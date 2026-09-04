from __future__ import annotations

import numpy as np

from multicam.core.cameras import Frame
from multicam.core.state import OverlayLayer, ViewState


class Compositor:
    def compose(
        self,
        frames: dict[str, Frame],
        view_state: ViewState,
    ) -> np.ndarray | None:
        if not view_state.base_camera_id:
            return None

        base_frame = frames.get(view_state.base_camera_id)

        if base_frame is None:
            return None

        output = self._to_display_rgb(base_frame.image)

        base_opacity = max(
            0.0,
            min(1.0, view_state.base_opacity),
        )

        if base_opacity < 1.0:
            output = (
                output.astype(np.float32)
                * base_opacity
            ).clip(
                0,
                255,
            ).astype(np.uint8)

        overlays = sorted(
            (
                layer
                for layer in view_state.overlays
                if layer.enabled
            ),
            key=lambda layer: layer.z_order,
        )

        for layer in overlays:
            frame = frames.get(layer.camera_id)

            if frame is None:
                continue

            overlay = self._to_display_rgb(frame.image)

            output = self._apply_overlay(
                output,
                overlay,
                layer,
            )

        return output

    def _to_display_rgb(self, image: np.ndarray) -> np.ndarray:
        if image.dtype == np.uint16:
            minimum = int(image.min())
            maximum = int(image.max())

            if maximum <= minimum:
                gray = np.zeros(
                    image.shape,
                    dtype=np.uint8,
                )
            else:
                gray = (
                    (image.astype(np.float32) - minimum)
                    * (255.0 / (maximum - minimum))
                ).clip(0, 255).astype(np.uint8)

            return np.repeat(
                gray[:, :, None],
                3,
                axis=2,
            )

        if image.ndim == 2:
            gray = image.astype(np.uint8)

            return np.repeat(
                gray[:, :, None],
                3,
                axis=2,
            )

        if image.ndim == 3 and image.shape[2] == 3:
            return image.astype(
                np.uint8,
                copy=True,
            )

        raise ValueError(
            f"Unsupported image shape: {image.shape}"
        )

    def _apply_overlay(
        self,
        base: np.ndarray,
        overlay: np.ndarray,
        layer: OverlayLayer,
    ) -> np.ndarray:
        overlay = self._resize_nearest(
            overlay,
            base.shape[1],
            base.shape[0],
        )

        x_offset = int(round(layer.transform.x))
        y_offset = int(round(layer.transform.y))

        if x_offset != 0 or y_offset != 0:
            overlay = self._translate(
                overlay,
                x_offset,
                y_offset,
            )

        opacity = max(
            0.0,
            min(1.0, layer.opacity),
        )

        blended = (
            base.astype(np.float32)
            * (1.0 - opacity)
            +
            overlay.astype(np.float32)
            * opacity
        )

        return blended.clip(
            0,
            255,
        ).astype(np.uint8)

    def _resize_nearest(
        self,
        image: np.ndarray,
        width: int,
        height: int,
    ) -> np.ndarray:
        source_height, source_width = image.shape[:2]

        if (
            source_width == width
            and source_height == height
        ):
            return image

        x_indices = np.linspace(
            0,
            source_width - 1,
            width,
        ).astype(np.int32)

        y_indices = np.linspace(
            0,
            source_height - 1,
            height,
        ).astype(np.int32)

        return image[
            y_indices[:, None],
            x_indices[None, :],
        ]

    def _translate(
        self,
        image: np.ndarray,
        x: int,
        y: int,
    ) -> np.ndarray:
        result = np.zeros_like(image)

        height, width = image.shape[:2]

        src_x1 = max(0, -x)
        src_y1 = max(0, -y)
        src_x2 = min(width, width - x)
        src_y2 = min(height, height - y)

        dst_x1 = max(0, x)
        dst_y1 = max(0, y)

        copy_width = src_x2 - src_x1
        copy_height = src_y2 - src_y1

        if copy_width <= 0 or copy_height <= 0:
            return result

        dst_x2 = dst_x1 + copy_width
        dst_y2 = dst_y1 + copy_height

        result[
            dst_y1:dst_y2,
            dst_x1:dst_x2,
        ] = image[
            src_y1:src_y2,
            src_x1:src_x2,
        ]

        return result
