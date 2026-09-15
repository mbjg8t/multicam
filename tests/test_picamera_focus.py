from multicam.backends.picamera2.backend import Picamera2Device


class FakePicamera:
    def __init__(self):
        self.camera_controls = {
            "AfMode": (0, 2, 0),
            "LensPosition": (0.0, 32.0, 1.0),
        }
        self.metadata = {
            "AfMode": 0,
            "AfState": 0,
            "LensPosition": 1.0,
        }
        self.applied = []

    def capture_metadata(self):
        return dict(self.metadata)

    def set_controls(self, controls):
        self.applied.append(dict(controls))
        self.metadata.update(controls)


def focus_device():
    device = object.__new__(Picamera2Device)
    device._camera = FakePicamera()
    device._preview_size = (1280, 960)
    device._preview_sizes = [(1280, 960)]
    return device


def test_picamera_focus_capabilities_are_reported_when_supported():
    capabilities = {
        item.id: item
        for item in focus_device().get_capabilities()
    }

    assert capabilities["focus_mode"].choices == [
        "manual",
        "single",
        "continuous",
    ]
    assert capabilities["focus_position"].minimum == 0.0
    assert capabilities["focus_position"].maximum == 32.0
    assert capabilities["focus_position"].metadata["purpose"] == "focus"


def test_picamera_single_autofocus_and_manual_position_controls():
    device = focus_device()

    device.set_control("focus_mode", "single")
    assert device._camera.applied[-1] == {"AfMode": 1, "AfTrigger": 0}

    device.set_control("focus_position", 2.5)
    assert device._camera.applied[-1] == {
        "LensPosition": 2.5,
        "AfMode": 0,
    }
    assert device.get_control("focus_position") == 2.5
