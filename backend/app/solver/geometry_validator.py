"""Independent Deterministic Geometry and Physical Constraint Validator.

Validates any 3D packing solution against:
1. Boundary containment within internal carton dimensions
2. Zero pairwise Axis-Aligned Bounding Box (AABB) intersection
3. Permitted rotation codes (checking keep_upright constraint)
4. Vertical base support ratio (>= min_support_ratio, default 60%)
5. Fragility and stacking rules (no heavy or unstackable item violations)
6. Carton maximum payload limit
"""

from typing import Dict, List, Tuple
from backend.app.schemas.contracts import (
    CartonSpec,
    PackableItem,
    PlacedItem,
    RotationCode,
    UPRIGHT_ROTATION_CODES,
    ValidationReport,
)


def _intervals_overlap(a_min: int, a_max: int, b_min: int, b_max: int) -> bool:
    """Return True if two open intervals (a_min, a_max) and (b_min, b_max) strictly overlap."""
    return max(a_min, b_min) < min(a_max, b_max)


def _compute_xy_overlap_area(p1: PlacedItem, p2: PlacedItem) -> int:
    """Compute overlapping horizontal contact area in mm^2 between two boxes."""
    x_overlap = max(0, min(p1.position_mm.x + p1.placed_dimensions_mm.dx, p2.position_mm.x + p2.placed_dimensions_mm.dx) -
                       max(p1.position_mm.x, p2.position_mm.x))
    y_overlap = max(0, min(p1.position_mm.y + p1.placed_dimensions_mm.dy, p2.position_mm.y + p2.placed_dimensions_mm.dy) -
                       max(p1.position_mm.y, p2.position_mm.y))
    return x_overlap * y_overlap


def validate_packing_solution(
    carton: CartonSpec,
    items: List[PackableItem],
    placements: List[PlacedItem],
    min_support_ratio: float = 0.60,
) -> ValidationReport:
    """Perform independent deterministic verification of a 3D packing plan."""
    violations: List[str] = []
    warnings: List[str] = []

    item_dict: Dict[str, PackableItem] = {it.item_id: it for it in items}
    carton_dims = carton.internal_dimensions_mm

    boundary_ok = True
    overlap_ok = True
    rotation_ok = True
    support_ok = True
    fragility_ok = True
    weight_ok = True

    # 1. Boundary Containment Check
    for p in placements:
        x_max = p.position_mm.x + p.placed_dimensions_mm.dx
        y_max = p.position_mm.y + p.placed_dimensions_mm.dy
        z_max = p.position_mm.z + p.placed_dimensions_mm.dz

        if (p.position_mm.x < 0 or x_max > carton_dims.length_mm or
            p.position_mm.y < 0 or y_max > carton_dims.width_mm or
            p.position_mm.z < 0 or z_max > carton_dims.height_mm):
            boundary_ok = False
            violations.append(
                f"Item '{p.item_id}' exceeds carton boundaries: "
                f"span=[{p.position_mm.x}..{x_max}, {p.position_mm.y}..{y_max}, {p.position_mm.z}..{z_max}] "
                f"vs carton=[{carton_dims.length_mm}, {carton_dims.width_mm}, {carton_dims.height_mm}]."
            )

    # 2. Pairwise AABB Overlap Check
    n = len(placements)
    for i in range(n):
        p1 = placements[i]
        x1_min, x1_max = p1.position_mm.x, p1.position_mm.x + p1.placed_dimensions_mm.dx
        y1_min, y1_max = p1.position_mm.y, p1.position_mm.y + p1.placed_dimensions_mm.dy
        z1_min, z1_max = p1.position_mm.z, p1.position_mm.z + p1.placed_dimensions_mm.dz

        for j in range(i + 1, n):
            p2 = placements[j]
            x2_min, x2_max = p2.position_mm.x, p2.position_mm.x + p2.placed_dimensions_mm.dx
            y2_min, y2_max = p2.position_mm.y, p2.position_mm.y + p2.placed_dimensions_mm.dy
            z2_min, z2_max = p2.position_mm.z, p2.position_mm.z + p2.placed_dimensions_mm.dz

            if (_intervals_overlap(x1_min, x1_max, x2_min, x2_max) and
                _intervals_overlap(y1_min, y1_max, y2_min, y2_max) and
                _intervals_overlap(z1_min, z1_max, z2_min, z2_max)):
                overlap_ok = False
                violations.append(
                    f"Pairwise collision between item '{p1.item_id}' and item '{p2.item_id}'."
                )

    # 3. Allowed Rotation & Upright Check
    for p in placements:
        req_item = item_dict.get(p.item_id)
        if req_item:
            if p.rotation_code not in req_item.allowed_rotations:
                rotation_ok = False
                violations.append(
                    f"Item '{p.item_id}' rotated with unpermitted code '{p.rotation_code}'."
                )
            if req_item.keep_upright and p.rotation_code not in UPRIGHT_ROTATION_CODES:
                rotation_ok = False
                violations.append(
                    f"Item '{p.item_id}' violates keep_upright=True constraint with rotation '{p.rotation_code}'."
                )

    # 4. Vertical Support Ratio Check
    for p in placements:
        if p.position_mm.z == 0:
            # Rests directly on carton floor
            continue

        base_area = p.placed_dimensions_mm.dx * p.placed_dimensions_mm.dy
        if base_area <= 0:
            continue

        supported_area = 0
        supporting_items = []
        for other in placements:
            if other.item_id == p.item_id:
                continue
            other_z_max = other.position_mm.z + other.placed_dimensions_mm.dz
            if other_z_max == p.position_mm.z:
                overlap = _compute_xy_overlap_area(p, other)
                if overlap > 0:
                    supported_area += overlap
                    supporting_items.append(other.item_id)

        support_ratio = min(1.0, supported_area / base_area)
        if support_ratio < min_support_ratio:
            support_ok = False
            violations.append(
                f"Item '{p.item_id}' at z={p.position_mm.z} has insufficient vertical support: "
                f"{round(support_ratio * 100, 1)}% < {round(min_support_ratio * 100, 1)}%."
            )

    # 5. Fragility and Top-Load Check
    for p_top in placements:
        top_item = item_dict.get(p_top.item_id)
        for p_bot in placements:
            if p_top.item_id == p_bot.item_id:
                continue
            bot_item = item_dict.get(p_bot.item_id)
            if not bot_item:
                continue

            bot_z_max = p_bot.position_mm.z + p_bot.placed_dimensions_mm.dz
            if bot_z_max == p_top.position_mm.z:
                overlap = _compute_xy_overlap_area(p_top, p_bot)
                if overlap > 0:
                    if not bot_item.stackable:
                        fragility_ok = False
                        violations.append(
                            f"Item '{p_top.item_id}' placed on top of non-stackable item '{p_bot.item_id}'."
                        )
                    if bot_item.fragility_class == "high" and (top_item and top_item.fragility_class != "high"):
                        fragility_ok = False
                        violations.append(
                            f"Non-fragile item '{p_top.item_id}' stacked atop highly fragile item '{p_bot.item_id}'."
                        )

    # 6. Max Payload Weight Check
    total_payload_g = 0
    for p in placements:
        item_obj = item_dict.get(p.item_id)
        if item_obj:
            if item_obj.weight_g is not None and item_obj.weight_g > 0:
                total_payload_g += item_obj.weight_g
            else:
                vol_cm3 = (item_obj.dimensions_mm.length_mm * item_obj.dimensions_mm.width_mm * item_obj.dimensions_mm.height_mm) / 1000.0
                total_payload_g += max(1, int(round(vol_cm3 * 0.25)))

    if total_payload_g > carton.max_payload_g:
        weight_ok = False
        violations.append(
            f"Total payload ({total_payload_g}g) exceeds carton maximum payload ({carton.max_payload_g}g)."
        )

    is_valid = boundary_ok and overlap_ok and rotation_ok and support_ok and fragility_ok and weight_ok

    return ValidationReport(
        is_valid=is_valid,
        boundary_check_passed=boundary_ok,
        overlap_check_passed=overlap_ok,
        rotation_check_passed=rotation_ok,
        support_check_passed=support_ok,
        fragility_check_passed=fragility_ok,
        weight_check_passed=weight_ok,
        violations=violations,
        warnings=warnings,
    )
