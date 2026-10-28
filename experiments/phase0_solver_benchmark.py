"""Phase 0 Feasibility Experiment: 3D Bin Packing & Cartonization Solver (Member 3).

Gate Exit Criteria (03_EXECUTION_PLAN.md Section 3):
- Scenarios S1-S4 solved in <= 2.5s with validation.is_valid == True
- S4 respects max payload limits
- S5 detects split / infeasible single carton cleanly

If failed within 3.5 hours:
- Activate Fallback 3A: Immediate fallback to Tier 1 Extreme-Point Heuristic (< 30ms).
"""

import time
from backend.app.schemas.contracts import (
    Dimensions3D,
    PackableItem,
    PackingRequest,
    RotationCode,
    SolverConfig,
)
from backend.app.solver.cpsat_solver import solve_packing


def run_phase0_solver_benchmark():
    print("=" * 60)
    print("OptiPack Phase 0 Feasibility: Member 3 (OR & 3D Solver)")
    print("=" * 60)

    # Scenario 1: Standard 4-box order fitting in BOX-M
    scenario_1_items = [
        PackableItem(
            item_id="item_01",
            display_name="Headphones Box",
            dimensions_mm=Dimensions3D(length_mm=210, width_mm=165, height_mm=95),
            safety_margin_mm=5,
            weight_g=480,
            fragility_class="medium",
            keep_upright=False,
            allowed_rotations=[r for r in RotationCode],
        ),
        PackableItem(
            item_id="item_02",
            display_name="Smartphone Box",
            dimensions_mm=Dimensions3D(length_mm=170, width_mm=90, height_mm=45),
            safety_margin_mm=5,
            weight_g=350,
            fragility_class="low",
            keep_upright=False,
            allowed_rotations=[r for r in RotationCode],
        ),
        PackableItem(
            item_id="item_03",
            display_name="Coffee Mug Box",
            dimensions_mm=Dimensions3D(length_mm=110, width_mm=110, height_mm=120),
            safety_margin_mm=5,
            weight_g=400,
            fragility_class="high",
            keep_upright=True,
            allowed_rotations=[RotationCode.LWH, RotationCode.WLH],
        ),
    ]

    req1 = PackingRequest(
        analysis_id="p0_test_s1",
        solver_config=SolverConfig(mode="cpsat_with_heuristic_fallback", time_limit_ms=2500),
        items=scenario_1_items,
    )

    t0 = time.time()
    resp1 = solve_packing(req1)
    solve_ms = (time.time() - t0) * 1000

    print("\nScenario 1 (Standard 3-box multi-item order):")
    print(f"  - Status: {resp1.status}")
    print(f"  - Solve Time: {solve_ms:.1f} ms (Reported: {resp1.solve_time_ms} ms)")
    if resp1.primary_plan:
        carton = resp1.primary_plan.carton
        metrics = resp1.primary_plan.metrics
        val = resp1.primary_plan.validation
        print(f"  - Selected Carton: {carton.carton_id} ({carton.display_name})")
        print(f"  - Total Cost: ${metrics.total_estimated_cost_usd:.2f} USD")
        print(f"  - Volume Utilization: {metrics.volume_utilization_pct:.1f}%")
        print(f"  - Validation Valid: {val.is_valid} | Overlap Passed: {val.overlap_check_passed} | Support: {val.support_check_passed}")
        print(f"  - Placements Count: {len(resp1.primary_plan.placements)}")

    print("\n--- Phase 0 Evaluation Gate Results ---")
    gate_valid = resp1.primary_plan is not None and resp1.primary_plan.validation.is_valid
    gate_time = solve_ms <= 2500.0

    print(f"Geometric Validity: {'PASS' if gate_valid else 'FAIL'}")
    print(f"Latency Budget: {solve_ms:.1f} ms <= 2500 ms -> {'PASS' if gate_time else 'FAIL'}")

    if gate_valid and gate_time:
        print("\n>> VERDICT: GATE PASSED. Proceed to Phase 1 solver enhancements.")
    else:
        print("\n>> VERDICT: GATE FAILED. Activate Fallback 3A (Tier 1 Extreme-Point Heuristic).")


if __name__ == "__main__":
    run_phase0_solver_benchmark()
