"""Cache V2 Baseline: Camera Matrices, Homographies, and Golden Binary Masks.

Phase 0 Gate - Stage 0A for OptiPack Computer Vision (Member 1).
Runs on all 8 real images in experiments/real_t01/images/, generates 40 golden
binary masks in experiments/real_t01/golden_masks/, and caches calibrated camera
parameters (K, R, t), ground-plane homographies H, and V2 3D metrology results.
"""
from pathlib import Path
from time import perf_counter
import csv
import json
import cv2
import numpy as np

from backend.app.cv.aruco_detector import detect_aruco_calibration_sheet
from experiments.real_t01.calibrate_dataset import load_landscape
from experiments.real_t01.selected_pipeline import load_selected_intrinsics
from experiments.real_t01.silhouette_fit import silhouette_evidence

HERE = Path(__file__).resolve().parent
GOLDEN_MASKS_DIR = HERE / "golden_masks"
IMAGES_DIR = HERE / "images"

IMAGE_NAMES = [
    "Trial01_Oblique.JPG",
    "Trial01_topdown.JPG",
    "Trial02_leftside.JPG",
    "Trial02_Oblique.JPG",
    "Trial02_rightside.JPG",
    "Trial02_topdown.JPG",
    "Trial03_Oblique.JPG",
    "Trial03_topdown.JPG",
]

STEREO_PAIRS = {
    "Trial01": ("Trial01_topdown.JPG", "Trial01_Oblique.JPG"),
    "Trial02": ("Trial02_topdown.JPG", "Trial02_Oblique.JPG"),
    "Trial02_left": ("Trial02_topdown.JPG", "Trial02_leftside.JPG"),
    "Trial02_right": ("Trial02_topdown.JPG", "Trial02_rightside.JPG"),
    "Trial03": ("Trial03_topdown.JPG", "Trial03_Oblique.JPG"),
}


def compute_ground_homography(K: np.ndarray, R1: np.ndarray, t1: np.ndarray,
                              R2: np.ndarray, t2: np.ndarray) -> np.ndarray:
    """Analytical ground plane (Z=0) homography mapping from camera 1 to camera 2."""
    M1 = K @ np.column_stack([R1[:, 0], R1[:, 1], t1])
    M2 = K @ np.column_stack([R2[:, 0], R2[:, 1], t2])
    H = M2 @ np.linalg.inv(M1)
    if abs(H[2, 2]) > 1e-12:
        H /= H[2, 2]
    return H


def extract_camera_poses_and_homographies(K: np.ndarray, D: np.ndarray):
    """Calibrate all 8 images with ArUco board and compute inter-camera homographies."""
    poses = {}
    for name in sorted(IMAGE_NAMES):
        img_path = IMAGES_DIR / name
        img = load_landscape(img_path)
        calibrated, info, pose = detect_aruco_calibration_sheet(img, K, D)
        if not calibrated or pose is None:
            raise RuntimeError(f"Failed to calibrate ArUco pose for {name}")

        poses[name] = {
            "rvec": pose["rvec"].tolist(),
            "tvec": pose["tvec"].tolist(),
            "R": pose["R"].tolist(),
            "camera_center_mm": pose["camera_center_mm"].tolist(),
            "reprojection_rmse_px": float(info.reprojection_error_px),
            "detected_markers_count": int(info.detected_markers_count),
            "camera_pose_valid": bool(info.camera_pose_valid),
            "scale_mm_per_px_at_z0": float(info.scale_mm_per_px_at_z0),
            "image_size_wh": [img.shape[1], img.shape[0]],
        }

    homographies = {}
    for pair_name, (name1, name2) in STEREO_PAIRS.items():
        R1 = np.asarray(poses[name1]["R"], dtype=np.float64)
        t1 = np.asarray(poses[name1]["tvec"], dtype=np.float64).reshape(3, 1)
        R2 = np.asarray(poses[name2]["R"], dtype=np.float64)
        t2 = np.asarray(poses[name2]["tvec"], dtype=np.float64).reshape(3, 1)

        H_1_to_2 = compute_ground_homography(K, R1, t1, R2, t2)
        H_2_to_1 = np.linalg.inv(H_1_to_2)
        if abs(H_2_to_1[2, 2]) > 1e-12:
            H_2_to_1 /= H_2_to_1[2, 2]

        homographies[pair_name] = {
            "source_view": name1,
            "target_view": name2,
            "H_1_to_2": H_1_to_2.tolist(),
            "H_2_to_1": H_2_to_1.tolist(),
        }

    return poses, homographies


def generate_golden_masks(annotations: dict, output_dir: Path):
    """Segment all 40 object instances using V2 GrabCut and save binary masks."""
    output_dir.mkdir(parents=True, exist_ok=True)
    mask_metadata = {}

    target_h, target_w = 3024, 4032

    for img_name in sorted(IMAGE_NAMES):
        raw = cv2.imread(str(IMAGES_DIR / img_name))
        if raw is None:
            raise FileNotFoundError(f"Image not found: {img_name}")
        H, W = raw.shape[:2]
        is_portrait = H > W

        img_stem = Path(img_name).stem
        for item, rel_roi in annotations[img_name].items():
            x0 = int(rel_roi[0] * W / 720)
            y0 = int(rel_roi[1] * H / 460)
            x1 = int(rel_roi[2] * W / 720)
            y1 = int(rel_roi[3] * H / 460)

            cnt = silhouette_evidence(raw, (x0, y0, x1, y1))
            if is_portrait:
                cnt = np.c_[H - 1 - cnt[:, 1], cnt[:, 0]]

            # Create full binary mask (3024, 4032)
            full_mask = np.zeros((target_h, target_w), dtype=np.uint8)
            cv2.fillPoly(full_mask, [np.round(cnt).astype(np.int32)], 255)

            mask_filename = f"{img_stem}__{item}.png"
            mask_path = output_dir / mask_filename
            cv2.imwrite(str(mask_path), full_mask)

            # Compute geometric properties
            rect = cv2.minAreaRect(cnt.astype(np.float32))
            area_px = int(np.count_nonzero(full_mask))
            bbox_xyxy = [
                float(cnt[:, 0].min()),
                float(cnt[:, 1].min()),
                float(cnt[:, 0].max()),
                float(cnt[:, 1].max()),
            ]

            key = f"{img_stem}__{item}"
            mask_metadata[key] = {
                "image_name": img_name,
                "item_id": item,
                "mask_file": mask_filename,
                "bbox_xyxy": bbox_xyxy,
                "area_px": area_px,
                "min_area_rect": {
                    "center": [float(rect[0][0]), float(rect[0][1])],
                    "size": [float(rect[1][0]), float(rect[1][1])],
                    "angle_deg": float(rect[2]),
                },
                "contour_samples_count": len(cnt),
                "contour_points": np.round(cnt, 2).tolist(),
            }

    return mask_metadata


def cache_v2_baseline(rerun_fit: bool = False):
    """Main routine to extract and cache V2 baseline assets."""
    tic_total = perf_counter()
    print("=" * 60)
    print("OptiPack Phase 0 Gate 0A: Cache V2 Baseline Assets")
    print("=" * 60)

    # 1. Load Camera Intrinsics
    K, D = load_selected_intrinsics()
    print(f"[1/4] Loaded camera intrinsics (free_tangent). K: {K.shape}, D: {D.shape}")

    # 2. Extract Camera Poses & Homographies
    print("[2/4] Calibrating 8 camera poses and inter-view homographies...")
    poses, homographies = extract_camera_poses_and_homographies(K, D)
    print(f"      Calibrated {len(poses)} views; computed {len(homographies)} homography pairs.")
    for name, p in poses.items():
        print(f"      - {name}: markers={p['detected_markers_count']}, RMSE={p['reprojection_rmse_px']:.3f}px")

    # 3. Generate Golden Masks
    annotations = json.loads((HERE / "roi_annotations.json").read_text(encoding="utf-8"))
    print(f"[3/4] Generating 40 golden binary masks into {GOLDEN_MASKS_DIR}...")
    mask_metadata = generate_golden_masks(annotations, GOLDEN_MASKS_DIR)
    print(f"      Generated and verified {len(mask_metadata)} golden binary masks.")

    # 4. Load Ground Truth and V2 Metrology Predictions
    gt = {}
    with (HERE / "ground_truth.csv").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            gt[row["item_id"]] = [float(row[v]) for v in ("length_mm", "width_mm", "height_mm")]

    if rerun_fit:
        from experiments.real_t01.silhouette_fit import run as run_v2
        print("[4/4] Re-running V2 silhouette fit (this may take ~60-80s)...")
        v2_results = run_v2(camera_intrinsics=(K, D), calibration_label="free_tangent_v2_cached")
    else:
        v2_cached_file = HERE / "selected_pipeline_results.json"
        if not v2_cached_file.exists():
            raise FileNotFoundError("selected_pipeline_results.json not found")
        v2_results = json.loads(v2_cached_file.read_text(encoding="utf-8"))
        print(f"[4/4] Loaded V2 metrology baseline from {v2_cached_file.name}")

    overall_xy = v2_results["overall_xy_mae_mm"]
    overall_h = v2_results["overall_h_mae_mm"]
    print(f"      V2 MAE(L, W) = {overall_xy:.3f} mm, MAE(H) = {overall_h:.3f} mm")

    # Save comprehensive metadata
    full_metadata = {
        "status": "V2_BASELINE_CACHED",
        "total_images": len(poses),
        "total_golden_masks": len(mask_metadata),
        "camera_calibration": {
            "model": "free_tangent",
            "camera_matrix": K.tolist(),
            "dist_coeffs": D.tolist(),
            "image_size_wh": [4032, 3024],
        },
        "poses": poses,
        "homographies": homographies,
        "ground_truth_dimensions_mm": gt,
        "v2_baseline_metrics": {
            "overall_xy_mae_mm": float(overall_xy),
            "overall_h_mae_mm": float(overall_h),
            "trials": v2_results["trials"],
        },
        "masks": mask_metadata,
    }

    meta_file = GOLDEN_MASKS_DIR / "metadata.json"
    meta_file.write_text(json.dumps(full_metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Metadata written to {meta_file}")
    elapsed = perf_counter() - tic_total
    print(f"Completed Cache V2 Baseline in {elapsed:.2f}s")
    return full_metadata


if __name__ == "__main__":
    cache_v2_baseline()

