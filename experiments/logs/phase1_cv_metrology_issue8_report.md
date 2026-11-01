# Phase 1 Issue #8 — 3D Metrology Integration Report

**Date:** 2026-11-01
**Branch:** `feat/m1-phase1-cv-v3`
**Status:** Functional integration completed, **production acceptance pending**.

## Scope

- Migrated V3 `ClosedFormInitializer` and `FastSDFFitter` to
  `backend/app/cv/metrology/{initializer,fitter}.py`; `sampled_outline`
  is included locally so production does not import experiment modules.
- Migrated `EpipolarMatcher` to `backend/app/cv/association/matcher.py`.
  Replaced a **greedy fallback mislabeled as Hungarian** with actual
  O(n³) Hungarian assignment and explicit dummy slots for unmatched items.
- Converted `backend/app/cv/metrology.py` to the package
  `backend/app/cv/metrology/__init__.py` while retaining old
  `estimate_item_dimensions_3d` and `quantify_measurement_uncertainty`
  imports for compatibility.
- Extended `CVMetrologyService` with `measure_segmented_pair` and
  `analyze_pair` to connect #6 ArUco calibration, #7 YOLOE auto masks
  and Census Parallax, 2-view matching and SDF cuboid fitting.
  No manual ROI JSON is needed in automatic inference.
- Each successful pair yields Contract v1.0.0 `DetectedItemMeasurement`
  containing `Dimensions3D`, `ItemUncertainty`, `MeasurementProvenance`
  and `VisualEvidence.bbox_2d_px`. The frozen contract has no separate
  `BoundingBox2D` model. Missing/failed measurements are reported rather
  than filled with invented heuristic dimensions.
- `estimate_fit_uncertainty` combines local SDF Jacobian curvature with
  reprojection and matching error floors, generates safety margins, and
  flags uncertain height or low confidence for user review.
  **These reported sigma values are heuristic proxies, NOT empirically
  calibrated 68% coverage intervals**; repeated captures are still needed.

## T01 development-set evaluation

### Reference-mask geometry regression

This experiment uses the old annotated masks and stored calibration poses
to **isolate the migrated geometry implementation**, not to claim automatic
ROI. The input/initialization is different from Phase 0 published benchmark.

| Trial | Correct stereo / physical GT | MAE(L/W), mm | MAE(H), mm |
| --- | ---: | ---: | ---: |
| Trial01 | 5/5 | 9.40 | 9.80 |
| Trial02 | 5/5 | 22.30 | 7.20 |
| Trial03 | 5/5 | 15.30 | 11.40 |
| **All** | **15/15** | **15.67** | **9.47** |

Report: `experiments/logs/phase1_metrology_annotated.json`.

This is *not* an apples-to-apples reproduction of Phase 0's 7.48mm
L/W and 10.30mm H, which measured V3's different ROI/initializer setup.
Direct regression tests with **identical input masks and initial
parameters** are required before claiming no 3D accuracy regression.

### Automatic ROI -> full 3D metrology

`yoloe-26n-seg.pt` text prompts, `imgsz=960`, global + four tiles,
board exclusion, Census parallax and frame-edge filtering. No ground-truth
ROI boxes supplied to inference. Ground truth is opened only after predictions
to evaluate identity, stereo association, coverage and MAE.

| Trial | Correctly measured / 5 physical objects | Unverifiable or wrong pairs | Conditional MAE(L/W), mm | Conditional MAE(H), mm | Pair wall time |
| --- | ---: | ---: | ---: | ---: | ---: |
| Trial01 | 5 | 0 | 7.10 | 12.20 | 22.08 s |
| Trial02 | 3 | 1 | 10.83 | 6.67 | 9.90 s |
| Trial03 | 4 | 0 | 10.38 | 9.00 | 10.63 s |
| **All** | **12/15 (80% measurement coverage)** | **1** | **9.13** | **9.75** | **14.20 s mean** |

The code output **13** 3D measurement records, but only **12** have both
views confirmed against the same ground-truth instance at mask IoU >=0.5.
The remaining Trial02 pair involves an oblique mask below IoU 0.5 and
cannot be certified as the correct physical item. The reported MAE is
conditioned on the 12 correctly measured physical objects, and must always
be read together with coverage and the unverified match count.

Report: `experiments/logs/phase1_metrology_automatic.json`.
The first pair includes cold model/prompt initialization. Times are on
the Windows Intel Core i5-13500H CPU and are not controlled P95 latency.

## Production blockers

1. **Measurement coverage 80%**, under desired >=95% detection quality.
   Detection misses and mask disagreement remain (Issue #7).
2. **One unverified stereo pair**; epipolar-only matching cannot guarantee
   identity for all similar/near-collinear objects. Use appearance and
   two-view shape consistency or request human review when ambiguous.
3. Conditional MAE is not an end-to-end all-item error metric;
   the original 7.48mm / 10.30mm gate cannot be inherited.
4. **Latency ~14.2s/capture pair** on test CPU. Model loading and tiled
   detection dominate; optimize runtime independently before production.
5. **Uncertainty proxies are uncalibrated**; their numeric sigma values
   and safety margin require repeated held-out physical measurements.
6. Need fresh held-out captures with unseen products and a fixed
   calibration procedure. No teammate solver/AI integration changed.

## Reproduction

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cv_metrology.py tests/test_cv_service.py -q
.\.venv\Scripts\python.exe -m experiments.real_t01.evaluate_phase1_metrology --mode annotated
.\.venv\Scripts\python.exe -m experiments.real_t01.evaluate_phase1_metrology --mode automatic --tiles
```

The old Phase 0 benchmark test file can rewrite its tracked historical
report and fail latency thresholds on busy Windows systems. It was not
modified or used as proof of production readiness here.
