"""Guard experimental calibration models against silent promotion to T01 GO."""
import json
import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from experiments.real_t01.calibration_model_variants import CONFIGS, BASE, fit, HERE
from experiments.real_t01.calibration_metrology_experiment import do_profile

def test_free_tangent_config_only_changes_tangent_constraint():
    assert CONFIGS["free_tangent"] == (BASE & ~cv2.CALIB_ZERO_TANGENT_DIST)
    assert CONFIGS["baseline"] == BASE
    assert CONFIGS["free_tangent"] != BASE

def test_loo_scores_and_pose_are_not_independent_calibration():
    data=json.loads((HERE/"calibration_model_variants.json").read_text(encoding="utf-8"))
    b=data["baseline"]
    t=data["free_tangent"]
    assert t["status"] == "NOT_INDEPENDENT_CALIBRATION"
    assert len(t["frames"]) == 8
    assert len(b["frames"]) == 8
    assert t["loo_pass_count"] == 8
    assert b["loo_pass_count"] == 6
    assert t["loo_mean_px"] < b["loo_mean_px"]
    K=np.array(t["camera_matrix"])
    dist=np.array(t["dist_coeffs"])
    assert K.shape == (3,3) and np.isfinite(K).all()
    assert abs(K[0,0]-K[1,1])<250
    assert abs(dist[2])+abs(dist[3]) < .03

def test_optional_profile_not_applied_to_baseline_file():
    old=json.loads((HERE/"camera_profile_estimated.json").read_text(encoding="utf-8"))
    candidate=json.loads((HERE/"calibration_model_variants.json").read_text(encoding="utf-8"))["free_tangent"]
    assert old["status"]=="estimated_not_verified"
    assert abs(old["distortion"][2]) < 1e-10
    assert abs(candidate["dist_coeffs"][3])>1e-4
    # Variant cannot rewrite the default camera file.
    assert not np.allclose(old["camera_matrix"],candidate["camera_matrix"],atol=1e-4)

def test_calibration_metrology_results_remain_exploratory():
    d=json.loads((HERE/"calibration_metrology_experiment.json").read_text(encoding="utf-8"))
    x=d["free_tangent"]
    assert x["in_sample_pose_pass"] == 8
    assert 0 < x["mean_xy_mm"] < 100
    assert 0 < x["mean_h_mm"] < 100
    assert x["mean_xy_mm"] < 7.90894
    assert x["mean_h_mm"] < 6.11949
    assert len(x["poses"])==8
