"""Pool-worker GPU lease, fresh hardware checks, strict policy and provenance."""
from pathlib import Path
import argparse, csv, datetime, fcntl, hashlib, io, json, os, socket, subprocess, sys

HERE=Path(__file__).resolve().parent
SCENE=HERE.parent                      # scripts are given relative to the scene folder, e.g. physics/simulate.py
ROOT=SCENE.parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(SCENE/'physics')]
from common import RUNTIME,WORK
from pcve_gpu_policy import rank_uuids, require_gpu

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True)
    ap.add_argument('--tool',choices=['sim','blender','cpu-blender','cpu-native','python'],required=True)
    ap.add_argument('--gpu',default='auto');ap.add_argument('command',nargs=argparse.REMAINDER)
    ap.add_argument('--blender-bin',type=Path);ap.add_argument('--threads',type=int,default=6);a=ap.parse_args()
    host=socket.gethostname().split('.')[0]
    assert os.name!='nt', 'Linux workers only'
    work=WORK/'receipts';work.mkdir(parents=True,exist_ok=True)
    log=work/(a.name+'.log');receipt=work/(a.name+'_launch.json')
    if receipt.exists():raise FileExistsError('Fresh job name required')
    command=a.command[1:] if a.command and a.command[0]=='--' else a.command
    locks=[];gpu='';policy=None;state='';procs=''
    if a.tool in ['sim','blender']:
        procs=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_memory',
                                      '--format=csv,noheader'],text=True,timeout=15)
        raw=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,name,memory.total,memory.free,memory.used,utilization.gpu',
                                    '--format=csv,noheader,nounits'],text=True,timeout=15)
        rows=list(csv.reader(io.StringIO(raw),skipinitialspace=True))
        idle=[r[0] for r in rows if r[0] not in procs and int(r[4])<768 and int(r[5])<=3]
        candidates=rank_uuids(idle,case_id='scarf_chair_slip')
        if a.gpu!='auto':candidates=[x for x in candidates if x==a.gpu]
        for uuid in candidates:
            acquired=[]
            try:
                for folder in ['.gpu_leases','tools/pcve_gpu_leases']:
                    directory=ROOT/folder;directory.mkdir(exist_ok=True)
                    f=(directory/(uuid+'.lock')).open('a+')
                    acquired.append(f);fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
                gpu=uuid;locks=acquired;break
            except BlockingIOError:
                for f in acquired:f.close()
        if not gpu:raise RuntimeError('No unlocked idle lower-memory GPU; retry later')
        policy=require_gpu(gpu,case_id='scarf_chair_slip')
        procs=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader'],text=True)
        state=subprocess.check_output(['nvidia-smi','--id='+gpu,'--query-gpu=uuid,name,memory.total,memory.free,memory.used,utilization.gpu,driver_version','--format=csv,noheader,nounits'],text=True).strip()
        row=next(csv.reader([state],skipinitialspace=True))
        if gpu in procs or int(row[4])>=768 or int(row[5])>3:raise RuntimeError('GPU became busy')
    env=dict(os.environ,CUDA_VISIBLE_DEVICES=gpu,OMP_NUM_THREADS=str(a.threads),OPENBLAS_NUM_THREADS='1',
             PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
    if a.tool in ['sim','cpu-native']:
        runtime=RUNTIME  # CPython 3.10 (python/), deps/ and tools/ffmpeg-linux staged on the pool worker
        py=runtime/'python/bin/python3.10'
        deps=[ROOT/'tools/ipc_probe_deps',ROOT/'tools/manifold3d_deps',runtime/'deps']
        selected=RUNTIME/'solver/active_solver_path.txt'
        if selected.is_file():
            solver=Path(selected.read_text().strip()).resolve()
            if not solver.is_relative_to((RUNTIME/'solver').resolve())or not(solver/'uipc/__init__.py').is_file():raise RuntimeError('Invalid case-isolated solver path')
            deps.insert(0,solver)
        env.update(PYTHONHOME=str(runtime/'python'),LD_LIBRARY_PATH=str(runtime/'python/lib')+':'+env.get('LD_LIBRARY_PATH',''),
                   PYTHONPATH=':'.join(map(str,deps)))
        cmd=[str(py),'-B',str(SCENE/command[0]),*command[1:]]
    elif a.tool in ['blender','cpu-blender']:
        cmd=[str(a.blender_bin or ROOT/'tools/blender-5.1.0-linux-x64/blender'),'-b','-t',str(a.threads),'--factory-startup',
             '--disable-autoexec','--python-exit-code','1','--python',str(SCENE/command[0]),'--',*command[1:]]
    else:cmd=['python3','-B',str(SCENE/command[0]),*command[1:]]
    rec=dict(worker_host=host,
             gpu_uuid=gpu,gpu_policy=policy,gpu_state_before=state,compute_processes_before=procs,command=cmd,
             time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),launcher_pid=os.getpid())
    receipt.write_text(json.dumps(rec,indent=2)+'\n')
    with log.open('w')as f:result=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
    rec.update(exit_code=result.returncode,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    receipt.write_text(json.dumps(rec,indent=2)+'\n')
    for f in locks:f.close()
    raise SystemExit(result.returncode)

if __name__=='__main__':main()
