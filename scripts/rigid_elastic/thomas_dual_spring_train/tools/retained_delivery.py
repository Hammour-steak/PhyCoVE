"""Read-only check of the accepted delivery: each video and native state against its render provenance, and the 96 native states."""

import ast
import hashlib
import json
import struct
import zipfile
from pathlib import Path

from pcve_media_contract import require_times, require_video

# Accepted native delivery (delivery/accepted, simulation/accepted, outputs/accepted), checked by --stage verify.
DATA = Path(__file__).resolve().parents[4] / "renders/thomas_dual_spring_train"
# Outputs of new solves and renders, launch leases and Blender caches; nothing is written under scripts/.
WORK = Path(__file__).resolve().parents[4] / "renders/thomas_dual_spring_train"
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

def verify(cases, data=DATA):
    data = Path(data)
    result = []
    for case in cases:
        video = data / f"delivery/accepted/{case}/video.mp4"
        state = data / f"simulation/accepted/{case}/states.npz"
        record = json.loads((data / f"delivery/accepted/{case}/render_provenance.json").read_text())
        video_sha = hashlib.sha256(video.read_bytes()).hexdigest()
        state_sha = hashlib.sha256(state.read_bytes()).hexdigest()
        if video_sha != record["video_sha256"] or state_sha != record["state_cache_sha256"]:
            raise ValueError(f"{case}: video or native states differ from render_provenance.json")
        info = require_video(video)
        times = load_times(state, "time")
        require_times(times)
        result.append({"case_id": case, "video": str(video), "video_sha256": video_sha,
                       "native_cache": str(state), "native_cache_sha256": state_sha,
                       "native_samples": len(times), "media": info})
    return result
