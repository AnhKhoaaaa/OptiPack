"""Compare constrained planar camera models using leave-one-image-out reprojection.

Zhang (2000) planar calibration via OpenCV calibrateCamera/solvePnP.
All images belong to one development session. Even the LOO result is
optimistically biased when a model is selected among these six candidates.
Never use this result to claim independent T01 camera calibration.
"""
from pathlib import Path
import json, math, time
import cv2
import numpy as np
from experiments.real_t01.calibration_ablation import observations, measure
from experiments.real_t01.calibrate_dataset import HERE

W,H=4032,3024
BASE=(cv2.CALIB_USE_INTRINSIC_GUESS|cv2.CALIB_FIX_PRINCIPAL_POINT|
      cv2.CALIB_ZERO_TANGENT_DIST|cv2.CALIB_FIX_K3|
      cv2.CALIB_FIX_K4|cv2.CALIB_FIX_K5|cv2.CALIB_FIX_K6)
CONFIGS={
 "baseline":BASE,
 "fix_aspect_ratio":BASE|cv2.CALIB_FIX_ASPECT_RATIO,
 "fix_k2":BASE|cv2.CALIB_FIX_K2,
 "no_radial_distortion":BASE|cv2.CALIB_FIX_K1|cv2.CALIB_FIX_K2,
 "free_principal_point":BASE & ~cv2.CALIB_FIX_PRINCIPAL_POINT,
 "free_tangent":BASE & ~cv2.CALIB_ZERO_TANGENT_DIST,
}
def fit(frames,flags):
    f=W*1.12
    K=np.array([[f,0,W/2],[0,f,H/2],[0,0,1]],np.float64)
    d=np.zeros((8,1),np.float64)
    rms,K,d,_,_=cv2.calibrateCamera(
        [v[1] for v in frames],[v[2] for v in frames],
        (W,H),K,d,flags=flags)
    return rms,K,d

def run():
    frames=observations(cv2.aruco.CORNER_REFINE_SUBPIX)
    rows={}
    for name,flags in CONFIGS.items():
        t=time.perf_counter()
        fit_rms,K,dist=fit(frames,flags)
        trial=[]
        for i,frame in enumerate(frames):
            try:
                _,Ki,di=fit([f for j,f in enumerate(frames) if j!=i],flags)
                err=measure(frame,Ki,di)
                trial.append({"image":frame[0],"held_out_pose_rmse_px":float(err)})
            except cv2.error as ex:
                trial.append({"image":frame[0],"held_out_pose_rmse_px":float('inf'),"error":str(ex)[:200]})
        values=[r["held_out_pose_rmse_px"] for r in trial]
        count=int(np.sum(np.array(values)<=2.5))
        rows[name]={"status":"NOT_INDEPENDENT_CALIBRATION","in_sample_rms_px":fit_rms,
                    "loo_mean_px":float(np.mean(values)),"loo_max_px":float(np.max(values)),
                    "loo_pass_count":count,"frames":trial,
                    "camera_matrix":K.tolist(),"dist_coeffs":dist.ravel().tolist(),
                    "elapsed_s":round(time.perf_counter()-t,2)}
        print(name,"in",round(fit_rms,3),"loo_mean",round(rows[name]["loo_mean_px"],3),
              "loo_max",round(rows[name]["loo_max_px"],3),"pass",count,"s",rows[name]["elapsed_s"],flush=True)
    return rows

if __name__=="__main__":
    output=run()
    (HERE/"calibration_model_variants.json").write_text(json.dumps(output,indent=2,allow_nan=True)+"\n")
