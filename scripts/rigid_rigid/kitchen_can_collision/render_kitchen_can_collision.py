"""Import the kitchen, replay verified rigid-body poses and render the four-second clip."""
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    if _Path(__file__).with_name("entrypoints.json").is_file() and (_Path(__file__).resolve().parents[2]/"pcve_scene_entry.py").is_file():
        _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
        # This scene also renders from a Python that has the bpy module
        # (--render-python). Load bpy first for real runs so prepare_entry keeps
        # the render in this process instead of relaunching Blender; planning
        # calls (--help/--dry-run/--describe) stay import-free.
        if not {"-h", "--help", "--dry-run", "--describe"} & set(_sys.argv[1:]):
            try:
                import bpy  # noqa: F401
            except ImportError:
                pass
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__, "render")
# PCVE_UNIFIED_ENTRY_END

# Resolve the shared scripts directory, then this scene's module folders.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_scripts_dir = _clean_scene_dir.parents[1]
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / 'scripts').is_dir())
if str(_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
# Shared modules live in scripts/; scene-local modules live in this directory and
# its physics/, appearance/ and tools/ subdirectories.
for _scene_sub in ("", "physics", "appearance", "tools"):
    _scene_sub_dir = _clean_scene_dir / _scene_sub if _scene_sub else _clean_scene_dir
    if _scene_sub_dir.is_dir() and str(_scene_sub_dir) not in _clean_sys.path:
        _clean_sys.path.insert(1, str(_scene_sub_dir))

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import shutil
import subprocess
from pcve_scene_runtime import python_for,parse_render_args,run_renderer
from scene_config import add_scenario_arguments,PHYSICS_LIMITS
from validate_kitchen_can_collision import validate_cache
from scene_geometry import KEYS
from look_kitchen_can_collision import build_environment,make_cans,used_assets
from tabletop_props import validate_island_props
from pcve_render_quality import configure_renderer,configure_color

# AgX exposure for the daylit kitchen: the sun patch on the oak sits about two
# stops over the room, as a phone exposes a sunlit interior.
EXPOSURE=1.2


def render(args):
    import bpy
    from mathutils import Vector
    from bpy_extras.object_utils import world_to_camera_view
    if args.samples<1 or min(args.resolution)<1:raise ValueError('Invalid render settings')
    out=args.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    physics=args.physics_json.resolve() if args.physics_json else out/'physics_transforms.json'
    scenario_keys=('scenario_json','scenario_overrides_json',*PHYSICS_LIMITS,'fps','duration_sec','slow_motion')
    if args.physics_json:
        if args.remove_receiver or any(getattr(args,k) is not None for k in scenario_keys):raise ValueError('Resimulate before changing cached initial conditions/timing')
    else:
        command=[str(args.physics_python or python_for('physics')),str(Path(__file__).with_name('simulate_kitchen_can_collision.py')),'--out',str(physics)]
        for key in scenario_keys:
            value=getattr(args,key)
            if value is not None:command+=['--'+key.replace('_','-'),str(value)]
        if args.remove_receiver:command+=['--remove-receiver']
        subprocess.run(command,check=True)
    data=json.loads(physics.read_text(encoding='utf-8'));validate_cache(data)
    if physics!=out/'physics_transforms.json':shutil.copy2(physics,out/'physics_transforms.json')
    (out/'simulation_metrics.json').write_text(json.dumps(data['quality'],indent=2),encoding='utf-8')
    s=deepcopy(data['scenario'])
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
    device=configure_renderer(bpy,scene,args);configure_color(scene)
    scene.view_settings.exposure=EXPOSURE
    # Half-shutter motion blur, as a 180-degree film camera records a rolling can.
    # Persistent data has to be off with it: in Blender 4.3 an object that has
    # come to rest vanishes from every later frame rendered in the same session
    # when both are on, and both cans stop well before the clip ends.
    scene.render.use_motion_blur=True;scene.render.motion_blur_shutter=.5
    scene.render.use_persistent_data=False
    scene.render.resolution_x,scene.render.resolution_y=args.resolution;scene.render.resolution_percentage=100
    scene.render.fps=data['playback_fps'];scene.frame_start=1;scene.frame_end=data['frame_end']
    room=build_environment(bpy,scene);objects=make_cans(bpy)
    props_validation=validate_island_props(bpy)
    for key,o in objects.items():
        o.hide_render=o.hide_viewport=not data['objects'][key]['present']
    for f in data['frames']:
        for key in KEYS:
            if not f[key]['present']:continue
            o=objects[key];state=f[key];o.location=state['location'];q=state['quaternion_xyzw']
            o.rotation_mode='QUATERNION';o.rotation_quaternion=(q[3],q[0],q[1],q[2])
            o.keyframe_insert('location',frame=f['frame_index']);o.keyframe_insert('rotation_quaternion',frame=f['frame_index'])
    for o in objects.values():
        if o.animation_data is None:continue
        for curve in o.animation_data.action.fcurves:
            for k in curve.keyframe_points:k.interpolation='LINEAR'
    cam=s['camera'];bpy.ops.object.camera_add(location=cam['location']);camera=bpy.context.object
    camera.name='Kitchen collision camera';camera.data.lens=cam['lens_mm']
    camera.rotation_euler=(Vector(cam['target'])-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.dof.use_dof=True;camera.data.dof.focus_distance=(Vector(cam['target'])-camera.location).length
    camera.data.dof.aperture_fstop=8.;scene.camera=camera
    bpy.context.view_layer.update();cm=[list(row) for row in camera.matrix_world]
    max_error=0.;min_screen_margin=1.;min_prop_clearance=10.;sight_lines=0
    can_names={o.name for o in objects.values()}
    for f in data['frames']:
        scene.frame_set(f['frame_index']);bpy.context.view_layer.update()
        depsgraph=bpy.context.evaluated_depsgraph_get()
        for key in KEYS:
            if not f[key]['present']:continue
            # Nothing but a can may stand between the camera and a can: the
            # props are not in the simulation and must not hide the motion.
            centre=objects[key].matrix_world.translation.copy();eye=camera.matrix_world.translation.copy()
            side=(centre-eye).cross(Vector((0,0,1))).normalized()
            for target in (centre,centre+side*.02,centre-side*.02,centre+Vector((0,0,.02))):
                ray=target-eye
                hit,_,_,_,blocker,_=scene.ray_cast(depsgraph,eye,ray.normalized(),distance=ray.length)
                sight_lines+=1
                if hit and blocker.name not in can_names:
                    raise RuntimeError(f'{blocker.name} hides the {key} from the camera on frame {f["frame_index"]}')
            max_error=max(max_error,max(abs(objects[key].matrix_world[a][b]-f[key]['matrix_world'][a][b]) for a in range(4) for b in range(4)))
            for corner in objects[key].bound_box:
                uv=world_to_camera_view(scene,camera,objects[key].matrix_world@Vector(corner))
                if uv.z<=0:raise RuntimeError('Can behind camera')
                min_screen_margin=min(min_screen_margin,uv.x,1-uv.x,uv.y,1-uv.y)
            points=[objects[key].matrix_world@Vector(corner) for corner in objects[key].bound_box]
            xmin,xmax=min(p.x for p in points),max(p.x for p in points)
            ymin,ymax=min(p.y for p in points),max(p.y for p in points)
            for prop in props_validation['props']:
                px0,px1,py0,py1=prop['xy_bounds']
                gapx=max(0.,px0-xmax,xmin-px1);gapy=max(0.,py0-ymax,ymin-py1)
                min_prop_clearance=min(min_prop_clearance,math.hypot(gapx,gapy))
    if max_error>2e-6:raise RuntimeError(f'Blender replay differs from physics by {max_error}')
    if min_screen_margin<.02:raise RuntimeError(f'Can outside safe camera framing: {min_screen_margin}')
    if min_prop_clearance<.02:raise RuntimeError(f'Decor obstructs the can trajectory: {min_prop_clearance}')
    props_validation.update(checked_frames=len(data['frames']),min_can_clearance_m=min_prop_clearance,
                            camera_sight_lines_checked=sight_lines,room=room)
    (out/'tabletop_validation.json').write_text(json.dumps(props_validation,indent=2),encoding='utf-8')
    metadata=deepcopy(s)
    metadata['render'].update(resolution=args.resolution,samples=args.samples,engine=args.engine,device=device,mode=args.mode)
    metadata['assets']=used_assets()
    gt=dict(schema_version=1,scene=data['scene'],fps=scene.render.fps,frame_start=1,frame_end=data['frame_end'],
            scenario=metadata,physics={k:v for k,v in data.items() if k!='frames'},
            objects={k:dict(v,object_name=objects[k].name) for k,v in data['objects'].items()},
            camera=dict(object_name=camera.name,matrix_world=cm,lens_mm=camera.data.lens,
                        sensor_width_mm=camera.data.sensor_width,resolution=args.resolution,
                        sensor_fit=camera.data.sensor_fit,projection='perspective'),
            sample_fps=data['sample_fps'],slow_motion=data['slow_motion'],
            physical_duration_sec=data['physical_duration_sec'],playback_duration_sec=data['playback_duration_sec'],
            frames=[dict(f,camera_matrix_world=cm) for f in data['frames']])
    for name,payload in [('ground_truth_transforms.json',gt),('scenario_metadata.json',metadata),
                         ('render_validation.json',dict(valid=True,checked_frames=len(data['frames']),objects_checked=sum(v['present'] for v in data['objects'].values()),
                                                        max_matrix_error=max_error,min_screen_margin=min_screen_margin))]:
        (out/name).write_text(json.dumps(payload,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    preview=args.preview_frame or min(scene.frame_end,round(((data['quality']['first_impact_sec'] or 0)+.22)*data['sample_fps'])+1)
    if not 1<=preview<=scene.frame_end:raise ValueError('Preview frame outside trajectory')
    scene.frame_set(preview);bpy.ops.file.pack_all()
    scene.render.image_settings.file_format='PNG';scene.render.filepath=str(out/'preview.png')
    if args.mode not in ('build','keyframes'):bpy.ops.render.render(write_still=True)
    if args.mode=='keyframes':
        impact=math.ceil((data['quality']['first_impact_sec'] or 0)*data['sample_fps'])+1
        indices=args.keyframes or [1,max(1,impact-1),impact,impact+5,round(2*data['sample_fps'])+1,scene.frame_end]
        if args.keyframes and any(not 1<=i<=scene.frame_end for i in indices):raise ValueError('Keyframe outside trajectory')
        indices=sorted({min(scene.frame_end,i) for i in indices})
        for index in indices:
            scene.frame_set(index);scene.render.filepath=str(out/f'frame_{index:04d}.png');bpy.ops.render.render(write_still=True)
        shutil.copy2(out/f'frame_{min(indices,key=lambda i:abs(i-preview)):04d}.png',out/'preview.png')
        (out/'keyframes.json').write_text(json.dumps([dict(frame=i,time_sec=(i-1)/data['sample_fps'],file=f'frame_{i:04d}.png') for i in indices],indent=2),encoding='utf-8')
    if args.mode=='animation':
        scene.render.image_settings.file_format='FFMPEG';scene.render.ffmpeg.format='MPEG4';scene.render.ffmpeg.codec='H264'
        scene.render.ffmpeg.constant_rate_factor='HIGH';scene.render.filepath=str(out/'kitchen_can_collision.mp4')
        scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'kitchen_can_collision.blend'))
    if args.mode=='animation':
        bpy.ops.render.render(animation=True);shutil.copy2(out/'kitchen_can_collision.mp4',out/'video.mp4')


def main():
    p=add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--physics-json',type=Path)
    p.add_argument('--physics-python',type=Path);p.add_argument('--engine',choices=('cycles','eevee'),default='cycles')
    p.add_argument('--device',choices=('auto','cpu'),default='auto');p.add_argument('--samples',type=int,default=48)
    p.add_argument('--resolution',nargs=2,type=int,default=[960,540])
    p.add_argument('--mode',choices=('build','preview','keyframes','animation'),default='keyframes')
    p.add_argument('--preview-frame',type=int)
    p.add_argument('--keyframes',nargs='+',type=int,help='Frame indices for --mode keyframes')
    render(parse_render_args(p))


if __name__=='__main__':run_renderer(main,'kitchen_can_collision')
