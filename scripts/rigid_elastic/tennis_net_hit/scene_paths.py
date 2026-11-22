"""Output, runtime and pool-launch paths for the tennis_net_hit entries."""
from pathlib import Path
import datetime
import os
import subprocess
import sys

from pcve_assets import blender

CASE=Path(__file__).resolve().parent
SCRIPTS=CASE.parents[1]
REPO=SCRIPTS.parent
# Every reproduction output (solves, renders, packages) goes below this root,
# outside scripts/. PCVE_TENNIS_WORK moves it; appearance/render.py reads the same variable.
WORK=Path(os.environ.get('PCVE_TENNIS_WORK',str(REPO/'renders/tennis_net_hit')))


def worker_only():
    """The native solve loads the frozen Linux contact libraries (.so) and runs on the CPU."""
    if sys.platform!='linux':
        raise RuntimeError('The native solve runs on a Linux host (it loads the frozen .so contact libraries)')


def output_path(value):
    target=Path(value).expanduser().resolve()
    if WORK.resolve() not in target.parents:
        raise ValueError(f'Reproduction output must stay under {WORK} (set PCVE_TENNIS_WORK to move it)')
    return target


def blender_runtime(value):
    pinned=REPO/'tools/blender-4.3.2-linux-x64/blender'
    return value or (pinned if pinned.is_file() else blender())


def launch(command,gpu,threads,env=None):
    """Launch with GPU preflight, lease and UUID binding (tools/worker_run.py)."""
    worker_only()
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    launcher=[sys.executable,'-B',str(CASE/'tools/worker_run.py'),'--gpu',gpu,'--name',f'launch_{stamp}','--wait','--',*map(str,command)]
    payload=dict(os.environ if env is None else env,OMP_NUM_THREADS=str(threads))
    subprocess.run(launcher,env=payload,check=True)
