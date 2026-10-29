# OptiPack M1 T01 — Research decision and implementation trace

**Selected direction:** marker-calibrated, line/edge-constrained multiview cuboid
geometry, **inspired by CubeSLAM (Yang & Scherer, IEEE TRO 2019)**.
**Current status:** successful *research ablation*, **not a validated T01 GO**.

## Research audit (2026-10-29)

| Method | Evidence and repository | Suitability |
|---|---|---|
| **CubeSLAM** (Yang & Scherer, 2019) | https://ieeexplore.ieee.org/document/8708251/ ; author code https://github.com/shichaoy/cube_slam ; source LICENSE states **BSD-3-Clause** | **Chosen:** image edges + cuboid geometry, multiview constraints. Original code is ROS/C++, full SLAM not needed for known ArUco poses |
| **Fast box volume estimation using a RGB camera** (Kim, 2026) | https://doi.org/10.1016/j.patcog.2026.113404 | Known distinct-color reference plate and static camera; methods not available as verified portable code. Not used |
| **Measuring The Dimensions of 3D Rectangular Objects Using A 2D Camera** (Gülen & Akbati, 2022) | https://ijeedc.iraj.in/paperdetails/19248 | Uses ArUco scale + box edge/corner measures; high-level comparison, but insufficient as an off-the-shelf two-view metrology implementation |
| **Web Application to Measure Box Volume for Warehouse and Logistics using ArUco Marker and Mobile Camera** (Thalor et al., 2025) | https://www.jisem-journal.com/index.php/journal/article/view/1503 | Top/side acquisition differs from OptiPack's top/oblique capture; no verified official implementation imported |
| **aruco-homography** (Bischof, community implementation) | https://github.com/leobischof/aruco-homography ; **GPL-3.0** | Not copied/imported; licensing and focus (planar document rectification) differ |

### What was actually implemented

1. **ArUco detection & camera pose:** existing OptiPack
   `backend/app/cv/aruco_detector.py` uses OpenCV
   `DICT_4X4_50` 0–3, 40mm board geometry, solvePnP.
   Changed corner refinement to **SUBPIX** after comparing NONE,
   SUBPIX and CONTOUR with eight leave-one-view-out evaluations.
2. **Baseline comparator:** `real_baseline.py` with manually seeded
   object ROIs, GrabCut and raycast-based silhouette L/W, and an
   untrusted H prior explicitly flagged for user review.
3. **Previous 3D baseline:** `exploratory_fit.py` fits a projected
   cuboid's image-space axis-aligned boxes across four views (Trial 02).
4. **Research implementation:** `paper_edge_experiment.py` models
   a cuboid with position XY, yaw, L/W/H and projects its twelve
   candidate edges into each calibrated camera view. Selected visible
   edges are sampled, then compared to a Canny **distance transform**
   (Chamfer-like alignment); Levenberg–Marquardt-style iterative
   updates use finite-difference Jacobians. Bounding-box residuals
   stabilize optimization. The 4-view experiment uses Trial 02 top,
   oblique, left and right shots.
5. **Required two-view ablation:** `paper_two_view.py` fits each
   of the three top-down/oblique capture pairs *independently*.
   ROI seeds, fixed provisional camera intrinsics, and object/camera
   metadata are allowed; **no length/width/height ground truth enters
   any objective or initial guess**. GT is used only after fitting
   to compute errors.
6. **Calibration study:** `calibration_ablation.py` fits camera
   intrinsics on seven captures and tests pose reprojection on the
   omitted eighth. Mean error: NONE about 2.13 px, SUBPIX about
   1.84 px, CONTOUR about 2.02 px. This is cross-validation
   **within one shoot**, not independent camera calibration.

### Important distinction from the cited paper

This **does not port** CubeSLAM or claim to reproduce its published
numbers. The original paper also samples vanishing points and optimizes
SLAM poses; our lightweight **independent Python adaptation** reuses
its high-level geometric insight (box edges and distance-map scoring)
with **known ArUco camera poses**. No author C++ source was copied,
and no pretrained ML model or dataset was downloaded for this method.
References and license checks are recorded for transparency.

### Interpreting results and deciding next action

The target is **3 paired RGB captures / 5 physical objects** with
**L/W MAE <=8mm, H MAE <=12mm, pose <=2.5px in >=90% of images,
and CPU <=800ms per pair**.

Consult `REPORT.md` and result JSONs for exact measured values.
Four-view on one trial can beat the XY/H thresholds, but is NOT the
prescribed two-view experiment; the two-view average L/W error stays
above threshold, pose success is 7/8 and CPU latency is too high.

The optimizer currently uses **coarse manual ROIs + GrabCut**, not
an autonomous multi-object detector; treating these experiments as
production performance would be misleading. Several photographed
objects are rounded/deformable rather than ideal hard-edged cuboids.

**Technical next step:** improve automatic top-face/keypoint/line
extraction, validate camera K independently, run a held-out session,
then optimize the numerical fit for CPU. If real two-view metrology
cannot pass the fixed gate, formally switch to review-based fallback
1A after obtaining team approval. Avoid changing acceptance criteria
to fit the observed results.

### Reproduce

```powershell
.\.venv\Scripts\python.exe -m experiments.real_t01.calibration_ablation
.\.venv\Scripts\python.exe -m experiments.real_t01.calibrate_dataset
.\.venv\Scripts\python.exe -m experiments.real_t01.real_baseline
.\.venv\Scripts\python.exe -m experiments.real_t01.paper_edge_experiment
.\.venv\Scripts\python.exe -m experiments.real_t01.paper_two_view
.\.venv\Scripts\python.exe experiments\real_t01\generate_report.py
.\.venv\Scripts\python.exe -m pytest -q tests
```

All 8 **privacy-sanitized, pixel-identical JPEG copies** and labeled ROI
metadata are part of the experiment. The original photos remain in Drive;
public GitHub copies exclude GPS, XMP and private EXIF tags. Benchmark result files intentionally
remain in the branch as provenance; transient caches are ignored or
removed. No commit, push, merge, or remote-source modification.
