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




from pcve_blender_compat import (eevee_engine, set_eevee_property, set_color_property)
from pathlib import Path
import argparse,json,sys,subprocess,shutil
from copy import deepcopy
from scene_config import defaults
from look_u_track_ball import build_room,box,configure_lighting,ENVIRONMENT_THEME,scan_material,turned_walnut,kraft_board
from visual_details import track_bed,continuous_rails,track_stand,carton_details,check_props
from pcve_scene_runtime import python_for
ROOT = _PCVE_PROJECT_ROOT
from pcve_scene_runtime import parse_render_args, run_renderer

def render(args):
    import bpy
    from mathutils import Vector
    out=args.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    physics=args.physics_json.resolve() if args.physics_json else out/'physics_transforms.json'
    if not args.physics_json:
        command=[str(args.physics_python or python_for('physics')),str(Path(__file__).with_name('simulate_u_track_ball.py')),'--out',str(physics)]
        for name in ('scenario_json','scenario_overrides_json','friction','initial_speed','initial_position','slow_motion','duration_sec','fps'):
            value=getattr(args,name)
            if value is not None:command+=['--'+name.replace('_','-'),str(value)]
        subprocess.run(command,check=True)
    records=json.loads(physics.read_text(encoding='utf-8'));s=deepcopy(records['scenario']);c=s['physics']
    s['render'].update(resolution=list(args.resolution),samples=args.samples,engine=args.engine,mode=args.mode)
    if records['scene']!='u_track_ball' or not records['quality']['valid']:raise ValueError('Invalid scene cache')
    if args.physics_json and any(getattr(args,k) is not None for k in ('scenario_json','scenario_overrides_json','friction','initial_speed','initial_position','slow_motion','duration_sec','fps')):raise ValueError('Physics options cannot modify a cached trajectory; resimulate first')
    if physics!=out/'physics_transforms.json':shutil.copy2(physics,out/'physics_transforms.json')
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
    scene.render.engine=eevee_engine() if args.engine=='eevee' else 'CYCLES'
    if args.engine=='eevee':
        set_eevee_property(scene.eevee, 'taa_render_samples', args.samples);set_eevee_property(scene.eevee, 'use_raytracing', False)
        set_eevee_property(scene.eevee, 'ray_tracing_options.resolution_scale', '2');set_eevee_property(scene.eevee, 'ray_tracing_options.screen_trace_quality', 0.6)
        set_eevee_property(scene.eevee, 'use_gtao', True);set_eevee_property(scene.eevee, 'gtao_distance', 0.2);set_eevee_property(scene.eevee, 'gtao_quality', 1.0)
        set_eevee_property(scene.eevee, 'shadow_ray_count', 1);set_eevee_property(scene.eevee, 'shadow_step_count', 8)
    else:
        scene.cycles.samples=args.samples;scene.cycles.use_denoising=True;scene.cycles.max_bounces=8;scene.cycles.diffuse_bounces=4;scene.cycles.glossy_bounces=4
        scene.cycles.adaptive_threshold=.025;scene.cycles.seed=19
        scene.cycles.device='CPU'
        if args.device=='auto':
            prefs=bpy.context.preferences.addons['cycles'].preferences
            try:
                prefs.compute_device_type='CUDA';prefs.get_devices();available=[dev for dev in prefs.devices if dev.type=='CUDA']
                for dev in prefs.devices:dev.use=(dev.type=='CUDA')
                if available:
                    scene.cycles.device='GPU';scene.cycles.denoiser='OPTIX' if any(dev.type=='OPTIX' for dev in prefs.devices) else 'OPENIMAGEDENOISE'
                    print('[render] CUDA: '+', '.join(dev.name for dev in available),flush=True)
            except Exception as exc:
                scene.cycles.device='CPU';scene.cycles.denoiser='OPENIMAGEDENOISE'
                print('[render] CPU fallback: '+str(exc),flush=True)
        s['render']['device']=scene.cycles.device
    scene.render.resolution_x,scene.render.resolution_y=args.resolution;scene.render.resolution_percentage=100
    # Half-frame shutter motion blur, as a 24 fps camera records a rolling ball.
    # Persistent data stays off: in Blender 4.3, persistent data together with
    # motion blur drops an object that has come to rest from every later frame
    # rendered in the same session (the ball and the carton both settle here).
    scene.render.use_motion_blur=True;scene.render.motion_blur_shutter=.5
    scene.render.use_persistent_data=False
    scene.render.fps=records['playback_fps'];scene.frame_start=1;scene.frame_end=records['frame_end']
    set_color_property(scene.view_settings, 'view_transform', 'AgX');set_color_property(scene.view_settings, 'look', 'AgX - Base Contrast');scene.view_settings.exposure=.35
    shared=build_room(bpy,c);configure_lighting(bpy,scene)
    s['render']['environment_theme']=ENVIRONMENT_THEME
    if args.engine=='eevee':
        for light in bpy.data.lights:
            if hasattr(light,'use_shadow_jitter'):light.use_shadow_jitter=False
        scene.use_nodes=True;nodes=scene.node_tree.nodes;links=scene.node_tree.links;nodes.clear()
        layers=nodes.new('CompositorNodeRLayers');denoise=nodes.new('CompositorNodeDenoise');denoise.use_hdr=True
        composite=nodes.new('CompositorNodeComposite');links.new(layers.outputs['Image'],denoise.inputs['Image']);links.new(denoise.outputs['Image'],composite.inputs['Image'])
    # The trough and the cheeks are the collision geometry (track_mesh and the rail
    # boxes of track_parts); the running surface is charcoal furniture linoleum.
    running=scan_material(bpy,'Charcoal linoleum running surface','linoleum_brown','uv',tint=(.42,.47,.55),saturation=.25,value=.42,rough_range=(.38,.56),normal_strength=.45,specular=.45)
    track_bed(bpy,c,running,shared['ply_face'],shared['ply_edges'])
    continuous_rails(bpy,c,shared['ply_face'],shared['ply_edges'])
    track_stand(bpy,c,shared['ply_face'],shared['ply_edges'])
    bpy.ops.mesh.primitive_uv_sphere_add(segments=96,ring_count=48,radius=c['ball_radius']);ball=bpy.context.object;ball.name='Turned walnut ball'
    ball.data.materials.append(turned_walnut(bpy))
    for poly in ball.data.polygons:poly.use_smooth=True
    target=box(bpy,'Shipping carton',[0,0,0],c['box_size'],kraft_board(bpy),bevel=.0012);carton_details(bpy,target,c)
    # Whole-clip deletions never show the carton; a mid-run removal hides it
    # from the removal frame on, with no fade interpolation.
    box_absent_at=next((f['frame_index'] for f in records['frames'] if not f['box'].get('present',True)),None)
    # A whole-clip ball deletion never shows the ball.
    if not records['frames'][0]['ball'].get('present',True):ball.hide_render=ball.hide_viewport=True
    for frame in records['frames']:
        ball_state=frame['ball']
        if ball_state.get('present',True):
            ball.location=ball_state['location'];ball.rotation_mode='QUATERNION';q=ball_state['quaternion_xyzw'];ball.rotation_quaternion=(q[3],q[0],q[1],q[2])
            ball.keyframe_insert('location',frame=frame['frame_index']);ball.keyframe_insert('rotation_quaternion',frame=frame['frame_index'])
        box_state=frame['box']
        if box_state.get('present',True):
            target.location=box_state['location'];target.rotation_mode='QUATERNION';q=box_state['quaternion_xyzw'];target.rotation_quaternion=(q[3],q[0],q[1],q[2])
            target.keyframe_insert('location',frame=frame['frame_index']);target.keyframe_insert('rotation_quaternion',frame=frame['frame_index'])
    for obj in (ball,target):
        curves=obj.animation_data.action.fcurves if obj.animation_data else []
        for curve in curves:
            for key in curve.keyframe_points:key.interpolation='LINEAR'
    if box_absent_at is not None:
        for obj in [target,*target.children_recursive]:
            for prop in ('hide_render','hide_viewport'):
                setattr(obj,prop,False);obj.keyframe_insert(prop,frame=max(1,box_absent_at-1))
                setattr(obj,prop,True);obj.keyframe_insert(prop,frame=box_absent_at)
            for curve in obj.animation_data.action.fcurves:
                if curve.data_path in ('hide_render','hide_viewport'):
                    for point in curve.keyframe_points:point.interpolation='CONSTANT'
    camera_cfg=s.get('camera',defaults()['camera'])
    bpy.ops.object.camera_add(location=camera_cfg['location']);camera=bpy.context.object;camera.data.lens=camera_cfg['lens_mm'];camera.rotation_euler=(Vector(camera_cfg['target'])-camera.location).to_track_quat('-Z','Y').to_euler();scene.camera=camera
    bpy.context.view_layer.update()
    # Visual-only props must stay 2 cm clear of the ball and the carton in every
    # frame and never stand between them and the camera; raises otherwise.
    clearance=check_props(bpy,scene,camera,records,c)
    print('[render] prop clearance: '+json.dumps(clearance),flush=True)
    gt=deepcopy(records);gt['scenario']=s;gt['fps']=scene.render.fps;gt['sample_fps']=records['sample_fps'];gt['duration_sec']=records['playback_duration_sec'];gt['camera']=dict(camera_cfg,resolution=args.resolution,matrix_world=[list(row) for row in camera.matrix_world])
    gt['physics']={key:value for key,value in records.items() if key!='frames'}
    gt['objects']={key:dict(value,object_name={'ball':ball,'box':target}[key].name) for key,value in records['objects'].items()}
    gt['camera'].update(object_name=camera.name,sensor_width_mm=camera.data.sensor_width)
    gt['frames']=[dict(frame,camera_matrix_world=[list(row) for row in camera.matrix_world]) for frame in records['frames']]
    (out/'ground_truth_transforms.json').write_text(json.dumps(gt,indent=2,ensure_ascii=False),encoding='utf-8')
    (out/'scenario_metadata.json').write_text(json.dumps(s,indent=2),encoding='utf-8')
    # The preview shows the measured impact, or nearest approach for a non-impact edit.
    time=records['quality']['events'].get('box_impact_sec',.7)
    frame=args.preview_frame or min(scene.frame_end,round(time*records['sample_fps'])+1)
    if not 1<=frame<=scene.frame_end:raise ValueError('Preview frame outside cached trajectory')
    checked=sorted({1,frame,scene.frame_end});error=0
    for index in checked:
        scene.frame_set(index);bpy.context.view_layer.update()
        for obj,key in ((ball,'ball'),(target,'box')):
            state=records['frames'][index-1][key]
            if not state.get('present',True):
                if obj.hide_render:continue
                raise RuntimeError(f'Render shows {key} at frame {index} but the physics removed it')
            expected=state['matrix_world']
            error=max(error,max(abs(obj.matrix_world[i][j]-expected[i][j]) for i in range(4) for j in range(4)))
    if error>1e-5:raise RuntimeError('Rigid replay mismatch')
    (out/'render_validation.json').write_text(json.dumps(dict(checked_frames=checked,max_matrix_error=error,physics_changed=False,prop_clearance=clearance)),encoding='utf-8')
    scene.frame_set(frame)
    if args.engine=='eevee' and bpy.app.version>=(4,2,0):
        probe_data=bpy.data.lightprobes.new('Static room irradiance','VOLUME');probe_data.resolution_x=6;probe_data.resolution_y=4;probe_data.resolution_z=4;probe_data.bake_samples=32;probe_data.surfel_density=10
        probe=bpy.data.objects.new('Static room irradiance',probe_data);scene.collection.objects.link(probe);probe.location=[.3,.4,1.4];probe.scale=[3.2,2.4,1.7]
        moving=[ball,target,*target.children];previous=[obj.hide_render for obj in moving]
        try:
            for obj in moving:obj.hide_render=True
            bpy.context.view_layer.objects.active=probe;probe.select_set(True)
            print('[render] Baking static room indirect light',flush=True);bpy.ops.object.lightprobe_cache_bake(subset='ALL')
            print('[render] Indirect light bake complete',flush=True)
        finally:
            for obj,hidden in zip(moving,previous):obj.hide_render=hidden
    # Packed textures keep the saved scene portable without external absolute paths.
    bpy.ops.file.pack_all()
    scene.render.image_settings.file_format='PNG';scene.render.filepath=str(out/'preview.png');bpy.ops.render.render(write_still=True)
    if args.mode=='animation':
        scene.render.image_settings.file_format='FFMPEG';scene.render.ffmpeg.format='MPEG4';scene.render.ffmpeg.codec='H264';scene.render.ffmpeg.constant_rate_factor='HIGH';scene.render.filepath=str(out/'video.mp4');scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'u_track_ball.blend'))
    if args.mode=='animation':bpy.ops.render.render(animation=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out-dir',type=Path,required=True);parser.add_argument('--physics-json',type=Path);parser.add_argument('--physics-python',type=Path)
    parser.add_argument('--scenario-json',type=Path);parser.add_argument('--scenario-overrides-json',type=Path)
    for name in ('friction','initial-speed','initial-position','duration-sec'):parser.add_argument('--'+name,type=float)
    parser.add_argument('--slow-motion',type=int,choices=(1,2,4,8));parser.add_argument('--engine',choices=('eevee','cycles'),default='cycles');parser.add_argument('--device',choices=('auto','cpu'),default='auto');parser.add_argument('--samples',type=int,default=32);parser.add_argument('--resolution',type=int,nargs=2,default=[960,540]);parser.add_argument('--mode',choices=('preview','animation'),default='animation');parser.add_argument('--preview-frame',type=int)
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:];render(parse_render_args(parser, argv))

if __name__=='__main__':run_renderer(main, 'u_track_ball')
