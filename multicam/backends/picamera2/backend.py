from __future__ import annotations

import time

from multicam.core.cameras import (
    CameraBackend,
    CameraCapability,
    CameraDevice,
    CameraInfo,
    Frame,
)


class Picamera2Device(CameraDevice):

    _STANDARD_CONTROLS = {
        "brightness": ("Brightness", "Brightness", "float", None),
        "contrast": ("Contrast", "Contrast", "float", None),
        "saturation": ("Saturation", "Saturation", "float", None),
        "sharpness": ("Sharpness", "Sharpness", "float", None),
        "exposure_compensation": (
            "ExposureValue", "Exposure Compensation", "float", "EV"
        ),
        "auto_exposure": ("AeEnable", "Auto Exposure", "boolean", None),
        "auto_white_balance": (
            "AwbEnable", "Auto White Balance", "boolean", None
        ),
    }

    def __init__(self, info: CameraInfo):
        super().__init__(info)

        from picamera2 import Picamera2

        camera_num = info.metadata.get("num")

        if camera_num is None:
            raise RuntimeError(
                f"No Picamera2 camera number available for {info.id}"
            )

        self._camera = Picamera2(camera_num)

        self._preview_size = (1280, 960)
        self._preview_sizes = self._supported_preview_sizes()
        self._configure_preview(self._preview_size)

        self._running = False
        self._frame_number = 0

    def _maximum_sensor_size(self):
        modes = getattr(self._camera, "sensor_modes", ()) or ()
        sizes = [tuple(mode["size"]) for mode in modes if mode.get("size")]
        return max(sizes, key=lambda size: size[0] * size[1], default=None)

    def capture_calibration_frame(self):
        """Capture one maximum-resolution still, then restore live preview."""
        maximum_size = self._maximum_sensor_size()
        if maximum_size is None:
            return None

        still_config = self._camera.create_still_configuration(
            main={"size": maximum_size, "format": "RGB888"}
        )

        try:
            self._camera.configure(still_config)
            self._camera.start()
            image = self._camera.capture_array("main")
            metadata = dict(self._camera.capture_metadata())
            timestamp_ns = time.time_ns()
            monotonic_ns = time.monotonic_ns()
        finally:
            try:
                self._camera.stop()
            finally:
                self._configure_preview(self._preview_size)

        height, width = image.shape[:2]
        metadata.update({
            "capture_purpose": "alignment_calibration",
            "capture_quality": "maximum_sensor_resolution",
            "live_preview_size": self._preview_size,
            "sensor_capture_size": (width, height),
        })
        self._frame_number += 1
        return Frame(
            camera_id=self.id,
            image=image,
            timestamp_ns=timestamp_ns,
            monotonic_timestamp_ns=monotonic_ns,
            width=width,
            height=height,
            pixel_format="RGB888",
            bit_depth=8,
            frame_number=self._frame_number,
            metadata=metadata,
        )

    def _configure_preview(self, size):
        config = self._camera.create_preview_configuration(
            main={
                "size": size,
                "format": "RGB888",
            }
        )
        self._camera.configure(config)

    def _supported_preview_sizes(self):
        """Return conservative output sizes validated by Picamera2 config."""
        candidates = [
            (640, 480),
            (1280, 720),
            (1280, 960),
            (1920, 1080),
        ]
        supported = []

        for size in candidates:
            try:
                self._camera.create_preview_configuration(
                    main={"size": size, "format": "RGB888"}
                )
            except Exception:
                continue

            supported.append(size)

        if self._preview_size not in supported:
            supported.append(self._preview_size)

        return supported

    def start(self):
        if self._running:
            return

        self._camera.start()
        self._running = True

    def stop(self):
        if not self._running:
            return

        try:
            self._camera.stop()
        finally:
            self._running = False

    def close(self):
        try:
            self.stop()
        finally:
            self._camera.close()

    def get_frame(self, timeout=None):
        if not self._running:
            return None

        # Picamera2 capture_array is synchronous.
        # FrameBroker will later run acquisition in its own worker.
        image = self._camera.capture_array("main")
        metadata = self._camera.capture_metadata()

        self._frame_number += 1

        height, width = image.shape[:2]

        return Frame(
            camera_id=self.id,
            image=image,
            width=width,
            height=height,
            pixel_format="RGB888",
            bit_depth=8,
            frame_number=self._frame_number,
            metadata=dict(metadata),
        )

    def get_capabilities(self):
        capabilities = []

        controls = self._camera.camera_controls

        for control_id, definition in self._STANDARD_CONTROLS.items():
            libcamera_id, name, value_type, units = definition
            if libcamera_id not in controls:
                continue

            minimum, maximum, default = controls[libcamera_id]
            capabilities.append(CameraCapability(
                id=control_id,
                name=name,
                type=value_type,
                readable=True,
                writable=True,
                value=default,
                minimum=minimum if value_type != "boolean" else None,
                maximum=maximum if value_type != "boolean" else None,
                units=units,
                metadata={"libcamera_control": libcamera_id},
            ))

        if "ExposureTime" in controls:
            minimum, maximum, default = controls["ExposureTime"]

            capabilities.append(
                CameraCapability(
                    id="exposure",
                    name="Exposure",
                    type="integer",
                    readable=True,
                    writable=True,
                    value=default,
                    minimum=minimum,
                    maximum=maximum,
                    units="us",
                )
            )

        if "AnalogueGain" in controls:
            minimum, maximum, default = controls["AnalogueGain"]

            capabilities.append(
                CameraCapability(
                    id="gain",
                    name="Analogue Gain",
                    type="float",
                    readable=True,
                    writable=True,
                    value=default,
                    minimum=minimum,
                    maximum=maximum,
                )
            )

        if "AfMode" in controls:
            capabilities.append(
                CameraCapability(
                    id="focus_mode",
                    name="Focus Mode",
                    type="choice",
                    readable=True,
                    writable=True,
                    value="manual",
                    choices=["manual", "single", "continuous"],
                    metadata={
                        "purpose": "focus",
                        "profile_persistent": False,
                    },
                )
            )

        if "LensPosition" in controls:
            minimum, maximum, default = controls["LensPosition"]
            capabilities.append(
                CameraCapability(
                    id="focus_position",
                    name="Lens Position",
                    type="float",
                    readable=True,
                    writable=True,
                    value=default,
                    minimum=minimum,
                    maximum=maximum,
                    step=0.05,
                    units="diopters",
                    metadata={"purpose": "focus"},
                )
            )

        capabilities.append(
            CameraCapability(
                id="preview_resolution",
                name="Live Preview Resolution",
                type="choice",
                readable=True,
                writable=True,
                value=self._format_preview_size(self._preview_size),
                choices=[
                    self._format_preview_size(size)
                    for size in self._preview_sizes
                ],
                metadata={
                    "requires_stream_restart": True,
                    "profile_safe": True,
                    "purpose": "preview_output",
                },
            )
        )

        return capabilities

    def get_control(self, control_id):
        metadata = self._camera.capture_metadata()

        if control_id in self._STANDARD_CONTROLS:
            libcamera_id = self._STANDARD_CONTROLS[control_id][0]
            value = metadata.get(libcamera_id)
            if value is None:
                capability = next(
                    item for item in self.get_capabilities()
                    if item.id == control_id
                )
                value = capability.value
            return value

        if control_id == "exposure":
            return metadata.get("ExposureTime")

        if control_id == "gain":
            return metadata.get("AnalogueGain")

        if control_id == "focus_mode":
            return self._focus_mode_name(metadata.get("AfMode"))

        if control_id == "focus_position":
            return metadata.get("LensPosition")

        if control_id == "preview_resolution":
            return self._format_preview_size(self._preview_size)

        raise KeyError(control_id)

    def set_control(self, control_id, value):
        if control_id in self._STANDARD_CONTROLS:
            libcamera_id, _, value_type, _ = self._STANDARD_CONTROLS[
                control_id
            ]
            if value_type == "boolean":
                parsed = bool(value)
            elif value_type == "integer":
                parsed = int(value)
            else:
                parsed = float(value)

            self._camera.set_controls({libcamera_id: parsed})
            return

        if control_id == "exposure":
            self._camera.set_controls(
                {
                    "AeEnable": False,
                    "ExposureTime": int(value),
                }
            )
            return

        if control_id == "gain":
            self._camera.set_controls(
                {
                    "AeEnable": False,
                    "AnalogueGain": float(value),
                }
            )
            return

        if control_id == "focus_mode":
            modes = {
                "manual": 0,
                "single": 1,
                "continuous": 2,
            }
            mode = str(value).lower()

            if mode not in modes:
                raise ValueError(f"Unsupported focus mode: {value}")

            controls = {"AfMode": modes[mode]}

            if mode == "single":
                controls["AfTrigger"] = 0

            self._camera.set_controls(controls)
            return

        if control_id == "focus_position":
            position = float(value)
            capability = next(
                item
                for item in self.get_capabilities()
                if item.id == "focus_position"
            )

            if (
                capability.minimum is not None
                and position < float(capability.minimum)
            ) or (
                capability.maximum is not None
                and position > float(capability.maximum)
            ):
                raise ValueError("Lens position is outside the supported range")

            controls = {"LensPosition": position}

            if "AfMode" in self._camera.camera_controls:
                controls["AfMode"] = 0

            self._camera.set_controls(controls)
            return

        if control_id == "preview_resolution":
            if self._running:
                raise RuntimeError(
                    "Preview resolution requires the stream to be stopped"
                )

            size = self._parse_preview_size(value)

            if size not in self._preview_sizes:
                raise ValueError(
                    f"Unsupported preview resolution: {value}"
                )

            self._configure_preview(size)
            self._preview_size = size
            return

        raise KeyError(control_id)

    @staticmethod
    def _format_preview_size(size):
        return f"{size[0]}x{size[1]}"

    @staticmethod
    def _parse_preview_size(value):
        try:
            width_text, height_text = str(value).lower().split("x", 1)
            width = int(width_text.strip())
            height = int(height_text.strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Preview resolution must be WIDTHxHEIGHT"
            ) from exc

        if width <= 0 or height <= 0:
            raise ValueError("Preview dimensions must be positive")

        return width, height

    @staticmethod
    def _focus_mode_name(value):
        try:
            mode = int(value)
        except (TypeError, ValueError):
            return None

        return {
            0: "manual",
            1: "single",
            2: "continuous",
        }.get(mode, str(mode))


class Picamera2Backend(CameraBackend):
    name = "picamera2"

    def discover(self):
        try:
            from picamera2 import Picamera2
        except ImportError:
            return []

        cameras = []

        for item in Picamera2.global_camera_info():

            model = item.get("Model")
            camera_num = item.get("Num")
            camera_path = item.get("Id")

            persistent_part = (
                str(camera_path)
                if camera_path is not None
                else str(camera_num)
            )

            camera_id = f"picamera2:{persistent_part}"

            cameras.append(
                CameraInfo(
                    id=camera_id,
                    backend=self.name,
                    name=model or camera_id,
                    model=model,
                    vendor="Raspberry Pi/libcamera",
                    serial=None,
                    metadata={
                        "num": camera_num,
                        "location": item.get("Location"),
                        "rotation": item.get("Rotation"),
                        "raw_info": dict(item),
                    },
                )
            )

        return cameras

    def open(self, camera_id):
        for info in self.discover():
            if info.id == camera_id:
                return Picamera2Device(info)

        raise KeyError(camera_id)
