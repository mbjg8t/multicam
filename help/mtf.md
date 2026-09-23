# MTF Workbench

Use the MTF Workbench for controlled single-camera image-quality measurements.
It consumes an immutable raw broker frame; display DSP, layer opacity, and
camera-to-camera alignment are intentionally excluded.

## Workflow

1. Start the camera and set exposure, gain, focus, and preview resolution.
2. Open **MTF** from the main window and select the camera.
3. Choose **Freeze raw live frame**. Backends with controlled still capture use
   their maximum sensor resolution; other backends copy the current raw frame.
4. Drag a tight rectangle around one tri-bar group or one clean slanted edge.
5. Select the appropriate analysis and choose **Analyze ROI**.

**USAF / tri-bar modulation** reports Michelson modulation and the dominant
image-space frequency in cycles/pixel. Use a tight ROI containing repeated bars
of one size and orientation. It is a practical resolution measurement, not an
MTF50 estimate.

**Slanted-edge MTF** reports MTF50, MTF20, MTF10, MTF at Nyquist, edge slant,
contrast, and the normalized MTF curve. Select one clean, high-contrast edge
slanted approximately 2–20 degrees from horizontal or vertical.

## Interpretation

- Compare results only at the same resolution, crop, exposure, gain, focus,
  target distance, illumination, and ROI location.
- Initial results are in cycles/pixel. Object-space units require known target
  geometry and magnification.
- A bar pattern can look resolved because of aliasing. Use slanted-edge MTF for
  the quantitative curve and tri-bars for practical visual confirmation.
- The first release uses manual ROIs deliberately. Automatic target detection
  and multi-site spatial reports will be added after this measurement boundary
  is validated in Multicam.
