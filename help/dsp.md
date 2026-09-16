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
they do not wait for mouse release. The two Workbench previews show only the
selected camera with its configured display orientation:

- **Selected camera — DSP bypassed** shows its raw broker frame.
- **Selected camera — DSP processed** shows its DSP output.

Other layers are intentionally excluded so filter changes can be compared
without composite ghosting. The main window continues to show the complete
aligned composite. Browser preview images are capped at 1280 pixels on their
long edge; raw broker frames and DSP source data are not resized.

## Current portable processors

- Levels: Off, automatic min/max, or percentile stretch
- Gamma: Off or power gamma
- Denoise: Off, box, Gaussian, or median
- Sharpen: Off, unsharp mask, sharpen kernel, or edge enhance
- Edges/lines: Off, fast 3×3, or Laplacian with adjustable blend strength
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
statistics to avoid large full-frame floating-point intermediates. RGB8 bypass
avoids the lookup entirely. Compiled Pillow luminance and edge kernels replace
large temporary NumPy gradient arrays, and the Workbench does not JPEG-encode
the same frame repeatedly. The initial implementation is portable NumPy/Pillow
code. Raspberry Pi,
Jetson/CUDA, GStreamer, and desktop-GPU implementations can later sit behind
the same pipeline interface.

## Measurement warning

Sharpening, denoising, levels, and gamma can change image measurements. MTF must
use raw or explicitly calibration-corrected frames by default. A future MTF
comparison mode may deliberately measure raw and processed variants while
recording the complete DSP pipeline and revision.
