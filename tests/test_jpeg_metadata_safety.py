"""Regression tests preventing EXIF GPS leaks in GitHub T01 image assets."""
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from experiments.real_t01.sanitize_jpeg import (
    strip_private_jpeg_metadata, verify_visual_identity,
)

HERE=Path(__file__).resolve().parents[1]/"experiments"/"real_t01"

def test_public_jpegs_have_no_private_metadata():
    manifest=json.loads((HERE/"source_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["images"])==8
    stripped=0
    for name,record in manifest["images"].items():
        data=(HERE/"images"/name).read_bytes()
        assert hashlib.sha256(data).hexdigest()==record["sha256"]
        assert strip_private_jpeg_metadata(data)==data, name
        assert record["source_sha256"] != record["sha256"], name
        stripped+=1
    assert stripped==8

def test_jpeg_scrubbing_keeps_compressed_image_visually_identical():
    img=np.zeros((80,120,3),np.uint8)
    img[8:70,19:100]=(82,121,221)
    ok,jpg=cv2.imencode(".jpg",img)
    assert ok
    raw=jpg.tobytes()
    # Inject an APP1 XMP segment containing deliberately non-private dummy text.
    payload=b"http://ns.adobe.com/xap/1.0/\x00"+b"dummy metadata payload"
    app1=b"\xff\xe1"+(len(payload)+2).to_bytes(2,"big")+payload
    augmented=raw[:2]+app1+raw[2:]
    output=strip_private_jpeg_metadata(augmented)
    assert output==raw
    verify_visual_identity(augmented,output)
