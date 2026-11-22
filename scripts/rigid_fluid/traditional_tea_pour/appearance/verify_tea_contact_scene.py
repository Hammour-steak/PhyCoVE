"""Reopen fixed scene and check protected asset/environment state and cache."""
import argparse
import json
import sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tea_environment_state import protected_state,environment_state,digest,file_hash
p=argparse.ArgumentParser()
p.add_argument('case',type=Path)
p.add_argument('--report',type=Path)
p.add_argument('--relocated',action='store_true')
p.add_argument('--animation-report',type=Path)
p.add_argument('--output',type=Path)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
case=a.case.resolve()
report=json.loads((a.report or case/'scene_revision.json').read_text())
scene=bpy.context.scene; scene.frame_set(72); bpy.context.view_layer.update()
actual=protected_state()
samples=actual['render'][6]
actual['render'][6]=report['protected_after']['render'][6]
assert digest(actual)==report['protected_sha256']
assert digest(environment_state())==report['environment_sha256_after']
cache=bpy.data.cache_files[0]
assert cache.filepath=='//genesis_liquid_cache.abc'
assert file_hash(Path(bpy.path.abspath(cache.filepath)))==report['native_cache_sha256']
if not a.relocated:
    assert file_hash(Path(report['source_blend']))==report['source_sha256']
assert (scene.frame_start,scene.frame_end)==(1,96)
assert samples>=32
assert all(im.packed_file for im in bpy.data.images if im.source=='FILE' and im.users)
result={'passed':True,'cup_teapot_lid_geometry_UVs_materials_transforms_match_environment':True,
        'environment_lights_camera_unchanged':True,'tea_material_unchanged':True,
        'textures_packed':True,'cache_relative_path':cache.filepath,'native_cache_sha256':report['native_cache_sha256'],
        'samples':samples,'resolution':[scene.render.resolution_x,scene.render.resolution_y],
        'fps':scene.render.fps,'range':[scene.frame_start,scene.frame_end]}
result['relocated']=a.relocated
if a.animation_report:
    reference=json.loads(a.animation_report.read_text())['all96frames']
    checks={}
    for f in [1,24,72,96]:
        scene.frame_set(f); bpy.context.view_layer.update()
        m=bpy.data.objects['GenesisTeaSurface'].evaluated_get(bpy.context.evaluated_depsgraph_get()).data
        assert len(m.vertices)==reference[str(f)]['vertices']
        assert len(m.polygons)==reference[str(f)]['triangles']
        checks[str(f)]={'vertices':len(m.vertices),'triangles':len(m.polygons)}
    result['relocated_native_frame_checks']=checks
(a.output or case/'protected_scene_validation.json').write_text(json.dumps(result,indent=2)+'\n')
print('TEA_CONTACT_PROTECTED_SCENE_PASS',flush=True)
