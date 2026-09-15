from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any
import copy

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
