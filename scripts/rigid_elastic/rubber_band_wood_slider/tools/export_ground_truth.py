"""Write cases/<case>/ground_truth_transforms.json for every case of a suite (pcve_ground_truth/1).

Per-frame values come only from the accepted native states the videos replay (simulation.npz of each case in the
registered increment, 480 Hz; video frame i shows state 20*i, t = i/24 s); the camera comes from the case's
render_provenance.json (the camera is fixed). Nothing is interpolated or authored. The per-frame native record is
converted to the pcve_ground_truth/1 layout by scripts/pcve_ground_truth.py; the left clamp is static scenery and is
left out.

    python3 scripts/rigid_elastic/rubber_band_wood_slider/tools/export_ground_truth.py \
        --suite DIR [--cases source ...] [--check] [--compare-increment]

--check recomputes every file and fails if one differs from what is on disk (the "source" block, which only records
how a file was made, is not compared); --compare-increment compares the slider track and camera with the ground truth
delivered inside the registered increment.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

CASE_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(CASE_DIR), str(CASE_DIR.parents[1])]
from scene_paths import (CASES, CATALOG, FPS, FRAMES, INCREMENT_NAME, PREFIX, REPO, RESOLUTION, SCENE,  # noqa: E402
                         ensure_numpy_runtime, increment_member, native_case, sha256, state_sha256)
from pcve_ground_truth import from_schema3, write  # noqa: E402

ensure_numpy_runtime()
import numpy as np  # noqa: E402

STRIDE = 20                       # 480 Hz native states, 24 fps video
SENSOR_WIDTH_MM = 36.0            # appearance/render_scene.py: cam.data.sensor_width=36 (horizontal fit)
STOP_EARS_Y = (-0.016, 0.016)     # the two blocks of the added stop (render_scene.py), 22 mm clear between them


def vec(values):
    return [float(v) for v in values]


def translation(x, y, z):
    return [[1.0, 0.0, 0.0, float(x)], [0.0, 1.0, 0.0, float(y)], [0.0, 0.0, 1.0, float(z)], [0.0, 0.0, 0.0, 1.0]]


def camera_block(prov):
    lens = float(prov['lens_mm'])
    width, height = prov['resolution']
    sensor = float(prov.get('sensor_width_mm', SENSOR_WIDTH_MM))
    focal = lens / sensor * width
    assert [width, height] == list(RESOLUTION), prov['resolution']
    return {'matrix_world': [vec(r) for r in prov['camera_matrix_world']],
            'intrinsics': [[focal, 0, width / 2], [0, focal, height / 2], [0, 0, 1]],
            'lens_mm': lens, 'sensor_width_mm': sensor, 'sensor_fit': 'HORIZONTAL', 'shift': [0.0, 0.0],
            'fstop': prov.get('fstop'), 'convention': 'Blender camera: looks along local -Z, +Y up', 'trajectory': 'fixed'}


def loop_length(centres):
    return float(np.linalg.norm(np.roll(centres, -1, axis=0) - centres, axis=1).sum())


def build(case, prov):
    folder = native_case(case)
    states = folder / 'states.npz'
    accepted = state_sha256(case)
    if sha256(states) != accepted:
        raise SystemExit(f'{case}: native states differ from the accepted increment')
    if prov['simulation_cache_sha256'] != accepted:
        raise SystemExit(f'{case}: the render provenance belongs to other native states')
    info = json.loads((folder / 'physics.json').read_text())
    p = info['physics']
    z = np.load(states)
    times, trace, band = z['times'], z['trace'], z['band_vertices']
    rows = int(info['width_rows'])
    index = np.arange(FRAMES) * STRIDE
    assert np.allclose(times[index], np.arange(FRAMES) / FPS, atol=1e-9), 'native clock is not 480 Hz'
    band_present = bool(p['band_present'][0])
    stop_present = bool(p['stopper_present'][0])
    half = p['slider_size_m'][2] / 2
    floor = p['floor_z_m']
    camera = camera_block(prov)
    objects = {
        'slider': {'present': True, 'rigid': True, 'mass': float(p['mass_kg']), 'dimensions_m': vec(p['slider_size_m']),
                   'origin': 'centre of the 55 x 42 x 24 mm block (centre of mass); moves along +x/-x only',
                   'peg_offset_x_m': float(p['attachment_offset_m'])},
        'band': {'present': band_present, 'deformable': True, 'young_modulus_pa': float(p['young_pa']),
                 'rest_loop_length_m': float(p['loop_rest_m']), 'width_m': float(p['band_width_m']),
                 'thickness_m': float(p['band_thickness_m']),
                 'vertex_count': int(band.shape[1]) if band_present else 0,
                 'fields': 'vertex_centroid / vertex_bbox_min / vertex_bbox_max over the shell mid-surface vertices; '
                           'centerline_length_m: closed polyline through the width-row midpoints; '
                           'max_principal_stretch and elastic_energy_j from the solver trace'},
        'stopper': {'present': stop_present, 'static': True, 'centre_m': vec(p['stopper_position_m']),
                    'envelope_m': vec(p['stopper_size_m']),
                    'parts': [{'centre_m': [p['stopper_position_m'][0], y, p['stopper_position_m'][2]],
                               'size_m': [p['stopper_size_m'][0], 0.010, p['stopper_size_m'][2]]} for y in STOP_EARS_Y]},
        'guide': {'present': True, 'static': True, 'dimensions_m': vec(p['guide_size_m']), 'floor_top_z_m': float(floor),
                  'slider_friction': float(p['friction'])},
        'left_clamp': {'present': True, 'static': True, 'band_anchor_x_m': float(p['anchor_x_m']),
                       'peg_radius_m': float(p['pin_radius_m'])},
    }
    frames = []
    for f, k in enumerate(index):
        x, vx = float(trace[k, 1]), float(trace[k, 2])
        entry = {'frame_index': f + 1, 'time_sec': f / FPS, 'native_state_index': int(k),
                 'camera_matrix_world': camera['matrix_world'], 'objects': {}}
        entry['objects']['slider'] = {'present': True, 'matrix_world': translation(x, 0.0, floor + half),
                                      'location': [x, 0.0, floor + half], 'rotation_euler': [0.0, 0.0, 0.0],
                                      'linear_velocity': [vx, 0.0, 0.0], 'angular_velocity': [0.0, 0.0, 0.0],
                                      'displacement_from_start_m': x - float(trace[0, 1])}
        if band_present:
            v = band[k]
            centres = v.reshape(-1, rows, 3).mean(axis=1)
            entry['objects']['band'] = {
                'present': True, 'deformable': True, 'deformation_frame_index': int(k),
                'matrix_world': translation(0, 0, 0),
                'vertex_centroid': vec(v.mean(0)), 'vertex_bbox_min': vec(v.min(0)), 'vertex_bbox_max': vec(v.max(0)),
                'centerline_length_m': loop_length(centres),
                'max_principal_stretch': float(trace[k, 5]), 'elastic_energy_j': float(trace[k, 3])}
        else:
            entry['objects']['band'] = {'present': False, 'deformable': True}
        entry['objects']['stopper'] = ({'present': True, 'matrix_world': translation(*p['stopper_position_m']),
                                        'location': vec(p['stopper_position_m'])} if stop_present else {'present': False})
        entry['objects']['guide'] = {'present': True, 'matrix_world': translation(0, 0, 0)}
        frames.append(entry)
    src = f'{PREFIX}cases/{case}/simulation.npz'
    return {'schema_version': 3, 'scene_id': SCENE, 'interaction_category': 'rigid_elastic', 'case_id': CATALOG[case],
            'native_case_id': case, 'fps': FPS, 'resolution': list(RESOLUTION), 'frame_start': 1, 'frame_end': FRAMES,
            'units': {'length': 'm', 'time': 's', 'angle': 'rad', 'mass': 'kg'},
            'world': 'Blender world, z up; the guide runs along x, the slider returns towards -x; guide floor top at z = 0.006 m',
            'source': {'native_states': f'{INCREMENT_NAME}#{src}', 'native_states_sha256': accepted,
                       'native_rate_hz': 480, 'frame_stride': STRIDE, 'camera': 'native_metadata/render_provenance.json of this case',
                       'exporter': str(Path(__file__).resolve().relative_to(REPO))},
            'material_calibrated': False, 'camera': camera, 'objects': objects, 'frames': frames}


def convert(case, record):
    """pcve_ground_truth/1 record of one case from its native record (no resampling)."""
    return from_schema3(record, SCENE, CATALOG[case], skip=['left_clamp'], tool=record['source']['exporter'],
                        files=[native_case(case) / 'states.npz', native_case(case) / 'physics.json'])


def compare_increment(case, gt):
    old = json.loads(increment_member(f'cases/{case}/ground_truth_transforms.json'))
    dx = max(abs(a['objects']['slider']['location'][0] - b['objects']['slider']['matrix_world'][0][3])
             for a, b in zip(gt['frames'], old['frames']))
    cam = float(np.abs(np.array(gt['camera']['matrix_world']) - np.array(old['camera']['matrix_world'])).max())
    return {'case': case, 'increment_frames': len(old['frames']), 'max_slider_x_difference_m': dx, 'max_camera_difference': cam}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--suite', type=Path, required=True,
                    help='suite whose cases/<id>/ground_truth_transforms.json are written (pcve_ground_truth/1)')
    ap.add_argument('--cases', nargs='+', choices=CASES, default=CASES)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--compare-increment', action='store_true')
    a = ap.parse_args()
    suite = a.suite.resolve()
    rows = []
    for case in a.cases:
        folder = suite / 'cases' / CATALOG[case]
        prov = json.loads((folder / 'native_metadata/render_provenance.json').read_text())
        record = build(case, prov)
        gt = convert(case, record)
        text = json.dumps(gt, indent=1, allow_nan=False) + '\n'
        target = folder / 'ground_truth_transforms.json'
        if a.check:
            def body(value):
                return {k: v for k, v in value.items() if k != 'source'}
            if not target.is_file() or body(json.loads(target.read_text())) != body(json.loads(text)):
                raise SystemExit(f'ground truth differs from the native states: {target}')
        else:
            write(target, gt)
        row = {'case': CATALOG[case], 'file': str(target), 'sha256': hashlib.sha256(text.encode()).hexdigest()}
        if a.compare_increment:
            row['increment'] = compare_increment(case, record)
        rows.append(row)
    print(json.dumps({'checked' if a.check else 'written': rows}, indent=1))


if __name__ == '__main__':
    main()
