"""Regression tests for optional fast ArUco/planar-PnP research ablation."""
import cv2
import numpy as np
import pytest

from backend.app.cv.aruco_detector import marker_world_corners
from experiments.real_t01.fast_pose_ablation import (
    detect_correspondences, solve_planar,
)

def test_fast_detector_rejects_invalid_scale_or_input():
    gray=np.full((200,250),255,np.uint8)
    for scale in (-.5,0,1.01):
        with pytest.raises(ValueError):detect_correspondences(gray,scale)
    with pytest.raises(ValueError):
        detect_correspondences(np.zeros((200,250,3),np.uint8),.5)
    with pytest.raises(ValueError):
        detect_correspondences(gray.astype(np.float32),.5)
    world,pixels,found=detect_correspondences(gray,.5)
    assert len(world)==len(pixels)==len(found)==0

def _synthetic_board():
    """Place legitimate OpenCV ArUco markers on an upright white board."""
    gray=np.full((900,1200),255,np.uint8)
    origins={0:(0,0),1:(237,0),2:(237,150),3:(0,150)}
    for tag,(x,y) in origins.items():
        marker=cv2.aruco.generateImageMarker(
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),tag,120)
        px=110+x*3
        py=770-(y+40)*3
        gray[py:py+120,px:px+120]=marker
    return gray

@pytest.mark.parametrize("scale",[1.0,.5,.35])
def test_fast_marker_correspondences_stay_in_original_pixel_grid(scale):
    gray=_synthetic_board()
    obj,px,detected=detect_correspondences(gray,scale)
    assert len(detected)==4
    assert set(detected)==set(range(4))
    assert obj.shape==(16,3) and px.shape==(16,2)
    assert (px[:,0]>=0).all() and (px[:,0]<=gray.shape[1]).all()
    assert (px[:,1]>=0).all() and (px[:,1]<=gray.shape[0]).all()

@pytest.mark.parametrize("solver",["iterative","epnp_refine","ippe_refine"])
def test_planar_pnp_recovers_valid_synthetic_camera(solver):
    obj=np.vstack([marker_world_corners(i) for i in range(4)])
    K=np.array([[960.,0,640.],[0,960.,480.],[0,0,1.]])
    dist=np.zeros(5)
    # Camera must physically look down onto the plane (center Z > 0).
    rvec=np.array([[3.0],[-.13],[.04]],float)
    tvec=np.array([[-135.],[-105.],[690.]],float)
    pts,_=cv2.projectPoints(obj,rvec,tvec,K,dist)
    sol=solve_planar(obj,pts.reshape(-1,2),K,dist,solver)
    assert sol is not None
    assert sol[0]<1e-4
    R,_=cv2.Rodrigues(rvec)
    center=(-R.T@tvec).ravel()
    assert np.linalg.norm(sol[3]-center)<.01

def test_plane_solver_does_not_invent_pose_without_markers():
    K=np.eye(3,dtype=float)
    assert solve_planar(np.empty((0,3)),np.empty((0,2)),K,np.zeros(5),"iterative") is None
    with pytest.raises(ValueError):
        solve_planar(np.zeros((8,3)),np.zeros((8,2)),K,np.zeros(5),"not_a_solver")
