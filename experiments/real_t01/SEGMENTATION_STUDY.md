# T01 Class-Agnostic Segmentation Research — 2026-10-30

**Decision: NO model / algorithm promoted into the V2 or production pipeline.**
These are development-set, detection-box-only experiments. T01 remains **NOT PASSED**.

## Why these approaches

The previous COCO-pretrained YOLO26n-seg benchmark reached only **25/40**
manual ROI matches at confidence 0.05 (IoU >= 0.3). The tested objects
are small and unlike the COCO labels. We therefore investigated
(1) FastSAM-s, a **class-agnostic instance segmentation** model trained
to propose objects without requiring a COCO category, and (2) a
**planar homography** based on the known ArUco sheet, to find nonplanar
foreground by alignment and frame differencing.

Literature:
- Zhao et al., *Fast Segment Anything*, arXiv:2306.12156 (2023):
  https://arxiv.org/abs/2306.12156
- MIT *Foundations of Computer Vision*, Homographies:
  https://visionbook.mit.edu/homography.html
- OpenCV, *Basic concepts of the homography explained with code*:
  https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html

### Test A: FastSAM-s class-agnostic proposals (not production ready)

Research model: [third-party ONNX export, anakhiu/fastsam-onnx](https://huggingface.co/anakhiu/fastsam-onnx).
This is **not** the official FastSAM distribution. The source model was
exported from Ultralytics FastSAM-s; licensing needs careful review
(the host card says Apache-2.0, but acknowledges Ultralytics AGPL
provenance). Do not ship weights based on this test.

- ONNX fp32, 47,637,745 bytes. SHA-256:
  `8663b25472f06d36fc90f9b6262318292b760403c69c240360da5d1a3509f1ea`.
- Fixed model input **1024 x 1024** (letterbox, top-left origin),
  output0 `[1,37,21504]`, output1 mask prototypes
  `[1,32,256,256]`. CPU ONNX Runtime 1.23.2, 4 threads.
- 8 original sanitized JPGs, all 40 manually annotated coarse object ROIs.
  These annotations were used **ONLY after inference**, for evaluation.
- Per-image detection boxes created from `output0` scores, NMS
  around IoU 0.55; greedy one-to-one matching to labeled **coarse ROIs**
  with IoU >= 0.30. This is a lenient **proposal recall**, NOT true
  pixel-mask IoU, AP50, mAP, or end-to-end dimension accuracy.
- Two timed inference passes per photo after one warmup, excluding
  image decoding, preprocessing, NMS, mask generation and cuboid fitting.
  ONNX CPU median across eight photos was **~1.29 seconds per image**.
  Timing had substantial per-photo variation (~0.39–1.39 s), so
  a controlled dedicated CPU profile is still required.

| Method / ranking | ROI matched across all 8 photos | Measured implication |
|---|---:|---|
| Prior COCO YOLO26n-seg at confidence 0.05 | 25/40 (62.5%) | Fast but misses many objects |
| FastSAM-s, all accepted NMS proposals | **33/40 (82.5%)** | Better proposal recall, still 7 misses |
| FastSAM-s, top 20 confidence per image | 33/40 (82.5%) | Still many candidates |
| FastSAM-s, top 10 confidence per image | 25/40 (62.5%) | Dropped valid instances |
| FastSAM-s, top 5 confidence per image | **13/40 (32.5%)** | Unreliable naive object selection |

Mean NMS proposals: **65.1 per image** at confidence 0.05 (0.2 gave
the same 33/40 matches). FastSAM produces substantial extra
proposals, and selecting five highest confidence objects is not
adequate. Two-image **inference alone** is roughly 2.6 seconds at the
observed median, exceeding the **800 ms full-pair CPU target**.
This is NOT a substitute for manual ROI + GrabCut within current T01.

Machine-readable source: `segmentation_fastsam_eval.json`. The
model, weights, ONNX Runtime trial installation and exploratory scripts
were kept outside the repository during evaluation and removed when
the experiment ended. No backend dependency was changed.

### Test B: Plane-induced homography + parallax/color residual

For each of the three top-down/oblique pairs:
1. Detect common ArUco corner IDs in 720 x 540 landscape images.
2. Estimate `cv2.findHomography` (RANSAC, 3px threshold).
3. Warp the oblique view onto the top-down view's marker plane.
4. Compare Lab chroma and a weighted luminance residual; exclude the
   marker board, apply morphology and propose contours.
5. Evaluate on the top-down frame only. No object ROI enters estimation.

At a single exploratory image-difference threshold of 14, matches
at coarse ROI IoU >= 0.25 were:

| Pair reference | Matched | Candidate contours |
|---|---:|---:|
| Trial01 top-down | 1/5 | 16 |
| Trial02 top-down | 3/5 | 12 |
| Trial03 top-down | 4/5 | 10 |
| **Total** | **8/15** | **38 regions** |

Thresholds 22 and 30 performed worse overall. Shadows, specular
floor reflections, lighting/exposure shifts, objects not coplanar
with the fiducials, and image warping artifacts produce foreground
residuals unrelated to the true object mask. This result does NOT
support automatic object detection, so the experiment was discarded.
The geometric principle itself remains useful for calibration
checks, not for interpreting all image differences as objects.

### Why no integration was accepted

FastSAM-s was **better at proposing objects** but failed both runtime
and practical candidate-selection requirements. The homography-only
approach was lightweight but failed proposal recall. Neither was
validated with ground-truth pixel masks or independent photos, and
neither improved L/W/H MAE. Shipping either now would regress the
overall end-to-end T01 system.

**Do not replace V2, alter camera intrinsics, claim T01 GO,
or use the current eight images as an unbiased holdout.**

## Next controlled experiment

1. Acquire new capture sessions and correct instance masks, physical
   object dimensions, units and marker geometry (see
   `CAPTURE_PROTOCOL.md`). Confirm whether the Trial01 black
   two-driver object is the same physical item as the plain black box
   in Trials02–03.
2. Measure class-agnostic proposal recall @ IoU 0.5, segmentation
   mask IoU, false positives/image, and object correspondence across
   the two views, *before* any end-to-end metrology claim.
3. Prefer a compact domain-specific segmentation model only once
   there are enough masks for subject/session-disjoint validation.
   Test CPU p50 and p95 pair time including decoding, calibration,
   mask generation and cuboid estimation.
4. Preserve a manual-confirmation fallback for unknown objects or
   low-confidence measurements. A usable MVP fallback is not the
   same thing as passing the autonomous T01 gate.
