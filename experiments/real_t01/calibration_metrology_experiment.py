"""Historical candidate calibration benchmark, now using explicit K/D injection.

The selected reusable entrypoint is selected_pipeline.py. This file retains
the original per-trial report format without monkeypatching shared functions.
All experiments are manually annotated and same-session calibrated.
"""
from time import perf_counter
import csv
import json
import math

import cv2
import numpy as np

from backend.app.cv.aruco_detector import detect_aruco_calibration_sheet
from experiments.real_t01 import silhouette_fit as s
from experiments.real_t01 import paper_two_view as p
from experiments.real_t01.calibrate_dataset import load_landscape


def do_profile(profile_name):
    source=json.loads((s.HERE/"calibration_model_variants.json").read_text(encoding="utf-8"))
    item=source[profile_name]
    K=np.asarray(item["camera_matrix"],np.float64)
    D=np.asarray(item["dist_coeffs"],np.float64)
    gt={}
    with (s.HERE/"ground_truth.csv").open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            gt[row["item_id"]]=np.asarray([float(row[k]) for k in ("length_mm","width_mm","height_mm")])

    started=perf_counter()
    poses=[]
    for path in sorted((s.HERE/"images").glob("*.JPG")):
        _,info,pose=detect_aruco_calibration_sheet(load_landscape(path),K,D)
        poses.append((path.name,info.detected_markers_count,float(info.reprojection_error_px),
                      bool(info.camera_pose_valid)))

    metrics={}
    errors=[]
    for trial,names in s.TRIAL_PAIRS.items():
        tic=perf_counter()
        views=p.load_views(names,camera_intrinsics=(K,D))
        evidence=s.evidence_for_pair(trial,names,views,
            json.loads((s.HERE/"roi_annotations.json").read_text(encoding="utf-8")))
        records=[]
        for obj in gt:
            xy,length,width=p.center_guess(views[names[0]],obj)
            best=None
            for yaw in (0.,math.pi/4,math.pi/2,3*math.pi/4):
                for height in (35.,90.):
                    init=[xy[0],xy[1],max(25.,length*.75),max(25.,width*.75),height,yaw]
                    candidate,score=s.bbox_optimize(list(views.values()),obj,init)
                    if best is None or score<best[1]:
                        best=(candidate,score)
            observations=[
                (views[name]["pose"],views[name]["items"][obj]["bbox"],*evidence[name][obj])
                for name in names
            ]
            fit,_=s.refine(best[0],observations)
            predicted=np.r_[sorted(fit[2:4],reverse=True),fit[4]]
            records.append(np.abs(predicted-gt[obj]))
        xy_mae=float(np.mean([np.mean(v[:2]) for v in records]))
        h_mae=float(np.mean([v[2] for v in records]))
        metrics[trial]={"xy_mae_mm":xy_mae,"h_mae_mm":h_mae,
                        "elapsed_s":perf_counter()-tic}
        errors.extend(records)
        print(profile_name,trial,"xy",round(xy_mae,3),
              "h",round(h_mae,3),flush=True)
    result={
        "model":profile_name,
        "status":"EXPLORATORY_NOT_T01_GATE",
        "in_sample_pose_pass":sum(int(n>=3 and error<=2.5) for _,n,error,_ in poses),
        "poses":poses,
        "mean_xy_mm":float(np.mean([np.mean(v[:2]) for v in errors])),
        "mean_h_mm":float(np.mean([v[2] for v in errors])),
        "per_trial":metrics,
        "runtime_s":perf_counter()-started,
    }
    print("CALIB_V2",json.dumps({k:v for k,v in result.items() if k!="poses"}),flush=True)
    return result


def main():
    from argparse import ArgumentParser
    cli=ArgumentParser()
    cli.add_argument("--model",default="free_tangent",
                     choices=("free_tangent","baseline"))
    args=cli.parse_args()
    result={args.model:do_profile(args.model)}
    (s.HERE/"calibration_metrology_experiment.json").write_text(
        json.dumps(result,indent=2)+"\n",encoding="utf-8")


if __name__=="__main__":
    main()
