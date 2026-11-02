# OptiPack — Phase 1 Issue #7: Automatic ROI & Instance Segmentation

**Run date:** 2026-11-01
**Status:** Functional implementation verified on T01 development captures; **quality/latency gate not fully met**.
**Branch:** `feat/m1-phase1-cv-v3`
**Baseline:** Phase 0 V3 manual-annotation-guided candidate boxes (untouched).

## 1. Scope and evidence of autonomy

The production path invokes `YOLOESegmenter.detect_and_segment(image,K,D,pose)`
**without** `candidate_boxes`. It gets bounding boxes, masks and confidence
from real YOLOE model inference, excludes the A4 fiducial sheet using
projected geometry, optionally rejects planar artifacts using two-view
Census Parallax, then generates high-resolution crops with unique IDs.

The benchmark performs inference and crop extraction **before** opening
golden segmentation masks for evaluation. `roi_annotations.json` and
`golden_masks/metadata.json["masks"]` do not enter model inference.
The previous explicit `candidate_boxes=...` route is retained only for
controlled comparison with the Phase 0 baseline.

Calibration uses ArUco live-image pose and camera intrinsics taken from
the T01 in-sample profile. This does *not* mean intrinsics are independently
calibrated on a new phone.

## 2. Verified implementation artifacts

- `backend/app/cv/segmentation/detector.py`: zero-shot YOLOE text mode,
  optional ONNX inference, binary instance masks, class/confidence, tiled
  detection and cross-tile dedup, exclusion of reference board and truncated
  frame-edge objects, explicit legacy GrabCut baseline.
- `backend/app/cv/segmentation/parallax_verifier.py`: original Census/Sobel
  two-view shadow/ground residual verifier, preserved and integrated.
- `backend/app/cv/segmentation/pipeline.py`: orchestrates two views using
  `PairCalibration` from #6. Undistorts images and masks when applying
  ground-plane homography; top view is filtered by parallax, oblique remains
  available for later association (#8).
- `backend/app/cv/segmentation/cropping.py`: high-resolution RGB patches,
  unique item IDs, path-safe JPEG writing under
  `backend/app/api/static/crops`.
- `tests/test_cv_segmentation_phase1.py`: no-annotation model interface,
  mask/board exclusion, tile merge, cropped-image persistence, failure cases,
  parallax rejection and frame truncation.
- `experiments/real_t01/evaluate_auto_roi_phase1.py`: actual independent
  prediction-versus-ground-truth evaluation protocol. See JSON metrics.

## 3. Final T01 benchmark (PyTorch text-prompt, tiles, parallax)

Configuration: `yoloe-26n-seg.pt`, 9 fixed object prompts, `imgsz=960`,
`conf=0.15`, global + four overlapping tiles, deduplication, projected
ArUco board exclusion, 2.5% capture-border exclusion and two-view Census.

**Metric definitions:** Recall = number of one-to-one matched instance masks
at IoU >= 0.5 divided by total golden instances. A prediction not matched
to golden instance counts as false positive. Mask IoU mean uses matched
instances only. For six images (three top/oblique pairs), there are 30
ground-truth *image instances*, representing five physical items per trial.

| Trial | Correct / GT | Unmatched predictions (FP) | Wall latency / pair |
| --- | ---: | ---: | ---: |
| Trial01 | 10 / 10 | 0 | 17.923 s |
| Trial02 | 8 / 10 | 1 | 8.032 s |
| Trial03 | 9 / 10 | 0 | 7.667 s |
| **Total / mean** | **27/30 (90.0% recall)** | **1 FP** | **11.207 s / pair** |

Matched-instance mask IoU mean **0.8766**, median **0.9111**, minimum
**0.6563**. Thus the detected masks are often accurate, but **3/30
instances are missed**. Results and per-prediction scores:
`experiments/logs/phase1_auto_roi_final.json`. Predicted-box contact sheet:
`experiments/logs/phase1_auto_roi_preview.jpg`.

The first pair includes model initialization; latter pairs approximate a
loaded-model scenario, but no statistically valid P50/P95 latency benchmark
has been run. CPU: Intel Core i5-13500H, Windows, PyTorch CPU.

## 4. Ablations and rejected alternatives

| Mode / input | Measured set | Matched / GT | FP | Mean pair wall time |
| --- | --- | ---: | ---: | ---: |
| Prompt-free YOLOE, full frame, no parallax | Trial01 | 9/10 | 36 | 38.2 s |
| Prompt-free YOLOE, parallax | Trial01–02 | 18/20 | 49 | 18.4 s |
| Text-prompt full-frame 960 | Trial02–03 | 13/20 | 1 | 4.5 s |
| Text-prompt full-frame 1280 | Trial02–03 | 13/20 | 1 | 5.0 s |
| Text-prompt tiled 960, no parallax | Trial02–03 | 17/20 | 1 | 8.8 s |
| Text-prompt tiled 960, parallax, before frame filter | Trial01–03 | 27/30 | 6 | 10.3 s |
| **Text-prompt tiled 960, parallax, frame filter** | **Trial01–03** | **27/30** | **1** | **11.2 s** |
| ONNX exported with fixed text prompts, tiled 960, no parallax | Trial02–03 | 16/20 | 1 | 17.2 s |

Model/download and warm-up influence wall-time figures; comparisons are not
controlled steady-state throughput benchmarks. ONNX export was successful,
but was **slower and slightly less accurate** on this hardware and is
not the recommended current backend.

Filtering incomplete edge objects eliminated 5 false positives on T01
without losing a matched target in this set. This filter is **capture-
protocol dependent** and may discard real objects on other images; the
`frame_margin_fraction` is adjustable.

**Note:** Phase 0's previously published 97.5% recall / 0 FP / 147.8 ms
was measured with candidate boxes from annotated metadata, not actual
automatic ROI proposals. It is **not directly comparable** and is not used
as new model validation.

## 5. Test verification and risks

- Issue #7 and Issue #6 / CV related tests: **30 passed**.
- Project tests excluding `tests/test_phase0_cv_metrology_v3.py`:
  **98 passed, 1 warning**.
- The existing Phase 0 V3 benchmark file remains a known
  environment-dependent latency failure (0B, 0C, 0D thresholds on this CPU).
  Running its tests overwrites a tracked old report; the report was
  restored to the original committed content, not modified for this work.
- 15 actual RGB crops were saved during a prior `--save-crops` run.
  Model/checkpoint files and encoder cache remain local and Git-ignored.
- Open limitations: **recall below 95% target**, wall latency much greater
  than ~200 ms gate, one FP, possible partial object dropout at image edges,
  no unseen-scene validation and no downstream 3D MAE regression with
  automatic predictions.
- Do not claim end-to-end production readiness or no-human-intervention
  for arbitrary unseen captures.

## 6. Next engineering actions

1. Capture at least three **held-out** orders with different object sizes,
   backgrounds, illumination and a fresh camera profile. Do not tune
   thresholds on this held-out set.
2. Test a more diverse class prompt profile or geometry-guided recovery for
   small black/low-texture items on a *separate development set*. Compare
   mAP50, recall, per-mask IoU, FP and latency.
3. Profile tile count / batching / CPU-specific inference (OpenVINO versus
   ONNX/PyTorch) before optimization; preserve accuracy.
4. Feed auto masks into #8 3D measurement; recompute MAE(L,W,H) and
   uncertainty with **the same predicted object identities**, not old JSON
   labels.
5. Keep the Phase 0 pipeline and its metrics unchanged until the new
   evaluation gates pass and teammate integration review is complete.

**References:** Ultralytics YOLOE documentation:
https://docs.ultralytics.com/models/yoloe/ (static prompt embedding export,
ONNX and prompt-free modes). Check AGPL-3.0 / commercial license requirements
before distributing proprietary software.
