"""Build, render and verify a source plus five physical counterfactuals."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess,sys,time
from collections import deque
from pathlib import Path
from scene_config import save_json,signature
from counterfactual_cases import CASE_IDS,DEFINITIONS,case_configuration,prompts
from simulate_toy_car_track_jump import simulate,export_csv
from physics.validate_counterfactuals import validate_case

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]))
from pcve_assets import blender as blender_default

def check_video(path):
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=width,height,r_frame_rate,avg_frame_rate,nb_read_frames:format=duration','-of','json',str(path)],text=True))
    st=probe['streams'][0]
    decode=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],capture_output=True,text=True)
    checks={'resolution':[st['width'],st['height']]==[1280,720],'fps':st['r_frame_rate']==st['avg_frame_rate']=='24/1',
            'frames':int(st['nb_read_frames'])==96,'duration':abs(float(probe['format']['duration'])-4)<.001,
            'full_decode':decode.returncode==0 and not decode.stderr.strip()}
    return {'accepted':all(checks.values()),'checks':checks,'ffprobe':probe,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-root',type=Path,required=True)
    p.add_argument('--stage',choices=['all','simulate','graybox','prepare','render','verify'],default='all')
    p.add_argument('--cases',nargs='+',choices=CASE_IDS,default=CASE_IDS)
    p.add_argument('--blender',type=Path,default=blender_default())
    p.add_argument('--device',choices=['cpu','auto'],default='auto')
    p.add_argument('--threads-native',type=int,default=4)
    p.add_argument('--render-workers',type=int,default=3)
    p.add_argument('--skip-existing',action='store_true')
    p.add_argument('--scenario-overrides-json',type=Path)
    p.add_argument('--source-scene',type=Path)
    p.add_argument('--keyframes',nargs='+',type=int)
    a=p.parse_args();out=a.out_root.resolve();out.mkdir(parents=True,exist_ok=True)
    selected=list(dict.fromkeys(['source',*a.cases]));overrides=json.loads(a.scenario_overrides_json.read_text()) if a.scenario_overrides_json else None
    cfgs={c:case_configuration(c,overrides) for c in selected}
    manifest_path=out/'suite_manifest.json'
    existing=json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    if existing and existing['configuration_sha256']!=signature(cfgs['source']):raise ValueError('Use a fresh root after input changes')
    manifest=existing or {'schema_version':4,'scene':'toy_car_track_jump','suite_name':'pcve_toy_car_track_jump_counterfactuals',
        'interaction_category':'rigid_rigid','source_case_id':'source','configuration':cfgs['source'],'configuration_sha256':signature(cfgs['source']),
        'fps':24,'duration_sec':4.,'total_frames':96,'resolution':[1280,720],'samples':128,'playback_rate':1.,'source':{},'edits':[],'status':'running','timing':{}}
    start=time.perf_counter();save_json(manifest_path,manifest)
    results={}
    for case in selected:
        folder=out/'cases'/case;folder.mkdir(parents=True,exist_ok=True);path=folder/'physics_transforms.json'
        cached=json.loads(path.read_text()) if path.exists() else None
        fresh=cached is not None and cached['configuration']==cfgs[case]
        if a.stage in ['all','simulate','graybox'] and not(a.skip_existing and fresh):
            result=simulate(cfgs[case],case);save_json(path,result);export_csv(folder/'trajectory.csv',result);save_json(folder/'contacts.json',result['contact_events'])
        result=json.loads(path.read_text())
        if result['configuration']!=cfgs[case]:raise ValueError('Physics cache mismatch: '+case)
        results[case]=result
        report=validate_case(result,results.get('source'));save_json(folder/'physics_validation.json',report)
        save_json(folder/'settings.json',cfgs[case]);save_json(folder/'prompts.json',prompts(case))
        save_json(folder/'parameter_diff.json',{'before':{'physics':cfgs['source']['physics']},'after':{'physics':cfgs[case]['physics']}})
        if not report['accepted']:raise RuntimeError('Physics rejected '+case+': '+str([k for k,v in report['checks'].items() if not v]))
    manifest['timing']['simulation_wall_sec']=sum(r['simulation_wall_sec'] for r in results.values())
    template=out/'source_template.blend'
    if a.source_scene:
        original=a.source_scene.resolve()
        sha=hashlib.sha256(original.read_bytes()).hexdigest()
        if template.exists():
            if hashlib.sha256(template.read_bytes()).hexdigest()!=sha:raise ValueError('Scene template mismatch')
        else:shutil.copy2(original,template)
        manifest['source_template']={'path':str(template),'original':str(original),'sha256':sha}
    if a.stage in ['all','prepare']:
        for case in selected:
            folder=out/'cases'/case
            if a.skip_existing and (folder/'frame_signatures.json').exists():
                stored=json.loads((folder/'scenario_metadata.json').read_text())
                if stored['physics_input_sha256']!=hashlib.sha256((folder/'physics_transforms.json').read_bytes()).hexdigest():raise ValueError('Prepared case inputs changed; use a fresh output root: '+case)
                continue
            cmd=[str(a.blender),'-b','-t',str(a.threads_native),'--python-exit-code','1','--python',str(HERE/'render_toy_car_track_jump.py'),'--',
                '--out-dir',str(folder),'--physics-json',str(folder/'physics_transforms.json'),'--mode','prepare','--device',a.device]
            if template.exists():cmd+=['--base-scene',str(template)]
            env={**os.environ,'OMP_NUM_THREADS':str(a.threads_native),'OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
            # Preparation is geometry/animation only; avoid claiming any GPU.
            cmd[cmd.index('--device')+1]='cpu'
            with (folder/'prepare.log').open('w') as log:subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
            print('PREPARED',case,flush=True)
    def rows():
        items=[]
        for c in selected:
            f=out/'cases'/c;vr=f/'video_validation.json';visual=f/'visual_review.json'
            status='accepted' if visual.exists() and json.loads(visual.read_text()).get('accepted') else ('technically_verified_pending_visual_review' if vr.exists() else 'physics_accepted')
            items.append({'case_id':c,'kind':DEFINITIONS[c]['kind'],'title_zh':DEFINITIONS[c]['title_zh'],'case_dir':str(f),'status':status,
                'edit_instruction':DEFINITIONS[c]['edit_zh'],'parameter_overrides':DEFINITIONS[c]['overrides'],
                'observed_outcome':json.loads((f/'physics_validation.json').read_text())['metrics'],
                'outputs':{k:str(f/v) for k,v in {'video':'video.mp4','scene':'toy_car_track_jump.blend','physics':'physics_transforms.json','ground_truth':'ground_truth_transforms.json','settings':'settings.json','prompts':'prompts.json'}.items()}})
        return items
    def save_manifest():
        r=rows();manifest['source']=next(x for x in r if x['case_id']=='source');manifest['edits']=[x for x in r if x['case_id']!='source']
        manifest['status']='accepted' if all(x['status']=='accepted' for x in r) else ('technically_verified_pending_visual_review' if all(x['status'] in ['accepted','technically_verified_pending_visual_review'] for x in r) else 'running')
        save_json(manifest_path,manifest)
    save_manifest()
    if a.stage in ['all','render']:
        frame_set=set(a.keyframes or range(1,97));groups={};membership={}
        for c in selected:
            folder=out/'cases'/c
            stored=json.loads((folder/'scenario_metadata.json').read_text())
            if stored['physics_input_sha256']!=hashlib.sha256((folder/'physics_transforms.json').read_bytes()).hexdigest():raise ValueError('Prepared case physics mismatch: '+c)
            signatures=json.loads((out/'cases'/c/'frame_signatures.json').read_text())
            for row in signatures['frames']:
                if row['frame'] not in frame_set:continue
                key=row['signature'];member={'case_id':c,'frame':row['frame']}
                membership.setdefault(key,[]).append(member)
                groups.setdefault(key,member)
        jobs=[]
        for key,rep in groups.items():
            path=out/'cases'/rep['case_id']/'frames'/f"{rep['frame']:04d}.png"
            if not(a.skip_existing and path.exists()):jobs.append({'key':key,**rep})
        # Useful review frames appear first; all remaining native frames follow.
        jobs.sort(key=lambda j:(j['frame'] not in [13,24,1,8,48,96],j['frame']!=13,CASE_IDS.index(j['case_id']),j['frame']))
        save_json(out/'frame_reuse.json',{'policy':'Exact Blender exposure matrix signatures; temporal encoder noise retained independently per output frame.','groups':membership,
            'requested_frames':len(frame_set)*len(selected),'unique_render_states':len(groups)})
        pending=deque(jobs);active=[];completed=0;render_start=time.perf_counter();encoded=set()
        def distribute():
            for key,rep in groups.items():
                src=out/'cases'/rep['case_id']/'frames'/f"{rep['frame']:04d}.png"
                if not src.exists():continue
                for member in membership[key]:
                    dest=out/'cases'/member['case_id']/'frames'/f"{member['frame']:04d}.png"
                    if dest==src or dest.exists():continue
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    try:os.link(src,dest)
                    except OSError:shutil.copy2(src,dest)
        def encode_ready():
            if a.keyframes:return
            for c in selected:
                if c in encoded:continue
                folder=out/'cases'/c
                if not all((folder/'frames'/f'{i:04d}.png').exists() for i in range(1,97)):continue
                if a.skip_existing and (folder/'video.mp4').exists() and (folder/'video_validation.json').exists():
                    saved=json.loads((folder/'video_validation.json').read_text());check=check_video(folder/'video.mp4')
                    if saved['accepted'] and check['accepted'] and check['sha256']==saved['sha256']:
                        encoded.add(c);save_manifest();continue
                t=time.perf_counter()
                subprocess.run(['ffmpeg','-v','error','-y','-framerate','24','-start_number','1','-i',str(folder/'frames/%04d.png'),'-frames:v','96','-vf',cfgs[c]['render']['encode_filter'],
                                '-c:v','libx264','-preset','medium','-crf','17','-pix_fmt','yuv420p','-movflags','+faststart',str(folder/'video.mp4')],check=True)
                video=check_video(folder/'video.mp4');save_json(folder/'video_validation.json',video)
                if not video['accepted']:raise RuntimeError('Video failed '+c)
                save_json(folder/'encode_timing.json',{'wall_sec':time.perf_counter()-t});encoded.add(c);save_manifest();print('VIDEO_READY',c,flush=True)
        while pending or active:
            for task in list(active):
                code=task['process'].poll()
                if code is None:continue
                task['log'].close();active.remove(task)
                if code:raise RuntimeError('Frame render failed: '+str(task['job'])+'; log '+str(task['log_path']))
                completed+=1
            distribute();encode_ready()
            if pending and len(active)<a.render_workers:
                if a.device=='auto':
                    q=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
                    reserved={t['gpu'] for t in active};available=[r.split(',')[0].strip() for r in q.splitlines() if int(r.split(',')[1])<1000 and int(r.split(',')[2])==0 and r.split(',')[0].strip() not in reserved]
                else:available=['CPU'] if not active else []
                for gpu in available[:max(0,a.render_workers-len(active))]:
                    if not pending:break
                    job=pending.popleft();c,f=job['case_id'],job['frame'];folder=out/'cases'/c
                    log_path=folder/f'render_frame_{f:04d}.log';log=log_path.open('w')
                    env={**os.environ,'OMP_NUM_THREADS':str(a.threads_native),'OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
                    if gpu!='CPU':env['CUDA_VISIBLE_DEVICES']=gpu
                    cmd=[str(a.blender),'-b','-t',str(a.threads_native),'--python-exit-code','1','--python',str(HERE/'render_toy_car_track_jump.py'),'--',
                         '--out-dir',str(folder),'--physics-json',str(folder/'physics_transforms.json'),'--mode','frames','--frames',str(f),'--device',a.device,'--worker-id',f'frame_{f:04d}']
                    proc=subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
                    active.append({'process':proc,'gpu':gpu,'job':job,'log':log,'log_path':log_path})
            save_json(out/'progress.json',{'stage':'render','unique_states':len(groups),'scheduled_states':len(jobs),'completed_states':completed,
                'pending_states':len(pending),'active':[{'gpu':t['gpu'],**t['job']} for t in active],
                'native_frames_available':{c:len(list((out/'cases'/c/'frames').glob('*.png'))) for c in selected},'videos_ready':sorted(encoded),'render_wall_sec':time.perf_counter()-render_start})
            if pending or active:time.sleep(2)
        distribute();encode_ready();manifest['timing']['render_wall_sec']=time.perf_counter()-render_start
    if a.stage in ['all','render','verify'] and not a.keyframes:
        for c in selected:
            f=out/'cases'/c;v=check_video(f/'video.mp4');save_json(f/'video_validation.json',v)
            if not v['accepted']:raise RuntimeError('Video invalid: '+c)
    save_json(out/'implementation_manifest.json',{'source_template':manifest.get('source_template'),'python':sys.executable})
    shutil.copy2(HERE/'asset_manifest.json',out/'asset_manifest.json')
    manifest['timing']['last_stage_wall_sec']=time.perf_counter()-start;save_manifest()
    print(json.dumps({'status':manifest['status'],'out_root':str(out)},indent=2),flush=True)

if __name__=='__main__':main()
