"""Furnished daylight room: lab-stand pendulums on a timber table, scanned floor and furniture, plain ABS balls.

architecture(), build_balls(), build_ropes() and lighting() build on the aluminium lab-stand tabletop
layer (helpers suffixed _lab_stand): steel table base with the photographed timber top, plywood base
board, slot-8 aluminium frame and brackets, suspension hardware, cords and knots, hourglass, notebook,
tape measure and the rear window. On top of it: the floor uses scanned Poly Haven planks, the left wall
has a second real window, scanned furniture stands against the rear wall, the only light is the sky seen
through the two window openings (portals only guide sampling and emit nothing; there are no hidden
lamps), and the balls are plain solid ABS without printed numbers.
"""
from __future__ import annotations

import math
import random
import sys as _scene_sys
from pathlib import Path as _ScenePath, Path

import bpy
from mathutils import Vector, Matrix
from scene_config import construction
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))


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


def wood_material(asset_root,cfg,asset="oak_veneer_01"):
    roots=[asset_root/"polyhaven"/asset,asset_root/asset]
    root=next((r for r in roots if r.is_dir()),None)
    if root is None:raise FileNotFoundError(f"The documented CC0 {asset} PBR maps are required.")
    files={k:next(iter(sorted(root.glob(f"*{suffix}*.jpg"))),None) for k,suffix in [("color","_diff_"),("roughness","_rough_"),("normal","_nor_gl_")]}
    if not all(files.values()):raise FileNotFoundError(files)
    is_table=asset=="wood_table_001"
    mat=material("Oiled dark hardwood activity tabletop" if is_table else "Warm satin oak frame, grain follows each member",(.58,.39,.23),.4)
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get("Principled BSDF")
    uv=n.new("ShaderNodeTexCoord")
    for role,path in files.items():
        tex=n.new("ShaderNodeTexImage");tex.name=role+" CC0 Poly Haven";tex.image=bpy.data.images.load(str(path),check_existing=True)
        l.new(uv.outputs["UV"],tex.inputs["Vector"])
        if role=="color":
            hue=n.new("ShaderNodeHueSaturation");hue.inputs["Saturation"].default_value=.78 if is_table else .90
            hue.inputs["Value"].default_value=.94 if is_table else .57;l.new(tex.outputs["Color"],hue.inputs["Color"])
            if is_table:l.new(hue.outputs["Color"],bs.inputs["Base Color"])
            else:
                tint=n.new("ShaderNodeMixRGB");tint.inputs[0].default_value=.16
                l.new(hue.outputs["Color"],tint.inputs[1]);tint.inputs[2].default_value=tuple(linear(c) for c in [.52,.40,.26])+(1,)
                l.new(tint.outputs[0],bs.inputs["Base Color"])
        elif role=="roughness":
            tex.image.colorspace_settings.name="Non-Color"
            remap=n.new("ShaderNodeMapRange");remap.inputs["From Min"].default_value=0;remap.inputs["From Max"].default_value=1
            remap.inputs["To Min"].default_value=.40 if is_table else .34;remap.inputs["To Max"].default_value=.56
            l.new(tex.outputs["Color"],remap.inputs["Value"]);l.new(remap.outputs["Result"],bs.inputs["Roughness"])
        else:
            tex.image.colorspace_settings.name="Non-Color"
            normal=n.new("ShaderNodeNormalMap");normal.inputs["Strength"].default_value=.24 if is_table else .16
            l.new(tex.outputs["Color"],normal.inputs["Color"]);l.new(normal.outputs["Normal"],bs.inputs["Normal"])
    bs.inputs["Coat Weight"].default_value=.10;bs.inputs["Coat Roughness"].default_value=.38
    return mat,files


def paint_material(name,rgb):
    mat=material(name,rgb,.78);n,l=mat.node_tree.nodes,mat.node_tree.links
    noise=n.new("ShaderNodeTexNoise");noise.inputs["Scale"].default_value=650;noise.inputs["Detail"].default_value=2
    tc=n.new("ShaderNodeTexCoord");l.new(tc.outputs["Object"],noise.inputs["Vector"])
    bump=n.new("ShaderNodeBump");bump.inputs["Strength"].default_value=.14;bump.inputs["Distance"].default_value=.00007
    l.new(noise.outputs["Fac"],bump.inputs["Height"]);l.new(bump.outputs["Normal"],n.get("Principled BSDF").inputs["Normal"])
    return mat


def append_asset_objects(path,prefix):
    with bpy.data.libraries.load(str(path),link=False) as (src,dst):dst.objects=list(src.objects)
    objects=[]
    for o in dst.objects:
        if o.type in {"MESH","CURVE","EMPTY"}:
            bpy.context.collection.objects.link(o);objects.append(o)
    bpy.context.view_layer.update()
    worlds={o:o.matrix_world.copy() for o in objects}
    original_names={o:o.name for o in objects}
    for o in objects:
        o.parent=None;o.matrix_world=worlds[o];o.name=prefix+original_names[o]
        if o.animation_data:o.animation_data_clear()
    return objects,original_names,worlds


def evaluated_bounds(objects):
    deps=bpy.context.evaluated_depsgraph_get();points=[]
    for o in objects:
        if o.type!="MESH":continue
        ev=o.evaluated_get(deps);points.extend(ev.matrix_world@Vector(c) for c in ev.bound_box)
    return [[min(p[i] for p in points) for i in range(3)],[max(p[i] for p in points) for i in range(3)]]


def asset_table(cfg,asset_root):
    path=asset_root/"blenderkit/pendulum_wood_metal_table/wood_metal_table.blend"
    objects,names,worlds=append_asset_objects(path,"Furniture_")
    before=evaluated_bounds(objects);f=cfg["physics"]["fixture"];dx,dy,dz=f["table_dimensions_m"];top=f["table_top_z_m"]
    scale_x=dx/(before[1][0]-before[0][0]);scale_y=dy/(before[1][1]-before[0][1])
    from mathutils import Matrix
    tabletop=next(o for o in objects if names[o]=="Cube")
    original_top=.75;original_top_bottom=.7100000381469727
    for o in objects:
        if o.type!="MESH":bpy.data.objects.remove(o,do_unlink=True);continue
        if o==tabletop:
            scale_z=dz/(original_top-original_top_bottom);shift=top-scale_z*original_top
        else:scale_z=(top-dz)/original_top_bottom;shift=0
        fit=Matrix.Diagonal((scale_x,scale_y,scale_z,1.))
        fit.translation=Vector((-(before[1][0]+before[0][0])/2*scale_x,.04-(before[1][1]+before[0][1])/2*scale_y,shift))
        o.matrix_world=fit@worlds[o]
        o["source_asset"]="bdff957c-a9e9-4827-b6c9-602b264a4fbf"
    # Retain the real steel base; replace the pale, uniformly glossy top with
    # a photographed solid-timber surface and actual shallow board joins.
    bpy.data.objects.remove(tabletop,do_unlink=True)
    tabletop,top_ledger=photographic_tabletop(cfg,asset_root)
    bpy.context.view_layer.update()
    meshes=[o for o in bpy.context.scene.objects if o==tabletop or o.name.startswith("Furniture_")]
    return {"source":"https://www.blenderkit.com/asset-gallery-detail/bdff957c-a9e9-4827-b6c9-602b264a4fbf/","author":"Nicușor Vatră","license":"CC0",
        "source_bounds_m":before,"fitted_bounds_m":evaluated_bounds(meshes),"tabletop_bounds_m":evaluated_bounds([tabletop]),
        "fitting":"Measured XY fit to unchanged collision boundary. Original steel support geometry retained; a 36 mm glued timber top has 1.5 mm edge radii, photographic PBR and correct longitudinal/end grain.",
        "tabletop_surface":top_ledger}


def end_grain_material():
    mat=material("Solid timber end grain, restrained growth rings",(.34,.22,.13),.57)
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get('Principled BSDF')
    tc=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY'
    mapping.inputs[1].default_value=(.12,1.,1.);l.new(tc.outputs['Object'],mapping.inputs[0])
    wave=n.new('ShaderNodeTexWave');wave.wave_type='RINGS';wave.rings_direction='X'
    wave.inputs['Scale'].default_value=78.;wave.inputs['Distortion'].default_value=3.5
    wave.inputs['Detail Scale'].default_value=2.2;l.new(mapping.outputs[0],wave.inputs['Vector'])
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=tuple(linear(c) for c in [.31,.21,.13])+(1,)
    ramp.color_ramp.elements[1].color=tuple(linear(c) for c in [.39,.28,.18])+(1,)
    l.new(wave.outputs['Color'],ramp.inputs[0]);l.new(ramp.outputs[0],bs.inputs['Base Color'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12;bump.inputs['Distance'].default_value=.000025
    l.new(wave.outputs['Color'],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal']);return mat


def photographic_tabletop(cfg,asset_root):
    f=cfg['physics']['fixture'];ap=cfg['appearance']['tabletop'];dx,dy,dz=f['table_dimensions_m'];top=f['table_top_z_m']
    mat,files=wood_material(asset_root,cfg,'wood_table_001');mat.name='Photographed warm hardwood, satin oil and handling variation'
    for n in mat.node_tree.nodes:
        if n.bl_idname=='ShaderNodeMapRange':
            n.inputs['To Min'].default_value=ap['roughness_range'][0];n.inputs['To Max'].default_value=ap['roughness_range'][1]
        elif n.bl_idname=='ShaderNodeNormalMap':n.inputs['Strength'].default_value=ap['normal_strength']
    bs=mat.node_tree.nodes.get('Principled BSDF');bs.inputs['Coat Weight'].default_value=0.
    handling_smudges(mat,bs,scale=6.,amount=.10)
    verts=[];faces=[];count=ap['board_count'];joint=ap['glue_joint_width_m'];width=dy/count
    for i in range(count):
        y0=.04-dy/2+i*width+(joint/2 if i else 0);y1=.04-dy/2+(i+1)*width-(joint/2 if i<count-1 else 0)
        off=len(verts);verts.extend([(x,y,z) for z in [top-dz,top] for y in [y0,y1] for x in [-dx/2,dx/2]])
        faces.extend([tuple(off+j for j in face) for face in [(0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5)]])
    table=mesh_object('Table',verts,faces,mat);table.data.materials.append(end_grain_material())
    for p in table.data.polygons:
        if abs(p.normal.x)>.5:p.material_index=1
    wood_uv(table,531,cfg['appearance']['wood']['table_repeat_m'],'X')
    weights=table.data.attributes.new('bevel_weight_edge','FLOAT','EDGE')
    for e in table.data.edges:
        a,b=(table.data.vertices[j].co for j in e.vertices)
        outer=(abs(abs(a.x)-dx/2)<1.e-6 and abs(a.x-b.x)<1.e-6) or (abs(abs(a.y-.04)-dy/2)<1.e-6 and abs(a.y-b.y)<1.e-6)
        weights.data[e.index].value=1. if outer else .00010/ap['edge_radius_m']
    bevel=table.modifiers.new('Softly worn outer arris, fine glued board joints','BEVEL');bevel.width=ap['edge_radius_m'];bevel.segments=4;bevel.limit_method='WEIGHT'
    table.modifiers.new('Planar tabletop weighted normals','WEIGHTED_NORMAL')
    table['fixed_collision_boundary']=True;table['collision_box_dimensions_m']=f['table_dimensions_m']
    table['appearance_only']='Microscopic glue joints and edge arris; collision outer envelope and contact top unchanged.'
    return table,{'asset':'https://polyhaven.com/a/wood_table_001','texture_repeat_m':cfg['appearance']['wood']['table_repeat_m'],
        'board_count':count,'glue_joint_width_m':joint,'edge_radius_m':ap['edge_radius_m'],
        'pbr_files':{k:str(v) for k,v in files.items()},'surface':'Photographic diffuse, roughness and OpenGL normal; physical grain orientation, no geometric displacement.'}


def thin_window_glass():
    mat=bpy.data.materials.new("Optically thin clear window glass, two-sided Fresnel");mat.use_nodes=True
    n,l=mat.node_tree.nodes,mat.node_tree.links;n.clear()
    out=n.new("ShaderNodeOutputMaterial");transparent=n.new("ShaderNodeBsdfTransparent")
    reflection=n.new("ShaderNodeBsdfAnisotropic");reflection.inputs["Roughness"].default_value=.035
    fresnel=n.new("ShaderNodeFresnel");fresnel.inputs["IOR"].default_value=1.46
    mix=n.new("ShaderNodeMixShader");l.new(fresnel.outputs[0],mix.inputs[0]);l.new(transparent.outputs[0],mix.inputs[1]);l.new(reflection.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],out.inputs["Surface"])
    return mat


def plaster_material(asset_root):
    mat=material("Photographic fine mineral plaster, 2 m repeat",(.80,.79,.76),.86)
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get("Principled BSDF")
    tc=n.new("ShaderNodeTexCoord");scale=n.new("ShaderNodeVectorMath");scale.operation="SCALE";scale.inputs["Scale"].default_value=.5;l.new(tc.outputs["Object"],scale.inputs[0])
    for suffix,role in [("diff","color"),("rough","roughness"),("nor_gl","normal")]:
        tex=n.new("ShaderNodeTexImage");tex.image=bpy.data.images.load(str(asset_root/f"architecture_pbr/white_stucco/white_stucco_{suffix}_4k.jpg"),check_existing=True)
        tex.projection="BOX";tex.projection_blend=.1;l.new(scale.outputs["Vector"],tex.inputs["Vector"])
        if role=="color":
            hue=n.new("ShaderNodeHueSaturation");hue.inputs["Saturation"].default_value=.35;hue.inputs["Value"].default_value=.94;l.new(tex.outputs["Color"],hue.inputs["Color"])
            tint=n.new("ShaderNodeMixRGB");tint.inputs[0].default_value=.82;tint.inputs[2].default_value=tuple(linear(c) for c in [.82,.815,.79])+(1,)
            l.new(hue.outputs[0],tint.inputs[1]);l.new(tint.outputs[0],bs.inputs["Base Color"])
        elif role=="roughness":
            tex.image.colorspace_settings.name="Non-Color";remap=n.new("ShaderNodeMapRange");remap.inputs["To Min"].default_value=.74;remap.inputs["To Max"].default_value=.94;l.new(tex.outputs["Color"],remap.inputs[0]);l.new(remap.outputs[0],bs.inputs["Roughness"])
        else:
            tex.image.colorspace_settings.name="Non-Color";normal=n.new("ShaderNodeNormalMap");normal.inputs["Strength"].default_value=.018;l.new(tex.outputs["Color"],normal.inputs["Color"]);l.new(normal.outputs[0],bs.inputs["Normal"])
    return mat


def wood_uv(obj,seed,repeat=1.83,grain_axis="X"):
    rng=random.Random(seed);ox,oy=rng.uniform(.05,.78),rng.uniform(.02,.5)
    uv=obj.data.uv_layers.new(name=f"Measured {repeat} m grain along {grain_axis}, independent board crop")
    for poly in obj.data.polygons:
        for idx in poly.loop_indices:
            v=obj.matrix_world@obj.data.vertices[obj.data.loops[idx].vertex_index].co
            if grain_axis=="Z":
                # Image grain runs along V. Both long upright faces therefore use V=Z.
                u,vv=(v.x,v.z) if abs(poly.normal.y)>.5 else ((v.y,v.z) if abs(poly.normal.x)>.5 else (v.x,v.y))
            elif grain_axis=="Y":
                u,vv=(v.x,v.y) if abs(poly.normal.z)>.5 else ((v.z,v.y) if abs(poly.normal.x)>.5 else (v.x,v.z))
            else:
                u,vv=(v.y,v.x) if abs(poly.normal.z)>.5 else ((v.z,v.x) if abs(poly.normal.y)>.5 else (v.y,v.z))
            uv.data[idx].uv=(u/repeat+ox,vv/repeat+oy)


def cord_knot(name,location,mat,tail):
    """Small overhand knot of the same cord with a short trimmed tail."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=16,radius=1.,location=location)
    knot=bpy.context.object;knot.name=name+" overhand knot";knot.scale=(.0026,.0023,.0025)
    knot.data.materials.append(mat)
    for p in knot.data.polygons:p.use_smooth=True
    disp=knot.modifiers.new("Lumpy wraps","DISPLACE");tex=bpy.data.textures.new(name+" knot lumps","CLOUDS");tex.noise_scale=.45
    disp.texture=tex;disp.strength=.18;disp.texture_coords="LOCAL"
    curve=bpy.data.curves.new(name+" trimmed tail","CURVE");curve.dimensions="3D";curve.bevel_depth=.00085;curve.bevel_resolution=2;curve.use_fill_caps=True
    spline=curve.splines.new("BEZIER");spline.bezier_points.add(len(tail)-1)
    for bp,co in zip(spline.bezier_points,tail):
        bp.co=Vector(location)+Vector(co);bp.handle_left_type=bp.handle_right_type="AUTO"
    obj=bpy.data.objects.new(name+" cord tail",curve);bpy.context.collection.objects.link(obj);obj.data.materials.append(mat)
    return knot,obj


def cylinder(name,location,radius,depth,mat,vertices=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=location)
    o=bpy.context.object;o.name=name;o.data.materials.append(mat)
    bevel=o.modifiers.new("Machined edge radius","BEVEL");bevel.width=min(.0003,radius*.15);bevel.segments=2
    o.modifiers.new("Weighted normals","WEIGHTED_NORMAL")
    return o


def torus(name,location,major,minor,mat):
    bpy.ops.mesh.primitive_torus_add(major_segments=48,minor_segments=12,location=location,major_radius=major,minor_radius=minor)
    o=bpy.context.object;o.name=name;o.data.materials.append(mat)
    for p in o.data.polygons:p.use_smooth=True
    return o


def metal_material(name,rgb):
    mat=material(name,rgb,.43);n,l=mat.node_tree.nodes,mat.node_tree.links
    bs=n.get("Principled BSDF");bs.inputs["Metallic"].default_value=.93
    tc=n.new("ShaderNodeTexCoord");noise=n.new("ShaderNodeTexNoise");noise.inputs["Scale"].default_value=2400
    l.new(tc.outputs["Object"],noise.inputs["Vector"])
    bump=n.new("ShaderNodeBump");bump.inputs["Strength"].default_value=.065;bump.inputs["Distance"].default_value=.000008
    l.new(noise.outputs["Fac"],bump.inputs["Height"]);l.new(bump.outputs["Normal"],bs.inputs["Normal"])
    return mat


def plywood_edge_material(pitch=.00385):
    mat=material("Birch plywood edge, pale veneers and thin glue lines",(.74,.63,.47),.66)
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get("Principled BSDF")
    tc=n.new("ShaderNodeTexCoord");sep=n.new("ShaderNodeSeparateXYZ");l.new(tc.outputs["Object"],sep.inputs["Vector"])
    scale=n.new("ShaderNodeMath");scale.operation="MULTIPLY";scale.inputs[1].default_value=2*math.pi/pitch;l.new(sep.outputs["Z"],scale.inputs[0])
    wave=n.new("ShaderNodeMath");wave.operation="SINE";l.new(scale.outputs[0],wave.inputs[0])
    # Narrow dark glue line at each ply interface; alternate plies differ slightly in tone.
    unit=n.new("ShaderNodeMapRange");unit.inputs["From Min"].default_value=-1.;l.new(wave.outputs[0],unit.inputs["Value"])
    ramp=n.new("ShaderNodeValToRGB");ramp.color_ramp.interpolation="EASE"
    ramp.color_ramp.elements[0].position=.0;ramp.color_ramp.elements[0].color=tuple(linear(c) for c in [.43,.34,.23])+(1,)
    ramp.color_ramp.elements[1].position=.06;ramp.color_ramp.elements[1].color=tuple(linear(c) for c in [.70,.59,.43])+(1,)
    top=ramp.color_ramp.elements.new(.8);top.color=tuple(linear(c) for c in [.80,.69,.52])+(1,)
    l.new(unit.outputs["Result"],ramp.inputs[0]);l.new(ramp.outputs[0],bs.inputs["Base Color"])
    noise=n.new("ShaderNodeTexNoise");noise.inputs["Scale"].default_value=2400;l.new(tc.outputs["Object"],noise.inputs["Vector"])
    bump=n.new("ShaderNodeBump");bump.inputs["Distance"].default_value=.000035;bump.inputs["Strength"].default_value=.13;l.new(noise.outputs["Fac"],bump.inputs["Height"]);l.new(bump.outputs[0],bs.inputs["Normal"])
    return mat


def profile_samples(points,count=6):
    """Shape-preserving cubic interpolation in Z; avoids spline overshoot."""
    slopes=[(b[0]-a[0])/(b[1]-a[1]) for a,b in zip(points,points[1:])];tangents=[slopes[0]]
    for a,b in zip(slopes,slopes[1:]):tangents.append(0. if a*b<=0 else 2*a*b/(a+b))
    tangents.append(slopes[-1]);result=[]
    for i,(a,b) in enumerate(zip(points,points[1:])):
        dz=b[1]-a[1]
        for j in range(count):
            t=j/count;r=(2*t**3-3*t**2+1)*a[0]+(t**3-2*t**2+t)*dz*tangents[i]+(-2*t**3+3*t**2)*b[0]+(t**3-t**2)*dz*tangents[i+1]
            result.append((max(0.,r),a[1]+t*dz))
    return result+[points[-1]]


def lathed_part(name,profile,mat,center,segments=96,reverse=False):
    verts=[];faces=[];rings=[]
    for radius,z in profile:
        start=len(verts)
        if radius<1.e-9:verts.append((0,0,z));rings.append([start])
        else:
            verts.extend([(radius*math.cos(j*2*math.pi/segments),radius*math.sin(j*2*math.pi/segments),z) for j in range(segments)])
            rings.append(list(range(start,start+segments)))
    for a,b in zip(rings,rings[1:]):
        for j in range(segments):
            k=(j+1)%segments
            face=(a[0],b[k],b[j]) if len(a)==1 else ((a[j],a[k],b[0]) if len(b)==1 else (a[j],a[k],b[k],b[j]))
            faces.append(tuple(reversed(face)) if reverse else face)
    obj=mesh_object(name,verts,faces,mat);obj.location=center
    for face in obj.data.polygons:face.use_smooth=True
    return obj


def bespoke_hourglass(cfg):
    ap=cfg['appearance']['props'];center=Vector(ap['center_m']);height=ap['height_m'];rad=ap['radius_m'];wall=ap['glass_wall_m'];created=[]
    bronze=metal_material('Hourglass satin patinated bronze caps',(.25,.21,.16));bronze.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.35
    brass=metal_material('Hourglass warm brushed brass rods',(.60,.48,.28));brass.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.31
    dark=material('Hourglass charcoal silicone glass seats',(.12,.12,.105),.79)
    for label,z in [('bottom',.007),('top',height-.007)]:
        created.append(cylinder('Hourglass '+label+' solid bronze cap',center+Vector((0,0,z)),rad,.014,bronze,96))
        seat_z=.0143 if label=='bottom' else height-.0143
        created.append(cylinder('Hourglass '+label+' contacting silicone seat',center+Vector((0,0,seat_z)),.015,.0014,dark,64))
    for i in range(3):
        angle=math.radians(35)+i*2*math.pi/3;x,y=.046*math.cos(angle),.046*math.sin(angle)
        created.append(cylinder('Hourglass brass support '+str(i),center+Vector((x,y,height/2)),.0018,height-.025,brass,32))
        for z in [.015,.180]:created.append(cylinder('Hourglass support ferrule',center+Vector((x,y,z)),.0031,.004,bronze,32))
    glass=material('Hourglass real 1.1 mm clear glass',(.98,.99,1.),.025);bs=glass.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Transmission Weight'].default_value=1.;bs.inputs['IOR'].default_value=1.46
    p=[(0.,.0145),(.013,.0150),(.027,.021),(.036,.034),(.038,.046),(.034,.059),(.026,.073),(.014,.083),(.004,.090),(.0028,.094),(.004,.098),(.014,.105),(.026,.116),(.034,.131),(.037,.146),(.033,.161),(.021,.172),(.008,.177),(0.,.1805)]
    outer=lathed_part('Hourglass closed glass outer surface',profile_samples(p),glass,center)
    inside=[(0.,.0156)]+[(max(.0003,r-wall),z) for r,z in p[2:-2]]+[(.0069,.176),(0.,.1794)]
    inner=lathed_part('Hourglass closed glass inner surface',profile_samples(inside),glass,center,reverse=True)
    # Join two oppositely oriented watertight surfaces into a true glass volume.
    bpy.ops.object.select_all(action='DESELECT');outer.select_set(True);inner.select_set(True);bpy.context.view_layer.objects.active=outer;bpy.ops.object.join()
    outer.name='Hourglass hollow glass vessel';outer['nominal_radial_wall_m']=wall;created.append(outer)
    sand=material('Hourglass pale fine dry quartz sand',(.73,.65,.47),.84);n,l=sand.node_tree.nodes,sand.node_tree.links
    tc=n.new('ShaderNodeTexCoord');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=6200.;noise.inputs['Detail'].default_value=2.;l.new(tc.outputs['Object'],noise.inputs['Vector'])
    bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000055;bump.inputs['Strength'].default_value=.24;l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],n.get('Principled BSDF').inputs['Normal'])
    # Already-finished timer: no stationary falling stream is presented as sand dynamics.
    sand_profile=[(0.,.0168),(.011,.017),(.025,.0235),(.034,.036),(.0361,.045),(.0330,.054),(.029,.058),(.022,.063),(.013,.069),(0.,.077)]
    created.append(lathed_part('Hourglass settled lower sand pile',profile_samples(sand_profile),sand,center))
    for o in created:o['noninteractive_background_prop']=True;o['authored_for_scene']='opposing_pendulum_collision';o['source_asset']='scene_specific_bespoke_hourglass'
    bpy.context.view_layer.update()
    return {'type':ap['asset'],'authored_for_scene':'opposing_pendulum_collision','reused_prior_scene_props':False,
        'center_m':list(center),'bounds_m':evaluated_bounds(created),'height_m':height,'diameter_m':rad*2,
        'glass_wall_m':wall,'glass_IOR':1.46,'glass_model':'Closed outer surface and reversed closed inner surface; no single-face fake glass',
        'sand_state':ap['sand_state'],'simulation_role':'Static decoration; no grain simulation or implied animated sand flow',
        'removed':['tea cup','saucer','linen mat','measuring tape','notebook'],
        'placement':'Rear-right tabletop strip, physically seated on the tabletop and outside the base and swept spheres.'}


def linen_material(name,color):
    mat=material(name,color,.84);n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get('Principled BSDF')
    tc=n.new('ShaderNodeTexCoord');waves=[]
    for axis in ['X','Y']:
        wave=n.new('ShaderNodeTexWave');wave.wave_type='BANDS';wave.bands_direction=axis
        wave.inputs['Scale'].default_value=1900.;wave.inputs['Distortion'].default_value=.7
        l.new(tc.outputs['Object'],wave.inputs['Vector']);waves.append(wave)
    combine=n.new('ShaderNodeMath');combine.operation='MULTIPLY'
    for i,w in enumerate(waves):l.new(w.outputs['Fac'],combine.inputs[i])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.22;bump.inputs['Distance'].default_value=.000085
    l.new(combine.outputs[0],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal'])
    bs.inputs['Sheen Weight'].default_value=.18;return mat


def place_imported_group(objects,center_xy,bottom_z,rotation_z):
    bpy.context.view_layer.update();before=evaluated_bounds(objects)
    center=Vector(((before[0][0]+before[1][0])/2,(before[0][1]+before[1][1])/2,before[0][2]))
    fit=Matrix.Translation(Vector((*center_xy,bottom_z)))@Matrix.Rotation(rotation_z,4,'Z')@Matrix.Translation(-center)
    for o in objects:o.matrix_world=fit@o.matrix_world
    bpy.context.view_layer.update();return {'source_bounds_m':before,'placed_bounds_m':evaluated_bounds(objects),'uniform_scale':1.0}


def restored_stationery(cfg,asset_root):
    top=cfg['physics']['fixture']['table_top_z_m'];ap=cfg['appearance']['props']['stationery']
    nx,ny,_=ap['notebook_center_m'];cover=linen_material('Faded slate linen notebook cover',(.31,.38,.40))
    paper=material('Warm uncoated notebook page edges',(.76,.73,.65),.84)
    book=[]
    for name,z,dims,mat in [('Notebook back cloth cover',top+.0012,(.203,.142,.0024),cover),('Notebook cream page block',top+.0068,(.198,.137,.009),paper),('Notebook front cloth cover',top+.0125,(.203,.142,.0024),cover)]:
        o=box(name,(nx,ny,z),dims,mat,.0008);book.append(o)
    # Individual page-edge relief stays below a pixel at the formal camera.
    page_line=material('Subtle individual paper leaf edges',(.63,.60,.53),.86)
    for i in range(10):
        o=box('Fine notebook leaf edge',(nx,ny-.0686,top+.0026+i*.00086),(.194,.00010,.000055),page_line);book.append(o)
    for o in book:
        point=Vector((nx,ny,top));o.matrix_world=Matrix.Translation(point)@Matrix.Rotation(ap['notebook_rotation_z_rad'],4,'Z')@Matrix.Translation(-point)@o.matrix_world
        o['noninteractive_background_prop']=True
    root=asset_root/'polyhaven/measuring_tape_01';objects,names,worlds=append_asset_objects(root/'measuring_tape_01_2k.blend','Everyday_')
    tape_fit=place_imported_group(objects,(nx-.003,ny+.002),top+.0137,math.pi/2-.15)
    for o in objects:o['source_asset']='polyhaven_measuring_tape_01';o['noninteractive_background_prop']=True
    # All used texture paths are resolved from packaged scene-owned assets.
    for im in bpy.data.images:
        if im.source!='FILE':continue
        for asset in ['measuring_tape_01']:
            p=asset_root/'polyhaven'/asset/'textures'/Path(im.filepath).name
            if p.is_file():im.filepath=str(p)
    bpy.context.view_layer.update()
    return {'notebook_dimensions_m':[.203,.142,.0137], 'notebook_bounds_m':evaluated_bounds(book),
        'measuring_tape':tape_fit, 'source':'Earlier version of opposing_pendulum_collision, explicitly restored at user request',
        'placement':'Rear-left tabletop strip; notebook rests on the table, tape rests on the notebook; no simulated contacts.'}


def aluminium_material(name,axis,roughness=.30,cast=False):
    """Clear anodized 6063: drawing streaks run along the extrusion axis."""
    mat=material(name,(.80,.81,.82),roughness);n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get("Principled BSDF")
    bs.inputs["Metallic"].default_value=1.
    tc=n.new("ShaderNodeTexCoord");mp=n.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value=(1.,1.,1.) if cast else tuple(.015 if a==axis else 1. for a in "XYZ")
    l.new(tc.outputs["Object"],mp.inputs["Vector"])
    streak=n.new("ShaderNodeTexNoise");streak.inputs["Scale"].default_value=900 if cast else 1400;streak.inputs["Detail"].default_value=6;l.new(mp.outputs[0],streak.inputs["Vector"])
    rough=n.new("ShaderNodeMapRange");rough.inputs["To Min"].default_value=roughness-.07;rough.inputs["To Max"].default_value=roughness+.08
    l.new(streak.outputs["Fac"],rough.inputs["Value"]);l.new(rough.outputs["Result"],bs.inputs["Roughness"])
    bump=n.new("ShaderNodeBump");bump.inputs["Strength"].default_value=.12 if cast else .05;bump.inputs["Distance"].default_value=.00001
    l.new(streak.outputs["Fac"],bump.inputs["Height"]);l.new(bump.outputs["Normal"],bs.inputs["Normal"])
    if not cast:
        bs.inputs["Anisotropic"].default_value=.55
        tangent=n.new("ShaderNodeTangent");tangent.direction_type="RADIAL";tangent.axis=axis
        # Radial tangent around the member axis gives highlights stretched across the streaks.
        l.new(tangent.outputs["Tangent"],bs.inputs["Tangent"])
    return mat


def slot8_profile(size=.030,slot=.008):
    """B-type 30x30 slot-8 outline (m): lip, undercut chamber and V floor on each face."""
    h=size/2;w=slot/2;face=[(0.,-w),(.0022,-w),(.0022,-.0082),(.0044,-.0082),(.0080,-.0046),(.0080,.0046),(.0044,.0082),(.0022,.0082),(.0022,w),(0.,w)]
    pts=[]
    for k in range(4):
        c,s=math.cos(k*math.pi/2),math.sin(k*math.pi/2)
        rot=lambda x,y:(c*x-s*y,s*x+c*y)
        pts.append(rot(h,-h+.0006));pts+=[rot(h-d,t) for d,t in face];pts.append(rot(h,h-.0006))
    return pts


def extrusion(name,center,dims,mat,profile):
    import bmesh
    axis=max(range(3),key=lambda i:dims[i]);length=dims[axis];a,b=[i for i in range(3) if i!=axis]
    bm=bmesh.new();rings=[]
    for t in [-length/2,length/2]:
        ring=[]
        for u,v in profile:
            co=[0.,0.,0.];co[axis]=t;co[a]=u;co[b]=v;ring.append(bm.verts.new(co))
        rings.append(ring)
    m=len(profile)
    for i in range(m):bm.faces.new((rings[0][i],rings[0][(i+1)%m],rings[1][(i+1)%m],rings[1][i]))
    bm.faces.new(rings[0][::-1]);bm.faces.new(rings[1])
    bmesh.ops.recalc_face_normals(bm,faces=bm.faces[:])
    mesh=bpy.data.meshes.new(name);bm.to_mesh(mesh);bm.free()
    o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);o.location=center;o.data.materials.append(mat)
    bevel=o.modifiers.new("Extrusion edge radius","BEVEL");bevel.width=.00025;bevel.segments=2;bevel.limit_method="ANGLE"
    o.modifiers.new("Weighted normals","WEIGHTED_NORMAL")
    return o


def corner_bracket(name,corner,a,b,width_axis,leg,mat,width=.028,land=.004):
    """Cast 90 deg bracket in the inner corner: two legs with flat lands and a chamfered web."""
    import bmesh
    corner,a,b,wv=Vector(corner),Vector(a),Vector(b),Vector(width_axis)
    outline=[(0.,0.),(leg,0.),(leg,land),(land,leg),(0.,leg)]
    bm=bmesh.new();rings=[[bm.verts.new(corner+a*u+b*v+wv*s*width/2) for u,v in outline] for s in [-1,1]]
    for i in range(5):bm.faces.new((rings[0][i],rings[0][(i+1)%5],rings[1][(i+1)%5],rings[1][i]))
    bm.faces.new(rings[0]);bm.faces.new(rings[1][::-1]);bmesh.ops.recalc_face_normals(bm,faces=bm.faces[:])
    mesh=bpy.data.meshes.new(name);bm.to_mesh(mesh);bm.free()
    o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);o.data.materials.append(mat)
    bevel=o.modifiers.new("Cast edge radius","BEVEL");bevel.width=.0006;bevel.segments=2
    o.modifiers.new("Weighted normals","WEIGHTED_NORMAL")
    return o


def handling_smudges(mat,bs,scale,amount):
    """Broad, low-contrast patches of extra roughness added on top of the scanned roughness."""
    n,l=mat.node_tree.nodes,mat.node_tree.links;link=next(k for k in l if k.to_socket==bs.inputs['Roughness'])
    tc=n.new('ShaderNodeTexCoord');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=scale;noise.inputs['Detail'].default_value=5;noise.inputs['Roughness'].default_value=.6
    l.new(tc.outputs['Object'],noise.inputs['Vector'])
    patch=n.new('ShaderNodeMapRange');patch.inputs['From Min'].default_value=.48;patch.inputs['From Max'].default_value=.68;patch.inputs['To Max'].default_value=amount
    l.new(noise.outputs['Fac'],patch.inputs['Value'])
    add=n.new('ShaderNodeMath');add.operation='ADD';add.use_clamp=True;l.new(link.from_socket,add.inputs[0]);l.new(patch.outputs['Result'],add.inputs[1])
    l.new(add.outputs[0],bs.inputs['Roughness'])


def plywood_face_material(cfg,asset_root):
    """Poly Haven scanned plywood face (0.5 m tile), unfinished but sealed; low sheen."""
    ap=cfg["appearance"]["base_board"];root=asset_root/"polyhaven"/ap["surface_asset"]
    mat=material("Sealed birch plywood face, scanned",(.7,.6,.45),.6);n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get("Principled BSDF")
    uv=n.new("ShaderNodeTexCoord")
    def image(suffix,colour=True):
        tex=n.new("ShaderNodeTexImage");tex.image=bpy.data.images.load(str(next(root.glob(f"*{suffix}*.jpg"))),check_existing=True)
        if not colour:tex.image.colorspace_settings.name="Non-Color"
        l.new(uv.outputs["UV"],tex.inputs["Vector"]);return tex
    col=image("_diff_");hue=n.new("ShaderNodeHueSaturation");hue.inputs["Saturation"].default_value=.82;hue.inputs["Value"].default_value=.97
    l.new(col.outputs["Color"],hue.inputs["Color"])
    # Sheet-scale tonal drift breaks up the 0.5 m tile repeat across a 1.54 m board.
    tc=n.new("ShaderNodeTexCoord");drift=n.new("ShaderNodeTexNoise");drift.inputs["Scale"].default_value=2.2;drift.inputs["Detail"].default_value=3
    l.new(tc.outputs["Object"],drift.inputs["Vector"])
    shade=n.new("ShaderNodeMapRange");shade.inputs["To Min"].default_value=.88;shade.inputs["To Max"].default_value=1.06;l.new(drift.outputs["Fac"],shade.inputs["Value"])
    mul=n.new("ShaderNodeVectorMath");mul.operation="SCALE";l.new(hue.outputs["Color"],mul.inputs[0]);l.new(shade.outputs["Result"],mul.inputs["Scale"])
    l.new(mul.outputs[0],bs.inputs["Base Color"])
    rough=image("_rough_",False);remap=n.new("ShaderNodeMapRange")
    remap.inputs["To Min"].default_value,remap.inputs["To Max"].default_value=ap["roughness_range"]
    l.new(rough.outputs["Color"],remap.inputs["Value"]);l.new(remap.outputs["Result"],bs.inputs["Roughness"])
    nor=image("_nor_gl_",False);nm=n.new("ShaderNodeNormalMap");nm.inputs["Strength"].default_value=ap["normal_strength"]
    l.new(nor.outputs["Color"],nm.inputs["Color"]);l.new(nm.outputs["Normal"],bs.inputs["Normal"])
    handling_smudges(mat,bs,scale=9.,amount=.06)
    return mat


def cord_material(cfg):
    ap=cfg["appearance"]["rope"];mat=material("Ordinary woven cotton polyester cord",ap["color_srgb"],.76)
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get("Principled BSDF")
    bs.inputs["Specular IOR Level"].default_value=.25
    tc=n.new("ShaderNodeTexCoord");sep=n.new("ShaderNodeSeparateXYZ");l.new(tc.outputs["Object"],sep.inputs["Vector"])
    angle=n.new("ShaderNodeMath");angle.operation="ARCTAN2";l.new(sep.outputs["Y"],angle.inputs[0]);l.new(sep.outputs["X"],angle.inputs[1])
    mul=n.new("ShaderNodeMath");mul.operation="MULTIPLY";mul.inputs[1].default_value=3.;l.new(angle.outputs[0],mul.inputs[0])
    z=n.new("ShaderNodeMath");z.operation="MULTIPLY";z.inputs[1].default_value=2*math.pi/ap["braid_pitch_m"];l.new(sep.outputs["Z"],z.inputs[0])
    masks=[]
    for op in ["ADD","SUBTRACT"]:
        combine=n.new("ShaderNodeMath");combine.operation=op;l.new(mul.outputs[0],combine.inputs[0]);l.new(z.outputs[0],combine.inputs[1])
        wave=n.new("ShaderNodeMath");wave.operation="SINE";l.new(combine.outputs[0],wave.inputs[0]);masks.append(wave)
    weave=n.new("ShaderNodeMath");weave.operation="MULTIPLY";l.new(masks[0].outputs[0],weave.inputs[0]);l.new(masks[1].outputs[0],weave.inputs[1])
    bump=n.new("ShaderNodeBump");bump.inputs["Strength"].default_value=.32;bump.inputs["Distance"].default_value=.000055
    l.new(weave.outputs[0],bump.inputs["Height"]);l.new(bump.outputs["Normal"],bs.inputs["Normal"])
    noise=n.new("ShaderNodeTexNoise");noise.inputs["Scale"].default_value=4200.;noise.inputs["Detail"].default_value=2.;l.new(tc.outputs["Object"],noise.inputs["Vector"])
    mix=n.new("ShaderNodeMixRGB");mix.blend_type="MULTIPLY";mix.inputs[0].default_value=.19;mix.inputs[1].default_value=tuple(linear(c) for c in ap["color_srgb"])+(1,)
    l.new(noise.outputs["Color"],mix.inputs[2]);l.new(mix.outputs[0],bs.inputs["Base Color"])
    return mat


def cord_surface_modifier(obj,cfg,mat):
    """Three cotton bundles are generated from the animated physical centerline."""
    ap=cfg["appearance"]["rope"];radius=ap["radius_m"]
    tree=bpy.data.node_groups.new(obj.name+" real laid cotton bundles","GeometryNodeTree")
    tree.interface.new_socket(name="Geometry",in_out="INPUT",socket_type="NodeSocketGeometry")
    tree.interface.new_socket(name="Geometry",in_out="OUTPUT",socket_type="NodeSocketGeometry")
    n,l=tree.nodes,tree.links;inp=n.new("NodeGroupInput");out=n.new("NodeGroupOutput")
    resample=n.new("GeometryNodeResampleCurve");resample.mode="LENGTH";resample.inputs["Length"].default_value=.00065
    l.new(inp.outputs["Geometry"],resample.inputs["Curve"])
    profile=n.new("GeometryNodeCurvePrimitiveCircle");profile.inputs["Resolution"].default_value=8;profile.inputs["Radius"].default_value=radius*.46
    normal=n.new("GeometryNodeInputNormal");tangent=n.new("GeometryNodeInputTangent");parameter=n.new("GeometryNodeSplineParameter")
    angle=n.new("ShaderNodeMath");angle.operation="MULTIPLY";angle.inputs[1].default_value=2*math.pi/ap["braid_pitch_m"];l.new(parameter.outputs["Length"],angle.inputs[0])
    width=n.new("ShaderNodeVectorMath");width.operation="SCALE";width.inputs["Scale"].default_value=radius*.54;l.new(normal.outputs["Normal"],width.inputs[0])
    join=n.new("GeometryNodeJoinGeometry")
    for i in range(3):
        phase=n.new("ShaderNodeMath");phase.operation="ADD";phase.inputs[1].default_value=i*2*math.pi/3;l.new(angle.outputs[0],phase.inputs[0])
        rotate=n.new("ShaderNodeVectorRotate");rotate.rotation_type="AXIS_ANGLE"
        l.new(width.outputs["Vector"],rotate.inputs["Vector"]);l.new(tangent.outputs["Tangent"],rotate.inputs["Axis"]);l.new(phase.outputs[0],rotate.inputs["Angle"])
        position=n.new("GeometryNodeSetPosition");l.new(resample.outputs["Curve"],position.inputs["Geometry"]);l.new(rotate.outputs["Vector"],position.inputs["Offset"])
        tube=n.new("GeometryNodeCurveToMesh");tube.inputs["Fill Caps"].default_value=True
        l.new(position.outputs["Geometry"],tube.inputs["Curve"]);l.new(profile.outputs["Curve"],tube.inputs["Profile Curve"]);l.new(tube.outputs["Mesh"],join.inputs["Geometry"])
    core=n.new("GeometryNodeCurvePrimitiveCircle");core.inputs["Resolution"].default_value=8;core.inputs["Radius"].default_value=radius*.50
    tube=n.new("GeometryNodeCurveToMesh");tube.inputs["Fill Caps"].default_value=True
    l.new(resample.outputs["Curve"],tube.inputs["Curve"]);l.new(core.outputs["Curve"],tube.inputs["Profile Curve"]);l.new(tube.outputs["Mesh"],join.inputs["Geometry"])
    setmat=n.new("GeometryNodeSetMaterial");setmat.inputs["Material"].default_value=mat;l.new(join.outputs["Geometry"],setmat.inputs["Geometry"]);l.new(setmat.outputs["Geometry"],out.inputs["Geometry"])
    mod=obj.modifiers.new("Cotton bundles follow the solved centerline","NODES");mod.node_group=tree


def build_ropes(cfg,physics):
    ropes={};mat=cord_material(cfg);reports={}
    for name,r in cfg["physics"]["ropes"].items():
        if not r["present"] or not cfg["physics"]["balls"][name]["present"]:continue
        curve=bpy.data.curves.new(name+" physically attached cord","CURVE");curve.dimensions="3D";curve.resolution_u=1
        curve.bevel_depth=0;curve.use_fill_caps=True
        spline=curve.splines.new("POLY");spline.points.add(32)
        obj=bpy.data.objects.new(name+"_rope",curve);bpy.context.collection.objects.link(obj);obj.rotation_mode="QUATERNION"
        obj.location=r["anchor_m"];obj.data.materials.append(mat);obj["rope_endpoint_length_m"]=r["length_m"]
        cord_surface_modifier(obj,cfg,mat)
        x,y,z=r["anchor_m"];cord_knot(name+" anchor",(x,y,z-.0004),mat,[(.0010,0.,-.0004),(.0018,.0004,-.0060),(.0021,.0008,-.0105)])
        obj["visual_model"]="Centerline uses actual simulated endpoints. Slack is an inextensible quasi-static sine sag; no bending forces in physics."
        last=None;maxerr=0.
        for sample in physics["frames"]:
            rope=sample["objects"][name]["rope"];start=Vector(rope["anchor_m"]);end=Vector(rope["attachment_world_m"])
            d=end-start;distance=d.length;axis=d.normalized();down=Vector((0,0,-1));xx=down-axis*down.dot(axis)
            if xx.length<1.e-7:xx=Vector((0,1,0))-axis*axis.y
            xx.normalize();yy=axis.cross(xx).normalized()
            # Re-orthogonalize after float32 cancellation near a vertical chord.
            # This makes local +Z follow the actual endpoint direction precisely.
            xx=yy.cross(axis).normalized();rot=Matrix((xx,yy,axis)).transposed().to_quaternion()
            if last is not None and rot.dot(last)<0:rot.negate()
            last=rot.copy();obj.rotation_quaternion=rot;frame=sample["frame_index"];obj.keyframe_insert(data_path="rotation_quaternion",frame=frame)
            length=r["length_m"];us=[i/32 for i in range(33)]
            def centers(sag):return [Vector((sag*math.sin(math.pi*u),0.,distance*u)) for u in us]
            def arc(sag):
                pts=centers(sag);return sum((b-a).length for a,b in zip(pts,pts[1:]))
            lo,hi=0.,length/2
            if distance<length-1.e-10:
                for _ in range(35):
                    mid=(lo+hi)/2
                    if arc(mid)>length:hi=mid
                    else:lo=mid
            sag=(lo+hi)/2 if distance<length-1.e-10 else 0.;points=centers(sag)
            maxerr=max(maxerr,abs(arc(sag)-length))
            for p,co in zip(spline.points,points):p.co=(*co,1.);p.keyframe_insert(data_path="co",frame=frame)
        for block in [obj,curve]:
            if block.animation_data:
                for fc in block.animation_data.action.fcurves:
                    for key in fc.keyframe_points:key.interpolation="LINEAR"
        ropes[name]=obj;reports[name]={"max_visual_polyline_length_error_m":maxerr,"endpoints":"Actual solved world endpoints at every video frame",
            "slack_shape":"Quasi-static inextensible sine sag, no simulated cord mass or bending stiffness",
            "surface":"Geometry Nodes lays three cotton bundles around the actual animated centerline; outer radius matches configuration. Fine weave and fiber roughness use local material coordinates."}
    return ropes,reports


def ball_material(cfg, name):
    """Solid pigmented ABS (about 1.05 g/cm3, so a 60 mm ball weighs about 120 g): glossy, no print."""
    ap = cfg["appearance"]["ball"]; rgb = ap["red_srgb" if name == "B_left" else "blue_srgb"]
    mat = material(name + " solid glossy ABS plastic", rgb, ap["roughness"])
    n, l = mat.node_tree.nodes, mat.node_tree.links; bs = n.get("Principled BSDF")
    bs.inputs["IOR"].default_value = ap["ior"]
    tc = n.new("ShaderNodeTexCoord")
    # Handling marks: broad, faint patches of slightly higher roughness.
    smudge = n.new("ShaderNodeTexNoise"); smudge.inputs["Scale"].default_value = 38
    smudge.inputs["Detail"].default_value = 4; smudge.inputs["Roughness"].default_value = .62
    l.new(tc.outputs["Object"], smudge.inputs["Vector"])
    rough = n.new("ShaderNodeMapRange"); rough.inputs["From Min"].default_value = .45; rough.inputs["From Max"].default_value = .72
    rough.inputs["To Min"].default_value, rough.inputs["To Max"].default_value = ap["roughness_range"]
    l.new(smudge.outputs["Fac"], rough.inputs["Value"]); l.new(rough.outputs["Result"], bs.inputs["Roughness"])
    micro = n.new("ShaderNodeTexNoise"); micro.inputs["Scale"].default_value = 5200; micro.inputs["Detail"].default_value = 2
    l.new(tc.outputs["Object"], micro.inputs["Vector"])
    bump = n.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = .03; bump.inputs["Distance"].default_value = .000005
    l.new(micro.outputs["Fac"], bump.inputs["Height"]); l.new(bump.outputs["Normal"], bs.inputs["Normal"])
    return mat


def build_balls(cfg):
    objects = {}
    for name, b in cfg["physics"]["balls"].items():
        if not b["present"]:
            continue
        bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=64, radius=b["radius_m"])
        ball = bpy.context.object; ball.name = name; ball.rotation_mode = "QUATERNION"
        ball.data.materials.append(ball_material(cfg, name))
        for face in ball.data.polygons:
            face.use_smooth = True
        objects[name] = ball
    metal = metal_material("Small embedded ball eyelets, satin brass", (.53, .43, .26))
    cord = cord_material(cfg)
    for name, ball in objects.items():
        collar = cylinder(name + " resin eyelet insert", (0., 0., .029), .0028, .006, metal, 24); collar.parent = ball
        eye = torus(name + " real rope attachment eye", (0., 0., .033), .0028, .0007, metal)
        eye.parent = ball; eye.rotation_euler = (math.pi / 2, 0., 0.)
        if cfg["physics"]["ropes"][name]["present"]:
            # Cord is tied through the eye; knot sits on the solved attachment point.
            for part in cord_knot(name + " eye", (0., 0., .0378), cord, [(.0012, 0., -.0003), (.0036, -.0008, -.0030), (.0050, -.0013, -.0062)]):
                part.parent = ball
    return objects


def resolve_textures(asset_dirs):
    """Point appended images at the registered texture files (library-relative paths do not survive append)."""
    for im in bpy.data.images:
        if im.source != "FILE" or not im.filepath:
            continue
        for d in asset_dirs:
            p = d / "textures" / Path(bpy.path.abspath(im.filepath)).name
            if p.is_file():
                im.filepath = str(p); break


def scanned_floor_material(asset_root, ap):
    """Poly Haven wood_floor scan at its measured 1.70 m tile; planks run along the room depth (Y)."""
    root = asset_root / "polyhaven" / ap["asset"]
    mat = bpy.data.materials.new("Scanned lacquered oak plank floor"); mat.use_nodes = True
    n, l = mat.node_tree.nodes, mat.node_tree.links; bs = n.get("Principled BSDF")
    tc = n.new("ShaderNodeTexCoord"); mp = n.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / ap["tile_m"],) * 3; mp.inputs["Location"].default_value = (ap["offset"][0], ap["offset"][1], 0.)
    l.new(tc.outputs["Object"], mp.inputs["Vector"])
    def image(suffix, colour):
        tex = n.new("ShaderNodeTexImage"); tex.image = bpy.data.images.load(str(next(root.glob(f"*{suffix}*.jpg"))), check_existing=True)
        if not colour:
            tex.image.colorspace_settings.name = "Non-Color"
        l.new(mp.outputs["Vector"], tex.inputs["Vector"]); return tex
    col = image("_diff_", True)
    # Room-scale tonal drift (about 3 m) so the 1.7 m tile does not read as a repeat.
    drift = n.new("ShaderNodeTexNoise"); drift.inputs["Scale"].default_value = .33; drift.inputs["Detail"].default_value = 2
    l.new(tc.outputs["Object"], drift.inputs["Vector"])
    shade = n.new("ShaderNodeMapRange"); shade.inputs["To Min"].default_value = .90; shade.inputs["To Max"].default_value = 1.07
    l.new(drift.outputs["Fac"], shade.inputs["Value"])
    hue = n.new("ShaderNodeHueSaturation"); hue.inputs["Saturation"].default_value = ap["saturation"]; hue.inputs["Value"].default_value = ap["value"]
    l.new(col.outputs["Color"], hue.inputs["Color"])
    mul = n.new("ShaderNodeVectorMath"); mul.operation = "SCALE"; l.new(hue.outputs["Color"], mul.inputs[0]); l.new(shade.outputs["Result"], mul.inputs["Scale"])
    l.new(mul.outputs[0], bs.inputs["Base Color"])
    rough = image("_rough_", False); remap = n.new("ShaderNodeMapRange")
    remap.inputs["To Min"].default_value, remap.inputs["To Max"].default_value = ap["roughness_range"]
    l.new(rough.outputs["Color"], remap.inputs["Value"]); l.new(remap.outputs["Result"], bs.inputs["Roughness"])
    nor = image("_nor_gl_", False); nm = n.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = ap["normal_strength"]
    l.new(nor.outputs["Color"], nm.inputs["Color"]); l.new(nm.outputs["Normal"], bs.inputs["Normal"])
    handling_smudges(mat, bs, scale=1.4, amount=.05)
    return mat, {k: str(next(root.glob(f"*{s}*.jpg"))) for k, s in [("color", "_diff_"), ("roughness", "_rough_"), ("normal", "_nor_gl_")]}


def append_window(asset_root, glass, rotation_z, translation):
    objects, names, worlds = append_asset_objects(asset_root / 'blenderkit/pendulum_sliding_window/sliding_window.blend', 'Window_')
    before = evaluated_bounds(objects)
    fit = Matrix.Translation(Vector(translation)) @ Matrix.Rotation(rotation_z, 4, 'Z') @ Matrix.Translation(Vector(((before[0][0] + before[1][0]) / -2, 0., 0.)))
    kept = []
    for o in objects:
        if o.type != 'MESH':
            bpy.data.objects.remove(o, do_unlink=True); continue
        o.matrix_world = fit @ o.matrix_world; o['source_asset'] = '7f77e8d9-4cb7-40a4-b20e-6a411c2afd0c'; kept.append(o)
        for i, m in enumerate(o.data.materials):
            if m and m.name.lower().startswith('glass'):
                o.data.materials[i] = glass
    bpy.context.view_layer.update()
    return kept, before


def cut_opening(wall, center, dims):
    cutter = box('Temporary window opening cutter', center, dims, None)
    mod = wall.modifiers.new('Actual through-wall window reveal', 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.solver = 'EXACT'; mod.object = cutter
    bpy.context.view_layer.objects.active = wall; bpy.ops.object.modifier_apply(modifier=mod.name); bpy.data.objects.remove(cutter, do_unlink=True)


def wall_frame(r, wall):
    """Wall centre line and inward normal: rear (+Y, the visible window wall), left (-X) or front (-Y, behind the camera)."""
    if wall == 'rear':
        return (lambda c, z: Vector((c, r['rear_wall_center_y_m'], z))), Vector((0., -1., 0.)), 0.
    if wall == 'left':
        return (lambda c, z: Vector((-r['width_m'] / 2, c, z))), Vector((1., 0., 0.)), math.pi / 2
    return (lambda c, z: Vector((c, r['front_wall_y_m'], z))), Vector((0., 1., 0.)), math.pi


def window_list(r):
    wx, wy, wz = r['window_center_m']
    return [{'wall': 'rear', 'center_m': wx, 'center_z_m': wz}] + list(r['extra_windows'])


def room(cfg, asset_root):
    r = cfg['appearance']['room']; wall_y = r['rear_wall_center_y_m']
    width = r['width_m']; height = r['height_m']; thick = r['wall_thickness_m']; front = r['front_wall_y_m']
    glass = thin_window_glass()
    wall = plaster_material(asset_root); trim = paint_material('Satin warm white window board and skirting', (.86, .85, .81))
    depth = wall_y - front
    walls = {'rear': box('Continuous plaster wall with true window opening', (0, wall_y, height / 2), (width, thick, height), wall),
             'left': box('Left plaster wall with true window openings', (-width / 2, (wall_y + front) / 2, height / 2), (thick, depth, height), wall),
             'front': box('Wall behind camera with true window opening', (0, front, height / 2), (width, thick, height), wall)}
    placed = []
    for i, w in enumerate(window_list(r)):
        point, normal, rot = wall_frame(r, w['wall']); c, z = w['center_m'], w['center_z_m']
        objs, before = append_window(asset_root, glass, rot, point(c, z - .60))
        opening = (before[1][0] - before[0][0] - .010, 1.190); along = Vector((-normal.y, normal.x, 0.))
        dims = [abs(along.x) * opening[0] + abs(normal.x) * .55, abs(along.y) * opening[0] + abs(normal.y) * .55, opening[1]]
        cut_opening(walls[w['wall']], point(c, z), dims)
        sill = [abs(along.x) * 1.13 + abs(normal.x) * .305, abs(along.y) * 1.13 + abs(normal.y) * .305, .024]
        box(f'Painted timber window board {i}', point(c, z - .613) + normal * .063, sill, trim, .003)
        lip = [abs(along.x) * 1.06 + abs(normal.x) * .030, abs(along.y) * 1.06 + abs(normal.y) * .030, .040]
        box(f'Window board underside trim {i}', point(c, z - .644) + normal * .125, lip, trim, .002)
        placed.append({**w, 'opening_m': list(opening), 'bounds_m': evaluated_bounds(objs),
                       'portal_center_m': list(point(c, z) + normal * (thick / 2 - .02)), 'inward_normal': list(normal)})
    for o in walls.values():
        b = o.modifiers.new('2 mm plaster reveal arris', 'BEVEL'); b.width = .002; b.segments = 3
        o.modifiers.new('Continuous wall weighted normals', 'WEIGHTED_NORMAL')
    for name, loc, dims in [('Right plaster wall', (width / 2, (wall_y + front) / 2, height / 2), (thick, depth, height)),
                            ('Room ceiling', (0, (wall_y + front) / 2, height + .05), (width, depth + thick, .10))]:
        box(name, loc, dims, wall)
    left_x = -width / 2
    inner_rear = wall_y - thick / 2; inner_left = left_x + thick / 2
    box('Continuous rear skirting', (0, inner_rear - .0125, .050), (width - thick, .025, .10), trim, .0015)
    box('Left wall skirting', (inner_left + .0125, (inner_rear + front + thick / 2) / 2, .050), (.025, inner_rear - front - thick / 2, .10), trim, .0015)
    fa = r['floor']; mat, files = scanned_floor_material(asset_root, fa)
    x0, x1, y0, y1 = -width / 2, width / 2, front, wall_y
    floor = mesh_object('Scanned oak plank floor', [(x, y, z) for z in [-.035, 0.] for y in [y0, y1] for x in [x0, x1]],
                        [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)], mat)
    bpy.context.view_layer.update()
    f = cfg['physics']['fixture']; table_back = .04 + f['table_dimensions_m'][1] / 2
    return {'windows': placed, 'window_source': 'https://www.blenderkit.com/asset-gallery-detail/7f77e8d9-4cb7-40a4-b20e-6a411c2afd0c/',
            'window_author': 'Flareworks Studio', 'window_license': 'CC0', 'window_scale': 1.0,
            'floor': {'asset': 'https://polyhaven.com/a/' + fa['asset'], 'tile_m': fa['tile_m'], 'pbr_files': files},
            'table_rear_to_wall_clearance_m': inner_rear - table_back,
            'provenance': 'Room shell authored for this scene; floor, furniture and window are registered scans or CC0 models.'}


def surfaces_at(x, y, z_top=2.6):
    """Upward-facing surfaces under (x, y), top first, found by ray casting the evaluated scene."""
    deps = bpy.context.evaluated_depsgraph_get(); hits = []; z = z_top
    for _ in range(40):
        ok, loc, nrm, _i, obj, _m = bpy.context.scene.ray_cast(deps, Vector((x, y, z)), Vector((0, 0, -1)))
        if not ok:
            break
        if nrm.z > .9:
            hits.append((loc.z, obj.name))
        z = loc.z - 2.e-4
    return hits


def append_model(asset_root, asset, prefix):
    path = asset_root / 'polyhaven' / asset / f'{asset}_2k.blend'
    objects, _n, _w = append_asset_objects(path, prefix)
    for o in list(objects):
        if o.type != 'MESH':
            objects.remove(o); bpy.data.objects.remove(o, do_unlink=True); continue
        o['source_asset'] = 'polyhaven_' + asset; o['noninteractive_background_prop'] = True
    resolve_textures([asset_root / 'polyhaven' / asset]); return objects


def furnish(cfg, asset_root):
    """Scanned furniture against the rear wall, outside every solved ball corridor."""
    fa = cfg['appearance']['furniture']; ledger = {}
    cab = fa['cabinet']; objs = append_model(asset_root, cab['asset'], 'Furniture_cabinet_')
    ledger['cabinet'] = {'asset': 'https://polyhaven.com/a/' + cab['asset'], **place_imported_group(objs, cab['center_xy_m'], 0., math.radians(cab['rotation_z_deg']))}
    surf = surfaces_at(*cab['center_xy_m']); ledger['cabinet']['support_surfaces_z_m'] = [round(z, 4) for z, _ in surf]
    for key in ['basket', 'succulent']:
        p = fa[key]; zs = [z for z, name in surfaces_at(*p['center_xy_m']) if name.startswith('Furniture_cabinet_')]
        bottom = zs[p['surface_index']]
        objs = append_model(asset_root, p['asset'], f'Furniture_{key}_')
        ledger[key] = {'asset': 'https://polyhaven.com/a/' + p['asset'], 'resting_on_z_m': bottom,
                       **place_imported_group(objs, p['center_xy_m'], bottom, math.radians(p['rotation_z_deg']))}
        # The shelf board above sits about 20 mm under the next upward surface; keep a visible gap.
        if p['surface_index'] > 0:
            above = zs[p['surface_index'] - 1]; ledger[key]['clearance_to_shelf_above_m'] = above - .02 - ledger[key]['placed_bounds_m'][1][2]
            assert ledger[key]['clearance_to_shelf_above_m'] > .01, (key, ledger[key])
        lo, hi = ledger['cabinet']['placed_bounds_m']; pb = ledger[key]['placed_bounds_m']
        assert all(lo[i] < pb[0][i] and pb[1][i] < hi[i] for i in range(2)), (key, 'outside the cabinet footprint')
    plant = fa['floor_plant']; before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(asset_root / 'polyhaven_models' / plant['asset'] / f"{plant['asset']}_1k.gltf"))
    objs = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in objs if o.type == 'MESH']
    bpy.context.view_layer.update()
    worlds = {o: o.matrix_world.copy() for o in meshes}
    for o in meshes:
        o.parent = None; o.matrix_world = worlds[o]; o['source_asset'] = 'polyhaven_' + plant['asset']; o['noninteractive_background_prop'] = True
    for o in objs:
        if o.type != 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
    ledger['floor_plant'] = {'asset': 'https://polyhaven.com/a/' + plant['asset'], **place_imported_group(meshes, plant['center_xy_m'], 0., math.radians(plant['rotation_z_deg']))}
    r = cfg['appearance']['room']; inner_rear = r['rear_wall_center_y_m'] - r['wall_thickness_m'] / 2 - .025
    inner_left = -r['width_m'] / 2 + r['wall_thickness_m'] / 2 + .025
    for key in ['cabinet', 'floor_plant']:
        pb = ledger[key]['placed_bounds_m']; assert pb[1][1] < inner_rear and pb[0][0] > inner_left, (key, 'touches a wall or skirting')
    return ledger


def unprinted_tape_housing(rect):
    """The scanned tape measure carries a printed maker label; paint that UV patch plain housing black."""
    done = []
    for o in bpy.data.objects:
        if o.get('source_asset') != 'polyhaven_measuring_tape_01' or o.type != 'MESH':
            continue
        for m in o.data.materials:
            if not m or m.name in done or not m.use_nodes:
                continue
            n, l = m.node_tree.nodes, m.node_tree.links
            bs = next((x for x in n if x.bl_idname == 'ShaderNodeBsdfPrincipled'), None)
            link = next((k for k in l if bs and k.to_socket == bs.inputs['Base Color']), None)
            if link is None:
                continue
            uv = n.new('ShaderNodeTexCoord'); sep = n.new('ShaderNodeSeparateXYZ'); l.new(uv.outputs['UV'], sep.inputs['Vector'])
            inside = None
            for axis, lo, hi in [('X', rect[0], rect[2]), ('Y', rect[1], rect[3])]:
                for op, edge in [('GREATER_THAN', lo), ('LESS_THAN', hi)]:
                    c = n.new('ShaderNodeMath'); c.operation = op; c.inputs[1].default_value = edge; l.new(sep.outputs[axis], c.inputs[0])
                    if inside is None:
                        inside = c
                    else:
                        mul = n.new('ShaderNodeMath'); mul.operation = 'MULTIPLY'; l.new(inside.outputs[0], mul.inputs[0]); l.new(c.outputs[0], mul.inputs[1]); inside = mul
            mix = n.new('ShaderNodeMix'); mix.data_type = 'RGBA'; l.new(inside.outputs[0], mix.inputs['Factor'])
            l.new(link.from_socket, mix.inputs['A']); mix.inputs['B'].default_value = tuple(linear(c) for c in [.095, .095, .10]) + (1.,)
            l.new(mix.outputs['Result'], bs.inputs['Base Color']); done.append(m.name)
    return {'materials': done, 'uv_rect': list(rect), 'reason': 'no printed text or maker marks in frame'}


def architecture(cfg, asset_root):
    f = cfg["physics"]["fixture"]; top = f["table_top_z_m"]
    table_asset = asset_table(cfg, asset_root); fa = cfg["appearance"]["frame"]; profile = slot8_profile(f["post_dimensions_m"][0], fa["slot_width_m"])
    cap = material("Black polyamide extrusion end cap", (.035, .035, .037), .55)
    ledger = []
    for i, member in enumerate(construction(cfg)):
        ledger.append(member)
        if member["id"] == "Table":
            continue
        dims = member["dimensions"]
        if member["id"] == "Base":
            o = box(member["id"], member["center"], dims, plywood_face_material(cfg, asset_root), .0009)
            wood_uv(o, 240 + i, cfg["appearance"]["base_board"]["repeat_m"], "Y")
            o.data.materials.append(plywood_edge_material(cfg["appearance"]["base_board"]["ply_pitch_m"]))
            for face in o.data.polygons:
                if abs(face.normal.z) < .5:
                    face.material_index = 1
        elif member["id"] == "Beam":
            # End caps (3 mm) lie inside the collision length, so the visible envelope equals the box.
            body = list(dims); body[0] -= .006
            o = extrusion(member["id"], member["center"], body, aluminium_material("Anodized aluminium beam", "X"), profile)
            for side in [-1, 1]:
                box("Beam end cap", (member["center"][0] + side * (dims[0] / 2 - .0015), member["center"][1], member["center"][2]), (.003, dims[1], dims[2]), cap, .0007)
        else:
            o = extrusion(member["id"], member["center"], dims, aluminium_material("Anodized aluminium upright", "Z"), profile)
        o["collision_box_dimensions_m"] = dims; o["fixed_collision_boundary"] = True
    metal = metal_material("Zinc plated steel hardware", (.62, .63, .63)); cast = aluminium_material("Cast aluminium corner brackets", "Z", .42, cast=True)
    bd = f["base_dimensions_m"]; base_top = top + bd[2]; h = f["post_dimensions_m"][0] / 2; beam_bottom = f["beam_center_z_m"] - f["beam_dimensions_m"][2] / 2; leg = fa["corner_bracket_leg_m"]
    for side in [-1, 1]:
        x = side * f["post_abs_x_m"]
        corner_bracket("Upright to beam bracket", (x - side * h, 0., beam_bottom), (-side, 0., 0.), (0., 0., -1.), (0., 1., 0.), leg, cast)
        for d in [(-side, 0., 0.), (side, 0., 0.)]:
            corner_bracket("Upright foot bracket", (x + d[0] * h, 0., base_top), d, (0., 0., 1.), (0., 1., 0.), leg, cast)
        for sign in [-1, 1]:
            corner_bracket("Upright foot bracket", (x, sign * h, base_top), (0., sign, 0.), (0., 0., 1.), (1., 0., 0.), leg, cast)
    for name, r in cfg["physics"]["ropes"].items():
        x, y, z = r["anchor_m"]
        cylinder(name + " fixed threaded suspension shaft", (x, y, z + .020), .0017, .020, metal, 24)
        cylinder(name + " eye bolt lock nut against beam slot", (x, y, beam_bottom - .0016), .0040, .0032, metal, 6)
        eye = torus(name + " fixed suspension eye", (x, y, z + .005), .0042, .0008, metal); eye.rotation_euler = (math.pi / 2, 0., 0.)
        # Hardware remains when a ball or cord is removed, as in the real fixture.
    room_ledger = room(cfg, asset_root)
    props = bespoke_hourglass(cfg)
    props["removed"] = ["tea cup", "saucer", "linen mat"]
    props["stationery"] = restored_stationery(cfg, asset_root)
    props["stationery"]["tape_label_removed"] = unprinted_tape_housing(cfg["appearance"]["props"]["stationery"]["tape_label_uv_rect"])
    furniture = furnish(cfg, asset_root)
    return {"look_module": Path(__file__).name, "table_dimensions_m": f["table_dimensions_m"], "table_top_m": top,
            "base_dimensions_m": f["base_dimensions_m"], "upright_to_beam_joint_z_m": 1.625,
            "base_board_repeat_m": cfg["appearance"]["base_board"]["repeat_m"], "structure_and_collision_boxes": ledger,
            "scene_units": "m", "table_asset": table_asset, "room": room_ledger, "furniture": furniture, "tabletop_props": props,
            "hardware_fit": {"profile": fa["profile"], "upright_face_abs_y_m": h, "bracket_leg_m": leg,
                             "beam_bottom_z_m": beam_bottom, "beam_end_caps_inside_collision_length": True}}


def lighting(cfg, asset_root):
    """Daylight only: the HDRI sky seen through the two real window openings."""
    sky = cfg["appearance"]["sky"]; r = cfg["appearance"]["room"]
    world = bpy.data.worlds.new("Daylight sky outside the windows"); world.use_nodes = True; bpy.context.scene.world = world
    n, l = world.node_tree.nodes, world.node_tree.links
    env = n.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(str(asset_root / sky["asset"]), check_existing=True)
    tc = n.new("ShaderNodeTexCoord"); mapping = n.new("ShaderNodeMapping"); mapping.inputs["Rotation"].default_value[2] = math.radians(sky["rotation_deg"])
    l.new(tc.outputs["Generated"], mapping.inputs["Vector"]); l.new(mapping.outputs["Vector"], env.inputs["Vector"])
    bg = n.get("Background"); l.new(env.outputs["Color"], bg.inputs["Color"]); bg.inputs["Strength"].default_value = sky["strength"]
    world.cycles.sampling_method = "MANUAL"; world.cycles.sample_map_resolution = 2048
    # A portal sits in each window opening; portals only guide sky sampling and add no light.
    portals = []
    for i, w in enumerate(window_list(r)):
        point, normal, _rot = wall_frame(r, w["wall"]); loc = point(w["center_m"], w["center_z_m"]) + normal * (r["wall_thickness_m"] / 2 - .02)
        name = f"Sky portal in {w['wall']} window {i}"
        data = bpy.data.lights.new(name, "AREA"); data.shape = "RECTANGLE"; data.size = 1.0; data.size_y = 1.18
        data.cycles.is_portal = True
        obj = bpy.data.objects.new(name, data); bpy.context.collection.objects.link(obj); obj.location = loc; look_at(obj, loc + normal)
        portals.append({"name": name, "location_m": list(loc), "inward_normal": list(normal)})
    sun = None
    if sky.get("sun"):
        # Sun disc of a sunny HDRI as a real sun lamp; the HDRI itself is clamped below the disc.
        sp = sky["sun"]; data = bpy.data.lights.new("Sun", "SUN"); data.energy = sp["irradiance_w_m2"]; data.angle = math.radians(.53)
        data.color = sp.get("color", (1., .96, .9))
        obj = bpy.data.objects.new("Sun", data); bpy.context.collection.objects.link(obj)
        az, el = math.radians(sp["azimuth_deg"]), math.radians(sp["elevation_deg"])
        to_sun = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
        obj.rotation_euler = (-to_sun).to_track_quat("-Z", "Y").to_euler(); sun = {"direction_to_sun": list(to_sun), **sp}
    if sky.get("clamp"):
        clamp = n.new("ShaderNodeMix"); clamp.data_type = "RGBA"; clamp.blend_type = "DARKEN"; clamp.inputs["Factor"].default_value = 1.
        l.new(env.outputs["Color"], clamp.inputs["A"]); clamp.inputs["B"].default_value = (sky["clamp"],) * 3 + (1.,)
        l.new(clamp.outputs["Result"], bg.inputs["Color"])
    return {"sky": sky, "portals": portals, "sun": sun, "emitting_lamps": ["Sun"] if sun else []}
