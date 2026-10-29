"""Experimental two-view cuboid fitting with silhouette boundary constraints.

Inspired by visual-hull/silhouette consistency and CubeSLAM geometric cuboids;
independent OpenCV/NumPy implementation. NO ground-truth dimensions as input.
Needs manually supplied ROI, GrabCut, estimated camera intrinsics. Research only.
"""
from pathlib import Path
from time import perf_counter
import json,math,csv
import numpy as np
import cv2

from experiments.real_t01.paper_two_view import TRIAL_PAIRS,load_views,center_guess,HERE
from experiments.real_t01.exploratory_fit import optimize as bbox_optimize
from experiments.real_t01.paper_edge_experiment import model_vertices

SCALE=0.23
SILHOUETTE_SAMPLES=32

def silhouette_evidence(image, roi):
    """Segment one manually initialized ROI. Returns silhouette contour in global coordinates."""
    x0,y0,x1,y1=roi
    patch=image[y0:y1,x0:x1]
    if patch.size==0:raise ValueError("Empty ROI")
    ph,pw=patch.shape[:2]
    scale=min(1.,360./max(ph,pw))
    im=cv2.resize(patch,(max(30,int(pw*scale)),max(30,int(ph*scale))),interpolation=cv2.INTER_AREA)
    h,w=im.shape[:2]
    mask=np.full((h,w),cv2.GC_PR_BGD,np.uint8)
    by,bx=max(2,int(.035*h)),max(2,int(.035*w))
    mask[:by]=cv2.GC_BGD;mask[-by:]=cv2.GC_BGD
    mask[:,:bx]=cv2.GC_BGD;mask[:,-bx:]=cv2.GC_BGD
    mask[int(.12*h):int(.88*h),int(.12*w):int(.88*w)]=cv2.GC_PR_FGD
    mask[int(.35*h):int(.65*h),int(.35*w):int(.65*w)]=cv2.GC_FGD
    cv2.grabCut(im,mask,None,np.zeros((1,65),np.float64),np.zeros((1,65),np.float64),2,cv2.GC_INIT_WITH_MASK)
    binary=np.where((mask==cv2.GC_FGD)|(mask==cv2.GC_PR_FGD),255,0).astype(np.uint8)
    contours,_=cv2.findContours(binary,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
    if not contours:raise RuntimeError("No GrabCut foreground")
    biggest=max(contours,key=cv2.contourArea).reshape(-1,2).astype(float)
    if cv2.contourArea(biggest.astype(np.float32))<.015*w*h:raise RuntimeError("Invalid contour")
    return biggest/scale+np.array([x0,y0])

def evidence_for_pair(trial,names,views,annotations):
    images={}
    for name in names:
        im=cv2.imread(str(HERE/"images"/name))
        H,W=im.shape[:2]
        byobj={}
        for item,relative in annotations[name].items():
            x0=int(relative[0]*W/720)
            y0=int(relative[1]*H/460)
            x1=int(relative[2]*W/720)
            y1=int(relative[3]*H/460)
            contour=silhouette_evidence(im,(x0,y0,x1,y1))
            if H>W:
                contour=np.c_[H-1-contour[:,1],contour[:,0]]
            # 32 fixed samples of observed silhouette.
            obs=contour[np.linspace(0,len(contour)-1,SILHOUETTE_SAMPLES).astype(int)]*SCALE
            pose=views[name]["pose"]
            ed=np.zeros((int(3024*SCALE)+2,int(4032*SCALE)+2),np.uint8)
            cv2.polylines(ed,[np.round(contour*SCALE).astype(np.int32)],True,255,2)
            distance=np.minimum(cv2.distanceTransform(255-ed,cv2.DIST_L2,3),26.)
            byobj[item]=(distance,obs)
        images[name]=byobj
    return images

def sampled_outline(hull,n=SILHOUETTE_SAMPLES):
    # Interpolate an equal-length sample of the convex hull boundary.
    close=np.vstack([hull,hull[0]])
    edge=close[1:]-close[:-1]
    length=np.linalg.norm(edge,axis=1)
    cum=np.r_[0,np.cumsum(length)]
    total=cum[-1]
    if total<.001:return np.tile(hull[0],(n,1))
    t=np.linspace(0,total,n,endpoint=False)
    idx=np.searchsorted(cum,t,side="right")-1
    idx=np.minimum(idx,len(edge)-1)
    u=(t-cum[idx])/np.maximum(length[idx],1e-9)
    return close[idx]+u[:,None]*edge[idx]

def residual(p,items):
    vert=model_vertices(p)
    out=[]
    for pose,bbox,dist,obs in items:
        xy,_=cv2.projectPoints(vert,pose["rvec"],pose["tvec"],pose["camera_matrix"],pose["dist_coeffs"])
        xy=xy.reshape(-1,2)
        box=np.array([xy[:,0].min(),xy[:,1].min(),xy[:,0].max(),xy[:,1].max()])
        out.extend(((box-bbox)*SCALE*.55).tolist())
        hull=cv2.convexHull(xy.astype(np.float32)).reshape(-1,2)*SCALE
        samples=sampled_outline(hull)
        vals=cv2.remap(dist,samples[:,0].astype(np.float32).reshape(1,-1),
                       samples[:,1].astype(np.float32).reshape(1,-1),cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_CONSTANT,borderValue=26).ravel()
        out.extend((np.minimum(vals,17.)*.8).tolist())
        # Reverse chamfer, penalizes cuboid that is too small to cover mask.
        segments=np.roll(hull,-1,axis=0)-hull
        relative=obs[:,None,:]-hull[None,:,:]
        t=np.clip(np.sum(relative*segments[None,:,:],axis=-1)/
                  np.maximum(np.sum(segments*segments,axis=-1)[None,:],1.e-6),0,1)
        nearest=hull[None,:,:]+t[:,:,None]*segments[None,:,:]
        dd=np.linalg.norm(obs[:,None,:]-nearest,axis=-1).min(axis=1)
        out.extend((np.minimum(dd,17.)*.8).tolist())
    return np.asarray(out,float)

def refine(p,items,maxiter=40):
    p=np.asarray(p,float).copy()
    step=np.array([.5,.5,.5,.5,.5,.005])
    damping=1.
    eye=np.eye(6)*step[:,None]
    r=residual(p,items);score=float(r@r)
    for it in range(maxiter):
        J=np.column_stack([(residual(p+eye[j],items)-r)/step[j] for j in range(6)])
        try:d=-np.linalg.solve(J.T@J+np.eye(6)*damping,J.T@r)
        except np.linalg.LinAlgError:break
        pp=p+d
        pp[2:5]=np.clip(pp[2:5],15,300)
        pp[5]%=2*math.pi
        rr=residual(pp,items)
        ss=float(rr@rr)
        if ss<score:
            change=score-ss
            p,r,score=pp,rr,ss
            damping=max(.0001,damping*.6)
            if change<1.e-5:break
        else:damping=min(1.e5,damping*2)
        if np.linalg.norm(d)<1.e-4:break
    return p,score

def run():
    annotations=json.loads((HERE/"roi_annotations.json").read_text(encoding="utf-8"))
    gt={}
    with (HERE/"ground_truth.csv").open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            gt[row["item_id"]]=np.array([float(row[v]) for v in ("length_mm","width_mm","height_mm")])
    result={"status":"EXPLORATORY_NOT_T01_GATE","paper_inspiration":"CubeSLAM geometry + visual-hull silhouette consistency, independent implementation",
            "constraints":"Manual ROI + GrabCut, self-calibration on same captures, two views, no GT as optimizer input",
            "trials":{}}
    start=perf_counter()
    for trial,names in TRIAL_PAIRS.items():
        tic=perf_counter()
        views=load_views(names)
        evidence=evidence_for_pair(trial,names,views,annotations)
        data=list(views.values())
        predictions=[]
        for item in gt:
            xy,l,w=center_guess(views[names[0]],item)
            best=None
            # Identical eight starting seeds as the published v1 local baseline.
            for yaw in (0,math.pi/4,math.pi/2,3*math.pi/4):
                for H0 in (35.,90.):
                    init=[xy[0],xy[1],max(25,l*.75),max(25,w*.75),H0,yaw]
                    p,loss=bbox_optimize(data,item,init)
                    if best is None or loss<best[1]:best=(p,loss)
            observations=[(views[name]["pose"],views[name]["items"][item]["bbox"],
                           *evidence[name][item]) for name in names]
            p,loss=refine(best[0],observations)
            pred=np.r_[sorted(p[2:4],reverse=True),p[4]]
            err=np.abs(pred-gt[item])
            predictions.append({"item_id":item,"predicted_LWH_mm":pred.tolist(),
                 "absolute_errors_mm":err.tolist(),"fit_parameters":p.tolist(),
                 "silhouette_cost":float(loss)})
        xymae=float(np.mean([np.mean(x["absolute_errors_mm"][:2]) for x in predictions]))
        hmae=float(np.mean([x["absolute_errors_mm"][2] for x in predictions]))
        ms=(perf_counter()-tic)*1000
        result["trials"][trial]={"xy_mae_mm":xymae,"h_mae_mm":hmae,
                                "runtime_ms_five_objects":ms,"items":predictions}
        print(trial,"xy",round(xymae,2),"h",round(hmae,2),"ms",round(ms),flush=True)
    result["overall_xy_mae_mm"]=float(np.mean([x["xy_mae_mm"] for x in result["trials"].values()]))
    result["overall_h_mae_mm"]=float(np.mean([x["h_mae_mm"] for x in result["trials"].values()]))
    result["overall_runtime_ms"]=round((perf_counter()-start)*1000,1)
    (HERE/"silhouette_experiment.json").write_text(json.dumps(result,indent=2)+"\n")
    print("TOTAL",round(result["overall_xy_mae_mm"],2),round(result["overall_h_mae_mm"],2),flush=True)
    return result

if __name__=="__main__":run()
