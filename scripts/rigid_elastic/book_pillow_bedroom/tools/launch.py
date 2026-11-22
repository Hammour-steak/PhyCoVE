"""Idle-only, leased GPU launcher with a final post-gate occupancy query.

Without an explicit GPU the GPU policy ranks and selects an idle GPU. On a host whose
cards that policy refuses (48 GB cards), the operator claims one idle card and passes its UUID
explicitly (PCVE_EXPLICIT_GPU); that card is used as given.
"""
from pathlib import Path
import fcntl, hashlib, json, os, shutil, socket, subprocess, sys, time

ROOT = Path(os.environ['BOOK_PILLOW_ROOT'])
CASE_DIR=Path(__file__).resolve().parents[1]
SCRIPTS=CASE_DIR.parents[1]
sys.path[:0]=[str(SCRIPTS),str(CASE_DIR)]
import pcve_gpu_policy as policy
from scene_paths import SCENE, kit_dirs
HERE = Path(__file__).resolve().parent
DATA, SUPPORT = kit_dirs(ROOT)  # case-data and helper directories inside the restored kit
STAGE = ROOT.parent
CASE_ID = SCENE
host = socket.gethostname().split('.')[0]

def state(uuid):
    row = subprocess.check_output(['nvidia-smi','--id='+uuid,'--query-gpu=name,memory.total,memory.free,utilization.gpu','--format=csv,noheader,nounits'],text=True,timeout=15).strip().split(',')
    procs = subprocess.check_output(['nvidia-smi','--id='+uuid,'--query-compute-apps=pid,process_name,used_memory','--format=csv,noheader,nounits'],text=True,timeout=15).strip()
    return dict(uuid=uuid,model=row[0].strip(),total_mib=int(row[1]),free_mib=int(row[2]),utilization_percent=int(row[3]),processes=procs)

def idle(s): return s['free_mib']>10000 and s['utilization_percent']<5 and not s['processes']

phase, case = sys.argv[1:3]
assert phase in {'simulate','preview','render'}
assert sys.platform == 'linux'
explicit = os.environ.get('PCVE_EXPLICIT_GPU','auto')
pool = not explicit.startswith('GPU-')
leases = SCRIPTS.parent/'tools/pcve_gpu_leases'
leases.mkdir(exist_ok=True,parents=True)
rows = [state(r['uuid']) for r in policy.inventory()]
lease = None
candidates = [r['uuid'] for r in rows if idle(r) and explicit in ('auto',r['uuid'])]
for uuid in (policy.rank_uuids(candidates,case_id=CASE_ID) if pool else candidates):
    f = (leases/(uuid+'.lock')).open('a')
    try: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: f.close(); continue
    decision = (policy.require_gpu(uuid,case_id=CASE_ID) if pool else
                {'policy_id':'explicit-claim','host':host,'gpu_uuid':uuid,'reason':'GPU claimed by the operator'})
    selected = state(uuid)  # Must be AFTER require_gpu and immediately before subprocess launch.
    if idle(selected): lease = f; break
    f.close()
if lease is None:
    print('NO_IDLE_ELIGIBLE_GPU; retry without displacing jobs',flush=True)
    raise SystemExit(75)

env = dict(os.environ,BOOK_PILLOW_KIT_SUPPORT=str(SUPPORT),CUDA_VISIBLE_DEVICES=uuid,OMP_NUM_THREADS=os.environ.get('PCVE_CPU_THREADS','3'),OPENBLAS_NUM_THREADS=os.environ.get('PCVE_CPU_THREADS','3'),PYTHONDONTWRITEBYTECODE='1')
if phase == 'simulate':
    env.update(PYTHONHOME=str(STAGE/'python10'),PYTHONPATH=str(STAGE/'runtime'),
        LD_LIBRARY_PATH=str(STAGE/'cudart/lib')+':'+str(STAGE/'python10/lib'))
    cmd = [str(STAGE/'python10/bin/python3.10'), str(CASE_DIR/'physics/simulate.py'), '--case',case,*sys.argv[3:]]
else:
    env.pop('PYTHONHOME',None);env.pop('PYTHONPATH',None)
    cmd = [os.environ.get('PCVE_BLENDER_BIN',str(SCRIPTS.parent/'tools/blender-4.3.2-linux-x64/blender')),'-b','--threads',env['OMP_NUM_THREADS'],'--disable-autoexec','--python-exit-code','1','--python',str(CASE_DIR/'appearance/render.py'),'--','--case',case,*sys.argv[3:]]
    if phase=='preview': cmd.append('--preview')
receipts=DATA/'.work/canonical_logs';receipts.mkdir(parents=True,exist_ok=True)
receipt = receipts/(phase+'_'+case+'_'+str(os.getpid())+'.json')
r = dict(phase=phase,case=case,worker=host,
    gpu=selected,policy=decision,command=cmd,start_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
receipt.write_text(json.dumps(r,indent=2)); print(json.dumps(r),flush=True)
final_state=state(uuid)
if not idle(final_state):
    r.update(exit_code=75,not_launched=True,final_occupancy=final_state)
    receipt.write_text(json.dumps(r,indent=2));raise SystemExit(75)
r['final_occupancy']=final_state
receipt.write_text(json.dumps(r,indent=2))
done = subprocess.run(cmd,env=env)
r.update(exit_code=done.returncode,end_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
receipt.write_text(json.dumps(r,indent=2)); raise SystemExit(done.returncode)
