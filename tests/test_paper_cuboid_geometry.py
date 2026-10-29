"""Geometry regression tests for the CubeSLAM-inspired cuboid edge objective."""
import json
from pathlib import Path

import cv2
import numpy as np

from experiments.real_t01.paper_edge_experiment import (
    SCALE,model_vertices,visible_edge_pairs,project_bbox,residual
)

ROOT=Path(__file__).resolve().parents[1]
def synthetic_scene():
    meta=json.loads((ROOT/"experiments/synthetic_t01/ground_truth.json").read_text())
    K=np.array(meta["camera_intrinsic_K"],float)
    cfg=meta["images"][1]
    R=np.array(cfg["rotation_world_to_camera"],float)
    t=np.array(cfg["translation_world_to_camera_mm"],float).reshape(3,1)
    r,_=cv2.Rodrigues(R)
    pose={"camera_matrix":K,"dist_coeffs":np.zeros(5),"rvec":r,"tvec":t,
          "R":R,"camera_center_mm":(-R.T@t).ravel()}
    b=meta["box_ground_truth"]
    p=np.array([b["x0_mm"]+b["length_mm"]/2,b["y0_mm"]+b["width_mm"]/2,
                b["length_mm"],b["width_mm"],b["height_mm"],0.])
    return pose,p

def test_3d_cuboid_vertices_have_ground_and_top_planes():
    pose,p=synthetic_scene()
    verts=model_vertices(p)
    assert verts.shape==(8,3)
    np.testing.assert_allclose(verts[:4,2],0.)
    np.testing.assert_allclose(verts[4:,2],105.)
    np.testing.assert_allclose(verts[:4,:2].min(axis=0),[365,27])
    np.testing.assert_allclose(verts[:4,:2].max(axis=0),[565,167])

def test_projected_cuboid_edges_match_perfect_synthetic_evidence():
    pose,p=synthetic_scene()
    vertices=model_vertices(p)
    corners,_=cv2.projectPoints(vertices,pose["rvec"],pose["tvec"],
                                pose["camera_matrix"],pose["dist_coeffs"])
    pts=corners.reshape(-1,2)*SCALE
    canvas=np.zeros((int(1050*SCALE),int(1600*SCALE)),np.uint8)
    for a,b,_ in visible_edge_pairs(p,pose["camera_center_mm"]):
        cv2.line(canvas,tuple(np.round(pts[a]).astype(int)),
                 tuple(np.round(pts[b]).astype(int)),255,2)
    dist=cv2.distanceTransform(255-canvas,cv2.DIST_L2,3)
    edge_map={"synthetic":dist}
    bbox=project_bbox(p,pose)
    item=[("synthetic",pose,bbox)]
    true_res=residual(p,item,edge_map)
    moved=p.copy()
    moved[0]+=25
    moved[1]-=20
    moved[2]*=1.15
    moved[4]*=.8
    moved_res=residual(moved,item,edge_map)
    assert np.mean(true_res**2) < np.mean(moved_res**2)*.6

def test_real_method_outputs_do_not_claim_t01_go():
    p=ROOT/"experiments/real_t01/paper_edge_experiment.json"
    q=ROOT/"experiments/real_t01/paper_two_view_results.json"
    four=json.loads(p.read_text())
    pairs=json.loads(q.read_text())
    assert four["status"]=="EXPERIMENTAL_NOT_T01_GATE"
    assert four["no_ground_truth_in_optimizer"] is True
    assert pairs["status"]=="EXPLORATORY_NOT_AUTONOMOUS_T01"
    assert len(four["individual"])==5
    assert set(pairs["pair_results"])=={"Trial01","Trial02","Trial03"}
    for trial,part in pairs["pair_results"].items():
        assert len(part["images"])==2 and len(part["items"])==5
