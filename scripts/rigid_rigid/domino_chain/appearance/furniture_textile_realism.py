"""Appearance-only photographic linen material shared by the static curtains (gathered_linen.py)."""
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[4]

def linen_material(cfg):
    from look_domino_chain import material,set_socket
    mat=material('Linen drapes | cream photographic woven fibres',(.72,.68,.59,1),.88)
    n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF');out=n.get('Material Output')
    set_socket(bs,'IOR',1.46);set_socket(bs,'Sheen Weight',.28);set_socket(bs,'Sheen Roughness',.82)
    set_socket(bs,'Subsurface Weight',.018);set_socket(bs,'Subsurface Scale',.0003)
    uv=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeMapping');mapping.name='Real fabric arc-length per UV axis'
    l.new(uv.outputs['UV'],mapping.inputs['Vector'])
    def tex(name,colour=False):
        t=n.new('ShaderNodeTexImage');t.image=bpy.data.images.load(str(ROOT/'assets/polyhaven/rough_linen'/name),check_existing=True)
        t.image.colorspace_settings.name='sRGB' if colour else 'Non-Color';l.new(mapping.outputs['Vector'],t.inputs['Vector']);return t
    albedo=tex('rough_linen_diff_2k.jpg',True);normal=tex('rough_linen_nor_gl_2k.exr');rough=tex('rough_linen_rough_2k.jpg');height=tex('rough_linen_disp_2k.exr')
    gray=n.new('ShaderNodeRGBToBW');l.new(albedo.outputs['Color'],gray.inputs[0])
    tone=n.new('ShaderNodeMapRange');tone.clamp=True;tone.inputs['From Min'].default_value=.02;tone.inputs['From Max'].default_value=.30
    tone.inputs['To Min'].default_value=.82;tone.inputs['To Max'].default_value=1.08;l.new(gray.outputs[0],tone.inputs['Value'])
    dye=n.new('ShaderNodeMixRGB');dye.blend_type='MULTIPLY';dye.inputs[0].default_value=1;dye.inputs[1].default_value=(.72,.68,.59,1)
    l.new(tone.outputs['Result'],dye.inputs[2]);l.new(dye.outputs[0],bs.inputs['Base Color'])
    r=n.new('ShaderNodeMapRange');r.clamp=True;r.inputs['From Min'].default_value=.45;r.inputs['From Max'].default_value=.95
    r.inputs['To Min'].default_value=.78;r.inputs['To Max'].default_value=.96;l.new(rough.outputs['Color'],r.inputs['Value']);l.new(r.outputs['Result'],bs.inputs['Roughness'])
    nm=n.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.55;l.new(normal.outputs['Color'],nm.inputs['Color'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.30;bump.inputs['Distance'].default_value=.00015
    l.new(height.outputs['Color'],bump.inputs['Height']);l.new(nm.outputs['Normal'],bump.inputs['Normal']);l.new(bump.outputs[0],bs.inputs['Normal'])
    trans=n.new('ShaderNodeBsdfTranslucent');l.new(dye.outputs[0],trans.inputs['Color']);l.new(bump.outputs[0],trans.inputs['Normal'])
    mix=n.new('ShaderNodeMixShader');mix.inputs[0].default_value=cfg['appearance']['room']['curtain_translucent_weight']
    l.new(bs.outputs[0],mix.inputs[1]);l.new(trans.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],out.inputs['Surface'])
    mat['material_note']='Opaque yarn surface plus diffuse thin-cloth transmission. No alpha, additive transparency, emissive glow or glass transmission.'
    return mat,mapping
