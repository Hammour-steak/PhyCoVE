"""Resource-bounded, resumable processing of five accepted physical edits."""
import hashlib,json,os,subprocess,time,traceback
from pathlib import Path
from PIL import Image
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import blender
W=Path(__file__).resolve().parent.parent;P=json.loads((W/'edit_plan.json').read_text());R=Path(P['root']);BASE=Path(P['baseline'])
B=str(blender());S=P['source_scene']
E=os.environ.copy();E.update(OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4')
PREVIEW='1,24,28,49,72,96';jobs=[]
def read(p):
    try:return json.loads(p.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return None
def write(p,d):
    t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(d,indent=2)+'\n');t.replace(p)
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def start(argv,name,case,gpu=None):
    env=E.copy()
    if gpu is not None:env['CUDA_VISIBLE_DEVICES']=str(gpu)
    log=W/(name+'.log')
    with log.open('w') as f:process=subprocess.Popen(argv,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT)
    job={'name':name,'case':case,'gpu':gpu,'pid':process.pid,'argv':argv,'log':str(log),'start_unix':time.time(),'process':process}
    jobs.append(job);return job
def done(job):
    process=job['process'];code=process.poll()
    if code is None:return False
    if 'end_unix' not in job:job.update(end_unix=time.time(),return_code=code)
    if code or 'Traceback (most recent call last)' in Path(job['log']).read_text():raise RuntimeError('Stage failed '+job['log'])
    return True
def render(c,frames,cache=False):
    root=Path(c['root']);argv=[B,'-t','8','-b',S,'--python',str(W/'source/render_edit.py'),'--','--case-id',c['id'],
            '--run',str(root/'simulation/run'),'--bounded',str(root/'bounded'),'--out',str(root/'render'),'--frames',frames,'--reuse']
    return argv+(['--cache-only','--package-cache'] if cache else [])
def idle_gpus():
    raw=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'],text=True)
    snapshot=[list(map(int,l.split(','))) for l in raw.strip().splitlines()]
    used={j['gpu'] for j in jobs if j['gpu'] is not None and j['process'].poll() is None}
    good=sorted([g for g in snapshot if g[0] not in used and g[3]<10 and g[2]>14000],key=lambda g:g[1])
    write(W/'latest_gpu_snapshot.json',{'time_unix':time.time(),'snapshot':snapshot,'own_active_gpus':list(used)})
    return [g[0] for g in good]
def memory_available_gb():
    fields={l.split(':')[0]:int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines() if ':' in l and len(l.split())>1 and l.split()[1].isdigit()}
    return fields['MemAvailable']/1024**2
def reuse_timed_prefix(c):
    root=Path(c['root']);bounded=root/'bounded';frames=root/'render/frames';bounded.mkdir(exist_ok=True);frames.mkdir(parents=True,exist_ok=True)
    records={r['frame']:r for r in read(BASE/'boundary_acceptance.json')['frames']}
    for f in range(1,50):
        for kind in ['water','spray','mist','foam']:
            source=BASE/'bounded'/f'{kind}_{f:04d}.npz';target=bounded/source.name
            if not target.exists():os.link(source,target)
        source=BASE/'render/frames'/f'frame_{f:04d}.png';target=frames/source.name
        if not target.exists():os.link(source,target)
    write(bounded/'bake_report_reused_source_prefix.json',[records[f] for f in range(1,50)])
    renders={}
    for path in (BASE/'render').glob('render_report_*.json'):
        for row in read(path):renders[row['frame']]=row
    write(root/'render/render_report_reused_source_prefix.json',[{**renders[f],'reused_from_source':True,'render_seconds':0.0,'original_render_seconds':renders[f]['render_seconds']} for f in range(1,50)])
    write(root/'prefix_reuse.json',{'source':str(BASE),'physical_frames_verified':[1,49],'baked_frames_reused':[1,49],
          'rendered_frames_reused':[1,49],'quality_identical':True,'sha256':[{'frame':f,'sha256':sha(frames/f'frame_{f:04d}.png')} for f in range(1,50)]})
def gather_bounded(root):
    rows={}
    for path in (root/'bounded').glob('bake_report_*.json'):
        for row in read(path) or []:rows[row['frame']]=row
    return rows
def encode(c):
    root=Path(c['root']);out=root/'render';rows={}
    for path in out.glob('render_report_*.json'):
        for row in read(path):rows[row['frame']]=row
    assert set(rows)==set(range(1,97)),(c['id'],sorted(rows))
    hashes=[]
    for f in range(1,97):
        path=out/'frames'/f'frame_{f:04d}.png'
        with Image.open(path) as im:assert im.size==(1280,720);im.verify()
        hashes.append({'frame':f,'sha256':sha(path)})
    tick=time.monotonic();video=out/'video.mp4'
    subprocess.run(['ffmpeg','-y','-v','warning','-framerate','24','-start_number','1','-i',str(out/'frames/frame_%04d.png'),
                    '-frames:v','96','-c:v','libx264','-preset','slow','-crf','17','-pix_fmt','yuv420p','-threads','8','-movflags','+faststart',str(video)],check=True)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_entries',
                    'stream=width,height,r_frame_rate,nb_read_frames:format=duration,size','-of','json',str(video)],text=True));stream=probe['streams'][0]
    assert [stream['width'],stream['height']]==[1280,720] and stream['r_frame_rate']=='24/1' and int(stream['nb_read_frames'])==96
    assert abs(float(probe['format']['duration'])-4)<.001
    subprocess.run(['ffmpeg','-v','error','-i',str(video),'-f','null','-'],check=True)
    if c['id']=='mass_after_2s_x3':
        for f in range(1,50):assert sha(out/'frames'/f'frame_{f:04d}.png')==sha(BASE/'render/frames'/f'frame_{f:04d}.png')
    write(root/'video_acceptance.json',{'status':'all_96_render_and_native_frames_passed','video_sha256':sha(video),'probe':probe,
          'frames':hashes,'encode_seconds':time.monotonic()-tick,'render_call_seconds_sum':sum(r['render_seconds'] for r in rows.values()),
          'runtime_booleans':0,'baseline':str(BASE)})

states={c['id']:{'case':c,'root':Path(c['root']),'surface_ready':False,'bake_queued':False,'bounded':False,
         'preview':None,'preview_ready':False,'preview_accepted':False,'export':None,'export_done':False,
         'verify':None,'verified':False,'render_queued':False,'renders':[],'encoded':False} for c in P['cases']}
bake_queue=[];baking=[];render_queue=[]
try:
    assert read(R/'physics_acceptance.json')['status']=='all_five_rebased_edits_passed'
    assert read(W/'baker_optimization_acceptance.json')['status']=='all_mesh_arrays_bit_identical'
    for state in states.values():
        state['root'].mkdir(parents=True,exist_ok=True);(state['root']/'bounded').mkdir(exist_ok=True)
        if state['case']['id']=='mass_after_2s_x3':reuse_timed_prefix(state['case'])
    while not all(s['encoded'] for s in states.values()):
        for job in jobs:
            if job['process'].poll() is not None:done(job)
        baking=[item for item in baking if not done(item[2])]
        for name,state in states.items():
            c=state['case'];root=state['root'];surface=read(root/'simulation/run/aniso_surface_clean/report.json')
            state['surface_frames']=len(surface['frames']) if surface else 0
            if state['surface_frames']==96 and not state['bake_queued']:
                if name=='no_car':assert all(row['drops']==row['mist']==row['foam']==0 for row in surface['frames'].values())
                existing=gather_bounded(root)
                for lo in range(1,97,6):
                    hi=lo+5
                    if not all(f in existing for f in range(lo,hi+1)):bake_queue.append((name,lo,hi))
                state['surface_ready']=True;state['bake_queued']=True
            if state['bake_queued'] and not state['bounded']:
                rows=gather_bounded(root);state['bounded_frames']=len(rows)
                own_active=any(n==name for n,_,_ in baking);own_queued=any(n==name for n,_,_ in bake_queue)
                if len(rows)==96 and not own_active and not own_queued:
                    write(root/'boundary_acceptance.json',{'status':'all_96_frames_valid','frames':[rows[f] for f in range(1,97)]});state['bounded']=True
            if state['preview'] and done(state['preview']):
                assert (root/f'render/animation_manifest_{PREVIEW}.json').exists();state['preview_ready']=True
            marker=read(W/'preview_reviews'/f'{name}.json')
            if state['preview_ready'] and marker and marker['status']=='accepted':state['preview_accepted']=True
            if state['export'] and done(state['export']):
                assert (root/'render/cache_manifest.json').exists();state['export_done']=True
            if state['verify'] and done(state['verify']):
                assert read(root/'render/native_acceptance.json')['status']=='all_96_native_frames_verified';state['verified']=True
            if state['preview_accepted'] and not state['render_queued']:
                for lo in range(1,97,12):
                    hi=lo+11
                    if not all((root/'render/frames'/f'frame_{f:04d}.png').is_file() for f in range(lo,hi+1)):render_queue.append((name,lo,hi))
                state['render_queued']=True
            pending=any(n==name for n,_,_ in render_queue)
            if state['render_queued'] and not pending and all(done(j) for j in state['renders']) and state['verified'] and not state['encoded']:
                assert len(list((root/'render/frames').glob('frame_*.png')))==96;encode(c);state['encoded']=True
        while bake_queue and len(baking)<32 and memory_available_gb()>40:
            name,lo,hi=bake_queue.pop(0);c=states[name]['case'];root=states[name]['root']
            argv=[B,'-t','4','-b',S,'--python',str(W/'source/bake_edit_boundaries.py'),'--','--run',str(root/'simulation/run'),
                  '--out',str(root/'bounded'),'--start',str(lo),'--end',str(hi),'--strip-unrelated']
            job=start(argv,f'boundary_{name}_{lo}-{hi}',name);baking.append((name,(lo,hi),job))
        exporting=sum(s['export'] is not None and not s['export_done'] for s in states.values())
        verifying=sum(s['verify'] is not None and not s['verified'] for s in states.values())
        for name,state in states.items():
            if state['bounded'] and not state['export'] and exporting<2:
                state['export']=start(render(state['case'],'1-96',True),'native_'+name,name);exporting+=1
            if state['export_done'] and not state['verify'] and verifying<2:
                root=state['root'];argv=[B,'-t','4','-b','--python',str(W/'source/verify_edit_native.py'),'--',S,
                    str(root/'render/scene_animation.blend'),str(root/'bounded'),str(root/'simulation/run'),str(root/'render/native_acceptance.json')]
                state['verify']=start(argv,'verify_'+name,name);verifying+=1
        gpus=idle_gpus();active_gpu_count=sum(j['gpu'] is not None and j['process'].poll() is None for j in jobs)
        for gpu in gpus[:max(0,6-active_gpu_count)]:
            waiting=next((s for s in states.values() if s['bounded'] and not s['preview']),None)
            if waiting:
                name=waiting['case']['id'];waiting['preview']=start(render(waiting['case'],PREVIEW),'preview_'+name,name,gpu)
            elif render_queue:
                name,lo,hi=render_queue.pop(0);state=states[name]
                state['renders'].append(start(render(state['case'],f'{lo}-{hi}'),f'render_{name}_{lo}-{hi}',name,gpu))
            else:break
        progress={name:{'surface':s.get('surface_frames',0),'bounded':s.get('bounded_frames',0),'preview_ready':s['preview_ready'],
            'preview_accepted':s['preview_accepted'],'native_export_done':s['export_done'],'native_verified':s['verified'],
            'rendered':len(list((s['root']/'render/frames').glob('frame_*.png'))),'video_verified':s['encoded']} for name,s in states.items()}
        write(W/'status.json',{'stage':'processing_five_edits','progress':progress,'active_boundary_workers':len(baking),
              'pending_boundary_chunks':len(bake_queue),'pending_render_chunks':len(render_queue),'memory_available_gb':memory_available_gb(),'updated_unix':time.time()})
        write(W/'derived_jobs.json',[{k:v for k,v in j.items() if k!='process'} for j in jobs])
        for job in read(W/'surface_jobs.json') or []:
            if 'Traceback (most recent call last)' in Path(job['log']).read_text():raise RuntimeError('Surface failed '+job['id'])
        time.sleep(5)
    write(W/'status.json',{'stage':'ready_for_full_visual_review','updated_unix':time.time(),'cases':list(states)})
except Exception as exc:
    write(W/'status.json',{'stage':'failed','error':str(exc),'traceback':traceback.format_exc(),'updated_unix':time.time()})
    for job in jobs:
        if job['process'].poll() is None:job['process'].terminate()
    raise
