"""Scene paths, accepted presets and safe workflow utilities; no solver imports."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=Path(os.environ["PCVE_ROOT"]).resolve() if os.environ.get("PCVE_ROOT") else HERE.parents[2]
STEM="glass_bottle_water_balloon_true_coupled"
SPEC=json.loads((HERE/"scene_spec.json").read_text())
TOTAL_FRAMES=96
FPS=24
CAMERA="front_low"
SAMPLES=96
SOURCE_CASE_ID="glass_jar_water_balloon_source"  # Retain existing dataset identity.
BASELINE_PHYSICS={"flow_l_min":4.5,"edge_stiffness":25.0,"elastic_modulus_scale":1.0}
SIM_PRESET={"frames":96,"pump_start_frame":2,"bend_stiffness":6.,"settle_seconds":1.,
    "latex_areal_density":.285,"damping":5.,"substeps":120,"segments":72,"ring_dz":.0016,
    "neck_rest_r":.007,"body_half_width":.026,"body_half_depth":.004,"body_length":.07,
    "level_every":6,"no_volume":False,"open_mouth":True,"water_retention":"retain_all"}
FIXED_SIM_ARGS=["--open-mouth","--bend-stiffness","6","--water-retention","retain_all"]
DEFAULT_OUT=ROOT/"renders"/STEM
# The data volume behind renders/pcve_suites (the repository's own renders/ when there is no link).
DATA_RENDERS=(ROOT/"renders/pcve_suites").resolve().parent
# Accepted native outputs (renders/<scene>/ on the data volume): never written to, and validated in their recorded layout.
READ_ONLY_OUTPUTS=(DATA_RENDERS.parent/SPEC["outputs"]["root"],)
KITCHEN=ROOT/"assets/blenderkit/modern_living_kitchen/modern_living_kitchen.blend"

def default_blender():
    """Blender 5.1.2 renders this scene: $BLENDER, else blender-5.1.2 from tools/ of the repository or ~/.local/opt (pcve_assets.blender)."""
    if str(HERE.parents[1]) not in sys.path:
        sys.path.append(str(HERE.parents[1]))
    from pcve_assets import blender
    return str(blender("5.1.2"))

def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def read_json(path):
    return json.loads(Path(path).read_text())

def write_json(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+".tmp")
    tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n")
    tmp.replace(path)

def _compared(value):
    """value without outputs.root, which only records where accepted outputs are stored and may be absolute in case copies of scene_spec.json."""
    if isinstance(value,dict) and isinstance(value.get("outputs"),dict) and "root" in value["outputs"]:
        value={**value,"outputs":{k:v for k,v in value["outputs"].items() if k!="root"}}
    return value

def ensure_json(path,value):
    """Write value, or check that an existing file holds the same value (outputs.root is not compared)."""
    path=Path(path)
    if path.exists():
        if _compared(read_json(path))!=_compared(value):
            raise RuntimeError("Refusing to overwrite a different configuration: "+str(path))
    else:
        write_json(path,value)

def require_empty(path):
    path=Path(path)
    if path.exists() and any(path.iterdir()):
        raise RuntimeError("Refusing to overwrite existing output: "+str(path))

def choose_gpu(request="auto"):
    if str(request)!="auto":
        if not str(request).isdigit():
            raise ValueError("--gpu must be auto or a physical GPU index")
        return str(request)
    output=subprocess.check_output(["nvidia-smi","--query-gpu=index,utilization.gpu,memory.free",
        "--format=csv,noheader,nounits"],text=True)
    devices=[tuple(map(int,row.split(","))) for row in output.splitlines()]
    free=sorted((d for d in devices if d[1]<10 and d[2]>8000),key=lambda d:(d[1],-d[2],d[0]))
    if not free:
        raise RuntimeError("No idle GPU with 8 GiB free; quality has not been lowered")
    return str(free[0][0])

def run(command,log,env=None):
    log=Path(log)
    log.parent.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    with log.open("xb") as stream:
        result=subprocess.run([str(c) for c in command],stdin=subprocess.DEVNULL,stdout=stream,
            stderr=subprocess.STDOUT,env=env)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {log}")
    return time.monotonic()-started

def files_manifest(directory):
    directory=Path(directory)
    return {str(p.relative_to(directory)):digest(p) for p in sorted(directory.rglob("*")) if p.is_file()}

def verify_files(directory,files):
    for relative,expected in files.items():
        if digest(Path(directory)/relative)!=expected:
            raise RuntimeError("Changed output: "+str(Path(directory)/relative))
