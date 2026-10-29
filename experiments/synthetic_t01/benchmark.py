"""Real OpenCV pixel-processing on synthetic fixtures; NOT a real-world T01 PASS.

The color-threshold top-face extractor is intentionally synthetic-scene-specific.
No oracle object corners are passed to the estimator; the calibrated K is known.
"""
from pathlib import Path
import itertools
import json
import sys
import time
import numpy as np
import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.cv.aruco_detector import detect_aruco_calibration_sheet

DATA = Path(__file__).resolve().parent
PERMUTATIONS = np.asarray(list(itertools.permutations(range(4))), dtype=int)


def detect_synthetic_box_top(image: np.ndarray) -> np.ndarray:
    """Extract the blue top-face quadrilateral; calibrated synthetic scene ONLY."""
    b, g, r = cv2.split(image)
    blue_contrast = r.astype(np.int16) - b.astype(np.int16)
    mask = ((blue_contrast > 31) & (r > 190) & (b > 145)).astype(np.uint8) * 255
    mask[:65] = 0  # Exclude synthetic-image provenance banner.
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError("No blue box face detected; no pretend dimensions returned")
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < 2000:
        raise ValueError("Synthetic box top face is too small")
    perimeter = cv2.arcLength(largest, True)
    corners = cv2.approxPolyDP(largest, 0.012 * perimeter, True).reshape(-1, 2)
    if len(corners) != 4:
        raise ValueError(f"Expected 4 top-face corners, detected {len(corners)}")
    return corners.astype(np.float64)


def points_on_plane(corners, pose, z_mm):
    K = pose["camera_matrix"]
    dist = pose["dist_coeffs"]
    rays = cv2.undistortPoints(corners.reshape(-1, 1, 2), K, dist).reshape(-1, 2)
    directions = pose["R"].T @ np.c_[rays, np.ones(len(rays))].T
    center = pose["camera_center_mm"]
    if np.any(np.abs(directions[2]) < 1e-8):
        raise ValueError("Ray parallel to candidate table plane")
    lambdas = (z_mm - center[2]) / directions[2]
    return (center[:, None] + directions * lambdas).T


def match_corners_at_height(top_corners, top_pose, side_corners, side_pose, h):
    a = points_on_plane(top_corners, top_pose, h)
    b = points_on_plane(side_corners, side_pose, h)
    distance_sq = np.sum((a[:, None, :2] - b[None, :, :2]) ** 2, axis=2)
    costs = distance_sq[np.arange(4), PERMUTATIONS].mean(axis=1)
    which = int(np.argmin(costs))
    return float(costs[which]), a, b[PERMUTATIONS[which]]


def infer_synthetic_box_size(corners_a, pose_a, corners_b, pose_b):
    """Fit common top-face plane using only observed contour points in both images."""
    best = None
    # Coarse-to-fine deterministic 1D search (no oracle box dimensions used).
    for height in np.arange(0.0, 251.0, 2.0):
        loss, a, b = match_corners_at_height(corners_a, pose_a, corners_b, pose_b, height)
        if best is None or loss < best[0]:
            best = (loss, height, a, b)
    coarse_h = best[1]
    for height in np.arange(max(0.0, coarse_h-3), coarse_h+3.01, 0.25):
        loss, a, b = match_corners_at_height(corners_a, pose_a, corners_b, pose_b, height)
        if loss < best[0]:
            best = (loss, height, a, b)
    loss, height, a, b = best
    average = (a + b) / 2
    xy_span = average[:, :2].max(axis=0) - average[:, :2].min(axis=0)
    return {"length_mm": float(xy_span[0]),
            "width_mm": float(xy_span[1]),
            "height_mm": float(height),
            "two_view_corner_alignment_rms_mm": float(np.sqrt(loss))}


def evaluate() -> dict:
    metadata = json.loads((DATA/"ground_truth.json").read_text("utf-8"))
    if not metadata.get("synthetic") or metadata.get("real_world_phase0_evidence"):
        raise ValueError("This evaluator is exclusively for synthetic data")
    K = np.asarray(metadata["camera_intrinsic_K"], dtype=np.float64)
    dist = np.asarray(metadata["distortion_coefficients"], dtype=np.float64)
    views = []
    start = time.perf_counter()
    for entry in metadata["images"]:
        frame = cv2.imread(str(DATA / entry["file"]))
        if frame is None:
            raise FileNotFoundError(entry["file"])
        calibrated, info, pose = detect_aruco_calibration_sheet(frame, K, dist)
        if not calibrated or pose is None:
            raise AssertionError(f"ArUco pose check failed: {entry['file']}: {info}")
        corners = detect_synthetic_box_top(frame)
        views.append((corners, pose, info))
    prediction = infer_synthetic_box_size(*views[0][:2], *views[1][:2])
    runtime_ms = (time.perf_counter()-start)*1000
    gt = metadata["box_ground_truth"]
    errors = {name: abs(prediction[name]-float(gt[name]))
              for name in ("length_mm","width_mm","height_mm")}
    footprint_mae = (errors["length_mm"]+errors["width_mm"])/2
    height_mae = errors["height_mm"]
    reprojections = [v[2].reprojection_error_px for v in views]
    passed = (max(reprojections)<=2.5 and footprint_mae<=8 and
              height_mae<=12 and runtime_ms<=800)
    return {"dataset_type":"synthetic",
            "real_world_phase0_pass":False,
            "synthetic_regression_pass":bool(passed),
            "marker_counts":[v[2].detected_markers_count for v in views],
            "reprojection_rmse_px":reprojections,
            "prediction_mm":prediction,
            "ground_truth_mm":{k:gt[k] for k in errors},
            "absolute_errors_mm":errors,
            "footprint_mae_mm":float(footprint_mae),
            "height_mae_mm":float(height_mae),
            "cpu_latency_ms_per_pair":float(runtime_ms),
            "limitations":"Single colored synthetic box; known intrinsics; no real photos, printed board or multi-object segmentation."}


if __name__ == "__main__":
    report = evaluate()
    (DATA/"synthetic_results.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["synthetic_regression_pass"]:
        raise SystemExit(1)
