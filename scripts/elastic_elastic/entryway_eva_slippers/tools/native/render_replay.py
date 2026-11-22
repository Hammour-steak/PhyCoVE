"""Render exact native states of the replay cases, or one labelled material study (--material-study-state)."""
import argparse
import os
from pathlib import Path
import socket
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy
import numpy as np

from common import INPUTS, read, save, sha
from vocab_replay import SPEC, SPEC_PATH, parameters
from geometry import placed
import render as base
from room_scene import apply, metric_uv, oak
from shoe_tray import tray_mesh

MAX_CPU_PREVIEW_FRAMES = 4


def slipper_material(name, color, sole):
    material = base.material(name, color, 0.57)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["IOR"].default_value = 1.45
    shader.inputs["Coat Weight"].default_value = 0.025
    shader.inputs["Coat Roughness"].default_value = 0.42

    rest = nodes.new("ShaderNodeAttribute")
    rest.attribute_name = "foam_local"
    split = nodes.new("ShaderNodeSeparateXYZ")
    links.new(rest.outputs["Vector"], split.inputs[0])

    mould = nodes.new("ShaderNodeTexNoise")
    mould.inputs["Scale"].default_value = 155.0
    mould.inputs["Detail"].default_value = 2.0
    links.new(rest.outputs["Vector"], mould.inputs["Vector"])
    mould_bump = nodes.new("ShaderNodeBump")
    mould_bump.inputs["Strength"].default_value = 0.24
    mould_bump.inputs["Distance"].default_value = 0.000065
    links.new(mould.outputs["Fac"], mould_bump.inputs["Height"])

    grain = nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 760.0 if sole else 1080.0
    grain.inputs["Detail"].default_value = 2.4
    links.new(rest.outputs["Vector"], grain.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.46
    bump.inputs["Distance"].default_value = 0.00012 if sole else 0.000075
    links.new(grain.outputs["Fac"], bump.inputs["Height"])
    links.new(mould_bump.outputs[0], bump.inputs["Normal"])
    links.new(bump.outputs[0], shader.inputs["Normal"])

    rough = nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.46 if sole else 0.53
    rough.inputs["To Max"].default_value = 0.68
    links.new(grain.outputs["Fac"], rough.inputs["Value"])
    links.new(rough.outputs[0], shader.inputs["Roughness"])

    pigment = nodes.new("ShaderNodeValToRGB")
    pigment.color_ramp.elements[0].color = (*[v * 0.78 for v in color], 1)
    pigment.color_ramp.elements[1].color = (*[v * 1.15 for v in color], 1)
    links.new(grain.outputs["Fac"], pigment.inputs[0])
    if sole:
        band = nodes.new("ShaderNodeMapRange")
        band.inputs["From Min"].default_value = 0.0075
        band.inputs["From Max"].default_value = 0.0090
        links.new(split.outputs["Z"], band.inputs["Value"])
        tint = nodes.new("ShaderNodeMixRGB")
        tint.inputs[1].default_value = (0.029, 0.042, 0.044, 1)
        links.new(band.outputs[0], tint.inputs[0])
        links.new(pigment.outputs[0], tint.inputs[2])
        links.new(tint.outputs[0], shader.inputs["Base Color"])

        rotate = nodes.new("ShaderNodeVectorRotate")
        rotate.rotation_type = "AXIS_ANGLE"
        rotate.inputs["Axis"].default_value = (0, 0, 1)
        rotate.inputs["Angle"].default_value = np.pi / 4
        links.new(rest.outputs["Vector"], rotate.inputs["Vector"])
        ridges = []
        for direction in ("X", "Y"):
            ribs = nodes.new("ShaderNodeTexWave")
            ribs.bands_direction = direction
            ribs.inputs["Scale"].default_value = 60
            links.new(rotate.outputs["Vector"], ribs.inputs["Vector"])
            ridge = nodes.new("ShaderNodeMath")
            ridge.operation = "GREATER_THAN"
            ridge.inputs[1].default_value = 0.85
            links.new(ribs.outputs["Fac"], ridge.inputs[0])
            ridges.append(ridge)
        pattern = nodes.new("ShaderNodeMath")
        pattern.operation = "MAXIMUM"
        for index, ridge in enumerate(ridges):
            links.new(ridge.outputs[0], pattern.inputs[index])
        mask = nodes.new("ShaderNodeAttribute")
        mask.attribute_name = "foam_footbed"
        bed = nodes.new("ShaderNodeBump")
        bed.inputs["Distance"].default_value = 0.00022
        links.new(mask.outputs["Fac"], bed.inputs["Strength"])
        links.new(pattern.outputs[0], bed.inputs["Height"])
        links.new(bump.outputs[0], bed.inputs["Normal"])
        links.new(bed.outputs[0], shader.inputs["Normal"])
    else:
        links.new(pigment.outputs[0], shader.inputs["Base Color"])
    return material


def apply_actor_finish(scene, cache, geometry):
    """Assign sole and vamp by original face labels after the room setup."""
    sole = slipper_material("Moulded slate EVA sole and grip edge", (0.085, 0.130, 0.135), True)
    vamp = slipper_material("Pebbled EVA vamp", (0.064, 0.102, 0.107), False)
    vertices = geometry["vertices"]
    faces = geometry["faces"]
    normals = np.zeros_like(vertices)
    face_normals = np.cross(vertices[faces[:, 1]] - vertices[faces[:, 0]],
                            vertices[faces[:, 2]] - vertices[faces[:, 0]])
    for corner in range(3):
        np.add.at(normals, faces[:, corner], face_normals)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-15)
    footbed = np.clip((normals[:, 2] - 0.45) / 0.45, 0, 1)
    footbed *= np.clip((vertices[:, 2] - 0.018) / 0.003, 0, 1)
    for actor in scene.objects:
        if "part_id" not in actor:
            continue
        part = actor["part_id"]
        original = np.flatnonzero(cache["part_ids"] == part)
        faces = cache["faces"][np.all(cache["part_ids"][cache["faces"]] == part, axis=1)]
        local_indices = np.searchsorted(original, np.unique(faces))
        attribute = actor.data.attributes.new("foam_local", "FLOAT_VECTOR", "POINT")
        attribute.data.foreach_set("vector", geometry["vertices"][local_indices].astype(np.float32).ravel())
        grip = actor.data.attributes.new("foam_footbed", "FLOAT", "POINT")
        grip.data.foreach_set("value", footbed[local_indices].astype(np.float32))
        actor.data.materials[0] = sole
        actor.data.materials[1] = vamp
        actor.data.polygons.foreach_set("material_index", geometry["material_ids"].astype(np.int32))


def setup_state(case, geometry):
    physics = parameters(case)
    positions, faces, ids = [], [], []
    offset = 0
    for part, name in enumerate(("falling", "resting")):
        if part == 1 and not physics["resting_present"][0]:
            continue
        vertices, _, surface = placed(geometry, physics, name)
        positions.append(vertices)
        faces.append(surface + offset)
        ids.append(np.full(len(vertices), part))
        offset += len(vertices)
    world = np.concatenate(positions)
    return dict(positions=world[None], rest=world, faces=np.concatenate(faces),
                part_ids=np.concatenate(ids), times=np.array([0.0]))


def main():
    host = socket.gethostname().split(".")[0]
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=SPEC["cases"], required=True)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=160)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--preview", nargs="+", type=int)
    parser.add_argument("--cpu-preview", action="store_true")
    parser.add_argument("--material-study-state", action="store_true")
    parser.add_argument("--setup-study", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.out.exists():
        raise FileExistsError(args.out)
    if args.cpu_preview and (not args.preview or len(args.preview) > MAX_CPU_PREVIEW_FRAMES):
        raise ValueError("CPU rendering is limited to the requested diagnostic samples")
    if args.material_study_state and (not args.preview or args.case != "source"):
        raise ValueError("An earlier cached state is for the labelled material study only")
    if args.setup_study:
        if args.cache or args.preview != [1] or args.material_study_state:
            raise ValueError("The initial setup study is a single still without a dynamics cache")
        config = dict(mesh_level=SPEC["simulation"]["mesh_level"], geometry_file=SPEC["simulation"]["geometry"])
        with np.load(INPUTS / "accepted_delivery/geometry_d" / Path(config["geometry_file"]).name) as geometry:
            cache = setup_state(args.case, geometry)
    else:
        if args.cache is None:
            raise ValueError("A native cache is required for this render")
        config = read(args.cache.parent / "simulation_config.json")
        if not args.material_study_state and config["physics"] != parameters(args.case):
            raise ValueError("The replay scene requires its matching native cache")
        with np.load(args.cache) as archive:
            cache = {key: archive[key] for key in ("positions", "times", "faces", "part_ids", "rest")}
            if not args.material_study_state:
                for key in ("tray_transforms", "tray_vertices_local", "tray_faces"):
                    cache[key] = archive[key]
    args.out.mkdir(parents=True)
    base.build.level = config["mesh_level"]
    base.build.geometry_file = config["geometry_file"]
    base.build.cpu_preview = args.cpu_preview
    scene = base.build(cache, "source", args.out, args.width, args.samples)
    room = apply(scene, SPEC["render"])
    with np.load(INPUTS / "accepted_delivery/geometry_d" / Path(config["geometry_file"]).name) as geometry:
        apply_actor_finish(scene, cache, geometry)
    if not args.material_study_state and parameters(args.case)["tray_present"][0]:
        if args.setup_study:
            vertices, faces = tray_mesh(parameters(args.case))
            sequence = vertices[None]
        else:
            transforms = cache["tray_transforms"]
            if transforms.shape != (len(cache["times"]), 4, 4):
                raise ValueError("The added tray requires one actual native affine state per sample")
            local = cache["tray_vertices_local"]
            sequence = local[None] @ transforms[:, :3, :3].transpose(0, 2, 1) + transforms[:, None, :3, 3]
            vertices, faces = sequence[0], cache["tray_faces"]
        tray = base.mesh_object("Added wooden shoe tray", vertices, faces, oak())
        tray["pcve_contact_object"] = "shoe_tray"
        tray["pcve_motion_source"] = "Native affine-body transforms, exact vertex replay without rigid projection"
        metric_uv(tray)
        tray.shape_key_add(name="Basis")
        for frame in range(1, len(sequence)):
            key = tray.shape_key_add(name=f"Native_tray_{frame:03d}")
            key.data.foreach_set("co", sequence[frame].astype(np.float32).ravel())
            for timeline, value in ((frame, 0.0), (frame + 1, 1.0), (frame + 2, 0.0)):
                key.value = value
                key.keyframe_insert("value", frame=timeline)
        if tray.data.shape_keys.animation_data:
            for curve in tray.data.shape_keys.animation_data.action.fcurves:
                for point in curve.keyframe_points:
                    point.interpolation = "LINEAR"
    if args.setup_study:
        scene.frame_end = 1
    metadata = read(args.out / "render_config.json")
    metadata["baseline_builder_scene_spec_sha256"] = metadata.pop("scene_spec_sha256")
    cache_hash = sha(args.cache) if args.cache else None
    take = "production"
    if args.material_study_state:
        take = "material_study"
    if args.setup_study:
        take = "initial_setup_no_simulation"
    metadata.update(room, case=args.case, visual_revision="replay", frames=scene.frame_end,
                    physics_take=take,
                    native_cache_sha256=cache_hash, visual_spec_sha256=sha(SPEC_PATH),
                    scene_spec_sha256=sha(SPEC_PATH),
                    hero_material="Two-tone moulded EVA, fine pores, mould grain and shallow diamond footbed grip",
                    material_detail_max_bump_distance_m=0.00022,
                    decorative_collision_scope="Native contact uses the floor, both present slides and the optional freely moving finite-mass concave shoe tray. Background props remain outside the contact domain.")
    if args.setup_study:
        metadata.update(physical_duration_s=0.0, native_endpoint_s=None, diagnostic_only=True)
    save(args.out / "render_config.json", metadata)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out / "scene.blend"), compress=True)
    frames = args.preview or list(range(1, 97))
    if min(frames) < 1 or max(frames) > scene.frame_end:
        raise ValueError("Requested frame has no physical sample")
    folder = args.out / ("previews" if args.preview else "frames")
    folder.mkdir()
    start = time.monotonic()
    for frame in frames:
        scene.frame_set(frame)
        scene.render.filepath = str(folder / f"{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
    save(args.out / "render_receipt.json", dict(
        case=args.case, frames=frames, preview=bool(args.preview), host=host,
        gpu_uuid=os.environ["CUDA_VISIBLE_DEVICES"], cache_sha256=cache_hash,
        scene_sha256=sha(args.out / "scene.blend"), wall_s=time.monotonic() - start,
        material_study_state=args.material_study_state,
        setup_study=args.setup_study,
    ))


if __name__ == "__main__":
    main()
