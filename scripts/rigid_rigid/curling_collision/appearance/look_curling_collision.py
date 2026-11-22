"""Look of the SI-scale curling club: ice, imported stones, text-free club room and camera finish.

rink(), build_stone(), lighting() and camera_finish() build the look: the club room and ice, the
imported stone with its polished finishes, and the text-free photographic pass below.
ice_material_base_ice is the pebbled ice that ice_material_debris finishes.

Final pass (appearance only; stones, camera, collision geometry and solved motion are untouched):
- no lettering, figures, menus or brand marks anywhere in the room;
- mirror-polished granite with a ground striking band, yellow handle pigment;
- ice tuned through the configuration (ice_finish), plus sparse broom debris;
- a photographic camera finish in the compositor: lateral colour dispersion (no lens distortion),
  restrained bloom on the brightest highlights and natural lens vignetting.
"""
from __future__ import annotations

import hashlib
import math
import random
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from pcve_assets import asset


class Nodes:
    def __init__(self, material):
        self.nodes,self.links = material.node_tree.nodes,material.node_tree.links

    def set(self, socket, value):
        if isinstance(value,(float,int)):
            socket.default_value = value
        elif isinstance(value,(tuple,list)):
            socket.default_value = (*value,1) if len(socket.default_value)==4 else value
        else:
            self.links.new(value,socket)

    def math(self, operation, a=None, b=None, name=None):
        n = self.nodes.new("ShaderNodeMath"); n.operation = operation
        if name: n.name = name
        for socket,value in zip(n.inputs,[a,b]):
            if value is not None: self.set(socket,value)
        return n.outputs[0]

    def mix(self, fac, a, b, mode="MIX", name=None):
        n = self.nodes.new("ShaderNodeMixRGB"); n.blend_type = mode
        if name: n.name = name
        for socket,value in zip(n.inputs,[fac,a,b]): self.set(socket,value)
        return n.outputs[0]

    def remap(self, value, low, high, out_low=0., out_high=1., name=None):
        n = self.nodes.new("ShaderNodeMapRange"); n.clamp = True
        if name: n.name = name
        for key,v in [("From Min",low),("From Max",high),("To Min",out_low),("To Max",out_high)]:
            n.inputs[key].default_value = v
        self.set(n.inputs["Value"],value)
        return n.outputs[0]

    def ramp(self, value, stops, constant=False, name=None):
        n = self.nodes.new("ShaderNodeValToRGB")
        if name: n.name = name
        if constant: n.color_ramp.interpolation = "CONSTANT"
        for index,(position,color) in enumerate(stops):
            element = n.color_ramp.elements[index] if index<2 else n.color_ramp.elements.new(position)
            element.position,element.color = position,(*color,1)
        self.set(n.inputs[0],value)
        return n.outputs[0]

    def noise(self, vector, scale, detail=2., roughness=.5, name=None):
        n = self.nodes.new("ShaderNodeTexNoise")
        if name: n.name = name
        n.inputs["Scale"].default_value,n.inputs["Detail"].default_value,n.inputs["Roughness"].default_value = scale,detail,roughness
        self.links.new(vector,n.inputs["Vector"])
        return n

    def voronoi(self, vector, scale, name=None):
        n = self.nodes.new("ShaderNodeTexVoronoi")
        if name: n.name = name
        n.inputs["Scale"].default_value = scale
        self.links.new(vector,n.inputs["Vector"])
        return n

    def luma(self, color):
        n = self.nodes.new("ShaderNodeRGBToBW"); self.links.new(color,n.inputs[0])
        return n.outputs[0]


def _principled(name):
    material = bpy.data.materials.new(name); material.use_nodes = True
    return material,material.node_tree.nodes.get("Principled BSDF")


_images,_props = {},{}


def _texture(n, vector, path, color=False, name=None):
    image = _images.get(path)
    if image is None:
        image = _images[path] = bpy.data.images.load(str(asset(path)),check_existing=True)
        if not color: image.colorspace_settings.name = "Non-Color"
    node = n.nodes.new("ShaderNodeTexImage"); node.image = image
    if name: node.name = name
    n.links.new(vector,node.inputs["Vector"])
    return node


def _wall_uv(n, tile, axis="X"):
    """World-metre planar coordinates, along the given horizontal axis and Z."""
    xyz = n.nodes.new("ShaderNodeSeparateXYZ"); n.links.new(n.nodes.new("ShaderNodeNewGeometry").outputs["Position"],xyz.inputs[0])
    uv = n.nodes.new("ShaderNodeCombineXYZ")
    n.links.new(n.math("DIVIDE",xyz.outputs[axis],tile),uv.inputs[0])
    n.links.new(n.math("DIVIDE",xyz.outputs["Z"],tile),uv.inputs[1])
    return uv.outputs[0],xyz


def _new(name):
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    return mat,Nodes(mat),mat.node_tree.nodes.get("Principled BSDF")


def painted_block_wall(name, paint, band, band_top, tile, world):
    """Scanned concrete block with thick paint: block relief survives, its colour does not."""
    mat,n,shader = _new(name)
    uv,xyz = _wall_uv(n,tile)
    pos = n.nodes.new("ShaderNodeNewGeometry").outputs["Position"]
    root = "polyhaven/concrete_block_wall/concrete_block_wall_"
    diff = _texture(n,uv,root+"diff_4k.jpg",name="Scanned block albedo")
    relief = _texture(n,uv,root+"disp_4k.jpg",name="Scanned block relief")
    rough = _texture(n,uv,root+"rough_4k.jpg")
    colour = n.mix(n.remap(xyz.outputs["Z"],band_top-.004,band_top+.004,1.,0.),paint,band)
    colour = n.mix(1,colour,n.remap(n.luma(diff.outputs["Color"]),.015,.13,.82,1.04),"MULTIPLY")
    # Running-bond courses in metres; thick paint leaves the joints as shallow grooves.
    courses = n.nodes.new("ShaderNodeTexBrick"); courses.name = "Concrete block courses"; courses.offset = .5
    joint_uv = n.nodes.new("ShaderNodeCombineXYZ"); n.links.new(xyz.outputs["X"],joint_uv.inputs[0]); n.links.new(xyz.outputs["Z"],joint_uv.inputs[1])
    n.links.new(joint_uv.outputs[0],courses.inputs["Vector"])
    for key,value in [("Scale",1.),("Mortar Size",world["wall_joint_m"]),("Mortar Smooth",.5),("Brick Width",world["wall_block_m"][0]),("Row Height",world["wall_block_m"][1])]:
        courses.inputs[key].default_value = value
    courses.inputs["Color1"].default_value = courses.inputs["Color2"].default_value = (0,0,0,1)
    courses.inputs["Mortar"].default_value = (1,1,1,1)
    groove = n.luma(courses.outputs["Color"])
    colour = n.mix(n.math("MULTIPLY",groove,.20),colour,(.03,.03,.028))
    patch = n.noise(pos,1.1,3,.55,"Repainted patches")
    colour = n.mix(1,colour,n.remap(patch.outputs["Fac"],.38,.62,world["wall_patch_low"],1.05),"MULTIPLY")
    stretch = n.nodes.new("ShaderNodeVectorMath"); stretch.operation = "MULTIPLY"; stretch.inputs[1].default_value = (9,1,.8)
    n.links.new(pos,stretch.inputs[0])
    streak = n.noise(stretch.outputs[0],1.,4,.6,"Vertical run-off streaks")
    colour = n.mix(n.math("MULTIPLY",n.remap(streak.outputs["Fac"],.52,.72),world["wall_streak"]),colour,(.09,.085,.07))
    floor = n.remap(xyz.outputs["Z"],.08,.75,world["wall_floor_grime"],0.,"Grime rising from the walkway")
    colour = n.mix(floor,colour,(.05,.048,.042))
    n.links.new(colour,shader.inputs["Base Color"])
    n.links.new(n.remap(n.luma(rough.outputs["Color"]),0.,1.,.42,.72),shader.inputs["Roughness"])
    bump = n.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = .8; bump.inputs["Distance"].default_value = .012
    n.links.new(n.math("SUBTRACT",n.luma(relief.outputs["Color"]),n.math("MULTIPLY",groove,.5)),bump.inputs["Height"]); n.links.new(bump.outputs[0],shader.inputs["Normal"])
    return mat


def stained_timber(name, tint, tile=.9, axis="X"):
    mat,n,shader = _new(name)
    uv,_ = _wall_uv(n,tile,axis)
    root = "polyhaven/plywood/plywood_"
    grain = _texture(n,uv,root+"diff_4k.jpg",True,"Scanned plywood")
    n.links.new(n.mix(1,grain.outputs["Color"],tint,"MULTIPLY"),shader.inputs["Base Color"])
    shader.inputs["Roughness"].default_value = .46
    return mat


def scuffed_paint(name, paint, roughness=.42, grime=.3):
    """Enamel over steel or door skin, dirtier near hands and floor."""
    mat,n,shader = _new(name)
    pos = n.nodes.new("ShaderNodeNewGeometry").outputs["Position"]
    xyz = n.nodes.new("ShaderNodeSeparateXYZ"); n.links.new(pos,xyz.inputs[0])
    dirt = n.noise(pos,16,5,.6,"Handling dirt")
    mask = n.math("MULTIPLY",n.remap(dirt.outputs["Fac"],.42,.68),grime)
    low = n.remap(xyz.outputs["Z"],.1,.7,1.,.25)
    colour = n.mix(n.math("MULTIPLY",mask,low),paint,tuple(v*.45 for v in paint))
    n.links.new(colour,shader.inputs["Base Color"])
    n.links.new(n.remap(dirt.outputs["Fac"],.35,.7,roughness-.06,roughness+.14),shader.inputs["Roughness"])
    return mat


def append_prop(path, location, rotation_z=0., scale=1., only=None, skip=()):
    """Place a scanned asset; repeated placements share its mesh and materials."""
    objects = _props.get(path)
    if objects is None:
        with bpy.data.libraries.load(str(asset(path)),link=False) as (source,target):
            target.objects = source.objects
        objects = _props[path] = [o for o in target.objects if o and o.type=="MESH"]
    transform = Matrix.Translation(location)@Matrix.Rotation(rotation_z,4,"Z")@Matrix.Scale(scale,4)
    placed = []
    for original in objects:
        if original.name in skip or (only and original.name not in only):
            continue
        obj = original.copy(); obj.parent = None
        bpy.context.collection.objects.link(obj)
        obj.matrix_world = transform@original.matrix_world
        placed.append(obj)
    return placed


def bar_room_club(cfg):
    """The club bar behind the glazing, from a complete scanned-scale cafe interior."""
    ar = cfg["appearance"]["arena"]
    move = Matrix.Translation(ar["bar_room_offset_m"])
    keep_y,(min_x,max_x) = ar["wall_y_m"]+.13,ar["bar_room_x_limits_m"]
    with bpy.data.libraries.load(str(asset("blenderkit/cafe_interior_loft_bar/cafe_interior_loft_bar.blend")),link=False) as (source,target):
        target.objects = source.objects
    loaded = [o for o in target.objects if o]
    holder = bpy.data.collections.new("Bar room source"); bpy.context.scene.collection.children.link(holder)
    for obj in loaded:
        if obj.type in ("MESH","CURVE","EMPTY"): holder.objects.link(obj)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    used = set(); baked = []
    for obj in holder.objects:
        if obj.type=="EMPTY": continue
        world = move@obj.matrix_world
        corners = [world@Vector(c) for c in obj.bound_box]
        if max(c.y for c in corners)<keep_y or max(c.x for c in corners)<min_x or min(c.x for c in corners)>max_x:
            continue
        mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
        mesh.transform(world)
        if min(c.y for c in corners)<keep_y:
            bm = bmesh.new(); bm.from_mesh(mesh)
            bmesh.ops.bisect_plane(bm,geom=bm.verts[:]+bm.edges[:]+bm.faces[:],plane_co=(0,keep_y,0),plane_no=(0,1,0),clear_inner=True)
            bm.to_mesh(mesh); bm.free()
        if not mesh.polygons:
            bpy.data.meshes.remove(mesh); continue
        baked.append((obj.name,mesh))
    bpy.context.scene.collection.children.unlink(holder); bpy.data.collections.remove(holder)
    for obj in loaded: bpy.data.objects.remove(obj)
    room = bpy.data.collections.new("Club bar room"); bpy.context.scene.collection.children.link(room)
    for name,mesh in baked:
        obj = bpy.data.objects.new("Bar room / "+name,mesh); room.objects.link(obj)
        used.update(m for m in mesh.materials if m)
    # The room is only ever seen blurred through glass; keep its textures small.
    images = {n.image for m in used if m.use_nodes for n in m.node_tree.nodes if n.type=="TEX_IMAGE" and n.image}
    for image in images:
        side = max(image.size)
        if side>ar["bar_room_texture_px"]:
            f = ar["bar_room_texture_px"]/side
            image.scale(max(1,int(image.size[0]*f)),max(1,int(image.size[1]*f)))
            image.pack()
    for x,y,z,watts in ar["bar_room_lights"]:
        data = bpy.data.lights.new("Bar room light","AREA"); data.size = 2.2; data.energy = watts; data.color = (1.,.80,.56)
        light = bpy.data.objects.new(data.name,data); room.objects.link(light); light.location = (x,y,z)
        light.visible_camera = light.visible_glossy = light.visible_transmission = False
    return baked


def viewing_gallery(cfg, rear_wall, cube, material, dark):
    """A real opening in the rear wall: deep reveal, aluminium frame, blinds, the bar beyond."""
    ar = cfg["appearance"]["arena"]; wall_y = ar["wall_y_m"]
    glass = material("Clear viewing-gallery glazing",(.82,.86,.86),.02)
    shader = glass.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Transmission Weight"].default_value = .95; shader.inputs["IOR"].default_value = 1.47
    alloy = scuffed_paint("Anodised window frame",(.055,.058,.06),.36,.3)
    slat = material("Venetian blind slat",(.42,.40,.35),.5)
    sill = stained_timber("Gallery window sill",(.34,.26,.19))
    x,z,(w,h) = ar["gallery_window_x_m"],ar["gallery_center_z_m"],ar["gallery_window_size_m"]
    opening = cube("Gallery opening cutter",(x,wall_y,z),(w,.5,h),dark)
    cutter = rear_wall.modifiers.new("Window opening","BOOLEAN")
    cutter.operation,cutter.object = "DIFFERENCE",opening
    opening.hide_render = opening.hide_viewport = True
    face = wall_y+.075
    cube("Gallery glazing",(x,face,z),(w,.012,h),glass)
    for dx in [-w/2+.02,0,w/2-.02]:
        cube(f"Window mullion {dx}",(x+dx,face-.012,z),(.05,.05,h),alloy,.003)
    for dz in [h/2-.02,-h/2+.02]:
        cube(f"Window rail {dz}",(x,face-.012,z+dz),(w,.05,.05),alloy,.003)
    cube("Window sill",(x,wall_y-.135,z-h/2-.012),(w+.14,.09,.03),sill,.004)
    # Blinds half lowered on one bay, as somebody left them, tucked behind the frame.
    bay = x+w/4
    for j in range(ar["gallery_blind_slats"]):
        blind = cube(f"Blind slat {j}",(bay,face+.03,z+h/2-.05-j*.034),(w/2-.07,.024,.003),slat)
        blind.rotation_euler.x = .3
    bar_room_text_free(cfg)


def bench(name, x, cfg, cube, rod, timber, tube):
    """Slatted bench against the wall on welded tube frames."""
    wall = cfg["appearance"]["arena"]["wall_y_m"]-.11; floor_z = .08
    length = 1.8
    rng = random.Random(cfg["appearance"]["seed"]+int(x*100))
    for i,dy in enumerate([.56,.455,.35]):
        cube(f"{name} seat slat {i}",(x+rng.uniform(-.004,.004),wall-dy,floor_z+.445+rng.uniform(-.0015,.0015)),(length,.09,.024),timber,.007)
    for i,(dy,z) in enumerate([(.215,.60),(.195,.72),(.175,.84)]):
        slat = cube(f"{name} back slat {i}",(x,wall-dy,floor_z+z),(length,.022,.09),timber,.007)
        slat.rotation_euler.x = -.16
    for dx in [-.72,0.,.72]:
        rod(f"{name} front leg {dx}",(x+dx,wall-.56,floor_z),(x+dx,wall-.56,floor_z+.43),.014,tube)
        rod(f"{name} rear post {dx}",(x+dx,wall-.30,floor_z),(x+dx,wall-.30,floor_z+.43),.014,tube)
        rod(f"{name} seat rail {dx}",(x+dx,wall-.60,floor_z+.43),(x+dx,wall-.28,floor_z+.43),.014,tube)
        rod(f"{name} back rail {dx}",(x+dx,wall-.28,floor_z+.43),(x+dx,wall-.16,floor_z+.90),.014,tube)
    for dx in [-.72,.72]:
        rod(f"{name} foot rail {dx}",(x+dx,wall-.56,floor_z+.012),(x+dx,wall-.30,floor_z+.012),.012,tube)


def walkway_floor(name):
    """Interlocking rubber matting: seams, scuffed traffic down the middle, dirt at the wall."""
    mat,n,shader = _new(name)
    pos = n.nodes.new("ShaderNodeNewGeometry").outputs["Position"]
    xyz = n.nodes.new("ShaderNodeSeparateXYZ"); n.links.new(pos,xyz.inputs[0])
    tiles = n.nodes.new("ShaderNodeTexChecker"); tiles.inputs["Scale"].default_value = 1.
    seams = n.nodes.new("ShaderNodeTexBrick"); seams.offset = 0.; n.links.new(pos,seams.inputs["Vector"])
    for key,value in [("Scale",1.),("Mortar Size",.003),("Brick Width",.9),("Row Height",.9)]:
        seams.inputs[key].default_value = value
    seams.inputs["Color1"].default_value = seams.inputs["Color2"].default_value = (0,0,0,1); seams.inputs["Mortar"].default_value = (1,1,1,1)
    nodes = n.nodes; nodes.remove(tiles)
    dirt = n.noise(pos,6,5,.6,"Scuffed traffic")
    colour = n.mix(1,(.15,.15,.14),n.remap(dirt.outputs["Fac"],.35,.65,.72,1.12),"MULTIPLY")
    colour = n.mix(n.math("MULTIPLY",n.luma(seams.outputs["Color"]),.8),colour,(.02,.02,.02))
    n.links.new(colour,shader.inputs["Base Color"])
    n.links.new(n.remap(dirt.outputs["Fac"],.35,.65,.5,.78),shader.inputs["Roughness"])
    return mat


def walkway_dressing(cfg, cube, material, rod):
    """Everyday things along the wall: benches, a towel, a bin, a rubber skirting."""
    ar = cfg["appearance"]["arena"]; wall = ar["wall_y_m"]-.11
    timber = stained_timber("Worn bench slats",(.33,.25,.18))
    tube = scuffed_paint("Bench tube enamel",(.03,.032,.034),.4,.35)
    for i,x in enumerate(ar["bench_x_m"]):
        bench(f"Bench {i}",x,cfg,cube,rod,timber,tube)
    skirt = material("Rubber wall skirting",(.012,.012,.013),.6)
    cube("Wall skirting",(0,wall-.004,.135),(48,.008,.11),skirt)
    px,py = ar["towel_xy_m"]
    append_prop("blenderkit/kitchen_towel/kitchen_towel.blend",(px,wall-py,.08+.457),1.35,1.)
    bin_mat = scuffed_paint("Grey waste bin",(.13,.135,.13),.55,.5)
    bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=.2,depth=.62,location=(ar["bin_x_m"],wall-.28,.39))
    waste = bpy.context.object; waste.name = "Waste bin"; waste.data.materials.append(bin_mat); bpy.ops.object.shade_smooth()
    bpy.ops.mesh.primitive_torus_add(major_radius=.2,minor_radius=.012,major_segments=48,minor_segments=12,location=(ar["bin_x_m"],wall-.28,.70))
    bag = bpy.context.object; bag.name = "Bin liner rim"; bag.data.materials.append(material("Black bin liner",(.01,.01,.012),.4)); bpy.ops.object.shade_smooth()


def far_board_dressing(cfg, cube, material, rod, dark, grey):
    """Resting brooms on the walkway."""
    ar = cfg["appearance"]["arena"]
    shaft = material("Carbon broom shaft",(.022,.024,.028),.34)
    pad = material("Worn broom pad",(.085,.09,.095),.85)
    head = material("Broom head moulding",(.03,.03,.032),.5)
    # Brooms lean on the block wall beyond the walkway.
    wall_face,floor_z = ar["wall_y_m"]-.11,.08
    for x,lean,out in zip(ar["broom_x_m"],[.10,-.08,.14],[.40,.46,.36]):
        rod("Broom shaft "+str(x),(x,wall_face-out,floor_z+.055),(x+lean,wall_face-.015,floor_z+1.30),.0115,shaft)
        rod("Broom grip "+str(x),(x+lean*.93,wall_face-.015-(out-.015)*.07,floor_z+1.215),(x+lean,wall_face-.015,floor_z+1.30),.0145,dark)
        cube("Broom head "+str(x),(x,wall_face-out,floor_z+.05),(.12,.05,.03),head,.008)
        obj = cube("Broom pad "+str(x),(x,wall_face-out,floor_z+.022),(.29,.085,.042),pad,.014); obj.rotation_euler.z = lean*.5


# Image textures of the cafe interior that carry printed labels, menus, logos or screen pictures.
LABEL_IMAGE_KEYS = ("starbuck","caramel","nescafe","decafe","cof.png","gin.png","coffeejar","imagepaste",
    "adora","ado3","img_4373","sharp","ขนมปัง","หะ")


POINT_OF_SALE = ("Bar room / Cube.011",)


def _is_label(image):
    key = (image.name+" "+image.filepath).lower()
    return any(k in key for k in LABEL_IMAGE_KEYS)


def _mean_colour(image):
    """Mean scene-linear colour of an sRGB label image."""
    import numpy as np
    small = image.copy(); small.scale(32,32)
    pixels = np.empty(32*32*4,dtype=np.float32); small.pixels.foreach_get(pixels)
    bpy.data.images.remove(small)
    srgb = pixels.reshape(-1,4)[:,:3]
    linear = np.where(srgb<=.04045,srgb/12.92,((srgb+.055)/1.055)**2.4)
    return tuple(float(v) for v in linear.mean(axis=0))


def flatten_labels(materials):
    """Replace every label image by a flat colour node with the label's mean colour."""
    flattened = []
    for mat in materials:
        if not mat or not mat.use_nodes:
            continue
        tree = mat.node_tree
        for node in list(tree.nodes):
            if node.type!="TEX_IMAGE" or not node.image or not _is_label(node.image):
                continue
            image = node.image
            colour = _mean_colour(image) if image.colorspace_settings.name!="Non-Color" else (.5,.5,.5)
            flat = tree.nodes.new("ShaderNodeRGB"); flat.location = node.location
            flat.outputs[0].default_value = (*colour,1)
            for link in list(tree.links):
                if link.from_node==node:
                    if link.from_socket.name=="Alpha":
                        value = tree.nodes.new("ShaderNodeValue"); value.outputs[0].default_value = 1.
                        tree.links.new(value.outputs[0],link.to_socket)
                    else:
                        tree.links.new(flat.outputs[0],link.to_socket)
            tree.nodes.remove(node)
            flattened.append(image.name)
    for image in list(bpy.data.images):
        if image.users==0 and _is_label(image):
            bpy.data.images.remove(image)
    return sorted(set(flattened))


def bar_room_text_free(cfg):
    """The club bar (clipped, textures reduced), then every label flattened."""
    baked = bar_room_club(cfg)
    room = bpy.data.collections["Club bar room"]
    # The till's screen showed a stock picture; the till goes, the counter stays.
    for name in POINT_OF_SALE:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            mesh = obj.data; bpy.data.objects.remove(obj); bpy.data.meshes.remove(mesh)
    used = {m for o in room.objects if o.type=="MESH" for m in o.data.materials if m}
    room["flattened_label_images"] = flatten_labels(used)
    return baked



def team_photograph(name, index, rng, aspect):
    """Faded print of a curling team line-up: four or five people standing side by side.

    Built in the print's generated coordinates (u across, v up; aspect = width/height); at the camera
    distance it resolves as a few faces over team jackets in front of a hall, as real framed club
    photographs do. Every third print is an old monochrome one.
    """
    mat,n,shader = _new(name)
    gen = n.nodes.new("ShaderNodeTexCoord").outputs["Generated"]
    uvw = n.nodes.new("ShaderNodeSeparateXYZ"); n.links.new(gen,uvw.inputs[0])
    u,v = uvw.outputs["X"],uvw.outputs["Z"]
    hall = [(.30,.29,.25),(.22,.24,.26),(.33,.30,.27),(.26,.27,.24),(.24,.22,.21),(.29,.30,.31)][index%6]
    jackets = [(.20,.035,.03),(.025,.04,.11),(.05,.06,.07),(.03,.09,.05),(.24,.20,.16),(.10,.03,.08)]
    jacket = jackets[(index*5+2)%len(jackets)]
    count = rng.choice([4,4,5])
    left,right = .10,.90
    # Background: hall wall above, the ice the team stands on below, with a soft vertical light falloff.
    colour = n.mix(n.remap(v,.10,.16,1.,0.),hall,(.55,.57,.58))
    colour = n.mix(1,colour,n.remap(v,.2,1.,1.05,.85),"MULTIPLY")
    span = n.remap(u,left,right,0.,count)
    inside = n.math("MULTIPLY",n.math("GREATER_THAN",u,left),n.math("LESS_THAN",u,right))
    local = n.math("SUBTRACT",n.math("FRACT",span),.5)
    who = n.nodes.new("ShaderNodeTexWhiteNoise"); who.noise_dimensions = "1D"
    n.links.new(n.math("ADD",n.math("FLOOR",span),index*7.3),who.inputs["W"])
    jit = who.outputs["Value"]
    # Cell width in units of print height, so heads stay round whatever the frame.
    cell = (right-left)/count*aspect
    head_r = .10
    head_v = n.math("ADD",.69,n.math("MULTIPLY",n.math("SUBTRACT",jit,.5),.08))
    dx = n.math("MULTIPLY",local,cell)
    dy = n.math("SUBTRACT",v,head_v)
    radial = n.math("ADD",n.math("POWER",n.math("DIVIDE",dx,head_r*.8),2.),n.math("POWER",n.math("DIVIDE",dy,head_r),2.))
    head = n.math("MULTIPLY",n.math("LESS_THAN",radial,1.),inside)
    hair = n.math("MULTIPLY",head,n.math("GREATER_THAN",dy,head_r*.55))
    # Broad, rounded shoulders just below the chin; jackets reach the bottom of the print.
    shoulders = n.math("SUBTRACT",head_v,head_r*1.15)
    drop = n.math("MAXIMUM",n.math("SUBTRACT",v,n.math("SUBTRACT",shoulders,.05)),0.)
    half_width = n.math("SUBTRACT",.46,n.math("MULTIPLY",n.math("POWER",n.math("DIVIDE",drop,.05),2.),.30))
    body = n.math("MULTIPLY",n.math("LESS_THAN",n.math("ABSOLUTE",local),half_width),
        n.math("MULTIPLY",n.math("GREATER_THAN",v,.0),n.math("LESS_THAN",v,shoulders)))
    body = n.math("MULTIPLY",body,inside)
    skin = n.mix(jit,(.42,.29,.22),(.26,.17,.12))
    hair_colour = n.mix(n.math("FRACT",n.math("MULTIPLY",jit,7.)),(.03,.025,.02),(.22,.17,.11))
    tone = n.remap(n.math("FRACT",n.math("MULTIPLY",jit,3.)),0.,1.,.82,1.12)
    colour = n.mix(body,colour,n.mix(1,jacket,tone,"MULTIPLY"))
    colour = n.mix(head,colour,skin)
    colour = n.mix(hair,colour,hair_colour)
    if index%3==2:
        colour = n.mix(.9,colour,n.mix(1,(.9,.85,.75),n.luma(colour),"MULTIPLY"))
    # A faded, slightly warm print.
    colour = n.mix(.16,colour,(.40,.36,.30))
    n.links.new(colour,shader.inputs["Base Color"])
    shader.inputs["Roughness"].default_value = .3
    return mat


def photo_wall(cfg, cube, material):
    """Two rows of framed team photographs, hung by different hands over the years."""
    ar = cfg["appearance"]["arena"]; wall = ar["wall_y_m"]-.116
    rng = random.Random(cfg["appearance"]["seed"]+5)
    frame = stained_timber("Photo frame timber",(.16,.11,.08))
    black = material("Black photo frame",(.018,.018,.02),.38)
    mount = material("Photo mount card",(.46,.45,.40),.8)
    placed = []
    rows = [(ar["photo_z_m"],ar["photo_x_m"],(.40,.30),(.36,.26),(.27,.17))]
    rows.append((ar["photo_lower_row_z_m"],ar["photo_lower_row_x_m"],(.52,.40),(.47,.35),(.38,.25)))
    i = 0
    for z0,xs,outer,mount_size,print_size in rows:
        for x in xs:
            z = z0+rng.uniform(-.025,.025)
            twist = rng.uniform(-.014,.014)
            print_ = team_photograph(f"Team photograph {i}",i,rng,print_size[0]/print_size[1])
            frame_mat = black if i%3==1 else frame
            for part,size,depth,mat in [("frame",outer,.004,frame_mat),("mount",mount_size,.0085,mount),("print",print_size,.0095,print_)]:
                obj = cube(f"Team photo {i} {part}",(x,wall-depth,z),(size[0],.008,size[1]),mat,.001)
                obj.rotation_euler = (0,twist,0)
            placed.append(x); i += 1
    return placed


def wall_services(cfg, cube, material, rod):
    """Conduit and switch box, then the photo wall."""
    ar = cfg["appearance"]["arena"]; wall = ar["wall_y_m"]-.116
    galv = material("Galvanized conduit",(.34,.35,.35),.45,.8)
    z = ar["conduit_z_m"]
    rod("Lighting conduit",(-24,wall-.03,z),(24,wall-.03,z),.011,galv)
    for x in [i*1.18+.31 for i in range(-20,21)]:
        cube(f"Conduit saddle {x}",(x,wall-.022,z),(.022,.02,.04),galv,.002)
    down = ar["door_x_m"]+.72
    rod("Switch drop conduit",(down,wall-.03,z),(down,wall-.03,1.42),.011,galv)
    box = scuffed_paint("Switch box",(.33,.34,.33),.45,.4)
    cube("Switch box",(down,wall-.04,1.34),(.11,.05,.16),box,.004)
    cube("Conduit junction",(down,wall-.03,z),(.09,.04,.09),galv,.004)
    photo_wall(cfg,cube,material)


def door(cfg, cube, material, rod):
    """Service door; a plain twin-head emergency light instead of a lettered exit sign."""
    ar = cfg["appearance"]["arena"]; wall_y = ar["wall_y_m"]; dx = ar["door_x_m"]
    leaf = scuffed_paint("Service door enamel",(.20,.215,.205),.4,.75)
    frame = scuffed_paint("Door frame paint",(.09,.095,.09),.42,.5)
    steel = material("Door hardware",(.38,.39,.39),.34,.9)
    dark = material("Door reveal and gaskets",(.018,.023,.024),.72)
    pane = material("Wired vision pane",(.05,.055,.055),.12)
    cube("Service door reveal",(dx,wall_y-.125,1.13),(1.08,.035,2.13),dark,.004)
    cube("Service door leaf",(dx,wall_y-.15,1.13),(.99,.035,2.05),leaf,.003)
    for offset in [-.53,.53]:
        cube("Door jamb "+str(offset),(dx+offset,wall_y-.18,1.13),(.05,.08,2.13),frame,.003)
    cube("Door head",(dx,wall_y-.18,2.19),(1.11,.08,.05),frame,.003)
    cube("Door kick plate",(dx,wall_y-.170,.26),(.92,.003,.26),steel,.001)
    cube("Door vision pane",(dx+.1,wall_y-.170,1.62),(.26,.004,.46),pane,.002)
    cube("Vision pane frame",(dx+.1,wall_y-.1685,1.62),(.31,.002,.51),frame)
    rod("Door push bar",(dx-.38,wall_y-.21,1.03),(dx+.40,wall_y-.21,1.03),.016,steel)
    for x in [dx-.38,dx+.40]:
        cube(f"Push bar bracket {x}",(x,wall_y-.19,1.03),(.05,.05,.07),steel,.004)
    # Twin-head emergency light: an off-white battery box on the wall with two unlit lamp heads.
    housing = scuffed_paint("Emergency light housing",(.52,.52,.49),.45,.3)
    lens = material("Emergency lamp lens",(.60,.60,.56),.18)
    face = wall_y-.11
    cube("Emergency light battery box",(dx,face-.045,2.42),(.34,.09,.12),housing,.008)
    for side in [-1,1]:
        x = dx+side*.115
        rod(f"Emergency lamp stem {side}",(x,face-.06,2.47),(x,face-.10,2.53),.01,housing)
        bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=.045,depth=.07,location=(x,face-.12,2.55))
        head = bpy.context.object; head.name = f"Emergency lamp head {side}"
        head.rotation_euler = (math.radians(100),0,side*math.radians(18)); head.data.materials.append(housing)
        bpy.ops.object.shade_smooth()
        bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=.038,depth=.004,location=(0,0,0))
        glass = bpy.context.object; glass.name = f"Emergency lamp lens {side}"
        glass.parent = head; glass.location = (0,0,.036); glass.data.materials.append(lens)
        bpy.ops.object.shade_smooth()
    # Plain fire extinguisher on its wall bracket beside the door; no label.
    red = material("Extinguisher red enamel",(.36,.012,.012),.28)
    black = material("Extinguisher black fittings",(.012,.012,.014),.45)
    ex = dx-.82
    cube("Fire extinguisher bracket",(ex,face-.012,.86),(.08,.024,.30),black,.004)
    bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=.075,depth=.48,location=(ex,face-.10,.80))
    body = bpy.context.object; body.name = "Fire extinguisher body"; body.data.materials.append(red)
    bevel = body.modifiers.new("Rounded shoulders","BEVEL"); bevel.width,bevel.segments = .03,6
    bpy.ops.object.shade_smooth()
    cube("Fire extinguisher valve",(ex,face-.10,1.075),(.05,.05,.07),black,.006)
    rod("Fire extinguisher hose",(ex+.03,face-.10,1.06),(ex+.085,face-.13,.70),.008,black)


SEGMENTS = 192


# (radius, height) rings measured from the normalized asset; its 24-gon body showed facets on screen.
LOWER = [(.0844,0.),(.1098,.0039),(.1283,.015),(.1407,.032),(.145,.049)]


UPPER = [(.145,.082),(.1407,.1),(.1283,.116),(.1075,.1285)]


def catmull_rom(points, per_span=10):
    samples = []
    for a,b,c,d in zip(points,points[1:],points[2:],points[3:]):
        for i in range(per_span):
            t = i/per_span
            samples.append(tuple(.5*(2*b[k]+(c[k]-a[k])*t+(2*a[k]-5*b[k]+4*c[k]-d[k])*t*t+(3*b[k]-a[k]-3*c[k]+d[k])*t**3) for k in range(2)))
    return samples


def body_profile(radius):
    """Bottom to top; the striking band stays exactly at the collision radius."""
    lower = catmull_rom([(.06,-.002),*LOWER,UPPER[0]])
    upper = catmull_rom([LOWER[-1],*UPPER,(.09,.133)])
    return [(min(r,radius),max(z,0.)) for r,z in [*lower,LOWER[-1],*upper,UPPER[-1]]]


def add_lathe(bm, profile, material_index):
    rings = []
    for r,z in profile:
        rings.append([bm.verts.new((r*math.cos(2*math.pi*i/SEGMENTS),r*math.sin(2*math.pi*i/SEGMENTS),z)) for i in range(SEGMENTS)])
    for below,above in zip(rings,rings[1:]):
        for i in range(SEGMENTS):
            j = (i+1)%SEGMENTS
            face = bm.faces.new((below[i],below[j],above[j],above[i]))
            face.material_index,face.smooth = material_index,True
    for ring,z,flip in [(rings[0],profile[0][1],True),(rings[-1],profile[-1][1],False)]:
        centre = bm.verts.new((0,0,z))
        for i in range(SEGMENTS):
            j = (i+1)%SEGMENTS
            face = bm.faces.new((centre,ring[j],ring[i]) if flip else (centre,ring[i],ring[j]))
            face.material_index,face.smooth = material_index,True


def stone_mesh(original, radius):
    """Keep the asset's cap and handle islands, subdivided, and replace its 24-gon body."""
    source = bpy.data.objects.new("Asset handle working copy",original.data.copy())
    bpy.context.collection.objects.link(source)
    bm = bmesh.new(); bm.from_mesh(source.data)
    seen,remove = set(),[]
    for start in bm.verts:
        if start in seen:
            continue
        stack,island = [start],[]
        seen.add(start)
        while stack:
            vertex = stack.pop(); island.append(vertex)
            for edge in vertex.link_edges:
                other = edge.other_vert(vertex)
                if other not in seen:
                    seen.add(other); stack.append(other)
        if max(v.co.z for v in island) < .13:
            remove.extend(island)
    bmesh.ops.delete(bm,geom=remove,context="VERTS")
    bm.to_mesh(source.data); bm.free()
    subsurf = source.modifiers.new("Smooth handle","SUBSURF")
    subsurf.levels = subsurf.render_levels = 2
    bpy.context.view_layer.update()
    mesh = bpy.data.meshes.new_from_object(source.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    data = source.data
    bpy.data.objects.remove(source); bpy.data.meshes.remove(data)
    mesh.name = "Curling stone: lathed granite, asset handle"
    mesh.materials.clear()
    mesh.materials.append(None); mesh.materials.append(None)
    bm = bmesh.new(); bm.from_mesh(mesh)
    for face in bm.faces:
        face.material_index,face.smooth = 1,True
    add_lathe(bm,body_profile(radius),0)
    bm.to_mesh(mesh); bm.free()
    return mesh


def build_stone(cfg,index,asset_root):
    """The imported stone geometry with the polished granite and polymer finishes."""
    ph,asset = cfg["physics"],cfg["appearance"]["stone_asset"]
    path = Path(asset_root)/asset["registry_id"]/asset["blend_filename"]
    if not path.is_file():
        raise FileNotFoundError(f"Download and prepare the registered curling stone asset: {path}")
    if hashlib.sha256(path.read_bytes()).hexdigest()!=asset["normalized_blend_sha256"]:
        raise ValueError("The registered curling stone asset checksum differs")
    mesh = bpy.data.meshes.get("Curling stone: lathed granite, asset handle")
    if mesh is None:
        with bpy.data.libraries.load(str(path),link=False) as (source,target):
            if asset["collection_name"] not in source.collections:
                raise ValueError("Expected normalized asset collection is missing")
            target.collections = [asset["collection_name"]]
        templates = target.collections[0]
        meshes = [o for o in templates.all_objects if o.type=="MESH"]
        if len(meshes)!=1 or (meshes[0].matrix_world-Matrix.Identity(4)).to_scale().length>1e-6:
            raise ValueError("Expected one baked, identity-transform asset mesh")
        mesh = stone_mesh(meshes[0],ph["radius_m"])
    name = ph["object_ids"][index]
    root = bpy.data.objects.new(name+" / solved rigid stone",None)
    bpy.context.collection.objects.link(root)
    root.rotation_mode = "QUATERNION"
    root["object_id"],root["mass_kg"] = name,ph["mass_kg"][index]
    root["degrees_of_freedom"] = ph["degrees_of_freedom"]
    root["asset_source"] = asset["source_page"]
    root["asset_author"],root["asset_license"] = "FilinMX","CC BY-NC 4.0"
    root["normalized_asset_sha256"] = asset["normalized_blend_sha256"]
    obj = bpy.data.objects.new(name+" / imported curling stone",mesh)
    obj.parent = root
    obj.matrix_basis = Matrix.Translation((0,0,-ph["com_height_m"]))
    bpy.context.collection.objects.link(obj)
    finish = cfg["appearance"]["stone_finish"]
    for slot,material in zip(obj.material_slots,[granite_material_polished(name,finish),
            polymer_material_polished(name,cfg["appearance"]["handle_colors_rgb"][index],finish)]):
        slot.link = "OBJECT"
        slot.material = material
    root["visual_asset_dimensions_m"] = [max(v.co[i] for v in mesh.vertices)-min(v.co[i] for v in mesh.vertices) for i in range(3)]
    return root


def _blur(field, sigma):
    h,w = field.shape
    fy,fx = np.fft.fftfreq(h)[:,None],np.fft.rfftfreq(w)[None,:]
    return np.fft.irfft2(np.fft.rfft2(field)*np.exp(-2*(np.pi*sigma)**2*(fx*fx+fy*fy)),s=field.shape)


def _low_frequency(rng, shape, sigma_xy):
    h,w = shape
    fy,fx = np.fft.fftfreq(h)[:,None],np.fft.rfftfreq(w)[None,:]
    spectrum = np.fft.rfft2(rng.standard_normal(shape))*np.exp(-2*np.pi**2*((sigma_xy[0]*fx)**2+(sigma_xy[1]*fy)**2))
    field = np.fft.irfft2(spectrum,s=shape)
    return (field-field.mean())/field.std()


def wear_image(ap):
    """R: stone running tracks. G: broad lane wear. B: sweeping and slider scuffs."""
    w,h = ap["ice_finish"]["wear_map_pixels"]
    (x0,y0),(ex,ey) = ap["ice_finish"]["wear_map_origin_m"],ap["ice_finish"]["wear_map_extent_m"]
    rng = np.random.default_rng(ap["seed"])
    tracks,scuffs = np.zeros((h,w)),np.zeros((h,w))
    px,py = w/ex,h/ey

    def plot(field, x, y, weight):
        ix,iy = ((x-x0)*px).astype(int),((y-y0)*py).astype(int)
        keep = (ix>=0)&(ix<w)&(iy>=0)&(iy<h)
        np.add.at(field,(iy[keep],ix[keep]),weight)

    house_x = ap["house_center_m"][0]
    xs = np.linspace(x0,house_x+2.2,int((house_x+2.2-x0)*px*2))
    lanes = np.zeros((h,w))
    yy = y0+(np.arange(h)+.5)/py
    for sheet in ap["arena"]["sheet_centers_y_m"]:
        lanes += np.exp(-((yy-sheet)/1.0)**2)[:,None]
        for _ in range(ap["ice_finish"]["wear_tracks_per_sheet"]):
            end_x,end_y = house_x+rng.normal(0,1.0),sheet+rng.normal(0,.75)
            curl = rng.choice([-1,1])*rng.uniform(.004,.03)
            line = end_y+curl*(xs-end_x)**2-curl*rng.uniform(0,1)*(xs-end_x)
            line = np.where(xs<=end_x,line,np.nan)
            weight = rng.uniform(.08,.3)
            for rail in [-.065,.065]:
                ok = np.isfinite(line)
                plot(tracks,xs[ok],line[ok]+rail,weight)
            # Short transverse sweeps follow some paths.
            for t in rng.integers(0,len(xs),10):
                if not np.isfinite(line[t]): continue
                u = np.linspace(-.2,.2,int(.4*py*2))
                skew = rng.normal(0,.5)
                plot(scuffs,xs[t]+skew*u,line[t]+u,rng.uniform(.02,.07))
        for _ in range(ap["ice_finish"]["wear_scuffs_per_sheet"]):
            cx,cy = rng.normal(house_x-1.5,4.0),sheet+rng.normal(0,1.1)
            u = rng.normal(0,1,60)
            plot(scuffs,cx+.14*u,cy+.03*rng.normal(0,1,60),rng.uniform(.01,.04))
    tracks = np.clip(_blur(tracks,.8)*2.2,0,1)
    scuffs = np.clip(_blur(scuffs,1.6)*7.,0,1)
    broad = _low_frequency(rng,(h,w),(70,26))
    broad = np.clip(.5+.28*broad,0,1)*np.clip(.28+.72*lanes,0,1)
    pixels = np.stack([tracks,broad,scuffs,np.ones_like(broad)],axis=-1).astype(np.float32)
    image = bpy.data.images.new("Curling ice accumulated play wear",w,h,alpha=False)
    image.colorspace_settings.name = "Non-Color"
    image.pixels.foreach_set(pixels.ravel())
    image.update(); image.pack()
    return image


def ice_material_base_ice(cfg):
    ap = cfg["appearance"]; finish = ap["ice_finish"]; arena = ap["arena"]
    mat = bpy.data.materials.new("Continuous refrigerated pebbled curling ice"); mat.use_nodes = True
    n = Nodes(mat); nodes,links = n.nodes,n.links
    shader = nodes.get("Principled BSDF")
    pos = nodes.new("ShaderNodeNewGeometry").outputs["Position"]
    xyz = nodes.new("ShaderNodeSeparateXYZ"); links.new(pos,xyz.inputs[0])
    color = tuple(finish["base_rgb"])

    def paint(mask, tint):
        nonlocal color
        haze = finish["marking_under_ice_haze"]
        color = n.mix(mask,color,tuple(v*(1-haze)+b*haze for v,b in zip(tint,finish["base_rgb"])))

    edge = finish["paint_edge_softening_m"]
    lines = finish["line_rgb"]
    for sheet_y in arena["sheet_centers_y_m"]:
        shift = nodes.new("ShaderNodeVectorMath"); shift.operation = "SUBTRACT"
        shift.inputs[1].default_value = (ap["house_center_m"][0],sheet_y,0); links.new(pos,shift.inputs[0])
        length = nodes.new("ShaderNodeVectorMath"); length.operation = "LENGTH"; links.new(shift.outputs[0],length.inputs[0])
        for radius,tint in zip(ap["house_radii_m"],[finish["blue_paint_rgb"],finish["base_rgb"],finish["red_paint_rgb"],finish["base_rgb"]]):
            paint(n.remap(length.outputs["Value"],radius-edge,radius+edge,1.,0.),tint)
        house_x = ap["house_center_m"][0]
        for axis,offset,half_width,tint in [("Y",sheet_y,.00635,lines),
                ("Y",sheet_y+ap["rink_width_m"]/2,.012,finish["divider_rgb"]),
                ("Y",sheet_y-ap["rink_width_m"]/2,.012,finish["divider_rgb"]),
                ("X",house_x,.00635,lines),("X",house_x+ap["house_radii_m"][0],.00635,lines),
                ("X",house_x-6.40,.0508,finish["red_paint_rgb"])]:
            distance = n.math("ABSOLUTE",n.math("SUBTRACT",xyz.outputs[axis],offset))
            paint(n.remap(distance,half_width-.001,half_width+.001,1.,0.),tint)

    # Accumulated wear, in world metres.
    (x0,y0),(ex,ey) = finish["wear_map_origin_m"],finish["wear_map_extent_m"]
    uv = nodes.new("ShaderNodeVectorMath"); uv.operation = "SUBTRACT"; uv.inputs[1].default_value = (x0,y0,0); links.new(pos,uv.inputs[0])
    uv_scale = nodes.new("ShaderNodeVectorMath"); uv_scale.operation = "DIVIDE"; uv_scale.inputs[1].default_value = (ex,ey,1); links.new(uv.outputs[0],uv_scale.inputs[0])
    wear = nodes.new("ShaderNodeTexImage"); wear.name = "Stone tracks, lane wear, sweep scuffs"
    wear.image = wear_image(ap); wear.extension = "REPEAT"; links.new(uv_scale.outputs[0],wear.inputs["Vector"])
    channels = nodes.new("ShaderNodeSeparateColor"); links.new(wear.outputs["Color"],channels.inputs[0])
    tracks,broad,scuffs = channels.outputs

    frost = n.remap(xyz.outputs["Y"],arena["far_board_y_m"]-finish["board_frost_width_m"],arena["far_board_y_m"],0.,1.,"Frost near the cold boards")
    cloud = n.noise(pos,finish["mesoscale_frost_scale_per_m"],3,.55,"Uneven resurfacing tone")
    tone = n.remap(cloud.outputs["Fac"],.3,.7,1-finish["mesoscale_frost_contrast"],1+finish["mesoscale_frost_contrast"])
    darkened = n.math("SUBTRACT",tone,n.math("MULTIPLY",broad,finish["lane_albedo_delta"]))
    darkened = n.math("SUBTRACT",darkened,n.math("MULTIPLY",tracks,finish["track_albedo_delta"]))
    darkened = n.math("ADD",darkened,n.math("MULTIPLY",scuffs,finish["scuff_albedo_delta"]))
    surface = n.mix(1,color,darkened,"MULTIPLY")
    surface = n.mix(n.math("MULTIPLY",frost,finish["board_frost_mix"]),surface,finish["frost_rgb"])

    # Pebble: two droplet sizes, flattened where stones have run.
    large = n.voronoi(pos,1/ap["pebble_spacing_m"],"SI-scale pebbled ice surface"); large.voronoi_dimensions = "2D"
    small = n.voronoi(pos,1/(.6*ap["pebble_spacing_m"]),"Fine pebble droplets"); small.voronoi_dimensions = "2D"
    dome_large = n.remap(large.outputs["Distance"],.12,.55,1.,0.)
    dome_small = n.math("MULTIPLY",n.remap(small.outputs["Distance"],.10,.48,1.,0.),.55)
    pebble = n.math("MAXIMUM",dome_large,dome_small)
    flatten = n.math("MAXIMUM",n.math("MULTIPLY",tracks,.75),n.math("MULTIPLY",broad,.5))
    pebble = n.math("MULTIPLY",pebble,n.math("SUBTRACT",1.,flatten))
    surface = n.mix(1,surface,n.remap(pebble,0.,1.,1-finish["pebble_albedo_contrast"],1+finish["pebble_albedo_contrast"]),"MULTIPLY")
    speckle = n.noise(pos,finish["pebble_cluster_scale_per_m"],2,.6,"Clusters of pebble droplets, resolved by the camera")
    surface = n.mix(1,surface,n.remap(speckle.outputs["Fac"],.35,.65,1-finish["pebble_cluster_contrast"],1+finish["pebble_cluster_contrast"]),"MULTIPLY")
    links.new(surface,shader.inputs["Base Color"])

    # Ice is never optically flat: slow undulation wobbles reflections, pebble breaks them.
    wave = n.noise(pos,finish["undulation_scale_per_m"],3,.5,"Long-wave resurfacing undulation")
    wave_bump = nodes.new("ShaderNodeBump"); wave_bump.inputs["Strength"].default_value = 1.
    wave_bump.inputs["Distance"].default_value = finish["undulation_height_m"]; links.new(wave.outputs["Fac"],wave_bump.inputs["Height"])
    bump = nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = finish["pebble_normal_strength"]
    bump.inputs["Distance"].default_value = ap["pebble_height_m"]
    links.new(pebble,bump.inputs["Height"]); links.new(wave_bump.outputs[0],bump.inputs["Normal"])
    links.new(bump.outputs[0],shader.inputs["Normal"]); links.new(bump.outputs[0],shader.inputs["Coat Normal"])

    shader.inputs["Roughness"].default_value = finish["base_roughness"]
    shader.inputs["IOR"].default_value = 1.31
    shader.inputs["Coat Weight"].default_value = finish["coat_weight"]
    shader.inputs["Coat IOR"].default_value = finish["coat_ior"]
    low,high = finish["coat_roughness_range"]
    coat_rough = n.remap(pebble,0.,1.,low,high)
    coat_rough = n.math("ADD",coat_rough,n.math("MULTIPLY",n.math("MAXIMUM",scuffs,frost),finish["scuff_roughness_delta"]))
    links.new(coat_rough,shader.inputs["Coat Roughness"])
    return mat


def create_ice(cfg, substrate, cube):
    """Opaque white ice approximation; bump detail leaves support exactly flat."""
    return cube('Continuous optically pebbled ice', (0,0,-.06), (48,24,.12), substrate)


def look_at(obj,target):
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()


def material(name,color,roughness=.4,metallic=0.):
    mat=bpy.data.materials.new(name);mat.use_nodes=True
    p=mat.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Roughness'].default_value=roughness
    p.inputs['Metallic'].default_value=metallic
    return mat


def cube(name,location,dimensions,mat,bevel=0.):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location)
    obj=bpy.context.object;obj.name,obj.dimensions=name,dimensions
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj.data.materials.append(mat)
    if bevel:
        mod=obj.modifiers.new('Manufactured edge radius','BEVEL');mod.width,mod.segments=bevel,3
        obj.modifiers.new('Weighted corner normals','WEIGHTED_NORMAL')
    return obj


def noise_surface(name,color,roughness,scale,bump_distance):
    mat=material(name,color,roughness);nodes,links=mat.node_tree.nodes,mat.node_tree.links
    shader=nodes.get('Principled BSDF');coord=nodes.new('ShaderNodeTexCoord')
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=scale
    noise.inputs['Detail'].default_value=2;links.new(coord.outputs['Object'],noise.inputs['Vector'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.16
    bump.inputs['Distance'].default_value=bump_distance;links.new(noise.outputs['Fac'],bump.inputs['Height'])
    links.new(bump.outputs[0],shader.inputs['Normal'])
    return mat


def rod(name,start,end,radius,mat):
    delta=Vector(end)-Vector(start)
    bpy.ops.mesh.primitive_cylinder_add(vertices=12,radius=radius,depth=delta.length,location=(Vector(start)+Vector(end))/2)
    obj=bpy.context.object;obj.name=name;obj.rotation_euler=delta.to_track_quat('Z','Y').to_euler();obj.data.materials.append(mat)
    return obj


def lighting(cfg):
    ap=cfg['appearance'];arena=ap['arena'];power=ap['lighting_power_w']
    world=bpy.data.worlds.new('Cool neutral indoor ambient');world.use_nodes=True
    world.node_tree.nodes['Background'].inputs[0].default_value=(*arena['world_rgb'],1)
    world.node_tree.nodes['Background'].inputs[1].default_value=arena['world_strength'];bpy.context.scene.world=world
    housing=material('Ceiling luminaire housing',(.20,.22,.23),.36,.72)
    panel=material('Opal luminaire diffuser',(.72,.75,.76),.31)
    shader=panel.node_tree.nodes.get('Principled BSDF');shader.inputs['Emission Color'].default_value=(.97,.98,1,1);shader.inputs['Emission Strength'].default_value=arena['fixture_emission']
    # Rows of lengthwise battens over every sheet: the polished stones and ice reflect them.
    width,height=arena['fixture_size_m']
    for y in arena['fixture_rows_y_m']:
        for x in arena['fixture_columns_x_m']:
            name=f'Ceiling batten {x} {y}'
            data=bpy.data.lights.new(name,'AREA');data.energy=power['ceiling_batten']*(1+.12*math.sin(7.3*x+3.1*y))
            data.shape,data.size,data.size_y,data.color='RECTANGLE',width,height,(.97,.98,1.)
            obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj);obj.location=(x,y,4.95)
            shell=cube(name+' / metal housing',(0,0,.065),(width+.08,height+.08,.08),housing,.015);shell.parent=obj
            diffuser=cube(name+' / luminous opal panel',(0,0,.018),(width,height,.012),panel,.003);diffuser.parent=obj
            # Both meshes lie behind the emitting plane; the area emitter faces local -Z.
    # Old walkway downlights, unevenly spaced, leave scallops on the block wall.
    for i,(x,watts) in enumerate(arena['walkway_downlights']):
        data=bpy.data.lights.new(f'Walkway downlight {i}','SPOT');data.energy=watts*power['walkway_downlight_scale']
        data.spot_size,data.spot_blend,data.shadow_soft_size=math.radians(112),.8,.09;data.color=(1.,.90,.76)
        obj=bpy.data.objects.new(data.name,data);bpy.context.collection.objects.link(obj);obj.location=(x,arena['wall_y_m']-.75,4.3);look_at(obj,(x,arena['wall_y_m']-.1,1.2))
        obj.visible_camera=obj.visible_glossy=obj.visible_transmission=False
    # Warm spill from the lit gallery behind the real glazing.
    for x in [-6.6,5.3]:
        data=bpy.data.lights.new(f'Viewing gallery light {x}','AREA')
        data.energy=power['gallery_spill']
        data.shape,data.size,data.size_y='RECTANGLE',2.8,1.0
        data.color=(1.0,.90,.74)
        obj=bpy.data.objects.new(data.name,data);bpy.context.collection.objects.link(obj)
        obj.location=(x,arena['wall_y_m']-.27,2.35);look_at(obj,(x,0,.2))
        obj.visible_camera=obj.visible_glossy=False


OFFSETS = {"R01":(0,0,0),"B01":(.273,.139,.051),"Y01":(.514,.297,.121),"G01":(.731,.422,.186)}


def granite_material_polished(name, finish):
    material,shader = _principled(name+" / polished granite body")
    n = Nodes(material)
    coord = n.nodes.new("ShaderNodeTexCoord")
    offset = n.nodes.new("ShaderNodeVectorMath"); offset.operation = "ADD"
    offset.inputs[1].default_value = OFFSETS[name]
    n.links.new(coord.outputs["Object"],offset.inputs[0])
    z = n.nodes.new("ShaderNodeSeparateXYZ"); n.links.new(coord.outputs["Object"],z.inputs[0])
    # Warped cells give interlocking crystals rather than round pepper dots.
    warp = n.nodes.new("ShaderNodeVectorMath"); warp.operation = "ADD"
    n.links.new(offset.outputs[0],warp.inputs[0])
    wobble = n.noise(offset.outputs[0],90,3,.6,"Crystal boundary warp")
    scale = n.nodes.new("ShaderNodeVectorMath"); scale.operation = "SCALE"
    scale.inputs["Scale"].default_value = finish["granite_warp_m"]
    n.links.new(wobble.outputs["Color"],scale.inputs[0]); n.links.new(scale.outputs[0],warp.inputs[1])
    pos = warp.outputs[0]
    dark,mid,light = finish["granite_dark_rgb"],finish["granite_mid_rgb"],finish["granite_light_rgb"]
    stops = [(0.,dark),(finish["granite_dark_fraction"],mid),(1-finish["granite_light_fraction"],light)]
    coarse = n.ramp(n.luma(n.voronoi(pos,1/finish["granite_crystal_spacing_m"],"Interlocking mineral crystals").outputs["Color"]),stops,True,"Biotite, matrix, feldspar")
    fine = n.ramp(n.luma(n.voronoi(pos,1/(.45*finish["granite_crystal_spacing_m"]),"Fine mineral crystals").outputs["Color"]),stops,True)
    mineral = n.mix(finish["granite_fine_mix"],coarse,fine)
    cloud = n.noise(offset.outputs[0],finish["granite_cloud_scale_per_m"],3,.55,"Broad mineral banding")
    mineral = n.mix(1,mineral,n.remap(cloud.outputs["Fac"],.3,.7,1-finish["granite_cloud_contrast"],1+finish["granite_cloud_contrast"]),"MULTIPLY")
    # Ground striking band at the widest part, feathered into the polished shoulders.
    centre,(inner,outer) = finish["strike_band_centre_m"],finish["strike_band_half_width_m"]
    band = n.remap(n.math("ABSOLUTE",n.math("SUBTRACT",z.outputs["Z"],centre)),inner,outer,1.,0.,"Ground striking band")
    mineral = n.mix(n.math("MULTIPLY",band,finish["strike_band_pale"]),mineral,finish["strike_band_rgb"])
    pits = n.noise(offset.outputs[0],520,2,.5,"Contact chips and wear")
    chips = n.math("MULTIPLY",band,n.remap(pits.outputs["Fac"],.64,.72))
    mineral = n.mix(n.math("MULTIPLY",chips,.8),mineral,finish["strike_band_chip_rgb"])
    n.links.new(mineral,shader.inputs["Base Color"])
    # Mirror polish, broken by handling scuffs and by running wear low on the body.
    polish = n.remap(n.noise(offset.outputs[0],260,2).outputs["Fac"],.3,.7,finish["granite_roughness_min"],finish["granite_roughness_max"])
    scuff_noise = n.noise(offset.outputs[0],finish["handling_scuff_scale_per_m"],4,.62,"Handling scuffs on the polish")
    scuffs = n.remap(scuff_noise.outputs["Fac"],.56,.74,0.,finish["handling_scuff_roughness"])
    polish = n.math("ADD",polish,scuffs)
    scuffed = n.remap(z.outputs["Z"],.010,.030,finish["lower_shoulder_roughness"],0.,"Lower shoulder running wear")
    rough = n.math("MAXIMUM",polish,scuffed)
    rough = n.mix(band,rough,(finish["strike_band_roughness"],)*3)
    rough = n.math("MAXIMUM",rough,n.math("MULTIPLY",chips,.8))
    n.links.new(rough,shader.inputs["Roughness"])
    shader.inputs["IOR"].default_value = 1.54
    relief = n.nodes.new("ShaderNodeBump"); relief.inputs["Distance"].default_value = .00006
    n.links.new(n.math("MULTIPLY",band,.6),relief.inputs["Strength"]); n.links.new(pits.outputs["Fac"],relief.inputs["Height"])
    n.links.new(relief.outputs[0],shader.inputs["Normal"])
    material["modification"] = "Procedural mineral field in attached coordinates, mirror-polished shoulders, ground striking band; no atlas"
    return material


def polymer_material_polished(name, color, finish):
    material,shader = _principled(name+" / molded handle and cap")
    n = Nodes(material)
    coord = n.nodes.new("ShaderNodeTexCoord")
    grain = n.noise(coord.outputs["Object"],700,2,.5,"Molded polymer grain")
    wear = n.noise(coord.outputs["Object"],45,3,.55,"Handling wear")
    tone = n.mix(1,color,n.remap(wear.outputs["Fac"],.35,.65,.9,1.04),"MULTIPLY")
    n.links.new(tone,shader.inputs["Base Color"])
    variation = finish["handle_roughness_variation"]/2
    n.links.new(n.remap(grain.outputs["Fac"],.3,.7,finish["handle_roughness"]-variation,finish["handle_roughness"]+variation),shader.inputs["Roughness"])
    shader.inputs["Coat Weight"].default_value = finish["handle_coat_weight"]
    shader.inputs["Coat Roughness"].default_value = finish["handle_coat_roughness"]
    shader.inputs["IOR"].default_value = 1.5
    material["source_author"],material["source_license"] = "FilinMX","CC BY-NC 4.0"
    material["modification"] = "Asset handle/cap geometry retained; plain pigment replaces the printed atlas and its logos"
    return material


def ice_material_debris(cfg):
    mat = ice_material_base_ice(cfg)
    finish = cfg["appearance"]["ice_finish"]
    n = Nodes(mat); nodes,links = n.nodes,n.links
    shader = nodes.get("Principled BSDF")
    base = shader.inputs["Base Color"].links[0].from_socket
    pos = nodes.new("ShaderNodeNewGeometry").outputs["Position"]
    cells = n.voronoi(pos,finish["debris_cells_per_m"],"Broom debris on the ice"); cells.voronoi_dimensions = "2D"
    keep = n.math("LESS_THAN",n.luma(cells.outputs["Color"]),finish["debris_fraction"])
    size = n.math("MULTIPLY",finish["debris_radius_m"]*finish["debris_cells_per_m"],n.math("ADD",.4,n.luma(cells.outputs["Color"])))
    dot = n.math("LESS_THAN",cells.outputs["Distance"],size)
    debris = n.math("MULTIPLY",keep,dot,"Debris mask")
    # Sprayed paint and flooded white layers are never perfectly even: decimetre-scale mottling.
    mottle = n.noise(pos,finish["mottle_scale_per_m"],4,.62,"Uneven paint and flood layers")
    tone = n.remap(mottle.outputs["Fac"],.3,.7,1-finish["mottle_contrast"],1+finish["mottle_contrast"])
    surface = n.mix(1,base,tone,"MULTIPLY")
    links.new(n.mix(debris,surface,finish["debris_rgb"]),shader.inputs["Base Color"])
    mat["modification"] = "Pebbled ice plus paint mottling and sparse broom debris; tone, frost and gloss tuned in configuration"
    return mat


def rink(cfg):
    ap = cfg['appearance']; arena = ap['arena']; board_y = arena['far_board_y_m']; wall_y = arena['wall_y_m']
    create_ice(cfg,ice_material_debris(cfg),cube)
    rubber = walkway_floor('Interlocking rubber walkway matting')
    steel = material('Brushed galvanized steel',(.30,.33,.34),.38,.78)
    dark = material('Powder coated charcoal metal',(.028,.037,.041),.43,.12)
    wall = painted_block_wall('Painted concrete block wall',arena['wall_rgb'],arena['wall_band_rgb'],arena['wall_band_top_m'],arena['wall_block_tile_m'],arena)
    # Low charcoal foam bumper on the far side line, in manufactured lengths.
    foam = noise_surface('Charcoal high-density foam bumper',arena['bumper_rgb'],.72,160,.0004)
    side,length = arena['bumper_section_m'],arena['bumper_length_m']
    for i in range(-12,12):
        cube(f'Far bumper length {i}',(i*length+length/2,board_y+.004*((i*5)%3-1),side/2),(length-.004,side,side),foam,.012)
    far_board_dressing(cfg,cube,material,rod,dark,steel)
    cube('Raised continuous rubber service walkway',(0,(board_y+wall_y)/2,.005),(48,wall_y-board_y-.12,.15),rubber)
    rear_wall = cube('Arena rear wall',(0,wall_y,2.7),(48,.22,5.5),wall)
    ceiling = noise_surface('Off-white acoustic roof underside',(.48,.49,.47),.86,110,.0001)
    cube('Full arena ceiling',(0,-.5,arena['ceiling_height_m']+.07),(48,23,.14),ceiling)
    cube('Arena near wall behind camera',(0,-12.,2.7),(48,.22,5.5),wall)
    for x in [-24.,24.]:
        cube(f'Arena end wall {x}',(x,-.5,2.7),(.22,23,5.5),wall)
        cube(f'End bumper {x}',(x-.2*x/abs(x),-2.2,side/2),(side,19.7,side),foam,.012)
    for y in [-10,-5,0,5,9.3]:
        cube(f'Longitudinal roof beam {y}',(0,y,5.25),(48,.12,.28),steel,.006)
    for x in range(-20,24,4):
        cube(f'Cross roof purlin {x}',(x,-.5,5.40),(.10,22.5,.15),steel,.004)
    viewing_gallery(cfg,rear_wall,cube,material,dark)
    walkway_dressing(cfg,cube,material,rod)
    # Service ventilation remains physically attached to the wall.
    cube('Upper galvanized ventilation trunk',(0,wall_y-.32,3.80),(48,.30,.30),steel,.018)
    for x in [-5,1,7]:
        cube(f'Ventilation diffuser {x}',(x,wall_y-.49,3.79),(.85,.035,.23),dark,.005)
        for j in range(9):
            cube(f'Diffuser louver {x} {j}',(x-.37+j*.092,wall_y-.515,3.79),(.015,.018,.18),steel,.002)
    door(cfg,cube,material,rod)
    wall_services(cfg,cube,material,rod)
    bpy.data.orphans_purge(do_recursive=True)
    return {'stone_diameter_m':2*cfg['physics']['radius_m'],'stone_mass_kg':19.5,
        'sheet_width_m':ap['rink_width_m'],'sheet_length_m':ap['rink_length_m'],
        'sheet_centers_y_m':arena['sheet_centers_y_m'],'house_outer_diameter_m':3.66,
        'perimeter_bumper_height_m':side,'bench_seat_height_m':.561,'ceiling_height_m':arena['ceiling_height_m'],
        'ice_pebble_spacing_m':ap['pebble_spacing_m'],'ice_pebble_height_m':ap['pebble_height_m'],
        'appearance_preset':ap['preset'],
        'background_method':'Continuous 3D two-sheet ice and club arena, scanned PBR surfaces and props, shared perspective and lighting; no photograph, image plane, lettering or brand mark.'}


def camera_finish(scene, cfg):
    """Lens and sensor response of a real camera, applied after rendering; no scene content changes."""
    lens = cfg['appearance']['camera_finish']
    scene.use_nodes = True
    tree = scene.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    layers = tree.nodes.new('CompositorNodeRLayers')
    distortion = tree.nodes.new('CompositorNodeLensdist')
    distortion.inputs[1].default_value = lens['barrel_distortion']
    distortion.inputs[2].default_value = lens['lateral_dispersion']
    distortion.use_fit = False
    tree.links.new(layers.outputs['Image'],distortion.inputs['Image'])
    glare = tree.nodes.new('CompositorNodeGlare')
    glare.glare_type,glare.quality = 'FOG_GLOW','HIGH'
    glare.threshold,glare.mix,glare.size = lens['bloom_threshold'],lens['bloom_mix'],lens['bloom_size']
    tree.links.new(distortion.outputs['Image'],glare.inputs['Image'])
    # Natural vignetting: a soft elliptical falloff towards the corners.
    mask = tree.nodes.new('CompositorNodeEllipseMask')
    mask.mask_width,mask.mask_height = lens['vignette_ellipse']
    blur = tree.nodes.new('CompositorNodeBlur')
    blur.filter_type,blur.use_relative = 'FAST_GAUSS',True
    blur.factor_x = blur.factor_y = lens['vignette_softness_percent']
    tree.links.new(mask.outputs['Mask'],blur.inputs['Image'])
    falloff = tree.nodes.new('CompositorNodeMapRange'); falloff.use_clamp = True
    falloff.inputs['To Min'].default_value = 1-lens['vignette_strength']
    tree.links.new(blur.outputs['Image'],falloff.inputs['Value'])
    shade = tree.nodes.new('CompositorNodeMixRGB'); shade.blend_type = 'MULTIPLY'
    shade.inputs['Fac'].default_value = 1.
    tree.links.new(glare.outputs['Image'],shade.inputs[1])
    tree.links.new(falloff.outputs['Value'],shade.inputs[2])
    out = tree.nodes.new('CompositorNodeComposite')
    tree.links.new(shade.outputs['Image'],out.inputs['Image'])
    return {'barrel_distortion':lens['barrel_distortion'],'lateral_dispersion':lens['lateral_dispersion'],
        'bloom':'fog glow above scene-linear %.2f, mix %.2f'%(lens['bloom_threshold'],lens['bloom_mix']),
        'vignette_strength':lens['vignette_strength']}
