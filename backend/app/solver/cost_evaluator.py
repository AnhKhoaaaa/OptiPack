"""Packaging & Shipping Cost Evaluation Model.

Implements the explicit cost function defined in 01_PROJECT_SPEC.md Section 5.2:
1. Actual Gross Weight = (Carton Tare + Sum of item weights) / 1000
2. DIM Weight = (L * W * H) / 5,000,000
3. Billable Weight = max(Actual Gross Weight, DIM Weight)
4. Shipping Cost = Base fee ($3.50) + $1.20 * ceil(2 * Billable Weight) / 2
5. Void Fill Cost = $0.04 per Liter of empty space
6. Total Cost = Box Cost + Shipping Cost + Void Fill Cost
"""

import math
from typing import List, Tuple
from backend.app.schemas.contracts import CartonSpec, CenterOfMass3D, PackableItem, PackingMetrics, PlacedItem
from backend.app.solver.carton_catalog import (
    BASE_SHIPPING_FEE_USD,
    DEFAULT_ASSUMED_DENSITY_G_PER_CM3,
    DIM_DIVISOR_MM3_PER_KG,
    RATE_PER_KG_USD,
    RATE_VOID_PER_LITER_USD,
    get_carton_volume_mm3,
)


def compute_item_effective_weight_g(item: PackableItem) -> Tuple[int, bool]:
    """Return item weight in grams and whether it was assumed from density fallback."""
    if item.weight_g is not None and item.weight_g > 0:
        return item.weight_g, item.weight_assumed

    # Volume in cm^3
    vol_cm3 = (item.dimensions_mm.length_mm * item.dimensions_mm.width_mm * item.dimensions_mm.height_mm) / 1000.0
    assumed_weight = int(round(vol_cm3 * DEFAULT_ASSUMED_DENSITY_G_PER_CM3))
    return max(1, assumed_weight), True


def compute_packing_metrics(
    carton: CartonSpec,
    items: List[PackableItem],
    placements: List[PlacedItem],
) -> PackingMetrics:
    """Compute all volumetric, weight, and financial metrics for a packing plan."""
    carton_vol_mm3 = get_carton_volume_mm3(carton)

    # Total item volume (nominal dimensions in mm^3)
    total_item_vol_mm3 = sum(
        it.dimensions_mm.length_mm * it.dimensions_mm.width_mm * it.dimensions_mm.height_mm
        for it in items
    )
    volume_utilization_pct = round(
        min(100.0, (total_item_vol_mm3 / carton_vol_mm3) * 100.0), 1
    ) if carton_vol_mm3 > 0 else 0.0

    # Weight calculations
    total_item_weight_g = sum(compute_item_effective_weight_g(it)[0] for it in items)
    actual_gross_weight_kg = round((carton.tare_weight_g + total_item_weight_g) / 1000.0, 2)
    dim_weight_kg = round(carton_vol_mm3 / DIM_DIVISOR_MM3_PER_KG, 2)
    billable_weight_raw = max(actual_gross_weight_kg, dim_weight_kg)
    # Billed in 0.5 kg increments rounded up
    billable_weight_kg = math.ceil(billable_weight_raw * 2.0) / 2.0

    # Shipping cost
    shipping_cost_usd = round(BASE_SHIPPING_FEE_USD + RATE_PER_KG_USD * billable_weight_kg, 2)

    # Void fill cost
    void_vol_mm3 = max(0, carton_vol_mm3 - total_item_vol_mm3)
    void_fill_cost_usd = round(RATE_VOID_PER_LITER_USD * (void_vol_mm3 / 1_000_000.0), 2)

    # Box material cost
    box_cost_usd = carton.box_cost_usd

    # Total cost
    total_estimated_cost_usd = round(box_cost_usd + shipping_cost_usd + void_fill_cost_usd, 2)

    # Composite center of mass
    if placements and total_item_weight_g > 0:
        item_map = {it.item_id: it for it in items}
        weighted_x = 0.0
        weighted_y = 0.0
        weighted_z = 0.0
        for p in placements:
            w_g = compute_item_effective_weight_g(item_map[p.item_id])[0] if p.item_id in item_map else 100
            cx = p.position_mm.x + p.placed_dimensions_mm.dx / 2.0
            cy = p.position_mm.y + p.placed_dimensions_mm.dy / 2.0
            cz = p.position_mm.z + p.placed_dimensions_mm.dz / 2.0
            weighted_x += cx * w_g
            weighted_y += cy * w_g
            weighted_z += cz * w_g
        center_of_mass = CenterOfMass3D(
            x=round(weighted_x / total_item_weight_g, 1),
            y=round(weighted_y / total_item_weight_g, 1),
            z=round(weighted_z / total_item_weight_g, 1),
        )
    else:
        dims = carton.internal_dimensions_mm
        center_of_mass = CenterOfMass3D(
            x=round(dims.length_mm / 2.0, 1),
            y=round(dims.width_mm / 2.0, 1),
            z=round(dims.height_mm / 2.0, 1),
        )

    return PackingMetrics(
        volume_utilization_pct=volume_utilization_pct,
        total_items_packed=len(placements),
        actual_gross_weight_kg=actual_gross_weight_kg,
        dim_weight_kg=dim_weight_kg,
        billable_weight_kg=round(billable_weight_kg, 2),
        box_cost_usd=box_cost_usd,
        void_fill_cost_usd=void_fill_cost_usd,
        shipping_cost_usd=shipping_cost_usd,
        total_estimated_cost_usd=total_estimated_cost_usd,
        center_of_mass_mm=center_of_mass,
    )
