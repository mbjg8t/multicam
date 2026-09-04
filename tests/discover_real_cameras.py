from multicam.core.cameras import CameraManager
from multicam.backends.picamera2 import Picamera2Backend
from multicam.backends.aravis import AravisBackend


manager = CameraManager()

manager.register_backend(Picamera2Backend())
manager.register_backend(AravisBackend())

cameras = manager.discover()

print()
print("Discovered cameras")
print("==================")

for camera in cameras:
    print()
    print(f"ID:        {camera.id}")
    print(f"Backend:   {camera.backend}")
    print(f"Name:      {camera.name}")
    print(f"Vendor:    {camera.vendor}")
    print(f"Model:     {camera.model}")
    print(f"Serial:    {camera.serial}")
    print(f"Connected: {camera.connected}")

print()
print(f"Total: {len(cameras)}")
