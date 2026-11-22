"""Current look of the foam press rig: the accepted packed scene lit and backed by a photographed workshop.

Run inside Blender 4.3 on an accepted packed scene `assets/scenes/silicone_block_chain/accepted_solves/packed/<case>.blend`
(sha256 checked against `delivery_manifest.json` of the accepted delivery); the saved file is never written.
Ball, cup/platen, flag, ballast ring, foam, camera and frame clock stay those of the saved scene. Before anything
changes, every requested frame is checked against the native cache (`accepted_solves/physics/<case>/simulation.npz`,
96 Hz, frame f = sample 4 (f - 1)); right before each render the same frame is checked again and every original
object, the foam surfaces, the foam optical densities and the camera must equal the pre-overlay state exactly.

What the overlay changes: the hidden studio lights and the backdrop wall are removed, the scene is lit only by a
calibrated HDR panorama of a real workshop (Poly Haven, CC0), which is also what the steel parts reflect and what the
defocused background shows; props that came from BlenderKit and the numerals of the paper gauge are removed; the
camera gets a real shutter (motion blur) and a mild lens finish.

    <blender> -b packed/<case>.blend --python-exit-code 1 --python realism.py -- --case <case> --out OUT [--frames 1-96]
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import subprocess
import sys

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(HERE), str(HERE.parent), str(ROOT / "scripts")]
import pcve_realism_kit as kit
from pcve_assets import asset
from scene_paths import DELIVERY, INPUTS

CASES = ("source", "stiff_foam", "light_ball", "viscous_foam", "remove_foam")
TIMED_CASES = ("light_ball_at_frame_8",)
STRIDE = 4                                    # 96 Hz native cache, 24 fps video
CUP, BALL, FLAG, COLLAR = "Physical guided cup", "Steel marble", "Passive revolute flag", "Steel ballast collar (40 g)"
CARRIER, PORES, INTERIOR = "Native FEM carrier", "Material-bound open-cell sponge", "Homogenized cellular interior"
TOL_M, TOL_RAD = 2e-6, 1e-5                   # the delivered audit's limits (float32 keyframes)
HDRI = "polyhaven/{id}/{id}_4k.hdr"
# Saved-scene objects that do not belong in the photograph: BlenderKit props (ruler, pencil and their empties),
# the sketch sheet, the gauge numerals and the low backdrop wall right behind the bench.
REMOVED_PREFIXES = ("BlenderKit", "12in", "Pencil", "Lightly curled graph paper", "Scale number", "Matte school wall")
# Wood of each part: Poly Haven scan (None keeps the saved plywood scan), tile size in metres, HSV, small grain turn
# (degrees) and how its cut edges read: plies of a sheet ("ply"), or end grain of solid wood ("solid").
TEXTURE = "polyhaven/{id}/{id}_{kind}_4k.jpg"
WOOD = {
    "Plywood mechanism base":      ("white_maple_veneer", 1.0, (0.50, 1.25, 0.92), 0.0, "ply"),     # birch-faced ply
    "Fitted sloping wooden riser": ("ash_veneer", 1.0, (0.50, 1.00, 0.92), 1.5, "solid"),
    "Track exit support":          ("ash_veneer", 1.0, (0.49, 1.05, 0.86), -2.0, "solid"),
    "Short wooden ball track":     (None, 0.5, (0.50, 0.80, 0.98), 0.0, "ply"),                     # saved okoume ply
    "Wood track side rail":        (None, 0.5, (0.50, 0.78, 1.00), 0.8, "solid"),
    "Wood track side rail.001":    (None, 0.5, (0.50, 0.78, 0.96), -0.6, "solid"),
    "Light plywood sliding platen": ("white_maple_veneer", 1.0, (0.48, 1.65, 0.80), 90.0, "ply"),   # aged, cross grain
    "Shallow receiving cup":       (None, 0.5, (0.51, 0.90, 0.90), 0.0, "ply"),
    "Light wooden flag":           ("ash_veneer", 1.0, (0.50, 0.95, 1.02), 0.0, "solid"),
    "Flag hinge support":          (None, 0.5, (0.50, 0.70, 1.05), 0.0, "solid"),
    "Flag hinge support.001":      (None, 0.5, (0.50, 0.70, 1.00), 0.0, "solid"),
    "Flag horizontal rest":        (None, 0.5, (0.50, 0.75, 1.08), 0.0, "solid"),
    "Spare wood offcut":           ("ash_veneer", 1.0, (0.50, 1.00, 0.95), 3.0, "solid"),
    "Spare wood offcut.001":       ("white_maple_veneer", 1.0, (0.50, 1.40, 0.88), -2.0, "ply"),
}
PLY_COLORS = ((1.0, 0.98, 0.94, 1.0), (0.80, 0.74, 0.62, 1.0), (0.32, 0.25, 0.16, 1.0))   # light ply, dark ply, glue line


# ---------------------------------------------------------------- frozen-state checks
def delivered_scene(case):
    saved = Path(bpy.data.filepath)
    manifest = json.loads((DELIVERY / "delivery_manifest.json").read_text())
    pinned = {Path(f["path"]).name: f["sha256"] for f in manifest["files"] if str(f.get("path", "")).endswith(".blend")}
    digest = kit.sha256(saved)
    if saved.name != f"{case}.blend" or pinned.get(saved.name) != digest:
        raise RuntimeError(f"{saved} is not the accepted packed scene for {case}")
    return saved, digest


def native(case):
    with np.load(INPUTS / f"physics/{case}/simulation.npz") as z:
        return {k: z[k] for k in z.files}


def native_dir_scene(case, directory):
    """A native state outside the accepted delivery: DIR/packed.blend baked by bake_native.py from DIR/simulation.npz."""
    directory = directory.resolve()
    report = json.loads((directory / "bake_report.json").read_text())
    saved = Path(bpy.data.filepath).resolve()
    cache_path = directory / "simulation.npz"
    digest = kit.sha256(saved)
    if (saved != directory / "packed.blend" or report["case"] != case or digest != report["packed_scene_sha256"]
            or kit.sha256(cache_path) != report["native_cache_sha256"]
            or json.loads((directory / "config.json").read_text())["cache_sha256"] != report["native_cache_sha256"]):
        raise RuntimeError(f"{saved} is not the bake of {cache_path} for {case}")
    with np.load(cache_path) as z:
        return saved, digest, {k: z[k] for k in z.files}, cache_path


def evaluated_co(obj, graph):
    ev = obj.evaluated_get(graph)
    mesh = ev.to_mesh()
    co = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    m = np.array(obj.matrix_world)
    return co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]


def optical_sockets():
    mat = bpy.data.materials.get("Homogenized foam optical interior")
    if not mat:
        return []
    return [n.inputs["Density"] for n in mat.node_tree.nodes
            if n.bl_idname in ("ShaderNodeVolumeScatter", "ShaderNodeVolumeAbsorption")]


def snapshot(scene, frame, originals):
    """Everything the overlay must not touch, at one frame."""
    scene.frame_set(frame)
    graph = bpy.context.evaluated_depsgraph_get()
    snap = {"poses": {n: tuple(map(tuple, bpy.data.objects[n].matrix_world)) for n in originals},
            "carrier": evaluated_co(bpy.data.objects[CARRIER], graph) if CARRIER in bpy.data.objects else None,
            "optical": tuple(round(s.default_value, 9) for s in optical_sockets())}
    digest = hashlib.sha256()
    for name in (PORES, INTERIOR):
        if name in bpy.data.objects:
            digest.update(np.ascontiguousarray(evaluated_co(bpy.data.objects[name], graph)).tobytes())
    snap["sponge_sha256"] = digest.hexdigest()
    cam = scene.camera
    snap["camera"] = (tuple(map(tuple, cam.matrix_world)), cam.data.lens, cam.data.sensor_width, cam.data.shift_x,
                      cam.data.shift_y, cam.data.dof.use_dof, cam.data.dof.aperture_fstop, cam.data.dof.focus_distance,
                      cam.data.dof.focus_object.name if cam.data.dof.focus_object else None,
                      scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage,
                      scene.render.fps, scene.render.fps_base, scene.frame_start, scene.frame_end)
    return snap


def check_against_cache(frame, cache):
    """The saved scene's own audit, per frame: cup, ball, spin, flag, foam carrier, ring."""
    bpy.context.scene.frame_set(frame)
    i = STRIDE * (frame - 1)
    if abs(float(cache["times"][i]) - (frame - 1) / 24) > 1e-9:
        raise RuntimeError(f"frame {frame}: cache clock mismatch")
    plate, x, z, angle = (float(v) for v in cache["states"][i])
    cup, ball, flag = (bpy.data.objects[n] for n in (CUP, BALL, FLAG))
    err = {"cup_m": abs(cup.location.z - plate),
           "ball_m": float(np.max(np.abs(np.asarray(ball.location) - (x, 0.0, z)))),
           "flag_rad": abs(flag.rotation_euler.y + angle),
           "spin_rad": abs(ball.rotation_euler.y - float(cache["ball_spin_rad"][i]))}
    if CARRIER in bpy.data.objects:
        graph = bpy.context.evaluated_depsgraph_get()
        err["carrier_m"] = float(np.max(np.abs(evaluated_co(bpy.data.objects[CARRIER], graph) - cache["elastic_positions"][i])))
    elif "elastic_positions" in cache and cache["elastic_positions"].size:
        raise RuntimeError(f"frame {frame}: cache has a foam block but the scene has none")
    if COLLAR in bpy.data.objects and bpy.data.objects[COLLAR].parent is not cup:
        raise RuntimeError("ballast ring is no longer carried by the cup")
    for key, value in err.items():
        if value > (TOL_RAD if key.endswith("rad") else TOL_M):
            raise RuntimeError(f"frame {frame}: {key} = {value:.3g} exceeds the delivered tolerance")
    return err


def check_unchanged(frame, before, after):
    for name, pose in before["poses"].items():
        if after["poses"][name] != pose:
            raise RuntimeError(f"frame {frame}: overlay moved {name}")
    if (before["carrier"] is None) != (after["carrier"] is None) or (
            before["carrier"] is not None and not np.array_equal(before["carrier"], after["carrier"])):
        raise RuntimeError(f"frame {frame}: overlay changed the foam carrier")
    for key in ("sponge_sha256", "optical", "camera"):
        if before[key] != after[key]:
            raise RuntimeError(f"frame {frame}: overlay changed {key}")


# ---------------------------------------------------------------- overlay
def remove_props(scene):
    hidden = []
    for obj in scene.objects:
        if obj.name.startswith(REMOVED_PREFIXES):
            for item in (obj, *obj.children_recursive):
                if not item.hide_render:
                    item.hide_render = True
                    hidden.append(item.name)
    return sorted(set(hidden))


def workshop_light(scene, args):
    """Light, reflections and background from one HDR panorama; nothing hidden adds light."""
    removed = [o.name for o in scene.objects if o.type == "LIGHT"]
    for name in removed:
        bpy.data.objects.remove(bpy.data.objects[name])
    path = args.hdri_file or asset(HDRI.format(id=args.hdri))
    world = bpy.data.worlds.new("Photographed workshop")
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    nodes.clear()
    coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(args.hdri_rotation))
    env = nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(path), check_existing=True)
    env.interpolation = "Cubic"
    background = nodes.new("ShaderNodeBackground")
    background.inputs["Strength"].default_value = args.hdri_strength
    output = nodes.new("ShaderNodeOutputWorld")
    links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    links.new(env.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])
    world.cycles.sampling_method = "MANUAL"
    world.cycles.sample_map_resolution = 2048
    return {"removed_lights": removed, "hdri": str(Path(path).relative_to(ROOT) if ROOT in Path(path).parents else path),
            "hdri_sha256": kit.sha256(path), "rotation_deg": args.hdri_rotation, "strength": args.hdri_strength}


def sanded_edges(scene):
    """Cut plywood is sanded: round its 90-degree edges a little (0.6 mm, 0.3 mm on parts under 4 mm). Geometry
    only; object transforms, and so every pose the checks compare, stay the saved ones."""
    done = []
    for obj in scene.objects:
        if obj.type != "MESH" or not any(m and "plywood" in m.name for m in obj.data.materials):
            continue
        if any(m.type == "BEVEL" for m in obj.modifiers):
            continue
        bevel = obj.modifiers.new("Sanded edge", "BEVEL")
        bevel.width = 0.0003 if min(obj.dimensions) < 0.004 else 0.0006
        bevel.segments = 3
        bevel.limit_method = "ANGLE"
        bevel.angle_limit = math.radians(40)
        bevel.use_clamp_overlap = True
        done.append(obj.name)
    return sorted(done)


def _seeded(name, span):
    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
    return ((seed % 997) / 997 * span, ((seed // 997) % 991) / 991 * span)


def _texture_coordinates(mat, name, tile_m, turn_deg):
    """UV (metric, grain-aligned) -> turn -> per-part offset -> 1/tile; feeds every image of the material."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    uv = next((n for n in nodes if n.bl_idname == "ShaderNodeUVMap"), None)
    images = [n for n in nodes if n.bl_idname == "ShaderNodeTexImage"]
    if uv is None or not images:
        return
    rotate = nodes.new("ShaderNodeVectorRotate")
    rotate.rotation_type = "Z_AXIS"
    rotate.inputs["Angle"].default_value = math.radians(turn_deg)
    offset = nodes.new("ShaderNodeVectorMath")
    offset.operation = "ADD"
    offset.inputs[1].default_value = (*_seeded(name, 0.8), 0.0)
    scale = nodes.new("ShaderNodeVectorMath")
    scale.operation = "MULTIPLY"
    scale.inputs[1].default_value = (1 / tile_m, 1 / tile_m, 1.0)
    links.new(uv.outputs["UV"], rotate.inputs["Vector"])
    links.new(rotate.outputs["Vector"], offset.inputs[0])
    links.new(offset.outputs["Vector"], scale.inputs[0])
    for image in images:
        links.new(scale.outputs["Vector"], image.inputs["Vector"])


def _swap_images(mat, species):
    for node in mat.node_tree.nodes:
        if node.bl_idname != "ShaderNodeTexImage" or not node.image:
            continue
        for kind in ("diff", "rough", "nor_gl"):
            if f"_{kind}_" in node.image.name:
                node.image = bpy.data.images.load(str(asset(TEXTURE.format(id=species, kind=kind))), check_existing=True)
                node.image.colorspace_settings.name = "sRGB" if kind == "diff" else "Non-Color"


def wood_species(scene):
    """Different stock for different parts: birch-faced ply base and platen (the platen aged, cross grain), ash posts
    and flag, the saved okoume ply for the track, cup and small sticks; each part with its own grain offset and tone."""
    done = {}
    for name, (species, tile_m, hsv, turn, edge) in WOOD.items():
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            continue
        for mat in obj.data.materials:
            if mat is None or not mat.use_nodes:
                continue
            nodes = mat.node_tree.nodes
            if species:
                _swap_images(mat, species)
            _texture_coordinates(mat, name, tile_m, turn)
            if "photographed unfinished plywood" in mat.name:
                tint = next(n for n in nodes if n.bl_idname == "ShaderNodeHueSaturation")
                for key, value in zip(("Hue", "Saturation", "Value"), hsv):
                    tint.inputs[key].default_value = value
            elif "alternating veneer end layers" in mat.name:
                layers, _, glue = (nodes.get(n) for n in ("Mix (Legacy)", "Mix (Legacy).001", "Mix (Legacy).002"))
                glue_mask = nodes.get("Math.006")
                if edge == "ply":
                    layers.inputs["Color1"].default_value, layers.inputs["Color2"].default_value = PLY_COLORS[:2]
                    glue.inputs["Color2"].default_value = PLY_COLORS[2]
                else:                                   # solid wood: no plies, slightly darker end grain
                    layers.inputs["Color1"].default_value = layers.inputs["Color2"].default_value = (0.78, 0.74, 0.68, 1.0)
                    glue_mask.inputs[1].default_value = 0.0
        done[name] = species or "saved plywood scan"
    return done


def foam_surface():
    """Deformation marks as thin felt-tip lines (soft edges, partly soaked in) instead of hard dark cuts, and the
    light/dark mottling and pore shading of open-cell PU foam. All in the foam's rest coordinates, so every mark moves
    with the material."""
    mat = bpy.data.materials.get("Warm uncoated open-cell PU foam")
    if mat is None or PORES not in bpy.data.objects:
        return None
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    rest = nodes["Attribute"]
    mix = nodes["Mix (Legacy)"]
    region = nodes["Math.003"]
    lines = []
    for distance in ("Math.005", "Math.008", "Math.012"):
        for width, weight in ((0.0005, 1.0), (0.0013, 0.25)):      # ink line and its faint bleed into the cells
            soft = nodes.new("ShaderNodeMapRange")
            soft.interpolation_type = "SMOOTHSTEP"
            soft.inputs["From Min"].default_value = width * 0.35
            soft.inputs["From Max"].default_value = width
            soft.inputs["To Min"].default_value = weight
            soft.inputs["To Max"].default_value = 0.0
            links.new(nodes[distance].outputs["Value"], soft.inputs["Value"])
            lines.append(soft)
    mark = lines[0]
    for other in lines[1:]:
        biggest = nodes.new("ShaderNodeMath")
        biggest.operation = "MAXIMUM"
        links.new(mark.outputs[0], biggest.inputs[0])
        links.new(other.outputs[0], biggest.inputs[1])
        mark = biggest
    masked = nodes.new("ShaderNodeMath")
    masked.operation = "MULTIPLY"
    links.new(mark.outputs[0], masked.inputs[0])
    links.new(region.outputs["Value"], masked.inputs[1])
    ink = nodes.new("ShaderNodeMath")
    ink.operation = "MULTIPLY"
    ink.inputs[1].default_value = 0.65
    links.new(masked.outputs[0], ink.inputs[0])
    links.new(ink.outputs[0], mix.inputs["Fac"])
    mix.inputs["Color2"].default_value = (0.10, 0.13, 0.22, 1.0)            # faded blue-black marker
    shade = None
    for scale, low, high in ((70.0, 0.86, 1.06), (900.0, 0.85, 1.0)):      # broad mottling, cell-cluster shading
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = scale
        noise.inputs["Detail"].default_value = 3.0
        links.new(rest.outputs["Vector"], noise.inputs["Vector"])
        level = nodes.new("ShaderNodeMapRange")
        level.inputs["From Min"].default_value, level.inputs["From Max"].default_value = 0.3, 0.7
        level.inputs["To Min"].default_value, level.inputs["To Max"].default_value = low, high
        links.new(noise.outputs["Fac"], level.inputs["Value"])
        if shade is None:
            shade = level
        else:
            product = nodes.new("ShaderNodeMath")
            product.operation = "MULTIPLY"
            links.new(shade.outputs[0], product.inputs[0])
            links.new(level.outputs[0], product.inputs[1])
            shade = product
    darken = nodes.new("ShaderNodeMixRGB")
    darken.blend_type = "MULTIPLY"
    darken.inputs["Fac"].default_value = 1.0
    links.new(mix.outputs["Color"], darken.inputs["Color1"])
    links.new(shade.outputs[0], darken.inputs["Color2"])
    links.new(darken.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])
    return mat.name


def steel_rule():
    """The paper gauge becomes a short brushed stainless rule with fine etched graduations."""
    rule = bpy.data.objects.get("Fixed scale")
    if rule is None:
        return None
    steel = bpy.data.materials.new("Brushed stainless rule")
    steel.use_nodes = True
    nodes, links = steel.node_tree.nodes, steel.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.66, 0.66, 0.64, 1.0)
    bsdf.inputs["Metallic"].default_value = 1.0
    coord = nodes.new("ShaderNodeTexCoord")
    stretch = nodes.new("ShaderNodeMapping")
    stretch.inputs["Scale"].default_value = (2600.0, 2600.0, 18.0)          # brushing runs along the rule
    links.new(coord.outputs["Object"], stretch.inputs["Vector"])
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 1.0
    noise.inputs["Detail"].default_value = 6.0
    links.new(stretch.outputs["Vector"], noise.inputs["Vector"])
    rough = nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value, rough.inputs["To Max"].default_value = 0.20, 0.34
    links.new(noise.outputs["Fac"], rough.inputs["Value"])
    links.new(rough.outputs[0], bsdf.inputs["Roughness"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.06
    bump.inputs["Distance"].default_value = 0.00002
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    rule.data.materials.clear()
    rule.data.materials.append(steel)
    etched = bpy.data.materials.new("Etched graduations")
    etched.use_nodes = True
    etched.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.03, 0.03, 0.03, 1.0)
    etched.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.55
    ticks = [o for o in bpy.data.objects if o.name.startswith("Millimetre tick")]
    for tick in ticks:
        tick.data.materials.clear()
        tick.data.materials.append(etched)
    return {"rule": rule.name, "graduations": len(ticks)}


def camera_finish(scene, args):
    scene.render.use_motion_blur = args.shutter > 0
    scene.render.motion_blur_shutter = args.shutter
    scene.render.use_persistent_data = False         # Blender 4.3: persistent data with motion blur drops settled objects
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = args.look
    scene.view_settings.exposure = args.exposure
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.005
    scene.cycles.sample_clamp_indirect = 4.0
    scene.cycles.caustics_reflective = scene.cycles.caustics_refractive = False
    scene.cycles.seed = 0
    scene.cycles.use_animated_seed = False
    kit.lens_finish(scene, vignette=0.12, dispersion=0.003)


def overlay(scene, args):
    hidden = remove_props(scene)
    edges = sanded_edges(scene)
    woods = wood_species(scene)
    foam = foam_surface()
    rule = steel_rule()
    light = workshop_light(scene, args)
    camera_finish(scene, args)
    return {"hidden_objects": hidden, "sanded_edges": edges, "wood": woods, "foam_material": foam,
            "steel_rule": rule, "light": light}


def frame_list(text):
    if "-" in text:
        a, b = text.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(f) for f in text.split(",")]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--case", required=True, help=" | ".join(CASES + TIMED_CASES) + "; any case id with --native-dir "
                   "(checked against its bake_report.json)")
    p.add_argument("--native-dir", type=Path, help="render DIR/packed.blend (appearance/bake_native.py) of DIR/simulation.npz "
                   "instead of an accepted case (timed edits; the source re-solve they branch from)")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--frames", default="1-96", help="'a-b' or a comma list")
    p.add_argument("--look-mode", choices=("delivered", "realism"), default="realism")
    p.add_argument("--hdri", default="small_workshop", help="Poly Haven id under assets/polyhaven")
    p.add_argument("--hdri-file", type=Path, help="test override of the panorama file")
    p.add_argument("--hdri-rotation", type=float, default=270.0, help="degrees about +z; 270 puts the windows behind the camera")
    p.add_argument("--hdri-strength", type=float, default=1.0)
    p.add_argument("--exposure", type=float, default=0.8)
    p.add_argument("--look", default="AgX - Medium High Contrast")
    p.add_argument("--shutter", type=float, default=0.25, help="fraction of a frame; 0 disables motion blur")
    p.add_argument("--samples", type=int, default=384)
    p.add_argument("--video", action="store_true", help="encode video.mp4 after frames 1-96")
    p.add_argument("--device", choices=("OPTIX", "CUDA", "CPU"), default="OPTIX")
    args = p.parse_args(argv)
    frames = frame_list(args.frames)
    scene = bpy.context.scene
    if args.native_dir is not None:
        saved, saved_sha, cache, cache_path = native_dir_scene(args.case, args.native_dir)
    else:
        if args.case not in CASES:
            raise RuntimeError("a timed case is rendered from its --native-dir")
        saved, saved_sha = delivered_scene(args.case)
        cache = native(args.case)
        cache_path = INPUTS / f"physics/{args.case}/simulation.npz"
    originals = sorted(o.name for o in scene.objects if o.type != "LIGHT")      # lights are replaced
    before, worst = {}, {}
    for f in frames:                                           # frozen state, before any change
        for key, value in check_against_cache(f, cache).items():
            worst[key] = max(worst.get(key, 0.0), value)
        before[f] = snapshot(scene, f, originals)
    audit = overlay(scene, args) if args.look_mode == "realism" else {"note": "saved delivered look"}
    if args.native_dir is not None and not json.loads((args.native_dir / "config.json").read_text())["physics"].get(
            "ball_present", [1])[0]:
        # DELETE steel_ball: the solve keeps the ball's coordinates parked and uncoupled; the ball is not rendered
        # (camera, shadow, reflection and every other ray).
        ball = bpy.data.objects[BALL]
        for obj in (ball, *ball.children_recursive):
            obj.hide_render = True
        audit["not_rendered"] = [BALL, *(o.name for o in ball.children_recursive)]
    if args.device == "CPU":
        scene.cycles.device = "CPU"
    else:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = args.device    # 3090s in some pools crash in OptiX init; they render with CUDA
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == args.device
        if sum(bool(d.use) for d in prefs.devices) != 1:
            raise RuntimeError(f"expected exactly one visible {args.device} GPU")
        scene.cycles.device = "GPU"
    scene.cycles.samples = args.samples
    args.out.mkdir(parents=True, exist_ok=True)
    provenance = {
        "look": args.look_mode, "case": args.case, "worker": kit.host_record(), "blender": bpy.app.version_string,
        "saved_scene": str(saved.relative_to(ROOT)) if ROOT in saved.parents else str(saved), "saved_scene_sha256": saved_sha,
        "native_cache": str(cache_path.relative_to(ROOT)) if ROOT in cache_path.parents else str(cache_path),
        "native_cache_sha256": kit.sha256(cache_path),
        "overlay": audit,
        "samples": args.samples, "exposure": args.exposure, "view_look": args.look, "shutter": args.shutter,
        "device": args.device, "frames": [frames[0], frames[-1], len(frames)],
        "frozen_check": {"pre_overlay_max_error": worst, "tolerance_m": TOL_M, "tolerance_rad": TOL_RAD, "per_frame": {}}}
    for f in frames:
        err = check_against_cache(f, cache)
        check_unchanged(f, before[f], snapshot(scene, f, originals))
        provenance["frozen_check"]["per_frame"][f] = max(err.values())
        scene.frame_set(f)
        scene.render.filepath = str(args.out / f"frame_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("REALISM_FRAME", f, f"max_err={max(err.values()):.2e}", flush=True)
        kit.write_json(args.out / "realism_provenance.json", provenance)
    if args.video:
        if frames != list(range(1, 97)):
            raise RuntimeError("--video needs frames 1-96")
        video = args.out / "video.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "24", "-i", str(args.out / "frame_%04d.png"),
                        "-frames:v", "96", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(video)], check=True)
        provenance["video"] = {"file": video.name, "sha256": kit.sha256(video)}
        kit.write_json(args.out / "realism_provenance.json", provenance)
    print("REALISM_DONE", args.case, len(frames), flush=True)


main()
