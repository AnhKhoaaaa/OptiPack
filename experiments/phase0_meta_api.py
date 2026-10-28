"""Phase 0 Feasibility Experiment: Meta Model API Integration (Member 2).

Gate Exit Criteria (03_EXECUTION_PLAN.md Section 3):
- 100% of muse-spark-1.3 responses conform to schema
- P95 latency <= 4.0s
- 0% fabricated weights on unmarked opaque boxes

If failed within 3 hours:
- Activate Fallback 2A/2B: Composite image + JPEG downscale + SHA256 disk cache + deterministic heuristics.
"""

import os
import time
from backend.app.ai.meta_client import extract_item_semantics_muse


def run_phase0_meta_api_benchmark():
    print("=" * 60)
    print("OptiPack Phase 0 Feasibility: Member 2 (AI & Meta Model API)")
    print("=" * 60)

    api_key = os.getenv("MODEL_API_KEY", "")
    print(f"MODEL_API_KEY Present: {bool(api_key)}")

    test_samples = [
        {"item_id": "item_01", "name": "Headphones Box", "bytes": b"synthetic_image_headphone"},
        {"item_id": "item_02", "name": "Glass Perfume Bottle", "bytes": b"synthetic_image_perfume"},
        {"item_id": "item_03", "name": "Plastic Shampoo Bottle", "bytes": b"synthetic_image_shampoo"},
    ]

    latencies = []
    fabricated_weights = 0
    schema_passes = 0

    print("\nTesting Semantic Attribute Extraction:")
    for sample in test_samples:
        t0 = time.time()
        attrs, telemetry = extract_item_semantics_muse(sample["bytes"], sample["item_id"])
        dt_ms = (time.time() - t0) * 1000
        latencies.append(dt_ms)

        schema_valid = attrs is not None and isinstance(attrs.visible_labels, list)
        if schema_valid:
            schema_passes += 1

        if attrs.weight_g is not None and attrs.weight_source != "scale_verified":
            fabricated_weights += 1

        print(f"  - {sample['name']}: Latency={dt_ms:.1f}ms | Status={telemetry.muse_status} | "
              f"Fragility={attrs.fragility_class} | Upright={attrs.keep_upright} | Weight={attrs.weight_g}")

    p95_latency = max(latencies) if latencies else 0.0
    pass_rate = (schema_passes / len(test_samples)) * 100.0

    print("\n--- Phase 0 Evaluation Gate Results ---")
    print(f"Schema Compliance: {pass_rate:.1f}% (Gate: 100%) -> {'PASS' if pass_rate == 100 else 'FAIL'}")
    print(f"P95 Latency: {p95_latency:.1f} ms (Gate: <= 4000 ms) -> {'PASS' if p95_latency <= 4000 else 'FAIL'}")
    print(f"Fabricated Weights Count: {fabricated_weights} (Gate: 0) -> {'PASS' if fabricated_weights == 0 else 'FAIL'}")

    passed = (pass_rate == 100 and p95_latency <= 4000 and fabricated_weights == 0)
    if passed:
        print("\n>> VERDICT: GATE PASSED. Proceed to Phase 1 Meta API integration.")
    else:
        print("\n>> VERDICT: GATE FAILED. Activate Fallback 2A/2B (Pre-warmed SHA256 cache + heuristics).")


if __name__ == "__main__":
    run_phase0_meta_api_benchmark()
