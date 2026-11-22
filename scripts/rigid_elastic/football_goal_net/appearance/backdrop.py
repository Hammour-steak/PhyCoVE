"""Preserve the photographic stadium backdrop, and show the existing physical barriers.

Render binding only. The triangle coordinates come from the SHA-frozen
collision world; they are shared by all six cases and are never moved.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np

WORLD_SHA = '99033d1f877fd9148edcb9d82816526a63171ca2c9b39cd80236def112b6aa12'
OWNERS = ('Material2.026', 'Material2.133', 'Material2.136', 'Material3.034')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def apply(bpy, scene, eye, inputs):
    """inputs: {'world': collision world npz, 'hdri': goal-free stadium panorama} (registered assets)."""
    path = Path(__file__).with_name('stadium_backdrop.py')
    spec = importlib.util.spec_from_file_location('preserved_stadium_backdrop', path)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    result = original.apply(bpy, scene, eye, inputs)
    world_path = Path(inputs['world'])
    assert sha(world_path) == WORLD_SHA
    with np.load(world_path, allow_pickle=False) as z:
        triangles = z['triangles'].copy()
        indices = z['owner_indices'].copy()
        names = json.loads(str(z['owner_labels_json'].item()))
    bindings = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for name in OWNERS:
        owner_id = names.index(name)
        tris = triangles[indices == owner_id]
        assert len(tris)
        source = bpy.data.objects[name]
        assert source.hide_render  # These were hidden by the photographic backdrop.
        evaluated = source.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        co = np.array([v.co[:] for v in mesh.vertices], dtype=np.float64)
        matrix = np.array(source.matrix_world, dtype=np.float64)
        co = co @ matrix[:3, :3].T + matrix[:3, 3]
        candidates = np.array([t.vertices[:] for t in mesh.loop_triangles], dtype=np.int32)
        original_tris = co[candidates]
        centres = original_tris.mean(axis=1)
        materials = [slot.material for slot in source.material_slots]
        assert materials and all(materials)
        material_indices = [int(t.material_index) for t in mesh.loop_triangles]
        assigned = []
        errors = []
        for triangle in tris:
            distances = np.linalg.norm(centres - triangle.mean(axis=0), axis=1)
            best = int(np.argmin(distances))
            # The collision export may triangulate a quad with a different diagonal.
            # Its render surface is still EXACTLY the exported physical triangle.
            assigned.append(material_indices[best])
            errors.append(float(distances[best]))
        evaluated.to_mesh_clear()
        visible = bpy.data.meshes.new('frozen physical surface | ' + name)
        visible.from_pydata(tris.reshape(-1, 3).tolist(), [],
                           [(3*i, 3*i+1, 3*i+2) for i in range(len(tris))])
        visible.update()
        for material in materials:
            visible.materials.append(material)
        for polygon, material_index in zip(visible.polygons, assigned):
            polygon.material_index = material_index
        obj = bpy.data.objects.new(visible.name, visible)
        scene.collection.objects.link(obj)
        obj['pcve_role'] = 'render_binding_of_existing_frozen_world_collider'
        obj['physical_owner'] = name
        obj['world_sha256'] = WORLD_SHA
        actual = np.array([v.co[:] for v in visible.vertices]).reshape(-1, 3, 3)
        error = float(np.max(np.abs(actual - tris)))
        assert error < 4e-6
        bindings.append({'owner': name, 'object': obj.name, 'triangles': len(tris),
                         'bounds_min_m': tris.min(axis=(0, 1)).tolist(),
                         'bounds_max_m': tris.max(axis=(0, 1)).tolist(),
                         'maximum_render_float_error_m': error,
                         'nearest_material_centroid_max_error_m': max(errors),
                         'materials': [m.name for m in materials],
                         'matrix_is_identity': bool(np.array_equal(np.array(obj.matrix_world), np.eye(4))),
                         'visible': not obj.hide_render})
    result.update(existing_collision_world_sha256=WORLD_SHA,
                  existing_collision_surfaces_restored=bindings,
                  common_to_source_and_all_five_edits=True,
                  physical_parameters_or_initial_actor_transforms_changed=False,
                  original_backdrop_preserved=True)
    return result
