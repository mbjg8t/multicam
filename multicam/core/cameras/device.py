from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CameraInfo:
    """
    Stable description of a discovered camera.
    """

    id: str
    backend: str

    name: str
    model: str | None = None
    vendor: str | None = None
    serial: str | None = None

    connected: bool = True

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CameraCapability:
    """
    Description of one camera control or capability.

    Examples:
        exposure
        gain
        pixel_format
        cooling
        nuc
        roi
        autofocus
    """

    id: str
    name: str

    type: str

    readable: bool = True
    writable: bool = False

    value: Any = None

    minimum: Any = None
    maximum: Any = None
    step: Any = None

    choices: list[Any] | None = None

    units: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)
