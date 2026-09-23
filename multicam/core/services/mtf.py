from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any
import math

import numpy as np

from multicam.core.cameras import Frame, FrameBroker


@dataclass(frozen=True, slots=True)
class MtfFrozenFrame:
    camera_id: str
    width: int
    height: int
    timestamp_ns: int
    frame_number: int | None


class MtfService:
    """Raw-frame MTF and bar-target measurement service."""

    def __init__(self, broker: FrameBroker, orientation_store=None):
        self.broker = broker
        self.orientation_store = orientation_store
        self._frames: dict[str, Frame] = {}
        self._lock = RLock()

    def freeze(self, camera_id: str) -> MtfFrozenFrame:
        preview = self.broker.get_latest(camera_id)
        try:
            frame = self.broker.capture_calibration_frame(camera_id)
        except (AttributeError, NotImplementedError):
            frame = None
        if frame is None:
            frame = preview
        if frame is None:
            raise ValueError(f"No live frame available for {camera_id}")

        frozen = Frame(
            camera_id=frame.camera_id,
            image=np.array(frame.image, copy=True),
            timestamp_ns=frame.timestamp_ns,
            monotonic_timestamp_ns=frame.monotonic_timestamp_ns,
            device_timestamp_ns=frame.device_timestamp_ns,
            width=frame.width,
            height=frame.height,
            pixel_format=frame.pixel_format,
            bit_depth=frame.bit_depth,
            frame_number=frame.frame_number,
            metadata=dict(frame.metadata),
        )
        with self._lock:
            self._frames[camera_id] = frozen
        return self._info(frozen)

    def get_frozen(self, camera_id: str) -> Frame | None:
        with self._lock:
            return self._frames.get(camera_id)

    def get_oriented_image(self, camera_id: str) -> np.ndarray | None:
        """Return the frozen image in the same orientation shown to the user."""
        frame = self.get_frozen(camera_id)
        if frame is None:
            return None
        if self.orientation_store is None:
            return frame.image
        orientation = self.orientation_store.get(camera_id)
        output = frame.image
        if orientation.rotation_deg == 90:
            output = np.rot90(output, k=3)
        elif orientation.rotation_deg == 180:
            output = np.rot90(output, k=2)
        elif orientation.rotation_deg == 270:
            output = np.rot90(output, k=1)
        if orientation.flip_horizontal:
            output = np.fliplr(output)
        if orientation.flip_vertical:
            output = np.flipud(output)
        return output

    def analyze(
        self,
        camera_id: str,
        roi: tuple[float, float, float, float],
        mode: str,
        roi_space: str = "normalized",
    ) -> dict[str, Any]:
        frame = self.get_frozen(camera_id)
        if frame is None:
            raise ValueError("Freeze the selected camera first")

        oriented = self.get_oriented_image(camera_id)
        gray = self._gray(oriented)
        x0, y0, x1, y1 = self._roi_pixels(roi, gray.shape, roi_space)
        crop = gray[y0:y1, x0:x1]
        if mode == "slanted_edge":
            result = self._slanted_edge(crop)
        elif mode == "usaf_bar":
            result = self._bar_modulation(crop)
        else:
            raise ValueError("Unknown MTF analysis mode")

        result.update({
            "camera_id": camera_id,
            "mode": mode,
            "roi_pixels": [x0, y0, x1, y1],
            "frame_width": int(gray.shape[1]),
            "frame_height": int(gray.shape[0]),
            "frame_number": frame.frame_number,
            "timestamp_ns": frame.timestamp_ns,
        })
        return result

    def _info(self, frame: Frame) -> MtfFrozenFrame:
        image = self.get_oriented_image(frame.camera_id)
        height, width = image.shape[:2]
        return MtfFrozenFrame(
            camera_id=frame.camera_id,
            width=width,
            height=height,
            timestamp_ns=frame.timestamp_ns,
            frame_number=frame.frame_number,
        )

    @staticmethod
    def _gray(image: np.ndarray) -> np.ndarray:
        values = np.asarray(image)
        if values.ndim == 2:
            return values.astype(np.float64)
        if values.ndim == 3 and values.shape[2] >= 3:
            return (
                0.2126 * values[:, :, 0]
                + 0.7152 * values[:, :, 1]
                + 0.0722 * values[:, :, 2]
            ).astype(np.float64)
        raise ValueError("Unsupported frame format for MTF analysis")

    @staticmethod
    def _roi_pixels(roi, shape, roi_space="normalized"):
        if len(roi) != 4:
            raise ValueError("ROI must contain x0, y0, x1 and y1")
        height, width = shape
        values = [float(value) for value in roi]
        if roi_space == "normalized":
            values = [
                values[0] * width, values[1] * height,
                values[2] * width, values[3] * height,
            ]
        elif roi_space != "pixels":
            raise ValueError("ROI coordinate space must be normalized or pixels")
        x0, x1 = sorted((int(round(values[0])), int(round(values[2]))))
        y0, y1 = sorted((int(round(values[1])), int(round(values[3]))))
        x0, x1 = max(0, x0), min(width, x1)
        y0, y1 = max(0, y0), min(height, y1)
        if x1 - x0 < 24 or y1 - y0 < 24:
            raise ValueError("Select an ROI at least 24 x 24 pixels")
        return x0, y0, x1, y1

    @classmethod
    def _slanted_edge(cls, gray: np.ndarray) -> dict[str, Any]:
        gy, gx = np.gradient(gray)
        magnitude = np.hypot(gx, gy)
        threshold = float(np.percentile(magnitude, 88.0))
        yy, xx = np.nonzero(magnitude >= threshold)
        if len(xx) < 80:
            raise ValueError("ROI does not contain enough edge pixels")

        weights = magnitude[yy, xx]
        points = np.column_stack((xx, yy)).astype(np.float64)
        center = np.average(points, axis=0, weights=weights)
        centered = points - center
        covariance = (centered * weights[:, None]).T @ centered
        _, vectors = np.linalg.eigh(covariance)
        tangent = vectors[:, -1]
        normal = np.array((-tangent[1], tangent[0]))
        distances = (
            (np.indices(gray.shape)[1] - center[0]) * normal[0]
            + (np.indices(gray.shape)[0] - center[1]) * normal[1]
        ).ravel()
        intensities = gray.ravel()

        half_width = min(20.0, float(np.percentile(np.abs(distances), 55)))
        selected = np.abs(distances) <= half_width
        distances = distances[selected]
        intensities = intensities[selected]
        bin_width = 0.25
        edges = np.arange(-half_width, half_width + bin_width, bin_width)
        positions = 0.5 * (edges[:-1] + edges[1:])
        indices = np.digitize(distances, edges) - 1
        sums = np.zeros(len(positions), dtype=np.float64)
        counts = np.zeros(len(positions), dtype=np.int64)
        valid = (indices >= 0) & (indices < len(positions))
        np.add.at(sums, indices[valid], intensities[valid])
        np.add.at(counts, indices[valid], 1)
        populated = counts > 0
        if np.count_nonzero(populated) < 48:
            raise ValueError("ROI does not produce a complete edge profile")
        esf = np.interp(positions, positions[populated], sums[populated] / counts[populated])
        positions, esf, contrast = cls._normalize_esf(positions, esf)
        curve = cls._calculate_mtf(positions, esf)

        angle = math.degrees(math.atan2(tangent[1], tangent[0]))
        slant = min(abs(angle) % 90.0, 90.0 - (abs(angle) % 90.0))
        valid_slant = 2.0 <= slant <= 20.0
        dynamic_range = float(
            np.percentile(gray, 95.0) - np.percentile(gray, 5.0)
        )
        contrast_fraction = contrast / max(dynamic_range, 1e-9)
        valid_contrast = contrast_fraction >= 0.20
        warnings = []
        if not valid_slant:
            warnings.append(
                "Edge slant should be 2 to 20 degrees from an image axis"
            )
        if not valid_contrast:
            warnings.append(
                "Edge profile is not isolated; select one clean edge with "
                "uniform areas on both sides"
            )
        return {
            "valid": bool(
                valid_slant and valid_contrast
                and curve["mtf50"] is not None
            ),
            "warning": "; ".join(warnings) or None,
            "edge_angle_degrees": angle,
            "slant_degrees": slant,
            "contrast": contrast,
            "contrast_fraction": contrast_fraction,
            "mtf50_cycles_per_pixel": curve["mtf50"],
            "mtf20_cycles_per_pixel": curve["mtf20"],
            "mtf10_cycles_per_pixel": curve["mtf10"],
            "mtf_at_nyquist": curve["mtf_at_nyquist"],
            "frequency_cycles_per_pixel": curve["frequency"].tolist(),
            "mtf": curve["mtf"].tolist(),
            "esf_position_px": positions.tolist(),
            "esf": esf.tolist(),
        }

    @staticmethod
    def _normalize_esf(position, esf):
        plateau = max(12, int(round(len(esf) * 0.18)))
        left = float(np.median(esf[:plateau]))
        right = float(np.median(esf[-plateau:]))
        if right < left:
            esf = esf[::-1]
            position = -position[::-1]
            left = float(np.median(esf[:plateau]))
            right = float(np.median(esf[-plateau:]))
        amplitude = right - left
        if amplitude <= 5.0:
            raise ValueError("Edge contrast is too low for MTF measurement")
        return position, (esf - left) / amplitude, amplitude

    @staticmethod
    def _crossing(frequency, mtf, level):
        for index in range(1, len(mtf)):
            if mtf[index - 1] >= level >= mtf[index]:
                x0, x1 = frequency[index - 1:index + 1]
                y0, y1 = mtf[index - 1:index + 1]
                if abs(y1 - y0) < 1e-12:
                    return float(x0)
                return float(x0 + (level - y0) * (x1 - x0) / (y1 - y0))
        return None

    @classmethod
    def _calculate_mtf(cls, position, esf):
        spacing = float(np.median(np.diff(position)))
        lsf = np.gradient(esf, spacing)
        weights = np.abs(lsf)
        center = float(np.sum(position * weights) / np.sum(weights))
        centered = position - center
        span = min(abs(centered[0]), abs(centered[-1]))
        segment = lsf[np.abs(centered) <= span]
        if len(segment) < 32:
            raise ValueError("Insufficient edge support for MTF measurement")
        windowed = segment * np.hamming(len(segment))
        nfft = 1
        while nfft < max(4096, 16 * len(windowed)):
            nfft *= 2
        magnitude = np.abs(np.fft.rfft(windowed, n=nfft))
        if magnitude[0] <= 1e-12:
            raise ValueError("Edge profile has no usable frequency response")
        frequency = np.fft.rfftfreq(nfft, d=spacing)
        mtf = magnitude / magnitude[0]
        keep = frequency <= 0.5
        frequency, mtf = frequency[keep], mtf[keep]
        return {
            "frequency": frequency,
            "mtf": mtf,
            "mtf50": cls._crossing(frequency, mtf, 0.50),
            "mtf20": cls._crossing(frequency, mtf, 0.20),
            "mtf10": cls._crossing(frequency, mtf, 0.10),
            "mtf_at_nyquist": float(mtf[-1]),
        }

    @staticmethod
    def _bar_modulation(gray: np.ndarray) -> dict[str, Any]:
        row_profile = np.mean(gray, axis=1)
        column_profile = np.mean(gray, axis=0)
        row_strength = float(np.std(row_profile))
        column_strength = float(np.std(column_profile))
        if column_strength >= row_strength:
            profile = column_profile
            orientation = "vertical bars"
        else:
            profile = row_profile
            orientation = "horizontal bars"

        profile = profile - np.mean(profile)
        spectrum = np.abs(np.fft.rfft(profile))
        if len(spectrum) < 3:
            raise ValueError("Bar ROI is too small")
        spectrum[0] = 0.0
        peak = int(np.argmax(spectrum))
        cycles_per_pixel = peak / len(profile)
        low = float(np.percentile(gray, 10.0))
        high = float(np.percentile(gray, 90.0))
        denominator = high + low
        if high - low <= 5.0 or denominator <= 1e-9:
            raise ValueError("Bar contrast is too low")
        modulation = (high - low) / denominator
        valid = peak >= 2 and cycles_per_pixel <= 0.5
        warning = None
        if peak < 2:
            warning = (
                "ROI does not contain a distinct tri-bar element; select one "
                "small three-bar pattern instead of the complete chart"
            )
        return {
            "valid": bool(valid),
            "warning": warning,
            "orientation": orientation,
            "modulation": modulation,
            "contrast_percent": modulation * 100.0,
            "dominant_frequency_cycles_per_pixel": cycles_per_pixel,
            "dark_level": low,
            "bright_level": high,
            "profile": profile.tolist(),
        }
