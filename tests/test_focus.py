from types import SimpleNamespace

from flask import Flask
import numpy as np
import pytest

from multicam.api.web.focus_routes import create_focus_blueprint
from multicam.core.cameras import CameraCapability, Frame
from multicam.core.imaging import Compositor
from multicam.core.services import CameraOrientationStore, FocusService


class StubBroker:
    def __init__(self, frames):
        self.frames = frames

    def get_latest(self, camera_id):
        return self.frames.get(camera_id)

    def get_state(self, camera_id):
        return SimpleNamespace(running=True, last_error=None)


class FocusDevice:
    def __init__(self):
        self.position = 1.0

    def get_capabilities(self):
        return [
            CameraCapability(
                id="focus_position",
                name="Lens Position",
                type="float",
                writable=True,
                minimum=0.0,
                maximum=10.0,
                metadata={"purpose": "focus"},
            )
        ]

    def set_control(self, control_id, value):
        assert control_id == "focus_position"
        self.position = float(value)


class StubManager:
    def __init__(self, camera, device):
        self.camera = camera
        self.device = device

    def list_cameras(self):
        return [self.camera]

    def get_device(self, camera_id):
        return self.device if camera_id == self.camera.id else None


def box_blur(image, radius=4):
    padded = np.pad(image.astype(np.float32), radius, mode="edge")
    result = np.zeros_like(image, dtype=np.float32)
    width = radius * 2 + 1

    for y_offset in range(width):
        for x_offset in range(width):
            result += padded[
                y_offset:y_offset + image.shape[0],
                x_offset:x_offset + image.shape[1],
            ]

    return (result / (width * width)).astype(np.uint8)


def focus_service(tmp_path, frames):
    return FocusService(
        broker=StubBroker(frames),
        orientation_store=CameraOrientationStore(
            tmp_path / "orientations.json"
        ),
        compositor=Compositor(),
    )


def test_focus_metric_prefers_sharp_structure(tmp_path):
    y, x = np.indices((180, 240))
    sharp = (((x // 6 + y // 6) % 2) * 255).astype(np.uint8)
    blurred = box_blur(sharp)
    service = focus_service(tmp_path, {
        "sharp": Frame(camera_id="sharp", image=sharp),
        "blurred": Frame(camera_id="blurred", image=blurred),
    })

    sharp_sample = service.analyze("sharp", size=0.5)
    blurred_sample = service.analyze("blurred", size=0.5)

    assert sharp_sample.tenengrad > blurred_sample.tenengrad
    assert sharp_sample.laplacian > blurred_sample.laplacian


def test_focus_roi_stays_inside_frame():
    assert FocusService.roi_box(
        100,
        80,
        center_x=0.0,
        center_y=1.0,
        size=0.25,
    ) == (0, 60, 25, 80)

    with pytest.raises(ValueError, match="inside"):
        FocusService.roi_box(
            100,
            80,
            center_x=1.1,
            center_y=0.5,
            size=0.25,
        )


def test_focus_api_lists_analyzes_and_controls_camera(tmp_path):
    camera = SimpleNamespace(
        id="fake:focus",
        name="Focus Camera",
        model="Test",
        backend="fake",
        connected=True,
    )
    device = FocusDevice()
    frame = Frame(
        camera_id=camera.id,
        image=np.tile(np.arange(100, dtype=np.uint8), (80, 1)),
        frame_number=4,
        metadata={"LensPosition": 1.5, "AfState": 2},
    )
    broker = StubBroker({camera.id: frame})
    service = FocusService(
        broker=broker,
        orientation_store=CameraOrientationStore(
            tmp_path / "orientations.json"
        ),
        compositor=Compositor(),
    )
    app = Flask(
        __name__,
        template_folder="../multicam/api/web/templates",
    )
    app.register_blueprint(create_focus_blueprint(
        manager=StubManager(camera, device),
        broker=broker,
        focus_service=service,
    ))
    client = app.test_client()

    listed = client.get("/api/focus/cameras")
    assert listed.status_code == 200
    assert listed.get_json()["cameras"][0]["id"] == camera.id

    metrics = client.get(
        "/api/focus/fake:focus/metrics?x=0.5&y=0.5&size=0.25"
    )
    assert metrics.status_code == 200
    assert metrics.get_json()["frame_number"] == 4
    assert metrics.get_json()["lens_position"] == 1.5

    changed = client.post("/api/focus/fake:focus/control", json={
        "control_id": "focus_position",
        "value": 2.25,
    })
    assert changed.status_code == 200
    assert device.position == 2.25
