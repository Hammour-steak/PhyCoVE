"""Bind solver particles to the accepted environment, including empty-time states."""
import argparse
import copy
import json
import sys
import time
from pathlib import Path
import bpy
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tea_environment_state import protected_state, environment_state, digest, file_hash, mesh_hash, material_state
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('case',type=Path)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
case=a.case.resolve(); source=Path(bpy.data.filepath).resolve()
assert source!=case/'scene.blend'
experiment=json.loads((case/'experiment.json').read_text())
delete_frame=experiment['after']['deletion_frame']
scene=bpy.context.scene
source_hash=file_hash(source)
source_caches={bpy.path.abspath(c.filepath):file_hash(Path(bpy.path.abspath(c.filepath))) for c in bpy.data.cache_files}
scene.frame_set(72);bpy.context.view_layer.update()
def extra_environment():
    return {o.name:{'mesh':mesh_hash(o.data),'matrix':[list(r) for r in o.matrix_world],
                    'hide_render':o.hide_render,'materials':[material_state(m) for m in o.data.materials if m]}
            for o in scene.objects if o.name.startswith('Env17_') and o.type=='MESH'}
locked_before=protected_state(); env_before=environment_state(); extra_before=extra_environment()
# Record all non-liquid animation transforms, not just the accepted sample.
trajectory_before={}
for f in range(1,97):
    scene.frame_set(f)
    trajectory_before[str(f)]={o.name:[list(r) for r in o.matrix_world] for o in scene.objects if o.type in ('MESH','CAMERA','LIGHT') and o.name!='GenesisTeaSurface'}
surface=bpy.data.objects['GenesisTeaSurface'];materials=list(surface.data.materials)
for m in list(surface.modifiers): surface.modifiers.remove(m)
surface.data=bpy.data.meshes.new('EditedTeaMesh')
for m in materials: surface.data.materials.append(m)
for c in list(bpy.data.cache_files):
    assert c.users==0
    bpy.data.batch_remove(ids=(c,))
def load_frame(f):
    with np.load(case/f'surfaces/frame_{f:04d}.npz') as z:
        v,t,n,velocity=z['vertices'],z['triangles'],z['normals'],z['velocity']
    mesh=surface.data
    mesh.clear_geometry()
    if len(v):
        mesh.vertices.add(len(v));mesh.vertices.foreach_set('co',v.ravel())
        mesh.loops.add(t.size);mesh.loops.foreach_set('vertex_index',t.ravel())
        mesh.polygons.add(len(t));mesh.polygons.foreach_set('loop_start',np.arange(0,t.size,3))
        mesh.polygons.foreach_set('use_smooth',np.ones(len(t),bool));mesh.update();mesh.validate(clean_customdata=False)
        mesh.normals_split_custom_set_from_vertices(n.tolist())
        attr=mesh.attributes.get('velocity') or mesh.attributes.new('velocity','FLOAT_VECTOR','POINT');attr.data.foreach_set('vector',velocity.ravel())
    mesh.update_tag();surface.update_tag()
start=time.monotonic()
if delete_frame!=1:
    def handler(current_scene):load_frame(current_scene.frame_current)
    sampling=surface.modifiers.new('SequenceSamplingIdentity','TRIANGULATE')
    if hasattr(sampling,'keep_custom_normals'):sampling.keep_custom_normals=True
    bpy.app.handlers.frame_change_pre.append(handler)
    bpy.ops.object.select_all(action='DESELECT');surface.select_set(True);bpy.context.view_layer.objects.active=surface
    scene.frame_start,scene.frame_end=1,96;scene.frame_set(1)
    bpy.ops.wm.alembic_export(filepath=str(case/'genesis_liquid_cache.abc'),start=1,end=96,
        selected=True,flatten=True,visible_objects_only=False,as_background_job=False)
    bpy.app.handlers.frame_change_pre.remove(handler)
    bpy.data.objects.remove(surface,do_unlink=True);old=set(bpy.data.objects)
    bpy.ops.wm.alembic_import(filepath=str(case/'genesis_liquid_cache.abc'),as_background_job=False)
    imported=[o for o in set(bpy.data.objects)-old if o.type=='MESH'];assert len(imported)==1
    surface=imported[0];surface.name='GenesisTeaSurface';surface.data.materials.clear()
    for m in materials:surface.data.materials.append(m)
    assert len(bpy.data.cache_files)==1
    cache=bpy.data.cache_files[0];cache.filepath=str(case/'genesis_liquid_cache.abc');cache.velocity_name='.velocities';cache.velocity_unit='SECOND'
else:
    load_frame(1)
# Keyed visibility gives explicit native playback semantics even in applications
# that retain the final nonempty Alembic sample after an empty topology sample.
if delete_frame is not None:
    for f,hidden in [(1,delete_frame==1),(max(1,delete_frame-1),delete_frame==1),(delete_frame,True)]:
        for prop in ('hide_render','hide_viewport'):
            setattr(surface,prop,hidden);surface.keyframe_insert(prop,frame=f)
    for curve in surface.animation_data.action.fcurves:
        for point in curve.keyframe_points:point.interpolation='CONSTANT'
scene.frame_set(72);bpy.context.view_layer.update()
locked_after=protected_state();expected=copy.deepcopy(locked_before)
expected['visibility']['GenesisTeaSurface']=locked_after['visibility']['GenesisTeaSurface']
expected['hero_and_tea_materials']['GenesisTeaSurface']=locked_after['hero_and_tea_materials']['GenesisTeaSurface']
assert digest(expected)==digest(locked_after),'Non-target hero, optics, camera or support changed'
assert digest(env_before)==digest(environment_state())
assert digest(extra_before)==digest(extra_environment())
checks={}
for f in range(1,97):
    scene.frame_set(f);bpy.context.view_layer.update()
    trajectory={o.name:[list(r) for r in o.matrix_world] for o in scene.objects if o.type in ('MESH','CAMERA','LIGHT') and o.name!='GenesisTeaSurface'}
    assert trajectory==trajectory_before[str(f)]
    with np.load(case/f'surfaces/frame_{f:04d}.npz') as z:expected_v=z['vertices'];expected_velocity=z['velocity']
    evaluated=surface.evaluated_get(bpy.context.evaluated_depsgraph_get())
    actual_v=np.empty((len(evaluated.data.vertices),3),np.float32);evaluated.data.vertices.foreach_get('co',actual_v.ravel())
    hidden=bool(delete_frame is not None and f>=delete_frame)
    assert surface.hide_render==hidden and surface.hide_viewport==hidden
    if hidden:
        assert len(expected_v)==0
    else:
        assert actual_v.shape==expected_v.shape,(f,actual_v.shape,expected_v.shape)
        assert not len(expected_v) or np.allclose(actual_v,expected_v,rtol=0,atol=1e-7)
    if len(expected_v):
        attr=evaluated.data.attributes.get('velocity');assert attr is not None
        actual_velocity=np.empty((len(attr.data),3),np.float32);attr.data.foreach_get('vector',actual_velocity.ravel())
        assert actual_velocity.shape==expected_velocity.shape and np.allclose(actual_velocity,expected_velocity,rtol=1e-6,atol=1e-6)
    checks[str(f)]={'velocity_cache_matches_surface':True,'display_time_sec':(f-1)/24,'solver_surface_vertices':len(expected_v),
                    'native_vertices':len(actual_v),'hidden':hidden,'non_tea_transforms_preserved':True}
scene['pcve_scene_id']='traditional_tea_pour';scene['pcve_edit_case']=case.name
scene['pcve_physical_case']=str(case)
if experiment['after'].get('stop_flow_sec') is not None:
    scene['pcve_edit_note']=f"Inlet velocity becomes zero at {experiment['after']['stop_flow_sec']}s; every existing liquid particle remains active and continues the SPH solve."
elif delete_frame is not None:
    scene['pcve_edit_note']='Explicit liquid-deletion intervention; subsequent emission disabled.'
else:
    scene['pcve_edit_note']='Fixed-aperture inlet-speed edit with native mass flux following inlet velocity.'
scene['pcve_visual_revision']='edit_scene'
scene.render.filepath='//rerender/frame_';scene.frame_set(1)
if bpy.data.cache_files:bpy.data.cache_files[0].filepath='//genesis_liquid_cache.abc'
bpy.ops.wm.save_as_mainfile(filepath=str(case/'scene.blend'),check_existing=False,relative_remap=False)
assert source_hash==file_hash(source)
for path,h in source_caches.items():assert file_hash(Path(path))==h
report={'source_blend':str(source),'source_sha256':source_hash,'source_caches_preserved':source_caches,
        'protected_before':locked_before,'protected_after':locked_after,
        'protected_sha256':digest(locked_after),'environment_sha256':digest(env_before),
        'extra_environment_sha256':digest(extra_before),'non_liquid_animation_preserved_all96':True,
        'native_cache_sha256':file_hash(case/'genesis_liquid_cache.abc') if bpy.data.cache_files else None,
        'native_export_seconds':time.monotonic()-start,'native_all96_checks':checks,
        'all_textures_packed':all(im.packed_file for im in bpy.data.images if im.source=='FILE' and im.users),
        'requires_python_playback_handler':False,'simulation_recomputed':True,'raw_particle_cache_unchanged':True}
(case/'scene_revision.json').write_text(json.dumps(report,indent=2)+'\n')
print('TEA_EDIT_NATIVE_PREPARED',case.name,flush=True)
