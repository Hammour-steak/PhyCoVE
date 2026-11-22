"""Render the simulated poses of the ball and every individual wooden block."""
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
import argparse,json,math,sys,subprocess,shutil
from copy import deepcopy
from pcve_scene_runtime import python_for
from building_geometry import building_blocks
from look_ball_block_building import build_room,make_ball,make_block,ENVIRONMENT_THEME
from render_quality import configure_renderer,configure_color,prepare_eevee

from pcve_scene_runtime import parse_render_args, run_renderer

# The camera sees a bench in low morning sun and the shaded workshop around
# it; this exposure keeps the sunlit bench top below AgX's shoulder.
EXPOSURE=-.35
# Phone-like optics at the ground-truth camera: f/8 focused on the stack keeps
# the whole bench sharp and softens only the view through the back window.
F_STOP=8.

def render(args):
    import bpy
    from mathutils import Vector
    from workshop import check_clearance,check_sightlines
    out=args.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    physics=args.physics_json.resolve() if args.physics_json else out/'physics_transforms.json'
    if args.physics_json:
        if any(getattr(args,key) is not None for key in ('scenario_json','scenario_overrides_json','ball_mass','ball_speed','fps','duration_sec','slow_motion')):
            raise ValueError('Resimulate to change physics/timing; cached trajectory cannot be edited by the renderer')
    else:
        command=[str(args.physics_python or python_for('physics')),str(Path(__file__).with_name('simulate_ball_block_building.py')),'--out',str(physics)]
        for key in ('scenario_json','scenario_overrides_json','ball_mass','ball_speed','fps','duration_sec','slow_motion'):
            value=getattr(args,key)
            if value is not None:command+=['--'+key.replace('_','-'),str(value)]
        subprocess.run(command,check=True)
    data=json.loads(physics.read_text(encoding='utf-8'));s=deepcopy(data['scenario']);c=s['physics']
    s['render'].update(resolution=list(args.resolution),samples=args.samples,engine=args.engine,mode=args.mode)
    if data['scene']!='ball_block_building' or not data['quality']['valid']:raise ValueError('Invalid physics cache')
    object_presence=data.get('object_presence',{'ball':True,**{block['object_id']:True for block in building_blocks(c)}})
    layout=[block for block in building_blocks(c) if object_presence.get(block['object_id'],True)]
    ball_present=object_presence.get('ball',True)
    if set(data['objects'])!={*(['ball'] if ball_present else []),*(block['object_id'] for block in layout)}:
        raise ValueError('Cached object presence differs from the requested stack layout; rerun simulation')
    if any(data['objects'][b['object_id']]['size']!=b['size'] for b in layout):
        raise ValueError('Cached block dimensions differ from current geometry; rerun simulation')
    if physics!=out/'physics_transforms.json':shutil.copy2(physics,out/'physics_transforms.json')
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
    s['render']['device']=configure_renderer(bpy,scene,args)
    configure_color(scene);scene.view_settings.exposure=EXPOSURE
    scene.render.resolution_x,scene.render.resolution_y=args.resolution;scene.render.resolution_percentage=100
    scene.render.fps=data['playback_fps'];scene.frame_start=1;scene.frame_end=data['frame_end']
    # Half-frame shutter, as a phone films at 24 fps. Persistent data must stay
    # off with motion blur: in Blender 4.3 the pair makes a body that has come
    # to rest vanish from every later frame rendered in the same session.
    scene.render.use_motion_blur=True;scene.render.motion_blur_shutter=.5
    scene.render.use_persistent_data=False
    room,props=build_room(bpy,c)
    s['render']['environment_theme']=ENVIRONMENT_THEME
    objects={'ball':make_ball(bpy,c['ball_radius'])} if ball_present else {}
    for block in layout:objects[block['object_id']]=make_block(bpy,block['object_id'],block['size'])
    for frame in data['frames']:
        for key,obj in objects.items():
            state=frame[key];obj.location=state['location'];obj.rotation_mode='QUATERNION';q=state['quaternion_xyzw'];obj.rotation_quaternion=(q[3],q[0],q[1],q[2])
            obj.keyframe_insert('location',frame=frame['frame_index']);obj.keyframe_insert('rotation_quaternion',frame=frame['frame_index'])
    for obj in objects.values():
        for curve in obj.animation_data.action.fcurves:
            for key in curve.keyframe_points:key.interpolation='LINEAR'
    # Props are not simulated: no moving body may come within 2 cm of one in
    # any frame of this take (bounding spheres against the props' boxes).
    radius={'ball':c['ball_radius'],**{b['object_id']:.5*math.sqrt(sum(v*v for v in b['size'])) for b in layout}}
    samples=[(Vector(f[key]['location']),radius[key]) for f in data['frames'] for key in objects if f['presence'].get(key,True)]
    clearance=check_clearance(props,samples)
    camera_cfg=s['camera'];bpy.ops.object.camera_add(location=camera_cfg['location']);camera=bpy.context.object;camera.data.lens=camera_cfg['lens_mm']
    camera.rotation_euler=(Vector(camera_cfg['target'])-camera.location).to_track_quat('-Z','Y').to_euler();scene.camera=camera
    focus=Vector(building_blocks(c)[0]['location'])
    camera.data.dof.use_dof=True;camera.data.dof.focus_distance=(focus-camera.location).length;camera.data.dof.aperture_fstop=F_STOP
    bpy.context.view_layer.update();camera_matrix=[list(row) for row in camera.matrix_world]
    s['room']=dict(description='Joinery workshop: the simulated bench drawn on its collision boxes with a laminated ash top, '
        'concrete floor on the ground plane z = 0, whitewashed brick walls, a steel-framed back window onto farmland, '
        'low morning sun through an east window outside the frame, Poly Haven CC0 tools and furniture',
        room_lines=room['room_lines'],ceiling_z=room['ceiling_z'],windows=room['windows'],daylight=room['daylight'],
        props=room['props'],clearance_m=clearance,motion_blur_shutter=scene.render.motion_blur_shutter,
        exposure=EXPOSURE,aperture_fstop=F_STOP)
    # Ground-truth fields of the rigid-scene layout; slow-motion metadata is additive.
    gt=dict(schema_version=1,scene=data['scene'],fps=scene.render.fps,frame_start=1,frame_end=data['frame_end'],
        physics={key:value for key,value in data.items() if key!='frames'},scenario=s,object_presence=object_presence,
        objects={key:dict(meta,object_name=objects[key].name) for key,meta in data['objects'].items()},
        camera=dict(object_name=camera.name,lens_mm=camera.data.lens,sensor_width_mm=camera.data.sensor_width,resolution=list(args.resolution)),
        sample_fps=data['sample_fps'],slow_motion=data['slow_motion'],physical_duration_sec=data['physical_duration_sec'],playback_duration_sec=data['playback_duration_sec'],
        frames=[dict(frame,camera_matrix_world=camera_matrix) for frame in data['frames']])
    (out/'ground_truth_transforms.json').write_text(json.dumps(gt,indent=2,ensure_ascii=False),encoding='utf-8')
    (out/'scenario_metadata.json').write_text(json.dumps(s,indent=2,ensure_ascii=False),encoding='utf-8')
    # 0.75 s after the first contact the pile has visibly separated; a shorter
    # offset lands on the frame where the upper block still overlaps the base.
    time=data['quality']['events'].get('first_block_impact_sec',.3)+.75
    preview=args.preview_frame or min(scene.frame_end,round(time*data['sample_fps'])+1)
    if not 1<=preview<=scene.frame_end:raise ValueError('Preview frame outside cached trajectory')
    max_error=0
    for index in range(1,scene.frame_end+1):
        scene.frame_set(index);bpy.context.view_layer.update()
        for key,obj in objects.items():
            expected=data['frames'][index-1][key]['matrix_world']
            max_error=max(max_error,max(abs(obj.matrix_world[i][j]-expected[i][j]) for i in range(4) for j in range(4)))
    if max_error>1e-5:raise RuntimeError('Blender replay differs from simulated rigid poses')
    # Nothing that is not simulated may hide a moving body from the camera.
    rays=check_sightlines(scene,camera,objects,list(range(1,scene.frame_end+1)),props.objects())
    (out/'render_validation.json').write_text(json.dumps(dict(checked_frames=scene.frame_end,objects_checked=len(objects),max_matrix_error=max_error,
        prop_clearance_m=clearance,sightline_rays=rays,physics_changed=False)),encoding='utf-8')
    scene.frame_set(preview)
    prepare_eevee(bpy,scene,[*objects.values()])
    bpy.ops.file.pack_all()
    scene.render.image_settings.file_format='PNG'
    if args.mode=='sampled':
        if not 2<=args.frame_count<=scene.frame_end:raise ValueError('Frame count must be between 2 and trajectory length')
        indices=[1+round(i*(scene.frame_end-1)/(args.frame_count-1)) for i in range(args.frame_count)]
        for index in indices:
            scene.frame_set(index);scene.render.filepath=str(out/f'frame_{index:04d}.png');bpy.ops.render.render(write_still=True)
        (out/'sampled_frames.json').write_text(json.dumps(dict(frame_indices=indices,frame_end=scene.frame_end)),encoding='utf-8')
    else:
        scene.render.filepath=str(out/'preview.png');bpy.ops.render.render(write_still=True)
    if args.mode=='animation':
        scene.render.image_settings.file_format='FFMPEG';scene.render.ffmpeg.format='MPEG4';scene.render.ffmpeg.codec='H264';scene.render.ffmpeg.constant_rate_factor='HIGH'
        scene.render.filepath=str(out/'ball_block_building.mp4');scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'ball_block_building.blend'))
    if args.mode=='animation':
        bpy.ops.render.render(animation=True);shutil.copy2(out/'ball_block_building.mp4',out/'video.mp4')

def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--physics-json',type=Path);p.add_argument('--physics-python',type=Path)
    p.add_argument('--scenario-json',type=Path);p.add_argument('--scenario-overrides-json',type=Path)
    p.add_argument('--ball-mass',type=float);p.add_argument('--ball-speed',type=float);p.add_argument('--fps',type=int);p.add_argument('--duration-sec',type=float);p.add_argument('--slow-motion',type=int,choices=(1,2,4,8))
    p.add_argument('--engine',choices=('eevee','cycles'),default='cycles');p.add_argument('--device',choices=('auto','cpu'),default='auto');p.add_argument('--samples',type=int,default=32);p.add_argument('--resolution',type=int,nargs=2,default=[960,540]);p.add_argument('--mode',choices=('preview','animation','sampled'),default='animation');p.add_argument('--preview-frame',type=int);p.add_argument('--frame-count',type=int,default=6)
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:];render(parse_render_args(p, argv))

if __name__=='__main__':run_renderer(main, 'ball_block_building')
