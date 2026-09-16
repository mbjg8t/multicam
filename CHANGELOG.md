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

### Selectable display DSP

- Added a per-camera DSP Workbench with raw/processed previews.
- Added portable levels, gamma, denoise, sharpen, grayscale, invert, and iron
  palette processors.
- Run DSP in rate-limited background latest-frame workers so slow processing
  skips frames instead of accumulating latency.
- Keep raw broker frames immutable for Focus, Alignment, capture, and MTF while
  the main live compositor can consume a processed display variant.
- Preserve source timestamps/frame numbers and attach pipeline provenance to
  processed frames.
- Added Off and multiple algorithms for levels, gamma, denoise, sharpen, and
  Sobel/Laplacian edge/line stages.
- Made slider updates continuously throttled rather than release/debounce only.
- Render DSP comparisons through the same orientation, alignment, layer, and
  compositing path as the main live screen.
- Replaced full-frame float levels/gamma work with integer lookup tables and
  sampled statistics for substantially lower preview latency.

### Guided camera alignment

- Added a compact main-window camera strip with stream and alignment status.
- Added explicit reference-camera and transformed-target selection.
- Added frozen snapshots of all running cameras with timestamp-skew reporting.
- Added one-point translation alignment across different frame resolutions.
- Added a separate alignment window with exact click mapping, markers, a 50%
  overlay preview, draft acceptance/rejection, and undo.
- Kept camera registration separate from ordinary display-layer transforms.
- Added mode-mismatch protection and generic 3x3 registration matrices used by
  similarity, affine, and homography alignment.
- Added one-click structural matching from a selected reference point to the
  target camera, with high/medium/low confidence reporting.
- Preserved manual target clicking, draft preview, nudging, rejection, and undo
  as correction and validation paths.
- Added progressive numbered point pairs with explicit Shift (one point),
  Rotate + Scale (two points), and Perspective (four points) modes.
- Added exact similarity, affine, and homography solvers and full 3x3 inverse
  warping in the live compositor.
- Added validity-mask compositing so pixels outside a rotated or perspective
  target do not darken the reference image.
- Added Precision auto alignment using 6–12 point pairs and automatic selection
  of the simplest similarity, affine, or homography model that fits.
- Added normalized high-resolution homography estimation, robust outlier
  rejection, per-point residuals, RMS/max error reporting, and residual vectors.
- Added controls to correct or remove any individual point pair without
  restarting the alignment.
- Reject ambiguous automatic matches instead of adding misleading pairs, and
  guide later searches using the current transform's predicted target region.
- Require a majority correspondence consensus so a 2-of-6 fit cannot produce
  an apparently valid draft with zero RMS error.
- Added 1×/2×/4×/8× frozen-frame selection zoom with independent drag panning
  while preserving native image-coordinate clicks and residual markers.
- Added smooth cursor-centered mouse-wheel zoom up to 12×.
- Added a spatial prior for repeated-pattern matching so later matches favor
  strong structure nearest the location predicted by the current transform.
- Require two manual anchor pairs before automatic matching is available.
- Report underpowered transform models separately from incorrect point pairs,
  and suppress stale residuals after a failed fit.
- Preserve point pairs, corrections, and zoom while switching alignment models;
  refit the same points immediately and label fit exclusions as model outliers.
- Keep the last valid overlay visible when another model cannot fit, allow an
  explicit four-point homography, and explain disabled Accept/Undo controls.

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

### Focus utility

- Added an independent Focus window that consumes shared `FrameBroker` frames.
- Added camera selection, click-positioned ROI, bounded 5–15 Hz Tenengrad and
  Laplacian feedback, session peak, recent trend, zoomed ROI, and edge view.
- Added capability-driven Picamera2 manual lens position, single autofocus,
  continuous autofocus, and AF-state reporting where supported.
- Kept focus scores explicitly separate from calibrated MTF measurement.

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
- Persistent alignment and lens-calibration profiles.
- MTF service and MTF Workbench integration.
- Measurement sessions, synchronized capture, recording, and reports.
