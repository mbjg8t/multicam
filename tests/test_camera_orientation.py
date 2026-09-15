import numpy as np
import pytest

from multicam.core.imaging import Compositor
from multicam.core.services import CameraOrientationStore
from multicam.core.state import CameraOrientation


def test_camera_orientation_only_allows_right_angle_rotations():
    with pytest.raises(ValueError):
        CameraOrientation(rotation_deg=45)


def test_camera_orientation_store_round_trip(tmp_path):
    path = tmp_path / "orientations.json"
    store = CameraOrientationStore(path)
    orientation = CameraOrientation(
        rotation_deg=180,
        flip_horizontal=True,
    )

    store.set("camera:1", orientation)

    assert CameraOrientationStore(path).get("camera:1") == orientation


def test_compositor_orients_image_before_registration():
    image = np.array([
        [1, 2, 3],
        [4, 5, 6],
    ], dtype=np.uint8)

    result = Compositor().orient_display_image(
        image,
        CameraOrientation(rotation_deg=90),
    )

    assert result.shape == (3, 2, 3)
    assert result[:, :, 0].tolist() == [
        [4, 1],
        [5, 2],
        [6, 3],
    ]
