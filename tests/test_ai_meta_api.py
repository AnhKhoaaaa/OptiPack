"""Unit and Integration Tests for AI & Meta Model API Module (Member 2).

Conforms to 02b_member2_ai_meta_model_api.md Section 9:
1. test_user_role_only_vision_payload
2. test_unobservable_weight_sanitization
3. test_keep_upright_rotation_restriction
4. test_timeout_triggers_clean_fallback
5. test_sam31_regex_parser
"""

import os
import pytest
from unittest.mock import patch, MagicMock
import httpx

from backend.app.ai.meta_client import (
    analyze_items_with_muse_spark,
    extract_item_semantics_muse,
    parse_sam31_response,
    MUSE_ITEM_SEMANTIC_SCHEMA,
    MUSE_BATCH_SEMANTIC_SCHEMA,
)
from backend.app.ai.sanitizer import (
    derive_allowed_rotations,
    sanitize_physical_attributes,
)
from backend.app.schemas.contracts import RotationCode


def test_user_role_only_vision_payload():
    """Verify that input_image blocks are strictly confined to 'user' messages.
    
    Per Meta Model API constraints, putting input_image in 'developer' or 'system'
    results in HTTP 400 Bad Request.
    """
    dummy_bytes = b"\xff\xd8\xff\xe0" + os.urandom(32)

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            '{"item_id":"item_test","display_name":"Test Box","category":"generic_carton",'
                            '"visible_labels":[],"printed_weight_g":null,"fragility_class":"medium",'
                            '"fragility_source":"default_safe","keep_upright":false,'
                            '"orientation_source":"default_unconstrained","stackable":true,'
                            '"reasoning_note":"unit test"}'
                        ),
                    }
                ],
            }
        ]
    }
    mock_client.post.return_value = mock_resp

    with patch.dict(os.environ, {"MODEL_API_KEY": "mock_api_key_for_testing"}):
        with patch("backend.app.ai.meta_client.get_cached_response", return_value=None):
            with patch("backend.app.ai.meta_client.store_cached_response"):
                with patch("backend.app.ai.meta_client.get_sync_http_client", return_value=mock_client):
                    extract_item_semantics_muse(dummy_bytes, item_id="item_test")

                assert mock_client.post.called
                call_kwargs = mock_client.post.call_args[1]
                payload = call_kwargs["json"]

                # Verify messages inside payload
                for msg in payload["input"]:
                    role = msg.get("role")
                    content = msg.get("content", [])
                    if role in ("system", "developer"):
                        if isinstance(content, list):
                            for part in content:
                                assert part.get("type") != "input_image", "input_image found in developer/system role!"
                        elif isinstance(content, str):
                            assert "input_image" not in content
                    elif role == "user":
                        if isinstance(content, list):
                            has_image = any(part.get("type") == "input_image" for part in content)
                            assert has_image, "User role should contain the input_image block"


def test_unobservable_weight_sanitization():
    """Verify that unobservable weight on unmarked opaque box is stripped.
    
    Guarantees epistemic honesty: weight_g MUST be None and weight_source MUST be 'unknown'.
    """
    raw_response = {
        "item_id": "box_01",
        "display_name": "Brown Opaque Box",
        "category": "generic_carton",
        "visible_labels": [],
        "printed_weight_g": None,
        "fragility_class": "unknown",
        "fragility_source": "unknown",
        "keep_upright": False,
        "orientation_source": "default_unconstrained",
        "stackable": True,
        "reasoning_note": "No markings visible",
    }

    sanitized = sanitize_physical_attributes(raw_response)

    assert sanitized.weight_g is None
    assert sanitized.weight_source == "unknown"
    assert sanitized.fragility_class == "unknown"
    assert sanitized.max_top_load_g == 2000
    assert sanitized.keep_upright is False


def test_keep_upright_rotation_restriction():
    """Verify that keep_upright=True restricts rotations to LWH and WLH only."""
    upright_rotations = derive_allowed_rotations(keep_upright=True)
    assert set(upright_rotations) == {RotationCode.LWH, RotationCode.WLH}
    assert len(upright_rotations) == 2

    all_rotations = derive_allowed_rotations(keep_upright=False)
    assert len(all_rotations) == 6
    assert set(all_rotations) == {
        RotationCode.LWH,
        RotationCode.WLH,
        RotationCode.LHW,
        RotationCode.HLW,
        RotationCode.WHL,
        RotationCode.HWL,
    }


def test_timeout_triggers_clean_fallback():
    """Verify that network timeout cleanly triggers local heuristic fallback."""
    dummy_bytes = b"non_cached_image_bytes_for_timeout_test"

    mock_client = MagicMock()
    mock_client.post.side_effect = httpx.TimeoutException("Connection timed out")

    with patch.dict(os.environ, {"MODEL_API_KEY": "mock_api_key_for_testing"}):
        with patch("backend.app.ai.meta_client.get_cached_response", return_value=None):
            with patch("backend.app.ai.meta_client.get_sync_http_client", return_value=mock_client):
                attrs, telemetry = extract_item_semantics_muse(dummy_bytes, item_id="item_timeout", timeout_sec=0.1)

                assert telemetry.fallback_activated is True
                assert telemetry.muse_status == "fallback"
                assert attrs.fragility_class == "medium"
                assert attrs.weight_g is None
                assert attrs.weight_source == "unknown"


def test_sam31_regex_parser():
    """Verify SAM 3.1 custom output stream regex parser."""
    raw_stream = (
        "<0f>0<|box;x1=10;y1=20;x2=110;y2=220;w=100;h=200|><|mask;x=0;y=0;data=AAAA|><|/0f|>"
        "<0f>1<|box;x1=150;y1=60;x2=350;y2=260;w=200;h=200|><|mask;x=150;y=60;data=BBBB|><|/0f|>"
    )

    detections = parse_sam31_response(raw_stream)

    assert len(detections) == 2

    det0 = detections[0]
    assert det0["obj_id"] == 0
    assert det0["bbox_xyxy"] == [10, 20, 110, 220]
    assert det0["mask_origin_xy"] == (0, 0)
    assert det0["mask_b64_data"] == "AAAA"

    det1 = detections[1]
    assert det1["obj_id"] == 1
    assert det1["bbox_xyxy"] == [150, 60, 350, 260]
    assert det1["mask_origin_xy"] == (150, 60)
    assert det1["mask_b64_data"] == "BBBB"


@pytest.mark.asyncio
async def test_batch_muse_disk_cache_fast_path():
    """Verify that batch analysis immediately resolves from disk cache without network requests."""
    cached_payload = {
        "item_id": "box_cached_01",
        "display_name": "Cached Sennheiser Box",
        "category": "electronics_boxed",
        "visible_labels": ["Sennheiser"],
        "printed_weight_g": None,
        "fragility_class": "medium",
        "fragility_source": "default_safe",
        "keep_upright": False,
        "orientation_source": "default_unconstrained",
        "stackable": True,
        "max_top_load_g": 3000,
        "reasoning_note": "Cache hit test",
    }

    dummy_crop_bytes = b"sample_crop_bytes_12345"

    with patch("backend.app.ai.meta_client.get_cached_response", return_value=cached_payload):
        with patch("backend.app.ai.meta_client.get_async_http_client") as mock_async_client:
            res = await analyze_items_with_muse_spark(
                overview_image_bytes=b"overview_bytes",
                item_crops=[{"item_id": "box_cached_01", "crop_bytes": dummy_crop_bytes, "dims_mm": (100, 100, 50)}],
            )

            assert res["status"] == "cached"
            assert res["fallback_activated"] is False
            assert "box_cached_01" in res["items"]
            item_attrs = res["items"]["box_cached_01"]
            assert item_attrs["fragility_class"] == "medium"
            assert item_attrs["fragility_source"] == "default_safe"
            assert item_attrs["stackable"] is True
            # Async HTTP client should never be invoked when all items are in cache
            assert not mock_async_client.called


@pytest.mark.asyncio
async def test_batch_muse_demo_item_fallback():
    """Verify perceptual demo item fallback returns rich domain semantics offline."""
    with patch.dict(os.environ, {"MODEL_API_KEY": ""}):
        res = await analyze_items_with_muse_spark(
            overview_image_bytes=b"overview_bytes",
            item_crops=[
                {"item_id": "item_gocheck", "name": "GoChek Mic", "crop_bytes": b"noise_bytes_gocheck"},
                {"item_id": "order_3_topdown_wood", "crop_bytes": b"noise_bytes_wood"},
                {"item_id": "item_tissue_paper", "name": "Top Gia Paper", "crop_bytes": b"noise_bytes_paper"},
            ],
        )

        assert res["status"] == "fallback"
        items = res["items"]
        assert "item_gocheck" in items
        assert items["item_gocheck"]["fragility_class"] == "medium"
        assert "order_3_topdown_wood" in items
        assert items["order_3_topdown_wood"]["max_top_load_g"] == 3000
        assert "item_tissue_paper" in items
        assert items["item_tissue_paper"]["fragility_class"] == "low"


@pytest.mark.asyncio
async def test_batch_muse_partial_caching():
    """Verify that when 1 item is cached and 1 is uncached, only uncached is sent to Meta API."""
    cached_payload = {
        "item_id": "cached_item_1",
        "display_name": "Pre-warmed Item",
        "category": "generic_carton",
        "visible_labels": [],
        "printed_weight_g": None,
        "fragility_class": "medium",
        "fragility_source": "default_safe",
        "keep_upright": False,
        "orientation_source": "default_unconstrained",
        "stackable": True,
        "max_top_load_g": 2000,
        "reasoning_note": "from cache",
    }

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            '{"items":[{"item_id":"uncached_item_2","display_name":"New Item",'
                            '"category":"generic_carton","visible_labels":[],"printed_weight_g":null,'
                            '"fragility_class":"low","fragility_source":"default_safe","keep_upright":false,'
                            '"orientation_source":"default_unconstrained","stackable":true,'
                            '"reasoning_note":"newly analyzed"}]}'
                        ),
                    }
                ],
            }
        ]
    }
    
    async def async_post(*args, **kwargs):
        return mock_resp

    mock_client.post = async_post

    def fake_get_cache(sha):
        if sha == "hash_cached":
            return cached_payload
        return None

    with patch.dict(os.environ, {"MODEL_API_KEY": "test_key"}):
        with patch("backend.app.ai.meta_client.compute_image_sha256", side_effect=lambda b: "hash_cached" if b == b"bytes_cached" else "hash_uncached"):
            with patch("backend.app.ai.meta_client.get_cached_response", side_effect=fake_get_cache):
                with patch("backend.app.ai.meta_client.store_cached_response"):
                    with patch("backend.app.ai.meta_client.get_async_http_client", return_value=mock_client):
                        res = await analyze_items_with_muse_spark(
                            overview_image_bytes=b"overview",
                            item_crops=[
                                {"item_id": "cached_item_1", "crop_bytes": b"bytes_cached"},
                                {"item_id": "uncached_item_2", "crop_bytes": b"bytes_uncached"},
                            ],
                        )

                        assert res["status"] == "success"
                        assert "cached_item_1" in res["items"]
                        assert "uncached_item_2" in res["items"]
                        assert res["items"]["cached_item_1"]["fragility_class"] == "medium"
                        assert res["items"]["uncached_item_2"]["fragility_class"] == "low"
