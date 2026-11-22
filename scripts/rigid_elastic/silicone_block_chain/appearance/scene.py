"""Bake the native samples into the packed workshop model and render the delivered look on a pool worker."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "physics"))
from config import CASE_DSL, PLATEN_STOP_Z, SCENE, parameters
from pcve_media_contract import require_times, require_video

FOAM_OBJECTS = ("Material-bound open-cell sponge", "Homogenized cellular interior", "Native FEM carrier")
COLLAR = "Steel ballast collar (40 g)"
CUP = "Physical guided cup"
BALL = "Steel marble"
FLAG = "Passive revolute flag"
SAMPLE_FRAMES = (1, 15, 17, 25, 49, 96)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def material(name, color, roughness, metallic):
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    bsdf = result.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return result


def annulus(name, inner, outer, bottom, top, xy, mat, parent=None):
    sides = 128
    angles = np.linspace(0, 2*math.pi, sides, endpoint=False)
    points = [(r*math.cos(a), r*math.sin(a), z) for z in (bottom, top)
              for r in (inner, outer) for a in angles]
    faces = []
    for i in range(sides):
        j = (i+1) % sides
        faces.extend(((i, i+sides, j+sides, j), (i+2*sides, j+2*sides, j+3*sides, i+3*sides),
                      (i, j, j+2*sides, i+2*sides), (i+sides, i+3*sides, j+3*sides, j+sides)))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent, obj.location = parent, (*xy, 0.)
    mesh.materials.append(mat)
    bevel = obj.modifiers.new("Machined edge radius", "BEVEL")
    bevel.width, bevel.segments = .000065, 2
    obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return obj


def guide_stops():
    steel = bpy.data.materials["Satin stainless fasteners"]
    cap = material("Dark compression stop washers", (.027, .032, .033), .66, 0.)
    for x in (-.035, .035):
        for y in (-.032, .032):
            annulus("Fixed guide stop sleeve", .0015, .00255, .00875, PLATEN_STOP_Z-.0008, (x, y), steel)
            annulus("Lower stop washer", .0015, .0028, PLATEN_STOP_Z-.0008, PLATEN_STOP_Z, (x, y), cap)


def relieve_flag_tongue():
    # The offset only changes the widthwise location of the tongue. Every
    # x-section keeps its area and z coordinates, preserving inertia about Y.
    obj = bpy.data.objects["Light wooden flag"]
    old = obj.data
    points, faces = [], [(0, 3, 2, 1)]
    for x, shift in ((-.029, .006), (-.014, .006), (-.007, 0.), (.041, 0.)):
        points.extend((x-.006, y+shift, z) for y, z in
                      ((-.011, -.001), (.011, -.001), (.011, .001), (-.011, .001)))
    for k in (0, 4, 8):
        for j in range(4):
            a, b = k+j, k+(j+1) % 4
            faces.append((a, b, b+4, a+4))
    faces.append((12, 13, 14, 15))
    mesh = bpy.data.meshes.new("Guide-clear plywood flag")
    mesh.from_pydata(points, [], faces)
    mesh.update()
    for mat in old.materials:
        mesh.materials.append(mat)
    uv = mesh.uv_layers.new(name="Grain-aligned metric UV")
    seed = int(hashlib.sha256(obj.name.encode()).hexdigest()[:8], 16)
    u0, v0 = (seed % 997)/997*.41, ((seed//997) % 991)/991*.41
    for face in mesh.polygons:
        axis = max(range(3), key=lambda k: abs(face.normal[k]))
        axes = [k for k in range(3) if k != axis]
        face.material_index = 0 if axis == 2 else 1
        for loop in face.loop_indices:
            point = mesh.vertices[mesh.loops[loop].vertex_index].co
            uv.data[loop].uv = (point[axes[0]]+u0, point[axes[1]]+v0)
    obj.data = mesh
    bpy.data.meshes.remove(old)


def optical_nodes():
    nodes = bpy.data.materials["Homogenized foam optical interior"].node_tree.nodes
    return [next(n for n in nodes if n.bl_idname == node_type).inputs["Density"] for node_type in
            ("ShaderNodeVolumeScatter", "ShaderNodeVolumeAbsorption")]


def optical_densities(cache, indices):
    tets, rest = cache["elastic_tets"], cache["elastic_rest"]

    def edges(positions):
        corners = positions[tets]
        return np.swapaxes(corners[:, 1:]-corners[:, :1], 1, 2)

    inv = np.linalg.inv(edges(rest))
    ratio = [float(np.linalg.det(edges(cache["elastic_positions"][i]) @ inv).mean()) for i in indices]
    return np.array([1200., 100.])[None, :] / np.array(ratio)[:, None]


def bake(cache, cfg, indices):
    physics = cfg["physics"]
    cup, ball, flag = (bpy.data.objects[name] for name in (CUP, BALL, FLAG))
    for obj in (cup, ball, flag):
        obj.animation_data_clear()
    for frame, index in enumerate(indices, 1):
        plate, x, z, angle = cache["states"][index]
        cup.location = (0., 0., plate)
        ball.location = (x, 0., z)
        ball.rotation_euler.y = float(cache["ball_spin_rad"][index])
        flag.rotation_euler.y = -angle
        cup.keyframe_insert("location", frame=frame)
        ball.keyframe_insert("location", frame=frame)
        ball.keyframe_insert("rotation_euler", frame=frame)
        flag.keyframe_insert("rotation_euler", frame=frame)
    for obj in (cup, ball, flag):
        for curve in obj.animation_data.action.fcurves:
            for key in curve.keyframe_points:
                key.interpolation = "LINEAR"
    ball["mass_kg"] = physics["ball_mass_kg"]
    ball["inner_radius_m"] = cfg["ball_inner_radius_m"]
    ball["axial_inertia_kg_m2"] = cfg["ball_inertia_kg_m2"]
    cup["moving_mass_kg"] = cfg["moving_platen_mass_kg"]
    if physics["foam_present"][0]:
        keys = bpy.data.objects[FOAM_OBJECTS[2]].data.shape_keys.key_blocks
        if len(keys) != len(indices) or len(keys[0].data) != len(cache["elastic_rest"]):
            raise ValueError("Native grid and packed material binding differ.")
        for key, index in zip(keys, indices):
            key.data.foreach_set("co", np.asarray(cache["elastic_positions"][index], np.float32).ravel())
        density_sockets = optical_nodes()
        for frame, densities in enumerate(optical_densities(cache, indices), 1):
            for socket_, value in zip(density_sockets, densities):
                socket_.default_value = float(value)
                socket_.keyframe_insert("default_value", frame=frame)
    else:
        for name in FOAM_OBJECTS:
            obj = bpy.data.objects[name]
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.meshes.remove(mesh)
    guide_stops()
    relieve_flag_tongue()
    if physics["ballast_present"][0]:
        mat = material("Brushed steel collar", (.36, .39, .40), .31, 1.)
        obj = annulus(COLLAR, physics["ballast_inner_radius_m"], physics["ballast_outer_radius_m"],
                      .004, .004+physics["ballast_height_m"], (0., 0.), mat, cup)
        obj["mass_kg"] = physics["ballast_mass_kg"]
        obj["attachment"] = "Bonded to the receiving cup around its outside wall"
    bpy.context.scene.frame_set(1)


def audit_saved(cache, cfg, indices):
    scene = bpy.context.scene
    cup, ball, flag = (bpy.data.objects[name] for name in (CUP, BALL, FLAG))
    physics = cfg["physics"]
    foam = physics["foam_present"][0]
    assert all((name in bpy.data.objects) == bool(foam) for name in FOAM_OBJECTS)
    assert (COLLAR in bpy.data.objects) == bool(physics["ballast_present"][0])
    stop_tops = []
    for obj in bpy.data.objects:
        if obj.name.startswith("Lower stop washer"):
            stop_tops.append(max((obj.matrix_world @ v.co).z for v in obj.data.vertices))
    assert len(stop_tops) == 4 and max(abs(z-PLATEN_STOP_Z) for z in stop_tops) < 1e-8
    assert .004 > .0028 and .052 - math.hypot(.014, .001) > .035+.0028
    scene.frame_set(1)
    common_poses = {
        obj.name: [round(float(value), 8) for row in obj.matrix_world for value in row]
        for obj in sorted(scene.objects, key=lambda item: item.name)
        if obj.name not in (*FOAM_OBJECTS, COLLAR)
    }
    common_rig = {
        "initial_transforms": common_poses,
        "camera_lens": scene.camera.data.lens,
        "focus_distance": scene.camera.data.dof.focus_distance,
        "f_stop": scene.camera.data.dof.aperture_fstop,
        "exposure": scene.view_settings.exposure,
        "lights": [(obj.name, obj.data.energy, list(obj.data.color)) for obj in
                   sorted(scene.objects, key=lambda item: item.name) if obj.type == "LIGHT"],
    }
    errors = {"cup_m": 0., "ball_m": 0., "flag_rad": 0., "spin_rad": 0.,
              "carrier_m": 0., "pore_m": 0., "optical_per_m": 0., "ballast_center_m": 0.}
    if foam:
        carrier = bpy.data.objects[FOAM_OBJECTS[2]]
        pore = bpy.data.objects[FOAM_OBJECTS[0]]
        total = len(pore.data.vertices)
        ids = np.linspace(0, total-1, 1200, dtype=int)
        node_ids, weights = [], []
        for i in range(4):
            full_ids = np.empty(total, np.int32)
            full_weights = np.empty(total, np.float32)
            pore.data.attributes[f"tet_{i}"].data.foreach_get("value", full_ids)
            pore.data.attributes[f"weight_{i}"].data.foreach_get("value", full_weights)
            node_ids.append(full_ids[ids])
            weights.append(full_weights[ids])
        node_ids, weights = np.array(node_ids).T, np.array(weights).T
        sockets = optical_nodes()
        optical = optical_densities(cache, indices)
    for frame, index in enumerate(indices, 1):
        scene.frame_set(frame)
        plate, x, z, angle = cache["states"][index]
        errors["cup_m"] = max(errors["cup_m"], abs(cup.location.z-plate))
        errors["ball_m"] = max(errors["ball_m"], float(np.max(abs(np.asarray(ball.location)-[x, 0., z]))))
        errors["flag_rad"] = max(errors["flag_rad"], abs(flag.rotation_euler.y+angle))
        errors["spin_rad"] = max(errors["spin_rad"], abs(ball.rotation_euler.y-cache["ball_spin_rad"][index]))
        if physics["ballast_present"][0]:
            obj = bpy.data.objects[COLLAR]
            assert obj.parent == cup and obj["mass_kg"] == physics["ballast_mass_kg"]
            coords = [((obj.matrix_world @ v.co).z) for v in obj.data.vertices]
            expected = plate + physics["ballast_initial_center_m"][2]-physics["initial_platen_bottom_m"]
            errors["ballast_center_m"] = max(errors["ballast_center_m"], abs((min(coords)+max(coords))/2-expected))
        if foam:
            graph = bpy.context.evaluated_depsgraph_get()
            coords = np.empty((len(carrier.data.vertices), 3), np.float32)
            carrier.evaluated_get(graph).data.vertices.foreach_get("co", coords.ravel())
            expected = cache["elastic_positions"][index]
            errors["carrier_m"] = max(errors["carrier_m"], float(np.max(abs(coords-expected))))
            errors["optical_per_m"] = max(errors["optical_per_m"], max(
                abs(socket_.default_value-value) for socket_, value in zip(sockets, optical[frame-1])))
            if frame in SAMPLE_FRAMES:
                evaluated = pore.evaluated_get(graph)
                mesh = evaluated.to_mesh()
                coords = np.empty((len(mesh.vertices), 3), np.float32)
                mesh.vertices.foreach_get("co", coords.ravel())
                expected_pores = (expected[node_ids]*weights[..., None]).sum(axis=1)
                errors["pore_m"] = max(errors["pore_m"], float(np.max(abs(coords[ids]-expected_pores))))
                evaluated.to_mesh_clear()
    for key, value in errors.items():
        limit = .002 if key == "optical_per_m" else 1e-5 if key == "spin_rad" else 2e-6
        if value > limit:
            raise ValueError(f"Saved scene mismatch: {key}={value:.6g}")
    scene.frame_set(1)
    return {"frames_checked": 96, "initial_common_scene": common_rig,
            "max_errors": {key: float(value) for key, value in errors.items()},
            "lower_stops_top_m": stop_tops, "foam_present": bool(foam),
            "ballast_present": bool(physics["ballast_present"][0]),
            "pore_samples_per_selected_frame": 1200 if foam else 0,
            "pore_sample_frames": list(SAMPLE_FRAMES) if foam else []}


def set_render_device(scene, mode):
    scene.cycles.device = mode
    if mode == "CPU":
        if os.environ.get("CUDA_VISIBLE_DEVICES", "") not in ("", "-1"):
            raise RuntimeError("CPU jobs must mask the pool GPUs.")
        return None
    gpu = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if not gpu.startswith("GPU-") or "," in gpu:
        raise RuntimeError("A leased UUID must be bound before Blender starts.")
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "CUDA"
    prefs.get_devices()
    selected = [d for d in prefs.devices if d.type == "CUDA"]
    if len(selected) != 1:
        raise RuntimeError("Blender did not see exactly the leased CUDA device.")
    for device in prefs.devices:
        device.use = device == selected[0]
    return selected[0].name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=CASE_DSL)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--preview", type=int, nargs="+")
    parser.add_argument("--device", choices=("CPU", "GPU"), default="GPU")
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--threads", type=int, default=8)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    if args.out.exists() and any(args.out.iterdir()):
        raise FileExistsError(args.out)
    cfg = json.loads((args.cache.parent/"config.json").read_text(encoding="utf-8"))
    assert cfg["case"] == args.case and cfg["edit_dsl"] == CASE_DSL[args.case]
    assert cfg["physics"] == parameters(args.case)
    assert cfg["cache_sha256"] == sha256(args.cache)
    with np.load(args.cache) as native:
        cache = dict(native)
    indices = np.arange(96)*4
    require_times(cache["times"][indices])
    start = time.monotonic()
    bpy.ops.wm.open_mainfile(filepath=str(args.template))
    bake(cache, cfg, indices)
    scene = bpy.context.scene
    scene.cycles.samples = args.samples
    scene.render.threads_mode = "FIXED"
    scene.render.threads = args.threads
    args.out.mkdir(parents=True, exist_ok=True)
    model = args.out/"scene.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(model))
    bpy.ops.wm.open_mainfile(filepath=str(model))
    audit = audit_saved(cache, cfg, indices)
    scene = bpy.context.scene
    device_name = set_render_device(scene, args.device)
    for frame in args.preview or range(1, 97):
        scene.frame_set(frame)
        scene.render.filepath = str(args.out/f"frame_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
    if not args.preview:
        subprocess.run([args.ffmpeg, "-y", "-framerate", "24", "-i", str(args.out/"frame_%04d.png"),
                        "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                        "-threads", "4", str(args.out/"video.mp4")], check=True)
        require_video(args.out/"video.mp4")
    report = {
        "case": args.case, "worker": socket.gethostname(), "blender": bpy.app.version_string,
        "device": args.device, "gpu_name": device_name,
        "gpu_uuid": os.environ.get("CUDA_VISIBLE_DEVICES") if args.device == "GPU" else None,
        "samples": args.samples, "cpu_threads": args.threads, "status": "preview" if args.preview else "complete",
        "native_cache_sha256": cfg["cache_sha256"], "source_template_sha256": sha256(args.template),
        "packed_scene_sha256": sha256(model),
        "physical_times_s": cache["times"][indices].tolist(), "saved_scene_audit": audit,
        "elapsed_s": time.monotonic()-start,
    }
    (args.out/"render_report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print("SAVED_SCENE_AND_RENDER_OK", SCENE, args.case, device_name, flush=True)


if __name__ == "__main__":
    main()
