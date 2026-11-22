"""A school sports hall built on the simulator's floor plane.

This module builds an ordinary school hall at real size, around the one
physical surface the simulator shares with it, the floor at
``COURT['floor_z']``:

* a strip-maple sports floor (Poly Haven ``wooden_floor_01`` laid as narrow
  strips under a gloss coat) with a FIBA basketball court painted on it,
  measured from the rim the ball circles;
* vinyl crash pads on every wall up to two metres (Poly Haven
  ``leather_white`` grain), painted block walls above them (``concrete_wall_004``)
  and a rubber cove base below;
* a row of tall windows high up on both long walls, a sun lamp and a physical
  sky outside them, and a cloud-sky photograph that only the camera sees through
  the glass (``kloofendal_48d_partly_cloudy_puresky``);
* pendant high-bay lamps under the roof (Poly Haven ``hanging_industrial_lamp``),
  each lit by a disc light at its own diffuser;
* a pair of steel doors in the end wall and a storage crate against the pads.

Nothing here is a collider. ``check_clearance`` refuses a take in which the
ball would pass within 2 cm of any of it, and ``occluders`` reports any of it
standing between the camera and the ball.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

import math

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from pcve_assets import asset as _pcve_asset
from scene_config import COURT, SCENE_NAME

TEXTURES = _pcve_asset('polyhaven') / SCENE_NAME
FZ = COURT['floor_z']

# Interior faces of the hall. The end wall stands 0.85 m behind the goal's base;
# the hall is long enough for a full 28 m court measured from this rim, and wide
# enough that the fastest edit (which lands 6.3 m to the right) never nears a
# wall.
HALL_X = (-9.0, 9.0)
HALL_Y = (-22.3, 9.40)
HALL_HEIGHT = 7.6
WALL_THICK = 0.30
PAD_TOP, PAD_BOTTOM, PAD_THICK, PAD_WIDTH = 2.00, 0.10, 0.05, 1.22
COVE_HEIGHT = 0.10
# Steel doors in the end wall, right of the goal (x span, height above floor).
DOOR_X, DOOR_HEIGHT = (1.15, 2.95), 2.40
# Window openings on both long walls: centres along y, width, sill and head.
WINDOW_Y = (7.2, 2.6, -2.0, -6.6, -11.2, -15.8, -20.4)
WINDOW_WIDTH, WINDOW_SILL, WINDOW_HEAD = 3.0, 2.70, 5.90
# Pendant lamps under the roof.
LAMP_X = (-6.0, -2.0, 2.0, 6.0)
LAMP_Y = (7.0, 2.5, -2.0, -6.5, -11.0, -15.5, -20.0)

# Court markings (FIBA), measured from the point under the rim centre.
RIM_X, RIM_Y = COURT['rim_center'][0], COURT['rim_center'][1]
LINE_W = 0.05
END_Y = RIM_Y + 1.575            # inner edge of the end line
COURT_HALF_W = 7.5               # inner edge of the side lines
COURT_LENGTH = 28.0
KEY_HALF_W = 2.45                # outer edge of the lane lines
FREE_THROW_Y = END_Y - 5.80      # far edge of the free-throw line
THREE_R, THREE_X = 6.75, 6.60
NO_CHARGE_R = 1.25

# Poly Haven sizes: wooden_floor_01 is a 1.988 m patch of 0.11 m strips of
# short boards. Laid at 0.6 across the strips they are 66 mm wide, the width of
# sports-hall maple, and at 1.4 along them the boards are hall-floor lengths
# (the grain is stretched along the board, where it runs anyway).
# leather_white is a 0.30 m patch of grain; concrete_wall_004 a 2 m patch of
# painted blocks. The *_MEAN values are the scans' mean linear colour or
# luminance, used to recolour them around their own average.
FLOOR_TILE_ACROSS_M = 1.988 * 0.6
FLOOR_TILE_ALONG_M = 1.988 * 1.4
FLOOR_SCAN_MEAN = (0.449, 0.216, 0.079)
VINYL_SCAN_LUMA = 0.288
BLOCK_SCAN_LUMA = 0.170
VINYL_TILE_M = 0.30
BLOCK_TILE_M = 2.0

# Poly Haven kloofendal_48d_partly_cloudy_puresky: its sun stands at u = 0.5950,
# v = 0.766, i.e. azimuth (0.5 - u) * 360 = -34.2 deg in the photograph's own
# frame and 47.9 deg up. The lamp below uses the same elevation.
WINDOW_VIEW = 'kloofendal_48d_partly_cloudy_puresky_2k.hdr'
WINDOW_VIEW_SUN_AZIMUTH_DEG = -34.2


# ------------------------------------------------------------------ helpers


def _link(obj):
    bpy.context.collection.objects.link(obj)
    return obj


def box(name, lo, hi, mat=None, bevel=0.0, segments=2):
    """An axis-aligned box from its two corners, transform-free (object = world)."""
    lo, hi = Vector(lo), Vector(hi)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=hi - lo, verts=bm.verts)
    bmesh.ops.translate(bm, vec=(lo + hi) / 2, verts=bm.verts)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = _link(bpy.data.objects.new(name, mesh))
    if mat is not None:
        obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new('Soft edges', 'BEVEL')
        mod.width, mod.segments = bevel, segments
        mod.limit_method = 'ANGLE'
        obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return obj


def _image(nodes, name, colour, vector, projection='FLAT'):
    node = nodes.new('ShaderNodeTexImage')
    node.image = bpy.data.images.load(str(TEXTURES / name), check_existing=True)
    if not colour:
        node.image.colorspace_settings.name = 'Non-Color'
    node.extension = 'REPEAT'
    node.projection = projection
    if projection == 'BOX':
        node.projection_blend = 0.1
    node.id_data.links.new(vector, node.inputs['Vector'])
    return node


def _new_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    return mat, nodes, mat.node_tree.links, nodes.get('Principled BSDF')


def _math(nodes, links, op, a, b=None, clamp=False):
    node = nodes.new('ShaderNodeMath')
    node.operation = op
    node.use_clamp = clamp
    for socket, value in zip(node.inputs, (a, b)):
        if value is None:
            continue
        if isinstance(value, (int, float)):
            socket.default_value = value
        else:
            links.new(value, socket)
    return node.outputs[0]


def _mix_colour(nodes, links, factor, a, b, blend='MIX'):
    node = nodes.new('ShaderNodeMix')
    node.data_type = 'RGBA'
    node.blend_type = blend
    sockets = [s for s in node.inputs if s.type == 'RGBA']
    for socket, value in zip(sockets, (a, b)):
        if isinstance(value, tuple):
            socket.default_value = (*value, 1.0)
        else:
            links.new(value, socket)
    if isinstance(factor, (int, float)):
        node.inputs['Factor'].default_value = factor
    else:
        links.new(factor, node.inputs['Factor'])
    return [s for s in node.outputs if s.type == 'RGBA'][0]


# ----------------------------------------------------------- floor markings


def _court_mask(nodes, links, x, y):
    """1 on painted lines, 0 elsewhere, from world x/y; returns (lines, key)."""
    def inside(value, lo, hi):
        above = _math(nodes, links, 'GREATER_THAN', value, lo)
        below = _math(nodes, links, 'LESS_THAN', value, hi)
        return _math(nodes, links, 'MULTIPLY', above, below)

    def rect(x0, x1, y0, y1):
        return _math(nodes, links, 'MULTIPLY', inside(x, x0, x1), inside(y, y0, y1))

    def ring(cx, cy, r_outer, keep):
        dx = _math(nodes, links, 'SUBTRACT', x, cx)
        dy = _math(nodes, links, 'SUBTRACT', y, cy)
        r = _math(nodes, links, 'SQRT', _math(nodes, links, 'ADD',
                  _math(nodes, links, 'MULTIPLY', dx, dx), _math(nodes, links, 'MULTIPLY', dy, dy)))
        band = inside(r, r_outer - LINE_W, r_outer)
        return _math(nodes, links, 'MULTIPLY', band, keep)

    far_end = END_Y - COURT_LENGTH
    parts = [
        rect(-COURT_HALF_W - LINE_W, COURT_HALF_W + LINE_W, END_Y, END_Y + LINE_W),          # end line
        rect(-COURT_HALF_W - LINE_W, COURT_HALF_W + LINE_W, far_end - LINE_W, far_end),       # far end line
        rect(-COURT_HALF_W - LINE_W, -COURT_HALF_W, far_end - LINE_W, END_Y + LINE_W),        # side lines
        rect(COURT_HALF_W, COURT_HALF_W + LINE_W, far_end - LINE_W, END_Y + LINE_W),
        rect(-KEY_HALF_W, -KEY_HALF_W + LINE_W, FREE_THROW_Y, END_Y),                          # lane lines
        rect(KEY_HALF_W - LINE_W, KEY_HALF_W, FREE_THROW_Y, END_Y),
        rect(-KEY_HALF_W, KEY_HALF_W, FREE_THROW_Y, FREE_THROW_Y + LINE_W),                    # free-throw line
        ring(RIM_X, FREE_THROW_Y + LINE_W / 2, 1.80, _math(nodes, links, 'LESS_THAN', y, FREE_THROW_Y)),
        # Three-point line: two straight runs from the end line, then the arc.
        rect(-THREE_X - LINE_W, -THREE_X, RIM_Y - math.sqrt(THREE_R ** 2 - THREE_X ** 2), END_Y),
        rect(THREE_X, THREE_X + LINE_W, RIM_Y - math.sqrt(THREE_R ** 2 - THREE_X ** 2), END_Y),
        ring(RIM_X, RIM_Y, THREE_R, _math(nodes, links, 'MULTIPLY',
             _math(nodes, links, 'LESS_THAN', y, RIM_Y - math.sqrt(THREE_R ** 2 - THREE_X ** 2) + 1e-3),
             inside(x, -THREE_X - LINE_W, THREE_X + LINE_W))),
        # No-charge semicircle and its two short legs towards the end line.
        ring(RIM_X, RIM_Y, NO_CHARGE_R + LINE_W, _math(nodes, links, 'LESS_THAN', y, RIM_Y)),
        rect(-NO_CHARGE_R - LINE_W, -NO_CHARGE_R, RIM_Y, RIM_Y + 0.375),
        rect(NO_CHARGE_R, NO_CHARGE_R + LINE_W, RIM_Y, RIM_Y + 0.375),
        # Centre line and centre circle, out of shot but part of the court.
        rect(-COURT_HALF_W, COURT_HALF_W, END_Y - COURT_LENGTH / 2 - LINE_W / 2,
             END_Y - COURT_LENGTH / 2 + LINE_W / 2),
        ring(RIM_X, END_Y - COURT_LENGTH / 2, 1.80, 1.0),
    ]
    # Lane marks: short ticks outside both lane lines.
    for offset in (1.75, 2.60, 3.45, 4.30):
        yy = END_Y - offset
        parts.append(rect(-KEY_HALF_W - 0.10, -KEY_HALF_W, yy - LINE_W, yy))
        parts.append(rect(KEY_HALF_W, KEY_HALF_W + 0.10, yy - LINE_W, yy))
    lines = parts[0]
    for part in parts[1:]:
        lines = _math(nodes, links, 'MAXIMUM', lines, part)
    key = rect(-KEY_HALF_W + LINE_W, KEY_HALF_W - LINE_W, FREE_THROW_Y + LINE_W, END_Y)
    return lines, key


def floor_material():
    """Strip maple under a gloss coat, with the court painted on it.

    The strips run along the court. The scan is laid in bands one tile wide,
    each slid along the strips by its own random amount, so the board ends never
    line up into the grid a plain repeat would draw across 20 m of floor.
    """
    mat, nodes, links, bsdf = _new_material('Sports maple, gloss coat')
    geometry = nodes.new('ShaderNodeNewGeometry')
    xyz = nodes.new('ShaderNodeSeparateXYZ')
    links.new(geometry.outputs['Position'], xyz.inputs['Vector'])
    x, y = xyz.outputs['X'], xyz.outputs['Y']
    # u runs along the strips (world y), v across them (world x).
    band = _math(nodes, links, 'FLOOR', _math(nodes, links, 'DIVIDE', x, FLOOR_TILE_ACROSS_M))
    hash_in = nodes.new('ShaderNodeCombineXYZ')
    links.new(band, hash_in.inputs['X'])
    noise = nodes.new('ShaderNodeTexWhiteNoise')
    noise.noise_dimensions = '3D'
    links.new(hash_in.outputs['Vector'], noise.inputs['Vector'])
    slide = _math(nodes, links, 'MULTIPLY', noise.outputs['Value'], 7.31)
    u = _math(nodes, links, 'DIVIDE', _math(nodes, links, 'ADD', y, slide), FLOOR_TILE_ALONG_M)
    v = _math(nodes, links, 'DIVIDE', x, FLOOR_TILE_ACROSS_M)
    uv = nodes.new('ShaderNodeCombineXYZ')
    links.new(u, uv.inputs['X'])
    links.new(v, uv.inputs['Y'])
    vector = uv.outputs['Vector']
    diffuse = _image(nodes, 'wooden_floor_01_diff_2k.jpg', True, vector)
    rough = _image(nodes, 'wooden_floor_01_rough_2k.jpg', False, vector)
    normal_map = _image(nodes, 'wooden_floor_01_nor_gl_2k.jpg', False, vector)
    # The scan is a honey-coloured lacquered oak with a strong board-to-board
    # contrast; hall maple is paler and far more even. The scan is pulled 45 %
    # towards its own mean colour, then lifted and partly desaturated.
    even = _mix_colour(nodes, links, 0.55, FLOOR_SCAN_MEAN, diffuse.outputs['Color'])
    hsv = nodes.new('ShaderNodeHueSaturation')
    hsv.inputs['Hue'].default_value = 0.505
    hsv.inputs['Saturation'].default_value = 0.74
    hsv.inputs['Value'].default_value = 1.22
    links.new(even, hsv.inputs['Color'])
    # A band-to-band drift in tone, as boards from different bundles have.
    tint = _math(nodes, links, 'ADD', 0.96, _math(nodes, links, 'MULTIPLY', noise.outputs['Value'], 0.08))
    wood = nodes.new('ShaderNodeMix')
    wood.data_type = 'RGBA'
    wood.blend_type = 'MULTIPLY'
    wood.inputs['Factor'].default_value = 1.0
    sockets = [s for s in wood.inputs if s.type == 'RGBA']
    links.new(hsv.outputs['Color'], sockets[0])
    tint_rgb = nodes.new('ShaderNodeCombineColor')
    for channel in ('Red', 'Green', 'Blue'):
        links.new(tint, tint_rgb.inputs[channel])
    links.new(tint_rgb.outputs['Color'], sockets[1])
    wood_out = [s for s in wood.outputs if s.type == 'RGBA'][0]

    lines, key = _court_mask(nodes, links, x, y)
    # The key is stained, not painted: the grain still shows through.
    stained = _mix_colour(nodes, links, 1.0, wood_out, (0.09, 0.19, 0.58), 'MULTIPLY')
    keyed = _mix_colour(nodes, links, key, wood_out, stained)
    painted = _mix_colour(nodes, links, lines, keyed, (0.80, 0.80, 0.78))
    # Shoe rubber: sparse grey-black scuffs, a little denser where play is,
    # under the coat like real marks that the cleaner has not lifted.
    scuff_noise = nodes.new('ShaderNodeTexNoise')
    scuff_noise.inputs['Scale'].default_value = 3.2
    scuff_noise.inputs['Detail'].default_value = 12.0
    scuff_noise.inputs['Roughness'].default_value = 0.72
    stretch = nodes.new('ShaderNodeMapping')
    stretch.inputs['Scale'].default_value = (1.0, 2.6, 1.0)
    stretch.inputs['Rotation'].default_value = (0.0, 0.0, 0.5)
    links.new(geometry.outputs['Position'], stretch.inputs['Vector'])
    links.new(stretch.outputs['Vector'], scuff_noise.inputs['Vector'])
    scuff = nodes.new('ShaderNodeMapRange')
    scuff.inputs['From Min'].default_value = 0.70
    scuff.inputs['From Max'].default_value = 0.80
    scuff.inputs['To Max'].default_value = 0.35
    links.new(scuff_noise.outputs['Fac'], scuff.inputs['Value'])
    marked = _mix_colour(nodes, links, scuff.outputs['Result'], painted, (0.06, 0.055, 0.05))
    links.new(marked, bsdf.inputs['Base Color'])
    # Under the coat the wood is a satin surface; the coat carries the gloss.
    satin = nodes.new('ShaderNodeMapRange')
    satin.inputs['To Min'].default_value = 0.30
    satin.inputs['To Max'].default_value = 0.55
    links.new(rough.outputs['Color'], satin.inputs['Value'])
    links.new(satin.outputs['Result'], bsdf.inputs['Roughness'])
    nmap = nodes.new('ShaderNodeNormalMap')
    nmap.inputs['Strength'].default_value = 0.6
    links.new(normal_map.outputs['Color'], nmap.inputs['Color'])
    links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])
    bsdf.inputs['Coat Weight'].default_value = 1.0
    bsdf.inputs['Coat IOR'].default_value = 1.5
    # The coat is a flat film over the boards (it does not follow the joints),
    # worn duller in broad patches and in traffic lanes: the reflections of the
    # windows break up across it instead of lying on it like on a mirror.
    wear = nodes.new('ShaderNodeTexNoise')
    wear.inputs['Scale'].default_value = 0.35
    wear.inputs['Detail'].default_value = 6.0
    wear.inputs['Roughness'].default_value = 0.6
    links.new(geometry.outputs['Position'], wear.inputs['Vector'])
    dull = nodes.new('ShaderNodeMapRange')
    dull.inputs['From Min'].default_value = 0.35
    dull.inputs['From Max'].default_value = 0.70
    dull.inputs['To Min'].default_value = 0.08
    dull.inputs['To Max'].default_value = 0.24
    links.new(wear.outputs['Fac'], dull.inputs['Value'])
    links.new(dull.outputs['Result'], bsdf.inputs['Coat Roughness'])
    return mat


# ---------------------------------------------------------------- materials


def vinyl_material(name, colour):
    """Vinyl-covered foam: the scanned grain, a semi-gloss sheen, one colour."""
    mat, nodes, links, bsdf = _new_material(name)
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1 / VINYL_TILE_M,) * 3
    links.new(coord.outputs['Object'], mapping.inputs['Vector'])
    diffuse = _image(nodes, 'leather_white_diff_2k.jpg', True, mapping.outputs['Vector'], 'BOX')
    rough = _image(nodes, 'leather_white_rough_2k.jpg', False, mapping.outputs['Vector'], 'BOX')
    normal_map = _image(nodes, 'leather_white_nor_gl_2k.jpg', False, mapping.outputs['Vector'], 'BOX')
    shade = nodes.new('ShaderNodeRGBToBW')
    links.new(diffuse.outputs['Color'], shade.inputs['Color'])
    gain = _math(nodes, links, 'MULTIPLY', shade.outputs['Val'], 1.0 / VINYL_SCAN_LUMA)
    rgb = nodes.new('ShaderNodeCombineColor')
    for channel, value in zip(('Red', 'Green', 'Blue'), colour):
        links.new(_math(nodes, links, 'MULTIPLY', gain, value), rgb.inputs[channel])
    links.new(rgb.outputs['Color'], bsdf.inputs['Base Color'])
    sheen = nodes.new('ShaderNodeMapRange')
    sheen.inputs['To Min'].default_value = 0.36
    sheen.inputs['To Max'].default_value = 0.62
    links.new(rough.outputs['Color'], sheen.inputs['Value'])
    links.new(sheen.outputs['Result'], bsdf.inputs['Roughness'])
    nmap = nodes.new('ShaderNodeNormalMap')
    nmap.inputs['Strength'].default_value = 0.8
    links.new(normal_map.outputs['Color'], nmap.inputs['Color'])
    # Foam under vinyl is never flat: a slow, shallow undulation over the panel.
    pillow = nodes.new('ShaderNodeTexNoise')
    pillow.inputs['Scale'].default_value = 1.6
    pillow.inputs['Detail'].default_value = 2.0
    links.new(coord.outputs['Object'], pillow.inputs['Vector'])
    swell = nodes.new('ShaderNodeBump')
    swell.inputs['Strength'].default_value = 0.2
    swell.inputs['Distance'].default_value = 0.004
    links.new(pillow.outputs['Fac'], swell.inputs['Height'])
    links.new(nmap.outputs['Normal'], swell.inputs['Normal'])
    links.new(swell.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def block_paint_material(colour=(0.56, 0.555, 0.52)):
    """Painted concrete block: the scan's joints and blemishes under a light paint."""
    mat, nodes, links, bsdf = _new_material('Painted block wall')
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1 / BLOCK_TILE_M,) * 3
    links.new(coord.outputs['Object'], mapping.inputs['Vector'])
    diffuse = _image(nodes, 'concrete_wall_004_diff_2k.jpg', True, mapping.outputs['Vector'], 'BOX')
    rough = _image(nodes, 'concrete_wall_004_rough_2k.jpg', False, mapping.outputs['Vector'], 'BOX')
    normal_map = _image(nodes, 'concrete_wall_004_nor_gl_2k.jpg', False, mapping.outputs['Vector'], 'BOX')
    shade = nodes.new('ShaderNodeRGBToBW')
    links.new(diffuse.outputs['Color'], shade.inputs['Color'])
    # Keep the scan's tonal structure at half strength around the paint colour.
    gain = _math(nodes, links, 'ADD', 0.5, _math(nodes, links, 'MULTIPLY', shade.outputs['Val'], 0.5 / BLOCK_SCAN_LUMA))
    rgb = nodes.new('ShaderNodeCombineColor')
    for channel, value in zip(('Red', 'Green', 'Blue'), colour):
        links.new(_math(nodes, links, 'MULTIPLY', gain, value), rgb.inputs[channel])
    links.new(rgb.outputs['Color'], bsdf.inputs['Base Color'])
    sheen = nodes.new('ShaderNodeMapRange')
    sheen.inputs['To Min'].default_value = 0.62
    sheen.inputs['To Max'].default_value = 0.85
    links.new(rough.outputs['Color'], sheen.inputs['Value'])
    links.new(sheen.outputs['Result'], bsdf.inputs['Roughness'])
    nmap = nodes.new('ShaderNodeNormalMap')
    nmap.inputs['Strength'].default_value = 1.0
    links.new(normal_map.outputs['Color'], nmap.inputs['Color'])
    links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def plain_material(name, colour, roughness, metallic=0.0, bump=0.0, scale=160.0):
    mat, nodes, links, bsdf = _new_material(name)
    mat.diffuse_color = (*colour, 1.0)
    bsdf.inputs['Base Color'].default_value = (*colour, 1.0)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    if bump:
        coord = nodes.new('ShaderNodeTexCoord')
        noise = nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = scale
        noise.inputs['Detail'].default_value = 4.0
        links.new(coord.outputs['Object'], noise.inputs['Vector'])
        node = nodes.new('ShaderNodeBump')
        node.inputs['Strength'].default_value = 0.3
        node.inputs['Distance'].default_value = bump
        links.new(noise.outputs['Fac'], node.inputs['Height'])
        links.new(node.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def thin_glass():
    """Thin float glass: a Fresnel reflection over a see-through layer.

    Shaded as transparent so rays through it stay camera rays (the world shows
    the sky photograph to the camera alone) and sunlight is not stopped. Cycles'
    Fresnel node inverts the IOR on back faces, which would turn a pane seen at
    a grazing angle totally reflective and black; the inverse IOR is fed there.
    """
    existing = bpy.data.materials.get('Thin float glass')
    if existing is not None:
        return existing
    mat = bpy.data.materials.new('Thin float glass')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    for node in [n for n in nodes if n.type != 'OUTPUT_MATERIAL']:
        nodes.remove(node)
    clear = nodes.new('ShaderNodeBsdfTransparent')
    reflection = nodes.new('ShaderNodeBsdfGlossy')
    reflection.inputs['Roughness'].default_value = 0.0
    fresnel = nodes.new('ShaderNodeFresnel')
    geometry = nodes.new('ShaderNodeNewGeometry')
    ior = nodes.new('ShaderNodeMath')
    ior.operation = 'MULTIPLY_ADD'
    ior.inputs[1].default_value = 1.0 / 1.52 - 1.52
    ior.inputs[2].default_value = 1.52
    links.new(geometry.outputs['Backfacing'], ior.inputs[0])
    links.new(ior.outputs['Value'], fresnel.inputs['IOR'])
    pane = nodes.new('ShaderNodeMixShader')
    links.new(fresnel.outputs['Fac'], pane.inputs['Fac'])
    links.new(clear.outputs['BSDF'], pane.inputs[1])
    links.new(reflection.outputs['BSDF'], pane.inputs[2])
    links.new(pane.outputs['Shader'], nodes['Material Output'].inputs['Surface'])
    return mat


# -------------------------------------------------------------------- shell


def _pads_along(name, axis, fixed, inward, start, stop, mat, skip=()):
    """Crash pads in a row along one wall, filling the run edge to edge."""
    length = stop - start
    count = max(1, round(length / PAD_WIDTH))
    width = length / count
    made = []
    for i in range(count):
        a = start + i * width + 0.003
        b = a + width - 0.006
        if any(a < s1 and b > s0 for s0, s1 in skip):
            continue
        face = fixed + inward * PAD_THICK
        lo_n, hi_n = sorted((fixed, face))
        if axis == 'x':
            lo, hi = (a, lo_n, FZ + PAD_BOTTOM), (b, hi_n, FZ + PAD_TOP)
        else:
            lo, hi = (lo_n, a, FZ + PAD_BOTTOM), (hi_n, b, FZ + PAD_TOP)
        made.append(box(f'{name} pad {i + 1}', lo, hi, mat, bevel=0.014, segments=3))
    return made


def _window_frame(name, wall_x, inward, y0, y1, z0, z1, frame_mat):
    """Aluminium window in the middle of a reveal through the wall at wall_x."""
    mid = wall_x - inward * WALL_THICK / 2
    t = 0.06            # frame depth
    bar = 0.065
    x0, x1 = sorted((mid - t / 2, mid + t / 2))
    parts = [
        box(f'{name} head', (x0, y0, z1 - bar), (x1, y1, z1), frame_mat, 0.002),
        box(f'{name} sill rail', (x0, y0, z0), (x1, y1, z0 + bar), frame_mat, 0.002),
        box(f'{name} jamb a', (x0, y0, z0 + bar), (x1, y0 + bar, z1 - bar), frame_mat, 0.002),
        box(f'{name} jamb b', (x0, y1 - bar, z0 + bar), (x1, y1, z1 - bar), frame_mat, 0.002),
        box(f'{name} mullion', (x0, (y0 + y1) / 2 - 0.03, z0 + bar), (x1, (y0 + y1) / 2 + 0.03, z1 - bar),
            frame_mat, 0.002),
    ]
    transom = z0 + (z1 - z0) * 0.68
    parts.append(box(f'{name} transom', (x0, y0 + bar, transom - 0.03), (x1, y1 - bar, transom + 0.03),
                     frame_mat, 0.002))
    pane = box(f'{name} glass', (mid - 0.003, y0 + 0.02, z0 + 0.02), (mid + 0.003, y1 - 0.02, z1 - 0.02),
               thin_glass())
    pane.visible_shadow = False
    # A sill board on the room half of the reveal, nosed 3 cm past the wall.
    sx0, sx1 = sorted((wall_x + inward * 0.03, mid + inward * t / 2))
    parts.append(box(f'{name} inner sill', (sx0, y0, z0), (sx1, y1, z0 + 0.018), frame_mat, 0.002))
    return parts + [pane]


def _portal(name, centre, size, inward):
    data = bpy.data.lights.new(name, 'AREA')
    data.shape = 'RECTANGLE'
    data.size, data.size_y = size
    data.cycles.is_portal = True
    obj = _link(bpy.data.objects.new(name, data))
    obj.location = centre
    obj.rotation_euler = Vector(inward).to_track_quat('-Z', 'Y').to_euler()
    return obj


def _long_wall(name, wall_x, inward, block, frame_mat):
    """A long wall at constant x with the window row cut through it."""
    outer = wall_x - inward * WALL_THICK
    x0, x1 = sorted((wall_x, outer))
    y_lo, y_hi = HALL_Y[0] - WALL_THICK, HALL_Y[1] + WALL_THICK
    top = FZ + HALL_HEIGHT + 0.2
    pieces = [box(f'{name} below windows', (x0, y_lo, FZ - 0.1), (x1, y_hi, FZ + WINDOW_SILL), block),
              box(f'{name} above windows', (x0, y_lo, FZ + WINDOW_HEAD), (x1, y_hi, top), block)]
    openings = sorted((c - WINDOW_WIDTH / 2, c + WINDOW_WIDTH / 2) for c in WINDOW_Y)
    edge = y_lo
    for k, (a, b) in enumerate(openings):
        pieces.append(box(f'{name} pier {k}', (x0, edge, FZ + WINDOW_SILL), (x1, a, FZ + WINDOW_HEAD), block))
        edge = b
    pieces.append(box(f'{name} pier end', (x0, edge, FZ + WINDOW_SILL), (x1, y_hi, FZ + WINDOW_HEAD), block))
    windows = []
    for k, (a, b) in enumerate(openings):
        pieces += _window_frame(f'{name} window {k}', wall_x, inward, a, b, FZ + WINDOW_SILL,
                                FZ + WINDOW_HEAD, frame_mat)
        _portal(f'{name} window {k} sky portal',
                (outer - inward * 0.01, (a + b) / 2, FZ + (WINDOW_SILL + WINDOW_HEAD) / 2),
                (b - a, WINDOW_HEAD - WINDOW_SILL), (inward, 0.0, 0.0))
        windows.append([a, b])
    return pieces, windows


def _doors(steel, frame_mat, kick, bar_mat):
    """A pair of hollow-metal doors set in the end wall, with push bars."""
    y = HALL_Y[1]
    x0, x1 = DOOR_X
    top = FZ + DOOR_HEIGHT
    f = 0.05
    parts = [box('Door frame head', (x0 - f, y - 0.012, top), (x1 + f, y + 0.20, top + f), frame_mat, 0.002),
             box('Door frame jamb left', (x0 - f, y - 0.012, FZ), (x0, y + 0.20, top), frame_mat, 0.002),
             box('Door frame jamb right', (x1, y - 0.012, FZ), (x1 + f, y + 0.20, top), frame_mat, 0.002)]
    mid = (x0 + x1) / 2
    ly0, ly1 = y + 0.03, y + 0.075
    lite_z = (FZ + 1.22, FZ + 1.86)
    for side, (a, b) in (('left', (x0 + 0.003, mid - 0.002)), ('right', (mid + 0.002, x1 - 0.003))):
        # The leaf is built round a narrow vision lite near its meeting edge.
        la, lb = ((b - 0.30, b - 0.12) if side == 'left' else (a + 0.12, a + 0.30))
        z0, z1 = FZ + 0.012, top - 0.003
        parts += [box(f'Door leaf {side} below lite', (a, ly0, z0), (b, ly1, lite_z[0]), steel, 0.003),
                  box(f'Door leaf {side} above lite', (a, ly0, lite_z[1]), (b, ly1, z1), steel, 0.003),
                  box(f'Door leaf {side} beside lite a', (a, ly0, lite_z[0]), (la, ly1, lite_z[1]), steel),
                  box(f'Door leaf {side} beside lite b', (lb, ly0, lite_z[0]), (b, ly1, lite_z[1]), steel)]
        bead = 0.014
        parts += [box(f'Door lite bead {side} {k}', lo, hi, kick, 0.001) for k, (lo, hi) in enumerate((
            ((la - bead, ly0 - 0.006, lite_z[0] - bead), (lb + bead, ly0, lite_z[0])),
            ((la - bead, ly0 - 0.006, lite_z[1]), (lb + bead, ly0, lite_z[1] + bead)),
            ((la - bead, ly0 - 0.006, lite_z[0]), (la, ly0, lite_z[1])),
            ((lb, ly0 - 0.006, lite_z[0]), (lb + bead, ly0, lite_z[1]))))]
        lite = box(f'Door lite glass {side}', (la, (ly0 + ly1) / 2 - 0.003, lite_z[0]),
                   (lb, (ly0 + ly1) / 2 + 0.003, lite_z[1]), thin_glass())
        lite.visible_shadow = False
        parts.append(lite)
        parts.append(box(f'Door kick plate {side}', (a + 0.01, y + 0.027, FZ + 0.03), (b - 0.01, y + 0.03, FZ + 0.28),
                         kick, 0.001))
        # Push bar: a stainless rail on two end housings, 0.95 m up.
        hz = FZ + 0.95
        parts.append(box(f'Door push bar {side}', (a + 0.08, y - 0.040, hz - 0.018), (b - 0.08, y - 0.012, hz + 0.018),
                         bar_mat, 0.006))
        for end in (a + 0.06, b - 0.10):
            parts.append(box(f'Door push bar housing {side}', (end, y - 0.045, hz - 0.045), (end + 0.04, y + 0.03, hz + 0.045),
                             bar_mat, 0.004))
    # A dim lobby behind the doors: what the vision lites show, and what closes
    # the opening for the light.
    parts.append(box('Lobby behind doors', (x0 - 0.5, y + 0.30, FZ - 0.1), (x1 + 0.5, y + 2.5, top + 0.5),
                     plain_material('Lobby', (0.2, 0.2, 0.2), 0.8)))
    # Return-air grille over the doors: an aluminium frame and louvre blades in
    # front of a dark duct.
    gx0, gx1, gz0, gz1 = x0 + 0.25, x1 - 0.25, top + 0.24, top + 0.66
    parts.append(box('Return grille duct', (gx0, y - 0.004, gz0), (gx1, y, gz1),
                     plain_material('Duct interior', (0.012, 0.012, 0.013), 0.7)))
    rim = 0.035
    parts += [box('Return grille frame top', (gx0 - rim, y - 0.02, gz1), (gx1 + rim, y + 0.002, gz1 + rim), frame_mat, 0.003),
              box('Return grille frame bottom', (gx0 - rim, y - 0.02, gz0 - rim), (gx1 + rim, y + 0.002, gz0), frame_mat, 0.003),
              box('Return grille frame left', (gx0 - rim, y - 0.02, gz0), (gx0, y + 0.002, gz1), frame_mat, 0.003),
              box('Return grille frame right', (gx1, y - 0.02, gz0), (gx1 + rim, y + 0.002, gz1), frame_mat, 0.003)]
    blades = 12
    for k in range(blades):
        zc = gz0 + (k + 0.5) * (gz1 - gz0) / blades
        blade = box(f'Return grille blade {k}', (gx0, -0.012, -0.0015), (gx1, 0.012, 0.0015), frame_mat)
        blade.data.transform(Matrix.Translation((0.0, y - 0.008, zc)) @ Matrix.Rotation(math.radians(-38), 4, 'X'))
        parts.append(blade)
    # Fire alarm bell left of the doors: a red dome on a back box.
    red = plain_material('Alarm bell red enamel', (0.45, 0.02, 0.015), 0.25)
    parts.append(box('Alarm bell back box', (x0 - 0.42, y - 0.03, FZ + 2.16), (x0 - 0.30, y, FZ + 2.28), red, 0.006))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.075, segments=48, ring_count=24,
                                         location=(x0 - 0.36, y - 0.03, FZ + 2.22))
    bell = bpy.context.object
    bell.name = 'Alarm bell dome'
    bell.scale = (1.0, 0.45, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bm = bmesh.new()
    bm.from_mesh(bell.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y > 0.0005], context='VERTS')
    bm.to_mesh(bell.data)
    bm.free()
    for poly in bell.data.polygons:
        poly.use_smooth = True
    bell.data.materials.append(red)
    parts.append(bell)
    return parts


def build_shell():
    """Floor, walls, crash pads, windows, doors and ceiling. Returns a summary."""
    block = block_paint_material()
    pads = vinyl_material('Navy vinyl crash pad', (0.012, 0.030, 0.105))
    cove = plain_material('Rubber cove base', (0.025, 0.025, 0.027), 0.55, bump=0.0004, scale=300)
    frame_mat = plain_material('Anodised aluminium', (0.50, 0.51, 0.52), 0.35, metallic=0.9)
    steel = plain_material('Door enamel', (0.16, 0.19, 0.24), 0.30, bump=0.0004, scale=220)
    kick = plain_material('Brushed stainless', (0.55, 0.55, 0.56), 0.28, metallic=1.0, bump=0.0002, scale=900)
    ceiling = plain_material('Roof deck paint', (0.55, 0.56, 0.57), 0.8)

    made = []
    x0, x1 = HALL_X
    y0, y1 = HALL_Y
    top = FZ + HALL_HEIGHT
    made.append(box('Hall floor', (x0 - WALL_THICK, y0 - WALL_THICK, FZ - 0.1),
                    (x1 + WALL_THICK, y1 + WALL_THICK, FZ), floor_material()))
    made.append(box('Roof deck', (x0 - WALL_THICK, y0 - WALL_THICK, top), (x1 + WALL_THICK, y1 + WALL_THICK, top + 0.2),
                    ceiling))
    # End wall, with the door opening left in it.
    dx0, dx1 = DOOR_X
    made += [box('End wall left', (x0 - WALL_THICK, y1, FZ - 0.1), (dx0, y1 + WALL_THICK, top + 0.2), block),
             box('End wall right', (dx1, y1, FZ - 0.1), (x1 + WALL_THICK, y1 + WALL_THICK, top + 0.2), block),
             box('End wall over doors', (dx0, y1, FZ + DOOR_HEIGHT), (dx1, y1 + WALL_THICK, top + 0.2), block)]
    made.append(box('Back wall', (x0 - WALL_THICK, y0 - WALL_THICK, FZ - 0.1), (x1 + WALL_THICK, y0, top + 0.2), block))
    left, left_windows = _long_wall('Left wall', x0, 1.0, block, frame_mat)
    right, right_windows = _long_wall('Right wall', x1, -1.0, block, frame_mat)
    made += left + right
    made += _doors(steel, frame_mat, kick, kick)

    # Rubber cove base along every wall, then the pads above it.
    c = 0.004
    made += [box('Cove base end left', (x0, y1 - c, FZ), (dx0 - 0.05, y1, FZ + COVE_HEIGHT), cove),
             box('Cove base end right', (dx1 + 0.05, y1 - c, FZ), (x1, y1, FZ + COVE_HEIGHT), cove),
             box('Cove base back', (x0, y0, FZ), (x1, y0 + c, FZ + COVE_HEIGHT), cove),
             box('Cove base left', (x0, y0, FZ), (x0 + c, y1, FZ + COVE_HEIGHT), cove),
             box('Cove base right', (x1 - c, y0, FZ), (x1, y1, FZ + COVE_HEIGHT), cove)]
    # The side-wall pads run into the corners; the end pads butt against them.
    made += _pads_along('End wall', 'x', y1, -1.0, x0 + PAD_THICK, x1 - PAD_THICK, pads,
                        skip=[(dx0 - 0.06, dx1 + 0.06)])
    made += _pads_along('Back wall', 'x', y0, 1.0, x0 + PAD_THICK, x1 - PAD_THICK, pads)
    made += _pads_along('Left wall', 'y', x0, 1.0, y0, y1, pads)
    made += _pads_along('Right wall', 'y', x1, -1.0, y0, y1, pads)

    # Ground outside: stops sky light from below the windows; the camera looks
    # through it at the sky photograph.
    ground = box('Ground outside', (-200, -200, FZ - 1.2), (200, 200, FZ - 1.0),
                 plain_material('Ground outside', (0.16, 0.15, 0.13), 0.9))
    ground.visible_camera = False
    return made, {'left_windows': left_windows, 'right_windows': right_windows}


# ------------------------------------------------------------------- lights


def _import_gltf(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    return [o for o in bpy.data.objects if o not in before]


def pendant_lamps(power):
    """High-bay pendants on a grid under the roof, each lit at its diffuser.

    The scanned lamp hangs from its own origin (top of the cable) and is 1.355 m
    tall; its glass bowl is the bottom 0.1 m. A disc light the size of the bowl
    sits just under it, aimed at the floor, so the light comes out of the
    fixture and nowhere else.
    """
    imported = _import_gltf(TEXTURES / 'hanging_industrial_lamp' / 'hanging_industrial_lamp_1k.gltf')
    lamp = next(o for o in imported if o.type == 'MESH')
    for slot in lamp.material_slots:
        mat = slot.material
        if mat is None:
            continue
        if 'glass' in mat.name.lower():
            slot.material = thin_glass()
            continue
        bsdf = mat.node_tree.nodes.get('Principled BSDF')
        if bsdf is not None:
            bsdf.inputs['Emission Strength'].default_value = 6.0
    top = FZ + HALL_HEIGHT
    lamps = []
    for i, x in enumerate(LAMP_X):
        for j, y in enumerate(LAMP_Y):
            obj = lamp if not lamps else lamp.copy()
            if obj is not lamp:
                _link(obj)
            obj.name = f'High-bay pendant {i}{j}'
            obj.location = (x, y, top)
            lamps.append(obj)
            data = bpy.data.lights.new(f'High-bay diffuser {i}{j}', 'AREA')
            data.shape = 'DISK'
            data.size = 0.42
            data.energy = power
            data.color = (1.0, 0.93, 0.84)
            light = _link(bpy.data.objects.new(data.name, data))
            light.location = (x, y, top - 1.36)
    return lamps


def daylight(spec, target):
    """Sun lamp and Nishita sky outside the windows; the photograph for the camera."""
    el = math.radians(float(spec['sun_elevation_deg']))
    heading = math.radians(float(spec['sun_heading_deg']))
    travel = Vector((math.cos(el) * math.cos(heading), math.cos(el) * math.sin(heading), -math.sin(el)))
    data = bpy.data.lights.new('Afternoon sun', 'SUN')
    data.energy, data.angle, data.color = float(spec['sun_strength']), math.radians(0.53), (1.0, 0.955, 0.90)
    sun = _link(bpy.data.objects.new('Afternoon sun', data))
    sun.location = Vector(target) - 10 * travel
    sun.rotation_euler = travel.to_track_quat('-Z', 'Y').to_euler()

    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new('Afternoon sky')
    scene.world.use_nodes = True
    nodes, links = scene.world.node_tree.nodes, scene.world.node_tree.links
    sky = nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'NISHITA'
    sky.sun_disc = False
    sky.sun_elevation = el
    # Nishita puts the sun at (sin r, cos r) in the ground plane: r = 0 is +y.
    sky.sun_rotation = math.atan2(-travel.x, -travel.y)
    sky.air_density, sky.dust_density = 1.0, 2.0
    lighting = nodes['Background']
    links.new(sky.outputs['Color'], lighting.inputs['Color'])
    lighting.inputs['Strength'].default_value = float(spec['sky_strength'])

    coord = nodes.new('ShaderNodeTexCoord')
    turn = nodes.new('ShaderNodeMapping')
    turn.vector_type = 'VECTOR'
    towards_sun = -travel
    # Rotating the lookup by theta moves the photograph by -theta: the lamp's
    # direction is sent to the photograph's own sun.
    turn.inputs['Rotation'].default_value = (
        0.0, 0.0, math.radians(WINDOW_VIEW_SUN_AZIMUTH_DEG) - math.atan2(towards_sun.y, towards_sun.x))
    photo = nodes.new('ShaderNodeTexEnvironment')
    photo.image = bpy.data.images.load(str(TEXTURES / WINDOW_VIEW), check_existing=True)
    links.new(coord.outputs['Generated'], turn.inputs['Vector'])
    links.new(turn.outputs['Vector'], photo.inputs['Vector'])
    view = nodes.new('ShaderNodeBackground')
    view.inputs['Strength'].default_value = float(spec['window_view_strength'])
    links.new(photo.outputs['Color'], view.inputs['Color'])
    path = nodes.new('ShaderNodeLightPath')
    mix = nodes.new('ShaderNodeMixShader')
    links.new(path.outputs['Is Camera Ray'], mix.inputs['Fac'])
    links.new(lighting.outputs['Background'], mix.inputs[1])
    links.new(view.outputs['Background'], mix.inputs[2])
    links.new(mix.outputs['Shader'], nodes['World Output'].inputs['Surface'])
    return sun


# -------------------------------------------------------------------- props


def place_model(path, name, yaw_deg=0.0, **anchor):
    """Import a glTF, turn it about z and set its bounding box on an anchor.

    Anchor keys: ``x``/``y`` (box centre), ``x_min``/``x_max``/``y_min``/``y_max``
    (box faces) and ``z`` (box bottom).
    """
    imported = _import_gltf(path)
    for obj in imported:
        obj.animation_data_clear()
    root = _link(bpy.data.objects.new(name, None))
    for obj in imported:
        if obj.parent is None:
            world = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = world
    root.rotation_euler.z = math.radians(yaw_deg)
    bpy.context.view_layer.update()
    meshes = [o for o in imported if o.type == 'MESH']
    points = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    shift = Vector((0.0, 0.0, 0.0))
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
    return meshes


def props():
    """A blue equipment crate against the end-wall pads, left of the goal."""
    face = HALL_Y[1] - PAD_THICK
    crate = place_model(TEXTURES / 'industrial_pastic_container' / 'industrial_pastic_container_1k.gltf',
                        'Equipment crate', yaw_deg=90.0, x=-2.55, y_max=face - 0.02, z=FZ)
    return crate


# ----------------------------------------------------------------- checks


def _bvh(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    matrix = obj.matrix_world
    verts = [matrix @ v.co for v in mesh.vertices]
    polys = [tuple(p.vertices) for p in mesh.polygons]
    evaluated.to_mesh_clear()
    if not polys:
        return None
    lo = Vector([min(v[i] for v in verts) for i in range(3)])
    hi = Vector([max(v[i] for v in verts) for i in range(3)])
    return BVHTree.FromPolygons(verts, polys), lo, hi


def check_clearance(props_objects, path, radius, margin=0.02, substeps=8):
    """Smallest gap between the ball and each prop over the whole take.

    ``path`` is the ball centre per frame; the motion between frames is sampled
    ``substeps`` times so a fast ball cannot skip through a thin part. Raises if
    any prop comes within ``margin`` of the ball's surface.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    samples = []
    for a, b in zip(path, path[1:]):
        for k in range(substeps):
            samples.append(Vector(a).lerp(Vector(b), k / substeps))
    samples.append(Vector(path[-1]))
    reach = radius + margin
    worst = {}
    for obj in props_objects:
        built = _bvh(obj, depsgraph)
        if built is None:
            continue
        tree, lo, hi = built
        gap = None
        for c in samples:
            outside = math.sqrt(sum(max(lo[i] - c[i], 0.0, c[i] - hi[i]) ** 2 for i in range(3)))
            if outside > 1.0:
                continue
            hit = tree.find_nearest(c, 2.0)
            if hit[0] is None:
                continue
            d = hit[3] - radius
            gap = d if gap is None else min(gap, d)
        if gap is not None:
            worst[obj.name] = round(gap, 4)
            if gap < margin:
                raise ValueError(f'the ball passes within {gap:.3f} m of {obj.name}; move it')
    closest = sorted(worst.items(), key=lambda kv: kv[1])[:6]
    print('[hall] closest props to the ball: ' + ', '.join(f'{k} {v:.3f} m' for k, v in closest))
    return dict(closest)
