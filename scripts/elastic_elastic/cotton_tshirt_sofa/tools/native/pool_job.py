"""GPU launcher: fresh process query, shared GPU policy ranking, per-GPU lease, UUID binding and receipt."""

from pathlib import Path
import argparse, csv, datetime, fcntl, io, os, socket, subprocess, sys, time,json
from common import CASE, HERE, ROOT, save
sys.path.insert(0,str(ROOT/'scripts'))
from pcve_gpu_policy import rank_uuids, require_gpu
from pcve_assets import blender

def query(args):return subprocess.check_output(['nvidia-smi',*args],text=True,timeout=20)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);ap.add_argument('--tool',choices=['python','blender'],required=True);ap.add_argument('--gpu',default='auto');ap.add_argument('command',nargs=argparse.REMAINDER)
    ap.add_argument('--pool-audit',type=Path);ap.add_argument('--blender-bin',type=Path);ap.add_argument('--threads',type=int,default=6);a=ap.parse_args()
    if os.name=='nt' or sys.platform!='linux':raise RuntimeError('The native tools run on Linux')
    work=ROOT/'renders'/CASE/'launches';work.mkdir(parents=True,exist_ok=True)
    if (work/(a.name+'_receipt.json')).exists():raise FileExistsError(a.name)
    procs=query(['--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader'])
    state=query(['--query-gpu=uuid,name,memory.total,memory.free,memory.used,utilization.gpu','--format=csv,noheader,nounits'])
    rows=list(csv.reader(io.StringIO(state),skipinitialspace=True))
    idle=[r[0] for r in rows if int(r[4])<1000 and int(r[5])<=3 and r[0] not in procs]
    # An optional GPU inventory taken by the operator (time_utc, workers) is recorded with the job.
    scan=None
    if a.pool_audit:
        scan=json.loads(a.pool_audit.read_text())
        age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(scan['time_utc'])).total_seconds()
        if not 0<=age<=300:raise RuntimeError('The GPU inventory is older than five minutes')
    ranked=rank_uuids(idle,case_id=CASE)
    leases=ROOT/'tools/pcve_gpu_leases';leases.mkdir(parents=True,exist_ok=True)
    lease=None;uuid=None
    for candidate in ranked:
        if a.gpu!='auto' and a.gpu!=candidate:continue
        f=(leases/(candidate+'.lock')).open('a+')
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:f.close();continue
        lease=f;uuid=candidate;break
    if lease is None:raise RuntimeError('No idle eligible unleased GPU; retry later')
    policy=require_gpu(uuid,case_id=CASE)
    nowprocs=query(['--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader'])
    now=query(['--id='+uuid,'--query-gpu=uuid,name,memory.used,utilization.gpu,driver_version','--format=csv,noheader,nounits']).strip()
    f=[x.strip() for x in now.split(',')]
    if uuid in nowprocs or int(f[2])>=1000 or int(f[3])>3:raise RuntimeError('GPU became busy')
    args=list(a.command)
    if args and args[0]=='--':args.pop(0)
    script=HERE/args[0]
    env=dict(os.environ,CUDA_VISIBLE_DEVICES=uuid,OMP_NUM_THREADS=str(a.threads),OPENBLAS_NUM_THREADS='1',PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1')
    if a.tool=='blender':
        # Blender carries its own Python. A portable solver Python must not leak in.
        for key in ['PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH']:env.pop(key,None)
        pinned=ROOT/'tools/blender-4.3.2-linux-x64/blender'
        cmd=[str(a.blender_bin or (pinned if pinned.is_file() else blender())),'-b','-t',str(a.threads),'--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script),'--',*args[1:]]
    else:
        # A Python 3.10 staged in .runtime/<scene>/python (packages in deps/) is used when present, else this interpreter.
        runtime=ROOT/'.runtime'/CASE
        env['PYTHONPATH']=':'.join(map(str,[ROOT/'tools/ipc_probe_deps',ROOT/'tools/manifold3d_deps',runtime/'deps']))
        if (runtime/'python/bin/python3.10').is_file():
            env['PYTHONHOME']=str(runtime/'python')
            env['LD_LIBRARY_PATH']=str(runtime/'python/lib')+':'+env.get('LD_LIBRARY_PATH','')
            executable=str(runtime/'python/bin/python3.10')
        else:executable=sys.executable
        cmd=[executable,'-B',str(script),*args[1:]]
    rec=dict(case_id=CASE,worker_host=socket.gethostname(),
        gpu_uuid=uuid,gpu_policy=policy,initial_pool_host_inventory=state,processes=procs,rechecked=now,pool_inventory_before_job=scan,
        command=cmd,time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),local_blender_invoked=False,remote_blender_only_policy=True)
    final_procs=query(['--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader'])
    final_gpu=query(['--id='+uuid,'--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits']).strip()
    final_fields=[int(v.strip())for v in final_gpu.split(',')]
    if uuid in final_procs or final_fields[0]>=1000 or final_fields[1]>3:raise RuntimeError('GPU became busy before launch')
    rec['final_processes_before_launch']=final_procs;rec['final_gpu_before_launch']=final_gpu
    start=time.monotonic();save(work/(a.name+'_receipt.json'),rec)
    with (work/(a.name+'.log')).open('w') as log:
        child=subprocess.Popen(cmd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
        rec['pid']=child.pid;save(work/(a.name+'_receipt.json'),rec)
        rc=child.wait()
    rec.update(exit_code=rc,elapsed_seconds=time.monotonic()-start,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    save(work/(a.name+'_receipt.json'),rec);raise SystemExit(rc)

if __name__=='__main__':main()
