"""Use the original delivery audit and verify every native cache clock."""

import ast
import hashlib
import json
import struct
import zipfile
from pathlib import Path
from pcve_media_contract import require_times, require_video
from scene_inputs import ASSETS, accepted_case
from scene_paths import DELIVERY
from tools.validate_original import validate_delivery

def load_times(path, member):
    with zipfile.ZipFile(path) as z:
        raw = z.read(member + ".npy")
    if raw[:8] != b"\x93NUMPY\x01\x00":
        raise ValueError(f"Unsupported native sample clock: {path}")
    size, = struct.unpack_from("<H", raw, 8)
    header = ast.literal_eval(raw[10:10 + size].decode("latin1").strip())
    if header["descr"] not in {"<f8", "<f4"} or len(header["shape"]) != 1:
        raise ValueError(f"Expected a 1D floating-point clock: {path}")
    code = "d" if header["descr"] == "<f8" else "f"
    return struct.unpack(f"<{header['shape'][0]}{code}", raw[10 + size:])

def digest(path):
    result=hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda:source.read(4*1024**2),b""):result.update(chunk)
    return result.hexdigest()

def verify(cases):
    validate_delivery()
    # validate_delivery checks every video against delivery_verification.json; native caches are
    # covered by the asset registry.
    verified=[]
    for case in cases:
        video=accepted_case(case)/"main"/"video.mp4"
        native=ASSETS/f"native/{case}/cache.npz"
        times=load_times(native,"times")
        require_times(times)
        verified.append({"case_id":case,"video":str(video),"video_sha256":digest(video),
                         "native_cache":str(native),"native_cache_sha256":digest(native),
                         "native_samples":len(times),"media":require_video(video)})
    return verified
