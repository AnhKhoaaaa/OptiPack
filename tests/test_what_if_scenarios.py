"""Unit tests for What-If multi-scenario generation engine."""

from backend.app.schemas.contracts import (
    CartonSpec,
    Dimensions3D,
    PackableItem,
    PackingRequest,
    SolverConfig,
)
from backend.app.solver.cpsat_solver import solve_packing
from backend.app.solver.what_if_engine import (
    compute_elastic_height_mm,
    generate_what_if_scenarios,
)


def test_compute_elastic_height_mm():
    # 10% of 200 is 20mm
    assert compute_elastic_height_mm(200) == 20
    # 10% of 400 is 40mm, capped at 25mm
    assert compute_elastic_height_mm(400) == 25
    # Small height (e.g. 50mm) returns at least 10mm
    assert compute_elastic_height_mm(50) == 10


def test_what_if_scenarios_generated():
    items = [
        PackableItem(
            item_id="item_01",
            display_name="T-Shirt Pack",
            quantity=1,
            dimensions_mm=Dimensions3D(length_mm=180, width_mm=130, height_mm=60),
            safety_margin_mm=0,
            weight_g=250,
            material_type="soft_fabric",
            weight_tier="light",
        ),
        PackableItem(
            item_id="item_02",
            display_name="Shoes Box",
            quantity=1,
            dimensions_mm=Dimensions3D(length_mm=220, width_mm=140, height_mm=80),
            safety_margin_mm=0,
            weight_g=800,
            material_type="rigid_box",
            weight_tier="medium",
        ),
    ]

    req = PackingRequest(
        contract_version="1.0.0",
        analysis_id="test_analysis",
        solver_config=SolverConfig(
            mode="cpsat_with_heuristic_fallback",
            time_limit_ms=2000,
            apply_uncertainty_margin=False,
            min_support_ratio=0.6,
            allow_multi_carton_split=True,
        ),
        items=items,
    )

    base_solution = solve_packing(req)
    assert base_solution.primary_plan is not None

    scenarios = generate_what_if_scenarios(
        items=items,
        user_boxes=[],
        base_solution=base_solution,
        solver_config=req.solver_config,
    )

    assert len(scenarios) >= 1
    # Check that best_fit is among scenarios
    has_best_fit = any(sc.badge_status == "BEST_FIT" for sc in scenarios)
    assert has_best_fit
