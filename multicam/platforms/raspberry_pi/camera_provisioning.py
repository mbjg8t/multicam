from __future__ import annotations

from pathlib import Path

from multicam.core.cameras import CameraInfo, CameraManager
from multicam.core.provisioning import (
    CameraProvisioner,
    CameraProvisioningEntry,
    ConfiguredCamera,
    ProvisioningChange,
    ProvisioningSnapshot,
    ProvisioningStatus,
    RuntimeCamera,
)

from .camera_overlays import is_camera_overlay


class RaspberryPiCameraProvisioner(CameraProvisioner):
    """
    Read-only Raspberry Pi camera provisioning inspector.

    Current responsibilities:
      - identify the Pi model
      - read camera_auto_detect
      - parse dtoverlay configuration
      - inspect Picamera2/libcamera runtime cameras
      - correlate runtime camera models with configured overlays

    It intentionally does NOT modify boot configuration or reboot.
    """

    def __init__(
        self,
        config_path: str | Path = "/boot/firmware/config.txt",
        model_path: str | Path = "/proc/device-tree/model",
    ):
        self.config_path = Path(config_path)
        self.model_path = Path(model_path)

    def inspect(self, manager: CameraManager) -> ProvisioningSnapshot:
        errors: list[str] = []

        platform_model = self._read_platform_model(errors)

        (
            camera_auto_detect,
            overlays,
        ) = self._read_boot_config(errors)

        runtime_cameras = [
            self._runtime_camera(info)
            for info in manager.list_cameras()
            if info.backend == "picamera2"
        ]

        configured_cameras = self._camera_overlays(
            overlays,
            runtime_cameras,
        )

        entries = self._correlate(
            configured_cameras,
            runtime_cameras,
        )

        proposed_changes = self._propose_changes(entries)

        return ProvisioningSnapshot(
            platform="raspberry_pi",
            platform_model=platform_model,
            camera_auto_detect=camera_auto_detect,
            configured_cameras=configured_cameras,
            runtime_cameras=runtime_cameras,
            entries=entries,
            all_overlays=overlays,
            proposed_changes=proposed_changes,
            reboot_required=any(
                change.reboot_required
                for change in proposed_changes
            ),
            pending_changes=bool(proposed_changes),
            errors=errors,
        )

    def _read_platform_model(
        self,
        errors: list[str],
    ) -> str | None:
        try:
            return (
                self.model_path
                .read_bytes()
                .replace(b"\x00", b"")
                .decode(errors="replace")
                .strip()
            )
        except Exception as exc:
            errors.append(
                f"Unable to read platform model: {exc}"
            )
            return None

    def _read_boot_config(
        self,
        errors: list[str],
    ) -> tuple[bool | None, list[ConfiguredCamera]]:
        try:
            lines = self.config_path.read_text().splitlines()
        except Exception as exc:
            errors.append(
                f"Unable to read {self.config_path}: {exc}"
            )
            return None, []

        camera_auto_detect: bool | None = None
        overlays: list[ConfiguredCamera] = []

        for line_number, original_line in enumerate(lines, start=1):
            line = original_line.strip()

            if not line or line.startswith("#"):
                continue

            if line.startswith("camera_auto_detect="):
                raw_value = line.split("=", 1)[1].strip().lower()

                if raw_value in {"1", "true", "yes", "on"}:
                    camera_auto_detect = True
                elif raw_value in {"0", "false", "no", "off"}:
                    camera_auto_detect = False

                continue

            if not line.startswith("dtoverlay="):
                continue

            overlay_value = line.split("=", 1)[1].strip()

            if not overlay_value:
                continue

            parts = [
                part.strip()
                for part in overlay_value.split(",")
                if part.strip()
            ]

            if not parts:
                continue

            overlay_name = parts[0]
            parameters: dict[str, str | bool] = {}

            for part in parts[1:]:
                if "=" in part:
                    key, value = part.split("=", 1)
                    parameters[key.strip()] = value.strip()
                else:
                    parameters[part] = True

            overlays.append(
                ConfiguredCamera(
                    overlay=overlay_name,
                    parameters=parameters,
                    source_line=original_line,
                    line_number=line_number,
                )
            )

        return camera_auto_detect, overlays

    def _runtime_camera(
        self,
        info: CameraInfo,
    ) -> RuntimeCamera:
        raw_info = info.metadata.get("raw_info", {})

        runtime_path = raw_info.get("Id")

        if runtime_path is None:
            runtime_path = self._path_from_camera_id(info.id)

        return RuntimeCamera(
            runtime_id=info.id,
            backend=info.backend,
            name=info.name,
            model=info.model,
            connected=info.connected,
            runtime_number=info.metadata.get("num"),
            runtime_path=runtime_path,
            rotation=info.metadata.get("rotation"),
            metadata=dict(info.metadata),
        )

    @staticmethod
    def _path_from_camera_id(camera_id: str) -> str | None:
        prefix = "picamera2:"

        if camera_id.startswith(prefix):
            return camera_id[len(prefix):]

        return None

    def _camera_overlays(
        self,
        overlays: list[ConfiguredCamera],
        runtime_cameras: list[RuntimeCamera],
    ) -> list[ConfiguredCamera]:
        """
        Identify overlays relevant to cameras without maintaining a
        hardcoded list of Raspberry Pi sensor models.

        An overlay is considered camera-related when:
          - it is present in the Raspberry Pi camera overlay catalog,
          - its name matches a currently discovered camera model/name, or
          - it explicitly contains a cam0/cam1 parameter.

        The platform catalog allows configured-but-missing cameras to
        remain visible even when no matching runtime camera is present.
        """

        runtime_names = {
            value.lower()
            for camera in runtime_cameras
            for value in (camera.name, camera.model)
            if value
        }

        camera_overlays: list[ConfiguredCamera] = []

        for overlay in overlays:
            if is_camera_overlay(overlay.overlay):
                camera_overlays.append(overlay)
                continue

            if overlay.overlay.lower() in runtime_names:
                camera_overlays.append(overlay)
                continue

            if overlay.port_hint is not None:
                camera_overlays.append(overlay)

        return camera_overlays

    def _correlate(
        self,
        configured: list[ConfiguredCamera],
        runtime: list[RuntimeCamera],
    ) -> list[CameraProvisioningEntry]:
        entries: list[CameraProvisioningEntry] = []

        unmatched_config = list(configured)

        for camera in runtime:
            match = self._find_configuration(
                camera,
                unmatched_config,
            )

            if match is not None:
                unmatched_config.remove(match)

                entries.append(
                    CameraProvisioningEntry(
                        status=ProvisioningStatus.READY,
                        runtime=camera,
                        configured=match,
                        message=(
                            "Camera is configured and detected at runtime."
                        ),
                    )
                )
            else:
                entries.append(
                    CameraProvisioningEntry(
                        status=(
                            ProvisioningStatus.DETECTED_NOT_CONFIGURED
                        ),
                        runtime=camera,
                        configured=None,
                        message=(
                            "Camera is detected at runtime but no matching "
                            "explicit camera overlay was identified."
                        ),
                    )
                )

        for config in unmatched_config:
            entries.append(
                CameraProvisioningEntry(
                    status=ProvisioningStatus.CONFIGURED_NOT_DETECTED,
                    runtime=None,
                    configured=config,
                    message=(
                        "Camera overlay is configured but a matching "
                        "runtime camera was not detected."
                    ),
                )
            )

        return entries

    @staticmethod
    def _propose_changes(
        entries: list[CameraProvisioningEntry],
    ) -> list[ProvisioningChange]:
        changes: list[ProvisioningChange] = []

        for entry in entries:
            if (
                entry.status
                == ProvisioningStatus.DETECTED_NOT_CONFIGURED
                and entry.runtime is not None
            ):
                overlay = entry.runtime.model or entry.runtime.name

                changes.append(
                    ProvisioningChange(
                        action="add_overlay",
                        description=(
                            f"Add camera overlay for {overlay}."
                        ),
                        overlay=overlay,
                        reboot_required=True,
                    )
                )

        return changes

    @staticmethod
    def _find_configuration(
        runtime: RuntimeCamera,
        configured: list[ConfiguredCamera],
    ) -> ConfiguredCamera | None:
        names = {
            value.lower()
            for value in (runtime.name, runtime.model)
            if value
        }

        for config in configured:
            if config.overlay.lower() in names:
                return config

        return None
