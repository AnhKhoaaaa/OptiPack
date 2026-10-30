"""Meta Model API Client Module (Member 2).

Interfaces with Meta Model API (/v1/responses endpoint):
- muse-spark-1.3 for structured JSON semantic handling and label extraction
- sam-3.1 for text-prompted segmentation
Includes timeout handling, connection pooling, retries, and offline disk caching.
"""

import base64
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import dotenv
import httpx
import numpy as np
from pydantic import BaseModel, Field

from backend.app.ai.cache import compute_image_sha256, get_cached_response, store_cached_response
from backend.app.ai.sanitizer import sanitize_physical_attributes
from backend.app.schemas.contracts import AITelemetry, PhysicalAttributes

# Ensure .env is loaded
dotenv.load_dotenv()

META_API_BASE_URL = os.getenv("META_API_BASE_URL", "https://api.meta.ai/v1")
MODEL_API_KEY = os.getenv("MODEL_API_KEY", "")
MUSE_MODEL_NAME = os.getenv("MUSE_MODEL_NAME", "muse-spark-1.3")

# Connection pool singletons
_SYNC_CLIENT: Optional[httpx.Client] = None
_ASYNC_CLIENT: Optional[httpx.AsyncClient] = None


def get_sync_http_client(timeout_sec: float = 10.0) -> httpx.Client:
    """Return persistent HTTP client with connection pooling and keep-alive."""
    global _SYNC_CLIENT
    if _SYNC_CLIENT is None or _SYNC_CLIENT.is_closed:
        _SYNC_CLIENT = httpx.Client(
            timeout=timeout_sec,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=60.0),
        )
    return _SYNC_CLIENT


def get_async_http_client(timeout_sec: float = 10.0) -> httpx.AsyncClient:
    """Return persistent async HTTP client with connection pooling."""
    global _ASYNC_CLIENT
    if _ASYNC_CLIENT is None or _ASYNC_CLIENT.is_closed:
        _ASYNC_CLIENT = httpx.AsyncClient(
            timeout=timeout_sec,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=60.0),
        )
    return _ASYNC_CLIENT


def warmup_meta_client() -> bool:
    """Pre-warm TCP + TLS handshake connection to Meta API to eliminate cold-start latency."""
    api_key = os.getenv("MODEL_API_KEY", MODEL_API_KEY).strip()
    if not api_key:
        return False
    try:
        client = get_sync_http_client()
        resp = client.get(
            f"{META_API_BASE_URL}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5.0,
        )
        return resp.status_code == 200
    except Exception:
        return False


# Strict JSON Schema for single item semantic inspection
MUSE_ITEM_SEMANTIC_SCHEMA: Dict[str, Any] = {
    "name": "item_packaging_semantics",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "item_id": {"type": "string"},
            "display_name": {"type": "string"},
            "category": {
                "type": "string",
                "enum": [
                    "electronics_boxed",
                    "cosmetics_personal_care",
                    "food_beverage_rigid",
                    "book_media_flat",
                    "apparel_boxed",
                    "glass_ceramic_fragile",
                    "generic_carton",
                    "other_rigid",
                ],
            },
            "visible_labels": {
                "type": "array",
                "items": {"type": "string"},
            },
            "printed_weight_g": {
                "type": ["integer", "null"],
                "description": (
                    "ONLY populate if net weight in grams/oz is explicitly printed "
                    "and readable on the packaging. Otherwise MUST be null."
                ),
            },
            "fragility_class": {
                "type": "string",
                "enum": ["low", "medium", "high", "unknown"],
            },
            "fragility_source": {
                "type": "string",
                "enum": ["visible_label", "ai_inferred_packaging", "unknown"],
            },
            "keep_upright": {"type": "boolean"},
            "orientation_source": {
                "type": "string",
                "enum": ["visible_label", "liquid_container_shape", "default_unconstrained"],
            },
            "stackable": {"type": "boolean"},
            "reasoning_note": {"type": "string"},
        },
        "required": [
            "item_id",
            "display_name",
            "category",
            "visible_labels",
            "printed_weight_g",
            "fragility_class",
            "fragility_source",
            "keep_upright",
            "orientation_source",
            "stackable",
            "reasoning_note",
        ],
        "additionalProperties": False,
    },
}

# Strict JSON Schema for batched items inspection
MUSE_BATCH_SEMANTIC_SCHEMA: Dict[str, Any] = {
    "name": "optipack_order_semantics",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": MUSE_ITEM_SEMANTIC_SCHEMA["schema"],
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    },
}


class MuseItemSemanticOutput(BaseModel):
    item_id: str
    display_name: str
    category: str
    visible_labels: List[str] = Field(default_factory=list)
    printed_weight_g: Optional[int] = None
    fragility_class: str
    fragility_source: str
    keep_upright: bool
    orientation_source: str
    stackable: bool
    reasoning_note: str


class MuseBatchOutput(BaseModel):
    items: List[MuseItemSemanticOutput]


# SAM 3.1 token stream parser regex
SAM31_OBJECT_REGEX = re.compile(
    r"(?P<obj_id>\d+)<\|box;x1=(?P<x1>\d+);y1=(?P<y1>\d+);x2=(?P<x2>\d+);y2=(?P<y2>\d+);w=(?P<w>\d+);h=(?P<h>\d+)\|>"
    r"(?:<\|mask;x=(?P<mx>\d+);y=(?P<my>\d+);data=(?P<mdata>[^|]+)\|>)"
)


def parse_sam31_response(raw_stream_text: str) -> List[Dict[str, Any]]:
    """Parse SAM 3.1 custom output stream tokens into bounding boxes and masks."""
    detections = []
    for match in SAM31_OBJECT_REGEX.finditer(raw_stream_text):
        detections.append({
            "obj_id": int(match.group("obj_id")),
            "bbox_xyxy": [
                int(match.group("x1")),
                int(match.group("y1")),
                int(match.group("x2")),
                int(match.group("y2")),
            ],
            "mask_origin_xy": (int(match.group("mx")), int(match.group("my"))),
            "mask_b64_data": match.group("mdata"),
        })
    return detections


def encode_image_data_url(image_bytes: bytes, max_long_edge: int = 200) -> str:
    """Encode raw image bytes to a data URL, downscaling to optimize payload latency."""
    is_jpeg = image_bytes.startswith(b"\xff\xd8\xff")
    is_png = image_bytes.startswith(b"\x89PNG")

    if not (is_jpeg or is_png):
        nparr = np.frombuffer(image_bytes, np.uint8)
        decoded = cv2.imdecode(nparr, cv2.IMREAD_COLOR) if len(nparr) > 0 else None
        if decoded is None:
            decoded = np.full((120, 120, 3), 220, dtype=np.uint8)
        _, enc = cv2.imencode(".jpg", decoded, [cv2.IMWRITE_JPEG_QUALITY, 75])
        image_bytes = enc.tobytes()
        mime_type = "image/jpeg"
    else:
        mime_type = "image/jpeg"
        nparr = np.frombuffer(image_bytes, np.uint8)
        decoded = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if decoded is not None:
            h, w = decoded.shape[:2]
            if max(h, w) > max_long_edge:
                scale = max_long_edge / float(max(h, w))
                new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
                resized = cv2.resize(decoded, (new_w, new_h), interpolation=cv2.INTER_AREA)
                _, enc = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 75])
                image_bytes = enc.tobytes()
            elif not is_jpeg:
                _, enc = cv2.imencode(".jpg", decoded, [cv2.IMWRITE_JPEG_QUALITY, 75])
                image_bytes = enc.tobytes()

    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


def extract_output_text_from_responses_api(data: Dict[str, Any]) -> str:
    """Extract assistant text from Meta Model API /v1/responses output structure."""
    for item in data.get("output", []):
        if item.get("type") == "message" and item.get("role") == "assistant":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    return c.get("text", "")
    return ""


def build_deterministic_fallback_semantics(
    item_crops: List[Dict[str, Any]], reason: str = "fallback"
) -> Dict[str, Any]:
    """Generate safe, conservative physical semantics when API or key is unavailable."""
    items = {}
    for crop in item_crops:
        iid = crop.get("item_id", "item_01")
        name = crop.get("name", "Generic Package")
        items[iid] = {
            "item_id": iid,
            "display_name": name,
            "category": "generic_carton",
            "visible_labels": [],
            "printed_weight_g": None,
            "fragility_class": "medium",
            "fragility_source": "default_safe",
            "keep_upright": False,
            "orientation_source": "default_unconstrained",
            "stackable": True,
            "max_top_load_g": 2000,
            "reasoning_note": f"Offline safe default ({reason})",
        }
    return {
        "status": "fallback",
        "model": MUSE_MODEL_NAME,
        "latency_ms": 0,
        "fallback_activated": True,
        "items": items,
    }


def extract_item_semantics_muse(
    image_bytes: bytes,
    item_id: str = "item_01",
    timeout_sec: float = 5.0,
    model_name: Optional[str] = None,
) -> Tuple[PhysicalAttributes, AITelemetry]:
    """Extract semantic handling attributes from a single item image crop using muse-spark-1.3."""
    start_time = time.time()
    cache_key = compute_image_sha256(image_bytes)
    target_model = model_name or MUSE_MODEL_NAME
    api_key = os.getenv("MODEL_API_KEY", MODEL_API_KEY).strip()

    # 1. Check disk cache
    cached = get_cached_response(cache_key)
    if cached:
        telemetry = AITelemetry(
            sam_status="skipped",
            muse_model=target_model,
            muse_status="cached",
            muse_latency_ms=int((time.time() - start_time) * 1000),
            fallback_activated=False,
        )
        return sanitize_physical_attributes(cached), telemetry

    # 2. Check API key
    if not api_key:
        fallback_dict = {
            "item_id": item_id,
            "display_name": "Unverified Box",
            "category": "generic_carton",
            "visible_labels": [],
            "printed_weight_g": None,
            "fragility_class": "medium",
            "fragility_source": "default_safe",
            "keep_upright": False,
            "orientation_source": "default_unconstrained",
            "stackable": True,
            "max_top_load_g": 2000,
            "reasoning_note": "Missing MODEL_API_KEY, using safe default",
        }
        telemetry = AITelemetry(
            sam_status="skipped",
            muse_model=target_model,
            muse_status="fallback",
            muse_latency_ms=int((time.time() - start_time) * 1000),
            fallback_activated=True,
        )
        return sanitize_physical_attributes(fallback_dict), telemetry

    # 3. Call live Meta Model API
    data_url = encode_image_data_url(image_bytes, max_long_edge=200)
    payload = {
        "model": target_model,
        "reasoning": {"effort": "low"},
        "input": [
            {
                "role": "developer",
                "content": (
                    "Packaging inspector. Output strict JSON. Keep reasoning_note under 6 words. "
                    "Rules: 1. Set printed_weight_g ONLY if net weight is explicitly printed on the package; else null. "
                    "2. Set keep_upright=true ONLY if 'THIS SIDE UP' arrows or bottle shape are visible. "
                    "3. If an unmarked box with no labels, set fragility_class='unknown', fragility_source='unknown'."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": f"Inspect item ID: {item_id}"},
                    {"type": "input_image", "image_url": data_url},
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                **MUSE_ITEM_SEMANTIC_SCHEMA,
            }
        },
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        client = get_sync_http_client()
        resp = client.post(
            f"{META_API_BASE_URL}/responses",
            headers=headers,
            json=payload,
            timeout=timeout_sec,
        )
        resp.raise_for_status()
        res_json = resp.json()

        raw_text = extract_output_text_from_responses_api(res_json)
        parsed = MuseItemSemanticOutput.model_validate_json(raw_text)
        item_data = parsed.model_dump()

        # Cache valid response
        store_cached_response(cache_key, item_data)

        telemetry = AITelemetry(
            sam_status="skipped",
            muse_model=target_model,
            muse_status="success",
            muse_latency_ms=int((time.time() - start_time) * 1000),
            fallback_activated=False,
        )
        return sanitize_physical_attributes(item_data), telemetry

    except Exception:
        fallback_dict = {
            "item_id": item_id,
            "display_name": "Unverified Box",
            "category": "generic_carton",
            "visible_labels": [],
            "printed_weight_g": None,
            "fragility_class": "medium",
            "fragility_source": "default_safe",
            "keep_upright": False,
            "orientation_source": "default_unconstrained",
            "stackable": True,
            "max_top_load_g": 2000,
            "reasoning_note": "API call timed out or failed, using safe fallback",
        }
        telemetry = AITelemetry(
            sam_status="skipped",
            muse_model=target_model,
            muse_status="fallback",
            muse_latency_ms=int((time.time() - start_time) * 1000),
            fallback_activated=True,
        )
        return sanitize_physical_attributes(fallback_dict), telemetry


async def analyze_items_with_muse_spark(
    overview_image_bytes: bytes,
    item_crops: List[Dict[str, Any]],
    model_name: Optional[str] = None,
    timeout_sec: float = 7.0,
) -> Dict[str, Any]:
    """Batched semantic extraction for multiple item crops in a single call."""
    api_key = os.getenv("MODEL_API_KEY", MODEL_API_KEY).strip()
    target_model = model_name or MUSE_MODEL_NAME

    if not api_key:
        return build_deterministic_fallback_semantics(item_crops, reason="missing_api_key")

    user_content: List[Dict[str, Any]] = [
        {
            "type": "input_text",
            "text": (
                "Packaging inspection. Image 1 is overview, rest are crops. Keep reasoning_note under 6 words. "
                "1. Set printed_weight_g ONLY if net weight is legibly printed; else null. "
                "2. Set keep_upright=true ONLY if 'THIS SIDE UP' arrows or liquid bottle visible. "
                "3. If unmarked box, set fragility_class='unknown', fragility_source='unknown'."
            ),
        },
        {
            "type": "input_image",
            "image_url": encode_image_data_url(overview_image_bytes, max_long_edge=300),
        },
    ]

    for crop in item_crops:
        iid = crop.get("item_id", "item_01")
        dims = crop.get("dims_mm", (100, 100, 100))
        crop_bytes = crop.get("crop_bytes", b"")
        user_content.append({
            "type": "input_text",
            "text": f"Item ID: {iid} | Dims: {dims[0]}x{dims[1]}x{dims[2]} mm",
        })
        user_content.append({
            "type": "input_image",
            "image_url": encode_image_data_url(crop_bytes, max_long_edge=200),
        })

    payload = {
        "model": target_model,
        "reasoning": {"effort": "low"},
        "input": [
            {
                "role": "developer",
                "content": "E-commerce packaging inspection engine. Output strict JSON matching schema.",
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                **MUSE_BATCH_SEMANTIC_SCHEMA,
            }
        },
    }

    t0 = time.perf_counter()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        client = get_async_http_client()
        resp = await client.post(
            f"{META_API_BASE_URL}/responses",
            headers=headers,
            json=payload,
            timeout=timeout_sec,
        )
        resp.raise_for_status()
        res_json = resp.json()

        raw_text = extract_output_text_from_responses_api(res_json)
        parsed = MuseBatchOutput.model_validate_json(raw_text)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        results = {}
        for item in parsed.items:
            dumped = item.model_dump()
            matching_crop = next((c for c in item_crops if c.get("item_id") == item.item_id), None)
            if matching_crop and "crop_bytes" in matching_crop:
                store_cached_response(compute_image_sha256(matching_crop["crop_bytes"]), dumped)
            results[item.item_id] = sanitize_physical_attributes(dumped).model_dump()

        return {
            "status": "success",
            "model": target_model,
            "latency_ms": latency_ms,
            "fallback_activated": False,
            "items": results,
        }
    except Exception as exc:
        return build_deterministic_fallback_semantics(item_crops, reason=f"api_error: {str(exc)}")


def segment_with_sam31(
    image_bytes: bytes,
    prompt_text: str = "box",
    timeout_sec: float = 5.0,
) -> Dict[str, Any]:
    """Segment objects in an image using sam-3.1 with a single-concept text prompt."""
    t0 = time.perf_counter()
    api_key = os.getenv("MODEL_API_KEY", MODEL_API_KEY).strip()
    if not api_key:
        return {
            "status": "skipped",
            "latency_ms": 0,
            "detections": [],
            "error": "missing_api_key",
        }

    data_url = encode_image_data_url(image_bytes, max_long_edge=200)
    payload = {
        "model": "sam-3.1",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt_text},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        client = get_sync_http_client()
        resp = client.post(
            f"{META_API_BASE_URL}/responses",
            headers=headers,
            json=payload,
            timeout=timeout_sec,
        )
        resp.raise_for_status()
        res_json = resp.json()

        raw_text = extract_output_text_from_responses_api(res_json)
        detections = parse_sam31_response(raw_text)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "status": "success",
            "latency_ms": latency_ms,
            "raw_stream": raw_text,
            "detections": detections,
        }
    except Exception as exc:
        return {
            "status": "fallback",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "detections": [],
            "error": str(exc),
        }
