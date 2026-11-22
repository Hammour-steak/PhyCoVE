"""Shared paths, frozen scene specification and safe artifact utilities."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import blender

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ["PCVE_ROOT"]).resolve() if os.environ.get("PCVE_ROOT") else HERE.parents[2]
SPEC = json.loads((HERE / "scene_spec.json").read_text())
ASSETS = ROOT / "assets/elastic_fluid/wind_flag_extended"
RUNTIME_DEPS = Path(os.environ.get("PCVE_IPC_DEPS",str(ROOT / ".runtime/wind_flag_ipc_deps")))
SOURCE_ID = "wind_flag_baseline"
CASE_MAP = {SOURCE_ID: "source", "edit_wind_6mps": "flow_6mps",
            "edit_young_modulus_100mpa": "young_stiff", "edit_wind_drop_at_2s": "wind_drop_at_2s",
            "edit_wind_0p5mps": "flow_0p5mps", "edit_wind_0mps": "flow_0mps"}
CASE_E = {name: SPEC["physics"]["young_modulus_pa"] for name in CASE_MAP.values()}
CASE_E["young_stiff"] = SPEC["approved_edits"]["young_stiff"]["young_modulus_pa"]
CASE_WIND_SPEED = {native:SPEC["approved_edits"].get(native,{}).get(
    "wind_reference_speed_m_s",SPEC["physics"]["wind_reference_speed_m_s"]) for native in CASE_MAP.values()}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    temporary.replace(path)


def ensure_json(path, value):
    path = Path(path)
    if path.exists():
        if read_json(path) != value:
            raise RuntimeError(f"Refusing to replace a different configuration: {path}")
    else:
        write_json(path, value)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def copy_verified(source, destination, expected):
    source, destination = Path(source), Path(destination)
    if digest(source) != expected:
        raise RuntimeError(f"Input hash mismatch: {source}")
    if destination.exists():
        if digest(destination) != expected:
            raise RuntimeError(f"Refusing to overwrite different content: {destination}")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    if digest(destination) != expected:
        raise RuntimeError(f"Copy verification failed: {destination}")


def default_blender():
    return os.environ.get("BLENDER") or shutil.which("blender") or str(blender())


def choose_gpu(request="auto"):
    if str(request) != "auto":
        if not str(request).isdigit():
            raise ValueError("--gpu must be auto or a physical GPU index")
        return str(request)
    rows = subprocess.check_output(["nvidia-smi", "--query-gpu=index,utilization.gpu,memory.free", "--format=csv,noheader,nounits"], text=True)
    devices = [tuple(map(int, line.split(","))) for line in rows.splitlines()]
    free = sorted((r for r in devices if r[1] < 10 and r[2] > 8000), key=lambda r: (r[1], -r[2]))
    if not free:
        raise RuntimeError("No idle GPU with at least 8 GiB free; no quality was reduced")
    return str(free[0][0])
