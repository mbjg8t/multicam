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

Choose the least complex model that corrects the visible error:

- **Shift — 1 point pair:** corrects X/Y position and normalizes different
  frame sizes.
- **Rotate + scale — 2 point pairs:** adds arbitrary in-plane rotation and
  uniform scale. This is the normal choice after cameras have moved slightly.
- **Perspective — 4 point pairs:** also corrects planar keystone and affine
  differences. While collecting four pairs, the preview progresses through
  translation, similarity, affine, and finally homography.

Use well-defined features that are visible in both spectral bands. Spread the
points widely across the common field of view. For Perspective, put them near
four corners of the useful subject plane; do not place them on one line.

## Workflow

1. Confirm that both cameras have green status dots on the main page.
2. Select the fixed camera under **Align to** and the camera that should move
   under **Transform**.
3. Open **Alignment**, choose a model, and select **Freeze all running
   cameras**.
4. Review the displayed timestamp skew. Keep the scene still when cameras are
   not hardware-synchronized.
5. Leave **Auto-find target** enabled and click the first distinctive physical
   feature in the frozen reference image.
6. Verify that numbered marker 1 identifies the same physical feature in the
   target. If it is wrong, click the correct target location manually.
7. For Rotate + Scale or Perspective, continue with well-separated reference
   features. Verify each numbered target marker before choosing the next.
8. Inspect the 50% overlay. Use the target image to correct the most recent
   match, or **Clear points** and repeat if an older pair is wrong.
9. Use the arrow buttons to nudge the complete transform by 1, 5, or 20
   reference-canvas pixels if needed.
10. Choose **Accept**, **Reject**, or **Undo accepted**.
11. Select another target and repeat. The reference remains fixed.

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
- Alignment-profile persistence, lens-distortion calibration, and robust
  multi-feature refinement remain planned work.
