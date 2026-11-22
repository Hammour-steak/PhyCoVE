"""Paths, registered inputs and small helpers shared by the phone_sofa_drop entries (stdlib only)."""
from __future__ import annotations

import ast
import hashlib
import json
import shutil
import struct
import sys
import zipfile
from pathlib import Path

SCENE = Path(__file__).resolve().parents[1]
SCRIPTS = SCENE.parents[1]
REPO = SCRIPTS.parent
for _p in (SCRIPTS, SCENE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
from pcve_assets import asset  # noqa: E402

SPEC = json.loads((SCENE / "scene_spec.json").read_text(encoding="utf-8"))
CASE_IDS = ("source", *SPEC["edit_dsl"])
SCENE_ASSETS = "scenes/phone_sofa_drop"
SUITE_KEY = "pcve_phone_sofa_drop_suite"
SUITE_DIR = REPO / "renders" / "pcve_suites" / SUITE_KEY
RENDER_ROOT = REPO / "renders" / "phone_sofa_drop" / "render"
# numpy Python for ground truth and physics: the repository venv when present.
PYTHON = REPO / ".venv-rigid-elastic" / "bin" / "python"
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)
BLENDER_DEFAULT = REPO / "tools" / "blender-4.3.2-linux-x64" / "blender"
CACHES = {  # window -> (registered file, state rate, state count)
    "4s": ("solves_4s_240hz/{case}/simulation_dense.npz", 240, 961),
    "3s": ("solves_3s_30hz/{case}/simulation.npz", 30, 91),
}


def catalog_id(case):
    return "source" if case == "source" else f"edit_{case}"


def sha256(path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(16 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".writing")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def registered_files():
    return json.loads((REPO / "assets.json").read_text(encoding="utf-8"))["assets"][SCENE_ASSETS]["files"]


def sample_times(npz):
    """The cache's `times` array, read without numpy."""
    with zipfile.ZipFile(npz) as archive:
        raw = archive.read("times.npy")
    if raw[:6] != b"\x93NUMPY":
        raise ValueError(f"Unexpected native sample clock format: {npz}")
    size, offset = (struct.unpack_from("<H", raw, 8)[0], 10) if raw[6] == 1 else (struct.unpack_from("<I", raw, 8)[0], 12)
    header = ast.literal_eval(raw[offset:offset + size].decode("latin1"))
    if header["descr"] != "<f8" or header["fortran_order"] or len(header["shape"]) != 1:
        raise ValueError(f"Unexpected native sample clock layout: {npz}")
    return struct.unpack(f"<{header['shape'][0]}d", raw[offset + size:])


def native_cache(case, window="4s"):
    """Check one registered cache (sha256 against assets.json, exact sample clock)."""
    name, rate, count = CACHES[window]
    name = name.format(case=case)
    path = asset(f"{SCENE_ASSETS}/{name}")
    digest = sha256(path)
    if digest != registered_files()[name]["sha256"]:
        raise ValueError(f"Native cache differs from assets.json: {name}")
    times = sample_times(path)
    if len(times) != count or any(abs(t - i / rate) > 1e-12 for i, t in enumerate(times)):
        raise ValueError(f"{case}: {name} is not the {rate} Hz clock with {count} states")
    return path, times, digest


def copy_verified(source, destination):
    digest = sha256(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256(destination) != digest:
            raise FileExistsError(destination)
        return digest
    with destination.open("xb") as output, Path(source).open("rb") as original:
        shutil.copyfileobj(original, output)
    if sha256(destination) != digest:
        raise ValueError(f"Copy verification failed: {destination}")
    return digest


def canonical_suite():
    """(suite directory, {catalog case: video sha256}) from scene_manifest.json."""
    manifest = json.loads((SCENE / "scene_manifest.json").read_text(encoding="utf-8"))
    entry = manifest["canonical_suites"][SUITE_KEY]
    target = Path(entry["target"])
    return (target if target.is_absolute() else REPO / target), entry["case_video_sha256"]
