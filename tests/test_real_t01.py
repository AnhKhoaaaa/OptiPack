"""Regression tests for reproducible real T01 captures, labels and honest evidence."""
import csv
import hashlib
import json
from pathlib import Path

import cv2
import pytest

from backend.app.cv.aruco_detector import MARKER_ORIGINS_MM
from experiments.real_t01.prepare_dataset import actual_roi

DATA=Path(__file__).resolve().parents[1]/"experiments"/"real_t01"
EXPECTED={"white":(135,45,65),"gocheck":(65,65,30),
          "black":(140,45,70),"paper":(140,80,50),"wood":(75,45,35)}

def test_ground_truth_converted_to_mm():
    with (DATA/"ground_truth.csv").open(encoding="utf-8-sig",newline="") as f:
        rows={r["item_id"]:r for r in csv.DictReader(f)}
    assert set(rows)==set(EXPECTED)
    for key,dims in EXPECTED.items():
        assert tuple(int(rows[key][v]) for v in ("length_mm","width_mm","height_mm"))==dims
        assert rows[key]["source_units"]=="cm"

def test_original_images_have_source_hashes():
    manifest=json.loads((DATA/"source_manifest.json").read_text())
    assert len(manifest["images"])==8
    for filename,meta in manifest["images"].items():
        img=DATA/"images"/filename
        assert img.is_file() and img.stat().st_size==meta["bytes"]
        assert hashlib.sha256(img.read_bytes()).hexdigest()==meta["sha256"]

def test_marker_ids_really_detected_in_all_captures():
    detector=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(
        cv2.aruco.DICT_4X4_50),cv2.aruco.DetectorParameters())
    for img_path in sorted((DATA/"images").glob("*.JPG")):
        im=cv2.imread(str(img_path),cv2.IMREAD_GRAYSCALE)
        assert im is not None,img_path
        corners,ids,_=detector.detectMarkers(im)
        assert ids is not None and set(ids.ravel().tolist())==set(MARKER_ORIGINS_MM),img_path

def test_human_object_rois_are_complete_valid_and_crops_exist():
    a=json.loads((DATA/"roi_annotations.json").read_text())
    assert a["reference_size_px"]==[720,460]
    files={k:v for k,v in a.items() if k.endswith(".JPG")}
    assert len(files)==8
    for name,objects in files.items():
        assert set(objects)==set(EXPECTED)
        im=cv2.imread(str(DATA/"images"/name))
        assert im is not None
        h,w=im.shape[:2]
        for label,roi in objects.items():
            x0,y0,x1,y1=actual_roi(roi,w,h)
            assert 0<=x0<x1<=w and 0<=y0<y1<=h
            crop=DATA/"crops"/f"{Path(name).stem}__{label}.jpg"
            assert crop.exists() and cv2.imread(str(crop)) is not None

def test_crop_annotations_cannot_be_mistaken_for_auto_detections():
    annotations=json.loads((DATA/"crop_annotations.json").read_text())
    assert len(annotations)==40
    assert all(a["label_source"]=="manual_from_visual_inspection" for a in annotations)

def test_camera_intrinsics_not_misrepresented_as_external_calibration():
    profile=json.loads((DATA/"camera_profile_estimated.json").read_text())
    assert profile["status"]=="estimated_not_verified"
    assert profile["training_frames"]==8
    assert profile["in_sample_rms_px"]>=0

def test_real_results_do_not_claim_unverified_t01_go():
    result=json.loads((DATA/"real_results.json").read_text())
    assert result["dataset"]=="real"
    assert result["images_analyzed"]==8
    assert result["marker_detection_rate"]==1.0
    assert result["real_world_t01_gate"]=="NOT_PASSED"
    assert result["height_mae_mm"] is None
    assert result["observed_xy_mae_mm"] is not None
    assert len(result["object_baseline_diagnostics"])==15
    assert all(x["requires_user_review"] for x in result["object_baseline_diagnostics"])


def test_exploratory_four_view_fit_is_labeled_research_not_gate():
    exp=json.loads((DATA/"experimental_3d_results.json").read_text())
    assert exp["status"]=="EXPERIMENTAL_NOT_GATE_EVIDENCE"
    assert len(exp["views"])==4
    assert len(exp["metrics_exploratory_only"])==5
    assert {r["item_id"] for r in exp["metrics_exploratory_only"]}==set(EXPECTED)
    assert all(len(r["fitted_LWH_mm"])==3 for r in exp["metrics_exploratory_only"])
    assert all(r["pixel_bbox_rms_error_px"]>=0 for r in exp["metrics_exploratory_only"])
