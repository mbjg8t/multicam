from __future__ import annotations

from multicam.core.cameras import CameraManager, FrameBroker
from multicam.core.imaging import Compositor
from multicam.core.state import AlignmentStateStore, ViewStateStore


class LiveViewService:
    def __init__(
        self,
        manager: CameraManager,
        broker: FrameBroker,
        state: ViewStateStore,
        alignment_state: AlignmentStateStore | None = None,
        orientation_store=None,
        dsp_service=None,
    ):
        self.manager = manager
        self.broker = broker
        self.state = state
        self.alignment_state = alignment_state
        self.orientation_store = orientation_store
        self.dsp_service = dsp_service
        self.compositor = Compositor()

    def get_composite(self):
        view_state = self.state.get()

        if not view_state.layers:
            return None

        alignment = (
            self.alignment_state.get()
            if self.alignment_state is not None
            else None
        )
        frames = {}

        # Retrieve all layer frames, including disabled layers. The compositor
        # may use the first available layer to preserve output canvas geometry
        # while that layer is hidden.
        for layer in view_state.layers:
            frame = (
                self.dsp_service.get_frame(layer.camera_id)
                if self.dsp_service is not None
                else self.broker.get_latest(layer.camera_id)
            )

            if frame is not None:
                frames[layer.camera_id] = frame

        if (
            alignment is not None
            and alignment.reference_camera_id
            and alignment.reference_camera_id not in frames
        ):
            reference_frame = self.broker.get_latest(
                alignment.reference_camera_id
            )

            if reference_frame is not None:
                frames[alignment.reference_camera_id] = reference_frame

        registrations = (
            self.alignment_state.effective_transforms()
            if self.alignment_state is not None
            else None
        )
        orientations = (
            self.orientation_store.snapshot()
            if self.orientation_store is not None
            else None
        )

        return self.compositor.compose(
            frames,
            view_state,
            registrations=registrations,
            orientations=orientations,
            reference_camera_id=(
                alignment.reference_camera_id
                if alignment is not None
                else None
            ),
        )
