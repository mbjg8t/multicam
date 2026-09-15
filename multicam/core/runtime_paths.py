from __future__ import annotations

import os
from pathlib import Path


def config_directory() -> Path:
    """Return the writable Multicam configuration directory."""

    configured = os.environ.get("MULTICAM_CONFIG_DIR")

    if configured:
        return Path(configured).expanduser()

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")

    if xdg_config_home:
        return Path(xdg_config_home).expanduser() / "multicam"

    return Path.home() / ".config" / "multicam"
