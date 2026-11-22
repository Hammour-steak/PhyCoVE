"""GPU job launcher shared by the scenes' tools/worker_run.py: current GPU/process preflight, a per-GPU lease and
UUID binding.

A scene's tools/worker_run.py calls main() with its own path, its scene ID (for the shared GPU policy,
scripts/pcve_gpu_policy.py), its job folder and the free GPU memory a job needs. A launch writes
<work>/<runs>/<name>/{launch.json,stdout.log,allocation_ready.json,exit.json}; lease locks are
<work>/gpu_leases/<GPU UUID>.lock. The command runs under a holder process (the scene's worker_run.py --holder)
that keeps a CUDA context open on the GPU through CPU gaps between solver and render stages.
"""
from pathlib import Path
import argparse, ctypes, json, os, socket, subprocess, sys, time

from pcve_gpu_policy import require_gpu as _pcve_require_gpu, rank_uuids as _pcve_rank_gpus
from pcve_gpu_reservations import reservations


def hold_run(path, case_id, min_free_mib):
    """Retain this job's allocation through CPU gaps between solver/render stages."""
    receipt=json.loads(path.read_text());gpu=receipt['gpu_uuid'];run=path.parent
    _pcve_require_gpu(gpu, case_id=case_id)
    status=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-gpu=memory.used,utilization.gpu,memory.free','--format=csv,noheader,nounits'],text=True).strip().split(',')
    active=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader'],text=True)
    if int(status[0])>=100 or int(status[1])>3 or int(status[2])<min_free_mib or gpu in active:
        raise RuntimeError('GPU became occupied before context initialization; retry the queue')
    pci=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-gpu=pci.bus_id','--format=csv,noheader'],text=True).strip()
    driver=ctypes.CDLL('libcuda.so.1')
    def check(code):
        if code:raise RuntimeError('CUDA allocation context failed: '+str(code))
    check(driver.cuInit(0));device=ctypes.c_int();context=ctypes.c_void_p();allocation=ctypes.c_uint64()
    driver.cuDeviceGetByPCIBusId.argtypes=[ctypes.POINTER(ctypes.c_int),ctypes.c_char_p]
    check(driver.cuDeviceGetByPCIBusId(ctypes.byref(device),pci.encode()))
    driver.cuCtxCreate_v2.argtypes=[ctypes.POINTER(ctypes.c_void_p),ctypes.c_uint,ctypes.c_int]
    check(driver.cuCtxCreate_v2(ctypes.byref(context),0,device))
    driver.cuMemAlloc_v2.argtypes=[ctypes.POINTER(ctypes.c_uint64),ctypes.c_size_t]
    check(driver.cuMemAlloc_v2(ctypes.byref(allocation),1024*1024))
    (run/'allocation_ready.json').write_text(json.dumps(dict(pid=os.getpid(),gpu_uuid=gpu,pci_bus_id=pci)),encoding='utf-8')
    child=subprocess.Popen(receipt['command']);code=child.wait()
    (run/'exit.json').write_text(json.dumps(dict(exit_code=code,finished_unix_s=time.time())),encoding='utf-8')
    driver.cuMemFree_v2.argtypes=[ctypes.c_uint64];driver.cuMemFree_v2(allocation)
    driver.cuCtxDestroy_v2.argtypes=[ctypes.c_void_p];driver.cuCtxDestroy_v2(context)
    raise SystemExit(code)


def main(script, case_id, work, runs='launches', min_free_mib=8192):
    """Launch the command after `--` on an idle GPU (--gpu UUID or auto); script is the scene's worker_run.py."""
    script=Path(script).resolve();work=Path(work)
    if len(sys.argv)==3 and sys.argv[1]=='--holder':return hold_run(Path(sys.argv[2]),case_id,min_free_mib)
    ap=argparse.ArgumentParser();ap.add_argument('--gpu',required=True);ap.add_argument('--name',required=True)
    ap.add_argument('--wait-idle',action='store_true')
    ap.add_argument('--wait',action='store_true')
    ap.add_argument('command',nargs=argparse.REMAINDER);a=ap.parse_args()
    import fcntl
    cmd=a.command[1:] if a.command and a.command[0]=='--' else a.command
    case_root=script.parents[1]
    run=work/runs/a.name
    if run.exists():raise FileExistsError('Existing job record: '+str(run))
    lease_dir=work/'gpu_leases';lease_dir.mkdir(parents=True,exist_ok=True)
    lease_fd=None
    requested=a.gpu
    for attempt in range(1440 if a.wait_idle else 1):
        inventory=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,name,memory.used,utilization.gpu,memory.total,memory.free,index','--format=csv,noheader,nounits'],text=True)
        processes=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader'],text=True)
        gpu_rows=[[v.strip() for v in row.split(',')] for row in inventory.splitlines()]
        bindings=reservations([(row[6],row[0]) for row in gpu_rows],exclude=(os.getpid(),os.getppid()))
        bound={record['gpu_uuid'] for record in bindings}
        choices=[]
        idle=[]
        for values in gpu_rows:
            if int(values[2])<100 and int(values[3])<=3 and int(values[5])>=min_free_mib and values[0] not in processes and values[0] not in bound:
                idle.append(values[0])
        for uuid in _pcve_rank_gpus(idle, case_id=case_id):
            values=next([v.strip() for v in row.split(',')] for row in inventory.splitlines() if row.split(',')[0].strip()==uuid)
            if requested not in ['auto',uuid]:continue
            if int(values[2])<100 and int(values[3])<=3 and uuid not in processes:
                candidate_fd=os.open(str(lease_dir/(uuid+'.lock')),os.O_CREAT|os.O_RDWR,0o600)
                try:fcntl.flock(candidate_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:os.close(candidate_fd);continue
                lease_fd=candidate_fd;choices.append(uuid);break
        if choices:a.gpu=choices[0];break
        if not a.wait_idle:raise RuntimeError('Selected GPU is occupied; no other job was changed')
        if attempt%12==0:print('Waiting for a fully idle GPU',flush=True)
        time.sleep(5)
    else:raise RuntimeError('Idle GPU wait budget exhausted')
    policy_decision=_pcve_require_gpu(a.gpu, case_id=case_id)
    run.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy();env['CUDA_VISIBLE_DEVICES']=a.gpu;env.setdefault('OMP_NUM_THREADS','8');env.setdefault('OPENBLAS_NUM_THREADS','1')
    repo=case_root.parents[2]
    paths = [str(repo/'scripts'),str(case_root/'physics')]
    if env.get('PYTHONPATH'):
        paths.append(env['PYTHONPATH'])
    env['PYTHONPATH']=os.pathsep.join(paths)
    receipt=dict(host=socket.gethostname(),gpu_uuid=a.gpu,gpu_policy=policy_decision,preflight_inventory=inventory,preflight_processes=processes,
                 preflight_gpu_bindings=bindings,
                 command=cmd,started_unix_s=time.time())
    (run/'launch.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    log=(run/'stdout.log').open('w')
    process=subprocess.Popen([sys.executable,str(script),'--holder',str(run/'launch.json')],
        env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,pass_fds=(lease_fd,))
    receipt['allocation_pid']=process.pid
    for _ in range(100):
        if (run/'allocation_ready.json').exists():break
        if process.poll() is not None:raise RuntimeError('Allocation context failed; see '+str(run/'stdout.log'))
        time.sleep(.1)
    else:raise RuntimeError('Allocation context initialization timeout')
    (run/'launch.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    os.close(lease_fd)
    print(json.dumps(receipt,indent=2))
    if a.wait:raise SystemExit(process.wait())
