from abc import ABC, abstractmethod

from .device import CameraInfo, CameraCapability
from .frame import Frame


class CameraDevice(ABC):
    """
    Open camera instance owned by CameraManager.

    UI code and tools must not directly instantiate camera hardware.
    """

    def __init__(self, info: CameraInfo):
        self.info = info

    @property
    def id(self) -> str:
        return self.info.id

    @abstractmethod
    def start(self) -> None:
        """Start camera acquisition."""
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        """Stop camera acquisition."""
        raise NotImplementedError

    @abstractmethod
    def get_frame(self, timeout: float | None = None) -> Frame | None:
        """Return the next available frame."""
        raise NotImplementedError

    @abstractmethod
    def get_capabilities(self) -> list[CameraCapability]:
        """Return controls/features exposed by this camera."""
        raise NotImplementedError

    @abstractmethod
    def get_control(self, control_id: str):
        """Read a camera control."""
        raise NotImplementedError

    @abstractmethod
    def set_control(self, control_id: str, value):
        """Change a camera control."""
        raise NotImplementedError

    def close(self) -> None:
        """
        Release the camera.

        Backends may override this if close requires more than stop().
        """
        self.stop()


class CameraBackend(ABC):
    """
    Hardware/API adapter.

    Examples:
        Picamera2Backend
        AravisBackend
        BosonBackend
        V4L2Backend
    """

    name: str

    @abstractmethod
    def discover(self) -> list[CameraInfo]:
        """Discover cameras available through this backend."""
        raise NotImplementedError

    @abstractmethod
    def open(self, camera_id: str) -> CameraDevice:
        """Open one discovered camera."""
        raise NotImplementedError
