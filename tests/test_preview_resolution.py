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
