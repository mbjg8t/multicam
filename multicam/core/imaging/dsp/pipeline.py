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

        output = cls._levels_and_gamma(source, config)
        output = cls._denoise(output, config)
        output = cls._sharpen(output, config)
        if config.edge_mode != "off":
            gray_u8 = cls._luminance_u8(output)
            edges = cls._edges(gray_u8, config.edge_mode)
            edge_rgb = np.repeat(edges[:, :, None], 3, axis=2)
            strength = float(config.edge_strength)
            if strength >= 1.0:
                output = edge_rgb
            elif strength > 0.0:
                output = np.rint(
                    output.astype(np.float32) * (1.0 - strength)
                    + edge_rgb.astype(np.float32) * strength
                ).clip(0, 255).astype(np.uint8)

        if config.palette == "iron":
            gray_u8 = cls._luminance_u8(output)
            output = cls._iron_palette(gray_u8.astype(np.float32) / 255.0)
        elif config.palette == "grayscale":
            gray_u8 = cls._luminance_u8(output)
            output = np.repeat(gray_u8[:, :, None], 3, axis=2)

        if config.invert:
            output = 255 - output

        return np.ascontiguousarray(output, dtype=np.uint8)

    @classmethod
    def _levels_and_gamma(
        cls,
        image: np.ndarray,
        config: DspConfig,
    ) -> np.ndarray:
        if (
            image.dtype == np.uint8
            and config.levels_mode == "off"
            and config.gamma_mode == "off"
        ):
            if image.ndim == 2:
                return np.repeat(image[:, :, None], 3, axis=2)
            return image

        if not np.issubdtype(image.dtype, np.integer):
            finite = np.nan_to_num(image.astype(np.float32), copy=False)
            maximum = float(np.max(finite))
            if maximum <= 1.0:
                finite *= 255.0
            image = np.rint(finite).clip(0, 255).astype(np.uint8)

        type_max = int(np.iinfo(image.dtype).max)
        sample_step = max(
            1,
            math.ceil(math.sqrt(image.shape[0] * image.shape[1] / 262_144)),
        )
        sample = image[::sample_step, ::sample_step]
        sample_luma = cls._source_luminance(sample)

        if config.levels_mode == "percentile":
            black = float(np.percentile(sample_luma, config.black_percentile))
            white = float(np.percentile(sample_luma, config.white_percentile))
        elif config.levels_mode == "minmax" or image.dtype == np.uint16:
            black = float(np.min(sample_luma))
            white = float(np.max(sample_luma))
        else:
            black = 0.0
            white = float(type_max)

        gamma = config.gamma if config.gamma_mode == "gamma" else 1.0
        values = np.arange(type_max + 1, dtype=np.float32)

        if white <= black + 1e-9:
            normalized = values / max(float(type_max), 1.0)
        else:
            normalized = np.clip((values - black) / (white - black), 0.0, 1.0)

        if gamma != 1.0:
            normalized = np.power(normalized, 1.0 / float(gamma))

        lookup = np.rint(normalized * 255.0).astype(np.uint8)
        mapped = lookup[image]

        if mapped.ndim == 2:
            mapped = np.repeat(mapped[:, :, None], 3, axis=2)

        return mapped

    @staticmethod
    def _source_luminance(image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            return image
        values = image.astype(np.float32)
        return (
            values[:, :, 0] * 0.299
            + values[:, :, 1] * 0.587
            + values[:, :, 2] * 0.114
        )

    @staticmethod
    def _denoise(output: np.ndarray, config: DspConfig) -> np.ndarray:
        if config.denoise_mode == "off" or config.denoise_radius == 0:
            return output

        image = Image.fromarray(output)
        if config.denoise_mode == "box":
            filtered = image.filter(ImageFilter.BoxBlur(config.denoise_radius))
        elif config.denoise_mode == "gaussian":
            filtered = image.filter(ImageFilter.GaussianBlur(config.denoise_radius))
        else:
            filtered = image.filter(
                ImageFilter.MedianFilter(config.denoise_radius * 2 + 1)
            )
        return np.asarray(filtered)

    @staticmethod
    def _sharpen(output: np.ndarray, config: DspConfig) -> np.ndarray:
        if config.sharpen_mode == "off" or config.sharpen == 0:
            return output

        image = Image.fromarray(output)
        if config.sharpen_mode == "unsharp":
            filtered = image.filter(ImageFilter.UnsharpMask(
                radius=1.5,
                percent=int(round(config.sharpen * 100.0)),
                threshold=2,
            ))
            return np.asarray(filtered)

        image_filter = (
            ImageFilter.SHARPEN
            if config.sharpen_mode == "sharpen"
            else ImageFilter.EDGE_ENHANCE_MORE
        )
        filtered = np.asarray(image.filter(image_filter)).astype(np.float32)
        alpha = min(float(config.sharpen), 1.0)
        return np.rint(
            output.astype(np.float32) * (1.0 - alpha) + filtered * alpha
        ).clip(0, 255).astype(np.uint8)

    @staticmethod
    def _luminance_u8(rgb: np.ndarray) -> np.ndarray:
        return np.asarray(Image.fromarray(rgb).convert("L"))

    @staticmethod
    def _edges(gray: np.ndarray, mode: str) -> np.ndarray:
        image = Image.fromarray(gray)
        if mode == "laplacian":
            filtered = image.filter(
                ImageFilter.Kernel(
                    (3, 3),
                    (-1, -1, -1, -1, 8, -1, -1, -1, -1),
                    scale=1,
                )
            )
        else:
            # Pillow's compiled 3x3 edge detector avoids several full-frame
            # NumPy gradient temporaries. It serves the same display purpose
            # as the earlier Sobel magnitude at a fraction of the Pi cost.
            filtered = image.filter(ImageFilter.FIND_EDGES)

        return np.asarray(filtered)

    @staticmethod
    def _iron_palette(gray: np.ndarray) -> np.ndarray:
        points = np.asarray((0.0, 0.25, 0.5, 0.75, 1.0))
        red = np.interp(gray, points, (0.0, 0.18, 0.75, 1.0, 1.0))
        green = np.interp(gray, points, (0.0, 0.0, 0.08, 0.55, 1.0))
        blue = np.interp(gray, points, (0.02, 0.25, 0.35, 0.05, 0.85))
        return np.rint(
            np.stack((red, green, blue), axis=2) * 255.0
        ).astype(np.uint8)
