"""Issue #7 two-view segmentation / crop facade.

ROI discovery uses model predictions, never preannotated bounding boxes.
Requires a live PairCalibration from the ArUco facade (Issue #6).
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np

from backend.app.cv.service import PairCalibration
from backend.app.cv.segmentation.cropping import (
    DEFAULT_CROP_DIR, extract_item_rgb_crop, save_item_rgb_crop,
)
from backend.app.cv.segmentation.detector import YOLOESegmenter
from backend.app.cv.segmentation.parallax_verifier import ParallaxVerifier


@dataclass
class PairSegmentation:
    top_items: List[Dict]
    oblique_items: List[Dict]
    warnings: List[str]


class SegmentationPipeline:
    """YOLOE -> board exclusion -> optional 2-view parallax -> RGB crops.

    Returned masks and boxes are in ORIGINAL input pixel coordinates. For
    parallax only, the images and candidate masks are undistorted because
    PairCalibration's ground homography is defined in undistorted space.
    """

    def __init__(
        self,
        segmenter: Optional[YOLOESegmenter] = None,
        verifier: Optional[ParallaxVerifier] = None,
        crop_dir: Path = DEFAULT_CROP_DIR,
    ):
        self.segmenter = segmenter or YOLOESegmenter()
        self.verifier = verifier or ParallaxVerifier()
        self.crop_dir = Path(crop_dir)

    def run(
        self,
        top_image: np.ndarray,
        oblique_image: np.ndarray,
        calibration: PairCalibration,
        *,
        save_crops: bool = True,
        filter_ground_plane: bool = True,
    ) -> PairSegmentation:
        """Autonomous segmentation of both views, without ROI annotations.

        filter_ground_plane drops top-view candidates rejected by parallax.
        Set False for detector-only ablations (no shadow filtering).
        """
        if top_image.shape[:2] != oblique_image.shape[:2]:
            raise ValueError("Both views must have the same resolution")
        K = np.asarray(calibration.top_pose["camera_matrix"], np.float64)
        D = np.asarray(calibration.top_pose["dist_coeffs"], np.float64)
        top = self.segmenter.detect_and_segment(top_image, K, D, calibration.top_pose)
        oblique = self.segmenter.detect_and_segment(
            oblique_image, K, D, calibration.oblique_pose
        )
        warnings = []
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

        # Deterministic reading order within each view, stable across class labels.
        for items in (top, oblique):
            items.sort(key=lambda item: (round(item["center"][1] / 100), item["center"][0]))
        if save_crops:
            for item in top:
                crop = extract_item_rgb_crop(top_image, item["bbox"])
                item_id, path = save_item_rgb_crop(crop, output_dir=self.crop_dir)
                item["item_id"] = item_id
                item["crop_path"] = str(path)
                # API static mounting is a separate integration responsibility.
                item["crop_url"] = f"/static/crops/{path.name}"
        return PairSegmentation(top_items=top, oblique_items=oblique, warnings=warnings)
