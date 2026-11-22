"""Render the exact QA-owned finite boxes of the new fixed ADD identity.

No bevel geometry, extra supports, altered panel extents or existing-object
changes. Root calls only for training_rebound_board presence=true. Shader
bevel/normal detail is not a collision or geometry bevel.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import bpy




def shader(name, color, roughness, metallic=0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    surface = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    surface.inputs["Base Color"].default_value = (*color, 1)
    surface.inputs["Roughness"].default_value = roughness
    surface.inputs["Metallic"].default_value = metallic
    geometry = tree.nodes.new("ShaderNodeNewGeometry")
    noise = tree.nodes.new("ShaderNodeTexNoise")
    tree.links.new(geometry.outputs["Position"], noise.inputs["Vector"])
    noise.inputs["Scale"].default_value = 1700
    bump = tree.nodes.new("ShaderNodeBump")
    tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    bump.inputs["Distance"].default_value, bump.inputs["Strength"].default_value = .000025, .2
    bevel = tree.nodes.new("ShaderNodeBevel")
    bevel.inputs["Radius"].default_value = .0008
    bevel.samples = 4
    tree.links.new(bump.outputs[0], bevel.inputs["Normal"])
    tree.links.new(bevel.outputs[0], surface.inputs["Normal"])
    return mat


def build_from_frozen_preset(preset_path, *, present):
    path = Path(preset_path)
    existing = [obj.name for obj in bpy.data.objects if obj.get("pcve_stable_id") == "training_rebound_board"]
    if not present and existing:
        raise RuntimeError("Source/absence case unexpectedly contains the new ADD identity")
    if not present:
        return {"stable_id": "training_rebound_board", "present": False, "objects_added": []}
    if existing:
        raise RuntimeError("Do not duplicate or replace an existing ADD identity")
    preset = json.loads(path.read_text(encoding="utf-8"))
    # The QA schema adapter is deliberately explicit below: no guessed fallback
    # boxes or transforms if the agreed field names change.
    components = preset.get("components", preset.get("boxes"))
    if not isinstance(components, list) or len(components) != 5:
        raise RuntimeError("Expected the five frozen QA box components")
    panel_mat = shader("new training board | matte tough polymer", (.065, .10, .12), .56)
    steel_mat = shader("new fixed training board | powder-coated steel", (.11, .12, .115), .43)
    root = bpy.data.objects.new("ADDED anchored training_rebound_board", None)
    root["pcve_stable_id"] = "training_rebound_board"
    bpy.context.scene.collection.objects.link(root)
    records = []
    for index, item in enumerate(components):
        identity = item.get("id", item.get("name"))
        center = item.get("center_m", item.get("center_world_m"))
        size = item.get("dimensions_xyz_m")
        quat = item.get("orientation_wxyz", item.get("quaternion_wxyz", [1, 0, 0, 0]))
        if not identity or center is None or size is None or list(quat) != [1, 0, 0, 0]:
            raise RuntimeError("Unknown frozen component schema or non-axis-aligned collider")
        vertices = [(center[0]+sx*size[0]/2, center[1]+sy*size[1]/2, center[2]+sz*size[2]/2)
                    for sx, sy, sz in ((-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),
                                      (1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1))]
        faces = [(0,4,6,2),(1,3,7,5),(0,1,5,4),(2,6,7,3),(0,2,3,1),(4,5,7,6)]
        mesh = bpy.data.meshes.new("exact QA box "+str(identity))
        mesh.from_pydata(vertices, [], faces); mesh.update()
        obj = bpy.data.objects.new("ADDED training_rebound_board / "+str(identity), mesh)
        bpy.context.scene.collection.objects.link(obj); obj.parent = root
        obj["pcve_stable_id"] = "training_rebound_board"
        mesh.materials.append(panel_mat if "panel" in str(identity).lower() else steel_mat)
        records.append({"component": identity, "object": obj.name, "center_world_m": center,
                        "dimensions_xyz_m": size, "geometry_bevel": False, "additional_parts": False})
    return {"stable_id": "training_rebound_board", "present": True,
            "preset_path": str(path), "objects_added": records,
            "same_five_finite_visible_and_collision_boxes": True,
            "installation_acceptance": "not asserted; independent clearance/surface export required"}
