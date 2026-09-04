import time
from pathlib import Path

from PIL import Image

from multicam.core.cameras import CameraManager, FrameBroker
from multicam.core.imaging import Compositor
from multicam.core.state import OverlayLayer, ViewState
from multicam.backends.picamera2 import Picamera2Backend
from multicam.backends.aravis import AravisBackend


manager = CameraManager()
manager.register_backend(Picamera2Backend())
manager.register_backend(AravisBackend())

cameras = manager.discover()

picam = next(
    (c for c in cameras if c.backend == "picamera2"),
    None,
)

xenics = next(
    (c for c in cameras if c.backend == "aravis"),
    None,
)

if picam is None:
    raise SystemExit("No Picamera2 camera found")

if xenics is None:
    raise SystemExit("No Aravis/Xenics camera found")

print()
print("Base:")
print(f"  {picam.id}")

print()
print("Overlay:")
print(f"  {xenics.id}")

broker = FrameBroker()

for info in (picam, xenics):
    broker.add_camera(
        manager.open(info.id)
    )

broker.start_all()

print()
print("Waiting for frames...")

deadline = time.time() + 10.0

while time.time() < deadline:
    base_frame = broker.get_latest(picam.id)
    overlay_frame = broker.get_latest(xenics.id)

    if (
        base_frame is not None
        and overlay_frame is not None
    ):
        break

    time.sleep(0.05)
else:
    broker.stop_all()
    manager.close_all()
    raise SystemExit("Timed out waiting for both cameras")

frames = {
    picam.id: base_frame,
    xenics.id: overlay_frame,
}

state = ViewState(
    base_camera_id=picam.id,
    overlays=[
        OverlayLayer(
            camera_id=xenics.id,
            opacity=0.50,
            z_order=0,
        )
    ],
)

output = Compositor().compose(
    frames,
    state,
)

if output is None:
    raise SystemExit("Compositor returned no image")

output_dir = Path("output")
output_dir.mkdir(exist_ok=True)

output_path = output_dir / "multicam_fused_test.jpg"

Image.fromarray(output).save(
    output_path,
    quality=95,
)

print()
print(f"Saved: {output_path}")
print(f"Shape: {output.shape}")
print(f"dtype: {output.dtype}")

broker.stop_all()
manager.close_all()

print()
print("Stopped cleanly.")
