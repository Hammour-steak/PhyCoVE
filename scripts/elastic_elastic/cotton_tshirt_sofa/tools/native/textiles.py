"""Photographed textile maps at physical scale, with stable sewn-surface UVs."""
import bpy,numpy as np
from common import asset

def clean_principled(mat):
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;nodes.clear()
    bs=nodes.new('ShaderNodeBsdfPrincipled');out=nodes.new('ShaderNodeOutputMaterial');links.new(bs.outputs[0],out.inputs['Surface'])
    bs.inputs['Metallic'].default_value=0;bs.inputs['IOR'].default_value=1.46
    bs.inputs['Specular IOR Level'].default_value=.45;bs.inputs['Coat Weight'].default_value=0
    bs.inputs['Sheen Weight'].default_value=.22;bs.inputs['Sheen Roughness'].default_value=.65
    return nodes,links,bs,out

def photo(nodes,links,name,vector,noncolor=False):
    tex=nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(asset(name)),check_existing=True)
    if noncolor:tex.image.colorspace_settings.name='Non-Color'
    tex.interpolation='Linear';links.new(vector,tex.inputs['Vector']);return tex

def images(mat,name,vector,res='2k',strength=.4,uv='Woven UV'):
    n=mat.node_tree.nodes;l=mat.node_tree.links;bs=next(x for x in n if x.type=='BSDF_PRINCIPLED')
    diffuse=photo(n,l,name+'_Diffuse_'+res+'.jpg',vector);rough=photo(n,l,name+'_Rough_'+res+'.jpg',vector,True)
    normal=photo(n,l,name+'_nor_gl_'+res+'.png',vector,True)
    gray=n.new('ShaderNodeRGBToBW');l.new(diffuse.outputs[0],gray.inputs[0])
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.44,.425,.39,1);ramp.color_ramp.elements[1].color=(.73,.71,.665,1)
    l.new(gray.outputs[0],ramp.inputs[0]);l.new(ramp.outputs[0],bs.inputs['Base Color'])
    rm=n.new('ShaderNodeMapRange');rm.inputs['To Min'].default_value=.68;rm.inputs['To Max'].default_value=.91;l.new(rough.outputs[0],rm.inputs[0]);l.new(rm.outputs[0],bs.inputs['Roughness'])
    nm=n.new('ShaderNodeNormalMap');nm.uv_map=uv;nm.inputs['Strength'].default_value=strength;l.new(normal.outputs[0],nm.inputs['Color']);l.new(nm.outputs[0],bs.inputs['Normal'])
    return ramp

def cotton_jersey(mat):
    n,l,bs,out=clean_principled(mat);bs.inputs['Sheen Weight'].default_value=.18
    scale=n.new('ShaderNodeVectorMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=(1/.2636027474,1,1/.2637999952)
    sep=n.new('ShaderNodeSeparateXYZ');combine=n.new('ShaderNodeCombineXYZ');l.new(scale.outputs[0],sep.inputs[0]);l.new(sep.outputs['X'],combine.inputs['X']);l.new(sep.outputs['Z'],combine.inputs['Y'])
    ramp=images(mat,'cotton_jersey',combine.outputs[0],'4k',.53,'Knit UV')
    translucent=n.new('ShaderNodeBsdfTranslucent');l.new(ramp.outputs[0],translucent.inputs[0])
    mix=n.new('ShaderNodeMixShader');mix.inputs[0].default_value=.045;l.new(bs.outputs[0],mix.inputs[1]);l.new(translucent.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],out.inputs['Surface'])
    return scale

def sofa_textile(mat,colors=((.16,.20,.174),(.235,.28,.242))):
    n,l,bs,out=clean_principled(mat);bs.inputs['Sheen Weight'].default_value=.26
    uv=n.new('ShaderNodeUVMap');uv.uv_map='Upholstery UV'
    ao=photo(n,l,'fabric_pattern_07_ao_2k.jpg',uv.outputs[0],True)
    rough=photo(n,l,'fabric_pattern_07_rough_2k.jpg',uv.outputs[0],True)
    normal=photo(n,l,'fabric_pattern_07_nor_gl_2k.png',uv.outputs[0],True)
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=.20;ramp.color_ramp.elements[1].position=1.
    ramp.color_ramp.elements[0].color=(*colors[0],1);ramp.color_ramp.elements[1].color=(*colors[1],1)
    l.new(ao.outputs[0],ramp.inputs[0]);l.new(ramp.outputs[0],bs.inputs['Base Color'])
    rm=n.new('ShaderNodeMapRange');rm.inputs['To Min'].default_value=.72;rm.inputs['To Max'].default_value=.91;l.new(rough.outputs[0],rm.inputs[0]);l.new(rm.outputs[0],bs.inputs['Roughness'])
    nm=n.new('ShaderNodeNormalMap');nm.uv_map='Upholstery UV';nm.inputs['Strength'].default_value=.72;l.new(normal.outputs[0],nm.inputs['Color']);l.new(nm.outputs[0],bs.inputs['Normal'])

def ensure_upholstery_uv(obj):
    me=obj.data
    if obj.type!='MESH'or not me.uv_layers:return
    source=me.uv_layers.get('Artist UV')or me.uv_layers.active
    uv=np.array([p.uv[:]for p in source.data]);me.calc_loop_triangles()
    loops=np.array([t.loops[:]for t in me.loop_triangles],dtype=int);ids=np.array([t.vertices[:]for t in me.loop_triangles],dtype=int)
    x=np.array([obj.matrix_world@v.co for v in me.vertices]);tri=x[ids];u=uv[loops]
    area=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)/2
    a=u[:,1]-u[:,0];b=u[:,2]-u[:,0];ua=np.abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])/2
    valid=(area>1e-12)&(ua>1e-12)
    metric=float(np.sqrt(area[valid].sum()/ua[valid].sum()))if np.any(valid)else 1.
    layer=me.uv_layers.get('Upholstery UV')or me.uv_layers.new(name='Upholstery UV')
    layer.data.foreach_set('uv',(uv*metric/.4).astype(np.float32).reshape(-1));obj['upholstery_metres_per_artist_uv']=metric

def woven(mat,name,tile_m,strength=.65,plane='XY'):
    n,l,bs,out=clean_principled(mat);bs.inputs['Sheen Weight'].default_value=.25
    uv=n.new('ShaderNodeUVMap');uv.uv_map='Woven UV'
    return images(mat,name,uv.outputs[0],strength=strength)
