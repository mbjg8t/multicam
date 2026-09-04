import time

from multicam.core.cameras import CameraManager, FrameBroker
from multicam.backends.picamera2 import Picamera2Backend
from multicam.backends.aravis import AravisBackend


manager = CameraManager()
manager.register_backend(Picamera2Backend())
manager.register_backend(AravisBackend())

cameras = manager.discover()

print()
print("Discovered:")
for info in cameras:
    print(f"  {info.backend:10} {info.id}")

broker = FrameBroker()

for info in cameras:
    device = manager.open(info.id)
    broker.add_camera(device)

print()
print("Starting all cameras...")
broker.start_all()

deadline = time.time() + 10

while time.time() < deadline:
    ready = True

    for info in cameras:
        frame = broker.get_latest(info.id)

        if frame is None:
            ready = False
            continue

        state = broker.get_state(info.id)

        print(
            f"{info.backend:10} "
            f"frame={frame.frame_number:<5} "
            f"{frame.width}x{frame.height} "
            f"{frame.pixel_format:<8} "
            f"count={state.frame_count}"
        )

    if ready:
        break

    time.sleep(0.25)

print()
print("Running simultaneously for 3 seconds...")
time.sleep(3)

print()
print("Final states:")

for info in cameras:
    frame = broker.get_latest(info.id)
    state = broker.get_state(info.id)

    print()
    print(f"Camera: {info.id}")
    print(f"  running:     {state.running}")
    print(f"  frame_count: {state.frame_count}")
    print(f"  last_error:  {state.last_error}")

    if frame is not None:
        print(
            f"  latest:      "
            f"#{frame.frame_number} "
            f"{frame.width}x{frame.height} "
            f"{frame.pixel_format} "
            f"dtype={frame.image.dtype}"
        )

broker.stop_all()
manager.close_all()

print()
print("Stopped cleanly.")
