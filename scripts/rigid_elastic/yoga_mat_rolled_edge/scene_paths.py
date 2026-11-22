"""Repository paths, output guard, Blender selection and the GPU job launcher of yoga_mat_rolled_edge."""
from pathlib import Path
import datetime
import json
import os
import subprocess
import sys

from pcve_assets import asset,blender

CASE=Path(__file__).resolve().parent
SCRIPTS=CASE.parents[1]
REPO=SCRIPTS.parent
SCENE='yoga_mat_rolled_edge'
SUITE_NAME=f'pcve_{SCENE}_suite'
# Default parent of reproduction outputs (simulations, renders, verify reports).
OUTPUT=REPO/'renders'/SCENE


def suite_dir():
    """Published video suite named by scene_manifest.json (canonical_suites)."""
    manifest=json.loads((CASE/'scene_manifest.json').read_text(encoding='utf-8'))
    return REPO/manifest['canonical_suites'][SUITE_NAME]['target']


def require_linux():
    """The libuipc CUDA solve and the Blender replay run on Linux."""
    if sys.platform!='linux':
        raise RuntimeError('Run the native solve and the Blender replay on Linux')


def output_path(value):
    """Reproduction output: never inside scripts/, the asset store or the published suite."""
    target=Path(value).expanduser().resolve()
    for protected in (SCRIPTS,asset(f'scenes/{SCENE}'),suite_dir()):
        protected=protected.resolve()
        if target==protected or protected in target.parents:
            raise ValueError(f'Reproduction output must stay outside {protected}: {target}')
    return target


def blender_runtime(value):
    pinned=REPO/'tools/blender-4.3.2-linux-x64/blender'
    return value or (pinned if pinned.is_file() else blender())


def launch(command,gpu,threads,env=None):
    require_linux()
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    launcher=[sys.executable,'-B',str(CASE/'tools/worker_run.py'),'--gpu',gpu,'--name',f'{SCENE}_{stamp}','--wait','--',*map(str,command)]
    payload=dict(os.environ if env is None else env,OMP_NUM_THREADS=str(threads))
    subprocess.run(launcher,env=payload,check=True)
