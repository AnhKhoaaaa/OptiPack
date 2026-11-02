# OptiPack Phase 1 Issue #7 — Automatic ROI

This module implements zero-shot YOLOE proposals + instance masks, board
exclusion, two-view Census parallax verification, and full-resolution RGB item
crops. It does not use ROI annotations for inference.

## Environment

From repo root (Windows PowerShell):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-cv.txt
```

Text-prompt inference (default `yoloe-26n-seg.pt`) uses an additional
Ultralytics/CLIP tokenizer and MobileCLIP2 text encoder. These are downloaded
on first use and require internet; afterward `detector.py` caches checkpoint
and prompt-specific embeddings under `backend/app/cv/segmentation/.cache/`.
Prompt-free `yoloe-26n-seg-pf.pt` needs no text encoder but can have many
false positives. Weights and encoder assets are excluded from Git.

Usage:

```python
segmenter = YOLOESegmenter(model_path="yoloe-26n-seg.pt", imgsz=960, tiled_inference=True)
calibration = CVMetrologyService(K, D, image_size_px=(4032,3024)).calibrate_pair(top, oblique)
result = SegmentationPipeline(segmenter=segmenter).run(top, oblique, calibration)
# result.top_items contains bbox, mask, contour, confidence, item_id, crop_path.
```

Images should be oriented according to the calibration profile before calling
`calibrate_pair`. Ground homographies apply to undistorted pixels; the
pipeline undistorts images and masks only for the parallax verification stage.
Output boxes/masks remain in original image coordinates.

The explicit `candidate_boxes=...` detector call is retained for historical
Phase 0 comparison only, and is **not** the automatic mode.

## Tests and benchmark

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cv_segmentation_phase1.py tests/test_cv_service.py -q
.\.venv\Scripts\python.exe -m experiments.real_t01.evaluate_auto_roi_phase1 --model yoloe-26n-seg.pt --imgsz 960 --tiles
```

The benchmark runs inference first, then reads `golden_masks/*.png` **only**
for metrics. It measures per-view mask-matched recall at IoU >= 0.5, false
positives, and per-pair latency. T01 was used for calibration/model selection,
so do not report it as independent generalization validation. Run separate
captured unseen orders to validate before production use.

**Caveats:** PYTORCH/CLIP model setup and CPU throughput can dominate the
latency. Thresholds must be tuned on a development set and assessed on held-out
images. Only the top-view candidate set is filtered by two-view parallax;
oblique detections remain available for downstream view association (#8).
Public/commercial distribution also requires checking Ultralytics license
obligations (AGPL-3.0 or appropriate commercial license).

## Model backend and experimental limitations

`yoloe-26n-seg.pt` runs PyTorch inference with text prompts. After
`save_prompt_embeddings`/`load_prompt_embeddings`, it can be exported once
to static ONNX using `YOLOE.export(format="onnx", imgsz=960)`; ONNX inherits
those class names and cannot accept new prompts. The exported `.onnx` model
uses ONNX Runtime via Ultralytics postprocessing.

Option `--tiles` enables global + four overlapping 65%-size image tiles,
merged by bounding-box IoU/containment. It improves recognition of small
items but adds latency. Automatic detection excludes calibration-board
proposals and rejects objects intersecting a 2.5%-wide capture-frame margin:
such partial objects cannot be reliably measured. The margin can be disabled
or adjusted with `frame_margin_fraction=0` where the capture protocol differs.

Parallax filtering is a best-effort geometry heuristic and was insufficient
by itself to reject prompt-free model false positives on T01. Compare with
`--skip-parallax` and validate on new scenes before relying on it.

## Reproduced T01 result (2026-11-01)

The selected `yoloe-26n-seg.pt` PyTorch text-prompt model with `--tiles`,
two-view parallax and 2.5% frame exclusion achieved **27/30 matched instances**
(recall 90.0% at IoU >= 0.5), **1 false positive** and **mean matched-mask IoU
0.8766** on 3 T01 photo pairs. Mean CPU wall latency was **11.21 seconds
per pair**, including model/prompt initialization (last two pairs: 8.03 and
7.67 seconds). Full results: `experiments/logs/phase1_auto_roi_final.json`.

The frozen-class ONNX export ran but measured **16/20 recall, 1 FP, 17.16 s**
average on Trial02–03; it was slower than PyTorch on this Windows Intel CPU.
Therefore the current recommendation is the PyTorch backend, not ONNX.
Do **not** label this build as passing a 95%-recall or real-time latency gate.

The ROI JSON is not used for inference, but the camera intrinsics for T01
are an in-sample estimated profile. Generalization and end-to-end 3D MAE after
switching to automatic ROI have **not** been verified. Capture new held-out
photos and run downstream #8 measurements before declaring production-ready.

## PR review: memory footprint

The detector retains only bounding-box-sized binary mask crops for candidate
proposals during tiled inference, then creates full-resolution masks **after**
cross-tile deduplication. Public outputs and pixel geometry remain unchanged.
Trial01 re-evaluation on 2026-11-01 matched 10/10 instances, FP=0, using
this implementation. This run took 45.96 seconds per pair on an extremely
memory-constrained Windows session; do not interpret it as a controlled
performance comparison against earlier warm CPU latency measurements.
