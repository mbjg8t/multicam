from types import SimpleNamespace

from flask import Flask
import numpy as np

from multicam.api.web.alignment_routes import create_alignment_blueprint
from multicam.core.cameras import Frame
from multicam.core.imaging import Compositor
from multicam.core.services import AlignmentService, CameraOrientationStore
from multicam.core.state import AlignmentStateStore


class StubManager:
    def __init__(self, cameras):
        self.cameras = cameras

    def list_cameras(self):
        return self.cameras


class StubBroker:
    def __init__(self, frames):
        self.frames = frames

    def get_latest(self, camera_id):
        return self.frames.get(camera_id)

    def get_state(self, camera_id):
        return SimpleNamespace(
            running=camera_id in self.frames,
            last_error=None,
        )


def test_guided_alignment_api_workflow(tmp_path):
    cameras = [
        SimpleNamespace(
            id="reference",
            name="Reference",
            backend="fake",
            model="A",
            connected=True,
        ),
        SimpleNamespace(
            id="target",
            name="Target",
            backend="fake",
            model="B",
            connected=True,
        ),
    ]
    broker = StubBroker({
        "reference": Frame(
            camera_id="reference",
            image=np.zeros((40, 60), dtype=np.uint8),
            monotonic_timestamp_ns=1_000,
        ),
        "target": Frame(
            camera_id="target",
            image=np.zeros((20, 30), dtype=np.uint8),
            monotonic_timestamp_ns=2_000,
        ),
    })
    state = AlignmentStateStore()
    orientations = CameraOrientationStore(tmp_path / "orientations.json")
    alignment = AlignmentService(
        broker,
        state,
        orientation_store=orientations,
    )
    app = Flask(
        __name__,
        template_folder="../multicam/api/web/templates",
    )
    app.register_blueprint(create_alignment_blueprint(
        manager=StubManager(cameras),
        broker=broker,
        alignment_state=state,
        alignment_service=alignment,
        compositor=Compositor(),
        orientation_store=orientations,
    ))
    client = app.test_client()

    response = client.patch("/api/alignment/selection", json={
        "reference_camera_id": "reference",
        "target_camera_id": "target",
    })
    assert response.status_code == 200

    response = client.post("/api/alignment/freeze")
    assert response.status_code == 200
    assert response.get_json()["timestamp_skew_ns"] == 1_000

    response = client.post("/api/alignment/point-pair", json={
        "reference_point": {"x": 30, "y": 20},
        "target_point": {"x": 10, "y": 5},
    })
    assert response.status_code == 200
    target = next(
        item
        for item in response.get_json()["cameras"]
        if item["id"] == "target"
    )
    assert target["alignment_status"] == "preview"
    assert target["transform"]["x"] == 10.0
    assert target["transform"]["y"] == 10.0

    response = client.post("/api/alignment/nudge", json={
        "x_delta": 5,
        "y_delta": -2,
    })
    assert response.status_code == 200
    target = next(
        item
        for item in response.get_json()["cameras"]
        if item["id"] == "target"
    )
    assert target["transform"]["x"] == 15.0
    assert target["transform"]["y"] == 8.0

    preview = client.get("/alignment/preview")
    assert preview.status_code == 200
    assert preview.mimetype == "image/jpeg"

    response = client.post("/api/alignment/accept")
    target = next(
        item
        for item in response.get_json()["cameras"]
        if item["id"] == "target"
    )
    assert target["alignment_status"] == "aligned"
