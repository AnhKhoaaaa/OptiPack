"""Detect the known OptiPack four-marker A4 board and estimate camera pose.

Coordinates in millimetres; origin at marker 0's lower-left corner.
A measured camera matrix is required for a *calibrated* result. Passing no
camera_matrix uses an approximate FOV solely for diagnostic visualization.
"""
from typing import Dict, Optional, Tuple
import cv2
import numpy as np

from backend.app.schemas.contracts import CalibrationInfo

ARUCO_DICT_ID = "DICT_4X4_50"
ARUCO_MARKER_SIZE_MM = 40.0
# Lower-left XY of each marker on the 297 x 210 mm board.
MARKER_ORIGINS_MM = {0: (0.0, 0.0), 1: (237.0, 0.0),
                     2: (237.0, 150.0), 3: (0.0, 150.0)}


def marker_world_corners(marker_id: int) -> np.ndarray:
    """World corners in OpenCV ArUco detector order: TL, TR, BR, BL."""
    x, y = MARKER_ORIGINS_MM[marker_id]
    s = ARUCO_MARKER_SIZE_MM
    return np.array([[x, y+s, 0], [x+s, y+s, 0],
                     [x+s, y, 0], [x, y, 0]], dtype=np.float64)


def _approx_intrinsics(width: int, height: int) -> np.ndarray:
    """65-degree horizontal FOV assumption: diagnostic, not a calibration."""
    f = width / (2 * np.tan(np.deg2rad(65.0 / 2)))
    return np.array([[f, 0, width/2], 
                     [0, f, height/2],
                     [0, 0, 1.0]], dtype=np.float64)


def _scale_at_table_center(
    K: np.ndarray, dist: np.ndarray, R: np.ndarray, center: np.ndarray,
    width: int, height: int
) -> float:
    """mm per pixel at the principal point on the table plane Z=0."""
    cx, cy = K[0, 2], K[1, 2]
    # Center pixel and an offset pixel along +X
    pts = np.array([[[cx, cy]], [[cx+10.0, cy]]], dtype=np.float64)
    undist = cv2.undistortPoints(pts, K, dist).reshape(-1, 2)
    # Ray in camera coordinates (Z=1), rotated to world coordinates:
    rays_world = (R.T @ np.c_[undist, np.ones(2)].T).T
    # Intersect with world plane Z=0: center + s * ray = [X, Y, 0] => s = -center[2] / ray[2]
    denom = rays_world[:, 2]
    if np.any(np.abs(denom) < 1e-9):
        return 1.0
    s = -center[2] / denom
    if np.any(s <= 0):
        return 1.0
    p0 = center + s[0] * rays_world[0]
    p1 = center + s[1] * rays_world[1]
    return float(np.linalg.norm(p1 - p0) / 10.0)


def detect_aruco_calibration_sheet(
    image: np.ndarray,
    camera_matrix: Optional[np.ndarray] = None,
    dist_coeffs: Optional[np.ndarray] = None,
) -> Tuple[bool, CalibrationInfo, Optional[Dict[str, np.ndarray]]]:
    """Detect marker pixels and estimate world->camera pose via solvePnP.

    Returns (calibrated, Pydantic calibration info, pose dict). An approximate
    unknown-FOV camera can be used for debugging but is NOT marked calibrated.
    """
    if image is None or image.ndim not in (2, 3) or image.size == 0:
        raise ValueError("Image must be a non-empty grayscale or BGR array")
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    parameters = cv2.aruco.DetectorParameters()
    # Subpixel refinement improved real-board LOOCV calibration RMS
    # from 2.13 px to 1.84 px on the T01 capture set.
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    parameters.cornerRefinementWinSize = 5
    corners, ids, _ = cv2.aruco.ArucoDetector(
        dictionary, parameters).detectMarkers(gray)
    detected = [] if ids is None else [int(v) for v in ids.ravel()
                                       if int(v) in MARKER_ORIGINS_MM]
    count = len(set(detected))

    # Adaptive illumination recovery if markers missed due to shadows or low contrast
    if count < 4:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray_enhanced = clahe.apply(gray)
        c_enh, ids_enh, _ = cv2.aruco.ArucoDetector(
            dictionary, parameters).detectMarkers(gray_enhanced)
        det_enh = [] if ids_enh is None else [int(v) for v in ids_enh.ravel()
                                              if int(v) in MARKER_ORIGINS_MM]
        if len(set(det_enh)) > count:
            corners, ids = c_enh, ids_enh
            detected = det_enh
            count = len(set(det_enh))

    warnings = []
    intrinsics_known = camera_matrix is not None
    if not intrinsics_known:
        warnings.append("Camera intrinsics estimated from 65-degree FOV; physical accuracy unverified")
    if count < 2:
        warnings.append("At least two board markers are required for pose estimation")
        info = CalibrationInfo(status="uncalibrated", detected_markers_count=count,
                               reprojection_error_px=0.0, scale_mm_per_px_at_z0=1.0,
                               camera_pose_valid=False, warnings=warnings)
        return False, info, None

    if intrinsics_known:
        K = np.asarray(camera_matrix, dtype=np.float64).reshape(3, 3).copy()
        # Scale intrinsics if the image resolution differs from reference resolution implied by (cx, cy)
        ref_w = K[0, 2] * 2.0
        ref_h = K[1, 2] * 2.0
        if ref_w > 0 and ref_h > 0 and (abs(width - ref_w) > 5 or abs(height - ref_h) > 5):
            ref_long = max(ref_w, ref_h)
            img_long = max(width, height)
            s = img_long / ref_long
            K[0, 0] *= s
            K[1, 1] *= s
            K[0, 2] = width / 2.0
            K[1, 2] = height / 2.0
    else:
        K = _approx_intrinsics(width, height)

    dist = np.asarray(dist_coeffs, dtype=np.float64).ravel() if dist_coeffs is not None else np.zeros(5, dtype=np.float64)
    world_points, image_points = [], []
    for item_corners, marker in zip(corners, ids.ravel()):
        marker = int(marker)
        if marker in MARKER_ORIGINS_MM:
            world_points.extend(marker_world_corners(marker))
            image_points.extend(item_corners.reshape(4, 2))
    obj = np.asarray(world_points, np.float64)
    img = np.asarray(image_points, np.float64)
    success, rvec, tvec = cv2.solvePnP(obj, img, K, dist, flags=cv2.SOLVEPNP_ITERATIVE)
    if not success:
        warnings.append("solvePnP failed")
        info = CalibrationInfo(status="uncalibrated", detected_markers_count=count,
                               reprojection_error_px=0.0, scale_mm_per_px_at_z0=1.0,
                               camera_pose_valid=False, warnings=warnings)
        return False, info, None
    projected, _ = cv2.projectPoints(obj, rvec, tvec, K, dist)
    rmse = float(np.sqrt(np.mean(np.sum((projected.reshape(-1, 2)-img)**2, axis=1))))
    R, _ = cv2.Rodrigues(rvec)
    center = (-R.T @ tvec).ravel()
    physically_valid = np.isfinite(rmse) and np.isfinite(center).all() and center[2] > 0
    threshold_px = max(3.5, 4.0 * (max(width, height) / 1600.0))
    accurate_pose = bool(physically_valid and rmse <= threshold_px and count >= 3)
    if not accurate_pose:
        warnings.append("Pose quality below Phase 0 threshold")
    if count < 4:
        warnings.append("Some reference markers were not detected")
    calibrated = bool(intrinsics_known and accurate_pose)
    scale = _scale_at_table_center(K, dist, R, center, width, height) if physically_valid else 1.0
    info = CalibrationInfo(status="calibrated" if calibrated else "uncalibrated",
                           detected_markers_count=count,
                           reprojection_error_px=max(0.0, rmse),
                           scale_mm_per_px_at_z0=max(1e-8, scale),
                           camera_pose_valid=bool(physically_valid), warnings=warnings)
    pose = {"rvec": rvec, "tvec": tvec, "R": R, "camera_center_mm": center,
            "camera_matrix": K, "dist_coeffs": dist,
            "image_points_px": img, "world_points_mm": obj}
    return calibrated, info, pose
