"""Coated playing-card stock and original engraved back; appearance only."""
from pathlib import Path
import math
import bpy
from look_domino_chain import set_socket
from natural_card_table import node_noise, mapped
ROOT=Path(__file__).resolve().parents[4]
REVISION='coated_stock'
BACK=ROOT/'assets/pcve/domino_chain_cards/engraved_navy_back.png'
PRINTED=['Printed King of Hearts - Byron Knoll / Public Domain',
         'Printed Eight of Spades - Byron Knoll / Public Domain',
         'Original navy geometric card back']

def math_node(n,l,op,a,b=None,name=None):
    node=n.new('ShaderNodeMath');node.operation=op
    if name:node.name=name
    for value,socket in [(a,node.inputs[0]),(b,node.inputs[1])]:
        if value is None:continue
        if isinstance(value,(int,float)):socket.default_value=value
        else:l.new(value,socket)
    return node.outputs[0]

def mix(n,l,a,b,factor,name):
    node=n.new('ShaderNodeMixRGB');node.name=name;node.blend_type='MIX'
    for value,socket in [(factor,node.inputs[0]),(a,node.inputs[1]),(b,node.inputs[2])]:
        if isinstance(value,(int,float,tuple,list)):socket.default_value=value
        else:l.new(value,socket)
    return node.outputs['Color']

def multiply_color(n,l,a,b,name):
    node=n.new('ShaderNodeMixRGB');node.name=name;node.blend_type='MULTIPLY';node.inputs[0].default_value=1
    for value,socket in [(a,node.inputs[1]),(b,node.inputs[2])]:
        if isinstance(value,(tuple,list,int,float)):socket.default_value=value
        else:l.new(value,socket)
    return node.outputs['Color']

def reset_shader(mat):
    n=mat.node_tree.nodes;l=mat.node_tree.links;n.clear()
    bs=n.new('ShaderNodeBsdfPrincipled');out=n.new('ShaderNodeOutputMaterial')
    l.new(bs.outputs['BSDF'],out.inputs['Surface'])
    return n,l,bs

def print_finish(mat):
    image=next(node.image for node in mat.node_tree.nodes if node.bl_idname=='ShaderNodeTexImage' and node.image)
    is_back=mat.name==PRINTED[2]
    if is_back:image=bpy.data.images.load(str(BACK),check_existing=True)
    n,l,bs=reset_shader(mat)
    set_socket(bs,'IOR',1.47);set_socket(bs,'Specular IOR Level',.40)
    set_socket(bs,'Coat Weight',.10);set_socket(bs,'Coat Roughness',.31);set_socket(bs,'Coat IOR',1.47)
    coord=n.new('ShaderNodeTexCoord');coord.name='Card coordinates in actual metres'
    info=n.new('ShaderNodeObjectInfo')
    tex=n.new('ShaderNodeTexImage');tex.image=image;tex.interpolation='Cubic'
    tex.name='Original engraved back' if is_back else 'Public-domain printed face'
    tex.extension='EXTEND';l.new(coord.outputs['UV'],tex.inputs['Vector'])
    stock=node_noise(n,l,coord.outputs['Object'],88,3)
    stock.name='Low contrast stock variation';stock.noise_dimensions='4D';l.new(info.outputs['Random'],stock.inputs['W'])
    tone=mapped(n,l,stock.outputs['Fac'],.975,1.015)
    print_color=multiply_color(n,l,tex.outputs['Color'],(.805,.789,.745,1),'Slightly warm unbleached stock')
    print_color=multiply_color(n,l,print_color,tone,'Restrained stock tone')

    # The outer 0.6 mm of a handled card has a little cut-edge wear. UV distances
    # are converted to metres, so this treatment cannot become a giant border.
    sep=n.new('ShaderNodeSeparateXYZ');l.new(coord.outputs['UV'],sep.inputs[0])
    du=math_node(n,l,'MINIMUM',sep.outputs['X'],math_node(n,l,'SUBTRACT',1,sep.outputs['X']))
    dv=math_node(n,l,'MINIMUM',sep.outputs['Y'],math_node(n,l,'SUBTRACT',1,sep.outputs['Y']))
    edge=math_node(n,l,'MINIMUM',math_node(n,l,'MULTIPLY',du,.063),math_node(n,l,'MULTIPLY',dv,.088),'Distance to die-cut edge in metres')
    wear=mapped(n,l,edge,.15,0,0,.0006)
    cut_noise=node_noise(n,l,coord.outputs['Object'],2400,2)
    wear=math_node(n,l,'MULTIPLY',wear,mapped(n,l,cut_noise.outputs['Fac'],.4,1))
    color=mix(n,l,print_color,(.51,.455,.35,1),wear,'Very slight handling on white border')
    l.new(color,bs.inputs['Base Color'])

    polish=node_noise(n,l,coord.outputs['Object'],120,2);polish.name='Broad finger-polished satin coating'
    rough=mapped(n,l,polish.outputs['Fac'],.285,.425)
    l.new(rough,bs.inputs['Roughness'])
    # Shallow emboss in the coating, never displaced card geometry. This is
    # an artistic stock finish, not a measured reproduction of a named brand.
    local=n.new('ShaderNodeSeparateXYZ');l.new(coord.outputs['Object'],local.inputs[0])
    waves=[]
    for axis in ['X','Y']:
        phase=math_node(n,l,'MULTIPLY',local.outputs[axis],2*math.pi/.00032)
        wave=math_node(n,l,'SINE',phase)
        waves.append(math_node(n,l,'POWER',math_node(n,l,'ABSOLUTE',wave),3))
    emboss=math_node(n,l,'MULTIPLY',waves[0],waves[1],'320 micron shallow coating emboss')
    bump=n.new('ShaderNodeBump');bump.name='Coating emboss 1.6 micron';bump.inputs['Strength'].default_value=.22;bump.inputs['Distance'].default_value=.0000016
    l.new(emboss,bump.inputs['Height'])
    fibres=node_noise(n,l,coord.outputs['Object'],18000,2)
    micro=n.new('ShaderNodeBump');micro.name='Fine sealed paper fibres';micro.inputs['Strength'].default_value=.10;micro.inputs['Distance'].default_value=.0000011
    l.new(fibres.outputs['Fac'],micro.inputs['Height']);l.new(bump.outputs['Normal'],micro.inputs['Normal'])
    l.new(micro.outputs['Normal'],bs.inputs['Normal']);l.new(micro.outputs['Normal'],bs.inputs['Coat Normal'])
    mat['card_finish_revision']=REVISION
    mat['surface_note']='Thin satin coating over printed paper, shallow emboss and modest edge handling; no displacement or support changes.'

def cut_edge_finish():
    mat=bpy.data.materials['Exposed used paper card edges'];n,l,bs=reset_shader(mat)
    set_socket(bs,'IOR',1.47);set_socket(bs,'Specular IOR Level',.24)
    bs.inputs['Roughness'].default_value=.79
    coord=n.new('ShaderNodeTexCoord');info=n.new('ShaderNodeObjectInfo')
    individual=mapped(n,l,info.outputs['Random'],.87,1.045)
    grain=node_noise(n,l,coord.outputs['Object'],3100,2)
    tone=math_node(n,l,'MULTIPLY',individual,mapped(n,l,grain.outputs['Fac'],.93,1.045))
    paper=multiply_color(n,l,(.535,.513,.453,1),tone,'Separate warm cut paper sheets')
    sep=n.new('ShaderNodeSeparateXYZ');l.new(coord.outputs['Object'],sep.inputs[0])
    core=math_node(n,l,'ABSOLUTE',math_node(n,l,'SUBTRACT',sep.outputs['Z'],.00014))
    core=mapped(n,l,core,.34,0,.000016,.000038)
    color=mix(n,l,paper,(.13,.126,.105,1),core,'Subtle dark adhesive/core band inside each 0.28 mm sheet')
    l.new(color,bs.inputs['Base Color'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.14;bump.inputs['Distance'].default_value=.000002
    l.new(grain.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],bs.inputs['Normal'])
    mat['card_finish_revision']=REVISION
    mat['surface_note']='Cut-stock shade and a fine core stripe; original 52 closed laminas, spacing and normals retained.'

def apply_card_finish(cfg,ledger):
    rev=cfg['appearance']['card_table'].get('paper_finish_revision')
    if rev is None:return ledger
    if rev!=REVISION:raise ValueError('Unknown card finish revision: '+str(rev))
    for name in PRINTED:print_finish(bpy.data.materials[name])
    cut_edge_finish()
    old=bpy.data.images.get('back_original.png')
    if old and old.users==0:bpy.data.images.remove(old)
    return {**ledger,'paper_finish_revision':REVISION,
            'card_back':'Original two-way engraved navy ornament; 2.5 mm white border',
            'card_back_asset':'assets/pcve/domino_chain_cards/engraved_navy_back.svg',
            'card_stock_finish':'Satin coated stock with 320 micron shallow emboss, modest edge handling and cut-edge core band',
            'coating_emboss_depth_m':.0000016,'coating_emboss_pitch_m':.00032,
            'paper_finish_geometry_preserved':True,'paper_finish_affects_physics':False}
