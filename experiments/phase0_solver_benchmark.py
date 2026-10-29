"""Phase 0 Feasibility Experiment: 3D Bin Packing & Cartonization Solver (Member 3).

Reference Document: document/02c_member3_or_3d_solver.md Section 6
GitHub Issue: #3 [Phase 0 Gate] Member 3: 3D Bin Packing Solver & Geometry Validator

Gate Exit Criteria:
- Scenarios S1-S4 solved in <= 2.5s with validation.is_valid == True
- S4 respects max payload limits (rejects BOX-S/BOX-M, picks BOX-L)
- S5 cleanly detects and splits oversized orders into multi-carton plans
- 5 corrupted synthetic placements are 100% rejected by deterministic validator
- Outputs detailed JSON benchmark log to experiments/logs/phase0_solver_results.json
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.schemas.contracts import (
    CartonSpec,
    Dimensions3D,
    PackableItem,
    PackingRequest,
    PlacedDimensions3D,
    PlacedItem,
    Position3D,
    RotationCode,
    SolverConfig,
)
from backend.app.solver.carton_catalog import STANDARD_CARTONS
from backend.app.solver.cpsat_solver import solve_packing
from backend.app.solver.geometry_validator import validate_packing_solution


def create_scenarios() -> Dict[str, List[PackableItem]]:
    """Define the 5 benchmark scenarios described in 02C_MEMBER3_OR_3D_SOLVER.md."""
    # S1: 3 small items fitting comfortably into BOX-S (200x150x100 mm)
    s1_items = [
        PackableItem(
            item_id="s1_item_1",
            display_name="Small Box A",
            dimensions_mm=Dimensions3D(length_mm=85, width_mm=65, height_mm=40),
            safety_margin_mm=2,
            weight_g=250,
            fragility_class="low",
            allowed_rotations=[r for r in RotationCode],
        ),
        PackableItem(
            item_id="s1_item_2",
            display_name="Small Box B",
            dimensions_mm=Dimensions3D(length_mm=95, width_mm=75, height_mm=35),
            safety_margin_mm=2,
            weight_g=300,
            fragility_class="low",
            allowed_rotations=[r for r in RotationCode],
        ),
        PackableItem(
            item_id="s1_item_3",
            display_name="Small Box C",
            dimensions_mm=Dimensions3D(length_mm=100, width_mm=60, height_mm=40),
            safety_margin_mm=2,
            weight_g=200,
            fragility_class="low",
            allowed_rotations=[r for r in RotationCode],
        ),
    ]

    # S2: 6 mixed items with 2 keep_upright=True and 1 high fragility
    s2_items = [
        PackableItem(
            item_id="s2_item_1",
            display_name="Solid Wooden Base",
            dimensions_mm=Dimensions3D(length_mm=160, width_mm=120, height_mm=50),
            safety_margin_mm=3,
            weight_g=950,
            fragility_class="low",
            stackable=True,
            allowed_rotations=[r for r in RotationCode],
        ),
        PackableItem(
            item_id="s2_item_2",
            display_name="Metal Bracket Box",
            dimensions_mm=Dimensions3D(length_mm=140, width_mm=90, height_mm=40),
            safety_margin_mm=3,
            weight_g=700,
            fragility_class="low",
            stackable=True,
            allowed_rotations=[r for r in RotationCode],
        ),
        PackableItem(
            item_id="s2_item_3",
            display_name="Upright Cosmetic Serum",
            dimensions_mm=Dimensions3D(length_mm=50, width_mm=50, height_mm=130),
            safety_margin_mm=3,
            weight_g=220,
            fragility_class="medium",
            keep_upright=True,
            allowed_rotations=[RotationCode.LWH, RotationCode.WLH],
        ),
        PackableItem(
            item_id="s2_item_4",
            display_name="Upright Essential Oil",
            dimensions_mm=Dimensions3D(length_mm=45, width_mm=45, height_mm=110),
            safety_margin_mm=3,
            weight_g=180,
            fragility_class="medium",
            keep_upright=True,
            allowed_rotations=[RotationCode.LWH, RotationCode.WLH],
        ),
        PackableItem(
            item_id="s2_item_5",
            display_name="Fragile Ceramic Mug",
            dimensions_mm=Dimensions3D(length_mm=110, width_mm=100, height_mm=95),
            safety_margin_mm=3,
            weight_g=380,
            fragility_class="high",
            stackable=False,
            allowed_rotations=[RotationCode.LWH, RotationCode.WLH],
        ),
        PackableItem(
            item_id="s2_item_6",
            display_name="Cotton Swabs Pack",
            dimensions_mm=Dimensions3D(length_mm=80, width_mm=60, height_mm=35),
            safety_margin_mm=3,
            weight_g=90,
            fragility_class="low",
            stackable=True,
            allowed_rotations=[r for r in RotationCode],
        ),
    ]

    # S3: 8 items near ~72% volumetric capacity of BOX-L (400x300x200 = 24,000 cm3)
    s3_items = [
        PackableItem(
            item_id=f"s3_item_{i}",
            display_name=f"Standard Retail Unit {i}",
            dimensions_mm=Dimensions3D(length_mm=180, width_mm=135, height_mm=85),
            safety_margin_mm=2,
            weight_g=600,
            fragility_class="medium",
            allowed_rotations=[r for r in RotationCode],
        )
        for i in range(1, 9)
    ]

    # S4: Heavy dense order (9.0 kg total, exceeding BOX-S [3kg] and BOX-M [8kg] limits)
    s4_items = [
        PackableItem(
            item_id="s4_lead_block_1",
            display_name="Heavy Steel Component 1",
            dimensions_mm=Dimensions3D(length_mm=150, width_mm=120, height_mm=70),
            safety_margin_mm=2,
            weight_g=4500,  # 4.5 kg
            fragility_class="low",
            allowed_rotations=[r for r in RotationCode],
        ),
        PackableItem(
            item_id="s4_lead_block_2",
            display_name="Heavy Steel Component 2",
            dimensions_mm=Dimensions3D(length_mm=150, width_mm=120, height_mm=70),
            safety_margin_mm=2,
            weight_g=4500,  # 4.5 kg
            fragility_class="low",
            allowed_rotations=[r for r in RotationCode],
        ),
    ]

    # S5: Oversized 10-item order requiring a 2-carton split (exceeds single BOX-XXL)
    s5_items = [
        PackableItem(
            item_id=f"s5_bulky_item_{i}",
            display_name=f"Bulky Industrial Casing {i}",
            dimensions_mm=Dimensions3D(length_mm=380, width_mm=270, height_mm=170),
            safety_margin_mm=2,
            weight_g=3500,
            fragility_class="low",
            allowed_rotations=[r for r in RotationCode],
        )
        for i in range(1, 11)
    ]

    return {
        "S1": s1_items,
        "S2": s2_items,
        "S3": s3_items,
        "S4": s4_items,
        "S5": s5_items,
    }


def run_corrupted_validator_tests() -> List[Dict[str, Any]]:
    """Test validator against 5 synthetic corrupted placements."""
    results = []
    carton = next(c for c in STANDARD_CARTONS if c.carton_id == "BOX-M")

    base_item = PackableItem(
        item_id="box_base",
        display_name="Base Box",
        dimensions_mm=Dimensions3D(length_mm=100, width_mm=100, height_mm=60),
        safety_margin_mm=0,
        weight_g=500,
        allowed_rotations=[RotationCode.LWH],
    )
    other_item = PackableItem(
        item_id="box_other",
        display_name="Other Box",
        dimensions_mm=Dimensions3D(length_mm=100, width_mm=100, height_mm=60),
        safety_margin_mm=0,
        weight_g=500,
        allowed_rotations=[RotationCode.LWH],
    )

    # Test 1: Pairwise AABB Overlap
    p1 = PlacedItem(
        step_number=1,
        item_id="box_base",
        display_name="Base Box",
        rotation_code=RotationCode.LWH,
        position_mm=Position3D(x=0, y=0, z=0),
        placed_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=60),
        nominal_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=60),
        support_ratio=1.0,
    )
    p_overlap = PlacedItem(
        step_number=2,
        item_id="box_other",
        display_name="Other Box",
        rotation_code=RotationCode.LWH,
        position_mm=Position3D(x=40, y=40, z=0),  # overlaps with p1
        placed_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=60),
        nominal_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=60),
        support_ratio=1.0,
    )
    rep1 = validate_packing_solution(carton, [base_item, other_item], [p1, p_overlap])
    results.append({
        "test_name": "C1_Pairwise_Overlap",
        "expected_caught": True,
        "actually_caught": not rep1.is_valid and not rep1.overlap_check_passed,
        "violations": rep1.violations,
    })

    # Test 2: Boundary Out of Bounds
    p_oob = PlacedItem(
        step_number=1,
        item_id="box_base",
        display_name="Base Box",
        rotation_code=RotationCode.LWH,
        position_mm=Position3D(x=250, y=0, z=0),  # 250 + 100 = 350 > carton_l (300)
        placed_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=60),
        nominal_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=60),
        support_ratio=1.0,
    )
    rep2 = validate_packing_solution(carton, [base_item], [p_oob])
    results.append({
        "test_name": "C2_Out_Of_Bounds",
        "expected_caught": True,
        "actually_caught": not rep2.is_valid and not rep2.boundary_check_passed,
        "violations": rep2.violations,
    })

    # Test 3: Floating Box (z=50 with no support)
    p_float = PlacedItem(
        step_number=1,
        item_id="box_base",
        display_name="Base Box",
        rotation_code=RotationCode.LWH,
        position_mm=Position3D(x=0, y=0, z=50),  # floating
        placed_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=60),
        nominal_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=60),
        support_ratio=0.0,
    )
    rep3 = validate_packing_solution(carton, [base_item], [p_float])
    results.append({
        "test_name": "C3_Floating_Box",
        "expected_caught": True,
        "actually_caught": not rep3.is_valid and not rep3.support_check_passed,
        "violations": rep3.violations,
    })

    # Test 4: Crushed Fragile Box
    fragile_item = PackableItem(
        item_id="box_fragile",
        display_name="Fragile Glass",
        dimensions_mm=Dimensions3D(length_mm=100, width_mm=100, height_mm=60),
        safety_margin_mm=0,
        weight_g=200,
        fragility_class="high",
        stackable=False,
        allowed_rotations=[RotationCode.LWH],
    )
    p_fragile = PlacedItem(
        step_number=1,
        item_id="box_fragile",
        display_name="Fragile Glass",
        rotation_code=RotationCode.LWH,
        position_mm=Position3D(x=0, y=0, z=0),
        placed_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=60),
        nominal_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=60),
        support_ratio=1.0,
    )
    p_on_fragile = PlacedItem(
        step_number=2,
        item_id="box_base",
        display_name="Heavy Base Box",
        rotation_code=RotationCode.LWH,
        position_mm=Position3D(x=0, y=0, z=60),  # directly atop unstackable fragile
        placed_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=60),
        nominal_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=60),
        support_ratio=1.0,
        supported_by_item_ids=["box_fragile"],
    )
    rep4 = validate_packing_solution(carton, [fragile_item, base_item], [p_fragile, p_on_fragile])
    results.append({
        "test_name": "C4_Crushed_Fragile_Box",
        "expected_caught": True,
        "actually_caught": not rep4.is_valid and not rep4.fragility_check_passed,
        "violations": rep4.violations,
    })

    # Test 5: Disallowed Rotation
    p_bad_rot = PlacedItem(
        step_number=1,
        item_id="box_base",
        display_name="Base Box",
        rotation_code=RotationCode.HWL,  # Not in allowed_rotations [LWH]
        position_mm=Position3D(x=0, y=0, z=0),
        placed_dimensions_mm=PlacedDimensions3D(dx=60, dy=100, dz=100),
        nominal_dimensions_mm=PlacedDimensions3D(dx=60, dy=100, dz=100),
        support_ratio=1.0,
    )
    rep5 = validate_packing_solution(carton, [base_item], [p_bad_rot])
    results.append({
        "test_name": "C5_Disallowed_Rotation",
        "expected_caught": True,
        "actually_caught": not rep5.is_valid and not rep5.rotation_check_passed,
        "violations": rep5.violations,
    })

    return results


def run_phase0_solver_benchmark():
    print("=" * 72)
    print("OptiPack Phase 0 Feasibility Gate: Member 3 (OR & 3D Packing Solver)")
    print("=" * 72)

    scenarios = create_scenarios()
    scenario_results: Dict[str, Any] = {}

    all_criteria_met = True

    # 1. Run Scenarios S1 - S5
    for s_name, items in scenarios.items():
        print(f"\n--- Running Scenario {s_name} ({len(items)} items) ---")
        req = PackingRequest(
            analysis_id=f"p0_bench_{s_name.lower()}",
            solver_config=SolverConfig(
                mode="cpsat_with_heuristic_fallback",
                time_limit_ms=2500,
                allow_multi_carton_split=True,
            ),
            items=items,
        )

        t0 = time.time()
        resp = solve_packing(req)
        solve_ms = round((time.time() - t0) * 1000, 2)

        is_valid_plan = False
        selected_carton_id = None
        cost_usd = 0.0
        util_pct = 0.0
        cartons_used = 1

        if resp.primary_plan:
            is_valid_plan = resp.primary_plan.validation.is_valid
            selected_carton_id = resp.primary_plan.carton.carton_id
            cost_usd = resp.primary_plan.metrics.total_estimated_cost_usd
            util_pct = resp.primary_plan.metrics.volume_utilization_pct

            if resp.overflow_plans:
                cartons_used += len(resp.overflow_plans)
                for over in resp.overflow_plans:
                    if not over.validation.is_valid:
                        is_valid_plan = False
                    cost_usd += over.metrics.total_estimated_cost_usd

        # Scenario specific validations
        s_pass = True
        notes = []

        if s_name in ("S1", "S2", "S3"):
            if not is_valid_plan or solve_ms > 2500.0 or not resp.single_carton_feasible:
                s_pass = False
            notes.append(f"Carton: {selected_carton_id}, Cost: ${cost_usd:.2f}, Time: {solve_ms}ms")

        elif s_name == "S4":
            # Must reject BOX-S and BOX-M due to payload (9kg > 3kg and 8kg)
            box_s_eval = next((c for c in resp.candidate_carton_comparison if c.carton_id == "BOX-S"), None)
            box_m_eval = next((c for c in resp.candidate_carton_comparison if c.carton_id == "BOX-M"), None)
            s_rejected = box_s_eval and not box_s_eval.feasible and "payload" in (box_s_eval.rejection_reason or "").lower()
            m_rejected = box_m_eval and not box_m_eval.feasible and "payload" in (box_m_eval.rejection_reason or "").lower()
            if not (s_rejected and m_rejected and selected_carton_id == "BOX-L" and is_valid_plan and solve_ms <= 2500.0):
                s_pass = False
            notes.append(f"BOX-S payload reject: {s_rejected}, BOX-M payload reject: {m_rejected}, Picked: {selected_carton_id}")

        elif s_name == "S5":
            # Must split into multi-carton with all plans valid
            if not (not resp.single_carton_feasible and len(resp.overflow_plans) >= 1 and is_valid_plan and solve_ms <= 2500.0):
                s_pass = False
            notes.append(f"Multi-carton split: {cartons_used} cartons, Unpacked remaining: {len(resp.unpacked_item_ids)}")

        if not s_pass:
            all_criteria_met = False

        print(f"  Status: {resp.status} | Engine: {resp.solver_used} | Wall Time: {solve_ms} ms")
        print(f"  Single Feasible: {resp.single_carton_feasible} | Total Cartons: {cartons_used}")
        print(f"  Primary Carton: {selected_carton_id} | Cost: ${cost_usd:.2f} | Valid: {is_valid_plan}")
        print(f"  Pass Criteria: {'PASS' if s_pass else 'FAIL'} ({', '.join(notes)})")

        scenario_results[s_name] = {
            "status": resp.status,
            "solver_used": resp.solver_used,
            "solve_time_ms": solve_ms,
            "single_carton_feasible": resp.single_carton_feasible,
            "cartons_used": cartons_used,
            "primary_carton": selected_carton_id,
            "total_estimated_cost_usd": cost_usd,
            "volume_utilization_pct": util_pct,
            "is_valid": is_valid_plan,
            "gate_passed": s_pass,
            "notes": notes,
        }

    # 2. Corrupted Validator Tests
    print("\n--- Running 5 Synthetic Corrupted Validator Tests ---")
    corrupted_results = run_corrupted_validator_tests()
    corrupted_all_caught = True
    for c in corrupted_results:
        caught = c["actually_caught"]
        if not caught:
            corrupted_all_caught = False
            all_criteria_met = False
        print(f"  [{'PASS' if caught else 'FAIL'}] {c['test_name']}: Detected = {caught} (Violations: {c['violations']})")

    # 3. Export JSON Log Report
    logs_dir = Path(__file__).resolve().parents[1] / "experiments" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    report_file = logs_dir / "phase0_solver_results.json"

    full_report = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "member": "Member 3 (OR & 3D Packing Solver)",
        "phase": "Phase 0 Feasibility Gate",
        "overall_verdict": "GATE_PASSED" if all_criteria_met and corrupted_all_caught else "GATE_FAILED",
        "scenarios": scenario_results,
        "corrupted_validation_tests": corrupted_results,
    }

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2)

    print("\n" + "=" * 72)
    print("PHASE 0 GATE EVALUATION SUMMARY")
    print("=" * 72)
    print(f"Scenarios S1-S4 Solved <= 2.5s & Valid: {'PASS' if all(scenario_results[s]['gate_passed'] for s in ['S1', 'S2', 'S3', 'S4']) else 'FAIL'}")
    print(f"Scenario S4 Max Payload Rejection & BOX-L Selection: {'PASS' if scenario_results['S4']['gate_passed'] else 'FAIL'}")
    print(f"Scenario S5 Clean Multi-Carton Split: {'PASS' if scenario_results['S5']['gate_passed'] else 'FAIL'}")
    print(f"Validator Detection Rate on Corrupted Inputs (100%): {'PASS' if corrupted_all_caught else 'FAIL'}")
    print(f"JSON Benchmark Report Saved: {report_file}")

    if all_criteria_met and corrupted_all_caught:
        print("\n>> FINAL VERDICT: GATE PASSED (GO). Ready for Milestone M1 Architecture Lock.")
    else:
        print("\n>> FINAL VERDICT: GATE FAILED. Activate Fallback 3A (Extreme-Point Heuristic Baseline).")


if __name__ == "__main__":
    run_phase0_solver_benchmark()
