"""Height map of the kitchen around the basin: the first surface met from below --top in every 4 mm
column within --half of the basin, with the basin and apple left out, and which object that surface
belongs to. The simulation's floor is the flat counter; this map tells the splash stage where that floor
is really the cutting board or the open sink, and where droplets flying past the simulated domain come
down. Under anything standing on the counter, the column goes on down through it: its solid layers
(entered and left in turn, LAYERS at most, each with the object it is) and the ground below, so
droplets meet the soda maker, the peppers or the tap where they are solid and pass under the tap's
spout into the sink. It reaches well beyond the domain (0.42 m), and starts half a metre above the
counter, under the wall cabinets.

blender -b --python ground_apple_drop_kitchen_basin.py -- --out <ground.npz> [--half 0.8] [--cell 0.004]
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scene_apple_drop_kitchen_basin as apple_scene  # noqa: E402

LAYERS = 4      # solid layers kept per column
STAND = .003    # m; columns whose top is this far above the counter have something standing there
GROUND = .002   # m; a column ends at the first surface this close above the counter, or below it

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument('--out', required=True)
parser.add_argument('--half', type=float, default=0.8)
parser.add_argument('--cell', type=float, default=0.004)
parser.add_argument('--top', type=float, default=apple_scene.COUNTER_Z + 0.5)
args = parser.parse_args(argv)
apple, _, _ = apple_scene.build_environment((-1.782, 1.908, 2.6676), added_lights=False)
for obj in (apple, bpy.data.objects['PCVE_BlenderKit_Basin']):
    obj.hide_viewport = True
bpy.context.view_layer.update()
depsgraph = bpy.context.evaluated_depsgraph_get()
scene = bpy.context.scene
down = Vector((0, 0, -1))
centre = np.array([apple_scene.BASIN_CENTER.x, apple_scene.BASIN_CENTER.y])
lower = centre - args.half
count = int(round(2 * args.half / args.cell)) + 1
height = np.full((count, count), np.nan)
owner = np.full((count, count), -1, np.int16)
names = []


def named(obj):
    if obj.name not in names:
        names.append(obj.name)
    return names.index(obj.name)


for i in range(count):
    for j in range(count):
        x, y = lower + (np.array([i, j]) + .5) * args.cell
        hit, location, _, _, obj, _ = scene.ray_cast(depsgraph, Vector((x, y, args.top)), down, distance=3.0)
        if hit:
            height[i, j], owner[i, j] = location.z, named(obj)
# On down through whatever stands on the counter: surfaces met in turn enter and leave its solid.
layers = np.full((count, count, LAYERS, 2), np.nan, np.float32)
layer_owner = np.full((count, count, LAYERS), -1, np.int16)
base = height.copy()
for i, j in np.argwhere(height > apple_scene.COUNTER_Z + STAND):
    x, y = lower + (np.array([i, j]) + .5) * args.cell
    hits = [(height[i, j], owner[i, j])]
    while hits[-1][0] > apple_scene.COUNTER_Z + GROUND and len(hits) < 2 * LAYERS + 1:
        hit, location, _, _, obj, _ = scene.ray_cast(depsgraph, Vector((x, y, hits[-1][0] - 1e-4)), down, distance=3.0)
        if not hit:
            break
        hits.append((location.z, named(obj)))
    base[i, j] = min(hits[-1][0], apple_scene.COUNTER_Z)
    for k in range(min(LAYERS, len(hits) // 2)):
        (top, whose), (bottom, _) = hits[2 * k], hits[2 * k + 1]
        layers[i, j, k], layer_owner[i, j, k] = (bottom, top), whose
np.savez(args.out, lower=lower, cell=args.cell, height=height, counter_z=apple_scene.COUNTER_Z, owner=owner,
         names=np.array(names), layers=layers, layer_owner=layer_owner, base=base)
print('GROUND', args.out, 'shape', height.shape, 'nan', int(np.isnan(height).sum()),
      'z %.4f..%.4f' % (np.nanmin(height), np.nanmax(height)))
for k in np.argsort(-np.bincount(owner[owner >= 0].ravel(), minlength=len(names))):
    columns = owner == k
    if columns.any():
        print('HIT', names[k], int(columns.sum()), 'top %.4f' % np.nanmax(height[columns]),
              'layers', int((layer_owner == k).sum()))
for k in sorted(set(np.unique(layer_owner[layer_owner >= 0])) - set(np.unique(owner[owner >= 0]))):
    print('UNDER', names[k], 'layers', int((layer_owner == k).sum()))
below = height < apple_scene.COUNTER_Z - .01
if below.any():
    idx = np.argwhere(below)
    xy = lower + (idx + .5) * args.cell
    print('BELOW_COUNTER cells', int(below.sum()), 'x %.3f..%.3f y %.3f..%.3f z %.3f..%.3f' % (
        xy[:, 0].min(), xy[:, 0].max(), xy[:, 1].min(), xy[:, 1].max(), np.nanmin(height[below]), np.nanmax(height[below])))
