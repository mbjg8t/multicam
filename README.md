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
- live camera-status strip with selectable alignment reference and target
- robust multi-point alignment with automatic similarity/affine/perspective
  selection, outlier rejection, residual reporting, preview, and undo
- persistent per-camera display orientation (rotate/flip), applied before alignment
- manual target nudges with 1, 5, or 20 pixel steps in the Alignment window
- safe, backend-reported live-preview resolution selection for Pi cameras
- independent live Focus utility with selectable ROI, sharpness trend, peak
  tracking, edge view, and capability-driven autofocus controls
- selectable per-camera display DSP with raw/processed comparison, levels,
  gamma, denoise, sharpen, grayscale, inversion, and palettes
- capability-driven camera settings and saved camera profiles
- Raspberry Pi CSI provisioning inspection
- Flask web interface

Planned but not yet integrated:

- FLIR Boson backend
- runtime hot-plug reconciliation
- persistent alignment and lens-calibration profiles
- persistent/reorderable DSP profiles and accelerated processor providers
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

The main page shows every discovered camera and whether it is streaming with
frames. Choose **Align to** (the fixed reference) and **Transform** (the camera
that will move), then open **Alignment**. Freeze the running cameras and use
**Quick affine** for a stable three-point setup, or **Planar precision** with
6–12 widely separated features for a flat subject with perspective differences.
Guided auto chooses the simplest materially better model and never promotes a
four-point fit to an exact homography. It reports per-pair residuals and creates
a 50% overlay draft. Use cursor-centered mouse-wheel zoom up to 12× or zoom
presets, then pan with a precise selection crosshair. Correct or remove any
numbered pair, download diagnostics if needed, nudge the transform, and accept
it after inspection. See
[`help/alignment.md`](help/alignment.md) for the complete workflow and current
limitations.

Set a camera's permanent display orientation in **Cameras → Settings** before
aligning it. Orientation is stored by camera ID and included when saving a
camera profile. The Alignment window provides manual arrow nudges for the
selected target camera; these are part of registration, not camera orientation.

When a camera's backend reports supported live-preview sizes, choose one in
**Cameras → Settings → Live Preview Resolution**. Applying a size restarts only
that camera and clears active alignment, because registration coordinates use
the preview pixels. The Pi camera backend currently exposes conservative
preview sizes; Aravis/Xenics resolution and ROI are intentionally not changed
through this control because they can alter scientific capture geometry.

Open **Focus** from the main window to evaluate any streaming camera without
interrupting the composite view. Click the live image to position the ROI and
maximize the relative Tenengrad score while adjusting focus. Electronic AF and
lens-position controls appear only when reported by the selected backend. See
[`help/focus.md`](help/focus.md) for operating guidance and limitations.

Open **DSP** to compare a raw broker frame with a portable processed display
variant and optionally route that variant into the live layer compositor. DSP
runs in a rate-limited background latest-frame worker; raw frames remain
unchanged for Focus, Alignment, capture, and future MTF. See
[`help/dsp.md`](help/dsp.md).

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
