from __future__ import annotations

from multicam.core.cameras import (
    CameraBackend,
    CameraCapability,
    CameraDevice,
    CameraInfo,
    Frame,
)


class Picamera2Device(CameraDevice):

    def __init__(self, info: CameraInfo):
        super().__init__(info)

        from picamera2 import Picamera2

        camera_num = info.metadata.get("num")

        if camera_num is None:
            raise RuntimeError(
                f"No Picamera2 camera number available for {info.id}"
            )

        self._camera = Picamera2(camera_num)

        # Temporary Multicam test configuration.
        # Later the stream/configuration service will own this.
        config = self._camera.create_preview_configuration(
            main={
                "size": (1280, 960),
                "format": "RGB888",
            }
        )

        self._camera.configure(config)

        self._running = False
        self._frame_number = 0

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

        return capabilities

    def get_control(self, control_id):
        metadata = self._camera.capture_metadata()

        if control_id == "exposure":
            return metadata.get("ExposureTime")

        if control_id == "gain":
            return metadata.get("AnalogueGain")

        raise KeyError(control_id)

    def set_control(self, control_id, value):
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

        raise KeyError(control_id)


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
