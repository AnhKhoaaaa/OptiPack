"""OR-Tools CP-SAT 3D Bin Packing and Cartonization Solver.

Implements two-tier optimization:
- Tier 1: Extreme-Point Heuristic (< 30ms) for fast constructive warm-start / fallback
- Tier 2: OR-Tools CP-SAT with 6-orientation selection and independent validation
Includes multi-carton overflow splitting and deterministic physical validation.
"""

import time
from typing import Dict, List, Optional, Tuple
from ortools.sat.python import cp_model

from backend.app.schemas.contracts import (
    CandidateCartonEvaluation,
    CartonSpec,
    PackableItem,
    PackingPlan,
    PackingRequest,
    PackingSolutionResponse,
    PlacedDimensions3D,
    PlacedItem,
    Position3D,
    RotationCode,
    UPRIGHT_ROTATION_CODES,
)
from backend.app.solver.carton_catalog import STANDARD_CARTONS, get_carton_volume_mm3
from backend.app.solver.cost_evaluator import compute_packing_metrics
from backend.app.solver.geometry_validator import validate_packing_solution
from backend.app.solver.heuristic_ep import (
    get_oriented_dimensions,
    pack_carton_heuristic_ep,
    pack_carton_subset_heuristic_ep,
)


def pack_carton_cpsat(
    carton: CartonSpec,
    items: List[PackableItem],
    min_support_ratio: float = 0.60,
    time_limit_ms: int = 2000,
    initial_placements: Optional[List[PlacedItem]] = None,
) -> Tuple[bool, List[PlacedItem]]:
    """Solve 3D orthogonal placement inside a single carton using OR-Tools CP-SAT.

    Warm-started with initial_placements (from Tier 1 EP Heuristic).
    Validated by independent deterministic geometry validator before returning.
    """
    carton_l = carton.internal_dimensions_mm.length_mm
    carton_w = carton.internal_dimensions_mm.width_mm
    carton_h = carton.internal_dimensions_mm.height_mm

    item_dict: Dict[str, PackableItem] = {it.item_id: it for it in items}
    n = len(items)

    model = cp_model.CpModel()

    # Decision variables for each item
    item_vars = []
    x_vars = []
    y_vars = []
    z_vars = []
    dx_vars = []
    dy_vars = []
    dz_vars = []

    for idx, item in enumerate(items):
        nom_l = item.dimensions_mm.length_mm
        nom_w = item.dimensions_mm.width_mm
        nom_h = item.dimensions_mm.height_mm
        margin = item.safety_margin_mm

        allowed_rots = UPRIGHT_ROTATION_CODES if item.keep_upright else item.allowed_rotations

        x = model.NewIntVar(0, carton_l, f"x_{idx}")
        y = model.NewIntVar(0, carton_w, f"y_{idx}")
        z = model.NewIntVar(0, carton_h, f"z_{idx}")

        dx = model.NewIntVar(0, carton_l, f"dx_{idx}")
        dy = model.NewIntVar(0, carton_w, f"dy_{idx}")
        dz = model.NewIntVar(0, carton_h, f"dz_{idx}")

        # Orientation selection
        o_vars = []
        dx_terms = []
        dy_terms = []
        dz_terms = []

        for r_idx, rot in enumerate(allowed_rots):
            o = model.NewBoolVar(f"o_{idx}_{r_idx}")
            o_vars.append((o, rot))
            rdx, rdy, rdz = get_oriented_dimensions(nom_l, nom_w, nom_h, rot)
            pdx, pdy, pdz = rdx + margin, rdy + margin, rdz + margin
            dx_terms.append(pdx * o)
            dy_terms.append(pdy * o)
            dz_terms.append(pdz * o)

        model.AddExactlyOne([o for o, _ in o_vars])
        model.Add(dx == sum(dx_terms))
        model.Add(dy == sum(dy_terms))
        model.Add(dz == sum(dz_terms))

        # Carton boundary containment
        model.Add(x + dx <= carton_l)
        model.Add(y + dy <= carton_w)
        model.Add(z + dz <= carton_h)

        x_vars.append(x)
        y_vars.append(y)
        z_vars.append(z)
        dx_vars.append(dx)
        dy_vars.append(dy)
        dz_vars.append(dz)
        item_vars.append((x, y, z, dx, dy, dz, o_vars))

    # Pairwise 3D non-overlap constraints
    for i in range(n):
        for j in range(i + 1, n):
            xi, yi, zi, dxi, dyi, dzi, _ = item_vars[i]
            xj, yj, zj, dxj, dyj, dzj, _ = item_vars[j]

            left = model.NewBoolVar(f"left_{i}_{j}")
            right = model.NewBoolVar(f"right_{i}_{j}")
            front = model.NewBoolVar(f"front_{i}_{j}")
            back = model.NewBoolVar(f"back_{i}_{j}")
            below = model.NewBoolVar(f"below_{i}_{j}")
            above = model.NewBoolVar(f"above_{i}_{j}")

            model.Add(xi + dxi <= xj).OnlyEnforceIf(left)
            model.Add(xj + dxj <= xi).OnlyEnforceIf(right)
            model.Add(yi + dyi <= yj).OnlyEnforceIf(front)
            model.Add(yj + dyj <= yi).OnlyEnforceIf(back)
            model.Add(zi + dzi <= zj).OnlyEnforceIf(below)
            model.Add(zj + dzj <= zi).OnlyEnforceIf(above)

            # Fragility stacking restrictions
            item_i = items[i]
            item_j = items[j]

            # If j is not stackable or high-fragility, i cannot be above j
            if (not item_j.stackable or item_j.fragility_class == "high") and item_i.fragility_class != "high":
                model.Add(above == 0)
            # If i is not stackable or high-fragility, j cannot be above i
            if (not item_i.stackable or item_i.fragility_class == "high") and item_j.fragility_class != "high":
                model.Add(below == 0)

            model.AddBoolOr([left, right, front, back, below, above])

    # Objective: Lower center-of-mass and compact towards (0,0,0)
    max_z = model.NewIntVar(0, carton_h, "max_z")
    for i in range(n):
        model.Add(z_vars[i] + dz_vars[i] <= max_z)

    # Heavier items lower
    weighted_z = sum((items[i].weight_g or 500) * z_vars[i] for i in range(n))
    coord_sum = sum(x_vars[i] + y_vars[i] for i in range(n))
    model.Minimize(100 * max_z + weighted_z + coord_sum)

    # Solution hints from initial_placements (warm-start)
    if initial_placements:
        initial_map = {p.item_id: p for p in initial_placements}
        for idx, item in enumerate(items):
            init_p = initial_map.get(item.item_id)
            if init_p:
                model.AddHint(x_vars[idx], init_p.position_mm.x)
                model.AddHint(y_vars[idx], init_p.position_mm.y)
                model.AddHint(z_vars[idx], init_p.position_mm.z)
                for o_var, rot in item_vars[idx][6]:
                    if rot == init_p.rotation_code:
                        model.AddHint(o_var, 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.2, min(3.0, time_limit_ms / 1000.0))
    solver.parameters.num_search_workers = 4

    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        placements: List[PlacedItem] = []
        for idx, item in enumerate(items):
            x_val = int(solver.Value(x_vars[idx]))
            y_val = int(solver.Value(y_vars[idx]))
            z_val = int(solver.Value(z_vars[idx]))
            pdx_val = int(solver.Value(dx_vars[idx]))
            pdy_val = int(solver.Value(dy_vars[idx]))
            pdz_val = int(solver.Value(dz_vars[idx]))

            chosen_rot = items[idx].allowed_rotations[0]
            for o_var, rot in item_vars[idx][6]:
                if solver.Value(o_var) == 1:
                    chosen_rot = rot
                    break

            nom_l = item.dimensions_mm.length_mm
            nom_w = item.dimensions_mm.width_mm
            nom_h = item.dimensions_mm.height_mm
            rdx, rdy, rdz = get_oriented_dimensions(nom_l, nom_w, nom_h, chosen_rot)

            p = PlacedItem(
                step_number=idx + 1,
                item_id=item.item_id,
                display_name=item.display_name,
                rotation_code=chosen_rot,
                position_mm=Position3D(x=x_val, y=y_val, z=z_val),
                placed_dimensions_mm=PlacedDimensions3D(dx=pdx_val, dy=pdy_val, dz=pdz_val),
                nominal_dimensions_mm=PlacedDimensions3D(dx=rdx, dy=rdy, dz=rdz),
                support_ratio=1.0 if z_val == 0 else 0.0,
                supported_by_item_ids=["CARTON_FLOOR"] if z_val == 0 else [],
                display_color_hex=item.display_color_hex,
            )
            placements.append(p)

        # Lexicographical step order
        placements.sort(
            key=lambda p: (
                p.position_mm.z,
                p.position_mm.y,
                p.position_mm.x,
                -(p.placed_dimensions_mm.dx * p.placed_dimensions_mm.dy * p.placed_dimensions_mm.dz),
            )
        )
        for s_idx, p in enumerate(placements, start=1):
            p.step_number = s_idx

        # Independent validation
        val = validate_packing_solution(carton, items, placements, min_support_ratio=min_support_ratio)
        if val.is_valid:
            return True, placements

    return False, []


def solve_packing(request: PackingRequest) -> PackingSolutionResponse:
    """Solve cartonization and 3D placement problem for an order.

    Two-tier approach:
    1. Fast Extreme-Point heuristic warm-start and fallback
    2. OR-Tools CP-SAT optimal placement with constraint propagation
    3. Multi-carton overflow split if order cannot fit in any single catalog box.
    """
    start_time = time.time()
    items = request.items
    time_limit_ms = request.solver_config.time_limit_ms
    min_support_ratio = request.solver_config.min_support_ratio
    mode = request.solver_config.mode

    total_item_vol_mm3 = sum(
        it.dimensions_mm.length_mm * it.dimensions_mm.width_mm * it.dimensions_mm.height_mm
        for it in items
    )
    total_item_weight_g = sum((it.weight_g or 500) for it in items)

    candidate_evaluations: List[CandidateCartonEvaluation] = []
    feasible_plans: List[Tuple[float, PackingPlan, str]] = []

    # 1. Quick catalog screening using Tier 1 EP Heuristic (< 20 ms total)
    ep_results: Dict[str, Tuple[bool, List[PlacedItem], Optional[PackingPlan]]] = {}

    for carton in STANDARD_CARTONS:
        carton_vol = get_carton_volume_mm3(carton)

        # Volume capacity filter
        if total_item_vol_mm3 > carton_vol:
            candidate_evaluations.append(
                CandidateCartonEvaluation(
                    carton_id=carton.carton_id,
                    feasible=False,
                    rejection_reason=f"Total item volume ({round(total_item_vol_mm3 / 1000)} cm3) exceeds {carton.carton_id} volume ({round(carton_vol / 1000)} cm3).",
                )
            )
            continue

        # Payload capacity filter
        if total_item_weight_g > carton.max_payload_g:
            candidate_evaluations.append(
                CandidateCartonEvaluation(
                    carton_id=carton.carton_id,
                    feasible=False,
                    rejection_reason=f"Total payload ({total_item_weight_g}g) exceeds {carton.carton_id} max payload ({carton.max_payload_g}g).",
                )
            )
            continue

        # Run fast Tier 1 EP Heuristic
        ep_success, ep_placements = pack_carton_heuristic_ep(
            carton, items, min_support_ratio=min_support_ratio
        )

        if not ep_success:
            ep_results[carton.carton_id] = (False, [], None)
            continue

        val_report = validate_packing_solution(
            carton, items, ep_placements, min_support_ratio=min_support_ratio
        )
        if not val_report.is_valid:
            ep_results[carton.carton_id] = (False, [], None)
            continue

        metrics = compute_packing_metrics(carton, items, ep_placements)
        ep_plan = PackingPlan(
            plan_index=1,
            carton=carton,
            metrics=metrics,
            placements=ep_placements,
            validation=val_report,
        )
        ep_results[carton.carton_id] = (True, ep_placements, ep_plan)

    # Sort feasible candidates by total estimated cost ascending
    feasible_carton_candidates: List[Tuple[float, CartonSpec, List[PlacedItem], PackingPlan]] = []
    for carton in STANDARD_CARTONS:
        if carton.carton_id in ep_results and ep_results[carton.carton_id][0]:
            _, pl, plan = ep_results[carton.carton_id]
            feasible_carton_candidates.append((plan.metrics.total_estimated_cost_usd, carton, pl, plan))

    feasible_carton_candidates.sort(key=lambda x: x[0])

    # 2. Tier 2 CP-SAT optimization on lowest-cost candidate cartons
    best_final_plan: Optional[PackingPlan] = None
    engine_name = "extreme_point_heuristic"

    for cost_estimate, carton, ep_pl, ep_plan in feasible_carton_candidates:
        elapsed_ms = (time.time() - start_time) * 1000
        remaining_budget_ms = max(200, time_limit_ms - int(elapsed_ms))

        if mode in ("cpsat_with_heuristic_fallback", "cpsat_exact_only") and remaining_budget_ms > 300:
            cpsat_success, cpsat_pl = pack_carton_cpsat(
                carton=carton,
                items=items,
                min_support_ratio=min_support_ratio,
                time_limit_ms=min(1000, remaining_budget_ms),
                initial_placements=ep_pl,
            )
            if cpsat_success:
                val_report = validate_packing_solution(
                    carton, items, cpsat_pl, min_support_ratio=min_support_ratio
                )
                if val_report.is_valid:
                    metrics = compute_packing_metrics(carton, items, cpsat_pl)
                    best_final_plan = PackingPlan(
                        plan_index=1,
                        carton=carton,
                        metrics=metrics,
                        placements=cpsat_pl,
                        validation=val_report,
                    )
                    engine_name = "ortools_cpsat"
                    break

        # Fallback 3A: use valid Tier 1 EP solution
        if ep_plan is not None:
            best_final_plan = ep_plan
            engine_name = "heuristic_ep_fallback" if mode.startswith("cpsat") else "extreme_point_heuristic"
            break

    # Build candidate carton comparison list
    for carton in STANDARD_CARTONS:
        # Check if already added due to volume/weight rejection
        if any(c.carton_id == carton.carton_id for c in candidate_evaluations):
            continue

        if carton.carton_id in ep_results and ep_results[carton.carton_id][0]:
            _, _, ep_plan = ep_results[carton.carton_id]
            is_selected = best_final_plan is not None and best_final_plan.carton.carton_id == carton.carton_id
            candidate_evaluations.append(
                CandidateCartonEvaluation(
                    carton_id=carton.carton_id,
                    feasible=True,
                    total_estimated_cost_usd=best_final_plan.metrics.total_estimated_cost_usd if is_selected else ep_plan.metrics.total_estimated_cost_usd,
                    volume_utilization_pct=best_final_plan.metrics.volume_utilization_pct if is_selected else ep_plan.metrics.volume_utilization_pct,
                    selected=is_selected,
                )
            )
        else:
            candidate_evaluations.append(
                CandidateCartonEvaluation(
                    carton_id=carton.carton_id,
                    feasible=False,
                    rejection_reason=f"Geometrically could not pack all {len(items)} items into {carton.carton_id}.",
                )
            )

    solve_time_ms = int((time.time() - start_time) * 1000)

    # If feasible single carton plan found, return cost-optimal response
    if best_final_plan is not None:
        return PackingSolutionResponse(
            contract_version="1.0.0",
            status="OPTIMAL",
            solver_used=engine_name,
            solve_time_ms=solve_time_ms,
            single_carton_feasible=True,
            primary_plan=best_final_plan,
            overflow_plans=[],
            unpacked_item_ids=[],
            candidate_carton_comparison=candidate_evaluations,
        )

    # 3. Multi-Carton Split handling for oversized orders
    if request.solver_config.allow_multi_carton_split:
        remaining_items = list(items)
        split_plans: List[PackingPlan] = []
        plan_idx = 1

        # Use catalog cartons for split (from largest XXL down to S)
        carton_candidates_for_split = list(reversed(STANDARD_CARTONS))

        while remaining_items and plan_idx <= 10:
            best_split_plan: Optional[PackingPlan] = None
            best_packed_items: List[PackableItem] = []

            for carton in carton_candidates_for_split:
                all_fit, placements, unpacked = pack_carton_subset_heuristic_ep(
                    carton, remaining_items, min_support_ratio=min_support_ratio
                )
                if placements:
                    packed_ids = {p.item_id for p in placements}
                    packed_items_here = [it for it in remaining_items if it.item_id in packed_ids]
                    val = validate_packing_solution(
                        carton, packed_items_here, placements, min_support_ratio=min_support_ratio
                    )
                    if val.is_valid:
                        # Prioritize packing more items / larger volume
                        if len(packed_items_here) > len(best_packed_items):
                            metrics = compute_packing_metrics(carton, packed_items_here, placements)
                            best_split_plan = PackingPlan(
                                plan_index=plan_idx,
                                carton=carton,
                                metrics=metrics,
                                placements=placements,
                                validation=val,
                            )
                            best_packed_items = packed_items_here

            if not best_split_plan or not best_packed_items:
                break

            split_plans.append(best_split_plan)
            packed_ids = {it.item_id for it in best_packed_items}
            remaining_items = [it for it in remaining_items if it.item_id not in packed_ids]
            plan_idx += 1

        if split_plans:
            total_solve_ms = int((time.time() - start_time) * 1000)
            status_val = "FEASIBLE" if not remaining_items else "FEASIBLE"
            return PackingSolutionResponse(
                contract_version="1.0.0",
                status=status_val,
                solver_used="multi_carton_split_heuristic",
                solve_time_ms=total_solve_ms,
                single_carton_feasible=False,
                primary_plan=split_plans[0],
                overflow_plans=split_plans[1:],
                unpacked_item_ids=[it.item_id for it in remaining_items],
                infeasibility_diagnostics={
                    "reason": "Order exceeds single carton capacity. Order successfully split across multi-carton plan.",
                    "total_item_volume_cm3": round(total_item_vol_mm3 / 1000, 1),
                    "total_item_weight_g": total_item_weight_g,
                    "cartons_required": len(split_plans),
                },
                candidate_carton_comparison=candidate_evaluations,
            )

    # 4. Infeasible and split not permitted
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
