# OptiPack / Member 1 / T01 — synthetic geometry regression

These two generated images are deliberately **SYNTHETIC** and are NOT evidence
that the physical-camera Phase 0 gate has passed. They are repeatable software
fixtures for implementing and debugging camera pose, plane intersection, and
two-view size recovery.

## Reproduce

From repository root, with the project's Python environment:

```powershell
.\.venv\Scripts\python.exe experiments\synthetic_t01\generate_fixture.py
.\.venv\Scripts\python.exe experiments\phase0_cv_metrology.py
.\.venv\Scripts\python.exe -m pytest -q
```

Expected artifacts:

- `optipack_synthetic_top.png` and `optipack_synthetic_oblique.png`: a
  fixed blue cuboid (L/W/H = 200/140/105 mm), A4 ArUco board with four 40 mm
  markers 0, 1, 2, 3. The box does not move between camera views.
- `ground_truth.json`: exact camera intrinsic matrix and synthetic scene
  ground truth. The evaluator uses known intrinsics but does NOT pass the
  3D cuboid corners to the fitting algorithm.
- `benchmark.py`: detects ArUco corners from pixels, estimates pose with
  `solvePnP`, detects the blue top face using a *synthetic-only* color rule,
  matches quadrilateral corners between two views, fits the height of a common
  plane, and reports L/W/H errors and CPU time.
- `synthetic_results.json`: regenerated result; marked
  `"real_world_phase0_pass": false`.

## Scope / limitations

This is a **single-box synthetic regression**, using a known pinhole camera,
zero lens distortion, and a deliberately high-contrast blue box. It does not
implement generic multi-item segmentation, lens calibration from real photos,
or robust height estimation under clutter and occlusion. It is **not** a
Phase 1 production metrology pipeline.

The existing `item_segmenter.py`, `metrology.py`, and `/orders/analyze`
endpoint still contain placeholders and were left unchanged.

## Actual T01 exit gate (still pending)

As specified in `document/02a_member1_computer_vision.md`, use five *physical*
rigid boxes and three capture pairs with ruler ground truth. Report marker
detection/pose success rate >=90%, reprojection RMSE <=2.5 pixels, footprint
L/W MAE <=8 mm, height MAE <=12 mm, CPU <=800 ms per photo pair.
If height reconstruction fails, communicate Fallback 1A: top-down footprint
with mandatory user confirmation of height. Do NOT report synthetic PASS as
real T01 GO.

## Version control

Work on `feat/m1-cv-metrology`; do not change shared contract v1.0.0 or push
without team review. Link evidence to GitHub issue #1.
