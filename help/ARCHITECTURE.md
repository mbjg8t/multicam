# Multicam 1.0 Architecture

## Purpose

Multicam is a portable multi-camera acquisition, viewing, overlay,
alignment and image-analysis application.

Raspberry Pi is the first supported platform, but the architecture must
remain portable to NVIDIA Jetson, Linux PCs, Windows PCs and future platforms.

## Core Rules

### 1. Core is platform independent

Code under `multicam/core/` must not depend directly on:

- Picamera2
- libcamera
- Aravis
- V4L2
- NVIDIA/Jetson APIs
- Windows camera APIs
- Flask
- HTML or JavaScript

Hardware and platform dependencies belong behind adapters/backends.

### 2. Cameras are generic devices

Application code must not assume fixed camera roles such as:

- RGB
- NIR
- SWIR
- thermal
- cam0
- cam1

A camera has a persistent ID, metadata and capabilities.

Application roles are assigned separately.

### 3. Camera count is dynamic

The application must support any number of cameras that the host hardware
can practically operate.

No code should assume two cameras.

### 4. Overlay count is dynamic

A view consists conceptually of:

    base camera
    + 0..N overlay layers

Overlay layers are stored as a collection/list.

Do not create fixed fields such as overlay1, overlay2 or thermal_overlay.

### 5. Cameras are acquired centrally

Individual GUI windows and tools must not independently open camera hardware.

The camera manager owns acquisition.

Frames are distributed to consumers such as:

- live view
- compositor
- MTF
- future capture
- future recording
- future calibration tools

### 6. Raw data and display data are separate concepts

A camera may provide high-bit-depth or otherwise scientific/raw data while
the UI uses a lower-bandwidth display representation.

Do not destroy raw information merely to make a preview image.

### 7. Capability-driven controls

Camera configuration is generated from reported capabilities where practical.

Examples:

- exposure
- gain
- ROI
- pixel format
- trigger
- temperature
- cooling
- NUC
- autofocus

Tools should ask whether a capability exists instead of assuming a
particular camera model or platform.

### 8. Runtime state is authoritative and shared

Independent windows operate against one shared application state.

Changing camera configuration, overlays or alignment in a tool window
must be reflected immediately in the live main view.

### 9. GUI is not the application

Application functionality belongs in core/services.

The web interface is one presentation layer.

A future Qt/PySide or other desktop application should reuse the same core
without rewriting camera management, compositing, alignment or MTF logic.

### 10. Platform-specific acceleration is optional

Portable implementations come first.

Platforms may later provide optimized implementations such as:

- Raspberry Pi hardware paths
- NVIDIA CUDA/NVMM/GStreamer
- PC GPU acceleration
- hardware video encoding

These optimizations must not change the public core interfaces.

## Initial Multicam 1.0 Scope

Implement now:

- camera discovery/management framework
- Raspberry Pi Picamera2 backend
- Xenics GenICam/Aravis backend
- FLIR Boson backend
- generic base + 0..N overlays
- shared application state
- live main view
- camera configuration window
- alignment window
- existing MTF functionality

Leave extension points but do not implement yet:

- recording
- advanced capture
- additional calibration tools
- sessions
- tracking/detection
- native desktop GUI
- advanced platform acceleration

## Intended High-Level Flow

    Camera Backends
          |
    Camera Manager
          |
      Frame Broker
          |
    +-----+--------+---------+
    |              |         |
 Live View     Compositor   Tools
                   |
             Base + 0..N Layers

Shared state and events connect all application services and user interfaces.

