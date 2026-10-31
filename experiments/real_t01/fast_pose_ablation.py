"""Research ablation: fast downsampled ArUco+subpixel, IPPE vs iterative PnP.

Source concepts:
  Collins & Bartoli, Infinitesimal Plane-Based Pose Estimation, IJCV 2014.
  Lepetit et al., EPnP, IJCV 2009.
The board is planar. These solvers DO NOT fix untrusted camera intrinsics,
printed marker geometry, blur, or a poor physical capture.
Independent NumPy/OpenCV evaluation; no paper implementation copied.
"""
from pathlib import Path
from time import perf_counter
import json
import cv2
import numpy as np
from backend.app.cv.aruco_detector import detect_aruco_calibration_sheet, marker_world_corners
from experiments.real_t01.calibrate_dataset import load_landscape

HERE=Path(__file__).resolve().parent
DICT=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

def detect_correspondences(gray, scale=0.5):
    """Fast coarse detection plus fine full-resolution corner refinement."""
    if gray.ndim != 2 or gray.dtype != np.uint8:raise ValueError("uint8 grayscale expected")
    if not 0<scale<=1:raise ValueError("scale must be (0,1]")
    h,w=gray.shape
    if scale<1:
        small=cv2.resize(gray,(round(w*scale),round(h*scale)),interpolation=cv2.INTER_AREA)
    else:small=gray
    params=cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX
    params.cornerRefinementWinSize=5
    detected,ids,_=cv2.aruco.ArucoDetector(DICT,params).detectMarkers(small)
    if ids is None:return np.empty((0,3),float),np.empty((0,2),float),[]
    world, pixels, seen=[],[],[]
    sx,sy=w/small.shape[1],h/small.shape[0]
    for c,i in zip(detected,ids.ravel()):
        i=int(i)
        if i not in range(4) or i in seen:continue
        xy=np.asarray(c,np.float32).reshape(4,2).copy()
        xy[:,0]*=sx;xy[:,1]*=sy
        if scale!=1:
            cv2.cornerSubPix(gray,xy,(5,5),(-1,-1),
                   (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER,30,.005))
        seen.append(i)
        world.extend(marker_world_corners(i))
        pixels.extend(xy.astype(np.float64))
    return np.asarray(world,np.float64).reshape(-1,3),np.asarray(pixels,np.float64).reshape(-1,2),seen

def solve_planar(obj,pixels,K,dist,method):
    """Both candidates for planar IPPE; select valid minimum reprojection error."""
    if len(obj)<8:return None
    if method=="iterative":
        ok,r,t=cv2.solvePnP(obj,pixels,K,dist,flags=cv2.SOLVEPNP_ITERATIVE)
        candidates=[(r,t)] if ok else []
    elif method=="epnp_refine":
        ok,r,t=cv2.solvePnP(obj,pixels,K,dist,flags=cv2.SOLVEPNP_EPNP)
        candidates=[(r,t)] if ok else []
    elif method=="ippe_refine":
        result=cv2.solvePnPGeneric(obj,pixels,K,dist,flags=cv2.SOLVEPNP_IPPE)
        candidates=list(zip(result[1],result[2])) if result[0] else []
    else:raise ValueError("unknown pose solver")
    valid=[]
    for r,t in candidates:
        rr=np.asarray(r,np.float64).reshape(3,1)
        tt=np.asarray(t,np.float64).reshape(3,1)
        if method!="iterative":
            try:rr,tt=cv2.solvePnPRefineLM(obj,pixels,K,dist,rr,tt)
            except cv2.error:continue
        R,_=cv2.Rodrigues(rr)
        center=(-R.T@tt).ravel()
        if not np.isfinite(center).all() or center[2]<=0:continue
        projected,_=cv2.projectPoints(obj,rr,tt,K,dist)
        rmse=float(np.sqrt(np.mean(np.sum((projected.reshape(-1,2)-pixels)**2,axis=1))))
        if np.isfinite(rmse):valid.append((rmse,rr,tt,center))
    return min(valid,key=lambda x:x[0]) if valid else None

def evaluate():
    cam=json.loads((HERE/"camera_profile_estimated.json").read_text())
    K=np.asarray(cam["camera_matrix"],float);dist=np.asarray(cam["distortion"],float)
    rows=[]
    for p in sorted((HERE/"images").glob("*.JPG")):
        im=load_landscape(p)
        gray=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
        _,old_info,old_pose=detect_aruco_calibration_sheet(im,K,dist)
        original=old_info.reprojection_error_px
        row={"image":p.name,"baseline_rmse_px":original,"variants":{}}
        for scale in (1.0,0.5,0.35):
            for solver in ("iterative","epnp_refine","ippe_refine"):
                times=[];value=None;diff=None;count=0
                for i in range(3):
                    start=perf_counter()
                    obj,pixels,ids=detect_correspondences(gray,scale)
                    count=len(ids)
                    value=solve_planar(obj,pixels,K,dist,solver)
                    times.append((perf_counter()-start)*1000)
                if value is not None and old_pose is not None:
                    diff=float(np.linalg.norm(value[3]-old_pose["camera_center_mm"]))
                row["variants"][f"scale{scale}_{solver}"]={
                    "markers":count,
                    "rmse_px":round(value[0],5) if value else None,
                    "camera_center_drift_mm":round(diff,4) if diff is not None else None,
                    "median_ms":round(float(np.median(times)),2),
                    "pose_pass":bool(value and count>=3 and value[0]<=2.5),
                }
        print(p.name,"original",round(original,3),"scaled-IPPE",
              row["variants"]["scale0.5_ippe_refine"],flush=True)
        rows.append(row)
    output={"status":"RESEARCH_ONLY","note":"Same eight development photos, in-sample intrinsics; no independent calibration","images":rows}
    keys=list(rows[0]["variants"])
    output["summary"]={}
    for key in keys:
        entries=[r["variants"][key] for r in rows]
        output["summary"][key]={
            "pose_pass_count":sum(int(e["pose_pass"]) for e in entries),
            "marker_4_count":sum(int(e["markers"]==4) for e in entries),
            "median_ms_per_image":round(float(np.median([e["median_ms"] for e in entries])),2),
            "max_camera_center_drift_mm":max(e["camera_center_drift_mm"] for e in entries if e["camera_center_drift_mm"] is not None),
        }
    (HERE/"fast_pose_ablation.json").write_text(json.dumps(output,indent=2)+"\n")
    print("ABLATED",json.dumps(output["summary"],indent=2),flush=True)
    return output

if __name__=="__main__":evaluate()
