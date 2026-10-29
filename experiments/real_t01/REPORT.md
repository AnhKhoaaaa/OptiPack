# OptiPack T01 — Real capture evidence report

**Verdict: NOT PASSED / needs further CV metrology work.**

## Latest research — before / after (NOT an autonomous T01 pass)

| Approach | L/W MAE | H MAE | Evidence |
|---|---:|---:|---|
| Baseline silhouette/raycast | 24.73 mm | Not measured | 3 top-down views; untrusted H prior |
| CubeSLAM-inspired edge fit (v1) | 12.39 mm | 8.88 mm | 3 pairs, manual ROIs |
| **Silhouette-constrained cuboid (v2)** | **7.91 mm** | **6.12 mm** | 3 pairs, manual ROIs + GrabCut, provisional K |

V2 adds bidirectional silhouette-boundary distance (a shape-consistency
constraint) to cuboid fitting, reducing misleading matches to
floor grout/text/texture in global Canny maps. It is a custom
experiment motivated by geometric cuboid fitting (CubeSLAM)
and silhouette-consistency/visual-hull principles, **not an exact
reproduction** of either paper. No ground-truth dimensions enter
the optimizer; all errors are computed after fitting.

| Pair | V1 L/W MAE | V2 L/W MAE | V2 H MAE | V2 wall time for 5 items |
|---|---:|---:|---:|---:|
| Trial01 | 10.52 mm | 4.53 mm | 4.21 mm | 12.41 s |
| Trial02 | 16.48 mm | 11.18 mm | 9.61 mm | 38.10 s |
| Trial03 | 10.17 mm | 8.02 mm | 4.55 mm | 10.83 s |

**Status:** L/W and H means fall below 8/12 mm in this
**development-set ablation only**; **T01 is still NOT PASSED**
because pose is 7/8 <=2.5 px (<90%), processing time exceeds
800 ms per pair, camera intrinsics were fit in-sample, and
manual object ROIs are required. Several item errors still
exceed 12–20 mm; a 7.91 mm aggregate mean is not evidence
of robust generalization on new captures.

**Dataset consistency warning:** Trial01 'black' appears to be
a two-driver black speaker, while Trials 02–03 show a plain
black box. Verify whether these are the same physical item
and its actual dimensions before trusting aggregated MAE.
The user-provided units (assumed cm) and box resting orientations
also need independent confirmation.

## Dataset & provenance

- Eight **pixel-identical, GPS/EXIF-sanitized RGB JPEG copies** from the user-shared Drive folder. The source originals remain on Drive; `source_manifest.json` records Drive IDs and source/sanitized SHA-256 hashes.
- Three named top-down/oblique trial pairs; two additional left/right side views for Trial 02.
- Five object *labels* per capture; physical identity across trials, especially 'black' in Trial01, remains to be verified. Input dimensions interpreted as **centimetres** and converted to millimetres in `ground_truth.csv`; user has not explicitly confirmed measurement units.
- **40 manually seeded ROIs/crops** (five items per photo), with provenance in `roi_annotations.json` and `crop_annotations.json`. These are NOT automatic detections or pixel-perfect masks.

## Measured results on real pixels

| Gate / metric | Observed | Threshold | Verdict |
|---|---:|---:|---|
| Marker IDs 0–3 detected | 8/8 (100%) | >=90% | Meets marker visibility only |
| Pose reprojection <=2.5 px (estimated K) | 7/8 (87.5%) | >=90% | Does not meet threshold |
| Self-calibration in-sample RMS | 1.86 px | <=2.5 px | Diagnostic ONLY — estimated K fitted on these same images |
| Crude L/W baseline MAE | 24.73 mm across 15 object/trial cases | <=8.0 mm | Does not meet threshold |
| Height H MAE | NOT EVALUATED | <=12.0 mm | Not passed |
| Full pipeline CPU latency per two-image pair | NOT EVALUATED | <=800 ms | Not passed |

The L/W estimate uses a real segmentation from a manually seeded ROI and projects
a 2D object silhouette to a plane using an aspect-ratio height prior. The true
top-face corners and height are NOT recovered; silhouette inflation can cause
large errors. **Ground truth is read only for evaluation; it is not passed to the estimator.**

## Detailed exploratory L/W results

| Trial | Item | GT L/W (mm) | Estimated L/W (mm) | Abs error L/W (mm) |
|---|---|---|---|---|
| Trial01 | wood | 75/45 | 105.6/54.7 | 30.6/9.7 |
| Trial01 | white | 135/45 | 178.6/55.8 | 43.6/10.8 |
| Trial01 | gocheck | 65/65 | 90.4/80.9 | 25.4/15.9 |
| Trial01 | black | 140/45 | 154.3/81.3 | 14.3/36.3 |
| Trial01 | paper | 140/80 | 153.5/96.5 | 13.5/16.5 |
| Trial02 | wood | 75/45 | 88.5/66.0 | 13.5/21.0 |
| Trial02 | white | 135/45 | 152.5/98.1 | 17.5/53.1 |
| Trial02 | gocheck | 65/65 | 88.9/80.3 | 23.9/15.3 |
| Trial02 | black | 140/45 | 157.5/95.4 | 17.5/50.4 |
| Trial02 | paper | 140/80 | 155.7/123.7 | 15.7/43.7 |
| Trial03 | wood | 75/45 | 126.0/65.6 | 51.0/20.6 |
| Trial03 | white | 135/45 | 157.1/93.8 | 22.1/48.8 |
| Trial03 | gocheck | 65/65 | 87.5/68.4 | 22.5/3.4 |
| Trial03 | black | 140/45 | 166.9/58.8 | 26.9/13.8 |
| Trial03 | paper | 140/80 | 164.8/100.2 | 24.8/20.2 |

## Experimental multi-view cuboid fit — research only, NOT T01 gate

The experimental least-squares cuboid silhouette fit uses FOUR views of **Trial 02**
(top, oblique, left and right), 5 manually seeded segmentation ROIs and a
self-calibrated camera profile. It does **not** consume L/W/H ground truth
while fitting. It is NOT a tested fully automatic two-view T01 estimator.

**Diagnostic XY MAE: 12.46 mm; diagnostic H MAE: 17.12 mm**.
Both exceed T01 thresholds (8 / 12 mm); these are not acceptance metrics
because only one trial and four views were used, manual ROIs were provided,
and intrinsic calibration is provisional. Pixel silhouette residuals are high.

| Item | Estimated L/W/H (mm) | GT L/W/H (mm) | Abs error L/W/H (mm) | Pixel bbox RMS |
|---|---|---|---|---:|
| white | 142.9/56.7/51.8 | 135/45/65 | 7.9/11.7/13.2 | 46.3 |
| gocheck | 80.6/62.9/38.5 | 65/65/30 | 15.6/2.1/8.5 | 87.4 |
| black | 155.2/62.3/102.8 | 140/45/70 | 15.2/17.3/32.8 | 94.8 |
| paper | 131.4/91.5/63.6 | 140/80/50 | 8.6/11.5/13.6 | 61.3 |
| wood | 91.9/62.7/17.5 | 75/45/35 | 16.9/17.7/17.5 | 54.4 |

## Paper-inspired edge-constrained cuboid results (research only)

- Method basis: Yang & Scherer (2019), CubeSLAM, cuboid proposals
  and Canny/edge-distance scoring; independent Python/OpenCV/NumPy
  geometric adaptation, not a verbatim reproduction of the ROS/C++ code.
- Source: https://github.com/shichaoy/cube_slam (BSD-3-Clause).
- 3D cuboid parameters (center XY, dimensions L/W/H, yaw) are
  projected through ArUco-derived camera poses and refined against
  observed bounding boxes and Canny distance transforms.
- All real-photo variants still require manually initialized ROIs
  and intrinsics estimated from the same capture set.

| Condition | Mean L/W error | Mean H error | Time for 5 objects |
|---|---:|---:|---:|
| Trial 02, **4 views** | 7.42 mm | 7.62 mm | 33.65 s |
| Trial01, **2 views** | 10.52 mm | 5.70 mm | 7.74 s |
| Trial02, **2 views** | 16.48 mm | 9.18 mm | 17.87 s |
| Trial03, **2 views** | 10.17 mm | 11.75 mm | 8.42 s |
| **2-view mean across trials** | **12.39 mm** | **8.88 mm** | — |

Four-view exploratory errors can be below 8/12 mm on this one trial,
but the actual **two-view** average L/W error remains above the 8 mm
gate and processing time far exceeds 800 ms. None of these results
is an independently calibrated, autonomous acceptance benchmark.
Source capture repeats served as both development and evaluation;
a held-out physical test set is needed to support generalization.

## Marker corner refinement ablation

Leave-one-image-out calibration (other seven images fit intrinsics; test
image estimates its pose and reprojection error). This is still the
same capture session, not an independent device calibration.

| Corner refinement | In-sample RMS | LOO mean | LOO max |
|---|---:|---:|---:|
| none | 2.14 px | 2.13 px | 3.43 px |
| subpix | 1.86 px | 1.84 px | 2.91 px |
| contour | 2.02 px | 2.02 px | 3.02 px |

Subpixel refinement was retained because it gave the lowest
LOO mean and maximum error among these three methods.


## Camera and annotation constraints

- Intrinsics obtained by `cv2.calibrateCamera` from these same eight frames (assumed printed A4 board 40 mm marker size). This is NOT an independent camera calibration; held-out generalization and printed size must be validated.
- Original Trial 01 JPGs are portrait; they are rotated clockwise **in-memory** for consistent 4032×3024 camera calibration. The raw originals remain on Drive; the repo copies have private metadata removed.
- Each photo is a different camera pose; ArUco marker detection is independent of this intrinsics fit, but pose quality is not.
- No supervised neural-network training was performed. OpenCV ArUco and GrabCut need no pretrained weights.
- Trial 01 oblique angle is visually close to top-down, reducing useful parallax; this is an observation, not a quantified elevation angle.
- Human ROIs and unknown physical resting orientation of each box can bias measurements. A segmentation crop alone does not establish a top-face quadrilateral.

## Decision / next technical steps

1. **Do not close GitHub Issue #1 or claim T01 GO.** The exploratory v2 L/W aggregate is <=8 mm on this development set but the strict gate still fails for pose, manual ROI/unknown intrinsics, latency and missing held-out validation; several individual errors remain high.
2. Obtain **independent camera intrinsics** (camera calibration profile for the same smartphone mode) and verify printed 40 mm ArUco marker size.
3. Build reliable multi-object tabletop top-face segmentation and correspondence between top/oblique views; do not use bounding-box silhouette as a precise top-face measurement.
4. Independently validate two-view H and L/W measurement (including uncertainty), evaluate a held-out capture session and optimize runtime. If H fails, activate the documented height-review fallback; if L/W remains >15 mm, escalate to the team as specified by T01.
5. Expose only measurements validated by the CV module to `/orders/analyze`; the current router/production segmenter and metrology modules still contain placeholders.

## Reproduction

```powershell
.\.venv\Scripts\python.exe experiments\real_t01\download_images.py
.\.venv\Scripts\python.exe experiments\real_t01\inspect_captures.py
.\.venv\Scripts\python.exe experiments\real_t01\calibrate_dataset.py
.\.venv\Scripts\python.exe experiments\real_t01\prepare_dataset.py
.\.venv\Scripts\python.exe experiments\phase0_cv_metrology.py --dataset both
.\.venv\Scripts\python.exe -m experiments.real_t01.exploratory_fit  # optional; ~35 s
.\.venv\Scripts\python.exe -m experiments.real_t01.paper_two_view
.\.venv\Scripts\python.exe -m experiments.real_t01.silhouette_fit
.\.venv\Scripts\python.exe experiments\real_t01\generate_report.py
.\.venv\Scripts\python.exe -m pytest -q tests
```

No commits, pushes or merges are performed by these scripts.
