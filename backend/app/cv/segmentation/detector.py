"""Automatic 2D item instance detection and segmentation for OptiPack Issue #7.

Production inference requires a YOLOE segmentation checkpoint. Candidate-guided
GrabCut remains available explicitly for Phase 0 baseline comparisons, but is
never used as a silent substitute for autonomous detection.

No ROI annotation JSON is read by this module.
"""
from pathlib import Path
from threading import RLock
import hashlib
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from backend.app.cv.aruco_detector import MARKER_ORIGINS_MM, ARUCO_MARKER_SIZE_MM


class YOLOESegmenter:
    """Open-vocabulary model proposals + ArUco exclusion + optional GrabCut."""

    REPRTA_PROMPTS = (
        "cardboard box", "package", "parcel", "carton", "box",
        "container", "book", "bottle", "packaged product",
    )

    def __init__(
        self,
        model_path: str | Path = "yoloe-26n-seg.pt",
        conf_threshold: float = 0.15,
        iou_threshold: float = 0.50,
        grabcut_fallback: bool = True,
        crop_max_dim: int = 150,
        imgsz: int = 960,
        prompts: Optional[Sequence[str]] = None,
        device: str = "cpu",
        min_area_px: int = 500,
        tiled_inference: bool = False,
        frame_margin_fraction: float = 0.025,
    ):
        if not 0.0 < conf_threshold < 1.0 or not 0.0 < iou_threshold < 1.0:
            raise ValueError("confidence and IoU thresholds must be within (0,1)")
        if imgsz <= 0 or min_area_px < 1:
            raise ValueError("imgsz and min_area_px must be positive")
        if not 0 <= frame_margin_fraction < .20:
            raise ValueError("frame_margin_fraction must be between 0 and 0.20")
        self.model_path = str(model_path)
        self.conf_threshold = float(conf_threshold)
        self.iou_threshold = float(iou_threshold)
        self.grabcut_fallback = grabcut_fallback
        self.crop_max_dim = crop_max_dim
        self.imgsz = int(imgsz)
        self.prompts = list(prompts or self.REPRTA_PROMPTS)
        self.device = device
        self.min_area_px = min_area_px
        self.tiled_inference = tiled_inference
        self.frame_margin_fraction = float(frame_margin_fraction)
        self._model = None
        # YOLOE's prediction state is mutable; serialize shared-model calls
        # while preserving the benefit of warm model/prompt embeddings.
        self._inference_lock = RLock()

    def _get_model(self):
        """Load checkpoint lazily; only automatic inference needs heavy deps."""
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLO, YOLOE
        except ImportError as exc:
            raise RuntimeError(
                "Automatic ROI requires ultralytics>=8.4.0 and torch. "
                "Install the optional segmentation requirements first."
            ) from exc

        path = self.model_path
        try:
            if path.lower().endswith(".onnx"):
                # Text prompts have to be fixed before export to ONNX.
                model = YOLO(path, task="segment")
            else:
                model = YOLOE(path)
                if not path.lower().endswith("-pf.pt"):
                    # Prompt embeddings are bound to the checkpoint and prompt
                    # vocabulary, not computed on each CPU inference run.
                    profile_key = hashlib.sha256(
                        (Path(path).name + "\\n" + "\\n".join(self.prompts)).encode()
                    ).hexdigest()[:16]
                    cache = Path(__file__).resolve().parent / ".cache" / f"{profile_key}.npz"
                    if cache.is_file():
                        model.load_prompt_embeddings(str(cache))
                    else:
                        model.set_classes(self.prompts)
                        cache.parent.mkdir(parents=True, exist_ok=True)
                        model.save_prompt_embeddings(str(cache))
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load YOLOE segmentation checkpoint '{path}': {exc}"
            ) from exc
        self._model = model
        return model

    @staticmethod
    def get_aruco_exclusion_polygons(
        K: np.ndarray, D: np.ndarray, pose: Dict
    ) -> Tuple[np.ndarray, List[np.ndarray]]:
        """Project known A4 calibration board and marker borders into image."""
        rvec = np.asarray(pose["rvec"], dtype=np.float64)
        tvec = np.asarray(pose["tvec"], dtype=np.float64)
        board_world = np.array(
            [[-20.0, -20.0, 0.0], [280.0, -20.0, 0.0],
             [280.0, 195.0, 0.0], [-20.0, 195.0, 0.0]],
            dtype=np.float64,
        )
        board, _ = cv2.projectPoints(board_world, rvec, tvec, K, D)
        markers = []
        for ox, oy in MARKER_ORIGINS_MM.values():
            side = ARUCO_MARKER_SIZE_MM
            corners = np.array([
                [ox-8, oy-8, 0], [ox+side+8, oy-8, 0],
                [ox+side+8, oy+side+8, 0], [ox-8, oy+side+8, 0],
            ], dtype=np.float64)
            pixel, _ = cv2.projectPoints(corners, rvec, tvec, K, D)
            markers.append(pixel.reshape(-1, 2))
        return board.reshape(-1, 2), markers

    def refine_with_grabcut(
        self, image: np.ndarray, bbox: List[int], max_dim: Optional[int] = None
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Candidate-guided mask refinement (legacy baseline / explicit fallback)."""
        max_dim = max_dim or self.crop_max_dim
        h, w = image.shape[:2]
        x0, y0, x1, y1 = [int(v) for v in bbox]
        if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
            return None, None
        pad_x = max(15, int(0.08 * (x1-x0)))
        pad_y = max(15, int(0.08 * (y1-y0)))
        cx0, cy0 = max(0, x0-pad_x), max(0, y0-pad_y)
        cx1, cy1 = min(w, x1+pad_x), min(h, y1+pad_y)
        patch = image[cy0:cy1, cx0:cx1]
        if patch.size == 0 or min(patch.shape[:2]) < 10:
            return None, None
        ph, pw = patch.shape[:2]
        scale = min(1.0, float(max_dim) / max(ph, pw))
        scaled = cv2.resize(
            patch, (max(24, int(pw*scale)), max(24, int(ph*scale))),
            interpolation=cv2.INTER_LINEAR,
        )
        sh, sw = scaled.shape[:2]
        gc_mask = np.full((sh, sw), cv2.GC_PR_BGD, np.uint8)
        by, bx = max(2, int(0.04*sh)), max(2, int(0.04*sw))
        gc_mask[:by] = cv2.GC_BGD
        gc_mask[-by:] = cv2.GC_BGD
        gc_mask[:, :bx] = cv2.GC_BGD
        gc_mask[:, -bx:] = cv2.GC_BGD
        gc_mask[int(.12*sh):int(.88*sh), int(.12*sw):int(.88*sw)] = cv2.GC_PR_FGD
        gc_mask[int(.35*sh):int(.65*sh), int(.35*sw):int(.65*sw)] = cv2.GC_FGD
        try:
            cv2.grabCut(
                scaled, gc_mask, None, np.zeros((1, 65), np.float64),
                np.zeros((1, 65), np.float64), 1, cv2.GC_INIT_WITH_MASK,
            )
        except cv2.error:
            return None, None
        binary = np.where(
            (gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD), 255, 0
        ).astype(np.uint8)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contours:
            return None, None
        biggest = max(contours, key=cv2.contourArea).reshape(-1, 2).astype(float)
        contour = biggest / scale + np.array([cx0, cy0])
        mask = np.zeros((h, w), np.uint8)
        cv2.fillPoly(mask, [np.rint(contour).astype(np.int32)], 255)
        return mask, contour

    @staticmethod
    def _as_numpy(tensor) -> np.ndarray:
        if hasattr(tensor, "detach"):
            tensor = tensor.detach()
        if hasattr(tensor, "cpu"):
            tensor = tensor.cpu()
        return np.asarray(tensor, dtype=np.float32)

    def _predict_patch(
        self, patch: np.ndarray, x_offset: int, y_offset: int,
        full_shape: tuple[int, int],
    ) -> List[Dict]:
        try:
            with self._inference_lock:
                model = self._get_model()
                result = model.predict(
                    source=patch, imgsz=self.imgsz, conf=self.conf_threshold,
                    iou=self.iou_threshold, agnostic_nms=True, max_det=30,
                    retina_masks=True, device=self.device, verbose=False,
                )[0]
        except Exception as exc:
            raise RuntimeError(f"YOLOE inference failed: {exc}") from exc
        if result.boxes is None or len(result.boxes) == 0:
            return []
        if result.masks is None:
            raise RuntimeError("YOLOE returned detections without instance masks")
        xyxy = self._as_numpy(result.boxes.xyxy)
        scores = self._as_numpy(result.boxes.conf)
        classes = self._as_numpy(result.boxes.cls)
        masks = self._as_numpy(result.masks.data)
        if len(xyxy) != len(masks):
            raise RuntimeError("YOLOE detection/mask count mismatch")
        patch_h, patch_w = patch.shape[:2]
        full_h, full_w = full_shape
        found = []
        for _, confidence, class_id, raw_mask in zip(xyxy, scores, classes, masks):
            binary = (raw_mask > .5).astype(np.uint8) * 255
            if binary.shape != (patch_h, patch_w):
                binary = cv2.resize(binary, (patch_w, patch_h), interpolation=cv2.INTER_NEAREST)
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            contour = max(contours, key=cv2.contourArea)
            clean = np.zeros((patch_h, patch_w), np.uint8)
            cv2.drawContours(clean, [contour], -1, 255, thickness=-1)
            area = int(cv2.countNonZero(clean))
            if area < self.min_area_px or area > .80 * patch_h * patch_w:
                continue
            x, y, bw, bh = cv2.boundingRect(contour)
            # A tile-cut object cannot be used reliably for 3D fitting.
            if (x_offset or y_offset or patch_h != full_h or patch_w != full_w):
                border = 5
                if ((x <= border and x_offset > 0)
                    or (y <= border and y_offset > 0)
                    or (x+bw >= patch_w-border and x_offset+patch_w < full_w)
                    or (y+bh >= patch_h-border and y_offset+patch_h < full_h)):
                    continue
            gx, gy = x+x_offset, y+y_offset
            # Hold only a cropped mask while proposals from five views
            # compete for NMS. Expanding every rejected candidate into a
            # 4032x3024 binary canvas can exhaust RAM on 16 GB laptops.
            found.append({
                "bbox": [gx, gy, gx+bw, gy+bh],
                "_mask_roi": clean[y:y+bh, x:x+bw].copy(),
                "contour": contour.reshape(-1, 2).astype(float) + [x_offset, y_offset],
                "area_px": area,
                "center": [gx+bw/2, gy+bh/2],
                "confidence": float(confidence),
                "class_name": str(result.names.get(int(class_id), int(class_id))),
                "source": "yoloe_tile" if patch_h != full_h or patch_w != full_w else "yoloe",
            })
        return found

    @staticmethod
    def _bbox_iou(a: List[int], b: List[int]) -> tuple[float, float]:
        x0, y0 = max(a[0], b[0]), max(a[1], b[1])
        x1, y1 = min(a[2], b[2]), min(a[3], b[3])
        common = max(0, x1-x0) * max(0, y1-y0)
        area_a = max(1, (a[2]-a[0]) * (a[3]-a[1]))
        area_b = max(1, (b[2]-b[0]) * (b[3]-b[1]))
        return common / (area_a+area_b-common), common / min(area_a, area_b)

    def _automatic_predictions(self, image: np.ndarray) -> List[Dict]:
        height, width = image.shape[:2]
        found = self._predict_patch(image, 0, 0, (height, width))
        if self.tiled_inference:
            tile_h, tile_w = round(height * .65), round(width * .65)
            for y0 in (0, height-tile_h):
                for x0 in (0, width-tile_w):
                    patch = image[y0:y0+tile_h, x0:x0+tile_w]
                    found.extend(self._predict_patch(patch, x0, y0, (height, width)))
        # Merge the overlapping global/tile predictions before board exclusion.
        keep = []
        for candidate in sorted(found, key=lambda item: item["confidence"], reverse=True):
            if any(
                (lambda iou, containment: iou >= .50 or containment >= .85)(
                    *self._bbox_iou(candidate["bbox"], selected["bbox"])
                )
                for selected in keep
            ):
                continue
            keep.append(candidate)
        # Preserve the public full-resolution mask interface, but allocate
        # canvases only for retained detections, never all tile proposals.
        for candidate in keep:
            roi = candidate.pop("_mask_roi", None)
            if roi is None:
                continue  # Supports externally injected candidates in tests.
            x0, y0, x1, y1 = candidate["bbox"]
            full_mask = np.zeros((height, width), dtype=np.uint8)
            full_mask[y0:y1, x0:x1] = roi
            candidate["mask"] = full_mask
        return keep

    def _is_board(self, candidate: Dict, board_mask: np.ndarray) -> bool:
        mask = candidate["mask"]
        overlap = cv2.countNonZero(cv2.bitwise_and(mask, board_mask))
        return overlap / max(1, candidate["area_px"]) >= .40

    def detect_and_segment(
        self,
        image: np.ndarray,
        K: np.ndarray,
        D: np.ndarray,
        pose: Dict,
        candidate_boxes: Optional[List[List[float]]] = None,
    ) -> List[Dict]:
        """Create automatic proposals and masks; annotations are never loaded.

        If candidate_boxes is explicitly provided, run the saved V3 GrabCut
        baseline without invoking a model. This path is not autonomous.
        """
        if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("image must be a 3-channel BGR ndarray")
        height, width = image.shape[:2]
        board_poly, marker_polys = self.get_aruco_exclusion_polygons(K, D, pose)
        board_mask = np.zeros((height, width), np.uint8)
        cv2.fillPoly(board_mask, [np.rint(board_poly).astype(np.int32)], 255)
        for poly in marker_polys:
            cv2.fillPoly(board_mask, [np.rint(poly).astype(np.int32)], 255)

        if candidate_boxes is None:
            proposals = self._automatic_predictions(image)
            margin_x = width * self.frame_margin_fraction
            margin_y = height * self.frame_margin_fraction
            # An object crossing the capture border has an incomplete mask,
            # unsuitable for reliable 3D dimensions. No manual ROI is used.
            results = [item for item in proposals if (
                item["bbox"][0] >= margin_x and item["bbox"][1] >= margin_y
                and item["bbox"][2] <= width-margin_x
                and item["bbox"][3] <= height-margin_y
            )]
        else:
            results = []
            for bbox in candidate_boxes:
                mask, cnt = self.refine_with_grabcut(image, bbox)
                if mask is None or cnt is None:
                    continue
                x0, y0, x1, y1 = [int(x) for x in bbox]
                results.append({
                    "bbox": [x0, y0, x1, y1], "mask": mask, "contour": cnt,
                    "area_px": int(cv2.countNonZero(mask)),
                    "center": [(x0+x1)/2, (y0+y1)/2],
                    "confidence": None, "class_name": None,
                    "source": "candidate_grabcut",
                })
        return [item for item in results if not self._is_board(item, board_mask)]
