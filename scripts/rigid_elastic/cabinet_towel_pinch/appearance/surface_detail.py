"""Remote Blender PBR finishing; all length scales below are in metres."""
import bpy
from geometry import LAYOUT

def mat(name):
    m=bpy.data.materials.new(name);m.use_nodes=True
    return m,m.node_tree.nodes,m.node_tree.links,m.node_tree.nodes.get('Principled BSDF')

def noise(n,l,vector,scale,detail=3):
    a=n.new('ShaderNodeTexNoise');a.inputs['Scale'].default_value=scale;a.inputs['Detail'].default_value=detail
    l.new(vector,a.inputs['Vector']);return a.outputs['Fac']

def ramp(n,l,value,low,high):
    a=n.new('ShaderNodeValToRGB');a.color_ramp.elements[0].color=(*low,1);a.color_ramp.elements[1].color=(*high,1)
    l.new(value,a.inputs['Fac']);return a.outputs['Color']

def wood(source):
    images=[a.image for a in source.node_tree.nodes if a.type=='TEX_IMAGE' and a.image]
    image=next(i for i in images if 'diffuse' in i.name.lower() or 'albedo' in i.name.lower() or 'base' in i.name.lower())
    normal=next(i for i in images if 'normal' in i.name.lower())
    m,n,l,b=mat('Pale oak · open pores and photographic growth rings')
    tex=n.new('ShaderNodeTexCoord');uv=tex.outputs['UV']
    im=n.new('ShaderNodeTexImage');im.image=image;l.new(uv,im.inputs['Vector'])
    tone=n.new('ShaderNodeHueSaturation');tone.inputs['Saturation'].default_value=.78;tone.inputs['Value'].default_value=.88
    l.new(im.outputs['Color'],tone.inputs['Color']);l.new(tone.outputs['Color'],b.inputs['Base Color'])
    ni=n.new('ShaderNodeTexImage');ni.image=normal;l.new(uv,ni.inputs['Vector']);nm=n.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.25
    l.new(ni.outputs['Color'],nm.inputs['Color'])
    mapping=n.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY';mapping.inputs[1].default_value=(45,3,1);l.new(uv,mapping.inputs[0])
    pores=noise(n,l,mapping.outputs[0],32,2)
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.15;bump.inputs['Distance'].default_value=.00012
    l.new(pores,bump.inputs['Height']);l.new(nm.outputs[0],bump.inputs['Normal']);l.new(bump.outputs[0],b.inputs['Normal'])
    l.new(ramp(n,l,noise(n,l,uv,34),(.38,)*3,(.68,)*3),b.inputs['Roughness'])
    b.inputs['Coat Weight'].default_value=.07;b.inputs['Coat Roughness'].default_value=.5
    return m

def cotton(source):
    images=[a.image for a in source.node_tree.nodes if a.type=='TEX_IMAGE' and a.image]
    base=next(i for i in images if 'Base_color' in i.name);normal=next(i for i in images if 'Normal' in i.name)
    m,n,l,b=mat('Unbleached cotton · woven navy bands, sewn hem and fibre nap')
    b.inputs['Sheen Weight'].default_value=.45;b.inputs['Sheen Roughness'].default_value=.85;b.inputs['Roughness'].default_value=.88
    tc=n.new('ShaderNodeTexCoord');uv=tc.outputs['UV'];xy=n.new('ShaderNodeSeparateXYZ');l.new(uv,xy.inputs[0])
    mapping=n.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY';mapping.inputs[1].default_value=(2.5,4.8,1);l.new(uv,mapping.inputs[0])
    im=n.new('ShaderNodeTexImage');im.image=base;l.new(mapping.outputs[0],im.inputs['Vector'])
    bw=n.new('ShaderNodeRGBToBW');l.new(im.outputs['Color'],bw.inputs[0])
    colour=ramp(n,l,bw.outputs[0],(.30,.25,.17),(.86,.79,.62))
    def math(op,a,bval):
        o=n.new('ShaderNodeMath');o.operation=op
        if hasattr(a,'node'):l.new(a,o.inputs[0])
        else:o.inputs[0].default_value=a
        if hasattr(bval,'node'):l.new(bval,o.inputs[1])
        else:o.inputs[1].default_value=bval
        return o.outputs[0]
    mask=None
    for lo,hi in [(.07,.092),(.113,.124),(.876,.887),(.908,.93)]:
        band=math('MULTIPLY',math('GREATER_THAN',xy.outputs['X'],lo),math('LESS_THAN',xy.outputs['X'],hi))
        mask=band if mask is None else math('MAXIMUM',mask,band)
    mix=n.new('ShaderNodeMixRGB');l.new(mask,mix.inputs[0]);l.new(colour,mix.inputs[1]);mix.inputs[2].default_value=(.025,.052,.061,1)
    border=math('MAXIMUM',math('LESS_THAN',xy.outputs['X'],.022),math('GREATER_THAN',xy.outputs['X'],.978))
    border=math('MAXIMUM',border,math('LESS_THAN',xy.outputs['Y'],.012));border=math('MAXIMUM',border,math('GREATER_THAN',xy.outputs['Y'],.988))
    hem=n.new('ShaderNodeMixRGB');hem.blend_type='MULTIPLY';l.new(border,hem.inputs[0]);l.new(mix.outputs[0],hem.inputs[1]);hem.inputs[2].default_value=(.72,.67,.58,1)
    l.new(hem.outputs[0],b.inputs['Base Color'])
    ni=n.new('ShaderNodeTexImage');ni.image=normal;l.new(mapping.outputs[0],ni.inputs['Vector'])
    sp=n.new('ShaderNodeSeparateColor');co=n.new('ShaderNodeCombineColor');l.new(ni.outputs[0],sp.inputs[0])
    l.new(sp.outputs['Red'],co.inputs['Red']);l.new(sp.outputs['Blue'],co.inputs['Blue']);l.new(math('SUBTRACT',1,sp.outputs['Green']),co.inputs['Green'])
    nm=n.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.7;l.new(co.outputs[0],nm.inputs['Color'])
    # Crossed threads at 0.8 mm pitch, with a stitched 6--7 mm folded hem.
    a=math('SINE',math('MULTIPLY',xy.outputs['X'],2*3.141592653589793*LAYOUT['towel_width']/.0008),0)
    c=math('SINE',math('MULTIPLY',xy.outputs['Y'],2*3.141592653589793*LAYOUT['towel_length']/.0008),0)
    weave=math('MULTIPLY',a,c);height=math('ADD',weave,math('MULTIPLY',border,1.4))
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.38;bump.inputs['Distance'].default_value=.00019
    l.new(height,bump.inputs['Height']);l.new(nm.outputs[0],bump.inputs['Normal']);l.new(bump.outputs[0],b.inputs['Normal'])
    return m

def stone():
    m,n,l,b=mat('Honed warm limestone · mineral inclusions and micro pits')
    tc=n.new('ShaderNodeTexCoord');p=tc.outputs['Object']
    low=noise(n,l,p,8,5);base=ramp(n,l,low,(.22,.21,.175),(.48,.46,.40))
    grains=n.new('ShaderNodeTexVoronoi');grains.inputs['Scale'].default_value=340;l.new(p,grains.inputs['Vector'])
    mask=n.new('ShaderNodeMath');mask.operation='LESS_THAN';mask.inputs[1].default_value=.18;l.new(grains.outputs['Distance'],mask.inputs[0])
    chips=n.new('ShaderNodeMixRGB');l.new(mask.outputs[0],chips.inputs[0]);l.new(base,chips.inputs[1]);chips.inputs[2].default_value=(.12,.115,.105,1)
    l.new(chips.outputs[0],b.inputs['Base Color'])
    fine=noise(n,l,p,720,2);l.new(ramp(n,l,fine,(.42,)*3,(.65,)*3),b.inputs['Roughness'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.24;bump.inputs['Distance'].default_value=.00015
    l.new(fine,bump.inputs['Height']);l.new(bump.outputs[0],b.inputs['Normal']);return m

def brushed_metal():
    m,n,l,b=mat('Brushed steel · directional machining and fingerprint roughness')
    b.inputs['Base Color'].default_value=(.45,.49,.51,1);b.inputs['Metallic'].default_value=.96
    t=n.new('ShaderNodeTexCoord');scale=n.new('ShaderNodeVectorMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=(800,800,12)
    l.new(t.outputs['Object'],scale.inputs[0]);f=noise(n,l,scale.outputs[0],8,2)
    l.new(ramp(n,l,f,(.22,)*3,(.42,)*3),b.inputs['Roughness'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.22;bump.inputs['Distance'].default_value=.000025
    l.new(f,bump.inputs['Height']);l.new(bump.outputs[0],b.inputs['Normal'])
    a=b.inputs.get('Anisotropic IOR Level')
    if a is not None:a.default_value=.42
    return m

def ceramic(name,colour,roughness):
    m,n,l,b=mat(name);b.inputs['Base Color'].default_value=(*colour,1)
    t=n.new('ShaderNodeTexCoord');f=noise(n,l,t.outputs['Object'],90,3)
    l.new(ramp(n,l,f,(roughness-.07,)*3,(roughness+.1,)*3),b.inputs['Roughness'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12;bump.inputs['Distance'].default_value=.00009
    l.new(f,bump.inputs['Height']);l.new(bump.outputs[0],b.inputs['Normal']);return m
