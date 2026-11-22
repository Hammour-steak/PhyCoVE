"""Replay the native coupled states in the original packed court scene (Blender 4.3.2).

The 96 frame centres are genuine native states; shutter samples interpolate the
native 3840 Hz records linearly, exactly as the solver does. Appearance changes are
made by appearance/realism.py through the hook before render_setup is written."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
if os.name!='posix':raise RuntimeError('Blender is remote-only')
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[4]
OUT_ROOT=Path(os.environ.get('PCVE_TENNIS_WORK',str(ROOT/'renders/tennis_net_hit')))
p=argparse.ArgumentParser()
p.add_argument('--cache',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--start-frame',type=int,default=1)
p.add_argument('--end-frame',type=int,default=96)
p.add_argument('--samples',type=int,default=128)
p.add_argument('--gpu',type=int,default=0)
p.add_argument('--case-id',required=True)
p.add_argument('--audit-only',action='store_true')
p.add_argument('--device',choices=('OPTIX','CUDA','CPU'),default='OPTIX')
p.add_argument('--threads',type=int,default=6)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
if not a.out.resolve().is_relative_to(OUT_ROOT.resolve()):raise ValueError('Output must stay under '+str(OUT_ROOT))
a.out.mkdir(parents=True,exist_ok=True);(a.out/'frames').mkdir(exist_ok=True)
start=time.monotonic()
for obj in list(bpy.data.objects):
    if obj.type=='MESH' and obj.data.shape_keys:
        obj.shape_key_clear()
    if obj.animation_data:obj.animation_data_clear()

with np.load(a.cache,allow_pickle=False) as z:
    states={k:z[k] for k in ('times','net_positions','net_edges','net_edge_kind','band_positions',
                              'strap_surface_positions','ball_positions','ball_quaternions')}
with np.load(a.cache,allow_pickle=False) as z:
    net_present=bool(z['net_present'])
    # DELETE tennis_ball: the cache carries ball_present false (the published caches have no such key: present).
    ball_present=bool(z['ball_present']) if 'ball_present' in z.files else True
times=states['times'];fps=24
for t in np.arange(96)/24:
    if np.min(abs(times-t))>1e-10:raise ValueError('Missing genuine native frame center')
if float(times[0])!=0 or times[-1]<0:raise ValueError('Unexpected motion time bounds')
scene=bpy.context.scene
# Packed historical scenes retain compositor output paths. Redirect every
# file-output node before the first render so no historical sidecar is touched.
owned_compositor_outputs=[]
if scene.use_nodes and scene.node_tree:
    for node_index,node in enumerate(scene.node_tree.nodes):
        if node.type=='OUTPUT_FILE':
            node.base_path=str(a.out/'instance_masks_raw')
            for slot_index,slot in enumerate(node.file_slots):
                slot.path=f'node_{node_index:02d}_slot_{slot_index:02d}_'
                owned_compositor_outputs.append({'node':node.name,'slot_index':slot_index,'base_path':node.base_path,'relative_prefix':slot.path})
scene.render.fps=fps;scene.frame_start=1;scene.frame_end=96;scene.render.fps_base=1
scene.render.resolution_x=1280;scene.render.resolution_y=720;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
scene.cycles.samples=a.samples;scene.cycles.use_denoising=True;scene.render.use_persistent_data=True
scene.render.threads_mode='FIXED';scene.render.threads=a.threads
scene.render.use_motion_blur=True;scene.render.motion_blur_shutter=fps/480
if hasattr(scene.render,'motion_blur_position'):
    scene.render.motion_blur_position='CENTER'
    shutter_position=scene.render.motion_blur_position
elif hasattr(scene.cycles,'motion_blur_position'):
    scene.cycles.motion_blur_position='CENTER'
    shutter_position=scene.cycles.motion_blur_position
else:
    raise ValueError('Cannot verify centered physical shutter interval')
if a.audit_only or a.device=='CPU':
    if a.audit_only:assert os.environ.get('CUDA_VISIBLE_DEVICES')==''
    scene.cycles.device='CPU';render_devices=[]
else:
    preferences=bpy.context.preferences.addons['cycles'].preferences
    preferences.compute_device_type=a.device;preferences.get_devices()
    for d in preferences.devices:d.use=d.type==a.device
    if not any(d.use for d in preferences.devices):raise RuntimeError(a.device+' GPU missing')
    scene.cycles.device='GPU';render_devices=[d.name for d in preferences.devices if d.use]
mapped=[];deleted=[]
if not net_present:
    for obj in list(scene.objects):
        if obj.get('physical_owner') in {'net','center_strap','court_anchor'} or obj.pass_index in (2,3):
            deleted.append(obj.name);bpy.data.objects.remove(obj,do_unlink=True)
    if any(obj.get('physical_owner') in {'net','center_strap','court_anchor'} for obj in scene.objects):raise ValueError('Deleted net still visible')
else:
    for kind,name in ((0,'Manufactured open polyethylene mesh'),(1,'Native installed steel headline'),
                      (2,'Native manufactured lower binding'),(3,'Native laced side binding')):
        obj=bpy.data.objects.get(name)
        ids=np.unique(states['net_edges'][states['net_edge_kind']==kind])
        if obj is None or len(obj.data.vertices)!=len(ids):raise ValueError('Historical vertex map differs: '+name)
        mapped.append((obj,states['net_positions'],ids))
    for name,key in [('Native bound upper tape surface','band_positions'),
                     ('Native finite folded center strap surface','strap_surface_positions')]:
        obj=bpy.data.objects[name]
        if len(obj.data.vertices)!=states[key].shape[1]:raise ValueError('Surface topology differs: '+name)
        mapped.append((obj,states[key],None))
ball=bpy.data.objects['physical_ball'];ball.rotation_mode='QUATERNION'
if not ball_present:
    # The ball and its mesh are not rendered; the empty keeps its static record for the replay checks.
    for obj in [ball,*ball.children_recursive]:
        obj.hide_render=True;deleted.append(obj.name)
for obj in [ball,*[item[0] for item in mapped]]:
    if not hasattr(obj.cycles,'motion_steps'):raise ValueError('Deformation shutter sampling control missing')
    obj.cycles.motion_steps=5
errors=[];orientation_errors=[]
def sample(array,t):
    i=max(0,min(len(times)-2,int(np.searchsorted(times,t,side='right')-1)))
    alpha=(t-times[i])/(times[i+1]-times[i])
    return (1-alpha)*array[i]+alpha*array[i+1]

# Native keys explicitly mark mesh deformation and ball motion for Cycles.
# Linear segments reproduce solver interpolation, without trajectory filtering.
bpy.app.handlers.frame_change_pre.clear()
centers=np.arange(scene.frame_end,dtype=float)/fps
playback_times=np.unique(np.clip((centers[:,None]+np.arange(-4,5)/3840).ravel(),0.,times[-1]))
playback_frames=1+playback_times*fps

def bulk_keys(owner,path,values,name):
    # keyframe_insert merges nearby frames (the shutter keys are only .00625
    # frames apart). Allocate the complete ordered FCurve directly so every
    # native exposure sample and every frame center survives independently.
    values=np.asarray(values)
    if values.ndim==1:values=values[:,None]
    owner.animation_data_create();action=bpy.data.actions.new(name)
    owner.animation_data.action=action
    for component in range(values.shape[1]):
        curve=action.fcurves.new(data_path=path,index=component)
        curve.keyframe_points.add(len(playback_frames))
        coords=np.column_stack((playback_frames,values[:,component])).astype(np.float32)
        curve.keyframe_points.foreach_set('co',coords.ravel())
        for point in curve.keyframe_points:point.interpolation='LINEAR'
        # update() also deduplicates keys with Blender's .01-frame tolerance.
        # These coordinates are already sorted; retain the dense native keys.
        assert len(curve.keyframe_points)==len(playback_times)
    return action

for obj,array,ids in mapped:
    evaluation_times=[]
    for k,t in enumerate(playback_times):
        vertices=sample(array,t)
        if ids is not None:vertices=vertices[ids]
        key=obj.shape_key_add(name='Basis' if k==0 else f'native_{k:04d}',from_mix=False)
        key.data.foreach_set('co',np.asarray(vertices,np.float32).ravel())
        key.interpolation='KEY_LINEAR'
        keys=obj.data.shape_keys;keys.use_relative=False
        evaluation_times.append(key.frame)
    bulk_keys(keys,'eval_time',evaluation_times,'Native deformation | '+obj.name)
positions=[];quaternions=[]
for t in playback_times:
    positions.append(sample(states['ball_positions'],t))
    q=sample(states['ball_quaternions'],t);quaternions.append(q/np.linalg.norm(q))
action=bulk_keys(ball,'location',positions,'Native rigid ball')
quaternions=np.asarray(quaternions)
for component in range(4):
    curve=action.fcurves.new(data_path='rotation_quaternion',index=component)
    curve.keyframe_points.add(len(playback_frames))
    curve.keyframe_points.foreach_set('co',np.column_stack((playback_frames,quaternions[:,component])).astype(np.float32).ravel())
    for point in curve.keyframe_points:point.interpolation='LINEAR'
    assert len(curve.keyframe_points)==len(playback_times)
# Check evaluated material coordinates with display modifiers temporarily off.
probes=np.unique(np.clip((centers[:,None]+np.array([-1/960,0.,1/960])).ravel(),0.,times[-1]))
modifier_flags=[(modifier,modifier.show_viewport) for obj,_,_ in mapped for modifier in obj.modifiers]
for modifier,_ in modifier_flags:modifier.show_viewport=False
bpy.context.view_layer.update()
for physical in probes:
    frame=1+physical*fps;scene.frame_set(int(frame),subframe=frame-int(frame))
    ball_error=float(np.max(np.abs(np.asarray(ball.location)-sample(states['ball_positions'],physical))))
    if ball_error>1e-6 and not a.audit_only:raise ValueError('Ball replay mismatch '+str({'time_s':float(physical),'maximum_error_m':ball_error,'actual':list(ball.location),'expected':sample(states['ball_positions'],physical).tolist()}))
    errors.append({'time_s':physical,'object':ball.name,'max_error_m':ball_error})
    expected_q=sample(states['ball_quaternions'],physical);expected_q/=np.linalg.norm(expected_q)
    quaternion_error=float(np.max(np.abs(np.asarray(ball.rotation_quaternion)-expected_q)))
    orientation_errors.append({'time_s':float(physical),'max_component_error':quaternion_error})
    if quaternion_error>1e-6 and not a.audit_only:raise ValueError('Ball orientation replay mismatch '+str((float(physical),quaternion_error)))
    for obj,array,ids in mapped:
        evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        actual=np.empty(len(evaluated.data.vertices)*3,np.float32)
        evaluated.data.vertices.foreach_get('co',actual)
        expected=sample(array,physical)
        if ids is not None:expected=expected[ids]
        error=float(np.max(np.abs(actual.reshape(-1,3)-expected)))
        is_center=abs(float(physical)*fps-round(float(physical)*fps))<1e-8
        # Native video poses retain the1um gate. At shutter offsets, absolute
        # shape-key evaluation uses float32 time/coordinates; allow four ULPs
        # of the stored mesh scale, capped at2um. Native contact gates remain
        #1nm/1e-5N and the independent exposure contact gate remains20um.
        graphics_bound=1e-6 if is_center else min(2e-6,max(1e-6,4*float(np.spacing(np.float32(np.max(np.abs(expected)))))))
        if error>graphics_bound and not a.audit_only:raise ValueError('Replay mismatch: '+obj.name+' '+str((float(physical),error,graphics_bound)))
        errors.append({'time_s':physical,'object':obj.name,'max_error_m':error,'frame_center':is_center,'graphics_tolerance_m':graphics_bound})
for modifier,flag in modifier_flags:modifier.show_viewport=flag
bpy.context.view_layer.update()
key_counts=[len(curve.keyframe_points) for owner in [ball,*[obj.data.shape_keys for obj,_,_ in mapped]] for curve in owner.animation_data.action.fcurves]
assert all(count==len(playback_times) for count in key_counts)
report={'case_id':a.case_id,'net_present':net_present,'ball_present':ball_present,'deleted_objects':deleted,'remote_host':os.uname().nodename,'blender_version':bpy.app.version_string,
        'cuda_visible_devices':os.environ.get('CUDA_VISIBLE_DEVICES'),
        'original_packed_scene':bpy.data.filepath,'new_solver_cache':str(a.cache),
        'normal_speed':True,'fps':fps,'resolution':[1280,720],'motion_blur_exposure_s':1/480,'motion_blur_position':shutter_position,'object_motion_steps_setting':5,
        'native_blender_deformation_keys':True,'playback_sample_count':len(playback_times),'owned_compositor_outputs':owned_compositor_outputs,
        'source_camera_preserved':True,'replay_coordinate_checks':errors,
        'replay_orientation_checks':orientation_errors,
        'dense_fcurve_key_counts':key_counts,
        'camera_matrix_world':np.asarray(scene.camera.matrix_world).tolist(),'lens_mm':scene.camera.data.lens,
        'render_device_names':render_devices,'audit_only':a.audit_only}
# appearance/realism.py runs this file with __overlay__ in its globals (runpy.run_path) and records its look here.
if '__overlay__' in globals():report['appearance_overlay']=__overlay__(scene,a)
(a.out/f'render_setup_{a.start_frame:04d}.json').write_text(json.dumps(report,indent=2))
for frame in ([] if a.audit_only else range(a.start_frame,min(a.end_frame,scene.frame_end)+1)):
    path=a.out/'frames'/f'{frame:04d}.png'
    if path.is_file():continue
    scene.frame_set(frame)
    scene.render.filepath=str(path)
    bpy.ops.render.render(write_still=True)
    (a.out/f'render_progress_{a.start_frame:04d}.json').write_text(json.dumps({'last_frame':frame,'end_frame':min(a.end_frame,scene.frame_end),
        'elapsed_s':time.monotonic()-start}))
print('REMOTE_RENDER_COMPLETE',flush=True)
