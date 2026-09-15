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
Orientation** before starting alignment. Rotation and flip are saved per camera
and are applied before registration. Changing them clears current runtime
alignment, deliberately, because the old pixel coordinates are no longer valid.

## One-click automatic workflow

1. Confirm that both cameras have green status dots on the main page.
2. Select the reference camera under **Align to**.
3. Select the camera that should move under **Transform**.
4. Open **Alignment** and choose **Freeze all running cameras**.
5. Review the displayed maximum timestamp skew. Keep the scene still when
   cameras are not hardware-synchronized.
6. Leave **Auto-find target** enabled and click a distinctive physical feature
   in the frozen reference image.
7. Review the target marker and the reported structural-match confidence.
8. Inspect the 50% overlay preview and the X/Y movement. If the automatic match
   is wrong, click the correct target feature manually.
9. Use the arrow buttons to nudge the target by 1, 5, or 20 reference-canvas
   pixels when needed. Nudges create a draft, just like matching points.
10. Choose **Accept**, **Reject**, or **Undo accepted**.
11. Select the next target and repeat. The reference remains fixed.

The automatic matcher downsamples the display frames, converts them to gradient
structure, and searches the complete target frame using normalized
correlation. This is more useful across visible, NIR, SWIR, and thermal imagery
than matching raw brightness. It reports confidence but always requires the
operator to inspect and accept the draft. Disable **Auto-find target** to use
the original two-click workflow.

One matching point calculates translation. The target is first normalized to
the reference frame size, so cameras with different resolutions are supported.
The current compositor does not yet apply rotation, perspective, or a custom
scale beyond this normal frame-size normalization.

## Status meanings

- **Reference:** fixed alignment coordinate system.
- **Target:** camera currently selected for adjustment.
- **Preview:** a matching point pair created a draft transform.
- **Aligned:** the draft was accepted and the camera mode still matches.
- **Mode mismatch:** resolution changed after alignment; the transform is kept
  in state but is not applied.
- **Unaligned:** no accepted transform exists for the camera.

## Current boundaries

- Alignments are runtime state and are not persisted after application exit.
- Changing the reference is blocked after alignment work exists so transforms
  cannot silently be interpreted in the wrong coordinate system. Use **Reset
  all alignments** before choosing a different reference.
- Frozen frames are the latest available frames and may not be simultaneous.
  Timestamp skew is reported for this reason.
- Multi-feature refinement, two-point rotation/scale, alignment-profile
  persistence, and reference rebasing are the next planned stages.
