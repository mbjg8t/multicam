from threading import RLock

from .backend import CameraBackend, CameraDevice
from .device import CameraInfo


class CameraManager:
    """
    Central owner of camera discovery and open camera devices.

    Camera hardware must be opened here rather than independently by
    GUI windows or tools.
    """

    def __init__(self):
        self._backends: dict[str, CameraBackend] = {}
        self._cameras: dict[str, CameraInfo] = {}
        self._devices: dict[str, CameraDevice] = {}

        self._lock = RLock()

    # ------------------------------------------------------------------
    # Backends
    # ------------------------------------------------------------------

    def register_backend(self, backend: CameraBackend) -> None:
        with self._lock:
            if backend.name in self._backends:
                raise ValueError(
                    f"Camera backend already registered: {backend.name}"
                )

            self._backends[backend.name] = backend

    @property
    def backend_names(self) -> list[str]:
        with self._lock:
            return list(self._backends.keys())

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> list[CameraInfo]:
        """
        Ask every registered backend to discover cameras.

        Cameras that disappear remain known but are marked disconnected.
        This gives us the basis for hot-plug behavior later.
        """

        with self._lock:
            previous_ids = set(self._cameras.keys())
            discovered: dict[str, CameraInfo] = {}

            for backend in self._backends.values():
                try:
                    cameras = backend.discover()
                except Exception:
                    # A failing backend must not prevent other camera
                    # systems from operating.
                    continue

                for camera in cameras:
                    if camera.id in discovered:
                        raise RuntimeError(
                            f"Duplicate camera ID discovered: {camera.id}"
                        )

                    camera.connected = True
                    discovered[camera.id] = camera

            missing_ids = previous_ids - set(discovered.keys())

            for camera_id in missing_ids:
                old = self._cameras[camera_id]
                old.connected = False
                discovered[camera_id] = old

            self._cameras = discovered

            return list(self._cameras.values())

    def list_cameras(self) -> list[CameraInfo]:
        with self._lock:
            return list(self._cameras.values())

    def get_camera_info(self, camera_id: str) -> CameraInfo:
        with self._lock:
            return self._cameras[camera_id]

    # ------------------------------------------------------------------
    # Camera ownership
    # ------------------------------------------------------------------

    def open(self, camera_id: str) -> CameraDevice:
        with self._lock:
            existing = self._devices.get(camera_id)

            if existing is not None:
                return existing

            info = self._cameras.get(camera_id)

            if info is None:
                raise KeyError(f"Unknown camera: {camera_id}")

            if not info.connected:
                raise RuntimeError(f"Camera is disconnected: {camera_id}")

            backend = self._backends.get(info.backend)

            if backend is None:
                raise RuntimeError(
                    f"No backend registered for camera: {camera_id}"
                )

            device = backend.open(camera_id)
            self._devices[camera_id] = device

            return device

    def get_device(self, camera_id: str) -> CameraDevice | None:
        with self._lock:
            return self._devices.get(camera_id)

    def close(self, camera_id: str) -> None:
        with self._lock:
            device = self._devices.pop(camera_id, None)

            if device is not None:
                device.close()

    def close_all(self) -> None:
        with self._lock:
            camera_ids = list(self._devices.keys())

            for camera_id in camera_ids:
                self.close(camera_id)
