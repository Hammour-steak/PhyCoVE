"""A school sports-equipment room in afternoon daylight, built at metre scale.

Terrazzo floor, a green oil-paint dado under white stucco, an aluminium sliding
window in a real opening, a low steel cabinet on the cabinet collider, steel
shelving under the split unit and a few Poly Haven props.  All light comes in
through the windows: a sun lamp and a physical sky outside, with the field
photograph shown to camera rays through the glass.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
ROOT = _PCVE_ROOT
import bmesh
import bpy
from mathutils import Matrix, Vector
from scene_config import MODELS
from scene_geometry import (AC_BACK_GAP, AC_CENTER, AC_WIDTH, CABINET_CENTER,
    CABINET_SIZE, SPARE_BALL_CENTERS, SPARE_BALL_RADIUS, WINDOW_CENTER_Y)
from pcve_assets import asset as _pcve_asset

# Everything this look downloads lives in one Poly Haven folder (CC0).
POLYHAVEN = _pcve_asset('') / 'polyhaven' / 'volleyball_corner_rebound'

WALL_T = .20
# The window opening in the x=0 wall: 1.4 m wide around WINDOW_CENTER_Y,
# sill board at 1.10-1.13 m, head at 2.63 m.
WINDOW_HALF = .70
WINDOW_Z = (1.13, 2.63)
# Oil-paint dado (a school's washable lower wall) up to the window board, a
# dark band at its top, and a painted skirting band.  All three are paint on
# the one plaster plane, so the wall the ball hits stays the physics plane.
DADO_TOP = 1.10
DADO_STRIPE = .025
SKIRT_TOP = .12

# Afternoon sun through the x=0 window.  The elevation is the sun's own in the
# window photograph (autumn_park, measured at pixel u=0.5999, v=0.3107:
# azimuth -36.0 deg in the photograph's frame, elevation 34.1 deg).  HEADING is
# the direction the light travels across the floor, from +x towards +y.
SUN_ELEVATION_DEG = 34.1
SUN_HEADING_DEG = 12.0
SUN_ENERGY = 3.4
SKY_STRENGTH = .55
WINDOW_VIEW_SUN_AZIMUTH_DEG = -36.0
WINDOW_VIEW_STRENGTH = 1.0


def material(name, color, roughness=.6, bump=.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    if bump:
        coord = nodes.new('ShaderNodeTexCoord')
        noise = nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = 170
        noise.inputs['Detail'].default_value = 2
        links.new(coord.outputs['Object'], noise.inputs['Vector'])
        node = nodes.new('ShaderNodeBump')
        node.inputs['Strength'].default_value = .22
        node.inputs['Distance'].default_value = bump
        links.new(noise.outputs['Fac'], node.inputs['Height'])
        links.new(node.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def cube(name, center, size, mat, bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new('Soft manufactured edges', 'BEVEL')
        mod.width, mod.segments = bevel, 3
        obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return obj


def span_box(name, lo, hi, mat, bevel=0):
    """A cube given by its two opposite corners."""
    return cube(name, [(a + b) / 2 for a, b in zip(lo, hi)], [b - a for a, b in zip(lo, hi)], mat, bevel)


def aim(obj, point):
    obj.rotation_euler = (Vector(point)-obj.location).to_track_quat('-Z','Y').to_euler()


def world_uvs(obj):
    """UVs in world metres, projected along each face's own axis.

    The scanned maps are tiled at their real size, and a tangent-space normal
    map needs UVs whose u x v is the face normal: u runs along +y on a +x face,
    along -x on a +y face, and so on, so the relief is lit from the right side
    on every wall.
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    layer = bm.loops.layers.uv.verify()
    world, turn = obj.matrix_world, obj.matrix_world.to_3x3()
    for face in bm.faces:
        n = (turn @ face.normal).normalized()
        axis = max(range(3), key=lambda i: abs(n[i]))
        for loop in face.loops:
            p = world @ loop.vert.co
            if axis == 0:
                uv = (p.y if n.x > 0 else -p.y, p.z)
            elif axis == 1:
                uv = (-p.x if n.y > 0 else p.x, p.z)
            else:
                uv = (p.x if n.z > 0 else -p.x, p.y)
            loop[layer].uv = uv
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def _scan_nodes(mat, stem, tile_m):
    """Colour, roughness and OpenGL-normal image nodes of one Poly Haven set."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1 / tile_m, 1 / tile_m, 1)
    links.new(coord.outputs['UV'], mapping.inputs['Vector'])
    out = {}
    for kind, colour in (('diff', True), ('rough', False), ('nor_gl', False)):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(POLYHAVEN / f'{stem}_{kind}_2k.jpg'), check_existing=True)
        if not colour:
            node.image.colorspace_settings.name = 'Non-Color'
        node.extension = 'REPEAT'
        links.new(mapping.outputs['Vector'], node.inputs['Vector'])
        out[kind] = node
    normal = nodes.new('ShaderNodeNormalMap')
    links.new(out['nor_gl'].outputs['Color'], normal.inputs['Color'])
    out['normal'] = normal
    return out


def _math(nodes, links, operation, a, b=None):
    node = nodes.new('ShaderNodeMath')
    node.operation = operation
    for index, value in enumerate((a, b)):
        if value is None:
            continue
        if isinstance(value, (int, float)):
            node.inputs[index].default_value = value
        else:
            links.new(value, node.inputs[index])
    return node.outputs[0]


def _mix(nodes, links, fac, a, b, blend='MIX'):
    node = nodes.new('ShaderNodeMixRGB')
    node.blend_type = blend
    for index, value in ((0, fac), (1, a), (2, b)):
        if isinstance(value, (int, float)):
            node.inputs[index].default_value = value if index == 0 else (value, value, value, 1)
        elif isinstance(value, tuple):
            node.inputs[index].default_value = (*value, 1)
        else:
            links.new(value, node.inputs[index])
    return node.outputs[0]


def terrazzo_material(stem='mixed_stone_tiles'):
    """Poly Haven mixed_stone_tiles as a polished terrazzo floor (1.8 m scan, 30 cm tiles).

    The scan was made outdoors, matt (roughness 0.72-0.82); an indoor terrazzo
    floor is ground and waxed, so the scan's roughness is kept as variation but
    remapped into 0.16-0.42, which gives the window its soft reflection.
    """
    mat = material('Terrazzo tiles / scanned mixed_stone_tiles', (.25, .19, .12), .3)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    scan = _scan_nodes(mat, stem, 1.8)
    tone = nodes.new('ShaderNodeHueSaturation')
    tone.inputs['Saturation'].default_value = .85
    links.new(scan['diff'].outputs['Color'], tone.inputs['Color'])
    links.new(tone.outputs['Color'], bsdf.inputs['Base Color'])
    polish = nodes.new('ShaderNodeMapRange')
    polish.inputs['From Min'].default_value, polish.inputs['From Max'].default_value = .70, .85
    polish.inputs['To Min'].default_value, polish.inputs['To Max'].default_value = .16, .42
    links.new(scan['rough'].outputs['Color'], polish.inputs['Value'])
    links.new(polish.outputs['Result'], bsdf.inputs['Roughness'])
    scan['normal'].inputs['Strength'].default_value = 1.0
    links.new(scan['normal'].outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def wall_paint(name='Painted wall / white stucco over green dado'):
    """White emulsion on stucco above, green oil-paint dado and dark skirting band below.

    The bands are chosen by world height, so every wall piece, reveal and the
    corner continue into each other without seams.  The stucco scan supplies
    the white wall's colour, roughness and relief; the oil paint keeps a
    softened copy of the relief and its own gloss.
    """
    mat = material(name, (.66, .65, .62), .85)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    scan = _scan_nodes(mat, 'white_stucco', 2.0)
    geometry = nodes.new('ShaderNodeNewGeometry')
    split = nodes.new('ShaderNodeSeparateXYZ')
    links.new(geometry.outputs['Position'], split.inputs[0])
    z = split.outputs['Z']
    upper = _math(nodes, links, 'GREATER_THAN', z, DADO_TOP)
    stripe_up = _math(nodes, links, 'GREATER_THAN', z, DADO_TOP - DADO_STRIPE)
    above_skirt = _math(nodes, links, 'GREATER_THAN', z, SKIRT_TOP)
    # Brush and roller leave a few percent of drift over a metre.
    drift = nodes.new('ShaderNodeTexNoise')
    drift.inputs['Scale'].default_value = .7
    drift.inputs['Detail'].default_value = 3
    links.new(geometry.outputs['Position'], drift.inputs['Vector'])
    drift_tone = nodes.new('ShaderNodeMapRange')
    drift_tone.inputs['To Min'].default_value, drift_tone.inputs['To Max'].default_value = .93, 1.04
    links.new(drift.outputs['Fac'], drift_tone.inputs['Value'])
    shade = drift_tone.outputs['Result']
    # The stucco scan averages 0.68 linear; dividing it out keeps its grain on
    # the painted bands without darkening them.
    grain = _mix(nodes, links, 1.0, scan['diff'].outputs['Color'], (1 / .68, 1 / .68, 1 / .68), 'MULTIPLY')
    white = _mix(nodes, links, 1.0, scan['diff'].outputs['Color'], (.98, .965, .93), 'MULTIPLY')
    green = _mix(nodes, links, 1.0, grain, (.27, .40, .265), 'MULTIPLY')
    band = _mix(nodes, links, 1.0, grain, (.075, .13, .08), 'MULTIPLY')
    skirt = _mix(nodes, links, 1.0, grain, (.035, .047, .042), 'MULTIPLY')
    colour = _mix(nodes, links, above_skirt, skirt, green)
    colour = _mix(nodes, links, stripe_up, colour, band)
    colour = _mix(nodes, links, upper, colour, white)
    scaled = nodes.new('ShaderNodeVectorMath')
    scaled.operation = 'SCALE'
    links.new(colour, scaled.inputs[0])
    links.new(shade, scaled.inputs['Scale'])
    links.new(scaled.outputs['Vector'], bsdf.inputs['Base Color'])
    gloss = _mix(nodes, links, above_skirt, .42, .30)
    gloss = _mix(nodes, links, stripe_up, gloss, .30)
    gloss = _mix(nodes, links, upper, gloss, scan['rough'].outputs['Color'])
    links.new(gloss, bsdf.inputs['Roughness'])
    relief = _mix(nodes, links, upper, .35, 1.0)
    links.new(relief, scan['normal'].inputs['Strength'])
    links.new(scan['normal'].outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def ceiling_paint():
    mat = material('Ceiling / white emulsion on stucco', (.8, .79, .76), .9)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    scan = _scan_nodes(mat, 'white_stucco', 2.0)
    tint = _mix(nodes, links, 1.0, scan['diff'].outputs['Color'], (1.0, .99, .97), 'MULTIPLY')
    links.new(tint, bsdf.inputs['Base Color'])
    links.new(scan['rough'].outputs['Color'], bsdf.inputs['Roughness'])
    scan['normal'].inputs['Strength'].default_value = .6
    links.new(scan['normal'].outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def thin_glass():
    """Thin float glass: a Fresnel reflection over a see-through layer.

    Rays through it stay camera rays, so the world shows the field photograph
    to the camera alone while the room is lit by the physical sky.  Both faces
    reflect as air-to-glass: Cycles' Fresnel node inverts the IOR on a back
    face, which would totally reflect a ray leaving the pane at more than
    41 deg and turn an obliquely seen window black, so back faces get 1/1.52.
    """
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
    reflection.inputs['Roughness'].default_value = .0
    fresnel = nodes.new('ShaderNodeFresnel')
    geometry = nodes.new('ShaderNodeNewGeometry')
    ior = nodes.new('ShaderNodeMath')
    ior.operation = 'MULTIPLY_ADD'
    ior.inputs[1].default_value = 1 / 1.52 - 1.52
    ior.inputs[2].default_value = 1.52
    links.new(geometry.outputs['Backfacing'], ior.inputs[0])
    links.new(ior.outputs['Value'], fresnel.inputs['IOR'])
    pane = nodes.new('ShaderNodeMixShader')
    links.new(fresnel.outputs['Fac'], pane.inputs['Fac'])
    links.new(clear.outputs['BSDF'], pane.inputs[1])
    links.new(reflection.outputs['BSDF'], pane.inputs[2])
    links.new(pane.outputs['Shader'], nodes['Material Output'].inputs['Surface'])
    return mat


def wall_with_opening(name, x_span, y_span, z_span, hole, mat, runs_along='y'):
    """A wall panel as four pieces around one rectangular opening.

    The spans are given as for a wall at constant x; runs_along='x' lays the
    same panel out as a wall at constant y (x_span is then its thickness in y
    and y_span its length in x).
    """
    swap = (lambda v: (v[1], v[0], v[2])) if runs_along == 'x' else (lambda v: v)
    (x0, x1), (y0, y1), (z0, z1) = x_span, y_span, z_span
    hy0, hy1, hz0, hz1 = hole
    pieces = (('below opening', (x0, hy0, z0), (x1, hy1, hz0)),
              ('above opening', (x0, hy0, hz1), (x1, hy1, z1)),
              ('before opening', (x0, y0, z0), (x1, hy0, z1)),
              ('after opening', (x0, hy1, z0), (x1, y1, z1)))
    return [world_uvs(span_box(f'{name} / {label}', swap(lo), swap(hi), mat)) for label, lo, hi in pieces]


def sky_portal(name, centre, size, inward):
    """An area-light portal across an opening, so Cycles samples the sky through it."""
    data = bpy.data.lights.new(name, 'AREA')
    data.shape = 'RECTANGLE'
    data.size, data.size_y = size
    data.cycles.is_portal = True
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = centre
    aim(obj, Vector(centre) + Vector(inward))
    return obj


def build_window():
    """Silver anodised aluminium sliding window in the x=0 opening.

    Fixed outer frame in the middle of the 20 cm reveal, two sashes in their
    own tracks overlapping at the meeting stiles, thin glass, a terrazzo window
    board 2 cm proud of the plaster and a sky portal outside.
    """
    y0, y1 = WINDOW_CENTER_Y - WINDOW_HALF, WINDOW_CENTER_Y + WINDOW_HALF
    z0, z1 = WINDOW_Z
    alu = material('Window / silver anodised aluminium', (.78, .79, .80), .3)
    alu.node_tree.nodes['Principled BSDF'].inputs['Metallic'].default_value = 1.0
    seal = material('Window / EPDM seal', (.02, .022, .022), .7)
    glass = thin_glass()
    face, depth = .05, (-.15, -.08)
    span_box('Window frame / head', (depth[0], y0, z1 - face), (depth[1], y1, z1), alu, .002)
    span_box('Window frame / bottom track', (depth[0], y0, z0), (depth[1], y1, z0 + face), alu, .002)
    for name, a, b in (('near', y0, y0 + face), ('far', y1 - face, y1)):
        span_box(f'Window frame / {name} jamb', (depth[0], a, z0 + face), (depth[1], b, z1 - face), alu, .002)
    inner = (y0 + face, y1 - face, z0 + face, z1 - face)
    overlap, bar = .03, .045
    middle = (inner[0] + inner[1]) / 2
    for label, (sy0, sy1), (sx0, sx1) in (('outer sash', (inner[0], middle + overlap), (-.142, -.118)),
                                         ('inner sash', (middle - overlap, inner[1]), (-.112, -.088))):
        sz0, sz1 = inner[2] + .005, inner[3] - .005
        span_box(f'Window {label} / top rail', (sx0, sy0, sz1 - bar), (sx1, sy1, sz1), alu, .0015)
        span_box(f'Window {label} / bottom rail', (sx0, sy0, sz0), (sx1, sy1, sz0 + bar), alu, .0015)
        span_box(f'Window {label} / stile a', (sx0, sy0, sz0 + bar), (sx1, sy0 + bar, sz1 - bar), alu, .0015)
        span_box(f'Window {label} / stile b', (sx0, sy1 - bar, sz0 + bar), (sx1, sy1, sz1 - bar), alu, .0015)
        mid = (sx0 + sx1) / 2
        pane = span_box(f'Window {label} / glass', (mid - .0025, sy0 + bar - .01, sz0 + bar - .01),
                        (mid + .0025, sy1 - bar + .01, sz1 - bar + .01), glass)
        pane.visible_shadow = False
        span_box(f'Window {label} / seal', (mid - .006, sy0 + bar - .004, sz0 + bar - .004),
                 (mid + .006, sy0 + bar, sz1 - bar + .004), seal)
    # Crescent lock on the inner sash's meeting stile.
    span_box('Window lock / body', (-.088, middle - overlap, 1.86), (-.074, middle - overlap + .035, 1.92), alu, .003)
    terrazzo = bpy.data.materials.get('Terrazzo tiles / scanned mixed_stone_tiles') or terrazzo_material()
    world_uvs(span_box('Window board / terrazzo', (depth[1], y0 - .05, z0 - .03), (.02, y1 + .05, z0), terrazzo, .003))
    world_uvs(span_box('Window exterior sill', (-.27, y0 - .03, z0 - .05), (depth[0], y1 + .03, z0 - .01), terrazzo, .003))
    sky_portal('Sky portal / x=0 window', (-WALL_T - .01, WINDOW_CENTER_Y, (z0 + z1) / 2), (y1 - y0, z1 - z0), (1, 0, 0))


def far_window(name, lo, hi, inward):
    """A glazed opening in a wall behind the camera: unseen, but the sky it lets in
    bounces back onto the corner the way a real room's second window does."""
    pane = span_box(f'{name} glass', lo, hi, thin_glass())
    pane.visible_shadow = False
    centre = [(a + b) / 2 for a, b in zip(lo, hi)]
    axis = 0 if inward[0] else 1
    size = (hi[1 - axis] - lo[1 - axis], hi[2] - lo[2])
    centre[axis] -= inward[axis] * .12
    sky_portal(f'Sky portal / {name}', centre, size, inward)


def daylight(sun_target, window_view):
    """Sun and sky outside, no lamp inside the room."""
    el, heading = math.radians(SUN_ELEVATION_DEG), math.radians(SUN_HEADING_DEG)
    travel = Vector((math.cos(el) * math.cos(heading), math.cos(el) * math.sin(heading), -math.sin(el)))
    sun_data = bpy.data.lights.new('Afternoon sun', 'SUN')
    sun_data.energy, sun_data.angle, sun_data.color = SUN_ENERGY, math.radians(.53), (1., .9, .78)
    sun = bpy.data.objects.new('Afternoon sun', sun_data)
    bpy.context.collection.objects.link(sun)
    sun.location = Vector(sun_target) - 6 * travel
    aim(sun, sun.location + travel)
    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new('Afternoon sky over the sports field')
    scene.world.use_nodes = True
    nodes, links = scene.world.node_tree.nodes, scene.world.node_tree.links
    sky = nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'NISHITA'
    sky.sun_disc = False
    sky.sun_elevation = el
    # Nishita puts the sun at (sin r, cos r) in the ground plane: r = 0 is +y.
    sky.sun_rotation = math.atan2(-travel.x, -travel.y)
    sky.air_density, sky.dust_density = 1.0, 1.5
    lighting = nodes['Background']
    links.new(sky.outputs['Color'], lighting.inputs['Color'])
    lighting.inputs['Strength'].default_value = SKY_STRENGTH
    coord = nodes.new('ShaderNodeTexCoord')
    turn = nodes.new('ShaderNodeMapping')
    turn.vector_type = 'VECTOR'
    # Rotating the lookup vector by theta moves the photograph by -theta, so
    # the lamp's direction is sent to the photograph's own sun azimuth.
    towards_sun = -travel
    turn.inputs['Rotation'].default_value = (0, 0, math.radians(WINDOW_VIEW_SUN_AZIMUTH_DEG) - math.atan2(towards_sun.y, towards_sun.x))
    photo = nodes.new('ShaderNodeTexEnvironment')
    photo.image = bpy.data.images.load(str(window_view), check_existing=True)
    links.new(coord.outputs['Generated'], turn.inputs['Vector'])
    links.new(turn.outputs['Vector'], photo.inputs['Vector'])
    view = nodes.new('ShaderNodeBackground')
    view.inputs['Strength'].default_value = WINDOW_VIEW_STRENGTH
    links.new(photo.outputs['Color'], view.inputs['Color'])
    path = nodes.new('ShaderNodeLightPath')
    world = nodes.new('ShaderNodeMixShader')
    links.new(path.outputs['Is Camera Ray'], world.inputs['Fac'])
    links.new(lighting.outputs['Background'], world.inputs[1])
    links.new(view.outputs['Background'], world.inputs[2])
    links.new(world.outputs['Shader'], nodes['World Output'].inputs['Surface'])
    return sun


def build_cabinet():
    """The cabinet collider as a low pressed-steel cupboard, flush with its box.

    Carcass, face frame and doors together fill exactly CABINET_CENTER +- SIZE/2:
    the 1.5x speed edit grazes its top corner at 1.69 s, so nothing may stand
    proud of the box (the pulls are slots, not handles).
    """
    (cx, cy, cz), (w, d, h) = CABINET_CENTER, CABINET_SIZE
    x0, x1, y0, y1, z0, z1 = cx - w / 2, cx + w / 2, cy - d / 2, cy + d / 2, cz - h / 2, cz + h / 2
    paint = material('Cabinet / light grey stoved enamel', (.50, .52, .50), .36)
    nodes, links = paint.node_tree.nodes, paint.node_tree.links
    peel = nodes.new('ShaderNodeTexNoise')
    peel.inputs['Scale'].default_value = 900
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .04
    links.new(nodes.new('ShaderNodeTexCoord').outputs['Object'], peel.inputs['Vector'])
    links.new(peel.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], nodes['Principled BSDF'].inputs['Normal'])
    shadow = material('Cabinet / unlit interior', (.012, .013, .013), .8)
    front = y1 - .006
    span_box('Steel cabinet / carcass', (x0, y0, z0), (x1, front - .012, z1), paint, .004)
    span_box('Steel cabinet / interior behind doors', (x0 + .01, front - .013, z0 + .06), (x1 - .01, front, z1 - .015), shadow)
    span_box('Steel cabinet / top rail', (x0, front - .013, z1 - .015), (x1, y1, z1), paint, .0025)
    span_box('Steel cabinet / plinth', (x0 + .01, front - .013, z0), (x1 - .01, front - .006, z0 + .06), shadow)
    for name, a, b in (('near stile', x0, x0 + .01), ('far stile', x1 - .01, x1)):
        span_box(f'Steel cabinet / {name}', (a, front - .013, z0), (b, y1, z1), paint, .002)
    gap, doors = .004, 3
    width = (x1 - x0 - .02 - (doors - 1) * gap) / doors
    for k in range(doors):
        a = x0 + .01 + k * (width + gap)
        span_box(f'Steel cabinet / door {k + 1}', (a, front, z0 + .062), (a + width, y1 - .0005, z1 - .017), paint, .0015)
        span_box(f'Steel cabinet / door {k + 1} pull slot', (a + width / 2 - .045, y1 - .0012, z1 - .05),
                 (a + width / 2 + .045, y1 - .0002, z1 - .038), shadow)
        for row in range(5):
            zz = z0 + .10 + row * .022
            span_box(f'Steel cabinet / door {k + 1} louvre {row + 1}', (a + width / 2 - .06, y1 - .0012, zz),
                     (a + width / 2 + .06, y1 - .0002, zz + .006), shadow)


def import_model(model_id, name, yaw_deg=0.0, **anchor):
    """Import one Poly Haven glTF, join it into one object and set its bbox on an anchor.

    Anchor keys: x / y (bbox centre), x_min / x_max / y_min / y_max (faces) and
    z (bottom).  A model's glazing imports as a refractive slab, which turns
    what is behind it black; it is shaded as the same thin pane as the window.
    """
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(POLYHAVEN / model_id / f'{model_id}_1k.gltf'))
    imported = [o for o in bpy.data.objects if o not in before]
    names = [o.name for o in imported]
    meshes = [o for o in imported if o.type == 'MESH']
    if not meshes:
        raise ValueError(f'{model_id} contains no meshes')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.animation_data_clear()
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    body = bpy.context.object
    world = body.matrix_world.copy()
    body.parent = None
    body.matrix_world = world
    for other in names:
        obj = bpy.data.objects.get(other)
        if obj is not None and obj is not body:
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    body.data.transform(Matrix.Rotation(math.radians(yaw_deg), 4, 'Z'))
    lo = Vector([min(v.co[i] for v in body.data.vertices) for i in range(3)])
    hi = Vector([max(v.co[i] for v in body.data.vertices) for i in range(3)])
    shift = Vector((0, 0, 0))
    for axis, index in (('x', 0), ('y', 1)):
        if axis in anchor:
            shift[index] = anchor[axis] - (lo[index] + hi[index]) / 2
        elif f'{axis}_min' in anchor:
            shift[index] = anchor[f'{axis}_min'] - lo[index]
        elif f'{axis}_max' in anchor:
            shift[index] = anchor[f'{axis}_max'] - hi[index]
    if 'z' in anchor:
        shift.z = anchor['z'] - lo.z
    elif 'zc' in anchor:
        shift.z = anchor['zc'] - (lo.z + hi.z) / 2
    body.data.transform(Matrix.Translation(shift))
    body.location = (0, 0, 0)
    body.name = name
    for slot in body.material_slots:
        if slot.material is not None and 'glass' in slot.material.name.lower():
            slot.material = thin_glass()
    lo, hi = lo + shift, hi + shift
    return {'name': name, 'model': model_id, 'bbox_min': [round(v, 4) for v in lo], 'bbox_max': [round(v, 4) for v in hi]}


def shelf_levels(name, min_area=.08):
    """Heights of the planks of a shelving unit: upward faces with real area."""
    obj = bpy.data.objects[name]
    area = {}
    for poly in obj.data.polygons:
        if poly.normal.z > .95:
            z = round(poly.center.z, 3)
            area[z] = area.get(z, 0) + poly.area
    return sorted(z for z, a in area.items() if a >= min_area)


# The shelving bay under the split unit: two 0.59 m Poly Haven units against the
# x=0 wall, then what a sports storeroom keeps on them.  The upper planks are
# left for the larger items so nothing reaches into the 0.26 m under the unit.
SHELF_UNITS = ((4.12, 'Steel shelving / near unit'), (4.725, 'Steel shelving / far unit'))
SHELF_ITEMS = (
    # (model, name, unit, plank index from the bottom, yaw, y offset in the unit)
    ('plastic_crate_02', 'Crate / yellow, bibs and cones', 0, 1, 90.0, .0),
    ('cardboard_box_01', 'Cardboard box / spare nets', 0, 3, 0.0, .0),
    ('plastic_crate_01', 'Crate / red', 1, 0, 0.0, -.08),
    ('plastic_crate_01', 'Crate / red, second', 1, 2, 0.0, .08),
)


def furnish():
    """Poly Haven props by bbox anchor; returns their world boxes for the clearance check."""
    props = []
    for y_min, name in SHELF_UNITS:
        props.append(import_model('steel_frame_shelves_02', name, 90.0, x_min=.012, y_min=y_min, z=0.0))
    for model, name, unit, plank, yaw, offset in SHELF_ITEMS:
        shelf = props[unit]
        levels = shelf_levels(shelf['name'])
        centre_y = (shelf['bbox_min'][1] + shelf['bbox_max'][1]) / 2 + offset
        centre_x = (shelf['bbox_min'][0] + shelf['bbox_max'][0]) / 2
        props.append(import_model(model, name, yaw, x=centre_x, y=centre_y, z=levels[plank] + .002))
    # A school clock between the window and the split unit, a framed notice over
    # the cabinet: both flat on the plaster.  Their fronts face -y as imported.
    props.append(import_model('wall_clock', 'Wall clock', 90.0, x_min=.003, y=3.66, zc=2.18))
    props.append(import_model('hanging_picture_frame_01', 'Imported framed art 1 / hanging_picture_frame_01', 180.0,
                              x=CABINET_CENTER[0], y_min=.004, zc=1.50))
    props.append(import_model('SchoolChair_01', 'School chair', 145.0, x=.95, y=3.75, z=0.0))
    return props


def build_room(scenario):
    w, d, h = scenario['physics']['room_size']
    paint = wall_paint()
    floor = terrazzo_material(scenario['assets']['floor'])
    # The floor runs under the walls, so no seam can show daylight.
    world_uvs(span_box('Floor / terrazzo', (-WALL_T, -WALL_T, -.2), (w + WALL_T, d + WALL_T, 0), floor))
    ground = cube('Ground outside', (w / 2, d / 2, -.45), (200, 200, .3), material('Ground outside', (.16, .15, .12), .9))
    ground.visible_camera = False
    hole = (WINDOW_CENTER_Y - WINDOW_HALF, WINDOW_CENTER_Y + WINDOW_HALF, *WINDOW_Z)
    # The impact faces are the physics planes x=0 and y=0; the corner block
    # belongs to the x wall so the y wall starts exactly at the corner.
    wall_with_opening('Wall_X / impact face x=0', (-WALL_T, 0), (-WALL_T, d + WALL_T), (-.05, h), hole, paint)
    world_uvs(span_box('Wall_Y / impact face y=0', (0, -WALL_T, -.05), (w + WALL_T, 0, h), paint))
    # The two walls behind the camera, each with a window: unseen, but in a
    # closed room the sky they admit is what lifts the corner out of shadow.
    rear = (1.4, 4.4, .9, 2.6)
    wall_with_opening('Far wall x=w', (w, w + WALL_T), (-WALL_T, d + WALL_T), (-.05, h), rear, paint)
    far_window('Rear window x=w', (w + .09, rear[0], rear[2]), (w + .095, rear[1], rear[3]), (-1, 0, 0))
    back = (1.2, 4.2, .9, 2.6)
    wall_with_opening('Far wall y=d', (d, d + WALL_T), (0, w), (-.05, h), back, paint, runs_along='x')
    far_window('Back window y=d', (back[0], d + .09, back[2]), (back[1], d + .095, back[3]), (0, -1, 0))
    world_uvs(span_box('Interior ceiling', (-WALL_T, -WALL_T, h), (w + WALL_T, d + WALL_T, h + .16), ceiling_paint()))
    build_window()
    build_cabinet()
    import_air_conditioner(MODELS / scenario['assets']['air_conditioner'])
    build_spare_balls(MODELS / scenario['assets']['ball'])
    trim = material('Outlet / white urea plastic', (.72, .71, .68), .35)
    dark = material('Outlet / socket holes', (.01, .01, .01), .6)
    cube('Outlet face', (.004, 3.66, .32), (.008, .086, .086), trim, .003)
    for yy in (3.645, 3.675):
        cube('Outlet socket', (.0085, yy, .325), (.002, .006, .014), dark, .0008)
    props = furnish()
    daylight((-WALL_T, WINDOW_CENTER_Y, sum(WINDOW_Z) / 2), POLYHAVEN / scenario['assets']['window_view'])
    return {'props': props}


def check_clearance(props, rows, radius, margin=.02, substeps=12):
    """Smallest gap between the ball and each added prop over the whole take.

    Props are render-only, so a ball passing through one would be invisible to
    the simulator; this refuses the render instead.  Positions are sampled
    between frames too (a fast ball moves up to 0.37 m per frame).
    """
    points = []
    for a, b in zip(rows, rows[1:]):
        pa, pb = Vector(a['ball_location']), Vector(b['ball_location'])
        points.extend(pa.lerp(pb, k / substeps) for k in range(substeps))
    points.append(Vector(rows[-1]['ball_location']))
    gaps = {}
    for prop in props:
        lo, hi = prop['bbox_min'], prop['bbox_max']
        gap = min(math.sqrt(sum(max(lo[i] - p[i], 0, p[i] - hi[i]) ** 2 for i in range(3))) for p in points) - radius
        gaps[prop['name']] = round(gap, 3)
        if gap < margin:
            raise ValueError(f'The ball passes within {gap:.3f} m of {prop["name"]}; move the prop')
    return gaps


def build_spare_balls(path):
    first=import_ball(path,SPARE_BALL_RADIUS)
    first.name='Spare volleyball 1 / static'
    for index,position in enumerate(SPARE_BALL_CENTERS):
        body=first if index==0 else first.copy()
        if index:
            body.data=first.data.copy()
            bpy.context.collection.objects.link(body)
        body.name=f'Spare volleyball {index+1} / static'
        body.animation_data_clear()
        body.location=position
        body.rotation_mode='XYZ'
        body.rotation_euler=((.4,.9,.2),(1.2,.3,2.1))[index]


def import_air_conditioner(path):
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported=[o for o in bpy.data.objects if o not in before]
    meshes=[o for o in imported if o.type=='MESH']
    if not meshes:
        raise ValueError('Indoor unit asset contains no meshes')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.animation_data_clear()
        obj.select_set(True)
    bpy.context.view_layer.objects.active=meshes[0]
    if len(meshes)>1:
        bpy.ops.object.join()
    body=bpy.context.object
    world=body.matrix_world.copy()
    body.parent=None
    body.matrix_world=world
    for obj in imported:
        if obj!=body and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj,do_unlink=True)
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    # The asset's back is its +Y face and the louvre panel faces -Y.  The wall it
    # goes on is x=0 with the room on +X, so a quarter turn about Z (+Y -> -X)
    # lays the back on the plaster and points the panel into the room; the unit's
    # width then runs along Y and its depth along X, which is why AC_SIZE swaps
    # the two.  Width, not height, is what a split is specified by, so that is
    # the one dimension the uniform scale is pinned to.
    body.data.transform(Matrix.Rotation(math.pi/2,4,'Z'))
    lo=Vector(tuple(min(v.co[i] for v in body.data.vertices) for i in range(3)))
    hi=Vector(tuple(max(v.co[i] for v in body.data.vertices) for i in range(3)))
    factor=AC_WIDTH/(hi.y-lo.y)
    centre=Vector((lo.x,(lo.y+hi.y)*.5,(lo.z+hi.z)*.5))
    for vertex in body.data.vertices:
        vertex.co=(vertex.co-centre)*factor+Vector((AC_BACK_GAP,AC_CENTER[1],AC_CENTER[2]))
    body.location=(0,0,0)
    body.name='Split indoor unit'
    for poly in body.data.polygons:
        poly.use_smooth=True
    for mat in body.data.materials:
        if not mat or not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type=='BSDF_PRINCIPLED':
                node.inputs['Emission Strength'].default_value=0
                # The glb's packed metallic channel reads 0.91 over the painted
                # shell, which is an authoring slip rather than the object: a
                # split indoor unit is painted steel and plastic, and at that
                # value it renders as a blue-grey mirror, so metallic is pinned
                # to 0.  Roughness keeps the supplied map.
                for link in list(node.inputs['Metallic'].links):
                    mat.node_tree.links.remove(link)
                node.inputs['Metallic'].default_value=0


def import_ball(path, radius):
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported=[o for o in bpy.data.objects if o not in before]
    meshes=[o for o in imported if o.type=='MESH']
    if not meshes:
        raise ValueError('Volleyball asset contains no meshes')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.animation_data_clear()
        obj.select_set(True)
    bpy.context.view_layer.objects.active=meshes[0]
    if len(meshes)>1:
        bpy.ops.object.join()
    ball=bpy.context.object
    world=ball.matrix_world.copy()
    ball.parent=None
    ball.matrix_world=world
    for obj in imported:
        if obj!=ball and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj,do_unlink=True)
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    # Bounding sphere centre, so the visual centre matches GEOM_SPHERE.
    lo=Vector(tuple(min(v.co[i] for v in ball.data.vertices) for i in range(3)))
    hi=Vector(tuple(max(v.co[i] for v in ball.data.vertices) for i in range(3)))
    center=(lo+hi)*.5
    factor=2*radius/max(hi-lo)
    for vertex in ball.data.vertices:
        vertex.co=(vertex.co-center)*factor
    ball.location=(0,0,0)
    ball.name='volleyball'
    for poly in ball.data.polygons:
        poly.use_smooth=True
    for mat in ball.data.materials:
        if not mat or not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type=='BSDF_PRINCIPLED':
                node.inputs['Emission Strength'].default_value=0
                if not node.inputs['Roughness'].is_linked:
                    node.inputs['Roughness'].default_value=.68
    return ball
