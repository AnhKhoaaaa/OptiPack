"""V3-based Phase 1 segmentation and crop utilities."""

from backend.app.cv.segmentation.detector import YOLOESegmenter
from backend.app.cv.segmentation.sam31_segmenter import SAM31Segmenter
from backend.app.cv.segmentation.parallax_verifier import ParallaxVerifier
from backend.app.cv.segmentation.cropping import extract_item_rgb_crop, save_item_rgb_crop
from backend.app.cv.segmentation.pipeline import PairSegmentation, SegmentationPipeline

__all__ = [
    "YOLOESegmenter",
    "SAM31Segmenter",
    "ParallaxVerifier",
    "extract_item_rgb_crop",
    "save_item_rgb_crop",
    "PairSegmentation",
    "SegmentationPipeline",
]
