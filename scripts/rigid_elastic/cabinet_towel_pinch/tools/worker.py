"""Pool-worker launcher: fresh idle checks, GPU policy, cooperative file leases.

The script argument is relative to the scene folder (physics/simulate.py, appearance/render_replay.py).
Receipts go to renders/cabinet_towel_pinch/rebuild/provenance/<name>/.
"""
from pathlib import Path
import argparse, csv, io, json, os, socket, subprocess, sys, time, fcntl
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'physics'))
from common import HERE,SCENE_DIR,WORK,RUNTIME,REPO,CASE,save,sha,cpu_runtime
sys.path.insert(0,str(REPO/'scripts'))
from pcve_gpu_policy import require_gpu,rank_uuids

def query(fields,apps=False):
    return list(csv.reader(io.StringIO(subprocess.check_output(['nvidia-smi',
        '--query-'+('compute-apps'if apps else'gpu')+'='+fields,'--format=csv,noheader,nounits'],text=True,timeout=15)),skipinitialspace=True))

def preparing(uuid):
    bound=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit()or int(proc.name)==os.getpid():continue
        try:
            if proc.stat().st_uid!=os.getuid():continue
            if ('CUDA_VISIBLE_DEVICES='+uuid).encode()in (proc/'environ').read_bytes().split(b'\0'):bound.append(int(proc.name))
        except (OSError,PermissionError):pass
    return bound

def acquire(a,out):
    while True:
        rows=query('uuid,name,memory.total,memory.used,utilization.gpu,driver_version');apps=query('gpu_uuid,pid,process_name,used_gpu_memory',True)
        idle=[r[0]for r in rows if int(r[3])<600 and int(r[4])<3 and not any(p[0]==r[0]for p in apps)]
        ranked=rank_uuids(idle,case_id=CASE)
        if a.gpu!='auto':ranked=[u for u in ranked if u==a.gpu]
        for uuid in ranked:
            handles=[]
            try:
                for folder in [REPO/'.gpu_leases',REPO/'tools/pcve_gpu_leases']:
                    folder.mkdir(exist_ok=True,parents=True);f=(folder/(uuid+'.lock')).open('a+')
                    fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);handles.append(f)
                if preparing(uuid):
                    for f in handles:f.close()
                    continue
                apps2=query('gpu_uuid,pid',True)
                if any(p[0]==uuid for p in apps2):
                    for f in handles:f.close()
                    continue
                policy= require_gpu(uuid,case_id=CASE)
                final_apps=query('gpu_uuid,pid',True)
                final_gpu=next(r for r in query('uuid,memory.used,utilization.gpu')if r[0]==uuid)
                if any(p[0]==uuid for p in final_apps)or int(final_gpu[1])>=600 or int(final_gpu[2])>=3:
                    for f in handles:f.close()
                    continue
                return uuid,handles,rows,apps,policy
            except BlockingIOError:
                for f in handles:f.close()
        save(out/'queue.json',dict(status='waiting_for_idle_3090',inventory=rows,compute_apps=apps,time_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
        print('WAITING_FOR_IDLE_3090',flush=True);time.sleep(a.poll_seconds)

def main():
    a=argparse.ArgumentParser();a.add_argument('--name',required=True);a.add_argument('--gpu',default='auto')
    a.add_argument('--poll-seconds',type=float,default=5.);a.add_argument('--resume-queued',action='store_true')
    a.add_argument('--blender-version',choices=['4.3.2','5.1.0'],default='4.3.2')
    a.add_argument('--tool',choices=['python','blender'],required=True);a.add_argument('args',nargs=argparse.REMAINDER)
    a.add_argument('--blender-bin',type=Path);a.add_argument('--threads',type=int,default=4);a=a.parse_args()
    host=socket.gethostname().split('.')[0];assert os.name=='posix'
    assert 5<=a.poll_seconds<=60
    out=WORK/'provenance'/a.name
    if a.resume_queued:
        assert out.is_dir()and not(out/'launch.json').exists()and not(out/'completion.json').exists()
        assert json.loads((out/'queue_resume_authorization.json').read_text())['previous_cpu_worker_terminated']
    else:out.mkdir(parents=True,exist_ok=False)
    selected,lease_handles,rows,apps,policy=acquire(a,out)
    env=dict(os.environ,CUDA_VISIBLE_DEVICES=selected,PCVE_JOB_NAME=a.name,OMP_NUM_THREADS=str(a.threads),OPENBLAS_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
    args=a.args[1:]if a.args[:1]==['--']else a.args
    if a.tool=='python':
        runtime=cpu_runtime()
        env.update(PYTHONHOME=str(runtime/'python'),LD_LIBRARY_PATH=str(runtime/'python/lib')+':'+env.get('LD_LIBRARY_PATH',''),
            PYTHONPATH=':'.join(map(str,[RUNTIME/'uipc029',RUNTIME/'geometry_deps',REPO/'tools/ipc_probe_deps',REPO/'tools/manifold3d_deps',runtime/'deps',HERE,REPO/'scripts'])))
        cmd=[str(runtime/'python/bin/python3.10'),'-B',str(SCENE_DIR/args[0]),*args[1:]]
    else:
        for key in ['PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD']:env.pop(key,None)
        cmd=[str(a.blender_bin or REPO/('tools/blender-'+a.blender_version+'-linux-x64/blender')),'-b','-t',str(a.threads),'--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(SCENE_DIR/args[0]),'--',*args[1:]]
    receipt=dict(worker_host=host,
        gpu_uuid=selected,inventory=rows,compute_apps=apps,gpu_policy=policy,command=cmd,started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        local_blender=False)
    with (out/'run.log').open('wb') as stream:
        child=subprocess.Popen(cmd,env=env,stdout=stream,stderr=subprocess.STDOUT)
        receipt['pid']=child.pid;save(out/'launch.json',receipt)
        rc=child.wait()
    receipt.update(exit_code=rc,finished_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    save(out/'completion.json',receipt)
    raise SystemExit(rc)

if __name__=='__main__':main()
