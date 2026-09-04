from __future__ import annotations

from abc import ABC, abstractmethod

from multicam.core.cameras import CameraManager

from .model import ProvisioningSnapshot


class CameraProvisioner(ABC):
    """
    Platform adapter for camera hardware provisioning.

    Implementations may understand platform-specific concepts such as
    Raspberry Pi dtoverlays or Jetson device-tree configuration.

    Generic Multicam code must not contain those platform details.
    """

    @abstractmethod
    def inspect(self, manager: CameraManager) -> ProvisioningSnapshot:
        raise NotImplementedError


class CameraProvisioningService:
    """
    Shared application service for platform camera provisioning.

    UI/tools consume this service rather than directly reading boot files
    or executing platform-specific configuration logic.
    """

    def __init__(
        self,
        manager: CameraManager,
        provisioner: CameraProvisioner,
    ):
        self._manager = manager
        self._provisioner = provisioner

    def inspect(self) -> ProvisioningSnapshot:
        return self._provisioner.inspect(self._manager)
