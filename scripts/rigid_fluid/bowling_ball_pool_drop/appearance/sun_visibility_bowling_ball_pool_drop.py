"""Static sun visibility for caustics_bowling_ball_pool_drop.py.

Which points of the still water surface, and of the tank walls above it, see the fitted sun past the
authored windows, walls, deck, coping and ladder, and past the tank's own walls. Shadow rays through
the environment mesh as the render keeps it (debris removed) plus the tank walls.

blender -b --python sun_visibility_bowling_ball_pool_drop.py -- --level <still water z> --out visibility.npz
"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import optics_bowling_ball_pool_drop as optics  # noqa: E402
import scene_bowling_ball_pool_drop as pool_scene  # noqa: E402


def environment_bvh():
    pool_scene.clear_scene()
    pool_scene.add_mountain_pool_environment(optics.FLOOR)
    bpy.context.view_layer.update()
    obj = bpy.data.objects['pool.001']
    mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
    mesh.calc_loop_triangles()
    verts = [obj.matrix_world @ v.co for v in mesh.vertices]
    tris = [tuple(t.vertices) for t in mesh.loop_triangles]
    centres = np.array([tuple(sum((verts[k] for k in t), Vector()) / 3) for t in tris])
    triangles = [t for t, gone in zip(tris, optics.debris(centres)) if not gone]
    for quad in optics.tank_quads()[1:]:
        base = len(verts)
        verts += [Vector(p) for p in quad]
        triangles += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    return BVHTree.FromPolygons(verts, triangles)


def visible(bvh, points, to_sun):
    return np.array([bvh.ray_cast(Vector(p) + to_sun * .002, to_sun, 60.)[0] is None for p in points], dtype=np.float32)


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument('--level', type=float, required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    bvh = environment_bvh()
    to_sun = Vector(optics.TO_SUN).normalized()
    layout = optics.faces()
    result = {}
    # Still water surface, one value per floor texture pixel centre inside the pool.
    origin, u, v, _, (rows, cols) = layout['PoolFloor']
    xs = origin[0] + (np.arange(cols) + .5) * optics.SHELL_PIXEL
    ys = origin[1] + (np.arange(rows) + .5) * optics.SHELL_PIXEL
    grid = np.stack(np.meshgrid(xs, ys, indexing='xy'), -1).reshape(-1, 2)
    water = np.zeros(len(grid), np.float32)
    inside = optics.wall_distance(grid, optics.POOL) > 0
    water[inside] = visible(bvh, np.column_stack([grid[inside], np.full(inside.sum(), args.level)]), to_sun)
    result['water'] = water.reshape(rows, cols)
    # Walls above the still water (the band the sun can reach directly), per wall texture pixel.
    for name in optics.FACES[1:]:
        origin, u, v, _, (rows, cols) = layout[name]
        texture = np.zeros((rows, cols), np.float32)
        inward = optics.inward(name)
        if inward @ np.asarray(optics.TO_SUN) > 0:
            band = np.flatnonzero(optics.FLOOR + (np.arange(rows) + .5) * optics.SHELL_PIXEL > args.level - .08)
            along = (np.arange(cols) + .5) * optics.SHELL_PIXEL
            for row in band:
                points = origin + along[:, None] * u + (row + .5) * optics.SHELL_PIXEL * v + .003 * inward
                texture[row] = visible(bvh, points, to_sun)
        result[name] = texture
    np.savez_compressed(args.out, level=args.level, to_sun=np.asarray(optics.TO_SUN), corners=optics.POOL, **result)
    print('VISIBILITY', {k: round(float(np.asarray(x).mean()), 4) for k, x in result.items()},
          'water inside', round(float(result['water'].reshape(-1)[inside].mean()), 4), flush=True)


if __name__ == '__main__':
    main()
