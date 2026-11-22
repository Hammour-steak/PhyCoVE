"""Render Genesis car poses and DFSPH meshes in the accepted sunny scene."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector


def parse_args():
    av = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--input-blend", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--preview-frames", nargs="*", type=int)
    p.add_argument("--resolution", nargs=2, type=int, default=(1280, 720))
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--engine", choices=("cycles", "eevee"), default="cycles")
    p.add_argument("--reuse-existing-frames", action="store_true")
    p.add_argument("--mesh-dir-name", default="meshes")
    p.add_argument("--camera-preset", choices=("wide", "action", "natural"), default="wide")
    p.add_argument("--render-spray-particles", action="store_true")
    p.add_argument("--spray-radius", type=float, default=0.0042)
    p.add_argument("--spray-speed-threshold", type=float, default=0.30)
    p.add_argument("--secondary-dir-name",
                   help="Duck-style water/spray/mist/foam directory inside the Genesis run")
    p.add_argument("--lighting-preset", choices=("source", "natural-courtyard", "garden-sky"),
                   default="source")
    p.add_argument("--background-yaw-degrees", type=float, default=0.0,
                   help="Rotate the Summer Garden around the final camera to choose a different view")
    p.add_argument("--hdri-yaw-degrees", type=float, default=0.0,
                   help="Additional Z rotation for the accepted courtyard environment map")
    p.add_argument("--environment-hdri", type=Path,
                   help="Replace the source environment image without changing scene physics")
    p.add_argument("--clip-water-to-pool-liner", action="store_true",
                   help="Hide low reconstructed water outside the authored pool-water footprint")
    p.add_argument("--pool-clip-margin", type=float, default=0.012,
                   help="Inward XY margin, in metres, for the authored pool-water footprint")
    p.add_argument("--pool-clip-z", type=float, default=0.16,
                   help="Only clip reconstructed vertices below this world-space height")
    p.add_argument("--hide-genesis-fluid", action="store_true",
                   help="Diagnostic: hide the Genesis surface and all secondary liquid")
    p.add_argument("--disable-pool-shadow", action="store_true",
                   help="Diagnostic: disable shadow-ray visibility for the inflatable pool")
    p.add_argument("--remove-pool-valves", action="store_true",
                   help="Remove three detached valve shells whose intersections read as wall holes")
    p.add_argument("--contact-fill-energy", type=float, default=0.0,
                   help="Enable the accepted large sky fill at this energy to soften pool contact")
    p.add_argument("--sun-angle-degrees", type=float,
                   help="Optional apparent sun diameter used to soften hard contact shadows")
    p.add_argument("--sun-yaw-offset-degrees", type=float, default=0.0,
                   help="Rotate the accepted sun around world Z while preserving elevation")
    p.add_argument("--blue-pool-bottom", action="store_true")
    return p.parse_args(av)


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_state(run: Path, frame: int, mesh_dir_name: str):
    with np.load(run / "particles" / f"frame_{frame:04d}.npz") as src:
        car_pos = src["car_pos"].astype(float)
        car_quat = src["car_quat_wxyz"].astype(float)
        water_pos = src["water_pos"].astype(float)
        water_vel = src["water_vel"].astype(float)
    with np.load(run / mesh_dir_name / f"water_{frame:04d}.npz") as src:
        vertices = src["vertices"].astype(float)
        triangles = src["triangles"].astype(int)
    return car_pos, car_quat, water_pos, water_vel, vertices, triangles


def replace_water_geometry(obj, vertices, triangles):
    old = obj.data
    materials = [material for material in old.materials if material]
    mesh = bpy.data.meshes.new(f"PCVE_GenesisWaterMesh_{bpy.context.scene.frame_current:04d}")
    mesh.from_pydata(vertices.tolist(), [], triangles.tolist())
    mesh.update()
    for material in materials:
        mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    obj.data = mesh
    if old and old.users == 0:
        bpy.data.meshes.remove(old)


def convex_hull_2d(points):
    """Return a counter-clockwise convex hull for an Nx2 point array."""
    unique = sorted({(float(point[0]), float(point[1])) for point in points})
    if len(unique) < 3:
        raise RuntimeError("pool-water footprint has fewer than three unique XY points")

    def cross(origin, a, b):
        return ((a[0] - origin[0]) * (b[1] - origin[1]) -
                (a[1] - origin[1]) * (b[0] - origin[0]))

    lower = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return np.asarray(lower[:-1] + upper[:-1], dtype=float)


def inset_convex_polygon(polygon, margin):
    """Apply a small centroid-directed inset suitable for a hidden liner mask."""
    if margin <= 0.0:
        return polygon.copy()
    center = polygon.mean(axis=0)
    radial = polygon - center
    length = np.linalg.norm(radial, axis=1)
    scale = np.maximum(0.0, (length - margin) / np.maximum(length, 1.0e-9))
    return center + radial * scale[:, None]


def points_in_convex_polygon(points, polygon, tolerance=1.0e-7):
    edges = np.roll(polygon, -1, axis=0) - polygon
    relative = points[:, None, :] - polygon[None, :, :]
    cross = edges[None, :, 0] * relative[:, :, 1] - edges[None, :, 1] * relative[:, :, 0]
    return np.all(cross >= -tolerance, axis=1)


def clip_low_water_to_polygon(vertices, triangles, polygon, z_limit):
    """Remove low triangles that protrude outside the visible pool liner.

    High vertices are retained so solver-generated splashes can legitimately
    rise above or cross the inflatable rim.
    """
    inside = points_in_convex_polygon(vertices[:, :2], polygon)
    bad_vertex = (~inside) & (vertices[:, 2] < z_limit)
    keep = ~np.any(bad_vertex[triangles], axis=1)
    return vertices, triangles[keep], int(np.count_nonzero(~keep))


def replace_spray_geometry(obj, points, radius):
    """Render solver particles above the sheet as compact octahedral droplets."""
    old = obj.data
    materials = [material for material in old.materials if material]
    vertices = []
    triangles = []
    offsets = ((1, 0, 0), (-1, 0, 0), (0, 1, 0),
               (0, -1, 0), (0, 0, 1), (0, 0, -1))
    faces = ((0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4),
             (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5))
    radii = np.broadcast_to(np.asarray(radius, dtype=float), (len(points),))
    for point, particle_radius in zip(points, radii):
        base = len(vertices)
        vertices.extend(tuple(point + np.asarray(offset) * particle_radius) for offset in offsets)
        triangles.extend(tuple(base + i for i in face) for face in faces)
    mesh = bpy.data.meshes.new(f"PCVE_GenesisSprayMesh_{bpy.context.scene.frame_current:04d}")
    mesh.from_pydata(vertices, [], triangles)
    mesh.update()
    for material in materials:
        mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    obj.data = mesh
    if old and old.users == 0:
        bpy.data.meshes.remove(old)


def particle_material(name, base, transmission, roughness, alpha=1.0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Transmission Weight"].default_value = transmission
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["IOR"].default_value = 1.333
    bsdf.inputs["Alpha"].default_value = alpha
    return material


def secondary_object(name, material):
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name + "Mesh"))
    scene.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def load_secondary(run, directory, frame, kind):
    with np.load(run / directory / f"{kind}_{frame:04d}.npz") as data:
        return data["position"].astype(float), data["radius"].astype(float)


def apply_lighting_preset(scene, preset):
    if preset == "source":
        return {}
    if preset not in {"natural-courtyard", "garden-sky"}:
        raise ValueError(preset)
    camera = scene.camera
    camera.data.dof.use_dof = True
    camera.data.dof.aperture_fstop = 16.0
    world_background = next(
        (node for node in scene.world.node_tree.nodes if node.bl_idname == "ShaderNodeBackground"), None)
    if world_background is None:
        raise RuntimeError("courtyard lighting preset requires a world Background node")
    world_source = "Qwantani Patio HDRI"
    if preset == "garden-sky":
        world_nodes = scene.world.node_tree.nodes
        world_links = scene.world.node_tree.links
        world_nodes.clear()
        world_output = world_nodes.new("ShaderNodeOutputWorld")
        world_background = world_nodes.new("ShaderNodeBackground")
        sky = world_nodes.new("ShaderNodeTexSky")
        sky.sky_type = "NISHITA"
        sky.sun_disc = False
        sky.sun_elevation = np.radians(48.0)
        sky.sun_rotation = np.radians(132.0)
        sky.altitude = 0.12
        sky.air_density = 1.0
        sky.dust_density = 1.8
        sky.ozone_density = 1.0
        world_background.inputs["Strength"].default_value = 0.34
        world_links.new(sky.outputs["Color"], world_background.inputs["Color"])
        world_links.new(world_background.outputs["Background"], world_output.inputs["Surface"])
        world_source = "Nishita clear sky; brick patio panorama removed"
    else:
        world_background.inputs["Strength"].default_value = 0.52
    sun = bpy.data.objects.get("PCVE_RealismSun")
    if sun is None or sun.type != "LIGHT" or sun.data.type != "SUN":
        raise RuntimeError("accepted realism sun is missing")
    sun.hide_render = False
    sun.data.energy = 1.48
    sun.data.angle = np.radians(1.1)
    sun.data.color = (1.0, 0.945, 0.87)
    fill = bpy.data.objects.get("PCVE_SoftSkyFill")
    if fill is not None:
        fill.hide_render = True
    scene.view_settings.look = "AgX - Base Contrast"
    scene.view_settings.exposure = 0.08
    return {
        "intent": "sunny open garden with coherent direct light and unobstructed sky",
        "world_source": world_source,
        "world_strength": world_background.inputs["Strength"].default_value,
        "sun_energy": 1.48,
        "sun_angle_degrees": 1.1,
        "sun_color": list(sun.data.color),
        "artificial_area_fill_hidden": fill is not None,
        "camera_fstop": camera.data.dof.aperture_fstop,
        "view_look": scene.view_settings.look,
        "exposure": scene.view_settings.exposure,
    }


args = parse_args()
run = args.run.resolve()
out = args.out_dir.resolve()
out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(args.input_blend.resolve()))
scene = bpy.context.scene

if args.environment_hdri:
    environment = next(
        (node for node in scene.world.node_tree.nodes if node.bl_idname == "ShaderNodeTexEnvironment"),
        None,
    )
    if environment is None:
        raise RuntimeError("environment HDRI replacement requires a Texture Environment node")
    environment.image = bpy.data.images.load(str(args.environment_hdri.resolve()), check_existing=True)

# Preserve the accepted longer-lens composition while lifting the eye line
# enough to see the car after it clears the near inflatable rim.
camera = scene.camera
if args.camera_preset == "natural":
    camera.location = (2.58, -3.72, 1.64)
    camera.rotation_euler = (Vector((0.00, 0.0, 0.13)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = 61.0
elif args.camera_preset == "action":
    camera.location = (2.34, -3.35, 1.88)
    camera.rotation_euler = (Vector((0.00, 0.0, 0.12)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = 60.0
else:
    camera.location = (2.80, -4.20, 2.48)
    camera.rotation_euler = (Vector((0.02, 0.0, 0.09)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = 58.0

if args.background_yaw_degrees:
    garden_root = bpy.data.objects.get("PCVE_SummerGardenRoot")
    if garden_root is None:
        raise RuntimeError("Summer Garden root is missing")
    pivot = camera.location.copy()
    turn = Matrix.Rotation(np.radians(args.background_yaw_degrees), 4, "Z")
    garden_root.matrix_world = (
        Matrix.Translation(pivot) @ turn @ Matrix.Translation(-pivot) @ garden_root.matrix_world
    )
    bpy.context.view_layer.update()

report = json.loads((run / "simulation_report.json").read_text())
frame_count = int(report["numerics"]["frames"])
frames = args.preview_frames or list(range(1, frame_count + 1))

# Replace the Mantaflow result and its collision-only helpers; retain the
# accepted pool, track, garden, camera and sunny lighting unchanged.
for name in (
    "PCVE_ShallowWaterDomain", "PCVE_RenderOnlyWaterCore", "PCVE_ToyCarFluidHull",
    "PCVE_FluidBottom", "PCVE_FluidSideA", "PCVE_FluidSideB", "PCVE_FluidEnd", "PCVE_FluidStart",
):
    obj = bpy.data.objects.get(name)
    if obj:
        obj.hide_render = True

# The BlenderKit pool is a single mesh containing both the inflatable shell
# and an authored static water surface.  Delete only polygons assigned to its
# "Pool Water" slot, so every visible liquid surface comes from Genesis.
pool = bpy.data.objects.get("Childrens Inflatable Pool.001")
pool_clip_polygon = None
sealed_pool_accessory_openings = 0
removed_pool_valves = 0
if pool and pool.type == "MESH":
    if args.disable_pool_shadow:
        pool.visible_shadow = False
    static_water_slots = {
        i for i, material in enumerate(pool.data.materials)
        if material and "pool water" in material.name.lower()
    }
    if static_water_slots:
        footprint = []
        for polygon in pool.data.polygons:
            if polygon.material_index not in static_water_slots:
                continue
            for vertex_index in polygon.vertices:
                world = pool.matrix_world @ pool.data.vertices[vertex_index].co
                footprint.append((world.x, world.y))
        if footprint:
            pool_clip_polygon = inset_convex_polygon(
                convex_hull_2d(footprint), args.pool_clip_margin)
            print("POOL_WATER_CLIP_HULL", pool_clip_polygon.tolist(), flush=True)
        pool.data = pool.data.copy()
        bm = bmesh.new()
        bm.from_mesh(pool.data)
        doomed = [face for face in bm.faces if face.material_index in static_water_slots]
        bmesh.ops.delete(bm, geom=doomed, context="FACES")

        if args.remove_pool_valves:
            remaining_faces = set(bm.faces)
            face_components = []
            while remaining_faces:
                seed = remaining_faces.pop()
                stack = [seed]
                component = []
                while stack:
                    face = stack.pop()
                    component.append(face)
                    for edge in face.edges:
                        for other in edge.link_faces:
                            if other in remaining_faces:
                                remaining_faces.remove(other)
                                stack.append(other)
                face_components.append(component)
            valve_vertices = set()
            for component in face_components:
                points = [pool.matrix_world @ vertex.co
                          for face in component for vertex in face.verts]
                span = [max(point[i] for point in points) - min(point[i] for point in points)
                        for i in range(3)]
                minimum_x = min(point.x for point in points)
                if (minimum_x > 1.20 and span[0] < 0.05 and
                        span[1] < 0.05 and span[2] < 0.05):
                    valve_vertices.update(vertex for face in component for vertex in face.verts)
                    removed_pool_valves += 1
            if valve_vertices:
                bmesh.ops.delete(bm, geom=list(valve_vertices), context="VERTS")

        # The BlenderKit pool includes three detached inflation-valve shells.
        # Their circular bases overlap the main inflatable body but are left
        # topologically open, so a grazing camera can see a small black hole at
        # each junction.  Seal only those three tiny right-end boundary loops;
        # the main inflatable shell is already watertight.
        boundary_edges = [edge for edge in bm.edges if edge.is_boundary]
        by_vertex = {}
        for edge in boundary_edges:
            for vertex in edge.verts:
                by_vertex.setdefault(vertex, []).append(edge)
        remaining = set(boundary_edges)
        boundary_components = []
        while remaining:
            seed = remaining.pop()
            stack = [seed]
            component = []
            while stack:
                edge = stack.pop()
                component.append(edge)
                for vertex in edge.verts:
                    for other in by_vertex.get(vertex, []):
                        if other in remaining:
                            remaining.remove(other)
                            stack.append(other)
            boundary_components.append(component)
        for component in boundary_components:
            points = [pool.matrix_world @ vertex.co
                      for edge in component for vertex in edge.verts]
            span = [max(point[i] for point in points) - min(point[i] for point in points)
                    for i in range(3)]
            minimum_x = min(point.x for point in points)
            if len(component) != 28 or minimum_x < 1.20 or span[1] > 0.05 or span[2] > 0.05:
                continue
            material_index = component[0].link_faces[0].material_index
            result = bmesh.ops.holes_fill(bm, edges=component, sides=0)
            new_faces = result.get("faces", [])
            for face in new_faces:
                face.material_index = material_index
            if new_faces:
                bmesh.ops.recalc_face_normals(bm, faces=new_faces)
                sealed_pool_accessory_openings += 1
        bm.to_mesh(pool.data)
        bm.free()
        pool.data.update()
        print("REMOVED_STATIC_POOL_WATER_FACES", len(doomed), flush=True)
        print("SEALED_POOL_ACCESSORY_OPENINGS", sealed_pool_accessory_openings, flush=True)
        print("REMOVED_POOL_VALVES", removed_pool_valves, flush=True)
    if args.blue_pool_bottom:
        liner = bpy.data.materials.new("PCVE_BluePoolLiner")
        liner.use_nodes = True
        liner_nodes = liner.node_tree.nodes
        liner_links = liner.node_tree.links
        liner_nodes.clear()
        liner_out = liner_nodes.new("ShaderNodeOutputMaterial")
        liner_bsdf = liner_nodes.new("ShaderNodeBsdfPrincipled")
        liner_noise = liner_nodes.new("ShaderNodeTexNoise")
        liner_ramp = liner_nodes.new("ShaderNodeValToRGB")
        liner_noise.inputs["Scale"].default_value = 8.0
        liner_noise.inputs["Detail"].default_value = 2.0
        liner_noise.inputs["Roughness"].default_value = 0.55
        liner_ramp.color_ramp.elements[0].color = (0.012, 0.085, 0.24, 1.0)
        liner_ramp.color_ramp.elements[1].color = (0.035, 0.30, 0.62, 1.0)
        liner_bsdf.inputs["Roughness"].default_value = 0.34
        liner_bsdf.inputs["IOR"].default_value = 1.46
        liner_links.new(liner_noise.outputs["Fac"], liner_ramp.inputs["Fac"])
        liner_links.new(liner_ramp.outputs["Color"], liner_bsdf.inputs["Base Color"])
        liner_links.new(liner_bsdf.outputs["BSDF"], liner_out.inputs["Surface"])
        liner_slot = len(pool.data.materials)
        pool.data.materials.append(liner)
        liner_faces = 0
        if pool_clip_polygon is None:
            raise RuntimeError("blue pool bottom requires the authored pool-water footprint")
        for polygon in pool.data.polygons:
            center = pool.matrix_world @ polygon.center
            inside_liner = points_in_convex_polygon(
                np.asarray([[center.x, center.y]], dtype=float), pool_clip_polygon)[0]
            # The BlenderKit liner is double-sided and its visible inner sheet
            # includes downward-authored faces. Select both sides of the low
            # floor sheet, but constrain the edit to the authored water
            # footprint so low exterior tabs are not painted like spilled water.
            if center.z < 0.03 and inside_liner:
                polygon.material_index = liner_slot
                liner_faces += 1
        print("ASSIGNED_BLUE_POOL_LINER_FACES", liner_faces, flush=True)

proxy = bpy.data.objects["PCVE_ToyCarCollisionProxy"]
visual = bpy.data.objects["PCVE_ToyCarVisual"]
proxy.animation_data_clear()
proxy.hide_render = True
proxy.rotation_mode = "QUATERNION"

# The BlenderKit rally car's authored front is local -Y.  Genesis defines the
# simulated car's forward/downhill direction as local +X, hence +90 degrees.
visual.rotation_mode = "XYZ"
visual.rotation_euler = (0.0, 0.0, np.pi / 2.0)
visual.location = (0.0, 0.0, 0.0)

water_mat = bpy.data.materials.get("PCVE_ClearShallowWater")
if water_mat is None:
    raise RuntimeError("accepted water material missing from appearance scene")
# Rebuild the inherited material as a simple dielectric.  The prior
# Principled-plus-volume network accumulated a chalky white result inside the
# closed Splashsurf mesh and completely hid the liner beneath it.
water_mat = water_mat.copy()
water_mat.name = "PCVE_GenesisClearShallowWater"
water_mat.use_nodes = True
nodes = water_mat.node_tree.nodes
links = water_mat.node_tree.links
nodes.clear()
out_node = nodes.new("ShaderNodeOutputMaterial")
glass = nodes.new("ShaderNodeBsdfGlass")
glass.inputs["Color"].default_value = (0.72, 0.91, 1.0, 1.0)
glass.inputs["Roughness"].default_value = 0.028
glass.inputs["IOR"].default_value = 1.333
links.new(glass.outputs["BSDF"], out_node.inputs["Surface"])
if args.secondary_dir_name:
    # The accepted duck look gets its restrained blue-green depth from volume
    # absorption, not from whitening the surface.  Keep this deliberately weak
    # for the toy pool's roughly 9 cm optical path.
    absorption = nodes.new("ShaderNodeVolumeAbsorption")
    absorption.inputs["Color"].default_value = (0.48, 0.86, 0.93, 1.0)
    absorption.inputs["Density"].default_value = 0.32
    links.new(absorption.outputs["Volume"], out_node.inputs["Volume"])
mesh = bpy.data.meshes.new("PCVE_GenesisWaterMesh")
water = bpy.data.objects.new("PCVE_GenesisWater", mesh)
scene.collection.objects.link(water)
water.data.materials.append(water_mat)
water.hide_render = args.hide_genesis_fluid

spray = None
surface_z = None
secondary = {}
if args.secondary_dir_name:
    secondary = {
        "spray": secondary_object("PCVE_GenesisSpray", particle_material(
            "PCVE_GenesisSprayDrops", (0.92, 0.98, 1.0), 1.0, 0.025)),
        "mist": secondary_object("PCVE_GenesisMist", particle_material(
            "PCVE_GenesisMistDrops", (0.92, 0.97, 1.0), 0.25, 0.42, 0.42)),
        "foam": secondary_object("PCVE_GenesisFoam", particle_material(
            "PCVE_GenesisSurfaceFoam", (0.82, 0.90, 0.94), 0.10, 0.48, 0.78)),
    }
    if args.hide_genesis_fluid:
        for obj in secondary.values():
            obj.hide_render = True
elif args.render_spray_particles:
    with np.load(run / "particles" / "frame_0001.npz") as initial:
        surface_z = float(np.percentile(initial["water_pos"][:, 2], 99.0))
    spray_mesh = bpy.data.meshes.new("PCVE_GenesisSprayMesh")
    spray = bpy.data.objects.new("PCVE_GenesisSpray", spray_mesh)
    scene.collection.objects.link(spray)
    spray.data.materials.append(water_mat)
    spray.hide_render = args.hide_genesis_fluid

scene.render.resolution_x, scene.render.resolution_y = args.resolution
scene.render.resolution_percentage = 100
scene.render.fps = 24
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.use_motion_blur = False  # topology changes per frame
lighting_record = apply_lighting_preset(scene, args.lighting_preset)
if args.contact_fill_energy > 0.0:
    contact_fill = bpy.data.objects.get("PCVE_SoftSkyFill")
    if contact_fill is None or contact_fill.type != "LIGHT":
        raise RuntimeError("contact fill light is missing")
    contact_fill.hide_render = False
    contact_fill.data.energy = args.contact_fill_energy
    lighting_record["contact_fill_energy"] = args.contact_fill_energy
if args.sun_angle_degrees is not None:
    realism_sun = bpy.data.objects.get("PCVE_RealismSun")
    if realism_sun is None or realism_sun.type != "LIGHT" or realism_sun.data.type != "SUN":
        raise RuntimeError("accepted realism sun is missing")
    realism_sun.data.angle = np.radians(args.sun_angle_degrees)
    lighting_record["sun_angle_degrees"] = args.sun_angle_degrees
if args.sun_yaw_offset_degrees:
    realism_sun = bpy.data.objects.get("PCVE_RealismSun")
    if realism_sun is None or realism_sun.type != "LIGHT" or realism_sun.data.type != "SUN":
        raise RuntimeError("accepted realism sun is missing")
    realism_sun.rotation_euler.z += np.radians(args.sun_yaw_offset_degrees)
    lighting_record["sun_yaw_offset_degrees"] = args.sun_yaw_offset_degrees
if args.hdri_yaw_degrees:
    mapping = next(
        (node for node in scene.world.node_tree.nodes if node.bl_idname == "ShaderNodeMapping"), None)
    if mapping is None:
        raise RuntimeError("HDRI yaw requires the source environment Mapping node")
    mapping.inputs["Rotation"].default_value[2] += np.radians(args.hdri_yaw_degrees)
    lighting_record["hdri_yaw_degrees"] = args.hdri_yaw_degrees
if args.engine == "cycles":
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.device = "GPU"
    scene.cycles.max_bounces = 10
    scene.cycles.transmission_bounces = 8
    scene.render.use_persistent_data = False
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
            dev.use = dev.type == prefs.compute_device_type
    except Exception as exc:
        print("GPU_SETUP_WARNING", exc)
else:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.use_raytracing = True
    scene.eevee.ray_tracing_method = "SCREEN"
    scene.eevee.taa_render_samples = args.samples

frames_dir = out / "frames"
frames_dir.mkdir(exist_ok=True)
render_rows = []
started = time.monotonic()
for frame in frames:
    target = frames_dir / f"frame_{frame:04d}.png"
    if args.reuse_existing_frames and target.is_file() and target.stat().st_size > 10000:
        continue
    scene.frame_set(frame)
    car_pos, car_quat, water_pos, water_vel, vertices, triangles = load_state(run, frame, args.mesh_dir_name)
    proxy.location = car_pos.tolist()
    proxy.rotation_quaternion = Quaternion(car_quat.tolist())
    clipped_triangles = 0
    if args.clip_water_to_pool_liner:
        if pool_clip_polygon is None:
            raise RuntimeError("authored pool-water footprint was not found")
        vertices, triangles, clipped_triangles = clip_low_water_to_polygon(
            vertices, triangles, pool_clip_polygon, args.pool_clip_z)
    replace_water_geometry(water, vertices, triangles)
    spray_count = 0
    secondary_counts = {}
    if secondary:
        caps = {"spray": 1800, "mist": 2600, "foam": 3200}
        for kind, obj in secondary.items():
            points, radii = load_secondary(run, args.secondary_dir_name, frame, kind)
            if len(points) > caps[kind]:
                # Stable even sampling keeps the preview cost bounded without
                # selecting only the largest, most conspicuous droplets.
                index = np.linspace(0, len(points) - 1, caps[kind], dtype=int)
                points, radii = points[index], radii[index]
            replace_spray_geometry(obj, points, radii)
            secondary_counts[kind] = int(len(points))
    elif spray is not None:
        speed = np.linalg.norm(water_vel, axis=1)
        mask = ((water_pos[:, 2] > surface_z + 0.004) &
                (speed > args.spray_speed_threshold) & (water_pos[:, 0] < 0.48))
        candidates = np.flatnonzero(mask)
        if len(candidates) > 700:
            score = (water_pos[candidates, 2] - surface_z) + 0.012 * speed[candidates]
            candidates = candidates[np.argpartition(score, -700)[-700:]]
        spray_count = int(len(candidates))
        replace_spray_geometry(spray, water_pos[candidates], radius=args.spray_radius)
    bpy.context.view_layer.update()
    scene.render.filepath = str(target)
    tick = time.monotonic()
    bpy.ops.render.render(write_still=True)
    render_rows.append({"frame": frame, "seconds": time.monotonic() - tick,
                        "car_pos": car_pos.tolist(), "water_vertices": len(vertices),
                        "water_triangles_clipped": clipped_triangles,
                        "spray_particles": spray_count,
                        "secondary_particles": secondary_counts})
    print("RENDER", frame, flush=True)

bpy.ops.wm.save_as_mainfile(filepath=str(out / "scene_genesis.blend"))
manifest = {
    "solver": report["solver"],
    "coupling": report["coupling"],
    "simulation_report": str((run / "simulation_report.json").resolve()),
    "source_appearance_scene": str(args.input_blend.resolve()),
    "car_visual_forward_mapping": "BlenderKit local -Y to Genesis local +X via +90 degree local Z rotation",
    "water_source": "per-frame surface reconstructed exclusively from Genesis DFSPH particles",
    "water_mesh_directory": args.mesh_dir_name,
    "spray_source": "high-speed Genesis DFSPH particles above the reconstructed sheet" if spray else None,
    "duck_style_secondary_directory": args.secondary_dir_name,
    "duck_style_components": list(secondary),
    "camera_preset": args.camera_preset,
    "lighting_preset": args.lighting_preset,
    "background_yaw_degrees": args.background_yaw_degrees,
    "hdri_yaw_degrees": args.hdri_yaw_degrees,
    "environment_hdri": str(args.environment_hdri.resolve()) if args.environment_hdri else None,
    "lighting_changes": lighting_record,
    "blue_pool_bottom": args.blue_pool_bottom,
    "clip_water_to_pool_liner": args.clip_water_to_pool_liner,
    "pool_clip_margin_m": args.pool_clip_margin if args.clip_water_to_pool_liner else None,
    "pool_clip_z_m": args.pool_clip_z if args.clip_water_to_pool_liner else None,
    "pool_clip_polygon_xy": pool_clip_polygon.tolist() if pool_clip_polygon is not None else None,
    "sealed_pool_accessory_openings": sealed_pool_accessory_openings,
    "removed_pool_valves": removed_pool_valves,
    "diagnostic_hide_genesis_fluid": args.hide_genesis_fluid,
    "diagnostic_disable_pool_shadow": args.disable_pool_shadow,
    "frames_rendered": frames,
    "render_seconds": time.monotonic() - started,
    "per_frame": render_rows,
}
(out / "genesis_render_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

if args.preview_frames:
    raise SystemExit(0)

video = out / "video.mp4"
subprocess.run([
    "ffmpeg", "-y", "-v", "warning", "-framerate", "24", "-start_number", "1",
    "-i", str(frames_dir / "frame_%04d.png"), "-frames:v", str(frame_count),
    "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
    "-movflags", "+faststart", str(video),
], check=True)
probe = json.loads(subprocess.check_output([
    "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
    "-show_entries", "stream=width,height,r_frame_rate,avg_frame_rate,nb_read_frames:format=duration,size",
    "-of", "json", str(video),
], text=True))
subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], check=True)
probe["sha256"] = sha256(video)
(out / "video_verification.json").write_text(json.dumps(probe, indent=2) + "\n")
print("VIDEO", video)
print("VERIFY", json.dumps(probe))
