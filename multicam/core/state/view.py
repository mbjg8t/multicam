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
class CameraLayer:
    camera_id: str
    enabled: bool = True
    opacity: float = 1.0
    transform: Transform = field(default_factory=Transform)
    display_mode: str = "normal"
    z_order: int = 0


@dataclass(slots=True)
class ViewState:
    layers: list[CameraLayer] = field(default_factory=list)


class ViewStateStore:
    def __init__(self):
        self._state = ViewState()
        self._lock = RLock()

    def get(self) -> ViewState:
        with self._lock:
            return ViewState(
                layers=[
                    self._copy_layer(layer)
                    for layer in self._state.layers
                ],
            )

    def add_layer(self, layer: CameraLayer) -> None:
        with self._lock:
            if any(
                item.camera_id == layer.camera_id
                for item in self._state.layers
            ):
                raise ValueError(
                    f"Camera is already a layer: {layer.camera_id}"
                )

            layer.opacity = self._clamp_opacity(layer.opacity)
            self._state.layers.append(self._copy_layer(layer))
            self._sort_layers()

    def remove_layer(self, camera_id: str) -> None:
        with self._lock:
            self._state.layers = [
                layer
                for layer in self._state.layers
                if layer.camera_id != camera_id
            ]

    def update_layer(
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
            for layer in self._state.layers:
                if layer.camera_id != camera_id:
                    continue

                if enabled is not None:
                    layer.enabled = bool(enabled)

                if opacity is not None:
                    layer.opacity = self._clamp_opacity(opacity)

                if transform is not None:
                    layer.transform = Transform(
                        x=transform.x,
                        y=transform.y,
                        scale_x=transform.scale_x,
                        scale_y=transform.scale_y,
                        rotation_deg=transform.rotation_deg,
                    )

                if display_mode is not None:
                    layer.display_mode = display_mode

                if z_order is not None:
                    layer.z_order = int(z_order)

                self._sort_layers()
                return

            raise KeyError(camera_id)

    def _sort_layers(self) -> None:
        self._state.layers.sort(
            key=lambda item: item.z_order
        )

    @staticmethod
    def _clamp_opacity(opacity: float) -> float:
        return max(0.0, min(1.0, float(opacity)))

    @staticmethod
    def _copy_layer(layer: CameraLayer) -> CameraLayer:
        return CameraLayer(
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
