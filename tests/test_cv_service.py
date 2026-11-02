"""Phase 1 CV facade: real-pixel ArUco pose and live homography regression."""
from pathlib import Path
import json

import cv2
import numpy as np
import pytest

from backend.app.cv.aruco_detector import detect_aruco_calibration_sheet, marker_world_corners
from backend.app.cv.service import CVCalibrationError, CVMetrologyService

FIXTURE = Path(__file__).resolve().parents[1] / "experiments" / "synthetic_t01"
META = json.loads((FIXTURE / "ground_truth.json").read_text(encoding="utf-8"))
K = np.asarray(META["camera_intrinsic_K"], dtype=np.float64)
D = np.asarray(META["distortion_coefficients"], dtype=np.float64)


def _image(view: str) -> np.ndarray:
    image = cv2.imread(str(FIXTURE / f"optipack_synthetic_{view}.png"))
    assert image is not None
    return image


def test_live_calibration_pair_uses_real_marker_pixels():
    service = CVMetrologyService(K, D)
    result = service.calibrate_pair(_image("top"), _image("oblique"))

    assert result.top_info.status == "calibrated"
    assert result.oblique_info.status == "calibrated"
    assert result.top_info.detected_markers_count == 4
    assert result.oblique_info.detected_markers_count == 4
    assert result.homography_oblique_to_top.shape == (3, 3)
    assert np.isfinite(result.homography_oblique_to_top).all()

    # Geometry must map any planar marker world point between views.
    world = marker_world_corners(1)
    projections = []
    for pose in (result.top_pose, result.oblique_pose):
        pixels, _ = cv2.projectPoints(world, pose["rvec"], pose["tvec"], K, D)
        undistorted = cv2.undistortPoints(pixels, K, D, P=K)
        projections.append(undistorted)
    top_px, oblique_px = projections
    mapped = cv2.perspectiveTransform(
        oblique_px.astype(np.float64), result.homography_oblique_to_top
    )
    assert np.max(np.linalg.norm(mapped - top_px, axis=2)) < 0.1


def test_blank_top_does_not_silently_fallback_to_fake_pose():
    service = CVMetrologyService(K, D)
    with pytest.raises(CVCalibrationError, match="Top view"):
        service.calibrate_pair(np.zeros_like(_image("top")), _image("oblique"))


def test_blank_oblique_does_not_silently_fallback_to_fake_pose():
    service = CVMetrologyService(K, D)
    with pytest.raises(CVCalibrationError, match="Oblique view"):
        service.calibrate_pair(_image("top"), np.zeros_like(_image("oblique")))


def test_invalid_calibration_and_image_shape_fail_explicitly():
    with pytest.raises(ValueError, match="3x3"):
        CVMetrologyService(np.eye(2), D)
    with pytest.raises(ValueError, match="dist_coeffs"):
        CVMetrologyService(K, np.ones(3))
    service = CVMetrologyService(K, D)
    with pytest.raises(ValueError, match="same resolution"):
        service.calibrate_pair(_image("top"), _image("oblique")[:50, :50])

# The real T01 profile was fitted on these same images (not independent
# calibration evidence). This is a regression for wiring live image pixels
# into the Phase 1 service; no saved poses or ROI annotations are supplied.
REAL = Path(__file__).resolve().parents[1] / "experiments" / "real_t01"
REAL_PROFILE = json.loads(
    (REAL / "calibration_model_variants.json").read_text(encoding="utf-8")
)["free_tangent"]
REAL_K = np.asarray(REAL_PROFILE["camera_matrix"], dtype=np.float64)
REAL_D = np.asarray(REAL_PROFILE["dist_coeffs"], dtype=np.float64)


def _real_landscape_image(name: str) -> np.ndarray:
    image = cv2.imread(str(REAL / "images" / name))
    assert image is not None
    # Profile intrinsics were fitted on 4032x3024 landscape views.
    return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE) if image.shape[0] > image.shape[1] else image


@pytest.mark.parametrize("trial", ("Trial01", "Trial02", "Trial03"))
def test_real_t01_aruco_pair_and_live_homography(trial):
    service = CVMetrologyService(REAL_K, REAL_D, image_size_px=(4032, 3024))
    result = service.calibrate_pair(
        _real_landscape_image(f"{trial}_topdown.JPG"),
        _real_landscape_image(f"{trial}_Oblique.JPG"),
    )

    for info in (result.top_info, result.oblique_info):
        assert info.status == "calibrated"
        assert info.detected_markers_count == 4
        assert info.reprojection_error_px <= 2.5

    # Homography is valid on the ground plane in UNDISTORTED pixels only.
    ground_points = marker_world_corners(0)
    mapped_pixels = []
    for pose in (result.top_pose, result.oblique_pose):
        pixels, _ = cv2.projectPoints(ground_points, pose["rvec"], pose["tvec"], REAL_K, REAL_D)
        mapped_pixels.append(cv2.undistortPoints(pixels, REAL_K, REAL_D, P=REAL_K))
    projected = cv2.perspectiveTransform(
        mapped_pixels[1].astype(np.float64), result.homography_oblique_to_top
    )
    assert np.max(np.linalg.norm(projected - mapped_pixels[0], axis=2)) < 0.1


def test_calibration_profile_rejects_wrong_capture_orientation():
    raw_portrait = cv2.imread(str(REAL / "images" / "Trial01_topdown.JPG"))
    assert raw_portrait is not None
    assert raw_portrait.shape[:2] == (4032, 3024)
    service = CVMetrologyService(REAL_K, REAL_D, image_size_px=(4032, 3024))
    with pytest.raises(ValueError, match="normalize image orientation"):
        service.calibrate_pair(raw_portrait, raw_portrait)


@pytest.mark.parametrize("bad_size", ((0, 3024), (4032, -1), (4032,), (4032.5, 3024)))
def test_invalid_calibration_profile_image_size_rejected(bad_size):
    with pytest.raises(ValueError, match="image_size_px"):
        CVMetrologyService(REAL_K, REAL_D, image_size_px=bad_size)

def test_three_visible_markers_calibrate_but_two_require_review():
    top = _image("top").copy()
    oblique = _image("oblique")
    ok, _, pose = detect_aruco_calibration_sheet(top, K, D)
    assert ok and pose is not None
    service = CVMetrologyService(K, D)

    for marker_id in (0, 1):
        pixels, _ = cv2.projectPoints(marker_world_corners(marker_id), pose["rvec"], pose["tvec"], K, D)
        x, y, w, h = cv2.boundingRect(pixels.astype(np.float32))
        cv2.rectangle(top, (x - 5, y - 5), (x + w + 5, y + h + 5), (125, 125, 125), -1)
        if marker_id == 0:
            partially_occluded = service.calibrate_pair(top, oblique)
            assert partially_occluded.top_info.detected_markers_count == 3
            assert partially_occluded.top_info.status == "calibrated"

    with pytest.raises(CVCalibrationError, match="Top view"):
        service.calibrate_pair(top, oblique)
