"""Common grass-only geometry; bpy executes inside Blender (appearance/render.py).

CPU-safe array functions are tested without Blender. Runtime follows the real
carrier GN CollectionInfo pointer, never a guessed/truncated collection name.
No material/lighting/camera/physical actor/collider changes. All new grass uses
the unchanged original InstanceOnPoints + one-way solved-ball compression GN.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np


RECIPE = {
    "seed": 2026102804,
    "foreground_gaussians": [
        {"count": 600000, "center_xy_m": [.8, -16.5], "sigma_xy_m": [2.3, 4.]},
        {"count": 350000, "center_xy_m": [1.6, -22.], "sigma_xy_m": [1.3, 2.6]},
    ],
    "maximum_new_roots": 1000000, "root_z_m": .0001,
    "prototype_leaf_height_m": [.020, .026], "prototype_maximum_width_m": [.0011, .0020],
    "pointed_leaf_probability": .35, "clipped_tip_width_factor": [.28, .48],
    "pointed_tip_width_factor": [.06, .15], "transverse_fold_m": [.00009, .00020],
    "longitudinal_twist_rad": [-.36, .36], "source_point_attributes_and_positions_change": False,
    "mowing_band_m": 5.5, "coupled_grass_simulation": False,
    "new_instances_realized": False, "material_canopy_camera_lighting_changes": False,
}
RECIPE_SHA256 = hashlib.sha256(json.dumps(RECIPE, sort_keys=True).encode()).hexdigest()


def record(values):
    a = np.ascontiguousarray(values)
    return {"shape": list(a.shape), "dtype": a.dtype.str, "sha256": hashlib.sha256(a.tobytes()).hexdigest()}


def foreground_arrays():
    """A fixed shared recipe; no case name, animation or camera in the seed."""
    rng = np.random.default_rng(RECIPE["seed"])
    positions, source_counts = [], []
    for spec in RECIPE["foreground_gaussians"]:
        xy = rng.normal(spec["center_xy_m"], spec["sigma_xy_m"], (spec["count"], 2))
        keep = (np.abs(xy[:, 0]) < 42.5) & (xy[:, 1] > -105.) & (xy[:, 1] < 8.)
        points = np.column_stack((xy[keep], np.full(int(keep.sum()), RECIPE["root_z_m"])))
        positions.append(points)
        source_counts.append({**spec, "actual_kept_roots": len(points)})
    points = np.concatenate(positions).astype(np.float32)
    if len(points) > RECIPE["maximum_new_roots"]:
        raise RuntimeError("Bounded common foreground-root limit exceeded")
    x, y = points[:, 0].astype(float), points[:, 1].astype(float)
    azimuth = rng.uniform(-math.pi, math.pi, len(points))
    tilt = np.where(np.floor(-y/5.5).astype(np.int64) % 2 == 0, 1., -1.) * rng.uniform(.12, .32, len(points))
    rotation = np.column_stack((tilt*np.cos(azimuth), -tilt*np.sin(azimuth), azimuth))
    # Match the existing common deterministic small visual-angle variation,
    # without touching any original point attribute or existing animation.
    phase = x*73.913+y*47.271
    rotation[:, 0] += .025*np.sin(phase)
    rotation[:, 1] += .025*np.sin(phase*1.371+1.3)
    rotation[:, 2] += .12*np.sin(phase*.731)
    scale = rng.uniform(.94, 1.06, (len(points), 3))
    scale[:, 2] *= np.clip(1+.025*np.sin(x*.81+np.sin(y*.57))+.015*np.sin(x*3.1-y*2.4), .96, 1.04)
    variant = rng.integers(0, 24, len(points), dtype=np.int32)
    return {"position": points, "tuft_rotation": rotation.astype(np.float32),
            "tuft_scale": scale.astype(np.float32), "tuft_variant": variant}, source_counts


def connected_components(vertex_count, edges):
    parent = list(range(vertex_count))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a, b in np.asarray(edges, dtype=np.int64):
        parent[root(int(b))] = root(int(a))
    groups = {}
    for i in range(vertex_count):
        groups.setdefault(root(i), []).append(i)
    return list(groups.values())


def refined_prototype_positions(positions, edges, prototype_index):
    """Preserve topology/attributes and every leaf root center; new real shape."""
    old = np.asarray(positions, dtype=np.float64)
    if old.shape[1:] != (3,) or not np.isfinite(old).all():
        raise ValueError("Finite actual prototype positions required")
    parts = connected_components(len(old), edges)
    if len(parts) not in {4, 5, 6} or any(len(p) != 15 for p in parts):
        raise RuntimeError("Actual prototype is not the inventory-confirmed4..6 leaves ×15 vertices")
    result, evidence = old.copy(), []
    t_values = np.array([0., .24, .52, .78, 1.])
    for leaf_index, component in enumerate(parts):
        ids = np.asarray(sorted(component), dtype=np.int64)
        rings = old[ids].reshape(5, 3, 3)
        origin = rings[0, 1].copy()
        across = rings[0, 2]-rings[0, 0]
        across[2] = 0.
        norm = np.linalg.norm(across)
        if norm < .0001 or norm > .004:
            raise RuntimeError("Actual prototype ring orientation/width outside known millimetre layout")
        across /= norm
        tangent = np.cross(across, [0., 0., 1.])
        rng = np.random.default_rng(RECIPE["seed"] + prototype_index*1009 + leaf_index*53 + 17)
        height = rng.uniform(*RECIPE["prototype_leaf_height_m"])
        width = rng.uniform(*RECIPE["prototype_maximum_width_m"])
        pointed = bool(rng.random() < RECIPE["pointed_leaf_probability"])
        tip = rng.uniform(*(RECIPE["pointed_tip_width_factor"] if pointed else RECIPE["clipped_tip_width_factor"]))
        widths = width*np.array([.72, 1., .88, .64, tip])
        lean = rng.uniform(.0035, .008)
        twist = rng.uniform(*RECIPE["longitudinal_twist_rad"])
        fold = rng.uniform(*RECIPE["transverse_fold_m"])
        side_bend = rng.uniform(-.0012, .0012)
        ragged = rng.uniform(-.00012, .00012)
        updated = []
        for level, t in enumerate(t_values):
            center = origin + tangent*lean*t*t + across*side_bend*np.sin(math.pi*t)*t
            center[2] += height*(t+.04*t*(1-t))
            cross = across*math.cos(twist*t)+tangent*math.sin(twist*t)
            for side in (-1, 0, 1):
                v = center+cross*(widths[level]*.5*side)
                if side == 0:
                    v[2] += fold*math.sin(math.pi*t)
                elif level == 4:
                    # Mown leaf tip, not a large horizontal rectangular card.
                    v[2] -= abs(ragged)*(1 if side < 0 else .6)
                updated.append(v)
        updated = np.asarray(updated)
        if not np.array_equal(updated[1], origin):
            raise RuntimeError("Prototype leaf root center moved")
        result[ids] = updated
        evidence.append({"pointed_tip": pointed, "height_m": float(np.ptp(updated[:, 2])),
                         "maximum_width_m": float(widths.max()), "tip_to_root_width_ratio": float(widths[-1]/widths[0]),
                         "root_center_unchanged": True})
    return result.astype(np.float32), evidence


def _co(mesh):
    values = np.empty((len(mesh.vertices), 3), np.float32)
    mesh.vertices.foreach_get("co", values.ravel())
    return values


def _source_arrays(mesh):
    values = {"position": _co(mesh)}
    for name, columns, dtype, field in (("tuft_rotation", 3, np.float32, "vector"),
                                       ("tuft_scale", 3, np.float32, "vector"), ("tuft_variant", 1, np.int32, "value")):
        attr = mesh.attributes.get(name)
        if attr is None or attr.domain != "POINT" or len(attr.data) != len(mesh.vertices):
            raise RuntimeError("Expected actual original point attribute absent: "+name)
        a = np.empty((len(mesh.vertices), columns), dtype)
        attr.data.foreach_get(field, a.ravel())
        values[name] = a[:, 0] if columns == 1 else a
    return values


def _socket_value(value):
    if value is None or isinstance(value, (float, int, bool, str)):
        return value
    if hasattr(value, "name"):
        return {"datablock": value.name}
    try:
        return [_socket_value(v) for v in value]
    except TypeError:
        return str(value)


def _graph_sha(group):
    data = {"nodes": [{"name": n.name, "type": n.bl_idname,
              "inputs": [(s.identifier, _socket_value(s.default_value), s.is_linked) for s in n.inputs if hasattr(s, "default_value")]} for n in group.nodes],
            "links": [(l.from_node.name, l.from_socket.identifier, l.to_node.name, l.to_socket.identifier) for l in group.links]}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _densities(arrays, leaf_counts):
    points, variants = arrays["position"], arrays["tuft_variant"]
    rows = []
    for x in (-2, 0, 2):
        for y in (-26, -24, -22, -20, -18, -16, -14, -12, -8, 0):
            keep = (points[:, 0] >= x) & (points[:, 0] < x+1) & (points[:, 1] >= y) & (points[:, 1] < y+1)
            counts = np.bincount(variants[keep], minlength=24)
            rows.append({"one_m2_bounds_xy": [[x, y], [x+1, y+1]], "actual_tufts_per_m2": int(keep.sum()),
                         "actual_leaves_per_m2": int(np.dot(counts, leaf_counts))})
    return rows


def _protected(snapshot, excluded_meshes, added_object=None):
    # Only explicitly enumerated visual prototypes + the newly added visual
    # grass are excluded. All original object matrices/visibility, actions,
    # physical meshes, cameras, lights/world remain in the equality check.
    result = json.loads(json.dumps(snapshot))
    if added_object:
        result["objects"].pop(added_object.name, None)
    for name in excluded_meshes:
        result["meshes_positions_topology_shape_keys"].pop(name, None)
    return result


def apply_common_turf(*, look, expect_net_present: bool):
    """Root calls after the frozen look, the selective surfaces and the real cache bind, before rendering."""
    import bpy
    scene = bpy.context.scene
    if any(o.get("football_goal_net_turf_added", False) for o in bpy.data.objects):
        raise RuntimeError("Do not apply the shared turf twice")
    carriers = [o for o in scene.objects if o.type == "MESH" and not o.hide_render and o.data.attributes.get("tuft_variant")]
    if len(carriers) != 1:
        raise RuntimeError("Inventory baseline requires one actual visible point carrier, not a guessed name")
    carrier = carriers[0]
    if len(carrier.data.edges) or len(carrier.data.polygons) or not np.allclose(np.asarray(carrier.matrix_world), np.eye(4), rtol=0, atol=1e-8):
        raise RuntimeError("Original grass point-only identity-coordinate baseline changed")
    groups = [m.node_group for m in carrier.modifiers if m.type == "NODES" and m.node_group]
    if len(groups) != 1:
        raise RuntimeError("Unknown actual point-carrier GN stack")
    group = groups[0]
    collection_nodes = [n for n in group.nodes if n.bl_idname == "GeometryNodeCollectionInfo"]
    instances = [n for n in group.nodes if n.bl_idname == "GeometryNodeInstanceOnPoints"]
    info = [n for n in group.nodes if n.bl_idname == "GeometryNodeObjectInfo"]
    if len(collection_nodes) != 1 or len(instances) != 1 or len(info) != 1:
        raise RuntimeError("Actual original instancing/solved-ball compression graph differs")
    collection = collection_nodes[0].inputs["Collection"].default_value
    if collection is None or len(collection.objects) != 24:
        raise RuntimeError("Actual GN Collection pointer must contain24 prototypes")
    if not collection_nodes[0].inputs["Separate Children"].default_value or not collection_nodes[0].inputs["Reset Children"].default_value or not instances[0].inputs["Pick Instance"].default_value:
        raise RuntimeError("Original collection indexing contract changed")
    if any(n.bl_idname == "GeometryNodeRealizeInstances" for n in group.nodes):
        raise RuntimeError("Unexpected realized grass; do not increase realized geometry")
    ball = info[0].inputs["Object"].default_value
    if ball is None or info[0].transform_space != "RELATIVE":
        raise RuntimeError("Original one-way actual-ball dependency absent")
    mapping = [n for n in group.nodes if n.bl_idname == "ShaderNodeMapRange"]
    if len(mapping) != 1 or not mapping[0].clamp or mapping[0].interpolation_type != "SMOOTHSTEP" or not all(abs(mapping[0].inputs[k].default_value-v) < 1e-6 for k, v in (("From Min", .111), ("From Max", .138), ("To Min", .12), ("To Max", 1.))):
        raise RuntimeError("Actual one-way compression law changed; no silent substitute")
    prototypes = list(collection.objects)  # Preserve actual CollectionInfo instance ordering.
    if any(o.type != "MESH" for o in prototypes):
        raise RuntimeError("Actual prototype collection includes nonmesh objects")
    prototype_meshes = {o.data for o in prototypes}
    if any(o not in prototypes and o.type == "MESH" and o.data in prototype_meshes for o in bpy.data.objects):
        raise RuntimeError("Prototype mesh also belongs to a non-grass object")
    nets = [o for o in scene.objects if o.name.startswith("visible net =") and not o.hide_render]
    if len(nets) != int(expect_net_present):
        raise RuntimeError("Real cache/net presence differs before common turf change")
    before = look.protected_state()
    net_before = look.evaluated_net_digest(nets[0]) if nets else None
    source = _source_arrays(carrier.data)
    source_records = {k: record(v) for k, v in source.items()}
    graph_before = _graph_sha(group)
    old_mesh_names = {o.data.name for o in prototypes}
    changes, leaf_counts, new_mesh_names = [], [], set()
    for index, obj in enumerate(prototypes):
        original = obj.data
        vertices = _co(original)
        edges = np.empty((len(original.edges), 2), np.int32)
        original.edges.foreach_get("vertices", edges.ravel())
        revised, leaf_info = refined_prototype_positions(vertices, edges, index)
        new = original.copy()
        new.name = "tapered mown tuft "+str(index).zfill(2)
        new.vertices.foreach_set("co", revised.ravel())
        new.update()
        obj.data = new
        new_mesh_names.add(new.name)
        leaf_counts.append(len(leaf_info))
        changes.append({"object": obj.name, "original_mesh": original.name, "new_mesh": new.name,
                        "original_geometry_sha256": look.mesh_digest(original), "revised_geometry_sha256": look.mesh_digest(new),
                        "positions_before": record(vertices), "positions_after_actual": record(_co(new)),
                        "vertex_count_unchanged": len(new.vertices) == len(original.vertices), "polygons_unchanged": len(new.polygons) == len(original.polygons),
                        "materials_unchanged": [m.name for m in original.materials] == [m.name for m in new.materials], "leaves": leaf_info})
    extra, component_counts = foreground_arrays()
    mesh = bpy.data.meshes.new("deterministic foreground grass point roots")
    mesh.vertices.add(len(extra["position"]))
    mesh.vertices.foreach_set("co", extra["position"].ravel())
    for name, kind, field in (("tuft_rotation", "FLOAT_VECTOR", "vector"), ("tuft_scale", "FLOAT_VECTOR", "vector"), ("tuft_variant", "INT", "value")):
        mesh.attributes.new(name=name, type=kind, domain="POINT").data.foreach_set(field, extra[name].ravel())
    mesh.update()
    added = bpy.data.objects.new("common foreground grass roots | visual only", mesh)
    scene.collection.objects.link(added)
    added["football_goal_net_turf_added"] = True
    added["pcve_role"] = "visual_only_grass_not_collision"
    modifier = added.modifiers.new("Unchanged shared original tuft instancing and solved-ball compression", "NODES")
    modifier.node_group = group
    bpy.context.view_layer.update()
    after = look.protected_state()
    protected_before = _protected(before, old_mesh_names)
    protected_after = _protected(after, new_mesh_names | {mesh.name}, added)
    net_after = look.evaluated_net_digest(nets[0]) if nets else None
    source_after = {k: record(v) for k, v in _source_arrays(carrier.data).items()}
    if protected_before != protected_after or net_before != net_after or source_records != source_after or graph_before != _graph_sha(group):
        raise RuntimeError("changed protected actor/fixture/pose/camera/light/action/world/original grass points/GN law")
    old_density, extra_density = _densities(source, leaf_counts), _densities(extra, leaf_counts)
    total_density = [{"one_m2_bounds_xy": a["one_m2_bounds_xy"], "old_actual_tufts_per_m2": a["actual_tufts_per_m2"],
                      "added_actual_tufts_per_m2": b["actual_tufts_per_m2"], "total_actual_tufts_per_m2": a["actual_tufts_per_m2"]+b["actual_tufts_per_m2"],
                      "total_actual_leaves_per_m2": a["actual_leaves_per_m2"]+b["actual_leaves_per_m2"]} for a, b in zip(old_density, extra_density)]
    return {"recipe": RECIPE, "recipe_sha256": RECIPE_SHA256, "all_six_cases_same_recipe_required": True,
            "actual_carrier": carrier.name, "actual_collection_pointer_name": collection.name,
            "actual_collection_prototype_order": [o.name for o in prototypes], "prototype_changes": changes,
            "original_roots_count": len(source["position"]), "added_roots_count": len(extra["position"]), "total_roots_count": len(source["position"])+len(extra["position"]),
            "foreground_components": component_counts, "added_point_arrays": {k: record(v) for k, v in extra.items()},
            "original_point_arrays_before": source_records, "original_point_arrays_after": source_after,
            "protected_original_actor_camera_fixture_state_before_sha256": hashlib.sha256(json.dumps(protected_before, sort_keys=True).encode()).hexdigest(),
            "protected_original_actor_camera_fixture_state_after_sha256": hashlib.sha256(json.dumps(protected_after, sort_keys=True).encode()).hexdigest(),
            "net_evaluated_before_sha256": net_before, "net_evaluated_after_sha256": net_after,
            "original_instance_compression_group_sha256": graph_before, "new_roots_reuse_identical_node_group_pointer": modifier.node_group == group,
            "local_actual_density": total_density, "new_instances_realized": False, "source_and_edit_initial_pose_change": False,
            "canopy_materials_lighting_cameras_keyframes_or_collision_changes": False,
            "coupled_grass_solver_or_material_calibration_or_movie_grade_acceptance": False}
