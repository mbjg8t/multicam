from multicam.core.state import (
    OverlayLayer,
    Transform,
    ViewStateStore,
)


def test_view_state():
    state = ViewStateStore()

    state.set_base("camera:A")

    state.add_overlay(
        OverlayLayer(
            camera_id="camera:B",
            opacity=0.75,
            transform=Transform(
                x=10,
                y=-5,
                scale_x=1.1,
                scale_y=1.1,
            ),
            z_order=1,
        )
    )

    current = state.get()

    assert current.base_camera_id == "camera:A"
    assert len(current.overlays) == 1
    assert current.overlays[0].camera_id == "camera:B"
    assert current.overlays[0].opacity == 0.75

    state.update_overlay(
        "camera:B",
        opacity=0.5,
    )

    assert state.get().overlays[0].opacity == 0.5

    state.remove_overlay("camera:B")

    assert state.get().overlays == []
