"""Deterministically render a two-view, geometrically calibrated CV test scene.

Synthetic images are for software verification, NOT real-world Phase 0 evidence.
Run: .venv\\Scripts\\python.exe experiments\\synthetic_t01\\generate_fixture.py
"""
from pathlib import Path
import json
import cv2
import numpy as np

OUT = Path(__file__).resolve().parent
W, H = 1600, 1050
K = np.array([[1500.,0.,W/2],[0.,1500.,H/2],[0.,0.,1.]])
DIST = np.zeros(5)
MARKERS = {0:(0.,0.),1:(237.,0.),2:(237.,150.),3:(0.,150.)}
BOX = {"length_mm":200,"width_mm":140,"height_mm":105,
       "x0_mm":365,"y0_mm":27,"z0_mm":0}
ARUCO = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


def camera(eye, target):
    eye=np.array(eye,float); target=np.array(target,float)
    f=target-eye; f/=np.linalg.norm(f)
    right=np.cross(f, [0.,1.,0.]); right/=np.linalg.norm(right)
    up=np.cross(right, f); up/=np.linalg.norm(up)
    R=np.vstack([right,-up,f]); t=-R@eye
    return R,t


def project(points, R, t):
    p=np.asarray(points,np.float64).reshape(-1,3)
    z,_=cv2.projectPoints(p,cv2.Rodrigues(R)[0],t,K,DIST)
    return z.reshape(-1,2).astype(np.float32)


def polygon(dst, pts, color, R, t, border=None):
    px=np.rint(project(pts,R,t)).astype(np.int32)
    cv2.fillConvexPoly(dst,px,color,lineType=cv2.LINE_AA)
    if border is not None:
        cv2.polylines(dst,[px],True,border,3,cv2.LINE_AA)


def texture(dst, bitmap, corners, R, t, interp=cv2.INTER_NEAREST):
    sh,sw=bitmap.shape[:2]
    src=np.array([[0,0],[sw-1,0],[sw-1,sh-1],[0,sh-1]],np.float32)
    transform=cv2.getPerspectiveTransform(src,project(corners,R,t))
    result=cv2.warpPerspective(bitmap,transform,(W,H),flags=interp)
    alpha=cv2.warpPerspective(np.full((sh,sw),255,np.uint8),transform,(W,H),flags=cv2.INTER_NEAREST)
    dst[alpha>0]=result[alpha>0]


def render(view, eye, target):
    R,t=camera(eye,target)
    rng=np.random.default_rng(42)
    background=210+rng.normal(0,1.2,(H,W))
    img=np.stack([background*.95,background,background*1.015],axis=-1).clip(0,255).astype(np.uint8)
    sheet=[[-10,-10,0],[287,-10,0],[287,200,0],[-10,200,0]]
    polygon(img,sheet,(250,250,250),R,t,(170,170,170))
    for tag,(x,y) in MARKERS.items():
        bmp=cv2.aruco.generateImageMarker(ARUCO,tag,720,borderBits=1)
        bmp=cv2.cvtColor(bmp,cv2.COLOR_GRAY2BGR)
        quad=[[x,y+40,0],[x+40,y+40,0],[x+40,y,0],[x,y,0]]
        texture(img,bmp,quad,R,t)
    b=BOX; x,y,z=b["x0_mm"],b["y0_mm"],b["z0_mm"]
    l,w,h=b["length_mm"],b["width_mm"],b["height_mm"]
    a=[x,y,z]; c=[x+l,y+w,z]; b0=[x+l,y,z]; d0=[x,y+w,z]
    A=[x,y,h]; B=[x+l,y,h]; C=[x+l,y+w,h]; D=[x,y+w,h]
    faces=[
        ([a,b0,B,A],(122,150,185),[0,-1,0]),
        ([b0,c,C,B],(99,127,157),[1,0,0]),
        ([d0,c,C,D],(109,136,164),[0,1,0]),
        ([a,d0,D,A],(125,153,181),[-1,0,0]),
        ([A,B,C,D],(170,191,214),[0,0,1])]
    visible=[]
    for points,color,normal in faces:
        mid=np.mean(points,axis=0)
        if np.dot(np.asarray(eye)-mid,normal)>0:
            visible.append((float(np.linalg.norm(np.asarray(eye)-mid)),points,color))
    for _,points,color in sorted(visible,key=lambda v:v[0],reverse=True):
        polygon(img,points,color,R,t,(66,83,100))
    label=np.full((120,320,3),(221,231,240),np.uint8)
    cv2.putText(label,"ITEM 01",(28,76),cv2.FONT_HERSHEY_SIMPLEX,1.4,(57,70,80),3,cv2.LINE_AA)
    texture(img,label,[[x+35,y+w-30,h],[x+l-35,y+w-30,h],
                        [x+l-35,y+30,h],[x+35,y+30,h]],R,t)
    cv2.rectangle(img,(0,0),(W,56),(45,50,59),-1)
    cv2.putText(img,f"SYNTHETIC | {view.upper()} | NOT REAL DATA",
                (24,38),cv2.FONT_HERSHEY_SIMPLEX,.85,(245,245,245),2,cv2.LINE_AA)
    filename=f"optipack_synthetic_{view}.png"
    if not cv2.imwrite(str(OUT/filename),img): raise IOError(filename)
    return {"file":filename,"view":view,"eye_xyz_mm":list(map(float,eye)),
            "rotation_world_to_camera":R.tolist(),"translation_world_to_camera_mm":t.tolist()}


def main():
    images=[render("top",[300,90,850],[300,90,0]),
            render("oblique",[550,-460,680],[280,90,0])]
    manifest={"synthetic":True,"real_world_phase0_evidence":False,
              "units":"mm","marker_dictionary":"DICT_4X4_50",
              "marker_side_mm":40,
              "marker_bottom_left_xy_mm":{str(k):list(v) for k,v in MARKERS.items()},
              "camera_intrinsic_K":K.tolist(),"distortion_coefficients":DIST.tolist(),
              "box_ground_truth":BOX,"images":images}
    (OUT/"ground_truth.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print("Saved calibrated synthetic image pair and ground_truth.json")


if __name__=="__main__": main()
