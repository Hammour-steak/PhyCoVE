"""Poly Haven scans standing in the kitchen, and the checks that keep them
out of the way of everything that moves.

Every piece is a CC0 scan placed by its bounding box: the box centre goes on an
(x, y) anchor and the box bottom on the surface found by casting rays down at
that spot (the worktop, the window board or the floor). None of them -- nor any
other part of the built kitchen -- is in the simulation, so check_clearance()
refuses a take in which the lid (or the ADDed bowl) passes within 2 cm of
anything but the floor it lands on, or in which something hides it from the
camera.
"""
from __future__ import annotations

import math

from coastal_kitchen import TEXTURES

# name: (Poly Haven model, (x, y) anchor in world metres, yaw deg)
# The lid falls at x >= 0.50 and lands around (0.8, -0.6); every piece stands
# on the worktop behind the pot (y > 0) against the wall, or on the floor in the
# far right corner, well clear of all six trajectories (see check_clearance).
PROPS = [
    ('Wine and oil bottles', 'wine_bottles_01', (-0.06, 1.78), 90.),
    ('White stoneware jug', 'ceramic_vase_04', (-0.02, 0.62), 35.),
    ('White stoneware crock', 'ceramic_vase_02', (-0.03, 0.25), 0.),
    ('Counter stool', 'metal_stool_01', (2.12, 1.80), 20.),
]

CLEARANCE_M = 0.02

_PLACED: list[dict] = []


def _support_height(x, y, radius, start_z):
    """Highest surface under a disc of ``radius`` at (x, y), by rays from above."""
    import bpy
    from mathutils import Vector
    depsgraph = bpy.context.evaluated_depsgraph_get()
    best = None
    for dx, dy in [(0, 0)] + [(radius * math.cos(a), radius * math.sin(a)) for a in
                              (k * math.pi / 4 for k in range(8))]:
        hit, location, *_ = bpy.context.scene.ray_cast(depsgraph, Vector((x + dx, y + dy, start_z)),
                                                        Vector((0, 0, -1)), distance=3.)
        if hit:
            best = location.z if best is None else max(best, location.z)
    if best is None:
        raise RuntimeError(f'nothing to rest on at {x:.3f}, {y:.3f}')
    return best


def place(name, model, anchor, yaw_deg, start_z):
    """Import one scan, turn it and set its box on the anchor; return its record."""
    import bpy
    from mathutils import Euler, Vector
    path = TEXTURES / model / f'{model}_1k.gltf'
    if not path.is_file():
        raise FileNotFoundError(f'Missing local asset: {path}; run scripts/download_assets.py --scene pot_lid_drop')
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
    root.rotation_euler = Euler((0., 0., math.radians(yaw_deg)), 'XYZ')
    bpy.context.view_layer.update()
    points = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    # Probe under the inner part of the footprint, with the piece out of the way.
    for o in meshes:
        o.hide_viewport = True
    radius = .35 * min(hi.x - lo.x, hi.y - lo.y)
    z = _support_height(anchor[0], anchor[1], radius, start_z)
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
    record = dict(object_name=name, model=model, yaw_deg=yaw_deg, support_z=round(z, 5),
                  bbox_min=[round(v, 5) for v in lo], bbox_max=[round(v, 5) for v in hi])
    _PLACED.append(record)
    return record


def add_props(start_z):
    """Place every piece in PROPS; ``start_z`` is where the downward rays
    start (below the wall cabinets, above anything standing on the worktop)."""
    _PLACED.clear()
    for name, model, anchor, yaw in PROPS:
        place(name, model, anchor, yaw, start_z)
    _check_props_apart()
    return list(_PLACED)


def _check_props_apart():
    for i, a in enumerate(_PLACED):
        for b in _PLACED[i + 1:]:
            if all(a['bbox_min'][k] < b['bbox_max'][k] and b['bbox_min'][k] < a['bbox_max'][k] for k in range(3)):
                raise RuntimeError(f'Props overlap: {a["object_name"]} / {b["object_name"]}')


# ------------------------------------------------------------------ checks


def _static_tree(objects):
    """One BVH over every static mesh in world space."""
    import bpy
    from mathutils.bvhtree import BVHTree
    depsgraph = bpy.context.evaluated_depsgraph_get()
    verts, polys = [], []
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        matrix = obj.matrix_world
        base = len(verts)
        verts.extend(matrix @ v.co for v in mesh.vertices)
        polys.extend([base + i for i in p.vertices] for p in mesh.polygons)
        evaluated.to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys)


def check_clearance(*, lid, physics, origin, hull_vertices, camera, bowl=None, exclude=()):
    """Refuse the take if any moving body comes within CLEARANCE_M of a static
    object other than the floor, or is hidden from the camera.

    The poses are the simulator's own (physics_transforms frames plus the
    action origin), so the check sees exactly what is keyframed. The bowl, when
    the ADD edit puts one in, is held to the same rule.
    """
    import bpy
    from mathutils import Matrix, Quaternion, Vector
    skip = {lid.name, *(o.name for o in exclude)}
    if bowl is not None:
        skip.add(bowl.name)
    statics = [o for o in bpy.context.scene.objects
               if o.type in {'MESH', 'CURVE'} and o.name not in skip and not o.get('physics_floor')
               and o.visible_get()]
    tree = _static_tree(statics)
    lid_points = [Vector(v) for v in hull_vertices]
    bowl_points = [Vector(v.co) for v in bowl.data.vertices][::7] if bowl is not None else []
    cam = camera.matrix_world.translation.copy()
    nearest = (math.inf, None, None)
    hidden = []
    for record in physics['frames']:
        frame = int(record['frame_index'])
        bodies = [('lid', record['lid_location'], record['lid_quaternion_xyzw'], lid_points)]
        if bowl is not None and record.get('bowl_location') is not None:
            bodies.append(('bowl', record['bowl_location'], record['bowl_quaternion_xyzw'], bowl_points))
        for body, location, quat, points in bodies:
            x, y, z, w = quat
            matrix = Matrix.Translation(Vector(location) + origin) @ Quaternion((w, x, y, z)).to_matrix().to_4x4()
            world = [matrix @ p for p in points]
            for p in world:
                found = tree.find_nearest(p, CLEARANCE_M * 4)
                if found[0] is not None and found[3] < nearest[0]:
                    nearest = (found[3], frame, body)
            # Visible if a ray from the camera reaches the body's centre, or
            # failing that any of a ring of its points, before hitting the room.
            centre = matrix.translation
            targets = [centre] + world[::max(1, len(world) // 12)]
            seen = False
            for target in targets:
                direction = target - cam
                distance = direction.length
                hit = tree.ray_cast(cam, direction.normalized(), distance - .005)
                if hit[0] is None:
                    seen = True
                    break
            if not seen:
                hidden.append((frame, body))
    report = dict(clearance_m=CLEARANCE_M, static_objects=len(statics),
                  nearest_static_m=None if nearest[1] is None else round(nearest[0], 4),
                  nearest_frame=nearest[1], nearest_body=nearest[2], hidden_frames=hidden)
    if nearest[0] < CLEARANCE_M:
        raise RuntimeError(f'{nearest[2]} passes {nearest[0] * 100:.1f} cm from a static object at frame {nearest[1]} '
                           f'(minimum {CLEARANCE_M * 100:.0f} cm): {report}')
    if hidden:
        raise RuntimeError(f'moving body hidden from the camera at {hidden[:8]}')
    return report
