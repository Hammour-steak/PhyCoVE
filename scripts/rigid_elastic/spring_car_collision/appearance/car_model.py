"""A plain die-cast toy coupe, modelled here: 230 mm long, enamel paint, smoked windows, four rolling wheels.

The body is a smooth loft of cross-sections (Catmull-Clark, level 3) with real
window openings, wheel arches cut into the sides, a dark front intake and lamp
lenses masked onto the paint. No brand, badge, number or lettering.

The same code makes the solver's collision input. `build_car(..., export_dir=D)`
writes the canonical geometry (car_geometry.json, car_body_points.npz,
car_body_surface.npz, car_body_surface_parts.json) from the final body mesh in
the chassis frame; a normal render rebuilds the mesh and checks it bit for bit
against those frozen files, so the rendered body is the body the solver hits.
Chassis frame: origin at the car body frame (0.040 m above the floor), x
forward (nose), y left, z up. Wheel pivots, radius and width are those of the
previous car, so the wheel dynamics are unchanged.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

WHEEL_ORDER = ["front_left", "front_right", "rear_left", "rear_right"]
LENGTH, WIDTH, ROOF_Z, BOTTOM_Z = 0.230, 0.110, 0.0385, -0.0345      # body extents in the chassis frame
COM_Z = 0.040                                                         # chassis frame above the floor
WHEEL_RADIUS, WHEEL_WIDTH = 0.024175624032511087, 0.016558504075180523
WHEEL_CENTERS = [[0.06689156630930683, 0.045088379948237126, -0.015824375967488917],
                 [0.06689156630930683, -0.045088379948237126, -0.015824375967488917],
                 [-0.06153003654907267, 0.045088379948237126, -0.015824375967488917],
                 [-0.06153003654907267, -0.045088379948237126, -0.015824375967488917]]
ARCH_RADIUS = 0.0285
PAINT = (0.035, 0.150, 0.400)
# Cross-sections, nose to tail: x, z_bottom, z_belt, z_top, half width low / at belt / at roof edge.
STATIONS = [
    ("nose", 0.115, -0.024, -0.006, -0.004, 0.038, 0.040, 0.030),
    ("bumper", 0.108, -0.030, -0.001, 0.001, 0.049, 0.051, 0.040),
    ("front arch", 0.090, -0.032, 0.003, 0.005, 0.053, 0.055, 0.044),
    ("hood", 0.060, -0.032, 0.007, 0.009, 0.054, 0.056, 0.046),
    ("windscreen base", 0.032, -0.032, 0.011, 0.012, 0.054, 0.056, 0.046),
    ("A pillar", 0.002, -0.032, 0.012, 0.037, 0.054, 0.056, 0.040),
    ("roof", -0.022, -0.032, 0.012, 0.038, 0.054, 0.056, 0.041),
    ("C pillar", -0.050, -0.032, 0.012, 0.036, 0.054, 0.056, 0.040),
    ("deck lid", -0.080, -0.032, 0.013, 0.015, 0.054, 0.056, 0.045),
    ("rear arch", -0.097, -0.032, 0.012, 0.014, 0.053, 0.055, 0.044),
    ("tail", -0.109, -0.029, 0.008, 0.010, 0.049, 0.051, 0.040),
    ("tail end", -0.115, -0.024, 0.002, 0.004, 0.038, 0.040, 0.030),
]
CABIN = ("windscreen base", "A pillar", "roof", "C pillar", "deck lid")
MAT = {"paint": 0, "glass": 1, "under": 2, "intake": 3, "liner": 4}


def _ring(z_bot, z_belt, z_top, w_low, w_belt, w_roof, cabin):
    """Closed section: bottom centre, left side up to the roof centre, right side back down."""
    if cabin:
        upper = [(w_roof, z_top - 0.004), (0.62 * w_roof, z_top)]
    else:                       # hood or deck: a low crown instead of a cabin
        upper = [(0.86 * w_belt, z_belt + 0.0018), (0.5 * w_belt, z_top + 0.0008)]
    left = [(0.74 * w_low, z_bot), (w_low, z_bot + 0.32 * (z_belt - z_bot)),
            (w_belt, z_belt - 0.006), (0.975 * w_belt, z_belt)] + upper
    ring = [(0.0, z_bot)] + left + [(0.0, z_top + (0.0 if cabin else 0.0012))]
    ring += [(-y, z) for y, z in reversed(left)]
    return ring        # 14 points; segment k joins point k and k+1 (13 -> 0)


def _segment_material(name_a, name_b, k):
    if k in (0, 13):
        return MAT["under"]
    cabin_pair = (name_a, name_b)
    window_strip = k in (4, 9)
    top = k in (5, 6, 7, 8)
    if cabin_pair == ("windscreen base", "A pillar"):
        return MAT["glass"] if top else MAT["paint"]
    if cabin_pair in (("A pillar", "roof"), ("roof", "C pillar")):
        return MAT["glass"] if window_strip else MAT["paint"]
    if cabin_pair == ("C pillar", "deck lid"):
        return MAT["glass"] if top else MAT["paint"]
    return MAT["paint"]


def _cage(bpy):
    import bmesh
    bm = bmesh.new()
    rings = []
    for name, x, zb, zbelt, ztop, wl, wb, wr in STATIONS:
        rings.append([bm.verts.new((x, y, z)) for y, z in _ring(zb, zbelt, ztop, wl, wb, wr, name in CABIN[1:-1])])
    for i in range(len(rings) - 1):
        for k in range(14):
            k2 = (k + 1) % 14
            face = bm.faces.new((rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]))
            face.material_index = _segment_material(STATIONS[i][0], STATIONS[i + 1][0], k)
    nose = bm.faces.new(list(reversed(rings[0])))
    nose.material_index = MAT["paint"]      # the intake is a flush mask in the paint shader
    tail = bm.faces.new(rings[-1])
    tail.material_index = MAT["paint"]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new("toy car | body")
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def _materials(bpy):
    def principled(name, color, rough, metallic=0.0, coat=0.0, coat_rough=0.05):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bs = mat.node_tree.nodes.get("Principled BSDF")
        bs.inputs["Base Color"].default_value = (*color, 1)
        bs.inputs["Roughness"].default_value = rough
        bs.inputs["Metallic"].default_value = metallic
        bs.inputs["Coat Weight"].default_value = coat
        bs.inputs["Coat Roughness"].default_value = coat_rough
        return mat

    paint = principled("Toy car | blue enamel over die-cast zinc, clear coat", PAINT, 0.30, coat=1.0, coat_rough=0.035)
    _lamp_masks(paint)
    glass = principled("Toy car | smoked window plastic", (0.018, 0.020, 0.024), 0.04, coat=1.0, coat_rough=0.02)
    under = principled("Toy car | black base plate plastic", (0.020, 0.020, 0.021), 0.55)
    intake = principled("Toy car | front intake, black plastic", (0.012, 0.012, 0.013), 0.45)
    _intake_mesh(intake)
    liner = principled("Toy car | wheel arch liner", (0.015, 0.015, 0.016), 0.7)
    tyre = principled("Toy car | rubber tyre", (0.021, 0.021, 0.022), 0.82)
    rim = principled("Toy car | satin chrome wheel", (0.62, 0.62, 0.64), 0.22, metallic=1.0)
    hub = principled("Toy car | dark hub", (0.05, 0.05, 0.055), 0.35, metallic=1.0)
    axle = principled("Toy car | steel axle", (0.45, 0.45, 0.47), 0.3, metallic=1.0)
    return {"paint": paint, "glass": glass, "under": under, "intake": intake, "liner": liner,
            "tyre": tyre, "rim": rim, "hub": hub, "axle": axle}


def _lamp_masks(mat):
    """Headlamp and tail-lamp lenses and the front intake masked onto the paint (flush, so the body surface is unchanged)."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    out = next(n for n in nodes if n.type == "OUTPUT_MATERIAL")
    paint = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    coord = nodes.new("ShaderNodeTexCoord")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coord.outputs["Object"], sep.inputs[0])
    absy = nodes.new("ShaderNodeMath"); absy.operation = "ABSOLUTE"
    links.new(sep.outputs["Y"], absy.inputs[0])

    def lens(x_from, sign, yc, ry, zc, rz, power=2.0):
        dy = nodes.new("ShaderNodeMath"); dy.operation = "SUBTRACT"
        links.new(absy.outputs[0], dy.inputs[0]); dy.inputs[1].default_value = yc
        ny = nodes.new("ShaderNodeMath"); ny.operation = "DIVIDE"
        links.new(dy.outputs[0], ny.inputs[0]); ny.inputs[1].default_value = ry
        if power != 2.0:
            ay = nodes.new("ShaderNodeMath"); ay.operation = "ABSOLUTE"; links.new(ny.outputs[0], ay.inputs[0])
            py = nodes.new("ShaderNodeMath"); py.operation = "POWER"; links.new(ay.outputs[0], py.inputs[0]); py.inputs[1].default_value = power / 2
            ny = py
        dz = nodes.new("ShaderNodeMath"); dz.operation = "SUBTRACT"
        links.new(sep.outputs["Z"], dz.inputs[0]); dz.inputs[1].default_value = zc
        nz = nodes.new("ShaderNodeMath"); nz.operation = "DIVIDE"
        links.new(dz.outputs[0], nz.inputs[0]); nz.inputs[1].default_value = rz
        if power != 2.0:
            az = nodes.new("ShaderNodeMath"); az.operation = "ABSOLUTE"; links.new(nz.outputs[0], az.inputs[0])
            pz = nodes.new("ShaderNodeMath"); pz.operation = "POWER"; links.new(az.outputs[0], pz.inputs[0]); pz.inputs[1].default_value = power / 2
            nz = pz
        vec = nodes.new("ShaderNodeCombineXYZ")
        links.new(ny.outputs[0], vec.inputs[0]); links.new(nz.outputs[0], vec.inputs[1])
        length = nodes.new("ShaderNodeVectorMath"); length.operation = "LENGTH"
        links.new(vec.outputs[0], length.inputs[0])
        inside = nodes.new("ShaderNodeMapRange")       # soft 4 % edge, antialiased
        inside.inputs["From Min"].default_value, inside.inputs["From Max"].default_value = 1.0, 0.96
        links.new(length.outputs["Value"], inside.inputs["Value"])
        ahead = nodes.new("ShaderNodeMapRange")
        sx = nodes.new("ShaderNodeMath"); sx.operation = "MULTIPLY"
        links.new(sep.outputs["X"], sx.inputs[0]); sx.inputs[1].default_value = sign
        links.new(sx.outputs[0], ahead.inputs["Value"])
        ahead.inputs["From Min"].default_value, ahead.inputs["From Max"].default_value = x_from, x_from + 0.0015
        both = nodes.new("ShaderNodeMath"); both.operation = "MULTIPLY"
        links.new(inside.outputs["Result"], both.inputs[0]); links.new(ahead.outputs["Result"], both.inputs[1])
        return both

    head = lens(0.100, 1.0, 0.034, 0.011, 0.0005, 0.0042)
    intake = lens(0.103, 1.0, 0.0, 0.027, -0.0150, 0.0065, power=6.0)
    tail = lens(0.100, -1.0, 0.036, 0.010, 0.0060, 0.0035)
    head_bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    head_bsdf.inputs["Base Color"].default_value = (0.85, 0.86, 0.84, 1)
    head_bsdf.inputs["Roughness"].default_value = 0.12
    head_bsdf.inputs["Metallic"].default_value = 0.6
    head_bsdf.inputs["Coat Weight"].default_value = 1.0
    tail_bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tail_bsdf.inputs["Base Color"].default_value = (0.45, 0.02, 0.015, 1)
    tail_bsdf.inputs["Roughness"].default_value = 0.15
    tail_bsdf.inputs["Coat Weight"].default_value = 1.0
    mix1 = nodes.new("ShaderNodeMixShader")
    links.new(head.outputs[0], mix1.inputs["Fac"])
    links.new(paint.outputs[0], mix1.inputs[1]); links.new(head_bsdf.outputs[0], mix1.inputs[2])
    mix2 = nodes.new("ShaderNodeMixShader")
    links.new(tail.outputs[0], mix2.inputs["Fac"])
    links.new(mix1.outputs[0], mix2.inputs[1]); links.new(tail_bsdf.outputs[0], mix2.inputs[2])
    intake_bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    intake_bsdf.inputs["Base Color"].default_value = (0.012, 0.012, 0.013, 1)
    intake_bsdf.inputs["Roughness"].default_value = 0.45
    mix3 = nodes.new("ShaderNodeMixShader")
    links.new(intake.outputs[0], mix3.inputs["Fac"])
    links.new(mix2.outputs[0], mix3.inputs[1]); links.new(intake_bsdf.outputs[0], mix3.inputs[2])
    links.new(mix3.outputs[0], out.inputs["Surface"])


def _intake_mesh(mat):
    """Fine moulded mesh in the front intake (bump only)."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    coord = nodes.new("ShaderNodeTexCoord")
    tex = nodes.new("ShaderNodeTexChecker")
    tex.inputs["Scale"].default_value = 260.0
    links.new(coord.outputs["Object"], tex.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.5
    bump.inputs["Distance"].default_value = 0.0002
    links.new(tex.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bs.inputs["Normal"])


def _apply(bpy, obj, modifier):
    bpy.context.view_layer.objects.active = obj
    with bpy.context.temp_override(object=obj, active_object=obj):
        bpy.ops.object.modifier_apply(modifier=modifier.name)


def _cylinder(bpy, name, radius, depth, location, mat, vertices=96, collection=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location,
                                        rotation=(math.pi / 2, 0, 0))
    obj = bpy.context.object
    obj.name = name
    if mat:
        obj.data.materials.append(mat)
    if collection is not None:
        for c in list(obj.users_collection):
            c.objects.unlink(obj)
        collection.objects.link(obj)
    return obj


def _body(bpy, collection, mats):
    mesh = _cage(bpy)
    obj = bpy.data.objects.new("toy car | body", mesh)
    collection.objects.link(obj)
    for key in ("paint", "glass", "under", "intake", "liner"):
        mesh.materials.append(mats[key])
    sub = obj.modifiers.new("Smooth body", "SUBSURF")
    sub.levels = sub.render_levels = 3
    _apply(bpy, obj, sub)
    # Normalise to the declared extents (the subdivided surface sits inside its cage).
    co = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    lo, hi = co.min(0), co.max(0)
    target_lo = np.array([-LENGTH / 2, -WIDTH / 2, BOTTOM_Z])
    target_hi = np.array([LENGTH / 2, WIDTH / 2, ROOF_Z])
    co = target_lo + (co - lo) * (target_hi - target_lo) / (hi - lo)
    mesh.vertices.foreach_set("co", co.ravel())
    mesh.update()
    # Wheel arches: a cylinder from each side into the body; the cut walls take the liner material.
    for i, (x, y, z) in enumerate(WHEEL_CENTERS):
        side = 1 if y > 0 else -1
        cutter = _cylinder(bpy, "Temporary arch cutter", ARCH_RADIUS, 0.05, (x, side * (0.026 + 0.025), z), mats["liner"])
        mod = obj.modifiers.new("Wheel arch", "BOOLEAN")
        mod.operation, mod.solver, mod.object = "DIFFERENCE", "EXACT", cutter
        mod.material_mode = "TRANSFER"
        _apply(bpy, obj, mod)
        bpy.data.objects.remove(cutter, do_unlink=True)
    for p in mesh.polygons:
        p.use_smooth = True
    with bpy.context.temp_override(object=obj, active_object=obj, selected_editable_objects=[obj]):
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(75))
    obj.pass_index = 2
    obj["pcve_part"] = "car_body"
    return obj


def _wheel(bpy, collection, pivot, mats, index):
    """Tyre with rounded shoulders, chromed five-hole rim, dark hub; axis along the pivot's y."""
    side = 1 if WHEEL_CENTERS[index][1] > 0 else -1
    tyre = _cylinder(bpy, "toy car | tyre " + WHEEL_ORDER[index], WHEEL_RADIUS, WHEEL_WIDTH, (0, 0, 0), mats["tyre"], 96, collection)
    bore = _cylinder(bpy, "Temporary tyre bore", 0.0150, WHEEL_WIDTH * 2, (0, 0, 0), None, 96)
    mod = tyre.modifiers.new("Tyre bore", "BOOLEAN")
    mod.operation, mod.solver, mod.object = "DIFFERENCE", "EXACT", bore
    _apply(bpy, tyre, mod)
    bpy.data.objects.remove(bore, do_unlink=True)
    bev = tyre.modifiers.new("Rounded shoulder", "BEVEL")
    bev.width, bev.segments, bev.limit_method = 0.0035, 5, "ANGLE"
    _apply(bpy, tyre, bev)
    rim = _cylinder(bpy, "toy car | rim " + WHEEL_ORDER[index], 0.0158, WHEEL_WIDTH - 0.002, (0, 0, 0), mats["rim"], 96, collection)
    for k in range(5):
        a = 2 * math.pi * k / 5
        hole = _cylinder(bpy, "Temporary rim hole", 0.0032, WHEEL_WIDTH, (0.0095 * math.cos(a), 0, 0.0095 * math.sin(a)), None, 32)
        mod = rim.modifiers.new("Rim hole", "BOOLEAN")
        mod.operation, mod.solver, mod.object = "DIFFERENCE", "EXACT", hole
        _apply(bpy, rim, mod)
        bpy.data.objects.remove(hole, do_unlink=True)
    hub = _cylinder(bpy, "toy car | hub " + WHEEL_ORDER[index], 0.0045, WHEEL_WIDTH - 0.001, (0, 0, 0), mats["hub"], 48, collection)
    for part in (tyre, rim, hub):
        part.parent = pivot
        part.pass_index = 2
        part["pcve_part"] = "car_wheel"
        part["pcve_wheel_index"] = index
        for p in part.data.polygons:
            p.use_smooth = True
        with bpy.context.temp_override(object=part, active_object=part, selected_editable_objects=[part]):
            bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    return [tyre, rim, hub]


def _surface(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    co = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    tri = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int64)
    mesh.loop_triangles.foreach_get("vertices", tri)
    return co, tri.reshape(-1, 3)


def build_car(bpy, geometry_dir, export_dir=None):
    """Build the car under one chassis root and four wheel pivots; return {root, wheels, metadata}."""
    geometry_dir = Path(geometry_dir) if geometry_dir else None
    collection = bpy.data.collections.new("Toy car")
    bpy.context.scene.collection.children.link(collection)
    mats = _materials(bpy)
    root = bpy.data.objects.new("car | physical chassis frame", None)
    collection.objects.link(root)
    root.pass_index = 2
    root["pcve_part"] = "car_body_root"
    body = _body(bpy, collection, mats)
    body.parent = root
    axles = []
    for x in (WHEEL_CENTERS[0][0], WHEEL_CENTERS[2][0]):
        axle = _cylinder(bpy, "toy car | axle", 0.0012, 2 * WHEEL_CENTERS[0][1], (x, 0, WHEEL_CENTERS[0][2]), mats["axle"], 24, collection)
        axle.parent = root
        axles.append(axle)
    pivots = []
    for i, centre in enumerate(WHEEL_CENTERS):
        pivot = bpy.data.objects.new("car | wheel pivot " + WHEEL_ORDER[i], None)
        collection.objects.link(pivot)
        pivot.location = centre
        pivot.pass_index = 2
        pivot["pcve_part"] = "car_wheel_root"
        pivot["pcve_wheel_index"] = i
        _wheel(bpy, collection, pivot, mats, i)
        pivots.append(pivot)
    points, triangles = _surface(body)
    lo, hi = points.min(0), points.max(0)
    metadata = {"source_key": "procedural_toy_coupe", "source": "Modelled in appearance/car_model.py (no external asset)",
                "license": "PCVE generated", "body_length_m": float(hi[0] - lo[0]), "body_width_m": float(hi[1] - lo[1]),
                "total_height_m": float(hi[2] + COM_Z), "chassis_com_above_table_m": COM_Z,
                "body_bbox_chassis_m": [lo.tolist(), hi.tolist()],
                "body_minimum_ground_clearance_m": float(lo[2] + COM_Z),
                "wheel_order": WHEEL_ORDER, "wheel_centers_local_m": WHEEL_CENTERS,
                "wheel_radius_m": WHEEL_RADIUS, "wheel_width_m": WHEEL_WIDTH,
                "front_track_half_width_m": abs(WHEEL_CENTERS[0][1]), "rear_track_half_width_m": abs(WHEEL_CENTERS[2][1]),
                "wheelbase_m": WHEEL_CENTERS[0][0] - WHEEL_CENTERS[2][0], "arch_radius_m": ARCH_RADIUS,
                "body_vertices": int(len(points)), "body_triangles": int(len(triangles)),
                "source_uniform_scale": 1.0, "source_to_chassis_matrix": np.eye(4).tolist(),
                "collision_geometry_points": "car_body_points.npz",
                "collision_model": "convex hull of the whole body surface (one component); wheels are the solver's four cylinders",
                "paint_linear_rgb": list(PAINT), "markings": "none (no badge, number, lettering or face)",
                "initial_travel": "Car starts at rest against the compressed spring's pusher; nose faces +X."}
    if export_dir is not None:
        export_dir = Path(export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(export_dir / "car_body_points.npz", vertices=points)
        np.savez_compressed(export_dir / "car_body_surface.npz", triangles=points[triangles],
                            source_object_ids=np.zeros(len(triangles), np.int32),
                            component_ids=np.zeros(len(triangles), np.int32))
        (export_dir / "car_body_surface_parts.json").write_text(json.dumps(
            {"schema_version": 1, "frame": "chassis-local metres", "triangles_file": "car_body_surface.npz",
             "parts": [{"source_object_id": 0, "component_id": 0, "role": "main_body", "vertices": int(len(points)),
                        "bbox_chassis_m": [lo.tolist(), hi.tolist()]}]}, indent=2) + "\n", encoding="utf-8")
        (export_dir / "car_geometry.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    else:
        with np.load(geometry_dir / "car_body_points.npz", allow_pickle=False) as frozen:
            stored = frozen["vertices"]
        equal = stored.shape == points.shape and float(np.max(np.abs(stored - points))) <= 1e-9
        contract = json.loads((geometry_dir / "car_geometry.json").read_text(encoding="utf-8"))
        fields = ["body_length_m", "body_width_m", "total_height_m", "chassis_com_above_table_m",
                  "wheel_centers_local_m", "wheel_radius_m", "wheel_width_m", "body_bbox_chassis_m"]
        worst = max(float(np.max(np.abs(np.asarray(metadata[k]) - np.asarray(contract[k])))) for k in fields)
        if not equal or worst > 1e-12:
            raise RuntimeError(f"Toy car body differs from the frozen solver geometry (points equal {equal}, fields {worst})")
        metadata["canonical_input_validation"] = {
            "body_points_equal_within_1e-9_m": equal, "maximum_field_difference_m": worst,
            "body_points_sha256": hashlib.sha256((geometry_dir / "car_body_points.npz").read_bytes()).hexdigest(),
            "contract_sha256": hashlib.sha256((geometry_dir / "car_geometry.json").read_bytes()).hexdigest()}
    root["asset_provenance"] = json.dumps({k: metadata[k] for k in ("source_key", "body_length_m", "markings")})
    return {"root": root, "wheels": pivots, "body": body, "axles": axles, "metadata": metadata}
