"""Input Image Preprocessing and Quality Verification for 3D Metrology.

Implements autonomous orientation normalization, image quality assessment
(sharpness, lighting, contrast), and gentle illumination enhancement before
computer vision segmentation and ArUco pose estimation.
"""
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np


def detect_board_axis(image: np.ndarray) -> Tuple[Optional[np.ndarray], int]:
    """Detect ArUco board markers and return the physical +X orientation vector and marker count."""
    if image is None or image.size == 0:
        return None, 0

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX

    corners, ids, _ = cv2.aruco.ArucoDetector(dictionary, parameters).detectMarkers(gray)
    count = 0 if ids is None else len(set(int(v) for v in ids.ravel() if int(v) in (0, 1, 2, 3)))

    if count < 2:
        # Multi-scale & CLAHE detection for dark or high-resolution mobile photos
        h, w = gray.shape[:2]
        long_dim = max(w, h)
        if long_dim > 1600:
            scale = 1200.0 / long_dim
            gray_scaled = cv2.resize(gray, (int(round(w * scale)), int(round(h * scale))), interpolation=cv2.INTER_AREA)
        else:
            gray_scaled = gray

        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        gray_enh = clahe.apply(gray_scaled)
        c_enh, ids_enh, _ = cv2.aruco.ArucoDetector(dictionary, parameters).detectMarkers(gray_enh)
        count_enh = 0 if ids_enh is None else len(set(int(v) for v in ids_enh.ravel() if int(v) in (0, 1, 2, 3)))
        if count_enh >= 2:
            corners, ids = c_enh, ids_enh
            count = count_enh

    if ids is not None and count >= 2:
        centers = {int(mid): c.reshape(4, 2).mean(axis=0) for c, mid in zip(corners, ids.ravel()) if int(mid) in (0, 1, 2, 3)}
        if 0 in centers and 1 in centers:
            return centers[1] - centers[0], count
        elif 3 in centers and 2 in centers:
            return centers[2] - centers[3], count
        elif 0 in centers and 3 in centers:
            vec_y = centers[3] - centers[0]
            return np.array([-vec_y[1], vec_y[0]]), count
        elif 1 in centers and 2 in centers:
            vec_y = centers[2] - centers[1]
            return np.array([-vec_y[1], vec_y[0]]), count

    return None, count


def normalize_image_orientation(image: np.ndarray) -> np.ndarray:
    """Auto-orient image so that the ArUco calibration board is horizontal (+X rightward).

    If ArUco markers are detected, smartly orient based on the board's physical coordinate frame.
    Works at any 360-degree rotation angle (0°, 90°, 180°, 270°).
    Falls back to clockwise rotation if no markers found and H > W.
    """
    if image is None or image.size == 0:
        return image

    vec_x, count = detect_board_axis(image)
    if vec_x is not None:
        angle = np.rad2deg(np.arctan2(vec_x[1], vec_x[0]))
        # 4-quadrant rotation mapping:
        if -45.0 <= angle <= 45.0:
            return image
        elif 45.0 < angle <= 135.0:
            return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        elif -135.0 <= angle < -45.0:
            return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        else:
            return cv2.rotate(image, cv2.ROTATE_180)

    # Legacy unit test fallback for blank portrait image without markers
    if image.shape[0] > image.shape[1] and count == 0:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    return image


def harmonize_pair_geometry(top: np.ndarray, oblique: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Harmonize dual-photo geometry so top and oblique share matching dimensions and coordinate frame.

    Handles mixed orientations (e.g. Top in Portrait, Oblique in Landscape, or vice versa)
    and differing camera sensor resolutions:
    1. If shapes already match, returns (top, oblique) directly.
    2. If neither image has ArUco markers, preserves original shapes (allowing contract checks to reject).
    3. If orientations are transposed (one Portrait, one Landscape), rotates oblique 90° (CW or CCW)
       to align with top's board coordinate frame and aspect ratio.
    4. If oblique is 180° inverted relative to top, rotates 180°.
    5. If dimensions still differ slightly, resizes oblique to match top's exact (width, height).
    """
    if top is None or oblique is None or top.size == 0 or oblique.size == 0:
        return top, oblique
    if top.shape == oblique.shape:
        return top, oblique

    vec_t, count_t = detect_board_axis(top)
    vec_o, count_o = detect_board_axis(oblique)

    # If neither image contains fiducials, do not auto-harmonize synthetic blank images
    if count_t == 0 and count_o == 0:
        return top, oblique

    ht, wt = top.shape[:2]
    ho, wo = oblique.shape[:2]

    top_is_portrait = ht > wt
    ob_is_portrait = ho > wo

    if top_is_portrait != ob_is_portrait:
        cand_cw = cv2.rotate(oblique, cv2.ROTATE_90_CLOCKWISE)
        cand_ccw = cv2.rotate(oblique, cv2.ROTATE_90_COUNTERCLOCKWISE)

        if vec_t is not None:
            vec_cw, _ = detect_board_axis(cand_cw)
            vec_ccw, _ = detect_board_axis(cand_ccw)
            score_cw = float(np.dot(vec_t, vec_cw)) if vec_cw is not None else -1e9
            score_ccw = float(np.dot(vec_t, vec_ccw)) if vec_ccw is not None else -1e9
            if score_cw >= score_ccw and score_cw > 0:
                oblique = cand_cw
                vec_o = vec_cw
            elif score_ccw > 0:
                oblique = cand_ccw
                vec_o = vec_ccw
            else:
                oblique = cand_cw
                vec_o, _ = detect_board_axis(oblique)
        else:
            oblique = cand_cw
            vec_o, _ = detect_board_axis(oblique)

    if vec_t is not None and vec_o is not None:
        if np.dot(vec_t, vec_o) < 0:
            oblique = cv2.rotate(oblique, cv2.ROTATE_180)

    if oblique.shape[:2] != (ht, wt):
        oblique = cv2.resize(oblique, (wt, ht), interpolation=cv2.INTER_AREA)

    return top, oblique


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

