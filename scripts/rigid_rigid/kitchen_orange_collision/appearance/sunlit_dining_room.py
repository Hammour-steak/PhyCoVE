"""A Mediterranean breakfast room built to measure around the simulator's table.

This module builds an ordinary room at real sizes:

* lime-plastered walls about 36 cm thick, washed off-white, a honed cream marble
  floor, and in the wall at the table's far end a pair of glazed French doors
  standing open onto a stone-paved terrace with a whitewashed parapet; a
  casement window beside them. Everything is a Poly Haven CC0 scan at its
  measured size.
* the table is the simulator's table box: a natural linen cloth whose flat top
  *is* the box's top face (TABLE_TOP_Z) and whose edge rolls over the box's
  edge, so the surface the oranges roll on and fall from is the collider.
* the room floor, the door threshold and the terrace paving are all at z = 0,
  which is where the simulator's floor plane is. The open doors are placed so
  that an orange thrown off the table rolls out through them: in
  ``edit_midframe_surge`` the struck orange is still in shot 8.5 m away, which
  is why there is a terrace rather than a wall there.
* light is a low morning sun and a physical sky, entering through the door and
  the window only; there is no lamp anywhere. Over the low parapet the camera
  sees hazy hills across a valley (Poly Haven pizzo_pernice), turned so its sun stands
  where the sun lamp is.

Nothing in here takes part in the simulation. ``check_clearance`` refuses any
frame in which a moving orange comes within 2 cm of a piece of the set that is
not a surface the simulator collides with, and ``check_occlusion`` refuses a
frame in which a piece of furniture hides an orange from the camera.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from scene_geometry import TABLE_TOP_Z, TABLE_CENTER, TABLE_HALF, RADIUS

ASSETS = _pcve_asset('polyhaven/kitchen_orange_collision')

# --- the simulator's table box: x/y footprint and top face -------------------
TABLE_X = (TABLE_CENTER[0] - TABLE_HALF[0], TABLE_CENTER[0] + TABLE_HALF[0])
TABLE_Y = (TABLE_CENTER[1] - TABLE_HALF[1], TABLE_CENTER[1] + TABLE_HALF[1])
# The collision box is 40 mm deep; below its bottom face the hanging cloth is
# set dressing and has to keep clear of the fruit like everything else.
TABLE_BOX_BOTTOM_Z = TABLE_TOP_Z - .04

# Linen cloth: thickness and the radius it rolls over the table's edge with.
CLOTH_THICK_M = .0015
CLOTH_ROLL_M = .008
# How far the cloth hangs down each edge. It lies a little askew, pulled
# towards the near end and the back, as a cloth does after breakfast has been
# laid: it hangs 20 cm down the near end (-x) and the back (+y) and only 36 mm
# over the far end (+x) and the front (-y). The six cases decide this:
# * every orange that leaves the table goes over the far end, where a long drop
#   would hang in its path; 36 mm is inside the collision box's own 40 mm, so
#   what an orange passes on its way over is the box side;
# * nothing goes over the front edge, but the falling oranges and the floor
#   they land on are seen past it, just under the table: any drop below the
#   box hides them (heavy_driver frame 66, fast_driver 44, midframe_surge 28);
# * nothing passes near the near end or the back, and no sight line to an
#   orange crosses them, so those two hang freely in soft folds.
CLOTH_DROP_M = dict(x0=.20, x1=.036, y0=.036, y1=.20)
# Where the cloth's flat UVs (metres) start on the weave scan.
CLOTH_UV_OFFSET = (3.1, 1.7)
# Trestle ends of the table: this far in from the table's centre along x.
TRESTLE_X = .65

# --- the room (plaster faces) ------------------------------------------------
ROOM_X = (-2.45, 3.30)
ROOM_Y = (-2.25, 2.55)
CEILING_M = 2.95
WALL_THICK_M = .36
# Openings in the x = ROOM_X[1] wall, as (span along y, z span).
DOOR = dict(span=(-1.27, .57), z=(0., 2.32))
SIDE_WINDOW = dict(span=(1.55, 2.27), z=(.86, 2.32))
DOOR_FRAME_M = .065          # jamb lining inside the opening
DOOR_LEAF_THICK_M = .045
DOOR_LEAF_OPEN_DEG = 172.    # folded back almost flat against the inner wall
# Terrace outside the door, at the room's floor level.
TERRACE_X = (ROOM_X[1] + WALL_THICK_M, 10.60)
TERRACE_Y = (-8., 8.)
PARAPET_THICK_M = .34
# A low garden wall: at 0.70 m its top sits 3.3 deg under the camera's eye
# line, which is where the hills across the valley begin in the photograph.
PARAPET_TOP_M = .70

# Real sizes of the Poly Haven scans (api.polyhaven.com/info "dimensions").
FLOOR_TILE_M = 1.50          # marble_01
WALL_TILE_M = 1.00           # grey_plaster_03
LINEN_TILE_M = .266          # terlenka
LEG_WOOD_TILE_M = .55        # wood_table_worn
PAVING_TILE_M = 2.00         # stone_pavers

# The painted chairs: the scan's seat stands 0.58 m off the floor and its back
# 1.26 m, which is a bar-height chair, not a dining chair -- at that size the
# seat would sit 16 cm under the cloth. Its proportions are an ordinary
# ladder-back's, so it is scaled uniformly to a 0.46 m seat (1.00 m overall).
CHAIR_SEAT_SCAN_M = .58
CHAIR_SEAT_M = .46
CHAIR_SCALE = CHAIR_SEAT_M / CHAIR_SEAT_SCAN_M

# Morning sun. SUN_AZIMUTH_DEG is the direction *towards* the sun, degrees from
# +x towards +y: it stands a little to the right of the open doors, so its
# light comes in through them and lays a patch over the far half of the table
# while the near end stays in skylight.
SUN_ELEVATION_DEG = 25.
SUN_AZIMUTH_DEG = -8.
SUN_STRENGTH = 4.2
SKY_STRENGTH = .6
# Poly Haven pizzo_pernice: its sun stands at pixel u = 0.6006, i.e. azimuth
# (0.5 - u) * 360 = -36.2 deg in the photograph's own frame. Turning the lookup
# by the difference puts the photograph's sun where the lamp is. Over the
# parapet the camera sees only a few degrees about the horizon: hill ridges
# kilometres off in morning haze, nothing near enough to look magnified.
WINDOW_VIEW = 'pizzo_pernice_4k.hdr'
WINDOW_VIEW_SUN_AZIMUTH_DEG = -36.2
WINDOW_VIEW_TURN_DEG = WINDOW_VIEW_SUN_AZIMUTH_DEG - SUN_AZIMUTH_DEG
WINDOW_VIEW_STRENGTH = 1.

TEXTURE_SETS = ('marble_01', 'grey_plaster_03', 'terlenka', 'wood_table_worn', 'stone_pavers')
MODELS = ('painted_wooden_chair_02', 'painted_wooden_cabinet_02', 'food_pomegranate_01',
          'brass_vase_02', 'ceramic_pot', 'fancy_picture_frame_01', 'hamburger_buns')

# Roles recorded on every object this module builds; the checks read them.
SUPPORT, CLOTH, SHELL, FURNITURE, GLASS = 'support', 'cloth', 'shell', 'furniture', 'glass'


def used_files():
    """Every file of the scene's asset folder that the room loads."""
    files = [f'{s}_{k}_2k.jpg' for s in TEXTURE_SETS for k in ('diff', 'rough', 'nor_gl')]
    files.append(WINDOW_VIEW)
    for m in MODELS:
        files += [p.relative_to(ASSETS).as_posix() for p in sorted((ASSETS / m).rglob('*')) if p.is_file()]
    return files


# ------------------------------------------------------------------ geometry


def _tag(obj, role):
    obj['pcve_role'] = role
    return obj


def box(name, lo, hi, mat=None, role=SHELL, bevel=0., segments=2):
    """An axis-aligned box built in world coordinates (object at the origin),
    so Object texture coordinates are world metres on every part of the room."""
    import bpy
    import bmesh
    from mathutils import Vector
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.)
    centre = [(a + b) / 2 for a, b in zip(lo, hi)]
    size = [b - a for a, b in zip(lo, hi)]
    for v in bm.verts:
        v.co = Vector(tuple(centre[i] + v.co[i] * size[i] for i in range(3)))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if mat is not None:
        mesh.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new('Eased edges', 'BEVEL')
        mod.width, mod.segments, mod.limit_method = bevel, segments, 'ANGLE'
        obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return _tag(obj, role)


# ----------------------------------------------------------------- materials


def principled(name, color, roughness, metallic=0.):
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, 1)
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    return mat


def _scan_nodes(mat, stem, vector, tint=None, rough_range=None, normal_strength=1., projection='FLAT',
                hsv=None, wash=None):
    """Wire one Poly Haven 2k set (diff / rough / nor_gl) into the BSDF.

    ``hsv`` = (saturation, value) rescales the scan's colour. ``wash`` =
    (colour, keep) lays a coat of that colour over it and keeps ``keep`` of the
    scan's own variation: grey plaster limewashed white keeps its undulations
    and faint stains, not its grey."""
    import bpy
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']

    def image(kind, colour):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(ASSETS / f'{stem}_{kind}_2k.jpg'), check_existing=True)
        if not colour:
            node.image.colorspace_settings.name = 'Non-Color'
        node.projection = projection
        node.projection_blend = .15
        node.interpolation = 'Cubic'
        links.new(vector, node.inputs['Vector'])
        return node

    colour = image('diff', True).outputs['Color']
    if hsv is not None:
        adjust = nodes.new('ShaderNodeHueSaturation')
        adjust.inputs['Saturation'].default_value, adjust.inputs['Value'].default_value = hsv
        links.new(colour, adjust.inputs['Color'])
        colour = adjust.outputs['Color']
    if wash is not None:
        coat = nodes.new('ShaderNodeMixRGB')
        coat.inputs['Fac'].default_value = wash[1]
        coat.inputs['Color1'].default_value = (*wash[0], 1.)
        links.new(colour, coat.inputs['Color2'])
        colour = coat.outputs['Color']
    if tint is not None:
        # A vector multiply, not a colour mix: colour sockets clamp at 1 and a
        # tint that lifts a scan would be cut off.
        mix = nodes.new('ShaderNodeVectorMath')
        mix.operation = 'MULTIPLY'
        links.new(colour, mix.inputs[0])
        mix.inputs[1].default_value = tint
        colour = mix.outputs['Vector']
    links.new(colour, bsdf.inputs['Base Color'])
    rough = image('rough', False).outputs['Color']
    if rough_range is not None:
        remap = nodes.new('ShaderNodeMapRange')
        remap.inputs['To Min'].default_value, remap.inputs['To Max'].default_value = rough_range
        links.new(rough, remap.inputs['Value'])
        rough = remap.outputs['Result']
    links.new(rough, bsdf.inputs['Roughness'])
    normal = nodes.new('ShaderNodeNormalMap')
    normal.inputs['Strength'].default_value = normal_strength
    links.new(image('nor_gl', False).outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])


def scanned(name, stem, tile_m, base=(.5, .5, .5), coord='Object', **options):
    """A scan box-projected in world metres (every room part is built at the
    origin), so tiles and plaster keep their real size everywhere."""
    mat = principled(name, base, .5)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    source = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1 / tile_m,) * 3
    links.new(source.outputs[coord], mapping.inputs['Vector'])
    _scan_nodes(mat, stem, mapping.outputs['Vector'], projection='BOX' if coord == 'Object' else 'FLAT',
                **options)
    return mat


def painted(name, color, roughness=.40):
    """Satin paint on joinery: one colour drifting a little in tone and sheen,
    with the faint brush texture of hand-painted timber."""
    mat = principled(name, color, roughness)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    position = nodes.new('ShaderNodeNewGeometry')
    drift = nodes.new('ShaderNodeTexNoise')
    drift.inputs['Scale'].default_value = 1.6
    drift.inputs['Detail'].default_value = 3.
    links.new(position.outputs['Position'], drift.inputs['Vector'])
    tone = nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].color = (*(c * .93 for c in color), 1)
    tone.color_ramp.elements[1].color = (*(min(1., c * 1.05) for c in color), 1)
    links.new(drift.outputs['Fac'], tone.inputs['Fac'])
    links.new(tone.outputs['Color'], bsdf.inputs['Base Color'])
    sheen = nodes.new('ShaderNodeMapRange')
    sheen.inputs['To Min'].default_value = roughness - .07
    sheen.inputs['To Max'].default_value = roughness + .07
    links.new(drift.outputs['Fac'], sheen.inputs['Value'])
    links.new(sheen.outputs['Result'], bsdf.inputs['Roughness'])
    brush = nodes.new('ShaderNodeTexWave')
    brush.wave_type, brush.bands_direction = 'BANDS', 'Z'
    brush.inputs['Scale'].default_value = 140.
    brush.inputs['Distortion'].default_value = 9.
    brush.inputs['Detail'].default_value = 2.
    links.new(position.outputs['Position'], brush.inputs['Vector'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .035
    bump.inputs['Distance'].default_value = .0002
    links.new(brush.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def thin_glass():
    """Float glass shaded thin: Fresnel reflection over a transparent layer.

    Rays through it stay camera rays (the world shows the valley photograph to
    the camera only). Cycles' Fresnel node inverts the IOR on back faces, which
    would turn a pane seen obliquely from inside black by total internal
    reflection; feeding 1/1.52 on back faces cancels that.
    """
    import bpy
    existing = bpy.data.materials.get('Clear float glass')
    if existing is not None:
        return existing
    mat = bpy.data.materials.new('Clear float glass')
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


def linen():
    """The tablecloth: the terlenka weave scan on the cloth's own flat UVs, so
    the weave runs on unbroken over the edge and down the drop, with a thin
    sheen lobe because woven linen catches low light at grazing angles."""
    mat = principled('Natural linen tablecloth', (.55, .50, .42), .85)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    source = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1 / LINEN_TILE_M,) * 3
    links.new(source.outputs['UV'], mapping.inputs['Vector'])
    _scan_nodes(mat, 'terlenka', mapping.outputs['Vector'], hsv=(.32, 1.25), tint=(1.02, 1.01, .98),
                rough_range=(.72, .95), normal_strength=.7)
    bsdf = nodes['Principled BSDF']
    bsdf.inputs['Sheen Weight'].default_value = .35
    bsdf.inputs['Sheen Roughness'].default_value = .45
    # Ironing creases: a linen cloth is stored folded in half lengthwise and in
    # quarters across, and the folds stay in it as soft ridges. They are shading
    # only (a bump), so the cloth top stays exactly the collider's top face.
    uv = nodes.new('ShaderNodeSeparateXYZ')
    links.new(source.outputs['UV'], uv.inputs['Vector'])

    def m(op, a, b=None):
        node = nodes.new('ShaderNodeMath')
        node.operation = op
        for socket, value in zip(node.inputs, (a, b)):
            if value is None:
                continue
            if isinstance(value, (int, float)):
                socket.default_value = value
            else:
                links.new(value, socket)
        return node.outputs['Value']

    def fold_lines(coord, origin, period):
        # Distance to the nearest fold line, then a soft 22 mm ridge profile.
        phase = m('FRACT', m('ADD', m('DIVIDE', m('SUBTRACT', coord, origin), period), .5))
        dist = m('MULTIPLY', m('ABSOLUTE', m('SUBTRACT', phase, .5)), period)
        ridge = nodes.new('ShaderNodeMapRange')
        ridge.interpolation_type = 'SMOOTHSTEP'
        ridge.inputs['From Min'].default_value, ridge.inputs['From Max'].default_value = 0., .022
        ridge.inputs['To Min'].default_value, ridge.inputs['To Max'].default_value = 1., 0.
        links.new(dist, ridge.inputs['Value'])
        return ridge.outputs['Result']

    across = fold_lines(uv.outputs['X'], TABLE_CENTER[0] + CLOTH_UV_OFFSET[0], TABLE_HALF[0])
    along = fold_lines(uv.outputs['Y'], TABLE_CENTER[1] + CLOTH_UV_OFFSET[1], 2 * TABLE_HALF[1] + .3)
    crease = m('MAXIMUM', across, along)
    # A cloth laid on a table is never dead flat: a faint slow undulation and
    # small soft wrinkles left from use.
    lie = nodes.new('ShaderNodeTexNoise')
    lie.inputs['Scale'].default_value = 2.2
    lie.inputs['Detail'].default_value = 2.
    links.new(source.outputs['UV'], lie.inputs['Vector'])
    wrinkle = nodes.new('ShaderNodeTexNoise')
    wrinkle.inputs['Scale'].default_value = 9.
    wrinkle.inputs['Detail'].default_value = 4.
    wrinkle.inputs['Distortion'].default_value = .6
    links.new(source.outputs['UV'], wrinkle.inputs['Vector'])
    height = m('ADD', m('ADD', m('MULTIPLY', crease, .6), m('MULTIPLY', lie.outputs['Fac'], .5)),
               m('MULTIPLY', wrinkle.outputs['Fac'], .3))
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .32
    bump.inputs['Distance'].default_value = .002
    links.new(height, bump.inputs['Height'])
    # Slubs: linen yarn is uneven, so from a few metres a linen cloth shows faint
    # streaks along its warp and weft and a mottled sheen, not a flat white.
    def streaks(stretch):
        scale = nodes.new('ShaderNodeVectorMath')
        scale.operation = 'MULTIPLY'
        scale.inputs[1].default_value = stretch
        links.new(source.outputs['UV'], scale.inputs[0])
        tex = nodes.new('ShaderNodeTexNoise')
        tex.inputs['Scale'].default_value = 1.
        tex.inputs['Detail'].default_value = 3.
        links.new(scale.outputs['Vector'], tex.inputs['Vector'])
        return tex.outputs['Fac']
    slub = m('MULTIPLY', m('ADD', streaks((4., 160., 1.)), streaks((160., 4., 1.))), .5)
    tone = nodes.new('ShaderNodeMapRange')
    tone.inputs['From Min'].default_value, tone.inputs['From Max'].default_value = .3, .7
    tone.inputs['To Min'].default_value, tone.inputs['To Max'].default_value = .93, 1.04
    links.new(slub, tone.inputs['Value'])
    shade = m('MULTIPLY', tone.outputs['Result'], m('SUBTRACT', 1., m('MULTIPLY', crease, .05)))
    weave_colour = bsdf.inputs['Base Color'].links[0].from_socket
    tinted = nodes.new('ShaderNodeVectorMath')
    tinted.operation = 'SCALE'
    links.new(weave_colour, tinted.inputs[0])
    links.new(shade, tinted.inputs['Scale'])
    links.new(tinted.outputs['Vector'], bsdf.inputs['Base Color'])
    weave_rough = bsdf.inputs['Roughness'].links[0].from_socket
    links.new(m('ADD', weave_rough, m('MULTIPLY', m('SUBTRACT', slub, .5), -.25)), bsdf.inputs['Roughness'])
    links.new(bsdf.inputs['Normal'].links[0].from_socket, bump.inputs['Normal'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


# ----------------------------------------------------------------- the table


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


def _overhang(drop):
    """Cloth length past the flat top for a given drop below the table top."""
    return drop - CLOTH_ROLL_M + math.pi * CLOTH_ROLL_M / 2


def _side_samples(flat_half, overhang):
    """1-D cloth parameters from the centre outwards on one side: 2 cm on the
    flat top (fine enough for the folds that run along it), 1 mm through the
    roll, 1 cm down the drop, 2 mm in the hem."""
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


def _hang_offset(hang):
    """How far a hanging cloth stands out from the table side ``hang`` metres
    below the collision box: a stiff linen flares a little towards the hem."""
    return .010 * min(1., hang / .16) ** 2


def tablecloth(mat):
    """The cloth as one sheet: flat over the simulator's table box, rolled over
    its edges and hanging CLOTH_DROP_M down each, in soft folds where it hangs
    long, its surplus falling into a cone at the long corner, its hem rolled.

    The outer face of the flat top is exactly TABLE_TOP_Z out to within
    CLOTH_ROLL_M of the box's edge (the cloth's thickness is laid downwards
    with Solidify), and down to the box's bottom face the hanging cloth stays
    within a few millimetres of the box's sides, so the surface an orange rolls
    on and the edge it drops from are the collider's.
    """
    import bpy
    cx, cy = TABLE_CENTER
    fx = TABLE_HALF[0] + CLOTH_THICK_M - CLOTH_ROLL_M
    fy = TABLE_HALF[1] + CLOTH_THICK_M - CLOTH_ROLL_M
    over = {k: _overhang(d) for k, d in CLOTH_DROP_M.items()}
    xs = [-v for v in reversed(_side_samples(fx, over['x0'])[1:])] + _side_samples(fx, over['x1'])
    ys = [-v for v in reversed(_side_samples(fy, over['y0'])[1:])] + _side_samples(fy, over['y1'])

    def folds(along, hang, phase):
        # Soft vertical folds, growing towards the hem; wavelengths 17-27 cm.
        a = .013 * min(1., hang / .16) ** 1.4
        return a * (.6 * math.sin(along * 23. + phase) + .4 * math.sin(along * 37. + 2.1 * phase))

    def hem_curl(ex, ey, ox_lim, oy_lim):
        # The last 12 mm turn in under themselves: a rolled hem, not a cut edge.
        t = max((ex - (ox_lim - .012)) / .012, (ey - (oy_lim - .012)) / .012, 0.)
        return -.004 * min(1., t) ** 2

    verts, uvs = [], []
    for v in ys:
        for u in xs:
            sx, sy = math.copysign(1., u), math.copysign(1., v)
            ox_lim = over['x1'] if u > 0 else over['x0']
            oy_lim = over['y1'] if v > 0 else over['y0']
            ex, ey = abs(u) - fx, abs(v) - fy
            curl = hem_curl(ex, ey, ox_lim, oy_lim)
            if ex > 0. and ey > 0.:
                e = math.hypot(ex, ey)
                theta = math.atan2(ey, ex)
                out, drop = _roll(e)
                hang = max(0., drop - .04)
                # Below the box the corner's surplus cloth stands out along the
                # diagonal in a cone, and its tip hangs lowest, as a real
                # tablecloth's does.
                out += _hang_offset(hang) + .16 * hang * math.sin(2 * theta) ** 2 + curl
                x = cx + sx * (fx + out * math.cos(theta))
                y = cy + sy * (fy + out * math.sin(theta))
                z = TABLE_TOP_Z - drop
            elif ex > 0. or ey > 0.:
                on_x = ex > 0.
                out, drop = _roll(ex if on_x else ey)
                hang = max(0., drop - .04)
                along = v if on_x else u
                limit = fy if on_x else fx
                # Folds fade out towards the corners so the side meets the
                # corner cone without a seam.
                fade = min(1., max(0., (limit - abs(along)) / .10))
                phase = (1.3 if on_x else .4) + (0. if (u if on_x else v) > 0 else 2.7)
                out += _hang_offset(hang) + folds(along, hang, phase) * fade + curl
                x = cx + (sx * (fx + out) if on_x else u)
                y = cy + (v if on_x else sy * (fy + out))
                z = TABLE_TOP_Z - drop
            else:
                x, y, z = cx + u, cy + v, TABLE_TOP_Z
            verts.append((x, y, z))
            uvs.append((u + CLOTH_UV_OFFSET[0], v + CLOTH_UV_OFFSET[1]))
    nx = len(xs)
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i)
             for j in range(len(ys) - 1) for i in range(nx - 1)]
    mesh = bpy.data.meshes.new('Linen tablecloth')
    mesh.from_pydata(verts, [], faces)
    layer = mesh.uv_layers.new(name='UVMap')
    for poly in mesh.polygons:
        poly.use_smooth = True
        for li in poly.loop_indices:
            layer.data[li].uv = uvs[mesh.loops[li].vertex_index]
    mesh.update()
    obj = bpy.data.objects.new('Linen tablecloth', mesh)
    bpy.context.collection.objects.link(obj)
    mesh.materials.append(mat)
    solid = obj.modifiers.new('Cloth thickness', 'SOLIDIFY')
    solid.thickness = CLOTH_THICK_M
    solid.offset = -1.
    solid.use_even_offset = True
    _tag(obj, CLOTH)
    top = [v[2] for v in verts if abs(v[0] - cx) <= TABLE_HALF[0] - CLOTH_ROLL_M and abs(v[1] - cy) <= TABLE_HALF[1] - CLOTH_ROLL_M]
    if max(abs(z - TABLE_TOP_Z) for z in top) > 1e-9:
        raise RuntimeError('The cloth top is not the simulator table top')
    # Down to the box's bottom face the cloth is the box's side: it may stand
    # off it by its own thickness, the roll and a few millimetres of hem, no more.
    band = [max(abs(x - cx) - TABLE_HALF[0], abs(y - cy) - TABLE_HALF[1]) for x, y, z in verts
            if z >= TABLE_BOX_BOTTOM_Z and (abs(x - cx) > TABLE_HALF[0] or abs(y - cy) > TABLE_HALF[1])]
    if band and max(band) > .006:
        raise RuntimeError(f'The cloth stands {max(band) * 1000:.1f} mm off the table box side')
    return obj


def table(cloth_mat, wood):
    """Linen over a trestle table: the board, two trestle ends and a stretcher.

    The board stands under the cloth's thickness, so the cloth's outer face is
    the collider's top. A trestle rather than four corner legs because the
    thrown oranges land and roll on the floor just past the table's far end,
    and seen from the camera a corner leg stands right in front of that floor:
    with the trestle ends TRESTLE_X either side of the centre and on the centre
    line, nothing under the table hides an orange in any of the six cases.
    """
    x0, x1 = TABLE_X
    y0, y1 = TABLE_Y
    cx = TABLE_CENTER[0]
    board_top = TABLE_TOP_Z - CLOTH_THICK_M
    board_bottom = TABLE_BOX_BOTTOM_Z + .003
    # The board is the collision box itself: a support surface, not dressing.
    box('Table board', (x0 + .002, y0 + .002, board_bottom), (x1 - .002, y1 - .002, board_top), wood,
        SUPPORT, .003)
    for side, sx in (('near', -1.), ('far', 1.)):
        x = cx + sx * TRESTLE_X
        box(f'Trestle cleat {side}', (x - .035, -.46, board_bottom - .075), (x + .035, .46, board_bottom),
            wood, FURNITURE, .006)
        box(f'Trestle post {side}', (x - .045, -.045, .07), (x + .045, .045, board_bottom - .075),
            wood, FURNITURE, .006)
        box(f'Trestle foot {side}', (x - .035, -.38, .012), (x + .035, .38, .07), wood, FURNITURE, .008)
        for end, sy in (('front', -1.), ('back', 1.)):
            # The foot stands on two pads at its ends, as a trestle foot does.
            y = sy * .34
            box(f'Trestle foot pad {side} {end}', (x - .035, y - .04, 0.), (x + .035, y + .04, .012),
                wood, FURNITURE, .003)
    box('Trestle stretcher', (cx - TRESTLE_X, -.025, .24), (cx + TRESTLE_X, .025, .33), wood, FURNITURE, .005)
    return tablecloth(cloth_mat)


# -------------------------------------------------------------------- shell


def wall_x(name, x0, x1, y_span, z_span, holes, mat):
    """A wall at constant x built as panels around rectangular openings."""
    (y0, y1), (z0, z1) = y_span, z_span
    cursor = y0
    for (hy0, hy1), (hz0, hz1) in sorted(holes):
        box(f'{name} / pier', (x0, cursor, z0), (x1, hy0, z1), mat)
        if hz0 > z0:
            box(f'{name} / below opening', (x0, hy0, z0), (x1, hy1, hz0), mat)
        box(f'{name} / above opening', (x0, hy0, hz1), (x1, hy1, z1), mat)
        cursor = hy1
    box(f'{name} / pier', (x0, cursor, z0), (x1, y1, z1), mat)


def french_door(paint, glass, stone):
    """Jamb linings in the door opening, a stone threshold flush with the
    floor, and two glazed leaves folded back against the inner wall face.

    The hinges stand just inside the room, so a leaf swung back to
    DOOR_LEAF_OPEN_DEG clears the jamb lining and the wall face."""
    import bpy
    from mathutils import Matrix
    (s0, s1), (z0, z1) = DOOR['span'], DOOR['z']
    x_in, x_out = ROOM_X[1], ROOM_X[1] + WALL_THICK_M
    f = DOOR_FRAME_M
    # Lining on both jambs and the head; the threshold is a stone at floor level.
    box('Door lining near jamb', (x_in, s0, z0), (x_in + .12, s0 + f, z1), paint, FURNITURE, .002)
    box('Door lining far jamb', (x_in, s1 - f, z0), (x_in + .12, s1, z1), paint, FURNITURE, .002)
    box('Door lining head', (x_in, s0, z1 - f), (x_in + .12, s1, z1), paint, FURNITURE, .002)
    clear = (s0 + f, s1 - f)
    leaf_w = (clear[1] - clear[0]) / 2
    leaf_h = z1 - f - .008
    leaves = []
    for side, hinge_y, sign in (('near', clear[0], -1.), ('far', clear[1], 1.)):
        parts = []
        st, rail, bottom = .072, .075, .21
        # Built closed in the opening, in the leaf's own frame: y across, z up.
        def part(label, a0, a1, c0, c1, mat=paint, t=DOOR_LEAF_THICK_M, bevel=.002):
            o = box(f'Door leaf {side} {label}', (0., a0, c0), (t, a1, c1), mat, FURNITURE if mat is paint else GLASS, bevel)
            parts.append(o)
            return o
        w = leaf_w - .004
        part('hinge stile', 0., st, 0., leaf_h)
        part('lock stile', w - st, w, 0., leaf_h)
        part('top rail', st, w - st, leaf_h - rail, leaf_h)
        part('bottom rail', st, w - st, 0., bottom)
        part('lock rail', st, w - st, bottom + .38, bottom + .38 + .05)
        part('panel', st, w - st, bottom, bottom + .38, t=DOOR_LEAF_THICK_M * .55)
        g0, g1 = bottom + .43, leaf_h - rail
        for k in range(1, 4):
            zk = g0 + (g1 - g0) * k / 4
            part(f'glazing bar {k}', st, w - st, zk - .012, zk + .012, t=DOOR_LEAF_THICK_M * .8)
        part('glazing bar upright', w / 2 - .012, w / 2 + .012, g0, g1, t=DOOR_LEAF_THICK_M * .8)
        pane = part('glass', st, w - st, g0, g1, glass, t=.006, bevel=0.)
        pane.location.x = DOOR_LEAF_THICK_M / 2 - .003
        pane.visible_shadow = False
        # Leaf frame: mirror the far leaf so both hinge stiles sit on the jambs,
        # then swing each about its hinge (inner face, at the jamb) into the room.
        leaf = bpy.data.objects.new(f'Door leaf {side}', None)
        bpy.context.collection.objects.link(leaf)
        for o in parts:
            o.parent = leaf
        mirror = Matrix.Scale(sign * -1., 4, (0, 1, 0)) if sign > 0 else Matrix.Identity(4)
        angle = math.radians(DOOR_LEAF_OPEN_DEG) * (-sign)
        leaf.matrix_world = (Matrix.Translation((x_in - .006, hinge_y, z0 + .004))
                             @ Matrix.Rotation(angle, 4, 'Z') @ mirror)
        leaves.append(leaf)
    box('Door threshold stone', (x_in, s0, -.06), (x_out, s1, 0.), stone, SUPPORT)
    return leaves


def casement(paint, glass, sill):
    """Two-leaf timber casement set in the middle of the side window's reveal."""
    (s0, s1), (z0, z1) = SIDE_WINDOW['span'], SIDE_WINDOW['z']
    face = ROOM_X[1]
    depth = (face + .13, face + .19)

    def part(label, a0, a1, c0, c1, d=depth, mat=paint, bevel=.0015, role=FURNITURE):
        return box(f'Side window {label}', (d[0], a0, c0), (d[1], a1, c1), mat, role, bevel)

    bar = .06
    part('head', s0, s1, z1 - bar, z1)
    part('sill rail', s0, s1, z0, z0 + bar)
    part('near jamb', s0, s0 + bar, z0 + bar, z1 - bar)
    part('far jamb', s1 - bar, s1, z0 + bar, z1 - bar)
    mid = (s0 + s1) / 2
    inner = (depth[0] + .006, depth[1] - .006)
    part('meeting stiles', mid - .03, mid + .03, z0 + bar, z1 - bar, inner)
    for k in range(1, 3):
        zk = z0 + bar + (z1 - z0 - 2 * bar) * k / 3
        part(f'glazing bar near {k}', s0 + bar, mid - .03, zk - .011, zk + .011, inner)
        part(f'glazing bar far {k}', mid + .03, s1 - bar, zk - .011, zk + .011, inner)
    pane = part('glass', s0 + .01, s1 - .01, z0 + .01, z1 - .01,
                ((depth[0] + depth[1]) / 2 - .003, (depth[0] + depth[1]) / 2 + .003), glass, 0., GLASS)
    pane.visible_shadow = False
    # A plastered sill board inside, as in a lime-washed reveal.
    part('board', s0 - .03, s1 + .03, z0 - .03, z0, (face - .03, depth[0]), sill, .004, SHELL)


def portal(name, centre, size, inward):
    import bpy
    from mathutils import Vector
    data = bpy.data.lights.new(name, 'AREA')
    data.shape = 'RECTANGLE'
    data.size, data.size_y = size
    data.cycles.is_portal = True
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = centre
    obj.rotation_euler = Vector(inward).to_track_quat('-Z', 'Y').to_euler()
    return obj


def shell(walls, ceiling, floor, paving, coping):
    """Floor, ceiling, four thick walls, the door and window openings, the
    terrace outside and its parapet."""
    (x0, x1), (y0, y1), t = ROOM_X, ROOM_Y, WALL_THICK_M
    box('Tiled floor', (x0 - t, y0 - t, -.06), (x1, y1 + t, 0.), floor, SUPPORT)
    box('Ceiling', (x0 - t, y0 - t, CEILING_M), (x1 + t, y1 + t, CEILING_M + .15), ceiling)
    z = (-.06, CEILING_M)
    # The door opening runs down to the wall's foot: the threshold stone fills it.
    wall_x('Terrace wall', x1, x1 + t, (y0 - t, y1 + t), z,
           [(DOOR['span'], (z[0], DOOR['z'][1])), (SIDE_WINDOW['span'], SIDE_WINDOW['z'])], walls)
    box('Wall behind the table', (x0, y1, z[0]), (x1, y1 + t, z[1]), walls)
    box('Wall at the near end', (x0 - t, y0 - t, z[0]), (x0, y1 + t, z[1]), walls)
    box('Wall behind the camera', (x0, y0 - t, z[0]), (x1, y0, z[1]), walls)
    # The terrace: paving at the room's floor level out to a whitewashed parapet.
    (tx0, tx1), (ty0, ty1) = TERRACE_X, TERRACE_Y
    box('Terrace paving', (tx0, ty0, -.12), (tx1 + PARAPET_THICK_M + .2, ty1, 0.), paving, SUPPORT)
    box('Terrace parapet', (tx1, ty0, 0.), (tx1 + PARAPET_THICK_M, ty1, PARAPET_TOP_M - .05), walls)
    box('Parapet coping', (tx1 - .03, ty0, PARAPET_TOP_M - .05), (tx1 + PARAPET_THICK_M + .03, ty1, PARAPET_TOP_M),
        coping, SHELL, .01)
    # The house front beyond the room, so the terrace is not lit through a gap.
    box('House front, near side', (x1, ty0, z[0]), (x1 + t, y0 - t, z[1]), walls)
    box('House front, far side', (x1, y1 + t, z[0]), (x1 + t, ty1, z[1]), walls)
    # Below the parapet the hillside falls away: a ground far down stops sky
    # light from below without the camera ever seeing it.
    ground = box('Hillside below the terrace', (-80., -80., -9.), (80., 80., -8.5),
                 principled('Hillside', (.16, .14, .10), .95))
    ground.visible_camera = False


# ---------------------------------------------------------------- furniture


def place_model(name, model, *, yaw_deg=0., scale=1., role=FURNITURE, **anchor):
    """Import a Poly Haven glTF, turn it about z, scale it uniformly and put its
    bounding box on an anchor: x / y (box centre), x_min / x_max / y_min /
    y_max (box faces) and z (bottom of the box)."""
    import bpy
    from mathutils import Vector
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(ASSETS / model / f'{model}_1k.gltf'))
    bpy.context.view_layer.update()
    imported = [o for o in bpy.data.objects if o not in before]
    for o in imported:
        o.animation_data_clear()
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for o in imported:
        if o.parent is None:
            world = o.matrix_world.copy()
            o.parent = root
            o.matrix_world = world
    root.rotation_euler.z = math.radians(yaw_deg)
    root.scale = (scale,) * 3
    bpy.context.view_layer.update()
    meshes = [o for o in imported if o.type == 'MESH']
    for o in meshes:
        _tag(o, role)
    points = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    shift = Vector((0., 0., 0.))
    for axis, index in (('x', 0), ('y', 1)):
        if axis in anchor:
            shift[index] = anchor[axis] - (lo[index] + hi[index]) / 2
        elif f'{axis}_min' in anchor:
            shift[index] = anchor[f'{axis}_min'] - lo[index]
        elif f'{axis}_max' in anchor:
            shift[index] = anchor[f'{axis}_max'] - hi[index]
    if 'z' in anchor:
        shift.z = anchor['z'] - lo.z
    root.location = shift
    bpy.context.view_layer.update()
    return dict(name=name, model=model, yaw_deg=yaw_deg, scale=round(scale, 4),
                bbox_min=[round(v, 4) for v in lo + shift], bbox_max=[round(v, 4) for v in hi + shift])


def scatter_model(name, model, spots, z, role=FURNITURE):
    """Import a scan of several loose pieces and lay each piece down at its own
    (x, y, yaw) spot, bottom on ``z``, rather than in the row it was shot in."""
    import bpy
    from mathutils import Matrix, Vector
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(ASSETS / model / f'{model}_1k.gltf'))
    bpy.context.view_layer.update()
    pieces = sorted((o for o in bpy.data.objects if o not in before and o.type == 'MESH'), key=lambda o: o.name)
    if len(pieces) != len(spots):
        raise RuntimeError(f'{model} has {len(pieces)} pieces, {len(spots)} spots given')
    placed = []
    for i, (o, (x, y, yaw)) in enumerate(zip(pieces, spots)):
        o.animation_data_clear()
        world = o.matrix_world.copy()
        o.parent = None
        pts = [world @ v.co for v in o.data.vertices]
        lo = Vector([min(p[k] for p in pts) for k in range(3)])
        hi = Vector([max(p[k] for p in pts) for k in range(3)])
        centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
        o.matrix_world = (Matrix.Translation((x, y, z)) @ Matrix.Rotation(math.radians(yaw), 4, 'Z')
                          @ Matrix.Translation(-centre) @ world)
        o.name = f'{name} {i + 1}'
        _tag(o, role)
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ v.co for v in o.data.vertices]
        placed.append(dict(name=o.name, model=model, yaw_deg=yaw, scale=1.,
                           bbox_min=[round(min(p[k] for p in pts), 4) for k in range(3)],
                           bbox_max=[round(max(p[k] for p in pts), 4) for k in range(3)]))
    return placed


def furnish():
    """Painted chairs at the table, the dresser and an old landscape in a gilt
    frame on the back wall, a glazed storage pot by the window, and breakfast on
    the table's near end: bread rolls, pomegranates and a brass water ewer.

    Nothing stands beyond the table's far end or between it and the door:
    that floor is where the thrown oranges land and roll.
    """
    placed = []
    y_back = TABLE_Y[1] + .02        # chairs pulled out just clear of the cloth
    placed.append(place_model('Chair, far side left', 'painted_wooden_chair_02', yaw_deg=0.,
                              scale=CHAIR_SCALE, x=-.40, y_min=y_back + .03, z=0.))
    placed.append(place_model('Chair, far side right', 'painted_wooden_chair_02', yaw_deg=-7.,
                              scale=CHAIR_SCALE, x=.30, y_min=y_back + .07, z=0.))
    placed.append(place_model('Dresser', 'painted_wooden_cabinet_02', yaw_deg=0.,
                              x=-.35, y_max=ROOM_Y[1] - .012, z=0.))
    placed.append(place_model('Brass ewer', 'brass_vase_02', yaw_deg=-65., x=-.44, y=.41, z=TABLE_TOP_Z))
    placed += scatter_model('Bread roll', 'hamburger_buns',
                            [(-.80, -.36, 20.), (-.675, -.43, 75.), (-.775, -.235, 140.)], TABLE_TOP_Z)
    # The canvas faces -y in the scan, i.e. into the room from the back wall.
    placed.append(place_model('Landscape painting', 'fancy_picture_frame_01', yaw_deg=0.,
                              x=.95, y_max=ROOM_Y[1] - .004, z=1.12))
    placed.append(place_model('Glazed storage pot', 'ceramic_pot', yaw_deg=-20.,
                              x=2.62, y_max=ROOM_Y[1] - .06, z=0.))
    for i, (x, y, yaw) in enumerate(((-.80, .30, 10.), (-.70, .40, 75.), (-.83, .43, 140.))):
        placed.append(place_model(f'Pomegranate {i + 1}', 'food_pomegranate_01', yaw_deg=yaw,
                                  x=x, y=y, z=TABLE_TOP_Z))
    return placed


# ------------------------------------------------------------------ daylight


def daylight(scene):
    """A sun lamp and a Nishita sky outside, nothing inside.

    Light rays see the physical sky (its own sun disc off: the lamp is the only
    sun). Camera rays that leave through the openings see the valley
    photograph instead, turned so its sun stands where the lamp is.
    """
    import bpy
    from mathutils import Vector
    el, az = math.radians(SUN_ELEVATION_DEG), math.radians(SUN_AZIMUTH_DEG)
    towards_sun = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    data = bpy.data.lights.new('Morning sun', 'SUN')
    data.energy, data.angle, data.color = SUN_STRENGTH, math.radians(.53), (1., .965, .92)
    sun = bpy.data.objects.new('Morning sun', data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (-towards_sun).to_track_quat('-Z', 'Y').to_euler()
    world = bpy.data.worlds.new('Morning sky')
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    sky = nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'NISHITA'
    sky.sun_disc = False
    sky.sun_elevation = el
    # Nishita puts its sun at (sin r, cos r) in the ground plane: r = 0 is +y.
    sky.sun_rotation = math.atan2(towards_sun.x, towards_sun.y)
    sky.air_density, sky.dust_density = 1., 2.
    lighting = nodes['Background']
    links.new(sky.outputs['Color'], lighting.inputs['Color'])
    lighting.inputs['Strength'].default_value = SKY_STRENGTH
    coord = nodes.new('ShaderNodeTexCoord')
    photo = nodes.new('ShaderNodeTexEnvironment')
    photo.image = bpy.data.images.load(str(ASSETS / WINDOW_VIEW), check_existing=True)
    turn = nodes.new('ShaderNodeMapping')
    turn.vector_type = 'VECTOR'
    turn.inputs['Rotation'].default_value = (0., 0., math.radians(WINDOW_VIEW_TURN_DEG))
    links.new(coord.outputs['Generated'], turn.inputs['Vector'])
    links.new(turn.outputs['Vector'], photo.inputs['Vector'])
    view = nodes.new('ShaderNodeBackground')
    view.inputs['Strength'].default_value = WINDOW_VIEW_STRENGTH
    links.new(photo.outputs['Color'], view.inputs['Color'])
    path = nodes.new('ShaderNodeLightPath')
    mix = nodes.new('ShaderNodeMixShader')
    links.new(path.outputs['Is Camera Ray'], mix.inputs['Fac'])
    links.new(lighting.outputs['Background'], mix.inputs[1])
    links.new(view.outputs['Background'], mix.inputs[2])
    links.new(mix.outputs['Shader'], nodes['World Output'].inputs['Surface'])
    return sun


# ------------------------------------------------------------------- build


def build_room(scene):
    """Build the room, the table, the furniture and the daylight."""
    # Grey plaster limewashed off-white: the scan's undulations and its tonal
    # drift stay, its grey goes.
    walls = scanned('Limewashed plaster walls', 'grey_plaster_03', WALL_TILE_M, hsv=(.3, 1.6),
                    wash=((.80, .79, .755), .38), rough_range=(.84, .97), normal_strength=.55)
    ceiling = scanned('Limewashed plaster ceiling', 'grey_plaster_03', WALL_TILE_M, hsv=(.3, 1.6),
                      wash=((.82, .81, .78), .3), rough_range=(.86, .97), normal_strength=.4)
    floor = scanned('Honed cream marble floor', 'marble_01', FLOOR_TILE_M, rough_range=(.20, .40))
    # Pale limestone pavers, as Mediterranean terraces are laid with.
    paving = scanned('Terrace stone pavers', 'stone_pavers', PAVING_TILE_M, hsv=(.75, 1.45),
                     rough_range=(.62, .92))
    coping = scanned('Parapet coping stone', 'stone_pavers', PAVING_TILE_M, hsv=(.6, 1.6),
                     rough_range=(.6, .9))
    wood = scanned('Worn table wood', 'wood_table_worn', LEG_WOOD_TILE_M, rough_range=(.45, .7))
    paint = painted('Blue-grey joinery paint', (.17, .245, .29), .42)
    glass = thin_glass()
    cloth = table(linen(), wood)
    shell(walls, ceiling, floor, paving, coping)
    leaves = french_door(paint, glass, coping)
    casement(paint, glass, walls)
    (s0, s1), (z0, z1) = DOOR['span'], DOOR['z']
    xo = ROOM_X[1] + WALL_THICK_M + .02
    portal('Door sky portal', (xo, (s0 + s1) / 2, (z0 + z1) / 2), (s1 - s0, z1 - z0), (-1, 0, 0))
    (s0, s1), (z0, z1) = SIDE_WINDOW['span'], SIDE_WINDOW['z']
    portal('Window sky portal', (xo, (s0 + s1) / 2, (z0 + z1) / 2), (s1 - s0, z1 - z0), (-1, 0, 0))
    furniture = furnish()
    daylight(scene)
    return dict(table_x=list(TABLE_X), table_y=list(TABLE_Y), table_top_z=TABLE_TOP_Z,
                cloth=cloth.name, door_leaves=[l.name for l in leaves], furniture=furniture,
                sun_elevation_deg=SUN_ELEVATION_DEG, sun_azimuth_deg=SUN_AZIMUTH_DEG,
                window_view=WINDOW_VIEW, chair_scale=round(CHAIR_SCALE, 4))


# ------------------------------------------------------------------- checks


def _world_bvh(obj, depsgraph, keep=None):
    """BVH of an object's evaluated mesh in world coordinates; ``keep`` filters
    faces by their world-space vertices."""
    from mathutils.bvhtree import BVHTree
    ev = obj.evaluated_get(depsgraph)
    mesh = ev.to_mesh()
    try:
        mw = ev.matrix_world
        verts = [mw @ v.co for v in mesh.vertices]
        polys = [tuple(p.vertices) for p in mesh.polygons]
        if keep is not None:
            polys = [p for p in polys if keep([verts[i] for i in p])]
        if not polys:
            return None
        return BVHTree.FromPolygons(verts, polys)
    finally:
        ev.to_mesh_clear()


def set_dressing_trees(bpy):
    """One BVH per piece of the set that the simulator does not know about.

    The floor, the threshold and the terrace paving are the simulator's floor
    plane and the cloth's top and its first 40 mm down the sides are its table
    box, so those are left out; the rest of the cloth's drop is set dressing.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    trees = {}
    for obj in bpy.data.objects:
        role = obj.get('pcve_role')
        if obj.type != 'MESH' or role in (None, SUPPORT):
            continue
        if role == CLOTH:
            tree = _world_bvh(obj, depsgraph, keep=lambda vs: max(v.z for v in vs) < TABLE_BOX_BOTTOM_Z - .002)
        else:
            tree = _world_bvh(obj, depsgraph)
        if tree is not None:
            trees[obj.name] = tree
    return trees


def check_clearance(trees, frames, keys, margin=.02):
    """Smallest gap between each moving orange and each piece of set dressing
    over every frame; raises if any is under ``margin``.

    Every orange is bounded by its sphere of RADIUS about its origin (the
    sliced one is a sphere with a cap removed, so the bound holds for it too).
    """
    from mathutils import Vector
    worst = {}
    for i, f in enumerate(frames):
        for key in keys:
            state = f[key]
            if not state.get('present'):
                continue
            # Between samples a thrown orange moves up to 0.3 m, so the path in
            # between is checked too (straight line, eight steps).
            here = Vector(state['location'])
            nxt = frames[i + 1][key] if i + 1 < len(frames) else None
            path = [here] if not (nxt and nxt.get('present')) else                 [here.lerp(Vector(nxt['location']), k / 8) for k in range(8)]
            for c in path:
                for name, tree in trees.items():
                    hit = tree.find_nearest(c)
                    if hit[0] is None:
                        continue
                    gap = hit[3] - RADIUS
                    if name not in worst or gap < worst[name][0]:
                        worst[name] = (gap, f['frame_index'], key)
    bad = {n: w for n, w in worst.items() if w[0] < margin}
    if bad:
        detail = ', '.join(f'{n}: {g * 1000:.0f} mm at frame {fi} ({k})' for n, (g, fi, k) in sorted(bad.items()))
        raise RuntimeError(f'A moving orange comes within {margin * 100:.0f} cm of the set: {detail}')
    closest = sorted(worst.items(), key=lambda kv: kv[1][0])[:6]
    return {n: dict(gap_m=round(g, 4), frame=fi, body=k) for n, (g, fi, k) in closest}


def check_occlusion(bpy, scene, camera, frames, keys, objects):
    """Cast rays from the camera to each orange in every frame it is in shot.

    A piece of furniture (role FURNITURE), or the cloth where it hangs below
    the collision box, in front of an orange's centre fails the take. Glass is
    looked through. The table box, the floor and the walls around the door
    opening are part of the place and are only counted.
    """
    from mathutils import Vector
    from bpy_extras.object_utils import world_to_camera_view
    origin = camera.matrix_world.translation.copy()
    blocked, walls, checked = [], 0, 0
    fruit = {o.name for o in objects.values()}
    for f in frames:
        scene.frame_set(f['frame_index'])
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for key in keys:
            state = f[key]
            if not state.get('present'):
                continue
            c = Vector(state['location'])
            uv = world_to_camera_view(scene, camera, c)
            if not (0. <= uv.x <= 1. and 0. <= uv.y <= 1. and uv.z > 0.):
                continue
            checked += 1
            start, d = origin.copy(), (c - origin)
            remaining = d.length - RADIUS
            d.normalize()
            while remaining > 1e-4:
                hit, loc, _n, _i, obj, _m = scene.ray_cast(depsgraph, start, d, distance=remaining)
                if not hit:
                    break
                role = obj.get('pcve_role') or (obj.parent.get('pcve_role') if obj.parent else None)
                if obj.name in fruit:
                    break
                if role == GLASS:
                    step = (loc - start).length + 1e-4
                    start = loc + d * 1e-4
                    remaining -= step
                    continue
                if role == FURNITURE or (role == CLOTH and loc.z < TABLE_BOX_BOTTOM_Z - .002):
                    blocked.append((f['frame_index'], key, obj.name))
                elif role == SHELL:
                    walls += 1
                break
    if blocked:
        first = blocked[:5]
        raise RuntimeError(f'Furniture hides an orange from the camera in {len(blocked)} checks: {first}')
    return dict(rays=checked, hidden_by_furniture=0, hidden_by_walls=walls)
