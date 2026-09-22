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
Tested cameras include OV5647, IMX519/B0449, and OV64A40/Arducam 64 MP.

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

### CAM0 and CAM1 on Raspberry Pi 5

Do not assume Picamera2 camera number 0 means CAM0. Multicam resolves the
physical connector from the device-tree path.

Use the connector names printed on the board: `CAM/DISP0` and `CAM/DISP1`.
Both camera/display connectors are between the micro-HDMI connectors and the
Ethernet jack. Use the silkscreen label rather than a remembered left/right or
“closest to USB” description, since board orientation makes those ambiguous.

On the current Raspberry Pi 5:

| Physical connector | Device-tree controller | Overlay form |
| --- | --- | --- |
| CSI/DSI0 | `i2c@88000` | `dtoverlay=<sensor>,cam0` |
| CSI/DSI1 | `i2c@80000` | `dtoverlay=<sensor>` |

Current known-good OV5647 + manual-focus IMX519/B0449 configuration:

```text
camera_auto_detect=0
dtoverlay=ov5647,cam0
dtoverlay=imx519,vcm=off
```

Current physical mapping:

| Connector | Camera | Overlay |
| --- | --- | --- |
| CAM/DISP0 | OV5647 | `dtoverlay=ov5647,cam0` |
| CAM/DISP1 | IMX519/B0449 manual lens | `dtoverlay=imx519,vcm=off` |

The previously tested OV64A40 on CAM/DISP1 uses
`dtoverlay=ov64a40`. Direct sensor overlays are preferred. Earlier attempts
with generic `arducam-64mp` and `arducam-pivariety` overlays produced sensor
identification or register-read failures on this hardware.

### Add or replace CSI cameras

Open **Cameras → Hardware Configuration** and select the physically installed
sensor independently for CAM0 and CAM1. `None / no camera` deliberately removes
the managed overlay for that connector. Choose **Review Selected Overlays**
before applying; the UI shows the exact `dtoverlay` lines that will be used.

The sensor catalog is implemented by the Raspberry Pi platform adapter, not by
the portable camera core. Adding a sensor normally requires one catalog entry
containing its stable ID, display name, runtime model, overlay, focus type, and
default parameters. The same generic UI and provisioning service then expose
it automatically.

When applied, Multicam:

1. requires a complete selection for both physical ports;
2. creates a timestamped backup of `config.txt`;
3. preserves unrelated settings and overlays;
4. replaces camera overlays with one marked, managed block;
5. writes `camera_auto_detect=0` and the reviewed direct-sensor overlays;
6. reads the file back and verifies the expected lines;
7. reports that a reboot is required.

Applying and rebooting remain separate operations. This prevents an accidental
selection from immediately taking the Pi offline and leaves a backup for manual
recovery.

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
settings, create a timestamped backup, write a reviewed overlay set, and verify
the result. Boot writes are disabled in a normal web-app startup. The current
write guard is intended for testing against an alternate config file:

```bash
clear
MULTICAM_PI_CONFIG=/tmp/multicam-config.txt \
MULTICAM_ALLOW_PROVISIONING_WRITE=1 \
multicam
```

A future narrowly privileged system helper should own real
`/boot/firmware/config.txt` writes and reboot requests. The web process should
not run as root.

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
