from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from multicam.core.cameras import FrameBroker
from multicam.core.imaging import Compositor


@dataclass(frozen=True, slots=True)
class FocusSample:
    camera_id: str
    frame_number: int | None
    timestamp_ns: int
    width: int
    height: int
    roi: tuple[int, int, int, int]
    tenengrad: float
    laplacian: float
    contrast: float
    lens_position: float | None
    autofocus_state: int | None


class FocusService:
    """Analyze sharpness from centrally acquired preview frames."""

    def __init__(
        self,
        *,
        broker: FrameBroker,
        orientation_store,
        compositor: Compositor,
    ):
        self.broker = broker
        self.orientation_store = orientation_store
        self.compositor = compositor

    def display_image(self, camera_id: str) -> np.ndarray:
        frame = self.broker.get_latest(camera_id)

        if frame is None:
            raise ValueError(f"No frame available for {camera_id}")

        return self.compositor.orient_display_image(
            frame.image,
            self.orientation_store.get(camera_id),
        )

    def analyze(
        self,
        camera_id: str,
        *,
        center_x: float = 0.5,
        center_y: float = 0.5,
        size: float = 0.25,
    ) -> FocusSample:
        frame = self.broker.get_latest(camera_id)

        if frame is None:
            raise ValueError(f"No frame available for {camera_id}")

        gray = self._oriented_gray(frame.image, camera_id)
        height, width = gray.shape
        roi_box = self.roi_box(
            width,
            height,
            center_x=center_x,
            center_y=center_y,
            size=size,
        )
        x0, y0, x1, y1 = roi_box
        gray = gray[y0:y1, x0:x1]
        gray = self._limit_size(gray, max_dimension=512)
        normalized, contrast = self._normalize(gray)
        tenengrad = self._tenengrad(normalized)
        laplacian = self._laplacian_variance(normalized)
        metadata = frame.metadata or {}

        return FocusSample(
            camera_id=camera_id,
            frame_number=frame.frame_number,
            timestamp_ns=frame.timestamp_ns,
            width=width,
            height=height,
            roi=roi_box,
            tenengrad=tenengrad,
            laplacian=laplacian,
            contrast=contrast,
            lens_position=self._optional_float(
                metadata.get("LensPosition")
            ),
            autofocus_state=self._optional_int(metadata.get("AfState")),
        )

    @staticmethod
    def roi_box(
        width: int,
        height: int,
        *,
        center_x: float,
        center_y: float,
        size: float,
    ) -> tuple[int, int, int, int]:
        if width <= 0 or height <= 0:
            raise ValueError("Frame dimensions must be positive")
        if not (0.0 <= center_x <= 1.0 and 0.0 <= center_y <= 1.0):
            raise ValueError("ROI center must be inside the frame")
        if not (0.05 <= size <= 1.0):
            raise ValueError("ROI size must be between 5% and 100%")

        roi_width = max(16, min(width, int(round(width * size))))
        roi_height = max(16, min(height, int(round(height * size))))
        center_pixel_x = int(round(center_x * (width - 1)))
        center_pixel_y = int(round(center_y * (height - 1)))
        x0 = min(max(0, center_pixel_x - roi_width // 2), width - roi_width)
        y0 = min(max(0, center_pixel_y - roi_height // 2), height - roi_height)
        return x0, y0, x0 + roi_width, y0 + roi_height

    @staticmethod
    def _gray(image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            return image.astype(np.float32)
        if image.ndim == 3 and image.shape[2] >= 3:
            return (
                image[..., 0].astype(np.float32) * 0.299
                + image[..., 1].astype(np.float32) * 0.587
                + image[..., 2].astype(np.float32) * 0.114
            )
        raise ValueError(f"Unsupported image shape: {image.shape}")

    def _oriented_gray(self, image, camera_id: str) -> np.ndarray:
        gray = self._gray(np.asarray(image))
        orientation = self.orientation_store.get(camera_id)

        if orientation.rotation_deg == 90:
            gray = np.rot90(gray, k=3)
        elif orientation.rotation_deg == 180:
            gray = np.rot90(gray, k=2)
        elif orientation.rotation_deg == 270:
            gray = np.rot90(gray, k=1)

        if orientation.flip_horizontal:
            gray = np.fliplr(gray)
        if orientation.flip_vertical:
            gray = np.flipud(gray)

        return gray

    @staticmethod
    def _limit_size(
        image: np.ndarray,
        *,
        max_dimension: int,
    ) -> np.ndarray:
        height, width = image.shape

        if max(width, height) <= max_dimension:
            return image

        scale = max_dimension / max(width, height)
        output_width = max(1, int(round(width * scale)))
        output_height = max(1, int(round(height * scale)))
        resized = Image.fromarray(image.astype(np.float32)).resize(
            (output_width, output_height),
            resample=Image.Resampling.BILINEAR,
        )
        return np.asarray(resized, dtype=np.float32)

    @staticmethod
    def _normalize(gray: np.ndarray) -> tuple[np.ndarray, float]:
        low = float(np.percentile(gray, 2))
        high = float(np.percentile(gray, 98))
        contrast = high - low

        if contrast <= 1e-6:
            return np.zeros(gray.shape, dtype=np.float32), contrast

        return (
            np.clip((gray - low) / contrast, 0.0, 1.0).astype(np.float32),
            contrast,
        )

    @staticmethod
    def _tenengrad(gray: np.ndarray) -> float:
        if min(gray.shape) < 3:
            return 0.0

        padded = np.pad(gray, 1, mode="edge")
        gx = (
            padded[:-2, 2:]
            + 2.0 * padded[1:-1, 2:]
            + padded[2:, 2:]
            - padded[:-2, :-2]
            - 2.0 * padded[1:-1, :-2]
            - padded[2:, :-2]
        )
        gy = (
            padded[2:, :-2]
            + 2.0 * padded[2:, 1:-1]
            + padded[2:, 2:]
            - padded[:-2, :-2]
            - 2.0 * padded[:-2, 1:-1]
            - padded[:-2, 2:]
        )
        return float(np.mean(gx * gx + gy * gy))

    @staticmethod
    def _laplacian_variance(gray: np.ndarray) -> float:
        if min(gray.shape) < 3:
            return 0.0

        padded = np.pad(gray, 1, mode="edge")
        laplacian = (
            padded[1:-1, :-2]
            + padded[1:-1, 2:]
            + padded[:-2, 1:-1]
            + padded[2:, 1:-1]
            - 4.0 * gray
        )
        return float(np.var(laplacian))

    @staticmethod
    def _optional_float(value) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_int(value) -> int | None:
        try:
            return None if value is None else int(value)
        except (TypeError, ValueError):
            return None
