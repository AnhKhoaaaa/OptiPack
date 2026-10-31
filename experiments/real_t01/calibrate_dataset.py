"""Estimate a provisional intrinsics profile from 8 views of the known board.

This is in-sample capture-based self-calibration, not independently measured
camera intrinsics and NOT sufficient evidence for a real-world T01 GO.
"""
from pathlib import Path
import cv2
import json
import numpy as np
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.app.cv.aruco_detector import marker_world_corners
HERE=Path(__file__).resolve().parent
def load_landscape(path):
    im=cv2.imread(str(path))
    if im is None: raise FileNotFoundError(path)
    if im.shape[0]>im.shape[1]:
        im=cv2.rotate(im,cv2.ROTATE_90_CLOCKWISE)
    return im
def collect():
    params=cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX
    params.cornerRefinementWinSize=5
    detector=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),params)
    frames=[]
    for p in sorted((HERE/"images").glob("*.JPG")):
        image=load_landscape(p)
        corners,ids,_=detector.detectMarkers(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY))
        objects=[];pixels=[]
        for c,mi in zip(corners, ids.ravel() if ids is not None else []):
            if int(mi) in (0,1,2,3):
                objects.extend(marker_world_corners(int(mi)).astype(np.float32))
                pixels.extend(c.reshape(-1,2))
        if len(objects)<8:continue
        frames.append((p.name,np.asarray(objects,np.float32),np.asarray(pixels,np.float32),image.shape[:2]))
    return frames
def fit():
    frames=collect()
    if len(frames)<3:raise ValueError("insufficient board perspectives")
    sizes={tuple(v[3]) for v in frames}
    if len(sizes)!=1:raise ValueError(f"inconsistent normalized image sizes: {sizes}")
    height,width=next(iter(sizes))
    # Use a conservative intrinsic model (fixed principal point, modest distortion).
    f=float(width)*1.12
    K=np.array([[f,0,width/2],[0,f,height/2],[0,0,1]],np.float64)
    dist=np.zeros((8,1),np.float64)
    flags=(cv2.CALIB_USE_INTRINSIC_GUESS|cv2.CALIB_FIX_PRINCIPAL_POINT|
           cv2.CALIB_ZERO_TANGENT_DIST|cv2.CALIB_FIX_K3|
           cv2.CALIB_FIX_K4|cv2.CALIB_FIX_K5|cv2.CALIB_FIX_K6)
    rms,K,dist,rv,tv=cv2.calibrateCamera([v[1] for v in frames],[v[2] for v in frames],(width,height),K,dist,flags=flags)
    per_view={}
    for (name,obj,pts,_),r,t in zip(frames,rv,tv):
        projected,_=cv2.projectPoints(obj,r,t,K,dist)
        rmse=float(np.sqrt(np.mean(np.sum((projected.reshape(-1,2)-pts)**2,axis=1))))
        per_view[name]=rmse
    result={"source":"self-calibration from same 8 T01 captures (NOT independently calibrated)",
            "status":"estimated_not_verified","landscape_orientation":"portrait files rotated 90deg clockwise",
            "image_size_px":[width,height],"camera_matrix":K.tolist(),
            "distortion":dist.ravel().tolist(),"training_frames":len(frames),
            "in_sample_rms_px":float(rms),"per_view_reprojection_rmse_px":per_view,
            "limitations":"Planar board; same captures used in fit and scoring; geometry/marker printed 100% assumed; camera zoom/intrinsics consistency not independently verified."}
    (HERE/"camera_profile_estimated.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":fit()
