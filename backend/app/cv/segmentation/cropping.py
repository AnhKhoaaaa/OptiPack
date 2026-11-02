"""High-resolution item crops for downstream item semantics (Phase 1 #7)."""
from pathlib import Path
import re
import uuid

import cv2
import numpy as np

DEFAULT_CROP_DIR = Path(__file__).resolve().parents[2] / "api" / "static" / "crops"


def extract_item_rgb_crop(
    image_bgr: np.ndarray,
    bbox_xyxy: list[int],
    mask: np.ndarray | None = None,
) -> np.ndarray:
    """Extract an uncropped-resolution RGB item patch from OpenCV BGR pixels.

    BBox is [x_min, y_min, x_max, y_max], with max coordinates exclusive.
    Optional full-image mask sets background pixels to black.
    """
    if image_bgr.ndim != 3 or image_bgr.shape[2] != 3 or image_bgr.size == 0:
        raise ValueError("image_bgr must be a non-empty 3-channel image")
    if len(bbox_xyxy) != 4:
        raise ValueError("bbox_xyxy must have four coordinates")
    h, w = image_bgr.shape[:2]
    x0, y0, x1, y1 = (int(round(v)) for v in bbox_xyxy)
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("bbox_xyxy has no valid intersection with image")

    crop = cv2.cvtColor(image_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)
    if mask is not None:
        if mask.shape != (h, w):
            raise ValueError("mask must match the full image height and width")
        crop = crop.copy()
        crop[mask[y0:y1, x0:x1] == 0] = 0
    return crop


def save_item_rgb_crop(
    rgb_crop: np.ndarray,
    *,
    output_dir: Path = DEFAULT_CROP_DIR,
    item_id: str | None = None,
) -> tuple[str, Path]:
    """Persist RGB patch as JPEG and return (unique item ID, filesystem path).

    Generated IDs are random UUIDs; caller IDs must be path-safe. The API layer
    must mount/serve this directory before referencing it as a crop_url.
    """
    if rgb_crop.ndim != 3 or rgb_crop.shape[2] != 3 or rgb_crop.size == 0:
        raise ValueError("rgb_crop must be a non-empty RGB image")
    item_id = item_id or f"item_{uuid.uuid4().hex}"
    if not re.fullmatch(r"[A-Za-z0-9_-]+", item_id):
        raise ValueError("item_id must contain only letters, digits, - and _")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{item_id}.jpg"
    if path.exists():
        raise FileExistsError(f"Crop already exists for item ID {item_id}")
    success, encoded = cv2.imencode(".jpg", cv2.cvtColor(rgb_crop, cv2.COLOR_RGB2BGR))
    if not success:
        raise RuntimeError("Failed to encode item crop")
    with path.open("xb") as file:
        file.write(encoded.tobytes())
    return item_id, path
