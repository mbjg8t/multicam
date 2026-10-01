from __future__ import annotations

import re
import subprocess
import time
from collections.abc import Callable
from typing import Any

import numpy as np

from multicam.core.cameras import (
    CameraBackend,
    CameraCapability,
    CameraDevice,
    CameraInfo,
    Frame,
)


BOSON_SIZES = ((640, 512), (640, 514), (320, 256))
COLORMAPS = ("gray", "inferno", "turbo", "jet", "magma", "hot", "bone")


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )


def _parse_video_blocks(output: str) -> list[tuple[str, list[str]]]:
    blocks: list[tuple[str, list[str]]] = []
    heading: str | None = None
    devices: list[str] = []

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("/dev/video"):
            if heading is not None:
                devices.append(stripped)
            continue
        if heading is not None:
            blocks.append((heading, devices))
        heading = stripped.rstrip(":")
        devices = []

    if heading is not None:
        blocks.append((heading, devices))
    return blocks


def _parse_sizes(output: str) -> list[tuple[int, int]]:
    sizes = {
        (int(width), int(height))
        for width, height in re.findall(r"(\d{2,5})x(\d{2,5})", output)
    }
    return sorted(sizes, key=lambda size: size[0] * size[1], reverse=True)


class BosonDevice(CameraDevice):
    def __init__(
        self,
        info: CameraInfo,
        capture_factory: Callable[[str], Any] | None = None,
        cv2_module: Any | None = None,
    ):
        super().__init__(info)
        self._cv2 = cv2_module
        self._capture_factory = capture_factory
        self._capture = None
        self._running = False
        self._frame_number = 0
        self._controls: dict[str, Any] = {
            "colormap": "inferno",
            "auto_contrast": True,
            "contrast_low_percentile": 1.0,
            "contrast_high_percentile": 99.0,
            "crop_telemetry_rows": True,
        }

    def _opencv(self):
        if self._cv2 is None:
            try:
                import cv2
            except ImportError as exc:
                raise RuntimeError(
                    "Boson support requires OpenCV (python3-opencv or "
                    "multicam[boson])"
                ) from exc
            self._cv2 = cv2
        return self._cv2

    def _new_capture(self):
        device_path = self.info.metadata["device_path"]
        if self._capture_factory is not None:
            return self._capture_factory(device_path)
        cv2 = self._opencv()
        return cv2.VideoCapture(device_path, cv2.CAP_V4L2)

    def start(self) -> None:
        if self._running:
            return
        capture = self._new_capture()
        width, height = self.info.metadata["capture_size"]
        cv2 = self._opencv()
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(
                f"Could not open Boson device: {self.info.metadata['device_path']}"
            )
        self._capture = capture
        self._running = True

    def stop(self) -> None:
        capture, self._capture = self._capture, None
        self._running = False
        if capture is not None:
            capture.release()

    def get_frame(self, timeout: float | None = None) -> Frame | None:
        del timeout
        if not self._running or self._capture is None:
            return None
        ok, image = self._capture.read()
        if not ok or image is None:
            return None
        return self._make_frame(image)

    def capture_calibration_frame(self) -> Frame | None:
        self.start()
        try:
            for _ in range(3):
                ok, image = self._capture.read()
                if ok and image is not None:
                    frame = self._make_frame(image)
                    frame.metadata.update({
                        "capture_purpose": "alignment_calibration",
                        "capture_quality": "native_sensor_resolution",
                    })
                    return frame
            return None
        finally:
            self.stop()

    def _make_frame(self, image: np.ndarray) -> Frame:
        gray = self._to_gray(image)
        if self._controls["crop_telemetry_rows"] and gray.shape == (514, 640):
            gray = gray[:512, :]
        display = self._render(gray)
        self._frame_number += 1
        height, width = display.shape[:2]
        return Frame(
            camera_id=self.id,
            image=display,
            timestamp_ns=time.time_ns(),
            monotonic_timestamp_ns=time.monotonic_ns(),
            width=width,
            height=height,
            pixel_format="RGB888" if display.ndim == 3 else "Mono8",
            bit_depth=8,
            frame_number=self._frame_number,
            metadata={
                "source": "FLIR Boson UVC",
                "device_path": self.info.metadata["device_path"],
                "source_shape": tuple(image.shape),
                "colormap": self._controls["colormap"],
                "auto_contrast": self._controls["auto_contrast"],
            },
        )

    def _to_gray(self, image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            return image
        if image.ndim == 3 and image.shape[2] == 1:
            return image[:, :, 0]
        if image.ndim == 3 and image.shape[2] >= 3:
            return self._opencv().cvtColor(image[:, :, :3], self._opencv().COLOR_BGR2GRAY)
        raise ValueError(f"Unsupported Boson frame shape: {image.shape}")

    def _render(self, gray: np.ndarray) -> np.ndarray:
        if self._controls["auto_contrast"]:
            low = float(np.percentile(gray, self._controls["contrast_low_percentile"]))
            high = float(np.percentile(gray, self._controls["contrast_high_percentile"]))
            if high > low:
                normalized = ((gray.astype(np.float32) - low) * (255.0 / (high - low)))
                normalized = normalized.clip(0, 255).astype(np.uint8)
            else:
                normalized = np.zeros(gray.shape, dtype=np.uint8)
        elif gray.dtype == np.uint8:
            normalized = gray.copy()
        else:
            normalized = (gray.astype(np.float32) / 257.0).clip(0, 255).astype(np.uint8)

        colormap = self._controls["colormap"]
        if colormap == "gray":
            return normalized
        cv2 = self._opencv()
        map_id = getattr(cv2, f"COLORMAP_{colormap.upper()}")
        bgr = cv2.applyColorMap(normalized, map_id)
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    def get_capabilities(self) -> list[CameraCapability]:
        thermal = {"section": "Thermal", "session_default": None}
        return [
            CameraCapability(
                id="colormap", name="Palette", type="choice",
                writable=True, value="inferno", choices=list(COLORMAPS),
                metadata={**thermal, "session_default": "inferno"},
            ),
            CameraCapability(
                id="auto_contrast", name="Automatic Contrast", type="boolean",
                writable=True, value=True,
                metadata={**thermal, "session_default": True},
            ),
            CameraCapability(
                id="contrast_low_percentile", name="Contrast Low Clip",
                type="float", writable=True, value=1.0,
                minimum=0.0, maximum=20.0, step=0.5, units="%",
                metadata={**thermal, "session_default": 1.0},
            ),
            CameraCapability(
                id="contrast_high_percentile", name="Contrast High Clip",
                type="float", writable=True, value=99.0,
                minimum=80.0, maximum=100.0, step=0.5, units="%",
                metadata={**thermal, "session_default": 99.0},
            ),
            CameraCapability(
                id="crop_telemetry_rows", name="Crop Telemetry Rows",
                type="boolean", writable=True, value=True,
                metadata={**thermal, "session_default": True},
            ),
            CameraCapability(
                id="device_path", name="Video Device", type="string",
                writable=False, value=self.info.metadata["device_path"],
                metadata={"section": "Sensor"},
            ),
        ]

    def get_control(self, control_id: str):
        if control_id == "device_path":
            return self.info.metadata["device_path"]
        if control_id not in self._controls:
            raise KeyError(control_id)
        return self._controls[control_id]

    def set_control(self, control_id: str, value):
        if control_id not in self._controls:
            raise KeyError(control_id)
        if control_id == "colormap":
            value = str(value).lower()
            if value not in COLORMAPS:
                raise ValueError(f"Unsupported Boson palette: {value}")
        elif control_id in ("auto_contrast", "crop_telemetry_rows"):
            value = bool(value)
        elif control_id == "contrast_low_percentile":
            value = max(0.0, min(20.0, float(value)))
            if value >= self._controls["contrast_high_percentile"]:
                raise ValueError("Low contrast clip must be below high clip")
        elif control_id == "contrast_high_percentile":
            value = max(80.0, min(100.0, float(value)))
            if value <= self._controls["contrast_low_percentile"]:
                raise ValueError("High contrast clip must be above low clip")
        self._controls[control_id] = value
        return value


class BosonBackend(CameraBackend):
    name = "boson"

    def __init__(self, runner: Callable[[list[str]], Any] = _run_command):
        self._runner = runner
        self._cameras: dict[str, CameraInfo] = {}

    def discover(self) -> list[CameraInfo]:
        listing = self._runner(["v4l2-ctl", "--list-devices"])
        if listing.returncode != 0:
            return []
        discovered: dict[str, CameraInfo] = {}
        for heading, device_paths in _parse_video_blocks(listing.stdout):
            if "boson" not in heading.lower() and "flir" not in heading.lower():
                continue
            for device_path in device_paths:
                formats = self._runner([
                    "v4l2-ctl", "-d", device_path, "--list-formats-ext"
                ])
                sizes = _parse_sizes(formats.stdout + formats.stderr)
                capture_size = next((size for size in sizes if size in BOSON_SIZES), None)
                if capture_size is None:
                    continue
                camera_id = f"boson:{device_path}"
                discovered[camera_id] = CameraInfo(
                    id=camera_id,
                    backend=self.name,
                    name=heading,
                    model="Boson",
                    vendor="Teledyne FLIR",
                    metadata={
                        "device_path": device_path,
                        "capture_size": capture_size,
                        "supported_sizes": sizes,
                    },
                )
        self._cameras = discovered
        return list(discovered.values())

    def open(self, camera_id: str) -> CameraDevice:
        info = self._cameras.get(camera_id)
        if info is None:
            raise KeyError(camera_id)
        return BosonDevice(info)
