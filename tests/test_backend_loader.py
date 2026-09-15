from types import SimpleNamespace

from multicam.api.web import backend_loader
from multicam.core.cameras import CameraManager


class FakeBackend:
    name = "picamera2"

    def discover(self):
        return []

    def open(self, camera_id):
        raise KeyError(camera_id)


def test_unavailable_backend_does_not_block_others(monkeypatch):
    def fake_import(module_name):
        if module_name.endswith(".aravis"):
            raise ImportError("Aravis is not installed")

        return SimpleNamespace(Picamera2Backend=FakeBackend)

    monkeypatch.setattr(
        backend_loader.importlib,
        "import_module",
        fake_import,
    )

    manager = CameraManager()
    results = backend_loader.register_available_backends(
        manager,
        backend_loader.logging.getLogger("test"),
    )

    assert manager.backend_names == ["picamera2"]
    assert results[0].loaded is True
    assert results[1].loaded is False
    assert "not installed" in results[1].error
