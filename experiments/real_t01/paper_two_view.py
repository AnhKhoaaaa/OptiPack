"""Real T01 pair-only benchmark for the CubeSLAM-inspired edge/cuboid fit.

Uses only a named top-down + oblique pair to infer each cuboid.
Camera intrinsics remain provisional (fitted on all 8 photos); each
object ROI is human supplied. This is NOT autonomous product code.
"""
from pathlib import Path
from time import perf_counter
import csv, json, math
import numpy as np
import cv2

from experiments.real_t01.exploratory_fit import optimize as optimize_bbox, raycast_xy
from experiments.real_t01.real_baseline import roi_from_annotation, mask_object
from experiments.real_t01.calibrate_dataset import load_landscape
from experiments.real_t01.paper_edge_experiment import cache_edges,refine
from backend.app.cv.aruco_detector import detect_aruco_calibration_sheet

HERE=Path(__file__).resolve().parent
TRIAL_PAIRS={
    "Trial01":("Trial01_topdown.JPG","Trial01_Oblique.JPG"),
    "Trial02":("Trial02_topdown.JPG","Trial02_Oblique.JPG"),
    "Trial03":("Trial03_topdown.JPG","Trial03_Oblique.JPG"),
}

def load_views(names):
    a=json.loads((HERE/"roi_annotations.json").read_text(encoding="utf-8"))
    profile=json.loads((HERE/"camera_profile_estimated.json").read_text())
    K=np.asarray(profile["camera_matrix"],np.float64)
    dist=np.asarray(profile["distortion"],np.float64)
    result={}
    for name in names:
        raw=cv2.imread(str(HERE/"images"/name))
        img=load_landscape(HERE/"images"/name)
        calibrated,info,pose=detect_aruco_calibration_sheet(img,K,dist)
        if pose is None:raise ValueError("No ArUco pose in "+name)
        items={}
        for label,bbox in a[name].items():
            roi=roi_from_annotation(label,(raw.shape[1],raw.shape[0]),bbox)
            corners,_=mask_object(raw,roi)
            if raw.shape[0]>raw.shape[1]:
                corners=np.stack([raw.shape[0]-1-corners[:,1],corners[:,0]],axis=1)
            obs=np.array([corners[:,0].min(),corners[:,1].min(),
                          corners[:,0].max(),corners[:,1].max()],float)
            items[label]={"corners":corners,"bbox":obs}
        result[name]={"pose":pose,"items":items,"markers":info.detected_markers_count,
                      "reprojection_rmse_px":info.reprojection_error_px}
    return result

def center_guess(view,item):
    pose=view["pose"]; corner=view["items"][item]["corners"];bb=view["items"][item]["bbox"]
    mid=np.array([[(bb[0]+bb[2])/2,(bb[1]+bb[3])/2]],float)
    norm=cv2.undistortPoints(mid.reshape(-1,1,2),pose["camera_matrix"],pose["dist_coeffs"]).reshape(2)
    direction=pose["R"].T@np.r_[norm,1.0]
    center=pose["camera_center_mm"]; ray=center-center[2]*direction/direction[2]
    L,W=raycast_xy(corner,pose,0)
    return ray,L,W

def run():
    gt={}
    with (HERE/"ground_truth.csv").open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            gt[row["item_id"]]=np.array([float(row[v]) for v in ("length_mm","width_mm","height_mm")])
    res={"status":"EXPLORATORY_NOT_AUTONOMOUS_T01","source_paper":"CubeSLAM Yang & Scherer 2019",
         "intrinsics":"estimated from same 8 images, not independent",
         "localization":"manual ROI + GrabCut",
         "height":"two-view cuboid fit (no ground truth as optimizer input)",
         "pair_results":{}}
    total_start=perf_counter()
    for trial,names in TRIAL_PAIRS.items():
        start=perf_counter()
        views=load_views(names)
        maps=cache_edges(names)
        data=list(views.values())
        rows=[]
        for item in gt:
            center,l,w=center_guess(views[names[0]],item)
            best=None
            for yaw in (0.,math.pi/4,math.pi/2,3*math.pi/4):
                for height in (35.,90.):
                    init=[center[0],center[1],max(25,l*.75),max(25,w*.75),height,yaw]
                    fit,loss=optimize_bbox(data,item,init)
                    if best is None or loss<best[1]:best=(fit,loss)
            edge_views=[(name,v["pose"],v["items"][item]["bbox"]) for name,v in views.items()]
            fitted,loss=refine(best[0],edge_views,maps)
            pred=np.array([*sorted(fitted[2:4],reverse=True),fitted[4]])
            err=np.abs(pred-gt[item])
            rows.append({"item_id":item,"predicted_LWH_mm":pred.tolist(),
                         "ground_truth_LWH_mm":gt[item].tolist(),
                         "absolute_errors_mm":err.tolist(),
                         "edge_cost":float(loss)})
        xy=float(np.mean([(r["absolute_errors_mm"][0]+r["absolute_errors_mm"][1])/2 for r in rows]))
        hm=float(np.mean([r["absolute_errors_mm"][2] for r in rows]))
        elapsed=(perf_counter()-start)*1000
        res["pair_results"][trial]={"images":list(names),"xy_mae_mm":xy,"h_mae_mm":hm,
            "time_ms_five_objects":elapsed,"items":rows,
            "marker_reprojection_rmse_px":[views[n]["reprojection_rmse_px"] for n in names]}
        print(trial,"XY_MAE_MM",round(xy,2),"H_MAE_MM",round(hm,2),"TOTAL_MS",round(elapsed,1),flush=True)
        (HERE/"paper_two_view_results.json").write_text(json.dumps(res,indent=2)+"\n")
    res["total_runtime_ms"]=(perf_counter()-total_start)*1000
    res["all_pairs_xy_mae_mm"]=float(np.mean([a["xy_mae_mm"] for a in res["pair_results"].values()]))
    res["all_pairs_h_mae_mm"]=float(np.mean([a["h_mae_mm"] for a in res["pair_results"].values()]))
    (HERE/"paper_two_view_results.json").write_text(json.dumps(res,indent=2)+"\n")
    print("OVERALL",round(res["all_pairs_xy_mae_mm"],2),round(res["all_pairs_h_mae_mm"],2),flush=True)
if __name__=="__main__":run()
