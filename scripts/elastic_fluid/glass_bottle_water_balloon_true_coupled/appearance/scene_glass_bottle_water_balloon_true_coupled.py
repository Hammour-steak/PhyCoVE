#!/usr/bin/env python3
"""Render the water-balloon-in-a-jar experiment on a real kitchen island.

Scene: BlenderKit "Modern Living and Kitchen Interior" (dark marble island,
undermount sink, black gooseneck tap).  A ~3 L glass jar stands on the island
beside the sink; the balloon neck is rolled over the jar lip and sealed by a
rubber stopper with a glass feed tube.  The tap is swung toward the jar and a
clear hose runs from its outlet into the feed tube.

Simulation data (sim coordinates, jar axis at x = y = 0) come from the
surface_glass_bottle_water_balloon_true_coupled.py stage. The accepted pour
mode has an open mouth and no feed tube. Every balloon frame carries the
per-vertex areal stretch, so the latex darkens when slack and thins to a
lighter, translucent blue where it is stretched.

Run with Blender 5.1 (the kitchen file was saved by Blender 4.5).
"""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))

import argparse
import json
import math
import sys
sys.dont_write_bytecode = True
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import look_glass_bottle_water_balloon_true_coupled as base  # noqa: E402
from balloon_config import KITCHEN
from overflow_glass_bottle_water_balloon_true_coupled import add_overflow_visuals

COUNTER_TOP_Z = 2.147
JAR_BASE_SIM_Z = 0.100
SIM_ORIGIN = Vector((-0.58, 1.80, COUNTER_TOP_Z - JAR_BASE_SIM_Z))
# Simulated flat bag's wide axis is (0.901, 0.434); turn it broadside to a camera looking along +y.
SIM_YAW = -math.atan2(0.434, 0.901)
TAP_NAME = "Kitchen tap balck"
TAP_POST = Vector((-1.0755, 1.7766, COUNTER_TOP_Z))
TAP_OUTLET = Vector((-1.0759, 1.9956, 2.379))
TAP_SWING = -math.pi / 2.0                       # spout from over the sink to over its right edge
JAR_PROFILE = [                                  # (outer radius, sim z)
    (0.058, 0.100), (0.068, 0.108), (0.072, 0.118), (0.072, 0.225), (0.066, 0.245),
    (0.048, 0.265), (0.034, 0.284), (0.026, 0.304), (0.026, 0.337), (0.031, 0.341),
    (0.031, 0.349), (0.024, 0.353),
]
# Pour mode: the tap pours straight into the open balloon mouth.  The island
# tap is scaled 1.5x about its base (a 38 cm high-arc tap) and swung forward so
# its outlet sits over the jar, which stands on the counter in front of the sink.
POUR_TAP_SCALE = 1.5
POUR_JAR_XY = (-0.7985, 1.60)
POUR_AERATOR_R = 0.0075
POUR_CAMERAS = {
    "front_low": ((-0.62, 0.80, 2.37), (-0.84, 1.62, 2.35), 40.0),
    "front_eye": ((-0.55, 0.70, 2.56), (-0.84, 1.62, 2.34), 38.0),
    "right_three_quarter": ((-0.06, 0.95, 2.46), (-0.88, 1.66, 2.34), 40.0),
    "left_three_quarter": ((-1.66, 0.90, 2.46), (-0.80, 1.64, 2.34), 40.0),
}
CAMERAS = {
    "front_low": ((-0.32, 0.92, 2.36), (-0.58, 1.82, 2.31), 42.0),
    "front_eye": ((-0.25, 0.80, 2.52), (-0.58, 1.82, 2.30), 40.0),
    "right_three_quarter": ((0.22, 1.02, 2.42), (-0.60, 1.84, 2.30), 42.0),
    "left_three_quarter": ((-1.30, 0.92, 2.44), (-0.55, 1.82, 2.30), 40.0),
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--surface-dir", type=Path, required=True)
    p.add_argument("--kitchen", type=Path, default=KITCHEN, help="original accepted BlenderKit kitchen asset")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--scene", type=Path, required=True)
    p.add_argument("--frames", default="1-96")
    p.add_argument("--camera", default="front_low", help="camera name, or 'survey' to render every candidate")
    p.add_argument("--samples", type=int, default=96)
    p.add_argument("--preview", action="store_true")
    p.add_argument("--flow-l-min", type=float, default=4.5, help="tap flow from the pour start (pour mode)")
    p.add_argument("--pour-start-frame", type=int, default=2)
    p.add_argument("--timed-edits-json", type=Path, default=None,
                   help='same schedule the simulator ran: [{"frame": n, "params": {"flow_l_min": q}}]')
    p.add_argument("--mode", choices=("sealed", "pour"), default="pour",
                   help="sealed: hose into a stoppered balloon; pour: tap pours into the open mouth")
    p.add_argument("--without-balloon", action="store_true",
                   help="DELETE balloon (pour mode): no latex balloon or rolled neck; the surfaces hold the water "
                        "collected in the open jar (simulate --without-balloon)")
    return p.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])


def setup_cycles(scene, args):
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 32 if args.preview else args.samples
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.max_bounces = 10
    scene.cycles.transmission_bounces = 12
    scene.cycles.sample_clamp_indirect = 3.0
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            break
        except Exception:
            continue
    for device in prefs.devices:
        device.use = device.type != "CPU"
    scene.cycles.device = "GPU"
    scene.render.resolution_x = 960 if args.preview else 1280
    scene.render.resolution_y = 540 if args.preview else 720
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.use_motion_blur = False


def latex_material():
    """Blue latex whose colour and translucency follow the local areal stretch."""
    mat = bpy.data.materials.new("Stretch-dependent blue latex")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    attr = nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "stretch"
    t = nodes.new("ShaderNodeMapRange")
    t.inputs["From Min"].default_value = 1.0
    t.inputs["From Max"].default_value = 5.0
    links.new(attr.outputs["Fac"], t.inputs["Value"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.004, 0.030, 0.28, 1.0)   # slack latex: thick, deep blue
    ramp.color_ramp.elements[1].color = (0.030, 0.200, 0.80, 1.0)   # stretched latex: thin, lighter
    links.new(t.outputs["Result"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    trans = nodes.new("ShaderNodeMapRange")
    trans.inputs["From Min"].default_value = 1.0
    trans.inputs["From Max"].default_value = 5.0
    trans.inputs["To Min"].default_value = 0.04
    trans.inputs["To Max"].default_value = 0.42
    links.new(attr.outputs["Fac"], trans.inputs["Value"])
    links.new(trans.outputs["Result"], shader.inputs["Transmission Weight"])
    rough = nodes.new("ShaderNodeMapRange")
    rough.inputs["From Min"].default_value = 1.0
    rough.inputs["From Max"].default_value = 5.0
    rough.inputs["To Min"].default_value = 0.34
    rough.inputs["To Max"].default_value = 0.16
    links.new(attr.outputs["Fac"], rough.inputs["Value"])
    links.new(rough.outputs["Result"], shader.inputs["Roughness"])
    base.set_input(shader, "IOR", 1.5)
    base.set_input(shader, "Specular IOR Level", 0.5)
    base.set_input(shader, "Coat Weight", 0.45)
    base.set_input(shader, "Coat Roughness", 0.06)
    base.set_input(shader, "Subsurface Weight", 0.06)
    base.set_input(shader, "Subsurface Radius", (0.02, 0.08, 0.5))
    return mat


PER_FRAME: dict[int, list] = {}


def show_only_on(obj, frame, last_frame):
    """Register a per-frame object.  Visibility is set explicitly before each render
    (hide_render keyframes are not evaluated reliably in Blender 5), and a frame-change
    handler does the same when the saved .blend is played back."""
    PER_FRAME.setdefault(frame, []).append(obj.name)
    obj["pcve_frame"] = frame
    obj.hide_render = True
    obj.hide_viewport = True


def apply_frame_visibility(frame):
    for objs in PER_FRAME.values():
        for name in objs:
            bpy.data.objects[name].hide_render = True
    for name in PER_FRAME.get(frame, []):
        bpy.data.objects[name].hide_render = False


def vertex_areas(verts, faces):
    tri = verts[faces]
    area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    out = np.zeros(len(verts))
    for c in range(3):
        np.add.at(out, faces[:, c], area / 3.0)
    return out


def make_jar(parent, glass, glass_edge):
    segments = 128
    verts, faces = [], []
    for r, z in JAR_PROFILE:
        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            verts.append((r * math.cos(a), r * math.sin(a), z))
    for ring in range(len(JAR_PROFILE) - 1):
        for i in range(segments):
            j = (i + 1) % segments
            a, b = ring * segments + i, (ring + 1) * segments + i
            faces.extend(((a, b, (ring + 1) * segments + j), (a, (ring + 1) * segments + j, ring * segments + j)))
    jar = base.mesh_object("Glass jar", verts, faces, glass)
    jar.parent = parent
    solid = jar.modifiers.new("Glass wall", "SOLIDIFY")
    solid.thickness = 0.003
    solid.offset = -1.0
    bev = jar.modifiers.new("Molded edges", "BEVEL")
    bev.width = 0.0015
    bev.segments = 3
    bottom = base.add_cylinder("Jar base", 0.060, 0.008, (0.0, 0.0, JAR_BASE_SIM_Z + 0.004), glass, 128)
    bottom.parent = parent
    bpy.ops.mesh.primitive_torus_add(major_radius=0.0282, minor_radius=0.0042, major_segments=96,
                                     minor_segments=24, location=(0.0, 0.0, 0.347))
    lip = bpy.context.object
    lip.name = "Jar rolled lip"
    lip.data.materials.append(glass_edge)
    lip.parent = parent
    return jar


def swing_tap(swing=TAP_SWING, scale=1.0):
    """Swivel (and optionally scale) the tap and its children about the base of its
    post; return the new outlet position."""
    tap = bpy.data.objects[TAP_NAME]
    xf = (Matrix.Translation(TAP_POST) @ Matrix.Rotation(swing, 4, "Z") @ Matrix.Scale(scale, 4)
          @ Matrix.Translation(-TAP_POST))
    tap.matrix_world = xf @ tap.matrix_world
    return xf @ TAP_OUTLET


def pour_tap_swing():
    """Swing angle that puts the scaled outlet straight above the jar axis."""
    old = TAP_OUTLET - TAP_POST
    new = Vector((POUR_JAR_XY[0], POUR_JAR_XY[1], 0.0)) - Vector((TAP_POST.x, TAP_POST.y, 0.0))
    return math.atan2(new.y, new.x) - math.atan2(old.y, old.x)


def flow_schedule(args, frame_count):
    """Tap flow (m^3/s) on each frame, as the simulator applied it."""
    changes = {}
    if args.timed_edits_json is not None:
        for item in json.loads(args.timed_edits_json.read_text()):
            changes[int(item["frame"])] = float(item["params"]["flow_l_min"])
    flow, out = args.flow_l_min, {}
    for frame in range(1, frame_count + 1):
        flow = changes.get(frame, flow)
        out[frame] = flow / 60000.0 if frame >= args.pour_start_frame else 0.0
    return out


def tap_stream(name, outlet, top_z, bottom_z, flow, material, rng):
    """Free-falling tap stream from the outlet (or, after the tap closes, the
    falling tail starting at top_z).  It speeds up under gravity and necks down
    so the flow rate is conserved (r ~ v^-1/2, measured from the outlet)."""
    v0 = flow / (math.pi * POUR_AERATOR_R ** 2)
    top = Vector((outlet.x, outlet.y, top_z))
    bottom = Vector((outlet.x, outlet.y, bottom_z))
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = POUR_AERATOR_R
    curve.bevel_resolution = 4
    spline = curve.splines.new("POLY")
    n = 14
    spline.points.add(n - 1)
    wobble = rng.normal(0.0, 0.00035, size=2)
    for k, pt in enumerate(spline.points):
        f = k / (n - 1)
        z = top.z + (bottom.z - top.z) * f
        drop = max(outlet.z - z, 0.0)
        v = math.sqrt(v0 * v0 + 2.0 * 9.81 * drop)
        pt.co = (top.x + wobble[0] * f * f, top.y + wobble[1] * f * f, z, 1.0)
        pt.radius = math.sqrt(v0 / v) * 0.92
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def main() -> None:
    args = parse_args()
    (args.out / "frames").mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    bpy.ops.wm.open_mainfile(filepath=str(args.kitchen))
    scene = bpy.context.scene
    setup_cycles(scene, args)
    # The kitchen file's compositor grades with a Hue Correct node that strips the
    # saturation out of blues (the latex rendered grey).  Pass the image through.
    comp = getattr(scene, "compositing_node_group", None)
    for node in (comp.nodes if comp else []):
        if node.bl_idname == "CompositorNodeHueCorrect":
            node.mute = True

    levels = np.load(args.surface_dir / "water_level.npy")
    if args.without_balloon:
        if args.mode != "pour":
            raise ValueError("--without-balloon is a pour-mode scene")
        frame_count = len(levels)
    else:
        balloon_cache = np.load(args.surface_dir / "balloon_visual.npz")
        frames_v = balloon_cache["outer_vertices"].astype(np.float64)
        faces = balloon_cache["outer_faces"].astype(np.int64)
        frame_count = len(frames_v)
    scene.frame_start, scene.frame_end = 1, frame_count

    # Everything simulated lives in one frame: jar axis at the origin, sim z units.
    sim = bpy.data.objects.new("Simulation frame", None)
    scene.collection.objects.link(sim)
    pour = args.mode == "pour"
    sim.location = (Vector((POUR_JAR_XY[0], POUR_JAR_XY[1], SIM_ORIGIN.z)) if pour else SIM_ORIGIN)
    sim.rotation_euler = (0.0, 0.0, SIM_YAW)

    glass = base.fresnel_glass_material("Jar glass", (0.93, 0.975, 1.0, 1.0), 0.02, 1.47)
    glass_edge = base.fresnel_glass_material("Jar lip glass", (0.88, 0.96, 1.0, 1.0), 0.015, 1.47)
    water = base.glass_material("Water", (0.82, 0.92, 1.0, 1.0), 1.0, 0.02, 1.333)
    silicone = base.glass_material("Clear silicone hose", (0.93, 0.96, 0.97, 1.0), 1.0, 0.16, 1.41)
    rubber = base.micro_surface_material("Gray rubber stopper", (0.055, 0.058, 0.062, 1.0), 0.62, 0.0,
                                         noise_scale=320.0, bump_strength=0.04, bump_distance=0.00012)
    latex = latex_material()
    make_jar(sim, glass, glass_edge)

    # Balloon: one mesh per frame with per-vertex areal stretch (vs. the deflated frame 1).
    # DELETE balloon (--without-balloon): neither the membrane nor its neck rolled over the lip is built.
    if not args.without_balloon:
        if pour:
            top_vertex = len(frames_v[0]) - 1          # stopper-face centre in the sim mesh
            faces = faces[(faces != top_vertex).all(axis=1)]
        area0 = vertex_areas(frames_v[0], faces)
        for frame in range(1, frame_count + 1):
            v = frames_v[frame - 1]
            obj = base.mesh_object(f"Latex balloon {frame:03d}", v, faces, latex)
            obj.parent = sim
            stretch = vertex_areas(v, faces) / np.maximum(area0, 1e-12)
            attr = obj.data.attributes.new("stretch", "FLOAT", "POINT")
            attr.data.foreach_set("value", stretch.astype(np.float32))
            thick = obj.modifiers.new("Latex thickness", "SOLIDIFY")
            thick.thickness = 0.00045
            thick.offset = 1.0
            show_only_on(obj, frame, frame_count)
        bpy.ops.mesh.primitive_torus_add(major_radius=0.0285, minor_radius=0.0040, major_segments=72,
                                         minor_segments=16, location=(0.0, 0.0, 0.3425))
        collar = bpy.context.object
        collar.name = "Balloon neck rolled over jar lip"
        collar.data.materials.append(latex)
        collar.parent = sim

    for frame in range(1, frame_count + 1):
        path = args.surface_dir / "water" / f"water_{frame:04d}.npz"
        if not path.exists():
            continue
        cache = np.load(path)
        if not len(cache["faces"]):
            continue
        obj = base.mesh_object(f"Water {frame:03d}", cache["vertices"], cache["faces"], water)
        obj.parent = sim
        show_only_on(obj, frame, frame_count)
        level = float(levels[frame - 1])
        if not pour and frame >= 2 and level < 0.310:
            rng = np.random.default_rng(frame)
            sway = rng.normal(0.0, 0.0004, size=2)
            stream = base.curve_tube(f"Feed stream {frame:03d}", [
                (0.0, 0.0, 0.312), (sway[0] * 0.5, sway[1] * 0.5, 0.5 * (0.312 + level)),
                (sway[0], sway[1], level - 0.002)], 0.0028, water)
            stream.parent = sim
            show_only_on(stream, frame, frame_count)

    if pour:
        outlet = swing_tap(pour_tap_swing(), POUR_TAP_SCALE)
        bpy.context.view_layer.update()
        flows = flow_schedule(args, frame_count)
        mouth = outlet + Vector((0, 0, -0.002))
        last_open_flow, closed_at = 0.0, None
        for frame in range(2, frame_count + 1):
            level_z = (sim.matrix_world @ Vector((0.0, 0.0, float(levels[frame - 1])))).z - 0.003
            flow = flows[frame]
            if flow > 0.0:
                last_open_flow, closed_at, top_z = flow, None, mouth.z
            elif last_open_flow > 0.0:
                # tap just closed: the detached column keeps falling
                closed_at = frame if closed_at is None else closed_at
                v0 = last_open_flow / (math.pi * POUR_AERATOR_R ** 2)
                tau = (frame - closed_at + 0.5) / 24.0
                top_z = mouth.z - (v0 * tau + 0.5 * 9.81 * tau * tau)
                flow = last_open_flow
            else:
                continue
            if top_z - level_z < 0.004:
                continue
            stream = tap_stream(f"Tap stream {frame:03d}", mouth, top_z, level_z, flow, water,
                                np.random.default_rng(frame))
            show_only_on(stream, frame, frame_count)
    else:
        # Stopper and feed tube (sim frame)
        bpy.ops.mesh.primitive_cone_add(vertices=96, radius1=0.0200, radius2=0.0262, depth=0.031,
                                        location=(0.0, 0.0, 0.336 + 0.0155))
        stopper = bpy.context.object
        stopper.name = "Rubber stopper"
        stopper.data.materials.append(rubber)
        stopper.parent = sim
        tube_top = 0.336 + 0.045
        tube_len = tube_top - 0.312
        for name, radius, mat in (("Glass feed tube", 0.0050, glass_edge), ("Water in feed tube", 0.0038, water)):
            obj = base.add_cylinder(name, radius, tube_len, (0.0, 0.0, 0.312 + tube_len / 2.0), mat, 48)
            obj.parent = sim

        # Tap swung toward the jar; hose from its outlet into the feed tube.
        outlet = swing_tap()
        tube_top_world = sim.matrix_world @ Vector((0.0, 0.0, tube_top))
        bpy.context.view_layer.update()
        tube_top_world = sim.matrix_world @ Vector((0.0, 0.0, tube_top))
        # A soft hose: drops from the outlet, sags between tap and jar, and bends
        # gently down into the feed tube.
        run = tube_top_world - outlet
        run.z = 0.0
        low = min(outlet.z, tube_top_world.z) - 0.055
        hose_path = [tuple(outlet + Vector((0, 0, -0.004))),
                     tuple(outlet + run * 0.18 + Vector((0, 0, low - outlet.z + 0.025))),
                     tuple(outlet + run * 0.50 + Vector((0, 0, low - outlet.z))),
                     tuple(outlet + run * 0.86 + Vector((0, 0, tube_top_world.z - outlet.z + 0.010))),
                     tuple(tube_top_world + Vector((0, 0, -0.008)))]
        base.curve_tube("Clear fill hose", hose_path, 0.0062, silicone)
        base.curve_tube("Water in fill hose", hose_path, 0.0044, water)
        bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=0.0072, radius2=0.0105, depth=0.014,
                                        location=tuple(outlet + Vector((0, 0, -0.003))))
        adapter = bpy.context.object
        adapter.name = "Hose adapter on tap outlet"
        adapter.data.materials.append(silicone)

    if pour:
        add_overflow_visuals(args,sim,water,JAR_PROFILE,COUNTER_TOP_Z,frame_count,show_only_on)

    cameras = POUR_CAMERAS if pour else CAMERAS
    names = list(cameras) if args.camera == "survey" else [args.camera]
    rendered = []
    frame_list = ([int(f) for f in args.frames.split(",")] if "," in args.frames
                  else list(range(*[int(v) + k for k, v in enumerate(args.frames.split("-"))]))
                  if "-" in args.frames else [int(args.frames)])
    for name in names:
        loc, target, lens = cameras[name]
        cam = bpy.data.objects.new(f"Camera {name}", bpy.data.cameras.new(name))
        scene.collection.objects.link(cam)
        cam.location = loc
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = lens
        cam.data.dof.use_dof = True
        cam.data.dof.focus_distance = (Vector(target) - Vector(loc)).length
        cam.data.dof.aperture_fstop = 5.6
        scene.camera = cam
        for frame in frame_list:
            scene.frame_set(frame)
            apply_frame_visibility(frame)
            suffix = f"{name}_" if len(names) > 1 else ""
            scene.render.filepath = str(args.out / "frames" / f"{suffix}frame_{frame:04d}.png")
            bpy.ops.render.render(write_still=True)
            rendered.append((name, frame))
    args.scene.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.scene))
    report = {"cameras": names, "frames": frame_list, "rendered": len(rendered),
              "seconds": time.monotonic() - start, "tap_outlet_world": list(outlet)}
    (args.out / "render_report.json").write_text(json.dumps(report, indent=1))
    print("RENDER_COMPLETE", json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
