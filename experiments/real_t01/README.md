# T01 — User-supplied real RGB capture dataset

**Source:** https://drive.google.com/drive/folders/1_rKzBn4uuPKspFRDF7G_TwtU255h-xeG

**Physical test set:** Five rigid household/retail packages with a printed A4
four-ArUco board, DICT_4X4_50 IDs 0–3, nominal printed side 40 mm.
Three trial pairs were named by the photographer. Trial 02 also includes
`leftside` and `rightside` auxiliary images. This public repo contains
**GPS/EXIF-sanitized copies** in `images/` with identical decoded pixels;
the untouched original JPEGs remain on Drive. `source_manifest.json`
records both the original source and sanitized copy SHA-256 digests.

## Ground truth supplied by the user

| item_id | Appearance | L × W × H (mm) |
|---|---|---:|
| white | White rectangular speaker | 135 × 45 × 65 |
| gocheck | GoCheck black square box | 65 × 65 × 30 |
| black | Black rectangular speaker/box | 140 × 45 × 70 |
| paper | TOP GIA tissue/paper pack | 140 × 80 × 50 |
| wood | Small wooden box | 75 × 45 × 35 |

**Units are an explicit ASSUMPTION:** the user provided 13.5, 4.5,
6.5, etc. without naming a unit. We interpreted these as **cm** (converted
×10 to mm) because the pictured objects are centimetre-scale. Confirm
before accepting physical MAE results. The user did not provide object
resting orientation relative to canonical L/W/H; trial-to-trial rotation
can alter which dimension is vertical.

## Pipeline and files

- `download_images.py`: download and remove private EXIF/GPS/XMP metadata from eight photographs while preserving decoded pixels; verify SHA-256 of repo copies and retain separate source hashes.
- `inspect_captures.py`: detect markers from pixels (all 8 show IDs 0–3)
  and create marker-annotated contact sheet.
- `calibrate_dataset.py`: *provisional* OpenCV self-calibration based on
  the same eight images. This is NOT independently calibrated intrinsics;
  `camera_profile_estimated.json` explicitly records the limitation.
- `roi_annotations.json`: coarse object rectangles hand-initialized
  by visual inspection of each image; no claims of automatic recognition.
- `prepare_dataset.py`: crops 40 views (5 objects × 8 source images)
  into `crops/`, and records provenance in `crop_annotations.json`.
  `crop_contact_sheet.jpg` is a human QA montage.
- `real_baseline.py`: image-pixel ArUco + camera pose and **experimental**
  manual-ROI-seeded GrabCut XY silhouette baseline. Uses a dimension
  prior for H with `requires_user_review=True`. GT values are used
  **only after prediction** to compute real-photo L/W errors.
- `real_results.json` and `REPORT.md`: machine-readable evidence and
  full candid findings.
- `exploratory_fit.py` and `experimental_3d_results.json`: additional four-view
  cuboid fitting using Trial 02 top/oblique/left/right images. This fits L/W/H
  from segmented silhouettes without passing ground truth to the optimizer,
  but is **research-only, not a passing T01 two-view gate**.
- `paper_edge_experiment.py`: independent CubeSLAM-inspired 4-view cuboid
  edge-fitting prototype; results in `paper_edge_experiment.json`.
- `paper_two_view.py`: original CubeSLAM-inspired 2-view comparison;
  outputs `paper_two_view_results.json`. Still manual ROI and too slow for MVP.
- `silhouette_fit.py`: refined method, replaces unconstrained global Canny-edge
  attraction with a bidirectional silhouette-boundary distance and retains
  bbox stabilization; same ArUco calibration/manual ROI protocol. Results
  recorded in `silhouette_experiment.json`. Research only.
- `calibration_ablation.py`: marker subpixel-refinement study with
  leave-one-image-out validation (`calibration_ablation.json`).
- `RESEARCH_DECISION.md`: audited paper/source selection, license notes and
  a precise description of the adapted method.
- `tests/test_real_t01.py`, `tests/test_paper_cuboid_geometry.py`:
  provenance, regression, geometry, and no-fake-GO tests.

The Phase 0 production **H triangulator is not yet implemented on these
real photos** and current `backend/app/cv/metrology.py` / API integration
remain placeholders. Neither the preliminary K fitted on this same
dataset nor manual seeded ROIs may be represented as autonomous real-world
metrology success.

## Reproduce (Windows PowerShell, repo root)

```powershell
.\.venv\Scripts\python.exe experiments\real_t01\download_images.py
.\.venv\Scripts\python.exe experiments\real_t01\inspect_captures.py
.\.venv\Scripts\python.exe experiments\real_t01\calibrate_dataset.py
.\.venv\Scripts\python.exe experiments\real_t01\prepare_dataset.py
.\.venv\Scripts\python.exe experiments\phase0_cv_metrology.py --dataset both
.\.venv\Scripts\python.exe -m experiments.real_t01.exploratory_fit  # prior baseline
.\.venv\Scripts\python.exe -m experiments.real_t01.calibration_ablation
.\.venv\Scripts\python.exe -m experiments.real_t01.paper_edge_experiment
.\.venv\Scripts\python.exe -m experiments.real_t01.paper_two_view
.\.venv\Scripts\python.exe -m experiments.real_t01.silhouette_fit
.\.venv\Scripts\python.exe experiments\real_t01\generate_report.py
.\.venv\Scripts\python.exe -m pytest -q tests
```

`--require-go` on the Phase 0 script exits nonzero until both the
synthetic regression and requested physical acceptance gate pass.

## Acceptance decision

Current real baseline: **NOT PASSED**; see `REPORT.md`.
Do not close GitHub T01 Issue #1 based on marker detection alone.
Need independent intrinsics, robust automatic segmentation and
top-face geometry, real two-view H triangulation and pair-level CPU
latency. For poor height estimation use documented Fallback 1A
(top-down L/W + mandatory UI confirmation of H); if L/W also fail,
escalate to team rather than silently accepting fallback.


### 2026-10-30 paper-guided pose + acceptance audit

Run the **optional** experiment and conservative gate audit with the
same eight local images and the same provisional intrinsics:

```powershell
.\.venv\Scripts\python.exe -m experiments.real_t01.fast_pose_ablation
.\.venv\Scripts\python.exe -m experiments.real_t01.t01_quality_audit
.\.venv\Scripts\python.exe experiments\real_t01\generate_report.py
.\.venv\Scripts\python.exe -m pytest -q tests
```

- `fast_pose_ablation.py` / `fast_pose_ablation.json`: iterative,
  IPPE, EPnP pose solvers with marker detection at full, half and 35%
  image resolution and full-size corner refinement. **0.5x+ITERATIVE**
  reduces marker detection+PnP median from 154.55 to 49.16 ms/image
  with the same 7/8 pose threshold count. This is NOT a new camera
  calibration or production pipeline default.
- `t01_quality_audit.py` / `t01_quality_audit.json`: machine-readable,
  conservative status including dataset sensitivity. With one suspect
  Trial01 `black` match excluded, diagnostic XY MAE is **8.27 mm**
  rather than the full 15-case **7.91 mm** (not a repaired dataset).
- `tests/test_fast_pose_ablation.py` and
  `tests/test_t01_quality_audit.py`: synthetic pose, marker extraction,
  invalid-input and anti-overclaim regression checks.

See `RESEARCH_DECISION.md` for candidate papers, negative ablations,
the full trial protocol, and important data limitations. The
end-to-end T01 verdict remains **NOT PASSED**; no production code
or remote Git branch has been changed by these research scripts.


### Optional calibration-model experiment (2026-10-30)

A paper-guided camera calibration comparison is provided **for evaluation
only**. Run these after preparing the original eight sanitized photos:

```powershell
.\.venv\Scripts\python.exe -m experiments.real_t01.calibration_model_variants
.\.venv\Scripts\python.exe -m experiments.real_t01.calibration_metrology_experiment
.\.venv\Scripts\python.exe experiments\real_t01\generate_report.py
```

`calibration_model_variants.py` compares six constrained camera models
using leave-one-image-out marker reprojection. The free-tangential-
distortion candidate scores **8/8** images within 2.5 px (vs baseline
**6/8** under LOO) and has **1.686 px** LOO mean (baseline **1.838 px**).
`calibration_metrology_experiment.py` evaluates the candidate on the
existing two-view V2 pipeline without writing a replacement camera
profile. On the same 15 labeled cases the candidate obtains
L/W **7.723 mm** and H **5.898 mm** (V2 default **7.909/6.119 mm**).

**No default calibration or production metrology code is changed.**
This is still the same 8-photo capture session, not independent
calibration or held-out validation; choosing among six candidates
introduces optimistic selection bias. Trial03 H also worsens slightly.
`REPORT.md` and `RESEARCH_DECISION.md` document the risks.
The trial shortcuts to GrabCut were **rejected/removed** because
their MAE regressed, despite some CPU savings.


### Class-agnostic segmentation research (2026-10-30)

See `SEGMENTATION_STUDY.md` for paper sources, FastSAM-s ONNX CPU
benchmark (33/40 coarse ROI matches, ~1.29 s/image inference, 65
proposals/image) and a failed ArUco plane-homography foreground trial
(8/15 matches). Both are **rejected as replacements for production
T01**; the V2 silhouette fitting, GrabCut and camera profile remain
unchanged. Machine-readable FastSAM evidence:
`segmentation_fastsam_eval.json`.

`CAPTURE_PROTOCOL.md` explains how to collect independent photos,
confirmed object dimensions, camera calibration and pixel-level
instance masks needed before training/validating another model.
