"""Closed-form Geometric 1ms Parallax Initializer.

Phase 0 Gate - Stage 0B for OptiPack Computer Vision (Member 1).
Computes initial 3D cuboid parameters [cx0, cy0, L0, W0, H0, psi0] from two views:
1. Zenith (Topdown) mask: extracts ground center (cx0, cy0), yaw psi0, and ground footprint (L_ground, W_ground)
2. Oblique mask: extracts top tangent line / parallax displacement to compute initial height H0
3. Perspective magnification correction: adjusts L0, W0 based on height H0 and camera distance.
"""
from typing import Dict, Tuple
import cv2
import numpy as np


class ClosedFormInitializer:
    """1ms closed-form geometric initializer for 3D cuboid parameters."""

    @staticmethod
    def compute_initial_guess(
        cnt1: np.ndarray,
        cnt2: np.ndarray,
        pose1: Dict,
        pose2: Dict,
        K: np.ndarray,
        D: np.ndarray,
    ) -> np.ndarray:
        """Compute closed-form initial cuboid parameters [cx0, cy0, L0, W0, H0, psi0].
        
        Args:
            cnt1: 2D contour points of object in Camera 1 (Zenith / Topdown).
            cnt2: 2D contour points of object in Camera 2 (Oblique).
            pose1: Pose dictionary for Camera 1 (R, tvec, camera_center_mm).
            pose2: Pose dictionary for Camera 2 (R, tvec, camera_center_mm).
            K: 3x3 camera intrinsic matrix.
            D: Distortion coefficients array.

        Returns:
            np.ndarray of shape (6,) containing [cx0, cy0, L0, W0, H0, psi0].
        """
        R1 = np.asarray(pose1["R"], dtype=np.float64)
        t1 = np.asarray(pose1["tvec"], dtype=np.float64).reshape(3, 1)
        C1 = np.asarray(pose1["camera_center_mm"], dtype=np.float64).ravel()

        R2 = np.asarray(pose2["R"], dtype=np.float64)
        t2 = np.asarray(pose2["tvec"], dtype=np.float64).reshape(3, 1)
        C2 = np.asarray(pose2["camera_center_mm"], dtype=np.float64).ravel()

        rvec1 = np.asarray(pose1["rvec"], dtype=np.float64)
        rvec2 = np.asarray(pose2["rvec"], dtype=np.float64)

        # 1. Zenith View: Raycast ground footprint and yaw
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

        # 2. Oblique View: Height H0 from top tangent line & planar parallax
        p2_z0, _ = cv2.projectPoints(np.array([[center_xy[0], center_xy[1], 0.0]]), rvec2, t2, K, D)
        p2_z100, _ = cv2.projectPoints(np.array([[center_xy[0], center_xy[1], 100.0]]), rvec2, t2, K, D)
        v_par = (p2_z100 - p2_z0).ravel()
        norm_v = np.linalg.norm(v_par)
        u_par = v_par / (norm_v if norm_v > 1e-9 else 1.0)

        # Boundary point with maximum displacement along parallax direction
        proj = np.dot(cnt2, u_par)
        top_idx = int(np.argmax(proj))
        top_pt_px = cnt2[top_idx]

        # Top tangent line l_top in Camera 2:
        norm_top = cv2.undistortPoints(top_pt_px.reshape(1, 1, 2), K, D).reshape(2)
        r2_top = R2.T @ np.r_[norm_top, 1.0]
        r2_top /= np.linalg.norm(r2_top)

        # Intersection with vertical ray at center_xy
        denom = float(np.linalg.norm(r2_top[:2]))
        if denom > 1e-6:
            s = float(np.linalg.norm(center_xy[:2] - C2[:2]) / denom)
            H0 = float(np.clip(C2[2] + s * r2_top[2], 20.0, 150.0))
        else:
            H0 = 50.0

        # 3. Perspective magnification correction:
        # L0 = (1 - H0 / Z_cam1) * L_ground, W0 = (1 - H0 / Z_cam1) * W_ground
        scale_corr = float(max(0.4, 1.0 - H0 / C1[2]))
        L0 = float(max(20.0, L_ground * scale_corr))
        W0 = float(max(20.0, W_ground * scale_corr))

        return np.array([center_xy[0], center_xy[1], L0, W0, H0, psi0], dtype=np.float64)

