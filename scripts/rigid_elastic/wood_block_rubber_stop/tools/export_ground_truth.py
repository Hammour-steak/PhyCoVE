"""Per-frame ground truth of one delivered case (run inside Blender).

    blender -b <render out>/<case>/scene.blend --factory-startup --python tools/export_ground_truth.py -- \
        --case source --cache <cache>/source/simulation.npz --out <suite>/cases/source/ground_truth_transforms.json

The camera (pose, lens, sensor, shift, resolution) is read from the scene.blend
the case was rendered from. Every object state comes from the native libuipc
cache (`simulation.npz`): rigid blocks as their ABD transforms and velocities,
the free sponge as its FEM surface/volume vertices (centroid, bounding box,
mean velocity, peak displacement from rest). Video frame i (1..96) is native
state 10*(i-1) at t=(i-1)/24 s, the same samples the renderer takes
(`scene_spec.json`: 240 Hz cache, 24 FPS display, playback scale 1).
Nothing is keyframed or estimated from pixels. The file is written in the
pcve_ground_truth/1 layout (scripts/pcve_ground_truth.py), converted from that
per-frame record without resampling (the table leg and the floor are left out);
--case-id names the suite case (default: the folder of --out).
"""
from pathlib import Path
import argparse, hashlib, sys

import bpy
import numpy as np

sys.dont_write_bytecode = True  # scene modules imported below must not leave __pycache__ in scripts/
HERE = Path(__file__).resolve().parent
SCENE = HERE.parent
sys.path[:0] = [str(SCENE), str(SCENE.parents[1])]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def matrix(m):
    return [[float(v) for v in row] for row in m]


def angular_velocity(transform, velocity):
    """Spin of an affine body: skew part of dA/dt A^T (A = linear block of the transform)."""
    a, adot = np.asarray(transform)[:3, :3], np.asarray(velocity)[:3, :3]
    w = adot @ a.T
    w = .5 * (w - w.T)
    return [float(w[2, 1]), float(w[0, 2]), float(w[1, 0])]


def camera_record(scene):
    cam = scene.camera
    data = cam.data
    r = scene.render
    width = r.resolution_x * r.resolution_percentage // 100
    height = r.resolution_y * r.resolution_percentage // 100
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


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', required=True)
    ap.add_argument('--cache', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--case-id', help='suite case folder name (default: the folder of --out)')
    a = ap.parse_args(argv)
    from edit_vocab import SPEC, case_dsl, parameters
    p = parameters(a.case)
    z = np.load(a.cache, allow_pickle=False)
    scene = bpy.context.scene
    camera = camera_record(scene)
    step = round(SPEC['fps'] * SPEC['playback_time_scale'] / SPEC['display_fps'])
    count = round(SPEC['duration_s'] / SPEC['playback_time_scale'] * SPEC['display_fps'])
    times = z['times']
    if step * (count - 1) >= len(times):
        raise SystemExit('cache is shorter than the delivered window')
    if scene.camera.animation_data is not None:
        raise SystemExit('camera is animated; this exporter expects the fixed camera')

    block_dims = list(map(float, p['block_dimensions_m']))
    sponge_dims = list(map(float, p['bumper_dimensions_m']))
    leg_dims = list(map(float, p['backstop_dimensions_m']))
    leg_matrix = np.eye(4)
    leg_matrix[:3, 3] = p['backstop_center_m']
    added = bool(p['added_block_present']) and len(z['added_block_transforms']) > 0
    sponge = bool(p['bumper_present']) and len(z['elastic_rest_positions']) > 0
    block = bool(p.get('block_present', True))
    objects = {
        'wood_block': ({'present': True, 'rigid': True, 'mass': float(p['block_mass_kg']),
                        'dimensions_m': block_dims, 'motion_source': 'libuipc ABD cache'} if block else {'present': False}),
        'open_cell_sponge': ({'present': True, 'deformable': True,
                              'mass': float(np.prod(sponge_dims) * p['bumper_density_kg_m3']),
                              'rest_dimensions_m': sponge_dims,
                              'young_modulus_pa': float(p['bumper_young_modulus_pa']),
                              'vertex_count': int(len(z['elastic_rest_positions'])),
                              'motion_source': 'libuipc Stable Neo-Hookean FEM cache'}
                             if sponge else {'present': False}),
        'table_leg': {'present': True, 'fixed': True, 'dimensions_m': leg_dims,
                      'matrix_world': matrix(leg_matrix),
                      'note': 'fixed collision cuboid of the front-left table leg; the visible table is a static asset'},
        'secondary_wood_block': ({'present': True, 'rigid': True, 'mass': float(p['added_block_mass_kg']),
                                  'dimensions_m': list(map(float, p['added_block_dimensions_m'])),
                                  'motion_source': 'libuipc ABD cache'} if added else {'present': False}),
        'floor': {'present': True, 'fixed': True, 'plane': 'z = 0', 'block_friction': float(p['floor_friction']),
                  'sponge_friction': float(p['sponge_floor_friction'])},
    }
    rest = z['elastic_rest_positions'] if sponge else None
    frames = []
    for i in range(count):
        k = step * i
        T, V = z['block_transforms'][k], z['block_velocities'][k]
        state = {
            'wood_block': ({'present': True, 'matrix_world': matrix(T), 'location': [float(v) for v in T[:3, 3]],
                            'linear_velocity': [float(v) for v in V[:3, 3]],
                            'angular_velocity': angular_velocity(T, V)} if block else {'present': False}),
            'table_leg': {'present': True, 'matrix_world': objects['table_leg']['matrix_world']},
        }
        if sponge:
            x, v = z['elastic_positions'][k], z['elastic_velocities'][k]
            state['open_cell_sponge'] = {
                'present': True, 'deformable': True, 'deformation_frame_index': int(k),
                'matrix_world': matrix(np.eye(4)),
                'centroid': [float(c) for c in x.mean(axis=0)],
                'bbox_min': [float(c) for c in x.min(axis=0)], 'bbox_max': [float(c) for c in x.max(axis=0)],
                'linear_velocity': [float(c) for c in v.mean(axis=0)],
                'max_vertex_displacement_from_rest_m': float(np.linalg.norm(x - rest, axis=1).max()),
            }
        else:
            state['open_cell_sponge'] = {'present': False}
        if added:
            A, AV = z['added_block_transforms'][k], z['added_block_velocities'][k]
            state['secondary_wood_block'] = {'present': True, 'matrix_world': matrix(A),
                                             'location': [float(v) for v in A[:3, 3]],
                                             'linear_velocity': [float(v) for v in AV[:3, 3]],
                                             'angular_velocity': angular_velocity(A, AV)}
        else:
            state['secondary_wood_block'] = {'present': False}
        frames.append({'frame_index': i + 1, 'time_sec': float(times[k]), 'native_state_index': k,
                       'camera_matrix_world': camera['matrix_world'], 'objects': state})
    blend = Path(bpy.data.filepath)
    record = {
        'schema_version': 3, 'scene_id': 'wood_block_rubber_stop', 'case_id': a.case,
        'edit_dsl': case_dsl(a.case), 'interaction_category': SPEC['interaction_category'],
        'fps': SPEC['display_fps'], 'resolution': camera['resolution'],
        'frame_start': 1, 'frame_end': count, 'coordinate_system': 'right-handed, Z up, metres, seconds',
        'camera': camera, 'objects': objects, 'frames': frames,
        'source': {'cache_sha256': sha(a.cache), 'cache_states': int(len(times)), 'native_sample_hz': SPEC['fps'],
                   'native_state_stride': step, 'camera_blend_sha256': sha(blend),
                   'generator': 'scripts/rigid_elastic/wood_block_rubber_stop/tools/export_ground_truth.py'},
    }
    from pcve_ground_truth import from_schema3, write
    a.out.parent.mkdir(parents=True, exist_ok=True)
    write(a.out, from_schema3(record, 'wood_block_rubber_stop', a.case_id or a.out.parent.name,
                              skip=['table_leg', 'floor'], tool=record['source']['generator'], files=[a.cache, blend]))
    print('GROUND_TRUTH', a.case, a.out, count, 'frames', flush=True)


if __name__ == '__main__':
    main()
