# OptiPack — Member 4 Implementation Specification: Frontend & 3D Visualization (`02D_MEMBER4_FRONTEND_3D_VISUALIZATION.md`)

- **Role Owner:** Member 4 — Frontend & 3D Visualization Engineer
- **Primary Module Path:** `frontend/` (React 18 + TypeScript + Vite + Tailwind CSS + Three.js / `@react-three/fiber` + `@react-three/drei`)
- **Upstream Dependencies:** `OrderAnalysisResponse` from `POST /api/v1/orders/analyze`, `PackingSolutionResponse` from `POST /api/v1/orders/pack`, and golden mock JSON fixtures (`frontend/src/mocks/`)
- **Downstream Consumers:** End User (Packing Operator) & Hackathon Judges; emits user-edited `PackingRequest` JSON back to `POST /api/v1/orders/pack`
- **Contract Reference:** `01_PROJECT_SPEC.md` (`Contract v1.0.0`)

---

## 1. Role Objective & Scope Boundaries

Member 4 owns the **User Experience, Human-in-the-Loop Uncertainty & Override Workflow, Interactive 3D Packing Visualization, and Cost/Validation Dashboard**. Specifically, Member 4 must build:

1. **The Capture & Demo Preset Loader Panel:** Allows uploading a top-down + oblique photo pair (or selecting 1 of 3 pre-loaded benchmark orders for instant zero-camera testing and resilient live pitching) and displays the 2D detection bounding-box overlay and ArUco calibration badge.
2. **The Editable Item Manifest & Uncertainty Inspector:** Displays every detected item's dimensions $(L, W, H\text{ in mm})$, uncertainty $(\pm\sigma\text{ mm})$, weight (`g`), fragility class, and `keep_upright` toggle. Items with `requires_user_review == true` or `"unknown"` weight/fragility are visually highlighted in amber so the operator can edit or confirm them and click **"Optimize Carton & Pack"**.
3. **The Interactive 3D Carton & Step-by-Step Packing Viewer (`Three.js` / `@react-three/fiber`):** Renders the selected carton as a translucent wireframe/glass container with labeled axes, renders each packed item up to the active step $k \in [1, N]$, and implements the **exact deterministic coordinate transformation** from the backend's canonical $Z$-up corner-anchored coordinate system to Three.js's $Y$-up center-anchored coordinate system.
4. **The Cost, DIM Weight & Validation Scorecard:** Displays the selected carton (`BOX-M`), Total Estimated Cost (`$6.87 USD`), Actual vs. DIM vs. Billable Weight, Volume Utilization (`%`), Candidate Carton Comparison Table, and the 6 green checkmarks from Member 3's deterministic `ValidationReport` (plus multi-carton overflow tabs or infeasibility diagnostics when an order cannot fit in a single box).

---

## 2. Screen Layout & Component Architecture

### 2.1 Single-Page Split-Workspace Layout (`1440x900` Desktop Target)

```
+---------------------------------------------------------------------------------------------------+
| [OptiPack Logo]  E-Commerce Multi-Item Cartonization MVP     [Calibration: Calibrated (0.84px)]   |
|                  [Load Demo Order 1] [Load Demo Order 2] [Upload Custom Photos]                   |
+------------------------------------------------+--------------------------------------------------+
| LEFT PANE (42% Width): Perception & Manifest   | RIGHT PANE (58% Width): 3D Packing & Scorecard   |
|                                                |                                                  |
| 1. 2D Capture & Calibration Preview            | 3. Interactive 3D Viewport (Three.js Canvas)     |
|    - Top-Down Image with colored 2D boxes      |    - Translucent Carton + Floor Grid (mm)        |
|    - ArUco 4-marker status & scale (mm/px)     |    - Color-coded 3D boxes + edge outlines        |
|    - AI Telemetry badge (muse-spark-1.3: 1.4s) |    - Upright arrows (^) & Fragile badges         |
|                                                |    - Camera presets: [Iso] [Top] [Front] [Side]  |
| 2. Editable Item Manifest Table                |    - Toggle: [Show Nominal vs. +Margin Bounds]   |
|    - Row per item (Color swatch, Name, Qty)    |                                                  |
|    - Editable L x W x H (mm) + Uncertainty     | 4. Step-by-Step Packing Scrubber                 |
|    - Editable Weight (g) [Warning if Unknown]  |    [|<] [< Prev]  Step 2 of 4  [Next >] [Play]   |
|    - Fragility dropdown: Low | Med | High      |    "Step 2: Place Wireless Headphones at         |
|    - Checkbox: [x] Keep Upright  [x] Stackable |     (0, 0, 0) in LWH orientation"                |
|    - [+ Add Manual Item]                       |                                                  |
|                                                | 5. Cost, DIM Weight & Validator Scorecard        |
|    [x] Include Uncertainty Margin (+5mm)       |    - Selected: BOX-M (300x220x150mm) | $6.87 USD |
|    [   Re-Optimize 3D Packing (POST /pack)   ] |    - Actual: 1.42kg | DIM: 1.98kg | Bill: 2.0kg  |
|                                                |    - Validator: [PASS] 6/6 Checks Verified       |
|                                                |    - Collapsible Candidate Carton Comparison     |
+------------------------------------------------+--------------------------------------------------+
```

---

## 3. Canonical $Z$-Up (Corner) to Three.js $Y$-Up (Center) Coordinate Adapter

> **CRITICAL GEOMETRY RULE (`[Verified]`):**
> 1. **Axis Convention Difference:** The OptiPack backend (`01_PROJECT_SPEC.md` Section 4.2) uses a right-handed **$Z$-Up** coordinate system where $(X, Y)$ is the horizontal floor ($X$ = Length right, $Y$ = Width depth) and $Z$ is vertical Height up. **Three.js** uses a right-handed **$Y$-Up** coordinate system where $(X_{\text{three}}, Z_{\text{three}})$ is the horizontal floor and $Y_{\text{three}}$ is vertical Height up.
> 2. **Anchor Point Difference:** The backend reports `position_mm: {x, y, z}` as the **Minimum Corner** $(x_{\min}, y_{\min}, z_{\min})$ of the box. Three.js `<boxGeometry args={[width, height, depth]} />` positions meshes by their **Geometric Center** $(x_c, y_c, z_c)$.
>
> **Failure to apply both the axis swap and the half-dimension center offset is the #1 cause of overlapping or floating boxes in 3D bin-packing UIs!**

### 3.1 Exact Mathematical Transformation Formulas (`[Verified]`)

Given backend placement `position_mm = {x, y, z}` and `placed_dimensions_mm = {dx, dy, dz}` inside a carton of internal dimensions `(Lc, Wc, Hc)` (with visual scaling factor $s = 0.01$, i.e., $100\text{ mm} = 1.0\text{ Three.js world unit}$, and centering the carton floor around the Three.js origin $(0, 0, 0)$):

1. **Three.js Box Geometry Dimensions `(width_X, height_Y, depth_Z)`:**
   $$W_{\text{three}} = s \cdot dx, \qquad H_{\text{three}} = s \cdot dz, \qquad D_{\text{three}} = s \cdot dy$$
2. **Three.js Mesh Center Position `(pos_X, pos_Y, pos_Z)` relative to Carton Minimum Corner at $(-s L_c / 2,\; 0,\; -s W_c / 2)$:**
   $$X_{\text{three}} = s \cdot \left(x + \frac{dx}{2} - \frac{L_c}{2}\right)$$
   $$Y_{\text{three}} = s \cdot \left(z + \frac{dz}{2}\right)$$
   $$Z_{\text{three}} = s \cdot \left(y + \frac{dy}{2} - \frac{W_c}{2}\right)$$
3. **Carton Wireframe Mesh Center & Size:**
   - Size: `(s * Lc, s * Hc, s * Wc)`
   - Center Position: `(0, s * Hc / 2, 0)` (so the carton floor sits exactly on the Three.js ground plane $Y_{\text{three}} = 0$).

### 3.2 Reference TypeScript Implementation (`frontend/src/utils/coordinateTransform.ts`)

```typescript
export interface Vec3MM {
  x: number;
  y: number;
  z: number;
}

export interface PlacedDimsMM {
  dx: number;
  dy: number;
  dz: number;
}

export interface CartonDimsMM {
  length_mm: number;
  width_mm: number;
  height_mm: number;
}

export interface ThreeBoxTransform {
  /** Three.js mesh position [X_three, Y_three, Z_three] (center of box) */
  position: [number, number, number];
  /** Three.js boxGeometry args [width_X, height_Y, depth_Z] */
  geometryArgs: [number, number, number];
}

export const MM_TO_THREE_SCALE = 0.01; // 100 mm = 1.0 Three.js unit

/**
 * Deterministically maps canonical OptiPack Z-up minimum-corner coordinates (mm)
 * into Three.js Y-up center-anchored coordinates, with the carton floor centered at (0, 0, 0).
 */
export function mapPlacementToThreeJS(
  position_mm: Vec3MM,
  placed_dimensions_mm: PlacedDimsMM,
  carton_mm: CartonDimsMM,
  scale: number = MM_TO_THREE_SCALE
): ThreeBoxTransform {
  const { x, y, z } = position_mm;
  const { dx, dy, dz } = placed_dimensions_mm;
  const { length_mm: Lc, width_mm: Wc } = carton_mm;

  const widthX = dx * scale;
  const heightY = dz * scale; // Canonical Z (height) -> Three.js Y (up)
  const depthZ = dy * scale;  // Canonical Y (depth)  -> Three.js Z (depth)

  const centerX = (x + dx / 2.0 - Lc / 2.0) * scale;
  const centerY = (z + dz / 2.0) * scale;
  const centerZ = (y + dy / 2.0 - Wc / 2.0) * scale;

  return {
    position: [
      Number(centerX.toFixed(5)),
      Number(centerY.toFixed(5)),
      Number(centerZ.toFixed(5)),
    ],
    geometryArgs: [
      Number(widthX.toFixed(5)),
      Number(heightY.toFixed(5)),
      Number(depthZ.toFixed(5)),
    ],
  };
}

export function mapCartonToThreeJS(
  carton_mm: CartonDimsMM,
  scale: number = MM_TO_THREE_SCALE
): ThreeBoxTransform {
  const widthX = carton_mm.length_mm * scale;
  const heightY = carton_mm.height_mm * scale;
  const depthZ = carton_mm.width_mm * scale;

  return {
    position: [0, Number((heightY / 2.0).toFixed(5)), 0],
    geometryArgs: [
      Number(widthX.toFixed(5)),
      Number(heightY.toFixed(5)),
      Number(depthZ.toFixed(5)),
    ],
  };
}
```

---

## 4. Handling Uncertainty, Overrides & Error States in the UI

### 4.1 Uncertainty & Provenance Badges
Every row in the **Editable Item Manifest Table** must display:
- **Dimension Confidence Badge:**
  - Green (`Confidence >= 0.85`, $\sigma \le 5\text{ mm}$): `"Calibrated Dual-View (±4mm)"`
  - Amber (`requires_user_review == true` or $\sigma > 8\text{ mm}$): `"Review Height (±25mm — Prior Fallback)"` with an inline yellow highlight around the `H (mm)` input box.
- **Weight Provenance Badge:**
  - If `weight_g == null` or `weight_source == "unknown"`: Show an amber badge `"Weight Unknown (Est. 450g)"` next to an editable numeric input (`g`) so the operator can type the real weight or accept the density estimate.
- **Handling Constraint Controls:**
  - `keep_upright` toggle switch (`[Up Arrow]` icon): When toggled ON, the UI automatically updates `allowed_rotations` for that item to `["LWH", "WLH"]`.
  - `fragility_class` selector (`Low` / `Medium` / `High`): Selecting `High` automatically unchecks `stackable` and sets `max_top_load_g = 0`.

### 4.2 Visualizing nominal vs. safety-margin bounds in 3D
When `apply_uncertainty_margin == true`, each item's `placed_dimensions_mm` includes `safety_margin_mm` (e.g., $+5\text{ mm}$). The 3D viewer renders:
- The **solid colored inner box** using `nominal_dimensions_mm` centered inside the allocated slot, and
- A **subtle translucent wireframe halo** using `placed_dimensions_mm` (toggleable via `[Show Safety Buffer Halo]`) so judges can visually see how OptiPack protects against CV measurement uncertainty!

### 4.3 Multi-Carton Overflow & Infeasibility UI States
1. **Multi-Carton Split (`overflow_plans.length > 0`):** Display a top tab bar above the 3D viewport: `[Box 1: BOX-XL (6 items)]` and `[Box 2: BOX-M (2 overflow items)]`, plus a combined total cost banner.
2. **Unpackable Single Item (`unpacked_item_ids.length > 0`):** Highlight the unpacked item row in red in the manifest table and show `infeasibility_diagnostics` (e.g., *"Item 'item_04' (650x420x300 mm) exceeds largest catalog carton BOX-XXL (600x400x350 mm)"*).

---

## 5. Phase 0 Proof-of-Feasibility Experiment (`Member 4 Gate`)

Member 4 must execute the following standalone prototype verification before backend endpoints are live:

| Experiment Field | Concrete Specification |
| :--- | :--- |
| **1. Hypothesis** | A standalone React + Three.js (`@react-three/fiber`) prototype using `mapPlacementToThreeJS()` can render a 3D carton and 6 placed items from a static `PackingSolutionResponse` JSON fixture with zero visual clipping/floating, interactive step-by-step scrubbing ($1 \dots 6$), and instant state updates from the editable manifest form. |
| **2. Question Being Tested** |1) Does `mapPlacementToThreeJS()` align the bottom face of floor items ($z=0$) flush with the carton floor ($Y_{\text{three}} = 0$) and align stacked items ($z_2 = dz_1$) with zero gap or overlap? 2) Does WebGL render smoothly ($\ge 30\text{ FPS}$) on the team's demo laptop? |
| **3. Setup** | Vite + React + TypeScript + `@react-three/fiber` + `@react-three/drei` + Tailwind CSS; 3 static mock JSON files in `frontend/src/mocks/` conforming to `Contract v1.0.0` (`mock_optimal_box_m.json`, `mock_uncertain_height_review.json`, `mock_multi_carton_split.json`). |
| **4. Procedure** |1) Run unit tests on `mapPlacementToThreeJS()`. 2) Load `mock_optimal_box_m.json` in the browser, inspect from Top, Front, and Side orthographic camera presets, and step the slider from 1 to 6. 3) Edit an item's height in the manifest form and verify the outgoing `PackingRequest` JSON payload matches `Contract v1.0.0`. |
| **5. Expected Output** | Working local dev server (`http://localhost:5173`) rendering all 3 mock scenarios plus passing unit tests in `frontend/src/utils/__tests__/coordinateTransform.test.ts`. |
| **6. Evaluation Metric** | Visual alignment accuracy ($0.0\text{ mm}$ discrepancy on floor/wall/stack contact planes), frame rate ($\text{FPS}$), and JSON schema conformity of emitted `PackingRequest`. |
| **7. Pass Criteria** |1) Floor items ($z=0$) have exact bottom face $Y_{\text{three}} - H_{\text{three}}/2 == 0$; 2) Front-left-bottom corner item ($x=0, y=0, z=0$) touches the carton's front-left-bottom corner exactly; 3) Step slider cleanly filters visible meshes (`step_number <= activeStep`); 4) All 3 mock states render without console errors at $\ge 30\text{ FPS}$. |
| **8. Fail Criteria** |1) Boxes visually intersect, float above the carton floor, or extend outside the carton walls when `validation.is_valid == true`; OR 2) React Three Fiber dependency conflicts or WebGL context crashes on the demo laptop. |
| **9. Fallback** | **Fallback 4A (R3F Dependency Issue):** Use imperative vanilla `three` (`new THREE.Scene()`, `THREE.BoxGeometry`, `THREE.EdgesGeometry`, `OrbitControls`) inside a standard React `useEffect` `canvas` ref (~80 lines of zero-dependency code).<br/>**Fallback 4B (WebGL Hardware Failure):** Render a deterministic **3-View 2D Orthographic SVG Canvas** (Top-Down $X\text{-}Y$, Front $X\text{-}Z$, Side $Y\text{-}Z$) using the exact same `placements` JSON. |
| **10. Decision Owner** | **Member 4**. |
| **11. Team Escalation Condition** | Escalate to Member 3 only if an additional field is needed in `PackingSolutionResponse` for visualization (must be proposed before the Contract Freeze milestone). |
| **12. Time / Effort Boundary** | **Maximum 3.5 hours** during Phase 0. |

---

## 6. Mandatory Failure-Handling & Escalation Procedure (7 Steps)

If Member 4's Phase 0 experiment hits any **Fail Criterion**:

1. **Step 1 — Record Evidence:** Capture screenshots from Top/Front/Side camera angles and console error logs in `experiments/logs/phase0_frontend_failure_report.md`.
2. **Step 2 — Classify Root Cause:** Determine whether the issue is:
   - *Coordinate Mapping Bug* (missing $-L_c/2$ carton centering offset or $Y \leftrightarrow Z$ swap),
   - *Nominal vs. Inflated Dimension Mismatch* (rendering `nominal_dimensions_mm` at `position_mm` without accounting for `safety_margin_mm`), or
   - *React Three Fiber / WebGL Context Crash*.
3. **Step 3 — Check Scope vs. Cross-Module Impact:** Both coordinate mapping fixes and switching from `@react-three/fiber` to vanilla `three` are **100% internal to Member 4**.
4. **Step 4 — Evaluate Pre-Defined Fallbacks:** If `@react-three/fiber` has peer-dependency issues with React 18/19, switch immediately to Fallback 4A (imperative `three` canvas component).
5. **Step 5 — Propose Concrete Action:** Share a 10-second screen recording of the working 3D mock viewer in the team channel to confirm visual parity with Member 3's coordinate convention.
6. **Step 6 — Update Shared Documentation:** Mark the 3D viewer rendering path as `[Verified]` in `03_EXECUTION_PLAN.md`.
7. **Step 7 — Freeze Contract & Proceed:** Wire the frontend API client (`frontend/src/api/optipackClient.ts`) to switch seamlessly between live backend endpoints (`http://localhost:8000/api/v1/...`) and local mock fixtures (`USE_MOCK_FALLBACK`).

---

## 7. Unit & Integration Test Cases (`frontend/src/utils/__tests__/coordinateTransform.test.ts`)

1. **`test_origin_corner_box_alignment`:** Given carton $300\times 220\times 150\text{ mm}$ and an item of placed size $(100, 80, 60)\text{ mm}$ at `position_mm = {x: 0, y: 0, z: 0}` with `scale = 0.01`:
   - Assert `geometryArgs` equals `[1.0, 0.6, 0.8]`.
   - Assert `position` equals `[-1.0, 0.3, -0.7]`.
   - Assert the item's minimum Three.js corner `(pos.x - w/2, pos.y - h/2, pos.z - d/2)` equals `(-1.5, 0.0, -1.1)`, which is **identically equal** to the carton's minimum corner `(-Lc/2 * s, 0, -Wc/2 * s)`!
2. **`test_stacked_box_vertical_contact`:** Given Item 1 at `z=0, dz=60` and Item 2 at `z=60, dz=40`, assert Item 1 top Y (`0.3 + 0.3 = 0.6`) equals Item 2 bottom Y (`0.8 - 0.2 = 0.6`) with zero gap.
3. **`test_keep_upright_toggle_updates_allowed_rotations`:** Assert that toggling `keep_upright` from `false` to `true` in the manifest state reducer updates `allowed_rotations` to `["LWH", "WLH"]`.
4. **`test_step_scrubber_filtering`:** Given 4 placements with `step_number` $1 \dots 4$, assert setting `activeStep = 2` renders exactly items with `step_number in (1, 2)` opaque and hides (or ghost-wires) steps 3 and 4.
