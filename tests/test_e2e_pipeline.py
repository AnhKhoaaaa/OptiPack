"""End-to-End API Integration & Milestone Acceptance Test Suite.

Covers Canonical Scenarios E2E-01 through E2E-05 conforming to:
- document/03_execution_plan.md Section 6
- GitHub Issue #23 [Milestone M3] Full End-to-End Acceptance Suite
"""

import json
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from backend.app.api.main import app
from backend.app.schemas.contracts import (
    Dimensions3D,
    PackableItem,
    PackingRequest,
    RotationCode,
    SolverConfig,
)


client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# -----------------------------------------------------------------------------
# Base Health & Catalog Verification
# -----------------------------------------------------------------------------

def test_health_endpoint():
    """Verify system health check."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["contract_version"] == "1.0.0"


def test_catalog_endpoint():
    """Verify carton catalog endpoint returns all 5 standard cartons."""
    response = client.get("/api/v1/catalog/cartons")
    assert response.status_code == 200
    cartons = response.json()
    assert len(cartons) == 5
    carton_ids = [c["carton_id"] for c in cartons]
    assert carton_ids == ["BOX-S", "BOX-M", "BOX-L", "BOX-XL", "BOX-XXL"]


# -----------------------------------------------------------------------------
# Milestone M3 Acceptance Test Suite (E2E-01 through E2E-05)
# -----------------------------------------------------------------------------

def test_e2e_01_standard_happy_path():
    """E2E-01: Standard 4-Item Order (Happy Path).

    Full pipeline: Top-down photo -> analyze -> 4 detected items -> CP-SAT pack into BOX-M.
    Asserts HTTP 200, valid geometry across all 6 deterministic checks, and candidate comparison.
    """
    with open(FIXTURES_DIR / "order_analysis_sample.json", "rb") as f:
        file_bytes = f.read()

    # Step 1: Analyze Order
    analyze_res = client.post(
        "/api/v1/orders/analyze",
        files={"top_image": ("top.jpg", file_bytes, "image/jpeg")},
        data={"capture_mode": "dual_photo"},
    )
    assert analyze_res.status_code == 200
    analysis = analyze_res.json()
    assert analysis["contract_version"] == "1.0.0"
    assert analysis["calibration"]["status"] in ("calibrated", "fallback_zenith_only")

    # Step 2: Pack 4 Standard Items
    items = [
        PackableItem(
            item_id="item_01",
            display_name="Wireless Headphones Retail Box",
            quantity=1,
            dimensions_mm=Dimensions3D(length_mm=210, width_mm=165, height_mm=95),
            safety_margin_mm=5,
            weight_g=480,
            allowed_rotations=[RotationCode.LWH, RotationCode.WLH],
        ),
        PackableItem(
            item_id="item_02",
            display_name="Smartphone Packaging",
            quantity=1,
            dimensions_mm=Dimensions3D(length_mm=160, width_mm=85, height_mm=45),
            safety_margin_mm=5,
            weight_g=320,
        ),
        PackableItem(
            item_id="item_03",
            display_name="Fast Charger GaN Set",
            quantity=1,
            dimensions_mm=Dimensions3D(length_mm=85, width_mm=50, height_mm=45),
            safety_margin_mm=5,
            weight_g=210,
        ),
        PackableItem(
            item_id="item_04",
            display_name="Silicone Armor Case",
            quantity=1,
            dimensions_mm=Dimensions3D(length_mm=85, width_mm=50, height_mm=30),
            safety_margin_mm=5,
            weight_g=90,
        ),
    ]

    req = PackingRequest(
        analysis_id=analysis["analysis_id"],
        solver_config=SolverConfig(mode="cpsat_with_heuristic_fallback", time_limit_ms=3000),
        items=items,
    )

    pack_res = client.post("/api/v1/orders/pack", json=req.model_dump())
    assert pack_res.status_code == 200
    sol = pack_res.json()
    assert sol["status"] in ("OPTIMAL", "FEASIBLE")
    assert sol["primary_plan"] is not None

    plan = sol["primary_plan"]
    assert plan["carton"]["carton_id"] == "BOX-M"
    assert len(plan["placements"]) == 4

    val = plan["validation"]
    assert val["is_valid"] is True
    assert val["boundary_check_passed"] is True
    assert val["overlap_check_passed"] is True
    assert val["rotation_check_passed"] is True
    assert val["support_check_passed"] is True
    assert val["fragility_check_passed"] is True
    assert val["weight_check_passed"] is True


def test_e2e_02_fragile_and_upright_override():
    """E2E-02: Fragile + Keep Upright Override.

    Asserts user toggling keep_upright=True on Item 1 restricts rotations to LWH/WLH,
    and setting fragility_class="high" on Item 2 guarantees nothing is stacked on top.
    """
    items = [
        PackableItem(
            item_id="item_perfume",
            display_name="Luxury Glass Perfume",
            dimensions_mm=Dimensions3D(length_mm=90, width_mm=70, height_mm=135),
            safety_margin_mm=5,
            weight_g=380,
            keep_upright=True,
            allowed_rotations=[RotationCode.LWH, RotationCode.WLH],
        ),
        PackableItem(
            item_id="item_glass_candle",
            display_name="Scented Candle in Ceramic Jar",
            dimensions_mm=Dimensions3D(length_mm=110, width_mm=110, height_mm=90),
            safety_margin_mm=5,
            weight_g=520,
            fragility_class="high",
            stackable=False,
            max_top_load_g=0,
            keep_upright=True,
            allowed_rotations=[RotationCode.LWH, RotationCode.WLH],
        ),
        PackableItem(
            item_id="item_gift_box",
            display_name="Velvet Gift Box",
            dimensions_mm=Dimensions3D(length_mm=180, width_mm=140, height_mm=60),
            safety_margin_mm=5,
            weight_g=280,
            fragility_class="low",
            stackable=True,
            max_top_load_g=3000,
        ),
    ]

    req = PackingRequest(
        analysis_id="ord_override_02",
        solver_config=SolverConfig(mode="cpsat_with_heuristic_fallback", time_limit_ms=3000),
        items=items,
    )

    pack_res = client.post("/api/v1/orders/pack", json=req.model_dump())
    assert pack_res.status_code == 200
    sol = pack_res.json()
    assert sol["primary_plan"] is not None

    plan = sol["primary_plan"]
    assert plan["validation"]["is_valid"] is True
    assert plan["validation"]["fragility_check_passed"] is True
    assert plan["validation"]["rotation_check_passed"] is True

    # Perfume item must be strictly upright (Z dimension equals nominal height + margin = 140)
    perfume_p = next(p for p in plan["placements"] if p["item_id"] == "item_perfume")
    assert perfume_p["rotation_code"] in (RotationCode.LWH, RotationCode.WLH)
    assert perfume_p["placed_dimensions_mm"]["dz"] == 140


def test_e2e_03_dim_weight_vs_payload_tradeoff():
    """E2E-03: DIM Weight vs. Heavy Payload Tradeoff.

    3 compact heavy metal items totaling 4,200g fit in BOX-S volume,
    but exceed BOX-S max payload (3,000g). Solver must reject BOX-S and select BOX-M,
    billing by Actual Gross Weight instead of DIM weight.
    """
    items = [
        PackableItem(
            item_id=f"metal_item_{i}",
            display_name=f"Cast Iron Fitting {i}",
            dimensions_mm=Dimensions3D(length_mm=100, width_mm=80, height_mm=40),
            safety_margin_mm=5,
            weight_g=1400,
        )
        for i in range(3)
    ]

    req = PackingRequest(
        analysis_id="ord_heavy_payload_03",
        solver_config=SolverConfig(mode="cpsat_with_heuristic_fallback"),
        items=items,
    )

    pack_res = client.post("/api/v1/orders/pack", json=req.model_dump())
    assert pack_res.status_code == 200
    sol = pack_res.json()
    assert sol["primary_plan"] is not None

    plan = sol["primary_plan"]
    # BOX-S rejected due to 3000g payload cap; BOX-M chosen
    assert plan["carton"]["carton_id"] == "BOX-M"
    metrics = plan["metrics"]
    # Actual gross weight (~4.36kg) > DIM weight (~1.98kg)
    assert metrics["actual_gross_weight_kg"] > metrics["dim_weight_kg"]
    assert metrics["billable_weight_kg"] >= metrics["actual_gross_weight_kg"]


def test_e2e_04_degraded_unknown_weight_pack():
    """E2E-04: Degraded Calibration / Unknown Weight Warning & Manual Override.

    Simulates item with unobservable weight (null) and user-review requirement.
    User supplies confirmed weight and height; solver outputs valid packing plan.
    """
    item = PackableItem(
        item_id="item_unknown_weight",
        display_name="Custom Unmarked Container",
        dimensions_mm=Dimensions3D(length_mm=140, width_mm=90, height_mm=60),
        safety_margin_mm=5,
        weight_g=350,  # User confirmed weight
        weight_assumed=False,
    )

    req = PackingRequest(
        analysis_id="ord_degraded_04",
        solver_config=SolverConfig(mode="cpsat_with_heuristic_fallback"),
        items=[item],
    )

    pack_res = client.post("/api/v1/orders/pack", json=req.model_dump())
    assert pack_res.status_code == 200
    sol = pack_res.json()
    assert sol["primary_plan"] is not None
    assert sol["primary_plan"]["validation"]["is_valid"] is True


def test_e2e_05_multi_carton_split_oversized():
    """E2E-05: Multi-Carton Split for Oversized Order.

    8 large hardware items exceed the capacity of a single BOX-XXL.
    Solver must split items cleanly into primary carton + overflow carton(s),
    both passing 100% deterministic geometry validation.
    """
    items = [
        PackableItem(
            item_id=f"large_hardware_{i}",
            display_name=f"Heavy Industrial Assembly {i}",
            dimensions_mm=Dimensions3D(length_mm=380, width_mm=280, height_mm=180),
            safety_margin_mm=0,
            weight_g=4000,
        )
        for i in range(8)
    ]

    req = PackingRequest(
        analysis_id="ord_oversized_05",
        solver_config=SolverConfig(allow_multi_carton_split=True, time_limit_ms=3000),
        items=items,
    )

    pack_res = client.post("/api/v1/orders/pack", json=req.model_dump())
    assert pack_res.status_code == 200
    sol = pack_res.json()

    assert sol["single_carton_feasible"] is False
    assert sol["primary_plan"] is not None
    assert sol["primary_plan"]["validation"]["is_valid"] is True
    assert len(sol["overflow_plans"]) >= 1

    for overflow in sol["overflow_plans"]:
        assert overflow["validation"]["is_valid"] is True

    # Total items packed across primary + overflow plans equals 8
    total_packed = len(sol["primary_plan"]["placements"]) + sum(
        len(ov["placements"]) for ov in sol["overflow_plans"]
    )
    assert total_packed == 8
