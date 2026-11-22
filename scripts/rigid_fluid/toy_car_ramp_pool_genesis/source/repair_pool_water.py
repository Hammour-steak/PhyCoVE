"""Contain the reconstructed liquid inside the actual 3D basin, appearance only."""
import argparse,bmesh,hashlib,json,math,sys,time
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from refine_scene import base,protected_snapshot,lighting_state

SUSPECT_PIXELS=[(1644,793),(1640,804),(1650,820),(1600,810),(1690,820)]

def geometry_hash(mesh):
    v=np.empty(len(mesh.vertices)*3,dtype=np.float32);mesh.vertices.foreach_get('co',v)
    ids=np.empty(len(mesh.loops),dtype=np.int32);mesh.loops.foreach_get('vertex_index',ids)
    return hashlib.sha256(v.tobytes()+ids.tobytes()).hexdigest()

def topology(mesh):
    bm=bmesh.new();bm.from_mesh(mesh)
    result={'vertices':len(bm.verts),'faces':len(bm.faces),'boundary_edges':sum(e.is_boundary for e in bm.edges),
        'nonmanifold_edges':sum(not e.is_manifold for e in bm.edges)}
    bm.free();return result

def pixel_ray(scene,x,y):
    cam=scene.camera;frame=cam.data.view_frame(scene=scene)
    u=x/1920;v=1-y/1080
    corner=Vector((min(p.x for p in frame)+(max(p.x for p in frame)-min(p.x for p in frame))*u,
        min(p.y for p in frame)+(max(p.y for p in frame)-min(p.y for p in frame))*v,frame[0].z))
    return cam.matrix_world.translation,(cam.matrix_world.to_3x3()@corner).normalized()

def hit_object(obj,origin,direction):
    inv=obj.matrix_world.inverted();hit,loc,normal,index=obj.ray_cast(inv@origin,inv.to_3x3()@direction)
    if not hit:return None
    p=obj.matrix_world@loc
    return {'distance':(p-origin).length,'world':list(p),'face':index}

def exterior_rays(scene):
    bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get()
    pool=bpy.data.objects['Childrens Inflatable Pool.001'].evaluated_get(deps)
    water=bpy.data.objects['PCVE_GenesisWater'].evaluated_get(deps)
    result=[]
    for x,y in SUSPECT_PIXELS:
        origin,direction=pixel_ray(scene,x,y);p=hit_object(pool,origin,direction);w=hit_object(water,origin,direction)
        result.append({'pixel':[x,y],'pool':p,'water':w,'water_in_front_of_shell':bool(p and w and w['distance']<p['distance']-.001)})
    return result

def dry_paving():
    obj=bpy.data.objects['ScannedPatio_TrueRelief'];old=obj.data.materials[0]
    mat=old.copy();mat.name='Dry_Concrete_Paving';obj.data.materials[0]=mat
    nodes,links=mat.node_tree.nodes,mat.node_tree.links;bs=nodes.get('Principled BSDF')
    for name,input_name in [('Dry to damp colour','Base Color'),('Dry to damp roughness','Roughness')]:
        source=nodes[name].inputs[1].links[0].from_socket;links.new(source,bs.inputs[input_name])
    return {'before':old.name,'after':mat.name,'pool_and_hose_static_moisture_removed':True,
            'registered_paving_ao_retained':True}

def basin_volume(pool,water,overlap=.001):
    points=[pool.matrix_world@Vector(c) for c in pool.bound_box]
    cx=(min(p.x for p in points)+max(p.x for p in points))/2
    cy=(min(p.y for p in points)+max(p.y for p in points))/2
    zlip=max(p.z for p in points);inv=pool.matrix_world.inverted()
    water_z=[(water.matrix_world@Vector(c)).z for c in water.bound_box]
    bottom=min(water_z)-.006;top=max(max(water_z)+.03,zlip+.03)
    # Horizontal first-hit rays measure the real inflated inner wall at each height.
    # This captures the rounded corners and all three air-ring profiles.
    zrows=list(np.arange(bottom,zlip+.001,.002,dtype=float));zrows.extend([zlip+.002,top])
    count=256;vertices=[];faces=[];misses=0;radius_limit=3.0
    for z in zrows:
        origin=Vector((cx,cy,z))
        for i in range(count):
            angle=i*math.tau/count;direction=Vector((math.cos(angle),math.sin(angle),0))
            hit,local,n,index=pool.ray_cast(inv@origin,inv.to_3x3()@direction)
            if hit:radius=(pool.matrix_world@local-origin).length+overlap
            else:radius=radius_limit;misses+=1
            p=origin+direction*radius;vertices.append(tuple(p))
    for j in range(len(zrows)-1):
        for i in range(count):
            ni=(i+1)%count
            faces.append((j*count+i,j*count+ni,(j+1)*count+ni,(j+1)*count+i))
    faces.append(tuple(reversed(range(count))))
    faces.append(tuple((len(zrows)-1)*count+i for i in range(count)))
    mesh=bpy.data.meshes.new('Measured_Basin_Interior_Volume');mesh.from_pydata(vertices,[],faces);mesh.update()
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
    col=bpy.data.collections.new('Actual_Basin_Water_Boundary');bpy.context.scene.collection.children.link(col)
    obj=bpy.data.objects.new('Basin_Interior_Render_Clip',mesh);col.objects.link(obj)
    obj.display_type='WIRE';obj.hide_render=True;obj.hide_set(True)
    assert topology(mesh)['nonmanifold_edges']==0
    return obj,{'center_xy_m':[cx,cy],'angular_samples':count,'height_step_m':.002,
        'height_rows':len(zrows),'height_range_m':[bottom,top],'inside_wall_overlap_m':overlap,
        'upper_air_ray_misses':misses,'method':'Per-height radial first intersections against the unmodified watertight original pool shell',
        'collision_or_solver_object':False}

def repair(scene):
    pool=bpy.data.objects['Childrens Inflatable Pool.001'];water=bpy.data.objects['PCVE_GenesisWater']
    pool_hash=geometry_hash(pool.data);water_hash=geometry_hash(water.data)
    result={'source':bpy.data.filepath,'protected_before':protected_snapshot(),'lighting_before':lighting_state(scene),
        'rays_before':exterior_rays(scene),'pool_topology':topology(pool.data),'water_source_topology':topology(water.data)}
    cutter,record=basin_volume(pool,water);result['basin']=record
    modifier=water.modifiers.new('Clip water to actual rounded basin','BOOLEAN')
    modifier.operation='INTERSECT';modifier.solver='EXACT';modifier.object=cutter;modifier.use_hole_tolerant=True
    started=time.monotonic();bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get()
    evaluated=water.evaluated_get(deps);mesh=evaluated.to_mesh()
    result['water_evaluated_topology']=topology(mesh);result['water_evaluated_sha256']=geometry_hash(mesh)
    result['intersection_seconds']=time.monotonic()-started
    assert len(mesh.polygons)>len(water.data.polygons)*.50,'Unexpectedly lost the main liquid surface'
    evaluated.to_mesh_clear()
    result['paving']=dry_paving();result['rays_after']=exterior_rays(scene)
    assert any(r['water_in_front_of_shell'] for r in result['rays_before'])
    assert not any(r['water_in_front_of_shell'] for r in result['rays_after']),'Water still covers the outer shell'
    result['protected_after']=protected_snapshot();result['lighting_after']=lighting_state(scene)
    assert result['protected_before']==result['protected_after'],'Original geometry, camera or physics was edited'
    assert result['lighting_before']==result['lighting_after']
    assert pool_hash==geometry_hash(pool.data) and water_hash==geometry_hash(water.data)
    result.update({'pool_visual_geometry_and_uv_unchanged':True,'source_water_mesh_unchanged':True,
        'water_render_geometry':'New reversible 3D Boolean intersection with measured basin interior',
        'pool_hash':pool_hash,'water_source_hash':water_hash,'appearance_only':True,
        'scope':'Frame-32 render-mesh containment repair; no full Genesis cache or physics rebake is claimed.'})
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--save',action='store_true');p.add_argument('--beauty',action='store_true');p.add_argument('--crop',action='store_true')
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);args.out.mkdir(parents=True,exist_ok=True)
    scene=bpy.context.scene;started=time.monotonic();record=repair(scene);record['repair_seconds']=time.monotonic()-started
    base.configure_gpu(scene,64 if args.crop else 32);scene.render.resolution_x=1920 if args.crop else 1280;scene.render.resolution_y=1080 if args.crop else 720
    scene.cycles.use_adaptive_sampling=True;scene.cycles.adaptive_threshold=.01 if args.crop else .02
    scene.render.use_border=args.crop;scene.render.use_crop_to_border=args.crop
    if args.crop:
        scene.render.border_min_x=1320/1920;scene.render.border_max_x=1900/1920
        scene.render.border_min_y=(1080-1010)/1080;scene.render.border_max_y=(1080-600)/1080
    record['renders']={}
    scene.render.filepath=str(args.out/('repaired_crop.png' if args.crop else 'after.png'));started=time.monotonic()
    bpy.ops.render.render(write_still=True);record['renders']['preview_seconds']=time.monotonic()-started
    if args.beauty:
        scene.render.resolution_x=1920;scene.render.resolution_y=1080;scene.cycles.samples=128;scene.cycles.adaptive_threshold=.008
        scene.render.filepath=str(args.out/'beauty_1080p.png');started=time.monotonic()
        bpy.ops.render.render(write_still=True);record['renders']['beauty_seconds']=time.monotonic()-started
    if args.save:
        scene.render.use_border=False;scene.render.use_crop_to_border=False;bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=str(args.out/'scene_pool_corrected.blend'),compress=True)
    (args.out/'repair_manifest.json').write_text(json.dumps(record,indent=2));print('POOL_WATER_REPAIRED',args.out,flush=True)

if __name__=='__main__':main()
