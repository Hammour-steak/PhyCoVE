"""Render isolated cases on GPU candidates only when their memory and compute are idle."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import time
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import blender

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]

def main():
    p=argparse.ArgumentParser();p.add_argument('--out-root',type=Path,required=True);p.add_argument('--gpus',nargs='+',required=True)
    p.add_argument('--appearance-json',type=Path)
    p.add_argument('--cases',nargs='+',choices=['source','edit_heavy_left','edit_low_restitution','edit_remove_right'],default=['source','edit_heavy_left','edit_low_restitution','edit_remove_right'])
    p.add_argument('--synchronized-cache',action='store_true')
    p.add_argument('--blender',type=Path,default=blender());a=p.parse_args()
    root=a.out_root.resolve();pending=list(a.cases);running={};rows=[]
    for case in pending:assert json.loads((root/'cases'/case/'physics_validation.json').read_text())['accepted']
    begin=time.perf_counter();resource_before=None
    try:
        while pending or running:
            for gpu,(proc,log,case,started) in list(running.items()):
                code=proc.poll()
                if code is not None:
                    log.close();del running[gpu]
                    if code:raise RuntimeError(f'{case} Blender exit {code}; see case render.log')
                    rows.append({'case_id':case,'gpu':gpu,'wall_sec':time.perf_counter()-started})
                    print(case,'completed on GPU',gpu,flush=True)
            if pending:
                resource=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
                if resource_before is None:resource_before=resource
                used={row.split(',')[0].strip():[int(v.strip()) for v in row.split(',')[1:]] for row in resource.strip().splitlines()}
                for gpu in a.gpus:
                    if not pending:break
                    if gpu in running or used[gpu][0]>=200 or used[gpu][1]>=10:continue
                    case=pending.pop(0);folder=root/'cases'/case;env={**os.environ,'CUDA_VISIBLE_DEVICES':gpu,'OMP_NUM_THREADS':'4'}
                    cmd=[str(a.blender),'-b','-t','4','--python-exit-code','1','--python',str(HERE/'render_twin_ramp_collision.py'),'--',
                        '--physics-json',str(folder/'physics_transforms.json'),'--out-dir',str(folder),'--mode','animation','--skip-existing']
                    if a.appearance_json:cmd.extend(['--appearance-json',str(a.appearance_json.resolve())])
                    if a.synchronized_cache:cmd.append('--synchronized-cache')
                    log=(folder/'render.log').open('w');proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
                    running[gpu]=(proc,log,case,time.perf_counter());print(case,'started on idle GPU',gpu,flush=True)
            (root/'render_queue_status.json').write_text(json.dumps({'pending':pending,'running':{g:v[2] for g,v in running.items()},'completed':rows},indent=2)+'\n')
            if pending or running:time.sleep(2)
    finally:
        for proc,log,case,started in running.values():
            proc.wait();log.close()
    (root/'render_queue_report.json').write_text(json.dumps({'wall_sec':time.perf_counter()-begin,'resource_before':resource_before,'cases':rows},indent=2)+'\n')

if __name__=='__main__':main()
