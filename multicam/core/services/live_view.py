from __future__ import annotations

from multicam.core.cameras import CameraManager, FrameBroker
from multicam.core.imaging import Compositor
from multicam.core.state import ViewStateStore


class LiveViewService:
    def __init__(
        self,
        manager: CameraManager,
        broker: FrameBroker,
        state: ViewStateStore,
    ):
        self.manager = manager
        self.broker = broker
        self.state = state
        self.compositor = Compositor()

    def get_composite(self):
        view_state = self.state.get()

        if view_state.base_camera_id is None:
            return None

        frames = {}

        base = self.broker.get_latest(
            view_state.base_camera_id
        )

        if base is not None:
            frames[view_state.base_camera_id] = base

        for layer in view_state.overlays:
            frame = self.broker.get_latest(
                layer.camera_id
            )

            if frame is not None:
                frames[layer.camera_id] = frame

        return self.compositor.compose(
            frames,
            view_state,
        )
