"""Source-gated native simulation, Cycles rendering and PCVE verification."""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'tools'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__=='__main__':
    import sys as _sys
    from pathlib import Path as _Path
    if (_Path(__file__).resolve().parents[2]/'pcve_scene_entry.py').is_file():
        _sys.path.insert(0,str(_Path(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__,'build_pcve')
# PCVE_UNIFIED_ENTRY_END
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import copy
import shutil
from scene_config import configured_scenario,signature,differences,save_json,CASES
from simulate_ramp_car_ball_collision import simulate,export_csv
from validate_ramp_car_ball_collision import validate
from edit_vocab import edit_info
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from pcve_assets import blender

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def verified_result(path,case,source=None,expected=None):
    r=load(path);assert r['configuration']==expected,'Changed inputs need a new isolated output root'
    report=validate(r,case,source);save_json(path.with_name('physics_validation.json'),report)
    if not report['accepted']:raise RuntimeError((case,[k for k,v in report['checks'].items() if not v]))
    return r

def main():
    p=argparse.ArgumentParser();p.add_argument('--out-root',type=Path,required=True);p.add_argument('--stage',choices=['all','prepare','simulate','render','verify','graybox'],default='all')
    p.add_argument('--cases',choices=list(CASES),nargs='+',default=list(CASES));p.add_argument('--blender',type=Path,default=blender())
    p.add_argument('--device',choices=['auto','cpu'],default='auto');p.add_argument('--skip-existing',action='store_true');p.add_argument('--synchronized-cache',action='store_true')
    p.add_argument('--refresh-dynamic-only',action='store_true')
    p.add_argument('--appearance-json',type=Path);p.add_argument('--configuration-json',type=Path,help='Full scene configuration JSON used instead of BASELINE in scene_config.py');p.add_argument('--reuse-physics-from',type=Path,help='Accepted suite whose solver inputs and trajectories are copied byte-for-byte; no simulation')
    a=p.parse_args();out=a.out_root.resolve()
    appearance=load(a.appearance_json) if a.appearance_json else None
    def case_config(case='source'):return configured_scenario(case,a.configuration_json)
    def visual_config(value):
        value=copy.deepcopy(value)
        if appearance is not None:value['appearance']=copy.deepcopy(appearance)
        return value
    if a.reuse_physics_from:
        assert a.stage in ['all','prepare','render','verify'],'Physics reuse is for appearance-only changes'
        assert a.reuse_physics_from.resolve()!=out
    if a.stage=='graybox':
        cmd=[sys.executable,str(HERE/'physics/graybox_scan.py'),'--out-root',str(out/'graybox')]
        if a.configuration_json:cmd+=['--configuration-json',str(a.configuration_json)]
        subprocess.run(cmd,check=True);return
    cfg=visual_config(case_config());manifest_path=out/'suite_manifest.json'
    if manifest_path.exists():
        manifest=load(manifest_path);assert manifest['configuration']==cfg,'Frozen suite configuration changed; choose a new root'
    else:
        if out.exists() and any(out.iterdir()):raise FileExistsError('Unrecognized nonempty output root '+str(out))
        manifest={'schema_version':1,'scene':'ramp_car_ball_collision','category':'rigid_rigid','configuration':cfg,'cases':{},'status':'in_progress',
            'formal_video_spec':f"{cfg['render']['resolution'][0]}x{cfg['render']['resolution'][1]}, {cfg['render']['fps']} fps, {cfg['render']['duration_sec']} s, {round(cfg['render']['fps']*cfg['render']['duration_sec'])} frames, Cycles {cfg['render']['samples']} samples, fixed camera, real-time playback"}
        save_json(manifest_path,manifest)
    if a.reuse_physics_from:
        evidence={}
        for case in dict.fromkeys(['source']+a.cases):
            old=a.reuse_physics_from.resolve()/'cases'/case;new=out/'cases'/case;new.mkdir(parents=True,exist_ok=True)
            proof=load(old/'case_acceptance.json');assert proof['accepted'] and proof['physics_sha256']==sha(old/'physics_transforms.json')
            evidence[case]={}
            for filename in ['physics_transforms.json','trajectory.csv','physics_validation.json','contacts.json','prompts.json']:
                original=old/filename;target=new/filename
                if target.exists():assert sha(target)==sha(original),(case,filename,'frozen file changed')
                else:shutil.copy2(original,target)
                evidence[case][filename]={'before_sha256':sha(original),'after_sha256':sha(target),'identical':True}
        reference_cfg=load(a.reuse_physics_from.resolve()/'suite_manifest.json')['configuration']
        save_json(out/'physics_freeze_audit.json',{'accepted':True,'reference_suite':str(a.reuse_physics_from.resolve()),'no_solver_rerun':True,'files':evidence,
            'before':reference_cfg,'after':cfg,'configuration_diff':differences(reference_cfg,cfg),'allowed_changed_group':'appearance'})
    source_path=out/'cases/source/physics_transforms.json'
    if not a.reuse_physics_from and a.stage in ['all','simulate'] and not(a.skip_existing and source_path.exists()):
        src=simulate(case_config());save_json(source_path,src);export_csv(source_path.with_name('trajectory.csv'),src)
    source=verified_result(source_path,'source',expected=case_config())
    for case in a.cases:
        folder=out/'cases'/case;path=folder/'physics_transforms.json';folder.mkdir(parents=True,exist_ok=True)
        if not a.reuse_physics_from and a.stage in ['all','simulate'] and case!='source' and not(a.skip_existing and path.exists()):
            r=simulate(case_config(case));save_json(path,r);export_csv(folder/'trajectory.csv',r)
        r=verified_result(path,case,None if case=='source' else source,case_config(case))
        actual_cfg=visual_config(r['configuration'])
        save_json(folder/'settings.json',actual_cfg);save_json(folder/'config_diff.json',{'before':cfg,'after':actual_cfg,'differences':differences(cfg,actual_cfg)})
        save_json(folder/'contacts.json',{'events':r['contact_events'],'intervention_events':r.get('intervention_events',[]),'episodes':r['outcome']['contact_episodes'],'raw_solver_intervals':r['outcome']['raw_solver_contact_intervals']})
        save_json(folder/'prompts.json',{'scene':'ramp_car_ball_collision','case_id':case,'source_case_id':'source',**edit_info(case)})
        rec={'case_id':case,'status':'physics_accepted','outcome':{k:v for k,v in r['outcome'].items() if k not in ['first_collision','raw_solver_contact_intervals']},
            'physics_override':CASES[case],'configuration_sha256':signature(actual_cfg),'solver_configuration_sha256':signature(r['configuration']),'simulation_sec':r['simulation_wall_sec'],
            'outputs':{k:str(folder/f) for k,f in [('video','video.mp4'),('physics','physics_transforms.json'),('csv','trajectory.csv'),('blend','ramp_car_ball_collision.blend'),('annotations','ground_truth_transforms.json')]}}
        if a.stage in ['all','render']:
            if case!='source':
                review=out/'cases/source/case_acceptance.json'
                if not review.exists() or not load(review).get('accepted'):raise RuntimeError('Source full-video visual acceptance must be recorded before rendering formal edits.')
                assert load(review)['video_sha256']==sha(source_path.with_name('video.mp4'))
                assert load(review)['physics_sha256']==sha(source_path)
            if not(a.skip_existing and (folder/'video_validation.json').exists()):
                cmd=[str(a.blender),'-b','-t',os.environ.get('OMP_NUM_THREADS','6'),'--python-exit-code','1','--python',str(HERE/'render_ramp_car_ball_collision.py'),'--',
                    '--physics-json',str(path),'--out-dir',str(folder),'--mode','animation','--device',a.device]
                if a.skip_existing:cmd.append('--skip-existing')
                if a.synchronized_cache:cmd.append('--synchronized-cache')
                if a.refresh_dynamic_only:cmd.append('--refresh-dynamic-only')
                if a.appearance_json:cmd+=['--appearance-json',str(a.appearance_json.resolve())]
                with (folder/'render.log').open('w') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        if a.stage in ['all','render','verify']:
            subprocess.run([sys.executable,str(ROOT/'scripts/pcve_verify_video.py'),str(folder/'video.mp4'),'--out',str(folder/'video_validation.json'),
                '--resolution',*[str(x) for x in actual_cfg['render']['resolution']],'--fps',str(actual_cfg['render']['fps']),'--frames',str(round(actual_cfg['render']['fps']*actual_cfg['render']['duration_sec']))],check=True)
            rec['status']='video_verified_pending_visual_review';rec['video_sha256']=sha(folder/'video.mp4')
            if (folder/'case_acceptance.json').exists():
                review=load(folder/'case_acceptance.json')
                if review.get('accepted') and review['physics_sha256']==sha(path) and review['video_sha256']==sha(folder/'video.mp4'):rec['status']='accepted'
        manifest['cases'][case]=rec;save_json(manifest_path,manifest);print(case,rec['status'],flush=True)
    manifest['status']='accepted' if len(manifest['cases'])==len(CASES) and all(v['status']=='accepted' for v in manifest['cases'].values()) else 'in_progress'
    save_json(manifest_path,manifest)
    save_json(out/'implementation_manifest.json',{'python':sys.executable,
        'asset_manifest':'assets.json','solver':source['solver'],'configuration_sha256':signature(cfg),
        'limitations':['Rigid hollow-sphere approximation; no PVC deformation','No calibration against a measured physical toy experiment',
            'Native Bullet rolling/spinning constraints are a load-limited contact approximation; no hidden velocity brake',
            'Fixed 4-second observation; 240 Hz pose replay with a 0.15-frame shutter']})
if __name__=='__main__':main()
