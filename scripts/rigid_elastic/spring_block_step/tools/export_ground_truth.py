"""Per-frame ground truth of one delivered case (runs inside Blender).

    blender -b <render>/<case>/scene.blend --factory-startup --python tools/export_ground_truth.py -- \
        --case source --native assets/scenes/spring_block_step/native_states/source --out <suite>/cases/source/ground_truth_transforms.json
    # a video rendered without a saved scene.blend: rebuild its fixed camera from the render record
    blender -b --factory-startup --python tools/export_ground_truth.py -- --case source --native ... --out ... \
        --camera-location 0.58 -1.64 0.38 --camera-target 0.17 0 0.085 --lens 58 --sensor-width 36

Every object state comes from the native PyBullet states of the case
(`states.npz`: 96 samples at t=i/24 s, the frames the video shows; positions,
wxyz quaternions and world-frame [angular, linear] velocities) and its
`resolved_physics.json`. The camera (pose, lens, sensor, shift, resolution) is
read from the scene.blend the case was rendered from, or rebuilt with the
renderer's own aim rule. Nothing is estimated from pixels. The file is written in
the pcve_ground_truth/1 layout (scripts/pcve_ground_truth.py), converted from that
per-frame record without resampling (the spring is located at its coil centre and
the launch platform is left out); --case-id names the suite case (default: the
folder of --out).
"""
from pathlib import Path
import argparse, hashlib, sys

import bpy
import numpy as np
from mathutils import Quaternion, Vector

sys.dont_write_bytecode = True  # scene modules imported below must not leave __pycache__ in scripts/
HERE = Path(__file__).resolve().parent
SCENE = HERE.parent
sys.path[:0] = [str(SCENE), str(SCENE.parents[1])]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def matrix(m):
    return [[float(v) for v in row] for row in m]


def camera_record(scene, cam, width, height):
    data = cam.data
    r = scene.render
    aspect = width * r.pixel_aspect_x / (height * r.pixel_aspect_y)
    fit = data.sensor_fit if data.sensor_fit != 'AUTO' else ('HORIZONTAL' if aspect >= 1 else 'VERTICAL')
    if fit == 'HORIZONTAL':
        fx = data.lens / data.sensor_width * width
        fy = fx * r.pixel_aspect_x / r.pixel_aspect_y
    else:
        fy = data.lens / data.sensor_height * height
        fx = fy * r.pixel_aspect_y / r.pixel_aspect_x
    size = max(width, height)
    cx = width / 2 - data.shift_x * size
    cy = height / 2 + data.shift_y * size
    return {
        'matrix_world': matrix(cam.matrix_world),
        'intrinsics': [[fx, 0, cx], [0, fy, cy], [0, 0, 1]],
        'intrinsics_convention': 'pixels, origin top-left, y down; camera looks along -Z of matrix_world (Blender)',
        'lens_mm': data.lens, 'sensor_width_mm': data.sensor_width, 'sensor_fit': fit,
        'shift': [data.shift_x, data.shift_y], 'clip': [data.clip_start, data.clip_end],
        'resolution': [width, height], 'name': cam.name, 'trajectory': 'fixed',
    }


def pose(position, quat_wxyz):
    m = Quaternion([float(v) for v in quat_wxyz]).to_matrix().to_4x4()
    m.translation = Vector([float(v) for v in position])
    return m


def rigid_state(position, quat, vel, offset=(0, 0, 0)):
    m = pose(position, quat)
    if any(offset):
        m.translation = m @ Vector(offset)
    return {'present': True, 'matrix_world': matrix(m), 'location': [float(v) for v in position],
            'quaternion_wxyz': [float(v) for v in quat],
            'linear_velocity': [float(v) for v in vel[3:]], 'angular_velocity': [float(v) for v in vel[:3]]}


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', required=True)
    ap.add_argument('--native', type=Path, required=True, help='folder with states.npz and resolved_physics.json of the case')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--case-id', help='suite case folder name (default: the folder of --out)')
    ap.add_argument('--camera-location', type=float, nargs=3)
    ap.add_argument('--camera-target', type=float, nargs=3)
    ap.add_argument('--lens', type=float)
    ap.add_argument('--sensor-width', type=float, default=36.0)
    ap.add_argument('--generator-note', default='')
    a = ap.parse_args(argv)
    from scene_common import CASES, FPS, FRAMES, HEIGHT, WIDTH, CASE_ID, load_physics, spring_properties
    c = load_physics(a.native / 'resolved_physics.json')
    z = np.load(a.native / 'states.npz')
    names = [str(n) for n in z['body_names']]
    if len(z['time']) != FRAMES or np.max(np.abs(z['time'] - np.arange(FRAMES) / FPS)) > 1e-12:
        raise SystemExit('native states do not hold the 96 video instants t=i/24 s')
    scene = bpy.context.scene
    if a.camera_location:
        if a.camera_target is None or a.lens is None:
            raise SystemExit('--camera-location needs --camera-target and --lens')
        data = bpy.data.cameras.new('ground truth camera')
        cam = bpy.data.objects.new('Fixed side front camera', data)
        scene.collection.objects.link(cam)
        cam.location = a.camera_location
        # Same aim rule as appearance/base_scene.aim().
        cam.rotation_euler = (Vector(a.camera_target) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        data.lens, data.sensor_width = a.lens, a.sensor_width
        bpy.context.view_layer.update()
        camera_source = {'kind': 'render record (location, aim target, lens, sensor)', 'location': a.camera_location,
                         'target': a.camera_target, 'lens_mm': a.lens, 'sensor_width_mm': a.sensor_width}
        width, height = WIDTH, HEIGHT
    else:
        cam = scene.camera
        if cam is None or not bpy.data.filepath:
            raise SystemExit('open the scene.blend of the case, or give --camera-location/--camera-target/--lens')
        if cam.animation_data is not None:
            raise SystemExit('camera is animated; this exporter expects the fixed camera')
        r = scene.render
        width, height = r.resolution_x * r.resolution_percentage // 100, r.resolution_y * r.resolution_percentage // 100
        camera_source = {'kind': 'scene.blend', 'blend_sha256': sha(bpy.data.filepath)}
    camera = camera_record(scene, cam, width, height)
    if (width, height) != (WIDTH, HEIGHT):
        raise SystemExit(f'camera resolution {width}x{height} is not the delivered {WIDTH}x{HEIGHT}')

    spring = 'pusher' in names
    added = 'obstacle' in names
    derived = spring_properties(c)
    plate_offset = (-.001, 0, 0)  # collision-frame offset of the push plate in its body frame (physics/simulate.py)
    upper = np.eye(4); upper[:3, 3] = c['upper_position_m']
    table = np.eye(4); table[:3, 3] = c['table_position_m']
    risers = []
    for centre in c['platform_riser_centres_m']:
        m = np.eye(4); m[:3, 3] = centre; risers.append(matrix(m))
    block = 'block' in names
    objects = {
        'block': ({'present': True, 'rigid': True, 'mass': float(c['block_mass_kg']), 'dimensions_m': c['block_size_m'],
                   'motion_source': 'PyBullet 3.2.5 rigid box (native states)'} if block else {'present': False}),
        'spring': ({'present': True, 'deformable': True, 'kind': 'helical compression spring, axial deformation only',
                    'young_modulus_pa': float(c['spring_young_modulus_pa']), 'poisson_ratio': float(c['spring_poisson_ratio']),
                    'stiffness_n_m': float(derived['stiffness_n_m']), 'wire_diameter_m': float(c['spring_wire_diameter_m']),
                    'mean_coil_diameter_m': float(c['spring_mean_diameter_m']), 'active_turns': int(c['spring_active_turns']),
                    'free_seat_length_m': float(c['steel_free_seat_length_m']), 'fixed_seat_x_m': float(c['spring_anchor_x_m']),
                    'axis': {'y_m': 0.0, 'z_m': float(c['spring_axis_z_m']), 'direction': [1, 0, 0]},
                    'motion_source': 'axial length from the native push-plate state (moving seat = plate back face)'}
                   if spring else {'present': False}),
        'push_plate': ({'present': True, 'rigid': True, 'mass': float(c['pusher_mass_kg'] + derived['effective_coil_mass_kg']),
                        'dimensions_m': c['pusher_size_m'], 'constraint': 'prismatic guide along +x, latched until t=0.375 s',
                        'note': 'matrix_world is the visible plate (body origin + 1 mm collision-frame offset along -x); location is the body origin',
                        'motion_source': 'PyBullet rigid box (native states)'} if spring else {'present': False}),
        'obstacle': ({'present': True, 'rigid': True, 'mass': float(c['obstacle_mass_kg']), 'dimensions_m': c['obstacle_size_m'],
                      'motion_source': 'PyBullet rigid box (native states)'} if added else {'present': False}),
        'launch_platform': {'present': True, 'fixed': True, 'dimensions_m': c['upper_size_m'], 'matrix_world': matrix(upper),
                            'top_z_m': float(c['upper_position_m'][2] + c['upper_size_m'][2] / 2),
                            'block_friction': float(c['upper_friction']),
                            'risers': {'dimensions_m': c['platform_riser_size_m'], 'matrix_world': risers}},
        'table': {'present': True, 'fixed': True, 'dimensions_m': c['table_size_m'], 'matrix_world': matrix(table),
                  'top_z_m': float(c['table_position_m'][2] + c['table_size_m'][2] / 2),
                  'block_friction': float(c['table_friction'])},
    }
    frames = []
    for i in range(FRAMES):
        P, Q, V = z['positions'][i], z['quaternions'][i], z['cvel'][i]
        state = {'block': rigid_state(P[names.index('block')], Q[names.index('block')], V[names.index('block')])
                 if block else {'present': False}}
        if spring:
            j = names.index('pusher')
            plate = rigid_state(P[j], Q[j], V[j], plate_offset)
            state['push_plate'] = plate
            seat = float(P[j][0]) + 2 * plate_offset[0]          # back face of the 2 mm plate
            length = seat - c['spring_anchor_x_m']
            r = (c['spring_mean_diameter_m'] + c['spring_wire_diameter_m']) / 2
            centre = [(c['spring_anchor_x_m'] + seat) / 2, 0.0, c['spring_axis_z_m']]
            m = np.eye(4); m[:3, 3] = centre
            state['spring'] = {'present': True, 'deformable': True, 'matrix_world': matrix(m), 'centroid': centre,
                               'axial_length_m': length, 'compression_m': float(c['steel_free_seat_length_m'] - length),
                               'bbox_min': [c['spring_anchor_x_m'], -r, c['spring_axis_z_m'] - r],
                               'bbox_max': [seat, r, c['spring_axis_z_m'] + r],
                               'linear_velocity': [float(V[j][3]) / 2, 0.0, 0.0]}
        else:
            state['push_plate'] = {'present': False}
            state['spring'] = {'present': False}
        if added:
            j = names.index('obstacle')
            state['obstacle'] = rigid_state(P[j], Q[j], V[j])
        else:
            state['obstacle'] = {'present': False}
        state['launch_platform'] = {'present': True, 'matrix_world': objects['launch_platform']['matrix_world']}
        state['table'] = {'present': True, 'matrix_world': objects['table']['matrix_world']}
        frames.append({'frame_index': i + 1, 'time_sec': float(z['time'][i]), 'native_state_index': i,
                       'camera_matrix_world': camera['matrix_world'], 'objects': state})
    record = {
        'schema_version': 3, 'scene_id': CASE_ID, 'case_id': a.case, 'edit_dsl': CASES[a.case][1],
        'interaction_category': 'rigid_elastic', 'fps': FPS, 'resolution': camera['resolution'],
        'frame_start': 1, 'frame_end': FRAMES, 'coordinate_system': 'right-handed, Z up, metres, seconds',
        'camera': camera, 'objects': objects, 'frames': frames,
        'source': {'states_sha256': sha(a.native / 'states.npz'), 'resolved_physics_sha256': sha(a.native / 'resolved_physics.json'),
                   'native_samples': int(len(z['time'])), 'native_sample_hz': FPS,
                   'note': 'video frame i (1..96) shows native state i-1 at t=(i-1)/24 s',
                   'camera_source': camera_source,
                   'generator': 'scripts/rigid_elastic/spring_block_step/tools/export_ground_truth.py'},
    }
    if a.generator_note:
        record['source']['note_camera'] = a.generator_note
    from pcve_ground_truth import from_schema3, write
    a.out.parent.mkdir(parents=True, exist_ok=True)
    write(a.out, from_schema3(record, CASE_ID, a.case_id or a.out.parent.name, skip=['launch_platform'],
                              deformable=['spring'], tool=record['source']['generator'],
                              files=[a.native / 'states.npz', a.native / 'resolved_physics.json']))
    print('GROUND_TRUTH', a.case, a.out, len(frames), 'frames', flush=True)


if __name__ == '__main__':
    main()
