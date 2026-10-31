"""Fast Signed Distance Field (SDF) 3D Cuboid Fitter.

Phase 0 Gate - Stage 0B for OptiPack Computer Vision (Member 1).
Optimizes 3D cuboid parameters [cx, cy, L, W, H, psi] in sub-150ms per trial:
1. Precomputes Signed Distance Field (SDF = EDT(1-M) - EDT(M)) on 40px expanded ROI crops ONCE.
2. Within the LM optimization loop:
   - Projects 8 cuboid vertices via cv2.projectPoints (<15 us)
   - Computes 2D convex hull via cv2.convexHull (<2 us)
   - Uniformly samples K=24 points along convex hull boundary (<15 us)
   - Bilinear lookups directly on precomputed SDF crop array (<25 us)
   - Vectorized Levenberg-Marquardt step in pure NumPy (<300 us/iter)
"""
from typing import Dict, List, Optional, Tuple
from time import perf_counter
from pathlib import Path
import cv2
import numpy as np

from experiments.real_t01.fast_metrology.initializer import ClosedFormInitializer
from experiments.real_t01.silhouette_fit import sampled_outline


def bilinear_sample(grid: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Fast vectorized bilinear interpolation on a 2D numpy grid."""
    h, w = grid.shape
    u_c = np.clip(u, 0, w - 1.001)
    v_c = np.clip(v, 0, h - 1.001)
    u0 = u_c.astype(np.int32)
    v0 = v_c.astype(np.int32)
    u1 = u0 + 1
    v1 = v0 + 1
    du = u_c - u0
    dv = v_c - v0
    return (
        (1.0 - du) * (1.0 - dv) * grid[v0, u0]
        + du * (1.0 - dv) * grid[v0, u1]
        + (1.0 - du) * dv * grid[v1, u0]
        + du * dv * grid[v1, u1]
    )


def batch_model_vertices(P: np.ndarray) -> np.ndarray:
    """Generate 8 3D vertices for a batch of M cuboid parameter vectors.
    
    Args:
        P: Array of shape (M, 6) with [cx, cy, L, W, H, angle].
        
    Returns:
        Array of shape (M, 8, 3) where vertices 0..3 are ground and 4..7 are top.
    """
    cx, cy, L, W, H, angle = P.T
    cos_a = np.cos(angle)
    sin_a = np.sin(angle)
    dx = np.array([-0.5, 0.5, 0.5, -0.5])
    dy = np.array([-0.5, -0.5, 0.5, 0.5])

    x = dx[None, :] * L[:, None]
    y = dy[None, :] * W[:, None]

    xr = x * cos_a[:, None] - y * sin_a[:, None] + cx[:, None]
    yr = x * sin_a[:, None] + y * cos_a[:, None] + cy[:, None]

    V_ground = np.stack([xr, yr, np.zeros_like(xr)], axis=-1)
    V_top = np.stack([xr, yr, np.broadcast_to(H[:, None], (len(P), 4))], axis=-1)
    return np.concatenate([V_ground, V_top], axis=1)


class FastSDFFitter:
    """High-speed 3D cuboid fitter using precomputed SDF crops and fast LM."""

    def __init__(self, K: np.ndarray, D: np.ndarray):
        self.K = np.asarray(K, dtype=np.float64)
        self.D = np.asarray(D, dtype=np.float64)

    def prepare_crop_evidence(self, mask: np.ndarray, cnt: np.ndarray, pose: Dict, margin: int = 40) -> Dict:
        """Compute Signed Distance Field on an expanded crop ROI."""
        H_img, W_img = mask.shape[:2]
        x_min, y_min = int(cnt[:, 0].min()), int(cnt[:, 1].min())
        x_max, y_max = int(cnt[:, 0].max()), int(cnt[:, 1].max())

        x0 = max(0, x_min - margin)
        y0 = max(0, y_min - margin)
        x1 = min(W_img, x_max + margin)
        y1 = min(H_img, y_max + margin)

        patch = (mask[y0:y1, x0:x1] > 127).astype(np.uint8)
        d_out = cv2.distanceTransform(1 - patch, cv2.DIST_L2, 3)
        d_in = cv2.distanceTransform(patch, cv2.DIST_L2, 3)
        sdf = d_out - d_in

        obs_crop = cnt[np.linspace(0, len(cnt) - 1, 24).astype(int)] - np.array([x0, y0])
        bbox_crop = np.array([x_min - x0, y_min - y0, x_max - x0, y_max - y0], dtype=np.float64)

        return {
            "x0": x0,
            "y0": y0,
            "sdf": sdf,
            "obs_crop": obs_crop,
            "bbox_crop": bbox_crop,
            "rvec": np.asarray(pose["rvec"], dtype=np.float64),
            "tvec": np.asarray(pose["tvec"], dtype=np.float64),
        }

    def evaluate_batch_residual(self, P: np.ndarray, views_crops: List[Dict]) -> np.ndarray:
        """Batch evaluate geometric residuals for M candidate parameters."""
        M = len(P)
        V = batch_model_vertices(P)
        V_flat = V.reshape(-1, 3)
        residuals_per_p = [[] for _ in range(M)]

        for v in views_crops:
            pts, _ = cv2.projectPoints(V_flat, v["rvec"], v["tvec"], self.K, self.D)
            pts = pts.reshape(M, 8, 2) - np.array([v["x0"], v["y0"]])

            for i in range(M):
                pi = pts[i]
                b_box = np.array([pi[:, 0].min(), pi[:, 1].min(), pi[:, 0].max(), pi[:, 1].max()])
                res_bbox = (b_box - v["bbox_crop"]) * 0.1

                hull = cv2.convexHull(pi.astype(np.float32)).reshape(-1, 2)
                samples = sampled_outline(hull, 24)
                sdf_vals = bilinear_sample(v["sdf"], samples[:, 0], samples[:, 1])
                res_sdf = np.clip(sdf_vals, -30.0, 30.0) * 0.5

                segments = np.roll(hull, -1, axis=0) - hull
                relative = v["obs_crop"][:, None, :] - hull[None, :, :]
                seg_sq = np.maximum(np.sum(segments * segments, axis=-1)[None, :], 1e-6)
                t = np.clip(np.sum(relative * segments[None, :, :], axis=-1) / seg_sq, 0, 1)
                nearest = hull[None, :, :] + t[:, :, None] * segments[None, :, :]
                dd = np.linalg.norm(v["obs_crop"][:, None, :] - nearest, axis=-1).min(axis=1)
                res_rc = np.clip(dd, 0.0, 30.0) * 0.5

                residuals_per_p[i].extend(res_bbox)
                residuals_per_p[i].extend(res_sdf)
                residuals_per_p[i].extend(res_rc)

        return np.asarray(residuals_per_p, dtype=np.float64)

    def fit_cuboid(self, p_init: np.ndarray, views_crops: List[Dict], max_iter: int = 10) -> Tuple[np.ndarray, float]:
        """Refine 3D cuboid parameters using vectorized Levenberg-Marquardt."""
        p = np.asarray(p_init, dtype=np.float64).copy()
        step = np.array([0.5, 0.5, 0.5, 0.5, 0.5, 0.005])
        damping = 1.0
        eye = np.eye(6) * step

        r = self.evaluate_batch_residual(p[None, :], views_crops)[0]
        score = float(r @ r)

        for _ in range(max_iter):
            P_perturbed = p + np.vstack([np.zeros(6), eye])
            all_r = self.evaluate_batch_residual(P_perturbed, views_crops)
            r_curr = all_r[0]
            J = ((all_r[1:] - r_curr) / step[:, None]).T

            try:
                d = -np.linalg.solve(J.T @ J + np.eye(6) * damping, J.T @ r_curr)
            except np.linalg.LinAlgError:
                break

            pp = p + d
            pp[2:5] = np.clip(pp[2:5], 15.0, 300.0)
            pp[5] = pp[5] % (2 * np.pi)

            rr = self.evaluate_batch_residual(pp[None, :], views_crops)[0]
            ss = float(rr @ rr)
            if ss < score:
                change = score - ss
                p, r, score = pp, rr, ss
                damping = max(0.0001, damping * 0.6)
                if change < 1e-4:
                    break
            else:
                damping = min(1e5, damping * 2.0)
            if np.linalg.norm(d) < 1e-3:
                break

        return p, score

