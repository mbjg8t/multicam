# DSP Workbench

## Purpose

The DSP Workbench applies a selectable display-processing pipeline to any
running camera without modifying its raw `FrameBroker` frame. When a camera's
pipeline is enabled, its processed variant is used by the main live compositor.
Focus, Alignment, capture, and future MTF measurements continue to receive raw
broker frames unless they explicitly request a processed variant.

Open **DSP** from the main Multicam window, select a camera, and enable **Enable
DSP and use it in live view** to activate the processed preview and live-layer
variant. Adjustments then update the processed view without altering raw data.

## Current portable processors

- Black and white percentile levels
- Gamma
- Box denoise
- Unsharp-mask sharpening
- Grayscale and inversion
- Normal, grayscale, and iron palettes
- Per-camera DSP rate limit

These operations preserve image geometry. They do not invalidate alignment.
Future crop, resize, lens-undistortion, or spatial-warp processors must publish
a changed geometry signature and invalidate incompatible alignment profiles.

## Performance behavior

DSP runs in a background latest-frame worker. If processing is slower than the
camera, intermediate frames are skipped instead of accumulating latency. The
Workbench reports processed FPS, per-frame processing latency, and errors.
Lower **Maximum DSP FPS** for high-resolution or high-frame-rate cameras.

The initial implementation is portable NumPy/Pillow code. Raspberry Pi,
Jetson/CUDA, GStreamer, and desktop-GPU implementations can later sit behind
the same pipeline interface.

## Measurement warning

Sharpening, denoising, levels, and gamma can change image measurements. MTF must
use raw or explicitly calibration-corrected frames by default. A future MTF
comparison mode may deliberately measure raw and processed variants while
recording the complete DSP pipeline and revision.
