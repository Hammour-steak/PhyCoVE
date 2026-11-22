"""Check the accepted delivery: native solver states bound to their renders, exposure sidecars and the strict edit bindings."""
import ast
import hashlib
import json
import struct
import zipfile
from pathlib import Path

from edit_vocab import VOCAB
from pcve_edit_policy import audit_suite_manifest
from pcve_media_contract import require_video,require_times
from scene_driver import DATA,PUBLISHED,SUITE,TIMED_CASES

# Accepted full-clip cases: video, native state, exposure sidecar and render report under DATA.
DELIVERY="accepted_delivery/benchmark_increment/scenes/cotton_tshirt_sofa/cases"
FULL_CASES={case:{"video":f"accepted_delivery/videos/{case}.mp4",
                  "state":f"{DELIVERY}/{case}/deformation.npz",
                  "exposure":f"{DELIVERY}/{case}/shutter_positions.npz",
                  "render":f"accepted_renders/{case}/render_report.json"}
            for case in ("source","stiff_shirt","heavy_shirt","low_friction","remove_seat")}

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

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(4*1024**2),b""):h.update(block)
    return h.hexdigest()

def shutter_clock(case,exposure):
    extra=load_times(exposure,"times")
    require_times(extra[::3])
    if len(extra)!=288 or any(abs(t-(i//3)/24-(i%3)/120)>1e-8 for i,t in enumerate(extra)):
        raise ValueError(f"Shutter clock mismatch: {case}")

def verify_timed(case):
    """A timed edit: the merged native cache published with the suite continues the accepted source cache."""
    import numpy as np
    folder=PUBLISHED/"inputs/native_timed"/case
    cache,exposure=folder/"simulation.npz",folder/"shutter_positions.npz"
    completion=json.loads((folder/"completion.json").read_bytes())
    handoff=json.loads((folder/"state_handoff.json").read_bytes())
    timed=json.loads((folder/"simulation_config.json").read_bytes())["timed_continuation"]
    digest=sha256(cache)
    if completion["cache_sha256"]!=digest or completion["exposure_cache_sha256"]!=sha256(exposure):
        raise ValueError(f"Merged timed cache differs from its completion record: {case}")
    source=DATA/FULL_CASES["source"]["state"]
    if timed["source_cache_sha256"]!=sha256(source):
        raise ValueError(f"The timed solve continued another source cache: {case}")
    if not handoff["verified"] or max(handoff["max_abs_error"].values())>=1e-8:
        raise ValueError(f"State handoff not verified: {case}")
    require_times(load_times(cache,"times"))
    shutter_clock(case,exposure)
    k=int(timed["edit_frame"])
    with np.load(cache,allow_pickle=False) as merged, np.load(source,allow_pickle=False) as base:
        for key in base.files:
            if key.endswith(("_positions","_velocities")) and not np.array_equal(merged[key][:k-1],base[key][:k-1]):
                raise ValueError(f"Frames 1..{k-1} of {case} differ from the source cache: {key}")
    video=PUBLISHED/"cases"/("edit_"+case)/"video.mp4"
    return {"case_id":case,"video":str(video),"video_sha256":sha256(video),"native_cache":str(cache),
            "native_cache_sha256":digest,"edit_frame":k,"native_samples":96,"media":require_video(video)}

def verify(cases):
    manifest=json.loads((SUITE/"suite_manifest.json").read_bytes())
    # The delivery manifest also lists an ADD case that is not in the published suite; audit the published edits only.
    manifest["edits"]=[e for e in manifest.get("edits",[]) if e["case_id"] in FULL_CASES]
    if not audit_suite_manifest(manifest,VOCAB,SUITE)["all_edits_compliant"]:
        raise ValueError("Strict physical-edit check failed")
    result=[]
    for case in cases:
        if case in TIMED_CASES:
            result.append(verify_timed(case))
            continue
        row=FULL_CASES[case]
        video,state,exposure=(DATA/row[k] for k in ("video","state","exposure"))
        report=json.loads((DATA/row["render"]).read_bytes())
        state_sha=sha256(state)
        if report["cache_sha256"]!=state_sha or report["exposure_cache_sha256"]!=sha256(exposure):
            raise ValueError(f"Native render inputs differ: {case}")
        times=load_times(state,"times")
        require_times(times)
        shutter_clock(case,exposure)
        result.append({"case_id":case,"video":str(video),"video_sha256":sha256(video),"native_cache":str(state),
                       "native_cache_sha256":state_sha,"native_samples":96,"media":require_video(video)})
    return result
