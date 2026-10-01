from multicam.core.cameras import CameraManager
from multicam.backends.picamera2 import Picamera2Backend


manager = CameraManager()
manager.register_backend(Picamera2Backend())

cameras = manager.discover()

if not cameras:
    raise SystemExit("No Picamera2 cameras discovered")

info = cameras[0]

print()
print("Opening:")
print(info)

camera = manager.open(info.id)

print()
print("Capabilities:")

for capability in camera.get_capabilities():
    print(
        f"  {capability.id}: "
        f"default={capability.value} "
        f"range={capability.minimum}..{capability.maximum} "
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
        f"shape={frame.image.shape} "
        f"min={frame.image.min()} "
        f"max={frame.image.max()}"
    )

manager.close_all()
