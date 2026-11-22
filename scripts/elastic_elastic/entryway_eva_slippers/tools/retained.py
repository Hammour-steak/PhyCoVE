from pathlib import Path
import ast,hashlib,json,struct,sys,zipfile

CASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CASE.parents[1]))
sys.path.append(str(CASE/"tools/native"))  # appended: the scene's own edit_vocab.py must stay first
from common import DATA  # accepted native delivery (renders/entryway_eva_slippers)
from pcve_media_contract import require_video
# New simulate/render/verify outputs go below this root, outside scripts/.
WORK=CASE.parents[2]/"renders"/CASE.name

SUITE=DATA/"accepted_delivery/pcve_entryway_eva_slippers_suite"
CASES=("source","stiff_falling","slippery_floor","light_falling","remove_resting","add_shoe_tray")

def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest() if hasattr(hashlib,"file_digest") else digest_stream(f)

def digest_stream(stream):
    value=hashlib.sha256()
    for part in iter(lambda:stream.read(4<<20),b""):
        value.update(part)
    return value.hexdigest()

def read(path):
    return json.loads(path.read_bytes())

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


def require_clock(path,count,fps):
    values=load_times(path,"times")
    if len(values)!=count or any(abs(t-i/fps)>1e-6 for i,t in enumerate(values)):
        raise ValueError(f"Wrong native sample clock in {path}")
    return len(values)

def require_listed(path,manifest):
    """The data file matches its entry in the case's artifact_manifest.json."""
    entry=next(f for f in manifest["files"] if f["path"]==path.name)
    digest=sha(path)
    if digest!=entry["sha256"]:raise ValueError(f"Production binding changed: {path}")
    return digest

def out_path(path):
    target=path.expanduser().resolve()
    if WORK.resolve() not in target.parents or target.exists():
        raise ValueError(f"Choose a fresh output beneath {WORK}")
    return target

def verify(cases=CASES):
    import edit_vocab as vocab
    from pcve_edit_policy import audit_suite_manifest
    manifest=read(SUITE/"suite_manifest.json")
    audit=audit_suite_manifest(manifest,vocab.VOCAB,SUITE)
    assert audit["all_edits_compliant"]
    result={}
    for case in cases:
        branch=SUITE/"cases"/case
        movie=branch/"video.mp4"
        state=branch/"simulation.npz"
        simulation=read(branch/"simulation_config.json")
        renderer=read(branch/"render_config.json")
        prompt=read(branch/"prompts.json")
        assert simulation["physics"]==vocab.parameters(case),case
        assert simulation["edit_dsl"]==vocab.CASE_DSL[case]
        assert prompt.get("edit_dsl")==vocab.CASE_DSL[case]
        assert read(branch/"scenario_overrides.json")==vocab.override_for(case)
        artifacts=read(branch/"artifact_manifest.json")
        video_sha=require_listed(movie,artifacts)
        native_sha=require_listed(state,artifacts)
        assert renderer["native_cache_sha256"]==native_sha and renderer["physics_take"]=="production"
        result[case]={"video":str(movie),"video_sha256":video_sha,"native_sha256":native_sha,
                      "media":require_video(movie),"native_samples":require_clock(state,97,24)}
    return {"verified_cases":result,"strict_edits":True,"accepted_benchmark_GT":False}
