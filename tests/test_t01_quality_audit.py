"""Source-data and anti-overclaim quality regression tests for T01."""
import json
from pathlib import Path
import pytest
from experiments.real_t01.t01_quality_audit import HERE,evaluate

def _read(name):
    return json.loads((HERE/name).read_text(encoding="utf-8"))

def test_quality_audit_must_fail_full_t01_gate():
    result=evaluate(_read("real_results.json"),_read("silhouette_experiment.json"),
                    _read("fast_pose_ablation.json"))
    assert result["status"]=="NOT_PASSED"
    crit=result["criteria"]
    assert crit["marker_detected"]["meets_numeric_threshold"]
    assert not crit["pose_reprojection"]["meets_numeric_threshold"]
    assert crit["xy_mae"]["meets_development_mean"]
    assert crit["h_mae"]["meets_development_mean"]
    assert crit["cpu_pair"]["meets"] is False
    assert crit["fully_automatic_multiobject"]["meets"] is False
    assert crit["independent_camera_calibration"]["meets"] is False
    assert crit["independent_holdout_session"]["meets"] is False
    assert result["uncertain_label_sensitivity"]["xy_mae_mm_excluding_case"]>8.
    assert result["experimental_fast_pose"]["stats"]["pose_pass_count"]==7
    assert len(result["worst_five_xy_errors"])==5

def test_quality_audit_rejects_wrong_dataset_size():
    b=_read("real_results.json")
    e=_read("silhouette_experiment.json")
    e["trials"]["Trial01"]["items"].pop()
    with pytest.raises(ValueError):
        evaluate(b,e)
