"""Two-view segmentation / crop facade using Meta SAM 3.1, YOLOE, & Classical Contour fallback.

ROI discovery uses autonomous predictions, never preannotated bounding boxes.
Requires a live PairCalibration from the ArUco facade.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from backend.app.cv.service import PairCalibration
from backend.app.cv.segmentation.cropping import (
    DEFAULT_CROP_DIR, extract_item_rgb_crop, save_item_rgb_crop,
)
from backend.app.cv.segmentation.detector import YOLOESegmenter
from backend.app.cv.segmentation.parallax_verifier import ParallaxVerifier
from backend.app.cv.segmentation.sam31_segmenter import SAM31Segmenter


@dataclass
class PairSegmentation:
    top_items: List[Dict[str, Any]]
    oblique_items: List[Dict[str, Any]]
    warnings: List[str]


class SegmentationPipeline:
    """SAM 3.1 (Async Parallel) -> Local YOLOE -> Autonomous Classical Contours -> Parallax -> RGB crops.

    Provides multi-tier resilience:
    1. Meta SAM 3.1 Frontier Segmenter (Meta Model API, zero server GPU memory).
    2. Local YOLOE (if ultralytics & torch are available).
    3. Classical OpenCV Contour Segmentation (zero heavy dependencies, pure CPU, failsafe).
    """

    def __init__(
        self,
        segmenter: Optional[Any] = None,
        verifier: Optional[ParallaxVerifier] = None,
        crop_dir: Path = DEFAULT_CROP_DIR,
    ):
        if segmenter is not None:
            self._primary = segmenter
        else:
            self._primary = SAM31Segmenter()
        self._fallback = YOLOESegmenter(tiled_inference=True)
        self.verifier = verifier or ParallaxVerifier()
        self.crop_dir = Path(crop_dir)

    @property
    def segmenter(self) -> Any:
        return self._primary

    @staticmethod
    def _detect_classical_contours(
        image: np.ndarray,
        K: np.ndarray,
        D: np.ndarray,
        pose: Dict[str, Any],
        min_area_px: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Lightweight OpenCV contour proposal fallback (zero heavy dependencies)."""
        h, w = image.shape[:2]
        board_poly, markers = YOLOESegmenter.get_aruco_exclusion_polygons(K, D, pose)
        board_mask = np.zeros((h, w), np.uint8)
        if board_poly is not None and len(board_poly) > 0:
            cv2.fillPoly(board_mask, [np.rint(board_poly).astype(np.int32)], 255)
        for poly in markers:
            cv2.fillPoly(board_mask, [np.rint(poly).astype(np.int32)], 255)
        board_mask = cv2.dilate(board_mask, np.ones((35, 35), np.uint8))

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (7, 7), 0)

        _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        adapt = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 41, 10)
        fg = cv2.bitwise_or(otsu, adapt)
        fg[board_mask > 0] = 0

        margin_x = int(w * 0.025)
        margin_y = int(h * 0.025)
        fg[:margin_y, :] = 0
        fg[-margin_y:, :] = 0
        fg[:, :margin_x] = 0
        fg[:, -margin_x:] = 0

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        closed = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, kernel, iterations=2)
        opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)), iterations=1)

        contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        found = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area_px or area > 0.40 * h * w:
                continue
            x, y, bw, bh = cv2.boundingRect(c)
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.drawContours(mask, [c], -1, 255, -1)
            found.append({
                "bbox": [x, y, x + bw, y + bh],
                "mask": mask,
                "contour": c.reshape(-1, 2).astype(float),
                "area_px": int(area),
                "center": [x + bw / 2, y + bh / 2],
                "confidence": 0.70,
                "class_name": "item",
                "source": "classical_opencv",
            })
        return found

    def _run_fallback(
        self,
        image: np.ndarray,
        K: np.ndarray,
        D: np.ndarray,
        pose: Dict[str, Any],
        warnings: List[str],
        view_name: str,
    ) -> List[Dict[str, Any]]:
        """Attempt YOLOE fallback; gracefully fall through to classical OpenCV segmentation if unavailable."""
        try:
            res = self._fallback.detect_and_segment(image, K, D, pose)
            if res:
                return res
            warnings.append(f"Local YOLOE segmenter returned empty candidates for {view_name}; using classical contour fallback")
        except Exception as exc:
            warnings.append(f"Local YOLOE segmenter unavailable ({exc}) for {view_name}; using classical contour fallback")
        return self._detect_classical_contours(image, K, D, pose)

    def run(
        self,
        top_image: np.ndarray,
        oblique_image: np.ndarray,
        calibration: PairCalibration,
        *,
        save_crops: bool = True,
        filter_ground_plane: bool = True,
    ) -> PairSegmentation:
        """Autonomous segmentation of both views, without ROI annotations."""
        if top_image.shape[:2] != oblique_image.shape[:2]:
            raise ValueError("Both views must have the same resolution")

        K = np.asarray(calibration.top_pose["camera_matrix"], np.float64)
        D = np.asarray(calibration.top_pose["dist_coeffs"], np.float64)
        warnings: List[str] = []

        top: List[Dict[str, Any]] = []
        oblique: List[Dict[str, Any]] = []

        # 1. Primary segmentation: SAM 3.1 (Parallel) or user-specified segmenter
        if isinstance(self._primary, SAM31Segmenter):
            try:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    fut_top = executor.submit(
                        self._primary.detect_and_segment,
                        top_image, K, D, calibration.top_pose, True
                    )
                    fut_ob = executor.submit(
                        self._primary.detect_and_segment,
                        oblique_image, K, D, calibration.oblique_pose, False
                    )
                    try:
                        top = fut_top.result(timeout=15.0)
                    except Exception as exc_top:
                        warnings.append(f"sam-3.1 top view unavailable ({exc_top}); falling back to local YOLOE segmenter")
                        top = []
                    try:
                        oblique = fut_ob.result(timeout=15.0)
                    except Exception as exc_ob:
                        warnings.append(f"sam-3.1 oblique view unavailable ({exc_ob}); falling back to local YOLOE segmenter")
                        oblique = []

                if not top:
                    warnings.append("sam-3.1 returned empty top candidates; falling back to local YOLOE segmenter for top view")
                    top = self._run_fallback(top_image, K, D, calibration.top_pose, warnings, "top view")
                if not oblique:
                    warnings.append("sam-3.1 returned empty oblique candidates; falling back to local YOLOE segmenter for oblique view")
                    oblique = self._run_fallback(oblique_image, K, D, calibration.oblique_pose, warnings, "oblique view")
            except Exception as exc:
                warnings.append(f"sam-3.1 unavailable ({exc}); falling back to local YOLOE segmenter")
                if not top:
                    top = self._run_fallback(top_image, K, D, calibration.top_pose, warnings, "top view")
                if not oblique:
                    oblique = self._run_fallback(oblique_image, K, D, calibration.oblique_pose, warnings, "oblique view")
        else:
            top = self._primary.detect_and_segment(top_image, K, D, calibration.top_pose)
            oblique = self._primary.detect_and_segment(oblique_image, K, D, calibration.oblique_pose)

        # 2. Planar Parallax verification
        if filter_ground_plane and top:
            top_u = cv2.undistort(top_image, K, D)
            oblique_u = cv2.undistort(oblique_image, K, D)
            parallax = self.verifier.compute_parallax_maps(
                top_u, oblique_u, calibration.homography_oblique_to_top
            )
            verified = []
            for item in top:
                undistorted_mask = cv2.undistort(item["mask"], K, D)
                is_3d, score, details = self.verifier.verify_candidate(
                    undistorted_mask, parallax
                )
                item["parallax_score"] = score
                item["parallax_verified"] = bool(is_3d)
                item["parallax_details"] = details
                if is_3d:
                    verified.append(item)
                else:
                    warnings.append(
                        f"Rejected ground-plane candidate near {item['center']}: "
                        f"{details.get('reason', 'parallax test')}"
                    )
            top = verified

        # Deterministic reading order within each view
        for items in (top, oblique):
            items.sort(key=lambda item: (round(item["center"][1] / 100), item["center"][0]))

        if save_crops:
            for item in top:
                crop = extract_item_rgb_crop(top_image, item["bbox"])
                item_id, path = save_item_rgb_crop(crop, output_dir=self.crop_dir)
                item["item_id"] = item_id
                item["crop_path"] = str(path)
                item["crop_url"] = f"/static/crops/{path.name}"

        return PairSegmentation(top_items=top, oblique_items=oblique, warnings=warnings)
