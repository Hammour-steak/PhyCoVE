"""Render-only surface finishing for the existing bathtub bathroom."""
from copy import deepcopy

import bmesh
import bpy
import hashlib
import numpy as np
from math import pi
from mathutils import Vector
from mathutils.bvhtree import BVHTree


CERAMIC_SETTINGS = {
    'base_color_linear': [0.78, 0.79, 0.80],
    'roughness': 0.13,
    'coat_weight': 0.24,
    'coat_roughness': 0.065,
}
FINISH_SETTINGS = {
    'tub_geometry': 'continuous shell fitted to the source radial sections',
    'tub_radial_segments': 384,
    'tub_contour_smoothing_iterations': 2,
    'tub_subdivision_levels': 1,
    'tub_rim_height_m': 0.600,
    'tub_floor_height_m': 0.1125,
    'drain_opening_radius_m': 0.052,
    'wall_roughness_range': [0.38, 0.49],
    'stone_roughness_range': [0.30, 0.43],
    'wood_roughness_range': [0.32, 0.46],
    'wall_bump_distance_m': 0.00008,
    'stone_bump_distance_m': 0.00004,
    'wood_bump_distance_m': 0.00006,
    'shelf_edge_radius_m': 0.0015,
    'brass_frame_edge_radius_m': 0.0006,
    'wood_saturation': 0.82,
    'wood_value': 0.94,
}


def smooth_tub(scene, settings):
    """Fit a closed visual shell, with a continuous rounded rim and real drain."""
    source = next(o for o in scene.objects if o.type == 'MESH' and
                  o.name.startswith('Duravit_Starck_free standing'))
    if scene.objects.get('PCVE_BathtubShell'):
        raise RuntimeError('Bathtub finishing has already been applied')
    points = np.asarray([tuple(source.matrix_world @ v.co) for v in source.data.vertices])
    tree = BVHTree.FromPolygons([Vector(p) for p in points],
                                [list(f.vertices) for f in source.data.polygons])
    count = settings['tub_radial_segments']
    theta = np.arange(count)*2*pi/count
    directions = np.column_stack((np.cos(theta), np.sin(theta)))
    cx, cy = 0.0132777, 0.0108457
    lo, hi = points.min(axis=0), points.max(axis=0)
    sampling = []

    def contour(z, outside=False):
        center = Vector((cx, cy, z))
        radii = []
        for d in directions:
            direction = Vector((float(d[0]), float(d[1]), 0))
            origin = center+direction*2 if outside else center
            ray = -direction if outside else direction
            hit, normal, index, distance = tree.ray_cast(origin, ray)
            radii.append((hit-center).dot(direction) if hit is not None else np.nan)
        raw = np.asarray(radii)
        valid = np.isfinite(raw)
        if valid.sum()<count*.9:
            raise RuntimeError(f'Incomplete bathtub section at {z}: {valid.sum()}/{count}')
        filled = np.interp(theta, theta[valid], raw[valid], period=2*pi)
        result = filled.copy()
        for unused in range(settings['tub_contour_smoothing_iterations']):
            result = (np.roll(result, -2)+4*np.roll(result, -1)+6*result+
                      4*np.roll(result, 1)+np.roll(result, 2))/16
        sampling.append({'z_m': z, 'outside': outside, 'missing_rays': int((~valid).sum()),
                         'smoothing_max_radial_delta_m': float(np.max(np.abs(result-filled)))})
        return result

    inner_heights = [.12, .14, .16, .20, .26, .30, .32, .38, .42, .46, .50, .54, .56]
    outer_heights = [.02, .08, .14, .20, .30, .42, .50, .54, .56]
    inner = {z: contour(z) for z in inner_heights}
    outer = {z: contour(z, True) for z in outer_heights}

    def extrapolated(z):
        return inner[.50]+(z-.50)*(inner[.50]-inner[.30])/.20

    # Axial dimensions come from the original asset; the low side-rim notches
    # are replaced with a continuous lip at its original maximum height.
    desired_x = (hi[0]-lo[0])/2
    desired_y = (hi[1]-lo[1])/2
    base = outer[.56]
    sx, sy = desired_x/base[0], desired_y/base[count//4]
    outer_top = base*(sx*directions[:,0]**2+sy*directions[:,1]**2)
    inner_top = extrapolated(.585)
    floor = settings['tub_floor_height_m']
    drain = np.full(count, settings['drain_opening_radius_m'])
    # Closely spaced support loops keep the pop-up drain flange seated after
    # subdivision instead of rolling the floor down into a wide dark socket.
    rings = [(drain, floor-.0015), (drain, floor-.0002),
             (drain+.0008, floor)]
    for fraction, z in [(.25, floor+.0003), (.55, floor+.001), (.80, floor+.002),
                         (.94, .12), (.99, .135)]:
        rings.append((inner[.12]*fraction, z))
    for z in inner_heights:
        if z>=.16:
            rings.append((inner[z], z))
    rings.extend([(extrapolated(.58), .58), (inner_top, .590)])
    top = settings['tub_rim_height_m']
    for mix, z in [(.07, top-.003), (.22, top-.0006), (.40, top),
                   (.63, top), (.84, top-.0006), (.96, top-.003), (1, top-.008)]:
        rings.append((inner_top*(1-mix)+outer_top*mix, z))
    rings.append((outer_top, .580))
    for z in reversed(outer_heights):
        rings.append((outer[z], z))
    rings.append((outer[.02]*.993, .006))
    for fraction in (.85, .55, .20):
        rings.append((outer[.02]*fraction, .006))
    rings.append((drain, .006))
    vertices = []
    for radius, z in rings:
        vertices.extend([(cx+float(r*d[0]), cy+float(r*d[1]), z)
                         for r, d in zip(radius, directions)])
    faces = []
    for i in range(len(rings)):
        next_ring = (i+1)%len(rings)
        for j in range(count):
            k = (j+1)%count
            faces.append((i*count+j, i*count+k, next_ring*count+k, next_ring*count+j))
    mesh = bpy.data.meshes.new('PCVE_FittedBathtubShell')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    if bm.calc_volume(signed=True)<0:
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
    nonmanifold = sum(not e.is_manifold for e in bm.edges)
    bm.to_mesh(mesh)
    bm.free()
    for mat in source.data.materials:
        mesh.materials.append(mat)
    for face in mesh.polygons:
        face.use_smooth = True
    obj = bpy.data.objects.new('PCVE_BathtubShell', mesh)
    scene.collection.objects.link(obj)
    subdivision = obj.modifiers.new('Continuous ceramic curvature', 'SUBSURF')
    subdivision.subdivision_type = 'CATMULL_CLARK'
    subdivision.levels = subdivision.render_levels = settings['tub_subdivision_levels']
    source.hide_render = source.hide_viewport = True
    return {'source_object': source.name, 'replacement_object': obj.name,
            'source_world_vertices_sha256': hashlib.sha256(points.astype(np.float32).tobytes()).hexdigest(),
            'source_bounds_m': [lo.tolist(), hi.tolist()],
            'vertices': len(vertices), 'faces': len(faces), 'nonmanifold_edges': nonmanifold,
            'radial_segments': count, 'profile_rings': len(rings),
            'section_sampling': sampling,
            'waterline_fit_max_radial_delta_m': next(r['smoothing_max_radial_delta_m'] for r in sampling if r['z_m']==.42 and not r['outside']),
            'rim_height_m': top, 'drain_opening_radius_m': settings['drain_opening_radius_m'],
            'render_subdivision_levels': settings['tub_subdivision_levels'],
            'collision_geometry_changed': False}


def surface_material(original, kind, settings):
    mat = original.copy()
    mat.name = {'wall': 'PCVE_HonedLimestone', 'stone': 'PCVE_SatinDarkStone',
                'wood': 'PCVE_SealedOak'}[kind]
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    before = {k: bsdf.inputs[k].default_value for k in
              ('Roughness', 'Coat Weight', 'Coat Roughness')}
    geom = nodes.new('ShaderNodeNewGeometry')
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 750 if kind != 'wood' else 1
    noise.inputs['Detail'].default_value = 2
    if kind == 'wood':
        grain = nodes.new('ShaderNodeVectorMath')
        grain.operation = 'MULTIPLY'
        grain.inputs[1].default_value = (18, 1800, 1800)
        links.new(geom.outputs['Position'], grain.inputs[0])
        links.new(grain.outputs['Vector'], noise.inputs['Vector'])
    else:
        links.new(geom.outputs['Position'], noise.inputs['Vector'])
    rough = nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value, rough.inputs['To Max'].default_value = settings[f'{kind}_roughness_range']
    links.new(noise.outputs['Fac'], rough.inputs['Value'])
    links.new(rough.outputs['Result'], bsdf.inputs['Roughness'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.12
    bump.inputs['Distance'].default_value = settings[f'{kind}_bump_distance_m']
    links.new(noise.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    bsdf.inputs['Coat Weight'].default_value = {'wall': 0.03, 'stone': 0.12, 'wood': 0.10}[kind]
    bsdf.inputs['Coat Roughness'].default_value = 0.22
    if kind == 'wood' and bsdf.inputs['Base Color'].links:
        old = bsdf.inputs['Base Color'].links[0].from_socket
        hue = nodes.new('ShaderNodeHueSaturation')
        hue.inputs['Saturation'].default_value = settings['wood_saturation']
        hue.inputs['Value'].default_value = settings['wood_value']
        links.new(old, hue.inputs['Color'])
        links.new(hue.outputs['Color'], bsdf.inputs['Base Color'])
    return mat, before


def apply_material_finish(scene, settings):
    mapping = {'12_-_Default': 'wall', '10_-_Default_0': 'stone', '07_-_Default': 'wood'}
    replacements = {}
    ledger = []
    for obj in list(scene.objects):
        if obj.type != 'MESH' or obj.hide_render:
            continue
        for slot in obj.material_slots:
            original = slot.material
            if original is None or original.name not in mapping:
                continue
            if original.name not in replacements:
                kind = mapping[original.name]
                mat, before = surface_material(original, kind, settings)
                replacements[original.name] = mat
                ledger.append({'source_material': original.name, 'material': mat.name,
                               'kind': kind, 'before': before,
                               'after_roughness_range': settings[f'{kind}_roughness_range'], 'objects': []})
            slot.material = replacements[original.name]
            next(r for r in ledger if r['source_material'] == original.name)['objects'].append(obj.name)
    edge_objects = []
    for obj in scene.objects:
        if obj.type == 'MESH' and obj.name.startswith(('Rectangle1111125391_', 'Rectangle1111125392_',
                                                       'Rectangle1111125394_', 'Rectangle1111125395_')):
            mod = obj.modifiers.new('Finished shelf edge', 'BEVEL')
            # Blender bevel widths are in object-local units; these imports
            # carry their real-world scaling in parent transforms.
            scale = max(abs(v) for v in obj.matrix_world.to_scale())
            mod.width = settings['shelf_edge_radius_m']/scale
            mod.segments = 3
            mod.harden_normals = True
            normal = obj.modifiers.new('Planar stone faces', 'WEIGHTED_NORMAL')
            normal.keep_sharp = True
            edge_objects.append(obj.name)
    brass_edges = []
    for obj in scene.objects:
        mod = obj.modifiers.get('Brass edge highlights')
        if mod is not None:
            scale = max(abs(v) for v in obj.matrix_world.to_scale())
            before_radius = mod.width*scale
            mod.width = settings['brass_frame_edge_radius_m']/scale
            brass_edges.append({'object': obj.name, 'before_edge_radius_m': before_radius,
                                'after_edge_radius_m': settings['brass_frame_edge_radius_m']})
    return {'materials': ledger, 'shelf_edge_objects': edge_objects,
            'brass_frame_edge_corrections': brass_edges}


def apply_bathroom_finish(scene, settings):
    if settings is None:
        return None
    ledger = {'settings': deepcopy(settings)}
    ledger['tub_geometry'] = smooth_tub(scene, settings)
    ledger.update(apply_material_finish(scene, settings))
    bpy.context.view_layer.update()
    return ledger
