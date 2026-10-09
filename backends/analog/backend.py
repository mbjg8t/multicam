"""Generic USB UVC analog capture devices (initially MacroSilicon 534d:0021)."""
from __future__ import annotations
import re
import subprocess
import time
from pathlib import Path
from typing import Any
from multicam.core.cameras import CameraBackend, CameraCapability, CameraDevice, CameraInfo, Frame


def _run(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)


def _modes(text):
    modes = []
    fmt = None
    size = None
    for line in text.splitlines():
        m = re.search(r"\[\d+\]:\s*'([A-Z0-9]{4})'", line)
        if m:
            fmt, size = m.group(1), None
        m = re.search(r"Size:\s*Discrete\s+(\d+)x(\d+)", line)
        if m:
            size = (int(m.group(1)), int(m.group(2)))
        m = re.search(r"\((\d+(?:\.\d+)?)\s+fps\)", line)
        if m and fmt and size:
            modes.append((fmt, *size, float(m.group(1))))
    return modes


class AnalogDevice(CameraDevice):
    def __init__(self, info, cv2_module=None):
        super().__init__(info)
        self.cv2 = cv2_module
        self.capture = None
        self.count = 0
        self.mode = tuple(info.metadata['default_mode'])

    def _opencv(self):
        if self.cv2 is None:
            import cv2
            self.cv2 = cv2
        return self.cv2

    def start(self):
        if self.capture is not None:
            return
        cv2 = self._opencv()
        path = self.info.metadata['device_path']
        cap = cv2.VideoCapture(path, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(f'Cannot open analog UVC capture device {path}')
        fmt, width, height, fps = self.mode
        try:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fmt))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, fps)
            actual = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            if actual != (width, height):
                raise RuntimeError(f'Analog UVC requested {width}x{height} but negotiated {actual}')
        except Exception:
            cap.release()
            raise
        self.capture = cap

    def stop(self):
        cap, self.capture = self.capture, None
        if cap is not None:
            cap.release()

    @property
    def calibration_capture_uses_live_frame(self):
        return True

    def get_frame(self, timeout=None):
        del timeout
        if self.capture is None:
            return None
        ok, bgr = self.capture.read()
        if not ok or bgr is None:
            return None
        rgb = self._opencv().cvtColor(bgr, self._opencv().COLOR_BGR2RGB)
        self.count += 1
        height, width = rgb.shape[:2]
        return Frame(camera_id=self.id, image=rgb, width=width, height=height,
                     pixel_format='RGB888', bit_depth=8, frame_number=self.count,
                     timestamp_ns=time.time_ns(), monotonic_timestamp_ns=time.monotonic_ns(),
                     metadata={'source':'USB analog capture', 'device_path':self.info.metadata['device_path'],
                               'input_format':self.mode[0], 'capture_quality':'selected_acquisition_mode',
                               'mode':list(self.mode)})

    def get_capabilities(self):
        return [CameraCapability(id='mode', name='Capture mode', type='enum',
                value=self.get_control('mode'), choices=[self._label(x) for x in self.info.metadata['modes']],
                metadata={'restart_required':True})]

    @staticmethod
    def _label(mode):
        fmt, w, h, fps = mode
        return f'{w}x{h} @ {fps:g} fps ({fmt})'

    def get_control(self, control_id):
        if control_id != 'mode':
            raise KeyError(control_id)
        return self._label(self.mode)

    def set_control(self, control_id, value):
        if control_id != 'mode':
            raise KeyError(control_id)
        options = {self._label(x):tuple(x) for x in self.info.metadata['modes']}
        if value not in options:
            raise ValueError(f'Unsupported capture mode: {value}')
        was_running = self.capture is not None
        old = self.mode
        if was_running:
            self.stop()
        self.mode = options[value]
        if was_running:
            try:
                self.start()
            except Exception:
                self.mode = old
                self.start()
                raise
        return value


class AnalogBackend(CameraBackend):
    name = 'analog'
    def __init__(self, runner=_run, sys_video='/sys/class/video4linux'):
        self.runner, self.sys_video = runner, Path(sys_video)
        self.cameras = {}

    def discover(self):
        found = {}
        for node in sorted(self.sys_video.glob('video*')):
            device_path = '/dev/' + node.name
            try:
                props = self.runner(['udevadm','info','--query=property','--name='+device_path]).stdout
                values = dict(line.split('=',1) for line in props.splitlines() if '=' in line)
                if (values.get('ID_VENDOR_ID','').lower(), values.get('ID_MODEL_ID','').lower()) != ('534d','0021'):
                    continue
                if ':capture:' not in values.get('ID_V4L_CAPABILITIES',''):
                    continue
                modes = _modes(self.runner(['v4l2-ctl','-d',device_path,'--list-formats-ext']).stdout)
                if not modes:
                    continue
                # Prefer native SD YUYV, avoiding MJPG scaling advertised by the adapter.
                preferred = next((m for m in modes if m[:3] == ('YUYV',720,480) and m[3] == 30), None)
                preferred = preferred or next((m for m in modes if m[:3] == ('YUYV',720,576) and m[3] == 25), None)
                preferred = preferred or modes[0]
                identity = values.get('ID_PATH_TAG') or values.get('ID_PATH') or node.name
                camera_id = 'analog:' + re.sub(r'[^A-Za-z0-9_.-]', '_', identity)
                found[camera_id] = CameraInfo(id=camera_id, backend=self.name,
                    name='USB Analog Capture', model='MacroSilicon 534d:0021', vendor='MacroSilicon',
                    serial=values.get('ID_SERIAL_SHORT'), metadata={'device_path':device_path,
                        'physical_path':values.get('ID_PATH'), 'modes':modes,'default_mode':preferred})
            except (OSError, subprocess.SubprocessError):
                continue
        self.cameras = found
        return list(found.values())

    def open(self, camera_id):
        return AnalogDevice(self.cameras[camera_id])
