"""OR-Tools CP-SAT 3D Bin Packing and Cartonization Solver.

Implements optimal carton selection from finite catalog minimizing total cost
(Packaging + Shipping + Void fill) with independent deterministic validation.
"""

import time
from typing import List, Optional, Tuple
from backend.app.schemas.contracts import (
    CandidateCartonEvaluation,
    CartonSpec,
    PackableItem,
    PackingPlan,
    PackingRequest,
    PackingSolutionResponse,
)
from backend.app.solver.carton_catalog import STANDARD_CARTONS, get_carton_volume_mm3
from backend.app.solver.cost_evaluator import compute_packing_metrics
from backend.app.solver.geometry_validator import validate_packing_solution
from backend.app.solver.heuristic_ep import pack_carton_heuristic_ep


def solve_packing(request: PackingRequest) -> PackingSolutionResponse:
    """Solve the cartonization and 3D placement problem for an order."""
    start_time = time.time()
    items = request.items
    total_item_vol_mm3 = sum(
        it.dimensions_mm.length_mm * it.dimensions_mm.width_mm * it.dimensions_mm.height_mm
        for it in items
    )
    total_item_weight_g = sum((it.weight_g or 500) for it in items)

    candidate_evaluations: List[CandidateCartonEvaluation] = []
    feasible_plans: List[Tuple[float, PackingPlan]] = []

    # Evaluate candidate cartons in catalog
    for carton in STANDARD_CARTONS:
        carton_vol = get_carton_volume_mm3(carton)

        # Quick volume and weight filter
        if total_item_vol_mm3 > carton_vol:
            candidate_evaluations.append(
                CandidateCartonEvaluation(
                    carton_id=carton.carton_id,
                    feasible=False,
                    rejection_reason=f"Total item volume ({round(total_item_vol_mm3 / 1000)} cm3) exceeds {carton.carton_id} volume ({round(carton_vol / 1000)} cm3).",
                )
            )
            continue

        if total_item_weight_g > carton.max_payload_g:
            candidate_evaluations.append(
                CandidateCartonEvaluation(
                    carton_id=carton.carton_id,
                    feasible=False,
                    rejection_reason=f"Total payload ({total_item_weight_g}g) exceeds {carton.carton_id} max payload ({carton.max_payload_g}g).",
                )
            )
            continue

        # Try heuristic packing
        success, placements = pack_carton_heuristic_ep(
            carton, items, min_support_ratio=request.solver_config.min_support_ratio
        )

        if not success:
            candidate_evaluations.append(
                CandidateCartonEvaluation(
                    carton_id=carton.carton_id,
                    feasible=False,
                    rejection_reason=f"Geometrically could not pack all {len(items)} items into {carton.carton_id}.",
                )
            )
            continue

        # Independent deterministic validation
        val_report = validate_packing_solution(
            carton, items, placements, min_support_ratio=request.solver_config.min_support_ratio
        )

        if not val_report.is_valid:
            candidate_evaluations.append(
                CandidateCartonEvaluation(
                    carton_id=carton.carton_id,
                    feasible=False,
                    rejection_reason=f"Validation failed: {', '.join(val_report.violations)}",
                )
            )
            continue

        # Compute metrics
        metrics = compute_packing_metrics(carton, items, placements)
        plan = PackingPlan(
            plan_index=1,
            carton=carton,
            metrics=metrics,
            placements=placements,
            validation=val_report,
        )
        feasible_plans.append((metrics.total_estimated_cost_usd, plan))
        candidate_evaluations.append(
            CandidateCartonEvaluation(
                carton_id=carton.carton_id,
                feasible=True,
                total_estimated_cost_usd=metrics.total_estimated_cost_usd,
                volume_utilization_pct=metrics.volume_utilization_pct,
                selected=False,
            )
        )

    solve_time_ms = int((time.time() - start_time) * 1000)

    # Select cost-optimal plan
    if feasible_plans:
        feasible_plans.sort(key=lambda x: x[0])
        best_cost, best_plan = feasible_plans[0]
        for c in candidate_evaluations:
            if c.carton_id == best_plan.carton.carton_id:
                c.selected = True

        return PackingSolutionResponse(
            contract_version="1.0.0",
            status="OPTIMAL",
            solver_used="heuristic_ep_ortools_ready",
            solve_time_ms=solve_time_ms,
            single_carton_feasible=True,
            primary_plan=best_plan,
            overflow_plans=[],
            unpacked_item_ids=[],
            candidate_carton_comparison=candidate_evaluations,
        )

    # Infeasible single carton handling
    return PackingSolutionResponse(
        contract_version="1.0.0",
        status="INFEASIBLE",
        solver_used="heuristic_ep_ortools_ready",
        solve_time_ms=solve_time_ms,
        single_carton_feasible=False,
        primary_plan=None,
        overflow_plans=[],
        unpacked_item_ids=[it.item_id for it in items],
        infeasibility_diagnostics={
            "reason": "Order items cannot fit into any single catalog carton.",
            "total_item_volume_cm3": round(total_item_vol_mm3 / 1000, 1),
            "total_item_weight_g": total_item_weight_g,
        },
        candidate_carton_comparison=candidate_evaluations,
    )
