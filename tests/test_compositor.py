import numpy as np

from multicam.core.cameras import Frame
from multicam.core.imaging import Compositor
from multicam.core.state import (
    CameraLayer,
    ViewState,
)


def test_compositor_layers():
    first = np.zeros(
        (100, 100, 3),
        dtype=np.uint8,
    )
    first[:, :, 0] = 100

    second = np.full(
        (50, 50),
        1000,
        dtype=np.uint16,
    )
    second[10:40, 10:40] = 5000

    frames = {
        "camera:A": Frame(
            camera_id="camera:A",
            image=first,
            width=100,
            height=100,
            pixel_format="RGB888",
            bit_depth=8,
        ),
        "camera:B": Frame(
            camera_id="camera:B",
            image=second,
            width=50,
            height=50,
            pixel_format="Mono16",
            bit_depth=16,
        ),
    }

    state = ViewState(
        layers=[
            CameraLayer(
                camera_id="camera:A",
                opacity=1.0,
                z_order=0,
            ),
            CameraLayer(
                camera_id="camera:B",
                opacity=0.5,
                z_order=1,
            ),
        ],
    )

    output = Compositor().compose(frames, state)

    assert output is not None
    assert output.shape == (100, 100, 3)
    assert output.dtype == np.uint8


def test_disabled_first_layer_keeps_canvas_and_shows_next_layer():
    first = np.full(
        (40, 60, 3),
        200,
        dtype=np.uint8,
    )
    second = np.full(
        (20, 30, 3),
        80,
        dtype=np.uint8,
    )

    frames = {
        "camera:A": Frame(
            camera_id="camera:A",
            image=first,
        ),
        "camera:B": Frame(
            camera_id="camera:B",
            image=second,
        ),
    }

    state = ViewState(
        layers=[
            CameraLayer(
                camera_id="camera:A",
                enabled=False,
                z_order=0,
            ),
            CameraLayer(
                camera_id="camera:B",
                enabled=True,
                opacity=1.0,
                z_order=1,
            ),
        ],
    )

    output = Compositor().compose(frames, state)

    assert output is not None
    assert output.shape == (40, 60, 3)
    assert np.all(output == 80)


def test_first_layer_opacity_blends_against_black():
    image = np.full(
        (10, 10, 3),
        100,
        dtype=np.uint8,
    )

    frames = {
        "camera:A": Frame(
            camera_id="camera:A",
            image=image,
        ),
    }

    state = ViewState(
        layers=[
            CameraLayer(
                camera_id="camera:A",
                opacity=0.5,
            ),
        ],
    )

    output = Compositor().compose(frames, state)

    assert output is not None
    assert np.all(output == 50)
