"""Job launch with current GPU/process preflight, a per-GPU lease and UUID binding."""
from pathlib import Path
import argparse, ctypes, json, os, socket, subprocess, sys, time

# Shared PCVE GPU allocation policy (scripts/pcve_gpu_policy.py)
import sys as _pcve_policy_sys
_pcve_policy_root = Path(__file__).resolve().parents[4]
_pcve_policy_sys.path.insert(0, str(_pcve_policy_root / 'scripts'))
from pcve_gpu_policy import require_gpu as _pcve_require_gpu, rank_uuids as _pcve_rank_gpus

def hold_run(path):
    """Retain this job's allocation through CPU gaps between solver/render stages."""
    receipt=json.loads(path.read_text());gpu=receipt['gpu_uuid'];run=path.parent
    _pcve_require_gpu(gpu, case_id='steel_ball_silicone_cup')
    status=subprocess.check_output(['nvidia-smi','-i',gpu,'--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip().split(',')
    active=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader'],text=True)
    if int(status[0])>=100 or int(status[1])>3 or gpu in active:
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

def main():
    if len(sys.argv)==3 and sys.argv[1]=='--holder':return hold_run(Path(sys.argv[2]))
    ap=argparse.ArgumentParser();ap.add_argument('--gpu',required=True);ap.add_argument('--name',required=True)
    ap.add_argument('--wait-idle',action='store_true')
    ap.add_argument('command',nargs=argparse.REMAINDER);a=ap.parse_args()
    import fcntl
    cmd=a.command[1:] if a.command and a.command[0]=='--' else a.command
    case_root=Path(__file__).resolve().parents[1]
    jobs=case_root.parents[2]/'renders/spring_scale_weight_drop'
    run=jobs/'launches'/a.name
    if run.exists():raise FileExistsError('Existing job record: '+str(run))
    lease_dir=jobs/'gpu_leases';lease_dir.mkdir(parents=True,exist_ok=True)
    lease_fd=None
    requested=a.gpu
    for attempt in range(1440 if a.wait_idle else 1):
        inventory=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,name,memory.used,utilization.gpu,memory.total,memory.free','--format=csv,noheader,nounits'],text=True)
        processes=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader'],text=True)
        choices=[]
        idle=[]
        for row in inventory.splitlines():
            values=[v.strip() for v in row.split(',')]
            if int(values[2])<100 and int(values[3])<=3 and values[0] not in processes:idle.append(values[0])
        for uuid in _pcve_rank_gpus(idle, case_id='steel_ball_silicone_cup'):
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
    policy_decision=_pcve_require_gpu(a.gpu, case_id='steel_ball_silicone_cup')
    run.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy();env['CUDA_VISIBLE_DEVICES']=a.gpu;env['OMP_NUM_THREADS']='4';env['OPENBLAS_NUM_THREADS']='4'
    repo=case_root.parents[2]
    # Only the shared scripts and this scene go on PYTHONPATH: extension-module paths of other runtimes
    # (CPython 3.10 builds) must not shadow the worker interpreter's NumPy or other packages.
    env['PYTHONPATH']=os.pathsep.join([str(repo/'scripts'),str(case_root)])
    receipt=dict(host=socket.gethostname(),gpu_uuid=a.gpu,gpu_policy=policy_decision,preflight_inventory=inventory,preflight_processes=processes,
                 command=cmd,started_unix_s=time.time())
    (run/'launch.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    log=(run/'stdout.log').open('w')
    process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--holder',str(run/'launch.json')],
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

if __name__=='__main__':main()
