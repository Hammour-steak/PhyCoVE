"""Sunlight on the pool floor and walls for render_elastic_fluid_duck.py, with caustics traced through the
simulated water surface.

Parallel sunlight (optics.SUN_TO) enters the water surface reconstructed by splash_elastic_fluid_duck.py, with
the fine ripples of optics_elastic_fluid_duck.py on top: Snell refraction and Schlick Fresnel transmission, shadows of
the pool walls, the ladder, the duck and the surface foam, and absorption on the way down. Where the
light lands on the pool shell it is collected per texture pixel; the sun-facing walls above the water
get the direct sun. Each texture holds the sun irradiance per colour channel relative to a surface
facing the sun. render_elastic_fluid_duck.py turns it into the tiles' sunlit colour, and the sun lamp does not light
the shell itself.

Writes runs/source/aniso/caustics_####.npz (an RGB array per shell object, optics.shell_textures
layout) and caustics_report.json. Needs runs/source/aniso/occluders.npz from render_elastic_fluid_duck.py --occluders.
"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
import argparse
import hashlib
import json
from pathlib import Path

import numba
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

import optics_elastic_fluid_duck as optics

RAY_SPACING = .0025     # m between sun rays on the water, jittered within their cell
SURFACE_PIECE = .02     # water pieces under this share of the vertices (drops, torn sheets) let the light pass
LAYER = .05             # top layer: surface points within this of the highest of their neighbours
NEIGHBOURS = 32
# Gaussian scale (m) of the surface the light refracts at. Bumps of a single 3.5 cm particle that
# fell back onto the water are below the simulation's resolution; unsmoothed they focus the light
# into sharp dark discs on the floor that persist for many frames.
SURFACE_SMOOTHING = .02
SURFACE_GAP = .03       # rays farther than this from any top surface point find no water
FOAM_SHADOW = .5        # share of the light that fully opaque foam takes away
WATERLINE_BAND = .03    # surface points this close to a wall give its waterline
BLUR = 1.               # texture pixels: the sun disc (0.6 deg over the 1.3 m depth) and ray noise
SEED = 11
WORKERS = 16
FACES = ('PoolFloor', 'PoolBack', 'PoolFront', 'PoolLeft', 'PoolRight')


@numba.njit(parallel=True, cache=True)
def segment_hits(start, direction, length, corner, edge1, edge2):
    """Whether each segment start + s*direction, 0 < s < length, crosses a triangle (Moller-Trumbore)."""
    hit = np.zeros(len(start), np.bool_)
    for i in numba.prange(len(start)):
        ox, oy, oz = start[i, 0], start[i, 1], start[i, 2]
        dx, dy, dz = direction[i, 0], direction[i, 1], direction[i, 2]
        for j in range(len(corner)):
            ax, ay, az = edge1[j, 0], edge1[j, 1], edge1[j, 2]
            bx, by, bz = edge2[j, 0], edge2[j, 1], edge2[j, 2]
            px, py, pz = dy*bz-dz*by, dz*bx-dx*bz, dx*by-dy*bx
            det = ax*px+ay*py+az*pz
            if abs(det) < 1e-14:
                continue
            inverse = 1./det
            tx, ty, tz = ox-corner[j, 0], oy-corner[j, 1], oz-corner[j, 2]
            u = (tx*px+ty*py+tz*pz)*inverse
            if u < 0. or u > 1.:
                continue
            qx, qy, qz = ty*az-tz*ay, tz*ax-tx*az, tx*ay-ty*ax
            v = (dx*qx+dy*qy+dz*qz)*inverse
            if v < 0. or u+v > 1.:
                continue
            s = (bx*qx+by*qy+bz*qz)*inverse
            if 1e-6 < s < length[i]:
                hit[i] = True
                break
    return hit


def crosses(start, direction, length, triangles):
    """Whether each segment start + s*direction, 0 < s < length, crosses one of the triangles (T, 3, 3).
    Only segments that pass through the triangles' bounding box are tested."""
    lower, upper = triangles.min(axis=(0, 1))-.005, triangles.max(axis=(0, 1))+.005
    rise = np.where(np.abs(direction[:, 2]) < 1e-9, 1e-9, direction[:, 2])
    s0, s1 = (lower[2]-start[:, 2])/rise, (upper[2]-start[:, 2])/rise
    first, last = np.clip(np.minimum(s0, s1), 0, length), np.clip(np.maximum(s0, s1), 0, length)
    a, b = start+first[:, None]*direction, start+last[:, None]*direction
    near = last > first
    for axis in (0, 1):
        near &= (np.minimum(a[:, axis], b[:, axis]) < upper[axis]) & (np.maximum(a[:, axis], b[:, axis]) > lower[axis])
    hit = np.zeros(len(start), bool)
    if near.any():
        hit[near] = segment_hits(np.ascontiguousarray(start[near]), np.ascontiguousarray(direction[near]),
                                 np.ascontiguousarray(length[near]), np.ascontiguousarray(triangles[:, 0]),
                                 np.ascontiguousarray(triangles[:, 1]-triangles[:, 0]),
                                 np.ascontiguousarray(triangles[:, 2]-triangles[:, 0]))
    return hit


def entry_surface(path, floor):
    """Upward-facing vertices of the large water pieces: the surface where the sunlight enters."""
    with np.load(path) as mesh:
        vertices, triangles = mesh['vertices'].astype(np.float64), mesh['triangles']
        normals = mesh['normals'].astype(np.float64)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    count = len(vertices)
    edges = np.concatenate([triangles[:, :2], triangles[:, 1:]])
    graph = coo_matrix((np.ones(len(edges), np.int8), (edges[:, 0], edges[:, 1])), shape=(count, count))
    _, piece = connected_components(graph, directed=False)
    large = np.bincount(piece)[piece] >= SURFACE_PIECE*count
    top = large & (normals[:, 2] > .3) & (vertices[:, 2] > floor+.2)
    return vertices[top], normals[top]


def sample_surface(points, up, x, y):
    """Height and normal of the surface's top layer above each ray (Gaussian-weighted over
    SURFACE_SMOOTHING), and the distance to the nearest top surface point."""
    tree = cKDTree(points[:, :2])
    height, normal, gap = np.empty(len(x)), np.empty((len(x), 3)), np.empty(len(x))
    for begin in range(0, len(x), 400_000):
        part = slice(begin, begin+400_000)
        distance, index = tree.query(np.column_stack([x[part], y[part]]), k=NEIGHBOURS, workers=WORKERS)
        z = points[index, 2]
        weight = (z >= z.max(axis=1, keepdims=True)-LAYER)*np.exp(-.5*(distance/SURFACE_SMOOTHING)**2)
        weight[:, 0] += 1e-30  # rays far from any water
        height[part] = (weight*z).sum(axis=1)/weight.sum(axis=1)
        normal[part] = np.einsum('nk,nkd->nd', weight, up[index])
        gap[part] = distance[:, 0]
    return height, normal/np.linalg.norm(normal, axis=1, keepdims=True), gap


def land(start, direction, lower, upper):
    """Distance along each ray to the first pool shell face it reaches, and that face's index in FACES."""
    with np.errstate(divide='ignore', invalid='ignore'):
        times = np.stack([np.where(direction[:, 2] < 0, (lower[2]-start[:, 2])/direction[:, 2], np.inf),
                          np.where(direction[:, 1] > 0, (upper[1]-start[:, 1])/direction[:, 1], np.inf),
                          np.where(direction[:, 1] < 0, (lower[1]-start[:, 1])/direction[:, 1], np.inf),
                          np.where(direction[:, 0] < 0, (lower[0]-start[:, 0])/direction[:, 0], np.inf),
                          np.where(direction[:, 0] > 0, (upper[0]-start[:, 0])/direction[:, 0], np.inf)], axis=1)
    times[~(times >= 0)] = np.inf
    face = np.argmin(times, axis=1)
    return times[np.arange(len(start)), face], face


def sunlight(frame, run, rays, lower, upper, layout, occluders, duck_poses, fps):
    """The frame's sun irradiance textures (name -> (rows, cols, 3)) and a few numbers for the report."""
    gx, gy = rays
    light = -np.asarray(optics.SUN_TO)/np.linalg.norm(optics.SUN_TO)   # direction the sunlight travels
    points, up = entry_surface(run/'aniso'/f'water_{frame:04d}.npz', lower[2])
    surface_z, normal, water_gap = sample_surface(points, up, gx, gy)
    tilt_x, tilt_y = optics.ripple_tilt(gx, gy, (frame-1)/fps)
    normal[:, 0] += normal[:, 2]*tilt_x
    normal[:, 1] += normal[:, 2]*tilt_y
    normal /= np.linalg.norm(normal, axis=1, keepdims=True)
    # Snell and Schlick; power per ray is the sun's flux through its patch of horizontal area.
    cosine = np.clip(-(normal@light), 0, 1)
    eta = 1/optics.IOR
    direction = eta*light+(eta*cosine-np.sqrt(1-eta**2*(1-cosine**2)))[:, None]*normal
    r0 = ((optics.IOR-1)/(optics.IOR+1))**2
    power = (1-r0-(1-r0)*(1-cosine)**5)*cosine/np.maximum(normal[:, 2], .3)
    power[water_gap > SURFACE_GAP] = 0
    start = np.column_stack([gx, gy, surface_z])
    length, face = land(start, direction, lower, upper)
    power[~np.isfinite(length)] = 0
    # Shadows: the walls' tops, then the ladder and the duck above (towards the sun) and below the water.
    to_sun = -light
    shade = np.zeros(len(gx), bool)
    for axis in (0, 1):
        wall = lower[axis] if to_sun[axis] < 0 else upper[axis]
        shade |= start[:, 2]+(wall-start[:, axis])/to_sun[axis]*to_sun[2] < optics.SHELL_TOP
    upward = np.broadcast_to(to_sun, start.shape)
    groups = [occluders['static_triangles'][occluders['static_owner'] == owner]
              for owner in range(len(occluders['static_names']))]
    if duck_poses is not None:
        groups.append(duck_poses[frame-1][occluders['duck_triangles']].astype(np.float64))
    open_water = np.where(np.isfinite(length), length-1e-4, 0.)
    for triangles in groups:
        shade |= crosses(start, upward, np.full(len(gx), 50.), triangles)
        shade |= crosses(start, direction, open_water, triangles)
    power[shade] = 0
    with np.load(run/'aniso'/f'foam_{frame:04d}.npz') as foam:
        position, radius = foam['position'], foam['radius']
        fade = foam['fade'] if 'fade' in foam.files else np.ones(len(radius), np.float32)
    if len(position):
        gap, which = cKDTree(position[:, :2]).query(np.column_stack([gx, gy]), distance_upper_bound=float(radius.max()),
                                                    workers=WORKERS)
        under = np.isfinite(gap)
        under[under] = gap[under] < radius[which[under]]
        power[under] *= 1-FOAM_SHADOW*fade[which[under]]
    # Collect the light where it lands, dimmed by the water it crossed.
    hit = start+np.where(np.isfinite(length), length, 0)[:, None]*direction
    sigma = optics.absorption()
    textures = {}
    for number, name in enumerate(FACES):
        u, v, (u0, _), (v0, _), (rows, cols) = layout[name]
        pick = (face == number) & (power > 0)
        cell = np.clip(((hit[pick, v]-v0)/optics.SHELL_PIXEL).astype(int), 0, rows-1)*cols \
            + np.clip(((hit[pick, u]-u0)/optics.SHELL_PIXEL).astype(int), 0, cols-1)
        energy = power[pick, None]*np.exp(-length[pick, None]*sigma)
        textures[name] = np.stack([np.bincount(cell, weights=energy[:, c], minlength=rows*cols) for c in range(3)],
                                  axis=-1).reshape(rows, cols, 3)*(RAY_SPACING/optics.SHELL_PIXEL)**2
    # Direct sun on the walls above the water line.
    for name in FACES[1:]:
        inward = np.asarray(optics.SHELL_INWARD[name], float)
        facing = float(inward@to_sun)
        if facing <= 0:
            continue
        u, v, (u0, _), (v0, _), (rows, cols) = layout[name]
        axis = int(np.flatnonzero(inward)[0])
        wall = lower[axis] if inward[axis] > 0 else upper[axis]
        rim = points[np.abs(points[:, axis]-wall) < WATERLINE_BAND]
        level = np.full(cols, -np.inf)
        np.maximum.at(level, np.clip(((rim[:, u]-u0)/optics.SHELL_PIXEL).astype(int), 0, cols-1), rim[:, 2])
        known = np.isfinite(level)
        assert known.any(), f'no water surface along {name}'
        level = np.interp(np.arange(cols), np.flatnonzero(known), level[known])
        bottom = v0+np.arange(rows)*optics.SHELL_PIXEL
        dry = np.clip((bottom[:, None]+optics.SHELL_PIXEL-level[None, :])/optics.SHELL_PIXEL, 0, 1)
        textures[name] += facing*dry[..., None]
    for name in FACES:
        textures[name] = gaussian_filter(textures[name], (BLUR, BLUR, 0)).astype(np.float32)
    floor = textures['PoolFloor'][50:-50, 50:-50].mean(axis=-1)
    stats = {'floor_mean': round(float(floor.mean()), 3), 'floor_p99': round(float(np.percentile(floor, 99)), 3),
             'floor_max': round(float(floor.max()), 3), 'rays_in_water': round(float((water_gap <= SURFACE_GAP).mean()), 4),
             'rays_shaded': round(float(shade.mean()), 4)}
    return textures, stats


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-dir', type=Path, required=True)
    parser.add_argument('--frames', default='1-96', help='Frames to write, e.g. 9-32 or 1,13,60.')
    args = parser.parse_args()
    wanted = sorted({frame for part in args.frames.split(',')
                     for frame in range(int(part.split('-')[0]), int(part.split('-')[-1])+1)})
    case = args.case_dir.resolve()
    run = case/'runs/source'
    spec = json.loads((case/'mpm_sph_experiment.json').read_text())
    assert spec['physics'].get('water_presence', [1]) == [1], 'No water in this case: the sun lights the empty pool directly.'
    q = spec['simulation_quality']
    lower, upper = np.asarray(q['sph_lower_bound_m'], float), np.asarray(q['sph_upper_bound_m'], float)
    occluder_path = run/'aniso/occluders.npz'
    settings = json.loads(json.dumps({
        'ray_spacing': RAY_SPACING, 'surface_piece': SURFACE_PIECE, 'layer': LAYER, 'neighbours': NEIGHBOURS,
        'surface_smoothing': SURFACE_SMOOTHING, 'surface_gap': SURFACE_GAP,
        'foam_shadow': FOAM_SHADOW, 'waterline_band': WATERLINE_BAND, 'blur': BLUR, 'seed': SEED,
        'sun_to': optics.SUN_TO, 'ior': optics.IOR, 'water_absorption': optics.WATER_ABSORPTION,
        'ripples': (optics.RIPPLE_COUNT, optics.RIPPLE_WAVELENGTHS, optics.RIPPLE_RMS_SLOPE, optics.RIPPLE_WIND,
                    optics.RIPPLE_SPREAD, optics.RIPPLE_SEED), 'shell_pixel': optics.SHELL_PIXEL,
        'shell_top': optics.SHELL_TOP, 'occluders_sha256': digest(occluder_path),
        'splash_detail_settings': json.loads((run/'aniso/report.json').read_text())['settings']}))
    report_path = run/'aniso/caustics_report.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else None
    if not report or report['settings'] != settings:
        report = {'settings': settings, 'frames': {}}
    layout = optics.shell_textures(lower, upper)
    rng = np.random.default_rng(SEED)
    gx, gy = np.meshgrid(np.arange(lower[0], upper[0]-1e-9, RAY_SPACING), np.arange(lower[1], upper[1]-1e-9, RAY_SPACING))
    rays = (gx.ravel()+rng.uniform(0, RAY_SPACING, gx.size), gy.ravel()+rng.uniform(0, RAY_SPACING, gy.size))
    with np.load(occluder_path) as data:
        occluders = {key: data[key] for key in data.files}
    duck_poses = None  # a deleted duck casts no shadow
    if spec['physics'].get('duck_presence', [1]) == [1]:
        with np.load(run/'visual_deformation.npz') as data:
            duck_poses = data['positions']
    numba.set_num_threads(min(WORKERS, numba.config.NUMBA_NUM_THREADS))
    for frame in wanted:
        path = run/'aniso'/f'caustics_{frame:04d}.npz'
        if path.exists() and str(frame) in report['frames']:
            continue
        textures, stats = sunlight(frame, run, rays, lower, upper, layout, occluders, duck_poses, spec['render']['fps'])
        temporary = path.with_name(path.stem+'.tmp.npz')
        np.savez_compressed(temporary, **textures)
        temporary.replace(path)
        report['frames'][str(frame)] = stats
        temporary = report_path.with_name(report_path.name+'.tmp')
        temporary.write_text(json.dumps(report, indent=2))
        temporary.replace(report_path)
        print('CAUSTICS', frame, json.dumps(stats), flush=True)


if __name__ == '__main__':
    main()
