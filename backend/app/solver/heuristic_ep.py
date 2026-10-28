"""Tier 1 Extreme-Point First-Fit Decreasing 3D Bin Packing Heuristic.

Provides a fast deterministic baseline (< 30ms) for carton packing and
constructive initial solutions with guaranteed vertical support.
"""

from typing import List, Optional, Tuple
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


def pack_carton_heuristic_ep(
    carton: CartonSpec,
    items: List[PackableItem],
    min_support_ratio: float = 0.60,
) -> Tuple[bool, List[PlacedItem]]:
    """Pack items into the carton using Extreme-Point placement heuristic.

    Returns:
        (success_bool, placements_list)
    """
    carton_l = carton.internal_dimensions_mm.length_mm
    carton_w = carton.internal_dimensions_mm.width_mm
    carton_h = carton.internal_dimensions_mm.height_mm

    # Sort items by volume descending (First-Fit Decreasing)
    sorted_items = sorted(
        items,
        key=lambda it: it.dimensions_mm.length_mm * it.dimensions_mm.width_mm * it.dimensions_mm.height_mm,
        reverse=True,
    )

    placements: List[PlacedItem] = []
    extreme_points: List[Tuple[int, int, int]] = [(0, 0, 0)]

    for idx, item in enumerate(sorted_items, start=1):
        placed = False
        allowed_rots = UPRIGHT_ROTATION_CODES if item.keep_upright else item.allowed_rotations

        # Candidate evaluations (sort extreme points primarily by Z ascending, then Y, then X)
        extreme_points.sort(key=lambda pt: (pt[2], pt[1], pt[0]))

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
                    if (max(px, ex_x) < min(px + pdx, ex_x + ex_dx) and
                        max(py, ex_y) < min(py + pdy, ex_y + ex_dy) and
                        max(pz, ex_z) < min(pz + pdz, ex_z + ex_dz)):
                        collision = True
                        break

                if collision:
                    continue

                # Support check if elevated
                if pz > 0:
                    supported_area = 0
                    for existing in placements:
                        ex_top = existing.position_mm.z + existing.placed_dimensions_mm.dz
                        if ex_top == pz:
                            ox = max(0, min(px + pdx, existing.position_mm.x + existing.placed_dimensions_mm.dx) -
                                        max(px, existing.position_mm.x))
                            oy = max(0, min(py + pdy, existing.position_mm.y + existing.placed_dimensions_mm.dy) -
                                        max(py, existing.position_mm.y))
                            supported_area += ox * oy
                    if (supported_area / (pdx * pdy)) < min_support_ratio:
                        continue

                # Place item
                placed_item = PlacedItem(
                    step_number=idx,
                    item_id=item.item_id,
                    display_name=item.display_name,
                    rotation_code=rot,
                    position_mm=Position3D(x=px, y=py, z=pz),
                    placed_dimensions_mm=PlacedDimensions3D(dx=pdx, dy=pdy, dz=pdz),
                    nominal_dimensions_mm=PlacedDimensions3D(dx=dx, dy=dy, dz=dz),
                    support_ratio=1.0 if pz == 0 else min(1.0, supported_area / (pdx * pdy)),
                    supported_by_item_ids=["CARTON_FLOOR"] if pz == 0 else [],
                    display_color_hex=item.display_color_hex,
                )
                placements.append(placed_item)

                # Add new extreme points generated by this placement
                extreme_points.append((px + pdx, py, pz))
                extreme_points.append((px, py + pdy, pz))
                extreme_points.append((px, py, pz + pdz))

                placed = True
                break
            if placed:
                break

        if not placed:
            return False, placements

    return True, placements
