from types import SimpleNamespace
import time

from multicam.backends.picamera2.backend import Picamera2Device
from multicam.core.cameras import CameraCapability, CameraDevice, CameraInfo
from multicam.core.cameras.broker import FrameBroker


class ReconfigurableFakeCamera(CameraDevice):
    def __init__(self):
        super().__init__(CameraInfo(
            id="fake:preview",
            backend="fake",
            name="Preview Fake",
        ))
        self.running = False
        self.resolution = "640x480"

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def get_frame(self, timeout=None):
        time.sleep(0.01)
        return None

    def get_capabilities(self):
        return [
            CameraCapability(
                id="preview_resolution",
                name="Live Preview Resolution",
                type="choice",
                writable=True,
                value=self.resolution,
                choices=["640x480", "1280x960"],
                metadata={"requires_stream_restart": True},
            )
        ]

    def get_control(self, control_id):
        if control_id == "preview_resolution":
            return self.resolution
        raise KeyError(control_id)

    def set_control(self, control_id, value):
        if control_id != "preview_resolution":
            raise KeyError(control_id)
        if self.running:
            raise RuntimeError("configuration while streaming")
        self.resolution = value


def test_picamera_preview_resolution_capability_is_generic_choice():
    device = object.__new__(Picamera2Device)
    device._camera = SimpleNamespace(camera_controls={})
    device._preview_size = (1280, 960)
    device._preview_sizes = [(640, 480), (1280, 960)]

    capability = next(
        item
        for item in device.get_capabilities()
        if item.id == "preview_resolution"
    )

    assert capability.value == "1280x960"
    assert capability.choices == ["640x480", "1280x960"]
    assert capability.metadata["requires_stream_restart"] is True


def test_picamera_reports_all_supported_standard_image_controls():
    device = object.__new__(Picamera2Device)
    device._camera = SimpleNamespace(camera_controls={
        "Brightness": (-1.0, 1.0, 0.0),
        "Contrast": (0.0, 32.0, 1.0),
        "Saturation": (0.0, 32.0, 1.0),
        "Sharpness": (0.0, 16.0, 1.0),
        "ExposureValue": (-8.0, 8.0, 0.0),
        "AeEnable": (False, True, True),
        "AwbEnable": (False, True, True),
    })
    device._preview_size = (1280, 960)
    device._preview_sizes = [(1280, 960)]

    capabilities = {item.id: item for item in device.get_capabilities()}

    assert {
        "brightness", "contrast", "saturation", "sharpness",
        "exposure_compensation", "auto_exposure", "auto_white_balance",
    } <= set(capabilities)
    assert capabilities["auto_exposure"].type == "boolean"


def test_picamera_preview_resolution_parser_rejects_bad_values():
    assert Picamera2Device._parse_preview_size("640x480") == (640, 480)

    try:
        Picamera2Device._parse_preview_size("invalid")
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid preview size should be rejected")


def test_broker_reconfigures_only_the_selected_camera():
    broker = FrameBroker()
    camera = ReconfigurableFakeCamera()
    broker.add_camera(camera)

    broker.reconfigure(
        camera.id,
        lambda device: device.set_control(
            "preview_resolution",
            "1280x960",
        ),
    )

    assert camera.resolution == "1280x960"
    broker.stop(camera.id)


def test_picamera_sensor_modes_are_reported_from_libcamera():
    device = object.__new__(Picamera2Device)
    device._camera = SimpleNamespace(
        camera_controls={},
        sensor_modes=[
            {"size": (1920, 1080), "fps": 70.56, "bit_depth": 10,
             "format": "SRGGB10", "crop_limits": (0, 0, 9248, 6944)},
            {"size": (9248, 6944), "fps": 2.60, "bit_depth": 10,
             "format": "SRGGB10", "crop_limits": (0, 0, 9248, 6944)},
        ],
    )
    device._sensor_modes = device._read_sensor_modes()
    device._preview_size = (1920, 1080)
    device._preview_sizes = [m["size"] for m in device._sensor_modes]

    capability = next(
        item for item in device.get_capabilities()
        if item.id == "sensor_modes"
    )

    assert "1920x1080 @ 70.56 fps" in capability.value
    assert "9248x6944 @ 2.60 fps" in capability.value
    assert "MAX" in capability.value
    assert capability.metadata["section"] == "Sensor"


def test_picamera_maximum_mode_uses_largest_sensor_area():
    device = object.__new__(Picamera2Device)
    device._sensor_modes = [
        {"size": (4624, 3472), "bit_depth": 10},
        {"size": (9248, 6944), "bit_depth": 10},
        {"size": (8000, 6000), "bit_depth": 10},
    ]

    assert device._maximum_sensor_mode()["size"] == (9248, 6944)
