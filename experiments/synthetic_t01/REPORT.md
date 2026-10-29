# T01 synthetic regression — evidence summary (2026-10-29)

**Result: synthetic regression PASS; real-image T01 gate NOT EVALUATED.**

## What ran (on the local Windows .venv)

- OpenCV detected real marker pixels in both rendered images: **4/4** in each.
- Known synthetic pinhole camera intrinsics used for `solvePnP`.
- Reprojection RMSE: **0.623 px** (top); **0.769 px** (oblique).
- Box top-face quadrilateral detected **from pixels**, using a blue-color rule
  intentionally tailored to the synthetic controlled scene.
- Two-view plane-height fit produced L/W/H:
  **197.14 / 135.81 / 105.25 mm** versus synthetic GT
  **200 / 140 / 105 mm**.
- Absolute L/W/H errors: **2.86 / 4.19 / 0.25 mm**.
- Footprint L/W MAE (this single item): **3.52 mm**.
- Height absolute error (this single item): **0.25 mm**.
- CPU pair processing time: **126.8 ms** (one observed run).
- Regression suite: **15 passed, 1 dependency deprecation warning**.
- `git diff --check`: no whitespace errors.

## Why this is not a T01 physical PASS

This is **one synthetic blue cuboid** from two perfect simulated cameras
with known intrinsics. Real data requirements remain: 5 physical boxes,
3 capture pairs, ground truth ruler measurements, real camera calibration,
realistic segmentation/pose success rate, and full MAE/latency evidence.
No physical data was evaluated. Current `item_segmenter.py`,
`metrology.py` and `/orders/analyze` remain placeholder implementations.

See `synthetic_results.json` for machine-readable measurements and
`README.md` for reproducible commands.

No code has been committed, pushed or merged.
