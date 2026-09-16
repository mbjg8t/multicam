from __future__ import annotations

from dataclasses import dataclass, field, replace
from threading import RLock
import math
import time


Matrix3x3 = tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]


@dataclass(frozen=True, slots=True)
class RegistrationTransform:
    """Map pixels from one camera into a reference camera's pixel space."""

    matrix: Matrix3x3
    model: str = "translation"
    source_size: tuple[int, int] | None = None
    reference_size: tuple[int, int] | None = None
    source_points: tuple[tuple[float, float], ...] = ()
    reference_points: tuple[tuple[float, float], ...] = ()
    created_at: float = field(default_factory=time.time)

    @property
    def x(self) -> float:
        return float(self.matrix[0][2])

    @property
    def y(self) -> float:
        return float(self.matrix[1][2])

    @property
    def rotation_deg(self) -> float:
        return math.degrees(math.atan2(self.matrix[1][0], self.matrix[0][0]))

    @property
    def scale_x(self) -> float:
        return math.hypot(self.matrix[0][0], self.matrix[1][0])

    @property
    def scale_y(self) -> float:
        return math.hypot(self.matrix[0][1], self.matrix[1][1])

    @classmethod
    def from_point_pair(
        cls,
        *,
        source_point: tuple[float, float],
        reference_point: tuple[float, float],
        source_size: tuple[int, int],
        reference_size: tuple[int, int],
    ) -> RegistrationTransform:
        source_width, source_height = source_size
        reference_width, reference_height = reference_size

        if min(
            source_width,
            source_height,
            reference_width,
            reference_height,
        ) <= 0:
            raise ValueError("Frame dimensions must be positive")

        scale_x = reference_width / source_width
        scale_y = reference_height / source_height

        source_x = source_point[0] * scale_x
        source_y = source_point[1] * scale_y

        offset_x = reference_point[0] - source_x
        offset_y = reference_point[1] - source_y

        return cls(
            matrix=(
                (scale_x, 0.0, offset_x),
                (0.0, scale_y, offset_y),
                (0.0, 0.0, 1.0),
            ),
            source_size=source_size,
            reference_size=reference_size,
            source_points=(source_point,),
            reference_points=(reference_point,),
        )

    @classmethod
    def identity_for_sizes(
        cls,
        *,
        source_size: tuple[int, int],
        reference_size: tuple[int, int],
    ) -> RegistrationTransform:
        source_width, source_height = source_size
        reference_width, reference_height = reference_size

        if min(
            source_width,
            source_height,
            reference_width,
            reference_height,
        ) <= 0:
            raise ValueError("Frame dimensions must be positive")

        return cls(
            matrix=(
                (reference_width / source_width, 0.0, 0.0),
                (0.0, reference_height / source_height, 0.0),
                (0.0, 0.0, 1.0),
            ),
            source_size=source_size,
            reference_size=reference_size,
        )

    def translated(
        self,
        x_delta: float,
        y_delta: float,
    ) -> RegistrationTransform:
        row_0, row_1, row_2 = self.matrix

        return replace(
            self,
            matrix=(
                tuple(
                    row_0[index] + x_delta * row_2[index]
                    for index in range(3)
                ),
                tuple(
                    row_1[index] + y_delta * row_2[index]
                    for index in range(3)
                ),
                row_2,
            ),
            created_at=time.time(),
        )


@dataclass(slots=True)
class AlignmentState:
    reference_camera_id: str | None = None
    target_camera_id: str | None = None
    transforms: dict[str, RegistrationTransform] = field(
        default_factory=dict
    )
    drafts: dict[str, RegistrationTransform] = field(
        default_factory=dict
    )
    previous: dict[str, RegistrationTransform | None] = field(
        default_factory=dict
    )


class AlignmentStateStore:
    def __init__(self):
        self._state = AlignmentState()
        self._lock = RLock()

    def get(self) -> AlignmentState:
        with self._lock:
            return AlignmentState(
                reference_camera_id=self._state.reference_camera_id,
                target_camera_id=self._state.target_camera_id,
                transforms=dict(self._state.transforms),
                drafts=dict(self._state.drafts),
                previous=dict(self._state.previous),
            )

    def select(
        self,
        reference_camera_id: str,
        target_camera_id: str,
    ) -> None:
        if reference_camera_id == target_camera_id:
            raise ValueError("Reference and target cameras must differ")

        with self._lock:
            if (
                self._state.reference_camera_id
                and self._state.reference_camera_id
                != reference_camera_id
                and (
                    self._state.transforms
                    or self._state.drafts
                )
            ):
                raise ValueError(
                    "Clear existing alignments before changing reference camera"
                )

            self._state.reference_camera_id = reference_camera_id
            self._state.target_camera_id = target_camera_id

    def set_draft(
        self,
        camera_id: str,
        transform: RegistrationTransform,
    ) -> None:
        with self._lock:
            self._state.drafts[camera_id] = transform

    def accept(self, camera_id: str) -> bool:
        with self._lock:
            draft = self._state.drafts.pop(camera_id, None)

            if draft is None:
                return False

            self._state.previous[camera_id] = (
                self._state.transforms.get(camera_id)
            )
            self._state.transforms[camera_id] = draft
            return True

    def reject(self, camera_id: str) -> bool:
        with self._lock:
            return self._state.drafts.pop(camera_id, None) is not None

    def undo(self, camera_id: str) -> bool:
        with self._lock:
            if camera_id not in self._state.previous:
                return False

            prior = self._state.previous.pop(camera_id)

            if prior is None:
                self._state.transforms.pop(camera_id, None)
            else:
                self._state.transforms[camera_id] = prior

            self._state.drafts.pop(camera_id, None)
            return True

    def effective_transforms(self) -> dict[str, RegistrationTransform]:
        with self._lock:
            result = dict(self._state.transforms)
            result.update(self._state.drafts)
            return result

    def reset(self) -> bool:
        with self._lock:
            changed = bool(
                self._state.transforms
                or self._state.drafts
                or self._state.previous
            )
            self._state.transforms.clear()
            self._state.drafts.clear()
            self._state.previous.clear()
            return changed
