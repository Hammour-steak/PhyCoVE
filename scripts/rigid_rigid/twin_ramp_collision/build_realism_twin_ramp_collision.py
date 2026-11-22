"""Render an appearance-only variant from byte-identical accepted dynamics."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from scene_config import BASELINE, CASES, differences, signature,visual_override,visual_difference,formal_quality_equal
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import blender

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]

def load(p):return json.loads(Path(p).read_text())
def dump(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+"\n")
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out-root',type=Path,required=True)
    ap.add_argument('--physics-source-root',type=Path,default=ROOT/'renders/twin_ramp_collision/native')
    ap.add_argument('--appearance-json',type=Path,help='Visual-only override; default: the appearance and photographic shutter in scene_config.py')
    ap.add_argument('--stage',choices=['prepare','render','verify','all'],default='all')
    ap.add_argument('--gpus',nargs='+',default=[str(i) for i in range(8)])
    ap.add_argument('--blender',type=Path,default=blender())
    a=ap.parse_args();out=a.out_root.resolve();source=a.physics_source_root.resolve()
    if out==source:raise ValueError('Realism output must be isolated from the accepted source')
    override=load(a.appearance_json) if a.appearance_json else {'appearance':copy.deepcopy(BASELINE['appearance']),'render':{k:BASELINE['render'][k] for k in ('motion_blur_shutter_frames','persistent_data')}}
    original=load(source/'cases/source/physics_transforms.json')['configuration']
    before=load(source/'cases/source/settings.json') if (source/'cases/source/settings.json').is_file() else original
    assert all(before[k]==original[k] for k in ['physics','simulation_quality']) and formal_quality_equal(before,original)
    after=visual_override(before,override);diff=differences(before,after)
    if any(not visual_difference(k) for k in diff):raise ValueError('The override must change appearance only')
    manifest_path=out/'suite_manifest.json'
    if manifest_path.exists():
        manifest=load(manifest_path)
        assert manifest['configuration']==after,'Changed look requires an isolated output root'
    else:
        if out.exists() and any(out.iterdir()):raise FileExistsError(out)
        manifest={'schema_version':1,'scene':'twin_ramp_collision','revision':override['appearance']['preset'],'configuration':after,
            'physics_source_root':str(source),'status':'preparing','cases':[]}
    frozen=[]
    for case in CASES:
        src=source/'cases'/case;dst=out/'cases'/case;dst.mkdir(parents=True,exist_ok=True)
        assert load(src/'physics_validation.json')['accepted']
        for name in ['physics_transforms.json','trajectory.csv','contacts.json','prompts.json','physics_validation.json']:
            origin=src/name;target=dst/name
            if target.exists():assert sha(origin)==sha(target),f'Frozen input changed: {target}'
            else:shutil.copy2(origin,target)
        cfg=visual_override(load(src/'physics_transforms.json')['configuration'],override)
        dump(dst/'settings.json',cfg)
        dump(dst/'config_diff.json',{'before':after,'after':cfg,'differences':differences(after,cfg)})
        frozen.append({'case_id':case,'origin':str(src/'physics_transforms.json'),'replay':str(dst/'physics_transforms.json'),
            'sha256':sha(src/'physics_transforms.json'),'physics_sha256':signature(cfg['physics']),
            'simulation_quality_sha256':signature(cfg['simulation_quality'])})
    manifest['cases']=frozen;manifest['status']='physics_reused_unchanged';dump(manifest_path,manifest)
    dump(out/'appearance_override.json',override)
    dump(out/'appearance_diff.json',{'before':before,'after':after,'differences':diff,'allowed_scope':'appearance, render.motion_blur_shutter_frames and render.persistent_data',
        'physics_byte_identical':True,'simulation_rerun':False,'same_preset_reproduction':not bool(diff),'formal_render_quality_unchanged':formal_quality_equal(before,after)})
    if a.stage in ['all','render']:
        subprocess.run([sys.executable,str(HERE/'physics/render_queue.py'),'--out-root',str(out),'--appearance-json',str(out/'appearance_override.json'),
            '--blender',str(a.blender),'--gpus',*a.gpus],check=True)
    if a.stage in ['all','verify']:
        for case in CASES:
            f=out/'cases'/case
            rd=after['render']
            subprocess.run([sys.executable,str(ROOT/'scripts/pcve_verify_video.py'),str(f/'video.mp4'),'--out',str(f/'video_validation.json'),
                '--resolution',*[str(v) for v in rd['resolution']],'--fps',str(rd['fps']),'--frames',str(round(rd['fps']*rd['duration_sec']))],check=True)
        subprocess.run([sys.executable,str(HERE/'physics/audit_twin_ramp_collision.py'),'--out-root',str(out)],check=True)
        with (out/'saved_scene_audit.log').open('w') as log:
            subprocess.run([str(a.blender),'-b','-t','4','--python-exit-code','1','--python',str(HERE/'appearance/audit_saved_scenes.py'),'--',str(out)],stdout=log,stderr=subprocess.STDOUT,check=True)
        invariants=[]
        for row in frozen:
            invariants.append({'case_id':row['case_id'],'origin_unchanged':sha(row['origin'])==row['sha256'],
                'replay_byte_identical':sha(row['replay'])==row['sha256']})
        checks={'every_formal_frame':load(out/'render_audit.json')['passed'],
            'saved_scene_and_solved_poses':load(out/'saved_scene_audit.json')['passed'],
            'all_original_dynamics_unchanged':all(r['origin_unchanged'] and r['replay_byte_identical'] for r in invariants),
            'only_declared_visual_changes':all(visual_difference(k) for k in diff),
            'formal_quality_unchanged':formal_quality_equal(before,after)}
        dump(out/'realism_validation.json',{'passed':all(checks.values()),'checks':checks,'frozen_dynamics':invariants,
            'visual_review':'Manual full-video review required separately; frame count/pose checks do not certify realism'})
        if not all(checks.values()):raise RuntimeError(checks)
        manifest['status']='technically_verified_pending_visual_review';dump(manifest_path,manifest)
    assets_manifest=HERE/after['appearance'].get('asset_manifest','realism_assets.json')
    dump(out/'implementation_manifest.json',{'appearance_sha256':signature(after['appearance']),'physics_reused':True,'runtime_python':sys.executable,
        'asset_manifest':str(assets_manifest),'asset_manifest_sha256':sha(assets_manifest)})

if __name__=='__main__':main()
