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
- Alignment and calibration tools.
- MTF service and MTF Workbench integration.
- Measurement sessions, synchronized capture, recording, and reports.
