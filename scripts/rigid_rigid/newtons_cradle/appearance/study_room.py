"""A mid-century home study built to measure around the cradle's desk.

The room is built from ordinary parts at their real sizes:

* a rosewood-veneered writing desk (1.70 x 0.80 m, 28 mm top on tapered legs)
  whose top face is the table height the cradle stands on;
* plaster walls in a deep slate paint, a parquet floor and a white ceiling,
  all from Poly Haven CC0 scans tiled at their measured size;
* a real window cut through the left wall. A low afternoon sun comes in
  through it and lays a patch across the desk and the cradle; the back wall
  and the sideboard stay in the shade. A second window behind the camera only
  adds sky light and is what the chrome balls reflect on their camera side.
  No lamp is hidden anywhere in the room.

Nothing in here takes part in the simulation.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from pcve_assets import asset as _pcve_asset

# One folder per Poly Haven asset.
TEXTURES = _pcve_asset('polyhaven/newtons_cradle')

# Room: inner faces of the four walls and the ceiling height (metres).
ROOM_X = (-2.60, 2.40)
ROOM_Y = (-3.20, 1.60)
CEILING_M = 2.75
WALL_THICK_M = .20

# Openings as (along-wall span, z span) on their wall.
LEFT_WINDOW = dict(span=(-.90, 1.20), z=(.80, 2.40))     # wall x = ROOM_X[0]
RIGHT_WINDOW = dict(span=(-2.70, -1.10), z=(.85, 2.30))  # wall x = ROOM_X[1], behind the camera

# Writing desk: top outline and thickness. The top face is table_height.
DESK_X = (-1.05, .65)
DESK_Y = (-.42, .40)
DESK_TOP_THICK_M = .028

# Real sizes of the Poly Haven scans (api.polyhaven.com/info "dimensions").
ROSEWOOD_TILE_M = 2.43      # rosewood_veneer1
WALL_TILE_M = 3.20          # plastered_wall_04
PARQUET_TILE_M = 2.25       # rectangular_parquet

# Afternoon sun, low enough to reach the desk through the left window.
# SUN_AZIMUTH_DEG is the compass direction *towards* the sun, in degrees from
# +x towards +y: the light comes in from the left (-x) and a little from behind
# (+y), so the back wall and the sideboard stay out of the direct sun.
SUN_ELEVATION_DEG = 25.0
SUN_AZIMUTH_DEG = 160.0
SUN_STRENGTH = 3.6
SKY_STRENGTH = 1.0
# AgX exposure: the sun patch on the desk sits about two stops over the shaded
# back of the room, as a phone exposes a sunlit interior.
EXPOSURE = 1.0


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


def tapered_leg(name, x, y, z0, z1, top_side, bottom_side, mat):
    """A square leg that tapers from ``top_side`` under the apron to
    ``bottom_side`` at the floor, built in world coordinates."""
    import bpy
    import bmesh
    from mathutils import Vector
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.)
    for v in bm.verts:
        side = top_side if v.co.z > 0 else bottom_side
        v.co = Vector((x + v.co.x * side, y + v.co.y * side, z1 if v.co.z > 0 else z0))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    mesh.materials.append(mat)
    mod = obj.modifiers.new('Eased edges', 'BEVEL')
    mod.width, mod.segments, mod.limit_method = .002, 2, 'ANGLE'
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
        node.image = bpy.data.images.load(str(TEXTURES / stem / f'{stem}_{kind}_2k.jpg'), check_existing=True)
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


def scanned(name, stem, tile_m, base=(.5, .5, .5), **options):
    """A scan box-projected in world metres (every room part is built at the
    origin), so floor boards and wall plaster keep their real size everywhere."""
    mat = principled(name, base, .5)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1 / tile_m,) * 3
    links.new(coord.outputs['Object'], mapping.inputs['Vector'])
    _scan_nodes(mat, stem, mapping.outputs['Vector'], projection='BOX', **options)
    return mat


def rosewood_veneer(name, length_axis='X'):
    """Lacquered rosewood veneer with the grain running along ``length_axis``.

    The scan's grain runs along its v axis; v follows the board's length and
    u the other two world axes, so the grain stays straight over the top and
    round the 28 mm edge. A thin satin lacquer coat sits over the scanned
    roughness, as on a factory-finished desk.
    """
    mat = principled(name, (.25, .11, .06), .4)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coord = nodes.new('ShaderNodeTexCoord')
    xyz = nodes.new('ShaderNodeSeparateXYZ')
    links.new(coord.outputs['Object'], xyz.inputs['Vector'])
    across = [axis for axis in 'XYZ' if axis != length_axis]
    add = nodes.new('ShaderNodeMath')
    add.operation = 'ADD'
    links.new(xyz.outputs[across[0]], add.inputs[0])
    links.new(xyz.outputs[across[1]], add.inputs[1])
    uv = nodes.new('ShaderNodeCombineXYZ')
    scale_u = nodes.new('ShaderNodeMath')
    scale_u.operation = 'DIVIDE'
    links.new(add.outputs['Value'], scale_u.inputs[0])
    scale_u.inputs[1].default_value = ROSEWOOD_TILE_M
    scale_v = nodes.new('ShaderNodeMath')
    scale_v.operation = 'DIVIDE'
    links.new(xyz.outputs[length_axis], scale_v.inputs[0])
    scale_v.inputs[1].default_value = ROSEWOOD_TILE_M
    links.new(scale_u.outputs['Value'], uv.inputs['X'])
    links.new(scale_v.outputs['Value'], uv.inputs['Y'])
    _scan_nodes(mat, 'rosewood_veneer1', uv.outputs['Vector'], tint=(.92, .86, .82),
                rough_range=(.28, .46), normal_strength=.35)
    bsdf = nodes['Principled BSDF']
    bsdf.inputs['Coat Weight'].default_value = .35
    bsdf.inputs['Coat Roughness'].default_value = .16
    return mat


def painted(name, color, roughness=.42, brush=True):
    """Eggshell paint: one colour that drifts a little in tone and sheen."""
    mat = principled(name, color, roughness)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    position = nodes.new('ShaderNodeNewGeometry')
    drift = nodes.new('ShaderNodeTexNoise')
    drift.inputs['Scale'].default_value = 1.6
    drift.inputs['Detail'].default_value = 3.
    links.new(position.outputs['Position'], drift.inputs['Vector'])
    tone = nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].color = (*(c * .95 for c in color), 1)
    tone.color_ramp.elements[1].color = (*(min(1., c * 1.03) for c in color), 1)
    links.new(drift.outputs['Fac'], tone.inputs['Fac'])
    links.new(tone.outputs['Color'], bsdf.inputs['Base Color'])
    sheen = nodes.new('ShaderNodeMapRange')
    sheen.inputs['To Min'].default_value = roughness - .06
    sheen.inputs['To Max'].default_value = min(1., roughness + .06)
    links.new(drift.outputs['Fac'], sheen.inputs['Value'])
    links.new(sheen.outputs['Result'], bsdf.inputs['Roughness'])
    return mat


def thin_glass():
    """Float glass shaded thin: Fresnel reflection over a transparent layer.

    Cycles' Fresnel node inverts the IOR on back faces, which would turn a
    pane seen obliquely from inside black by total internal reflection;
    feeding 1/1.52 on back faces cancels that.
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


def window(name, side, span, z, frame_paint, sill_mat):
    """A timber casement set in the middle of a wall reveal at x = const:
    frame, one mullion, a transom, thin glass and an interior window board.
    ``side`` is -1 for the left wall (ROOM_X[0]) or +1 for the right one."""
    (s0, s1), (z0, z1) = span, z
    face = ROOM_X[0] if side < 0 else ROOM_X[1]
    outward = side
    depth = tuple(sorted((face + outward * .07, face + outward * .12)))

    def part(label, a0, a1, c0, c1, d=depth, mat=frame_paint, bevel=.001):
        return box(f'{name} {label}', (d[0], a0, c0), (d[1], a1, c1), mat, bevel)

    bar = .058
    part('head', s0, s1, z1 - bar, z1)
    part('bottom rail', s0, s1, z0, z0 + bar)
    part('near jamb', s0, s0 + bar, z0 + bar, z1 - bar)
    part('far jamb', s1 - bar, s1, z0 + bar, z1 - bar)
    mid = (s0 + s1) / 2
    inner = (depth[0] + .004, depth[1] - .004)
    part('mullion', mid - .025, mid + .025, z0 + bar, z1 - bar, inner)
    transom = z1 - .42
    part('transom near', s0 + bar, mid - .025, transom - .022, transom + .022, inner)
    part('transom far', mid + .025, s1 - bar, transom - .022, transom + .022, inner)
    centre = (depth[0] + depth[1]) / 2
    glass = part('glass', s0 + .01, s1 - .01, z0 + .01, z1 - .01, (centre - .003, centre + .003), thin_glass(), 0.)
    glass.visible_shadow = False
    board = tuple(sorted((face - outward * .035, face + outward * .07)))
    part('window board', s0 - .05, s1 + .05, z0 - .028, z0, board, sill_mat, .002)
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
    obj.rotation_euler = Vector(inward).to_track_quat('-Z', 'Y').to_euler()
    return obj


def shell(walls, ceiling, floor, skirting):
    """Floor, ceiling and four walls with the two window openings."""
    (x0, x1), (y0, y1), t = ROOM_X, ROOM_Y, WALL_THICK_M
    box('Parquet floor', (x0 - t, y0 - t, -.06), (x1 + t, y1 + t, 0.), floor)
    box('Ceiling', (x0 - t, y0 - t, CEILING_M), (x1 + t, y1 + t, CEILING_M + .12), ceiling)
    z = (-.06, CEILING_M)
    left = (LEFT_WINDOW['span'], LEFT_WINDOW['z'])
    right = (RIGHT_WINDOW['span'], RIGHT_WINDOW['z'])
    wall_x('Left wall (window)', x0 - t, x0, (y0 - t, y1 + t), z, left, walls)
    wall_x('Right wall (window)', x1, x1 + t, (y0 - t, y1 + t), z, right, walls)
    box('Back wall', (x0, y1, z[0]), (x1, y1 + t, z[1]), walls)
    box('Wall behind camera', (x0, y0 - t, z[0]), (x1, y0, z[1]), walls)
    box('Skirting back wall', (x0, y1 - .016, 0.), (x1, y1, .10), skirting, .0015)
    box('Skirting left wall', (x0, y0, 0.), (x0 + .016, y1, .10), skirting, .0015)
    box('Skirting right wall', (x1 - .016, y0, 0.), (x1, y1, .10), skirting, .0015)
    box('Skirting camera wall', (x0, y0, 0.), (x1, y0 + .016, .10), skirting, .0015)


def writing_desk(top_z, wood):
    """The desk: a 28 mm veneered top, a 70 mm apron and four tapered legs.
    Its top face is exactly ``top_z``; the outline is DESK_X x DESK_Y."""
    (x0, x1), (y0, y1) = DESK_X, DESK_Y
    under = top_z - DESK_TOP_THICK_M
    parts = [box('Desk top', (x0, y0, under), (x1, y1, top_z), wood, .0025)]
    inset, apron = .045, .070
    parts.append(box('Desk apron front', (x0 + inset, y0 + inset, under - apron), (x1 - inset, y0 + inset + .02, under), wood, .0015))
    parts.append(box('Desk apron back', (x0 + inset, y1 - inset - .02, under - apron), (x1 - inset, y1 - inset, under), wood, .0015))
    parts.append(box('Desk apron left', (x0 + inset, y0 + inset, under - apron), (x0 + inset + .02, y1 - inset, under), wood, .0015))
    parts.append(box('Desk apron right', (x1 - inset - .02, y0 + inset, under - apron), (x1 - inset, y1 - inset, under), wood, .0015))
    for i, (x, y) in enumerate(((x0 + inset + .02, y0 + inset + .02), (x1 - inset - .02, y0 + inset + .02),
                                (x0 + inset + .02, y1 - inset - .02), (x1 - inset - .02, y1 - inset - .02))):
        parts.append(tapered_leg(f'Desk leg {i + 1}', x, y, 0., under, .048, .030, wood))
    return parts


# ------------------------------------------------------------------ daylight


def daylight(scene):
    """A sun lamp and a Nishita sky outside the windows, nothing inside.

    Light rays see the physical sky (with its own sun disc off: the lamp is
    the only sun). Neither window is in the camera's view.
    """
    import bpy
    from mathutils import Vector
    el, az = math.radians(SUN_ELEVATION_DEG), math.radians(SUN_AZIMUTH_DEG)
    towards_sun = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    data = bpy.data.lights.new('Afternoon sun', 'SUN')
    data.energy, data.angle, data.color = SUN_STRENGTH, math.radians(.53), (1., .89, .76)
    sun = bpy.data.objects.new('Afternoon sun', data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (-towards_sun).to_track_quat('-Z', 'Y').to_euler()
    world = bpy.data.worlds.new('Afternoon sky')
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    sky = nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'NISHITA'
    sky.sun_disc = False
    sky.sun_elevation = el
    # Nishita puts its sun at (sin r, cos r) in the ground plane: r = 0 is +y.
    sky.sun_rotation = math.atan2(towards_sun.x, towards_sun.y)
    sky.air_density, sky.dust_density = 1., 2.0
    background = nodes['Background']
    links.new(sky.outputs['Color'], background.inputs['Color'])
    background.inputs['Strength'].default_value = SKY_STRENGTH
    return sun


def build_study(scene, top_z):
    """Build the room and the desk; return a description of both."""
    walls = scanned('Slate painted plaster', 'plastered_wall_04', WALL_TILE_M, tint=(.55, .62, .70),
                    rough_range=(.78, .92), normal_strength=.5)
    ceiling = painted('Ceiling white', (.74, .73, .70), .9)
    floor = scanned('Oak parquet', 'rectangular_parquet', PARQUET_TILE_M, rough_range=(.35, .62), normal_strength=.6)
    skirting = painted('Skirting paint', (.70, .69, .66), .45)
    frame_paint = painted('Window frame paint', (.72, .71, .68), .40)
    sill = painted('Window board paint', (.70, .69, .66), .38)
    desk_wood = rosewood_veneer('Lacquered rosewood veneer')
    shell(walls, ceiling, floor, skirting)
    window('Left window', -1, LEFT_WINDOW['span'], LEFT_WINDOW['z'], frame_paint, sill)
    window('Right window', 1, RIGHT_WINDOW['span'], RIGHT_WINDOW['z'], frame_paint, sill)
    for label, wall_x_face, side, spec in (('Left', ROOM_X[0], -1, LEFT_WINDOW), ('Right', ROOM_X[1], 1, RIGHT_WINDOW)):
        (s0, s1), (z0, z1) = spec['span'], spec['z']
        portal(f'{label} window sky portal', (wall_x_face + side * (WALL_THICK_M + .01), (s0 + s1) / 2, (z0 + z1) / 2),
               (s1 - s0, z1 - z0), (-side, 0, 0))
    # The ground outside stops sky light from below the horizon.
    ground = box('Ground outside', (-60., -60., -.6), (60., 60., -.3), principled('Ground outside', (.16, .15, .12), .9))
    ground.visible_camera = False
    desk = writing_desk(top_z, desk_wood)
    daylight(scene)
    return dict(desk_x=list(DESK_X), desk_y=list(DESK_Y), desk_top_z=top_z, desk_parts=[o.name for o in desk],
                room_x=list(ROOM_X), room_y=list(ROOM_Y), ceiling_m=CEILING_M,
                sun_elevation_deg=SUN_ELEVATION_DEG, sun_azimuth_deg=SUN_AZIMUTH_DEG)
