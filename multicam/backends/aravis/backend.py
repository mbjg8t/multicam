from __future__ import annotations

import gi

gi.require_version("Aravis", "0.8")
from gi.repository import Aravis

import numpy as np

from multicam.core.cameras import (
    CameraBackend,
    CameraCapability,
    CameraDevice,
    CameraInfo,
    Frame,
)


class AravisDevice(CameraDevice):

    def __init__(self, info: CameraInfo):
        super().__init__(info)

        device_id = info.metadata.get("aravis_device_id")

        if not device_id:
            raise RuntimeError(
                f"No Aravis device ID available for {info.id}"
            )

        self._camera = Aravis.Camera.new(device_id)

        if self._camera is None:
            raise RuntimeError(
                f"Unable to open Aravis camera: {device_id}"
            )

        self._stream = None
        self._running = False
        self._frame_number = 0

        self._update_identity()

    def _update_identity(self):
        try:
            serial = self._camera.get_device_serial_number()
        except Exception:
            serial = None

        if serial:
            self.info.serial = serial
            self.info.metadata["device_serial_number"] = serial

    def start(self):
        if self._running:
            return

        self._stream = self._camera.create_stream(None, None)

        if self._stream is None:
            raise RuntimeError(
                f"Unable to create stream for {self.id}"
            )

        payload = self._camera.get_payload()

        for _ in range(16):
            self._stream.push_buffer(
                Aravis.Buffer.new_allocate(payload)
            )

        self._camera.start_acquisition()
        self._running = True

    def stop(self):
        if not self._running:
            return

        try:
            self._camera.stop_acquisition()
        finally:
            self._running = False
            self._stream = None

    def get_frame(self, timeout=None):
        if not self._running or self._stream is None:
            return None

        if timeout is None:
            timeout_us = 1_000_000
        else:
            timeout_us = int(timeout * 1_000_000)

        buffer = self._stream.timeout_pop_buffer(timeout_us)

        if buffer is None:
            return None

        try:
            status = buffer.get_status()

            if status != Aravis.BufferStatus.SUCCESS:
                return None

            width = self._camera.get_region()[2]
            height = self._camera.get_region()[3]

            pixel_format = self._camera.get_pixel_format_as_string()

            data = buffer.get_data()

            if pixel_format == "Mono16":
                image = np.frombuffer(
                    data,
                    dtype=np.uint16,
                ).copy().reshape((height, width))

                bit_depth = 16

            elif pixel_format == "Mono8":
                image = np.frombuffer(
                    data,
                    dtype=np.uint8,
                ).copy().reshape((height, width))

                bit_depth = 8

            else:
                raise RuntimeError(
                    f"Unsupported Aravis pixel format: {pixel_format}"
                )

            self._frame_number += 1

            return Frame(
                camera_id=self.id,
                image=image,
                width=width,
                height=height,
                pixel_format=pixel_format,
                bit_depth=bit_depth,
                frame_number=self._frame_number,
                metadata={},
            )

        finally:
            self._stream.push_buffer(buffer)

    def get_capabilities(self):
        capabilities = []

        try:
            exposure = self._camera.get_exposure_time()

            capabilities.append(
                CameraCapability(
                    id="exposure",
                    name="Exposure",
                    type="float",
                    readable=True,
                    writable=True,
                    value=exposure,
                    units="us",
                )
            )
        except Exception:
            pass

        try:
            gain = self._camera.get_gain()

            capabilities.append(
                CameraCapability(
                    id="gain",
                    name="Gain",
                    type="float",
                    readable=True,
                    writable=True,
                    value=gain,
                )
            )
        except Exception:
            pass

        try:
            pixel_format = self._camera.get_pixel_format_as_string()

            capabilities.append(
                CameraCapability(
                    id="pixel_format",
                    name="Pixel Format",
                    type="choice",
                    readable=True,
                    writable=True,
                    value=pixel_format,
                    choices=["Mono8", "Mono16"],
                )
            )
        except Exception:
            pass

        return capabilities

    def get_control(self, control_id):
        if control_id == "exposure":
            return self._camera.get_exposure_time()

        if control_id == "gain":
            return self._camera.get_gain()

        if control_id == "pixel_format":
            return self._camera.get_pixel_format_as_string()

        raise KeyError(control_id)

    def set_control(self, control_id, value):
        if control_id == "exposure":
            self._camera.set_exposure_time(float(value))
            return

        if control_id == "gain":
            self._camera.set_gain(float(value))
            return

        if control_id == "pixel_format":
            self._camera.set_pixel_format_from_string(str(value))
            return

        raise KeyError(control_id)


class AravisBackend(CameraBackend):
    name = "aravis"

    def discover(self):
        Aravis.update_device_list()

        cameras = []

        for index in range(Aravis.get_n_devices()):
            device_id = Aravis.get_device_id(index)
            vendor = Aravis.get_device_vendor(index)
            model = Aravis.get_device_model(index)
            serial = Aravis.get_device_serial_nbr(index)

            # Aravis can occasionally expose an incomplete USB3Vision
            # discovery entry. Do not attempt to open it; doing so can
            # block startup while the device bootstrap times out.
            if not device_id or device_id in {"-", "--"}:
                continue

            persistent_part = serial or device_id

            camera_id = (
                f"aravis:{vendor or 'camera'}:{persistent_part}"
            )

            cameras.append(
                CameraInfo(
                    id=camera_id,
                    backend=self.name,
                    name=model or camera_id,
                    model=model,
                    vendor=vendor,
                    serial=serial or None,
                    metadata={
                        "aravis_device_id": device_id,
                        "index": index,
                    },
                )
            )

        return cameras

    def open(self, camera_id):
        for info in self.discover():
            if info.id == camera_id:
                return AravisDevice(info)

        raise KeyError(camera_id)
