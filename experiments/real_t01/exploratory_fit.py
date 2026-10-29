"""EXPERIMENTAL multi-view 3D cuboid fit from manually initialized GrabCut masks.

No ground-truth L/W/H is used in prediction. Not a production path.
Fits projected 3D cuboid silhouettes to 2D bounding rectangles in four
different views from Trial 02; assumes rectangular upright box on z=0.
"""
from pathlib import Path
import json, csv, math
import numpy as np
import cv2
from experiments.real_t01.calibrate_dataset import load_landscape
from experiments.real_t01.real_baseline import mask_object,roi_from_annotation,raycast_xy
from backend.app.cv.aruco_detector import detect_aruco_calibration_sheet

HERE=Path(__file__).resolve().parent
TRIAL_FILES=["Trial02_topdown.JPG","Trial02_Oblique.JPG","Trial02_leftside.JPG","Trial02_rightside.JPG"]
def observations():
    roi=json.loads((HERE/"roi_annotations.json").read_text())
    profile=json.loads((HERE/"camera_profile_estimated.json").read_text())
    K=np.asarray(profile["camera_matrix"],np.float64)
    dist=np.asarray(profile["distortion"],np.float64)
    views={}
    for name in TRIAL_FILES:
        raw=cv2.imread(str(HERE/"images"/name))
        img=load_landscape(HERE/"images"/name)
        status,info,pose=detect_aruco_calibration_sheet(img,K,dist)
        if pose is None:raise RuntimeError(name+" marker pose fails")
        items={}
        for obj,bounds in roi[name].items():
            bb=roi_from_annotation(obj,(raw.shape[1],raw.shape[0]),bounds)
            corners,_=mask_object(raw,bb)
            if raw.shape[0]>raw.shape[1]:
                corners=np.stack([raw.shape[0]-1-corners[:,1],corners[:,0]],axis=1)
            observed_bbox=np.array([corners[:,0].min(),corners[:,1].min(),
                                    corners[:,0].max(),corners[:,1].max()],dtype=float)
            items[obj]={"corners":corners,"bbox":observed_bbox}
        views[name]={"pose":pose,"items":items}
    return views

def project_bbox(p,pose):
    cx,cy,L,W,H,ang=p
    a=np.array([L/2,W/2],np.float64)
    corners=np.array([[-1,-1],[1,-1],[1,1],[-1,1]],np.float64)*a
    c,s=math.cos(ang),math.sin(ang)
    Rxy=np.array([[c,-s],[s,c]])
    xy=corners@Rxy.T + np.array([cx,cy])
    base=np.c_[xy,np.zeros(4)]
    top=np.c_[xy,np.full(4,H)]
    pts=np.vstack([base,top])
    proj,_=cv2.projectPoints(pts,pose["rvec"],pose["tvec"],
                            pose["camera_matrix"],pose["dist_coeffs"])
    proj=proj.reshape(-1,2)
    return np.array([proj[:,0].min(),proj[:,1].min(),proj[:,0].max(),proj[:,1].max()])

def optimize(view_list,item_id,initial):
    os=[(v["pose"],v["items"][item_id]["bbox"]) for v in view_list]
    def residual(p):
        return np.concatenate([project_bbox(p,pose)-obs for pose,obs in os])
    def cost(p):
        r=residual(p)
        return float(np.dot(r,r))
    p=np.asarray(initial,np.float64)
    steps=np.array([.6,.6,.6,.6,.6,.007])
    lam=1.
    bestcost=cost(p)
    for it in range(100):
        r=residual(p)
        J=np.column_stack([(residual(p+np.eye(6)[j]*steps[j])-r)/steps[j] for j in range(6)])
        grad=J.T@r
        hess=J.T@J
        try:
            delta=-np.linalg.solve(hess+np.eye(6)*lam,grad)
        except np.linalg.LinAlgError:break
        if np.linalg.norm(delta)<1e-5:break
        candidate=p+delta
        candidate[2:5]=np.clip(candidate[2:5],10,400)
        candidate[5]=candidate[5]%(2*np.pi)
        c=cost(candidate)
        if c<bestcost:
            p=candidate
            if abs(c-bestcost)<1e-4:break
            bestcost=c;lam=max(1e-4,lam*.6)
        else:
            lam=min(1e6,lam*2.5)
    return p,bestcost

def run():
    data=observations()
    top=data[TRIAL_FILES[0]]
    results=[]
    gt={}
    with (HERE/"ground_truth.csv").open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            gt[row["item_id"]]=np.array([float(row[v]) for v in ("length_mm","width_mm","height_mm")])
    for item in gt:
        corners=top["items"][item]["corners"]
        bb=top["items"][item]["bbox"]
        pose=top["pose"]
        centerpx=np.array([[(bb[0]+bb[2])/2,(bb[1]+bb[3])/2]],np.float64)
        norm=cv2.undistortPoints(centerpx.reshape(-1,1,2),pose["camera_matrix"],pose["dist_coeffs"]).reshape(2)
        direction=pose["R"].T@np.r_[norm,1.]
        camera=pose["camera_center_mm"]
        center=camera-camera[2]*direction/direction[2]
        l,w=raycast_xy(corners,pose,0)
        fit_best=None
        for ang in (0.,math.pi/4,math.pi/2,3*math.pi/4):
            for seedh in (35.,90.):
                init=[center[0],center[1],max(25,l*.75),max(25,w*.75),seedh,ang]
                estimate,loss=optimize(list(data.values()),item,init)
                if fit_best is None or loss<fit_best[1]:
                    fit_best=estimate,loss
        est,loss=fit_best
        ordered=sorted((est[2],est[3]),reverse=True)
        errors=np.abs(np.r_[ordered,est[4]]-gt[item])
        row={"item_id":item,"fitted_LWH_mm":list(map(float,[*ordered,est[4]])),
             "ground_truth_LWH_mm":gt[item].tolist(),"abs_errors_mm":errors.tolist(),
             "pixel_bbox_rms_error_px":math.sqrt(loss/(len(data)*4)),
             "method":"manual ROI seeded GrabCut + multi-view cuboid bbox fit, exploratory"}
        results.append(row)
        print(item,"LWH",np.round([*ordered,est[4]],1),"GT",gt[item],"ERR",np.round(errors,1),"pixel residual",round(row["pixel_bbox_rms_error_px"],1),flush=True)
    dataout={"status":"EXPERIMENTAL_NOT_GATE_EVIDENCE","views":TRIAL_FILES,
             "metrics_exploratory_only":results,
             "provenance":"GT excluded from optimizer; ROI human seeded; camera K estimated in-sample"}
    (HERE/"experimental_3d_results.json").write_text(json.dumps(dataout,indent=2)+"\n")
    return dataout
if __name__=="__main__":run()
