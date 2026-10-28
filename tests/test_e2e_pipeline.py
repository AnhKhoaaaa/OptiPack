"""End-to-End API Integration Tests."""

import json
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from backend.app.api.main import app


client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["contract_version"] == "1.0.0"


def test_catalog_endpoint():
    response = client.get("/api/v1/catalog/cartons")
    assert response.status_code == 200
    cartons = response.json()
    assert len(cartons) == 5
    assert cartons[0]["carton_id"] == "BOX-S"


def test_analyze_endpoint_returns_golden_fixture():
    with open(FIXTURES_DIR / "order_analysis_sample.json", "rb") as f:
        file_bytes = f.read()

    response = client.post(
        "/api/v1/orders/analyze",
        files={"top_image": ("top.jpg", file_bytes, "image/jpeg")},
        data={"capture_mode": "dual_photo"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["contract_version"] == "1.0.0"
    assert len(data["items"]) >= 1


def test_pack_endpoint_e2e():
    with open(FIXTURES_DIR / "packing_request_sample.json", "r", encoding="utf-8") as f:
        req_payload = json.load(f)

    response = client.post("/api/v1/orders/pack", json=req_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["contract_version"] == "1.0.0"
    assert data["status"] in ("OPTIMAL", "FEASIBLE")
    assert data["primary_plan"] is not None
    assert data["primary_plan"]["validation"]["is_valid"] is True
