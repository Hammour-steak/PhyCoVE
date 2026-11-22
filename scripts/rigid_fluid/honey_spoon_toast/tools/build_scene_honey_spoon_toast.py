"""Build the static Blender scene of the honey simulation: table, plate, toast, and the concave spoon of
physics/spoon_reservoir_geometry.py around its finite honey reservoir."""

from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

TOAST_CENTER = (0.095, 0.0, 0.786)
TOAST_SIZE = (0.130, 0.105, 0.022)


def parse_args():
    av = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--toast-asset", type=Path,
                   help="Optional .glb/.gltf/.obj toast; normalized to 13 x 10.5 x 2.2 cm from world bounds")
    return p.parse_args(av)


def material(name, base, roughness=0.5, metallic=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*base, 1.0)
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Metallic"].default_value = metallic
    return m


def noisy_material(name, base, dark, scale, roughness, bump_strength):
    m = material(name, base, roughness)
    nt, b = m.node_tree, m.node_tree.nodes.get("Principled BSDF")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 5.0
    noise.inputs["Roughness"].default_value = 0.72
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].color = (*base, 1.0)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.0012
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def cube(name, center, size, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=center)
    obj = bpy.context.object
    obj.name = name
    obj.scale = tuple(v / 2 for v in size)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = obj.modifiers.new("RealScaleBevel", "BEVEL")
        mod.width = bevel
        mod.segments = 5
    obj.data.materials.append(mat)
    return obj


def prism(name, center, outline, height, mat, bevel=0.0):
    count = len(outline)
    vertices = [(center[0] + x, center[1] + y, center[2] - height / 2) for x, y in outline]
    vertices += [(center[0] + x, center[1] + y, center[2] + height / 2) for x, y in outline]
    faces = [tuple(reversed(range(count))), tuple(range(count, 2 * count))]
    for i in range(count):
        j = (i + 1) % count
        faces.append((i, j, count + j, count + i))
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("RealScaleBevel", "BEVEL")
        mod.width = bevel
        mod.segments = 5
    return obj


def world_bounds(objects):
    pts = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def import_toast(path):
    before = set(bpy.data.objects)
    suffix = path.suffix.lower()
    if suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path.resolve()))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path.resolve()))
    else:
        raise ValueError("--toast-asset supports .glb/.gltf/.obj")
    imported = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    if not imported:
        raise RuntimeError("toast asset imported no mesh objects")
    lo, hi = world_bounds(imported)
    extent = hi - lo
    scale = min(TOAST_SIZE[i] / max(extent[i], 1e-8) for i in range(3))
    center = (lo + hi) / 2
    for obj in imported:
        obj.scale *= scale
        obj.location = Vector(TOAST_CENTER) + scale * (obj.location - center)
        obj.name = "PCVE_ToastAsset_" + obj.name
    lo2, hi2 = world_bounds(imported)
    dz = TOAST_CENTER[2] - (lo2.z + hi2.z) / 2
    for obj in imported:
        obj.location.z += dz
    return imported, {"source": str(path.resolve()), "target_size_m": list(TOAST_SIZE),
                      "scale": scale, "source_world_bounds_m": [list(lo), list(hi)]}


def create_spoon(steel):
    from spoon_reservoir_geometry import bowl_mesh, SPOON_CENTER, INITIAL_TILT
    vertices, triangles = bowl_mesh()
    mesh = bpy.data.meshes.new("PCVE_SharedSpoonMesh")
    mesh.from_pydata(vertices.tolist(), [], triangles.tolist())
    mesh.update()
    bowl = bpy.data.objects.new("PCVE_SpoonBowl", mesh)
    bpy.context.collection.objects.link(bowl)
    bowl.data.materials.append(steel)
    for poly in bowl.data.polygons:
        poly.use_smooth = True
    rig = bpy.data.objects.new("PCVE_SpoonRig", None)
    bpy.context.collection.objects.link(rig)
    rig.location = SPOON_CENTER
    rig.rotation_euler[1] = math.radians(INITIAL_TILT)
    bowl.parent = rig
    handle = cube("PCVE_SpoonHandle", (-0.098,0,0.001),
                  (0.122,0.014,0.0032), steel, 0.005)
    handle.parent = rig
    return bowl, handle

args = parse_args()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1280, 720, 100
scene.render.image_settings.file_format = "PNG"
scene.render.fps = 24
scene.view_settings.look = "AgX - Medium High Contrast"

wood = noisy_material("PCVE_Walnut", (0.24, 0.085, 0.030), (0.055, 0.014, 0.006), 5.5, 0.32, 0.18)
ceramic = material("PCVE_WarmCeramic", (0.86, 0.82, 0.72), 0.24)
crust = noisy_material("PCVE_ToastCrust", (0.44, 0.13, 0.026), (0.10, 0.018, 0.004), 24, 0.62, 0.32)
crumb = noisy_material("PCVE_ToastCrumb", (0.76, 0.50, 0.20), (0.30, 0.095, 0.022), 70, 0.78, 0.46)
steel = material("PCVE_BrushedSteel", (0.34, 0.36, 0.38), 0.16, 0.92)
honey_mat = material("PCVE_Honey", (0.22, 0.028, 0.0012), 0.10)
hbsdf = honey_mat.node_tree.nodes.get("Principled BSDF")
hbsdf.inputs["Transmission Weight"].default_value = 0.36
hbsdf.inputs["IOR"].default_value = 1.49
hbsdf.inputs["Coat Weight"].default_value = 0.32
hbsdf.inputs["Coat Roughness"].default_value = 0.06
absorption = honey_mat.node_tree.nodes.new("ShaderNodeVolumeAbsorption")
absorption.inputs["Color"].default_value = (0.95, 0.22, 0.006, 1.0)
# Blender volume density is inverse-world-unit: centimetre-scale liquid needs
# tens of m^-1 before absorption is visible through an 8--12 mm strand.
absorption.inputs["Density"].default_value = 42.0
honey_mat.node_tree.links.new(
    absorption.outputs["Volume"],
    honey_mat.node_tree.nodes.get("Material Output").inputs["Volume"],
)
hbsdf.inputs["Base Color"].default_value = (0.34,0.13,0.008,1)
hbsdf.inputs["Transmission Weight"].default_value = 0.78
hbsdf.inputs["Roughness"].default_value = 0.075
absorption.inputs["Color"].default_value = (0.95,0.48,0.025,1)
absorption.inputs["Density"].default_value = 65.0

cube("PCVE_Table", (0.03, 0.0, 0.715), (1.10, 0.72, 0.07), wood, 0.012)
bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=0.118, depth=0.008, location=(0.07, 0.0, 0.758))
plate = bpy.context.object
plate.name = "PCVE_Plate"
plate.data.materials.append(ceramic)
bev = plate.modifiers.new("PlateRoundedEdge", "BEVEL")
bev.width, bev.segments = 0.004, 5

asset_record = {"source": "procedural", "license": "project-authored"}
if args.toast_asset:
    _, asset_record = import_toast(args.toast_asset)
else:
    toast_outline = [(-0.055, -0.050), (0.055, -0.050), (0.064, -0.036),
                     (0.062, 0.020), (0.050, 0.044), (0.027, 0.053),
                     (0.0, 0.048), (-0.027, 0.053), (-0.050, 0.044),
                     (-0.062, 0.020), (-0.064, -0.036)]
    prism("PCVE_ToastCrust", TOAST_CENTER, toast_outline, TOAST_SIZE[2], crust, 0.006)
    crumb_outline = [(x * 0.84, y * 0.82) for x, y in toast_outline]
    prism("PCVE_ToastCrumbTop",
          (TOAST_CENTER[0], TOAST_CENTER[1], TOAST_CENTER[2] + 0.0112),
          crumb_outline, 0.0032, crumb, 0.0035)

create_spoon(steel)

mesh = bpy.data.meshes.new("PCVE_HoneyMesh")
honey = bpy.data.objects.new("PCVE_Honey", mesh)
bpy.context.collection.objects.link(honey)
honey.data.materials.append(honey_mat)

# Background geometry keeps parallax and shadows coherent; it is intentionally sparse.
wall = cube("PCVE_BackWall", (0.10, 0.46, 1.22), (1.6, 0.05, 1.0),
            material("PCVE_BackWallMat", (0.38, 0.34, 0.28), 0.78), 0.01)
cube("PCVE_Napkin", (-0.16, 0.12, 0.758), (0.20, 0.12, 0.005),
     material("PCVE_Linen", (0.30, 0.38, 0.37), 0.88), 0.008).rotation_euler[2] = math.radians(-12)

bpy.ops.object.camera_add(location=(0.46, -0.72, 1.16))
camera = bpy.context.object
camera.name = "PCVE_Camera"
camera.data.lens = 58
camera.data.sensor_width = 36
target = Vector((0.065,0.0,0.855))
camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.dof.use_dof = True
focus = bpy.data.objects.new("PCVE_Focus", None)
bpy.context.collection.objects.link(focus)
focus.location = target
camera.data.dof.focus_object = focus
camera.data.dof.aperture_fstop = 11.0
scene.camera = camera

bpy.ops.object.light_add(type="AREA", location=(-0.28, -0.24, 1.42))
key = bpy.context.object
key.name = "PCVE_WindowKey"
key.data.energy, key.data.shape, key.data.size = 72.0, "DISK", 0.65
key.data.color = (1.0, 0.82, 0.62)
key.rotation_euler = (Vector((0.03, 0.0, 0.82)) - key.location).to_track_quat("-Z", "Y").to_euler()
bpy.ops.object.light_add(type="AREA", location=(0.32, 0.18, 1.15))
fill = bpy.context.object
fill.name = "PCVE_SoftFill"
fill.data.energy, fill.data.size, fill.data.color = 28.0, 0.45, (0.58, 0.72, 1.0)
fill.rotation_euler = (target - fill.location).to_track_quat("-Z", "Y").to_euler()
if scene.world is None:
    scene.world = bpy.data.worlds.new("PCVE_World")
scene.world.use_nodes = True
world_bg = scene.world.node_tree.nodes.get("Background")
world_bg.inputs["Color"].default_value = (0.025, 0.025, 0.025, 1.0)
world_bg.inputs["Strength"].default_value = 0.08
scene.view_settings.exposure = -0.5

scene.render.filepath = str(args.out.with_suffix(".png").resolve())
scene.render.film_transparent = False
scene.render.image_settings.file_format = "PNG"
args.out.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(args.out.resolve()))
(args.out.parent / "asset_manifest.json").write_text(json.dumps({"toast": asset_record}, indent=2) + "\n")
bpy.context.scene.render.filepath = str(args.out.with_name("static_preview.png").resolve())
bpy.ops.render.render(write_still=True)
print("PCVE_HONEY_SCENE", args.out.resolve())
