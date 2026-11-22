"""Remove the source's water, then run its unchanged native rigid kernels.

The source uses a translation-only spherical apple, not a Genesis rigid entity.
Once all water and boundary particles are inactive, its exact dry equations are
apply_ball_external (gravity, zero liquid force) and advance_ball (solid contact).
No particle solve, pressure impulse, or prescribed apple trajectory is retained.
"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse
import copy
import hashlib
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import simulate_apple_drop_kitchen_basin as source

CASES = {'delete_water': 1, 'delete_water_at_2s': 49}


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def config(report):
    info = report['info']
    return {
        'physics': {**report['physics'], 'gravity_m_s2': source.GRAVITY,
                    'apple_radius_m': source.BALL_RADIUS,
                    'restitution': source.RESTITUTION, 'friction': source.FRICTION,
                    'initial_center_m': info['apple']['start_m'],
                    'initial_velocity_m_s': info['apple']['start_velocity_m_s'],
                    'water_removal_time_s': None},
        'simulation_quality': {key: info[key] for key in
            ('dx_m', 'substep_dt_s', 'substeps_per_frame', 'contact_gap_dx',
             'film_band_dx', 'minimum_sweeps', 'warm_start', 'domain_top_m')},
        'appearance': {'builder': 'scene_apple_drop_kitchen_basin.py',
                       'added_lights': False, 'camera': 'PCVE_HeroCamera',
                       'exposure': 0.7, 'look': 'AgX - Medium High Contrast'},
        'render': {'resolution': [1280, 720], 'fps': 24, 'frame_count': 96,
                   'duration_s': 4.0, 'samples': 1024, 'adaptive_threshold': 0.003,
                   'denoising': True, 'shutter_frames': 0.5},
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--case', choices=CASES, required=True)
    args = p.parse_args()
    started = time.monotonic()
    ref = json.loads((args.source / 'simulation_report.json').read_text())
    assert ref['status'] == 'complete' and len(ref['frames']) == 96
    assert not args.out.exists(), f'Refusing to overwrite {args.out}'
    args.out.mkdir(parents=True)
    (args.out / 'particles').mkdir()
    (args.out / 'aniso').mkdir()
    (args.out / 'render').mkdir()
    event_frame = CASES[args.case]
    before = config(ref)
    # Derive all numerical settings from the actual accepted source.
    info = ref['info']
    source.DOMAIN_TOP = info['domain_top_m']
    opts = SimpleNamespace(out=str(args.out), dx=info['dx_m'],
        substeps=info['substeps_per_frame'] // source.STEPS_PER_FRAME,
        extra_layers=2, divergence_error=info['divergence_error'],
        density_error=info['density_error_percent'], surface_tension=info['surface_tension_gamma'])
    gs, scene, solver, water, offsets, volumes, built = source.build_scene(
        opts, ref['physics']['liquid_density'], ref['physics']['liquid_nu'])
    with np.load(args.source / 'particles' / f'frame_{event_frame:04d}.npz') as data:
        event_state = np.stack([data['ball_center'], data['ball_velocity']]).astype(np.float64)
    solver.configure_ball(event_state[0], event_state[1], ref['physics']['ball_mass'],
        offsets, volumes, dynamic=True, film_band=info['film_band_dx'],
        contact_gap=info['contact_gap_dx'])
    # Deactivate both liquid and ghost particles. No hidden fluid contacts survive.
    for entity in solver.entities:
        entity.set_particles_active(np.zeros(entity.n_particles, dtype=np.bool_))
    active_counts = [int(e.get_particles_active().sum().item()) for e in solver.entities]
    assert active_counts == [0, 0]
    solver.pressure_impulse.fill(0)
    solver.viscous_force.fill(0)
    solver.audit.fill(0)
    solver.contacts[None] = int(ref['frames'][event_frame - 1]['floor_contacts']) if event_frame > 1 else 0
    actual = solver.ball.to_numpy()
    assert np.array_equal(actual, event_state), 'Event position/velocity changed'
    actual_scalars = solver.ball_scalars.to_numpy()
    assert np.allclose(actual_scalars, [1 / ref['physics']['ball_mass'], source.BALL_RADIUS,
                                       source.RESTITUTION, source.FRICTION], rtol=0, atol=1e-14)
    assert built['substep_dt_s'] == info['substep_dt_s']
    after = copy.deepcopy(before)
    after['physics']['water_removal_time_s'] = (event_frame - 1) / source.FPS
    report = {'case': args.case, 'status': 'running', 'source': str(args.source),
        'physics': ref['physics'], 'info': info, 'before': before, 'after': after,
        'event': {'time_s': (event_frame - 1) / source.FPS, 'frame': event_frame,
                  'state_before': event_state.tolist(), 'state_after': actual.tolist(),
                  'active_particle_counts': active_counts,
                  'pressure_impulse_after': solver.pressure_impulse.to_numpy().tolist(),
                  'viscous_force_after': solver.viscous_force.to_numpy().tolist()},
        'method': 'Original RigidBallSPH.apply_ball_external and advance_ball kernels at source dt; all particles inactive.',
        'limitations': ['Source apple is a smooth sphere with translation only; source does not simulate rotation.',
                        'Source contact proxy and 1.5 mm floor gap retained.'],
        'frames': []}
    # Empty liquid caches remove surface, spray, mist, foam, beads, and wet coats.
    with np.load(args.source / 'aniso/water_0001.npz') as data:
        empty_water = {k: np.empty((0,) + data[k].shape[1:], data[k].dtype) for k in data.files}
    with np.load(args.source / 'aniso/wet_0001.npz') as data:
        dry_wet = {k: data[k].copy() for k in data.files}
    for key in ('water_mm', 'wall', 'wall_film_mm'):
        assert not np.any(dry_wet[key]), f'Source first-frame wet map {key} is not dry'
    for frame in range(1, 97):
        particle_path = args.out / 'particles' / f'frame_{frame:04d}.npz'
        if frame < event_frame:
            os.link(args.source / 'particles' / particle_path.name, particle_path)
            for kind in ('water', 'spray', 'mist', 'foam', 'beads', 'wet'):
                name = f'{kind}_{frame:04d}.npz'
                os.link(args.source / 'aniso' / name, args.out / 'aniso' / name)
            os.link(args.source / 'render' / f'{frame:04d}.png', args.out / 'render' / f'{frame:04d}.png')
            report['frames'].append({**ref['frames'][frame - 1], 'water_present': True, 'prefix_reused': True})
            continue
        if frame > event_frame:
            for _ in range(info['substeps_per_frame']):
                solver.apply_ball_external()
                solver.advance_ball()
        state = solver.ball.to_numpy()
        assert np.isfinite(state).all()
        assert not np.any(solver.audit.to_numpy())
        assert not np.any(solver.pressure_impulse.to_numpy())
        assert not np.any(solver.viscous_force.to_numpy())
        np.savez(particle_path, ball_center=state[0], ball_velocity=state[1],
                 water_pos=np.empty((0, 3), np.float32), water_vel=np.empty((0, 3), np.float16),
                 water_active_count=np.array(0, np.int32))
        np.savez(args.out / 'aniso' / f'water_{frame:04d}.npz', **empty_water)
        np.savez(args.out / 'aniso' / f'wet_{frame:04d}.npz', **dry_wet)
        for kind in ('spray', 'mist', 'foam', 'beads'):
            with np.load(args.source / 'aniso' / f'{kind}_0001.npz') as data:
                empty = {k: np.empty((0,) + data[k].shape[1:], data[k].dtype) for k in data.files}
            np.savez(args.out / 'aniso' / f'{kind}_{frame:04d}.npz', **empty)
        report['frames'].append({'frame': frame, 'time_s': (frame - 1) / source.FPS,
            'ball_center': state[0].tolist(), 'ball_velocity': state[1].tolist(),
            'water_present': False, 'water_active_count': 0,
            'ball_pressure_impulse': [0, 0, 0], 'ball_viscous_impulse': [0, 0, 0],
            'floor_contacts': int(solver.contacts[None])})
        if frame == event_frame or frame % 12 == 0:
            print('DRY_FRAME', frame, state.tolist(), flush=True)
    os.link(args.source / 'ground.npz', args.out / 'ground.npz')
    report['status'] = 'complete'
    report['wall_seconds'] = time.monotonic() - started
    report['final_active_counts'] = [int(e.get_particles_active().sum().item()) for e in solver.entities]
    source.save_json(args.out / 'simulation_report.json', report)
    source.save_json(args.out / 'config_diff.json', {'before': before, 'after': after})
    print('COMPLETE', args.case, report['wall_seconds'], flush=True)


if __name__ == '__main__':
    main()
