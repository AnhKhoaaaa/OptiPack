"""Closed-form Geometric Parallax & Radial Relief Initializer.

Phase 2 CV Metrology for OptiPack (Member 1):
1. Zenith (Topdown) mask: extracts ground center (cx0, cy0), yaw psi0, and ground footprint (L_ground, W_ground).
2. Ground-Subtracted Parallax Height: subtracts ground footprint extent from oblique contour along parallax direction.
3. Directional Radial Relief De-biasing: compensates perspective side-face dilation strictly along the camera radial ray.
4. Generates multi-start hypothesis parameters for multi-start Levenberg-Marquardt SDF fitting.
"""
from typing import Dict, List, Tuple
import cv2
import numpy as np


class ClosedFormInitializer:
    """Closed-form geometric initializer with directional de-biasing and parallax height."""

    @classmethod
    def _extract_ground_and_radial(
        cls,
        cnt1: np.ndarray,
        pose1: Dict,
        K: np.ndarray,
        D: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, float, float, float, np.ndarray, float, float]:
        R1 = np.asarray(pose1["R"], dtype=np.float64)
        C1 = np.asarray(pose1["camera_center_mm"], dtype=np.float64).ravel()

        rect1 = cv2.minAreaRect(cnt1.astype(np.float32))
        box_pts = cv2.boxPoints(rect1)

        norm_box = cv2.undistortPoints(box_pts.reshape(-1, 1, 2), K, D).reshape(-1, 2)
        dirs = (R1.T @ np.c_[norm_box, np.ones(4)].T).T
        lamb = -C1[2] / np.where(np.abs(dirs[:, 2]) > 1e-8, dirs[:, 2], -1e-8)
        xy_ground = (C1 + dirs * lamb[:, None])[:, :2]

        center_xy = np.mean(xy_ground, axis=0)
        spans = np.linalg.norm(np.roll(xy_ground, -1, axis=0) - xy_ground, axis=1)
        L_ground = float(max((spans[0] + spans[2]) / 2.0, (spans[1] + spans[3]) / 2.0))
        W_ground = float(min((spans[0] + spans[2]) / 2.0, (spans[1] + spans[3]) / 2.0))

        edge_vec = xy_ground[1] - xy_ground[0] if spans[0] >= spans[1] else xy_ground[2] - xy_ground[1]
        psi0 = float(np.arctan2(edge_vec[1], edge_vec[0]) % np.pi)

        # Radial unit vector from Camera 1 optical center
        r_vec = center_xy - C1[:2]
        r = float(np.linalg.norm(r_vec))
        u_rad = r_vec / (r if r > 1e-9 else 1.0)

        # Edge unit vectors
        u0 = (xy_ground[1] - xy_ground[0]) / max(spans[0], 1e-6)
        u1 = (xy_ground[2] - xy_ground[1]) / max(spans[1], 1e-6)
        c0 = abs(float(np.dot(u0, u_rad)))
        c1 = abs(float(np.dot(u1, u_rad)))

        return xy_ground, center_xy, L_ground, W_ground, psi0, u_rad, c0, c1

    @classmethod
    def _compute_parallax_height(
        cls,
        cnt2: np.ndarray,
        xy_ground: np.ndarray,
        center_xy: np.ndarray,
        pose2: Dict,
        K: np.ndarray,
        D: np.ndarray,
    ) -> float:
        rvec2 = np.asarray(pose2["rvec"], dtype=np.float64)
        t2 = np.asarray(pose2["tvec"], dtype=np.float64).reshape(3, 1)

        # Project ground footprint to Camera 2
        g_pts_3d = np.c_[xy_ground, np.zeros(len(xy_ground))]
        g_2d, _ = cv2.projectPoints(g_pts_3d, rvec2, t2, K, D)
        g_2d = g_2d.reshape(-1, 2)

        # Compute vertical parallax direction and scale
        p2_z0, _ = cv2.projectPoints(np.array([[center_xy[0], center_xy[1], 0.0]]), rvec2, t2, K, D)
        p2_z100, _ = cv2.projectPoints(np.array([[center_xy[0], center_xy[1], 100.0]]), rvec2, t2, K, D)
        v_par = (p2_z100 - p2_z0).ravel()
        norm_v = float(np.linalg.norm(v_par))
        s_h = norm_v / 100.0
        u_par = v_par / (norm_v if norm_v > 1e-9 else 1.0)

        proj_cnt2 = np.dot(cnt2, u_par)
        proj_g2d = np.dot(g_2d, u_par)

        span_cnt2 = float(np.percentile(proj_cnt2, 98) - np.percentile(proj_cnt2, 2))
        span_g2d = float(np.max(proj_g2d) - np.min(proj_g2d))

        delta_ob_px = span_cnt2 - 0.85 * span_g2d
        H0 = float(np.clip(max(5.0, delta_ob_px) / max(s_h, 1e-6), 22.0, 110.0))
        return H0

    @classmethod
    def compute_initial_guess(
        cls,
        cnt1: np.ndarray,
        cnt2: np.ndarray,
        pose1: Dict,
        pose2: Dict,
        K: np.ndarray,
        D: np.ndarray,
    ) -> np.ndarray:
        """Compute closed-form initial cuboid parameters [cx0, cy0, L0, W0, H0, psi0]."""
        C1 = np.asarray(pose1["camera_center_mm"], dtype=np.float64).ravel()
        xy_ground, center_xy, L_ground, W_ground, psi0, u_rad, c0, c1 = cls._extract_ground_and_radial(
            cnt1, pose1, K, D
        )
        H0 = cls._compute_parallax_height(cnt2, xy_ground, center_xy, pose2, K, D)

        r = float(np.linalg.norm(center_xy - C1[:2]))
        mag = max(0.4, 1.0 - H0 / C1[2])
        delta_r = r * (H0 / max(C1[2] - H0, 100.0))

        # Directional radial relief subtraction
        L0 = max(18.0, L_ground * mag - 0.70 * delta_r * c0)
        W0 = max(18.0, W_ground * mag - 0.70 * delta_r * c1)
        c_xy0 = center_xy - 0.45 * delta_r * u_rad

        return np.array([c_xy0[0], c_xy0[1], L0, W0, H0, psi0], dtype=np.float64)

    @classmethod
    def compute_hypotheses(
        cls,
        cnt1: np.ndarray,
        cnt2: np.ndarray,
        pose1: Dict,
        pose2: Dict,
        K: np.ndarray,
        D: np.ndarray,
    ) -> List[np.ndarray]:
        """Generate multi-start cuboid hypotheses across varying height and de-biasing levels."""
        C1 = np.asarray(pose1["camera_center_mm"], dtype=np.float64).ravel()
        xy_ground, center_xy, L_ground, W_ground, psi0, u_rad, c0, c1 = cls._extract_ground_and_radial(
            cnt1, pose1, K, D
        )
        H0 = cls._compute_parallax_height(cnt2, xy_ground, center_xy, pose2, K, D)

        r = float(np.linalg.norm(center_xy - C1[:2]))
        hypotheses = []
        h_candidates = [0.75 * H0, 0.90 * H0, H0, 1.15 * H0, 35.0, 55.0, 70.0]

        for h_val in h_candidates:
            mag = max(0.4, 1.0 - h_val / C1[2])
            delta_r = r * (h_val / max(C1[2] - h_val, 100.0))
            for coeff in (0.35, 0.70):
                L_h = max(18.0, L_ground * mag - coeff * delta_r * c0)
                W_h = max(18.0, W_ground * mag - coeff * delta_r * c1)
                c_xy_h = center_xy - 0.45 * delta_r * u_rad
                hypotheses.append(
                    np.array([c_xy_h[0], c_xy_h[1], L_h, W_h, h_val, psi0], dtype=np.float64)
                )

        return hypotheses
