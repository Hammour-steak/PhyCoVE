"""Current look of tennis_net_hit: a public hard court in a park on a clear afternoon.

Runs the replay renderer `appearance/render.py` unchanged in substance: the qualified render
cache, the dense native deformation keys, the 1 um replay checks, the camera, the 1/480 s centred
shutter and the frame timing are those of the delivered renderer. render.py is run with `__overlay__`
in its globals and calls it after the replay checks, so the look is recorded in the renderer's
own report (`render_setup_*.json`, key `appearance_overlay`). Nothing here reads or writes solver state.

    <blender> -b assets/scenes/tennis_net_hit/inputs/scene.blend --disable-autoexec --python-exit-code 1 \
        --python realism.py -- --case <case> --cache <render_cache.npz> --out <renders/tennis_net_hit/...> \
        [--frames 1-96] [--samples N] [--device OPTIX|CUDA|CPU] [--threads N]
"""
from pathlib import Path
import argparse
import json
import math
import runpy
import sys

import bpy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import pcve_realism_kit as kit  # noqa: E402
from pcve_assets import asset  # noqa: E402

RENDERER = HERE / "render.py"
LOOK = "clear_afternoon_park_court"
CASES = ("source", "ball_speed_div5", "ball_speed_x2", "net_young_div10", "net_young_x10", "remove_entire_net")
# Cases outside the published catalog, rendered by the driver in the staged suite's inputs/edit_<case>/.
STAGED_CASES = ("remove_tennis_ball",)

DEFAULTS = {
    # Poly Haven CC0 sky (unclipped sun); the sun lamp follows the image's own sun.
    "sky": "polyhaven/pretoria_gardens/pretoria_gardens_8k.hdr",   # 8k: the park beyond the fence stays sharp
    "sun_azimuth_deg": 155.0,      # world azimuth toward the sun: on the camera's right, so the park beyond
                                   # the fence is sunlit and the net throws its shadow onto the far court
    "sky_strength": 1.0,
    "sun_energy": 4.5,             # W/m^2 added along the image sun: clear-sky sun/sky ratio
    "sun_color": (1.0, 0.955, 0.90),
    "exposure": -0.5,
    "view_look": "AgX - Medium High Contrast",
    "samples": 192,
    # Acrylic hard court (sRGB): inner court blue, outer green, off-white lines
    "court_blue": ((0.21, 0.31, 0.43), (0.23, 0.34, 0.47)),       # sun-faded acrylic blue
    "court_green": ((0.18, 0.31, 0.24), (0.20, 0.34, 0.26)),      # surround green
    "line_white": ((0.80, 0.81, 0.78), (0.88, 0.89, 0.86)),
    "mottle": (0.07, 0.035),       # broad / fine relative albedo variation of the faded coat
    "court_relief": (0.45, 0.32),  # normal-map and fine-bump strength of the sand-filled acrylic
}


def srgb_to_linear(c):
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


def image_sun(image):
    """Equirect longitude/elevation (deg) of the brightest pixel: the unclipped sun of the HDRI."""
    import numpy as np
    w, h = image.size
    px = np.empty(w * h * 4, np.float32)
    image.pixels.foreach_get(px)
    lum = px.reshape(h, w, 4)[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    row, col = np.unravel_index(int(np.argmax(lum)), lum.shape)
    u = (col + 0.5) / w
    v = (row + 0.5) / h                       # Blender pixel rows run bottom to top
    return 360.0 * u, 180.0 * v - 90.0, float(lum[row, col])


def world_and_sun(scene, p):
    for obj in [o for o in scene.objects if o.type == "LIGHT"]:
        bpy.data.objects.remove(obj)          # the packed scene's own "hazy afternoon sun", unrelated to any sky image
    tree = scene.world.node_tree
    env = next(n for n in tree.nodes if n.type == "TEX_ENVIRONMENT")
    sky = asset(p["sky"])
    env.image = bpy.data.images.load(str(sky), check_existing=True)
    u_deg, elevation, peak = image_sun(env.image)
    mapping = next(n for n in tree.nodes if n.type == "MAPPING")
    # Blender looks up u = 0.5 - atan2(y, x) / 2pi on the rotated vector: the image sun is at lookup
    # azimuth 180 - u, and the Mapping node adds its Z rotation to the world azimuth.
    rotation = (180.0 - u_deg) - p["sun_azimuth_deg"]
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(rotation))
    next(n for n in tree.nodes if n.type == "BACKGROUND").inputs["Strength"].default_value = p["sky_strength"]
    az, el = math.radians(p["sun_azimuth_deg"]), math.radians(elevation)
    toward = (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))
    kit.sun("Clear-sky sun along the sky image's sun", tuple(-c for c in toward), p["sun_energy"],
            angle_deg=0.53, color=p["sun_color"])
    return {"sky": sky.name, "sky_sha256": kit.sha256(sky), "image_sun_longitude_deg": round(u_deg, 2),
            "sun_elevation_deg": round(elevation, 2), "sun_azimuth_deg": p["sun_azimuth_deg"],
            "sky_rotation_deg": round(rotation, 3), "sun_energy_w_m2": p["sun_energy"]}


def recolour_ramp(material_name, colours):
    """Two-stop albedo ramp of a scanned acrylic material, keeping its microtexture and wear fields."""
    mat = bpy.data.materials[material_name]
    ramps = [n for n in mat.node_tree.nodes if n.type == "VALTORGB" and n.name == "Color Ramp"]
    if len(ramps) != 1 or len(ramps[0].color_ramp.elements) != 2:
        raise RuntimeError(f"{material_name}: expected one two-stop albedo ramp")
    for element, colour in zip(ramps[0].color_ramp.elements, colours):
        element.color = (*srgb_to_linear(colour), 1.0)
    return [list(c) for c in colours]


def mottle(material_name, broad, fine, seed):
    """Uneven fading of an outdoor acrylic coat: a multi-metre tonal field and a finer patchiness,
    multiplied into the material's final albedo (its scanned microtexture and wear layers stay)."""
    mat = bpy.data.materials[material_name]
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    socket = bsdf.inputs["Base Color"]
    upstream = socket.links[0].from_socket
    position = nodes.new("ShaderNodeNewGeometry")
    factor = None
    for scale, amount, detail in ((0.22, broad, 3.0), (1.1, fine, 4.0)):
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = scale
        noise.inputs["Detail"].default_value = detail
        noise.noise_dimensions = "4D"
        noise.inputs["W"].default_value = seed
        links.new(position.outputs["Position"], noise.inputs["Vector"])
        level = nodes.new("ShaderNodeMapRange")
        level.inputs["From Min"].default_value = 0.35
        level.inputs["From Max"].default_value = 0.65
        level.inputs["To Min"].default_value = 1.0 - amount
        level.inputs["To Max"].default_value = 1.0 + amount * 0.6
        links.new(noise.outputs["Fac"], level.inputs["Value"])
        if factor is None:
            factor = level.outputs["Result"]
        else:
            both = nodes.new("ShaderNodeMath")
            both.operation = "MULTIPLY"
            links.new(factor, both.inputs[0])
            links.new(level.outputs["Result"], both.inputs[1])
            factor = both.outputs["Value"]
    mix = nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    links.new(upstream, mix.inputs["A"])
    gray = nodes.new("ShaderNodeCombineColor")
    for channel in ("Red", "Green", "Blue"):
        links.new(factor, gray.inputs[channel])
    links.new(gray.outputs["Color"], mix.inputs["B"])
    links.new(mix.outputs["Result"], socket)
    return {"broad": broad, "fine": fine}


def relief(material_name, normal, bump):
    """Sand-filled acrylic shows its grain at grazing sun: raise the scanned normal map and fine bump."""
    nodes = bpy.data.materials[material_name].node_tree.nodes
    maps = [n for n in nodes if n.type == "NORMAL_MAP"]
    bumps = [n for n in nodes if n.type == "BUMP" and n.name == "Bump"]
    if len(maps) != 1 or len(bumps) != 1:
        raise RuntimeError(f"{material_name}: expected one normal map and one fine bump")
    maps[0].inputs["Strength"].default_value = normal
    bumps[0].inputs["Strength"].default_value = bump
    return {"normal_strength": normal, "bump_strength": bump}


# The packed scene's crescent "pivot rubber" decals render as thin dark rings, its herringbone
# outsole decals as striped arcs and its two hairline cracks as thin dark curves; none reads as a
# real mark at this distance. They are hidden and replaced by soft marks in the court shader below.
HIDDEN_DECALS = ("pivot rubber", "faded partial outsole", "limited hairline coating crack")


def hide_decals(scene):
    hidden = [o.name for o in scene.objects if o.name.startswith(HIDDEN_DECALS)]
    for name in hidden:
        bpy.data.objects[name].hide_render = True
    return hidden


def _scatter(nodes, links, coords, scale, stretch, offset, keep, inner, outer, breakup):
    """Soft, sparse, irregular blobs: one Voronoi cell in ~1/(1-keep) carries a blob whose edge fades
    from `inner` to `outer` (cell units) and is broken up by noise. No hard threshold, so no rings."""
    shaped = nodes.new("ShaderNodeVectorMath")
    shaped.operation = "MULTIPLY_ADD"
    shaped.inputs[1].default_value = (scale * stretch[0], scale * stretch[1], 0.0)
    shaped.inputs[2].default_value = offset
    links.new(coords, shaped.inputs[0])
    cells = nodes.new("ShaderNodeTexVoronoi")
    cells.voronoi_dimensions = "2D"
    cells.feature = "F1"
    cells.inputs["Randomness"].default_value = 1.0
    links.new(shaped.outputs["Vector"], cells.inputs["Vector"])
    pick = nodes.new("ShaderNodeSeparateColor")
    links.new(cells.outputs["Color"], pick.inputs["Color"])
    chosen = nodes.new("ShaderNodeMapRange")
    chosen.inputs["From Min"].default_value = keep
    chosen.inputs["From Max"].default_value = keep + 0.04
    links.new(pick.outputs["Red"], chosen.inputs["Value"])
    body = nodes.new("ShaderNodeMapRange")
    body.interpolation_type = "SMOOTHERSTEP"
    body.inputs["From Min"].default_value = outer
    body.inputs["From Max"].default_value = inner
    links.new(cells.outputs["Distance"], body.inputs["Value"])
    grain = nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = breakup
    grain.inputs["Detail"].default_value = 4.0
    links.new(coords, grain.inputs["Vector"])
    patchy = nodes.new("ShaderNodeMapRange")
    patchy.inputs["From Min"].default_value = 0.30
    patchy.inputs["From Max"].default_value = 0.70
    patchy.inputs["To Min"].default_value = 0.35
    links.new(grain.outputs["Fac"], patchy.inputs["Value"])
    mask = None
    for socket in (chosen.outputs["Result"], body.outputs["Result"], patchy.outputs["Result"]):
        if mask is None:
            mask = socket
            continue
        both = nodes.new("ShaderNodeMath")
        both.operation = "MULTIPLY"
        links.new(mask, both.inputs[0])
        links.new(socket, both.inputs[1])
        mask = both.outputs["Value"]
    return mask


def court_marks(material_name, density, seed):
    """Soft scuffs and shoe-rubber smudges (darker, slightly glossier) and a few fuzzy yellow-green
    tennis-ball marks, laid into the final albedo of the acrylic coat."""
    mat = bpy.data.materials[material_name]
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    base = bsdf.inputs["Base Color"]
    upstream = base.links[0].from_socket
    geometry = nodes.new("ShaderNodeNewGeometry")
    warp = nodes.new("ShaderNodeTexNoise")
    warp.inputs["Scale"].default_value = 2.2
    warp.inputs["Detail"].default_value = 3.0
    links.new(geometry.outputs["Position"], warp.inputs["Vector"])
    centred = nodes.new("ShaderNodeVectorMath")
    centred.operation = "MULTIPLY_ADD"
    centred.inputs[1].default_value = (0.14, 0.14, 0.0)
    centred.inputs[2].default_value = (-0.07, -0.07, 0.0)
    links.new(warp.outputs["Color"], centred.inputs[0])
    coords = nodes.new("ShaderNodeVectorMath")
    coords.operation = "ADD"
    links.new(geometry.outputs["Position"], coords.inputs[0])
    links.new(centred.outputs["Vector"], coords.inputs[1])
    coords = coords.outputs["Vector"]
    keep_scuff = 1.0 - 0.14 * density
    scuffs = [_scatter(nodes, links, coords, 1.3, stretch, (seed, 3.1 * seed, 0.0), keep_scuff, 0.0, 0.46, 4.0)
              for stretch in ((1.0, 0.30), (0.30, 1.0))]
    scuff = nodes.new("ShaderNodeMath")
    scuff.operation = "MAXIMUM"
    links.new(scuffs[0], scuff.inputs[0])
    links.new(scuffs[1], scuff.inputs[1])
    balls = _scatter(nodes, links, coords, 1.2, (1.0, 0.5), (7.3 * seed, seed, 0.0), 1.0 - 0.10 * density,
                     0.0, 0.09, 30.0)
    darker = nodes.new("ShaderNodeMix")
    darker.data_type = "RGBA"
    darker.blend_type = "MIX"
    darker.inputs["B"].default_value = (*srgb_to_linear((0.17, 0.18, 0.19)), 1.0)
    weight = nodes.new("ShaderNodeMath")
    weight.operation = "MULTIPLY"
    weight.inputs[1].default_value = 0.28
    links.new(scuff.outputs["Value"], weight.inputs[0])
    links.new(weight.outputs["Value"], darker.inputs["Factor"])
    links.new(upstream, darker.inputs["A"])
    felt = nodes.new("ShaderNodeMix")
    felt.data_type = "RGBA"
    felt.blend_type = "MIX"
    felt.inputs["B"].default_value = (*srgb_to_linear((0.58, 0.64, 0.24)), 1.0)
    tint = nodes.new("ShaderNodeMath")
    tint.operation = "MULTIPLY"
    tint.inputs[1].default_value = 0.55
    links.new(balls, tint.inputs[0])
    links.new(tint.outputs["Value"], felt.inputs["Factor"])
    links.new(darker.outputs["Result"], felt.inputs["A"])
    links.new(felt.outputs["Result"], base)
    rough = bsdf.inputs["Roughness"]
    if rough.is_linked:
        sheen = nodes.new("ShaderNodeMath")
        sheen.operation = "MULTIPLY_ADD"
        sheen.inputs[1].default_value = -0.10
        links.new(scuff.outputs["Value"], sheen.inputs[0])
        links.new(rough.links[0].from_socket, sheen.inputs[2])
        links.new(sheen.outputs["Value"], rough)
    return {"scuff_cells_kept": round(1 - keep_scuff, 3), "ball_mark_cells_kept": round(0.10 * density, 3)}


def debrand(scene):
    """The sideline racket asset carries a manufacturer's logo images; drop them and keep its plain paint."""
    removed = []
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        tree = mat.node_tree
        for node in [n for n in tree.nodes if n.type == "TEX_IMAGE" and n.image is not None]:
            name = node.image.name.lower()
            if "wilson" not in name and "logo" not in name:
                continue
            for link in list(tree.links):
                if link.from_node is node:
                    socket = link.to_socket
                    tree.links.remove(link)
                    if socket.name in ("Factor", "Fac", "Alpha"):
                        socket.default_value = 0.0
            removed.append(f"{mat.name}:{node.image.name}")
    return removed


def apply_look(scene, params=None):
    p = dict(DEFAULTS, **(params or {}))
    record = {"look": LOOK}
    record["world"] = world_and_sun(scene, p)
    record["court"] = {
        "blue": recolour_ramp("Acrylic_court_blue_scanned_microtexture", p["court_blue"]),
        "green": recolour_ramp("Acrylic_outer_green_scanned_microtexture", p["court_green"]),
        "lines": [recolour_ramp("used acrylic line 0.050m", p["line_white"]),
                  recolour_ramp("used acrylic line 0.100m", p["line_white"])][0]}
    if p["mottle"]:
        record["court"]["mottle"] = [mottle("Acrylic_court_blue_scanned_microtexture", *p["mottle"], seed=1.7),
                                     mottle("Acrylic_outer_green_scanned_microtexture", *p["mottle"], seed=4.2)]
    if p["court_relief"]:
        record["court"]["relief"] = [relief(name, *p["court_relief"]) for name in
                                     ("Acrylic_court_blue_scanned_microtexture", "Acrylic_outer_green_scanned_microtexture")]
    record["court"]["retired_decals"] = hide_decals(scene)
    record["court"]["marks"] = [court_marks("Acrylic_court_blue_scanned_microtexture", 1.0, 1.3),
                                court_marks("Acrylic_outer_green_scanned_microtexture", 0.5, 2.9)]
    record["debranded"] = debrand(scene)
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = p["view_look"]
    scene.view_settings.exposure = p["exposure"]
    scene.cycles.samples = p["samples"]
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    scene.cycles.denoising_prefilter = "ACCURATE"
    scene.cycles.sample_clamp_indirect = 10.0
    # Blender 4.3: with motion blur on, persistent data makes objects that come to rest vanish in later frames.
    scene.render.use_persistent_data = False
    kit.lens_finish(scene, vignette=0.10, dispersion=0.002)
    record.update(view_transform="AgX", view_look=p["view_look"], exposure=p["exposure"], samples=p["samples"],
                  denoiser="OIDN albedo+normal, accurate prefilter", persistent_data=False)
    return record


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--case", required=True, choices=CASES + STAGED_CASES)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--frames", default="1-96", help="'a-b'")
    p.add_argument("--samples", type=int, default=DEFAULTS["samples"])
    p.add_argument("--device", choices=("OPTIX", "CUDA", "CPU"), default="OPTIX")
    p.add_argument("--threads", type=int, default=6)
    p.add_argument("--audit-only", action="store_true")
    args = p.parse_args(argv)
    first, last = (int(v) for v in args.frames.split("-"))
    qual = json.loads(args.cache.with_name("qualification.json").read_text())
    cache_sha = kit.sha256(args.cache)
    if not qual["passed"] or qual["case_id"] != args.case or qual["render_cache_sha256"] != cache_sha:
        raise SystemExit("The cache is not the qualified render cache of this case")
    if args.out.exists():
        raise SystemExit("Choose a fresh output directory")
    sys.argv = [sys.argv[0], "--", "--cache", str(args.cache.resolve()), "--case-id", args.case, "--out", str(args.out.resolve()),
                "--start-frame", str(first), "--end-frame", str(last), "--samples", str(args.samples),
                "--device", args.device, "--threads", str(args.threads)] + (["--audit-only"] if args.audit_only else [])
    look = {}

    def overlay(scene, a):
        look.update(apply_look(scene, {"samples": args.samples}))
        return look

    runpy.run_path(str(RENDERER), init_globals={"__overlay__": overlay}, run_name="tennis_render")
    kit.write_json(args.out / "realism_provenance.json", {
        "revision": LOOK, "case": args.case, "worker": kit.host_record(), "device": args.device,
        "blender": bpy.app.version_string, "packed_scene": Path(bpy.data.filepath).name,
        "render_cache_sha256": cache_sha,
        "hook": "after the replay checks, before render_setup is written", "look_record": look,
        "samples": args.samples, "frames": [first, last]})


if __name__ == "__main__":
    main()
