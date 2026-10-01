from multicam.core.cameras import CameraManager
from multicam.backends.aravis import AravisBackend


manager = CameraManager()
manager.register_backend(AravisBackend())

cameras = manager.discover()

if not cameras:
    raise SystemExit("No Aravis cameras discovered")

camera_info = cameras[0]

print()
print("Opening:")
print(camera_info)

camera = manager.open(camera_info.id)

print()
print("Opened camera:")
print(camera.info)

print()
print("Capabilities:")

for capability in camera.get_capabilities():
    print(
        f"  {capability.id}: "
        f"{capability.value} "
        f"{capability.units or ''}"
    )

camera.start()

print()
print("Frames:")

for _ in range(10):
    frame = camera.get_frame(timeout=1.0)

    if frame is None:
        print("  timeout")
        continue

    print(
        f"  #{frame.frame_number} "
        f"{frame.width}x{frame.height} "
        f"{frame.pixel_format} "
        f"dtype={frame.image.dtype} "
        f"min={frame.image.min()} "
        f"max={frame.image.max()}"
    )

manager.close_all()
