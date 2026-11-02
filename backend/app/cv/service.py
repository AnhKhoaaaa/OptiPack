"""Camera-pair calibration facade for OptiPack Phase 1 (Issue #6).

Uses real image pixels and the existing four-marker A4 ArUco detector.
No cached camera poses, manual ROIs, or experiment metadata are inputs.
The homography maps the oblique view to the top view on the Z=0 plane.

Note: The 3x3 planar homography is exact in *undistorted* pixel
coordinates. Raw distorted images require undistortion before warping.
"""
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np

from backend.app.cv.aruco_detector import detect_aruco_calibration_sheet
from backend.app.schemas.contracts import CalibrationInfo


class CVCalibrationError(ValueError):
    """Camera-pair geometry is unavailable or insufficiently calibrated."""


@dataclass(frozen=True)
class PairCalibration:
    top_info: CalibrationInfo
    oblique_info: CalibrationInfo
    top_pose: Dict[str, np.ndarray]
    oblique_pose: Dict[str, np.ndarray]
    homography_oblique_to_top: np.ndarray


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
