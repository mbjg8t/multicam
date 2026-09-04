from dataclasses import dataclass, field
from typing import Any
import time


@dataclass(slots=True)
class Frame:
    """
    Camera frame passed through Multicam Core.

    The core intentionally does not assume OpenCV, NumPy, Flask,
    Picamera2, Aravis, or any particular image representation.
    """

    camera_id: str
    image: Any

    timestamp_ns: int = field(default_factory=time.time_ns)

    width: int | None = None
    height: int | None = None

    pixel_format: str | None = None
    bit_depth: int | None = None

    frame_number: int | None = None

    metadata: dict[str, Any] = field(default_factory=dict)
