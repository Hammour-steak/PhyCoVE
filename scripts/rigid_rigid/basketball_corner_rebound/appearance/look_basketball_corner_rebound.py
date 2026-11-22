"""Photographic materials and metre-scale architectural room, authored locally."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
import bpy
from mathutils import Vector
from scene_config import MODELS

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

def aim(obj, point):
    obj.rotation_euler = (Vector(point)-obj.location).to_track_quat('-Z','Y').to_euler()

def plaster(name, color, roughness=.88, bump=.0012):
    """Rolled emulsion on plaster: one colour, but never one value.

    A painted wall drifts by a few percent in tone over a metre and in sheen
    with the roller; a perfectly uniform albedo is what makes a CG wall read as
    a card. The drift is driven by world position so the four panels around the
    window opening continue into each other without a seam.
    """
    mat = material(name, color, roughness, bump)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    position = nodes.new('ShaderNodeNewGeometry')
    drift = nodes.new('ShaderNodeTexNoise')
    drift.inputs['Scale'].default_value = .8
    drift.inputs['Detail'].default_value = 3.0
    links.new(position.outputs['Position'], drift.inputs['Vector'])
    tone = nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].position = .3
    tone.color_ramp.elements[0].color = (*(c * .955 for c in color), 1)
    tone.color_ramp.elements[1].position = .7
    tone.color_ramp.elements[1].color = (*(min(1., c * 1.03) for c in color), 1)
    links.new(drift.outputs['Fac'], tone.inputs['Fac'])
    links.new(tone.outputs['Color'], bsdf.inputs['Base Color'])
    sheen = nodes.new('ShaderNodeMapRange')
    sheen.inputs['To Min'].default_value = roughness - .06
    sheen.inputs['To Max'].default_value = min(1., roughness + .06)
    links.new(drift.outputs['Fac'], sheen.inputs['Value'])
    links.new(sheen.outputs['Result'], bsdf.inputs['Roughness'])
    return mat

# Poly Haven authors wood_floor_worn as a 2 m x 2 m patch; tiling it at that size
# keeps the boards at their real width next to a 24 cm ball.
FLOOR_TILE_M = 2.0

def floor_material(diffuse):
    """The scanned boards with the scan's own roughness and normal maps.

    The colour map alone gives every board the same varnish, so the floor lit up
    as one uniform glossy sheet; the scanned roughness lets worn tracks go dull
    and the normal map gives the joints and grain their own relief.
    """
    mat = material('Oak boards / scanned worn wood', (.32,.19,.09), .5)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1 / FLOOR_TILE_M, 1 / FLOOR_TILE_M, 1)
    links.new(coord.outputs['Object'], mapping.inputs['Vector'])

    def scan(kind, colour_data):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(diffuse).replace('_diff_', f'_{kind}_'), check_existing=True)
        if not colour_data:
            node.image.colorspace_settings.name = 'Non-Color'
        node.extension = 'REPEAT'
        links.new(mapping.outputs['Vector'], node.inputs['Vector'])
        return node

    links.new(scan('diff', True).outputs['Color'], bsdf.inputs['Base Color'])
    links.new(scan('rough', False).outputs['Color'], bsdf.inputs['Roughness'])
    normal = nodes.new('ShaderNodeNormalMap')
    links.new(scan('nor_gl', False).outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    return mat

# The shared picture library packs three framed prints into one file; this
# scene hangs one of them, and the render block says which and where.
DEFAULT_PICTURE = {'model': 'cafe_wall_pictures.glb', 'object': 'wall_picture_2',
                   'height_m': .62, 'location': [3.05, .03, 1.55]}


def hang_picture(spec):
    """Hang one framed print from assets/models flat against the y=0 wall.

    The library model is a group of three frames whose local +X is the pane
    normal, so a quarter turn about Z stands the chosen one up facing into the
    room. It is then scaled to a real wall height and slid back against the
    plaster, which keeps the frame out of every ball trajectory.
    """
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(MODELS / spec['model']))
    imported = [o for o in bpy.data.objects if o not in before]
    frames = [o for o in imported if o.type == 'MESH' and o.name.startswith(spec['object'] + '_')]
    if len(frames) != 1:
        raise ValueError(f"{spec['model']} has no single mesh named {spec['object']!r}")
    picture = frames[0]
    bpy.ops.object.select_all(action='DESELECT')
    picture.select_set(True)
    bpy.context.view_layer.objects.active = picture
    if picture.parent:
        bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for obj in imported:
        if obj is not picture and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    # glTF imports arrive in quaternion mode, where rotation_euler is inert.
    picture.rotation_mode = 'XYZ'
    picture.rotation_euler = (0, 0, math.pi/2)
    bpy.context.view_layer.update()
    corners = [picture.matrix_world @ Vector(c) for c in picture.bound_box]
    height = max(c.z for c in corners) - min(c.z for c in corners)
    factor = spec['height_m'] / max(height, 1e-6)
    picture.scale = (factor, factor, factor)
    bpy.context.view_layer.update()
    corners = [picture.matrix_world @ Vector(c) for c in picture.bound_box]
    low = [min(c[i] for c in corners) for i in range(3)]
    high = [max(c[i] for c in corners) for i in range(3)]
    target = spec['location']
    picture.location = (target[0] - (low[0] + high[0])/2,
                        target[1] - low[1],
                        target[2] - (low[2] + high[2])/2)
    picture.name = 'Wall picture'
    return picture


# A potted fiddle-leaf fig from the shared model library, standing under the
# window: an empty room is the strongest tell of a render, and a plant by the
# glass also puts leaf shadows into the sun patch.
DEFAULT_PLANT = {'model': 'fiddle_leaf_fig.glb', 'height_m': 1.55, 'location': [.45, 2.35], 'yaw_deg': 35.0}


def place_plant(spec):
    """Stand the plant on the floor at spec['location'] and return its footprint.

    The footprint (centre and radius on the floor plane) is what the renderer
    checks every frame of the ball against, so an edit that would roll the ball
    through the pot is reported instead of rendered silently.
    """
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(MODELS / spec['model']))
    imported = [o for o in bpy.data.objects if o not in before]
    # Names, not objects: join() deletes the meshes it merges.
    imported_names = [o.name for o in imported]
    meshes = [o for o in imported if o.type == 'MESH']
    if not meshes:
        raise ValueError(f"{spec['model']} contains no meshes")
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.animation_data_clear()
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    plant = bpy.context.object
    world = plant.matrix_world.copy()
    plant.parent = None
    plant.matrix_world = world
    for name in imported_names:
        obj = bpy.data.objects.get(name)
        if obj is not None and obj != plant:
            bpy.data.objects.remove(obj, do_unlink=True)
    # The library fig is a photogrammetry scan exported unlit: Blender imports it
    # as an emission that only the camera sees and every other ray passes
    # through, so it glowed with its baked light, took none from the room and
    # cast no shadow. Shade its scanned colour as an ordinary waxy surface.
    for mat in plant.data.materials:
        if mat and mat.use_nodes and not any(n.type == 'BSDF_PRINCIPLED' for n in mat.node_tree.nodes):
            nodes, links = mat.node_tree.nodes, mat.node_tree.links
            scan = next((n for n in nodes if n.type == 'TEX_IMAGE'), None)
            if scan is None:
                continue
            for node in [n for n in nodes if n not in (scan,) and n.type != 'OUTPUT_MATERIAL']:
                nodes.remove(node)
            surface = nodes.new('ShaderNodeBsdfPrincipled')
            surface.inputs['Roughness'].default_value = .55
            links.new(scan.outputs['Color'], surface.inputs['Base Color'])
            links.new(surface.outputs['BSDF'], next(n for n in nodes if n.type == 'OUTPUT_MATERIAL').inputs['Surface'])
    plant.rotation_mode = 'XYZ'
    plant.rotation_euler.z += math.radians(spec.get('yaw_deg', 0.0))
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    lo = Vector(tuple(min(v.co[i] for v in plant.data.vertices) for i in range(3)))
    hi = Vector(tuple(max(v.co[i] for v in plant.data.vertices) for i in range(3)))
    factor = spec['height_m'] / max(hi.z - lo.z, 1e-6)
    base = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    target = Vector((*spec['location'], 0.0))
    for vertex in plant.data.vertices:
        vertex.co = (vertex.co - base) * factor + target
    plant.name = 'Potted fiddle-leaf fig'
    # Only what stands at ball height can be hit: the pot and any low leaves.
    low_parts = [v.co for v in plant.data.vertices if v.co.z < BALL_HEIGHT_REACH_M]
    radius = max(Vector((c.x - target.x, c.y - target.y)).length for c in low_parts)
    return {'object': plant.name, 'centre_xy': list(spec['location']), 'radius_m': radius,
            'below_height_m': BALL_HEIGHT_REACH_M}


# Top of a 24 cm basketball rolling on the floor, plus a bounce allowance.
BALL_HEIGHT_REACH_M = .30


def window_glass():
    """Thin float glass: a 4% Fresnel reflection over a see-through layer.

    A 6 mm pane displaces nothing worth refracting, so it is shaded as a
    transparent surface. Rays seen through it then stay camera rays, which is
    what lets the world show the garden photograph to the camera alone while
    the room is lit by the physical sky (see daylight). Sunlight is not stopped
    by it either: build_room also makes the pane transparent to shadow rays.
    """
    mat = bpy.data.materials.new('Clear float glass')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    for node in [n for n in nodes if n.type != 'OUTPUT_MATERIAL']:
        nodes.remove(node)
    clear = nodes.new('ShaderNodeBsdfTransparent')
    reflection = nodes.new('ShaderNodeBsdfGlossy')
    reflection.inputs['Roughness'].default_value = .0
    fresnel = nodes.new('ShaderNodeFresnel')
    fresnel.inputs['IOR'].default_value = 1.52
    pane = nodes.new('ShaderNodeMixShader')
    links.new(fresnel.outputs['Fac'], pane.inputs['Fac'])
    links.new(clear.outputs['BSDF'], pane.inputs[1])
    links.new(reflection.outputs['BSDF'], pane.inputs[2])
    links.new(pane.outputs['Shader'], nodes['Material Output'].inputs['Surface'])
    return mat


# Afternoon sun through the window wall. HEADING is the direction the light
# travels across the floor, in degrees from +x towards +y: it enters through the
# x=0 wall and slants towards the y=0 wall, so the window throws its patch onto
# the boards in front of the camera while the corner stays in skylight.
SUN_ELEVATION_DEG = 38.0
SUN_HEADING_DEG = -35.0
# What the camera sees through the glass: Poly Haven's symmetrical_garden_02, a
# sunny formal garden whose hedges and trees stand far enough away to pass for a
# view at infinity (a photograph of a nearby house would be magnified to fill the
# pane). Its sun sits at pixel u = 0.6002, i.e. azimuth atan2(y, x) =
# (0.5 - u) * 360 = -36.1 deg in the photograph's own frame; the photograph is
# turned so that sun stands where the lamp is. STRENGTH puts the garden a couple
# of stops over the room, bright but legible, the way a phone exposes a room
# with a window in it.
WINDOW_VIEW_SUN_AZIMUTH_DEG = -36.1
WINDOW_VIEW_STRENGTH = 1.0


def daylight(sun_target, window_view):
    """Sun and sky outside, no lamp inside the room.

    All light comes in through the openings: a sun lamp and a physical sky
    whose own sun disc is off, so the lamp is the only sun. There are no
    interior lamps. Camera
    rays that leave through the glass see the garden photograph instead of the
    bare sky gradient, which at an interior exposure is a flat white card.
    """
    el, heading = math.radians(SUN_ELEVATION_DEG), math.radians(SUN_HEADING_DEG)
    travel = Vector((math.cos(el) * math.cos(heading), math.cos(el) * math.sin(heading), -math.sin(el)))
    sun_data = bpy.data.lights.new('Afternoon sun', 'SUN')
    sun_data.energy, sun_data.angle, sun_data.color = 4.2, math.radians(.53), (1., .955, .90)
    sun = bpy.data.objects.new('Afternoon sun', sun_data)
    bpy.context.collection.objects.link(sun)
    sun.location = Vector(sun_target) - 6 * travel
    aim(sun, sun.location + travel)

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
    lighting.inputs['Strength'].default_value = .55

    coord = nodes.new('ShaderNodeTexCoord')
    turn = nodes.new('ShaderNodeMapping')
    turn.vector_type = 'VECTOR'
    # Rotating the lookup vector by theta moves the photograph's content by
    # -theta, so the lamp's direction (towards the sun) is sent to the
    # photograph's own sun azimuth.
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


def sky_portal(name, centre, size, inward):
    """An area-light portal across an opening: Cycles then samples the sky
    through the hole instead of hoping a bounce finds it, which is what keeps a
    daylit room from rendering as grain."""
    data = bpy.data.lights.new(name, 'AREA')
    data.shape = 'RECTANGLE'
    data.size, data.size_y = size
    data.cycles.is_portal = True
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = centre
    aim(obj, Vector(centre) + Vector(inward))
    return obj


def wall_with_opening(name, x_span, y_span, z_span, hole, mat, runs_along='y'):
    """Build a wall panel as four pieces around a rectangular opening.

    A window only reads as part of a wall if the wall has a hole to sit in: the
    reveal then has the full wall thickness behind the joinery, which is what
    tells the eye how deep the wall is. The spans are given as for a wall at
    constant x; runs_along="x" lays the same panel out as a wall at constant y
    (x_span is then its thickness in y and y_span its length in x).
    """
    if runs_along == 'x':
        swap = lambda v: (v[1], v[0], v[2])
        place = lambda n, c, s, m: cube(n, swap(c), swap(s), m)
    else:
        place = cube
    x0, x1 = x_span
    y0, y1 = y_span
    z0, z1 = z_span
    hy0, hy1, hz0, hz1 = hole
    xc, thick = (x0 + x1) / 2, x1 - x0
    place(f'{name} / below opening', (xc, (hy0 + hy1) / 2, (z0 + hz0) / 2),
         (thick, hy1 - hy0, hz0 - z0), mat)
    place(f'{name} / above opening', (xc, (hy0 + hy1) / 2, (hz1 + z1) / 2),
         (thick, hy1 - hy0, z1 - hz1), mat)
    place(f'{name} / before opening', (xc, (y0 + hy0) / 2, (z0 + z1) / 2),
         (thick, hy0 - y0, z1 - z0), mat)
    place(f'{name} / after opening', (xc, (hy1 + y1) / 2, (z0 + z1) / 2),
         (thick, y1 - hy1, z1 - z0), mat)

def window_ring(name, centre, outer_w, outer_h, bar, depth, mat, bevel=.0015):
    """Four members closing a rectangle in the y-z plane, butted, not fused.

    The rails run the full width and the jambs are cut in between them, so no two
    members share a coplanar face: the corners read as joints instead of a decal.
    """
    x0, x1 = depth
    xc, (yc, zc) = (x0 + x1) / 2, centre
    thick = x1 - x0
    cube(f'{name} head', (xc, yc, zc + (outer_h - bar) / 2), (thick, outer_w, bar), mat, bevel)
    cube(f'{name} bottom rail', (xc, yc, zc - (outer_h - bar) / 2), (thick, outer_w, bar), mat, bevel)
    for sign, side in ((-1, 'near jamb'), (1, 'far jamb')):
        cube(f'{name} {side}', (xc, yc + sign * (outer_w - bar) / 2, zc),
             (thick, bar, outer_h - 2 * bar), mat, bevel)

from pcve_assets import asset as _pcve_asset
def build_room(scenario):
    w,d,h = scenario['physics']['room_size']
    wall_paint = plaster('Warm chalk plaster',(.59,.57,.51),.86)
    wall_paint_side = plaster('Muted sage limewash',(.31,.39,.34),.9)
    ceiling_paint = plaster('Ceiling white',(.78,.77,.74),.92)
    trim = material('Painted ivory joinery',(.54,.52,.47),.9,.0003)
    dark = material('Charcoal metal',(.025,.03,.029),.38)
    # The floor runs under the walls: the room is lit from outside, and any
    # seam where two boxes only touch along an edge shows as a pinhole of daylight.
    cube('Floor', (w/2,d/2,-.1),(w+.4,d+.4,.2),floor_material(_pcve_asset('')/'polyhaven'/'basketball_corner_rebound'/scenario['assets']['floor']))
    # The ground outside blocks the sky from below for the light, but the camera
    # looks through it to the garden photograph (see daylight).
    ground = cube('Ground outside', (w/2,d/2,-.35),(200,200,.3),material('Sunlit paving outside',(.30,.29,.26),.9))
    ground.visible_camera = False
    # A window needs a hole to sit in, so wall X is four panels around one:
    # the reveal then has the wall's real thickness to show.
    window_hole = (1.875, 3.225, 1.130, 2.630)
    # The plaster stops 5 mm above the skirting: a shadow-gap skirting, the
    # detail that lets a flush board read as joinery rather than a painted band.
    gap_top = .075
    wall_with_opening('Wall_X / impact face x=0', (-.2, 0.0), (-.1, d + .1), (gap_top, h),
                      window_hole, wall_paint_side)
    cube('Wall_Y / impact face y=0',(w/2,-.1,(h+gap_top)/2),(w,.2,h-gap_top),wall_paint)
    # Flush skirting: faces match the physics planes exactly, no visual protrusion.
    cube('Flush skirting X',(-.1,d/2,.035),(.2,d,.07),trim)
    cube('Flush skirting Y',(w/2,-.1,.035),(w,.2,.07),trim)
    cube('Shadow gap X',(-.11,d/2,(.07+gap_top)/2),(.18,d,gap_top-.07),dark)
    cube('Shadow gap Y',(w/2,-.11,(.07+gap_top)/2),(w,.18,gap_top-.07),dark)
    # Solid masonry behind the corner, where the two walls and their shadow gaps
    # would otherwise leave a 5 mm slot to the outside.
    cube('Outside corner',(-.1,-.1,h/2),(.2,.2,h),wall_paint)
    # Close the room. The camera never sees the ceiling or the two walls behind
    # it, but the daylight does: in an open box it leaks out of the top instead
    # of bouncing back onto the walls, and the shadows go flat. The two walls behind
    # the camera have windows of their own, as a real room does: one in shade, one
    # with sun on the boards out of view. Their bounce is what keeps the corner
    # and the window wall from reading as a backlit cave.
    cube('Ceiling',(w/2,d/2,h+.1),(w+.4,d+.4,.2),ceiling_paint)
    rear_hole = (1.2, 4.4, .8, 2.6)
    wall_with_opening('Far wall x=w', (w, w+.2), (-.2, d+.2), (0, h), rear_hole, wall_paint)
    back_hole = (1.6, 4.2, .8, 2.5)
    wall_with_opening('Far wall y=d', (d, d+.2), (-.2, w+.2), (0, h), back_hole, wall_paint, runs_along='x')
    # A framed print from the shared model library, hung clear of the ball path.
    hang_picture(scenario.get('render', {}).get('picture') or DEFAULT_PICTURE)
    plant = place_plant(scenario.get('render', {}).get('plant') or DEFAULT_PLANT)
    # Outlet is on a part of the wall away from the ball trajectory.
    cube('Outlet face',(.004,2.9,.36),(.008,.085,.085),trim,.003)
    for yy in (2.88,2.92):
        cube('Outlet socket',(.009,yy,.36),(.003,.007,.016),dark,.001)
    # A timber window inside that opening: lined through the full wall thickness,
    # sash set 55 mm into the reveal, glazed in the sash plane.
    sash_paint = material('Eggshell sash paint', (.62, .61, .58), .7, .0)
    trim.node_tree.nodes['Principled BSDF'].inputs['Specular IOR Level'].default_value = .0
    win_y, win_z = 2.55, 1.88
    window_ring('Window sash', (win_y, win_z), 1.354, 1.504, .050, (-.100, -.064), sash_paint, .0008)
    pane = cube('Window glass', (-.082, win_y, win_z), (.006, 1.27, 1.42), window_glass())
    pane.visible_shadow = False
    # The transom runs across; the mullion is cut between it and the rails, so the
    # two never share a front face and every joint stays a joint.
    inner_w, inner_h = 1.354 - .100, 1.504 - .100
    cube('Window transom', (-.082, win_y, win_z), (.036, inner_w, .044), sash_paint, .0008)
    for sign, side in ((1, 'above'), (-1, 'below')):
        cube(f'Window mullion {side}', (-.082, win_y, win_z + sign * (.022 + (inner_h / 2 - .022) / 2)),
             (.036, .044, inner_h / 2 - .022), sash_paint, .0008)
    cube('Window sill', (-.049, win_y, 1.115), (.178, 1.470, .046), trim, .0008)
    hy0, hy1, hz0, hz1 = window_hole
    daylight((-.2, (hy0 + hy1) / 2, (hz0 + hz1) / 2),
             _pcve_asset('')/'polyhaven'/'basketball_corner_rebound'/scenario['assets']['window_view'])
    sky_portal('Window sky portal', (-.21, (hy0 + hy1) / 2, (hz0 + hz1) / 2), (hy1 - hy0, hz1 - hz0), (1, 0, 0))
    ry0, ry1, rz0, rz1 = rear_hole
    sky_portal('Rear window sky portal', (w + .21, (ry0 + ry1) / 2, (rz0 + rz1) / 2), (ry1 - ry0, rz1 - rz0), (-1, 0, 0))
    bx0, bx1, bz0, bz1 = back_hole
    sky_portal('Back window sky portal', ((bx0 + bx1) / 2, d + .21, (bz0 + bz1) / 2), (bx1 - bx0, bz1 - bz0), (0, -1, 0))
    return {'plant': plant}

def import_ball(path, radius):
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported=[o for o in bpy.data.objects if o not in before]
    meshes=[o for o in imported if o.type=='MESH']
    if not meshes:
        raise ValueError('Basketball asset contains no meshes')
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
    ball.name='basketball'
    for poly in ball.data.polygons:
        poly.use_smooth=True
    # The library ball is a 400-vertex sphere whose outline turns into a polygon
    # once the ball is more than a few dozen pixels wide. Subdivide it, then put
    # every vertex back on the physical radius: the silhouette is then the
    # PyBullet GEOM_SPHERE itself, not a smoothed cage that sits inside it.
    smooth=ball.modifiers.new('Round outline','SUBSURF')
    smooth.levels=smooth.render_levels=2
    bpy.ops.object.modifier_apply(modifier=smooth.name)
    for vertex in ball.data.vertices:
        vertex.co=vertex.co.normalized()*radius
    for mat in ball.data.materials:
        if not mat or not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type=='BSDF_PRINCIPLED':
                node.inputs['Emission Strength'].default_value=0
                if not node.inputs['Roughness'].is_linked:
                    node.inputs['Roughness'].default_value=.68
    return ball
