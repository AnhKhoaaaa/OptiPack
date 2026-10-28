"""Standard E-Commerce Carton Catalog and Packaging Constants.

Conforms strictly to 01_PROJECT_SPEC.md Section 5.1.
All dimensions are internal usable dimensions in millimeters (mm).
"""

from typing import Dict, List
from backend.app.schemas.contracts import CartonSpec, Dimensions3D


# DIM Divisor in mm^3 / kg (5000 cm^3/kg)
DIM_DIVISOR_MM3_PER_KG = 5_000_000.0

# Shipping Cost Parameters
BASE_SHIPPING_FEE_USD = 3.50
RATE_PER_KG_USD = 1.20
RATE_VOID_PER_LITER_USD = 0.04  # $0.04 per 10^6 mm^3
DEFAULT_ASSUMED_DENSITY_G_PER_CM3 = 0.25


# Finite standard carton catalog (5 standard corrugated mailer/carton sizes)
STANDARD_CARTONS: List[CartonSpec] = [
    CartonSpec(
        carton_id="BOX-S",
        display_name="Small Mailer Box",
        internal_dimensions_mm=Dimensions3D(length_mm=200, width_mm=150, height_mm=100),
        tare_weight_g=85,
        max_payload_g=3000,
        box_cost_usd=0.45,
    ),
    CartonSpec(
        carton_id="BOX-M",
        display_name="Medium Standard Carton",
        internal_dimensions_mm=Dimensions3D(length_mm=300, width_mm=220, height_mm=150),
        tare_weight_g=160,
        max_payload_g=8000,
        box_cost_usd=0.85,
    ),
    CartonSpec(
        carton_id="BOX-L",
        display_name="Large E-Commerce Carton",
        internal_dimensions_mm=Dimensions3D(length_mm=400, width_mm=300, height_mm=200),
        tare_weight_g=280,
        max_payload_g=15000,
        box_cost_usd=1.40,
    ),
    CartonSpec(
        carton_id="BOX-XL",
        display_name="Extra-Large Fulfillment Box",
        internal_dimensions_mm=Dimensions3D(length_mm=500, width_mm=350, height_mm=250),
        tare_weight_g=420,
        max_payload_g=20000,
        box_cost_usd=2.10,
    ),
    CartonSpec(
        carton_id="BOX-XXL",
        display_name="Heavy Bulk Master Carton",
        internal_dimensions_mm=Dimensions3D(length_mm=600, width_mm=400, height_mm=350),
        tare_weight_g=650,
        max_payload_g=25000,
        box_cost_usd=3.20,
    ),
]


CARTON_BY_ID: Dict[str, CartonSpec] = {c.carton_id: c for c in STANDARD_CARTONS}


def get_carton_volume_mm3(carton: CartonSpec) -> int:
    """Return internal volume in mm^3."""
    dims = carton.internal_dimensions_mm
    return dims.length_mm * dims.width_mm * dims.height_mm


def get_carton_dim_weight_kg(carton: CartonSpec) -> float:
    """Return dimensional weight in kg."""
    return round(get_carton_volume_mm3(carton) / DIM_DIVISOR_MM3_PER_KG, 2)
