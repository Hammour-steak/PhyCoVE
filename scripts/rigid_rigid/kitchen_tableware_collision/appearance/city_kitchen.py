"""A city apartment kitchen at night, built to measure around the simulator's worktop.

The room is built from ordinary parts at their real sizes:

* the island top is one 30 mm honed granite slab whose top face *is* the
  simulator's table box (WORKTOP_X/Y, COUNTER_Z), so everything the bowls touch
  on screen is the collider;
* handleless smoked-oak joinery (a recessed pull rail under the top, 3 mm gaps
  between fronts) under the island and along the back wall, walnut open
  shelves, micro-cement plaster walls, all from Poly Haven CC0 scans at their
  measured size;
* a real window cut through the back wall, black aluminium frame and thin
  glass, looking out on a city at night over a gathered linen cafe curtain;
* it is evening: the only light comes from the room's own fittings -- two
  pendant lamps over the island (placed in kitchen_props.py), recessed ceiling
  downlights in modelled cans and LED strips under the shelves. Nothing lights
  the room that is not a lamp in it.

Nothing in here takes part in the simulation.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from scene_geometry import COUNTER_Z
from pcve_assets import asset as _pcve_asset

TEXTURES = _pcve_asset('polyhaven/kitchen_tableware_collision')

# The simulator's worktop is one fixed box (simulate_kitchen_tableware_collision.py:
# halfExtents 1.52 x 0.49 x 0.025 m, top face at COUNTER_Z). The granite slab is
# that box's footprint and top face exactly.
WORKTOP_X = (-1.52, 1.52)
WORKTOP_Y = (-.49, .49)
SLAB_M = .03

# Room: plaster faces of the four walls and the ceiling height.
ROOM_X = (-3.0, 3.2)
ROOM_Y = (-2.6, 2.45)
CEILING_M = 2.65
WALL_THICK_M = .2

# Back run of base cabinets along the y = ROOM_Y[1] wall.
BACK_TOP_Z = .92
BACK_FRONT_Y = 1.83
# Window in the back wall, (x span, z span), and the open shelves to its left.
WINDOW = dict(x=(-1.0, .95), z=(1.02, 2.35), curtain_top=1.55)
SHELF_X = (-2.98, -1.24)
SHELF_TOPS = (1.42, 1.80)
SHELF_DEPTH = .27
# Tall larder/fridge column to the right of the window.
TALL_X = (1.20, ROOM_X[1])
TALL_TOP = 2.30

# Real sizes of the Poly Haven scans (api.polyhaven.com/info "dimensions").
GRANITE_SCAN_M = 1.802     # granite_tile_03: 2 x 2 tiles of 0.9 m with grout joints
GRANITE_TILE_M = GRANITE_SCAN_M / 2
PLASTER_M = 1.5            # plaster_grey_04
OAK_M = 1.0                # flamed_black_veneer
WALNUT_M = 1.0             # black_walnut_veneer_02
LINEN_M = .271             # rough_linen

# Colour temperatures of the fittings (linear RGB, roughly 2700 K and 3000 K).
WARM_2700K = (1.0, .66, .38)
WARM_3000K = (1.0, .72, .47)


# ------------------------------------------------------------------ geometry


def _world_uv(mesh):
    """UVs in world metres, projected along each face's dominant axis.

    Every room part is built at the origin, so these are true sizes on every
    face and the tangent-space normal maps of the scans line up with them.
    """
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(mesh)
    layer = bm.loops.layers.uv.new('world_m')
    for face in bm.faces:
        n = face.normal
        axis = max(range(3), key=lambda i: abs(n[i]))
        for loop in face.loops:
            co = loop.vert.co
            if axis == 2:
                uv = (co.x, co.y)
            elif axis == 1:
                uv = (co.x, co.z)
            else:
                uv = (co.y, co.z)
            loop[layer].uv = uv
    bm.to_mesh(mesh)
    bm.free()


def box(name, lo, hi, mat=None, bevel=0., segments=2):
    """An axis-aligned box built in world coordinates (object at the origin)."""
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
    _world_uv(mesh)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if mat is not None:
        mesh.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new('Eased edges', 'BEVEL')
        mod.width, mod.segments, mod.limit_method = bevel, segments, 'ANGLE'
        obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return obj


def cylinder(name, centre, radius, depth, mat, vertices=32):
    """A vertical cylinder (axis z) with softened edges."""
    import bpy
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=centre)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    mod = obj.modifiers.new('Eased edges', 'BEVEL')
    mod.width, mod.segments, mod.limit_method = min(radius, depth) * .15, 2, 'ANGLE'
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


def _image(nodes, links, stem, kind, vector, colour):
    import bpy
    node = nodes.new('ShaderNodeTexImage')
    node.image = bpy.data.images.load(str(TEXTURES / f'{stem}_{kind}_2k.jpg'), check_existing=True)
    if not colour:
        node.image.colorspace_settings.name = 'Non-Color'
    node.interpolation = 'Cubic'
    links.new(vector, node.inputs['Vector'])
    return node.outputs['Color']


def _wire_scan(mat, stem, vector, tint=None, rough_range=None, normal_strength=1.):
    """Wire one Poly Haven 2k set (diff / rough / nor_gl) into the BSDF."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    colour = _image(nodes, links, stem, 'diff', vector, True)
    if tint is not None:
        # A vector multiply, not a colour mix: colour sockets clamp at 1.
        mix = nodes.new('ShaderNodeVectorMath')
        mix.operation = 'MULTIPLY'
        links.new(colour, mix.inputs[0])
        mix.inputs[1].default_value = tint
        colour = mix.outputs['Vector']
    links.new(colour, bsdf.inputs['Base Color'])
    rough = _image(nodes, links, stem, 'rough', vector, False)
    if rough_range is not None:
        remap = nodes.new('ShaderNodeMapRange')
        remap.inputs['To Min'].default_value, remap.inputs['To Max'].default_value = rough_range
        links.new(rough, remap.inputs['Value'])
        rough = remap.outputs['Result']
    links.new(rough, bsdf.inputs['Roughness'])
    if normal_strength:
        normal = nodes.new('ShaderNodeNormalMap')
        normal.uv_map = 'world_m'
        normal.inputs['Strength'].default_value = normal_strength
        links.new(_image(nodes, links, stem, 'nor_gl', vector, False), normal.inputs['Color'])
        links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])


def _math(nodes, links, op, a, b=None):
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


def scanned(name, stem, tile_m, base=(.5, .5, .5), swap=False, per_object=False, **options):
    """A scan laid on the world-metre UVs at its real size.

    ``swap`` turns the scan a quarter turn (for vertical grain on doors);
    ``per_object`` gives every object its own random offset into the scan, so
    neighbouring fronts or shelves are cut from different parts of the veneer.
    """
    mat = principled(name, base, .5)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    uv = nodes.new('ShaderNodeUVMap')
    uv.uv_map = 'world_m'
    xyz = nodes.new('ShaderNodeSeparateXYZ')
    links.new(uv.outputs['UV'], xyz.inputs['Vector'])
    u, v = (xyz.outputs['Y'], xyz.outputs['X']) if swap else (xyz.outputs['X'], xyz.outputs['Y'])
    u = _math(nodes, links, 'DIVIDE', u, tile_m)
    v = _math(nodes, links, 'DIVIDE', v, tile_m)
    if per_object:
        info = nodes.new('ShaderNodeObjectInfo')
        u = _math(nodes, links, 'ADD', u, _math(nodes, links, 'MULTIPLY', info.outputs['Random'], 37.3))
        v = _math(nodes, links, 'ADD', v, _math(nodes, links, 'MULTIPLY', info.outputs['Random'], 91.7))
    combine = nodes.new('ShaderNodeCombineXYZ')
    links.new(u, combine.inputs['X'])
    links.new(v, combine.inputs['Y'])
    _wire_scan(mat, stem, combine.outputs['Vector'], **options)
    return mat


def honed_granite(name):
    """Honed salt-and-pepper granite cut as one seamless slab.

    The scan is a 2 x 2 grid of 0.9 m floor tiles with grout joints. A worktop
    has no joints, so the slab is sampled in Voronoi patches of about 0.2 m,
    each taken from a random spot well inside one of the four tiles: the
    grout never shows, and granite's random grain hides where patches meet.
    The polish is a satin hone: soft reflections, no mirror.
    """
    mat = principled(name, (.30, .29, .27), .3)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    uv = nodes.new('ShaderNodeUVMap')
    uv.uv_map = 'world_m'
    cell = .2
    scaled = nodes.new('ShaderNodeVectorMath')
    scaled.operation = 'SCALE'
    links.new(uv.outputs['UV'], scaled.inputs[0])
    scaled.inputs['Scale'].default_value = 1 / cell
    vor = nodes.new('ShaderNodeTexVoronoi')
    vor.voronoi_dimensions = '2D'
    vor.inputs['Randomness'].default_value = 1.
    links.new(scaled.outputs['Vector'], vor.inputs['Vector'])
    # Offset from the patch's own feature point, in metres.
    centre = nodes.new('ShaderNodeVectorMath')
    centre.operation = 'SCALE'
    links.new(vor.outputs['Position'], centre.inputs[0])
    centre.inputs['Scale'].default_value = cell
    local = nodes.new('ShaderNodeVectorMath')
    local.operation = 'SUBTRACT'
    links.new(uv.outputs['UV'], local.inputs[0])
    links.new(centre.outputs['Vector'], local.inputs[1])
    rand = nodes.new('ShaderNodeSeparateColor')
    links.new(vor.outputs['Color'], rand.inputs['Color'])
    xyz = nodes.new('ShaderNodeSeparateXYZ')
    links.new(local.outputs['Vector'], xyz.inputs['Vector'])
    out = []
    for coord, pick, jitter in ((xyz.outputs['X'], rand.outputs['Red'], rand.outputs['Green']),
                                (xyz.outputs['Y'], rand.outputs['Blue'], rand.outputs['Red'])):
        # Tile centre 0.45 m or 1.35 m into the scan, +-0.1 m jitter.
        tile = _math(nodes, links, 'FLOOR', _math(nodes, links, 'MULTIPLY', pick, 2.))
        start = _math(nodes, links, 'ADD', _math(nodes, links, 'MULTIPLY', tile, GRANITE_TILE_M), GRANITE_TILE_M / 2)
        start = _math(nodes, links, 'ADD', start, _math(nodes, links, 'MULTIPLY', _math(nodes, links, 'SUBTRACT', jitter, .5), .2))
        out.append(_math(nodes, links, 'DIVIDE', _math(nodes, links, 'ADD', start, coord), GRANITE_SCAN_M))
    combine = nodes.new('ShaderNodeCombineXYZ')
    links.new(out[0], combine.inputs['X'])
    links.new(out[1], combine.inputs['Y'])
    _wire_scan(mat, 'granite_tile_03', combine.outputs['Vector'], tint=(.86, .86, .88),
               rough_range=(.22, .34), normal_strength=.12)
    bsdf = nodes['Principled BSDF']
    # The scan is a pink-brown granite; this slab is the common grey
    # salt-and-pepper kind, so most of the feldspar's colour is taken out.
    grey = nodes.new('ShaderNodeHueSaturation')
    grey.inputs['Saturation'].default_value = .3
    links.new(bsdf.inputs['Base Color'].links[0].from_socket, grey.inputs['Color'])
    links.new(grey.outputs['Color'], bsdf.inputs['Base Color'])
    if bsdf.inputs.get('Coat Weight'):
        # Penetrating sealer: a faint clear sheen over the honed stone.
        bsdf.inputs['Coat Weight'].default_value = .25
        bsdf.inputs['Coat Roughness'].default_value = .18
    return mat


def thin_glass():
    """Float glass shaded thin: Fresnel reflection over a transparent layer.

    Rays through it stay camera rays (the world shows the city photograph to
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


def led_diffuser(name, color, strength):
    """Opal diffuser of an LED strip: what the camera sees of a lit strip."""
    mat = principled(name, (.9, .9, .9), .4)
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Emission Color'].default_value = (*color, 1)
    bsdf.inputs['Emission Strength'].default_value = strength
    return mat


# ------------------------------------------------------------------ joinery


PULL_RAIL_M = .055


def carcass(prefix, x0, x1, face_y, back_y, z_low, z_top, mat):
    """Cabinet carcass whose top 59 mm is set 34 mm back for the pull rail."""
    box(f'{prefix} carcass', (x0, face_y, z_low), (x1, back_y, z_top - PULL_RAIL_M - .004), mat)
    box(f'{prefix} carcass behind pull rail', (x0, face_y + .034, z_top - PULL_RAIL_M - .004), (x1, back_y, z_top), mat)


def handleless_run(prefix, x0, x1, face_y, facing, z_low, z_top, oak, rail, bay=.6, rows=(.24,)):
    """Slab fronts with 3 mm gaps under a recessed pull rail.

    The carcass face is at ``face_y``; fronts stand 19 mm proud of it towards
    ``facing`` (-1 in y here). Below the worktop a 55 mm aluminium channel is
    recessed into the carcass -- the finger pull of a handleless kitchen --
    then rows of drawer fronts of the given heights, the last row taking what
    is left down to ``z_low``.
    """
    s = facing
    front = (face_y, face_y + s * .019)
    fy0, fy1 = min(front), max(front)
    channel_top = z_top
    channel_bottom = z_top - PULL_RAIL_M
    # The channel: a dark anodised C-profile, its back 30 mm behind the carcass face.
    back = face_y - s * .03
    box(f'{prefix} pull rail', (x0, min(back, back - s * .004), channel_bottom), (x1, max(back, back - s * .004), channel_top), rail)
    lip = (back, face_y)
    box(f'{prefix} pull rail lip', (x0, min(lip), channel_bottom - .004), (x1, max(lip), channel_bottom), rail, .001)
    count = max(1, round((x1 - x0) / bay))
    width = (x1 - x0) / count
    gap = .003
    for b in range(count):
        bx0, bx1 = x0 + b * width + gap / 2, x0 + (b + 1) * width - gap / 2
        top = channel_bottom - gap
        for r, height in enumerate(list(rows) + [None]):
            bottom = z_low if height is None else top - height
            if top - bottom < .02:
                break
            box(f'{prefix} front {b + 1}.{r + 1}', (bx0, fy0, bottom + gap / 2), (bx1, fy1, top - gap / 2), oak, .0012)
            top = bottom
            if height is None:
                break


# ---------------------------------------------------------------- the island


def island(granite, oak, rail, plinth):
    """Granite slab on a smoked-oak base, fronts on the camera side and a
    0.29 m overhang on the far side for stools."""
    top = box('Island granite slab', (WORKTOP_X[0], WORKTOP_Y[0], COUNTER_Z - SLAB_M),
              (WORKTOP_X[1], WORKTOP_Y[1], COUNTER_Z), granite, .0015, 3)
    under = COUNTER_Z - SLAB_M
    face_y = -.465
    carcass('Island', WORKTOP_X[0] + .03, WORKTOP_X[1] - .03, face_y, .20, .10, under, plinth)
    box('Island plinth', (WORKTOP_X[0] + .09, face_y + .07, 0.), (WORKTOP_X[1] - .09, .14, .10), plinth)
    handleless_run('Island', WORKTOP_X[0] + .03, WORKTOP_X[1] - .03, face_y, -1, .103, under - .002, oak, rail)
    for x0, x1 in ((WORKTOP_X[0] + .01, WORKTOP_X[0] + .03), (WORKTOP_X[1] - .03, WORKTOP_X[1] - .01)):
        box('Island end panel', (x0, face_y - .019, 0.), (x1, .20, under), oak, .0012)
    box('Island seating-side panel', (WORKTOP_X[0] + .03, .20, .10), (WORKTOP_X[1] - .03, .219, under), oak, .0012)
    return top


# ------------------------------------------------------------- the back run


def back_run(granite, oak, rail, plinth, steel, hob_glass):
    """Base cabinets along the back wall, the same granite on top with a short
    upstand, a black-glass induction hob under the shelves."""
    wall = ROOM_Y[1]
    face_y = BACK_FRONT_Y + .02
    under = BACK_TOP_Z - SLAB_M
    x_lo, x_hi = ROOM_X[0], TALL_X[0]
    carcass('Back run', x_lo, x_hi, face_y, wall, .10, under, plinth)
    box('Back run plinth', (x_lo, face_y + .07, 0.), (x_hi, wall, .10), plinth)
    box('Back run granite top', (x_lo, BACK_FRONT_Y, under), (x_hi, wall, BACK_TOP_Z), granite, .0015, 3)
    box('Back run granite upstand', (x_lo, wall - .02, BACK_TOP_Z), (x_hi, wall, BACK_TOP_Z + .10), granite, .001)
    handleless_run('Back run', x_lo, x_hi, face_y, -1, .103, under - .002, oak, rail, rows=(.18, .30))
    # Induction hob: 6 mm black glass sitting in the granite, steel trim.
    hx = (SHELF_X[0] + .55, SHELF_X[0] + 1.33)
    box('Induction hob glass', (hx[0], 1.97, BACK_TOP_Z - .001), (hx[1], 2.48 - .14, BACK_TOP_Z + .005), hob_glass, .002)
    return dict(hob_x=list(hx), hob_y=[1.97, 2.34], hob_top_z=BACK_TOP_Z + .005)


def tall_column(oak, rail, plinth):
    """Floor-to-bulkhead larder and integrated fridge right of the window."""
    wall = ROOM_Y[1]
    face_y = BACK_FRONT_Y + .02
    x0, x1 = TALL_X
    box('Tall column carcass', (x0, face_y, .10), (x1, wall, TALL_TOP), plinth)
    box('Tall column plinth', (x0, face_y + .07, 0.), (x1, wall, .10), plinth)
    doors = 3
    width = (x1 - x0) / doors
    for d in range(doors):
        dx0, dx1 = x0 + d * width + .0015, x0 + (d + 1) * width - .0015
        box(f'Tall door {d + 1}', (dx0, face_y - .019, .103), (dx1, face_y, TALL_TOP - .003), oak, .0012)
        # A vertical recessed grip at the opening edge.
        gx = dx1 - .02 if d % 2 == 0 else dx0
        box(f'Tall door {d + 1} grip', (gx, face_y - .021, 1.0), (gx + .02, face_y - .017, 1.35), rail, .001)
    box('Tall column end panel', (x0 - .02, face_y - .019, 0.), (x0, wall, TALL_TOP), oak, .0012)


def shelves(walnut, led_mat):
    """Two oiled walnut shelves on hidden brackets, an LED strip under each."""
    wall = ROOM_Y[1]
    out = []
    for i, top in enumerate(SHELF_TOPS):
        box(f'Walnut shelf {i + 1}', (SHELF_X[0], wall - SHELF_DEPTH, top - .04), (SHELF_X[1], wall, top), walnut, .002)
        box(f'Shelf {i + 1} LED strip', (SHELF_X[0] + .04, wall - SHELF_DEPTH + .03, top - .043),
            (SHELF_X[1] - .04, wall - SHELF_DEPTH + .042, top - .04), led_mat)
        out.append(dict(top_z=top, x=list(SHELF_X), y=[wall - SHELF_DEPTH, wall]))
    return out


# -------------------------------------------------------------------- shell


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


def window(frame_mat, sill_mat):
    """Black aluminium casement in the back wall: frame, one mullion, thin
    glass, granite sill, plaster reveals."""
    (x0, x1), (z0, z1) = WINDOW['x'], WINDOW['z']
    face = ROOM_Y[1]
    depth = (face + .08, face + .14)
    bar = .05

    def part(label, a0, a1, c0, c1, d=depth, mat=frame_mat, bevel=.001):
        return box(f'Window {label}', (a0, d[0], c0), (a1, d[1], c1), mat, bevel)

    part('head', x0, x1, z1 - bar, z1)
    part('bottom rail', x0, x1, z0, z0 + bar)
    part('left jamb', x0, x0 + bar, z0 + bar, z1 - bar)
    part('right jamb', x1 - bar, x1, z0 + bar, z1 - bar)
    mid = (x0 + x1) / 2
    part('mullion', mid - .03, mid + .03, z0 + bar, z1 - bar, (depth[0] - .01, depth[1]))
    glass = part('glass', x0 + .01, x1 - .01, z0 + .01, z1 - .01,
                 ((depth[0] + depth[1]) / 2 - .003, (depth[0] + depth[1]) / 2 + .003), thin_glass(), 0.)
    glass.visible_shadow = False
    part('sill', x0 - .02, x1 + .02, z0 - .03, z0, (face - .02, depth[0]), sill_mat, .0015)
    return glass


def cafe_curtain(linen, rod_mat):
    """A gathered linen cafe curtain on a slim tension rod across the reveal.

    It covers the lower part of the window, up to just under eye height, so
    the street below stays out of the picture and the skyline shows over it.
    The panel is gathered into uneven soft folds (mostly 10-11 cm
    apart, about 1 cm deep, fuller at the rod), hanging just clear of
    the sill.
    """
    import bpy
    import bmesh
    (x0, x1), z0 = WINDOW['x'], WINDOW['z'][0]
    top, bottom = WINDOW['curtain_top'], z0 + .012
    yc = ROOM_Y[1] + .04
    nx, nz = 180, 24
    bm = bmesh.new()
    rows = []
    for j in range(nz + 1):
        t = j / nz
        z = bottom + t * (top - .012 - bottom)
        row = []
        for i in range(nx + 1):
            x = x0 + .004 + (x1 - x0 - .008) * i / nx
            # Gathered folds are never regular: two fold sizes, depth that
            # wanders along the panel, and folds that drift as they fall.
            u = 2 * math.pi * (x - x0)
            depth = (.010 + .004 * t) * (1 + .35 * math.sin(u / .61 + .7))
            drift = .5 * (1 - t) * math.sin(u / .83)
            y = yc + depth * (.7 * math.sin(u / .105 + drift) + .3 * math.sin(u / .046 + 2.1 + 1.7 * drift))
            row.append(bm.verts.new((x, y, z)))
        rows.append(row)
    for j in range(nz):
        for i in range(nx):
            bm.faces.new((rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i]))
    mesh = bpy.data.meshes.new('Linen cafe curtain')
    bm.to_mesh(mesh)
    bm.free()
    _world_uv(mesh)
    for p in mesh.polygons:
        p.use_smooth = True
    obj = bpy.data.objects.new('Linen cafe curtain', mesh)
    bpy.context.collection.objects.link(obj)
    mesh.materials.append(linen)
    solid = obj.modifiers.new('Cloth thickness', 'SOLIDIFY')
    solid.thickness, solid.offset = .0012, 0.
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=.0065, depth=x1 - x0, location=((x0 + x1) / 2, yc, top - .006),
                                        rotation=(0., math.pi / 2, 0.))
    rod = bpy.context.object
    rod.name = 'Curtain tension rod'
    rod.data.materials.append(rod_mat)
    bpy.ops.object.shade_smooth()
    return dict(top_z=top, bottom_z=bottom, y=yc)


def shell(walls, ceiling, floor):
    """Floor, ceiling and four walls; the back wall has the window opening."""
    (x0, x1), (y0, y1), t = ROOM_X, ROOM_Y, WALL_THICK_M
    box('Floor', (x0 - t, y0 - t, -.06), (x1 + t, y1 + t, 0.), floor)
    box('Ceiling', (x0 - t, y0 - t, CEILING_M), (x1 + t, y1 + t, CEILING_M + .12), ceiling)
    z = (-.06, CEILING_M)
    box('Left wall', (x0 - t, y0 - t, z[0]), (x0, y1 + t, z[1]), walls)
    box('Right wall', (x1, y0 - t, z[0]), (x1 + t, y1 + t, z[1]), walls)
    wall_y('Back wall', y1, y1 + t, (x0, x1), z, (WINDOW['x'], WINDOW['z']), walls)
    wall_y('Wall behind camera', y0 - t, y0, (x0, x1), z, None, walls)
    box('Bulkhead over tall column', (TALL_X[0] - .02, BACK_FRONT_Y + .001, TALL_TOP), (x1, y1, CEILING_M), walls)


# -------------------------------------------------------------------- lights


# Recessed downlights: (x, y) under the ceiling. Two rows: over the back run
# and in front of the island; none sits over the island, the pendants do that.
DOWNLIGHTS = [(-2.2, 2.05), (-.95, 2.05), (.35, 2.05), (-1.3, -1.05), (.3, -1.05), (1.9, -1.05)]
DOWNLIGHT_W = 5.
SHELF_LED_W_PER_M = 7.


def downlight(name, x, y, trim, baffle):
    """A 100 mm downlight: white trim ring, black baffle, a 70-degree spot just
    under the baffle."""
    import bpy
    cylinder(f'{name} trim', (x, y, CEILING_M - .002), .05, .004, trim, 48)
    cylinder(f'{name} baffle', (x, y, CEILING_M - .0045), .036, .002, baffle, 48)
    data = bpy.data.lights.new(name, 'SPOT')
    data.energy, data.color = DOWNLIGHT_W, WARM_3000K
    data.spot_size, data.spot_blend = math.radians(70.), .35
    data.shadow_soft_size = .03
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = (x, y, CEILING_M - .006)
    obj.rotation_euler = (0., 0., 0.)   # spots point down -z
    return obj


def shelf_leds(shelf_records):
    """The strips' light: a thin area light along each strip, facing down."""
    import bpy
    for i, rec in enumerate(shelf_records):
        length = rec['x'][1] - rec['x'][0] - .08
        data = bpy.data.lights.new(f'Shelf {i + 1} LED light', 'AREA')
        data.shape, data.size, data.size_y = 'RECTANGLE', length, .012
        data.energy, data.color = SHELF_LED_W_PER_M * length, WARM_3000K
        obj = bpy.data.objects.new(f'Shelf {i + 1} LED light', data)
        bpy.context.collection.objects.link(obj)
        obj.location = ((rec['x'][0] + rec['x'][1]) / 2, rec['y'][0] + .036, rec['top_z'] - .0445)
        obj.rotation_euler = (0., 0., 0.)   # area lights emit along -z


# What the camera sees through the window: Poly Haven shanghai_bund, the Pudong
# skyline at night across the river -- a kilometre away, so it stays at
# infinity through a window. Only camera rays see it; for every other ray the
# world is the dark night sky, so the city does not light the room.
WINDOW_VIEW = 'shanghai_bund_2k.hdr'
# The Pudong towers, turned to stand out of the back window (+y); checked
# by rendering the panorama along +y at several turns.
WINDOW_VIEW_TURN_DEG = -115.
WINDOW_VIEW_STRENGTH = .2
NIGHT_SKY = (.0018, .0024, .0040)


def night_world(scene):
    import bpy
    world = bpy.data.worlds.new('City at night')
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    lighting = nodes['Background']
    lighting.inputs['Color'].default_value = (*NIGHT_SKY, 1)
    lighting.inputs['Strength'].default_value = 1.
    coord = nodes.new('ShaderNodeTexCoord')
    turn = nodes.new('ShaderNodeMapping')
    turn.vector_type = 'VECTOR'
    turn.inputs['Rotation'].default_value = (0., 0., math.radians(WINDOW_VIEW_TURN_DEG))
    links.new(coord.outputs['Generated'], turn.inputs['Vector'])
    photo = nodes.new('ShaderNodeTexEnvironment')
    photo.image = bpy.data.images.load(str(TEXTURES / WINDOW_VIEW), check_existing=True)
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


def build_kitchen(scene):
    """Build the room, the island, the back run and the fittings; return a
    description of what was built."""
    granite = honed_granite('Honed salt-and-pepper granite')
    oak = scanned('Smoked oak veneer fronts', 'flamed_black_veneer', OAK_M, swap=True, per_object=True,
                  rough_range=(.38, .62), normal_strength=.5)
    linen = scanned('Natural rough linen', 'rough_linen', LINEN_M, tint=(1.22, 1.10, .90), rough_range=(.80, .95),
                    normal_strength=.8)
    walnut = scanned('Oiled walnut shelves', 'black_walnut_veneer_02', WALNUT_M, per_object=True,
                     tint=(.78, .70, .62), rough_range=(.40, .60), normal_strength=.5)
    walls = scanned('Micro-cement plaster', 'plaster_grey_04', PLASTER_M, tint=(1.05, 1.03, 1.0),
                    rough_range=(.70, .90), normal_strength=.4)
    rail = principled('Dark anodised aluminium', (.035, .034, .033), .38, 1.)
    plinth = principled('Carcass and plinth shadow grey', (.025, .024, .023), .7)
    frame = principled('Black powder-coated aluminium', (.02, .02, .021), .42)
    steel = principled('Brushed stainless steel', (.62, .62, .60), .28, 1.)
    hob_glass = principled('Black ceramic hob glass', (.008, .008, .009), .06)
    ceiling = principled('Ceiling white emulsion', (.72, .71, .69), .92)
    floor = principled('Grey porcelain floor', (.22, .21, .20), .45)
    trim = principled('White downlight trim', (.80, .80, .78), .4)
    baffle = principled('Black downlight baffle', (.01, .01, .01), .6)
    led = led_diffuser('Warm LED strip diffuser', WARM_3000K, 6.)

    top = island(granite, oak, rail, plinth)
    hob = back_run(granite, oak, rail, plinth, steel, hob_glass)
    tall_column(oak, rail, plinth)
    shelf_records = shelves(walnut, led)
    shell(walls, ceiling, floor)
    window(frame, granite)
    curtain = cafe_curtain(linen, frame)
    for i, (x, y) in enumerate(DOWNLIGHTS):
        downlight(f'Ceiling downlight {i + 1}', x, y, trim, baffle)
    shelf_leds(shelf_records)
    night_world(scene)
    return dict(worktop_object=top.name, worktop_x=list(WORKTOP_X), worktop_y=list(WORKTOP_Y),
                worktop_top_z=COUNTER_Z, back_top_z=BACK_TOP_Z, shelves=shelf_records, hob=hob,
                window_view=WINDOW_VIEW, curtain=curtain, downlights=len(DOWNLIGHTS))
