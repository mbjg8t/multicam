from __future__ import annotations

import numpy as np

from multicam.core.cameras import Frame
from multicam.core.state import CameraLayer, ViewState


class Compositor:
    def compose(
        self,
        frames: dict[str, Frame],
        view_state: ViewState,
    ) -> np.ndarray | None:
        layers = sorted(
            view_state.layers,
            key=lambda layer: layer.z_order,
        )

        # The first available layer establishes the output canvas even if
        # that layer is disabled. This keeps the output geometry stable when
        # Layer 1 is temporarily hidden.
        canvas_frame = next(
            (
                frames.get(layer.camera_id)
                for layer in layers
                if frames.get(layer.camera_id) is not None
            ),
            None,
        )

        if canvas_frame is None:
            return None

        canvas_image = self._to_display_rgb(canvas_frame.image)
        output = np.zeros_like(canvas_image)

        for layer in layers:
            if not layer.enabled:
                continue

            frame = frames.get(layer.camera_id)

            if frame is None:
                continue

            image = self._to_display_rgb(frame.image)

            output = self._apply_layer(
                output,
                image,
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

    def _apply_layer(
        self,
        base: np.ndarray,
        image: np.ndarray,
        layer: CameraLayer,
    ) -> np.ndarray:
        image = self._resize_nearest(
            image,
            base.shape[1],
            base.shape[0],
        )

        x_offset = int(round(layer.transform.x))
        y_offset = int(round(layer.transform.y))

        if x_offset != 0 or y_offset != 0:
            image = self._translate(
                image,
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
            image.astype(np.float32)
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
