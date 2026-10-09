import sys
from types import SimpleNamespace
from multicam.backends.picamera2.backend import Picamera2Backend


def test_uvc_is_not_picamera2(monkeypatch):
    devices = [
        {"Model": "ov64a40", "Num": 0, "Id": "/base/axi/pcie@1000120000/rp1/i2c@88000/ov64a40@36"},
        {"Model": "USB Video: USB Video", "Num": 1, "Id": "/base/axi/pcie@1000120000/rp1/usb@300000-1:1.0-534d:0021"},
    ]
    monkeypatch.setitem(sys.modules, "picamera2", SimpleNamespace(Picamera2=SimpleNamespace(global_camera_info=lambda: devices)))
    result = Picamera2Backend().discover()
    assert len(result) == 1
    assert result[0].name == "ov64a40"
