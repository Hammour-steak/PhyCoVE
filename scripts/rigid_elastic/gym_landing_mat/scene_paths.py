"""Launch, delivery, suite and output paths for gym_landing_mat."""
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
SCENE_ID='gym_landing_mat'
SUITE='pcve_gym_landing_mat_suite'
# Jobs launch through tools/worker_run.py (GPU policy, UUID binding, leases) unless the caller names a claimed GPU
# with --gpu-uuid; then they run directly on it.


def manifest():
    return json.loads((CASE/'scene_manifest.json').read_text(encoding='utf-8'))


def _in_repo(value):
    """A recorded absolute path, re-rooted at this checkout when the repository is mounted elsewhere."""
    target=Path(value)
    if not target.is_absolute():
        return REPO/target
    if target.exists() or 'renders' not in target.parts:
        return target
    index=len(target.parts)-1-target.parts[::-1].index('renders')
    return REPO.joinpath(*target.parts[index:])


def accepted_delivery():
    """Accepted native delivery (five cases plus the later Young's modulus x10 case): solver states, audits, reference renders."""
    return _in_repo(manifest()['data']['accepted_delivery'])


def current_suite():
    """Published video suite, as named by scene_manifest.json canonical_suites."""
    return _in_repo(manifest()['canonical_suites'][SUITE]['target'])


DELIVERY=accepted_delivery()
OUTPUT=REPO/'renders'/SCENE_ID/'rebuild'


def worker_only():
    if sys.platform!='linux':
        raise RuntimeError('Solves and renders run on Linux')


def output_path(value):
    target=value.expanduser().resolve()
    for protected in (DELIVERY,current_suite(),asset(f'scenes/{SCENE_ID}')):
        protected=protected.resolve()
        if target==protected or protected in target.parents:
            raise ValueError('Reproduction output must not be written into the accepted delivery, the published suite or the asset store: '+str(target))
    return target


def blender_runtime(value):
    pinned=SCRIPTS.parent/'tools/blender-4.3.2-linux-x64/blender'
    return value or (pinned if pinned.is_file() else blender())


def launch(command,gpu,threads,env=None):
    """Without a claimed GPU (--gpu-uuid auto) the command goes through tools/worker_run.py (UUID binding, leases);
    with --gpu-uuid (a GPU-... UUID the caller has already claimed) it runs directly on that GPU."""
    worker_only()
    payload=dict(os.environ if env is None else env,OMP_NUM_THREADS=str(threads))
    if str(gpu)!='auto':
        payload['CUDA_VISIBLE_DEVICES']=str(gpu)
        subprocess.run([str(part) for part in command],env=payload,check=True)
        return
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    launcher=[sys.executable,'-B',str(CASE/'tools/worker_run.py'),'--gpu',gpu,'--name',f'gym_landing_mat_{stamp}','--wait','--',*map(str,command)]
    subprocess.run(launcher,env=payload,check=True)
