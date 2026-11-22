"""Home activity table in a daylit room: twin ramps, numbered resin balls, handled laminate, window-only daylight.

architecture(), build_balls() and lighting() build the look in layers: the base apparatus, the
photographic domestic look, the worn table and finite room, the domestic background, the chair-free
activity table with measured props, numbered resin balls with a light laminate table, the cleared sill and
legible floor, and finally window-only daylight through a sky portal with scanned wall paint and handled
laminate. Helpers suffixed with a layer name (architecture_clear_sill, lighting_domestic, ...) are the
earlier layers the final functions build on. Objects and materials that a later layer removes or
replaces are not built in the first place, so the layers load only assets that reach the final scene;
the base, ramp and trestles get their plywood material in architecture_worn_table(). All running-surface
coordinates remain solver exact.
"""
from __future__ import annotations

import math
import random
import sys as _scene_sys
from pathlib import Path as _ScenePath, Path

import bpy
from mathutils import Vector, Matrix
from scene_config import ramp_mesh, profile, surface
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))


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


def paint_material(name,rgb):
    mat=material(name,rgb,.78);n,l=mat.node_tree.nodes,mat.node_tree.links
    noise=n.new("ShaderNodeTexNoise");noise.inputs["Scale"].default_value=650;noise.inputs["Detail"].default_value=2
    tc=n.new("ShaderNodeTexCoord");l.new(tc.outputs["Object"],noise.inputs["Vector"])
    bump=n.new("ShaderNodeBump");bump.inputs["Strength"].default_value=.14;bump.inputs["Distance"].default_value=.00007
    l.new(noise.outputs["Fac"],bump.inputs["Height"]);l.new(bump.outputs["Normal"],n.get("Principled BSDF").inputs["Normal"])
    return mat


def uv_metric(obj, seed=0, repeat=1.5, grain_axis="X"):
    # Cubes carry a default UVMap. Explicitly replace it, including active_render.
    while obj.data.uv_layers: obj.data.uv_layers.remove(obj.data.uv_layers[0])
    uv=obj.data.uv_layers.new(name=f"Measured {repeat:g} m unmirrored grain")
    uv.active_render=True
    rng=random.Random(seed);ox,oy=rng.random()*2,rng.random()*2
    for poly in obj.data.polygons:
        normal=obj.matrix_world.to_3x3()@poly.normal
        for idx in poly.loop_indices:
            p=obj.matrix_world@obj.data.vertices[obj.data.loops[idx].vertex_index].co
            if grain_axis=="Z":u,v=(p.x if abs(normal.y)>.5 else p.y),p.z
            elif abs(normal.z)>.5:u,v=p.y,p.x
            elif abs(normal.y)>.5:u,v=p.z,p.x
            else:u,v=p.z,p.y
            uv.data[idx].uv=(u/repeat+ox,v/repeat+oy)


def pbr_wood(asset_root, asset, repeat, name, value=1., saturation=.8, rough=(.34,.52), normal=.16):
    root=asset_root/"polyhaven"/asset
    files={role:next(iter(sorted(root.glob(f"*{key}*.jpg")))) for role,key in
           [("color","_diff_"),("roughness","_rough_"),("normal","_nor_gl_")]}
    mat=material(name,(.5,.4,.3),.45);n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get("Principled BSDF")
    tc=n.new("ShaderNodeTexCoord")
    for role,path in files.items():
        tex=n.new("ShaderNodeTexImage");tex.image=bpy.data.images.load(str(path),check_existing=True)
        l.new(tc.outputs["UV"],tex.inputs["Vector"])
        if role=="color":
            hs=n.new("ShaderNodeHueSaturation");hs.inputs["Saturation"].default_value=saturation;hs.inputs["Value"].default_value=value
            l.new(tex.outputs["Color"],hs.inputs["Color"]);l.new(hs.outputs["Color"],bs.inputs["Base Color"])
        elif role=="roughness":
            tex.image.colorspace_settings.name="Non-Color";mr=n.new("ShaderNodeMapRange")
            mr.inputs["To Min"].default_value=rough[0];mr.inputs["To Max"].default_value=rough[1]
            l.new(tex.outputs["Color"],mr.inputs["Value"]);l.new(mr.outputs["Result"],bs.inputs["Roughness"])
        else:
            tex.image.colorspace_settings.name="Non-Color";nm=n.new("ShaderNodeNormalMap");nm.inputs["Strength"].default_value=normal
            l.new(tex.outputs["Color"],nm.inputs["Color"]);l.new(nm.outputs["Normal"],bs.inputs["Normal"])
    bs.inputs["Coat Weight"].default_value=.07;bs.inputs["Coat Roughness"].default_value=.36
    return mat,{k:str(v) for k,v in files.items()}


def timber(name,loc,dims,mat,seed,repeat=1.5,bevel=.001,axis="X"):
    o=box(name,loc,dims,mat,bevel);uv_metric(o,seed,repeat,axis);return o


def ply_edge():
    mat=material("Seven real-scale birch plies, satin sawn edge",(.58,.43,.28),.61)
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get("Principled BSDF");tc=n.new("ShaderNodeTexCoord")
    sep=n.new("ShaderNodeSeparateXYZ");l.new(tc.outputs["UV"],sep.inputs[0])
    mul=n.new("ShaderNodeMath");mul.operation="MULTIPLY";mul.inputs[1].default_value=7.;l.new(sep.outputs["Y"],mul.inputs[0])
    pi=n.new("ShaderNodeMath");pi.operation="MULTIPLY";pi.inputs[1].default_value=math.pi*2;l.new(mul.outputs[0],pi.inputs[0])
    wave=n.new("ShaderNodeMath");wave.operation="SINE";l.new(pi.outputs[0],wave.inputs[0])
    ramp=n.new("ShaderNodeValToRGB");ramp.color_ramp.elements[0].position=.05;ramp.color_ramp.elements[1].position=.85
    ramp.color_ramp.elements[0].color=tuple(linear(c) for c in (.58,.44,.29))+(1,)
    ramp.color_ramp.elements[1].color=tuple(linear(c) for c in (.79,.66,.48))+(1,)
    l.new(wave.outputs[0],ramp.inputs[0]);l.new(ramp.outputs[0],bs.inputs["Base Color"])
    return mat


def side_laminations(cfg,mat):
    r=cfg["physics"]["ramp"];pts=profile(cfg);t=r["board_thickness_m"]
    for side in [-1,1]:
        verts=[]
        for x,z in pts:verts.extend([(x,side*(r["width_m"]/2+.000015),z),(x,side*(r["width_m"]/2+.000015),z-t)])
        faces=[(2*i,2*i+1,2*i+3,2*i+2) for i in range(len(pts)-1)]
        obj=mesh_object("Exposed plywood edge with seven 2 mm layers",verts,faces,mat);uv=obj.data.uv_layers.new()
        for poly in obj.data.polygons:
            for idx in poly.loop_indices:
                vi=obj.data.loops[idx].vertex_index;uv.data[idx].uv=(verts[vi][0],float(vi%2))


def append_meshes(path,names,asset_root):
    before=set(bpy.data.images)
    with bpy.data.libraries.load(str(path),link=False) as (src,dst):dst.objects=[n for n in src.objects if n in names]
    result=[]
    for obj in dst.objects:
        if obj:
            bpy.context.collection.objects.link(obj);result.append(obj)
    for img in set(bpy.data.images)-before:
        if img.packed_file:continue
        resolved=Path(bpy.path.abspath(img.filepath))
        if not resolved.is_file():
            candidates=list(asset_root.rglob(resolved.name))
            if not candidates:raise FileNotFoundError(resolved)
            img.filepath=str(candidates[0]);img.reload()
    return result


def bounds(objects):
    p=[o.matrix_world@Vector(c) for o in objects for c in o.bound_box]
    return Vector([min(v[i] for v in p) for i in range(3)]),Vector([max(v[i] for v in p) for i in range(3)])


def place_group(objects,xy,bottom,yaw=0.,height=None):
    bpy.context.view_layer.update();lo,hi=bounds(objects);center=(lo+hi)/2
    scale=height/(hi.z-lo.z) if height else 1.
    transform=Matrix.Rotation(yaw,4,"Z")@Matrix.Scale(scale,4)
    for o in objects:
        old=o.matrix_world.copy();o.parent=None;o.matrix_world=transform@Matrix.Translation(-Vector((center.x,center.y,lo.z)))@old
        o.location+=Vector((xy[0],xy[1],bottom))
    bpy.context.view_layer.update()


def fabric_material(assets):
    mat=material("Natural undyed linen curtain",(.76,.73,.65),.9);n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get("Principled BSDF")
    tc=n.new("ShaderNodeTexCoord");mapping=n.new("ShaderNodeVectorMath");mapping.operation="SCALE";mapping.inputs[3].default_value=5.
    l.new(tc.outputs["Object"],mapping.inputs[0])
    tex=n.new("ShaderNodeTexImage");tex.image=bpy.data.images.load(str(assets/"ambientcg/Fabric034/Fabric034_SQ_Color.jpg"),check_existing=True)
    l.new(mapping.outputs["Vector"],tex.inputs[0]);mix=n.new("ShaderNodeMixRGB");mix.blend_type="MULTIPLY";mix.inputs[0].default_value=.6
    mix.inputs[2].default_value=(.75,.71,.63,1);l.new(tex.outputs["Color"],mix.inputs[1]);l.new(mix.outputs[0],bs.inputs["Base Color"])
    bump=n.new("ShaderNodeBump");bump.inputs["Strength"].default_value=.12;bump.inputs["Distance"].default_value=.00012
    l.new(tex.outputs["Color"],bump.inputs["Height"]);l.new(bump.outputs[0],bs.inputs["Normal"])
    bs.inputs["Sheen Weight"].default_value=.22;bs.inputs["Subsurface Weight"].default_value=.025
    return mat


def curtain_photographic(name,x0,x1,assets,seed):
    rng=random.Random(seed);mat=fabric_material(assets);verts=[];nx,nz=100,32
    for iz in range(nz+1):
        v=iz/nz;z=.10+v*2.30
        for ix in range(nx+1):
            u=ix/nx;x=x0+(x1-x0)*u
            fold=math.sin(u*math.pi*2*6+.2*math.sin(v*2))* .034+math.sin(u*math.pi*4+1.1)*.008
            verts.append((x,1.20+fold*(.85+.15*v),z+.003*math.sin(u*20)*(1-v)))
    faces=[(j*(nx+1)+i,j*(nx+1)+i+1,(j+1)*(nx+1)+i+1,(j+1)*(nx+1)+i) for j in range(nz) for i in range(nx)]
    o=mesh_object(name,verts,faces,mat)
    for p in o.data.polygons:p.use_smooth=True
    sol=o.modifiers.new("Linen cloth thickness 0.6 mm","SOLIDIFY");sol.thickness=.0006
    return o


def architecture_photographic(cfg,assets):
    r=cfg["physics"]["ramp"];top=r["table_top_z_m"];t=r["board_thickness_m"]
    # The base, ramp and trestles get their plywood material in architecture_worn_table().
    ply=ply_edge();dark=material("Dark timber end grain",(.27,.19,.125),.6)
    # Base sits at exactly the frozen collision baseline height.
    timber("Apparatus birch plywood base",(0.,0.,top+.008),(1.24,.29,.016),None,287,1.83,.0006)
    verts,faces=ramp_mesh(cfg);o=mesh_object("Continuous 14 mm oak-veneered ramp running surface",verts,faces,None);uv_metric(o,943,1.83)
    bevel=o.modifiers.new("Sanded outside edge radius 0.3 mm, running lane untouched","BEVEL");bevel.width=.0003;bevel.segments=3;bevel.limit_method="ANGLE"
    side_laminations(cfg,ply)
    # Open construction. Transverse trestles genuinely touch the board underside.
    for side in [-1,1]:
        for xx in [.29,.575]:
            x=xx*side;w=.018;z0=top+.016
            za=surface(cfg,x-w/2)[0]-t;zb=surface(cfg,x+w/2)[0]-t
            vv=[(xa,y,z) for y in [-.112,.112] for xa,z in [(x-w/2,z0),(x+w/2,z0),(x+w/2,zb),(x-w/2,za)]]
            ob=mesh_object("Solid transverse plywood trestle",vv,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],None)
            uv_metric(ob,100+round(xx*100)+side,1.83,"Z")
            b=ob.modifiers.new("Sanded trestle edges","BEVEL");b.width=.00035;b.segments=2
    metal=material("Used zinc countersunk fasteners",(.46,.45,.42),.37);metal.node_tree.nodes.get("Principled BSDF").inputs["Metallic"].default_value=.8
    slot=material("Recess in screw heads",(.13,.12,.11),.9)
    for x in [-.57,.57]:
        for y in [-.137,.137]:
            bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=.0026,depth=.00035,location=(x,y,top+.01608))
            bpy.context.object.name="Countersunk base screw outside lane";bpy.context.object.data.materials.append(metal)
            ob=box("Cross recess in fastener",(x,y,top+.01627),(.0035,.00045,.00003),slot);ob.rotation_euler.z=.34
            ob=box("Cross recess in fastener",(x,y,top+.01628),(.00045,.0035,.00003),slot);ob.rotation_euler.z=.34
    wall=paint_material("Warm mineral-painted interior wall",(.76,.76,.71));trim=paint_material("Warm off-white window joinery",(.84,.84,.79))
    floor=material("Matte warm domestic floor",(.36,.29,.23),.76)
    box("Continuous room floor",(0,0,-.035),(8,8,.07),floor)
    # Large window, real reveal depth, sill and glazing opening.
    for name,x0,x1,z0,z1 in [("Left wall",-4.,-1.60,0.,3.),("Right wall",-.34,4.,0.,3.),("Wall below window",-1.60,-.34,0.,.82),("Wall above window",-1.60,-.34,2.28,3.)]:
        box(name,((x0+x1)/2,1.42,(z0+z1)/2),(x1-x0,.18,z1-z0),wall,.0008)
    for x in [-1.60,-.34]:box("Window painted timber jamb",(x,1.35,1.55),(.05,.23,1.50),trim,.0018)
    for z in [.82,2.28]:box("Window sill or header",(-.97,1.31,z),(1.37,.32,.05),trim,.002)
    box("Window central mullion",(-.97,1.42,1.55),(.035,.05,1.42),trim,.001)
    box("Rear skirting",(0,1.31,.055),(8,.04,.11),trim,.0018)
    curtain_photographic("Natural linen drawn left",-1.85,-1.43,assets,12)
    curtain_photographic("Natural linen drawn right",-.49,-.18,assets,14)
    # Real scanned plant, outside the apparatus and its moving envelope.
    bpy.ops.import_scene.gltf(filepath=str(assets/"polyhaven_models/potted_plant_02/potted_plant_02_1k.gltf"))
    plant=[o for o in bpy.context.selected_objects if o.type=="MESH"]
    place_group(plant,(-.63,.82),.846,math.radians(-15),height=.26)
    return {"table_m":[1.72,.85,.76],"device_m":[1.20,.25,.12],"ball_diameter_m":.05,
        "central_horizontal_m":r["central_length_m"],"toe_transition_m":r["toe_transition_m"],"board_thickness_m":t,
        "wood_repeat_m":{"ramp":1.83,"table":1.5},"pbr_files":{"ramp":None,"table":None},
        "running_surface":"Identical vertices and coordinates to frozen physical surface; no displacement",
        "background":"Shared 3D room, real window reveal, linen curtains, CC0 scanned plant",
        "asset_licenses":"Poly Haven and ambientCG CC0; see realism_assets.json"}


def remove(objects):
    for obj in list(objects):bpy.data.objects.remove(obj,do_unlink=True)


def clear_unused():
    # Do not pack unused first-pass wood maps into the new standalone scenes.
    for collection in [bpy.data.meshes,bpy.data.curves,bpy.data.materials,bpy.data.images]:
        for item in list(collection):
            if item.users==0:collection.remove(item)


def handling_wood(mat,seed):
    """Restrained coating variation, pores and handling; never displace the board."""
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get('Principled BSDF')
    tc=n.new('ShaderNodeTexCoord');tc.name='Object-local real metre coordinates'
    coarse=n.new('ShaderNodeTexNoise');coarse.inputs['Scale'].default_value=8.5;coarse.inputs['Detail'].default_value=2
    coarse.inputs['Roughness'].default_value=.72;l.new(tc.outputs['Object'],coarse.inputs['Vector'])
    # A few percent in albedo; a broader and more visible change in coating gloss.
    prev=bs.inputs['Base Color'].links[0].from_socket
    tint=n.new('ShaderNodeMapRange');tint.inputs['To Min'].default_value=.94;tint.inputs['To Max'].default_value=1.02
    l.new(coarse.outputs['Fac'],tint.inputs['Value']);mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1.
    l.new(prev,mix.inputs[1]);l.new(tint.outputs['Result'],mix.inputs[2]);l.new(mix.outputs[0],bs.inputs['Base Color'])
    previous=bs.inputs['Roughness'].links[0].from_socket
    add=n.new('ShaderNodeMath');add.operation='MULTIPLY_ADD';add.inputs[1].default_value=.15;add.inputs[2].default_value=-.06
    l.new(coarse.outputs['Fac'],add.inputs[0]);sum_node=n.new('ShaderNodeMath');sum_node.operation='ADD'
    l.new(previous,sum_node.inputs[0]);l.new(add.outputs[0],sum_node.inputs[1]);l.new(sum_node.outputs[0],bs.inputs['Roughness'])
    bs.inputs['Coat Weight'].default_value=.015;bs.inputs['Coat Roughness'].default_value=.44


def real_ply_edge():
    mat=material('Sawn birch edge, thin irregular adhesive lines',(.72,.60,.43),.66)
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get('Principled BSDF');tc=n.new('ShaderNodeTexCoord')
    sep=n.new('ShaderNodeSeparateXYZ');l.new(tc.outputs['UV'],sep.inputs[0])
    stretch=n.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY';stretch.inputs[1].default_value=(45,2.8,1);l.new(tc.outputs['UV'],stretch.inputs[0])
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=1.;noise.inputs['Detail'].default_value=3.;l.new(stretch.outputs[0],noise.inputs[0])
    warp=n.new('ShaderNodeMath');warp.operation='MULTIPLY_ADD';warp.inputs[1].default_value=.045;warp.inputs[2].default_value=-.0225;l.new(noise.outputs['Fac'],warp.inputs[0])
    z=n.new('ShaderNodeMath');z.operation='MULTIPLY_ADD';z.inputs[1].default_value=7;l.new(sep.outputs['Y'],z.inputs[0]);l.new(warp.outputs[0],z.inputs[2])
    frac=n.new('ShaderNodeMath');frac.operation='FRACT';l.new(z.outputs[0],frac.inputs[0])
    glue=n.new('ShaderNodeValToRGB');glue.color_ramp.elements[0].position=.025;glue.color_ramp.elements[0].color=(.32,.22,.12,1)
    glue.color_ramp.elements[1].position=.11;glue.color_ramp.elements[1].color=(.59,.43,.26,1)
    l.new(frac.outputs[0],glue.inputs[0])
    # Veneer fibres retain subtle, non-repeating variation along the sawn edge.
    mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=.17
    l.new(glue.outputs['Color'],mix.inputs[1]);l.new(noise.outputs['Color'],mix.inputs[2]);l.new(mix.outputs[0],bs.inputs['Base Color'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.15;bump.inputs['Distance'].default_value=.000035
    l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal'])
    return mat


def add_wear_marks(cfg):
    # Thin, softly colored handling strokes outside the central 10 cm ball lane.
    rng=random.Random(409032);mat=material('Faint handling abrasion on satin wood',(.57,.47,.32),.69)
    for side in [-1,1]:
        for i in range(15):
            x=rng.uniform(-.56,.56);y=side*rng.uniform(.082,.116);length=rng.uniform(.005,.023)
            curve=bpy.data.curves.new('Short hairline handling scuff','CURVE');curve.dimensions='3D';curve.bevel_depth=rng.uniform(.000012,.000030);curve.bevel_resolution=1
            sp=curve.splines.new('POLY');sp.points.add(4)
            for j,p in enumerate(sp.points):
                xx=x+(j/4-.5)*length;z=surface(cfg,xx)[0]+.000010
                p.co=(xx,y+.0003*math.sin(j+i),z,1)
            o=bpy.data.objects.new('Subtle board handling mark outside rolling lane',curve);bpy.context.collection.objects.link(o);o.data.materials.append(mat)


def plywood_uv(obj,seed):
    """This photographed plywood grain runs along image U."""
    uv_metric(obj,seed,.5)
    for loop in obj.data.uv_layers.active.data:
        u,v=loop.uv;loop.uv=(v,u)


def joinery(cfg):
    metal=material('Dull recessed zinc assembly screws',(.52,.51,.47),.42)
    metal.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value=.8
    recess=material('Narrow recessed screwdriver slot',(.18,.17,.14),.79)
    for side in [-1,1]:
        for y in [-.101,.101]:
            x=side*.575;z,slope=surface(cfg,x);normal=Vector((-slope,0,1)).normalized()
            bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=.0028,depth=.00012,location=Vector((x,y,z))+normal*.000065)
            head=bpy.context.object;head.name='Flush assembly fastener outside rolling lane';head.rotation_euler=normal.to_track_quat('Z','Y').to_euler();head.data.materials.append(metal)
            # Same solver surface remains continuous under the 10 cm wide clear lane.
            slot=box('Recessed cross slot in assembly screw',Vector((x,y,z))+normal*.000132,(.0038,.00052,.000025),recess)
            slot.rotation_euler=head.rotation_euler
            slot=box('Recessed cross slot in assembly screw',Vector((x,y,z))+normal*.000133,(.00052,.0038,.000025),recess)
            slot.rotation_euler=head.rotation_euler
    # Hairline color-only butt joints: 0.12 mm, exactly flush, no colliding geometry.
    glue=material('Flush board joint, fine closed glue line',(.42,.35,.25),.54)
    for x in [-.135,.135]:
        verts=[]
        for xx in [x-.00006,x+.00006]:
            z=surface(cfg,xx)[0]+.000002
            verts.extend([(xx,-.125,z),(xx,.125,z)])
        mesh_object('Flush closed board joint, visual only',verts,[(0,2,3,1)],glue)


def pencil(name,center,yaw,color):
    """Actual 7 mm x 165 mm pencil, resting flat outside the moving envelope."""
    wood=material(name+' exposed cedar',(.68,.48,.27),.7);paint=material(name+' worn paint',color,.51);graphite=material('Graphite pencil lead',(.13,.13,.12),.51)
    parent=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(parent)
    for title,depth,r1,r2,z,mat in [('Hexagonal lacquered pencil body',.145,.0035,.0035,0,paint),('Sharpened wooden pencil tip',.017,.0035,.00045,-.081,wood),('Graphite tip',.003,.00045,0,-.091,graphite)]:
        bpy.ops.mesh.primitive_cone_add(vertices=6 if r1>.001 else 12,radius1=r2,radius2=r1,depth=depth)
        o=bpy.context.object;o.name=title;o.data.materials.append(mat);o.location.z=z;o.rotation_euler.z=math.pi/6;o.parent=parent
    parent.rotation_euler=(0,math.pi/2,yaw);parent.location=center


def architecture_worn_table(cfg,assets):
    ledger=architecture_photographic(cfg,assets)
    ledger['table_asset']=None  # filled by architecture_resin_balls(); set here to keep the ledger key order
    # Plywood photographic maps at their measured 0.50 m repeat.
    ply,files=pbr_wood(assets,'plywood',.50,'Photographic birch plywood, handled satin finish',1.02,.80,(.32,.48),.075)
    handling_wood(ply,409032)
    for obj in bpy.context.scene.objects:
        if obj.type=='MESH' and (obj.name.startswith('Continuous 14 mm') or obj.name.startswith('Apparatus birch') or obj.name.startswith('Solid transverse')):
            obj.data.materials.clear();obj.data.materials.append(ply);plywood_uv(obj,943 if obj.name.startswith('Continuous') else sum(map(ord,obj.name)))
    edge=real_ply_edge()
    for obj in bpy.context.scene.objects:
        if obj.name.startswith('Exposed plywood edge'):obj.data.materials.clear();obj.data.materials.append(edge)
    add_wear_marks(cfg)
    joinery(cfg)
    # Plant stands on the actual window ledge.
    plant=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.name.startswith('potted_plant_02')]
    place_group(plant,(-.67,1.30),.845,math.radians(-4),height=.29)
    pencil('Ochre drawing pencil',(-.35,.325,.763031),math.radians(17),(.64,.36,.10))
    pencil('Muted green drawing pencil',(-.33,.353,.763031),math.radians(-9),(.26,.36,.24))
    # A closed room makes the directions and strength of indirect light meaningful.
    paint=material('Off-white matte interior paint',(.83,.815,.77),.88)
    for name in ['Left wall','Right wall','Wall below window','Wall above window']:
        obj=bpy.data.objects.get(name)
        if obj:obj.data.materials.clear();obj.data.materials.append(paint)
    for name,loc,dims in [('Room left return wall',(-2.35,-.8,1.4),(.18,4.7,2.8)),('Room right return wall',(2.35,-.8,1.4),(.18,4.7,2.8)),
                          ('Room ceiling',(0,-.8,2.80),(4.9,4.7,.12)),('Room wall behind observer',(0,-3.12,1.4),(4.9,.18,2.8))]:
        box(name,loc,dims,paint)
    # Clear ordinary glazing; the nearest scene is always three-dimensional.
    glass=material('Ordinary window glass, 2 mm',(.98,.99,1),.025);bs=glass.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Transmission Weight'].default_value=1.;bs.inputs['IOR'].default_value=1.46
    for x in [-1.285,-.655]:box('Clear window pane',(x,1.433,1.55),(.575,.002,1.39),glass)
    ledger['wood_repeat_m']={'ramp':.50,'table':'Original furniture UV atlas'};ledger['pbr_files']['ramp']=files
    ledger['background']='Finite 3D room, real glazed opening, curtains, pencils and plant on sill'
    ledger['running_surface']='Frozen solver-exact top mesh, no displacement; appearance-only pores, finish variation and off-lane hairline wear'
    clear_unused();return ledger


def textile(assets,name,linen_rgb):
    mat=material(name,linen_rgb,.84);n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get('Principled BSDF')
    tc=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeVectorMath');mapping.operation='SCALE';mapping.inputs[3].default_value=5.
    l.new(tc.outputs['UV'],mapping.inputs[0])
    color=n.new('ShaderNodeTexImage');color.image=bpy.data.images.load(str(assets/'ambientcg/Fabric034/Fabric034_SQ_Color.jpg'),check_existing=True)
    l.new(mapping.outputs[0],color.inputs['Vector'])
    mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=.48
    mix.inputs[2].default_value=(*linen_rgb,1.);l.new(color.outputs[0],mix.inputs[1]);l.new(mix.outputs[0],bs.inputs['Base Color'])
    # Texture normal is DirectX: explicitly invert green before the GL normal node.
    tex=n.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(assets/'ambientcg/Fabric034/Fabric034_SQ_NormalDX.jpg'),check_existing=True)
    tex.image.colorspace_settings.name='Non-Color';l.new(mapping.outputs[0],tex.inputs['Vector'])
    split=n.new('ShaderNodeSeparateColor');join=n.new('ShaderNodeCombineColor');l.new(tex.outputs[0],split.inputs[0])
    inv=n.new('ShaderNodeMath');inv.operation='SUBTRACT';inv.inputs[0].default_value=1.;l.new(split.outputs[1],inv.inputs[1])
    l.new(split.outputs[0],join.inputs[0]);l.new(inv.outputs[0],join.inputs[1]);l.new(split.outputs[2],join.inputs[2])
    normal=n.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.24;l.new(join.outputs[0],normal.inputs[1]);l.new(normal.outputs[0],bs.inputs['Normal'])
    bs.inputs['Sheen Weight'].default_value=.32;bs.inputs['Sheen Roughness'].default_value=.75
    return mat


def cloth_mesh(name,verts,faces,uvs,mat,thickness):
    o=mesh_object(name,verts,faces,mat);uv=o.data.uv_layers.new(name='Physical metre fabric coordinates')
    for p in o.data.polygons:
        p.use_smooth=True
        for idx in p.loop_indices:uv.data[idx].uv=uvs[o.data.loops[idx].vertex_index]
    sol=o.modifiers.new('Real fabric thickness','SOLIDIFY');sol.thickness=thickness;sol.offset=0.
    return o


def curtain_domestic(assets,name,x0,x1,seed):
    rng=random.Random(seed);mat=textile(assets,name+' oatmeal woven linen',(.80,.78,.71));nx,nz=100,100
    phases=[rng.uniform(-math.pi,math.pi) for _ in range(5)];verts=[];uv=[]
    width=x1-x0
    for j in range(nz+1):
        v=j/nz;z=.085+v*2.38
        for i in range(nx+1):
            u=i/nx
            # Unequal gather spacing, broad gravity folds, fine cloth wrinkles and a weighted hem.
            phase=2*math.pi*(4.1*u+.065*math.sin(7*u+phases[0]))
            x=x0+width*(.10*(1-v)+u*(.90+.10*v))+.009*math.sin(5*v+phases[1])*math.sin(math.pi*u)
            y=1.235+.043*math.sin(phase+.11*math.sin(v*3+phases[2]))
            y+=.011*math.sin(phase*1.9+phases[3])*(.4+.6*(1-v))+.004*math.sin(43*u+8*v)*(1-v)
            zz=z+.006*math.sin(13*u+phases[4])*(1-v)**3
            verts.append((x,y,zz));uv.append((u*width,v*2.38))
    faces=[(j*(nx+1)+i,j*(nx+1)+i+1,(j+1)*(nx+1)+i+1,(j+1)*(nx+1)+i) for j in range(nz) for i in range(nx)]
    return cloth_mesh(name,verts,faces,uv,mat,.00065)


def window(assets):
    paint=paint_material('Satin off-white painted timber window profiles',(.86,.855,.81))
    paint.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.43
    seal=material('Recessed charcoal EPDM glazing gasket',(.13,.14,.135),.86)
    glass=material('Clear 4 mm window glass',(.99,.995,1),.012);bs=glass.node_tree.nodes.get('Principled BSDF');bs.inputs['Transmission Weight'].default_value=1.;bs.inputs['IOR'].default_value=1.50
    # Shadow-ray transmission avoids the opaque-glass shadow approximation when
    # refractive caustics are disabled; camera/glossy rays retain real glazing.
    n,l=glass.node_tree.nodes,glass.node_tree.links
    path=n.new('ShaderNodeLightPath');transparent=n.new('ShaderNodeBsdfTransparent');transparent.inputs[0].default_value=(.96,.96,.96,1)
    mix=n.new('ShaderNodeMixShader');l.new(path.outputs['Is Shadow Ray'],mix.inputs[0]);l.new(bs.outputs[0],mix.inputs[1]);l.new(transparent.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],n.get('Material Output').inputs[0])
    # Outer frame is recessed into the actual masonry opening, with overlapping inner sash.
    for x in [-1.573,-.367]:box('Window outer rebated jamb',(x,1.445,1.555),(.054,.125,1.43),paint,.002)
    for z in [.870,2.252]:box('Window outer rebated rail',(-.97,1.445,z),(1.26,.125,.054),paint,.002)
    box('Window weathered projecting sill',(-.97,1.325,.831),(1.39,.335,.028),paint,.003)
    box('Window sill apron',(-.97,1.314,.797),(1.285,.031,.035),paint,.0015)
    for x0,x1 in [(-1.547,-.972),(-.968,-.393)]:
        center=(x0+x1)/2
        for x in [x0+.017,x1-.017]:box('Window sash vertical profile',(x,1.407,1.563),(.034,.065,1.326),paint,.0014)
        for z in [.917,2.209]:box('Window sash horizontal profile',(center,1.407,z),(x1-x0,.065,.034),paint,.0014)
        a,b=x0+.034,x1-.034;low,high=.934,2.192
        for x in [a+.0015,b-.0015]:box('Window glazing seal vertical',(x,1.430,1.563),(.003,.006,high-low),seal,.0006)
        for z in [low+.0015,high-.0015]:box('Window glazing seal horizontal',(center,1.430,z),(b-a,.006,.003),seal,.0006)
        for y in [1.442,1.462]:box('Window double glazing 4 mm pane',(center,y,1.563),(b-a-.003,.004,high-low-.003),glass,.0003)
        # Fine painted bead sits over the gasket; no large black outlines.
        for x in [a-.005,b+.005]:box('Window inner glazing bead',(x,1.398,1.563),(.010,.012,high-low),paint,.0008)
    nickel=material('Brushed nickel window latch',(.52,.53,.51),.28);nickel.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value=.87
    box('Window handle escutcheon',(-.995,1.366,1.39),(.023,.007,.067),nickel,.005)
    box('Window handle short spindle',(-.995,1.351,1.39),(.012,.024,.013),nickel,.004)
    box('Window latch lever',(-.995,1.336,1.358),(.014,.014,.074),nickel,.005)
    curtain_domestic(assets,'Uneven gathered linen left',-1.87,-1.49,180)
    curtain_domestic(assets,'Uneven gathered linen right',-.46,-.16,193)


def props(assets):
    names=['alarm_clock_01', 'alarm_clock_01_glass', 'alarm_clock_01_hour_hand',
           'alarm_clock_01_minute_hand', 'alarm_clock_01_second_hand', 'rig_alarm_clock_01']
    imported=append_meshes(assets/'polyhaven/alarm_clock_01/alarm_clock_01_2k.blend',names,assets)
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()
    deps=bpy.context.evaluated_depsgraph_get()
    clock=[o for o in imported if o.type=='MESH']
    # Freeze the decorative asset's original rest pose, including its hand rig.
    # Only the solved balls receive motion; no decorative rig enters that cache.
    evaluated=[(o,o.matrix_world.copy(),bpy.data.meshes.new_from_object(o.evaluated_get(deps),depsgraph=deps)) for o in clock]
    for o,world,mesh in evaluated:
        o.parent=None;o.constraints.clear();o.animation_data_clear();o.modifiers.clear()
        o.data=mesh;o.matrix_world=world
    remove(o for o in imported if o.type!='MESH')
    place_group(clock,(.30,.345),.7600,math.radians(-10))
    tape=append_meshes(assets/'polyhaven/measuring_tape_01/measuring_tape_01_2k.blend',['measuring_tape_01'],assets)
    place_group(tape,(-.255,.335),.7600,math.radians(-65))
    ledger={}
    for name,objects in [('alarm_clock_01',clock),('measuring_tape_01',tape)]:
        lo,hi=bounds(objects)
        ledger[name]={'world_bounds_m':[list(lo),list(hi)],'dimensions_m':list(hi-lo),
            'scale_policy':'Original metre-scale asset, no visual resizing',
            'original_uv_and_pbr':True,'table_contact_z_m':lo.z}
    return ledger


def architecture_activity_table(cfg,assets):
    ledger=architecture_worn_table(cfg,assets)
    prefixes=('Ochre drawing pencil','Muted green drawing pencil','Hexagonal lacquered pencil','Sharpened wooden pencil','Graphite tip',
              'Window painted timber jamb','Window sill or header','Window central mullion',
              'Clear window pane','Natural linen drawn')
    remove(o for o in bpy.context.scene.objects if o.name.startswith(prefixes))
    window(assets)
    ledger['domestic_props']=props(assets)
    ledger['chair_count']=0
    ledger['window_construction']={'opening_m':[1.26,1.46],'wall_depth_m':.18,
        'frame_depth_m':.125,'sash_depth_m':.065,'double_glazing_panes_m':[.004,.004],
        'glass_centers_y_m':[1.442,1.462],'sill_top_m':.845,
        'profiles':'Rebated frame, sash, fine beads, recessed gasket, satin nickel latch'}
    ledger['background']='Chair-free finite home room; worn metal alarm clock and used tape measure on the rear of the activity table; window, curtain, sill plant and daylight retained'
    clear_unused()
    assert not any('chair' in o.name.lower() for o in bpy.context.scene.objects)
    return ledger


def finish(name, rgb, roughness, fine_scale, bump_distance):
    mat=material(name,rgb,roughness);n,l=mat.node_tree.nodes,mat.node_tree.links
    bs=n.get('Principled BSDF');tc=n.new('ShaderNodeTexCoord')
    coarse=n.new('ShaderNodeTexNoise');coarse.inputs['Scale'].default_value=8.;coarse.inputs['Detail'].default_value=2.
    l.new(tc.outputs['Object'],coarse.inputs[0])
    rough=n.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=roughness-.035;rough.inputs['To Max'].default_value=roughness+.035
    l.new(coarse.outputs['Fac'],rough.inputs[0]);l.new(rough.outputs[0],bs.inputs['Roughness'])
    grain=n.new('ShaderNodeTexNoise');grain.inputs['Scale'].default_value=fine_scale;grain.inputs['Detail'].default_value=2.
    l.new(tc.outputs['Object'],grain.inputs[0]);bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.16;bump.inputs['Distance'].default_value=bump_distance
    l.new(grain.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal'])
    bs.inputs['IOR'].default_value=1.48
    return mat


def rounded_top(cfg,mat):
    c=cfg['appearance']['table'];width,depth=c['dimensions_m'][:2];z=cfg['physics']['ramp']['table_top_z_m'];t=c['top_thickness_m'];r=c['corner_radius_m']
    outline=[]
    for cx,cy,start in [(width/2-r,depth/2-r,0),(-width/2+r,depth/2-r,90),(-width/2+r,-depth/2+r,180),(width/2-r,-depth/2+r,270)]:
        for j in range(17):
            a=math.radians(start+j*90/16);outline.append((cx+r*math.cos(a),cy+r*math.sin(a)+.04))
    n=len(outline);verts=[(x,y,h) for h in [z-t,z] for x,y in outline]
    faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    obj=mesh_object('Warm grey laminate activity tabletop',verts,faces,mat)
    bevel=obj.modifiers.new('Subtle 1.2 mm sealed laminate edge radius','BEVEL');bevel.width=.0012;bevel.segments=3
    obj.modifiers.new('Flat top and softly rounded perimeter normals','WEIGHTED_NORMAL')
    return obj


def tube(name,xy,z0,z1,r,mat):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=r,depth=z1-z0,location=(xy[0],xy[1],(z0+z1)/2))
    obj=bpy.context.object;obj.name=name;obj.data.materials.append(mat)
    for p in obj.data.polygons:p.use_smooth=len(p.vertices)==4
    bevel=obj.modifiers.new('Coated tube edge radius','BEVEL');bevel.width=.0006;bevel.segments=2
    obj.modifiers.new('Tube end face normals','WEIGHTED_NORMAL');return obj


def table(cfg):
    c=cfg['appearance']['table'];z=cfg['physics']['ramp']['table_top_z_m'];bottom=z-c['top_thickness_m']
    topmat=finish('Warm greige matte laminate, fine sealed surface',c['top_srgb'],c['roughness'],3200.,.000008)
    paint=finish('Warm grey powder-coated steel frame',c['frame_srgb'],.49,1800.,.000012)
    rubber=material('Small charcoal anti-slip foot plugs',(.14,.15,.145),.84)
    objects=[rounded_top(cfg,topmat)]
    for x in [-.745,.745]:
        for y in [-.25,.33]:
            objects.append(tube('Slim powder-coated steel table leg',(x,y),.007,bottom-.002,.018,paint))
            objects.append(tube('Table leg soft floor plug',(x,y),0.,.007,.0188,rubber))
            objects.append(box('Tabletop steel fixing plate',(x,y,bottom-.001),(.060,.060,.002),paint,.001))
    for y in [-.25,.33]:objects.append(box('Long underside tubular steel frame',(0,y,bottom-.0175),(1.49,.022,.035),paint,.002))
    for x in [-.745,.745]:objects.append(box('Short underside tubular steel frame',(x,.04,bottom-.0175),(.022,.58,.035),paint,.002))
    bpy.context.view_layer.update();lo,hi=bounds(objects)
    return {'asset':'authored_laminate_steel_activity_table','placed_world_bounds_m':[list(lo),list(hi)],'placed_dimensions_m':list(hi-lo),
        'tabletop_top_z_m':z,'tabletop_thickness_m':c['top_thickness_m'],'corner_radius_m':c['corner_radius_m'],
        'leg_outer_diameter_m':.036,'floor_z_m':0.,'surface':'Solid matte warm-grey laminate, no timber texture; sealed rounded perimeter',
        'support':'Four 36 mm steel tubes, continuous underside frame, fixing plates and 7 mm foot plugs'}


def architecture_resin_balls(cfg,assets):
    ledger=architecture_activity_table(cfg,assets)
    ledger['table_asset']=table(cfg)
    ledger['pbr_files']['table']={'type':'Authored metre-scale laminate and powder-coat shaders; no photographic wood image'}
    ledger['wood_repeat_m']['table']=None
    ledger['background']='Chair-free home activity table, matte warm-grey laminate and slender coated steel legs; clock, tape measure, room and window retained'
    clear_unused();return ledger


def resin_material(cfg,name):
    c=cfg['appearance']['ball'];rgb=c['red_srgb' if name=='B_left' else 'blue_srgb']
    mat=material(name+' lightly handled cast resin with two ivory number medallions',rgb,c['roughness'])
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get('Principled BSDF');tc=n.new('ShaderNodeTexCoord')
    center=n.new('ShaderNodeVectorMath');center.operation='SUBTRACT';center.inputs[1].default_value=(.5,.5,.5);l.new(tc.outputs['Generated'],center.inputs[0])
    norm=n.new('ShaderNodeVectorMath');norm.operation='NORMALIZE';l.new(center.outputs[0],norm.inputs[0])
    dot=n.new('ShaderNodeVectorMath');dot.operation='DOT_PRODUCT';dot.inputs[1].default_value=Vector(c['medallion_axis']).normalized();l.new(norm.outputs[0],dot.inputs[0])
    absolute=n.new('ShaderNodeMath');absolute.operation='ABSOLUTE';l.new(dot.outputs['Value'],absolute.inputs[0])
    edge=n.new('ShaderNodeMapRange');edge.clamp=True;edge.inputs['From Min'].default_value=math.cos(c['medallion_angle_rad']+.002);edge.inputs['From Max'].default_value=math.cos(c['medallion_angle_rad']-.002)
    l.new(absolute.outputs[0],edge.inputs[0])
    color=n.new('ShaderNodeMixRGB');color.inputs[1].default_value=tuple(linear(v) for v in rgb)+(1.,);color.inputs[2].default_value=tuple(linear(v) for v in c['ivory_srgb'])+(1.,)
    l.new(edge.outputs[0],color.inputs[0]);l.new(color.outputs[0],bs.inputs['Base Color'])
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=27.;noise.inputs['Detail'].default_value=2.;l.new(tc.outputs['Generated'],noise.inputs[0])
    rough=n.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=c['roughness_range'][0];rough.inputs['To Max'].default_value=c['roughness_range'][1]
    l.new(noise.outputs['Fac'],rough.inputs[0]);l.new(rough.outputs[0],bs.inputs['Roughness'])
    fine=n.new('ShaderNodeTexNoise');fine.inputs['Scale'].default_value=240.;fine.inputs['Detail'].default_value=2.;l.new(tc.outputs['Generated'],fine.inputs[0])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.15;bump.inputs['Distance'].default_value=.0000015
    l.new(fine.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal'])
    bs.inputs['IOR'].default_value=1.49;bs.inputs['Coat Weight'].default_value=c['coat_weight'];bs.inputs['Coat Roughness'].default_value=.25
    return mat


def cylinder_between(name,a,b,r,mat):
    a,b=Vector(a),Vector(b)
    bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=r,depth=(b-a).length,location=(a+b)/2)
    obj=bpy.context.object;obj.name=name;obj.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler()
    obj.data.materials.append(mat)
    for p in obj.data.polygons:p.use_smooth=len(p.vertices)==4
    return obj


def clear_curtains(cfg):
    c=cfg['appearance']['room_detail'];shift=c['curtain_forward_offset_m']
    curtains=[o for o in bpy.context.scene.objects if o.name.startswith('Uneven gathered linen')]
    for obj in curtains:
        obj.location.y-=shift
        # The very top is gathered onto rings along a straight rod; folds open
        # below it rather than displacing the supports through the masonry.
        for v in obj.data.vertices:
            weight=max(0.,min(1.,(v.co.z-2.405)/.060))
            v.co.y=(1-weight)*v.co.y+weight*1.235
        obj.data.update()
    paint=material('Warm pewter curtain hardware',(.34,.35,.335),.48)
    paint.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value=.65
    rod_y=1.235-shift
    cylinder_between('Linen curtain continuous supported rod',(-1.97,rod_y,2.484),(-.06,rod_y,2.484),.008,paint)
    for x in [-1.90,-.12]:
        cylinder_between('Curtain rod wall standoff',(x,1.331,2.484),(x,rod_y,2.484),.0045,paint)
        box('Curtain rod wall mounting plate',(x,1.328,2.484),(.035,.004,.045),paint,.002)
    for obj in curtains:
        top=sorted((v.co.x for v in obj.data.vertices if v.co.z>2.4649))
        for j in range(7):
            x=top[round((j+.5)/7*(len(top)-1))]
            bpy.ops.mesh.primitive_torus_add(major_segments=32,minor_segments=8,location=(x,rod_y,2.480),
                rotation=(0,math.pi/2,0),major_radius=.014,minor_radius=.0012)
            ring=bpy.context.object;ring.name='Linen curtain hanging ring';ring.data.materials.append(paint)
            for p in ring.data.polygons:p.use_smooth=True
    bpy.context.view_layer.update()
    deps=bpy.context.evaluated_depsgraph_get();ledger=[]
    for obj in curtains:
        evaluated=obj.evaluated_get(deps);mesh=evaluated.to_mesh()
        vertices=[obj.matrix_world@v.co for v in mesh.vertices]
        lo=[min(v[i] for v in vertices) for i in range(3)];hi=[max(v[i] for v in vertices) for i in range(3)]
        ledger.append({'object':obj.name,'evaluated_bounds_m':[lo,hi],'minimum_y_separation_from_sill_front_m':1.1575-hi[1]})
        evaluated.to_mesh_clear()
    return {'forward_offset_m':shift,'rod_y_m':rod_y,'rod_z_m':2.484,'cloth_thickness_m':.00065,
        'sill_front_y_m':1.1575,'panels':ledger,'support':'Continuous 16 mm rod, two wall brackets and fourteen hanging rings'}


def porcelain(cfg):
    c=cfg['appearance']['room_detail'];mat=material('Warm light-grey matte porcelain floor',c['floor_srgb'],.66)
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get('Principled BSDF');tc=n.new('ShaderNodeTexCoord')
    # The cube dimensions are applied: Object coordinates are physical metres.
    coarse=n.new('ShaderNodeTexNoise');coarse.inputs['Scale'].default_value=11.;coarse.inputs['Detail'].default_value=3.
    l.new(tc.outputs['Object'],coarse.inputs[0]);object_info=n.new('ShaderNodeObjectInfo')
    tone=n.new('ShaderNodeMath');tone.operation='MULTIPLY_ADD';tone.inputs[1].default_value=.035;tone.inputs[2].default_value=.9825;l.new(object_info.outputs['Random'],tone.inputs[0])
    mottling=n.new('ShaderNodeMath');mottling.operation='MULTIPLY_ADD';mottling.inputs[1].default_value=.025;mottling.inputs[2].default_value=.9875;l.new(coarse.outputs['Fac'],mottling.inputs[0])
    amount=n.new('ShaderNodeMath');amount.operation='MULTIPLY';l.new(tone.outputs[0],amount.inputs[0]);l.new(mottling.outputs[0],amount.inputs[1])
    color=n.new('ShaderNodeMixRGB');color.blend_type='MULTIPLY';color.inputs[0].default_value=1.;color.inputs[1].default_value=tuple(linear(v) for v in c['floor_srgb'])+(1.,)
    l.new(amount.outputs[0],color.inputs[2]);l.new(color.outputs[0],bs.inputs['Base Color'])
    rough=n.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.61;rough.inputs['To Max'].default_value=.71
    l.new(coarse.outputs['Fac'],rough.inputs[0]);l.new(rough.outputs[0],bs.inputs['Roughness'])
    grain=n.new('ShaderNodeTexNoise');grain.inputs['Scale'].default_value=1400.;grain.inputs['Detail'].default_value=2.
    l.new(tc.outputs['Object'],grain.inputs[0]);bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.18;bump.inputs['Distance'].default_value=.000018
    l.new(grain.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal'])
    return mat


def room_floor(cfg):
    c=cfg['appearance']['room_detail'];tile=porcelain(cfg)
    grout=material('Narrow warm-grey porcelain grout',(.40,.405,.38),.89)
    remove(o for o in bpy.context.scene.objects if o.name in ['Continuous room floor','Rear skirting'])
    # Continuous real substrate closes the floor even through every recessed joint.
    box('Continuous solid room floor substrate',(0,-.85,-.0357),(4.70,4.94,.07),grout)
    pitch=c['tile_pitch_m'];gap=c['tile_joint_m'];origin=c['tile_grid_origin_m'];count=0
    for ix in range(-5,6):
        for iy in range(-7,4):
            x0=origin[0]+ix*pitch;x1=x0+pitch;y0=origin[1]+iy*pitch;y1=y0+pitch
            x0,x1=max(x0,-2.35),min(x1,2.35);y0,y1=max(y0,-3.20),min(y1,1.42)
            if x1-x0<.02 or y1-y0<.02:continue
            box('Metric matte porcelain floor tile',((x0+x1)/2,(y0+y1)/2,-.006),
                (x1-x0-gap,y1-y0-gap,.012),tile,.00035);count+=1
    trim=material('Warm off-white satin room skirting',(.77,.775,.73),.57)
    for name,loc,dims in [
        ('Continuous rear wall skirting',(0,1.322,.048),(4.52,.016,.096)),
        ('Left return wall skirting',(-2.252,-.89,.048),(.016,4.42,.096)),
        ('Right return wall skirting',(2.252,-.89,.048),(.016,4.42,.096)),
        ('Observer wall skirting',(0,-3.022,.048),(4.52,.016,.096))]:box(name,loc,dims,trim,.0015)
    return {'style':'Matte warm-grey porcelain, metric geometry and fine surface pores','tile_pitch_m':pitch,'tile_joint_m':gap,
        'tile_depth_m':.012,'tile_top_z_m':0.,'grout_top_z_m':-.0007,'tile_count':count,
        'tile_grid_origin_m':origin,'solid_substrate':True,'skirting_height_m':.096,
        'floor_extents_m':[[-2.35,-3.20],[2.35,1.42]],'existing_table_leg_ground_z_m':0.}


def architecture_clear_sill(cfg,assets):
    ledger=architecture_resin_balls(cfg,assets)
    ledger['curtain_clearance']=clear_curtains(cfg)
    ledger['room_floor']=room_floor(cfg)
    ledger['background']='Resin balls and laminate table retained; linen hangs in front of the projecting sill; metric porcelain floor and connected skirting establish room depth beneath the table'
    clear_unused();return ledger


WALLS=['Left wall','Right wall','Wall below window','Wall above window','Room left return wall',
       'Room right return wall','Room ceiling','Room wall behind observer']


def image(path,data=False):
    img=bpy.data.images.load(str(path),check_existing=True)
    if data:img.colorspace_settings.name='Non-Color'
    return img


def wall_paint(cfg,assets):
    """Photographed matte emulsion paint (diffuse, roughness, normal) at its measured repeat."""
    # Scene-local 2K copy (assets.json: scenes/twin_ramp_collision/wall_textures/beige_wall_001);
    # polyhaven/beige_wall_001 holds the 4K maps used by another scene.
    c=cfg['appearance']['wall_paint'];root=assets/'scenes/twin_ramp_collision/wall_textures'/c['asset']
    mat=bpy.data.materials.new('Scanned matte emulsion wall paint');mat.use_nodes=True
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get('Principled BSDF');tc=n.new('ShaderNodeTexCoord')
    files={role:root/f"{c['asset']}_{key}_2k.jpg" for role,key in [('color','diff'),('roughness','rough'),('normal','nor_gl')]}
    color=n.new('ShaderNodeTexImage');color.image=image(files['color']);l.new(tc.outputs['UV'],color.inputs['Vector'])
    hs=n.new('ShaderNodeHueSaturation');hs.inputs['Saturation'].default_value=c['saturation'];hs.inputs['Value'].default_value=c['value']
    l.new(color.outputs['Color'],hs.inputs['Color']);l.new(hs.outputs['Color'],bs.inputs['Base Color'])
    rough=n.new('ShaderNodeTexImage');rough.image=image(files['roughness'],True);l.new(tc.outputs['UV'],rough.inputs['Vector'])
    mr=n.new('ShaderNodeMapRange');mr.inputs['To Min'].default_value=c['roughness_range'][0];mr.inputs['To Max'].default_value=c['roughness_range'][1]
    l.new(rough.outputs['Color'],mr.inputs['Value']);l.new(mr.outputs['Result'],bs.inputs['Roughness'])
    nor=n.new('ShaderNodeTexImage');nor.image=image(files['normal'],True);l.new(tc.outputs['UV'],nor.inputs['Vector'])
    nm=n.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=c['normal_strength']
    l.new(nor.outputs['Color'],nm.inputs['Color']);l.new(nm.outputs['Normal'],bs.inputs['Normal'])
    bs.inputs['IOR'].default_value=1.5
    count=0
    for obj in [o for o in bpy.context.scene.objects if o.type=='MESH' and o.name.startswith(tuple(WALLS))]:
        obj.data.materials.clear();obj.data.materials.append(mat)
        # One shared world-space offset keeps the paint continuous across wall pieces.
        uv_metric(obj,c['uv_seed'],c['repeat_m']);count+=1
    return {'asset':c['asset'],'repeat_m':c['repeat_m'],'objects':count,'files':{k:str(v) for k,v in files.items()},
        'mapping':'Planar world-metre UVs with one shared offset; continuous across all wall pieces'}


def handled_laminate(cfg,assets):
    """Photographed smudge/dust roughness on the satin laminate top; colour unchanged."""
    c=cfg['appearance']['table_wear'];obj=bpy.data.objects['Warm grey laminate activity tabletop'];mat=obj.data.materials[0]
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get('Principled BSDF')
    path=assets/'ambientcg'/c['asset']/f"{c['asset']}_SQ_Roughness.jpg"
    geo=n.new('ShaderNodeNewGeometry');mapping=n.new('ShaderNodeMapping')
    mapping.inputs['Location'].default_value=c['offset_m']+[0.];mapping.inputs['Rotation'].default_value[2]=c['rotation_rad']
    mapping.inputs['Scale'].default_value=(1/c['repeat_m'],1/c['repeat_m'],1.)
    l.new(geo.outputs['Position'],mapping.inputs['Vector'])
    tex=n.new('ShaderNodeTexImage');tex.image=image(path,True);tex.interpolation='Cubic';l.new(mapping.outputs['Vector'],tex.inputs['Vector'])
    mr=n.new('ShaderNodeMapRange');mr.clamp=True
    mr.inputs['From Min'].default_value=c['map_from'][0];mr.inputs['From Max'].default_value=c['map_from'][1]
    mr.inputs['To Min'].default_value=c['roughness_range'][0];mr.inputs['To Max'].default_value=c['roughness_range'][1]
    l.new(tex.outputs['Color'],mr.inputs['Value'])
    for link in list(bs.inputs['Roughness'].links):l.remove(link)
    l.new(mr.outputs['Result'],bs.inputs['Roughness'])
    bs.inputs['Specular IOR Level'].default_value=c['specular_ior_level']
    return {'asset':c['asset'],'repeat_m':c['repeat_m'],'roughness_range':c['roughness_range'],'file':str(path),
        'mapping':'World XY metres, flat projection on the horizontal top only'}


def glazing():
    glass=material('Clear 4 mm side window glass',(.99,.995,1),.012);bs=glass.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Transmission Weight'].default_value=1.;bs.inputs['IOR'].default_value=1.50
    # Same treatment as the rear window: shadow rays see thin clear glass instead of an opaque pane.
    n,l=glass.node_tree.nodes,glass.node_tree.links
    path=n.new('ShaderNodeLightPath');transparent=n.new('ShaderNodeBsdfTransparent');transparent.inputs[0].default_value=(.96,.96,.96,1)
    mix=n.new('ShaderNodeMixShader');l.new(path.outputs['Is Shadow Ray'],mix.inputs[0]);l.new(bs.outputs[0],mix.inputs[1]);l.new(transparent.outputs[0],mix.inputs[2])
    l.new(mix.outputs[0],n.get('Material Output').inputs[0])
    return glass


def side_window(cfg):
    """A second ordinary casement in the left return wall, outside the camera frustum."""
    c=cfg['appearance']['side_window'];(y0,y1),(z0,z1)=c['opening_y_m'],c['opening_z_m']
    wall=bpy.data.objects['Room left return wall'];paint=wall.data.materials[0]
    lo=[wall.matrix_world@v.co for v in wall.data.vertices];xmin=min(v.x for v in lo);xmax=max(v.x for v in lo)
    ymin=min(v.y for v in lo);ymax=max(v.y for v in lo);zmin=min(v.z for v in lo);zmax=max(v.z for v in lo)
    remove([wall]);x=(xmin+xmax)/2;t=xmax-xmin
    for name,(ya,yb,za,zb) in [('Room left return wall, observer side of side window',(ymin,y0,zmin,zmax)),
                               ('Room left return wall, rear side of side window',(y1,ymax,zmin,zmax)),
                               ('Room left return wall below side window',(y0,y1,zmin,z0)),
                               ('Room left return wall above side window',(y0,y1,z1,zmax))]:
        box(name,(x,(ya+yb)/2,(za+zb)/2),(t,yb-ya,zb-za),paint,.0008)
    frame=paint_material('Satin off-white painted timber side window',(.86,.855,.81))
    frame.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.43
    glass=glazing();fx=x+.005
    for y in [y0+.027,y1-.027]:box('Side window rebated jamb',(fx,y,(z0+z1)/2),(.125,.054,z1-z0),frame,.002)
    for z in [z0+.027,z1-.027]:box('Side window rebated rail',(fx,(y0+y1)/2,z),(.125,y1-y0,.054),frame,.002)
    box('Side window central mullion',(fx,(y0+y1)/2,(z0+z1)/2),(.125,.050,z1-z0),frame,.002)
    half=(y1-y0-.054*2-.050)/2
    for yc in [y0+.054+half/2,y1-.054-half/2]:
        for gx in [x-.010,x+.010]:box('Side window double glazing 4 mm pane',(gx,yc,(z0+z1)/2),(.004,half,z1-z0-.108),glass,.0003)
    box('Side window painted sill',(xmax+.02,(y0+y1)/2,z0-.014),(.05,y1-y0+.06,.028),frame,.002)
    return {'opening_y_m':[y0,y1],'opening_z_m':[z0,z1],'wall_x_m':[xmin,xmax],
        'visibility':'Outside the fixed camera frustum; contributes daylight and reflections only'}


def worn_floor(cfg,assets):
    """Photographed dust and scuff variation on the existing matte porcelain tiles."""
    c=cfg['appearance']['floor_wear'];mat=bpy.data.materials['Warm light-grey matte porcelain floor']
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get('Principled BSDF')
    path=assets/'ambientcg'/c['asset']/f"{c['asset']}_SQ_Roughness.jpg"
    geo=n.new('ShaderNodeNewGeometry');mapping=n.new('ShaderNodeMapping')
    mapping.inputs['Location'].default_value=c['offset_m']+[0.];mapping.inputs['Rotation'].default_value[2]=c['rotation_rad']
    mapping.inputs['Scale'].default_value=(1/c['repeat_m'],1/c['repeat_m'],1.)
    l.new(geo.outputs['Position'],mapping.inputs['Vector'])
    tex=n.new('ShaderNodeTexImage');tex.image=image(path,True);l.new(mapping.outputs['Vector'],tex.inputs['Vector'])
    rough=n.new('ShaderNodeMapRange');rough.clamp=True
    rough.inputs['From Min'].default_value=c['map_from'][0];rough.inputs['From Max'].default_value=c['map_from'][1]
    rough.inputs['To Min'].default_value=c['roughness_range'][0];rough.inputs['To Max'].default_value=c['roughness_range'][1]
    l.new(tex.outputs['Color'],rough.inputs['Value'])
    for link in list(bs.inputs['Roughness'].links):l.remove(link)
    l.new(rough.outputs['Result'],bs.inputs['Roughness'])
    # Dust lifts and scuffs lower the tile tone by a few percent around the existing per-tile colour.
    tone=n.new('ShaderNodeMapRange');tone.clamp=True
    tone.inputs['From Min'].default_value=c['map_from'][0];tone.inputs['From Max'].default_value=c['map_from'][1]
    tone.inputs['To Min'].default_value=c['albedo_scale'][0];tone.inputs['To Max'].default_value=c['albedo_scale'][1]
    l.new(tex.outputs['Color'],tone.inputs['Value'])
    previous=bs.inputs['Base Color'].links[0].from_socket
    mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1.
    l.new(previous,mix.inputs[1]);l.new(tone.outputs['Result'],mix.inputs[2]);l.new(mix.outputs[0],bs.inputs['Base Color'])
    return {'asset':c['asset'],'repeat_m':c['repeat_m'],'roughness_range':c['roughness_range'],'albedo_scale':c['albedo_scale'],'file':str(path)}


def architecture(cfg,assets):
    ledger=architecture_clear_sill(cfg,assets)
    if cfg['appearance'].get('side_window'):ledger['side_window']=side_window(cfg)
    ledger['wall_paint']=wall_paint(cfg,assets)
    ledger['table_wear']=handled_laminate(cfg,assets)
    if cfg['appearance'].get('floor_wear'):ledger['floor_wear']=worn_floor(cfg,assets)
    ledger['background']=('Room, table, ramp, props and rear window retained; second casement in the left return wall '
        'outside the frame; scanned matte wall paint, photographed handling marks on laminate and floor; daylight only')
    clear_unused();return ledger


def build_balls(cfg):
    """Cast-resin spheres with plain ivory spots; no printed numerals or other characters."""
    balls={}
    for name,c in cfg['physics']['balls'].items():
        if not c['present']:continue
        bpy.ops.mesh.primitive_uv_sphere_add(segments=96,ring_count=64,radius=c['radius_m'])
        obj=bpy.context.object;obj.name=name;obj.rotation_mode='QUATERNION'
        mat=resin_material(cfg,name);mat.name=name+' cast resin, two plain ivory spots'
        bs=mat.node_tree.nodes.get('Principled BSDF');bs.inputs['Coat Roughness'].default_value=cfg['appearance']['ball']['coat_roughness']
        obj.data.materials.append(mat)
        for p in obj.data.polygons:p.use_smooth=True
        balls[name]=obj
    return balls


def lighting(cfg,assets):
    """The overcast garden HDRI is the only light; it reaches the closed room only through the glazed opening."""
    ap=cfg['appearance'];world=bpy.data.worlds.new('Overcast garden sky outside the glazed opening');world.use_nodes=True;bpy.context.scene.world=world
    n,l=world.node_tree.nodes,world.node_tree.links;env=n.new('ShaderNodeTexEnvironment')
    env.image=bpy.data.images.load(str(assets/'polyhaven/residential_garden/residential_garden_4k.hdr'),check_existing=True)
    tc=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeMapping');mapping.inputs['Rotation'].default_value[2]=ap['environment_rotation_rad']
    l.new(tc.outputs['Generated'],mapping.inputs[0]);l.new(mapping.outputs[0],env.inputs[0]);l.new(env.outputs[0],n.get('Background').inputs['Color'])
    n.get('Background').inputs['Strength'].default_value=ap['environment_strength']
    # A portal emits nothing: it only tells Cycles where the sky enters the room.
    portals=[('Sky portal filling the rear glazed window opening (emits no light)',ap['window_portal'])]
    s=ap.get('side_window')
    if s:
        (y0,y1),(z0,z1)=s['opening_y_m'],s['opening_z_m']
        portals.append(('Sky portal filling the side glazed window opening (emits no light)',
            {'location':[s['portal_x_m'],(y0+y1)/2,(z0+z1)/2],'target':[0.,(y0+y1)/2,(z0+z1)/2],'size_m':[y1-y0,z1-z0]}))
    for name,c in portals:
        data=bpy.data.lights.new(name,'AREA')
        data.shape='RECTANGLE';data.size=c['size_m'][0];data.size_y=c['size_m'][1];data.cycles.is_portal=True
        o=bpy.data.objects.new(data.name,data);bpy.context.collection.objects.link(o);o.location=c['location'];look_at(o,c['target'])
    return {'sources':'residential_garden HDRI through the glazed openings only','portals':[c for _,c in portals],'hidden_lights':0}
