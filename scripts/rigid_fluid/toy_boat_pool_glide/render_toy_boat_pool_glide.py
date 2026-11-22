"""Render the toy boat glide: the Sketchfab kiddie pool and toy tug on a sunlit back-garden lawn,
with the water surface reconstructed from the Genesis particles.

Blender 4.3, from the repository root:

    blender -b --factory-startup --python scripts/rigid_fluid/toy_boat_pool_glide/render_toy_boat_pool_glide.py -- \
        --run <run dir> --out-dir <dir> [--survey] [--frames 1 24 48] [--camera NAME ...]

`--survey` renders every camera candidate at the given frames, small and fast, for choosing the shot.
"""
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

import argparse
import json
import math
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

ROOT = Path.cwd()
ASSETS = ROOT / "assets"
SHIP_GLB = ASSETS / "sketchfab/toy_ship/source/toy_ship.glb"
POOL_GLB = ASSETS / "sketchfab/inflatable_swimming_pool/source/inflatable_swimming_pool.glb"
SHIP_FRAME = json.loads((ASSETS / "sketchfab/toy_ship/prepared/boat_frame.json").read_text())
POOL = json.loads((ASSETS / "sketchfab/inflatable_swimming_pool/prepared/pool_profile.json").read_text())
# Sunny rose garden: a real sun at 49 deg (residential_garden is overcast, peak radiance 10).
HDRI = ASSETS / "polyhaven/sunny_rose_garden/sunny_rose_garden_8k.hdr"
HDRI_PROBE = ASSETS / "polyhaven/sunny_rose_garden/sunny_rose_garden_1k.hdr"
LAWN = ASSETS / "polyhaven/leafy_grass"
GRASS_MODELS = [ASSETS / "polyhaven_models/grass_medium_01/grass_medium_01_1k.gltf",
                ASSETS / "polyhaven_models/grass_bermuda_01/grass_bermuda_01_1k.gltf"]
DANDELION = ASSETS / "polyhaven_models/dandelion_01/dandelion_01_1k.gltf"
POOL_OUTER_RADIUS = 0.5 * POOL["outer_diameter_m"]
GRASS_HEIGHT = {"grass_medium_01_1k": 0.11, "grass_bermuda_01_1k": 0.07, "dandelion_01_1k": 0.13}  # m, mown lawn
GRASS_DENSITY = 900.0  # clumps per m^2 within GRASS_RADIUS
GRASS_SHARE = {"grass_bermuda_01_1k": 0.0, "grass_medium_01_1k": 0.06, "dandelion_01_1k": 0.002}
LAWN_STRANDS = 120_000  # parent hairs within GRASS_RADIUS; each grows HAIR_CHILDREN interpolated children
HAIR_CHILDREN = 30
BLADE_LENGTH = 0.055
GRASS_RADIUS = 5.0
SEED = 20261023

# Camera candidates: location, look-at target, focal length (mm), framed for the 1.20 m pool (rim top
# 0.365 m, water 0.222 m) and scaled with the pool about its centre, so the composition stays put.
CAMERA_SCALE = POOL["outer_diameter_m"] / 1.20
CAMERAS_120 = {
    "side_high": ((0.00, -2.20, 0.95), (0.00, 0.00, 0.20), 35),
    "side_low": ((0.00, -1.80, 0.70), (0.00, 0.00, 0.24), 40),
    "front_quarter": ((1.35, -1.55, 0.90), (0.00, 0.00, 0.20), 35),
    "rear_quarter": ((-1.55, -1.35, 0.95), (0.05, 0.00, 0.20), 35),
    "standing": ((0.30, -1.55, 1.45), (0.00, 0.00, 0.20), 35),
    "kneeling_rim": ((0.20, -1.05, 0.62), (0.00, 0.05, 0.22), 28),
    "head_on": ((1.90, -0.35, 0.85), (0.00, 0.00, 0.22), 40),
    "long_lens": ((0.50, -3.80, 1.25), (0.00, 0.00, 0.22), 70),
}
CAMERAS = CAMERAS_120


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--surface-dir-name", default="surface")
    p.add_argument("--frames", type=int, nargs="*")
    p.add_argument("--camera", nargs="*", default=None)
    p.add_argument("--survey", action="store_true")
    p.add_argument("--resolution", type=int, nargs=2, default=(1280, 720))
    p.add_argument("--samples", type=int, default=64)
    return p.parse_args(argv)


def import_gltf(path, name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    for o in new:
        if o.parent is None:
            o.parent = root
    return root, new


def pbr_material(name, folder, stem, scale, displacement=0.0):
    """Poly Haven texture set (diff / nor_gl / rough [/ disp]) on world-space-scaled box mapping."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes["Principled BSDF"]
    coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (scale, scale, scale)
    links.new(coord.outputs["Object"], mapping.inputs["Vector"])

    def tex(suffix, non_color):
        node = nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(str(folder / f"{stem}_{suffix}_2k.jpg"), check_existing=True)
        if non_color:
            node.image.colorspace_settings.name = "Non-Color"
        links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        return node

    links.new(tex("diff", False).outputs["Color"], bsdf.inputs["Base Color"])
    links.new(tex("rough", True).outputs["Color"], bsdf.inputs["Roughness"])
    normal = nodes.new("ShaderNodeNormalMap")
    links.new(tex("nor_gl", True).outputs["Color"], normal.inputs["Color"])
    links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])
    if displacement:
        disp = nodes.new("ShaderNodeDisplacement")
        disp.inputs["Scale"].default_value = displacement
        links.new(tex("disp", True).outputs["Color"], disp.inputs["Height"])
        links.new(disp.outputs["Displacement"], nodes["Material Output"].inputs["Displacement"])
        mat.cycles.displacement_method = "BOTH"
    return mat


def hdri_sun_direction():
    """Direction to the brightest region of the HDRI (equirectangular, Blender's world mapping)."""
    img = bpy.data.images.load(str(HDRI_PROBE), check_existing=True)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)[..., :3].sum(axis=2)
    y, x = np.unravel_index(np.argmax(px), px.shape)  # Blender pixel rows start at the bottom
    u, v = (x + 0.5) / w, (y + 0.5) / h
    # Inverse of Blender's equirectangular lookup: u = atan2(d.y, -d.x) / 2pi + 0.5, v = asin(d.z) / pi + 0.5.
    azimuth = (u - 0.5) * 2 * math.pi
    elevation = (v - 0.5) * math.pi
    direction = Vector((-math.cos(elevation) * math.cos(azimuth), math.cos(elevation) * math.sin(azimuth),
                        math.sin(elevation)))
    return direction.normalized(), math.degrees(elevation)


def setup_world(scene):
    world = bpy.data.worlds.new("PCVE_GardenWorld")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(HDRI), check_existing=True)
    nt.links.new(env.outputs["Color"], nt.nodes["Background"].inputs["Color"])
    nt.nodes["Background"].inputs["Strength"].default_value = 1.0
    # The HDRI's own sun lights the scene (no extra lamp); its direction is recorded for reference.
    direction, elevation = hdri_sun_direction()
    return {"hdri": str(HDRI.relative_to(ROOT)), "sun_direction": list(direction), "sun_elevation_deg": elevation}


def setup_lawn(scene):
    # Textured soil under the grass disc; beyond it a shadow catcher, so the HDRI's own garden fills the
    # distance (a flat far plane reads as an olive wall at the horizon) while still taking the shadows.
    n = 128
    ring = [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)) for i in range(n)]
    inner = GRASS_RADIUS + 0.2
    mesh = bpy.data.meshes.new("PCVE_Lawn")
    mesh.from_pydata([(0, 0, 0)] + [(inner * c, inner * s_, 0) for c, s_ in ring], [],
                     [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)])
    lawn = bpy.data.objects.new("PCVE_Lawn", mesh)
    scene.collection.objects.link(lawn)
    far = bpy.data.meshes.new("PCVE_FarGround")
    far.from_pydata([(inner * c, inner * s_, 0) for c, s_ in ring] + [(400 * c, 400 * s_, 0) for c, s_ in ring], [],
                    [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)])
    catcher = bpy.data.objects.new("PCVE_FarGround", far)
    scene.collection.objects.link(catcher)
    catcher.is_shadow_catcher = True
    mat = pbr_material("PCVE_LeafyGrass", LAWN, "leafy_grass", 0.55)  # soil seen between the blades
    # leafy_grass is weeds on sandy soil; pull it toward lawn green so the far field is not desert.
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    diffuse = bsdf.inputs["Base Color"].links[0].from_socket
    tint = nodes.new("ShaderNodeMix")
    tint.data_type = "RGBA"
    tint.blend_type = "MULTIPLY"
    tint.inputs["Factor"].default_value = 0.85
    tint.inputs["B"].default_value = (0.42, 0.62, 0.22, 1.0)
    links.new(diffuse, tint.inputs["A"])
    links.new(tint.outputs["Result"], bsdf.inputs["Base Color"])
    lawn.data.materials.append(mat)
    scatter = {}
    for path in GRASS_MODELS + [DANDELION]:
        scatter[path.stem] = grass_variants(scene, path)
    disc = bpy.data.meshes.new("PCVE_LawnScatterDisc")
    n = 96
    disc.from_pydata([(0, 0, 0)] + [(GRASS_RADIUS * math.cos(2 * math.pi * i / n),
                                     GRASS_RADIUS * math.sin(2 * math.pi * i / n), 0) for i in range(n)],
                     [], [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)])
    holder = bpy.data.objects.new("PCVE_LawnScatter", disc)
    scene.collection.objects.link(holder)
    mod = holder.modifiers.new("scatter", "NODES")
    mod.node_group = lawn_scatter_nodes({k: c for k, c in scatter.items() if GRASS_SHARE[k] > 0})
    hair_lawn(scene)
    return {"lawn_texture": "Poly Haven leafy_grass (CC0), tinted to lawn green",
            "grass_scatter": {k: {"collection": c.name, "variants": len(c.objects)} for k, c in scatter.items()},
            "grass_density_per_m2": GRASS_DENSITY, "grass_radius_m": GRASS_RADIUS,
            "hair_lawn": {"parents": LAWN_STRANDS, "children_each": HAIR_CHILDREN, "blade_length_m": BLADE_LENGTH}}


def hair_lawn(scene):
    """Mown lawn as hair strands on a fine disc, weighted to zero under the pool."""
    n = 240
    xs = np.linspace(-GRASS_RADIUS, GRASS_RADIUS, n)
    verts = [(x, y, 0.0) for y in xs for x in xs]
    faces = [(j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i) for j in range(n - 1) for i in range(n - 1)]
    mesh = bpy.data.meshes.new("PCVE_LawnHairBase")
    mesh.from_pydata(verts, [], faces)
    base = bpy.data.objects.new("PCVE_LawnHair", mesh)
    scene.collection.objects.link(base)
    group = base.vertex_groups.new(name="density")
    for i, (x, y, _) in enumerate(verts):
        r = math.hypot(x, y)
        w = 0.0 if r < POOL_OUTER_RADIUS + 0.03 else (0.0 if r > GRASS_RADIUS else 1.0)
        group.add([i], w, "REPLACE")
    mod = base.modifiers.new("lawn", "PARTICLE_SYSTEM")
    ps = mod.particle_system
    ps.vertex_group_density = "density"
    st = ps.settings
    st.type = "HAIR"
    st.count = LAWN_STRANDS
    st.use_advanced_hair = True
    st.emit_from = "FACE"
    st.distribution = "RAND"
    st.use_even_distribution = True
    st.normal_factor = 1.0
    st.factor_random = 0.25  # blades lean
    st.length_random = 0.45
    st.child_type = "INTERPOLATED"
    st.rendered_child_count = HAIR_CHILDREN
    st.child_percent = 2  # viewport only
    st.child_length = 1.0
    st.child_length_threshold = 0.0
    st.roughness_1 = 0.012
    st.roughness_2 = 0.02
    st.roughness_endpoint = 0.004
    st.root_radius = 0.0012
    st.tip_radius = 0.0001
    st.radius_scale = 1.0
    st.use_close_tip = True
    base.data.materials.append(bpy.data.materials.new("PCVE_LawnBlades"))
    mat = base.data.materials[0]
    st.material_slot = mat.name  # the enum only lists slots that exist
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    info = nodes.new("ShaderNodeHairInfo")
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.020, 0.055, 0.010, 1.0)  # shaded roots
    ramp.color_ramp.elements[1].color = (0.20, 0.36, 0.06, 1.0)  # sunlit tips
    links.new(info.outputs["Intercept"], ramp.inputs["Fac"])
    jitter = nodes.new("ShaderNodeHueSaturation")
    random = nodes.new("ShaderNodeMath")
    random.operation = "MULTIPLY_ADD"
    random.inputs[1].default_value = 0.08
    random.inputs[2].default_value = 0.46
    links.new(info.outputs["Random"], random.inputs[0])
    links.new(random.outputs[0], jitter.inputs["Hue"])
    links.new(ramp.outputs["Color"], jitter.inputs["Color"])
    links.new(jitter.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.45
    add_leaf_translucency(mat, amount=0.40)
    # With advanced hair the strand length follows the emission velocity (and the emitter's size), not
    # hair_length: measure the evaluated strands and rescale the velocity factors to the blade length.
    for _ in range(3):
        bpy.context.view_layer.update()
        ev = base.evaluated_get(bpy.context.evaluated_depsgraph_get()).particle_systems[0]
        lengths = [(p.hair_keys[-1].co - p.hair_keys[0].co).length for p in ev.particles[:3000]]
        mean = float(np.mean(lengths))
        if abs(mean / BLADE_LENGTH - 1) < 0.05:
            break
        st.normal_factor *= BLADE_LENGTH / mean
        st.factor_random *= BLADE_LENGTH / mean
    base["mean_blade_length_m"] = mean
    if abs(mean / BLADE_LENGTH - 1) > 0.15:
        raise RuntimeError(f"lawn blades are {mean:.3f} m, wanted {BLADE_LENGTH} m")
    return base


def grass_variants(scene, path):
    """Each Poly Haven grass file is a row of separate clump variants.  Bake every variant into its own
    mesh, centred on its footprint, keel at z = 0 and scaled to mown-lawn height, in one collection."""
    root, objs = import_gltf(path, "src_" + path.stem)
    bpy.context.view_layer.update()
    coll = bpy.data.collections.new("PCVE_Grass_" + path.stem)
    scene.collection.children.link(coll)
    for o in objs:
        if o.type != "MESH":
            continue
        pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
        lo = Vector([min(p[i] for p in pts) for i in range(3)])
        hi = Vector([max(p[i] for p in pts) for i in range(3)])
        k = GRASS_HEIGHT[path.stem] / max(hi.z - lo.z, 1e-6)
        mesh = o.data.copy()
        mesh.transform(Matrix.Diagonal((k, k, k, 1.0))
                       @ Matrix.Translation((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)) @ o.matrix_world)
        v = bpy.data.objects.new(o.name + "_variant", mesh)
        coll.objects.link(v)
        v.location = (0, 0, -100)  # the template itself is out of view; instances reset to the point
    for o in objs + [root]:
        bpy.data.objects.remove(o)
    for mat in {slot.material for v in coll.objects for slot in v.material_slots if slot.material}:
        add_leaf_translucency(mat)
    return coll


def add_leaf_translucency(mat, amount=0.35):
    """Poly Haven's blades are opaque; real grass is lit through.  Mix in a translucent lobe of the leaf colour."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    out = nodes["Material Output"]
    translucent = nodes.new("ShaderNodeBsdfTranslucent")
    if bsdf.inputs["Base Color"].links:
        links.new(bsdf.inputs["Base Color"].links[0].from_socket, translucent.inputs["Color"])
    mix = nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = amount
    links.new(bsdf.outputs["BSDF"], mix.inputs[1])
    links.new(translucent.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])


def lawn_scatter_nodes(scatter):
    """Distribute grass clump instances over the scatter disc, outside the pool's footprint."""
    ng = bpy.data.node_groups.new("PCVE_LawnScatter", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gin, gout = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    join = N.new("GeometryNodeJoinGeometry")
    L.new(join.outputs[0], gout.inputs[0])
    position = N.new("GeometryNodeInputPosition")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(position.outputs[0], sep.inputs[0])
    flat = N.new("ShaderNodeCombineXYZ")
    L.new(sep.outputs["X"], flat.inputs["X"])
    L.new(sep.outputs["Y"], flat.inputs["Y"])
    radius = N.new("ShaderNodeVectorMath")
    radius.operation = "LENGTH"
    L.new(flat.outputs[0], radius.inputs[0])
    inside = N.new("FunctionNodeCompare")  # evaluated on the scattered points, not the disc's faces
    inside.data_type = "FLOAT"
    inside.operation = "LESS_THAN"
    inside.inputs["B"].default_value = POOL_OUTER_RADIUS + 0.02
    L.new(radius.outputs["Value"], inside.inputs["A"])
    for seed, (stem, coll) in enumerate(scatter.items()):
        dist = N.new("GeometryNodeDistributePointsOnFaces")
        dist.distribute_method = "RANDOM"
        dist.inputs["Density"].default_value = GRASS_DENSITY * GRASS_SHARE[stem]
        dist.inputs["Seed"].default_value = SEED + seed
        L.new(gin.outputs[0], dist.inputs["Mesh"])
        prune = N.new("GeometryNodeDeleteGeometry")
        prune.domain = "POINT"
        L.new(dist.outputs["Points"], prune.inputs["Geometry"])
        L.new(inside.outputs[0], prune.inputs["Selection"])
        info = N.new("GeometryNodeCollectionInfo")
        info.inputs["Collection"].default_value = coll
        info.inputs["Separate Children"].default_value = True
        info.inputs["Reset Children"].default_value = True
        inst = N.new("GeometryNodeInstanceOnPoints")
        inst.inputs["Pick Instance"].default_value = True
        pick = N.new("FunctionNodeRandomValue")
        pick.data_type = "INT"
        pick.inputs[4].default_value = 0  # integer Min / Max (the named sockets are the vector ones)
        pick.inputs[5].default_value = len(coll.objects) - 1
        pick.inputs["Seed"].default_value = SEED + 10 + seed
        turn = N.new("FunctionNodeRandomValue")
        turn.data_type = "FLOAT"
        turn.inputs[2].default_value = 0.0
        turn.inputs[3].default_value = 2 * math.pi
        turn.inputs["Seed"].default_value = SEED + 20 + seed
        euler = N.new("ShaderNodeCombineXYZ")
        L.new(turn.outputs[1], euler.inputs["Z"])
        size = N.new("FunctionNodeRandomValue")
        size.data_type = "FLOAT"
        size.inputs[2].default_value = 0.75
        size.inputs[3].default_value = 1.25
        size.inputs["Seed"].default_value = SEED + 30 + seed
        L.new(prune.outputs[0], inst.inputs["Points"])
        L.new(info.outputs[0], inst.inputs["Instance"])
        L.new(pick.outputs[2], inst.inputs["Instance Index"])
        L.new(euler.outputs[0], inst.inputs["Rotation"])
        L.new(size.outputs[1], inst.inputs["Scale"])
        L.new(inst.outputs[0], join.inputs[0])
    return ng


def setup_pool(scene):
    root, objs = import_gltf(POOL_GLB, "PCVE_Pool")
    s = POOL["scale"]
    root.matrix_world = Matrix.Diagonal((s, s, s, 1.0)) @ Matrix.Translation(POOL["glb_offset_before_scale"])
    water = [o for o in objs if o.name.startswith("Circle_Water")]
    objs = [o for o in objs if o not in water]
    for o in water:
        bpy.data.objects.remove(o)  # every visible liquid surface comes from Genesis
    for o in objs:
        if o.type == "MESH":
            for slot in o.material_slots:
                bsdf = slot.material.node_tree.nodes.get("Principled BSDF")
                if bsdf:  # glossy PVC
                    bsdf.inputs["Roughness"].default_value = 0.28
                    bsdf.inputs["Coat Weight"].default_value = 0.35
                    bsdf.inputs["Coat Roughness"].default_value = 0.12
    return root


def setup_ship(scene):
    root, objs = import_gltf(SHIP_GLB, "PCVE_ShipAsset")
    pose = bpy.data.objects.new("PCVE_BoatPose", None)
    scene.collection.objects.link(pose)
    pose.rotation_mode = "QUATERNION"
    s = SHIP_FRAME["scale"]
    root.parent = pose
    root.matrix_parent_inverse = Matrix.Identity(4)
    root.matrix_basis = (Matrix.Rotation(math.radians(SHIP_FRAME["rotation_z_deg_after_scale"]), 4, "Z")
                         @ Matrix.Diagonal((s, s, s, 1.0)) @ Matrix.Translation(SHIP_FRAME["glb_offset_before_scale"]))
    return pose, [o for o in objs if o.type == "MESH"]


def show(objects, visible):
    for o in objects:
        o.hide_render = o.hide_viewport = not visible


def water_material():
    mat = bpy.data.materials.new("PCVE_PoolWater")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    glass = nodes.new("ShaderNodeBsdfGlass")
    glass.inputs["Color"].default_value = (0.94, 0.985, 1.0, 1.0)
    glass.inputs["Roughness"].default_value = 0.02
    glass.inputs["IOR"].default_value = 1.333
    links.new(glass.outputs["BSDF"], out.inputs["Surface"])
    absorption = nodes.new("ShaderNodeVolumeAbsorption")
    absorption.inputs["Color"].default_value = (0.55, 0.88, 0.92, 1.0)
    absorption.inputs["Density"].default_value = 0.6
    links.new(absorption.outputs["Volume"], out.inputs["Volume"])
    return mat


def load_frame(run, surface_dir, frame, water_present):
    """Boat pose and whether it is in the scene, and the water surface (empty for an empty pool)."""
    with np.load(run / "particles" / f"frame_{frame:04d}.npz") as st:
        boat_pos, boat_quat = st["boat_pos"], st["boat_quat_wxyz"]
        boat_active = bool(st["boat_active"]) if "boat_active" in st else True
    if not water_present:
        empty = np.zeros((0, 3), np.float32)
        return boat_pos, boat_quat, boat_active, empty, np.zeros((0, 3), np.int32), empty
    with np.load(run / surface_dir / f"water_{frame:04d}.npz") as m:
        return boat_pos, boat_quat, boat_active, m["vertices"], m["triangles"], m["normals"]


def replace_water(obj, vertices, triangles, normals):
    mesh = bpy.data.meshes.new("PCVE_WaterMesh")
    mesh.from_pydata(vertices.tolist(), [], triangles.tolist())
    mesh.validate(clean_customdata=False)
    mesh.shade_smooth()
    if len(normals) == len(mesh.vertices):
        mesh.normals_split_custom_set_from_vertices(normals.tolist())
    old = obj.data
    obj.data = mesh
    mesh.materials.append(old.materials[0] if old.materials else None)
    if old.users == 0:
        bpy.data.meshes.remove(old)


def setup_render(scene, args):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
            break
        except Exception:
            pass
    for d in prefs.devices:
        d.use = d.type == prefs.compute_device_type
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.render.use_persistent_data = True  # reuse static garden BVHs across frames
    scene.cycles.max_bounces = 12
    scene.cycles.transmission_bounces = 10
    scene.cycles.caustics_refractive = True
    scene.cycles.caustics_reflective = True
    scene.render.resolution_x, scene.render.resolution_y = args.resolution
    scene.render.fps = 24
    scene.render.use_motion_blur = False
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Base Contrast"


def main():
    args = parse_args()
    run = args.run.resolve()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    record = {"world": setup_world(scene)}
    # The garden (appearance/realism_environment_toy_boat.py) builds on the backyard of
    # appearance/garden_environment_toy_boat.py, which lays its lawn with setup_lawn() of this module.
    import importlib.util
    module_path = Path(__file__).parent / "appearance/realism_environment_toy_boat.py"
    spec = importlib.util.spec_from_file_location("toy_boat_garden", module_path)
    garden = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(garden)
    record["garden"] = garden.build(scene, sys.modules[__name__])
    record["environment"] = "garden"
    setup_pool(scene)
    record["pvc"] = garden.soften_pvc()
    pose, ship_meshes = setup_ship(scene)
    water = bpy.data.objects.new("PCVE_Water", bpy.data.meshes.new("PCVE_WaterMesh"))
    scene.collection.objects.link(water)
    water.data.materials.append(water_material())
    cam = bpy.data.objects.new("PCVE_Camera", bpy.data.cameras.new("PCVE_Camera"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    setup_render(scene, args)

    report = json.loads((run / "simulation_report.json").read_text())
    water_present = report["physics"].get("water_presence", [1]) == [1]
    frames = args.frames or list(range(1, int(report["numerics"]["frames"]) + 1))
    cameras = args.camera or (list(CAMERAS) if args.survey else ["side_high"])
    rows = []
    for frame in frames:
        boat_pos, boat_quat, boat_active, v, t, n = load_frame(run, args.surface_dir_name, frame, water_present)
        pose.location = boat_pos.tolist()
        pose.rotation_quaternion = Quaternion(boat_quat.tolist())
        show(ship_meshes, boat_active)
        replace_water(water, v, t, n)
        for name in cameras:
            loc, target, lens = CAMERAS[name]
            loc, target = tuple(CAMERA_SCALE * c for c in loc), tuple(CAMERA_SCALE * c for c in target)
            cam.location = loc
            cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
            cam.data.lens = lens
            # Focus on the pool's middle with a mild aperture: the background softens like a real lens.
            cam.data.dof.use_dof = True
            cam.data.dof.focus_distance = (Vector(target) - Vector(loc)).length
            cam.data.dof.aperture_fstop = 4.0
            path = out / (f"{name}_f{frame:03d}.png" if args.survey else f"frames/frame_{frame:04d}.png")
            path.parent.mkdir(parents=True, exist_ok=True)
            scene.render.filepath = str(path)
            tick = time.monotonic()
            bpy.ops.render.render(write_still=True)
            rows.append({"frame": frame, "camera": name, "file": path.name, "seconds": time.monotonic() - tick})
            print("RENDERED", json.dumps(rows[-1]), flush=True)
    record["renders"] = rows
    (out / "render_report.json").write_text(json.dumps(record, indent=2) + "\n")
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "scene.blend"))


main()
