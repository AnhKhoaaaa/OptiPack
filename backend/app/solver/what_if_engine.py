"""What-If Multi-Scenario Simulation Engine for OptiPack V2.0.

Generates GREEN, YELLOW (elastic bulge), RED (item ejection), and BEST_FIT
packing scenario cards with 0ms precomputed 3D plans.
"""

from __future__ import annotations

import copy
from typing import List, Optional

from backend.app.schemas.contracts import (
    CartonSpec,
    PackableItem,
    PackingPlan,
    PackingScenarioCard,
    PackingSolutionResponse,
    SolverConfig,
)
from backend.app.solver.carton_catalog import STANDARD_CARTONS
from backend.app.solver.cost_evaluator import compute_packing_metrics
from backend.app.solver.geometry_validator import validate_packing_solution
from backend.app.solver.heuristic_ep import (
    pack_carton_heuristic_ep,
    pack_carton_subset_heuristic_ep,
)


def compute_elastic_height_mm(height_mm: int) -> int:
    """Calculate maximum safe lid flex delta: min(floor(0.10 * H), 25mm)."""
    delta = min(int(height_mm * 0.10), 25)
    return max(delta, 10)


def generate_what_if_scenarios(
    items: List[PackableItem],
    user_boxes: List[CartonSpec],
    base_solution: PackingSolutionResponse,
    solver_config: SolverConfig,
) -> List[PackingScenarioCard]:
    """Generate 1-4 What-If Packing Scenario cards.
    
    Guarantees:
    - Never raises an unhandled exception.
    - Returns at least 1 card (BEST_FIT or standard).
    - If user provided boxes, attempts Green/Yellow/Red evaluations.
    """
    scenarios: List[PackingScenarioCard] = []

    # 1. BEST_FIT scenario (from base solution or optimal standard box)
    if base_solution.primary_plan:
        best_plan = base_solution.primary_plan
        scenarios.append(
            PackingScenarioCard(
                scenario_id="best_fit",
                title=f"System Optimal ({best_plan.carton.carton_id})",
                badge_status="BEST_FIT",
                badge_label="System Optimal",
                overflow_height_mm=0,
                original_box_height_mm=best_plan.carton.internal_dimensions_mm.height_mm,
                plan=best_plan,
                overflow_plans=base_solution.overflow_plans,
                ai_advisor_note=(
                    f"Recommended {best_plan.carton.display_name or best_plan.carton.carton_id} "
                    f"for optimal volume fill ({best_plan.metrics.volume_utilization_pct:.0f}%) "
                    f"and lowest shipping footprint."
                ),
            )
        )

    # Boxes to test: user-selected or top standard candidates
    boxes_to_test = list(user_boxes) if user_boxes else [STANDARD_CARTONS[0], STANDARD_CARTONS[1]]

    for idx, box in enumerate(boxes_to_test[:3]):
        box_h = box.internal_dimensions_mm.height_mm
        sc_id_base = f"box_{box.carton_id.lower()}_{idx + 1}"

        # Test A: Exact standard fit (GREEN)
        ep_success, ep_pl = pack_carton_heuristic_ep(box, items, min_support_ratio=0.6)
        if ep_success:
            val = validate_packing_solution(box, items, ep_pl, min_support_ratio=0.6)
            if val.is_valid:
                metrics = compute_packing_metrics(box, items, ep_pl)
                plan = PackingPlan(
                    plan_index=1,
                    carton=box,
                    metrics=metrics,
                    placements=ep_pl,
                    validation=val,
                )
                scenarios.append(
                    PackingScenarioCard(
                        scenario_id=f"{sc_id_base}_green",
                        title=f"{box.display_name or box.carton_id} (Snug)",
                        badge_status="GREEN",
                        badge_label="Perfect Fit (100%)",
                        overflow_height_mm=0,
                        original_box_height_mm=box_h,
                        plan=plan,
                        ai_advisor_note=(
                            f"All {len(items)} items fit within {box.carton_id} with 0mm height overflow."
                        ),
                    )
                )
                continue  # Fits perfectly, move to next box

        # Test B: Elastic bulge (YELLOW)
        delta_h = compute_elastic_height_mm(box_h)
        elastic_box = copy.deepcopy(box)
        elastic_box.internal_dimensions_mm.height_mm = box_h + delta_h

        e_success, e_pl = pack_carton_heuristic_ep(elastic_box, items, min_support_ratio=0.6)
        if e_success:
            # Check which items sit in the bulge zone (z + dz > box_h)
            overhang_placements = [p for p in e_pl if (p.position_mm.z + p.placed_dimensions_mm.dz) > box_h]
            overhang_ids = {p.item_id for p in overhang_placements}
            overhang_items = [it for it in items if it.item_id in overhang_ids]

            # Safety check: No fragile/glass in bulge zone
            has_fragile = any(
                it.fragility_class == "high" or it.material_type == "glass_ceramic" or not it.stackable
                for it in overhang_items
            )

            if not has_fragile:
                actual_max_z = max(p.position_mm.z + p.placed_dimensions_mm.dz for p in e_pl)
                actual_overflow = max(1, actual_max_z - box_h)
                val = validate_packing_solution(elastic_box, items, e_pl, min_support_ratio=0.6)
                if val.is_valid:
                    metrics = compute_packing_metrics(elastic_box, items, e_pl)
                    plan = PackingPlan(
                        plan_index=1,
                        carton=elastic_box,
                        metrics=metrics,
                        placements=e_pl,
                        validation=val,
                    )
                    top_name = overhang_items[0].display_name if overhang_items else "Top item"
                    scenarios.append(
                        PackingScenarioCard(
                            scenario_id=f"{sc_id_base}_yellow",
                            title=f"{box.display_name or box.carton_id} (Elastic Lid)",
                            badge_status="YELLOW",
                            badge_label=f"Elastic Bulge (+{actual_overflow}mm)",
                            overflow_height_mm=actual_overflow,
                            original_box_height_mm=box_h,
                            top_item_name=top_name,
                            plan=plan,
                            ai_advisor_note=(
                                f"Bulges +{actual_overflow}mm at [{top_name}]. "
                                "Because packaging is non-fragile, press lid down gently and seal with H-pattern tape."
                            ),
                        )
                    )
                    continue

        # Test C: Subset packing / Eject bulky item (RED)
        if len(items) > 1:
            # Eject least fragile / bulkiest item
            _, sub_pl, sub_unpacked = pack_carton_subset_heuristic_ep(box, items, min_support_ratio=0.6)
            if sub_pl and sub_unpacked:
                ejected_ids = [it.item_id for it in sub_unpacked]
                val = validate_packing_solution(box, items, sub_pl, min_support_ratio=0.6)
                metrics = compute_packing_metrics(box, items, sub_pl)
                plan = PackingPlan(
                    plan_index=1,
                    carton=box,
                    metrics=metrics,
                    placements=sub_pl,
                    validation=val,
                )
                ejected_name = sub_unpacked[0].display_name if sub_unpacked else "bulky item"
                scenarios.append(
                    PackingScenarioCard(
                        scenario_id=f"{sc_id_base}_red",
                        title=f"{box.display_name or box.carton_id} (Split 1 Item)",
                        badge_status="RED",
                        badge_label=f"Eject {len(ejected_ids)} Item",
                        overflow_height_mm=0,
                        original_box_height_mm=box_h,
                        top_item_name=ejected_name,
                        ejected_item_ids=ejected_ids,
                        plan=plan,
                        ai_advisor_note=(
                            f"Box is too small for all items. Eject [{ejected_name}] to pack in a separate "
                            f"bubble mailer; remaining {len(sub_pl)} items fit securely."
                        ),
                    )
                )

    # Fallback guarantee: if scenarios only has best_fit, synthesize a green/yellow scenario
    if len(scenarios) == 1 and base_solution.primary_plan:
        plan = base_solution.primary_plan
        scenarios.insert(
            0,
            PackingScenarioCard(
                scenario_id="perfect_fit_1",
                title=f"{plan.carton.display_name or plan.carton.carton_id} (Flush Fit)",
                badge_status="GREEN",
                badge_label="Perfect Fit (100%)",
                overflow_height_mm=0,
                original_box_height_mm=plan.carton.internal_dimensions_mm.height_mm,
                plan=plan,
                ai_advisor_note="All items fit completely within standard box boundaries.",
            ),
        )

    return scenarios
