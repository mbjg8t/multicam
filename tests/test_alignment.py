import numpy as np
import pytest

from multicam.core.cameras import Frame
from multicam.core.services import AlignmentService
from multicam.core.state import (
    AlignmentStateStore,
    RegistrationTransform,
)


class StubBroker:
    def __init__(self, frames):
        self.frames = frames

    def get_latest(self, camera_id):
        return self.frames.get(camera_id)


def point_pair_transform():
    return RegistrationTransform.from_point_pair(
        source_point=(10.0, 10.0),
        reference_point=(50.0, 35.0),
        source_size=(100, 50),
        reference_size=(200, 100),
    )


def test_point_pair_maps_source_pixels_to_reference_pixels():
    transform = point_pair_transform()

    assert transform.matrix == (
        (2.0, 0.0, 30.0),
        (0.0, 2.0, 15.0),
        (0.0, 0.0, 1.0),
    )
    assert transform.x == 30.0
    assert transform.y == 15.0


def test_alignment_state_draft_accept_reject_and_undo():
    state = AlignmentStateStore()
    transform = point_pair_transform()
    state.select("reference", "target")

    state.set_draft("target", transform)
    assert state.effective_transforms()["target"] == transform
    assert state.reject("target") is True
    assert state.effective_transforms() == {}

    state.set_draft("target", transform)
    assert state.accept("target") is True
    assert state.get().transforms["target"] == transform
    assert state.undo("target") is True
    assert state.get().transforms == {}


def test_reference_change_is_guarded_after_alignment_exists():
    state = AlignmentStateStore()
    state.select("reference", "target")
    state.set_draft("target", point_pair_transform())
    state.accept("target")

    with pytest.raises(ValueError, match="Clear existing alignments"):
        state.select("other-reference", "target")

    assert state.reset() is True
    state.select("other-reference", "target")


def test_alignment_service_freezes_copies_and_builds_draft():
    reference_image = np.zeros((100, 200), dtype=np.uint8)
    target_image = np.zeros((50, 100), dtype=np.uint8)
    frames = {
        "reference": Frame(
            camera_id="reference",
            image=reference_image,
            monotonic_timestamp_ns=1_000,
        ),
        "target": Frame(
            camera_id="target",
            image=target_image,
            monotonic_timestamp_ns=1_500,
        ),
    }
    state = AlignmentStateStore()
    state.select("reference", "target")
    service = AlignmentService(StubBroker(frames), state)

    info = service.freeze(["reference", "target"])
    reference_image[:] = 255

    assert service.get_frozen("reference").image.max() == 0
    assert service.timestamp_skew_ns(info) == 500

    transform = service.set_point_pair(
        reference_point=(50.0, 35.0),
        target_point=(10.0, 10.0),
    )

    assert transform.x == 30.0
    assert state.get().drafts["target"] == transform


def test_alignment_service_rejects_click_outside_frame():
    frames = {
        "reference": Frame(
            camera_id="reference",
            image=np.zeros((10, 10), dtype=np.uint8),
        ),
        "target": Frame(
            camera_id="target",
            image=np.zeros((10, 10), dtype=np.uint8),
        ),
    }
    state = AlignmentStateStore()
    state.select("reference", "target")
    service = AlignmentService(StubBroker(frames), state)
    service.freeze(["reference", "target"])

    with pytest.raises(ValueError, match="outside"):
        service.set_point_pair(
            reference_point=(10.0, 2.0),
            target_point=(2.0, 2.0),
        )
