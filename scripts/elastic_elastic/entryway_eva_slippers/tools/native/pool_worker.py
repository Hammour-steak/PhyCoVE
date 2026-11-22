"""Fresh hardware query, shared 3090 ranking/gate, lease and UUID binding."""

from pathlib import Path
import argparse,csv,datetime,fcntl,io,os,socket,subprocess,sys,time
from common import CASE,HERE,ROOT,read,save
sys.path.insert(0,str(ROOT/'scripts'))
from pcve_assets import blender
from pcve_gpu_policy import rank_uuids,require_gpu
# Scene runtime: lib/ holds the CUDA 12 runtime of the native viscosity extension; a Python 3.10 staged in
# python/ (packages in deps/) is used when present. libuipc itself comes from tools/ipc_probe_deps.
RUNTIME=ROOT/'.runtime'/CASE

def query(args):return subprocess.check_output(['nvidia-smi',*args],text=True,timeout=20)

def main():
 p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--tool',choices=['python','blender'],required=True);p.add_argument('--gpu',default='auto');p.add_argument('--cpu',action='store_true');p.add_argument('command',nargs=argparse.REMAINDER);p.add_argument('--pool-audit',type=Path);p.add_argument('--blender-bin',type=Path);p.add_argument('--threads',type=int,default=6);a=p.parse_args()
 host=socket.gethostname().split('.')[0]
 if os.name=='nt':raise RuntimeError('The native tools run on Linux')
 jobs=ROOT/'renders'/CASE/'launches';receipt=jobs/(a.name+'_receipt.json')
 if receipt.exists():raise FileExistsError(a.name)
 receipt.parent.mkdir(parents=True,exist_ok=True)
 lease=None;policy=None;uuid='';state='';processes='';fresh=''
 if not a.cpu:
  if a.pool_audit:
   scan=read(a.pool_audit);age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(scan['time_utc'])).total_seconds()
   if not 0<=age<=300:raise RuntimeError('The GPU inventory is older than five minutes')
  state=query(['--query-gpu=uuid,name,memory.total,memory.free,memory.used,utilization.gpu','--format=csv,noheader,nounits']);processes=query(['--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader'])
  rows=list(csv.reader(io.StringIO(state),skipinitialspace=True));idle=[r[0] for r in rows if int(r[4])<256 and int(r[5])<=2 and int(r[3])>4096 and r[0] not in processes]
  ranked=rank_uuids(idle,case_id=CASE)
  folder=ROOT/'tools/pcve_gpu_leases';folder.mkdir(parents=True,exist_ok=True)
  for candidate in ranked:
   if a.gpu!='auto' and a.gpu!=candidate:continue
   lock=(folder/(candidate+'.lock')).open('a+')
   try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   except BlockingIOError:lock.close();continue
   lease=lock;uuid=candidate;break
  if lease is None:raise RuntimeError('No idle, eligible and unleased GPU; retry later')
  policy=require_gpu(uuid,case_id=CASE)
  processes=query(['--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader']);fresh=query(['-i',uuid,'--query-gpu=uuid,name,memory.total,memory.free,memory.used,utilization.gpu,driver_version','--format=csv,noheader,nounits']).strip();row=next(csv.reader([fresh],skipinitialspace=True))
  if uuid in processes or int(row[4])>=256 or int(row[5])>2:raise RuntimeError('Selected GPU became busy')
 args=list(a.command)
 if args and args[0]=='--':args.pop(0)
 script=HERE/args.pop(0);env=dict(os.environ,CUDA_VISIBLE_DEVICES=uuid,OMP_NUM_THREADS=str(a.threads),OPENBLAS_NUM_THREADS='2',PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1',PCVE_JOB_NAME=a.name);env['PATH']=str(RUNTIME/'encoder/bin')+os.pathsep+env.get('PATH','')
 if a.tool=='blender':
  for k in ['PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH']:env.pop(k,None)
  pinned=ROOT/'tools/blender-4.3.2-linux-x64/blender';cmd=[str(a.blender_bin or (pinned if pinned.is_file() else blender())),'-b','-t',str(a.threads),'--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script),'--',*args]
 else:
  staged=RUNTIME/'python/bin/python3.10'
  env['PYTHONPATH']=':'.join(map(str,[ROOT/'tools/ipc_probe_deps',ROOT/'tools/manifold3d_deps',RUNTIME/'deps',RUNTIME]))
  env['LD_LIBRARY_PATH']=':'.join(map(str,[RUNTIME/'lib',*([RUNTIME/'python/lib'] if staged.is_file() else []),ROOT/'tools/ipc_probe_deps/uipc/_native']))+':'+env.get('LD_LIBRARY_PATH','')
  if staged.is_file():env['PYTHONHOME']=str(RUNTIME/'python');exe=str(staged)
  else:exe=sys.executable
  cmd=[exe,'-B',str(script),*args]
 if not a.cpu:
  final=query(['--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader']);r=query(['-i',uuid,'--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits']);m,u=map(int,r.strip().split(','))
  if uuid in final or m>=256 or u>2:raise RuntimeError('GPU became busy during preparation')
 rec=dict(case_id=CASE,host=host,gpu_uuid=uuid,gpu_policy=policy,cpu_only=a.cpu,inventory=state,processes=processes,rechecked=fresh,command=cmd,time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),local_blender_used=False)
 save(receipt,rec);start=time.monotonic()
 with (jobs/(a.name+'.log')).open('wb') as log:
  child=subprocess.Popen(cmd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT);rec['pid']=child.pid;save(receipt,rec);code=child.wait()
 rec.update(returncode=code,wall_s=time.monotonic()-start);save(receipt,rec)
 if lease:lease.close()
 raise SystemExit(code)

if __name__=='__main__':main()
