# Multicam Camera Configuration

Quick reference for connecting and configuring cameras in Multicam.

## Start Multicam

```bash
clear
multicam
1. USB / GenICam Cameras

USB cameras normally do not require Raspberry Pi device-tree overlays.

Example: Xenics Wildcat SWIR camera.

Connect
Connect the camera to the Pi.
Start Multicam.
Open Cameras.
The camera should appear in the Add Camera Layer dropdown.
Select it and click + Add Camera Layer.

Multicam currently uses the Aravis backend for the Xenics/GenICam camera.

Xenics Wildcat Troubleshooting

Confirm Linux sees the camera:

clear
lsusb | grep -i 317c

Expected example:

ID 317c:f132 Xenics Wildcat-1280-TE1-USB

Confirm Aravis sees it:

clear
arv-tool-0.8

Healthy example:

Xenics-317C00710261- (USB3)

If Aravis instead reports:

-- (USB3)

the camera is visible to USB, but its USB3 Vision interface is not
responding correctly.

Power-cycle/reset the camera and test again.

This bad state can also cause Aravis discovery to take approximately
4 seconds and slow Multicam startup. Healthy Wildcat discovery is
approximately 1 second.

Xenics USB Permissions

Current udev rule:

SUBSYSTEM=="usb", ATTR{idVendor}=="317c", MODE="0666"

Location:

/etc/udev/rules.d/99-xenics-usb.rules

After changing the rule:

clear
sudo udevadm control --reload-rules
sudo udevadm trigger

Then unplug/reconnect the camera.

2. Raspberry Pi CSI Cameras

CSI cameras may require a Raspberry Pi device-tree overlay before
libcamera/Picamera2 can use them.

Current examples:

OV5647
OV64A40 / Arducam 64 MP

Physically connect the camera and start Multicam:

clear
multicam

Open:

Cameras -> Hardware Configuration

Multicam compares:

Runtime camera detection
Raspberry Pi device-tree topology
/boot/firmware/config.txt
Required camera overlay

It then reports the camera provisioning status and any proposed
configuration changes.

3. CAM0 / CAM1 Overlay Selection

Do NOT assume that Picamera2 camera number 0 means CAM0 or camera
number 1 means CAM1.

Multicam determines the physical CSI connector using the Raspberry Pi
device tree.

On the current Raspberry Pi 5:

CSI/DSI0 -> i2c@88000
CSI/DSI1 -> i2c@80000

The cam0 overlay parameter selects CSI/DSI0 for supported overlays.

Example OV5647 on CAM0:

dtoverlay=ov5647,cam0

Example OV64A40 on the default CAM1 connector:

dtoverlay=ov64a40

Multicam determines this from the actual runtime/device-tree path
rather than guessing from Picamera2 numbering.

4. Current Working Pi Configuration

Current known-good camera-related configuration:

camera_auto_detect=0
dtoverlay=ov64a40
dtoverlay=ov5647,cam0

Other unrelated settings in /boot/firmware/config.txt should be
preserved.

Current physical mapping:

CSI/DSI0
  OV5647
  dtoverlay=ov5647,cam0

CSI/DSI1
  OV64A40
  dtoverlay=ov64a40
5. Check Cameras Outside Multicam

List Raspberry Pi/libcamera cameras:

clear
rpicam-hello --list-cameras

List Aravis/GenICam cameras:

clear
arv-tool-0.8

Check the Xenics at the USB level:

clear
lsusb | grep -i 317c

These commands help determine whether a problem is in Multicam or
below Multicam in the hardware/driver layer.

6. Multicam Provisioning Status

Multicam can inspect Raspberry Pi camera configuration and generate
required changes.

Typical states include:

READY
DETECTED_NOT_CONFIGURED
CONFIGURED_NOT_DETECTED
CONFIG_CHANGE_PENDING
REBOOT_REQUIRED
ERROR
UNKNOWN

Example:

DETECTED_NOT_CONFIGURED

with:

dtoverlay=ov5647,cam0

means Multicam detected the camera but the required boot overlay is
missing.

7. Apply Configuration

The provisioning system has been tested to:

Determine the required overlay.
Determine CAM0/CAM1 from the actual device tree.
Preserve the existing configuration.
Create a timestamped backup.
Add the required overlay.
Verify the written configuration.
Report whether a reboot is required.

Normal Multicam currently does NOT have permission to modify the real:

/boot/firmware/config.txt

through the web interface.

The Apply Configuration workflow has been validated using temporary
configuration files, but privileged writing to the real Pi boot
configuration is intentionally not enabled yet.

Until this is completed, use Hardware Configuration to determine
the required change and manually edit the boot configuration when
necessary.

After changing a CSI camera overlay, reboot:

clear
sudo reboot
8. Adding a Camera as a Layer

Once the camera is correctly discovered:

Open Cameras.
Find Add Camera Layer.
Select the desired camera.
Click + Add Camera Layer.

Every camera is treated generically as a layer.

Multicam does not assign fixed roles such as RGB, NIR, SWIR, or
Thermal.

The model is:

Camera -> Camera Layer -> Display / Alignment / Tools

This allows arbitrary camera combinations and camera counts.

9. Basic Troubleshooting Order

Work from the hardware upward.

USB / Xenics
clear
lsusb | grep -i 317c
arv-tool-0.8
Raspberry Pi CSI
clear
rpicam-hello --list-cameras

Then check:

Multicam -> Cameras -> Hardware Configuration

If the operating-system/backend tools cannot see the camera, fix that
problem before troubleshooting the Multicam layer UI.

If the backend sees the camera but Multicam does not, investigate the
Multicam discovery/backend handling.

Current Camera Backends
Camera type	Backend
Raspberry Pi CSI / libcamera	Picamera2
Xenics / USB3 Vision / GenICam	Aravis

Future camera types should be added through additional backends rather
than adding camera-specific logic throughout Multicam.

Design Rule

A camera is a camera. A displayed camera is a layer.

Hardware-specific configuration belongs in the camera backend/platform
provisioning layer.

The rest of Multicam should remain independent of the particular
camera model.
