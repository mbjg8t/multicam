import numpy as np

from multicam.core.cameras import Frame
from multicam.core.imaging import Compositor
from multicam.core.state import (
    OverlayLayer,
    ViewState,
)


def test_compositor_base_and_overlay():
    base = np.zeros(
        (100, 100, 3),
        dtype=np.uint8,
    )

    base[:, :, 0] = 100

    overlay = np.full(
        (50, 50),
        1000,
        dtype=np.uint16,
    )

    overlay[10:40, 10:40] = 5000

    frames = {
        "camera:A": Frame(
            camera_id="camera:A",
            image=base,
            width=100,
            height=100,
            pixel_format="RGB888",
            bit_depth=8,
        ),
        "camera:B": Frame(
            camera_id="camera:B",
            image=overlay,
            width=50,
            height=50,
            pixel_format="Mono16",
            bit_depth=16,
        ),
    }

    state = ViewState(
        base_camera_id="camera:A",
        overlays=[
            OverlayLayer(
                camera_id="camera:B",
                opacity=0.5,
                z_order=0,
            )
        ],
    )

    output = Compositor().compose(
        frames,
        state,
    )

    assert output is not None
    assert output.shape == (100, 100, 3)
    assert output.dtype == np.uint8
