"""Download and metadata-sanitize user-authorized real T01 JPEG captures.

The public repo stores pixel-identical, privacy-sanitized JPEG copies.
The original untouched photographs remain in the user-supplied Drive folder.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen
import hashlib
import json
import os
import time

from sanitize_jpeg import strip_private_jpeg_metadata, verify_visual_identity

HERE = Path(__file__).resolve().parent
IMAGES = HERE / "images"
SOURCE_FOLDER = "https://drive.google.com/drive/folders/1_rKzBn4uuPKspFRDF7G_TwtU255h-xeG"
FILES = {
    "Trial01_topdown.JPG": "1rlB2YO_fGCcQKOev9-OcBROqmuv9Dv2g",
    "Trial01_Oblique.JPG": "1p39tlASzDLrM03Zn4Ib0VmI9JweG1sVr",
    "Trial02_topdown.JPG": "1PXuKw9ojyREMXhn6mVvHp8iB7IWXnaOP",
    "Trial02_Oblique.JPG": "1fd8i9D73cIqFDRKuRPLJaNkB69kopzwL",
    "Trial02_leftside.JPG": "12QRGXOVAFyIoTUao2uD5tOi3Unjh-tEC",
    "Trial02_rightside.JPG": "11VW58hBhnNL39PINMMnK9ORu9ondmOPX",
    "Trial03_topdown.JPG": "1fpYQ5E6uw22ZtHKHZbX9bJFHN2dVwwbh",
    "Trial03_Oblique.JPG": "1TyKaqbp0_5TYnB6YztLX0wdM4NIPkT7s",
}

def fetch(item, previous):
    name, ident = item
    dest = IMAGES / name
    old = previous.get(name, {})
    existing = dest.is_file() and dest.stat().st_size > 100000
    if existing:
        raw = dest.read_bytes()
        if not raw.startswith(bytes.fromhex("ffd8ff")):
            existing = False
    if not existing:
        url = "https://drive.google.com/uc?export=download&id=" + ident
        for attempt in range(3):
            try:
                with urlopen(Request(url, headers={"User-Agent":"Mozilla/5.0"}), timeout=65) as r:
                    raw = r.read()
                if not raw.startswith(bytes.fromhex("ffd8ff")):
                    raise ValueError("Drive response is not JPEG")
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
    cleaned = strip_private_jpeg_metadata(raw)
    if cleaned != raw:
        verify_visual_identity(raw, cleaned)
        status = "sanitized" if existing else "downloaded_sanitized"
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(cleaned)
        os.replace(tmp, dest)
        source_sha = hashlib.sha256(raw).hexdigest()
    else:
        status = "verified" if existing else "downloaded"
        if not existing:
            dest.write_bytes(cleaned)
        source_sha = old.get("source_sha256", hashlib.sha256(raw).hexdigest())
    sha = hashlib.sha256(cleaned).hexdigest()
    return name, len(cleaned), sha, source_sha, status

def main():
    IMAGES.mkdir(parents=True, exist_ok=True)
    path = HERE/"source_manifest.json"
    try:
        previous=json.loads(path.read_text(encoding="utf-8"))["images"]
    except (FileNotFoundError,KeyError,json.JSONDecodeError):
        previous={}
    manifest = {"source_folder":SOURCE_FOLDER,
                "asset_policy":"public repo stores pixel-identical JPEGs without GPS/XMP/IPTC; retains minimal EXIF orientation when required",
                "images":{}}
    with ThreadPoolExecutor(max_workers=4) as pool:
        future_map={pool.submit(fetch,item,previous):item[0] for item in FILES.items()}
        for job in as_completed(future_map):
            name,size,sha,source_sha,status=job.result()
            print(f"{status}: {name} {size} bytes",flush=True)
            manifest["images"][name]={"drive_id":FILES[name],"sha256":sha,
                                     "source_sha256":source_sha,"bytes":size}
    path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("VERIFIED",len(manifest["images"]),"sanitized JPEG images",flush=True)

if __name__=="__main__":
    main()
