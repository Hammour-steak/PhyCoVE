"""Dining-room corner around the native collision layout (appearance only).

Nothing here reads or writes solver state. The z=0 floor top, the table-leg
registration and every moving body come from the native cache and scene_spec.json;
this module builds the room shell, scanned materials, furniture, daylight and
the fixed camera around them.
"""
from pathlib import Path
import math
import sys

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[2])]
import pcve_realism_kit as kit
from pcve_assets import asset

SCENE_ASSETS = asset('scenes/wood_block_rubber_stop')
POLYHAVEN = asset('polyhaven')
# Swept volume of all six cases (blocks from the left frame edge to the leg, the
# sponge, fast_block's rebound out of frame) plus margin: no prop may enter it.
KEEPOUT = ((-3.2, -0.20, -0.01), (0.26, 0.20, 0.45))
# Room shell (metres). The back wall stands 1.05 m behind the path, 0.4 m
# behind the dining table; daylight enters through a window in the left wall.
X0, X1, Y0, Y1, CEILING = -3.0, 2.2, -3.2, 1.05, 2.6
WINDOW = (-1.7, 0.3, 0.85, 2.15)  # y0, y1, z0, z1 in the x=X0 wall
SKIRTING = (.018, .12)  # depth, height
# Low tripod camera, 0.42 m above the floor, 45 mm: the whole path (block start
# x=-1.39 m to the table leg x=0.22 m) fits with ~0.1 m to spare at either end.
CAMERA = {'location': (-0.59, -2.30, 0.42), 'target': (-0.59, 0.0, 0.14), 'lens_mm': 45.0,
          'sensor_mm': 36.0, 'fstop': 5.6, 'focus': (-0.60, 0.0, 0.06)}


def box(name, low, high, material, bevel=0.0):
    centre = [(a + b) / 2 for a, b in zip(low, high)]
    size = [b - a for a, b in zip(low, high)]
    obj = kit.plain_box(name, centre, size, material)
    if bevel:
        mod = obj.modifiers.new('Edge radius', 'BEVEL')
        mod.width = bevel
        mod.segments = 3
    return obj


def world_uv(obj, axes, tile, offset=(0.0, 0.0)):
    layer = obj.data.uv_layers.active or obj.data.uv_layers.new(name='Metric UV')
    for poly in obj.data.polygons:
        for index in poly.loop_indices:
            v = obj.matrix_world @ obj.data.vertices[obj.data.loops[index].vertex_index].co
            layer.data[index].uv = (v[axes[0]] / tile + offset[0], v[axes[1]] / tile + offset[1])


def image(nodes, links, path, uv, data=False):
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(path), check_existing=True)
    if data:
        tex.image.colorspace_settings.name = 'Non-Color'
    links.new(uv, tex.inputs['Vector'])
    return tex


def principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def oak_floor():
    """Poly Haven Wood Floor (oak planks, 1.7 m tile), satin polyurethane finish."""
    root = POLYHAVEN / 'wood_floor/textures'
    mat = bpy.data.materials.new('Lacquered oak plank floor (Poly Haven wood_floor 4K)')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = principled(mat)
    uv = nodes.new('ShaderNodeTexCoord').outputs['UV']
    diff = image(nodes, links, root / 'wood_floor_diff_4k.jpg', uv)
    arm = image(nodes, links, root / 'wood_floor_arm_4k.jpg', uv, data=True)
    nor = image(nodes, links, root / 'wood_floor_nor_gl_4k.jpg', uv, data=True)
    links.new(diff.outputs['Color'], bs.inputs['Base Color'])
    split = nodes.new('ShaderNodeSeparateColor')
    links.new(arm.outputs['Color'], split.inputs['Color'])
    rough = nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value = .30
    rough.inputs['To Max'].default_value = .55
    links.new(split.outputs['Green'], rough.inputs['Value'])
    links.new(rough.outputs['Result'], bs.inputs['Roughness'])
    normal = nodes.new('ShaderNodeNormalMap')
    normal.inputs['Strength'].default_value = .7
    links.new(nor.outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bs.inputs['Normal'])
    # Thin lacquer coat: the sheen of a sealed floor, broken up by wear below.
    bs.inputs['Coat Weight'].default_value = .25
    bs.inputs['Coat Roughness'].default_value = .18
    kit.add_surface_wear(mat, smudge=.06, grime=.05, scratch=.04, scale=.6)
    return mat


def plaster_wall():
    root = SCENE_ASSETS / 'white_plaster_02_4k'
    mat = bpy.data.materials.new('Painted plaster wall (Poly Haven white_plaster_02 4K)')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = principled(mat)
    uv = nodes.new('ShaderNodeTexCoord').outputs['UV']
    diff = image(nodes, links, root / 'white_plaster_02_diff_4k.jpg', uv)
    rough = image(nodes, links, root / 'white_plaster_02_rough_4k.jpg', uv, data=True)
    nor = image(nodes, links, root / 'white_plaster_02_nor_gl_4k.jpg', uv, data=True)
    paint = nodes.new('ShaderNodeMixRGB')  # Opaque emulsion over the scanned plaster.
    paint.inputs[0].default_value = .86
    paint.inputs[2].default_value = (.77, .74, .69, 1)
    links.new(diff.outputs['Color'], paint.inputs[1])
    links.new(paint.outputs['Color'], bs.inputs['Base Color'])
    remap = nodes.new('ShaderNodeMapRange')
    remap.inputs['To Min'].default_value = .78
    remap.inputs['To Max'].default_value = .94
    links.new(rough.outputs['Color'], remap.inputs['Value'])
    links.new(remap.outputs['Result'], bs.inputs['Roughness'])
    normal = nodes.new('ShaderNodeNormalMap')
    normal.inputs['Strength'].default_value = .55
    links.new(nor.outputs['Color'], normal.inputs['Color'])
    # Hand-applied plaster: broad trowel undulation and a faint roller tone drift.
    coord = nodes.new('ShaderNodeTexCoord')
    wave = nodes.new('ShaderNodeTexNoise')
    wave.inputs['Scale'].default_value = 2.2
    wave.inputs['Detail'].default_value = 6.0
    wave.inputs['Roughness'].default_value = .62
    links.new(coord.outputs['Object'], wave.inputs['Vector'])
    relief = nodes.new('ShaderNodeBump')
    relief.inputs['Strength'].default_value = .35
    relief.inputs['Distance'].default_value = .0015
    links.new(wave.outputs['Fac'], relief.inputs['Height'])
    links.new(normal.outputs['Normal'], relief.inputs['Normal'])
    links.new(relief.outputs['Normal'], bs.inputs['Normal'])
    tone = nodes.new('ShaderNodeMapRange')
    tone.inputs['From Min'].default_value = .35
    tone.inputs['From Max'].default_value = .65
    tone.inputs['To Min'].default_value = .95
    tone.inputs['To Max'].default_value = 1.03
    links.new(wave.outputs['Fac'], tone.inputs['Value'])
    shade = nodes.new('ShaderNodeVectorMath')
    shade.operation = 'SCALE'
    links.new(paint.outputs['Color'], shade.inputs[0])
    links.new(tone.outputs['Result'], shade.inputs['Scale'])
    links.new(shade.outputs['Vector'], bs.inputs['Base Color'])
    return mat


def shell():
    """Floor, four walls with a window opening in the left wall, ceiling, skirting."""
    floor_mat, wall_mat = oak_floor(), plaster_wall()
    white = kit.diffuse('Satin white woodwork', (.80, .79, .76), .42)
    ceiling = kit.diffuse('Ceiling paint', (.82, .81, .79), .9)
    t = .08
    floor = box('Oak plank floor - physical plane z=0', (X0, Y0, -.03), (X1, Y1, 0.0), floor_mat)
    world_uv(floor, (1, 0), 1.7, (.31, .17))  # planks run along x, the direction of travel
    made = [floor]
    walls = [
        box('Back wall', (X0 - t, Y1, 0), (X1 + t, Y1 + t, CEILING), wall_mat),
        box('Right wall', (X1, Y0, 0), (X1 + t, Y1, CEILING), wall_mat),
        box('Front wall', (X0 - t, Y0 - t, 0), (X1 + t, Y0, CEILING), wall_mat),
    ]
    y0, y1, z0, z1 = WINDOW
    walls += [
        box('Window wall below', (X0 - t, Y0, 0), (X0, Y1, z0), wall_mat),
        box('Window wall above', (X0 - t, Y0, z1), (X0, Y1, CEILING), wall_mat),
        box('Window wall near', (X0 - t, Y0, z0), (X0, y0, z1), wall_mat),
        box('Window wall far', (X0 - t, y1, z0), (X0, Y1, z1), wall_mat),
    ]
    for wall in walls:
        axes = (0, 2) if abs(wall.dimensions.y) < abs(wall.dimensions.x) else (1, 2)
        world_uv(wall, axes, 1.0, (.237, .413))
    made += walls
    made.append(box('Ceiling', (X0 - t, Y0 - t, CEILING), (X1 + t, Y1 + t, CEILING + t), ceiling))
    # Skirting boards and the window joinery.
    d, h = SKIRTING
    made += [box('Skirting back', (X0, Y1 - d, 0), (X1, Y1, h), white, .005),
             box('Skirting right', (X1 - d, Y0, 0), (X1, Y1 - d, h), white, .005)]
    f = .055
    made += [box('Window frame bottom', (X0 - t, y0, z0), (X0 + .03, y1, z0 + f), white, .002),
             box('Window frame top', (X0 - t, y0, z1 - f), (X0 + .01, y1, z1), white, .002),
             box('Window frame near', (X0 - t, y0, z0), (X0 + .01, y0 + f, z1), white, .002),
             box('Window frame far', (X0 - t, y1 - f, z0), (X0 + .01, y1, z1), white, .002)]
    return made


def daylight(scene):
    """Sky through the window (Poly Haven HDRI) and the sun; no hidden fill lights."""
    world = bpy.data.worlds.new('Partly cloudy sky (Poly Haven kloofendal_48d_partly_cloudy_puresky 2K)')
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    env = nodes.new('ShaderNodeTexEnvironment')
    env.image = bpy.data.images.load(str(POLYHAVEN / 'kloofendal_48d_partly_cloudy_puresky/kloofendal_48d_partly_cloudy_puresky_2k.hdr'))
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Rotation'].default_value[2] = math.radians(200)
    coord = nodes.new('ShaderNodeTexCoord')
    links.new(coord.outputs['Generated'], mapping.inputs['Vector'])
    links.new(mapping.outputs['Vector'], env.inputs['Vector'])
    links.new(env.outputs['Color'], nodes['Background'].inputs['Color'])
    nodes['Background'].inputs['Strength'].default_value = 4.5
    scene.world = world
    sun = kit.sun('Afternoon sun through the window', (.84, .20, -.50), 4.5, angle_deg=.53, color=(1.0, .94, .84))
    return {'world': 'kloofendal_48d_partly_cloudy_puresky_2k.hdr, strength 4.5', 'sun': 'direction (.84,.20,-.50), 4.5 W/m2, 0.53 deg'}


def table(params):
    """Poly Haven Wooden Table 02; its front-left leg face sits on the IPC leg cuboid (x=0.118 m)."""
    path = SCENE_ASSETS / 'polyhaven_wooden_table_02_4k/wooden_table_02_4k.gltf'
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    parts = [o for o in bpy.context.scene.objects if o not in before]
    root = bpy.data.objects.new('Poly Haven Wooden Table 02 - fixed', None)
    bpy.context.collection.objects.link(root)
    for obj in parts:
        world = obj.matrix_world.copy()
        obj.parent = root
        obj.matrix_world = world
    # Source low front-left leg face x=-0.512877 m -> native cuboid face x=0.118 m.
    root.location = (.630877, .3000, .0002)
    bpy.context.view_layer.update()
    low = min((o.matrix_world @ v.co).z for o in parts if o.type == 'MESH' for v in o.data.vertices)
    root.location.z += .0002 - low
    root['collision_leg_front_x_m'] = float(params['backstop_center_m'][0] - params['backstop_dimensions_m'][0] / 2)
    return root


def textured(name, folder, stem, tint=None, value=1.0, saturation=1.0, rough=(.6, .9), normal=.6, tile=None):
    """Poly Haven scan (diff/arm/nor_gl 2K) on object-space box mapping at its real-world tile size."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = principled(mat)
    coord = nodes.new('ShaderNodeTexCoord')
    scale = nodes.new('ShaderNodeMapping')
    scale.inputs['Scale'].default_value = (1 / tile,) * 3
    links.new(coord.outputs['Object'], scale.inputs['Vector'])

    def tex(kind, data):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(folder / f'{stem}_{kind}_2k.jpg'), check_existing=True)
        node.projection = 'BOX'
        node.projection_blend = .2
        if data:
            node.image.colorspace_settings.name = 'Non-Color'
        links.new(scale.outputs['Vector'], node.inputs['Vector'])
        return node
    diff, arm, nor = tex('diff', False), tex('arm', True), tex('nor_gl', True)
    hsv = nodes.new('ShaderNodeHueSaturation')
    hsv.inputs['Saturation'].default_value = saturation
    hsv.inputs['Value'].default_value = value
    links.new(diff.outputs['Color'], hsv.inputs['Color'])
    colour = hsv.outputs['Color']
    if tint:
        mul = nodes.new('ShaderNodeMixRGB')
        mul.blend_type = 'MULTIPLY'
        mul.inputs[0].default_value = 1.0
        mul.inputs[2].default_value = (*tint, 1)
        links.new(colour, mul.inputs[1])
        colour = mul.outputs['Color']
    links.new(colour, bs.inputs['Base Color'])
    split = nodes.new('ShaderNodeSeparateColor')
    links.new(arm.outputs['Color'], split.inputs['Color'])
    remap = nodes.new('ShaderNodeMapRange')
    remap.inputs['To Min'].default_value, remap.inputs['To Max'].default_value = rough
    links.new(split.outputs['Green'], remap.inputs['Value'])
    links.new(remap.outputs['Result'], bs.inputs['Roughness'])
    nmap = nodes.new('ShaderNodeNormalMap')
    nmap.inputs['Strength'].default_value = normal
    links.new(nor.outputs['Color'], nmap.inputs['Color'])
    links.new(nmap.outputs['Normal'], bs.inputs['Normal'])
    return mat


def leaning_canvas(x, width=.60, height=.45, lean_deg=11.0, yaw_deg=-7.0):
    """A stretched canvas waiting to be hung, leaning on the wall with its back to the room:
    pine stretcher bars (four sides and a centre cross brace), unbleached linen pulled over the
    front and round the edges, folded onto the backs of the bars and held by staples."""
    pine = textured('Stretcher bars - raw pine (Poly Haven coated_pine 2K, lightened)', POLYHAVEN / 'coated_pine/textures',
                    'coated_pine', tint=(1.0, .90, .74), value=2.6, saturation=.40, rough=(.7, .9), normal=.5, tile=.74)
    linen = textured('Canvas - unbleached linen (Poly Haven rough_linen 2K weave)', POLYHAVEN / 'rough_linen/textures',
                     'rough_linen', tint=(.66, .58, .45), value=1.0, saturation=0.0, rough=(.85, .97), normal=.9, tile=.27)
    steel = kit.diffuse('Canvas staples - galvanised steel', (.42, .42, .40), .35)
    steel.node_tree.nodes['Principled BSDF'].inputs['Metallic'].default_value = 1.0
    root = bpy.data.objects.new('Leaning canvas (back to the room)', None)
    bpy.context.collection.objects.link(root)
    w, h, d, bar, t = width, height, .032, .042, .0012
    parts = []

    def add(name, low, high, mat, bevel=0.0):
        obj = box(name, low, high, mat, bevel)
        obj.parent = root
        parts.append(obj)
        return obj
    # Local frame: x across, z up, y from the back (y=0, facing the room) to the front (y=d+t, facing the wall).
    add('Canvas face (linen, inside visible between bars)', (-w / 2, d, 0), (w / 2, d + t, h), linen)
    # linen wrapped round the four edges
    add('Canvas wrap left', (-w / 2 - t, -t, 0), (-w / 2, d + t, h), linen)
    add('Canvas wrap right', (w / 2, -t, 0), (w / 2 + t, d + t, h), linen)
    add('Canvas wrap bottom', (-w / 2 - t, -t, -t), (w / 2 + t, d + t, 0), linen)
    add('Canvas wrap top', (-w / 2 - t, -t, h), (w / 2 + t, d + t, h + t), linen)
    add('Stretcher bar left', (-w / 2, 0, 0), (-w / 2 + bar, d, h), pine, .002)
    add('Stretcher bar right', (w / 2 - bar, 0, 0), (w / 2, d, h), pine, .002)
    add('Stretcher bar bottom', (-w / 2 + bar, 0, 0), (w / 2 - bar, d, bar), pine, .002)
    add('Stretcher bar top', (-w / 2 + bar, 0, h - bar), (w / 2 - bar, d, h), pine, .002)
    add('Stretcher cross brace', (-w / 2 + bar, .003, h / 2 - bar / 2), (w / 2 - bar, d, h / 2 + bar / 2), pine, .002)
    fold = .016  # linen turned over onto the back of the outer bars
    add('Canvas fold left', (-w / 2, -t, 0), (-w / 2 + fold, 0, h), linen)
    add('Canvas fold right', (w / 2 - fold, -t, 0), (w / 2, 0, h), linen)
    add('Canvas fold bottom', (-w / 2 + fold, -t, 0), (w / 2 - fold, 0, fold), linen)
    add('Canvas fold top', (-w / 2 + fold, -t, h - fold), (w / 2 - fold, 0, h), linen)
    for i in range(9):  # staples across the folded linen, about 65 mm apart
        u = -w / 2 + .04 + i * (w - .08) / 8
        for z0 in (.008, h - .008):
            add('Staple', (u - .006, -t - .0005, z0 - .0007), (u + .006, -t, z0 + .0007), steel)
    for j in range(6):
        v = .04 + j * (h - .08) / 5
        for u0 in (-w / 2 + .008, w / 2 - .008):
            add('Staple', (u0 - .0007, -t - .0005, v - .006), (u0 + .0007, -t, v + .006), steel)
    root.location = (x, 0.0, 0.0)
    # Top towards the wall (+y), turned a little so one top corner rests on the wall.
    root.rotation_euler = (math.radians(-lean_deg), 0.0, math.radians(yaw_deg))
    bpy.context.view_layer.update()
    low, high = kit.world_bbox(parts)
    root.location.z -= low.z  # the lowest (wall-side bottom) edge rests on the floor
    root.location.y += Y1 - .0005 - high.y  # the top edge touches the wall above the skirting
    bpy.context.view_layer.update()
    audit = kit.assert_clear(parts, KEEPOUT, 'leaning canvas')
    audit['construction'] = f'{width:.2f} x {height:.2f} m stretched linen on 42 x 32 mm pine bars with a cross brace, stapled on the back, leaning {lean_deg:.0f} deg, turned {yaw_deg:.0f} deg'
    return audit


def furniture():
    """Scanned props standing on the floor along the back wall, well clear of the path."""
    wall = Y1 - SKIRTING[0]
    props = [  # name, bottom-centre location, yaw, tilt
        ('wooden_display_shelves_01', (-1.62, wall - .19, 0.0), 0.0, None),
        ('wicker_basket_02', (-.27, wall - .17, 0.0), -.25, None),
        ('wooden_stool_02', (-1.28, wall - .14, 0.0), .35, None),
    ]
    audit = []
    for name, location, rot, tilt in props:
        path = next((POLYHAVEN / name).glob('*.gltf'))
        root, members = kit.import_prop(path, 'Furniture ' + name, location, rot, tilt=tilt)
        audit.append(kit.assert_clear(members, KEEPOUT, name))
    audit.append(leaning_canvas(-.78))
    return audit


def camera(scene, focus_object=None):
    data = bpy.data.cameras.new('Fixed tripod camera')
    cam = bpy.data.objects.new('Fixed tripod camera', data)
    scene.collection.objects.link(cam)
    cam.location = CAMERA['location']
    cam.rotation_euler = (Vector(CAMERA['target']) - Vector(CAMERA['location'])).to_track_quat('-Z', 'Y').to_euler()
    data.lens = CAMERA['lens_mm']
    data.sensor_width = CAMERA['sensor_mm']
    data.sensor_fit = 'HORIZONTAL'
    data.dof.use_dof = True
    data.dof.aperture_fstop = CAMERA['fstop']
    data.dof.focus_distance = (Vector(CAMERA['focus']) - Vector(CAMERA['location'])).length
    scene.camera = cam
    return cam


def build(scene, params):
    report = {'shell': [o.name for o in shell()], 'daylight': daylight(scene)}
    report['table'] = table(params).name
    report['furniture'] = furniture()
    camera(scene)
    report['camera'] = CAMERA
    report['assets'] = ['https://polyhaven.com/a/' + i for i in (
        'wood_floor', 'white_plaster_02', 'wooden_table_02', 'wooden_display_shelves_01', 'wooden_stool_02',
        'wicker_basket_02', 'coated_pine', 'rough_linen', 'kloofendal_48d_partly_cloudy_puresky', 'dark_wood')]
    return report
