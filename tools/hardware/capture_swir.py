from pathlib import Path
import numpy as np
from PIL import Image

from multicam.core.cameras import CameraManager
from multicam.backends.aravis import AravisBackend


manager = CameraManager()
manager.register_backend(AravisBackend())

cameras = manager.discover()

swir = next(
    (camera for camera in cameras if camera.backend == "aravis"),
    None,
)

if swir is None:
    raise SystemExit("No Aravis/SWIR camera found")

print()
print("SWIR camera:")
print(swir)

camera = manager.open(swir.id)
camera.start()

frame = camera.get_frame(timeout=2.0)

if frame is None:
    camera.stop()
    manager.close_all()
    raise SystemExit("No SWIR frame received")

print()
print(f"Resolution:   {frame.width}x{frame.height}")
print(f"Format:       {frame.pixel_format}")
print(f"dtype:        {frame.image.dtype}")
print(f"min:          {frame.image.min()}")
print(f"max:          {frame.image.max()}")

raw = frame.image

minimum = int(raw.min())
maximum = int(raw.max())

if maximum > minimum:
    display = (
        (raw.astype(np.float32) - minimum)
        * (255.0 / (maximum - minimum))
    ).clip(0, 255).astype(np.uint8)
else:
    display = np.zeros_like(raw, dtype=np.uint8)

output_dir = Path("output")
output_dir.mkdir(exist_ok=True)

output_path = output_dir / "swir_test.jpg"

Image.fromarray(display).save(output_path, quality=95)

print()
print(f"Saved: {output_path}")

camera.stop()
manager.close_all()

print("Stopped cleanly.")
