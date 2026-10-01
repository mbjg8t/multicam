# FLIR Boson field setup

Multicam discovers Boson UVC video nodes through `v4l2-ctl`. Supported image
sizes are 640x512, 640x514 (two telemetry rows), and 320x256.

## Pi setup

```bash
clear
cd /home/pi/dev/multicam
sudo apt update
sudo apt install -y v4l-utils python3-opencv
source .venv/bin/activate
pip install -e .
v4l2-ctl --list-devices
python -m pytest -q tests/test_boson.py
```

Start Multicam normally, open **Cameras**, add the Boson as a layer, then open
**Settings**. Thermal settings include palette, automatic contrast, low/high
percentile clipping, and optional removal of the two telemetry rows. Opacity,
rotation, flip, scaling, and alignment use the standard layer and alignment
controls.

The legacy overlay's hotspot, temperature threshold, and grid are presentation
features rather than UVC camera settings. They are intentionally not burned
into acquired frames; add them later as non-destructive thermal overlay/DSP
features so alignment, focus, MTF, recording, and snapshots retain clean data.

If the Boson is absent, confirm that `v4l2-ctl --list-devices` names it FLIR or
Boson and that `v4l2-ctl -d /dev/videoN --list-formats-ext` reports a supported
size. Do not hard-code `/dev/video0`; the assigned node can change after reboot.
