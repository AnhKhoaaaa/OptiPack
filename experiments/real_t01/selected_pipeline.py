"""Canonical *research* two-view metrology runner selected for OptiPack T01.

Selection: V2 bidirectional silhouette-constrained cuboid fit (CubeSLAM-inspired)
with the best observed planar calibration parameterization: free p1/p2 tangential
distortion (Zhang-style calibration). Explicit manual ROIs and same-session K;
this is NOT a production estimator and CANNOT certify T01 GO.

This runner directly supplies camera intrinsics; no monkeypatching of global
ArUco detector code or overwriting the preexisting default camera profile.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from experiments.real_t01.silhouette_fit import run as run_v2

HERE = Path(__file__).resolve().parent
SELECTED_CALIBRATION = "free_tangent"


def load_selected_intrinsics(path=None):
    """Read and validate development-session K and distortion coefficients.

    The JSON includes experiments with the same eight source photographs; do
    not reuse it for another camera, lens, zoom, resolution, or photo session.
    """
    source = Path(path) if path is not None else HERE / "calibration_model_variants.json"
    options = json.loads(source.read_text(encoding="utf-8"))
    item = options[SELECTED_CALIBRATION]
    if item.get("status") != "NOT_INDEPENDENT_CALIBRATION":
        raise ValueError("Calibration provenance is missing or unexpected")
    K = np.asarray(item["camera_matrix"], dtype=np.float64)
    D = np.asarray(item["dist_coeffs"], dtype=np.float64)
    if K.shape != (3, 3) or D.size not in (4, 5, 8, 12, 14):
        raise ValueError("Invalid candidate camera matrix or distortion dimensions")
    if not np.isfinite(K).all() or not np.isfinite(D).all():
        raise ValueError("Nonfinite camera calibration")
    if K[0, 0] <= 0 or K[1, 1] <= 0 or abs(K[2, 2] - 1) > 1e-6:
        raise ValueError("Nonphysical camera intrinsics")
    if item.get("loo_pass_count", 0) < 8 or len(item.get("frames", [])) != 8:
        raise ValueError("Unverified development-set calibration evidence")
    return K, D


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--calibration", choices=("selected", "baseline"), default="selected",
        help="selected=experimental free-tangent K; baseline=original provisional K",
    )
    args = parser.parse_args(argv)

    if args.calibration == "selected":
        K, D = load_selected_intrinsics()
        intrinsics = (K, D)
        label = "free_tangent_from_same_8_development_photos_NOT_INDEPENDENT"
        result_path = HERE / "selected_pipeline_results.json"
    else:
        intrinsics = None
        label = "baseline_provisional_from_same_8_photos_NOT_INDEPENDENT"
        result_path = HERE / "selected_pipeline_baseline_results.json"

    result = run_v2(
        camera_intrinsics=intrinsics,
        calibration_label=label,
        output_path=result_path,
    )
    if result["status"] != "EXPLORATORY_NOT_T01_GATE":
        raise RuntimeError("Refuse to declare a production T01 pass")
    print(
        "SELECTED RESEARCH PIPELINE:",
        args.calibration,
        "L/W MAE", round(result["overall_xy_mae_mm"], 3),
        "H MAE", round(result["overall_h_mae_mm"], 3),
        "STATUS", result["status"],
        "RESULT", str(result_path),
    )
    return result


if __name__ == "__main__":
    main()
