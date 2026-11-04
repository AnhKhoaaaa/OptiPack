"""Orders and Cartonization API router (Phase 2A CV + AI integration)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from backend.app.ai.meta_client import analyze_items_with_muse_spark
from backend.app.ai.sanitizer import derive_allowed_rotations, sanitize_physical_attributes
from backend.app.api.services.order_analysis import (
    demo_fixture_response, encode_semantic_crops, get_cv_service,
    new_analysis_id, no_measurement_response, normalize_crop_urls,
    read_image, timestamp_utc,
)
from backend.app.cv.service import CVCalibrationError, CVMetrologyService
from backend.app.schemas.contracts import (
    AITelemetry, OrderAnalysisResponse, PackingRequest, PackingSolutionResponse,
)
from backend.app.solver.cpsat_solver import solve_packing


router = APIRouter(prefix="/orders", tags=["Orders & Packing"])


@router.post("/analyze", response_model=OrderAnalysisResponse)
async def analyze_order(
    top_image: UploadFile = File(..., description="Top-down image, JPEG or PNG"),
    oblique_image: Optional[UploadFile] = File(None, description="35-45 degree oblique capture"),
    capture_mode: str = Form("dual_photo"),
    enable_cloud_sam: bool = Form(False),
    enable_muse_semantics: bool = Form(True),
    cv_service: Optional[CVMetrologyService] = Depends(get_cv_service),
) -> OrderAnalysisResponse:
    """Real dual-photo analysis, with conservative and explicit fallback.

    No uploaded photo is interpreted as a physical measurement unless a
    configured camera profile and real ArUco pose solve both succeed.
    """
    if capture_mode == "single_top_photo":
        capture_mode = "zenith_only"
    if capture_mode not in ("dual_photo", "zenith_only", "demo_fixture"):
        raise HTTPException(422, detail="capture_mode must be dual_photo, zenith_only or demo_fixture")
    if capture_mode == "demo_fixture":
        return demo_fixture_response()

    top, top_bytes = await read_image(top_image)
    if capture_mode == "zenith_only" or oblique_image is None:
        return no_measurement_response(
            "3D metrology requires an oblique image; no dimensions were inferred from a single image",
            status="fallback_zenith_only",
        )
    oblique, _ = await read_image(oblique_image)
    from backend.app.cv.preprocessing import harmonize_pair_geometry
    top, oblique = harmonize_pair_geometry(top, oblique)

    if top.shape != oblique.shape:
        raise HTTPException(422, detail="Both images must have identical height, width and color channels")

    warnings = []
    from backend.app.cv.preprocessing import assess_image_quality
    warnings.extend(assess_image_quality(top).get("warnings", []))
    warnings.extend(assess_image_quality(oblique).get("warnings", []))

    if enable_cloud_sam:
        warnings.append("Cloud SAM was requested but is not integrated into the CV pipeline; YOLOE was used")
    if cv_service is None:
        return no_measurement_response(
            "Missing OPTIPACK_CAMERA_PROFILE_PATH: no metric measurement attempted",
            warnings=warnings,
        )

    import logging
    import cv2
    logger = logging.getLogger("optipack.api")
    try:
        from pathlib import Path
        debug_dir = Path("/tmp/optipack_debug")
        debug_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_dir / "last_top.jpg"), top)
        cv2.imwrite(str(debug_dir / "last_oblique.jpg"), oblique)
    except Exception as e:
        logger.warning(f"Could not save debug images: {e}")

    try:
        batch = await run_in_threadpool(
            cv_service.process_pair,
            top,
            oblique,
            save_crops=True,
        )
    except (CVCalibrationError, ValueError) as exc:
        logger.error(f"[AnalyzeOrder] ArUco/calibration failed: {exc}")
        return no_measurement_response(
            f"ArUco/camera calibration failed; no metric measurement returned: {exc}",
            warnings=warnings,
        )
    except RuntimeError as exc:
        # Missing model weights, inference failures, etc. No fabricated metric dimensions.
        return no_measurement_response(
            f"CV inference unavailable; no metric measurement returned: {exc}",
            warnings=warnings,
        )
    except Exception as exc:
        return no_measurement_response(
            f"CV metrology processing error; no metric measurement returned: {exc}",
            warnings=warnings,
        )

    items = batch.items
    normalize_crop_urls(items)
    warnings.extend(batch.warnings)
    if batch.unmatched_top_indices or batch.unmatched_oblique_indices:
        warnings.append(
            "Not all visible candidates have reliable two-view matches; verify item count before packing"
        )
    if not items:
        warnings.append("No 3D items measured. Check the capture and confirm all objects manually")

    if not enable_muse_semantics or not items:
        for idx, item in enumerate(items):
            cv_stackable = item.physical_attributes.stackable if item.physical_attributes else True
            sanitized = sanitize_physical_attributes({})
            if not cv_stackable:
                sanitized.stackable = False
            item.physical_attributes = sanitized
            item.allowed_rotations = derive_allowed_rotations(False)
        warnings.append("AI semantics disabled or no measurable items; safe unknown-weight defaults retained")
        telemetry = AITelemetry(
            sam_status="skipped",
            muse_status="fallback",
            muse_latency_ms=0,
            fallback_activated=True,
        )
    else:
        try:
            crops = encode_semantic_crops(top, items)
            # Use Member 2's batched Muse path: one network call for uncached
            # items and existing SHA-256 cache/sanitizer for cached items.
            semantics = await analyze_items_with_muse_spark(
                top_bytes, crops, timeout_sec=20.0,
            )
        except (ValueError, OSError, RuntimeError) as exc:
            warnings.append(f"AI crop preparation/semantics unavailable; using safe defaults: {exc}")
            semantics = {
                "status": "fallback", "fallback_activated": True,
                "latency_ms": 0, "items": {},
            }
        resolved = semantics.get("items", {})
        for idx, item in enumerate(items):
            if item.item_id not in resolved:
                warnings.append(f"Missing AI semantics for {item.item_id}; using conservative defaults")
            raw = resolved.get(item.item_id) or {}
            cv_stackable = item.physical_attributes.stackable if item.physical_attributes else True
            sanitized = sanitize_physical_attributes(raw)
            if not cv_stackable:
                sanitized.stackable = False
            item.physical_attributes = sanitized
            item.allowed_rotations = derive_allowed_rotations(
                item.physical_attributes.keep_upright
            )
            # Map human-readable label and product category from Muse AI semantics
            ai_name = raw.get("display_name")
            if ai_name and str(ai_name).strip() and str(ai_name).strip().lower() not in ("packaged product", "item", "generic package"):
                item.display_name = str(ai_name).strip()
            elif not item.display_name or item.display_name.lower() in ("item", "detected object"):
                clean_cat = item.category.replace("_", " ").title()
                item.display_name = f"Item #{idx + 1:02d} ({clean_cat})"
            ai_cat = raw.get("category")
            if ai_cat and str(ai_cat).strip():
                item.category = str(ai_cat).strip()

            if item.physical_attributes.weight_g is None:
                warnings.append(f"Weight unknown for {item.item_id}; user must verify before packing")

        status = semantics.get("status", "fallback")
        if status not in ("success", "cached", "fallback", "failed"):
            status = "fallback"
        is_fallback = bool(semantics.get("fallback_activated", status in ("fallback", "failed")))
        telemetry = AITelemetry(
            sam_status="skipped",
            muse_status=status,
            muse_latency_ms=max(0, int(semantics.get("latency_ms", 0))),
            fallback_activated=is_fallback,
        )
        if is_fallback:
            warnings.append("Muse semantics fallback active; labels/handling attributes must be verified")

    if any(item.measurement_provenance.requires_user_review for item in items):
        warnings.append("One or more 3D dimensions require user review before packing")

    return OrderAnalysisResponse(
        analysis_id=new_analysis_id(),
        timestamp_utc=timestamp_utc(),
        calibration=batch.calibration.top_info,
        items=items,
        ai_telemetry=telemetry,
        global_warnings=warnings,
    )


@router.post("/pack", response_model=PackingSolutionResponse)
async def pack_order(request: PackingRequest) -> PackingSolutionResponse:
    """Run the 3D cartonization solver and synthesize AI scenario advice if applicable."""
    response = solve_packing(request)
    if response.scenarios:
        try:
            from backend.app.ai.meta_client import synthesize_scenario_advisor_notes
            response.scenarios = await synthesize_scenario_advisor_notes(
                response.scenarios, request.items, timeout_sec=3.0
            )
        except Exception:
            pass
    return response
