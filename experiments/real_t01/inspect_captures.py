"""Create visual contact sheet and basic ArUco inventory (diagnostic only)."""
from pathlib import Path
import cv2, json, numpy as np
HERE = Path(__file__).resolve().parent
images = sorted((HERE/"images").glob("*.JPG"))
D = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
detector = cv2.aruco.ArucoDetector(D,cv2.aruco.DetectorParameters())
W,H=720,510
canvas=np.full((H*2,W*4,3),235,np.uint8)
res=[]
for i,p in enumerate(images):
    im=cv2.imread(str(p))
    if im is None: raise RuntimeError("Cannot decode "+p.name)
    h,w=im.shape[:2]
    corners,ids,rejected=detector.detectMarkers(im)
    allids=ids.ravel().astype(int).tolist() if ids is not None else []
    thumb=cv2.resize(im,(W,460),interpolation=cv2.INTER_AREA)
    for cc,marker_id in zip(corners,allids):
        poly=(cc.reshape(4,2)*[W/w,460/h]).astype(np.int32)
        cv2.polylines(thumb,[poly],True,(0,255,0),3)
        cv2.putText(thumb,str(marker_id),tuple(poly[0]),cv2.FONT_HERSHEY_SIMPLEX,.95,(0,0,255),3)
    y=(i//4)*H;x=(i%4)*W
    canvas[y:y+460,x:x+W]=thumb
    cv2.putText(canvas,p.name+"  "+str((w,h))+" IDs="+str(allids), (x+12,y+492),cv2.FONT_HERSHEY_SIMPLEX,.53,(0,0,0),2)
    res.append({"file":p.name,"width":w,"height":h,"marker_ids":allids,"marker_count":len(allids)})
out=HERE/"contact_sheet.jpg"
cv2.imwrite(str(out),canvas,[cv2.IMWRITE_JPEG_QUALITY,87])
(HERE/"marker_inventory.json").write_text(json.dumps(res,indent=2)+"\n",encoding="utf-8")
print(json.dumps(res,indent=2))
print("CONTACT_SHEET",out)
