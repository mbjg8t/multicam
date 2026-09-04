from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock


@dataclass(slots=True)
class Transform:
    x: float = 0.0
    y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation_deg: float = 0.0


@dataclass(slots=True)
class OverlayLayer:
    camera_id: str
    enabled: bool = True
    opacity: float = 1.0
    transform: Transform = field(default_factory=Transform)
    display_mode: str = "normal"
    z_order: int = 0


@dataclass(slots=True)
class ViewState:
    base_camera_id: str | None = None
    base_opacity: float = 1.0
    overlays: list[OverlayLayer] = field(default_factory=list)


class ViewStateStore:
    def __init__(self):
        self._state = ViewState()
        self._lock = RLock()

    def get(self) -> ViewState:
        with self._lock:
            return ViewState(
                base_camera_id=self._state.base_camera_id,
                base_opacity=self._state.base_opacity,
                overlays=[
                    OverlayLayer(
                        camera_id=layer.camera_id,
                        enabled=layer.enabled,
                        opacity=layer.opacity,
                        transform=Transform(
                            x=layer.transform.x,
                            y=layer.transform.y,
                            scale_x=layer.transform.scale_x,
                            scale_y=layer.transform.scale_y,
                            rotation_deg=layer.transform.rotation_deg,
                        ),
                        display_mode=layer.display_mode,
                        z_order=layer.z_order,
                    )
                    for layer in self._state.overlays
                ],
            )

    def set_base(self, camera_id: str | None) -> None:
        with self._lock:
            self._state.base_camera_id = camera_id

    def set_base_opacity(self, opacity: float) -> None:
        with self._lock:
            self._state.base_opacity = max(0.0, min(1.0, opacity))

    def add_overlay(self, layer: OverlayLayer) -> None:
        with self._lock:
            self._state.overlays.append(layer)
            self._state.overlays.sort(key=lambda item: item.z_order)

    def remove_overlay(self, camera_id: str) -> None:
        with self._lock:
            self._state.overlays = [
                layer
                for layer in self._state.overlays
                if layer.camera_id != camera_id
            ]

    def update_overlay(
        self,
        camera_id: str,
        *,
        enabled: bool | None = None,
        opacity: float | None = None,
        transform: Transform | None = None,
        display_mode: str | None = None,
        z_order: int | None = None,
    ) -> None:
        with self._lock:
            for layer in self._state.overlays:
                if layer.camera_id != camera_id:
                    continue

                if enabled is not None:
                    layer.enabled = enabled

                if opacity is not None:
                    layer.opacity = max(0.0, min(1.0, opacity))

                if transform is not None:
                    layer.transform = transform

                if display_mode is not None:
                    layer.display_mode = display_mode

                if z_order is not None:
                    layer.z_order = z_order

                self._state.overlays.sort(
                    key=lambda item: item.z_order
                )

                return

            raise KeyError(camera_id)
