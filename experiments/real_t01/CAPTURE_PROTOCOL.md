# T01 Capture & Validation Protocol — next dataset

**Purpose:** obtain evidence that is independent of the eight OptiPack
development photos. Do not treat higher MAE on a new session as a
software regression until measurements, labels and camera assumptions
are checked.

## Minimum collection pilot

- **12 new two-view scenes** (24 photographs) with five actual
  measured objects whenever physically possible; ~120 visible masks.
  This is a **pilot for algorithm selection and error analysis**, not
  enough by itself to guarantee segmentation-model generalization.
- Capture scenes on different days/lighting/backgrounds rather than
  taking adjacent video frames and pretending they are independent.
- Keep **the same physical objects in the same arrangement** for
  top-down/oblique within one pair. Do not swap a speaker for a black
  box across scenes under one shared ground-truth ID.
- Include a few **unseen physical objects** for final evaluation.
  Record each distinct object's dimensions, don't reuse dimensions
  from objects that merely look similar.

## Physical ground truth and ArUco board

1. **Measure L/W/H in millimeters**, using a ruler or caliper; repeat
   and record uncertainty (for curved/irregular shapes, define a
   measured external bounding cuboid). Measure along the *actual
   resting orientation* in the image. Do not assume cm.
2. Measure the printed ArUco board marker side and offsets in **mm**
   after printing, rather than assuming the PDF printed at 100%.
   Board and objects must rest on the **same geometric plane**.
3. Use a separate camera-calibration capture set with a known-size
   ChArUco/checkerboard, multiple distances and board angles, to
   estimate K and distortion independently. Reprojection RMSE in
   pixels alone cannot verify the physical millimeter scale.
4. Keep phone model, lens, zoom, capture resolution and camera mode
   fixed inside an evaluated calibration session. If settings
   change, record and validate a new profile.
5. Keep marker IDs 0–3 wholly visible, unoccluded and sharp in
   both images. Prefer adequate diffuse light, low motion blur and
   avoid direct mirror-like glare from tile floors.

## Image pairs and annotation

For each scene:
- Capture one **top-down** and one **oblique** photograph
  (approx. 25–45 degrees from the tabletop, with all objects visible).
- Keep the board visible and objects within the shared region of view;
  do not touch or reposition objects between the two captures.
- Annotate each visible object as an **instance polygon/mask**, not
  only a rectangle; use a stable `physical_object_id` across views.
  Keep box ROIs separately as the legacy benchmark requires them.
- Record the crop-independent image dimensions, orientation and
  photo/session ID. Use sanitized copies for any public repository:
  discard GPS/EXIF location while retaining orientation semantics.

Suggested CSV fields:
`capture_session,scene_id,view,image_filename,physical_object_id,
length_mm,width_mm,height_mm,gt_uncertainty_mm,board_marker_side_mm,
camera_id,zoom`.

## Evaluation and leakage control

- **Pilot:** collect 12 pairs, inspect all masks and measurements.
  Partition at the **scene/session level**; never scatter neighboring
  frames from the same scene across train/validation/test.
- **Model experiment:** measure paired instance detection recall,
  box IoU >=0.50, pixel mask IoU, false proposals per image,
  topdown/oblique correspondence accuracy and CPU latency.
- **Metrology:** recompute L/W/H using the predicted masks and the
  SAME K and cuboid optimizer; compare against manual-ROI V2 and
  report per-object and worst-case errors in addition to overall MAE.
- **Acceptance:** keep a genuinely unseen session untouched until
  the algorithm and thresholds have been frozen. Report both
  success/failure rates and full end-to-end CPU p50/p95 including
  calibration/pose and segmentation.
- **No false GO:** the T01 targets still include 90% pose under
  2.5 px, L/W MAE <=8 mm, H MAE <=12 mm, and <=800 ms CPU
  per pair. Manual ROI or using the same-session calibration data
  cannot be silently certified as an autonomous production pass.

Existing blockers: Trial01 `black` appears to be a distinct
two-driver product from the plain black cuboid in Trials02/03;
the dimensions in the original annotations were interpreted as
centimeters but have not been independently confirmed.
