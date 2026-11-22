"""Export the scenery the DELETE backboard shot can reach as static collider triangles.

    blender -b --python-exit-code 1 --python tools/export_board_absent_colliders.py -- \
        --track TRACK.json [--margin 0.30] [--keep]

TRACK.json is the list of ball centres of a board_presence [0] run. The hall and the goal are built
exactly as the renderer builds them, the backboard unit is removed, and every rendered mesh that comes
within ball radius + margin of the track (other than the floor and the goal base, which are colliders
already) is written in world coordinates to physics/board_absent_colliders.json. --keep also keeps the
colliders already in that file, so repeating solve -> export grows the set until the shot meets
nothing that is not solid. Only the DELETE backboard case reads the file.
"""
import argparse
import json
import sys
from pathlib import Path

SCENE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = SCENE_DIR.parents[1]
for sub in (SCRIPTS, SCENE_DIR, SCENE_DIR / 'physics', SCENE_DIR / 'appearance'):
    if str(sub) not in sys.path:
        sys.path.insert(0, str(sub))
sys.argv[0] = str(SCENE_DIR / 'render_basketball_rim_roll_in.py')
sys.dont_write_bytecode = True

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402
from scene_config import load_scenario  # noqa: E402
from look_basketball_rim_roll_in import build_room  # noqa: E402

BOARD_PARTS = ('Glass backboard', 'Board frame ', 'Back frame ', 'Rim ring', 'Rim mount housing',
               'Rim flange plate')
ALREADY_SOLID = ('Hall floor', 'Goal base')
STEEL = ('Boom ', 'Goal ', 'Base castor', 'Castor axle')
OUT = SCENE_DIR / 'physics' / 'board_absent_colliders.json'


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument('--track', type=Path, required=True)
    p.add_argument('--margin', type=float, default=0.30)
    p.add_argument('--keep', action='store_true')
    a = p.parse_args(argv)
    scenario = load_scenario()
    radius = scenario['physics']['ball_radius']
    bpy.ops.wm.read_factory_settings(use_empty=True)
    build_room(scenario)
    for o in [o for o in bpy.data.objects if o.name.startswith(BOARD_PARTS)]:
        bpy.data.objects.remove(o, do_unlink=True)
    track = [Vector(c) for c in json.loads(a.track.read_text())]
    keep = {}
    if a.keep and OUT.is_file():
        keep = {c['name']: c for c in json.loads(OUT.read_text())['colliders']}
    deps = bpy.context.evaluated_depsgraph_get()
    found = {}
    for o in bpy.data.objects:
        if (o.type != 'MESH' or not o.visible_camera or o.name.startswith(ALREADY_SOLID)
                or o.name.startswith('Ground outside')):
            continue
        ev = o.evaluated_get(deps)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        verts = [tuple(o.matrix_world @ v.co) for v in me.vertices]
        tris = [list(t.vertices) for t in me.loop_triangles]
        ev.to_mesh_clear()
        if not tris:
            continue
        tree = BVHTree.FromPolygons(verts, tris)
        gap = min((h[3] for h in (tree.find_nearest(c, radius + a.margin) for c in track) if h[0] is not None),
                  default=None)
        if gap is None and o.name not in keep:
            continue
        material = 'pad' if 'pad' in o.name.lower() else 'steel' if o.name.startswith(STEEL) else 'wall'
        found[o.name] = {'name': o.name, 'label': ('goal:' if material == 'steel' else 'hall:') + o.name,
                         'material': material, 'closest_surface_to_track_centre_m': gap,
                         'vertices': [[round(c, 6) for c in v] for v in verts],
                         'indices': [i for t in tris for i in t]}
    missing = sorted(set(keep) - set(found))
    if missing:
        raise SystemExit(f'kept colliders no longer in the scene: {missing}')
    OUT.write_text(json.dumps({'note': __doc__.strip().splitlines()[0], 'track': str(a.track.name),
                               'margin_m': a.margin, 'colliders': [found[k] for k in sorted(found)]}) + '\n')
    print('exported', len(found), 'colliders:', ', '.join(sorted(found)))


if __name__ == '__main__':
    main()
