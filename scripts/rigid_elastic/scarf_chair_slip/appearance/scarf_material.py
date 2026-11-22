"""Use the licensed scarf model's fabric on the native cloth pattern."""
import bpy
from common import LAYOUT,ASSETS
ASSET_KEY='scarf_hanging'
def cotton(length):
 path=ASSETS/ASSET_KEY/'asset.blend'
 with bpy.data.libraries.load(str(path),link=False)as(src,dst):dst.materials=src.materials
 mats=[m for m in dst.materials if m and m.use_nodes]
 if not mats:raise RuntimeError('Scarf asset contains no node material')
 original=next((m for m in mats if 'body'in m.name.lower()),mats[0]);m=original.copy();m.name='Cotton scarf / licensed hanging-scarf fabric'
 nodes=m.node_tree.nodes;links=m.node_tree.links;bs=next((n for n in nodes if n.type=='BSDF_PRINCIPLED'),None)
 if bs is None:raise RuntimeError('Inspect the original scarf node network before adaptation')
 # Keep texture relief optical; never displace the native render surface.
 for output in [n for n in nodes if n.type=='OUTPUT_MATERIAL']:
  for link in list(output.inputs['Displacement'].links):links.remove(link)
 uv=nodes.new('ShaderNodeTexCoord')
 # The author baked the textile into two narrow panels in a larger atlas.
 # Use the clean left body panel at equal texels/metre along warp and weft.
 atlas_u0=.029;atlas_du=.165;atlas_dv=atlas_du*length/LAYOUT['width']
 atlas_scale=nodes.new('ShaderNodeVectorMath');atlas_scale.operation='MULTIPLY';atlas_scale.inputs[1].default_value=(atlas_du,atlas_dv,1.)
 atlas_offset=nodes.new('ShaderNodeVectorMath');atlas_offset.operation='ADD';atlas_offset.inputs[1].default_value=(atlas_u0,.5-atlas_dv/2,0.)
 links.new(uv.outputs['UV'],atlas_scale.inputs[0]);links.new(atlas_scale.outputs['Vector'],atlas_offset.inputs[0])
 # Keep colours and wear anchored to material UV coordinates during deformation.
 for n in list(nodes):
  if n.type=='TEX_COORD'and n!=uv:
   for socket in ['UV','Generated','Object']:
    for link in list(n.outputs[socket].links):links.new(atlas_offset.outputs['Vector'],link.to_socket)
 bs.inputs['Metallic'].default_value=0.;bs.inputs['Specular IOR Level'].default_value=.20;bs.inputs['Sheen Weight'].default_value=.16;bs.inputs['Sheen Roughness'].default_value=.85
 rough=nodes.new('ShaderNodeMapRange');rough.inputs['From Min'].default_value=0.;rough.inputs['From Max'].default_value=1.;rough.inputs['To Min'].default_value=.76;rough.inputs['To Max'].default_value=.94;rough.clamp=True
 if bs.inputs['Roughness'].is_linked:links.new(bs.inputs['Roughness'].links[0].from_socket,rough.inputs['Value'])
 else:rough.inputs['Value'].default_value=bs.inputs['Roughness'].default_value
 links.new(rough.outputs['Result'],bs.inputs['Roughness'])
 metric=nodes.new('ShaderNodeVectorMath');metric.operation='MULTIPLY';metric.inputs[1].default_value=(LAYOUT['width'],length,1.);links.new(uv.outputs['UV'],metric.inputs[0])
 noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=2600.;noise.inputs['Detail'].default_value=2.;links.new(metric.outputs['Vector'],noise.inputs['Vector'])
 bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.18;bump.inputs['Distance'].default_value=.000025;links.new(noise.outputs['Fac'],bump.inputs['Height'])
 if bs.inputs['Normal'].is_linked:links.new(bs.inputs['Normal'].links[0].from_socket,bump.inputs['Normal'])
 links.new(bump.outputs['Normal'],bs.inputs['Normal'])
 m['source_asset']='BlenderKit Hanging scarf / 2f573618-d7ed-46a1-8d24-5f8a7e641609';m['adaptation']='Original fabric colour/texture network, UV anchoring, matte cotton optical response and fine fibre bump. Material displacement disconnected to preserve native geometry. Native body and fringe are new thin-shell topology, not baked asset pose.'
 m['atlas_body_region_uv']=[atlas_u0,.5-atlas_dv/2,atlas_u0+atlas_du,.5+atlas_dv/2]
 return m
