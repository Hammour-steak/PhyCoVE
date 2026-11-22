"""Case-local packaging with the shared default physical-edit policy preflight."""

from pathlib import Path
import argparse,ast,json,shutil,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'physics'))
from baseline import CASE,LAYOUT,save,sha
from vocab import VOCAB,CASES,resolve
from pcve_edit_policy import audit_suite_manifest
import pcve_edit_dsl as dsl
from pcve_media_contract import require_video,require_times

BUILDER=Path(__file__).resolve().parents[1]/f'build_pcve_{CASE}.py'

def catalog_constant(name):
    """A literal catalog constant (PCVE_SOURCE / PCVE_EDITS) of the scene builder, read without importing it."""
    for node in ast.parse(BUILDER.read_text(encoding='utf8')).body:
        if isinstance(node,ast.Assign) and any(getattr(t,'id',None)==name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['metadata','validate','package'],default='metadata')
    ap.add_argument('--root',type=Path,required=True,help='native delivery folder with cases/<case>/')
    ap.add_argument('--simulation-root',type=Path,help='native solver outputs <root>/<case>/ (package stage)')
    ap.add_argument('--simulation-run',default='',help='optional run folder inside each case, e.g. run1 (<root>/<case>/run1/)')
    a=ap.parse_args();root=a.root
    DESCRIPTION=catalog_constant('PCVE_SOURCE')['prompts']
    edit_prompts={c:e['prompts'] for c,e in catalog_constant('PCVE_EDITS').items()}
    records=[]
    for case,text in CASES.items():
        p,info=resolve(case);out=root/'cases'/case;out.mkdir(parents=True,exist_ok=True)
        if text:info['prompts']=edit_prompts[case]
        payload={'physics':p,'layout':LAYOUT}
        if a.stage=='metadata':
            save(out/'scenario_overrides.json',payload);save(out/'edit.json',info)
        else:
            if a.stage=='package':
                if a.simulation_root is None:ap.error('--stage package needs --simulation-root')
                simulation=a.simulation_root/case/a.simulation_run
                audit_source=simulation/'physics_audit.json';audit_target=out/'physics_audit.json'
                if not audit_target.exists()or not audit_source.samefile(audit_target):shutil.copy2(audit_source,audit_target)
            actual=json.loads((out/'scenario_overrides.json').read_text(encoding='utf8'))
            if actual!=payload:raise RuntimeError('Actual scenario differs from DSL: '+case)
            for name in ['video.mp4','simulation_config.json','cache.npz','physics_audit.json','render_manifest.json','gt.json','instance_masks.npz']:
                if not(out/name).is_file():raise FileNotFoundError(out/name)
            config=json.loads((out/'simulation_config.json').read_text(encoding='utf8'))
            if config['physics']!=p or config['layout']!=LAYOUT:raise RuntimeError('Simulated config mismatch: '+case)
            if a.stage=='package':
                import numpy as np
                require_video(out/'video.mp4');require_times(np.load(out/'cache.npz')['times'].tolist())
                from standardize_case import export
                export(case,out,simulation,info['prompts'])
        rec=dict(case_id=case,source_case_id='source',video=f'cases/{case}/video.mp4',edit_dsl=text,prompts=info['prompts'],
            applies_from_frame=1,material_calibrated=False,accepted_benchmark_gt=False,
            numerical_settings={'dt':1/240,'cloth_pitch_m':.009,'fps':24})
        if case=='source':
            rec['description']=DESCRIPTION
            if a.stage=='package':
                save(out/'prompts.json',dict(schema_version=1,case_id=case,kind='source',prompts=DESCRIPTION,editable_objects=dsl.editable_objects(VOCAB)))
                descriptor=json.loads((out/'artifact_manifest.json').read_text(encoding='utf8'))
                for entry in descriptor['files']:
                    if entry['path']=='prompts.json':entry.update(bytes=(out/'prompts.json').stat().st_size,sha256=sha(out/'prompts.json'))
                save(out/'artifact_manifest.json',descriptor)
        elif text:
            e=dsl.parse(text,VOCAB)
            if isinstance(e,dsl.SetEdit):
                rec['physics_diff']={f'{e.property_name} ({e.object_id})':{'from':e.from_value,'to':e.to_value}}
            else:rec['physics_diff']={e.object_id:{'from':'present'if isinstance(e,dsl.DeleteEdit)else'absent','to':'removed'if isinstance(e,dsl.DeleteEdit)else'present'}}
        records.append(rec)
    manifest=dict(schema_version=3,scene_id=CASE,interaction_category='rigid_elastic',
        source=records[0],edits=records[1:],status='metadata_only'if a.stage=='metadata'else'complete',
        review_status='pending_user_review',fps=24,width=1280,height=720,total_frames=96,duration=4.,
        physics_acceptance_status='pending_native_simulation_and_render'if a.stage=='metadata'else'implementation_and_sampled_contact_checks_passed; fold_trajectory_convergence_not_established',
        accepted_benchmark_gt=False,material_calibrated=False,numerical_checks_passed=False,
        implementation_and_contact_checks_passed=a.stage!='metadata',numerical_fold_trajectory_convergence_established=False,
        completion_scope='Six native physical simulations, render replay, edit policy, videos and GT; material parameters are effective, not product calibrated.',
        asset_manifest='cases/source/asset_credits.json',hand_authored_motion=False,
        main_review_registry_changed=False,baseline_revision='no_hardware_settled')
    policy=audit_suite_manifest(manifest,VOCAB,suite_root=root)
    if not policy['all_edits_compliant']:raise RuntimeError(json.dumps(policy,ensure_ascii=False))
    save(root/'global_edit_policy_preflight.json',policy);save(root/'suite_manifest.json',manifest)
    if a.stage=='package':
        files=[p for p in root.rglob('*')if p.is_file()and p.name!='artifact_manifest.json']
        save(root/'artifact_manifest.json',{'files':[dict(path=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=sha(p))for p in files]})
    print(json.dumps({'stage':a.stage,'cases':len(records),'policy_passed':True,'root':str(root)},indent=2))

if __name__=='__main__':main()
