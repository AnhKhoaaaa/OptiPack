# OptiPack — E-Commerce Multi-Item 3D Cartonization & Packing Assistant

OptiPack is a rapid-turnaround hackathon MVP designed for e-commerce multi-item fulfillment cartonization:
Given an order of multiple distinct items captured at a controlled packing bench, OptiPack:
1. Detects and measures items in 3D millimeters with explicit uncertainty quantification (**Computer Vision & Metrology**).
2. Extracts packaging and handling semantics via the **Meta Model API** (`muse-spark-1.3`).
3. Evaluates shipping costs (Actual vs. DIM weight) and optimizes 3D item placement inside a standard carton catalog (**OR-Tools CP-SAT & 3D Heuristics**).
4. Verifies physical validity via an **Independent Deterministic Geometry Validator**.
5. Renders an interactive step-by-step **3D Packing Guide with inline manual override capabilities** (React + Three.js).

---

## 1. Team Module Ownership & Responsibilities

| Role | Module Directory | Primary Responsibilities | Phase 0 Gate Script |
| :--- | :--- | :--- | :--- |
| **Member 1** (CV & Metrology) | `backend/app/cv/` | ArUco A4 board detection (`solvePnP`), 2D segmentation, 3D bounding box estimation $(L, W, H\text{ mm})$, uncertainty $(\pm\sigma)$. | `experiments/phase0_cv_metrology.py` |
| **Member 2** (AI & Meta Model API) | `backend/app/ai/` | Meta Model API (`muse-spark-1.3`, `sam-3.1`), JSON Schema validation, safety guard against hallucinated weights, SHA-256 disk cache. | `experiments/phase0_meta_api.py` |
| **Member 3** (OR & 3D Solver) | `backend/app/solver/` | Standard carton catalog, shipping cost model, Extreme-Point heuristic, OR-Tools CP-SAT solver, independent deterministic validator. | `experiments/phase0_solver_benchmark.py` |
| **Member 4** (Frontend & 3D UI) | `frontend/src/` | Upload / capture workflow, editable manifest table with uncertainty warnings, Three.js 3D viewport, step-by-step placement slider. | `frontend/src/utils/__tests__/coordinateTransform.test.ts` |

---

## 2. Repository Directory Structure

```text
OptiPack/
├── 01_project_spec.md            # Master Technical Specification (Contract v1.0.0)
├── 02a_member1_computer_vision.md # Deep-dive guide for Member 1
├── 02b_member2_ai_meta_model_api.md # Deep-dive guide for Member 2
├── 02c_member3_or_3d_solver.md    # Deep-dive guide for Member 3
├── 02d_member4_frontend_3d_visualization.md # Deep-dive guide for Member 4
├── 03_execution_plan.md          # Schedule, Phase 0 Feasibility Gates & Risk Register
├── requirements.txt              # Python backend dependencies
├── .env.example                  # Environment configuration template
├── .gitignore
├── backend/
│   └── app/
│       ├── api/                  # FastAPI orchestrator & routers
│       │   ├── main.py           # App entrypoint, CORS, static mounts
│       │   └── routers/          # /orders and /catalog endpoints
│       ├── cv/                   # Member 1: CV & 3D Metrology
│       ├── ai/                   # Member 2: Meta Model API & Sanitizers
│       ├── solver/               # Member 3: Carton catalog, Cost, EP & CP-SAT Solver
│       └── schemas/              # Pydantic models for Contract v1.0.0
├── frontend/                     # Member 4: React + TypeScript + Three.js UI
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── components/           # UploadPanel, ManifestTable, PackingViewer3D, CostScorecard
│       ├── mocks/                # Golden JSON fixtures for standalone UI dev
│       ├── types/contract.ts     # TypeScript Contract v1.0.0 interfaces
│       └── utils/                # Coordinate transform adapter (Z-up to Three.js Y-up)
├── experiments/                  # Phase 0 Feasibility Experiment Scripts (Hours 1–4)
│   ├── phase0_cv_metrology.py    # Member 1 gate benchmark
│   ├── phase0_meta_api.py        # Member 2 gate benchmark
│   └── phase0_solver_benchmark.py# Member 3 gate benchmark
└── tests/
    ├── fixtures/                 # Golden sample JSON contracts
    ├── test_contracts.py         # Schema validation tests
    └── test_e2e_pipeline.py      # FastAPI end-to-end integration tests
```

---

## 3. Canonical Shared Conventions (`Contract v1.0.0`)

All modules adhere strictly to these shared units and coordinate conventions:
- **Dimensions & Coordinates:** Integer millimeters (`mm`) (`int`).
- **Weight:** Grams (`g`) (`int`), or `null` if unobservable (triggers density fallback).
- **Coordinate System:** Right-Handed, $Z$-Up Cartesian coordinate system.
  - Front-Left-Bottom corner is Origin $(0, 0, 0)$.
  - $+X$: Left to Right ($0 \le x \le L_{\text{carton}}$)
  - $+Y$: Front to Back ($0 \le y \le W_{\text{carton}}$)
  - $+Z$: Upward against gravity ($0 \le z \le H_{\text{carton}}$)
- **Rotations:** 6 orthogonal rotation codes (`LWH`, `WLH`, `LHW`, `HLW`, `WHL`, `HWL`).
  - When `keep_upright == true`, only `LWH` and `WLH` are permitted.

---

## 4. Phase 0 Feasibility Gates (Hours 1–4)

Before full integration, each team member runs and iterates on their Phase 0 feasibility benchmark:

1. **Member 1 (CV & Metrology):**
   ```bash
   python experiments/phase0_cv_metrology.py
   ```
   - *Target:* Reprojection error $\le 2.5\text{ px}$, Footprint MAE $\le 8\text{ mm}$, Height MAE $\le 12\text{ mm}$.
   - *Real captures:* [`experiments/real_t01/REPORT.md`](experiments/real_t01/REPORT.md) documents eight RGB photos and five ground-truth items. Real T01 gate is **NOT PASSED**; this script now audits both synthetic and real data by default. Select `--dataset synthetic` or `--dataset real` to run one.
   - *Paper & method:* [`RESEARCH_DECISION.md`](experiments/real_t01/RESEARCH_DECISION.md) explains the CubeSLAM-inspired edge-constrained cuboid fit, official paper/code sources, provenance, and limits; [`real_t01/README.md`](experiments/real_t01/README.md) contains reproducible commands. Best exploratory **two-view** means: L/W 12.39 mm and H 8.88 mm, both with **manual ROIs** and provisional intrinsics, so not production results.

2. **Member 2 (AI & Meta API):**
   ```bash
   python experiments/phase0_meta_api.py
   ```
   - *Target:* 100% schema compliance, P95 latency $\le 4.0\text{ s}$, 0 fabricated weights on opaque boxes.

3. **Member 3 (OR & 3D Solver):**
   ```bash
   python experiments/phase0_solver_benchmark.py
   ```
   - *Target:* Solve time $\le 2.5\text{ s}$, zero overlap, $\ge 60\%$ vertical base support.

4. **Member 4 (Frontend UI & 3D):**
   - Run coordinate adapter unit tests and preview UI at `http://localhost:5173`.

---

## 5. Developer Quickstart

### Backend Setup (Python 3.10+)

1. Create and activate a virtual environment:
   ```bash
   # Windows PowerShell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   ```bash
   cp .env.example .env
   # Add your MODEL_API_KEY if testing live Meta API calls
   ```

4. Run tests:
   ```bash
   pytest tests/
   ```

5. Start the FastAPI backend server:
   ```bash
   python -m uvicorn backend.app.api.main:app --reload --port 8000
   ```
   - Interactive Swagger API docs: `http://localhost:8000/docs`
   - Health check: `http://localhost:8000/health`

### Frontend Setup (Node.js 18+)

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Launch development server:
   ```bash
   npm run dev
   ```
   - Open browser at: `http://localhost:5173`
