"""Assets and environment of the bowling-ball pool-drop scene, shared by the render and the sun
visibility: the baked mountain-pool interior, the HDRI world and lights, and the prepared bowling ball.

blender -b --python scene_bowling_ball_pool_drop.py -- --prepare-assets
    validates the mountain-pool and bowling-ball assets and downloads the HDRI if missing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True
import bpy
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
BOWLING_ASSET = ROOT / "assets/blenderkit/bowling_ball/bowling_ball_prepared.blend"
BOWLING_MATERIAL_PRESET = {
    "id": "soft_reflection_resin",
    "roughness_input_range": [0.0, 1.0],
    "roughness_output_range": [0.30, 0.48],
    "coat_weight": 0.12,
    "coat_roughness": 0.28,
}
BOWLING_COLOR_PRESETS = {
    "authored": {
        "id": "authored_blue_purple",
        "pigments_linear_rgba": [[0.5, 0.009707984514534473, 0.14708206057548523, 1.0],
                                 [0.005040808115154505, 0.05993228778243065, 0.5, 1.0]],
    },
    "burgundy-red": {
        "id": "burgundy_red_B",
        "comparison_option": "B",
        "pigments_linear_rgba": [[0.68, 0.025, 0.04, 1.0], [0.92, 0.14, 0.09, 1.0]],
    },
}


def prepare_assets() -> None:
    """Prepare only the assets used by the selected mountain-pool scene."""
    asset_dir = ROOT / "assets" / "sketchfab" / "pool_in_the_mountains_baked"
    blend = asset_dir / "source" / "neuback3.blend"
    source_url = "https://sketchfab.com/3d-models/pool-in-the-mountains-baked-96537a370338456680c8327ec811733f"
    if not blend.is_file():
        raise FileNotFoundError(f"Download the original Blender package from {source_url} and place neuback3.blend at {blend}")
    digest = hashlib.sha256()
    with blend.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    expected = "af82a2dd65a2487152e2366d6ece09ed688b6eec267e525e98bfbeef6d170a46"
    if digest.hexdigest() != expected:
        raise ValueError(f"Unexpected mountain-pool source digest: {digest.hexdigest()}")
    bowling_manifest = BOWLING_ASSET.parent / "prepared_manifest.json"
    if not BOWLING_ASSET.is_file() or not bowling_manifest.is_file():
        raise FileNotFoundError("Prepare the bowling-ball asset described in README.md before building this scene")
    bowling = json.loads(bowling_manifest.read_text())
    if hashlib.sha256(BOWLING_ASSET.read_bytes()).hexdigest() != bowling["prepared_sha256"]:
        raise ValueError("Prepared bowling asset does not match its provenance manifest")
    hdri = ROOT / "assets" / "polyhaven" / "qwantani_patio" / "qwantani_patio_4k.hdr"
    if not hdri.is_file() or hdri.stat().st_size == 0:
        hdri.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/qwantani_patio_4k.hdr",
            headers={"User-Agent": "PhyCoVE asset downloader/1.0"},
        )
        partial = hdri.with_suffix(".hdr.part")
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as stream:
            shutil.copyfileobj(response, stream, length=1024 * 1024)
        partial.replace(hdri)
    print(json.dumps({
        "mountain_pool": {"path": str(blend), "sha256": digest.hexdigest(),
                          "author": "Vince_Crusty (vince.trust)", "license": "CC BY 4.0", "source": source_url},
        "hdri": {"path": str(hdri), "license": "CC0", "source": "https://polyhaven.com/a/qwantani_patio"},
        "bowling_ball": {"path": str(BOWLING_ASSET), "author": bowling["source_author"],
                         "license": "Royalty Free", "diameter_m": bowling["target_diameter_m"]},
    }, indent=2))


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.materials, bpy.data.curves, bpy.data.meshes,
                       bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def add_uv_sphere(name: str, location, radius: float, mat=None) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.shade_smooth()
    if mat:
        obj.data.materials.append(mat)
    return obj


def soften_bowling_ball_material(visual: bpy.types.Object) -> dict:
    """Copy only the ball shader; preserve its color network and roughness detail.

    The authored asset and every fluid/collision setting remain untouched.
    This operation is idempotent, so it can also be applied to a cached scene.
    """
    preset = BOWLING_MATERIAL_PRESET
    for slot in visual.material_slots:
        original = slot.material
        if original is None or not original.use_nodes:
            raise ValueError("Bowling-ball material must have a shader node tree")
        if original.get("pcve_ball_material_preset") != preset["id"]:
            slot.material = original.copy()
            slot.material.name = original.name + "_SoftReflection"
        mat = slot.material
        tree = mat.node_tree
        shaders = [node for node in tree.nodes if node.type == "BSDF_PRINCIPLED"]
        if not shaders:
            raise ValueError("Bowling-ball material has no Principled BSDF")
        for index, shader in enumerate(shaders):
            roughness = shader.inputs["Roughness"]
            node_name = f"PCVE_Ball_SoftRoughness_{index}"
            remap = tree.nodes.get(node_name)
            if remap is None:
                remap = tree.nodes.new("ShaderNodeMapRange")
                remap.name = node_name
                remap.label = "Softened ball reflections; original detail retained"
                remap.location = (shader.location.x - 240, shader.location.y - 260)
                if roughness.is_linked:
                    source = roughness.links[0].from_socket
                    tree.links.remove(roughness.links[0])
                    tree.links.new(source, remap.inputs["Value"])
                else:
                    remap.inputs["Value"].default_value = roughness.default_value
                tree.links.new(remap.outputs["Result"], roughness)
            remap.clamp = True
            remap.inputs["From Min"].default_value, remap.inputs["From Max"].default_value = preset["roughness_input_range"]
            remap.inputs["To Min"].default_value, remap.inputs["To Max"].default_value = preset["roughness_output_range"]
            shader.inputs["Coat Weight"].default_value = preset["coat_weight"]
            shader.inputs["Coat Roughness"].default_value = preset["coat_roughness"]
        mat["pcve_ball_material_preset"] = preset["id"]
    visual["material_preset"] = preset["id"]
    return dict(preset)


def apply_bowling_ball_color(visual: bpy.types.Object, color_name: str) -> dict:
    """Only change the two authored pigment sockets, retaining every other node."""
    preset = BOWLING_COLOR_PRESETS[color_name]
    for slot in visual.material_slots:
        original = slot.material
        if original is None or not original.use_nodes:
            raise ValueError("Bowling-ball color needs the inspected node material")
        if original.get("pcve_ball_color_preset") != preset["id"]:
            slot.material = original.copy()
            slot.material.name = original.name + "_" + preset["id"]
        mat = slot.material
        mix = mat.node_tree.nodes.get("Mix")
        if mix is None or mix.type != "MIX":
            raise ValueError("Bowling-ball pigment Mix node is missing")
        for index, color in zip((6, 7), preset["pigments_linear_rgba"]):
            if mix.inputs[index].is_linked:
                raise ValueError("Unexpected linked pigment socket; refusing to replace its network")
            mix.inputs[index].default_value = color
        mat["pcve_ball_color_preset"] = preset["id"]
    visual["color_preset"] = preset["id"]
    return dict(preset)


def add_bowling_ball_visual(ball: bpy.types.Object, radius: float,
                           asset_path: Path, material_preset: str = "soft-reflection",
                           color_preset: str = "burgundy-red") -> bpy.types.Object:
    """Keep the real finger holes and shader separate from the closed collider."""
    if not asset_path.is_file():
        raise FileNotFoundError(f"Prepared bowling-ball asset is missing: {asset_path}")
    with bpy.data.libraries.load(str(asset_path), link=False) as (source, target):
        if "BowlingBall_Visual" not in source.objects:
            raise ValueError("Asset has no inspected BowlingBall_Visual object")
        target.objects = ["BowlingBall_Visual"]
    visual = target.objects[0]
    bpy.context.scene.collection.objects.link(visual)
    if not visual.data.materials or any(mat is None for mat in visual.data.materials):
        raise ValueError("Bowling-ball material is missing")
    if material_preset == "soft-reflection":
        soften_bowling_ball_material(visual)
    apply_bowling_ball_color(visual, color_preset)
    visual.parent = ball
    visual.matrix_parent_inverse = Matrix.Identity(4)
    visual.location = (0, 0, 0)
    visual.rotation_euler = (0, 0, 0)
    visual.scale = (radius / 0.109,) * 3
    visual["diameter_m"] = 2 * radius
    visual["collision_proxy"] = ball.name
    ball.hide_render = True
    ball["proxy_note"] = "External spherical envelope; small finger cavities omitted from fluid collision and analytic buoyancy"
    return visual


def add_mountain_pool_environment(target_floor_z: float) -> None:
    """Append and align Vince_Crusty's baked mountain-pool environment."""
    asset_path = (
        ROOT / "assets" / "sketchfab" / "pool_in_the_mountains_baked"
        / "source" / "neuback3.blend"
    )
    if not asset_path.exists():
        raise FileNotFoundError(
            f"Missing complete 3D environment: {asset_path}. "
            "Run render_bowling_ball_pool_drop.py --prepare-assets first."
        )
    with bpy.data.libraries.load(str(asset_path), link=False) as (source, target):
        target.objects = [name for name in source.objects if name in {"pool.001", "Skybox"}]
    environment = bpy.data.collections.new("Pool in the Mountains Environment")
    bpy.context.scene.collection.children.link(environment)
    root = bpy.data.objects.new("Pool in the Mountains Root", None)
    environment.objects.link(root)
    for obj in target.objects:
        if obj is None:
            continue
        environment.objects.link(obj)
        if obj.parent is None:
            obj.parent = root
    # The authored pool water spans 8.328 x 8.328 m. Non-uniform horizontal
    # scaling maps that opening exactly onto the benchmark's unchanged 4 x 5 m
    # liquid domain; vertical scale keeps a realistic 2.9 m glazed enclosure.
    source_water_centre = Vector((3.91035, -2.29720, -0.11085))
    root.scale = (4.0 / 8.3283, 5.0 / 8.3284, 0.60)
    root.location = Vector((
        -source_water_centre.x * root.scale.x,
        -source_water_centre.y * root.scale.y,
        -0.18 - source_water_centre.z * root.scale.z,
    ))
    root["asset_source"] = "https://sketchfab.com/3d-models/pool-in-the-mountains-baked-96537a370338456680c8327ec811733f"
    root["asset_author"] = "Vince_Crusty (vince.trust)"
    root["asset_license"] = "CC BY 4.0"
    root["alignment"] = "authored 8.328 m water opening mapped to unchanged 4 x 5 m benchmark pool"

    # The baked environment is one object, but the two purple inflatable pads
    # are independent connected mesh islands. Remove those exact islands in
    # transformed world space so the interaction area reads as a clean pool.
    # This preserves the pool shell, deck, glazing, furniture and plants.
    bpy.context.view_layer.update()
    pool_mesh = bpy.data.objects.get("pool.001")
    if pool_mesh is not None and pool_mesh.type == "MESH":
        mesh = pool_mesh.data
        adjacency = {vertex.index: [] for vertex in mesh.vertices}
        for edge in mesh.edges:
            a, b = edge.vertices
            adjacency[a].append(b)
            adjacency[b].append(a)
        remaining = set(adjacency)
        remove_indices = set()
        removed_components = 0
        while remaining:
            start = remaining.pop()
            stack = [start]
            component = [start]
            while stack:
                current = stack.pop()
                for neighbor in adjacency[current]:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        stack.append(neighbor)
                        component.append(neighbor)
            points = [pool_mesh.matrix_world @ mesh.vertices[index].co for index in component]
            mins = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
            maxs = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
            center = (mins + maxs) * 0.5
            size = maxs - mins
            floating_pad = (
                mins.x > -1.35 and maxs.x < -0.40
                and mins.y > -0.10 and maxs.y < 0.55
                and mins.z > -0.25 and maxs.z < 0.00
            )
            beach_ball = (
                0.90 < center.x < 1.30 and -0.80 < center.y < -0.30
                and -0.25 < center.z < 0.10
                and size.x < 0.35 and size.y < 0.35 and size.z < 0.35
            )
            if floating_pad or beach_ball:
                remove_indices.update(component)
                removed_components += 1
        if remove_indices:
            import bmesh

            bm = bmesh.new()
            bm.from_mesh(mesh)
            bm.verts.ensure_lookup_table()
            bmesh.ops.delete(
                bm,
                geom=[bm.verts[index] for index in sorted(remove_indices)],
                context="VERTS",
            )
            bm.to_mesh(mesh)
            bm.free()
            mesh.update()
            pool_mesh["removed_inflatable_components"] = removed_components

        # The downloaded scene has a decorative basin only about 0.54 m deep
        # after metric alignment. Move just the 47 authored floor vertices to
        # the physical floor height; adjoining faces extend the inner walls.
        # Furniture, coping, glazing and all above-water geometry stay fixed.
        inverse_world = pool_mesh.matrix_world.inverted()
        deepened_vertices = 0
        for vertex in mesh.vertices:
            world = pool_mesh.matrix_world @ vertex.co
            if (
                -2.05 <= world.x <= 2.05
                and -2.55 <= world.y <= 2.55
                and world.z <= -0.40
            ):
                world.z = target_floor_z
                vertex.co = inverse_world @ world
                deepened_vertices += 1
        if deepened_vertices != 47:
            raise RuntimeError(
                f"Expected 47 basin-floor vertices, found {deepened_vertices}"
            )
        mesh.update()
        pool_mesh["deepened_basin_floor_z"] = float(target_floor_z)
        pool_mesh["deepened_basin_vertices"] = deepened_vertices

    # These are light-baked colour atlases. Feeding them through a Principled
    # shader would illuminate an already-lit texture a second time and makes
    # the enclosed pool almost black in Cycles. An emission shader preserves
    # the authored sunset, window shadows and interior light balance.
    for material_name, strength in (("Material.001", 1.78), ("Skybox", 1.12)):
        baked = bpy.data.materials.get(material_name)
        if baked is None or baked.node_tree is None:
            continue
        nodes = baked.node_tree.nodes
        links = baked.node_tree.links
        image_node = next((node for node in nodes if node.type == "TEX_IMAGE"), None)
        output = next((node for node in nodes if node.type == "OUTPUT_MATERIAL"), None)
        if image_node is None or output is None:
            continue
        for link in list(output.inputs["Surface"].links):
            links.remove(link)
        emission = nodes.new("ShaderNodeEmission")
        emission.inputs["Strength"].default_value = strength
        links.new(image_node.outputs["Color"], emission.inputs["Color"])
        links.new(emission.outputs["Emission"], output.inputs["Surface"])

def point_camera(camera: bpy.types.Object, target: tuple[float, float, float]) -> None:
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()


def configure_world() -> None:
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    bg = nodes.get("Background")
    hdri_path = ROOT / "assets" / "polyhaven" / "qwantani_patio" / "qwantani_patio_4k.hdr"
    if hdri_path.exists():
        texcoord = nodes.new("ShaderNodeTexCoord")
        mapping = nodes.new("ShaderNodeMapping")
        environment = nodes.new("ShaderNodeTexEnvironment")
        environment.image = bpy.data.images.load(str(hdri_path))
        mapping.inputs["Rotation"].default_value[2] = math.radians(104)
        bg.inputs["Strength"].default_value = 0.82
        links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], environment.inputs["Vector"])
        links.new(environment.outputs["Color"], bg.inputs["Color"])
    else:
        print(f"[scene] missing HDRI, using Nishita fallback: {hdri_path}")
        sky = nodes.new("ShaderNodeTexSky")
        sky.sky_type = "NISHITA"
        sky.sun_elevation = math.radians(32)
        sky.sun_rotation = math.radians(150)
        bg.inputs["Strength"].default_value = 0.22
        links.new(sky.outputs["Color"], bg.inputs["Color"])


def add_lighting() -> None:
    bpy.ops.object.light_add(type="SUN", location=(2.6, -3.0, 5.2))
    key = bpy.context.object
    key.name = "Qwantani sun match"
    key.data.energy = 0.38
    key.data.angle = math.radians(4.5)
    key.rotation_euler = (math.radians(31), math.radians(-12), math.radians(136))
    bpy.ops.object.light_add(type="AREA", location=(-3.2, 1.8, 3.2))
    fill = bpy.context.object
    fill.name = "Fill_Area"
    fill.data.energy = 12
    fill.data.size = 4.5
    fill.rotation_euler = (math.radians(58), 0.0, math.radians(-118))
    bpy.ops.object.light_add(type="AREA", location=(1.0, 3.8, 4.5))
    rim = bpy.context.object
    rim.name = "Rim_Area"
    rim.data.energy = 16
    rim.data.size = 3.5
    rim.rotation_euler = (math.radians(42), 0.0, math.radians(180))


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-assets", action="store_true", required=True)
    parser.parse_args(argv)
    prepare_assets()


if __name__ == "__main__":
    main()
