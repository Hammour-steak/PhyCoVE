"""Bind genuinely re-solved tea to the accepted environment scene and camera."""
import argparse
import json
import sys
import time
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
from tea_environment_state import protected_state,environment_state,digest,file_hash

p=argparse.ArgumentParser()
p.add_argument('case',type=Path)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
case=a.case.resolve()
assert not (case/'genesis_liquid_cache.abc').exists()
source=Path(bpy.data.filepath).resolve()
assert source!=case/'scene_tea_fixed.blend','Keep the input environment/scene and new target independent'
source_hash=file_hash(source)
scene=bpy.context.scene
scene.frame_set(72); bpy.context.view_layer.update()
locked_before=protected_state(); environment_before=environment_state()
source_caches={bpy.path.abspath(c.filepath):file_hash(Path(bpy.path.abspath(c.filepath))) for c in bpy.data.cache_files}
surface=bpy.data.objects['GenesisTeaSurface']
materials=list(surface.data.materials)
for modifier in list(surface.modifiers): surface.modifiers.remove(modifier)
surface.data=bpy.data.meshes.new('GenesisTeaContactMesh')
for m in materials: surface.data.materials.append(m)
for cache in list(bpy.data.cache_files):
    assert cache.users==0
    bpy.data.batch_remove(ids=(cache,))
def load_frame(f):
    with np.load(case/f'surfaces/frame_{f:04d}.npz') as z:
        v,t,n,velocity=z['vertices'],z['triangles'],z['normals'],z['velocity']
    mesh=surface.data; mesh.clear_geometry()
    mesh.from_pydata(v.tolist(),[],t.tolist()); mesh.update()
    mesh.polygons.foreach_set('use_smooth',np.ones(len(mesh.polygons),dtype=bool))
    if len(n): mesh.normals_split_custom_set_from_vertices(n.tolist())
    attr=mesh.attributes.get('velocity') or mesh.attributes.new('velocity','FLOAT_VECTOR','POINT')
    attr.data.foreach_set('vector',velocity.ravel())
    mesh.update_tag(); surface.update_tag()
def handler(current_scene): load_frame(current_scene.frame_current)
sampling=surface.modifiers.new('SequenceSamplingIdentity','TRIANGULATE')
if hasattr(sampling,'keep_custom_normals'): sampling.keep_custom_normals=True
bpy.app.handlers.frame_change_pre.append(handler)
bpy.ops.object.select_all(action='DESELECT'); surface.select_set(True)
bpy.context.view_layer.objects.active=surface
scene.frame_start,scene.frame_end=1,96
scene.frame_set(1)
start=time.monotonic()
bpy.ops.wm.alembic_export(filepath=str(case/'genesis_liquid_cache.abc'),start=1,end=96,
                         selected=True,flatten=True,visible_objects_only=False,as_background_job=False)
bpy.app.handlers.frame_change_pre.remove(handler)
bpy.data.objects.remove(surface,do_unlink=True)
old=set(bpy.data.objects)
bpy.ops.wm.alembic_import(filepath=str(case/'genesis_liquid_cache.abc'),as_background_job=False)
imported=[o for o in set(bpy.data.objects)-old if o.type=='MESH']
assert len(imported)==1
surface=imported[0]; surface.name='GenesisTeaSurface'
surface.data.materials.clear()
for m in materials: surface.data.materials.append(m)
assert len(bpy.data.cache_files)==1
cache=bpy.data.cache_files[0]
cache.filepath=str(case/'genesis_liquid_cache.abc')
scene.frame_set(72); bpy.context.view_layer.update()
locked_after=protected_state(); environment_after=environment_state()
assert digest(locked_before)==digest(locked_after),'Hero, camera, tea material, supports or original quality changed'
assert digest(environment_before)==digest(environment_after),'Environment or lighting changed'
scene['pcve_contact_revision']='finite_support_contact'
scene['pcve_physical_case']=str(case)
scene['pcve_contact_revision_note']='Fixed finite particle contact skin on table/coaster; re-solved all96 frames; no particle, mesh or wetting-film overlays.'
bpy.ops.wm.save_as_mainfile(filepath=str(case/'scene_tea_fixed.blend'),check_existing=False,relative_remap=False)
cache.filepath='//genesis_liquid_cache.abc'
bpy.ops.wm.save_as_mainfile(filepath=str(case/'scene_tea_fixed.blend'),check_existing=False,relative_remap=False)
assert source_hash==file_hash(source)
for path,h in source_caches.items(): assert file_hash(Path(path))==h
report={'source_blend':str(source),'source_sha256':source_hash,'source_caches_preserved':source_caches,
        'protected_before':locked_before,'protected_after':locked_after,'protected_sha256':digest(locked_after),
        'environment_sha256_before':digest(environment_before),'environment_sha256_after':digest(environment_after),
        'native_cache_sha256':file_hash(case/'genesis_liquid_cache.abc'),
        'native_export_seconds':time.monotonic()-start,'all_textures_packed':all(im.packed_file for im in bpy.data.images if im.source=='FILE' and im.users),
        'requires_python_playback_handler':False,'simulation_recomputed':True,'source_versions_preserved':True}
(case/'scene_revision.json').write_text(json.dumps(report,indent=2)+'\n')
print('TEA_CONTACT_NATIVE_PREPARED',flush=True)
