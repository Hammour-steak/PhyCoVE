"""Partition remaining frames of one native scene across currently empty GPUs."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
import os
from pathlib import Path
import subprocess
import time
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import blender
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('case',type=Path);a=p.parse_args();case=a.case.resolve()
query=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
gpus=[dict(zip(('index','memory_mib','utilization_percent'),map(int,r.split(',')))) for r in query.strip().splitlines()]
free=[g['index'] for g in gpus if g['memory_mib']<200 and g['utilization_percent']==0][:3]
if not free:raise RuntimeError('No empty GPU available')
frames=[f for f in range(1,97) if not (case/f'frames/frame_{f:04d}.png').exists()]
original=[f for f in range(1,97) if f not in frames]
chunks=[frames[i::len(free)] for i in range(len(free))]
started=time.monotonic()
def run(i,gpu,chunk):
    if not chunk:return
    q=subprocess.check_output(['nvidia-smi',f'--id={gpu}','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
    memory,util=map(int,q.strip().split(','))
    if memory>=200 or util:raise RuntimeError(f'GPU {gpu} became occupied')
    env=os.environ.copy();env.update(CUDA_VISIBLE_DEVICES=str(gpu),OMP_NUM_THREADS='16')
    command=[str(blender()),'-b',str(case/'scene.blend'),'-t','16','--python-exit-code','1','--python',str(HERE/'render_tea_edit.py'),'--',str(case),'--frames',*map(str,chunk),'--report-tag',f'chunk_{i}']
    print(json.dumps({'chunk':i,'gpu':gpu,'frames':len(chunk),'started':True}),flush=True)
    with open(case/f'render_chunk_{i}.log','w') as log:subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    (case/f'render_chunk_{i}_execution.json').write_text(json.dumps({'command':command,'gpu':gpu,'gpus_at_dispatch':gpus},indent=2)+'\n')
    print(json.dumps({'chunk':i,'complete':True}),flush=True)
with ThreadPoolExecutor(max_workers=len(free)) as executor:
    for job in as_completed([executor.submit(run,i,gpu,chunk) for i,(gpu,chunk) in enumerate(zip(free,chunks))]):job.result()
times={}
for i in range(len(free)):
    if chunks[i]:times.update(json.loads((case/f'render_chunk_{i}.json').read_text())['frames'])
assert all((case/f'frames/frame_{f:04d}.png').exists() for f in range(1,97))
result={'frames':times,'reused_same_quality_frames':original,'render_seconds':time.monotonic()-started,
        'samples':128,'width':1280,'height':720,'fps':24,'device':'GPU','source_and_cache_preserved':True,'parallel_chunks':len(free)}
(case/'render_all.json').write_text(json.dumps(result,indent=2)+'\n')
print('ALL96_COMPLETE',time.monotonic()-started,flush=True)
