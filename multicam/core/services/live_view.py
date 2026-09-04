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

        if not view_state.layers:
            return None

        frames = {}

        # Retrieve all layer frames, including disabled layers. The compositor
        # may use the first available layer to preserve output canvas geometry
        # while that layer is hidden.
        for layer in view_state.layers:
            frame = self.broker.get_latest(
                layer.camera_id
            )

            if frame is not None:
                frames[layer.camera_id] = frame

        return self.compositor.compose(
            frames,
            view_state,
        )
