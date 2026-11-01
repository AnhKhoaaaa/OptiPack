"""Independent Phase 1 auto-ROI benchmark on previously annotated T01 images.

Image -> live ArUco calibration -> YOLOE -> parallax -> masks + crops.
The preannotated golden masks are read ONLY AFTER inference for scoring.
This is a development-set regression; not evidence of unseen-image generalization.

Usage:
    python -m experiments.real_t01.evaluate_auto_roi_phase1 --model yoloe-26n-seg.pt
"""
import argparse
import json
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from backend.app.cv.service import CVMetrologyService
from backend.app.cv.segmentation import SegmentationPipeline, YOLOESegmenter
from experiments.real_t01.calibrate_dataset import load_landscape

HERE = Path(__file__).resolve().parent
TRIALS = ("Trial01", "Trial02", "Trial03")


def binary_iou(pred: np.ndarray, gt: np.ndarray) -> float:
    pred = pred > 0
    gt = gt > 0
    intersection = np.count_nonzero(pred & gt)
    union = np.count_nonzero(pred | gt)
    return float(intersection / union) if union else 0.0


def match_masks(predictions: list, targets: list) -> tuple[int, list, int]:
    """Greedy one-to-one ground-truth matching at mask IoU >= 0.5."""
    scored = []
    for pi, pred in enumerate(predictions):
        for gi, gt in enumerate(targets):
            scored.append((binary_iou(pred["mask"], gt), pi, gi))
    scored.sort(reverse=True)
    used_pred, used_gt, matched_iou = set(), set(), []
    for score, pi, gi in scored:
        if score < .5:
            break
        if pi not in used_pred and gi not in used_gt:
            used_pred.add(pi)
            used_gt.add(gi)
            matched_iou.append(round(score, 4))
    return len(matched_iou), matched_iou, len(predictions) - len(used_pred)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="yoloe-26n-seg.pt")
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--conf", type=float, default=0.15)
    parser.add_argument("--tiles", action="store_true", help="Use 2x2 overlapping tiles plus full image")
    parser.add_argument("--trial", choices=TRIALS, nargs="+", default=list(TRIALS))
    parser.add_argument("--skip-parallax", action="store_true")
    parser.add_argument("--save-crops", action="store_true")
    parser.add_argument("--report", type=Path, default=Path("experiments/logs/phase1_auto_roi_metrics.json"))
    args = parser.parse_args()

    # Only intrinsic calibration metadata is needed at inference time.
    profile = json.loads((HERE / "calibration_model_variants.json").read_text())["free_tangent"]
    K = np.asarray(profile["camera_matrix"], dtype=np.float64)
    D = np.asarray(profile["dist_coeffs"], dtype=np.float64)
    cv_service = CVMetrologyService(K, D, image_size_px=(4032, 3024))
    segmentation = SegmentationPipeline(
        segmenter=YOLOESegmenter(model_path=args.model, imgsz=args.imgsz, conf_threshold=args.conf, tiled_inference=args.tiles)
    )
    all_rows = []
    for trial in args.trial:
        top_name = f"{trial}_topdown.JPG"
        ob_name = f"{trial}_Oblique.JPG"
        top = load_landscape(HERE / "images" / top_name)
        ob = load_landscape(HERE / "images" / ob_name)
        calibration = cv_service.calibrate_pair(top, ob)

        t0 = perf_counter()
        result = segmentation.run(
            top, ob, calibration, save_crops=args.save_crops,
            filter_ground_plane=not args.skip_parallax,
        )
        duration_ms = (perf_counter()-t0)*1000
        # Ground-truth masks are deliberately accessed AFTER prediction.
        gt = {}
        for name, expected in ((top_name, result.top_items), (ob_name, result.oblique_items)):
            gt_masks = sorted((HERE / "golden_masks").glob(f"{Path(name).stem}__*.png"))
            targets = [cv2.imread(str(path), cv2.IMREAD_GRAYSCALE) for path in gt_masks]
            if any(mask is None for mask in targets):
                raise FileNotFoundError(f"Failed reading ground truth masks for {name}")
            matched, ious, false_positives = match_masks(expected, targets)
            gt[name] = {
                "gt_count": len(targets), "prediction_count": len(expected),
                "matched_at_iou_0.5": matched, "matched_mask_ious": ious,
                "false_positives": false_positives,
                "recall": matched/max(1, len(targets)),
                "predictions": [
                    {
                        "bbox": item["bbox"],
                        "confidence": item.get("confidence"),
                        "label": item.get("class_name"),
                        "area_px": item["area_px"],
                        "best_mask_iou": round(max([binary_iou(item["mask"], mask) for mask in targets], default=0.0), 4),
                    }
                    for item in expected
                ],
            }
        row = {
            "trial": trial, "latency_ms_for_pair": round(duration_ms, 1),
            "top": gt[top_name], "oblique": gt[ob_name],
            "warnings": result.warnings,
        }
        all_rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    views = [row[view] for row in all_rows for view in ("top", "oblique")]
    total_gt = sum(v["gt_count"] for v in views)
    total_tp = sum(v["matched_at_iou_0.5"] for v in views)
    total_fp = sum(v["false_positives"] for v in views)
    summary = {
        "model": args.model, "imgsz": args.imgsz, "confidence_threshold": args.conf,
        "tiles_enabled": args.tiles,
        "parallax_enabled": not args.skip_parallax,
        "note": "T01 development images only; manual masks used for scoring, not input",
        "total_gt": total_gt, "true_positives": total_tp,
        "false_positives": total_fp,
        "recall_at_mask_iou_0.5": total_tp/max(1, total_gt),
        "mean_pair_latency_ms": round(float(np.mean([r["latency_ms_for_pair"] for r in all_rows])), 1),
    }
    result = {"summary": summary, "scenes": all_rows}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("SUMMARY", json.dumps(summary), "REPORT", args.report, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
