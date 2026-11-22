"""A warm hotel-spa bathroom at dusk, built on the GLB bathroom the physics uses.

The room shell, washbasin cabinet, basin, mirror and bathtub come from
assets/models/big_project.glb at their exact positions (they are the static
colliders' visible surfaces). Their surfaces are re-dressed: limestone slab
walls, honed travertine floor, walnut vanity, solid-surface tub and vanity
top, brass fittings. A window cut into the north wall shows a dusk sky; the
room is lit by that twilight plus its own fixtures (four recessed ceiling
cans, two opal sconces beside the mirror, the mirror's LED halo and candles).

The stool is the tall seat the GLB itself ships stacked beside the bathtub:
seat slab Cube.045 on three splayed cylinder legs (Cylinder.062/.063/.064),
re-dressed as an oiled teak seat on blackened bronze legs (sizes unchanged).
The bigger lower slab (Cube.046) and the coffee cup + saucer resting on top
are removed. Each rigid body is an empty parented at the measured seat centre
(physics body origin), so replayed poses align with the visible mesh.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from scene_geometry import STOOL_ORIGIN, FLOOR_Z
import spa_materials as sm
import spa_dressing as sd

MODELS = _pcve_asset('models')
# AgX exposure for the interior: the fixtures, not the twilight, set it.
EXPOSURE = 0.0

# GLB hierarchy: the empty 'Cube.045' is the whole stacked-stool assembly
# (seat slab mesh + the lower big slab 'Cube.046' + three leg empties). The
# small top stool is thrown; the big lower slab and the coffee cup + saucer
# on top are removed.
STOOL_ASSEMBLY = 'Cube.045'
REMOVE_SUBTREE = 'Cube.046'               # the big stool below (empty + mesh)
REMOVE_PREFIXES = ('Coffee_cup_withe',)   # cup + saucer resting on the seat
# Non-rigid decor sitting on confirmed stool flight paths (BVH audited over
# the source and all four edits). The coriander pot sits on the tub rim the
# rebound rolls through (baseline / edit_remove_bathtub), the wicker vase
# under it is clipped by the same roll, and the north-east towel rack is crossed mid-tumble by edit_fast_spin.
# Removing them beats leaving the stool to visually clip through cloth,
# leaves and wicker.
DECOR_REMOVE_PREFIXES = ('Plant_Coriander_A',   # pot plant on the tub rim
                         'Vase_Weaved-Wicker-Shell_A_spring-summer-autumn.001',
                         'Towels.003',          # NE wall towel rack group
                         'tovel1.002',
                         'tove2.001',
                         # The fourth towel of that same rack:
                         # edit_fast_throw's *3 flight cuts
                         # straight through it (228 cloth triangles at frame 15).
                         'tovel3.003',
                         # Floating north-east decor panel (glass Cube.043 +
                         # painting Plane.006 in a black frame Cube.044). It
                         # hangs in the un-modelled corner void with no wall
                         # behind it, straight across the eastward flight of
                         # edit_fast_throw (and the post-tub flight of
                         # edit_remove_bathtub): the stool visibly burst
                         # through the glass. Removed so the completed wall
                         # below reads as a plain bathroom wall.
                         'Cube.043',
                         'Plane.006',
                         'Cube.044',
                         # East end of the tub shelf. With the chamfer
                         # collider, edit_fast_throw's *3 flight is deflected
                         # south along it and skims the shelf top at z~3.1 on
                         # frames 18-27, cutting this candle (153 wax triangles)
                         # and the hibiscus in the vase beside it (up to 361
                         # leaf triangles). Removing the two props is cheaper
                         # and steadier than giving cloth-thin leaves a collider.
                         'candles-01.006',
                         'Vase_Circular-Simple-Glazed-Ceramics_A_spring-summer-autumn',
                         'Plant_Hibiscus_D')
# Whole GLB groups removed by exact root name (prefixes would also catch
# 'Cylinder.0xx' / 'Decorated candle.001'). The black shelving tower beside the
# camera (Cube.002-.007 with its rails, towels and flowers) stood 0.2 m from
# the lens and filled the left 15 % of the frame with a black post; the window
# sits behind that spot. The sunburst wall clock is a branded design
# piece; the ceiling slab Cube.013 is a hidden emitter above the plaster.
REMOVE_ROOTS = ('Cube.002', 'Cube.003', 'Cube.004', 'Cube.005', 'Cube.006', 'Cube.007',
                'Cylinder', 'Cylinder.001', 'Cylinder.002', 'Cylinder.003',
                'Towels', 'Towels.001', 'Towels.002',
                'Flower_Cornflower_B_spring-summer', 'Flower_Cornflower_E_spring-summer',
                'Vase_Circular-Widening-Glazed-Ceramics_A_spring-summer-autu',
                'Vitra_Sunflower_Clock_mat(1)', 'Vitra_Sunflower_Clock_mat(1).001',
                'Cube.013')
# The candle tray from that shelf is kept and carried to the side table.
CANDLE_TRAY = 'Decorated candle'


def set_visible(obj, visible):
    """Hide a rigged stool and all of its descendants from render/viewport."""
    stack = [obj]
    while stack:
        o = stack.pop()
        o.hide_render = not visible
        o.hide_viewport = not visible
        stack.extend(o.children)


# The visual bathtub shell plus the towel draped over its rim; both follow
# the DELETE bathtub edit so nothing floats where the tub stands in the source.
BATHTUB_VISUALS = ('bathtub', 'Plane.003')


def set_bathtub_visible(bpy, visible):
    for prefix in BATHTUB_VISUALS:
        for top in bpy.context.scene.objects:
            if not top.name.startswith(prefix): continue
            if top.parent is not None and top.parent.name.startswith(prefix): continue
            for o in _subtree(top):
                o.hide_render = not visible
                o.hide_viewport = not visible


def _subtree(root):
    out, stack = [], [root]
    while stack:
        o = stack.pop()
        out.append(o)
        stack.extend(o.children)
    return out


def strip_decor(bpy, imported):
    """Delete the lower stool, its cup, decor on flight paths and the removed groups."""
    assembly = next(o for o in imported if o.type == 'EMPTY' and o.name == STOOL_ASSEMBLY)
    doomed = [o for o in _subtree(assembly) if o.name.split('_')[0] == REMOVE_SUBTREE]
    prefixes = REMOVE_PREFIXES + DECOR_REMOVE_PREFIXES

    def prefixed(o):
        return o.name.startswith(prefixes)

    # Decor removal takes whole subtrees: GLB plants/towels hang off empty
    # parents whose mesh children inherit the name prefix.
    for top in bpy.context.scene.objects:
        if prefixed(top) and not (top.parent is not None and prefixed(top.parent)):
            doomed += _subtree(top)
        elif top.name in REMOVE_ROOTS:
            doomed += _subtree(top)
    for o in dict.fromkeys(doomed):
        bpy.data.objects.remove(o, do_unlink=True)
    left = [o.name for o in bpy.context.scene.objects if prefixed(o) or o.name in REMOVE_ROOTS]
    if left: raise RuntimeError(f'Decor removal missed: {left[:4]}')
    bpy.context.view_layer.update()


def make_stools(bpy, imported):
    """Rig the GLB's own stool assembly under the 'stool' body empty."""
    from mathutils import Matrix
    assembly = next(o for o in bpy.context.scene.objects if o.type == 'EMPTY' and o.name == STOOL_ASSEMBLY)
    pivot = bpy.data.objects.new('GLB tall stool A body', None)
    bpy.context.scene.collection.objects.link(pivot)
    pivot.empty_display_size = .12
    pivot.location = STOOL_ORIGIN
    world = assembly.matrix_world.copy()
    assembly.parent = pivot
    assembly.matrix_parent_inverse = Matrix.Identity(4)
    # The depsgraph must see the new parent before the world-space
    # assignment, otherwise the old (parentless) matrix is baked into
    # matrix_basis and the meshes detach from the animated pivot.
    bpy.context.view_layer.update()
    assembly.matrix_world = world
    bpy.context.view_layer.update()
    delta = max(abs(a - b) for a, b in zip(assembly.matrix_world.translation, world.translation))
    if delta > 1e-6: raise RuntimeError(f'{assembly.name} drifted {delta:.2e} m while rigging')
    return {'stool': pivot}


def import_bathroom(bpy):
    path = MODELS / 'big_project.glb'
    if not path.is_file(): raise FileNotFoundError(f'Missing local asset: {path}')
    previous = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [o for o in bpy.data.objects if o not in previous]
    for o in imported:
        o.animation_data_clear()
        if o.type in {'CAMERA', 'LIGHT'}: bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.update()
    imported = [o for o in bpy.data.objects if o not in previous]
    strip_decor(bpy, imported)
    return [o for o in bpy.data.objects if o not in previous]


# The GLB models its east wall only up to y=0.52 (inner face x=10.95) and a
# stepped recess to y=1.82 (x=11.24); north of that the corner is an open
# void — the physics box 'wall_east' (inner face x=11.10, scene_geometry)
# nevertheless blocks the whole range. edit_fast_throw and edit_remove_bathtub
# fly the stool into that corner; without a visible wall it would bounce off
# an invisible wall and settle floating in the void. This patch closes the gap
# flush with the physics plane.
NE_WALL = dict(x_inner=11.10, x_outer=11.44, y0=0.52, y1=4.86, z0=0.0, z1=6.38)


def complete_northeast_wall(bpy, scene, material):
    """Add a visible wall closing the un-modelled NE corner at x=11.10."""
    w = NE_WALL
    x0, x1, y0, y1, z0, z1 = w['x_inner'], w['x_outer'], w['y0'], w['y1'], w['z0'], w['z1']
    mesh = bpy.data.meshes.new('NE patch wall')
    mesh.from_pydata(
        [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], [],
        [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)])
    mesh.update()
    mesh.materials.append(material)
    obj = bpy.data.objects.new('NE patch wall', mesh)
    scene.collection.objects.link(obj)
    sm.world_box_uv(bpy, obj)
    return obj


def _meshes(bpy, *roots):
    out = []
    for name in roots:
        root = bpy.data.objects.get(name)
        if root is None:
            raise RuntimeError(f'GLB object {name!r} is missing')
        out += [o for o in _subtree(root) if o.type == 'MESH']
    return out


def _assign(bpy, objs, material, uv=False):
    for o in objs:
        if uv:
            sm.world_box_uv(bpy, o)
        o.data.materials.clear()
        o.data.materials.append(material)


def dress_surfaces(bpy):
    """Replace the GLB's materials, object by object (several GLB materials are
    shared between things that must now differ, e.g. 'sm_black_thing' is the
    stool legs, the taps and the downlight trims)."""
    stone = sm.scanned(bpy, 'Limestone slab walls', 'wall', rough=(.62, .9), hue=.5, sat=.5, val=.97, normal=1.2)
    floor = sm.scanned(bpy, 'Honed travertine floor', 'floor', rough=(.32, .6), sat=.7, val=.9, normal=.9)
    # The splashback is the floor's travertine turned on end, a shade lighter.
    splash = sm.scanned(bpy, 'Travertine splashback', 'floor', rough=(.3, .55), sat=.75, val=1.0, normal=.9, rotate=True)
    # Slatted fronts: grain runs along the slats, as cut.
    walnut = sm.scanned(bpy, 'Oiled walnut joinery', 'walnut', rough=(.38, .55), hue=.49, sat=1.1, val=.62, rotate=True)
    teak = sm.scanned(bpy, 'Oiled teak stool seat', 'teak', rough=(.42, .6), hue=.52, sat=1.15, val=.5)
    solid = sm.plain(bpy, 'Warm white solid surface', (.74, .71, .66), .2, drift=.02, coat=.15)
    bronze = sm.plain(bpy, 'Dark bronze shower profile', (.075, .058, .042), .42, metallic=1.0)
    legs = sm.plain(bpy, 'Blackened bronze stool legs', (.045, .038, .032), .42, metallic=1.0)
    brass = sm.brass(bpy)
    plaster = sm.plain(bpy, 'Warm white ceiling plaster', (.74, .71, .65), .9, drift=.03)
    mirror = sm.plain(bpy, 'Silvered mirror', (.93, .93, .92), .015, metallic=1.0)
    trim = sm.plain(bpy, 'White downlight trim', (.78, .77, .74), .45)
    ceramic = sm.plain(bpy, 'Matte stoneware glaze', (.70, .66, .60), .55, drift=.03)

    walls = _meshes(bpy, 'Cube')                          # room shell + ceiling plane
    shell = [o for o in walls if o.name.startswith('Cube_Wall pattern')]
    ceiling = [o for o in walls if o not in shell]
    sd.cut_window(bpy, shell[0])
    _assign(bpy, shell, stone, uv=True)
    _assign(bpy, ceiling, plaster)
    _assign(bpy, _meshes(bpy, 'Plane.004'), plaster)       # south wall upper band
    # Floor slab, skirting, shower tray and bench, and the stone plinth by the
    # camera (Cube.030/.031) in the same honed travertine.
    _assign(bpy, _meshes(bpy, 'Cube.047', 'Cube.035', 'Cube.037', 'Cube.030', 'Cube.031'), floor, uv=True)
    # The GLB floor slab is a grid of 2.4 m tiles with dark grooves between
    # them; under the scanned 0.5 m tiles that drew a second, coarser grid.
    # One flat slab at the physics floor height (FLOOR_Z, 2 mm above the GLB's
    # tile tops) replaces it, so the floor the stools land on is the floor the
    # camera sees.
    for o in _meshes(bpy, 'Cube.029'):
        o.hide_render = True
    slab = sd._box(bpy, 'Travertine floor slab', (-8.6, -5.6, FLOOR_Z - .06), (11.5, 4.9, FLOOR_Z), floor)
    sm.world_box_uv(bpy, slab)
    _assign(bpy, _meshes(bpy, 'Plane'), splash, uv=True)   # splashback behind the mirror
    _assign(bpy, _meshes(bpy, 'Cube.040', 'Cube.028'), walnut, uv=True)
    _assign(bpy, _meshes(bpy, 'Cube.038', 'bathtub'), solid)
    _assign(bpy, _meshes(bpy, 'Cube.021'), mirror)
    seat = [o for o in _meshes(bpy, STOOL_ASSEMBLY) if o.name.startswith('Cube.045')]
    _assign(bpy, seat, teak, uv=True)
    _assign(bpy, _meshes(bpy, 'Cylinder.062', 'Cylinder.063', 'Cylinder.064'), legs)
    # Taps, tub filler, shower set, paper holder, sconce bodies: one brass.
    metal = ['Cylinder.015', 'Cylinder.016', 'Cylinder.017', 'Cylinder.047', 'Cylinder.048',
             'Cylinder.018', 'Cylinder.019', 'Cube.020', 'Cylinder.037',
             'Cylinder.020', 'Cylinder.021', 'Cylinder.022', 'Cylinder.023', 'Cylinder.024',
             'Cylinder.025', 'Cylinder.034', 'Cylinder.036', 'BezierCurve', 'Cube.036',
             'Cylinder.039', 'Cylinder.041', 'Empty.003', 'Empty.004',
             'Cube.032', 'Cube.033', 'Cube.034',
             'Cube.001', 'Cylinder.008', 'Cylinder.010', 'Cylinder.011', 'Cylinder.012', 'Cylinder.032', 'Cylinder.033',
             'Cube.041', 'Cylinder.049', 'Cylinder.051', 'Cylinder.052', 'Cylinder.053', 'Cylinder.056', 'Cylinder.057',
             'Cylinder.014', 'Cylinder.055', 'Cylinder.009', 'Cylinder.050']
    _assign(bpy, _meshes(bpy, *metal), brass)
    _assign(bpy, _meshes(bpy, 'Cube.014', 'Cube.019', 'Cube.025', 'Cube.026'), sm.thin_glass(bpy))
    _assign(bpy, _meshes(bpy, 'Cube.027'), bronze)        # shower screen profiles
    _assign(bpy, _meshes(bpy, 'Cylinder.043', 'Cylinder.045', 'Cylinder.058', 'Cylinder.060'), trim)
    # Soap pump: amber glass bottle, brass pump.
    soap = _meshes(bpy, 'Liquid soap holder')
    _assign(bpy, [o for o in soap if 'Glass' in o.name], sm.amber_glass(bpy))
    _assign(bpy, [o for o in soap if 'PLastic' in o.name], brass)
    # Vase on the vanity and the floor vase under the fig: stoneware.
    for o in bpy.context.scene.objects:
        if o.type != 'MESH':
            continue
        for slot in o.material_slots:
            m = slot.material
            if m is None:
                continue
            if m.name == 'Gold_bqm':
                slot.material = brass
            elif m.name.startswith('Vase_White_bqm'):
                slot.material = ceramic
            elif m.name == 'Towel':
                slot.material = bpy.data.materials.get('Oatmeal towel') or sm.tinted(bpy, m, 'Oatmeal towel', (.93, .86, .74), .9)
            elif m.name == 'Wax_candle_beige':
                m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.80, .74, .62, 1)
                m.node_tree.nodes['Principled BSDF'].inputs['Subsurface Weight'].default_value = .4
                m.node_tree.nodes['Principled BSDF'].inputs['Subsurface Scale'].default_value = .01
    return dict(stone=stone, floor=floor, solid=solid, brass=brass)


def light_room(bpy, scene):
    """Twilight through the window plus the room's own fixtures."""
    sd.dusk_world(bpy, scene)
    discs = _meshes(bpy, 'Cylinder.044', 'Cylinder.046', 'Cylinder.059', 'Cylinder.061')
    discs = [o for o in discs if o.name.endswith('emission_0')]
    _assign(bpy, discs, sm.glowing(bpy, 'Downlight lens', sd.CAN_COLOUR, 25.0))
    sd.downlights(bpy, scene, discs, power=750.0)
    shades = _meshes(bpy, 'Cylinder.013', 'Cylinder.054')
    _assign(bpy, shades, sm.glowing(bpy, 'Opal sconce glass', sd.SCONCE_COLOUR, 9.0, (.9, .88, .84)))
    for shade in shades:
        sd.bulb_in_shade(bpy, scene, shade, power=60.0, radius=.05)
    halo = _meshes(bpy, 'Cube.039')
    _assign(bpy, halo, sm.glowing(bpy, 'Mirror LED halo', sd.CAN_COLOUR, 4.0))
    for m in bpy.data.materials:
        if m.name == 'Flame' and m.use_nodes:
            m.node_tree.nodes['Principled BSDF'].inputs['Emission Strength'].default_value = 25.0


# Poly Haven props in the free corner under the window (x < -1.3 m; the
# stools never pass x = -0.22 m). Positions are bounding-box anchors.
PROPS = (
    dict(stem='mid_century_lounge_chair', name='Leather lounge chair', x=-2.75, y=2.55, z=FLOOR_Z,
         face_towards=(1.0, -1.5)),
    dict(stem='side_table_tall_01', name='Side table', x=-1.75, y=3.75, z=FLOOR_Z),
)


def furnish(bpy, scene):
    placed = [sd.place_model(bpy, **spec) for spec in PROPS]
    table = next(p for p in placed if p['name'] == 'Side table')
    tray = bpy.data.objects[CANDLE_TRAY]
    tray_meshes = sd.move_subtree_onto(bpy, tray, (table['bbox_min'][0] + table['bbox_max'][0]) / 2,
                                       (table['bbox_min'][1] + table['bbox_max'][1]) / 2, table['bbox_max'][2])
    cup = sd.place_model(bpy, 'brass_vase_04', 'Brass tooth mug', x=3.05, y=4.18, z=1.81)
    placed += [cup, dict(name='Candle tray', meshes=tray_meshes)]
    return placed


# Static GLB dressing the stools never collide with (no collider): checked
# for clearance and occlusion together with the Poly Haven props.
GLB_DECOR = ('Plane.005', 'Plane.003', 'Liquid soap holder', 'Vase_Hemispheric-Steel-Pedestal_A_spring-summer-autumn',
             'Flower_Bellflower_C_spring-summer', 'Flower_Bellflower_E_spring-summer', 'Flower_Bellflower_F_spring-summer',
             'Cylinder.015', 'Cylinder.016', 'Cylinder.017', 'Cylinder.047', 'Cylinder.048',
             'Cylinder.018', 'Cylinder.019', 'Cube.020', 'Cylinder.037',
             'Decorated candle.001', 'Plant_Ficus_A_spring-summer-autumn',
             'Vase_Diamond-Pattern-Glazed-Ceramics_A_spring-summer-autumn', 'Slippers_leather_right', 'z',
             'Cube.001', 'Cube.041', 'Cylinder.013', 'Cylinder.054')


def decor_for_checks(bpy, placed):
    decor = {}
    for name in GLB_DECOR:
        root = bpy.data.objects.get(name)
        if root is not None:
            decor[name] = [o for o in _subtree(root) if o.type == 'MESH']
    for p in placed:
        decor[p['name']] = p['meshes']
    return decor


def build_environment(bpy, scene):
    imported = import_bathroom(bpy)
    mats = dress_surfaces(bpy)
    complete_northeast_wall(bpy, scene, mats['stone'])
    sd.build_window(bpy, mats['stone'], mats['floor'])
    light_room(bpy, scene)
    placed = furnish(bpy, scene)
    return dict(imported=imported, placed=placed)
