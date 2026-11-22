"""Daylit living room by a courtyard: copper diecast car, molded toy ramp with a flat runout, three PVC balls.

room(), car(), ball() and lighting() build the scene in layers: the authored full-scale living room and SI
toy meshes, the photographic household layer, the molded toy ramp with its horizontal runout and thin
floor transition, the recessed double-glazed casement window with clearance-correct linen drapes, and the
CC BY Car Concept diecast with photographed materials and a real courtyard beyond clear glazing.
Helpers suffixed with a layer name (room_realism, lighting_realism, ...) are the earlier layers the final
functions build on. All solver roots are unchanged by appearance.

honest_daylight(), plaster_walls() and sofa_textiles() are the finishing pass, applied after the scene is
built (refine_template() applies them to an opened packed template): window-only daylight with no hidden
helper lamps, scanned beige_wall_001 plaster on walls and ceiling, and scanned rough_linen on the sofa and
pillows.
"""

import math
import os
import random
import sys as _scene_sys
from pathlib import Path as _ScenePath, Path

import bpy
from mathutils import Vector, Matrix
from pcve_assets import ASSETS, asset
from scene_config import profile, surface
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))


def mat(name,color,rough=.4,metal=0.,coat=0.,micro=.0):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    n=m.node_tree.nodes;l=m.node_tree.links;s=n.get('Principled BSDF')
    s.inputs['Base Color'].default_value=(*color,1);s.inputs['Roughness'].default_value=rough
    s.inputs['Metallic'].default_value=metal;s.inputs['Coat Weight'].default_value=coat
    s.inputs['Coat Roughness'].default_value=.22
    if micro:
        noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=1500.;noise.inputs['Detail'].default_value=2.
        bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.15;bump.inputs['Distance'].default_value=micro
        l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],s.inputs['Normal'])
        remap=n.new('ShaderNodeMapRange');remap.inputs['From Min'].default_value=0.;remap.inputs['From Max'].default_value=1.
        remap.inputs['To Min'].default_value=rough-.04;remap.inputs['To Max'].default_value=rough+.06
        l.new(noise.outputs['Fac'],remap.inputs['Value']);l.new(remap.outputs[0],s.inputs['Roughness'])
    return m


def assign(obj,material):
    obj.data.materials.append(material);return obj


def mesh(name,verts,faces,material,parent=None):
    data=bpy.data.meshes.new(name);data.from_pydata(verts,[],faces);data.update();o=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(o)
    assign(o,material)
    if parent:o.parent=parent
    return o


def box(name,center,size,material,bevel=0.,parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1,location=center);o=bpy.context.object;o.name=name;o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    assign(o,material)
    if bevel:
        mod=o.modifiers.new('Real manufactured edge radii','BEVEL');mod.width=bevel;mod.segments=3
        norm=o.modifiers.new('Weighted corner normals','WEIGHTED_NORMAL')
    if parent:o.parent=parent
    return o


def cylinder(name,center,radius,depth,material,axis='Y',parent=None,vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=center);o=bpy.context.object;o.name=name
    if axis=='Y':o.rotation_euler[0]=math.pi/2
    elif axis=='X':o.rotation_euler[1]=math.pi/2
    assign(o,material);be=o.modifiers.new('Rounded rim','BEVEL');be.width=min(radius*.08,depth*.18);be.segments=3
    for p in o.data.polygons:p.use_smooth=True
    o.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
    if parent:o.parent=parent
    return o


def curve(name,points,radius,material,parent=None,cyclic=False):
    data=bpy.data.curves.new(name,'CURVE');data.dimensions='3D';data.resolution_u=2;data.bevel_depth=radius;data.bevel_resolution=2
    sp=data.splines.new('POLY');sp.points.add(len(points)-1)
    for a,v in zip(sp.points,points):a.co=(*v,1.)
    sp.use_cyclic_u=cyclic;o=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(o);assign(o,material)
    if parent:o.parent=parent
    return o


def empty(name):
    o=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(o);o.rotation_mode='QUATERNION';return o


def look_at(obj,target):obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()


def build_ramp(cfg):
    before=set(bpy.context.scene.objects)
    finish=cfg['appearance']['ramp_finish'];build=cfg['appearance']['ramp_construction']
    width=cfg['physics']['ramp']['width_m'];points=profile(cfg)
    shell=build['deck_shell_thickness_m'];join=cfg['physics']['ramp']['flat_runout_m'];end=join+cfg['physics']['ramp']['exit_transition_m']
    face=mat('Satin teal ABS ramp deck',finish['deck_color_linear'],finish['deck_roughness'],coat=.10,micro=.000008)
    edge=mat('Dark teal molded ramp edge',finish['edge_color_linear'],.49,micro=.000008)
    support=mat('Charcoal ABS ramp support',finish['support_color_linear'],.56,micro=.000012)
    shoe=mat('Graphite flexible ramp exit shoe',build['exit_shoe_color_linear'],build['exit_shoe_roughness'],coat=.025,micro=.000012)
    rubber=mat('Toy ramp nonslip foot pads',(.025,.029,.031),.72,micro=.000025)
    vertices=[];lookup={};sections=[];faces=[];material_indices=[]
    def vertex(co):
        key=tuple(round(v,12) for v in co)
        if key not in lookup:lookup[key]=len(vertices);vertices.append(co)
        return lookup[key]
    def polygon(ids,material):
        ids=list(dict.fromkeys(ids))
        if len(ids)>=3:faces.append(ids);material_indices.append(material)
    def half_width(x):
        t=max(0.,min(1.,(x-join)/(end-join)));ease=t*t*(3-2*t)
        return (width+(build['exit_shoe_front_width_m']-width)*ease)/2
    for x,z in points:
        half=half_width(x)
        # The 3.2 mm horizontal deck rests on the floor; its exit lip tapers to zero.
        bottom=max(0.,z-shell)
        sections.append([vertex((x,-half,z)),vertex((x,half,z)),vertex((x,-half,bottom)),vertex((x,half,bottom))])
    for i,(a,b) in enumerate(zip(sections,sections[1:])):
        top_material=2 if points[i][0]>=join-1e-9 else 0
        polygon([a[0],b[0],b[1],a[1]],top_material)
        polygon([a[0],a[2],b[2],b[0]],1)
        polygon([a[1],b[1],b[3],a[3]],1)
        polygon([a[2],a[3],b[3],b[2]],1)
    a=sections[0];polygon([a[0],a[1],a[3],a[2]],1)
    a=sections[-1];polygon([a[0],a[2],a[3],a[1]],1)
    deck=mesh('Continuous physical ramp with flush curved toe',vertices,faces,face)
    deck.data.materials.append(edge);deck.data.materials.append(shoe)
    for poly,index in zip(deck.data.polygons,material_indices):poly.material_index=index
    # The edge rails sit beyond the 6 cm vehicle, leaving a 16.6 cm clear lane.
    rail_width=build['side_rail_width_m'];rise=build['side_rail_height_m']
    radius=build['edge_radius_m'];pad=build['support_foot_thickness_m']
    def beam(name,x0,x1,y,dy,lower,upper,material,bevel=radius):
        vv=[(x,yy,zfunc(x)) for zfunc in [lower,upper] for yy in [y-dy/2,y+dy/2] for x in [x0,x1]]
        obj=mesh(name,vv,[(0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5)],material)
        if bevel:
            mod=obj.modifiers.new('Manufactured rounded edges','BEVEL');mod.width=bevel;mod.segments=3
            obj.modifiers.new('Weighted molded edge normals','WEIGHTED_NORMAL')
        return obj
    for sign in [-1,1]:
        y=sign*(width/2-rail_width/2)
        # Follow the actual C1 slope-to-flat profile, rather than bridging the bend.
        rail_points=[(x,z) for x,z in points if x<=join+1e-9]
        vv=[]
        for x,z in rail_points:
            vv.extend([(x,y-rail_width/2,max(0.,z-build['side_rail_drop_m'])),
                       (x,y+rail_width/2,max(0.,z-build['side_rail_drop_m'])),
                       (x,y-rail_width/2,z+rise),(x,y+rail_width/2,z+rise)])
        ff=[]
        for i in range(len(rail_points)-1):
            a=i*4;b=a+4
            ff.extend([(a,a+1,b+1,b),(a+2,b+2,b+3,a+3),(a,b,b+2,a+2),(a+1,a+3,b+3,b+1)])
        ff.extend([(0,2,3,1),(len(vv)-4,len(vv)-3,len(vv)-1,len(vv)-2)])
        rail=mesh('Toy ramp rounded perimeter rail',vv,ff,face)
        mod=rail.modifiers.new('Manufactured rounded edges','BEVEL');mod.width=radius;mod.segments=3
        rail.modifiers.new('Weighted molded edge normals','WEIGHTED_NORMAL')
        # Low edge cheeks taper with the flexible exit lip; they cannot contact the car.
        toe_points=[(x,sign*(half_width(x)-rail_width/2),z) for x,z in points if join<=x<end-1e-9]
        vv=[]
        for x,cy,z in toe_points:
            amount=min(rise,z*.65)
            vv.extend([(x,cy-rail_width/2,z),(x,cy+rail_width/2,z),
                       (x,cy-rail_width/2,z+amount),(x,cy+rail_width/2,z+amount)])
        ff=[]
        for i in range(len(toe_points)-1):
            a=i*4;b=a+4;ff.extend([(a,a+1,b+1,b),(a+2,b+2,b+3,a+3),(a,b,b+2,a+2),(a+1,a+3,b+3,b+1)])
        ff.extend([(0,2,3,1),(len(vv)-4,len(vv)-3,len(vv)-1,len(vv)-2)])
        mesh('Toy ramp exit shoe edge cheek',vv,ff,edge)
        for x,dx in [(-.485,.032),(-.235,.028),(-.125,.024)]:
            # Sloped tops meet the shell underside, with real feet resting at z=0.
            beam('Toy ramp molded support leg',x-dx/2,x+dx/2,sign*.071,.017,
                 lambda x:pad,lambda x:surface(cfg,x)[0]-shell,support,.0005)
            box('Toy ramp nonslip foot',(x,sign*.071,pad/2),(dx+.006,.025,pad),rubber,.0004)
        box('Toy ramp longitudinal base frame',(-.305,sign*.071,pad+.005),(.39,.014,.010),support,.0007)
    for x in [-.485,-.235,-.125]:
        beam('Toy ramp transverse shell rib',x-.014,x+.014,0.,.151,
             lambda x:surface(cfg,x)[0]-shell-.005,
             lambda x:surface(cfg,x)[0]-shell,support,.0004)
    zinc=mat('Dull zinc countersunk screw',(.34,.35,.34),.35,.65)
    slot=mat('Recess in screw head',(.055,.050,.042),.7)
    for x in [-.485,-.235]:
        z=surface(cfg,x)[0]
        for y in [-.067,.067]:
            cylinder('Flush countersunk ramp screw',(x,y,z+.00002),.0014,.0001,zinc,'Z',vertices=32)
            box('Screw head slot',(x,y,z+.00009),(.0018,.00026,.00005),slot,.00004)
    root=empty('Toy ramp standalone assembly')
    root['construction_revision']=build['revision'];root['static_environment_assembly']=True
    for obj in set(bpy.context.scene.objects)-before-{root}:obj.parent=root
    return {'contact_surface':'Freshly simulated C1 slope, 16 cm horizontal deck at 3.2 mm, then 3.5 cm C1 lip to the wooden floor',
            'size_m':[cfg['physics']['ramp']['length_m']+end,width,.12],
            'flat_runout_m':join,'exit_transition_m':end-join,'deck_shell_thickness_m':shell,
            'clear_lane_width_m':width-2*rail_width,'exit_shoe_front_width_m':build['exit_shoe_front_width_m'],
            'construction':build,'surface_finish':finish,'physical_parameters_unchanged':False,
            'assembly':'One continuous molded teal deck with a horizontal base, rounded perimeter rails, support ribs, six nonslip feet and a short graphite exit lip.'}


def build_window(cfg,wx=-1.8,y0=-.72,y1=1.25,z0=.65,z1=2.35):
    settings=cfg['appearance']['window_curtain'];before=set(bpy.context.scene.objects)
    root=empty('Window and curtain assembly')
    paint=mat('Window warm white satin joinery',(.76,.755,.71),.34,coat=.08,micro=.000007)
    reveal=mat('Window pale painted reveal',(.69,.685,.65),.83,micro=.000025)
    gasket=mat('Window recessed charcoal glazing seal',(.025,.029,.028),.64,micro=.000006)
    spacer=mat('Window aluminium glazing spacer',(.27,.30,.29),.39,.72)
    metal=mat('Window satin nickel hardware',(.34,.36,.35),.31,.76)
    sill=mat('Window painted timber sill',(.79,.775,.715),.38,coat=.09,micro=.000009)
    mid=(y0+y1)/2;height=z1-z0;span=y1-y0
    # The reveal is real wall depth, with nested outer frame, sash and glazing beads.
    for y in [y0+.004,y1-.004]:box('Window deep jamb return',(wx,y,(z0+z1)/2),(.12,.008,height),reveal,.0008)
    for z in [z0+.004,z1-.004]:box('Window deep horizontal reveal',(wx,mid,z),(.12,span,.008),reveal,.0008)
    fx=wx+.025;frame_depth=.085;border=.062
    for y in [y0+border/2,y1-border/2]:box('Window fixed outer jamb',(fx,y,(z0+z1)/2),(frame_depth,border,height),paint,.002)
    for z in [z0+border/2,z1-border/2]:box('Window fixed outer rail',(fx,mid,z),(frame_depth,span-2*border,border),paint,.002)
    # Face trim covers the masonry/frame joint without occupying the curtain plane.
    for y in [y0-.015,y1+.015]:box('Window interior architrave',(wx+.078,y,(z0+z1)/2),(.018,.046,height+.085),paint,.002)
    box('Window architrave head',(wx+.078,mid,z1+.025),(.018,span+.075,.046),paint,.002)
    sill_obj=box('Window projecting rounded sill',(wx+.055,mid,z0-.012),(.235,span+.14,.032),sill,.005)
    box('Window sill apron',(wx+.070,mid,z0-.047),(.020,span+.03,.046),paint,.002)
    box('Window exterior drip edge',(wx-.070,mid,z0+.006),(.047,span,.018),paint,.002)
    # Two 4 mm glass sheets separated by a 14 mm air gap. Actual reflective/refraction geometry.
    glass=bpy.data.materials.new('Window clear double glazing');glass.use_nodes=True
    n=glass.node_tree.nodes;l=glass.node_tree.links;n.clear()
    output=n.new('ShaderNodeOutputMaterial');optical=n.new('ShaderNodeBsdfGlass')
    optical.inputs['Color'].default_value=(.97,.988,.982,1.);optical.inputs['Roughness'].default_value=.014;optical.inputs['IOR'].default_value=1.46
    # Thin pane shadow transmission avoids dark, unresolved glass caustics at 64 samples.
    path=n.new('ShaderNodeLightPath');trans=n.new('ShaderNodeBsdfTransparent');trans.inputs[0].default_value=(.94,.97,.96,1.)
    mix=n.new('ShaderNodeMixShader');l.new(path.outputs['Is Shadow Ray'],mix.inputs[0]);l.new(optical.outputs[0],mix.inputs[1]);l.new(trans.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],output.inputs['Surface'])
    glass.diffuse_color=(.90,.97,.95,1.)
    for index,(left,right) in enumerate([(y0+.068,mid-.010),(mid+.010,y1-.068)]):
        bottom=z0+.069;top=z1-.065;sash_width=.040;sx=wx+.047
        for y in [left+sash_width/2,right-sash_width/2]:box('Window opening sash stile',(sx,y,(bottom+top)/2),(.056,sash_width,top-bottom),paint,.0016)
        for z in [bottom+sash_width/2,top-sash_width/2]:box('Window opening sash rail',(sx,(left+right)/2,z),(.056,right-left-2*sash_width,sash_width),paint,.0016)
        gl=left+sash_width;gr=right-sash_width;gb=bottom+sash_width;gt=top-sash_width
        for side,y in [(-1,gl+.0015),(1,gr-.0015)]:
            box('Window narrow rubber glazing gasket',(wx+.047,y,(gb+gt)/2),(.004,.003,gt-gb),gasket,.0005)
            box('Window stepped glazing bead',(wx+.056,y+side*.005,(gb+gt)/2),(.012,.010,gt-gb),paint,.0008)
            box('Window sealed glass spacer',(wx+.035,y,(gb+gt)/2),(.016,.003,gt-gb),spacer,.00035)
        for z in [gb+.0015,gt-.0015]:
            box('Window narrow rubber glazing gasket',(wx+.047,(gl+gr)/2,z),(.004,gr-gl,.003),gasket,.0005)
            box('Window stepped glazing bead',(wx+.056,(gl+gr)/2,z+(-.005 if z<(gb+gt)/2 else .005)),(.012,gr-gl,.010),paint,.0008)
            box('Window sealed glass spacer',(wx+.035,(gl+gr)/2,z),(.016,gr-gl,.003),spacer,.00035)
        for gx in [wx+.026,wx+.044]:
            o=box('Window 4mm clear glass pane',(gx,(gl+gr)/2,(gb+gt)/2),(.004,gr-gl-.002,gt-gb-.002),glass,.00025)
            o['glass_thickness_m']=.004;o['air_gap_m']=.014
        # A lever, rose, screws and hinges make this an operable manufactured window.
        handle_y=right-.021 if index==0 else left+.021
        box('Window handle rose',(wx+.084,handle_y,1.47),(.012,.024,.060),metal,.004)
        cylinder('Window handle spindle',(wx+.100,handle_y,1.47),.005,.026,metal,'X',vertices=32)
        box('Window casement lever',(wx+.118,handle_y,1.435),(.014,.014,.080),paint,.006)
        for z in [1.450,1.490]:cylinder('Window handle fixing screw',(wx+.091,handle_y,z),.0016,.001,metal,'X',vertices=24)
        hinge_y=left-.003 if index==0 else right+.003
        for z in [bottom+.18,(bottom+top)/2,top-.18]:
            cylinder('Window sash hinge barrel',(wx+.080,hinge_y,z),.004,.034,metal,'Z',vertices=32)
            box('Window hinge leaf',(wx+.074,hinge_y,z),(.007,.019,.027),metal,.001)
    # Curtain support stands clear of the projecting sill, including deepest folds and cloth thickness.
    rodx=settings['rod_x_m'];rodz=settings['rod_height_m'];extension=settings['rod_end_extension_m']
    rodmat=mat('Curtain brushed warm nickel rod',(.30,.29,.265),.37,.67)
    cylinder('Curtain continuous rod',(rodx,mid,rodz),.009,span+2*extension,rodmat,'Y')
    for y in [y0-extension+.025,y1+extension-.025]:
        box('Curtain wall mounting plate',(wx+.066,y,rodz-.020),(.009,.027,.068),rodmat,.004)
        cylinder('Curtain projecting support bracket',((wx+.070+rodx)/2,y,rodz-.012),.004,rodx-(wx+.070),rodmat,'X',vertices=32)
        cylinder('Curtain rod end cap',(rodx,y+(-.025 if y<mid else .025),rodz),.014,.022,rodmat,'Y',vertices=40)
    linen=uv_material('Curtain natural woven ivory linen','rough_linen',(.72,.9),tint=(.99,.98,.94),normal_strength=.16)
    bsdf=linen.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Sheen Weight'].default_value=.32;bsdf.inputs['Sheen Roughness'].default_value=.72
    # Keep the scanned weave while restoring the existing room's warm ivory cloth.
    n=linen.node_tree.nodes;l=linen.node_tree.links
    diffuse=next(node for node in n if node.type=='TEX_IMAGE' and '_diff_' in node.image.name)
    gray=n.new('ShaderNodeRGBToBW');l.new(diffuse.outputs['Color'],gray.inputs[0])
    variation=n.new('ShaderNodeMapRange');variation.inputs['To Min'].default_value=.78;variation.inputs['To Max'].default_value=1.06;l.new(gray.outputs[0],variation.inputs['Value'])
    color=n.new('ShaderNodeMixRGB');color.blend_type='MULTIPLY';color.inputs[0].default_value=1.;color.inputs[1].default_value=(.70,.68,.61,1.);l.new(variation.outputs[0],color.inputs[2]);l.new(color.outputs[0],bsdf.inputs['Base Color'])
    n=linen.node_tree.nodes;l=linen.node_tree.links;out=n.get('Material Output');trans=n.new('ShaderNodeBsdfTranslucent');trans.inputs[0].default_value=(.77,.74,.67,1)
    mix=n.new('ShaderNodeMixShader');mix.inputs[0].default_value=.10;l.new(bsdf.outputs[0],mix.inputs[1]);l.new(trans.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],out.inputs['Surface'])
    hems=mat('Curtain stitched linen hems',(.62,.59,.52),.86,micro=.000025)
    nr=73;nc=65;top=rodz-.0145;bottom=settings['hem_floor_clearance_m'];cloths=[]
    for panel,cy in enumerate([y0-.015,y1+.015]):
        verts=[];faces=[];widths=[]
        for iz in range(nr):
            s=iz/(nr-1);width=.32+.10*(1-s)**1.6+.012*math.sin(math.pi*s);widths.append(width)
            amplitude=.028*min(1.,(1-s)/.025)
            for iy in range(nc):
                t=iy/(nc-1);fold=math.sin(t*10*math.pi+.13*math.sin(s*math.pi))
                x=rodx+amplitude*fold+.007*math.sin(s*math.pi)*math.sin(t*math.pi)
                y=cy+(t-.5)*width+.003*math.sin(2*math.pi*s+panel)*math.sin(math.pi*t)*(1-s)
                z=bottom+s*(top-bottom)+.005*(1-s)**5*(.5+.5*math.cos(t*10*math.pi))
                verts.append((x,y,z))
        for iz in range(nr-1):
            for iy in range(nc-1):a=iz*nc+iy;faces.append((a,a+1,a+nc+1,a+nc))
        o=mesh('Curtain hanging linen panel',verts,faces,linen);cloths.append(o)
        for p in o.data.polygons:p.use_smooth=True
        # World metre weave UVs follow the folded cross-section length.
        uv=o.data.uv_layers.new(name='Metre linen weave');distance={}
        for iz in range(nr):
            u=0.
            for iy in range(nc):
                if iy:
                    a=verts[iz*nc+iy-1];b=verts[iz*nc+iy];u+=math.dist(a,b)
                distance[iz*nc+iy]=(u/.271,verts[iz*nc+iy][2]/.271)
        for poly in o.data.polygons:
            for k in poly.loop_indices:uv.data[k].uv=distance[o.data.loops[k].vertex_index]
        mod=o.modifiers.new('Real linen thickness','SOLIDIFY');mod.thickness=.0008;mod.offset=0.
        # Side seams and a double bottom hem follow the same folded surface.
        for iy in [0,nc-1]:curve('Curtain sewn side hem',[verts[iz*nc+iy] for iz in range(nr)],.00065,hems)
        for iz in [1,2]:curve('Curtain double stitched lower hem',[verts[iz*nc+iy] for iy in range(nc)],.0005,hems)
        for iy in [0,10,21,32,43,54,64]:
            x,y,z=verts[(nr-1)*nc+iy]
            bpy.ops.mesh.primitive_torus_add(major_segments=32,minor_segments=8,location=(rodx,y,rodz),rotation=(math.pi/2,0,0),major_radius=.0125,minor_radius=.0011)
            ring=bpy.context.object;ring.name='Curtain hanging ring';ring.data.materials.append(rodmat)
            for p in ring.data.polygons:p.use_smooth=True
    root['revision']=settings['revision'];root['fixed_background_assembly']=True
    for obj in set(bpy.context.scene.objects)-before-{root}:obj.parent=root
    bpy.context.view_layer.update()
    cloth_min=min((o.matrix_world@v.co).x for o in cloths for v in o.data.vertices)-.0004
    sill_front=max((sill_obj.matrix_world@v.co).x for v in sill_obj.data.vertices)
    return {'revision':settings['revision'],'opening_width_m':span,'opening_height_m':height,
            'glass':'Two 4mm sheets per sash, 14mm air gap, IOR 1.46, roughness .014. Camera rays refract and reflect; thin-pane shadow transmission approximation avoids unresolved caustics.',
            'construction':'Deep masonry reveal, nested painted frames and sashes, stepped glazing beads, rubber seals, spacer bars, two casement levers and six hinges.',
            'curtain':'Two lined-thickness woven linen panels with side seams, double bottom hem, rings and wall-mounted rod; static background geometry.',
            'minimum_cloth_to_sill_x_clearance_m':cloth_min-sill_front,'hem_floor_clearance_m':bottom,
            'outdoor_context':'Existing photographic residential-garden HDRI seen through actual glass; no background image plane.'}


LIB=Path(os.environ.get('PCVE_ASSET_LIBRARY',str(ASSETS)))


def library_asset(relative):
    return LIB/relative


def uv_material(name,stem,rough=(.30,.46),tint=(1,1,1),normal_strength=.18,coat=0.):
    root=library_asset('polyhaven/'+stem+'/asset_manifest.json').parent;m=mat(name,(.5,.4,.3),.4,coat=coat)
    n=m.node_tree.nodes;l=m.node_tree.links;s=n.get('Principled BSDF')
    for suffix in ['diff','rough','nor_gl']:
        path=next(iter(sorted(root.glob(stem+'_'+suffix+'_*k.*'))),None)
        if not path:continue
        im=bpy.data.images.load(str(path),check_existing=True);tex=n.new('ShaderNodeTexImage');tex.image=im;tex.extension='REPEAT'
        if suffix!='diff':im.colorspace_settings.name='Non-Color'
        if suffix=='diff':
            mul=n.new('ShaderNodeMixRGB');mul.blend_type='MULTIPLY';mul.inputs[0].default_value=1;mul.inputs[2].default_value=(*tint,1)
            l.new(tex.outputs['Color'],mul.inputs[1]);l.new(mul.outputs[0],s.inputs['Base Color'])
        elif suffix=='rough':
            ran=n.new('ShaderNodeMapRange');ran.inputs['To Min'].default_value=rough[0];ran.inputs['To Max'].default_value=rough[1]
            l.new(tex.outputs['Color'],ran.inputs['Value']);l.new(ran.outputs[0],s.inputs['Roughness'])
        else:
            norm=n.new('ShaderNodeNormalMap');norm.inputs['Strength'].default_value=normal_strength
            l.new(tex.outputs['Color'],norm.inputs['Color']);l.new(norm.outputs[0],s.inputs['Normal'])
    return m


def physical_uv(o,axes=(0,1),repeat=1.,offset=(0,0)):
    uv=o.data.uv_layers.new(name='Real metre UV')
    o.data.uv_layers.active=uv;uv.active_render=True
    for p in o.data.polygons:
        for k in p.loop_indices:
            v=o.matrix_world@o.data.vertices[o.data.loops[k].vertex_index].co
            uv.data[k].uv=(v[axes[0]]/repeat+offset[0],v[axes[1]]/repeat+offset[1])


def append_objects(path,names=None):
    with bpy.data.libraries.load(str(path),link=False) as (src,dst):dst.objects=[s for s in src.objects if names is None or s in names]
    out=[o for o in dst.objects if o]
    for o in out:bpy.context.collection.objects.link(o)
    bpy.context.view_layer.update();return out


def bounds(objects):
    pts=[o.matrix_world@Vector(v) for o in objects if o.type=='MESH' for v in o.bound_box]
    return Vector([min(v[i] for v in pts) for i in range(3)]),Vector([max(v[i] for v in pts) for i in range(3)])


def normalize(objects,target_length,axis,xy=(0,0),bottom=0,name='Prop'):
    # Bake the existing hierarchy first, then apply one common world transform.
    matrices={o:o.matrix_world.copy() for o in objects}
    for o in objects:o.parent=None;o.matrix_world=matrices[o]
    bpy.context.view_layer.update();lo,hi=bounds(objects);factor=target_length/(hi[axis]-lo[axis])
    offset=Vector((xy[0],xy[1],bottom))-Vector(((lo.x+hi.x)*factor/2,(lo.y+hi.y)*factor/2,lo.z*factor))
    for o in objects:o.location=o.location*factor+offset;o.scale*=factor;o.name=name+' '+o.name
    bpy.context.view_layer.update();a,b=bounds(objects)
    return {'source_bounds_m':[list(lo),list(hi)],'uniform_scale':factor,'world_bounds_m':[list(a),list(b)],'dimensions_m':list(b-a)}


def ball(cfg):
    root=empty('ball');r=cfg['physics']['ball']['radius_m'];palette=[]
    for i,color in enumerate(cfg['appearance']['ball_colors']):
        m=mat('Printed PVC color '+str(i),color,.34,coat=.12)
        n=m.node_tree.nodes;l=m.node_tree.links;s=n.get('Principled BSDF');tc=n.new('ShaderNodeTexCoord')
        fine=n.new('ShaderNodeTexNoise');fine.inputs['Scale'].default_value=3700.;fine.inputs['Detail'].default_value=2.
        l.new(tc.outputs['Object'],fine.inputs['Vector']);bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000009;bump.inputs['Strength'].default_value=.22
        l.new(fine.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],s.inputs['Normal'])
        wear=n.new('ShaderNodeTexNoise');wear.inputs['Scale'].default_value=210.;wear.inputs['Detail'].default_value=3.;l.new(tc.outputs['Object'],wear.inputs['Vector'])
        ran=n.new('ShaderNodeMapRange');ran.inputs['To Min'].default_value=.27;ran.inputs['To Max'].default_value=.44
        l.new(wear.outputs['Fac'],ran.inputs['Value']);l.new(ran.outputs[0],s.inputs['Roughness']);palette.append(m)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=128,ring_count=64,radius=r);o=bpy.context.object;o.name='Scuffed color printed hollow PVC ball';o.parent=root
    for m in palette:o.data.materials.append(m)
    o.data.update()
    for p in o.data.polygons:
        p.use_smooth=True;p.material_index=int(((math.atan2(p.center.y,p.center.x)+math.pi)/(2*math.pi))*6)%3
    seam=mat('Subtle molded PVC seam',(.43,.38,.26),.46)
    curve('Fine mold equator',[(r*math.cos(k*2*math.pi/256),r*math.sin(k*2*math.pi/256),0) for k in range(256)],.000025,seam,root,True)
    cylinder('Recessed PVC inflation valve',(0,0,r-.0001),.0011,.00022,seam,'Z',root,40)
    return root


def ramp(cfg):
    return build_ramp(cfg)


def room_realism(cfg,assets):
    rng=random.Random(cfg['appearance']['seed']);ledger={}
    # A calibrated scanned floor preserves the continuous solved support plane at z=0.
    under=mat('Dark floor joint backing',(.12,.09,.06),.8);box('Continuous structural floor',(0,0,-.026),(10,9,.05),under)
    finish=uv_material('Scanned satin oak household floor','wood_floor',(.31,.52),tint=(.92,.94,.93),normal_strength=.18,coat=.08)
    o=box('Continuous flush oak floor finish',(0,0,-.006),(10,9,.012),finish)
    repeat=cfg['appearance']['floor_texture_repeat_m'];physical_uv(o,(1,0),repeat,(.11,.06))
    ledger['floor']={'scanned_board_width_m':repeat/9,'texture_repeat_m':repeat,'finished_top_z_m':0.,'relief':'PBR normal map; no geometric offset of the solved support plane'}
    ledger['ramp']=ramp(cfg)
    wall=mat('Warm white painted plaster',(.72,.715,.68),.91,micro=.00005);trim=mat('Satin painted skirting',(.78,.78,.74),.35)
    box('Rear room wall',(.5,2.45,1.4),(7,.12,2.8),wall)
    box('Rear skirting',(.5,2.378,.062),(7,.024,.124),trim,.003)
    # Genuine window opening in the side wall; no decorative frame laid over solid masonry.
    wx=-1.8;y0=-.72;y1=1.25;z0=.65;z1=2.35
    box('Left wall front pier',(wx,-1.86,1.4),(.12,2.28,2.8),wall)
    box('Left wall rear pier',(wx,1.875,1.4),(.12,1.25,2.8),wall)
    box('Wall below window',(wx,(y0+y1)/2,z0/2),(.12,y1-y0,z0),wall)
    box('Window lintel',(wx,(y0+y1)/2,(z1+2.8)/2),(.12,y1-y0,2.8-z1),wall)
    box('Ceiling',(.5,-.4,2.83),(7,5.7,.10),wall)
    # Fixed furniture is kept behind the entire motion corridor.
    sofa_names={'Sofa','Sofa.001','Sofa.002','Sofa.003','Sofa.004','Sofa.005','Sofa.006','Sofa.007','pillow L.001','pillow L.002','Cylinder','Cube','Cube.001'}
    sofa_source=asset(cfg['appearance']['sofa_asset'])
    if not sofa_source.is_file():sofa_source=LIB/'blenderkit/cozy_living_room/cozy_living_room.blend'
    sofa=append_objects(sofa_source,sofa_names)
    linen=uv_material('Oatmeal woven upholstery','rough_linen',(.72,.91),tint=(.71,.69,.63),normal_strength=.13)
    bsdf=linen.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Sheen Weight'].default_value=.25
    # The source UVs are preserved for the furniture; calibrated texture repeat is object metres.
    fabric_ref=empty('Upholstery real metre coordinates')
    for m,color in [(linen,(.56,.58,.56))]:
        n=m.node_tree.nodes;l=m.node_tree.links;tc=n.new('ShaderNodeTexCoord');scale=n.new('ShaderNodeVectorMath');scale.operation='SCALE';scale.inputs[3].default_value=1/.271;l.new(tc.outputs['Object'],scale.inputs[0])
        tc.object=fabric_ref
        for tex in n:
            if tex.type=='TEX_IMAGE':tex.projection='BOX';tex.projection_blend=.25;l.new(scale.outputs[0],tex.inputs['Vector'])
    pillow=mat('Muted blue gray woven pillow',(.14,.21,.23),.87,micro=.00012)
    cream=mat('Natural unbleached cushion',(.64,.60,.50),.9,micro=.00010)
    for o in sofa:
        for i,m in enumerate(o.data.materials):
            if m and m.name.startswith('Procedural Fabric'):o.data.materials[i]=linen
            elif m and m.name=='Fabric':o.data.materials[i]=pillow if '001' in o.name else cream
    ledger['sofa']=normalize(sofa,2.16,0,xy=(.6,1.50),name='Household sofa')
    basket=append_objects(LIB/'blenderkit/rattan_basket/rattan_basket.blend');ledger['basket']=normalize(basket,.41,0,xy=(-.62,.64),name='Toy storage')
    penguin=append_objects(LIB/'blenderkit/stuffed_penguin/stuffed_penguin.blend');ledger['soft_toy']=normalize(penguin,.24,2,xy=(-.64,.66),bottom=.095,name='Stored soft toy')
    # A few used wooden blocks inside the basket, with restrained bevels and varied orientation.
    for i,color in enumerate([(.36,.10,.055),(.055,.20,.24),(.58,.38,.09)]):
        o=box('Stored wooden play block',(-.75+i*.11,.56,.17),(.065,.065,.065),mat('Worn painted wood '+str(i),color,.63,micro=.000025),.0018);o.rotation_euler=(.08*i,.1*(i-1),.4*i)
    # Small everyday book stack, away from the ramp and impact corridor.
    pages=mat('Cream cut paper edges',(.68,.65,.56),.88,micro=.000035)
    for i,color in enumerate([(.10,.23,.25),(.42,.22,.11)]):
        root=empty('Picture book '+str(i));root.location=(-1.02,.13,.011+i*.021);root.rotation_mode='XYZ';root.rotation_euler.z=-.18+i*.22
        cover=mat('Printed cloth book cover '+str(i),color,.52)
        box('Textured paper block',(0,0,0),(.218,.17,.016),pages,.0008,root)
        for z in [-.009,.009]:box('Book cover board',(0,0,z),(.225,.177,.0022),cover,.0006,root)
        box('Rounded bound book spine',(-.111,0,0),(.004,.177,.020),cover,.001,root)
        for k in range(7):curve('Quiet page signature',[(.109,-.082,-.006+k*.002),(.109,.082,-.006+k*.002)],.000045,cream,root)
    ledger['window_curtain']=build_window(cfg,wx,y0,y1,z0,z1)
    ledger.update({'ball_diameter_m':.06,'car_approx_m':[.122,.061,.049],'room_m':[7,5.7,2.8],
       'assets':'Integrated BlenderKit toy car, sofa with original legs, wicker basket and stuffed penguin; Poly Haven CC0 oak/plywood/linen/HDRI. No photographic background planes.'})
    return ledger


def lighting_realism(cfg):
    s=bpy.context.scene;w=bpy.data.worlds.new('Daylight outside actual window');w.use_nodes=True;s.world=w
    n=w.node_tree.nodes;l=w.node_tree.links;env=n.new('ShaderNodeTexEnvironment');env.image=bpy.data.images.load(str(library_asset('polyhaven/residential_garden/residential_garden_4k.hdr')))
    l.new(env.outputs['Color'],n.get('Background').inputs['Color']);n.get('Background').inputs['Strength'].default_value=.55
    d=bpy.data.lights.new('Soft daylight through side window','AREA');d.energy=260;d.shape='RECTANGLE';d.size=1.65;d.size_y=1.45;d.color=(.91,.95,1.)
    o=bpy.data.objects.new(d.name,d);bpy.context.collection.objects.link(o);o.location=(-2.02,.10,1.55);look_at(o,(.4,.25,.25))
    # This area is a daylight surrogate, not a luminous panel outside the house.
    o.visible_camera=False;o.visible_glossy=False;o.visible_transmission=False
    sun=bpy.data.lights.new('Gentle morning sun','SUN');sun.energy=.85;sun.angle=math.radians(4.);sun.color=(1.,.91,.76)
    o=bpy.data.objects.new(sun.name,sun);bpy.context.collection.objects.link(o);o.location=(-4,1.2,3);look_at(o,(0,0,0))
    # Camera-side room opening gives only a broad, weak fill; window remains the dominant light.
    d=bpy.data.lights.new('Diffuse household room fill','AREA');d.energy=22;d.shape='DISK';d.size=2.5;d.color=(1.,.96,.88)
    o=bpy.data.objects.new(d.name,d);bpy.context.collection.objects.link(o);o.location=(1,-2,2.1);look_at(o,(.5,.5,.1))


def library():
    return Path(os.environ.get('PCVE_ASSET_LIBRARY', str(ASSETS)))


def actual_bounds(objects):
    points = [o.matrix_world @ v.co for o in objects if o.type == 'MESH' for v in o.data.vertices]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    return lo, hi


def smooth_with_derivative(value,start,end):
    t=max(0.,min(1.,(value-start)/(end-start)))
    return t*t*(3-2*t),(6*t*(1-t)/(end-start) if start<value<end else 0.)


def sculpt_front(point,settings):
    lift,dlift=smooth_with_derivative(point.x,settings['bonnet_start_x_m'],settings['bonnet_full_x_m'])
    upper,dupper=smooth_with_derivative(point.z,settings['lower_activation_z_m'],settings['full_activation_z_m'])
    shorten,dshorten=smooth_with_derivative(point.x,settings['shorten_start_x_m'],settings['shorten_full_x_m'])
    amount=settings['bonnet_lift_m'];back=settings['nose_shortening_m']
    result=Vector((point.x-back*shorten,point.y,point.z+settings.get('body_lift_m',0.)+amount*lift*upper))
    # Jacobian entries for exact inverse-transpose split-normal transport.
    return result,(1-back*dshorten,amount*dlift*upper,1+amount*lift*dupper)


def cut_toy_wheel_clearance(root,car_spec):
    """Machine actual round wheel openings; keep the native wheel and solver geometry intact."""
    changed=[]
    meshes=[o for o in root.children_recursive if o.type=='MESH' and 'BrakePad' not in o.name]
    for index in range(4):
        center=Vector((car_spec['wheelbase_m']/2 if index<2 else -car_spec['wheelbase_m']/2,
            -car_spec['wheel_center_track_m']/2 if index%2==0 else car_spec['wheel_center_track_m']/2,
            -car_spec['com_above_axle_m']))
        bpy.ops.mesh.primitive_cylinder_add(vertices=128,radius=car_spec['wheel_radius_m']+.0008,depth=.016,
            location=center,rotation=(math.pi/2,0,0))
        cutter=bpy.context.object;cutter.name='Temporary exact wheel-well tool';cutter.parent=root
        bpy.context.view_layer.update()
        for obj in meshes:
            points=[obj.matrix_basis @ vertex.co for vertex in obj.data.vertices]
            if not points:continue
            if any(max(p[i] for p in points)<center[i]-extent or min(p[i] for p in points)>center[i]+extent
                for i,extent in enumerate([.0148,.008,.0148])):continue
            modifier=obj.modifiers.new('Actual miniature wheel opening','BOOLEAN')
            modifier.operation='DIFFERENCE';modifier.solver='EXACT';modifier.object=cutter
            if hasattr(modifier,'use_hole_tolerant'):modifier.use_hole_tolerant=True
            bpy.context.view_layer.objects.active=obj
            bpy.ops.object.modifier_apply(modifier=modifier.name)
            changed.append({'wheel':index,'mesh':obj.name,'remaining_faces':len(obj.data.polygons)})
        bpy.data.objects.remove(cutter,do_unlink=True)
    return {'clearance_radius_m':car_spec['wheel_radius_m']+.0008,'wheel_radius_m':car_spec['wheel_radius_m'],'nominal_gap_m':.0008,'operations':changed}


def replace_car(cfg, roots=None, asset_path=None):
    c = cfg['physics']['car']
    roots = roots or {name: empty(name) for name in ['car_body', 'wheel_0', 'wheel_1', 'wheel_2', 'wheel_3']}
    for root in roots.values():
        for child in list(root.children_recursive):
            bpy.data.objects.remove(child, do_unlink=True)
    old = set(bpy.data.objects)
    asset_path = Path(asset_path or library() / cfg['appearance']['car_asset'])
    bpy.ops.import_scene.gltf(filepath=str(asset_path))
    imported = set(bpy.data.objects) - old
    bpy.context.view_layer.update()
    wheels = {name: next(o for o in imported if o.name == name) for name in ['WheelFrontL', 'WheelFrontR', 'WheelRearL', 'WheelRearR']}
    matrices = {o: o.matrix_world.copy() for o in imported}
    wheel_groups = {o: name for name, root in wheels.items() for o in root.children_recursive if o.type == 'MESH'}
    centers = {name: root.matrix_world.translation.copy() for name, root in wheels.items()}
    front_y = sum(centers[k].y for k in ['WheelFrontL', 'WheelFrontR']) / 2
    rear_y = sum(centers[k].y for k in ['WheelRearL', 'WheelRearR']) / 2
    center_y = (front_y + rear_y) / 2
    center_z = sum(v.z for v in centers.values()) / 4
    scale = c['wheelbase_m'] / (rear_y-front_y)
    rotation = Matrix.Rotation(math.pi/2, 3, 'Z')
    groups = {}
    for name, root in wheels.items():
        tire = next(o for o in root.children_recursive if o.type == 'MESH' and any(m and m.name.startswith('Tireside') for m in o.data.materials))
        local_matrix = matrices[root].inverted() @ matrices[tire]
        coords = [local_matrix @ v.co for v in tire.data.vertices]
        radius = max(math.hypot(p.y, p.z) for p in coords)
        lo_x, hi_x = min(p.x for p in coords), max(p.x for p in coords)
        target_index = (0 if 'Front' in name else 2) + (1 if centers[name].x > 0 else 0)
        groups[name] = {'radius_m_original': radius, 'width_m_original': hi_x-lo_x, 'index': target_index,
                        'axial_center': (lo_x+hi_x)/2}
    created = []
    front_settings=cfg['appearance']['car_front_shape']
    for obj in list(imported):
        if obj.type != 'MESH':
            continue
        matrix = matrices[obj]
        group = wheel_groups.get(obj)
        obj.data = obj.data.copy()
        source_normals = [item.vector.copy() for item in obj.data.corner_normals]
        front_jacobians={}
        obj.parent = None
        obj.matrix_world = Matrix.Identity(4)
        if group:
            g = groups[group]
            local = matrices[wheels[group]].inverted() @ matrix
            vertex_transform = rotation.to_4x4() @ Matrix.Diagonal((c['wheel_width_m']/g['width_m_original'],c['wheel_radius_m']/g['radius_m_original'],c['wheel_radius_m']/g['radius_m_original'],1.)) @ Matrix.Translation((-g['axial_center'],0,0)) @ local
            for vertex in obj.data.vertices:
                point = local @ vertex.co
                point.x = (point.x-g['axial_center']) * c['wheel_width_m'] / g['width_m_original']
                point.y *= c['wheel_radius_m'] / g['radius_m_original']
                point.z *= c['wheel_radius_m'] / g['radius_m_original']
                vertex.co = rotation @ point
            if 'BrakePad' in obj.name:
                obj.parent = roots['car_body']
                index = g['index']
                obj.location = (c['wheelbase_m']/2 if index < 2 else -c['wheelbase_m']/2,
                    -c['wheel_center_track_m']/2 if index % 2 == 0 else c['wheel_center_track_m']/2,
                    -c['com_above_axle_m'])
            else:
                obj.parent = roots['wheel_' + str(g['index'])]
        else:
            vertex_transform = Matrix.Translation((0,0,-c['com_above_axle_m'])) @ Matrix.Diagonal((scale,scale,scale*cfg['appearance']['car_body_vertical_scale'],1.)) @ rotation.to_4x4() @ Matrix.Translation((0,-center_y,-center_z)) @ matrix
            for vertex in obj.data.vertices:
                point = matrix @ vertex.co
                point = rotation @ Vector((point.x, point.y-center_y, point.z-center_z)) * scale
                point.z = point.z * cfg['appearance']['car_body_vertical_scale'] - c['com_above_axle_m']
                vertex.co,jacobian=sculpt_front(point,front_settings)
                front_jacobians[vertex.index]=jacobian
            obj.parent = roots['car_body']
        obj.name = 'diecast ' + obj.name
        obj.data.update()
        normal_matrix = vertex_transform.to_3x3().inverted().transposed()
        normals=[]
        for loop,normal in zip(obj.data.loops,source_normals):
            value=normal_matrix @ normal
            if not group:
                jac_x,jac_zx,jac_z=front_jacobians[loop.vertex_index]
                value=Vector((value.x/jac_x-jac_zx*value.z/(jac_x*jac_z),value.y,value.z/jac_z))
            normals.append(value.normalized())
        obj.data.normals_split_custom_set(normals)
        created.append(obj)
    for obj in imported:
        if obj.type != 'MESH':
            bpy.data.objects.remove(obj, do_unlink=True)
    # Clear imported presentation animations and switch off sample-car powered lamps.
    used_materials = {slot.material for obj in created for slot in obj.material_slots if slot.material}
    for material in used_materials:
        if not material.use_nodes:
            continue
        for node in material.node_tree.nodes:
            if node.type != 'BSDF_PRINCIPLED':
                continue
            if 'Emission Strength' in node.inputs:
                node.inputs['Emission Strength'].default_value = 0
            if material.name.startswith('Paint 1'):
                for socket in ['Base Color', 'Metallic', 'Roughness', 'Normal']:
                    for link in list(node.inputs[socket].links):
                        material.node_tree.links.remove(link)
                node.inputs['Base Color'].default_value = (*cfg['appearance']['car_color'], 1)
                node.inputs['Metallic'].default_value = .62
                node.inputs['Roughness'].default_value = .31
                node.inputs['Coat Weight'].default_value = .45
                node.inputs['Coat Roughness'].default_value = .20
            elif material.name.startswith('Paint 2'):
                node.inputs['Roughness'].default_value = .38
                node.inputs['Coat Weight'].default_value = .2
            elif material.name.startswith(('Tireside', 'Tiretread')):
                node.inputs['Roughness'].default_value = .72
                node.inputs['Coat Weight'].default_value = 0
            elif material.name.startswith('Glass'):
                node.inputs['Roughness'].default_value = .035
                node.inputs['IOR'].default_value = 1.46
                node.inputs['Transmission Weight'].default_value = 1
                node.inputs['Base Color'].default_value = (.92, .97, .98, 1)
                node.inputs['Coat Weight'].default_value = 0
            elif material.name.startswith('Rim'):
                node.inputs['Roughness'].default_value = .29
    # A molded miniature safety bumper is part of the car, exactly at its native contact face.
    finish = mat('flush diecast nose finish', cfg['appearance']['car_color'], .31, .62, .45)
    box('thin flush contact nose integrated into sculpted bonnet', (.0605, 0, .0005), (.001, .034, .0035), finish, .00035, roots['car_body'])
    # Original asset plate has a large demonstration logo; keep the modeled plate with plain paint.
    plate = mat('plain miniature number plate', (.72, .70, .61), .46)
    for obj in created:
        if 'License' in obj.name:
            obj.data.materials.clear()
            obj.data.materials.append(plate)
    wheel_clearance=cut_toy_wheel_clearance(roots['car_body'],c)
    roots['car_body']['visual_asset'] = 'Car Concept, Eric Chadwick / Darmstadt Graphics Group, CC BY 4.0; source public domain Unity Fan model'
    roots['car_body']['previous_car_assets_reused'] = False
    roots['car_body']['uniform_wheelbase_scale'] = scale
    roots['car_body']['toy_body_vertical_adaptation'] = cfg['appearance']['car_body_vertical_scale']
    roots['car_body']['collision_proxies_and_motion_unchanged'] = True
    return roots, {'source': str(asset_path), 'uniform_wheelbase_scale': scale, 'body_vertical_adaptation': cfg['appearance']['car_body_vertical_scale'],
                   'source_axle_centers': {k:list(v) for k,v in centers.items()}, 'wheel_groups': groups,
                   'wheelbase_m': c['wheelbase_m'], 'wheel_radius_m': c['wheel_radius_m'], 'wheel_width_m': c['wheel_width_m'],
                   'bumper_front_x_m': .061, 'bumper_center_z_relative_to_com_m': .0005,'front_shape':front_settings,'contact_trim_dimensions_m':[.001,.034,.0035], 'wheel_wells':wheel_clearance,'asset_reused_from_previous_scene': False}


def improve_surfaces():
    for material in bpy.data.materials:
        if not material.use_nodes:
            continue
        nodes = material.node_tree.nodes
        principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not principled:
            continue
        if material.name.startswith('Scanned satin oak household floor'):
            principled.inputs['Coat Weight'].default_value = .14
            principled.inputs['Coat Roughness'].default_value = .24
            for n in nodes:
                if n.type == 'NORMAL_MAP': n.inputs['Strength'].default_value = .10
                if n.type == 'MAP_RANGE':
                    n.inputs['To Min'].default_value = .28
                    n.inputs['To Max'].default_value = .47
        if material.name.startswith('Oatmeal woven upholstery'):
            principled.inputs['Sheen Weight'].default_value = .22
            for n in nodes:
                if n.type == 'NORMAL_MAP': n.inputs['Strength'].default_value = .08
        if material.name.startswith('Warm white painted plaster'):
            principled.inputs['Base Color'].default_value = (.63, .62, .58, 1)
        if 'clear double glazing' in material.name:
            for n in nodes:
                if n.type == 'BSDF_GLASS':
                    n.inputs['Color'].default_value = (.998, .998, .998, 1)
                    n.inputs['Roughness'].default_value = .002
                    n.inputs['IOR'].default_value = 1.46
                if n.type == 'BSDF_TRANSPARENT':
                    n.inputs[0].default_value = (.995, .995, .995, 1)
    panes = [o for o in bpy.context.scene.objects if '4mm clear glass pane' in o.name]
    for obj in panes:
        # Plane faces must be optically flat; bevel/weighted normals are unsuitable for glazing.
        for modifier in list(obj.modifiers):
            obj.modifiers.remove(modifier)
        for polygon in obj.data.polygons:
            polygon.use_smooth = False
        obj['optically_flat_normals'] = True
    return {'glazing_panes': len(panes), 'glass_ior': 1.46, 'glass_roughness': .002, 'pane_thickness_m': .004, 'camera_reflections_preserved': True}


def open_left_casement(angle_deg=160.):
    # Put the pin at the exterior edge of the frame. An interior pin makes a wide-open leaf
    # pass through the jamb and puts a grazing glass reflector across the camera's window ray.
    for obj in list(bpy.context.scene.objects):
        if 'Window sash hinge barrel' in obj.name or 'Window hinge leaf' in obj.name:
            bpy.data.objects.remove(obj,do_unlink=True)
    nickel=mat('exterior casement brushed hinge steel',(.31,.33,.32),.34,.75)
    for y in [-.72+.068-.003,1.25-.068+.003]:
        for z in [.65+.069+.18,1.502,2.35-.065-.18]:
            cylinder('fixed exterior casement hinge pin',(-1.82,y,z),.004,.034,nickel,'Z',vertices=32)
            box('moving casement offset hinge arm',((-1.82-1.753)/2,y,z),(.067,.012,.026),nickel,.001)
    tokens=['opening sash','rubber glazing gasket','stepped glazing bead','sealed glass spacer',
            '4mm clear glass pane','handle rose','handle spindle','casement lever','handle fixing screw','moving casement offset hinge arm']
    moved=[]
    bpy.context.view_layer.update()
    for obj in bpy.context.scene.objects:
        if obj.type!='MESH' or not any(token in obj.name for token in tokens):continue
        center=sum((obj.matrix_world @ Vector(c) for c in obj.bound_box),Vector())/8
        left=center.y<.265
        pivot=Vector((-1.82,-.72+.068-.003 if left else 1.25-.068+.003,.65))
        rotation=Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(angle_deg if left else -angle_deg),4,'Z') @ Matrix.Translation(-pivot)
        obj.matrix_world=rotation @ obj.matrix_world
        moved.append(obj.name)
    return {'both_leaves_open_outward_deg':angle_deg,'glazing':'Genuine flat double glazing with Fresnel reflections, physically swung out of the opening',
            'moved_sash_components':moved,'removed_reflection_cheats':False}


def instance_asset(path, size_z, position, yaw, name, originals=None):
    if originals is None:
        before = set(bpy.data.objects)
        if path.suffix == '.blend':
            with bpy.data.libraries.load(str(path), link=False) as (src, dest):
                dest.objects = src.objects
            originals = [o for o in dest.objects if o]
            for o in originals: bpy.context.collection.objects.link(o)
        else:
            bpy.ops.import_scene.gltf(filepath=str(path))
            originals = list(set(bpy.data.objects) - before)
        bpy.context.view_layer.update()
        matrices = {o:o.matrix_world.copy() for o in originals}
        for obj in originals:
            obj.parent = None
            obj.matrix_world = matrices[obj]
        lo, hi = actual_bounds(originals)
        factor = size_z / (hi.z-lo.z)
        origin = Vector(((lo.x+hi.x)/2, (lo.y+hi.y)/2, lo.z))
        rotation = Matrix.Rotation(yaw, 4, 'Z')
        transform = Matrix.Translation(Vector(position)) @ rotation @ Matrix.Scale(factor, 4) @ Matrix.Translation(-origin)
        for obj in originals:
            obj.matrix_world = transform @ matrices[obj]
            obj.name = name + ' ' + obj.name
        return originals
    raise NotImplementedError


def courtyard(cfg):
    rng = random.Random(713005)
    settings = cfg['appearance']['courtyard']
    ground = settings['ground_z_m']
    paving = mat('outdoor pale weathered limestone', (.38, .39, .35), .77, micro=.00008)
    soil = mat('shaded garden soil', (.045, .036, .021), .95, micro=.0003)
    lawn = mat('uneven short lawn ground', (.060, .105, .024), .92, micro=.0002)
    box('courtyard ground foundation', (-5.2, .2, ground-.05), (7.0, 12, .10), soil)
    # Proper parallax: near paving, a grass border, planters, then the boundary behind them.
    for ix in range(4):
        for iy in range(13):
            x = -2.02 - ix*.48
            y = -3.0 + iy*.48
            box('real outdoor paving slab', (x, y, ground+.018), (.477, .477, .036), paving, .003)
    box('recessed lawn bed', (-5.1, .25, ground+.002), (2.9, 9.0, .004), lawn)
    # A continuous courtyard boundary hides the panorama's building/curtain-like stripes,
    # so the opening looks at real geometry at a measured distance.
    boundary=mat('weathered garden limewash',(.48,.51,.46),.88,micro=.00012)
    wall_x=settings['boundary_wall_x_m'];wall_height=settings['boundary_wall_height_m']
    wall=box('actual exterior garden boundary wall',(wall_x,.25,ground+wall_height/2),(.14,11.0,wall_height),boundary,.009)
    nodes=boundary.node_tree.nodes;links=boundary.node_tree.links;bsdf=nodes.get('Principled BSDF')
    tc=nodes.new('ShaderNodeTexCoord');noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=6.5;noise.inputs['Detail'].default_value=3.
    links.new(tc.outputs['Generated'],noise.inputs['Vector'])
    ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.39,.43,.37,1);ramp.color_ramp.elements[1].color=(.56,.58,.53,1)
    links.new(noise.outputs['Fac'],ramp.inputs[0]);links.new(ramp.outputs[0],bsdf.inputs['Base Color'])
    cap=mat('aged pale concrete wall coping',(.34,.36,.32),.77,micro=.00008)
    box('sloped-weathered garden wall coping',(wall_x,.25,ground+wall_height+.01),(.19,11.05,.04),cap,.006)
    plant_path = library() / 'polyhaven_models/potted_plant_02/potted_plant_02_1k.gltf'
    for index, (x,y,h) in enumerate(settings['planted_containers_xyz_height_m']):
        instance_asset(plant_path, h, (x,y,ground), rng.uniform(-math.pi,math.pi), 'courtyard planted container '+str(index))
    grass_path = library() / 'polyhaven_models/grass_medium_01/grass_medium_01_1k.gltf'
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(grass_path))
    imported = list(set(bpy.data.objects) - before)
    bpy.context.view_layer.update()
    template = [o for o in imported if o.type == 'MESH']
    template_matrices = {o:o.matrix_world.copy() for o in template}
    lo,hi=actual_bounds(template)
    origin=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,lo.z))
    for i in range(65):
        size=rng.uniform(.12,.21)/(hi.z-lo.z)
        t=Matrix.Translation((-3.95-rng.random()*1.9,-3.5+rng.random()*7.5,ground)) @ Matrix.Rotation(rng.random()*6.283,4,'Z') @ Matrix.Scale(size,4) @ Matrix.Translation(-origin)
        for obj in template:
            new=bpy.data.objects.new('individual garden grass tuft',obj.data)
            bpy.context.collection.objects.link(new)
            new.matrix_world=t @ template_matrices[obj]
    for obj in imported:
        bpy.data.objects.remove(obj,do_unlink=True)
    return {'revision':settings['revision'], 'construction':'Real 3D near paving, planted containers, individually instanced scanned grasses, and 2.3 m limewashed courtyard boundary; HDRI supplies sky and distant lighting.',
            'ground_z_m':ground, 'nearest_slab_center_distance_from_window_m':.22, 'boundary_wall_x_m':wall_x,'boundary_wall_height_m':wall_height,
            'plants':'Poly Haven potted_plant_02 and grass_medium_01, CC0', 'background_image_planes':False}


def tune_lighting(cfg):
    scene=bpy.context.scene
    settings=cfg['appearance']['interior_lighting']
    scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=settings['environment_strength']
    for obj in scene.objects:
        if obj.type!='LIGHT':continue
        if obj.data.type=='SUN':
            obj.data.energy=settings['sun_energy'];obj.data.angle=math.radians(settings['sun_angle_deg']);obj.data.color=(1.,.97,.91)
        elif 'Soft daylight through side window' in obj.name:
            obj.data.energy=settings['window_area_w'];obj.data.color=(.93,.97,1.)
        elif 'Diffuse household room fill' in obj.name:
            obj.data.energy=settings['room_fill_w'];obj.data.color=(1.,.98,.94)
    scene.view_settings.exposure=settings['exposure_ev']
    scene.cycles.max_bounces=12
    scene.cycles.transmission_bounces=12
    scene.cycles.glossy_bounces=6
    return dict(settings)


def refine_existing(cfg, asset_path=None):
    roots={name:bpy.data.objects[name] for name in ['car_body','wheel_0','wheel_1','wheel_2','wheel_3']}
    roots,car_ledger=replace_car(cfg,roots,asset_path)
    glass_ledger=improve_surfaces()
    glass_ledger['casement']=open_left_casement(cfg['appearance']['courtyard']['both_casements_open_deg'])
    garden_ledger=courtyard(cfg)
    lights=tune_lighting(cfg)
    return roots,{'car':car_ledger,'window':glass_ledger,'courtyard':garden_ledger,'lighting':lights}


def room(cfg,assets):
    ledger=room_realism(cfg,assets)
    ledger['surfaces']=improve_surfaces()
    ledger['surfaces']['casement']=open_left_casement(cfg['appearance']['courtyard']['both_casements_open_deg'])
    ledger['courtyard']=courtyard(cfg)
    return ledger


def car(cfg):
    return replace_car(cfg)[0]


def lighting(cfg):
    lighting_realism(cfg)
    tune_lighting(cfg)


HIDDEN_FILL_LIGHTS = ('Soft daylight through side window', 'Diffuse household room fill')


# Real window opening of the side wall (built by room_realism): x = -1.8 (wall -1.86..-1.74).
WINDOW = {'wall_inner_x_m': -1.74, 'y_m': (-.72, 1.25), 'z_m': (.65, 2.35)}


def asset_library():
    return Path(os.environ.get('PCVE_ASSET_LIBRARY', str(ASSETS)))


def _image(path, non_color):
    image = bpy.data.images.load(str(path), check_existing=True)
    if non_color:
        image.colorspace_settings.name = 'Non-Color'
    return image


def honest_daylight(cfg):
    """Remove hidden helper lamps; real sky + sun through the real opening, with a portal."""
    spec = cfg['appearance']['room_finish']['lighting']
    scene = bpy.context.scene
    removed = []
    for name in HIDDEN_FILL_LIGHTS:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        removed.append({'name': name, 'type': obj.data.type, 'energy_w': obj.data.energy,
                        'visible_camera': obj.visible_camera, 'visible_glossy': obj.visible_glossy,
                        'location_m': [round(v, 4) for v in obj.matrix_world.translation]})
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data.users == 0:
            bpy.data.lights.remove(data)
    y0, y1 = WINDOW['y_m']
    z0, z1 = WINDOW['z_m']
    portal = bpy.data.lights.new('light portal in real window opening', 'AREA')
    portal.shape = 'RECTANGLE'
    portal.size = z1 - z0          # local X -> world Z
    portal.size_y = y1 - y0        # local Y -> world Y
    portal.cycles.is_portal = True
    obj = bpy.data.objects.new(portal.name, portal)
    scene.collection.objects.link(obj)
    obj.location = (WINDOW['wall_inner_x_m'] - .005, (y0 + y1) / 2, (z0 + z1) / 2)
    obj.rotation_euler = (0., -math.pi / 2, 0.)   # emits along +X, into the room
    background = scene.world.node_tree.nodes.get('Background')
    background.inputs['Strength'].default_value = spec['environment_strength']
    for light in scene.objects:
        if light.type == 'LIGHT' and light.data.type == 'SUN':
            light.data.energy = spec['sun_energy']
            light.data.angle = math.radians(spec['sun_angle_deg'])
    scene.view_settings.exposure = spec['exposure_ev']
    # A real room inter-reflects many times; with the fills gone, 4 diffuse bounces under-light it.
    scene.cycles.diffuse_bounces = spec['diffuse_bounces']
    remaining = [{'name': o.name, 'type': o.data.type, 'energy_w': o.data.energy,
                  'portal': bool(getattr(o.data.cycles, 'is_portal', False))}
                 for o in scene.objects if o.type == 'LIGHT']
    return {'removed_hidden_helper_lamps': removed, 'portal': {'size_m': [portal.size_y, portal.size],
            'center_m': list(obj.location), 'adds_energy': False}, 'environment_strength': spec['environment_strength'],
            'sun_energy': spec['sun_energy'], 'exposure_ev': spec['exposure_ev'], 'diffuse_bounces': spec['diffuse_bounces'], 'lights_after': remaining,
            'sources': 'HDRI sky seen through the open casement and one sun; no emitter hidden from the camera'}


def plaster_walls(cfg):
    """Scanned painted plaster (beige_wall_001) at real scale on walls and ceiling."""
    spec = cfg['appearance']['room_finish']['walls']
    root = asset_library() / spec['asset']
    material = bpy.data.materials['Warm white painted plaster']
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for node in list(nodes):
        if node.type in {'TEX_NOISE', 'BUMP', 'MAP_RANGE'}:
            nodes.remove(node)
    bsdf = nodes.get('Principled BSDF')
    coords = nodes.new('ShaderNodeTexCoord')
    scale = nodes.new('ShaderNodeVectorMath')
    scale.operation = 'SCALE'
    scale.inputs[3].default_value = 1 / spec['tile_m']
    links.new(coords.outputs['Object'], scale.inputs[0])

    def texture(stem, non_color):
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = _image(root / stem, non_color)
        tex.projection = 'BOX'
        tex.projection_blend = .2
        links.new(scale.outputs[0], tex.inputs['Vector'])
        return tex
    diffuse = texture(spec['files']['diffuse'], False)
    rough = texture(spec['files']['roughness'], True)
    normal = texture(spec['files']['normal'], True)
    # Keep the warm-white paint colour; the scan contributes only its relative unevenness.
    grey = nodes.new('ShaderNodeRGBToBW')
    links.new(diffuse.outputs['Color'], grey.inputs['Color'])
    level = nodes.new('ShaderNodeMapRange')
    level.inputs['From Min'].default_value = spec['scan_luminance_range'][0]
    level.inputs['From Max'].default_value = spec['scan_luminance_range'][1]
    level.inputs['To Min'].default_value = 1 - spec['tone_variation']
    level.inputs['To Max'].default_value = 1 + spec['tone_variation']
    links.new(grey.outputs['Val'], level.inputs['Value'])
    tint = nodes.new('ShaderNodeMix')
    tint.data_type = 'RGBA'
    tint.blend_type = 'MULTIPLY'
    tint.inputs['Factor'].default_value = 1.
    tint.inputs['A'].default_value = (*spec['paint_color_linear'], 1.)
    links.new(level.outputs['Result'], tint.inputs['B'])
    links.new(tint.outputs['Result'], bsdf.inputs['Base Color'])
    rough_range = nodes.new('ShaderNodeMapRange')
    rough_range.inputs['To Min'].default_value = spec['roughness'][0]
    rough_range.inputs['To Max'].default_value = spec['roughness'][1]
    links.new(rough.outputs['Color'], rough_range.inputs['Value'])
    links.new(rough_range.outputs['Result'], bsdf.inputs['Roughness'])
    normal_map = nodes.new('ShaderNodeNormalMap')
    normal_map.inputs['Strength'].default_value = spec['normal_strength']
    links.new(normal.outputs['Color'], normal_map.inputs['Color'])
    links.new(normal_map.outputs['Normal'], bsdf.inputs['Normal'])
    users = [o.name for o in bpy.data.objects if o.type == 'MESH' and material.name in [s.material.name for s in o.material_slots if s.material]]
    return {'material': material.name, 'scan': spec['asset'], 'tile_m': spec['tile_m'], 'objects': users,
            'paint_color_linear': spec['paint_color_linear'], 'normal_strength': spec['normal_strength']}


def sofa_textiles(cfg):
    """Visible weave relief and fabric sheen on the scanned linen; pillows use the same scan."""
    spec = cfg['appearance']['room_finish']['sofa']
    upholstery = bpy.data.materials['Oatmeal woven upholstery']
    nodes = upholstery.node_tree.nodes
    bsdf = nodes.get('Principled BSDF')
    for node in nodes:
        if node.type == 'NORMAL_MAP':
            node.inputs['Strength'].default_value = spec['upholstery_normal_strength']
        if node.type == 'MAP_RANGE':
            node.inputs['To Min'].default_value = spec['upholstery_roughness'][0]
            node.inputs['To Max'].default_value = spec['upholstery_roughness'][1]
    bsdf.inputs['Sheen Weight'].default_value = spec['sheen_weight']
    bsdf.inputs['Sheen Roughness'].default_value = spec['sheen_roughness']
    scans = {key: next(x.image for x in nodes if x.type == 'TEX_IMAGE' and key in x.image.name) for key in ['diff', 'rough', 'nor']}
    pillows = {}
    for material_name, color in spec['pillow_colors_linear'].items():
        pillow = bpy.data.materials[material_name]
        n = pillow.node_tree.nodes
        l = pillow.node_tree.links
        for node in list(n):
            if node.type in {'TEX_NOISE', 'BUMP', 'MAP_RANGE'}:
                n.remove(node)
        p = n.get('Principled BSDF')
        tc = n.new('ShaderNodeTexCoord')
        sc = n.new('ShaderNodeVectorMath')
        sc.operation = 'SCALE'
        sc.inputs[3].default_value = 1 / spec['linen_tile_m']
        l.new(tc.outputs['Object'], sc.inputs[0])
        textures = {}
        for key, image in scans.items():
            tex = n.new('ShaderNodeTexImage')
            tex.image = image
            tex.projection = 'BOX'
            tex.projection_blend = .3
            l.new(sc.outputs[0], tex.inputs['Vector'])
            textures[key] = tex
        # The scan supplies only the relative weave contrast; the pillow keeps its base colour.
        grey = n.new('ShaderNodeRGBToBW')
        l.new(textures['diff'].outputs['Color'], grey.inputs['Color'])
        level = n.new('ShaderNodeMapRange')
        level.inputs['From Min'].default_value = spec['linen_luminance_range'][0]
        level.inputs['From Max'].default_value = spec['linen_luminance_range'][1]
        level.inputs['To Min'].default_value = 1 - spec['pillow_weave_contrast']
        level.inputs['To Max'].default_value = 1 + spec['pillow_weave_contrast']
        l.new(grey.outputs['Val'], level.inputs['Value'])
        tint = n.new('ShaderNodeMix')
        tint.data_type = 'RGBA'
        tint.blend_type = 'MULTIPLY'
        tint.inputs['Factor'].default_value = 1.
        tint.inputs['A'].default_value = (*color, 1.)
        l.new(level.outputs['Result'], tint.inputs['B'])
        l.new(tint.outputs['Result'], p.inputs['Base Color'])
        rough = n.new('ShaderNodeMapRange')
        rough.inputs['To Min'].default_value = spec['upholstery_roughness'][0]
        rough.inputs['To Max'].default_value = spec['upholstery_roughness'][1]
        l.new(textures['rough'].outputs['Color'], rough.inputs['Value'])
        l.new(rough.outputs['Result'], p.inputs['Roughness'])
        nm = n.new('ShaderNodeNormalMap')
        nm.inputs['Strength'].default_value = spec['upholstery_normal_strength']
        l.new(textures['nor'].outputs['Color'], nm.inputs['Color'])
        l.new(nm.outputs['Normal'], p.inputs['Normal'])
        p.inputs['Sheen Weight'].default_value = spec['sheen_weight']
        p.inputs['Sheen Roughness'].default_value = spec['sheen_roughness']
        pillows[material_name] = {'color_linear': color, 'scan': 'polyhaven/rough_linen', 'tile_m': spec['linen_tile_m']}
    return {'upholstery': upholstery.name, 'normal_strength': spec['upholstery_normal_strength'], 'roughness': spec['upholstery_roughness'],
            'sheen_weight': spec['sheen_weight'], 'pillows': pillows}


def refine_template(cfg):
    """Apply the finishing pass to an opened packed template. Returns the appearance ledger."""
    ledger = {'revision': cfg['appearance']['room_finish']['revision']}
    ledger['lighting'] = honest_daylight(cfg)
    ledger['walls'] = plaster_walls(cfg)
    ledger['sofa'] = sofa_textiles(cfg)
    return ledger
