# OptiPack — Member 1 Implementation Specification: Computer Vision & 3D Metrology (`02A_MEMBER1_COMPUTER_VISION.md`)

- **Role Owner:** Member 1 — Computer Vision & 3D Metrology Engineer
- **Primary Module Path:** `backend/app/cv/`
- **Upstream Dependencies:** Raw capture images (`top_image`, optional `oblique_image`), printed A4 4-ArUco Calibration Sheet, optional `sam-3.1` segmentation masks from Member 2 (`backend/app/ai/sam_client.py`)
- **Downstream Consumers:** Member 2 (`ai_meta_api` consumes 2D item crops + initial dimension priors), Member 3 (`or_solver` consumes integer `dimensions_mm` and `safety_margin_mm`), Member 4 (`frontend_ui` renders 2D bounding boxes, uncertainty badges, and calibration status)
- **Contract Reference:** `01_PROJECT_SPEC.md` (`Contract v1.0.0`)

---

## 1. Role Objective & Scope Boundaries

Member 1 owns the **Visual Perception, Object Identity, and 3D Dimensional Metrology** pipeline. Given one or two RGB photographs of an e-commerce order arranged on a tabletop next to a known calibration target, this module must:

1. Detect the **Calibration Reference Board** (an A4 sheet containing 4 corner ArUco markers) and estimate the camera's extrinsic pose $(R, \mathbf{t})$ relative to the table plane $Z = 0$.
2. Segment and isolate each physical item on the packing table, assigning a deterministic `item_id` (`item_01`, `item_02`, ...) and generating a tight 2D RGB crop for Member 2's multimodal AI analysis.
3. Estimate each item's canonical 3D bounding box $(L, W, H)$ in integer millimeters (`mm`) using geometrically sound multi-view or plane-referenced metrology.
4. Compute an explicit **measurement uncertainty** $(\sigma_L, \sigma_W, \sigma_H)$ in millimeters and a conservative `safety_margin_mm` buffer, flagging any item whose height or footprint requires human confirmation (`requires_user_review: true`).

### What Member 1 Must NOT Do (`[Verified]` Boundary)
- **Do NOT use planar homography (`cv2.getPerspectiveTransform` / `cv2.warpPerspective`) on oblique views to measure the footprint or height of 3D objects directly.** As proven in projective geometry (`[Verified]`), a planar homography maps points on the $Z=0$ plane only. For an item of height $H > 0$ viewed at elevation angle $\theta$, its top face projects onto $Z=0$ with a parallax relief displacement of $\Delta L = H \cot\theta$ (at $\theta = 45^\circ$ and $H = 100\text{ mm}$, $\Delta L = 100\text{ mm}$ error!).
- **Do NOT claim sub-millimeter precision** from uncalibrated smartphone cameras. Always output an explicit uncertainty margin (`safety_margin_mm`, default $5\text{ mm}$ to $10\text{ mm}$).
- **Do NOT spend hackathon hours building custom SLAM or NeRF pipelines.** Stick strictly to the controlled tabletop capture protocol defined below.

---

## 2. Capture Protocol & Calibration Target Specification

### 2.1 The Calibration Reference Board (`a4_aruco_4corner`) (`[Proposed]`)

Instead of relying on unstable white-paper edge detection (which fails on light-colored tables or under shadows), OptiPack uses a printable **A4 Calibration Sheet** ($297\text{ mm} \times 210\text{ mm}$) with **4 OpenCV ArUco markers** (`cv2.aruco.DICT_4X4_50`, IDs `0, 1, 2, 3`) printed at the four corners:

- **Marker Size:** Each square ArUco marker has side length $s = 40.0\text{ mm}$.
- **Board Coordinate System ($Z = 0$ on tabletop):**
  - Origin $(0, 0, 0)$ is the bottom-left corner of Marker 0.
  - Marker 0 (Bottom-Left, ID `0`): corners at $(0,0,0), (40,0,0), (40,40,0), (0,40,0)\text{ mm}$.
  - Marker 1 (Bottom-Right, ID `1`): outer X span up to $277.0\text{ mm}$.
  - Marker 2 (Top-Right, ID `2`): outer corner at $(277.0, 190.0, 0)\text{ mm}$.
  - Marker 3 (Top-Left, ID `3`): outer Y span up to $190.0\text{ mm}$.
- **Why 4 ArUco Markers (`[Verified]`):** 4 markers provide $4 \times 4 = 16$ known 3D-to-2D coplanar corner correspondences. Even if 1 marker is occluded by an item or hand, the remaining 3 markers (12 corners) still over-determine `cv2.solvePnP` with sub-pixel reprojection verification.

### 2.2 Defined Operator Capture Procedure (`[Proposed]`)

To maximize accuracy while keeping operator effort under 10 seconds:
1. **Table Setup:** Place the A4 ArUco sheet flat on the left side of a dark/contrasting packing table ($Z = 0$). Place the order's items on the table to the right of the sheet with at least $20\text{--}30\text{ mm}$ spacing between items (zero physical overlap).
2. **View 1 — Top-Down Zenith Photo (`top_image`, Required):** Hold the camera roughly perpendicular to the table ($\theta \approx 80^\circ\text{--}90^\circ$, height $\approx 600\text{--}800\text{ mm}$ above table) so the A4 sheet and all items are near the center of the frame. *(Minimizes radial relief displacement for $(L, W)$ footprint measurement).*
3. **View 2 — Oblique Elevation Photo (`oblique_image`, Recommended Primary / Optional):** Hold the camera at an oblique angle ($\theta \approx 35^\circ\text{--}50^\circ$ above the table, viewing from the front edge) with both the A4 ArUco sheet and the items visible. *(Provides vertical pixel disparity and top-vs-bottom corner visibility to solve for height $H$ via ray-plane intersection).*

---

## 3. Mathematical Formulation of 3D Metrology

### 3.1 Camera Intrinsics $K$ and Extrinsic Pose $(R, \mathbf{t})$ (`[Verified]`)

1. **Intrinsics Matrix $K$:**
   - **Calibrated Mode (Preferred):** Load pre-calibrated focal lengths $(f_x, f_y)$, principal point $(c_x, c_y)$, and distortion coefficients $\mathbf{d} = (k_1, k_2, p_1, p_2, k_3)$ from `calibration_profiles.json` for the demo smartphone/webcam.
   - **EXIF / FOV Fallback Mode (`[Fallback]`):** If an unknown camera is used, estimate focal length from image dimensions $(W_{\text{img}}, H_{\text{img}})$ assuming a standard $65^\circ$ horizontal field of view:
     $$f_x = f_y = \frac{W_{\text{img}}}{2 \tan(65^\circ / 2)} \approx 0.785 \cdot W_{\text{img}}, \quad c_x = \frac{W_{\text{img}}}{2}, \quad c_y = \frac{H_{\text{img}}}{2}$$
2. **Extrinsic Pose via `cv2.solvePnP`:**
   Given the detected 2D pixel corners $\{\mathbf{u}_k\}_{k=1}^{4M}$ of $M \ge 2$ ArUco markers and their known 3D world coordinates $\{\mathbf{P}_k = (X_k, Y_k, 0)^T\}$ on the table plane, solve for rotation vector $\mathbf{r}_{\text{vec}}$ and translation vector $\mathbf{t}$ using `cv2.solvePnP(..., flags=cv2.SOLVEPNP_IPPE)` (specifically designed for planar targets), convert $R = \text{Rodrigues}(\mathbf{r}_{\text{vec}})$, and compute RMS reprojection error $e_{\text{reproj}}$ in pixels.
   - Camera optical center in world coordinates:
     $$\mathbf{C}_w = -R^T \mathbf{t} = (C_X, C_Y, C_Z)^T$$
   - For any undistorted pixel $\mathbf{u} = (u, v)^T$, its unit viewing ray direction in world coordinates is:
     $$\mathbf{d}_w(\mathbf{u}) = \frac{R^T K^{-1} \begin{bmatrix} u & v & 1 \end{bmatrix}^T}{\left\| R^T K^{-1} \begin{bmatrix} u & v & 1 \end{bmatrix}^T \right\|_2}$$

### 3.2 Ray-Plane Intersection at Arbitrary Elevation $Z = z_0$ (`[Verified]`)

A viewing ray originating at $\mathbf{C}_w$ along direction $\mathbf{d}_w = (d_X, d_Y, d_Z)^T$ intersects a horizontal plane $Z = z_0$ at world point:

$$\mathbf{P}_w(u, v, z_0) = \mathbf{C}_w + \lambda(z_0)\,\mathbf{d}_w, \quad \text{where} \quad \lambda(z_0) = \frac{z_0 - C_Z}{d_Z}$$

### 3.3 Strategy A (Primary): Dual-View Pose-Calibrated Footprint & Height Estimation (`[Needs Validation]`)

1. **Base Footprint $(L, W)$ from Top-Down View (`top_image`):**
   - Segment each item mask $M_i^{\text{top}}$ in `top_image` and fit a minimum-area oriented bounding rectangle (`cv2.minAreaRect`) with 4 pixel corners $\{\mathbf{u}_{i,c}^{\text{top}}\}_{c=1}^4$.
   - Project those 4 corners onto $Z = 0$ using $\mathbf{P}_w(\mathbf{u}, 0)$ from the top-down camera pose $(R_{\text{top}}, \mathbf{t}_{\text{top}})$.
   - Compute initial footprint dimensions $L_0, W_0$ (with $L_0 \ge W_0$).
   - **Zenith Relief Correction:** Once height $H_i$ is estimated (Step 2 below), refine the footprint by intersecting the top-face corners in `top_image` with the elevated plane $Z = H_i$ instead of $Z = 0$:
     $$L_i = L_0 \cdot \left(1 - \frac{H_i}{C_{Z,\text{top}}}\right), \quad W_i = W_0 \cdot \left(1 - \frac{H_i}{C_{Z,\text{top}}}\right)$$
     *(This explicitly eliminates perspective relief inflation when the top face of a box is closer to the overhead camera than the table surface!)*
2. **Height $H_i$ from Oblique View (`oblique_image`):**
   - Match item $i$ between `top_image` and `oblique_image` using the projected 3D footprint centroid $(X_{c,i}, Y_{c,i}, 0)$ mapped into `oblique_image` via `cv2.projectPoints`.
   - In `oblique_image`, locate the lowest visible front base contour pixel $\mathbf{u}_{\text{bot}}$ (lying on $Z = 0$ at world coordinate $(X_{\text{front}}, Y_{\text{front}}, 0)$) and the highest visible top-front edge pixel $\mathbf{u}_{\text{top}} = (u_{\text{top}}, v_{\text{top}})^T$ along the vertical edge at $(X_{\text{front}}, Y_{\text{front}})$.
   - Intersect the oblique ray $\mathbf{C}_{w,\text{obq}} + \lambda\,\mathbf{d}_{w,\text{obq}}(\mathbf{u}_{\text{top}})$ with the vertical line passing through $(X_{\text{front}}, Y_{\text{front}}, Z)$ via least-squares closest approach between two 3D lines, yielding $Z = H_i$.

### 3.4 Strategy B (Fallback 1): Single Top-Down View + Oblique Shadow / Monocular Depth Ratio (`[Fallback]`)

If `oblique_image` is omitted or ArUco pose fails on the oblique view:
- Compute $(L_i, W_i)$ from `top_image` at $Z = 0$.
- Estimate $H_i$ using either:
  1. **Catalog / Category Aspect-Ratio Prior:** Match item packaging class and footprint $(L_i, W_i)$ against known packaging aspect priors (e.g., standard shoebox $H \approx 0.38 L$, smartphone retail box $H \approx 0.30 L$), OR
  2. **Manual Height Slider Flag:** Set $H_i = \text{round}(0.40 \cdot W_i)$, set `height_sigma_mm = 25.0`, and set `requires_user_review = true` so Member 4's UI prompts the operator to confirm or drag the height slider.

---

## 4. Segmentation & Cross-View Identity Matching

### 4.1 Two-Tier 2D Segmentation Pipeline (`[Proposed]`)

1. **Tier 1 — Fast Local Tabletop Segmentation (`< 80 ms`, Default):**
   - Mask out the known A4 Calibration Sheet polygon (projected from the detected ArUco board bounds plus a $10\text{ mm}$ margin).
   - Convert the workspace ROI to LAB color space, estimate background table color/intensity from border strips, compute foreground distance map, apply Otsu + Canny edge fusion, morphological closing (`cv2.MORPH_CLOSE`, $7\times 7$ kernel), and extract external connected contours (`cv2.findContours`) with area $\ge 1500\text{ mm}^2$ ($\approx 40\text{ mm} \times 40\text{ mm}$).
2. **Tier 2 — Meta `sam-3.1` Cloud Segmentation Adapter (Optional Enhancement via Member 2):**
   - If local background contrast is poor (`enable_cloud_sam == true`), pass `top_image` to Member 2's `sam-3.1` client with single-concept prompt `"box"` or `"package"`, decode the returned 1-bit RLE masks, filter out the A4 calibration sheet mask by IoU overlap, and pass the masks into the same `minAreaRect` 3D metrology pipeline.

### 4.2 Deterministic Item Identity Ordering (`[Proposed]`)

To ensure deterministic `item_id` assignment across re-runs and easy visual correlation for the operator:
- Sort all detected items primarily by their world $Y$ coordinate (back-to-front, descending) quantized into $100\text{ mm}$ rows, and secondarily by world $X$ coordinate (left-to-right, ascending).
- Assign sequential IDs: `"item_01"`, `"item_02"`, ..., `"item_N"`, and assign distinct high-contrast hex colors from a fixed 10-color palette (`#3B82F6`, `#10B981`, `#F59E0B`, `#EF4444`, `#8B5CF6`, `#EC4899`, `#06B6D4`, `#84CC16`, `#F97316`, `#6366F1`).

---

## 5. Uncertainty Model & Safety Margin Calculation

Every item measurement must populate `uncertainty_mm`:

$$\sigma_{L} = \sqrt{\sigma_{\text{calib}}^2 + \left(2\text{ px} \cdot s_{\text{mm/px}}\right)^2 + \left(\frac{\sigma_H \cdot L}{C_{Z,\text{top}}}\right)^2}$$

$$\sigma_H = \begin{cases} 4.5\text{ mm} & \text{if dual-view PnP triangulation succeeds with } e_{\text{reproj}} < 1.5\text{ px} \\ 9.0\text{ mm} & \text{if dual-view PnP succeeds with } 1.5 \le e_{\text{reproj}} \le 3.0\text{ px} \\ 25.0\text{ mm} & \text{if single-view prior fallback is used} \end{cases}$$

- **Safety Margin (`safety_margin_mm`):**
  $$\text{safety\_margin\_mm} = \text{clamp}\Big(\lceil 1.25 \cdot \max(\sigma_L, \sigma_W, \sigma_H) \rceil,\; 3,\; 15\Big)$$
- **User Review Trigger (`requires_user_review`):**
  Set `requires_user_review = true` whenever $\max(\sigma_L, \sigma_W, \sigma_H) > 8.0\text{ mm}$, `reprojection_error_px > 2.5`, or fewer than 3 ArUco markers are detected.

---

## 6. Reference Implementation Pseudocode (`backend/app/cv/metrology.py`)

```python
from dataclasses import dataclass
from typing import List, Optional, Tuple
import cv2
import numpy as np

@dataclass
class CalibrationResult:
    status: str  # "calibrated" | "degraded" | "failed"
    detected_markers_count: int
    reprojection_error_px: float
    scale_mm_per_px_at_z0: float
    rvec: Optional[np.ndarray]
    tvec: Optional[np.ndarray]
    R: Optional[np.ndarray]
    camera_center_world_mm: Optional[np.ndarray]
    K: np.ndarray
    dist_coeffs: np.ndarray
    warnings: List[str]

# Canonical 3D coordinates (mm) of the 4 corner ArUco markers on an A4 sheet (Z=0)
# Each marker is 40x40 mm: corners ordered Clockwise starting Top-Left in board frame
ARUCO_BOARD_3D_MM = {
    0: np.array([[0.0, 40.0, 0.0], [40.0, 40.0, 0.0], [40.0, 0.0, 0.0], [0.0, 0.0, 0.0]], dtype=np.float32),
    1: np.array([[237.0, 40.0, 0.0], [277.0, 40.0, 0.0], [277.0, 0.0, 0.0], [237.0, 0.0, 0.0]], dtype=np.float32),
    2: np.array([[237.0, 190.0, 0.0], [277.0, 190.0, 0.0], [277.0, 150.0, 0.0], [237.0, 150.0, 0.0]], dtype=np.float32),
    3: np.array([[0.0, 190.0, 0.0], [40.0, 190.0, 0.0], [40.0, 150.0, 0.0], [0.0, 150.0, 0.0]], dtype=np.float32),
}

def estimate_camera_pose_from_aruco(
    image_bgr: np.ndarray,
    K: Optional[np.ndarray] = None,
    dist_coeffs: Optional[np.ndarray] = None,
) -> CalibrationResult:
    h, w = image_bgr.shape[:2]
    if K is None:
        fx = fy = 0.785 * float(w)
        K = np.array([[fx, 0.0, w / 2.0], [0.0, fy, h / 2.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    if dist_coeffs is None:
        dist_coeffs = np.zeros((5, 1), dtype=np.float64)

    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
    corners_list, ids, _ = detector.detectMarkers(image_bgr)

    warnings: List[str] = []
    if ids is None or len(ids) == 0:
        return CalibrationResult(
            status="failed", detected_markers_count=0, reprojection_error_px=999.0,
            scale_mm_per_px_at_z0=0.5, rvec=None, tvec=None, R=None,
            camera_center_world_mm=None, K=K, dist_coeffs=dist_coeffs,
            warnings=["No ArUco calibration markers detected. Falling back to manual scale."]
        )

    obj_pts, img_pts = [], []
    for marker_corners, marker_id_arr in zip(corners_list, ids):
        m_id = int(marker_id_arr[0])
        if m_id in ARUCO_BOARD_3D_MM:
            obj_pts.append(ARUCO_BOARD_3D_MM[m_id])
            img_pts.append(marker_corners.reshape(4, 2).astype(np.float32))

    if len(obj_pts) < 2:
        return CalibrationResult(
            status="failed", detected_markers_count=len(obj_pts), reprojection_error_px=999.0,
            scale_mm_per_px_at_z0=0.5, rvec=None, tvec=None, R=None,
            camera_center_world_mm=None, K=K, dist_coeffs=dist_coeffs,
            warnings=["Fewer than 2 valid ArUco markers detected."]
        )

    obj_pts_np = np.vstack(obj_pts)
    img_pts_np = np.vstack(img_pts)

    success, rvec, tvec = cv2.solvePnP(
        obj_pts_np, img_pts_np, K, dist_coeffs, flags=cv2.SOLVEPNP_IPPE
    )
    if not success:
        return CalibrationResult(
            status="failed", detected_markers_count=len(obj_pts), reprojection_error_px=999.0,
            scale_mm_per_px_at_z0=0.5, rvec=None, tvec=None, R=None,
            camera_center_world_mm=None, K=K, dist_coeffs=dist_coeffs,
            warnings=["cv2.solvePnP failed to converge."]
        )

    proj_pts, _ = cv2.projectPoints(obj_pts_np, rvec, tvec, K, dist_coeffs)
    reproj_err = float(np.sqrt(np.mean(np.sum((proj_pts.reshape(-1, 2) - img_pts_np) ** 2, axis=1))))

    R, _ = cv2.Rodrigues(rvec)
    cam_center_w = (-R.T @ tvec).reshape(3)
    scale_mm_per_px = float(abs(cam_center_w[2]) / K[0, 0])

    status = "calibrated" if (len(obj_pts) >= 3 and reproj_err <= 2.5) else "degraded"
    if status == "degraded":
        warnings.append(f"Calibration degraded: {len(obj_pts)} markers, reproj error {reproj_err:.2f}px.")

    return CalibrationResult(
        status=status, detected_markers_count=len(obj_pts), reprojection_error_px=round(reproj_err, 3),
        scale_mm_per_px_at_z0=round(scale_mm_per_px, 4), rvec=rvec, tvec=tvec, R=R,
        camera_center_world_mm=cam_center_w, K=K, dist_coeffs=dist_coeffs, warnings=warnings
    )

def intersect_pixel_with_z_plane(
    u: float, v: float, z_plane_mm: float, calib: CalibrationResult
) -> np.ndarray:
    """Intersects viewing ray through pixel (u, v) with horizontal plane Z = z_plane_mm."""
    uv_hom = np.array([[u], [v], [1.0]], dtype=np.float64)
    ray_cam = np.linalg.inv(calib.K) @ uv_hom
    ray_world = (calib.R.T @ ray_cam).reshape(3)
    ray_world = ray_world / np.linalg.norm(ray_world)

    c_w = calib.camera_center_world_mm
    lam = (z_plane_mm - c_w[2]) / ray_world[2]
    return c_w + lam * ray_world
```

---

## 7. Phase 0 Proof-of-Feasibility Experiment (`Member 1 Gate`)

Before writing full API glue code, Member 1 must execute the following standalone experiment in `experiments/phase0_cv_metrology.py`:

| Experiment Field | Concrete Specification |
| :--- | :--- |
| **1. Hypothesis** | Using a printed A4 4-ArUco Calibration Sheet + `cv2.solvePnP` on a top-down + oblique smartphone photo pair can estimate the 3D bounding dimensions $(L, W, H)$ of 5 rigid rectangular boxes within $\le 8\text{ mm}$ MAE on $(L, W)$ and $\le 12\text{ mm}$ MAE on $H$. |
| **2. Question Being Tested** | Does dual-view ArUco pose calibration + ray-plane intersection overcome the parallax distortion of single-view planar homography under realistic indoor tabletop lighting? |
| **3. Setup** | 1 printed A4 sheet with 4 corner ArUco markers (`DICT_4X4_50`, IDs 0–3, $40\text{ mm}$ squares); 5 physical test boxes measured with a physical ruler/caliper as ground truth (e.g., phone box, tea box, headphones box, cosmetics box, book); 1 smartphone camera. |
| **4. Procedure** | Capture 3 photo pairs (`top_image` at $\sim 85^\circ$, `oblique_image` at $\sim 40^\circ$) of the 5 items on a table. Run `estimate_camera_pose_from_aruco()`, segment item contours, compute $(L, W, H)$ with and without zenith relief correction, and compare against ruler ground truth. |
| **5. Expected Output** | A CSV/Markdown table comparing Ground Truth $(L, W, H)$ vs. Estimated $(L, W, H)$, absolute error $(\text{mm})$, relative error $(\%)$, and reprojection error $(\text{px})$ for all 5 items across 3 trials. |
| **6. Evaluation Metric** | Mean Absolute Error (MAE) and Max Absolute Error in millimeters (`mm`) for Footprint $(L, W)$ and Height $(H)$, plus end-to-end execution latency in milliseconds (`ms`). |
| **7. Pass Criteria** |1) ArUco pose succeeds on $\ge 90\%$ of frames with $e_{\text{reproj}} \le 2.5\text{ px}$; 2) Footprint $(L, W)$ MAE $\le 8.0\text{ mm}$; 3) Height $H$ MAE $\le 12.0\text{ mm}$; 4) Processing time $\le 800\text{ ms}$ per pair on CPU. |
| **8. Fail Criteria** |1) Footprint MAE $> 12.0\text{ mm}$, OR 2) Oblique height triangulation fails or produces MAE $> 20.0\text{ mm}$ due to indistinct front vertical edges, OR 3) Contour segmentation merges adjacent items in $> 20\%$ of trials. |
| **9. Fallback** | **Fallback 1A (Height Failure):** Lock CV pipeline to **Single Top-Down View** for $(L, W)$ footprint (where relief error is minimal near optical center) and use **Category Aspect Prior + Mandatory UI Height Slider Confirmation** (`requires_user_review = true`) for $H$.<br/>**Fallback 1B (Segmentation Failure):** Route `top_image` through Member 2's Meta `sam-3.1` endpoint (`input_text: "box"`) or require high-contrast dark tablecloth during demo capture. |
| **10. Decision Owner** | **Member 1** (in consultation with Member 4 if UI height slider becomes the primary height workflow). |
| **11. Team Escalation Condition** | Escalate immediately to all 4 members if top-down $(L, W)$ footprint error exceeds $15\text{ mm}$ OR if single-view vs. dual-view capture changes the upload UI payload required from Member 4. |
| **12. Time / Effort Boundary** | **Maximum 4 hours** during Phase 0. If dual-view height triangulation is not passing within 4 hours, freeze Fallback 1A immediately so integration is not blocked. |

---

## 8. Mandatory Failure-Handling & Escalation Procedure (7 Steps)

If Member 1's Phase 0 experiment hits any **Fail Criterion**:

1. **Step 1 — Record Evidence:** Save the failing test images, detected ArUco corner logs, reprojection error values, and ground-truth comparison table in `experiments/logs/phase0_cv_failure_report.md`.
2. **Step 2 — Classify Root Cause:** Identify whether the failure is:
   - *Calibration / Pose Error* (lens distortion, blurry ArUco markers, coplanar ambiguity in `solvePnP`),
   - *Segmentation Error* (table reflection, shadows merging boxes, white box blending with white table), or
   - *Height Triangulation Error* (difficulty matching the exact top-front vs. bottom-front corner of textureless boxes in the oblique view).
3. **Step 3 — Check Scope vs. Cross-Module Impact:**
   - Switching height estimation from dual-view triangulation to top-down + manual/prior fallback is **local to Member 1 & Member 4's UI highlight flag** (`requires_user_review: true`) — the JSON contract (`OrderAnalysisResponse`) does **not** change!
4. **Step 4 — Evaluate Pre-Defined Fallbacks:** Test Fallback 1A (Top-Down $(L, W)$ + Zenith Center Placement + UI Height Review) on the same 5 images within 30 minutes.
5. **Step 5 — Propose Concrete Action:** Present a 5-minute update to the team recommending either a targeted threshold fix (e.g., dark mat on table + zenith camera mount) or immediate adoption of Fallback 1A.
6. **Step 6 — Update Shared Documentation:** Update the status of dual-view height triangulation in `01_PROJECT_SPEC.md` Section 8 and `03_EXECUTION_PLAN.md` from `[Needs Validation]` to either `[Verified]` or `[Fallback Activated]`.
7. **Step 7 — Freeze Contract & Proceed:** Keep `OrderAnalysisResponse` schema 100% unchanged so Members 2, 3, and 4 continue development without interruption.

---

## 9. Unit & Integration Test Cases (`tests/test_cv_metrology.py`)

1. **`test_synthetic_aruco_pose_recovery`:** Render a synthetic $1920\times 1080$ image of the 4 corner ArUco markers using known $K$, $R$, $\mathbf{t}$ ($Z_c = 700\text{ mm}$). Assert `estimate_camera_pose_from_aruco()` recovers $C_Z$ within $\pm 2.0\text{ mm}$ and `reprojection_error_px < 0.5`.
2. **`test_zenith_relief_correction_math`:** Given an item of true dimensions $200\times 150\times 100\text{ mm}$ imaged from $C_Z = 700\text{ mm}$, its top face projects onto $Z=0$ with apparent size $200 \times \frac{700}{600} = 233.3\text{ mm}$. Assert that applying the zenith relief factor $(1 - H/C_Z)$ recovers exactly $200\text{ mm}$.
3. **`test_missing_aruco_graceful_degradation`:** Pass a blank white image with zero markers. Assert `status == "failed"`, `warnings` is non-empty, and the function returns cleanly in $< 50\text{ ms}$ without raising an unhandled exception.
4. **`test_deterministic_item_ordering_and_contract`:** Given 3 detected contours at known table positions, assert `item_id` values are deterministically assigned `"item_01"`, `"item_02"`, `"item_03"` and all output dimensions are positive Python `int` values in `mm`.
