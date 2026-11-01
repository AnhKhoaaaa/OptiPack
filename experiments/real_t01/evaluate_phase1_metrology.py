"""Issue #8: independent two-view measurement quality evaluation.

Reference mode uses annotated masks to isolate regression in the migrated V3
geometry; automatic mode discovers masks with YOLOE (no ROI JSON during
inference). Physical ground truth is loaded only AFTER predictions to score.
"""
from argparse import ArgumentParser
import json
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from backend.app.cv.service import CVMetrologyService, PairCalibration
from backend.app.cv.segmentation.pipeline import PairSegmentation, SegmentationPipeline
from backend.app.cv.segmentation.detector import YOLOESegmenter
from backend.app.schemas.contracts import CalibrationInfo
from experiments.real_t01.calibrate_dataset import load_landscape

HERE = Path(__file__).resolve().parent
GT_DIR = HERE / "golden_masks"
TRIALS = ("Trial01", "Trial02", "Trial03")


def as_pose(values, K, D):
    pose = {
        key: np.asarray(values[key], dtype=np.float64)
        for key in ("rvec", "tvec", "R", "camera_center_mm")
    }
    pose["camera_matrix"], pose["dist_coeffs"] = K, D
    return pose


def metadata_calibration(metadata, trial, K, D):
    def one(view):
        a = metadata["poses"][f"{trial}_{view}.JPG"]
        pose = as_pose(a, K, D)
        info = CalibrationInfo(
            status="calibrated", detected_markers_count=a["detected_markers_count"],
            reprojection_error_px=a["reprojection_rmse_px"],
            scale_mm_per_px_at_z0=a["scale_mm_per_px_at_z0"],
            camera_pose_valid=a["camera_pose_valid"],
        )
        return info, pose
    top_info, top_pose = one("topdown")
    ob_info, ob_pose = one("Oblique")
    H = CVMetrologyService._ground_homography_oblique_to_top(K, top_pose, ob_pose)
    return PairCalibration(top_info, ob_info, top_pose, ob_pose, H)


def item_from_mask(path):
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(path)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        raise ValueError(f"Empty reference mask: {path}")
    cnt = max(contours, key=cv2.contourArea).reshape(-1, 2).astype(float)
    x, y, w, h = cv2.boundingRect(cnt.astype(np.float32))
    return {
        "mask": mask, "contour": cnt, "bbox": [x, y, x + w, y + h],
        "center": [x + w / 2, y + h / 2], "confidence": 1.0,
        "item_id": path.stem.rsplit("__", 1)[-1],
    }


def annotated_pair(trial):
    top = [item_from_mask(p) for p in sorted(GT_DIR.glob(f"{trial}_topdown__*.png"))]
    ob = [item_from_mask(p) for p in sorted(GT_DIR.glob(f"{trial}_Oblique__*.png"))]
    return PairSegmentation(top, ob, [])


def reference_identity(candidate, gt_paths, min_iou=.5):
    """Identity lookup for evaluation only; no GT touches the measurement."""
    prediction = candidate["mask"]
    best_name, best_iou = None, 0.0
    for path in gt_paths:
        gt_mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if gt_mask is None:
            continue
        overlap = cv2.countNonZero(cv2.bitwise_and(prediction, gt_mask))
        total = cv2.countNonZero(prediction) + cv2.countNonZero(gt_mask) - overlap
        iou = float(overlap / total) if total else 0.0
        if iou > best_iou:
            best_name, best_iou = path.stem.rsplit("__", 1)[-1], iou
    return best_name if best_iou >= min_iou else None


def evaluate(trials, mode, model, imgsz, tiles):
    profile = json.loads((HERE / "calibration_model_variants.json").read_text())["free_tangent"]
    K = np.asarray(profile["camera_matrix"], dtype=np.float64)
    D = np.asarray(profile["dist_coeffs"], dtype=np.float64)
    service = CVMetrologyService(K, D, image_size_px=(4032, 3024))
    seg_pipe = SegmentationPipeline(
        segmenter=YOLOESegmenter(model_path=model, imgsz=imgsz, tiled_inference=tiles)
    ) if mode == "automatic" else None
    meta = json.loads((GT_DIR / "metadata.json").read_text()) if mode == "annotated" else None
    rows = []
    for trial in trials:
        t0 = perf_counter()
        if mode == "annotated":
            calibration = metadata_calibration(meta, trial, K, D)
            segmentation = annotated_pair(trial)
        else:
            top_img = load_landscape(HERE / "images" / f"{trial}_topdown.JPG")
            ob_img = load_landscape(HERE / "images" / f"{trial}_Oblique.JPG")
            calibration = service.calibrate_pair(top_img, ob_img)
            segmentation = seg_pipe.run(top_img, ob_img, calibration, save_crops=False)
        batch = service.measure_segmented_pair(calibration, segmentation)
        wall_time_ms = round((perf_counter() - t0) * 1000, 1)

        # Evaluation barrier: only now read names and physical GT.
        ground_truth = json.loads((GT_DIR / "metadata.json").read_text())[
            "ground_truth_dimensions_mm"
        ]
        tops = sorted(GT_DIR.glob(f"{trial}_topdown__*.png"))
        obs = sorted(GT_DIR.glob(f"{trial}_Oblique__*.png"))
        matched_physical = set()
        errors_lw, errors_h = [], []
        details = []
        erroneous_associations = 0
        for ti, oi, epi_dist in batch.matched_pairs:
            detected_top = segmentation.top_items[ti]
            detected_ob = segmentation.oblique_items[oi]
            identity_top = reference_identity(detected_top, tops)
            identity_ob = reference_identity(detected_ob, obs)
            expected_id = str(detected_top.get("item_id") or f"item_{ti+1:02d}")
            measurement = next(
                (m for m in batch.items if m.item_id == expected_id), None
            )
            correct_pair = bool(identity_top and identity_top == identity_ob)
            if not correct_pair:
                erroneous_associations += 1
            detail = {
                "top_idx": ti, "oblique_idx": oi,
                "top_gt_identity": identity_top, "oblique_gt_identity": identity_ob,
                "matching_correct": correct_pair, "epi_distance_px": round(epi_dist, 2),
                "measured": measurement is not None,
            }
            if measurement:
                detail["dimensions_mm"] = measurement.dimensions_mm.model_dump()
                detail["uncertainty_mm"] = measurement.uncertainty_mm.model_dump()
                detail["requires_user_review"] = measurement.measurement_provenance.requires_user_review
            if correct_pair and measurement and identity_top not in matched_physical:
                matched_physical.add(identity_top)
                pred = measurement.dimensions_mm
                gt = np.asarray(ground_truth[identity_top], dtype=float)
                pred_lw = sorted((pred.length_mm, pred.width_mm), reverse=True)
                gt_lw = sorted(gt[:2], reverse=True)
                lw = (abs(pred_lw[0] - gt_lw[0]) + abs(pred_lw[1] - gt_lw[1])) / 2
                height_err = abs(pred.height_mm - gt[2])
                errors_lw.append(lw)
                errors_h.append(height_err)
                detail["mae_lw_mm"] = lw
                detail["error_h_mm"] = height_err
            details.append(detail)
        row = {
            "trial": trial, "mode": mode,
            "ground_truth_physical_items": len(ground_truth),
            "top_candidates": len(segmentation.top_items),
            "oblique_candidates": len(segmentation.oblique_items),
            "stereo_matches": len(batch.matched_pairs),
            "measured_item_count": len(batch.items),
            "correctly_measured_physical_items": len(matched_physical),
            "coverage": len(matched_physical) / len(ground_truth),
            "wrong_or_unverifiable_stereo_matches": erroneous_associations,
            "MAE_LW_on_correctly_measured_mm": float(np.mean(errors_lw)) if errors_lw else None,
            "MAE_H_on_correctly_measured_mm": float(np.mean(errors_h)) if errors_h else None,
            "wall_time_ms": wall_time_ms,
            "warnings": batch.warnings, "measurements": details,
            "_errors_lw": errors_lw, "_errors_h": errors_h,
        }
        print("TRIAL", trial, {k: v for k, v in row.items() if k not in ("warnings", "measurements")}, flush=True)
        rows.append(row)

    lw_errors = [e for row in rows for e in row.pop("_errors_lw")]
    h_errors = [e for row in rows for e in row.pop("_errors_h")]
    summary = {
        "mode": mode, "trials": len(rows),
        "total_physical_items": sum(r["ground_truth_physical_items"] for r in rows),
        "correctly_measured_physical_items": sum(r["correctly_measured_physical_items"] for r in rows),
        "measurement_coverage": sum(r["correctly_measured_physical_items"] for r in rows)
        / max(1, sum(r["ground_truth_physical_items"] for r in rows)),
        "wrong_or_unverifiable_stereo_matches": sum(r["wrong_or_unverifiable_stereo_matches"] for r in rows),
        "conditional_MAE_LW_mm": float(np.mean(lw_errors)) if lw_errors else None,
        "conditional_MAE_H_mm": float(np.mean(h_errors)) if h_errors else None,
        "mean_wall_time_ms": float(np.mean([r["wall_time_ms"] for r in rows])),
    }
    return {"summary": summary, "trials": rows,
            "limitations": "T01 development set; uncertainty is an uncalibrated proxy. Annotated mode uses golden masks and saved poses for geometry migration regression only."}


def main():
    parser = ArgumentParser()
    parser.add_argument("--mode", choices=("annotated", "automatic"), default="annotated")
    parser.add_argument("--model", default="yoloe-26n-seg.pt")
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--tiles", action="store_true")
    parser.add_argument("--trial", nargs="+", choices=TRIALS, default=list(TRIALS))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output = args.output or Path(f"experiments/logs/phase1_metrology_{args.mode}.json")
    result = evaluate(args.trial, args.mode, args.model, args.imgsz, args.tiles)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print("SUMMARY", json.dumps(result["summary"]), "OUTPUT", output, flush=True)


if __name__ == "__main__":
    main()
