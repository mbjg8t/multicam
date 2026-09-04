from multicam.backends.picamera2 import Picamera2Backend
from multicam.core.cameras import CameraManager
from multicam.core.provisioning import CameraProvisioningService
from multicam.platforms.raspberry_pi import RaspberryPiCameraProvisioner


def main():
    manager = CameraManager()
    manager.register_backend(Picamera2Backend())
    manager.discover()

    service = CameraProvisioningService(
        manager=manager,
        provisioner=RaspberryPiCameraProvisioner(),
    )

    snapshot = service.inspect()

    print()
    print("MULTICAM CAMERA PROVISIONING")
    print("============================")
    print(f"Platform:           {snapshot.platform}")
    print(f"Model:              {snapshot.platform_model}")
    print(f"camera_auto_detect: {snapshot.camera_auto_detect}")
    print(f"Pending changes:    {snapshot.pending_changes}")
    print(f"Reboot required:    {snapshot.reboot_required}")

    print()
    print("Configured camera overlays")
    print("--------------------------")

    if not snapshot.configured_cameras:
        print("None identified")

    for config in snapshot.configured_cameras:
        params = ", ".join(
            f"{key}={value}"
            for key, value in config.parameters.items()
        )

        print(
            f"line {config.line_number}: "
            f"{config.overlay}"
            + (f" [{params}]" if params else "")
        )

    print()
    print("Runtime cameras")
    print("---------------")

    if not snapshot.runtime_cameras:
        print("None")

    for camera in snapshot.runtime_cameras:
        print(
            f"{camera.name}: "
            f"num={camera.runtime_number} "
            f"rotation={camera.rotation} "
            f"path={camera.runtime_path}"
        )

    print()
    print("Provisioning correlation")
    print("------------------------")

    if not snapshot.entries:
        print("None")

    for entry in snapshot.entries:
        runtime_name = (
            entry.runtime.name
            if entry.runtime is not None
            else "-"
        )

        configured_name = (
            entry.configured.overlay
            if entry.configured is not None
            else "-"
        )

        port_hint = (
            entry.configured.port_hint
            if entry.configured is not None
            else None
        )

        print(
            f"{entry.status.value.upper():26} "
            f"runtime={runtime_name:12} "
            f"configured={configured_name:12} "
            f"port_hint={port_hint or '-'}"
        )

    if snapshot.errors:
        print()
        print("Errors")
        print("------")

        for error in snapshot.errors:
            print(error)


if __name__ == "__main__":
    main()
