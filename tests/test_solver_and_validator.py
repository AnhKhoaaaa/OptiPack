"""Unit and Integration Tests for Member 3: Solver and Deterministic Validator.

Conforms to document/02c_member3_or_3d_solver.md Section 8.
"""

import pytest
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
from backend.app.solver.cost_evaluator import compute_packing_metrics
from backend.app.solver.cpsat_solver import solve_packing
from backend.app.solver.geometry_validator import validate_packing_solution


@pytest.fixture
def sample_carton_m() -> CartonSpec:
    return CartonSpec(
        carton_id="BOX-M",
        display_name="Medium Standard Carton",
        internal_dimensions_mm=Dimensions3D(length_mm=300, width_mm=220, height_mm=150),
        tare_weight_g=160,
        max_payload_g=8000,
        box_cost_usd=0.85,
    )


def test_validator_rejects_pairwise_overlap(sample_carton_m):
    """Assert validator detects AABB overlap between items."""
    item1 = PackableItem(
        item_id="item_01",
        display_name="Cube 1",
        dimensions_mm=Dimensions3D(length_mm=100, width_mm=100, height_mm=100),
        safety_margin_mm=0,
        weight_g=500,
        allowed_rotations=[RotationCode.LWH],
    )
    item2 = PackableItem(
        item_id="item_02",
        display_name="Cube 2",
        dimensions_mm=Dimensions3D(length_mm=100, width_mm=100, height_mm=100),
        safety_margin_mm=0,
        weight_g=500,
        allowed_rotations=[RotationCode.LWH],
    )

    # Placed at (0,0,0) and (50,0,0) -> 50mm overlap in X
    p1 = PlacedItem(
        step_number=1,
        item_id="item_01",
        display_name="Cube 1",
        rotation_code=RotationCode.LWH,
        position_mm=Position3D(x=0, y=0, z=0),
        placed_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=100),
        nominal_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=100),
        support_ratio=1.0,
        supported_by_item_ids=["CARTON_FLOOR"],
    )
    p2 = PlacedItem(
        step_number=2,
        item_id="item_02",
        display_name="Cube 2",
        rotation_code=RotationCode.LWH,
        position_mm=Position3D(x=50, y=0, z=0),
        placed_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=100),
        nominal_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=100),
        support_ratio=1.0,
        supported_by_item_ids=["CARTON_FLOOR"],
    )

    report = validate_packing_solution(sample_carton_m, [item1, item2], [p1, p2])
    assert report.is_valid is False
    assert report.overlap_check_passed is False
    assert any("collision" in v.lower() for v in report.violations)


def test_validator_rejects_floating_item(sample_carton_m):
    """Assert validator rejects item floating in mid-air with zero support."""
    item = PackableItem(
        item_id="item_01",
        display_name="Floating Box",
        dimensions_mm=Dimensions3D(length_mm=100, width_mm=100, height_mm=50),
        safety_margin_mm=0,
        weight_g=400,
        allowed_rotations=[RotationCode.LWH],
    )
    p = PlacedItem(
        step_number=1,
        item_id="item_01",
        display_name="Floating Box",
        rotation_code=RotationCode.LWH,
        position_mm=Position3D(x=0, y=0, z=50),  # Floating at z=50 with no supporting box
        placed_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=50),
        nominal_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=50),
        support_ratio=0.0,
        supported_by_item_ids=[],
    )

    report = validate_packing_solution(sample_carton_m, [item], [p], min_support_ratio=0.60)
    assert report.is_valid is False
    assert report.support_check_passed is False
    assert any("insufficient vertical support" in v.lower() for v in report.violations)


def test_validator_rejects_crushed_fragile_item(sample_carton_m):
    """Assert validator rejects stacking on non-stackable or highly fragile items."""
    fragile_item = PackableItem(
        item_id="item_glass",
        display_name="Glass Figurine",
        dimensions_mm=Dimensions3D(length_mm=100, width_mm=100, height_mm=60),
        safety_margin_mm=0,
        weight_g=300,
        fragility_class="high",
        stackable=False,
        allowed_rotations=[RotationCode.LWH],
    )
    heavy_item = PackableItem(
        item_id="item_metal",
        display_name="Metal Tool",
        dimensions_mm=Dimensions3D(length_mm=100, width_mm=100, height_mm=50),
        safety_margin_mm=0,
        weight_g=1500,
        fragility_class="low",
        stackable=True,
        allowed_rotations=[RotationCode.LWH],
    )

    p_bottom = PlacedItem(
        step_number=1,
        item_id="item_glass",
        display_name="Glass Figurine",
        rotation_code=RotationCode.LWH,
        position_mm=Position3D(x=0, y=0, z=0),
        placed_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=60),
        nominal_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=60),
        support_ratio=1.0,
        supported_by_item_ids=["CARTON_FLOOR"],
    )
    p_top = PlacedItem(
        step_number=2,
        item_id="item_metal",
        display_name="Metal Tool",
        rotation_code=RotationCode.LWH,
        position_mm=Position3D(x=0, y=0, z=60),
        placed_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=50),
        nominal_dimensions_mm=PlacedDimensions3D(dx=100, dy=100, dz=50),
        support_ratio=1.0,
        supported_by_item_ids=["item_glass"],
    )

    report = validate_packing_solution(
        sample_carton_m, [fragile_item, heavy_item], [p_bottom, p_top]
    )
    assert report.is_valid is False
    assert report.fragility_check_passed is False
    assert any("non-stackable" in v.lower() or "fragile" in v.lower() for v in report.violations)


def test_keep_upright_enforced_in_solver():
    """Assert solver restricts rotation to upright orientations when keep_upright=True."""
    item = PackableItem(
        item_id="item_bottle",
        display_name="Olive Oil Bottle",
        dimensions_mm=Dimensions3D(length_mm=80, width_mm=80, height_mm=220),
        safety_margin_mm=5,
        weight_g=800,
        keep_upright=True,
        allowed_rotations=[RotationCode.LWH, RotationCode.WLH],
    )

    req = PackingRequest(
        analysis_id="test_upright",
        solver_config=SolverConfig(mode="cpsat_with_heuristic_fallback", time_limit_ms=2000),
        items=[item],
    )

    response = solve_packing(req)
    assert response.status == "OPTIMAL"
    assert response.primary_plan is not None

    placement = response.primary_plan.placements[0]
    assert placement.rotation_code in (RotationCode.LWH, RotationCode.WLH)
    # Z extent must correspond to height_mm + safety_margin_mm
    assert placement.placed_dimensions_mm.dz == 220 + 5


def test_dim_weight_vs_actual_weight_cost_selection():
    """Assert cost evaluator calculates DIM vs Actual correctly and selects lower cost carton."""
    items = [
        PackableItem(
            item_id="item_01",
            display_name="Book",
            dimensions_mm=Dimensions3D(length_mm=180, width_mm=120, height_mm=40),
            safety_margin_mm=0,
            weight_g=500,
        )
    ]
    req = PackingRequest(
        analysis_id="test_cost",
        solver_config=SolverConfig(mode="cpsat_with_heuristic_fallback"),
        items=items,
    )
    response = solve_packing(req)
    assert response.status == "OPTIMAL"
    assert response.primary_plan is not None
    # For small book, BOX-S ($4.87) is strictly cheaper than BOX-M ($7.01)
    assert response.primary_plan.carton.carton_id == "BOX-S"
    assert response.primary_plan.metrics.box_cost_usd == 0.45


def test_multi_carton_split_oversized_order():
    """Assert oversized order triggers clean multi-carton split with valid plans."""
    oversized_items = [
        PackableItem(
            item_id=f"big_item_{i}",
            display_name=f"Big Item {i}",
            dimensions_mm=Dimensions3D(length_mm=380, width_mm=280, height_mm=180),
            safety_margin_mm=0,
            weight_g=4000,
        )
        for i in range(8)
    ]

    req = PackingRequest(
        analysis_id="test_split",
        solver_config=SolverConfig(allow_multi_carton_split=True),
        items=oversized_items,
    )

    response = solve_packing(req)
    assert response.single_carton_feasible is False
    assert response.status in ("FEASIBLE", "OPTIMAL")
    assert response.primary_plan is not None
    assert response.primary_plan.validation.is_valid is True
    assert len(response.overflow_plans) >= 1
    for over in response.overflow_plans:
        assert over.validation.is_valid is True

