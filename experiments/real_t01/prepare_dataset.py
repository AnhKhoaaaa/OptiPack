"""Crop user-identified items from original T01 captures, without resizing originals.

The ROIs in roi_annotations.json are manually initialized labels, not
automatic detections. Ground-truth dimensions are deliberately NOT consulted.
"""
from pathlib import Path
import csv
import json
import cv2
import numpy as np

HERE=Path(__file__).resolve().parent
REF_W,REF_H=720,460
ORDER=("wood","white","gocheck","black","paper")
def actual_roi(roi,w,h):
    x0,y0,x1,y1=roi
    return (max(0,int(round(x0*w/REF_W))),max(0,int(round(y0*h/REF_H))),
            min(w,int(round(x1*w/REF_W))),min(h,int(round(y1*h/REF_H))))
def build():
    mapping=json.loads((HERE/"roi_annotations.json").read_text(encoding="utf-8"))
    assert mapping["reference_size_px"]==[REF_W,REF_H]
    paths=sorted((HERE/"images").glob("*.JPG"))
    if len(paths)!=8:raise RuntimeError(f"expected eight originals, got {len(paths)}")
    dest=HERE/"crops"
    dest.mkdir(exist_ok=True)
    sheet=np.full((8*220,5*270,3),245,np.uint8)
    annotations=[]
    for row,p in enumerate(paths):
        im=cv2.imread(str(p))
        if im is None:raise RuntimeError("Cannot decode "+p.name)
        h,w=im.shape[:2]
        if set(mapping[p.name])!=set(ORDER):raise ValueError("Incomplete item IDs: "+p.name)
        for col,item in enumerate(ORDER):
            x0,y0,x1,y1=actual_roi(mapping[p.name][item],w,h)
            if x1-x0<30 or y1-y0<30:raise ValueError("Invalid crop: "+p.name+" "+item)
            crop=im[y0:y1,x0:x1]
            out=dest/f"{p.stem}__{item}.jpg"
            cv2.imwrite(str(out),crop,[cv2.IMWRITE_JPEG_QUALITY,91])
            thumb=cv2.resize(crop,(250,185),interpolation=cv2.INTER_AREA)
            x=col*270;y=row*220
            sheet[y:y+185,x:x+250]=thumb
            cv2.putText(sheet,item+" | "+p.stem,(x+2,y+205),
                        cv2.FONT_HERSHEY_SIMPLEX,.33,(0,0,0),1)
            annotations.append({"file":p.name,"item_id":item,"bbox_xyxy_px":[x0,y0,x1,y1],
                                "crop_file":out.relative_to(HERE).as_posix(),"label_source":"manual_from_visual_inspection"})
    (HERE/"crop_annotations.json").write_text(json.dumps(annotations,indent=2)+"\n",encoding="utf-8")
    cv2.imwrite(str(HERE/"crop_contact_sheet.jpg"),sheet,[cv2.IMWRITE_JPEG_QUALITY,80])
    print(f"CROPPED {len(annotations)} manually localized object views from {len(paths)} images.")
if __name__=="__main__":build()
