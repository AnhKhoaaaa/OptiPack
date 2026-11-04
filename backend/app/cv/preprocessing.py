"""Input Image Preprocessing and Quality Verification for 3D Metrology.

Implements autonomous orientation normalization, image quality assessment
(sharpness, lighting, contrast), and gentle illumination enhancement before
computer vision segmentation and ArUco pose estimation.
"""
from typing import Any, Dict, List, Tuple
import cv2
import numpy as np


def normalize_image_orientation(image: np.ndarray) -> np.ndarray:
    """Auto-orient image so that the ArUco calibration board is horizontal (+X rightward).

    If ArUco markers are detected, smartly orient based on the board's physical coordinate frame.
    Falls back to clockwise rotation if no markers found and H > W.
    """
    if image is None or image.size == 0:
        return image

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    parameters = cv2.aruco.DetectorParameters()
    corners, ids, _ = cv2.aruco.ArucoDetector(dictionary, parameters).detectMarkers(gray)
    if ids is not None and len(ids) >= 2:
        centers = {int(mid): c.reshape(4, 2).mean(axis=0) for c, mid in zip(corners, ids.ravel())}
        vec_x = None
        if 0 in centers and 1 in centers:
            vec_x = centers[1] - centers[0]
        elif 3 in centers and 2 in centers:
            vec_x = centers[2] - centers[3]
        elif 0 in centers and 3 in centers:
            vec_y = centers[3] - centers[0]
            vec_x = np.array([-vec_y[1], vec_y[0]])

        if vec_x is not None:
            angle = np.rad2deg(np.arctan2(vec_x[1], vec_x[0]))
            if -45.0 <= angle <= 45.0:
                return image
            elif 45.0 < angle <= 135.0:
                return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
            elif -135.0 <= angle < -45.0:
                return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
            else:
                return cv2.rotate(image, cv2.ROTATE_180)

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
        warnings.append("Image appears slightly blurry or out of focus. Hold the camera steady for sharpest metrology.")
    if mean_brightness < 55.0:
        warnings.append("Low-light scene detected. Consider increasing ambient light or turning on camera flash.")
    elif mean_brightness > 215.0:
        warnings.append("High glare or reflection detected. Check overhead lighting angle.")
    if contrast_std < 35.0:
        warnings.append("Low scene contrast detected. Ensure objects stand out against the background surface.")

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
    max_edge: int = 1600,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Preprocess uploaded/captured frame for optimal CV accuracy without geometric distortion.

    Steps:
    1. Standardize aspect orientation based on physical ArUco board angle.
    2. Normalize high-resolution mobile frames (e.g. 12MP/48MP) to max_edge for fast, sub-pixel accuracy.
    3. Assess optical quality (sharpness, lighting, exposure).
    4. Apply gentle adaptive illumination lifting if low-light, without altering edge positions.
    """
    if image is None or image.size == 0:
        raise ValueError("Cannot preprocess empty image")

    # 1. Orientation normalization
    processed = normalize_image_orientation(image)

    # 2. Resolution normalization for high-res mobile uploads
    h, w = processed.shape[:2]
    long_dim = max(w, h)
    if max_edge > 0 and long_dim > max_edge:
        scale = max_edge / float(long_dim)
        new_w, new_h = int(round(w * scale)), int(round(h * scale))
        processed = cv2.resize(processed, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # 3. Quality assessment
    quality = assess_image_quality(processed)

    # 4. Adaptive lighting enhancement (only if underexposed)
    if auto_enhance and quality["is_low_light"]:
        # Gentle gamma curve (gamma=1.3) to lift dark shadows without shifting geometry
        inv_gamma = 1.0 / 1.3
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
        processed = cv2.LUT(processed, table)

    return processed, quality

