"""Scene paths, output rule, runtimes, native-state extraction and single-GPU launch."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import socket
import subprocess
import sys
import zipfile

SCENE = 'rubber_band_wood_slider'
CATEGORY = 'rigid_elastic'
CASE = Path(__file__).resolve().parent
SCRIPTS = CASE.parents[1]
REPO = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from pcve_assets import asset, blender  # noqa: E402

CASES = ['source', 'young_x0p5', 'mass_x3', 'friction_x2', 'delete_band', 'add_stop']
CATALOG = {case: case if case == 'source' else f'edit_{case}' for case in CASES}
# The accepted physics: the benchmark increment with the native states (480 Hz, 4 s), registered in assets.json.
INCREMENT = asset(f'scenes/{SCENE}/native/accepted_increment.zip')
INCREMENT_NAME = f'assets/scenes/{SCENE}/native/accepted_increment.zip'   # how records name it (PCVE_ASSETS_DIR may move it)
PREFIX = f'accepted_increment/scenes/{SCENE}/'
# Runtime folder: extraction cache of the native states, launch receipts, the MuJoCo 3.17.0 runtime of the solver.
RUNTIME = REPO / '.runtime' / SCENE
NATIVE = RUNTIME / 'native'
MUJOCO = RUNTIME / 'mujoco'
RENDERS = REPO / 'renders' / SCENE
SUITE_KEY = f'pcve_{SCENE}_suite'
SUITE = REPO / 'renders/pcve_suites' / SUITE_KEY
SCENE_MANIFEST = CASE / 'scene_manifest.json'
FPS, FRAMES, RESOLUTION = 24, 96, (1280, 720)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 22), b''):
            h.update(block)
    return h.hexdigest()



def output_path(value):
    target = Path(value).expanduser().resolve()
    if target == SCRIPTS.resolve() or SCRIPTS.resolve() in target.parents:
        raise ValueError('scripts/ holds code only; write outputs elsewhere, for example under renders/')
    return target


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def increment_member(member):
    with zipfile.ZipFile(INCREMENT) as archive:
        return archive.read(PREFIX + member)


def extract(member, destination):
    """Copy one increment member to destination; an existing file must have the same bytes.

    On a render host that only received the extracted cache (no increment zip), an existing file is accepted."""
    destination = Path(destination)
    if destination.exists() and not INCREMENT.is_file():
        return destination
    payload = increment_member(member)
    digest = hashlib.sha256(payload).hexdigest()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256(destination) != digest:
            raise FileExistsError(f'{destination} differs from the increment member {member}')
    else:
        tmp = destination.with_name('.' + destination.name + '.writing')
        tmp.write_bytes(payload)
        tmp.replace(destination)
    return destination


def state_sha256(case):
    """sha256 of the accepted native states of one case, read from the registered increment."""
    return hashlib.sha256(increment_member(f'cases/{case}/simulation.npz')).hexdigest()


def native_case(case):
    """Folder with states.npz, physics.json and capture_start_audit.json of one accepted case."""
    folder = NATIVE / case
    extract(f'cases/{case}/simulation.npz', folder / 'states.npz')
    extract(f'cases/{case}/physics.json', folder / 'physics.json')
    extract('verification/capture_start_audit.json', folder / 'capture_start_audit.json')
    return folder


def blender_runtime(value=None):
    pinned = REPO / 'tools/blender-4.3.2-linux-x64/blender'
    return Path(value) if value else (pinned if pinned.is_file() else blender())


def python_runtime(value=None):
    """Python with numpy/numba (default: the repository venv)."""
    pinned = REPO / '.venv-rigid-elastic/bin/python'
    return Path(value) if value else (pinned if pinned.is_file() else Path(sys.executable))


def ffmpeg_binary():
    import shutil
    found = os.environ.get('PCVE_FFMPEG') or shutil.which('ffmpeg')
    if not found:
        raise RuntimeError('ffmpeg not found; set PCVE_FFMPEG or encode on a host with ffmpeg')
    return Path(found)


def ensure_numpy_runtime():
    """Re-run the calling script with the repository venv when numpy is missing."""
    try:
        import numpy  # noqa: F401
    except ModuleNotFoundError:
        venv = python_runtime()
        if Path(sys.executable).resolve() == venv.resolve():
            raise
        os.execv(str(venv), [str(venv), *sys.argv])


def _gpus():
    rows = subprocess.check_output(['nvidia-smi', '--query-gpu=index,uuid,name,utilization.gpu,memory.used',
                                    '--format=csv,noheader,nounits'], text=True, timeout=30)
    busy = set(subprocess.check_output(['nvidia-smi', '--query-compute-apps=gpu_uuid', '--format=csv,noheader'],
                                       text=True, timeout=30).split())
    gpus = []
    for row in rows.strip().splitlines():
        index, uuid, name, util, used = [v.strip() for v in row.split(',')]
        gpus.append({'index': index, 'uuid': uuid, 'name': name, 'utilization_percent': int(util),
                     'memory_used_mib': int(used), 'compute_processes': uuid in busy})
    return gpus


def bind_gpu(gpu):
    """Resolve an index or UUID to one idle GPU ('auto' takes the first idle one).

    Idle: no compute process, utilization <= 10 % and < 1 GiB in use. PCVE_ALLOW_SHARED_GPU=1 accepts a busy
    GPU (for example one already held by your own job)."""
    gpus = _gpus()
    shared = os.environ.get('PCVE_ALLOW_SHARED_GPU') == '1'
    idle = [g for g in gpus if shared or (not g['compute_processes'] and g['utilization_percent'] <= 10
                                          and g['memory_used_mib'] < 1024)]
    if gpu in (None, '', 'auto'):
        if not idle:
            raise RuntimeError('No idle GPU on this host; pass --gpu once one is free')
        return idle[0]
    match = [g for g in gpus if str(gpu) in (g['index'], g['uuid'])]
    if len(match) != 1:
        raise RuntimeError(f'Unknown GPU {gpu!r}')
    if match[0] not in idle:
        raise RuntimeError(f'GPU {gpu} is busy: {match[0]}')
    return match[0]


def launch(command, gpu=None, threads=8, cpu=False):
    """Run one command; GPU jobs are bound to one checked-idle GPU by UUID, CPU jobs hide CUDA."""
    if sys.platform != 'linux':
        raise RuntimeError('Blender replay runs on a Linux host')
    env = dict(os.environ, OMP_NUM_THREADS=str(threads))
    command = [str(c) for c in command]
    receipt = {'host': socket.gethostname(), 'command': command, 'started_utc': stamp(), 'device': 'CPU' if cpu else 'GPU'}
    if cpu:
        env['CUDA_VISIBLE_DEVICES'] = ''
        env['PCVE_CPU_RENDER_THREADS'] = str(threads)
    else:
        chosen = bind_gpu(gpu)
        env['CUDA_VISIBLE_DEVICES'] = chosen['uuid']
        env['PCVE_GPU_POLICY_PASSED'] = '1'
        receipt['gpu'] = chosen
    env.setdefault('PCVE_WORKER_IP', socket.gethostname())
    record = RUNTIME / 'launches' / f"{receipt['started_utc']}_{os.getpid()}.json"
    try:
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    except OSError:
        pass  # a render host without the repository runtime folder
    print(json.dumps({'launch': receipt}), flush=True)
    return subprocess.run(command, env=env).returncode
