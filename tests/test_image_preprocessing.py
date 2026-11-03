"""Unit tests for autonomous image preprocessing and adaptive camera scaling."""
import json
import cv2
import numpy as np
import pytest

from backend.app.cv.preprocessing import (
    assess_image_quality,
    normalize_image_orientation,
    preprocess_image_for_cv,
)
from backend.app.cv.aruco_detector import detect_aruco_calibration_sheet
from backend.app.cv.service import CVMetrologyService


def test_normalize_image_orientation():
    # Portrait image (H > W) should be rotated clockwise (W > H)
    portrait = np.zeros((600, 400, 3), dtype=np.uint8)
    landscape = normalize_image_orientation(portrait)
    assert landscape.shape[:2] == (400, 600)

    # Landscape image (W >= H) should remain unchanged
    already_landscape = np.zeros((400, 600, 3), dtype=np.uint8)
    result = normalize_image_orientation(already_landscape)
    assert result.shape[:2] == (400, 600)


def test_assess_image_quality_metrics():
    # Synthetic normal contrast image
    img = np.full((300, 400, 3), 128, dtype=np.uint8)
    cv2.circle(img, (200, 150), 50, (0, 0, 0), -1)
    cv2.rectangle(img, (50, 50), (120, 120), (255, 255, 255), -1)

    quality = assess_image_quality(img)
    assert quality["width_px"] == 400
    assert quality["height_px"] == 300
    assert 50 < quality["mean_brightness"] < 200
    assert quality["contrast_std"] > 20
    assert not quality["is_low_light"]
    assert not quality["is_overexposed"]


def test_preprocess_low_light_enhancement():
    # Very dark image
    dark_img = np.full((300, 400, 3), 30, dtype=np.uint8)
    processed, q = preprocess_image_for_cv(dark_img, auto_enhance=True)
    assert q["is_low_light"] is True
    # Enhanced image should be brighter than original
    assert np.mean(processed) > np.mean(dark_img)


def test_live_camera_resolution_scaling_aruco():
    """Verify that images at 1280x960 calibrate with auto-scaled intrinsics."""
    prof_path = "experiments/real_t01/calibration_model_variants.json"
    with open(prof_path) as f:
        variants = json.load(f)
    prof = variants["free_tangent"]
    K = np.array(prof["camera_matrix"], dtype=float)
    D = np.array(prof["dist_coeffs"], dtype=float)

    img = cv2.imread("experiments/real_t01/images/Trial01_topdown.JPG")
    if img.shape[0] > img.shape[1]:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)

    # Simulate live browser camera at 1280x960
    img_1280 = cv2.resize(img, (1280, 960))
    calibrated, info, pose = detect_aruco_calibration_sheet(img_1280, K, D)

    assert calibrated is True
    assert info.status == "calibrated"
    assert info.reprojection_error_px <= 2.5
    assert info.detected_markers_count >= 3

