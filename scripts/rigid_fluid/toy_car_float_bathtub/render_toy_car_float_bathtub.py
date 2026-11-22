"""Blender 4.3 / Cycles: render a simulated case in the bathroom (the Sketchfab room with the fitted ceramic shell).

The room has no real opening, so daylight comes through a virtual window on the wall behind the shelves (off camera): a large
soft area light as the sky seen through it, and a directional beam (area light with a small spread) as low sun, which is what
casts the float's shadow and the water's light pattern on the ceramic. The float is PVC with its seam and valve, the water a
clear dielectric with the real absorption of water, droplets glass spheres with motion blur (clear, without the absorption),
the car's beads wet paint.
usage: blender -b --python render_toy_car_float_bathtub.py -- --run RUN --mesh-dir DIR --out OUT --frames 1 12 ... [--samples 128]"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import scene_asset
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
import argparse, json, math, sys, time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

HERE = Path(__file__).resolve().parent


def ASSET(rel):
    return scene_asset(HERE, "assets/" + rel)


import car_paint_appearance, bathroom_appearance, bathroom_details, bathroom_finish

ap = argparse.ArgumentParser()
ap.add_argument("--run", type=Path, required=True)
ap.add_argument("--mesh-dir", type=Path, required=True)
ap.add_argument("--out", type=Path, required=True)
ap.add_argument("--frames", type=int, nargs="+", required=True)
ap.add_argument("--samples", type=int, default=64)
ap.add_argument("--resolution", type=int, nargs=2, default=(1280, 720))
ap.add_argument("--camera", type=float, nargs=3, default=(-1.05, 0.80, 1.62))
ap.add_argument("--target", type=float, nargs=3, default=(0.02, -0.04, 0.56))
ap.add_argument("--lens", type=float, default=32.0)
ap.add_argument("--exposure", type=float, default=-2.3)
ap.add_argument("--window", type=float, default=90.0, help="soft window light (W)")
ap.add_argument("--beam", type=float, default=150.0, help="sun beam (W)")
ap.add_argument("--beam-spread", type=float, default=16.0)
ap.add_argument("--world", type=float, default=0.2)
ap.add_argument("--caustics", type=float, default=0.8, help="strength of the sun's light lines on the ceramic (surface_toy_car_float_bathtub.py); added light, so nothing is darkened")
ap.add_argument("--absorb", type=float, nargs=3, default=(0.82, 0.97, 0.99), help="water absorption colour (density 1 per m)")
ap.add_argument("--look", default="AgX - Medium High Contrast")
ap.add_argument("--no-motion-blur", action="store_true")
ap.add_argument("--no-water", action="store_true")
a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
a.out.mkdir(parents=True, exist_ok=True)
log = json.loads((a.run / "sim_log.json").read_text())
args_sim = log["args"]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def material(name, color, metallic=0.0, roughness=0.4):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1); b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = roughness
    return m


def add_cylinder(name, center, radius, depth, mat, parent=None, segments=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=segments, radius=radius, depth=depth, location=center)
    o = bpy.context.object; o.name = name; o.data.materials.append(mat)
    for poly in o.data.polygons:
        poly.use_smooth = True
    if parent is not None:
        o.parent = parent
    return o


# ---------------------------------------------------------------- room
before = set(scene.objects)
bpy.ops.import_scene.gltf(filepath=str(ASSET("sketchfab_bathroom/bathroom.glb")))
imported = [o for o in scene.objects if o not in before]
root = bpy.data.objects.new("PCVE_BathroomAssetRoot", None); scene.collection.objects.link(root)
s_ = set(imported)
for o in [o for o in imported if o.parent not in s_]:
    m_ = o.matrix_world.copy(); o.parent = root; o.matrix_world = m_
for o in imported:
    if o.type == "MESH" and (o.name.startswith("Circle140_Water_0") or o.name.startswith("arch24_023_")):
        o.hide_render = True; o.hide_viewport = True
root.location = (1.6419553756713867, 0.8095061779022217, 0.007460540160536766)
bpy.context.view_layer.update()
preset = bathroom_appearance.PRESETS["natural_finish"]
bathroom_appearance.apply_tub_glaze(scene, preset["tub_glaze"])
bathroom_details.apply_screen_details(scene, preset.get("screen_details"))
bathroom_finish.apply_bathroom_finish(scene, preset.get("finish_details"))
drain_metal = material("PCVE_ChromeDrain", (0.56, 0.60, 0.63), 0.95, 0.17)
drain_metal.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.34
_floor = add_cylinder("PCVE_DrainFloor", (0.0132777, 0.0108457, 0.1122), 0.056, 0.0012, bpy.data.objects["PCVE_BathtubShell"].material_slots[0].material)
add_cylinder("PCVE_DrainFlange", (0.0132777, 0.0108457, 0.1132), 0.035, 0.0012, drain_metal)
_cap = add_cylinder("PCVE_DrainCap", (0.0132777, 0.0108457, 0.1142), 0.031, 0.0028, drain_metal)
_bv = _cap.modifiers.new("Rounded cap", "BEVEL"); _bv.width = 0.0012; _bv.segments = 4


# ---------------------------------------------------------------- float
def pvc_material(color):
    """Thin glossy PVC over air: a clear-coated colour with some light coming through the skin."""
    m = bpy.data.materials.new("PCVE_FloatPVC"); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]; out = nt.nodes["Material Output"]
    b.inputs["Roughness"].default_value = 0.28
    b.inputs["Coat Weight"].default_value = 0.35; b.inputs["Coat Roughness"].default_value = 0.03
    b.inputs["Subsurface Weight"].default_value = 0.15; b.inputs["Subsurface Scale"].default_value = 0.006
    b.inputs["Subsurface Radius"].default_value = (0.6, 0.45, 1.0)
    # slow unevenness of the pigment where the sheet stretched
    co = nt.nodes.new("ShaderNodeTexCoord"); no = nt.nodes.new("ShaderNodeTexNoise"); no.inputs["Scale"].default_value = 9.0
    ra = nt.nodes.new("ShaderNodeValToRGB")
    ra.color_ramp.elements[0].color = (color[0] * 0.8, color[1] * 0.8, color[2] * 0.85, 1); ra.color_ramp.elements[1].color = (*color, 1)
    nt.links.new(co.outputs["Object"], no.inputs["Vector"]); nt.links.new(no.outputs["Fac"], ra.inputs["Fac"]); nt.links.new(ra.outputs["Color"], b.inputs["Base Color"])
    tr = nt.nodes.new("ShaderNodeBsdfTranslucent"); nt.links.new(ra.outputs["Color"], tr.inputs["Color"])
    mx = nt.nodes.new("ShaderNodeMixShader"); mx.inputs[0].default_value = 0.12
    nt.links.new(b.outputs["BSDF"], mx.inputs[1]); nt.links.new(tr.outputs["BSDF"], mx.inputs[2]); nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return m


tray_pose = robot_pose = None
_d0 = np.load(a.run / "particles" / f"frame_{a.frames[0]:04d}.npz")
if not args_sim.get("no_float"):
    tray_pose = bpy.data.objects.new("PCVE_TrayPose", None); scene.collection.objects.link(tray_pose)
    fm = np.load(ASSET("procedural_float/float_mesh.npz"))
    me = bpy.data.meshes.new("PCVE_FloatMesh")
    v_, t_ = fm["vertices"], fm["triangles"]
    me.vertices.add(len(v_)); me.vertices.foreach_set("co", v_.ravel())
    me.loops.add(t_.size); me.loops.foreach_set("vertex_index", t_.ravel())
    me.polygons.add(len(t_)); me.polygons.foreach_set("loop_start", np.arange(0, t_.size, 3)); me.polygons.foreach_set("loop_total", np.full(len(t_), 3))
    me.update(); me.validate()
    me.polygons.foreach_set("use_smooth", np.ones(len(t_), bool))
    me.materials.append(pvc_material((0.085, 0.022, 0.40)))
    ob = bpy.data.objects.new("PCVE_Float", me); scene.collection.objects.link(ob); ob.parent = tray_pose
    # the valve on the outer tube near a corner: a stem with its cap on a tether
    ff = np.load(ASSET("procedural_float/float_field.npz"))
    vx, vy = 0.180, 0.095
    i_, j_ = np.searchsorted(ff["x"], vx), np.searchsorted(ff["y"], vy)
    zv = float(ff["z0"][i_, j_] + ff["t"][i_, j_])
    valve = material("PCVE_ValvePVC", (0.82, 0.80, 0.70), 0.0, 0.3)
    add_cylinder("PCVE_ValveBase", (vx, vy, zv + 0.0008), 0.0095, 0.0022, valve, tray_pose, 32)
    add_cylinder("PCVE_ValveStem", (vx, vy, zv + 0.0050), 0.0050, 0.0070, valve, tray_pose, 32)
    add_cylinder("PCVE_ValveCap", (vx + 0.016, vy + 0.003, zv + 0.0012), 0.0060, 0.0030, valve, tray_pose, 32)

# ---------------------------------------------------------------- wet paint
# The surface stage marks the car points particles have come close to (car_wet_local in spray_####.npz). As glass spheres
# those beads are under a pixel across at this distance (about 1.3 mm per pixel at the car): the sampler cannot resolve
# them and they shimmer from frame to frame. The paint where water has been is drawn wet instead: a little darker, a full
# clear coat, and sparse beads of a pixel or two in the coat's normal that ride with the car.
WET_RADIUS = 0.004        # a vertex is wet from the first frame a marked point within this distance (m) was wet
BEAD_CELL = 0.004         # bead spacing (m); about a third of the cells hold a bead


def wet_paint(m):
    """wet from the vertex attribute pcve_wet_frame on; returns the value node the render sets to the frame"""
    nt = m.node_tree; b = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    at = nt.nodes.new("ShaderNodeAttribute"); at.attribute_type = "GEOMETRY"; at.attribute_name = "pcve_wet_frame"
    now = nt.nodes.new("ShaderNodeValue"); now.name = "PCVE_WetNow"; now.outputs[0].default_value = 0.0
    age = nt.nodes.new("ShaderNodeMath"); age.operation = "SUBTRACT"
    nt.links.new(now.outputs[0], age.inputs[0]); nt.links.new(at.outputs["Fac"], age.inputs[1])
    wet = nt.nodes.new("ShaderNodeMapRange")                      # fades in over two frames
    wet.inputs["From Min"].default_value = -0.5; wet.inputs["From Max"].default_value = 1.5
    nt.links.new(age.outputs[0], wet.inputs["Value"])
    c0 = tuple(b.inputs["Base Color"].default_value)
    col = nt.nodes.new("ShaderNodeMix"); col.data_type = "RGBA"
    col.inputs["A"].default_value = c0; col.inputs["B"].default_value = (c0[0] * 0.9, c0[1] * 0.9, c0[2] * 0.9, 1)
    nt.links.new(wet.outputs["Result"], col.inputs["Factor"]); nt.links.new(col.outputs["Result"], b.inputs["Base Color"])
    coat = nt.nodes.new("ShaderNodeMix"); coat.data_type = "FLOAT"
    coat.inputs["A"].default_value = b.inputs["Coat Weight"].default_value; coat.inputs["B"].default_value = 1.0
    nt.links.new(wet.outputs["Result"], coat.inputs["Factor"]); nt.links.new(coat.outputs["Result"], b.inputs["Coat Weight"])
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi"); vor.feature = "F1"
    vor.inputs["Scale"].default_value = 1.0 / BEAD_CELL; vor.inputs["Randomness"].default_value = 1.0
    nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
    cap = nt.nodes.new("ShaderNodeMapRange"); cap.interpolation_type = "SMOOTHSTEP"
    cap.inputs["From Min"].default_value = 0.40; cap.inputs["From Max"].default_value = 0.12
    nt.links.new(vor.outputs["Distance"], cap.inputs["Value"])
    keep = nt.nodes.new("ShaderNodeMapRange"); keep.interpolation_type = "SMOOTHSTEP"
    keep.inputs["From Min"].default_value = 0.64; keep.inputs["From Max"].default_value = 0.70
    nt.links.new(vor.outputs["Color"], keep.inputs["Value"])
    m1 = nt.nodes.new("ShaderNodeMath"); m1.operation = "MULTIPLY"; m2 = nt.nodes.new("ShaderNodeMath"); m2.operation = "MULTIPLY"
    nt.links.new(cap.outputs["Result"], m1.inputs[0]); nt.links.new(keep.outputs["Result"], m1.inputs[1])
    nt.links.new(m1.outputs[0], m2.inputs[0]); nt.links.new(wet.outputs["Result"], m2.inputs[1])
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.6; bump.inputs["Distance"].default_value = 0.0005
    nt.links.new(m2.outputs[0], bump.inputs["Height"]); nt.links.new(bump.outputs["Normal"], b.inputs["Coat Normal"])
    return now


car_wet_now = []

# ---------------------------------------------------------------- car
if not args_sim.get("no_car"):
    toy = json.loads(ASSET("amg_vision_gt/toy_manifest.json").read_text())
    robot_pose = bpy.data.objects.new("PCVE_RobotPose", None); scene.collection.objects.link(robot_pose)
    before = set(scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(ASSET("amg_vision_gt/amg_vision_gt.glb")))
    imported = [o for o in scene.objects if o not in before]
    centre, sc_ = Vector(toy["centre_blender_m"]), toy["scale"]
    body = Matrix.Diagonal((sc_, sc_, sc_, 1.0)) @ Matrix.Translation(-centre)
    visual, prefixes = [], toy.get("visual_object_prefixes")
    for o in imported:
        if o.type == "MESH" and (not prefixes or any(o.name.startswith(p_) for p_ in prefixes)):
            o.data = o.data.copy(); o.data.transform(body @ o.matrix_world)
            o.parent = robot_pose; o.matrix_parent_inverse = Matrix.Identity(4); o.matrix_basis = Matrix.Identity(4)
            visual.append(o)
    for o in imported:
        if o not in visual:
            bpy.data.objects.remove(o)
    car_paint_appearance.apply_car(robot_pose)
    for o in visual:
        for m_ in o.data.materials:
            if m_ and m_.name.split(".")[0] in ("CHROME", "CAR_CHASSIS"):
                b_ = next(n for n in m_.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
                b_.inputs["Base Color"].default_value = (0.20, 0.215, 0.24, 1); b_.inputs["Metallic"].default_value = 0.9
                b_.inputs["Roughness"].default_value = 0.22; b_.inputs["Coat Weight"].default_value = 0.9; b_.inputs["Coat Roughness"].default_value = 0.03
    first = {}                                    # car point (car frame) -> first frame it was wet
    for p_s in sorted(a.mesh_dir.glob("spray_*.npz")):
        with np.load(p_s) as d_s:
            if "car_wet_local" not in d_s.files:
                first = None
                break
            for q_ in map(tuple, d_s["car_wet_local"].tolist()):
                first.setdefault(q_, int(p_s.stem.split("_")[1]))
    if first is None:
        print("NOTE: these surfaces have no car_wet_local: the car keeps its sphere beads", flush=True)
    else:
        from mathutils.kdtree import KDTree
        kd = KDTree(max(len(first), 1))
        for i_, q_ in enumerate(first):
            kd.insert(q_, i_)
        kd.balance()
        when = list(first.values())
        for o in visual:                          # mesh coordinates are the car frame (the pose sits on the parent)
            co = np.empty(len(o.data.vertices) * 3, np.float32); o.data.vertices.foreach_get("co", co)
            wf = np.full(len(o.data.vertices), 1.0e4, np.float32)
            if first:
                for k_, v_ in enumerate(co.reshape(-1, 3).tolist()):
                    _, i_, dist_ = kd.find(v_)
                    if dist_ is not None and dist_ < WET_RADIUS:
                        wf[k_] = when[i_]
            o.data.attributes.new("pcve_wet_frame", "FLOAT", "POINT").data.foreach_set("value", wf)
        for m_ in {m_ for o in visual for m_ in o.data.materials if m_ and m_.name.split(".")[0] in ("CHROME", "CAR_CHASSIS")}:
            car_wet_now.append(wet_paint(m_))
        print(f"WET PAINT: {len(first)} wet car points", flush=True)

# ---------------------------------------------------------------- poses
frames_all = sorted(int(p.stem.split("_")[1]) for p in (a.run / "particles").glob("frame_*.npz"))
floor_gap = 2 * float(args_sim["particle"])
poses = {k: o for k, o in (("tray", tray_pose), ("robot", robot_pose)) if o is not None}
prev = {}
for f in frames_all:
    with np.load(a.run / "particles" / f"frame_{f:04d}.npz") as d:
        for key, o in poses.items():
            q = Quaternion(d[f"{key}_quat_wxyz"])
            if key in prev and prev[key].dot(q) < 0:
                q.negate()
            prev[key] = q
            o.rotation_mode = "QUATERNION"; o.rotation_quaternion = q
            # the simulation rests a body two particle sizes above the ceramic (simulate_toy_car_float_bathtub.py): put it down on it here
            p_ = np.array(d[f"{key}_pos"], float)
            gap_ = p_[2] - 0.026 - 0.1125
            p_[2] -= floor_gap * float(np.clip(1 - (gap_ - floor_gap) / 0.03, 0, 1))
            o.location = p_
            o.keyframe_insert("location", frame=f); o.keyframe_insert("rotation_quaternion", frame=f)
for o in poses.values():
    for cu in o.animation_data.action.fcurves:
        for kp in cu.keyframe_points:
            kp.interpolation = "LINEAR"


# ---------------------------------------------------------------- water
def water_material():
    m = material("PCVE_Water", (1, 1, 1), 0.0, 0.0)
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]; out = nt.nodes["Material Output"]
    b.inputs["Transmission Weight"].default_value = 1.0; b.inputs["IOR"].default_value = 1.333
    ab = nt.nodes.new("ShaderNodeVolumeAbsorption")
    # absorption of clean water (1/m): red 0.35, green 0.06, blue 0.02
    ab.inputs["Color"].default_value = (*a.absorb, 1); ab.inputs["Density"].default_value = 1.0
    nt.links.new(ab.outputs["Volume"], out.inputs["Volume"])
    if True:
        lp = nt.nodes.new("ShaderNodeLightPath"); tr = nt.nodes.new("ShaderNodeBsdfTransparent"); mx = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(lp.outputs["Is Shadow Ray"], mx.inputs[0]); nt.links.new(b.outputs["BSDF"], mx.inputs[1]); nt.links.new(tr.outputs["BSDF"], mx.inputs[2])
        nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return m


water_mat = water_material()
water = bpy.data.objects.new("PCVE_Water", bpy.data.meshes.new("PCVE_WaterMesh")); scene.collection.objects.link(water)
water.data.materials.append(water_mat)


def points_object(name, mat):
    g = bpy.data.node_groups.new(name, "GeometryNodeTree")
    g.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    g.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n, l = g.nodes, g.links
    src, dst = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    pts = n.new("GeometryNodeMeshToPoints"); rad = n.new("GeometryNodeInputNamedAttribute")
    rad.data_type = "FLOAT"; rad.inputs["Name"].default_value = "radius"
    st = n.new("GeometryNodeSetMaterial"); st.inputs["Material"].default_value = mat
    l.new(src.outputs[0], pts.inputs["Mesh"]); l.new(rad.outputs["Attribute"], pts.inputs["Radius"])
    l.new(pts.outputs["Points"], st.inputs["Geometry"]); l.new(st.outputs["Geometry"], dst.inputs[0])
    o = bpy.data.objects.new(name, bpy.data.meshes.new(name)); scene.collection.objects.link(o)
    o.modifiers.new("Points", "NODES").node_group = g
    return o


def drop_material():
    """Droplets and beads: the water's surface without its volume. They are a few millimetres across, so their own
    absorption is nil; and with the water's volume the six overlapping spheres of each torn-off particle confuse Cycles'
    inside/outside bookkeeping, so rays leaving the splash keep absorbing through the air and the splash turns teal."""
    m = material("PCVE_WaterDrops", (1, 1, 1), 0.0, 0.0)
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]; out = nt.nodes["Material Output"]
    b.inputs["Transmission Weight"].default_value = 1.0; b.inputs["IOR"].default_value = 1.333
    lp = nt.nodes.new("ShaderNodeLightPath"); tr = nt.nodes.new("ShaderNodeBsdfTransparent"); mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Shadow Ray"], mx.inputs[0]); nt.links.new(b.outputs["BSDF"], mx.inputs[1]); nt.links.new(tr.outputs["BSDF"], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return m


spray = points_object("PCVE_Spray", drop_material())


def load_water(f):
    d = np.load(a.mesh_dir / f"water_{f:04d}.npz")
    v_, t_, n_, vel = d["vertices"], d["triangles"], d["normals"], d["velocity"]
    me = bpy.data.meshes.new(f"W{f}")
    me.vertices.add(len(v_)); me.vertices.foreach_set("co", v_.ravel())
    me.loops.add(t_.size); me.loops.foreach_set("vertex_index", t_.ravel())
    me.polygons.add(len(t_)); me.polygons.foreach_set("loop_start", np.arange(0, t_.size, 3)); me.polygons.foreach_set("loop_total", np.full(len(t_), 3))
    me.update()
    me.polygons.foreach_set("use_smooth", np.ones(len(t_), bool))
    me.normals_split_custom_set_from_vertices(n_.astype(float).tolist())
    if not a.no_motion_blur:
        me.attributes.new("velocity", "FLOAT_VECTOR", "POINT").data.foreach_set("vector", vel.ravel())
    me.materials.append(water_mat)
    old = water.data; water.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    d = np.load(a.mesh_dir / f"spray_{f:04d}.npz")
    pos, rad, vel = d["position"], d["radius"], d["velocity"]
    if car_wet_now and "kind" in d.files:            # the car's beads are in its paint
        keep = d["kind"] != 2
        pos, rad, vel = pos[keep], rad[keep], vel[keep]
    me = bpy.data.meshes.new(f"S{f}")
    me.vertices.add(len(pos)); me.vertices.foreach_set("co", pos.ravel())
    me.attributes.new("radius", "FLOAT", "POINT").data.foreach_set("value", rad)
    if not a.no_motion_blur:
        me.attributes.new("velocity", "FLOAT_VECTOR", "POINT").data.foreach_set("vector", vel.ravel())
    me.update()
    old = spray.data; spray.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)


# ---------------------------------------------------------------- daylight through the virtual window at y = -1
world = bpy.data.worlds.new("PCVE_World"); world.use_nodes = True; scene.world = world
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs["Color"].default_value = (0.72, 0.80, 0.95, 1); bg.inputs["Strength"].default_value = a.world


def area(name, loc, target, size, energy, color, spread=None):
    L = bpy.data.lights.new(name, "AREA"); L.shape = "RECTANGLE"; L.size = size[0]; L.size_y = size[1]; L.energy = energy; L.color = color
    if spread is not None:
        L.spread = math.radians(spread)
    o = bpy.data.objects.new(name, L); scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


win = area("PCVE_WindowSky", (-1.2, -0.97, 1.55), (-1.2, 1.0, 1.1), (1.3, 1.5), a.window, (0.86, 0.92, 1.0))
beam = area("PCVE_SunBeam", (-1.05, -0.92, 1.95), (0.05, -0.15, 0.42), (1.2, 1.2), a.beam, (1.0, 0.93, 0.82), a.beam_spread)

# the light pattern multiplies the ceramic's colour under the water (a per-frame image over the surface grid)
tub_mat = bpy.data.objects["PCVE_BathtubShell"].material_slots[0].material
_nt = tub_mat.node_tree
_b = next(n for n in _nt.nodes if n.type == "BSDF_PRINCIPLED")
_geo = _nt.nodes.new("ShaderNodeNewGeometry")
_map = _nt.nodes.new("ShaderNodeMapping"); _map.vector_type = "POINT"
_tex = _nt.nodes.new("ShaderNodeTexImage"); _tex.extension = "EXTEND"; _tex.interpolation = "Linear"
_gain = _nt.nodes.new("ShaderNodeMapRange"); _gain.inputs["From Min"].default_value = 1.0; _gain.inputs["From Max"].default_value = 2.0
_gain.inputs["To Min"].default_value = 0.0; _gain.inputs["To Max"].default_value = a.caustics; _gain.clamp = False
_nt.links.new(_geo.outputs["Position"], _map.inputs["Vector"])
_nt.links.new(_map.outputs["Vector"], _tex.inputs["Vector"])
_sep = _nt.nodes.new("ShaderNodeSeparateColor")
_nt.links.new(_tex.outputs["Color"], _sep.inputs["Color"])
_nt.links.new(_sep.outputs[0], _gain.inputs["Value"])
_clamp = _nt.nodes.new("ShaderNodeMath"); _clamp.operation = "MAXIMUM"; _clamp.inputs[1].default_value = 0.0
_nt.links.new(_gain.outputs["Result"], _clamp.inputs[0])
_b.inputs["Emission Color"].default_value = (1.0, 0.96, 0.88, 1)
_nt.links.new(_clamp.outputs[0], _b.inputs["Emission Strength"])
# wet ceramic (green channel): glossier and a little darker, with an uneven edge and runs down the wall
_noise = _nt.nodes.new("ShaderNodeTexNoise"); _noise.inputs["Scale"].default_value = 1.0; _noise.inputs["Detail"].default_value = 5.0
_stretch = _nt.nodes.new("ShaderNodeVectorMath"); _stretch.operation = "MULTIPLY"; _stretch.inputs[1].default_value = (260, 260, 45)
_nt.links.new(_geo.outputs["Position"], _stretch.inputs[0]); _nt.links.new(_stretch.outputs["Vector"], _noise.inputs["Vector"])
_add = _nt.nodes.new("ShaderNodeMath"); _add.operation = "MULTIPLY_ADD"; _add.inputs[1].default_value = 0.5; _add.inputs[2].default_value = -0.25
_nt.links.new(_noise.outputs["Fac"], _add.inputs[0])
_sum = _nt.nodes.new("ShaderNodeMath"); _sum.operation = "ADD"
_nt.links.new(_sep.outputs[1], _sum.inputs[0]); _nt.links.new(_add.outputs[0], _sum.inputs[1])
_edge = _nt.nodes.new("ShaderNodeMapRange"); _edge.interpolation_type = "SMOOTHSTEP"
_edge.inputs["From Min"].default_value = 0.42; _edge.inputs["From Max"].default_value = 0.58
_nt.links.new(_sum.outputs[0], _edge.inputs["Value"])
# only the inside of the tub gets wet: the map is over (x, y), and the outer wall stands under the same cells
_rad = _nt.nodes.new("ShaderNodeVectorMath"); _rad.operation = "SUBTRACT"; _rad.inputs[1].default_value = (0.0132777, 0.0108457, 0.0)
_nt.links.new(_geo.outputs["Position"], _rad.inputs[0])
_flat = _nt.nodes.new("ShaderNodeVectorMath"); _flat.operation = "MULTIPLY"; _flat.inputs[1].default_value = (1, 1, 0)
_nt.links.new(_rad.outputs[0], _flat.inputs[0])
_unit = _nt.nodes.new("ShaderNodeVectorMath"); _unit.operation = "NORMALIZE"
_nt.links.new(_flat.outputs[0], _unit.inputs[0])
_dot = _nt.nodes.new("ShaderNodeVectorMath"); _dot.operation = "DOT_PRODUCT"
_nt.links.new(_unit.outputs[0], _dot.inputs[0]); _nt.links.new(_geo.outputs["Normal"], _dot.inputs[1])
_inside = _nt.nodes.new("ShaderNodeMapRange"); _inside.inputs["From Min"].default_value = 0.1; _inside.inputs["From Max"].default_value = 0.35
_inside.inputs["To Min"].default_value = 1.0; _inside.inputs["To Max"].default_value = 0.0
_nt.links.new(_dot.outputs["Value"], _inside.inputs["Value"])
_wet_in = _nt.nodes.new("ShaderNodeMath"); _wet_in.operation = "MULTIPLY"
_nt.links.new(_edge.outputs[0], _wet_in.inputs[0]); _nt.links.new(_inside.outputs[0], _wet_in.inputs[1])
_dry_rough, _dry_coat = _b.inputs["Roughness"].default_value, _b.inputs["Coat Weight"].default_value
_rough = _nt.nodes.new("ShaderNodeMix"); _rough.data_type = "FLOAT"
_rough.inputs["A"].default_value = _dry_rough; _rough.inputs["B"].default_value = 0.05
_nt.links.new(_wet_in.outputs[0], _rough.inputs["Factor"]); _nt.links.new(_rough.outputs["Result"], _b.inputs["Roughness"])
_coat = _nt.nodes.new("ShaderNodeMix"); _coat.data_type = "FLOAT"
_coat.inputs["A"].default_value = _dry_coat; _coat.inputs["B"].default_value = 0.9
_nt.links.new(_wet_in.outputs[0], _coat.inputs["Factor"]); _nt.links.new(_coat.outputs["Result"], _b.inputs["Coat Weight"])
_col = _nt.nodes.new("ShaderNodeMix"); _col.data_type = "RGBA"
_c0 = tuple(_b.inputs["Base Color"].default_value)
_col.inputs["A"].default_value = _c0; _col.inputs["B"].default_value = (_c0[0] * 0.90, _c0[1] * 0.90, _c0[2] * 0.91, 1)
_nt.links.new(_wet_in.outputs[0], _col.inputs["Factor"]); _nt.links.new(_col.outputs["Result"], _b.inputs["Base Color"])
# beads on wet ceramic are flat caps: a bump with fine highlights (glass spheres would refract dark rims on the white glaze)
_vor = _nt.nodes.new("ShaderNodeTexVoronoi"); _vor.feature = "F1"; _vor.inputs["Scale"].default_value = 420.0; _vor.inputs["Randomness"].default_value = 1.0
_nt.links.new(_geo.outputs["Position"], _vor.inputs["Vector"])
_cap = _nt.nodes.new("ShaderNodeMapRange"); _cap.interpolation_type = "SMOOTHSTEP"
_cap.inputs["From Min"].default_value = 0.42; _cap.inputs["From Max"].default_value = 0.10
_nt.links.new(_vor.outputs["Distance"], _cap.inputs["Value"])
_keep = _nt.nodes.new("ShaderNodeMapRange"); _keep.interpolation_type = "SMOOTHSTEP"          # not every cell holds a bead
_keep.inputs["From Min"].default_value = 0.62; _keep.inputs["From Max"].default_value = 0.72
_nt.links.new(_vor.outputs["Color"], _keep.inputs["Value"])
_m1 = _nt.nodes.new("ShaderNodeMath"); _m1.operation = "MULTIPLY"; _m2 = _nt.nodes.new("ShaderNodeMath"); _m2.operation = "MULTIPLY"
_nt.links.new(_cap.outputs[0], _m1.inputs[0]); _nt.links.new(_keep.outputs[0], _m1.inputs[1])
_nt.links.new(_m1.outputs[0], _m2.inputs[0]); _nt.links.new(_wet_in.outputs[0], _m2.inputs[1])
_bump = _nt.nodes.new("ShaderNodeBump"); _bump.inputs["Strength"].default_value = 0.8; _bump.inputs["Distance"].default_value = 0.0007
_nt.links.new(_m2.outputs[0], _bump.inputs["Height"])
_nt.links.new(_bump.outputs["Normal"], _b.inputs["Normal"]); _nt.links.new(_bump.outputs["Normal"], _b.inputs["Coat Normal"])
_image = {"current": None}


def load_caustic(f):
    p = a.mesh_dir / f"caustic_{f:04d}.npy"
    if not p.exists() or a.caustics <= 0:
        return
    I = np.load(p).astype(np.float32)               # (x, y) on the surface grid
    nx, ny = I.shape
    # surface grid of surface_toy_car_float_bathtub.py: x from -0.46, y from -0.95, cell 2 mm
    x0, y0, cell = -0.46, -0.95, 0.002
    _map.inputs["Scale"].default_value = (1 / (nx * cell), 1 / (ny * cell), 1)
    _map.inputs["Location"].default_value = (-x0 / (nx * cell), -y0 / (ny * cell), 0)
    im = bpy.data.images.new(f"Caustic{f}", nx, ny, alpha=False, float_buffer=True, is_data=True)
    rgba = np.ones((ny, nx, 4), np.float32); rgba[..., 0] = I.T
    p_w = a.mesh_dir / f"wet_{f:04d}.npy"
    rgba[..., 1] = np.load(p_w).astype(np.float32).T if p_w.exists() else 0.0
    im.pixels.foreach_set(rgba.ravel())
    im.colorspace_settings.is_data = True
    _tex.image = im
    if _image["current"] is not None:
        bpy.data.images.remove(_image["current"])
    _image["current"] = im


# ---------------------------------------------------------------- camera and Cycles
bpy.ops.object.camera_add(location=a.camera)
cam = bpy.context.object; cam.data.lens = a.lens; cam.data.sensor_width = 36
cam.rotation_euler = (Vector(a.target) - Vector(a.camera)).to_track_quat("-Z", "Y").to_euler()
scene.camera = cam
r = scene.render
r.resolution_x, r.resolution_y = a.resolution; r.resolution_percentage = 100; r.fps = 24
r.image_settings.file_format = "PNG"; r.image_settings.color_mode = "RGB"
r.use_motion_blur = not a.no_motion_blur; r.motion_blur_shutter = 0.5
scene.view_settings.look = a.look; scene.view_settings.exposure = a.exposure
r.engine = "CYCLES"
c = scene.cycles
c.samples = a.samples; c.use_denoising = True; c.device = "GPU"; c.max_bounces = 12; c.transmission_bounces = 12; c.transparent_max_bounces = 12
c.sample_clamp_indirect = 10.0; c.blur_glossy = 0.5; c.caustics_reflective = False; c.caustics_refractive = True
# a white tub lights itself: light that bounced off the dry wall has to get through the water surface, and back out of it
for _l in (win, beam):
    _l.visible_transmission = False                 # the lamps reach the water through the shadow rays; only their bounce comes through here
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"; prefs.get_devices()
for dev in prefs.devices:
    dev.use = dev.type == "OPTIX"
if a.no_water:
    water.hide_render = True

for f in a.frames:
    t0 = time.time()
    if not a.no_water:
        load_water(f)
        load_caustic(f)
    for n_ in car_wet_now:
        n_.outputs[0].default_value = f
    scene.frame_set(f)
    r.filepath = str(a.out / f"frame_{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", f, round(time.time() - t0, 1), flush=True)
