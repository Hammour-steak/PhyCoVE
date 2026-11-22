"""Moving parts at their solver dimensions: guided spring assembly, launcher frame, wooden blocks, coil helix.

The room, table, light and camera are appearance/look.py; the car is car_model.py.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

CAR_LENGTH = .230
CAR_COM_Z = .040
CAR_WHEEL_ORDER = ["front_left", "front_right", "rear_left", "rear_right"]


def material(bpy, name, color, roughness=.5, metallic=0):
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    bs = mat.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (*color, 1)
    bs.inputs["Roughness"].default_value = roughness
    bs.inputs["Metallic"].default_value = metallic
    return mat


def microfinish(mat, scale_m=36000, amplitude_m=.000014, strength=.13):
    n, l = mat.node_tree.nodes, mat.node_tree.links
    co = n.new("ShaderNodeTexCoord")
    noise = n.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = scale_m
    noise.inputs["Detail"].default_value = 2
    bump = n.new("ShaderNodeBump"); bump.inputs["Distance"].default_value = amplitude_m
    bump.inputs["Strength"].default_value = strength
    l.new(co.outputs["Object"], noise.inputs["Vector"])
    l.new(noise.outputs["Fac"], bump.inputs["Height"])
    l.new(bump.outputs["Normal"], n.get("Principled BSDF").inputs["Normal"])
    return mat


def cube(bpy, name, location, dimensions, mat, bevel=0, segments=4):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object; obj.name = name; obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat: obj.data.materials.append(mat)
    if bevel:
        m = obj.modifiers.new("Metric softly machined edge", "BEVEL")
        m.width = bevel; m.segments = segments
        obj.modifiers.new("Weighted corner normals", "WEIGHTED_NORMAL")
    return obj


def cylinder(bpy, name, location, radius, depth, mat, axis="Z", vertices=64, bevel=0):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object; obj.name = name
    obj.rotation_euler = (0, math.pi / 2, 0) if axis == "X" else ((math.pi / 2, 0, 0) if axis == "Y" else (0, 0, 0))
    if mat: obj.data.materials.append(mat)
    for p in obj.data.polygons: p.use_smooth = len(p.vertices) == 4
    if bevel:
        m = obj.modifiers.new("Deburred circular edge", "BEVEL"); m.width = bevel; m.segments = 3
        obj.modifiers.new("Weighted cap normals", "WEIGHTED_NORMAL")
    return obj


def apply_construction_modifier(bpy, obj, modifier):
    """Apply booleans before bevel/normal finish modifiers already on an object."""
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    while obj.modifiers.find(modifier.name) > 0:
        bpy.ops.object.modifier_move_up(modifier=modifier.name)
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def hollow_tube(bpy, name, outer_radius, inner_radius, length, mat, location=(0, 0, 0), segments=64):
    """Closed thin-wall tube along local X; geometry has a real bore."""
    vertices, faces = [], []
    for xx in [-length / 2, length / 2]:
        for rr in [outer_radius, inner_radius]:
            vertices.extend([(xx, rr * math.cos(a), rr * math.sin(a))
                             for a in np.linspace(0, 2 * math.pi, segments, endpoint=False)])
    for i in range(segments):
        j = (i + 1) % segments
        faces += [(i, j, 2 * segments + j, 2 * segments + i),
                  (segments + j, segments + i, 3 * segments + i, 3 * segments + j),
                  (j, i, segments + i, segments + j),
                  (2 * segments + i, 2 * segments + j, 3 * segments + j, 3 * segments + i)]
    mesh = bpy.data.meshes.new(name); mesh.from_pydata(vertices, [], faces); mesh.update()
    obj = bpy.data.objects.new(name, mesh); bpy.context.scene.collection.objects.link(obj)
    obj.location = location; mesh.materials.append(mat)
    # Smooth annular caps would tilt the only two longitudinal wall normals
    # toward ±X across the entire tube, turning a clear thin shell into a false
    # lens. Explicit radial side normals and flat caps preserve real optics.
    split_normals = [None] * len(mesh.loops)
    for polygon in mesh.polygons:
        face_kind = polygon.index % 4
        polygon.use_smooth = face_kind < 2
        for li in polygon.loop_indices:
            vertex = mesh.vertices[mesh.loops[li].vertex_index].co
            if face_kind < 2:
                radial = math.hypot(vertex.y, vertex.z); sign = 1 if face_kind == 0 else -1
                split_normals[li] = (0, sign * vertex.y / radial, sign * vertex.z / radial)
            else: split_normals[li] = (-1 if face_kind == 2 else 1, 0, 0)
    mesh.normals_split_custom_set(split_normals)
    return obj


def actual_mesh_volume(bpy, obj):
    """Volume of the actual evaluated closed mesh, including bores and bevels."""
    import bmesh
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh(); bm = bmesh.new(); bm.from_mesh(mesh)
    value = float(bm.calc_volume(signed=False)); bm.free(); evaluated.to_mesh_clear()
    return value


def _component_labels(mesh):
    """Connected topology islands, including UV-split shell pieces."""
    neighbors = [[] for _ in mesh.vertices]
    for edge in mesh.edges:
        a, b = edge.vertices; neighbors[a].append(b); neighbors[b].append(a)
    labels = np.full(len(neighbors), -1, np.int32); groups = []
    for start in range(len(neighbors)):
        if labels[start] >= 0: continue
        label = len(groups); stack = [start]; labels[start] = label; ids = []
        while stack:
            i = stack.pop(); ids.append(i)
            for j in neighbors[i]:
                if labels[j] < 0: labels[j] = label; stack.append(j)
        groups.append(np.array(ids, dtype=np.int32))
    return labels, groups


def _subset_mesh(bpy, source_mesh, keep_vertices, name):
    """Preserve source UVs, sharp normals and materials through mesh partition."""
    import bmesh
    mesh = source_mesh.copy(); mesh.name = name
    bm = bmesh.new(); bm.from_mesh(mesh); bm.verts.ensure_lookup_table()
    removed = [v for v in bm.verts if not keep_vertices[v.index]]
    bmesh.ops.delete(bm, geom=removed, context="VERTS")
    bm.to_mesh(mesh); bm.free(); mesh.update()
    return mesh




def metric_uv(obj, grain_axis=0):
    """Orthogonal metre UVs, preserving material coordinates under rigid motion."""
    uv = obj.data.uv_layers.new(name="MaterialMeters"); obj.data.uv_layers.active = uv
    for poly in obj.data.polygons:
        axis = max(range(3), key=lambda i: abs(poly.normal[i]))
        # The photographed scans have their grain along V; all long-cut sides
        # therefore place physical X along V. End cuts use their own Y/Z UVs.
        dims = ([1, 2] if axis == 0 else [2, 0] if axis == 1 else [1, 0])
        for li in poly.loop_indices:
            v = obj.data.vertices[obj.data.loops[li].vertex_index].co
            uv.data[li].uv = (v[dims[0]], v[dims[1]])
    return uv


def scan_material(bpy, asset_dir, key, physical_tile_m, name, normal_strength=.24, tint=None, roughness_range=None):
    """Photo-based CC0 colour/roughness/decoded OpenGL normal at physical extent."""
    mat = material(bpy, name, (.4, .3, .2), .55)
    n, l = mat.node_tree.nodes, mat.node_tree.links; bs = n.get("Principled BSDF")
    uv = n.new("ShaderNodeUVMap"); uv.uv_map = "MaterialMeters"
    mapping = n.new("ShaderNodeVectorMath"); mapping.operation = "SCALE"
    mapping.inputs[3].default_value = 1 / physical_tile_m; l.new(uv.outputs["UV"], mapping.inputs[0])
    folder = Path(asset_dir) / "cc0" / key
    for suffix, destination, noncolor in [("diff", "Base Color", False), ("rough", "Roughness", True),
                                           ("nor_gl", "Normal", True)]:
        suffixes = [suffix, "col"] if suffix == "diff" else [suffix]
        files = sorted([p for suf in suffixes for pattern in ["*" + suf + "_*.jpg", "*" + suf + "_*.png"]
                        for p in folder.glob(pattern)])
        if not files: raise FileNotFoundError(str(folder / ("*" + suffix + "_*")))
        tex = n.new("ShaderNodeTexImage"); tex.image = bpy.data.images.load(str(files[0]), check_existing=True)
        tex.image.colorspace_settings.name = "Non-Color" if noncolor else "sRGB"
        l.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        if destination == "Normal":
            normal = n.new("ShaderNodeNormalMap"); normal.uv_map = "MaterialMeters"
            normal.inputs["Strength"].default_value = normal_strength
            l.new(tex.outputs["Color"], normal.inputs["Color"]); l.new(normal.outputs["Normal"], bs.inputs["Normal"])
        elif destination == "Roughness" and roughness_range:
            remap = n.new("ShaderNodeMapRange")
            remap.inputs["To Min"].default_value, remap.inputs["To Max"].default_value = roughness_range
            l.new(tex.outputs["Color"], remap.inputs["Value"]); l.new(remap.outputs["Result"], bs.inputs[destination])
        elif destination == "Base Color" and tint:
            mix = n.new("ShaderNodeMixRGB"); mix.blend_type = "MULTIPLY"; mix.inputs[0].default_value = 1
            mix.inputs[2].default_value = (*tint, 1); l.new(tex.outputs["Color"], mix.inputs[1]); l.new(mix.outputs[0], bs.inputs[destination])
        else: l.new(tex.outputs["Color"], bs.inputs[destination])
    return mat


def endgrain_material(bpy):
    """Explicit end-cut growth rings and pores; not misrepresented as a scan."""
    mat = material(bpy, "Wood block end grain | analytic annual rings and pores", (.43, .27, .13), .70)
    n, l = mat.node_tree.nodes, mat.node_tree.links; bs = n.get("Principled BSDF")
    uv = n.new("ShaderNodeUVMap"); uv.uv_map = "MaterialMeters"
    centre = n.new("ShaderNodeVectorMath"); centre.operation = "ADD"; centre.inputs[1].default_value = (.032, .046, 0)
    l.new(uv.outputs["UV"], centre.inputs[0])
    noise = n.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = 95; noise.inputs["Detail"].default_value = 3.5
    l.new(centre.outputs["Vector"], noise.inputs["Vector"])
    distort = n.new("ShaderNodeVectorMath"); distort.operation = "SCALE"; distort.inputs[3].default_value = .005
    l.new(noise.outputs["Color"], distort.inputs[0])
    vector = n.new("ShaderNodeVectorMath"); vector.operation = "ADD"
    l.new(centre.outputs["Vector"], vector.inputs[0]); l.new(distort.outputs["Vector"], vector.inputs[1])
    rings = n.new("ShaderNodeTexWave"); rings.wave_type = "RINGS"; rings.rings_direction = "Z"
    rings.inputs["Scale"].default_value = 88; rings.inputs["Distortion"].default_value = 2.2
    rings.inputs["Detail Scale"].default_value = 4; l.new(vector.outputs["Vector"], rings.inputs["Vector"])
    ramp = n.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = .16; ramp.color_ramp.elements[0].color = (.18, .079, .026, 1)
    ramp.color_ramp.elements[1].position = .82; ramp.color_ramp.elements[1].color = (.57, .34, .16, 1)
    l.new(rings.outputs["Fac"], ramp.inputs["Fac"]); l.new(ramp.outputs["Color"], bs.inputs["Base Color"])
    pores = n.new("ShaderNodeTexNoise"); pores.inputs["Scale"].default_value = 16500
    pores.inputs["Detail"].default_value = 2; l.new(uv.outputs["UV"], pores.inputs["Vector"])
    bump = n.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = .20; bump.inputs["Distance"].default_value = .00006
    l.new(pores.outputs["Fac"], bump.inputs["Height"]); l.new(bump.outputs["Normal"], bs.inputs["Normal"])
    return mat


def build_block(bpy, asset_dir, dimensions=(.080, .085, .055)):
    from mathutils import Matrix
    side = scan_material(bpy, asset_dir, "fine_grained_wood", .600000024,
                         "Wood block long grain | CC0 fine-grained 4K scan", .25, (1.14, 1.07, .98))
    end = endgrain_material(bpy)
    block = cube(bpy, "block | solid fine-grained timber", (0, 0, 0), dimensions, side, .0008, 4)
    metric_uv(block); block.data.materials.append(end)
    for p in block.data.polygons:
        if abs(p.normal.x) > .8: p.material_index = 1
    block.pass_index = 3; block.rotation_mode = "QUATERNION"
    return {"root": block, "metadata": {"dimensions_m": list(dimensions),
             "edge_bevel_m": .0008, "side_texture": "Poly Haven fine_grained_wood 4K CC0, physical tile 600mm",
             "grain_axis": "+X", "end_faces": "±X analytic annual rings + end-cut pores; explicit procedural material",
             "hidden_ballast": "Heavier-block counterfactual uses hidden ballast in the same exterior solid-wood visual shape."}}


def coil_vertices(length, anchor_x, z, mean_diameter, wire_diameter, active_turns=16, end_turns=2,
                  samples_per_turn=48, tube_segments=12):
    """Constant-diameter wire helix with closed end pitch, cache-driven axial length."""
    total_turns = active_turns + end_turns
    count = total_turns * samples_per_turn + 1
    s = np.linspace(0, total_turns, count)
    # One close-wound turn at each end; only active pitch absorbs compression.
    active_pitch = (length - wire_diameter * end_turns) / active_turns
    x = np.where(s <= 1, s * wire_diameter,
                 np.where(s >= 1 + active_turns,
                          wire_diameter + active_turns * active_pitch + (s - 1 - active_turns) * wire_diameter,
                          wire_diameter + (s - 1) * active_pitch))
    angle = 2 * math.pi * s; r = mean_diameter / 2
    centers = np.stack([anchor_x + x, r * np.cos(angle), z + r * np.sin(angle)], 1)
    tangents = np.gradient(centers, axis=0); tangents /= np.linalg.norm(tangents, axis=1)[:, None]
    radial = np.stack([np.zeros(count), np.cos(angle), np.sin(angle)], 1)
    radial -= (radial * tangents).sum(1)[:, None] * tangents
    radial /= np.linalg.norm(radial, axis=1)[:, None]
    binormal = np.cross(tangents, radial)
    a = np.linspace(0, 2 * math.pi, tube_segments, endpoint=False)
    vertices = centers[:, None, :] + wire_diameter / 2 * (
        np.cos(a)[None, :, None] * radial[:, None, :] + np.sin(a)[None, :, None] * binormal[:, None, :])
    return vertices.reshape(-1, 3)


def _build_physical_spring(bpy, config, present=True):
    """Guided compression spring; only coil and slider are semantic A."""
    from mathutils import Matrix
    anchor = float(config.get("anchor_x", -.66)); length = float(config.get("free_length", .22))
    z = float(config.get("axis_height", .035)); diameter = float(config.get("mean_diameter", .030))
    wire = float(config.get("wire_diameter", .0012)); turns = int(config.get("active_coils", 16))
    ends = int(config.get("end_coils", 2)); plate_dimensions = config.get("plate_dimensions", [.006, .185, .060])
    steel = microfinish(material(bpy, "Spring and guides | brushed spring steel", (.21, .24, .27), .27, .96),
                        73000, .0000035, .09)
    brushed = microfinish(material(bpy, "Spring fixture | brushed aluminium", (.36, .39, .41), .47, .92),
                          45000, .000008, .14)
    dark = material(bpy, "Fixture bolts | blackened steel", (.036, .040, .046), .33, .84)
    back = cube(bpy, "Static fixture | bolted spring backstop", (anchor - .015, 0, .0375), (.030, .19, .075), brushed, .0015)
    back.pass_index = 4
    # The moving inner spring core can retract behind the anchor through this
    # genuine backstop bore; there is no stationary rod entering the toy car.
    hole = cylinder(bpy, "Temporary telescopic-core backstop tool", (anchor - .015, 0, z), .01450, .045, None, "X")
    bpy.context.view_layer.objects.active = back
    cut = back.modifiers.new("Telescopic spring-core through-bore", "BOOLEAN"); cut.operation = "DIFFERENCE"; cut.object = hole
    apply_construction_modifier(bpy, back, cut); bpy.data.objects.remove(hole, do_unlink=True)
    base = cube(bpy, "Static fixture | aluminium mounting foot", (anchor - .016, 0, .0015), (.056, .205, .003), brushed, .0007)
    base.pass_index = 4
    guide_y = float(config.get("guide_y", .079)); guide_z = float(config.get("guide_z", .019))
    guide_end = anchor + length + .009
    for yy in [-guide_y, guide_y]:
        rod = cylinder(bpy, "Static fixture | off-axis sliding guide rod", ((anchor + guide_end) / 2, yy, guide_z), .002,
                       guide_end - anchor, steel, "X", bevel=.0003); rod.pass_index = 4
        collar = cylinder(bpy, "Static fixture | guided slider return-stop hex nut", (anchor + length + .0045, yy, guide_z), .0048, .003,
                          dark, "X", vertices=6, bevel=.00025)
        collar.pass_index = 4
        for xx in np.linspace(anchor + length + .0062, guide_end, 5):
            thread = cylinder(bpy, "Static fixture | guide-end fine screw thread", (xx, yy, guide_z), .0022, .00022,
                              steel, "X", vertices=32); thread.pass_index = 4
    for yy in [-.077, .077]:
        bolt = cylinder(bpy, "Static fixture | recessed hex bolt", (anchor - .021, yy, .0042), .0035, .0022,
                        dark, vertices=6, bevel=.00025); bolt.pass_index = 4
    if not present:
        return {"coil": None, "plate": None, "metadata": {"present": False,
                "static_fixture_retained": True, "removed": ["active coil", "thin C-section pusher and bushes",
                "moving PETG telescope", "fixed clear PC spring-core telescope and mount"]}}
    # The 12 g solver mass is the whole moving assembly. A solid 6 mm aluminium
    # slab would weigh about180 g. A real thin C-section retains the same outer
    # contact envelope while its skins, returns, polymer bushes and core obey
    # an explicit volume/density budget.
    plate = bpy.data.objects.new("spring | physical guided lightweight pusher root", None)
    bpy.context.scene.collection.objects.link(plate); plate.location = (anchor + length, 0, z); plate.pass_index = 1
    moving_parts = []
    width, height, depth = float(plate_dimensions[1]), float(plate_dimensions[2]), float(plate_dimensions[0])
    skin_thickness, flange_thickness = .00015, .00035
    face = cube(bpy, "spring | 150 micron aluminium pusher front skin", (depth / 2 - skin_thickness / 2, 0, 0),
                (skin_thickness, width, height), brushed)
    face.parent = plate; face.pass_index = 1; moving_parts.append((face, 2700.0, "aluminium150umfrontskin"))
    for side in [-1, 1]:
        flange = cube(bpy, "spring | 0.35mm returned C-section flange", (-skin_thickness / 2, 0, side * (height / 2 - flange_thickness / 2)),
                      (depth - skin_thickness, width, flange_thickness), brushed)
        flange.parent = plate; flange.pass_index = 1; moving_parts.append((flange, 2700.0, "aluminium0.35mmreturn"))
    bpy.context.view_layer.update()
    for yy in [-guide_y, guide_y]:
        # Real apertures and hollow bushings match the ideal slider's mating
        # clearance; an unbored plate would visibly intersect the guide rods.
        hole = cylinder(bpy, "Temporary bored plate tool", (anchor + length, yy, guide_z), .0042, .026, None, "X")
        bpy.context.view_layer.objects.active = face
        modifier = face.modifiers.new("Guide through-hole " + str(yy), "BOOLEAN")
        modifier.operation = "DIFFERENCE"; modifier.object = hole
        apply_construction_modifier(bpy, face, modifier); bpy.data.objects.remove(hole, do_unlink=True)
        nylon = material(bpy, "POM guide bush | moulded dark engineering polymer " + str(yy), (.031, .036, .040), .48)
        sleeve = hollow_tube(bpy, "spring | hollow POM guide bush", .0041, .00212, depth, nylon,
                             location=(0, yy, guide_z - z))
        sleeve.parent = plate; sleeve.pass_index = 1
        moving_parts.append((sleeve, 1410.0, "POMguidebush"))
    # Three pressed channels reduce unsupported skin height to about14mm. The
    # central34mm disk-backed region remains flat; channel ends stop before the
    # guide-bush mounting area. All car-bearing flat skin remains at x=+3mm.
    rib_width, rib_depth = .0012, .0009
    for zz in [-.015, 0, .015]:
        for yy in [-.046, .046]:
            rib_length = .056
            cut_tool = cube(bpy, "Temporary pressed-channel opening", (anchor + length, yy, z + zz), (.03, rib_length, rib_width), None)
            bpy.context.view_layer.objects.active = face
            cutter = face.modifiers.new("Pressed channel opening", "BOOLEAN"); cutter.operation = "DIFFERENCE"; cutter.object = cut_tool
            apply_construction_modifier(bpy, face, cutter); bpy.data.objects.remove(cut_tool, do_unlink=True)
            trough = cube(bpy, "spring | pressed channel back skin", (depth / 2 - skin_thickness / 2 - rib_depth, yy, zz),
                          (skin_thickness, rib_length, rib_width), brushed)
            trough.parent = plate; trough.pass_index = 1; moving_parts.append((trough, 2700.0, "pressedaluminiumchannelback"))
            for side in [-1, 1]:
                wall = cube(bpy, "spring | pressed channel return wall", (depth / 2 - rib_depth / 2, yy,
                            zz + side * (rib_width / 2 - skin_thickness / 2)),
                            (rib_depth, rib_length, skin_thickness), brushed)
                wall.parent = plate; wall.pass_index = 1; moving_parts.append((wall, 2700.0, "pressedaluminiumchannelwall"))
    # Nested tubes cover the long coil while retracting toward the anchor. The
    # fixed outer tube is part of semantic spring A and disappears with A.
    outer_mat = material(bpy, "Clear polycarbonate fixed coil guide", (.97, .98, .99), .06)
    outer_bs = outer_mat.node_tree.nodes.get("Principled BSDF")
    outer_bs.inputs["Transmission Weight"].default_value = 1.0; outer_bs.inputs["IOR"].default_value = 1.586
    outer = hollow_tube(bpy, "spring | anchored clear PC outer telescope", .01375, .01335, .090, outer_mat,
                        location=(anchor + .030, 0, z)); outer.pass_index = 1
    mount = hollow_tube(bpy, "spring | anchored aluminium core mounting collar", .0165, .01375, .003, brushed,
                        location=(anchor - .0015, 0, z)); mount.pass_index = 1
    core_mat = material(bpy, "Clear PETG moving spring core", (.97, .98, .99), .06)
    core_bs = core_mat.node_tree.nodes.get("Principled BSDF")
    core_bs.inputs["Transmission Weight"].default_value = 1.0; core_bs.inputs["IOR"].default_value = 1.57
    inner_length = .154
    inner = hollow_tube(bpy, "spring | 0.2mm wall PETG moving inner telescope", .01325, .01305, inner_length, core_mat,
                        location=(wire / 2 - inner_length / 2, 0, 0)); inner.parent = plate; inner.pass_index = 1
    moving_parts.append((inner, 1270.0, "PETG0.2mminnertelescope"))
    seat = cylinder(bpy, "spring | aluminium axial coil-seat disk", (wire / 2 + .0001, 0, 0), .017, .0002,
                    brushed, "X", vertices=96)
    seat.parent = plate; seat.pass_index = 1; moving_parts.append((seat, 2700.0, "aluminiumcoilseat"))
    backer = cylinder(bpy, "spring | disk backer touching pusher contact skin", (depth / 2 - skin_thickness - .0001, 0, 0),
                      .017, .0002, brushed, "X", vertices=96)
    backer.parent = plate; backer.pass_index = 1; moving_parts.append((backer, 2700.0, "aluminiumcontactskinbacker"))
    coupling_length = depth / 2 - skin_thickness - .0002 - (wire / 2 + .0002)
    coupling = cylinder(bpy, "spring | short seat-to-skin coupling spindle", (wire / 2 + .0002 + coupling_length / 2, 0, 0),
                        .003, coupling_length, brushed, "X", vertices=48)
    coupling.parent = plate; coupling.pass_index = 1; moving_parts.append((coupling, 2700.0, "aluminiumseatcoupling"))
    # Four small hidden-side seat screws are real geometry, behind the car's
    # contact face, so they cannot visually penetrate the bumper at impact.
    for yy, zz in [(-.009, -.009), (-.009, .009), (.009, -.009), (.009, .009)]:
        screw = cylinder(bpy, "spring | miniature coil-seat fastener", (wire / 2 + .00065, yy, zz), .0011, .0012,
                         dark, "X", vertices=6)
        screw.parent = plate; screw.pass_index = 1; moving_parts.append((screw, 7850.0, "steelseatfastener"))
    bpy.context.view_layer.update()
    mass_rows = []
    for obj, density, role in moving_parts:
        volume = actual_mesh_volume(bpy, obj)
        mass_rows.append({"object": obj.name, "role": role, "is_moving": True, "actual_closed_mesh_volume_m3": volume,
                          "density_kg_m3": density, "mass_kg": volume * density})
    measured_mass = sum(row["mass_kg"] for row in mass_rows)
    target_mass = float(config.get("moving_assembly_mass", .012))
    bond_mass = target_mass - measured_mass
    if not 0 <= bond_mass <= .0015:
        raise RuntimeError("Lightweight pusher geometry does not fit the12g moving mass budget")
    # A visible thin adhesive fillet joins the polymer core to the metal seat.
    # Its feasible sub-3mm axial size closes a material design budget, rather
    # than hiding a point mass in an unrealistically solid slab.
    adhesive_density = 1100.0
    # Use the polygonal tube's actual area so even the small fillet volume is
    # audited with the same closed-mesh method as the principal parts.
    adhesive_area = math.sin(2 * math.pi / 64) * 64 / 2 * (.0140 ** 2 - .01325 ** 2)
    adhesive_length = bond_mass / (adhesive_density * adhesive_area)
    if not .0003 <= adhesive_length <= .003:
        raise RuntimeError("Bonding fillet falls outside the physically declared0.3–3mm assembly allowance")
    adhesive = hollow_tube(bpy, "spring | actual polymer-to-seat adhesive fillet", .0140, .01325, adhesive_length,
                           material(bpy, "Clear amber structural adhesive", (.26, .16, .069), .35),
                           location=(wire / 2 - adhesive_length / 2, 0, 0))
    adhesive.parent = plate; adhesive.pass_index = 1
    bpy.context.view_layer.update(); adhesive_volume = actual_mesh_volume(bpy, adhesive)
    mass_rows.append({"object": adhesive.name, "role": "structuraladhesivefillet", "is_moving": True, "actual_closed_mesh_volume_m3": adhesive_volume,
                      "density_kg_m3": adhesive_density, "mass_kg": adhesive_volume * adhesive_density})
    final_mass = sum(row["mass_kg"] for row in mass_rows)
    assembly_mass_audit = {"schema_version": 1, "method": "Actual evaluated closed-mesh volume × declared engineering material density",
        "moving_parts": mass_rows, "represented_geometry_mass_kg": measured_mass,
        "spring_assembly_static_parts": [{"object": obj.name, "role": role, "is_moving": False,
                 "removed_with_spring_A": True, "actual_closed_mesh_volume_m3": actual_mesh_volume(bpy, obj),
                 "density_kg_m3": density, "mass_kg": actual_mesh_volume(bpy, obj) * density,
                 "solver_role": "static spring guide enforces reduced axial-mode interpretation; fixed mass contributes no kinetic energy"}
                 for obj, role, density in [(outer, "clearPCfixedoutertelescope", 1200.0),
                                             (mount, "aluminiumtelescopeanchorcollar", 2700.0)]],
        "target_total_moving_assembly_mass_kg": target_mass, "residual_bonding_film_mass_kg": bond_mass,
        "total_moving_assembly_mass_kg": final_mass,
        "moving_mass_difference_kg": final_mass - target_mass,
        "bond_mass_note": "Actual annular fillet geometry connects PETG tube and metal spring seat; design length bounded0.3–3mm, no hidden ballast",
        "bond_geometry_length_m": adhesive_length,
        "contact_skin_structure": {"front_skin_m": skin_thickness, "C_return_thickness_m": flange_thickness,
                                  "pressed_channels_z_local_m": [-.015, 0, .015], "pressed_depth_m": rib_depth,
                                  "pressed_width_m": rib_width, "central_backer_diameter_m": .034,
                                  "unsupported_skin_height_approx_m": .0138,
                                  "rigid_approximation": "Disk backs central contact skin; C returns and pressed channels support remaining spans. The car begins at rest under spring preload and releases the holding constraint; case-specific native contact loads are recorded in physics telemetry. Rigid structural approximation has no plate-FEM or physical calibration."},
        "density_basis": "Engineering assumptions, not supplier-certified material or measured weights",
        "contact_proxy": "Solver's6mm bounding contact box encloses the thin front skin/returns; actual car-contact face remains x=+3mm",
        "telescope": {"fixed_outer_diameter_m": .0275, "fixed_inner_diameter_m": .0267, "fixed_length_m": .090,
                      "fixed_x_range_m": [anchor - .015, anchor + .075], "fixed_exposed_length_m": .075,
                      "moving_outer_diameter_m": .0265, "moving_inner_diameter_m": .0261, "moving_length_m": inner_length,
                      "moving_right_x_offset_from_pusher_m": wire / 2,
                      "initial_overlap_m": (anchor + .075) - (anchor + length + wire / 2 - inner_length),
                      "radial_telescope_clearance_m": .0001, "anchor_through_bore_radius_m": .0145,
                      "pusher_rear_envelope_x_local_m": -depth / 2,
                      "clearance_at_declared130mm_stroke_m": length - .130 - depth / 2 - .075,
                      "fixed_sleeve_removed_with_A": True,
                      "motion": "Moving inner tube ends at pusher centre and retracts through anchor bore, never enters car",
                      "coil_inside_radius_clearance_m": (diameter - wire) / 2 - .01375,
                      "coil_lateral_mode_limit": "Thin near-fitting telescopic core limits lateral buckling; rendered axial mode does not solve residual radial wire strain"}}
    v = coil_vertices(length, anchor, z, diameter, wire, turns, ends)
    ring_count = len(v) // 12
    faces = [(i * 12 + j, i * 12 + (j + 1) % 12, (i + 1) * 12 + (j + 1) % 12, (i + 1) * 12 + j)
             for i in range(ring_count - 1) for j in range(12)]
    faces += [tuple(reversed(range(12))), tuple(range((ring_count - 1) * 12, ring_count * 12))]
    mesh = bpy.data.meshes.new("spring | solver-length helix mesh"); mesh.from_pydata(v, [], faces); mesh.update()
    obj = bpy.data.objects.new("spring | steel coil physical axial state", mesh); bpy.context.scene.collection.objects.link(obj)
    mesh.materials.append(steel); obj.pass_index = 1
    for p in mesh.polygons: p.use_smooth = len(p.vertices) == 4
    return {"coil": obj, "plate": plate, "configuration": {"anchor_x": anchor, "free_length": length,
            "axis_height": z, "mean_diameter": diameter, "wire_diameter": wire,
            "active_coils": turns, "end_coils": ends},
            "metadata": {"present": True, "free_length_m": length, "mean_diameter_m": diameter,
            "wire_diameter_m": wire, "active_turns": turns, "closed_end_turns": ends,
            "wire_surface": "constant diameter real tubular helix; active axial pitch follows physics cache only",
            "guide_rod_y_m": [-guide_y, guide_y], "guide_rod_z_m": guide_z, "guide_rod_radius_m": .002,
            "return_stop_nut_contact_x_m": anchor + length + .003,
            "moving_assembly_mass_audit": assembly_mass_audit,
            "plate_dimensions_m": list(plate_dimensions), "removed_in_delete_spring": ["active coil", "thin C-section pusher with POM bushes and seat",
                "moving PETG telescope", "fixed clear PC core telescope and mount"],
            "static_fixture_semantic": "support id4 retained for delete spring"}}





def mount_tag(obj, role, mount_target, note=''):
    obj['look_role'] = role
    obj['look_mount_target'] = mount_target.name if hasattr(mount_target, 'name') else str(mount_target)
    if note: obj['look_mount_note'] = note
    obj.pass_index = 4
    return obj


def boolean_bore(bpy, target, centre, radius, depth, axis='Z', vertices=48):
    cutter = cylinder(bpy, 'Temporary real drilled bore', centre, radius, depth, None, axis, vertices=vertices)
    bpy.context.view_layer.objects.active = target
    modifier = target.modifiers.new('Actual through-drilled aperture', 'BOOLEAN')
    modifier.operation = 'DIFFERENCE'; modifier.solver = 'EXACT'; modifier.object = cutter
    apply_construction_modifier(bpy, target, modifier)
    bpy.data.objects.remove(cutter, do_unlink=True)


def machined_metal(bpy, name, base=(.38, .40, .42), roughness=(.31, .55), direction=(10000, 24, 2400)):
    """Directional abrasive lines at metric scale, not large random metal blobs."""
    mat = material(bpy, name, base, sum(roughness)/2, .93)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links; bs = nodes.get('Principled BSDF')
    co = nodes.new('ShaderNodeTexCoord')
    stretch = nodes.new('ShaderNodeVectorMath'); stretch.operation = 'MULTIPLY'
    stretch.inputs[1].default_value = direction; links.new(co.outputs['Object'], stretch.inputs[0])
    abrasives = nodes.new('ShaderNodeTexNoise'); abrasives.inputs['Scale'].default_value = 1
    abrasives.inputs['Detail'].default_value = 1.4; abrasives.inputs['Roughness'].default_value = .58
    links.new(stretch.outputs['Vector'], abrasives.inputs['Vector'])
    remap = nodes.new('ShaderNodeMapRange'); remap.inputs['To Min'].default_value = roughness[0]
    remap.inputs['To Max'].default_value = roughness[1]
    links.new(abrasives.outputs['Fac'], remap.inputs['Value']); links.new(remap.outputs['Result'], bs.inputs['Roughness'])
    bump = nodes.new('ShaderNodeBump'); bump.inputs['Distance'].default_value = .0000035
    bump.inputs['Strength'].default_value = .19
    links.new(abrasives.outputs['Fac'], bump.inputs['Height']); links.new(bump.outputs['Normal'], bs.inputs['Normal'])
    if 'Anisotropic IOR Level' in bs.inputs: bs.inputs['Anisotropic IOR Level'].default_value = .34
    return mat


def socket_cap(bpy, name, axis, support_face, shank_radius, head_radius, head_height, shank_length, mat, target):
    """Closed head with a real recessed hex drive; shank reaches the support."""
    axisv = np.array({'X': (1.,0.,0.), 'Y': (0.,1.,0.), 'Z': (0.,0.,1.)}[axis])
    contact = np.array(support_face, float)
    head = cylinder(bpy, name + ' | socket-cap head', contact + axisv*head_height/2,
                    head_radius, head_height, mat, axis, vertices=48, bevel=.00012)
    # The socket remains blind: its floor is 40 percent of the head height.
    socket_depth = head_height*.60
    boolean_bore(bpy, head, contact + axisv*(head_height-socket_depth/2+.00004),
                 head_radius*.47, socket_depth+.00008, axis, vertices=6)
    mount_tag(head, 'static_fastener', target, 'Head underside bears on its washer or machined support face; real blind hex socket')
    shank = cylinder(bpy, name + ' | threaded embedded shank', contact-axisv*shank_length/2,
                     shank_radius, shank_length, mat, axis, vertices=32)
    mount_tag(shank, 'static_fastener', head, 'Shank is continuous with cap and extends into the receiving support')
    return head


def washer(bpy, name, centre, outer, inner, thickness, mat, target, axis='Z'):
    obj = hollow_tube(bpy, name, outer, inner, thickness, mat, location=centre, segments=48)
    if axis == 'Z': obj.rotation_euler.y = -math.pi/2
    elif axis == 'Y': obj.rotation_euler.z = math.pi/2
    return mount_tag(obj, 'static_fastener', target, 'Real annular washer bore, underside seated on named support')


def build_spring(bpy, config, present=True):
    # All moving surfaces come from _build_physical_spring (unchanged geometry and mass audit).
    result = _build_physical_spring(bpy, config, present)
    anchor = float(config.get('anchor_x', -.66)); length = float(config.get('free_length', .22))
    gy = float(config.get('guide_y', .079)); gz = float(config.get('guide_z', .019))
    back = bpy.data.objects['Static fixture | bolted spring backstop']
    foot = bpy.data.objects['Static fixture | aluminium mounting foot']
    aluminium = machined_metal(bpy, 'fabricated aluminium | fine longitudinal brushed tool marks')
    steel = machined_metal(bpy, 'zinc-plated fasteners | satin machined metal', (.29,.31,.32), (.24,.42), (8000,100,6000))
    dark = machined_metal(bpy, 'black-oxide socket screws | rubbed crests', (.038,.042,.046), (.31,.49))
    for obj in list(bpy.data.objects):
        if obj.type == 'MESH' and obj.data.materials:
            for i, mat in enumerate(obj.data.materials):
                if mat and mat.name.startswith('Spring fixture | brushed aluminium'):
                    obj.data.materials[i] = aluminium
        if obj.name.startswith('Static fixture | recessed hex bolt'):
            # Two older cap shapes sat hidden inside the backstop volume.
            bpy.data.objects.remove(obj, do_unlink=True)
    mount_tag(back, 'static_mount', foot, 'Original backstop mesh/contact envelope retained; added guide collars seat on its front face')
    mount_tag(foot, 'static_mount', 'Environment | solid timber bench with contact plane z=0', 'Mounting foot bottom is exactly z=0')
    # Four accessible M4 bolts clamp the actual exposed ledges, not the solid
    # vertical block. Their washers and holes have physical dimensions.
    for index, (xx, yy) in enumerate([(anchor-.038,-.079),(anchor-.038,.079),
                                       (anchor+.0065,-.094),(anchor+.0065,.094)]):
        boolean_bore(bpy, foot, (xx,yy,.0015), .0022, .012)
        ring = washer(bpy, f'backstop mount M4 {index+1} washer', (xx,yy,.00335), .0043, .0022, .0007, steel, foot)
        socket_cap(bpy, f'backstop mount M4 {index+1}', 'Z', (xx,yy,.0037), .002, .0034, .0036, .017, dark, ring)
    # Static rod clamp bosses are attached to the real front of the backstop.
    for index, yy in enumerate([-gy,gy]):
        boss = hollow_tube(bpy, f'guide root {index+1} reamed collar', .005, .00205, .004, aluminium,
                           location=(anchor+.002,yy,gz))
        mount_tag(boss, 'static_mount', back, 'Rear annulus is flush with backstop front x=anchor; rod fits actual reamed bore')
        socket_cap(bpy, f'guide root {index+1} clamp screw', 'Z', (anchor+.002,yy,gz+.0045),
                   .0009,.0016,.0015,.0045,dark,boss)
        # A low profile end support carries each guide. All added geometry is
        # ahead of the returned pusher envelope or below it, and outside car Y.
        post_x = anchor+length+.0115
        post = cube(bpy, f'guide free end {index+1} support block', (post_x,yy,.014), (.010,.012,.028), aluminium,.00045)
        boolean_bore(bpy,post,(post_x,yy,gz),.0023,.018,'X')
        pad = cube(bpy, f'guide free end {index+1} mounting pad', (post_x+.0035,yy,.001),(.026,.022,.002),aluminium,.00025)
        mount_tag(pad,'static_mount','Environment | solid timber bench with contact plane z=0','Pad bottom z=0; outside native car lateral envelope')
        mount_tag(post,'static_mount',pad,'Support block intersects its mounting pad; rod tip enters a real clearance bore')
        socket_cap(bpy, f'guide free end {index+1} rod clamp', 'Z',(post_x,yy,.0275),.0009,.0016,.0015,.0085,dark,post)
        mount_x = post_x+.0105
        boolean_bore(bpy,pad,(mount_x,yy,.001),.0017,.008)
        ring=washer(bpy,f'guide free end {index+1} M3 washer',(mount_x,yy,.00225),.0030,.00165,.0005,steel,pad)
        socket_cap(bpy,f'guide free end {index+1} M3 mount','Z',(mount_x,yy,.0025),.0015,.0026,.0027,.012,dark,ring)
    result['metadata']['static_fabrication_details'] = 'Four through-bored mounting bolts/annular washers, reamed guide collars with socket screws, two supported guide ends, directional machined aluminium finish'
    result['metadata']['moving_geometry_unchanged']=True
    result['metadata']['moving_finish_change_only']='Directional abrasive micro-normal/roughness finish, no displacement or added moving mass'
    return result



def build_obstacle_block(bpy, asset_dir, dimensions):
    result=build_block(bpy,asset_dir,dimensions)
    obj=result['root'];obj.name='obstacle_block | additional wooden obstacle'
    obj.pass_index=5;obj['pcve_object_id']='obstacle_block'
    obj['pcve_part']='obstacle_block';obj['semantic_instance_id']=5
    for uv in obj.data.uv_layers.active.data:uv.uv=(uv.uv.x+.213,uv.uv.y+.157)
    result['metadata'].update(present=True,object_id='obstacle_block',semantic_instance_id=5,
       texture_sampling='Distinct physical wood-scan patch for genuinely added piece; original block untouched')
    result['metadata'].pop('hidden_ballast',None)
    return result
