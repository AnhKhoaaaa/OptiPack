"""Privacy-preserving lossless JPEG metadata removal for public GitHub assets.

Drops EXIF private tags (including GPS), XMP (APP1), IPTC (APP13) and JPEG comments.
Keeps the entropy-coded compressed image data UNCHANGED. Retains only a
minimal EXIF orientation tag, if present, for identical decoded pixels.
"""
from pathlib import Path
import struct

def exif_orientation(segment: bytes):
    if not segment.startswith(b"Exif\x00\x00"):
        return None
    tiff=segment[6:]
    if len(tiff)<14 or tiff[:2] not in (b"II",b"MM"):
        return None
    endian="<" if tiff[:2]==b"II" else ">"
    try:
        if struct.unpack_from(endian+"H",tiff,2)[0]!=42:return None
        off=struct.unpack_from(endian+"I",tiff,4)[0]
        count=struct.unpack_from(endian+"H",tiff,off)[0]
        for i in range(count):
            p=off+2+12*i
            tag,kind,n=struct.unpack_from(endian+"HHI",tiff,p)
            if tag==0x0112 and kind==3 and n==1:
                return struct.unpack_from(endian+"H",tiff,p+8)[0]
    except (ValueError,struct.error,IndexError):
        return None
    return None

def orientation_segment(direction: int):
    body=(b"Exif\x00\x00"+b"II"+struct.pack("<H",42)+struct.pack("<I",8)+
          struct.pack("<H",1)+struct.pack("<HHI",0x0112,3,1)+
          struct.pack("<H",direction)+b"\x00\x00"+struct.pack("<I",0))
    return b"\xff\xe1"+struct.pack(">H",len(body)+2)+body

def strip_private_jpeg_metadata(image: bytes) -> bytes:
    if not image.startswith(b"\xff\xd8"):raise ValueError("Expected JPEG SOI")
    output=bytearray(image[:2])
    orientation=None
    p=2
    while p<len(image):
        if image[p]!=0xff:raise ValueError("Malformed JPEG segment boundary")
        start=p
        while p<len(image) and image[p]==0xff:p+=1
        if p>=len(image):raise ValueError("Truncated JPEG marker")
        marker=image[p];p+=1
        if marker==0xda:  # Start of scan: preserve entropy-coded image verbatim.
            output.extend(image[start:])
            break
        if marker==0xd9:
            output.extend(image[start:])
            break
        if marker in (0x01,*range(0xd0,0xd8)):
            output.extend(image[start:p])
            continue
        if p+2>len(image):raise ValueError("Truncated JPEG length")
        length=struct.unpack_from(">H",image,p)[0]
        if length<2 or p+length>len(image):raise ValueError("Invalid JPEG segment length")
        payload=image[p+2:p+length]
        if marker==0xe1:
            if payload.startswith(b"Exif\x00\x00"):
                orientation=exif_orientation(payload)
            # Drop EXIF, XMP and all other APP1 metadata.
        elif marker in (0xed,0xfe):
            # Drop IPTC/Photoshop and free-form comments.
            pass
        else:
            output.extend(image[start:p+length])
        p+=length
    else:
        raise ValueError("JPEG scan not found")
    if orientation is not None and orientation not in range(1,9):
        raise ValueError("Invalid EXIF orientation")
    if orientation is not None and orientation!=1:
        output[2:2]=orientation_segment(orientation)
    return bytes(output)

def verify_visual_identity(original: bytes, cleaned: bytes):
    import cv2
    import numpy as np
    a=cv2.imdecode(np.frombuffer(original,np.uint8),cv2.IMREAD_COLOR)
    b=cv2.imdecode(np.frombuffer(cleaned,np.uint8),cv2.IMREAD_COLOR)
    if a is None or b is None or a.shape!=b.shape or not np.array_equal(a,b):
        raise AssertionError("JPEG metadata scrub altered decoded image pixels/orientation")

if __name__=="__main__":
    import sys
    path=Path(sys.argv[1])
    raw=path.read_bytes()
    clean=strip_private_jpeg_metadata(raw)
    verify_visual_identity(raw,clean)
    print("Metadata scrub possible, pixels unchanged; bytes saved:",len(raw)-len(clean))
