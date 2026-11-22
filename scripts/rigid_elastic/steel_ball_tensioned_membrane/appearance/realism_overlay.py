"""Appearance overlay for the accepted base steel-ball membrane replay.

Opens the accepted, fully animated base scene of a case
(`renders/steel_ball_tensioned_membrane/outputs/accepted/cases/<case>/scene.blend`),
checks its sha256 against that case's artifact manifest, changes shaders, lights and
colour settings only, and renders the same 96 frames. Before rendering it proves that
geometry, shape-key animation, modifiers, transforms and the camera are byte-identical
(the base `immutable_signature`) and replays all 96 states against `simulation.npz` with the
base audit tolerances. `--look base` renders the base look of the saved scene through the same path.

    <blender> -b --factory-startup --disable-autoexec --python-exit-code 1 --python realism_overlay.py -- \
        --case <case> --out renders/steel_ball_tensioned_membrane/.work/<folder>/<case> [--frames 1-96]
"""
from pathlib import Path
import argparse
import json
import sys
import time
from types import SimpleNamespace

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(HERE))
import pcve_realism_kit as kit
from upgrade_visuals import immutable_signature   # the base byte-sensitive geometry/animation signature

REVISION = "realism_overlay"
DATA = ROOT / "renders/steel_ball_tensioned_membrane"
ACCEPTED = DATA / "outputs/accepted/cases"
CASES = ("source", "ball_mass_heavy", "membrane_soft", "membrane_stiff", "remove_membrane", "add_second_ball")
# Cases outside the published catalog: their saved scene comes from --case-dir (the staged suite's driver).
STAGED_CASES = ("remove_ball",)
MEMBRANE_UV_SPAN_M = 0.76          # the 'DIC coordinates' UV square spans the clear diameter
LATEX_ROUGH = 0.16                 # smooth, glossy black latex sheet
SPECKLES = False                   # optional sprayed white DIC speckle paint (off: the user wants a smooth sheet)
SPECKLE_CELL_M = 0.0042            # speckle pitch; dots of roughly 1.5-3.5 mm
SPECKLE_KEEP = 0.10                # fraction of cells left unpainted
PAINT = 0.58                       # matte white spray paint albedo
BOARD_ROUGH = 0.42                 # lapped stainless optical-table top
BOARD_ALBEDO = 0.60
HOLE_PITCH_M = 0.025               # M6 tapped holes on a 25 mm grid
HOLE_ORIGIN_M = (-1.32, -0.91)     # aligned with the scene's own (hidden) M6 bore grid
HOLE_RADIUS_M = 0.0032
WORLD_STRENGTH = 0.32              # base value
EXPOSURE = -0.25
TUNABLE = ("LATEX_ROUGH", "SPECKLES", "SPECKLE_CELL_M", "SPECKLE_KEEP", "PAINT", "BOARD_ROUGH", "BOARD_ALBEDO",
           "HOLE_PITCH_M", "HOLE_RADIUS_M", "WORLD_STRENGTH", "EXPOSURE", "LAYOUT",
           "WALLS", "WALL_ALBEDO")
VISIBLE_TABLE = "Damped optical breadboard"   # its top (z = 0) is what the camera sees; the coplanar skin loses


def nodes_of(mat):
    return mat.node_tree.nodes, mat.node_tree.links


def math(nodes, links, op, a, b=None, clamp=False):
    node = nodes.new("ShaderNodeMath")
    node.operation = op
    node.use_clamp = clamp
    for socket, value in zip(node.inputs, (a, b)):
        if value is None:
            continue
        if isinstance(value, (int, float)):
            socket.default_value = value
        else:
            links.new(value, socket)
    return node.outputs[0]


def fresh(name):
    old = bpy.data.materials.get(name)
    if old:
        old.name = name + " (replaced)"
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    return mat, kit._principled(mat)


def latex_sheet():
    """Smooth glossy black latex; optional sprayed white DIC speckles bound to the membrane's material UVs."""
    mat, bs = fresh("Black latex with sprayed DIC speckles" if SPECKLES else "Smooth black latex sheet")
    nodes, links = nodes_of(mat)
    uv = nodes.new("ShaderNodeTexCoord").outputs["UV"]
    cells = nodes.new("ShaderNodeTexVoronoi")
    cells.feature = "F1"
    cells.inputs["Scale"].default_value = MEMBRANE_UV_SPAN_M / SPECKLE_CELL_M
    cells.inputs["Randomness"].default_value = 1.0
    links.new(uv, cells.inputs["Vector"])
    rnd = nodes.new("ShaderNodeSeparateColor")
    links.new(cells.outputs["Color"], rnd.inputs["Color"])
    radius = math(nodes, links, "MULTIPLY_ADD", rnd.outputs[0], 0.20)        # 0.20..0.40 of a cell
    radius.node.inputs[2].default_value = 0.20
    ragged = nodes.new("ShaderNodeTexNoise")                                   # irregular droplet rims
    ragged.inputs["Scale"].default_value = 3.0 * MEMBRANE_UV_SPAN_M / SPECKLE_CELL_M
    ragged.inputs["Detail"].default_value = 1.0
    links.new(uv, ragged.inputs["Vector"])
    wobble = math(nodes, links, "MULTIPLY_ADD", ragged.outputs["Fac"], 0.16)
    wobble.node.inputs[2].default_value = -0.08
    distance = math(nodes, links, "ADD", cells.outputs["Distance"], wobble)
    edge = math(nodes, links, "SUBTRACT", radius, distance)
    dot = math(nodes, links, "DIVIDE", edge, 0.04, clamp=True)                 # soft, anti-aliased rim
    keep = math(nodes, links, "GREATER_THAN", rnd.outputs[1], SPECKLE_KEEP)   # some cells left bare
    paint = math(nodes, links, "MULTIPLY", dot, keep)
    if not SPECKLES:
        paint = math(nodes, links, "MULTIPLY", paint, 0.0)
    mix = nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    links.new(paint, mix.inputs["Factor"])
    mix.inputs["A"].default_value = (0.010, 0.010, 0.011, 1.0)                # black latex
    mix.inputs["B"].default_value = (PAINT, PAINT, PAINT * 0.97, 1.0)         # matte white spray paint
    links.new(mix.outputs["Result"], bs.inputs["Base Color"])
    rough_paint = nodes.new("ShaderNodeMix")                                   # no micro-relief: a smooth sheet
    rough_paint.data_type = "FLOAT"
    links.new(paint, rough_paint.inputs["Factor"])
    rough_paint.inputs["A"].default_value = LATEX_ROUGH
    rough_paint.inputs["B"].default_value = 0.72
    links.new(rough_paint.outputs["Result"], bs.inputs["Roughness"])
    bs.inputs["IOR"].default_value = 1.52
    bs.inputs["Specular IOR Level"].default_value = 0.5
    return mat


def optical_table(sides):
    """Lapped stainless optical-table top with an M6 tapped-hole grid; the edges keep the base black finish."""
    mat, bs = fresh("Lapped stainless optical table top")
    nodes, links = nodes_of(mat)
    coord = nodes.new("ShaderNodeTexCoord").outputs["Object"]
    fine = nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 2600.0
    fine.inputs["Detail"].default_value = 2.0
    links.new(coord, fine.inputs["Vector"])
    # Tapped holes: distance to the nearest grid node in the table plane.
    xyz = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coord, xyz.inputs[0])
    flat = nodes.new("ShaderNodeCombineXYZ")
    for axis, origin in zip((0, 1), HOLE_ORIGIN_M):
        cell = math(nodes, links, "DIVIDE", math(nodes, links, "SUBTRACT", xyz.outputs[axis], origin), HOLE_PITCH_M)
        local = math(nodes, links, "SUBTRACT", math(nodes, links, "FRACT", math(nodes, links, "ADD", cell, 0.5)), 0.5)
        links.new(local, flat.inputs[axis])
    reach = nodes.new("ShaderNodeVectorMath")
    reach.operation = "LENGTH"
    links.new(flat.outputs[0], reach.inputs[0])
    gap = math(nodes, links, "SUBTRACT", HOLE_RADIUS_M / HOLE_PITCH_M, reach.outputs["Value"])
    hole = math(nodes, links, "DIVIDE", gap, 0.012, clamp=True)
    inside = math(nodes, links, "MULTIPLY",
                  math(nodes, links, "LESS_THAN", math(nodes, links, "ABSOLUTE", xyz.outputs[0]), 1.43),
                  math(nodes, links, "LESS_THAN", math(nodes, links, "ABSOLUTE", xyz.outputs[1]), 1.0))
    hole = math(nodes, links, "MULTIPLY", hole, inside)
    color = nodes.new("ShaderNodeMix")
    color.data_type = "RGBA"
    links.new(hole, color.inputs["Factor"])
    color.inputs["A"].default_value = (BOARD_ALBEDO * 0.96, BOARD_ALBEDO * 0.985, BOARD_ALBEDO, 1.0)
    color.inputs["B"].default_value = (0.02, 0.02, 0.02, 1.0)
    links.new(color.outputs["Result"], bs.inputs["Base Color"])
    links.new(math(nodes, links, "SUBTRACT", 1.0, math(nodes, links, "MULTIPLY", hole, 0.7)), bs.inputs["Metallic"])
    rough = math(nodes, links, "MULTIPLY_ADD", fine.outputs["Fac"], 0.12)
    rough.node.inputs[2].default_value = BOARD_ROUGH - 0.06
    links.new(rough, bs.inputs["Roughness"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.06
    bump.inputs["Distance"].default_value = 4e-6
    links.new(fine.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bs.inputs["Normal"])
    kit.add_surface_wear(mat, smudge=0.09, grime=0.05, scratch=0.05, scale=0.6)
    # Top face only: the bevelled edges and sides keep the base black anodized shader.
    edge_bs = nodes.new("ShaderNodeBsdfPrincipled")
    src = kit._principled(sides)
    for name in ("Base Color", "Metallic", "Roughness"):
        edge_bs.inputs[name].default_value = src.inputs[name].default_value
    up = nodes.new("ShaderNodeNewGeometry")
    nz = nodes.new("ShaderNodeSeparateXYZ")
    links.new(up.outputs["Normal"], nz.inputs[0])
    is_top = math(nodes, links, "GREATER_THAN", nz.outputs[2], 0.98)
    mix = nodes.new("ShaderNodeMixShader")
    links.new(is_top, mix.inputs[0])
    links.new(edge_bs.outputs[0], mix.inputs[1])
    links.new(bs.outputs[0], mix.inputs[2])
    out = next(n for n in nodes if n.type == "OUTPUT_MATERIAL")
    links.new(mix.outputs[0], out.inputs["Surface"])
    return mat


def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


HIDE_PREFIXES = ("Rear safety shield", "Safety shield top rail", "Photogate", "Upper photogate cable",
                 "Lower photogate cable", "Release trigger cable", "Camera data cable")
BACKLIGHT_PREFIXES = ("Diffuse LED backlight panel", "LED panel")
DAQ_PREFIXES = ("DAQ", "BNC")
BACKLIGHT_FROM = (0.0, 0.855)      # centre of the base panel assembly, behind the drop axis as seen by the render camera
BACKLIGHT_TO = (0.95, 0.11)        # on the high-speed camera's optical axis, opposite it across the membrane
DAQ_SHIFT = (0.0, 0.46)            # to the back right corner of the table, clear of the moved backlight
LAYOUT = True
WALLS = True                       # plain painted lab walls behind and left of the table hide the busy workshop panorama
WALL_ALBEDO = 0.62
ROOM_PREFIX = "Lab room"
PHYSICAL_PREFIXES = ("304 stainless", "Rubber membrane", "Upper precision clamp ring", "Lower precision clamp ring",
                     "Replaceable clamp insert")


def group(scene, prefixes):
    return [o for o in scene.objects if o.name.startswith(prefixes)]


def tidy_layout(scene):
    """Remove clutter and put the backlight where a backlit high-speed recording needs it.

    Only props that never touch the ball or the membrane are hidden or moved; the drop axis and
    the table area under the ring (where the ball lands without a membrane) stay clear.
    """
    from mathutils import Matrix
    hidden = [o.name for o in group(scene, HIDE_PREFIXES)]
    for o in group(scene, HIDE_PREFIXES):
        o.hide_render = True
    pivot = Matrix.Translation((*BACKLIGHT_FROM, 0.0))
    place = Matrix.Translation((*BACKLIGHT_TO, 0.0)) @ Matrix.Rotation(-np.pi / 2, 4, "Z") @ pivot.inverted()
    moved = []
    for o in group(scene, BACKLIGHT_PREFIXES):
        o.matrix_world = place @ o.matrix_world
        moved.append(o.name)
    shift = Matrix.Translation((*DAQ_SHIFT, 0.0))
    for o in group(scene, DAQ_PREFIXES):
        o.matrix_world = shift @ o.matrix_world
        moved.append(o.name)
    # The panel now faces the camera with its emitting face only; the other faces are its dark housing.
    panel = bpy.data.objects["Diffuse LED backlight panel"]
    led = panel.material_slots[0].material
    mat = led.copy()
    mat.name = "LED backlight, front face only"
    nodes, links = nodes_of(mat)
    out = next(n for n in nodes if n.type == "OUTPUT_MATERIAL")
    front = out.inputs["Surface"].links[0].from_socket
    housing = nodes.new("ShaderNodeBsdfPrincipled")
    housing.inputs["Base Color"].default_value = (0.02, 0.022, 0.025, 1.0)
    housing.inputs["Metallic"].default_value = 0.6
    housing.inputs["Roughness"].default_value = 0.42
    geo = nodes.new("ShaderNodeNewGeometry")
    n = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geo.outputs["Normal"], n.inputs[0])
    facing = math(nodes, links, "LESS_THAN", n.outputs[0], -0.98)
    mix = nodes.new("ShaderNodeMixShader")
    links.new(facing, mix.inputs[0])
    links.new(housing.outputs[0], mix.inputs[1])
    links.new(front, mix.inputs[2])
    links.new(mix.outputs[0], out.inputs["Surface"])
    assign(panel, mat)
    walls = []
    if WALLS:
        paint = kit.diffuse(ROOM_PREFIX + " wall paint", (WALL_ALBEDO, WALL_ALBEDO, WALL_ALBEDO * 0.97), 0.9)
        kit.add_wall_mottling(paint, amount=0.05)
        for name, centre, size in ((" back wall", (-1.0, 2.6, 1.2), (12.0, 0.1, 4.1)),
                                   (" left wall", (-3.6, -0.5, 1.2), (0.1, 6.3, 4.1))):
            walls.append(kit.plain_box(ROOM_PREFIX + name, centre, size, paint).name)
    return {"hidden_props": hidden, "moved_props": moved, "added_walls": walls,
            "backlight_to": BACKLIGHT_TO, "daq_shift": DAQ_SHIFT}


def overlay(scene, look):
    record = {"look": look}
    if look != "lab":
        return record
    changed = {}
    if LAYOUT:
        record["layout_changes"] = tidy_layout(scene)
    membrane = next((o for o in scene.objects if o.name.startswith("Rubber membrane")), None)
    if membrane:
        latex = latex_sheet()
        assign(membrane, latex)
        changed[membrane.name] = latex.name
    table = bpy.data.objects.get(VISIBLE_TABLE)
    if table:
        top = optical_table(table.material_slots[0].material)
        assign(table, top)
        changed[table.name] = top.name
    for node in scene.world.node_tree.nodes:
        if node.type == "BACKGROUND":
            node.inputs["Strength"].default_value = WORLD_STRENGTH
    scene.view_settings.exposure = EXPOSURE
    kit.lens_finish(scene, vignette=0.10, dispersion=0.002)
    record.update({"materials_replaced": changed, "membrane_uv_span_m": MEMBRANE_UV_SPAN_M,
                   **{k.lower(): globals()[k] for k in TUNABLE}})
    return record


def replay_audit(scene, npz):
    """The base saved-scene audit (tools/audit_native_replay.py), run in memory on the overlaid scene."""
    z = np.load(npz, allow_pickle=False)
    membrane = next((o for o in scene.objects if o.name.startswith("Rubber membrane")), None)
    primary = bpy.data.objects.get("304 stainless drop sphere")
    secondary = bpy.data.objects.get("304 stainless pre-positioned sphere")
    presence = ((secondary is not None) == bool(z["second_ball_present"][0])
                and (membrane is not None) == bool(z["membrane_positions"].shape[1])
                and (primary is not None) == bool(z["rigid_body_present"][0]))
    shown = []
    if membrane:
        shown = [m.show_viewport for m in membrane.modifiers]
        for m in membrane.modifiers:
            m.show_viewport = False
    camera = np.array(scene.camera.matrix_world)
    center = vertex = drift = 0.0
    for i in range(96):
        scene.frame_set(i + 1)
        bpy.context.view_layer.update()
        drift = max(drift, float(np.max(np.abs(np.array(scene.camera.matrix_world) - camera))))
        if primary:
            center = max(center, float(np.linalg.norm(np.array(primary.matrix_world.translation) - z["ball_transforms"][i, :3, 3])))
        if secondary:
            center = max(center, float(np.linalg.norm(np.array(secondary.matrix_world.translation) - z["second_ball_transforms"][i, :3, 3])))
        if membrane:
            ev = membrane.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh = ev.to_mesh()
            co = np.empty(len(mesh.vertices) * 3)
            mesh.vertices.foreach_get("co", co)
            vertex = max(vertex, float(np.max(np.linalg.norm(co.reshape(-1, 3) - z["membrane_positions"][i], axis=1))))
            ev.to_mesh_clear()
    if membrane:
        for m, s in zip(membrane.modifiers, shown):
            m.show_viewport = s
    ok = center < 1e-6 and vertex < 1e-5 and drift == 0 and presence
    return dict(frames_checked=96, maximum_ball_center_error_m=center, maximum_native_membrane_vertex_error_m=vertex,
                maximum_camera_matrix_drift=drift, object_presence_matches_cache=bool(presence),
                ball_center_tolerance_m=1e-6, membrane_vertex_tolerance_m=1e-5, native_replay_ok=bool(ok))


def setup_gpu(scene):
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    used = []
    for d in prefs.devices:
        d.use = d.type == "OPTIX"
        if d.use:
            used.append(d.name)
    if len(used) != 1:
        raise RuntimeError(f"Expected exactly one OptiX GPU, got {used}")
    scene.cycles.device = "GPU"
    return used


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--case", required=True, choices=CASES + STAGED_CASES)
    p.add_argument("--case-dir", type=Path, help="saved scene of the case (scene.blend, simulation.npz, artifact_manifest.json, "
                                                  "render_report.json); default: the accepted case")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--frames", default="1-96", help="'a-b'")
    p.add_argument("--stills", type=int, nargs="+", help="render only these frames as PNG stills")
    p.add_argument("--look", choices=("base", "lab"), default="lab")
    p.add_argument("--samples", type=int, default=256)
    p.add_argument("--set", nargs="*", default=[], metavar="NAME=VALUE", help="look-dev override of a tunable constant")
    args = p.parse_args(argv)
    for item in args.set:
        name, value = item.split("=", 1)
        if name not in TUNABLE:
            raise SystemExit(f"Not tunable: {name}")
        globals()[name] = json.loads(value)
    out = args.out.resolve()
    if (DATA / ".work").resolve() not in out.parents:
        raise SystemExit("Write under renders/steel_ball_tensioned_membrane/.work")
    if out.exists():
        raise SystemExit("Choose a fresh output directory")
    case = args.case_dir.resolve() if args.case_dir else ACCEPTED / args.case
    if args.case in STAGED_CASES and not args.case_dir:
        raise SystemExit("A staged case needs --case-dir")
    manifest = {a["path"]: a.get("sha256") for a in json.loads((case / "artifact_manifest.json").read_text())["artifacts"]}
    for name in ("scene.blend", "simulation.npz"):
        if kit.sha256(case / name) != manifest[name]:
            raise SystemExit(f"{name} is not the accepted base artifact of {args.case}")
    out.mkdir(parents=True)
    bpy.ops.wm.open_mainfile(filepath=str(case / "scene.blend"))
    scene = bpy.context.scene
    scene.frame_set(1)
    bpy.context.view_layer.update()
    movable = BACKLIGHT_PREFIXES + DAQ_PREFIXES + (ROOM_PREFIX,) if (LAYOUT and args.look == "lab") else ()
    fixed = lambda: SimpleNamespace(objects=[o for o in scene.objects if not (movable and o.name.startswith(movable))])
    physical = lambda: SimpleNamespace(objects=[o for o in scene.objects if o.name.startswith(PHYSICAL_PREFIXES) or o.type == "CAMERA"])
    before, physical_before = immutable_signature(fixed()), immutable_signature(physical())
    record = overlay(scene, args.look)
    bpy.context.view_layer.update()
    after, physical_after = immutable_signature(fixed()), immutable_signature(physical())
    if before != after or physical_before != physical_after:
        raise SystemExit("The overlay changed geometry, animation, modifiers, transforms or the camera")
    record["signature_scope"] = ("all objects except the moved backlight and DAQ props and the added walls" if movable else "all objects")
    record["physical_and_camera_signature"] = physical_after
    audit = replay_audit(scene, case / "simulation.npz")
    if not audit["native_replay_ok"]:
        raise SystemExit("Replay audit failed: " + json.dumps(audit))
    devices = setup_gpu(scene)
    scene.cycles.samples = args.samples
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.use_persistent_data = True
    first, last = (int(v) for v in args.frames.split("-"))
    started = time.monotonic()
    if args.stills:
        for f in args.stills:
            scene.frame_set(f)
            scene.render.filepath = str(out / f"still_{f:04d}.png")
            bpy.ops.render.render(write_still=True)
    else:
        scene.frame_start, scene.frame_end = first, last
        scene.render.filepath = str(out / "frames" / "####")
        bpy.ops.render.render(animation=True)
    report = json.loads((case / "render_report.json").read_text())
    report.update(status="stills" if args.stills else "complete", frames=len(args.stills) if args.stills else last - first + 1,
                  samples=args.samples, appearance_overlay=record, immutable_scene_signature_before=before,
                  immutable_scene_signature_after=after, native_replay_audit=audit, execution_host=kit.host_record()["host"],
                  worker=kit.host_record(), cycles_devices=devices, local_blender_used=True,
                  wall_seconds=time.monotonic() - started)
    kit.write_json(out / "render_report.json", report)
    kit.write_json(out / "realism_provenance.json", {
        "revision": REVISION if args.look == "lab" else "base_unchanged", "case": args.case, "worker": kit.host_record(),
        "blender": bpy.app.version_string,
        "accepted_scene": str((case / "scene.blend").relative_to(ROOT)) if not args.case_dir else str(case / "scene.blend"),
        "accepted_scene_sha256": manifest["scene.blend"], "simulation_npz_sha256": manifest["simulation.npz"],
        "immutable_scene_signature": after, "native_replay_ok": audit["native_replay_ok"],
        "samples": args.samples, "frames": args.stills or [first, last]})
    print("REALISM_OVERLAY_DONE", args.case, round(time.monotonic() - started, 1), flush=True)


if __name__ == "__main__":
    main()
