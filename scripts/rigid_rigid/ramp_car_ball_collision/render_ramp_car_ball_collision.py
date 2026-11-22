"""Fixed camera, real-time Cycles replay of unmodified solved poses."""
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
        prepare_entry(__file__,'render')
# PCVE_UNIFIED_ENTRY_END
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from pcve_assets import asset
from scene_config import save_json,signature
from look_ramp_car_ball_collision import room,car,ball,lighting,look_at,honest_daylight,plaster_walls,sofa_textiles
from object_presence import keyframe_presence,apply_frame_presence

def device(choice):
    if choice=='cpu':bpy.context.scene.cycles.device='CPU';return 'CPU'
    prefs=bpy.context.preferences.addons['cycles'].preferences
    for backend in ['OPTIX','CUDA','METAL']:
        try:
            prefs.compute_device_type=backend;prefs.get_devices();sel=[d for d in prefs.devices if d.type==backend]
            if not sel:continue
            for d in prefs.devices:d.use=d in sel
            bpy.context.scene.cycles.device='GPU';return backend+': '+', '.join(d.name for d in sel)
        except Exception:pass
    bpy.context.scene.cycles.device='CPU';return 'CPU'

def build(result,assets):
    bpy.ops.wm.read_factory_settings(use_empty=True);s=bpy.context.scene;cfg=result['configuration'];r=cfg['render']
    s.unit_settings.system='METRIC';s.unit_settings.scale_length=1.;s.render.engine='CYCLES'
    s.cycles.samples=r['samples'];s.cycles.use_denoising=r['denoising'];s.cycles.denoising_use_gpu=True;s.cycles.max_bounces=8;s.cycles.diffuse_bounces=4;s.cycles.glossy_bounces=4
    s.render.resolution_x,s.render.resolution_y=r['resolution'];s.render.resolution_percentage=100;s.render.fps=r['fps']
    s.frame_start=1;s.frame_end=result['frame_end'];s.render.use_persistent_data=r['persistent_data']
    s.view_settings.view_transform=r['color_management'];s.view_settings.look='AgX - Medium High Contrast'
    s.render.use_motion_blur=r['motion_blur_shutter_frames']>0;s.render.motion_blur_shutter=r['motion_blur_shutter_frames']
    s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB';s.render.image_settings.compression=20
    ledger=room(cfg,assets);roots=car(cfg) if cfg['physics']['car'].get('present',True) else {}
    if cfg['physics']['ball']['present']:roots['ball']=ball(cfg)
    lighting(cfg)
    # Finishing pass: real-sky-only daylight, scanned plaster and textile refinements.
    ledger['room_finish']={'lighting':honest_daylight(cfg),'walls':plaster_walls(cfg),'sofa':sofa_textiles(cfg)}
    s.cycles.denoising_use_gpu=False
    previous={}
    for sample in result['trajectory_samples']:
        f=sample['time_sec']*r['fps']+1
        for name,data in sample['objects'].items():
            obj=roots[name];obj.location=data['location'];x,y,z,w=data['quaternion_xyzw'];quat=(w,x,y,z)
            if name in previous and sum(a*b for a,b in zip(previous[name],quat))<0:quat=tuple(-v for v in quat)
            previous[name]=quat;obj.rotation_quaternion=quat;obj.keyframe_insert(data_path='location',frame=f);obj.keyframe_insert(data_path='rotation_quaternion',frame=f)
    for obj in roots.values():
        if obj.animation_data:
            for fc in obj.animation_data.action.fcurves:
                for key in fc.keyframe_points:key.interpolation='LINEAR'
    keyframe_presence(roots,cfg)
    c=cfg['appearance']['camera'];bpy.ops.object.camera_add(location=c['location']);cam=bpy.context.object;cam.name='Fixed oblique camera';look_at(cam,c['target'])
    cam.data.lens=c['lens_mm'];cam.data.sensor_width=c['sensor_width_mm'];cam.data.clip_start=.01;cam.data.clip_end=40.;cam.data.dof.use_dof=c.get('use_depth_of_field',False)
    if cam.data.dof.use_dof:cam.data.dof.focus_distance=c['focus_distance_m'];cam.data.dof.aperture_fstop=c['f_stop']
    s.camera=cam
    s.frame_set(1);bpy.context.view_layer.update();projections=[]
    for frame in result['frames']:
        out={}
        for name,data in frame['objects'].items():
            if name.startswith('wheel'):continue
            radius=.03 if name=='ball' else .067;xyz=Vector(data['location']);uv=world_to_camera_view(s,cam,xyz)
            edge=world_to_camera_view(s,cam,xyz+cam.matrix_world.to_quaternion()@Vector((radius,0,0)))
            diameter=abs(edge.x-uv.x)*2*r['resolution'][0]
            out[name]={'uv':[uv.x,uv.y],'bounding_diameter_px':diameter,'in_frame':diameter/2+3<uv.x*r['resolution'][0]<r['resolution'][0]-diameter/2-3 and diameter/2+3<uv.y*r['resolution'][1]<r['resolution'][1]-diameter/2-3}
        projections.append({'frame_index':frame['frame_index'],'objects':out})
    return s,roots,ledger,projections

def main():
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    pa=argparse.ArgumentParser();pa.add_argument('--physics-json',type=Path,required=True);pa.add_argument('--out-dir',type=Path,required=True)
    pa.add_argument('--asset-root',type=Path,default=asset('polyhaven'));pa.add_argument('--mode',choices=['prepare','frames','animation'],default='animation')
    pa.add_argument('--keyframes',type=int,nargs='+');pa.add_argument('--device',choices=['auto','cpu'],default='auto');pa.add_argument('--skip-existing',action='store_true')
    pa.add_argument('--frame-start',type=int,default=1);pa.add_argument('--frame-end',type=int);pa.add_argument('--input-blend',type=Path)
    pa.add_argument('--appearance-json',type=Path,help='Appearance-only override; solved physics JSON stays byte-identical')
    pa.add_argument('--synchronized-cache',action='store_true',help='Runtime texture cache with explicit full mesh refresh; saved scene retains its declared default')
    pa.add_argument('--refresh-dynamic-only',action='store_true',help='With synchronized cache, refresh solved-body child meshes only; keep static background BVHs cached')
    a=pa.parse_args(argv);out=a.out_dir.resolve();out.mkdir(parents=True,exist_ok=True);result=json.loads(a.physics_json.read_text());cfg=result['configuration']
    if a.refresh_dynamic_only and not a.synchronized_cache:pa.error('--refresh-dynamic-only requires --synchronized-cache')
    if a.appearance_json:
        from copy import deepcopy
        result=deepcopy(result);cfg=result['configuration'];cfg['appearance']=json.loads(a.appearance_json.read_text())
    if a.input_blend:
        bpy.ops.wm.open_mainfile(filepath=str(a.input_blend));s=bpy.context.scene;ledger={};projections=[]
        roots={n:bpy.data.objects[n] for n in ['car_body','wheel_0','wheel_1','wheel_2','wheel_3','ball'] if n in bpy.data.objects}
    else:s,roots,ledger,projections=build(result,a.asset_root)
    backend=device(a.device)
    if not a.input_blend:
        save_json(out/'scenario_metadata.json',{'configuration':cfg,'configuration_sha256':signature(cfg),'physics_sha256':hashlib.sha256(a.physics_json.read_bytes()).hexdigest(),
            'blender_version':bpy.app.version_string,'dimension_ledger':ledger,'camera_static':True,'playback_rate':1.,'projected_bounds':projections,'denoising_use_gpu':s.cycles.denoising_use_gpu,
            'all_objects_in_frame':all(v['in_frame'] for f in projections for v in f['objects'].values()),
            'minimum_ball_diameter_px':min([f['objects']['ball']['bounding_diameter_px'] for f in projections if 'ball' in f['objects']] or [0.]),
            'animation_source':'Solver poses sampled at 240 Hz; quaternion hemisphere continuity; no authored motion or spin',
            'asset_root':str(a.asset_root.resolve())})
        save_json(out/'ground_truth_transforms.json',{'scene':result['scene'],'fps':cfg['render']['fps'],'units':cfg['physics']['units'],'frames':result['frames'],'contact_events':result['contact_events'],'intervention_events':result.get('intervention_events',[]),'camera':cfg['appearance']['camera']})
        bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/'ramp_car_ball_collision.blend'))
    if a.synchronized_cache:s.render.use_persistent_data=True
    refresh_objects=[]
    for obj in s.objects:
        if obj.type not in {'MESH','CURVE'}:continue
        root=obj
        while root.parent:root=root.parent
        if not a.refresh_dynamic_only or root.name in {'car_body','wheel_0','wheel_1','wheel_2','wheel_3','ball'}:refresh_objects.append(obj)
    start=time.monotonic();rendered=[]
    if a.mode!='prepare':
        (out/'frames').mkdir(exist_ok=True)
        requested=a.keyframes or [1,13,21,25,31,41,57,77,96] if a.mode=='frames' else range(a.frame_start,(a.frame_end or result['frame_end'])+1)
        for frame in requested:
            path=out/'frames'/('frame_%04d.png'%frame)
            if a.skip_existing and path.is_file():continue
            s.frame_set(frame)
            apply_frame_presence(roots,cfg,frame)
            if a.synchronized_cache:
                for obj in refresh_objects:obj.data.update_tag();obj.update_tag(refresh={'DATA'})
            bpy.context.view_layer.update();s.render.filepath=str(path);bpy.ops.render.render(write_still=True);rendered.append(frame)
    render_sec=time.monotonic()-start;encode_sec=0.
    if a.mode=='animation' and a.frame_start==1 and (a.frame_end is None or a.frame_end==result['frame_end']):
        start=time.monotonic();subprocess.run(['ffmpeg','-y','-v','error','-framerate',str(cfg['render']['fps']),'-start_number','1','-i',str(out/'frames/frame_%04d.png'),'-frames:v',str(result['frame_end']),'-c:v','libx264','-preset','slow','-crf','17','-pix_fmt','yuv420p','-movflags','+faststart',str(out/'video.mp4')],check=True);encode_sec=time.monotonic()-start
    save_json(out/('render_report.json' if a.frame_start==1 else 'render_report_%04d.json'%a.frame_start),{'render_sec':render_sec,'encode_sec':encode_sec,'backend':backend,'CUDA_VISIBLE_DEVICES':os.environ.get('CUDA_VISIBLE_DEVICES'),'mode':a.mode,'rendered_frames':rendered,'synchronized_cache':a.synchronized_cache,'explicit_full_geometry_refresh':a.synchronized_cache and not a.refresh_dynamic_only,'dynamic_only_geometry_refresh':a.refresh_dynamic_only,'refreshed_mesh_curve_count':len(refresh_objects),'saved_scene_persistent_data':cfg['render']['persistent_data']})
    print(json.dumps({'render_sec':render_sec,'encode_sec':encode_sec,'backend':backend}),flush=True)

if __name__=='__main__':main()
