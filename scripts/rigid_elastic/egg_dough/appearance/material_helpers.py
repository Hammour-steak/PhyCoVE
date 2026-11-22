"""Scene-owned geometry and CC0 photographed wood PBR helpers."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import scene_asset
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
from pathlib import Path
import bpy

ASSETS=scene_asset(Path(__file__).resolve().parents[1], 'assets/look_assets')

def material(name,color,rough=.5):
    m=bpy.data.materials.new(name);m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Roughness'].default_value=rough
    return m,bs

def node(m,kind):return m.node_tree.nodes.new(kind)
def link(m,out,inp):m.node_tree.links.new(out,inp)
def math_node(m,op,a,b=None):
    n=node(m,'ShaderNodeMath');n.operation=op
    for i,v in enumerate((a,b)):
        if v is None:continue
        if isinstance(v,(int,float)):n.inputs[i].default_value=v
        else:link(m,v,n.inputs[i])
    return n.outputs[0]
def vector_math(m,op,a,b=None):
    n=node(m,'ShaderNodeVectorMath');n.operation=op
    link(m,a,n.inputs[0])
    if b is not None:
        if isinstance(b,tuple):n.inputs[1].default_value=b
        else:link(m,b,n.inputs[1])
    return n.outputs['Value'] if op in ('LENGTH','DOT_PRODUCT') else n.outputs[0]
def map_range(m,a,lo,hi,src=(0,1)):
    n=node(m,'ShaderNodeMapRange');link(m,a,n.inputs['Value'])
    for k,v in [('From Min',src[0]),('From Max',src[1]),('To Min',lo),('To Max',hi)]:n.inputs[k].default_value=v
    return n.outputs[0]
def noise(m,co,scale,detail=2,rough=.65):
    n=node(m,'ShaderNodeTexNoise');n.inputs['Scale'].default_value=scale;n.inputs['Detail'].default_value=detail;n.inputs['Roughness'].default_value=rough
    link(m,co,n.inputs['Vector']);return n
def image(m,path,co,linear=False,box=False):
    n=node(m,'ShaderNodeTexImage');n.image=bpy.data.images.load(str(ASSETS/path),check_existing=True)
    if linear:n.image.colorspace_settings.name='Non-Color'
    n.interpolation='Linear';n.extension='REPEAT'
    if box:n.projection='BOX';n.projection_blend=.35
    link(m,co,n.inputs['Vector']);return n.outputs['Color']
def combine(m,x,y,z=0):
    n=node(m,'ShaderNodeCombineXYZ')
    for i,v in enumerate((x,y,z)):
        if isinstance(v,(int,float)):n.inputs[i].default_value=v
        else:link(m,v,n.inputs[i])
    return n.outputs[0]

def wood_material(color_multiplier=(1.,1.,1.),appearance=None):
    from realism_look import wood
    return wood(color_multiplier)

def box(name,loc,dim,mat,bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);ob=bpy.context.object;ob.name=name;ob.dimensions=dim
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);ob.data.materials.append(mat)
    if bevel:
        mod=ob.modifiers.new('Real manufactured edge radius','BEVEL');mod.width=bevel;mod.segments=3
        ob.modifiers.new('Weighted corner normals','WEIGHTED_NORMAL')
    return ob

def cylinder(name,pos,radius,depth,mat,bevel=.001):
    bpy.ops.mesh.primitive_cylinder_add(vertices=96,radius=radius,depth=depth,location=pos)
    ob=bpy.context.object;ob.name=name;ob.data.materials.append(mat)
    if bevel:
        mod=ob.modifiers.new('Manufactured fillet','BEVEL');mod.width=bevel;mod.segments=3
        ob.modifiers.new('Corner normals','WEIGHTED_NORMAL')
    for p in ob.data.polygons:p.use_smooth=True
    return ob

