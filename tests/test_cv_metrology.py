"""Regression checks for real ArUco pixel detection + synthetic-only geometry."""
from pathlib import Path
import json

import cv2
import numpy as np
import pytest

from backend.app.cv.aruco_detector import (
    detect_aruco_calibration_sheet, marker_world_corners)
from experiments.synthetic_t01.benchmark import (
    evaluate, detect_synthetic_box_top, infer_synthetic_box_size)

BASE = Path(__file__).resolve().parents[1] / "experiments" / "synthetic_t01"
META = json.loads((BASE/"ground_truth.json").read_text(encoding="utf-8"))
K = np.asarray(META["camera_intrinsic_K"], np.float64)
D = np.asarray(META["distortion_coefficients"], np.float64)


def image(which):
    result = cv2.imread(str(BASE / f"optipack_synthetic_{which}.png"))
    assert result is not None, "Regenerate test images with generate_fixture.py"
    return result


@pytest.mark.parametrize("which", ["top", "oblique"])
def test_aruco_real_pixel_detection_and_reprojection(which):
    calibrated, info, pose = detect_aruco_calibration_sheet(image(which), K, D)
    assert calibrated
    assert info.status == "calibrated"
    assert info.detected_markers_count == 4
    assert info.reprojection_error_px <= 2.5
    assert info.camera_pose_valid
    assert pose is not None
    assert pose["image_points_px"].shape == (16, 2)


def test_marker_layout_in_mm():
    assert np.array_equal(marker_world_corners(0)[0], [0, 40, 0])
    assert np.array_equal(marker_world_corners(1)[2], [277, 0, 0])
    assert np.array_equal(marker_world_corners(2)[1], [277, 190, 0])


def test_blank_image_fails_without_fake_calibration():
    calibrated, info, pose = detect_aruco_calibration_sheet(np.zeros((600, 800, 3), np.uint8), K)
    assert not calibrated
    assert info.status == "uncalibrated"
    assert info.detected_markers_count == 0
    assert not info.camera_pose_valid
    assert pose is None


def test_unknown_intrinsics_not_falsely_certified():
    calibrated, info, pose = detect_aruco_calibration_sheet(image("top"))
    assert not calibrated
    assert info.status == "uncalibrated"
    assert any("intrinsics" in msg.lower() for msg in info.warnings)
    assert pose is not None


def test_synthetic_box_face_is_extracted_from_pixels():
    for view in ("top", "oblique"):
        observed = detect_synthetic_box_top(image(view))
        assert observed.shape == (4, 2)


def test_synthetic_dimension_recovery_and_provenance():
    result = evaluate()
    assert result["dataset_type"] == "synthetic"
    assert result["real_world_phase0_pass"] is False
    assert result["synthetic_regression_pass"] is True
    assert result["footprint_mae_mm"] <= 8
    assert result["height_mae_mm"] <= 12
    assert result["cpu_latency_ms_per_pair"] <= 800
    assert max(result["reprojection_rmse_px"]) <= 2.5

# Phase 1 Issue #8 production-facade regression tests.
from backend.app.cv.association import EpipolarMatcher
from backend.app.cv.metrology import ClosedFormInitializer, FastSDFFitter
from backend.app.cv.service import CVMetrologyService, PairCalibration
from backend.app.cv.segmentation.pipeline import PairSegmentation
from backend.app.schemas.contracts import (
    CalibrationInfo, DetectedItemMeasurement, Dimensions3D,
)


def test_hungarian_assignment_not_greedy():
    # Greedy takes (0,0)=1, then (1,1)=100. Global solution costs 2+2.
    costs = np.array([[1.0, 2.0], [2.0, 100.0]])
    assert sorted(EpipolarMatcher._hungarian_assignment(costs)) == [(0, 1), (1, 0)]


def test_matcher_never_forces_unrelated_views():
    K_small = np.array([[800., 0, 150], [0, 800., 150], [0, 0, 1]])
    pose = {"rvec": np.array([[np.pi], [0.], [0.]]),
            "tvec": np.array([[0.], [0.], [600.]])}
    matcher = EpipolarMatcher(max_epipolar_dist_px=30.)
    assert matcher.match_views(
        [{"center": [150, 150]}], [{"center": [5000, 5000]}],
        pose, pose, K_small, np.zeros(5)
    ) == []


def _fake_pair_calibration():
    from cv2 import Rodrigues
    rvec = np.array([[np.pi], [0.], [0.]])
    R, _ = Rodrigues(rvec)
    center = np.array([[0.], [0.], [500.]])
    tvec = -R @ center
    pose = {
        "rvec": rvec, "tvec": tvec, "R": R,
        "camera_center_mm": center.ravel(),
        "camera_matrix": np.array([[800., 0., 150.], [0., 800., 150.], [0., 0., 1.]]),
        "dist_coeffs": np.zeros(5),
    }
    info = CalibrationInfo(
        status="calibrated", detected_markers_count=4,
        reprojection_error_px=1.0, scale_mm_per_px_at_z0=0.25,
        camera_pose_valid=True,
    )
    return PairCalibration(info, info, pose, pose, np.eye(3))


def test_metrology_reports_unmatched_and_never_makes_up_dimensions():
    calibration = _fake_pair_calibration()
    service = CVMetrologyService(
        calibration.top_pose["camera_matrix"], np.zeros(5)
    )
    fake_mask = np.zeros((120, 120), np.uint8)
    fake_mask[20:70, 20:70] = 255
    top = {
        "center": [45, 45], "bbox": [20, 20, 70, 70],
        "contour": np.array([[20,20],[70,20],[70,70],[20,70]]),
        "mask": fake_mask, "confidence": 0.9,
    }
    result = service.measure_segmented_pair(
        calibration, PairSegmentation([top], [], [])
    )
    assert result.items == []
    assert result.matched_pairs == []
    assert result.unmatched_top_indices == [0]
    assert any("lack stereo partners" in msg for msg in result.warnings)


def test_legacy_metrology_imports_are_preserved_after_migration():
    from backend.app.cv import (
        estimate_item_dimensions_3d, quantify_measurement_uncertainty
    )
    dims = estimate_item_dimensions_3d([0, 0, 40, 25], .5)
    assert isinstance(dims, Dimensions3D)
    unc, provenance = quantify_measurement_uncertainty(dims, 1.0)
    assert unc.height_sigma_mm > 0
    assert isinstance(provenance.requires_user_review, bool)


def test_fit_uncertainty_review_threshold_with_synthetic_residuals():
    from backend.app.cv.metrology.uncertainty import estimate_fit_uncertainty

    class FakeFitter:
        def evaluate_batch_residual(self, params, evidence):
            # Informative, dimension-dependent residuals; no image allocation.
            return np.column_stack([
                params[:, i] * (1. + i / 10.) for i in range(6)
            ]).repeat(5, axis=1)

    dims = Dimensions3D(length_mm=100, width_mm=65, height_mm=50)
    low, low_prov, _ = estimate_fit_uncertainty(
        FakeFitter(), np.array([0., 0., 100., 65., 50., .1]), [{}],
        dims, 1.0, .25, 2.0, .9, height_review_threshold_mm=1000.0,
    )
    high, high_prov, _ = estimate_fit_uncertainty(
        FakeFitter(), np.array([0., 0., 100., 65., 50., .1]), [{}],
        dims, 1.0, .25, 40.0, .9, height_review_threshold_mm=.1,
    )
    assert np.isfinite(low.height_sigma_mm)
    assert high.height_sigma_mm >= low.height_sigma_mm
    assert high_prov.requires_user_review
    assert low.safety_margin_mm > 0

def test_synthetic_two_view_cuboid_produces_contract_measurement():
    from backend.app.cv.metrology.fitter import batch_model_vertices

    K_small = np.array([[650., 0, 300.], [0., 650., 240.], [0., 0., 1.]])
    D_small = np.zeros(5)

    def make_pose(rvec, camera_xyz):
        R, _ = cv2.Rodrigues(rvec)
        camera = np.asarray(camera_xyz, dtype=float)
        tvec = (-R @ camera).reshape(3, 1)
        return {
            "rvec": rvec, "tvec": tvec, "R": R,
            "camera_center_mm": camera, "camera_matrix": K_small,
            "dist_coeffs": D_small,
        }

    p_top = make_pose(np.array([[np.pi], [0.], [0.]]), [0, 0, 650])
    p_ob = make_pose(np.array([[2.85], [.1], [0.]]), [0, -175, 600])
    vertices = batch_model_vertices(
        np.array([[0., 0., 90., 65., 55., .15]])
    )[0]

    def silhouette(pose):
        pixel, _ = cv2.projectPoints(
            vertices, pose["rvec"], pose["tvec"], K_small, D_small
        )
        hull = cv2.convexHull(pixel.astype(np.float32)).reshape(-1, 2)
        mask = np.zeros((480, 600), np.uint8)
        cv2.fillPoly(mask, [hull.astype(np.int32)], 255)
        x, y, w, h = cv2.boundingRect(hull)
        return {
            "bbox": [x, y, x + w, y + h],
            "center": [x + w / 2, y + h / 2],
            "contour": hull, "mask": mask, "confidence": .9,
        }

    info = CalibrationInfo(
        status="calibrated", detected_markers_count=4,
        reprojection_error_px=.5, scale_mm_per_px_at_z0=.25,
        camera_pose_valid=True,
    )
    calibration = PairCalibration(info, info, p_top, p_ob, np.eye(3))
    measurements = CVMetrologyService(K_small, D_small).measure_segmented_pair(
        calibration,
        PairSegmentation([silhouette(p_top)], [silhouette(p_ob)], []),
    )
    assert len(measurements.matched_pairs) == 1
    assert len(measurements.items) == 1
    item = measurements.items[0]
    assert isinstance(item, DetectedItemMeasurement)
    assert abs(item.dimensions_mm.length_mm - 90) <= 20
    assert abs(item.dimensions_mm.width_mm - 65) <= 20
    assert abs(item.dimensions_mm.height_mm - 55) <= 25
    assert 0 <= item.measurement_provenance.confidence_score <= 1
    assert item.uncertainty_mm.height_sigma_mm >= 4.0
    assert not measurements.unmatched_top_indices

def test_analysis_facade_connects_calibration_segmentation_and_metrology(monkeypatch):
    calibration = _fake_pair_calibration()
    service = CVMetrologyService(
        calibration.top_pose["camera_matrix"], np.zeros(5)
    )
    calls = []

    def stub_calibrate(top, oblique):
        calls.append("calibrate")
        return calibration

    class StubPipeline:
        def run(self, top, oblique, cal, *, save_crops, filter_ground_plane):
            assert cal is calibration
            assert save_crops is False
            calls.append("segment")
            return PairSegmentation([], [], [])

    monkeypatch.setattr(service, "calibrate_pair", stub_calibrate)
    batch = service.analyze_pair(
        np.zeros((5, 5, 3), np.uint8), np.zeros((5, 5, 3), np.uint8),
        segmentation_pipeline=StubPipeline(), save_crops=False,
    )
    assert calls == ["calibrate", "segment"]
    assert not batch.items
    assert not batch.matched_pairs
