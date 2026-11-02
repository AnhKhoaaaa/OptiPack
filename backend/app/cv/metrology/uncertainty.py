"""Heuristic, locally linearized metrology uncertainty (Issue #8).

The contract calls these fields 1-sigma values; they are NOT statistically
calibrated coverage intervals until tested against repeated physical captures.
We combine local SDF curvature, pixel reprojection uncertainty and matching.
"""
from typing import Dict, List, Tuple

import numpy as np

from backend.app.schemas.contracts import (
    Dimensions3D, ItemUncertainty, MeasurementProvenance,
)
from backend.app.cv.metrology.fitter import FastSDFFitter


def estimate_fit_uncertainty(
    fitter: FastSDFFitter,
    parameters: np.ndarray,
    crop_evidence: List[Dict],
    dimensions: Dimensions3D,
    reprojection_error_px: float,
    scale_mm_per_px: float,
    epipolar_distance_px: float,
    detection_confidence: float,
    height_review_threshold_mm: float = 8.0,
    uncertainty_calibrated: bool = False,
) -> Tuple[ItemUncertainty, MeasurementProvenance, List[str]]:
    """Estimate an uncertainty *proxy*, with conservative degeneracy review.

    Hessian of the SDF pixel residuals is evaluated at the final fit;
    calibration and stereo-association errors provide explicit nonzero floors.
    This is an engineering heuristic, not a calibrated uncertainty distribution.
    """
    p = np.asarray(parameters, dtype=float).reshape(6)
    step = np.array([0.5, 0.5, 0.5, 0.5, 0.5, 0.005])
    P = np.vstack([p, p + np.eye(6) * step])
    residuals = fitter.evaluate_batch_residual(P, crop_evidence)
    r = residuals[0]
    J = ((residuals[1:] - r[None, :]) / step[:, None]).T
    normal = J.T @ J
    singular = np.linalg.svd(normal, compute_uv=False)
    degenerate = (
        not np.isfinite(singular).all()
        or singular[-1] < 1e-9
        or singular[0] / max(singular[-1], 1e-12) > 1e10
    )
    dof = max(len(r) - 6, 1)
    residual_scale = max(1.0, float(np.sqrt((r @ r) / dof)))
    covariance = (residual_scale ** 2) * np.linalg.pinv(normal, rcond=1e-10)
    local_sigma = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    # 1-pixel reprojection error corresponds to this approximate world distance
    # near the calibration plane; height is less constrained than the footprint.
    reproj_floor = max(1.0, float(reprojection_error_px)) * max(float(scale_mm_per_px), 0.01)
    match_floor = max(0.0, float(epipolar_distance_px)) * max(float(scale_mm_per_px), 0.01)
    L, W, H = dimensions.length_mm, dimensions.width_mm, dimensions.height_mm
    sigma_l = max(2.0, float(max(local_sigma[2], local_sigma[3])), 2.0 * reproj_floor, 0.015 * L)
    sigma_w = max(2.0, float(min(local_sigma[2], local_sigma[3])), 2.0 * reproj_floor, 0.015 * W)
    sigma_h = max(4.0, float(local_sigma[4]), 4.0 * reproj_floor, match_floor, 0.04 * H)
    warnings = []
    if degenerate:
        sigma_h = max(sigma_h, 25.0)
        warnings.append("Ill-conditioned 3D fit; height uncertainty unreliable")
    if np.any(p[2:5] < 16.0) or np.any(p[2:5] > 299.0):
        sigma_h = max(sigma_h, 20.0)
        warnings.append("3D dimensions near fitter bounds")
    if not np.isfinite([sigma_l, sigma_w, sigma_h]).all():
        raise ValueError("Invalid uncertainty estimate from SDF fit")
    confidence = float(np.clip(
        float(detection_confidence) * np.exp(-epipolar_distance_px / 150.0)
        * np.exp(-residual_scale / 20.0), 0.0, 1.0
    ))
    if confidence < .4:
        warnings.append("Low combined detection/matching/fitting confidence")
    # A covariance proxy can look deceptively precise for a biased fit. Until
    # repeated independent physical measurements validate its coverage, review
    # is mandatory regardless of the fitted numerical sigma.
    if not uncertainty_calibrated:
        warnings.append("Uncertainty proxy not calibrated on independent captures")
    needs_review = bool(
        sigma_h > height_review_threshold_mm or confidence < .4
        or not uncertainty_calibrated
    )
    uncertainty = ItemUncertainty(
        length_sigma_mm=round(sigma_l, 2),
        width_sigma_mm=round(sigma_w, 2),
        height_sigma_mm=round(sigma_h, 2),
        safety_margin_mm=int(np.ceil(max(5.0, 2.0 * max(sigma_l, sigma_w, sigma_h)))),
    )
    provenance = MeasurementProvenance(
        xy_method="aruco_two_view_sdf_fit",
        z_method="parallax_initializer_dual_view_sdf",
        confidence_score=round(confidence, 4),
        requires_user_review=needs_review,
    )
    return uncertainty, provenance, warnings
