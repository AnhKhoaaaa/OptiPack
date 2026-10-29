"""Conservative real-photo Phase 0 evaluation.

Pipeline: ArUco -> provisional pose -> human-initialized ROI + GrabCut ->
top-view XY planar raycast -> document-specified aspect prior for height.
This is a REAL pixel test but NOT a fully autonomous dual-view 3D metrology
implementation, and no result here is allowed to certify T01 GO.
"""
from pathlib import Path
from time import perf_counter
import csv, json, sys
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.app.cv.aruco_detector import detect_aruco_calibration_sheet
from experiments.real_t01.calibrate_dataset import load_landscape,collect

HERE=Path(__file__).resolve().parent
BOARD_PASSES_MAX_REPROJ=2.5

def roi_from_annotation(item,image_size,annotations):
    x0,y0,x1,y1=annotations
    w,h=image_size
    return tuple(int(v) for v in
          (max(0,x0*w/720),max(0,y0*h/460),min(w,x1*w/720),min(h,y1*h/460)))

def mask_object(image, roi):
    """GrabCut seeded from a *manual* coarse ROI, never using dimension GT."""
    x0,y0,x1,y1=roi
    if x1<=x0 or y1<=y0:raise ValueError("Invalid object crop ROI")
    patch=image[y0:y1,x0:x1]
    ph,pw=patch.shape[:2]
    shrink=min(1.0,700.0/max(ph,pw))
    small=cv2.resize(patch,(max(50,int(pw*shrink)),max(50,int(ph*shrink))),
                     interpolation=cv2.INTER_AREA)
    h,w=small.shape[:2]
    m=np.full((h,w),cv2.GC_PR_BGD,np.uint8)
    by,bx=max(2,int(h*.03)),max(2,int(w*.03))
    m[:by,:]=cv2.GC_BGD;m[-by:,:]=cv2.GC_BGD
    m[:,:bx]=cv2.GC_BGD;m[:,-bx:]=cv2.GC_BGD
    # Broad probable foreground and confident central seed.
    m[int(.12*h):int(.88*h),int(.12*w):int(.88*w)]=cv2.GC_PR_FGD
    m[int(.36*h):int(.64*h),int(.36*w):int(.64*w)]=cv2.GC_FGD
    bg=np.zeros((1,65),np.float64);fg=np.zeros((1,65),np.float64)
    cv2.grabCut(small,m,None,bg,fg,2,cv2.GC_INIT_WITH_MASK)
    binmask=np.where((m==cv2.GC_FGD)|(m==cv2.GC_PR_FGD),255,0).astype(np.uint8)
    cnts,_=cv2.findContours(binmask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:raise ValueError("GrabCut extracted no foreground")
    biggest=max(cnts,key=cv2.contourArea)
    if cv2.contourArea(biggest)<.015*h*w:raise ValueError("Foreground too small")
    rect=cv2.minAreaRect(biggest)
    corners=cv2.boxPoints(rect).astype(np.float64)
    corners[:,0]=corners[:,0]/shrink+x0
    corners[:,1]=corners[:,1]/shrink+y0
    return corners, float(cv2.contourArea(biggest)/(h*w))

def raycast_xy(corners,pose,z):
    K=pose["camera_matrix"];dist=pose["dist_coeffs"]
    norm=cv2.undistortPoints(corners.reshape(-1,1,2),K,dist).reshape(-1,2)
    directions=pose["R"].T@np.c_[norm,np.ones(len(norm))].T
    c=pose["camera_center_mm"]
    if np.any(np.abs(directions[2])<1e-8):raise ValueError("Parallel ray")
    lamb=(z-c[2])/directions[2]
    xy=(c[:,None]+directions*lamb).T[:,:2]
    spans=np.linalg.norm(np.roll(xy,-1,axis=0)-xy,axis=1)
    return float(max((spans[0]+spans[2])/2,(spans[1]+spans[3])/2)),float(min((spans[0]+spans[2])/2,(spans[1]+spans[3])/2))

def baseline_xy_and_fallback_height(corners,pose):
    l0,w0=raycast_xy(corners,pose,0.0)
    prior_h=.4*w0
    l,w=raycast_xy(corners,pose,prior_h)
    return {"length_mm":l,"width_mm":w,"height_prior_mm":.4*w,
            "uncorrected_length_mm":l0,"uncorrected_width_mm":w0,
            "height_method":"category_aspect_prior_needs_user_review",
            "requires_user_review":True}

def evaluate():
    gt={}
    with (HERE/"ground_truth.csv").open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            gt[row["item_id"]]={d:float(row[d]) for d in ("length_mm","width_mm","height_mm")}
    roi=json.loads((HERE/"roi_annotations.json").read_text(encoding="utf-8"))
    profile=json.loads((HERE/"camera_profile_estimated.json").read_text())
    K=np.asarray(profile["camera_matrix"],np.float64)
    dist=np.asarray(profile["distortion"],np.float64)
    view_rows=[];object_rows=[]
    trial_data={}
    for name in sorted(x for x in roi if x.endswith(".JPG")):
        img=load_landscape(HERE/"images"/name)
        # Pixel ROIs were recorded in the originals; normalized landscape changes orientation.
        raw=cv2.imread(str(HERE/"images"/name))
        rotate=raw.shape[0]>raw.shape[1]
        t0=perf_counter()
        okay,info,pose=detect_aruco_calibration_sheet(img,K,dist)
        pose_time=(perf_counter()-t0)*1000
        view_rows.append({"image":name,"detected_marker_count":info.detected_markers_count,
                         "pose_accepted_by_detector":okay,"reprojection_rmse_px":info.reprojection_error_px,
                         "pose_time_ms":pose_time,"pose_valid":info.camera_pose_valid,
                         "warnings":info.warnings})
        if pose is None or not info.camera_pose_valid:continue
        if "topdown" not in name.lower():continue
        trial=name.split("_")[0]
        trial_data[trial]=[]
        for item,box in roi[name].items():
            x0,y0,x1,y1=roi_from_annotation(item,(raw.shape[1],raw.shape[0]),box)
            # Use the raw image orientation for ROI/segmentation.
            t=perf_counter()
            corners,mask_fraction=mask_object(raw,(x0,y0,x1,y1))
            if rotate:
                # Raw portrait H>W => cv2.ROTATE_90_CLOCKWISE to match pose.
                rw=raw.shape[0]
                corners=np.stack([rw-1-corners[:,1],corners[:,0]],axis=1)
            pred=baseline_xy_and_fallback_height(corners,pose)
            elapsed=(perf_counter()-t)*1000
            ground=gt[item]
            record={"trial":trial,"image":name,"item_id":item,"mask_coverage_ratio":mask_fraction,
                    **pred,"segmentation_and_xy_ms":elapsed,
                    "ground_truth_mm":ground,
                    "absolute_error_length_mm":abs(pred["length_mm"]-ground["length_mm"]),
                    "absolute_error_width_mm":abs(pred["width_mm"]-ground["width_mm"])}
            object_rows.append(record)
            trial_data[trial].append(record)
    observed=[v for v in object_rows if np.isfinite(v["absolute_error_length_mm"])]
    mae_xy=float(np.mean([(v["absolute_error_length_mm"]+v["absolute_error_width_mm"])/2 for v in observed])) if observed else None
    reproj_valid=[v for v in view_rows if v["pose_valid"]]
    pose_threshold_hits=sum(v["detected_marker_count"]>=3 and v["reprojection_rmse_px"]<=2.5 for v in reproj_valid)
    result={"dataset":"real","ground_truth_units":"mm (user input interpreted from cm)",
            "intrinsics_source":"self-calibrated from SAME image set; independent calibration unavailable",
            "object_localization":"manual ROI labels + GrabCut; NOT fully automated",
            "XY_measurement":"experimental Z=prior H raycast of top-view silhouette (not full box corner measurement)",
            "height_measurement":"manual confirmation required; no valid automated H estimate",
            "real_world_t01_gate":"NOT_PASSED",
            "reason":"No independent intrinsics/fully automatic multi-object dimension estimator or validated two-view H; in-sample calibration and manual ROI not a T01 end-to-end pass.",
            "images_analyzed":len(view_rows),"top_views_with_xy":len(trial_data),
            "marker_detection_rate":sum(v["detected_marker_count"]==4 for v in view_rows)/len(view_rows),
            "pose_quality_threshold_rate":pose_threshold_hits/len(view_rows),
            "observed_xy_mae_mm":mae_xy,
            "height_mae_mm":None,
            "view_diagnostics":view_rows,"object_baseline_diagnostics":object_rows}
    (HERE/"real_results.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in ("view_diagnostics","object_baseline_diagnostics")},indent=2,ensure_ascii=False))
    print("METROLOGY_RESULT_COUNT",len(object_rows))
    for v in object_rows:
        print(v["trial"],v["item_id"],"XY",round(v["length_mm"],1),round(v["width_mm"],1),"error",round(v["absolute_error_length_mm"],1),round(v["absolute_error_width_mm"],1))
    return result

if __name__=="__main__":evaluate()
