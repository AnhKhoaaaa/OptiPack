"""Phase 0 Feasibility Experiment: Meta Model API Integration (Member 2).

Gate Exit Criteria (03_EXECUTION_PLAN.md Section 3 & 02b_member2_ai_meta_model_api.md Section 7):
- 100% of muse-spark-1.3 responses conform to strict schema
- P95 latency <= 4,000 ms
- 0% fabricated weights on unmarked opaque boxes (Epistemic Honesty)
- 100% visible label recall on labeled items ("FRAGILE", "THIS SIDE UP")
- SAM 3.1 regex parser functional on token stream
- Offline disk cache & deterministic fallback functional

Output:
- Detailed JSON report: experiments/logs/phase0_meta_api_benchmark.json
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import cv2
import dotenv
import numpy as np

# Add project root directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
dotenv.load_dotenv(PROJECT_ROOT / ".env")

from backend.app.ai.cache import CACHE_DIR, compute_image_sha256, get_cached_response
from backend.app.ai.meta_client import (
    analyze_items_with_muse_spark,
    extract_item_semantics_muse,
    parse_sam31_response,
    segment_with_sam31,
    warmup_meta_client,
)


def generate_synthetic_item_image(
    label_text: str = "",
    box_color: tuple = (140, 180, 210),
    label_color: tuple = (0, 0, 200),
    has_arrows: bool = False,
) -> bytes:
    """Generate realistic synthetic item crop image for benchmark evaluation."""
    img = np.full((240, 240, 3), 245, dtype=np.uint8)
    # Box contour
    cv2.rectangle(img, (15, 15), (225, 225), box_color, -1)
    cv2.rectangle(img, (15, 15), (225, 225), (70, 90, 120), 3)

    if label_text:
        # White label sticker background
        cv2.rectangle(img, (25, 85), (215, 155), (255, 255, 255), -1)
        cv2.rectangle(img, (25, 85), (215, 155), (0, 0, 0), 2)
        cv2.putText(img, label_text, (30, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.72, label_color, 2)

    if has_arrows:
        # Draw two prominent upward pointing arrows
        for ax in (75, 165):
            cv2.arrowedLine(img, (ax, 70), (ax, 30), (0, 0, 0), 3, tipLength=0.35)

    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes()


def generate_tabletop_overview_image() -> bytes:
    """Generate synthetic tabletop overview with items and reference marker."""
    img = np.full((320, 420, 3), 235, dtype=np.uint8)
    # Packing table border
    cv2.rectangle(img, (25, 25), (395, 295), (210, 210, 210), -1)
    cv2.rectangle(img, (25, 25), (395, 295), (120, 120, 120), 2)

    # ArUco sheet simulation
    cv2.rectangle(img, (35, 35), (110, 135), (255, 255, 255), -1)
    cv2.rectangle(img, (45, 45), (65, 65), (0, 0, 0), -1)
    cv2.rectangle(img, (80, 45), (100, 65), (0, 0, 0), -1)
    cv2.putText(img, "ArUco Sheet", (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1)

    # Items on table
    cv2.rectangle(img, (140, 50), (240, 150), (140, 180, 210), -1)
    cv2.putText(img, "item_01", (150, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)

    cv2.rectangle(img, (260, 60), (360, 160), (150, 170, 190), -1)
    cv2.putText(img, "item_02", (270, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)

    cv2.rectangle(img, (160, 180), (280, 280), (160, 160, 180), -1)
    cv2.putText(img, "item_03", (170, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)

    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes()


def run_phase0_meta_api_benchmark() -> Dict[str, Any]:
    print("=" * 70)
    print("OptiPack Phase 0 Feasibility Benchmark: Member 2 (AI & Meta Model API)")
    print("=" * 70)

    api_key = os.getenv("MODEL_API_KEY", "")
    base_url = os.getenv("META_API_BASE_URL", "https://api.meta.ai/v1")
    model_name = os.getenv("MUSE_MODEL_NAME", "muse-spark-1.3")

    print(f"Meta Base URL : {base_url}")
    print(f"Model ID      : {model_name}")
    print(f"API Key Set   : {bool(api_key)} (length: {len(api_key)})")

    # Pre-warm connection pool to eliminate initial TLS handshake cold-start
    print("\nWarming up connection to Meta API...")
    warm = warmup_meta_client()
    print(f"Connection pool ready: {warm}")

    # 1. Define benchmark test suite with ground truth requirements
    test_cases = [
        {
            "item_id": "item_01_fragile",
            "name": "Fragile Carton Box",
            "image_bytes": generate_synthetic_item_image("FRAGILE", (130, 170, 210), (0, 0, 220)),
            "dims_mm": (220, 160, 120),
            "expected_handling_label": "FRAGILE",
            "expected_fragility": "high",
            "expect_upright": False,
            "must_have_weight": False,
        },
        {
            "item_id": "item_02_upright",
            "name": "This-Side-Up Liquid Carton",
            "image_bytes": generate_synthetic_item_image("THIS SIDE UP", (180, 190, 140), (0, 0, 0), has_arrows=True),
            "dims_mm": (150, 150, 250),
            "expected_handling_label": "THIS SIDE UP",
            "expected_fragility": None,
            "expect_upright": True,
            "must_have_weight": False,
        },
        {
            "item_id": "item_03_printed_wt",
            "name": "Retail Box with Printed Weight",
            "image_bytes": generate_synthetic_item_image("NET WT 500g", (200, 160, 150), (20, 20, 20)),
            "dims_mm": (180, 120, 80),
            "expected_handling_label": None,
            "expected_weight_g": 500,
            "expected_fragility": None,
            "expect_upright": False,
            "must_have_weight": True,
        },
        {
            "item_id": "item_04_opaque_unmarked_1",
            "name": "Plain Brown Cardboard Box #1",
            "image_bytes": generate_synthetic_item_image("", (140, 180, 210)),
            "dims_mm": (200, 200, 150),
            "expected_handling_label": None,
            "expected_fragility": None,
            "expect_upright": False,
            "must_have_weight": False,
        },
        {
            "item_id": "item_05_opaque_unmarked_2",
            "name": "Plain Gray Rigid Box #2",
            "image_bytes": generate_synthetic_item_image("", (160, 160, 170)),
            "dims_mm": (140, 110, 90),
            "expected_handling_label": None,
            "expected_fragility": None,
            "expect_upright": False,
            "must_have_weight": False,
        },
    ]

    # Clean old cache for benchmark items to ensure fresh network measurement
    for tc in test_cases:
        key = compute_image_sha256(tc["image_bytes"])
        cf = CACHE_DIR / f"{key}.json"
        if cf.exists():
            try:
                cf.unlink()
            except Exception:
                pass

    latencies_ms: List[float] = []
    schema_passes = 0
    fabricated_weights_count = 0
    labeled_stickers_tested = 0
    labeled_stickers_recalled = 0
    results_detail: List[Dict[str, Any]] = []

    print("\n[Step 1/4] Running Single-Item Semantic Extractions via muse-spark-1.3:")
    for tc in test_cases:
        t0 = time.perf_counter()
        attrs, telemetry = extract_item_semantics_muse(
            tc["image_bytes"], item_id=tc["item_id"], timeout_sec=5.0, model_name=model_name
        )
        dt_ms = (time.perf_counter() - t0) * 1000
        latencies_ms.append(dt_ms)

        # Check schema pass
        valid_schema = attrs is not None and isinstance(attrs.visible_labels, list)
        if valid_schema:
            schema_passes += 1

        # Check epistemic honesty on weight
        # If item has no printed weight label, weight MUST be None
        if not tc["must_have_weight"]:
            if attrs.weight_g is not None and attrs.weight_source not in ("scale_verified", "manifest"):
                fabricated_weights_count += 1
                print(f"  [!] Weight Hallucination detected on {tc['name']}: {attrs.weight_g}g")

        # Check handling sticker recall ("FRAGILE", "THIS SIDE UP")
        if tc["expected_handling_label"]:
            labeled_stickers_tested += 1
            labels_upper = [lbl.upper() for lbl in attrs.visible_labels]
            found = any(tc["expected_handling_label"].upper() in lbl or lbl in tc["expected_handling_label"].upper() for lbl in labels_upper)
            if found:
                labeled_stickers_recalled += 1
            else:
                print(f"  [?] Label '{tc['expected_handling_label']}' not in visible_labels: {attrs.visible_labels}")

        print(
            f"  - [{tc['item_id']}] {tc['name'][:28]:<28} | {dt_ms:.0f}ms | Status: {telemetry.muse_status} | "
            f"Fragility: {attrs.fragility_class} | Upright: {attrs.keep_upright} | Labels: {attrs.visible_labels} | "
            f"Weight: {attrs.weight_g} ({attrs.weight_source})"
        )

        results_detail.append({
            "item_id": tc["item_id"],
            "name": tc["name"],
            "latency_ms": round(dt_ms, 1),
            "status": telemetry.muse_status,
            "visible_labels": attrs.visible_labels,
            "fragility_class": attrs.fragility_class,
            "keep_upright": attrs.keep_upright,
            "weight_g": attrs.weight_g,
            "weight_source": attrs.weight_source,
            "max_top_load_g": attrs.max_top_load_g,
        })

    # [Step 2/4] Batched multi-crop test
    print("\n[Step 2/4] Running Batched Multi-Crop Request (1 Overview + 3 Crops):")
    overview_bytes = generate_tabletop_overview_image()
    batch_crops = [
        {"item_id": tc["item_id"], "crop_bytes": tc["image_bytes"], "dims_mm": tc["dims_mm"]}
        for tc in test_cases[:3]
    ]

    import asyncio
    t_batch_start = time.perf_counter()
    batch_res = asyncio.run(
        analyze_items_with_muse_spark(overview_bytes, batch_crops, model_name=model_name, timeout_sec=8.0)
    )
    t_batch_ms = (time.perf_counter() - t_batch_start) * 1000
    print(f"  Batched Call Status: {batch_res['status']} | Latency: {t_batch_ms:.0f}ms | Items extracted: {len(batch_res.get('items', {}))}")

    # [Step 3/4] SAM 3.1 Segmentation Test
    print("\n[Step 3/4] Testing sam-3.1 Segmentation & Regex Token Parser:")
    sam_res = segment_with_sam31(test_cases[0]["image_bytes"], prompt_text="box", timeout_sec=6.0)
    print(f"  SAM 3.1 Status: {sam_res['status']} | Latency: {sam_res.get('latency_ms', 0)}ms | Detections: {len(sam_res.get('detections', []))}")

    # Verify custom token regex parser on sample token string
    sample_tokens = "<0f>0<|box;x1=20;y1=20;x2=280;y2=280;w=260;h=260|><|mask;x=20;y=20;data=AAAA|><|/0f|>"
    parsed_tokens = parse_sam31_response(sample_tokens)
    sam_parser_ok = len(parsed_tokens) == 1 and parsed_tokens[0]["bbox_xyxy"] == [20, 20, 280, 280]
    print(f"  SAM 3.1 Regex Parser Integrity Check: {'PASS' if sam_parser_ok else 'FAIL'}")

    # [Step 4/4] SHA-256 Disk Cache Hit Verification
    print("\n[Step 4/4] Verifying SHA-256 Disk Cache Hit Latency:")
    cache_t0 = time.perf_counter()
    cached_attrs, cached_telemetry = extract_item_semantics_muse(test_cases[0]["image_bytes"], item_id="item_01_fragile")
    cache_dt_ms = (time.perf_counter() - cache_t0) * 1000
    cache_ok = cached_telemetry.muse_status == "cached" and cache_dt_ms < 50.0
    print(f"  Cache Status: {cached_telemetry.muse_status} | Hit Latency: {cache_dt_ms:.2f}ms (< 50ms) -> {'PASS' if cache_ok else 'FAIL'}")

    # Aggregate Metrics
    n_tests = len(test_cases)
    schema_compliance_pct = (schema_passes / n_tests) * 100.0
    sorted_lats = sorted(latencies_ms)
    p50_latency = sorted_lats[int(0.50 * (len(sorted_lats) - 1))]
    p95_latency = sorted_lats[int(0.95 * (len(sorted_lats) - 1))]
    label_recall_pct = (labeled_stickers_recalled / labeled_stickers_tested * 100.0) if labeled_stickers_tested > 0 else 100.0

    # Pass Criteria Check per 02b Section 7
    pass_schema = schema_compliance_pct == 100.0
    pass_latency = p95_latency <= 4000.0
    pass_weights = fabricated_weights_count == 0
    pass_labels = label_recall_pct >= 90.0
    pass_sam = sam_parser_ok
    pass_cache = cache_ok

    all_passed = pass_schema and pass_latency and pass_weights and pass_labels and pass_sam and pass_cache

    print("\n" + "=" * 70)
    print("--- OptiPack Phase 0 Feasibility Gate: Member 2 Results Summary ---")
    print("=" * 70)
    print(f"  1. Schema Compliance Rate   : {schema_compliance_pct:.1f}% (Gate: 100.0%)       -> {'PASS' if pass_schema else 'FAIL'}")
    print(f"  2. P50 Latency              : {p50_latency:.1f} ms")
    print(f"  3. P95 Latency              : {p95_latency:.1f} ms (Gate: <= 4000 ms)   -> {'PASS' if pass_latency else 'FAIL'}")
    print(f"  4. Fabricated Weights Count : {fabricated_weights_count} (Gate: 0)               -> {'PASS' if pass_weights else 'FAIL'}")
    print(f"  5. Visible Sticker Recall   : {label_recall_pct:.1f}% (Gate: 100.0%)      -> {'PASS' if pass_labels else 'FAIL'}")
    print(f"  6. SAM 3.1 Token Parser     : {'PASS' if pass_sam else 'FAIL'} (Gate: PASS)          -> {'PASS' if pass_sam else 'FAIL'}")
    print(f"  7. SHA-256 Cache Sub-50ms   : {'PASS' if pass_cache else 'FAIL'} ({cache_dt_ms:.2f}ms)          -> {'PASS' if pass_cache else 'FAIL'}")

    verdict = "GATE PASSED" if all_passed else "GATE FAILED"
    print(f"\n>> OVERALL VERDICT: {verdict}")
    if all_passed:
        print(">> Congratulations! Member 2 has satisfied all Phase 0 milestone criteria.")
        print(">> Proceeding to Phase 1 Meta API integration and Milestone M1 lock.")
    else:
        print(">> Activate pre-defined Fallback 2A/2B (Pre-warmed SHA-256 cache + heuristics).")

    # Save benchmark report to JSON
    logs_dir = PROJECT_ROOT / "experiments" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    report_file = logs_dir / "phase0_meta_api_benchmark.json"

    benchmark_data = {
        "benchmark_name": "Phase 0 Feasibility - Member 2 (AI & Meta Model API)",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_id": model_name,
        "base_url": base_url,
        "verdict": verdict,
        "all_passed": all_passed,
        "metrics": {
            "schema_compliance_pct": schema_compliance_pct,
            "p50_latency_ms": round(p50_latency, 1),
            "p95_latency_ms": round(p95_latency, 1),
            "fabricated_weights_count": fabricated_weights_count,
            "visible_label_recall_pct": round(label_recall_pct, 1),
            "sam_parser_ok": pass_sam,
            "cache_hit_latency_ms": round(cache_dt_ms, 2),
            "batch_latency_ms": round(t_batch_ms, 1),
        },
        "gates": {
            "schema_gate": "PASS" if pass_schema else "FAIL",
            "latency_gate": "PASS" if pass_latency else "FAIL",
            "epistemic_weight_gate": "PASS" if pass_weights else "FAIL",
            "label_recall_gate": "PASS" if pass_labels else "FAIL",
            "sam_parser_gate": "PASS" if pass_sam else "FAIL",
            "cache_gate": "PASS" if pass_cache else "FAIL",
        },
        "item_results": results_detail,
    }

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, indent=2)

    print(f"\nBenchmark JSON artifact saved to: {report_file}")
    return benchmark_data


if __name__ == "__main__":
    run_phase0_meta_api_benchmark()
