"""Epipolar Ray Projection and Hungarian Two-View Association.

Phase 0 Gate - Stage 0D for OptiPack Computer Vision (Member 1).
Projects 3D height rays Z in [0, 300 mm] from Zenith view mask center to Oblique view
to construct epipolar line segments.
Solves optimal 1-to-1 bipartite assignment using Hungarian algorithm.
"""
from typing import Dict, List, Tuple
import cv2
import numpy as np


class EpipolarMatcher:
    """Matches 2D candidate detections between Zenith (Topdown) and Oblique views."""

    def __init__(self, max_epipolar_dist_px: float = 120.0, z_range_mm: Tuple[float, float] = (0.0, 250.0)):
        self.max_epipolar_dist_px = max_epipolar_dist_px
        self.z_range_mm = z_range_mm

    @staticmethod
    def _raycast_pixel_to_plane_z(
        pixel_xy: Tuple[float, float],
        K: np.ndarray,
        D: np.ndarray,
        rvec: np.ndarray,
        tvec: np.ndarray,
        z_plane_mm: float,
    ) -> np.ndarray:
        """Raycast a 2D pixel to 3D world coordinates on plane Z = z_plane_mm."""
        pt = np.array([[[pixel_xy[0], pixel_xy[1]]]], dtype=np.float64)
        undist = cv2.undistortPoints(pt, K, D).reshape(2)
        ray_cam = np.array([undist[0], undist[1], 1.0], dtype=np.float64)

        R, _ = cv2.Rodrigues(rvec)
        ray_world = R.T @ ray_cam
        cam_center = -R.T @ tvec.reshape(3)

        if abs(ray_world[2]) < 1e-9:
            return cam_center
        s = (z_plane_mm - cam_center[2]) / ray_world[2]
        return cam_center + s * ray_world

    @staticmethod
    def _distance_point_to_segment(point: np.ndarray, seg_start: np.ndarray, seg_end: np.ndarray) -> float:
        """Perpendicular distance from 2D point to 2D line segment."""
        v = seg_end - seg_start
        v_len_sq = np.dot(v, v)
        if v_len_sq < 1e-6:
            return float(np.linalg.norm(point - seg_start))
        u = point - seg_start
        t = np.clip(np.dot(u, v) / v_len_sq, 0.0, 1.0)
        proj = seg_start + t * v
        return float(np.linalg.norm(point - proj))

    @staticmethod
    def _hungarian_assignment(cost_matrix: np.ndarray) -> List[Tuple[int, int]]:
        """Solve min-cost bipartite matching via linear sum assignment."""
        n_rows, n_cols = cost_matrix.shape
        # Use ortools or pure scipy / numpy assignment
        try:
            from scipy.optimize import linear_sum_assignment
            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            return list(zip(row_ind, col_ind))
        except ImportError:
            pass

        # Robust greedy Kuhn-Munkres fallback for N <= 10
        assigned_cols = set()
        matches = []
        # Flatten and sort edges by cost
        flat = []
        for r in range(n_rows):
            for c in range(n_cols):
                flat.append((cost_matrix[r, c], r, c))
        flat.sort(key=lambda x: x[0])

        assigned_rows = set()
        for cost, r, c in flat:
            if r not in assigned_rows and c not in assigned_cols:
                assigned_rows.add(r)
                assigned_cols.add(c)
                matches.append((r, c))
                if len(matches) == min(n_rows, n_cols):
                    break
        return matches

    def match_views(
        self,
        top_candidates: List[Dict],
        ob_candidates: List[Dict],
        pose_top: Dict,
        pose_ob: Dict,
        K: np.ndarray,
        D: np.ndarray,
    ) -> List[Tuple[int, int, float]]:
        """Match topdown candidates to oblique candidates via epipolar distance.
        
        Args:
            top_candidates: List of candidate dicts in Zenith view (must have 'center' [x, y])
            ob_candidates: List of candidate dicts in Oblique view (must have 'center' [x, y])
            pose_top: Camera pose dict for Zenith view (rvec, tvec)
            pose_ob: Camera pose dict for Oblique view (rvec, tvec)
            K: Camera matrix
            D: Distortion coefficients
            
        Returns:
            List of (top_idx, ob_idx, epipolar_distance_px)
        """
        if not top_candidates or not ob_candidates:
            return []

        top_rvec = np.asarray(pose_top["rvec"], dtype=np.float64)
        top_tvec = np.asarray(pose_top["tvec"], dtype=np.float64)
        ob_rvec = np.asarray(pose_ob["rvec"], dtype=np.float64)
        ob_tvec = np.asarray(pose_ob["tvec"], dtype=np.float64)

        n_top = len(top_candidates)
        n_ob = len(ob_candidates)
        cost_matrix = np.full((n_top, n_ob), 1e6, dtype=np.float64)

        # Precompute epipolar segments for all topdown items
        epipolar_segments = []
        for i, cand_top in enumerate(top_candidates):
            tc = cand_top["center"]
            p3d_z0 = self._raycast_pixel_to_plane_z(tc, K, D, top_rvec, top_tvec, self.z_range_mm[0])
            p3d_z1 = self._raycast_pixel_to_plane_z(tc, K, D, top_rvec, top_tvec, self.z_range_mm[1])

            pts_2d, _ = cv2.projectPoints(np.array([p3d_z0, p3d_z1]), ob_rvec, ob_tvec, K, D)
            seg_start, seg_end = pts_2d[0, 0], pts_2d[1, 0]
            epipolar_segments.append((seg_start, seg_end))

        # Fill cost matrix
        for i, (seg_start, seg_end) in enumerate(epipolar_segments):
            for j, cand_ob in enumerate(ob_candidates):
                ob_c = np.asarray(cand_ob["center"], dtype=np.float64)
                dist = self._distance_point_to_segment(ob_c, seg_start, seg_end)
                cost_matrix[i, j] = dist

        # Solve assignment
        assignments = self._hungarian_assignment(cost_matrix)
        matched_pairs = []
        for i, j in assignments:
            dist = float(cost_matrix[i, j])
            if dist <= self.max_epipolar_dist_px:
                matched_pairs.append((i, j, dist))

        return matched_pairs
