"""Run all four isolated existence/speed edits with unchanged DFSPH numerics."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import time
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import REPO

HERE=Path(__file__).resolve().parent
PYTHON=str(REPO / '.venv-genesis-mpm-sph/bin/python')
# The accepted source run. The timed stop continues its state after frame 48 instead of re-solving the prefix.
SOURCE_RUN=REPO/'renders/pcve_suites/pcve_traditional_tea_pour_suite/inputs/source/cases/source_run'
CASES={'speed_2x':['--speed-scale','2'], 'speed_0p5x':['--speed-scale','.5'],
       'stop_flow_at_2s':['--stop-flow-at-sec','2','--resume-from',str(SOURCE_RUN),'--resume-frame','49'], 'remove_tea':['--delete-at-sec','0']}
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('root',type=Path)
p.add_argument('--cases',nargs='+',choices=list(CASES),default=list(CASES))
a=p.parse_args()
root=a.root.resolve()
pending={n:flags for n,flags in CASES.items() if n in a.cases and not ((root/n/'simulation_result.json').exists() and (root/n/'surface_audit.json').exists())}
query=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
gpus=[dict(zip(('index','memory_mib','utilization_percent'),map(int,r.split(',')))) for r in query.strip().splitlines()]
free=[g['index'] for g in gpus if g['memory_mib']<200 and g['utilization_percent']==0]
if not free and pending: raise RuntimeError('No empty GPU available for the validated CUDA solve')
slots=queue.Queue()
for gpu in free[:3]: slots.put(gpu)
(root/'compute_resources.json').write_text(json.dumps({'gpus':gpus,'selected':free[:3]},indent=2)+'\n')
def run_case(name,extra):
    case=root/name
    gpu=slots.get()
    try:
        # Recheck before taking a GPU originally idle at launch.
        env=os.environ.copy();env.update(OMP_NUM_THREADS='8',RAYON_NUM_THREADS='8',QD_NUM_THREADS='16')
        if gpu is not None:
            data=subprocess.check_output(['nvidia-smi',f'--id={gpu}','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
            memory,util=map(int,data.strip().split(','))
            if memory>=200 or util!=0: raise RuntimeError(f'GPU {gpu} became occupied')
            env['CUDA_VISIBLE_DEVICES']=str(gpu)
        device='cuda' if gpu is not None else 'cpu'
        stages=[('simulation',[PYTHON,str(HERE/'simulate_tea_edits.py'),str(case),'--device',device,'--max-density-error','.005','--max-divergence-error','.05','--domain-half','2.0' if name=='speed_2x' else '.24','--surface-friction','1','--gamma','.0002','--coaster','--support-contact-skin','0.0005208333472364128',*extra],case/'simulation_result.json'),
                ('surface',[PYTHON,str(HERE/'surface_tea_dynamics.py'),str(case)],case/'surface_audit.json')]
        for stage,command,marker in stages:
            if marker.exists(): continue
            if stage=='surface' and '--resume-frame' in extra:
                # The copied particle prefix keeps the source's own surfaces (checked byte for byte by validate_tea_edit.py).
                (case/'surfaces').mkdir(exist_ok=True)
                for f in range(1,int(extra[extra.index('--resume-frame')+1])):
                    target=case/'surfaces'/f'frame_{f:04d}.npz'
                    if not target.exists(): shutil.copy2(SOURCE_RUN/'surfaces'/target.name,target)
            started=time.monotonic()
            print(json.dumps({'case':name,'stage':stage,'gpu':gpu,'started':True}),flush=True)
            with open(case/f'{stage}.log','w') as log:
                subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
            (case/f'{stage}_execution.json').write_text(json.dumps({'command':command,'gpu':gpu,'seconds':time.monotonic()-started},indent=2)+'\n')
            assert marker.exists()
            print(json.dumps({'case':name,'stage':stage,'seconds':time.monotonic()-started,'completed':True}),flush=True)
    finally: slots.put(gpu)
with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(3,len(free)))) as executor:
    jobs=[executor.submit(run_case,name,extra) for name,extra in pending.items()]
    for job in concurrent.futures.as_completed(jobs): job.result()
print('ALL_COMPUTE_DONE',flush=True)
