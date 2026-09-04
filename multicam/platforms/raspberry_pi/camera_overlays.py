from __future__ import annotations

# Raspberry Pi camera sensor overlays known to Multicam.
#
# This list is intentionally platform-specific. Generic Multicam core
# must not know Raspberry Pi dtoverlay names.
#
# Keep this conservative: add camera overlays as we actually support or
# verify them rather than guessing arbitrary dtoverlay names.

CAMERA_OVERLAYS: set[str] = {
    "ov5647",
    "ov64a40",
}


def is_camera_overlay(name: str) -> bool:
    return name.lower() in CAMERA_OVERLAYS
