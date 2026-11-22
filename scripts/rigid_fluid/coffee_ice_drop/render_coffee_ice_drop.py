"""Blender 4.3: render one simulated case in the restaurant stage.

usage: blender -b loft_restaurant_stage.blend --python render_coffee_ice_drop.py -- <run_dir> <ice_asset.blend> <frames_dir>
       [samples] [frames "1,2,.."|""] [distance m] [target z] [mesh dir] [blur|noblur] [clear|frosted] [core density 1/m]
Hides the stage's authored coffee and its placeholder ice cube, places the camera (30 degrees down, 58 mm, 0.50 m from the cup),
swaps in the per-frame coffee surface and drop films, drives the BlenderKit ice (volume-matched to the simulated cube,
clear with a cloudy core) and renders Cycles PNGs. LOOK_* environment variables override look parameters (tests)."""
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
import argparse, json, os, shutil, sys
from pathlib import Path

parser = argparse.ArgumentParser(description="Render one simulated coffee_ice_drop case in the restaurant stage (Blender, arguments after --).")
parser.add_argument("run", type=Path, help="simulation run directory (sim_log.json and the surface step's output)")
parser.add_argument("ice_asset", type=Path, help="BlenderKit realistic ice cube .blend")
parser.add_argument("out_dir", type=Path, help="directory for frame_####.png")
parser.add_argument("samples", type=int, nargs="?", default=128)
parser.add_argument("frames", nargs="?", default="", help='comma-separated frame numbers; "" renders every frame')
parser.add_argument("distance", type=float, nargs="?", default=0.50, help="camera distance from the target (m)")
parser.add_argument("target_z", type=float, nargs="?", default=0.862, help="world z of the camera target on the cup axis (m)")
parser.add_argument("mesh_dir", nargs="?", default="surfaces", help="subdirectory of the run with coffee_####.npz")
parser.add_argument("blur", nargs="?", choices=("blur", "noblur"), default="blur", help="180-degree motion blur")
parser.add_argument("ice_look", nargs="?", choices=("clear", "frosted"), default="clear")
parser.add_argument("core_density", type=float, nargs="?", default=6000.0, help="scattering density of the clear ice's cloudy core (1/m)")
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
run, ice_asset, out_dir = args.run, args.ice_asset, args.out_dir
samples = args.samples
frames = [int(x) for x in args.frames.split(",")] if args.frames else None
distance, target_z, mesh_dir = args.distance, args.target_z, args.mesh_dir
motion_blur = args.blur == "blur"

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
# look parameters (environment overrides): coffee absorption density (1/m) and transmission colour, optional brown
# in-scatter, and the ice's cloudy core (density 1/m, inner/outer edge as a fraction of the half size)
coffee_absorption = float(os.environ.get("LOOK_COFFEE_ABS", 1500.0))
coffee_abs_color = tuple(float(x) for x in os.environ.get("LOOK_COFFEE_COLOR", "0.65,0.38,0.18").split(","))
coffee_scatter = float(os.environ.get("LOOK_COFFEE_SCATTER", 900.0))
out_dir.mkdir(parents=True, exist_ok=True)
L = json.load(open(run / "sim_log.json"))
geom_dir = Path(L["args"]["geom"]); geom_dir = geom_dir if geom_dir.is_absolute() else run.parent.parent / geom_dir
cx, cy = json.load(open(geom_dir / "geom_info.json"))["cup_center_xy"]
sc = bpy.context.scene

# hide the stage's authored static coffee and its placeholder ice cube
for name in ("Circle.028", "PCVE_IceCube_16mm"):
    o = bpy.data.objects.get(name)
    if o:
        o.hide_render = True; o.hide_viewport = True

# close-up camera along the accepted viewing direction
cam = sc.camera
L0 = Vector((-1.41, -6.77, 1.275)); T0 = Vector((-0.8585150241851807, -5.796055793762207, 0.925))
d = (T0 - L0).normalized()
cam_elev = os.environ.get("LOOK_CAM_ELEV", "30")  # degrees below horizontal (the stage's own view looks down 17)
import math as _m
az = Vector((d.x, d.y, 0.0)).normalized(); e = _m.radians(float(cam_elev))
d = (az * _m.cos(e) + Vector((0, 0, -_m.sin(e)))).normalized()
target = Vector((cx, cy, target_z))
cam.location = target - d * distance
cam.rotation_mode = "QUATERNION"
cam.rotation_quaternion = d.to_track_quat("-Z", "Y")
cam.data.lens = float(os.environ.get("LOOK_LENS", 58.0))
if cam.data.dof.use_dof:
    cam.data.dof.focus_object = None
    cam.data.dof.focus_distance = distance
    if os.environ.get("LOOK_FSTOP"):
        cam.data.dof.aperture_fstop = float(os.environ["LOOK_FSTOP"])
# colour management / exposure
if os.environ.get("LOOK_EXPOSURE"):
    sc.view_settings.exposure = float(os.environ["LOOK_EXPOSURE"])
if os.environ.get("LOOK_AGX"):
    sc.view_settings.look = os.environ["LOOK_AGX"]
# optional table-top lighting: a soft side key and a back light in the coffee's mirror direction (the room's own
# lights are far away, so the cup, spoon and coffee reflect almost nothing bright)
if os.environ.get("LOOK_KEY") == "1":
    import math as _m
    def area_light(name, energy, size, az_deg, el_deg, dist, color=(1.0, 0.94, 0.86)):
        ld = bpy.data.lights.new(name, "AREA"); ld.energy = energy; ld.size = size; ld.color = color
        ob = bpy.data.objects.new(name, ld); sc.collection.objects.link(ob)
        az = _m.atan2(d.y, d.x) + _m.radians(az_deg); el = _m.radians(el_deg)
        c = Vector((cx, cy, 0.83))
        ob.location = c + dist * Vector((_m.cos(az) * _m.cos(el), _m.sin(az) * _m.cos(el), _m.sin(el)))
        ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = (c - ob.location).normalized().to_track_quat("-Z", "Y")
        return ob
    # azimuth relative to the camera's viewing direction d: 0 = behind the cup (opposite the camera)
    area_light("PCVE_KeyLight", float(os.environ.get("LOOK_KEY_ENERGY", 8)), 0.6, float(os.environ.get("LOOK_KEY_AZ", 120)), float(os.environ.get("LOOK_KEY_EL", 40)), 0.9)
    area_light("PCVE_BackLight", float(os.environ.get("LOOK_BACK_ENERGY", 1.5)), float(os.environ.get("LOOK_BACK_SIZE", 0.08)), 0.0, float(os.environ.get("LOOK_BACK_EL", 34)), 0.8)

# coffee: dark, glossy, light-absorbing liquid (thin sheets/droplets read amber, bulk reads near black)
mat = bpy.data.materials.new("PCVE Genesis Coffee"); mat.use_nodes = True
nt = mat.node_tree; nodes = nt.nodes; links = nt.links
bsdf = nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.30, 0.12, 0.05, 1.0)
bsdf.inputs["Roughness"].default_value = 0.03
bsdf.inputs["IOR"].default_value = 1.34
bsdf.inputs["Transmission Weight"].default_value = 1.0
absorb = nodes.new("ShaderNodeVolumeAbsorption")
absorb.inputs["Color"].default_value = (*coffee_abs_color, 1.0)
absorb.inputs["Density"].default_value = coffee_absorption
if coffee_scatter > 0:  # suspended coffee solids: a faint warm in-scatter gives the body a brown glow
    cscat = nodes.new("ShaderNodeVolumeScatter")
    cscat.inputs["Color"].default_value = tuple(float(x) for x in os.environ.get("LOOK_COFFEE_SCATTER_COLOR", "0.75,0.45,0.25").split(",")) + (1.0,)
    cscat.inputs["Density"].default_value = coffee_scatter
    cadd = nodes.new("ShaderNodeAddShader")
    links.new(absorb.outputs["Volume"], cadd.inputs[0]); links.new(cscat.outputs["Volume"], cadd.inputs[1])
    links.new(cadd.outputs["Shader"], nodes["Material Output"].inputs["Volume"])
else:
    links.new(absorb.outputs["Volume"], nodes["Material Output"].inputs["Volume"])

mesh = bpy.data.meshes.new("PCVE_GenesisCoffee")
coffee = bpy.data.objects.new("PCVE_GenesisCoffee", mesh)
sc.collection.objects.link(coffee)
coffee.data.materials.append(mat)
drops = bpy.data.objects.new("PCVE_GenesisCoffeeDrops", bpy.data.meshes.new("drops_empty"))
sc.collection.objects.link(drops)

def load_coffee(frame):
    z = np.load(run / mesh_dir / f"coffee_{frame:04d}.npz")
    v, t, n = z["vertices"], z["triangles"], z["normals"]
    me = bpy.data.meshes.new(f"coffee_{frame:04d}")
    if len(v) == 0:  # DELETE coffee
        old = coffee.data; coffee.data = me
        if old.users == 0:
            bpy.data.meshes.remove(old)
        return
    me.vertices.add(len(v)); me.vertices.foreach_set("co", v.ravel())
    me.loops.add(t.size); me.loops.foreach_set("vertex_index", t.ravel())
    me.polygons.add(len(t)); me.polygons.foreach_set("loop_start", np.arange(0, t.size, 3))
    me.polygons.foreach_set("use_smooth", np.ones(len(t), bool))
    me.update(); me.validate(clean_customdata=False)
    me.normals_split_custom_set_from_vertices([tuple(x) for x in n])
    if "velocity" in z.files:  # Cycles reads a point "velocity" attribute (m/s) for motion blur of changing topology
        att = me.attributes.new("velocity", "FLOAT_VECTOR", "POINT")
        att.data.foreach_set("vector", z["velocity"].ravel())
    me.materials.append(mat)
    old = coffee.data; coffee.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    if "drops_vertices" in z.files:  # flattened wetting drops resting on the saucer / table
        dv_, dt_ = z["drops_vertices"], z["drops_triangles"]
        md = bpy.data.meshes.new(f"drops_{frame:04d}")
        if len(dv_):
            md.from_pydata(dv_.tolist(), [], dt_.tolist())
            md.polygons.foreach_set("use_smooth", np.ones(len(dt_), bool))
            md.update()
        md.materials.append(mat)
        oldd = drops.data; drops.data = md
        if oldd.users == 0:
            bpy.data.meshes.remove(oldd)

# ice: the accepted frosted-white BlenderKit asset, 16 mm physics cube shown as 17.4 mm rounded cube
with bpy.data.libraries.load(str(ice_asset), link=False) as (src, dst):
    dst.objects = list(src.objects)
ice_objs = [o for o in dst.objects if o is not None]
vis = [o for o in ice_objs if o.type == "MESH"][0]
for o in ice_objs:
    if o is not vis: bpy.data.objects.remove(o, do_unlink=True)
sc.collection.objects.link(vis)
vis.parent = None; vis.matrix_world = Matrix.Identity(4); bpy.context.view_layer.update()
bb = [Vector(c) for c in vis.bound_box]
lo = Vector([min(c[i] for c in bb) for i in range(3)]); hi = Vector([max(c[i] for c in bb) for i in range(3)])
ice_local_centre = (lo + hi) * 0.5  # mesh-local bbox centre; the asset origin is off-centre
if os.environ.get("LOOK_ICE_SCALE", "volume") == "volume":
    # scale the rounded beauty asset so its volume equals the simulated cube's (side^3); a 17.4 mm bbox made it ~9 %
    # larger than the physics cube, so it rode visibly higher out of the coffee
    import bmesh
    ev = vis.evaluated_get(bpy.context.evaluated_depsgraph_get()); me_ = ev.to_mesh()
    bm = bmesh.new(); bm.from_mesh(me_); vol_local = abs(bm.calc_volume()); bm.free(); ev.to_mesh_clear()
    s = (L["args"]["ice_side"] ** 3 / vol_local) ** (1.0 / 3.0)
    print(f"[ice] volume-matched scale: bbox {1000*s*max(hi - lo):.2f} mm, volume {1e9*s**3*vol_local:.0f} mm^3", flush=True)
else:
    s = 0.0174 * (L["args"]["ice_side"] / 0.016) / max(hi - lo)
root = bpy.data.objects.new("PCVE_IceRoot", None); sc.collection.objects.link(root)
vis.parent = root; vis.location = -(lo + hi) * 0.5 * s; vis.scale = (s, s, s); vis.rotation_euler = (0, 0, 0)
bpy.context.view_layer.update()
ice_look = args.ice_look
core_density = float(os.environ.get("LOOK_ICE_CORE_DENSITY", args.core_density))
core_in = float(os.environ.get("LOOK_ICE_CORE_IN", 0.35)); core_out = float(os.environ.get("LOOK_ICE_CORE_OUT", 0.80))


def clear_ice(m):
    """Freezer ice: clear, wet, slightly blue body with a cloudy core of trapped air (object-space density field).
    Keeps the asset's own noise bump and roughness pattern, scaled down to a wet surface."""
    nt = m.node_tree; nodes = nt.nodes; links = nt.links
    bsdf = next(nd for nd in nodes if nd.type == "BSDF_PRINCIPLED")
    out = next(nd for nd in nodes if nd.type == "OUTPUT_MATERIAL")
    bsdf.inputs["Base Color"].default_value = (0.94, 0.98, 1.0, 1.0)
    bsdf.inputs["Transmission Weight"].default_value = 1.0
    bsdf.inputs["IOR"].default_value = 1.31
    bsdf.inputs["Subsurface Weight"].default_value = 0.0
    bsdf.inputs["Coat Weight"].default_value = 0.0
    rough = next((l for l in links if l.to_node == bsdf and l.to_socket.name == "Roughness"), None)
    if rough is not None:  # asset ramp gives ~0.5; a melting surface is wet and glossy
        mul = nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = 0.12
        src = rough.from_socket; links.remove(rough)
        links.new(src, mul.inputs[0]); links.new(mul.outputs[0], bsdf.inputs["Roughness"])
    else:
        bsdf.inputs["Roughness"].default_value = 0.05
    tc = next(nd for nd in nodes if nd.type == "TEX_COORD")
    # cloudy core: 1 inside ~45 % of the half size, fading to clear at ~85 %, broken up by noise (bubble streaks)
    # distance from the mesh's own bbox centre (the asset origin is off-centre), Chebyshev norm -> cube-shaped core,
    # warped by noise so the edge of the cloud is feathery like trapped-air streaks
    centre = nodes.new("ShaderNodeVectorMath"); centre.operation = "SUBTRACT"
    centre.inputs[1].default_value = tuple(ice_local_centre)
    links.new(tc.outputs["Object"], centre.inputs[0])
    warp = nodes.new("ShaderNodeTexNoise"); warp.inputs["Scale"].default_value = 40.0; warp.inputs["Detail"].default_value = 4.0
    links.new(tc.outputs["Object"], warp.inputs["Vector"])
    wsc = nodes.new("ShaderNodeVectorMath"); wsc.operation = "SCALE"; wsc.inputs["Scale"].default_value = 0.004
    links.new(warp.outputs["Color"], wsc.inputs[0])
    wadd = nodes.new("ShaderNodeVectorMath"); wadd.operation = "ADD"
    links.new(centre.outputs[0], wadd.inputs[0]); links.new(wsc.outputs[0], wadd.inputs[1])
    absv = nodes.new("ShaderNodeVectorMath"); absv.operation = "ABSOLUTE"
    links.new(wadd.outputs[0], absv.inputs[0])
    sep = nodes.new("ShaderNodeSeparateXYZ"); links.new(absv.outputs[0], sep.inputs[0])
    mx1 = nodes.new("ShaderNodeMath"); mx1.operation = "MAXIMUM"; links.new(sep.outputs[0], mx1.inputs[0]); links.new(sep.outputs[1], mx1.inputs[1])
    length = nodes.new("ShaderNodeMath"); length.operation = "MAXIMUM"; links.new(mx1.outputs[0], length.inputs[0]); links.new(sep.outputs[2], length.inputs[1])
    half = 0.5 * max(vis.dimensions) / vis.scale[0]
    mr = nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = core_in * half; mr.inputs["From Max"].default_value = core_out * half
    mr.inputs["To Min"].default_value = 1.0; mr.inputs["To Max"].default_value = 0.0
    links.new(length.outputs[0], mr.inputs["Value"])
    noise = nodes.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = 90.0; noise.inputs["Detail"].default_value = 6.0
    links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB"); ramp.color_ramp.elements[0].position = 0.35; ramp.color_ramp.elements[1].position = 0.75
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    m1 = nodes.new("ShaderNodeMath"); m1.operation = "MULTIPLY"
    links.new(mr.outputs["Result"], m1.inputs[0]); links.new(ramp.outputs["Color"], m1.inputs[1])
    m2 = nodes.new("ShaderNodeMath"); m2.operation = "MULTIPLY"; m2.inputs[1].default_value = core_density  # 1/m
    links.new(m1.outputs[0], m2.inputs[0])
    scat = nodes.new("ShaderNodeVolumeScatter"); scat.inputs["Color"].default_value = (0.95, 0.97, 1.0, 1.0)
    scat.inputs["Anisotropy"].default_value = 0.3
    links.new(m2.outputs[0], scat.inputs["Density"])
    absn = nodes.new("ShaderNodeVolumeAbsorption"); absn.inputs["Color"].default_value = (0.86, 0.94, 1.0, 1.0)
    absn.inputs["Density"].default_value = 8.0
    add = nodes.new("ShaderNodeAddShader")
    links.new(scat.outputs["Volume"], add.inputs[0]); links.new(absn.outputs["Volume"], add.inputs[1])
    links.new(add.outputs["Shader"], out.inputs["Volume"])


def frosted_ice(m):
    for nd in m.node_tree.nodes:
        if nd.type == "BSDF_PRINCIPLED":
            nd.inputs["Base Color"].default_value = (0.90, 0.965, 1.0, 1.0)
            nd.inputs["IOR"].default_value = 1.31
            nd.inputs["Transmission Weight"].default_value = 0.24
            nd.inputs["Coat Weight"].default_value = 0.28
            nd.inputs["Coat Roughness"].default_value = 0.055
            nd.inputs["Subsurface Weight"].default_value = 0.035
    out = next(nd for nd in m.node_tree.nodes if nd.type == "OUTPUT_MATERIAL")
    vs = m.node_tree.nodes.new("ShaderNodeVolumeScatter")
    vs.inputs["Color"].default_value = (0.82, 0.93, 1.0, 1.0); vs.inputs["Density"].default_value = 10.0
    vs.inputs["Anisotropy"].default_value = 0.12
    m.node_tree.links.new(vs.outputs["Volume"], out.inputs["Volume"])


for m in vis.data.materials:
    if m and m.use_nodes:
        (clear_ice if ice_look == "clear" else frosted_ice)(m)
root.rotation_mode = "QUATERNION"

# render settings
r = sc.render
r.engine = "CYCLES"; r.resolution_x = 1280; r.resolution_y = 720; r.resolution_percentage = 100
sc.cycles.device = "GPU"; sc.cycles.samples = samples; sc.cycles.use_denoising = True
sc.cycles.seed = int(os.environ.get("LOOK_SEED", 0))
sc.cycles.use_adaptive_sampling = os.environ.get("LOOK_ADAPTIVE", "0") == "1"
sc.cycles.adaptive_threshold = float(os.environ.get("LOOK_ADAPTIVE_THRESHOLD", 0.01))
sc.cycles.max_bounces = 10; sc.cycles.transmission_bounces = 8; sc.cycles.volume_bounces = 2
sc.cycles.volume_step_rate = 0.5
r.use_persistent_data = True; r.use_motion_blur = motion_blur
if motion_blur:
    r.motion_blur_shutter = 0.5  # 180-degree shutter
    sc.cycles.motion_blur_position = "CENTER"
prefs = bpy.context.preferences.addons["cycles"].preferences
for backend in ("OPTIX", "CUDA"):
    try:
        prefs.compute_device_type = backend; prefs.get_devices(); break
    except Exception:
        continue
for dev in prefs.devices:
    dev.use = dev.type in {"OPTIX", "CUDA"}
r.image_settings.file_format = "PNG"

n_frames = len(L["frames"])
sc.frame_start, sc.frame_end = 1, n_frames
r.fps = L["args"]["fps"]
if not L["ice_pose"]:  # DELETE ice
    vis.hide_render = True
ice_pose_override = os.environ.get("LOOK_ICE_POSE_FRAME")  # debug: pin the ice to one frame's pose


def steady_ice_poses(poses, k=6, t_lo=0.4e-3, t_hi=1.0e-3, a_lo=0.4, a_hi=1.0):
    """The floating ice wobbles ~0.08 deg per frame from SPH pressure noise; its refraction and cloudy core then shimmer.
    Where the ice's whole motion within +-k frames is below t_lo / a_lo degrees, draw its window-mean pose, blended out by
    t_hi / a_hi (falling, bobbing and the viscous sinking keep their own trajectory). Render-side only."""
    P_ = np.array([q["pos"] for q in poses], float); Q = np.array([q["quat_wxyz"] for q in poses], float)
    out = []
    for f in range(len(poses)):
        lo, hi = max(0, f - k), min(len(poses), f + k + 1); kk = min(f - lo, hi - 1 - f)
        Wp = P_[f - kk:f + kk + 1]; Wq = Q[f - kk:f + kk + 1].copy()
        Wq[(Wq @ Q[f]) < 0] *= -1
        amp_t = (Wp.max(0) - Wp.min(0)).max()
        amp_a = np.degrees(2 * np.arccos(np.clip(np.abs(Wq @ Q[f]), 0, 1))).max()
        w = min(np.clip((t_hi - amp_t) / (t_hi - t_lo), 0, 1), np.clip((a_hi - amp_a) / (a_hi - a_lo), 0, 1)) if kk else 0.0
        pm = Wp.mean(0); qm = Wq.mean(0); qm /= np.linalg.norm(qm)
        qq = (1 - w) * Q[f] + w * qm; qq /= np.linalg.norm(qq)
        out.append({"pos": ((1 - w) * P_[f] + w * pm).tolist(), "quat_wxyz": qq.tolist()})
    return out


render_poses = steady_ice_poses(L["ice_pose"]) if L["ice_pose"] and os.environ.get("LOOK_ICE_STEADY", "1") == "1" else L["ice_pose"]
if ice_pose_override:
    render_poses = [render_poses[int(ice_pose_override) - 1]] * len(render_poses)
# holds (written by the surface step): stretches where the ice and the liquid stay within a fraction of a pixel are
# rendered once at their mean state and consecutive holds are cross-faded, so sub-pixel motion does not redraw the
# path-tracing noise every frame
hold_path = run / mesh_dir / "hold_plan.json"
hold = json.load(open(hold_path)) if hold_path.exists() and os.environ.get("LOOK_HOLD", "1") == "1" else None
seg_pose = {}
if hold:
    for k, sg in enumerate(hold["segments"]):
        for i in range(sg["first"], sg["last"] + 1):
            seg_pose[i] = sg["ice_pose"]
    print(f"[hold] {len(hold['segments'])} holds over {len(seg_pose)} of {n_frames} frames", flush=True)


def key_ice(f, pose):
    p = pose["pos"]; q = pose["quat_wxyz"]
    root.location = (p[0] + cx, p[1] + cy, p[2])
    root.rotation_quaternion = Quaternion(q)
    root.keyframe_insert("location", frame=f); root.keyframe_insert("rotation_quaternion", frame=f)


for f in (range(1, n_frames + 1) if L["ice_pose"] else []):  # keyframe the ice so Cycles has its motion for blur
    key_ice(f, seg_pose.get(f) or render_poses[f - 1])


def render_state(f, path, held):
    """Render frame f's state (a hold renders its first frame: mean liquid surface at rest, held ice pose)."""
    load_coffee(f)
    vis.cycles.use_motion_blur = not held
    sc.frame_set(f)
    r.filepath = str(path)
    bpy.ops.render.render(write_still=True)


keys_dir = out_dir / "holds"
if hold:  # hold renders are cached per plan: a new surface step invalidates them
    import hashlib
    stamp = hashlib.sha256(hold_path.read_bytes()).hexdigest()
    if keys_dir.exists() and not (keys_dir / stamp).exists():
        shutil.rmtree(keys_dir)
    keys_dir.mkdir(exist_ok=True); (keys_dir / stamp).touch()
for f in (frames or range(1, n_frames + 1)):
    entries = hold["frames"][f - 1] if hold else [[1.0, f"frame{f}"]]
    if len(entries) == 1 and entries[0][1].startswith("frame"):
        render_state(f, out_dir / f"frame_{f:04d}.png", False)
    else:
        parts = []
        for w, key in entries:
            path = keys_dir / f"{key}.png"
            if not path.exists():
                render_state(hold["segments"][int(key[3:])]["first"], path, True)
            parts.append((w, path))
        if len(parts) == 1:
            shutil.copyfile(parts[0][1], out_dir / f"frame_{f:04d}.png")
        else:
            import OpenImageIO as oiio
            bufs = [oiio.ImageBuf(str(pth)) for _, pth in parts]
            spec = bufs[0].spec()
            mix = sum(w * bufs[k].get_pixels(oiio.FLOAT) for k, (w, _) in enumerate(parts))
            res = oiio.ImageBuf(oiio.ImageSpec(spec.width, spec.height, spec.nchannels, spec.format))
            res.set_pixels(oiio.ROI(), np.asarray(mix, np.float32))
            res.write(str(out_dir / f"frame_{f:04d}.png"))
    print(f"RENDERED {f}", flush=True)
