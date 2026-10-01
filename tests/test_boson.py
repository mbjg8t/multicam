from types import SimpleNamespace

import numpy as np
import pytest

from multicam.backends.boson.backend import (
    BosonBackend,
    BosonDevice,
    _parse_sizes,
    _parse_video_blocks,
)
from multicam.core.cameras import CameraInfo


LISTING = """FLIR Boson (usb-0000:01:00.0-1.2):
    /dev/video4
    /dev/video5

Other Camera:
    /dev/video0
"""


def test_video_device_listing_parser():
    assert _parse_video_blocks(LISTING) == [
        ("FLIR Boson (usb-0000:01:00.0-1.2)", ["/dev/video4", "/dev/video5"]),
        ("Other Camera", ["/dev/video0"]),
    ]


def test_size_parser():
    assert _parse_sizes("Size: Discrete 640x512\nSize: Discrete 320x256") == [
        (640, 512), (320, 256)
    ]


def test_backend_only_discovers_boson_image_nodes():
    def runner(command):
        if command == ["v4l2-ctl", "--list-devices"]:
            return SimpleNamespace(returncode=0, stdout=LISTING, stderr="")
        device = command[2]
        output = "Size: Discrete 640x512" if device == "/dev/video4" else ""
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    backend = BosonBackend(runner=runner)
    cameras = backend.discover()
    assert [camera.id for camera in cameras] == ["boson:/dev/video4"]
    assert cameras[0].metadata["capture_size"] == (640, 512)


class FakeCv2:
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_FOURCC = 6
    CAP_PROP_CONVERT_RGB = 16
    COLOR_BGR2GRAY = 6
    COLOR_BGR2RGB = 4
    COLORMAP_INFERNO = 14
    COLORMAP_TURBO = 20
    COLORMAP_JET = 2
    COLORMAP_MAGMA = 13
    COLORMAP_HOT = 11
    COLORMAP_BONE = 1

    @staticmethod
    def VideoWriter_fourcc(*characters):
        assert characters == ("I", "4", "2", "0")
        return 0x30323449

    @staticmethod
    def cvtColor(image, code):
        if code == FakeCv2.COLOR_BGR2GRAY:
            return image[:, :, 0]
        if code == FakeCv2.COLOR_BGR2RGB:
            return image[:, :, ::-1]
        raise AssertionError(code)

    @staticmethod
    def applyColorMap(image, map_id):
        del map_id
        return np.repeat(image[:, :, None], 3, axis=2)


class FakeCapture:
    def __init__(self, frame):
        self.frame = frame
        self.released = False

    def set(self, key, value):
        return True

    def isOpened(self):
        return True

    def read(self):
        return True, self.frame.copy()

    def release(self):
        self.released = True


def make_device(frame):
    info = CameraInfo(
        id="boson:/dev/video4", backend="boson", name="FLIR Boson",
        metadata={"device_path": "/dev/video4", "capture_size": (640, 514)},
    )
    capture = FakeCapture(frame)
    return BosonDevice(
        info, capture_factory=lambda path: capture, cv2_module=FakeCv2
    ), capture


def test_boson_frame_is_cropped_colormapped_and_released():
    source = np.tile(np.arange(640, dtype=np.uint8), (514, 1))
    device, capture = make_device(source)
    device.start()
    frame = device.get_frame()
    device.stop()
    assert frame.image.shape == (512, 640, 3)
    assert frame.pixel_format == "RGB888"
    assert capture.released is True


def test_boson_decodes_byte_wide_y16_without_doubling_width():
    source = np.arange(514 * 640, dtype=np.uint16).reshape(514, 640)
    packed = source.view(np.uint8).reshape(514, 1280)
    device, _ = make_device(packed)
    device.start()
    gray = device._to_gray(packed)
    assert gray.shape == (514, 640)
    assert gray.dtype == np.uint16
    np.testing.assert_array_equal(gray, source)


def test_boson_controls_validate_ranges_and_palette():
    device, _ = make_device(np.zeros((514, 640), dtype=np.uint8))
    device.set_control("colormap", "gray")
    device.set_control("contrast_low_percentile", 5)
    device.set_control("contrast_high_percentile", 95)
    assert device.get_control("colormap") == "gray"
    assert device.get_control("contrast_low_percentile") == 5.0
    with pytest.raises(ValueError, match="palette"):
        device.set_control("colormap", "rainbow")


def test_boson_calibration_capture_uses_live_native_frame():
    source = np.tile(np.arange(640, dtype=np.uint8), (514, 1))
    device, capture = make_device(source)
    device.start()
    live = device.get_frame()

    assert device.calibration_capture_uses_live_frame is True
    assert live.width == 640
    assert live.height == 512
    assert live.metadata["capture_quality"] == "selected_acquisition_mode"
    assert capture.released is False

    device.stop()
