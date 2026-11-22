"""Sunlight on the tank floor and walls for render_bowling_ball_pool_drop.py, traced through the
simulated water.

The elastic-duck caustics (caustics_elastic_fluid_duck.py) for the bowling pool: parallel sunlight
from the fitted sun enters the anisotropic water surface of splash_bowling_ball_pool_drop.py with
Snell refraction and Schlick transmission, and is absorbed on its way to the tank, where it is
collected per texture pixel. The tank is the pool opening's parallelogram prism
(optics_bowling_ball_pool_drop.py); rays start inside it. Shadows: the authored windows, walls and
deck and the tank walls (static visibility from sun_visibility_bowling_ball_pool_drop.py), the ball
above and below the water, and the surface foam. Sun-facing walls above the water line get
the direct sun where the windows let it through. Each texture holds the sun irradiance per colour
channel relative to a surface facing the sun.

Writes <run>/aniso/caustics_####.npz and caustics_report.json.
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
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# The caustics stage of elastic_fluid_duck (and the optics module it imports) is reused as it is; a change
# to those modules changes this scene too.
DUCK_PHYSICS = REPO / 'scripts/elastic_fluid/elastic_fluid_duck/physics'
sys.path.insert(0, str(DUCK_PHYSICS))
import optics_bowling_ball_pool_drop as optics  # noqa: E402
import caustics_elastic_fluid_duck as duck  # noqa: E402

RAY_SPACING = duck.RAY_SPACING
SURFACE_GAP = duck.SURFACE_GAP
FOAM_SHADOW = duck.FOAM_SHADOW
BLUR = duck.BLUR
SEED = duck.SEED
BALL_RADIUS = .075


def sphere_hit(start, direction, length, centre, radius):
    """Whether each segment start + s*direction, 0 < s < length, passes through the sphere."""
    offset = start - centre
    b = np.einsum('nd,nd->n', offset, direction)
    c = np.einsum('nd,nd->n', offset, offset) - radius * radius
    disc = b * b - c
    root = np.sqrt(np.maximum(disc, 0.))
    return (disc > 0) & (-b - root < length) & (-b + root > 1e-6)


def frame_list(text):
    return sorted({f for part in text.split(',') for f in range(int(part.split('-')[0]), int(part.split('-')[-1]) + 1)})


def sunlight(frame, run, rays, visibility, layout, corners):
    gx, gy = rays
    to_sun = np.asarray(optics.TO_SUN) / np.linalg.norm(optics.TO_SUN)
    light = -to_sun
    # The surface carries its mirror images past the walls, so rays next to a wall sample a whole surface.
    points, up = duck.entry_surface(run / 'aniso' / f'water_{frame:04d}.npz', optics.FLOOR)
    surface_z, normal, water_gap = duck.sample_surface(points, up, gx, gy)
    cosine = np.clip(-(normal @ light), 0, 1)
    eta = 1 / optics.IOR
    direction = eta * light + (eta * cosine - np.sqrt(1 - eta ** 2 * (1 - cosine ** 2)))[:, None] * normal
    r0 = ((optics.IOR - 1) / (optics.IOR + 1)) ** 2
    power = (1 - r0 - (1 - r0) * (1 - cosine) ** 5) * cosine / np.maximum(normal[:, 2], .3)
    power[water_gap > SURFACE_GAP] = 0
    start = np.column_stack([gx, gy, surface_z])
    length, face = optics.land(start, direction, corners)
    power[~np.isfinite(length)] = 0
    # Windows, walls, coping and deck between the water and the sun.
    power *= visibility['water'][optics.texel(np.column_stack([gx, gy, np.full_like(gx, optics.FLOOR)]),
                                              layout['PoolFloor'])]
    # The ball, towards the sun above the water and along the refracted ray below it.
    with np.load(run / 'particles' / f'frame_{frame:04d}.npz') as data:
        centre = data['ball_center'].astype(np.float64)
        ball_present = bool(data['ball_present']) if 'ball_present' in data else True
    open_water = np.where(np.isfinite(length), length - 1e-4, 0.)
    shade = np.zeros(len(gx), dtype=bool)
    if ball_present:
        shade = sphere_hit(start, np.broadcast_to(to_sun, start.shape), np.full(len(gx), 60.), centre, BALL_RADIUS)
        shade |= sphere_hit(start, direction, open_water, centre, BALL_RADIUS)
    power[shade] = 0
    with np.load(run / 'aniso' / f'foam_{frame:04d}.npz') as foam:
        position, radius, fade = foam['position'], foam['radius'], foam['fade']
    if len(position):
        gap, which = cKDTree(position[:, :2]).query(np.column_stack([gx, gy]), distance_upper_bound=float(radius.max()),
                                                    workers=duck.WORKERS)
        under = np.isfinite(gap)
        under[under] = gap[under] < radius[which[under]]
        power[under] *= 1 - FOAM_SHADOW * fade[which[under]]
    hit = start + np.where(np.isfinite(length), length, 0)[:, None] * direction
    sigma = optics.absorption()
    textures = {}
    wall_normal, wall_offset = optics.planes(corners)
    for number, name in enumerate(optics.FACES):
        _, _, _, _, (rows, cols) = layout[name]
        pick = (face == number) & (power > 0)
        row, column = optics.texel(hit[pick], layout[name])
        energy = power[pick, None] * np.exp(-length[pick, None] * sigma)
        textures[name] = np.stack([np.bincount(row * cols + column, weights=energy[:, c], minlength=rows * cols)
                                   for c in range(3)], axis=-1).reshape(rows, cols, 3) * (RAY_SPACING / optics.SHELL_PIXEL) ** 2
    # Direct sun on the sun-facing walls above this frame's water line, where the windows let it in.
    for k, name in enumerate(optics.FACES[1:]):
        facing = float(optics.inward(name, corners) @ to_sun)
        if facing <= 0:
            continue
        origin, u, _, _, (rows, cols) = layout[name]
        rim = points[np.abs(wall_offset[k] - points[:, :2] @ wall_normal[k]) < duck.WATERLINE_BAND + .01]
        level = np.full(cols, -np.inf)
        np.maximum.at(level, np.clip((((rim - origin) @ u) / optics.SHELL_PIXEL).astype(int), 0, cols - 1), rim[:, 2])
        known = np.isfinite(level)
        if not known.any():
            continue
        level = np.interp(np.arange(cols), np.flatnonzero(known), level[known])
        bottom = optics.FLOOR + np.arange(rows) * optics.SHELL_PIXEL
        dry = np.clip((bottom[:, None] + optics.SHELL_PIXEL - level[None, :]) / optics.SHELL_PIXEL, 0, 1)
        textures[name] += (facing * dry * visibility[name])[..., None]
    for name in optics.FACES:
        textures[name] = gaussian_filter(textures[name], (BLUR, BLUR, 0)).astype(np.float32)
    floor = textures['PoolFloor'].mean(axis=-1)
    stats = {'floor_mean': round(float(floor.mean()), 4), 'floor_p99': round(float(np.percentile(floor, 99)), 3),
             'floor_max': round(float(floor.max()), 3), 'rays_in_water': round(float((water_gap <= SURFACE_GAP).mean()), 4),
             'rays_sunlit': round(float((power > 0).mean()), 4), 'ball_shaded': int(shade.sum())}
    return textures, stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--visibility', type=Path, required=True)
    parser.add_argument('--frames', default='1-96')
    parser.add_argument('--part', default='', help='Report name suffix when frames are split over processes.')
    args = parser.parse_args()
    run = args.run.resolve()
    corners = optics.container(json.loads((run / 'simulation_report.json').read_text())['info'])
    layout = optics.faces(corners)
    with np.load(args.visibility) as data:
        visibility = {key: data[key] for key in data.files}
    assert np.allclose(visibility['to_sun'], optics.TO_SUN) and np.allclose(visibility['corners'], corners)
    lower, upper = corners.min(axis=0), corners.max(axis=0)
    rng = np.random.default_rng(SEED)
    gx, gy = np.meshgrid(np.arange(lower[0], upper[0] - 1e-9, RAY_SPACING), np.arange(lower[1], upper[1] - 1e-9, RAY_SPACING))
    gx, gy = gx.ravel() + rng.uniform(0, RAY_SPACING, gx.size), gy.ravel() + rng.uniform(0, RAY_SPACING, gy.size)
    inside = optics.wall_distance(np.column_stack([gx, gy]), corners) > 0
    rays = (gx[inside], gy[inside])
    report_path = run / 'aniso' / f'caustics_report{args.part}.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else {'frames': {}}
    report['settings'] = {'to_sun': optics.TO_SUN, 'ray_spacing': RAY_SPACING, 'shell_pixel': optics.SHELL_PIXEL,
                          'visibility_level_m': float(visibility['level']), 'water_absorption': optics.WATER_ABSORPTION}
    for frame in frame_list(args.frames):
        textures, stats = sunlight(frame, run, rays, visibility, layout, corners)
        path = run / 'aniso' / f'caustics_{frame:04d}.npz'
        temporary = path.with_name(path.stem + '.tmp.npz')
        np.savez_compressed(temporary, **textures)
        temporary.replace(path)
        report['frames'][str(frame)] = stats
        report_path.write_text(json.dumps(report, indent=1))
        print('CAUSTICS', frame, json.dumps(stats), flush=True)


if __name__ == '__main__':
    main()
