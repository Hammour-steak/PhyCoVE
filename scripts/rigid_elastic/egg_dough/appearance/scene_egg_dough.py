"""Blender Cycles tabletop, driven only by viscoelastic FEM cache geometry."""
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
import argparse
import json
import math
import sys
import time
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dough_config import write_json,digest,LOOK_FILE

def material(name,color,rough=.5):
    m=bpy.data.materials.new(name); m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF'); bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Roughness'].default_value=rough
    return m,bs

def wood():
    m,bs=material('Solid light beech • 1.3 mm growth rings',(.48,.24,.09),.43)
    n=m.node_tree.nodes; l=m.node_tree.links
    tex=n.new('ShaderNodeTexCoord')
    mapping=n.new('ShaderNodeVectorMath'); mapping.operation='MULTIPLY'; mapping.inputs[1].default_value=(1.,1.,.13)
    l.new(tex.outputs['Object'],mapping.inputs[0])
    noise=n.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value=380; noise.inputs['Detail'].default_value=3
    noise.inputs['Roughness'].default_value=.67; l.new(mapping.outputs['Vector'],noise.inputs['Vector'])
    sep=n.new('ShaderNodeSeparateXYZ');l.new(tex.outputs['Object'],sep.inputs[0])
    radial=n.new('ShaderNodeCombineXYZ');l.new(sep.outputs['X'],radial.inputs['X']);l.new(sep.outputs['Y'],radial.inputs['Y'])
    length=n.new('ShaderNodeVectorMath');length.operation='LENGTH';l.new(radial.outputs[0],length.inputs[0])
    phase=n.new('ShaderNodeMath');phase.operation='MULTIPLY';phase.inputs[1].default_value=2*math.pi/.0013
    l.new(length.outputs['Value'],phase.inputs[0])
    warp=n.new('ShaderNodeMath');warp.operation='MULTIPLY';warp.inputs[1].default_value=1.7;l.new(noise.outputs['Fac'],warp.inputs[0])
    add=n.new('ShaderNodeMath');add.operation='ADD';l.new(phase.outputs[0],add.inputs[0]);l.new(warp.outputs[0],add.inputs[1])
    sine=n.new('ShaderNodeMath');sine.operation='SINE';l.new(add.outputs[0],sine.inputs[0])
    rings=n.new('ShaderNodeMapRange');rings.inputs['From Min'].default_value=-1;rings.inputs['From Max'].default_value=1
    rings.inputs['To Min'].default_value=.55;rings.inputs['To Max'].default_value=1;l.new(sine.outputs[0],rings.inputs['Value'])
    mix=n.new('ShaderNodeMixRGB'); mix.blend_type='MULTIPLY'; mix.inputs[0].default_value=.28
    l.new(noise.outputs['Fac'],mix.inputs[1]); l.new(rings.outputs[0],mix.inputs[2])
    ramp=n.new('ShaderNodeValToRGB'); ramp.color_ramp.elements.remove(ramp.color_ramp.elements[1])
    for i,(p,col) in enumerate(((.08,(.10,.026,.006,1)),(.34,(.24,.075,.014,1)),(.60,(.45,.205,.058,1)),(.85,(.64,.37,.15,1)))):
        e=ramp.color_ramp.elements[0] if i==0 else ramp.color_ramp.elements.new(p); e.position=p; e.color=col
    l.new(mix.outputs['Color'],ramp.inputs['Fac']); l.new(ramp.outputs['Color'],bs.inputs['Base Color'])
    bump=n.new('ShaderNodeBump'); bump.inputs['Strength'].default_value=.13; bump.inputs['Distance'].default_value=.000055
    l.new(noise.outputs['Fac'],bump.inputs['Height']); l.new(bump.outputs['Normal'],bs.inputs['Normal'])
    return m

def box(name,loc,dim,mat,bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc); o=bpy.context.object; o.name=name; o.dimensions=dim
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    o.data.materials.append(mat)
    if bevel:
        mod=o.modifiers.new('Manufactured edge radius','BEVEL'); mod.width=bevel; mod.segments=3
        o.modifiers.new('Corner normals','WEIGHTED_NORMAL')
    return o

def cylinder(name,pos,radius,depth,mat,bevel=.001):
    bpy.ops.mesh.primitive_cylinder_add(vertices=96,radius=radius,depth=depth,location=pos)
    o=bpy.context.object; o.name=name; o.data.materials.append(mat)
    if bevel:
        mod=o.modifiers.new('Soft ceramic edge','BEVEL'); mod.width=bevel; mod.segments=3
        o.modifiers.new('Corner normals','WEIGHTED_NORMAL')
    for p in o.data.polygons: p.use_smooth=True
    return o

def look_at(o,target): o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()

def area(name,pos,target,energy,size,color,shape='DISK',size_y=None):
    ld=bpy.data.lights.new(name,'AREA'); ld.energy=energy; ld.shape=shape; ld.size=size; ld.color=color
    if size_y is not None: ld.size_y=size_y
    o=bpy.data.objects.new(name,ld); bpy.context.collection.objects.link(o); o.location=pos; look_at(o,target)
    return o

def setup(c):
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    sc=bpy.context.scene;sc.render.engine='CYCLES';sc.cycles.samples=c['render']['samples'];sc.cycles.use_denoising=True
    import os
    if os.environ.get('PCVE_CYCLES_CPU')=='1':sc.cycles.device='CPU'
    else:
        sc.cycles.device='GPU'
        # PCVE_CYCLES_GPU_BACKEND=CUDA is a fallback for machines where OptiX fails; default OptiX.
        backend=os.environ.get('PCVE_CYCLES_GPU_BACKEND','OPTIX')
        prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type=backend;prefs.get_devices()
        for d in prefs.devices:d.use=d.type==backend
        if not any(d.use for d in prefs.devices):raise RuntimeError(backend+' GPU unavailable')
    sc.render.resolution_x=1280;sc.render.resolution_y=720;sc.render.resolution_percentage=100
    sc.render.fps=24;sc.render.image_settings.file_format='PNG';sc.render.image_settings.color_mode='RGB'
    sc.render.film_transparent=False;sc.render.use_persistent_data=True
    sc.view_settings.view_transform='AgX';sc.view_settings.look='AgX - Medium High Contrast'
    sc.world.use_nodes=True; bg=sc.world.node_tree.nodes.get('Background');bg.inputs['Color'].default_value=(.74,.80,.89,1);bg.inputs['Strength'].default_value=.15
    sc.unit_settings.system='METRIC'; sc.unit_settings.scale_length=1
    from baking_look import make_baking_bench
    make_baking_bench(c['appearance'])
    # Closed room lit only by daylight through a window; no studio HDRI or hidden lamps.
    from realism_look import finish_environment
    finish_environment(sc,c['appearance'])
    bpy.ops.object.camera_add(location=c['appearance']['camera_position_m'])
    cam=bpy.context.object;cam.name='Fixed side-front interaction camera';cam.data.lens=c['appearance']['camera_focal_length_mm'];cam.data.clip_start=.005
    cam.data.clip_end=30;look_at(cam,c['appearance']['camera_target_m']);cam.data.dof.use_dof=False;sc.camera=cam
    if c['appearance'].get('camera_fstop'):
        cam.data.dof.use_dof=True;cam.data.dof.aperture_fstop=c['appearance']['camera_fstop']
        cam.data.dof.focus_distance=(cam.location-Vector(c['appearance']['camera_target_m'])).length
    return sc

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cache',type=Path,required=True);ap.add_argument('--out-dir',type=Path,required=True)
    ap.add_argument('--frames',default='all',help='Comma-separated 1-based diagnostic frames or all')
    ap.add_argument('--appearance-file',type=Path,default=LOOK_FILE)
    ap.add_argument('--save-blend',action='store_true');a=ap.parse_args(sys.argv[sys.argv.index('--')+1:])
    a.out_dir.mkdir(parents=True,exist_ok=True)
    d=np.load(a.cache);c=json.loads((a.cache.parent/'actual_config.json').read_text())
    if a.appearance_file.is_file():c['appearance']=json.loads(a.appearance_file.read_text())
    write_json(a.out_dir/'actual_render_config.json',c)
    sc=setup(c);sc.frame_end=96
    dough=None
    if bool(d['dough_present']):
        mesh=bpy.data.meshes.new('Actual deformed tetrahedral boundary');mesh.from_pydata(d['vertices'][0].tolist(),[],d['dough_faces'].tolist());mesh.update()
        dough=bpy.data.objects.new('Dough • actual viscoelastic FEM boundary',mesh);bpy.context.collection.objects.link(dough)
        ref=mesh.attributes.new('rest_position_m','FLOAT_VECTOR','POINT')
        ref.data.foreach_set('vector',d['rest_vertices'].astype(np.float32).ravel())
        from realism_look import dough as look_dough
        mat=look_dough(c['appearance'])
        dough.data.materials.append(mat)
        for p in dough.data.polygons:p.use_smooth=True
    ball_present=bool(c['physics']['ball'].get('present',True))
    ball=None
    # Append the same meter-scale mesh used to prepare the physical SDF unless
    # this counterfactual explicitly removes the egg from frame 1 onward.
    if ball_present:
        asset=scene_asset(Path(__file__).parents[1],c['appearance']['rigid_asset'])
        with bpy.data.libraries.load(str(asset),link=False) as (src,dst):
            dst.objects=['Whole brown egg • six degree-of-freedom rigid pose']
        ball=dst.objects[0];bpy.context.collection.objects.link(ball)
        assert ball.get('rigid_interaction') and not ball.modifiers
        from realism_look import egg_shell
        egg_shell(ball,c['appearance']['egg_shell_treatment'])
        for p in ball.data.polygons:p.use_smooth=True
    def key_ball():
        if ball is None:return
        # One linear keyframe per cached frame: exact cached pose on every frame, and Cycles
        # motion blur interpolates the rigid pose inside the shutter interval.
        ball.rotation_mode='QUATERNION';previous=None
        for i,T in enumerate(d['ball_transforms'][:96]):
            ball.matrix_world=Matrix(T.tolist())
            q=ball.rotation_quaternion.copy()
            if previous is not None and q.dot(previous)<0:q.negate()
            ball.rotation_quaternion=q;previous=q.copy()
            ball.keyframe_insert('location',frame=i+1);ball.keyframe_insert('rotation_quaternion',frame=i+1);ball.keyframe_insert('scale',frame=i+1)
        for fc in ball.animation_data.action.fcurves:
            for k in fc.keyframe_points:k.interpolation='LINEAR'
    keyed=bool(sc.render.use_motion_blur and ball_present)
    if keyed:
        key_ball()
        if dough is not None:
            # The dough mesh is set per whole frame (no sub-frame states), so it carries no blur.
            dough.cycles.use_motion_blur=False
    def update(scene):
        # Sub-frame evaluations (motion blur shutter samples) use the nearest cached frame.
        i=max(0,min(int(round(scene.frame_current+scene.frame_subframe))-1,len(d['ball_transforms'])-1))
        if dough is not None:
            dough.data.vertices.foreach_set('co',d['vertices'][i].astype(np.float32).ravel());dough.data.update()
        if not keyed and ball is not None:ball.matrix_world=Matrix(d['ball_transforms'][i].tolist())
    bpy.app.handlers.frame_change_pre.append(update)
    update(sc)
    frame_ids=list(range(1,97)) if a.frames=='all' else list(map(int,a.frames.split(',')))
    (a.out_dir/'frames').mkdir(exist_ok=True)
    if a.save_blend:
        # The saved blend includes the complete native deformation/pose animation as shape keys and matrix curves.
        if dough is not None:
            dough.shape_key_add(name='Basis')
            for i,verts in enumerate(d['vertices'][:96]):
                key=dough.shape_key_add(name=f'FEM_{i+1:04d}');key.data.foreach_set('co',verts.astype(np.float32).ravel())
                for at,val in ((max(1,i),0),(i+1,1),(min(96,i+2),0)):
                    # End points have only one active sample.
                    if at==i+1 and val==0:continue
                    key.value=val;key.keyframe_insert('value',frame=at)
            for fc in dough.data.shape_keys.animation_data.action.fcurves:
                for k in fc.keyframe_points:k.interpolation='LINEAR'
        if not keyed:key_ball()
        sc.frame_set(1);update(sc)
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=str(a.out_dir/'scene.blend'))
        # Render cache directly; the saved shape-key animation is for portable manual inspection.
        if dough is not None:
            dough.shape_key_clear()
    begin=time.monotonic()
    times=[]
    for i in frame_ids:
        fp=a.out_dir/'frames'/f'frame_{i:04d}.png'
        if fp.exists():raise FileExistsError(fp)
        sc.frame_set(i);update(sc);sc.render.filepath=str(fp)
        t=time.monotonic();bpy.ops.render.render(write_still=True);times.append({'frame':i,'seconds':time.monotonic()-t})
    from baking_look import receipt
    extra={'baking_layout':receipt()}
    write_json(a.out_dir/'blender_receipt.json',{'blender':bpy.app.version_string,'samples':sc.cycles.samples,
        'resolution':[1280,720],'fps':24,'frames_rendered':frame_ids,'seconds':time.monotonic()-begin,
        'per_frame':times,'cache_sha256':digest(a.cache),'camera':c['appearance'],'fluids':0,
        'actual_camera_world_matrix':[list(row) for row in sc.camera.matrix_world],'egg_present':ball_present,
        'actual_lights':[{'name':o.name,'world_position_m':list(o.location),'energy_W':o.data.energy,
            'size_m':o.data.size,'color':list(o.data.color)} for o in sc.objects if o.type=='LIGHT'],
        'actual_color_management':{'view':sc.view_settings.view_transform,'look':sc.view_settings.look,'exposure':sc.view_settings.exposure},
        'actual_cycles':{'device':sc.cycles.device,'samples':sc.cycles.samples,'max_bounces':sc.cycles.max_bounces,
            'diffuse_bounces':sc.cycles.diffuse_bounces,'glossy_bounces':sc.cycles.glossy_bounces},
        'surface_policy':'Exact FEM boundary vertices; shader normal relief only; no deformation magnification or subdivision',**extra})

if __name__=='__main__':main()
