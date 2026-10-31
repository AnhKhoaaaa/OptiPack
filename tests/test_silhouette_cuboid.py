"""Pure-geometry tests for the silhouette-constrained cuboid research ablation."""
import json
from pathlib import Path

import cv2
import numpy as np

from experiments.real_t01.silhouette_fit import (
    SCALE, SILHOUETTE_SAMPLES, sampled_outline, residual, refine, model_vertices,
)
from experiments.real_t01.exploratory_fit import project_bbox
from tests.test_paper_cuboid_geometry import synthetic_scene

ROOT=Path(__file__).resolve().parents[1]

def test_equal_arc_length_samples_on_rectangle():
    hull=np.array([[0,0],[50,0],[50,20],[0,20]],float)
    points=sampled_outline(hull,n=28)
    assert points.shape==(28,2)
    assert np.isfinite(points).all()
    assert np.all(points[:,0]>=0) and np.all(points[:,0]<=50)
    assert np.all(points[:,1]>=0) and np.all(points[:,1]<=20)
    steps=np.linalg.norm(np.roll(points,-1,axis=0)-points,axis=1)
    assert steps.max()<8.01
    assert steps.min()>3.0

def test_perfect_synthetic_silhouette_scores_better_than_shifted_cuboid():
    pose,p=synthetic_scene()
    verts=model_vertices(p)
    proj,_=cv2.projectPoints(verts,pose["rvec"],pose["tvec"],pose["camera_matrix"],pose["dist_coeffs"])
    hull=cv2.convexHull((proj.reshape(-1,2)*SCALE).astype(np.float32)).reshape(-1,2)
    ref=sampled_outline(hull)
    canvas=np.zeros((int(1050*SCALE)+4,int(1600*SCALE)+4),np.uint8)
    cv2.polylines(canvas,[np.round(hull).astype(np.int32)],True,255,2)
    dist=cv2.distanceTransform(255-canvas,cv2.DIST_L2,3)
    example=[(pose,project_bbox(p,pose),dist,ref)]
    correct=residual(p,example)
    shifted=p.copy()
    shifted[0]+=25
    shifted[1]-=20
    shifted[2]*=1.15
    shifted[4]*=.8
    wrong=residual(shifted,example)
    assert len(correct)==len(wrong)==4+SILHOUETTE_SAMPLES*2
    assert float(correct@correct)<float(wrong@wrong)*.2
    _,opt_cost=refine(shifted,example,18)
    assert opt_cost<float(wrong@wrong)

def test_comparison_is_labeled_exploratory_not_gate_pass():
    p=ROOT/"experiments/real_t01/silhouette_experiment.json"
    res=json.loads(p.read_text(encoding="utf-8"))
    assert res["status"]=="EXPLORATORY_NOT_T01_GATE"
    assert set(res["trials"])=={"Trial01","Trial02","Trial03"}
    assert "no GT" in res["constraints"]
    for row in res["trials"].values():
        assert len(row["items"])==5
