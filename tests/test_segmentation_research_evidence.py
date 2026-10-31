"""Regression checks for development-set class-agnostic proposal evidence.

No inference, no model weights, no optional dependencies or production changes.
"""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]/"experiments"/"real_t01"

def test_segmentation_research_matches_its_raw_results():
    data=json.loads((HERE/"segmentation_fastsam_eval.json").read_text(encoding="utf-8"))
    rows=data["rows"]
    summary=data["summary"]
    assert len(rows)==summary["images"]==8
    assert summary["gt_coarse_rois"]==40
    scores=[r["variants"]["0.2"] for r in rows]
    assert sum(x["recall"] for x in scores)==summary["0.2_recall"]==33
    assert sum(x["top5_recall"] for x in scores)==13
    assert sum(x["top10_recall"] for x in scores)==25
    assert sum(x["top20_recall"] for x in scores)==33
    assert summary["median_cpu_infer_ms"]>800
    assert all(0<=x["top5_recall"]<=x["top10_recall"]<=x["top20_recall"]<=x["recall"]<=5 for x in scores)

def test_research_is_explicitly_not_production_ready():
    text=(HERE/"SEGMENTATION_STUDY.md").read_text(encoding="utf-8")
    assert "NOT PASSED" in text
    assert "NO model / algorithm promoted" in text
    assert "mask" in (HERE/"CAPTURE_PROTOCOL.md").read_text(encoding="utf-8").lower()
