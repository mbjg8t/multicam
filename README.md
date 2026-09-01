# Multicam

Multicam is a portable multi-camera acquisition, viewing, overlay,
alignment and imaging framework.

## Version

Current development series: **Multicam 1.0**

Raspberry Pi is the initial supported platform.

The architecture is designed to remain portable to:

- NVIDIA Jetson
- Linux PCs
- Windows PCs
- future camera platforms

## Initial Goals

- Dynamic camera discovery and configuration
- Multiple camera backends
- Persistent camera identities
- Base camera plus arbitrary 0..N overlay streams
- Shared live application state
- Independent tool windows
- Alignment
- MTF measurement
- Xenics GenICam/Aravis support
- Raspberry Pi Picamera2 support
- FLIR Boson support

The application core is intentionally independent of the web interface
so a future desktop application can reuse the same backend and imaging code.

See `help/ARCHITECTURE.md` for design rules.
