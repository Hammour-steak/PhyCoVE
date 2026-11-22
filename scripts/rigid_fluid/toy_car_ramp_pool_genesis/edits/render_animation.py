"""Render and package a cached Genesis animation in the accepted courtyard scene."""
import argparse,json,sys,time
from pathlib import Path
import bpy,numpy as np
from mathutils import Quaternion

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from geometry_helpers import load_state,replace_water_geometry,replace_spray_geometry,load_secondary
from repair_pool_water import base,protected_snapshot,lighting_state,exterior_rays

NAMES={'water':'PCVE_GenesisWater','spray':'PCVE_GenesisSpray','mist':'PCVE_GenesisMist','foam':'PCVE_GenesisFoam'}

def parse_frames(text):
    frames=set()
    for item in text.split(','):
        ends=list(map(int,item.split('-')));frames.update(range(ends[0],ends[-1]+1))
    return sorted(frames)

def static_signature():
    s=protected_snapshot();s.pop('frame',None)
    for name in list(s):
        if name.startswith(('PCVE_Genesis','PCVE_ToyCar')):s.pop(name)
    for name,record in s['fixed_geometry'].items():
        if name.startswith('PCVE_ToyCar'):record.pop('matrix',None)
    s['lighting']=lighting_state(bpy.context.scene)
    return s

def attach_containment(obj,cutter):
    if any(m.type=='BOOLEAN' for m in obj.modifiers):return
    m=obj.modifiers.new('Actual basin water boundary','BOOLEAN');m.operation='INTERSECT'
    m.solver='EXACT';m.object=cutter;m.use_hole_tolerant=True

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--frames',default='1-96');p.add_argument('--secondary',default='aniso_surface')
    p.add_argument('--package-cache',action='store_true');p.add_argument('--cache-only',action='store_true')
    p.add_argument('--samples',type=int,default=32);p.add_argument('--resolution',nargs=2,type=int,default=[1280,720])
    p.add_argument('--reuse',action='store_true')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);a.out.mkdir(parents=True,exist_ok=True)
    scene=bpy.context.scene;source=bpy.data.filepath;frozen=static_signature();report=json.loads((a.run/'simulation_report.json').read_text())
    count=report['numerics']['frames'];scene.frame_start=1;scene.frame_end=count;scene.render.fps=24
    proxy=bpy.data.objects['PCVE_ToyCarCollisionProxy'];proxy.animation_data_clear();proxy.rotation_mode='QUATERNION'
    assert proxy.rigid_body is None,'Unexpected active Blender rigid-body object'
    for row in report['frames']:
        proxy.location=row['car_pos'];proxy.rotation_quaternion=Quaternion(row['car_quat_wxyz'])
        proxy.keyframe_insert(data_path='location',frame=row['frame']);proxy.keyframe_insert(data_path='rotation_quaternion',frame=row['frame'])
    for curve in proxy.animation_data.action.fcurves:
        for key in curve.keyframe_points:key.interpolation='LINEAR'
    cutter=bpy.data.objects['Basin_Interior_Render_Clip'];cutter.data=cutter.data.copy()
    # The still-scene clip ended at 24 cm; the full sequence must retain high spray.
    zmax=max(v.co.z for v in cutter.data.vertices)
    for v in cutter.data.vertices:
        if v.co.z>zmax-.00001:v.co.z=.65
    cutter.data.update();cutter.hide_render=True
    objects={kind:bpy.data.objects[name] for kind,name in NAMES.items()}
    for obj in objects.values():attach_containment(obj,cutter);obj.hide_render=False
    base.configure_gpu(scene,a.samples);scene.render.resolution_x,scene.render.resolution_y=a.resolution
    scene.cycles.use_adaptive_sampling=True;scene.cycles.adaptive_threshold=.02
    scene.render.use_border=False;scene.render.use_crop_to_border=False;scene.render.use_motion_blur=False
    scene.render.use_persistent_data=False
    frames_dir=a.out/'frames';frames_dir.mkdir(exist_ok=True);rows=[]

    cache_export_mode=False
    def load_frame(frame):
        pos,quat,wp,wv,vertices,triangles=load_state(a.run,frame,a.secondary)
        proxy.location=pos.tolist();proxy.rotation_quaternion=Quaternion(quat.tolist())
        replace_water_geometry(objects['water'],vertices,triangles,in_place=cache_export_mode)
        stats={'source_water_vertices':len(vertices),'source_water_faces':len(triangles),'secondary':{}}
        for kind,cap in [('spray',1800),('mist',2600),('foam',3200)]:
            points,radii=load_secondary(a.run,a.secondary,frame,kind)
            original=len(points)
            if len(points)>cap:
                ids=np.linspace(0,len(points)-1,cap,dtype=int);points,radii=points[ids],radii[ids]
            replace_spray_geometry(objects[kind],points,radii,in_place=cache_export_mode)
            stats['secondary'][kind]={'source_count':original,'rendered_count':len(points)}
        return stats

    for frame in ([] if a.cache_only else parse_frames(a.frames)):
        target=frames_dir/f'frame_{frame:04d}.png'
        if a.reuse and target.exists():continue
        scene.frame_set(frame);stats=load_frame(frame);bpy.context.view_layer.update()
        rays=exterior_rays(scene)
        assert not any(r['water_in_front_of_shell'] for r in rays),('Exterior water overlap',frame)
        scene.render.filepath=str(target);started=time.monotonic();bpy.ops.render.render(write_still=True)
        row={'frame':frame,'render_seconds':time.monotonic()-started,'water_containment_rays_passed':True,**stats}
        rows.append(row);(a.out/('render_report_'+a.frames.replace(',','_')+'.json')).write_text(json.dumps(rows,indent=2))
        print('ANIMATION_RENDER',json.dumps(row),flush=True)

    native=None;cache=None
    if a.package_cache:
        cache_export_mode=True
        mats={kind:list(obj.data.materials) for kind,obj in objects.items()}
        for obj in objects.values():
            obj.data.name=obj.name+'_AnimatedMesh'
            for mod in obj.modifiers:
                if mod.type=='BOOLEAN':mod.show_render=False;mod.show_viewport=False
        def frame_handler(updated_scene,*_):
            frame=int(updated_scene.frame_current)
            if 1<=frame<=count:load_frame(frame)
        bpy.app.handlers.frame_change_pre.append(frame_handler)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects.values():obj.select_set(True)
        bpy.context.view_layer.objects.active=objects['water'];scene.frame_set(1)
        cache=a.out/'liquid_animation.abc';started=time.monotonic()
        try:
            bpy.ops.wm.alembic_export(filepath=str(cache),start=1,end=count,selected=True,
                visible_objects_only=True,flatten=True,uvs=False,normals=True,vcolors=False,
                face_sets=False,export_hair=False,export_particles=False,as_background_job=False,use_instancing=False,
                xsamples=1,gsamples=1,evaluation_mode='RENDER',init_scene_frame_range=True)
        finally:bpy.app.handlers.frame_change_pre.remove(frame_handler)
        cache_seconds=time.monotonic()-started
        for obj in objects.values():
            mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
            if mesh.users==0:bpy.data.meshes.remove(mesh)
        before=set(bpy.data.objects)
        bpy.ops.wm.alembic_import(filepath=str(cache),relative_path=True,set_frame_range=True,
            always_add_cache_reader=True,as_background_job=False)
        imported=set(bpy.data.objects)-before
        assert len([o for o in imported if o.type=='MESH'])==4,'Unexpected Alembic mesh schemas'
        for kind,name in NAMES.items():
            obj=next(o for o in imported if o.type=='MESH' and o.name.startswith(name))
            conflict=bpy.data.objects.get(name)
            if conflict and conflict!=obj:conflict.name=name+'_CacheTransform'
            obj.name=name;obj.data.materials.clear()
            for mat in mats[kind]:obj.data.materials.append(mat)
            attach_containment(obj,cutter)
            assert bpy.data.objects[name]==obj and any(m.type=='BOOLEAN' for m in obj.modifiers)
        scene.frame_set(1);scene.render.filepath='//frames/frame_0001.png'
        assert static_signature()==frozen,'Frozen environment/camera/light changed'
        bpy.ops.file.pack_all();native=a.out/'scene_animation.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(native),compress=True)
        cache_info={'file':str(cache),'seconds':cache_seconds,'bytes':cache.stat().st_size}
        (a.out/'animation_cache.json').write_text(json.dumps(cache_info,indent=2))
    assert static_signature()==frozen,'Environment, camera or lighting changed'
    record={'source':source,'run':str(a.run),'frames':parse_frames(a.frames),'cache_only':a.cache_only,
        'render':{'resolution':a.resolution,'samples':a.samples,'fps':24,'frames':count,'seconds':count/24},
        'static_before':frozen,'static_after':static_signature(),'source_car_mapping':'Source BlenderKit -Y mapped to Genesis +X, retained',
        'containment':'Measured actual basin below the rim; extended free space above rim to retain legitimate spray',
        'cache':str(cache) if cache else None,'native':str(native) if native else None}
    (a.out/('animation_manifest_cache.json' if a.cache_only else 'animation_manifest_'+a.frames.replace(',','_')+'.json')).write_text(json.dumps(record,indent=2))
    print('ANIMATION_STAGE_DONE',a.frames,flush=True)

if __name__=='__main__':main()
