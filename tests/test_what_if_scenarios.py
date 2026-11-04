"""Unit and Integration Tests for What-If Multi-Scenario Packaging Engine (V2.0).

Verifies the 4 scenario classification tiers:
1. GREEN: Feasible at nominal box dimensions.
2. YELLOW: Elastic lid compression (Delta H <= min(10% H, 25mm)) for soft/resilient items.
3. RED: Fragile overflow rejection or oversized ejection to fit remainder.
4. BEST_FIT: Standard catalog benchmark generation.
Also tests FastAPI POST /api/v1/orders/pack endpoint integration.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.api.main import app
from backend.app.schemas.contracts import (
    CartonSpec,
    Dimensions3D,
    PackableItem,
    PackingRequest,
    RotationCode,
    SolverConfig,
)
from backend.app.solver.cpsat_solver import solve_packing
from backend.app.solver.what_if_engine import evaluate_what_if_scenarios


@pytest.fixture
def user_box_m() -> CartonSpec:
    return CartonSpec(
        carton_id="USER-BOX-M",
        display_name="Thùng Carton M của bạn",
        internal_dimensions_mm=Dimensions3D(length_mm=300, width_mm=220, height_mm=150),
        tare_weight_g=160,
        max_payload_g=8000,
        box_cost_usd=0.85,
    )


@pytest.fixture
def small_shallow_box() -> CartonSpec:
    return CartonSpec(
        carton_id="USER-SHALLOW",
        display_name="Thùng dẹt của bạn",
        internal_dimensions_mm=Dimensions3D(length_mm=200, width_mm=150, height_mm=80),
        tare_weight_g=100,
        max_payload_g=5000,
        box_cost_usd=0.50,
    )


def test_what_if_green_scenario(user_box_m):
    """Assert items that fit comfortably inside user box receive GREEN classification."""
    items = [
        PackableItem(
            item_id="item_01",
            display_name="GoChek Wireless Mic Case",
            dimensions_mm=Dimensions3D(length_mm=80, width_mm=80, height_mm=40),
            safety_margin_mm=0,
            weight_g=200,
            material_type="rigid_box",
            weight_tier="light",
            allowed_rotations=[RotationCode.LWH],
        ),
        PackableItem(
            item_id="item_02",
            display_name="White Electronic Device",
            dimensions_mm=Dimensions3D(length_mm=130, width_mm=50, height_mm=60),
            safety_margin_mm=0,
            weight_g=350,
            material_type="rigid_box",
            weight_tier="light",
            allowed_rotations=[RotationCode.LWH],
        ),
    ]

    config = SolverConfig(min_support_ratio=0.60)
    scenarios = evaluate_what_if_scenarios(items, [user_box_m], config)

    # Must contain user box scenario + BEST_FIT scenario
    assert len(scenarios) == 2
    user_card = next(s for s in scenarios if s.is_user_box)

    assert user_card.badge_status == "GREEN"
    assert user_card.feasible is True
    assert user_card.overflow_height_mm == 0
    assert len(user_card.ejected_item_ids) == 0
    assert user_card.is_selected_default is True
    assert user_card.plan is not None
    assert "Vừa vặn" in user_card.title
    assert "Vừa vặn hoàn hảo" in user_card.advisor_title
    assert len(user_card.advisor_explanation) > 10


def test_what_if_yellow_scenario_soft_compressible(small_shallow_box):
    """Assert item exceeding box height by <= 10% with soft material receives YELLOW classification."""
    # Box height is 80mm. 10% of 80 is 8mm.
    # An item with height 86mm overflows by 6mm (<= 8mm), soft_fabric material.
    items = [
        PackableItem(
            item_id="item_tissue",
            display_name="Top Gia Khăn Giấy",
            dimensions_mm=Dimensions3D(length_mm=150, width_mm=100, height_mm=86),
            safety_margin_mm=0,
            weight_g=150,
            fragility_class="low",
            stackable=True,
            material_type="soft_fabric",
            weight_tier="light",
            allowed_rotations=[RotationCode.LWH],  # forces 86mm along Z
        )
    ]

    config = SolverConfig(min_support_ratio=0.60)
    scenarios = evaluate_what_if_scenarios(items, [small_shallow_box], config)

    user_card = next(s for s in scenarios if s.is_user_box)
    assert user_card.badge_status == "YELLOW"
    assert user_card.feasible is True
    assert user_card.overflow_height_mm == 6
    assert len(user_card.ejected_item_ids) == 0
    assert user_card.is_selected_default is True
    assert "Cấn nắp nhẹ" in user_card.title
    assert "băng keo" in user_card.advisor_explanation.lower()


def test_what_if_yellow_rejected_when_fragile(small_shallow_box):
    """Assert elastic compression is strictly rejected if overflowing item is glass/fragile, resulting in RED."""
    # Box height is 80mm. Item height 86mm, but material is glass_ceramic.
    items = [
        PackableItem(
            item_id="item_glass_cup",
            display_name="Ly Thủy Tinh Cao Cấp",
            dimensions_mm=Dimensions3D(length_mm=150, width_mm=100, height_mm=86),
            safety_margin_mm=0,
            weight_g=300,
            fragility_class="high",
            stackable=False,
            material_type="glass_ceramic",
            weight_tier="medium",
            allowed_rotations=[RotationCode.LWH],
        )
    ]

    config = SolverConfig(min_support_ratio=0.60)
    scenarios = evaluate_what_if_scenarios(items, [small_shallow_box], config)

    user_card = next(s for s in scenarios if s.is_user_box)
    # Cannot be YELLOW because glass/fragile item cannot tolerate lid pressure!
    assert user_card.badge_status == "RED"
    assert user_card.feasible is False
    assert "item_glass_cup" in user_card.ejected_item_ids


def test_what_if_red_scenario_ejection(small_shallow_box):
    """Assert that when order exceeds capacity, RED card packs a subset and lists ejected items."""
    # Small shallow box (200 x 150 x 80)
    items = [
        PackableItem(
            item_id="item_fits",
            display_name="Món vừa vặn",
            dimensions_mm=Dimensions3D(length_mm=140, width_mm=90, height_mm=50),
            safety_margin_mm=0,
            weight_g=200,
            material_type="rigid_box",
            allowed_rotations=[RotationCode.LWH],
        ),
        PackableItem(
            item_id="item_oversized",
            display_name="Món quá khổ",
            dimensions_mm=Dimensions3D(length_mm=250, width_mm=180, height_mm=120),  # exceeds 200x150x80
            safety_margin_mm=0,
            weight_g=1000,
            material_type="rigid_box",
            allowed_rotations=[RotationCode.LWH],
        ),
    ]

    config = SolverConfig(min_support_ratio=0.60)
    scenarios = evaluate_what_if_scenarios(items, [small_shallow_box], config)

    user_card = next(s for s in scenarios if s.is_user_box)
    assert user_card.badge_status == "RED"
    assert user_card.feasible is False
    assert "item_oversized" in user_card.ejected_item_ids
    assert "item_fits" not in user_card.ejected_item_ids
    assert user_card.plan is not None
    assert len(user_card.plan.placements) == 1
    assert "Cần tách kiện" in user_card.title


def test_what_if_best_fit_benchmark(user_box_m):
    """Assert evaluate_what_if_scenarios always attaches a BEST_FIT benchmark card from standard catalog."""
    items = [
        PackableItem(
            item_id="item_01",
            display_name="Laptop Box",
            dimensions_mm=Dimensions3D(length_mm=350, width_mm=250, height_mm=60),
            safety_margin_mm=0,
            weight_g=1500,
            material_type="rigid_box",
        )
    ]

    config = SolverConfig(min_support_ratio=0.60)
    scenarios = evaluate_what_if_scenarios(items, [user_box_m], config)

    bf_card = next(s for s in scenarios if s.badge_status == "BEST_FIT")
    assert bf_card.is_user_box is False
    assert bf_card.feasible is True
    assert bf_card.plan is not None
    assert bf_card.volume_utilization_pct > 0.0
    assert "Đề xuất chuẩn" in bf_card.title


def test_solve_packing_with_user_boxes_request(user_box_m):
    """Assert solve_packing routes directly to what-if engine when user_selected_boxes is provided."""
    items = [
        PackableItem(
            item_id="item_01",
            display_name="GoChek Mic",
            dimensions_mm=Dimensions3D(length_mm=80, width_mm=80, height_mm=40),
            safety_margin_mm=0,
            weight_g=200,
        )
    ]

    req = PackingRequest(
        analysis_id="test_analysis_123",
        solver_config=SolverConfig(
            user_selected_boxes=[user_box_m]
        ),
        items=items,
    )

    resp = solve_packing(req)
    assert resp.status == "OPTIMAL"
    assert resp.solver_used == "what_if_multi_scenario_engine"
    assert resp.single_carton_feasible is True
    assert resp.primary_plan is not None
    assert len(resp.scenarios) >= 2


def test_pack_api_endpoint_integration(user_box_m):
    """Test FastAPI /api/v1/orders/pack endpoint with user_selected_boxes."""
    client = TestClient(app)

    payload = {
        "contract_version": "1.0.0",
        "analysis_id": "test_e2e_what_if",
        "solver_config": {
            "mode": "cpsat_with_heuristic_fallback",
            "time_limit_ms": 3000,
            "apply_uncertainty_margin": False,
            "min_support_ratio": 0.60,
            "allow_multi_carton_split": True,
            "user_selected_boxes": [user_box_m.model_dump()],
        },
        "items": [
            {
                "item_id": "item_top_gia",
                "display_name": "Top Gia Tissue",
                "quantity": 1,
                "dimensions_mm": {"length_mm": 140, "width_mm": 80, "height_mm": 50},
                "safety_margin_mm": 0,
                "weight_g": 200,
                "weight_assumed": False,
                "fragility_class": "low",
                "keep_upright": False,
                "stackable": True,
                "material_type": "soft_fabric",
                "weight_tier": "light",
                "allowed_rotations": ["LWH", "WLH", "LHW", "HLW", "WHL", "HWL"],
                "display_color_hex": "#3B82F6",
            }
        ],
    }

    res = client.post("/api/v1/orders/pack", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("OPTIMAL", "FEASIBLE")
    assert "scenarios" in data
    assert len(data["scenarios"]) >= 2
    # Verify first scenario card schema
    sc0 = data["scenarios"][0]
    assert "scenario_id" in sc0
    assert "badge_status" in sc0
    assert "advisor_title" in sc0
    assert "advisor_explanation" in sc0
    assert len(sc0["advisor_title"]) > 0


def test_empty_user_boxes_backward_compatibility():
    """Assert that omitting user_selected_boxes retains 100% backward compatibility and supplies BEST_FIT scenario."""
    client = TestClient(app)

    payload = {
        "contract_version": "1.0.0",
        "analysis_id": "test_backward_compat",
        "solver_config": {
            "mode": "cpsat_with_heuristic_fallback",
            "time_limit_ms": 3000,
            "apply_uncertainty_margin": False,
            "min_support_ratio": 0.60,
            "allow_multi_carton_split": True,
        },
        "items": [
            {
                "item_id": "item_standard",
                "display_name": "Standard Book",
                "quantity": 1,
                "dimensions_mm": {"length_mm": 200, "width_mm": 140, "height_mm": 30},
                "safety_margin_mm": 0,
                "weight_g": 400,
                "weight_assumed": False,
                "fragility_class": "low",
                "keep_upright": False,
                "stackable": True,
                "allowed_rotations": ["LWH", "WLH"],
                "display_color_hex": "#3B82F6",
            }
        ],
    }

    res = client.post("/api/v1/orders/pack", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "OPTIMAL"
    assert data["single_carton_feasible"] is True
    assert data["primary_plan"] is not None
    assert "scenarios" in data
    assert len(data["scenarios"]) >= 1
    assert data["scenarios"][0]["badge_status"] == "BEST_FIT"
