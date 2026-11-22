"""Job launch with current GPU/process preflight, a per-GPU lease and UUID binding."""

import argparse,csv,hashlib,io,json,os,platform,socket,subprocess,time
from pathlib import Path
import fcntl

# Shared PCVE GPU allocation policy (scripts/pcve_gpu_policy.py)
import sys as _pcve_policy_sys
_pcve_policy_root = next(p for p in Path(__file__).resolve().parents if (p / 'scripts/pcve_gpu_policy.py').is_file())
_pcve_policy_sys.path.insert(0, str(_pcve_policy_root / 'scripts'))
from pcve_gpu_policy import require_gpu as _pcve_require_gpu, rank_uuids as _pcve_rank_gpus
from pcve_gpu_reservations import reservations

def query(args):
    return list(csv.reader(io.StringIO(subprocess.check_output(['nvidia-smi',*args],text=True,timeout=15)),skipinitialspace=True))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--gpu',required=True);ap.add_argument('--name',required=True)
    ap.add_argument('--runtime',default=str(_pcve_policy_root/'tools/blender-4.3.2-linux-x64/blender'))
    ap.add_argument('--threads',type=int,default=4)
    ap.add_argument('arguments',nargs=argparse.REMAINDER);a=ap.parse_args()
    host=socket.gethostname().split('.')[0]
    if platform.system()!='Linux':raise RuntimeError('Linux GPU host required')
    _pcve_policy_sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from scene_paths import RENDERS,RUNTIME
    out=RENDERS/'launches'/a.name;out.mkdir(parents=True,exist_ok=False)
    rows=query(['--query-gpu=index,uuid,name,memory.total,memory.used,utilization.gpu,driver_version,memory.free','--format=csv,noheader,nounits'])
    apps=query(['--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader,nounits'])
    lease_dir=RUNTIME/'gpu_leases';lease_dir.mkdir(parents=True,exist_ok=True)
    bound=reservations(rows,exclude=(os.getpid(),os.getppid()))
    busy={p[0] for p in apps}|{p['gpu_uuid'] for p in bound}
    idle=[r[1] for r in rows if int(r[4])<256 and int(r[5])<=2 and int(r[7])>=4096 and r[1] not in busy]
    ranked=_pcve_rank_gpus(idle,case_id='metro_security_bag_curtain')
    selected=next((uid for uid in ranked if a.gpu in ('auto',uid)),None)
    if selected is None:
        raise RuntimeError('No eligible idle GPU on this worker; retry after preflight')
    a.gpu=selected
    lease=(lease_dir/(a.gpu+'.lock')).open('a+')
    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    row=next(r for r in rows if r[1]==a.gpu)
    receipt=dict(host=host,interface_addresses=subprocess.check_output(['hostname','-I'],text=True,timeout=5).split(),gpu_uuid=a.gpu,gpu=row,
        all_gpus=rows,compute_processes=apps,started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        platform=platform.platform())
    try:
        receipt['gpu_selection_policy']=_pcve_require_gpu(a.gpu, case_id='metro_security_bag_curtain')
    except RuntimeError as error:
        receipt.update(status='refused_gpu_policy',exit_code=75,preflight_refused=True,reason=str(error))
        (out/'receipt.json').write_text(json.dumps(receipt,indent=2));raise SystemExit(75)
    receipt['bound_gpu_processes']=bound
    latest=query(['-i',a.gpu,'--query-gpu=memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'])
    processes=query(['--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'])
    used,free,util=map(int,latest[0])
    if used>=256 or free<4096 or util>2 or any(row[0]==a.gpu for row in processes):
        receipt.update(status='refused_gpu_busy',exit_code=75,preflight_refused=True)
        (out/'receipt.json').write_text(json.dumps(receipt,indent=2));raise SystemExit(75)
    arguments=a.arguments[1:] if a.arguments[:1]==['--'] else a.arguments
    cmd=[a.runtime,'--background','--disable-autoexec','--factory-startup','--python-exit-code','1','--threads',str(a.threads),*arguments]
    receipt['command']=cmd;receipt['blender_binary_sha256']=hashlib.sha256(Path(a.runtime).read_bytes()).hexdigest()
    sources=[Path(token) for token in cmd if token.endswith('.py') and Path(token).is_file()]
    for source in list(sources):
        for name in ('scene_environment.py','checkpoint_details.py','detail_refinement.py','monitor_upgrade.py','concourse_return.py','outfeed.py','station_details.py','audit_grounding.py','audit_scene_reuse.py'):
            dependency=source.parent/name
            if dependency.is_file() and dependency not in sources:sources.append(dependency)
    env=os.environ.copy();env.update(CUDA_VISIBLE_DEVICES=a.gpu,OMP_NUM_THREADS=str(a.threads),
                                   OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    start=time.monotonic();print(json.dumps({'launch':a.name,'host':host,'gpu_uuid':a.gpu}),flush=True)
    with (out/'blender.log').open('wb') as log:
        child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env);receipt['pid']=child.pid
        (out/'receipt.json').write_text(json.dumps(receipt,indent=2))
        while child.poll() is None:
            time.sleep(5)
            try:others=query(['--query-compute-apps=gpu_uuid,pid,used_memory','--format=csv,noheader,nounits'])
            except subprocess.TimeoutExpired:
                receipt.setdefault('monitor_timeouts',[]).append(time.monotonic()-start)
                continue
            conflicts=[r for r in others if r[0]==a.gpu and r[1]!=str(child.pid)]
            own_memory=[float(r[2]) for r in others if r[1]==str(child.pid) and r[2].replace('.','',1).isdigit()]
            if own_memory:
                receipt['peak_observed_own_memory_mib']=max(receipt.get('peak_observed_own_memory_mib',0),max(own_memory))
            own_devices=sorted({r[0] for r in others if r[1]==str(child.pid)})
            if own_devices:receipt['observed_compute_gpu_uuids']=own_devices
            if any(uuid!=a.gpu for uuid in own_devices):
                receipt['gpu_binding_violation']=own_devices;child.terminate();break
            if conflicts:
                receipt['external_conflict']=conflicts;child.terminate();break
        receipt['exit_code']=child.wait()
    receipt['wall_s']=time.monotonic()-start;receipt['finished_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    receipt['blender_log_sha256']=hashlib.sha256((out/'blender.log').read_bytes()).hexdigest()
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt),flush=True)
    raise SystemExit(receipt['exit_code'] or (75 if 'external_conflict' in receipt else 0))

if __name__=='__main__':main()
