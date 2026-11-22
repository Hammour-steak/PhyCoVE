"""Water surface and splash detail of a simulated run, reusing the elastic-duck splash stage.

Anisotropic-kernel water surface plus spray, mist and foam, exactly as splash_elastic_fluid_duck.py
computes them. The duck's per-particle counts were set for its 3.47 cm particles (33.5 g each); here
they scale with particle mass, and the churn-foam rate with the surface particle density, so a given
volume of torn or churning water makes the same spray and foam at any resolution. The rigid ball
stands in for the duck's material points (droplets land on it; foam is not left inside it).

Writes <run>/aniso/water_####.npz, spray_/mist_/foam_####.npz and report_<part>.json.
"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import REPO
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse
import json
import math
import sys
import time
from pathlib import Path

import numba
import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# The splash stage of elastic_fluid_duck is reused as it is; a change to that module changes this scene too.
DUCK_PHYSICS = REPO / 'scripts/elastic_fluid/elastic_fluid_duck/physics'
sys.path.insert(0, str(DUCK_PHYSICS))
import optics_bowling_ball_pool_drop as optics  # noqa: E402
import splash_elastic_fluid_duck as duck  # noqa: E402

DUCK_DX = 0.034722222222222224
FLOOR = -1.25
BALL_RADIUS = 0.075
BALL_POINTS = 1200
WALL_MIRROR = 3.0  # particles this many smoothing lengths inside a wall are mirrored across it


def ball_points(center):
    index = np.arange(BALL_POINTS) + 0.5
    polar = np.arccos(1 - 2 * index / BALL_POINTS)
    azimuth = math.pi * (1 + 5 ** 0.5) * index
    unit = np.stack([np.cos(azimuth) * np.sin(polar), np.sin(azimuth) * np.sin(polar), np.cos(polar)], 1)
    return np.asarray(center, dtype=np.float64) + BALL_RADIUS * unit


def frame_list(text):
    return sorted({frame for part in text.split(',') for frame in range(int(part.split('-')[0]), int(part.split('-')[-1]) + 1)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--frames', default='1-30', help='Frames whose spray, mist and foam are written.')
    parser.add_argument('--surfaces', help='Frames whose surface this process meshes (default: --frames).')
    parser.add_argument('--write-particles', action='store_true', help='This process writes spray/mist/foam.')
    parser.add_argument('--part', default='0')
    args = parser.parse_args()
    numba.set_num_threads(min(32, numba.config.NUMBA_NUM_THREADS))
    wanted = frame_list(args.frames)
    surfaces = set(frame_list(args.surfaces)) if args.surfaces else set(wanted)
    run = args.run.resolve()
    info = json.loads((run / 'simulation_report.json').read_text())['info']
    dx = info['dx_m']
    h = 2 * dx
    corners = optics.container(info)
    lower = np.array([*corners.min(axis=0), FLOOR])
    upper = np.array([*corners.max(axis=0), info['domain_top_m']])
    with np.load(run / 'particles' / 'frame_0001.npz') as data:
        still_level = float(np.percentile(data['water_pos'][:, 2], 99.5)) + dx / 2
    mass, area = (dx / DUCK_DX) ** 3, (dx / DUCK_DX) ** 2
    counts_per = {'drops_per_torn': duck.DROPS_PER_TORN * mass, 'mist_per_torn': duck.MIST_PER_TORN * mass,
                  'shed_per_frame': duck.SHED_PER_FRAME * mass, 'mist_per_frame': duck.MIST_PER_FRAME * mass,
                  'foam_rate': duck.FOAM_RATE * area}
    out = run / 'aniso'
    out.mkdir(exist_ok=True)
    report = {'dx_m': dx, 'still_level_m': still_level, 'scaled_counts': counts_per,
              'duck_stage': str(Path(duck.__file__).resolve()), 'frames': {}}
    report_path = out / f'report_{args.part}.json'
    drops = duck.Flying(dx, duck.DROP_RADIUS)
    mist = duck.Flying(dx, duck.MIST_RADIUS, terminal=duck.MIST_TERMINAL, life=duck.MIST_LIFE)
    foam = duck.Foam()
    converted = None
    last = max(max(wanted), max(surfaces))
    for frame in range(1, last + 1):
        tick = time.monotonic()
        with np.load(run / 'particles' / f'frame_{frame:04d}.npz') as data:
            x, v = data['water_pos'].astype(np.float64), data['water_vel'].astype(np.float64)
            present = bool(data['ball_present']) if 'ball_present' in data else True
            ball = ball_points(data['ball_center']) if present else np.empty((0, 3), np.float64)
        converted = np.zeros(len(x), bool) if converted is None else converted
        tree = cKDTree(x)
        counts = tree.query_ball_point(x, .999 * h, return_length=True, workers=duck.WORKERS) - 1
        heights = duck.Heights(np.concatenate([x[counts >= 9], ball]) + [0, 0, dx / 2], lower, upper, still_level)
        torn = duck.torn_particles(tree, x, counts, h)
        surface_now = duck.Surface(x, v, counts, still_level, dx)
        rng = np.random.default_rng(duck.SEED + frame)
        if frame > 1:
            drops.advance(1 / duck.FPS)
            mist.advance(1 / duck.FPS)
            foam.advance(1 / duck.FPS, surface_now, ball, lower, upper)
        landed = drops.cull(heights, lower, upper)
        mist.cull(heights, lower, upper)
        foam.spawn(landed[rng.uniform(size=len(landed)) < duck.FOAM_FROM_LANDING], surface_now, rng, duck.FOAM_LANDING_PATCH)
        clearance = x[:, 2] - heights(x)
        new = torn & ~converted & (clearance > 0)
        converted = (converted | new) & torn
        speed = np.linalg.norm(v, axis=1)
        energy = np.clip((speed[new] - duck.SPRAY_SPEED[0]) / (duck.SPRAY_SPEED[1] - duck.SPRAY_SPEED[0]), 0, 1) \
            * (clearance[new] > duck.SPRAY_MIN_HEIGHT)
        drops.emit(x[new], v[new], rng.poisson(counts_per['drops_per_torn'] * energy), rng,
                   duck.DROP_ALONG, duck.DROP_ACROSS, duck.DROP_SPREAD, duck.DROP_STRETCH)
        mist.emit(x[new], v[new], rng.poisson(counts_per['mist_per_torn'] * energy), rng, .5, 1., duck.MIST_SPREAD, .2,
                  duck.MIST_SLOWDOWN)
        shedding = (~converted & (counts >= 1) & (counts <= duck.SHED_NEIGHBOURS) & (speed > duck.SHED_MIN_SPEED)
                    & (x[:, 2] > still_level + duck.SHED_HEIGHT))
        rate = np.clip(speed[shedding] / 3, 0, 1.5)
        drops.emit(x[shedding], v[shedding], rng.poisson(counts_per['shed_per_frame'] * rate), rng,
                   duck.DROP_ALONG, duck.DROP_ACROSS, duck.DROP_SPREAD, duck.DROP_STRETCH)
        mist.emit(x[shedding], v[shedding], rng.poisson(counts_per['mist_per_frame'] * rate), rng, .5, 1.,
                  duck.MIST_SPREAD, .2, duck.MIST_SLOWDOWN)
        top, _ = surface_now.sample(surface_now.points[:, :2])
        layer = surface_now.points[:, 2] > top - dx / 2 - .02
        points, flow = surface_now.points[layer], surface_now.velocity[layer]
        _, neighbour = cKDTree(points).query(points, k=9, workers=duck.WORKERS)
        churn = np.linalg.norm(flow[neighbour[:, 1:]] - flow[:, None, :], axis=2).mean(axis=1)
        churn = rng.poisson(counts_per['foam_rate'] * np.clip((churn - duck.FOAM_CHURN[0]) / (duck.FOAM_CHURN[1] - duck.FOAM_CHURN[0]), 0, 1))
        foam.spawn(np.repeat(points, churn, axis=0), surface_now, rng, duck.FOAM_PATCH)
        foam.advance(0., surface_now, ball, lower, upper)
        record = {'torn_new': int(new.sum()), 'hidden': int(converted.sum()), 'shedding': int(shedding.sum()),
                  'drops': len(drops.radius), 'mist': len(mist.radius), 'foam': len(foam.radius)}
        if args.write_particles and frame in wanted:
            drops.save(out / f'spray_{frame:04d}.npz')
            mist.save(out / f'mist_{frame:04d}.npz')
            foam.save(out / f'foam_{frame:04d}.npz')
        if frame in surfaces:
            # Mirror images across the walls give the surface the support a wall gives real water, so it
            # meets the wall level instead of rounding off like a free edge.
            kept, flow = x[~converted], v[~converted]
            images, image_flow = optics.mirror(kept, flow, corners, WALL_MIRROR * h)
            mesh, stats = duck.surface(np.concatenate([kept, images]), np.concatenate([flow, image_flow]), h, dx, still_level)
            stats['wall_images'] = len(images)
            np.savez(out / f'water_{frame:04d}.npz', **mesh)
            record['surface'] = stats
        record['seconds'] = time.monotonic() - tick
        report['frames'][str(frame)] = record
        duck.save(report_path, report)
        print('SPLASH', args.part, frame, json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
