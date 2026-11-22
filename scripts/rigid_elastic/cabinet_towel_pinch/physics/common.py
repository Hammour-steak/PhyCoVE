"""Shared case paths and immutable scene specification (no Blender imports)."""
from pathlib import Path
import hashlib, json, sys

HERE = Path(__file__).resolve().parent          # physics/
SCENE_DIR = HERE.parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / 'scripts'))
from pcve_assets import asset

CASE = 'cabinet_towel_pinch'
ASSETS = asset('scenes/cabinet_towel_pinch')
# Worker receipts and reproduction outputs.
WORK = REPO / 'renders' / CASE / 'rebuild'
# CPython 3.10 + pyuipc 0.0.29 runtime, staged on the solver worker (see README).
RUNTIME = REPO / '.runtime' / CASE

from pcve_media_contract import CONTRACT
FPS = CONTRACT['fps']
DURATION = CONTRACT['duration_s']
FRAMES = CONTRACT['frames']
WIDTH = CONTRACT['width']
HEIGHT = CONTRACT['height']
assert (FPS,FRAMES,WIDTH,HEIGHT,DURATION)==(24,96,1280,720,4.),'Current source/edit delivery must match the user canonical media contract'

def cpu_runtime():
    if (RUNTIME/'python/bin/python3.10').is_file():return RUNTIME
    raise FileNotFoundError('Stage the CPython 3.10 / pyuipc 0.0.29 runtime in '+str(RUNTIME)+' on this worker')

def save(p, value):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda: f.read(1<<20), b''): h.update(block)
    return h.hexdigest()
