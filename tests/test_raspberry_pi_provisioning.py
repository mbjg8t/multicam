from pathlib import Path

from multicam.core.cameras import CameraInfo, CameraManager
from multicam.core.provisioning import ProvisioningStatus
from multicam.platforms.raspberry_pi import (
    RaspberryPiCameraProvisioner,
)


class FakeBackend:
    name = "picamera2"

    def __init__(self, cameras):
        self._cameras = cameras

    def discover(self):
        return self._cameras

    def open(self, camera_id):
        raise NotImplementedError


def make_camera(
    camera_id: str,
    model: str,
    num: int,
    rotation: int,
):
    path = camera_id.removeprefix("picamera2:")

    return CameraInfo(
        id=camera_id,
        backend="picamera2",
        name=model,
        model=model,
        vendor="Raspberry Pi/libcamera",
        metadata={
            "num": num,
            "rotation": rotation,
            "raw_info": {
                "Model": model,
                "Num": num,
                "Rotation": rotation,
                "Id": path,
            },
        },
    )


def test_pi_provisioning_correlates_current_two_camera_case(
    tmp_path: Path,
):
    config = tmp_path / "config.txt"
    model = tmp_path / "model"

    config.write_text(
        "\n".join(
            [
                "camera_auto_detect=0",
                "dtoverlay=vc4-kms-v3d",
                "dtoverlay=dwc2,dr_mode=host",
                "dtoverlay=ov64a40",
                "dtoverlay=ov5647,cam0",
            ]
        )
    )

    model.write_bytes(b"Raspberry Pi 5 Model B Rev 1.0\x00")

    cameras = [
        make_camera(
            "picamera2:/base/test/i2c@88000/ov5647@36",
            "ov5647",
            0,
            0,
        ),
        make_camera(
            "picamera2:/base/test/i2c@80000/ov64a40@36",
            "ov64a40",
            1,
            180,
        ),
    ]

    manager = CameraManager()
    manager.register_backend(FakeBackend(cameras))
    manager.discover()

    provisioner = RaspberryPiCameraProvisioner(
        config_path=config,
        model_path=model,
    )

    snapshot = provisioner.inspect(manager)

    assert snapshot.platform == "raspberry_pi"
    assert snapshot.platform_model == "Raspberry Pi 5 Model B Rev 1.0"
    assert snapshot.camera_auto_detect is False

    assert [c.overlay for c in snapshot.configured_cameras] == [
        "ov64a40",
        "ov5647",
    ]

    statuses = {
        entry.runtime.name: entry.status
        for entry in snapshot.entries
        if entry.runtime is not None
    }

    assert statuses["ov5647"] == ProvisioningStatus.READY
    assert statuses["ov64a40"] == ProvisioningStatus.READY

    ov5647_config = next(
        config
        for config in snapshot.configured_cameras
        if config.overlay == "ov5647"
    )

    assert ov5647_config.port_hint == "cam0"

    ov64_config = next(
        config
        for config in snapshot.configured_cameras
        if config.overlay == "ov64a40"
    )

    # Critical architecture rule:
    # no explicit port means we do not invent one.
    assert ov64_config.port_hint is None


def test_runtime_camera_without_matching_overlay_is_reported(
    tmp_path: Path,
):
    config = tmp_path / "config.txt"
    model = tmp_path / "model"

    config.write_text("camera_auto_detect=0\n")
    model.write_text("Raspberry Pi 5")

    camera = make_camera(
        "picamera2:/base/test/ov5647@36",
        "ov5647",
        0,
        0,
    )

    manager = CameraManager()
    manager.register_backend(FakeBackend([camera]))
    manager.discover()

    snapshot = RaspberryPiCameraProvisioner(
        config_path=config,
        model_path=model,
    ).inspect(manager)

    assert len(snapshot.entries) == 1
    assert (
        snapshot.entries[0].status
        == ProvisioningStatus.DETECTED_NOT_CONFIGURED
    )


def test_configured_camera_not_detected(
    tmp_path: Path,
):
    config = tmp_path / "config.txt"
    model = tmp_path / "model"

    config.write_text(
        "\n".join(
            [
                "camera_auto_detect=0",
                "dtoverlay=ov5647,cam0",
            ]
        )
    )

    model.write_text("Raspberry Pi 5")

    manager = CameraManager()
    manager.register_backend(FakeBackend([]))
    manager.discover()

    snapshot = RaspberryPiCameraProvisioner(
        config_path=config,
        model_path=model,
    ).inspect(manager)

    assert len(snapshot.entries) == 1

    entry = snapshot.entries[0]

    assert (
        entry.status
        == ProvisioningStatus.CONFIGURED_NOT_DETECTED
    )
    assert entry.runtime is None
    assert entry.configured is not None
    assert entry.configured.overlay == "ov5647"
    assert entry.configured.port_hint == "cam0"


def test_detected_camera_not_configured(
    tmp_path: Path,
):
    config = tmp_path / "config.txt"
    model = tmp_path / "model"

    config.write_text(
        "\n".join(
            [
                "camera_auto_detect=0",
                "dtoverlay=vc4-kms-v3d",
            ]
        )
    )

    model.write_text("Raspberry Pi 5")

    camera = make_camera(
        "picamera2:/base/test/i2c@88000/ov5647@36",
        "ov5647",
        0,
        0,
    )

    manager = CameraManager()
    manager.register_backend(FakeBackend([camera]))
    manager.discover()

    snapshot = RaspberryPiCameraProvisioner(
        config_path=config,
        model_path=model,
    ).inspect(manager)

    assert len(snapshot.entries) == 1

    entry = snapshot.entries[0]

    assert (
        entry.status
        == ProvisioningStatus.DETECTED_NOT_CONFIGURED
    )
    assert entry.runtime is not None
    assert entry.runtime.name == "ov5647"
    assert entry.configured is None


def test_non_camera_overlays_are_not_reported_as_cameras(
    tmp_path: Path,
):
    config = tmp_path / "config.txt"
    model = tmp_path / "model"

    config.write_text(
        "\n".join(
            [
                "camera_auto_detect=0",
                "dtoverlay=vc4-kms-v3d",
                "dtoverlay=dwc2,dr_mode=host",
            ]
        )
    )

    model.write_text("Raspberry Pi 5")

    manager = CameraManager()
    manager.register_backend(FakeBackend([]))
    manager.discover()

    snapshot = RaspberryPiCameraProvisioner(
        config_path=config,
        model_path=model,
    ).inspect(manager)

    assert snapshot.configured_cameras == []
    assert snapshot.entries == []

    assert [overlay.overlay for overlay in snapshot.all_overlays] == [
        "vc4-kms-v3d",
        "dwc2",
    ]


def test_known_camera_overlay_remains_visible_when_camera_missing(
    tmp_path: Path,
):
    config = tmp_path / "config.txt"
    model = tmp_path / "model"

    config.write_text(
        "\n".join(
            [
                "camera_auto_detect=0",
                "dtoverlay=ov64a40",
            ]
        )
    )

    model.write_text("Raspberry Pi 5")

    manager = CameraManager()
    manager.register_backend(FakeBackend([]))
    manager.discover()

    snapshot = RaspberryPiCameraProvisioner(
        config_path=config,
        model_path=model,
    ).inspect(manager)

    assert len(snapshot.configured_cameras) == 1
    assert snapshot.configured_cameras[0].overlay == "ov64a40"

    assert len(snapshot.entries) == 1

    entry = snapshot.entries[0]

    assert (
        entry.status
        == ProvisioningStatus.CONFIGURED_NOT_DETECTED
    )
    assert entry.runtime is None
    assert entry.configured is not None
    assert entry.configured.overlay == "ov64a40"


def test_healthy_configuration_has_no_proposed_changes(
    tmp_path: Path,
):
    config = tmp_path / "config.txt"
    model = tmp_path / "model"

    config.write_text(
        "\n".join(
            [
                "camera_auto_detect=0",
                "dtoverlay=ov5647,cam0",
            ]
        )
    )
    model.write_text("Raspberry Pi 5")

    camera = make_camera(
        "picamera2:/base/test/i2c@88000/ov5647@36",
        "ov5647",
        0,
        0,
    )

    manager = CameraManager()
    manager.register_backend(FakeBackend([camera]))
    manager.discover()

    snapshot = RaspberryPiCameraProvisioner(
        config_path=config,
        model_path=model,
    ).inspect(manager)

    assert snapshot.proposed_changes == []
    assert snapshot.pending_changes is False
    assert snapshot.reboot_required is False


def test_detected_unconfigured_camera_proposes_overlay_only(
    tmp_path: Path,
):
    config = tmp_path / "config.txt"
    model = tmp_path / "model"
    symbols = tmp_path / "__symbols__"

    symbols.mkdir()

    config.write_text("camera_auto_detect=0\n")
    model.write_text("Raspberry Pi 5")

    (symbols / "i2c_csi_dsi0").write_bytes(
        b"/test/i2c@88000\x00"
    )
    (symbols / "i2c_csi_dsi1").write_bytes(
        b"/test/i2c@80000\x00"
    )

    camera = make_camera(
        "picamera2:/base/test/i2c@88000/ov5647@36",
        "ov5647",
        0,
        0,
    )

    manager = CameraManager()
    manager.register_backend(FakeBackend([camera]))
    manager.discover()

    snapshot = RaspberryPiCameraProvisioner(
        config_path=config,
        model_path=model,
        symbols_path=symbols,
    ).inspect(manager)

    assert len(snapshot.proposed_changes) == 1

    change = snapshot.proposed_changes[0]

    assert change.action == "add_overlay"
    assert change.overlay == "ov5647"
    assert change.parameters == {"cam0": True}
    assert change.reboot_required is True

    assert snapshot.pending_changes is True
    assert snapshot.reboot_required is True
    assert snapshot.errors == []

def test_missing_runtime_camera_does_not_propose_removing_config(
    tmp_path: Path,
):
    config = tmp_path / "config.txt"
    model = tmp_path / "model"

    config.write_text(
        "\n".join(
            [
                "camera_auto_detect=0",
                "dtoverlay=ov64a40",
            ]
        )
    )
    model.write_text("Raspberry Pi 5")

    manager = CameraManager()
    manager.register_backend(FakeBackend([]))
    manager.discover()

    snapshot = RaspberryPiCameraProvisioner(
        config_path=config,
        model_path=model,
    ).inspect(manager)

    assert snapshot.proposed_changes == []
    assert snapshot.pending_changes is False
    assert snapshot.reboot_required is False


def test_apply_add_overlay_creates_backup_and_writes_config(
    tmp_path: Path,
):
    from multicam.core.provisioning import ProvisioningChange

    config = tmp_path / "config.txt"
    model = tmp_path / "model"

    original = (
        "camera_auto_detect=0\n"
        "dtoverlay=vc4-kms-v3d\n"
        "dtoverlay=ov64a40\n"
    )

    config.write_text(original)
    model.write_text("Raspberry Pi 5")

    provisioner = RaspberryPiCameraProvisioner(
        config_path=config,
        model_path=model,
    )

    change = ProvisioningChange(
        action="add_overlay",
        description="Add camera overlay for ov5647.",
        overlay="ov5647",
        reboot_required=True,
    )

    manager = CameraManager()

    result = provisioner.apply(manager, [change])

    assert result.success is True
    assert result.applied_changes == [change]
    assert result.skipped_changes == []
    assert result.reboot_required is True
    assert result.backup_path is not None
    assert result.errors == []

    backup = Path(result.backup_path)

    assert backup.exists()
    assert backup.read_text() == original

    updated = config.read_text()

    assert "dtoverlay=ov64a40\n" in updated
    assert "dtoverlay=ov5647\n" in updated

    # Critical safety rule: no physical port is invented.
    assert "dtoverlay=ov5647,cam0" not in updated
    assert "dtoverlay=ov5647,cam1" not in updated


def test_apply_existing_overlay_is_idempotent(
    tmp_path: Path,
):
    from multicam.core.provisioning import ProvisioningChange

    config = tmp_path / "config.txt"
    model = tmp_path / "model"

    original = (
        "camera_auto_detect=0\n"
        "dtoverlay=ov5647,cam0\n"
    )

    config.write_text(original)
    model.write_text("Raspberry Pi 5")

    provisioner = RaspberryPiCameraProvisioner(
        config_path=config,
        model_path=model,
    )

    change = ProvisioningChange(
        action="add_overlay",
        description="Add camera overlay for ov5647.",
        overlay="ov5647",
        reboot_required=True,
    )

    result = provisioner.apply(
        CameraManager(),
        [change],
    )

    assert result.success is True
    assert result.applied_changes == []
    assert result.skipped_changes == [change]
    assert result.backup_path is None
    assert result.reboot_required is False

    assert config.read_text() == original


def test_apply_rejects_unsupported_action_without_writing(
    tmp_path: Path,
):
    from multicam.core.provisioning import ProvisioningChange

    config = tmp_path / "config.txt"
    model = tmp_path / "model"

    original = "camera_auto_detect=0\n"

    config.write_text(original)
    model.write_text("Raspberry Pi 5")

    provisioner = RaspberryPiCameraProvisioner(
        config_path=config,
        model_path=model,
    )

    change = ProvisioningChange(
        action="remove_overlay",
        description="Do not support this yet.",
        overlay="ov5647",
    )

    result = provisioner.apply(
        CameraManager(),
        [change],
    )

    assert result.success is False
    assert result.applied_changes == []
    assert result.backup_path is None
    assert result.errors

    assert config.read_text() == original


def test_service_apply_delegates_to_pi_provisioner(
    tmp_path: Path,
):
    from multicam.core.provisioning import (
        CameraProvisioningService,
        ProvisioningChange,
    )

    config = tmp_path / "config.txt"
    model = tmp_path / "model"

    config.write_text(
        "camera_auto_detect=0\n"
        "dtoverlay=ov64a40\n"
    )
    model.write_text("Raspberry Pi 5")

    manager = CameraManager()

    service = CameraProvisioningService(
        manager=manager,
        provisioner=RaspberryPiCameraProvisioner(
            config_path=config,
            model_path=model,
        ),
    )

    change = ProvisioningChange(
        action="add_overlay",
        description="Add camera overlay for ov5647.",
        overlay="ov5647",
        reboot_required=True,
    )

    result = service.apply([change])

    assert result.success is True
    assert result.applied_changes == [change]
    assert result.reboot_required is True
    assert result.backup_path is not None

    assert "dtoverlay=ov5647\n" in config.read_text()


def test_pi_runtime_path_resolves_cam0_from_device_tree_symbol(
    tmp_path: Path,
):
    from multicam.core.provisioning import RuntimeCamera

    symbols = tmp_path / "__symbols__"
    symbols.mkdir()

    (symbols / "i2c_csi_dsi0").write_bytes(
        b"/axi/pcie@1000120000/rp1/i2c@88000\x00"
    )
    (symbols / "i2c_csi_dsi1").write_bytes(
        b"/axi/pcie@1000120000/rp1/i2c@80000\x00"
    )

    provisioner = RaspberryPiCameraProvisioner(
        symbols_path=symbols,
    )

    runtime = RuntimeCamera(
        runtime_id="test",
        backend="picamera2",
        name="ov5647",
        model="ov5647",
        connected=True,
        runtime_number=0,
        runtime_path=(
            "/base/axi/pcie@1000120000/rp1/"
            "i2c@88000/ov5647@36"
        ),
        rotation=0,
    )

    assert provisioner._runtime_overlay_parameters(runtime) == {
        "cam0": True
    }


def test_pi_runtime_path_resolves_default_cam1(
    tmp_path: Path,
):
    from multicam.core.provisioning import RuntimeCamera

    symbols = tmp_path / "__symbols__"
    symbols.mkdir()

    (symbols / "i2c_csi_dsi0").write_bytes(
        b"/axi/pcie@1000120000/rp1/i2c@88000\x00"
    )
    (symbols / "i2c_csi_dsi1").write_bytes(
        b"/axi/pcie@1000120000/rp1/i2c@80000\x00"
    )

    provisioner = RaspberryPiCameraProvisioner(
        symbols_path=symbols,
    )

    runtime = RuntimeCamera(
        runtime_id="test",
        backend="picamera2",
        name="ov64a40",
        model="ov64a40",
        connected=True,
        runtime_number=1,
        runtime_path=(
            "/base/axi/pcie@1000120000/rp1/"
            "i2c@80000/ov64a40@36"
        ),
        rotation=180,
    )

    assert provisioner._runtime_overlay_parameters(runtime) == {}


def test_pi_runtime_path_with_unknown_connector_is_not_resolved(
    tmp_path: Path,
):
    from multicam.core.provisioning import RuntimeCamera

    symbols = tmp_path / "__symbols__"
    symbols.mkdir()

    (symbols / "i2c_csi_dsi0").write_bytes(
        b"/axi/pcie@1000120000/rp1/i2c@88000\x00"
    )
    (symbols / "i2c_csi_dsi1").write_bytes(
        b"/axi/pcie@1000120000/rp1/i2c@80000\x00"
    )

    provisioner = RaspberryPiCameraProvisioner(
        symbols_path=symbols,
    )

    runtime = RuntimeCamera(
        runtime_id="test",
        backend="picamera2",
        name="future_camera",
        model="future_camera",
        connected=True,
        runtime_number=7,
        runtime_path=(
            "/base/axi/pcie@1000120000/rp1/"
            "i2c@DEADBEEF/future_camera@36"
        ),
        rotation=0,
    )

    assert (
        provisioner._runtime_overlay_parameters(runtime)
        is None
    )
