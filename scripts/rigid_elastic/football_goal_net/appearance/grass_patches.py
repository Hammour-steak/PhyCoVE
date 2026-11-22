"""Remote-only static turf tiles. The animated native tuft carriers are untouched.

This is one common visual baseline for source and all five independent edits.
It does not implement or alter a physical edit, simulation, material or camera.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


COLLECTION = 'static grass patches | eight native baked mesh tiles'
MARKER = 'static_grass_patch_field'
RECIPE = {
    'seed': 2026110308,
    'patch_variants': 8,
    'tile_size_m': .5,
    'tufts_per_tile': 2500,
    'tufts_per_m2': 10000,
    'field_bounds_xy_m': [-43., 43., -115.5, 10.5],
    'excluded_dynamic_bounds_xy_m': [-1., 2., -16., 9.],
    'quarter_turn_choices': [0, 1, 2, 3],
    'prototype_leaf_height_m': [.020, .026],
    'prototype_geometry': 'actual original24 GN CollectionInfo children after frozen look, surfaces and turf',
    'root_distribution': '50x50 stratified uniform; edge roots fit their complete native tuft inside tile; no blade clipping',
    'root_z_m': .0001,
    'static_compression_multiplier': 1.,
    'all_six_cases_same_seed_and_layout': True,
}
RECIPE_SHA256 = hashlib.sha256(json.dumps(RECIPE, sort_keys=True).encode()).hexdigest()


def _remote_only():
    """No host requirement; any Blender 4.3 host renders this scene."""


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def layout_arrays():
    """No case id, cache, animation, ball location or camera enters this layout."""
    import numpy as np
    x0, x1, y0, y1 = RECIPE['field_bounds_xy_m']
    a, b, c, d = RECIPE['excluded_dynamic_bounds_xy_m']
    tile = RECIPE['tile_size_m']
    nx, ny = round((x1-x0)/tile), round((y1-y0)/tile)
    x, y = np.meshgrid(x0+(np.arange(nx)+.5)*tile, y0+(np.arange(ny)+.5)*tile, indexing='ij')
    in_corridor = (x >= a) & (x < b) & (y >= c) & (y < d)
    points = np.column_stack((x[~in_corridor], y[~in_corridor], np.zeros(int((~in_corridor).sum())))).astype(np.float32)
    rng = np.random.default_rng(RECIPE['seed'])
    variants = rng.integers(0, RECIPE['patch_variants'], len(points), dtype=np.int32)
    quarters = rng.integers(0, 4, len(points), dtype=np.int32)
    rotation = np.zeros((len(points), 3), np.float32)
    rotation[:, 2] = quarters*(math.pi/2)
    # Every full tile is outside the closed dynamic rectangle. The native
    # baked geometry is wholly inside its tile, including the complete leaves.
    half = tile/2
    overlaps = (points[:, 0]+half > a) & (points[:, 0]-half < b) & (points[:, 1]+half > c) & (points[:, 1]-half < d)
    if overlaps.any() or len(points) != 43044 or int(in_corridor.sum()) != 300:
        raise RuntimeError('Shared field tiling/exclusion mismatch')
    return {'position': points, 'patch_variant': variants, 'patch_rotation': rotation}, {
        'grid_tiles_before_exclusion': nx*ny, 'excluded_tiles': int(in_corridor.sum()),
        'static_tiles': len(points), 'static_area_m2': len(points)*tile*tile,
        'excluded_dynamic_area_m2': float((b-a)*(d-c)),
        'static_tufts_virtual': len(points)*RECIPE['tufts_per_tile'],
        'variant_tile_counts': np.bincount(variants, minlength=8).tolist(),
        'quarter_turn_tile_counts': np.bincount(quarters, minlength=4).tolist(),
        'full_tile_geometry_excludes_dynamic_rectangle': True,
        'arrays_sha256': {k: hashlib.sha256(v.tobytes()).hexdigest() for k, v in {'position': points, 'patch_variant': variants, 'patch_rotation': rotation}.items()},
    }


def _dynamic_state(bpy):
    import numpy as np
    a, b, c, d = RECIPE['excluded_dynamic_bounds_xy_m']
    result = []
    for obj in bpy.context.scene.objects:
        if obj.get('static_unaffected_turf'):
            raise RuntimeError('Remove only static_unaffected_turf objects before adding background patches')
        if obj.type != 'MESH' or obj.hide_render or not obj.data.attributes.get('tuft_variant'):
            continue
        points = np.empty((len(obj.data.vertices), 3), np.float32)
        obj.data.vertices.foreach_get('co', points.ravel())
        if len(points) and not ((points[:, 0] >= a-1e-6) & (points[:, 0] <= b+1e-6) & (points[:, 1] >= c-1e-6) & (points[:, 1] <= d+1e-6)).all():
            raise RuntimeError('Native dynamic tuft roots must be restricted to shared corridor before patch integration: '+obj.name)
        attrs = {}
        for name, field, count, dtype in [('tuft_rotation', 'vector', 3, np.float32), ('tuft_scale', 'vector', 3, np.float32), ('tuft_variant', 'value', 1, np.int32)]:
            value = np.empty((len(points), count), dtype)
            obj.data.attributes[name].data.foreach_get(field, value.ravel())
            attrs[name] = hashlib.sha256(value.tobytes()).hexdigest()
        result.append({'object': obj.name, 'mesh_pointer': obj.data.as_pointer(), 'roots': len(points),
                       'positions_sha256': hashlib.sha256(points.tobytes()).hexdigest(), 'attributes_sha256': attrs,
                       'matrix': [list(row) for row in obj.matrix_world],
                       'node_group_pointers': [m.node_group.as_pointer() for m in obj.modifiers if m.type == 'NODES' and m.node_group]})
    return result


def apply(bpy, asset_dir):
    """Call after grass_binding and removal of marked static root objects.

    asset_dir: the registered assets/scenes/football_goal_net/grass_patches folder.
    This adds one point carrier and a GN group, with8 shared realized tile
    meshes in an unlinked CollectionInfo collection. No RealizeInstances is
    present in the field group. No existing object/datablock is modified.
    """
    _remote_only()
    asset_dir = Path(asset_dir).resolve(strict=True)
    manifest = json.loads((asset_dir/'asset_manifest.json').read_text())
    asset = asset_dir/'static_grass_patches.blend'
    if manifest['recipe_sha256'] != RECIPE_SHA256 or sha(asset) != manifest['asset_sha256']:
        raise RuntimeError('Frozen patch recipe/asset checksum differs')
    if any(o.get(MARKER) for o in bpy.data.objects) or bpy.data.collections.get(COLLECTION):
        raise RuntimeError('Static grass patch field must be applied exactly once')
    before = _dynamic_state(bpy)
    with bpy.data.libraries.load(str(asset), link=False) as (available, wanted):
        if COLLECTION not in available.collections:
            raise RuntimeError('Actual patch collection absent from frozen asset')
        wanted.collections = [COLLECTION]
    collection = wanted.collections[0]
    if collection is None or len(collection.objects) != 8 or collection.children:
        raise RuntimeError('Expected exactly8 actual baked tile meshes')
    source_objects = list(collection.objects)
    if [o.name for o in source_objects] != manifest['prototype_object_order']:
        raise RuntimeError('Patch collection indexing differs from frozen asset')
    for obj in source_objects:
        if obj.type != 'MESH' or obj.modifiers or obj.animation_data or len(obj.data.vertices) < 100000:
            raise RuntimeError('Expected static, already realized native blade geometry')
        if obj.data.attributes.get('leaf_pigment') is None:
            raise RuntimeError('Native leaf pigment missing')
    arrays, layout = layout_arrays()
    mesh = bpy.data.meshes.new('shared background patch tile origins')
    mesh.vertices.add(len(arrays['position']))
    mesh.vertices.foreach_set('co', arrays['position'].ravel())
    for name, kind, field in [('patch_variant', 'INT', 'value'), ('patch_rotation', 'FLOAT_VECTOR', 'vector')]:
        mesh.attributes.new(name=name, type=kind, domain='POINT').data.foreach_set(field, arrays[name].ravel())
    mesh.update()
    obj = bpy.data.objects.new('static background |43,044 shared native mesh grass tiles', mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj[MARKER] = True
    obj['pcve_role'] = 'common_visual_only_static_grass_outside_physical_contact_corridor'
    obj['recipe_sha256'] = RECIPE_SHA256
    obj['asset_sha256'] = manifest['asset_sha256']
    group = bpy.data.node_groups.new('static field |native baked mesh tile instances only', 'GeometryNodeTree')
    group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    nodes, links = group.nodes, group.links
    inp = nodes.new('NodeGroupInput')
    out = nodes.new('NodeGroupOutput')
    info = nodes.new('GeometryNodeCollectionInfo')
    info.inputs['Collection'].default_value = collection
    info.inputs['Separate Children'].default_value = True
    info.inputs['Reset Children'].default_value = True
    instance = nodes.new('GeometryNodeInstanceOnPoints')
    instance.inputs['Pick Instance'].default_value = True
    index = nodes.new('GeometryNodeInputNamedAttribute'); index.data_type = 'INT'; index.inputs['Name'].default_value = 'patch_variant'
    rotate = nodes.new('GeometryNodeInputNamedAttribute'); rotate.data_type = 'FLOAT_VECTOR'; rotate.inputs['Name'].default_value = 'patch_rotation'
    links.new(inp.outputs['Geometry'], instance.inputs['Points'])
    links.new(info.outputs['Instances'], instance.inputs['Instance'])
    links.new(index.outputs['Attribute'], instance.inputs['Instance Index'])
    links.new(rotate.outputs['Attribute'], instance.inputs['Rotation'])
    links.new(instance.outputs['Instances'], out.inputs['Geometry'])
    obj.modifiers.new('Fixed shared tile layout, no animated object dependencies', 'NODES').node_group = group
    after = _dynamic_state(bpy)
    if before != after:
        raise RuntimeError('Patch integration changed native animated grass roots/attributes/transform/GN')
    return {'recipe': RECIPE, 'recipe_sha256': RECIPE_SHA256, 'asset_sha256': manifest['asset_sha256'],
            'asset_path': str(asset), 'field_object': obj.name, 'collection': collection.name,
            'layout': layout, 'dynamic_carriers_unchanged': before,
            'no_field_RealizeInstances': True, 'no_animated_object_dependency': True,
            'physical_edit_or_initial_transform_change': False, 'performance_improvement_measured': False}
