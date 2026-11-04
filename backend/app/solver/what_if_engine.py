"""What-If Multi-Scenario Solver Engine (BE-2).

Evaluates user-selected packaging boxes against 4 classification tiers:
1. GREEN (100% Fit): Order packs cleanly within nominal dimensions.
2. YELLOW (Elastic Lid Compression):
   Order exceeds nominal height by Delta H <= min(floor(0.10 * H), 25 mm).
   Allowed ONLY if all overflowing items are resilient/soft (soft_fabric, rigid_box)
   and not fragile.
3. RED (Eject Candidates to Fit Remainder):
   Order exceeds elastic bounds or top items are fragile.
   Runs subset heuristic to pack primary subset and eject remainder.
4. BEST_FIT (Optimal Volume Benchmark):
   Determines the optimal catalog carton benchmark.
"""

from typing import Dict, List, Optional, Tuple

from backend.app.schemas.contracts import (
    CartonSpec,
    Dimensions3D,
    PackableItem,
    PackingPlan,
    PackingScenarioCard,
    PlacedItem,
    SolverConfig,
)
from backend.app.solver.carton_catalog import STANDARD_CARTONS, get_carton_volume_mm3
from backend.app.solver.cost_evaluator import compute_packing_metrics
from backend.app.solver.geometry_validator import validate_packing_solution
from backend.app.solver.heuristic_ep import (
    pack_carton_heuristic_ep,
    pack_carton_subset_heuristic_ep,
)


def _format_material_label(material_type: str) -> str:
    """Map canonical material type code to clear English label."""
    mapping = {
        "soft_fabric": "soft fabric / apparel",
        "rigid_box": "standard cardboard box",
        "glass_ceramic": "fragile glass / ceramic",
        "metal_wood": "solid metal / wood",
        "other": "general household item",
    }
    return mapping.get(material_type, "general package")


def format_scenario_advice(card: PackingScenarioCard, items: List[PackableItem]) -> Tuple[str, str]:
    """Generate clear, professional English packaging advice for a scenario card."""
    item_dict = {it.item_id: it for it in items}
    total_items = len(items)

    if card.badge_status == "GREEN":
        title = "Perfect Fit"
        explanation = (
            f"All {total_items} items fit comfortably inside {card.carton.display_name} "
            f"with {round(card.volume_utilization_pct)}% volume efficiency. Standard top-flap tape sealing recommended."
        )
        return title, explanation

    elif card.badge_status == "YELLOW":
        title = f"Slight Lid Bulge (+{card.overflow_height_mm} mm) - Packable"
        explanation = (
            f"Order height exceeds box depth by {card.overflow_height_mm} mm. "
            f"Since top items are soft and resilient, you can apply gentle lid pressure "
            f"and seal with H-pattern tape without needing a larger box."
        )
        return title, explanation

    elif card.badge_status == "RED":
        packed_count = total_items - len(card.ejected_item_ids)
        ejected_names = [
            item_dict[iid].display_name
            for iid in card.ejected_item_ids
            if iid in item_dict
        ]
        ejected_str = ", ".join(ejected_names[:3])
        if len(ejected_names) > 3:
            ejected_str += f" and {len(ejected_names) - 3} other item(s)"

        title = "Split Shipment Recommended"
        explanation = (
            f"This box holds {packed_count}/{total_items} items ({round(card.volume_utilization_pct)}% capacity). "
            f"We recommend packing the remaining {len(card.ejected_item_ids)} item(s) ({ejected_str}) into a separate mailer or second box."
        )
        return title, explanation

    else:  # BEST_FIT
        title = f"Recommended: {card.carton.display_name}"
        explanation = (
            f"Optimal standard packaging size with {round(card.volume_utilization_pct)}% space efficiency. "
            f"Fits 100% of order items safely according to shipping standards."
        )
        return title, explanation


def check_elastic_compression(
    carton: CartonSpec,
    items: List[PackableItem],
    min_support_ratio: float = 0.60,
) -> Tuple[bool, int, Optional[PackableItem], Optional[List[PlacedItem]], Optional[PackingPlan]]:
    """Check if items can fit with elastic lid compression on top.

    Elastic allowance: Delta H_max = min(int(carton_h * 0.10), 25) mm.
    Requires Delta H_max >= 5 mm.
    """
    carton_h = carton.internal_dimensions_mm.height_mm
    delta_h_max = min(int(carton_h * 0.10), 25)
    if delta_h_max < 5:
        return False, 0, None, None, None

    elastic_carton = CartonSpec(
        carton_id=f"{carton.carton_id}_ELASTIC",
        display_name=f"{carton.display_name} (Elastic)",
        internal_dimensions_mm=Dimensions3D(
            length_mm=carton.internal_dimensions_mm.length_mm,
            width_mm=carton.internal_dimensions_mm.width_mm,
            height_mm=carton_h + delta_h_max,
        ),
        tare_weight_g=carton.tare_weight_g,
        max_payload_g=carton.max_payload_g,
        box_cost_usd=carton.box_cost_usd,
    )

    success, placements = pack_carton_heuristic_ep(
        elastic_carton, items, min_support_ratio=min_support_ratio
    )
    if not success or not placements:
        return False, 0, None, None, None

    # Validate against elastic carton
    val_report = validate_packing_solution(
        elastic_carton, items, placements, min_support_ratio=min_support_ratio
    )
    if not val_report.is_valid:
        return False, 0, None, None, None

    item_dict = {it.item_id: it for it in items}

    # Find overflowing items: z + dz > carton_h
    overflowing_items: List[Tuple[PlacedItem, PackableItem, int]] = []
    for p in placements:
        top_z = p.position_mm.z + p.placed_dimensions_mm.dz
        if top_z > carton_h:
            it = item_dict.get(p.item_id)
            if it is not None:
                overflowing_items.append((p, it, top_z - carton_h))

    if not overflowing_items:
        # Actually fit nominally without overflow
        return False, 0, None, None, None

    max_overflow = max(overflow for _, _, overflow in overflowing_items)
    if max_overflow > delta_h_max:
        return False, 0, None, None, None

    # Safety check on all overflowing items:
    # Glass/ceramic or high fragility items CANNOT be compressed
    for _, it, _ in overflowing_items:
        if it.fragility_class == "high" or it.material_type == "glass_ceramic":
            return False, 0, None, None, None
        if not it.stackable:
            return False, 0, None, None, None

    # Top item with highest overflow
    top_p, top_it, _ = max(overflowing_items, key=lambda x: x[2])

    metrics = compute_packing_metrics(elastic_carton, items, placements)
    plan = PackingPlan(
        plan_index=1,
        carton=carton,
        metrics=metrics,
        placements=placements,
        validation=val_report,
    )

    return True, max_overflow, top_it, placements, plan


def solve_red_subset(
    carton: CartonSpec,
    items: List[PackableItem],
    min_support_ratio: float = 0.60,
) -> Tuple[List[str], Optional[PackingPlan], float]:
    """Pack as many items as possible into the carton, returning ejected item IDs."""
    all_fit, placements, unpacked = pack_carton_subset_heuristic_ep(
        carton, items, min_support_ratio=min_support_ratio
    )

    item_dict = {it.item_id: it for it in items}
    packed_ids = {p.item_id for p in placements}
    packed_items = [item_dict[pid] for pid in packed_ids if pid in item_dict]
    ejected_ids = [it.item_id for it in items if it.item_id not in packed_ids]

    if not placements or not packed_items:
        return [it.item_id for it in items], None, 0.0

    val_report = validate_packing_solution(
        carton, packed_items, placements, min_support_ratio=min_support_ratio
    )
    metrics = compute_packing_metrics(carton, packed_items, placements)
    plan = PackingPlan(
        plan_index=1,
        carton=carton,
        metrics=metrics,
        placements=placements,
        validation=val_report,
    )
    return ejected_ids, plan, metrics.volume_utilization_pct


def find_best_fit_catalog_carton(
    items: List[PackableItem],
    min_support_ratio: float = 0.60,
) -> Optional[Tuple[CartonSpec, PackingPlan]]:
    """Find the smallest standard catalog carton that packs all items."""
    total_vol = sum(
        it.dimensions_mm.length_mm * it.dimensions_mm.width_mm * it.dimensions_mm.height_mm
        for it in items
    )
    candidates = [c for c in STANDARD_CARTONS if get_carton_volume_mm3(c) >= total_vol]
    candidates.sort(key=get_carton_volume_mm3)

    for carton in candidates:
        success, placements = pack_carton_heuristic_ep(
            carton, items, min_support_ratio=min_support_ratio
        )
        if success and placements:
            val = validate_packing_solution(
                carton, items, placements, min_support_ratio=min_support_ratio
            )
            if val.is_valid:
                metrics = compute_packing_metrics(carton, items, placements)
                plan = PackingPlan(
                    plan_index=1,
                    carton=carton,
                    metrics=metrics,
                    placements=placements,
                    validation=val,
                )
                return carton, plan
    return None


def evaluate_what_if_scenarios(
    items: List[PackableItem],
    user_boxes: List[CartonSpec],
    solver_config: SolverConfig,
) -> List[PackingScenarioCard]:
    """Evaluate user-selected boxes against GREEN, YELLOW, RED tiers and attach BEST_FIT benchmark."""
    scenarios: List[PackingScenarioCard] = []
    min_support_ratio = solver_config.min_support_ratio

    # 1. Evaluate each user-selected box
    for idx, u_box in enumerate(user_boxes):
        scenario_id = f"scenario_user_box_{idx + 1}"

        # Check nominal fit (GREEN)
        nom_success, nom_placements = pack_carton_heuristic_ep(
            u_box, items, min_support_ratio=min_support_ratio
        )
        if nom_success and nom_placements:
            val = validate_packing_solution(
                u_box, items, nom_placements, min_support_ratio=min_support_ratio
            )
            if val.is_valid:
                metrics = compute_packing_metrics(u_box, items, nom_placements)
                plan = PackingPlan(
                    plan_index=1,
                    carton=u_box,
                    metrics=metrics,
                    placements=nom_placements,
                    validation=val,
                )
                card = PackingScenarioCard(
                    scenario_id=scenario_id,
                    title=f"{u_box.display_name} (Perfect Fit)",
                    badge_status="GREEN",
                    carton=u_box,
                    is_user_box=True,
                    is_selected_default=False,
                    volume_utilization_pct=metrics.volume_utilization_pct,
                    feasible=True,
                    overflow_height_mm=0,
                    ejected_item_ids=[],
                    plan=plan,
                )
                title, explanation = format_scenario_advice(card, items)
                card.advisor_title = title
                card.advisor_explanation = explanation
                scenarios.append(card)
                continue

        # Check elastic compression (YELLOW)
        el_ok, overflow_h, top_it, el_placements, el_plan = check_elastic_compression(
            u_box, items, min_support_ratio=min_support_ratio
        )
        if el_ok and el_plan is not None:
            card = PackingScenarioCard(
                scenario_id=scenario_id,
                title=f"{u_box.display_name} (Slight Bulge +{overflow_h}mm)",
                badge_status="YELLOW",
                carton=u_box,
                is_user_box=True,
                is_selected_default=False,
                volume_utilization_pct=el_plan.metrics.volume_utilization_pct,
                feasible=True,
                overflow_height_mm=overflow_h,
                ejected_item_ids=[],
                plan=el_plan,
            )
            title, explanation = format_scenario_advice(card, items)
            card.advisor_title = title
            card.advisor_explanation = explanation
            scenarios.append(card)
            continue

        # Otherwise RED
        ejected_ids, red_plan, util_pct = solve_red_subset(
            u_box, items, min_support_ratio=min_support_ratio
        )
        card = PackingScenarioCard(
            scenario_id=scenario_id,
            title=f"{u_box.display_name} (Split Shipment Needed)",
            badge_status="RED",
            carton=u_box,
            is_user_box=True,
            is_selected_default=False,
            volume_utilization_pct=util_pct,
            feasible=False,
            overflow_height_mm=0,
            ejected_item_ids=ejected_ids,
            plan=red_plan,
        )
        title, explanation = format_scenario_advice(card, items)
        card.advisor_title = title
        card.advisor_explanation = explanation
        scenarios.append(card)

    # 2. Add BEST_FIT catalog benchmark
    best_catalog = find_best_fit_catalog_carton(items, min_support_ratio=min_support_ratio)
    if best_catalog is not None:
        c_box, c_plan = best_catalog
        bf_card = PackingScenarioCard(
            scenario_id="scenario_best_fit",
            title=f"Recommended: {c_box.display_name}",
            badge_status="BEST_FIT",
            carton=c_box,
            is_user_box=False,
            is_selected_default=False,
            volume_utilization_pct=c_plan.metrics.volume_utilization_pct,
            feasible=True,
            overflow_height_mm=0,
            ejected_item_ids=[],
            plan=c_plan,
        )
        title, explanation = format_scenario_advice(bf_card, items)
        bf_card.advisor_title = title
        bf_card.advisor_explanation = explanation
        scenarios.append(bf_card)

    # 3. Mark default selection
    green_cards = [c for c in scenarios if c.badge_status == "GREEN"]
    yellow_cards = [c for c in scenarios if c.badge_status == "YELLOW"]
    bf_cards = [c for c in scenarios if c.badge_status == "BEST_FIT"]

    if green_cards:
        best_green = max(green_cards, key=lambda c: c.volume_utilization_pct)
        best_green.is_selected_default = True
    elif yellow_cards:
        yellow_cards[0].is_selected_default = True
    elif bf_cards:
        bf_cards[0].is_selected_default = True
    elif scenarios:
        scenarios[0].is_selected_default = True

    return scenarios
