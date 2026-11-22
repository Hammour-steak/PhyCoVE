"""Things on the desk and the sideboard behind it, all Poly Haven CC0 scans.

Every piece is placed by its bounding box: the box centre goes on an (x, y)
anchor and the box bottom on the surface below it -- the desk top, the floor,
or whatever an earlier piece presents at that spot, found by casting rays
down onto it. None of them is in the simulation, so validate_props() proves
that each desk piece really stands on the desk and keeps PROP_CLEARANCE_M out
of the cradle's keep-out box (which holds every ball position of every case),
and the renderer refuses any frame in which a piece hides a ball from the
camera.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from study_room import TEXTURES, DESK_X, DESK_Y, thin_glass
from cradle_model import KEEP_OUT, PROP_CLEARANCE_M

# name: (Poly Haven model, support, (x, y) anchor, yaw deg, (tilt about x, about y) deg, mesh subset)
# support is 'desk', 'floor', or the name of an earlier piece the scan rests
# on. The sideboard stands against the back wall (y = 1.60); its front faces
# the room (-y) as authored.
PROPS = [
    ('Rosewood sideboard', 'modern_wooden_cabinet', 'floor', (-1.00, 1.325), 0., (0., 0.), None),
    ('Stoneware jug vase', 'ceramic_vase_04', 'Rosewood sideboard', (-1.86, 1.37), 25., (0., 0.), None),
    ('Brass bud vase', 'brass_vase_03', 'Rosewood sideboard', (-1.62, 1.42), 0., (0., 0.), None),
    ('Porcelain horse', 'horse_statue_01', 'Rosewood sideboard', (.02, 1.36), -35., (0., 0.), None),
    ('Framed photograph', 'standing_picture_frame_01', 'desk', (-.64, .24), -48., (0., 0.), None),
    ('Yellow legal pad', 'office_notepads', 'desk', (-.56, -.23), 9., (0., 0.), ('office_notepads_yellow_pad',)),
    ('Reading glass', 'magnifying_glass_01', 'Yellow legal pad', (-.53, -.25), -24., (90., 0.), None),
    ('Desk stapler', 'vintage_stapler', 'desk', (.46, .25), -28., (0., 0.), None),
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


def place(name, model, support, anchor, yaw_deg, tilt_deg, subset, desk_top_z):
    """Import one scan, turn it and set its box on the anchor; return its record."""
    import bpy
    from mathutils import Euler, Vector
    path = TEXTURES / model / f'{model}_1k.gltf'
    if not path.is_file():
        raise FileNotFoundError(f'Missing local asset: {path}; run scripts/download_assets.py --scene newtons_cradle')
    if support == 'desk':
        z = desk_top_z
    elif support == 'floor':
        z = 0.
    else:
        below = next(p for p in _PLACED if p['object_name'] == support)
        z = None
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [o for o in bpy.data.objects if o not in before]
    if subset is not None:
        unwanted = [o for o in imported if o.type == 'MESH' and o.name not in subset]
        missing = set(subset) - {o.name for o in imported}
        if missing:
            raise RuntimeError(f'{model} has no object(s) {sorted(missing)}')
        for o in unwanted:
            bpy.data.objects.remove(o, do_unlink=True)
        imported = [o for o in imported if o not in unwanted]
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for obj in imported:
        # Some scans ship door/drawer animations; the room stays still.
        obj.animation_data_clear()
        if obj.parent is None:
            world = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = world
    meshes = [o for o in imported if o.type == 'MESH']
    root.rotation_mode = 'XYZ'
    # Tilt about x then y (e.g. lay a reading glass flat), then turn about z.
    root.rotation_euler = Euler((math.radians(tilt_deg[0]), math.radians(tilt_deg[1]), math.radians(yaw_deg)), 'XYZ')
    bpy.context.view_layer.update()
    points = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    if z is None:
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
    glass = None
    for o in meshes:
        o['desk_prop'] = name
        # The scans' glazing is solid refractive glass, which turns a picture
        # behind it into a dark mirror; picture glass is a thin pane.
        for slot in o.material_slots:
            if slot.material is not None and 'glass' in slot.material.name.lower():
                glass = glass or thin_glass()
                slot.material = glass
    record = dict(object_name=name, model=model, support=support, yaw_deg=yaw_deg, tilt_deg=list(tilt_deg),
                  bbox_min=[round(v, 5) for v in lo], bbox_max=[round(v, 5) for v in hi],
                  xy_bounds=[lo.x, hi.x, lo.y, hi.y], meshes=[o.name for o in meshes])
    _PLACED.append(record)
    return record


def add_props(desk_top_z):
    """Place every piece in PROPS order (decor after what it rests on)."""
    _PLACED.clear()
    for name, model, support, anchor, yaw, tilt, subset in PROPS:
        place(name, model, support, anchor, yaw, tilt, subset, desk_top_z)
    return list(_PLACED)


def _box_gap(a_lo, a_hi, b_lo, b_hi):
    """Euclidean distance between two axis-aligned boxes (0 if they overlap)."""
    return math.sqrt(sum(max(0., b_lo[i] - a_hi[i], a_lo[i] - b_hi[i]) ** 2 for i in range(3)))


def keep_out_box():
    return ([KEEP_OUT['x'][0], KEEP_OUT['y'][0], KEEP_OUT['z'][0]],
            [KEEP_OUT['x'][1], KEEP_OUT['y'][1], KEEP_OUT['z'][1]])


def validate_props(bpy, desk_top_z):
    """Ray-check the desk under every desk piece, keep pieces apart and keep
    every piece PROP_CLEARANCE_M away from the cradle's keep-out box."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    top = bpy.context.scene.objects['Desk top']
    tree = BVHTree.FromObject(top, depsgraph)
    inset = .02
    ko_lo, ko_hi = keep_out_box()
    min_gap = 10.
    for rec in _PLACED:
        gap = _box_gap(rec['bbox_min'], rec['bbox_max'], ko_lo, ko_hi)
        min_gap = min(min_gap, gap)
        if gap < PROP_CLEARANCE_M:
            raise RuntimeError(f'Prop within {PROP_CLEARANCE_M} m of the cradle keep-out box: {rec["object_name"]} ({gap:.4f} m)')
        if rec['support'] != 'desk':
            continue
        x0, x1, y0, y1 = rec['xy_bounds']
        if not (DESK_X[0] + inset <= x0 <= x1 <= DESK_X[1] - inset and DESK_Y[0] + inset <= y0 <= y1 <= DESK_Y[1] - inset):
            raise RuntimeError(f'Prop not inset from the desk edge: {rec["object_name"]} {rec["xy_bounds"]}')
        if abs(rec['bbox_min'][2] - desk_top_z) > 1e-4:
            raise RuntimeError(f'Prop does not stand on the desk: {rec["object_name"]}')
        for x in (x0, (x0 + x1) / 2, x1):
            for y in (y0, (y0 + y1) / 2, y1):
                hit = tree.ray_cast(Vector((x, y, desk_top_z + .3)), Vector((0, 0, -1)), .6)[0]
                if hit is None or abs(hit.z - desk_top_z) > .002:
                    raise RuntimeError(f'Prop outside the desk top: {rec["object_name"]}')
    resting = {}
    for rec in _PLACED:
        resting.setdefault(rec['support'], []).append(rec)
    for support, group in resting.items():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                ax0, ax1, ay0, ay1 = a['xy_bounds']
                bx0, bx1, by0, by1 = b['xy_bounds']
                if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                    raise RuntimeError(f'Props overlap on the {support}: {a["object_name"]} / {b["object_name"]}')
    return dict(valid=True, keep_out_box=dict(KEEP_OUT), min_prop_gap_to_keep_out_m=min_gap,
                props=[dict(object_name=r['object_name'], model=r['model'], support=r['support'],
                            bbox_min=r['bbox_min'], bbox_max=r['bbox_max']) for r in _PLACED])


def check_frame(bpy, scene, camera, balls, frame_states, radius):
    """Per-frame checks: every present ball lies inside the keep-out box and
    nothing but the cradle stands between the camera and a ball."""
    from mathutils import Vector
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eye = camera.matrix_world.translation.copy()
    sight_lines = 0
    for key, ball in balls.items():
        if not frame_states[key].get('present', True):
            continue
        centre = ball.matrix_world.translation.copy()
        for axis, (lo, hi) in enumerate((KEEP_OUT['x'], KEEP_OUT['y'], KEEP_OUT['z'])):
            if not (lo <= centre[axis] - radius and centre[axis] + radius <= hi):
                raise RuntimeError(f'{key} leaves the keep-out box on axis {axis}: {tuple(centre)}')
        side = (centre - eye).cross(Vector((0, 0, 1))).normalized()
        for target in (centre, centre + side * radius * .6, centre - side * radius * .6, centre + Vector((0, 0, radius * .6))):
            ray = target - eye
            hit, _, _, _, blocker, _ = scene.ray_cast(depsgraph, eye, ray.normalized(), distance=ray.length - 1e-4)
            sight_lines += 1
            if hit and not blocker.get('cradle_part'):
                raise RuntimeError(f'{blocker.name} hides {key} from the camera')
    return sight_lines
