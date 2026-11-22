"""Common look of the packed scene (net, frame, ball and turf shaders); used by appearance/render.py.

No actor transform/vertex/shape-key/collider/camera/light changes. Net GN only
adds shader coordinates; its evaluated surface is SHA checked. Optional grass
angle variation affects visual-only point attributes, never collision actors.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import socket
import sys

import bpy
import numpy as np


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()




def node(tree, kind, **kwargs):
    n = tree.nodes.new(kind)
    for key, value in kwargs.items():
        setattr(n, key, value)
    return n


def wire(tree, value, target):
    if hasattr(value, "node"):
        tree.links.new(value, target)
    else:
        target.default_value = value


def scalar(tree, operation, first, second=None):
    n = node(tree, "ShaderNodeMath", operation=operation)
    wire(tree, first, n.inputs[0])
    if second is not None:
        wire(tree, second, n.inputs[1])
    return n.outputs[0]


def mix(tree, a, b, factor, blend="MIX"):
    n = node(tree, "ShaderNodeMixRGB", blend_type=blend)
    wire(tree, factor, n.inputs[0]); wire(tree, a, n.inputs[1]); wire(tree, b, n.inputs[2])
    return n.outputs[0]


def noise(tree, position, frequency, detail=2):
    n = node(tree, "ShaderNodeTexNoise")
    wire(tree, position, n.inputs["Vector"])
    n.inputs["Scale"].default_value = frequency
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = .65
    return n.outputs["Fac"]


def source(socket):
    if socket.is_linked:
        return socket.links[0].from_socket
    value = socket.default_value
    return value[:] if hasattr(value, "__len__") else value


def bump(tree, surface, height, distance, strength):
    old = surface.inputs["Normal"].links[0].from_socket if surface.inputs["Normal"].is_linked else None
    n = node(tree, "ShaderNodeBump")
    wire(tree, height, n.inputs["Height"])
    n.inputs["Distance"].default_value, n.inputs["Strength"].default_value = distance, strength
    if old is not None:
        tree.links.new(old, n.inputs["Normal"])
    tree.links.new(n.outputs[0], surface.inputs["Normal"])


def mesh_digest(mesh):
    h = hashlib.sha256()
    for collection, field, count, dtype in ((mesh.vertices, "co", 3, np.float32),
                                             (mesh.edges, "vertices", 2, np.int32),
                                             (mesh.loops, "vertex_index", 1, np.int32),
                                             (mesh.polygons, "loop_total", 1, np.int32)):
        values = np.empty(len(collection)*count, dtype)
        collection.foreach_get(field, values)
        h.update(str((field, len(collection), count)).encode()); h.update(values.tobytes())
    if mesh.shape_keys:
        for key in mesh.shape_keys.key_blocks:
            coords = np.empty(len(key.data)*3, np.float32)
            key.data.foreach_get("co", coords)
            h.update(key.name.encode()); h.update(coords.tobytes())
    return h.hexdigest()


def protected_state():
    scene = bpy.context.scene
    objects, meshes = {}, {}
    for obj in scene.objects:
        objects[obj.name] = {"type": obj.type, "matrix": [list(row) for row in obj.matrix_world],
                             "hide_render": obj.hide_render}
        if obj.type == "MESH" and obj.data.name not in meshes:
            meshes[obj.data.name] = mesh_digest(obj.data)
    cameras = {}
    for obj in scene.objects:
        if obj.type == "CAMERA":
            cam = obj.data
            cameras[obj.name] = {"matrix": [list(row) for row in obj.matrix_world], "lens": cam.lens,
                                 "sensor": [cam.sensor_width, cam.sensor_height, cam.sensor_fit],
                                 "shift": [cam.shift_x, cam.shift_y], "clip": [cam.clip_start, cam.clip_end],
                                 "dof": [cam.dof.use_dof, cam.dof.aperture_fstop, cam.dof.focus_distance]}
    lights = {obj.name: {"type": obj.data.type, "energy": obj.data.energy, "color": list(obj.data.color),
                         "matrix": [list(row) for row in obj.matrix_world]} for obj in scene.objects if obj.type == "LIGHT"}
    actions = {}
    for action in bpy.data.actions:
        h = hashlib.sha256()
        for curve in action.fcurves:
            h.update(str((curve.data_path, curve.array_index, curve.extrapolation)).encode())
            for point in curve.keyframe_points:
                h.update(str((tuple(point.co), tuple(point.handle_left), tuple(point.handle_right), point.interpolation)).encode())
        actions[action.name] = h.hexdigest()
    world = None
    if scene.world and scene.world.use_nodes:
        world = {"name": scene.world.name,
                 "nodes": [{"name": n.name, "type": n.bl_idname,
                            "image": n.image.name if hasattr(n, "image") and n.image else None,
                            "inputs": [(s.identifier, str(s.default_value)) for s in n.inputs if hasattr(s, "default_value")]}
                           for n in scene.world.node_tree.nodes],
                 "links": [(link.from_node.name, link.from_socket.identifier, link.to_node.name, link.to_socket.identifier)
                           for link in scene.world.node_tree.links]}
    return {"objects": objects, "meshes_positions_topology_shape_keys": meshes, "cameras": cameras,
            "active_camera": scene.camera.name if scene.camera else None, "lights": lights,
            "all_action_curve_hashes": actions, "world_shader": world,
            "color_management": [scene.view_settings.view_transform, scene.view_settings.look, scene.view_settings.exposure]}


def evaluated_net_digest(obj):
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(graph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=False, depsgraph=graph)
    try:
        return mesh_digest(mesh)
    finally:
        evaluated.to_mesh_clear()


def rope_attribute_evidence(obj):
    graph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(graph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
    result = {}
    try:
        for name in ("rope_arc_m", "rope_profile_u"):
            attribute = mesh.attributes.get(name)
            if not attribute or attribute.data_type != "FLOAT":
                raise RuntimeError(f"Rope shader coordinate did not survive Curve to Mesh: {name}")
            values = np.empty(len(attribute.data), np.float32)
            attribute.data.foreach_get("value", values)
            if not len(values) or not np.isfinite(values).all() or float(values.max()-values.min()) < .001:
                raise RuntimeError(f"Rope shader coordinate is absent/constant/non-finite: {name}")
            result[name] = {"domain": attribute.domain, "count": len(values),
                            "range": [float(values.min()), float(values.max())],
                            "sha256": hashlib.sha256(values.tobytes()).hexdigest()}
        return result
    finally:
        evaluated.to_mesh_clear()


def store(tree, geometry, field, name):
    n = node(tree, "GeometryNodeStoreNamedAttribute", data_type="FLOAT", domain="POINT")
    tree.links.new(geometry, n.inputs["Geometry"])
    n.inputs["Name"].default_value = name
    tree.links.new(field, n.inputs["Value"])
    return n.outputs["Geometry"]


def add_rope_coordinates(obj):
    modifier = next((m for m in obj.modifiers if m.type == "NODES" and m.node_group), None)
    if not modifier:
        raise RuntimeError("Exact physical net has no known geometry-node tube builder")
    tree = modifier.node_group.copy()
    tree.name = "same net surface | shader-only braid coordinates"
    tubes = [n for n in tree.nodes if n.bl_idname == "GeometryNodeCurveToMesh"]
    if len(tubes) != 1:
        raise RuntimeError("Expected exactly one original Curve to Mesh node")
    tube = tubes[0]
    for socket, attr_name, parameter in (("Curve", "rope_arc_m", "Length"),
                                         ("Profile Curve", "rope_profile_u", "Factor")):
        if len(tube.inputs[socket].links) != 1:
            raise RuntimeError("Unknown original rope tube inputs")
        geometry = tube.inputs[socket].links[0].from_socket
        spline = node(tree, "GeometryNodeSplineParameter")
        result = store(tree, geometry, spline.outputs[parameter], attr_name)
        tree.links.new(result, tube.inputs[socket])
    modifier.node_group = tree
    return {"node_group": tree.name, "added_attributes": ["rope_arc_m", "rope_profile_u"],
            "no_radius_resolution_or_position_input_changed": True}


def improve_material(original, kind):
    material = original.copy()
    material.name = kind + " | " + original.name
    tree = material.node_tree
    surfaces = [n for n in tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"]
    if len(surfaces) != 1:
        raise RuntimeError(f"Expected one existing Principled surface for {original.name}")
    surface = surfaces[0]
    geometry = node(tree, "ShaderNodeNewGeometry")
    pos = geometry.outputs["Position"]
    old_color = source(surface.inputs["Base Color"])
    coarse, fine = noise(tree, pos, 2.7), noise(tree, pos, 1750, 2)
    report = {"original": original.name, "new": material.name, "kind": kind,
              "existing_packed_image_nodes_preserved": True, "true_displacement_added": False}
    if kind == "braided synthetic net":
        arc = node(tree, "ShaderNodeAttribute", attribute_name="rope_arc_m").outputs["Fac"]
        around = node(tree, "ShaderNodeAttribute", attribute_name="rope_profile_u").outputs["Fac"]
        along = scalar(tree, "MULTIPLY", arc, 2*math.pi/.008)
        turn = scalar(tree, "MULTIPLY", around, 2*math.pi*6)
        first = scalar(tree, "SINE", scalar(tree, "ADD", along, turn))
        second = scalar(tree, "SINE", scalar(tree, "SUBTRACT", along, turn))
        weave = scalar(tree, "ADD", .5, scalar(tree, "MULTIPLY", scalar(tree, "MAXIMUM", first, second), .5))
        filaments = scalar(tree, "SINE", scalar(tree, "ADD", scalar(tree, "MULTIPLY", arc, 2*math.pi/.0006),
                                               scalar(tree, "MULTIPLY", around, 2*math.pi*72)))
        dirt = scalar(tree, "MULTIPLY", scalar(tree, "POWER", coarse, 3), .16)
        tint = mix(tree, (.70, .72, .66, 1), (.29, .26, .19, 1), dirt)
        wire(tree, tint, surface.inputs["Base Color"])
        wire(tree, scalar(tree, "ADD", .51, scalar(tree, "MULTIPLY", fine, .23)), surface.inputs["Roughness"])
        surface.inputs["Metallic"].default_value = 0
        surface.inputs["IOR"].default_value = 1.49
        surface.inputs["Sheen Weight"].default_value = .11
        bump(tree, surface, weave, .000045, .40)
        bump(tree, surface, filaments, .000007, .20)
        report.update({"braid_lay_m": .008, "bundle_cycles_around_cord": 6,
                       "bundle_bump_distance_m": .000045, "filament_bump_distance_m": .000007,
                       "no_fiber_silhouette_or_junction_knots_added": True,
                       "polymer_and_weave_are_explicit_visual_assumptions_not_supplier_identification": True})
    elif kind == "living grass leaves":
        micro = noise(tree, pos, 105, 2)
        gain = scalar(tree, "ADD", .90, scalar(tree, "MULTIPLY", micro, .18))
        wire(tree, mix(tree, old_color, gain, 1, "MULTIPLY"), surface.inputs["Base Color"])
        # Retain the original 110mm paint mask; carry the same final colour to
        # its translucent branch, not a separate unpainted neon transmission.
        for n in tree.nodes:
            if n.bl_idname == "ShaderNodeBsdfTranslucent":
                tree.links.new(surface.inputs["Base Color"].links[0].from_socket, n.inputs[0])
        wire(tree, scalar(tree, "ADD", .34, scalar(tree, "MULTIPLY", micro, .28)), surface.inputs["Roughness"])
        surface.inputs["Sheen Weight"].default_value = .12
        bump(tree, surface, fine, .000012, .18)
        report.update({"additional_pigment_gain": [.90, 1.08], "roughness_range": [.34, .62],
                       "leaf_micro_normal_depth_m": .000012})
    elif kind == "continuous living canopy substrate":
        variation = noise(tree, pos, 38, 2)
        gain = scalar(tree, "ADD", .94, scalar(tree, "MULTIPLY", variation, .12))
        wire(tree, mix(tree, old_color, gain, 1, "MULTIPLY"), surface.inputs["Base Color"])
        old_roughness = source(surface.inputs["Roughness"])
        wire(tree, scalar(tree, "MULTIPLY", old_roughness,
                           scalar(tree, "ADD", .90, scalar(tree, "MULTIPLY", variation, .15))),
             surface.inputs["Roughness"])
        report.update({"original_2p51m_root_pbr_and_paint_chain_retained": True,
                       "short_scale_pigment_gain": [.94, 1.06], "new_displacement_or_density": False})
    elif kind == "maintained cast concrete":
        xyz = node(tree, "ShaderNodeSeparateXYZ")
        tree.links.new(pos, xyz.inputs[0])
        runoff = noise(tree, pos, 9, 2)
        near_ground = scalar(tree, "SUBTRACT", 1, scalar(tree, "MINIMUM", scalar(tree, "MULTIPLY", xyz.outputs["Z"], .8), 1))
        stain = scalar(tree, "MULTIPLY", scalar(tree, "POWER", coarse, 3), .25)
        stain = scalar(tree, "ADD", stain, scalar(tree, "MULTIPLY", near_ground, scalar(tree, "MULTIPLY", runoff, .12)))
        wire(tree, mix(tree, old_color, (.078, .087, .065, 1), stain), surface.inputs["Base Color"])
        # Preserve official 2m scalar-height/PBR detail below the new small pores.
        bump(tree, surface, noise(tree, pos, 480, 2), .00028, .25)
        report.update({"maximum_extra_stain_mix": .37, "extra_pore_depth_m": .00028,
                       "official_concrete_2m_maps_and_prior_height_chain_retained": True})
    elif kind == "maintained printed pitchside panel":
        xyz = node(tree, "ShaderNodeSeparateXYZ"); tree.links.new(pos, xyz.inputs[0])
        low_edge = scalar(tree, "MAXIMUM", 0, scalar(tree, "SUBTRACT", 1, scalar(tree, "MULTIPLY", xyz.outputs["Z"], 8)))
        scuff = scalar(tree, "MULTIPLY", scalar(tree, "POWER", noise(tree, pos, 11, 2), 4), .065)
        dirt = scalar(tree, "ADD", scuff, scalar(tree, "MULTIPLY", low_edge, .06))
        wire(tree, mix(tree, old_color, (.095, .085, .062, 1), dirt), surface.inputs["Base Color"])
        wire(tree, scalar(tree, "ADD", .48, scalar(tree, "MULTIPLY", noise(tree, pos, 17, 2), .16)), surface.inputs["Roughness"])
        bump(tree, surface, fine, .000015, .18)
        report.update({"actual_panel_material_matched": True, "print_and_front_back_shader_chain_retained": True,
                       "grain_depth_m": .000015, "not_concrete_or_emissive_led": True})
    elif kind == "moulded polypropylene chairs":
        weather = noise(tree, pos, 4.5, 2)
        fade = scalar(tree, "MULTIPLY", scalar(tree, "POWER", weather, 2), .11)
        wire(tree, mix(tree, old_color, (.075, .115, .145, 1), fade), surface.inputs["Base Color"])
        wire(tree, scalar(tree, "ADD", .38, scalar(tree, "MULTIPLY", weather, .23)), surface.inputs["Roughness"])
        surface.inputs["Coat Weight"].default_value = .045
        bump(tree, surface, noise(tree, pos, 2200, 2), .000035, .22)
        report.update({"bounded_uv_weather_mix_max": .11, "mould_microtexture_m": .000035,
                       "native_component_tone_and_true_curved_shells_retained": True})
    else:
        # Sparse maintained dust and coating grain, never rust applied uniformly
        # to aluminium or pristine uncoated metal underneath all powder paint.
        dust = scalar(tree, "MULTIPLY", scalar(tree, "POWER", coarse, 4), .07)
        wire(tree, mix(tree, old_color, (.14, .13, .10, 1), dust), surface.inputs["Base Color"])
        bump(tree, surface, fine, .000024, .18)
        report.update({"sparse_dust_mix_max": .07, "extra_coating_grain_m": .000024})
    material["procedural_detail_assumption"] = True
    return material, report


def replace_material_references(mapping):
    uses = []
    for mesh in bpy.data.meshes:
        for index, material in enumerate(mesh.materials):
            if material in mapping:
                mesh.materials[index] = mapping[material]
                uses.append({"mesh": mesh.name, "slot": index})
    for obj in bpy.data.objects:
        for slot in obj.material_slots:
            if slot.link == "OBJECT" and slot.material in mapping:
                slot.material = mapping[slot.material]
    for group in bpy.data.node_groups:
        for n in group.nodes:
            for sock in n.inputs:
                if sock.type == "MATERIAL" and sock.default_value in mapping:
                    sock.default_value = mapping[sock.default_value]
    return uses


def grass_angles():
    records = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.hide_render or "grass tufts" not in obj.name:
            continue
        attr = obj.data.attributes.get("tuft_rotation")
        if not attr:
            continue
        count = len(obj.data.vertices)
        values = np.empty((count, 3), np.float32)
        attr.data.foreach_get("vector", values.ravel())
        before = hashlib.sha256(values.tobytes()).hexdigest()
        pos = np.empty((count, 3), np.float32); obj.data.vertices.foreach_get("co", pos.ravel())
        phase = pos[:, 0].astype(np.float64)*73.913+pos[:, 1].astype(np.float64)*47.271
        values[:, 0] += (.025*np.sin(phase)).astype(np.float32)
        values[:, 1] += (.025*np.sin(phase*1.371+1.3)).astype(np.float32)
        values[:, 2] += (.12*np.sin(phase*.731)).astype(np.float32)
        attr.data.foreach_set("vector", values.ravel()); obj.data.update()
        records.append({"object": obj.name, "count": count, "original_rotation_sha256": before,
                        "rotation_sha256": hashlib.sha256(values.tobytes()).hexdigest(),
                        "max_component_delta_rad": [.025, .025, .12],
                        "world_position_deterministic_no_case_seed": True,
                        "only_visual_grass_no_collider_or_ball_feedback": True})
    return records


def enhance_loaded_scene(*, expect_net_present: bool, vary_visual_grass=True):
    before = protected_state()
    nets = [obj for obj in bpy.context.scene.objects if obj.name.startswith("visible net =") and not obj.hide_render]
    if len(nets) != (1 if expect_net_present else 0):
        raise RuntimeError("Visible solved net presence differs from explicit cache-bound expect_net_present")
    net = nets[0] if expect_net_present else None
    evaluated_before = evaluated_net_digest(net) if net else None
    coordinate_report = add_rope_coordinates(net) if net else {"net_expected_present": False, "not_applicable": True}
    rope_materials = set()
    for mod in net.modifiers if net else []:
        if mod.type == "NODES":
            for n in mod.node_group.nodes:
                for sock in n.inputs:
                    if sock.type == "MATERIAL" and sock.default_value:
                        rope_materials.add(sock.default_value)
    if expect_net_present and not rope_materials:
        raise RuntimeError("Original exact net shader binding not found")
    mapping, material_reports = {}, []
    for mat in list(bpy.data.materials):
        kind = None
        if mat in rope_materials:
            kind = "braided synthetic net"
        elif mat.name.startswith("cut ryegrass/fine fescue"):
            kind = "living grass leaves"
        elif mat.name.startswith("living canopy over"):
            kind = "continuous living canopy substrate"
        elif mat.name.startswith("cast concrete"):
            kind = "maintained cast concrete"
        elif mat.name.startswith("non-emissive professional matte pitchside panel"):
            kind = "maintained printed pitchside panel"
        elif mat.name.startswith("UV-stabilised injection-moulded polypropylene"):
            kind = "moulded polypropylene chairs"
        elif mat.name.startswith(("galvanized guardrails", "charcoal powder-coated", "satin white polyester")):
            kind = "maintained metal coating"
        if kind:
            mapping[mat], record = improve_material(mat, kind)
            material_reports.append(record)
    uses = replace_material_references(mapping)
    foliage = grass_angles() if vary_visual_grass else []
    bpy.context.view_layer.update()
    after, evaluated_after = protected_state(), evaluated_net_digest(net) if net else None
    if before != after:
        raise RuntimeError("look changed protected object/actor geometry, transform, camera, light or colour management")
    if evaluated_before != evaluated_after:
        raise RuntimeError("Shader-coordinate GN unexpectedly changed the actual evaluated net surface")
    attributes = rope_attribute_evidence(net) if net else {}
    return {"materials": material_reports, "material_slot_uses": uses,
            "expect_net_present_from_cache": expect_net_present,
            "net_coordinates": coordinate_report, "evaluated_rope_coordinate_evidence": attributes,
            "visual_grass_angle_revision": foliage,
            "protected_state_before_sha256": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
            "protected_state_after_sha256": hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest(),
            "net_evaluated_before_sha256": evaluated_before, "net_evaluated_after_sha256": evaluated_after,
            "protected_geometry_transforms_cameras_lighting_byte_identical": True,
            "knots_or_fiber_silhouette_geometry_added": False,
            "true_displacement_added": False,
            "all_cases_must_use_same_common_look": True,
            "photoreal_or_physical_calibration_pass": "not asserted; actual same-camera renders required"}
