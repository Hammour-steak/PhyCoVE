"""A galley kitchen in a seaside flat, built to measure around the drop.

The room is built from ordinary parts at their real sizes:

* a dark granite tile floor (Poly Haven CC0 scan at its measured 2.3 m repeat)
  whose top face *is* the simulator's floor plane, so the only surface the lid
  touches on screen is the collider;
* a run of handleless base cabinets along the left wall with a 30 mm quartz
  worktop and a flush induction hob with the pot standing on it; wall cabinets
  with an LED strip under them;
* a block of charcoal tall units (fridge, oven tower, larder) on the right;
* a tall steel-framed window cut through the end wall, looking out over the
  sea (Poly Haven dalkey_view). The overcast sky outside is the only daylight;
  inside, three recessed ceiling downlights and the under-cabinet strip are the
  lamps the flat actually has. Nothing lights the room from nowhere.

Nothing in here takes part in the simulation. Every coordinate is Blender world
space in metres; heights are given above the floor plane ``layout['floor_z']``.
"""
from __future__ import annotations

import math

from pcve_assets import asset as _pcve_asset

TEXTURES = _pcve_asset('polyhaven/pot_lid_drop')

# ----------------------------------------------------------------- the room
# Plan, world x/y. The camera stands in the aisle at x = 1.46 looking up the
# room (+y) and slightly left, so the left run fills the left of the frame and
# the end wall with the window closes the view.
X_WALL_LEFT = -0.20       # plaster face behind the base run
X_DOOR_FACE = 0.429       # face of the base-cabinet doors
X_TOP_FRONT = 0.455       # front edge of the worktop (26 mm past the doors)
X_TALL_FACE = 2.47        # face of the tall units on the right
X_WALL_RIGHT = 3.10
Y_FAR = 2.228             # plaster face of the end wall (window wall)
Y_BACK = -3.00            # wall behind the camera
Y_TALL_START = 0.45       # the tall units run from here to the end wall
WALL_THICK = 0.20
CEILING_H = 2.75          # above the floor

# The worktop top is at z = 0.946 in the layout frame, so the pot and the lid
# released beside it sit 1.036 m above the floor (a tall but ordinary counter).
WORKTOP_TOP_Z = 0.946
WORKTOP_THICK = 0.03
PLINTH_H = 0.12
PLINTH_SETBACK = 0.07
DOOR_THICK = 0.019
DOOR_GAP = 0.003

# Flush induction hob under the pot (pot centre at x 0.30, y -0.85).
HOB_X = (-0.105, 0.415)
HOB_Y = (-1.05, -0.46)
HOB_ZONES = ((0.28, -0.87, 0.105), (0.28, -0.63, 0.085), (0.02, -0.87, 0.085), (0.02, -0.63, 0.105))

# Wall cabinets over the far part of the run, with an LED strip underneath.
WALL_CAB_X = (X_WALL_LEFT, 0.15)
WALL_CAB_Y = (-0.25, Y_FAR)
WALL_CAB_Z = (1.62, 2.38)   # above the floor

# The window in the end wall: along-wall span (x) and sill/head heights.
WINDOW_X = (0.55, 1.85)
WINDOW_Z = (0.12, 2.50)     # above the floor: a low sill, the sea shows below the horizon

# Real sizes of the Poly Haven scans (api.polyhaven.com/info "dimensions").
FLOOR_TILE_M = 2.30        # granite_tile: four 575 mm tiles per repeat
WALL_TILE_M = 2.00         # painted_plaster_wall

# What the camera sees through the glass, and what lights the room: Poly Haven
# dalkey_view, an overcast coastal morning above Dublin Bay. Its open sea and
# the far headland sit at u = 0.20-0.30 of the photograph; turning the lookup by
# WINDOW_VIEW_TURN_DEG puts that part behind the window (+y), which leaves the
# veiled sun (u = 0.68) behind the building: soft north-facing light, no sun
# patch on the floor.
WINDOW_VIEW = 'dalkey_view_4k.hdr'
WINDOW_VIEW_TURN_DEG = 8.0
SKY_STRENGTH = 1.0

LED_COLOUR = (1.0, 0.80, 0.58)      # 3000 K strip
DOWNLIGHT_COLOUR = (1.0, 0.78, 0.55)
DOWNLIGHT_W = 18.0
DOWNLIGHTS_Y = (-1.55, -0.05, 1.35)
DOWNLIGHT_X = 1.30


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
    obj['kitchen_part'] = True
    return obj


def cylinder(name, centre, radius, depth, mat, vertices=48, axis='z', bevel=0.):
    import bpy
    rotation = {'x': (0, math.pi / 2, 0), 'y': (math.pi / 2, 0, 0), 'z': (0, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                        location=centre, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new('Eased edges', 'BEVEL')
        mod.width, mod.segments, mod.limit_method = bevel, 2, 'ANGLE'
    bpy.ops.object.shade_smooth()
    obj.data.set_sharp_from_angle(angle=math.radians(40))
    obj['kitchen_part'] = True
    return obj


# ----------------------------------------------------------------- materials


def principled(name, color, roughness, metallic=0., coat=0.):
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, 1)
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    if coat:
        bsdf.inputs['Coat Weight'].default_value = coat
        bsdf.inputs['Coat Roughness'].default_value = .05
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
        # A vector multiply, not a colour mix: colour sockets clamp at 1.
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


def scanned(name, stem, tile_m, offset=(0., 0., 0.), **options):
    """A scan box-projected in world metres (every room part is built at the
    origin), so floor tiles and wall paint keep their real size everywhere."""
    mat = principled(name, (.5, .5, .5), .5)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Location'].default_value = offset
    mapping.inputs['Scale'].default_value = (1 / tile_m,) * 3
    links.new(coord.outputs['Object'], mapping.inputs['Vector'])
    _scan_nodes(mat, stem, mapping.outputs['Vector'], projection='BOX', **options)
    return mat


def lacquer(name, color, roughness=.38, drift=.04):
    """Matt lacquered joinery: one colour with a faint drift in tone and sheen
    across a door, the way a sprayed panel never comes out perfectly even."""
    mat = principled(name, color, roughness)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    position = nodes.new('ShaderNodeNewGeometry')
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 2.2
    noise.inputs['Detail'].default_value = 4.
    links.new(position.outputs['Position'], noise.inputs['Vector'])
    tone = nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].color = (*(c * (1 - drift) for c in color), 1)
    tone.color_ramp.elements[1].color = (*(min(1., c * (1 + drift / 2)) for c in color), 1)
    links.new(noise.outputs['Fac'], tone.inputs['Fac'])
    links.new(tone.outputs['Color'], bsdf.inputs['Base Color'])
    sheen = nodes.new('ShaderNodeMapRange')
    sheen.inputs['To Min'].default_value = roughness - .05
    sheen.inputs['To Max'].default_value = roughness + .06
    links.new(noise.outputs['Fac'], sheen.inputs['Value'])
    links.new(sheen.outputs['Result'], bsdf.inputs['Roughness'])
    return mat


def quartz():
    """Engineered white quartz: a fine grey-and-white speckle under a polished,
    very slightly hazy surface."""
    mat = principled('White quartz worktop', (.80, .79, .76), .12)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    coord = nodes.new('ShaderNodeTexCoord')
    grain = nodes.new('ShaderNodeTexVoronoi')
    grain.inputs['Scale'].default_value = 900.
    grain.inputs['Randomness'].default_value = 1.
    links.new(coord.outputs['Object'], grain.inputs['Vector'])
    fleck = nodes.new('ShaderNodeValToRGB')
    fleck.color_ramp.elements[0].position = .82
    fleck.color_ramp.elements[0].color = (.80, .79, .76, 1)
    fleck.color_ramp.elements[1].position = .97
    fleck.color_ramp.elements[1].color = (.46, .45, .44, 1)
    links.new(grain.outputs['Color'], fleck.inputs['Fac'])
    cloud = nodes.new('ShaderNodeTexNoise')
    cloud.inputs['Scale'].default_value = 3.
    links.new(coord.outputs['Object'], cloud.inputs['Vector'])
    mix = nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    mix.inputs['Factor'].default_value = .08
    links.new(fleck.outputs['Color'], mix.inputs['A'])
    links.new(cloud.outputs['Color'], mix.inputs['B'])
    links.new(mix.outputs['Result'], bsdf.inputs['Base Color'])
    return mat


def brushed_steel(name, roughness=.22, color=(.56, .55, .53)):
    """Brushed stainless/aluminium: anisotropic highlights along world y."""
    mat = principled(name, color, roughness, metallic=1.)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    bsdf.inputs['Anisotropic'].default_value = .6
    tangent = nodes.new('ShaderNodeTangent')
    tangent.direction_type = 'RADIAL'
    tangent.axis = 'Y'
    links.new(tangent.outputs['Tangent'], bsdf.inputs['Tangent'])
    return mat


def black_glass(name, rings=()):
    """Toughened black glass of a hob or an oven door: a mirror-smooth coat
    over near-black, with the hob's printed zone rings in pale grey."""
    mat = principled(name, (.006, .006, .007), .25, coat=1.)
    if not rings:
        return mat
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    coord = nodes.new('ShaderNodeTexCoord')
    xyz = nodes.new('ShaderNodeSeparateXYZ')
    links.new(coord.outputs['Object'], xyz.inputs['Vector'])
    printed = None
    for cx, cy, r in rings:
        dx = nodes.new('ShaderNodeMath'); dx.operation = 'SUBTRACT'
        links.new(xyz.outputs['X'], dx.inputs[0]); dx.inputs[1].default_value = cx
        dy = nodes.new('ShaderNodeMath'); dy.operation = 'SUBTRACT'
        links.new(xyz.outputs['Y'], dy.inputs[0]); dy.inputs[1].default_value = cy
        vec = nodes.new('ShaderNodeCombineXYZ')
        links.new(dx.outputs[0], vec.inputs['X']); links.new(dy.outputs[0], vec.inputs['Y'])
        length = nodes.new('ShaderNodeVectorMath'); length.operation = 'LENGTH'
        links.new(vec.outputs['Vector'], length.inputs[0])
        off = nodes.new('ShaderNodeMath'); off.operation = 'SUBTRACT'
        links.new(length.outputs['Value'], off.inputs[0]); off.inputs[1].default_value = r
        mag = nodes.new('ShaderNodeMath'); mag.operation = 'ABSOLUTE'
        links.new(off.outputs[0], mag.inputs[0])
        line = nodes.new('ShaderNodeMath'); line.operation = 'LESS_THAN'
        links.new(mag.outputs[0], line.inputs[0]); line.inputs[1].default_value = .0012
        if printed is None:
            printed = line.outputs[0]
        else:
            add = nodes.new('ShaderNodeMath'); add.operation = 'MAXIMUM'
            links.new(printed, add.inputs[0]); links.new(line.outputs[0], add.inputs[1])
            printed = add.outputs[0]
    mix = nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    links.new(printed, mix.inputs['Factor'])
    mix.inputs['A'].default_value = (.006, .006, .007, 1)
    mix.inputs['B'].default_value = (.30, .30, .30, 1)
    links.new(mix.outputs['Result'], bsdf.inputs['Base Color'])
    return mat


def thin_glass():
    """Float glass shaded thin: Fresnel reflection over a transparent layer.

    Rays through it stay camera rays (the world shows the sea photograph to the
    camera) and it casts no shadow. Cycles' Fresnel node inverts the IOR on
    back faces, which would turn a pane seen obliquely from inside black by
    total internal reflection; feeding 1/1.52 on back faces cancels that.
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


def emitter(name, colour, strength):
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    for node in [n for n in nodes if n.type != 'OUTPUT_MATERIAL']:
        nodes.remove(node)
    emit = nodes.new('ShaderNodeEmission')
    emit.inputs['Color'].default_value = (*colour, 1)
    emit.inputs['Strength'].default_value = strength
    links.new(emit.outputs['Emission'], nodes['Material Output'].inputs['Surface'])
    return mat


# ----------------------------------------------------------------- joinery


def base_run(F, fronts, plinth, worktop, profile, glass_hob):
    """Handleless base cabinets along the left wall, worktop and hob.

    Doors are 600 mm bays counted from the end wall, 19 mm slabs with 3 mm
    shadow gaps; the recessed aluminium rail under the worktop is the handle.
    """
    top = WORKTOP_TOP_Z
    under = top - WORKTOP_THICK
    door_top = under - .040          # the rail channel sits above the doors
    door_bottom = F + PLINTH_H + .002
    box('Base run carcass', (X_WALL_LEFT, Y_BACK, F + PLINTH_H), (X_DOOR_FACE - DOOR_THICK, Y_FAR, under), fronts)
    box('Base run plinth', (X_WALL_LEFT, Y_BACK, F), (X_DOOR_FACE - PLINTH_SETBACK, Y_FAR, F + PLINTH_H), plinth)
    box('Handle rail', (X_DOOR_FACE - DOOR_THICK - .012, Y_BACK, door_top + .004),
        (X_DOOR_FACE - DOOR_THICK, Y_FAR, under - .002), profile)
    box('Worktop', (X_WALL_LEFT, Y_BACK, under), (X_TOP_FRONT, Y_FAR, top), worktop, .0015)
    y = Y_FAR
    index = 0
    while y - .6 > Y_BACK + .05:
        y0, y1 = y - .6 + DOOR_GAP / 2, y - DOOR_GAP / 2
        box(f'Base door {index + 1:02d}', (X_DOOR_FACE - DOOR_THICK, y0, door_bottom), (X_DOOR_FACE, y1, door_top),
            fronts, .0012)
        y -= .6
        index += 1
    box('Base filler panel', (X_DOOR_FACE - DOOR_THICK, Y_BACK, door_bottom), (X_DOOR_FACE, y - DOOR_GAP / 2, door_top),
        fronts, .0012)
    # Flush hob: the glass stands 0.5 mm proud of the worktop around it.
    box('Induction hob glass', (HOB_X[0], HOB_Y[0], top - .004), (HOB_X[1], HOB_Y[1], top + .0005), glass_hob, .0015)


def wall_cabinets(F, fronts, profile, led):
    """Wall cabinets with a slim aluminium LED profile under the front edge."""
    x0, x1 = WALL_CAB_X
    y0, y1 = WALL_CAB_Y
    z0, z1 = F + WALL_CAB_Z[0], F + WALL_CAB_Z[1]
    box('Wall cabinet carcass', (x0, y0, z0), (x1 - DOOR_THICK, y1, z1), fronts)
    y = y1
    index = 0
    while y - .6 > y0 - .05:
        box(f'Wall cabinet door {index + 1:02d}', (x1 - DOOR_THICK, max(y0, y - .6) + DOOR_GAP / 2, z0),
            (x1, y - DOOR_GAP / 2, z1), fronts, .0012)
        y -= .6
        index += 1
    box('LED profile', (x1 - .075, y0 + .03, z0 - .009), (x1 - .055, y1 - .03, z0), profile)
    box('LED diffuser', (x1 - .0735, y0 + .035, z0 - .0095), (x1 - .0565, y1 - .035, z0 - .0085), led)


def tall_units(F, charcoal, plinth, steel, glass):
    """Fridge, oven tower and larder in matt charcoal on the right."""
    x0 = X_TALL_FACE
    height = 2.40
    box('Tall units carcass', (x0 + DOOR_THICK, Y_TALL_START, F + PLINTH_H), (X_WALL_RIGHT, Y_FAR, F + height), charcoal)
    box('Tall units plinth', (x0 + PLINTH_SETBACK, Y_TALL_START, F), (X_WALL_RIGHT, Y_FAR, F + PLINTH_H), plinth)
    box('Tall units bulkhead', (x0 + .02, Y_TALL_START, F + height), (X_WALL_RIGHT, Y_FAR, F + CEILING_H), principled(
        'Bulkhead paint', (.70, .69, .66), .85))
    bays = [(Y_TALL_START, Y_TALL_START + .60, 'fridge'), (Y_TALL_START + .60, Y_TALL_START + 1.20, 'oven'),
            (Y_TALL_START + 1.20, Y_FAR, 'larder')]
    z_lo, z_hi = F + PLINTH_H + .002, F + height - .002
    for y0, y1, kind in bays:
        y0g, y1g = y0 + DOOR_GAP / 2, y1 - DOOR_GAP / 2
        if kind == 'oven':
            oz0, oz1 = F + .86, F + 1.46
            box('Oven fascia', (x0 - .002, y0g + .01, oz0), (x0 + DOOR_THICK, y1g - .01, oz1), steel, .002)
            box('Oven door glass', (x0 - .006, y0g + .03, oz0 + .03), (x0 - .001, y1g - .03, oz1 - .11), glass, .002)
            box('Oven handle', (x0 - .045, y0g + .07, oz1 - .07), (x0 - .03, y1g - .07, oz1 - .055), steel, .004)
            for sign in (-1, 1):
                yc = (y0 + y1) / 2 + sign * .21
                box('Oven handle post', (x0 - .032, yc - .006, oz1 - .068), (x0 - .006, yc + .006, oz1 - .057), steel, .002)
            box('Oven control strip', (x0 - .003, y0g + .03, oz1 - .095), (x0 - .001, y1g - .03, oz1 - .03), glass, .001)
            box('Tall door below oven', (x0, y0g, z_lo), (x0 + DOOR_THICK, y1g, oz0 - DOOR_GAP), charcoal, .0012)
            box('Tall door above oven', (x0, y0g, oz1 + DOOR_GAP), (x0 + DOOR_THICK, y1g, z_hi), charcoal, .0012)
        elif kind == 'fridge':
            split = F + 1.55
            box('Fridge door', (x0, y0g, z_lo), (x0 + DOOR_THICK, y1g, split - DOOR_GAP / 2), charcoal, .0012)
            box('Freezer door', (x0, y0g, split + DOOR_GAP / 2), (x0 + DOOR_THICK, y1g, z_hi), charcoal, .0012)
        else:
            box('Larder door', (x0, y0g, z_lo), (x0 + DOOR_THICK, y1g, z_hi), charcoal, .0012)
        # Vertical recessed pull: a dark slot on the door edge next to the bay.
        box(f'{kind} pull slot', (x0 - .001, y0g + .002, z_lo + .4), (x0 + .006, y0g + .022, z_hi - .4), plinth)


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


def steel_window(F, frame_mat, sill_mat):
    """Slim black steel window in the middle of the reveal: outer frame, a
    centre mullion and a transom, thin glass in each light, and a quartz
    window board inside."""
    (s0, s1), (h0, h1) = WINDOW_X, (F + WINDOW_Z[0], F + WINDOW_Z[1])
    depth = (Y_FAR + .085, Y_FAR + .125)
    bar = .045
    box('Window frame head', (s0, depth[0], h1 - bar), (s1, depth[1], h1), frame_mat, .002)
    box('Window frame sill', (s0, depth[0], h0), (s1, depth[1], h0 + bar), frame_mat, .002)
    box('Window frame left jamb', (s0, depth[0], h0 + bar), (s0 + bar, depth[1], h1 - bar), frame_mat, .002)
    box('Window frame right jamb', (s1 - bar, depth[0], h0 + bar), (s1, depth[1], h1 - bar), frame_mat, .002)
    mid = (s0 + s1) / 2
    inner = (depth[0] + .006, depth[1] - .004)
    box('Window mullion', (mid - .022, inner[0], h0 + bar), (mid + .022, inner[1], h1 - bar), frame_mat, .002)
    transom = h1 - .55
    for a, b in ((s0 + bar, mid - .022), (mid + .022, s1 - bar)):
        box('Window transom', (a, inner[0], transom - .018), (b, inner[1], transom + .018), frame_mat, .002)
    glass = box('Window glass', (s0 + .01, (depth[0] + depth[1]) / 2 - .003, h0 + .01),
                (s1 - .01, (depth[0] + depth[1]) / 2 + .003, h1 - .01), thin_glass())
    glass.visible_shadow = False
    box('Window board', (s0 - .04, Y_FAR - .03, h0 - .025), (s1 + .04, depth[0], h0), sill_mat, .002)
    return glass


def shell(F, walls, ceiling, floor, skirting):
    """Floor, ceiling and four walls with the window opening in the end wall."""
    t = WALL_THICK
    x0, x1, y0, y1 = X_WALL_LEFT, X_WALL_RIGHT, Y_BACK, Y_FAR
    floor_obj = box('Granite tile floor', (x0 - t, y0 - t, F - .06), (x1 + t, y1 + t, F), floor)
    floor_obj['physics_floor'] = True
    box('Ceiling', (x0 - t, y0 - t, F + CEILING_H), (x1 + t, y1 + t, F + CEILING_H + .12), ceiling)
    z = (F - .06, F + CEILING_H)
    hole = (WINDOW_X, (F + WINDOW_Z[0], F + WINDOW_Z[1]))
    wall_y('End wall (window)', y1, y1 + t, (x0 - t, x1 + t), z, hole, walls)
    wall_y('Wall behind camera', y0 - t, y0, (x0 - t, x1 + t), z, None, walls)
    box('Left wall', (x0 - t, y0, z[0]), (x0, y1, z[1]), walls)
    box('Right wall', (x1, y0, z[0]), (x1 + t, y1, z[1]), walls)
    # Skirting where no cabinet stands against a wall.
    box('Skirting end wall', (X_TOP_FRONT, y1 - .015, F), (X_TALL_FACE, y1, F + .09), skirting, .0015)
    box('Skirting right wall', (x1 - .015, y0, F), (x1, Y_TALL_START, F + .09), skirting, .0015)
    box('Skirting camera wall', (X_DOOR_FACE, y0, F), (x1, y0 + .015, F + .09), skirting, .0015)
    return floor_obj


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


def downlights(F, trim, lens):
    """Recessed ceiling downlights: a white trim ring and a frosted lens that
    glows, plus the light each one throws (a wide, soft-edged beam)."""
    import bpy
    from mathutils import Vector
    z = F + CEILING_H
    for i, y in enumerate(DOWNLIGHTS_Y):
        cylinder(f'Downlight trim {i + 1}', (DOWNLIGHT_X, y, z - .002), .045, .006, trim, 48)
        cylinder(f'Downlight lens {i + 1}', (DOWNLIGHT_X, y, z - .0055), .032, .002, lens, 48)
        data = bpy.data.lights.new(f'Downlight {i + 1}', 'SPOT')
        data.energy = DOWNLIGHT_W
        data.color = DOWNLIGHT_COLOUR
        data.shadow_soft_size = .03
        data.spot_size = math.radians(110)
        data.spot_blend = 1.
        light = bpy.data.objects.new(f'Downlight {i + 1}', data)
        bpy.context.collection.objects.link(light)
        light.location = (DOWNLIGHT_X, y, z - .012)
        light.rotation_euler = Vector((0, 0, -1)).to_track_quat('-Z', 'Y').to_euler()


def sky(scene, window_view):
    """The overcast morning outside. The photograph lights the room through the
    window and is what the camera sees through the glass, so the light and the
    view agree; a portal in the opening tells Cycles where to look for it."""
    import bpy
    world = bpy.data.worlds.new('Overcast coastal morning')
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    background = nodes['Background']
    coord = nodes.new('ShaderNodeTexCoord')
    turn = nodes.new('ShaderNodeMapping')
    turn.vector_type = 'VECTOR'
    turn.inputs['Rotation'].default_value = (0., 0., math.radians(WINDOW_VIEW_TURN_DEG))
    photo = nodes.new('ShaderNodeTexEnvironment')
    photo.image = bpy.data.images.load(str(window_view), check_existing=True)
    links.new(coord.outputs['Generated'], turn.inputs['Vector'])
    links.new(turn.outputs['Vector'], photo.inputs['Vector'])
    links.new(photo.outputs['Color'], background.inputs['Color'])
    background.inputs['Strength'].default_value = SKY_STRENGTH
    return world


def faucet(F, steel):
    """Gooseneck mixer tap behind the sink, the one fitting that shows above
    the worktop edge from the low camera."""
    import bpy
    from mathutils import Vector
    x, y = .02, 1.30
    top = WORKTOP_TOP_Z
    cylinder('Tap base', (x, y, top + .015), .026, .03, steel, 48, bevel=.003)
    curve = bpy.data.curves.new('Tap spout', 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = .011
    curve.bevel_resolution = 4
    curve.resolution_u = 24
    spline = curve.splines.new('BEZIER')
    pts = [(x, y, top + .03), (x, y, top + .30), (x + .19, y, top + .30), (x + .19, y, top + .22)]
    spline.bezier_points.add(len(pts) - 1)
    for point, co in zip(spline.bezier_points, pts):
        point.co = co
        point.handle_left_type = point.handle_right_type = 'AUTO'
    spline.bezier_points[1].handle_left_type = spline.bezier_points[1].handle_right_type = 'ALIGNED'
    spline.bezier_points[1].handle_left = (x, y, top + .22)
    spline.bezier_points[1].handle_right = (x, y, top + .37)
    spline.bezier_points[2].handle_left_type = spline.bezier_points[2].handle_right_type = 'ALIGNED'
    spline.bezier_points[2].handle_left = (x + .19, y, top + .37)
    spline.bezier_points[2].handle_right = (x + .19, y, top + .26)
    obj = bpy.data.objects.new('Tap spout', curve)
    bpy.context.collection.objects.link(obj)
    curve.materials.append(steel)
    obj['kitchen_part'] = True
    lever = cylinder('Tap lever', (x - .005, y + .03, top + .075), .006, .07, steel, 24, 'y', .001)
    lever.rotation_euler = (math.radians(70), 0, 0)
    return obj


def build_kitchen(scene, layout):
    """Build the room, the joinery, the window and the lights; describe them."""
    F = float(layout['floor_z'])
    floor = scanned('Honed granite floor tiles', 'granite_tile', FLOOR_TILE_M, offset=(.10, .25, 0.),
                    tint=(1.05, 1.05, 1.07), rough_range=(.30, .62), normal_strength=.7)
    walls = scanned('Painted plaster walls', 'painted_plaster_wall', WALL_TILE_M, tint=(1.18, 1.17, 1.14),
                    rough_range=(.78, .92), normal_strength=.30)
    ceiling = principled('Ceiling white', (.76, .76, .74), .92)
    fronts = lacquer('Warm white matt lacquer', (.72, .71, .67), .40)
    charcoal = lacquer('Charcoal matt lacquer', (.075, .077, .080), .45, .06)
    plinth = principled('Plinth shadow grey', (.025, .026, .027), .6)
    worktop = quartz()
    profile = brushed_steel('Anodised aluminium profile', .30, (.62, .62, .62))
    steel = brushed_steel('Brushed stainless steel', .20)
    hob = black_glass('Induction hob glass', [(cx, cy, r) for cx, cy, r in HOB_ZONES])
    oven_glass = black_glass('Oven door glass')
    frame = principled('Black powder-coated steel', (.018, .018, .019), .42)
    skirting = principled('Skirting paint', (.66, .65, .62), .5)
    led = emitter('LED strip diffuser', LED_COLOUR, 9.)
    trim = principled('Downlight trim', (.80, .80, .78), .4)
    lens = emitter('Downlight lens', DOWNLIGHT_COLOUR, 10.)

    floor_obj = shell(F, walls, ceiling, floor, skirting)
    base_run(F, fronts, plinth, worktop, profile, hob)
    wall_cabinets(F, fronts, profile, led)
    tall_units(F, charcoal, plinth, steel, oven_glass)
    steel_window(F, frame, worktop)
    faucet(F, steel)
    downlights(F, trim, lens)
    (s0, s1), (z0, z1) = WINDOW_X, (F + WINDOW_Z[0], F + WINDOW_Z[1])
    portal('Window sky portal', ((s0 + s1) / 2, Y_FAR + WALL_THICK + .01, (z0 + z1) / 2), (s1 - s0, z1 - z0), (0, -1, 0))
    sky(scene, TEXTURES / WINDOW_VIEW)
    return dict(floor_object=floor_obj.name, floor_top_z=F, worktop_top_z=WORKTOP_TOP_Z,
                worktop_front_x=X_TOP_FRONT, window_x=list(WINDOW_X), window_z_above_floor=list(WINDOW_Z),
                window_view=WINDOW_VIEW, window_view_turn_deg=WINDOW_VIEW_TURN_DEG)
