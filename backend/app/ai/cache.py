"""SHA-256 Disk Cache for Meta Model API Responses.

Ensures offline demo reproducibility and minimizes redundant API costs/latencies.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def compute_image_sha256(image_bytes: bytes) -> str:
    """Compute SHA-256 hex digest for an image byte string."""
    return hashlib.sha256(image_bytes).hexdigest()


def get_cached_response(cache_key: str) -> Optional[Dict[str, Any]]:
    """Retrieve cached JSON payload by SHA-256 key if present."""
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def store_cached_response(cache_key: str, data: Dict[str, Any]) -> None:
    """Write response payload to cache file."""
    cache_file = CACHE_DIR / f"{cache_key}.json"
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass
