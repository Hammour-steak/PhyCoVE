"""Breakfast things on the oak island, the back counter and the stools.

Every piece is a Poly Haven CC0 scan placed by its bounding box: the box
centre goes on an (x, y) anchor and the box bottom on the surface below it --
the island top, the back worktop, the floor, or (for fruit) whatever the scan
it rests on presents at that spot, found by casting rays down onto it. None of
them is in the simulation, so validate_island_props() proves that each island
piece really stands on the oak, and the renderer refuses any frame in which a
can comes within 2 cm of a piece or a piece hides a can from the camera.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from scene_geometry import COUNTER_Z
from kitchen_room import TEXTURES, WORKTOP_X, WORKTOP_Y, BACK_TOP_Z

# name: (Poly Haven model, support, (x, y) anchor, yaw deg, (tilt about x, about y) deg)
# support is 'island', 'back' (the back worktop), 'floor', or the name of an
# earlier piece the scan rests on. The cans run along y = 0 between x = -0.51
# and x = 0.86 in the six cases, so the island pieces keep behind (y > 0.15),
# beyond (x > 0.93) or well to the left of that strip.
PROPS = [
    ('Oak chopping board', 'wooden_cutting_board', 'island', (1.19, .17), 10., (0., 0.)),
    ('Lemon on the board', 'lemon', 'Oak chopping board', (1.07, .19), 35., (90., 0.)),
    ('Lime on the board', 'food_lime_01', 'Oak chopping board', (1.15, .25), -20., (82., 0.)),
    ('Onion on the board', 'yellow_onion', 'Oak chopping board', (1.30, .13), 60., (0., 0.)),
    ('Turned wooden fruit bowl', 'wooden_bowl_01', 'island', (.40, .31), 20., (0., 0.)),
    # Three apples 10 cm apart, so no two of the 9.8 cm scans touch.
    ('Apple in the bowl 1', 'food_apple_01', 'Turned wooden fruit bowl', (.400, .368), 0., (8., -5.)),
    ('Apple in the bowl 2', 'food_apple_01', 'Turned wooden fruit bowl', (.350, .281), 130., (-12., 6.)),
    ('Apple in the bowl 3', 'food_apple_01', 'Turned wooden fruit bowl', (.450, .281), 250., (5., 14.)),
    ('Carved wooden plate', 'carved_wooden_plate', 'island', (.06, -.30), 0., (0., 0.)),
    ('Croissant on the plate', 'croissant', 'Carved wooden plate', (.06, -.30), 25., (0., 0.)),
    ('Electric kettle', 'vintage_electric_kettle', 'back', (1.95, 2.13), -35., (0., 0.)),
    ('Enamel stock pot', 'pot_enamel_01', 'back', (2.60, 2.12), 15., (0., 0.)),
    ('Milk jug', 'jug_01', 'back', (-1.05, 2.16), 200., (0., 0.)),
    ('Bar stool 1', 'bar_chair_round_01', 'floor', (-.95, .72), 10., (0., 0.)),
    ('Bar stool 2', 'bar_chair_round_01', 'floor', (-.15, .74), 37., (0., 0.)),
    ('Bar stool 3', 'bar_chair_round_01', 'floor', (.65, .71), 71., (0., 0.)),
]

_PLACED = []


def _support_height(x, y, radius, top):
    """Highest surface under a disc of ``radius`` at (x, y), by rays from above."""
    import bpy
    from mathutils import Vector
    depsgraph = bpy.context.evaluated_depsgraph_get()
    best = None
    for dx, dy in [(0, 0)] + [(radius * math.cos(a), radius * math.sin(a)) for a in
                              (k * math.pi / 4 for k in range(8))]:
        hit, location, *_ = bpy.context.scene.ray_cast(depsgraph, Vector((x + dx, y + dy, top + .3)),
                                                        Vector((0, 0, -1)), distance=1.)
        if hit:
            best = location.z if best is None else max(best, location.z)
    if best is None:
        raise RuntimeError(f'nothing to rest on at {x:.3f}, {y:.3f}')
    return best


def place(name, model, support, anchor, yaw_deg, tilt_deg):
    """Import one scan, turn it and set its box on the anchor; return its record."""
    import bpy
    from mathutils import Euler, Vector
    path = TEXTURES / model / f'{model}_1k.gltf'
    if not path.is_file():
        raise FileNotFoundError(f'Missing local asset: {path}; run scripts/download_assets.py --scene kitchen_can_collision')
    if support == 'island':
        z = COUNTER_Z
    elif support == 'back':
        z = BACK_TOP_Z
    elif support == 'floor':
        z = 0.
    else:
        below = next(p for p in _PLACED if p['object_name'] == support)
        # Rest on the scan below: the highest point it offers under the inner
        # part of this piece's footprint (filled in after the import below).
        z = None
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for obj in imported:
        obj.animation_data_clear()
        if obj.parent is None:
            world = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = world
    meshes = [o for o in imported if o.type == 'MESH']
    root.rotation_mode = 'XYZ'
    # Tilt about x then y (e.g. lay a lemon on its side), then turn about z.
    root.rotation_euler = Euler((math.radians(tilt_deg[0]), math.radians(tilt_deg[1]), math.radians(yaw_deg)), 'XYZ')
    bpy.context.view_layer.update()
    points = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    if z is None:
        # Hide the new piece while probing what lies under it.
        for o in meshes:
            o.hide_viewport = True
        radius = .4 * min(hi.x - lo.x, hi.y - lo.y) / 2
        z = _support_height(anchor[0], anchor[1], radius, below['bbox_max'][2])
        for o in meshes:
            o.hide_viewport = False
    shift = Vector((anchor[0] - (lo.x + hi.x) / 2, anchor[1] - (lo.y + hi.y) / 2, z - lo.z))
    root.location = shift
    bpy.context.view_layer.update()
    lo, hi = lo + shift, hi + shift
    for o in meshes:
        o['kitchen_prop'] = name
        for poly in o.data.polygons:
            poly.use_smooth = True
    record = dict(object_name=name, model=model, support=support, yaw_deg=yaw_deg, tilt_deg=list(tilt_deg),
                  bbox_min=[round(v, 5) for v in lo], bbox_max=[round(v, 5) for v in hi],
                  xy_bounds=[lo.x, hi.x, lo.y, hi.y])
    _PLACED.append(record)
    return record


def add_tabletop_props():
    """Place every piece in PROPS order (fruit after what it rests on)."""
    _PLACED.clear()
    for name, model, support, anchor, yaw, tilt in PROPS:
        place(name, model, support, anchor, yaw, tilt)
    return list(_PLACED)


def validate_island_props(bpy):
    """Ray-check the oak under every island piece and keep pieces apart.

    Island pieces must lie inside the worktop by 2 cm and have oak under the
    corners and middle of their footprint; no two pieces resting on the same
    surface may overlap.
    """
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    staves = [o for o in bpy.context.scene.objects if o.name.startswith('Island oak stave')]
    trees = [BVHTree.FromObject(o, depsgraph) for o in staves]
    inset = .02
    for rec in _PLACED:
        if rec['support'] != 'island':
            continue
        x0, x1, y0, y1 = rec['xy_bounds']
        if not (WORKTOP_X[0] + inset <= x0 <= x1 <= WORKTOP_X[1] - inset
                and WORKTOP_Y[0] + inset <= y0 <= y1 <= WORKTOP_Y[1] - inset):
            raise RuntimeError(f'Prop not inset from the oak worktop: {rec["object_name"]} {rec["xy_bounds"]}')
        if abs(rec['bbox_min'][2] - COUNTER_Z) > 1e-4:
            raise RuntimeError(f'Prop does not stand on the worktop: {rec["object_name"]}')
        for x in (x0, (x0 + x1) / 2, x1):
            for y in (y0, (y0 + y1) / 2, y1):
                hits = [t.ray_cast(Vector((x, y, COUNTER_Z + .3)), Vector((0, 0, -1)), .6)[0] for t in trees]
                hits = [h for h in hits if h is not None]
                if not hits or abs(max(h.z for h in hits) - COUNTER_Z) > .002:
                    raise RuntimeError(f'Prop outside the oak worktop: {rec["object_name"]}')
    resting = {}
    for rec in _PLACED:
        resting.setdefault(rec['support'], []).append(rec)
    for support, group in resting.items():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                ax0, ax1, ay0, ay1 = a['xy_bounds']
                bx0, bx1, by0, by1 = b['xy_bounds']
                if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1 and support in ('island', 'back'):
                    raise RuntimeError(f'Props overlap on the {support}: {a["object_name"]} / {b["object_name"]}')
    return dict(valid=True, worktop_x=list(WORKTOP_X), worktop_y=list(WORKTOP_Y), required_inset_m=inset,
                props=[dict(r) for r in _PLACED])
