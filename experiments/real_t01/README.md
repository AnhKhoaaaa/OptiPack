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
- `paper_two_view.py`: required top-down/oblique 2-view trial comparison;
  outputs `paper_two_view_results.json`. Still manual ROI and too slow for MVP.
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
