"""Manufactured resin tiles and a furniture-scale, window-lit desk.

Visual geometry only. Collision bodies and solved trajectories are untouched.
"""
from __future__ import annotations
import math
from pathlib import Path
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[4]


def material(name,color,roughness=.4,metallic=0):
    mat=bpy.data.materials.new(name);mat.use_nodes=True
    bs=mat.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value=color
    bs.inputs['Roughness'].default_value=roughness
    bs.inputs['Metallic'].default_value=metallic
    return mat


def box(name,location,dimensions,mat,bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location)
    obj=bpy.context.object;obj.name=name;obj.dimensions=dimensions
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if mat:obj.data.materials.append(mat)
    if bevel:
        m=obj.modifiers.new('Small physical edge radius','BEVEL');m.width=bevel;m.segments=5
        m=obj.modifiers.new('Weighted surface normals','WEIGHTED_NORMAL');m.keep_sharp=True
    return obj


def look_at(obj,target):
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()


def set_socket(node,name,value):
    if name in node.inputs:node.inputs[name].default_value=value


def text(name,body,loc,size,mat,parent=None,rotation=(0,0,0)):
    data=bpy.data.curves.new(name,'FONT');data.body=body;data.size=size
    data.align_x='CENTER';data.align_y='CENTER';data.extrude=.000002
    obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj)
    obj.location=loc;obj.rotation_euler=rotation;data.materials.append(mat)
    if parent:obj.parent=parent
    return obj


def wood_material(cfg):
    mat=material('Furniture veneer - measured physical texture mapping',(.23,.10,.045,1),.33)
    tree=mat.node_tree;n=tree.nodes;l=tree.links;bs=n.get('Principled BSDF')
    coords=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeMapping')
    repeat=cfg['appearance']['room']['wood_repeat_m']
    mapping.inputs['Scale'].default_value=(1/repeat,1/repeat,1/repeat)
    mapping.inputs['Location'].default_value=(.28,.19,0)
    mapping.inputs['Rotation'].default_value[2]=math.pi/2
    l.new(coords.outputs['UV'],mapping.inputs['Vector'])
    asset=cfg['appearance']['room']['wood_asset'];base=ROOT/'assets/polyhaven'/asset
    for suffix,res in [('diff','8k'),('rough','4k'),('nor_gl','4k')]:
        tex=n.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(base/f'{asset}_{suffix}_{res}.jpg'),check_existing=True)
        tex.image.colorspace_settings.name='sRGB' if suffix=='diff' else 'Non-Color'
        l.new(mapping.outputs['Vector'],tex.inputs['Vector'])
        if suffix=='diff':
            finish=n.new('ShaderNodeHueSaturation');finish.inputs['Saturation'].default_value=cfg['appearance']['room']['wood_saturation']
            finish.inputs['Value'].default_value=cfg['appearance']['room']['wood_albedo_scale']
            l.new(tex.outputs['Color'],finish.inputs['Color'])
            if 'wood_tint_linear' in cfg['appearance']['room']:
                tint=n.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1
                tint.inputs[2].default_value=cfg['appearance']['room']['wood_tint_linear']
                l.new(finish.outputs['Color'],tint.inputs[1]);l.new(tint.outputs['Color'],bs.inputs['Base Color'])
            else:l.new(finish.outputs['Color'],bs.inputs['Base Color'])
        elif suffix=='rough':
            ramp=n.new('ShaderNodeMapRange');ramp.inputs['To Min'].default_value=.38;ramp.inputs['To Max'].default_value=.52
            l.new(tex.outputs['Color'],ramp.inputs['Value']);l.new(ramp.outputs['Result'],bs.inputs['Roughness'])
        else:
            normal=n.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.12
            l.new(tex.outputs['Color'],normal.inputs['Color']);l.new(normal.outputs['Normal'],bs.inputs['Normal'])
    set_socket(bs,'Coat Weight',.06);set_socket(bs,'Coat Roughness',.34)
    return mat


def resin_material(cfg):
    if cfg.get('finish')=='daylight_handled_resin':
        from daylight_card_table import daylight_resin
        return daylight_resin(cfg)
    mat=material('Polished ivory filled resin - subdued wear',cfg['color_linear'],cfg['roughness'])
    tree=mat.node_tree;n=tree.nodes;l=tree.links;bs=n.get('Principled BSDF')
    set_socket(bs,'IOR',1.52);set_socket(bs,'Coat Weight',.10);set_socket(bs,'Coat Roughness',.24)
    set_socket(bs,'Subsurface Weight',.025);set_socket(bs,'Subsurface Radius',(1,.55,.32));set_socket(bs,'Subsurface Scale',.0005)
    coords=n.new('ShaderNodeTexCoord');info=n.new('ShaderNodeObjectInfo')
    fine=n.new('ShaderNodeTexNoise');fine.noise_dimensions='4D';fine.inputs['Scale'].default_value=6000;fine.inputs['Detail'].default_value=2
    l.new(coords.outputs['Object'],fine.inputs['Vector']);l.new(info.outputs['Random'],fine.inputs['W'])
    broad=n.new('ShaderNodeTexNoise');broad.noise_dimensions='4D';broad.inputs['Scale'].default_value=160;broad.inputs['Detail'].default_value=2
    l.new(coords.outputs['Object'],broad.inputs['Vector']);l.new(info.outputs['Random'],broad.inputs['W'])
    tone=n.new('ShaderNodeMapRange');tone.inputs['To Min'].default_value=.965;tone.inputs['To Max'].default_value=1.012
    l.new(broad.outputs['Fac'],tone.inputs['Value'])
    color=n.new('ShaderNodeMixRGB');color.blend_type='MULTIPLY';color.inputs[0].default_value=1;color.inputs[1].default_value=cfg['color_linear']
    l.new(tone.outputs['Result'],color.inputs[2]);l.new(color.outputs['Color'],bs.inputs['Base Color'])
    rough=n.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.18;rough.inputs['To Max'].default_value=.26
    l.new(broad.outputs['Fac'],rough.inputs['Value'])
    stretch=n.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY';stretch.inputs[1].default_value=(300,18000,180)
    l.new(coords.outputs['Object'],stretch.inputs[0])
    scratches=n.new('ShaderNodeTexNoise');scratches.noise_dimensions='4D';scratches.inputs['Scale'].default_value=1;scratches.inputs['Detail'].default_value=2
    l.new(stretch.outputs['Vector'],scratches.inputs['Vector']);l.new(info.outputs['Random'],scratches.inputs['W'])
    threshold=n.new('ShaderNodeMapRange');threshold.clamp=True;threshold.inputs['From Min'].default_value=.73;threshold.inputs['From Max'].default_value=.81
    threshold.inputs['To Min'].default_value=0;threshold.inputs['To Max'].default_value=.20
    l.new(scratches.outputs['Fac'],threshold.inputs['Value'])
    add=n.new('ShaderNodeMath');add.operation='ADD';l.new(rough.outputs['Result'],add.inputs[0]);l.new(threshold.outputs['Result'],add.inputs[1]);l.new(add.outputs[0],bs.inputs['Roughness'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.10;bump.inputs['Distance'].default_value=.000002
    l.new(fine.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],bs.inputs['Normal'])
    return mat


def rounded_tile_body(name,thick,width,height,mat,corner_radius,edge_radius):
    # Rounded corners in the broad YZ face, with a much smaller X rim radius.
    # This avoids using a large all-axis bevel that would lift the visible support edge.
    w,h=width/2,height/2;r=corner_radius;outline=[]
    for cy,cz,start in [(w-r,h-r,0),(-w+r,h-r,90),(-w+r,-h+r,180),(w-r,-h+r,270)]:
        for j in range(9):
            a=math.radians(start+j*90/8);outline.append((cy+r*math.cos(a),cz+r*math.sin(a)))
    n=len(outline);verts=[(x,y,z) for x in [-thick/2,thick/2] for y,z in outline]
    faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]
    for i in range(n):faces.append((i,(i+1)%n,(i+1)%n+n,i+n))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj);mesh.materials.append(mat)
    for face in mesh.polygons:face.use_smooth=True
    bevel=obj.modifiers.new('Small resin face rim','BEVEL');bevel.width=edge_radius;bevel.segments=4;bevel.limit_method='ANGLE'
    obj.modifiers.new('Broad resin face normals','WEIGHTED_NORMAL')
    return obj


def apply_modifier(obj,modifier):
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def subtract(body,cutter):
    m=body.modifiers.new('Actual machined recess','BOOLEAN');m.operation='DIFFERENCE';m.solver='EXACT';m.object=cutter
    apply_modifier(body,m);mesh=cutter.data;bpy.data.objects.remove(cutter,do_unlink=True)
    if mesh.users==0:bpy.data.meshes.remove(mesh)


def pip_bowl(name,side,face_x,y,z,radius,mat,parent):
    # Shallow concave black inlay: a 0.24 mm dimple with a resin lip.
    rings,segments=5,40
    vertices=[(side*(face_x-.00024),y,z)];faces=[]
    for ring in range(1,rings+1):
        r=radius*ring/rings
        depth=.00005+.00019*(1-(r/radius)**2)
        for j in range(segments):
            a=2*math.pi*j/segments
            vertices.append((side*(face_x-depth),y+r*math.cos(a),z+r*math.sin(a)))
    for j in range(segments):faces.append((0,1+j,1+(j+1)%segments))
    for ring in range(rings-1):
        a=1+ring*segments;b=a+segments
        for j in range(segments):faces.append((a+j,b+j,b+(j+1)%segments,a+(j+1)%segments))
    if side<0:faces=[tuple(reversed(f)) for f in faces]
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj);obj.parent=parent;mesh.materials.append(mat)
    for poly in mesh.polygons:poly.use_smooth=True


def sketchfab_domino(index,cfg,mats):
    """Use the measured, normalized imported tile, including its original pips."""
    asset=ROOT/cfg['appearance']['domino']['asset_file']
    names=[f'Sketchfab_D{i+1:02}_mesh' for i in range(5)]
    if not all(name in bpy.data.meshes for name in names):
        with bpy.data.libraries.load(str(asset),link=False) as (source,target):
            assert all(name in source.meshes for name in names)
            target.meshes=list(names)
        for mesh in target.meshes:
            mesh.materials[0]=mats['resin'];mesh.materials[1]=mats['pip']
    anchor=bpy.data.objects.new(f'D{index+1:02}',None);bpy.context.collection.objects.link(anchor)
    mesh=bpy.data.meshes[names[index]].copy()
    obj=bpy.data.objects.new(f'D{index+1:02}_Sketchfab_resin_and_inlays',mesh);bpy.context.collection.objects.link(obj);obj.parent=anchor
    obj['source_asset']='Dominoes by Render at Night / Sketchfab / CC BY 4.0'
    obj['normalized_dimensions_m']=[.008,.025,.050]
    width=cfg['physics']['domino_width']
    text(f'D{index+1:02}_identity',f'D{index+1:02}',(0,-width/2-.000006,-.0208),.0022,mats['ink'],anchor,(math.pi/2,0,0))
    return anchor


def domino(index,cfg,mats):
    if cfg['appearance']['domino'].get('asset_kind')=='sketchfab':return sketchfab_domino(index,cfg,mats)
    ph=cfg['physics'];ap=cfg['appearance']['domino'];thick,width,height=(ph['domino_'+k] for k in ['thickness','width','height'])
    anchor=bpy.data.objects.new(f'D{index+1:02}',None);bpy.context.collection.objects.link(anchor)
    body=rounded_tile_body(f'D{index+1:02}_resin',thick,width,height,mats['resin'],ap['face_corner_radius_m'],ap['bevel_m']);body.parent=anchor
    for modifier in list(body.modifiers):apply_modifier(body,modifier)
    patterns={1:[(0,0)],2:[(-1,1),(1,-1)],3:[(-1,1),(0,0),(1,-1)],4:[(-1,1),(1,1),(-1,-1),(1,-1)],
              5:[(-1,1),(1,1),(0,0),(-1,-1),(1,-1)],6:[(-1,1),(1,1),(-1,0),(1,0),(-1,-1),(1,-1)]}
    radius=ap['pip_radius_m']
    for side in [-1,1]:
        for half,number in [(1,index+1),(-1,6-index)]:
            for j,(u,v) in enumerate(patterns[number]):
                y,z=u*.0058,half*.0119+v*.0053
                bpy.ops.mesh.primitive_cylinder_add(vertices=40,radius=radius+.00004,depth=.0007,
                    location=(side*(thick/2+.00007),y,z),rotation=(0,math.pi/2,0))
                subtract(body,bpy.context.object)
                pip_bowl(f'D{index+1:02}_recessed_pip_{side}_{half}_{j}',side,thick/2,y,z,radius-.000025,mats['pip'],anchor)
        cutter=box('Engraving cutter',(side*(thick/2+.00020),0,0),(.00065,.020,.00027),None,.00006)
        for mod in list(cutter.modifiers):apply_modifier(cutter,mod)
        subtract(body,cutter)
    bevel=body.modifiers.new('Soft inlay lips','BEVEL');bevel.width=.000045;bevel.segments=3;bevel.limit_method='ANGLE'
    normal=body.modifiers.new('Broad manufactured face normals','WEIGHTED_NORMAL');normal.keep_sharp=True;normal.weight=50
    for poly in body.data.polygons:poly.use_smooth=True
    text(f'D{index+1:02}_identity',f'D{index+1:02}',(0,-width/2-.000006,-.0208),.0022,mats['ink'],anchor,(math.pi/2,0,0))
    return anchor


def book(z):
    # Original asset coordinates are metres: 237 x 163 x 23 mm, no miniaturizing.
    path=ROOT/'assets/polyhaven/book_encyclopedia_set_01/book_encyclopedia_set_01_2k.blend'
    with bpy.data.libraries.load(str(path),link=False) as (source,target):
        target.objects=['book_encyclopedia_set_01_book03']
    obj=target.objects[0];bpy.context.collection.objects.link(obj)
    obj.name='Used leather-bound encyclopedia - 237 mm tall original'
    corners=[Vector(c) for c in obj.bound_box]
    center=(Vector([min(c[i] for c in corners) for i in range(3)])+Vector([max(c[i] for c in corners) for i in range(3)]))/2
    for vertex in obj.data.vertices:vertex.co-=center
    obj.location=(-.100,.170,z+.0227971263/2)
    obj.rotation_euler=(0,math.pi/2,-.15)
    for mat in obj.data.materials:
        if not mat or not mat.use_nodes:continue
        for node in mat.node_tree.nodes:
            if node.type=='TEX_IMAGE' and node.image:
                node.image.filepath=str(path.parent/'textures'/Path(node.image.filepath).name)
                node.image.reload()
    return obj


def cylinder(name,radius,depth,location,mat,parent=None,vertices=48,bevel=0):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=location,rotation=(0,math.pi/2,0))
    obj=bpy.context.object;obj.name=name;obj.data.materials.append(mat)
    if parent:obj.parent=parent
    if bevel:
        m=obj.modifiers.new('Small rounded edge','BEVEL');m.width=bevel;m.segments=3
        obj.modifiers.new('Surface normals','WEIGHTED_NORMAL')
    return obj


def pencil(z):
    anchor=bpy.data.objects.new('Sharpened 174 mm HB pencil',None);bpy.context.collection.objects.link(anchor)
    anchor.location=(.040,-.100,z+.00335);anchor.rotation_euler[2]=-.045;anchor.rotation_euler[1]=-.00148
    lacquer=material('Ochre pencil lacquer',(.39,.23,.063,1),.3)
    cedar=material('Exposed sharpened cedar',(.53,.31,.13,1),.62)
    lead=material('Graphite pencil point',(.022,.024,.022,1),.35,.18)
    metal=material('Satin nickel pencil ferrule',(.43,.44,.41,1),.28,.85)
    eraser=material('Handled salmon eraser',(.28,.105,.082,1),.86)
    cylinder('Six-sided lacquered pencil barrel',.00325,.131,(-.0015,0,0),lacquer,anchor,6,.00008)
    bpy.ops.mesh.primitive_cone_add(vertices=48,radius1=.00322,radius2=.00015,depth=.018,location=(-.076,0,0),rotation=(0,-math.pi/2,0))
    obj=bpy.context.object;obj.name='Sharpened exposed cedar';obj.parent=anchor;obj.data.materials.append(cedar)
    bpy.ops.mesh.primitive_cone_add(vertices=32,radius1=.00075,radius2=.000035,depth=.0048,location=(-.084,0,0),rotation=(0,-math.pi/2,0))
    obj=bpy.context.object;obj.name='Exposed graphite tip';obj.parent=anchor;obj.data.materials.append(lead)
    cylinder('Nickel ferrule sleeve',.00337,.013,(.0705,0,0),metal,anchor,48,.00012)
    for i in range(7):cylinder(f'Ferrule crimp {i}',.00346,.00026,(.065+i*.0017,0,0),metal,anchor)
    cylinder('Soft eraser end',.00324,.009,(.0815,0,0),eraser,anchor,48,.0008)
    text('Small pencil grade marking','HB',(.038,-.00283,.0006),.0014,lead,anchor,(math.pi/2,0,0))
    return anchor


def ceramic_cup(z):
    mat=material('Thin glazed grey ceramic',(.24,.29,.27,1),.24)
    profile=[(.024,0),(.029,.002),(.034,.009),(.037,.067),(.0368,.073),(.0359,.0745),(.0343,.0742),(.0338,.071),(.031,.010),(.0,.009)]
    segments=72;verts=[];faces=[]
    for radius,h in profile:
        for i in range(segments):
            a=i*2*math.pi/segments;verts.append((radius*math.cos(a),radius*math.sin(a),h))
    for k in range(len(profile)-1):
        for i in range(segments):faces.append((k*segments+i,k*segments+(i+1)%segments,(k+1)*segments+(i+1)%segments,(k+1)*segments+i))
    mesh=bpy.data.meshes.new('Hollow ceramic mug mesh');mesh.from_pydata(verts,[],faces);mesh.materials.append(mat)
    obj=bpy.data.objects.new('Hollow mug with actual rim',mesh);bpy.context.collection.objects.link(obj);obj.location=(.235,.205,z)
    for p in mesh.polygons:p.use_smooth=True
    bpy.ops.mesh.primitive_torus_add(major_radius=.020,minor_radius=.004,major_segments=48,minor_segments=12,location=(.273,.205,z+.042),rotation=(math.pi/2,0,0))
    handle=bpy.context.object;handle.name='Ceramic mug handle';handle.data.materials.append(mat)
    for p in handle.data.polygons:p.use_smooth=True


def desk_environment(cfg):
    if cfg['appearance']['room'].get('environment_kind')=='home_card_table':
        from card_table_environment import build_card_table
        env=build_card_table(cfg)
        if cfg['appearance']['room'].get('surface_revision')=='natural':
            from natural_card_table import enhance_environment
            env=enhance_environment(cfg,env)
        if cfg['appearance']['room'].get('domestic_revision')=='daylight_home':
            from daylight_card_table import enhance_environment as domestic_environment
            env=domestic_environment(cfg,env)
        from playing_card_finish import apply_card_finish
        env=apply_card_finish(cfg,env)
        from mahjong_table_realism import enhance_environment as mahjong_environment
        return mahjong_environment(cfg,env)
    z=cfg['physics']['floor_z'];wood=wood_material(cfg)
    desk=box('1200 x 650 mm satin varnished home desk',(0,.03,z-.014),(1.2,.65,.028),wood,.002)
    uv=desk.data.uv_layers.active or desk.data.uv_layers.new(name='World metre UV')
    for poly in desk.data.polygons:
        for li in poly.loop_indices:
            co=desk.data.vertices[desk.data.loops[li].vertex_index].co;uv.data[li].uv=(co.x+.6,co.y+.325)
    book(z);pencil(z);ceramic_cup(z)
    wall=material('Neutral painted home study wall',(.39,.40,.37,1),.88)
    box('Shared back wall',(0,.65,1.35),(3,.08,2.7),wall)
    box('Shared side wall',(-1.15,0,1.35),(.08,1.6,2.7),wall)
    flooring=material('Out of frame home floor',(.15,.115,.08,1),.6)
    box('Continuous room floor',(0,0,-.025),(3,3,.05),flooring)
    for x in [-.52,.52]:
        for y in [-.24,.30]:box('Desk support leg',(x,y,(z-.028)/2),(.045,.045,z-.028),wood,.001)
    return {'desk_dimensions_m':[1.2,.65,.028],'desk_surface_z_m':z,'wood_texture_repeat_m':cfg['appearance']['room']['wood_repeat_m'],
            'book_dimensions_m':[.237418175,.163062319,.0227971263],'pencil_length_m':.174,'cup_height_m':.0745,
            'visual_geometry_does_not_modify_collision_proxies':True}


def setup_lighting(cfg):
    sc=bpy.context.scene;ap=cfg['appearance'];window=ap['window']
    world=bpy.data.worlds.new('Captured indoor daylight reflections');world.use_nodes=True;sc.world=world
    n=world.node_tree.nodes;l=world.node_tree.links;bg=n.get('Background')
    env=n.new('ShaderNodeTexEnvironment');env.image=bpy.data.images.load(str(ROOT/'assets/polyhaven/brown_photostudio_05/brown_photostudio_05_2k.hdr'),check_existing=True)
    coords=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeMapping');mapping.inputs['Rotation'].default_value[2]=math.radians(115)
    l.new(coords.outputs['Generated'],mapping.inputs['Vector']);l.new(mapping.outputs['Vector'],env.inputs['Vector']);l.new(env.outputs['Color'],bg.inputs['Color'])
    bg.inputs['Strength'].default_value=ap['room']['environment_strength']
    bpy.ops.object.light_add(type='AREA',location=window['location']);light=bpy.context.object;light.name='Single soft rectangular daylight window'
    light.data.energy=window['power_w'];light.data.shape='RECTANGLE';light.data.size=window['size_m'];light.data.size_y=window['size_y_m'];light.data.color=window['color']
    look_at(light,(0,0,.76))
    # A dark room side outside the camera gives a real reflected tonal gradient.
    dark=material('Out of frame dark room side',ap['room'].get('reflection_wall_color_linear',(.025,.027,.026,1)),.95)
    box('Off-camera room reflection surface',((1.30 if ap['room'].get('surface_revision')=='natural' else .65),.05,1.18),(.04,1.2,1.0),dark)
    sc.view_settings.exposure=ap['room']['exposure_ev']
