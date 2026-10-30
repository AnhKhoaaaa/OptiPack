"""Tests for curated two-view research pipeline and explicit calibration injection."""
import json
from pathlib import Path

import numpy as np
import pytest

from experiments.real_t01 import paper_two_view
from experiments.real_t01.selected_pipeline import HERE, load_selected_intrinsics


def test_selected_calibration_has_valid_shape_and_provenance():
    K, distortion=load_selected_intrinsics()
    assert K.shape == (3, 3)
    assert distortion.shape in ((5,), (8,), (12,), (14,))
    assert np.isfinite(K).all() and np.isfinite(distortion).all()
    assert K[0, 0] > 0 and K[1, 1] > 0
    assert abs(distortion[2]) + abs(distortion[3]) > 0


def test_invalid_candidate_is_rejected():
    # An isolated temporary folder avoids a Windows pytest basetemp lock.
    from tempfile import TemporaryDirectory
    src=json.loads((HERE/"calibration_model_variants.json").read_text(encoding="utf-8"))
    with TemporaryDirectory(prefix="optipack_calib_test_") as directory:
        p=Path(directory)/"bad_calibration.json"
        src["free_tangent"]["camera_matrix"] = [[0,0,0],[0,0,0],[0,0,1]]
        p.write_text(json.dumps(src),encoding="utf-8")
        with pytest.raises(ValueError,match="Nonphysical"):
            load_selected_intrinsics(p)
        src["free_tangent"]["camera_matrix"] = [[1,0,0],[0,1,0],[0,0,1]]
        src["free_tangent"]["status"]="PASS"
        p.write_text(json.dumps(src),encoding="utf-8")
        with pytest.raises(ValueError,match="provenance"):
            load_selected_intrinsics(p)


def test_intrinsics_injection_validates_bad_shape_without_image_io():
    with pytest.raises(ValueError,match="dimensions"):
        paper_two_view.load_views([],camera_intrinsics=(np.zeros((2,2)),np.zeros(5)))
    with pytest.raises(ValueError,match="Nonphysical"):
        paper_two_view.load_views([],camera_intrinsics=(np.eye(3)*-1,np.zeros(5)))


def test_curated_results_are_not_a_production_gate():
    path=HERE/"selected_pipeline_results.json"
    result=json.loads(path.read_text(encoding="utf-8"))
    baseline=json.loads((HERE/"silhouette_experiment.json").read_text(encoding="utf-8"))
    assert result["status"]=="EXPLORATORY_NOT_T01_GATE"
    assert "NOT_INDEPENDENT" in result["calibration_label"]
    assert len(result["trials"])==3
    assert sum(len(v["items"]) for v in result["trials"].values())==15
    assert result["overall_xy_mae_mm"]<baseline["overall_xy_mae_mm"]
    assert result["overall_h_mae_mm"]<baseline["overall_h_mae_mm"]
    assert result["trials"]["Trial03"]["h_mae_mm"]>baseline["trials"]["Trial03"]["h_mae_mm"]
    assert "NOT PASSED" in (HERE/"REPORT.md").read_text(encoding="utf-8")


def test_historical_camera_profile_remains_conservative():
    original=json.loads((HERE/"camera_profile_estimated.json").read_text(encoding="utf-8"))
    K,dist=load_selected_intrinsics()
    assert original["status"]=="estimated_not_verified"
    assert abs(original["distortion"][2])<1e-12 and abs(original["distortion"][3])<1e-12
    assert abs(dist[2])+abs(dist[3])>0
    assert not np.allclose(K, original["camera_matrix"], atol=1e-5)
