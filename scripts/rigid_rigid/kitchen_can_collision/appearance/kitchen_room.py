"""A farmhouse kitchen built to measure around the simulator's worktop.

The room is built from ordinary parts at their real sizes:

* the island top is a 40 mm oiled white-oak butcher block made of separate
  staves, and its top face *is* the simulator's table box (WORKTOP_X/Y,
  COUNTER_Z), so everything the cans touch on screen is the collider;
* painted shaker joinery under it and along the back wall, a terracotta tile
  floor, a stack-bond tile splashback and painted plaster walls, all from
  Poly Haven CC0 scans at their measured size;
* two real windows cut through the walls. A low sun comes in through the side
  window and lays a patch across the island, the back window adds sky light;
  no lamp is hidden anywhere in the room.

Nothing in here takes part in the simulation.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
import random
from scene_geometry import COUNTER_Z
from pcve_assets import asset as _pcve_asset

TEXTURES = _pcve_asset('polyhaven/kitchen_can_collision')

# The simulator's worktop is one fixed box (simulate_kitchen_can_collision.py:
# halfExtents 1.52 x 0.49 x 0.025 m, top face at COUNTER_Z). The oak top is that
# box's footprint and top face exactly.
WORKTOP_X = (-1.52, 1.52)
WORKTOP_Y = (-.49, .49)
WORKTOP_THICK_M = .04
# Butcher-block staves are 38-45 mm wide; 24 of them fill the 0.98 m top.
STAVE_COUNT = 24

# Room: plaster faces of the four walls and the ceiling height.
ROOM_X = (-3.0, 3.2)
ROOM_Y = (-2.6, 2.4)
CEILING_M = 2.7
WALL_THICK_M = .2

# Back run of cabinets along the y = ROOM_Y[1] wall.
BACK_TOP_Z = .92
BACK_FRONT_Y = 1.80

# Real sizes of the Poly Haven scans (api.polyhaven.com/info "dimensions").
OAK_TILE_M = .50           # white_oak_veneer
FLOOR_TILE_M = 2.08        # terracotta_floor_tiles
SPLASHBACK_TILE_M = 1.27   # long_white_tiles
WALL_TILE_M = 3.0          # beige_wall_001

# Openings, as (along-wall span, z span) on their wall.
SIDE_WINDOW = dict(span=(-2.05, -.55), z=(.86, 2.30))   # wall x = ROOM_X[1]
BACK_WINDOW = dict(span=(-.10, 1.40), z=(1.10, 2.30))   # wall y = ROOM_Y[1]

# Late-afternoon sun, low enough to reach the island through the side window.
# SUN_AZIMUTH_DEG is the compass direction *towards* the sun, in degrees from +x
# towards +y; the light travels the opposite way, across the island towards -x.
SUN_ELEVATION_DEG = 17.0
SUN_AZIMUTH_DEG = -22.0
SUN_STRENGTH = 3.6
SKY_STRENGTH = 1.0


# ------------------------------------------------------------------ geometry


def box(name, lo, hi, mat=None, bevel=0., segments=2):
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
    return obj


def cylinder(name, centre, radius, depth, axis, mat, vertices=32):
    import bpy
    rotation = {'x': (0, math.pi / 2, 0), 'y': (math.pi / 2, 0, 0), 'z': (0, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                        location=centre, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    mod = obj.modifiers.new('Eased edges', 'BEVEL')
    mod.width, mod.segments, mod.limit_method = min(radius, depth) * .2, 2, 'ANGLE'
    bpy.ops.object.shade_smooth()
    return obj


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


def _scan_nodes(mat, stem, vector, tint=None, rough_range=None, normal_strength=1., projection='FLAT'):
    """Wire one Poly Haven 2k set (diff / rough / nor_gl) into the BSDF."""
    import bpy
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']

    def image(kind, colour):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(TEXTURES / f'{stem}_{kind}_2k.jpg'), check_existing=True)
        if not colour:
            node.image.colorspace_settings.name = 'Non-Color'
        node.projection = projection
        node.projection_blend = .15
        node.interpolation = 'Cubic'
        links.new(vector, node.inputs['Vector'])
        return node

    colour = image('diff', True).outputs['Color']
    if tint is not None:
        # A vector multiply, not a colour mix: colour sockets clamp at 1 and
        # some tints lift a scan slightly.
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


def scanned(name, stem, tile_m, base=(.5, .5, .5), **options):
    """A scan box-projected in world metres (every room part is built at the
    origin), so floor tiles and wall paint keep their real size everywhere."""
    mat = principled(name, base, .5)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1 / tile_m,) * 3
    links.new(coord.outputs['Object'], mapping.inputs['Vector'])
    _scan_nodes(mat, stem, mapping.outputs['Vector'], projection='BOX', **options)
    return mat


def oak_staves():
    """Oiled white oak, one random patch of the scan per stave.

    Every stave is its own object, so Object Info > Random gives each one its
    own offset into the 0.5 m veneer scan and its own slight tone: a butcher
    block is glued from many boards and never reads as one printed sheet. The
    grain of the scan runs along its v axis, so v follows world x (the staves'
    length). Using y + z across the grain keeps the grain horizontal on the
    40 mm front edge as well as on the top.
    """
    mat = principled('Oiled white oak butcher block', (.42, .30, .19), .45)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coord = nodes.new('ShaderNodeTexCoord')
    info = nodes.new('ShaderNodeObjectInfo')
    xyz = nodes.new('ShaderNodeSeparateXYZ')
    links.new(coord.outputs['Object'], xyz.inputs['Vector'])

    def math_node(op, a, b):
        node = nodes.new('ShaderNodeMath')
        node.operation = op
        for socket, value in zip(node.inputs, (a, b)):
            if isinstance(value, (int, float)):
                socket.default_value = value
            else:
                links.new(value, socket)
        return node.outputs['Value']

    across = math_node('ADD', xyz.outputs['Y'], xyz.outputs['Z'])
    u = math_node('ADD', math_node('DIVIDE', across, OAK_TILE_M), math_node('MULTIPLY', info.outputs['Random'], 37.3))
    v = math_node('ADD', math_node('DIVIDE', xyz.outputs['X'], OAK_TILE_M), math_node('MULTIPLY', info.outputs['Random'], 91.7))
    uv = nodes.new('ShaderNodeCombineXYZ')
    links.new(u, uv.inputs['X'])
    links.new(v, uv.inputs['Y'])
    _scan_nodes(mat, 'white_oak_veneer', uv.outputs['Vector'], tint=(.96, .86, .70),
                rough_range=(.30, .52), normal_strength=.55)
    # Per-stave tone: boards from different logs differ by a few percent.
    bsdf = nodes['Principled BSDF']
    colour_link = bsdf.inputs['Base Color'].links[0]
    shade = nodes.new('ShaderNodeVectorMath')
    shade.operation = 'MULTIPLY'
    tone = nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].color = (.80, .76, .70, 1)
    tone.color_ramp.elements[1].color = (1., .97, .92, 1)
    links.new(info.outputs['Random'], tone.inputs['Fac'])
    links.new(colour_link.from_socket, shade.inputs[0])
    links.new(tone.outputs['Color'], shade.inputs[1])
    links.new(shade.outputs['Vector'], bsdf.inputs['Base Color'])
    return mat


def painted(name, color, roughness=.42):
    """Eggshell paint on joinery: one colour that drifts a little in tone and
    sheen, with the faint brush texture of a hand-painted kitchen."""
    mat = principled(name, color, roughness)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    position = nodes.new('ShaderNodeNewGeometry')
    drift = nodes.new('ShaderNodeTexNoise')
    drift.inputs['Scale'].default_value = 1.6
    drift.inputs['Detail'].default_value = 3.
    links.new(position.outputs['Position'], drift.inputs['Vector'])
    tone = nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].color = (*(c * .94 for c in color), 1)
    tone.color_ramp.elements[1].color = (*(min(1., c * 1.04) for c in color), 1)
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

    Rays through it stay camera rays (the world shows the garden photograph to
    the camera only) and it casts no shadow. Cycles' Fresnel node inverts the
    IOR on back faces, which would turn a pane seen obliquely from inside black
    by total internal reflection; feeding 1/1.52 on back faces cancels that.
    """
    import bpy
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


# ---------------------------------------------------------------- the island


def island_top(oak):
    """The butcher block: STAVE_COUNT staves across y, each finger-jointed into
    lengths of 0.55-1.25 m along x. Top faces lie exactly on COUNTER_Z and the
    outline is exactly the simulator's box. The staves are glued flush, so the
    joints show only as the change of grain and tone from board to board."""
    rng = random.Random(4207)
    width = (WORKTOP_Y[1] - WORKTOP_Y[0]) / STAVE_COUNT
    staves = []
    for j in range(STAVE_COUNT):
        y0 = WORKTOP_Y[0] + j * width
        x = WORKTOP_X[0]
        k = 0
        while x < WORKTOP_X[1] - 1e-9:
            length = rng.uniform(.55, 1.25)
            x1 = WORKTOP_X[1] if WORKTOP_X[1] - (x + length) < .30 else x + length
            staves.append(box(f'Island oak stave {j:02d}-{k}', (x, y0, COUNTER_Z - WORKTOP_THICK_M),
                              (x1, y0 + width, COUNTER_Z), oak))
            x, k = x1, k + 1
    return staves


def shaker_front(name, x0, x1, z0, z1, face_y, facing, paint, brass, handle='knob'):
    """A shaker door or drawer front: a recessed panel inside a 62 mm frame,
    hung on a carcass face at ``face_y`` that faces ``facing`` (-1 or +1 in y)."""
    stile = .062
    s = facing
    panel = (face_y + s * .012, face_y + s * .002)
    frame = (face_y + s * .020, face_y)
    lo_y, hi_y = min(frame), max(frame)
    plo_y, phi_y = min(panel), max(panel)
    box(f'{name} panel', (x0 + stile - .004, plo_y, z0 + stile - .004), (x1 - stile + .004, phi_y, z1 - stile + .004), paint)
    box(f'{name} left stile', (x0, lo_y, z0), (x0 + stile, hi_y, z1), paint, .0015)
    box(f'{name} right stile', (x1 - stile, lo_y, z0), (x1, hi_y, z1), paint, .0015)
    box(f'{name} bottom rail', (x0 + stile, lo_y, z0), (x1 - stile, hi_y, z0 + stile), paint, .0015)
    box(f'{name} top rail', (x0 + stile, lo_y, z1 - stile), (x1 - stile, hi_y, z1), paint, .0015)
    front = face_y + s * .020
    if handle == 'bar':
        zc = (z0 + z1) / 2
        half = min(.08, (x1 - x0) / 4)
        cylinder(f'{name} brass pull', ((x0 + x1) / 2, front + s * .032, zc), .0055, 2 * half, 'x', brass, 24)
        for sign in (-1, 1):
            cylinder(f'{name} pull post', ((x0 + x1) / 2 + sign * (half - .012), front + s * .016, zc), .0045, .032, 'y', brass, 16)
    else:
        xk = x1 - .045 if handle == 'knob_right' else x0 + .045
        cylinder(f'{name} knob stem', (xk, front + s * .012, z1 - .085), .006, .024, 'y', brass, 16)
        cylinder(f'{name} knob', (xk, front + s * .028, z1 - .085), .0145, .012, 'y', brass, 32)


def island_base(paint, plinth, brass):
    """Painted carcass under the oak: drawers over doors on the camera side, a
    recessed plinth, and a 0.29 m overhang on the far side for the stools."""
    top_under = COUNTER_Z - WORKTOP_THICK_M
    face_y = -.465
    box('Island carcass', (WORKTOP_X[0] + .05, face_y, .10), (WORKTOP_X[1] - .05, .20, top_under), paint)
    box('Island plinth', (WORKTOP_X[0] + .11, face_y + .07, 0.), (WORKTOP_X[1] - .11, .14, .10), plinth)
    bays = 6
    x_lo, x_hi = WORKTOP_X[0] + .05, WORKTOP_X[1] - .05
    width = (x_hi - x_lo) / bays
    for b in range(bays):
        x0, x1 = x_lo + b * width + .0015, x_lo + (b + 1) * width - .0015
        shaker_front(f'Island drawer {b + 1}', x0, x1, top_under - .175, top_under - .004, face_y, -1, paint, brass, 'bar')
        shaker_front(f'Island door {b + 1}', x0, x1, .104, top_under - .179, face_y, -1, paint, brass,
                     'knob_right' if b % 2 == 0 else 'knob')
    # Plain painted end panels and the back of the seating side.
    for x0, x1 in ((WORKTOP_X[0] + .03, WORKTOP_X[0] + .05), (WORKTOP_X[1] - .05, WORKTOP_X[1] - .03)):
        box('Island end panel', (x0, face_y - .02, 0.), (x1, .20, top_under), paint, .0015)


# ------------------------------------------------------------- the back run


def back_run(oak_back, paint, plinth, brass, splashback):
    """Base cabinets along the back wall with an oak top and a tiled splashback."""
    wall_y = ROOM_Y[1]
    face_y = BACK_FRONT_Y + .025
    top_under = BACK_TOP_Z - .04
    x_lo, x_hi = ROOM_X[0], ROOM_X[1]
    box('Back run carcass', (x_lo, face_y, .10), (x_hi, wall_y, top_under), paint)
    box('Back run plinth', (x_lo, face_y + .07, 0.), (x_hi, wall_y, .10), plinth)
    box('Back run oak top', (x_lo, BACK_FRONT_Y, top_under), (x_hi, wall_y, BACK_TOP_Z), oak_back, .002)
    bay = .60
    count = int((x_hi - x_lo) // bay)
    start = x_lo + ((x_hi - x_lo) - count * bay) / 2
    if start - x_lo > .01:
        box('Back run filler left', (x_lo, face_y - .02, .10), (start, face_y, top_under), paint)
        box('Back run filler right', (start + count * bay, face_y - .02, .10), (x_hi, face_y, top_under), paint)
    for b in range(count):
        x0, x1 = start + b * bay + .0015, start + (b + 1) * bay - .0015
        shaker_front(f'Back drawer {b + 1}', x0, x1, top_under - .17, top_under - .004, face_y, -1, paint, brass, 'bar')
        shaker_front(f'Back door {b + 1}', x0, x1, .104, top_under - .174, face_y, -1, paint, brass,
                     'knob_right' if b % 2 else 'knob')
    # Splashback up to the window sill, and on either side of the window up to 1.45 m.
    sx0, sx1 = BACK_WINDOW['span']
    sz0 = BACK_WINDOW['z'][0]
    box('Tiled splashback', (x_lo, wall_y - .008, BACK_TOP_Z), (x_hi, wall_y, sz0 - .028), splashback)
    box('Tiled splashback left', (x_lo, wall_y - .008, sz0 - .028), (sx0 - .05, wall_y, 1.45), splashback)
    box('Tiled splashback right', (sx1 + .05, wall_y - .008, sz0 - .028), (x_hi, wall_y, 1.45), splashback)


# -------------------------------------------------------------------- shell


def wall_x(name, x0, x1, y_span, z_span, hole, mat):
    """A wall at constant x built as panels around one rectangular opening."""
    (y0, y1), (z0, z1) = y_span, z_span
    if hole is None:
        box(name, (x0, y0, z0), (x1, y1, z1), mat)
        return
    (hy0, hy1), (hz0, hz1) = hole
    box(f'{name} / below opening', (x0, hy0, z0), (x1, hy1, hz0), mat)
    box(f'{name} / above opening', (x0, hy0, hz1), (x1, hy1, z1), mat)
    box(f'{name} / before opening', (x0, y0, z0), (x1, hy0, z1), mat)
    box(f'{name} / after opening', (x0, hy1, z0), (x1, y1, z1), mat)


def wall_y(name, y0, y1, x_span, z_span, hole, mat):
    """A wall at constant y built as panels around one rectangular opening."""
    (x0, x1), (z0, z1) = x_span, z_span
    if hole is None:
        box(name, (x0, y0, z0), (x1, y1, z1), mat)
        return
    (hx0, hx1), (hz0, hz1) = hole
    box(f'{name} / below opening', (hx0, y0, z0), (hx1, y1, hz0), mat)
    box(f'{name} / above opening', (hx0, y0, hz1), (hx1, y1, z1), mat)
    box(f'{name} / before opening', (x0, y0, z0), (hx0, y1, z1), mat)
    box(f'{name} / after opening', (hx1, y0, z0), (x1, y1, z1), mat)


def window(name, wall, span, z, sash_paint, sill_mat):
    """Timber casement in the middle of the reveal: frame, one mullion, a
    transom, thin glass and an interior window board. ``wall`` is 'x' for the
    side wall (span along y) or 'y' for the back wall (span along x)."""
    (s0, s1), (z0, z1) = span, z
    face = ROOM_X[1] if wall == 'x' else ROOM_Y[1]
    depth = (face + .07, face + .12)

    def part(label, a0, a1, c0, c1, d=depth, mat=sash_paint, bevel=.001):
        if wall == 'x':
            return box(f'{name} {label}', (d[0], a0, c0), (d[1], a1, c1), mat, bevel)
        return box(f'{name} {label}', (a0, d[0], c0), (a1, d[1], c1), mat, bevel)

    bar = .058
    part('head', s0, s1, z1 - bar, z1)
    part('bottom rail', s0, s1, z0, z0 + bar)
    part('near jamb', s0, s0 + bar, z0 + bar, z1 - bar)
    part('far jamb', s1 - bar, s1, z0 + bar, z1 - bar)
    mid = (s0 + s1) / 2
    part('mullion', mid - .025, mid + .025, z0 + bar, z1 - bar, (depth[0] + .004, depth[1] - .004))
    transom = z1 - .42
    part('transom lower', s0 + bar, mid - .025, transom - .022, transom + .022, (depth[0] + .004, depth[1] - .004))
    part('transom upper', mid + .025, s1 - bar, transom - .022, transom + .022, (depth[0] + .004, depth[1] - .004))
    glass = part('glass', s0 + .01, s1 - .01, z0 + .01, z1 - .01, ((depth[0] + depth[1]) / 2 - .003, (depth[0] + depth[1]) / 2 + .003), thin_glass(), 0.)
    glass.visible_shadow = False
    part('window board', s0 - .05, s1 + .05, z0 - .028, z0, (face - .035, face + .07), sill_mat, .002)
    return glass


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
    obj.rotation_euler = (Vector(inward)).to_track_quat('-Z', 'Y').to_euler()
    return obj


def shell(walls, ceiling, floor, skirting):
    """Floor, ceiling and four walls with the two window openings."""
    (x0, x1), (y0, y1), t = ROOM_X, ROOM_Y, WALL_THICK_M
    box('Terracotta floor', (x0 - t, y0 - t, -.06), (x1 + t, y1 + t, 0.), floor)
    box('Ceiling', (x0 - t, y0 - t, CEILING_M), (x1 + t, y1 + t, CEILING_M + .12), ceiling)
    z = (-.06, CEILING_M)
    side = (SIDE_WINDOW['span'], SIDE_WINDOW['z'])
    back = (BACK_WINDOW['span'], BACK_WINDOW['z'])
    wall_x('Side wall (window)', x1, x1 + t, (y0 - t, y1 + t), z, side, walls)
    wall_x('Left wall', x0 - t, x0, (y0 - t, y1 + t), z, None, walls)
    wall_y('Back wall (window)', y1, y1 + t, (x0, x1), z, back, walls)
    wall_y('Wall behind camera', y0 - t, y0, (x0, x1), z, None, walls)
    # Skirting where no cabinet stands against the wall.
    box('Skirting left wall', (x0, y0, 0.), (x0 + .018, BACK_FRONT_Y, .11), skirting, .0015)
    box('Skirting side wall', (x1 - .018, y0, 0.), (x1, BACK_FRONT_Y, .11), skirting, .0015)
    box('Skirting camera wall', (x0, y0, 0.), (x1, y0 + .018, .11), skirting, .0015)


# ------------------------------------------------------------------ daylight


def daylight(scene, window_view):
    """A sun lamp and a Nishita sky outside the windows, nothing inside.

    Light rays see the physical sky (with its own sun disc off: the lamp is the
    only sun). Camera rays that leave through the glass see ``window_view``, a
    garden photograph with distant content, instead of the sky model's dark
    ground below the horizon.
    """
    import bpy
    from mathutils import Vector
    el, az = math.radians(SUN_ELEVATION_DEG), math.radians(SUN_AZIMUTH_DEG)
    towards_sun = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    data = bpy.data.lights.new('Late afternoon sun', 'SUN')
    data.energy, data.angle, data.color = SUN_STRENGTH, math.radians(.53), (1., .86, .70)
    sun = bpy.data.objects.new('Late afternoon sun', data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (-towards_sun).to_track_quat('-Z', 'Y').to_euler()
    world = bpy.data.worlds.new('Late afternoon sky')
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    sky = nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'NISHITA'
    sky.sun_disc = False
    sky.sun_elevation = el
    # Nishita puts its sun at (sin r, cos r) in the ground plane: r = 0 is +y.
    sky.sun_rotation = math.atan2(towards_sun.x, towards_sun.y)
    sky.air_density, sky.dust_density = 1., 2.5
    lighting = nodes['Background']
    links.new(sky.outputs['Color'], lighting.inputs['Color'])
    lighting.inputs['Strength'].default_value = SKY_STRENGTH
    if window_view is None:
        return sun
    coord = nodes.new('ShaderNodeTexCoord')
    photo = nodes.new('ShaderNodeTexEnvironment')
    photo.image = bpy.data.images.load(str(window_view), check_existing=True)
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


# What the camera sees through the back window: Poly Haven approaching_storm, a
# mown meadow with its tree line far enough away to pass for a view at infinity.
WINDOW_VIEW = 'approaching_storm_2k.hdr'
# Its sun stands at u = 0.5994 (azimuth -35.8 deg, elevation 18.5 deg in the
# photograph's own frame); turning the lookup by the difference puts it where
# the lamp is, so the meadow's shadows fall the same way as the room's.
WINDOW_VIEW_TURN_DEG = -35.8 - SUN_AZIMUTH_DEG
WINDOW_VIEW_STRENGTH = 1.


def build_kitchen(scene):
    """Build the room, the island and the back run; return what was built."""
    oak = oak_staves()
    oak_back = scanned('Oiled oak back worktop', 'white_oak_veneer', OAK_TILE_M, tint=(.96, .86, .70),
                       rough_range=(.30, .52), normal_strength=.55)
    sage = painted('Sage green eggshell joinery', (.155, .205, .150), .40)
    cream = painted('Warm white eggshell joinery', (.62, .59, .52), .38)
    plinth = principled('Shadowed plinth paint', (.035, .037, .034), .6)
    brass = principled('Aged brass hardware', (.62, .45, .22), .32, 1.)
    walls = scanned('Painted plaster walls', 'beige_wall_001', WALL_TILE_M, tint=(1.18, 1.14, 1.08),
                    rough_range=(.80, .95), normal_strength=.6)
    ceiling = principled('Ceiling white', (.72, .71, .68), .92)
    floor = scanned('Terracotta floor tiles', 'terracotta_floor_tiles', FLOOR_TILE_M, tint=(1.15, 1.05, .98),
                    rough_range=(.45, .80))
    splashback = scanned('Stack-bond glazed splashback tiles', 'long_white_tiles', SPLASHBACK_TILE_M,
                         rough_range=(.08, .35), normal_strength=.8)
    skirting = principled('Skirting paint', (.62, .59, .52), .45)
    sash = principled('Window sash paint', (.66, .65, .62), .5)

    staves = island_top(oak)
    island_base(sage, plinth, brass)
    back_run(oak_back, cream, plinth, brass, splashback)
    shell(walls, ceiling, floor, skirting)
    window('Side window', 'x', SIDE_WINDOW['span'], SIDE_WINDOW['z'], sash, oak_back)
    window('Back window', 'y', BACK_WINDOW['span'], BACK_WINDOW['z'], sash, oak_back)
    (s0, s1), (z0, z1) = SIDE_WINDOW['span'], SIDE_WINDOW['z']
    portal('Side window sky portal', (ROOM_X[1] + WALL_THICK_M + .01, (s0 + s1) / 2, (z0 + z1) / 2), (s1 - s0, z1 - z0), (-1, 0, 0))
    (s0, s1), (z0, z1) = BACK_WINDOW['span'], BACK_WINDOW['z']
    portal('Back window sky portal', ((s0 + s1) / 2, ROOM_Y[1] + WALL_THICK_M + .01, (z0 + z1) / 2), (s1 - s0, z1 - z0), (0, -1, 0))
    # The ground outside stops sky light from below; the camera looks through it.
    ground = box('Ground outside', (-60., -60., -.6), (60., 60., -.3), principled('Ground outside', (.16, .15, .12), .9))
    ground.visible_camera = False
    view = TEXTURES / WINDOW_VIEW if WINDOW_VIEW else None
    daylight(scene, view)
    return dict(worktop_staves=len(staves), worktop_x=list(WORKTOP_X), worktop_y=list(WORKTOP_Y),
                worktop_top_z=COUNTER_Z, sun_elevation_deg=SUN_ELEVATION_DEG, sun_azimuth_deg=SUN_AZIMUTH_DEG,
                window_view=WINDOW_VIEW)
