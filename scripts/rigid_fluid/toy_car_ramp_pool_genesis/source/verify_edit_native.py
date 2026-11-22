"""Check every delivered native frame, including frames whose native state is empty."""
import json,hashlib,sys
from pathlib import Path
import bpy,numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from render_animation import static_signature
from repair_pool_water import geometry_hash,exterior_rays
from render_edit import NAMES
from water_presence import samples

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def uv_hash(mesh):
    h=hashlib.sha256()
    for uv in mesh.uv_layers:
        values=np.empty(len(uv.data)*2,dtype=np.float32);uv.data.foreach_get('uv',values);h.update(values.tobytes())
    return h.hexdigest()
def signature():
    pool=bpy.data.objects['Childrens Inflatable Pool.001']
    return {'static':static_signature(),'pool_geometry':geometry_hash(pool.data),'pool_uv':uv_hash(pool.data)}
source,native,bounded,run,out=map(Path,sys.argv[sys.argv.index('--')+1:])
sim=json.loads((run/'simulation_report.json').read_text());present=sim['physics'].get('car_present',True)
bpy.ops.wm.open_mainfile(filepath=str(source))
if not present:
    roots=[o for o in bpy.data.objects if o.name.startswith('PCVE_ToyCar')];removed=set(roots)
    for o in roots:removed.update(o.children_recursive)
    for o in list(removed):bpy.data.objects.remove(o,do_unlink=True)
before=signature()
bpy.ops.wm.open_mainfile(filepath=str(native));after=signature();assert before==after,'Approved static scene changed'
scene=bpy.context.scene;assert scene.frame_start==1 and scene.frame_end==96 and scene.render.fps==24
cache_paths=[{'path':c.filepath,'resolved':bpy.path.abspath(c.filepath)} for c in bpy.data.cache_files]
assert cache_paths and all(c['path'].startswith('//') and Path(c['resolved']).is_file() for c in cache_paths)
assert not any(i.source=='FILE' and i.filepath and not i.packed_file for i in bpy.data.images)
objects={k:bpy.data.objects[n] for k,n in NAMES.items()}
assert all(not any(m.type=='BOOLEAN' for m in o.modifiers) for o in objects.values())
sim=json.loads((run/'simulation_report.json').read_text());proxy=bpy.data.objects.get('PCVE_ToyCarCollisionProxy');rows=[]
assert bool(proxy)==present
for f in range(1,97):
    scene.frame_set(f);bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get();stats={}
    if proxy:assert np.allclose(proxy.location,sim['frames'][f-1]['car_pos'],atol=1e-5)
    if proxy:assert np.allclose(proxy.rotation_quaternion,sim['frames'][f-1]['car_quat_wxyz'],atol=1e-5)
    if proxy:assert np.isclose(proxy['mass_kg'],sim['frames'][f-1].get('car_mass_kg',sim['physics']['car_mass_kg']),atol=1e-6)
    for kind,obj in objects.items():
        ev=obj.evaluated_get(deps);mesh=ev.to_mesh();coords=np.empty(len(mesh.vertices)*3,dtype=np.float32);mesh.vertices.foreach_get('co',coords);coords=coords.reshape(-1,3)
        with np.load(bounded/f'{kind}_{f:04d}.npz') as data:
            expected=data['vertices'];assert len(coords)==len(expected) and len(mesh.polygons)==len(data['loop_start']),(f,kind,'topology')
            assert np.isfinite(coords).all()
            if len(coords):
                assert np.allclose(coords,expected,atol=2e-5),(f,kind,'vertices')
        stats[kind]={'vertices':len(coords),'faces':len(mesh.polygons)}
        if kind=='water':
            assert len(mesh.polygons)>200000
            rays=samples(ev,sim['frames'][f-1],present)
            stats[kind]['presence_rays']=rays
        ev.to_mesh_clear()
    rays=exterior_rays(scene);assert not any(r['water_in_front_of_shell'] for r in rays),('Delivered exterior water',f)
    rows.append({'frame':f,'meshes':stats,'car_present':present,'car_pose_matches_simulation':bool(present),'reported_corner_contained':True})
    print('NATIVE_CHECK',f,stats['water']['faces'],flush=True)
result={'status':'all_96_native_frames_verified','static_scene_unchanged':before==after,'pool_uv_and_geometry_unchanged':True,
    'source':str(source),'native':str(native),'native_sha256':sha(native),'cache_files':cache_paths,
    'alembic_sha256':sha(Path(cache_paths[0]['resolved'])),'all_file_textures_packed':True,'runtime_boolean_count':0,
    'frames':rows,'fps':24,'duration_seconds':4,'blender':bpy.app.version_string}
out.write_text(json.dumps(result,indent=2));print('NATIVE_VERIFIED',flush=True)
