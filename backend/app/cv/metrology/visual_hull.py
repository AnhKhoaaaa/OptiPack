"""3D Visual Hull Voxel Carving for Cuboid and Non-Cuboid Metrology.

Implements Section 3.4 of optipack_cv_optimization_plan.md:
- 3D voxel carving across dual views (Zenith + Oblique).
- Computes 2D contour circularity and convexity.
- Computes 3D volumetric solidity eta_3d = Vol(V_hull) / (L * W * H).
- Extracts minimum oriented bounding prism (OBB) for irregular objects.
- Classifies items into: rigid_cuboid, cylinder, irregular_or_deformable.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import cv2
import numpy as np


class VisualHullCarver:
    """Carves 3D space with two silhouettes to analyze geometry and detect non-cuboids."""

    def __init__(self, nx: int = 28, ny: int = 28, nz: int = 20):
        self.nx = int(nx)
        self.ny = int(ny)
        self.nz = int(nz)

    def carve_and_analyze(
        self,
        mask_top: np.ndarray,
        mask_ob: np.ndarray,
        cnt_top: np.ndarray,
        pose_top: Dict,
        pose_ob: Dict,
        K: np.ndarray,
        D: np.ndarray,
        p_cuboid: np.ndarray,
    ) -> Dict[str, Any]:
        """Carve voxel grid and extract 3D shape properties."""
        cx, cy, L_cub, W_cub, H_cub, psi = [float(v) for v in p_cuboid]
        H_top, W_top = mask_top.shape[:2]
        H_ob, W_ob = mask_ob.shape[:2]

        # 1. 2D shape metrics on Zenith view
        area_2d = float(cv2.contourArea(cnt_top.astype(np.float32)))
        perimeter = float(cv2.arcLength(cnt_top.astype(np.float32), True))
        circularity = float((4.0 * np.pi * area_2d) / max(perimeter * perimeter, 1.0))
        hull_2d = cv2.convexHull(cnt_top.astype(np.float32))
        hull_area = float(cv2.contourArea(hull_2d))
        convexity = float(area_2d / max(hull_area, 1.0))

        # 2. Voxel Grid centered at cuboid hypothesis
        half_l = max(25.0, 0.70 * L_cub)
        half_w = max(25.0, 0.70 * W_cub)
        max_h = max(35.0, 1.30 * H_cub)

        xs = np.linspace(-half_l, half_l, self.nx)
        ys = np.linspace(-half_w, half_w, self.ny)
        zs = np.linspace(2.0, max_h, self.nz)

        X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
        cos_p, sin_p = np.cos(psi), np.sin(psi)
        Xr = X * cos_p - Y * sin_p + cx
        Yr = X * sin_p + Y * cos_p + cy

        pts_3d = np.stack([Xr.ravel(), Yr.ravel(), Z.ravel()], axis=-1)

        rvec1 = np.asarray(pose_top["rvec"], dtype=np.float64)
        tvec1 = np.asarray(pose_top["tvec"], dtype=np.float64)
        rvec2 = np.asarray(pose_ob["rvec"], dtype=np.float64)
        tvec2 = np.asarray(pose_ob["tvec"], dtype=np.float64)

        p1_2d, _ = cv2.projectPoints(pts_3d, rvec1, tvec1, K, D)
        p2_2d, _ = cv2.projectPoints(pts_3d, rvec2, tvec2, K, D)

        u1 = np.clip(np.round(p1_2d[:, 0, 0]).astype(int), 0, W_top - 1)
        v1 = np.clip(np.round(p1_2d[:, 0, 1]).astype(int), 0, H_top - 1)

        u2 = np.clip(np.round(p2_2d[:, 0, 0]).astype(int), 0, W_ob - 1)
        v2 = np.clip(np.round(p2_2d[:, 0, 1]).astype(int), 0, H_ob - 1)

        in_mask1 = mask_top[v1, u1] > 0
        in_mask2 = mask_ob[v2, u2] > 0

        in_hull = in_mask1 & in_mask2
        voxels_hull = pts_3d[in_hull]

        voxel_vol = (
            (2.0 * half_l / max(self.nx - 1, 1))
            * (2.0 * half_w / max(self.ny - 1, 1))
            * (max_h / max(self.nz - 1, 1))
        )
        vol_hull = float(len(voxels_hull) * voxel_vol)

        if len(voxels_hull) < 25:
            shape_class = "cylinder" if circularity >= 0.85 else "rigid_cuboid"
            return {
                "shape_class": shape_class,
                "length_mm": L_cub,
                "width_mm": W_cub,
                "height_mm": H_cub,
                "circularity": circularity,
                "convexity": convexity,
                "solidity_3d": 1.0,
                "vol_hull_mm3": vol_hull,
                "stackable": shape_class == "rigid_cuboid",
            }

        # 3. OBB on lower portion of voxel hull
        z_mid = np.percentile(voxels_hull[:, 2], 65)
        lower_voxels = voxels_hull[voxels_hull[:, 2] <= z_mid]
        if len(lower_voxels) < 10:
            lower_voxels = voxels_hull

        rect_hull = cv2.minAreaRect(lower_voxels[:, :2].astype(np.float32))
        (rx, ry), (rw, rh), _ = rect_hull
        L_hull = float(max(rw, rh))
        W_hull = float(min(rw, rh))
        H_hull = float(max(15.0, np.percentile(voxels_hull[:, 2], 98) - np.percentile(voxels_hull[:, 2], 2)))

        bounding_vol = max(1.0, L_hull * W_hull * H_hull)
        solidity_3d = float(np.clip(vol_hull / bounding_vol, 0.05, 1.0))

        # 4. Shape Classification & Parameter Resolution
        if circularity >= 0.88:
            shape_class = "cylinder"
            # For cylinders, diameter is symmetric from bounding box in mm
            diameter = float((L_hull + W_hull) / 2.0)
            L_out, W_out = diameter, diameter
            H_out = H_hull
            stackable = False  # Cylindrical items cannot support heavy boxes on top safely
        elif convexity < 0.82 or solidity_3d < 0.45:
            shape_class = "irregular_or_deformable"
            L_out, W_out = L_hull, W_hull
            H_out = H_hull
            stackable = False
        else:
            shape_class = "rigid_cuboid"
            L_out, W_out = L_cub, W_cub
            H_out = H_cub
            stackable = True

        return {
            "shape_class": shape_class,
            "length_mm": L_out,
            "width_mm": W_out,
            "height_mm": H_out,
            "circularity": circularity,
            "convexity": convexity,
            "solidity_3d": solidity_3d,
            "vol_hull_mm3": vol_hull,
            "stackable": stackable,
        }
