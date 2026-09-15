import numpy as np

from multicam.core.cameras import Frame
from multicam.core.imaging import Compositor
from multicam.core.state import (
    CameraLayer,
    RegistrationTransform,
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


def test_compositor_uses_alignment_reference_canvas_and_translation():
    frames = {
        "target": Frame(
            camera_id="target",
            image=np.array([[255, 0], [0, 0]], dtype=np.uint8),
        ),
        "reference": Frame(
            camera_id="reference",
            image=np.zeros((4, 4), dtype=np.uint8),
        ),
    }
    view = ViewState(layers=[
        CameraLayer(camera_id="target", opacity=1.0, z_order=0),
    ])
    registration = RegistrationTransform(
        matrix=(
            (2.0, 0.0, 1.0),
            (0.0, 2.0, 0.0),
            (0.0, 0.0, 1.0),
        ),
        source_size=(2, 2),
        reference_size=(4, 4),
    )

    output = Compositor().compose(
        frames,
        view,
        registrations={"target": registration},
        reference_camera_id="reference",
    )

    assert output.shape == (4, 4, 3)
    assert output[0, 1].tolist() == [255, 255, 255]
    assert output[0, 0].tolist() == [0, 0, 0]
