"""Render the tilted-cup pour: the water meshes and wet-oak maps of surface_tilted_cup_table_pour.py in the refined
kitchen (appearance_kitchen.py, ceramic_wood_details.py) under the sunlit look (look_tilted_cup_table_pour.py)."""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'render')
# PCVE_UNIFIED_ENTRY_END

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))

import bpy
import numpy as np
from mathutils import Matrix, Vector

CUP_CENTER = Vector((0.0, 0.0, 0.0425))
CUP_TILT_DEG = 58.0
TARGET_CUP_HEIGHT = 0.055
SUPPORT_CENTER = (-0.025, 0.0, 0.0140)
SUPPORT_HALF_EXTENTS = (0.0175, 0.0225, 0.0140)


def args_parse():
    av = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--hdri", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--frames", help="comma/range preview; default full sequence")
    p.add_argument("--mesh-dir-name", default="meshes")
    p.add_argument("--resolution", nargs=2, type=int, default=(1280, 720))
    p.add_argument("--output-fps", type=int, default=24)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--engine", choices=("cycles", "eevee"), default="cycles")
    p.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    p.add_argument("--camera-lens", type=float, default=58.0)
    p.add_argument("--camera-target", nargs=3, type=float, default=(0.045, 0.035, 0.055))
    p.add_argument("--resume", action="store_true")
    p.add_argument("--geometric-normals", action="store_true",
                   help="Diagnostic: derive normals from triangles instead of using the reconstructed normals")
    p.add_argument("--real-time", action="store_true",
                   help="Require one physical sampling interval per video frame")
    p.add_argument("--appearance-preset", choices=("base_scene", "refined_kitchen"), default="refined_kitchen")
    p.add_argument("--appearance-assets", type=Path)
    p.add_argument("--look", choices=["sunlit", "plain"], default="sunlit")
    p.add_argument("--sun-strength", type=float, default=40.0)
    p.add_argument("--bounce-energy", type=float, default=0.0)
    p.add_argument("--window-scale", type=float, default=0.6)
    p.add_argument("--exposure", type=float, default=-1.15)
    p.add_argument("--sun-elevation", type=float, default=32.0)
    p.add_argument("--sun-azimuth", type=float, default=-20.0)
    p.add_argument("--fstop", type=float, default=8.0)
    return p.parse_args(av)


def parse_frames(text, maximum):
    if not text:
        return list(range(1, maximum + 1))
    frames = sorted({i for part in text.split(",") for i in range(
        int(part.split("-")[0]), int(part.split("-")[-1]) + 1)})
    if not frames or frames[0] < 1 or frames[-1] > maximum:
        raise ValueError(f"frames must be inside 1-{maximum}")
    return frames


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def principled(name, base, roughness=0.4, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def bevel(obj, width, segments=3):
    mod = obj.modifiers.new("Small real edge radius", "BEVEL")
    mod.width = width
    mod.segments = segments


def add_box(name, loc, scale, material, bevel_width=0.0):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel_width:
        bevel(obj, bevel_width)
    obj.data.materials.append(material)
    return obj


def add_cylinder(name, loc, radius, depth, material, bevel_width=0.0):
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    if bevel_width:
        bevel(obj, bevel_width, 3)
    return obj


def textured_linen(name, base):
    mat = principled(name, base, 0.78)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    tex = nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 180.0
    tex.inputs["Detail"].default_value = 2.0
    tex.inputs["Roughness"].default_value = 0.72
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.18
    bump.inputs["Distance"].default_value = 0.00035
    links.new(tex.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def add_kitchen_dressing():
    """Sparse, real-scale kitchen context kept clear of the spill corridor."""
    grout = principled("Backsplash grout", (0.22, 0.23, 0.22), 0.82)
    for index, x in enumerate((-0.40, -0.18, 0.04, 0.26, 0.48, 0.70)):
        add_box(f"VerticalGrout{index+1}", (x, 0.3015, 0.115),
                (0.0014, 0.0012, 0.114), grout, 0.0005)
    for index, z in enumerate((0.058, 0.116, 0.174)):
        add_box(f"HorizontalGrout{index+1}", (0.16, 0.3013, z),
                (0.66, 0.0012, 0.0014), grout, 0.0005)

    shelf_wood = principled("Shelf warm oak", (0.16, 0.055, 0.018), 0.46)
    add_box("BackShelf", (0.08, 0.274, 0.245), (0.35, 0.032, 0.012), shelf_wood, 0.004)

    stoneware = principled("Kitchen stoneware", (0.36, 0.31, 0.25), 0.34)
    lid_mat = principled("Brushed brass lids", (0.20, 0.115, 0.035), 0.27, 0.72)
    for index, (x, radius, height) in enumerate(((-0.20, 0.035, 0.090),
                                                 (-0.105, 0.030, 0.075))):
        add_cylinder(f"StonewareCanister{index+1}", (x, 0.272, height / 2.0),
                     radius, height, stoneware, 0.004)
        add_cylinder(f"CanisterLid{index+1}", (x, 0.272, height + 0.004),
                     radius * 1.035, 0.008, lid_mat, 0.0015)

    pot_mat = principled("Terracotta herb pot", (0.24, 0.055, 0.018), 0.62)
    soil_mat = principled("Dark potting soil", (0.018, 0.009, 0.004), 0.90)
    leaf_mat = principled("Herb leaves", (0.025, 0.16, 0.035), 0.52)
    add_cylinder("HerbPot", (-0.305, 0.255, 0.046), 0.043, 0.082, pot_mat, 0.003)
    add_cylinder("HerbSoil", (-0.305, 0.255, 0.089), 0.038, 0.004, soil_mat)
    for index, (dx, dy, height, lean) in enumerate((
            (-0.018, -0.006, 0.064, -13), (0.002, 0.004, 0.078, 7),
            (0.020, -0.002, 0.060, 16), (-0.008, 0.012, 0.072, -4),
            (0.013, 0.014, 0.058, 11))):
        stem = add_cylinder(f"HerbStem{index+1}", (-0.305 + dx, 0.255 + dy, 0.088 + height / 2),
                            0.0015, height, leaf_mat)
        stem.rotation_euler[1] = math.radians(lean)
        for leaf_index, zoff in enumerate((0.020, 0.043, 0.060)):
            if zoff >= height:
                continue
            bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12,
                                                location=(-0.305 + dx + (0.012 if leaf_index % 2 else -0.010),
                                                          0.255 + dy, 0.088 + zoff))
            leaf = bpy.context.object
            leaf.name = f"HerbLeaf{index+1}_{leaf_index+1}"
            leaf.scale = (0.022, 0.008, 0.010)
            leaf.rotation_euler[1] = math.radians(20 if leaf_index % 2 else -20)
            leaf.data.materials.append(leaf_mat)

    steel = principled("Brushed stainless spoon", (0.34, 0.36, 0.37), 0.24, 0.82)
    spoon_handle = add_box("SpoonHandle", (-0.15, -0.105, 0.006),
                           (0.055, 0.004, 0.0015), steel, 0.003)
    spoon_handle.rotation_euler[2] = math.radians(12.0)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24,
                                        location=(-0.205, -0.117, 0.008))
    spoon_bowl = bpy.context.object
    spoon_bowl.name = "SpoonBowl"
    spoon_bowl.scale = (0.022, 0.013, 0.003)
    spoon_bowl.rotation_euler[2] = math.radians(12.0)
    spoon_bowl.data.materials.append(steel)


def create_cup_visual():
    """Create a smooth ceramic shell from the exact collision-proxy ledger."""
    outer_bottom, outer_top = 0.0370, 0.0370
    inner_bottom, inner_top = 0.0315, 0.0315
    z0, z1 = -0.0275, 0.0275
    zi = z0 + 0.006
    profile = [
        (0.0, z0), (outer_bottom, z0), (outer_bottom, z0 + 0.004),
        (outer_top, z1 - 0.002), (outer_top, z1),
        (inner_top, z1), (inner_top, z1 - 0.002),
        (inner_bottom, zi + 0.002), (inner_bottom, zi), (0.0, zi),
    ]
    segments, vertices, rings = 128, [], []
    for radius, z in profile:
        if radius == 0:
            rings.append([len(vertices)])
            vertices.append((0.0, 0.0, z))
        else:
            ring = []
            for i in range(segments):
                a = 2 * math.pi * i / segments
                ring.append(len(vertices))
                vertices.append((radius * math.cos(a), radius * math.sin(a), z))
            rings.append(ring)
    faces = []
    for lower, upper in zip(rings, rings[1:]):
        if len(lower) == 1:
            faces.extend((lower[0], upper[(i + 1) % segments], upper[i]) for i in range(segments))
        elif len(upper) == 1:
            faces.extend((lower[i], lower[(i + 1) % segments], upper[0]) for i in range(segments))
        else:
            faces.extend((lower[i], lower[(i + 1) % segments], upper[(i + 1) % segments], upper[i])
                         for i in range(segments))
    mesh = bpy.data.meshes.new("MeasuredCeramicCupMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    mug = bpy.data.objects.new("MeasuredCeramicCup", mesh)
    bpy.context.scene.collection.objects.link(mug)
    ceramic = principled("Ivory glazed ceramic", (0.72, 0.58, 0.43), 0.18)
    bsdf = ceramic.node_tree.nodes.get("Principled BSDF")
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.25
        bsdf.inputs["Coat Roughness"].default_value = 0.08
    mug.data.materials.append(ceramic)
    for poly in mug.data.polygons:
        poly.use_smooth = True
    cup_matrix = Matrix.Translation(CUP_CENTER) @ Matrix.Rotation(math.radians(CUP_TILT_DEG), 4, "Y")
    mug.matrix_world = cup_matrix

    bpy.ops.mesh.primitive_torus_add(major_segments=64, minor_segments=16,
                                    major_radius=0.019, minor_radius=0.0038)
    handle = bpy.context.object
    handle.name = "CeramicCupHandle"
    handle.data.materials.append(ceramic)
    handle.matrix_world = (cup_matrix @ Matrix.Translation(Vector((0.0, -0.035, -0.001))) @
                           Matrix.Rotation(math.radians(90.0), 4, "Y"))
    return mug


def setup_world(hdri):
    world = bpy.data.worlds.new("Warm kitchen world")
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputWorld")
    bg = nodes.new("ShaderNodeBackground")
    env = nodes.new("ShaderNodeTexEnvironment")
    mapping = nodes.new("ShaderNodeMapping")
    tex = nodes.new("ShaderNodeTexCoord")
    env.image = bpy.data.images.load(str(hdri))
    mapping.inputs["Rotation"].default_value[2] = math.radians(118.0)
    bg.inputs["Strength"].default_value = 0.16
    links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    links.new(env.outputs["Color"], bg.inputs["Color"])
    links.new(bg.outputs["Background"], out.inputs["Surface"])
    bpy.context.scene.world = world


def setup_scene(hdri):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    setup_world(hdri)

    wood = principled("Oiled walnut", (0.09, 0.022, 0.007), 0.38)
    wood.use_nodes = True
    bsdf = wood.node_tree.nodes.get("Principled BSDF")
    noise = wood.node_tree.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 5.0
    noise.inputs["Detail"].default_value = 3.2
    noise.inputs["Roughness"].default_value = 0.68
    mapping = wood.node_tree.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (0.9, 14.0, 3.0)
    tex = wood.node_tree.nodes.new("ShaderNodeTexCoord")
    ramp = wood.node_tree.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.018, 0.004, 0.0015, 1.0)
    ramp.color_ramp.elements[1].color = (0.22, 0.055, 0.012, 1.0)
    wood.node_tree.links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
    wood.node_tree.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    wood.node_tree.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    wood.node_tree.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    add_box("RealScaleWoodTable", (0.0, 0.0, -0.035), (0.61, 0.43, 0.035), wood, 0.006)

    wall = principled("Warm plaster", (0.36, 0.32, 0.27), 0.72)
    add_box("BackWall", (0.20, 0.34, 0.35), (0.78, 0.025, 0.35), wall, 0.008)
    tile = principled("Muted stone backsplash", (0.26, 0.30, 0.29), 0.38)
    tile_nodes, tile_links = tile.node_tree.nodes, tile.node_tree.links
    tile_bsdf = tile_nodes.get("Principled BSDF")
    tile_tex = tile_nodes.new("ShaderNodeTexNoise")
    tile_tex.inputs["Scale"].default_value = 38.0
    tile_tex.inputs["Detail"].default_value = 3.0
    tile_bump = tile_nodes.new("ShaderNodeBump")
    tile_bump.inputs["Strength"].default_value = 0.12
    tile_bump.inputs["Distance"].default_value = 0.001
    tile_links.new(tile_tex.outputs["Fac"], tile_bump.inputs["Height"])
    tile_links.new(tile_bump.outputs["Normal"], tile_bsdf.inputs["Normal"])
    add_box("Backsplash", (0.16, 0.311, 0.115), (0.66, 0.008, 0.115), tile, 0.002)

    add_kitchen_dressing()

    mug = create_cup_visual()
    mug.rotation_mode = "XYZ"
    support_mat = principled("Dark walnut support block", (0.045, 0.010, 0.003), 0.52)
    support=add_box("SquareCupSupport", SUPPORT_CENTER, SUPPORT_HALF_EXTENTS,
                    support_mat, 0.002)
    # Keep the actual contact edge sharp; beveling it away would create a gap
    # between the visual wood and the matching box collider's support edge.
    weights=support.data.attributes.new('bevel_weight_edge','FLOAT','EDGE')
    for edge in support.data.edges:
        vertices=[support.data.vertices[i].co for i in edge.vertices]
        contact=all(abs(v.x-SUPPORT_HALF_EXTENTS[0])<1e-7 and
                    abs(v.z-SUPPORT_HALF_EXTENTS[2])<1e-7 for v in vertices)
        weights.data[edge.index].value=0. if contact else 1.
    support.modifiers['Small real edge radius'].limit_method='WEIGHT'

    water_mat = bpy.data.materials.new("Physically based clear water")
    water_mat.use_nodes = True
    nodes, links = water_mat.node_tree.nodes, water_mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    water_bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    water_bsdf.inputs["Base Color"].default_value = (0.91, 0.97, 1.0, 1.0)
    water_bsdf.inputs["Roughness"].default_value = 0.040
    water_bsdf.inputs["IOR"].default_value = 1.333
    if "Transmission Weight" in water_bsdf.inputs:
        water_bsdf.inputs["Transmission Weight"].default_value = 1.0
    elif "Transmission" in water_bsdf.inputs:
        water_bsdf.inputs["Transmission"].default_value = 1.0
    absorption = nodes.new("ShaderNodeVolumeAbsorption")
    absorption.inputs["Color"].default_value = (0.58, 0.88, 0.96, 1.0)
    absorption.inputs["Density"].default_value = 0.10
    links.new(water_bsdf.outputs["BSDF"], out.inputs["Surface"])
    links.new(absorption.outputs["Volume"], out.inputs["Volume"])
    mesh = bpy.data.meshes.new("GenesisWaterMesh")
    water = bpy.data.objects.new("GenesisWater", mesh)
    scene.collection.objects.link(water)
    water.data.materials.append(water_mat)

    bpy.ops.object.light_add(type="AREA", location=(-0.28, -0.24, 0.62))
    key = bpy.context.object
    key.name = "LargeWindowKey"
    key.data.energy = 82
    key.data.shape = "DISK"
    key.data.size = 0.48
    key.data.color = (1.0, 0.92, 0.82)
    look_at(key, (0.04, 0.0, 0.02))
    bpy.ops.object.light_add(type="AREA", location=(0.42, 0.22, 0.35))
    fill = bpy.context.object
    fill.name = "CoolSoftFill"
    fill.data.energy = 42
    fill.data.size = 0.30
    fill.data.color = (0.67, 0.79, 1.0)
    look_at(fill, (0.08, 0.0, 0.04))

    bpy.ops.object.light_add(type="AREA", location=(0.08, 0.30, 0.42))
    rim = bpy.context.object
    rim.name = "WaterReflectionRim"
    rim.data.energy = 34
    rim.data.shape = "RECTANGLE"
    rim.data.size = 0.28
    rim.data.size_y = 0.10
    rim.data.color = (0.78, 0.90, 1.0)
    look_at(rim, (0.08, 0.0, 0.025))

    bpy.ops.object.camera_add(location=(0.34, -0.47, 0.25))
    camera = bpy.context.object
    camera.name = "Camera"
    camera.data.lens = args.camera_lens
    camera.data.sensor_width = 36
    look_at(camera, args.camera_target)
    camera.data.dof.use_dof = True
    camera.data.dof.focus_object = mug
    camera.data.dof.aperture_fstop = 7.1
    scene.camera = camera
    return scene, water


def replace_mesh(obj, vertices, triangles, normals=None, velocity=None):
    old = obj.data
    mats = [m for m in old.materials if m]
    mesh = bpy.data.meshes.new(f"GenesisWaterMesh_{bpy.context.scene.frame_current:04d}")
    mesh.from_pydata(vertices.tolist(), [], triangles.tolist())
    mesh.update()
    for mat in mats:
        mesh.materials.append(mat)
    if velocity is not None:                     # Cycles motion blur for changing topology
        attr = mesh.attributes.new("velocity", "FLOAT_VECTOR", "POINT")
        attr.data.foreach_set("vector", velocity.astype(np.float32).ravel())
    for poly in mesh.polygons:
        poly.use_smooth = True
    if normals is not None:
        if normals.shape != vertices.shape or not np.isfinite(normals).all():
            raise RuntimeError("Invalid reconstructed vertex normals")
        mesh.normals_split_custom_set_from_vertices(normals.tolist())
    obj.data = mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


args = args_parse()
run, out = args.run.resolve(), args.out.resolve()
out.mkdir(parents=True, exist_ok=True)
report = json.loads((run / "simulation_report.json").read_text())
cup_present = bool(report['physics'].get('cup_present', True))
water_present = bool(report['physics'].get('water_present', True))
CUP_CENTER=Vector(report['physics']['cup_pose']['center_m'])
SUPPORT_CENTER=tuple(report['geometry']['square_support_center_m'])
frame_count = int(report["frames_simulated"])
frames = parse_frames(args.frames, frame_count)
if args.real_time:
    if not math.isclose(float(report["numerics"]["simulation_fps"]), args.output_fps):
        raise RuntimeError("Real-time output requires simulation_fps == output_fps")
    times = [row.get("physical_time_sec") for row in report.get("trajectory", [])]
    if times and all(value is not None for value in times):
        if not all(math.isclose(b - a, 1.0 / args.output_fps, abs_tol=1e-8)
                   for a, b in zip(times[:-1], times[1:])):
            raise RuntimeError("Particle snapshots do not follow the real-time frame intervals")
scene, water = setup_scene(args.hdri.resolve())
appearance_ledger={"name":"base_scene"}
if args.appearance_preset == "refined_kitchen":
    if args.appearance_assets is None:
        raise ValueError("--appearance-assets is required for refined_kitchen")
    from appearance_kitchen import apply
    appearance_ledger=apply(scene,args.appearance_assets)
support=bpy.data.objects['SquareCupSupport']
evaluated=support.evaluated_get(bpy.context.evaluated_depsgraph_get())
normal=Vector((math.sin(math.radians(CUP_TILT_DEG)),0,math.cos(math.radians(CUP_TILT_DEG))))
plane=[normal.dot(evaluated.matrix_world@v.co-CUP_CENTER)+.0275 for v in evaluated.data.vertices]
cup_vertices=[bpy.data.objects['MeasuredCeramicCup'].matrix_world@v.co
              for v in bpy.data.objects['MeasuredCeramicCup'].data.vertices]
cup_evaluated=bpy.data.objects['MeasuredCeramicCup'].evaluated_get(bpy.context.evaluated_depsgraph_get())
cup_evaluated_min_z=min((cup_evaluated.matrix_world@v.co).z for v in cup_evaluated.data.vertices)
contact_audit={'support_signed_plane_max_m':max(plane),
               'cup_minimum_world_z_m':min(p.z for p in cup_vertices),
               'cup_evaluated_minimum_world_z_m':cup_evaluated_min_z,
               'support_center_from_simulation':list(SUPPORT_CENTER),
               'contact_edge_sharp_matches_collision':True}
assert abs(contact_audit['support_signed_plane_max_m'])<1e-6,contact_audit
assert abs(contact_audit['cup_minimum_world_z_m'])<1e-6,contact_audit
assert abs(cup_evaluated_min_z)<1e-6,contact_audit
if not cup_present:
    # Preserve the exact original optical focus while removing all renderable
    # cup geometry. There is no hidden cup mesh or water-shape substitution.
    mug = bpy.data.objects['MeasuredCeramicCup']
    focus = bpy.data.objects.new('CameraFocusAtOriginalCup', None)
    scene.collection.objects.link(focus)
    focus.matrix_world = mug.matrix_world.copy()
    scene.camera.data.dof.focus_object = focus
    removed = []
    for obj in list(bpy.data.objects):
        if obj.name in ('MeasuredCeramicCup', 'CeramicCupHandle') or obj.name.startswith('Glazed handle attachment'):
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    assert not bpy.data.objects.get('MeasuredCeramicCup')
    contact_audit = {'cup_present': False, 'cup_contact_check': 'not applicable: cup removed',
                     'support_minimum_world_z_m': min((evaluated.matrix_world@v.co).z for v in evaluated.data.vertices),
                     'removed_visual_objects': removed, 'focus_point_preserved_m': list(CUP_CENTER)}
    assert abs(contact_audit['support_minimum_world_z_m']) < 1e-6
appearance_ledger['cup_present'] = cup_present
appearance_ledger['water_present'] = water_present
if not water_present:
    bpy.data.objects.remove(water, do_unlink=True)
    water = None
    assert not bpy.data.objects.get('GenesisWater')
(out/'contact_audit.json').write_text(json.dumps(contact_audit,indent=2)+'\n')

scene.render.resolution_x, scene.render.resolution_y = args.resolution
scene.render.resolution_percentage = 100
scene.render.fps = args.output_fps
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.film_transparent = False
scene.render.use_motion_blur = False
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = -0.95
if args.appearance_preset == "refined_kitchen":
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.0
if args.look == "sunlit":
    from look_tilted_cup_table_pour import apply as apply_look
    appearance_ledger["look"], look_update = apply_look(scene, args, run)
if args.engine == "cycles":
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.device = "GPU" if args.device == "gpu" else "CPU"
    scene.cycles.max_bounces = 10
    scene.cycles.transmission_bounces = 8
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for backend in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = backend
                prefs.get_devices()
                break
            except Exception:
                pass
        for dev in prefs.devices:
            dev.use = (args.device == "gpu" and dev.type == prefs.compute_device_type)
    except Exception as exc:
        print("GPU_SETUP_WARNING", exc)
else:
    scene.render.engine = "BLENDER_EEVEE_NEXT"

frames_dir = out / "frames"
frames_dir.mkdir(exist_ok=True)
render_settings = {
    "run": str(run), "mesh_dir_name": args.mesh_dir_name,
    "resolution": list(args.resolution), "output_fps": args.output_fps,
    "engine": args.engine, "device": args.device, "samples": args.samples,
    "camera_lens_mm": args.camera_lens, "camera_target_m": list(args.camera_target),
    "hdri": str(args.hdri.resolve()),
    "real_time_required": args.real_time,
    "appearance": appearance_ledger,
    "contact_audit":contact_audit,
    "normal_source": "triangle geometry" if args.geometric_normals else "standard reconstruction vertex normals",
    "shape_policy": "pysplashsurf isosurface of the particles; tabletop water as a volume-conserving film (surface_tilted_cup_table_pour.py)" if water_present else "Whole liquid absent from physical construction and rendering from t=0",
}
settings_path = out / "render_settings.json"
if args.resume and settings_path.exists():
    if json.loads(settings_path.read_text()) != render_settings:
        raise RuntimeError("Cannot reuse frames rendered with different settings")
elif args.resume and any(frames_dir.glob("frame_*.png")):
    raise RuntimeError("Existing frames have no render-settings record")
settings_path.write_text(json.dumps(render_settings, indent=2) + "\n")
rows, started = [], time.monotonic()
for frame in frames:
    scene.frame_set(frame)
    with np.load(run / args.mesh_dir_name / f"water_{frame:04d}.npz") as data:
        vertices = data["vertices"].astype(float)
        triangles = data["triangles"].astype(int)
        normals = None if args.geometric_normals else data["normals"].astype(float)
        velocity = data["velocity"] if args.look == "sunlit" and "velocity" in data else None
    if args.look == "sunlit":
        look_update(frame)
    if water_present:
        replace_mesh(water, vertices, triangles, normals, velocity)
    elif len(vertices) or len(triangles):
        raise RuntimeError('Deleted liquid still contributes visible geometry')
    target = frames_dir / f"frame_{frame:04d}.png"
    if args.resume and target.exists():
        rows.append({"frame": frame, "seconds": 0.0, "reused_existing_frame": True,
                     "vertices": int(len(vertices)), "triangles": int(len(triangles))})
        continue
    scene.render.filepath = str(target)
    tick = time.monotonic()
    bpy.ops.render.render(write_still=True)
    rows.append({"frame": frame, "seconds": time.monotonic() - tick,
                 "vertices": int(len(vertices)), "triangles": int(len(triangles))})
    print("RENDER", frame, flush=True)

bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(out / "scene_genesis.blend"))
manifest = {
    "scene_id": "tilted_cup_table_pour",
    "solver": report["solver"], "coupling": report["coupling"],
    "simulation_report": str((run / "simulation_report.json").resolve()),
    "assets": [{"name": "Qwantani Patio HDRI", "provider": "Poly Haven",
                "path": str(args.hdri.resolve()), "license": "CC0"},
               {"name": "Procedural kitchen dressing", "provider": "scene generator",
                "path": str(Path(__file__).resolve()), "license": "project source"}],
    "water_source": "surface reconstructed only from Genesis DFSPH particles" if water_present else "No liquid: removed before physical construction at t=0",
    "render_settings": render_settings,
    "timing": {
        "simulation_fps": report["numerics"]["simulation_fps"],
        "output_fps": args.output_fps,
        "presentation_time_scale": args.output_fps / report["numerics"]["simulation_fps"],
        "physical_duration_sec": report["numerics"]["physical_duration_sec"],
        "video_duration_sec": frame_count / args.output_fps,
        "real_time_required": args.real_time,
    },
    "support": {
        "shape": "beveled square block",
        "center_m": list(SUPPORT_CENTER),
        "size_m": [2.0 * value for value in SUPPORT_HALF_EXTENTS],
        "has_matching_genesis_collision": True,
    },
    "render": {"resolution": list(args.resolution), "samples": args.samples,
               "engine": args.engine, "device": args.device, "frames": frames},
    "render_seconds": time.monotonic() - started, "per_frame": rows,
}
(out / "render_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

if args.frames:
    raise SystemExit(0)
video = out / "video.mp4"
encode_started = time.monotonic()
subprocess.run(["ffmpeg", "-y", "-v", "warning", "-framerate", str(args.output_fps), "-start_number", "1",
                "-i", str(frames_dir / "frame_%04d.png"), "-frames:v", str(frame_count),
                "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(video)], check=True)
manifest["encode_seconds"] = time.monotonic() - encode_started
(out / "render_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
probe = json.loads(subprocess.check_output([
    "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
    "-show_entries", "stream=width,height,r_frame_rate,avg_frame_rate,nb_read_frames:format=duration,size",
    "-of", "json", str(video)], text=True))
subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], check=True)
probe["sha256"] = sha256(video)
(out / "video_verification.json").write_text(json.dumps(probe, indent=2) + "\n")
print("VIDEO", video)

