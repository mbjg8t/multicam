from __future__ import annotations

import json
from pathlib import Path
from threading import RLock

from multicam.core.runtime_paths import config_directory
from multicam.core.state import CameraOrientation


class CameraOrientationStore:
    """Persistent camera presentation orientation keyed by camera ID."""

    def __init__(self, path: Path | None = None):
        self.path = (
            Path(path)
            if path is not None
            else config_directory() / "camera_orientations.json"
        )
        self._lock = RLock()
        self._orientations = self._load()

    def get(self, camera_id: str) -> CameraOrientation:
        with self._lock:
            return self._orientations.get(
                camera_id,
                CameraOrientation(),
            )

    def snapshot(self) -> dict[str, CameraOrientation]:
        with self._lock:
            return dict(self._orientations)

    def set(
        self,
        camera_id: str,
        orientation: CameraOrientation,
    ) -> CameraOrientation:
        with self._lock:
            self._orientations[camera_id] = orientation
            self._save()
            return orientation

    def _load(self) -> dict[str, CameraOrientation]:
        if not self.path.exists():
            return {}

        try:
            raw = json.loads(self.path.read_text())
        except (OSError, ValueError, TypeError):
            return {}

        if not isinstance(raw, dict):
            return {}

        result: dict[str, CameraOrientation] = {}

        for camera_id, value in raw.items():
            if not isinstance(camera_id, str) or not isinstance(value, dict):
                continue

            try:
                result[camera_id] = CameraOrientation(
                    rotation_deg=int(value.get("rotation_deg", 0)),
                    flip_horizontal=bool(value.get("flip_horizontal", False)),
                    flip_vertical=bool(value.get("flip_vertical", False)),
                )
            except (TypeError, ValueError):
                continue

        return result

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        raw = {
            camera_id: orientation.as_dict()
            for camera_id, orientation in self._orientations.items()
        }
        temporary.write_text(
            json.dumps(raw, indent=2, sort_keys=True) + "\n"
        )
        temporary.replace(self.path)
