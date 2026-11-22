"""Furniture-scale home card table, visual-only environment for a frozen solve."""
from __future__ import annotations
import math, random
from pathlib import Path
import bpy
from look_domino_chain import material, box, wood_material, set_socket
ROOT=Path(__file__).resolve().parents[4]

def mesh_object(name,verts,faces,mat=None):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    if mat:mesh.materials.append(mat)
    return obj

def rounded_outline(width,depth,radius,segments=12):
    points=[]
    for cx,cy,start in [(width/2-radius,depth/2-radius,0),(-width/2+radius,depth/2-radius,90),
                         (-width/2+radius,-depth/2+radius,180),(width/2-radius,-depth/2+radius,270)]:
        for j in range(segments+1):
            a=math.radians(start+j*90/segments);points.append((cx+radius*math.cos(a),cy+radius*math.sin(a)))
    return points

def metre_uv(obj):
    uv=obj.data.uv_layers.active or obj.data.uv_layers.new(name='Actual metre coordinates')
    for poly in obj.data.polygons:
        normal=poly.normal;axis=max(range(3),key=lambda i:abs(normal[i]))
        axes={0:(1,2),1:(0,2),2:(0,1)}[axis]
        for li in poly.loop_indices:
            co=obj.data.vertices[obj.data.loops[li].vertex_index].co
            uv.data[li].uv=(co[axes[0]],co[axes[1]])

def rounded_slab(name,width,depth,height,radius,loc,mat,bevel=.0005):
    outline=rounded_outline(width,depth,radius);n=len(outline)
    verts=[(x,y,z) for z in [-height/2,height/2] for x,y in outline]
    faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]
    faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    obj=mesh_object(name,verts,faces,mat);obj.location=loc;metre_uv(obj)
    if bevel:
        mod=obj.modifiers.new('Furniture edge radius','BEVEL');mod.width=bevel;mod.segments=4
        obj.modifiers.new('Furniture surface normals','WEIGHTED_NORMAL')
    return obj

def table_rail(cfg,wood):
    ap=cfg['appearance']['card_table'];outer=ap['outer_dimensions_m'];inner=ap['felt_dimensions_m']
    out=rounded_outline(outer[0],outer[1],ap['outer_corner_radius_m'])
    inn=rounded_outline(inner[0],inner[1],ap['inner_corner_radius_m'])
    n=len(out);z=cfg['physics']['floor_z'];top=z+.004;bottom=z-.029
    verts=[(x,y,h) for h in [bottom,top] for outline in [out,inn] for x,y in outline]
    faces=[]
    for i in range(n):
        j=(i+1)%n
        faces.extend([(2*n+i,2*n+j,3*n+j,3*n+i),(i,n+i,n+j,j),(i,j,2*n+j,2*n+i),
                      (n+j,n+i,3*n+i,3*n+j)])
    obj=mesh_object('Solid wooden perimeter rail - real inset opening',verts,faces,wood)
    obj.location=(0,ap['center_y_m'],0);metre_uv(obj)
    mod=obj.modifiers.new('Handled rail edge radius 2 mm','BEVEL');mod.width=.002;mod.segments=5
    obj.modifiers.new('Broad rail surface normals','WEIGHTED_NORMAL')
    return obj

def baize_material(cfg):
    color=cfg['appearance']['card_table']['felt_color_linear']
    mat=material('Brushed wool baize - fine fibres and restrained wear',color,.86)
    n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF')
    set_socket(bs,'IOR',1.46);set_socket(bs,'Sheen Weight',.08);set_socket(bs,'Sheen Roughness',.72);set_socket(bs,'Sheen Tint',(.12,.32,.19,1))
    coords=n.new('ShaderNodeTexCoord')
    # All object coordinates are metres; neither a giant weave nor coarse gravel.
    broad=n.new('ShaderNodeTexNoise');broad.inputs['Scale'].default_value=43;broad.inputs['Detail'].default_value=2
    l.new(coords.outputs['Object'],broad.inputs['Vector'])
    tone=n.new('ShaderNodeMapRange');tone.inputs['To Min'].default_value=.90;tone.inputs['To Max'].default_value=1.06
    l.new(broad.outputs['Fac'],tone.inputs['Value'])
    col=n.new('ShaderNodeMixRGB');col.blend_type='MULTIPLY';col.inputs[0].default_value=1;col.inputs[1].default_value=color
    l.new(tone.outputs['Result'],col.inputs[2]);l.new(col.outputs['Color'],bs.inputs['Base Color'])
    stretch=n.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY';stretch.inputs[1].default_value=(2600,7000,5000)
    l.new(coords.outputs['Object'],stretch.inputs[0])
    fibres=n.new('ShaderNodeTexNoise');fibres.inputs['Scale'].default_value=1;fibres.inputs['Detail'].default_value=2;fibres.inputs['Roughness'].default_value=.7
    l.new(stretch.outputs['Vector'],fibres.inputs['Vector'])
    bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000035;bump.inputs['Strength'].default_value=.28
    l.new(fibres.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],bs.inputs['Normal'])
    rough=n.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.80;rough.inputs['To Max'].default_value=.94
    l.new(fibres.outputs['Fac'],rough.inputs['Value']);l.new(rough.outputs['Result'],bs.inputs['Roughness'])
    mapping=n.new('ShaderNodeMapping');mapping.inputs['Scale'].default_value=(5,5,5)
    mapping.inputs['Location'].default_value=(.127,.293,0);l.new(coords.outputs['UV'],mapping.inputs['Vector'])
    base=ROOT/'assets/ambientcg/Fabric034';textures={}
    for channel,filename in [('color','Fabric034_SQ_Color.jpg'),('normal','Fabric034_SQ_NormalDX.jpg'),('rough','Fabric034_SQ_Roughness.jpg')]:
        tex=n.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(base/filename),check_existing=True)
        tex.image.colorspace_settings.name='sRGB' if channel=='color' else 'Non-Color'
        l.new(mapping.outputs['Vector'],tex.inputs['Vector']);textures[channel]=tex
    gray=n.new('ShaderNodeRGBToBW');l.new(textures['color'].outputs['Color'],gray.inputs['Color'])
    dye=n.new('ShaderNodeMapRange');dye.clamp=True;dye.inputs['From Min'].default_value=.15;dye.inputs['From Max'].default_value=.65
    dye.inputs['To Min'].default_value=.77;dye.inputs['To Max'].default_value=1.2;l.new(gray.outputs[0],dye.inputs['Value'])
    tone_photo=n.new('ShaderNodeMath');tone_photo.operation='MULTIPLY';l.new(tone.outputs['Result'],tone_photo.inputs[0]);l.new(dye.outputs['Result'],tone_photo.inputs[1]);l.new(tone_photo.outputs[0],col.inputs[2])
    l.new(textures['rough'].outputs['Color'],rough.inputs['Value'])
    split=n.new('ShaderNodeSeparateColor');combine=n.new('ShaderNodeCombineColor')
    l.new(textures['normal'].outputs['Color'],split.inputs['Color'])
    invert=n.new('ShaderNodeMath');invert.operation='SUBTRACT';invert.inputs[0].default_value=1;l.new(split.outputs['Green'],invert.inputs[1])
    l.new(split.outputs['Red'],combine.inputs['Red']);l.new(invert.outputs[0],combine.inputs['Green']);l.new(split.outputs['Blue'],combine.inputs['Blue'])
    normal=n.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.30
    l.new(combine.outputs['Color'],normal.inputs['Color']);l.new(normal.outputs['Normal'],bump.inputs['Normal'])
    return mat

def printed_paper(name,filename):
    mat=material(name,(.8,.78,.72,1),.43)
    n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF')
    set_socket(bs,'IOR',1.47);set_socket(bs,'Coat Weight',.035);set_socket(bs,'Coat Roughness',.4)
    tex=n.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(ROOT/'assets/public_domain/byron_knoll_cards'/filename),check_existing=True)
    tex.interpolation='Linear'
    tint=n.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1;tint.inputs[2].default_value=(.86,.845,.80,1)
    l.new(tex.outputs['Color'],tint.inputs[1]);l.new(tint.outputs['Color'],bs.inputs['Base Color'])
    coord=n.new('ShaderNodeTexCoord');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=16500
    l.new(coord.outputs['Object'],noise.inputs['Vector'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.09;bump.inputs['Distance'].default_value=.000003
    l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],bs.inputs['Normal'])
    return mat

def card(name,loc,angle,top,paper,curl=.00018):
    width,depth,thick=.063,.088,.00028
    outline=rounded_outline(width,depth,.0025,segments=8);n=len(outline)
    def height(x,y):
        return .000012+curl*(y/(depth/2))**4+.000045*(x/(width/2))**4
    verts=[(0,0,height(0,0)),(0,0,height(0,0)+thick)]
    for layer in [0,1]:
        verts += [(x,y,height(x,y)+layer*thick) for x,y in outline]
    faces=[];indices=[]
    for i in range(n):
        j=(i+1)%n
        faces.append((1,2+n+i,2+n+j));indices.append(0)
        faces.append((0,2+j,2+i));indices.append(1)
        faces.append((2+i,2+j,2+n+j,2+n+i));indices.append(1)
    obj=mesh_object(name,verts,faces);obj.location=loc;obj.rotation_euler[2]=angle
    obj.data.materials.append(top);obj.data.materials.append(paper)
    uv=obj.data.uv_layers.new(name='Entire printed card face')
    for poly,index in zip(obj.data.polygons,indices):
        poly.material_index=index;poly.use_smooth=index==0
        for li in poly.loop_indices:
            co=obj.data.vertices[obj.data.loops[li].vertex_index].co;uv.data[li].uv=(co.x/width+.5,co.y/depth+.5)
    obj['actual_dimensions_m']=[width,depth,thick];obj['static_decorative_prop']=True
    return obj

def playing_cards(z):
    paper=material('Exposed used paper card edges',(.72,.71,.66,1),.65)
    hearts=printed_paper('Printed King of Hearts - Byron Knoll / Public Domain','KH.png')
    spades=printed_paper('Printed Eight of Spades - Byron Knoll / Public Domain','8S.png')
    back=printed_paper('Original navy geometric card back','back_original.png')
    card('Loosely dealt 8 of spades',(-.089,.093,z),-.19,spades,paper,.00016)
    card('Loosely dealt King of hearts',(-.057,.119,z+.00040),.16,hearts,paper,.00024)
    rng=random.Random(6100)
    anchor=bpy.data.objects.new('Remaining deck - 50 separate 0.28 mm paper cards',None);bpy.context.collection.objects.link(anchor)
    anchor.location=(.080,.160,z);anchor.rotation_euler[2]=-.18
    for i in range(50):
        c=card(f'Deck card {i+1:02}',(rng.uniform(-.00013,.00013),rng.uniform(-.00014,.00014),i*.000282),
               rng.uniform(-.0025,.0025),back,paper,.000008);c.parent=anchor
    return {'playing_card_dimensions_m':[.063,.088,.00028],'deck_card_count':50,'deck_height_m':.0141,
            'card_art_source':'Byron Knoll / Public Domain','card_back':'Original procedural geometric design'}

def lathe(name,profile,loc,mat,segments=96):
    verts=[(r*math.cos(2*math.pi*i/segments),r*math.sin(2*math.pi*i/segments),h)
           for r,h in profile for i in range(segments)]
    faces=[(k*segments+i,k*segments+(i+1)%segments,(k+1)*segments+(i+1)%segments,(k+1)*segments+i)
           for k in range(len(profile)-1) for i in range(segments)]
    obj=mesh_object(name,verts,faces,mat);obj.location=loc
    for p in obj.data.polygons:p.use_smooth=True
    return obj

def tea_cup(z):
    # Small handleless tea cup: a believable home-game prop clear of the interaction.
    ceramic=material('Warm speckled stoneware tea cup',(.39,.34,.255,1),.25)
    n=ceramic.node_tree.nodes;l=ceramic.node_tree.links;bs=n.get('Principled BSDF')
    set_socket(bs,'Coat Weight',.24);set_socket(bs,'Coat Roughness',.17)
    coord=n.new('ShaderNodeTexCoord');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=5600;noise.inputs['Detail'].default_value=1
    l.new(coord.outputs['Object'],noise.inputs['Vector'])
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=.68;ramp.color_ramp.elements[0].color=(.39,.34,.255,1)
    ramp.color_ramp.elements[1].position=.79;ramp.color_ramp.elements[1].color=(.11,.085,.055,1)
    l.new(noise.outputs['Fac'],ramp.inputs['Fac']);l.new(ramp.outputs['Color'],bs.inputs['Base Color'])
    x,y=-.006,.230
    saucer_profile=[(0,0),(.021,0),(.023,.0008),(.033,.0015),(.044,.0035),(.045,.0055),(.044,.0060),
                    (.038,.0048),(.026,.0035),(.016,.003),(0,.003)]
    lathe('Stoneware tea saucer - 90 mm diameter',saucer_profile,(x,y,z+.00001),ceramic)
    profile=[(.015,0),(.020,0),(.021,.003),(.026,.009),(.032,.042),(.0318,.049),(.0309,.050),
             (.0297,.0498),(.0295,.047),(.0255,.013),(.018,.006),(0,.006)]
    lathe('Hollow tea cup - fine rolled ceramic rim',profile,(x,y,z+.003),ceramic)
    tea=material('Dark amber tea - real level surface',(.065,.026,.006,1),.13)
    bs=tea.node_tree.nodes.get('Principled BSDF');set_socket(bs,'IOR',1.333);set_socket(bs,'Transmission Weight',.38)
    lathe('Tea surface and shallow meniscus',[(.0293,.0006),(.0292,.00025),(.02885,0),(0,0)],(x,y,z+.047),tea)
    return {'tea_cup_height_m':.050,'tea_saucer_diameter_m':.090,'tea_cup_center_m':[x,y,z+.003]}

def build_card_table(cfg):
    ap=cfg['appearance']['card_table'];z=cfg['physics']['floor_z'];cy=ap['center_y_m']
    wood=wood_material(cfg);wood.name='Satin oak card table rail - physical grain and handled edge'
    base=rounded_slab('Card table solid timber foundation',.900,.900,.025,.045,(0,cy,z-.0175),wood,.002)
    table_rail(cfg,wood)
    felt=baize_material(cfg)
    rounded_slab('Inset baize - top coincides with solved support plane',.820,.820,.003,.022,(0,cy,z-.0015),felt,.00030)
    # Fine dark binding around the recess, with actual small diameter.
    binding=material('Inset dark green cloth binding',(.009,.021,.014,1),.78)
    curve=bpy.data.curves.new('Continuous fine baize edge binding','CURVE');curve.dimensions='3D';curve.bevel_depth=.00055;curve.bevel_resolution=3
    pts=rounded_outline(.821,.821,.0225,20);spline=curve.splines.new('POLY');spline.points.add(len(pts)-1)
    for p,(x,y) in zip(spline.points,pts):p.co=(x,y+cy,z-.00025,1)
    spline.use_cyclic_u=True
    obj=bpy.data.objects.new('Cloth binding seated inside timber rail',curve);bpy.context.collection.objects.link(obj);curve.materials.append(binding)
    apron=material('Dark oak table apron',(.065,.030,.014,1),.47)
    rounded_slab('Table apron',.85,.85,.075,.032,(0,cy,z-.066),apron,.002)
    for x in [-.36,.36]:
        for y in [cy-.36,cy+.36]:
            leg=box('Card table tapered timber support',(x,y,(z-.103)/2),(.041,.041,z-.103),wood,.002);metre_uv(leg)
    props={**playing_cards(z),**tea_cup(z)}
    wall=material('Soft warm home dining room plaster',(.42,.405,.36,1),.9)
    box('Home dining room back wall',(0,1.25,1.35),(3,.08,2.7),wall)
    box('Home dining room side wall',(-1.25,.3,1.35),(.08,2.6,2.7),wall)
    floor=material('Home floor outside close shot',(.12,.075,.040,1),.62)
    box('Continuous home floor',(0,.2,-.025),(3,3,.05),floor)
    return {'environment_kind':'home_card_table','table_dimensions_m':[.9,.9,.033],'felt_dimensions_m':[.82,.82,.003],
            'table_center_y_m':cy,'felt_surface_z_m':z,'raised_rail_height_above_felt_m':.004,
            'felt_fibre_bump_distance_m':.000035,'felt_asset':'ambientCG Fabric034 official 2048-square PBR maps','felt_selected_repeat_m':.20,'felt_repeat_is_measured':False,'wood_texture_repeat_m':cfg['appearance']['room']['wood_repeat_m'],
            **props,'visual_geometry_does_not_modify_collision_proxies':True,
            'contact_material_note':'Baize is visual shading only. Accepted support friction and solved motion are unchanged; no new measured cloth friction calibration is claimed.'}

