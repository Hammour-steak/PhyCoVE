"""Shared appearance helpers for the PCVE realism pass.

Everything here changes looks only: no solver state, collision shape or edit
parameter is read or written. Scene overlays call these after their builder has
produced the delivered scene.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
from pathlib import Path
import random
import subprocess


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def host_record():
    """Actual machine and GPU, never a placeholder from the delivered worker table."""
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    query = subprocess.run(["nvidia-smi", "--query-gpu=uuid,name,memory.total", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=20).stdout.splitlines()
    gpu = next((row for row in query if row.startswith(visible)), "") if visible else ""
    return {"host": platform.node(), "cuda_visible_devices": visible, "gpu": gpu}


def _bpy():
    import bpy
    return bpy


def world_bbox(objects):
    from mathutils import Vector
    bpy = _bpy()
    bpy.context.view_layer.update()
    points = [o.matrix_world @ Vector(c) for o in objects if o.type == "MESH" for c in o.bound_box]
    low = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    return low, high


def import_prop(path, name, location, rot_z=0.0, scale=1.0, tilt=None, lay_flat=False):
    """Import a metric glTF so its bbox sits with bottom centre on `location`.

    `lay_flat` turns the thinnest axis upright: scans of hand tools ship standing.
    """
    from mathutils import Matrix, Vector
    bpy = _bpy()
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for obj in new:
        if obj.parent is None:
            obj.parent = root
    root.scale = (scale, scale, scale)
    bpy.context.view_layer.update()
    if lay_flat:
        low, high = world_bbox(new)
        extent = high - low
        thinnest = min(range(3), key=lambda i: extent[i])
        tilt = {0: (0.0, math.pi / 2), 1: (math.pi / 2, 0.0), 2: (0.0, 0.0)}[thinnest]
    root.rotation_euler = (*(tilt or (0.0, 0.0)), rot_z)
    bpy.context.view_layer.update()
    low, high = world_bbox(new)
    root.location = Vector(location) - Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, low.z))
    bpy.context.view_layer.update()
    root["realism_members"] = len(new)
    return root, new


def assert_supported(members, label, tolerance=.012, inset=.15):
    """Fail if a prop's footprint hangs off the surface it is meant to stand on."""
    from mathutils import Vector
    bpy = _bpy()
    low, high = world_bbox(members)
    for member in members:  # The prop must not count as its own support.
        member.hide_viewport = True
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    try:
        for fx, fy in ((.5, .5), (inset, inset), (1 - inset, inset), (inset, 1 - inset), (1 - inset, 1 - inset)):
            origin = Vector((low.x + (high.x - low.x) * fx, low.y + (high.y - low.y) * fy, low.z + tolerance))
            hit, point, _, _, _, _ = bpy.context.scene.ray_cast(graph, origin, Vector((0, 0, -1)))
            if not hit or abs(point.z - low.z) > tolerance:
                raise RuntimeError(f"{label} overhangs at {fx},{fy}: support {point.z if hit else None} vs base {low.z}")
    finally:
        for member in members:
            member.hide_viewport = False
        bpy.context.view_layer.update()


def prop(root, name, location, rot_z=0.0, keepout=None, rests=False, **kw):
    """Place one of a scene's own props; `keepout` guards motion, `rests` guards overhang."""
    path = next((Path(root) / name).glob("*.gltf"))
    _, members = import_prop(path, "Dressing " + name, location, rot_z, **kw)
    if rests:
        assert_supported(members, name)
    return assert_clear(members, keepout, name) if keepout else {"label": name, "location": list(location)}


def assert_clear(objects, keepout, label):
    """Fail if a static addition intrudes on a swept motion volume of any case."""
    low, high = world_bbox(objects)
    (x0, y0, z0), (x1, y1, z1) = keepout
    if low.x < x1 and high.x > x0 and low.y < y1 and high.y > y0 and low.z < z1 and high.z > z0:
        raise RuntimeError(f"{label} enters the motion corridor: {tuple(low)} .. {tuple(high)}")
    return {"label": label, "bbox_low_m": list(low), "bbox_high_m": list(high)}


def _principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def _object_noise(nodes, links, scale, detail=4.0, stretch=None):
    coord = nodes.new("ShaderNodeTexCoord")
    source = coord.outputs["Object"]
    if stretch:
        mul = nodes.new("ShaderNodeVectorMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = stretch
        links.new(source, mul.inputs[0])
        source = mul.outputs[0]
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = detail
    links.new(source, noise.inputs["Vector"])
    return noise


def add_surface_wear(mat, smudge=0.16, grime=0.14, scratch=0.10, scale=1.0):
    """Handling marks: broad roughness smudges, tonal drift, fine directional scratches."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = _principled(mat)
    rough = bs.inputs["Roughness"]
    previous = rough.links[0].from_socket if rough.is_linked else None
    base_value = rough.default_value
    broad = _object_noise(nodes, links, 5.0 / scale, 6.0)
    fine = _object_noise(nodes, links, 38.0 / scale, 5.0)
    lines = _object_noise(nodes, links, 16.0 / scale, 2.0, (1.0, 26.0, 1.0))
    ramp = nodes.new("ShaderNodeMapRange")
    ramp.inputs["From Min"].default_value = 0.56
    ramp.inputs["From Max"].default_value = 0.66
    links.new(lines.outputs["Fac"], ramp.inputs["Value"])
    combo = nodes.new("ShaderNodeMath")
    combo.operation = "ADD"
    if previous:
        links.new(previous, combo.inputs[0])
    else:
        combo.inputs[0].default_value = base_value
    smear = nodes.new("ShaderNodeMath")
    smear.operation = "MULTIPLY_ADD"
    links.new(broad.outputs["Fac"], smear.inputs[0])
    smear.inputs[1].default_value = smudge * 2.0
    smear.inputs[2].default_value = -smudge
    links.new(smear.outputs[0], combo.inputs[1])
    marks = nodes.new("ShaderNodeMath")
    marks.operation = "MULTIPLY_ADD"
    links.new(ramp.outputs[0], marks.inputs[0])
    marks.inputs[1].default_value = scratch
    links.new(combo.outputs[0], marks.inputs[2])
    clamp = nodes.new("ShaderNodeClamp")
    clamp.inputs["Min"].default_value = 0.08
    clamp.inputs["Max"].default_value = 0.98
    links.new(marks.outputs[0], clamp.inputs["Value"])
    links.new(clamp.outputs[0], rough)
    base = bs.inputs["Base Color"]
    color = base.links[0].from_socket if base.is_linked else None
    tone = nodes.new("ShaderNodeMapRange")
    tone.inputs["From Min"].default_value = 0.3
    tone.inputs["From Max"].default_value = 0.7
    tone.inputs["To Min"].default_value = 1.0 - grime
    tone.inputs["To Max"].default_value = 1.0 + grime * 0.35
    links.new(fine.outputs["Fac"], tone.inputs["Value"])
    mix = nodes.new("ShaderNodeVectorMath")
    mix.operation = "SCALE"
    if color:
        links.new(color, mix.inputs[0])
    else:
        mix.inputs[0].default_value = tuple(base.default_value)[:3]
    links.new(tone.outputs[0], mix.inputs["Scale"])
    links.new(mix.outputs[0], base)


def add_wall_mottling(mat, amount=0.09, bump=0.00025):
    """Hand-painted wall: roller lap tone variation and faint plaster relief."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = _principled(mat)
    base = tuple(bs.inputs["Base Color"].default_value)[:3]
    broad = _object_noise(nodes, links, 1.6, 7.0)
    tone = nodes.new("ShaderNodeMapRange")
    tone.inputs["From Min"].default_value = 0.32
    tone.inputs["From Max"].default_value = 0.68
    tone.inputs["To Min"].default_value = 1.0 - amount
    tone.inputs["To Max"].default_value = 1.0 + amount
    links.new(broad.outputs["Fac"], tone.inputs["Value"])
    scale = nodes.new("ShaderNodeVectorMath")
    scale.operation = "SCALE"
    scale.inputs[0].default_value = base
    links.new(tone.outputs[0], scale.inputs["Scale"])
    links.new(scale.outputs[0], bs.inputs["Base Color"])
    relief = _object_noise(nodes, links, 95.0, 5.0)
    height = nodes.new("ShaderNodeBump")
    height.inputs["Distance"].default_value = bump
    height.inputs["Strength"].default_value = 0.6
    links.new(relief.outputs["Fac"], height.inputs["Height"])
    links.new(height.outputs[0], bs.inputs["Normal"])


def scan_material(name, folder, prefix, normal=1.0, rough_floor=.68, specular=.28):
    """Matte PBR material from a scanned diff/rough/nor_gl set, for props with no glossy finish."""
    bpy = _bpy()
    folder = Path(folder)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = _principled(mat)
    uv = nodes.new("ShaderNodeTexCoord")

    def image(kind, data=True):
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(folder / f"{prefix}_{kind}_2k.jpg"), check_existing=True)
        if data:
            tex.image.colorspace_settings.name = "Non-Color"
        links.new(uv.outputs["UV"], tex.inputs["Vector"])
        return tex

    links.new(image("diff", False).outputs["Color"], bs.inputs["Base Color"])
    floor = nodes.new("ShaderNodeMath")
    floor.operation = "MAXIMUM"
    floor.inputs[1].default_value = rough_floor
    links.new(image("rough").outputs["Color"], floor.inputs[0])
    links.new(floor.outputs[0], bs.inputs["Roughness"])
    bump = nodes.new("ShaderNodeNormalMap")
    bump.inputs["Strength"].default_value = normal
    links.new(image("nor_gl").outputs["Color"], bump.inputs["Color"])
    links.new(bump.outputs[0], bs.inputs["Normal"])
    if "Specular IOR Level" in bs.inputs:
        bs.inputs["Specular IOR Level"].default_value = specular
    return mat


def stained_wood(base, name, tint, wear=.55):
    """Copy of a scanned wood with translucent stain: grain shows through, edges rub back to bare wood."""
    mat = base.copy()
    mat.name = name
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = _principled(mat)
    grain = bs.inputs["Base Color"].links[0].from_socket
    stain = nodes.new("ShaderNodeMixRGB")
    stain.blend_type = "MULTIPLY"
    stain.inputs[0].default_value = 1.0
    stain.inputs[2].default_value = (*tint, 1)
    links.new(grain, stain.inputs[1])
    geometry = nodes.new("ShaderNodeNewGeometry")
    blotch = _object_noise(nodes, links, 150.0, 5.0)
    rub = nodes.new("ShaderNodeMapRange")  # Convex edges wear first, broken up by noise.
    rub.inputs["From Min"].default_value = .56
    rub.inputs["From Max"].default_value = .68
    links.new(geometry.outputs["Pointiness"], rub.inputs["Value"])
    amount = nodes.new("ShaderNodeMath")
    amount.operation = "MULTIPLY"
    amount.use_clamp = True
    links.new(rub.outputs[0], amount.inputs[0])
    spot = nodes.new("ShaderNodeMapRange")
    spot.inputs["From Min"].default_value = .42
    spot.inputs["From Max"].default_value = .55
    spot.inputs["To Max"].default_value = wear * 1.6
    links.new(blotch.outputs["Fac"], spot.inputs["Value"])
    links.new(spot.outputs[0], amount.inputs[1])
    mix = nodes.new("ShaderNodeMixRGB")
    links.new(amount.outputs[0], mix.inputs[0])
    links.new(stain.outputs[0], mix.inputs[1])
    links.new(grain, mix.inputs[2])
    links.new(mix.outputs[0], bs.inputs["Base Color"])
    return mat


def plain_box(name, centre, size, mat):
    bpy = _bpy()
    bpy.ops.mesh.primitive_cube_add(size=1, location=centre)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat:
        obj.data.materials.append(mat)
    return obj


def diffuse(name, color, rough=0.85):
    bpy = _bpy()
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bs = _principled(mat)
    bs.inputs["Base Color"].default_value = (*color, 1)
    bs.inputs["Roughness"].default_value = rough
    return mat


def daylight_room(x_min, x_max, y_min, y_back, z_floor, z_ceil, window, wall=(.68, .66, .60),
                  ceiling=(.78, .77, .74), floor=(.18, .12, .08), mullion=.045, back_wall=False):
    """Closed room whose only daylight enters through a real window in the x_min wall.

    `window` = (y0, y1, z0, z1, n_vertical, n_horizontal). The shell is real
    bounce geometry, so ambient comes from the room instead of a uniform dome.
    """
    wall_mat, ceil_mat, floor_mat = diffuse("Room wall", wall), diffuse("Room ceiling", ceiling), diffuse("Room floor", floor, .55)
    frame_mat = diffuse("Window frame", (.62, .60, .55), .5)
    t = .06
    y0, y1, z0, z1, n_v, n_h = window
    cy, sy = (y_min + y_back) / 2, y_back - y_min
    cz, sz = (z_floor + z_ceil) / 2, z_ceil - z_floor
    x = x_min - t / 2
    made = [
        plain_box("Room floor", ((x_min + x_max) / 2, cy, z_floor - t / 2), (x_max - x_min + 2 * t, sy + 2 * t, t), floor_mat),
        plain_box("Room ceiling", ((x_min + x_max) / 2, cy, z_ceil + t / 2), (x_max - x_min + 2 * t, sy + 2 * t, t), ceil_mat),
        plain_box("Room right wall", (x_max + t / 2, cy, cz), (t, sy, sz), wall_mat),
        plain_box("Room front wall", ((x_min + x_max) / 2, y_min - t / 2, cz), (x_max - x_min, t, sz), wall_mat),
        plain_box("Window wall lower", (x, cy, (z_floor + z0) / 2), (t, sy, z0 - z_floor), wall_mat),
        plain_box("Window wall upper", (x, cy, (z1 + z_ceil) / 2), (t, sy, z_ceil - z1), wall_mat),
        plain_box("Window wall near", (x, (y_min + y0) / 2, (z0 + z1) / 2), (t, y0 - y_min, z1 - z0), wall_mat),
        plain_box("Window wall far", (x, (y1 + y_back) / 2, (z0 + z1) / 2), (t, y_back - y1, z1 - z0), wall_mat),
    ]
    if back_wall:
        made.append(plain_box("Room back wall", ((x_min + x_max) / 2, y_back + t / 2, cz), (x_max - x_min, t, sz), wall_mat))
    for i in range(1, n_v + 1):
        yy = y0 + (y1 - y0) * i / (n_v + 1)
        made.append(plain_box(f"Window mullion v{i}", (x, yy, (z0 + z1) / 2), (t, mullion, z1 - z0), frame_mat))
    for i in range(1, n_h + 1):
        zz = z0 + (z1 - z0) * i / (n_h + 1)
        made.append(plain_box(f"Window mullion h{i}", (x, (y0 + y1) / 2, zz), (t, y1 - y0, mullion), frame_mat))
    return made


def sun(name, direction, energy, angle_deg=1.2, color=(1.0, .93, .82)):
    """`direction` is the way the light travels, e.g. (0.85, 0.25, -0.45)."""
    from mathutils import Vector
    bpy = _bpy()
    data = bpy.data.lights.new(name, "SUN")
    data.energy = energy
    data.angle = math.radians(angle_deg)
    data.color = color
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.rotation_euler = Vector(direction).normalized().to_track_quat("-Z", "Y").to_euler()
    return obj


def surface_z(x, y, start=3.0, ignore=()):
    """Height of the first surface below (x, y), used to rest props on scanned shelves."""
    from mathutils import Vector
    bpy = _bpy()
    bpy.context.view_layer.update()
    origin = Vector((x, y, start))
    graph = bpy.context.evaluated_depsgraph_get()
    while True:
        hit, point, _, _, obj, _ = bpy.context.scene.ray_cast(graph, origin, Vector((0, 0, -1)))
        if not hit:
            raise RuntimeError(f"no surface below {x}, {y}")
        if not any(obj.name.startswith(prefix) for prefix in ignore):
            return point.z
        origin = point - Vector((0, 0, 1e-4))


def sawdust(name, regions, count, keepout, color=(.55, .40, .24), seed=7, size=(.0004, .0016), z=0.0):
    """Static fibres and flecks on a surface; rejects anything inside `keepout`."""
    bpy = _bpy()
    rng = random.Random(seed)
    verts, faces = [], []
    (kx0, ky0), (kx1, ky1) = keepout
    placed = 0
    while placed < count:
        x0, y0, x1, y1, weight = rng.choices(regions, weights=[r[4] for r in regions])[0]
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        if kx0 < x < kx1 and ky0 < y < ky1:
            continue
        length = rng.uniform(*size) * rng.choice((1, 1, 1, 2.5))
        width = length * rng.uniform(.25, .6)
        a = rng.uniform(0, math.tau)
        ca, sa = math.cos(a), math.sin(a)
        h = z + rng.uniform(.00004, .00018)
        base = len(verts)
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            px = sx * length / 2
            py = sy * width / 2
            verts.append((x + px * ca - py * sa, y + px * sa + py * ca, h + rng.uniform(0, .00012)))
        faces.append((base, base + 1, base + 2, base + 3))
        placed += 1
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    mesh.materials.append(diffuse(name + " material", color, .9))
    return obj


def lens_finish(scene, vignette=0.14, dispersion=0.004):
    """Mild optical falloff and lateral colour; no per-frame noise, so video stays stable."""
    import bpy
    if bpy.app.version >= (5, 0, 0):  # Compositor API moved; those scenes skip this mild finish.
        print("REALISM_KIT lens_finish skipped on Blender", bpy.app.version_string, flush=True)
        return
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    image = tree.nodes.new("CompositorNodeRLayers")
    lens = tree.nodes.new("CompositorNodeLensdist")
    lens.use_fit = True
    lens.inputs["Distortion"].default_value = 0.0
    lens.inputs["Dispersion"].default_value = dispersion
    tree.links.new(image.outputs["Image"], lens.inputs["Image"])
    mask = tree.nodes.new("CompositorNodeEllipseMask")
    mask.width = 1.18
    mask.height = 1.32
    blur = tree.nodes.new("CompositorNodeBlur")
    blur.filter_type = "GAUSS"
    blur.use_relative = True
    blur.factor_x = blur.factor_y = 30.0
    tree.links.new(mask.outputs["Mask"], blur.inputs["Image"])
    level = tree.nodes.new("CompositorNodeMapRange")
    level.inputs["To Min"].default_value = 1.0 - vignette
    level.inputs["To Max"].default_value = 1.0
    tree.links.new(blur.outputs["Image"], level.inputs["Value"])
    mix = tree.nodes.new("CompositorNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    tree.links.new(lens.outputs["Image"], mix.inputs[1])
    tree.links.new(level.outputs[0], mix.inputs[2])
    out = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(mix.outputs[0], out.inputs["Image"])


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
