"""Render-only restoration of the imported circular brass-and-glass screen.

The downloaded GLB loses metal/transmission parameters. Its glass also overlaps
the front 11 mm of the rods. These changes leave every simulation input alone.
"""

from copy import deepcopy
from math import pi

import bpy
from mathutils import Vector


SCREEN_SETTINGS = {
    'brass_color_linear': [0.63, 0.39, 0.16],
    'brass_roughness': 0.26,
    'brass_roughness_variation': 0.035,
    'brass_anisotropy': 0.30,
    'brass_bump_m': 0.000015,
    'rod_radial_segments': 64,
    'rod_edge_radius_m': 0.0006,
    'frame_edge_radius_m': 0.0006,
    'glass_thickness_m': 0.006,
    'glass_front_x_m': 0.550,
    'glass_color_linear': [0.97, 0.985, 0.98],
    'glass_ior': 1.46,
    'glass_roughness': 0.045,
    'glass_edge_radius_m': 0.00025,
    'glass_shadow_mode': 'transparent shadow rays for a thin flat pane',
    'backing_color_linear': [0.40, 0.36, 0.29],
    'backing_roughness': 0.64,
    'backing_front_x_m': 0.612,
    'backing_thickness_m': 0.008,
    'chrome_color_linear': [0.62, 0.65, 0.68],
    'chrome_roughness': 0.16,
}


def bounds(obj):
    points = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
    return (Vector(tuple(min(p[i] for p in points) for i in range(3))),
            Vector(tuple(max(p[i] for p in points) for i in range(3))))


def summarize_material(mat):
    if mat is None or not mat.use_nodes:
        return {'name': mat.name if mat else None}
    bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        return {'name': mat.name}
    return {'name': mat.name,
            **{k: bsdf.inputs[k].default_value for k in
               ('Metallic', 'Roughness', 'Alpha', 'Transmission Weight')}}


def principled(name, color, metallic, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Alpha'].default_value = 1
    return mat, bsdf


def brass_material(settings):
    mat, bsdf = principled('PCVE_SatinBrass', settings['brass_color_linear'],
                           1.0, settings['brass_roughness'])
    bsdf.inputs['Anisotropic'].default_value = settings['brass_anisotropy']
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    # Position in world metres keeps the grain scale stable across components.
    geom = nodes.new('ShaderNodeNewGeometry')
    mapping = nodes.new('ShaderNodeVectorMath')
    mapping.operation = 'MULTIPLY'
    mapping.inputs[1].default_value = (6500, 6500, 35)
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 1
    noise.inputs['Detail'].default_value = 2
    links.new(geom.outputs['Position'], mapping.inputs[0])
    links.new(mapping.outputs['Vector'], noise.inputs['Vector'])
    rough = nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value = settings['brass_roughness'] - settings['brass_roughness_variation']
    rough.inputs['To Max'].default_value = settings['brass_roughness'] + settings['brass_roughness_variation']
    links.new(noise.outputs['Fac'], rough.inputs['Value'])
    links.new(rough.outputs['Result'], bsdf.inputs['Roughness'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.12
    bump.inputs['Distance'].default_value = settings['brass_bump_m']
    links.new(noise.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    tangent = nodes.new('ShaderNodeCombineXYZ')
    tangent.name = 'Axial brushing direction'
    tangent.inputs['Z'].default_value = 1
    links.new(tangent.outputs['Vector'], bsdf.inputs['Tangent'])
    return mat


def cylinder(name, center, radius, depth, mat, edge, axis='Z', vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                       location=center, rotation=(0, pi/2, 0) if axis == 'X' else (0, 0, 0))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    for face in obj.data.polygons:
        face.use_smooth = len(face.vertices) == 4
    bevel = obj.modifiers.new('Manufactured edge radius', 'BEVEL')
    bevel.width = edge
    bevel.segments = 3
    bevel.affect = 'EDGES'
    normals = obj.modifiers.new('Preserve planar caps', 'WEIGHTED_NORMAL')
    normals.keep_sharp = True
    return obj


def apply_screen_details(scene, settings):
    if settings is None:
        return None
    if scene.objects.get('PCVE_ScreenGlass'):
        raise RuntimeError('Screen details have already been applied')
    source_rods = sorted([o for o in scene.objects if o.type == 'MESH' and
                          o.name.startswith('Line20292527') and
                          2734 <= int(o.name.split('_')[0][-4:]) <= 2752], key=lambda o: o.name)
    if len(source_rods) != 19:
        raise RuntimeError(f'Expected 19 imported screen rods, found {len(source_rods)}')
    source_glass = next(o for o in scene.objects if o.name.startswith('Shape002_'))
    frame = next(o for o in scene.objects if o.name.startswith('Shape001_'))
    inner_frame = next(o for o in scene.objects if o.name.startswith('Shape018_'))
    brass = brass_material(settings)
    ledger = {'settings': deepcopy(settings), 'rods': [], 'frame': [], 'chrome': []}
    for index, source in enumerate(source_rods):
        lo, hi = bounds(source)
        radius = (hi.y - lo.y) / 2
        rod = cylinder(f'PCVE_BrassRod_{index:02d}', (lo+hi)/2, radius, hi.z-lo.z,
                       brass, settings['rod_edge_radius_m'],
                       vertices=settings['rod_radial_segments'])
        source.hide_render = source.hide_viewport = True
        ledger['rods'].append({'source': source.name, 'replacement': rod.name,
                               'before': summarize_material(source.data.materials[0]),
                               'diameter_m': 2*radius, 'bounds_m': [list(lo), list(hi)]})
    for obj in (frame, inner_frame):
        before = [summarize_material(m) for m in obj.data.materials]
        obj.data = obj.data.copy()
        obj.data.materials.clear()
        obj.data.materials.append(brass)
        bevel = obj.modifiers.new('Brass edge highlights', 'BEVEL')
        bevel.width = settings['frame_edge_radius_m']
        bevel.segments = 3
        bevel.angle_limit = 0.6
        ledger['frame'].append({'object': obj.name, 'before': before})
    glass, bsdf = principled('PCVE_ClearScreenGlass', settings['glass_color_linear'],
                             0, settings['glass_roughness'])
    bsdf.inputs['IOR'].default_value = settings['glass_ior']
    bsdf.inputs['Transmission Weight'].default_value = 1
    # Match the existing water renderer's shadow convention. Direct lighting
    # reaches the backing through the thin flat pane without an MNEE solve;
    # camera/glossy rays still use the dielectric, including its Fresnel reflection.
    path = glass.node_tree.nodes.new('ShaderNodeLightPath')
    transparent = glass.node_tree.nodes.new('ShaderNodeBsdfTransparent')
    transparent.inputs['Color'].default_value = (*settings['glass_color_linear'], 1)
    mix = glass.node_tree.nodes.new('ShaderNodeMixShader')
    glass.node_tree.links.new(path.outputs['Is Shadow Ray'], mix.inputs[0])
    glass.node_tree.links.new(bsdf.outputs['BSDF'], mix.inputs[1])
    glass.node_tree.links.new(transparent.outputs['BSDF'], mix.inputs[2])
    glass.node_tree.links.new(mix.outputs['Shader'], glass.node_tree.nodes['Material Output'].inputs['Surface'])
    lo, hi = bounds(source_glass)
    glass_center = (lo+hi)/2
    glass_center.x = settings['glass_front_x_m'] + settings['glass_thickness_m']/2
    pane = cylinder('PCVE_ScreenGlass', glass_center, (hi.y-lo.y)/2,
                    settings['glass_thickness_m'], glass, settings['glass_edge_radius_m'],
                    axis='X', vertices=256)
    source_glass.hide_render = source_glass.hide_viewport = True
    ledger['glass'] = {'source': source_glass.name, 'replacement': pane.name,
                       'before': summarize_material(source_glass.data.materials[0]),
                       'before_bounds_m': [list(lo), list(hi)],
                       'front_x_m': settings['glass_front_x_m'],
                       'back_x_m': settings['glass_front_x_m'] + settings['glass_thickness_m'],
                       'clearance_to_rods_m': min(r['bounds_m'][0][0] for r in ledger['rods']) -
                                              settings['glass_front_x_m'] - settings['glass_thickness_m']}
    # The source wall has a circular opening, with no lit room behind it.
    # Finish that recess so corrected transmission does not reveal a black void.
    backing, backing_bsdf = principled('PCVE_ScreenMineralBacking', settings['backing_color_linear'],
                                       0, settings['backing_roughness'])
    noise = backing.node_tree.nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 160
    bump = backing.node_tree.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.15
    bump.inputs['Distance'].default_value = 0.00008
    backing.node_tree.links.new(noise.outputs['Fac'], bump.inputs['Height'])
    backing.node_tree.links.new(bump.outputs['Normal'], backing_bsdf.inputs['Normal'])
    backing_center = glass_center.copy()
    backing_center.x = settings['backing_front_x_m'] + settings['backing_thickness_m']/2
    back = cylinder('PCVE_ScreenBacking', backing_center, (hi.y-lo.y)/2,
                    settings['backing_thickness_m'], backing, 0.0004, axis='X', vertices=256)
    ledger['backing'] = {'object': back.name, 'front_x_m': settings['backing_front_x_m'],
                         'clearance_to_rods_m': settings['backing_front_x_m'] -
                                                 max(r['bounds_m'][1][0] for r in ledger['rods'])}
    chrome, bsdf = principled('PCVE_BathFittingChrome', settings['chrome_color_linear'],
                              1.0, settings['chrome_roughness'])
    for obj in scene.objects:
        if obj.type == 'MESH' and any(m and m.name == 'Material_2143566106' for m in obj.data.materials):
            before = [summarize_material(m) for m in obj.data.materials]
            obj.data = obj.data.copy()
            obj.data.materials.clear()
            obj.data.materials.append(chrome)
            ledger['chrome'].append({'object': obj.name, 'before': before})
    bpy.context.view_layer.update()
    return ledger
