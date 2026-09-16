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


def alignment_service_with_large_frames():
    frames = {
        "reference": Frame(
            camera_id="reference",
            image=np.zeros((1000, 1200), dtype=np.uint8),
        ),
        "target": Frame(
            camera_id="target",
            image=np.zeros((1000, 1200), dtype=np.uint8),
        ),
    }
    state = AlignmentStateStore()
    state.select("reference", "target")
    service = AlignmentService(StubBroker(frames), state)
    service.freeze(["reference", "target"])
    return service, state


def test_two_point_alignment_solves_rotation_scale_and_translation():
    service, state = alignment_service_with_large_frames()
    source_points = [(10.0, 10.0), (30.0, 10.0)]
    reference_points = [(80.0, 70.0), (80.0, 110.0)]

    transform = service.set_point_pairs(
        reference_points=reference_points,
        target_points=source_points,
    )

    assert transform.model == "similarity"
    assert np.asarray(transform.matrix) == pytest.approx(np.asarray((
        (0.0, -2.0, 100.0),
        (2.0, 0.0, 50.0),
        (0.0, 0.0, 1.0),
    )))
    assert transform.rotation_deg == pytest.approx(90.0)
    assert transform.scale_x == pytest.approx(2.0)
    assert state.get().drafts["target"] == transform


def test_four_point_alignment_solves_perspective_transform():
    service, _ = alignment_service_with_large_frames()
    expected = np.asarray((
        (1.2, 0.1, 10.0),
        (0.05, 1.1, 20.0),
        (0.0005, 0.0002, 1.0),
    ))
    source_points = [
        (50.0, 50.0),
        (950.0, 60.0),
        (900.0, 850.0),
        (80.0, 900.0),
    ]

    def project(point):
        mapped = expected @ np.asarray((point[0], point[1], 1.0))
        return tuple(mapped[:2] / mapped[2])

    reference_points = [project(point) for point in source_points]
    transform = service.set_point_pairs(
        reference_points=reference_points,
        target_points=source_points,
    )

    assert transform.model == "homography"
    assert np.asarray(transform.matrix) == pytest.approx(
        expected,
        rel=1e-8,
        abs=1e-8,
    )


def test_multi_point_alignment_rejects_degenerate_layout():
    service, _ = alignment_service_with_large_frames()

    with pytest.raises(ValueError, match="cannot determine"):
        service.set_point_pairs(
            reference_points=[
                (10.0, 10.0),
                (20.0, 20.0),
                (30.0, 30.0),
                (40.0, 40.0),
            ],
            target_points=[
                (10.0, 10.0),
                (20.0, 20.0),
                (30.0, 30.0),
                (40.0, 40.0),
            ],
            requested_model="homography",
        )


def test_auto_model_selects_affine_for_directional_stretch():
    service, _ = alignment_service_with_large_frames()
    expected = np.asarray((
        (1.2, 0.15, 20.0),
        (-0.05, 0.8, 30.0),
        (0.0, 0.0, 1.0),
    ))
    source_points = [
        (50.0, 50.0),
        (800.0, 60.0),
        (820.0, 850.0),
        (70.0, 880.0),
        (500.0, 300.0),
        (750.0, 650.0),
    ]

    def project(point):
        mapped = expected @ np.asarray((point[0], point[1], 1.0))
        return tuple(mapped[:2])

    transform = service.set_point_pairs(
        reference_points=[project(point) for point in source_points],
        target_points=source_points,
        requested_model="auto",
    )

    assert transform.model == "affine"
    assert transform.rms_error_px == pytest.approx(0.0, abs=1e-8)
    assert transform.inlier_mask == (True,) * len(source_points)


def test_robust_homography_rejects_bad_point_pair():
    service, _ = alignment_service_with_large_frames()
    expected = np.asarray((
        (0.95, 0.08, 30.0),
        (-0.03, 1.05, 15.0),
        (0.0002, -0.0001, 1.0),
    ))
    source_points = [
        (50.0, 50.0),
        (1050.0, 50.0),
        (1050.0, 780.0),
        (50.0, 780.0),
        (300.0, 250.0),
        (800.0, 300.0),
        (350.0, 650.0),
        (850.0, 700.0),
    ]

    def project(point):
        mapped = expected @ np.asarray((point[0], point[1], 1.0))
        return tuple(mapped[:2] / mapped[2])

    reference_points = [project(point) for point in source_points]
    reference_points[5] = (100.0, 950.0)
    transform = service.set_point_pairs(
        reference_points=reference_points,
        target_points=source_points,
        requested_model="homography",
    )

    assert transform.model == "homography"
    assert transform.inlier_mask[5] is False
    assert sum(transform.inlier_mask) == 7
    assert transform.rms_error_px == pytest.approx(0.0, abs=1e-7)
    assert transform.residuals_px[5] > 100.0


def test_multi_point_alignment_limits_collection_to_twelve_pairs():
    service, _ = alignment_service_with_large_frames()
    points = [(float(index * 10), 50.0) for index in range(13)]

    with pytest.raises(ValueError, match="twelve"):
        service.set_point_pairs(
            reference_points=points,
            target_points=points,
        )


def test_nudge_left_multiplies_perspective_transform():
    transform = RegistrationTransform(
        matrix=(
            (1.0, 0.0, 10.0),
            (0.0, 1.0, 20.0),
            (0.01, 0.02, 1.0),
        ),
        model="homography",
    )

    nudged = transform.translated(5.0, -3.0)

    assert nudged.matrix == (
        (1.05, 0.1, 15.0),
        (-0.03, 0.94, 17.0),
        (0.01, 0.02, 1.0),
    )
    assert nudged.rms_error_px is None
    assert nudged.residuals_px == ()


def test_auto_alignment_finds_cross_spectral_structural_shift():
    reference_image = np.full((140, 180), 20, dtype=np.uint8)
    reference_image[35:95, 75:82] = 230
    reference_image[62:70, 48:125] = 230
    reference_image[82:103, 105:132] = 150
    reference_image[42:55, 50:65] = 100

    x_shift = -17
    y_shift = 11
    target_image = np.full_like(reference_image, 235)
    source_y1 = max(0, -y_shift)
    source_y2 = min(reference_image.shape[0], reference_image.shape[0] - y_shift)
    source_x1 = max(0, -x_shift)
    source_x2 = min(reference_image.shape[1], reference_image.shape[1] - x_shift)
    target_y1 = max(0, y_shift)
    target_x1 = max(0, x_shift)
    shifted = reference_image[source_y1:source_y2, source_x1:source_x2]
    target_image[
        target_y1:target_y1 + shifted.shape[0],
        target_x1:target_x1 + shifted.shape[1],
    ] = 255 - shifted
    target_image = target_image[::2, ::2]

    frames = {
        "reference": Frame(camera_id="reference", image=reference_image),
        "target": Frame(camera_id="target", image=target_image),
    }
    state = AlignmentStateStore()
    state.select("reference", "target")
    service = AlignmentService(StubBroker(frames), state)
    service.freeze(["reference", "target"])

    result = service.auto_align(reference_point=(80.0, 66.0))

    assert result.target_point[0] == pytest.approx(31.5, abs=1.0)
    assert result.target_point[1] == pytest.approx(38.5, abs=1.0)
    assert result.transform.x == pytest.approx(17.0, abs=1.0)
    assert result.transform.y == pytest.approx(-11.0, abs=2.1)
    assert result.score >= 0.65
    assert result.confidence == "high"


def test_auto_alignment_marks_ambiguous_peak_low_confidence():
    assert AlignmentService._confidence_label(0.90, 0.01) == "low"
    assert AlignmentService._confidence_label(0.70, 0.10) == "high"
