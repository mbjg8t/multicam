# MTF Workbench

Use the MTF Workbench for controlled single-camera image-quality measurements.
It consumes an immutable raw broker frame; display DSP, layer opacity, and
camera-to-camera alignment are intentionally excluded.

## Workflow

1. Start the camera and set exposure, gain, focus, and preview resolution.
2. Open **MTF** from the main window and select the camera.
3. Choose **Freeze raw live frame**. Backends with controlled still capture use
   their maximum sensor resolution; other backends copy the current raw frame.
4. Optionally choose **4-corner target** and click the chart corners clockwise.
   For USAF analysis, place these corners around one three-bar element. The
   workbench perspective-corrects that quadrilateral before measuring its bar
   profile. Click **Clear outline** or click the active tool again to reset it.
5. Choose **ROI tool** and drag a tight rectangle around one tri-bar element or
   one clean slanted edge. Use the corner handles and zoom controls to refine it.
   Mouse-wheel zoom works over the image; **Zoom / pan** allows drag-to-pan.
6. Select the appropriate analysis and choose **Analyze ROI**.

**USAF / tri-bar modulation** reports Michelson modulation and the dominant
image-space frequency in cycles/pixel. Use a tight ROI containing repeated bars
of one size and orientation. It is a practical resolution measurement, not an
MTF50 estimate.

**Slanted-edge MTF** reports MTF50, MTF20, MTF10, MTF at Nyquist, edge slant,
contrast, and the normalized MTF curve. Select one clean, high-contrast edge
slanted approximately 2–20 degrees from horizontal or vertical.

Do not analyze the complete USAF chart. Background gradients and the chart
boundary overwhelm the individual bar frequency. Likewise, do not place
multiple chart edges or bar groups in a slanted-edge ROI. The workbench marks
these common cases for review instead of reporting them as valid measurements.
Use a rectangular, unwarped ROI for slanted-edge MTF because resampling an edge
would change the sharpness being measured.

## Interpretation

- Compare results only at the same resolution, crop, exposure, gain, focus,
  target distance, illumination, and ROI location.
- Initial results are in cycles/pixel. Object-space units require known target
  geometry and magnification.
- A bar pattern can look resolved because of aliasing. Use slanted-edge MTF for
  the quantitative curve and tri-bars for practical visual confirmation.
- Perspective makes the chart outline trapezoidal. A small local image-space
  ROI remains useful, but a strongly tilted chart places different regions at
  different focus distances. Square the chart to the camera for comparisons.
- The first release uses manual ROIs deliberately. Automatic target detection
  and multi-site spatial reports will be added after this measurement boundary
  is validated in Multicam.

## Algorithm validation checklist

1. **Capture geometry:** Freeze each camera and confirm the status reports
   `maximum sensor resolution` and the expected sensor width and height.
2. **USAF repeatability:** Measure the same isolated three-bar element in five
   new freezes. Dominant frequency should remain within one FFT bin and bar
   modulation should normally remain within 5% under fixed exposure and focus.
3. **Slanted-edge repeatability:** Measure the same clean edge five times. Each
   result should be valid, edge isolation at least 20%, slant 2–20 degrees, and
   MTF50 normally within 10% under fixed conditions.
4. **Focus sensitivity:** Record a focused result, then deliberately defocus.
   MTF50 and fine-element USAF modulation must decrease.
5. **Scale sensitivity:** Move the chart farther away. Its image-space bar
   frequency must increase; compare modulation only for the same chart element.
6. **Spatial check:** Repeat the same feature at image center and four corners.
   Save the results separately; corner degradation is expected from many lenses.
7. **Reference check:** Compare a saved frame with the former `pi_camera` MTF
   implementation or a trusted desktop tool using exactly the same pixel ROI.
