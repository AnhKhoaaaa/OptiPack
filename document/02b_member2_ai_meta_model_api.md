# OptiPack — Member 2 Implementation Specification: AI & Meta Model API Integration (`02B_MEMBER2_AI_META_MODEL_API.md`)

- **Role Owner:** Member 2 — AI Systems & Meta Model API Engineer
- **Primary Module Path:** `backend/app/ai/`
- **Upstream Dependencies:** Cropped item images, full scene image, and initial dimension estimates from Member 1 (`backend/app/cv/`); `MODEL_API_KEY` environment variable
- **Downstream Consumers:** FastAPI Orchestrator (`/api/v1/orders/analyze`), Member 3 (`or_solver` consumes validated handling rules: `keep_upright`, `fragility_class`, `stackable`), Member 4 (`frontend_ui` displays semantic labels, provenance badges, and AI telemetry)
- **Contract Reference:** `01_PROJECT_SPEC.md` (`Contract v1.0.0`)

---

## 1. Role Objective & Scope Boundaries

Member 2 owns all interactions with the **Meta Model API** (`https://api.meta.ai/v1`), semantic packaging classification, visible handling-label extraction, output schema validation, rate-limit resilience, and offline fallback caching. Specifically, Member 2 is responsible for:

1. Integrating **`muse-spark-1.3`** via the OpenAI-compatible `/v1/responses` endpoint using **Structured Outputs (`json_schema`)** to classify detected items, read visible packaging text/icons (*"Fragile"*, *"This Side Up"*, *"Glass"*, battery marks), and recommend conservative packing rules.
2. Providing an optional **`sam-3.1`** segmentation adapter (`/v1/responses` with single-concept `input_text` prompts) + Python custom token/1-bit RLE mask parser to assist Member 1 on complex backgrounds.
3. Enforcing **Epistemic Honesty on Physical Properties**: strictly distinguishing between visually observable attributes (printed text, box material, bottle shape) and visually unobservable physical quantities (internal weight of an opaque sealed carton, internal cushioning quality), ensuring unobservable properties are returned as `null` / `"unknown"` rather than hallucinated numbers.
4. Providing a **zero-downtime Local Heuristic & Preset Cache Fallback** so the OptiPack pipeline and live hackathon demo never crash due to Wi-Fi dropouts, API rate limits, or quota exhaustion.

---

## 2. Verified Meta Model API Specification (`[Verified]`)

All parameters in this section were verified directly against the official Meta Developer Documentation ([Overview](https://dev.meta.ai/docs/overview), [Models & Pricing](https://dev.meta.ai/docs/pricing-rate-limits), [Structured Output](https://dev.meta.ai/docs/structured-output), [SAM Segmenting](https://dev.meta.ai/docs/sam/segmenting), [Vision Input](https://www.google.com/search?q=https://dev.meta.ai/docs/vision)).

### 2.1 Endpoint, Authentication & SDK Compatibility (`[Verified]`)

- **Base URL:** `https://api.meta.ai/v1`
- **Primary Endpoint:** `POST https://api.meta.ai/v1/responses` (OpenAI Responses API compatible) and `POST https://api.meta.ai/v1/files` (for large media uploads).
- **Authentication Header:** `Authorization: Bearer $MODEL_API_KEY`
- **Python Client:** Official `openai` Python SDK (`openai>=1.60.0`) initialized with `OpenAI(api_key=os.environ["MODEL_API_KEY"], base_url="https://api.meta.ai/v1")` or direct `httpx.AsyncClient` requests.

### 2.2 Model Catalog, Quotas & Pricing (`[Verified]`)

| Model ID | Release Status | Context / Limits | Rate Limits (Default Tier) | Pricing (USD) | Role in OptiPack MVP |
| :--- | :---: | :--- | :--- | :--- | :--- |
| **`muse-spark-1.3`** | **GA** | $1,000,000\text{ in} / 128,000\text{ out}$ tokens; up to ~50 images per request | $3,000\text{ RPM} / 4,000,000\text{ TPM}$ | $\$1.25 / 1\text{M in}$, $\$4.25 / 1\text{M out}$ | **Primary Multimodal Semantic Extractor** (item naming, visible label OCR, fragility/orientation priors). |
| **`muse-spark-1.3-contributor`** | **GA** | $1,000,000\text{ in} / 128,000\text{ out}$ tokens; logs opted-in for Meta improvement | $150\text{ RPM} / 200,000\text{ TPM}$ | $\$0.10 / 1\text{M in}$, $\$0.20 / 1\text{M out}$ | **Low-Cost Development / Testing Tier** ($12\times$ cheaper input, $21\times$ cheaper output during dev). |
| **`sam-3.1`** | **GA** | 1 image or 1 video (MP4/MOV) + **1 short noun phrase** per request | $3,000\text{ RPM}$ | $\$2.50 / 1\text{k images}$, $\$0.20 / 1\text{k video frames}$ (min 50 frames) | **Optional Cloud Segmentation Helper** for Member 1 (single-image keyframe mode only; never send full video streams). |
| **`muse-wonder-1.0`** | **Preview** | $1,000,000\text{ in} / 128,000\text{ out}$ tokens | $3,000\text{ RPM} / 4,000,000\text{ TPM}$ | $\$4.00 / 1\text{M in}$, $\$20.00 / 1\text{M out}$ | **Excluded from Critical Path** (`[Proposed]`): Preview status, higher latency, and $4.7\times$ higher output cost; spatial geometry belongs in Member 3's deterministic CP-SAT solver. |

### 2.3 Hard API Constraints & Gotchas (`[Verified]`)

1. **`muse-spark-1.3` Vision Role Constraint:** `input_image` blocks **MUST ONLY** be placed inside messages with `"role": "user"`. Placing an `input_image` block inside a `"system"` or `"developer"` message immediately returns **`HTTP 400 Bad Request`** (`[Verified]` via [Vision Input Docs](https://www.google.com/search?q=https://dev.meta.ai/docs/vision)).
2. **`sam-3.1` Single-Concept Prompt Constraint:** `sam-3.1` accepts **only one short noun phrase** (`1–3 words`, e.g., `"box"` or `"package"`) per request. Passing comma-separated or semicolon-separated lists (e.g., `"box, bottle, book"`) causes the API to return **zero matches** (`[Verified]` via [SAM Segmenting Docs](https://dev.meta.ai/docs/sam/segmenting)).
3. **`sam-3.1` No Visual Prompting in Cloud API:** Unlike the open-weight SAM 3 checkpoint on GitHub, the hosted `/v1/responses` API for `sam-3.1` does **not** accept 2D bounding-box coordinates or point clicks as prompts—only `input_text` + `input_image`/`input_video` (`[Verified]`).
4. **`sam-3.1` Custom Output Stream Format:** `sam-3.1` does not return standard JSON objects; it outputs a text string formatted as `<0f>0<|box;x1=...;y1=...;x2=...;y2=...;w=...;h=...|}><|mask;x=0;y=0;data=...|>` (with `metadata={"mask_encoding": "one_bit"}` recommended). Because the official `@meta-sam/parser` package is Node.js ESM only, Member 2 provides a clean 40-line Python regex parser (`parse_sam31_response()`) (`[Verified]`).

---

## 3. Physical Property Inference Policy (What AI Can vs. Cannot Know)

> **CRITICAL ENGINEERING RULE (`[Verified]`):** A vision-language model inspecting an RGB photo of a closed cardboard box **cannot see inside the box** and **cannot weigh the box**. Pretending that `muse-spark-1.3` knows the exact weight in grams or internal fragility of an unmarked opaque carton is scientifically invalid.

Member 2's prompt and schema enforce the following strict separation:

| Attribute | Visually Observable When... | AI Output Rule when Observable | AI Output Rule when Unobservable |
| :--- | :--- | :--- | :--- |
| **`display_name` & `category`** | Packaging graphics, brand logo, or item shape is visible. | Specific name (e.g., `"Logitech Mouse Retail Box"`, `"electronics_boxed"`). | Generic descriptive name (`"Brown Corrugated Box #2"`, `"generic_carton"`). |
| **`visible_labels`** | Text or symbols (`"FRAGILE"`, `"THIS SIDE UP"`, $\uparrow\uparrow$, wine glass icon, `"UN3481"` battery mark) are legible on the visible faces. | Exact list of transcribed strings, e.g., `["FRAGILE", "THIS SIDE UP"]`. | Empty list `[]`. |
| **`keep_upright`** | `"THIS SIDE UP"` arrow symbol or liquid bottle cap/neck is clearly visible. | `true`, with `orientation_source: "visible_label"` or `"liquid_container_shape"`. | `false`, with `orientation_source: "default_unconstrained"` (operator can toggle in UI). |
| **`fragility_class`** | Glass container, ceramic item, `"FRAGILE"` sticker, or thin electronics retail box is visible. | `"high"` or `"medium"`, with `fragility_source: "visible_label"` or `"ai_inferred_packaging"`. | `"unknown"` (mapped to conservative `"medium"` default only after flagging `requires_user_review: true`). |
| **`weight_g`** | **ONLY** if net weight is explicitly printed in large legible text on the front of the consumer package (e.g., `"NET WT 500g"` on a coffee bag/box). | Integer grams (e.g., `500`) with `weight_source: "printed_net_weight_ocr"`. | **`null`** with `weight_source: "unknown"`. **Never guess weight from box size in the LLM!** |

---

## 4. Prompt Engineering & Structured JSON Schema for `muse-spark-1.3`

### 4.1 Batched Multi-Crop Request Strategy (`[Proposed]`)

Instead of making $N$ separate sequential API calls for $N$ items (which multiplies latency by $N$), Member 2 sends **a single batched `/v1/responses` request** containing:
1. A `"developer"` text instruction defining the strict physical-property rules.
2. A single `"user"` message containing:
   - The annotated overview image (`top_image` with labeled bounding boxes `item_01` ... `item_N` and their CV-measured $(L, W, H)$ in `mm`), followed by
   - Individual high-resolution cropped images of `item_01` ... `item_N`.
3. A strict `text.format` (`json_schema`) declaration guaranteeing 100% syntactically valid JSON output.

### 4.2 Strict JSON Schema Definition (`MUSE_SEMANTIC_SCHEMA`)

```python
MUSE_SEMANTIC_JSON_SCHEMA = {
    "name": "optipack_order_semantics",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
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
                                "other_rigid"
                            ]
                        },
                        "visible_labels": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "printed_weight_g": {
                            "type": ["integer", "null"],
                            "description": "ONLY populate if weight in grams/oz is explicitly printed and readable on the packaging. Otherwise MUST be null."
                        },
                        "fragility_class": {
                            "type": "string",
                            "enum": ["low", "medium", "high", "unknown"]
                        },
                        "fragility_source": {
                            "type": "string",
                            "enum": ["visible_label", "ai_inferred_packaging", "unknown"]
                        },
                        "keep_upright": {"type": "boolean"},
                        "orientation_source": {
                            "type": "string",
                            "enum": ["visible_label", "liquid_container_shape", "default_unconstrained"]
                        },
                        "stackable": {"type": "boolean"},
                        "reasoning_note": {"type": "string"}
                    },
                    "required": [
                        "item_id", "display_name", "category", "visible_labels",
                        "printed_weight_g", "fragility_class", "fragility_source",
                        "keep_upright", "orientation_source", "stackable", "reasoning_note"
                    ],
                    "additionalProperties": False
                }
            }
        },
        "required": ["items"],
        "additionalProperties": False
    }
}
```

---

## 5. Reference Implementation Pseudocode (`backend/app/ai/meta_client.py`)

```python
import base64
import json
import os
import re
import time
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel, Field, ValidationError

META_API_BASE_URL = "https://api.meta.ai/v1"

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

def encode_image_data_url(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{b64}"

async def analyze_items_with_muse_spark(
    overview_image_bytes: bytes,
    item_crops: List[Dict[str, Any]],  # [{"item_id": "item_01", "crop_bytes": b"...", "dims_mm": (210,165,95)}]
    model_name: str = "muse-spark-1.3",
    timeout_sec: float = 4.5,
) -> Dict[str, Any]:
    api_key = os.getenv("MODEL_API_KEY", "").strip()
    if not api_key:
        return build_deterministic_fallback_semantics(item_crops, reason="missing_api_key")

    user_content: List[Dict[str, Any]] = [
        {
            "type": "input_text",
            "text": (
                "Analyze the following e-commerce order items captured on a packing table. "
                "Image 1 is the annotated tabletop overview. Subsequent images are individual item crops. "
                "STRICT RULES:\n"
                "1. Set printed_weight_g ONLY if a net weight is legibly printed on the package; otherwise set null.\n"
                "2. Set keep_upright=true ONLY if 'THIS SIDE UP' arrows or a liquid bottle cap/neck are visible.\n"
                "3. If an item is an unmarked opaque box with no visible clues, set fragility_class='unknown' and fragility_source='unknown'."
            ),
        },
        {
            "type": "input_image",
            "image_url": encode_image_data_url(overview_image_bytes),
        },
    ]

    for crop in item_crops:
        L, W, H = crop["dims_mm"]
        user_content.append({
            "type": "input_text",
            "text": f"Item ID: {crop['item_id']} | CV Measured Dimensions: {L}x{W}x{H} mm"
        })
        user_content.append({
            "type": "input_image",
            "image_url": encode_image_data_url(crop["crop_bytes"]),
        })

    payload = {
        "model": model_name,
        "input": [
            {
                "role": "developer",
                "content": "You are a precise e-commerce packaging inspection engine. Output strict JSON matching the schema."
            },
            {
                "role": "user",
                "content": user_content  # CRITICAL: input_image MUST only appear in 'user' role!
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                **MUSE_SEMANTIC_JSON_SCHEMA
            }
        }
    }

    t0 = time.perf_counter()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                resp = await client.post(f"{META_API_BASE_URL}/responses", headers=headers, json=payload)
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(0.4 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            raw_text = extract_output_text_from_responses_api(data)
            parsed = MuseBatchOutput.model_validate_json(raw_text)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return {
                "status": "success",
                "model": model_name,
                "latency_ms": latency_ms,
                "fallback_activated": False,
                "items": {item.item_id: item.model_dump() for item in parsed.items}
            }
        except Exception as exc:
            last_err = str(exc)

    return build_deterministic_fallback_semantics(item_crops, reason=f"api_error: {last_err}")

# Python parser for sam-3.1 special-token output:
# Format: <0f>0<|box;x1=12;y1=34;x2=100;y2=200;w=88;h=166|><|mask;x=0;y=0;data=...|><|/0f|>
SAM31_OBJECT_REGEX = re.compile(
    r"(?P<obj_id>\d+)<\|box;x1=(?P<x1>\d+);y1=(?P<y1>\d+);x2=(?P<x2>\d+);y2=(?P<y2>\d+);w=(?P<w>\d+);h=(?P<h>\d+)\|>"
    r"(?:<\|mask;x=(?P<mx>\d+);y=(?P<my>\d+);data=(?P<mdata>[^|]+)\|>)"
)

def parse_sam31_response(raw_stream_text: str) -> List[Dict[str, Any]]:
    detections = []
    for match in SAM31_OBJECT_REGEX.finditer(raw_stream_text):
        detections.append({
            "obj_id": int(match.group("obj_id")),
            "bbox_xyxy": [
                int(match.group("x1")), int(match.group("y1")),
                int(match.group("x2")), int(match.group("y2"))
            ],
            "mask_origin_xy": (int(match.group("mx")), int(match.group("my"))),
            "mask_b64_data": match.group("mdata"),
        })
    return detections
```

---

## 6. Post-Validation & Sanitization Rules (`backend/app/ai/sanitizer.py`)

Even when `muse-spark-1.3` returns valid JSON matching `MUSE_SEMANTIC_JSON_SCHEMA`, Member 2 applies deterministic post-validation rules before returning `OrderAnalysisResponse`:

1. **Orientation Filtering:**
   - If `keep_upright == True`, restrict `allowed_rotations` to `["LWH", "WLH"]`.
   - Otherwise, set `allowed_rotations` to all 6 rotations `["LWH", "WLH", "LHW", "HLW", "WHL", "HWL"]`.
2. **Fragility-to-Load Mapping:**
   - `"high"` fragility (or `stackable == False`) $\rightarrow$ `max_top_load_g = 0` (nothing can be stacked on top of this item).
   - `"medium"` fragility $\rightarrow$ `max_top_load_g = 2000`.
   - `"low"` fragility $\rightarrow$ `max_top_load_g = 8000`.
   - `"unknown"` fragility $\rightarrow$ map to conservative `"medium"` (`max_top_load_g = 2000`) AND set `requires_user_review = True`.
3. **Weight Sanity Guard:**
   - If `printed_weight_g` is populated by OCR, verify it is between $5\text{ g}$ and $25,000\text{ g}$; if outside that range, discard it (`weight_g = None`, `weight_source = "unknown"`).

---

## 7. Phase 0 Proof-of-Feasibility Experiment (`Member 2 Gate`)

Member 2 must execute the following standalone verification script in `experiments/phase0_meta_api.py` immediately upon obtaining `MODEL_API_KEY`:

| Experiment Field | Concrete Specification |
| :--- | :--- |
| **1. Hypothesis** | The live Meta Model API (`https://api.meta.ai/v1/responses`) supports `muse-spark-1.3` with multi-image `input_image` payloads in the `user` role and strict `json_schema` structured outputs within $\le 3.5\text{ s}$ latency, and `sam-3.1` returns parseable `<\|box...\|><\|mask...\|>` tokens for single-concept prompts (`"box"`). |
| **2. Question Being Tested** |1) Does our hackathon `MODEL_API_KEY` have active quota for both `muse-spark-1.3` and `sam-3.1`? 2) Does `muse-spark-1.3` honor the exact `MUSE_SEMANTIC_JSON_SCHEMA` without `HTTP 400` errors? 3) What is the real end-to-end latency from our network location? |
| **3. Setup** | Python 3.11 environment with `httpx`, `openai`, `pydantic`; valid `MODEL_API_KEY`; 5 sample tabletop photos and 15 cropped item photos (including 2 items with visible `"FRAGILE"` / `"THIS SIDE UP"` stickers and 3 unmarked boxes). |
| **4. Procedure** |1) Run 10 batched calls to `muse-spark-1.3` (and `muse-spark-1.3-contributor`) with 1 overview + 4 crop images per request. 2) Run 5 single-image calls to `sam-3.1` with prompt `"box"` and `metadata={"mask_encoding": "one_bit"}`. 3) Measure HTTP status codes, P50/P95 latency, JSON schema validation rate, and label detection accuracy. |
| **5. Expected Output** | JSON benchmark report `experiments/logs/phase0_meta_api_benchmark.json` logging status codes, latency distribution (`ms`), token usage, and parsed outputs. |
| **6. Evaluation Metric** | Schema compliance rate ($\%$), P95 latency ($\text{ms}$), false-hallucination rate on unobservable weights ($\%$), and `sam-3.1` regex parse success rate ($\%$). |
| **7. Pass Criteria** |1) $100\%$ of `muse-spark-1.3` responses pass `MuseBatchOutput.model_validate_json()`; 2) P95 latency $\le 4,000\text{ ms}$; 3) $0\%$ fabricated weights on unmarked boxes; 4) Visible `"FRAGILE"` / `"THIS SIDE UP"` stickers detected on $100\%$ of labeled test crops. |
| **8. Fail Criteria** |1) `MODEL_API_KEY` lacks access or hits persistent 401/403/429 errors; OR 2) `json_schema` mode returns HTTP 400 on multi-image inputs; OR 3) P95 latency exceeds $6,000\text{ ms}$. |
| **9. Fallback** | **Fallback 2A (`json_schema` incompat with multi-image):** Send a single composite collage image (overview + numbered crop strip stitched side-by-side in OpenCV) with prompt-enforced JSON + regex JSON block extraction.<br/>**Fallback 2B (High latency or quota failure):** Switch dev testing to `muse-spark-1.3-contributor` and enable deterministic SHA-256 image-hash response caching (`backend/app/ai/cache/`) + instant local heuristic fallback after a $3.5\text{ s}$ timeout. |
| **10. Decision Owner** | **Member 2**. |
| **11. Team Escalation Condition** | Escalate to Member 1 if `sam-3.1` latency exceeds $3.0\text{ s}$ (confirming Member 1 should rely exclusively on local OpenCV segmentation for the live demo) or to all members if `MODEL_API_KEY` authentication fails. |
| **12. Time / Effort Boundary** | **Maximum 3 hours** during Phase 0. |

---

## 8. Mandatory Failure-Handling & Escalation Procedure (7 Steps)

If Member 2's Phase 0 experiment hits any **Fail Criterion**:

1. **Step 1 — Record Evidence:** Save full HTTP request/response headers (redacting the API key), status codes, error payloads, and latency timings in `experiments/logs/phase0_ai_failure_report.md`.
2. **Step 2 — Classify Root Cause:** Distinguish between:
   - *Auth / Quota Error* (`401`, `403`, `429`),
   - *Payload Formatting Error* (`400 Bad Request` from `json_schema` syntax or image encoding size),
   - *Latency / Network Bottleneck* (large base64 payload upload delay), or
   - *SAM 3.1 Token Parsing Mismatch*.
3. **Step 3 — Check Scope vs. Cross-Module Impact:** Downscaling images to max $1024\text{ px}$ long edge before base64 encoding or switching from multi-image array to a single stitched composite image is **100% internal to Member 2** and requires zero changes from Members 1, 3, or 4.
4. **Step 4 — Evaluate Pre-Defined Fallbacks:** Test Fallback 2A (stitched single-image collage + downscaled JPEG quality `80`) and Fallback 2B (local SHA-256 disk cache + heuristic fallback).
5. **Step 5 — Propose Concrete Action:** Notify the team in the shared channel which payload encoding and timeout threshold ($3.5\text{ s}$) are locked in.
6. **Step 6 — Update Shared Documentation:** Record the verified P50/P95 latency and active model tier in `01_PROJECT_SPEC.md` and `03_EXECUTION_PLAN.md`.
7. **Step 7 — Freeze Contract & Proceed:** Guarantee that `analyze_items_with_muse_spark()` always returns a valid dictionary matching `OrderAnalysisResponse` within $4.0\text{ seconds}$ wall-clock time.

---

## 9. Unit & Integration Test Cases (`tests/test_ai_meta_api.py`)

1. **`test_user_role_only_vision_payload`:** Inspect the generated JSON request body for `/v1/responses` and assert that no message with `role in ("system", "developer")` contains an `"input_image"` block.
2. **`test_unobservable_weight_sanitization`:** Pass a mock LLM response where `fragility_class="unknown"` and `printed_weight_g=None`. Assert the sanitizer outputs `weight_g=None`, `weight_source="unknown"`, and appends a clear human-readable warning to `global_warnings`.
3. **`test_keep_upright_rotation_restriction`:** Assert that when `keep_upright=True`, `allowed_rotations` is strictly `["LWH", "WLH"]`, and when `keep_upright=False`, all 6 rotation codes are present.
4. **`test_timeout_triggers_clean_fallback`:** Simulate an `httpx.TimeoutException` on `/v1/responses`. Assert the client catches the timeout within the configured window and returns a valid fallback response with `ai_telemetry.fallback_activated == True` and HTTP 200.
5. **`test_sam31_regex_parser`:** Pass a sample `<0f>0<|box;x1=10;y1=20;x2=110;y2=220;w=100;h=200|><|mask;x=0;y=0;data=AAAA|><|/0f|>` string into `parse_sam31_response()` and assert it extracts `obj_id=0` and `bbox_xyxy=[10, 20, 110, 220]`.
