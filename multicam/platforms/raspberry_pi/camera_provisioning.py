from __future__ import annotations

from pathlib import Path
import shutil
from datetime import datetime

from multicam.core.cameras import CameraInfo, CameraManager
from multicam.core.provisioning import (
    CameraPortOption,
    CameraProvisioner,
    CameraProvisioningEntry,
    ConfiguredCamera,
    ProvisioningApplyResult,
    ProvisioningChange,
    ProvisioningSnapshot,
    ProvisioningStatus,
    RuntimeCamera,
)

from .camera_overlays import is_camera_overlay
from .camera_sensors import SENSOR_BY_ID, SENSOR_DEFINITIONS


MANAGED_BEGIN = "# BEGIN MULTICAM CAMERA CONFIGURATION"
MANAGED_END = "# END MULTICAM CAMERA CONFIGURATION"


class RaspberryPiCameraProvisioner(CameraProvisioner):
    """
    Raspberry Pi camera provisioning adapter.

    Current responsibilities:
      - identify the Pi model
      - read camera_auto_detect
      - parse dtoverlay configuration
      - inspect Picamera2/libcamera runtime cameras
      - correlate runtime camera models with configured overlays

    Boot writes are exposed only through the guarded provisioning service.
    Rebooting remains outside this adapter.
    """

    def __init__(
        self,
        config_path: str | Path = "/boot/firmware/config.txt",
        model_path: str | Path = "/proc/device-tree/model",
        symbols_path: str | Path = "/proc/device-tree/__symbols__",
    ):
        self.config_path = Path(config_path)
        self.model_path = Path(model_path)
        self.symbols_path = Path(symbols_path)

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

        proposed_changes = self._propose_changes(
            entries,
            errors,
        )

        ports = self._port_options(configured_cameras, runtime_cameras)

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
            ports=ports,
            sensor_options=[sensor.as_option() for sensor in SENSOR_DEFINITIONS],
        )

    def plan_ports(
        self,
        manager: CameraManager,
        selections: dict[str, str | None],
    ) -> list[ProvisioningChange]:
        del manager

        unknown_ports = set(selections) - {"cam0", "cam1"}
        if unknown_ports:
            raise ValueError(
                "Unknown camera port(s): " + ", ".join(sorted(unknown_ports))
            )

        changes: list[ProvisioningChange] = []
        for port_id in ("cam0", "cam1"):
            sensor_id = selections.get(port_id)
            if sensor_id in (None, "", "none"):
                changes.append(ProvisioningChange(
                    action="replace_camera_configuration",
                    description=f"Configure {port_id.upper()} with no camera.",
                    reboot_required=True,
                    metadata={"port_id": port_id, "sensor_id": None},
                ))
                continue

            sensor = SENSOR_BY_ID.get(sensor_id)
            if sensor is None:
                raise ValueError(f"Unknown camera sensor selection: {sensor_id}")

            changes.append(ProvisioningChange(
                action="replace_camera_configuration",
                description=f"Configure {port_id.upper()} for {sensor.name}.",
                overlay=sensor.overlay,
                parameters=sensor.parameters_for_port(port_id),
                reboot_required=True,
                metadata={"port_id": port_id, "sensor_id": sensor_id},
            ))

        return changes

    def apply(
        self,
        manager: CameraManager,
        changes: list[ProvisioningChange],
    ) -> ProvisioningApplyResult:
        """
        Apply explicitly requested Raspberry Pi camera configuration changes.

        Safety limits:
          - selected-port changes must include both CAM0 and CAM1
          - only known sensor definitions generate managed overlay lines
          - unrelated boot configuration is preserved
          - a backup is created before modification
          - resulting configuration is verified after writing
          - reboot is never performed here
        """

        del manager  # Reserved for future validation against runtime hardware.

        if not changes:
            return ProvisioningApplyResult(
                success=True,
                reboot_required=False,
            )

        actions = {change.action for change in changes}
        if actions == {"replace_camera_configuration"}:
            return self._apply_port_configuration(changes)

        unsupported = [
            change
            for change in changes
            if change.action != "add_overlay"
        ]

        if unsupported:
            actions = ", ".join(
                sorted({change.action for change in unsupported})
            )

            return ProvisioningApplyResult(
                success=False,
                errors=[
                    f"Unsupported provisioning action(s): {actions}"
                ],
            )

        try:
            original_text = self.config_path.read_text()
        except Exception as exc:
            return ProvisioningApplyResult(
                success=False,
                errors=[
                    f"Unable to read {self.config_path}: {exc}"
                ],
            )

        existing_overlays = self._active_overlay_names(original_text)

        applied: list[ProvisioningChange] = []
        skipped: list[ProvisioningChange] = []
        lines_to_add: list[str] = []

        for change in changes:
            if not change.overlay:
                return ProvisioningApplyResult(
                    success=False,
                    errors=[
                        "add_overlay change is missing an overlay name."
                    ],
                )

            overlay_name = change.overlay.strip()

            if not overlay_name:
                return ProvisioningApplyResult(
                    success=False,
                    errors=[
                        "add_overlay change has an empty overlay name."
                    ],
                )

            if overlay_name.lower() in existing_overlays:
                skipped.append(change)
                continue

            parts = [f"dtoverlay={overlay_name}"]

            for key, value in change.parameters.items():
                if value is True:
                    parts.append(str(key))
                else:
                    parts.append(f"{key}={value}")

            lines_to_add.append(",".join(parts))
            existing_overlays.add(overlay_name.lower())
            applied.append(change)

        if not applied:
            return ProvisioningApplyResult(
                success=True,
                skipped_changes=skipped,
                reboot_required=False,
            )

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = self.config_path.with_name(
            f"{self.config_path.name}.multicam-{timestamp}.bak"
        )

        try:
            shutil.copy2(self.config_path, backup_path)
        except Exception as exc:
            return ProvisioningApplyResult(
                success=False,
                errors=[
                    f"Unable to create backup {backup_path}: {exc}"
                ],
            )

        updated_text = original_text

        if updated_text and not updated_text.endswith("\n"):
            updated_text += "\n"

        updated_text += "\n".join(lines_to_add) + "\n"

        try:
            self.config_path.write_text(updated_text)
        except Exception as exc:
            return ProvisioningApplyResult(
                success=False,
                backup_path=str(backup_path),
                errors=[
                    f"Unable to write {self.config_path}: {exc}"
                ],
            )

        try:
            verified_text = self.config_path.read_text()
            verified_overlays = self._active_overlay_names(
                verified_text
            )
        except Exception as exc:
            return ProvisioningApplyResult(
                success=False,
                applied_changes=applied,
                skipped_changes=skipped,
                backup_path=str(backup_path),
                errors=[
                    f"Unable to verify {self.config_path}: {exc}"
                ],
            )

        missing = [
            change.overlay
            for change in applied
            if (
                change.overlay is not None
                and change.overlay.lower() not in verified_overlays
            )
        ]

        if missing:
            return ProvisioningApplyResult(
                success=False,
                applied_changes=applied,
                skipped_changes=skipped,
                backup_path=str(backup_path),
                errors=[
                    "Configuration verification failed for overlay(s): "
                    + ", ".join(missing)
                ],
            )

        return ProvisioningApplyResult(
            success=True,
            applied_changes=applied,
            skipped_changes=skipped,
            backup_path=str(backup_path),
            reboot_required=any(
                change.reboot_required
                for change in applied
            ),
        )

    def _apply_port_configuration(
        self,
        changes: list[ProvisioningChange],
    ) -> ProvisioningApplyResult:
        port_changes = {
            change.metadata.get("port_id"): change
            for change in changes
        }
        if len(changes) != 2 or set(port_changes) != {"cam0", "cam1"}:
            return ProvisioningApplyResult(
                success=False,
                errors=["A complete CAM0 and CAM1 selection is required."],
            )

        for port_id, change in port_changes.items():
            sensor_id = change.metadata.get("sensor_id")
            if sensor_id is None:
                valid = change.overlay is None and not change.parameters
            else:
                sensor = SENSOR_BY_ID.get(sensor_id)
                valid = bool(
                    sensor
                    and change.overlay == sensor.overlay
                    and change.parameters == sensor.parameters_for_port(port_id)
                )
            if not valid:
                return ProvisioningApplyResult(
                    success=False,
                    errors=[
                        f"Invalid or stale camera plan for {port_id.upper()}."
                    ],
                )

        try:
            original_text = self.config_path.read_text()
        except Exception as exc:
            return ProvisioningApplyResult(
                success=False,
                errors=[f"Unable to read {self.config_path}: {exc}"],
            )

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = self.config_path.with_name(
            f"{self.config_path.name}.multicam-{timestamp}.bak"
        )
        try:
            shutil.copy2(self.config_path, backup_path)
            updated = self._replace_managed_camera_configuration(
                original_text,
                [port_changes["cam0"], port_changes["cam1"]],
            )
            self.config_path.write_text(updated)
            verified = self.config_path.read_text()
        except Exception as exc:
            return ProvisioningApplyResult(
                success=False,
                backup_path=str(backup_path) if backup_path.exists() else None,
                errors=[f"Unable to update {self.config_path}: {exc}"],
            )

        expected_lines = {
            self._overlay_line(change)
            for change in changes
            if change.overlay
        }
        if not expected_lines.issubset(set(verified.splitlines())):
            return ProvisioningApplyResult(
                success=False,
                applied_changes=changes,
                backup_path=str(backup_path),
                errors=["Managed camera configuration verification failed."],
            )

        return ProvisioningApplyResult(
            success=True,
            applied_changes=changes,
            backup_path=str(backup_path),
            reboot_required=True,
        )

    def _replace_managed_camera_configuration(
        self,
        text: str,
        changes: list[ProvisioningChange],
    ) -> str:
        output: list[str] = []
        inside_managed = False

        for original_line in text.splitlines():
            stripped = original_line.strip()
            if stripped == MANAGED_BEGIN:
                inside_managed = True
                continue
            if stripped == MANAGED_END:
                inside_managed = False
                continue
            if inside_managed:
                continue

            if stripped.startswith("camera_auto_detect="):
                continue

            if stripped.startswith("dtoverlay="):
                overlay = stripped.split("=", 1)[1].split(",", 1)[0].strip()
                if is_camera_overlay(overlay):
                    output.append(f"# multicam-replaced: {stripped}")
                    continue

            output.append(original_line)

        while output and not output[-1].strip():
            output.pop()

        # Re-enter the global section so a preceding board-specific section
        # cannot accidentally scope the generated camera configuration.
        output.extend(["", "[all]", MANAGED_BEGIN, "camera_auto_detect=0"])
        output.extend(
            self._overlay_line(change)
            for change in changes
            if change.overlay
        )
        output.append(MANAGED_END)
        return "\n".join(output) + "\n"

    @staticmethod
    def _overlay_line(change: ProvisioningChange) -> str:
        parts = [f"dtoverlay={change.overlay}"]
        for key, value in change.parameters.items():
            parts.append(str(key) if value is True else f"{key}={value}")
        return ",".join(parts)

    def _port_options(
        self,
        configured: list[ConfiguredCamera],
        runtime: list[RuntimeCamera],
    ) -> list[CameraPortOption]:
        results: list[CameraPortOption] = []
        for port_id, description in (
            ("cam0", "Board connector labelled CAM/DISP0"),
            ("cam1", "Board connector labelled CAM/DISP1"),
        ):
            config = next(
                (item for item in configured if self._configuration_port(item) == port_id),
                None,
            )
            camera = next(
                (item for item in runtime if self._runtime_port(item) == port_id),
                None,
            )
            sensor_id = self._sensor_id_for_configuration(config)
            results.append(CameraPortOption(
                id=port_id,
                name=port_id.upper(),
                description=description,
                selected_sensor_id=sensor_id,
                runtime_model=camera.model if camera else None,
                runtime_path=camera.runtime_path if camera else None,
            ))
        return results

    @staticmethod
    def _configuration_port(config: ConfiguredCamera) -> str:
        return config.port_hint or "cam1"

    def _runtime_port(self, runtime: RuntimeCamera) -> str | None:
        parameters = self._runtime_overlay_parameters(runtime)
        if parameters is None:
            return None
        return "cam0" if parameters.get("cam0") is True else "cam1"

    @staticmethod
    def _sensor_id_for_configuration(
        config: ConfiguredCamera | None,
    ) -> str | None:
        if config is None:
            return None
        candidates = [
            sensor for sensor in SENSOR_DEFINITIONS
            if sensor.overlay == config.overlay.lower()
        ]
        if config.overlay.lower() == "imx519":
            return (
                "imx519_manual"
                if config.parameters.get("vcm") == "off"
                else "imx519_af"
            )
        return candidates[0].id if candidates else None

    @staticmethod
    def _active_overlay_names(text: str) -> set[str]:
        names: set[str] = set()

        for original_line in text.splitlines():
            line = original_line.strip()

            if not line or line.startswith("#"):
                continue

            if not line.startswith("dtoverlay="):
                continue

            value = line.split("=", 1)[1].strip()

            if not value:
                continue

            name = value.split(",", 1)[0].strip()

            if name:
                names.add(name.lower())

        return names

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

    def _propose_changes(
        self,
        entries: list[CameraProvisioningEntry],
        errors: list[str],
    ) -> list[ProvisioningChange]:
        changes: list[ProvisioningChange] = []

        for entry in entries:
            if (
                entry.status
                != ProvisioningStatus.DETECTED_NOT_CONFIGURED
                or entry.runtime is None
            ):
                continue

            overlay = entry.runtime.model or entry.runtime.name
            parameters = self._runtime_overlay_parameters(
                entry.runtime,
            )

            if parameters is None:
                errors.append(
                    "Unable to determine Raspberry Pi camera connector "
                    f"for {overlay}; no automatic configuration change "
                    "was proposed."
                )
                continue

            changes.append(
                ProvisioningChange(
                    action="add_overlay",
                    description=(
                        f"Add camera overlay for {overlay}."
                    ),
                    overlay=overlay,
                    parameters=parameters,
                    reboot_required=True,
                )
            )

        return changes

    def _runtime_overlay_parameters(
        self,
        runtime: RuntimeCamera,
    ) -> dict[str, object] | None:
        """
        Resolve a libcamera runtime path to Raspberry Pi overlay parameters.

        Raspberry Pi camera overlays use CAM1 by default. The explicit
        ``cam0`` parameter redirects the overlay to CAM0.

        The mapping is derived from the live device-tree symbols rather
        than Picamera2 runtime numbering.
        """

        runtime_path = runtime.runtime_path

        if not runtime_path:
            return None

        cam0_path = self._read_dt_symbol("i2c_csi_dsi0")
        cam1_path = self._read_dt_symbol("i2c_csi_dsi1")

        if cam0_path and self._path_is_within(
            runtime_path,
            cam0_path,
        ):
            return {"cam0": True}

        if cam1_path and self._path_is_within(
            runtime_path,
            cam1_path,
        ):
            return {}

        return None

    def _read_dt_symbol(self, name: str) -> str | None:
        path = self.symbols_path / name

        try:
            value = path.read_bytes().rstrip(b"\x00").decode()
        except (OSError, UnicodeDecodeError):
            return None

        return value or None

    @staticmethod
    def _path_is_within(
        runtime_path: str,
        parent_path: str,
    ) -> bool:
        def normalize(value: str) -> str:
            value = value.rstrip("/")

            # libcamera currently reports paths rooted at /base while
            # device-tree __symbols__ paths are rooted directly at /.
            # They refer to the same live device-tree hierarchy.
            if value.startswith("/base/"):
                value = value[len("/base"):]

            return value

        runtime = normalize(runtime_path)
        parent = normalize(parent_path)

        return (
            runtime == parent
            or runtime.startswith(parent + "/")
        )

    def _find_configuration(
        self,
        runtime: RuntimeCamera,
        configured: list[ConfiguredCamera],
    ) -> ConfiguredCamera | None:
        names = {
            value.lower()
            for value in (runtime.name, runtime.model)
            if value
        }

        name_matches = [
            config
            for config in configured
            if config.overlay.lower() in names
        ]

        runtime_port = self._runtime_port(runtime)
        if runtime_port is not None:
            for config in name_matches:
                if self._configuration_port(config) == runtime_port:
                    return config

        # Topology may be unavailable on a non-Pi development host. A model
        # match remains useful there, but physical-port identity always wins
        # when the live device tree can resolve it.
        if name_matches:
            return name_matches[0]

        return None
