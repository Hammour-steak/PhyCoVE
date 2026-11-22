"""Replay one native case of football_goal_net into the packed stadium scene and render it.

Blender 4.3.2, from the repository root:

    <blender> -b --factory-startup --disable-autoexec --python-exit-code 1 \
        --python scripts/rigid_elastic/football_goal_net/appearance/render.py -- \
        --case source --out renders/football_goal_net/<folder>/source \
        [--frames 1-96 | --frames 1,12,48] [--device OPTIX|CUDA|CPU] [--threads N] [--samples N] [--look realism|base]

Inputs are the registered assets of group scenes/football_goal_net (assets.json):
prepared_scene.blend (packed stadium/goal scene), native/<case>/ (120 Hz native solver state with its
render gate, physics report and sampled geometry audit; a timed edit's merged solve is given with
--cache-dir), model/model.npz (net strand model),
world/source.npz (frozen collision world), grass_patches/ and orlando_goalfree.exr.

The scene build is the one every accepted video used: the layout corrections of the packed scene, the net drawn
from the solver's own strand centrelines (one shape key per 120 Hz state), the ball keyed with the
solver pose, the turf bound to the solver's turf compression samples, the fixed pitchside camera
(appearance/camera.py) and the stadium photograph re-projected behind the goal. Frame k of the
video shows the native state with index 5*(k-1) (t = (k-1)/24 s); every rendered frame re-checks the
ball, net and grass bindings against the cache. The current look (appearance/realism.py) is applied
after the build; --look base renders the scene without it.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import platform
import socket
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[2]
sys.path[:0] = [str(HERE), str(SCRIPTS)]
from pcve_assets import asset  # noqa: E402

PREFIX = "scenes/football_goal_net"
SCENE_SHA256 = "f8fc20a2ba58f62ba69660eebeb80c943cf3b48fa93c4df834220e3c389fd357"
CASES = ("source", "young_tenth", "mass_double", "speed_half", "remove_net")
# Timed edits (edit_vocab.TIMED_DSL) replay their merged native solve (physics/solve_timed.py), given with --cache-dir.
TIMED_CASES = ("mass_double_at_frame_8",)
FPS, NATIVE_FPS, FRAMES = 24, 120, 96


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def load(p, name):
    s = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def frame_list(text):
    if "-" in text and "," not in text:
        first, last = (int(v) for v in text.split("-"))
        frames = list(range(first, last + 1))
    else:
        frames = sorted({int(v) for v in text.split(",")})
    if not frames or frames[0] < 1 or frames[-1] > FRAMES:
        raise ValueError("Frames must lie in 1-96")
    return frames


def setup_render(bpy, scene, a):
    """Cycles settings shared by every frame of a case (device type, samples and seed fixed)."""
    scene.render.engine = "CYCLES"
    devices = []
    if a.device == "CPU":
        scene.cycles.device = "CPU"
    else:
        preferences = bpy.context.preferences.addons["cycles"].preferences
        preferences.compute_device_type = a.device
        preferences.get_devices()
        for device in preferences.devices:
            device.use = device.type == a.device
            if device.use:
                devices.append(device.name)
        if not devices:
            raise RuntimeError(f"No {a.device} device visible")
        scene.cycles.device = "GPU"
    if a.threads:
        scene.render.threads_mode = "FIXED"
        scene.render.threads = a.threads
    scene.cycles.samples = a.samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = .012
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.seed = 260026
    scene.cycles.max_bounces = 10
    scene.cycles.transparent_max_bounces = 8
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    # The scene timeline is the native 120 Hz clock; a 0.5 shutter is 1/240 s.
    scene.render.fps, scene.render.fps_base = NATIVE_FPS, 1
    scene.render.frame_map_old = scene.render.frame_map_new = 100
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = .5
    # Blender 4.3 drops objects that come to rest when persistent data is on together with motion blur.
    scene.render.use_persistent_data = False
    return devices or ["CPU"]


def build(bpy, case, cache_dir, model_dir):
    from mathutils import Quaternion
    if (cache_dir/'timed_edit.json').is_file():
        # Timed edit: the merged solve is bound by its own receipt (physics/solve_timed.py); same model.
        receipt = json.loads((cache_dir/'timed_edit.json').read_text())
        assert receipt['case'] == case and receipt['simulation_sha256'] == sha(cache_dir/'simulation.npz')
        # The accepted render gates record the audited soil field; here the same check is made directly:
        # every turf control the solver activated lies inside the common visual soil bounds.
        bounds = json.loads((HERE/'visual_layout.json').read_text())['common_soil_bounds_xy_m']
        with np.load(cache_dir/'simulation.npz', allow_pickle=False) as z:
            xy = z['turf_control_xy']
        assert len(xy) == 0 or (xy[:, 0].min() >= bounds[0] and xy[:, 0].max() <= bounds[1]
                                and xy[:, 1].min() >= bounds[2] and xy[:, 1].max() <= bounds[3]), 'turf contact outside the soil field'
        proof = {'simulation_sha256': receipt['simulation_sha256'], 'model_sha256': sha(model_dir/'model.npz'),
                 'common_soil_bounds_xy_m': bounds}
        geometry_audit = None  # no sampled-geometry audit for a timed merge; the receipt binds the cache
    else:
        proof = json.loads((cache_dir/'render_gate.json').read_text())
        assert proof['render_candidate_allowed'] and not proof['accepted_benchmark_GT']
        geometry_audit = json.loads((cache_dir/'sampled_geometry_audit.json').read_text())
        assert geometry_audit['simulation_sha256'] == proof['simulation_sha256']
    cache_sha = sha(cache_dir/'simulation.npz')
    assert cache_sha == proof['simulation_sha256'] and sha(model_dir/'model.npz') == proof['model_sha256']
    with np.load(cache_dir/'simulation.npz', allow_pickle=False) as z:
        cache = {k: z[k].copy() for k in z.files}
    with np.load(model_dir/'model.npz', allow_pickle=False) as z:
        model = {k: z[k].copy() for k in z.files}
    report = json.loads((cache_dir/'physics_report.json').read_text())
    assert report['complete_requested_time']
    net_present = bool(cache['net_present'])
    board_present = bool(cache['training_rebound_board_present'])
    assert report['seconds_completed'] == float(cache['times'][-1]) == 4. and report['physics_identity']['native_fps'] == NATIVE_FPS
    scene_file = asset(PREFIX + "/prepared_scene.blend")
    assert sha(scene_file) == SCENE_SHA256
    look = load(HERE/'look_base.py', 'football_look_base')
    surfaces = load(HERE/'surfaces.py', 'football_surfaces')
    turf = load(HERE/'turf.py', 'football_turf')
    bpy.ops.wm.open_mainfile(filepath=str(scene_file),load_ui=False);scene=bpy.context.scene
    if True:  # the layout reconstruction of the packed scene used by every accepted render
        prototypes=set()
        for group in bpy.data.node_groups:
            for node in group.nodes:
                if node.bl_idname=='GeometryNodeCollectionInfo':
                    collection=node.inputs['Collection'].default_value
                    if collection:prototypes.update(collection.all_objects)
        for obj in list(scene.objects):
            chain=[];parent=obj
            while parent:chain.append(parent.name);parent=parent.parent
            if obj in prototypes or obj.name.startswith('visible net =') or 'Football rigid transform' in chain or obj.type not in {'MESH','CURVE','FONT'}:continue
            low=obj.name.lower()
            if 'grass' in low or 'pitch and grass' in low or (obj.type=='MESH' and obj.data.attributes.get('tuft_variant')):continue
            if obj.name.startswith(('shared 110mm','coated welded','flush goal','recessed stainless','closed nylon')):continue
            delta=.65 if 'stanchion' in low or 'support wire' in low else 2.;matrix=obj.matrix_world.copy();matrix.translation.y+=delta
            if obj.get('static_instances'):
                assert obj.type=='MESH' and np.allclose(np.array(obj.matrix_world),np.eye(4),atol=1e-8)
                obj.data=obj.data.copy();obj.data.transform(matrix);obj.data.update()
            else:obj.matrix_world=matrix
            if 'support wire' in low:
                for spline in obj.data.splines:spline.points[-1].co.z+=.035
    # The blanket background shift also moves the bottom frame.
    # Correct this COMMON baseline so the real rails match physical anchors.
    rail_corrections=[]
    for obj in scene.objects:
        if not obj.name.startswith(('anchored rear ground rail','anchored side ground rail')):continue
        assert obj.type=='MESH';obj.data=obj.data.copy();M=np.array(obj.matrix_world);inverse=np.linalg.inv(M)
        co=np.empty((len(obj.data.vertices),3),np.float32);obj.data.vertices.foreach_get('co',co.ravel());world=co@M[:3,:3].T+M[:3,3];before=[world.min(axis=0).tolist(),world.max(axis=0).tolist()]
        if obj.name.startswith('anchored rear'):world[:,1]-=1.35
        else:world[:,1]=(world[:,1]-2.)*(2.5/1.85)
        # Full homogeneous inverse, valid even when the original pipe is rotated.
        local=world@inverse[:3,:3].T+inverse[:3,3]
        obj.data.vertices.foreach_set('co',local.astype(np.float32).ravel());obj.data.update()
        rail_corrections.append({'object':obj.name,'old_world_bounds_m':before,'new_world_bounds_m':[world.min(axis=0).tolist(),world.max(axis=0).tolist()]})
    assert len(rail_corrections)==3
    # One common physical installation for source and every independent edit.
    mount_records=[]
    mount_prefixes=('anchored rear ground rail','anchored side ground rail','40mm dark closed-cell stanchion padding','closed nylon clip','shared FIFA-offset steel stanchion','stanchion padding retaining strap','support wire to fixed rear corner')
    for obj in scene.objects:
        if obj.name.startswith(mount_prefixes):
            matrix=obj.matrix_world.copy();matrix.translation.y+=.065;obj.matrix_world=matrix;mount_records.append(obj.name)
    board_builder=load(HERE/'rebound_board.py','football_rebound_board')
    board_receipt=board_builder.build_from_frozen_preset(HERE/'training_rebound_board.preset.json',present=board_present)
    old=[o for o in scene.objects if o.name.startswith('visible net =')];assert len(old)==1
    nylon=next(n.inputs['Material'].default_value for m in old[0].modifiers if m.type=='NODES' for n in m.node_group.nodes if n.bl_idname=='GeometryNodeSetMaterial')
    bpy.data.objects.remove(old[0],do_unlink=True)
    positions=cache['net_positions'];times=cache['times'];net=None;mapping=np.empty(0,np.int32);radii=np.empty(0,np.float32)
    if net_present:
        ids=model['parent_ids'];edges=model['edges'];chains=[[] for _ in model['parent_edges']]
        for i,parent in enumerate(ids):chains[int(parent)].append(i)
        mapping=[];mesh_edges=[];radii=[]
        for strand in chains:
            chain=[int(edges[strand[0],0])]+[int(edges[i,1]) for i in strand];offset=len(mapping);mapping.extend(chain)
            mesh_edges.extend((offset+i,offset+i+1) for i in range(len(chain)-1));radii.extend([float(model['diameters'][strand[0]])*.5]*len(chain))
        mapping=np.asarray(mapping,np.int32);radii=np.asarray(radii,np.float32);positions=cache['net_positions'];times=cache['times']
        assert np.array_equal(times,cache['net_times']) and positions.shape[0]==len(times)
        mesh=bpy.data.meshes.new('actual material-segment centreline mesh');mesh.from_pydata(positions[0,mapping].tolist(),mesh_edges,[])
        mesh.attributes.new(name='cord_radius_m',type='FLOAT',domain='POINT').data.foreach_set('value',radii)
        net=bpy.data.objects.new('visible net = physical material rods',mesh);scene.collection.objects.link(net);net['physical_cache_sha256']=cache_sha
        net.shape_key_add(name='Basis')
        for i,t in enumerate(times):
            frame=1+float(t)*120;key=net.shape_key_add(name=f'PhysicalNet_{i:04d}');key.data.foreach_set('co',positions[i,mapping].ravel())
            for f,value in ((frame-1,0.),(frame,1.),(frame+1,0.)):key.value=value;key.keyframe_insert('value',frame=f)
        group=bpy.data.node_groups.new('true4mm material rods and6mm supports','GeometryNodeTree')
        group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry');group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
        nodes,links=group.nodes,group.links;inp=nodes.new('NodeGroupInput');output=nodes.new('NodeGroupOutput');curve=nodes.new('GeometryNodeMeshToCurve');links.new(inp.outputs['Geometry'],curve.inputs['Mesh'])
        attr=nodes.new('GeometryNodeInputNamedAttribute');attr.data_type='FLOAT';attr.inputs['Name'].default_value='cord_radius_m'
        radius=nodes.new('GeometryNodeSetCurveRadius');links.new(curve.outputs['Curve'],radius.inputs['Curve']);links.new(attr.outputs['Attribute'],radius.inputs['Radius'])
        circle=nodes.new('GeometryNodeCurvePrimitiveCircle');circle.inputs['Resolution'].default_value=8;circle.inputs['Radius'].default_value=1.
        tubes=nodes.new('GeometryNodeCurveToMesh');links.new(radius.outputs['Curve'],tubes.inputs['Curve']);links.new(circle.outputs['Curve'],tubes.inputs['Profile Curve']);tubes.inputs['Fill Caps'].default_value=True
        mat=nodes.new('GeometryNodeSetMaterial');mat.inputs['Material'].default_value=nylon;links.new(tubes.outputs['Mesh'],mat.inputs['Geometry']);links.new(mat.outputs['Geometry'],output.inputs['Geometry'])
        modifier=net.modifiers.new('Actual rod radii and finite material centreline','NODES');modifier.node_group=group
    ball=bpy.data.objects['Football rigid transform'];ball.animation_data_clear();ball.rotation_mode='QUATERNION';previous=None
    for t,pos,quat in zip(times,cache['ball_positions'],cache['ball_orientations']):
        value=quat.copy()
        if previous is not None and previous@value<0:value=-value
        previous=value;ball.location=pos;ball.rotation_quaternion=Quaternion(tuple(value));ball.keyframe_insert('location',frame=1+float(t)*120);ball.keyframe_insert('rotation_quaternion',frame=1+float(t)*120)
    for action in ([ball.animation_data.action]+([net.data.shape_keys.animation_data.action] if net_present else [])):
        for fcurve in action.fcurves:
            for key in fcurve.keyframe_points:key.interpolation='LINEAR'
    scene.frame_set(1);bpy.context.view_layer.update()
    look_receipt = look.enhance_loaded_scene(expect_net_present=net_present)
    surface_receipt = surfaces.apply_common_surfaces(look=look, expect_net_present=net_present, panel_mode='unchanged')
    turf_receipt = turf.apply_common_turf(look=look, expect_net_present=net_present)
    profile = load(HERE/'visual_profile.py', 'football_visual_profile')
    profile_receipt = profile.apply(bpy, turf, ball, proof)
    camera_module = load(HERE/'camera.py', 'football_camera')
    cam, camera_receipt = camera_module.apply(bpy, scene, 'wide', float(times[-1]))
    eye, target, _ = camera_module.state(0., 'wide')
    grass = load(HERE/'grass_binding.py', 'football_grass_binding')
    grass_receipt = grass.bind(bpy, turf, cache, eye, target)
    profile_receipt['grass_soil_binding'] = profile.finalize_grass(bpy, ball)
    removed_static = []
    for obj in tuple(scene.objects):
        if obj.get('static_unaffected_turf', False):
            removed_static.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    patches = load(HERE/'grass_patches.py', 'football_grass_patches')
    patch_receipt = patches.apply(bpy, asset(PREFIX + "/grass_patches"))
    patch_receipt['replaced_generated_static_root_objects'] = removed_static
    backdrop = load(HERE/'backdrop.py', 'football_backdrop')
    audience_receipt = backdrop.apply(bpy, scene, eye, {'world': asset(PREFIX + "/world/source.npz"),
                                                        'hdri': asset(PREFIX + "/orlando_goalfree.exr")})
    actual_soil = profile_receipt['soil']['common_bounds_xy_m']
    audited_soil = proof['common_soil_bounds_xy_m']
    assert (actual_soil[0] <= audited_soil[0] and actual_soil[1] >= audited_soil[1]
            and actual_soil[2] <= audited_soil[2] and actual_soil[3] >= audited_soil[3])
    return dict(scene=scene, cache=cache, cache_sha=cache_sha, report=report, times=times, ball=ball, net=net,
                mesh=mesh if net_present else None, modifier=modifier if net_present else None, mapping=mapping,
                radii=radii, positions=positions, net_present=net_present, board_present=board_present, camera=cam,
                eye=eye, target=target, proof=proof, geometry_audit=geometry_audit, scene_file=scene_file,
                receipts={'camera': camera_receipt, 'common_bottom_frame_corrections': rail_corrections,
                          'common_mount_offset_y_m': .065, 'common_mount_owners': len(mount_records),
                          'added_board': board_receipt,
                          'physical_grass_binding': grass_receipt.get('source'),
                          'photographic_backdrop': {k: audience_receipt.get(k) for k in ('hdri_sha256', 'layout', 'lighting')}})


def check_bindings(bpy, s, index):
    """Ball, net and grass carriers must sit exactly on the native state of this frame."""
    cache, ball = s['cache'], s['ball']
    position_error = float(np.linalg.norm(np.array(ball.matrix_world.translation) - cache['ball_positions'][index]))
    assert position_error < 2e-5, position_error
    net_error = 0.
    if s['net_present']:
        s['modifier'].show_viewport = False
        bpy.context.view_layer.update()
        evaluated = s['net'].evaluated_get(bpy.context.evaluated_depsgraph_get())
        view = evaluated.to_mesh()
        actual = np.empty((len(s['mesh'].vertices), 3), np.float32)
        view.vertices.foreach_get('co', actual.ravel())
        evaluated.to_mesh_clear()
        net_error = float(np.max(np.linalg.norm(actual - s['positions'][index, s['mapping']], axis=1)))
        assert net_error < 2e-6, net_error
        s['modifier'].show_viewport = True
    control = bpy.data.objects['nonrender physical grass samples']
    evaluated_control = control.evaluated_get(bpy.context.evaluated_depsgraph_get())
    control_mesh = evaluated_control.to_mesh()
    actual_control = np.empty((len(control_mesh.vertices), 3), np.float32)
    control_mesh.vertices.foreach_get('co', actual_control.ravel())
    evaluated_control.to_mesh_clear()
    expected_scale = cache['turf_control_scale'][index] if cache['turf_control_scale'].shape[1] else np.ones(1)
    grass_error = float(np.max(np.abs(actual_control[:, 2] - .024 * expected_scale)))
    assert grass_error < 2e-7, grass_error
    bpy.context.view_layer.update()
    return position_error, net_error, grass_error


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--case', choices=CASES + TIMED_CASES, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--cache-dir', type=Path, help='native case folder (default: assets native/<case>; required for a timed case)')
    p.add_argument('--frames', default='1-96', help="'a-b' or a comma list (1-based video frames)")
    p.add_argument('--device', choices=('OPTIX', 'CUDA', 'CPU'), default='OPTIX')
    p.add_argument('--threads', type=int, default=0)
    p.add_argument('--samples', type=int, default=256)
    p.add_argument('--look', choices=('realism', 'base'), default='realism')
    p.add_argument('--audit-only', action='store_true', help='build and check every requested frame, render nothing')
    p.add_argument('--without-ball', action='store_true',
                   help='DELETE ball: the football is hidden from every ray (net, turf and bindings stay those of the cache)')
    a = p.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    import bpy
    start = time.time()
    frames = frame_list(a.frames)
    out = a.out.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    for k in frames:
        if (out / f'frame_{k:04d}.png').exists():
            raise FileExistsError(out / f'frame_{k:04d}.png')
    s = build(bpy, a.case, a.cache_dir.resolve() if a.cache_dir else asset(PREFIX + "/native/" + a.case), asset(PREFIX + "/model"))
    scene = s['scene']
    devices = [] if a.audit_only else setup_render(bpy, scene, a)
    look_record = None
    if a.look == 'realism':
        realism = load(HERE/'realism.py', 'football_realism')
        look_record = realism.apply(bpy, scene, s)
    scene.frame_end = 1 + round(float(s['times'][-1]) * NATIVE_FPS)
    if a.without_ball:
        for obj in [s['ball'], *s['ball'].children_recursive]:
            obj.hide_render = True
            obj.hide_viewport = True
    ledger = []
    for k in frames:
        index = (k - 1) * (NATIVE_FPS // FPS)
        scene.frame_set(1 + index)
        bpy.context.view_layer.update()
        position_error, net_error, grass_error = check_bindings(bpy, s, index)
        name = None
        if not a.audit_only:
            name = f'frame_{k:04d}.png'
            scene.render.filepath = str(out / name)
            bpy.ops.render.render(write_still=True)
        ledger.append({'frame': k, 'file': name, 'time_s': float(s['times'][index]), 'cache_index': index,
                       'ball_position_error_m': position_error, 'net_max_binding_error_m': net_error,
                       'grass_height_binding_error_m': grass_error, 'sha256': None if name is None else sha(out / name)})
        print(json.dumps({'frame': k, 'time_s': ledger[-1]['time_s'], 'sha256': ledger[-1]['sha256']}), flush=True)
    data = scene.camera.data
    record = {
        'case': a.case, 'frames': ledger, 'audit_only': a.audit_only,
        'host': socket.gethostname(), 'platform': platform.platform(), 'blender': bpy.app.version_string,
        'device': a.device, 'devices': devices, 'threads': a.threads,
        'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
        'samples': a.samples, 'denoiser': 'OPENIMAGEDENOISE', 'adaptive_threshold': scene.cycles.adaptive_threshold,
        'seed': scene.cycles.seed, 'resolution': [1280, 720], 'fps': FPS, 'native_fps': NATIVE_FPS,
        'shutter_seconds': scene.render.motion_blur_shutter / NATIVE_FPS, 'motion_blur': scene.render.use_motion_blur,
        'persistent_data': scene.render.use_persistent_data,
        'view_transform': [scene.view_settings.view_transform, scene.view_settings.look, scene.view_settings.exposure],
        'camera': {'matrix_world': [list(r) for r in scene.camera.matrix_world], 'lens_mm': data.lens,
                   'sensor_width_mm': data.sensor_width, 'shift': [data.shift_x, data.shift_y],
                   'f_stop': data.dof.aperture_fstop, 'focus_distance_m': data.dof.focus_distance},
        'cache_sha256': s['cache_sha'], 'scene_sha256': SCENE_SHA256, 'net_present': s['net_present'],
        'training_rebound_board_present': s['board_present'], 'round_rope_radii_m': np.unique(s['radii']).tolist(),
        'net_mapping_sha256': hashlib.sha256(np.asarray(s['mapping']).tobytes()).hexdigest(),
        'look': a.look, 'look_record': look_record, **({'without_ball': True} if a.without_ball else {}),
        'build': s['receipts'], 'physics_changed': False, 'elapsed_s': time.time() - start}
    tag = f'{frames[0]:04d}-{frames[-1]:04d}' if ',' not in a.frames else 'f' + '_'.join(str(k) for k in frames)
    (out / f'render_report_{tag}.json').write_text(json.dumps(record, indent=1, allow_nan=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
