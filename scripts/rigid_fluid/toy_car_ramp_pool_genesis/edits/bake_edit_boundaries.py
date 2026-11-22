"""Bake robust exact basin intersections once, retaining evaluated shading."""
import argparse,json,sys,time
from pathlib import Path
import bpy,numpy as np
from mathutils import Quaternion

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from geometry_helpers import load_state,load_secondary,replace_water_geometry,replace_spray_geometry
from repair_pool_water import exterior_rays
from water_presence import samples

NAMES={'water':'PCVE_GenesisWater','spray':'PCVE_GenesisSpray','mist':'PCVE_GenesisMist','foam':'PCVE_GenesisFoam'}
POINTS=[(.1,0),(.3,0),(.5,0),(.7,0),(.9,0),(.3,-.15),(.5,-.15),(.7,-.15),(.3,.15),(.5,.15),(.7,.15)]

def snapshot(mesh):
    data={}
    for name,collection,prop,shape,dtype in [
        ('vertices',mesh.vertices,'co',(len(mesh.vertices),3),np.float32),
        ('loop_vertex',mesh.loops,'vertex_index',(len(mesh.loops),),np.int32),
        ('loop_start',mesh.polygons,'loop_start',(len(mesh.polygons),),np.int32),
        ('loop_total',mesh.polygons,'loop_total',(len(mesh.polygons),),np.int32),
        ('smooth',mesh.polygons,'use_smooth',(len(mesh.polygons),),np.bool_),
        ('material_index',mesh.polygons,'material_index',(len(mesh.polygons),),np.int32),
        ('corner_normals',mesh.corner_normals,'vector',(len(mesh.loops),3),np.float32)]:
        array=np.empty(shape,dtype=dtype);collection.foreach_get(prop,array.ravel());data[name]=array
    return data

def volume(mesh):
    mesh.calc_loop_triangles();v=np.empty(len(mesh.vertices)*3,dtype=np.float32);mesh.vertices.foreach_get('co',v);v=v.reshape(-1,3)
    t=np.empty(len(mesh.loop_triangles)*3,dtype=np.int32);mesh.loop_triangles.foreach_get('vertices',t);t=t.reshape(-1,3)
    return float(np.sum(np.einsum('ij,ij->i',v[t[:,0]],np.cross(v[t[:,1]],v[t[:,2]])))/6)

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--start',type=int,required=True);p.add_argument('--end',type=int,required=True);p.add_argument('--strip-unrelated',action='store_true')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);a.out.mkdir(parents=True,exist_ok=True)
    scene=bpy.context.scene
    if a.strip_unrelated:
        keep={bpy.data.objects[n] for n in NAMES.values()}
        keep.update([bpy.data.objects['Basin_Interior_Render_Clip'],bpy.data.objects['PCVE_ToyCarCollisionProxy'],bpy.data.objects['Childrens Inflatable Pool.001'],scene.camera])
        if scene.camera.data.dof.focus_object:keep.add(scene.camera.data.dof.focus_object)
        for obj in list(keep):
            parent=obj.parent
            while parent:keep.add(parent);parent=parent.parent
        for obj in list(bpy.data.objects):
            if obj not in keep:bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.orphans_purge(do_local_ids=True,do_linked_ids=True,do_recursive=True)
        bpy.context.view_layer.update()
    cutter=bpy.data.objects['Basin_Interior_Render_Clip']
    zmax=max(v.co.z for v in cutter.data.vertices)
    for v in cutter.data.vertices:
        if v.co.z>zmax-.00001:v.co.z=.65
    cutter.data.update();objects={k:bpy.data.objects[n] for k,n in NAMES.items()}
    for obj in objects.values():
        mod=next((m for m in obj.modifiers if m.type=='BOOLEAN'),None)
        if mod is None:mod=obj.modifiers.new('robust basin boundary','BOOLEAN')
        mod.operation='INTERSECT';mod.solver='EXACT';mod.object=cutter;mod.use_self=True;mod.use_hole_tolerant=True
        mod.show_viewport=True;mod.show_render=True
    sim=json.loads((a.run/'simulation_report.json').read_text());present=sim['physics'].get('car_present',True)
    existing={}
    for path in a.out.glob('bake_report_*.json'):
        try:
            for row in json.loads(path.read_text()):existing[row['frame']]=row
        except json.JSONDecodeError:pass
    rows=[];proxy=bpy.data.objects['PCVE_ToyCarCollisionProxy'];proxy.rotation_mode='QUATERNION'
    for frame in range(a.start,a.end+1):
        if frame in existing and all((a.out/f'{kind}_{frame:04d}.npz').is_file() for kind in NAMES):
            rows.append(existing[frame]);(a.out/f'bake_report_{a.start}-{a.end}.json').write_text(json.dumps(rows,indent=2))
            print('BOUNDARY_REUSE_VALIDATED',frame,flush=True);continue
        started=time.monotonic();scene.frame_set(frame)
        pos,quat,wp,wv,v,t=load_state(a.run,frame,'aniso_surface_clean')
        raw_volume=float(np.sum(np.einsum('ij,ij->i',v[t[:,0]],np.cross(v[t[:,1]],v[t[:,2]])))/6)
        proxy.location=pos.tolist();proxy.rotation_quaternion=Quaternion(quat.tolist())
        replace_water_geometry(objects['water'],v,t)
        for kind,cap in [('spray',1800),('mist',2600),('foam',3200)]:
            points,radii=load_secondary(a.run,'aniso_surface_clean',frame,kind)
            if len(points)>cap:
                ids=np.linspace(0,len(points)-1,cap,dtype=int);points,radii=points[ids],radii[ids]
            replace_spray_geometry(objects[kind],points,radii)
        bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get();stats={}
        for kind,obj in objects.items():
            ev=obj.evaluated_get(deps);mesh=ev.to_mesh();data=snapshot(mesh)
            stats[kind]={'vertices':len(mesh.vertices),'faces':len(mesh.polygons),'solid_volume_m3':volume(mesh) if len(mesh.polygons) else 0}
            if kind=='water':
                hits=samples(ev,sim['frames'][frame-1],present)
                assert stats[kind]['faces']>200000,('Main surface lost',frame,stats[kind])
                assert .94<stats[kind]['solid_volume_m3']/raw_volume<1.01,('Unexpected lost volume',frame,raw_volume,stats[kind])
                stats[kind]['presence_rays']=hits;stats[kind]['raw_volume_m3']=raw_volume
            target=a.out/f'{kind}_{frame:04d}.npz';tmp=target.with_suffix('.tmp')
            with tmp.open('wb') as f:np.savez_compressed(f,**data)
            tmp.replace(target);ev.to_mesh_clear()
        rays=exterior_rays(scene);assert not any(r['water_in_front_of_shell'] for r in rays),('Exterior water overlay',frame)
        row={'frame':frame,'seconds':time.monotonic()-started,'meshes':stats,'exterior_rays':rays,'robust_self_intersection':True}
        rows.append(row);(a.out/f'bake_report_{a.start}-{a.end}.json').write_text(json.dumps(rows,indent=2));print('BOUNDARY_BAKED',frame,round(row['seconds'],2),stats['water']['faces'],flush=True)
    print('BOUNDARY_CHUNK_DONE',a.start,a.end,flush=True)
if __name__=='__main__':main()
