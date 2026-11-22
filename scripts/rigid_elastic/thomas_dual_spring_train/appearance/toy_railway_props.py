"""Static accessories from the same wooden railway set as the train: tunnel, trees, signal.

Purely visual. Dimensions follow common wooden train sets (40 mm gauge track).
"""
import math

import bpy
from mathutils import Vector


def _metric_uv(obj, period=.2, offset=(.1, .3)):
    layer = obj.data.uv_layers.active or obj.data.uv_layers.new()
    for polygon in obj.data.polygons:
        axis = max(range(3), key=lambda k: abs(polygon.normal[k]))
        a, b = ((1, 2) if axis == 0 else (0, 2) if axis == 1 else (0, 1))
        for li in polygon.loop_indices:
            co = obj.data.vertices[obj.data.loops[li].vertex_index].co
            layer.data[li].uv = (co[a] / period + offset[0], co[b] / period + offset[1])


def _finish(obj, material, bevel=.0012, smooth=False):
    obj.data.materials.append(material)
    seed = sum(map(ord, obj.name))  # Stable between runs and cases, unlike hash().
    _metric_uv(obj, offset=(seed % 97 / 97, seed % 89 / 89))
    if smooth:
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    if bevel:
        mod = obj.modifiers.new("Sanded toy edge", "BEVEL")
        mod.width = bevel
        mod.segments = 3
        mod.limit_method = "ANGLE"
    # Saw marks and uneven sanding: silhouettes and highlights must not be mathematically clean.
    subdivide = obj.modifiers.new("Surface refinement", "SUBSURF")
    subdivide.subdivision_type = "SIMPLE"
    subdivide.levels = subdivide.render_levels = 3
    wobble = obj.modifiers.new("Hand cut unevenness", "DISPLACE")
    wobble.texture = _wobble_texture()
    wobble.texture_coords = "GLOBAL"
    wobble.strength = .0011
    wobble.mid_level = .5
    return obj


def _wobble_texture():
    texture = bpy.data.textures.get("Toy hand cut wobble")
    if texture is None:
        texture = bpy.data.textures.new("Toy hand cut wobble", type="CLOUDS")
        texture.noise_scale = .009
        texture.noise_depth = 3
    return texture


def _mesh(name, vertices, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def _cylinder(name, location, radius, height, material, radius_top=None, vertices=48, bevel=.0008):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius, radius2=radius if radius_top is None else radius_top,
                                    depth=height, location=(location[0], location[1], location[2] + height / 2))
    obj = bpy.context.object
    obj.name = name
    for polygon in obj.data.polygons:
        polygon.use_smooth = len(polygon.vertices) == 4
    return _finish(obj, material, bevel)


def tunnel(location, rot_z, wood, roof, length=.135, width=.086, height=.082, radius=.027):
    """Arched block the track would pass through, standing beside the line."""
    half, arch = width / 2, radius * 1.15
    corner = math.atan2(height / arch, half / radius)
    angles = sorted({math.pi * i / 32 for i in range(33)} | {corner, math.pi - corner})
    inner, outer = [], []
    for angle in angles:
        c, s = math.cos(angle), math.sin(angle)
        inner.append((radius * c, arch * s))
        reach = min(half / abs(radius * c) if abs(c) > 1e-9 else 1e9, height / (arch * s) if s > 1e-9 else 1e9)
        outer.append((radius * c * reach, arch * s * reach))
    ring = inner + outer  # Quad strips only: a concave n-gon collapses under subdivision.
    n = len(angles)
    vertices = [(-length / 2, y, z) for y, z in ring] + [(length / 2, y, z) for y, z in ring]
    both = 2 * n
    faces = []
    for i in range(n - 1):
        faces.append((i, n + i, n + i + 1, i + 1))  # Front face.
        faces.append((both + i + 1, both + n + i + 1, both + n + i, both + i))  # Back face.
        faces.append((i, i + 1, both + i + 1, both + i))  # Arch soffit.
        faces.append((n + i + 1, n + i, both + n + i, both + n + i + 1))  # Sides and top.
    faces.append((0, both, both + n, n))  # Base strips.
    faces.append((n - 1, 2 * n - 1, both + 2 * n - 1, both + n - 1))
    body = _finish(_mesh("Toy railway tunnel", vertices, faces), wood, .0016)
    cap = _finish(_mesh("Toy tunnel painted roof", [(-length / 2 - .003, -width / 2 - .003, height), (length / 2 + .003, -width / 2 - .003, height),
                                                    (length / 2 + .003, width / 2 + .003, height), (-length / 2 - .003, width / 2 + .003, height),
                                                    (-length / 2 - .003, -width / 2 - .003, height + .007), (length / 2 + .003, -width / 2 - .003, height + .007),
                                                    (length / 2 + .003, width / 2 + .003, height + .007), (-length / 2 - .003, width / 2 + .003, height + .007)],
                                  [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]), roof, .0014)
    for part in (body, cap):
        for co in part.data.vertices:  # Hand-cut toy: nothing is perfectly square.
            co.co.x += .0012 * math.sin(co.co.y * 61 + co.co.z * 37)
            co.co.z += .0007 * math.sin(co.co.x * 47)
        part.location = location
        part.rotation_euler[2] = rot_z
    return [body, cap]


def tree(location, wood, leaf, height=.085, radius=.027):
    x, y, z = location
    base = _cylinder("Toy tree base", (x, y, z), .021, .011, wood)
    trunk = _cylinder("Toy tree dowel", (x, y, z + .011), .0052, .03, wood, bevel=0)
    crown = _cylinder("Toy tree crown", (x, y, z + .034), radius, height, leaf, radius_top=.0015, bevel=.0012)
    crown.rotation_euler = (.018 * math.sin(x * 40), .018 * math.cos(y * 40), 0)  # Glued by hand, slightly off plumb.
    return [base, trunk, crown]


def signal(location, rot_z, wood, red, white):
    x, y, z = location
    base = _finish(_mesh("Toy signal base", _box_vertices(x, y, z, .034, .026, .010), _BOX_FACES), wood, .0012)
    post = _cylinder("Toy signal post", (x, y, z + .010), .0042, .092, white, bevel=0)
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=.0165, depth=.0045, location=(x, y - .006, z + .094), rotation=(math.pi / 2, 0, 0))
    disc = bpy.context.object
    disc.name = "Toy signal disc"
    for polygon in disc.data.polygons:
        polygon.use_smooth = len(polygon.vertices) == 4
    _finish(disc, red, .0007)
    parts = [base, post, disc]
    for part in parts:
        pivot = Vector((x, y, 0))
        offset = (part.location - pivot) if part is disc else Vector((0, 0, 0))
        if part is disc:
            offset.rotate(__import__("mathutils").Euler((0, 0, rot_z)))
            part.location = pivot + offset
            part.rotation_euler[2] = rot_z
    return parts


_BOX_FACES = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def _box_vertices(x, y, z, sx, sy, sz):
    return [(x - sx / 2, y - sy / 2, z), (x + sx / 2, y - sy / 2, z), (x + sx / 2, y + sy / 2, z), (x - sx / 2, y + sy / 2, z),
            (x - sx / 2, y - sy / 2, z + sz), (x + sx / 2, y - sy / 2, z + sz), (x + sx / 2, y + sy / 2, z + sz), (x - sx / 2, y + sy / 2, z + sz)]
