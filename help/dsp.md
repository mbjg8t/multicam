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

## Live operation

Workbench sliders send throttled updates continuously while they are moving;
they do not wait for mouse release. The two previews are rendered through the
same orientation, accepted alignment, layer opacity, reference canvas, and
compositor used by the main screen:

- **Live view — selected camera bypassed** substitutes its raw broker frame.
- **Live view — selected camera processed** substitutes its DSP output.

Other enabled layers remain present, so the processed preview matches the
actual main view rather than showing an unrotated sensor frame.

## Current portable processors

- Levels: Off, automatic min/max, or percentile stretch
- Gamma: Off or power gamma
- Denoise: Off, box, Gaussian, or median
- Sharpen: Off, unsharp mask, sharpen kernel, or edge enhance
- Edges/lines: Off, Sobel, or Laplacian with adjustable blend strength
- Normal, grayscale, and iron palettes; optional inversion
- Per-camera DSP rate limit

These operations preserve image geometry. They do not invalidate alignment.
Future crop, resize, lens-undistortion, or spatial-warp processors must publish
a changed geometry signature and invalidate incompatible alignment profiles.

## Performance behavior

DSP runs in a background latest-frame worker. If processing is slower than the
camera, intermediate frames are skipped instead of accumulating latency. The
Workbench reports processed FPS, per-frame processing latency, and errors.
Lower **Maximum DSP FPS** for high-resolution or high-frame-rate cameras.

Integer camera frames use lookup-table levels/gamma conversion and sampled
statistics to avoid large full-frame floating-point intermediates. The initial
implementation is portable NumPy/Pillow code. Raspberry Pi,
Jetson/CUDA, GStreamer, and desktop-GPU implementations can later sit behind
the same pipeline interface.

## Measurement warning

Sharpening, denoising, levels, and gamma can change image measurements. MTF must
use raw or explicitly calibration-corrected frames by default. A future MTF
comparison mode may deliberately measure raw and processed variants while
recording the complete DSP pipeline and revision.
