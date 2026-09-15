from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from multicam.core.runtime_paths import config_directory


class CameraProfileStore:
    """JSON camera profiles stored outside the source repository."""

    def __init__(self, directory: Path | None = None):
        self.directory = (
            Path(directory)
            if directory is not None
            else config_directory() / "camera_profiles"
        )

    @staticmethod
    def filename(name: str) -> str:
        safe = re.sub(
            r"[^A-Za-z0-9._ -]+",
            "_",
            name.strip(),
        ).strip(" .")

        if not safe:
            raise ValueError("Profile name is required")

        return safe + ".json"

    def path(self, name: str) -> Path:
        return self.directory / self.filename(name)

    def list_profiles(
        self,
    ) -> tuple[list[dict[str, Any]], list[tuple[Path, Exception]]]:
        self.directory.mkdir(parents=True, exist_ok=True)

        profiles: list[dict[str, Any]] = []
        errors: list[tuple[Path, Exception]] = []

        for path in sorted(self.directory.glob("*.json")):
            try:
                profile = json.loads(path.read_text())

                if not isinstance(profile, dict):
                    raise ValueError("Profile must contain a JSON object")

                profiles.append({
                    "name": profile.get("name", path.stem),
                    "camera": profile.get("camera", {}),
                    "controls": profile.get("controls", {}),
                })
            except (OSError, ValueError, TypeError) as exc:
                errors.append((path, exc))

        return profiles, errors

    def load(self, name: str) -> dict[str, Any]:
        profile = json.loads(self.path(name).read_text())

        if not isinstance(profile, dict):
            raise ValueError("Profile must contain a JSON object")

        return profile

    def save(self, name: str, profile: dict[str, Any]) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path(name)
        temporary = path.with_suffix(path.suffix + ".tmp")

        temporary.write_text(
            json.dumps(profile, indent=2, sort_keys=True) + "\n"
        )
        temporary.replace(path)

        return path

    def delete(self, name: str) -> bool:
        path = self.path(name)

        if not path.exists():
            return False

        path.unlink()
        return True
