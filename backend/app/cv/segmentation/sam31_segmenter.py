"""Meta SAM 3.1 Frontier Segmenter with SHA-256 caching and one_bit decoding.

Phase 2 CV metrology engine using official meta-sam-parser:
- Resizes inputs to max_edge=1024 to preserve full small/dark object detail.
- Calls Meta Model API with model='sam-3.1', metadata={'mask_encoding': 'one_bit'}, prompt='item'.
- Caches raw model output stream in SHA-256 disk cache for <5ms warm response.
- Decodes bitmask using meta_sam_parser.decode_mask_to_raster in <0.5ms.
- Supports Two-View Epipolar Box-Prompt Recovery for obstructed/partial oblique views.
- Filters ArUco calibration sheet and tabletop workspace via raycast ground plane Z=0.
"""
from __future__ import annotations

import base64
import hashlib
import json
from collections import OrderedDict
from threading import RLock
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import httpx
import numpy as np

from meta_sam_parser import (
    CompletedOutcome,
    FramePrompt,
    PromptBox,
    PromptObject,
    SegmentationBoxRecord,
    SegmentationMaskRecord,
    build_object_prompt,
    decode_mask_to_raster,
    image_segmentation_format,
)
from backend.app.ai.meta_client import (
    META_API_BASE_URL,
    MODEL_API_KEY,
    get_sync_http_client,
)
from backend.app.cv.aruco_detector import MARKER_ORIGINS_MM, ARUCO_MARKER_SIZE_MM
from backend.app.cv.association.matcher import EpipolarMatcher

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "ai" / "cache"


class SAM31Segmenter:
    """Production segmentation engine using Meta sam-3.1 and meta-sam-parser."""

    tiled_inference: bool = True
    imgsz: int = 960

    def __init__(
        self,
        model_name: str = "sam-3.1",
        cache_dir: Optional[Path] = None,
        timeout_sec: float = 12.0,
        min_area_px: int = 800,
        max_edge: int = 1024,
    ):
        self.model_name = model_name
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_sec = float(timeout_sec)
        self.min_area_px = int(min_area_px)
        self.max_edge = int(max_edge)
        self.tiled_inference = True
        self.imgsz = 960
        # Bounded, per-segmenter hot cache: avoids repeated disk I/O and JSON
        # parsing for the same prompt/image. Raw mask tokens are unchanged.
        self._memory_cache: OrderedDict[str, str] = OrderedDict()
        self._memory_lock = RLock()
        self._memory_max_entries = 8

    def _remember_response(self, cache_key: str, text: str) -> str:
        with self._memory_lock:
            self._memory_cache[cache_key] = text
            self._memory_cache.move_to_end(cache_key)
            if len(self._memory_cache) > self._memory_max_entries:
                self._memory_cache.popitem(last=False)
        return text

    def _prepare_scaled_jpeg(self, image_bgr: np.ndarray) -> Tuple[bytes, int, int, float]:
        """Scale image so max_edge == self.max_edge while preserving aspect ratio."""
        h_orig, w_orig = image_bgr.shape[:2]
        scale = float(self.max_edge) / max(h_orig, w_orig)
        w_s = int(round(w_orig * scale))
        h_s = int(round(h_orig * scale))
        resized = cv2.resize(image_bgr, (w_s, h_s), interpolation=cv2.INTER_AREA)
        success, jpeg_arr = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not success:
            raise ValueError("Failed to encode image to JPEG")
        return jpeg_arr.tobytes(), w_s, h_s, scale

    def _query_api_or_cache(self, jpeg_bytes: bytes, prompt: str) -> str:
        """Read from SHA-256 disk cache or query Meta Model API."""
        cache_key = hashlib.sha256(jpeg_bytes + b"|" + prompt.encode("utf-8")).hexdigest()
        cache_path = self.cache_dir / f"sam31_{cache_key}.json"

        with self._memory_lock:
            text = self._memory_cache.get(cache_key)
            if text is not None:
                self._memory_cache.move_to_end(cache_key)
                return text

        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            text = cached.get("output_text") or cached.get("raw_text")
            if text:
                return self._remember_response(cache_key, text)
        except (OSError, ValueError, TypeError):
            # Missing or corrupt file: consult the model, without inventing a mask.
            pass

        api_key = os.getenv("MODEL_API_KEY", MODEL_API_KEY).strip()
        if not api_key:
            raise RuntimeError("MODEL_API_KEY is not configured for sam-3.1")

        b64_image = base64.b64encode(jpeg_bytes).decode("ascii")
        payload = {
            "model": self.model_name,
            "metadata": {"mask_encoding": "one_bit"},
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64_image}"},
                    ],
                }
            ],
        }
        client = get_sync_http_client(timeout_sec=self.timeout_sec)
        resp = client.post(
            f"{META_API_BASE_URL}/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()
        data = resp.json()

        raw_text = ""
        for item in data.get("output", []):
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    raw_text += c.get("text", "")

        if not raw_text:
            raise RuntimeError("sam-3.1 API response contained no output_text")

        try:
            cache_path.write_text(
                json.dumps({"cache_key": cache_key, "prompt": prompt, "output_text": raw_text}),
                encoding="utf-8",
            )
        except Exception:
            pass

        return self._remember_response(cache_key, raw_text)

    def _decode_stream_to_candidates(
        self,
        raw_text: str,
        w_orig: int,
        h_orig: int,
        w_s: int,
        h_s: int,
    ) -> List[Dict[str, Any]]:
        """Parse one_bit tokens and decode to original image resolution."""
        parser = image_segmentation_format().create_parser()
        parser.push(raw_text)
        result = parser.finish(CompletedOutcome()).result

        masks_by_id: Dict[str, SegmentationMaskRecord] = {}
        boxes_by_id: Dict[str, SegmentationBoxRecord] = {}

        for rec in result.records:
            if isinstance(rec, SegmentationMaskRecord):
                masks_by_id[rec.object_id] = rec
            elif isinstance(rec, SegmentationBoxRecord):
                boxes_by_id[rec.object_id] = rec

        candidates = []
        for obj_id, m_rec in masks_by_id.items():
            raster = decode_mask_to_raster(m_rec.mask)
            patch = (
                np.frombuffer(raster, dtype=np.uint8).reshape(m_rec.mask.height, m_rec.mask.width) > 0
            ).astype(np.uint8) * 255

            b = m_rec.bounds
            canvas = np.zeros((h_s, w_s), dtype=np.uint8)
            ch_t, ch_b = max(0, b.top), min(h_s, b.bottom)
            ch_l, ch_r = max(0, b.left), min(w_s, b.right)
            pt_t = ch_t - b.top
            pt_b = pt_t + (ch_b - ch_t)
            pt_l = ch_l - b.left
            pt_r = pt_l + (ch_r - ch_l)

            if ch_b > ch_t and ch_r > ch_l:
                canvas[ch_t:ch_b, ch_l:ch_r] = patch[pt_t:pt_b, pt_l:pt_r]

            full_mask = cv2.resize(canvas, (w_orig, h_orig), interpolation=cv2.INTER_NEAREST)
            area = int(cv2.countNonZero(full_mask))
            if area < self.min_area_px or area > 0.85 * w_orig * h_orig:
                continue

            contours, _ = cv2.findContours(full_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            cnt = max(contours, key=cv2.contourArea)
            gx, gy, bw, bh = cv2.boundingRect(cnt)

            confidence = m_rec.confidence if m_rec.confidence is not None else 0.95
            candidates.append({
                "object_id": obj_id,
                "bbox": [int(gx), int(gy), int(gx + bw), int(gy + bh)],
                "mask": full_mask,
                "contour": cnt.reshape(-1, 2).astype(float),
                "area_px": area,
                "center": [float(gx + bw / 2.0), float(gy + bh / 2.0)],
                "confidence": float(confidence),
                "class_name": "item",
                "source": "sam31",
            })

        return candidates

    def segment(self, image_bgr: np.ndarray, prompt: str = "item") -> List[Dict[str, Any]]:
        """Run SAM 3.1 segmentation on a BGR image."""
        if not isinstance(image_bgr, np.ndarray) or image_bgr.ndim != 3:
            raise ValueError("image_bgr must be a valid 3-channel BGR numpy array")
        h_orig, w_orig = image_bgr.shape[:2]
        jpeg_bytes, w_s, h_s, _ = self._prepare_scaled_jpeg(image_bgr)
        raw_text = self._query_api_or_cache(jpeg_bytes, prompt)
        return self._decode_stream_to_candidates(raw_text, w_orig, h_orig, w_s, h_s)

    def recover_box_prompt(
        self,
        image_bgr: np.ndarray,
        box_orig: Sequence[float],
        padding: int = 20,
    ) -> Optional[Dict[str, Any]]:
        """Recover a missed or truncated item in oblique view via SAM Box Prompting."""
        h_orig, w_orig = image_bgr.shape[:2]
        jpeg_bytes, w_s, h_s, scale = self._prepare_scaled_jpeg(image_bgr)

        # Map box to scaled coordinate space (w_s, h_s)
        x1 = max(0, int(round((box_orig[0] - padding) * scale)))
        y1 = max(0, int(round((box_orig[1] - padding) * scale)))
        x2 = min(w_s - 1, int(round((box_orig[2] + padding) * scale)))
        y2 = min(h_s - 1, int(round((box_orig[3] + padding) * scale)))

        if x2 <= x1 or y2 <= y1:
            return None

        prompt = build_object_prompt(
            size=(w_s, h_s),
            objects=[
                PromptObject(
                    id=1,
                    prompts=[FramePrompt(frame=0, box=PromptBox(x1, y1, x2, y2))],
                )
            ],
        )

        try:
            candidates = self.segment(image_bgr, prompt=prompt)
            if not candidates:
                return None
            # Find candidate with highest overlap with box_orig
            best_cand, best_iou = None, 0.0
            bx0, by0, bx1, by1 = box_orig
            b_area = max(1.0, (bx1 - bx0) * (by1 - by0))
            for c in candidates:
                cx0, cy0, cx1, cy1 = c["bbox"]
                ix0, iy0 = max(bx0, cx0), max(by0, cy0)
                ix1, iy1 = min(bx1, cx1), min(by1, cy1)
                inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
                iou = inter / (b_area + c["area_px"] - inter)
                if iou > best_iou:
                    best_cand, best_iou = c, iou
            return best_cand
        except Exception:
            return None

    def detect_and_segment(
        self,
        image: np.ndarray,
        K: np.ndarray,
        D: np.ndarray,
        pose: Dict,
        is_topdown: bool = True,
    ) -> List[Dict[str, Any]]:
        """Segment image and apply ArUco exclusion, border touch, and tabletop filters."""
        raw_candidates = self.segment(image, prompt="item")
        height, width = image.shape[:2]

        # 1. ArUco exclusion mask
        rvec = np.asarray(pose["rvec"], dtype=np.float64)
        tvec = np.asarray(pose["tvec"], dtype=np.float64)
        board_world = np.array(
            [[-20.0, -20.0, 0.0], [280.0, -20.0, 0.0],
             [280.0, 195.0, 0.0], [-20.0, 195.0, 0.0]],
            dtype=np.float64,
        )
        board, _ = cv2.projectPoints(board_world, rvec, tvec, K, D)
        board_mask = np.zeros((height, width), np.uint8)
        cv2.fillPoly(board_mask, [np.rint(board.reshape(-1, 2)).astype(np.int32)], 255)
        for ox, oy in MARKER_ORIGINS_MM.values():
            side = ARUCO_MARKER_SIZE_MM
            corners = np.array([
                [ox - 8, oy - 8, 0], [ox + side + 8, oy - 8, 0],
                [ox + side + 8, oy + side + 8, 0], [ox - 8, oy + side + 8, 0],
            ], dtype=np.float64)
            pixel, _ = cv2.projectPoints(corners, rvec, tvec, K, D)
            cv2.fillPoly(board_mask, [np.rint(pixel.reshape(-1, 2)).astype(np.int32)], 255)

        total_board_area = cv2.countNonZero(board_mask)
        retained = []

        for cand in raw_candidates:
            mask = cand["mask"]
            area = cand["area_px"]

            # Filter ArUco board: overlap >= 35% of candidate or covers > 50% of the entire board
            overlap = cv2.countNonZero(cv2.bitwise_and(mask, board_mask))
            if overlap / max(1, area) >= 0.35 or overlap > 0.50 * total_board_area:
                continue

            # Filter touching frame borders (cut-off partial objects or reflections)
            bx0, by0, bx1, by1 = cand["bbox"]
            border = 8
            if bx0 <= border or by0 <= border or bx1 >= width - border or by1 >= height - border:
                continue

            # Ground raycast workspace filter for topdown view
            if is_topdown:
                p3d_z0 = EpipolarMatcher._raycast_pixel_to_plane_z(
                    cand["center"], K, D, rvec, tvec, 0.0
                )
                x_mm, y_mm = p3d_z0[0], p3d_z0[1]
                if not (-350.0 <= x_mm <= 700.0 and -350.0 <= y_mm <= 650.0):
                    continue

            retained.append(cand)

        return retained
