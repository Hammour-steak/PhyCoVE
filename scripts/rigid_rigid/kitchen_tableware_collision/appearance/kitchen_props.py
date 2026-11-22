"""Pendant lamps and the things standing about the kitchen.

Every piece is a Poly Haven CC0 scan placed by its bounding box: the box
centre goes on an (x, y) anchor and the box bottom on the surface below it --
the island slab, the back worktop, the hob, a shelf, or (for fruit) whatever
the scan it rests on presents at that spot, found by casting rays down onto
it. The pendants hang from the ceiling instead. None of them is in the
simulation, so validate_props() proves that each island piece really stands on
the granite, and the renderer refuses any frame in which a bowl comes within
2 cm of a piece or a piece hides a bowl from the camera.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
import re
from scene_geometry import COUNTER_Z
from city_kitchen import TEXTURES, WORKTOP_X, WORKTOP_Y, BACK_TOP_Z, CEILING_M, SHELF_TOPS, WARM_2700K

# The two pendants over the island: (x, y) of the cord. Each hangs its
# 0.95 m drop from the ceiling, so the shade's rim is 0.70 m over the granite.
PENDANTS = [(-.42, .02), (.78, .02)]
PENDANT_BULB_W = 55.

# name: (Poly Haven model, support, (x, y) anchor, yaw deg, (tilt about x, about y) deg, parts)
# support is 'island', 'back' (the back worktop), 'hob', 'shelf1'/'shelf2', or
# the name of an earlier piece the scan rests on. parts keeps only those mesh
# objects of a multi-object scan. In the six cases the bowls stay within
# y = -0.30 .. 0.33 wherever they are on the island, so the island pieces keep
# to its back strip (y > 0.36).
PROPS = [
    ('Asian pears', 'food_pears_asian_01', 'island', (-.70, .37), 25., (0., 0.), None),
    ('Turned wooden bowl', 'wooden_bowl_02', 'island', (.40, .39), 0., (0., 0.), None),
    ('Lychee 1', 'food_lychee_01', 'Turned wooden bowl', (.385, .38), 0., (0., 0.), None),
    ('Lychee 2', 'food_lychee_01', 'Turned wooden bowl', (.425, .40), 70., (12., 0.), None),
    ('Lychee 3', 'food_lychee_01', 'Turned wooden bowl', (.39, .42), 150., (0., 15.), None),
    ('Brass stock pot', 'brass_pot_01', 'hob', (-2.05, 2.16), 30., (0., 0.), None),
    ('Blue-and-white ginger jar', 'antique_ceramic_vase_01', 'back', (-1.17, 2.24), 40., (0., 0.), None),
    ('Teapot', 'tea_set_01', 'back', (.30, 2.26), 205., (0., 0.), ('tea_set_01_teapot_01', 'tea_set_01_teapot_01_lid')),
    ('Tea cup', 'tea_set_01', 'back', (.52, 2.21), 0., (0., 0.), ('tea_set_01_cup_small_01',)),
    ('Wine bottle 1', 'wine_bottles_01', 'back', (1.03, 2.33), 0., (0., 0.), ('wine_bottles_01_bordeaux',)),
    ('Wine bottle 2', 'wine_bottles_01', 'back', (1.12, 2.30), 60., (0., 0.), ('wine_bottles_01_burgundy',)),
    ('Round white vase', 'ceramic_vase_02', 'shelf1', (-1.45, 2.33), 0., (0., 0.), None),
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


def _import(model, parts=None):
    import bpy
    path = TEXTURES / model / f'{model}_1k.gltf'
    if not path.is_file():
        raise FileNotFoundError(f'Missing local asset: {path}; run scripts/download_assets.py --scene kitchen_tableware_collision')
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [o for o in bpy.data.objects if o not in before]
    if parts is not None:
        # A second import of the same scan names its objects '<name>.001'.
        base = {o: re.sub(r'\.\d{3}$', '', o.name) for o in imported}
        missing = set(parts) - set(base.values())
        if missing:
            raise RuntimeError(f'{model} has no part {sorted(missing)}')
        keep = [o for o in imported if o.type != 'MESH' or base[o] in parts]
        for o in [o for o in imported if o not in keep]:
            bpy.data.objects.remove(o, do_unlink=True)
        imported = keep
    return imported


def _group(name, imported):
    import bpy
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for obj in imported:
        obj.animation_data_clear()
        if obj.parent is None:
            world = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = world
    return root


def _bounds(meshes):
    from mathutils import Vector
    points = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    return lo, hi


def place(name, model, support, anchor, yaw_deg, tilt_deg, parts=None, surfaces=None):
    """Import one scan, turn it and set its box on the anchor; return its record."""
    import bpy
    from mathutils import Euler, Vector
    if support == 'island':
        z = COUNTER_Z
    elif support == 'back':
        z = BACK_TOP_Z
    elif support == 'hob':
        z = surfaces['hob_top_z']
    elif support in ('shelf1', 'shelf2'):
        z = SHELF_TOPS[int(support[-1]) - 1]
    else:
        below = next(p for p in _PLACED if p['object_name'] == support)
        z = None
    imported = _import(model, parts)
    root = _group(name, imported)
    meshes = [o for o in imported if o.type == 'MESH']
    root.rotation_mode = 'XYZ'
    root.rotation_euler = Euler((math.radians(tilt_deg[0]), math.radians(tilt_deg[1]), math.radians(yaw_deg)), 'XYZ')
    bpy.context.view_layer.update()
    lo, hi = _bounds(meshes)
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


def pendant(name, x, y):
    """One modern_ceiling_lamp_01 hung from the ceiling, its bulb lit.

    The scan's canopy is its highest point; it goes against the ceiling. The
    lamp's frosted bulb glows, and a small point lamp at the bulb's centre
    does the lighting, shaded by the opal glass dome around it.
    """
    import bpy
    from mathutils import Vector
    imported = _import('modern_ceiling_lamp_01')
    root = _group(name, imported)
    meshes = [o for o in imported if o.type == 'MESH']
    bpy.context.view_layer.update()
    lo, hi = _bounds(meshes)
    root.location = Vector((x - (lo.x + hi.x) / 2, y - (lo.y + hi.y) / 2, CEILING_M - hi.z))
    bpy.context.view_layer.update()
    lo, hi = _bounds(meshes)
    globe = []
    for o in meshes:
        o['kitchen_prop'] = name
        for i, slot in enumerate(o.material_slots):
            mat = slot.material
            pts = [o.matrix_world @ o.data.vertices[v].co for p in o.data.polygons if p.material_index == i
                   for v in p.vertices]
            if mat is None or not pts or not ('globe' in mat.name or 'glass' in mat.name):
                continue
            nodes, links = mat.node_tree.nodes, mat.node_tree.links
            bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
            out = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL')
            surface = out.inputs['Surface'].links[0].from_socket
            mix = nodes.new('ShaderNodeMixShader')
            if 'globe' in mat.name:
                # The frosted bulb: it glows, and it lets its own lamp's light
                # out (shadow rays pass through it).
                bsdf.inputs['Emission Color'].default_value = (*WARM_2700K, 1)
                for link in list(bsdf.inputs['Emission Color'].links):
                    links.remove(link)
                bsdf.inputs['Emission Strength'].default_value = 12.
                path = nodes.new('ShaderNodeLightPath')
                clear = nodes.new('ShaderNodeBsdfTransparent')
                links.new(path.outputs['Is Shadow Ray'], mix.inputs['Fac'])
                links.new(surface, mix.inputs[1])
                links.new(clear.outputs['BSDF'], mix.inputs[2])
                globe += pts
            else:
                # The dome (0.43 m, rim 0.75 m over the granite) is opal glass:
                # a glossy white skin that lets some of the bulb's light glow
                # through. Most of the light leaves through its open bottom.
                glow = nodes.new('ShaderNodeBsdfTranslucent')
                glow.inputs['Color'].default_value = (.85, .82, .78, 1)
                mix.inputs['Fac'].default_value = .3
                links.new(surface, mix.inputs[1])
                links.new(glow.outputs['BSDF'], mix.inputs[2])
            links.new(mix.outputs['Shader'], out.inputs['Surface'])
    if not globe:
        raise RuntimeError('modern_ceiling_lamp_01 has no globe material')
    centre = Vector([(min(p[i] for p in globe) + max(p[i] for p in globe)) / 2 for i in range(3)])
    data = bpy.data.lights.new(f'{name} bulb', 'POINT')
    data.energy, data.color, data.shadow_soft_size = PENDANT_BULB_W, WARM_2700K, .025
    bulb = bpy.data.objects.new(f'{name} bulb', data)
    bpy.context.collection.objects.link(bulb)
    bulb.location = centre
    record = dict(object_name=name, model='modern_ceiling_lamp_01', support='ceiling', bulb=list(centre),
                  bbox_min=[round(v, 5) for v in lo], bbox_max=[round(v, 5) for v in hi],
                  xy_bounds=[lo.x, hi.x, lo.y, hi.y])
    _PLACED.append(record)
    return record


def add_props(surfaces):
    """Hang the pendants, then place every piece in PROPS order (fruit after
    what it rests on)."""
    _PLACED.clear()
    for i, (x, y) in enumerate(PENDANTS):
        pendant(f'Pendant lamp {i + 1}', x, y)
    for name, model, support, anchor, yaw, tilt, parts in PROPS:
        place(name, model, support, anchor, yaw, tilt, parts, surfaces)
    return list(_PLACED)


def validate_props(bpy, worktop_name):
    """Ray-check the granite under every island piece and keep pieces apart.

    Island pieces must lie inside the worktop by 2 cm and have granite under
    the corners and middle of their footprint; no two pieces resting on the
    same surface may overlap.
    """
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    tree = BVHTree.FromObject(bpy.data.objects[worktop_name], depsgraph)
    inset = .02
    for rec in _PLACED:
        if rec['support'] != 'island':
            continue
        x0, x1, y0, y1 = rec['xy_bounds']
        if not (WORKTOP_X[0] + inset <= x0 <= x1 <= WORKTOP_X[1] - inset
                and WORKTOP_Y[0] + inset <= y0 <= y1 <= WORKTOP_Y[1] - inset):
            raise RuntimeError(f'Prop not inset from the granite worktop: {rec["object_name"]} {rec["xy_bounds"]}')
        if abs(rec['bbox_min'][2] - COUNTER_Z) > 1e-4:
            raise RuntimeError(f'Prop does not stand on the worktop: {rec["object_name"]}')
        for x in (x0, (x0 + x1) / 2, x1):
            for y in (y0, (y0 + y1) / 2, y1):
                hit = tree.ray_cast(Vector((x, y, COUNTER_Z + .3)), Vector((0, 0, -1)), .6)[0]
                if hit is None or abs(hit.z - COUNTER_Z) > .002:
                    raise RuntimeError(f'Prop outside the granite worktop: {rec["object_name"]}')
    resting = {}
    for rec in _PLACED:
        resting.setdefault(rec['support'], []).append(rec)
    for support, group in resting.items():
        if support not in ('island', 'back', 'hob', 'shelf1', 'shelf2'):
            continue
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                ax0, ax1, ay0, ay1 = a['xy_bounds']
                bx0, bx1, by0, by1 = b['xy_bounds']
                if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                    raise RuntimeError(f'Props overlap on the {support}: {a["object_name"]} / {b["object_name"]}')
    return dict(valid=True, worktop_x=list(WORKTOP_X), worktop_y=list(WORKTOP_Y), required_inset_m=inset,
                props=[dict(r) for r in _PLACED])
