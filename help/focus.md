# Focus Utility

## Purpose

The Focus window gives fast relative sharpness feedback for any streaming
camera without reopening the hardware or interrupting the main live view. It
uses the latest frame owned by `FrameBroker`.

The score is a focus aid, not a calibrated MTF result. Compare values only
within the same camera, ROI, preview resolution, exposure, gain, and image
processing settings.

## Workflow

1. Open **Focus** from the main Multicam window.
2. Select any streaming camera.
3. Choose a 15%, 25%, 40%, or full-frame ROI.
4. Click a textured, high-contrast feature in the live image to place the ROI.
5. Adjust the physical lens or use camera-reported electronic controls.
6. Maximize **Focus sharpness proxy** while watching **Current / peak** and the
   recent trend.
7. Use **Normal** for visual inspection or **Edges** to inspect local structure.
8. Reset the peak after changing camera, ROI, resolution, exposure, or gain.

Tenengrad gradient energy is the primary score. Laplacian variance is shown as
a secondary diagnostic. Analysis is bounded to a 512-pixel working image for
responsive Pi operation while the ROI preview retains the live display image.

## Camera controls

Controls are capability-driven:

- Cameras with no electronic focus still provide the full metric and ROI tool.
- A camera reporting `AfMode` receives **Auto once**, **Continuous AF**, and
  **Manual** controls.
- A camera reporting `LensPosition` receives a manual diopter slider.

The current ROI controls measurement only. A future step can map it into the
camera's autofocus metering window when that backend safely supports the
required sensor-coordinate conversion.

## Interpretation and limitations

- Prefer a stationary target with edges at several orientations.
- Motion, changing illumination, noise, digital sharpening, exposure, gain,
  and resolution can all change the score without changing optical focus.
- A higher score is meaningful only within the same controlled setup.
- The peak and trend are local to the open browser window and are not saved.
- Use the MTF Workbench for slanted-edge measurement and reportable MTF values.
