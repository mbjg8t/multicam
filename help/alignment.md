# Camera Alignment

## Purpose

The Alignment window registers any streaming target camera to any streaming
reference camera. Camera names and spectral roles are not hard-coded.

- **Align to (reference):** establishes the output pixel space and does not
  move.
- **Transform (target):** receives the calculated registration transform.

Registration is independent of ordinary layer position, opacity, and display
layout.

Set physical mounting orientation under **Cameras → Settings → Display
Orientation** before starting alignment. Right-angle rotation and flip are
saved per camera and applied before registration. Changing them clears current
runtime alignment because the old pixel coordinates are no longer valid.

## Alignment models

**Precision auto — 4–12 point pairs** is the recommended mode for a flat test
chart. It robustly fits similarity, affine, and homography candidates, rejects
isolated bad pairs, and selects the simplest model that meets the residual
error threshold.

Manual model choices remain available:

- **Shift — 1 point pair:** corrects X/Y position and normalizes different
  frame sizes.
- **Rotate + scale — 2–12 pairs:** adds arbitrary in-plane rotation and uniform
  scale.
- **Stretch + skew — 3–12 pairs:** adds independent directional stretch and
  shear without perspective.
- **Perspective — 4–12 pairs:** also corrects planar keystone differences.
  While collecting its first four pairs, the preview progresses through
  translation, similarity, affine, and finally homography.

Use well-defined features that are visible in both spectral bands. Spread the
points widely across the common field of view. For Perspective, put them near
four corners of the useful subject plane; do not place them on one line.

## Workflow

1. Confirm that both cameras have green status dots on the main page.
2. Select the fixed camera under **Align to** and the camera that should move
   under **Transform**.
3. Open **Alignment**, leave **Precision auto** selected, and choose **Freeze
   all running cameras**.
4. Review the displayed timestamp skew. Keep the scene still when cameras are
   not hardware-synchronized.
5. Leave **Auto-find target** enabled and click the first distinctive physical
   feature in the frozen reference image.
6. Verify that numbered marker 1 identifies the same physical feature in the
   target. If it is wrong, click the correct target location manually.
7. Collect at least four widely separated pairs. Six to twelve pairs provide a
   stronger fit and permit robust rejection of an incorrect match.
8. Inspect the model, RMS/max error, and per-pair residuals above the images.
   A red pair was rejected. Use **Correct target** for any numbered pair and
   click its correct target location, or remove it without restarting.
9. Residual lines on the reference show the remaining displacement between the
   transformed target point and its requested reference point.
10. Use the arrow buttons to nudge the complete transform by 1, 5, or 20
   reference-canvas pixels if needed.
11. Choose **Accept**, **Reject**, or **Undo accepted**.
12. Select another target and repeat. The reference remains fixed.

The automatic matcher downsamples the display frames, converts them to gradient
structure, and searches the complete target frame using normalized
correlation. This is more useful across visible, NIR, SWIR, and thermal imagery
than matching raw brightness. Confidence is reported, but the operator must
inspect and accept the draft. Disable **Auto-find target** for fully manual
point pairing.

## Status meanings

- **Reference:** fixed alignment coordinate system.
- **Target:** camera currently selected for adjustment.
- **Preview:** point pairs or a nudge created a draft transform.
- **Aligned:** the draft was accepted and the camera mode still matches.
- **Mode mismatch:** resolution changed after alignment; the transform is kept
  in state but is not applied.
- **Unaligned:** no accepted transform exists for the camera.

## Boundaries and practical limits

- Alignments are runtime state and are not persisted after application exit.
- Changing the reference is blocked after alignment work exists. Use **Reset
  all alignments** before choosing a different reference.
- Frozen frames are the latest available frames and may not be simultaneous.
- A homography aligns one subject plane. Cameras separated in space will still
  show parallax for objects at different depths; no single 2D transform can
  remove that.
- Strong cross-spectral appearance changes, blur, repeated patterns, or large
  initial rotations may defeat automatic patch matching. Place the matching
  target points manually in those cases; the multi-point transform still
  solves normally.
- Alignment-profile persistence and lens-distortion calibration remain planned
  work.
