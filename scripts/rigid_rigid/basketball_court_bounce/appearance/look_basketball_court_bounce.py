"""Text-free school gym: maple strip floor, trussed wall-mounted backstop, varnished closed bleachers.

gym(), build_ball(), lighting() and camera_response() build the look in layers: the full-scale gym,
photographic maple, the community maple court, photographic surfaces, lived-in detail, documentary finishes,
furniture and room clearing, and finally the text-free pass. Helpers suffixed with a layer name
(gym_furniture, build_ball_lived_in, ...) are the lower layers that the final functions build on.

Final text-free pass (static appearance only; every solved ball pose is kept): all lettering, numerals and
maker marks are removed (banner, scoreboard, EXIT letters, clock numerals, broom label, basketball ink stamp); the
glass board is carried on two welded side trusses anchored to the end wall; the closed telescopic bleachers
are long varnished riser boards with seat-plank nosings; the maple grain reads through the stained free
throw lanes.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector, Matrix, Euler, Quaternion


def look_at(obj, target):
    obj.rotation_euler = (Vector(target)-obj.location).to_track_quat("-Z", "Y").to_euler()


def material(name, color, roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    node = mat.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value = (*color, 1)
    node.inputs["Roughness"].default_value = roughness
    node.inputs["Metallic"].default_value = metallic
    return mat


def cube(name, location, dimensions, mat, bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    ob = bpy.context.object
    ob.name = name
    ob.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat:
        ob.data.materials.append(mat)
    if bevel:
        mod = ob.modifiers.new("Subtle manufactured edge", "BEVEL")
        mod.width, mod.segments = bevel, 2
        ob.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return ob


def tube(name, points, radius, mat, cyclic=False):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = radius
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    spline.points.add(len(points)-1)
    for p, xyz in zip(spline.points, points):
        p.co = (*xyz, 1)
    spline.use_cyclic_u = cyclic
    ob = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(ob)
    curve.materials.append(mat)
    return ob


def strip(name, x, y, dx, dy, mat):
    return cube(name, (x, y, 0.0004), (dx, dy, 0.0006), mat)


def arc(name, center, radius, width, mat, start=0, end=2*math.pi):
    count = max(32, int(256*(end-start)/(2*math.pi)))
    verts, faces = [], []
    for i in range(count+1):
        angle = start+(end-start)*i/count
        for rr in [radius-width/2, radius+width/2]:
            verts.append((center[0]+rr*math.cos(angle), center[1]+rr*math.sin(angle), 0.0008))
    for i in range(count):
        faces.append((2*i,2*i+1,2*i+3,2*i+2))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(mat)
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(ob)
    return ob


def maple_floor(cfg, asset_root):
    appearance = cfg["appearance"]
    folder = Path(asset_root)/appearance["wood_asset"]
    image = bpy.data.images.load(str(folder/"white_maple_veneer_diff_8k.jpg"), check_existing=True)
    rng = random.Random(appearance["seed"])
    mats = []
    for i in range(12):
        mat = material(f"Sealed maple / plank tone {i:02d}", (0.5,0.33,0.15), 0.30)
        nt = mat.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        bsdf.inputs["Coat Weight"].default_value = 0.34
        bsdf.inputs["Coat Roughness"].default_value = 0.23
        texture = nt.nodes.new("ShaderNodeTexImage")
        texture.image = image
        tint = nt.nodes.new("ShaderNodeMixRGB")
        tint.blend_type = "MULTIPLY"
        tint.inputs[0].default_value = 1
        tone = 0.89 + i*0.017
        tint.inputs[2].default_value = (*[tone*v for v in appearance["floor_tint_rgb"]], 1)
        nt.links.new(texture.outputs["Color"], tint.inputs[1])
        nt.links.new(tint.outputs[0], bsdf.inputs["Base Color"])
        coord = nt.nodes.new("ShaderNodeTexCoord")
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 85
        noise.inputs["Detail"].default_value = 2
        nt.links.new(coord.outputs["UV"], noise.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeMapRange")
        ramp.inputs["To Min"].default_value = 0.24
        ramp.inputs["To Max"].default_value = 0.36
        nt.links.new(noise.outputs["Fac"], ramp.inputs["Value"])
        nt.links.new(ramp.outputs["Result"], bsdf.inputs["Roughness"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.14
        bump.inputs["Distance"].default_value = 0.00010
        nt.links.new(texture.outputs["Color"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        mats.append(mat)
    dark = material("Dark hairline maple joints", (0.15,0.09,0.04), 0.4)
    cube("Continuous structural sports floor", (0,0,-0.0606), (18,32,0.12), dark)
    width, length = appearance["plank_width_m"], appearance["plank_nominal_length_m"]
    verts, faces, uvs, indices = [], [], [], []
    rows = math.ceil(32/width)
    for row in range(rows):
        y0, y1 = -16+row*width, min(16,-16+(row+1)*width)
        x0 = -9
        first = length*rng.uniform(0.18,0.95)
        while x0 < 9-1e-8:
            x1 = min(9, x0+(first if x0 == -9 else length*rng.uniform(0.72,1.22)))
            offset = len(verts)
            gap = 0.0005
            verts.extend([(x0+gap,y0+gap,0), (x1-gap,y0+gap,0), (x1-gap,y1-gap,0), (x0+gap,y1-gap,0)])
            faces.append((offset,offset+1,offset+2,offset+3))
            u, v = rng.random(), rng.random()
            # The source veneer grain runs along image V; preserve metric scale on every plank.
            uvs.extend([(u,v),(u,v+(x1-x0)/2.4),(u+width/1.0,v+(x1-x0)/2.4),(u+width/1.0,v)])
            indices.append(rng.randrange(len(mats)))
            x0 = x1
    mesh = bpy.data.meshes.new("Individual maple strip faces")
    mesh.from_pydata(verts, [], faces)
    for mat in mats:
        mesh.materials.append(mat)
    uv = mesh.uv_layers.new(name="Metric veneer UV")
    for poly, index in zip(mesh.polygons, indices):
        poly.material_index = index
        for loop in poly.loop_indices:
            uv.data[loop].uv = uvs[mesh.loops[loop].vertex_index]
    ob = bpy.data.objects.new("Maple sport flooring / 90 mm staggered planks", mesh)
    bpy.context.collection.objects.link(ob)
    return len(faces)


def court_lines(cfg):
    white = material("Court line / warm white polyurethane paint", (0.80,0.83,0.78), 0.36)
    teal = material("Secondary court paint / muted navy", (0.035,0.095,0.105), 0.37)
    w = cfg["appearance"]["court_line_width_m"]
    for x in [-7.5,7.5]:
        strip("15 by 28 m court / sideline", x,0,w,28+w,white)
    for y in [-14,14]:
        strip("Court baseline",0,y,15,w,white)
    strip("Half court line",0,0,15,w,white)
    arc("Center circle / 1.80 m radius", (0,0),1.8,w,white)
    arc("Center circle navy accent",(0,0),1.86,0.015,teal)
    for sign in [-1,1]:
        y = sign*8.2
        for x in [-2.45,2.45]:
            strip("Lane boundary",x,sign*11.1,w,5.8,white)
        strip("Free throw line",0,y,4.9,w,white)
        arc("Free throw semicircle",(0,y),1.8,w,white,0 if sign<0 else math.pi,math.pi if sign<0 else 2*math.pi)
        hoop_y = sign*12.425
        if sign > 0:
            arc("Three point arc",(0,hoop_y),6.75,w,teal,math.pi+0.40,2*math.pi-0.40)
        else:
            arc("Three point arc",(0,hoop_y),6.75,w,teal,0.40,math.pi-0.40)


def build_hoop(metal, graphite):
    glass = material("Backboard glass",(0.50,0.61,0.61),0.18)
    bsdf = glass.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Transmission Weight"].default_value = 0.55
    bsdf.inputs["IOR"].default_value = 1.5
    cube("1.80 by 1.05 m basketball backboard",(0,12.94,3.45),(1.8,0.045,1.05),glass,0.008)
    for x in [-0.88,0.88]:
        cube("Backboard edge",(x,12.90,3.45),(0.035,0.025,1.05),metal)
    for z in [2.94,3.96]:
        cube("Backboard edge",(0,12.90,z),(1.8,0.025,0.035),metal)
    for x in [-0.295,0.295]:
        cube("Backboard target square",(x,12.894,3.26),(0.025,0.015,0.45),metal)
    for z in [3.045,3.475]:
        cube("Backboard target square",(0,12.894,z),(0.615,0.015,0.025),metal)
    cube("Wall mounted hoop support",(0,14.52,4.0),(0.11,2.96,0.13),graphite,0.01)
    cube("Backboard support bracket",(0,12.98,3.64),(0.10,0.12,0.75),graphite,0.008)
    orange = material("Orange steel basketball rim",(0.55,0.09,0.014),0.35,0.35)
    pts = [(0.225*math.cos(i*math.tau/96),12.425+0.225*math.sin(i*math.tau/96),3.05) for i in range(96)]
    tube("45 cm basketball rim",pts,0.009,orange,True)
    cube("Rim bracket",(0,12.75,3.05),(0.13,0.26,0.022),orange,0.008)
    net = material("Braided ivory basketball net",(0.70,0.70,0.62),0.85)
    for i in range(12):
        angle = i*math.tau/12
        for side in [-1,1]:
            points = []
            for j in range(9):
                f = j/8
                a = angle+side*f*math.tau/12
                rr = 0.225*(1-0.40*f)
                points.append((rr*math.cos(a),12.425+rr*math.sin(a),3.04-0.42*f))
            tube("Net diamond cord",points,0.0020,net)


def noise_surface(mat, scale, strength, distance, low=0.45, high=0.65):
    nt = mat.node_tree
    bs = nt.nodes.get("Principled BSDF")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 3
    nt.links.new(coord.outputs["Object"],noise.inputs["Vector"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = low
    rough.inputs["To Max"].default_value = high
    nt.links.new(noise.outputs["Fac"],rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"],bs.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    nt.links.new(noise.outputs["Fac"],bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"],bs.inputs["Normal"])


def floor_finish(cfg, asset_root):
    count = maple_floor(cfg,asset_root)
    root = Path(asset_root)/cfg["appearance"]["wood_asset"]
    rough_path = root/"white_maple_veneer_rough_4k.jpg"
    normal_path = root/"white_maple_veneer_nor_gl_4k.jpg"
    for dependency in [rough_path,normal_path]:
        if not dependency.is_file():
            raise FileNotFoundError(dependency)
    for mat in bpy.data.materials:
        if not mat.name.startswith("Sealed maple / plank tone"):
            continue
        nt = mat.node_tree
        bs = nt.nodes.get("Principled BSDF")
        bs.inputs["Coat Weight"].default_value = cfg["appearance"]["floor_coat_weight"]
        bs.inputs["Coat Roughness"].default_value = cfg["appearance"]["floor_coat_roughness"]
        if rough_path.exists():
            image = bpy.data.images.load(str(rough_path),check_existing=True)
            image.colorspace_settings.name = "Non-Color"
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = image
            remap = nt.nodes.new("ShaderNodeMapRange")
            remap.inputs["To Min"].default_value = cfg["appearance"]["floor_roughness_range"][0]
            remap.inputs["To Max"].default_value = cfg["appearance"]["floor_roughness_range"][1]
            nt.links.new(tex.outputs["Color"],remap.inputs["Value"])
            nt.links.new(remap.outputs["Result"],bs.inputs["Roughness"])
        if normal_path.exists():
            image = bpy.data.images.load(str(normal_path),check_existing=True)
            image.colorspace_settings.name = "Non-Color"
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = image
            normal = nt.nodes.new("ShaderNodeNormalMap")
            normal.inputs["Strength"].default_value = 0.045
            nt.links.new(tex.outputs["Color"],normal.inputs["Color"])
            nt.links.new(normal.outputs["Normal"],bs.inputs["Normal"])
    court_lines(cfg)
    for mat in bpy.data.materials:
        if "Court line /" in mat.name or "Secondary court paint" in mat.name:
            noise_surface(mat,150,0.10,0.000035,0.28,0.38)
    # Sparse, translucent rubber scuffs at real shoe scale, all on the floor.
    scuff = bpy.data.materials.new("Subtle rubber sole transfer on polyurethane")
    scuff.use_nodes = True
    nt = scuff.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    transparent = nt.nodes.new("ShaderNodeBsdfTransparent")
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bs.inputs["Base Color"].default_value = (0.035,0.025,0.018,1)
    bs.inputs["Roughness"].default_value = 0.68
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = 0.11
    nt.links.new(transparent.outputs[0],mix.inputs[1])
    nt.links.new(bs.outputs[0],mix.inputs[2])
    nt.links.new(mix.outputs[0],out.inputs[0])
    rng = random.Random(919)
    for i in range(22):
        x,y = rng.uniform(-5,5),rng.uniform(-4,5)
        rr = rng.uniform(0.08,0.20)
        start = rng.random()*math.tau
        end = start+rng.uniform(0.3,1.2)
        ob = arc(f"Faint shoe sole scuff {i:02d}",(x,y),rr,rng.uniform(0.001,0.004),scuff,start,end)
        for v in ob.data.vertices:
            v.co.z = 0.000025
        ob.visible_shadow = False
    return count


def build_ball_photographic_maple(cfg, asset_root):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(Path(asset_root)/cfg["appearance"]["basketball_asset"]/"basketball.glb"))
    imported = set(bpy.data.objects)-before
    meshes = [o for o in imported if o.type=="MESH"]
    if len(meshes)!=1:
        raise RuntimeError("Expected one basketball visual mesh")
    ball = meshes[0]
    matrix = ball.matrix_world.copy()
    world = [matrix@v.co for v in ball.data.vertices]
    low = Vector([min(v[i] for v in world) for i in range(3)])
    high = Vector([max(v[i] for v in world) for i in range(3)])
    center = (low+high)/2
    scale = (2*cfg["physics"]["ball"]["radius_m"])/max(high-low)
    for vertex,point in zip(ball.data.vertices,world):
        vertex.co = (point-center)*scale
    ball.parent = None
    ball.matrix_world = Matrix.Identity(4)
    basis = Euler([math.radians(a) for a in cfg["appearance"]["ball_visual_rotation_euler_deg"]], "XYZ").to_matrix()
    for vertex in ball.data.vertices:
        vertex.co = basis @ vertex.co
    ball.data.update()
    ball.data.normals_split_custom_set_from_vertices([v.co.normalized() for v in ball.data.vertices])
    for ob in imported:
        if ob!=ball:
            bpy.data.objects.remove(ob,do_unlink=True)
    ball.name = "B01 / 240 mm basketball / mapped eight-panel composite cover"
    for poly in ball.data.polygons:
        poly.use_smooth = True
    for mat in ball.data.materials:
        bs = mat.node_tree.nodes.get("Principled BSDF")
        bs.inputs["Roughness"].default_value = 0.58
        bs.inputs["Specular IOR Level"].default_value = 0.32
        bs.inputs["Coat Weight"].default_value = 0.0
        for node in mat.node_tree.nodes:
            if node.type=="NORMAL_MAP":
                node.inputs["Strength"].default_value = 0.68
        noise_surface_roughness(mat)
    apply_surface_print(ball,cfg)
    ball["object_id"] = "B01"
    ball["physical_diameter_m"] = 0.24
    ball["source_world_bbox_dimensions_m"] = list(high-low)
    ball["normalization_scale"] = scale
    ball["surface_detail"] = "CC0 Innerscene eight-panel basketball; base color and tangent normals; constant normalized visual mesh, same independent physical sphere"
    return ball


def apply_surface_print(ball,cfg):
    """A thin, authored generic size/indoor stamp follows the sphere surface."""
    r = cfg["physics"]["ball"]["radius_m"]
    x,y,z,w = cfg["physics"]["ball"]["initial_quaternion_xyzw"]
    orientation = Quaternion((w,x,y,z));orientation.normalize()
    eye = Vector(cfg["appearance"]["camera"]["position_m"])
    center = Vector(cfg["physics"]["ball"]["initial_position_m"])
    n = orientation.inverted() @ (eye-center).normalized()
    u = Vector((0,0,1)).cross(n).normalized()
    v = n.cross(u).normalized()
    ink = material("Generic basketball stamped black ink",(0.011,0.009,0.007),0.72)
    for body,size,offset in [(cfg["appearance"]["ball_print_text"],0.014,0.013),("7  /  INDOOR",0.0048,-0.008)]:
        curve = bpy.data.curves.new("Original generic basketball surface stamp","FONT")
        curve.body,curve.size,curve.align_x,curve.align_y = body,size,"CENTER","CENTER"
        curve.resolution_u = 4
        text = bpy.data.objects.new("Basketball ink stamp",curve)
        bpy.context.collection.objects.link(text)
        curve.materials.append(ink)
        bpy.ops.object.select_all(action="DESELECT")
        text.select_set(True);bpy.context.view_layer.objects.active=text
        bpy.ops.object.convert(target="MESH")
        text = bpy.context.object
        bm = bmesh.new();bm.from_mesh(text.data)
        bmesh.ops.triangulate(bm,faces=list(bm.faces))
        bmesh.ops.subdivide_edges(bm,edges=list(bm.edges),cuts=3,use_grid_fill=True)
        bm.to_mesh(text.data);bm.free()
        for vertex in text.data.vertices:
            vertex.co = (n*r + u*(vertex.co.x-0.025) + v*(vertex.co.y+offset)).normalized()*(r+0.000025)
        for face in text.data.polygons:face.use_smooth=True
        text.data.update()
        text.data.normals_split_custom_set_from_vertices([a.co.normalized() for a in text.data.vertices])
        bpy.ops.object.select_all(action="DESELECT")
        text.select_set(True);ball.select_set(True);bpy.context.view_layer.objects.active=ball
        bpy.ops.object.join()
    ball["surface_stamp_thickness_m"] = 0.000025


def noise_surface_roughness(mat):
    nt = mat.node_tree
    bs = nt.nodes.get("Principled BSDF")
    tex = nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 75
    tex.inputs["Detail"].default_value = 2
    uv = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(uv.outputs["UV"],tex.inputs["Vector"])
    mapped = nt.nodes.new("ShaderNodeMapRange")
    mapped.inputs["To Min"].default_value = 0.51
    mapped.inputs["To Max"].default_value = 0.66
    nt.links.new(tex.outputs["Fac"],mapped.inputs["Value"])
    nt.links.new(mapped.outputs["Result"],bs.inputs["Roughness"])


def painted_blockwork(name, axis, color, appearance):
    """Metric running-bond joints in shared world coordinates across wall pieces."""
    mat = material(name, color, 0.84)
    nt = mat.node_tree
    bs = nt.nodes.get("Principled BSDF")
    position = nt.nodes.new("ShaderNodeNewGeometry")
    split = nt.nodes.new("ShaderNodeSeparateXYZ")
    combine = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(position.outputs["Position"], split.inputs[0])
    nt.links.new(split.outputs[axis], combine.inputs[0])
    nt.links.new(split.outputs["Z"], combine.inputs[1])
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Color1"].default_value = (*[c * 0.97 for c in color], 1)
    brick.inputs["Color2"].default_value = (*[c * 1.025 for c in color], 1)
    brick.inputs["Mortar"].default_value = (*[c * 0.90 for c in color], 1)
    brick.inputs["Mortar Size"].default_value = appearance["wall_mortar_width_m"]
    brick.inputs["Mortar Smooth"].default_value = 0.0015
    brick.inputs["Brick Width"].default_value = 0.40
    brick.inputs["Row Height"].default_value = 0.20
    nt.links.new(combine.outputs[0], brick.inputs["Vector"])
    nt.links.new(brick.outputs["Color"], bs.inputs["Base Color"])
    joint = nt.nodes.new("ShaderNodeBump")
    joint.invert = True
    joint.inputs["Strength"].default_value = 0.55
    joint.inputs["Distance"].default_value = appearance["wall_mortar_depth_m"]
    nt.links.new(brick.outputs["Fac"], joint.inputs["Height"])
    grain = nt.nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 220
    grain.inputs["Detail"].default_value = 2
    nt.links.new(position.outputs["Position"], grain.inputs["Vector"])
    finish = nt.nodes.new("ShaderNodeBump")
    finish.inputs["Strength"].default_value = 0.15
    finish.inputs["Distance"].default_value = 0.00018
    nt.links.new(grain.outputs["Fac"], finish.inputs["Height"])
    nt.links.new(joint.outputs["Normal"], finish.inputs["Normal"])
    nt.links.new(finish.outputs["Normal"], bs.inputs["Normal"])
    return mat


def bench_wood():
    mat = material("Bench / oiled ash with longitudinal grain", (0.28,0.15,0.06),0.43)
    nt = mat.node_tree
    bs = nt.nodes.get("Principled BSDF")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    stretch = nt.nodes.new("ShaderNodeVectorMath")
    stretch.operation = "MULTIPLY"
    stretch.inputs[1].default_value = (0.65,65,45)
    nt.links.new(coord.outputs["Object"],stretch.inputs[0])
    grain = nt.nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 3
    grain.inputs["Detail"].default_value = 3
    grain.inputs["Roughness"].default_value = 0.6
    nt.links.new(stretch.outputs["Vector"],grain.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.1
    ramp.color_ramp.elements[0].color = (0.19,0.087,0.030,1)
    ramp.color_ramp.elements[1].position = 0.9
    ramp.color_ramp.elements[1].color = (0.39,0.24,0.10,1)
    nt.links.new(grain.outputs["Fac"],ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"],bs.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.00012
    nt.links.new(grain.outputs["Fac"],bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"],bs.inputs["Normal"])
    return mat


def gym_community_maple(cfg, asset_root):
    plank_count = floor_finish(cfg,asset_root)
    appearance = cfg["appearance"]
    dado_height = appearance["wall_dado_height_m"]
    upper_color = appearance["wall_upper_rgb"]
    lower_color = appearance["wall_dado_rgb"]
    upper = {axis:painted_blockwork("Warm painted blockwork / "+axis,axis,upper_color,appearance) for axis in ["X","Y"]}
    lower = {axis:painted_blockwork("Washable painted wall dado / "+axis,axis,lower_color,appearance) for axis in ["X","Y"]}
    white = material("Satin off-white painted structural steel",(0.52,0.55,0.53),0.43,0.12)
    steel = material("Powder-coated gym support steel",(0.035,0.043,0.045),0.46,0.25)
    rubber = material("Rubber skirting and safety edges",(0.022,0.026,0.025),0.72)

    # The rear wall has a real 1.06 x 2.18 m door opening; frames sit in the reveal.
    door_x = -6.8
    door_half = 0.53
    for left,right in [(-9.3,door_x-door_half),(door_x+door_half,9.3)]:
        for bottom,top,mat in [(0,dado_height,lower["X"]),(dado_height,7,upper["X"])]:
            cube("Continuous rear blockwork",((left+right)/2,16.18,(bottom+top)/2),(right-left,0.36,top-bottom),mat)
    cube("Blockwork above door opening",(door_x,16.18,(2.18+7)/2),(1.06,0.36,7-2.18),upper["X"])
    for x in [-9.18,9.18]:
        cube("Side wall washable dado",(x,0,dado_height/2),(0.36,32,dado_height),lower["Y"])
        cube("Side wall below actual windows",(x,0,(dado_height+3.2)/2),(0.36,32,3.2-dado_height),upper["Y"])
        cube("Side wall above windows",(x,0,6.4),(0.36,32,1.2),upper["Y"])
        edges = [-16,-13.95,-10.05,-7.95,-4.05,-1.95,1.95,4.05,7.95,10.05,13.95,16]
        for a,b in zip(edges[::2],edges[1::2]):
            cube("Masonry window pier",(x,(a+b)/2,4.5),(0.36,b-a,2.6),upper["Y"])
    cube("High acoustic ceiling",(0,0,7.12),(18.5,32.5,0.24),white)
    for y in [-12,-6,0,6,12]:
        cube("Steel roof beam",(0,y,6.79),(18,0.12,0.27),steel,0.009)
    for left,right in [(-9,door_x-door_half),(door_x+door_half,9)]:
        cube("Rear bonded rubber skirting",((left+right)/2,15.992,0.05),(right-left,0.016,0.10),rubber,0.002)
    for x in [-8.992,8.992]:
        cube("Side bonded rubber skirting",(x,0,0.05),(0.016,32,0.10),rubber,0.002)

    # Local 45 mm protection under the basket; one soft face without cabinet-like gaps.
    pad = material("Continuous matt vinyl basket safety mat",(0.075,0.13,0.14),0.66)
    noise_surface(pad,330,0.14,0.00020,0.60,0.72)
    pad_width,pad_height,pad_depth = appearance["basket_wall_pad_dimensions_m"]
    pad_front = 16.0-pad_depth
    cube("Thin basket wall safety mat",(0,16.0-pad_depth/2,0.08+pad_height/2),(pad_width,pad_depth,pad_height),pad,0.010)
    # Flush welded vinyl seams use the same material, no dark frames or grooves.
    for x in [-pad_width/6,pad_width/6]:
        tube("Flush vinyl welded seam",[(x,pad_front-0.0006,0.10),(x,pad_front-0.0006,pad_height+0.06)],0.0008,pad)

    door = material("Painted steel gym door",(0.15,0.21,0.22),0.55,0.08)
    noise_surface(door,180,0.1,0.00006,0.50,0.59)
    for dx in [-0.51,0.51]:
        cube("Door reveal jamb",(door_x+dx,16.025,1.08),(0.04,0.14,2.16),door,0.002)
    cube("Door reveal head",(door_x,16.025,2.14),(1.06,0.14,0.04),door,0.002)
    # Four pieces leave an actual opening for the wired observation glass.
    for dx in [-0.295,0.295]:
        cube("Door leaf beside glazing",(door_x+dx,16.015,1.055),(0.37,0.045,2.08),door,0.002)
    cube("Door leaf below glazing",(door_x,16.015,0.6475),(0.22,0.045,1.265),door,0.002)
    cube("Door leaf above glazing",(door_x,16.015,1.9975),(0.22,0.045,0.195),door,0.002)
    glass = material("Wired door observation glass",(0.11,0.15,0.15),0.24)
    cube("Recessed observation glass",(door_x,16.018,1.59),(0.22,0.014,0.62),glass)
    for dx in [-0.119,0.119]:
        cube("Narrow metal glazing bead",(door_x+dx,15.987,1.59),(0.018,0.014,0.65),door,0.001)
    for z in [1.272,1.908]:
        cube("Narrow metal glazing bead",(door_x,15.987,z),(0.256,0.014,0.018),door,0.001)
    for dx in [-0.29,0.29]:
        cube("Push bar stand-off",(door_x+dx,15.959,1.0),(0.028,0.067,0.05),steel,0.003)
    cube("Brushed metal door push bar",(door_x,15.92,1.0),(0.66,0.025,0.035),white,0.006)
    for z in [0.25,1.05,1.88]:
        cube("Recessed door hinge",(door_x-0.48,15.978,z),(0.018,0.023,0.08),steel,0.003)
    cube("Door threshold",(door_x,16.025,0.003),(1.06,0.14,0.006),white,0.001)

    timber = bench_wood()
    for bx in [-4.4,4.5]:
        for j in range(3):
            cube("Bench seat ash slat",(bx,15.37+j*0.124,0.43),(2.6,0.116,0.04),timber,0.004)
        for z in [0.68,0.80]:
            cube("Bench backrest ash board",(bx,15.66,z),(2.6,0.035,0.10),timber,0.004)
        for dx in [-1.0,1.0]:
            for yy in [15.39,15.65]:
                cube("Bench square steel leg",(bx+dx,yy,0.222),(0.035,0.035,0.416),steel,0.002)
            cube("Bench steel foot on floor",(bx+dx,15.52,0.014),(0.065,0.43,0.028),steel,0.002)
            cube("Bench under-seat cross member",(bx+dx,15.52,0.397),(0.04,0.36,0.025),steel,0.002)
            cube("Bench backrest support",(bx+dx,15.69,0.62),(0.03,0.03,0.44),steel,0.002)
        cube("Bench longitudinal steel stretcher",(bx,15.52,0.24),(2.03,0.025,0.025),steel,0.002)

    window = material("Clear lightly diffusing gym glazing",(0.88,0.93,0.96),0.16)
    bs = window.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Transmission Weight"].default_value = 1.0
    bs.inputs["IOR"].default_value = 1.48
    for x in [-9.0,9.0]:
        for y in [-12,-6,0,6,12]:
            cube("Actual glazed window opening",(x,y,4.5),(0.012,3.88,2.58),window)
            for dy in [-1.97,0,1.97]:
                cube("Window steel mullion",(x,y+dy,4.5),(0.09,0.045,2.64),white,0.003)
            for z in [3.18,4.5,5.82]:
                cube("Window transom",(x,y,z),(0.09,3.98,0.045),white,0.003)
            cube("Window sill",(x+(0.05 if x<0 else -0.05),y,3.17),(0.22,4.04,0.055),white,0.003)
    build_hoop(white,steel)
    for ob in bpy.context.scene.objects:
        if ob.name.startswith("1.80 by 1.05 m basketball backboard"):
            ob.data.materials[0] = window
    cube("Backboard lower rubber safety pad",(0,12.89,2.94),(1.84,0.11,0.07),rubber,0.013)
    for x in [-0.88,0.88]:
        cube("Backboard side safety pad",(x,12.89,3.04),(0.07,0.11,0.22),rubber,0.013)
    return {"gym_dimensions_m":[18,32,7],"court_dimensions_m":[15,28],"door_dimensions_m":[0.96,2.08],
        "door_opening_dimensions_m":[1.06,2.18],"door_frame_front_projection_m":0.045,
        "bench_seat_height_m":0.45,"bench_foot_min_z_m":0.0,"bench_length_m":2.6,
        "wall_dado_height_m":dado_height,"local_basket_safety_mat_dimensions_m":[pad_width,pad_depth,pad_height],
        "cabinet_like_repeated_wall_modules":False,"floating_acoustic_plaques":False,
        "rim_height_m":3.05,"rim_inner_diameter_m":0.45,"maple_plank_width_m":0.09,
        "maple_plank_count":plank_count,"floor_surface_z_m":0,
        "all_foreground_background_geometry_in_one_scene":True,
        "masonry_block_dimensions_m":[0.40,0.20],"actual_side_window_openings":True}


def sealed_floor_material(name, asset_root, cfg, index=0):
    a=cfg["appearance"]
    scan=a["floor_surface_model"]=="scanned_hardwood"
    folder=Path(asset_root)/(a["floor_scan_asset"] if scan else a["wood_asset"])
    prefix="wood_floor" if scan else "white_maple_veneer"
    files=[folder/(prefix+"_diff_4k.jpg" if scan else prefix+"_diff_8k.jpg"),folder/(prefix+"_nor_gl_4k.jpg"),folder/(prefix+"_rough_4k.jpg")]
    for path in files:
        if not path.is_file():raise FileNotFoundError(path)
    mat=material(name,(0.4,0.25,0.11),0.25)
    nt=mat.node_tree;bs=nt.nodes.get("Principled BSDF")
    bs.inputs["Coat Weight"].default_value=a["floor_coat_weight"]
    bs.inputs["Coat Roughness"].default_value=a["floor_coat_roughness"]
    tex=[]
    for i,path in enumerate(files):
        image=bpy.data.images.load(str(path),check_existing=True)
        if i:image.colorspace_settings.name="Non-Color"
        node=nt.nodes.new("ShaderNodeTexImage");node.image=image;tex.append(node)
    tint=nt.nodes.new("ShaderNodeMixRGB");tint.blend_type="MULTIPLY";tint.inputs[0].default_value=1
    tone=0.80+index*0.032 if not scan else 1.0
    color=a["floor_scan_tint_rgb"] if scan else a["floor_tint_rgb"]
    tint.inputs[2].default_value=(*[v*tone for v in color],1)
    nt.links.new(tex[0].outputs["Color"],tint.inputs[1]);nt.links.new(tint.outputs[0],bs.inputs["Base Color"])
    normal=nt.nodes.new("ShaderNodeNormalMap");normal.inputs["Strength"].default_value=a["floor_normal_strength"]
    nt.links.new(tex[1].outputs["Color"],normal.inputs["Color"]);nt.links.new(normal.outputs["Normal"],bs.inputs["Normal"])
    remap=nt.nodes.new("ShaderNodeMapRange");remap.inputs["To Min"].default_value=a["floor_roughness_range"][0];remap.inputs["To Max"].default_value=a["floor_roughness_range"][1]
    nt.links.new(tex[2].outputs["Color"],remap.inputs["Value"]);nt.links.new(remap.outputs["Result"],bs.inputs["Roughness"])
    return mat


def refinish_floor(cfg,asset_root):
    a=cfg["appearance"]
    ob=bpy.data.objects["Maple sport flooring / 90 mm staggered planks"]
    old_materials=list(ob.data.materials)
    if a["floor_surface_model"]=="scanned_hardwood":
        old_mesh=ob.data
        bpy.data.objects.remove(ob,do_unlink=True)
        bpy.data.meshes.remove(old_mesh)
        mesh=bpy.data.meshes.new("Continuous photographic sports floor surface")
        mesh.from_pydata([(-9,-16,0),(9,-16,0),(9,16,0),(-9,16,0)],[],[(0,1,2,3)])
        uv=mesh.uv_layers.new(name="Measured 1.7 m scanned floor repeat")
        for loop in mesh.loops:
            co=mesh.vertices[loop.vertex_index].co
            uv.data[loop.index].uv=(co.y/a["floor_scan_repeat_m"],co.x/a["floor_scan_repeat_m"])
        mesh.materials.append(sealed_floor_material("Sealed photographic hardwood floor",asset_root,cfg))
        ob=bpy.data.objects.new("Photographic hardwood sports floor",mesh);bpy.context.collection.objects.link(ob)
        ledger={"floor_surface_model":"photographic sealed hardwood","photographic_tile_width_m":a["floor_scan_repeat_m"],"floor_geometry_surface_z_m":0.0}
    else:
        ob.data.materials.clear()
        for i in range(11):ob.data.materials.append(sealed_floor_material(f"Correct-grain sealed maple / tone {i:02d}",asset_root,cfg,i))
        rng=random.Random(a["seed"]+51);uv=ob.data.uv_layers.active
        for face in ob.data.polygons:
            vertices=[ob.data.vertices[i] for i in face.vertices]
            cx=sum(v.co.x for v in vertices)/4;cy=sum(v.co.y for v in vertices)/4
            close=0.0005-a["plank_joint_width_m"]/2
            for v in vertices:
                v.co.x+=close if v.co.x>cx else -close
                v.co.y+=close if v.co.y>cy else -close
            origin=vertices[0].co.copy();u,v=rng.random(),rng.random();direction=1 if rng.random()>0.5 else -1
            for loop in face.loop_indices:
                co=ob.data.vertices[ob.data.loops[loop].vertex_index].co
                # The actual source image grain runs along U; one image spans 1 m.
                uv.data[loop].uv=(u+direction*(co.x-origin.x),v+direction*(co.y-origin.y))
            face.material_index=rng.randrange(11)
        ob.data.update();ob.name="Correct-grain 57 mm strip maple sports floor"
        ledger={"floor_surface_model":"individual sealed maple strips","plank_width_m":a["plank_width_m"],"plank_joint_width_m":a["plank_joint_width_m"],"grain_aligned_to_board_length":True,"source_texture_width_m":1.0,"floor_geometry_surface_z_m":0.0}
    for mat in old_materials:
        if mat.users==0:bpy.data.materials.remove(mat)
    return ledger


def finish_walls(cfg):
    """Low-amplitude roller variation and localized lower-wall use, in metres."""
    for mat in list(bpy.data.materials):
        if not mat.name.startswith(("Warm painted blockwork","Washable painted wall dado")):continue
        nt=mat.node_tree;bs=nt.nodes.get("Principled BSDF")
        source=bs.inputs["Base Color"].links[0].from_socket
        position=nt.nodes.new("ShaderNodeNewGeometry")
        noise=nt.nodes.new("ShaderNodeTexNoise");noise.inputs["Scale"].default_value=0.95;noise.inputs["Detail"].default_value=3;noise.inputs["Roughness"].default_value=0.65
        nt.links.new(position.outputs["Position"],noise.inputs["Vector"])
        ramp=nt.nodes.new("ShaderNodeValToRGB");ramp.color_ramp.elements[0].color=(0.89,0.90,0.89,1);ramp.color_ramp.elements[1].color=(1.015,1.015,1.01,1)
        nt.links.new(noise.outputs["Fac"],ramp.inputs["Fac"])
        mult=nt.nodes.new("ShaderNodeMixRGB");mult.blend_type="MULTIPLY";mult.inputs[0].default_value=1
        nt.links.new(source,mult.inputs[1]);nt.links.new(ramp.outputs["Color"],mult.inputs[2]);nt.links.new(mult.outputs[0],bs.inputs["Base Color"])
        rough=nt.nodes.new("ShaderNodeMapRange");rough.inputs["To Min"].default_value=0.76;rough.inputs["To Max"].default_value=0.89
        nt.links.new(noise.outputs["Fac"],rough.inputs["Value"]);nt.links.new(rough.outputs["Result"],bs.inputs["Roughness"])


def gym_photographic(cfg,asset_root):
    ledger=gym_community_maple(cfg,asset_root)
    floor_ledger=refinish_floor(cfg,asset_root);ledger.update(floor_ledger)
    ledger.pop("maple_plank_width_m",None)
    if cfg["appearance"]["floor_surface_model"]=="scanned_hardwood":ledger.pop("maple_plank_count",None)
    finish_walls(cfg)
    # One regulation centre ring; remove the decorative second outline.
    for ob in list(bpy.data.objects):
        if ob.name=="Center circle navy accent":bpy.data.objects.remove(ob,do_unlink=True)
    for mat in bpy.data.materials:
        if mat.name.startswith(("Court line /","Secondary court paint")):
            bs=mat.node_tree.nodes.get("Principled BSDF")
            bs.inputs["Coat Weight"].default_value=cfg["appearance"]["floor_coat_weight"]
            bs.inputs["Coat Roughness"].default_value=cfg["appearance"]["floor_coat_roughness"]
    # Keep actual steel hardware at human scale, attached to the existing door.
    metal=material("Brushed door kick plate",(0.29,0.31,0.30),0.36,0.8)
    cube("Door lower protective kick plate",(-6.8,15.986,0.22),(0.86,0.004,0.28),metal,0.001)
    for mat in bpy.data.materials:
        if mat.name=="Clear lightly diffusing gym glazing":
            bs=mat.node_tree.nodes.get("Principled BSDF");bs.inputs["Roughness"].default_value=0.055
    ledger.update({"photographic_daylight_asset":cfg["appearance"]["daylight_asset"],"background_is_3d_geometry":True,"no_interior_photo_backplate":True})
    return ledger


def build_ball_photographic(cfg,asset_root):
    ball=build_ball_photographic_maple(cfg,asset_root)
    a=cfg["appearance"]
    for mat in ball.data.materials:
        bs=mat.node_tree.nodes.get("Principled BSDF")
        if not bs:continue
        bs.inputs["Specular IOR Level"].default_value=a["ball_specular_ior_level"]
        if bs.inputs["Roughness"].links:
            mapped=bs.inputs["Roughness"].links[0].from_node
            if mapped.type=="MAP_RANGE":
                mapped.inputs["To Min"].default_value=a["ball_roughness_range"][0];mapped.inputs["To Max"].default_value=a["ball_roughness_range"][1]
        for node in mat.node_tree.nodes:
            if node.type=="NORMAL_MAP":node.inputs["Strength"].default_value=a["ball_normal_strength"]
    return ball


def nodes(mat):
    nt = mat.node_tree
    return nt, nt.nodes.get("Principled BSDF")


def mix_rgb(nt, blend, fac, a, b):
    node = nt.nodes.new("ShaderNodeMixRGB")
    node.blend_type = blend
    for slot, value in zip(node.inputs, (fac, a, b)):
        if isinstance(value, bpy.types.NodeSocket):
            nt.links.new(value, slot)
        elif isinstance(value, (int, float)):
            slot.default_value = value
        else:
            slot.default_value = (*value, 1)
    return node.outputs[0]


def map_range(nt, source, from_min, from_max, to_min, to_max):
    node = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(source, node.inputs["Value"])
    for key, value in [("From Min", from_min), ("From Max", from_max), ("To Min", to_min), ("To Max", to_max)]:
        node.inputs[key].default_value = value
    return node.outputs[0]


def world_noise(nt, position, scale, detail=3):
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = detail
    nt.links.new(position, noise.inputs["Vector"])
    return noise.outputs["Fac"]


def painted_block(name, axis, color, a, asset_root, stripe=None):
    """Photographed block relief under satin paint, world-aligned so joints run across wall pieces."""
    folder = Path(asset_root)/a["wall_relief_asset"]
    mat = material(name, color, 0.6)
    nt, bs = nodes(mat)
    position = nt.nodes.new("ShaderNodeNewGeometry").outputs["Position"]
    split = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(position, split.inputs[0])
    tile = nt.nodes.new("ShaderNodeCombineXYZ")
    u = nt.nodes.new("ShaderNodeMath");u.operation = "DIVIDE"
    nt.links.new(split.outputs[axis], u.inputs[0]);u.inputs[1].default_value = a["wall_relief_tile_m"][0]
    v = nt.nodes.new("ShaderNodeMath");v.operation = "DIVIDE"
    nt.links.new(split.outputs["Z"], v.inputs[0]);v.inputs[1].default_value = a["wall_relief_tile_m"][1]
    nt.links.new(u.outputs[0], tile.inputs[0]);nt.links.new(v.outputs[0], tile.inputs[1])
    def texture(suffix):
        image = bpy.data.images.load(str(folder/f"concrete_block_wall_{suffix}_4k.jpg"), check_existing=True)
        image.colorspace_settings.name = "Non-Color"
        node = nt.nodes.new("ShaderNodeTexImage");node.image = image
        nt.links.new(tile.outputs[0], node.inputs["Vector"])
        return node.outputs["Color"]
    height, rough, diffuse = texture("disp"), texture("rough"), texture("diff")
    # Paint hides aggregate colour but not its relief; only a little tone survives.
    tone = map_range(nt, diffuse, 0.02, 0.22, 0.90, 1.04)
    macro = map_range(nt, world_noise(nt, position, 0.55), 0.3, 0.7, 0.90, 1.03)
    grime = map_range(nt, split.outputs["Z"], 0.0, 0.9, 0.80, 1.0)
    shade = nt.nodes.new("ShaderNodeMath");shade.operation = "MULTIPLY"
    nt.links.new(tone, shade.inputs[0]);nt.links.new(macro, shade.inputs[1])
    total = nt.nodes.new("ShaderNodeMath");total.operation = "MULTIPLY"
    nt.links.new(shade.outputs[0], total.inputs[0]);nt.links.new(grime, total.inputs[1])
    combined = nt.nodes.new("ShaderNodeCombineColor")
    for i in range(3):
        nt.links.new(total.outputs[0], combined.inputs[i])
    paint = color
    if stripe:
        low = nt.nodes.new("ShaderNodeMath");low.operation = "GREATER_THAN"
        nt.links.new(split.outputs["Z"], low.inputs[0]);low.inputs[1].default_value = stripe[0]
        high = nt.nodes.new("ShaderNodeMath");high.operation = "LESS_THAN"
        nt.links.new(split.outputs["Z"], high.inputs[0]);high.inputs[1].default_value = stripe[1]
        band = nt.nodes.new("ShaderNodeMath");band.operation = "MULTIPLY"
        nt.links.new(low.outputs[0], band.inputs[0]);nt.links.new(high.outputs[0], band.inputs[1])
        paint = mix_rgb(nt, "MIX", band.outputs[0], color, stripe[2])
    painted = mix_rgb(nt, "MULTIPLY", 1, paint, combined.outputs[0])
    # Paint pools in the joints, so they read darker than the block faces in albedo as well.
    joint = map_range(nt, height, a["wall_joint_height_range"][0], a["wall_joint_height_range"][1], a["wall_joint_shade"], 1.0)
    joint_rgb = nt.nodes.new("ShaderNodeCombineColor")
    for i in range(3):
        nt.links.new(joint, joint_rgb.inputs[i])
    painted = mix_rgb(nt, "MULTIPLY", 1, painted, joint_rgb.outputs[0])
    # Worn ball marks: soft grey rubber smudges at throwing height.
    marks = nt.nodes.new("ShaderNodeTexVoronoi");marks.inputs["Scale"].default_value = 0.8
    nt.links.new(position, marks.inputs["Vector"])
    mark = map_range(nt, marks.outputs["Distance"], 0.035, 0.11, 0.10, 0.0)
    nt.links.new(mix_rgb(nt, "MIX", mark, painted, (0.05, 0.05, 0.05)), bs.inputs["Base Color"])
    nt.links.new(map_range(nt, rough, 0.2, 0.9, 0.42, 0.68), bs.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.9
    bump.inputs["Distance"].default_value = a["wall_relief_depth_m"]
    nt.links.new(height, bump.inputs["Height"]);nt.links.new(bump.outputs["Normal"], bs.inputs["Normal"])
    return mat


def repaint_walls(a, asset_root):
    upper = a["wall_upper_rgb"];lower = a["wall_dado_rgb"]
    gold = a["wall_stripe_rgb"];top = a["wall_dado_height_m"]
    made = {}
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        for slot in ob.material_slots:
            if not slot.material:
                continue
            old = slot.material.name
            for prefix, color, stripe in [("Warm painted blockwork / ", upper, (top, top+a["wall_stripe_height_m"], gold)), ("Washable painted wall dado / ", lower, None)]:
                if old.startswith(prefix):
                    axis = old[len(prefix)]
                    key = prefix+axis
                    if key not in made:
                        made[key] = painted_block(key+" / painted CMU", axis, color, a, asset_root, stripe)
                    slot.material = made[key]
    for mat in list(bpy.data.materials):
        if mat.users == 0:
            bpy.data.materials.remove(mat)


def floor_material(name, a, asset_root, tone):
    folder = Path(asset_root)/a["wood_asset"]
    mat = material(name, (0.4, 0.25, 0.11), 0.34)
    nt, bs = nodes(mat)
    bs.inputs["Coat Weight"].default_value = a["floor_coat_weight"]
    def image(suffix, colour=False):
        data = bpy.data.images.load(str(folder/f"white_maple_veneer_{suffix}.jpg"), check_existing=True)
        if not colour:
            data.colorspace_settings.name = "Non-Color"
        node = nt.nodes.new("ShaderNodeTexImage");node.image = data
        return node.outputs["Color"]
    tint = [v*tone for v in a["floor_tint_rgb"]]
    nt.links.new(mix_rgb(nt, "MULTIPLY", 1, image("diff_8k", True), tint), bs.inputs["Base Color"])
    nt.links.new(map_range(nt, image("rough_4k"), 0, 1, *a["floor_roughness_range"]), bs.inputs["Roughness"])
    position = nt.nodes.new("ShaderNodeNewGeometry").outputs["Position"]
    # Polyurethane wear: traffic dulls the sheen in broad metre-scale patches, dust in small ones.
    broad = map_range(nt, world_noise(nt, position, 0.42, 4), 0.35, 0.68, 0.0, 1.0)
    dust = map_range(nt, world_noise(nt, position, 38, 3), 0.45, 0.72, 0.0, 1.0)
    wear = nt.nodes.new("ShaderNodeMath");wear.operation = "MAXIMUM"
    nt.links.new(broad, wear.inputs[0])
    dust_scale = nt.nodes.new("ShaderNodeMath");dust_scale.operation = "MULTIPLY"
    nt.links.new(dust, dust_scale.inputs[0]);dust_scale.inputs[1].default_value = 0.55
    nt.links.new(dust_scale.outputs[0], wear.inputs[1])
    nt.links.new(map_range(nt, wear.outputs[0], 0, 1, *a["floor_coat_roughness_range"]), bs.inputs["Coat Roughness"])
    normal = nt.nodes.new("ShaderNodeNormalMap");normal.inputs["Strength"].default_value = a["floor_normal_strength"]
    nt.links.new(image("nor_gl_4k"), normal.inputs["Color"]);nt.links.new(normal.outputs["Normal"], bs.inputs["Normal"])
    # A sprung floor is never optically flat: long, low swells bend reflections.
    swell = nt.nodes.new("ShaderNodeBump")
    swell.inputs["Strength"].default_value = 1.0;swell.inputs["Distance"].default_value = a["floor_swell_m"]
    nt.links.new(world_noise(nt, position, 1.6, 2), swell.inputs["Height"])
    nt.links.new(swell.outputs["Normal"], bs.inputs["Coat Normal"])
    return mat


def lengthwise_floor(a, asset_root):
    """Rebuild the floor so the maple strips run baseline to baseline, as on real courts."""
    old = bpy.data.objects["Correct-grain 57 mm strip maple sports floor"]
    mesh_old = old.data
    bpy.data.objects.remove(old, do_unlink=True);bpy.data.meshes.remove(mesh_old)
    for mat in list(bpy.data.materials):
        if mat.users == 0:
            bpy.data.materials.remove(mat)
    rng = random.Random(a["seed"]+61)
    width = a["plank_width_m"];gap = a["plank_joint_width_m"]/2
    verts, faces, uvs, tones, tilts = [], [], [], [], []
    for col in range(math.ceil(18/width)):
        x0, x1 = -9+col*width, min(9, -9+(col+1)*width)
        y0 = -16
        first = a["plank_nominal_length_m"]*rng.uniform(0.15, 1.0)
        while y0 < 16-1e-8:
            y1 = min(16, y0+(first if y0 == -16 else a["plank_nominal_length_m"]*rng.uniform(0.5, 1.35)))
            n = len(verts)
            verts += [(x1-gap, y0+gap, 0), (x1-gap, y1-gap, 0), (x0+gap, y1-gap, 0), (x0+gap, y0+gap, 0)]
            faces.append((n, n+1, n+2, n+3))
            u, v = rng.random(), rng.random();d = rng.choice([1, -1])
            length, across = (y1-y0)-2*gap, (x1-x0)-2*gap
            # The source grain runs along U and one image spans 1 m.
            uvs += [(u, v), (u+d*length, v), (u+d*length, v+d*across), (u, v+d*across)]
            tones.append(rng.randrange(11))
            tilts.append((rng.gauss(0, a["plank_tilt_rad"]), rng.gauss(0, a["plank_tilt_rad"]/3)))
            y0 = y1
    mesh = bpy.data.meshes.new("Lengthwise maple strips")
    mesh.from_pydata(verts, [], faces)
    for i in range(11):
        mesh.materials.append(floor_material(f"Correct-grain sealed maple / tone {i:02d}", a, asset_root, 0.84+i*0.032))
    uv = mesh.uv_layers.new(name="Metric maple UV")
    corner_normals = [None]*len(mesh.loops)
    for poly, tone, tilt in zip(mesh.polygons, tones, tilts):
        poly.material_index = tone
        normal = Vector((tilt[0], tilt[1], 1)).normalized()
        for loop in poly.loop_indices:
            uv.data[loop].uv = uvs[mesh.loops[loop].vertex_index]
            corner_normals[loop] = normal
    mesh.normals_split_custom_set(corner_normals)
    ob = bpy.data.objects.new("Correct-grain 57 mm strip maple sports floor", mesh)
    bpy.context.collection.objects.link(ob)
    return len(faces)


def paint_court(a):
    white = None
    for mat in bpy.data.materials:
        if mat.name.startswith(("Court line /", "Secondary court paint")):
            bs = mat.node_tree.nodes.get("Principled BSDF")
            bs.inputs["Base Color"].default_value = (0.86, 0.86, 0.82, 1)
            bs.inputs["Coat Weight"].default_value = a["floor_coat_weight"]
            bs.inputs["Coat Roughness"].default_value = a["floor_coat_roughness_range"][0]
            white = white or mat
    key = material("Painted free throw lane", a["court_key_rgb"], 0.34)
    bs = key.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Coat Weight"].default_value = a["floor_coat_weight"]
    bs.inputs["Coat Roughness"].default_value = a["floor_coat_roughness_range"][0]
    for sign in [-1, 1]:
        ob = cube("Painted free throw lane", (0, sign*11.1, 0.00015), (4.9, 5.8, 0.0003), key)
        ob.visible_shadow = False
        for dy in [1.75, 2.85, 3.95, 5.05]:
            for x in [-2.6, 2.6]:
                cube("Lane hash mark", (x, sign*(14-dy), 0.0004), (0.3, 0.05, 0.0006), white).visible_shadow = False
    # Rubber transfer where players actually turn: many short strokes, densest near the lanes.
    scuff = bpy.data.materials.get("Subtle rubber sole transfer on polyurethane")
    if scuff:
        scuff.node_tree.nodes["Mix Shader"].inputs[0].default_value = 0.2
        rng = random.Random(a["seed"]+73)
        for i in range(90):
            x, y = rng.uniform(-6.5, 6.5), rng.uniform(-3.5, 14)
            start = rng.random()*math.tau
            ob = arc(f"Shoe sole scuff {i:02d}", (x, y), rng.uniform(0.06, 0.5), rng.uniform(0.002, 0.007), scuff, start, start+rng.uniform(0.25, 1.1))
            for v in ob.data.vertices:
                v.co.z = 0.000025
            ob.visible_shadow = False


def recolour(name, rgb):
    for mat in bpy.data.materials:
        if mat.name.startswith(name):
            mat.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (*rgb, 1)


def capped_tube(name, points, radius, mat):
    ob = tube(name, points, radius, mat)
    ob.data.use_fill_caps = True
    return ob


def label(name, text, location, size, mat, extrude=0.002):
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = text;curve.size = size;curve.align_x = "CENTER";curve.align_y = "CENTER";curve.extrude = extrude
    curve.materials.append(mat)
    ob = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(ob)
    ob.location = location;ob.rotation_euler = (math.pi/2, 0, 0)
    return ob


def emissive(name, rgb, strength):
    mat = material(name, (0.02, 0.02, 0.02), 0.5)
    bs = mat.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Emission Color"].default_value = (*rgb, 1);bs.inputs["Emission Strength"].default_value = strength
    return mat


def place_library_model(asset_root, key, stem, ground_xy=None, rotate_z=0.0, centre=None):
    """Append a registered CC0 model and put it at real size in world coordinates."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(Path(asset_root)/key/f"{stem}_2k.gltf"))
    obs = [o for o in bpy.data.objects if o not in before]
    bpy.context.view_layer.update()
    spin = Matrix.Rotation(rotate_z, 4, "Z")
    roots = [o for o in obs if o.parent is None]
    for ob in roots:
        ob.matrix_world = spin @ ob.matrix_world
    bpy.context.view_layer.update()
    corners = [ob.matrix_world @ Vector(c) for ob in obs if ob.type == "MESH" for c in ob.bound_box]
    low = [min(c[i] for c in corners) for i in range(3)];high = [max(c[i] for c in corners) for i in range(3)]
    if ground_xy:
        shift = Vector((ground_xy[0]-(low[0]+high[0])/2, ground_xy[1]-(low[1]+high[1])/2, -low[2]))
    else:
        shift = Vector(centre)-Vector([(l+h)/2 for l, h in zip(low, high)])
    for ob in roots:
        ob.matrix_world = Matrix.Translation(shift) @ ob.matrix_world
    return obs


def bleacher_wood(a, asset_root):
    """Varnished veneer in world metres, grain along the boards; each row lands on another crop."""
    mat = material("Bleacher varnished oak boards", (0.3, 0.17, 0.07), 0.42)
    nt, bs = nodes(mat)
    bs.inputs["Coat Weight"].default_value = 0.35;bs.inputs["Coat Roughness"].default_value = 0.22
    position = nt.nodes.new("ShaderNodeNewGeometry").outputs["Position"]
    split = nt.nodes.new("ShaderNodeSeparateXYZ");nt.links.new(position, split.inputs[0])
    uv = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(split.outputs["Y"], uv.inputs[0]);nt.links.new(split.outputs["Z"], uv.inputs[1])
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(Path(asset_root)/a["bleacher_wood_asset"]/"oak_veneer_01_diff_8k.jpg"), check_existing=True)
    tex.extension = "REPEAT"
    nt.links.new(uv.outputs[0], tex.inputs["Vector"])
    nt.links.new(mix_rgb(nt, "MULTIPLY", 1, tex.outputs["Color"], a["bleacher_wood_tint_rgb"]), bs.inputs["Base Color"])
    return mat


def folded_bleachers(a, asset_root):
    """Telescopic seating closed against the left wall, clear of the 7.5 m sideline."""
    wood = bleacher_wood(a, asset_root)
    frame = material("Bleacher powder-coated steel", (0.03, 0.035, 0.04), 0.5, 0.3)
    dark = material("Shadowed bleacher interior", (0.012, 0.012, 0.013), 0.8)
    y0, y1 = 2.6, 14.6;front = -7.85;rows = 9;row_h = 0.32
    cube("Closed bleacher body", ((-9+front-0.02)/2, (y0+y1)/2, rows*row_h/2), (front-0.02+9, y1-y0, rows*row_h), dark)
    for i in range(rows):
        z = i*row_h
        cube("Bleacher seat board", (front, (y0+y1)/2, z+row_h*0.56), (0.03, y1-y0, row_h*0.74), wood, 0.004)
        cube("Bleacher riser steel", (front-0.01, (y0+y1)/2, z+row_h*0.1), (0.02, y1-y0, row_h*0.14), frame, 0.002)
    y = y0
    while y <= y1+1e-6:
        cube("Bleacher vertical frame", (front+0.02, y, rows*row_h/2), (0.05, 0.06, rows*row_h), frame, 0.003)
        y += 3.0
    cube("Bleacher end panel", ((-9+front)/2, y0-0.02, rows*row_h/2), (front+9, 0.04, rows*row_h), frame, 0.004)


def banner(name, x, z, width, height, cloth, trim, ink, lines):
    n = 14
    verts = [(x-width/2+width*i/n, 15.97-0.012*math.sin(i*1.9)-0.008*math.sin(i*0.7+j), z+height/2-height*j/n) for j in range(n+1) for i in range(n+1)]
    faces = [(j*(n+1)+i, j*(n+1)+i+1, (j+1)*(n+1)+i+1, (j+1)*(n+1)+i) for j in range(n) for i in range(n)]
    mesh = bpy.data.meshes.new(name);mesh.from_pydata(verts, [], faces);mesh.materials.append(cloth)
    for poly in mesh.polygons:
        poly.use_smooth = True
    ob = bpy.data.objects.new(name, mesh);bpy.context.collection.objects.link(ob)
    cube("Banner hanging rail", (x, 15.965, z+height/2+0.01), (width+0.1, 0.02, 0.025), trim)
    cube("Banner trim", (x, 15.94, z-height/2+0.05), (width, 0.006, 0.05), trim)
    for i, (text, size) in enumerate(lines):
        label(name+" text", text, (x, 15.93, z+height*0.22-i*height*0.3), size, ink, 0.001)


def dress_room(a, asset_root):
    steel = bpy.data.materials["Powder-coated gym support steel"]
    zinc = material("Galvanised conduit", (0.42, 0.43, 0.43), 0.42, 0.9)
    door_x = -6.8
    # Exit sign, closer and switch plate at the door.
    case = material("White sign housing", (0.72, 0.72, 0.68), 0.4)
    cube("Exit sign housing", (door_x, 15.95, 2.46), (0.36, 0.08, 0.18), case, 0.004)
    label("Exit sign", "EXIT", (door_x, 15.905, 2.455), 0.115, emissive("Exit sign LED", (1.0, 0.05, 0.03), 9), 0.001)
    cube("Door closer body", (door_x+0.3, 15.97, 2.1), (0.26, 0.05, 0.06), steel, 0.004)
    # Wall services stay off the camera-to-ball sight line (rear wall x = -6.0): a thin vertical
    # conduit or broom handle there reads as a string the ball hangs from.
    cube("Light switch plate", (-7.45, 15.99, 1.15), (0.09, 0.012, 0.14), case, 0.002)
    capped_tube("Surface conduit", [(-7.45, 15.985, 1.22), (-7.45, 15.985, 2.9)], 0.011, zinc)
    cube("Conduit junction box", (-7.45, 15.975, 2.9), (0.12, 0.05, 0.12), zinc, 0.003)
    capped_tube("Scoreboard conduit", [(-3.35, 15.985, 3.7), (-3.0, 15.985, 3.7), (-3.0, 15.985, 6.8)], 0.011, zinc)
    # Extinguisher in its bracket with a sign above, between the bench and the bin.
    red = material("Extinguisher enamel", (0.40, 0.012, 0.012), 0.28)
    capped_tube("Fire extinguisher", [(-2.95, 15.92, 0.82), (-2.95, 15.92, 1.24)], 0.065, red)
    capped_tube("Extinguisher neck", [(-2.95, 15.92, 1.24), (-2.95, 15.92, 1.31)], 0.018, steel)
    cube("Extinguisher bracket", (-2.95, 15.975, 1.02), (0.05, 0.05, 0.3), steel, 0.002)
    cube("Extinguisher sign", (-2.95, 15.99, 1.62), (0.18, 0.006, 0.26), red, 0.001)
    # Scoreboard off during practice: dark face, faint standby segments, cable from conduit.
    shell = material("Scoreboard shell", (0.012, 0.013, 0.016), 0.42, 0.2)
    cube("Scoreboard", (-4.5, 15.93, 3.72), (2.3, 0.14, 1.04), shell, 0.012)
    amber = emissive("Scoreboard standby segments", (1.0, 0.16, 0.02), 1.6)
    white_ink = emissive("Scoreboard painted captions", (0.9, 0.9, 0.85), 0.5)
    label("Scoreboard clock", "00:00", (-4.5, 15.855, 3.84), 0.3, amber, 0.001)
    label("Scoreboard home", "HOME", (-5.28, 15.855, 3.56), 0.09, white_ink, 0.001)
    label("Scoreboard guest", "GUEST", (-3.72, 15.855, 3.56), 0.09, white_ink, 0.001)
    label("Scoreboard home points", "00", (-5.28, 15.855, 3.38), 0.2, amber, 0.001)
    label("Scoreboard guest points", "00", (-3.72, 15.855, 3.38), 0.2, amber, 0.001)
    # Club banners above the door; text is generic.
    cloth = material("Banner felt", (0.03, 0.07, 0.19), 0.85)
    trim = material("Banner gold trim", (0.62, 0.42, 0.10), 0.5)
    ink = material("Banner lettering", (0.70, 0.68, 0.60), 0.8)
    banner("League banner", -7.55, 3.75, 0.9, 1.25, cloth, trim, ink, [("LEAGUE", 0.14), ("WINNERS", 0.13), ("2019", 0.16)])
    # Bench clutter and floor kit away from the ball path.
    towel = material("Grey cotton towel", (0.45, 0.46, 0.46), 0.9)
    bag = material("Navy duffel nylon", (0.016, 0.03, 0.07), 0.55)
    bottle = material("Blue squeeze bottle", (0.03, 0.2, 0.42), 0.22)
    cube("Towel on bench", (-5.1, 15.5, 0.462), (0.55, 0.3, 0.018), towel, 0.007)
    cube("Towel fold over bench edge", (-5.1, 15.345, 0.40), (0.55, 0.012, 0.13), towel, 0.004)
    for dx, dy in [(-3.6, 15.42), (-3.42, 15.52)]:
        capped_tube("Squeeze bottle", [(dx, dy, 0.45), (dx, dy, 0.63)], 0.036, bottle)
        capped_tube("Squeeze bottle cap", [(dx, dy, 0.63), (dx, dy, 0.67)], 0.019, steel)
    cube("Duffel bag under bench", (-4.45, 15.5, 0.135), (0.68, 0.3, 0.27), bag, 0.05)
    capped_tube("Duffel strap", [(-4.7, 15.36, 0.27), (-4.45, 15.32, 0.34), (-4.2, 15.36, 0.27)], 0.012, steel)
    bin_grey = material("Grey moulded waste bin", (0.10, 0.11, 0.12), 0.55)
    capped_tube("Waste bin", [(-2.55, 15.62, 0.0), (-2.55, 15.62, 0.62)], 0.22, bin_grey)
    capped_tube("Waste bin rim", [(-2.55, 15.62, 0.62), (-2.55, 15.62, 0.65)], 0.235, bin_grey)
    place_library_model(asset_root, a["prop_broom_asset"], "plastic_broom", ground_xy=(-7.72, 15.72), rotate_z=math.radians(a["prop_broom_yaw_deg"]))
    place_library_model(asset_root, a["prop_clock_asset"], "wall_clock", centre=(-2.4, 15.965, 3.6), rotate_z=math.radians(a["prop_clock_yaw_deg"]))
    folded_bleachers(a, asset_root)


def gym_lived_in(cfg, asset_root):
    a = cfg["appearance"]
    ledger = gym_photographic(cfg, asset_root)
    ledger["maple_plank_count"] = lengthwise_floor(a, asset_root)
    repaint_walls(a, asset_root)
    paint_court(a)
    recolour("Continuous matt vinyl basket safety mat", a["basket_pad_rgb"])
    recolour("Painted steel gym door", a["door_rgb"])
    dress_room(a, asset_root)
    # Light reaches the room through glazing without tracing refractive caustics.
    for ob in bpy.data.objects:
        if ob.type == "MESH" and ob.material_slots and ob.material_slots[0].material and ob.material_slots[0].material.name == "Clear lightly diffusing gym glazing":
            ob.visible_shadow = False
    ledger.update({"floor_strip_direction":"lengthwise, parallel to the 28 m sideline","wall_relief_asset":a["wall_relief_asset"],
        "closed_bleacher_depth_m":1.15,"distractor_policy":"no other balls and no other orange objects added"})
    return ledger


def build_ball_lived_in(cfg, asset_root):
    ball = build_ball_photographic(cfg, asset_root)
    a = cfg["appearance"]
    for mat in ball.data.materials:
        nt, bs = nodes(mat)
        if not bs or not bs.inputs["Base Color"].links:
            continue
        source = bs.inputs["Base Color"].links[0].from_socket
        position = nt.nodes.new("ShaderNodeTexCoord")
        # Handled-leather grime is uneven: palm oil and floor dust darken patches of the cover.
        wear = map_range(nt, world_noise(nt, position.outputs["Object"], 26, 4), 0.34, 0.66, 0.0, 1.0)
        tinted = mix_rgb(nt, "MULTIPLY", 1, source, a["ball_cover_tint_rgb"])
        nt.links.new(mix_rgb(nt, "MULTIPLY", wear, tinted, a["ball_grime_rgb"]), bs.inputs["Base Color"])
    ball.cycles.use_motion_blur = True
    ball.cycles.motion_steps = cfg["render"]["ball_motion_steps"]
    return ball


def lighting(cfg, asset_root):
    a = cfg["appearance"]
    scene = bpy.context.scene
    world = bpy.data.worlds.new("Photographed daylight outside real windows")
    world.use_nodes = True;scene.world = world
    nt = world.node_tree;nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld");bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = a["daylight_strength"]
    tex = nt.nodes.new("ShaderNodeTexEnvironment")
    tex.image = bpy.data.images.load(str(Path(asset_root)/a["daylight_asset"]/"residential_garden_4k.hdr"), check_existing=True)
    coord = nt.nodes.new("ShaderNodeTexCoord");mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value[2] = math.radians(a["daylight_rotation_deg"])
    nt.links.new(coord.outputs[a["daylight_coordinates"]], mapping.inputs["Vector"]);nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bg.inputs["Color"]);nt.links.new(bg.outputs[0], out.inputs[0])
    powers = a["light_energy_watts"]
    def area(name, xyz, target, power, size, size_y, color):
        if power <= 0:
            return None
        data = bpy.data.lights.new(name, "AREA");data.energy = power;data.shape = "RECTANGLE";data.size = size;data.size_y = size_y;data.color = color
        ob = bpy.data.objects.new(name, data);bpy.context.collection.objects.link(ob);ob.location = xyz;look_at(ob, target)
        ob.visible_camera = False;ob.visible_glossy = False
        return ob
    for y in [-12, -6, 0, 6, 12]:
        area("Overcast sky through left window", (-9.25, y, 4.5), (0, y, 4.5), powers["left_window"], 3.8, 2.5, (0.93, 0.96, 1.0))
        area("Overcast sky through right window", (9.25, y, 4.5), (0, y, 4.5), powers["right_fill"], 3.8, 2.5, (0.93, 0.96, 1.0))
    sun = a["sun"]
    if sun["strength"] > 0:
        data = bpy.data.lights.new("Low sun", "SUN");data.energy = sun["strength"];data.angle = math.radians(sun["angular_diameter_deg"]);data.color = sun["rgb"]
        ob = bpy.data.objects.new("Low sun", data);bpy.context.collection.objects.link(ob)
        el, yaw = math.radians(sun["elevation_deg"]), math.radians(sun["yaw_deg"])
        ob.location = (0, 0, 40)
        look_at(ob, ob.location+Vector((math.cos(el)*math.cos(yaw), math.cos(el)*math.sin(yaw), -math.sin(el))))
    # Hanging LED high-bays: chains, housing and an emitting diffuser that shows in the floor.
    housing = material("High-bay housing", (0.05, 0.05, 0.055), 0.5, 0.4)
    width, depth = 1.2, 0.3
    glow = emissive("High-bay diffuser", (1.0, 0.95, 0.87), powers["ceiling"]/(width*depth*math.pi))
    # Remove the photographic-layer fixtures; this layer builds the denser, lower layout.
    for ob in list(bpy.data.objects):
        if ob.name.startswith("Suspended linear LED sports light"):
            bpy.data.objects.remove(ob, do_unlink=True)
    for y in [-12, -6, 0, 6, 12]:
        for x in [-5.0, 0.0, 5.0]:
            cube("High-bay housing", (x, y, 6.02), (width+0.05, depth+0.05, 0.07), housing, 0.004)
            cube("High-bay diffuser", (x, y, 5.98), (width, depth, 0.012), glow)
            for dx in [-0.5, 0.5]:
                tube("High-bay chain", [(x+dx, y, 6.05), (x+dx, y, 6.8)], 0.004, housing)
            area("High-bay downlight", (x, y, 5.96), (x, y, 0), powers["ceiling"], width, depth, (1.0, 0.95, 0.87))


def camera_response(cfg):
    """Lens glow, falloff and dispersion in scene-linear light, before the view transform."""
    a = cfg["appearance"]["lens_response"]
    scene = bpy.context.scene
    scene.use_nodes = True
    nt = scene.node_tree;nt.nodes.clear()
    layers = nt.nodes.new("CompositorNodeRLayers")
    glare = nt.nodes.new("CompositorNodeGlare");glare.glare_type = "FOG_GLOW";glare.quality = "HIGH"
    glare.threshold = a["glow_threshold"];glare.size = a["glow_size"];glare.mix = a["glow_mix"]
    lens = nt.nodes.new("CompositorNodeLensdist");lens.inputs["Dispersion"].default_value = a["dispersion"]
    mask = nt.nodes.new("CompositorNodeEllipseMask");mask.width = 1.35;mask.height = 1.5
    blur = nt.nodes.new("CompositorNodeBlur");blur.size_x = blur.size_y = 240;blur.filter_type = "GAUSS"
    falloff = nt.nodes.new("CompositorNodeMapRange")
    falloff.inputs["To Min"].default_value = a["vignette_edge"];falloff.inputs["To Max"].default_value = 1.0
    falloff.inputs["From Min"].default_value = 0.0;falloff.inputs["From Max"].default_value = 1.0
    mult = nt.nodes.new("CompositorNodeMixRGB");mult.blend_type = "MULTIPLY";mult.inputs[0].default_value = 1
    out = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(layers.outputs["Image"], glare.inputs["Image"])
    nt.links.new(glare.outputs["Image"], lens.inputs["Image"])
    nt.links.new(mask.outputs[0], blur.inputs["Image"])
    nt.links.new(blur.outputs[0], falloff.inputs[0])
    nt.links.new(lens.outputs["Image"], mult.inputs[1]);nt.links.new(falloff.outputs[0], mult.inputs[2])
    nt.links.new(mult.outputs[0], out.inputs["Image"])


def film_response(path, frame, cfg):
    """Deterministic per-frame sensor noise on the written PNG, stronger in the shadows."""
    import numpy as np
    r = cfg["render"]
    sigma = r["film_grain_sigma_8bit"]/255.0
    image = bpy.data.images.load(str(path))
    width, height = image.size
    data = np.empty(width*height*4, dtype=np.float32)
    image.pixels.foreach_get(data)
    data = data.reshape(height, width, 4)
    rng = np.random.default_rng(cfg["appearance"]["seed"]*1000+frame)
    noise = rng.normal(0, 1, (height, width, 3)).astype(np.float32)
    # Demosaicing correlates neighbouring pixels; luma noise dominates chroma noise.
    noise = (noise*2+np.roll(noise, 1, 0)+np.roll(noise, 1, 1)+np.roll(noise, -1, 0)+np.roll(noise, -1, 1))/np.sqrt(8)
    luma = noise.mean(axis=2, keepdims=True)
    grain = luma*0.85+noise*0.3
    level = data[:, :, :3].mean(axis=2, keepdims=True)
    data[:, :, :3] = np.clip(data[:, :, :3]+grain*sigma*(1.35-level), 0, 1)
    image.pixels.foreach_set(data.ravel())
    image.filepath_raw = str(path);image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def remove_prefixes(prefixes):
    for ob in list(bpy.data.objects):
        if ob.name.startswith(tuple(prefixes)):
            bpy.data.objects.remove(ob, do_unlink=True)


def mesh_object(name, vertices, faces, mat):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    mesh.materials.append(mat)
    for face in mesh.polygons:
        face.use_smooth = True
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(ob)
    return ob


def cloth_material(name, rgb, weave_scale=1550):
    mat = material(name, rgb, 0.86)
    nt, bs = nodes(mat)
    bs.inputs["Sheen Weight"].default_value = 0.22
    position = nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    broad = world_noise(nt, position, 24, 2)
    tone = map_range(nt, broad, 0, 1, 0.92, 1.04)
    nt.links.new(mix_rgb(nt, "MULTIPLY", 1, rgb, tone), bs.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.55
    bump.inputs["Distance"].default_value = 0.00032
    nt.links.new(world_noise(nt, position, weave_scale*0.62, 2), bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bs.inputs["Normal"])
    return mat


def draped_bench_towel(a):
    """A single continuous sheet follows the OUTSIDE of the rounded front seat edge."""
    remove_prefixes(["Towel on bench", "Towel fold over bench edge"])
    spec = a["bench_towel"]
    seat = [o for o in bpy.data.objects if o.name.startswith("Bench seat ash slat") and o.location.x < 0]
    bpy.context.view_layer.update()
    points = [o.matrix_world @ v.co for o in seat for v in o.data.vertices]
    front = min(v.y for v in points)
    top = max(v.z for v in points)
    bevel = 0.004
    half = spec["thickness_m"]/2
    clearance = spec["surface_clearance_m"]
    # Concentric offset of the seat's 4 mm round-over. Its underside stays outside the seat.
    radius = bevel+half+clearance
    centre_y, centre_z = front+bevel, top-bevel
    path = []
    for j in range(49):
        t = j/48
        path.append((spec["rear_y_m"]*(1-t)+centre_y*t, top+half+clearance, "top", t))
    for j in range(1,17):
        t = j/16
        angle = t*math.pi/2
        path.append((centre_y-radius*math.sin(angle), centre_z+radius*math.cos(angle), "bend", t))
    for j in range(1,41):
        t = j/40
        path.append((centre_y-radius-0.006*t*t, centre_z-spec["hanging_length_m"]*t, "hang", t))
    nx = 72
    vertices = []
    for y,z,part,t in path:
        for i in range(nx+1):
            u = i/nx
            x = spec["center_x_m"]+spec["width_m"]*(u-0.5)
            # Top folds rise away from the wood; hanging wrinkles move out from the bench.
            if part == "top":
                wave = 0.0033*math.sin(4.2*math.pi*u+1.3*t)**2*math.sin(math.pi*t)**2
                vertices.append((x+0.0015*math.sin(math.pi*t)*math.sin(9*u), y, z+wave))
            elif part == "hang":
                wrinkle = 0.013*t*math.sin(5.6*math.pi*u+0.7*t)**2
                hem = 0.009*t*t*math.sin(5*u+0.4)
                vertices.append((x+0.002*t*math.sin(7*u), y-wrinkle, z+hem))
            else:
                vertices.append((x,y,z))
    faces = []
    for j in range(len(path)-1):
        for i in range(nx):
            k=j*(nx+1)+i
            faces.append((k,k+nx+1,k+nx+2,k+1))
    cotton = cloth_material("Off-white looped cotton towel", (0.58,0.565,0.53))
    band = cloth_material("Woven grey-blue towel border", (0.15,0.19,0.21))
    ob=mesh_object("Continuous towel draped outside bench edge",vertices,faces,cotton)
    ob.data.materials.append(band)
    for face in ob.data.polygons:
        row=face.index//nx
        if path[row][2]=="hang" and 0.79<path[row][3]<0.86:
            face.material_index=1
    solid=ob.modifiers.new("Measured cotton thickness","SOLIDIFY")
    solid.thickness=spec["thickness_m"];solid.offset=0;solid.use_even_offset=True
    ob["bench_contact_prop"]=True
    ob["seat_front_y_m"]=front
    ob["seat_top_z_m"]=top
    ob["minimum_designed_clearance_m"]=clearance
    hem_points=vertices[-(nx+1):]
    tube("Towel stitched bottom hem",hem_points,0.0006,cotton)
    return {"bench_towel_surface":"continuous rounded-edge drape",
            "bench_towel_thickness_m":spec["thickness_m"],"bench_front_y_m":front,
            "bench_seat_top_m":top,"towel_minimum_designed_clearance_m":clearance}


def photographic_timber(a,asset_root,name,axis="X",tone=1.0):
    mat=material(name,(0.3,0.2,0.10),0.46)
    nt,bs=nodes(mat)
    bs.inputs["Coat Weight"].default_value=0.23
    bs.inputs["Coat Roughness"].default_value=0.30
    position=nt.nodes.new("ShaderNodeNewGeometry").outputs["Position"]
    sep=nt.nodes.new("ShaderNodeSeparateXYZ");nt.links.new(position,sep.inputs[0])
    uv=nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(sep.outputs[axis],uv.inputs["Y" if axis=="Y" else "X"])
    across=nt.nodes.new("ShaderNodeMath");across.operation="ADD"
    nt.links.new(sep.outputs["Y" if axis=="X" else "X"],across.inputs[0])
    nt.links.new(sep.outputs["Z"],across.inputs[1]);nt.links.new(across.outputs[0],uv.inputs["X" if axis=="Y" else "Y"])
    tex=nt.nodes.new("ShaderNodeTexImage")
    wood_key = a["bleacher_wood_asset"] if axis=="Y" else a["wood_asset"]
    texture_name = "oak_veneer_01_diff_8k.jpg" if axis=="Y" else "white_maple_veneer_diff_8k.jpg"
    tex.image=bpy.data.images.load(str(Path(asset_root)/wood_key/texture_name),check_existing=True)
    nt.links.new(uv.outputs[0],tex.inputs["Vector"])
    tint=[v*tone for v in a["furniture_wood_tint_rgb"]]
    nt.links.new(mix_rgb(nt,"MULTIPLY",1,tex.outputs["Color"],tint),bs.inputs["Base Color"])
    nt.links.new(map_range(nt,world_noise(nt,position,8,3),0,1,0.38,0.53),bs.inputs["Roughness"])
    bump=nt.nodes.new("ShaderNodeBump");bump.inputs["Strength"].default_value=0.12;bump.inputs["Distance"].default_value=0.0001
    nt.links.new(tex.outputs["Color"],bump.inputs["Height"]);nt.links.new(bump.outputs["Normal"],bs.inputs["Normal"])
    return mat


def bench_and_bleacher_details(a,asset_root):
    woods=[photographic_timber(a,asset_root,"Worn clear-finished bench maple "+str(i),tone=0.93+i*0.035) for i in range(5)]
    boards=[o for o in bpy.data.objects if o.name.startswith(("Bench seat ash slat","Bench backrest ash board"))]
    for i,ob in enumerate(boards):
        ob.data.materials.clear();ob.data.materials.append(woods[i%5])
    metal=material("Recessed zinc furniture fixings",(0.21,0.23,0.24),0.38,0.78)
    for bx in [-4.4,4.5]:
        for dx in [-1,1]:
            for z in [0.68,0.80]:
                bpy.ops.mesh.primitive_cylinder_add(vertices=16,radius=0.0045,depth=0.002,location=(bx+dx,15.642,z),rotation=(math.pi/2,0,0))
                bolt=bpy.context.object;bolt.name="Recessed bench backrest fastener";bolt.data.materials.append(metal)
            for y in [15.37,15.494,15.618]:
                bpy.ops.mesh.primitive_cylinder_add(vertices=16,radius=0.0045,depth=0.001,location=(bx+dx,y,0.4501))
                bolt=bpy.context.object;bolt.name="Flush bench seat fixing";bolt.data.materials.append(metal)
    # Break the implausible single 12 m boards into manufactured sections with small end joints.
    remove_prefixes(["Bleacher seat board"])
    bleacher_woods=[photographic_timber(a,asset_root,"Sectioned bleacher maple "+str(i),axis="Y",tone=0.80+i*0.035) for i in range(6)]
    for row in range(9):
        z=row*0.32+0.32*0.56
        for section in range(8):
            ob=cube("Closed bleacher timber fascia section",(-7.85,2.6+(section+0.5)*1.5,z),(0.030,1.497,0.2368),bleacher_woods[(row*3+section)%6],0.0018)
        # A thin horizontal timber lip makes the collapsed seating mechanism legible.
        cube("Closed bleacher seat edge",(-7.825,8.6,z+0.124),(0.065,12.0,0.027),bleacher_woods[row%6],0.0025)
    frame=bpy.data.materials.get("Bleacher powder-coated steel")
    if frame:
        nodes(frame)[1].inputs["Base Color"].default_value=(0.048,0.052,0.055,1)
        nodes(frame)[1].inputs["Metallic"].default_value=0.12


def small_props():
    remove_prefixes(["Waste bin","Duffel bag under bench","Duffel strap"])
    mat=material("Soft navy woven duffel",(0.023,0.036,0.060),0.78)
    nt,bs=nodes(mat)
    coord=nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    bump=nt.nodes.new("ShaderNodeBump");bump.inputs["Strength"].default_value=0.17;bump.inputs["Distance"].default_value=0.00014
    nt.links.new(world_noise(nt,coord,750,2),bump.inputs["Height"]);nt.links.new(bump.outputs["Normal"],bs.inputs["Normal"])
    vertices=[];faces=[];n=48
    rings=[(-0.34,0.03),(-0.332,0.42),(-0.30,0.84),(-0.24,1),(0.24,1),(0.30,0.84),(0.332,0.42),(0.34,0.03)]
    for x,r in rings:
        for j in range(n):
            t=math.tau*j/n
            ripple=1-0.018*math.sin(j*1.7+x*24)**2
            vertices.append((-4.45+x,15.50+0.155*r*math.cos(t)*ripple,0.13+0.13*r*math.sin(t)*ripple))
    for i in range(len(rings)-1):
        for j in range(n):faces.append((i*n+j,i*n+(j+1)%n,(i+1)*n+(j+1)%n,(i+1)*n+j))
    faces += [tuple(reversed(range(n))),tuple((len(rings)-1)*n+j for j in range(n))]
    mesh_object("Soft duffel body resting below bench",vertices,faces,mat)
    strap=cloth_material("Black woven duffel straps",(0.016,0.020,0.025),1000)
    for y in [15.365,15.62]:
        verts=[]
        for i in range(41):
            t=i/40
            x=-4.45-0.19+0.38*t
            z=0.19+0.145*math.sin(math.pi*t)
            verts += [(x,y-0.012,z),(x,y+0.012,z)]
        ob=mesh_object("Flat woven duffel carry handle",verts,[(2*i,2*i+1,2*i+3,2*i+2) for i in range(40)],strap)
        mod=ob.modifiers.new("Webbing thickness","SOLIDIFY");mod.thickness=0.0015
    tube("Duffel top zipper",[(-4.72+i*0.0135,15.50,0.261+0.002*math.sin(i*.3)) for i in range(41)],0.0014,strap)
    # Open, tapered moulded bin with a rolled lip and a visible inner wall.
    plastic=material("Matte moulded grey bin",(0.075,0.086,0.09),0.63)
    profile=[(0.170,0),(0.173,0.020),(0.217,0.60),(0.220,0.625),(0.214,0.635),(0.208,0.625),(0.205,0.60),(0.160,0.020),(0.001,0.020),(0.001,0)]
    n=96;vertices=[];faces=[]
    for radius,z in profile:
        for j in range(n):
            t=math.tau*j/n
            vertices.append((-2.55+radius*math.cos(t),15.62+radius*math.sin(t),z))
    for i in range(len(profile)):
        k=(i+1)%len(profile)
        for j in range(n):faces.append((i*n+j,i*n+(j+1)%n,k*n+(j+1)%n,k*n+j))
    mesh_object("Open tapered waste bin",vertices,faces,plastic)


def scoreboard_segments():
    remove_prefixes(["Scoreboard clock","Scoreboard home points","Scoreboard guest points"])
    lit=material("Amber LED seven-segment lenses",(0.26,0.065,0.012),0.46)
    bs=nodes(lit)[1];bs.inputs["Emission Color"].default_value=(1,0.20,0.025,1);bs.inputs["Emission Strength"].default_value=0.38
    off=material("Unlit dark LED segments",(0.023,0.018,0.015),0.5)
    # Each numeral is actual segmented display geometry, rather than extruded font lettering.
    def digit(cx,cz,h):
        w=h*.52;th=h*.075
        pieces=[(0,h*.46,w-th,th),(-w*.5,h*.23,th,h*.40),(w*.5,h*.23,th,h*.40),
                (0,0,w-th,th),(-w*.5,-h*.23,th,h*.40),(w*.5,-h*.23,th,h*.40),(0,-h*.46,w-th,th)]
        for k,(dx,dz,sx,sz) in enumerate(pieces):
            cube("Scoreboard LED segment",(cx+dx,15.854,cz+dz),(sx,.002,sz),off if k==3 else lit,min(th*.25,.003))
    for x in [-4.81,-4.62,-4.38,-4.19]:digit(x,3.84,.27)
    for z in [3.80,3.88]:cube("Scoreboard LED colon",(-4.50,15.854,z),(.021,.002,.021),lit,.003)
    for centre in [-5.28,-3.72]:
        for x in [centre-.065,centre+.065]:digit(x,3.38,.18)
    captions=bpy.data.materials.get("Scoreboard painted captions")
    if captions:
        nodes(captions)[1].inputs["Emission Strength"].default_value=0
        nodes(captions)[1].inputs["Base Color"].default_value=(0.52,0.53,0.50,1)


def unify_court_finish(a):
    for mat in bpy.data.materials:
        if not mat.name.startswith(("Court line /","Secondary court paint","Painted free throw lane")):continue
        nt,bs=nodes(mat)
        bs.inputs["Coat Weight"].default_value=a["floor_coat_weight"]
        position=nt.nodes.new("ShaderNodeNewGeometry").outputs["Position"]
        rough=map_range(nt,world_noise(nt,position,.42,4),.35,.68,*a["floor_coat_roughness_range"])
        nt.links.new(rough,bs.inputs["Coat Roughness"])
        # The same thin clear finish crosses painted and unpainted floor.
        bump=nt.nodes.new("ShaderNodeBump");bump.inputs["Strength"].default_value=1
        bump.inputs["Distance"].default_value=a["floor_swell_m"]
        nt.links.new(world_noise(nt,position,1.6,2),bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"],bs.inputs["Coat Normal"])


def gym_documentary(cfg,asset_root):
    ledger=gym_lived_in(cfg,asset_root)
    a=cfg["appearance"]
    if not a["basket_wall_pad_enabled"]:
        remove_prefixes(["Thin basket wall safety mat","Flush vinyl welded seam"])
        ledger["local_basket_safety_mat_dimensions_m"]=None
    ledger["basket_wall_pad_present"]=a["basket_wall_pad_enabled"]
    if a.get("bench_props_enabled",True):
        ledger.update(draped_bench_towel(a))
    bench_and_bleacher_details(a,asset_root)
    small_props()
    if not a.get("bench_props_enabled",True):
        remove_prefixes(["Towel on bench","Towel fold over bench edge","Continuous towel draped outside bench edge",
                         "Towel stitched bottom hem","Squeeze bottle","Duffel bag under bench","Duffel strap",
                         "Soft duffel body resting below bench","Flat woven duffel carry handle","Duffel top zipper"])
    if not a.get("wall_extinguisher_enabled",True):
        remove_prefixes(["Fire extinguisher","Extinguisher"])
    ledger["bench_props_present"]=a.get("bench_props_enabled",True)
    ledger["wall_extinguisher_present"]=a.get("wall_extinguisher_enabled",True)
    scoreboard_segments()
    unify_court_finish(a)
    ledger.update({"appearance_revision":"restrained real-scale materials and resolved bench contact",
                   "freestanding_basketball_stand":False,"basket_mount":"existing suspended/wall-supported",
                   "closed_bleacher_fascia_section_length_m":1.497,
                   "static_cloth_method":"authored continuous offset surface" if a.get("bench_props_enabled",True) else "no cloth; bench props removed by user"})
    return ledger


def manufactured_box(name, position, size, mat, radius=0.002):
    ob = cube(name, position, size, mat, radius)
    if radius:
        ob.modifiers[0].segments = 4
        for polygon in ob.data.polygons:
            polygon.use_smooth = True
        ob.modifiers[0].harden_normals = True
    return ob


def capped_pipe(name, points, radius, mat):
    ob = tube(name, points, radius, mat)
    ob.data.bevel_resolution = 4
    ob.data.use_fill_caps = True
    return ob


def coated_surface(name, colour, roughness, micro_distance, metallic=0):
    mat = material(name, colour, roughness, metallic)
    nt, bs = nodes(mat)
    position = nt.nodes.new("ShaderNodeNewGeometry").outputs["Position"]
    tint = map_range(nt, world_noise(nt, position, 7, 2), .2, .8, .91, 1.04)
    nt.links.new(mix_rgb(nt, "MULTIPLY", 1, colour, tint), bs.inputs["Base Color"])
    nt.links.new(map_range(nt, world_noise(nt, position, 85, 2), .2, .8,
                          roughness-.055, roughness+.055), bs.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .18
    bump.inputs["Distance"].default_value = micro_distance
    nt.links.new(world_noise(nt, position, 1800, 2), bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bs.inputs["Normal"])
    return mat


def bench_maple(a, asset_root, index):
    mat = material("Gym bench satin maple %02d" % index, (.32,.21,.12), .43)
    nt, bs = nodes(mat)
    bs.inputs["Coat Weight"].default_value = .24
    bs.inputs["Coat Roughness"].default_value = .32
    folder = Path(asset_root)/a["wood_asset"]
    def tex(suffix, colour=False):
        image = bpy.data.images.load(str(folder/("white_maple_veneer_"+suffix+".jpg")), check_existing=True)
        if not colour:
            image.colorspace_settings.name = "Non-Color"
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = image
        return node.outputs["Color"]
    tint = [v*(.92+index*.024) for v in a["furniture_wood_tint_rgb"]]
    nt.links.new(mix_rgb(nt,"MULTIPLY",1,tex("diff_8k",True),tint), bs.inputs["Base Color"])
    nt.links.new(map_range(nt,tex("rough_4k"),0,1,.37,.54),bs.inputs["Roughness"])
    normal = nt.nodes.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = .11
    nt.links.new(tex("nor_gl_4k"),normal.inputs["Color"])
    nt.links.new(normal.outputs["Normal"],bs.inputs["Normal"])
    return mat


def board_uv(ob, offset, vertical=False):
    # One source image represents one metre. Adjacent slats sample different wood.
    uv = ob.data.uv_layers.active or ob.data.uv_layers.new(name="Metric furniture maple")
    for face in ob.data.polygons:
        for loop in face.loop_indices:
            p = ob.data.vertices[ob.data.loops[loop].vertex_index].co
            across = p.z if vertical or abs(face.normal.y)>.5 else p.y
            if abs(face.normal.x)>.5:
                uv.data[loop].uv = (offset+p.y, offset*.71+p.z)
            else:
                uv.data[loop].uv = (p.x+offset, across+offset*.71)


def bolt(name, position, direction, metal, rubber=None):
    # 9 mm domed head, shallow washer, and recessed slot, all at manufacturing scale.
    rotation = Vector(direction).to_track_quat("Z","Y")
    def disk(label, centre, radius, depth, mat):
        bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=radius,depth=depth,location=centre)
        ob=bpy.context.object;ob.name=label;ob.rotation_mode="QUATERNION";ob.rotation_quaternion=rotation
        ob.data.materials.append(mat)
        mod=ob.modifiers.new("Rounded pressed fixing","BEVEL");mod.width=.0006;mod.segments=3
        ob.modifiers.new("Fixing normal","WEIGHTED_NORMAL")
        return ob
    disk(name+" washer",position,.006,.0009,metal)
    disk(name+" head",Vector(position)+Vector(direction)*.0008,.0045,.0015,metal)


def gym_benches(a, asset_root):
    remove_prefixes(["Bench ","Recessed bench","Flush bench"])
    spec=a["furniture"]["bench"]
    steel=coated_surface("Gym bench powder-coated tubular steel",(.024,.031,.034),.48,.00006)
    rubber=coated_surface("Gym bench non-marking rubber feet",(.014,.017,.018),.76,.00014)
    metal=material("Gym bench satin zinc fasteners",(.24,.25,.25),.38,.78)
    woods=[bench_maple(a,asset_root,i) for i in range(8)]
    length=spec["length_m"];centre_y=spec["centre_y_m"];seat_top=spec["seat_top_m"]
    support=length/2-.29
    support_top=seat_top-.032-.018
    for bi,bx in enumerate(spec["centres_x_m"]):
        for side in [-1,1]:
            x=bx+side*support
            # A continuous bent side frame, with radiused upper corners.
            yz=[(-.247,.027),(-.196,support_top-.045)]
            for j in range(9):
                t=j/8*math.pi/2
                yz.append((-.151-.045*math.cos(t),support_top-.045+.045*math.sin(t)))
            yz.append((.151,support_top))
            for j in range(1,9):
                t=j/8*math.pi/2
                yz.append((.151+.045*math.sin(t),support_top-.045+.045*math.cos(t)))
            yz.append((.247,.027))
            capped_pipe("Gym bench continuous bent side frame",
                        [(x,centre_y+y,z) for y,z in yz],.018,steel)
            for yy in [-.247,.247]:
                foot=manufactured_box("Gym bench rubber foot touching floor",
                      (x,centre_y+yy,.011),(.064,.065,.022),rubber,.007)
                foot["ground_contact_furniture"]=True
                foot["bench_index"]=bi
            # Raked back support is welded to the rear frame, not hovering behind it.
            capped_pipe("Gym bench inclined back upright",
                        [(x,centre_y+.184,.36),(x,centre_y+.195,.48),
                         (x,centre_y+.276,.883)],.016,steel)
            manufactured_box("Gym bench seat support strap",
                             (x,centre_y,seat_top-.037),(.048,.405,.010),steel,.002)
            for yy in [-.15,.15]:
                bpy.ops.mesh.primitive_torus_add(major_segments=24,minor_segments=8,
                    location=(x,centre_y+yy,support_top),major_radius=.018,minor_radius=.0012,
                    rotation=(0,math.pi/2,0))
                weld=bpy.context.object;weld.name="Gym bench small frame weld";weld.data.materials.append(steel)
        for yy in [-.15,.15]:
            capped_pipe("Gym bench longitudinal underseat rail",
                        [(bx-support,centre_y+yy,support_top),(bx+support,centre_y+yy,support_top)],
                        .015,steel)
        for j in range(4):
            y=centre_y-.15+j*.10
            ob=manufactured_box("Gym bench rounded solid maple seat slat",
                    (bx,y,seat_top-.016),(length,.090,.032),woods[(bi*3+j)%8],.0035)
            board_uv(ob,bi*1.33+j*.263)
            ob["bench_index"]=bi;ob["wood_grain_axis"]="X";ob["seat_top_m"]=seat_top
            for side in [-1,1]:
                bolt("Gym bench seat recessed fixing",(bx+side*support,y,seat_top-.0005),(0,0,1),metal)
        rake=-math.atan(.20)
        for j in range(3):
            z=.636+j*.114
            y=centre_y+.195+(z-.48)*.20-.014
            ob=manufactured_box("Gym bench rounded raked maple back slat",
                    (bx,y,z),(length,.030,.098),woods[(bi*2+j+4)%8],.0035)
            board_uv(ob,.18+bi*.83+j*.197,vertical=True)
            ob.rotation_euler.x=rake
            ob["bench_index"]=bi
            front=Vector((0,-math.cos(rake),-math.sin(rake)))
            for side in [-1,1]:
                p=Vector((bx+side*support,y,z))+front*.015
                bolt("Gym bench back recessed fixing",p,front,metal)
    return {"bench_model":"authored maple slats on continuous bent steel side frames",
            "bench_nominal_length_m":length,"bench_seat_top_m":seat_top,
            "bench_foot_count":8,"bench_contents":"empty"}


def lathe(name, profile, centre, mat, segments=128):
    vertices=[];faces=[]
    for radius,z in profile:
        for j in range(segments):
            angle=math.tau*j/segments
            vertices.append((centre[0]+radius*math.cos(angle),centre[1]+radius*math.sin(angle),z))
    for i in range(len(profile)):
        k=(i+1)%len(profile)
        for j in range(segments):
            faces.append((i*segments+j,i*segments+(j+1)%segments,
                          k*segments+(j+1)%segments,k*segments+j))
    return mesh_object(name,vertices,faces,mat)


def gym_bin(a):
    remove_prefixes(["Open tapered waste bin","Waste bin"])
    spec=a["furniture"]["bin"];cx,cy=spec["centre_xy_m"]
    # A 62 cm commercial moulded bin, including inside wall, base and rounded lip.
    plastic=coated_surface("Commercial bin textured grey HDPE",(.105,.124,.130),.53,.00016)
    dark=coated_surface("Bin black polyethylene liner",(.009,.012,.014),.36,.000035)
    base=coated_surface("Bin reinforced dark foot ring",(.042,.050,.053),.63,.00012)
    profile=[(.001,0),(.166,0),(.177,.004),(.180,.014),(.180,.027),
             (.178,.035),(.181,.045),(.211,.465),(.214,.510),(.216,.535),
             (.220,.550),(.220,.568),(.216,.577),(.218,.602),
             (.228,.607),(.232,.614),(.231,.624),(.224,.630),
             (.215,.630),(.209,.624),(.207,.612),(.207,.580),
             (.201,.511),(.171,.048),(.166,.034),(.001,.034)]
    body=lathe("Commercial waste bin hollow moulded body",profile,(cx,cy),plastic)
    body["hollow_profile"]=True;body["wall_thickness_nominal_m"]=.008
    body["ground_contact_furniture"]=True
    lathe("Commercial bin reinforced foot",[(.166,0),(.180,.003),(.183,.013),
           (.182,.025),(.178,.032),(.174,.028),(.174,.008)],(cx,cy),base)
    # Integrated loop handles on both sides, attached beneath the rolled rim.
    for side in [-1,1]:
        x=cx+side*.216
        points=[(x,cy-.055,.586),(x+side*.030,cy-.055,.587),
                (x+side*.048,cy-.040,.572),(x+side*.048,cy+.040,.572),
                (x+side*.030,cy+.055,.587),(x,cy+.055,.586)]
        capped_pipe("Commercial bin moulded carry handle",points,.012,plastic)
        for yy in [-.055,.055]:
            manufactured_box("Commercial bin handle reinforcing boss",(x,cy+yy,.580),
                             (.025,.031,.056),plastic,.007)
    # Empty liner with an irregular folded collar; it remains below the open mouth.
    n=192;vertices=[];faces=[]
    rings=[(.164,.0355),(.184,.30),(.198,.52),(.202,.606),
           (.204,.621),(.210,.629),(.214,.638),(.227,.638),
           (.237,.632),(.237,.616),(.225,.584)]
    for i,(r,z) in enumerate(rings):
        for j in range(n):
            t=math.tau*j/n
            fold=math.sin(13*t+.4)+.45*math.sin(27*t+1.3)
            # Inside the bag, folds move inward from the inner shell, so no cloth is
            # buried in the plastic and no white spikes show through.
            r2=r-(.0012*(fold+1.45) if i<7 else .0018*fold)
            z2=z+(0 if i<6 else .0018*math.sin(9*t+.7)+.0010*math.sin(17*t))
            # No bulging trash: only folds in the empty bag around the lip.
            vertices.append((cx+r2*math.cos(t),cy+r2*math.sin(t),z2))
    for i in range(len(rings)-1):
        for j in range(n):
            faces.append((i*n+j,(i+1)*n+j,(i+1)*n+(j+1)%n,i*n+(j+1)%n))
    faces.append(tuple(reversed(range(n))))
    liner=mesh_object("Commercial bin empty liner and folded collar",vertices,faces,dark)
    solid=liner.modifiers.new("Thin polyethylene film","SOLIDIFY");solid.thickness=.0001
    return {"waste_bin_model":"authored hollow HDPE body, rolled lip, integrated handles and empty liner",
            "bin_body_height_m":.630,"bin_body_top_diameter_m":.464,
            "bin_world_centre_xy_m":[cx,cy]}


def gym_furniture(cfg,asset_root):
    ledger=gym_documentary(cfg,asset_root)
    ledger.update(gym_benches(cfg["appearance"],asset_root))
    ledger.update(gym_bin(cfg["appearance"]))
    ledger["appearance_revision"]="manufactured gym furniture, measured joints, restrained clearcoat, deeper focus"
    ledger["furniture_model_license"]="original authored geometry; photographic wood textures retain existing CC0 attribution"
    return ledger


# --------------------------------------------------------------------------- lettering
def remove_lettering():
    """Delete every font object, the lettered banner and the scoreboard with its numerals.

    A scoreboard without digits reads as a switched-off television, so the cabinet and the
    conduit feeding it are removed as well; school practice gyms often have none.
    """
    removed = []
    for ob in list(bpy.data.objects):
        if ob.type == "FONT" or ob.name.startswith((
                "League banner", "Banner hanging rail", "Banner trim", "Scoreboard")):
            removed.append(ob.name)
            bpy.data.objects.remove(ob, do_unlink=True)
    for collection in (bpy.data.curves, bpy.data.meshes, bpy.data.fonts, bpy.data.materials):
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)
    return sorted(removed)


def exit_pictogram():
    """Green illuminated exit sign with a plain arrow pictogram, no letters."""
    housing = bpy.data.objects["Exit sign housing"]
    x, y, z = housing.location
    front = y - housing.dimensions.y/2
    green = emissive("Exit sign green diffuser", (.06, 1.0, .32), 1.6)
    white = emissive("Exit sign white arrow pictogram", (1.0, 1.0, .96), 1.8)
    cube("Exit sign green diffuser", (x, front-.0015, z), (.31, .003, .13), green)
    cube("Exit sign arrow shaft", (x-.018, front-.0034, z), (.13, .0016, .024), white)
    for sign in (-1, 1):
        head = cube("Exit sign arrow head", (x+.05, front-.0034, z+sign*.022), (.07, .0016, .024), white)
        head.rotation_euler.y = sign*math.radians(45)


# --------------------------------------------------------------------------- library textures
def _pixels(image):
    import numpy as np
    w, h = image.size
    data = np.empty(w*h*4, dtype=np.float32)
    image.pixels.foreach_get(data)
    # Rows from the top, as image editors show them (Blender stores bottom-up).
    return data.reshape(h, w, 4)[::-1].astype(np.float64)


def _box(a, r):
    """Window sums over (2r+1)^2 pixels with edge clamping (summed-area table)."""
    import numpy as np
    p = np.pad(a, ((r+1, r), (r+1, r), (0, 0)), mode="edge")
    s = p.cumsum(0).cumsum(1)
    return s[2*r+1:, 2*r+1:]-s[:-2*r-1, 2*r+1:]-s[2*r+1:, :-2*r-1]+s[:-2*r-1, :-2*r-1]


def _inpaint(region, mask, r):
    import numpy as np
    w = (~mask).astype(np.float64)[..., None]
    fill = _box(region*w, r)/np.maximum(_box(w, r), 1e-9)
    out = region.copy()
    out[mask] = fill[mask]
    return out


def _replace_image(old, array, name):
    import numpy as np
    h, w = array.shape[:2]
    new = bpy.data.images.new(name, w, h, alpha=False)
    new.colorspace_settings.name = old.colorspace_settings.name
    new.pixels.foreach_set(np.ascontiguousarray(np.clip(array[::-1], 0, 1), dtype=np.float32).ravel())
    new.pack()
    for mat in bpy.data.materials:
        if mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == "TEX_IMAGE" and node.image == old:
                    node.image = new
    bpy.data.images.remove(old)
    return new


def _library_images(filename):
    stem = filename.rsplit(".", 1)[0]
    found = [im for im in bpy.data.images
             if Path(bpy.path.abspath(im.filepath)).name == filename or im.name.split(".")[0] in (stem, filename.split(".")[0])]
    if not found:
        raise RuntimeError(f"Library texture {filename} is not loaded")
    return found


def clean_library_textures():
    """Remove printed numerals/maker marks from the CC0 clock and the label from the broom.

    The clock keeps its scanned rim and its 60 tick marks (centre 557.8, 1482.1 px, ticks at
    r >= 489 px in the 2K map; glyphs reach r = 473 px). The broom label (x 1476-1539,
    y 1665-1843 px) is filled from the surrounding handle colour plus nearby fine texture.
    Derived images live only in memory and are packed into the saved scene.
    """
    import numpy as np
    report = {}
    cx, cy, radius = 557.8, 1482.1, 480.0
    source = _pixels(_library_images("wall_clock_diff_2k.jpg")[0])
    x0, x1 = int(cx-radius-40), int(cx+radius+40)
    y0, y1 = int(cy-radius-40), min(source.shape[0], int(cy+radius+40))
    yy, xx = np.mgrid[y0:y1, x0:x1]
    inside = np.hypot(xx-cx, yy-cy)
    glyph = (source[y0:y1, x0:x1, :3].mean(axis=2) < .62) & (inside < radius)
    glyph = (_box(glyph[..., None].astype(np.float64), 2)[..., 0] > .5) & (inside < radius+4)
    report["clock_dial_pixels_repainted"] = int(glyph.sum())
    for filename in ["wall_clock_diff_2k.jpg", "wall_clock_arm_2k.jpg", "wall_clock_nor_gl_2k.jpg"]:
        for image in _library_images(filename):
            data = _pixels(image)
            data[y0:y1, x0:x1] = _inpaint(data[y0:y1, x0:x1], glyph, 22)
            _replace_image(image, data, filename.replace(".jpg", "_no_numerals"))
    bx0, bx1, by0, by1, pad = 1468, 1548, 1656, 1854, 60
    for filename in ["plastic_broom_diff_2k.jpg", "plastic_broom_arm_2k.jpg"]:
        for image in _library_images(filename):
            data = _pixels(image)
            region = data[by0-pad:by1+pad, bx0-pad:bx1+pad].copy()
            mask = np.zeros(region.shape[:2], bool)
            mask[pad:-pad, pad:-pad] = True
            low = _inpaint(region, mask, 52)
            h = by1-by0
            texture = data[by0-h-20:by0-20, bx0:bx1]
            low[pad:-pad, pad:-pad] += texture-_box(texture, 10)/441.0
            data[by0-pad:by1+pad, bx0-pad:bx1+pad] = low
            _replace_image(image, data, filename.replace(".jpg", "_no_label"))
    report["broom_label_pixels_repainted"] = (bx1-bx0)*(by1-by0)
    return report


# --------------------------------------------------------------------------- backstop
def wall_mounted_backstop(a):
    """Fixed wall-mounted extension backstop: board frame plus two Warren side trusses."""
    remove_prefixes(["Wall mounted hoop support", "Backboard support bracket"])
    spec = a["backstop"]
    steel = coated_surface("Backstop truss powder-coated steel", tuple(spec["steel_rgb"]), .44, .00005)
    zinc = material("Backstop zinc-plated anchor bolts", (.30, .31, .31), .36, .85)
    board = bpy.data.objects["1.80 by 1.05 m basketball backboard"]
    board_back = board.location.y+board.dimensions.y/2
    wall = 16.0
    top, bottom = spec["top_chord_z_m"], spec["bottom_chord_z_m"]
    xs = spec["truss_x_m"]
    # A 4 mm rubber spacer separates the frame from the glass. Coincident glass/frame faces
    # z-fight, and the winner changes from frame to frame as the moving ball rebuilds the BVH.
    frame_y = board_back+.004+.025
    for x in xs:
        manufactured_box("Backboard rear mounting frame upright", (x, frame_y, (top+bottom)/2),
                         (.05, .05, top-bottom+.05), steel, .003)
    for z in (top, bottom):
        manufactured_box("Backboard rear mounting frame rail", (0, frame_y, z),
                         (xs[1]-xs[0]+.05, .05, .05), steel, .003)
    start = frame_y+.025
    panels = spec["panels"]
    ys = [start+(wall-start)*i/panels for i in range(panels+1)]
    for x in xs:
        for z, label in ((top, "top"), (bottom, "bottom")):
            capped_pipe(f"Wall-mounted truss {label} chord", [(x, start, z), (x, wall, z)], .030, steel)
            plate = manufactured_box("Wall-mounted truss anchor plate", (x, wall-.006, z), (.20, .012, .24), steel, .002)
            plate["touches_wall_y_m"] = wall
            for dx in (-.065, .065):
                for dz in (-.085, .085):
                    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=.011, depth=.010,
                                                        location=(x+dx, wall-.017, z+dz), rotation=(math.pi/2, 0, 0))
                    nut = bpy.context.object
                    nut.name = "Wall-mounted truss anchor bolt"
                    nut.data.materials.append(zinc)
        for i in range(panels):
            za, zb = (bottom, top) if i % 2 == 0 else (top, bottom)
            capped_pipe("Wall-mounted truss diagonal web", [(x, ys[i], za), (x, ys[i+1], zb)], .021, steel)
        for y in ys[1:-1]:
            capped_pipe("Wall-mounted truss vertical web", [(x, y, bottom), (x, y, top)], .018, steel)
    for y in ys[1:-1]:
        for z in (top, bottom):
            capped_pipe("Wall-mounted truss cross tie", [(xs[0], y, z), (xs[1], y, z)], .018, steel)
    for a0, a1 in ((0, 1), (1, 0)):
        capped_pipe("Wall-mounted truss plan brace", [(xs[a0], ys[0], top), (xs[a1], ys[2], top)], .016, steel)
    return {"backstop_model": "fixed wall-mounted extension: rear board frame and two Warren side trusses",
            "backstop_extension_m": wall-board_back, "backstop_truss_depth_m": top-bottom,
            "backstop_truss_x_m": list(xs), "backstop_anchor_wall_y_m": wall,
            "freestanding_basketball_stand": False}


# --------------------------------------------------------------------------- bleachers
def bleacher_maple(a, asset_root, index):
    spec = a["bleacher_sections"]
    mat = material("Bleacher varnished maple riser %02d" % index, (.35, .24, .13), .40)
    nt, bs = nodes(mat)
    bs.inputs["Coat Weight"].default_value = .35
    bs.inputs["Coat Roughness"].default_value = .26
    folder = Path(asset_root)/a["wood_asset"]

    def tex(suffix, colour=False):
        image = bpy.data.images.load(str(folder/("white_maple_veneer_"+suffix+".jpg")), check_existing=True)
        if not colour:
            image.colorspace_settings.name = "Non-Color"
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = image
        return node.outputs["Color"]
    rng = random.Random(a["seed"]+211+index)
    tone = .80+.04*index
    tint = [v*tone*rng.uniform(.96, 1.04) for v in spec["tint_rgb"]]
    position = nt.nodes.new("ShaderNodeNewGeometry").outputs["Position"]
    # Shoe scuffs and hand grime concentrate on the lower rows.
    wear = map_range(nt, world_noise(nt, position, 3.5, 4), .45, .75, 0.0, 1.0)
    # Solid planks show stronger figure than the floor veneer: stretch the grain contrast.
    figure = nt.nodes.new("ShaderNodeBrightContrast")
    figure.inputs["Bright"].default_value = -.10
    figure.inputs["Contrast"].default_value = .80
    nt.links.new(tex("diff_8k", True), figure.inputs["Color"])
    base = mix_rgb(nt, "MULTIPLY", 1, figure.outputs["Color"], tint)
    nt.links.new(mix_rgb(nt, "MULTIPLY", wear, base, (.82, .80, .78)), bs.inputs["Base Color"])
    nt.links.new(map_range(nt, tex("rough_4k"), 0, 1, .34, .52), bs.inputs["Roughness"])
    normal = nt.nodes.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = .16
    nt.links.new(tex("nor_gl_4k"), normal.inputs["Color"])
    nt.links.new(normal.outputs["Normal"], bs.inputs["Normal"])
    return mat


def closed_bleachers(a, asset_root):
    """Closed telescopic seating: per row a recessed steel rail, a long varnished riser board
    and a seat-plank nosing; boards are 4 m sections with tight joints, no frames in front."""
    remove_prefixes(["Bleacher vertical frame", "Closed bleacher timber fascia section",
                     "Closed bleacher seat edge", "Bleacher riser steel"])
    spec = a["bleacher_sections"]
    rows, rise, y0, y1, front = 9, .32, 2.6, 14.6, -7.85
    steel = coated_surface("Bleacher recessed riser steel", (.026, .029, .031), .52, .00006)
    woods = [bleacher_maple(a, asset_root, i) for i in range(8)]
    rng = random.Random(a["seed"]+97)
    sections = spec["section_count"]
    joint = .005
    boards = 0
    for row in range(rows):
        z0 = row*rise
        cube("Bleacher recessed riser rail", (front-.01, (y0+y1)/2, z0+.030), (.016, y1-y0, .044), steel, .002)
        for s in range(sections):
            ya = y0+(y1-y0)*s/sections+joint/2
            yb = y0+(y1-y0)*(s+1)/sections-joint/2
            riser = manufactured_box("Bleacher varnished riser board", (front, (ya+yb)/2, z0+.058+.106),
                                     (.030, yb-ya, .212), woods[rng.randrange(8)], .003)
            board_uv(riser, rng.uniform(0, 7))
            nose = manufactured_box("Bleacher seat plank nosing", (front+.012, (ya+yb)/2, z0+.294),
                                    (.054, yb-ya, .044), woods[rng.randrange(8)], .007)
            board_uv(nose, rng.uniform(0, 7))
            boards += 2
    return {"bleacher_model": "closed telescopic rows: recessed steel rail, varnished maple riser, seat nosing",
            "bleacher_board_sections_per_row": sections, "bleacher_board_count": boards,
            "bleacher_front_x_m": front}


# --------------------------------------------------------------------------- court paint
def stained_key(a, asset_root):
    """The lane colour is a stain under the clear finish, so maple grain still shows."""
    mat = bpy.data.materials["Painted free throw lane"]
    nt, bs = nodes(mat)
    position = nt.nodes.new("ShaderNodeNewGeometry").outputs["Position"]
    split = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(position, split.inputs[0])
    strip = nt.nodes.new("ShaderNodeMath");strip.operation = "MULTIPLY_ADD"
    nt.links.new(split.outputs["X"], strip.inputs[0])
    strip.inputs[1].default_value = 1/a["plank_width_m"];strip.inputs[2].default_value = 9/a["plank_width_m"]
    index = nt.nodes.new("ShaderNodeMath");index.operation = "FLOOR"
    nt.links.new(strip.outputs[0], index.inputs[0])
    noise = nt.nodes.new("ShaderNodeTexWhiteNoise");noise.noise_dimensions = "1D"
    nt.links.new(index.outputs[0], noise.inputs["W"])
    shift = nt.nodes.new("ShaderNodeMath");shift.operation = "MULTIPLY_ADD"
    nt.links.new(noise.outputs["Value"], shift.inputs[0]);shift.inputs[1].default_value = 13.7
    nt.links.new(split.outputs["Y"], shift.inputs[2])
    uv = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(shift.outputs[0], uv.inputs["X"]);nt.links.new(split.outputs["X"], uv.inputs["Y"])
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(Path(asset_root)/a["wood_asset"]/"white_maple_veneer_diff_8k.jpg"), check_existing=True)
    nt.links.new(uv.outputs[0], tex.inputs["Vector"])
    grey = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(tex.outputs["Color"], grey.inputs[0])
    grain = map_range(nt, grey.outputs[0], .30, .70, .78, 1.14)
    level = nt.nodes.new("ShaderNodeCombineColor")
    for i in range(3):
        nt.links.new(grain, level.inputs[i])
    nt.links.new(mix_rgb(nt, "MULTIPLY", 1, a["court_key_rgb"], level.outputs[0]), bs.inputs["Base Color"])


# --------------------------------------------------------------------------- entry points
def gym(cfg, asset_root):
    ledger = gym_furniture(cfg, asset_root)
    a = cfg["appearance"]
    removed = remove_lettering()
    exit_pictogram()
    ledger.update(clean_library_textures())
    ledger.update(wall_mounted_backstop(a))
    ledger.update(closed_bleachers(a, asset_root))
    stained_key(a, asset_root)
    # Materials of parts removed by later layers (bleacher fascia, scoreboard) would otherwise keep their
    # images alive and packed in the saved scene.
    for collection in (bpy.data.materials, bpy.data.images):
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)
    ledger.update({"appearance_revision": "Text-free finish: no lettering, trussed backstop, varnished closed bleachers",
                   "lettering_objects_removed": removed, "text_objects_present": False,
                   "scoreboard_present": False, "exit_sign": "green arrow pictogram, no letters"})
    return ledger


def build_ball(cfg, asset_root):
    """The furniture-layer ball without the authored ink stamp; cover texture and panel channels are kept."""
    global apply_surface_print
    original = apply_surface_print
    apply_surface_print = lambda ball, cfg: None
    try:
        ball = build_ball_lived_in(cfg, asset_root)
    finally:
        apply_surface_print = original
    ball["surface_print"] = "none"
    return ball
