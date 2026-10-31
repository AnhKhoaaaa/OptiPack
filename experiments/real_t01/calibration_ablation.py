"""Study marker corner refinement with leave-one-view-out calibration.

Uses the same 8 user captures, but each test image is excluded from its
intrinsics fit. This is diagnostic; it is not a device manufacturer's
independent calibration or holdout of an entirely separate session.
"""
from pathlib import Path
import json, sys
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.app.cv.aruco_detector import marker_world_corners
from experiments.real_t01.calibrate_dataset import load_landscape

HERE=Path(__file__).resolve().parent
def observations(refinement):
    detector=cv2.aruco.DetectorParameters()
    detector.cornerRefinementMethod=refinement
    detector.cornerRefinementWinSize=5
    detect=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),detector)
    frames=[]
    for p in sorted((HERE/"images").glob("*.JPG")):
        im=load_landscape(p); gray=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
        corners,ids,_=detect.detectMarkers(gray)
        pix=[];obj=[]
        for corner,k in zip(corners,ids.ravel()):
            obj.extend(marker_world_corners(int(k)).astype(np.float32))
            pix.extend(corner.reshape(4,2))
        frames.append((p.name,np.asarray(obj,np.float32),np.asarray(pix,np.float32)))
    return frames

def fit(frames):
    h,w=3024,4032
    f=w*1.12
    K=np.array([[f,0,w/2],[0,f,h/2],[0,0,1]],float)
    dist=np.zeros(8)
    flags=(cv2.CALIB_USE_INTRINSIC_GUESS|cv2.CALIB_FIX_PRINCIPAL_POINT|
           cv2.CALIB_ZERO_TANGENT_DIST|cv2.CALIB_FIX_K3|
           cv2.CALIB_FIX_K4|cv2.CALIB_FIX_K5|cv2.CALIB_FIX_K6)
    rms,K,dist,rv,tv=cv2.calibrateCamera([v[1] for v in frames],
            [v[2] for v in frames],(w,h),K,dist,flags=flags)
    return float(rms),K,dist

def measure(f, K, dist):
    ok,r,t=cv2.solvePnP(f[1],f[2],K,dist,flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:return float("inf")
    pred,_=cv2.projectPoints(f[1],r,t,K,dist)
    return float(np.sqrt(np.mean(np.sum((pred.reshape(-1,2)-f[2])**2,axis=1))))

def main():
    results={}
    for name,method in [("none",cv2.aruco.CORNER_REFINE_NONE),
                        ("subpix",cv2.aruco.CORNER_REFINE_SUBPIX),
                        ("contour",cv2.aruco.CORNER_REFINE_CONTOUR)]:
        observations_set=observations(method)
        rms,K,dist=fit(observations_set)
        scores=[]
        for i,f in enumerate(observations_set):
            _,Ki,di=fit([x for j,x in enumerate(observations_set) if j!=i])
            scores.append({"image":f[0],"leave_one_out_reprojection_rmse_px":measure(f,Ki,di)})
        results[name]={"in_sample_RMS_px":rms,
                       "mean_leave_one_out_px":float(np.mean([x["leave_one_out_reprojection_rmse_px"] for x in scores])),
                       "max_leave_one_out_px":float(max(x["leave_one_out_reprojection_rmse_px"] for x in scores)),
                       "K":K.tolist(),"dist":dist.ravel().tolist(),"views":scores}
        print(name,"in_sample",round(rms,3),"LOO_mean",round(results[name]["mean_leave_one_out_px"],3),
              "LOO_max",round(results[name]["max_leave_one_out_px"],3),flush=True)
    (HERE/"calibration_ablation.json").write_text(json.dumps(results,indent=2)+"\n")
if __name__=="__main__":main()
