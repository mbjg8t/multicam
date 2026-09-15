# Multicam Camera Configuration

Quick reference for connecting, configuring, and troubleshooting cameras.

## Start Multicam

```bash
clear
cd ~/dev/multicam
source .venv/bin/activate
multicam
```

Open `http://<pi-address>:5000`, then select **Cameras**.

## USB and GenICam cameras

USB cameras normally do not require Raspberry Pi device-tree overlays. The
Xenics Wildcat SWIR camera uses the Aravis/GenICam backend.

Confirm Linux sees the Xenics camera:

```bash
clear
lsusb | grep -i 317c
```

Expected USB ID:

```text
317c:f132
```

Confirm Aravis sees it:

```bash
clear
arv-tool-0.8
```

A healthy camera reports a complete device ID similar to:

```text
Xenics-317C00710261- (USB3)
```

If only `-- (USB3)` appears, the USB device is present but its USB3 Vision
interface is not responding correctly. Power-cycle the camera and test again.
This condition can also increase discovery time from about one second to about
four seconds.

### Xenics USB permissions

Current udev rule:

```text
SUBSYSTEM=="usb", ATTR{idVendor}=="317c", MODE="0666"
```

Store it in `/etc/udev/rules.d/99-xenics-usb.rules`, then reload the rules:

```bash
clear
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Unplug and reconnect the camera afterward.

## Raspberry Pi CSI cameras

CSI cameras may require a device-tree overlay before Picamera2 can use them.
Current cameras include OV5647 and OV64A40/Arducam 64 MP.

Check detection outside Multicam:

```bash
clear
rpicam-hello --list-cameras
```

In Multicam, open **Cameras → Hardware Configuration**. Multicam compares:

- runtime camera detection
- Raspberry Pi device-tree topology
- `/boot/firmware/config.txt`
- the required camera overlay

### CAM0 and CAM1

Do not assume Picamera2 camera number 0 means CAM0. Multicam resolves the
physical connector from the device-tree path.

On the current Raspberry Pi 5:

| Physical connector | Device-tree controller | Overlay form |
| --- | --- | --- |
| CSI/DSI0 | `i2c@88000` | `dtoverlay=<sensor>,cam0` |
| CSI/DSI1 | `i2c@80000` | `dtoverlay=<sensor>` |

Current known-good configuration:

```text
camera_auto_detect=0
dtoverlay=ov64a40
dtoverlay=ov5647,cam0
```

Current physical mapping:

| Connector | Camera | Overlay |
| --- | --- | --- |
| CSI/DSI0 | OV5647 | `dtoverlay=ov5647,cam0` |
| CSI/DSI1 | OV64A40 | `dtoverlay=ov64a40` |

## Provisioning status

Common states are:

- `READY`
- `DETECTED_NOT_CONFIGURED`
- `CONFIGURED_NOT_DETECTED`
- `CONFIG_CHANGE_PENDING`
- `REBOOT_REQUIRED`
- `ERROR`
- `UNKNOWN`

For example, `DETECTED_NOT_CONFIGURED` with `dtoverlay=ov5647,cam0` means the
camera was detected but the corresponding boot overlay is missing.

The provisioning service can determine required changes, preserve unrelated
settings, create a timestamped backup, write a proposed overlay, and verify the
result. Normal web-app startup intentionally does not have permission to modify
the real boot configuration. Review the proposal and edit the configuration
manually until a privileged helper is implemented.

After changing an overlay:

```bash
clear
sudo reboot
```

## Add a camera layer

Once a camera is discovered:

1. Open **Cameras**.
2. Select the camera under **Add Camera Layer**.
3. Select **+ Add Camera Layer**.

Multicam uses the generic relationship:

```text
Camera → Camera Layer → Display / Alignment / Tools
```

It does not assign fixed RGB, NIR, SWIR, thermal, cam0, or cam1 application
roles.

## Troubleshooting order

Work from the operating system upward.

For USB/Xenics:

```bash
clear
lsusb | grep -i 317c
arv-tool-0.8
```

For Raspberry Pi CSI:

```bash
clear
rpicam-hello --list-cameras
```

Then inspect **Multicam → Cameras → Hardware Configuration**.

- If the operating-system tool cannot see the camera, fix hardware, power,
  cabling, permissions, driver, or overlay configuration first.
- If the backend tool sees the camera but Multicam does not, inspect Multicam's
  backend diagnostics.
- If a camera appears but has no image, inspect stream state, pixel format,
  exposure, frame count, and the latest backend error.

## Backend mapping

| Camera family | Backend |
| --- | --- |
| Raspberry Pi CSI/libcamera | Picamera2 |
| Xenics USB3 Vision/GenICam | Aravis |
| FLIR Boson | Planned backend |

Hardware-specific behavior belongs in a backend or platform provisioner. Core,
display, alignment, MTF, and other tools remain camera-model independent.
