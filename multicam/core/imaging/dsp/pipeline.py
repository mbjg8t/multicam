from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageFilter

from .state import DspConfig


class DspPipeline:
    """Portable, geometry-preserving display DSP pipeline."""

    @classmethod
    def process(cls, image: np.ndarray, config: DspConfig) -> np.ndarray:
        source = np.asarray(image)

        if source.ndim not in (2, 3):
            raise ValueError(f"Unsupported DSP image shape: {source.shape}")
        if source.ndim == 3 and source.shape[2] != 3:
            raise ValueError(f"Unsupported DSP image shape: {source.shape}")

        rgb = cls._to_float_rgb(source)
        luminance = cls._luminance(rgb)
        # Bound percentile work on very large previews. The complete image is
        # still processed; only the statistics use a regular spatial sample.
        sample_step = max(
            1,
            math.ceil(math.sqrt(luminance.size / 262_144)),
        )
        sample = luminance[::sample_step, ::sample_step]
        black = float(np.percentile(sample, config.black_percentile))
        white = float(np.percentile(sample, config.white_percentile))

        if white <= black + 1e-9:
            normalized = np.clip(rgb, 0.0, 1.0)
        else:
            normalized = np.clip((rgb - black) / (white - black), 0.0, 1.0)

        normalized = np.power(
            normalized,
            1.0 / float(config.gamma),
            dtype=np.float32,
        )
        output = np.rint(normalized * 255.0).astype(np.uint8)

        if config.denoise_radius:
            output = np.asarray(
                Image.fromarray(output).filter(
                    ImageFilter.BoxBlur(config.denoise_radius)
                )
            )

        if config.sharpen > 0:
            percent = int(round(config.sharpen * 100.0))
            output = np.asarray(
                Image.fromarray(output).filter(
                    ImageFilter.UnsharpMask(
                        radius=1.5,
                        percent=percent,
                        threshold=2,
                    )
                )
            )

        gray = cls._luminance(output.astype(np.float32) / 255.0)

        if config.palette == "iron":
            output = cls._iron_palette(gray)
        elif config.palette == "grayscale" or config.grayscale:
            gray_u8 = np.rint(gray * 255.0).astype(np.uint8)
            output = np.repeat(gray_u8[:, :, None], 3, axis=2)

        if config.invert:
            output = 255 - output

        return np.ascontiguousarray(output, dtype=np.uint8)

    @staticmethod
    def _to_float_rgb(image: np.ndarray) -> np.ndarray:
        values = image.astype(np.float32)
        scale = float(np.iinfo(image.dtype).max) if np.issubdtype(
            image.dtype,
            np.integer,
        ) else float(np.nanmax(values) or 1.0)

        values = np.nan_to_num(values / max(scale, 1.0), copy=False)

        if values.ndim == 2:
            values = np.repeat(values[:, :, None], 3, axis=2)

        return np.clip(values, 0.0, 1.0)

    @staticmethod
    def _luminance(rgb: np.ndarray) -> np.ndarray:
        return (
            rgb[:, :, 0] * 0.299
            + rgb[:, :, 1] * 0.587
            + rgb[:, :, 2] * 0.114
        )

    @staticmethod
    def _iron_palette(gray: np.ndarray) -> np.ndarray:
        points = np.asarray((0.0, 0.25, 0.5, 0.75, 1.0))
        red = np.interp(gray, points, (0.0, 0.18, 0.75, 1.0, 1.0))
        green = np.interp(gray, points, (0.0, 0.0, 0.08, 0.55, 1.0))
        blue = np.interp(gray, points, (0.02, 0.25, 0.35, 0.05, 0.85))
        return np.rint(
            np.stack((red, green, blue), axis=2) * 255.0
        ).astype(np.uint8)
