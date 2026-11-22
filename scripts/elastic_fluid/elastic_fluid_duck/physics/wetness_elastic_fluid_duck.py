"""Wet surfaces for render_elastic_fluid_duck.py, from the simulated water: the band of pool wall above the
water line that the water has wetted, and the parts of the duck the water has touched. Surfaces stay
wet once touched (drying takes minutes; the clip lasts 4 s).

For every frame up to the last wanted one it finds the water line along each pool wall (the highest
upward-facing water surface within WATERLINE_BAND of the wall, per texture column) and the duck
vertices within DUCK_REACH of the water. The history uses the baseline surface meshes, which exist for
every frame; the current water line uses the rendered surface of splash_elastic_fluid_duck.py, so the wet band
starts right at the water you see. Writes runs/source/aniso/wet_####.npz (per pool wall a (rows, cols)
wet-film texture in the optics.shell_textures layout, 1 on wet tiles above the water, and 'duck', the
wetness of each duck_visual vertex) and wet_report.json.
"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter
from scipy.spatial import cKDTree

import optics_elastic_fluid_duck as optics

WATERLINE_BAND = .03   # m: upward-facing water surface this close to a wall gives its water line
CORNER = .04           # m: the reconstructed surface rises along the pool's vertical corners; skip those columns
WET_BAND = .03         # m above the highest water line so far that is wet too (meniscus, small waves)
WET_FADE = .015        # m: wet to dry at the top of the band
DUCK_REACH = .04       # m: duck surface this close to the water gets wet
WORKERS = 16
WALLS = ('PoolBack', 'PoolFront', 'PoolLeft', 'PoolRight')


def load_surface(path):
    """Vertices and unit vertex normals of a water surface mesh (normals from the faces if not stored)."""
    with np.load(path) as mesh:
        vertices, triangles = mesh['vertices'].astype(np.float64), mesh['triangles']
        normals = mesh['normals'].astype(np.float64) if 'normals' in mesh.files else None
    if normals is None:
        faces = np.cross(vertices[triangles[:, 1]]-vertices[triangles[:, 0]], vertices[triangles[:, 2]]-vertices[triangles[:, 0]])
        normals = np.zeros_like(vertices)
        for corner in range(3):
            np.add.at(normals, triangles[:, corner], faces)
    return vertices, normals/np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)


def water_lines(vertices, normals, lower, upper, layout):
    """Height of the water line along each wall per texture column."""
    top = normals[:, 2] > .3
    lines = {}
    for name in WALLS:
        inward = np.asarray(optics.SHELL_INWARD[name])
        axis = int(np.flatnonzero(inward)[0])
        wall = lower[axis] if inward[axis] > 0 else upper[axis]
        u, _, (u0, u1), _, (_, cols) = layout[name]
        near = top & (np.abs(vertices[:, axis]-wall) < WATERLINE_BAND) & (vertices[:, u] > u0+CORNER) & (vertices[:, u] < u1-CORNER)
        level = np.full(cols, -np.inf)
        np.maximum.at(level, np.clip(((vertices[near, u]-u0)/optics.SHELL_PIXEL).astype(int), 0, cols-1), vertices[near, 2])
        known = np.isfinite(level)
        assert known.sum() > cols//2, f'no water line along {name}'
        lines[name] = median_filter(np.interp(np.arange(cols), np.flatnonzero(known), level[known]), 5, mode='nearest')
    return lines


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
    assert spec['physics'].get('water_presence', [1]) == [1], 'No water in this case: nothing gets wet.'
    q = spec['simulation_quality']
    lower, upper = np.asarray(q['sph_lower_bound_m'], float), np.asarray(q['sph_upper_bound_m'], float)
    layout = optics.shell_textures(lower, upper)
    settings = {'waterline_band': WATERLINE_BAND, 'corner': CORNER, 'wet_band': WET_BAND, 'wet_fade': WET_FADE,
                'duck_reach': DUCK_REACH, 'shell_pixel': optics.SHELL_PIXEL, 'shell_top': optics.SHELL_TOP,
                'splash_detail_settings': json.loads((run/'aniso/report.json').read_text())['settings']}
    settings = json.loads(json.dumps(settings))
    report_path = run/'aniso/wet_report.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else None
    if not report or report['settings'] != settings:
        report = {'settings': settings, 'frames': {}}
    duck_poses = None  # a deleted duck has nothing to wet
    if spec['physics'].get('duck_presence', [1]) == [1]:
        with np.load(run/'visual_deformation.npz') as data:
            duck_poses = data['positions']
    highest, duck_wet = {}, np.zeros(0 if duck_poses is None else duck_poses.shape[1], bool)
    for frame in range(1, wanted[-1]+1):
        vertices, normals = load_surface(run/'meshes_smooth25'/f'water_{frame:04d}.npz')
        for name, level in water_lines(vertices, normals, lower, upper, layout).items():
            highest[name] = np.maximum(highest.get(name, level), level)
        if duck_poses is not None:
            duck_wet |= cKDTree(vertices).query(duck_poses[frame-1], workers=WORKERS)[0] < DUCK_REACH
        if frame not in wanted:
            continue
        vertices, normals = load_surface(run/'aniso'/f'water_{frame:04d}.npz')
        current = water_lines(vertices, normals, lower, upper, layout)
        wet = duck_wet.copy()
        if duck_poses is not None:
            wet |= cKDTree(vertices).query(duck_poses[frame-1], workers=WORKERS)[0] < DUCK_REACH
        textures, bands = {}, {}
        for name in WALLS:
            _, _, _, (v0, _), (rows, _) = layout[name]
            z = (v0+(np.arange(rows)+.5)*optics.SHELL_PIXEL)[:, None]
            top = np.maximum(highest[name], current[name])+WET_BAND
            above = np.clip((z-current[name]+.01)/.01, 0, 1)       # from 1 cm below the water line, so no dry gap
            textures[name] = (above*np.clip((top-z)/WET_FADE, 0, 1)).astype(np.float32)
            bands[name] = round(float(np.median(top-current[name])), 3)
        path = run/'aniso'/f'wet_{frame:04d}.npz'
        temporary = path.with_name(path.stem+'.tmp.npz')
        np.savez_compressed(temporary, duck=wet.astype(np.float32), **textures)
        temporary.replace(path)
        report['frames'][str(frame)] = {'wet_band_median_m': bands,
                                        'duck_wet_share': round(float(wet.mean()), 3) if len(wet) else None}
        print('WET', frame, json.dumps(report['frames'][str(frame)]), flush=True)
    temporary = report_path.with_name(report_path.name+'.tmp')
    temporary.write_text(json.dumps(report, indent=2))
    temporary.replace(report_path)


if __name__ == '__main__':
    main()
