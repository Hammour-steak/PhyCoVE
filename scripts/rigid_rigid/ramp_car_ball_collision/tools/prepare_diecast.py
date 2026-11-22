"""Prepare packed diecast-look case scenes from accepted native poses; do not run a solver.

prepare_template_suite.py and render_diecast.py use its pose and scene-audit functions."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

HERE = Path(__file__).resolve().parents[1]
for parent in HERE.parents:
    if (parent/'scripts/pcve_assets.py').is_file():
        sys.path.insert(0,str(parent/'scripts'))
        break
for directory in [HERE, HERE/'appearance']:
    sys.path.insert(0,str(directory))
from scene_config import differences, save_json, signature
from look_ramp_car_ball_collision import refine_existing, look_at

CASES = ['source','edit_heavy_ball','edit_low_restitution','edit_remove_ball']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def set_poses(roots, result):
    for root in roots.values():
        root.animation_data_clear()
        root.rotation_mode = 'QUATERNION'
    previous = {}
    for sample in result['trajectory_samples']:
        frame = 1 + sample['time_sec'] * 24
        for name, pose in sample['objects'].items():
            root = roots[name]
            root.location = pose['location']
            x,y,z,w = pose['quaternion_xyzw']
            quaternion = (w,x,y,z)
            if name in previous and sum(a*b for a,b in zip(previous[name],quaternion)) < 0:
                quaternion = tuple(-v for v in quaternion)
            root.rotation_quaternion = quaternion
            previous[name] = quaternion
            root.keyframe_insert(data_path='location',frame=frame)
            root.keyframe_insert(data_path='rotation_quaternion',frame=frame)
    for root in roots.values():
        for curve in root.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = 'LINEAR'


def playback(native, appearance):
    result = copy.deepcopy(native)
    result['configuration']['appearance'] = copy.deepcopy(appearance)
    result['configuration']['render'].update(fps=24,samples=128,persistent_data=False)
    # 60*256 == 24*640; the actual solver time step and all native solved states stay identical.
    result['configuration']['simulation_quality']['substeps_per_frame'] = 640
    assert 1/(24*640) == native['dt_sec']
    result['configuration_sha256'] = signature(result['configuration'])
    result['frames'] = []
    for i in range(96):
        sample = copy.deepcopy(native['trajectory_samples'][i*10])
        assert abs(sample['time_sec'] - i/24) < 1e-12
        sample['frame_index'] = i+1
        result['frames'].append(sample)
    result['frame_end'] = 96
    result['native_pose_replay'] = {'no_solver_rerun': True,'native_fps':60,'video_fps':24,'trajectory_hz':240,
        'resampling':'Every tenth exact native 240 Hz sample; all original samples retained for shutter interpolation',
        'actual_solver_dt_sec':native['dt_sec'],'substeps_metadata':'256 at 60 fps becomes 640 at 24 fps, preserving the same 1/15360 s solver step'}
    assert result['configuration']['physics'] == native['configuration']['physics']
    assert result['trajectory_samples'] == native['trajectory_samples']
    assert result['contact_events'] == native['contact_events']
    return result


def audit_scene(scene, roots, result, native_hash, ledger):
    maximum_position_error = 0.
    maximum_quaternion_error = 0.
    projections = []
    minimum_pixel_diameter = {'car_body':float('inf'),'ball':float('inf')}
    for frame in result['frames']:
        scene.frame_set(frame['frame_index'])
        bpy.context.view_layer.update()
        projected = {}
        for name, pose in frame['objects'].items():
            root = roots[name]
            maximum_position_error=max(maximum_position_error,(root.location-Vector(pose['location'])).length)
            x,y,z,w=pose['quaternion_xyzw'];expected=(w,x,y,z);actual=tuple(root.rotation_quaternion)
            maximum_quaternion_error=max(maximum_quaternion_error,min(max(abs(a-b) for a,b in zip(actual,expected)),max(abs(a+b) for a,b in zip(actual,expected))))
            if name.startswith('wheel'):continue
            points=[o.matrix_world @ Vector(c) for o in root.children_recursive if o.type=='MESH' for c in o.bound_box]
            uv=[world_to_camera_view(scene,scene.camera,p) for p in points]
            bounds=[min(v.x for v in uv),min(v.y for v in uv),max(v.x for v in uv),max(v.y for v in uv)]
            visible=all(v.z>0 for v in uv) and bounds[0]>.01 and bounds[1]>.01 and bounds[2]<.99 and bounds[3]<.99
            projected[name]={'uv_bounds':bounds,'fully_in_frame':visible}
            minimum_pixel_diameter[name]=min(minimum_pixel_diameter[name],(bounds[2]-bounds[0])*1280)
        projections.append({'frame_index':frame['frame_index'],'objects':projected})
    assert maximum_position_error < 1e-6 and maximum_quaternion_error < 1e-6
    assert all(o['fully_in_frame'] for p in projections for o in p['objects'].values()), 'An edited body leaves the new framing'
    assert scene.render.fps==24 and scene.frame_end==96
    assert not scene.render.use_persistent_data
    report={'accepted':True,'native_physics_sha256':native_hash,'pose_samples_checked':96*len(roots),
        'maximum_position_error_m':maximum_position_error,'maximum_quaternion_component_error':maximum_quaternion_error,
        'all_96_frames_fully_in_view':True,'minimum_object_width_px':{k:v for k,v in minimum_pixel_diameter.items() if v<float('inf')},
        'projected_bounds':projections,'dimension_and_appearance_ledger':ledger,'persistent_data':False,'fps':24,'frames':96,'samples':128}
    scene.frame_set(1)
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-blend',type=Path,required=True)
    parser.add_argument('--native-suite',type=Path,required=True,help='Suite whose cases contain original_case/native pose files')
    parser.add_argument('--appearance-json',type=Path,required=True)
    parser.add_argument('--car-asset',type=Path,required=True)
    parser.add_argument('--out-root',type=Path,required=True)
    parser.add_argument('--preview-frames',nargs='*',type=int)
    parser.add_argument('--threads',type=int,default=32)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    out=args.out_root.resolve();out.mkdir(parents=True,exist_ok=True)
    assert not (out/'suite_manifest.json').exists(),'Choose a fresh versioned output root'
    appearance=json.loads(args.appearance_json.read_text())
    source_folder=args.native_suite/'cases/source/original_case'
    source_native=json.loads((source_folder/'physics_transforms.json').read_text())
    source_result=playback(source_native,appearance)
    bpy.ops.wm.open_mainfile(filepath=str(args.base_blend))
    scene=bpy.context.scene
    scene.frame_set(1)
    roots,ledger=refine_existing(source_result['configuration'],args.car_asset)
    roots['ball']=bpy.data.objects['ball']
    scene.render.fps=24;scene.frame_start=1;scene.frame_end=96
    scene.render.resolution_x=1280;scene.render.resolution_y=720;scene.render.resolution_percentage=100
    scene.cycles.samples=128;scene.cycles.use_denoising=True;scene.cycles.denoising_use_gpu=False
    scene.render.use_persistent_data=False
    scene.render.threads_mode='FIXED';scene.render.threads=args.threads;scene.cycles.device='CPU'
    camera=scene.camera;spec=appearance['camera'];camera.animation_data_clear();camera.location=spec['location'];look_at(camera,spec['target'])
    camera.data.lens=spec['lens_mm'];camera.data.dof.use_dof=True;camera.data.dof.focus_distance=spec['focus_distance_m'];camera.data.dof.aperture_fstop=spec['f_stop']
    set_poses(roots,source_result)
    bpy.ops.outliner.orphans_purge(do_recursive=True)
    bpy.ops.file.pack_all()
    template=out/'source_template.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(template))
    records=[];freeze={}
    for case_id in CASES:
        if case_id!='source':
            bpy.ops.wm.open_mainfile(filepath=str(template));scene=bpy.context.scene
        folder=out/'cases'/case_id;folder.mkdir(parents=True)
        native_folder=args.native_suite/'cases'/case_id/'original_case'
        native_path=native_folder/'physics_transforms.json'
        native=json.loads(native_path.read_text());result=playback(native,appearance)
        roots={name:bpy.data.objects[name] for name in ['car_body','wheel_0','wheel_1','wheel_2','wheel_3']}
        if result['configuration']['physics']['ball']['present']:
            roots['ball']=bpy.data.objects['ball']
        else:
            root=bpy.data.objects['ball']
            for child in list(root.children_recursive):bpy.data.objects.remove(child,do_unlink=True)
            bpy.data.objects.remove(root,do_unlink=True)
        set_poses(roots,result)
        for name in ['physics_transforms.json','trajectory.csv','physics_validation.json','contacts.json','prompts.json']:
            if (native_folder/name).exists():shutil.copy2(native_folder/name,folder/('native_'+name))
        save_json(folder/'physics_transforms.json',result)
        save_json(folder/'settings.json',result['configuration'])
        save_json(folder/'prompts.json',json.loads((native_folder/'prompts.json').read_text()))
        save_json(folder/'ground_truth_transforms.json',{'scene':'ramp_car_ball_collision','case_id':case_id,'fps':24,'units':result['configuration']['physics']['units'],'frames':result['frames'],'contact_events':result['contact_events'],'camera':appearance['camera']})
        save_json(folder/'configuration_diff.json',{'before':native['configuration'],'after':result['configuration'],'differences':differences(native['configuration'],result['configuration']),
            'actual_physics_unchanged':True,'actual_dt_unchanged':True,'dense_trajectory_unchanged':True})
        report=audit_scene(scene,roots,result,sha(native_path),ledger)
        save_json(folder/'appearance_pose_validation.json',report)
        bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(folder/'ramp_car_ball_collision.blend'))
        freeze[case_id]={'before_sha256':sha(native_path),'preserved_native_file_sha256':sha(folder/'native_physics_transforms.json'),
            'physics_equal':result['configuration']['physics']==native['configuration']['physics'],
            'trajectory_equal':result['trajectory_samples']==native['trajectory_samples'],'actual_solver_dt_equal':result['dt_sec']==native['dt_sec'],
            'contacts_equal':result['contact_events']==native['contact_events']}
        records.append({'case_id':case_id,'kind':'source' if case_id=='source' else 'edit','source_case_id':'source','status':'prepared_pending_render',
            'case_dir':str(folder),'native_case_dir':str(native_folder),'outcome':result['outcome'],
            'outputs':{k:str(folder/n) for k,n in [('video','video.mp4'),('scene','ramp_car_ball_collision.blend'),('physics','physics_transforms.json'),('settings','settings.json'),('ground_truth','ground_truth_transforms.json'),('prompts','prompts.json')]}})
    assert all(v['before_sha256']==v['preserved_native_file_sha256'] and all(v[k] for k in ['physics_equal','trajectory_equal','actual_solver_dt_equal','contacts_equal']) for v in freeze.values())
    save_json(out/'physics_freeze_validation.json',{'accepted':True,'no_solver_rerun':True,'cases':freeze})
    save_json(out/'appearance_ledger.json',ledger)
    save_json(out/'suite_manifest.json',{'schema_version':4,'scene':'ramp_car_ball_collision','suite_name':'pcve_ramp_car_ball_collision_suite','interaction_category':'rigid_rigid',
        'configuration':source_result['configuration'],'source':records[0],'edits':records[1:],'fps':24,'resolution':[1280,720],'total_frames':96,'duration_sec':4.,'samples':128,
        'status':'prepared_pending_render','native_suite':str(args.native_suite),'source_template':str(template),'appearance_revision':'diecast_living_room_garden',
        'asset_credit':'Car Concept, Eric Chadwick / Darmstadt Graphics Group, CC BY 4.0; source Unity Fan CC0. Poly Haven courtyard plants CC0.'})
    if args.preview_frames:
        folder=out/'cases/source'
        bpy.ops.wm.open_mainfile(filepath=str(folder/'ramp_car_ball_collision.blend'));scene=bpy.context.scene
        (out/'preview').mkdir()
        for frame in args.preview_frames:
            scene.frame_set(frame);bpy.context.view_layer.update()
            scene.render.filepath=str(out/'preview'/('frame_%04d.png'%frame))
            start=time.monotonic();bpy.ops.render.render(write_still=True)
            print('PREVIEW_RENDERED',frame,time.monotonic()-start,flush=True)
    print('PREPARED',str(out),flush=True)


if __name__=='__main__':main()
