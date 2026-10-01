"""Opt-in smoke test for a physically connected Picamera2 camera."""
import os

import pytest

from multicam.core.cameras import CameraManager

pytestmark = pytest.mark.skipif(
    os.environ.get("MULTICAM_REAL_CAMERA_TESTS") != "1",
    reason="Set MULTICAM_REAL_CAMERA_TESTS=1 to run real-camera smoke tests",
)


def test_picamera2_real_camera_smoke():
    from multicam.backends.picamera2 import Picamera2Backend
    manager = CameraManager()
    manager.register_backend(Picamera2Backend())
    cameras = manager.discover()
    if not cameras:
        pytest.skip("No Picamera2 cameras discovered")

    camera = manager.open(cameras[0].id)
    try:
        camera.start()
        frames = [camera.get_frame(timeout=1.0) for _ in range(10)]
        assert any(frame is not None for frame in frames)
    finally:
        manager.close_all()
