"""Render reconstructed tea with coffee's velocity blur; scene inputs stay fixed."""
import argparse,json,sys,time
from pathlib import Path
import bpy
import numpy as np
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('case',type=Path)
p.add_argument('--frames',type=int,nargs='+')
p.add_argument('--device',choices=['GPU','CPU'],default='GPU')
p.add_argument('--no-blur',action='store_true')
p.add_argument('--native',action='store_true')
p.add_argument('--report-tag')
p.add_argument('--physical-optics',action='store_true')
p.add_argument('--output')
p.add_argument('--surface-dir',default='surfaces')
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);case=a.case.resolve()
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tea_environment_state import protected_state,environment_state,digest,file_hash
scene=bpy.context.scene;scene.frame_set(72);bpy.context.view_layer.update()
locked=protected_state();env=environment_state();source_hash=file_hash(Path(bpy.data.filepath))
assert scene.cycles.samples==128 and (scene.render.resolution_x,scene.render.resolution_y,scene.render.fps)==(1280,720,24)
surface=bpy.data.objects['GenesisTeaSurface'];materials=list(surface.data.materials)
if not a.native:
    for modifier in list(surface.modifiers):surface.modifiers.remove(modifier)
    for cache in list(bpy.data.cache_files):
        assert cache.users==0
        bpy.data.batch_remove(ids=(cache,))
if a.physical_optics:
    materials=[m.copy() for m in materials]
    for mat in materials:
        mat.name='TraditionalTea_PhysicalAmber'
        bsdf=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
        bsdf.inputs['Base Color'].default_value=(1.,1.,1.,1.)
        absorption=next(n for n in mat.node_tree.nodes if n.type=='VOLUME_ABSORPTION')
        absorption.inputs['Density'].default_value=450.
    surface.data.materials.clear()
    for mat in materials:surface.data.materials.append(mat)
scene.render.use_motion_blur=not a.no_blur
scene.render.motion_blur_shutter=.5;scene.cycles.motion_blur_position='CENTER'
scene.render.use_persistent_data=True
scene.render.threads_mode='FIXED';scene.render.threads=16
scene.cycles.device=a.device
if a.device=='GPU':
    prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
    assert any(d.type=='OPTIX' for d in prefs.devices)
    for d in prefs.devices:d.use=d.type=='OPTIX'
actual=protected_state();expected=json.loads(json.dumps(locked));expected['render'][-1]=not a.no_blur
if a.physical_optics:expected['hero_and_tea_materials']['GenesisTeaSurface']=actual['hero_and_tea_materials']['GenesisTeaSurface']
assert digest(actual)==digest(expected) and digest(environment_state())==digest(env)

def load_frame(f):
    with np.load(case/a.surface_dir/f'frame_{f:04d}.npz') as z:v,t,n,vel=z['vertices'],z['triangles'],z['normals'],z['velocity']
    me=bpy.data.meshes.new(f'TeaSurface_{f:04d}')
    if len(v):
        me.vertices.add(len(v));me.vertices.foreach_set('co',v.ravel())
        me.loops.add(t.size);me.loops.foreach_set('vertex_index',t.ravel())
        me.polygons.add(len(t));me.polygons.foreach_set('loop_start',np.arange(0,t.size,3))
        me.polygons.foreach_set('use_smooth',np.ones(len(t),bool));me.update();me.validate(clean_customdata=False)
        me.normals_split_custom_set_from_vertices(n.tolist())
        attr=me.attributes.new('velocity','FLOAT_VECTOR','POINT');attr.data.foreach_set('vector',vel.ravel())
    for mat in materials:me.materials.append(mat)
    old=surface.data;surface.data=me
    if old.users==0:bpy.data.meshes.remove(old)

out=case/(a.output or ('frames' if a.native else ('probes_no_blur' if a.no_blur else 'probes')))
out.mkdir(exist_ok=True);times={};start=time.monotonic();reused=[]
for f in a.frames or range(1,97):
    path=out/f'frame_{f:04d}.png'
    if path.exists():reused.append(f);continue
    scene.frame_set(f)
    if not a.native:load_frame(f)
    bpy.context.view_layer.update();scene.render.filepath=str(path)
    tick=time.monotonic();bpy.ops.render.render(write_still=True);times[str(f)]=time.monotonic()-tick
    print('TEA_SPLASH_RENDER',f,times[str(f)],flush=True)
assert file_hash(Path(bpy.data.filepath))==source_hash
report={'frames':times,'reused':reused,'render_seconds':time.monotonic()-start,'samples':128,'width':1280,'height':720,'fps':24,
        'motion_blur':scene.render.use_motion_blur,'shutter':scene.render.motion_blur_shutter,'protected_before':locked,
        'protected_after':protected_state(),'environment_preserved':digest(environment_state())==digest(env),'mode':'native' if a.native else 'direct velocity attributes'}
(case/f"render_{a.report_tag or ('native' if a.native else 'probe')}.json").write_text(json.dumps(report,indent=2)+'\n')
