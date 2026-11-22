"""Build the elastic-fluid duck suite: the selected base and physical edits.

The default source is the exact user-selected upright video, stored as a
hash-checked input asset independently of disposable output directories. Wet edits use
the consolidated MPM/DFSPH operator. DELETE water retains native elastic MPM
with aligned empty-pool floor contact. Every case is rendered with the same look
(render_elastic_fluid_duck.LOOK): after the surface stage, cases with water
compute the splash detail, the sun occluders, the pool caustics and the wet surfaces.
Each completed edit retains video.mp4 and its bilingual prompts.json.
"""
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import blender
from pcve_project_paths import suite_output_root
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'build_pcve')
# PCVE_UNIFIED_ENTRY_END
import argparse
import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0,str(HERE))
from render_elastic_fluid_duck import LOOK, REAL_SAMPLES
LOOK_PHASES = ('splash','occluders','caustics','wetness')  # CPU inputs of the look, for cases with water
CODE_FILES = ('simulate_elastic_fluid_duck.py','render_elastic_fluid_duck.py','build_pcve_elastic_fluid_duck.py',
              'physics/optics_elastic_fluid_duck.py','physics/splash_elastic_fluid_duck.py','physics/caustics_elastic_fluid_duck.py',
              'physics/wetness_elastic_fluid_duck.py')
SOURCE_CASE_ID = 'elastic_fluid_duck_baseline'
DELETE_WATER_CASE_ID = 'edit_delete_water_contact_fixed'
EDIT_CASES = (
    {'case_id':'edit_heavy_duck', 'edit_dsl':'SET duck.mass TIMES 5.5',
     'edit_summary':'Increase duck mass at the same shape and volume; the target motion is sinking.'},
    {'case_id':'edit_viscous_liquid', 'edit_dsl':'SET water.viscosity TIMES 400000',
     'edit_summary':'Increase liquid viscosity while retaining its density and optical material; the target is suppressed splash and waves.'},
    {'case_id':'edit_delete_duck', 'edit_dsl':'DELETE duck',
     'edit_summary':'Remove the duck from the very first frame, including its MPM material and SPH pressure boundary; water and the environment are unchanged.'},
    {'case_id':DELETE_WATER_CASE_ID, 'edit_dsl':'DELETE water',
     'edit_summary':'Remove all pool water from the first frame. The same elastic duck falls onto the unchanged pool floor, using mass-preserving refined MPM particle quadrature and explicit rigid-plane contact to resolve impact without numerical fracture. No water, prescribed motion, rotation lock or render-only repair remains.'},
    {'case_id':'edit_low_density_liquid_slow_sink_185', 'edit_dsl':'SET water.density TIMES 0.185',
     'edit_summary':'Use a less extreme liquid-density reduction than the previous 100 kg/m3 variant; target slower underwater descent and reduced splash while remaining submerged in the last second. Duck mass, dynamic viscosity and optical properties are unchanged.'},
    {'case_id':'edit_low_density_liquid_after_float_185_f73',
     'edit_dsl':'SET water.density TIMES 0.185 AT FRAME 73',
     'edit_summary':'At t=3.00 s, after the unchanged duck is floating comparatively steadily, reduce liquid density from 1000 to 185 kg/m3. Continue the live MPM/DFSPH state without resetting positions, velocities or deformation; the target is visible descent after floating.'},
)
EDIT_PHYSICS_FIELDS = {
    'edit_heavy_duck': {'duck_density_kg_m3','duck_nominal_mass_kg'},
    'edit_viscous_liquid': {'water_dynamic_viscosity_pa_s'},
    'edit_delete_duck': {'duck_presence'},
    DELETE_WATER_CASE_ID: {'water_presence'},
    'edit_low_density_liquid_slow_sink_185': {'water_density_kg_m3','water_target_mass_kg'},
    'edit_low_density_liquid_after_float_185_f73': {'water_density_kg_m3','water_target_mass_kg'},
}


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            value.update(block)
    return value.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf8')
    temporary.replace(path)


def vocabulary(root, manifest, profile):
    sys.path.insert(0,str(root/'scripts'))
    import pcve_edit_dsl as dsl
    baseline = copy.deepcopy(profile['physics'])
    baseline['duck_mass_kg'] = manifest['base_actual']['duck_discrete_mass_kg']
    baseline['duck_presence'] = [1]
    baseline['water_presence'] = [1]
    vocab = dsl.Vocabulary(
        objects={'duck':{'zh':'黄鸭','en':'the yellow duck'},'water':{'zh':'泳池中的液体','en':'the liquid in the pool'}},
        properties={'mass':dsl.PropertySpec('scalar','kg','质量','mass'),
                    'viscosity':dsl.PropertySpec('scalar','Pa·s','动力黏度','dynamic viscosity'),
                    'density':dsl.PropertySpec('scalar','kg/m³','密度','density')},
        sim_bindings={('duck','mass'):dsl.SimBinding('duck_mass_kg'),
                      ('water','viscosity'):dsl.SimBinding('water_dynamic_viscosity_pa_s'),
                      ('water','density'):dsl.SimBinding('water_density_kg_m3')},
        delete_bindings={'duck':dsl.DeleteBinding('duck_presence',0),
                         'water':dsl.DeleteBinding('water_presence',0)},baseline_physics=baseline,total_frames=96)
    return dsl,vocab


def make_plans(root, assets):
    manifest = json.loads((assets/'asset_manifest.json').read_text())
    assert digest(assets/'scene_spec.json') == manifest['files']['scene_spec.json']['sha256']
    profile = json.loads((assets/'scene_spec.json').read_text())
    dsl,vocab = vocabulary(root,manifest,profile)
    plans = [{'case_id':SOURCE_CASE_ID, 'kind':'source', 'edit_dsl':None,
              'physics':copy.deepcopy(profile['physics']), 'prompts':None, 'physics_override':{}}]
    for edit in EDIT_CASES:
        parsed = dsl.parse(edit['edit_dsl'],vocab)
        overrides = dsl.to_scenario_override(parsed,vocab)
        final_overrides = dsl.to_physics_override(parsed,vocab)
        physics = copy.deepcopy(profile['physics'])
        if 'duck_mass_kg' in final_overrides:
            ratio = parsed.factor if parsed.factor is not None else final_overrides['duck_mass_kg']/manifest['base_actual']['duck_discrete_mass_kg']
            physics['duck_density_kg_m3'] *= ratio
            physics['duck_nominal_mass_kg'] *= ratio
        else:
            physics.update(final_overrides)
        if 'water_density_kg_m3' in final_overrides:
            # Derived mass label at fixed initial liquid geometry, not another independent edit.
            physics['water_target_mass_kg'] = profile['physics']['water_target_mass_kg'] * physics['water_density_kg_m3']/profile['physics']['water_density_kg_m3']
        physical_diff = ({f'presence ({parsed.object_id})':{'from':True,'to':False}}
                         if isinstance(parsed,dsl.DeleteEdit) else
                         {f'{parsed.property_name} ({parsed.object_id})':{
                             'from':dsl.baseline_value_for(parsed,vocab),'to':parsed.to_value}})
        plans.append({**edit, 'kind':'edit', 'source_case_id':SOURCE_CASE_ID, 'physics':physics,
            'physics_override':overrides, 'applies_from_frame':dsl.starts_at_frame(parsed),
            'prompts':dsl.make_prompts(parsed,vocab),
            'physics_diff':{**physical_diff,'timing':dsl.timing_diff(parsed,vocab)}})
    return profile,manifest,plans


def case_specification(profile, manifest, assets, plan):
    spec = copy.deepcopy(profile)
    before = copy.deepcopy(profile['physics'])
    if plan['case_id']=='edit_delete_duck':
        before['duck_presence'] = [1]
    if plan['case_id']==DELETE_WATER_CASE_ID:
        before['water_presence'] = [1]
    spec['physics'] = plan['physics']
    changes = {key:{'before':before[key],'after':value} for key,value in plan['physics'].items()
               if value != before[key]}
    expected = set() if plan['kind']=='source' else EDIT_PHYSICS_FIELDS[plan['case_id']]
    assert set(changes) == expected
    spec['runtime_assets'] = {'path':str(assets),'manifest_sha256':digest(assets/'asset_manifest.json')}
    spec['counterfactual'] = {'id':plan['case_id'],'edit_dsl':plan['edit_dsl'],
        'before':before,'after':plan['physics'],'changes':changes,
        'appearance_unchanged':True,'edit_time':'Before release, t=0',
        'source_video_sha256':manifest['selected_base_video_sha256']}
    if plan['case_id']=='edit_delete_duck':
        spec['counterfactual']['deleted_objects'] = ['duck']
    if plan['case_id']==DELETE_WATER_CASE_ID:
        spec['counterfactual']['deleted_objects'] = ['water']
        # Genesis shrinks its MPM contact box by three cells. The wet base
        # never contacts the floor; for an empty pool align that contact plane
        # with the frozen PoolFloor mesh, rather than translating render poses.
        q = spec['simulation_quality']
        original_quality = copy.deepcopy(q)
        old_lower = copy.deepcopy(q['mpm_lower_bound_m'])
        floor = q['sph_lower_bound_m'][2]
        q['mpm_particle_size_m'] = 1/q['mpm_grid_density_per_m']/3
        q['mpm_lower_bound_m'][2] = floor-7/q['mpm_grid_density_per_m']
        q['duck_quadrature_target_mass_kg'] = manifest['base_actual']['duck_discrete_mass_kg']
        spec['empty_pool_contact'] = {'kind':'rigid_plane','plane_z_m':floor,
            'friction':0.,'restitution':0.,'softness_m':.002,
            'friction_and_restitution_unchanged_from_genesis_boundary':True}
        spec['numerical_boundary_alignment'] = {
            'reason':'Move the numerical safety boundary below the actual floor and handle physical floor contact with a rigid plane. Refine particle quadrature to maintain material continuity; preserve total mass and reference volume exactly. Grid spacing and time step are unchanged.',
            'pool_floor_top_z_m':floor, 'genesis_padding_cells':3,
            'before':{'mpm_lower_bound_m':old_lower},
            'after':{'mpm_lower_bound_m':copy.deepcopy(q['mpm_lower_bound_m'])},
            'physical_contact_lower_z_m':floor,
            'safety_boundary_lower_z_m':floor-4/q['mpm_grid_density_per_m'],
            'only_this_deleted_water_case':True}
        spec['numerical_repair'] = {'before':original_quality,'after':copy.deepcopy(q),
            'method':'Mass-preserving regular MPM quadrature with nominal 27 particles per occupied grid cell and explicit nonpenetrating rigid-plane contact.',
            'unchanged_physical_parameters':['duck_density_kg_m3','duck_nominal_mass_kg',
                'young_modulus_pa','poisson_ratio','constitutive_model','gravity_mps2',
                'duck_initial_reference_m','duck_initial_velocity_mps'],
            'continuity_limits':{'maximum_rest_neighbor_ratio':4.,
                'maximum_F_consistency_error_grid_cells':1.,
                'maximum_p99_F_consistency_error_grid_cells':.2,
                'maximum_sampled_energy_over_initial':1.05},
            'not_a_calibrated_rubber_shell_model':True}
    if plan['case_id']=='edit_low_density_liquid_after_float_185_f73':
        schedule = copy.deepcopy(plan['physics_override']['timed_edits'])
        assert schedule == [{'frame':73,'params':{'water_density_kg_m3':185.}}]
        spec['counterfactual'].update(
            initial_physics=before, timed_edits=schedule,
            edit_time='At t=3.00 s (frame 73 at 24 fps), after reaching that live state and before advancing further.',
            derived_parameter_changes=['water_target_mass_kg'],
            trigger_time_seconds=3.00,
            trigger_state_checks={'window_seconds':.25,'maximum_center_z_range_m':.02,
                                  'maximum_absolute_vertical_velocity_mps':.08,'maximum_tilt_degrees':15.},
            post_edit_motion_target={'minimum_center_descent_m':.15,
                                     'no_pose_velocity_or_deformation_reset':True},
            density_intervention='Externally imposed uniform density change at fixed particle volumes; mass and kinematic viscosity are updated consistently. It is not a mass-conserving thermodynamic process.')
    if plan['case_id']=='edit_low_density_liquid_slow_sink_185':
        spec['counterfactual']['derived_parameter_changes'] = ['water_target_mass_kg']
        spec['counterfactual']['sinking_target'] = {
            'definition':'The unchanged duck sinks after entry and its entire actual deformed visual mesh remains below the local liquid-surface proxy in the last second.',
            'late_window_seconds':[3.,4.],'minimum_surface_clearance_m':.03,
            'comparison_case_id':'edit_low_density_liquid_sink',
            'comparison_goal':'Slower descent after entry and less splash than the 100 kg/m3 variant; requires actual motion and video review, not inferred acceptance.',
            'no_mass_pose_or_rotation_override':True,
            'ordinary_water_density_claim':False}
    return spec


def promote_source(case, rendered, manifest, assets):
    """Import the selected clip without requiring deliberately discarded caches."""
    frozen = assets/'selected_base_video.mp4'
    original = rendered/'video.mp4'
    source_video = frozen if frozen.is_file() else original
    if not source_video.is_file():
        raise FileNotFoundError('Missing selected base video input: '+str(frozen)+
                                '. Restore this asset or use --import-base-render-dir.')
    assert digest(source_video) == manifest['selected_base_video_sha256']
    if (case/'video.mp4').exists():
        assert digest(case/'video.mp4') == manifest['selected_base_video_sha256']
    else:
        assert source_video.resolve() != (case/'video.mp4').resolve()
        shutil.copy2(source_video,case/'video.mp4')
    write_json(case/'selected_base_provenance.json',{
        'video_sha256':manifest['selected_base_video_sha256'],
        'original_simulation_report_sha256':manifest['selected_base_simulation_sha256'],
        'copied_from':str(source_video),'base_video_recomputed':False,
        'raw_physics_reaudit_available':False})


def edit_prompt_document(plan):
    """Keep the same edit annotation beside both new and retained videos."""
    return {key:copy.deepcopy(plan[key]) for key in
            ('case_id','source_case_id','edit_dsl','edit_summary','applies_from_frame','physics_diff','prompts')}


def prepare(args, assets, profile, manifest, plans):
    cases = args.out_root/'cases'
    for plan in plans:
        case = cases/plan['case_id']
        if args.case_storage_root and not case.exists():
            assert not case.is_symlink(), 'Refuse to repoint a dangling case symlink.'
            storage = args.case_storage_root/plan['case_id']
            storage.mkdir(parents=True,exist_ok=True)
            assert not any(storage.iterdir()), 'New external case storage must be empty.'
            cases.mkdir(parents=True,exist_ok=True)
            case.symlink_to(storage,target_is_directory=True)
        case.mkdir(parents=True,exist_ok=True)
        spec = case_specification(profile,manifest,assets,plan)
        path = case/'mpm_sph_experiment.json'
        if path.exists():
            assert json.loads(path.read_text()) == spec, 'Existing case has different parameters: '+str(case)
        else:
            write_json(path,spec)
            write_json(case/'physics_edit.json',spec['counterfactual'])
            write_json(case/'scenario_overrides.json',{'physics':plan['physics_override']})
            for name in ('duck_solid.obj','render_geometry.npz'):
                shutil.copy2(assets/name,case/name)
        if plan['kind']=='edit':
            prompt_path = case/'prompts.json'
            expected = edit_prompt_document(plan)
            if prompt_path.exists():
                assert json.loads(prompt_path.read_text()) == expected, 'Existing edit prompt differs: '+str(case)
            else:
                write_json(prompt_path,expected)
        if plan['kind']=='source' and not args.resimulate_base:
            source = args.import_base_case or Path(manifest['baseline_case'])
            rendered = args.import_base_render_dir or source
            promote_source(case,rendered,manifest,assets)


def find_empty_gpu(reserved=()):
    rows = list(csv.reader(io.StringIO(subprocess.check_output([
        'nvidia-smi','--query-gpu=index,uuid,memory.used,memory.free,utilization.gpu',
        '--format=csv,noheader,nounits'],text=True))))
    processes = list(csv.reader(io.StringIO(subprocess.check_output([
        'nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader'],text=True))))
    occupied = {row[0].strip() for row in processes if row}
    # CUDA driver bookkeeping can remain above 100 MiB after all compute
    # processes exit. Require an empty process list and zero utilization;
    # prefer the least-used truly idle device rather than a fixed index.
    for row in sorted(rows,key=lambda row:int(row[2].strip())):
        index,uuid,used,free,utilization = [value.strip() for value in row]
        if int(index) not in reserved and uuid not in occupied and int(used)<256 and int(utilization)==0:
            return {'index':int(index),'uuid':uuid,'memory_free_mib':int(free)}
    return None


def affinity_for_gpu(index):
    try:
        topology = subprocess.check_output(['nvidia-smi','topo','-m'],text=True)
        line = next(line for line in topology.splitlines() if line.split() and line.split()[0]=='GPU'+str(index))
        value = next(value for value in line.split() if re.fullmatch(r'\d+-\d+(?:,\d+-\d+)*',value))
        return {cpu for interval in value.split(',')
                for cpu in range(int(interval.split('-')[0]),int(interval.split('-')[1])+1)}
    except (subprocess.SubprocessError,StopIteration,ValueError):
        return None


def outputs(case):
    return {name.rsplit('.',1)[0]:str(case/name) for name in
            ('video.mp4','ground_truth_transforms.json','scenario_metadata.json','benchmark_validation.json',
             'prompts.json','video_verification.json','visual_review.json')
            if (case/name).exists()}


def finalize_manifest(out_root, suite):
    """Attach completed outputs; reuse visual reviews only for the exact video."""
    plans = [suite['source'], *suite['edits']]
    completed = []
    for plan in plans:
        state = suite['case_status'].get(plan['case_id'], {'status':'not_run'})
        case = out_root/'cases'/plan['case_id']
        plan['status'] = state['status']
        plan['outputs'] = outputs(case)
        if state['status'] != 'complete':
            continue
        state['outputs'] = plan['outputs']
        retained = suite.get('retained_case_evidence',{}).get(plan['case_id'],{})
        verification_path = case/'video_verification.json'
        verification = (json.loads(verification_path.read_text()) if verification_path.exists()
                        else retained['technical_verification'])
        assert verification['video_sha256'] == digest(case/'video.mp4')
        plan['video_sha256'] = verification['video_sha256']
        review_path = case/'visual_review.json'
        reviewed = False
        if review_path.exists():
            review = json.loads(review_path.read_text())
            reviewed = (review.get('video_sha256') == verification['video_sha256'] and
                        review.get('all_96_decoded_video_frames_inspected') is True)
        elif retained.get('visual_review'):
            review = retained['visual_review']
            reviewed = (review.get('video_sha256') == verification['video_sha256'] and
                        review.get('all_96_decoded_video_frames_inspected') is True)
        plan['visual_review_status'] = 'reviewed' if reviewed else 'pending'
        completed.append(reviewed)
    suite['all_planned_cases_complete'] = all(plan['status']=='complete' for plan in plans)
    suite['completed_case_ids'] = [plan['case_id'] for plan in plans if plan['status']=='complete']
    if suite.get('status') != 'failed_case_preserved' and completed and suite['all_planned_cases_complete']:
        suite['status'] = ('complete_qualitatively_reviewed' if all(completed)
                           else 'videos_complete_awaiting_visual_review')
    elif suite.get('status') != 'failed_case_preserved' and completed and all(completed):
        suite['status'] = 'requested_cases_complete_qualitatively_reviewed'
    write_json(out_root/'suite_manifest.json',suite)


def retain_videos_only(args, suite):
    """Keep videos and edit prompts; retain other checked evidence centrally."""
    if args.keep_intermediates:
        return
    allowed = {'runs','frames','duck_solid.obj','render_geometry.npz','mpm_sph_experiment.json',
        'physics_edit.json','scenario_overrides.json','prompts.json','ground_truth_transforms.json',
        'scenario_metadata.json','benchmark_validation.json','immersion_diagnostic.json',
        'render_report.json','video_verification.json','visual_review.json','selected_base_provenance.json',
        'simulate.log','surface.log','render.log','audit.log','verify.log',
        *(phase+'.log' for phase in LOOK_PHASES)}
    retained = suite.setdefault('retained_case_evidence',{})
    removals = []
    for plan in (suite['source'],*suite['edits']):
        state = suite['case_status'].get(plan['case_id'],{})
        if state.get('status') != 'complete':
            continue
        case = args.out_root/'cases'/plan['case_id']
        assert case.resolve() != args.out_root.resolve()
        verification_path = case/'video_verification.json'
        verification = (json.loads(verification_path.read_text()) if verification_path.exists()
                        else retained[plan['case_id']]['technical_verification'])
        assert verification['all_96_frames_decoded'] and verification['video_sha256']==digest(case/'video.mp4')
        evidence = copy.deepcopy(retained.get(plan['case_id'],{}))
        evidence.update(technical_verification=verification, raw_physics_reaudit_available=False)
        records = {'mpm_sph_experiment.json':'configuration','benchmark_validation.json':'numerical_validation',
            'scenario_metadata.json':'scenario_metadata','visual_review.json':'visual_review',
            'selected_base_provenance.json':'selected_base_provenance','render_report.json':'render_report',
            'immersion_diagnostic.json':'immersion_diagnostic'}
        for name,key in records.items():
            path = case/name
            if path.exists():
                value = json.loads(path.read_text())
                if 'frames' in value:
                    value['stored_frame_count_before_cleanup'] = len(value.pop('frames'))
                evidence[key] = value
        simulation_path = case/'runs/source/simulation_report.json'
        if simulation_path.exists():
            value = json.loads(simulation_path.read_text())
            value['stored_frame_count_before_cleanup'] = len(value.pop('frames'))
            evidence['simulation_report'] = value
        kept_outputs = {'video':str(case/'video.mp4')}
        kept_names = {'video.mp4'}
        if plan['kind']=='edit':
            prompt_path = case/'prompts.json'
            expected = edit_prompt_document(plan)
            if 'prompts' in evidence:
                assert evidence['prompts'] == expected, 'Retained edit prompt differs: '+str(case)
            if prompt_path.exists():
                assert json.loads(prompt_path.read_text()) == expected, 'Existing edit prompt differs: '+str(case)
            else:
                write_json(prompt_path,expected)
            evidence['prompts'] = expected
            kept_outputs['prompts'] = str(prompt_path)
            kept_names.add('prompts.json')
        retained[plan['case_id']] = evidence
        for child in case.iterdir():
            if child.name in kept_names:
                continue
            assert child.name in allowed and not child.is_symlink(), 'Unexpected cleanup target: '+str(child)
            removals.append(child)
        plan['outputs'] = state['outputs'] = kept_outputs
        state['retention'] = 'video_and_edit_prompts' if plan['kind']=='edit' else 'video_only'
        state['raw_physics_reaudit_available'] = False
    # Commit the evidence before removing any cache, log, configuration or PNG.
    suite['retention'] = 'videos_and_edit_prompts_with_configuration_and_validation_in_suite_manifest'
    write_json(args.out_root/'suite_manifest.json',suite)
    removed_bytes = 0
    for child in removals:
        removed_bytes += (sum(p.stat().st_size for p in child.rglob('*') if p.is_file())
                          if child.is_dir() else child.stat().st_size)
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    suite['removed_intermediate_bytes'] = suite.get('removed_intermediate_bytes',0)+removed_bytes
    write_json(args.out_root/'suite_manifest.json',suite)
    print('VIDEO_AND_PROMPT_RETENTION',removed_bytes,flush=True)


def stages_after_simulation(plan):
    """Surface meshes, the look's inputs when the case has water, then the render."""
    water = plan['physics'].get('water_presence',[1]) == [1]
    return ['surface',*(LOOK_PHASES if water else ()),'render']


def run_pipeline(args, plans, suite):
    selected = set(args.cases if args.cases is not None else [edit['case_id'] for edit in EDIT_CASES])
    tasks = []
    for plan in plans:
        if plan['kind']=='edit' and plan['case_id'] not in selected:
            continue
        case = args.out_root/'cases'/plan['case_id']
        # Retained clips are decoded and identity-checked, never relabelled as
        # newly simulated or as having their discarded raw physics re-audited.
        if args.skip_existing and (case/'video.mp4').exists() and not (case/'runs/source/simulation_report.json').exists():
            if plan['kind']=='source':
                assert digest(case/'video.mp4') == suite['selected_base_video_sha256']
            phases = ['verify']
        elif plan['kind']=='source' and not args.resimulate_base:
            phases = ['verify']
        elif args.skip_existing and (case/'video.mp4').exists():
            phases = ['audit','verify']
        else:
            path = case/'runs/source/simulation_report.json'
            if path.exists():
                assert json.loads(path.read_text())['status']=='simulated_awaiting_coupling_and_visual_review', 'Partial simulation cannot be resumed.'
                phases = stages_after_simulation(plan)
            else:
                phases = ['simulate',*stages_after_simulation(plan)]
        tasks.append({'case_id':plan['case_id'],'case':case,'phases':phases,'index':0,'process':None})
    reserved = set()
    start = time.monotonic()
    suite['status'] = 'running_requested_cases'
    while any(task['index']<len(task['phases']) for task in tasks):
        for task in tasks:
            process = task.get('process')
            if process is None or process.poll() is None:
                continue
            task['log'].close()
            if task.get('gpu'):
                reserved.discard(task['gpu']['index'])
            code = process.returncode
            suite.setdefault('case_phase_seconds',{}).setdefault(task['case_id'],{})[
                task['phases'][task['index']]] = time.monotonic()-task['stage_started']
            if code:
                suite['case_status'][task['case_id']] = {'status':'failed','stage':task['phases'][task['index']],
                    'exit_code':code,'log':str(task['log_path'])}
                task['index'] = len(task['phases'])
                task['failed'] = True
            else:
                task['index'] += 1
                suite['case_status'][task['case_id']] = {'status':'complete' if task['index']==len(task['phases']) else 'running',
                    'completed_stage':task['phases'][task['index']-1], 'outputs':outputs(task['case'])}
            task['process'] = None
            write_json(args.out_root/'suite_manifest.json',suite)
        active = sum(task.get('process') is not None for task in tasks)
        for task in tasks:
            if active >= args.jobs or task.get('process') is not None or task['index']==len(task['phases']):
                continue
            phase = task['phases'][task['index']]
            gpu = find_empty_gpu(reserved) if phase in ('simulate','render') else None
            if phase in ('simulate','render') and gpu is None:
                suite['case_status'][task['case_id']] = {'status':'waiting_for_empty_gpu','stage':phase}
                continue
            env = dict(os.environ,OMP_NUM_THREADS='8',RAYON_NUM_THREADS='8',PYOPENGL_PLATFORM='egl')
            if phase in ('simulate','surface','audit'):
                command = [str(args.python),'-u',str(HERE/'simulate_elastic_fluid_duck.py'),
                    '--case-dir',str(task['case']),'--stage',phase]
                if phase=='simulate':
                    command += ['--max-wall-seconds',str(args.max_wall_seconds)]
            elif phase=='render':
                command = [str(args.blender),'-b','-t','8','--python-exit-code','1',
                    '--python',str(HERE/'render_elastic_fluid_duck.py'),'--','--case-dir',str(task['case'])]
            elif phase=='occluders':
                command = [str(args.blender),'-b','--python-exit-code','1',
                    '--python',str(HERE/'render_elastic_fluid_duck.py'),'--','--case-dir',str(task['case']),'--occluders']
            elif phase in LOOK_PHASES:
                command = [str(args.python),'-u',str(HERE/'physics'/f'{phase}_elastic_fluid_duck.py'),'--case-dir',str(task['case'])]
            else:
                command = [str(args.python),str(HERE/'render_elastic_fluid_duck.py'),
                    '--case-dir',str(task['case']),'--verify-only',
                    '--evidence-manifest',str(args.out_root/'suite_manifest.json')]
            affinity = None
            if gpu:
                env['CUDA_VISIBLE_DEVICES'] = str(gpu['index'])
                reserved.add(gpu['index'])
                affinity = affinity_for_gpu(gpu['index'])
            log_path = task['case']/(phase+'.log')
            stream = log_path.open('a',encoding='utf8')
            preexec = (lambda cpus=affinity:os.sched_setaffinity(0,cpus)) if affinity and hasattr(os,'sched_setaffinity') else None
            task.update(process=subprocess.Popen(command,env=env,stdout=stream,stderr=subprocess.STDOUT,preexec_fn=preexec),
                        gpu=gpu,log=stream,log_path=log_path,stage_started=time.monotonic())
            suite['case_status'][task['case_id']] = {'status':'running','stage':phase,'command':command,
                'gpu':gpu,'cpu_affinity':sorted(affinity) if affinity else None,'log':str(log_path)}
            print('CASE_STAGE_STARTED',task['case_id'],phase,json.dumps(gpu),flush=True)
            write_json(args.out_root/'suite_manifest.json',suite)
            active += 1
        if time.monotonic()-start > args.max_wall_seconds+3600:
            raise TimeoutError('Suite scheduling safety time limit reached; outputs remain available.')
        time.sleep(3)
    suite['status'] = ('failed_case_preserved' if any(task.get('failed') for task in tasks)
                       else 'videos_complete_awaiting_visual_review')
    suite['pipeline_wall_seconds'] = time.monotonic()-start
    finalize_manifest(args.out_root,suite)
    if any(task.get('failed') for task in tasks):
        raise RuntimeError('One or more cases failed; inspect the recorded per-case logs.')
    retain_videos_only(args,suite)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',type=Path,default=ROOT)
    parser.add_argument('--asset-dir',type=Path)
    parser.add_argument('--out-root',type=Path)
    parser.add_argument('--case-storage-root',type=Path,
                        help='Store newly created cases on this volume and link them from the suite; existing cases are never moved.')
    parser.add_argument('--python',type=Path)
    parser.add_argument('--blender',type=Path,default=blender())
    parser.add_argument('--stage',choices=('prepare','all','finish'),default='all',
                        help='finish processes only explicit --cases with a complete simulation, without touching video-only retained cases.')
    parser.add_argument('--cases',nargs='*',choices=[edit['case_id'] for edit in EDIT_CASES])
    parser.add_argument('--edits-only',action='store_true',
                        help='Prepare and run only explicit --cases; do not copy, restore or process the retained base or other edits.')
    parser.add_argument('--jobs',type=int,default=6,
                        help='Maximum concurrently running case stages; one GPU is reserved per simulate/render stage.')
    parser.add_argument('--max-wall-seconds',type=float,default=7200)
    parser.add_argument('--skip-existing',action='store_true')
    parser.add_argument('--keep-intermediates',action='store_true',
                        help='Keep raw simulation/cache/PNG/log outputs for diagnostics; the default retains videos, per-edit prompts and central metadata.')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--resimulate-base',action='store_true')
    parser.add_argument('--import-base-case',type=Path)
    parser.add_argument('--import-base-render-dir',type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    args.out_root = (args.out_root or suite_output_root('elastic_fluid_duck', (root/'renders/pcve_suites').resolve().parent/'elastic_fluid_duck'/'suite_build')).resolve()
    assets = (args.asset_dir or root/'assets/elastic_fluid/elastic_fluid_duck').resolve()
    args.case_storage_root = args.case_storage_root.resolve() if args.case_storage_root else None
    # Keep the virtualenv entry point: resolving its symlink would launch the
    # system interpreter with a different sys.prefix and missing dependencies.
    args.python = (args.python or root/'.venv-genesis-mpm-sph/bin/python').expanduser().absolute()
    assert 1 <= args.jobs <= 8 and args.max_wall_seconds > 0
    if args.edits_only:
        assert args.cases and not args.resimulate_base, '--edits-only requires explicit edits and cannot resimulate the base.'
    profile,manifest,plans = make_plans(root,assets)
    suite = {'schema_version':3,'suite_name':'pcve_elastic_fluid_duck_suite','interaction_category':'elastic_fluid',
        'description':'An elastic duck enters the pool and returns upright; edits change duck mass, liquid viscosity, liquid density, remove the duck or remove all water before release.',
        'resolution':[1280,720],'fps':24,'duration_sec':4,'samples':REAL_SAMPLES,'total_frames':96,
        'look':LOOK,
        'source_case_id':SOURCE_CASE_ID,'selected_base_video_sha256':manifest['selected_base_video_sha256'],
        'baseline_physics':profile['physics'],
        'source':plans[0],'edits':plans[1:],'case_status':{},'status':'prepared',
        'asset_dir':str(assets),'code_files':[str(HERE/name) for name in CODE_FILES],
        'case_storage_root':str(args.case_storage_root) if args.case_storage_root else None,
        'accepted_as_calibrated_ground_truth':False}
    if args.dry_run:
        print(json.dumps(suite,indent=2,ensure_ascii=False))
        return
    if args.stage=='all' and not args.skip_existing:
        selected = set(args.cases if args.cases is not None else [e['case_id'] for e in EDIT_CASES])
        existing = [p['case_id'] for p in plans if p['case_id'] in selected and
                    (args.out_root/'cases'/p['case_id']/'video.mp4').exists()]
        if existing:
            raise FileExistsError('Completed edit videos already exist. Use a new --out-root or --skip-existing: '+', '.join(existing))
    previous_path = args.out_root/'suite_manifest.json'
    if previous_path.exists():
        previous = json.loads(previous_path.read_text())
        prior_plans = {p['case_id']:p for p in [previous['source'],*previous['edits']]}
        for plan in plans:
            old = prior_plans.get(plan['case_id'])
            if old and old['physics']==plan['physics'] and old['edit_dsl']==plan['edit_dsl']:
                if plan['case_id'] in previous.get('case_status',{}):
                    suite['case_status'][plan['case_id']] = copy.deepcopy(previous['case_status'][plan['case_id']])
                if plan['case_id'] in previous.get('retained_case_evidence',{}):
                    suite.setdefault('retained_case_evidence',{})[plan['case_id']] = copy.deepcopy(
                        previous['retained_case_evidence'][plan['case_id']])
    if args.stage == 'finish':
        assert args.cases, 'finish requires explicit --cases.'
        selected_plans = [p for p in plans if p['case_id'] in args.cases]
        for plan in selected_plans:
            case = args.out_root/'cases'/plan['case_id']
            assert json.loads((case/'mpm_sph_experiment.json').read_text()) == case_specification(profile,manifest,assets,plan)
            cached = json.loads((case/'runs/source/simulation_report.json').read_text())
            assert cached['status']=='simulated_awaiting_coupling_and_visual_review' and len(cached['frames'])==96
    else:
        prepare_plans = [p for p in plans if p['case_id'] in args.cases] if args.edits_only else plans
        prepare(args,assets,profile,manifest,prepare_plans)
    write_json(args.out_root/'suite_manifest.json',suite)
    if args.stage == 'all':
        run_pipeline(args,prepare_plans,suite)
    elif args.stage == 'finish':
        run_pipeline(args,selected_plans,suite)
    print(args.out_root/'suite_manifest.json',flush=True)


if __name__ == '__main__':
    main()
