# OptiPack — Member 3 Implementation Specification: Operations Research & 3D Packing Solver (`02C_MEMBER3_OR_3D_SOLVER.md`)

- **Role Owner:** Member 3 — Operations Research & 3D Bin Packing Solver Engineer
- **Primary Module Path:** `backend/app/solver/`
- **Upstream Dependencies:** `PackingRequest` JSON payload (containing user-reviewed items in `mm`, safety margins, weights, fragility classes, and allowed rotation codes)
- **Downstream Consumers:** FastAPI Orchestrator (`/api/v1/orders/pack`), Member 4 (`frontend_ui` renders 3D placements, step-by-step packing sequence, carton comparison table, and validation report)
- **Contract Reference:** `01_PROJECT_SPEC.md` (`Contract v1.0.0`)

---

## 1. Role Objective & Scope Boundaries

Member 3 owns the **Carton Selection, 3D Bin Packing Optimization, Multi-Carton Fallback, and Independent Deterministic Geometry Validation** engine. Specifically, Member 3 must build:

1. **The Carton Catalog & Shipping Cost Evaluator (`catalog.py`):** Evaluates candidate cartons (`BOX-S` through `BOX-XXL`), computes Actual Gross Weight vs. Dimensional (DIM) Weight, and ranks candidate cartons by **Total Estimated Cost ($\text{USD}$)**.
2. **Tier 1 — Fast Deterministic Heuristic Baseline (`heuristic_ep.py`):** An **Extreme-Point First-Fit Decreasing (EP-FFD)** 3D bin packing heuristic that finds a valid, gravity-supported packing arrangement in $< 50\text{ ms}$ and provides an immediate warm-start / fallback upper bound.
3. **Tier 2 — Exact / Bounded Constraint Programming Solver (`cpsat_solver.py`):** A **Google OR-Tools CP-SAT** (`ortools.sat.python.cp_model`) 3D orthogonal packing model with 6-orientation selection, `AddNoOverlap3D` (or explicit 6-way disjunctions), vertical base support constraints, fragility/load layering rules, and center-of-mass lowering.
4. **The Independent Deterministic Validator (`validator.py`):** A completely standalone mathematical verifier that checks any proposed placement (whether produced by CP-SAT, EP-FFD, or test mocks) before it is returned to the frontend.

### Critical Technical Realities (`[Verified]`)
- **Geometric Feasibility $\neq$ Physical Transport Safety:** Standard 3D bin packing constraints (`NoOverlap3D` + boundary containment) permit items to float in mid-air ($z_{\min} > 0$ with nothing underneath) or place a $5\text{ kg}$ metal part on top of a fragile glass box. Our solver and validator **must** explicitly enforce vertical support ($\ge 60\%$ base area supported) and fragility/load stacking tiers.
- **OR-Tools CP-SAT Integer Domain:** CP-SAT operates strictly on integer variables. All item dimensions, safety margins, carton dimensions, and $(x, y, z)$ coordinates are represented in **integer millimeters (`mm`)** (`[Verified]`).
- **OR-Tools CP-SAT Infeasibility Handling:** Unlike commercial MIP solvers (Gurobi/CPLEX), OR-Tools CP-SAT does **not** expose a `.computeIIS()` method (`[Verified]`). To diagnose why a carton is infeasible or to pack the maximum subset when a single carton is insufficient, we use either **Assumption Literals (`model.AddAssumptions`)** or a **Multi-Carton Split Loop**.

---

## 2. Mathematical Formulation of the 3D Cartonization Problem

### 2.1 Effective Dimensions with Uncertainty Margin

Let $I = \{1, 2, \dots, n\}$ be the list of individual item instances to pack (expanding any item with `quantity > 1` into distinct instances `item_01_a`, `item_01_b`, etc.).
For each item $i \in I$ with nominal dimensions $(L_i^0, W_i^0, H_i^0)$ and uncertainty buffer $m_i = \text{safety\_margin\_mm}$ (when `apply_uncertainty_margin == True`):

$$L_i = L_i^0 + m_i, \quad W_i = W_i^0 + m_i, \quad H_i = H_i^0 + m_i$$

*(Note: The solver packs using the inflated dimensions $(L_i, W_i, H_i)$ to guarantee physical clearance, and reports both `placed_dimensions_mm` and `nominal_dimensions_mm` in the output JSON.)*

### 2.2 Decision Variables for a Candidate Carton $c = (L_c, W_c, H_c)$

1. **Placement Position (Minimum Corner in $\text{mm}$):**
   $$x_i \in [0, L_c], \quad y_i \in [0, W_c], \quad z_i \in [0, H_c] \quad \forall i \in I$$
2. **Orientation Selection:**
   Let $R_i \subseteq \{\text{"LWH"}, \text{"WLH"}, \text{"LHW"}, \text{"HLW"}, \text{"WHL"}, \text{"HWL"}\}$ be the allowed rotations for item $i$. For each $r \in R_i$, let $(dx_{i,r}, dy_{i,r}, dz_{i,r})$ be the rotated dimensions along carton axes $(X, Y, Z)$, and introduce a Boolean literal $o_{i,r} \in \{0, 1\}$:
   $$\sum_{r \in R_i} o_{i,r} = 1 \quad \text{(ExactlyOne orientation selected)}$$
   $$dx_i = \sum_{r \in R_i} dx_{i,r} \cdot o_{i,r}, \quad dy_i = \sum_{r \in R_i} dy_{i,r} \cdot o_{i,r}, \quad dz_i = \sum_{r \in R_i} dz_{i,r} \cdot o_{i,r}$$
3. **Boundary Containment Constraints:**
   $$x_i + dx_i \le L_c, \quad y_i + dy_i \le W_c, \quad z_i + dz_i \le H_c \quad \forall i \in I$$
4. **Pairwise 3D Non-Overlap Constraints:**
   For every distinct pair of items $i < j$, introduce 6 relative-position Boolean literals indicating whether item $i$ is strictly to the left ($l_{ij}^X$), right ($l_{ji}^X$), front ($l_{ij}^Y$), back ($l_{ji}^Y$), below ($l_{ij}^Z$), or above ($l_{ji}^Z$) item $j$:
   $$l_{ij}^X \implies x_i + dx_i \le x_j, \qquad l_{ji}^X \implies x_j + dx_j \le x_i$$
   $$l_{ij}^Y \implies y_i + dy_i \le y_j, \qquad l_{ji}^Y \implies y_j + dy_j \le y_i$$
   $$l_{ij}^Z \implies z_i + dz_i \le z_j, \qquad l_{ji}^Z \implies z_j + dz_j \le z_i$$
   $$l_{ij}^X \lor l_{ji}^X \lor l_{ij}^Y \lor l_{ji}^Y \lor l_{ij}^Z \lor l_{ji}^Z = 1$$
   *(In OR-Tools CP-SAT, we combine `model.AddNoOverlap3D(x_intervals, y_intervals, z_intervals)` with these directional literals to achieve maximum propagation speed!)*

### 2.3 Fragility, Stacking & Vertical Support Constraints (`[Proposed]`)

To prevent floating items and crushing fragile goods without blowing up the CP-SAT solve time on $n \le 10$ items:

1. **Stacking / Fragility Ordering Rule:**
   Assign each item a **Stacking Tier Priority** $\tau_i$:
   $$\tau_i = \begin{cases} 1 & \text{if } \text{fragility\_class} == \text{"low"} \text{ and } \text{stackable} == \text{True} \\ 2 & \text{if } \text{fragility\_class} == \text{"medium"} \text{ and } \text{stackable} == \text{True} \\ 3 & \text{if } \text{fragility\_class} == \text{"high"} \text{ or } \text{stackable} == \text{False} \end{cases}$$
   - If item $j$ is non-stackable (`stackable == False` or `max_top_load_g == 0`), no item $i$ can be placed directly above item $j$ when their $(X, Y)$ footprints overlap:
     $$\text{If } \tau_j == 3: \quad l_{ji}^Z = 0 \quad \text{whenever } (X, Y) \text{ projections overlap}$$
   - More generally, a heavier/sturdier item ($\tau_i < \tau_j$ or $w_i > w_j + 500\text{ g}$) cannot sit directly on top of a more fragile/lighter item $j$.
2. **Gravity / Vertical Support Constraint:**
   Every item $i$ must either:
   - Rest directly on the carton floor ($z_i = 0$, controlled by Boolean literal $f_i \in \{0, 1\}$), OR
   - Rest directly on top of at least one supporting item $j \in I \setminus \{i\}$ ($s_{ij} = 1 \implies z_i = z_j + dz_j$, $\tau_j \le \tau_i$, `stackable`$_j == \text{True}$, and the horizontal $(X, Y)$ intersection of item $i$'s center/footprint with item $j$ is non-empty).
   - After CP-SAT returns a candidate solution (or during extreme-point generation), a fast deterministic **Gravity Settling & Support Verification Pass** drops any under-supported item downward until it achieves $\ge 60\%$ base area support (`min_support_ratio = 0.60`), or rejects the orientation if $\ge 60\%$ support cannot be satisfied.

### 2.4 Objective Function Hierarchy

1. **Outer Loop (Carton Catalog Selection):**
   - Pre-filter all cartons $c \in \mathcal{C}$ satisfying:
     $$\sum_{i \in I} L_i W_i H_i \le L_c W_c H_c, \qquad \sum_{i \in I} w_i \le \text{max\_payload\_g}(c), \qquad \max_{i \in I} \min_{r \in R_i} (dx_{i,r}, dy_{i,r}, dz_{i,r}) \le (L_c, W_c, H_c)$$
   - Sort feasible candidate cartons in ascending order of **`total_estimated_cost_usd`** $C_{\text{total}}(c, I)$ (defined in `01_PROJECT_SPEC.md` Section 5.2).
   - Test cartons in ascending cost order; the first carton that yields a validated feasible 3D packing is guaranteed to be **cost-optimal** across the catalog!
2. **Inner Loop (Within a Candidate Carton $c$):**
   Minimize the weighted height & center-of-mass stability objective:
   $$\min \; 100 \cdot Z_{\max} + \sum_{i \in I} w_i \cdot z_i + \sum_{i \in I} (x_i + y_i)$$
   where $Z_{\max} = \max_{i \in I} (z_i + dz_i)$ is the peak packing height. This packs heavier items on the floor ($z_i = 0$), keeps the load compact toward the front-left-bottom corner, and maximizes top clearance for void protection.

---

## 3. Deterministic Packing Step Ordering (`step_number`)

To generate an intuitive **Step-by-Step Packing Guide** for the warehouse operator (and Member 4's slider UI), packed items are sorted lexicographically by:
1. **$z_{\min}$ ascending** (bottom layers must be placed before top layers),
2. **$y_{\min}$ ascending** (back/front ordering so items don't block hand access),
3. **$x_{\min}$ ascending** (left-to-right),
4. **Item volume descending**.
Assign `step_number = 1, 2, ..., N` in this exact order.

---

## 4. Independent Deterministic Geometry & Physics Validator (`backend/app/solver/validator.py`)

> **MANDATORY ARCHITECTURAL RULE:** The validator must be written as a pure, solver-agnostic Python function `validate_packing_plan(carton, items, placements, min_support_ratio=0.60)` that does **not** trust any solver flags. Even if CP-SAT claims `OPTIMAL`, the orchestrator only marks `validation.is_valid = True` if `validate_packing_plan()` returns zero violations.

### 4.1 The 6 Deterministic Checks

```python
from typing import Dict, List, Tuple

ROTATION_MAP = {
    "LWH": lambda L, W, H: (L, W, H),
    "WLH": lambda L, W, H: (W, L, H),
    "LHW": lambda L, W, H: (L, H, W),
    "HLW": lambda L, W, H: (H, L, W),
    "WHL": lambda L, W, H: (W, H, L),
    "HWL": lambda L, W, H: (H, W, L),
}

def compute_2d_overlap_area(
    ax1: int, ay1: int, ax2: int, ay2: int,
    bx1: int, by1: int, bx2: int, by2: int
) -> int:
    ox = max(0, min(ax2, bx2) - max(ax1, bx1))
    oy = max(0, min(ay2, by2) - max(ay1, by1))
    return ox * oy

def validate_packing_plan(
    carton: dict,
    items_by_id: Dict[str, dict],
    placements: List[dict],
    min_support_ratio: float = 0.60,
    apply_uncertainty_margin: bool = True,
) -> dict:
    violations: List[str] = []
    warnings: List[str] = []

    Lc = carton["internal_dimensions_mm"]["length_mm"]
    Wc = carton["internal_dimensions_mm"]["width_mm"]
    Hc = carton["internal_dimensions_mm"]["height_mm"]

    boundary_ok = True
    overlap_ok = True
    rotation_ok = True
    support_ok = True
    fragility_ok = True
    weight_ok = True

    # 1. Total Payload Weight Check
    total_payload_g = sum(items_by_id[p["item_id"]].get("weight_g") or 300 for p in placements)
    if total_payload_g > carton["max_payload_g"]:
        weight_ok = False
        violations.append(
            f"Total payload ({total_payload_g}g) exceeds carton max_payload_g ({carton['max_payload_g']}g)."
        )

    # 2. Per-Item Rotation & Boundary Containment Check
    for p in placements:
        iid = p["item_id"]
        spec = items_by_id[iid]
        rot = p["rotation_code"]
        if rot not in spec["allowed_rotations"]:
            rotation_ok = False
            violations.append(f"Item {iid} uses disallowed rotation '{rot}'.")

        margin = spec.get("safety_margin_mm", 0) if apply_uncertainty_margin else 0
        L = spec["dimensions_mm"]["length_mm"] + margin
        W = spec["dimensions_mm"]["width_mm"] + margin
        H = spec["dimensions_mm"]["height_mm"] + margin
        exp_dx, exp_dy, exp_dz = ROTATION_MAP[rot](L, W, H)

        dx = p["placed_dimensions_mm"]["dx"]
        dy = p["placed_dimensions_mm"]["dy"]
        dz = p["placed_dimensions_mm"]["dz"]
        if (dx, dy, dz) != (exp_dx, exp_dy, exp_dz):
            rotation_ok = False
            violations.append(
                f"Item {iid} placed_dimensions {(dx,dy,dz)} mismatch expected {(exp_dx,exp_dy,exp_dz)} for {rot}."
            )

        x, y, z = p["position_mm"]["x"], p["position_mm"]["y"], p["position_mm"]["z"]
        if x < 0 or y < 0 or z < 0 or (x + dx > Lc) or (y + dy > Wc) or (z + dz > Hc):
            boundary_ok = False
            violations.append(
                f"Item {iid} [{x}..{x+dx}, {y}..{y+dy}, {z}..{z+dz}] exceeds carton ({Lc}x{Wc}x{Hc})."
            )

    # 3. Pairwise 3D AABB Non-Overlap Check
    n = len(placements)
    for i in range(n):
        pi = placements[i]
        xi1, yi1, zi1 = pi["position_mm"]["x"], pi["position_mm"]["y"], pi["position_mm"]["z"]
        xi2 = xi1 + pi["placed_dimensions_mm"]["dx"]
        yi2 = yi1 + pi["placed_dimensions_mm"]["dy"]
        zi2 = zi1 + pi["placed_dimensions_mm"]["dz"]
        for j in range(i + 1, n):
            pj = placements[j]
            xj1, yj1, zj1 = pj["position_mm"]["x"], pj["position_mm"]["y"], pj["position_mm"]["z"]
            xj2 = xj1 + pj["placed_dimensions_mm"]["dx"]
            yj2 = yj1 + pj["placed_dimensions_mm"]["dy"]
            zj2 = zj1 + pj["placed_dimensions_mm"]["dz"]

            ox = max(0, min(xi2, xj2) - max(xi1, xj1))
            oy = max(0, min(yi2, yj2) - max(yi1, yj1))
            oz = max(0, min(zi2, zj2) - max(zi1, zj1))
            if ox > 0 and oy > 0 and oz > 0:
                overlap_ok = False
                violations.append(
                    f"3D overlap ({ox}x{oy}x{oz} mm) between {pi['item_id']} and {pj['item_id']}."
                )

    # 4. Vertical Base Support & Fragility Stacking Check
    for p in placements:
        iid = p["item_id"]
        x1, y1, z1 = p["position_mm"]["x"], p["position_mm"]["y"], p["position_mm"]["z"]
        dx, dy, dz = p["placed_dimensions_mm"]["dx"], p["placed_dimensions_mm"]["dy"], p["placed_dimensions_mm"]["dz"]
        base_area = dx * dy
        if z1 == 0:
            p["support_ratio"] = 1.0
            p["supported_by_item_ids"] = ["CARTON_FLOOR"]
            continue

        supported_area = 0
        supporters: List[str] = []
        for q in placements:
            if q["item_id"] == iid:
                continue
            qx1, qy1, qz1 = q["position_mm"]["x"], q["position_mm"]["y"], q["position_mm"]["z"]
            qdx, qdy, qdz = q["placed_dimensions_mm"]["dx"], q["placed_dimensions_mm"]["dy"], q["placed_dimensions_mm"]["dz"]
            if qz1 + qdz == z1:  # Top face of q touches bottom face of p
                overlap_xy = compute_2d_overlap_area(x1, y1, x1 + dx, y1 + dy, qx1, qy1, qx1 + qdx, qy1 + qdy)
                if overlap_xy > 0:
                    supported_area += overlap_xy
                    supporters.append(q["item_id"])
                    q_spec = items_by_id[q["item_id"]]
                    if not q_spec.get("stackable", True) or q_spec.get("fragility_class") == "high":
                        fragility_ok = False
                        violations.append(
                            f"Item {iid} is stacked on top of non-stackable/fragile item {q['item_id']}."
                        )

        ratio = round(supported_area / float(base_area), 3) if base_area > 0 else 0.0
        p["support_ratio"] = ratio
        p["supported_by_item_ids"] = supporters
        if ratio < min_support_ratio:
            support_ok = False
            violations.append(
                f"Item {iid} at z={z1}mm has insufficient vertical support ({ratio*100:.1f}% < {min_support_ratio*100:.1f}%)."
            )

    is_valid = all([boundary_ok, overlap_ok, rotation_ok, support_ok, fragility_ok, weight_ok])
    return {
        "is_valid": is_valid,
        "boundary_check_passed": boundary_ok,
        "overlap_check_passed": overlap_ok,
        "rotation_check_passed": rotation_ok,
        "support_check_passed": support_ok,
        "fragility_check_passed": fragility_ok,
        "weight_check_passed": weight_ok,
        "violations": violations,
        "warnings": warnings,
    }
```

---

## 5. Reference Solver Architecture (Two-Tier Heuristic + CP-SAT)

### 5.1 Tier 1: Extreme-Point First-Fit Decreasing Heuristic (`heuristic_ep.py`)

1. Sort items primarily by **Stacking Tier Priority $\tau_i$ ascending** (sturdy/heavy items first), secondarily by **base footprint area $L_i W_i$ descending**, and tertiarily by **volume descending**.
2. Maintain a list of candidate 3D **Extreme Points** $E$, initialized to $\{(0, 0, 0)\}$.
3. For each item $i$, evaluate every candidate point $(x_e, y_e, z_e) \in E$ and every allowed rotation $r \in R_i$:
   - Drop $z_e$ down to the lowest collision-free height $z^*$ resting on $z^* = 0$ or the top face of existing packed items.
   - Check boundary containment, 3D non-overlap, fragility rules, and **`support_ratio >= min_support_ratio`**.
   - Select the feasible placement $(x^*, y^*, z^*, r^*)$ minimizing $100 \cdot (z^* + dz) + 10 \cdot z^* + (x^* + y^*)$.
   - Add new extreme points $(x^* + dx, y^*, z^*)$, $(x^*, y^* + dy, z^*)$, and $(x^*, y^*, z^* + dz)$ to $E$.

### 5.2 Tier 2: OR-Tools CP-SAT Solver with Warm-Start (`cpsat_solver.py`)

1. Run Tier 1 (`heuristic_ep.py`) across all candidate cartons in $< 20\text{ ms}$.
2. For each candidate carton $c$ in ascending order of `total_estimated_cost_usd`:
   - Build the CP-SAT model (`cp_model.CpModel()`) with integer interval variables, 6-orientation `AddExactlyOne`, `AddNoOverlap3D`, and stacking/support constraints.
   - If Tier 1 already found a valid packing for carton $c$, inject its coordinates as solution hints (`model.AddHint(...)`) so CP-SAT immediately starts with a feasible upper bound.
   - Set `solver.parameters.max_time_in_seconds = min(1.0, remaining_budget_sec)` and `solver.parameters.num_search_workers = 4`.
   - Pass any CP-SAT solution through `validate_packing_plan()`. If valid, return immediately as the cost-optimal single-carton plan.
3. **Multi-Carton Split / Infeasibility Diagnosis:**
   - If no single carton in the catalog (`BOX-S` through `BOX-XXL`) can pack all items (e.g., total volume $> 84,000\text{ cm}^3$ or incompatible non-stackable footprints), and `allow_multi_carton_split == True`, run a **Max-Volume Subset Packing** on `BOX-L` / `BOX-XL` to pack the largest feasible subset in `primary_plan`, and pack the remaining items into `overflow_plans[0]` with clear `infeasibility_diagnostics` explaining why a single carton could not hold the entire order.

---

## 6. Phase 0 Proof-of-Feasibility Experiment (`Member 3 Gate`)

Member 3 must execute the following standalone benchmark in `experiments/phase0_solver_benchmark.py`:

| Experiment Field | Concrete Specification |
| :--- | :--- |
| **1. Hypothesis** | The two-tier solver (Extreme-Point Heuristic + OR-Tools CP-SAT with `validate_packing_plan()`) can solve 100% of 2-to-8 item e-commerce order instances across the 5-carton catalog in $\le 2,000\text{ ms}$ with zero geometric/support violations, and correctly select the lowest-cost carton when DIM weight vs. actual weight tradeoffs occur. |
| **2. Question Being Tested** |1) Does CP-SAT with 6 rotations + support constraints converge within $2.0\text{ seconds}$ for $N = 8$ items? 2) Does `validate_packing_plan()` catch 100% of synthetic floating/overlapping/fragility violations? |
| **3. Setup** | Python 3.11 with `ortools>=9.8`; 5 synthetic benchmark scenarios: (S1) 3 small items fitting `BOX-S`; (S2) 6 mixed items with 2 `keep_upright=True` and 1 `fragility_class="high"`; (S3) 8 items near 72% capacity of `BOX-L`; (S4) Heavy dense order ($9\text{ kg}$ in small volume, exceeding `BOX-S` and `BOX-M` payload limits); (S5) Oversized 10-item order requiring a 2-carton split. |
| **4. Procedure** | Run both Tier 1 (EP-FFD) and Tier 2 (CP-SAT) on Scenarios S1–S5. Record solve time (`ms`), selected carton, total cost (`USD`), utilization (`%`), and run `validate_packing_plan()` on every output. Also run `validate_packing_plan()` on 5 intentionally corrupted placements (overlap, out-of-bounds, floating box at $z=50$, crushed fragile box, disallowed rotation). |
| **5. Expected Output** | Console and JSON summary `experiments/logs/phase0_solver_results.json` showing solve times, cost comparisons, and validator pass/fail matrices. |
| **6. Evaluation Metric** | Solve time (`ms`), validator pass rate on solver outputs ($100\%$ required), validator detection rate on corrupted inputs ($100\%$ required), and cost optimality. |
| **7. Pass Criteria** |1) All feasible scenarios (S1–S4) return `validation.is_valid == True` within $\le 2,500\text{ ms}$; 2) Scenario S4 correctly rejects `BOX-S`/`BOX-M` due to `max_payload_g` and picks `BOX-L`; 3) Scenario S5 cleanly outputs a 2-carton split without crashing; 4) All 5 corrupted placements are rejected by `validate_packing_plan()`. |
| **8. Fail Criteria** |1) CP-SAT times out ($> 3,000\text{ ms}$) without returning a valid solution on $N \le 8$ items; OR 2) CP-SAT produces floating boxes ($0 < \text{support\_ratio} < 0.60$) that fail `validate_packing_plan()`. |
| **9. Fallback** | **Fallback 3A (CP-SAT Support Complexity Slowdown):** Use CP-SAT strictly for $(X, Y, Z)$ non-overlap + orientation + stacking-tier $Z$-ordering, and apply a deterministic **Post-Solve Gravity Projection (`drop_to_support()`)** followed by `validate_packing_plan()`. If the post-settled CP-SAT layout fails $\ge 60\%$ support, immediately return the Tier 1 **Extreme-Point Heuristic (`heuristic_ep.py`)** solution (which enforces $\ge 60\%$ support constructively at every placement step in $< 30\text{ ms}$). |
| **10. Decision Owner** | **Member 3**. |
| **11. Team Escalation Condition** | Escalate to all members only if any field in `PackingSolutionResponse` needs adjustment (unlikely, as solver internals are completely encapsulated behind `/api/v1/orders/pack`). |
| **12. Time / Effort Boundary** | **Maximum 3.5 hours** during Phase 0. |

---

## 7. Mandatory Failure-Handling & Escalation Procedure (7 Steps)

If Member 3's Phase 0 experiment hits any **Fail Criterion**:

1. **Step 1 — Record Evidence:** Save the benchmark JSON timings and any validator violation traces in `experiments/logs/phase0_solver_failure_report.md`.
2. **Step 2 — Classify Root Cause:** Identify whether the bottleneck is:
   - *Combinatorial explosion in pairwise support area constraints inside CP-SAT*,
   - *Symmetry breaking among identical items*, or
   - *Overly strict `min_support_ratio` on narrow upright items*.
3. **Step 3 — Check Scope vs. Cross-Module Impact:** Switching between full CP-SAT support constraints, CP-SAT + gravity projection, and Extreme-Point heuristic fallback is **100% internal to Member 3** (`solver_used` telemetry simply reports `"ortools_cpsat"` vs. `"extreme_point_heuristic"`).
4. **Step 4 — Evaluate Pre-Defined Fallbacks:** Enable Fallback 3A (Extreme-Point heuristic warm-start + fallback whenever CP-SAT does not produce a validator-passing layout within $1,500\text{ ms}$).
5. **Step 5 — Propose Concrete Action:** Inform the team of the locked-in `time_limit_ms` ($2,000\text{ ms}$) and confirm that `validate_packing_plan()` is active as a mandatory gate.
6. **Step 6 — Update Shared Documentation:** Update solver latency and status tags in `01_PROJECT_SPEC.md` and `03_EXECUTION_PLAN.md`.
7. **Step 7 — Freeze Contract & Proceed:** Deliver a rock-solid `pack_order(request: PackingRequest) -> PackingSolutionResponse` function and export 3 golden JSON fixture files (`tests/fixtures/packing_solution_*.json`) immediately so Member 4 can test the 3D frontend against real solver outputs.

---

## 8. Unit & Integration Test Cases (`tests/test_solver_and_validator.py`)

1. **`test_validator_rejects_pairwise_overlap`:** Construct two $100\times 100\times 100\text{ mm}$ items placed at $(0,0,0)$ and $(50,0,0)$. Assert `validate_packing_plan()` returns `is_valid == False` and `overlap_check_passed == False`.
2. **`test_validator_rejects_floating_item`:** Place an item at $(0, 0, 50)$ with nothing underneath it. Assert `support_check_passed == False` and `support_ratio == 0.0`.
3. **`test_validator_rejects_crushed_fragile_item`:** Place a `"high"` fragility item (`stackable=False`) at $(0,0,0)$ and another item directly on top of it at $(0,0,100)$. Assert `fragility_check_passed == False`.
4. **`test_keep_upright_enforced_in_solver`:** Pass an item with `keep_upright=True` and `allowed_rotations=["LWH", "WLH"]`. Assert the solver selects either `"LWH"` or `"WLH"` and `placed_dimensions_mm.dz == height_mm + safety_margin_mm`.
5. **`test_dim_weight_vs_actual_weight_cost_selection`:** Verify that `evaluate_carton_cost()` computes `billable_weight_kg = max(actual_gross_weight_kg, dim_weight_kg)` and selects `BOX-M` over `BOX-L` when both are geometrically feasible.
