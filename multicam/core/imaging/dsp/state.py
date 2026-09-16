from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from threading import RLock


@dataclass(frozen=True, slots=True)
class DspConfig:
    enabled: bool = False
    black_percentile: float = 0.0
    white_percentile: float = 100.0
    gamma: float = 1.0
    denoise_radius: int = 0
    sharpen: float = 0.0
    grayscale: bool = False
    invert: bool = False
    palette: str = "normal"
    max_fps: float = 15.0
    revision: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


class DspPipelineStore:
    def __init__(self):
        self._configs: dict[str, DspConfig] = {}
        self._lock = RLock()

    def get(self, camera_id: str) -> DspConfig:
        with self._lock:
            return self._configs.get(camera_id, DspConfig())

    def snapshot(self) -> dict[str, DspConfig]:
        with self._lock:
            return dict(self._configs)

    def update(self, camera_id: str, **changes) -> DspConfig:
        allowed = {
            "enabled",
            "black_percentile",
            "white_percentile",
            "gamma",
            "denoise_radius",
            "sharpen",
            "grayscale",
            "invert",
            "palette",
            "max_fps",
        }
        unknown = set(changes) - allowed

        if unknown:
            raise ValueError(
                f"Unknown DSP setting(s): {', '.join(sorted(unknown))}"
            )

        with self._lock:
            current = self._configs.get(camera_id, DspConfig())
            values = current.as_dict()
            values.update(changes)
            values["revision"] = current.revision + 1
            config = DspConfig(**values)
            self._validate(config)
            self._configs[camera_id] = config
            return replace(config)

    @staticmethod
    def _validate(config: DspConfig) -> None:
        if not 0.0 <= config.black_percentile <= 25.0:
            raise ValueError("Black percentile must be between 0 and 25")
        if not 75.0 <= config.white_percentile <= 100.0:
            raise ValueError("White percentile must be between 75 and 100")
        if config.black_percentile >= config.white_percentile:
            raise ValueError("Black percentile must be below white percentile")
        if not 0.1 <= config.gamma <= 4.0:
            raise ValueError("Gamma must be between 0.1 and 4.0")
        if config.denoise_radius not in (0, 1, 2, 3):
            raise ValueError("Denoise radius must be 0, 1, 2, or 3")
        if not 0.0 <= config.sharpen <= 3.0:
            raise ValueError("Sharpen must be between 0 and 3")
        if config.palette not in ("normal", "grayscale", "iron"):
            raise ValueError("Unsupported DSP palette")
        if not 1.0 <= config.max_fps <= 60.0:
            raise ValueError("DSP maximum FPS must be between 1 and 60")
