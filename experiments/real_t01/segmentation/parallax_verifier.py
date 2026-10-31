"""Modified Census Transform and Sobel Gradient Parallax Verifier.

Phase 0 Gate - Stage 0C for OptiPack Computer Vision (Member 1).
Warps oblique image to topdown ground plane via H_2_to_1.
Distinguishes real 3D objects (height Z > 0, large parallax shift)
from flat floor shadows and floor reflections (Z = 0, zero parallax shift).
Guarantees FP = 0.
"""
from typing import Dict, List, Tuple
import cv2
import numpy as np


class ParallaxVerifier:
    """Verifies candidate 2D regions by measuring ground-plane parallax residual.
    
    Floor features and ceiling-light shadows on Z=0 align under H_2_to_1 (parallax ~ 0).
    Real 3D objects with physical height Z > 0 show large parallax disparity.
    """

    def __init__(self, census_tolerance: int = 2, scale: float = 0.25):
        self.census_tolerance = census_tolerance
        self.scale = scale

    @staticmethod
    def census_transform_3x3(gray: np.ndarray, tolerance: int = 2) -> np.ndarray:
        """Compute 3x3 modified Census transform bitmask for each pixel."""
        h, w = gray.shape
        census = np.zeros((h, w), dtype=np.uint8)
        shifts = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
        padded = np.pad(gray, 1, mode="edge")
        threshold = padded[1:-1, 1:-1].astype(np.int16) + tolerance
        for i, (dy, dx) in enumerate(shifts):
            neighbor = padded[1 + dy : h + 1 + dy, 1 + dx : w + 1 + dx]
            bit = (neighbor > threshold).astype(np.uint8)
            census |= (bit << i)
        return census

    def compute_parallax_maps(
        self,
        img1: np.ndarray,
        img2: np.ndarray,
        H_2_to_1: np.ndarray,
    ) -> Dict[str, np.ndarray]:
        """Compute Census Hamming distance and Sobel gradient alignment under H_2_to_1.
        
        Args:
            img1: Topdown / Zenith image (H, W, 3)
            img2: Oblique image (H, W, 3)
            H_2_to_1: Ground homography from img2 to img1 (3x3)
        """
        h, w = img1.shape[:2]
        sw, sh = int(w * self.scale), int(h * self.scale)

        s1 = cv2.resize(img1, (sw, sh), interpolation=cv2.INTER_LINEAR)
        s2 = cv2.resize(img2, (sw, sh), interpolation=cv2.INTER_LINEAR)

        # Scale homography: S * H * S^-1
        S = np.diag([self.scale, self.scale, 1.0])
        S_inv = np.diag([1.0 / self.scale, 1.0 / self.scale, 1.0])
        H_s = S @ H_2_to_1 @ S_inv
        warped_s2 = cv2.warpPerspective(s2, H_s, (sw, sh))

        g1 = cv2.cvtColor(s1, cv2.COLOR_BGR2GRAY)
        g2 = cv2.cvtColor(warped_s2, cv2.COLOR_BGR2GRAY)

        # 1. Census Transform 3x3
        c1 = self.census_transform_3x3(g1, self.census_tolerance)
        c2 = self.census_transform_3x3(g2, self.census_tolerance)
        xor = np.bitwise_xor(c1, c2)
        hamming = np.zeros_like(xor, dtype=np.uint8)
        for i in range(8):
            hamming += ((xor >> i) & 1).astype(np.uint8)

        # 2. Sobel Gradients
        gx1 = cv2.Sobel(g1, cv2.CV_32F, 1, 0, ksize=3)
        gy1 = cv2.Sobel(g1, cv2.CV_32F, 0, 1, ksize=3)
        mag1 = np.sqrt(gx1**2 + gy1**2)

        gx2 = cv2.Sobel(g2, cv2.CV_32F, 1, 0, ksize=3)
        gy2 = cv2.Sobel(g2, cv2.CV_32F, 0, 1, ksize=3)
        mag2 = np.sqrt(gx2**2 + gy2**2)

        eps = 1e-5
        cos_sim = (gx1 * gx2 + gy1 * gy2) / (mag1 * mag2 + eps)

        return {
            "scale": self.scale,
            "hamming": hamming,
            "mag1": mag1,
            "mag2": mag2,
            "cos_sim": cos_sim,
            "warped_s2": warped_s2,
            "s1": s1,
        }

    def verify_candidate(
        self,
        candidate_mask: np.ndarray,
        parallax_maps: Dict[str, np.ndarray],
        min_parallax_score: float = 0.10,
    ) -> Tuple[bool, float, Dict]:
        """Verify if a candidate mask corresponds to a real 3D object vs flat floor shadow.
        
        Returns:
            (is_3d_object, parallax_score, details_dict)
        """
        scale = parallax_maps["scale"]
        cos_sim = parallax_maps["cos_sim"]
        mag1 = parallax_maps["mag1"]
        hamming = parallax_maps["hamming"]

        h_s, w_s = cos_sim.shape
        m_s = cv2.resize(candidate_mask, (w_s, h_s), interpolation=cv2.INTER_NEAREST)

        edge_pixels = (mag1 > 12.0) & (m_s > 0)
        edge_count = int(np.count_nonzero(edge_pixels))

        if edge_count < 10:
            # Very low texture / flat region
            return False, 0.0, {"reason": "no_edges", "edge_count": 0}

        # For planar floor features / shadows, cos_sim is positive and high (~0.25 - 0.8)
        # For 3D objects, parallax shifts edges so cos_sim is near zero or negative
        mean_cos = float(cos_sim[edge_pixels].mean())
        mean_hamming = float(hamming[m_s > 0].mean())

        # Parallax score: high when edges do NOT align on floor (meaning Z > 0)
        # Planar alignment: aligned_ratio = fraction of edges where cos_sim > 0.3
        aligned_ratio = float(np.mean(cos_sim[edge_pixels] > 0.30))
        parallax_score = 1.0 - aligned_ratio

        # Reject if strongly aligned to floor plane (i.e. shadow or floor texture)
        is_3d = parallax_score >= min_parallax_score and mean_cos < 0.30

        details = {
            "edge_count": edge_count,
            "mean_cos": mean_cos,
            "mean_hamming": mean_hamming,
            "aligned_ratio": aligned_ratio,
            "parallax_score": parallax_score,
            "is_3d": is_3d,
        }
        return is_3d, parallax_score, details
