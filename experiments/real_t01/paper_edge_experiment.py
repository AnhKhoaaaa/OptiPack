"""CubeSLAM-inspired diagnostic: project cuboid edges and score against Canny edges.

This is an independent Python/OpenCV adaptation of the geometric idea from
Yang & Scherer, CubeSLAM (TRO 2019), NOT their C++/ROS source code.
NOT a paper reproduction or production-ready T01 solution.
"""
from pathlib import Path
import csv
import json
import math
import time
import numpy as np
import cv2

from experiments.real_t01.exploratory_fit import (
    observations, optimize as bbox_optimize, raycast_xy, project_bbox, HERE, TRIAL_FILES
)
from experiments.real_t01.calibrate_dataset import load_landscape

SCALE=.28
BOUND_WEIGHT=0.85
EDGE_WEIGHT=0.75

def model_vertices(p):
    cx,cy,L,W,H,angle=p
    xy=np.array([[-L/2,-W/2],[L/2,-W/2],[L/2,W/2],[-L/2,W/2]],dtype=float)
    c,s=math.cos(angle),math.sin(angle)
    xy=xy@np.array([[c,s],[-s,c]])+np.array([cx,cy])
    return np.vstack((np.c_[xy,np.zeros(4)],np.c_[xy,np.full(4,H)]))
def visible_edge_pairs(p,cam):
    pts=model_vertices(p)
    normal_cache=[]
    face_mid=[]
    for j in range(4):
        k=(j+1)%4
        v=pts[k]-pts[j]
        normal_cache.append(np.array([v[1],-v[0],0.]))
        face_mid.append((pts[j]+pts[k]+pts[4+j]+pts[4+k])/4)
    visible=[float(np.dot(cam-m,n))>0 for n,m in zip(normal_cache,face_mid)]
    edges=[]
    for j in range(4):
        k=(j+1)%4
        edges.append((4+j,4+k,1.0)) # top rectangle, reliable even if some occlusion
        if visible[j]:
            edges.append((j,k,.85))
        if visible[j] or visible[j-1]:
            edges.append((j,4+j,.95))
    return edges

def cache_edges(names):
    outputs={}
    for name in names:
        im=load_landscape(HERE/"images"/name)
        h,w=im.shape[:2]
        small=cv2.resize(im,(int(w*SCALE),int(h*SCALE)),interpolation=cv2.INTER_AREA)
        gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
        gray=cv2.GaussianBlur(gray,(5,5),1.2)
        ed=cv2.Canny(gray,40,115,L2gradient=True)
        # Gradients within a small manually designated ROI, not full clutter.
        non=255-ed
        dist=cv2.distanceTransform(non,cv2.DIST_L2,3)
        outputs[name]=np.minimum(dist,35.).astype(np.float32)
    return outputs

def interpolate(dist, pts):
    xy=np.asarray(pts,np.float32)
    mx=xy[:,0].reshape(1,-1)
    my=xy[:,1].reshape(1,-1)
    return cv2.remap(dist,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=35).ravel().astype(float)

def residual(p,items,edge_maps):
    verts=model_vertices(p)
    ret=[]
    for name,pose,observed_bbox in items:
        proj,_=cv2.projectPoints(verts,pose["rvec"],pose["tvec"],pose["camera_matrix"],pose["dist_coeffs"])
        proj=proj.reshape(-1,2)
        bbox=np.array([proj[:,0].min(),proj[:,1].min(),proj[:,0].max(),proj[:,1].max()])
        ret.extend(((bbox-observed_bbox)*SCALE*BOUND_WEIGHT).tolist())
        scored=[]
        edges=visible_edge_pairs(p,pose["camera_center_mm"])
        for a,b,weight in edges:
            samples=np.linspace(.12,.88,6)[:,None]*proj[b]+np.linspace(.88,.12,6)[:,None]*proj[a]
            d=interpolate(edge_maps[name],samples*SCALE)
            scored.extend((d*weight*EDGE_WEIGHT).tolist())
        # Fixed number of edges across optimization.
        if len(scored)<72: scored.extend([0.]*(72-len(scored)))
        else:scored=scored[:72]
        ret.extend(scored)
    return np.asarray(ret,float)

def refine(initial,items,edges):
    p=np.array(initial,dtype=float)
    step=np.array([.5,.5,.5,.5,.5,.005])
    d=1.
    r=residual(p,items,edges);loss=float(r@r)
    for i in range(65):
        # Finite difference Jacobian (observation/camera fixed).
        J=np.column_stack([(residual(p+np.eye(6)[j]*step[j],items,edges)-r)/step[j] for j in range(6)])
        try: delta=np.linalg.solve(J.T@J+np.eye(6)*d,-J.T@r)
        except np.linalg.LinAlgError:break
        cand=p+delta
        cand[2:5]=np.clip(cand[2:5],15,300)
        cand[5]=cand[5]%(2*np.pi)
        rr=residual(cand,items,edges);val=float(rr@rr)
        if val<loss:
            improvement=loss-val
            p,r,loss=cand,rr,val
            d=max(1e-3,d*.6)
            if improvement<1e-5:break
        else:d=min(1e5,d*2.0)
        if np.linalg.norm(delta)<1e-4:break
    return p,loss

def run():
    start=time.perf_counter()
    data=observations()
    edge_maps=cache_edges(TRIAL_FILES)
    gt={}
    with (HERE/"ground_truth.csv").open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            gt[row["item_id"]]=np.array([float(row[c]) for c in ("length_mm","width_mm","height_mm")])
    results=[]
    top=data[TRIAL_FILES[0]]
    for obj in gt:
        pose=top["pose"]; corners=top["items"][obj]["corners"]
        bb=top["items"][obj]["bbox"]
        middle=np.array([[(bb[0]+bb[2])/2,(bb[1]+bb[3])/2]])
        norm=cv2.undistortPoints(middle.reshape(-1,1,2),pose["camera_matrix"],pose["dist_coeffs"]).reshape(2)
        vec=pose["R"].T@np.r_[norm,1.0];cam=pose["camera_center_mm"]
        center=cam-cam[2]*vec/vec[2]
        L,W=raycast_xy(corners,pose,0)
        per_view=[(name,v["pose"],v["items"][obj]["bbox"]) for name,v in data.items()]
        best=None
        for ang in (0,np.pi/4,np.pi/2,3*np.pi/4):
            for h in (35.,90.):
                init=[center[0],center[1],max(25,L*.75),max(25,W*.75),h,ang]
                fit,loss=bbox_optimize(list(data.values()),obj,init)
                if best is None or loss<best[1]:best=(fit,loss)
        init_fit,init_loss=best
        improved,loss=refine(init_fit,per_view,edge_maps)
        pred=np.array([*sorted(improved[2:4],reverse=True),improved[4]])
        errors=np.abs(pred-gt[obj])
        row={"item_id":obj,"prediction_LWH_mm":pred.tolist(),
             "ground_truth_LWH_mm":gt[obj].tolist(),"absolute_errors_mm":errors.tolist(),
             "bbox_fit_initial_loss":init_loss,"refinement_loss":loss,"fit_parameters":improved.tolist()}
        results.append(row)
        print(obj,"LWH",np.round(pred,1),"ERROR",np.round(errors,1),flush=True)
    mae_xy=float(np.mean([(x["absolute_errors_mm"][0]+x["absolute_errors_mm"][1])/2 for x in results]))
    mae_h=float(np.mean([x["absolute_errors_mm"][2] for x in results]))
    report={"status":"EXPERIMENTAL_NOT_T01_GATE","paper_basis":"CubeSLAM Yang & Scherer 2019; own Python implementation, no copied C++",
            "assumptions":"manual ROIs, 4 views Trial 02, self-calibrated intrinsics, cuboid approximation; image Canny edges",
            "no_ground_truth_in_optimizer":True,
            "xy_mae_mm":mae_xy,"h_mae_mm":mae_h,"runtime_ms_total":(time.perf_counter()-start)*1000,
            "individual":results}
    (HERE/"paper_edge_experiment.json").write_text(json.dumps(report,indent=2)+"\n")
    print("RESULT",json.dumps({k:report[k] for k in ("xy_mae_mm","h_mae_mm","runtime_ms_total")},indent=2),flush=True)
if __name__=="__main__":run()
