"""Write ground_truth_transforms.json for every case of a book_pillow_bedroom video suite.

Everything comes from the accepted native cache of the case (simulation.npz, physics_config.json) and the
camera recorded by the render that produced the video (render_report.json); nothing is fitted or
invented. Rigid books: world matrix, location and linear velocity per frame (the falling book's
velocity is the solver's own; the added book's is a central difference of its cached poses).
Deformable pillow and quilt: presence, the cache sample index, and the centroid and axis-aligned
bounds of the cached vertices (pillow: the rendered surface; quilt: the simulated volume nodes).

    <numpy python> tools/export_ground_truth.py --suite SUITE --native-root renders/book_pillow_bedroom/accepted/cases \
        --render-root RENDERS [--cases source heavy_book ...] [--out-name ground_truth_transforms.json]

The files are written in the pcve_ground_truth/1 layout (scripts/pcve_ground_truth.py): the per-frame native
record above, converted without resampling (books at their recorded pose, pillow and quilt at their vertex centroid).
"""
from pathlib import Path
import argparse
import json
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from pcve_ground_truth import from_schema3, write  # noqa: E402

SCENE = 'book_pillow_bedroom'
FPS = 24
RESOLUTION = (1280, 720)
CASES = ('source', 'heavy_book', 'soft_pillow', 'firm_pillow', 'remove_pillow', 'add_bedside_book')


def catalog_id(case):
    return 'source' if case == 'source' else 'edit_' + case


def physics(config):
    return config.get('physics', config)


def camera_record(report):
    matrix = report.get('camera_matrix')
    if matrix is None:
        raise ValueError('render_report.json has no camera_matrix')
    lens = float(report['camera_lens_mm'])
    sensor = float(report.get('camera_sensor_width_mm', 36.0))   # Blender default; the delivered camera keeps it
    fit = report.get('camera_sensor_fit', 'AUTO')
    shift = report.get('camera_shift', [0.0, 0.0])
    w, h = RESOLUTION
    if fit not in ('AUTO', 'HORIZONTAL'):
        raise ValueError('Only a horizontal sensor fit is handled: ' + fit)
    f = lens / sensor * w
    cx, cy = w / 2 - shift[0] * w, h / 2 + shift[1] * w
    return {'matrix_world': matrix, 'intrinsics': [[f, 0, cx], [0, f, cy], [0, 0, 1]], 'lens_mm': lens,
            'sensor_width_mm': sensor, 'sensor_fit': fit, 'shift': shift, 'trajectory': 'fixed',
            'convention': 'Blender camera: looks along its local -Z, +Y up; intrinsics in pixels, origin at the top-left'}


def bounds(points):
    return {'centroid': points.mean(0).tolist(), 'bbox_min': points.min(0).tolist(), 'bbox_max': points.max(0).tolist()}


def export(case, native, report):
    z = np.load(native / 'simulation.npz')
    cfg = physics(json.loads((native / 'physics_config.json').read_text()))
    times = z['times']
    n = len(times)
    if n != 96 or not np.allclose(times, np.arange(n) / FPS, atol=1e-9):
        raise ValueError(f'{case}: cache times are not i/24 for 96 frames')
    book = z['phone_transforms']; book_v = z['phone_linear_velocity']
    pillow = z['pillow_art_positions'] if z['pillow_present'].item() else None
    accent = z['accent_book_transforms'] if z['accent_book_present'].item() else None
    duvet = z['duvet_positions']
    camera = camera_record(report)
    objects = {'book': {'present': True, 'mass': float(cfg['phone_mass_kg']), 'dimensions_m': list(cfg['phone_dimensions_m']),
                        'rigid': True, 'label': 'blue book'},
               'pillow': {'present': pillow is not None, 'deformable': True,
                          'young_modulus_pa': float(cfg['pillow_young_modulus_pa']), 'label': 'pillow',
                          'geometry': 'rendered pillow surface (pillow_art_positions)'},
               'duvet': {'present': True, 'deformable': True, 'young_modulus_pa': float(cfg['duvet_young_modulus_pa']),
                         'label': 'duvet over the mattress', 'geometry': 'simulated quilt volume nodes (duvet_positions)'}}
    if accent is not None:
        objects['extra_book'] = {'present': True, 'mass': float(cfg['accent_book_mass_kg']),
                                 'dimensions_m': list(cfg['accent_book_dimensions_m']), 'rigid': True, 'label': 'brown book'}
        accent_v = np.gradient(accent[:, :3, 3], 1 / FPS, axis=0)
    identity = np.eye(4).tolist()
    frames = []
    for i in range(n):
        row = {'book': {'present': True, 'matrix_world': book[i].tolist(), 'location': book[i, :3, 3].tolist(),
                        'linear_velocity': book_v[i].tolist()},
               'pillow': {'present': pillow is not None, 'deformable': True},
               'duvet': {'present': True, 'deformable': True, 'deformation_frame_index': i, 'matrix_world': identity,
                         **bounds(duvet[i])}}
        if pillow is not None:
            row['pillow'].update(deformation_frame_index=i, matrix_world=identity, **bounds(pillow[i]))
        if accent is not None:
            row['extra_book'] = {'present': True, 'matrix_world': accent[i].tolist(), 'location': accent[i, :3, 3].tolist(),
                                 'linear_velocity': accent_v[i].tolist()}
        frames.append({'frame_index': i + 1, 'time_sec': float(times[i]), 'camera_matrix_world': camera['matrix_world'],
                       'objects': row})
    return {'schema_version': 3, 'scene_id': SCENE, 'case_id': catalog_id(case), 'native_case_id': case,
            'interaction_category': 'rigid_elastic', 'fps': FPS, 'resolution': list(RESOLUTION),
            'frame_start': 1, 'frame_end': n, 'coordinate_system': 'right-handed, Z up, metres',
            'camera': camera, 'objects': objects, 'frames': frames,
            'sources': {'native_cache': 'simulation.npz', 'physics_config': 'physics_config.json',
                        'camera': 'render_report.json of the render that produced the video',
                        'added_book_velocity': 'central difference of cached poses' if accent is not None else None}}


def find_report(render_root, case):
    for candidate in (render_root / case / 'render_report.json', render_root / case / 'render' / 'render_report.json'):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f'No render_report.json for {case} under {render_root}')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--suite', type=Path, required=True)
    p.add_argument('--native-root', type=Path, required=True)
    p.add_argument('--render-root', type=Path, required=True)
    p.add_argument('--cases', nargs='+', choices=CASES, default=list(CASES))
    p.add_argument('--out-name', default='ground_truth_transforms.json')
    a = p.parse_args()
    written = []
    for case in a.cases:
        report_path = find_report(a.render_root, case)
        native = a.native_root / case
        gt = from_schema3(export(case, native, json.loads(report_path.read_text())), SCENE, catalog_id(case),
                          tool='scripts/rigid_elastic/book_pillow_bedroom/tools/export_ground_truth.py',
                          files=[native / 'simulation.npz', native / 'physics_config.json', report_path])
        out = a.suite / 'cases' / catalog_id(case) / a.out_name
        if not out.parent.is_dir():
            raise FileNotFoundError(out.parent)
        write(out, gt)   # written beside and renamed: the existing file may belong to another user
        written.append({'case': catalog_id(case), 'file': str(out), 'frames': len(gt['frames']),
                        'camera_from': str(report_path)})
    print(json.dumps(written, indent=2))


if __name__ == '__main__':
    main()
