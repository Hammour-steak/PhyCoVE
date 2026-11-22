"""Lease an actually idle permitted GPU before any Blender launch."""

from pathlib import Path
import argparse,csv,fcntl,hashlib,io,json,os,shutil,socket,subprocess,sys,time
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3]
WORK=REPO/'renders/thomas_dual_spring_train'
if os.name=='nt':
    raise RuntimeError('Blender rendering runs on a Linux GPU host')
sys.path.insert(0,str(REPO/'scripts'))
from pcve_gpu_policy import rank_uuids,require_gpu

def inventory():
    raw=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,name,memory.total,memory.free,memory.used,utilization.gpu',
        '--format=csv,noheader,nounits'],text=True,timeout=15)
    apps=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory',
        '--format=csv,noheader,nounits'],text=True,timeout=15)
    rows=[[value.strip() for value in row] for row in csv.reader(io.StringIO(raw))]
    occupied={row[0].strip() for row in csv.reader(io.StringIO(apps)) if row}
    idle=[row[1] for row in rows if row[1] not in occupied and int(row[5])<512 and int(row[6])<5 and int(row[4])>9000]
    return rank_uuids(idle,case_id='thomas_dual_spring_train'),{'gpus':rows,'processes':apps}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['preview','render'],required=True)
    parser.add_argument('--case',default='source',choices=['source', 'mass_x3', 'rolling_x4', 'right_young_x025', 'delete_right_spring', 'add_wood_block']);parser.add_argument('--frame',type=int,default=16)
    parser.add_argument('--tag',default='p1');parser.add_argument('--samples',type=int,default=192);parser.add_argument('--gpu')
    parser.add_argument('--state-root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--blender-bin',type=Path)
    parser.add_argument('--threads',type=int,default=4)
    a=parser.parse_args()
    out=a.out/a.case
    if not (a.state_root/a.case/'states.npz').is_file():raise FileNotFoundError(a.state_root/a.case/'states.npz')
    out.mkdir(parents=True,exist_ok=True)
    if a.mode=='render' and (out/'scene_render_metadata.json').exists():
        old=json.loads((out/'scene_render_metadata.json').read_text())
        if old['state_cache_sha256']==sha(a.state_root/a.case/'states.npz') and old['video_sha256']==sha(out/'video.mp4'):
            print('ALREADY_COMPLETE_VERIFIED',a.case,flush=True);return
    case_root=WORK/'case_leases';case_root.mkdir(parents=True,exist_ok=True)
    case_lock=(case_root/(a.case+'_'+a.mode+'.lock')).open('a+')
    try:fcntl.flock(case_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit(75)
    candidates,evidence=inventory()
    if a.gpu:candidates=[uuid for uuid in candidates if uuid==a.gpu]
    leases=REPO/'tools/pcve_gpu_leases';leases.mkdir(parents=True,exist_ok=True)
    lock=None;uuid=None
    for candidate in candidates:
        handle=(leases/(candidate+'.lock')).open('a+')
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:handle.close();continue
        lock=handle;uuid=candidate;break
    if lock is None:print('NO_IDLE_LEASEABLE_PERMITTED_GPU',flush=True);raise SystemExit(75)
    decision=require_gpu(uuid,case_id='thomas_dual_spring_train')
    fresh,fresh_evidence=inventory()
    if uuid not in fresh:print('GPU_BECAME_BUSY',flush=True);raise SystemExit(75)
    blender=a.blender_bin or REPO/'tools/blender-5.1.0-linux-x64/blender'
    if not blender.is_file():raise RuntimeError('Compatible remote Blender 5.1 installation absent')
    ffmpeg=next((p for p in [REPO/'tools/ffmpeg/ffmpeg'] if p.is_file()),None)
    if ffmpeg is None:
        found=shutil.which('ffmpeg');ffmpeg=Path(found) if found else None
    if ffmpeg is None:raise RuntimeError('Compatible worker ffmpeg is absent')
    work=WORK/'blender_runtime';(work/'cache').mkdir(parents=True,exist_ok=True);(work/'tmp').mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,CUDA_VISIBLE_DEVICES=uuid,OMP_NUM_THREADS=str(a.threads),OPENBLAS_NUM_THREADS='1',PCVE_FFMPEG=str(ffmpeg),
        XDG_CACHE_HOME=str(work/'cache'),TMPDIR=str(work/'tmp'),PYTHONDONTWRITEBYTECODE='1')
    # The published look: appearance/realism.py runs render.py with the overlay of the published videos.
    script=HERE.parent/'appearance/realism.py'
    args=[str(blender),'-b','-t',str(a.threads),'--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script)]
    args.extend(['--','--mode',a.mode,'--case',a.case,'--frame',str(a.frame),'--samples',str(a.samples),'--tag',a.tag,
                 '--state-root',str(a.state_root),'--out',str(a.out)])
    provenance={'worker':socket.gethostname(),'gpu_uuid':uuid,'policy':decision,'inventory_before_launch':evidence,
        'fresh_inventory_before_launch':fresh_evidence,'mode':a.mode,'case':a.case,'blender':str(blender),'ffmpeg':str(ffmpeg),
        'time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'local_blender_used':False,'argv':args}
    (out/('worker_'+a.mode+'_'+a.tag+'.json')).write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    print('LEASED_REMOTE_GPU',uuid,decision['gpu_name'],flush=True)
    subprocess.run(args,env=env,check=True)

if __name__=='__main__':main()
