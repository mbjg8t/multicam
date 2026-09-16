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

**Precision auto — 6–12 point pairs** is the recommended mode for a flat test
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
- **Perspective / homography — 6–12 pairs:** these are the same 3x3 projective
  transform. It also corrects planar keystone differences. A provisional
  homography preview begins at the mathematical minimum of four pairs, but
  acceptance requires six so incorrect correspondences can be detected.

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
5. Manually select the same distinctive physical feature in both frozen images,
   then repeat with a second widely separated feature. Two manual anchors keep
   repeated chart patterns from establishing the wrong initial pose.
6. After two anchors, optionally enable **Auto-find after 2 anchors**. Verify
   every suggested numbered marker; correct or remove any wrong target.
7. Collect at least six widely separated pairs in Precision auto. Four is the
   mathematical minimum for homography but cannot expose a wrong pair; six to
   twelve pairs permit meaningful rejection.
8. Inspect the model, RMS/max error, and per-pair residuals above the images.
   A red pair was rejected. Use **Correct target** for any numbered pair and
   click its correct target location, or remove it without restarting.
9. Scroll the mouse wheel over either frozen image for smooth cursor-centered
   zoom up to 12×, or use the 2×/4×/8× presets. Drag each image independently
   to pan it and use **Reset zoom/pan** to return to the full view.
10. Residual lines on the reference show the remaining displacement between the
   transformed target point and its requested reference point.
11. Use the arrow buttons to nudge the complete transform by 1, 5, or 20
   reference-canvas pixels if needed.
12. Choose **Accept**, **Reject**, or **Undo accepted**.
13. Select another target and repeat. The reference remains fixed.

The automatic matcher becomes available after two manual anchors. It downsamples
the display frames, converts them to gradient structure, and searches the target
near the position predicted by the current transform using normalized
correlation.
This is more useful across visible, NIR, SWIR, and thermal imagery than matching
raw brightness. Ambiguous automatic matches are not added; click
the corresponding target location manually. After a valid initial fit, the
search uses both a restricted region and a spatial preference for the strong
match nearest the predicted position. A low-uniqueness
but structurally adequate match in that guided region is labeled **guided**.
The operator must still inspect and accept the draft. Disable **Auto-find
after 2 anchors** for fully manual point pairing.

If manually selected pairs are consistent under a more flexible transform than
the selected model, the page reports a model mismatch rather than labeling the
points as bad. For example, correct points from a keystoned chart may require
**Perspective / homography** even though **Rotate + scale** cannot fit them.
Changing the Alignment model preserves all completed points, their order, and
manual corrections, then immediately refits them with the new model. A **model
outlier** means the selected transform cannot explain that pair within the
residual tolerance; it does not mean the manual click became ambiguous.

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
- Selection zoom enlarges the frozen frame without inventing detail; point
  coordinates remain in native frozen-frame pixels. Frozen frames currently
  use the configured live-preview resolution. A future full-resolution
  calibration-capture service must request a still safely through each backend
  without silently changing live sensor geometry.
- A homography aligns one subject plane. Cameras separated in space will still
  show parallax for objects at different depths; no single 2D transform can
  remove that.
- Strong cross-spectral appearance changes, blur, repeated patterns, or large
  initial rotations may defeat automatic patch matching. Place the matching
  target points manually in those cases; the multi-point transform still
  solves normally.
- Alignment-profile persistence and lens-distortion calibration remain planned
  work.
