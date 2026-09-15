# Multicam

Multicam 1.0 is a portable multi-camera acquisition, viewing, overlay, and
measurement platform. Raspberry Pi is the first supported platform; the core
is designed to remain reusable on NVIDIA Jetson, Linux PCs, and Windows PCs.

## Current status

Implemented:

- Picamera2 and Aravis/GenICam camera backends
- generic camera discovery and persistent identities
- central concurrent acquisition through `CameraManager` and `FrameBroker`
- generic 0..N camera layers and live compositing
- capability-driven camera settings and saved camera profiles
- Raspberry Pi CSI provisioning inspection
- Flask web interface

Planned but not yet integrated:

- FLIR Boson backend
- runtime hot-plug reconciliation
- alignment and calibration tools
- selectable DSP pipelines
- MTF Workbench and analysis service
- measurement sessions, synchronized capture, recording, and reports

## Raspberry Pi setup

The venv uses system site packages so it can access Raspberry Pi and
PyGObject/Aravis packages installed by APT.

```bash
clear
sudo apt update
sudo apt install -y python3-venv python3-picamera2 python3-gi \
  gir1.2-aravis-0.8 aravis-tools
```

From the repository:

```bash
clear
cd ~/dev/multicam
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## Run

```bash
clear
cd ~/dev/multicam
source .venv/bin/activate
multicam
```

Open `http://<pi-address>:5000` from another computer on the same network.

The existing launcher remains available:

```bash
clear
cd ~/dev/multicam
./multicam.sh
```

## Test

Run portable automated tests:

```bash
clear
cd ~/dev/multicam
source .venv/bin/activate
python -m pytest -q
```

Run hardware diagnostics individually when the corresponding camera is
attached:

```bash
clear
cd ~/dev/multicam
source .venv/bin/activate
python tools/hardware/picamera2_real.py
python tools/hardware/aravis_real.py
```

## Configuration

Writable camera profiles default to:

```text
~/.config/multicam/camera_profiles/
```

Set `MULTICAM_CONFIG_DIR` to use a different configuration directory. A sample
profile is provided at `config/examples/camera-profile.json`.

For camera attachment and Raspberry Pi overlays, see
[`help/cam_config.md`](help/cam_config.md). For design boundaries and future
services, see [`help/ARCHITECTURE.md`](help/ARCHITECTURE.md).
