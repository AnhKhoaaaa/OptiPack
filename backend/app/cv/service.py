"""OptiPack Phase 1 calibrated two-view CV and 3D metrology facade (#6–#8).

Uses real image pixels and the existing four-marker A4 ArUco detector.
No cached camera poses, manual ROIs, or experiment metadata are inputs.
The homography maps the oblique view to the top view on the Z=0 plane.

Note: The 3x3 planar homography is exact in *undistorted* pixel
coordinates. Raw distorted images require undistortion before warping.
"""
from dataclasses import dataclass
from threading import Lock
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

import numpy as np

from backend.app.cv.aruco_detector import detect_aruco_calibration_sheet
from backend.app.schemas.contracts import (
    CalibrationInfo, Dimensions3D, DetectedItemMeasurement, VisualEvidence,
)
from backend.app.cv.association import EpipolarMatcher
from backend.app.cv.metrology import FastSDFFitter, ClosedFormInitializer
from backend.app.cv.metrology.uncertainty import estimate_fit_uncertainty

if TYPE_CHECKING:
    from backend.app.cv.segmentation.pipeline import PairSegmentation, SegmentationPipeline


class CVCalibrationError(ValueError):
    """Camera-pair geometry is unavailable or insufficiently calibrated."""


@dataclass(frozen=True)
class PairCalibration:
    top_info: CalibrationInfo
    oblique_info: CalibrationInfo
    top_pose: Dict[str, np.ndarray]
    oblique_pose: Dict[str, np.ndarray]
    homography_oblique_to_top: np.ndarray


@dataclass
class CVMeasurementBatch:
    """Measured two-view items and explicit unmatched/malformed item warnings."""
    calibration: PairCalibration
    items: List[DetectedItemMeasurement]
    matched_pairs: List[Tuple[int, int, float]]
    unmatched_top_indices: List[int]
    unmatched_oblique_indices: List[int]
    warnings: List[str]


class CVMetrologyService:
    """Phase 1 CV facade; calibration is wired before segmentation/metrology.

    Both captures must use the same camera intrinsics and image resolution.
    When available, image_size_px=(width, height) additionally validates the
    camera calibration profile against the supplied pixel orientation.
    The service intentionally fails rather than silently treating an
    approximate-FOV pose as calibrated metric geometry.
    """

    def __init__(
        self,
        camera_matrix: np.ndarray,
        dist_coeffs: np.ndarray,
        image_size_px: Optional[Tuple[int, int]] = None,
    ):
        K = np.asarray(camera_matrix, dtype=np.float64)
        D = np.asarray(dist_coeffs, dtype=np.float64).ravel()
        if K.shape != (3, 3) or not np.isfinite(K).all():
            raise ValueError("camera_matrix must be a finite 3x3 matrix")
        if K[0, 0] <= 0 or K[1, 1] <= 0 or not np.isclose(K[2, 2], 1.0):
            raise ValueError("camera_matrix must have positive focal lengths")
        if D.size not in (4, 5, 8, 12, 14) or not np.isfinite(D).all():
            raise ValueError("dist_coeffs must be a finite OpenCV distortion vector")
        if image_size_px is not None:
            if (
                len(image_size_px) != 2
                or any(not isinstance(v, (int, np.integer)) or v <= 0 for v in image_size_px)
            ):
                raise ValueError("image_size_px must be (positive width, positive height)")
            self.image_size_px = (int(image_size_px[0]), int(image_size_px[1]))
        else:
            self.image_size_px = None
        self.K = K.copy()
        self.D = D.copy()
        # Keep the YOLOE checkpoint, text-prompt embeddings and predictors
        # resident between requests. The API should share one service instance.
        self._segmentation_pipeline = None
        self._pipeline_init_lock = Lock()

    @staticmethod
    def _ground_homography_oblique_to_top(
        K: np.ndarray, top_pose: Dict, oblique_pose: Dict
    ) -> np.ndarray:
        """Map oblique -> top on the table plane in undistorted pixel space."""
        def ground_projection(pose: Dict) -> np.ndarray:
            R = np.asarray(pose["R"], dtype=np.float64).reshape(3, 3)
            t = np.asarray(pose["tvec"], dtype=np.float64).reshape(3, 1)
            return K @ np.column_stack((R[:, 0], R[:, 1], t))

        M_top = ground_projection(top_pose)
        M_oblique = ground_projection(oblique_pose)
        if np.linalg.cond(M_oblique) > 1e12:
            raise CVCalibrationError("Oblique ground-plane projection is singular")
        try:
            H = np.linalg.solve(M_oblique.T, M_top.T).T
        except np.linalg.LinAlgError as exc:
            raise CVCalibrationError("Cannot calculate ground-plane homography") from exc
        if not np.isfinite(H).all() or abs(H[2, 2]) < 1e-12:
            raise CVCalibrationError("Ground-plane homography is degenerate")
        return H / H[2, 2]

    def calibrate_pair(self, top_image: np.ndarray, oblique_image: np.ndarray) -> PairCalibration:
        """Detect ArUco markers in both views and compute live pair geometry.

        Raises CVCalibrationError when either image lacks an accepted pose.
        The API fallback policy belongs to Phase 2, not this geometry layer.
        """
        for label, image in (("top", top_image), ("oblique", oblique_image)):
            if not isinstance(image, np.ndarray) or image.ndim not in (2, 3) or image.size == 0:
                raise ValueError(f"{label}_image must be a non-empty numpy image")
        if top_image.shape[:2] != oblique_image.shape[:2]:
            raise ValueError("Pair images must have the same resolution for shared intrinsics")
        if self.image_size_px is not None:
            actual_size_px = (top_image.shape[1], top_image.shape[0])
            if actual_size_px != self.image_size_px:
                raise ValueError(
                    f"Image size {actual_size_px} does not match calibration profile "
                    f"{self.image_size_px}; normalize image orientation before calibration"
                )

        calibrated_top, top_info, top_pose = detect_aruco_calibration_sheet(
            top_image, self.K, self.D
        )
        calibrated_ob, ob_info, ob_pose = detect_aruco_calibration_sheet(
            oblique_image, self.K, self.D
        )
        if not calibrated_top or top_pose is None:
            raise CVCalibrationError(
                f"Top view calibration failed: {', '.join(top_info.warnings) or top_info.status}"
            )
        if not calibrated_ob or ob_pose is None:
            raise CVCalibrationError(
                f"Oblique view calibration failed: {', '.join(ob_info.warnings) or ob_info.status}"
            )

        H = self._ground_homography_oblique_to_top(self.K, top_pose, ob_pose)
        return PairCalibration(
            top_info=top_info,
            oblique_info=ob_info,
            top_pose=top_pose,
            oblique_pose=ob_pose,
            homography_oblique_to_top=H,
        )

    def measure_segmented_pair(
        self,
        calibration: PairCalibration,
        segmentation: "PairSegmentation",
        *,
        max_epipolar_dist_px: float = 150.0,
        height_review_threshold_mm: float = 8.0,
        max_fit_iterations: int = 6,
    ) -> CVMeasurementBatch:
        """Associate independently detected masks and fit valid two-view cuboids.

        No manual ROI/ground-truth file is read; unmatched items are reported,
        not assigned fabricated dimensions. Input masks use raw camera pixels.
        """
        if max_epipolar_dist_px <= 0 or height_review_threshold_mm <= 0:
            raise ValueError("Matching and review thresholds must be positive")
        if max_fit_iterations < 1:
            raise ValueError("max_fit_iterations must be positive")
        top = segmentation.top_items
        oblique = segmentation.oblique_items
        warnings = list(segmentation.warnings)
        matcher = EpipolarMatcher(max_epipolar_dist_px=max_epipolar_dist_px)
        fitter = FastSDFFitter(self.K, self.D)
        matches = matcher.match_views(
            top, oblique, calibration.top_pose, calibration.oblique_pose,
            self.K, self.D,
        )
        matched_top = {i for i, _, _ in matches}
        matched_oblique = {j for _, j, _ in matches}
        unmatched_top = sorted(set(range(len(top))) - matched_top)
        unmatched_oblique = sorted(set(range(len(oblique))) - matched_oblique)
        if unmatched_top:
            warnings.append(f"{len(unmatched_top)} top-view detections lack stereo partners")
        if unmatched_oblique:
            warnings.append(f"{len(unmatched_oblique)} oblique detections lack stereo partners")
        result_items = []
        for top_idx, ob_idx, epi_dist in matches:
            item_top, item_ob = top[top_idx], oblique[ob_idx]
            try:
                contour_top = np.asarray(item_top["contour"], dtype=np.float64).reshape(-1, 2)
                contour_ob = np.asarray(item_ob["contour"], dtype=np.float64).reshape(-1, 2)
                if len(contour_top) < 3 or len(contour_ob) < 3:
                    raise ValueError("Contour requires at least three vertices")
                p0 = ClosedFormInitializer.compute_initial_guess(
                    contour_top, contour_ob,
                    calibration.top_pose, calibration.oblique_pose, self.K, self.D,
                )
                if not np.isfinite(p0).all():
                    raise ValueError("3D initializer returned nonfinite values")
                crops = [
                    fitter.prepare_crop_evidence(
                        item_top["mask"], contour_top, calibration.top_pose
                    ),
                    fitter.prepare_crop_evidence(
                        item_ob["mask"], contour_ob, calibration.oblique_pose
                    ),
                ]
                fitted, cost = fitter.fit_cuboid(
                    p0, crops, max_iter=max_fit_iterations
                )
                if not np.isfinite(fitted).all() or not np.isfinite(cost):
                    raise ValueError("3D fit returned nonfinite values")
                if np.any(fitted[2:5] <= 0):
                    raise ValueError("3D fit returned nonpositive dimensions")
                length, width = sorted((float(fitted[2]), float(fitted[3])), reverse=True)
                dims = Dimensions3D(
                    length_mm=max(1, int(round(length))),
                    width_mm=max(1, int(round(width))),
                    height_mm=max(1, int(round(float(fitted[4])))),
                )
                probs = [
                    float(c) for c in (
                        item_top.get("confidence"), item_ob.get("confidence")
                    ) if c is not None
                ]
                detection_confidence = min(probs) if probs else 0.7
                reproj_px = max(
                    calibration.top_info.reprojection_error_px,
                    calibration.oblique_info.reprojection_error_px,
                )
                uncertainty, provenance, fit_warnings = estimate_fit_uncertainty(
                    fitter, fitted, crops, dims,
                    reprojection_error_px=reproj_px,
                    scale_mm_per_px=calibration.top_info.scale_mm_per_px_at_z0,
                    epipolar_distance_px=epi_dist,
                    detection_confidence=detection_confidence,
                    height_review_threshold_mm=height_review_threshold_mm,
                )
                # A review flag includes unsafe measurements, not only low H confidence.
                if fit_warnings:
                    warnings.extend(
                        f"Top detection {top_idx}: {msg}" for msg in fit_warnings
                    )
                bbox = [int(v) for v in item_top["bbox"]]
                item_id = str(item_top.get("item_id") or f"item_{top_idx + 1:02d}")
                result_items.append(DetectedItemMeasurement(
                    item_id=item_id,
                    display_name=str(item_top.get("class_name") or "Detected object"),
                    category="general_box",
                    dimensions_mm=dims,
                    uncertainty_mm=uncertainty,
                    measurement_provenance=provenance,
                    visual_evidence=VisualEvidence(
                        bbox_2d_px=bbox,
                        crop_url=item_top.get("crop_url"),
                    ),
                ))
            except (ValueError, KeyError, TypeError, FloatingPointError, np.linalg.LinAlgError) as exc:
                warnings.append(
                    f"3D metrology failed for top index {top_idx} / "
                    f"oblique index {ob_idx}: {exc}"
                )
        return CVMeasurementBatch(
            calibration=calibration,
            items=result_items,
            matched_pairs=matches,
            unmatched_top_indices=unmatched_top,
            unmatched_oblique_indices=unmatched_oblique,
            warnings=warnings,
        )

    def analyze_pair(
        self,
        top_image: np.ndarray,
        oblique_image: np.ndarray,
        *,
        segmentation_pipeline: Optional["SegmentationPipeline"] = None,
        save_crops: bool = True,
        filter_ground_plane: bool = True,
        **measurement_options,
    ) -> CVMeasurementBatch:
        """Complete #6 -> #7 -> #8 live-image pipeline.

        YOLOE checkpoint loading is deferred to segmentation inference.
        No ROI annotation JSON is accepted by this interface.
        """
        from backend.app.cv.segmentation.pipeline import SegmentationPipeline

        calibration = self.calibrate_pair(top_image, oblique_image)
        if segmentation_pipeline is None:
            # Lazy one-time initialization, safe under concurrent API requests.
            # Explicit injected pipelines remain request-local and unchanged.
            with self._pipeline_init_lock:
                if self._segmentation_pipeline is None:
                    self._segmentation_pipeline = SegmentationPipeline()
                pipeline = self._segmentation_pipeline
        else:
            pipeline = segmentation_pipeline
        segmentation = pipeline.run(
            top_image, oblique_image, calibration,
            save_crops=save_crops, filter_ground_plane=filter_ground_plane,
        )
        return self.measure_segmented_pair(
            calibration, segmentation, **measurement_options
        )
    def process_pair(
        self,
        top_image: np.ndarray,
        oblique_image: np.ndarray,
        **kwargs,
    ) -> CVMeasurementBatch:
        """Stable Phase 2-facing alias for the full live two-image pipeline.

        Ingestion/AI enrichment is implemented by the #21 API integration;
        this call returns measured CV items only, not OrderAnalysisResponse.
        """
        return self.analyze_pair(top_image, oblique_image, **kwargs)
