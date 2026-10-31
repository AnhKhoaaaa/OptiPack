"""CI Acceptance Regression Tests for Phase 0 Gate (V3 CV Metrology).

Specification: Research_docs/optipack_phase_implementation_plan.md
Covers Phase 0 Gates:
- Gate 0A: Baseline Freeze and Golden Masks Verification
- Gate 0B: Fast SDF Metrology (Latency < 150ms, MAE <= 8mm/12mm)
- Gate 0C: Auto-Segmentation & Census Parallax Verifier (FP == 0, IoU >= 0.82)
- Gate 0D: Epipolar Hungarian Matching & End-to-End Metrology (Latency < 800ms)
"""
from pathlib import Path
import json
import pytest
import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
EXPERIMENTS_DIR = REPO_ROOT / "experiments" / "real_t01"
GOLDEN_DIR = EXPERIMENTS_DIR / "golden_masks"
METADATA_FILE = GOLDEN_DIR / "metadata.json"
REPORT_FILE = REPO_ROOT / "experiments" / "logs" / "phase0_cv_metrology_v3_report.md"


@pytest.fixture(scope="module")
def metadata():
    assert METADATA_FILE.exists(), "Golden masks metadata.json must exist."
    return json.loads(METADATA_FILE.read_text(encoding="utf-8"))


def test_gate_0a_golden_masks_and_reprojection(metadata):
    """Gate 0A: Verify 40 golden masks and camera poses with RMSE <= 2.5px."""
    assert metadata["total_golden_masks"] == 40
    assert len(metadata["masks"]) == 40

    for mask_id, info in metadata["masks"].items():
        mask_path = GOLDEN_DIR / info["mask_file"]
        assert mask_path.exists(), f"Missing golden mask: {info['mask_file']}"
        assert info["area_px"] > 20000

    for img_name, pose in metadata["poses"].items():
        rmse = pose["reprojection_rmse_px"]
        assert rmse <= 2.50, f"{img_name} RMSE {rmse} > 2.5px"


def test_gate_0b_fast_metrology_accuracy(metadata):
    """Gate 0B: Verify fast SDF metrology satisfies MAE <= 8.0/12.0 mm."""
    from experiments.real_t01.benchmark_v3_gate import run_stage_0b_fast_metrology

    res = run_stage_0b_fast_metrology(metadata, GOLDEN_DIR, num_threads=4)
    assert res["gate_passed"] is True
    assert res["overall_lw_mae_mm"] <= 8.00
    assert res["overall_h_mae_mm"] <= 12.00
    assert res["mean_latency_5_items_ms"] <= 150.0


def test_gate_0c_auto_segmentation_and_parallax_verifier(metadata):
    """Gate 0C: Verify Census parallax shadow rejection (FP=0) and IoU >= 0.82."""
    from experiments.real_t01.benchmark_v3_gate import run_stage_0c_segmentation

    res = run_stage_0c_segmentation(metadata, GOLDEN_DIR, num_threads=4)
    assert res["gate_passed"] is True
    assert res["false_positives"] == 0
    assert res["recall"] >= 0.925
    assert res["mean_iou"] >= 0.82
    assert res["mean_pair_latency_ms"] <= 200.0


def test_gate_0d_end_to_end_autonomous_metrology(metadata):
    """Gate 0D: Verify full autonomous pipeline latency <= 800ms and matching 15/15."""
    from experiments.real_t01.benchmark_v3_gate import run_stage_0d_end_to_end

    res = run_stage_0d_end_to_end(metadata, GOLDEN_DIR, num_threads=4)
    assert res["gate_passed"] is True
    assert res["total_matched"] == 15
    assert res["matching_rate"] == 1.0
    assert res["mae_lw"] <= 8.00
    assert res["mae_h"] <= 12.00
    assert res["mean_pair_latency_ms"] <= 800.0
    assert REPORT_FILE.exists()
