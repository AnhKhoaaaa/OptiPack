"""Phase 2A API contract, CV/AI integration and fail-closed regression tests."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from fastapi.testclient import TestClient
import pytest

from backend.app.api.main import app
from backend.app.api.routers import orders
from backend.app.api.services.order_analysis import (
    encode_semantic_crops, get_cv_service, no_measurement_response,
)
from backend.app.cv.service import CVCalibrationError
from backend.app.schemas.contracts import (
    CalibrationInfo, DetectedItemMeasurement, Dimensions3D,
    ItemUncertainty, MeasurementProvenance, VisualEvidence,
)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def jpeg(width=100, height=80):
    image = np.zeros((height, width, 3), np.uint8)
    image[10:60, 15:70] = [70, 100, 140]
    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return buffer.tobytes()


def upload_pair(*, top=None, ob=None):
    return {
        "top_image": ("top.jpg", top if top is not None else jpeg(), "image/jpeg"),
        "oblique_image": ("oblique.jpg", ob if ob is not None else jpeg(), "image/jpeg"),
    }


def fake_batch():
    calibration = CalibrationInfo(
        status="calibrated", detected_markers_count=4,
        reprojection_error_px=.7, scale_mm_per_px_at_z0=.25,
        camera_pose_valid=True,
    )
    item = DetectedItemMeasurement(
        item_id="item_test_001", display_name="Generic package",
        dimensions_mm=Dimensions3D(length_mm=95, width_mm=60, height_mm=40),
        uncertainty_mm=ItemUncertainty(
            length_sigma_mm=4, width_sigma_mm=3,
            height_sigma_mm=9, safety_margin_mm=18,
        ),
        measurement_provenance=MeasurementProvenance(
            xy_method="aruco_two_view_sdf_fit",
            z_method="parallax_initializer_dual_view_sdf",
            confidence_score=.7, requires_user_review=True,
        ),
        visual_evidence=VisualEvidence(bbox_2d_px=[15, 10, 70, 60]),
    )
    return SimpleNamespace(
        calibration=SimpleNamespace(top_info=calibration),
        items=[item], warnings=[],
        unmatched_top_indices=[], unmatched_oblique_indices=[],
    )


class FakeCV:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def process_pair(self, top, oblique, **kwargs):
        self.calls.append((top.shape, oblique.shape, kwargs))
        if self.error is not None:
            raise self.error
        return fake_batch()


def test_explicit_demo_fixture_is_never_reported_as_real_cv(client):
    response = client.post(
        "/api/v1/orders/analyze",
        files={"top_image": ("fake.jpg", b"json-not-image", "image/jpeg")},
        data={"capture_mode": "demo_fixture"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["calibration"]["status"] == "uncalibrated"
    assert not body["calibration"]["camera_pose_valid"]
    assert body["calibration"]["detected_markers_count"] == 0
    assert body["items"]
    assert all(item["visual_evidence"]["crop_url"] is None for item in body["items"])
    assert all(
        entry["measurement_provenance"]["xy_method"] == "demo_fixture_not_measured"
        and entry["measurement_provenance"]["requires_user_review"]
        for entry in body["items"]
    )
    assert body["global_warnings"][0].startswith("DEMO FIXTURE ONLY")


def test_invalid_image_fails_in_live_mode_not_silent_mock(client):
    response = client.post(
        "/api/v1/orders/analyze",
        files={"top_image": ("fake.jpg", b"this-is-not-jpeg", "image/jpeg")},
    )
    assert response.status_code == 422


def test_missing_oblique_fails_closed_without_inventing_dimensions(client):
    response = client.post(
        "/api/v1/orders/analyze",
        files={"top_image": ("top.jpg", jpeg(), "image/jpeg")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["calibration"]["status"] == "fallback_zenith_only"
    assert body["calibration"]["camera_pose_valid"] is False
    assert "no dimensions" in body["global_warnings"][0]


def test_missing_camera_profile_does_not_forge_measurements(client):
    app.dependency_overrides[get_cv_service] = lambda: None
    response = client.post("/api/v1/orders/analyze", files=upload_pair())
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["calibration"]["status"] == "uncalibrated"
    assert "OPTIPACK_CAMERA_PROFILE_PATH" in body["global_warnings"][0]
    assert "placeholder" in body["calibration"]["warnings"][0]


def test_invalid_capture_mode_rejected(client):
    response = client.post(
        "/api/v1/orders/analyze",
        files={"top_image": ("top.jpg", jpeg(), "image/jpeg")},
        data={"capture_mode": "unknown_mode"},
    )
    assert response.status_code == 422


def test_mismatched_image_shapes_rejected(client):
    response = client.post(
        "/api/v1/orders/analyze",
        files=upload_pair(ob=jpeg(110, 80)),
    )
    assert response.status_code == 422


@pytest.mark.parametrize("error", [
    CVCalibrationError("missing fiducials"),
    RuntimeError("model unavailable"),
])
def test_cv_failure_yields_no_fake_dimensions(client, error):
    cv = FakeCV(error)
    app.dependency_overrides[get_cv_service] = lambda: cv
    response = client.post("/api/v1/orders/analyze", files=upload_pair())
    assert response.status_code == 200
    result = response.json()
    assert result["items"] == []
    assert result["calibration"]["camera_pose_valid"] is False
    assert result["ai_telemetry"]["fallback_activated"]
    assert cv.calls


def test_live_cv_crop_to_muse_contract_and_rotations(client, monkeypatch):
    cv = FakeCV()
    app.dependency_overrides[get_cv_service] = lambda: cv
    semantic_calls = []

    async def fake_batch(overview, crops, timeout_sec):
        semantic_calls.append((overview, crops, timeout_sec))
        assert len(crops) == 1
        assert crops[0]["item_id"] == "item_test_001"
        assert crops[0]["bbox_xyxy"] == [15, 10, 70, 60]
        assert crops[0]["dims_mm"] == (95, 60, 40)
        assert crops[0]["crop_bytes"].startswith(b"\xff\xd8\xff")
        return {
            "status": "cached", "latency_ms": 3,
            "fallback_activated": False,
            "items": {"item_test_001": {
                "weight_g": None, "weight_source": "unknown",
                "fragility_class": "high", "fragility_source": "visible_label",
                "keep_upright": True, "orientation_source": "label_this_side_up",
                "stackable": False, "max_top_load_g": 0,
                "visible_labels": ["FRAGILE"],
            }},
        }

    monkeypatch.setattr(orders, "analyze_items_with_muse_spark", fake_batch)
    response = client.post("/api/v1/orders/analyze", files=upload_pair())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["contract_version"] == "1.0.0"
    assert body["calibration"]["status"] == "calibrated"
    assert body["ai_telemetry"]["muse_status"] == "cached"
    assert body["ai_telemetry"]["fallback_activated"] is False
    assert len(cv.calls) == 1 and cv.calls[0][2]["save_crops"] is True
    assert len(semantic_calls) == 1
    item = body["items"][0]
    assert item["dimensions_mm"] == {"length_mm": 95, "width_mm": 60, "height_mm": 40}
    assert item["physical_attributes"]["fragility_class"] == "high"
    assert item["physical_attributes"]["weight_g"] is None
    assert item["physical_attributes"]["stackable"] is False
    assert item["allowed_rotations"] == ["LWH", "WLH"]
    assert item["measurement_provenance"]["requires_user_review"]
    assert any("review" in m for m in body["global_warnings"])


def test_muse_failure_falls_back_to_safe_unknown_weight(client, monkeypatch):
    cv = FakeCV()
    app.dependency_overrides[get_cv_service] = lambda: cv

    async def broken_batch(*args, **kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(orders, "analyze_items_with_muse_spark", broken_batch)
    response = client.post("/api/v1/orders/analyze", files=upload_pair())
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["physical_attributes"]["weight_g"] is None
    assert body["items"][0]["physical_attributes"]["weight_source"] == "unknown"
    assert body["ai_telemetry"]["fallback_activated"]
    assert body["ai_telemetry"]["muse_status"] == "fallback"


def test_muse_disabled_does_not_call_ai(client, monkeypatch):
    cv = FakeCV()
    app.dependency_overrides[get_cv_service] = lambda: cv

    async def forbidden(*args, **kwargs):
        raise AssertionError("AI must not be called")

    monkeypatch.setattr(orders, "analyze_items_with_muse_spark", forbidden)
    response = client.post(
        "/api/v1/orders/analyze", files=upload_pair(),
        data={"enable_muse_semantics": "false", "enable_cloud_sam": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["physical_attributes"]["weight_g"] is None
    assert any("not integrated" in msg for msg in body["global_warnings"])


def test_explicit_camera_configuration(tmp_path, monkeypatch):
    cfg = tmp_path / "camera.json"
    cfg.write_text(json.dumps({
        "camera_matrix": [[700, 0, 50], [0, 700, 40], [0, 0, 1]],
        "dist_coeffs": [0, 0, 0, 0, 0],
        "image_size_wh": [100, 80],
    }), encoding="utf-8")
    monkeypatch.setenv("OPTIPACK_CAMERA_PROFILE_PATH", str(cfg))
    get_cv_service.cache_clear()
    try:
        instance = get_cv_service()
        assert isinstance(instance, orders.CVMetrologyService)
        assert instance.image_size_px == (100, 80)
        assert get_cv_service() is instance
    finally:
        get_cv_service.cache_clear()


def test_crop_encoder_preserves_binding_to_cv_item():
    image = np.zeros((80, 100, 3), dtype=np.uint8)
    item = fake_batch().items[0]
    crops = encode_semantic_crops(image, [item])
    assert len(crops) == 1
    assert crops[0]["item_id"] == item.item_id
    assert crops[0]["bbox_xyxy"] == item.visual_evidence.bbox_2d_px
    assert cv2.imdecode(
        np.frombuffer(crops[0]["crop_bytes"], np.uint8), cv2.IMREAD_COLOR,
    ).shape[:2] == (50, 55)

def test_crop_url_is_normalized_even_when_muse_is_disabled(client):
    class CVWithCrop(FakeCV):
        def process_pair(self, *args, **kwargs):
            batch = super().process_pair(*args, **kwargs)
            batch.items[0].visual_evidence.crop_url = "/static/crops/item_demo.jpg"
            return batch

    app.dependency_overrides[get_cv_service] = lambda: CVWithCrop()
    response = client.post(
        "/api/v1/orders/analyze",
        files=upload_pair(),
        data={"enable_muse_semantics": "false"},
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["visual_evidence"]["crop_url"] == (
        "/api/v1/assets/crops/item_demo.jpg"
    )


def test_invalid_camera_profile_fails_explicitly(tmp_path, monkeypatch):
    from fastapi import HTTPException
    profile = tmp_path / "invalid_camera_profile.json"
    profile.write_text('{"not_a_camera_matrix": true}', encoding="utf-8")
    monkeypatch.setenv("OPTIPACK_CAMERA_PROFILE_PATH", str(profile))
    monkeypatch.delenv("OPTIPACK_CAMERA_PROFILE_NAME", raising=False)
    get_cv_service.cache_clear()
    try:
        with pytest.raises(HTTPException) as raised:
            get_cv_service()
        assert raised.value.status_code == 503
        assert "Camera calibration profile" in raised.value.detail
    finally:
        get_cv_service.cache_clear()


def test_png_upload_accepted_with_valid_header(client):
    image = np.zeros((80, 100, 3), np.uint8)
    ok, png = cv2.imencode(".png", image)
    assert ok
    response = client.post(
        "/api/v1/orders/analyze",
        files={"top_image": ("top.png", png.tobytes(), "image/png")},
        data={"capture_mode": "zenith_only"},
    )
    assert response.status_code == 200
    assert response.json()["items"] == []

def test_real_aruco_failure_is_fail_closed_not_fixture_data(client):
    instance = orders.CVMetrologyService(
        np.array([[700., 0., 50.], [0., 700., 40.], [0., 0., 1.]]),
        np.zeros(5),
        image_size_px=(100, 80),
    )
    app.dependency_overrides[get_cv_service] = lambda: instance
    blank = np.zeros((80, 100, 3), dtype=np.uint8)
    jpg = cv2.imencode(".jpg", blank)[1].tobytes()
    response = client.post(
        "/api/v1/orders/analyze",
        files=upload_pair(top=jpg, ob=jpg),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == []
    assert body["calibration"]["status"] == "uncalibrated"
    assert body["calibration"]["camera_pose_valid"] is False
    assert any("calibration failed" in message for message in body["global_warnings"])
