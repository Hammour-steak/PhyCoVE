"""Launch, delivery, suite, runtime and output paths for curtain_doraemon_drape."""
from pathlib import Path
import datetime
import json
import os
import subprocess
import sys

from pcve_assets import asset, blender

CASE=Path(__file__).resolve().parent
SCRIPTS=CASE.parents[1]
REPO=SCRIPTS.parent
SCENE_ID='curtain_doraemon_drape'
SUITE='pcve_curtain_doraemon_drape_suite'


def manifest():
    return json.loads((CASE/'scene_manifest.json').read_text(encoding='utf-8'))


def _in_repo(value):
    """A recorded path, re-rooted at this checkout when the repository is mounted elsewhere."""
    target=Path(value)
    if not target.is_absolute():
        return REPO/target
    if target.exists() or 'renders' not in target.parts:
        return target
    index=len(target.parts)-1-target.parts[::-1].index('renders')
    return REPO.joinpath(*target.parts[index:])


def accepted_delivery():
    """Accepted native delivery of the published videos: solver caches, audits, masks, GT sidecars and videos."""
    return _in_repo(manifest()['data']['accepted_delivery'])


def current_suite():
    """Published video suite, as named by scene_manifest.json canonical_suites."""
    return _in_repo(manifest()['canonical_suites'][SUITE]['target'])


DELIVERY=accepted_delivery()
RUNTIME=_in_repo(manifest()['data']['runtime'])


def require_linux():
    if sys.platform!='linux':
        raise RuntimeError('Solves and renders run on a Linux host with a CUDA GPU')


def output_path(value):
    target=value.expanduser().resolve()
    for protected in (SCRIPTS,DELIVERY,current_suite(),asset(f'scenes/{SCENE_ID}')):
        protected=protected.resolve()
        if target==protected or protected in target.parents:
            raise ValueError('Output must not be written into scripts/, the accepted delivery, '
                             'the published suite or the asset store: '+str(target))
    return target


def blender_runtime(value):
    pinned=REPO/'tools/blender-4.3.2-linux-x64/blender'
    return value or (pinned if pinned.is_file() else blender())


def launch(command,gpu,threads,env=None):
    """Run on the GPU named by --gpu-uuid (a GPU-... UUID or index the caller has already claimed); with the
    default 'auto', tools/worker_run.py picks an idle GPU (preflight, per-GPU lease, UUID binding)."""
    require_linux()
    payload=dict(os.environ if env is None else env,OMP_NUM_THREADS=str(threads))
    if str(gpu)!='auto':
        payload['CUDA_VISIBLE_DEVICES']=str(gpu)
        subprocess.run([str(part) for part in command],env=payload,check=True)
        return
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    launcher=[sys.executable,'-B',str(CASE/'tools/worker_run.py'),'--gpu',gpu,'--name',f'{SCENE_ID}_{stamp}','--wait','--',*map(str,command)]
    subprocess.run(launcher,env=payload,check=True)
