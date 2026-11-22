"""Sunlit domestic stairwell with housed oak stair joinery and a lightly handled PVC play ball.

architecture(), build_ball() and lighting() build the look in layers: the real-scale stairwell, the
domestic finish, the enclosed room with photographic daylight, the sunlit stairwell with housed joinery
and ordinary furnishings, and finally the photographic finish pass below. Helpers suffixed with a layer
name (architecture_sunlit, lighting_daylit_room, ...) are the earlier layers the final functions build on.
Contact surfaces (oak caps, 2.5 mm noses, Z=0 floor) match the collision meshes; painted stair bodies are
recessed behind the noses, and furnishings stay outside the solved ball corridor (|Y| <= 0.07 m).

Final photographic pass:
- camera white balance taken on the painted wall (white paint reads white) and a matching exposure;
- scanned painted-plaster relief and roughness (Poly Haven beige_wall_001, CC0, 3 m x 3 m) on the walls
  and the painted stair, keeping the calibrated paint reflectance;
- a satin clear-lacquered oak floor showing soft reflections of the window, radiator and sun patch;
- a painted skirting board along the open side of the stair;
- head and cross members of the window, sash and door joinery sit 0.6 mm proud of the uprights, so no
  coplanar overlaps render as black squares on CPU.
Every added solid stays at Y <= -0.45 m or within 1 mm of existing joinery, outside the ball corridor and
below the camera's sightline to the ball.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

import bpy
from mathutils import Vector
from scene_config import collider_mesh, colliders


def linear(c):
    return c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4


def material(name, rgb, roughness=.5):
    mat=bpy.data.materials.new(name);mat.use_nodes=True
    bs=mat.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value=tuple(linear(c) for c in rgb[:3])+(1,)
    bs.inputs["Roughness"].default_value=roughness
    return mat


def box(name, location, dimensions, mat, bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    o=bpy.context.object;o.name=name;o.dimensions=dimensions
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if mat:o.data.materials.append(mat)
    if bevel:
        mod=o.modifiers.new("Small construction edge radii","BEVEL");mod.width=bevel;mod.segments=3
        mod=o.modifiers.new("Weighted surface normals","WEIGHTED_NORMAL")
    return o


def mesh_object(name, verts, faces, mat):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def look_at(obj, point):
    obj.rotation_euler=(Vector(point)-obj.location).to_track_quat("-Z","Y").to_euler()


def oak_uv(obj,seed,repeat=1.83, floor=False):
    rng=random.Random(seed);ox,oy=rng.uniform(0,3),rng.uniform(0,3)
    uv=obj.data.uv_layers.new(name="Measured wood grain, unique board crop")
    for poly in obj.data.polygons:
        for idx in poly.loop_indices:
            v=obj.matrix_world @ obj.data.vertices[obj.data.loops[idx].vertex_index].co
            # Image V follows the actual long grain: Y across treads, X along floor boards.
            if floor: u,vv=v.y,v.x
            elif abs(poly.normal.y)>.8:u,vv=v.x,v.z
            elif abs(poly.normal.z)>.8:u,vv=v.x,v.y
            else:u,vv=v.z,v.y
            uv.data[idx].uv=(u/repeat+ox,vv/repeat+oy)


def paint_material(name,rgb):
    mat=material(name,rgb,.78);n,l=mat.node_tree.nodes,mat.node_tree.links
    noise=n.new("ShaderNodeTexNoise");noise.inputs["Scale"].default_value=650;noise.inputs["Detail"].default_value=2
    tc=n.new("ShaderNodeTexCoord");l.new(tc.outputs["Object"],noise.inputs["Vector"])
    bump=n.new("ShaderNodeBump");bump.inputs["Strength"].default_value=.14;bump.inputs["Distance"].default_value=.00007
    l.new(noise.outputs["Fac"],bump.inputs["Height"]);l.new(bump.outputs["Normal"],n.get("Principled BSDF").inputs["Normal"])
    return mat


def ball_material(cfg):
    ap=cfg["appearance"]["ball"]
    mat=material("Red yellow blue PVC gores with faint mould seam",(.9,.1,.05),ap["roughness"])
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get("Principled BSDF")
    tc=n.new("ShaderNodeTexCoord");sep=n.new("ShaderNodeSeparateXYZ");l.new(tc.outputs["UV"],sep.inputs["Vector"])
    times=n.new("ShaderNodeMath");times.operation="MULTIPLY";times.inputs[1].default_value=6;l.new(sep.outputs["X"],times.inputs[0])
    fract=n.new("ShaderNodeMath");fract.operation="FLOOR";l.new(times.outputs[0],fract.inputs[0])
    mod=n.new("ShaderNodeMath");mod.operation="MODULO";mod.inputs[1].default_value=3;l.new(fract.outputs[0],mod.inputs[0])
    scale=n.new("ShaderNodeMath");scale.operation="DIVIDE";scale.inputs[1].default_value=2;l.new(mod.outputs[0],scale.inputs[0])
    ramp=n.new("ShaderNodeValToRGB");ramp.color_ramp.interpolation="CONSTANT"
    ramp.color_ramp.elements.remove(ramp.color_ramp.elements[1])
    for index,key in enumerate(["red_srgb","yellow_srgb","blue_srgb"]):
        e=ramp.color_ramp.elements[0] if index==0 else ramp.color_ramp.elements.new(index*.5)
        e.color=tuple(linear(c) for c in ap[key])+(1,)
    l.new(scale.outputs[0],ramp.inputs[0]);l.new(ramp.outputs["Color"],bs.inputs["Base Color"])
    noise=n.new("ShaderNodeTexNoise");noise.inputs["Scale"].default_value=155;noise.inputs["Detail"].default_value=3
    l.new(tc.outputs["Generated"],noise.inputs["Vector"])
    rough=n.new("ShaderNodeMapRange");rough.inputs["To Min"].default_value=.25;rough.inputs["To Max"].default_value=.36
    l.new(noise.outputs["Fac"],rough.inputs["Value"]);l.new(rough.outputs["Result"],bs.inputs["Roughness"])
    bump=n.new("ShaderNodeBump");bump.inputs["Strength"].default_value=.13;bump.inputs["Distance"].default_value=.000035
    l.new(noise.outputs["Fac"],bump.inputs["Height"])
    # A shallow, visually subtle equatorial manufacturing seam; no collider ridge.
    sub=n.new("ShaderNodeMath");sub.operation="SUBTRACT";sub.inputs[1].default_value=.5;l.new(sep.outputs["Y"],sub.inputs[0])
    absolute=n.new("ShaderNodeMath");absolute.operation="ABSOLUTE";l.new(sub.outputs[0],absolute.inputs[0])
    mask=n.new("ShaderNodeMath");mask.operation="LESS_THAN";mask.inputs[1].default_value=.0008;l.new(absolute.outputs[0],mask.inputs[0])
    seam=n.new("ShaderNodeBump");seam.invert=True;seam.inputs["Strength"].default_value=.20;seam.inputs["Distance"].default_value=.000075
    l.new(mask.outputs[0],seam.inputs["Height"]);l.new(bump.outputs["Normal"],seam.inputs["Normal"]);l.new(seam.outputs["Normal"],bs.inputs["Normal"])
    bs.inputs["Coat Weight"].default_value=ap["coat_weight"];bs.inputs["Coat Roughness"].default_value=.27
    bs.inputs["IOR"].default_value=1.48
    return mat


def build_ball_original(cfg):
    r=cfg["physics"]["ball"]["radius_m"]
    bpy.ops.mesh.primitive_uv_sphere_add(segments=96,ring_count=64,radius=r,location=(0,0,0))
    ball=bpy.context.object;ball.name="B01 free hollow PVC toy ball"
    ball.data.materials.append(ball_material(cfg))
    for face in ball.data.polygons:face.use_smooth=True
    ball.rotation_mode="QUATERNION"
    # Faint local scuff strokes rotate with the ball. Their relief is under 20 micrometres.
    scuff=material("Very faint PVC handling marks",(.77,.77,.72),.48)
    rng=random.Random(cfg["appearance"]["seed"])
    for i in range(13):
        a=rng.uniform(0,2*math.pi);b=rng.uniform(.4,2.7);length=rng.uniform(.004,.013)
        curve=bpy.data.curves.new("Hairline surface wear","CURVE");curve.dimensions="3D";curve.bevel_depth=.000013;curve.bevel_resolution=1
        poly=curve.splines.new("POLY");poly.points.add(5)
        for j,v in enumerate(poly.points):
            angle=a+(j/5-.5)*length/r
            v.co=((r+.000012)*math.sin(b)*math.cos(angle),(r+.000012)*math.sin(b)*math.sin(angle),(r+.000012)*math.cos(b),1)
        obj=bpy.data.objects.new(f"Faint rotating scuff {i:02d}",curve);bpy.context.collection.objects.link(obj);obj.parent=ball;obj.data.materials.append(scuff)
    return ball


def wood_material(asset_root, cfg, floor=False):
    ap = cfg["appearance"]["wood"]
    if ap["asset"] != "wood_floor":
        raise ValueError("The oak finish requires the documented wood_floor CC0 asset")
    root = Path(asset_root) / "polyhaven/wood_floor"
    files = {k: root / f"wood_floor_{suffix}_4k.jpg" for k, suffix in
             [("color", "diff"), ("roughness", "rough"), ("normal", "nor_gl")]}
    if not all(p.is_file() for p in files.values()):
        raise FileNotFoundError(files)
    mat = material("Measured satin oak " + ("landing" if floor else "tread"), (.56, .40, .26), ap["roughness"])
    n, l = mat.node_tree.nodes, mat.node_tree.links
    bs = n.get("Principled BSDF")
    uv = n.new("ShaderNodeTexCoord")
    for role, path in files.items():
        tex = n.new("ShaderNodeTexImage")
        tex.name = role + " original photographic oak / 1.7m"
        tex.image = bpy.data.images.load(str(path), check_existing=True)
        l.new(uv.outputs["UV"], tex.inputs["Vector"])
        if role == "color":
            hue = n.new("ShaderNodeHueSaturation")
            hue.inputs["Saturation"].default_value = .88
            hue.inputs["Value"].default_value = .96
            l.new(tex.outputs["Color"], hue.inputs["Color"])
            # Small finish/timber variation per physical board/tread, not random per frame.
            oi = n.new("ShaderNodeObjectInfo")
            variation = n.new("ShaderNodeMapRange")
            variation.inputs["To Min"].default_value = .95
            variation.inputs["To Max"].default_value = 1.025
            l.new(oi.outputs["Random"], variation.inputs["Value"])
            tint = n.new("ShaderNodeMixRGB")
            tint.blend_type = "MULTIPLY"
            tint.inputs[0].default_value = 1
            l.new(hue.outputs["Color"], tint.inputs[1])
            l.new(variation.outputs["Result"], tint.inputs[2])
            l.new(tint.outputs[0], bs.inputs["Base Color"])
        elif role == "roughness":
            tex.image.colorspace_settings.name = "Non-Color"
            remap = n.new("ShaderNodeMapRange")
            remap.inputs["To Min"].default_value = ap["roughness"] - (.045 if floor else .075)
            remap.inputs["To Max"].default_value = ap["roughness"] + (.13 if floor else .09)
            l.new(tex.outputs["Color"], remap.inputs["Value"])
            l.new(remap.outputs["Result"], bs.inputs["Roughness"])
        else:
            tex.image.colorspace_settings.name = "Non-Color"
            normal = n.new("ShaderNodeNormalMap")
            normal.inputs["Strength"].default_value = .16 if floor else .12
            l.new(tex.outputs["Color"], normal.inputs["Color"])
            l.new(normal.outputs["Normal"], bs.inputs["Normal"])
    bs.inputs["Coat Weight"].default_value = .045
    bs.inputs["Coat Roughness"].default_value = .42
    return mat, files


def painted_joinery(name, rgb, roughness=.53):
    mat = paint_material(name, rgb)
    bs = mat.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Roughness"].default_value = roughness
    bs.inputs["Coat Weight"].default_value = .035
    bs.inputs["Coat Roughness"].default_value = .48
    return mat


def cylinder(name, location, radius, depth, mat, axis="Z"):
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    if axis == "Y":
        obj.rotation_euler.x = math.pi / 2
    obj.data.materials.append(mat)
    bevel = obj.modifiers.new("Machined 0.6 mm hardware edges", "BEVEL")
    bevel.width = .0006
    bevel.segments = 3
    obj.modifiers.new("Hardware surface normals", "WEIGHTED_NORMAL")
    for p in obj.data.polygons:
        p.use_smooth = len(p.vertices) == 4
    return obj


def door_geometry(wall, trim):
    # The wall actually has a rough opening, and the leaf sits inside its depth.
    dark = material("Door reveal shadow / dark inner opening", (.16, .17, .16), .8)
    leaf = painted_joinery("Quiet warm grey painted door", (.66, .685, .66), .55)
    box("Door opening darkness behind closed leaf", (3.55, .635, 1.02), (.84, .025, 2.04), dark)
    box("Door leaf continuous backing", (3.55, .574, 1.008), (.78, .028, 2.0), leaf, .0015)
    # 105 mm stiles and three rails surround genuinely recessed, flat panels.
    for x in [3.2125, 3.8875]:
        box("Door structural stile", (x, .555, 1.008), (.105, .020, 2.0), leaf, .0015)
    for z0, z1 in [(.008, .17), (.96, 1.09), (1.85, 2.008)]:
        box("Door structural rail", (3.55, .555, (z0+z1)/2), (.57, .020, z1-z0), leaf, .0015)
    for z0, z1 in [(.17, .96), (1.09, 1.85)]:
        box("Recessed door panel", (3.55, .562, (z0+z1)/2), (.57, .010, z1-z0), leaf, .001)
        for x in [3.268, 3.832]:
            box("Panel moulding side", (x, .550, (z0+z1)/2), (.006, .006, z1-z0), leaf, .001)
        for z in [z0+.003, z1-.003]:
            box("Panel moulding rail", (3.55, .550, z), (.564, .006, .006), leaf, .001)
    for x in [3.142, 3.958]:
        box("Door jamb in actual opening", (x, .557, 1.025), (.028, .13, 2.05), trim, .001)
        box("Door casing with small arris", (x + (-.022 if x < 3.55 else .022), .479, 1.045), (.06, .038, 2.09), trim, .0015)
    box("Door head jamb", (3.55, .557, 2.025), (.84, .13, .028), trim, .001)
    box("Door casing head", (3.55, .479, 2.075), (.944, .038, .06), trim, .0015)
    metal = material("Brushed nickel functional door hardware", (.51, .525, .52), .32)
    metal.node_tree.nodes.get("Principled BSDF").inputs["Metallic"].default_value = .88
    cylinder("Lever handle circular rose", (3.823, .541, 1.0), .024, .007, metal, "Y")
    cylinder("Lever spindle", (3.823, .523, 1.0), .008, .032, metal, "Y")
    curve = bpy.data.curves.new("Bent lever profile", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 16
    curve.bevel_depth = .0075
    curve.bevel_resolution = 3
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(3)
    for point, co in zip(spline.bezier_points, [(3.823, .514, 1.0), (3.817, .499, 1.0), (3.795, .492, 1.0), (3.725, .492, 1.0)]):
        point.co = co
        point.handle_left_type = point.handle_right_type = "AUTO"
    obj = bpy.data.objects.new("Rounded nickel lever", curve)
    bpy.context.collection.objects.link(obj)
    curve.materials.append(metal)
    for z in [.26, 1.0, 1.77]:
        cylinder("Door hinge barrel", (3.164, .547, z), .0045, .065, metal)
    # Two millimetre plaster/trim reveals preserve a believable construction joint.
    return {"door_leaf_height_m": 2.0, "door_bottom_clearance_m": .008,
            "door_leaf_recess_from_wall_m": .045, "door_rough_opening_m": [.84, 2.06]}


def architecture_domestic(cfg, asset_root):
    mesh = mesh_object
    wood, files = wood_material(asset_root, cfg)
    floorwood, _ = wood_material(asset_root, cfg, floor=True)
    wall = paint_material("Warm neutral household emulsion", (.82, .815, .79))
    trim = painted_joinery("Soft white eggshell timber trim", (.875, .875, .845), .57)
    riser = painted_joinery("Painted timber risers and closed stringer", (.845, .842, .815), .60)
    geometry = colliders(cfg)
    repeat = cfg["appearance"]["wood"]["repeat_m"]
    for i, c in enumerate(geometry):
        if c["id"] == "lower_platform":
            v, f = collider_mesh(c, cfg["simulation_quality"]["edge_arc_segments"])
            obj = mesh("Continuous landing / measured oak planks", v, f, floorwood)
            oak_uv(obj, 1500, repeat, floor=True)
        else:
            # A 25 mm oak cap over a closed, painted riser. The union has the exact
            # contact silhouette of the step collider, including its 2.5 mm nose.
            body = dict(c, zmax=c["zmax"]-.025, radius=0)
            v, f = collider_mesh(body, cfg["simulation_quality"]["edge_arc_segments"])
            mesh(c["id"] + " closed painted timber body", v, f, riser)
            cap = dict(c, zmin=c["zmax"]-.025)
            v, f = collider_mesh(cap, cfg["simulation_quality"]["edge_arc_segments"])
            obj = mesh(c["id"] + " fixed oak contact surface", v, f, wood)
            oak_uv(obj, 1200+i, repeat, floor=c["id"] == "upper_platform")
    # One closed skirting profile avoids the gaps and dark ends of overlapping
    # trim cubes. Vertical returns are 18 mm wide, with a 76 mm tread upstand.
    upper = geometry[-2]
    bottom = [(upper["xmin"], upper["zmax"]), (0, upper["zmax"])]
    top = [(upper["xmin"], upper["zmax"]+.076), (.018, upper["zmax"]+.076)]
    for c in geometry[:5]:
        bottom.extend([(c["xmin"], c["zmax"]), (c["xmax"], c["zmax"])])
        top.extend([(c["xmin"]+.018, c["zmax"]+.076), (c["xmax"]+.018, c["zmax"]+.076)])
    end = geometry[4]["xmax"]+.018
    bottom.extend([(geometry[4]["xmax"], 0), (end, 0)])
    top.append((end, .082))
    profile = bottom + list(reversed(top))
    count = len(profile)
    verts = [(x, y, z) for y in [.452, .500] for x, z in profile]
    faces = [tuple(range(count)), tuple(reversed(range(count, 2*count)))]
    faces += [(j, j+count, (j+1)%count+count, (j+1)%count) for j in range(count)]
    skirting = mesh("Continuous joinery / closed stepped skirting", verts, faces, trim)
    bevel = skirting.modifiers.new("One millimetre painted arris", "BEVEL")
    bevel.width, bevel.segments = .001, 3
    skirting.modifiers.new("Continuous trim normals", "WEIGHTED_NORMAL")
    # Walls are split around both openings; door and window do not sit on a wall face.
    wx0, wx1 = cfg["appearance"]["window"]["opening_x_m"]
    wz0, wz1 = cfg["appearance"]["window"]["opening_z_m"]
    segments = [("Wall left of window", -3, wx0, -.15, 3.05),
                ("Window apron wall", wx0, wx1, -.15, wz0),
                ("Window lintel wall", wx0, wx1, wz1, 3.05),
                ("Wall between window and door", wx1, 3.13, -.15, 3.05),
                ("Door lintel wall", 3.13, 3.97, 2.06, 3.05),
                ("Door threshold foundation", 3.13, 3.97, -.15, 0),
                ("Wall beyond door", 3.97, 6, -.15, 3.05)]
    for name, x0, x1, z0, z1 in segments:
        box(name, ((x0+x1)/2, .56, (z0+z1)/2), (x1-x0, .12, z1-z0), wall, .0008)
    box("Indoor ceiling / real bounce surface", (1.5, -2.7, 3.08), (9, 6.6, .06), wall)
    box("Opposite room wall outside camera", (1.5, -6.0, 1.45), (9, .12, 3.2), wall)
    wxc, wzc = (wx0+wx1)/2, (wz0+wz1)/2
    for x in [wx0+.022, wx1-.022]:
        box("Painted window reveal jamb", (x, .553, wzc), (.044, .105, wz1-wz0), trim, .0015)
    for z in [wz0+.022, wz1-.022]:
        box("Window reveal head or stool", (wxc, .553, z), (wx1-wx0, .105, .044), trim, .0015)
    for x in [wx0-.022, wx1+.022]:
        box("Window flat architrave", (x, .484, wzc), (.048, .03, wz1-wz0+.10), trim, .0012)
    box("Window top architrave", (wxc, .484, wz1+.028), (wx1-wx0+.092, .03, .048), trim, .0012)
    box("Solid projecting window sill", (wxc, .493, wz0-.005), (wx1-wx0+.13, .23, .028), trim, .002)
    for x in [wx0+.054, wxc, wx1-.054]:
        box("Slim window sash vertical", (x, .603, wzc), (.025, .035, wz1-wz0-.075), trim, .0012)
    for z in [wz0+.054, wzc, wz1-.054]:
        box("Slim window sash horizontal", (wxc, .603, z), (wx1-wx0-.075, .035, .025), trim, .0012)
    glass = material("Lightly frosted stairwell window glass", (.965, .985, 1), .12)
    bs = glass.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Transmission Weight"].default_value = 1
    bs.inputs["IOR"].default_value = 1.46
    for x0, x1 in [(wx0+.067, wxc-.014), (wxc+.014, wx1-.067)]:
        for z0, z1 in [(wz0+.067, wzc-.014), (wzc+.014, wz1-.067)]:
            box("Actual glass pane / 2 mm", ((x0+x1)/2, .618, (z0+z1)/2), (x1-x0, .002, z1-z0), glass)
    # Quiet distant courtyard geometry, softened by real glass; no image backdrop.
    exterior = material("Distant courtyard plaster", (.78, .80, .75), .88)
    box("Courtyard wall beyond window", (2.4, 6.0, 1.05), (7, .18, 2.1), exterior, .003)
    coping = material("Courtyard coping", (.48, .51, .49), .85)
    box("Courtyard wall coping", (2.4, 6.0, 2.12), (7.08, .25, .06), coping, .006)
    for c in [geometry[-1]]:
        intervals = [(end, 3.09), (4.01, c["xmax"])]
        for x0, x1 in intervals:
            box("Landing timber skirting", ((x0+x1)/2, .477, c["zmax"]+.041), (x1-x0, .046, .082), trim, .0012)
            box("Skirting narrow top bead", ((x0+x1)/2, .470, c["zmax"]+.082), (x1-x0, .040, .005), trim, .0015)
    door_ledger = door_geometry(wall, trim)
    s = cfg["physics"]["stairs"]
    return {"stair_rise_m": s["rise_m"], "tread_m": s["tread_m"], "width_m": s["width_m"],
            "ball_diameter_m": 2*cfg["physics"]["ball"]["radius_m"], "door_height_m": 2.0,
            "oak_cap_thickness_m": .025, "collision_and_visible_nosing_radius_m": s["edge_radius_m"],
            "wood_repeat_m": repeat, "floor_surface_displacement_m": 0,
            "pbr_files": {k: str(v) for k, v in files.items()}, **door_ledger,
            "background_kind": "Shared 3D walls with actual door/window openings, glazing, ceiling, and distant courtyard wall; no photograph backdrop",
            "contact_geometry_policy": "Exact original collider outline; the painted body and oak cap partition the same solid. Texture normal mapping has no geometric displacement."}


def build_ball_domestic(cfg):
    ball = build_ball_original(cfg)
    mat = ball.data.materials[0]
    mat.name = "Used but clean PVC / soft highlights / mould seam"
    ap = cfg["appearance"]["ball"]
    for node in mat.node_tree.nodes:
        if node.bl_idname == "ShaderNodeMapRange":
            node.inputs["To Min"].default_value = ap["roughness"]-.045
            node.inputs["To Max"].default_value = ap["roughness"]+.055
    bs = mat.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Coat Roughness"].default_value = .39
    # A recessed valve is a material cue on the same spherical surface, not a ridge.
    valve = material("Faint grey-blue PVC inflation valve", (.20, .25, .28), .47)
    direction = Vector((.20, -.45, .87)).normalized()
    tangent = direction.cross(Vector((0, 0, 1))).normalized()
    bitangent = direction.cross(tangent).normalized()
    r = cfg["physics"]["ball"]["radius_m"]
    verts = [tuple(direction*(r+.000018))]
    for ring in range(1, 7):
        radius = .0027*ring/6
        for j in range(32):
            a = j/32*math.tau
            q = direction*math.sqrt(r*r-radius**2) + radius*(math.cos(a)*tangent+math.sin(a)*bitangent)
            verts.append(tuple(q*(1+.000018/r)))
    faces = [(0, j+1, (j+1)%32+1) for j in range(32)]
    for ring in range(5):
        for j in range(32):
            a, b = 1+ring*32+j, 1+ring*32+(j+1)%32
            faces.append((a, a+32, b+32, b))
    obj = mesh_object("Small PVC inflation valve rotating with ball", verts, faces, valve)
    obj.parent = ball
    return ball


PRESET_daylit_room = "home_oak_stairwell_daylit_room"


HDRI_ASSET_daylit_room = "suburban_field_01"


HDRI_ROTATION_DEG_daylit_room = 72.0


def remove(obj):
    bpy.data.objects.remove(obj, do_unlink=True)


def surface_reference():
    obj = bpy.data.objects.new("World metre coordinates for surface finishes", None)
    bpy.context.collection.objects.link(obj)
    obj.empty_display_size = .10
    return obj


def painted_surface(mat, reference, roughness):
    n, l = mat.node_tree.nodes, mat.node_tree.links
    bs = n.get("Principled BSDF")
    original = tuple(bs.inputs["Base Color"].default_value)
    coords = n.new("ShaderNodeTexCoord")
    coords.object = reference
    broad = n.new("ShaderNodeTexNoise")
    broad.inputs["Scale"].default_value = 1.25
    broad.inputs["Detail"].default_value = 2
    l.new(coords.outputs["Object"], broad.inputs["Vector"])
    color = n.new("ShaderNodeValToRGB")
    for e, scale in zip(color.color_ramp.elements, [.965, 1.025]):
        e.color = tuple(min(1.0, c*scale) for c in original[:3])+(1,)
    l.new(broad.outputs["Fac"], color.inputs["Fac"])
    l.new(color.outputs["Color"], bs.inputs["Base Color"])
    rough = n.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = roughness-.035
    rough.inputs["To Max"].default_value = roughness+.035
    l.new(broad.outputs["Fac"], rough.inputs["Value"])
    l.new(rough.outputs["Result"], bs.inputs["Roughness"])
    fine = n.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 1250
    fine.inputs["Detail"].default_value = 2
    l.new(coords.outputs["Object"], fine.inputs["Vector"])
    bump = n.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = .000055
    bump.inputs["Strength"].default_value = .18
    l.new(fine.outputs["Fac"], bump.inputs["Height"])
    l.new(bump.outputs["Normal"], bs.inputs["Normal"])


def architectural_glass():
    mat = material("Clear domestic glazing / thin direct-light transmittance", (.975, .985, 1.0), .022)
    n, l = mat.node_tree.nodes, mat.node_tree.links
    bs = n.get("Principled BSDF")
    bs.inputs["Transmission Weight"].default_value = 1.0
    bs.inputs["IOR"].default_value = 1.46
    # Thin architectural-window approximation: 96.5% transmission per shadow
    # surface, while camera/reflection rays retain Fresnel glass and refraction.
    # This avoids relying on unresolved refractive caustics for room daylight.
    transparent = n.new("ShaderNodeBsdfTransparent")
    transparent.inputs["Color"].default_value = (.965, .965, .965, 1)
    ray = n.new("ShaderNodeLightPath")
    mix = n.new("ShaderNodeMixShader")
    l.new(ray.outputs["Is Shadow Ray"], mix.inputs[0])
    l.new(bs.outputs[0], mix.inputs[1])
    l.new(transparent.outputs[0], mix.inputs[2])
    l.new(mix.outputs[0], n.get("Material Output").inputs["Surface"])
    return mat


def rail_material(reference):
    mat = material("Hand-rubbed solid oak handrail", (.56, .39, .235), .37)
    n, l = mat.node_tree.nodes, mat.node_tree.links
    tc = n.new("ShaderNodeTexCoord")
    tc.object = reference
    stretch = n.new("ShaderNodeVectorMath")
    stretch.operation = "MULTIPLY"
    stretch.inputs[1].default_value = (1.3, 95, 45)
    l.new(tc.outputs["Object"], stretch.inputs[0])
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 4.0
    noise.inputs["Detail"].default_value = 3.0
    l.new(stretch.outputs["Vector"], noise.inputs["Vector"])
    ramp = n.new("ShaderNodeValToRGB")
    for element, rgb in zip(ramp.color_ramp.elements, [(.40, .26, .145), (.61, .44, .28)]):
        element.color = tuple(linear(c) for c in rgb)+(1,)
    l.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    bs = n.get("Principled BSDF")
    l.new(ramp.outputs["Color"], bs.inputs["Base Color"])
    bs.inputs["Coat Weight"].default_value = .09
    bs.inputs["Coat Roughness"].default_value = .32
    return mat


def wall_handrail(reference):
    mat = rail_material(reference)
    curve = bpy.data.curves.new("Continuous safe-return handrail centreline", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 16
    curve.bevel_depth = .019
    curve.bevel_resolution = 5
    # Height is approximately 0.90 m above each tread centre. The rail is on
    # the wall side (Y=0.36), well above the entire solved ball corridor.
    points = [(-.38, .493, 1.90), (-.38, .36, 1.90), (-.20, .36, 1.90),
              (1.60, .36, .872), (1.75, .36, .872), (1.75, .493, .872)]
    rounded = [Vector(points[0])]
    for a, b, c in zip(points, points[1:], points[2:]):
        a, b, c = Vector(a), Vector(b), Vector(c)
        u, v = (b-a).normalized(), (c-b).normalized()
        run = min(.045, (b-a).length*.3, (c-b).length*.3)
        start, end = b-u*run, b+v*run
        for j in range(9):
            t = j/8
            rounded.append((1-t)**2*start+2*(1-t)*t*b+t*t*end)
    rounded.append(Vector(points[-1]))
    spline = curve.splines.new("POLY")
    spline.points.add(len(rounded)-1)
    for p, co in zip(spline.points, rounded):
        p.co = (*co, 1)
    obj = bpy.data.objects.new("Wall-side 38 mm oak handrail / clear of contacts", curve)
    bpy.context.collection.objects.link(obj)
    curve.materials.append(mat)
    metal = material("Satin stainless handrail brackets", (.46, .48, .47), .34)
    metal.node_tree.nodes.get("Principled BSDF").inputs["Metallic"].default_value = .86
    for x in [.10, .72, 1.31]:
        z = 1.90-(x+.20)*(.16/.28)
        cylinder("Handrail wall rose", (x, .490, z-.075), .019, .009, metal, "Y")
        box("Handrail bracket arm", (x, .425, z-.075), (.012, .12, .012), metal, .003)
        cylinder("Handrail saddle support", (x, .367, z-.045), .006, .060, metal)


def architecture_daylit_room(cfg, asset_root):
    ledger = architecture_domestic(cfg, asset_root)
    for obj in list(bpy.data.objects):
        if obj.name in ["Courtyard wall beyond window", "Courtyard wall coping", "Opposite room wall outside camera"]:
            remove(obj)
    reference = surface_reference()
    for name, roughness in [("Warm neutral household emulsion", .79),
                            ("Soft white eggshell timber trim", .46),
                            ("Painted timber risers and closed stringer", .53),
                            ("Quiet warm grey painted door", .47)]:
        painted_surface(bpy.data.materials[name], reference, roughness)
    for mat in bpy.data.materials:
        if mat.name.startswith("Measured satin oak"):
            for node in mat.node_tree.nodes:
                if node.bl_idname == "ShaderNodeNormalMap":
                    node.inputs["Strength"].default_value = .29
    glass = architectural_glass()
    for obj in bpy.data.objects:
        if obj.name.startswith("Actual glass pane"):
            obj.data.materials.clear()
            obj.data.materials.append(glass)
    gasket = material("Thin dark window glazing seals", (.22, .235, .225), .67)
    for obj in list(bpy.data.objects):
        if not obj.name.startswith("Actual glass pane"):
            continue
        x0, x1 = obj.location.x-obj.dimensions.x/2, obj.location.x+obj.dimensions.x/2
        z0, z1 = obj.location.z-obj.dimensions.z/2, obj.location.z+obj.dimensions.z/2
        for x in [x0, x1]:
            box("Window glazing gasket vertical", (x, .615, (z0+z1)/2), (.0022, .003, z1-z0), gasket, .0005)
        for z in [z0, z1]:
            box("Window glazing gasket horizontal", ((x0+x1)/2, .615, z), (x1-x0, .003, .0022), gasket, .0005)
    sash_hardware = material("Casement window handle / satin white", (.84, .85, .825), .34)
    cylinder("Window handle mounting rose", (2.746, .5815, 1.45), .011, .008, sash_hardware, "Y")
    cylinder("Window handle spindle", (2.746, .568, 1.45), .0045, .025, sash_hardware, "Y")
    box("Window casement locking lever", (2.746, .555, 1.423), (.012, .014, .061), sash_hardware, .0035)
    # The rendered floor ends at the inside wall. The broad solver floor extends
    # outside this wall, which is immaterial to the ball's Y=0 interaction band.
    floor = bpy.data.objects["Continuous landing / measured oak planks"]
    for vertex in floor.data.vertices:
        if vertex.co.y > .5:
            vertex.co.y = .5
    floor.data.update()
    while floor.data.uv_layers:
        floor.data.uv_layers.remove(floor.data.uv_layers[0])
    oak_uv(floor, 1500, cfg["appearance"]["wood"]["repeat_m"], floor=True)
    wood = floor.data.materials[0]
    extension = mesh_object("Room floor continuation behind camera", [(-3, -5.90, 0), (4.8, -5.90, 0),
                                (4.8, -3, 0), (-3, -3, 0)], [(0, 1, 2, 3)], wood)
    oak_uv(extension, 1500, cfg["appearance"]["wood"]["repeat_m"], floor=True)
    wall = bpy.data.materials["Warm neutral household emulsion"]
    trim = bpy.data.materials["Soft white eggshell timber trim"]
    # Real enclosure controls indirect light; the camera is inside the room.
    box("Left room return beyond upper landing", (-1.06, -2.68, 1.45), (.12, 6.44, 3.2), wall, .001)
    box("Right room return beyond landing", (4.86, -2.68, 1.45), (.12, 6.44, 3.2), wall, .001)
    # An actual second window behind the camera admits fill daylight. No studio
    # emitter is inserted into the photographed view of either window.
    front = [("Front wall left", -1.12, 1.0, -.15, 3.05),
             ("Front wall right", 3.4, 4.92, -.15, 3.05),
             ("Front window apron", 1.0, 3.4, -.15, 1.10),
             ("Front window lintel", 1.0, 3.4, 2.35, 3.05)]
    for name, x0, x1, z0, z1 in front:
        box(name, ((x0+x1)/2, -5.95, (z0+z1)/2), (x1-x0, .10, z1-z0), wall, .001)
    for x in [1.025, 2.2, 3.375]:
        box("Off-camera window vertical sash", (x, -5.945, 1.725), (.05, .12, 1.25), trim, .0015)
    for z in [1.125, 2.325]:
        box("Off-camera window horizontal sash", (2.2, -5.945, z), (2.4, .12, .05), trim, .0015)
    box("Off-camera window clear glazing", (2.2, -5.96, 1.725), (2.30, .002, 1.15), glass)
    wall_handrail(reference)
    switch = material("Ordinary satin white wall switch", (.84, .845, .82), .38)
    box("86 mm switch faceplate seated on wall", (2.98, .495, 1.14), (.086, .010, .086), switch, .002)
    box("Wall switch rocker", (2.98, .486, 1.14), (.036, .009, .058), switch, .0015)
    # architecture_sunlit() replaces this sky (scene property and ledger) before any light is built,
    # so the file is never read and need not exist.
    hdri = Path(asset_root)/"polyhaven"/HDRI_ASSET_daylit_room/(HDRI_ASSET_daylit_room+"_4k.hdr")
    bpy.context.scene["stair_daylight_hdri_file"] = str(hdri)
    ledger.update(appearance_revision=PRESET_daylit_room, room_ceiling_m=3.05, camera_inside_enclosure=True,
        handrail_diameter_m=.038, handrail_wall_side_y_m=.36, handrail_height_above_tread_centres_m=.90,
        render_floor_ymax_m=.5, solver_floor_ymax_m=3.0, interaction_corridor_y_m=[-.07, .07],
        visual_proxy_note="The floor is clipped only behind the room wall; every swept ball contact remains on the original Z=0 plane. Added enclosure and handrail do not touch the solved trajectory.",
        background_kind="Shared enclosed 3D room, actual window openings and glazing; photographic HDRI used only as distant exterior and incident light.",
        hdri_asset=HDRI_ASSET_daylit_room, hdri_file=str(hdri), hdri_rotation_deg=HDRI_ROTATION_DEG_daylit_room,
        glass_model="Camera/reflection Fresnel refraction; 0.965 direct shadow transmittance per surface; no visible emissive backdrop.")
    return ledger


def build_ball_daylit_room(cfg):
    ball = build_ball_domestic(cfg)
    mat = ball.data.materials[0]
    mat.name = "Soft PVC shell with broad natural window reflections"
    bs = mat.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Coat Roughness"].default_value = .43
    bs.inputs["IOR"].default_value = 1.46
    return ball


PRESET_sunlit = "home_oak_stairwell_sunlit"


HDRI_ASSET_sunlit = "sunny_rose_garden"


HDRI_FILE = "sunny_rose_garden_8k.hdr"


# Puts the photographed sun (49 deg elevation) behind the stairwell window,
# 60 deg azimuth, so the beam falls on the floor in front of the window.
HDRI_ROTATION_DEG_sunlit = -96.0


# Window-only daylight reaches the stair side of the room after several
# wall-to-wall interreflections; four diffuse bounces left it under-lit.
DIFFUSE_BOUNCES = 12


MAX_BOUNCES = 16


# Interior-weighted exposure, as a photographer would meter a sunlit room;
# AgX keeps the window and sun patch from hard clipping.
EXPOSURE_EV_sunlit = .6


VIEW_LOOK = "AgX - Medium High Contrast"


# White household emulsion and eggshell reflect ~80-85 %; the domestic-layer values
# (sRGB .82-.875, linear .64-.73) read as light grey and starve interreflection.
PAINT_SRGB = {"Warm neutral household emulsion": (.93, .925, .90),
              "Soft white eggshell timber trim": (.95, .95, .935),
              "Painted timber risers and closed stringer": (.93, .928, .91)}


NOSING_OVERHANG_M = .022


WALL_STRING_ABOVE_PITCH_M = .075


PROPS = {"potted_plant_04": "Small potted haworthia on window stool",
         "hanging_picture_frame_02": "Framed print above stair"}


def housed_stairs(cfg):
    """Recess painted risers behind each nose and house the tread tail under it."""
    geometry = colliders(cfg)
    chain = [c for c in geometry if c["id"] == "upper_platform"] + [c for c in geometry if c["id"].startswith("S")]
    segments = cfg["simulation_quality"]["edge_arc_segments"]
    riser = bpy.data.materials["Painted timber risers and closed stringer"]
    oak = bpy.data.materials["Measured satin oak tread"]
    r = NOSING_OVERHANG_M
    for k, c in enumerate(chain):
        bpy.data.objects.remove(bpy.data.objects[c["id"]+" closed painted timber body"], do_unlink=True)
        xmin = c["xmin"] if k == 0 else c["xmin"]-r
        body = dict(c, xmin=xmin, xmax=c["xmax"]-r, zmax=c["zmax"]-.025, radius=0)
        v, f = collider_mesh(body, segments)
        mesh_object(c["id"]+" recessed painted timber body", v, f, riser)
        if k:
            tail = dict(c, xmin=c["xmin"]-r, xmax=c["xmin"], zmin=c["zmax"]-.025, radius=0)
            v, f = collider_mesh(tail, segments)
            obj = mesh_object(c["id"]+" housed oak tread tail under nose", v, f, oak)
            oak_uv(obj, 1700+k, cfg["appearance"]["wood"]["repeat_m"])
    return {"nosing_overhang_m": r, "riser_recess_inside_collider": True}


def wall_string(cfg):
    """Sloped wall string replacing the stepped skirting outline above the treads."""
    bpy.data.objects.remove(bpy.data.objects["Continuous joinery / closed stepped skirting"], do_unlink=True)
    geometry = colliders(cfg)
    upper = next(c for c in geometry if c["id"] == "upper_platform")
    steps = [c for c in geometry if c["id"].startswith("S")]
    pitch = cfg["physics"]["stairs"]["rise_m"]/cfg["physics"]["stairs"]["tread_m"]
    top0 = upper["zmax"]+WALL_STRING_ABOVE_PITCH_M
    foot = (top0-.082)/pitch
    bottom = [(upper["xmin"], upper["zmax"]), (0, upper["zmax"])]
    for c in steps:
        bottom.extend([(c["xmin"], c["zmax"]), (c["xmax"], c["zmax"])])
    bottom.extend([(steps[-1]["xmax"], 0), (foot, 0)])
    top = [(foot, .082), (0, top0), (upper["xmin"], top0)]
    profile = bottom+top
    n = len(profile)
    verts = [(x, y, z) for y in [.452, .500] for x, z in profile]
    faces = [tuple(range(n)), tuple(reversed(range(n, 2*n)))]
    faces += [(j, j+n, (j+1) % n+n, (j+1) % n) for j in range(n)]
    trim = bpy.data.materials["Soft white eggshell timber trim"]
    obj = mesh_object("Sloped closed wall string / 18 mm painted", verts, faces, trim)
    bevel = obj.modifiers.new("One millimetre painted arris", "BEVEL")
    bevel.width, bevel.segments = .0015, 3
    obj.modifiers.new("Continuous trim normals", "WEIGHTED_NORMAL")
    return {"wall_string_height_above_pitch_m": WALL_STRING_ABOVE_PITCH_M, "wall_string_y_m": [.452, .5]}


def radiator(cfg):
    """Type-22 style compact panel radiator under the window, with valves and pipes."""
    wx0, wx1 = cfg["appearance"]["window"]["opening_x_m"]
    xc, width, z0, z1 = (wx0+wx1)/2, wx1-wx0-.12, .15, .63
    enamel = material("Gloss white stoved radiator enamel", (.90, .905, .89), .26)
    bs = enamel.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Coat Weight"].default_value = .25
    bs.inputs["Coat Roughness"].default_value = .18
    for y in [.418, .462]:
        box("Radiator water panel", (xc, y, (z0+z1)/2), (width, .018, z1-z0), enamel, .004)
    pitch = .05
    count = int(width/pitch)
    for i in range(count):
        x = xc-(count-1)*pitch/2+i*pitch
        box("Pressed radiator panel channel", (x, .4075, (z0+z1)/2), (.030, .004, z1-z0-.035), enamel, .0015)
    for x in [xc-width/2+.006, xc+width/2-.006]:
        box("Radiator side cover", (x, .44, (z0+z1)/2), (.012, .062, z1-z0+.01), enamel, .002)
    for i in range(int(width/.012)):
        box("Radiator top grille slat", (xc-width/2+.012*i+.006, .44, z1+.004), (.004, .052, .006), enamel, .0008)
    chrome = material("Chrome-plated radiator valve", (.62, .63, .64), .16)
    chrome.node_tree.nodes.get("Principled BSDF").inputs["Metallic"].default_value = 1.0
    white = material("White thermostatic valve head", (.86, .865, .85), .38)
    for x, head in [(xc-width/2-.035, True), (xc+width/2+.035, False)]:
        cylinder("15 mm radiator flow pipe", (x, .44, (z0+.03)/2), .0075, z0+.03, chrome)
        cylinder("Radiator valve body", (x, .44, z0+.045), .014, .05, chrome)
        edge = xc+(width/2 if x > xc else -width/2)
        tail = cylinder("Radiator valve tail", ((x+edge)/2, .44, z0+.045), .009, abs(edge-x), chrome)
        tail.rotation_euler.y = math.pi/2
        if head:
            cylinder("Thermostatic radiator valve head", (x, .44, z0+.115), .024, .085, white)
        else:
            cylinder("Lockshield cap", (x, .44, z0+.085), .013, .03, white)
        cylinder("Pipe floor collar", (x, .44, .002), .018, .004, white)
    return {"radiator_x_m": [xc-width/2, xc+width/2], "radiator_y_m": [.405, .471], "radiator_z_m": [z0, z1]}


def socket():
    plate = material("Satin white twin wall socket", (.86, .86, .845), .36)
    box("Twin 13 A socket faceplate", (1.62, .494, .32), (.146, .010, .086), plate, .002)
    dark = material("Socket pin apertures", (.05, .05, .05), .6)
    for x in [1.585, 1.655]:
        for dx, dz, w, h in [(0, .012, .004, .008), (-.011, -.006, .007, .004), (.011, -.006, .007, .004)]:
            box("Socket aperture", (x+dx, .4885, .32+dz), (w, .002, h), dark)


def repaint(paints):
    """Re-tint the daylit-room layer's broad paint variation ramp (.965-1.025 of the base colour)."""
    for name, rgb in paints.items():
        bs = bpy.data.materials[name].node_tree.nodes["Principled BSDF"]
        ramp = bs.inputs["Base Color"].links[0].from_node
        for e, scale in zip(ramp.color_ramp.elements, [.965, 1.025]):
            e.color = tuple(min(1.0, linear(c)*scale) for c in rgb)+(1,)


def import_prop(asset_root, asset, label, location, rotation_z):
    path = Path(asset_root)/"polyhaven"/asset/f"{asset}_2k.blend"
    if not path.is_file():
        raise FileNotFoundError(path)
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.objects = [n for n in src.objects]
    for obj in dst.objects:
        if obj.type != "MESH":
            bpy.data.objects.remove(obj, do_unlink=True)
            continue
        bpy.context.collection.objects.link(obj)
        obj.name = f"{label} / {obj.name}"
        obj.location = location
        obj.rotation_euler = (0, 0, rotation_z)
    return str(path)


def architecture_sunlit(cfg, asset_root):
    ledger = architecture_daylit_room(cfg, asset_root)
    ledger.update(housed_stairs(cfg))
    ledger.update(wall_string(cfg))
    ledger.update(radiator(cfg))
    socket()
    repaint(PAINT_SRGB)
    # Closes a 6 mm sliver between door head jamb and lintel that leaked daylight.
    box("Door head plaster filler", (3.55, .56, 2.05), (.86, .12, .024), bpy.data.materials["Warm neutral household emulsion"])
    wz0 = cfg["appearance"]["window"]["opening_z_m"][0]
    stool_top = wz0-.005+.014
    files = [import_prop(asset_root, "potted_plant_04", PROPS["potted_plant_04"], (2.04, .47, stool_top), math.radians(25)),
             import_prop(asset_root, "hanging_picture_frame_02", PROPS["hanging_picture_frame_02"], (.85, .5, 1.86), 0.0)]
    hdri = Path(asset_root)/"polyhaven"/HDRI_ASSET_sunlit/HDRI_FILE
    if not hdri.is_file():
        raise FileNotFoundError(hdri)
    bpy.context.scene["stair_daylight_hdri_file"] = str(hdri)
    ledger.update(appearance_revision=PRESET_sunlit, prop_files=files, props_min_y_m=.38,
        hdri_asset=HDRI_ASSET_sunlit, hdri_file=str(hdri), hdri_rotation_deg=HDRI_ROTATION_DEG_sunlit,
        diffuse_bounces=DIFFUSE_BOUNCES, max_bounces=MAX_BOUNCES, exposure_ev=EXPOSURE_EV_sunlit, view_look=VIEW_LOOK, paint_srgb=PAINT_SRGB,
        background_kind="Shared enclosed 3D room, actual window openings and glazing; photographic sunlit HDRI used as distant exterior and incident light, including its sun.")
    return ledger


def build_ball_sunlit(cfg):
    return build_ball_daylit_room(cfg)


def lighting_sunlit(cfg):
    # The photographed sky and sun are the only light; geometry admits them
    # through the two glazed openings. No lamps are added.
    path = Path(bpy.context.scene["stair_daylight_hdri_file"])
    world = bpy.data.worlds.new("Photographic sunlit daylight / enclosed room")
    world.use_nodes = True
    bpy.context.scene.world = world
    n, l = world.node_tree.nodes, world.node_tree.links
    environment = n.new("ShaderNodeTexEnvironment")
    environment.name = "Original CC0 sunny garden radiance"
    environment.image = bpy.data.images.load(str(path), check_existing=True)
    coords = n.new("ShaderNodeTexCoord")
    mapping = n.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value[2] = math.radians(HDRI_ROTATION_DEG_sunlit)
    l.new(coords.outputs["Generated"], mapping.inputs["Vector"])
    l.new(mapping.outputs["Vector"], environment.inputs["Vector"])
    background = n.get("Background")
    background.inputs["Strength"].default_value = cfg["appearance"]["environment_strength"]
    l.new(environment.outputs["Color"], background.inputs["Color"])
    s = bpy.context.scene
    s.cycles.diffuse_bounces, s.cycles.max_bounces = DIFFUSE_BOUNCES, MAX_BOUNCES
    s.view_settings.exposure, s.view_settings.look = EXPOSURE_EV_sunlit, VIEW_LOOK


PRESET = "home_oak_stairwell"


# Camera white balance (Blender 4.3 view white point). Under the mixed sky and
# oak-floor bounce light the wall rendered at r/g 1.04, b/g 0.87 (sRGB) without it.
WHITE_BALANCE_K = 5800.0


WHITE_BALANCE_TINT = 14.0


# The sunlit layer meters +0.6 EV without white balance; neutralising the yellow cast
# lowers the wall's apparent brightness, so the interior meter reads +0.9 EV.
EXPOSURE_EV = .9


# Scanned smooth painted plaster: Poly Haven reports 3000 x 3000 mm.
WALL_ASSET = "beige_wall_001"


WALL_TILE_M = 3.0


# Linear channel means of beige_wall_001_diff_4k.jpg; dividing by them keeps
# only the scanned blemish pattern (about 2 % RMS) on the calibrated paint.
WALL_DIFFUSE_LINEAR_MEAN = (.33939, .26212, .18853)


# 0.5-99.5 % range of beige_wall_001_rough_4k.jpg.
WALL_ROUGHNESS_RANGE = (.5647, .7098)


# material: (centre roughness, normal-map strength). Painted timber is smoother.
SCANNED_PAINT = {"Warm neutral household emulsion": (.79, .7),
                 "Painted timber risers and closed stringer": (.53, .5)}


PAINT_UV = "Scanned paint / world metres"


# Satin polyurethane over oak: thin clear coat with satin-lacquer roughness
# (broad, soft window reflections, no mirror image).
FLOOR_COAT_WEIGHT = .35


FLOOR_COAT_ROUGHNESS = .24


# Stair-side skirting, same profile as the landing skirting.
SKIRTING_DEPTH_M, SKIRTING_HEIGHT_M = .046, .082


# Members that overlap an upright with a shared front face; moved toward the room.
PROUD_MEMBERS_M = {"Window top architrave": .0006, "Window reveal head or stool": .0006,
                   "Slim window sash horizontal": .0006, "Door head jamb": .0006,
                   "Door casing head": .0006, "Panel moulding rail": .0006}


def world_uv(obj, size):
    """Planar world-metre UVs per face, continuous across adjoining wall boxes."""
    if PAINT_UV in obj.data.uv_layers:
        return
    uv = obj.data.uv_layers.new(name=PAINT_UV)
    mw = obj.matrix_world
    nm = mw.to_3x3().inverted().transposed()
    for poly in obj.data.polygons:
        n = nm @ poly.normal
        axis = max(range(3), key=lambda i: abs(n[i]))
        for li in poly.loop_indices:
            p = mw @ obj.data.vertices[obj.data.loops[li].vertex_index].co
            u, v = {0: (p.y, p.z), 1: (p.x, p.z), 2: (p.x, p.y)}[axis]
            uv.data[li].uv = (u/size, v/size)


def scanned_paint(asset_root):
    root = Path(asset_root)/"polyhaven"/WALL_ASSET
    files = {role: root/f"{WALL_ASSET}_{suffix}_4k.jpg" for role, suffix in
             [("color", "diff"), ("roughness", "rough"), ("normal", "nor_gl")]}
    if not all(p.is_file() for p in files.values()):
        raise FileNotFoundError(files)
    bpy.context.view_layer.update()
    for obj in bpy.data.objects:
        if obj.type == "MESH" and any(m and m.name in SCANNED_PAINT for m in obj.data.materials):
            world_uv(obj, WALL_TILE_M)
    for name, (roughness, strength) in SCANNED_PAINT.items():
        mat = bpy.data.materials[name]
        n, l = mat.node_tree.nodes, mat.node_tree.links
        bs = n.get("Principled BSDF")
        coords = n.new("ShaderNodeUVMap")
        coords.uv_map = PAINT_UV
        tex = {}
        for role, path in files.items():
            t = n.new("ShaderNodeTexImage")
            t.name = role+" scanned painted plaster / 3 m"
            t.image = bpy.data.images.load(str(path), check_existing=True)
            if role != "color":
                t.image.colorspace_settings.name = "Non-Color"
            l.new(coords.outputs["UV"], t.inputs["Vector"])
            tex[role] = t
        paint = bs.inputs["Base Color"].links[0].from_socket
        pattern = n.new("ShaderNodeVectorMath")
        pattern.operation = "MULTIPLY"
        pattern.inputs[1].default_value = tuple(1/m for m in WALL_DIFFUSE_LINEAR_MEAN)
        l.new(tex["color"].outputs["Color"], pattern.inputs[0])
        mix = n.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = 1
        l.new(paint, mix.inputs[1])
        l.new(pattern.outputs["Vector"], mix.inputs[2])
        l.new(mix.outputs[0], bs.inputs["Base Color"])
        rough = n.new("ShaderNodeMapRange")
        rough.inputs["From Min"].default_value, rough.inputs["From Max"].default_value = WALL_ROUGHNESS_RANGE
        rough.inputs["To Min"].default_value = roughness-.04
        rough.inputs["To Max"].default_value = roughness+.04
        l.new(tex["roughness"].outputs["Color"], rough.inputs["Value"])
        l.new(rough.outputs["Result"], bs.inputs["Roughness"])
        normal = n.new("ShaderNodeNormalMap")
        normal.uv_map = PAINT_UV
        normal.inputs["Strength"].default_value = strength
        l.new(tex["normal"].outputs["Color"], normal.inputs["Color"])
        l.new(normal.outputs["Normal"], bs.inputs["Normal"])
    return {"wall_finish_asset": WALL_ASSET, "wall_finish_tile_m": WALL_TILE_M,
            "wall_finish_files": {k: str(v) for k, v in files.items()},
            "wall_finish_materials": {k: {"roughness": r, "normal_strength": s} for k, (r, s) in SCANNED_PAINT.items()}}


def stair_side_skirting(cfg):
    """Painted skirting on the open side of the stair, with a mitred return."""
    from scene_config import colliders
    geometry = colliders(cfg)
    upper = next(c for c in geometry if c["id"] == "upper_platform")
    last = [c for c in geometry if c["id"].startswith("S")][-1]
    x0 = upper["xmin"]
    x1 = last["xmax"]-NOSING_OVERHANG_M+SKIRTING_DEPTH_M
    y_face = -cfg["physics"]["stairs"]["width_m"]/2
    trim = bpy.data.materials["Soft white eggshell timber trim"]
    box("Stair open-side skirting / mitred at foot", ((x0+x1)/2, y_face-SKIRTING_DEPTH_M/2, SKIRTING_HEIGHT_M/2),
             (x1-x0, SKIRTING_DEPTH_M, SKIRTING_HEIGHT_M), trim, .0012)
    box("Stair skirting narrow top bead", ((x0+x1)/2+.0005, y_face-.030, SKIRTING_HEIGHT_M+.0025),
             (x1-x0+.001, .040, .005), trim, .0015)
    return {"stair_skirting_x_m": [x0, x1+.001], "stair_skirting_y_m": [y_face-.05, y_face],
            "stair_skirting_height_m": SKIRTING_HEIGHT_M+.005}


def separate_coplanar_joinery():
    moved = 0
    for obj in bpy.data.objects:
        offset = PROUD_MEMBERS_M.get(obj.name.split(".")[0])
        if offset:
            obj.location.y -= offset
            moved += 1
    return {"joinery_members_set_proud": moved, "joinery_proud_m": max(PROUD_MEMBERS_M.values())}


def satin_lacquered_floor():
    mat = bpy.data.materials["Measured satin oak landing"]
    bs = mat.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Coat Weight"].default_value = FLOOR_COAT_WEIGHT
    bs.inputs["Coat Roughness"].default_value = FLOOR_COAT_ROUGHNESS
    bs.inputs["Coat IOR"].default_value = 1.50
    return {"floor_coat_weight": FLOOR_COAT_WEIGHT, "floor_coat_roughness": FLOOR_COAT_ROUGHNESS}


def architecture(cfg, asset_root):
    ledger = architecture_sunlit(cfg, asset_root)
    ledger.update(stair_side_skirting(cfg))
    ledger.update(separate_coplanar_joinery())
    ledger.update(scanned_paint(asset_root))
    ledger.update(satin_lacquered_floor())
    ledger.update(appearance_revision=PRESET, white_balance_k=WHITE_BALANCE_K, white_balance_tint=WHITE_BALANCE_TINT,
                  exposure_ev=EXPOSURE_EV)
    return ledger


def build_ball(cfg):
    return build_ball_sunlit(cfg)


def lighting(cfg):
    lighting_sunlit(cfg)
    v = bpy.context.scene.view_settings
    v.exposure = EXPOSURE_EV
    v.use_white_balance = True
    v.white_balance_temperature = WHITE_BALANCE_K
    v.white_balance_tint = WHITE_BALANCE_TINT
