"""Render only on currently idle GPUs (or, with --share-gpus, GPUs with enough free memory and low load); separate case files avoid manifest races."""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
_scene_sys.path.append(str(_ScenePath(__file__).resolve().parents[3]))
from pcve_assets import blender
from scene_config import CASES
from simulate_bowling import dump

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--out-root",type=Path,required=True);p.add_argument("--max-jobs",type=int,default=3);p.add_argument("--cases",nargs="+",choices=list(CASES),default=list(CASES))
    p.add_argument("--share-gpus",action="store_true",help="also launch on busy GPUs that have enough free memory and low utilization")
    p.add_argument("--min-free-mib",type=float,default=8192);p.add_argument("--max-util",type=float,default=30)
    a=p.parse_args();root=a.out_root.resolve();here=Path(__file__).resolve().parents[1]
    lock=(root/"render_queue.lock").open("w");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    queue=list(a.cases);running={};finished={};start=time.perf_counter();last_progress=0.
    while queue or running:
        for name,row in list(running.items()):
            status=row["process"].poll()
            if status is not None:
                row["log"].close();record={k:v for k,v in row.items() if k not in ["process","log","start"]}
                record.update(returncode=status,wall_sec=time.perf_counter()-row["start"]);dump(root/"cases"/name/"render_execution.json",record)
                finished[name]=record;del running[name];print(name,"complete" if status==0 else "FAILED",flush=True)
                if status:raise RuntimeError(f"Render failed for {name}; inspect case render.log")
        output=subprocess.check_output(["nvidia-smi","--query-gpu=index,uuid,utilization.gpu,memory.used,memory.total","--format=csv,noheader,nounits"],text=True)
        own={r["gpu_uuid"] for r in running.values()};free=[]
        for line in output.splitlines():
            index,uuid,util,memory,total=[x.strip() for x in line.split(",")];util,memory,total=float(util),float(memory),float(total)
            idle=util<=3 and memory<128;shared=a.share_gpus and total-memory>=a.min_free_mib and util<=a.max_util
            if uuid not in own and (idle or shared):free.append((not idle,util,memory,index,uuid))
        # Fully idle GPUs first, then the least loaded shared ones.
        free=[(index,uuid,shared) for shared,util,memory,index,uuid in sorted(free)]
        while queue and free and len(running)<a.max_jobs:
            name=queue[0];folder=root/"cases"/name;physics=folder/"physics_transforms.json"
            if not physics.is_file() or not (folder/"physics_validation.json").is_file():break
            validation=json.loads((folder/"physics_validation.json").read_text())
            if not validation["accepted"]:raise RuntimeError(f"Physics not accepted for {name}")
            queue.pop(0)
            index,uuid,shared=free.pop(0);env=os.environ.copy();env.update(CUDA_VISIBLE_DEVICES=uuid,OMP_NUM_THREADS="8",OPENBLAS_NUM_THREADS="1");temp=folder/"worker_tmp";temp.mkdir(exist_ok=True);env["TMPDIR"]=str(temp)
            command=[str(blender()),"--factory-startup","-b","-t","8","--python-exit-code","1","--python",str(here/"render_bowling.py"),"--","--physics-json",str(physics),"--out-dir",str(folder),"--mode","animation","--device","auto","--skip-existing"]
            log=(folder/"render.log").open("a");process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env,cwd=here.parents[2])
            running[name]={"process":process,"log":log,"start":time.perf_counter(),"gpu_index":index,"gpu_uuid":uuid,"gpu_shared":shared,"command":command}
            print("Started",name,"on","shared" if shared else "idle","GPU",index,flush=True)
        if time.perf_counter()-last_progress>20:
            progress={n:len(list((root/"cases"/n/"frames").glob("frame_*.png"))) for n in running}
            print("Frames",progress,"pending",queue,flush=True);last_progress=time.perf_counter()
        dump(root/"render_queue_status.json",{"running":{n:{"gpu_index":r["gpu_index"],"gpu_uuid":r["gpu_uuid"]} for n,r in running.items()},"pending":queue,"completed":finished,"elapsed_sec":time.perf_counter()-start})
        if queue or running:time.sleep(5)
    dump(root/"render_queue_report.json",{"wall_sec":time.perf_counter()-start,"cases":finished,"policy":(f"Idle GPUs (below 128 MiB, at most 3 percent utilization) first, then GPUs with at least {a.min_free_mib:g} MiB free and at most {a.max_util:g} percent utilization at launch" if a.share_gpus else "Only GPUs below 128 MiB and at most 3 percent utilization at launch")+"; no other processes stopped or changed"})

if __name__=="__main__":main()
