"""Verify the accepted native delivery (videos, native caches, clocks, strict edits) and the published timed edit."""

import ast
import hashlib
import json
import struct
import zipfile
from pathlib import Path

from pcve_media_contract import require_times, require_video
from pcve_edit_policy import audit_suite_manifest
from pcve_edit_catalog import load_catalog
from edit_vocab import VOCAB

REPO=Path(__file__).resolve().parents[4]
# Accepted native delivery (videos, physics caches, receipts), checked by --stage verify.
DATA=REPO/"renders/slingshot_domino"
DELIVERY=DATA/"delivery/accepted"
# Outputs of new solves, renders and reports; nothing is written under scripts/.
WORK=REPO/"renders/slingshot_domino"
SUITE=REPO/"renders/pcve_suites/pcve_slingshot_domino_suite"
# Timed edits are native continuations solved after the accepted delivery; they are checked in the suite.
TIMED=("heavy_domino_at_frame_12",)
PUBLISHED={r["case_id"] for r in load_catalog(Path(__file__).resolve().parents[1]/"build_pcve_slingshot_domino.py")["edits"].values()}
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

def verify_timed(case):
    """A published timed edit: media contract, native clock and the cache recorded in its provenance."""
    folder=SUITE/"cases"/("edit_"+case)
    video,state=folder/"video.mp4",folder/"native_metadata/trajectory.npz"
    info=require_video(video)
    times=load_times(state,"time_s")
    require_times(times)
    digest=hashlib.sha256(video.read_bytes()).hexdigest()
    if json.loads((folder/"provenance.json").read_bytes())["video_sha256"]!=digest:
        raise ValueError(f"{case}: video differs from its provenance.json")
    return {"case_id":case,"video":str(video),"video_sha256":digest,"native_cache":str(state),
            "native_cache_sha256":hashlib.sha256(state.read_bytes()).hexdigest(),"native_samples":len(times),"media":info}

def verify(cases,data=DATA):
    data=Path(data);delivery=data/DELIVERY.relative_to(DATA)
    manifest=json.loads((delivery/"suite_manifest.json").read_bytes())
    # The accepted delivery also records an ADD case that the published suite does not carry;
    # the strict edit policy is checked for the published cases.
    manifest["edits"]=[e for e in manifest["edits"] if e.get("case_id") in PUBLISHED]
    if not audit_suite_manifest(manifest,VOCAB,delivery)["all_edits_compliant"]:
        raise ValueError("Strict edit policy failed")
    result=[]
    for case in cases:
        if case in TIMED:
            result.append(verify_timed(case))
            continue
        folder=delivery/"cases"/case
        video,state=folder/"video.mp4",folder/"physics_cache.npz"
        info=require_video(video)
        times=load_times(state,"time_s")
        require_times(times)
        # The case's encoding receipt records the sha256 of its video and of the native cache it replays.
        receipt=json.loads((folder/"encoding_receipt.json").read_bytes())
        video_sha=hashlib.sha256(video.read_bytes()).hexdigest();state_sha=hashlib.sha256(state.read_bytes()).hexdigest()
        if video_sha!=receipt["video_sha256"] or state_sha!=receipt["physics_cache_sha256"]:
            raise ValueError(f"{case}: video or native cache differs from its encoding_receipt.json")
        result.append({"case_id":case,"video":str(video),"video_sha256":video_sha,
                       "native_cache":str(state),"native_cache_sha256":state_sha,
                       "native_samples":len(times),"media":info})
    return result
