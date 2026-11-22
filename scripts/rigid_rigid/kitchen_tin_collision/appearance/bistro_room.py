"""A Paris bistro corner at blue hour, built around the solver's table and room.

Appearance only: the simulator never imports this module.  Every plane it
builds on comes from scene_geometry.py -- the table box the tins slide on, the
floor and the two walls the camera sees -- so the surfaces the render draws are
the surfaces the solver uses.

The corner: a table under a red-and-white checked cotton cloth, leather dining
chairs, an old terrazzo floor, mahogany panelling on the back wall and a
shop-front window on the right with the blue evening outside.  Light comes only
from things that are in the room: two brass chandeliers whose bulbs are the
emitters (one over this table, one over the next table, out of shot), a candle
burning on the cloth, and the twilight sky through the window.  No hidden fill
lamps.  The street photograph outside the window is seen by camera rays only;
what lights the room through the glass is a smooth twilight sky (see
``twilight_world``).

Every scanned asset is CC0 from Poly Haven and lives in
``assets/polyhaven/kitchen_tin_collision``; ``used_files`` lists them.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from pathlib import Path
from scene_geometry import (TABLE_TOP_Z, TABLE_HALF_X, TABLE_HALF_Y, FLOOR_Z, ROOM_X, ROOM_Y,
                            ROOM_TOP_Z)

ASSETS = _pcve_asset('polyhaven/kitchen_tin_collision')

# --- the tablecloth ------------------------------------------------------------
# Cotton gingham: thickness, the radius it rolls over the table edge with, and
# how far it hangs.  The flat top is the solver's box; the table under it is
# scaled so that no part of it reaches past the box (see place_table), so the
# hanging cloth only has to stand off the box side by its own thickness.
CLOTH_THICK_M = .0016
CLOTH_ROLL_M = .008
CLOTH_DROP_M = .235
CLOTH_STANDOFF_M = .0015          # air between the box side and the cloth's inner face
CLOTH_TILE_M = .40                # fabric_pattern_07 is a 400 x 400 mm scan
CLOTH_UV_OFFSET = (.137, .061)    # where the sheet starts on the scan
# Laundry creases of a sheet folded in half each way, then in half again along
# its length: sheet coordinates (metres from the table centre) of the folds,
# their width and their height.
CLOTH_CREASES_U = (-.387, 0., .387)
CLOTH_CREASES_V = (0.,)
CLOTH_CREASE_W = .010
CLOTH_CREASE_H = .0030

# --- the room --------------------------------------------------------------------
WALL_THICK_M = .30
# Mahogany panelling: the scan is 2.1 m square, two panels across and five rails
# up, so a rail lands every 0.42 m.  Three rows of panels and a cap rail on top.
PANEL_TILE_M = 2.10
WAINSCOT_TOP_M = 1.26             # above the floor
WAINSCOT_PROUD_M = .022           # the panelling stands this far off the plaster
FLOOR_TILE_M = 2.00               # old_mosaic_floor: 3 x 3 cast terrazzo slabs
PLASTER_TILE_M = 2.00             # plastered_wall
# Shop-front window in the +x wall, inside face on ROOM_X[1].
WINDOW_Y = (-1.85, 1.02)
WINDOW_SILL_M = .30               # above the floor: a low stall riser under the glass
WINDOW_HEAD_M = 2.45
WINDOW_MULLIONS_Y = (-.90, .06)
WINDOW_TRANSOM_M = 2.02           # above the floor
GLASS_DEPTH_M = .19               # glazing plane, measured from the inside face
FRAME_MEMBER_M = (.06, .075)      # depth, face width
FRAME_COLOUR = (.018, .046, .036)  # Parisian shop-front green
# Cafe curtain ("brise-bise"): white cotton voile gathered on a brass rod across
# the lower part of the glass, so from the tables the street pavement is hidden
# and only the evening above it shows.  Heights above the floor; the rod stands
# this far in from the glazing.
CAFE_ROD_M = .745
CAFE_ROD_OFF_GLASS_M = .065
CAFE_ROD_RADIUS_M = .006
CAFE_HEM_GAP_M = .015              # hem above the sill board
CAFE_PLEAT_M = (.055, .083)        # the two pleat wavelengths of the gathering
CAFE_PLEAT_DEPTH_M = (.011, .008)  # pleat amplitude at the heading and at the hem
CAFE_TILE_M = .29                  # stretch_poplin weave scan, 291 x 281 mm
VOILE_COLOUR = (.86, .84, .78)
VOILE_SHEER = .30                  # share of light that passes straight through

# --- furniture ---------------------------------------------------------------------
# (x, y, yaw) of each chair; yaw 0 faces -y.  Bounding-box anchors are applied
# after the turn.  Pushed in to the cloth, each a few degrees off square, as
# chairs are when people have just got up.
CHAIRS = (
    dict(x=-.265, y_min=TABLE_HALF_Y + .045, yaw_deg=3.5),
    dict(x=.255, y_min=TABLE_HALF_Y + .052, yaw_deg=-4.0),
    dict(x_min=TABLE_HALF_X + .050, y=.035, yaw_deg=-90. + 5.),
    dict(x_max=-TABLE_HALF_X - .085, y=-.045, yaw_deg=90. - 9.),
)
CANDLE_XY = (-.335, .212)          # wooden candlestick on the back-left of the cloth
CHANDELIERS_XY = ((.02, .03), (-1.80, .12))
# The two scans used for the chandeliers and the candle carry their own
# real-world sizes; nothing is rescaled except the table (see place_table).

# --- light -------------------------------------------------------------------------
BULB_COLOUR = (1.0, .70, .45)      # tungsten, as a camera balanced for ~3200 K records it
BULB_STRENGTH = 700.
FLAME_COLOUR = (1.0, .58, .22)     # ~1900 K candle flame
FLAME_STRENGTH = 160.
# Blue hour: the sun is a few degrees under the horizon, the sky is a smooth
# blue, brightest low in the west.  Radiance of the sky dome that lights the
# room through the glass:
SKY_ZENITH = (.050, .085, .205)
SKY_HORIZON = (.120, .150, .240)
SKY_GROUND = (.020, .022, .028)
SKY_STRENGTH = 1.8
# The street photograph seen through the window (camera rays only).  Turned so
# the lit facades across the courtyard sit in the window, and scaled to the
# same brightness as the sky dome that lights the room.
WINDOW_VIEW = 'evening_museum_courtyard_4k.hdr'
WINDOW_VIEW_TURN_DEG = 205.
WINDOW_VIEW_STRENGTH = .30

TEXTURE_SETS = (('fabric_pattern_07', 'col_1'), ('old_mosaic_floor', 'diff'),
                ('wooden_panels', 'diff'), ('plastered_wall', 'diff'))
MODELS = ('wooden_table_02', 'dining_chair_02', 'wooden_candlestick', 'Chandelier_02')
VOILE_SCAN = 'stretch_poplin'      # only its roughness and normal maps: the voile is white

STATIC_TAG = 'pcve_static'        # custom property on everything the tins must keep clear of


def used_files():
    """Every file of the scene's Poly Haven folder that the render reads."""
    files = []
    for stem, colour in TEXTURE_SETS:
        for kind in (colour, 'rough', 'nor_gl'):
            files.append(ASSETS / f'{stem}_{kind}_2k.jpg')
    for model in MODELS:
        folder = ASSETS / model
        files += sorted(p for p in folder.rglob('*') if p.is_file())
    files += [ASSETS / f'{VOILE_SCAN}_{kind}_2k.jpg' for kind in ('rough', 'nor_gl')]
    files.append(ASSETS / WINDOW_VIEW)
    return files


# ------------------------------------------------------------------ materials

def _new_material(bpy, name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    return mat, mat.node_tree.nodes, mat.node_tree.links, mat.node_tree.nodes.get('Principled BSDF')


def scanned(bpy, name, stem, tile_m, colour='diff', coord='UV', tint=None, rough_gain=1.,
            rough_min=0., normal_strength=1., offset=(0., 0.)):
    """A Poly Haven texture set at its real size: ``tile_m`` metres per repeat.

    Meshes built here carry UVs in metres, so 'UV' coordinates divided by the
    tile give the scan its real scale on every face.
    """
    mat, nodes, links, bsdf = _new_material(bpy, name)
    coords = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Location'].default_value = (offset[0] / tile_m, offset[1] / tile_m, 0.)
    mapping.inputs['Scale'].default_value = (1. / tile_m, 1. / tile_m, 1.)
    links.new(coords.outputs[coord], mapping.inputs['Vector'])

    def image(kind, colour_data):
        node = nodes.new('ShaderNodeTexImage')
        path = ASSETS / f'{stem}_{kind}_2k.jpg'
        if not path.is_file():
            raise FileNotFoundError(f'Missing local asset: {path}')
        node.image = bpy.data.images.load(str(path), check_existing=True)
        if not colour_data:
            node.image.colorspace_settings.name = 'Non-Color'
        node.extension = 'REPEAT'
        node.interpolation = 'Cubic'
        links.new(mapping.outputs['Vector'], node.inputs['Vector'])
        return node

    base = image(colour, True).outputs['Color']
    if tint is not None:
        mix = nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.
        links.new(base, mix.inputs['A'])
        mix.inputs['B'].default_value = (*tint, 1.)
        base = mix.outputs['Result']
    links.new(base, bsdf.inputs['Base Color'])
    rough = image('rough', False).outputs['Color']
    if rough_gain != 1. or rough_min > 0.:
        gain = nodes.new('ShaderNodeMath')
        gain.operation = 'MULTIPLY_ADD'
        gain.inputs[1].default_value = rough_gain
        gain.inputs[2].default_value = 0.
        gain.use_clamp = True
        links.new(rough, gain.inputs[0])
        floor = nodes.new('ShaderNodeMath')
        floor.operation = 'MAXIMUM'
        floor.inputs[1].default_value = rough_min
        links.new(gain.outputs['Value'], floor.inputs[0])
        rough = floor.outputs['Value']
    links.new(rough, bsdf.inputs['Roughness'])
    normal = nodes.new('ShaderNodeNormalMap')
    normal.inputs['Strength'].default_value = normal_strength
    links.new(image('nor_gl', False).outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def painted(bpy, name, colour, roughness=.42, grain=.35):
    """Brushed enamel paint on joinery: a flat colour with faint brush marks."""
    mat, nodes, links, bsdf = _new_material(bpy, name)
    bsdf.inputs['Base Color'].default_value = (*colour, 1.)
    coords = nodes.new('ShaderNodeTexCoord')
    stretch = nodes.new('ShaderNodeMapping')
    stretch.inputs['Scale'].default_value = (40., 900., 40.)
    links.new(coords.outputs['Object'], stretch.inputs['Vector'])
    brush = nodes.new('ShaderNodeTexNoise')
    brush.inputs['Scale'].default_value = 1.
    brush.inputs['Detail'].default_value = 6.
    links.new(stretch.outputs['Vector'], brush.inputs['Vector'])
    rough = nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value = roughness - .06
    rough.inputs['To Max'].default_value = roughness + .06
    links.new(brush.outputs['Fac'], rough.inputs['Value'])
    links.new(rough.outputs['Result'], bsdf.inputs['Roughness'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .05 * grain
    bump.inputs['Distance'].default_value = .0004
    links.new(brush.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def thin_glass(bpy):
    """Thin float glass: a 4 % Fresnel reflection over a see-through layer.

    Shaded as transparent so rays through it stay camera rays: the world then
    shows the street photograph to the camera alone, while the room is lit by
    the twilight sky.  Both faces reflect as air-to-glass: Cycles' Fresnel node
    inverts the IOR on a back face, which would make a ray leaving the pane at
    more than 41 degrees totally reflect and turn the window black, so the
    inverse IOR is fed on back faces to cancel that.
    """
    existing = bpy.data.materials.get('Shop-front float glass')
    if existing is not None:
        return existing
    mat = bpy.data.materials.new('Shop-front float glass')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    for node in [n for n in nodes if n.type != 'OUTPUT_MATERIAL']:
        nodes.remove(node)
    clear = nodes.new('ShaderNodeBsdfTransparent')
    reflection = nodes.new('ShaderNodeBsdfGlossy')
    reflection.inputs['Roughness'].default_value = 0.
    fresnel = nodes.new('ShaderNodeFresnel')
    geometry = nodes.new('ShaderNodeNewGeometry')
    ior = nodes.new('ShaderNodeMath')
    ior.operation = 'MULTIPLY_ADD'
    ior.inputs[1].default_value = 1. / 1.52 - 1.52
    ior.inputs[2].default_value = 1.52
    links.new(geometry.outputs['Backfacing'], ior.inputs[0])
    links.new(ior.outputs['Value'], fresnel.inputs['IOR'])
    pane = nodes.new('ShaderNodeMixShader')
    links.new(fresnel.outputs['Fac'], pane.inputs['Fac'])
    links.new(clear.outputs['BSDF'], pane.inputs[1])
    links.new(reflection.outputs['BSDF'], pane.inputs[2])
    links.new(pane.outputs['Shader'], nodes['Material Output'].inputs['Surface'])
    return mat


def emitter(bpy, name, colour, strength):
    mat, nodes, links, bsdf = _new_material(bpy, name)
    nodes.remove(bsdf)
    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = (*colour, 1.)
    emission.inputs['Strength'].default_value = strength
    links.new(emission.outputs['Emission'], nodes['Material Output'].inputs['Surface'])
    return mat


# ------------------------------------------------------------------ geometry

def _tag(obj, role='static'):
    obj[STATIC_TAG] = role
    return obj


def box(bpy, name, lo, hi, mat, role='static'):
    """An axis-aligned box whose UVs are world metres on every face, so a
    scanned material lands at its real size whatever the face's orientation."""
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    verts = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    faces = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    uv = mesh.uv_layers.new(name='UVMap')
    mesh.update()
    for poly in mesh.polygons:
        n = poly.normal
        for li in poly.loop_indices:
            x, y, z = verts[mesh.loops[li].vertex_index]
            if abs(n.z) > .5:
                uv.data[li].uv = (x, y)
            elif abs(n.x) > .5:
                uv.data[li].uv = (y, z - FLOOR_Z)
            else:
                uv.data[li].uv = (x, z - FLOOR_Z)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if mat is not None:
        mesh.materials.append(mat)
    return _tag(obj, role)


# ------------------------------------------------------------------ models

def _import(bpy, path):
    if not Path(path).is_file():
        raise FileNotFoundError(f'Missing local asset: {path}')
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [o for o in bpy.data.objects if o not in before]


def _anchor(bpy, root, meshes, anchor):
    """Move ``root`` so its meshes' world bounding box sits on ``anchor``."""
    from mathutils import Vector
    root.location = (0., 0., 0.)
    bpy.context.view_layer.update()
    points = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    shift = Vector((0., 0., 0.))
    for axis, index in (('x', 0), ('y', 1)):
        if axis in anchor:
            shift[index] = anchor[axis] - (lo[index] + hi[index]) / 2.
        elif f'{axis}_min' in anchor:
            shift[index] = anchor[f'{axis}_min'] - lo[index]
        elif f'{axis}_max' in anchor:
            shift[index] = anchor[f'{axis}_max'] - hi[index]
    if 'z' in anchor:
        shift.z = anchor['z'] - lo.z
    root.location = shift
    bpy.context.view_layer.update()
    return lo + shift, hi + shift


def place_model(bpy, model, name, *, yaw_deg=0., **anchor):
    """Import a Poly Haven glTF at its own real-world size, turn it about z and
    set its bounding box on an anchor: ``x``/``y`` (box centre),
    ``x_min``/``x_max``/``y_min``/``y_max`` (box faces) and ``z`` (bottom of
    the box).  Returns the root, its meshes and the placed box."""
    imported = _import(bpy, ASSETS / model / f'{model}.gltf')
    for obj in imported:
        obj.animation_data_clear()
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for obj in imported:
        if obj.parent is None:
            world = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = world
    root.rotation_euler.z = math.radians(yaw_deg)
    meshes = [o for o in imported if o.type == 'MESH']
    for obj in meshes:
        _tag(obj)
    return (root, meshes, _anchor(bpy, root, meshes, anchor))


def place_table(bpy):
    """wooden_table_02, uniformly scaled so it fits inside the solver's box.

    The scan is 1.134 x 0.706 m over its widest part; one factor brings that
    width down to the box's 0.660 m depth, which puts its top at 0.7475 m -- a
    standard table height -- and leaves the whole table inside the box's
    footprint, so the cloth can hang straight down the box side without
    touching wood.  The table stands on the floor and its top must then meet
    the underside of the cloth; both are checked.
    """
    anchor = dict(x=0., y=0., z=FLOOR_Z)
    root, meshes, (lo, hi) = place_model(bpy, 'wooden_table_02', 'Bistro table (wooden_table_02)', **anchor)
    scale = min(2 * TABLE_HALF_X / (hi.x - lo.x), 2 * TABLE_HALF_Y / (hi.y - lo.y))
    root.scale = (scale, scale, scale)
    lo, hi = _anchor(bpy, root, meshes, anchor)
    top_gap = (TABLE_TOP_Z - CLOTH_THICK_M) - hi.z
    if abs(top_gap) > 5e-4:
        raise RuntimeError(f'Table top misses the cloth underside by {top_gap * 1000:.2f} mm')
    if max(abs(lo.x), abs(hi.x)) > TABLE_HALF_X + 1e-6 or max(abs(lo.y), abs(hi.y)) > TABLE_HALF_Y + 1e-6:
        raise RuntimeError('Table reaches past the solver box; the cloth would cut through it')
    for obj in meshes:
        obj[STATIC_TAG] = 'support'
    return dict(model='wooden_table_02', scale=round(scale, 5), height_m=round(hi.z - lo.z, 4),
                half_extents_m=[round(max(-lo.x, hi.x), 4), round(max(-lo.y, hi.y), 4)])


def _roll(e):
    """Outward offset and drop of a cloth point ``e`` metres past the flat top:
    a quarter turn of radius CLOTH_ROLL_M, then straight down."""
    r = CLOTH_ROLL_M
    if e <= 0.:
        return 0., 0.
    if e <= math.pi * r / 2:
        a = e / r
        return r * math.sin(a), r * (1. - math.cos(a))
    return r, r + (e - math.pi * r / 2)


def _side_params(flat_half, overhang):
    """Sheet coordinates from the centre outwards: 2 cm across the top, 1 mm
    through the roll, 1 cm down the drop, 2 mm through the hem."""
    s = [0.]
    while s[-1] < flat_half - .02:
        s.append(s[-1] + .02)
    s.append(flat_half)
    roll = math.pi * CLOTH_ROLL_M / 2
    for i in range(1, 9):
        s.append(flat_half + roll * i / 8)
    e = roll
    while e < overhang - 1e-6:
        e = min(overhang, e + (.002 if e > overhang - .014 else .01))
        s.append(flat_half + e)
    return s


def tablecloth(bpy, mat):
    """One sheet of gingham: flat over the solver's box, rolled over its edges,
    hanging CLOTH_DROP_M on all four sides in soft folds, its surplus falling
    into a cone at each corner and its hem turned under.

    The outer face of the flat part is exactly TABLE_TOP_Z out to within
    CLOTH_ROLL_M of the box edge (Solidify lays the thickness downwards), and
    the hanging cloth's inner face stands CLOTH_STANDOFF_M off the box side, so
    the surface a tin slides on and the edge it would leave from are the box's.
    """
    fx = TABLE_HALF_X + CLOTH_STANDOFF_M + CLOTH_THICK_M - CLOTH_ROLL_M
    fy = TABLE_HALF_Y + CLOTH_STANDOFF_M + CLOTH_THICK_M - CLOTH_ROLL_M
    over = CLOTH_DROP_M - CLOTH_ROLL_M + math.pi * CLOTH_ROLL_M / 2
    xs = [-v for v in reversed(_side_params(fx, over)[1:])] + _side_params(fx, over)
    ys = [-v for v in reversed(_side_params(fy, over)[1:])] + _side_params(fy, over)

    def flare(hang):
        # Cotton is stiff enough to stand a little off the table side lower down.
        return .009 * min(1., hang / .18) ** 2

    def folds(along, hang, phase):
        # Soft vertical folds, growing towards the hem (wavelengths 18-30 cm).
        # They only ever bulge outwards: the table side is behind the cloth.
        a = .014 * min(1., hang / .16) ** 1.4
        return a * .5 * (1. + .6 * math.sin(along * 21. + phase) + .4 * math.sin(along * 34. + 2.3 * phase))

    def hem(ex, ey):
        t = max((ex - (over - .012)) / .012, (ey - (over - .012)) / .012, 0.)
        return -.004 * min(1., t) ** 2

    verts, uvs = [], []
    for v in ys:
        for u in xs:
            sx, sy = math.copysign(1., u), math.copysign(1., v)
            ex, ey = abs(u) - fx, abs(v) - fy
            curl = hem(ex, ey)
            if ex > 0. and ey > 0.:
                e = math.hypot(ex, ey)
                theta = math.atan2(ey, ex)
                out, drop = _roll(e)
                hang = max(0., drop - .03)
                # The corner's surplus stands out along the diagonal in a cone
                # whose tip hangs lowest, as a square cloth's corner does.
                # (No hem curl here: turned under at the cone's tip it opens a
                # dark slit into the cone that a hanging corner does not show.)
                out += flare(hang) + .10 * hang * math.sin(2 * theta) ** 2
                # Near the top the cloth follows the table's square corner; it
                # rounds off into the cone over the first 8 cm of the hang.
                c, s = math.cos(theta), math.sin(theta)
                w = min(1., hang / .08)
                dx = c / max(c, s) * (1. - w) + c * w
                dy = s / max(c, s) * (1. - w) + s * w
                x = sx * (fx + out * dx)
                y = sy * (fy + out * dy)
                z = TABLE_TOP_Z - drop
            elif ex > 0. or ey > 0.:
                on_x = ex > 0.
                out, drop = _roll(ex if on_x else ey)
                hang = max(0., drop - .03)
                along = v if on_x else u
                limit = fy if on_x else fx
                fade = min(1., max(0., (limit - abs(along)) / .10))
                phase = (1.1 if on_x else .5) + (0. if (u if on_x else v) > 0 else 2.4)
                out += flare(hang) + folds(along, hang, phase) * fade + curl
                x = sx * (fx + out) if on_x else u
                y = v if on_x else sy * (fy + out)
                z = TABLE_TOP_Z - drop
            else:
                x, y, z = u, v, TABLE_TOP_Z
            verts.append((x, y, z))
            uvs.append((u, v))
    nx = len(xs)
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i)
             for j in range(len(ys) - 1) for i in range(nx - 1)]
    mesh = bpy.data.meshes.new('Tablecloth')
    mesh.from_pydata(verts, [], faces)
    layer = mesh.uv_layers.new(name='UVMap')
    for poly in mesh.polygons:
        poly.use_smooth = True
        for li in poly.loop_indices:
            layer.data[li].uv = uvs[mesh.loops[li].vertex_index]
    mesh.update()
    obj = bpy.data.objects.new('Tablecloth', mesh)
    bpy.context.collection.objects.link(obj)
    mesh.materials.append(mat)
    solid = obj.modifiers.new('Cotton thickness', 'SOLIDIFY')
    solid.thickness = CLOTH_THICK_M
    solid.offset = -1.
    solid.use_even_offset = True
    _tag(obj, 'support')
    top = [z for x, y, z in verts if abs(x) <= TABLE_HALF_X - CLOTH_ROLL_M and abs(y) <= TABLE_HALF_Y - CLOTH_ROLL_M]
    if max(abs(z - TABLE_TOP_Z) for z in top) > 1e-9:
        raise RuntimeError('The cloth top is not the simulator table top')
    inside = [(x, y) for x, y, z in verts if z < TABLE_TOP_Z - CLOTH_ROLL_M - 1e-6
              and abs(x) < TABLE_HALF_X + CLOTH_STANDOFF_M + CLOTH_THICK_M - 1e-6
              and abs(y) < TABLE_HALF_Y + CLOTH_STANDOFF_M + CLOTH_THICK_M - 1e-6]
    if inside:
        raise RuntimeError(f'{len(inside)} hanging cloth vertices fall inside the table box')
    return obj


def gingham(bpy):
    """Red-and-white cotton gingham, a scanned 400 mm swatch at real size, with
    the creases a laundered cloth keeps from being folded in quarters.

    The creases are shading only (a bump on the sheet's own coordinates): the
    cloth's top stays the solver's plane to the micrometre.
    """
    mat = scanned(bpy, 'Red gingham cotton (fabric_pattern_07)', 'fabric_pattern_07', CLOTH_TILE_M,
                  colour='col_1', rough_min=.62, offset=CLOTH_UV_OFFSET)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    bsdf.inputs['Sheen Weight'].default_value = .45
    bsdf.inputs['Sheen Roughness'].default_value = .55
    bsdf.inputs['Specular IOR Level'].default_value = .35
    coords = next(n for n in nodes if n.type == 'TEX_COORD')
    sheet = nodes.new('ShaderNodeSeparateXYZ')
    links.new(coords.outputs['UV'], sheet.inputs['Vector'])
    ridges = []
    for axis, centres in (('X', CLOTH_CREASES_U), ('Y', CLOTH_CREASES_V)):
        for c in centres:
            off = nodes.new('ShaderNodeMath'); off.operation = 'SUBTRACT'
            off.inputs[1].default_value = c
            links.new(sheet.outputs[axis], off.inputs[0])
            # A soft ridge CLOTH_CREASE_W wide: 1 on the fold, 0 away from it.
            ridge = nodes.new('ShaderNodeMapRange')
            ridge.interpolation_type = 'SMOOTHERSTEP'
            ridge.inputs['From Min'].default_value = -CLOTH_CREASE_W
            ridge.inputs['From Max'].default_value = 0.
            fold = nodes.new('ShaderNodeMath'); fold.operation = 'ABSOLUTE'
            links.new(off.outputs['Value'], fold.inputs[0])
            neg = nodes.new('ShaderNodeMath'); neg.operation = 'MULTIPLY'
            neg.inputs[1].default_value = -1.
            links.new(fold.outputs['Value'], neg.inputs[0])
            links.new(neg.outputs['Value'], ridge.inputs['Value'])
            ridges.append(ridge.outputs['Result'])
    total = ridges[0]
    for r in ridges[1:]:
        add = nodes.new('ShaderNodeMath'); add.operation = 'MAXIMUM'
        links.new(total, add.inputs[0]); links.new(r, add.inputs[1])
        total = add.outputs['Value']
    normal_map = next(n for n in nodes if n.type == 'NORMAL_MAP')
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 1.
    bump.inputs['Distance'].default_value = CLOTH_CREASE_H
    links.new(total, bump.inputs['Height'])
    links.new(normal_map.outputs['Normal'], bump.inputs['Normal'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


# ------------------------------------------------------------------ the window

def voile(bpy):
    """White cotton voile: diffuse on both sides, part of the light passing
    through it scattered (translucent) and part straight through (sheer)."""
    mat, nodes, links, bsdf = _new_material(bpy, 'White cotton voile')
    bsdf.inputs['Base Color'].default_value = (*VOILE_COLOUR, 1.)
    bsdf.inputs['Sheen Weight'].default_value = .3
    coords = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1. / CAFE_TILE_M, 1. / CAFE_TILE_M, 1.)
    links.new(coords.outputs['UV'], mapping.inputs['Vector'])
    maps = {}
    for kind in ('rough', 'nor_gl'):
        path = ASSETS / f'{VOILE_SCAN}_{kind}_2k.jpg'
        if not path.is_file():
            raise FileNotFoundError(f'Missing local asset: {path}')
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(path), check_existing=True)
        node.image.colorspace_settings.name = 'Non-Color'
        links.new(mapping.outputs['Vector'], node.inputs['Vector'])
        maps[kind] = node
    links.new(maps['rough'].outputs['Color'], bsdf.inputs['Roughness'])
    normal = nodes.new('ShaderNodeNormalMap')
    normal.inputs['Strength'].default_value = .5
    links.new(maps['nor_gl'].outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    through = nodes.new('ShaderNodeBsdfTranslucent')
    through.inputs['Color'].default_value = (*VOILE_COLOUR, 1.)
    links.new(normal.outputs['Normal'], through.inputs['Normal'])
    cloth = nodes.new('ShaderNodeMixShader')
    cloth.inputs['Fac'].default_value = .45
    links.new(bsdf.outputs['BSDF'], cloth.inputs[1])
    links.new(through.outputs['BSDF'], cloth.inputs[2])
    clear = nodes.new('ShaderNodeBsdfTransparent')
    sheer = nodes.new('ShaderNodeMixShader')
    sheer.inputs['Fac'].default_value = VOILE_SHEER
    links.new(cloth.outputs['Shader'], sheer.inputs[1])
    links.new(clear.outputs['BSDF'], sheer.inputs[2])
    links.new(sheer.outputs['Shader'], nodes['Material Output'].inputs['Surface'])
    return mat


def _brass(bpy):
    mat, nodes, links, bsdf = _new_material(bpy, 'Brushed brass')
    bsdf.inputs['Base Color'].default_value = (.78, .57, .28, 1.)
    bsdf.inputs['Metallic'].default_value = 1.
    bsdf.inputs['Roughness'].default_value = .28
    return mat


def cafe_curtain(bpy, x, bays, sill_z, face):
    """A brass rod across the window with a gathered voile panel in each bay,
    hanging from the rod to just above the sill board."""
    brass = bpy.data.materials.get('Brushed brass') or _brass(bpy)
    rod_z = FLOOR_Z + CAFE_ROD_M
    y0, y1 = bays[0][0] - face, bays[-1][1] + face
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=CAFE_ROD_RADIUS_M, depth=y1 - y0,
                                        location=(x, (y0 + y1) / 2, rod_z),
                                        rotation=(math.radians(90.), 0., 0.))
    rod = bpy.context.object
    rod.name = 'Cafe curtain rod'
    rod.data.materials.append(brass)
    _tag(rod)
    # Small brackets carry the rod from the jambs and the mullions.
    frame_face_x = x + CAFE_ROD_OFF_GLASS_M - FRAME_MEMBER_M[0] / 2
    posts = [y0 + face / 2] + [(a[1] + b[0]) / 2 for a, b in zip(bays, bays[1:])] + [y1 - face / 2]
    for i, yb in enumerate(posts):
        box(bpy, f'Cafe curtain rod bracket {i + 1}', (x - .006, yb - .008, rod_z - .012),
            (frame_face_x, yb + .008, rod_z + .004), brass)
    top, bottom = rod_z + CAFE_ROD_RADIUS_M * 2, sill_z + CAFE_HEM_GAP_M
    l1, l2 = CAFE_PLEAT_M
    d_top, d_hem = CAFE_PLEAT_DEPTH_M
    nz = max(2, round((top - bottom) / .02))
    voile_mat = bpy.data.materials.get('White cotton voile') or voile(bpy)
    for b, (ya, yb) in enumerate(bays):
        ya, yb = ya + .008, yb - .008
        ny = max(2, round((yb - ya) / .004))
        verts, uvs = [], []
        for j in range(nz + 1):
            z = top - (top - bottom) * j / nz
            depth = d_top + (d_hem - d_top) * j / nz
            for i in range(ny + 1):
                y = ya + (yb - ya) * i / ny
                phase = 1.7 * b
                off = depth * (.65 * math.sin(2 * math.pi * y / l1 + phase)
                               + .35 * math.sin(2 * math.pi * y / l2 + 2.3 * phase))
                verts.append((x + off, y, z))
                uvs.append((y, z))
        faces = [(j * (ny + 1) + i, j * (ny + 1) + i + 1, (j + 1) * (ny + 1) + i + 1, (j + 1) * (ny + 1) + i)
                 for j in range(nz) for i in range(ny)]
        mesh = bpy.data.meshes.new(f'Cafe curtain {b + 1}')
        mesh.from_pydata(verts, [], faces)
        layer = mesh.uv_layers.new(name='UVMap')
        for poly in mesh.polygons:
            poly.use_smooth = True
            for li in poly.loop_indices:
                layer.data[li].uv = uvs[mesh.loops[li].vertex_index]
        mesh.update()
        obj = bpy.data.objects.new(f'Cafe curtain {b + 1}', mesh)
        bpy.context.collection.objects.link(obj)
        mesh.materials.append(voile_mat)
        _tag(obj)


# ------------------------------------------------------------------ the room

def build_room(bpy):
    """Floor, ceiling, the panelled back wall and the shop-front window wall,
    plus plain plaster on the two walls behind the camera."""
    x0, x1 = ROOM_X
    y0, y1 = ROOM_Y
    floor_z, ceil_z = FLOOR_Z, ROOM_TOP_Z
    t = WALL_THICK_M
    floor = scanned(bpy, 'Terrazzo floor (old_mosaic_floor)', 'old_mosaic_floor', FLOOR_TILE_M,
                    rough_gain=.9, rough_min=.22, offset=(.31, .17))
    panel = scanned(bpy, 'Mahogany wall panelling (wooden_panels)', 'wooden_panels', PANEL_TILE_M,
                    tint=(.86, .78, .72), rough_gain=1.0, rough_min=.30)
    plaster = scanned(bpy, 'Warm limewash plaster (plastered_wall)', 'plastered_wall', PLASTER_TILE_M,
                      tint=(1.0, .86, .64), rough_min=.75)
    ceiling = scanned(bpy, 'Ceiling plaster (plastered_wall)', 'plastered_wall', PLASTER_TILE_M,
                      tint=(.96, .93, .86), rough_min=.8)
    rail = painted(bpy, 'Dark varnished cap rail', (.055, .022, .011), .32)
    frame = painted(bpy, 'Shop-front green paint', FRAME_COLOUR, .36)
    sill = painted(bpy, 'Varnished oak sill', (.20, .105, .045), .30)
    glass = thin_glass(bpy)

    # The floor stops at the window wall's outer face: past it, a ray through
    # the glass must reach the street photograph, not more mosaic.
    box(bpy, 'Floor', (x0 - t, y0 - t, floor_z - .05), (x1 + t, y1 + t, floor_z), floor)
    box(bpy, 'Ceiling', (x0 - t, y0 - t, ceil_z), (x1 + t, y1 + t, ceil_z + .05), ceiling)
    wain = floor_z + WAINSCOT_TOP_M
    proud = WAINSCOT_PROUD_M

    # Back wall: panelling up to the cap rail, plaster above, set back by the
    # panelling's thickness so the panel face is the solver's wall plane.
    box(bpy, 'Back wall panelling', (x0, y1, floor_z), (x1, y1 + proud, wain), panel)
    box(bpy, 'Back wall plaster', (x0, y1 + proud, wain), (x1 + t, y1 + t, ceil_z), plaster)
    box(bpy, 'Back wall masonry', (x0, y1 + proud, floor_z), (x1 + t, y1 + t, wain), plaster)
    box(bpy, 'Back wall cap rail', (x0, y1 - .022, wain - .012), (x1, y1 + proud, wain + .030), rail)

    # Window wall (+x): the opening is a gap between wall pieces, so the reveal
    # is the plaster of the pieces' own faces.
    wy0, wy1 = WINDOW_Y
    sill_z, head_z = floor_z + WINDOW_SILL_M, floor_z + WINDOW_HEAD_M
    box(bpy, 'Window wall below sill, panelling', (x1, wy0, floor_z), (x1 + proud, wy1, sill_z - .03), panel)
    box(bpy, 'Window wall below sill', (x1 + proud, wy0, floor_z), (x1 + t, wy1, sill_z - .03), plaster)
    box(bpy, 'Window wall above head', (x1 + proud, wy0, head_z), (x1 + t, wy1, ceil_z), plaster)
    for name, ya, yb in (('near', y0, wy0), ('corner', wy1, y1)):
        box(bpy, f'Window wall {name} pier panelling', (x1, ya, floor_z), (x1 + proud, yb, wain), panel)
        box(bpy, f'Window wall {name} pier', (x1 + proud, ya, floor_z), (x1 + t, yb + (t if name == 'corner' else 0.), ceil_z), plaster)
        box(bpy, f'Window wall {name} cap rail', (x1 - .022, ya, wain - .012), (x1 + proud, yb, wain + .030), rail)
    box(bpy, 'Window sill board', (x1 - .035, wy0 - .03, sill_z - .03), (x1 + GLASS_DEPTH_M - .02, wy1 + .03, sill_z), sill)

    # The shop-front frame: outer frame, two mullions and a transom, glazed.
    depth, face = FRAME_MEMBER_M
    gx = x1 + GLASS_DEPTH_M
    fx0, fx1 = gx - depth / 2, gx + depth / 2
    members = [('bottom rail', (fx0, wy0, sill_z), (fx1, wy1, sill_z + face * 1.4)),
               ('head', (fx0, wy0, head_z - face), (fx1, wy1, head_z)),
               ('near jamb', (fx0, wy0, sill_z), (fx1, wy0 + face, head_z)),
               ('corner jamb', (fx0, wy1 - face, sill_z), (fx1, wy1, head_z)),
               ('transom', (fx0, wy0, floor_z + WINDOW_TRANSOM_M - face / 2),
                (fx1, wy1, floor_z + WINDOW_TRANSOM_M + face / 2))]
    for i, my in enumerate(WINDOW_MULLIONS_Y):
        members.append((f'mullion {i + 1}', (fx0, my - face / 2, sill_z), (fx1, my + face / 2, head_z)))
    for name, lo, hi in members:
        box(bpy, f'Shop-front {name}', lo, hi, frame)
    pane = box(bpy, 'Shop-front glazing', (gx - .003, wy0 + face, sill_z + face * 1.4),
               (gx + .003, wy1 - face, head_z - face), glass, role='glass')
    pane.visible_shadow = True
    bays = [wy0 + face] + [v for my in WINDOW_MULLIONS_Y for v in (my - face / 2, my + face / 2)] + [wy1 - face]
    cafe_curtain(bpy, gx - CAFE_ROD_OFF_GLASS_M, list(zip(bays[::2], bays[1::2])), sill_z, face)

    # Two plain walls behind the camera close the room for bounce light.
    box(bpy, 'Near wall', (x0, y0 - t, floor_z), (x1 + t, y0, ceil_z), plaster)
    box(bpy, 'Dining room wall', (x0 - t, y0 - t, floor_z), (x0, y1 + t, ceil_z), plaster)
    portal_centre = (x1 + GLASS_DEPTH_M + .04, (wy0 + wy1) / 2, (sill_z + head_z) / 2)
    return dict(window=dict(y=list(WINDOW_Y), sill_z=sill_z, head_z=head_z, glass_x=gx),
                portal=dict(centre=portal_centre, size=(wy1 - wy0, head_z - sill_z)))


# ------------------------------------------------------------------ lights

def _aim(obj, point):
    from mathutils import Vector
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def hang_chandelier(bpy, xy, index):
    """Chandelier_02 hung from the ceiling; its own bulb material becomes the
    emitter, so the light comes out of the lamp the scan shows."""
    root, meshes, (lo, hi) = place_model(bpy, 'Chandelier_02', f'Brass chandelier {index}',
                                         x=xy[0], y=xy[1], z=0.)
    # Its ceiling rose goes against the ceiling.
    lo, hi = _anchor(bpy, root, meshes, dict(x=xy[0], y=xy[1], z=ROOM_TOP_Z - (hi.z - lo.z)))
    bulb = bpy.data.materials.get('Tungsten bulb') or emitter(bpy, 'Tungsten bulb', BULB_COLOUR, BULB_STRENGTH)
    for obj in meshes:
        for slot in obj.material_slots:
            if slot.material is not None and 'bulb' in slot.material.name.lower():
                slot.material = bulb
    return dict(model='Chandelier_02', bbox_min=[round(v, 4) for v in lo], bbox_max=[round(v, 4) for v in hi])


def light_candle(bpy):
    """wooden_candlestick on the cloth with its candle lit: a small teardrop
    flame on the wick is both what the camera sees and what lights the cloth."""
    root, meshes, (lo, hi) = place_model(bpy, 'wooden_candlestick', 'Wooden candlestick',
                                         yaw_deg=25., x=CANDLE_XY[0], y=CANDLE_XY[1], z=TABLE_TOP_Z)
    # The wick is the highest point of the scan; the flame sits on it.
    top = max((o.matrix_world @ v.co for o in meshes for v in o.data.vertices), key=lambda p: p.z)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, radius=1., location=(0, 0, 0))
    flame = bpy.context.object
    flame.name = 'Candle flame'
    peak = math.sqrt(.5 / 1.8) * (1. - .5 / 1.8) ** 1.3
    for v in flame.data.vertices:
        # Teardrop: round at the base, drawn to a point above.  Radius along
        # the height h in [0, 1] is sqrt(h) (1 - h)^1.3, widest a quarter up.
        h = (v.co.z + 1.) / 2.
        r = math.hypot(v.co.x, v.co.y)
        if r > 1e-9:
            k = math.sqrt(h) * (1. - h) ** 1.3 / peak / r
            v.co.x *= k
            v.co.y *= k
    flame.scale = (.0042, .0042, .0105)
    flame.location = (top.x, top.y, top.z + .0085)
    flame.data.materials.append(emitter(bpy, 'Candle flame', FLAME_COLOUR, FLAME_STRENGTH))
    flame.visible_shadow = False
    for poly in flame.data.polygons:
        poly.use_smooth = True
    return dict(model='wooden_candlestick', bbox_min=[round(v, 4) for v in lo], bbox_max=[round(v, 4) for v in hi],
                flame=[round(top.x, 4), round(top.y, 4), round(top.z + .0085, 4)])


def twilight_world(bpy, scene, portal):
    """The world: a smooth blue-hour sky for every ray that lights the room,
    the street photograph for camera rays only.

    Through the window the camera looks 8-21 degrees below the horizon, at the
    courtyard paving and the lit facades across it; those come from the
    photograph.  Lighting the room with the photograph would add its sodium
    street lamps as hard orange spots on the cloth, so the light that comes in
    is the sky's: zenith blue, paler toward the horizon, dim ground.
    """
    world = bpy.data.worlds.new('Blue hour')
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    for node in [n for n in nodes if n.type != 'OUTPUT_WORLD']:
        nodes.remove(node)
    coords = nodes.new('ShaderNodeTexCoord')
    split = nodes.new('ShaderNodeSeparateXYZ')
    links.new(coords.outputs['Generated'], split.inputs['Vector'])
    up = nodes.new('ShaderNodeMapRange')     # view direction's z, -1..1 -> 0..1
    up.inputs['From Min'].default_value = -1.
    up.inputs['From Max'].default_value = 1.
    links.new(split.outputs['Z'], up.inputs['Value'])
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.interpolation = 'EASE'
    stops = ramp.color_ramp.elements
    stops[0].position, stops[0].color = .47, (*SKY_GROUND, 1.)
    stops[1].position, stops[1].color = 1., (*SKY_ZENITH, 1.)
    horizon = stops.new(.505)
    horizon.color = (*SKY_HORIZON, 1.)
    links.new(up.outputs['Result'], ramp.inputs['Fac'])
    sky = nodes.new('ShaderNodeBackground')
    sky.inputs['Strength'].default_value = SKY_STRENGTH
    links.new(ramp.outputs['Color'], sky.inputs['Color'])

    view = nodes.new('ShaderNodeTexEnvironment')
    path = ASSETS / WINDOW_VIEW
    if not path.is_file():
        raise FileNotFoundError(f'Missing local asset: {path}')
    view.image = bpy.data.images.load(str(path), check_existing=True)
    turn = nodes.new('ShaderNodeMapping')
    turn.inputs['Rotation'].default_value = (0., 0., math.radians(WINDOW_VIEW_TURN_DEG))
    links.new(coords.outputs['Generated'], turn.inputs['Vector'])
    links.new(turn.outputs['Vector'], view.inputs['Vector'])
    photo = nodes.new('ShaderNodeBackground')
    photo.inputs['Strength'].default_value = WINDOW_VIEW_STRENGTH
    links.new(view.outputs['Color'], photo.inputs['Color'])
    path_info = nodes.new('ShaderNodeLightPath')
    mix = nodes.new('ShaderNodeMixShader')
    links.new(path_info.outputs['Is Camera Ray'], mix.inputs['Fac'])
    links.new(sky.outputs['Background'], mix.inputs[1])
    links.new(photo.outputs['Background'], mix.inputs[2])
    links.new(mix.outputs['Shader'], nodes['World Output'].inputs['Surface'])
    scene.world = world

    data = bpy.data.lights.new('Window sky portal', 'AREA')
    data.shape = 'RECTANGLE'
    data.size, data.size_y = portal['size']
    data.cycles.is_portal = True
    obj = bpy.data.objects.new('Window sky portal', data)
    scene.collection.objects.link(obj)
    obj.location = portal['centre']
    # An area lamp emits along its -Z: aim that into the room (-x).  Its local
    # X then runs along the wall (world y), the window's width.
    _aim(obj, (portal['centre'][0] - 1., portal['centre'][1], portal['centre'][2]))
    return world


# ------------------------------------------------------------------ assembly

def build(bpy, scene):
    """Build the whole bistro corner; returns a summary for the render log."""
    table = place_table(bpy)
    cloth = tablecloth(bpy, gingham(bpy))
    room = build_room(bpy)
    chairs = []
    for i, spec in enumerate(CHAIRS):
        spec = dict(spec)
        yaw = spec.pop('yaw_deg')
        _, _, (lo, hi) = place_model(bpy, 'dining_chair_02', f'Leather dining chair {i + 1}',
                                     yaw_deg=yaw, z=FLOOR_Z, **spec)
        chairs.append(dict(yaw_deg=yaw, bbox_min=[round(v, 4) for v in lo], bbox_max=[round(v, 4) for v in hi]))
    candle = light_candle(bpy)
    lamps = [hang_chandelier(bpy, xy, i + 1) for i, xy in enumerate(CHANDELIERS_XY)]
    twilight_world(bpy, scene, room['portal'])
    return dict(table=table, cloth=cloth.name, room=room, chairs=chairs, candle=candle, chandeliers=lamps)


def clearance_pieces(bpy):
    """Static pieces the tins must keep 2 cm from: everything tagged static
    except the table and cloth they stand on, as world-space boxes."""
    pieces = []
    for obj in bpy.data.objects:
        role = obj.get(STATIC_TAG)
        if obj.type != 'MESH' or role is None or role == 'support':
            continue
        points = [obj.matrix_world @ v.co for v in obj.data.vertices]
        lo = [min(p[i] for p in points) for i in range(3)]
        hi = [max(p[i] for p in points) for i in range(3)]
        pieces.append(dict(name=obj.name, lo=lo, hi=hi))
    return pieces
