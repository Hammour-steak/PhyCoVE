"""Appearance-only backyard environment build (scanned patio and lawn) on the courtyard scene."""
import argparse
import hashlib
import json
import math
import random
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector
from bpy_extras.object_utils import world_to_camera_view


def shader(name, color, roughness):
    mat=bpy.data.materials.new(name)
    mat.use_nodes=True
    bs=mat.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Roughness'].default_value=roughness
    return mat


def mesh_object(name, vertices, faces, mat, collection):
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata(vertices,[],faces)
    mesh.update()
    ob=bpy.data.objects.new(name,mesh)
    collection.objects.link(ob)
    ob.data.materials.append(mat)
    return ob


def texture(nodes, links, path, vector, color=False):
    node=nodes.new('ShaderNodeTexImage')
    node.image=bpy.data.images.load(str(path),check_existing=True)
    if not color: node.image.colorspace_settings.name='Non-Color'
    links.new(vector,node.inputs['Vector'])
    return node


def floor_material(assets):
    mat=shader('Scanned_Concrete_Pavement_4K',(0.3,0.29,0.25),0.7)
    nodes,links=mat.node_tree.nodes,mat.node_tree.links
    bs=nodes.get('Principled BSDF')
    uv=nodes.new('ShaderNodeTexCoord')
    base=assets/'concrete_pavement'
    maps={k:texture(nodes,links,base/f'concrete_pavement_{k}_4k.jpg',uv.outputs['UV'],k=='diff')
          for k in ('diff','rough','nor_gl','ao')}
    noise=nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value=0.65
    noise.inputs['Detail'].default_value=3
    links.new(uv.outputs['Object'],noise.inputs['Vector'])
    weather=nodes.new('ShaderNodeValToRGB')
    weather.color_ramp.elements[0].position=0.23
    weather.color_ramp.elements[0].color=(0.58,0.55,0.49,1)
    weather.color_ramp.elements[1].position=0.78
    weather.color_ramp.elements[1].color=(1,1,1,1)
    links.new(noise.outputs['Fac'],weather.inputs[0])
    multiply=nodes.new('ShaderNodeMixRGB')
    multiply.blend_type='MULTIPLY'
    multiply.inputs[0].default_value=0.50
    links.new(maps['diff'].outputs['Color'],multiply.inputs[1])
    links.new(weather.outputs['Color'],multiply.inputs[2])
    links.new(multiply.outputs[0],bs.inputs['Base Color'])
    links.new(maps['rough'].outputs['Color'],bs.inputs['Roughness'])
    normal=nodes.new('ShaderNodeNormalMap')
    normal.inputs['Strength'].default_value=0.42
    links.new(maps['nor_gl'].outputs[0],normal.inputs['Color'])
    links.new(normal.outputs[0],bs.inputs['Normal'])
    return mat


def scanned_patio(assets, collection):
    # The source scan covers 1.8 m. Real slab sizes are about 0.6 x 0.3 m.
    xmin,xmax,ymin,ymax=-2.15,2.45,-2.80,1.65
    nx,ny=600,580
    x,y=np.meshgrid(np.linspace(xmin,xmax,nx+1),np.linspace(ymin,ymax,ny+1))
    uvx=(x-xmin)/1.8
    uvy=(y-ymin)/1.8
    disp=bpy.data.images.load(str(assets/'concrete_pavement'/'concrete_pavement_disp_4k.jpg'),check_existing=True)
    disp.colorspace_settings.name='Non-Color'
    pixels=np.empty(len(disp.pixels),dtype=np.float32)
    disp.pixels.foreach_get(pixels)
    w,h=disp.size
    field=pixels.reshape(h,w,4)[:,:,0]
    ix=(uvx%1*(w-1)).astype(int)
    iy=(uvy%1*(h-1)).astype(int)
    z=-0.0032+(field[iy,ix]-0.5)*0.0045
    verts=np.stack((x,y,z),axis=-1).reshape(-1,3)
    ids=np.arange((nx+1)*(ny+1)).reshape(ny+1,nx+1)
    faces=np.stack((ids[:-1,:-1],ids[:-1,1:],ids[1:,1:],ids[1:,:-1]),axis=-1).reshape(-1,4)
    obj=mesh_object('ScannedPatio_TrueRelief',verts.tolist(),faces.tolist(),floor_material(assets),collection)
    uv=obj.data.uv_layers.new(name='MetreScale_1p8m_Scan')
    uvdata=np.stack((uvx,uvy),axis=-1).reshape(-1,2)
    uv.data.foreach_set('uv',uvdata[faces.flatten()].astype(np.float32).flatten())
    return {'bounds_m':[xmin,xmax,ymin,ymax],'texture_width_m':1.8,'relief_m':0.0045,
            'vertices':len(verts),'top_range_m':[float(z.min()),float(z.max())]}


def lawn_material():
    mat=shader('Organic_Soil_Thatch',(0.055,0.075,0.019),0.91)
    ns,ls=mat.node_tree.nodes,mat.node_tree.links
    bs=ns.get('Principled BSDF')
    coord=ns.new('ShaderNodeTexCoord')
    no=ns.new('ShaderNodeTexNoise')
    no.inputs['Scale'].default_value=4.8
    no.inputs['Detail'].default_value=4
    ls.new(coord.outputs['Object'],no.inputs['Vector'])
    ramp=ns.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color=(0.023,0.030,0.009,1)
    ramp.color_ramp.elements[1].color=(0.10,0.13,0.034,1)
    ls.new(no.outputs['Fac'],ramp.inputs['Fac'])
    ls.new(ramp.outputs[0],bs.inputs['Base Color'])
    bump=ns.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value=0.35
    bump.inputs['Distance'].default_value=0.002
    ls.new(no.outputs['Fac'],bump.inputs['Height'])
    ls.new(bump.outputs[0],bs.inputs['Normal'])
    return mat


def ground_height(x,y):
    # Small smooth height changes, with the verge slightly below the patio.
    return -0.016+0.003*math.sin(x*2.1+y*0.8)*math.sin(y*1.9-x*0.6)


def fine_turf(ground):
    mat=shader('Living_Grass_Blades',(0.065,0.13,0.021),0.78)
    ns,ls=mat.node_tree.nodes,mat.node_tree.links
    bs=ns.get('Principled BSDF')
    info=ns.new('ShaderNodeHairInfo')
    colors=ns.new('ShaderNodeValToRGB')
    colors.color_ramp.elements[0].position=0.08
    colors.color_ramp.elements[0].color=(0.018,0.050,0.005,1)
    colors.color_ramp.elements[1].position=0.94
    colors.color_ramp.elements[1].color=(0.14,0.25,0.027,1)
    colors.color_ramp.elements.new(0.60).color=(0.055,0.135,0.010,1)
    ls.new(info.outputs['Random'],colors.inputs[0])
    ls.new(colors.outputs[0],bs.inputs['Base Color'])
    trans=ns.new('ShaderNodeBsdfTranslucent')
    ls.new(colors.outputs[0],trans.inputs['Color'])
    mix=ns.new('ShaderNodeMixShader')
    mix.inputs[0].default_value=0.25
    ls.new(bs.outputs[0],mix.inputs[1])
    ls.new(trans.outputs[0],mix.inputs[2])
    ls.new(mix.outputs[0],ns.get('Material Output').inputs['Surface'])
    ground.data.materials.append(mat)
    density=ground.vertex_groups.new(name='Only_the_exposed_lawn')
    for v in ground.data.vertices:
        x,y=v.co.x,v.co.y
        if -2.168<x<2.468 and -2.818<y<1.668: continue
        density.add([v.index],0.85+0.15*math.sin(x*3+y*1.7)**2,'REPLACE')
    bpy.context.view_layer.objects.active=ground
    ground.select_set(True)
    bpy.ops.object.particle_system_add()
    ps=ground.particle_systems[-1]
    ps.seed=20261027
    ps.vertex_group_density=density.name
    settings=ps.settings
    settings.type='HAIR'
    settings.count=210000
    settings.hair_length=0.040
    settings.hair_step=3
    settings.material=2
    settings.child_type='INTERPOLATED'
    settings.child_percent=3
    settings.rendered_child_count=24
    settings.child_length=0.88
    settings.child_length_threshold=0
    settings.clump_factor=0.02
    settings.roughness_1=0.014
    settings.roughness_1_size=0.45
    settings.roughness_2=0.007
    settings.roughness_2_size=0.25
    settings.roughness_endpoint=0.012
    settings.root_radius=0.00030
    settings.tip_radius=0.000035
    settings.radius_scale=1.0
    settings.shape=-0.15
    settings.use_hair_bspline=True
    ground.select_set(False)
    return {'root_count':settings.count,'children':settings.rendered_child_count,
            'length_m':settings.hair_length,'root_radius_m':settings.root_radius}


def grass_sources(assets):
    source=assets/'grass_medium_01'/'grass_medium_01_2k.blend'
    with bpy.data.libraries.load(str(source),link=False) as (src,dst):
        dst.objects=[n for n in src.objects if n in {
            'grass_medium_01_small_a_LOD0','grass_medium_01_small_b_LOD0',
            'grass_medium_01_mid_a_LOD0','grass_medium_01_mid_b_LOD0',
            'grass_medium_01_tiny_a_LOD0','grass_medium_01_tiny_c_LOD0'}]
    prototypes=[]
    for o in dst.objects:
        if o is None or o.type!='MESH': continue
        mesh=o.data.copy()
        mesh.transform(o.matrix_world)
        v=np.array([v.co[:] for v in mesh.vertices])
        lo,hi=v.min(axis=0),v.max(axis=0)
        height=hi[2]-lo[2]
        target=0.055 if 'tiny' in o.name else 0.068
        s=target/height
        mesh.transform(Matrix.Diagonal((s,s,s,1)) @ Matrix.Translation((-(lo[0]+hi[0])/2,-(lo[1]+hi[1])/2,-lo[2])))
        prototypes.append(mesh)
        print('GRASS_SOURCE',o.name,'source_dimensions',list(hi-lo),'target_height',target,'faces',len(mesh.polygons),flush=True)
    # Use the authored scan material and transmission/alpha. Resolve library dependencies.
    for im in bpy.data.images:
        if 'grass_medium_01' in im.name:
            candidate=assets/'grass_medium_01'/'textures'/Path(im.filepath).name
            if candidate.is_file(): im.filepath=str(candidate)
    return prototypes


def add_lawn(scene,assets,collection):
    mat=lawn_material()
    xs=np.linspace(-9,5,180)
    ys=np.linspace(-4,13,200)
    verts=[(float(x),float(y),ground_height(x,y)-0.004) for y in ys for x in xs]
    faces=[(j*len(xs)+i,j*len(xs)+i+1,(j+1)*len(xs)+i+1,(j+1)*len(xs)+i)
           for j in range(len(ys)-1) for i in range(len(xs)-1)]
    ground=mesh_object('Continuous_Lawn_Soil',verts,faces,mat,collection)
    for f in ground.data.polygons: f.use_smooth=True
    fine=fine_turf(ground)
    prototypes=grass_sources(assets)
    if not prototypes: raise RuntimeError('No grass meshes loaded')
    rng=random.Random(20261027)
    points=[]
    # Ground-camera coverage matters more than a giant lawn outside the view.
    for j in range(172):
        for i in range(153):
            x=-7.4+(i+rng.random())*0.065
            y=-1.0+(j+rng.random())*0.065
            if -2.17 < x < 2.47 and -2.82 < y < 1.67: continue
            h=ground_height(x,y)
            screen=world_to_camera_view(scene,scene.camera,Vector((x,y,h)))
            if not(-0.13<screen.x<1.13 and -0.08<screen.y<1.16 and screen.z>0): continue
            if rng.random()<0.72: continue
            points.append((x,y,h))
    for index,(x,y,z) in enumerate(points):
        mesh=prototypes[rng.randrange(len(prototypes))]
        obj=bpy.data.objects.new(f'LawnTuft_{index:05d}',mesh)
        collection.objects.link(obj)
        obj.location=(x,y,z)
        obj.rotation_euler=(rng.uniform(-0.12,0.12),rng.uniform(-0.12,0.12),rng.random()*math.tau)
        s=rng.uniform(0.7,1.3)
        patch=1+0.16*math.sin(x*2.8+y*1.4)
        obj.scale=(s*patch,s*patch,s*rng.uniform(0.50,0.85))
    print('LAWN_TUFTS',len(points),flush=True)
    return {'sources':'Poly Haven Grass Medium 01, 2K, six scanned variants',
            'instances':len(points),'height_m':[0.03,0.095],'seed':20261027,
            'fine_turf':fine,
            'method':'Continuous fine grass with six linked scanned tufts; height/rotation/density variation'}


def environment_signature():
    names=['PCVE_ToyCarVisual','PCVE_ToyCarCollisionProxy','Childrens Inflatable Pool.001',
           'PCVE_ToyTrackDeck','PCVE_GenesisWater','PCVE_GenesisSpray','PCVE_GenesisMist','PCVE_GenesisFoam']
    result={}
    for name in names:
        ob=bpy.data.objects.get(name)
        if ob is None: continue
        meshhash=None
        if ob.type=='MESH':
            v=np.empty(len(ob.data.vertices)*3,dtype=np.float32)
            ob.data.vertices.foreach_get('co',v)
            ids=np.empty(len(ob.data.loops),dtype=np.int32)
            ob.data.loops.foreach_get('vertex_index',ids)
            meshhash=hashlib.sha256(v.tobytes()+ids.tobytes()).hexdigest()
        result[name]={'matrix':[list(r) for r in ob.matrix_world],'geometry_sha256':meshhash}
    cam=bpy.context.scene.camera
    result['camera']={'matrix':[list(r) for r in cam.matrix_world],'lens':cam.data.lens}
    return result


def build(scene,assets):
    before=environment_signature()
    col=bpy.data.collections.new('Real_Patio_and_Lawn')
    scene.collection.children.link(col)
    bpy.data.objects['PCVE_RealPatio'].hide_render=True
    bpy.data.objects['PCVE_RealPatio'].hide_viewport=True
    patio=scanned_patio(assets,col)
    lawn=add_lawn(scene,assets,col)
    after=environment_signature()
    if before!=after: raise RuntimeError('Protected action/camera geometry changed')
    return {'revision':'environment_realism','appearance_only':True,
            'patio':patio,'lawn':lawn,'protected_before':before,'protected_after':after,
            'protected_geometry_unchanged':True,
            'lighting':'Original world + sun + contact fill, unchanged',
            'assets':[{'source':'https://polyhaven.com/a/concrete_pavement','license':'CC0'},
                      {'source':'https://polyhaven.com/a/grass_medium_01','license':'CC0'}]}


def configure_gpu(scene,samples):
    scene.render.engine='CYCLES'
    scene.cycles.device='GPU'
    scene.cycles.samples=samples
    scene.cycles.use_denoising=True
    prefs=bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type='OPTIX'
    prefs.get_devices()
    for d in prefs.devices: d.use=d.type=='OPTIX'
    scene.render.image_settings.file_format='PNG'
    scene.render.image_settings.color_mode='RGB'
    scene.render.resolution_percentage=100


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--assets',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=32)
    parser.add_argument('--render-before',action='store_true')
    parser.add_argument('--no-render',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    args.out.mkdir(parents=True,exist_ok=True)
    scene=bpy.context.scene
    configure_gpu(scene,args.samples)
    if args.render_before:
        scene.render.filepath=str(args.out/'before.png')
        bpy.ops.render.render(write_still=True)
    started=time.monotonic()
    record=build(scene,args.assets)
    record['build_seconds']=time.monotonic()-started
    scene.render.filepath=str(args.out/'after.png')
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out/'scene_environment.blend'))
    if not args.no_render:
        started=time.monotonic()
        bpy.ops.render.render(write_still=True)
        record['render_seconds']=time.monotonic()-started
    (args.out/'environment_manifest.json').write_text(json.dumps(record,indent=2))
    print('ENVIRONMENT_DONE',str(args.out),flush=True)


if __name__=='__main__': main()
