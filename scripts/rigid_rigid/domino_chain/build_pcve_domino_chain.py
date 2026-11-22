"""Build the validated five-domino source and single-target counterfactuals."""
from __future__ import annotations
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import blender as default_blender
from pcve_project_paths import suite_output_root
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__=='__main__':
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    if _PcvePath(__file__).with_name('entrypoints.json').is_file():
        _pcve_sys.path.insert(0,str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__,'build_pcve')
# PCVE_UNIFIED_ENTRY_END
import argparse, copy, hashlib, json, math, os, subprocess, sys, time
from pathlib import Path
from edit_vocab import VOCAB, dsl
from simulate_domino_chain import simulate, write_json, scenario, differences, signature, BASELINE_PHYSICS, RENDER

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
SOURCE='domino_chain_baseline'
CASES={SOURCE:('source',None),
       'edit_heavy_D03':('heavy','SET D03.mass TIMES 10'),
       'edit_remove_D03':('remove','DELETE D03'),
       'edit_remove_D01':('remove_first','DELETE D01'),
       'edit_remove_D01_after_contact':('remove_first_after_contact','DELETE D01 AT FRAME 13'),
       'edit_heavy_D01':('heavy_first','SET D01.mass TIMES 10'),
       'edit_heavy_D04':('heavy_fourth','SET D04.mass TIMES 10')}
SUMMARIES={
    'edit_heavy_D03':'D03 mass only: 16 g to 160 g. D01 falls; D02 leans against D03. D03 rocks and returns upright, blocking D04 and D05.',
    'edit_remove_D03':'D03 is absent from t=0. D01 and D02 fall; D02 never bridges or slides across the gap. D04 and D05 remain upright.',
    'edit_remove_D01':'D01 is absent from t=0. With the initially tilted trigger removed, D02--D05 remain freely simulated, upright and separated for the whole clip.',
    'edit_remove_D01_after_contact':'Delete D01 at frame 13 (0.500000 s), after D01 has begun pushing D02. Motion before deletion and the impulse already transferred to D02 are retained.',
    'edit_heavy_D01':'Only D01 mass increases from 16 g to 160 g; its collision inertia changes with mass and the following motion is solved freely.',
    'edit_heavy_D04':'Only D04 mass increases from 16 g to 160 g; the interaction of the arriving dominoes and the heavier fourth tile is solved freely.'}


def edit_info(statement):
    edit=dsl.parse(statement,VOCAB)
    override=dsl.to_scenario_override(edit,VOCAB)
    if statement.startswith('SET'):
        diff={f'{edit.property_name} ({edit.object_id})':{'from':dsl.baseline_value_for(edit,VOCAB),'to':edit.to_value}}
    else:diff={edit.object_id:{'from':'present','to':'removed'}}
    diff['timing']=dsl.timing_diff(edit,VOCAB)
    prompts=dsl.make_prompts(edit,VOCAB)
    return {'edit_dsl':statement,'prompts':prompts,'physics_diff':diff,
            'physics_override':override,'applies_from_frame':dsl.starts_at_frame(edit)}


# Acceptance of the actual solver contacts and poses, not the intended story.
def validate(result, kind):
    q = result["quality"]
    maximum, final = q["max_tilt_deg_per_domino"], q["final_tilt_deg_per_domino"]
    pairs = [c["objects"] for c in result["contact_events"]]
    checks = {
        "initial_zero_linear_and_angular_velocities": all(v == [0.0]*3 for v in result["initial_linear_velocities"]+result["initial_angular_velocities"]),
        "initial_no_penetration": result["initial_max_penetration_m"] < 1e-6,
        "no_prescribed_motion_or_forces_or_constraints": not result["prescribed_motion"] and not result["constraints"] and not result["external_forces"],
        "no_premature_tipping": not q["premature_tipping_ids"],
        "penetration_below_0p1_mm": q["max_penetration_m"] < 0.0001,
        "stable_last_half_second": q["tail_max_equivalent_speed_m_per_s"] < 0.0005,
        "last_half_second_position_range_below_0p05mm": max(q["tail_position_range_m"]) < 0.00005,
        "last_half_second_tilt_range_below_0p05deg": max(q["tail_tilt_range_deg"]) < 0.05,
        "base_slide_before_45deg_below_1mm": max(q["base_slide_before_45deg_m"]) < 0.001,
    }
    if result["configuration"]["physics"]["domino_active"][0]:
        checks["initial_D01_D02_clearance"] = result["initial_pair_clearance_m"]["D01-D02"] > 0.01
        checks["initial_D01_beyond_stability_boundary"] = result["configuration"]["physics"]["push_angle_deg"] > result["critical_angle_deg"]
    if kind == "source":
        checks.update({"actual_contact_order": pairs == [["D01", "D02"], ["D02", "D03"], ["D03", "D04"], ["D04", "D05"]],
                       "all_five_fall": all(v > 45 for v in maximum),
                       "last_tile_flat": abs(final[4]-90) < 1})
    elif kind == "heavy":
        checks.update({"actual_contact_order": pairs == [["D01", "D02"], ["D02", "D03"]],
                       "first_two_reach_D03": maximum[0] > 45 and maximum[1] > 25,
                       "D03_rocks_below_critical_angle": maximum[2] < result["critical_angle_deg"],
                       "D03_stays_standing_at_end": final[2] < result["critical_angle_deg"],
                       "D04_D05_stay_upright": max(maximum[3:]) < 0.2})
    elif kind == "remove":
        checks.update({"actual_contact_order": pairs == [["D01", "D02"]],
                       "D03_absent_before_simulation": result["configuration"]["physics"]["domino_active"] == [1, 1, 0, 1, 1],
                       "D01_D02_fall": maximum[0] > 45 and maximum[1] > 80,
                       "D04_D05_stay_upright": max(maximum[3:]) < 0.2,
                       "D02_never_reaches_D04": q["min_D02_D04_clearance_m"] > 0.005})
    elif kind == "remove_first":
        recorded = result["frames"] + result.get("trajectory_samples", [])
        displacement = max(sum((pose["location"][k] - result["initial_locations"][i][k])**2 for k in range(3))**0.5
                           for record in recorded for i, pose in enumerate(record["dominoes"]) if pose["present"])
        checks.update({"D01_absent_before_simulation": result["configuration"]["physics"]["domino_active"] == [0, 1, 1, 1, 1],
                       "D01_absent_in_every_solved_sample": all(not record["dominoes"][0]["present"] for record in recorded),
                       "D02_D05_present_in_every_solved_sample": all(all(pose["present"] for pose in record["dominoes"][1:]) for record in recorded),
                       "no_domino_to_domino_contacts": pairs == [],
                       "D02_D05_stay_upright": max(maximum[1:]) < 0.2,
                       "no_remaining_domino_topples": q["toppled_count"] == 0,
                       "remaining_domino_displacement_below_0p05mm": displacement < 0.00005})
    elif kind == "remove_first_after_contact":
        events=result.get('interventions',[])
        removals=[event for event in events if event['kind']=='DELETE' and event['object_id']=='D01']
        event=removals[0] if len(removals)==1 else None
        contact=next((c for c in result['contact_events'] if c['objects']==['D01','D02']),None)
        requested=result['configuration']['physics']['timed_edits']
        requested_frame=requested[0]['frame']
        requested_time=(requested_frame-1)/result['fps']
        checks.update({"single_D01_removal": len(removals)==1,
                       "D01_present_before_requested_frame": all(frame['dominoes'][0]['present'] for frame in result['frames'] if frame['frame_index']<requested_frame),
                       "D01_absent_from_requested_frame": all(not frame['dominoes'][0]['present'] for frame in result['frames'] if frame['frame_index']>=requested_frame),
                       "remaining_dominoes_always_present": all(all(pose['present'] for pose in frame['dominoes'][1:]) for frame in result['frames']),
                       "removal_at_requested_frame": len(requested)==1 and bool(event) and event['frame_index']==requested_frame and abs(event['time_sec']-requested_time)<1e-12,
                       "removal_after_actual_D01_D02_contact": bool(event) and bool(contact) and event['time_sec']>contact['first_time_sec'],
                       "D01_has_no_contacts_after_removal": bool(event) and all(c['last_time_sec']<=event['time_sec']+result['physics_dt'] for c in result['contact_events'] if 'D01' in c['objects']),
                       "D02_receives_motion_before_removal": any(frame['dominoes'][1]['linear_velocity']!=[0.0]*3 for frame in result['trajectory_samples'] if bool(contact) and contact['first_time_sec']<=frame['time_sec']<requested_time)})
    elif kind in ["heavy_first", "heavy_fourth"]:
        index=0 if kind=='heavy_first' else 3
        target=f'D{index+1:02}'
        # A stronger transmitted collision may physically slide a tile before it
        # tips. Preserve the contact solve and record this response; the source's
        # visual no-slip gate is not a constraint on these mass counterfactuals.
        checks.pop("base_slide_before_45deg_below_1mm")
        if kind=='heavy_fourth':
            # Supported rocking has tiny displacement and angle variation, but
            # its peak instantaneous speed need not meet the source's gate.
            # Retain both strict tail pose-range checks and the measured speed.
            checks.pop("stable_last_half_second")
        checks.update({"heavier_target_has_dynamic_mass": result['configuration']['physics']['domino_masses'][index]==0.16,
                       "collision_reaches_target": any(target in pair for pair in pairs),
                       "chain_starts_at_D01_D02": bool(pairs) and pairs[0]==['D01','D02'],
                       "base_sliding_is_finite": all(math.isfinite(value) and value>=0 for value in q['base_slide_before_45deg_m'])})
    elif kind == "friction":
        # A candidate may slide: base-slide check is intentionally not an acceptance requirement.
        checks.pop("base_slide_before_45deg_below_1mm")
    else:
        raise ValueError(kind)
    return {"kind": kind, "accepted": all(checks.values()), "checks": checks,
            "contact_order": pairs, "quality": q}


def accept_case(result,kind,source_cfg):
    report=validate(result,kind)
    if kind!='source':
        changed=differences(source_cfg,result['configuration'])
        expected={'heavy':'physics.domino_masses.2','remove':'physics.domino_active.2','remove_first':'physics.domino_active.0',
                  'remove_first_after_contact':'physics.timed_edits','heavy_first':'physics.domino_masses.0',
                  'heavy_fourth':'physics.domino_masses.3','friction':'physics.domino_frictions.2'}[kind]
        report['parameter_audit']={'before':source_cfg,'after':result['configuration'],'actual_diff':changed,'expected_changed_fields':[expected],
                                   'accepted':set(changed)=={expected}}
        report['accepted'] &= report['parameter_audit']['accepted']
    return report


def graybox(root):
    """Reproducible mass/friction search, gated by an accepted source simulation."""
    root=Path(root)
    source=simulate(scenario())
    check=accept_case(source,'source',scenario())
    write_json(root/'source/physics_transforms.json',source)
    write_json(root/'source/physics_validation.json',check)
    print('source',check['accepted'],source['quality'],flush=True)
    if not check['accepted']:
        raise RuntimeError('Source gate failed; do not build counterfactuals.')
    mass_rows=[]
    for factor in [1,2,4,6,6.5,6.75,7,7.25,7.5,8,10,12,16]:
        masses=[0.016]*5; masses[2]*=factor
        cfg=scenario({'physics':{'domino_masses':masses}})
        result=simulate(cfg,record_frames=False)
        check=validate(result,'heavy')
        write_json(root/f'experiments/mass_{factor:g}.json',result)
        mass_rows.append({'factor':factor,'mass_kg':masses[2],**check})
        print('mass',factor,check['accepted'],[round(x,3) if x is not None else None for x in result['quality']['max_tilt_deg_per_domino']],{k:v for k,v in check['checks'].items() if not v},flush=True)
    write_json(root/'experiments/mass_scan.json',{'trials':mass_rows,'interpretation':'Only sampled masses are experimentally verified; bracket boundaries are not a universal threshold.'})
    for name,kind,override in [('edit_heavy_D03','heavy',{'domino_masses':[.016,.016,.160,.016,.016]}),
                               ('edit_remove_D03','remove',{'domino_active':[1,1,0,1,1]})]:
        result=simulate(scenario({'physics':override}))
        check=accept_case(result,kind,scenario())
        write_json(root/name/'physics_transforms.json',result)
        write_json(root/name/'physics_validation.json',check)
        write_json(root/name/'scenario_overrides.json',{'physics':override})
        print(name,check['accepted'],result['quality'],flush=True)
    friction_rows=[]
    for friction in [.3,.1,.03,.01,.003,0.0]:
        cfg=scenario({'physics':{'domino_frictions':[.65,.65,friction,.65,.65]}})
        result=simulate(cfg)
        check=validate(result,'friction')
        xdelta=abs(result['final_state'][2]['location'][0]-source['final_state'][2]['location'][0])
        changed=max(result['quality']['base_slide_before_45deg_m'][2],xdelta)>.005
        check['clear_dynamic_difference']=changed
        check['D03_final_x_difference_m']=xdelta
        write_json(root/f'experiments/friction_{friction:g}/physics_transforms.json',result)
        write_json(root/f'experiments/friction_{friction:g}/physics_validation.json',check)
        friction_rows.append({'friction':friction,**check})
        print('friction',friction,check['accepted'],changed,'base_slide',result['quality']['base_slide_before_45deg_m'][2], 'xdelta',xdelta,flush=True)
    write_json(root/'experiments/friction_scan.json',{'trials':friction_rows})
    return source


def replay_physics(source_root,case_id,case_cfg,case_dir):
    """Replay accepted contacts; permit only appearance and a uniform support-height translation."""
    path=source_root.expanduser().resolve()/'cases'/case_id/'physics_transforms.json'
    original=json.loads(path.read_text());result=copy.deepcopy(original)
    old_ph=copy.deepcopy(original['configuration']['physics'])
    dz=case_cfg['physics']['floor_z']-old_ph['floor_z']
    old_ph['floor_z']=case_cfg['physics']['floor_z']
    if old_ph!=case_cfg['physics']:
        raise ValueError(f'Frozen replay mismatch: {case_id}/physics (only support height may translate)')
    for section in ['simulation_quality','render']:
        if original['configuration'][section]!=case_cfg[section]:
            raise ValueError(f'Frozen replay mismatch: {case_id}/{section}')
    # All coordinates in the physical interaction are translated together.
    # Gravity, collision geometry relative to the plane, velocities and forces
    # are invariant; this neither designs motion nor changes contact timing.
    if dz:
        for location in result['initial_locations']:
            location[2]+=dz
        for group in ['frames','trajectory_samples']:
            for record in result[group]:
                for pose in record['dominoes']:
                    pose['location'][2]+=dz
        for pose in result['final_state']:
            pose['location'][2]+=dz
        for record in list(result['all_contacts'].values())+result['contact_events']:
            record['first_position_on_b_m'][2]+=dz
        result['trajectory_provenance']={
            'method':'rigid_world_height_translation',
            'source_file':str(path),'source_file_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'translation_m':[0.0,0.0,dz],'solver_rerun':False,
            'description':'Accepted PyBullet collision trajectory under one declared uniform world-height translation; rotations, velocities, forces and event timing are unchanged.'}
    result['configuration']=copy.deepcopy(case_cfg)
    result['configuration_sha256']=signature(case_cfg)
    payload=lambda value:{k:v for k,v in value.items() if k not in ['configuration','configuration_sha256','trajectory_provenance']}
    before=signature(payload(original));after=signature(payload(result))
    if not dz:assert before==after
    write_json(case_dir/'appearance_replay.json',{
        'source_file':str(path),'source_file_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'frozen_payload_sha256':before,'replayed_payload_sha256':after,
        'same_every_solved_value':not bool(dz),'same_relative_trajectory':True,
        'world_height_translation_m':dz,'solver_rerun':False,
        'configuration_diff':differences(original['configuration'],case_cfg)})
    return result


def command(args,case_dir):
    blender=Path(args.blender).expanduser().resolve()
    return [str(blender),'-b','-t',str(args.threads_native),'--python-exit-code','1','--python',str(HERE/'render_domino_chain.py'),'--',
            '--mode','animation','--out-dir',str(case_dir),'--physics-json',str(case_dir/'physics_transforms.json'),'--device',args.device]


def parse_args():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-root',type=Path,default=suite_output_root('domino_chain'))
    p.add_argument('--stage',choices=['all','graybox','simulate','render','verify'],default='all')
    p.add_argument('--cases',nargs='+',choices=list(CASES),default=list(CASES))
    p.add_argument('--blender',type=Path,default=default_blender())
    p.add_argument('--device',choices=['auto','cpu'],default='auto');p.add_argument('--threads-native',type=int,default=8)
    p.add_argument('--skip-existing',action='store_true')
    p.add_argument('--physics-source-root',type=Path,help='Replay accepted solver outputs from this suite; Only appearance or one common support-height translation may change; all relative dynamics stay frozen.')
    return p.parse_args()


def main():
    args=parse_args();root=args.out_root.expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    args.threads_native=int(os.environ.get('OMP_NUM_THREADS',args.threads_native))
    if args.stage=='graybox':
        graybox(root/'graybox');return
    cfg=scenario()
    manifest_path=root/'suite_manifest.json'
    manifest={'schema_version':3,'suite_name':'pcve_domino_chain_suite','scene':'domino_chain','interaction_category':'rigid_rigid',
              'description':'Five real-scale ivory resin dominoes on a green-baize home card table, gravity-initiated free rigid-body contact chain.',
              'baseline_physics':BASELINE_PHYSICS,'configuration':cfg,'resolution':RENDER['resolution'],'fps':RENDER['fps'],
              'duration_sec':RENDER['duration_sec'],'samples':RENDER['samples'],'total_frames':round(RENDER['duration_sec']*RENDER['fps']),
              'source':None,'edits':[],'physics_model':'PyBullet free 6-DOF box collisions at quarter gravity; normalized Sketchfab visual meshes do not drive physics.',
              'appearance_sha256':signature(cfg['appearance']),'simulation_quality_sha256':signature(cfg['simulation_quality'])}
    if manifest_path.exists():
        old=json.loads(manifest_path.read_text())
        assert old['configuration']==cfg,'Output belongs to a different frozen configuration.'
        manifest=old
    if args.stage in ['all','simulate']:
        # Source gate is always evaluated before any edit, even in a case-filtered call.
        source_dir=root/'cases'/SOURCE;src_path=source_dir/'physics_transforms.json'
        source=(replay_physics(args.physics_source_root,SOURCE,cfg,source_dir) if args.physics_source_root else
                json.loads(src_path.read_text()) if args.skip_existing and src_path.exists() else simulate(cfg))
        src_check=accept_case(source,'source',cfg)
        write_json(src_path,source);write_json(source_dir/'physics_validation.json',src_check)
        if not src_check['accepted']:raise RuntimeError('Source physics acceptance failed.')
    for case_id in args.cases:
        kind,statement=CASES[case_id];case_dir=root/'cases'/case_id;case_dir.mkdir(parents=True,exist_ok=True)
        info=edit_info(statement) if statement else None
        record={'case_id':case_id,'kind':'source' if kind=='source' else 'edit','seed':cfg['appearance']['seed'],
                'case_dir':str(case_dir),'source_case_id':SOURCE,'status':'pending'}
        if info:
            record.update(info);record['edit_summary']=SUMMARIES[case_id]
            write_json(case_dir/'scenario_overrides.json',{'physics':info['physics_override']})
            write_json(case_dir/'prompts.json',{'schema_version':2,'case_id':case_id,'source_case_id':SOURCE,**info,'edit_summary':SUMMARIES[case_id]})
        else:
            record['description']={'vague':{'zh':'五块奶白色骨牌在绿色绒面家用牌桌上由重力和碰撞依次倒下。','en':'Five ivory dominoes fall in sequence on a green-baize home card table under gravity and contact.'},
                                   'quantitative':{'zh':f'五块 50×25×8 mm、每块 16 g 的奶白色骨牌在绿色绒面牌桌上从左到右直立排成一列，相邻骨牌中心相距 35 mm。最左边的第一块骨牌初始向右倾斜 12° 且静止，在 {abs(cfg["physics"]["gravity"][2]):g} m/s² 的重力加速度下倒下，碰撞沿着这一列依次传到第五块骨牌。',
                                                   'en':f'Five ivory 50 x 25 x 8 mm dominoes, 16 g each, stand upright in a row from left to right on a green-baize card table, with centres 35 mm apart. The first domino on the left starts at rest, tilted 12 degrees toward the second, falls under a gravitational acceleration of {abs(cfg["physics"]["gravity"][2]):g} m/s^2, and the impacts pass along the row to the fifth domino.'}}
            write_json(case_dir/'prompts.json',{'schema_version':2,'case_id':case_id,'prompts':record['description']})
        physics_path=case_dir/'physics_transforms.json'
        if args.stage in ['all','simulate']:
            case_cfg=scenario({'physics':info['physics_override']}) if info else cfg
            if case_id==SOURCE:result=source
            elif args.physics_source_root:result=replay_physics(args.physics_source_root,case_id,case_cfg,case_dir)
            elif args.skip_existing and physics_path.exists():result=json.loads(physics_path.read_text())
            else:result=simulate(case_cfg)
            assert result['configuration']==case_cfg
            report=accept_case(result,kind,cfg)
            write_json(physics_path,result);write_json(case_dir/'physics_validation.json',report)
            if not report['accepted']:raise RuntimeError(f'Physics acceptance failed: {case_id}')
            record['status']='physics_accepted';record['quality']=result['quality']
        elif not physics_path.exists():raise FileNotFoundError(physics_path)
        else:
            result=json.loads(physics_path.read_text());record['quality']=result['quality']
            report=accept_case(result,kind,cfg)
            if not report['accepted']:raise RuntimeError(f'Existing physics acceptance failed: {case_id}')
            write_json(case_dir/'physics_validation.json',report)
        if kind in ['remove_first_after_contact','heavy_first','heavy_fourth']:
            reference=json.loads((root/'cases'/SOURCE/'physics_transforms.json').read_text())
            if kind=='remove_first_after_contact':
                removal_frame=info['applies_from_frame'];prefix_end=removal_frame-1
                prefix_before=reference['frames'][:prefix_end];prefix_after=result['frames'][:prefix_end]
                prefix_check={'accepted':prefix_before==prefix_after,'frame_range':[1,prefix_end],
                              'source_contact_time_sec':reference['contact_events'][0]['first_time_sec'],
                              'deletion_time_sec':prefix_end/RENDER['fps'],'deletion_frame':removal_frame}
                write_json(case_dir/'source_prefix_validation.json',prefix_check)
                report['source_prefix_validation']=prefix_check;report['accepted'] &= prefix_check['accepted']
            else:
                index=0 if kind=='heavy_first' else 3
                distance=max(sum((a['location'][k]-b['location'][k])**2 for k in range(3))**0.5
                             for old,new in zip(reference['frames'],result['frames'])
                             for a,b in zip(old['dominoes'],new['dominoes']) if a['present'] and b['present'])
                difference_check={'accepted':distance>0.001,'maximum_object_position_difference_m':distance,
                                  'edited_object':f'D{index+1:02}'}
                write_json(case_dir/'source_difference_validation.json',difference_check)
                report['source_difference_validation']=difference_check;report['accepted'] &= difference_check['accepted']
            write_json(case_dir/'physics_validation.json',report)
            if not report['accepted']:raise RuntimeError(f'Counterfactual/source comparison failed: {case_id}')
        if args.stage in ['all','render']:
            t=time.perf_counter();log=case_dir/'render.log'
            if not(args.skip_existing and (case_dir/'video_validation.json').exists()):
                with log.open('w') as f:subprocess.run(command(args,case_dir),stdout=f,stderr=subprocess.STDOUT,check=True)
            record['render_pipeline_sec']=time.perf_counter()-t;record['status']='completed'
        if args.stage in ['all','render','verify']:
            subprocess.run([sys.executable,str(ROOT/'scripts/pcve_verify_video.py'),str(case_dir/'video.mp4'),
                            '--out',str(case_dir/'video_validation.json'),'--resolution',*map(str,RENDER['resolution']),'--fps',str(RENDER['fps']),'--frames',str(round(RENDER['duration_sec']*RENDER['fps']))],check=True)
            record['status']='completed'
            record['video_sha256']=hashlib.sha256((case_dir/'video.mp4').read_bytes()).hexdigest()
        record['outputs']={key:str(case_dir/file) for key,file in [('video','video.mp4'),('ground_truth','ground_truth_transforms.json'),('scenario_metadata','scenario_metadata.json'),('physics','physics_transforms.json'),('physics_validation','physics_validation.json')]}
        if kind=='source':manifest['source']=record
        else:
            manifest['edits']=[r for r in manifest['edits'] if r['case_id']!=case_id]+[record]
        write_json(manifest_path,manifest)
        print(case_id,record['status'],flush=True)
    write_json(root/'implementation_manifest.json',{'configuration':cfg,'configuration_sha256':signature(cfg),
              'runtime_python':sys.executable,'python_version':sys.version,'asset_manifests':[str(ROOT/'assets/polyhaven'/name/'asset_manifest.json') for name in ['oak_veneer_01','brown_photostudio_05','tea_set_01','suburban_field_01','rough_linen','sunny_rose_garden','potted_plant_04']]+[str(ROOT/'assets/sketchfab/dominoes_render_at_night/asset_manifest.json'),str(ROOT/'assets/public_domain/byron_knoll_cards/asset_manifest.json'),str(ROOT/'assets/ambientcg/Fabric034/asset_manifest.json'),str(ROOT/'assets/pcve/domino_chain_natural/asset_manifest.json'),str(ROOT/'assets/pcve/domino_chain_cards/asset_manifest.json'),str(ROOT/'assets/innerscene/mahjong_game_table/asset_manifest.json'),str(ROOT/'assets/blenderkit/modern_living_room_interior/asset_manifest.json'),str(ROOT/'assets/pcve/domino_chain_curtain_drape/asset_manifest.json'),str(ROOT/'assets/polyhaven/caban/asset_manifest.json')]})


if __name__=='__main__':main()
