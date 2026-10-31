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
The initial two-view edge experiment (v1) averaged L/W MAE **12.39 mm**,
H MAE **8.88 mm**. The subsequent manually seeded silhouette-constrained
v2 experiment averaged **7.91 mm L/W** and **6.12 mm H** across the same
three pairs. These development-set numbers do **not** pass T01: pose
success is 7/8, ROI segmentation is manual-seeded, K is self-calibrated,
no held-out session exists and CPU latency remains seconds, not 800 ms.

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
.\.venv\Scripts\python.exe -m experiments.real_t01.silhouette_fit
.\.venv\Scripts\python.exe experiments\real_t01\generate_report.py
.\.venv\Scripts\python.exe -m pytest -q tests
```

All 8 **privacy-sanitized, pixel-identical JPEG copies** and labeled ROI
metadata are part of the experiment. The original photos remain in Drive;
public GitHub copies exclude GPS, XMP and private EXIF tags. Benchmark result files intentionally
remain in the branch as provenance; transient caches are ignored or
removed. No commit, push, merge, or remote-source modification.


### Iteration v2 — silhouette-constrained cuboid fitting (2026-10-29)

**Research origin:** CubeSLAM (Yang & Scherer, 2019) uses geometric
cuboid proposals and alignment to image edges:
https://doi.org/10.1109/TRO.2019.2909168
(source: https://github.com/shichaoy/cube_slam).
The idea of using calibrated silhouettes to constrain 3D shape is
established in visual-hull research; see Kristen Grauman,
*A Statistical Image-Based Shape Model for Visual Hull Reconstruction
and 3D Structure Inference* (MIT AI TR 2003-007):
https://dspace.mit.edu/entities/publication/3b27690e-62d4-4c89-aacc-98ca46fe185c

**We did NOT port CubeSLAM or implement a full visual hull.** We authored
a compact bidirectional contour-matching objective in
`silhouette_fit.py` and tested it with the already known ArUco camera
poses. A rough human ROI initializes GrabCut. For each candidate
cuboid, the eight corners are projected with `cv2.projectPoints`,
their convex hull approximates its visible silhouette, and the
following two residuals constrain L/W/H, center XY and yaw:

1. **Predicted -> observed:** equal-distance samples of the projected
   cuboid convex hull are penalized by a distance transform of the
   observed binary GrabCut contour.
2. **Observed -> predicted:** equally sampled observed contour points
   are penalized by distance to their nearest projected hull segment.
3. **BBox stabilization:** per-view projected min/max x/y residuals
   with reduced weight, to preserve scale despite imperfect silhouettes.

The reverse term discourages fitting a tiny box to unrelated internal
edges. Unlike v1, internal text markings and floor grout are not
attraction targets. We keep the **same eight bbox-fit initialization
seeds**, 2 images per trial and the same manually seeded ROIs and K.
No ground-truth dimension is used in the estimator or model selection
for each object. The benchmark CSV is loaded only to measure error
**after** each fit. This is methodological *inspiration*, not a paper
reproduction, an ML model, or an automatic production solution.

**Observed on the same development set (5 labels x 3 pairs):**

| Method | Mean L/W MAE | Mean H MAE |
|---|---:|---:|
| Original manual-ROI raycast baseline | 24.73 mm | Not measured |
| v1 two-view global Canny edge alignment | 12.39 mm | 8.88 mm |
| **v2 two-view silhouette boundary alignment** | **7.91 mm** | **6.12 mm** |

V2 per-pair L/W MAE = 4.53 (Trial01), 11.18 (Trial02),
8.02 mm (Trial03). Trial02 remains a failure under the L/W
threshold and several individual item errors exceed 20 mm.
CPU wall time across two runs was **5.53–12.41 s (Trial01),
14.96–38.10 s (Trial02), 8.24–10.83 s (Trial03)** for five items;
substantial CPU-load variability, always far above the 800 ms gate. Pose is still 7/8 at <=2.5 px
with in-sample calibration. The T01 gate remains **NOT PASSED**.
No held-out capture data has been evaluated; the method was designed
and assessed using the same 8 photos, so 7.91 mm is not an unbiased
generalization estimate.

**Dataset QA:** the 'black' label in Trial01 visibly has two white
circular drivers, while Trials02-03 show an all-black cuboid. This
could be a DIFFERENT OBJECT, which would invalidate one GT match.
The owner must verify object identity, units (cm assumed), resting
orientation and physical measurements before treating this set as
an acceptance benchmark.

**Reproduction:** `python -m experiments.real_t01.silhouette_fit`;
result is `silhouette_experiment.json`. New geometric regression tests
are in `tests/test_silhouette_cuboid.py`. Next priority is an
autonomous object ROI/keypoint pipeline and a fast implementation, then
independent camera calibration and held-out benchmark captures.


## Iteration v3 research — FASTER fiducials & honest acceptance gate (2026-10-30)

**Outcome:** Retain an **opt-in RESEARCH ablation** for marker detection and
automatic acceptance auditing; **do not modify production metrology, V2
silhouettes, camera calibration, or official acceptance rules**. No GitHub
push/merge as part of this iteration.

### Literature investigated and why each was selected/rejected

| Work | Relevant technique | Empirical decision |
|---|---|---|
| Collins & Bartoli, *Infinitesimal Plane-Based Pose Estimation*, IJCV 2014, doi:10.1007/s11263-014-0725-5 | IPPE generates possible solutions from coplanar marker corners | **Evaluated, not adopted as production solver**: the same 7/8 captures meet 2.5 px |
| Lepetit, Moreno-Noguer & Fua, *EPnP*, IJCV 2009, doi:10.1007/s11263-008-0152-6 | Linear-complexity PnP initializer | **Evaluated, not adopted**: no pose gate improvement on 8 captures |
| Grompone von Gioi et al., *LSD: A Fast Line Segment Detector with a False Detection Control*, TPAMI 2010, doi:10.1109/TPAMI.2008.300 | Additional top-face straight-line evidence for cuboid | **REJECTED/UNDONE**: aggregate XY 7.858 vs 7.909 mm in V2; negligible 0.051 mm change, Trial01 regressed and runtime remained high. Source scratch code removed. No ground-truth-based hyperparameter search |
| Felzenszwalb & Huttenlocher, *Efficient Graph-Based Image Segmentation*, IJCV 2004, doi:10.1023/B:VISI.0000022288.19776.77 | Region proposals without manual ROIs | Not evaluated: current installed OpenCV wheel has no `cv2.segmentation.createGraphSegmentation`. Did not install dependencies or add GPL code |
| Rother, Kolmogorov & Blake, *GrabCut*, ACM TOG 2004, doi:10.1145/1015706.1015720 | Foreground segmentation, existing V2 approach | Prior single-pass/parallel trials changed fitted L/W/H and were rejected; do not reintroduce silently |
| MobileSAM (Zhang et al., arXiv:2306.14289), TinySAM (Shu et al., AAAI 2025) | Lightweight prompt-based segmentation candidates | NOT integrated: GPU/model benchmarks are not an 800 ms **CPU full-pair** guarantee; would require extra weights, prompt/ROI design and held-out validation |

**Measured fast fiducial pathway** in
`fast_pose_ablation.py`:
1. Detect the same four ArUco IDs at scaled grayscale resolution.
2. Map detected corners to **full-resolution pixel coordinates**;
   run `cv2.cornerSubPix` against the full-resolution grayscale.
3. Evaluate **ITERATIVE**, **EPnP+LM**, and **IPPE+LM** pose solvers,
   explicitly rejecting solutions with nonphysical camera center Z.
4. Compare against the unchanged original full-res pose on all
   eight same-session photographs.

Full-size iterative median detection+PnP time **154.55 ms/image**;
50%-size iterative median **49.16 ms/image** (~3.1x speedup).
50%-size IPPE+LM median **47.61 ms/image**; 35%-size iterative
**28.75 ms/image**, but may fail on smaller/blurrier markers in unseen
photos. For 50%-size ITERATIVE: **8/8 markers complete, 7/8 pose <=2.5
px**, and max camera-center difference **0.0249 mm** compared to the
full-resolution solution. 0.0249 mm is numerical pose-center drift,
**NOT** actual calibration error or a dimension-accuracy estimate.
The experiment is repeatable using
`python -m experiments.real_t01.fast_pose_ablation`; findings are
in `fast_pose_ablation.json`. Bench timings are same-PC,
non-isolated wall time (three samples/variant/frame) and cannot
establish production CPU latency.

**Why NOT integrate into the production detector now?** The gain is
well supported on the existing 8 pictures, but new photos might have
markers too small for coarse detection, and the 7/8 reprojection
gate still fails with in-sample intrinsics. Keep this alternative
opt-in for controlled future validation; no new model, dependency,
or global behavior changes.

### New source-data quality audit and decision

`t01_quality_audit.py` reads the existing real and V2 JSON reports,
flags gates individually, and refuses a GO verdict. Run:
`python -m experiments.real_t01.t01_quality_audit`.
Generated `t01_quality_audit.json` records:
- 8/8 full marker detections; 7/8 pose reprojection <=2.5 px
- V2 research XY MAE **7.9089 mm**, H MAE **6.1195 mm** (15 cases)
- Excluding just **Trial01 / black** (identity visually questionable),
  XY MAE **8.2698 mm** on 14 cases — **sensitivity analysis**, not an
  alternate corrected benchmark
- Manual ROIs, same-session camera intrinsics, unknown GT units, no
  held-out photos, high CPU wall time, and no production backend
  integration still **FAIL** the full T01 acceptance.

There are now pure synthetic pose/ArUco tests and failure-gate tests.
No threshold was changed to make this benchmark appear passing.

### Next steps only after acquiring new evidence

1. Verify physical identity of 'black' in Trial01 vs later trials,
   original L/W/H and their units, print dimensions of marker board.
2. Capture independent camera-calibration frames plus new held-out
   topdown/oblique pairs, with accurate GT per physical object.
3. On those captures, benchmark (a) original full-res ArUco against
   0.5x with full-res refinement, (b) marker missing/fallback cases,
   (c) throughput at controlled CPU thread/thermal settings.
4. Design an automatic ROI pipeline only when it passes per-object
   detection/correspondence recall and downstream mm-error tests.
5. After robust QA, profile GrabCut (currently dominating runtime);
   evaluate SAM variants only if weights/licensing, CPU inference and
   prompting protocol are all feasible. Keep issue T01 open meanwhile.


## Calibration and segmentation iteration — 2026-10-30 (experimental only)

The default V2 code and `camera_profile_estimated.json` remain **unchanged**.
We compared calibration models in a controlled ablation on the same
eight captures, using planar calibration from Zhengyou Zhang,
*A Flexible New Technique for Camera Calibration* (TPAMI, 2000):
https://www.microsoft.com/en-us/research/publication/a-flexible-new-technique-for-camera-calibration/

### Calibration model comparison

The original conservative intrinsics fit fixes the principal point,
sets tangential distortion coefficients `p1=p2=0`, and estimates radial
`k1,k2`. The experimental candidate frees only `p1,p2` (a standard
camera distortion model), retaining the original other constraints.
Six model parameterizations were compared; the pre-existing ArUco
corner SUBPIX refinement was used for all. We measured both
**in-sample reprojection** and **leave-one-image-out (LOO)**, which
fits camera intrinsics from 7 photos, then measures pose on the
eighth.

| Metric | Default constrained K | Candidate K (free p1,p2) |
|---|---:|---:|
| In-sample pose <=2.5 px | 7/8 | **8/8** |
| LOO pose <=2.5 px | 6/8 | **8/8** |
| LOO mean reprojection RMSE | 1.838 px | **1.686 px** |
| V2 2-view L/W MAE (same 15 labels) | 7.909 mm | **7.723 mm** |
| V2 2-view H MAE | 6.119 mm | **5.898 mm** |

**Strict qualifications:** the candidate was selected from SIX
parameterizations using these exact same eight photos, creating
model-selection bias even for LOO metrics. All photographs are from
one development capture set; this is **not independent device
calibration**. Ground-truth object identity and measurement units
still require verification. Trial03's H MAE WORSENS from 4.55 to
4.80 mm despite the overall improvement. Do NOT replace the default
camera profile, claim a new production performance metric, or close
the T01 gate based on this ablation.

Reproduce in the repo root:

```powershell
.\.venv\Scripts\python.exe -m experiments.real_t01.calibration_model_variants
.\.venv\Scripts\python.exe -m experiments.real_t01.calibration_metrology_experiment
.\.venv\Scripts\python.exe -m pytest -q tests
```

Output is written to `calibration_model_variants.json` and
`calibration_metrology_experiment.json`. The metrology evaluation
monkeypatches the camera pose function **in the experiment process
only**; production camera intrinsics and measurement code are not
changed. Regression tests prevent mislabelling the result.

### Segmentation ablation — rejected and undone

We measured original GrabCut and two single-iteration variants
using unchanged object ROIs, geometry and test protocol. GrabCut's
original graph-cut algorithm is described by Rother, Kolmogorov &
Blake (SIGGRAPH 2004):
https://www.microsoft.com/en-us/research/publication/grabcut-interactive-foreground-extraction-using-iterated-graph-cuts/

| Segmentation setting | 3-pair run | L/W MAE | H MAE |
|---|---:|---:|---:|
| Existing V2: 2 iterations for 700px bbox + 360px silhouette | 76.26 s | 7.909 mm | 6.119 mm |
| One iteration only for 360px silhouette | 69.59 s | **8.009 mm (regression)** | **6.128 mm (regression)** |
| One iteration only for 700px bbox | 65.23 s | 7.861 mm | **6.228 mm (regression)** |

Per-run wall time on an active Windows computer is **not** a
controlled latency benchmark. 60 original GrabCut calls consume
~57.8 of 76.3 seconds, confirming a bottleneck. However, both
shortcuts worsened one or more metrology metrics, so **both were
undone**, not integrated and not committed. No segmentation
shortcut is production-qualified by this experiment.

**Final verdict: still T01 NOT PASSED.** Camera intrinsics must be
validated on a physically measured marker board and a new independent
capture session; segmentation needs automatic ROIs and a faster method
that does not regress L/W/H. A 0.19mm improvement on an 8-photo
development set is too small to establish real-world generalization.
