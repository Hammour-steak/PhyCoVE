"""Replay the five physical pendulums in a daylit mid-century study."""
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


from pathlib import Path
import argparse,json,sys,subprocess,shutil
from copy import deepcopy
from pcve_scene_runtime import python_for
from scene_config import defaults
from scene_geometry import pivots
from look_newtons_cradle import build_environment,ENVIRONMENT_THEME
from study_room import EXPOSURE
from cradle_model import build_cradle
from desk_props import validate_props,check_frame
from render_quality import configure_renderer,configure_color,prepare_eevee

from pcve_scene_runtime import parse_render_args, run_renderer

def render(args):
    import bpy
    from mathutils import Vector
    out=args.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    physics=args.physics_json.resolve() if args.physics_json else out/'physics_transforms.json'
    if args.physics_json:
        if any(getattr(args,key) is not None for key in ('scenario_json','scenario_overrides_json','initial_height','restitution','fps','duration_sec','slow_motion')):
            raise ValueError('Resimulate to change physics/timing; cached trajectory cannot be edited by the renderer')
    else:
        command=[str(args.physics_python or python_for('physics')),str(Path(__file__).with_name('simulate_newtons_cradle.py')),'--out',str(physics)]
        for key in ('scenario_json','scenario_overrides_json','initial_height','restitution','fps','duration_sec','slow_motion'):
            value=getattr(args,key)
            if value is not None:command+=['--'+key.replace('_','-'),str(value)]
        subprocess.run(command,check=True)
    data=json.loads(physics.read_text(encoding='utf-8'));s=deepcopy(data['scenario']);c=s['physics']
    s['render'].update(resolution=list(args.resolution),samples=args.samples,engine=args.engine,mode=args.mode)
    if data['scene']!='newtons_cradle' or not data['quality']['valid']:raise ValueError('Invalid physics cache')
    if set(data['objects'])!={f'ball_{i:02d}' for i in range(5)}:raise ValueError('Cached cradle layout differs')
    if physics!=out/'physics_transforms.json':shutil.copy2(physics,out/'physics_transforms.json')
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
    s['render']['device']=configure_renderer(bpy,scene,args)
    configure_color(scene);scene.view_settings.exposure=EXPOSURE
    scene.render.resolution_x,scene.render.resolution_y=args.resolution;scene.render.resolution_percentage=100
    scene.render.fps=data['playback_fps'];scene.frame_start=1;scene.frame_end=data['frame_end']
    # Quarter-shutter motion blur (90-degree film shutter): at half shutter the fast end
    # balls smeared into a translucent ghost for a frame and read as flicker.
    # Persistent data has to be off with it: in Blender 4.3 an object that has
    # come to rest vanishes from every later frame rendered in the same session
    # when both are on, and the inner balls rest for most of the clip.
    scene.render.use_motion_blur=True;scene.render.motion_blur_shutter=.25
    scene.render.use_persistent_data=False
    if scene.render.engine=='CYCLES':
        # Sun glints off the chrome balls would otherwise be traced as
        # reflective caustics on the base and desk: real, but at 48 samples
        # they only come out as fireflies.
        scene.cycles.caustics_reflective=False;scene.cycles.caustics_refractive=False;scene.cycles.blur_glossy=1.
    build_environment(bpy,scene,c)
    s['render']['environment_theme']=ENVIRONMENT_THEME
    anchors=pivots(c);presence=c.get('ball_presence',[1]*5)
    objects,parts=build_cradle(bpy,c,anchors,presence)
    props=validate_props(bpy,c['table_height'])
    for frame in data['frames']:
        for key,obj in objects.items():
            state=frame[key]
            if not state.get('present',True):continue
            obj.location=state['location'];obj.rotation_mode='QUATERNION';q=state['quaternion_xyzw'];obj.rotation_quaternion=(q[3],q[0],q[1],q[2])
            obj.keyframe_insert('location',frame=frame['frame_index']);obj.keyframe_insert('rotation_quaternion',frame=frame['frame_index'])
    for obj in objects.values():
        for curve in obj.animation_data.action.fcurves:
            for key in curve.keyframe_points:key.interpolation='LINEAR'
    camera_cfg=deepcopy(s['camera'])
    if camera_cfg==defaults()['camera']:camera_cfg=dict(location=[.78,-1.58,1.29],target=[-.01,0,.89],lens_mm=58,focus_distance=1.86,fstop=16.0)
    s['camera']=camera_cfg
    bpy.ops.object.camera_add(location=camera_cfg['location']);camera=bpy.context.object;camera.data.lens=camera_cfg['lens_mm']
    camera.rotation_euler=(Vector(camera_cfg['target'])-camera.location).to_track_quat('-Z','Y').to_euler();scene.camera=camera
    if 'focus_distance' in camera_cfg:
        camera.data.dof.use_dof=True;camera.data.dof.focus_distance=camera_cfg['focus_distance'];camera.data.dof.aperture_fstop=camera_cfg['fstop']
    bpy.context.view_layer.update();camera_matrix=[list(row) for row in camera.matrix_world]
    # Ground-truth fields follow the shared rigid-body layout; slow-motion metadata is additive.
    gt=dict(schema_version=1,scene=data['scene'],fps=scene.render.fps,frame_start=1,frame_end=data['frame_end'],
        physics={key:value for key,value in data.items() if key!='frames'},scenario=s,
        objects={key:dict(meta,**({'object_name':objects[key].name} if key in objects else {}))
                 for key,meta in data['objects'].items()},
        camera=dict(object_name=camera.name,lens_mm=camera.data.lens,sensor_width_mm=camera.data.sensor_width,resolution=list(args.resolution)),
        sample_fps=data['sample_fps'],slow_motion=data['slow_motion'],physical_duration_sec=data['physical_duration_sec'],playback_duration_sec=data['playback_duration_sec'],
        frames=[dict(frame,camera_matrix_world=camera_matrix) for frame in data['frames']])
    (out/'ground_truth_transforms.json').write_text(json.dumps(gt,indent=2,ensure_ascii=False),encoding='utf-8')
    (out/'scenario_metadata.json').write_text(json.dumps(s,indent=2,ensure_ascii=False),encoding='utf-8')
    time=data['quality']['events'].get('first_ball_impact_sec',.2)+.17
    preview=args.preview_frame or min(scene.frame_end,round(time*data['sample_fps'])+1)
    if not 1<=preview<=scene.frame_end:raise ValueError('Preview frame outside cached trajectory')
    # Every frame: the replayed poses match the simulation, every ball stays in
    # the cradle's keep-out box (which the props keep clear of) and no prop
    # hides a ball from the camera.
    max_error=0;sight_lines=0
    for frame in data['frames']:
        scene.frame_set(frame['frame_index']);bpy.context.view_layer.update()
        for key,obj in objects.items():
            state=frame[key]
            if not state.get('present',True):continue
            expected=state['matrix_world']
            max_error=max(max_error,max(abs(obj.matrix_world[i][j]-expected[i][j]) for i in range(4) for j in range(4)))
        sight_lines+=check_frame(bpy,scene,camera,objects,frame,c['ball_radius'])
    if max_error>1e-5:raise RuntimeError('Blender replay differs from simulated rigid poses')
    (out/'render_validation.json').write_text(json.dumps(dict(checked_frames=len(data['frames']),objects_checked=len(objects),max_matrix_error=max_error,physics_changed=False,camera_sight_lines_checked=sight_lines,
        keep_out_box=props['keep_out_box'],min_prop_gap_to_keep_out_m=props['min_prop_gap_to_keep_out_m'],
        props=[p['object_name'] for p in props['props']])),encoding='utf-8')
    scene.frame_set(preview)
    prepare_eevee(bpy,scene,[*objects.values(),*parts])
    bpy.ops.file.pack_all()
    scene.render.image_settings.file_format='PNG';scene.render.filepath=str(out/'preview.png');bpy.ops.render.render(write_still=True)
    if args.mode=='animation':
        scene.render.image_settings.file_format='FFMPEG';scene.render.ffmpeg.format='MPEG4';scene.render.ffmpeg.codec='H264';scene.render.ffmpeg.constant_rate_factor='HIGH'
        scene.render.filepath=str(out/'newtons_cradle.mp4');scene.frame_set(1)
    # No .blend1 backup next to the outputs when a case is rendered again.
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'newtons_cradle.blend'),compress=True)
    if args.mode=='animation':
        bpy.ops.render.render(animation=True);shutil.copy2(out/'newtons_cradle.mp4',out/'video.mp4')

def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--physics-json',type=Path);p.add_argument('--physics-python',type=Path)
    p.add_argument('--scenario-json',type=Path);p.add_argument('--scenario-overrides-json',type=Path)
    p.add_argument('--initial-height',type=float);p.add_argument('--restitution',type=float);p.add_argument('--fps',type=int);p.add_argument('--duration-sec',type=float);p.add_argument('--slow-motion',type=int,choices=(1,2,4,8))
    p.add_argument('--engine',choices=('eevee','cycles'),default='cycles');p.add_argument('--device',choices=('auto','cpu'),default='auto');p.add_argument('--samples',type=int,default=32);p.add_argument('--resolution',type=int,nargs=2,default=[960,540]);p.add_argument('--mode',choices=('preview','animation'),default='animation');p.add_argument('--preview-frame',type=int)
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:];render(parse_render_args(p, argv))

if __name__=='__main__':run_renderer(main, 'newtons_cradle')
