"""Bounded mesh, unchanged-quality render, native playback and video acceptance."""
import hashlib,json,os,subprocess,time,traceback
from pathlib import Path
from PIL import Image
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import blender
W=Path(__file__).resolve().parent.parent
P=json.loads((W/'source_plan.json').read_text());R=Path(P['root']);S=P['source_scene']
B=str(blender())
E=os.environ.copy();E.update(OMP_NUM_THREADS='8',MKL_NUM_THREADS='8',OPENBLAS_NUM_THREADS='8')
jobs=[]
def read(p):
    try:return json.loads(p.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return None
def write(p,d):
    t=p.with_suffix('.tmp');t.write_text(json.dumps(d,indent=2));t.replace(p)
def status(stage,**kwargs):
    old=read(W/'status.json') or {}
    now=time.time()
    if old.get('stage')!=stage:
        history=read(W/'stage_timing.json') or []
        history.append({'stage':stage,'unix':now})
        write(W/'stage_timing.json',history)
    write(W/'status.json',{'stage':stage,'updated_unix':now,**kwargs})
def start(args,name,gpu=None):
    e=E.copy()
    if gpu is not None:e['CUDA_VISIBLE_DEVICES']=str(gpu)
    log=W/(name+'.log')
    with log.open('w') as f:p=subprocess.Popen(args,env=e,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT)
    jobs.append({'name':name,'pid':p.pid,'argv':args,'gpu':gpu,'log':str(log)})
    write(W/'derived_jobs.json',jobs)
    return p
def check(p,name):
    if p.poll() is not None and p.returncode!=0:raise RuntimeError(name+' failed; see log')
    job=next(j for j in jobs if j['pid']==p.pid)
    if 'Traceback (most recent call last)' in Path(job['log']).read_text():raise RuntimeError(name+' Python exception; see log')
def choose(count):
    while True:
        g=[list(map(int,l.split(','))) for l in subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip().splitlines()]
        good=sorted([a for a in g if a[3]<10 and a[2]>12000],key=lambda a:a[1])
        if good:
            write(W/('gpu_snapshot_'+str(int(time.time()))+'.json'),g)
            return [a[0] for a in good[:count]]
        status('waiting_for_idle_gpu');time.sleep(10)
def render(frames,cache=False):
    a=[B,'-t','8','-b',S,'--python',str(W/'source/render_edit.py'),'--','--case-id',P['id'],'--run',str(R/'simulation/run'),'--bounded',str(R/'bounded'),'--out',str(R/'render'),'--frames',frames,'--reuse']
    return a+(['--cache-only','--package-cache'] if cache else [])
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(8*1024*1024),b''):h.update(c)
    return h.hexdigest()
try:
    status('waiting_for_surface')
    while True:
        report=read(R/'simulation/run/aniso_surface_clean/report.json')
        if report and len(report['frames'])==96:break
        physical=read(W/'physics_status.json')
        if physical and physical['stage']=='failed':raise RuntimeError(physical['error'])
        time.sleep(5)
    status('baking_basin_boundaries');(R/'bounded').mkdir(exist_ok=True)
    chunks=[]
    for lo in range(1,97,6):
        hi=lo+5
        a=[B,'-t','8','-b',S,'--python',str(W/'source/bake_edit_boundaries.py'),'--','--run',str(R/'simulation/run'),'--out',str(R/'bounded'),'--start',str(lo),'--end',str(hi)]
        chunks.append((lo,hi,start(a,f'boundary_{lo}-{hi}')))
    while any(p.poll() is None for _,_,p in chunks):
        for lo,hi,p in chunks:check(p,f'boundary_{lo}-{hi}')
        status('baking_basin_boundaries',frames=len(list((R/'bounded').glob('water_*.npz'))));time.sleep(5)
    rows=[]
    for lo,hi,p in chunks:
        check(p,f'boundary_{lo}-{hi}');part=read(R/f'bounded/bake_report_{lo}-{hi}.json');assert len(part)==hi-lo+1;rows.extend(part)
    rows.sort(key=lambda r:r['frame']);write(R/'boundary_acceptance.json',{'status':'all_96_frames_valid','frames':rows})
    status('rendering_keyframes')
    preview=start(render('1,24,26,32,40,64,96'),'preview',choose(1)[0])
    native=start(render('1-96',True),'native_export')
    while preview.poll() is None:time.sleep(5)
    check(preview,'preview');status('ready_for_preview_review')
    while not (W/'preview_review.json').exists():time.sleep(5)
    assert read(W/'preview_review.json')['status']=='accepted'
    g=choose(4);n=len(g);renders=[]
    for i,gpu in enumerate(g):
        lo=i*96//n+1;hi=(i+1)*96//n
        renders.append((f'{lo}-{hi}',start(render(f'{lo}-{hi}'),f'render_{lo}-{hi}',gpu)))
    while any(p.poll() is None for _,p in renders):
        for name,p in renders:check(p,name)
        status('rendering_all_frames',frames=len(list((R/'render/frames').glob('frame_*.png'))));time.sleep(5)
    for name,p in renders:check(p,name)
    native.wait();check(native,'native_export');status('verifying_native_playback')
    a=[B,'-t','8','-b','--python',str(W/'source/verify_edit_native.py'),'--',S,str(R/'render/scene_animation.blend'),str(R/'bounded'),str(R/'simulation/run'),str(R/'render/native_acceptance.json')]
    v=start(a,'verify_native');v.wait();check(v,'verify_native')
    assert read(R/'render/native_acceptance.json')['status']=='all_96_native_frames_verified'
    renders={}
    for p in (R/'render').glob('render_report_*.json'):
        for row in read(p):renders[row['frame']]=row
    assert set(renders)==set(range(1,97))
    hashes=[]
    for f in range(1,97):
        p=R/'render/frames'/f'frame_{f:04d}.png'
        with Image.open(p) as im:assert im.size==(1280,720);im.verify()
        hashes.append({'frame':f,'sha256':sha(p)})
    video=R/'render/video.mp4';tick=time.monotonic()
    subprocess.run(['ffmpeg','-y','-v','warning','-framerate','24','-start_number','1','-i',str(R/'render/frames/frame_%04d.png'),'-frames:v','96','-c:v','libx264','-preset','slow','-crf','17','-pix_fmt','yuv420p','-threads','8','-movflags','+faststart',str(video)],check=True)
    encode=time.monotonic()-tick
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=width,height,r_frame_rate,nb_read_frames:format=duration,size','-of','json',str(video)],text=True));s=probe['streams'][0]
    assert s['width']==1280 and s['height']==720 and s['r_frame_rate']=='24/1' and int(s['nb_read_frames'])==96 and abs(float(probe['format']['duration'])-4)<.001
    subprocess.run(['ffmpeg','-v','error','-i',str(video),'-f','null','-'],check=True)
    write(R/'video_acceptance.json',{'status':'all_96_render_and_native_frames_passed','video_sha256':sha(video),'probe':probe,'frames':hashes,'encode_seconds':encode,'render_call_seconds_sum':sum(r['render_seconds'] for r in renders.values()),'physics':P['physics'],'runtime_booleans':0})
    status('ready_for_full_visual_review')
except Exception as e:
    status('failed',error=str(e),traceback=traceback.format_exc());raise
