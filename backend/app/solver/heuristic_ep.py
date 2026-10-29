"""Tier 1 Extreme-Point First-Fit Decreasing 3D Bin Packing Heuristic.

Provides a fast deterministic baseline (< 30ms) for carton packing and
constructive initial solutions with guaranteed vertical support and fragility constraints.
"""

from typing import Dict, List, Optional, Tuple
from backend.app.schemas.contracts import (
    CartonSpec,
    PackableItem,
    PlacedDimensions3D,
    PlacedItem,
    Position3D,
    RotationCode,
    UPRIGHT_ROTATION_CODES,
)


def get_oriented_dimensions(
    length: int, width: int, height: int, code: RotationCode
) -> Tuple[int, int, int]:
    """Return (dx, dy, dz) for a given canonical (L, W, H) and rotation code."""
    if code == RotationCode.LWH:
        return length, width, height
    elif code == RotationCode.WLH:
        return width, length, height
    elif code == RotationCode.LHW:
        return length, height, width
    elif code == RotationCode.HLW:
        return height, length, width
    elif code == RotationCode.WHL:
        return width, height, length
    elif code == RotationCode.HWL:
        return height, width, length
    return length, width, height


def get_stacking_tier(item: PackableItem) -> int:
    """Assign stacking tier priority tau_i:

    1: sturdy / low fragility & stackable
    2: medium fragility & stackable
    3: high fragility or non-stackable (must be placed near top / floor only)
    """
    if not item.stackable or item.fragility_class == "high":
        return 3
    elif item.fragility_class == "medium":
        return 2
    return 1


def pack_carton_heuristic_ep(
    carton: CartonSpec,
    items: List[PackableItem],
    min_support_ratio: float = 0.60,
) -> Tuple[bool, List[PlacedItem]]:
    """Pack all items into the carton using Extreme-Point placement heuristic.

    Returns:
        (success_bool, placements_list)
    """
    success, placements, unpacked = pack_carton_subset_heuristic_ep(
        carton=carton,
        items=items,
        min_support_ratio=min_support_ratio,
    )
    if not success or unpacked:
        return False, placements
    return True, placements


def pack_carton_subset_heuristic_ep(
    carton: CartonSpec,
    items: List[PackableItem],
    min_support_ratio: float = 0.60,
) -> Tuple[bool, List[PlacedItem], List[PackableItem]]:
    """Pack as many items as possible into the carton using EP heuristic.

    Returns:
        (all_packed_bool, placements_list, unpacked_items_list)
    """
    carton_l = carton.internal_dimensions_mm.length_mm
    carton_w = carton.internal_dimensions_mm.width_mm
    carton_h = carton.internal_dimensions_mm.height_mm

    item_dict: Dict[str, PackableItem] = {it.item_id: it for it in items}

    # Sort items: sturdy/heavy first (tau_i asc), footprint desc, volume desc
    sorted_items = sorted(
        items,
        key=lambda it: (
            get_stacking_tier(it),
            -(it.dimensions_mm.length_mm * it.dimensions_mm.width_mm),
            -(it.dimensions_mm.length_mm * it.dimensions_mm.width_mm * it.dimensions_mm.height_mm),
        ),
    )

    placements: List[PlacedItem] = []
    unpacked: List[PackableItem] = []
    extreme_points: List[Tuple[int, int, int]] = [(0, 0, 0)]
    current_payload_g = 0

    for item in sorted_items:
        item_weight = item.weight_g or 500
        if current_payload_g + item_weight > carton.max_payload_g:
            unpacked.append(item)
            continue

        placed = False
        allowed_rots = UPRIGHT_ROTATION_CODES if item.keep_upright else item.allowed_rotations

        # Evaluate candidate extreme points (sort primarily by Z asc, then Y, then X)
        extreme_points.sort(key=lambda pt: (pt[2], pt[1], pt[0]))

        best_candidate: Optional[Tuple[int, int, int, RotationCode, int, int, int, int, int, int, float, List[str]]] = None
        best_score = float("inf")

        for pt in extreme_points:
            px, py, pz = pt
            for rot in allowed_rots:
                nom_l = item.dimensions_mm.length_mm
                nom_w = item.dimensions_mm.width_mm
                nom_h = item.dimensions_mm.height_mm
                margin = item.safety_margin_mm

                dx, dy, dz = get_oriented_dimensions(nom_l, nom_w, nom_h, rot)
                pdx, pdy, pdz = dx + margin, dy + margin, dz + margin

                # Boundary check
                if px + pdx > carton_l or py + pdy > carton_w or pz + pdz > carton_h:
                    continue

                # Overlap check against existing placements
                collision = False
                for existing in placements:
                    ex_x, ex_y, ex_z = existing.position_mm.x, existing.position_mm.y, existing.position_mm.z
                    ex_dx, ex_dy, ex_dz = existing.placed_dimensions_mm.dx, existing.placed_dimensions_mm.dy, existing.placed_dimensions_mm.dz
                    if (
                        max(px, ex_x) < min(px + pdx, ex_x + ex_dx)
                        and max(py, ex_y) < min(py + pdy, ex_y + ex_dy)
                        and max(pz, ex_z) < min(pz + pdz, ex_z + ex_dz)
                    ):
                        collision = True
                        break

                if collision:
                    continue

                # Support & Fragility check if elevated
                supported_area = 0
                supporting_ids: List[str] = []
                fragility_conflict = False

                if pz > 0:
                    for existing in placements:
                        ex_top = existing.position_mm.z + existing.placed_dimensions_mm.dz
                        if ex_top == pz:
                            ox = max(0, min(px + pdx, existing.position_mm.x + existing.placed_dimensions_mm.dx) - max(px, existing.position_mm.x))
                            oy = max(0, min(py + pdy, existing.position_mm.y + existing.placed_dimensions_mm.dy) - max(py, existing.position_mm.y))
                            overlap = ox * oy
                            if overlap > 0:
                                supported_area += overlap
                                supporting_ids.append(existing.item_id)
                                ex_item = item_dict.get(existing.item_id)
                                if ex_item:
                                    if not ex_item.stackable:
                                        fragility_conflict = True
                                        break
                                    if ex_item.fragility_class == "high" and item.fragility_class != "high":
                                        fragility_conflict = True
                                        break

                    if fragility_conflict:
                        continue

                    support_ratio = supported_area / float(pdx * pdy)
                    if support_ratio < min_support_ratio:
                        continue
                else:
                    support_ratio = 1.0
                    supporting_ids = ["CARTON_FLOOR"]

                # Placement objective score: compact toward front-left-bottom
                score = 100 * (pz + pdz) + 10 * pz + (px + py)
                if score < best_score:
                    best_score = score
                    best_candidate = (
                        px, py, pz, rot, pdx, pdy, pdz, dx, dy, dz, support_ratio, supporting_ids
                    )

        if best_candidate is not None:
            (
                c_px, c_py, c_pz, c_rot, c_pdx, c_pdy, c_pdz, c_dx, c_dy, c_dz, c_ratio, c_supporters
            ) = best_candidate

            placed_item = PlacedItem(
                step_number=len(placements) + 1,
                item_id=item.item_id,
                display_name=item.display_name,
                rotation_code=c_rot,
                position_mm=Position3D(x=c_px, y=c_py, z=c_pz),
                placed_dimensions_mm=PlacedDimensions3D(dx=c_pdx, dy=c_pdy, dz=c_pdz),
                nominal_dimensions_mm=PlacedDimensions3D(dx=c_dx, dy=c_dy, dz=c_dz),
                support_ratio=min(1.0, round(c_ratio, 3)),
                supported_by_item_ids=c_supporters,
                display_color_hex=item.display_color_hex,
            )
            placements.append(placed_item)
            current_payload_g += item_weight

            # Add new candidate extreme points
            extreme_points.append((c_px + c_pdx, c_py, c_pz))
            extreme_points.append((c_px, c_py + c_pdy, c_pz))
            extreme_points.append((c_px, c_py, c_pz + c_pdz))
            placed = True
        else:
            unpacked.append(item)

    # Sort final placements lexicographically by z asc, y asc, x asc, volume desc
    placements.sort(
        key=lambda p: (
            p.position_mm.z,
            p.position_mm.y,
            p.position_mm.x,
            -(p.placed_dimensions_mm.dx * p.placed_dimensions_mm.dy * p.placed_dimensions_mm.dz),
        )
    )
    for idx, p in enumerate(placements, start=1):
        p.step_number = idx

    all_packed = len(unpacked) == 0 and len(placements) == len(items)
    return all_packed, placements, unpacked

