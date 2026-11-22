"""Write a case's ground_truth_transforms.json (PCVE suite layout) from its native delivery case folder.

Every per-frame value comes from the native solver output of the case: cache.npz (curtain vertex positions and
velocities, vertex masses, rigid affine transforms, sample times i/24 s), the rigid collision meshes stored with
the case (geometry/<object>_native.npz, for the centre of mass) and simulation_config.json (masses, presence).
The fixed camera comes from the case's camera_calibration.json. Optional per-frame visible pixel counts come from
the case's instance_masks.npz (ids 1 figurine, 2 curtain, 3 cup). Nothing is authored; rigid linear velocities
are central differences of the native centre-of-mass positions (one-sided at the ends).

Format pcve_ground_truth/1 (layout A of eval/metrics/common/traj_lib.py): frames[i][<object>] holds present, location,
quaternion_xyzw and matrix_world. The curtain is tracked by the centroid of its shell vertices (identity rotation).
The camera_calibration.json files of the accepted delivery hold an identity matrix_world (they were read before
the depsgraph update that appearance/render.py now performs); --camera takes the fixed camera from a render
scene_manifest.json that records it (same LAYOUT camera for every case), and an identity camera is refused.

    python3 tools/export_ground_truth.py --case-dir DELIVERY/cases/source --out OUT.json --camera RENDER/scene_manifest.json
    python3 tools/export_ground_truth.py --delivery DELIVERY --suite renders/pcve_suites/pcve_curtain_doraemon_drape_suite \
        --camera RENDER/scene_manifest.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

CASES = ('source', 'young_modulus_x10', 'density_x0_5', 'friction_x0_1', 'delete_figurine', 'friction_x0_1_at_frame_8')
CATALOG = {case: 'source' if case == 'source' else 'edit_' + case for case in CASES}
MASK_IDS = {'figurine': 1, 'curtain': 2, 'ceramic_cup': 3}


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.writing')   # replace, do not rewrite in place
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def mesh_com(path: Path) -> np.ndarray:
    """Centre of mass of a closed triangle mesh of uniform density (divergence theorem)."""
    g = np.load(path); v = g['vertices']; f = g['faces']
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    vol = np.einsum('ij,ij->i', a, np.cross(b, c)) / 6.
    return ((a + b + c) / 4. * vol[:, None]).sum(0) / vol.sum()


def velocity(points: np.ndarray, dt: float) -> np.ndarray:
    return np.gradient(points, dt, axis=0, edge_order=1)


def quaternion_xyzw(R: np.ndarray) -> list:
    """Rotation of an affine body transform (polar factor; the native affine map is orthogonal to ~1e-9)."""
    u, _, vt = np.linalg.svd(R); Q = u @ vt
    w = np.sqrt(max(0., 1. + Q[0, 0] + Q[1, 1] + Q[2, 2])) / 2
    if w > 1e-6:
        x = (Q[2, 1] - Q[1, 2]) / (4 * w); y = (Q[0, 2] - Q[2, 0]) / (4 * w); z = (Q[1, 0] - Q[0, 1]) / (4 * w)
    else:
        i = int(np.argmax(np.diag(Q))); j, k = (i + 1) % 3, (i + 2) % 3
        r = np.sqrt(max(0., 1. + Q[i, i] - Q[j, j] - Q[k, k])); q = [0., 0., 0.]
        q[i] = r / 2; q[j] = (Q[j, i] + Q[i, j]) / (2 * r); q[k] = (Q[k, i] + Q[i, k]) / (2 * r); w = (Q[k, j] - Q[j, k]) / (2 * r)
        x, y, z = q
    n = np.sqrt(x * x + y * y + z * z + w * w)
    return [float(x / n), float(y / n), float(z / n), float(w / n)]


def ground_truth(case_dir: Path, camera_manifest: Path | None = None) -> dict:
    config = json.loads((case_dir / 'simulation_config.json').read_text(encoding='utf-8'))
    camera = json.loads((case_dir / 'camera_calibration.json').read_text(encoding='utf-8')) if (case_dir / 'camera_calibration.json').is_file() else {}
    if camera_manifest is not None:
        record = json.loads(Path(camera_manifest).read_text(encoding='utf-8'))
        if record['camera_layout'] != config['layout']:
            raise ValueError('The camera record belongs to another layout')
        camera = dict(camera, matrix_world=record['camera']['matrix_world'], lens_mm=record['camera']['lens_mm'],
                      sensor_width_mm=record['camera']['sensor_width_mm'], resolution=record['resolution'],
                      shift=record['camera']['shift'], aperture_fstop=record['camera']['fstop'],
                      sensor_fit=record['camera']['sensor_fit'], record=str(camera_manifest))
    if np.allclose(np.asarray(camera['matrix_world']), np.eye(4)):
        raise ValueError('Camera matrix_world is the identity (stale record); pass --camera with a fixed render manifest')
    with np.load(case_dir / 'cache.npz') as archive:
        cache = {key: archive[key] for key in archive.files}
    times = cache['times']; n = len(times); dt = float(times[1] - times[0])
    if config['scene_id'] != 'curtain_doraemon_drape' or n != 96 or not np.allclose(times, np.arange(n) / 24.):
        raise ValueError(f'Not a 96-sample curtain_doraemon_drape solve: {case_dir}')
    masks = None
    if (case_dir / 'instance_masks.npz').is_file():
        masks = np.load(case_dir / 'instance_masks.npz')['masks']
    names = [str(x) for x in cache['rigid_names']]; physics = config['physics']
    resolution = camera['resolution']; shift = camera.get('shift', [0.0, 0.0])
    timed = (config.get('timed_continuation') or None)
    gt = dict(schema_version=3, format_version='pcve_ground_truth/1', scene='curtain_doraemon_drape', case_id=CATALOG[config['case_id']],
              fps=24, frame_start=1, frame_end=n, units='m',
              camera=dict(resolution=resolution, projection='perspective', lens_mm=camera['lens_mm'],
                          sensor_width_mm=camera['sensor_width_mm'], sensor_fit=camera.get('sensor_fit', 'AUTO'),
                          shift_x=float(shift[0]), shift_y=float(shift[1]), matrix_world=camera['matrix_world'],
                          trajectory='fixed', aperture_fstop=camera.get('aperture_fstop'), record=camera.get('record')),
              coordinates='World, right handed, Z up, metres; the desk top is z = 0.',
              objects={}, frames=[])
    rigid = {}
    for name, mass_key, active in (('figurine', 'figure_mass', physics['figure_active'][0]),
                                   ('ceramic_cup', 'cup_mass', physics['cup_active'][0])):
        if not active:
            if name == 'figurine':
                gt['objects'][name] = dict(object_name='figurine', kind='rigid', present=False)
            continue
        T = cache['rigid_transforms'][:, names.index(name)]
        local_com = mesh_com(case_dir / 'geometry' / f'{name}_native.npz')
        com = np.einsum('tij,j->ti', T[:, :3, :3], local_com) + T[:, :3, 3]
        rigid[name] = (T, com, velocity(com, dt))
        g = np.load(case_dir / 'geometry' / f'{name}_native.npz')['vertices']
        gt['objects'][name] = dict(object_name=name, kind='rigid', present=True, mass=physics[mass_key],
                                   dimensions=(g.max(0) - g.min(0)).tolist(),
                                   native_origin='matrix_world/location: native collider frame, origin at the base centre (the porcelain vase)',
                                   local_center_of_mass=local_com.tolist())
    pos = cache['positions']; vel = cache['velocities']; m = cache['vertex_masses']
    centroid = pos.mean(1); cloth_vel = np.einsum('tvi,v->ti', vel, m) / m.sum()
    rest = cache['rest_positions']
    gt['objects']['curtain'] = dict(object_name='curtain', kind='deformable', present=True, mass=float(m.sum()),
        dimensions=(rest.max(0) - rest.min(0)).tolist(), surface_vertex_count=int(pos.shape[1]),
        location_semantics='centroid of the native shell vertices (cache.npz positions; all are surface vertices); '
                           'linear_velocity: mass-weighted mean vertex velocity; bbox: axis-aligned bounds, world metres')
    for i, t in enumerate(times):
        entry = dict(frame_index=i + 1, time_sec=float(t), camera_matrix_world=camera['matrix_world'])
        for name, (T, com, v) in rigid.items():
            entry[name] = dict(present=True, location=T[i, :3, 3].tolist(), quaternion_xyzw=quaternion_xyzw(T[i, :3, :3]),
                               matrix_world=T[i].tolist(), center_of_mass=com[i].tolist(), linear_velocity=v[i].tolist())
        if not physics['figure_active'][0]:
            entry['figurine'] = dict(present=False, location=None, quaternion_xyzw=None, matrix_world=None)
        c = centroid[i].tolist()
        entry['curtain'] = dict(present=True, location=c, quaternion_xyzw=[0., 0., 0., 1.],
                                matrix_world=[[1., 0., 0., c[0]], [0., 1., 0., c[1]], [0., 0., 1., c[2]], [0., 0., 0., 1.]],
                                linear_velocity=cloth_vel[i].tolist(), surface_bbox_min=pos[i].min(0).tolist(),
                                surface_bbox_max=pos[i].max(0).tolist())
        if masks is not None:
            for name, ident in MASK_IDS.items():
                if name in entry and entry[name].get('present'):
                    entry[name]['visible_pixels'] = int((masks[i] == ident).sum())
        gt['frames'].append(entry)
    files = [case_dir / 'cache.npz', case_dir / 'simulation_config.json']
    how = ('frame i = native sample i-1 (t=(i-1)/24) of the libuipc 0.0.29 solve the video replays; vase = native affine '
           'transform (collider frame, base centre); curtain = shell vertex centroid')
    if timed:
        how += (f"; timed edit at frame {timed['edit_frame']}: samples 1..{timed['edit_frame'] - 1} are the accepted source solve, "
                'later samples continue it from the exact source state of the edit frame with the edited friction')
    import hashlib
    gt['source'] = dict(how=how, files=[str(x) for x in files],
                        sha256={str(x): hashlib.sha256(x.read_bytes()).hexdigest() for x in files},
                        native_case_id=config['case_id'], generator='scripts/rigid_elastic/curtain_doraemon_drape/tools/export_ground_truth.py')
    return gt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--case-dir', type=Path, help='one native delivery case folder')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--delivery', type=Path, help='native delivery with cases/<case>/ (all six cases)')
    parser.add_argument('--suite', type=Path, help='published suite; writes cases/<catalog id>/ground_truth_transforms.json')
    parser.add_argument('--camera', type=Path, help='render scene_manifest.json with the evaluated fixed camera')
    parser.add_argument('--cases', nargs='+', choices=CASES, default=list(CASES[:5]))
    args = parser.parse_args()
    if args.delivery:
        if not args.suite:
            parser.error('--delivery needs --suite')
        for case in args.cases:
            target = args.suite / 'cases' / CATALOG[case] / 'ground_truth_transforms.json'
            save(target, ground_truth(args.delivery / 'cases' / case, args.camera)); print('wrote', target)
        return
    if not (args.case_dir and args.out):
        parser.error('give --case-dir and --out, or --delivery and --suite')
    save(args.out, ground_truth(args.case_dir, args.camera)); print('wrote', args.out)


if __name__ == '__main__':
    main()
