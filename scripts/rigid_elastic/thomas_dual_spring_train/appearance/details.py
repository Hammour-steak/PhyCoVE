"""Remote appearance details, in metres. No dynamic transforms or physics edits."""
import math
import bpy
from mathutils import Vector

base = None


def configure(scene_helpers):
    global base
    base = scene_helpers


def profile_rail(name, length, thickness, wood):
    """A single milled cross section, including the actual 3 mm deep grooves."""
    y0, y1, y2 = .0365, .0243, .0153
    top, bed = thickness, thickness - .003
    cross = [(-y0, 0), (y0, 0), (y0, top), (y1, top),
             (y1, bed), (y2, bed), (y2, top), (-y2, top),
             (-y2, bed), (-y1, bed), (-y1, top), (-y0, top)]
    n = len(cross)
    vertices = [(x, y, z) for x in [-length / 2, length / 2] for y, z in cross]
    faces = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    faces += [(j, (j + 1) % n, (j + 1) % n + n, j + n) for j in range(n)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    mesh.materials.append(wood)
    o = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(o)
    return o


def cut(o, cutter):
    modifier = o.modifiers.new('Machined recess', 'BOOLEAN')
    modifier.operation = 'DIFFERENCE'
    modifier.solver = 'EXACT'
    modifier.object = cutter
    bpy.context.view_layer.objects.active = o
    while o.modifiers.find(modifier.name)>0:
        bpy.ops.object.modifier_move_up(modifier=modifier.name)
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def round_edges(o, radius):
    bevel = o.modifiers.new('Sanded edge radius', 'BEVEL')
    bevel.width = radius
    bevel.segments = 4
    bevel.affect = 'EDGES'
    o.modifiers.new('Machined face normals', 'WEIGHTED_NORMAL')


def connectors(o, length, thickness, wood, male=True, female=True):
    # The join sits in the central land, outside both wheel paths.
    if female:
        x = -length / 2 + .0056
        cutter = base.cyl('Temporary round socket', (x, 0, thickness / 2),
                          .0078, thickness + .008, wood, segments=64)
        cut(o, cutter)
        cutter = base.box('Temporary socket neck', (-length / 2 + .002, 0, thickness / 2),
                          (.009, .0076, thickness + .008), wood, 0)
        cut(o, cutter)
    if male:
        head = base.cyl('Wood puzzle head ' + o.name, (length / 2 + .006, 0, thickness / 2),
                        .0075, thickness, wood, segments=64)
        neck = base.box('Wood puzzle neck ' + o.name, (length / 2 + .0015, 0, thickness / 2),
                        (.011, .007, thickness), wood, .00035)
        for part in [head, neck]:
            part.parent = o
    round_edges(o, .00042)


def make_track(wood):
    for j in range(4):
        rail = profile_rail('Milled running track ' + str(j), .2696, .012, wood)
        connectors(rail, .2696, .012, wood, male=j < 3, female=j > 0)
        rail.location = (-.405 + j * .270, 0, base.TABLE)


def make_props(wood):
    for j in range(2):
        rail = profile_rail('Spare wooden rail ' + str(j), .235, .016, wood)
        connectors(rail, .235, .016, wood)
        rail.location = (-.27 + j * .07, .285 + j * .035, base.TABLE + j * .016)
        rail.rotation_euler[2] = .08 + j * .17
    colors = [(.48, .10, .065), (.12, .30, .38), (.68, .43, .12)]
    for j, color in enumerate(colors):
        material = base.finish(base.mat('Worn painted block ' + str(j), color, .48),
                               4500, .000018, .12)
        block = base.box('Toy block background ' + str(j),
                         (.28 + j * .055, .275 + (j % 2) * .05, base.TABLE + .026),
                         (.048, .048, .052), material, .0016)
        block.rotation_euler[2] = [.16, -.10, .23][j]


def shader_trees(tree, seen=None):
    seen = set() if seen is None else seen
    if tree is None or tree.as_pointer() in seen:
        return
    seen.add(tree.as_pointer())
    yield tree
    for node in tree.nodes:
        if node.type == 'GROUP':
            yield from shader_trees(node.node_tree, seen)


def vary_roughness(tree, bs, lower, upper, scale):
    nodes, links = tree.nodes, tree.links
    coord = nodes.new('ShaderNodeTexCoord')
    vector = nodes.new('ShaderNodeVectorMath')
    vector.operation = 'MULTIPLY'
    vector.inputs[1].default_value = scale
    links.new(coord.outputs['Object'], vector.inputs[0])
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 1
    noise.inputs['Detail'].default_value = 3
    links.new(vector.outputs[0], noise.inputs['Vector'])
    remap = nodes.new('ShaderNodeMapRange')
    remap.inputs['To Min'].default_value = lower
    remap.inputs['To Max'].default_value = upper
    links.new(noise.outputs['Fac'], remap.inputs['Value'])
    links.new(remap.outputs['Result'], bs.inputs['Roughness'])
    return noise


def shader_bevel(tree, bs, radius):
    bevel = tree.nodes.new('ShaderNodeBevel')
    bevel.samples = 3
    bevel.inputs['Radius'].default_value = radius
    if bs.inputs['Normal'].is_linked:
        tree.links.new(bs.inputs['Normal'].links[0].from_socket, bevel.inputs['Normal'])
    tree.links.new(bevel.outputs['Normal'], bs.inputs['Normal'])


def constant(tree, bs, name, value):
    for link in list(bs.inputs[name].links):
        tree.links.remove(link)
    bs.inputs[name].default_value = value


def surface_finishes(scene, record):
    table_materials = set()
    train_materials = set()
    for o in scene.objects:
        if o.type != 'MESH':
            continue
        ancestor = o
        while ancestor.parent:
            ancestor = ancestor.parent
        if ancestor.name == 'TRAIN_ROOT':
            train_materials.update(m for m in o.data.materials if m)
        if o.name in record['table_objects']:
            table_materials.update(m for m in o.data.materials if m)
    for material in table_materials:
        print('APPEARANCE_TABLE_MATERIAL',material.name,flush=True)
        for tree in shader_trees(material.node_tree):
            for bs in list(tree.nodes):
                if bs.type != 'BSDF_PRINCIPLED':
                    continue
                vary_roughness(tree, bs, .36, .49, (8, 180, 55))
                constant(tree, bs, 'Coat Weight', .10)
                constant(tree, bs, 'Coat Roughness', .30)
                constant(tree, bs, 'IOR', 1.47)
                shader_bevel(tree, bs, .00018)
                if bs.inputs['Base Color'].is_linked:
                    old = bs.inputs['Base Color'].links[0].from_socket
                    hue = tree.nodes.new('ShaderNodeHueSaturation')
                    hue.inputs['Saturation'].default_value = .82
                    tree.links.new(old, hue.inputs['Color'])
                    tree.links.new(hue.outputs['Color'], bs.inputs['Base Color'])
    for material in train_materials:
        print('APPEARANCE_TRAIN_MATERIAL',material.name,flush=True)
        for tree in shader_trees(material.node_tree):
            for bs in list(tree.nodes):
                if bs.type != 'BSDF_PRINCIPLED':
                    continue
                vary_roughness(tree, bs, .28, .37, (90, 380, 180))
                bs.inputs['Coat Weight'].default_value = .14
                bs.inputs['Coat Roughness'].default_value = .24
                shader_bevel(tree, bs, .00010)
    for material in bpy.data.materials:
        if not material.use_nodes:
            continue
        bs = material.node_tree.nodes.get('Principled BSDF')
        if bs is None:
            continue
        if material.name.startswith('Cold drawn polished'):
            vary_roughness(material.node_tree, bs, .22, .29, (300, 1400, 1400))
        if material.name.startswith('Brushed aluminium'):
            vary_roughness(material.node_tree, bs, .32, .41, (25, 1800, 120))
            for name in ['Anisotropic IOR Level', 'Anisotropic']:
                if name in bs.inputs:
                    bs.inputs[name].default_value = .5
                    break
        if material.name.startswith('Chromed guide'):
            bs.inputs['Roughness'].default_value = .24
        if material.name.startswith('Scanned oak floor'):
            # Refinished timber, with quiet rather than mirror-like reflections.
            bs.inputs['Coat Weight'].default_value = .03
            bs.inputs['Coat Roughness'].default_value = .38


def screw(name, pos, material):
    head = base.cyl(name, pos, .00215, .0007, material, segments=48)
    for angle in [0, math.pi / 2]:
        slot = base.box('Temporary driver recess', (pos[0], pos[1], pos[2] + .0003),
                        (.0027, .00046, .00065), material, 0)
        slot.rotation_euler.z = angle
        cut(head, slot)
    return head


def assembly_details(config):
    steel = base.mat('Zinc plated fasteners', (.41, .43, .45), .32, 1)
    bronze = base.mat('Oil bronze guide bushings', (.32, .22, .11), .37, 1)
    for side, sign in [('left', 1), ('right', -1)]:
        anchor = -sign * .440
        # Side feet bridge the 3 mm gap between the wooden plinth and backplate,
        # outside the 73 mm rail. Nothing is added to a dynamic contact face.
        for y in [-.0405, .0405]:
            base.box(side + ' steel mounting foot ' + str(y),
                     (anchor - sign * .012, y, base.TABLE + .0075),
                     (.025, .007, .003), steel, .00035)
            screw(side + ' mounting foot fastener ' + str(y),
                  (anchor - sign * .022, y, base.TABLE + .009), steel)
        for y in [-.046, .046]:
            screw(side + ' plinth countersunk wood screw ' + str(y),
                  (anchor - sign * .012, y, base.TABLE + .006), steel)
        for y in [-.034, .034]:
            # Static sleeves on the fixed plate, concentric with the real rods.
            collar = base.cyl(side + ' fixed guide bushing ' + str(y),
                              (anchor + sign * .0015, y, base.RUN + .024),
                              .0033, .003, bronze, 'X', segments=64)
            cutter = base.cyl('Temporary bushing bore',
                              (anchor + sign * .0015, y, base.RUN + .024),
                              .00202, .009, bronze, 'X', segments=48)
            cut(collar, cutter)


def room_finish(scene):
    for material in bpy.data.materials:
        if not material.name.startswith('Scanned painted plaster'):
            continue
        tree = material.node_tree
        bs = tree.nodes.get('Principled BSDF')
        for node in tree.nodes:
            if node.type == 'NORMAL_MAP':
                node.inputs['Strength'].default_value = .16
        old = bs.inputs['Base Color'].links[0].from_socket
        paint = tree.nodes.new('ShaderNodeMixRGB')
        paint.name = 'Opaque warm white paint over fine plaster scan'
        paint.inputs[0].default_value = .60
        paint.inputs[2].default_value = (.70, .715, .69, 1)
        tree.links.new(old, paint.inputs[1])
        tree.links.new(paint.outputs[0], bs.inputs['Base Color'])
    # Closing the room gives wood and metal actual reflected wall surfaces.
    wall = bpy.data.materials.get('Scanned painted plaster, 3 metre repeat')
    for name, points in [
        ('Right reflected room wall', [(2.7, -3, 0), (2.7, 1.1, 0), (2.7, 1.1, 2.65), (2.7, -3, 2.65)]),
        ('Front reflected room wall', [(-1.45, -3, 0), (2.7, -3, 0), (2.7, -3, 2.65), (-1.45, -3, 2.65)])]:
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(points, [], [(0, 1, 2, 3)])
        mesh.materials.append(wall)
        layer = mesh.uv_layers.new(name='Metre wall scan')
        for i, p in enumerate(points):
            layer.data[i].uv = ((p[1] if 'Right' in name else p[0]) / 3, p[2] / 3)
        o = bpy.data.objects.new(name, mesh)
        scene.collection.objects.link(o)
    key = bpy.data.objects.get('Daylight through actual left aperture')
    key.data.energy = 205
    key.data.color = (.94, .97, 1)
    sun = bpy.data.objects.get('Soft afternoon sunlight')
    sun.data.energy = .55
    sun.data.angle = .0093
    sun.data.color = (1., .97, .91)
    sun.rotation_euler = Vector((1, .33, -.55)).to_track_quat('-Z', 'Y').to_euler()


def apply(scene, config, record):
    print('APPEARANCE_FINISH_START',flush=True)
    surface_finishes(scene, record)
    print('APPEARANCE_ASSEMBLY_START',flush=True)
    assembly_details(config)
    print('APPEARANCE_ROOM_START',flush=True)
    room_finish(scene)
    print('APPEARANCE_DETAILS_FINISHED',flush=True)
    record['appearance_detail_scope'] = {
        'track': 'Actual milled cross section and circular interlocking sockets; unchanged running beds and gauge',
        'hardware': 'Recessed driver screw heads and bored fixed guide sleeves; static visual assembly',
        'table': 'Original BlenderKit wood and plywood retained; spatially varying satin finish',
        'train': 'Original Sketchfab geometry and paint; 0.1 mm shader edge radius and nonuniform clearcoat',
        'wall': 'Fine scanned plaster under warm white paint, 0.16 normal strength and enclosed reflection geometry',
        'physical_model_or_poses_changed': False,
    }
