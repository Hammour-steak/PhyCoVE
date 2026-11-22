"""Launch, Blender runtime and output paths of the steel_ball_tensioned_membrane entries."""
from pathlib import Path
import datetime
import os
import subprocess
import sys

from pcve_assets import blender

CASE=Path(__file__).resolve().parent
SCRIPTS=CASE.parents[1]
# Accepted delivery (accepted_case.json, delivery/, outputs/): a record, not registered in assets.json.
DATA=SCRIPTS.parent/'renders/steel_ball_tensioned_membrane'
# Every reproduction output (solves, renders, launch records) goes below this root, outside scripts/.
WORK=SCRIPTS.parent/'renders/steel_ball_tensioned_membrane'


def worker_only():
    """The native solve and the Blender replay run on a Linux GPU host."""
    if sys.platform!='linux':
        raise RuntimeError('Run the native solve and the Blender replay on a Linux GPU host')


def output_path(value):
    target=value.expanduser().resolve()
    if WORK.resolve() not in target.parents:
        raise ValueError(f'Reproduction output must stay under {WORK}')
    return target


def blender_runtime(value):
    pinned=SCRIPTS.parent/'tools/blender-4.3.2-linux-x64/blender'
    return value or (pinned if pinned.is_file() else blender())


def launch(command,gpu,threads,env=None):
    worker_only()
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    launcher=[sys.executable,'-B',str(CASE/'tools/worker_run.py'),'--gpu',gpu,'--name',f'membrane_{stamp}','--wait','--',*map(str,command)]
    payload=dict(os.environ if env is None else env,OMP_NUM_THREADS=str(threads))
    subprocess.run(launcher,env=payload,check=True)
