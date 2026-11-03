"""Input Image Preprocessing and Quality Verification for 3D Metrology.

Implements autonomous orientation normalization, image quality assessment
(sharpness, lighting, contrast), and gentle illumination enhancement before
computer vision segmentation and ArUco pose estimation.
"""
from typing import Any, Dict, List, Tuple
import cv2
import numpy as np


def normalize_image_orientation(image: np.ndarray) -> np.ndarray:
    """Auto-orient portrait photos (H > W) to landscape workspace calibration (W > H)."""
    if image.shape[0] > image.shape[1]:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    return image


def assess_image_quality(image: np.ndarray) -> Dict[str, Any]:
    """Analyze lighting, contrast, and focus sharpness to warn users of poor captures."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    h, w = gray.shape[:2]
    mean_brightness = float(np.mean(gray))
    contrast_std = float(np.std(gray))
    sharpness_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    warnings: List[str] = []
    if sharpness_var < 45.0:
        warnings.append("Ảnh chụp có dấu hiệu bị mờ (out of focus); hãy giữ chắc máy khi chụp.")
    if mean_brightness < 55.0:
        warnings.append("Môi trường thiếu sáng (low light); hãy tăng ánh sáng hoặc bật đèn flash.")
    elif mean_brightness > 215.0:
        warnings.append("Ảnh bị chói sáng hoặc bóng lóa (glare); kiểm tra góc chiếu đèn.")
    if contrast_std < 35.0:
        warnings.append("Độ tương phản thấp; vật thể có thể bị lẫn với nền bàn.")

    return {
        "width_px": w,
        "height_px": h,
        "mean_brightness": round(mean_brightness, 1),
        "contrast_std": round(contrast_std, 1),
        "sharpness_score": round(sharpness_var, 1),
        "is_blurry": sharpness_var < 45.0,
        "is_low_light": mean_brightness < 55.0,
        "is_overexposed": mean_brightness > 215.0,
        "warnings": warnings,
    }


def preprocess_image_for_cv(
    image: np.ndarray,
    auto_enhance: bool = True,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Preprocess uploaded/captured frame for optimal CV accuracy without geometric distortion.

    Steps:
    1. Standardize aspect orientation (portrait -> landscape).
    2. Assess optical quality (sharpness, lighting, exposure).
    3. Apply gentle adaptive illumination lifting if low-light, without altering edge positions.
    """
    if image is None or image.size == 0:
        raise ValueError("Cannot preprocess empty image")

    # 1. Orientation normalization
    processed = normalize_image_orientation(image)

    # 2. Quality assessment
    quality = assess_image_quality(processed)

    # 3. Adaptive lighting enhancement (only if underexposed)
    if auto_enhance and quality["is_low_light"]:
        # Gentle gamma curve (gamma=1.3) to lift dark shadows without shifting geometry
        inv_gamma = 1.0 / 1.3
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
        processed = cv2.LUT(processed, table)

    return processed, quality
