from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CameraOrientation:
    """Presentation orientation applied before registration and display."""

    rotation_deg: int = 0
    flip_horizontal: bool = False
    flip_vertical: bool = False

    def __post_init__(self):
        if self.rotation_deg not in (0, 90, 180, 270):
            raise ValueError(
                "rotation_deg must be 0, 90, 180, or 270"
            )

    def as_dict(self) -> dict[str, int | bool]:
        return {
            "rotation_deg": self.rotation_deg,
            "flip_horizontal": self.flip_horizontal,
            "flip_vertical": self.flip_vertical,
        }
