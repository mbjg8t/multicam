from multicam.core.cameras import (
    CameraBackend,
    CameraCapability,
    CameraDevice,
    CameraInfo,
    CameraManager,
    Frame,
)


class FakeCamera(CameraDevice):

    def __init__(self, info):
        super().__init__(info)
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def get_frame(self, timeout=None):
        if not self.running:
            return None

        return Frame(
            camera_id=self.id,
            image="fake-image",
            width=640,
            height=480,
            pixel_format="Mono8",
            bit_depth=8,
        )

    def get_capabilities(self):
        return [
            CameraCapability(
                id="exposure",
                name="Exposure",
                type="float",
                writable=True,
                minimum=10.0,
                maximum=100000.0,
                units="us",
            )
        ]

    def get_control(self, control_id):
        return 1000.0

    def set_control(self, control_id, value):
        return value


class FakeBackend(CameraBackend):

    name = "fake"

    def discover(self):
        return [
            CameraInfo(
                id="fake:test:001",
                backend=self.name,
                name="Test Camera",
                vendor="Multicam",
                model="FakeCam",
                serial="001",
            )
        ]

    def open(self, camera_id):
        for info in self.discover():
            if info.id == camera_id:
                return FakeCamera(info)

        raise KeyError(camera_id)


def test_camera_manager():

    manager = CameraManager()

    manager.register_backend(FakeBackend())

    cameras = manager.discover()

    assert len(cameras) == 1
    assert cameras[0].id == "fake:test:001"
    assert cameras[0].connected is True

    camera = manager.open("fake:test:001")

    camera.start()

    frame = camera.get_frame()

    assert frame is not None
    assert frame.camera_id == "fake:test:001"
    assert frame.width == 640
    assert frame.height == 480

    manager.close_all()
