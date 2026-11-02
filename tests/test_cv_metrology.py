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
