"""Epipolar Ray Projection and Hungarian Two-View Association.

Phase 2 Gate - Multi-Feature Stereo Matching & Epipolar Box-Prompt Recovery:
1. Projects 3D height rays Z in [0, 300 mm] from Zenith view mask center to Oblique view.
2. Combines geometric epipolar distance and HSV color histogram correlation in Hungarian cost.
3. Automatically triggers SAM 3.1 Epipolar Box-Prompt Recovery when oblique mask area < 65% of expected projection.
"""
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np


class EpipolarMatcher:
    """Matches 2D candidate detections between Zenith (Topdown) and Oblique views."""

    def __init__(
        self,
        max_epipolar_dist_px: float = 140.0,
        z_range_mm: Tuple[float, float] = (0.0, 250.0),
        appearance_weight: float = 40.0,
    ):
        self.max_epipolar_dist_px = float(max_epipolar_dist_px)
        self.z_range_mm = z_range_mm
        self.appearance_weight = float(appearance_weight)

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
    def _extract_hsv_hist(image_bgr: Optional[np.ndarray], mask: Optional[np.ndarray]) -> Optional[np.ndarray]:
        """Extract L2-normalized 3D HSV histogram from eroded mask region."""
        if image_bgr is None or mask is None:
            return None
        kernel = np.ones((5, 5), np.uint8)
        eroded = cv2.erode(mask, kernel, iterations=1)
        if cv2.countNonZero(eroded) < 30:
            eroded = mask
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], eroded, [12, 6, 6], [0, 180, 0, 256, 0, 256])
        cv2.normalize(hist, hist)
        return hist.flatten()

    @staticmethod
    def _hungarian_assignment(cost_matrix: np.ndarray) -> List[Tuple[int, int]]:
        """Globally optimal rectangular Hungarian assignment in O(n^3)."""
        costs = np.asarray(cost_matrix, dtype=np.float64)
        if costs.ndim != 2 or not np.isfinite(costs).all():
            raise ValueError("Cost matrix must be finite and two-dimensional")
        n0, m0 = costs.shape
        if n0 == 0 or m0 == 0:
            return []
        swapped = n0 > m0
        if swapped:
            costs = costs.T
        n, m = costs.shape
        u = np.zeros(n + 1)
        v = np.zeros(m + 1)
        p = np.zeros(m + 1, dtype=np.int32)
        way = np.zeros(m + 1, dtype=np.int32)
        for i in range(1, n + 1):
            p[0] = i
            j0 = 0
            minv = np.full(m + 1, np.inf)
            used = np.zeros(m + 1, dtype=bool)
            while True:
                used[j0] = True
                i0 = p[j0]
                delta, j1 = np.inf, 0
                for j in range(1, m + 1):
                    if used[j]:
                        continue
                    current = costs[i0 - 1, j - 1] - u[i0] - v[j]
                    if current < minv[j]:
                        minv[j] = current
                        way[j] = j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
                for j in range(m + 1):
                    if used[j]:
                        u[p[j]] += delta
                        v[j] -= delta
                    else:
                        minv[j] -= delta
                j0 = j1
                if p[j0] == 0:
                    break
            while True:
                j1 = way[j0]
                p[j0] = p[j1]
                j0 = j1
                if j0 == 0:
                    break
        pairs = [(int(p[j]) - 1, j - 1) for j in range(1, m + 1) if p[j] > 0]
        if swapped:
            return [(j, i) for i, j in pairs]
        return pairs

    def match_views(
        self,
        top_candidates: List[Dict],
        ob_candidates: List[Dict],
        pose_top: Dict,
        pose_ob: Dict,
        K: np.ndarray,
        D: np.ndarray,
        top_image: Optional[np.ndarray] = None,
        ob_image: Optional[np.ndarray] = None,
        sam_segmenter: Optional[Any] = None,
    ) -> List[Tuple[int, int, float]]:
        """Match topdown candidates to oblique candidates via multi-feature Hungarian cost."""
        if not top_candidates or not ob_candidates:
            return []

        top_rvec = np.asarray(pose_top["rvec"], dtype=np.float64)
        top_tvec = np.asarray(pose_top["tvec"], dtype=np.float64)
        ob_rvec = np.asarray(pose_ob["rvec"], dtype=np.float64)
        ob_tvec = np.asarray(pose_ob["tvec"], dtype=np.float64)

        n_top = len(top_candidates)
        n_ob = len(ob_candidates)
        cost_matrix = np.full((n_top, n_ob), 1e6, dtype=np.float64)

        # 1. Precompute epipolar segments for all topdown items
        epipolar_segments = []
        for i, cand_top in enumerate(top_candidates):
            tc = cand_top["center"]
            p3d_z0 = self._raycast_pixel_to_plane_z(tc, K, D, top_rvec, top_tvec, self.z_range_mm[0])
            p3d_z1 = self._raycast_pixel_to_plane_z(tc, K, D, top_rvec, top_tvec, self.z_range_mm[1])
            pts_2d, _ = cv2.projectPoints(np.array([p3d_z0, p3d_z1]), ob_rvec, ob_tvec, K, D)
            seg_start, seg_end = pts_2d[0, 0], pts_2d[1, 0]
            epipolar_segments.append((seg_start, seg_end))

        # 2. Extract appearance features if images provided
        top_hists = [
            self._extract_hsv_hist(top_image, c.get("mask")) for c in top_candidates
        ] if top_image is not None else [None] * n_top
        ob_hists = [
            self._extract_hsv_hist(ob_image, c.get("mask")) for c in ob_candidates
        ] if ob_image is not None else [None] * n_ob

        # 3. Fill multi-feature cost matrix
        for i, (seg_start, seg_end) in enumerate(epipolar_segments):
            for j, cand_ob in enumerate(ob_candidates):
                ob_c = np.asarray(cand_ob["center"], dtype=np.float64)
                d_epi = self._distance_point_to_segment(ob_c, seg_start, seg_end)
                cost = d_epi
                if top_hists[i] is not None and ob_hists[j] is not None:
                    corr = float(cv2.compareHist(top_hists[i], ob_hists[j], cv2.HISTCMP_CORREL))
                    cost += self.appearance_weight * max(0.0, 1.0 - corr)
                cost_matrix[i, j] = cost

        cutoff = self.max_epipolar_dist_px + self.appearance_weight
        unmatched_penalty = cutoff + 1.0
        valid = cost_matrix <= cutoff
        effective = np.where(valid, cost_matrix, 2.0 * unmatched_penalty + cost_matrix)
        padded = np.column_stack([effective, np.full((n_top, n_top), unmatched_penalty)])
        assignments = self._hungarian_assignment(padded)

        matched_pairs = []
        for i, j in assignments:
            if j < n_ob and valid[i, j]:
                matched_pairs.append((i, j, float(cost_matrix[i, j])))

        # 4. Epipolar Box-Prompt Recovery for truncated oblique masks
        if ob_image is not None and sam_segmenter is not None and hasattr(sam_segmenter, "recover_box_prompt"):
            for idx, (i, j, cost_val) in enumerate(matched_pairs):
                cnt_top = top_candidates[i].get("contour")
                if cnt_top is None or len(cnt_top) < 3:
                    continue
                try:
                    rect = cv2.minAreaRect(cnt_top.astype(np.float32))
                    box_pts = cv2.boxPoints(rect)
                    R_top, _ = cv2.Rodrigues(top_rvec)
                    C_top = -R_top.T @ top_tvec.ravel()
                    norm_box = cv2.undistortPoints(box_pts.reshape(-1, 1, 2), K, D).reshape(-1, 2)
                    dirs = (R_top.T @ np.c_[norm_box, np.ones(4)].T).T
                    lamb = -C_top[2] / np.where(np.abs(dirs[:, 2]) > 1e-8, dirs[:, 2], -1e-8)
                    g_ground = C_top + dirs * lamb[:, None]

                    g_top = g_ground.copy()
                    g_top[:, 2] = 65.0
                    pts_3d = np.vstack([g_ground, g_top])
                    proj_2d, _ = cv2.projectPoints(pts_3d, ob_rvec, ob_tvec, K, D)
                    proj_2d = proj_2d.reshape(-1, 2)

                    px1, py1 = np.min(proj_2d, axis=0)
                    px2, py2 = np.max(proj_2d, axis=0)
                    expected_area = float((px2 - px1) * (py2 - py1))
                    actual_area = float(ob_candidates[j].get("area_px", 0))

                    if actual_area < 0.65 * expected_area:
                        recovered = sam_segmenter.recover_box_prompt(
                            ob_image, [px1, py1, px2, py2], padding=20
                        )
                        if recovered and recovered["area_px"] > actual_area:
                            ob_candidates[j] = recovered
                except Exception:
                    pass

        return matched_pairs
