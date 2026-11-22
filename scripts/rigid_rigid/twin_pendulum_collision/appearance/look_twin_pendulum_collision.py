"""A coupled-pendulum demonstrator on a physics teaching-lab bench; appearance only.

The room is a university physics lab: a black epoxy-resin wall bench against
painted concrete blockwork, two surface-mounted socket outlets, and a
data-logging laptop, a results sheet and a pocket watch left on the bench.
Light comes from
what such a room has: two opal fluorescent battens in the ceiling and low
morning sun through a window in the left wall (out of frame), under a Nishita
sky that is only seen through that window. Nothing here touches the physics:
the bobs, rods and pivots replay the simulation cache, and every prop is
checked against the replayed trajectory (see ``verify_props``).

Self-contained: every helper and asset lives in this scene (assets under
``assets/polyhaven/twin_pendulum_collision``); nothing is borrowed from another
scene.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from scene_geometry import TABLE_HEIGHT, PIVOT_HEIGHT, PIVOTS, BOB_RADIUS, LENGTH, KEYS
from pcve_assets import asset as _pcve_asset
from pcve_blender_compat import set_shader_input

# Physics teaching lab: black epoxy bench against painted blockwork, ceiling
# fluorescents + window sun, phenolic-resin bobs whose density matches the
# simulated 0.26 kg (see make_pendulums), scanned props.

ASSET_DIR = _pcve_asset('polyhaven/twin_pendulum_collision')
# Poly Haven publishes concrete_block_wall as a 2 m x 2 m scan.
BLOCK_WALL_M = 2.0
# Room layout (metres). The bench is a wall bench: its top runs back to the
# blockwork, so no floor or wall base shows between bench and wall.
WALL_Y = .62
ROOM_X = (-2.4, 2.4)
ROOM_FRONT_Y = -3.3
CEILING_Z = 3.0
# Window in the left wall, in front of the bench; the camera never sees it.
WINDOW_Y = (-2.5, -.55)
WINDOW_Z = (1.0, 2.45)
# Low morning sun through that window, travelling towards +x/+y and down. It
# enters the opening and lands on the bench around the apparatus.
SUN_DIRECTION = (.75, .40, -.35)
SUN_STRENGTH = 2.0
SKY_STRENGTH = .8
BATTEN_STRENGTH = 55.0
EXPOSURE = -.5
# Minimum clearance between any added prop and a moving body (sphere + rod).
PROP_CLEARANCE_M = .02


# --------------------------------------------------------------------------
# materials

def _principled(bpy, name, color, roughness=.5, metal=0., coat=0., coat_roughness=.05):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, 1.)
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, 1.)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metal
    if coat:
        set_shader_input(bsdf, 'Coat Weight', coat)
        set_shader_input(bsdf, 'Coat Roughness', coat_roughness)
    return mat, mat.node_tree.nodes, mat.node_tree.links, bsdf


def material(bpy, name, color, roughness=.5, metal=0., coat=0.):
    return _principled(bpy, name, color, roughness, metal, coat)[0]


def _noise(nodes, links, vector, scale, detail=3., roughness=.5):
    node = nodes.new('ShaderNodeTexNoise')
    node.inputs['Scale'].default_value = scale
    node.inputs['Detail'].default_value = detail
    node.inputs['Roughness'].default_value = roughness
    links.new(vector, node.inputs['Vector'])
    return node.outputs['Fac']


def _range(nodes, links, value, low, high, from_low=0., from_high=1.):
    node = nodes.new('ShaderNodeMapRange')
    node.inputs['From Min'].default_value = from_low
    node.inputs['From Max'].default_value = from_high
    node.inputs['To Min'].default_value = low
    node.inputs['To Max'].default_value = high
    links.new(value, node.inputs['Value'])
    return node.outputs['Result']


def _bump(nodes, links, height, strength, distance, normal=None):
    node = nodes.new('ShaderNodeBump')
    node.inputs['Strength'].default_value = strength
    node.inputs['Distance'].default_value = distance
    links.new(height, node.inputs['Height'])
    if normal is not None:
        links.new(normal, node.inputs['Normal'])
    return node.outputs['Normal']


def worked_metal(bpy, name, color, roughness, metal=1., scale=900., spread=.06, bump_distance=.000004, stretch=None):
    """Metal with a little roughness drift and fine machining relief."""
    mat, nodes, links, bsdf = _principled(bpy, name, color, roughness, metal)
    vector = nodes.new('ShaderNodeTexCoord').outputs['Object']
    if stretch:
        mapping = nodes.new('ShaderNodeMapping')
        mapping.inputs['Scale'].default_value = stretch
        links.new(vector, mapping.inputs['Vector'])
        vector = mapping.outputs['Vector']
    fine = _noise(nodes, links, vector, scale, 4., .55)
    links.new(_range(nodes, links, fine, roughness - spread, roughness + spread), bsdf.inputs['Roughness'])
    links.new(_bump(nodes, links, fine, .25, bump_distance), bsdf.inputs['Normal'])
    return mat


def hammertone(bpy, name, color):
    """Hammer-finish enamel, the stoved paint of cast lab apparatus bases."""
    mat, nodes, links, bsdf = _principled(bpy, name, color, .36, .35)
    vector = nodes.new('ShaderNodeTexCoord').outputs['Object']
    cells = nodes.new('ShaderNodeTexVoronoi')
    cells.feature = 'SMOOTH_F1'
    cells.inputs['Scale'].default_value = 210.
    links.new(vector, cells.inputs['Vector'])
    tone = nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].color = (*(c * .82 for c in color), 1.)
    tone.color_ramp.elements[1].color = (*(min(1., c * 1.10) for c in color), 1.)
    links.new(cells.outputs['Distance'], tone.inputs['Fac'])
    links.new(tone.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(_bump(nodes, links, cells.outputs['Distance'], .22, .0006), bsdf.inputs['Normal'])
    return mat


def epoxy_worktop(bpy):
    """Black epoxy-resin lab bench top: satin, wiped, lightly scratched."""
    base = (.017, .018, .019)
    mat, nodes, links, bsdf = _principled(bpy, 'Black epoxy resin worktop', base, .34)
    coord = nodes.new('ShaderNodeTexCoord').outputs['Object']
    # Broad wipe marks and dried cleaning streaks change the sheen, not the colour.
    wipe = _noise(nodes, links, coord, 2.3, 6., .62)
    gloss = _range(nodes, links, wipe, .13, .32, .30, .70)
    # Fine scratches from years of apparatus being slid along the bench (mostly along x).
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (2.5, 90., 90.)
    links.new(coord, mapping.inputs['Vector'])
    streak = _noise(nodes, links, mapping.outputs['Vector'], 6., 2., .5)
    mask = nodes.new('ShaderNodeValToRGB')
    mask.color_ramp.elements[0].position = .70
    mask.color_ramp.elements[0].color = (0., 0., 0., 1.)
    mask.color_ramp.elements[1].position = .80
    mask.color_ramp.elements[1].color = (1., 1., 1., 1.)
    links.new(streak, mask.inputs['Fac'])
    rough = nodes.new('ShaderNodeMix')
    rough.data_type = 'FLOAT'
    links.new(mask.outputs['Color'], rough.inputs['Factor'])
    links.new(gloss, rough.inputs['A'])
    rough.inputs['B'].default_value = .45
    links.new(rough.outputs['Result'], bsdf.inputs['Roughness'])
    # Resin is filled with a little mineral; a faint speckle keeps it from reading as paint.
    speck = _noise(nodes, links, coord, 1400., 1., .5)
    tone = nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].position = .45
    tone.color_ramp.elements[0].color = (*base, 1.)
    tone.color_ramp.elements[1].position = .75
    tone.color_ramp.elements[1].color = (.034, .035, .036, 1.)
    links.new(speck, tone.inputs['Fac'])
    scuffed = nodes.new('ShaderNodeMixRGB')
    links.new(tone.outputs['Color'], scuffed.inputs['Color1'])
    scuffed.inputs['Color2'].default_value = (.055, .056, .058, 1.)
    fac = nodes.new('ShaderNodeMath')
    fac.operation = 'MULTIPLY'
    fac.inputs[1].default_value = .35
    links.new(mask.outputs['Color'], fac.inputs[0])
    links.new(fac.outputs['Value'], scuffed.inputs['Fac'])
    links.new(scuffed.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(_bump(nodes, links, mask.outputs['Color'], .04, .00008), bsdf.inputs['Normal'])
    return mat


def _scan(nodes, links, vector, stem, kind, colour):
    node = nodes.new('ShaderNodeTexImage')
    node.projection = 'BOX'
    node.projection_blend = .2
    path = ASSET_DIR / f'{stem}_{kind}_2k.jpg'
    if not path.is_file():
        raise FileNotFoundError(path)
    import bpy
    node.image = bpy.data.images.load(str(path), check_existing=True)
    if not colour:
        node.image.colorspace_settings.name = 'Non-Color'
    links.new(vector, node.inputs['Vector'])
    return node.outputs['Color']


def painted_blockwork(bpy, paint):
    """Concrete blockwork under two coats of eggshell paint.

    The Poly Haven concrete_block_wall scan supplies the relief (block faces,
    raked mortar joints, pores) and the sheen; the paint supplies the colour,
    keeping only a trace of the bare block's tonal variation where the paint
    film is thinner.
    """
    mat, nodes, links, bsdf = _principled(bpy, 'Painted concrete blockwork', paint, .7)
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1 / BLOCK_WALL_M,) * 3
    links.new(coord.outputs['Object'], mapping.inputs['Vector'])
    vector = mapping.outputs['Vector']
    grey = nodes.new('ShaderNodeRGBToBW')
    links.new(_scan(nodes, links, vector, 'concrete_block_wall', 'diff', True), grey.inputs['Color'])
    film = _range(nodes, links, grey.outputs['Val'], .80, 1.04, .02, .40)
    tinted = nodes.new('ShaderNodeVectorMath')
    tinted.operation = 'SCALE'
    tinted.inputs[0].default_value = paint
    links.new(film, tinted.inputs['Scale'])
    links.new(tinted.outputs['Vector'], bsdf.inputs['Base Color'])
    rough = _scan(nodes, links, vector, 'concrete_block_wall', 'rough', False)
    links.new(_range(nodes, links, rough, .52, .86), bsdf.inputs['Roughness'])
    normal = nodes.new('ShaderNodeNormalMap')
    normal.inputs['Strength'].default_value = .30
    links.new(_scan(nodes, links, vector, 'concrete_block_wall', 'nor_gl', False), normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def phenolic_resin(bpy, name, color):
    """Cast phenolic resin, the material of carom and pool balls.

    A 64 mm phenolic ball (about 1.8 g/cm3) weighs about 0.25 kg and has a
    coefficient of restitution around 0.92, which is what the simulation uses
    (0.26 kg, e = 0.92). A solid steel ball that size would weigh 1.08 kg.
    """
    mat, nodes, links, bsdf = _principled(bpy, name, color, .16, 0., coat=1., coat_roughness=.035)
    set_shader_input(bsdf, 'Specular IOR Level', .5)
    coord = nodes.new('ShaderNodeTexCoord').outputs['Object']
    # Handling marks: the polish is a little uneven, as on any ball that is touched.
    marks = _noise(nodes, links, coord, 34., 5., .6)
    links.new(_range(nodes, links, marks, .10, .24, .35, .70), bsdf.inputs['Roughness'])
    coat = _noise(nodes, links, coord, 60., 3., .5)
    socket = bsdf.inputs['Coat Roughness'] if 'Coat Roughness' in bsdf.inputs else None
    if socket is not None:
        links.new(_range(nodes, links, coat, .02, .07, .3, .7), socket)
    return mat


# --------------------------------------------------------------------------
# geometry helpers

def _box_mesh(bpy, name, size):
    """A real-size box mesh, so Object texture coordinates are in metres."""
    x, y, z = (v / 2 for v in size)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z),
                      (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)], [],
                     [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    mesh.update()
    return mesh


def box(bpy, name, center, size, mat, bevel=0.):
    obj = bpy.data.objects.new(name, _box_mesh(bpy, name, size))
    bpy.context.scene.collection.objects.link(obj)
    obj.location = center
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new('Manufactured edge', 'BEVEL')
        mod.width = bevel
        mod.segments = 3
        obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return obj


def span(bpy, name, low, high, mat, bevel=0.):
    """Box from its lower and upper corners."""
    return box(bpy, name, [(a + b) / 2 for a, b in zip(low, high)], [b - a for a, b in zip(low, high)], mat, bevel)


def rod(bpy, name, start, end, radius, mat, vertices=32):
    from mathutils import Vector
    a, b = Vector(start), Vector(end)
    delta = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=1, location=(a + b) / 2)
    obj = bpy.context.object
    obj.name = name
    obj.scale.z = delta.length
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = delta.to_track_quat('Z', 'Y')
    obj.data.materials.append(mat)
    for face in obj.data.polygons:
        face.use_smooth = True
    bevel = obj.modifiers.new('Machined edge radius', 'BEVEL')
    bevel.width = min(radius * .12, .0006)
    bevel.segments = 3
    return obj


def text(bpy, name, body, location, size, mat, rotation=(math.pi / 2, 0, 0)):
    bpy.ops.object.text_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.data.body = body
    obj.data.size = size
    obj.data.extrude = .000015
    obj.data.materials.append(mat)
    return obj


def import_model(bpy, asset_id, location, yaw_deg=0., label=None, tilt_deg=0., scale=1.):
    """Place a Poly Haven glTF with its bounding-box bottom centre on ``location``.

    Poly Haven models face -Y and stand on z = 0. ``tilt_deg`` turns the asset
    about X first (-90 lays an upright object face-up), ``scale`` corrects an
    asset that is not published at real size; the bounding box is measured
    after both, so the asset always rests on ``location``. The import is
    re-parented under one empty so the whole asset turns about its own centre.
    """
    from mathutils import Matrix, Vector
    path = ASSET_DIR / asset_id / f'{asset_id}_1k.gltf'
    if not path.is_file():
        raise FileNotFoundError(path)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [obj for obj in bpy.data.objects if obj not in before]
    meshes = [obj for obj in new if obj.type == 'MESH']
    if not meshes:
        raise RuntimeError(f'{asset_id} has no mesh')
    root = bpy.data.objects.new(label or asset_id, None)
    bpy.context.scene.collection.objects.link(root)
    for obj in meshes:
        obj['prop_group'] = root.name
    bpy.context.view_layer.update()
    for obj in new:
        if obj.parent not in new:
            world = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_parent_inverse = Matrix.Identity(4)
            obj.matrix_world = world
    bpy.context.view_layer.update()
    pre = Matrix.Rotation(math.radians(tilt_deg), 4, 'X') @ Matrix.Scale(scale, 4)
    corners = [pre @ obj.matrix_world @ Vector(c) for obj in meshes for c in obj.bound_box]
    low = Vector([min(c[i] for c in corners) for i in range(3)])
    high = Vector([max(c[i] for c in corners) for i in range(3)])
    anchor = Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, low.z))
    root.matrix_world = (Matrix.Translation(Vector(location)) @ Matrix.Rotation(math.radians(yaw_deg), 4, 'Z')
                         @ Matrix.Translation(-anchor) @ pre)
    bpy.context.view_layer.update()
    return meshes


def world_bounds(objs):
    from mathutils import Vector
    corners = [obj.matrix_world @ Vector(c) for obj in objs for c in obj.bound_box]
    return (Vector([min(c[i] for c in corners) for i in range(3)]),
            Vector([max(c[i] for c in corners) for i in range(3)]))


# --------------------------------------------------------------------------
# room, bench and apparatus

def _socket_outlet(bpy, x, z, mats):
    """Surface-mounted metal-clad twin socket outlet (146 x 86 mm), as fitted in labs."""
    y = WALL_Y
    span(bpy, 'Socket back box', (x - .073, y - .038, z - .043), (x + .073, y, z + .043), mats['galvanised'], bevel=.004)
    span(bpy, 'Socket front plate', (x - .071, y - .041, z - .041), (x + .071, y - .037, z + .041), mats['galvanised'], bevel=.002)
    for dx in (-.036, .036):
        span(bpy, 'Socket insert', (x + dx - .028, y - .043, z - .030), (x + dx + .028, y - .040, z + .030), mats['outlet_white'], bevel=.002)
        for px, pz, w, h in ((0, .012, .005, .009), (-.011, -.009, .009, .005), (.011, -.009, .009, .005)):
            span(bpy, 'Socket pin slot', (x + dx + px - w / 2, y - .0436, z + pz - h / 2),
                 (x + dx + px + w / 2, y - .0428, z + pz + h / 2), mats['slot'])
        span(bpy, 'Socket rocker switch', (x + dx + .016, y - .049, z + .012), (x + dx + .025, y - .043, z + .026), mats['rocker'], bevel=.0012)


def _room(bpy, scene, mats):
    x0, x1 = ROOM_X
    wall = mats['wall_plaster']
    # Floor, ceiling and the plain plastered walls the camera never sees. They
    # close the room so the light has something to bounce off.
    span(bpy, 'Vinyl floor', (x0 - .2, ROOM_FRONT_Y - .2, -.05), (x1 + .2, WALL_Y + .3, 0.), mats['vinyl'])
    span(bpy, 'Ceiling', (x0 - .2, ROOM_FRONT_Y - .2, CEILING_Z), (x1 + .2, WALL_Y + .3, CEILING_Z + .12), mats['ceiling'])
    span(bpy, 'Right wall', (x1, ROOM_FRONT_Y - .2, -.05), (x1 + .15, WALL_Y + .3, CEILING_Z + .1), wall)
    span(bpy, 'Wall behind camera', (x0 - .2, ROOM_FRONT_Y - .15, -.05), (x1 + .2, ROOM_FRONT_Y, CEILING_Z + .1), wall)
    # Left wall with a real opening for the window.
    (wy0, wy1), (wz0, wz1) = WINDOW_Y, WINDOW_Z
    for name, low, high in (('Left wall below window', (x0 - .15, ROOM_FRONT_Y - .2, -.05), (x0, WALL_Y + .3, wz0)),
                            ('Left wall above window', (x0 - .15, ROOM_FRONT_Y - .2, wz1), (x0, WALL_Y + .3, CEILING_Z + .1)),
                            ('Left wall front pier', (x0 - .15, ROOM_FRONT_Y - .2, wz0), (x0, wy0, wz1)),
                            ('Left wall rear pier', (x0 - .15, wy1, wz0), (x0, WALL_Y + .3, wz1))):
        span(bpy, name, low, high, wall)
    frame = mats['window_frame']
    span(bpy, 'Window sill', (x0 - .15, wy0, wz0 - .02), (x0 + .05, wy1, wz0), frame, bevel=.003)
    for y in (wy0, (wy0 + wy1) / 2, wy1):
        span(bpy, 'Window mullion', (x0 - .10, y - .03, wz0), (x0 - .04, y + .03, wz1), frame, bevel=.002)
    for z in (wz0, wz0 + .95, wz1):
        span(bpy, 'Window transom', (x0 - .10, wy0, z - .03), (x0 - .04, wy1, z + .03), frame, bevel=.002)
    ground = span(bpy, 'Ground outside', (-40, -40, -.4), (40, 40, -.2), mats['paving'])
    ground.visible_camera = False
    # The back wall: painted blockwork, the bench runs back to it.
    span(bpy, 'Back wall blockwork', (x0 - .2, WALL_Y, -.05), (x1 + .2, WALL_Y + .2, CEILING_Z + .1), mats['blockwork'])


def _bench(bpy, mats):
    top = TABLE_HEIGHT
    x0, x1 = ROOM_X
    # 25 mm epoxy top from the left wall to beyond the right edge of frame, with
    # the 100 mm epoxy upstand that seals it to the wall.
    span(bpy, 'Epoxy resin worktop', (x0 + .002, -.50, top - .025), (1.90, WALL_Y, top), mats['epoxy'], bevel=.003)
    span(bpy, 'Epoxy upstand', (x0 + .002, WALL_Y - .012, top), (1.90, WALL_Y, top + .10), mats['epoxy'], bevel=.002)
    span(bpy, 'Bench carcass', (x0 + .02, -.44, .10), (1.86, WALL_Y, top - .025), mats['carcass'])
    span(bpy, 'Bench plinth', (x0 + .02, -.40, 0.), (1.86, WALL_Y, .10), mats['plinth'])
    # Two metal-clad twin outlets on the blockwork above the upstand.
    for x in (-.98, .90):
        _socket_outlet(bpy, x, top + .25, mats)


def _apparatus(bpy, mats):
    """The demonstrator: a hammer-finish cast base, stainless frame and pivots."""
    top = TABLE_HEIGHT
    steel, brass, black, base = mats['steel'], mats['brass'], mats['anodised'], mats['hammertone']
    for x in (-.355, .355):
        for y in (-.11, .11):
            rod(bpy, 'Adjustable rubber foot', [x, y, top], [x, y, top + .010], .018, mats['rubber'])
    box(bpy, 'Instrument cast base', [0, 0, top + .025], [.85, .31, .036], base, bevel=.009)
    box(bpy, 'Brushed aluminium inset', [0, -.010, top + .044], [.80, .26, .003], mats['aluminium'], bevel=.004)
    for x in (-.375, .375):
        for y in (-.095, .095):
            rod(bpy, 'Stand mounting collar', [x, y, top + .046], [x, y, top + .064], .018, brass)
            rod(bpy, 'Stainless upright', [x, y, top + .060], [x, y, PIVOT_HEIGHT + .050], .008, steel)
        rod(bpy, 'Rounded top cross member', [x, -.095, PIVOT_HEIGHT + .050], [x, .095, PIVOT_HEIGHT + .050], .008, steel)
    for y in (-.095, .095):
        rod(bpy, 'Upper horizontal rail', [-.375, y, PIVOT_HEIGHT + .050], [.375, y, PIVOT_HEIGHT + .050], .008, steel)
    for i, pivot in enumerate(PIVOTS):
        x, _, z = pivot
        box(bpy, f'Pivot bridge {i}', [x, 0, z + .050], [.026, .20, .018], black, bevel=.003)
        for y in (-.018, .018):
            box(bpy, f'Bearing lug {i}', [x, y, z + .014], [.020, .009, .041], brass, bevel=.003)
        rod(bpy, f'Pivot pin {i}', [x, -.027, z], [x, .027, z], .0035, steel)
        for y in (-.030, .030):
            rod(bpy, f'Pivot pin nut {i}', [x, y - .002, z], [x, y + .002, z], .0058, brass, vertices=6)
        # Permanent identity labels; no visual edits indicate a changed mass.
        text(bpy, f'Pivot identification {i}', 'A' if i == 0 else 'B', [x - .004, -.106, z + .044], .011, mats['engraving'])
    for x in (-.395, .395):
        for y in (-.12, .12):
            rod(bpy, 'Recessed base screw', [x, y, top + .045], [x, y, top + .048], .0045, black, vertices=6)
    # Engraved scale on the inset and the maker's plate on the front of the base.
    for i in range(71):
        x = -.35 + i * .01
        length = .010 if i % 5 == 0 else .005
        box(bpy, 'Etched millimetre tick', [x, -.119 + length / 2, top + .0456], [.00045, length, .00008], black)
    box(bpy, 'Anodised nameplate', [0, -.1555, top + .025], [.24, .001, .023], black, bevel=.002)
    text(bpy, 'Nameplate engraving', 'COUPLED PENDULUMS', [-.103, -.1562, top + .021], .012, mats['engraving'])


def _results_sheet(bpy, location, yaw_deg):
    """A loose A4 results sheet with a ruled table, lying flat on the bench top."""
    from mathutils import Matrix
    paper = material(bpy, 'Results sheet paper', (.80, .79, .74), .82)
    ink = material(bpy, 'Printed rule ink', (.16, .18, .22), .7)
    root = bpy.data.objects.new('Results sheet', None)
    bpy.context.scene.collection.objects.link(root)
    root.matrix_world = Matrix.Translation(location) @ Matrix.Rotation(math.radians(yaw_deg), 4, 'Z')
    parts = [span(bpy, 'Results sheet paper', (-.105, -.1485, 0.), (.105, .1485, .0002), paper)]
    for i in range(13):
        y = -.120 + i * .019
        parts.append(span(bpy, 'Results sheet rule', (-.090, y - .0002, .0002), (.090, y + .0002, .00023), ink))
    for x in (-.090, -.045, .015, .090):
        parts.append(span(bpy, 'Results sheet column rule', (x - .0002, -.120, .0002), (x + .0002, .108, .00023), ink))
    for obj in parts:
        obj.parent = root
        obj['prop_group'] = root.name
    bpy.context.view_layer.update()
    return parts


def _props(bpy):
    """Things a lab bench collects. Each one sits on the bench top by its own bounding box."""
    top = TABLE_HEIGHT
    props = []
    # Poly Haven publishes classic_laptop 652 mm wide, about twice a real
    # 1990s notebook; it is scaled to a 310 mm wide machine.
    props += import_model(bpy, 'classic_laptop', (.60, .37, top), yaw_deg=14., label='Data-logging laptop', scale=.31 / .652)
    props += _results_sheet(bpy, (-.74, .27, top), -14.)
    # A pocket watch for timing the swings, lying face up beside the sheet.
    props += import_model(bpy, 'pocket_watch', (-.56, .04, top), yaw_deg=24., label='Pocket watch', tilt_deg=-90.)
    return props


def _lights(bpy, scene):
    from mathutils import Vector
    world = bpy.data.worlds.new('Morning sky outside the lab')
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    sky = nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'NISHITA'
    sky.sun_disc = False
    direction = -Vector(SUN_DIRECTION).normalized()
    sky.sun_elevation = math.asin(direction.z)
    # Nishita's sun azimuth is measured from +Y towards -X (counter-clockwise about Z).
    sky.sun_rotation = math.atan2(-direction.x, direction.y)
    sky.air_density, sky.dust_density = 1., 1.5
    links.new(sky.outputs['Color'], nodes['Background'].inputs['Color'])
    nodes['Background'].inputs['Strength'].default_value = SKY_STRENGTH
    sun = bpy.data.lights.new('Morning sun', 'SUN')
    sun.energy = SUN_STRENGTH
    sun.angle = math.radians(.53)
    sun.color = (1., .93, .84)
    obj = bpy.data.objects.new('Morning sun', sun)
    scene.collection.objects.link(obj)
    obj.rotation_euler = Vector(SUN_DIRECTION).to_track_quat('-Z', 'Y').to_euler()
    # Portal in the window opening so the sky light is sampled efficiently.
    (wy0, wy1), (wz0, wz1) = WINDOW_Y, WINDOW_Z
    data = bpy.data.lights.new('Window sky portal', 'AREA')
    data.shape = 'RECTANGLE'
    data.size, data.size_y = wy1 - wy0, wz1 - wz0
    data.cycles.is_portal = True
    portal = bpy.data.objects.new('Window sky portal', data)
    scene.collection.objects.link(portal)
    portal.location = (ROOM_X[0] - .16, (wy0 + wy1) / 2, (wz0 + wz1) / 2)
    portal.rotation_euler = Vector((1., 0., 0.)).to_track_quat('-Z', 'Y').to_euler()
    # Two surface-mounted fluorescent battens with opal diffusers; the diffuser is the emitter.
    housing = material(bpy, 'Batten housing', (.78, .78, .76), .45)
    mat, nodes, links, bsdf = _principled(bpy, 'Opal batten diffuser', (.92, .92, .92), .5)
    set_shader_input(bsdf, 'Emission Color', (1., .96, .90, 1.))
    set_shader_input(bsdf, 'Emission Strength', BATTEN_STRENGTH)
    for y in (-.15, -1.85):
        span(bpy, 'Fluorescent batten housing', (-1.05, y - .08, CEILING_Z - .07), (.55, y + .08, CEILING_Z), housing, bevel=.004)
        diffuser = box(bpy, 'Fluorescent batten diffuser', (-.25, y, CEILING_Z - .08), (1.56, .13, .03), mat, bevel=.008)
        diffuser.visible_shadow = False


def build_environment(bpy, scene):
    mats = dict(
        epoxy=epoxy_worktop(bpy),
        blockwork=painted_blockwork(bpy, (.56, .555, .52)),
        wall_plaster=material(bpy, 'Matt emulsion plaster', (.60, .60, .57), .85),
        ceiling=material(bpy, 'Ceiling tile white', (.72, .72, .70), .9),
        vinyl=worked_metal(bpy, 'Grey sheet vinyl floor', (.20, .21, .21), .55, metal=0., scale=60., spread=.12, bump_distance=.0001),
        carcass=material(bpy, 'Light grey cabinet melamine', (.45, .46, .46), .45),
        plinth=material(bpy, 'Black vinyl plinth', (.02, .02, .02), .6),
        window_frame=material(bpy, 'White powder coated aluminium', (.70, .70, .68), .4),
        paving=material(bpy, 'Paving outside', (.24, .23, .21), .9),
        galvanised=worked_metal(bpy, 'Galvanised steel', (.50, .52, .53), .38, metal=1., scale=180., spread=.10, bump_distance=.00002),
        outlet_white=material(bpy, 'White outlet moulding', (.68, .68, .65), .32),
        slot=material(bpy, 'Socket slot shadow', (.004, .004, .004), .9),
        rocker=material(bpy, 'Red rocker switch', (.32, .02, .015), .3),
        steel=worked_metal(bpy, 'Satin stainless steel', (.62, .62, .61), .20, scale=1200., spread=.05, bump_distance=.000003, stretch=(1., 1., 30.)),
        brass=worked_metal(bpy, 'Machined brass', (.78, .56, .30), .24, scale=800., spread=.06, bump_distance=.000006),
        aluminium=worked_metal(bpy, 'Brushed aluminium', (.80, .80, .80), .30, scale=600., spread=.08, bump_distance=.000004, stretch=(1., 60., 1.)),
        anodised=material(bpy, 'Black anodised aluminium', (.025, .025, .027), .36, metal=.6),
        hammertone=hammertone(bpy, 'Grey hammer-finish enamel', (.30, .33, .35)),
        rubber=material(bpy, 'Black rubber', (.015, .016, .017), .78),
        engraving=material(bpy, 'Engraved bright metal', (.70, .70, .68), .35, metal=1.),
    )
    _room(bpy, scene, mats)
    _bench(bpy, mats)
    _apparatus(bpy, mats)
    mats['props'] = _props(bpy)
    _lights(bpy, scene)
    scene.view_settings.exposure = EXPOSURE
    return mats


def make_pendulums(bpy, mats, first_frame):
    """Phenolic-resin bobs on stainless rods.

    The simulated bob is a 64 mm sphere of 0.26 kg (density 1.9 g/cm3) with a
    pair restitution of 0.92: cast phenolic resin, not steel, is the real
    material with those numbers, so the bobs are rendered as phenolic balls.
    """
    from mathutils import Vector
    balls, rods, moving = {}, {}, []
    for index, key in enumerate(KEYS):
        if not first_frame[key]['present']:
            continue
        bobmat = phenolic_resin(bpy, key + ' phenolic resin', (.34, .030, .022))
        bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=BOB_RADIUS)
        ball = bpy.context.object
        ball.name = key
        ball.data.materials.append(bobmat)
        for face in ball.data.polygons:
            face.use_smooth = True
        balls[key] = ball
        # A threaded brass insert is set into the top of the ball for the rod.
        boss = rod(bpy, key + ' threaded socket', [0, 0, BOB_RADIUS - .002], [0, 0, BOB_RADIUS + .006], .0042, mats['brass'])
        boss.parent = ball
        rods[key] = rod(bpy, key + ' suspension rod', PIVOTS[index],
                        Vector(first_frame[key]['location']) + Vector([0, 0, BOB_RADIUS]), .0011, mats['steel'])
        # The hinge eye shares the pendulum's local upward direction.
        bpy.ops.mesh.primitive_torus_add(major_radius=.0042, minor_radius=.0012, major_segments=24, minor_segments=8,
                                        location=[0, 0, LENGTH], rotation=[math.pi / 2, 0, 0])
        eye = bpy.context.object
        eye.name = key + ' pivot eye'
        eye.data.materials.append(mats['brass'])
        eye.parent = ball
        moving.extend([ball, rods[key], boss, eye])
    return balls, rods, moving


# --------------------------------------------------------------------------
# prop checks

def _box_distance(low, high, point):
    return math.sqrt(sum(max(low[i] - point[i], 0., point[i] - high[i]) ** 2 for i in range(3)))


def verify_props(bpy, scene, camera, data, props, balls, rods):
    """Raise if a prop comes within PROP_CLEARANCE_M of a moving body or hides one.

    Clearance is checked twice: against this case's replayed trajectory (bob
    sphere plus its socket and eye, and the rod sampled along its length), and
    against the envelope of every swing the scenario limits allow (each bob
    stays within LENGTH + BOB_RADIUS of its pivot in the y = 0 swing plane), so
    a prop that passes here also passes for every edit case. Line of sight is
    checked by ray casts from the camera to points on each bob and rod.
    """
    from mathutils import Vector
    groups = {}
    for obj in props:
        groups.setdefault(obj.get('prop_group', obj.name), []).append(obj)
    bounds = {name: world_bounds(objs) for name, objs in groups.items()}
    # Props stand on the bench top, apart from each other and from the apparatus base.
    names = sorted(bounds)
    footprint = ((-.43, -.16, TABLE_HEIGHT), (.43, .16, PIVOT_HEIGHT + .06))
    for n, name in enumerate(names):
        low, high = bounds[name]
        if abs(low.z - TABLE_HEIGHT) > .003:
            raise RuntimeError(f'Prop {name} does not rest on the bench top (bottom at {low.z:.4f} m)')
        others = [(other, bounds[other]) for other in names[n + 1:]] + [('apparatus base', footprint)]
        for other, (olow, ohigh) in others:
            if all(low[i] < ohigh[i] and olow[i] < high[i] for i in range(3)):
                raise RuntimeError(f'Prop {name} overlaps {other}')
    reach = BOB_RADIUS + .010
    worst = (float('inf'), None, None)
    for frame in data['frames']:
        for i, key in enumerate(KEYS):
            state = frame[key]
            if not state['present']:
                continue
            centre = state['location']
            pivot = PIVOTS[i]
            samples = [(centre, reach)] + [([p + (c - p) * t / 16 for p, c in zip(pivot, centre)], .002) for t in range(17)]
            for name, (low, high) in bounds.items():
                for point, radius in samples:
                    gap = _box_distance(low, high, point) - radius
                    if gap < worst[0]:
                        worst = (gap, name, frame['frame_index'])
    if worst[0] < PROP_CLEARANCE_M:
        raise RuntimeError(f'Prop {worst[1]} is {worst[0]:.4f} m from a moving body at frame {worst[2]}')
    band = BOB_RADIUS + .010 + PROP_CLEARANCE_M
    for name, (low, high) in bounds.items():
        if low.y < band and high.y > -band:
            for pivot in PIVOTS:
                if _box_distance(low, high, pivot) < LENGTH + band:
                    raise RuntimeError(f'Prop {name} lies inside the swing envelope of a pendulum')
    allowed = set()
    for key, ball in balls.items():
        allowed.update([ball.name, rods[key].name, *(child.name for child in ball.children_recursive)])
    prop_names = {obj.name for obj in props}
    origin = camera.matrix_world.translation.copy()
    right = camera.matrix_world.to_3x3() @ Vector((1., 0., 0.))
    up = camera.matrix_world.to_3x3() @ Vector((0., 1., 0.))
    rays = 0
    for frame in data['frames']:
        scene.frame_set(frame['frame_index'])
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for i, key in enumerate(KEYS):
            if key not in balls or not frame[key]['present']:
                continue
            centre = Vector(frame[key]['location'])
            pivot = Vector(PIVOTS[i])
            targets = [centre + (right * dx + up * dz) * .6 * BOB_RADIUS for dx, dz in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))]
            targets += [pivot + (centre - pivot) * t for t in (.35, .6, .85)]
            for target in targets:
                direction = target - origin
                hit, _, _, _, obj, _ = scene.ray_cast(depsgraph, origin, direction.normalized(), distance=direction.length - 1e-4)
                rays += 1
                if hit and obj.name in prop_names:
                    raise RuntimeError(f'Prop {obj.name} hides {key} at frame {frame["frame_index"]}')
    print(f'[look] props clear of moving bodies by >= {worst[0]:.3f} m; {rays} line-of-sight rays unobstructed', flush=True)
    return dict(min_prop_clearance_m=worst[0], line_of_sight_rays=rays)
