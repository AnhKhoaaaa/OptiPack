"""Empirical Uncached Benchmark for Meta Muse Spark Open via Baseten.

Ensures 100% authentic, cold-start inference measurement on 5 real items
without using any pre-cached responses.
"""

import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, ".")
import dotenv
from backend.app.ai.cache import compute_image_sha256, get_cached_response
from backend.app.ai.meta_client import analyze_items_with_muse_spark

dotenv.load_dotenv()

TEST_ITEMS = [
    {
        "item_id": "item_01_paper",
        "name": "Tissue Paper Pack",
        "crop_path": "experiments/real_t01/crops/Trial03_Oblique__paper.jpg",
        "dims_mm": (148, 83, 55),
    },
    {
        "item_id": "item_02_wood",
        "name": "Wooden Audio Box",
        "crop_path": "experiments/real_t01/crops/Trial03_Oblique__wood.jpg",
        "dims_mm": (75, 48, 37),
    },
    {
        "item_id": "item_03_gocheck",
        "name": "Mic Case",
        "crop_path": "experiments/real_t01/crops/Trial03_Oblique__gocheck.jpg",
        "dims_mm": (67, 67, 30),
    },
    {
        "item_id": "item_04_white",
        "name": "White Box Device",
        "crop_path": "experiments/real_t01/crops/Trial03_Oblique__white.jpg",
        "dims_mm": (136, 49, 66),
    },
    {
        "item_id": "item_05_black",
        "name": "Black Box",
        "crop_path": "experiments/real_t01/crops/Trial03_Oblique__black.jpg",
        "dims_mm": (144, 62, 62),
    },
]


async def run_uncached_benchmark():
    print("=" * 70)
    print("OPTIPACK AUTHENTIC UNCACHED SPEED BENCHMARK (BASETEN MUSE SPARK OPEN)")
    print("=" * 70)

    # 1. Load crops and verify NO cache exists
    item_crops: List[Dict[str, Any]] = []
    print("\n[Step 1] Verifying cold-start cache integrity...")
    for item in TEST_ITEMS:
        with open(item["crop_path"], "rb") as f:
            crop_bytes = f.read()
        sha = compute_image_sha256(crop_bytes)
        cached_entry = get_cached_response(sha)
        assert cached_entry is None, f"Item {item['item_id']} is already cached! Test must be uncached."
        print(f"  - {item['item_id']} ({item['crop_path']}): SHA-256={sha[:12]}... | Cache: NOT CACHED (COLD)")

        item_crops.append({
            "item_id": item["item_id"],
            "name": item["name"],
            "dims_mm": item["dims_mm"],
            "crop_bytes": crop_bytes,
        })

    dummy_overview_bytes = item_crops[0]["crop_bytes"]

    # 2. Run real live parallel inference via Baseten
    print(f"\n[Step 2] Firing parallel async inference on Baseten for {len(item_crops)} uncached items...")
    t_start = time.perf_counter()
    res = await analyze_items_with_muse_spark(
        overview_image_bytes=dummy_overview_bytes,
        item_crops=item_crops,
        timeout_sec=25.0,
    )
    total_wall_clock_time = time.perf_counter() - t_start

    print("\n[Step 3] Benchmark Completed!")
    print(f"  - Total Wall-Clock Latency : {total_wall_clock_time:.2f} seconds")
    print(f"  - Average Per-Item Latency : {total_wall_clock_time / len(item_crops):.2f} seconds/item (in parallel)")
    print(f"  - Model Used               : {res.get('model')}")
    print(f"  - Status                   : {res.get('status')}")
    print(f"  - Fallback Activated       : {res.get('fallback_activated')}")

    print("\n[Step 4] Extracted Physical Semantics & OCR Names:")
    extracted_items = res.get("items", {})
    for item_id, data in extracted_items.items():
        print(f"\n  [{item_id}]")
        print(f"    - Display Name    : {data.get('display_name')}")
        print(f"    - Category        : {data.get('category')}")
        print(f"    - Visible Labels  : {data.get('visible_labels')}")
        print(f"    - Fragility Class : {data.get('fragility_class')} ({data.get('fragility_source')})")
        print(f"    - Stackable       : {data.get('stackable')}")
        print(f"    - Keep Upright    : {data.get('keep_upright')}")
        print(f"    - Reasoning Note  : {data.get('reasoning_note')}")

    # 3. Save benchmark record
    out_dir = "experiments/logs"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "baseten_uncached_speed_result.json")
    benchmark_record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_wall_clock_sec": round(total_wall_clock_time, 2),
        "item_count": len(item_crops),
        "model": res.get("model"),
        "status": res.get("status"),
        "fallback_activated": res.get("fallback_activated"),
        "items": extracted_items,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_record, f, indent=2, ensure_ascii=False)
    print(f"\n[Step 5] Benchmark report saved to: {out_path}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_uncached_benchmark())
