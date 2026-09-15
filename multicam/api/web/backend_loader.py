from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass

from multicam.core.cameras import CameraManager


@dataclass(frozen=True, slots=True)
class BackendLoadResult:
    name: str
    loaded: bool
    error: str | None = None


BUILTIN_BACKENDS = (
    ("picamera2", "multicam.backends.picamera2", "Picamera2Backend"),
    ("aravis", "multicam.backends.aravis", "AravisBackend"),
)


def register_available_backends(
    manager: CameraManager,
    logger: logging.Logger,
) -> list[BackendLoadResult]:
    """Register installed hardware backends without making them mandatory."""

    results: list[BackendLoadResult] = []

    for name, module_name, class_name in BUILTIN_BACKENDS:
        try:
            module = importlib.import_module(module_name)
            backend_type = getattr(module, class_name)
            manager.register_backend(backend_type())
        except Exception as exc:
            logger.warning(
                "Camera backend %s is unavailable: %s",
                name,
                exc,
            )
            results.append(
                BackendLoadResult(
                    name=name,
                    loaded=False,
                    error=str(exc),
                )
            )
        else:
            results.append(
                BackendLoadResult(name=name, loaded=True)
            )

    return results
