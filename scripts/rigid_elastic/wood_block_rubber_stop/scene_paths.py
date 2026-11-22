"""Scene paths, output rules and single-GPU launch for the native solver and renderer."""
from pathlib import Path
import datetime
import json
import os
import socket
import subprocess
import sys

from pcve_assets import asset, blender

SCENE='wood_block_rubber_stop'
CASE=Path(__file__).resolve().parent
SCRIPTS=CASE.parents[1]
REPO=SCRIPTS.parent
# Current native 4 s caches (simulation.npz + simulation_config.json per case).
CACHES=asset(f'scenes/{SCENE}/native_cache')
# Launch receipts and the encoder copy used inside Blender.
RUNTIME=REPO/'.runtime'/SCENE
SUITE_KEY=f'pcve_{SCENE}_suite'


def require_linux():
    if sys.platform!='linux':
        raise RuntimeError('GPU simulation and Blender replay run on a Linux CUDA host, never local Windows/WSL')


def output_path(value):
    target=Path(value).expanduser().resolve()
    if target==SCRIPTS.resolve() or SCRIPTS.resolve() in target.parents:
        raise ValueError('scripts/ holds code only; write outputs elsewhere, for example under renders/')
    return target


def blender_runtime(value):
    pinned=REPO/'tools/blender-4.3.2-linux-x64/blender'
    return value or (pinned if pinned.is_file() else blender())


def python_runtime(value):
    """Python 3.10 with numpy/scipy/trimesh; libuipc itself comes from tools/ipc_probe_deps."""
    pinned=REPO/'.venv-rigid-elastic/bin/python3.10'
    return value or (pinned if pinned.is_file() else None)


def _gpus():
    rows=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,name,utilization.gpu,memory.used',
                                  '--format=csv,noheader,nounits'],text=True,timeout=30)
    busy=set(subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid','--format=csv,noheader'],
                                     text=True,timeout=30).split())
    gpus=[]
    for row in rows.strip().splitlines():
        index,uuid,name,util,used=[v.strip() for v in row.split(',')]
        gpus.append({'index':index,'uuid':uuid,'name':name,'utilization_percent':int(util),
                     'memory_used_mib':int(used),'compute_processes':uuid in busy})
    return gpus


def bind_gpu(gpu):
    """Resolve an index or UUID to one idle GPU ('auto' takes the first idle one).

    Idle means no compute process, utilization <= 10 % and < 1 GiB in use. Set
    PCVE_ALLOW_SHARED_GPU=1 to place a further job of your own on a GPU you hold.
    """
    gpus=_gpus()
    shared=os.environ.get('PCVE_ALLOW_SHARED_GPU')=='1'
    idle=[g for g in gpus if shared or (not g['compute_processes'] and g['utilization_percent']<=10
                                         and g['memory_used_mib']<1024)]
    if gpu in (None,'','auto'):
        if not idle:
            raise RuntimeError('No idle GPU on this host; pass --gpu once one is free')
        return idle[0]
    match=[g for g in gpus if str(gpu) in (g['index'],g['uuid'])]
    if len(match)!=1:
        raise RuntimeError(f'Unknown GPU {gpu!r}')
    if match[0] not in idle:
        raise RuntimeError(f'GPU {gpu} is busy: {match[0]}')
    return match[0]


def launch(command,gpu,threads,env=None):
    require_linux()
    payload=dict(os.environ if env is None else env,OMP_NUM_THREADS=str(threads))
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    command=[str(c) for c in command]
    chosen=bind_gpu(gpu)
    payload['CUDA_VISIBLE_DEVICES']=chosen['uuid']
    receipt={'host':socket.gethostname(),'gpu':chosen,'command':command,'started_utc':stamp}
    record=RUNTIME/'launches'/f'{stamp}.json'
    record.parent.mkdir(parents=True,exist_ok=True)
    record.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'launch_receipt':str(record),'gpu':chosen}),flush=True)
    subprocess.run(command,env=payload,check=True)
