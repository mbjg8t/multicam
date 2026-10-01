"""Opt-in smoke test for a physically connected Aravis camera."""
import os

import pytest

from multicam.core.cameras import CameraManager

pytestmark = pytest.mark.skipif(
    os.environ.get("MULTICAM_REAL_CAMERA_TESTS") != "1",
    reason="Set MULTICAM_REAL_CAMERA_TESTS=1 to run real-camera smoke tests",
)


def test_aravis_real_camera_smoke():
    from multicam.backends.aravis import AravisBackend
    manager = CameraManager()
    manager.register_backend(AravisBackend())
    cameras = manager.discover()
    if not cameras:
        pytest.skip("No Aravis cameras discovered")

    camera = manager.open(cameras[0].id)
    try:
        camera.start()
        frames = [camera.get_frame(timeout=1.0) for _ in range(10)]
        assert any(frame is not None for frame in frames)
    finally:
        manager.close_all()
