# Changelog

## Multicam 1.0 development

### Current foundation

- Generic camera discovery and persistent camera identities.
- Picamera2 and Aravis/GenICam backends.
- Central camera ownership and concurrent acquisition through `FrameBroker`.
- Generic 0..N camera layers and live compositing.
- Capability-driven camera settings.
- Camera profile save and load.
- Raspberry Pi CSI provisioning inspection and guarded configuration proposals.

### Guided camera alignment

- Added a compact main-window camera strip with stream and alignment status.
- Added explicit reference-camera and transformed-target selection.
- Added frozen snapshots of all running cameras with timestamp-skew reporting.
- Added one-point translation alignment across different frame resolutions.
- Added a separate alignment window with exact click mapping, markers, a 50%
  overlay preview, draft acceptance/rejection, and undo.
- Kept camera registration separate from ordinary display-layer transforms.
- Added mode-mismatch protection and generic 3x3 registration matrices for
  future similarity, affine, and homography alignment.
- Added one-click structural matching from a selected reference point to the
  target camera, with high/medium/low confidence reporting.
- Preserved manual target clicking, draft preview, nudging, rejection, and undo
  as correction and validation paths.

### Camera orientation and manual alignment

- Added persistent per-camera rotation and horizontal/vertical flip settings.
- Applied camera orientation before both live compositing and registration.
- Added orientation to saved camera profiles.
- Added manual target-camera nudge controls in the Alignment window with 1,
  5, and 20 pixel steps.
- Clear frozen and active alignment state when orientation changes.

### Live preview resolution

- Added capability-driven selectable live-preview resolutions for Picamera2
  devices.
- Restart only the changed camera through the frame broker and clear active
  alignment when preview geometry changes.
- Keep Aravis/Xenics sensor resolution and ROI separate from preview sizing.

### Repository foundation cleanup

- Removed committed development snapshots; Git history remains authoritative.
- Kept real-camera diagnostics under `tools/hardware/` instead of pytest collection.
- Added complete setup, operating, and troubleshooting documentation.
- Declared runtime dependencies and a `multicam` console command.
- Moved writable camera profiles out of the source tree.
- Made optional hardware backends safe to load only when dependencies exist.
- Split the web application into Python routes, HTML templates, CSS, and JavaScript.
- Added backend health reporting and measurement-ready frame timestamps.

### Planned

- Runtime hot-plug reconciliation.
- Selectable DSP pipelines with raw-data preservation.
- Automatic alignment refinement, rotation/scale, and calibration profiles.
- MTF service and MTF Workbench integration.
- Measurement sessions, synchronized capture, recording, and reports.
