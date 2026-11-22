"""Furniture-scale domestic context and restrained surface wear, appearance only."""
from __future__ import annotations
from pathlib import Path
import bpy
from look_domino_chain import material,box,set_socket
from natural_card_table import node_noise,mapped
from card_table_environment import metre_uv

REVISION='daylight_home'

def daylight_resin(cfg):
    mat=material('Handled ivory resin - daylight satin',cfg['color_linear'],.27)
    n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF')
    set_socket(bs,'IOR',1.50);set_socket(bs,'Coat Weight',.04);set_socket(bs,'Coat Roughness',.29)
    set_socket(bs,'Subsurface Weight',.008);set_socket(bs,'Subsurface Scale',.00020)
    set_socket(bs,'Subsurface Radius',(1,.61,.38))
    coord=n.new('ShaderNodeTexCoord');info=n.new('ShaderNodeObjectInfo')
    broad=node_noise(n,l,coord.outputs['Object'],185,3);broad.noise_dimensions='4D';l.new(info.outputs['Random'],broad.inputs['W'])
    tone=mapped(n,l,broad.outputs['Fac'],.93,1.035)
    individual=mapped(n,l,info.outputs['Random'],.955,1.035)
    mult=n.new('ShaderNodeMath');mult.operation='MULTIPLY';l.new(tone,mult.inputs[0]);l.new(individual,mult.inputs[1])
    color=n.new('ShaderNodeMixRGB');color.blend_type='MULTIPLY';color.inputs[0].default_value=1;color.inputs[1].default_value=cfg['color_linear']
    l.new(mult.outputs[0],color.inputs[2]);l.new(color.outputs[0],bs.inputs['Base Color'])
    handled=node_noise(n,l,coord.outputs['Object'],580,2)
    rough=mapped(n,l,handled.outputs['Fac'],.205,.345)
    stretch=n.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY';stretch.inputs[1].default_value=(380,4100,290)
    l.new(coord.outputs['Object'],stretch.inputs[0]);marks=node_noise(n,l,stretch.outputs['Vector'],1,2)
    marks.noise_dimensions='4D';l.new(info.outputs['Random'],marks.inputs['W'])
    scratches=mapped(n,l,marks.outputs['Fac'],0,.075,.69,.81)
    add=n.new('ShaderNodeMath');add.operation='ADD';l.new(rough,add.inputs[0]);l.new(scratches,add.inputs[1]);l.new(add.outputs[0],bs.inputs['Roughness'])
    grain=node_noise(n,l,coord.outputs['Object'],12500,2)
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.13;bump.inputs['Distance'].default_value=.0000025
    l.new(grain.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],bs.inputs['Normal'])
    mat['surface_note']='Only reflectance, shallow normal detail and handling polish. Imported tile vertices, pips, dimensions and collision proxies are unchanged.'
    return mat

def felt_nap(cfg):
    mat=bpy.data.materials['Brushed wool baize - fine fibres and restrained wear'];n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF')
    set_socket(bs,'Sheen Weight',.22);set_socket(bs,'Sheen Roughness',.63)
    old_color=bs.inputs['Base Color'].links[0].from_socket
    old_normal=bs.inputs['Normal'].links[0].from_socket
    coord=n.new('ShaderNodeTexCoord');geometry=n.new('ShaderNodeNewGeometry')
    stretch=n.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY';stretch.inputs[1].default_value=(120,12,1)
    l.new(coord.outputs['Object'],stretch.inputs[0]);brushing=node_noise(n,l,stretch.outputs['Vector'],1,3)
    brushing.name='Felt directional nap at centimetre scale'
    nap=mapped(n,l,brushing.outputs['Fac'],.84,1.075)
    subtract=n.new('ShaderNodeVectorMath');subtract.operation='SUBTRACT';subtract.inputs[1].default_value=(-.025,.025,.75);l.new(geometry.outputs['Position'],subtract.inputs[0])
    scale=n.new('ShaderNodeVectorMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=(1/.22,1/.15,0);l.new(subtract.outputs['Vector'],scale.inputs[0])
    length=n.new('ShaderNodeVectorMath');length.operation='LENGTH';l.new(scale.outputs['Vector'],length.inputs[0])
    wear=mapped(n,l,length.outputs['Value'],1.105,.985,0,1.6)
    factor=n.new('ShaderNodeMath');factor.operation='MULTIPLY';l.new(nap,factor.inputs[0]);l.new(wear,factor.inputs[1])
    tone=n.new('ShaderNodeMixRGB');tone.blend_type='MULTIPLY';tone.inputs[0].default_value=1;l.new(old_color,tone.inputs[1]);l.new(factor.outputs[0],tone.inputs[2]);l.new(tone.outputs[0],bs.inputs['Base Color'])
    rough=mapped(n,l,brushing.outputs['Fac'],.73,.90);l.new(rough,bs.inputs['Roughness'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.19;bump.inputs['Distance'].default_value=.000019
    l.new(brushing.outputs['Fac'],bump.inputs['Height']);l.new(old_normal,bump.inputs['Normal']);l.new(bump.outputs['Normal'],bs.inputs['Normal'])
    for node in n:
        if node.bl_idname=='ShaderNodeNormalMap':node.inputs['Strength'].default_value=.44
    return {'felt_nap_revision':'centimetre_directional_handling','felt_wear_center_xy_m':[-.025,.025],
            'felt_wear_ellipse_radii_m':[.22,.15],'felt_wear_is_shader_only':True}

def paper_edges():
    mat=bpy.data.materials['Exposed used paper card edges'];n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF')
    info=n.new('ShaderNodeObjectInfo');factor=mapped(n,l,info.outputs['Random'],.925,1.055)
    tint=n.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1;tint.inputs[1].default_value=(.58,.565,.51,1)
    l.new(factor,tint.inputs[2]);l.new(tint.outputs[0],bs.inputs['Base Color'])
    bs.inputs['Roughness'].default_value=.77
    return {'paper_edge_tone_variation':[.925,1.055],'paper_support_geometry_preserved':True}

def furniture_and_wall(cfg):
    wood=bpy.data.materials['Satin oak card table rail - physical grain and handled edge'];n=wood.node_tree.nodes;l=wood.node_tree.links;bs=n.get('Principled BSDF')
    old=bs.inputs['Roughness'].links[0].from_socket
    coord=n.new('ShaderNodeTexCoord');polish=node_noise(n,l,coord.outputs['Object'],80,3)
    factor=mapped(n,l,polish.outputs['Fac'],.80,1.12)
    mult=n.new('ShaderNodeMath');mult.operation='MULTIPLY';l.new(old,mult.inputs[0]);l.new(factor,mult.inputs[1]);l.new(mult.outputs[0],bs.inputs['Roughness'])
    set_socket(bs,'Coat Weight',.08)
    for node in n:
        if node.bl_idname=='ShaderNodeNormalMap':node.inputs['Strength'].default_value=.19
    if 'back_wall_y_m' in cfg['appearance']['room']:
        bpy.data.objects['Home dining room back wall'].location.y=cfg['appearance']['room']['back_wall_y_m']
    wall=bpy.data.materials['Soft warm home dining room plaster'];n=wall.node_tree.nodes;l=wall.node_tree.links;bs=n.get('Principled BSDF')
    coord=n.new('ShaderNodeTexCoord');paint=node_noise(n,l,coord.outputs['Object'],450,2)
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.18;bump.inputs['Distance'].default_value=.00012
    l.new(paint.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],bs.inputs['Normal'])
    return wood

def chair(cfg,wood):
    # A real-size chair behind the table, with its seat tucked under the rail.
    # All props are static and remote from the complete domino motion envelope.
    anchor=bpy.data.objects.new('Domestic oak dining chair - 430 x 430 x 930 mm',None);bpy.context.collection.objects.link(anchor)
    center=cfg['appearance']['card_table'].get('background_chair_center_xy_m',[.18,.94])
    anchor.location=(*center,0);anchor.rotation_euler[2]=-.055
    def part(name,location,dimensions,bevel=.0015):
        obj=box('Chair '+name,location,dimensions,wood,bevel);metre_uv(obj);obj.parent=anchor;obj['static_decorative_prop']=True;return obj
    part('rounded timber seat',(0,0,.4475),(.43,.43,.025),.008)
    for x in [-.177,.177]:
        part('front leg',(x,-.17,.2175),(.029,.029,.435),.0015)
        part('rear leg and back post',(x,.17,.4575),(.029,.029,.915),.002)
    part('upper curved-edge back rail',(0,.17,.9075),(.39,.032,.045),.008)
    part('lower back rail',(0,.17,.595),(.39,.028,.035),.004)
    for x in [-.112,-.037,.037,.112]:part('slender back slat',(x,.17,.748),(.026,.019,.28),.002)
    return {'background_chair_dimensions_m':[.43,.43,.93],'background_chair_seat_height_m':.46,
            'background_chair_center_xy_m':list(center),'background_chair_geometry':'Procedural metre-scale oak furniture, not a scanned asset.'}


def imported_chair(cfg):
    root=Path(__file__).resolve().parents[4]
    asset=root/'assets/polyhaven/painted_wooden_chair_01/painted_wooden_chair_01_2k.blend'
    with bpy.data.libraries.load(str(asset),link=False) as (source,target):
        target.objects=list(source.objects)
    objects=[o for o in target.objects if o and o.type=='MESH'];assert len(objects)==1
    obj=objects[0];bpy.context.collection.objects.link(obj)
    original_name=obj.name;obj.name='PolyHaven worn painted dining chair - original metre scale'
    for mat in obj.data.materials:
        if not mat or not mat.use_nodes:continue
        for node in mat.node_tree.nodes:
            if node.bl_idname=='ShaderNodeTexImage' and node.image:
                node.image.filepath=str(asset.parent/'textures'/Path(node.image.filepath).name);node.image.reload()
    anchor=bpy.data.objects.new('Painted dining chair placement',None);bpy.context.collection.objects.link(anchor)
    obj.parent=anchor
    anchor.rotation_euler[2]=cfg['appearance']['card_table'].get('background_chair_yaw_rad',-.055)
    bpy.context.view_layer.update()
    def bounds():
        deps=bpy.context.evaluated_depsgraph_get();ev=obj.evaluated_get(deps);mesh=ev.to_mesh();points=[ev.matrix_world@v.co for v in mesh.vertices]
        lo=[min(p[k] for p in points) for k in range(3)];hi=[max(p[k] for p in points) for k in range(3)];ev.to_mesh_clear();return lo,hi
    lo,hi=bounds();center=cfg['appearance']['card_table']['background_chair_center_xy_m']
    anchor.location=(center[0]-(lo[0]+hi[0])/2,center[1]-(lo[1]+hi[1])/2,.000005-lo[2])
    obj['static_decorative_prop']=True;obj['source_asset']='Painted Wooden Chair 01 / Kuutti Siitonen / Poly Haven / CC0'
    obj['source_object_name']=original_name
    bpy.context.view_layer.update();lo,hi=bounds()
    return {'background_chair_asset':'Poly Haven Painted Wooden Chair 01 / CC0',
            'background_chair_original_scale_preserved':True,'background_chair_original_object':original_name,
            'background_chair_world_bounds_m':[lo,hi],'background_chair_dimensions_m':[hi[k]-lo[k] for k in range(3)],
            'background_chair_center_xy_m':list(center),'background_chair_floor_gap_m':lo[2],
            'background_chair_geometry':'Original supplied mesh, UVs and four PBR maps; no scan-method claim.'}

def enhance_environment(cfg,ledger):
    assert cfg['appearance']['room'].get('domestic_revision')==REVISION
    wood=furniture_and_wall(cfg)
    kind=cfg['appearance']['card_table'].get('background_chair_asset')
    furniture=({'background_chair_present':False} if kind=='none' else imported_chair(cfg) if kind=='painted_wooden_chair_01' else chair(cfg,wood))
    return {**ledger,**felt_nap(cfg),**paper_edges(),**furniture,
            'domestic_revision':REVISION,
            'appearance_note':'Fixed-camera photographic context, directional baize nap, satin resin and worn varnish. Solver data and existing paper support geometry are retained.'}
