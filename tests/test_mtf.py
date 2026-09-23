import numpy as np
import pytest

from multicam.core.cameras import Frame
from multicam.core.services import MtfService
from multicam.core.state import CameraOrientation


class StubBroker:
    def __init__(self, frame):
        self.frame = frame

    def get_latest(self, camera_id):
        return self.frame if camera_id == self.frame.camera_id else None


class StubOrientationStore:
    def get(self, camera_id):
        return CameraOrientation(rotation_deg=90)


def synthetic_edge(size=160, angle_degrees=6.0, sigma=1.2):
    yy, xx = np.mgrid[:size, :size].astype(np.float64)
    slope = np.tan(np.radians(angle_degrees))
    distance = (xx - slope * yy - size / 2) / np.sqrt(1 + slope**2)
    # Error-function approximation for a Gaussian-blurred step.
    values = np.vectorize(math_erf)(distance / (np.sqrt(2) * sigma))
    return 25.0 + 200.0 * 0.5 * (1.0 + values)


def math_erf(value):
    import math
    return math.erf(float(value))


def test_mtf_freeze_copies_raw_frame():
    image = np.zeros((60, 80), dtype=np.uint16)
    service = MtfService(StubBroker(Frame(camera_id="camera", image=image)))
    info = service.freeze("camera")
    image[:] = 1000
    assert (info.width, info.height) == (80, 60)
    assert service.get_frozen("camera").image.max() == 0


def test_pixel_roi_coordinates_are_not_treated_as_normalized():
    assert MtfService._roi_pixels(
        (10, 12, 70, 52), (60, 80), "pixels"
    ) == (10, 12, 70, 52)


def test_frozen_frame_and_analysis_use_camera_orientation():
    image = np.zeros((40, 80), dtype=np.uint16)
    image[:, :20] = 4095
    service = MtfService(
        StubBroker(Frame(camera_id="camera", image=image)),
        orientation_store=StubOrientationStore(),
    )
    info = service.freeze("camera")
    oriented = service.get_oriented_image("camera")
    assert (info.width, info.height) == (40, 80)
    assert oriented.shape == (80, 40)
    assert oriented[:20].min() == 4095


@pytest.mark.parametrize("sigma", [0.8, 1.0, 1.25, 1.5, 2.0])
def test_slanted_edge_mtf50_matches_gaussian_theory(sigma):
    image = synthetic_edge(sigma=sigma)
    service = MtfService(StubBroker(Frame(camera_id="camera", image=image)))
    service.freeze("camera")
    result = service.analyze("camera", (0, 0, 1, 1), "slanted_edge")
    expected = np.sqrt(np.log(2.0) / (2.0 * np.pi**2 * sigma**2))
    error_percent = 100.0 * abs(
        result["mtf50_cycles_per_pixel"] - expected
    ) / expected
    assert result["valid"] is True
    assert error_percent <= 5.0
    assert len(result["frequency_cycles_per_pixel"]) > 100


def test_usaf_bar_reports_modulation_and_frequency():
    width = 180
    bars = np.where((np.arange(width) // 6) % 2, 220.0, 30.0)
    image = np.tile(bars, (100, 1))
    service = MtfService(StubBroker(Frame(camera_id="camera", image=image)))
    service.freeze("camera")
    result = service.analyze("camera", (0, 0, 1, 1), "usaf_bar")
    assert result["orientation"] == "vertical bars"
    assert result["modulation"] == pytest.approx(0.76, abs=0.02)
    assert result["dominant_frequency_cycles_per_pixel"] == pytest.approx(
        1 / 12,
        abs=0.01,
    )


def test_usaf_rejects_whole_target_scale_gradient():
    image = np.tile(np.linspace(20.0, 220.0, 180), (100, 1))
    service = MtfService(StubBroker(Frame(camera_id="camera", image=image)))
    service.freeze("camera")
    result = service.analyze("camera", (0, 0, 1, 1), "usaf_bar")
    assert result["valid"] is False
    assert "three-bar" in result["warning"]
