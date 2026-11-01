"""Phase 1 #7: real autonomous ROI interface and crop regression tests."""
from pathlib import Path
import json

import cv2
import numpy as np
import pytest

from backend.app.cv.segmentation import (
    YOLOESegmenter, SegmentationPipeline,
    extract_item_rgb_crop, save_item_rgb_crop,
)
from backend.app.cv.service import CVMetrologyService


def test_rgb_crop_preserves_full_resolution_and_channel_order():
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    image[4:16, 5:23] = [12, 44, 220]
    rgb = extract_item_rgb_crop(image, [5, 4, 23, 16])
    assert rgb.shape == (12, 18, 3)
    np.testing.assert_array_equal(rgb[0, 0], [220, 44, 12])


def test_rgb_crop_supports_optional_full_size_mask():
    image = np.full((10, 10, 3), 90, np.uint8)
    mask = np.zeros((10, 10), np.uint8)
    mask[4:6, 4:6] = 255
    rgb = extract_item_rgb_crop(image, [3, 3, 7, 7], mask)
    assert np.array_equal(rgb[0, 0], [0, 0, 0])
    assert np.array_equal(rgb[1, 1], [90, 90, 90])
    with pytest.raises(ValueError, match="mask must match"):
        extract_item_rgb_crop(image, [3, 3, 7, 7], np.zeros((3, 3), np.uint8))


def test_crop_persistence_unique_ids_and_no_path_traversal(tmp_path):
    image = np.full((12, 13, 3), [110, 30, 220], np.uint8)
    first_id, first_path = save_item_rgb_crop(image, output_dir=tmp_path)
    second_id, second_path = save_item_rgb_crop(image, output_dir=tmp_path)
    assert first_id != second_id
    assert first_path.exists() and second_path.exists()
    stored_bgr = cv2.imread(str(first_path))
    assert stored_bgr is not None and stored_bgr.shape == image.shape
    np.testing.assert_allclose(stored_bgr[6, 6], [220, 30, 110], atol=2)
    with pytest.raises(FileExistsError):
        save_item_rgb_crop(image, output_dir=tmp_path, item_id=first_id)
    with pytest.raises(ValueError, match="item_id"):
        save_item_rgb_crop(image, output_dir=tmp_path, item_id="../unsafe")


class FakeTensor:
    def __init__(self, array):
        self.data = np.asarray(array, dtype=np.float32)

    def detach(self):
        return self

    def cpu(self):
        return self

    def __array__(self, dtype=None):
        return np.asarray(self.data, dtype=dtype)


class FakeResult:
    def __init__(self, masks):
        self.boxes = type("Boxes", (), {
            "__len__": lambda self: len(masks),
            "xyxy": FakeTensor([[10, 10, 70, 70], [110, 110, 145, 145]]),
            "conf": FakeTensor([0.91, 0.99]),
            "cls": FakeTensor([0, 0]),
        })()
        self.masks = type("Masks", (), {"data": FakeTensor(masks)})()
        self.names = {0: "package"}


class FakeModel:
    def __init__(self):
        self.calls = []

    def predict(self, **kwargs):
        self.calls.append(kwargs)
        masks = np.zeros((2, 200, 200), np.float32)
        masks[0, 10:70, 10:70] = 1
        masks[1, 110:145, 110:145] = 1
        return [FakeResult(masks)]


def _geometry():
    K = np.array([[200, 0, 100], [0, 200, 100], [0, 0, 1]], dtype=float)
    D = np.zeros(5, dtype=float)
    pose = {
        "rvec": np.zeros((3, 1), dtype=float),
        "tvec": np.array([[0], [0], [400]], dtype=float),
    }
    return K, D, pose


def test_auto_roi_from_model_masks_without_candidate_boxes_or_json():
    model = FakeModel()
    segmenter = YOLOESegmenter(min_area_px=20)
    segmenter._model = model
    K, D, pose = _geometry()
    image = np.zeros((200, 200, 3), np.uint8)
    found = segmenter.detect_and_segment(image, K, D, pose)
    assert len(found) == 1  # The second candidate lies on the A4 board.
    assert found[0]["bbox"] == [10, 10, 70, 70]
    assert found[0]["area_px"] == 3600
    assert found[0]["source"] == "yoloe"
    assert found[0]["confidence"] == pytest.approx(0.91)
    assert len(model.calls) == 1
    assert model.calls[0]["retina_masks"] is True
    assert model.calls[0]["agnostic_nms"] is True


def test_candidate_guided_baseline_is_explicit_not_default(monkeypatch):
    segmenter = YOLOESegmenter()
    K, D, pose = _geometry()
    image = np.full((200, 200, 3), 90, np.uint8)
    monkeypatch.setattr(segmenter, "_automatic_predictions", lambda image: [])
    assert segmenter.detect_and_segment(image, K, D, pose) == []
    # Supplying candidate_boxes=[] must not invoke the model.
    assert segmenter.detect_and_segment(image, K, D, pose, candidate_boxes=[]) == []


def test_detector_reports_missing_model_instead_of_silent_empty_results(monkeypatch):
    segmenter = YOLOESegmenter(model_path="missing-model-should-fail.pt")
    monkeypatch.setattr(segmenter, "_get_model", lambda: (_ for _ in ()).throw(RuntimeError("missing weights")))
    K, D, pose = _geometry()
    with pytest.raises(RuntimeError, match="missing weights"):
        segmenter.detect_and_segment(np.zeros((200, 200, 3), np.uint8), K, D, pose)


class StubSegmenter:
    def detect_and_segment(self, image, K, D, pose):
        h, w = image.shape[:2]
        mask = np.zeros((h, w), np.uint8)
        mask[30:70, 30:80] = 255
        return [{
            "bbox": [30, 30, 80, 70],
            "mask": mask,
            "contour": np.array([[30,30],[79,30],[79,69],[30,69]], float),
            "center": [55, 50],
            "area_px": 2000,
            "confidence": 0.9,
        }]


class StubVerifier:
    def compute_parallax_maps(self, img1, img2, H):
        assert H.shape == (3, 3)
        return {"ready": True}

    def verify_candidate(self, mask, parallax_maps):
        assert mask.ndim == 2 and parallax_maps["ready"]
        return True, 0.7, {"reason": "verified"}


def test_full_pair_pipeline_saves_crops_without_annotations(tmp_path):
    base = Path(__file__).resolve().parents[1] / "experiments" / "synthetic_t01"
    meta = json.loads((base / "ground_truth.json").read_text(encoding="utf-8"))
    K = np.asarray(meta["camera_intrinsic_K"], np.float64)
    D = np.asarray(meta["distortion_coefficients"], np.float64)
    top = cv2.imread(str(base / "optipack_synthetic_top.png"))
    oblique = cv2.imread(str(base / "optipack_synthetic_oblique.png"))
    assert top is not None and oblique is not None
    calibration = CVMetrologyService(K, D).calibrate_pair(top, oblique)
    pipeline = SegmentationPipeline(
        segmenter=StubSegmenter(), verifier=StubVerifier(), crop_dir=tmp_path
    )
    out = pipeline.run(top, oblique, calibration)
    assert len(out.top_items) == 1
    assert len(out.oblique_items) == 1
    assert out.warnings == []
    first = out.top_items[0]
    assert Path(first["crop_path"]).is_file()
    assert first["crop_url"].endswith(first["item_id"] + ".jpg")
    crop = cv2.imread(first["crop_path"])
    assert crop is not None and crop.shape[:2] == (40, 50)
    # Re-run should persist under a distinct UUID instead of overwriting.
    second = pipeline.run(top, oblique, calibration).top_items[0]
    assert first["item_id"] != second["item_id"]

def test_tiled_inference_merges_overlapping_proposals(monkeypatch):
    image = np.zeros((200, 200, 3), np.uint8)
    segmenter = YOLOESegmenter(tiled_inference=True)
    calls = []

    def fake_predict(patch, x_offset, y_offset, full_shape):
        calls.append((patch.shape[:2], x_offset, y_offset))
        if (x_offset, y_offset) != (0, 0):
            return []
        # Full image and upper-left tile both find the same object.
        score = .7 if patch.shape[:2] == image.shape[:2] else .9
        return [{
            "bbox": [10, 10, 70, 70], "confidence": score,
            "mask": np.zeros(full_shape, np.uint8), "area_px": 3600,
        }]

    monkeypatch.setattr(segmenter, "_predict_patch", fake_predict)
    result = segmenter._automatic_predictions(image)
    assert len(calls) == 5  # original view + 4 overlapping tiles
    assert len(result) == 1
    assert result[0]["confidence"] == pytest.approx(.9)


def test_parallax_rejection_does_not_create_crops(tmp_path):
    base = Path(__file__).resolve().parents[1] / "experiments" / "synthetic_t01"
    meta = json.loads((base / "ground_truth.json").read_text(encoding="utf-8"))
    K = np.asarray(meta["camera_intrinsic_K"], np.float64)
    D = np.asarray(meta["distortion_coefficients"], np.float64)
    top = cv2.imread(str(base / "optipack_synthetic_top.png"))
    oblique = cv2.imread(str(base / "optipack_synthetic_oblique.png"))
    calibration = CVMetrologyService(K, D).calibrate_pair(top, oblique)

    class RejectVerifier(StubVerifier):
        def verify_candidate(self, mask, parallax_maps):
            return False, 0.01, {"reason": "planar"}

    out = SegmentationPipeline(
        segmenter=StubSegmenter(), verifier=RejectVerifier(), crop_dir=tmp_path
    ).run(top, oblique, calibration)
    assert out.top_items == []
    assert len(out.oblique_items) == 1
    assert len(out.warnings) == 1
    assert not list(tmp_path.glob("*.jpg"))

def test_auto_roi_frame_margin_rejects_truncated_objects(monkeypatch):
    K, D, pose = _geometry()
    image = np.zeros((200, 200, 3), np.uint8)
    detector = YOLOESegmenter(frame_margin_fraction=0.025)

    def obj(box):
        mask = np.zeros((200, 200), np.uint8)
        x0, y0, x1, y1 = box
        mask[y0:y1, x0:x1] = 255
        return {
            "bbox": box, "mask": mask, "area_px": int(cv2.countNonZero(mask)),
            "center": [(x0+x1)/2, (y0+y1)/2],
            "confidence": .8,
        }

    monkeypatch.setattr(detector, "_automatic_predictions", lambda _: [
        obj([0, 10, 30, 35]), obj([10, 10, 60, 60])
    ])
    got = detector.detect_and_segment(image, K, D, pose)
    assert [item["bbox"] for item in got] == [[10, 10, 60, 60]]

def test_dedup_uses_cropped_mask_until_proposal_selection():
    model = FakeModel()
    detector = YOLOESegmenter(min_area_px=20)
    detector._model = model
    image = np.zeros((200, 200, 3), np.uint8)
    intermediate = detector._predict_patch(image, 0, 0, image.shape[:2])
    assert intermediate
    assert all("mask" not in prediction for prediction in intermediate)
    assert all(prediction["_mask_roi"].size < image.shape[0] * image.shape[1]
               for prediction in intermediate)
    final = detector._automatic_predictions(image)
    assert final
    assert all(item["mask"].shape == image.shape[:2] for item in final)
    assert all("_mask_roi" not in item for item in final)
