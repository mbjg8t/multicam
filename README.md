# Multicam

Multicam is a portable multi-camera acquisition, viewing, overlay, alignment,
and image-analysis framework.

## Multicam 1.0 Goals

Initial supported platform:
- Raspberry Pi

Architecture must remain portable to:
- NVIDIA Jetson platforms
- Linux PCs
- Windows PCs
- Other platforms where suitable camera backends are available

## Core Design Principles

1. The core is independent of Flask, HTML, JavaScript, and any specific GUI.
2. Hardware-specific camera APIs are isolated behind camera backends.
3. Cameras are identified generically and persistently where possible.
4. The system supports a base camera plus 0..N overlay streams.
5. Camera acquisition is owned centrally and frames may have multiple consumers.
6. Runtime state is shared so independent UI/tool windows remain synchronized.
7. Camera capabilities drive available controls rather than hard-coded camera types.
8. New camera backends and tools should be addable without restructuring the application.
9. Platform-specific optimizations are optional implementations, not core assumptions.
10. V1 should establish clean extension points without implementing unnecessary future features.

## Initial Functional Scope

Multicam 1.0 will initially provide:

- Live multi-camera viewing
- Camera discovery and configuration
- Base camera + arbitrary overlay layers
- Overlay alignment
- Existing MTF functionality
- Raspberry Pi CSI / Picamera2 support
- FLIR Boson support
- Xenics / GenICam / Aravis support
- Shared application state and events
- Web interface with independent tool windows

Future features such as recording, advanced capture, additional calibration tools,
sessions, tracking, and native desktop interfaces are intentionally outside the
initial implementation but should fit into the architecture without major redesign.

## Architecture

Hardware-specific dependencies belong in `multicam/backends/`.

Portable application logic belongs in `multicam/core/`.

The web API and interface are adapters around the core and must not own cameras
or contain camera-control logic.

