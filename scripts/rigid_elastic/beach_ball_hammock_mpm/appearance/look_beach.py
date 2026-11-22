"""Photographic beach appearance for the MPM hammock scene.

The stylised Sketchfab diorama is replaced by a measured beach built from CC0 scans: a
displaced aerial sand scan over a gently sloping beach, a Poly Haven sky (the sun is part of
the HDRI), the sea, two weathered timber posts and twisted ropes, and a woven striped hammock.
The MPM shell keeps its shape keys and is hidden from all ray types; a finer open fabric sheet is
bound to it with a Surface Deform modifier, so every visible hammock vertex follows the solver
surface. The MPM cache and the ball trajectory are not changed.

Settings read from appearance/appearance.json: terrain.sea_side = "away_from_camera" puts the sea
beyond the shoreline as seen from the camera; sea.animate = false freezes the sea at its frame-1
state; camera.override is a lower, level camera that shows palms, beach umbrellas, deck chairs and
the still sea in the background; terrain.detail_max_distance_m limits how far the displaced sand
reaches for a camera that sees the horizon; appearance.props places static set dressing by world
position (`xy`, `shadow_target_xy`) with a keep-out area around the hammock and the ball's fall
(`keep_out_xy`), so that nothing in the frame moves except the ball and the hammock.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

SCENE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENE_DIR.parents[1]))
from pcve_assets import asset  # noqa: E402

HAMMOCK = "Hammock_ElasticBody_ORIGINAL"
BALL = "BeachBall_RigidBody"
DEFAULT_CONFIG = SCENE_DIR / "appearance" / "appearance.json"


# --------------------------------------------------------------------------- helpers
def load_config(path=None):
    return json.loads(Path(path or DEFAULT_CONFIG).read_text(encoding="utf-8"))


def image(rel, colorspace="sRGB"):
    im = bpy.data.images.load(str(asset(rel)), check_existing=True)
    im.colorspace_settings.name = colorspace
    return im


def new_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (900, 0)
    return mat, nt, out


def node(nt, kind, x=0, y=0, **props):
    n = nt.nodes.new(kind)
    n.location = (x, y)
    for k, v in props.items():
        setattr(n, k, v)
    return n


def sock(n, name, kind="inputs"):
    """First enabled socket called `name` (Mix nodes expose several A/B sockets)."""
    for s in getattr(n, kind):
        if s.name == name and s.enabled:
            return s
    raise KeyError(f"{n.bl_idname}.{kind}[{name}]")


def link(nt, a, b):
    nt.links.new(a, b)


def mix(nt, data_type, fac, a, b, x=0, y=0, blend="MIX"):
    m = node(nt, "ShaderNodeMix", x, y, data_type=data_type)
    if data_type == "RGBA":
        m.blend_type = blend
    for socket, value in ((sock(m, "Factor"), fac), (sock(m, "A"), a), (sock(m, "B"), b)):
        if isinstance(value, bpy.types.NodeSocket):
            link(nt, value, socket)
        else:
            socket.default_value = value
    return sock(m, "Result", "outputs")


def math_node(nt, op, a, b=None, x=0, y=0, clamp=False):
    m = node(nt, "ShaderNodeMath", x, y, operation=op, use_clamp=clamp)
    for i, value in enumerate((a, b)):
        if value is None:
            continue
        if isinstance(value, bpy.types.NodeSocket):
            link(nt, value, m.inputs[i])
        else:
            m.inputs[i].default_value = value
    return m.outputs[0]


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def normal_dx(nt, tex_color, x, y, strength=1.0, uv_map=""):
    """ambientCG NormalDX -> OpenGL convention (flip green) -> tangent-space normal."""
    sep = node(nt, "ShaderNodeSeparateColor", x, y)
    link(nt, tex_color, sep.inputs[0])
    inv = math_node(nt, "SUBTRACT", 1.0, sep.outputs[1], x + 150, y - 60)
    comb = node(nt, "ShaderNodeCombineColor", x + 300, y)
    link(nt, sep.outputs[0], comb.inputs[0])
    link(nt, inv, comb.inputs[1])
    link(nt, sep.outputs[2], comb.inputs[2])
    nm = node(nt, "ShaderNodeNormalMap", x + 450, y, space="TANGENT", uv_map=uv_map)
    nm.inputs["Strength"].default_value = strength
    link(nt, comb.outputs[0], nm.inputs["Color"])
    return nm.outputs[0]


def mesh_object(name, verts, faces, uvs=None, smooth=True, collection=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v)) for v in verts], [], [tuple(f) for f in faces])
    me.update()
    if uvs is not None:
        layer = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li in poly.loop_indices:
                layer.data[li].uv = uvs[me.loops[li].vertex_index]
    if smooth:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    obj = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def parallel_frames(points):
    pts = [Vector(p) for p in points]
    tangents = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tangents.append((b - a).normalized())
    ref = Vector((0, 0, 1)) if abs(tangents[0].z) < 0.9 else Vector((1, 0, 0))
    normal = tangents[0].cross(ref).normalized()
    frames = []
    for i, t in enumerate(tangents):
        if i:
            normal = (normal - t * normal.dot(t)).normalized()
        frames.append((t, normal, t.cross(normal).normalized()))
    return pts, frames


def tube(name, points, radius, sides=12, material=None, collection=None, radius_fn=None):
    """Swept circular tube with parallel-transport frames. UV: u around, v along (in circumferences)."""
    pts, frames = parallel_frames(points)
    verts, uvs, faces = [], [], []
    length = 0.0
    circ = 2.0 * math.pi * radius
    for i, (p, (t, n, b)) in enumerate(zip(pts, frames)):
        if i:
            length += (p - pts[i - 1]).length
        r = radius * (radius_fn(i / max(len(pts) - 1, 1)) if radius_fn else 1.0)
        for k in range(sides + 1):
            a = 2.0 * math.pi * k / sides
            verts.append(p + (n * math.cos(a) + b * math.sin(a)) * r)
            uvs.append((k / sides, length / (0.5 * circ)))
    ring = sides + 1
    for i in range(len(pts) - 1):
        for k in range(sides):
            a0 = i * ring + k
            faces.append((a0, a0 + 1, a0 + ring + 1, a0 + ring))
    # end caps
    for end in (0, len(pts) - 1):
        c = len(verts)
        verts.append(pts[end])
        uvs.append((0.5, 0.0))
        base = end * ring
        for k in range(sides):
            f = (base + k, base + k + 1, c)
            faces.append(f if end else f[::-1])
    obj = mesh_object(name, verts, faces, uvs, collection=collection)
    if material:
        obj.data.materials.append(material)
    return obj


# --------------------------------------------------------------------------- scene cleanup
def clear_diorama(cfg):
    keep = set(cfg["appearance"]["keep_objects"])
    for name in list(keep):
        obj = bpy.data.objects.get(name)
        while obj is not None and obj.parent is not None:
            obj = obj.parent
            keep.add(obj.name)
    for obj in list(bpy.data.objects):
        if obj.name not in keep:
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)


# --------------------------------------------------------------------------- world
def build_world(cfg):
    w = cfg["appearance"]["world"]
    world = bpy.data.worlds.new("Beach_HDRI_World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    tc = node(nt, "ShaderNodeTexCoord", -900, 0)
    mp = node(nt, "ShaderNodeMapping", -700, 0, vector_type="POINT")
    rotation = math.radians(w["sun_in_hdri_azimuth_deg"] - w["sun_world_azimuth_deg"])
    mp.inputs["Rotation"].default_value = (0.0, 0.0, rotation)
    env = node(nt, "ShaderNodeTexEnvironment", -450, 0, interpolation="Cubic")
    env.image = image(w["hdri"], "Linear Rec.709")
    bg = node(nt, "ShaderNodeBackground", -150, 0)
    bg.inputs["Strength"].default_value = w["strength"]
    out = node(nt, "ShaderNodeOutputWorld", 100, 0)
    link(nt, tc.outputs["Generated"], mp.inputs["Vector"])
    link(nt, mp.outputs[0], env.inputs["Vector"])
    link(nt, env.outputs["Color"], bg.inputs["Color"])
    link(nt, bg.outputs[0], out.inputs["Surface"])
    world.cycles.sampling_method = "MANUAL"
    world.cycles.sample_map_resolution = 2048
    az = math.radians(w["sun_world_azimuth_deg"])
    el = math.radians(w["sun_in_hdri_elevation_deg"])
    return Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))


# --------------------------------------------------------------------------- terrain
class Beach:
    """Beach height field: dry sand rising from the waterline, seabed sloping below it."""

    def __init__(self, cfg, scene):
        t = cfg["appearance"]["terrain"]
        self.t = t
        cam = scene.camera
        tr, br, bl, tl = cam.data.view_frame(scene=scene)
        origin = cam.matrix_world.translation
        hits = []
        for px, py in t["shoreline_pixels"]:
            p = tl + (tr - tl) * (px / scene.render.resolution_x) + (bl - tl) * (py / scene.render.resolution_y)
            d = (cam.matrix_world.to_3x3() @ p).normalized()
            k = (t["sand_level_z_m"] - origin.z) / d.z
            if k <= 0:
                # a pixel at or above the horizon projects behind the camera
                raise ValueError(f"shoreline pixel {(px, py)} does not look down onto the sand")
            hits.append(np.array([(origin + d * k).x, (origin + d * k).y]))
        self.p1, p2 = hits
        along = (p2 - self.p1) / np.linalg.norm(p2 - self.p1)
        n = np.array([along[1], -along[0]])
        side = t.get("sea_side", "frame_top_left")
        if side == "frame_top_left":
            # seaward is the side that contains the far top-left corner of the frame
            p = tl
            d = (cam.matrix_world.to_3x3() @ p).normalized()
            k = (t["sand_level_z_m"] - origin.z) / d.z
            corner = np.array([(origin + d * k).x, (origin + d * k).y])
            if np.dot(corner - self.p1, n) < 0:
                n = -n
        elif side == "away_from_camera":
            # the camera stands on the beach; the sea lies beyond the shoreline (it may be out of frame)
            if np.dot(np.array([origin.x, origin.y]) - self.p1, n) > 0:
                n = -n
        else:
            raise ValueError(f"unknown terrain.sea_side {side!r}")
        self.sea_normal = n
        self.along = along
        rng = np.random.default_rng(cfg["appearance"]["seed"])
        self.waves = []
        for _ in range(6):
            ang = rng.uniform(0, 2 * math.pi)
            lam = t["undulation_wavelength_m"] * rng.uniform(0.6, 1.6)
            self.waves.append((math.cos(ang) * 2 * math.pi / lam, math.sin(ang) * 2 * math.pi / lam,
                               rng.uniform(0, 2 * math.pi), rng.uniform(0.5, 1.0)))
        norm = sum(w[3] for w in self.waves)
        self.waves = [(a, b, c, w / norm) for a, b, c, w in self.waves]
        self.sea_level = t["sand_level_z_m"] - t["beach_rise_m"]

    def inland(self, x, y):
        return -((x - self.p1[0]) * self.sea_normal[0] + (y - self.p1[1]) * self.sea_normal[1])

    def height(self, x, y):
        t = self.t
        d = self.inland(x, y)
        # ease-out beach face: finite slope at the waterline, flat on the upper beach
        tt = np.clip(d / t["beach_rise_width_m"], 0.0, 1.0)
        rise = 1.0 - (1.0 - tt) ** 2
        und = sum(w * np.sin(a * x + b * y + c) for a, b, c, w in self.waves)
        z = self.sea_level + t["beach_rise_m"] * rise + t["undulation_amplitude_m"] * und * rise
        return np.where(d < 0, self.sea_level + d * t["seabed_slope"], z)


def sand_material(cfg, beach):
    t = cfg["appearance"]["terrain"]
    mat, nt, out = new_material("Beach sand (Poly Haven aerial_sand scan)")
    base = t["texture"]
    uv = node(nt, "ShaderNodeTexCoord", -1800, 0)
    tile = 1.0 / t["texture_tile_m"]
    maps = []
    for i, (offset, rot) in enumerate(((0.0, 0.0), (0.3719, 0.6413))):
        mp = node(nt, "ShaderNodeMapping", -1600, 300 - i * 600)
        mp.inputs["Scale"].default_value = (tile, tile, 1.0)
        mp.inputs["Location"].default_value = (offset, rot, 0.0)
        mp.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(37.0) * i)
        link(nt, uv.outputs["UV"], mp.inputs["Vector"])
        maps.append(mp.outputs[0])
    def tex(name, colorspace, mp, x, y):
        n = node(nt, "ShaderNodeTexImage", x, y, interpolation="Cubic")
        n.image = image(f"{base}/{name}", colorspace)
        link(nt, mp, n.inputs["Vector"])
        return n
    dif = [tex("aerial_sand_diff_4k.jpg", "sRGB", m, -1300, 400 - i * 600) for i, m in enumerate(maps)]
    rou = [tex("aerial_sand_rough_4k.jpg", "Non-Color", m, -1300, 150 - i * 600) for i, m in enumerate(maps)]
    dsp = [tex("aerial_sand_disp_4k.exr", "Non-Color", m, -1300, -50 - i * 600) for i, m in enumerate(maps)]
    # blend mask between the two tilings (large-scale noise, sharpened)
    nz = node(nt, "ShaderNodeTexNoise", -1300, 700)
    nz.inputs["Scale"].default_value = 0.045
    nz.inputs["Detail"].default_value = 3.0
    link(nt, uv.outputs["UV"], nz.inputs["Vector"])
    mask = node(nt, "ShaderNodeMapRange", -1100, 700)
    mask.inputs["From Min"].default_value = 0.42
    mask.inputs["From Max"].default_value = 0.58
    link(nt, nz.outputs["Fac"], mask.inputs["Value"])
    m = mask.outputs[0]
    col = mix(nt, "RGBA", m, dif[0].outputs["Color"], dif[1].outputs["Color"], -900, 400)
    rgh = mix(nt, "FLOAT", m, rou[0].outputs["Color"], rou[1].outputs["Color"], -900, 100)
    hgt = mix(nt, "FLOAT", m, dsp[0].outputs["Color"], dsp[1].outputs["Color"], -900, -100)
    # macro brightness variation (patches of drier/whiter sand)
    nz2 = node(nt, "ShaderNodeTexNoise", -1100, 950)
    nz2.inputs["Scale"].default_value = 0.11
    nz2.inputs["Detail"].default_value = 4.0
    link(nt, uv.outputs["UV"], nz2.inputs["Vector"])
    var = node(nt, "ShaderNodeMapRange", -900, 950)
    var.inputs["To Min"].default_value = 0.90
    var.inputs["To Max"].default_value = 1.08
    link(nt, nz2.outputs["Fac"], var.inputs["Value"])
    col = mix(nt, "RGBA", 1.0, col, var.outputs[0], -700, 500, blend="MULTIPLY")
    col = mix(nt, "RGBA", 1.0, col, tuple(t["albedo_tint"]) + (1.0,), -550, 500, blend="MULTIPLY")
    # wet sand below the swash line, from world height
    geo = node(nt, "ShaderNodeNewGeometry", -1100, -400)
    sep = node(nt, "ShaderNodeSeparateXYZ", -950, -400)
    link(nt, geo.outputs["Position"], sep.inputs[0])
    wet = node(nt, "ShaderNodeMapRange", -800, -400)
    wet.inputs["From Min"].default_value = beach.sea_level + 0.32
    wet.inputs["From Max"].default_value = beach.sea_level + 0.06
    link(nt, sep.outputs["Z"], wet.inputs["Value"])
    wcol = mix(nt, "RGBA", 1.0, col, (0.52, 0.50, 0.46, 1.0), -400, 500, blend="MULTIPLY")
    col = mix(nt, "RGBA", wet.outputs[0], col, wcol, -250, 400)
    rgh = mix(nt, "FLOAT", wet.outputs[0], rgh, 0.38, -250, 100)
    bsdf = node(nt, "ShaderNodeBsdfPrincipled", 0, 200)
    link(nt, col, bsdf.inputs["Base Color"])
    link(nt, rgh, bsdf.inputs["Roughness"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.35
    disp = node(nt, "ShaderNodeDisplacement", 0, -250)
    disp.inputs["Midlevel"].default_value = 0.5
    disp.inputs["Scale"].default_value = t["displacement_scale_m"]
    link(nt, hgt, disp.inputs["Height"])
    link(nt, bsdf.outputs[0], out.inputs["Surface"])
    link(nt, disp.outputs[0], out.inputs["Displacement"])
    mat.displacement_method = "BOTH"
    return mat


def frustum_footprint(scene, z_near, z_far, margin, max_distance=None):
    """Camera footprint on the beach (near corners at z_near, far corners at z_far), grown by margin.

    With `max_distance` (a camera that sees the horizon), a corner whose ray does not reach the beach
    within that horizontal distance is placed at that distance along the ray's heading."""
    cam = scene.camera
    tr, br, bl, tl = cam.data.view_frame(scene=scene)
    o = cam.matrix_world.translation
    pts = []
    for corner, z in ((tl, z_far), (tr, z_far), (br, z_near), (bl, z_near)):
        d = (cam.matrix_world.to_3x3() @ corner).normalized()
        if max_distance is not None:
            h = Vector((d.x, d.y)).normalized()
            k = (z - o.z) / d.z if d.z < 0 else float("inf")
            reach = min(k * Vector((d.x, d.y)).length, max_distance)
            pts.append(np.array([o.x + h.x * reach, o.y + h.y * reach]))
            continue
        k = (z - o.z) / d.z
        pts.append(np.array([(o + d * k).x, (o + d * k).y]))
    poly = np.array(pts)
    c = poly.mean(axis=0)
    grown = []
    for i, p in enumerate(poly):
        # offset each vertex outward along the bisector of its two edges
        a, b = poly[i - 1], poly[(i + 1) % 4]
        e1 = (p - a) / np.linalg.norm(p - a)
        e2 = (b - p) / np.linalg.norm(b - p)
        n1 = np.array([e1[1], -e1[0]])
        n2 = np.array([e2[1], -e2[0]])
        if np.dot(n1, p - c) < 0:
            n1, n2 = -n1, -n2
        bis = (n1 + n2) / np.linalg.norm(n1 + n2)
        grown.append(p + bis * margin / max(np.dot(bis, n1), 0.3))
    return np.array(grown)


def inside(poly, x, y):
    res = np.zeros_like(x, dtype=bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cond = ((y1 > y) != (y2 > y)) & (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1)
        res ^= cond
    return res


def build_terrain(cfg, beach, scene):
    """Displaced sand where the camera sees it; a bump-mapped skirt of the same surface elsewhere."""
    t = cfg["appearance"]["terrain"]
    step = t["grid_step_m"]
    xs = np.arange(t["extent_x_m"][0], t["extent_x_m"][1] + 1e-6, step)
    ys = np.arange(t["extent_y_m"][0], t["extent_y_m"][1] + 1e-6, step)
    X, Y = np.meshgrid(xs, ys, indexing="xy")
    Z = beach.height(X, Y)
    verts = np.stack([X, Y, Z], axis=-1).reshape(-1, 3)
    nx = len(xs)
    poly = frustum_footprint(scene, t["sand_level_z_m"] + 0.3, beach.sea_level - 1.5, t["detail_margin_m"],
                             t.get("detail_max_distance_m"))
    cx = 0.5 * (X[:-1, :-1] + X[1:, 1:])
    cy = 0.5 * (Y[:-1, :-1] + Y[1:, 1:])
    detail = inside(poly, cx, cy)
    mat_detail = sand_material(cfg, beach)
    mat_skirt = mat_detail.copy()
    mat_skirt.name = "Beach sand skirt (bump only)"
    mat_skirt.displacement_method = "BUMP"
    objects = []
    for label, sel, mat in (("Detail", detail, mat_detail), ("Skirt", ~detail, mat_skirt)):
        faces = []
        jj, ii = np.nonzero(sel)
        for j, i in zip(jj, ii):
            a = j * nx + i
            faces.append((a, a + 1, a + nx + 1, a + nx))
        used = np.unique(np.array(faces).ravel())
        remap = -np.ones(len(verts), dtype=np.int64)
        remap[used] = np.arange(len(used))
        sub_verts = verts[used]
        sub_faces = [tuple(int(remap[k]) for k in f) for f in faces]
        uvs = [(float(v[0]), float(v[1])) for v in sub_verts]
        obj = mesh_object(f"Beach_Sand_Terrain_{label}", sub_verts, sub_faces, uvs)
        obj.data.materials.append(mat)
        if label == "Detail":
            sub = obj.modifiers.new("Adaptive displacement", "SUBSURF")
            sub.subdivision_type = "SIMPLE"
            sub.levels = 0
            sub.render_levels = 1
            obj.cycles.use_adaptive_subdivision = True
            obj.cycles.dicing_rate = 1.0
        objects.append(obj)
    return objects, poly


# --------------------------------------------------------------------------- sea
def build_sea(cfg, beach, scene):
    s = cfg["appearance"]["sea"]
    level = beach.sea_level + s["level_offset_from_shore_m"]
    me = bpy.data.meshes.new("Sea_Surface")
    obj = bpy.data.objects.new("Sea_Surface", me)
    scene.collection.objects.link(obj)
    center = beach.p1 + beach.sea_normal * (0.5 * s["spatial_size_m"] * s["repeat"] - 12.0)
    obj.location = (float(center[0]), float(center[1]), level)
    obj.rotation_euler = (0.0, 0.0, math.atan2(beach.along[1], beach.along[0]))
    oc = obj.modifiers.new("Wind sea", "OCEAN")
    oc.geometry_mode = "GENERATE"
    oc.resolution = s["resolution"]
    oc.viewport_resolution = 4
    oc.spatial_size = int(s["spatial_size_m"])
    oc.repeat_x = s["repeat"]
    oc.repeat_y = s["repeat"]
    oc.spectrum = "PIERSON_MOSKOWITZ"
    oc.wave_scale = s["wave_scale"]
    oc.wind_velocity = s["wind_velocity_m_s"]
    oc.choppiness = s["choppiness"]
    oc.wave_alignment = s["wave_alignment"]
    # local +y of the patch is the seaward normal; waves travel onshore (-y)
    oc.wave_direction = math.radians(-90.0 if s["wave_direction_onshore"] else 90.0)
    oc.damping = 0.6
    oc.depth = 30.0
    oc.random_seed = 11
    oc.use_normals = True
    # centre the generated patch on the requested point (the generated grid is not centred
    # on the object origin)
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    me_ev = ev.to_mesh()
    pts = np.array([tuple(obj.matrix_world @ v.co) for v in me_ev.vertices])
    ev.to_mesh_clear()
    actual = 0.5 * (pts.min(axis=0) + pts.max(axis=0))
    obj.location.x += float(center[0] - actual[0])
    obj.location.y += float(center[1] - actual[1])
    # "animate": false freezes the sea (waves, ripples and foam) at its frame-1 state
    animate = s.get("animate", True)
    oc.time = 0.0
    if animate:
        oc.keyframe_insert("time", frame=1)
        oc.time = (scene.frame_end - 1) / scene.render.fps
        oc.keyframe_insert("time", frame=scene.frame_end)
        for fc in obj.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"

    def phase(input_socket, rate):
        if animate:
            drv = input_socket.driver_add("default_value").driver
            drv.type = "SCRIPTED"
            drv.expression = f"frame / 24.0 * {rate}"
        else:
            input_socket.default_value = 1.0 / 24.0 * rate
    mat, nt, out = new_material("Sea water (absorbing, refractive)")
    bsdf = node(nt, "ShaderNodeBsdfPrincipled", 0, 300)
    bsdf.inputs["Base Color"].default_value = (1, 1, 1, 1)
    bsdf.inputs["Transmission Weight"].default_value = 1.0
    bsdf.inputs["IOR"].default_value = 1.333
    bsdf.inputs["Roughness"].default_value = s["roughness"]
    # fine capillary ripples on top of the generated waves (animated 4D noise)
    tc = node(nt, "ShaderNodeTexCoord", -900, 0)
    nz = node(nt, "ShaderNodeTexNoise", -700, 0, noise_dimensions="4D")
    nz.inputs["Scale"].default_value = 1.6
    nz.inputs["Detail"].default_value = 6.0
    link(nt, tc.outputs["Object"], nz.inputs["Vector"])
    phase(nz.inputs["W"], 0.35)
    bump = node(nt, "ShaderNodeBump", -450, 0)
    bump.inputs["Strength"].default_value = 0.08
    bump.inputs["Distance"].default_value = 0.02
    link(nt, nz.outputs["Fac"], bump.inputs["Height"])
    link(nt, bump.outputs[0], bsdf.inputs["Normal"])
    # thin line of foam where the water runs out on the sand: water depth over the
    # (planar) seabed of the beach profile, broken up by animated noise
    geo = node(nt, "ShaderNodeNewGeometry", -1200, -500)
    sep = node(nt, "ShaderNodeSeparateXYZ", -1050, -500)
    link(nt, geo.outputs["Position"], sep.inputs[0])
    dx = math_node(nt, "SUBTRACT", sep.outputs["X"], float(beach.p1[0]), -900, -450)
    dy = math_node(nt, "SUBTRACT", sep.outputs["Y"], float(beach.p1[1]), -900, -550)
    proj = math_node(nt, "ADD", math_node(nt, "MULTIPLY", dx, float(beach.sea_normal[0]), -750, -450),
                     math_node(nt, "MULTIPLY", dy, float(beach.sea_normal[1]), -750, -550), -600, -500)
    # depth = (z - sea) + proj * slope   (proj = -inland distance)
    depth = math_node(nt, "ADD", math_node(nt, "SUBTRACT", sep.outputs["Z"], float(level), -600, -650),
                      math_node(nt, "MULTIPLY", proj, float(cfg["appearance"]["terrain"]["seabed_slope"]), -450, -500),
                      -300, -550)
    fmask = node(nt, "ShaderNodeMapRange", -150, -550)
    fmask.inputs["From Min"].default_value = s["foam_depth_m"]
    fmask.inputs["From Max"].default_value = 0.0
    link(nt, depth, fmask.inputs["Value"])
    fn = node(nt, "ShaderNodeTexNoise", -450, -800, noise_dimensions="4D")
    fn.inputs["Scale"].default_value = 3.5
    fn.inputs["Detail"].default_value = 4.0
    link(nt, tc.outputs["Object"], fn.inputs["Vector"])
    phase(fn.inputs["W"], 0.6)
    fb = node(nt, "ShaderNodeMapRange", -250, -800)
    fb.inputs["From Min"].default_value = 0.45
    fb.inputs["From Max"].default_value = 0.62
    link(nt, fn.outputs["Fac"], fb.inputs["Value"])
    foam_fac = math_node(nt, "MULTIPLY", math_node(nt, "MULTIPLY", fmask.outputs[0], fb.outputs[0], 0, -700),
                         s["foam_strength"], 150, -700, clamp=True)
    foam = node(nt, "ShaderNodeBsdfPrincipled", 150, -950)
    foam.inputs["Base Color"].default_value = (0.86, 0.87, 0.85, 1.0)
    foam.inputs["Roughness"].default_value = 0.6
    wf = node(nt, "ShaderNodeMixShader", 350, 100)
    link(nt, foam_fac, wf.inputs[0])
    link(nt, bsdf.outputs[0], wf.inputs[1])
    link(nt, foam.outputs[0], wf.inputs[2])
    lp = node(nt, "ShaderNodeLightPath", 0, 600)
    tr = node(nt, "ShaderNodeBsdfTransparent", 250, 500)
    ms = node(nt, "ShaderNodeMixShader", 500, 300)
    link(nt, lp.outputs["Is Shadow Ray"], ms.inputs[0])
    link(nt, wf.outputs[0], ms.inputs[1])
    link(nt, tr.outputs[0], ms.inputs[2])
    link(nt, ms.outputs[0], out.inputs["Surface"])
    ab = node(nt, "ShaderNodeVolumeAbsorption", 250, -100)
    ab.inputs["Color"].default_value = tuple(s["absorption_color"]) + (1.0,)
    ab.inputs["Density"].default_value = s["absorption_density"]
    sc = node(nt, "ShaderNodeVolumeScatter", 250, -300)
    sc.inputs["Color"].default_value = tuple(s["scatter_color"]) + (1.0,)
    sc.inputs["Density"].default_value = s["scatter_density"]
    sc.inputs["Anisotropy"].default_value = 0.4
    add = node(nt, "ShaderNodeAddShader", 500, -200)
    link(nt, ab.outputs[0], add.inputs[0])
    link(nt, sc.outputs[0], add.inputs[1])
    link(nt, add.outputs[0], out.inputs["Volume"])
    obj.data.materials.append(mat)
    return obj, level


# --------------------------------------------------------------------------- hammock fabric
def principal_frame(points):
    xy = points[:, :2]
    c = xy.mean(axis=0)
    w, vec = np.linalg.eigh((xy - c).T @ (xy - c))
    axis = vec[:, 1]
    if axis[1] < 0:
        axis = -axis
    perp = np.array([-axis[1], axis[0]])
    return c, axis, perp


def evaluated_world_mesh(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    me = ev.to_mesh()
    mw = obj.matrix_world
    verts = [mw @ v.co for v in me.vertices]
    polys = [tuple(p.vertices) for p in me.polygons]
    ev.to_mesh_clear()
    return verts, polys


def fabric_material(cfg):
    h = cfg["appearance"]["hammock"]
    mat, nt, out = new_material("Hammock striped cotton canvas (ambientCG Fabric071)")
    base = h["fabric"]
    uv = node(nt, "ShaderNodeUVMap", -1200, 0, uv_map="UVMap")
    def tex(name, cs, y):
        n = node(nt, "ShaderNodeTexImage", -900, y, interpolation="Cubic")
        n.image = image(f"{base}/{name}", cs)
        link(nt, uv.outputs[0], n.inputs["Vector"])
        return n
    col = tex("Fabric071_SQ_Color.jpg", "sRGB", 300)
    rgh = tex("Fabric071_SQ_Roughness.jpg", "Non-Color", 0)
    nrm = tex("Fabric071_SQ_NormalDX.jpg", "Non-Color", -300)
    # sun-faded, slightly dusty outdoor canvas
    hsv = node(nt, "ShaderNodeHueSaturation", -600, 300)
    hsv.inputs["Saturation"].default_value = 0.86
    hsv.inputs["Value"].default_value = 0.93
    link(nt, col.outputs["Color"], hsv.inputs["Color"])
    rr = node(nt, "ShaderNodeMapRange", -600, 0)
    rr.inputs["To Min"].default_value = 0.78
    rr.inputs["To Max"].default_value = 0.96
    link(nt, rgh.outputs["Color"], rr.inputs["Value"])
    n_out = normal_dx(nt, nrm.outputs["Color"], -700, -300, strength=0.6, uv_map="UVMap")
    bsdf = node(nt, "ShaderNodeBsdfPrincipled", 0, 200)
    link(nt, hsv.outputs[0], bsdf.inputs["Base Color"])
    link(nt, rr.outputs[0], bsdf.inputs["Roughness"])
    link(nt, n_out, bsdf.inputs["Normal"])
    bsdf.inputs["Sheen Weight"].default_value = 0.35
    bsdf.inputs["Sheen Roughness"].default_value = 0.45
    bsdf.inputs["Specular IOR Level"].default_value = 0.3
    trl = node(nt, "ShaderNodeBsdfTranslucent", 0, -250)
    link(nt, hsv.outputs[0], trl.inputs["Color"])
    link(nt, n_out, trl.inputs["Normal"])
    ms = node(nt, "ShaderNodeMixShader", 400, 0)
    ms.inputs[0].default_value = 0.14
    link(nt, bsdf.outputs[0], ms.inputs[1])
    link(nt, trl.outputs[0], ms.inputs[2])
    link(nt, ms.outputs[0], out.inputs["Surface"])
    return mat


def build_hammock(cfg, scene):
    h = cfg["appearance"]["hammock"]
    shell = bpy.data.objects[HAMMOCK]
    for m in list(shell.modifiers):
        shell.modifiers.remove(m)
    sub = shell.modifiers.new("Shell smoothing", "SUBSURF")
    sub.levels = h["shell_subdivision_levels"]
    sub.render_levels = h["shell_subdivision_levels"]
    for attr in ("visible_camera", "visible_diffuse", "visible_glossy", "visible_transmission",
                 "visible_volume_scatter", "visible_shadow"):
        setattr(shell, attr, False)
    scene.frame_set(1)
    verts, polys = evaluated_world_mesh(shell)
    V = np.array([tuple(v) for v in verts])
    c, axis, perp = principal_frame(V)
    s_all = (V[:, :2] - c) @ axis
    q_all = (V[:, :2] - c) @ perp
    bvh = BVHTree.FromPolygons(verts, polys)
    down = Vector((0.0, 0.0, -1.0))

    def hits_at(x, y):
        out = []
        origin = Vector((x, y, 10.0))
        for _ in range(4):
            loc, nrm, idx, dist = bvh.ray_cast(origin, down, 20.0)
            if loc is None:
                break
            out.append(loc.z)
            origin = Vector((x, y, loc.z - 1.0e-4))
        return out

    def point(s, q):
        x, y = c + s * axis + q * perp
        return float(x), float(y)

    def last_hit(fn, lo, hi):
        for _ in range(24):
            mid = 0.5 * (lo + hi)
            if fn(mid):
                lo = mid
            else:
                hi = mid
        return lo

    # extent of the shell along its axis and its rim half-width per station, from ray hits
    s_end = min(last_hit(lambda t: bool(hits_at(*point(-t, 0.0))), 0.5, 1.4),
                last_hit(lambda t: bool(hits_at(*point(t, 0.0))), 0.5, 1.4)) - 0.01
    nb, nc, ng = h["bed_rows"], h["columns"], h["gather_rows"]
    s_rows = np.linspace(-s_end, s_end, nb)
    v_cols = np.linspace(-1.0, 1.0, nc)
    rims = np.array([[last_hit(lambda t, s=s, g=g: bool(hits_at(*point(s, g * t))), 0.0, 0.8)
                      for g in (1.0, -1.0)] for s in s_rows])
    kern = np.array([1, 2, 3, 2, 1], float) / 9.0
    smooth = np.stack([np.convolve(np.pad(rims[:, k], 2, mode="edge"), kern, mode="valid") for k in range(2)], axis=1)
    rims = np.minimum(rims, smooth)   # smoothing must never push the edge past the real rim
    bed = np.zeros((nb, nc, 3))
    for i, s in enumerate(s_rows):
        rp, rn = rims[i] * h["rim_fraction"]
        for j, v in enumerate(v_cols):
            x, y = point(s, v * (rp if v > 0 else rn))
            zs = hits_at(x, y)
            if len(zs) >= 2 and zs[0] - zs[1] < 0.05:
                z = 0.5 * (zs[0] + zs[1])
            elif zs:
                z = zs[0]
            else:
                z = np.nan
            bed[i, j] = (x, y, z)
    # fill the rare missed samples by linear extrapolation along the row
    for i in range(nb):
        z = bed[i, :, 2]
        bad = ~np.isfinite(z)
        if bad.all():
            raise RuntimeError(f"No MPM surface under fabric row {i}")
        if bad.any():
            good = np.nonzero(~bad)[0]
            for j in np.nonzero(bad)[0]:
                k = good[np.argsort(np.abs(good - j))[:2]]
                if len(k) < 2:
                    z[j] = z[k[0]]
                else:
                    z[j] = z[k[0]] + (z[k[1]] - z[k[0]]) * (j - k[0]) / (k[1] - k[0])
            bed[i, :, 2] = z
    missed = int(sum((~np.isfinite(bed[:, :, 2])).sum() for _ in [0]))
    # light smoothing of the sampled mid-surface (removes ray-sampling noise only)
    for _ in range(3):
        z = bed[:, :, 2].copy()
        z[1:-1, :] += 0.2 * (bed[2:, :, 2] + bed[:-2, :, 2] - 2 * bed[1:-1, :, 2])
        z[:, 1:-1] += 0.2 * (bed[:, 2:, 2] + bed[:, :-2, 2] - 2 * bed[:, 1:-1, 2])
        bed[:, :, 2] = z
    W = h["fabric_width_m"]
    tile = h["texture_tile_m"]
    rows = [bed[i] for i in range(nb)]
    u_rows = list(s_rows)
    ends = {}
    gathers = {}
    for sign, label in ((-1, "A"), (1, "B")):
        end_row = bed[0] if sign < 0 else bed[-1]
        prev_row = bed[6] if sign < 0 else bed[-7]
        e0 = end_row.mean(axis=0)
        T = e0 - prev_row.mean(axis=0)
        T /= np.linalg.norm(T)
        L = np.cross(T, [0, 0, 1.0])
        L /= np.linalg.norm(L)
        U = np.cross(L, T)
        rel = end_row - e0
        half = np.abs(rel @ L).max()
        shrink_end = h["bundle_radius_m"] / half
        g_rows = []
        for k in range(1, ng + 1):
            g = k / ng
            sm = float(smoothstep(np.array(g ** 0.8)))
            shrink = 1.0 - (1.0 - shrink_end) * sm
            pleat = h["pleat_amplitude_m"] * math.sin(math.pi * min(1.0, g * 1.15)) * (0.4 + 0.6 * g)
            row = []
            for j, v in enumerate(v_cols):
                r = rel[j]
                p = (e0 + T * (g * h["gather_length_m"])
                     + L * (r @ L) * shrink
                     + U * ((r @ U) * shrink + pleat * math.sin(v * math.pi * h["pleats"]))
                     + T * (r @ T) * shrink)
                row.append(p)
            g_rows.append(np.array(row))
        gathers[label] = g_rows
        ends[label] = {"e0": e0, "T": T, "L": L, "U": U,
                       "bundle": e0 + T * h["gather_length_m"], "sign": sign}
    all_rows = gathers["A"][::-1] + rows + gathers["B"]
    gl = h["gather_length_m"]
    u_all = ([-s_end - gl * (k / ng) for k in range(ng, 0, -1)] + u_rows
             + [s_end + gl * (k / ng) for k in range(1, ng + 1)])
    verts, uvs, faces = [], [], []
    nr = len(all_rows)
    for i, row in enumerate(all_rows):
        for j, p in enumerate(row):
            verts.append(p)
            uvs.append((u_all[i] / tile, v_cols[j] * 0.5 * W / tile))
    for i in range(nr - 1):
        for j in range(nc - 1):
            a = i * nc + j
            faces.append((a, a + 1, a + nc + 1, a + nc))
    fab = mesh_object("Hammock_Fabric_Visible", verts, faces, uvs)
    fab.data.materials.append(fabric_material(cfg))
    sd = fab.modifiers.new("Follow MPM surface", "SURFACE_DEFORM")
    sd.target = shell
    sd.falloff = 4.0
    bpy.context.view_layer.objects.active = fab
    fab.select_set(True)
    with bpy.context.temp_override(object=fab, active_object=fab, selected_objects=[fab],
                                   selected_editable_objects=[fab]):
        bpy.ops.object.surfacedeform_bind(modifier=sd.name)
    fab.select_set(False)
    if not sd.is_bound:
        raise RuntimeError("Surface Deform binding to the MPM shell failed")
    # The MPM hammock is a 0.15 m thick block whose mid-surface is the cached shell. The ball
    # is stopped by the block's upper boundary: half the thickness plus the grid contact
    # margin (contact radius R + 0.6 dx and the B-spline support of the top particle layer).
    # The visible canvas is drawn on that contact surface by offsetting the bound sheet along
    # its normal; towards the pinned, gathered ends the offset fades to zero so the sheet
    # meets the end bindings, which are static.
    cs = h["contact_surface"]
    # The grid contact margin depends on how much the block's top layer is compressed under the
    # ball, i.e. on its stiffness; it is read from each stiffness's resting equilibrium.
    young = scene.get("mpm_young_modulus_pa")
    margin = cs.get("contact_margin_by_young_modulus_pa", {}).get(
        str(int(round(young))) if young is not None else "", cs["contact_margin_m"])
    offset = cs["half_thickness_m"] + margin
    # parabolic fade 1 - (s/s_end)^2 keeps a single convex sag along the hammock
    vg = fab.vertex_groups.new(name="MPM contact surface offset")
    for i, u in enumerate(u_all):
        w = max(0.0, 1.0 - (abs(u) / s_end) ** 2)
        if w > 0:
            vg.add(list(range(i * nc, (i + 1) * nc)), w, "REPLACE")
    mid_row = ng + nb // 2
    poly_center = fab.data.polygons[mid_row * (nc - 1) + (nc - 1) // 2]
    sign = 1.0 if poly_center.normal.z > 0 else -1.0
    dp = fab.modifiers.new("MPM block contact surface", "DISPLACE")
    dp.direction = "NORMAL"
    dp.space = "LOCAL"
    dp.mid_level = 0.0
    dp.strength = sign * offset
    dp.vertex_group = vg.name
    # Non-penetration: where the offset surface would lie inside the ball (impact frames) the
    # canvas is laid onto the ball surface, with a smooth band of width b at the contact edge.
    gn = fab.modifiers.new("Canvas on ball contact", "NODES")
    gn.node_group = contact_node_group(bpy.data.objects[BALL],
                                       0.5 * max(bpy.data.objects[BALL].dimensions) + 0.5 * h["thickness_m"],
                                       cs["contact_band_m"])
    so = fab.modifiers.new("Canvas thickness", "SOLIDIFY")
    so.thickness = h["thickness_m"]
    so.offset = 0.0
    so.use_even_offset = True
    so.use_rim = True
    ss = fab.modifiers.new("Smooth", "SUBSURF")
    ss.levels = 1
    ss.render_levels = 1
    return fab, ends, {"center": c, "axis": axis, "perp": perp, "s_end": s_end,
                       "contact_offset_m": offset, "contact_margin_m": margin, "offset_fade": "1 - (s / s_end)^2",
                       "contact_band_m": cs["contact_band_m"]}


def contact_node_group(ball, r0, band):
    """Geometry nodes: p -> c + (p - c) * f(r) / r with f(r) = max(r, r0 + b t^2), t = clamp((r - r0 + b) / 2b)."""
    ng = bpy.data.node_groups.new("Canvas on ball contact", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n = ng.nodes
    gi = n.new("NodeGroupInput")
    go = n.new("NodeGroupOutput")
    oi = n.new("GeometryNodeObjectInfo")
    oi.transform_space = "RELATIVE"
    oi.inputs["Object"].default_value = ball
    pos = n.new("GeometryNodeInputPosition")
    def vmath(op, a, b=None):
        m = n.new("ShaderNodeVectorMath")
        m.operation = op
        ng.links.new(a, m.inputs[0])
        if b is not None:
            ng.links.new(b, m.inputs[1])
        return m
    def fmath(op, a, b, clamp=False):
        m = n.new("ShaderNodeMath")
        m.operation = op
        m.use_clamp = clamp
        for i, v in enumerate((a, b)):
            if isinstance(v, bpy.types.NodeSocket):
                ng.links.new(v, m.inputs[i])
            else:
                m.inputs[i].default_value = v
        return m.outputs[0]
    d = vmath("SUBTRACT", pos.outputs["Position"], oi.outputs["Location"])
    r = vmath("LENGTH", d.outputs[0]).outputs["Value"]
    unit = vmath("NORMALIZE", d.outputs[0]).outputs[0]
    t = fmath("DIVIDE", fmath("SUBTRACT", r, r0 - band), 2.0 * band, clamp=True)
    f = fmath("MAXIMUM", r, fmath("ADD", fmath("MULTIPLY", fmath("MULTIPLY", t, t), band), r0))
    delta = fmath("SUBTRACT", f, r)
    sc = n.new("ShaderNodeVectorMath")
    sc.operation = "SCALE"
    ng.links.new(unit, sc.inputs[0])
    ng.links.new(delta, sc.inputs["Scale"])
    sp = n.new("GeometryNodeSetPosition")
    ng.links.new(gi.outputs[0], sp.inputs["Geometry"])
    ng.links.new(sc.outputs[0], sp.inputs["Offset"])
    ng.links.new(sp.outputs[0], go.inputs[0])
    return ng


def contact_gaps(scene, fabric):
    """Distance from the ball surface to the visible canvas mid-plane in every frame."""
    ball = bpy.data.objects[BALL]
    radius = 0.5 * max(ball.dimensions)
    keep = {m.name: m.show_viewport for m in fabric.modifiers}
    for m in fabric.modifiers:
        m.show_viewport = m.type in ("SURFACE_DEFORM", "DISPLACE", "NODES")
    gaps = []
    for f in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
        ev = fabric.evaluated_get(deps)
        me = ev.to_mesh()
        bvh = BVHTree.FromPolygons([fabric.matrix_world @ v.co for v in me.vertices],
                                   [tuple(p.vertices) for p in me.polygons])
        ev.to_mesh_clear()
        loc, nrm, idx, dist = bvh.find_nearest(ball.matrix_world.translation)
        gaps.append(dist - radius)
    for m in fabric.modifiers:
        m.show_viewport = keep[m.name]
    scene.frame_set(scene.frame_start)
    return radius, gaps


# --------------------------------------------------------------------------- posts and ropes
def wood_material(cfg):
    p = cfg["appearance"]["posts"]
    mat, nt, out = new_material("Weathered timber post (ambientCG Wood062)")
    base = p["texture"]
    uv = node(nt, "ShaderNodeUVMap", -1200, 0, uv_map="UVMap")
    def tex(name, cs, y):
        n = node(nt, "ShaderNodeTexImage", -900, y, interpolation="Cubic")
        n.image = image(f"{base}/{name}", cs)
        link(nt, uv.outputs[0], n.inputs["Vector"])
        return n
    col = tex("Wood062_SQ_Color.jpg", "sRGB", 300)
    rgh = tex("Wood062_SQ_Roughness.jpg", "Non-Color", 0)
    nrm = tex("Wood062_SQ_NormalDX.jpg", "Non-Color", -300)
    # sun-bleached grey towards the top, darker and sand-dusted at the foot
    geo = node(nt, "ShaderNodeNewGeometry", -1200, 600)
    sep = node(nt, "ShaderNodeSeparateXYZ", -1050, 600)
    link(nt, geo.outputs["Position"], sep.inputs[0])
    foot = node(nt, "ShaderNodeMapRange", -900, 600)
    foot.inputs["From Min"].default_value = p["_sand_z"] + 0.25
    foot.inputs["From Max"].default_value = p["_sand_z"] + 0.0
    link(nt, sep.outputs["Z"], foot.inputs["Value"])
    hsv = node(nt, "ShaderNodeHueSaturation", -600, 300)
    hsv.inputs["Saturation"].default_value = 0.72
    hsv.inputs["Value"].default_value = 1.12
    link(nt, col.outputs["Color"], hsv.inputs["Color"])
    sandy = mix(nt, "RGBA", foot.outputs[0], hsv.outputs[0], (0.43, 0.38, 0.31, 1.0), -350, 400)
    bsdf = node(nt, "ShaderNodeBsdfPrincipled", 0, 200)
    link(nt, sandy, bsdf.inputs["Base Color"])
    rr = node(nt, "ShaderNodeMapRange", -600, 0)
    rr.inputs["To Min"].default_value = 0.62
    rr.inputs["To Max"].default_value = 0.92
    link(nt, rgh.outputs["Color"], rr.inputs["Value"])
    link(nt, rr.outputs[0], bsdf.inputs["Roughness"])
    link(nt, normal_dx(nt, nrm.outputs["Color"], -700, -300, strength=1.0, uv_map="UVMap"), bsdf.inputs["Normal"])
    link(nt, bsdf.outputs[0], out.inputs["Surface"])
    return mat


def rope_material(cfg):
    r = cfg["appearance"]["rope"]
    mat, nt, out = new_material("Twisted cotton rope (ambientCG Rope001)")
    base = r["texture"]
    uv = node(nt, "ShaderNodeUVMap", -1200, 0, uv_map="UVMap")
    mp = node(nt, "ShaderNodeMapping", -1050, 0)
    mp.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
    link(nt, uv.outputs[0], mp.inputs["Vector"])
    def tex(name, cs, y):
        n = node(nt, "ShaderNodeTexImage", -900, y, interpolation="Cubic")
        n.image = image(f"{base}/{name}", cs)
        link(nt, mp.outputs[0], n.inputs["Vector"])
        return n
    col = tex("Rope001_SQ_Color.jpg", "sRGB", 300)
    rgh = tex("Rope001_SQ_Roughness.jpg", "Non-Color", 0)
    nrm = tex("Rope001_SQ_NormalDX.jpg", "Non-Color", -300)
    hsv = node(nt, "ShaderNodeHueSaturation", -600, 300)
    hsv.inputs["Hue"].default_value = 0.5 + r["hue_shift"]
    hsv.inputs["Saturation"].default_value = r["saturation"]
    hsv.inputs["Value"].default_value = r["value"]
    link(nt, col.outputs["Color"], hsv.inputs["Color"])
    warm = mix(nt, "RGBA", 1.0, hsv.outputs[0], (1.0, 0.93, 0.80, 1.0), -400, 300, blend="MULTIPLY")
    bsdf = node(nt, "ShaderNodeBsdfPrincipled", 0, 200)
    link(nt, warm, bsdf.inputs["Base Color"])
    rr = node(nt, "ShaderNodeMapRange", -600, 0)
    rr.inputs["To Min"].default_value = 0.75
    rr.inputs["To Max"].default_value = 0.95
    link(nt, rgh.outputs["Color"], rr.inputs["Value"])
    link(nt, rr.outputs[0], bsdf.inputs["Roughness"])
    bsdf.inputs["Sheen Weight"].default_value = 0.3
    link(nt, normal_dx(nt, nrm.outputs["Color"], -700, -300, strength=1.0, uv_map="UVMap"), bsdf.inputs["Normal"])
    link(nt, bsdf.outputs[0], out.inputs["Surface"])
    return mat


def build_post(name, base_xy, sand_z, cfg, mat, rng):
    p = cfg["appearance"]["posts"]
    z0 = sand_z - p["embed_depth_m"]
    z1 = sand_z + p["height_above_sand_m"]
    sides, rings = 40, 48
    tilt = Vector((rng.normal(0, 0.006), rng.normal(0, 0.006), 1.0)).normalized()
    verts, uvs, faces = [], [], []
    tile = p["texture_tile_m"]
    phase = rng.uniform(0, 2 * math.pi, size=5)
    for i in range(rings + 1):
        f = i / rings
        z = z0 + (z1 - z0) * f
        r = p["radius_bottom_m"] + (p["radius_top_m"] - p["radius_bottom_m"]) * f
        top_round = 1.0
        if z1 - z < 0.02:
            top_round = math.sqrt(max(0.0, 1.0 - ((0.02 - (z1 - z)) / 0.02) ** 2)) * 0.25 + 0.75
        for k in range(sides + 1):
            a = 2 * math.pi * k / sides
            irr = 1.0 + 0.025 * math.sin(3 * a + phase[0] + 4 * f) + 0.015 * math.sin(7 * a + phase[1])
            rr = r * irr * top_round
            axis_pt = Vector((base_xy[0], base_xy[1], 0)) + tilt * ((z - z0) / tilt.z)
            verts.append((axis_pt.x + rr * math.cos(a), axis_pt.y + rr * math.sin(a), z0 + (z - z0)))
            uvs.append(((z - z0) / tile, (k / sides) * 2 * math.pi * r / tile))
    ring = sides + 1
    for i in range(rings):
        for k in range(sides):
            a0 = i * ring + k
            faces.append((a0, a0 + 1, a0 + ring + 1, a0 + ring))
    top = len(verts)
    tc = Vector((base_xy[0], base_xy[1], 0)) + tilt * ((z1 - z0) / tilt.z)
    verts.append((tc.x, tc.y, z1 + 0.004))
    uvs.append((0.5, 0.5))
    for k in range(sides):
        faces.append((rings * ring + k, rings * ring + k + 1, top))
    obj = mesh_object(name, verts, faces, uvs)
    obj.data.materials.append(mat)
    return obj, tilt, z0


def helix(center, radius, z_start, angle0, turns, pitch, direction, n_per_turn=40):
    pts = []
    n = int(turns * n_per_turn)
    for i in range(n + 1):
        a = angle0 + direction * 2 * math.pi * turns * i / n
        pts.append(Vector((center[0] + radius * math.cos(a), center[1] + radius * math.sin(a),
                           z_start - pitch * turns * i / n)))
    return pts


def build_supports(cfg, ends, beach):
    r = cfg["appearance"]["rope"]
    p = cfg["appearance"]["posts"]
    rng = np.random.default_rng(cfg["appearance"]["seed"] + 5)
    rope_mat = rope_material(cfg)
    rr = r["radius_m"]
    records = {}
    for label, e in sorted(ends.items()):
        T = Vector(e["T"])
        B = Vector(e["bundle"])
        wl = r["whipping_length_m"]
        # whipping: tight turns of rope binding the gathered end
        axis_start = B - T * (0.65 * wl)
        Lv, Uv = Vector(e["L"]), Vector(e["U"])
        whip = []
        turns = wl / (2.1 * rr)
        n = int(turns * 36)
        rad = cfg["appearance"]["hammock"]["bundle_radius_m"] * 1.05 + rr
        for i in range(n + 1):
            f = i / n
            a = 2 * math.pi * turns * f
            whip.append(axis_start + T * (wl * f) + (Lv * math.cos(a) + Uv * math.sin(a)) * rad)
        tube(f"Hammock_Whipping_{label}", whip, rr, sides=10, material=rope_mat)
        R0 = B + T * (0.35 * wl)
        Th = Vector((T.x, T.y, 0)).normalized()
        slope = T.z / math.hypot(T.x, T.y)
        D = r["post_distance_from_bundle_m"][label]
        rad_post_at = p["radius_bottom_m"] + (p["radius_top_m"] - p["radius_bottom_m"]) * 0.75
        post_xy = Vector((R0.x, R0.y, 0)) + Th * (D + rad_post_at)
        sand_z = float(beach.height(np.array(post_xy.x), np.array(post_xy.y)))
        p["_sand_z"] = sand_z
        wood = wood_material(cfg)
        wood.name = f"{wood.name} {label}"
        build_post(f"Hammock_Post_{label}", (post_xy.x, post_xy.y), sand_z, cfg, wood, rng)
        rc = rad_post_at + rr * 1.02
        rel = Vector((R0.x - post_xy.x, R0.y - post_xy.y, 0))
        beta = math.atan2(rel.y, rel.x)
        alpha = math.acos(min(1.0, rc / rel.length))
        tang_a = beta + alpha
        tang_pt = Vector((post_xy.x + rc * math.cos(tang_a), post_xy.y + rc * math.sin(tang_a), 0))
        incoming = (tang_pt - Vector((R0.x, R0.y, 0))).normalized()
        sigma = 1.0 if Vector((-math.sin(tang_a), math.cos(tang_a), 0)).dot(incoming) > 0 else -1.0
        z_att = R0.z + slope * (tang_pt - Vector((R0.x, R0.y, 0))).length
        tang_pt.z = z_att
        # main rope, taut with a slight sag
        main = []
        for i in range(41):
            f = i / 40
            q = R0.lerp(tang_pt, f)
            q.z -= 0.008 * 4 * f * (1 - f)
            main.append(q)
        coils = helix(post_xy, rc, z_att, tang_a, r["wraps"], 2.15 * rr, sigma)
        # tail: tucked under the last turn and hanging free
        last = coils[-1]
        a_end = tang_a + sigma * 2 * math.pi * r["wraps"]
        tdir = Vector((-math.sin(a_end), math.cos(a_end), 0)) * sigma
        outward = Vector((math.cos(a_end), math.sin(a_end), 0))
        tail = []
        for i in range(1, 25):
            f = i / 24
            tail.append(last + tdir * (0.035 * min(1.0, f * 3)) + outward * (0.014 * f)
                        + Vector((0, 0, -r["tail_length_m"] * f ** 1.3)))
        tube(f"Hammock_Rope_{label}", main + coils[1:] + tail, rr, sides=10, material=rope_mat)
        records[label] = {"post_xy": [post_xy.x, post_xy.y], "sand_z": sand_z, "attach_z": z_att,
                          "rope_start": list(R0), "post_top_z": sand_z + p["height_above_sand_m"]}
    return records


# --------------------------------------------------------------------------- ball
def ball_materials(cfg):
    b = cfg["appearance"]["ball"]
    ball = bpy.data.objects[BALL]
    for slot in ball.material_slots:
        old = slot.material
        color = (0.8, 0.8, 0.8, 1.0)
        if old and old.use_nodes:
            for n in old.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED":
                    color = tuple(n.inputs["Base Color"].default_value)
        mat, nt, out = new_material(f"Beach ball PVC {old.name if old else ''}")
        bsdf = node(nt, "ShaderNodeBsdfPrincipled", 0, 200)
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = b["roughness"]
        bsdf.inputs["IOR"].default_value = 1.54
        bsdf.inputs["Coat Weight"].default_value = b["coat_weight"]
        bsdf.inputs["Coat Roughness"].default_value = b["coat_roughness"]
        # faint large-scale unevenness of an inflated PVC skin
        tc = node(nt, "ShaderNodeTexCoord", -800, -200)
        nz = node(nt, "ShaderNodeTexNoise", -600, -200)
        nz.inputs["Scale"].default_value = 6.0
        link(nt, tc.outputs["Object"], nz.inputs["Vector"])
        bump = node(nt, "ShaderNodeBump", -350, -200)
        bump.inputs["Strength"].default_value = 0.05
        link(nt, nz.outputs["Fac"], bump.inputs["Height"])
        link(nt, bump.outputs[0], bsdf.inputs["Normal"])
        trl = node(nt, "ShaderNodeBsdfTranslucent", 0, -150)
        trl.inputs["Color"].default_value = color
        ms = node(nt, "ShaderNodeMixShader", 400, 0)
        ms.inputs[0].default_value = b["translucency"]
        link(nt, bsdf.outputs[0], ms.inputs[1])
        link(nt, trl.outputs[0], ms.inputs[2])
        link(nt, ms.outputs[0], out.inputs["Surface"])
        slot.material = mat
    for poly in ball.data.polygons:
        poly.use_smooth = True


# --------------------------------------------------------------------------- render settings
def configure_render(cfg, scene, device="CPU"):
    r = cfg["render"]
    scene.render.engine = "CYCLES"
    scene.cycles.feature_set = "EXPERIMENTAL"
    scene.render.resolution_x, scene.render.resolution_y = r["resolution"]
    scene.render.resolution_percentage = 100
    scene.render.fps = r["fps"]
    scene.cycles.samples = r["samples"]
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = r["adaptive_threshold"]
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = r["denoiser"]
    scene.cycles.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    scene.cycles.max_bounces = r["max_bounces"]
    scene.cycles.diffuse_bounces = r["diffuse_bounces"]
    scene.cycles.glossy_bounces = r["glossy_bounces"]
    scene.cycles.transmission_bounces = r["transmission_bounces"]
    scene.cycles.volume_bounces = r["volume_bounces"]
    scene.cycles.transparent_max_bounces = 16
    scene.cycles.sample_clamp_indirect = r["clamp_indirect"]
    scene.cycles.blur_glossy = 0.5
    # a fixed sampling seed (animated_seed false) keeps static scenery from shimmering
    scene.cycles.use_animated_seed = r.get("animated_seed", True)
    scene.cycles.seed = cfg["appearance"]["seed"] % 100000
    scene.cycles.dicing_rate = cfg["appearance"]["terrain"]["dicing_rate_px"]
    scene.cycles.offscreen_dicing_scale = 4.0
    scene.cycles.max_subdivisions = 8
    scene.render.use_motion_blur = r["motion_blur"]
    scene.render.motion_blur_shutter = r["motion_blur_shutter"]
    scene.render.use_persistent_data = r["persistent_data"]
    scene.view_settings.view_transform = r["view_transform"]
    scene.view_settings.look = r["look"]
    scene.view_settings.exposure = r["exposure"]
    scene.view_settings.gamma = 1.0
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    if device != "CPU":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        chosen = None
        for kind in ([device] if device in ("OPTIX", "CUDA") else ["OPTIX", "CUDA"]):
            try:
                prefs.compute_device_type = kind
                prefs.get_devices()
                gpus = [d for d in prefs.devices if d.type == kind]
                if gpus:
                    chosen = kind
                    for d in prefs.devices:
                        d.use = d.type == kind
                    break
            except TypeError:
                continue
        if chosen is None:
            raise RuntimeError("No GPU render device available")
        scene.cycles.device = "GPU"
        scene["pcve_render_device"] = chosen
    else:
        scene.cycles.device = "CPU"
        scene["pcve_render_device"] = "CPU"


def override_camera(cfg, scene):
    """Move the scene camera to `camera.override` (location, Euler XYZ rotation, lens), if given."""
    c = cfg["appearance"]["camera"]
    o = c.get("override")
    cam = scene.camera
    if cam.name != c["name"]:
        raise RuntimeError(f"Unexpected camera {cam.name}")
    if not o:
        return None
    if cam.animation_data is not None or cam.parent is not None or cam.constraints:
        raise RuntimeError("camera override expects an unanimated, unparented camera")
    cam.location = o["location_m"]
    cam.rotation_mode = "XYZ"
    cam.rotation_euler = [math.radians(a) for a in o["rotation_deg"]]
    cam.data.lens = o["lens_mm"]
    bpy.context.view_layer.update()
    return o


def configure_camera(cfg, scene):
    c = cfg["appearance"]["camera"]
    cam = scene.camera
    if cam.name != c["name"]:
        raise RuntimeError(f"Unexpected camera {cam.name}")
    cam.data.dof.use_dof = c["dof_enabled"]
    fwd = cam.matrix_world.to_3x3() @ Vector((0, 0, -1))
    cam.data.dof.focus_distance = (Vector(c["focus_point_m"]) - cam.matrix_world.translation).dot(fwd)
    cam.data.dof.aperture_fstop = c["fstop"]
    return {"location": list(cam.matrix_world.translation), "rotation_euler_deg": [math.degrees(a) for a in cam.matrix_world.to_euler()],
            "lens_mm": cam.data.lens, "sensor_width_mm": cam.data.sensor_width, "focus_distance_m": cam.data.dof.focus_distance}


# --------------------------------------------------------------------------- props
def _parents(obj):
    while obj.parent is not None:
        obj = obj.parent
        yield obj


def _append_prop(blend, root, exclude, scene):
    """Append `root` and its descendants from `blend`; empty helper meshes and `exclude` are dropped."""
    with bpy.data.libraries.load(str(blend)) as (src, dst):
        names = list(src.objects)
        dst.objects = list(src.objects)
    objs = {n: o for n, o in zip(names, dst.objects) if o is not None}
    r = objs[root]
    keep = [o for n, o in objs.items()
            if (o is r or any(p is r for p in _parents(o))) and n not in exclude
            and not (o.type == "MESH" and len(o.data.polygons) == 0)]
    for o in keep:
        scene.collection.objects.link(o)
    for o in objs.values():
        if o not in keep:
            bpy.data.objects.remove(o, do_unlink=True)
    _freeze_animation(keep, scene)
    return r, [o for o in keep if o.type == "MESH"]


def _animated(idb):
    ad = getattr(idb, "animation_data", None)
    return ad is not None and (ad.action is not None or len(ad.drivers) or len(ad.nla_tracks))


def _freeze_animation(objs, scene):
    """Props are set dressing and must not move: hold any animation the asset file carries (for
    example a rig's folding cycle) at the clip's first frame, then remove it."""
    owners = []
    for o in objs:
        owners += [o, o.data] if o.data is not None else [o]
        if o.type == "MESH" and o.data.shape_keys is not None:
            owners.append(o.data.shape_keys)
    animated = [idb for idb in owners if _animated(idb)]
    if not animated:
        return
    current = scene.frame_current
    scene.frame_set(scene.frame_start)       # flushes the animated values of frame 1 to the data
    for idb in animated:
        idb.animation_data_clear()
    scene.frame_set(current)
    left = [idb.name for idb in owners if _animated(idb)]
    if left:
        raise RuntimeError(f"props still animated: {left}")


def _world_vertices(meshes):
    deps = bpy.context.evaluated_depsgraph_get()
    pts = []
    for m in meshes:
        ev = m.evaluated_get(deps)
        me = ev.to_mesh()
        pts += [ev.matrix_world @ v.co for v in me.vertices]
        ev.to_mesh_clear()
    return pts


def _inside_any(poly, pts):
    """True if any of the xy points lies inside the polygon (even-odd rule)."""
    x, y = pts[:, 0], pts[:, 1]
    res = np.zeros(len(pts), dtype=bool)
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        res ^= ((y1 > y) != (y2 > y)) & (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1)
    return bool(res.any())


def _tint_albedo(meshes, hsv):
    """Insert a Hue/Saturation/Value node after the base-colour texture of the named objects' materials."""
    done = set()
    for m in meshes:
        if m.name.split(".")[0] not in hsv["objects"]:
            continue
        for slot in m.material_slots:
            mat = slot.material
            if mat is None or mat in done or not mat.use_nodes:
                continue
            done.add(mat)
            nt = mat.node_tree
            for b in [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"]:
                links = list(b.inputs["Base Color"].links)
                if not links:
                    raise RuntimeError(f"{mat.name}: base colour is not textured")
                src = links[0].from_socket
                h = nt.nodes.new("ShaderNodeHueSaturation")
                h.inputs["Hue"].default_value = hsv.get("hue", 0.5)
                h.inputs["Saturation"].default_value = hsv.get("saturation", 1.0)
                h.inputs["Value"].default_value = hsv.get("value", 1.0)
                nt.links.new(src, h.inputs["Color"])
                nt.links.new(h.outputs["Color"], b.inputs["Base Color"])
    if not done:
        raise RuntimeError(f"albedo_hsv matched no material on {hsv['objects']}")


def place_props(cfg, scene, sun_dir, terrain):
    """Static set dressing from asset files, placed on the sand from image positions.

    Each prop stands where the camera ray through `pixel` meets the sand, or (for an object out of
    view) where the shadow of its crown lands on `shadow_target_pixel`. A prop must lie inside the
    frame unless `allow_out_of_frame`, and must not overlap the keep-out boxes (the ball's fall
    column and the hammock with its ropes)."""
    spec = cfg["appearance"].get("props")
    if not spec:
        return []
    from bpy_extras.object_utils import world_to_camera_view
    cam = scene.camera
    W, H = scene.render.resolution_x, scene.render.resolution_y
    verts, polys = [], []
    for o in terrain:
        me = o.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
        base = len(verts)
        verts += [o.matrix_world @ v.co for v in me.vertices]
        polys += [[base + i for i in p.vertices] for p in me.polygons]
    bvh = BVHTree.FromPolygons(verts, polys)
    tr, br, bl, tl = cam.data.view_frame(scene=scene)

    def ground_under_pixel(px, py):
        p = tl + (tr - tl) * (px / W) + (bl - tl) * (py / H)
        hit, *_ = bvh.ray_cast(cam.matrix_world.translation, (cam.matrix_world.to_3x3() @ p).normalized())
        if hit is None:
            raise RuntimeError(f"pixel {(px, py)} does not see the sand")
        return hit

    def ground_under_xy(x, y):
        hit, *_ = bvh.ray_cast(Vector((x, y, 100.0)), Vector((0, 0, -1)))
        if hit is None:
            raise RuntimeError(f"no sand under {(x, y)}")
        return hit

    sun = Vector(sun_dir).normalized()
    keep_out = spec.get("keep_out_px", [])
    keep_out_xy = [np.array(poly, dtype=float) for poly in spec.get("keep_out_xy", [])]
    report = []
    for p in spec["items"]:
        obj, meshes = _append_prop(asset(p["file"]), p["object"], set(p.get("exclude", [])), scene)
        obj.parent = None
        obj.rotation_mode = "XYZ"
        obj.rotation_euler = [math.radians(a) for a in p.get("rotation_deg", (0, 0, 0))]
        obj.scale = (p.get("scale", 1.0),) * 3
        obj.location = (0.0, 0.0, 0.0)
        bpy.context.view_layer.update()
        if p.get("lean_deg"):
            # tilt the whole prop by lean_deg towards the compass heading lean_azimuth_deg
            az = math.radians(p["lean_azimuth_deg"])
            axis = Vector((0, 0, 1)).cross(Vector((math.cos(az), math.sin(az), 0))).normalized()
            obj.matrix_world = Matrix.Rotation(math.radians(p["lean_deg"]), 4, axis) @ obj.matrix_world
            bpy.context.view_layer.update()
        if p.get("albedo_hsv"):
            _tint_albedo(meshes, p["albedo_hsv"])
        vs = _world_vertices(meshes)
        zmin = min(v.z for v in vs)
        if p.get("anchor", "bbox") == "foot":      # centre of the lowest 5 cm (a trunk foot)
            foot = [v for v in vs if v.z < zmin + 0.05]
        else:                                       # centre of the bounding box
            foot = [Vector((min(v.x for v in vs), min(v.y for v in vs), 0)), Vector((max(v.x for v in vs), max(v.y for v in vs), 0))]
        cx = sum(v.x for v in foot) / len(foot)
        cy = sum(v.y for v in foot) / len(foot)
        shadow_target = "shadow_target_pixel" in p or "shadow_target_xy" in p
        if shadow_target:
            zmax = max(v.z for v in vs)
            top = [v for v in vs if v.z > zmax - 0.15 * (zmax - zmin)]
            crown = sum(top, Vector()) / len(top) - Vector((cx, cy, zmin))
            target = ground_under_pixel(*p["shadow_target_pixel"]) if "shadow_target_pixel" in p \
                else ground_under_xy(*p["shadow_target_xy"])
            g = ground_under_xy(target.x - crown.x + sun.x * crown.z / sun.z,
                                target.y - crown.y + sun.y * crown.z / sun.z)
        elif "xy" in p:
            g = ground_under_xy(*p["xy"])
        else:
            g = ground_under_pixel(*p["pixel"])
        obj.location = (g.x - cx, g.y - cy, g.z - zmin - p.get("sink_m", 0.0))
        bpy.context.view_layer.update()
        placed = _world_vertices(meshes)
        for poly in keep_out_xy:
            pts = np.array([(v.x, v.y) for v in placed[::max(1, len(placed) // 4000)]])
            if _inside_any(poly, pts):
                raise RuntimeError(f"prop {p['object']} enters the keep-out area {poly.tolist()}")
        q = [world_to_camera_view(scene, cam, v) for v in placed]
        behind = any(v.z <= 0 for v in q)
        box = None
        if not behind:
            xs = [v.x * W for v in q]
            ys = [(1 - v.y) * H for v in q]
            box = [min(xs), min(ys), max(xs), max(ys)]
            inside = box[0] >= 0 and box[1] >= 0 and box[2] <= W and box[3] <= H
            if not inside and not p.get("allow_out_of_frame"):
                raise RuntimeError(f"prop {p['object']} leaves the frame: {box}")
            for k in keep_out:
                if not (box[2] < k[0] or box[0] > k[2] or box[3] < k[1] or box[1] > k[3]):
                    raise RuntimeError(f"prop {p['object']} overlaps keep-out box {k}: {box}")
        elif not shadow_target and not p.get("allow_out_of_frame"):
            raise RuntimeError(f"prop {p['object']} is behind the camera")
        for m in meshes:
            for slot in m.material_slots:
                if slot.material is None or not slot.material.use_nodes:
                    continue
                for n in slot.material.node_tree.nodes:
                    if n.type == "TEX_IMAGE" and n.image is not None and n.image.size[0] == 0:
                        raise RuntimeError(f"prop {p['object']}: texture {n.image.name} did not load")
        report.append({"object": p["object"], "file": p["file"], "location_m": [round(c, 4) for c in obj.location],
                       "scale": p.get("scale", 1.0), "frame_box_px": None if box is None else [round(b, 1) for b in box],
                       "behind_camera": behind})
    return report


# --------------------------------------------------------------------------- entry
def apply_look(config_path=None, device="CPU"):
    cfg = load_config(config_path)
    scene = bpy.context.scene
    camera_before = (tuple(scene.camera.matrix_world.translation), tuple(scene.camera.matrix_world.to_euler()),
                     scene.camera.data.lens, scene.camera.data.sensor_width)
    clear_diorama(cfg)
    sun_dir = build_world(cfg)
    beach = Beach(cfg, scene)   # shoreline_pixels refer to the scene's own camera
    override = override_camera(cfg, scene)
    terrain, footprint = build_terrain(cfg, beach, scene)
    sea, sea_level = build_sea(cfg, beach, scene)
    props = place_props(cfg, scene, sun_dir, terrain)
    fabric, ends, frame = build_hammock(cfg, scene)
    supports = build_supports(cfg, ends, beach)
    ball_radius, gaps = contact_gaps(scene, fabric)
    first = next((i for i, g in enumerate(gaps) if g < 0.03), None)
    after = np.array(gaps[first:]) if first is not None else np.array([])
    ball_materials(cfg)
    camera = configure_camera(cfg, scene)
    configure_render(cfg, scene, device)
    camera_after = (tuple(scene.camera.matrix_world.translation), tuple(scene.camera.matrix_world.to_euler()),
                    scene.camera.data.lens, scene.camera.data.sensor_width)
    if override is None:
        if camera_before != camera_after:
            raise RuntimeError("The look must not move the camera")
    else:
        # only the configured override may move the camera
        want_loc = Vector(override["location_m"])
        want_rot = [math.radians(a) for a in override["rotation_deg"]]
        got = scene.camera.matrix_world
        if ((got.translation - want_loc).length > 1e-5 or abs(scene.camera.data.lens - override["lens_mm"]) > 1e-6
                or max(abs(a - b) for a, b in zip(got.to_euler("XYZ"), want_rot)) > 1e-5
                or scene.camera.data.sensor_width != camera_before[3]):
            raise RuntimeError("camera does not match camera.override")
    scene.frame_set(1)
    report = {
        "preset": cfg["appearance"]["preset"],
        "config": str(Path(config_path or DEFAULT_CONFIG).name),
        "sun_direction_world": list(sun_dir),
        "sea_level_z_m": sea_level,
        "shoreline_point_m": beach.p1.tolist(),
        "shoreline_sea_normal": beach.sea_normal.tolist(),
        "displaced_sand_footprint_m": footprint.round(3).tolist(),
        "hammock_frame": {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in frame.items()},
        "supports": supports,
        "ball_radius_m": ball_radius,
        "visible_canvas_contact": {
            "definition": "ball surface to visible canvas mid-plane (MPM mid-surface + contact offset, laid onto the ball where it would penetrate); canvas half thickness is included in the contact radius",
            "first_contact_frame": None if first is None else first + scene.frame_start,
            "gap_min_m": float(after.min()) if after.size else None,
            "gap_median_m": float(np.median(after)) if after.size else None,
            "gap_max_m": float(after.max()) if after.size else None,
            "gap_per_frame_m": [round(float(g), 5) for g in gaps],
        },
        "camera": camera,
        "render_device": scene["pcve_render_device"],
    }
    if cfg["appearance"].get("props"):
        report["sea_animated"] = cfg["appearance"]["sea"].get("animate", True)
        report["props"] = props
    if override is not None:
        report["camera_override"] = {"from": {"location": list(camera_before[0]), "rotation_euler_rad": list(camera_before[1]),
                                              "lens_mm": camera_before[2]}, "to": override}
    scene["pcve_appearance_preset"] = cfg["appearance"]["preset"]
    return report
