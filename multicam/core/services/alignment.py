from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from threading import RLock
from typing import Any
import copy
import math

import numpy as np

from multicam.core.cameras import Frame, FrameBroker
from multicam.core.state import AlignmentStateStore, RegistrationTransform


@dataclass(frozen=True, slots=True)
class FrozenFrameInfo:
    camera_id: str
    timestamp_ns: int
    monotonic_timestamp_ns: int
    width: int
    height: int
    pixel_format: str | None
    frame_number: int | None


@dataclass(frozen=True, slots=True)
class AutoAlignmentResult:
    reference_point: tuple[float, float]
    target_point: tuple[float, float]
    score: float
    uniqueness: float
    confidence: str
    patch_size: int
    transform: RegistrationTransform


class AlignmentService:
    """Coordinate frozen, operator-guided camera registration sessions."""

    def __init__(
        self,
        broker: FrameBroker,
        state: AlignmentStateStore,
        orientation_store=None,
    ):
        self.broker = broker
        self.state = state
        self.orientation_store = orientation_store
        self._frozen_frames: dict[str, Frame] = {}
        self._lock = RLock()

    def freeze(self, camera_ids: list[str]) -> list[FrozenFrameInfo]:
        if len(set(camera_ids)) != len(camera_ids):
            raise ValueError("Camera list contains duplicates")

        frozen: dict[str, Frame] = {}

        for camera_id in camera_ids:
            frame = self.broker.get_latest(camera_id)

            if frame is None:
                raise ValueError(f"No frame available for {camera_id}")

            frozen[camera_id] = self._copy_frame(frame)

        with self._lock:
            self._frozen_frames = frozen

        return [self._frame_info(frame) for frame in frozen.values()]

    def get_frozen(self, camera_id: str) -> Frame | None:
        with self._lock:
            return self._frozen_frames.get(camera_id)

    def frozen_info(self) -> list[FrozenFrameInfo]:
        with self._lock:
            return [
                self._frame_info(frame)
                for frame in self._frozen_frames.values()
            ]

    def clear_frozen(self) -> None:
        with self._lock:
            self._frozen_frames = {}

    def set_point_pair(
        self,
        *,
        reference_point: tuple[float, float],
        target_point: tuple[float, float],
    ) -> RegistrationTransform:
        current = self.state.get()
        reference_id = current.reference_camera_id
        target_id = current.target_camera_id

        if reference_id is None or target_id is None:
            raise ValueError("Select reference and target cameras first")

        with self._lock:
            reference = self._frozen_frames.get(reference_id)
            target = self._frozen_frames.get(target_id)

        if reference is None or target is None:
            raise ValueError("Freeze reference and target frames first")

        reference_size = self._frame_size(reference, reference_id)
        target_size = self._frame_size(target, target_id)

        self._validate_point(reference_point, reference_size, "reference")
        self._validate_point(target_point, target_size, "target")

        transform = RegistrationTransform.from_point_pair(
            source_point=target_point,
            reference_point=reference_point,
            source_size=target_size,
            reference_size=reference_size,
        )
        self.state.set_draft(target_id, transform)
        return transform

    def set_point_pairs(
        self,
        *,
        reference_points: list[tuple[float, float]],
        target_points: list[tuple[float, float]],
        requested_model: str = "auto",
    ) -> RegistrationTransform:
        if len(reference_points) != len(target_points):
            raise ValueError("Reference and target point counts must match")
        if not 1 <= len(reference_points) <= 12:
            raise ValueError("Provide between one and twelve point pairs")
        if requested_model not in {
            "auto",
            "translation",
            "similarity",
            "affine",
            "homography",
        }:
            raise ValueError("Unknown alignment model")

        current = self.state.get()
        reference_id = current.reference_camera_id
        target_id = current.target_camera_id

        if reference_id is None or target_id is None:
            raise ValueError("Select reference and target cameras first")

        with self._lock:
            reference = self._frozen_frames.get(reference_id)
            target = self._frozen_frames.get(target_id)

        if reference is None or target is None:
            raise ValueError("Freeze reference and target frames first")

        reference_size = self._frame_size(reference, reference_id)
        target_size = self._frame_size(target, target_id)

        for point in reference_points:
            self._validate_point(point, reference_size, "reference")
        for point in target_points:
            self._validate_point(point, target_size, "target")

        point_count = len(reference_points)

        if point_count == 1 or requested_model == "translation":
            return self.set_point_pair(
                reference_point=reference_points[0],
                target_point=target_points[0],
            )

        progressive_model = requested_model

        if requested_model == "auto":
            progressive_model = (
                "similarity"
                if point_count == 2
                else "affine"
                if point_count == 3
                else "auto"
            )
        elif requested_model == "homography" and point_count < 4:
            progressive_model = "similarity" if point_count == 2 else "affine"
        elif requested_model == "affine" and point_count < 3:
            progressive_model = "similarity"

        threshold = self._residual_threshold(reference_size)

        if progressive_model == "auto":
            fit = self._select_model(
                target_points,
                reference_points,
                threshold,
            )
        else:
            fit = self._robust_fit(
                progressive_model,
                target_points,
                reference_points,
                threshold,
            )

        matrix, model, residuals, inliers = fit
        inlier_residuals = [
            residual
            for residual, inlier in zip(residuals, inliers)
            if inlier
        ]
        rms_error = math.sqrt(
            sum(value * value for value in inlier_residuals)
            / len(inlier_residuals)
        )

        transform = RegistrationTransform(
            matrix=matrix,
            model=model,
            source_size=target_size,
            reference_size=reference_size,
            source_points=tuple(target_points),
            reference_points=tuple(reference_points),
            residuals_px=tuple(residuals),
            inlier_mask=tuple(inliers),
            rms_error_px=rms_error,
            max_error_px=max(inlier_residuals),
        )
        self.state.set_draft(target_id, transform)
        return transform

    def auto_align(
        self,
        *,
        reference_point: tuple[float, float],
        max_dimension: int = 512,
        patch_size: int = 51,
    ) -> AutoAlignmentResult:
        """Find a structural match in the selected target and create a draft."""
        current = self.state.get()
        reference_id = current.reference_camera_id
        target_id = current.target_camera_id

        if reference_id is None or target_id is None:
            raise ValueError("Select reference and target cameras first")

        with self._lock:
            reference = self._frozen_frames.get(reference_id)
            target = self._frozen_frames.get(target_id)

        if reference is None or target is None:
            raise ValueError("Freeze reference and target frames first")

        reference_image = self._oriented_gray(reference.image, reference_id)
        target_image = self._oriented_gray(target.image, target_id)
        reference_size = (reference_image.shape[1], reference_image.shape[0])
        target_size = (target_image.shape[1], target_image.shape[0])
        self._validate_point(reference_point, reference_size, "reference")

        work_width, work_height = self._working_size(
            reference_size,
            max_dimension,
        )
        reference_work = self._resize_gray(
            reference_image,
            work_width,
            work_height,
        )
        target_work = self._resize_gray(
            target_image,
            work_width,
            work_height,
        )
        reference_edges = self._edge_map(reference_work)
        target_edges = self._edge_map(target_work)

        work_point = (
            reference_point[0] * work_width / reference_size[0],
            reference_point[1] * work_height / reference_size[1],
        )
        effective_patch = self._effective_patch_size(
            patch_size,
            reference_edges.shape,
            work_point,
        )
        half = effective_patch // 2
        center_x = int(round(work_point[0]))
        center_y = int(round(work_point[1]))
        template = reference_edges[
            center_y - half:center_y + half + 1,
            center_x - half:center_x + half + 1,
        ]

        match_x, match_y, score, uniqueness = self._normalized_match(
            target_edges,
            template,
        )
        matched_work_point = (match_x + half, match_y + half)
        matched_reference_point = (
            matched_work_point[0] * reference_size[0] / work_width,
            matched_work_point[1] * reference_size[1] / work_height,
        )
        target_point = (
            matched_reference_point[0] * target_size[0] / reference_size[0],
            matched_reference_point[1] * target_size[1] / reference_size[1],
        )
        confidence = self._confidence_label(score, uniqueness)
        transform = self.set_point_pair(
            reference_point=reference_point,
            target_point=target_point,
        )

        return AutoAlignmentResult(
            reference_point=reference_point,
            target_point=target_point,
            score=score,
            uniqueness=uniqueness,
            confidence=confidence,
            patch_size=effective_patch,
            transform=transform,
        )

    def nudge(
        self,
        *,
        x_delta: float,
        y_delta: float,
    ) -> RegistrationTransform:
        current = self.state.get()
        reference_id = current.reference_camera_id
        target_id = current.target_camera_id

        if reference_id is None or target_id is None:
            raise ValueError("Select reference and target cameras first")

        with self._lock:
            reference = self._frozen_frames.get(reference_id)
            target = self._frozen_frames.get(target_id)

        if reference is None or target is None:
            raise ValueError("Freeze reference and target frames first")

        transform = (
            current.drafts.get(target_id)
            or current.transforms.get(target_id)
            or RegistrationTransform.identity_for_sizes(
                source_size=self._frame_size(target, target_id),
                reference_size=self._frame_size(reference, reference_id),
            )
        )
        transform = transform.translated(x_delta, y_delta)
        self.state.set_draft(target_id, transform)
        return transform

    @staticmethod
    def timestamp_skew_ns(frames: list[FrozenFrameInfo]) -> int:
        if len(frames) < 2:
            return 0

        timestamps = [frame.monotonic_timestamp_ns for frame in frames]
        return max(timestamps) - min(timestamps)

    @staticmethod
    def _copy_frame(frame: Frame) -> Frame:
        image: Any = frame.image

        if hasattr(image, "copy"):
            image = image.copy()
        else:
            image = copy.deepcopy(image)

        return Frame(
            camera_id=frame.camera_id,
            image=image,
            timestamp_ns=frame.timestamp_ns,
            monotonic_timestamp_ns=frame.monotonic_timestamp_ns,
            device_timestamp_ns=frame.device_timestamp_ns,
            width=frame.width,
            height=frame.height,
            pixel_format=frame.pixel_format,
            bit_depth=frame.bit_depth,
            frame_number=frame.frame_number,
            metadata=copy.deepcopy(frame.metadata),
        )

    def _frame_size(
        self,
        frame: Frame,
        camera_id: str,
    ) -> tuple[int, int]:
        height, width = frame.image.shape[:2]

        if self.orientation_store is not None:
            orientation = self.orientation_store.get(camera_id)

            if orientation.rotation_deg in (90, 270):
                width, height = height, width

        return int(width), int(height)

    def _oriented_gray(self, image: Any, camera_id: str) -> np.ndarray:
        array = np.asarray(image)

        if array.ndim == 3 and array.shape[2] >= 3:
            gray = (
                array[..., 0].astype(np.float32) * 0.299
                + array[..., 1].astype(np.float32) * 0.587
                + array[..., 2].astype(np.float32) * 0.114
            )
        elif array.ndim == 2:
            gray = array.astype(np.float32)
        else:
            raise ValueError(f"Unsupported image shape: {array.shape}")

        if self.orientation_store is None:
            return gray

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
    def _working_size(
        size: tuple[int, int],
        max_dimension: int,
    ) -> tuple[int, int]:
        width, height = size
        scale = min(1.0, max_dimension / max(width, height))
        return max(1, int(round(width * scale))), max(
            1,
            int(round(height * scale)),
        )

    @staticmethod
    def _resize_gray(
        image: np.ndarray,
        width: int,
        height: int,
    ) -> np.ndarray:
        source_height, source_width = image.shape
        x_indices = np.linspace(0, source_width - 1, width).astype(np.int32)
        y_indices = np.linspace(0, source_height - 1, height).astype(np.int32)
        return image[y_indices[:, None], x_indices[None, :]]

    @staticmethod
    def _edge_map(image: np.ndarray) -> np.ndarray:
        low = float(np.percentile(image, 2))
        high = float(np.percentile(image, 98))

        if high <= low:
            raise ValueError("Selected frame has insufficient contrast")

        normalized = np.clip((image - low) / (high - low), 0.0, 1.0)
        gradient_y, gradient_x = np.gradient(normalized)
        edges = np.hypot(gradient_x, gradient_y).astype(np.float32)
        structured = edges[edges > 1e-6]

        if structured.size == 0:
            raise ValueError("Selected frame has insufficient structure")

        edge_scale = float(np.percentile(structured, 90))
        return np.clip(edges / edge_scale, 0.0, 1.0)

    @staticmethod
    def _effective_patch_size(
        requested: int,
        image_shape: tuple[int, int],
        point: tuple[float, float],
    ) -> int:
        height, width = image_shape
        center_x = int(round(point[0]))
        center_y = int(round(point[1]))
        border = min(
            center_x,
            center_y,
            width - 1 - center_x,
            height - 1 - center_y,
        )
        maximum = 2 * border + 1
        size = min(int(requested), maximum, width, height)

        if size % 2 == 0:
            size -= 1
        if size < 15:
            raise ValueError(
                "Choose a reference feature farther from the image edge"
            )

        return size

    @classmethod
    def _normalized_match(
        cls,
        image: np.ndarray,
        template: np.ndarray,
    ) -> tuple[int, int, float, float]:
        template = template.astype(np.float32)
        template = template - float(template.mean())
        template_energy = float(np.sum(template * template))

        if template_energy <= 1e-6:
            raise ValueError(
                "The selected reference area has insufficient structure"
            )

        image_height, image_width = image.shape
        patch_height, patch_width = template.shape

        if patch_height > image_height or patch_width > image_width:
            raise ValueError("Reference patch is larger than target frame")

        fft_shape = (
            cls._next_power_of_two(image_height + patch_height - 1),
            cls._next_power_of_two(image_width + patch_width - 1),
        )
        correlation = np.fft.irfft2(
            np.fft.rfft2(image, fft_shape)
            * np.fft.rfft2(template[::-1, ::-1], fft_shape),
            fft_shape,
        )
        numerator = correlation[
            patch_height - 1:image_height,
            patch_width - 1:image_width,
        ]
        window_sum = cls._window_sums(image, patch_height, patch_width)
        window_squared_sum = cls._window_sums(
            image * image,
            patch_height,
            patch_width,
        )
        sample_count = float(patch_height * patch_width)
        window_energy = np.maximum(
            window_squared_sum - (window_sum * window_sum / sample_count),
            0.0,
        )
        denominator = np.sqrt(window_energy * template_energy)
        scores = np.full(numerator.shape, -1.0, dtype=np.float32)
        np.divide(
            numerator,
            denominator,
            out=scores,
            where=denominator > 1e-6,
        )
        flat_index = int(np.argmax(scores))
        match_y, match_x = np.unravel_index(flat_index, scores.shape)
        score = float(np.clip(scores[match_y, match_x], -1.0, 1.0))
        alternatives = scores.copy()
        exclusion_radius = max(3, min(patch_height, patch_width) // 3)
        alternatives[
            max(0, match_y - exclusion_radius):match_y + exclusion_radius + 1,
            max(0, match_x - exclusion_radius):match_x + exclusion_radius + 1,
        ] = -1.0
        second_score = float(np.max(alternatives))
        uniqueness = max(0.0, score - second_score)

        if score < 0.10:
            raise ValueError(
                "No reliable structural match was found; use manual matching"
            )

        return int(match_x), int(match_y), score, uniqueness

    @staticmethod
    def _window_sums(
        image: np.ndarray,
        height: int,
        width: int,
    ) -> np.ndarray:
        integral = np.pad(
            image.astype(np.float64),
            ((1, 0), (1, 0)),
        ).cumsum(axis=0).cumsum(axis=1)
        return (
            integral[height:, width:]
            - integral[:-height, width:]
            - integral[height:, :-width]
            + integral[:-height, :-width]
        )

    @staticmethod
    def _next_power_of_two(value: int) -> int:
        return 1 << max(0, value - 1).bit_length()

    @staticmethod
    def _confidence_label(score: float, uniqueness: float) -> str:
        if score >= 0.65 and uniqueness >= 0.08:
            return "high"
        if score >= 0.40 and uniqueness >= 0.04:
            return "medium"
        return "low"

    @staticmethod
    def _residual_threshold(reference_size: tuple[int, int]) -> float:
        width, height = reference_size
        return max(2.5, math.hypot(width, height) * 0.0015)

    @classmethod
    def _select_model(
        cls,
        source_points: list[tuple[float, float]],
        reference_points: list[tuple[float, float]],
        threshold: float,
    ) -> tuple[
        tuple[tuple[float, float, float], ...],
        str,
        list[float],
        list[bool],
    ]:
        candidates = []

        for model in ("similarity", "affine", "homography"):
            try:
                candidates.append(cls._robust_fit(
                    model,
                    source_points,
                    reference_points,
                    threshold,
                ))
            except ValueError:
                continue

        if not candidates:
            raise ValueError("Point layout cannot determine a valid transform")
        minimum_inliers = max(4, math.ceil(len(source_points) * 0.75))
        best_inlier_count = max(sum(candidate[3]) for candidate in candidates)

        for candidate in candidates:
            _, _, residuals, inliers = candidate
            inlier_residuals = [
                residual
                for residual, inlier in zip(residuals, inliers)
                if inlier
            ]
            rms = math.sqrt(
                sum(value * value for value in inlier_residuals)
                / len(inlier_residuals)
            )

            if (
                len(inlier_residuals) == best_inlier_count
                and len(inlier_residuals) >= minimum_inliers
                and rms <= threshold
            ):
                return candidate

        return max(
            candidates,
            key=lambda item: (
                sum(item[3]),
                -cls._inlier_rms(item[2], item[3]),
            ),
        )

    @classmethod
    def _robust_fit(
        cls,
        model: str,
        source_points: list[tuple[float, float]],
        reference_points: list[tuple[float, float]],
        threshold: float,
    ) -> tuple[
        tuple[tuple[float, float, float], ...],
        str,
        list[float],
        list[bool],
    ]:
        minimum = {
            "similarity": 2,
            "affine": 3,
            "homography": 4,
        }[model]

        if len(source_points) < minimum:
            raise ValueError(
                f"{model.title()} alignment requires at least {minimum} pairs"
            )

        solver = {
            "similarity": cls._solve_similarity,
            "affine": cls._solve_affine,
            "homography": cls._solve_homography,
        }[model]
        sample_sets = list(combinations(range(len(source_points)), minimum))

        if len(sample_sets) > 256:
            rng = np.random.default_rng(0)
            selected = rng.choice(len(sample_sets), size=256, replace=False)
            sample_sets = [sample_sets[index] for index in selected]

        best_inliers: list[bool] | None = None
        best_score: tuple[int, float] | None = None

        for indices in sample_sets:
            try:
                matrix = solver(
                    [source_points[index] for index in indices],
                    [reference_points[index] for index in indices],
                )
            except (ValueError, np.linalg.LinAlgError):
                continue

            residuals = cls._point_residuals(
                matrix,
                source_points,
                reference_points,
            )
            inliers = [value <= threshold for value in residuals]
            count = sum(inliers)

            if count < minimum:
                continue

            score = (count, -cls._inlier_rms(residuals, inliers))

            if best_score is None or score > best_score:
                best_score = score
                best_inliers = inliers

        if best_inliers is None:
            raise ValueError(
                f"Point layout cannot determine a valid {model} transform"
            )

        matrix = solver(
            [
                point
                for point, inlier in zip(source_points, best_inliers)
                if inlier
            ],
            [
                point
                for point, inlier in zip(reference_points, best_inliers)
                if inlier
            ],
        )
        residuals = cls._point_residuals(
            matrix,
            source_points,
            reference_points,
        )
        inliers = [value <= threshold for value in residuals]
        return matrix, model, residuals, inliers

    @staticmethod
    def _inlier_rms(residuals: list[float], inliers: list[bool]) -> float:
        values = [
            residual
            for residual, inlier in zip(residuals, inliers)
            if inlier
        ]

        if not values:
            return math.inf

        return math.sqrt(sum(value * value for value in values) / len(values))

    @staticmethod
    def _point_residuals(
        matrix: tuple[tuple[float, float, float], ...],
        source_points: list[tuple[float, float]],
        reference_points: list[tuple[float, float]],
    ) -> list[float]:
        transform = np.asarray(matrix, dtype=np.float64)
        source = np.column_stack((
            np.asarray(source_points, dtype=np.float64),
            np.ones(len(source_points), dtype=np.float64),
        ))
        projected = (transform @ source.T).T
        denominators = projected[:, 2]

        if np.any(np.abs(denominators) <= 1e-12):
            return [math.inf] * len(source_points)

        projected = projected[:, :2] / denominators[:, None]
        differences = projected - np.asarray(
            reference_points,
            dtype=np.float64,
        )
        return [float(value) for value in np.linalg.norm(differences, axis=1)]

    @classmethod
    def _solve_similarity(
        cls,
        source_points: list[tuple[float, float]],
        reference_points: list[tuple[float, float]],
    ) -> tuple[tuple[float, float, float], ...]:
        rows = []
        values = []

        for (x, y), (u, v) in zip(source_points, reference_points):
            rows.extend(((x, -y, 1.0, 0.0), (y, x, 0.0, 1.0)))
            values.extend((u, v))

        solution, _, rank, _ = np.linalg.lstsq(
            np.asarray(rows, dtype=np.float64),
            np.asarray(values, dtype=np.float64),
            rcond=None,
        )

        if rank < 4:
            raise ValueError(
                "Point layout cannot determine a similarity transform"
            )

        a, b, translation_x, translation_y = solution
        matrix = np.asarray((
            (a, -b, translation_x),
            (b, a, translation_y),
            (0.0, 0.0, 1.0),
        ))
        return cls._validated_matrix(matrix, "similarity")

    @classmethod
    def _solve_affine(
        cls,
        source_points: list[tuple[float, float]],
        reference_points: list[tuple[float, float]],
    ) -> tuple[tuple[float, float, float], ...]:
        rows = []
        values = []

        for (x, y), (u, v) in zip(source_points, reference_points):
            rows.extend((
                (x, y, 1.0, 0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0, x, y, 1.0),
            ))
            values.extend((u, v))

        design = np.asarray(rows, dtype=np.float64)
        solution, _, rank, _ = np.linalg.lstsq(
            design,
            np.asarray(values, dtype=np.float64),
            rcond=None,
        )

        if rank < 6:
            raise ValueError("Point layout cannot determine an affine transform")

        matrix = np.asarray((
            (solution[0], solution[1], solution[2]),
            (solution[3], solution[4], solution[5]),
            (0.0, 0.0, 1.0),
        ))
        return cls._validated_matrix(matrix, "affine")

    @classmethod
    def _solve_homography(
        cls,
        source_points: list[tuple[float, float]],
        reference_points: list[tuple[float, float]],
    ) -> tuple[tuple[float, float, float], ...]:
        source, source_normalization = cls._normalize_points(source_points)
        reference, reference_normalization = cls._normalize_points(
            reference_points
        )
        rows = []

        for (x, y), (u, v) in zip(source, reference):
            rows.extend((
                (-x, -y, -1.0, 0.0, 0.0, 0.0, u * x, u * y, u),
                (0.0, 0.0, 0.0, -x, -y, -1.0, v * x, v * y, v),
            ))

        design = np.asarray(rows, dtype=np.float64)
        _, singular_values, right_vectors = np.linalg.svd(design)

        if len(source_points) == 4:
            rank = int(np.sum(singular_values > singular_values[0] * 1e-12))
        else:
            rank = int(np.linalg.matrix_rank(design))

        if rank < 8:
            raise ValueError(
                "Point layout cannot determine a perspective transform"
            )

        normalized_matrix = right_vectors[-1].reshape(3, 3)
        matrix = (
            np.linalg.inv(reference_normalization)
            @ normalized_matrix
            @ source_normalization
        )

        if abs(float(matrix[2, 2])) > 1e-12:
            matrix /= matrix[2, 2]
        else:
            matrix /= np.linalg.norm(matrix)

        return cls._validated_matrix(matrix, "homography")

    @staticmethod
    def _normalize_points(
        points: list[tuple[float, float]],
    ) -> tuple[np.ndarray, np.ndarray]:
        values = np.asarray(points, dtype=np.float64)
        center = values.mean(axis=0)
        centered = values - center
        mean_distance = float(np.linalg.norm(centered, axis=1).mean())

        if mean_distance <= 1e-8:
            raise ValueError("Point layout is too tightly clustered")

        scale = math.sqrt(2.0) / mean_distance
        normalization = np.asarray((
            (scale, 0.0, -scale * center[0]),
            (0.0, scale, -scale * center[1]),
            (0.0, 0.0, 1.0),
        ))
        homogeneous = np.column_stack((
            values,
            np.ones(len(values), dtype=np.float64),
        ))
        normalized = (normalization @ homogeneous.T).T
        return normalized[:, :2], normalization

    @staticmethod
    def _validated_matrix(
        matrix: np.ndarray,
        label: str,
    ) -> tuple[tuple[float, float, float], ...]:
        determinant = abs(float(np.linalg.det(matrix)))

        if not np.isfinite(matrix).all() or determinant <= 1e-10:
            raise ValueError(f"Point layout produced an invalid {label} transform")

        return tuple(
            tuple(float(value) for value in row)
            for row in matrix
        )

    def _frame_info(self, frame: Frame) -> FrozenFrameInfo:
        width, height = self._frame_size(frame, frame.camera_id)
        return FrozenFrameInfo(
            camera_id=frame.camera_id,
            timestamp_ns=frame.timestamp_ns,
            monotonic_timestamp_ns=frame.monotonic_timestamp_ns,
            width=width,
            height=height,
            pixel_format=frame.pixel_format,
            frame_number=frame.frame_number,
        )

    @staticmethod
    def _validate_point(
        point: tuple[float, float],
        size: tuple[int, int],
        label: str,
    ) -> None:
        x, y = point
        width, height = size

        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f"{label.title()} point is outside the frame")
