from __future__ import annotations

import time
from threading import RLock

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
        self._io_lock = RLock()

        self._sensor_modes = self._read_sensor_modes()
        # Sensor modes are not automatically safe continuous RGB preview
        # modes. Large OV64 modes can exhaust RAM/CMA on a 4 GB Pi once
        # Picamera2, NumPy, the compositor and JPEG buffers are combined.
        # Keep every detected mode visible as sensor/still capability, while
        # exposing only bounded modes for continuous live acquisition.
        self._preview_sizes = self._safe_preview_sizes_from_sensor_modes()
        if not self._preview_sizes:
            self._preview_sizes = self._supported_preview_sizes()
        preferred = (1920, 1080)
        self._preview_size = (
            preferred if preferred in self._preview_sizes
            else self._preview_sizes[0]
        )
        self._configure_preview(self._preview_size)

        self._running = False
        self._frame_number = 0

    def _read_sensor_modes(self):
        """Normalize the real libcamera sensor modes reported by Picamera2."""
        normalized = []
        seen = set()
        for raw in (getattr(self._camera, "sensor_modes", ()) or ()):
            size = raw.get("size")
            if not size:
                continue
            size = tuple(size)
            key = (size, raw.get("bit_depth"), str(raw.get("format") or ""))
            if key in seen:
                continue
            seen.add(key)
            normalized.append({
                "size": size,
                "fps": raw.get("fps"),
                "bit_depth": raw.get("bit_depth"),
                "format": str(raw.get("format") or ""),
                "crop_limits": tuple(raw.get("crop_limits") or ()),
            })
        return normalized


    def _safe_preview_sizes_from_sensor_modes(self):
        """Return sensor modes safe for continuous RGB888 live view.

        Full-resolution modes remain available through sensor_modes and the
        high-quality still path.  The bound intentionally protects 4 GB Pi
        systems from multi-buffer 48/64 MP RGB allocations.
        """
        max_pixels = 3840 * 2160
        sizes = []
        for mode in self._sensor_modes:
            size = tuple(mode["size"])
            if size[0] * size[1] <= max_pixels and size not in sizes:
                sizes.append(size)
        return sizes

    def _maximum_sensor_mode(self):
        modes = self._sensor_modes or self._read_sensor_modes()
        return max(
            modes,
            key=lambda mode: mode["size"][0] * mode["size"][1],
            default=None,
        )

    def _sensor_mode_for_size(self, size):
        modes = [m for m in getattr(self, "_sensor_modes", []) if m["size"] == tuple(size)]
        if not modes:
            return None
        return max(modes, key=lambda m: int(m.get("bit_depth") or 0))

    def capture_calibration_frame(self):
        """Capture one maximum-resolution still and restore the live stream."""
        maximum_mode = self._maximum_sensor_mode()
        if maximum_mode is None:
            return None
        maximum_size = maximum_mode["size"]
        sensor = {"output_size": maximum_size}
        if maximum_mode.get("bit_depth"):
            sensor["bit_depth"] = maximum_mode["bit_depth"]

        with self._io_lock:
            was_running = self._running
            if was_running:
                self._camera.stop()
            try:
                still_config = self._camera.create_still_configuration(
                    main={"size": maximum_size, "format": "RGB888"},
                    sensor=sensor,
                )
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
                    if was_running:
                        self._camera.start()

        height, width = image.shape[:2]
        metadata.update({
            "capture_purpose": "high_quality_still",
            "capture_quality": "maximum_sensor_resolution",
            "live_preview_size": self._preview_size,
            "sensor_capture_size": (width, height),
            "sensor_bit_depth": maximum_mode.get("bit_depth"),
            "sensor_format": maximum_mode.get("format"),
            "sensor_crop_limits": maximum_mode.get("crop_limits"),
        })
        self._frame_number += 1
        return Frame(
            camera_id=self.id, image=image, timestamp_ns=timestamp_ns,
            monotonic_timestamp_ns=monotonic_ns, width=width, height=height,
            pixel_format="RGB888", bit_depth=8,
            frame_number=self._frame_number, metadata=metadata,
        )

    def _configure_preview(self, size):
        mode = self._sensor_mode_for_size(size)
        kwargs = {
            "main": {"size": size, "format": "RGB888"},
        }
        if mode is not None:
            sensor = {"output_size": size}
            if mode.get("bit_depth"):
                sensor["bit_depth"] = mode["bit_depth"]
            kwargs["sensor"] = sensor
        config = self._camera.create_preview_configuration(**kwargs)
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
        with self._io_lock:
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

        if getattr(self, "_sensor_modes", None):
            maximum = self._maximum_sensor_mode()
            mode_lines = []
            for mode in self._sensor_modes:
                width, height = mode["size"]
                fps = mode.get("fps")
                fps_text = f" @ {float(fps):.2f} fps" if fps else ""
                depth = mode.get("bit_depth")
                depth_text = f" • {depth}-bit" if depth else ""
                crop = mode.get("crop_limits")
                crop_text = f" • crop {crop}" if crop else ""
                suffix = " • MAX" if mode is maximum else ""
                mode_lines.append(
                    f"{width}x{height}{fps_text}{depth_text}{crop_text}{suffix}"
                )
            capabilities.append(CameraCapability(
                id="sensor_modes",
                name="Detected Sensor Modes",
                type="text",
                readable=True,
                writable=False,
                value=" | ".join(mode_lines),
                metadata={
                    "section": "Sensor",
                    "modes": self._sensor_modes,
                    "usage": "still_capture",
                    "maximum_still_size": maximum["size"] if maximum else None,
                },
            ))

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
                    "safety_note": (
                        "Large sensor modes are still-capture only to prevent "
                        "live-view memory exhaustion."
                    ),
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

            # libcamera can enumerate FLIR UVC devices, but its Picamera2 path
            # interprets the Boson's packed Y16 stream as a 1280-pixel-wide
            # image. Leave these devices exclusively to the Boson backend.
            model_text = str(model or "").lower()
            if "boson" in model_text or "flir" in model_text:
                continue

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
