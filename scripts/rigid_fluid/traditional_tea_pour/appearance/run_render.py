"""Native preparation/render launcher; reserve only currently empty GPUs."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import queue
import subprocess
import time
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import blender
HERE=Path(__file__).resolve().parent
BLENDER=str(blender())
SCENE=HERE.parents[3]/'renders/pcve_suites/pcve_traditional_tea_pour_suite/inputs/source/cases/environment_render/scene_environment_refined.blend'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('root',type=Path)
p.add_argument('--cases',nargs='+',default=['speed_2x','speed_0p5x','remove_tea','stop_flow_at_2s'])
p.add_argument('--frames',type=int,nargs='+')
p.add_argument('--prepare-only',action='store_true')
a=p.parse_args();root=a.root.resolve()
def prepare(name):
    case=root/name
    if (case/'scene_revision.json').exists():return
    started=time.monotonic()
    with open(case/'native_prepare.log','w') as log:
        subprocess.run([BLENDER,'-b',str(SCENE),'-t','8','--python-exit-code','1','--python',str(HERE/'prepare_tea_edit_native.py'),'--',str(case)],stdout=log,stderr=subprocess.STDOUT,check=True)
    print(json.dumps({'case':name,'native_seconds':time.monotonic()-started}),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
    for job in concurrent.futures.as_completed([executor.submit(prepare,name) for name in a.cases]):job.result()
if a.prepare_only:raise SystemExit(0)
if not a.frames:
    a.cases=[name for name in a.cases if not (root/name/'render_all.json').exists()]
    if not a.cases:raise SystemExit(0)
query=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
gpus=[dict(zip(('index','memory_mib','utilization_percent'),map(int,r.split(',')))) for r in query.strip().splitlines()]
free=[g['index'] for g in gpus if g['memory_mib']<200 and g['utilization_percent']==0]
workers=free[:3] or [None]
slots=queue.Queue()
for gpu in workers:slots.put(gpu)
def render(name):
    case=root/name;gpu=slots.get()
    try:
        env=os.environ.copy();env.update(OMP_NUM_THREADS='16')
        if gpu is not None:
            check=subprocess.check_output(['nvidia-smi',f'--id={gpu}','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
            memory,util=map(int,check.strip().split(','))
            if memory>=200 or util:raise RuntimeError(f'GPU {gpu} became occupied')
            env['CUDA_VISIBLE_DEVICES']=str(gpu)
        command=[BLENDER,'-b',str(case/'scene.blend'),'-t','16','--python-exit-code','1','--python',str(HERE/'render_tea_edit.py'),'--',str(case),'--device','GPU' if gpu is not None else 'CPU']
        if a.frames:command+=['--frames',*map(str,a.frames)]
        tag='probe' if a.frames else 'all'
        started=time.monotonic();print(json.dumps({'case':name,'render_started':True,'gpu':gpu}),flush=True)
        with open(case/f'render_{tag}.log','w') as log:subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        (case/f'render_{tag}_execution.json').write_text(json.dumps({'command':command,'gpu':gpu,'seconds':time.monotonic()-started,'gpus_at_dispatch':gpus},indent=2)+'\n')
        print(json.dumps({'case':name,'render_done':True,'seconds':time.monotonic()-started}),flush=True)
    finally:slots.put(gpu)
with concurrent.futures.ThreadPoolExecutor(max_workers=len(workers)) as executor:
    for job in concurrent.futures.as_completed([executor.submit(render,name) for name in a.cases]):job.result()
