from multicam.core.state import (
    CameraLayer,
    Transform,
    ViewStateStore,
)


def test_view_state_layers():
    state = ViewStateStore()

    state.add_layer(
        CameraLayer(
            camera_id="camera:A",
            opacity=1.0,
            z_order=0,
        )
    )

    state.add_layer(
        CameraLayer(
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

    assert [layer.camera_id for layer in current.layers] == [
        "camera:A",
        "camera:B",
    ]
    assert current.layers[1].opacity == 0.75

    state.update_layer(
        "camera:B",
        opacity=0.5,
        enabled=False,
    )

    updated = state.get().layers[1]
    assert updated.opacity == 0.5
    assert updated.enabled is False

    state.remove_layer("camera:B")

    assert [layer.camera_id for layer in state.get().layers] == [
        "camera:A"
    ]


def test_view_state_rejects_duplicate_camera_layer():
    state = ViewStateStore()
    state.add_layer(CameraLayer(camera_id="camera:A"))

    try:
        state.add_layer(CameraLayer(camera_id="camera:A"))
    except ValueError:
        pass
    else:
        raise AssertionError("Duplicate camera layer was accepted")
