from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProvisioningStatus(str, Enum):
    READY = "ready"
    DETECTED_NOT_CONFIGURED = "detected_not_configured"
    CONFIGURED_NOT_DETECTED = "configured_not_detected"
    CONFIG_CHANGE_PENDING = "config_change_pending"
    REBOOT_REQUIRED = "reboot_required"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class ConfiguredCamera:
    """
    Platform-level camera configuration.

    This describes how the operating system/platform is configured to
    expose a camera. It is intentionally separate from CameraInfo, which
    describes a camera discovered at runtime.
    """

    overlay: str
    parameters: dict[str, str | bool] = field(default_factory=dict)
    source_line: str | None = None
    line_number: int | None = None

    @property
    def port_hint(self) -> str | None:
        """
        Return an explicitly configured Pi camera port hint when present.

        Important:
        Absence of a hint does NOT imply a particular physical CSI port.
        """
        for key in ("cam0", "cam1"):
            if key in self.parameters:
                return key

        return None


@dataclass(slots=True)
class RuntimeCamera:
    """
    Runtime camera information relevant to platform provisioning.

    runtime_id remains separate from platform configuration identity.
    """

    runtime_id: str
    backend: str
    name: str
    model: str | None = None
    connected: bool = True

    runtime_number: int | None = None
    runtime_path: str | None = None
    rotation: int | None = None

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CameraProvisioningEntry:
    """
    Correlation between runtime discovery and platform configuration.

    Either side may be absent.
    """

    status: ProvisioningStatus

    runtime: RuntimeCamera | None = None
    configured: ConfiguredCamera | None = None

    message: str | None = None


@dataclass(slots=True)
class ProvisioningChange:
    """
    Proposed platform configuration change.

    This describes what Multicam believes should change without applying
    the change. Platform-specific code determines the actual operation.
    """

    action: str
    description: str

    overlay: str | None = None
    parameters: dict[str, str | bool] = field(default_factory=dict)

    reboot_required: bool = False


@dataclass(slots=True)
class ProvisioningSnapshot:
    platform: str
    platform_model: str | None

    camera_auto_detect: bool | None

    configured_cameras: list[ConfiguredCamera] = field(default_factory=list)
    runtime_cameras: list[RuntimeCamera] = field(default_factory=list)
    entries: list[CameraProvisioningEntry] = field(default_factory=list)

    all_overlays: list[ConfiguredCamera] = field(default_factory=list)

    proposed_changes: list[ProvisioningChange] = field(default_factory=list)

    reboot_required: bool = False
    pending_changes: bool = False

    errors: list[str] = field(default_factory=list)
