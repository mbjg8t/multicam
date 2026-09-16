from __future__ import annotations

import numpy as np
from PIL import Image

from multicam.core.cameras import Frame
from multicam.core.state import (
    CameraLayer,
    CameraOrientation,
    RegistrationTransform,
    ViewState,
)


class Compositor:
    def compose(
        self,
        frames: dict[str, Frame],
        view_state: ViewState,
        registrations: dict[str, RegistrationTransform] | None = None,
        orientations: dict[str, CameraOrientation] | None = None,
        reference_camera_id: str | None = None,
    ) -> np.ndarray | None:
        layers = sorted(
            view_state.layers,
            key=lambda layer: layer.z_order,
        )

        # The first available layer establishes the output canvas even if
        # that layer is disabled. This keeps the output geometry stable when
        # Layer 1 is temporarily hidden.
        canvas_frame = frames.get(reference_camera_id or "")

        if canvas_frame is None:
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

        orientations = orientations or {}
        canvas_image = self.orient_display_image(
            canvas_frame.image,
            orientations.get(canvas_frame.camera_id),
        )
        output = np.zeros_like(canvas_image)
        registrations = registrations or {}

        for layer in layers:
            if not layer.enabled:
                continue

            frame = frames.get(layer.camera_id)

            if frame is None:
                continue

            image = self.orient_display_image(
                frame.image,
                orientations.get(layer.camera_id),
            )

            output = self._apply_layer(
                output,
                image,
                layer,
                registrations.get(layer.camera_id),
            )

        return output

    def to_display_rgb(self, image: np.ndarray) -> np.ndarray:
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

    def orient_display_image(
        self,
        image: np.ndarray,
        orientation: CameraOrientation | None,
    ) -> np.ndarray:
        output = self.to_display_rgb(image)

        if orientation is None:
            return output

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

    def _apply_layer(
        self,
        base: np.ndarray,
        image: np.ndarray,
        layer: CameraLayer,
        registration: RegistrationTransform | None = None,
    ) -> np.ndarray:
        if registration is not None:
            source_changed = (
                registration.source_size is not None
                and registration.source_size
                != (image.shape[1], image.shape[0])
            )
            reference_changed = (
                registration.reference_size is not None
                and registration.reference_size
                != (base.shape[1], base.shape[0])
            )

            if source_changed or reference_changed:
                registration = None

        if registration is not None:
            image, mask = self._warp_registration(
                image,
                registration,
                base.shape[1],
                base.shape[0],
            )
        else:
            image = self._resize_nearest(
                image,
                base.shape[1],
                base.shape[0],
            )
            mask = np.full(base.shape[:2], 255, dtype=np.uint8)

        x_offset = int(round(layer.transform.x))
        y_offset = int(round(layer.transform.y))

        if x_offset != 0 or y_offset != 0:
            image = self._translate(
                image,
                x_offset,
                y_offset,
            )
            mask = self._translate(mask, x_offset, y_offset)

        opacity = max(
            0.0,
            min(1.0, layer.opacity),
        )

        alpha = opacity * (mask.astype(np.float32) / 255.0)
        blended = (
            base.astype(np.float32) * (1.0 - alpha[:, :, None])
            + image.astype(np.float32) * alpha[:, :, None]
        )

        return blended.clip(
            0,
            255,
        ).astype(np.uint8)

    def _warp_registration(
        self,
        image: np.ndarray,
        registration: RegistrationTransform,
        width: int,
        height: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        matrix = np.asarray(registration.matrix, dtype=np.float64)

        try:
            inverse = np.linalg.inv(matrix)
        except np.linalg.LinAlgError as exc:
            raise ValueError("Registration transform is singular") from exc

        if abs(float(inverse[2, 2])) <= 1e-12:
            raise ValueError("Registration transform has invalid perspective")

        inverse /= inverse[2, 2]
        coefficients = (
            float(inverse[0, 0]),
            float(inverse[0, 1]),
            float(inverse[0, 2]),
            float(inverse[1, 0]),
            float(inverse[1, 1]),
            float(inverse[1, 2]),
            float(inverse[2, 0]),
            float(inverse[2, 1]),
        )
        output_size = (width, height)
        warped = Image.fromarray(image).transform(
            output_size,
            Image.Transform.PERSPECTIVE,
            coefficients,
            resample=Image.Resampling.BILINEAR,
            fillcolor=(0, 0, 0),
        )
        source_mask = Image.fromarray(
            np.full(image.shape[:2], 255, dtype=np.uint8)
        )
        warped_mask = source_mask.transform(
            output_size,
            Image.Transform.PERSPECTIVE,
            coefficients,
            resample=Image.Resampling.NEAREST,
            fillcolor=0,
        )
        return np.asarray(warped), np.asarray(warped_mask)

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
