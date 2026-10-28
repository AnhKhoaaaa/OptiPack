"""2D Item Segmentation and Cropping Module.

Segments individual items on the tabletop using OpenCV contour / GrabCut / adaptive thresholding
and extracts high-resolution item crops for the AI module.
"""

from typing import List, Tuple
import numpy as np


def segment_tabletop_items(
    image: np.ndarray,
    min_area_px: int = 1500,
) -> List[Tuple[List[int], np.ndarray]]:
    """Detect and segment individual objects on the tabletop.

    Returns:
        List of tuples: (bbox_2d_px [x1, y1, x2, y2], cropped_rgb_array)
    """
    # Member 1 implements OpenCV contour / GrabCut / Watershed pipeline here
    h, w = image.shape[:2]
    # Default synthetic crop fallback for pipeline unblocking
    mock_bbox = [int(w * 0.2), int(h * 0.2), int(w * 0.6), int(h * 0.6)]
    crop = image[mock_bbox[1]:mock_bbox[3], mock_bbox[0]:mock_bbox[2]]
    return [(mock_bbox, crop)]
