"""Phase 2A live order-analysis composition (Issue #21).

Camera intrinsics must be provisioned explicitly. Missing/invalid calibration
never produces invented dimensions; the sample fixture is opt-in demo-only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import json
import os
from pathlib import Path
import uuid

import cv2
from fastapi import HTTPException, UploadFile
import numpy as np

from backend.app.cv.service import CVMetrologyService
from backend.app.cv.segmentation.cropping import DEFAULT_CROP_DIR
from backend.app.schemas.contracts import (
    AITelemetry, CalibrationInfo, OrderAnalysisResponse,
)

MAX_UPLOAD_BYTES = 18 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000
SAMPLE_PATH = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "order_analysis_sample.json"


def new_analysis_id() -> str:
    return f"analysis_{uuid.uuid4().hex}"


def timestamp_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


DEFAULT_CALIBRATION_PROFILE_PATH = (
    Path(__file__).resolve().parents[4] / "experiments" / "real_t01" / "calibration_model_variants.json"
)


@lru_cache(maxsize=1)
def get_cv_service() -> CVMetrologyService | None:
    """Share a warm model across API calls. Never infer intrinsics from FOV."""
    path_string = os.getenv("OPTIPACK_CAMERA_PROFILE_PATH", "").strip()
    if not path_string:
        if DEFAULT_CALIBRATION_PROFILE_PATH.is_file():
            path_string = str(DEFAULT_CALIBRATION_PROFILE_PATH)
        else:
            return None
    path = Path(path_string).expanduser()
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
        if "camera_matrix" not in profile:
            name = os.getenv("OPTIPACK_CAMERA_PROFILE_NAME", "").strip() or "free_tangent"
            if name not in profile:
                raise ValueError(f"Profile '{name}' not found in calibration profile JSON")
            profile = profile[name]
        size = profile.get("image_size_wh") or profile.get("image_size_px")
        return CVMetrologyService(
            np.asarray(profile["camera_matrix"], dtype=float),
            np.asarray(profile["dist_coeffs"], dtype=float),
            image_size_px=tuple(size) if size else None,
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Camera calibration profile invalid or unreadable; configure OPTIPACK_CAMERA_PROFILE_PATH",
        ) from exc


async def read_image(upload: UploadFile) -> tuple[np.ndarray, bytes]:
    """Reject invalid uploads rather than silently using fixture measurements."""
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(422, detail="Image upload is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail="Image exceeds the 18 MiB upload limit")
    is_jpeg = data[:3] == b"\xff\xd8\xff"
    is_png = data[:8] == b"\x89PNG\r\n\x1a\n"
    if not (is_jpeg or is_png):
        raise HTTPException(422, detail="Expected JPEG or PNG image data")
    if upload.content_type not in (
        "image/jpeg", "image/png", "application/octet-stream", None,
    ):
        raise HTTPException(415, detail="Unsupported image content type")
    if upload.content_type == "image/png" and not is_png:
        raise HTTPException(422, detail="Image content does not match its type")
    if upload.content_type == "image/jpeg" and not is_jpeg:
        raise HTTPException(422, detail="Image content does not match its type")
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise HTTPException(422, detail="Image could not be decoded")
    if image.shape[0] * image.shape[1] > MAX_IMAGE_PIXELS:
        raise HTTPException(413, detail="Image resolution exceeds allowed pixel count")

    # Auto-orient portrait phone photos (H > W) to landscape workspace calibration (W > H)
    if image.shape[0] > image.shape[1]:
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        success, enc = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if success:
            data = enc.tobytes()

    return image, data


def no_measurement_response(
    reason: str,
    *,
    status: str = "uncalibrated",
    warnings: list[str] | None = None,
) -> OrderAnalysisResponse:
    """Contract-compatible fail-closed response. 1.0 scale is a sentinel,
    explicitly marked invalid; it MUST NEVER be used for metric conversion."""
    messages = [reason, *(warnings or [])]
    return OrderAnalysisResponse(
        analysis_id=new_analysis_id(),
        timestamp_utc=timestamp_utc(),
        calibration=CalibrationInfo(
            status=status,
            detected_markers_count=0,
            reprojection_error_px=0.0,
            scale_mm_per_px_at_z0=1.0,
            camera_pose_valid=False,
            warnings=["Calibration unavailable: scale field is placeholder and is NOT a measurement"],
        ),
        items=[],
        ai_telemetry=AITelemetry(
            sam_status="skipped", muse_status="fallback",
            muse_latency_ms=0, fallback_activated=True,
        ),
        global_warnings=messages,
    )


def demo_fixture_response() -> OrderAnalysisResponse:
    """Explicit demo-only fallback with provenance preventing real-world use."""
    payload = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    output = OrderAnalysisResponse.model_validate(payload)
    output.analysis_id = new_analysis_id()
    output.timestamp_utc = timestamp_utc()
    output.calibration.status = "uncalibrated"
    output.calibration.detected_markers_count = 0
    output.calibration.reprojection_error_px = 0
    output.calibration.scale_mm_per_px_at_z0 = 1.0
    output.calibration.camera_pose_valid = False
    output.calibration.warnings.append(
        "DEMO FIXTURE: no calibration performed; marker count/scale are placeholders"
    )
    for item in output.items:
        item.visual_evidence.crop_url = None
        item.measurement_provenance.xy_method = "demo_fixture_not_measured"
        item.measurement_provenance.z_method = "demo_fixture_not_measured"
        item.measurement_provenance.confidence_score = 0
        item.measurement_provenance.requires_user_review = True
    output.ai_telemetry.muse_status = "fallback"
    output.ai_telemetry.sam_status = "skipped"
    output.ai_telemetry.fallback_activated = True
    output.ai_telemetry.muse_latency_ms = 0
    output.global_warnings = [
        "DEMO FIXTURE ONLY: dimensions, physical attributes and image crops are sample data, not extracted from the submitted image",
        "Manual verification is mandatory before any packing decision",
    ]
    return output



def normalize_crop_urls(items: list) -> None:
    """Use the actual FastAPI StaticFiles mount, independent of Muse toggles."""
    for item in items:
        raw = item.visual_evidence.crop_url
        if raw:
            filename = Path(raw).name
            if filename.endswith(".jpg") and filename.startswith("item_"):
                item.visual_evidence.crop_url = f"/api/v1/assets/crops/{filename}"
            else:
                # Reject malformed references rather than exposing a broken link.
                item.visual_evidence.crop_url = None


def encode_semantic_crops(
    image: np.ndarray,
    items: list,
) -> list[dict]:
    """Pass exact CV item IDs, boxes, metric dimensions and crop bytes to Muse."""
    h, w = image.shape[:2]
    crops = []
    for item in items:
        bbox = list(item.visual_evidence.bbox_2d_px)
        x0, y0, x1, y1 = [int(v) for v in bbox]
        if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
            raise ValueError(f"Invalid bounding box for {item.item_id}")
        # Prefer the exact crop persisted by the CV segmentation pipeline.
        url = item.visual_evidence.crop_url
        filename = Path(url).name if url else ""
        persisted = DEFAULT_CROP_DIR / filename if filename else None
        if persisted is not None and persisted.is_file() and persisted.suffix.lower() == ".jpg":
            crop_bytes = persisted.read_bytes()
        else:
            ok, encoded = cv2.imencode(
                ".jpg", image[y0:y1, x0:x1], [cv2.IMWRITE_JPEG_QUALITY, 85]
            )
            if not ok:
                raise ValueError(f"Could not encode crop for {item.item_id}")
            crop_bytes = encoded.tobytes()
        crops.append({
            "item_id": item.item_id,
            "name": item.display_name,
            "bbox_xyxy": bbox,
            "dims_mm": (
                item.dimensions_mm.length_mm,
                item.dimensions_mm.width_mm,
                item.dimensions_mm.height_mm,
            ),
            "crop_bytes": crop_bytes,
        })
        if filename:
            item.visual_evidence.crop_url = f"/api/v1/assets/crops/{filename}"
    return crops
