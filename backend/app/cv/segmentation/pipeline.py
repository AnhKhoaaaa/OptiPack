"""Two-view segmentation / crop facade using Meta SAM 3.1 & YOLOE fallback.

ROI discovery uses autonomous model predictions, never preannotated bounding boxes.
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
    """SAM 3.1 (Async Parallel) -> Workspace filter -> Parallax -> RGB crops.

    Falls back automatically to local YOLOESegmenter if SAM 3.1 is unavailable.
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
                    top = fut_top.result(timeout=15.0)
                    oblique = fut_ob.result(timeout=15.0)

                if not top or not oblique:
                    raise RuntimeError("sam-3.1 returned empty candidate list")
            except Exception as exc:
                warnings.append(f"sam-3.1 unavailable ({exc}); falling back to local YOLOE segmenter")
                top = self._fallback.detect_and_segment(top_image, K, D, calibration.top_pose)
                oblique = self._fallback.detect_and_segment(oblique_image, K, D, calibration.oblique_pose)
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
