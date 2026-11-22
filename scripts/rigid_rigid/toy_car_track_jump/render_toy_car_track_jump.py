"""Fixed-camera Cycles renderer of unmodified high-rate solver pose samples."""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == '__main__':
    import sys as _sys
    from pathlib import Path as _Path
    if (_Path(__file__).resolve().parents[2]/'pcve_scene_entry.py').is_file():
        _sys.path.insert(0,str(_Path(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__,'render')
# PCVE_UNIFIED_ENTRY_END
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import bpy
from mathutils import Quaternion, Vector
from bpy_extras.object_utils import world_to_camera_view
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE/'appearance'))
from scene_config import save_json, signature, merge, track_profile,launcher_colliders

def set_device(choice):
    if choice=='cpu':
        bpy.context.scene.cycles.device='CPU'
        return 'CPU'
    prefs=bpy.context.preferences.addons['cycles'].preferences
    for backend in ['OPTIX','CUDA','METAL']:
        try:
            prefs.compute_device_type=backend;prefs.get_devices()
            found=[d for d in prefs.devices if d.type==backend]
            if found:
                for d in prefs.devices:d.use=d in found
                bpy.context.scene.cycles.device='GPU'
                return backend
        except Exception:
            continue
    bpy.context.scene.cycles.device='CPU'
    return 'CPU'

def animate(roots,physics):
    times=[1+s['time_sec']*physics['fps'] for s in physics['trajectory_samples']]
    for name,obj in roots.items():
        obj.rotation_mode='QUATERNION'
        action=bpy.data.actions.new(name+' solved rigid pose cache')
        obj.animation_data_create();obj.animation_data.action=action
        positions=[];quats=[];previous=None
        for sample in physics['trajectory_samples']:
            b=sample['objects'][name];positions.append(b['location'])
            x,y,z,w=b['quaternion_xyzw'];q=[w,x,y,z]
            if previous is not None and sum(a*b for a,b in zip(q,previous))<0:q=[-v for v in q]
            quats.append(q);previous=q
        for path,values,n in [('location',positions,3),('rotation_quaternion',quats,4)]:
            for axis in range(n):
                fc=action.fcurves.new(data_path=path,index=axis)
                fc.keyframe_points.add(len(times))
                fc.keyframe_points.foreach_set('co',[value for t,xyz in zip(times,values) for value in [t,xyz[axis]]])
                for key in fc.keyframe_points:key.interpolation='LINEAR'
                fc.update()

def camera_audit(scene,camera,physics,cfg,assembly):
    bb=cfg['appearance']['car_local_bounds_m']
    local=[Vector((x,y,z)) for x in [bb[0][0],bb[1][0]] for y in [bb[0][1],bb[1][1]] for z in [bb[0][2],bb[1][2]]]
    projected=[]
    for s in physics['frames']:
        if 'car_body' not in s['objects']:continue
        b=s['objects']['car_body'];x,y,z,qw=b['quaternion_xyzw'];rot=Quaternion((qw,x,y,z));pos=Vector(b['location'])
        uv=[world_to_camera_view(scene,camera,pos+rot@v) for v in local]
        projected.append({'frame_index':s['frame_index'],'uv_min':[min(q.x for q in uv),min(q.y for q in uv)],
                          'uv_max':[max(q.x for q in uv),max(q.y for q in uv)],
                          'car_width_px':(max(q.x for q in uv)-min(q.x for q in uv))*cfg['render']['resolution'][0],
                          'intersects_frame':max(q.x for q in uv)>0 and min(q.x for q in uv)<1 and max(q.y for q in uv)>0 and min(q.y for q in uv)<1})
    pts=track_profile(cfg);width=cfg['physics']['track']['width_m']/2+.006
    track_uv=[world_to_camera_view(scene,camera,Vector((x,y,z))) for x,z in pts for y in [-width,width]]
    assembly_uv=[world_to_camera_view(scene,camera,obj.matrix_world@Vector(v)) for obj in assembly for v in obj.bound_box]
    margin=.018
    return {'all_track_assembly_in_frame':all(margin<q.x<1-margin and margin<q.y<1-margin for q in assembly_uv),
            'assembly_uv_bounds':[[min(q.x for q in assembly_uv),min(q.y for q in assembly_uv)],[max(q.x for q in assembly_uv),max(q.y for q in assembly_uv)]],
            'frames':projected,'all_car_silhouettes_in_frame':all(
                all(margin<v<1-margin for v in row['uv_min']+row['uv_max']) for row in projected),
            'all_track_in_frame':all(margin<q.x<1-margin and margin<q.y<1-margin for q in track_uv),
            'minimum_car_width_px':min((q['car_width_px'] for q in projected),default=None),'margin_fraction':margin,
            'first_fully_outside_frame':next((q['frame_index'] for q in projected if not q['intersects_frame']),None),
            'visibility_policy':'One shared fixed camera. Counterfactual motion may naturally leave its field of view; no trajectory is cropped or retimed.',
            'scope':'conservative 3D car bounding box including all wheels, mirrors and spoiler; static full-track envelope'}

def setup(cfg,physics):
    from look_toy_car_track_jump import car, track, room, lighting, look_at
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s=bpy.context.scene;s.unit_settings.system='METRIC';s.unit_settings.scale_length=1.
    r=cfg['render'];s.render.engine=r['engine'];s.cycles.samples=r['samples']
    s.cycles.use_denoising=r['denoising'];s.cycles.denoising_use_gpu=False
    s.cycles.max_bounces=8;s.cycles.diffuse_bounces=4;s.cycles.glossy_bounces=4
    s.cycles.transparent_max_bounces=6;s.cycles.transmission_bounces=6;s.cycles.adaptive_threshold=.012
    s.render.use_persistent_data=False
    s.render.resolution_x,s.render.resolution_y=r['resolution'];s.render.resolution_percentage=r['supersample_percent']
    s.render.fps=r['fps'];s.render.fps_base=1.;s.frame_start=1;s.frame_end=round(r['fps']*r['duration_sec'])
    s.view_settings.view_transform=r['color_management'];s.view_settings.look=r['view_look']
    s.view_settings.exposure=cfg['appearance']['exposure_ev']
    s.render.use_motion_blur=r['motion_blur_shutter_frames']>0
    s.render.motion_blur_shutter=r['motion_blur_shutter_frames']
    s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB';s.render.image_settings.compression=20
    ledger={'room':room(cfg)};before=set(bpy.context.scene.objects)
    ledger['track']=track(cfg);assembly=[o for o in set(bpy.context.scene.objects)-before if o.type in ['MESH','CURVE'] and not o.name.startswith(('Launcher','Button'))]
    roots=car(cfg) if cfg['physics']['car'].get('present',True) else {};lighting(cfg)
    from refine_toy_car_track_jump import refine_scene
    ledger['refinement']=refine_scene(s)
    # Finishing layer: daylight without hidden fill, molded plastic finish, rug pile.
    from finish_toy_car_track_jump import finish_scene
    ledger['daylight_finish']=finish_scene(s,cfg,roots)
    animate(roots,physics)
    cc=cfg['appearance']['camera'];bpy.ops.object.camera_add(location=cc['location'])
    camera=bpy.context.object;camera.name='Fixed side camera — single continuous shot'
    look_at(camera,cc['target']);camera.data.lens=cc['lens_mm'];camera.data.sensor_width=cc['sensor_width_mm']
    camera.data.clip_start=.01;camera.data.clip_end=100.;camera.data.dof.use_dof=True;camera.data.dof.aperture_fstop=cc['aperture_fstop'];camera.data.dof.focus_distance=cc['focus_distance_m'];s.camera=camera
    s.frame_set(1);bpy.context.view_layer.update()
    ledger['car']={k:cfg['physics']['car'][k] for k in ['length_m','body_width_m','wheel_radius_m','wheelbase_m','wheel_center_track_m']}
    return s,roots,ledger,camera_audit(s,camera,physics,cfg,assembly)

def setup_template(path,cfg,physics):
    bpy.ops.wm.open_mainfile(filepath=str(path))
    s=bpy.context.scene
    names=['car_body','wheel_0','wheel_1','wheel_2','wheel_3']
    roots={n:bpy.data.objects[n] for n in names}
    if not cfg['physics']['car'].get('present',True):
        removed={o for root in roots.values() for o in [root,*root.children_recursive]}
        for obj in removed:bpy.data.objects.remove(obj,do_unlink=True)
        roots={}
    else:
        for obj in roots.values():obj.animation_data_clear()
        animate(roots,physics)
    s.render.use_persistent_data=False
    s.render.fps=24;s.render.fps_base=1.;s.frame_start=1;s.frame_end=96
    s.frame_set(1);bpy.context.view_layer.update()
    assembly=[o for o in s.objects if o.type=='MESH' and any(m and m.name in ['Orange polypropylene track','Blue molded risers and connectors','Dark grey hinge pins','Black rubber feet'] for m in o.data.materials)]
    ledger={'scene_template':str(path),'scene_template_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            'car':{k:cfg['physics']['car'][k] for k in ['length_m','body_width_m','wheel_radius_m','wheelbase_m','wheel_center_track_m']}}
    return s,roots,ledger,camera_audit(s,s.camera,physics,cfg,assembly)

def exposure_signatures(scene,roots):
    """Conservative render reuse: dynamic frames share only within the same frame index;
    fully stationary exposures can share across time, using exact float32 matrices."""
    import struct
    assert not scene.cycles.use_animated_seed
    shutter=scene.render.motion_blur_shutter if scene.render.use_motion_blur else 0.
    position=getattr(scene.cycles,'motion_blur_position','CENTER')
    offsets={'CENTER':[-shutter/2,0.,shutter/2],'START':[0.,shutter/2,shutter],'END':[-shutter,-shutter/2,0.]}[position]
    rows=[]
    for frame in range(1,97):
        states=[]
        for offset in offsets:
            t=frame+offset;whole=int(t//1);scene.frame_set(whole,subframe=t-whole)
            data=b''.join(struct.pack('<16f',*(v for row in obj.matrix_world for v in row)) for name,obj in sorted(roots.items()))
            states.append(data)
        stationary=all(x==states[0] for x in states)
        payload=b''.join(states)+(b'static' if stationary else str(frame).encode())
        rows.append({'frame':frame,'signature':hashlib.sha256(payload).hexdigest(),'stationary_exposure':stationary})
    scene.frame_set(1)
    return {'method':'Exact float32 root matrices at shutter start, center and end; moving frames additionally require equal frame index. Static geometry, shaders, camera, lights, seed and compositor are common. Encoder temporal noise is applied afterwards.',
            'motion_blur_position':position,'shutter_frames':shutter,'frames':rows}

def main():
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--physics-json',type=Path,required=True)
    p.add_argument('--mode',choices=['prepare','frames','animation'],default='animation')
    p.add_argument('--keyframes',nargs='+',type=int);p.add_argument('--frame-start',type=int,default=1);p.add_argument('--frame-end',type=int,default=96)
    p.add_argument('--device',choices=['cpu','auto'],default='cpu');p.add_argument('--appearance-json',type=Path)
    p.add_argument('--base-scene',type=Path);p.add_argument('--frames',nargs='+',type=int)
    p.add_argument('--skip-existing',action='store_true');p.add_argument('--worker-id',default='main')
    a=p.parse_args(argv);out=a.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    result=json.loads(a.physics_json.read_text());cfg=result['configuration']
    if a.appearance_json:
        updates=json.loads(a.appearance_json.read_text())
        if set(updates)!={'appearance'}:raise ValueError('Only appearance overrides are accepted by render.')
        cfg=merge(cfg,updates)
    begin=time.perf_counter();prepared=out/'toy_car_track_jump.blend'
    if a.mode=='frames' and prepared.is_file():
        stored=json.loads((out/'scenario_metadata.json').read_text())
        if stored['physics_input_sha256']!=hashlib.sha256(a.physics_json.read_bytes()).hexdigest():raise ValueError('Prepared scene physics mismatch')
        bpy.ops.wm.open_mainfile(filepath=str(prepared));s=bpy.context.scene
        roots={n:bpy.data.objects[n] for n in ['car_body','wheel_0','wheel_1','wheel_2','wheel_3'] if n in bpy.data.objects}
        ledger=stored['dimension_ledger'];audit=json.loads((out/'camera_validation.json').read_text())
    elif a.base_scene:s,roots,ledger,audit=setup_template(a.base_scene,cfg,result)
    else:s,roots,ledger,audit=setup(cfg,result)
    backend=set_device(a.device)
    if (result['case_id']=='source' and not audit['all_car_silhouettes_in_frame']) or not audit['all_track_in_frame'] or not audit['all_track_assembly_in_frame']:
        save_json(out/'camera_validation.json',audit)
        raise RuntimeError('Camera does not cover the full scene trajectory.')
    metadata={'schema_version':1,'scene':'toy_car_track_jump','configuration':cfg,'configuration_sha256':signature(cfg),
        'blender_version':bpy.app.version_string,'render_backend':backend,'threads':s.render.threads,
        'physics_input_sha256':hashlib.sha256(a.physics_json.read_bytes()).hexdigest(),
        'camera_is_static':True,'camera_keyframes':0,'playback_rate':1.,
        'animation_source':'unmodified 240 Hz MuJoCo chassis and wheel poses; quaternion sign continuity only; deletion case contains no dynamic objects',
        'dimension_ledger':ledger,'physics_signature':signature(cfg['physics']),
        'appearance_signature':signature(cfg['appearance']),'render_settings':cfg['render'],
        'physical_limitations':['Tires use rigid capsule contact proxies; the floor contact uses a damped spring to approximate compliance.',
            'Planar floor and sampled rigid ramp approximate manufactured objects; no experimentally calibrated toy.',
            'Tire compliance is represented by soft floor contact; the visible wheel keeps its shape.']}
    if a.worker_id=='main' and a.mode!='frames':
        save_json(out/'scenario_metadata.json',metadata);save_json(out/'camera_validation.json',audit)
        save_json(out/'ground_truth_transforms.json',{'schema_version':1,'fps':result['fps'],'units':cfg['physics']['units'],
            'object_ids':{'car_body':'C01','wheel_0':'WFL','wheel_1':'WFR','wheel_2':'WRL','wheel_3':'WRR'},
            'object_presence':{k:bool(cfg['physics']['car'].get('present',True)) for k in ['C01','WFL','WFR','WRL','WRR']},
            'frames':result['frames'],'static_objects':{'track_profile_m':track_profile(cfg),'floor_height_m':0.,'launcher_colliders':launcher_colliders(cfg)}})
        s.render.filepath=str(out/'frames'/'####')
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=str(out/'toy_car_track_jump.blend'))
        save_json(out/'frame_signatures.json',exposure_signatures(s,roots))
    if a.mode=='prepare':
        print(json.dumps({'prepared':True,'camera_audit':{k:v for k,v in audit.items() if k!='frames'}},indent=2));return
    directory=out/('keyframes' if a.keyframes else 'frames');directory.mkdir(exist_ok=True)
    numbers=a.frames or a.keyframes or list(range(a.frame_start,min(a.frame_end,s.frame_end)+1))
    records=[]
    for frame in numbers:
        path=directory/f'{frame:04d}.png'
        if a.skip_existing and path.is_file():continue
        s.frame_set(frame);s.render.filepath=str(path)
        start=time.perf_counter();bpy.ops.render.render(write_still=True)
        records.append({'frame':frame,'wall_sec':time.perf_counter()-start})
    save_json(out/f'render_timing_{a.worker_id}.json',{'stage':'render','backend':backend,
        'worker_id':a.worker_id,'wall_sec':time.perf_counter()-begin,'frames':records})

if __name__=='__main__':main()
