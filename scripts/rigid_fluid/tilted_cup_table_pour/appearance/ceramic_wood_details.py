"""Centimetre-scale ceramic and solid-timber appearance; frozen colliders stay separate.

All lengths are metres.  The cavity, bottom contact plane and support contact
edge retain the accepted simulation dimensions.  The lip rounds down from the
original top height; it does not intrude into the simulated liquid cavity.
"""
import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


def shader_material(name, color, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    p = mat.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Roughness'].default_value = roughness
    return mat


def ceramic_materials():
    glaze = shader_material('Warm ivory feldspathic glaze', (.72, .695, .645), .20)
    n, l = glaze.node_tree.nodes, glaze.node_tree.links
    p = n.get('Principled BSDF')
    p.inputs['IOR'].default_value = 1.49
    p.inputs['Coat Weight'].default_value = .35
    p.inputs['Coat Roughness'].default_value = .09
    p.inputs['Subsurface Weight'].default_value = .025
    p.inputs['Subsurface Radius'].default_value = (.0006, .0004, .00025)
    co = n.new('ShaderNodeTexCoord')
    grain = n.new('ShaderNodeTexNoise')
    grain.inputs['Scale'].default_value = 1900
    grain.inputs['Detail'].default_value = 2.5
    grain.inputs['Roughness'].default_value = .63
    l.new(co.outputs['Object'], grain.inputs['Vector'])
    rough = n.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value = .105
    rough.inputs['To Max'].default_value = .17
    l.new(grain.outputs['Fac'], rough.inputs['Value'])
    l.new(rough.outputs[0], p.inputs['Roughness'])
    bump = n.new('ShaderNodeBump')
    bump.inputs['Distance'].default_value = .000006
    bump.inputs['Strength'].default_value = .18
    l.new(grain.outputs['Fac'], bump.inputs['Height'])
    l.new(bump.outputs['Normal'], p.inputs['Normal'])
    # Slight pigment variation below the transparent glaze, not an exposed rock texture.
    pigment = n.new('ShaderNodeTexNoise')
    pigment.inputs['Scale'].default_value = 260
    pigment.inputs['Detail'].default_value = 2
    l.new(co.outputs['Object'], pigment.inputs['Vector'])
    ramp = n.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (.708, .686, .635, 1)
    ramp.color_ramp.elements[1].color = (.739, .715, .670, 1)
    l.new(pigment.outputs['Fac'], ramp.inputs[0])
    l.new(ramp.outputs['Color'], p.inputs['Base Color'])
    biscuit = shader_material('Unglazed finely ground porcelain foot', (.55, .49, .39), .69)
    n, l = biscuit.node_tree.nodes, biscuit.node_tree.links
    co = n.new('ShaderNodeTexCoord')
    grain = n.new('ShaderNodeTexNoise')
    grain.inputs['Scale'].default_value = 5600
    grain.inputs['Detail'].default_value = 2
    l.new(co.outputs['Object'], grain.inputs['Vector'])
    bump = n.new('ShaderNodeBump')
    bump.inputs['Distance'].default_value = .000025
    bump.inputs['Strength'].default_value = .27
    l.new(grain.outputs['Fac'], bump.inputs['Height'])
    l.new(bump.outputs['Normal'], n.get('Principled BSDF').inputs['Normal'])
    return glaze, biscuit


def lathed_cup(mug, glaze, biscuit):
    z0, zi, z1 = -.0275, -.0215, .0275
    # The broad, flat ground foot retains the two accepted support tangencies.
    profile = [(0, z0), (.0297, z0), (.0303, z0),
               (.0309, z0), (.0313, z0), (.0316, z0),
               (.037, z0), (.037, z0+.00012), (.03696, z0+.00030),
               (.03682, z0+.00048), (.03655, z0+.00067),
               (.03620, z0+.00085), (.03597, z0+.00115),
               (.03590, z0+.0016), (.03593, z0+.0022),
               (.03602, z0+.0032), (.03619, z0+.0048),
               (.03640, z0+.0070), (.03661, z0+.010),
               (.03679, z0+.014), (.03692, z0+.019),
               (.03699, z0+.026), (.037, z0+.034),
               (.037, z0+.043), (.037, z1-.0011)]
    # A continuous elliptical crown replaces the slab-like flat annulus.
    for i in range(1, 33):
        t = math.pi*i/32
        profile.append((.03425+.00275*math.cos(t), z1-.0011+.0011*math.sin(t)))
    profile.extend([(.0315, z1-.002), (.0315, zi+.003),
                    (.0315, zi+.0005), (.0315, zi), (0, zi)])
    segments = 256
    vertices, rings, faces, sections = [], [], [], []
    for radius, z in profile:
        if radius == 0:
            rings.append([len(vertices)])
            vertices.append((0, 0, z))
        else:
            ring = []
            for j in range(segments):
                angle = math.tau*j/segments
                ring.append(len(vertices))
                vertices.append((radius*math.cos(angle), radius*math.sin(angle), z))
            rings.append(ring)
    for k, (a, b) in enumerate(zip(rings, rings[1:])):
        for j in range(segments):
            if len(a) == 1:
                faces.append((a[0], b[(j+1) % segments], b[j]))
            elif len(b) == 1:
                faces.append((a[j], a[(j+1) % segments], b[0]))
            else:
                faces.append((a[j], a[(j+1) % segments], b[(j+1) % segments], b[j]))
            sections.append(k)
    mesh = bpy.data.meshes.new('Thrown porcelain shell with ground foot and rolled lip')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    old = mug.data
    mug.data = mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)
    mug.modifiers.clear()
    mesh.materials.append(glaze)
    mesh.materials.append(biscuit)
    for face, section in zip(mesh.polygons, sections):
        face.material_index = int(section < 10)
        a, b = profile[section:section+2]
        face.use_smooth = abs(a[1]-b[1]) > 1e-8
    return {'outer_contact_radius_m': .037, 'bottom_plane_local_z_m': z0,
            'inner_radius_m': .0315, 'inner_floor_local_z_m': zi,
            'top_local_z_m': z1, 'lip_rounding_height_m': .0011,
            'foot_recess_m': 0, 'minimum_floor_thickness_m': .006}


def bezier(a, b, c, d, t):
    return (1-t)**3*Vector(a)+3*(1-t)**2*t*Vector(b)+3*(1-t)*t*t*Vector(c)+t**3*Vector(d)


def integrated_handle(mug, glaze):
    for obj in list(bpy.data.objects):
        if obj.name == 'CeramicCupHandle' or obj.name.startswith('Glazed handle attachment'):
            bpy.data.objects.remove(obj, do_unlink=True)
    angle = math.radians(-132)
    radial = Vector((math.cos(angle), math.sin(angle), 0))
    across = Vector((-math.sin(angle), math.cos(angle), 0))
    curves = [((.0345, -.014), (.045, -.020), (.060, -.014), (.0585, 0)),
              ((.0585, 0), (.058, .014), (.047, .0205), (.0345, .0155))]
    path = [bezier(*points, j/64) for k, points in enumerate(curves)
            for j in range(int(k > 0), 65)]
    verts, faces, sides = [], [], 40
    for i, point in enumerate(path):
        tangent = path[min(i+1, len(path)-1)]-path[max(i-1, 0)]
        normal = (radial*(-tangent.y)+Vector((0, 0, tangent.x))).normalized()
        end = math.exp(-(i/9)**2)+math.exp(-((len(path)-1-i)/9)**2)
        in_plane = .00315+.00105*end
        transverse = .00285+.00085*end
        centre = radial*point.x+Vector((0, 0, point.y))
        for j in range(sides):
            t = math.tau*j/sides
            verts.append(tuple(centre+normal*in_plane*math.cos(t)+across*transverse*math.sin(t)))
    for i in range(len(path)-1):
        for j in range(sides):
            faces.append((i*sides+j, i*sides+(j+1) % sides,
                          (i+1)*sides+(j+1) % sides, (i+1)*sides+j))
    faces.extend([tuple(reversed(range(sides))), tuple((len(path)-1)*sides+j for j in range(sides))])
    mesh = bpy.data.meshes.new('Oval-section pulled handle with flared roots')
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    # Ensure a consistently outward closed surface before exact union.
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(mesh)
    bm.free()
    handle = bpy.data.objects.new('Handle union operand', mesh)
    bpy.context.collection.objects.link(handle)
    handle.matrix_world = mug.matrix_world.copy()
    mesh.materials.append(glaze)
    for face in mesh.polygons:
        face.use_smooth = True
    bpy.context.view_layer.objects.active = mug
    union = mug.modifiers.new('Handle fired into cup body', 'BOOLEAN')
    union.operation = 'UNION'
    union.solver = 'EXACT'
    union.object = handle
    bpy.ops.object.modifier_apply(modifier=union.name)
    bpy.data.objects.remove(handle, do_unlink=True)
    # Round only the new attachment intersection, keeping the lip, foot and cavity fixed.
    bm = bmesh.new()
    bm.from_mesh(mug.data)
    bm.edges.ensure_lookup_table()
    weight = bm.edges.layers.float.get('bevel_weight_edge') or bm.edges.layers.float.new('bevel_weight_edge')
    count = 0
    for edge in bm.edges:
        mid = (edge.verts[0].co+edge.verts[1].co)/2
        radius = math.hypot(mid.x, mid.y)
        near_handle = mid.dot(radial) > .0345 and abs(mid.dot(across)) < .005
        root = .008 < abs(mid.z) < .021 and .035 < radius < .0374
        use = near_handle and root and edge.is_manifold and edge.calc_face_angle() > .3
        edge[weight] = float(use)
        count += int(use)
    bm.to_mesh(mug.data)
    bm.free()
    blend = mug.modifiers.new('Soft fired handle junctions 0.65 mm', 'BEVEL')
    blend.limit_method = 'WEIGHT'
    blend.width = .00065
    blend.segments = 4
    bpy.ops.object.modifier_apply(modifier=blend.name)
    return {'angle_degrees': -132, 'oval_section_m': [.0063, .0057],
            'union': 'exact Boolean with flared roots', 'blended_root_edges': count,
            'junction_radius_m': .00065, 'separate_attachment_pads': False}


def solid_timber_material():
    """A single metric 3D growth field supplies both side grain and cut ends.

    The pith is outside this small billet; end grain is arcs, not a target-like
    concentric pattern.  The longitudinal fibre axis is local Y on every face.
    """
    mat = shader_material('Solid oak billet: continuous end grain and longitudinal pores', (.32, .18, .075), .5)
    n, l = mat.node_tree.nodes, mat.node_tree.links
    p = n.get('Principled BSDF')
    p.inputs['Coat Weight'].default_value = .035
    p.inputs['Coat Roughness'].default_value = .4
    co = n.new('ShaderNodeTexCoord')

    def math_node(op, a, b=None):
        node = n.new('ShaderNodeMath')
        node.operation = op
        for i, value in enumerate((a, b)):
            if value is None:
                continue
            if isinstance(value, (float, int)):
                node.inputs[i].default_value = value
            else:
                l.new(value, node.inputs[i])
        return node.outputs[0]

    def vector_scale(vector, scale):
        node = n.new('ShaderNodeVectorMath')
        node.operation = 'MULTIPLY'
        node.inputs[1].default_value = scale
        l.new(vector, node.inputs[0])
        return node.outputs['Vector']

    # A small amount of slow fibre drift prevents machined concentric stripes.
    slow = n.new('ShaderNodeTexNoise')
    slow.inputs['Scale'].default_value = 31
    slow.inputs['Detail'].default_value = 3
    l.new(vector_scale(co.outputs['Object'], (1, .35, 1)), slow.inputs['Vector'])
    split = n.new('ShaderNodeSeparateXYZ')
    l.new(co.outputs['Object'], split.inputs[0])
    x = math_node('ADD', split.outputs['X'], .020)
    z = math_node('ADD', split.outputs['Z'], .040)
    radius = math_node('SQRT', math_node('ADD', math_node('MULTIPLY', x, x), math_node('MULTIPLY', z, z)))
    radius = math_node('ADD', radius, math_node('MULTIPLY', slow.outputs['Fac'], .0016))
    phase = math_node('MULTIPLY', radius, math.tau/.0023)
    irregular = n.new('ShaderNodeTexNoise')
    irregular.inputs['Scale'].default_value = 260
    irregular.inputs['Detail'].default_value = 2
    l.new(vector_scale(co.outputs['Object'], (1, .12, 1)), irregular.inputs['Vector'])
    phase = math_node('ADD', phase, math_node('MULTIPLY', irregular.outputs['Fac'], 2.9))
    rings = math_node('SINE', phase)
    ramp = n.new('ShaderNodeValToRGB')
    ramp.color_ramp.interpolation = 'EASE'
    for element in list(ramp.color_ramp.elements)[2:]:
        ramp.color_ramp.elements.remove(element)
    ramp.color_ramp.elements[0].position = .0
    ramp.color_ramp.elements[0].color = (.305, .203, .116, 1)
    ramp.color_ramp.elements[1].position = 1
    ramp.color_ramp.elements[1].color = (.292, .190, .104, 1)
    ramp.color_ramp.elements.new(.60).color = (.325, .221, .133, 1)
    ramp.color_ramp.elements.new(.87).color = (.315, .210, .121, 1)
    ramp.color_ramp.elements.new(.98).color = (.286, .185, .100, 1)
    l.new(math_node('MULTIPLY_ADD', rings, .5), ramp.inputs[0])
    # MULTIPLY_ADD above has an explicit offset so the sine covers 0..1.
    ramp.inputs[0].links[0].from_node.inputs[2].default_value = .5

    pores = n.new('ShaderNodeTexVoronoi')
    pores.inputs['Scale'].default_value = 1
    pores.inputs['Randomness'].default_value = .92
    l.new(vector_scale(co.outputs['Object'], (1800, 18, 1800)), pores.inputs['Vector'])
    pore_mask = math_node('LESS_THAN', pores.outputs['Distance'], .21)
    fibres = n.new('ShaderNodeTexNoise')
    fibres.inputs['Scale'].default_value = 1
    fibres.inputs['Detail'].default_value = 3
    fibres.inputs['Roughness'].default_value = .7
    l.new(vector_scale(co.outputs['Object'], (5000, 32, 5000)), fibres.inputs['Vector'])
    long_grain = n.new('ShaderNodeTexNoise')
    long_grain.inputs['Scale'].default_value = 1
    long_grain.inputs['Detail'].default_value = 3
    l.new(vector_scale(co.outputs['Object'], (650, 12, 650)), long_grain.inputs['Vector'])
    shade = math_node('SUBTRACT', math_node('ADD', .72, math_node('MULTIPLY', long_grain.outputs['Fac'], .50)), math_node('MULTIPLY', pore_mask, .44))
    geometry = n.new('ShaderNodeNewGeometry')
    normal = n.new('ShaderNodeSeparateXYZ')
    l.new(geometry.outputs['True Normal'], normal.inputs[0])
    end = math_node('ABSOLUTE', normal.outputs['Y'])
    # Photographic fibre detail on the long faces only.  U follows growth depth;
    # V follows the timber axis.  The cut ends keep the volumetric pore field.
    scan_co = n.new('ShaderNodeCombineXYZ')
    l.new(math_node('ADD', math_node('MULTIPLY', radius, 2.), .183), scan_co.inputs['X'])
    l.new(math_node('ADD', math_node('MULTIPLY', split.outputs['Y'], 2.), .271), scan_co.inputs['Y'])
    scan = n.new('ShaderNodeTexImage')
    scan.image = bpy.data.images['white_oak_veneer_diff_4k.jpg']
    l.new(scan_co.outputs[0], scan.inputs['Vector'])
    blend = n.new('ShaderNodeMixRGB')
    l.new(math_node('MULTIPLY', math_node('SUBTRACT', 1., end), .65), blend.inputs[0])
    l.new(ramp.outputs['Color'], blend.inputs[1])
    l.new(scan.outputs['Color'], blend.inputs[2])
    shade = math_node('MULTIPLY', shade, math_node('SUBTRACT', 1., math_node('MULTIPLY', end, .14)))
    multiply = n.new('ShaderNodeMixRGB')
    multiply.blend_type = 'MULTIPLY'
    multiply.inputs[0].default_value = 1
    l.new(blend.outputs[0], multiply.inputs[1])
    l.new(shade, multiply.inputs[2])
    l.new(multiply.outputs[0], p.inputs['Base Color'])
    rough = math_node('ADD', .43, math_node('ADD', math_node('MULTIPLY', end, .13), math_node('MULTIPLY', fibres.outputs['Fac'], .08)))
    l.new(rough, p.inputs['Roughness'])
    bump = n.new('ShaderNodeBump')
    bump.inputs['Distance'].default_value = .000055
    bump.inputs['Strength'].default_value = .4
    height = math_node('SUBTRACT', fibres.outputs['Fac'], math_node('MULTIPLY', pore_mask, .55))
    l.new(height, bump.inputs['Height'])
    l.new(bump.outputs['Normal'], p.inputs['Normal'])
    return mat


def apply(mug, support):
    glaze, biscuit = ceramic_materials()
    cup = lathed_cup(mug, glaze, biscuit)
    handle = integrated_handle(mug, glaze)
    support.data.materials.clear()
    support.data.materials.append(solid_timber_material())
    for modifier in support.modifiers:
        if modifier.type == 'BEVEL':
            # Tiny broken arrises suit a 35 mm block; keep its loaded edge sharp.
            modifier.width = .00055
            modifier.segments = 4
    return {'ceramic': cup, 'handle': handle,
            'wood': {'type': 'procedural solid oak', 'grain_axis': 'local Y',
                     'growth_ring_spacing_m': .0023, 'pore_pitch_m': 1/1800,
                     'edge_radius_m': .00055, 'end_grain_continues_into_side_grain': True,
                     'side_fibre_detail': 'White Oak Veneer photo scan, 0.5 m metric width, 65% blend on long faces',
                     'loaded_contact_edge_bevel_weight': 0},
            'simulation_cache_modified': False, 'colliders_modified': False}
