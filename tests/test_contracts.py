"""Unit Tests for Contract v1.0.0 Golden JSON Fixtures."""

import json
from pathlib import Path
import pytest
from backend.app.schemas.contracts import (
    CartonSpec,
    OrderAnalysisResponse,
    PackingRequest,
    PackingSolutionResponse,
)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_order_analysis_fixture_validates():
    with open(FIXTURES_DIR / "order_analysis_sample.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    resp = OrderAnalysisResponse(**data)
    assert resp.contract_version == "1.0.0"
    assert resp.analysis_id == "ord_20261027_001"
    assert len(resp.items) >= 1
    assert resp.items[0].dimensions_mm.length_mm == 210
    assert resp.calibration.status == "calibrated"


def test_packing_request_fixture_validates():
    with open(FIXTURES_DIR / "packing_request_sample.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    req = PackingRequest(**data)
    assert req.contract_version == "1.0.0"
    assert len(req.items) >= 1
    assert req.items[0].dimensions_mm.length_mm == 210


def test_packing_solution_fixture_validates():
    with open(FIXTURES_DIR / "packing_solution_sample.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    sol = PackingSolutionResponse(**data)
    assert sol.contract_version == "1.0.0"
    assert sol.status == "OPTIMAL"
    assert sol.primary_plan is not None
    assert sol.primary_plan.carton.carton_id == "BOX-M"
    assert sol.primary_plan.validation.is_valid is True
    assert sol.primary_plan.metrics.total_estimated_cost_usd == 6.87


def test_carton_catalog_fixture_validates():
    with open(FIXTURES_DIR / "carton_catalog_sample.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    cartons = [CartonSpec(**c) for c in data]
    assert len(cartons) == 5
    assert cartons[0].carton_id == "BOX-S"
    assert cartons[4].carton_id == "BOX-XXL"
