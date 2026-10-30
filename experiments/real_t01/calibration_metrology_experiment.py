"""Evaluate an optional camera intrinsics candidate through unchanged V2 fitting.

Candidate K is selected on the same development session, not independent
calibration. Monkeypatch ONLY within this experiment process; never rewrite
camera_profile_estimated.json or production metrology code.
"""
from time import perf_counter
import math,json,csv,sys
import numpy as np
import cv2
from experiments.real_t01 import silhouette_fit as s
from experiments.real_t01 import paper_two_view as p
from experiments.real_t01.calibrate_dataset import load_landscape
from backend.app.cv.aruco_detector import detect_aruco_calibration_sheet as detect

def do_profile(profile_name):
    candidates=json.loads((s.HERE/"calibration_model_variants.json").read_text())
    cp=candidates[profile_name]
    K=np.array(cp["camera_matrix"],np.float64)
    D=np.array(cp["dist_coeffs"],np.float64)
    old_fn=p.detect_aruco_calibration_sheet
    # Current code passes K,D but this route intentionally uses candidate K,D.
    p.detect_aruco_calibration_sheet=lambda im,km,dc: detect(im,K,D)
    annot=json.loads((s.HERE/"roi_annotations.json").read_text(encoding="utf-8"))
    gt={}
    with (s.HERE/"ground_truth.csv").open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            gt[row["item_id"]]=np.array([float(row[x]) for x in ("length_mm","width_mm","height_mm")])
    t0=perf_counter();rows=[];metrics={}
    allposes=[]
    for name in sorted((s.HERE/"images").glob("*.JPG")):
        im=load_landscape(name)
        ok,info,pose=detect(im,K,D)
        allposes.append((name.name,info.detected_markers_count,float(info.reprojection_error_px),bool(info.camera_pose_valid)))
    try:
        for trial,names in s.TRIAL_PAIRS.items():
            t=perf_counter()
            views=p.load_views(names)
            ev=s.evidence_for_pair(trial,names,views,annot)
            records=[]
            for item in gt:
                xy,l,w=p.center_guess(views[names[0]],item)
                best=None
                for yaw in (0,math.pi/4,math.pi/2,3*math.pi/4):
                    for H0 in (35.,90.):
                        ini=[xy[0],xy[1],max(25,l*.75),max(25,w*.75),H0,yaw]
                        q,z=s.bbox_optimize(list(views.values()),item,ini)
                        if best is None or z<best[1]:best=(q,z)
                obs=[(views[name]["pose"],views[name]["items"][item]["bbox"],*ev[name][item]) for name in names]
                fit,_=s.refine(best[0],obs)
                pred=np.r_[sorted(fit[2:4],reverse=True),fit[4]]
                err=np.abs(pred-gt[item])
                records.append((item,err,pred))
            mae_xy=float(np.mean([np.mean(v[1][:2]) for v in records]))
            mae_h=float(np.mean([v[1][2] for v in records]))
            metrics[trial]={"xy_mae_mm":mae_xy,"h_mae_mm":mae_h,"elapsed_s":time_now()-t}
            rows+=records
            print(profile_name,trial,"xy",round(mae_xy,3),"h",round(mae_h,3),flush=True)
    finally:
        p.detect_aruco_calibration_sheet=old_fn
    result={"model":profile_name,"in_sample_pose_pass":sum(int(n>=3 and v<=2.5) for _,n,v,_ in allposes),
            "poses":allposes,"mean_xy_mm":float(np.mean([np.mean(v[1][:2]) for v in rows])),
            "mean_h_mm":float(np.mean([v[1][2] for v in rows])),
            "per_trial":metrics,"runtime_s":time_now()-t0}
    print("CALIB_V2",json.dumps({k:v for k,v in result.items() if k!="poses"}),flush=True)
    return result

def time_now():return perf_counter()

if __name__=="__main__":
    names=sys.argv[1:] or ["free_tangent"]
    outputs={name:do_profile(name) for name in names}
    (s.HERE/"calibration_metrology_experiment.json").write_text(json.dumps(outputs,indent=2)+"\n")
