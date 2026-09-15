# Camera Alignment

## Purpose

The Alignment window registers any streaming target camera to any streaming
reference camera. Camera names and spectral roles are not hard-coded.

- **Align to (reference):** establishes the output pixel space and does not
  move.
- **Transform (target):** receives the calculated registration transform.

Registration is independent of ordinary layer position, opacity, and display
layout.

## Guided one-point workflow

1. Confirm that both cameras have green status dots on the main page.
2. Select the reference camera under **Align to**.
3. Select the camera that should move under **Transform**.
4. Open **Alignment** and choose **Freeze all running cameras**.
5. Review the displayed maximum timestamp skew. Keep the scene still when
   cameras are not hardware-synchronized.
6. Click a distinct physical feature in the frozen reference image.
7. Click the same feature in the frozen target image.
8. Inspect the 50% overlay preview and the X/Y movement.
9. Choose **Accept**, **Reject**, or **Undo accepted**.
10. Select the next target and repeat. The reference remains fixed.

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
- Automatic edge-based refinement, two-point rotation/scale, alignment-profile
  persistence, and reference rebasing are the next planned stages.
