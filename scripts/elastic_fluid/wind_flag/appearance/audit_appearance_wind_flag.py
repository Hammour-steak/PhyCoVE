"""Run in Blender to compare non-simulated scene content of a paired edit."""
import hashlib
import json
import sys
from pathlib import Path

import bpy


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def value_of(value):
    if isinstance(value, (bool, int, float, str)):
        return value
    try:
        return list(value)
    except TypeError:
        return str(value)


def node_signature(tree):
    nodes = []
    if tree:
        for node in tree.nodes:
            item = {"name": node.name, "type": node.bl_idname,
                    "inputs": {s.identifier: value_of(s.default_value) for s in node.inputs
                               if hasattr(s, "default_value")}}
            if getattr(node, "image", None):
                image = node.image
                item["image"] = image.name
            for attr in ("operation", "blend_type", "extension"):
                if hasattr(node, attr):
                    item[attr] = getattr(node, attr)
            nodes.append(item)
    links = [] if not tree else sorted((l.from_node.name, l.from_socket.identifier,
                                       l.to_node.name, l.to_socket.identifier) for l in tree.links)
    return {"nodes": sorted(nodes, key=lambda n: n["name"]), "links": links}


def signature(path):
    bpy.ops.wm.open_mainfile(filepath=str(path.resolve()))
    scene = bpy.context.scene
    objects = []
    for obj in sorted(scene.objects, key=lambda o: o.name):
        item = {"name": obj.name, "type": obj.type,
                "matrix": [list(row) for row in obj.matrix_world],
                "materials": [m.name for m in getattr(obj.data, "materials", [])]}
        if obj.type == "MESH":
            item["uv_layers"] = {layer.name: [list(loop.uv) for loop in layer.data] for layer in obj.data.uv_layers}
            if obj.name == "Flag_Genesis_FEM":
                item["topology"] = [tuple(p.vertices) for p in obj.data.polygons]
            else:
                item["vertices"] = [list(v.co) for v in obj.data.vertices]
                item["faces"] = [tuple(p.vertices) for p in obj.data.polygons]
            item["modifiers"] = [
                {"name": mod.name, "type": mod.type,
                 **{key: value_of(getattr(mod,key)) for key in (
                     "show_render", "thickness", "offset", "use_rim", "levels", "render_levels", "width", "segments")
                    if hasattr(mod,key)}} for mod in obj.modifiers]
        if obj.type == "CAMERA":
            item["camera"] = {"lens": obj.data.lens, "sensor_width": obj.data.sensor_width,
                              "use_dof": obj.data.dof.use_dof,
                              "focus_distance": obj.data.dof.focus_distance,
                              "fstop": obj.data.dof.aperture_fstop}
        if obj.type == "LIGHT":
            item["light"] = {"energy": obj.data.energy, "color": list(obj.data.color),
                             "type": obj.data.type}
        objects.append(item)
    images = {im.name: hashlib.sha256(im.packed_file.data).hexdigest()
              for im in bpy.data.images if im.source == "FILE" and im.packed_file}
    missing = [im.name for im in bpy.data.images if im.source == "FILE" and not im.packed_file]
    data = {"objects": objects, "images": images,
            "materials": {m.name: node_signature(m.node_tree) for m in bpy.data.materials},
            "world": node_signature(scene.world.node_tree),
            "render": [scene.render.engine, scene.render.resolution_x, scene.render.resolution_y,
                       scene.render.resolution_percentage, scene.render.fps, scene.render.fps_base,
                       scene.view_settings.view_transform, scene.view_settings.look,
                       scene.eevee.taa_render_samples, scene.render.use_motion_blur, scene.render.motion_blur_shutter]}
    return {"appearance_sha256": digest(data), "packed_image_count": len(images),
            "unpacked_images": missing, "scene": str(path)}


root = Path(sys.argv[sys.argv.index("--") + 1])
case_names = tuple(sys.argv[sys.argv.index("--") + 2:]) or ("source", "flow_6mps", "young_stiff", "wind_drop_at_2s")
results = {case: signature(root / case / "scene.blend") for case in case_names}
results["nonanimated_scene_content_identical"] = (
    len({results[case]["appearance_sha256"] for case in case_names}) == 1)
results["scope"] = "Static geometry, cloth topology, UVs, thickness/subdivision and other common modifier settings, transforms, cameras/DOF, lights, packed textures, material/world nodes and render settings including samples and motion blur; cloth deformation is excluded."
assert results["nonanimated_scene_content_identical"], results
assert all(not results[c]["unpacked_images"] for c in case_names), results
(root / "appearance_audit.json").write_text(json.dumps(results, indent=2), encoding="utf8")
print(json.dumps(results, indent=2))
