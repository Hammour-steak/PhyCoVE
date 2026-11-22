"""Render and package the physical states with baked, validated basin clipping."""
import argparse,json,sys,time
from pathlib import Path
import bpy
from mathutils import Quaternion
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from render_animation import static_signature,parse_frames
from repair_pool_water import base,exterior_rays
from bounded_geometry import load_mesh
from water_presence import samples
NAMES={'water':'PCVE_GenesisWater','spray':'PCVE_GenesisSpray','mist':'PCVE_GenesisMist','foam':'PCVE_GenesisFoam'}
POINTS=[(.1,0),(.3,0),(.5,0),(.7,0),(.9,0),(.3,-.15),(.5,-.15),(.7,-.15),(.3,.15),(.5,.15),(.7,.15)]

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--bounded',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--case-id',required=True);p.add_argument('--frames',default='1-96');p.add_argument('--samples',type=int,default=32);p.add_argument('--package-cache',action='store_true');p.add_argument('--cache-only',action='store_true');p.add_argument('--reuse',action='store_true')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);a.out.mkdir(parents=True,exist_ok=True)
    scene=bpy.context.scene;source=bpy.data.filepath
    sim=json.loads((a.run/'simulation_report.json').read_text());present=sim['physics'].get('car_present',True)
    if not present:
        roots=[o for o in bpy.data.objects if o.name.startswith('PCVE_ToyCar')]
        removed=set(roots)
        for o in roots:removed.update(o.children_recursive)
        for o in list(removed):bpy.data.objects.remove(o,do_unlink=True)
    water_present=sim['physics'].get('water_present',True)
    if not water_present:
        # DELETE water: the pool is empty, so the solved water, spray, mist and foam objects are removed.
        for name in NAMES.values():bpy.data.objects.remove(bpy.data.objects[name],do_unlink=True)
    frozen=static_signature()
    scene['PCVE_edit_id']=a.case_id;scene['PCVE_role']='edit';scene['PCVE_physics_json']=json.dumps(sim['physics'])
    scene['PCVE_solver']='Genesis 1.4.3; replayed baked geometry'
    if sim.get('mass_event'):
        scene['PCVE_mass_event_json']=json.dumps(sim['mass_event'])

    scene.frame_start=1;scene.frame_end=96;scene.render.fps=24
    proxy=bpy.data.objects.get('PCVE_ToyCarCollisionProxy')
    if proxy:proxy.animation_data_clear();proxy.rotation_mode='QUATERNION'
    for row in (sim['frames'] if proxy else []):
        proxy.location=row['car_pos'];proxy.rotation_quaternion=Quaternion(row['car_quat_wxyz'])
        proxy.keyframe_insert(data_path='location',frame=row['frame']);proxy.keyframe_insert(data_path='rotation_quaternion',frame=row['frame'])
        proxy['mass_kg']=row.get('car_mass_kg',sim['physics']['car_mass_kg'])
        proxy.keyframe_insert(data_path='["mass_kg"]',frame=row['frame'])
    for c in (proxy.animation_data.action.fcurves if proxy else []):
        for k in c.keyframe_points:k.interpolation='CONSTANT' if c.data_path=='["mass_kg"]' else 'LINEAR'
    objects={k:bpy.data.objects[n] for k,n in NAMES.items()} if water_present else {}
    for obj in objects.values():
        for m in list(obj.modifiers):
            assert m.type=='BOOLEAN',('Unexpected modifier',obj.name,m.type)
            obj.modifiers.remove(m)
        obj.hide_render=False;obj.data.name=obj.name+'_BoundedMesh'
    if not a.cache_only:base.configure_gpu(scene,a.samples)
    else:
        scene.render.engine='CYCLES';scene.cycles.samples=a.samples;scene.cycles.use_denoising=True
    scene.render.resolution_x=1280;scene.render.resolution_y=720
    scene.cycles.use_adaptive_sampling=True;scene.cycles.adaptive_threshold=.02
    scene.render.use_border=False;scene.render.use_crop_to_border=False;scene.render.use_motion_blur=False;scene.render.use_persistent_data=False
    def load_frame(f):
        row=sim['frames'][f-1]
        if proxy:proxy.location=row['car_pos'];proxy.rotation_quaternion=Quaternion(row['car_quat_wxyz'])
        return {kind:load_mesh(obj,a.bounded/f'{kind}_{f:04d}.npz') for kind,obj in objects.items()}
    frames=a.out/'frames';frames.mkdir(exist_ok=True);rows=[]
    for f in ([] if a.cache_only else parse_frames(a.frames)):
        target=frames/f'frame_{f:04d}.png'
        if a.reuse and target.exists():continue
        scene.frame_set(f);stats=load_frame(f);bpy.context.view_layer.update();hits=rays=None
        if water_present:
            water=objects['water'].evaluated_get(bpy.context.evaluated_depsgraph_get())
            hits=samples(water,sim['frames'][f-1],present)
            assert stats['water']['faces']>200000,('Missing water',f)
            rays=exterior_rays(scene);assert not any(r['water_in_front_of_shell'] for r in rays),('Exterior water overlap',f)
        scene.render.filepath=str(target);started=time.monotonic();bpy.ops.render.render(write_still=True)
        row={'frame':f,'render_seconds':time.monotonic()-started,'meshes':stats,'presence_rays':hits,'exterior_rays':rays,'runtime_boolean_count':0}
        rows.append(row);(a.out/f'render_report_{a.frames}.json').write_text(json.dumps(rows,indent=2));print('RENDER_FRAME',f,round(row['render_seconds'],2),flush=True)
    if a.package_cache:
        mats={k:list(o.data.materials) for k,o in objects.items()}
        # Alembic classifies handler-updated mesh data as static without an
        # animation source. A disabled non-subdivision modifier marks it as
        # time sampled without altering any exported vertex or normal.
        # Blender 4.3.2 IO_abstract_hierarchy_iterator check_is_animated().
        for obj in objects.values():
            marker=obj.modifiers.new('Export sampling marker','DISPLACE')
            marker.strength=0;marker.show_viewport=False;marker.show_render=False
        def handler(updated_scene,*_):
            f=int(updated_scene.frame_current)
            if 1<=f<=96:load_frame(f)
        bpy.app.handlers.frame_change_pre.append(handler);bpy.ops.object.select_all(action='DESELECT')
        for obj in objects.values():obj.select_set(True)
        bpy.context.view_layer.objects.active=objects['water'];scene.frame_set(1)
        cache=a.out/'liquid_animation.abc';started=time.monotonic()
        try:
            bpy.ops.wm.alembic_export(filepath=str(cache),start=1,end=96,selected=True,visible_objects_only=True,flatten=True,
                uvs=False,normals=True,vcolors=False,face_sets=False,export_hair=False,export_particles=False,
                as_background_job=False,use_instancing=False,xsamples=1,gsamples=1,evaluation_mode='RENDER',init_scene_frame_range=True)
        finally:bpy.app.handlers.frame_change_pre.remove(handler)
        seconds=time.monotonic()-started
        for obj in objects.values():
            mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
            if mesh.users==0:bpy.data.meshes.remove(mesh)
        before=set(bpy.data.objects);bpy.ops.wm.alembic_import(filepath=str(cache),relative_path=True,set_frame_range=True,always_add_cache_reader=True,as_background_job=False)
        imported=set(bpy.data.objects)-before;assert len([o for o in imported if o.type=='MESH'])==4
        for kind,name in NAMES.items():
            obj=next(o for o in imported if o.type=='MESH' and o.name.startswith(name));conflict=bpy.data.objects.get(name)
            if conflict and conflict!=obj:conflict.name=name+'_CacheTransform'
            obj.name=name;obj.data.materials.clear()
            for mat in mats[kind]:obj.data.materials.append(mat)
            assert not any(m.type=='BOOLEAN' for m in obj.modifiers)
        scene.frame_set(1);scene.render.filepath='//frames/frame_0001.png';assert static_signature()==frozen
        bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'scene_animation.blend'),compress=True)
        (a.out/'cache_manifest.json').write_text(json.dumps({'file':str(cache),'bytes':cache.stat().st_size,'export_seconds':seconds,'baked_basin_intersection':True,'runtime_boolean_count':0,'time_sampled_mesh_export':True},indent=2))
    assert static_signature()==frozen,'Approved scene changed'
    manifest_name='animation_manifest_cache.json' if a.cache_only else f'animation_manifest_{a.frames}.json'
    (a.out/manifest_name).write_text(json.dumps({'source':source,'run':str(a.run),'bounded':str(a.bounded),
        'render':{'resolution':[1280,720],'samples':a.samples,'fps':24,'frames':96,'seconds':4},'static_before':frozen,'static_after':static_signature(),
        'physics':sim['physics'],'case_id':a.case_id,'physical_run_recomputed':True,'baseline_low_yaw_source':True,'fix':'Bake exact basin intersection with self-intersection handling into cached evaluated meshes; no live Boolean in delivery'},indent=2))
    print('EDIT_RENDER_STAGE_DONE',a.case_id,a.frames,flush=True)
if __name__=='__main__':main()
