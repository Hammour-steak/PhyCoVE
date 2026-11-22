"""Current look of elastic_key_strap: a daylit entryway around the native replay.

    blender -b --factory-startup --python appearance/realism.py -- --case CASE --cache-dir DIR --out DIR
        [--samples 384] [--device CPU|OPTIX|CUDA] [--frames F ...]

render_elastic_key_strap.py launches this. appearance/render_scene.py build_scene() makes the moving parts
(keyring, keys, strap shell, key tag), the key rack, the cabinet, the wall plane and the fixed camera from the
native solve; this file replaces the room, the light and the dressing, bakes the 96 native states into keyframes
and shape keys (Cycles motion blur then sees the real motion between frames), checks every frame against the
cache before it is rendered and writes frame_0001..0096.png, native_replay_audit.json,
appearance_scene_audit.json and realism_provenance*.json. Nothing here reads or writes solver state.
"""
import argparse
import hashlib
import json
import math
import os
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASE_DIR = HERE.parent
SCRIPTS = CASE_DIR.parents[1]
REPO = SCRIPTS.parent
sys.path[:0] = [str(HERE), str(CASE_DIR), str(SCRIPTS)]

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Quaternion, Vector  # noqa: E402
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402

import render_scene as base  # noqa: E402
import pcve_realism_kit as kit  # noqa: E402
from pcve_assets import asset  # noqa: E402

LOOK = "daylit_entryway"
FRAMES = 96
SHUTTER = 0.25
# Swept volume of every case (keys, ring, tag, strap; the fall onto the cabinet in remove_strap and the
# soft-strap contact included): x -0.035..0.064, y 0.036..0.150, z 0.860..1.280, plus margins.
KEEPOUT = ((-0.08, -0.02, 0.855), (0.11, 0.19, 1.33))
WALL_Y, CABINET_Z = 0.205, 0.860
ROOM = dict(x_min=-0.92, x_max=1.60, y_min=-2.20, z_ceil=2.40)
WINDOW = dict(y0=-1.85, y1=-0.40, z0=0.85, z1=2.20)
MULLION_Y = -1.60  # fixed narrow pane beside a wide casement; its shadow lands at the right edge of the frame
# Late-afternoon sun entering the side window: travel direction (x, y, z).
SUN_DIRECTION = (0.585, 0.750, -0.310)
SUN_STRENGTH, WORLD_STRENGTH, EXPOSURE = 3.0, 1.5, 0.3
REMOVED = ("tray_asset_root", "Small receipt in tray", "Room ceiling bounce", "Room right wall bounce",
           "Room floor bounce", "Left wall below window", "Left wall above window", "Left wall before window",
           "Left wall behind window", "Off-camera vertical window frame", "Off-camera horizontal window frame",
           "Off-camera window transom", "Afternoon sun through side window", "Cool daylight through tall side window",
           "Warm reflected hallway light")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rel(path):
    path = Path(path).resolve()
    return str(path.relative_to(REPO)) if REPO in path.parents else str(path)


def remove_base_items():
    gone = []
    for name in REMOVED:
        for obj in [o for o in bpy.data.objects if o.name == name or o.name.startswith(name + ".")]:
            for child in list(obj.children_recursive):
                bpy.data.objects.remove(child, do_unlink=True)
            bpy.data.objects.remove(obj, do_unlink=True)
            gone.append(name)
    return sorted(set(gone))


def principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def noise(nodes, links, scale, detail=4.0, roughness=0.55, coord="Object"):
    tc = nodes.new("ShaderNodeTexCoord")
    tex = nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = scale
    tex.inputs["Detail"].default_value = detail
    tex.inputs["Roughness"].default_value = roughness
    links.new(tc.outputs[coord], tex.inputs["Vector"])
    return tex


def wall_paint():
    """Warm white emulsion over plaster: scanned plaster relief, roller-lap tone drift, faint grime low down."""
    mat = bpy.data.materials["Warm mineral white, rolled matte emulsion"]
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = principled(mat)
    mix = bs.inputs["Base Color"].links[0].from_node
    mix.inputs[2].default_value = (0.74, 0.715, 0.665, 1)
    broad = noise(nodes, links, 1.3, 6.0)
    tone = nodes.new("ShaderNodeMapRange")
    tone.inputs["From Min"].default_value, tone.inputs["From Max"].default_value = 0.30, 0.70
    tone.inputs["To Min"].default_value, tone.inputs["To Max"].default_value = 0.955, 1.03
    links.new(broad.outputs["Fac"], tone.inputs["Value"])
    scale = nodes.new("ShaderNodeVectorMath")
    scale.operation = "SCALE"
    links.new(mix.outputs[0], scale.inputs[0])
    links.new(tone.outputs[0], scale.inputs["Scale"])
    links.new(scale.outputs[0], bs.inputs["Base Color"])
    return mat


def room_shell():
    """Closed room: daylight enters only through the side window, so the wall falls off away from it."""
    wall = kit.diffuse("Room walls, warm white emulsion", (0.70, 0.68, 0.63), 0.86)
    ceiling = kit.diffuse("Room ceiling, flat white", (0.80, 0.79, 0.76), 0.9)
    floor = kit.diffuse("Room floor, oiled oak boards", (0.33, 0.23, 0.14), 0.55)
    frame = kit.diffuse("Window frame, painted timber", (0.72, 0.71, 0.67), 0.45)
    x0, x1, y0, z1 = ROOM["x_min"], ROOM["x_max"], ROOM["y_min"], ROOM["z_ceil"]
    wy0, wy1, wz0, wz1 = WINDOW["y0"], WINDOW["y1"], WINDOW["z0"], WINDOW["z1"]
    t = 0.14  # real wall thickness gives the window a reveal
    yb = WALL_Y + 0.03
    xw = x0 - t / 2
    made = [
        kit.plain_box("Room floor", ((x0 + x1) / 2, (y0 + yb) / 2, -0.03), (x1 - x0 + 0.4, yb - y0 + 0.4, 0.06), floor),
        kit.plain_box("Room ceiling", ((x0 + x1) / 2, (y0 + yb) / 2, z1 + 0.03), (x1 - x0 + 0.4, yb - y0 + 0.4, 0.06), ceiling),
        kit.plain_box("Room right wall", (x1 + 0.03, (y0 + yb) / 2, z1 / 2), (0.06, yb - y0, z1), wall),
        kit.plain_box("Room front wall", ((x0 + x1) / 2, y0 - 0.03, z1 / 2), (x1 - x0 + 0.4, 0.06, z1), wall),
        kit.plain_box("Room back wall masonry", ((x0 + x1) / 2, yb + 0.02, z1 / 2), (x1 - x0 + 0.4, 0.04, z1 + 0.1), wall),
        kit.plain_box("Window wall below", (xw, (y0 + yb) / 2, wz0 / 2), (t, yb - y0, wz0), wall),
        kit.plain_box("Window wall above", (xw, (y0 + yb) / 2, (wz1 + z1) / 2), (t, yb - y0, z1 - wz1), wall),
        kit.plain_box("Window wall near", (xw, (y0 + wy0) / 2, (wz0 + wz1) / 2), (t, wy0 - y0, wz1 - wz0), wall),
        kit.plain_box("Window wall far", (xw, (wy1 + yb) / 2, (wz0 + wz1) / 2), (t, yb - wy1, wz1 - wz0), wall),
        kit.plain_box("Window outer frame head", (x0 - 0.035, (wy0 + wy1) / 2, wz1 - 0.03), (0.07, wy1 - wy0, 0.06), frame),
        kit.plain_box("Window outer frame sill", (x0 - 0.035, (wy0 + wy1) / 2, wz0 + 0.03), (0.07, wy1 - wy0, 0.06), frame),
        kit.plain_box("Window outer frame near jamb", (x0 - 0.035, wy0 + 0.03, (wz0 + wz1) / 2), (0.07, 0.06, wz1 - wz0), frame),
        kit.plain_box("Window outer frame far jamb", (x0 - 0.035, wy1 - 0.03, (wz0 + wz1) / 2), (0.07, 0.06, wz1 - wz0), frame),
        kit.plain_box("Window mullion", (x0 - 0.035, MULLION_Y, (wz0 + wz1) / 2), (0.06, 0.05, wz1 - wz0), frame),
    ]
    return [o.name for o in made]


def daylight(scene):
    """Sky panorama seen through the window (its sun turned away from the window), a sun lamp for the
    direct patch, and a light portal in the window opening so Cycles samples the sky where it enters."""
    hdr = asset("polyhaven/kloofendal_48d_partly_cloudy_puresky/kloofendal_48d_partly_cloudy_puresky_2k.hdr")
    world = scene.world
    nodes, links = world.node_tree.nodes, world.node_tree.links
    nodes.clear()
    env = nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(hdr), check_existing=True)
    width, height = env.image.size
    px = np.empty(width * height * 4, dtype=np.float32)
    env.image.pixels.foreach_get(px)
    lum = px.reshape(height, width, 4)[..., :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    _, u = np.unravel_index(int(np.argmax(lum)), lum.shape)
    # Cycles equirectangular lookup: u = (pi - atan2(y, x)) / (2 pi)
    a = math.pi - 2 * math.pi * (u + 0.5) / width
    sun_tex_az = math.atan2(math.sin(a), math.cos(a))
    wanted_az = math.atan2(-0.35, 1.0)  # panorama sun behind the solid +x wall, never through the window
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, sun_tex_az - wanted_az)
    coord = nodes.new("ShaderNodeTexCoord")
    links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    bg = nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = WORLD_STRENGTH
    out = nodes.new("ShaderNodeOutputWorld")
    links.new(env.outputs["Color"], bg.inputs["Color"])
    links.new(bg.outputs[0], out.inputs["Surface"])
    sun = kit.sun("Late afternoon sun through the side window", SUN_DIRECTION, SUN_STRENGTH, angle_deg=0.55, color=(1.0, 0.90, 0.78))
    portal = bpy.data.lights.new("Window light portal", "AREA")
    portal.shape = "RECTANGLE"
    portal.size = WINDOW["y1"] - WINDOW["y0"]
    portal.size_y = WINDOW["z1"] - WINDOW["z0"]
    portal.cycles.is_portal = True
    pobj = bpy.data.objects.new(portal.name, portal)
    scene.collection.objects.link(pobj)
    pobj.location = (ROOM["x_min"] - 0.01, (WINDOW["y0"] + WINDOW["y1"]) / 2, (WINDOW["z0"] + WINDOW["z1"]) / 2)
    pobj.rotation_euler = Vector((1, 0, 0)).to_track_quat("-Z", "Z").to_euler()
    return {"world": rel(hdr), "world_strength": WORLD_STRENGTH, "world_rotation_z_rad": sun_tex_az - wanted_az,
            "panorama_sun_azimuth_rad": sun_tex_az, "sun_direction": list(SUN_DIRECTION), "sun_strength_w_m2": SUN_STRENGTH,
            "sun_angle_deg": 0.55, "portal": {"location": list(pobj.location), "size_m": [portal.size, portal.size_y]}}


def resting(members, label, tolerance=0.012, inset=0.15):
    """Fail if a prop's footprint hangs off the cabinet top it stands on (five downward rays)."""
    low, high = kit.world_bbox(members)
    for m in members:
        m.hide_viewport = True
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    try:
        for fx, fy in ((.5, .5), (inset, inset), (1 - inset, inset), (inset, 1 - inset), (1 - inset, 1 - inset)):
            origin = Vector((low.x + (high.x - low.x) * fx, low.y + (high.y - low.y) * fy, low.z + tolerance))
            hit, point, *_ = bpy.context.scene.ray_cast(graph, origin, Vector((0, 0, -1)))
            if not hit or abs(point.z - low.z) > tolerance:
                raise RuntimeError(f"{label} overhangs at {fx},{fy}")
    finally:
        for m in members:
            m.hide_viewport = False
        bpy.context.view_layer.update()


def place(model, label, location, rot_z=0.0, scale=1.0, rests=True, keepout=KEEPOUT):
    folder = asset(f"polyhaven/{model}")
    path = next(folder.glob("*.gltf"))
    root, members = kit.import_prop(path, "Dressing " + label, location, rot_z, scale=scale)
    if rests:
        resting(members, label)
    record = kit.assert_clear(members, keepout, label) if keepout else {"label": label}
    record.update(asset=f"polyhaven/{model}", scale=scale)
    return root, members, record


def hang_frame(model, label, centre_x, centre_z, scale):
    """A framed print hung flat on the wall: artwork faces the camera, back 4 mm off the paint."""
    root, members, _ = place(model, label, (0, 0, 0), 0.0, scale, rests=False, keepout=None)
    normal = Vector()
    for obj in members:
        if obj.type != "MESH":
            continue
        for poly in obj.data.polygons:
            name = obj.material_slots[poly.material_index].name if obj.material_slots else ""
            if "artwork" in name.lower():
                normal += (obj.matrix_world.to_3x3() @ poly.normal) * poly.area
    if normal.length == 0:
        raise RuntimeError(f"{model}: no artwork faces found")
    if normal.y > 0:  # turn the print to face -y (the room)
        root.rotation_euler[2] += math.pi
    glass = bpy.data.materials.new("Picture glass, thin float glass")
    glass.use_nodes = True
    gn, gl = glass.node_tree.nodes, glass.node_tree.links
    gn.clear()
    clear, gloss = gn.new("ShaderNodeBsdfTransparent"), gn.new("ShaderNodeBsdfGlossy")
    gloss.inputs["Roughness"].default_value = 0.03
    fresnel = gn.new("ShaderNodeFresnel")
    fresnel.inputs["IOR"].default_value = 1.52
    mix, out = gn.new("ShaderNodeMixShader"), gn.new("ShaderNodeOutputMaterial")
    gl.new(fresnel.outputs[0], mix.inputs[0])
    gl.new(clear.outputs[0], mix.inputs[1])
    gl.new(gloss.outputs[0], mix.inputs[2])
    gl.new(mix.outputs[0], out.inputs["Surface"])
    for obj in members:  # the model's glass slot has no texture of its own; a thin clear pane instead
        for slot in getattr(obj, "material_slots", []):
            if slot.material and "glass" in slot.material.name.lower():
                slot.material = glass
    bpy.context.view_layer.update()
    low, high = kit.world_bbox(members)
    root.location += Vector((centre_x - (low.x + high.x) / 2, WALL_Y - 0.004 - high.y, centre_z - (low.z + high.z) / 2))
    bpy.context.view_layer.update()
    return kit.assert_clear(members, KEEPOUT, label) | {"asset": f"polyhaven/{model}", "scale": scale}


def solid_hooks(c):
    """Solid steel hooks instead of thin wire on the rack.

    The base scene draws each hook as a 3.6 mm wire on the J centreline that the strap eyelet hangs in
    (bottom of the J at y 0.090, z 1.283, i.e. at the strap's pinned top edge). The centreline is kept;
    the rod becomes 5 mm round steel with a ball tip, it leaves the board through an 18 mm base plate with
    two small screws, and the strap's moulded eyelet is resized so its hole rests on the thicker rod. The
    per-hook screws above the hooks become two board mounting screws at the ends of the rack.
    """
    steel = bpy.data.materials["Brushed stainless steel"]
    principled(steel).inputs["Base Color"].default_value = (0.56, 0.57, 0.58, 1)
    rod_r, plate_r = 0.0025, 0.009
    made = []
    for hook in [o for o in bpy.data.objects if o.name.startswith("Fixed metal hook")]:
        hook.data.bevel_depth = rod_r
        hook.data.bevel_resolution = 6
        hook.data.use_fill_caps = True
        tip = hook.matrix_world @ hook.data.splines[0].bezier_points[-1].co
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=14, radius=rod_r * 1.3, location=tip)
        ball = bpy.context.object
        ball.name = "Hook ball tip"
        ball.data.materials.append(steel)
        made.append(ball.name)
    for obj in [o for o in bpy.data.objects if o.name.startswith("Rack screw")]:
        bpy.data.objects.remove(obj, do_unlink=True)
    screw_mat = steel
    def head(name, loc, r):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=10, radius=r, location=loc)
        o = bpy.context.object
        o.name = name
        o.scale = (1, 0.32, 1)
        o.data.materials.append(screw_mat)
        for poly in o.data.polygons:
            poly.use_smooth = True
        made.append(o.name)
    for x in (-0.14, 0.0, 0.14):
        bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=plate_r, depth=0.003, location=(x, 0.1712, 1.3230),
                                            rotation=(math.pi / 2, 0, 0))
        plate = bpy.context.object
        plate.name = "Hook base plate"
        plate.data.materials.append(steel)
        base.bevel(plate, 0.0009, 3)
        for poly in plate.data.polygons:
            poly.use_smooth = True
        made.append(plate.name)
        for dz in (0.0062, -0.0062):
            head("Hook plate screw", (x, 0.1697, 1.3230 + dz), 0.0014)
    for x in (-0.205, 0.205):
        head("Rack mounting screw", (x, 0.1722, 1.315), 0.0032)
    eyelet = bpy.data.objects.get("Reinforced strap eyelet")
    if eyelet is not None:
        material = eyelet.data.materials[0]
        bpy.data.objects.remove(eyelet, do_unlink=True)
        hole = 0.0033
        centre_z = 1.283 + rod_r - hole  # the hole's top edge rests on the rod
        bpy.ops.mesh.primitive_torus_add(major_radius=hole + 0.0009, minor_radius=0.0009, major_segments=64,
                                         minor_segments=12, location=(0.0, 0.090, centre_z), rotation=(math.pi / 2, 0, 0))
        ring = bpy.context.object
        ring.name = "Reinforced strap eyelet"
        ring.data.materials.append(material)
        for poly in ring.data.polygons:
            poly.use_smooth = True
        made.append(ring.name)
        if centre_z - hole - 0.0018 > c["anchor_m"][2] + 0.001:
            raise RuntimeError("eyelet no longer reaches the strap's top edge")
    return made


def bake_motion(cache, roots, shell, c):
    """Native state f-1 at frame f: linear keyframes for the rigid roots, one shape key per frame for the strap."""
    scene = bpy.context.scene
    names = [str(n) for n in cache["body_names"]]
    for i, name in enumerate(names):
        root = roots[name]
        previous = None
        for f in range(1, FRAMES + 1):
            q = Quaternion(cache["body_quaternions"][f - 1, i])
            if previous is not None and previous.dot(q) < 0:
                q.negate()
            previous = q
            root.location = cache["body_positions"][f - 1, i]
            root.rotation_quaternion = q
            root.keyframe_insert("location", frame=f)
            root.keyframe_insert("rotation_quaternion", frame=f)
        for curve in root.animation_data.action.fcurves:
            for key in curve.keyframe_points:
                key.interpolation = "LINEAR"
    if shell is not None:
        shell.shape_key_add(name="Basis", from_mix=False)
        blocks = []
        for f in range(1, FRAMES + 1):
            vv, _ = base.shell_geometry(cache["strap_vertices"][f - 1], cache["triangles"], cache["reference"],
                                        c["strap_thickness_m"])
            block = shell.shape_key_add(name=f"state_{f - 1:03d}", from_mix=False)
            block.data.foreach_set("co", vv.astype(np.float32).ravel())
            blocks.append(block)
        for f, block in enumerate(blocks, start=1):
            for frame, value in ((f - 1, 0.0), (f, 1.0), (f + 1, 0.0)):
                if f == 1 and frame == 0:
                    value = 1.0
                if f == FRAMES and frame == FRAMES + 1:
                    value = 1.0
                block.value = value
                block.keyframe_insert("value", frame=frame)
        for curve in shell.data.shape_keys.animation_data.action.fcurves:
            for key in curve.keyframe_points:
                key.interpolation = "LINEAR"
    scene.frame_start, scene.frame_end = 1, FRAMES
    return {"rigid_keyframes": len(names) * FRAMES, "strap_shape_keys": FRAMES if shell is not None else 0}


def check_frame(scene, cache, roots, shell, f):
    """Evaluated scene at frame f against native state f-1 (positions, orientations, strap mid-surface)."""
    scene.frame_set(f)
    i = f - 1
    err_p = err_q = err_s = 0.0
    for k, name in enumerate(str(n) for n in cache["body_names"]):
        mw = roots[name].matrix_world
        err_p = max(err_p, float(np.abs(np.array(mw.translation) - cache["body_positions"][i, k]).max()))
        w, x, y, z = cache["body_quaternions"][i, k] / np.linalg.norm(cache["body_quaternions"][i, k])
        r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                      [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                      [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])
        err_q = max(err_q, float(np.abs(np.array(mw.to_3x3()) - r).max()))
    if shell is not None:
        graph = bpy.context.evaluated_depsgraph_get()
        ev = shell.evaluated_get(graph)
        mesh = ev.to_mesh()
        co = np.empty(len(mesh.vertices) * 3)
        mesh.vertices.foreach_get("co", co)
        ev.to_mesh_clear()
        co = co.reshape(-1, 3)
        n = len(cache["reference"])
        err_s = float(np.abs((co[:n] + co[n:]) / 2 - cache["strap_vertices"][i]).max())
    if err_p > 2e-6 or err_s > 2e-6 or err_q > 2e-6:
        raise RuntimeError(f"frame {f}: scene differs from the native state ({err_p:.3g} m, {err_q:.3g}, {err_s:.3g} m)")
    return err_p, err_q, err_s


def camera_record(scene):
    cam = scene.camera
    return {"matrix_world": list(np.array(cam.matrix_world).ravel()), "lens": cam.data.lens,
            "sensor_width": cam.data.sensor_width, "sensor_fit": cam.data.sensor_fit,
            "shift_x": cam.data.shift_x, "shift_y": cam.data.shift_y,
            "clip_start": cam.data.clip_start, "clip_end": cam.data.clip_end,
            "width": scene.render.resolution_x, "height": scene.render.resolution_y}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--case", required=True)
    a.add_argument("--cache-dir", type=Path, required=True)
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--samples", type=int, default=384)
    a.add_argument("--device", default="CPU", choices=("CPU", "OPTIX", "CUDA"))
    a.add_argument("--frames", type=int, nargs="+")
    args = a.parse_args(sys.argv[sys.argv.index("--") + 1:])
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    cache_path = args.cache_dir / "simulation.npz"
    cache = dict(np.load(cache_path))
    c = json.loads((args.cache_dir / "resolved_config.json").read_text())
    import edit_vocab
    expected = dict(edit_vocab.BASELINE)
    expected.update(edit_vocab.override_for(args.case))
    if c != expected:
        raise RuntimeError(f"{args.cache_dir} does not hold the parameters of case {args.case}")

    scene, roots, shell, devices = base.build_scene(cache, c, args.device)
    removed = remove_base_items()
    room = room_shell()
    light = daylight(scene)
    wall_paint()
    rosettes = solid_hooks(c)
    principled(bpy.data.materials["Moulded sage silicone"]).inputs["Base Color"].default_value = (0.10, 0.27, 0.19, 1)
    kit.add_surface_wear(bpy.data.materials["Fine oak veneer, satin oil finish"], smudge=0.05, grime=0.05, scratch=0.04, scale=0.5)
    dressing = [
        place("potted_plant_04", "aloe in a glazed pot", (-0.31, 0.10, CABINET_Z), 0.6)[2],
        place("wooden_bowl_02", "wooden catch-all bowl", (0.27, 0.12, CABINET_Z), 0.4)[2],
        hang_frame("hanging_picture_frame_02", "framed photograph", -0.455, 1.165, 0.5),
    ]

    # Render settings: the base scene keeps its seed, adaptive threshold, bounces, camera and DOF.
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    scene.cycles.sample_clamp_indirect = 6.0
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = SHUTTER
    scene.render.use_persistent_data = False  # Blender 4.3: persistent data with motion blur drops settled objects
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = EXPOSURE
    kit.lens_finish(scene)
    baked = bake_motion(cache, roots, shell, c)

    frames = args.frames or list(range(1, FRAMES + 1))
    worst = [0.0, 0.0, 0.0]
    bounds = []
    for f in range(1, FRAMES + 1):
        e = check_frame(scene, cache, roots, shell, f)
        worst = [max(x, y) for x, y in zip(worst, e)]
        pts = [o.matrix_world @ Vector(v) for r in roots.values() for o in r.children if o.type == "MESH" for v in o.bound_box]
        if shell is not None:
            pts += [Vector(v) for v in cache["strap_vertices"][f - 1]]
        ndc = np.array([tuple(world_to_camera_view(scene, scene.camera, p)) for p in pts])
        bounds.append([float(ndc[:, 0].min()), float(ndc[:, 1].min()), float(ndc[:, 0].max()), float(ndc[:, 1].max())])
    replay = {"camera": camera_record(scene), "rigid_position_max_error_m": worst[0],
              "rigid_rotation_matrix_max_error": worst[1], "shell_mid_surface_max_error_m": worst[2],
              "screen_bounds_96_frames": bounds, "native_time_range_s": [float(cache["times"][0]), float(cache["times"][FRAMES - 1])],
              "sampling": "frame f shows native state f-1 (t = (f-1)/24 s)", "retiming": False, "motion_smoothing": False,
              "motion_blur": {"shutter_frames": SHUTTER, "between_states": "linear interpolation of consecutive native states"},
              "pose_edit": False}
    kit.write_json(out / "native_replay_audit.json", replay)
    kit.write_json(out / "appearance_scene_audit.json", {
        "look": LOOK, "removed_base_items": removed, "room": room, "light": light, "hooks": rosettes,
        "dressing": dressing, "keepout_m": KEEPOUT, "wall_plane_y_m": WALL_Y, "cabinet_top_z_m": CABINET_Z,
        "view_transform": scene.view_settings.view_transform, "look_transform": scene.view_settings.look,
        "exposure": scene.view_settings.exposure, "baked_motion": baked})

    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    gpu = None
    if args.device != "CPU" and visible:
        gpu = subprocess.run(["nvidia-smi", "-i", visible, "--query-gpu=name,uuid,driver_version", "--format=csv,noheader"],
                             capture_output=True, text=True).stdout.strip()
    provenance = {
        "scene": "elastic_key_strap", "case": args.case, "look": LOOK, "frames": [min(frames), max(frames), len(frames)],
        "frame_list": frames, "native_cache": rel(cache_path), "native_cache_sha256": sha256(cache_path),
        "render": {"engine": "Cycles", "device": args.device, "cycles_devices": devices, "gpu": gpu,
                   "host": socket.gethostname(), "blender": bpy.app.version_string, "samples": args.samples,
                   "adaptive_threshold": scene.cycles.adaptive_threshold, "seed": scene.cycles.seed,
                   "denoiser": "OpenImageDenoise (albedo + normal)", "motion_blur_shutter": SHUTTER,
                   "persistent_data": False, "resolution": [scene.render.resolution_x, scene.render.resolution_y],
                   "fps": scene.render.fps, "view_transform": "AgX", "look": scene.view_settings.look},
        "replay_max_error": {"rigid_position_m": worst[0], "rigid_rotation_matrix": worst[1],
                             "strap_mid_surface_m": worst[2]}}
    name = "realism_provenance.json" if len(frames) == FRAMES else f"realism_provenance_f{min(frames):04d}_{max(frames):04d}.json"
    kit.write_json(out / name, provenance)
    for f in frames:
        scene.frame_set(f)
        scene.render.filepath = str(out / f"frame_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        print(f"RENDERED {args.case} frame {f}", flush=True)


if __name__ == "__main__":
    main()
