"""Measured kitchen materials and detailed static props around frozen fluid caches."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
from pathlib import Path
import json
import math
import random

import bpy
from mathutils import Matrix, Vector


def material(name, color, roughness=.4, metallic=0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    return mat


def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def box(name, location, size, mat, bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign(obj, mat)
    if bevel:
        edge = obj.modifiers.new('Small manufactured edge radius', 'BEVEL')
        edge.width = bevel
        edge.segments = 3
        obj.modifiers.new('Planar normals', 'WEIGHTED_NORMAL')
    return obj


def curve(name, points, radius, mat, cyclic=False):
    data = bpy.data.curves.new(name, 'CURVE')
    data.dimensions = '3D'
    data.resolution_u = 2
    data.bevel_depth = radius
    data.bevel_resolution = 3
    spline = data.splines.new('POLY')
    spline.points.add(len(points)-1)
    for point, co in zip(spline.points, points):
        point.co = (*co, 1)
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    data.materials.append(mat)
    return obj


def texture(mat, path, colorspace):
    node = mat.node_tree.nodes.new('ShaderNodeTexImage')
    node.image = bpy.data.images.load(str(path), check_existing=True)
    node.image.colorspace_settings.name = colorspace
    return node


def oak_material(assets):
    mat = material('Fine white oak, satin kitchen finish', (.4, .28, .15), .43)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    uv = nodes.new('ShaderNodeTexCoord')
    base = Path(assets)/'white_oak_veneer'
    color = texture(mat, base/'white_oak_veneer_diff_4k.jpg', 'sRGB')
    rough = texture(mat, base/'white_oak_veneer_rough_4k.jpg', 'Non-Color')
    normal = texture(mat, base/'white_oak_veneer_nor_gl_4k.jpg', 'Non-Color')
    for node in (color, rough, normal):
        links.new(uv.outputs['UV'], node.inputs['Vector'])
    links.new(color.outputs['Color'], bsdf.inputs['Base Color'])
    remap = nodes.new('ShaderNodeMapRange')
    remap.inputs['To Min'].default_value = .38
    remap.inputs['To Max'].default_value = .52
    links.new(rough.outputs['Color'], remap.inputs['Value'])
    links.new(remap.outputs[0], bsdf.inputs['Roughness'])
    bump = nodes.new('ShaderNodeNormalMap')
    bump.inputs['Strength'].default_value = .055
    links.new(normal.outputs['Color'], bump.inputs['Color'])
    links.new(bump.outputs[0], bsdf.inputs['Normal'])
    bsdf.inputs['Coat Weight'].default_value = .12
    bsdf.inputs['Coat Roughness'].default_value = .34
    return mat


def metric_uv(obj, width=.5):
    """Project each planar box face in metres; no Generated-coordinate stretch."""
    uv = obj.data.uv_layers.active or obj.data.uv_layers.new(name='Metric wood UV')
    for polygon in obj.data.polygons:
        axis = max(range(3), key=lambda i: abs(polygon.normal[i]))
        pair = ((1, 2), (0, 2), (0, 1))[axis]
        for index in polygon.loop_indices:
            co = obj.matrix_world @ obj.data.vertices[obj.data.loops[index].vertex_index].co
            uv.data[index].uv = ((co[pair[0]]+.183)/width, (co[pair[1]]+.271)/width)


def porcelain():
    mat = material('Ivory porcelain with smooth clear glaze', (.72, .69, .63), .16)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    bsdf.inputs['Coat Weight'].default_value = .28
    bsdf.inputs['Coat Roughness'].default_value = .13
    coordinates = nodes.new('ShaderNodeTexCoord')
    fine = nodes.new('ShaderNodeTexNoise')
    fine.inputs['Scale'].default_value = 3200
    fine.inputs['Detail'].default_value = 2
    links.new(coordinates.outputs['Object'], fine.inputs['Vector'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Distance'].default_value = .000008
    bump.inputs['Strength'].default_value = .12
    links.new(fine.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs[0], bsdf.inputs['Normal'])
    return mat


def append_meshes(path, selector):
    """Bake selected authored meshes and preserve evaluated world transforms."""
    with bpy.data.libraries.load(str(path), link=False) as (source, loaded):
        loaded.objects = source.objects
    originals = [obj for obj in loaded.objects if obj]
    for obj in originals:
        bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.update()
    result = []
    graph = bpy.context.evaluated_depsgraph_get()
    for obj in originals:
        if obj.type == 'MESH' and selector(obj.name):
            mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(graph), depsgraph=graph)
            mesh.transform(obj.matrix_world)
            copy = bpy.data.objects.new('Authored '+obj.name, mesh)
            bpy.context.collection.objects.link(copy)
            result.append(copy)
    for obj in originals:
        bpy.data.objects.remove(obj, do_unlink=True)
    if not result:
        raise RuntimeError(f'No matching meshes in {path}')
    return result


def bounds(objects):
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    points = []
    for obj in objects:
        evaluated = obj.evaluated_get(graph)
        points.extend(evaluated.matrix_world @ Vector(point) for point in evaluated.bound_box)
    return [Vector(tuple(min(p[i] for p in points) for i in range(3))),
            Vector(tuple(max(p[i] for p in points) for i in range(3)))]


def place_group(objects, position, rotation=(0, 0, 0), scale=1):
    transform = Matrix.Translation(Vector(position)) @ Matrix.Rotation(rotation[2], 4, 'Z') @ Matrix.Rotation(rotation[1], 4, 'Y') @ Matrix.Rotation(rotation[0], 4, 'X') @ Matrix.Scale(scale, 4)
    for obj in objects:
        obj.matrix_world = transform
    low, high = bounds(objects)
    for obj in objects:
        obj.location.z -= low.z-position[2]
    return {'bounds_m': [list(v) for v in bounds(objects)], 'scale': scale}


def folded_linen(assets):
    originals = append_meshes(Path(assets)/'kitchen_towel/kitchen_towel.blend', lambda name: name == 'Towel')
    fabric = next(mat for obj in originals for mat in obj.data.materials if mat and 'Fabric' in mat.name)
    for obj in originals:
        bpy.data.objects.remove(obj, do_unlink=True)
    length, width, radius = .175, .145, .0013
    path = []
    for layer in range(3):
        for i in range(61):
            u = i/60
            x = (-length/2+u*length) * (-1 if layer == 1 else 1)
            path.append((x, .00065+2*radius*layer, float(layer)))
        if layer < 2:
            for i in range(1, 25):
                angle = math.pi*i/24
                sign = 1 if layer == 0 else -1
                path.append((sign*(length/2+radius*math.sin(angle)), .00065+2*radius*layer+radius*(1-math.cos(angle)), layer+i/24))
    vertices, faces, coordinates = [], [], []
    ny = 71
    for index, (x, z, layer) in enumerate(path):
        u = index/(len(path)-1)
        for j in range(ny):
            v = j/(ny-1)
            edge = math.sin(math.pi*v)
            y = (v-.5)*width + .0005*math.sin(u*9+v*2)*edge
            wrinkle = (.0002+.00025*layer)*edge*math.sin(8*math.pi*v+2.6*math.pi*u)
            wrinkle += .00025*layer*edge*math.exp(-((v-.34)/.13)**2)*math.sin(9*u)
            vertices.append((x, y, z+wrinkle))
            coordinates.append((u, v))
    for i in range(len(path)-1):
        for j in range(ny-1):
            k = i*ny+j
            faces.append((k, k+ny, k+ny+1, k+1))
    mesh = bpy.data.meshes.new('Three folds with curved fabric edges')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv = mesh.uv_layers.new(name='Original woven cloth UV')
    for loop in mesh.loops:
        uv.data[loop.index].uv = coordinates[loop.vertex_index]
    obj = bpy.data.objects.new('Folded woven kitchen towel', mesh)
    bpy.context.collection.objects.link(obj)
    cloth_transform = Matrix.Translation(Vector((-.205, .033, 0))) @ Matrix.Rotation(-.23, 4, 'Z')
    obj.matrix_world = cloth_transform
    assign(obj, fabric)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    solid = obj.modifiers.new('Fabric thickness 0.4 mm', 'SOLIDIFY')
    solid.thickness = .0004
    seam = material('Linen edge stitching', (.32, .30, .26), .85)
    for j in (0, ny-1):
        points = [vertices[i*ny+j] for i in range(len(path))]
        hem = curve('Sewn fabric border', points, .00017, seam)
        hem.matrix_world = cloth_transform
    return {'bounds_m': [list(v) for v in bounds([obj])], 'three_layers': True, 'authored_fabric_material': True}


def cup_handle(mug, mat):
    old = bpy.data.objects.get('CeramicCupHandle')
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    angle = math.radians(-132)
    radial = Vector((math.cos(angle), math.sin(angle), 0))
    # A rounded D-shaped handle with two attachment pads, away from the low rim.
    points = []
    for i in range(81):
        a = -math.pi/2+math.pi*i/80
        distance = .0355+.024*math.cos(a)
        z = .0162*math.sin(a)
        points.append(tuple(radial*distance+Vector((0, 0, z))))
    handle = curve('CeramicCupHandle', points, .0033, mat)
    handle.matrix_world = mug.matrix_world
    for z in (-.0162, .0162):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16)
        pad = bpy.context.object
        pad.name = 'Glazed handle attachment'
        pad.scale = (.0041, .0041, .005)
        pad.matrix_world = mug.matrix_world @ Matrix.Translation(radial*.0357+Vector((0, 0, z))) @ Matrix.Diagonal(Vector((.0041, .0041, .005, 1)))
        assign(pad, mat)
        for face in pad.data.polygons:
            face.use_smooth = True


def tile_backdrop():
    rng = random.Random(20261028)
    grout = material('Warm lime grout', (.42, .40, .35), .86)
    box('Continuous recessed grout bed', (.16, .302, .145), (1.6, .010, .29), grout)
    for row in range(4):
        for col in range(12):
            x = -.67+col*.150+(row % 2)*.075
            value = rng.uniform(.58, .61)
            mat = material('Hand glazed ivory tile', (value, value*.985, value*.945), rng.uniform(.22, .30))
            ns, ls = mat.node_tree.nodes, mat.node_tree.links
            shader = ns.get('Principled BSDF')
            shader.inputs['Coat Weight'].default_value = .18
            shader.inputs['Coat Roughness'].default_value = .22
            tc = ns.new('ShaderNodeTexCoord')
            noise = ns.new('ShaderNodeTexNoise')
            noise.inputs['Scale'].default_value = 65
            noise.inputs['Detail'].default_value = 2
            bump = ns.new('ShaderNodeBump')
            bump.inputs['Distance'].default_value = .00010
            bump.inputs['Strength'].default_value = .18
            ls.new(tc.outputs['Object'], noise.inputs['Vector'])
            ls.new(noise.outputs['Fac'], bump.inputs['Height'])
            ls.new(bump.outputs[0], shader.inputs['Normal'])
            box('Glazed tile', (x, .3008+rng.uniform(-.00012, .00012), .0375+row*.075), (.1482, .0095, .0732), mat, .0007)
    box('Thin counter seal', (.15, .2953, .00085), (1.6, .0015, .0017), grout, .0005)


def turned_surface(name, profile, mat, location, segments=128):
    vertices = [(r*math.cos(i*2*math.pi/segments), r*math.sin(i*2*math.pi/segments), z)
                for r, z in profile for i in range(segments)]
    faces = [(j*segments+i, j*segments+(i+1)%segments, (j+1)*segments+(i+1)%segments, (j+1)*segments+i)
             for j in range(len(profile)-1) for i in range(segments)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    assign(obj, mat)
    for face in mesh.polygons:
        face.use_smooth = True
    return obj


def coffee_jar(assets):
    glass = material('Clear storage glass, 1.4 mm wall', (.97, .99, 1), .065)
    shader = glass.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Transmission Weight'].default_value = 1
    shader.inputs['IOR'].default_value = 1.47
    centre = Vector((-.352, .227, 0))
    profile = [(.0001, .001), (.029, .001), (.033, .003), (.034, .007), (.034, .080),
               (.031, .086), (.030, .098), (.0286, .098), (.0296, .086), (.0326, .079),
               (.0326, .007), (.029, .003), (.0001, .003)]
    jar = turned_surface('Glass coffee storage jar', profile, glass, centre)
    lid_mat = material('Black satin screw lid', (.026, .024, .019), .34, .62)
    lid = turned_surface('Rolled metal jar lid', [(.0001, 0), (.031, 0), (.032, .002),
                           (.032, .008), (.030, .0095), (.0001, .0095)], lid_mat, centre+Vector((0, 0, .097)))
    for z in (.098, .101):
        points = [tuple(centre+Vector((.0321*math.cos(t), .0321*math.sin(t), z))) for t in [i*math.tau/128 for i in range(128)]]
        curve('Fine lid rolled edge', points, .00035, lid_mat, True)
    beans = append_meshes(Path(assets)/'coffee_cup_set/coffee_cup_set.blend', lambda name: name in ('coffee bean.000', 'coffee bean.001', 'coffee bean.002'))
    for obj in beans:
        low, high = bounds([obj])
        obj.data.transform(Matrix.Translation(-(low+high)/2))
    rng = random.Random(5418)
    for layer in range(12):
        for ix in range(-3, 4):
            for iy in range(-3, 4):
                x = ix*.009 + (layer % 2)*.003
                y = iy*.009
                if x*x+y*y > .0255**2:
                    continue
                source = beans[rng.randrange(len(beans))]
                obj = bpy.data.objects.new('Roasted coffee bean', source.data)
                bpy.context.collection.objects.link(obj)
                obj.location = centre+Vector((x+rng.uniform(-.001, .001), y+rng.uniform(-.001, .001), .006+layer*.0053))
                obj.rotation_euler = (rng.uniform(-.35, .35), rng.uniform(-.35, .35), rng.uniform(0, math.tau))
                obj.scale = (rng.uniform(.91, 1.07),)*3
    for obj in beans:
        bpy.data.objects.remove(obj, do_unlink=True)
    return {'bounds_m': [list(v) for v in bounds([jar, lid])], 'bean_meshes': 'authored coffee cup set, instantiated inside glass vessel'}


def room_and_window(scene):
    wall = material('Soft warm white room paint', (.66, .65, .61), .86)
    frame = material('Painted timber window frame', (.72, .71, .66), .36)
    box('Right room bounce wall', (.90, -.10, .45), (.04, 2.4, 2.8), wall)
    box('Ceiling bounce', (0, 0, 1.7), (3, 3, .04), wall)
    box('Kitchen floor', (0, 0, -.90), (3, 3, .04), wall)
    for name, y, z, sy, sz in [('below', .05, -.365, 1.8, 1.03), ('above', .05, 1.39, 1.8, .68), ('near', -.535, .60, .45, .90), ('far', .635, .60, .45, .90)]:
        box('Window wall '+name, (-.79, y, z), (.04, sy, sz), wall)
    for y in (-.31, .41):
        box('Window vertical frame', (-.765, y, .60), (.025, .023, .94), frame, .002)
    for z in (.15, 1.05):
        box('Window horizontal frame', (-.765, .05, z), (.025, .75, .025), frame, .002)
    box('Window centre mullion', (-.765, .05, .60), (.028, .018, .9), frame, .002)
    bpy.ops.object.light_add(type='AREA', location=(-.77, .05, .60))
    key = bpy.context.object
    key.name = 'Daylight through kitchen window'
    key.data.shape = 'RECTANGLE'
    key.data.size = .70
    key.data.size_y = .88
    key.data.energy = 48
    key.data.color = (1.0, .967, .915)
    key.rotation_euler = Vector((1, 0, 0)).to_track_quat('-Z', 'Y').to_euler()
    scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value = .11


def apply(scene, assets):
    assets = Path(assets)
    protected = {'RealScaleWoodTable', 'SquareCupSupport', 'MeasuredCeramicCup', 'GenesisWater', 'Camera'}
    for obj in list(bpy.data.objects):
        if obj.name not in protected:
            bpy.data.objects.remove(obj, do_unlink=True)
    oak = oak_material(assets)
    table = bpy.data.objects['RealScaleWoodTable']
    metric_uv(table)
    assign(table, oak)
    support = bpy.data.objects['SquareCupSupport']
    mug = bpy.data.objects['MeasuredCeramicCup']
    from ceramic_wood_details import apply as refine_cup_and_support
    hero = refine_cup_and_support(mug, support)
    tile_backdrop()
    cloth = folded_linen(assets)
    dishes = append_meshes(assets/'coffee_cup_set/coffee_cup_set.blend', lambda name: name.startswith('plate.') or name.startswith('spoon.'))
    dish_ledger = place_group(dishes, (-.058, .222, 0), rotation=(0, 0, .24))
    board = append_meshes(assets/'cutting_board/cutting_board.blend', lambda name: 'Wooden Cutting Board' in name)
    board_ledger = place_group(board, (-.207, .247, 0), rotation=(math.radians(76), 0, math.radians(-4)), scale=.95)
    jar_ledger = coffee_jar(assets)
    room_and_window(scene)
    scene.camera.data.dof.aperture_fstop = 11
    water_nodes = bpy.data.objects['GenesisWater'].data.materials[0].node_tree.nodes
    for node in water_nodes:
        if node.type == 'BSDF_PRINCIPLED':
            node.inputs['Base Color'].default_value = (1, 1, 1, 1)
            node.inputs['Roughness'].default_value = .018
    missing = [im.filepath for im in bpy.data.images if im.source == 'FILE' and not im.packed_file and im.filepath and not Path(bpy.path.abspath(im.filepath)).is_file()]
    if missing:
        raise FileNotFoundError(missing)
    return {'name': 'refined_kitchen',
            'asset_manifest': json.loads((assets/'asset_manifest.json').read_text()),
            'texture_width_m': .5, 'normal_strength': .055,
            'cloth': cloth, 'dishes': dish_ledger, 'cutting_board': board_ledger, 'coffee_jar': jar_ledger,
            'liquid_coordinates_modified': False, 'body_and_support_pose_modified': False,
            'cup_body_contact_geometry_modified': False,
            'cup_and_support_details': hero,
            'cup_visual_mesh_refined': True,
            'appearance_only': True}
