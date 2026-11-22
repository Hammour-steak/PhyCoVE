"""Shared scenario contract, matching the other rigid-body scene projects."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
from scene_geometry import COUNT
import json, math

SCENE_NAME='chalk_box_stack'
# The four-second source video uses the recipe in four_second.json. Keep a
# single source for its physics,
# framing and timing so the normal CLI cannot silently select another take.
from pcve_assets import asset as _pcve_asset
SCENARIO_DIR=_pcve_asset('')/'scenes'/'chalk_box_stack'
_DELIVERY_SCENARIO=json.loads((SCENARIO_DIR/'four_second.json').read_text(encoding='utf-8'))
BASELINE_PHYSICS=deepcopy(_DELIVERY_SCENARIO['physics'])
# A timed edit travels as a schedule inside the physics block, so the key is
# declared on the baseline the validator compares against.
BASELINE_PHYSICS.setdefault('timed_edits', [])
# One real-time clock from simulation through video, matching the suites.
TOTAL_FRAMES=96

def defaults():
    return dict(schema_version=1,scene=SCENE_NAME,physics=deepcopy(BASELINE_PHYSICS),
        render=deepcopy(_DELIVERY_SCENARIO['render']),
        camera=deepcopy(_DELIVERY_SCENARIO['camera']))

def merge(base,overrides):
    result=deepcopy(base)
    for key,value in overrides.items():
        result[key]=merge(result[key],value) if isinstance(value,dict) and isinstance(result.get(key),dict) else deepcopy(value)
    return result

def validate(s):
    if set(s)-{'schema_version','scene','physics','render','camera','seed'} or s.get('scene')!=SCENE_NAME:
        raise ValueError('Invalid scenario fields or scene name')
    c=s['physics'];r=s['render']
    # ``body_active`` ([eraser, box_0, box_1, ...], 1 = present) is optional and written only by a DELETE;
    # absent means every body is present, so the baseline and the published cases carry no such key.
    if set(c)-{'body_active'}!=set(BASELINE_PHYSICS):raise ValueError('Unknown or missing physics parameter')
    if 'body_active' in c and (not isinstance(c['body_active'],list) or len(c['body_active'])!=1+COUNT or any(type(v) is not int or v not in (0,1) for v in c['body_active'])):
        raise ValueError('body_active must list 0/1 for the eraser and every carton')
    for key,value in c.items():
        # The timed-edit schedule is a list of events, not a physical knob; the
        # simulator validates every entry it is given. Everything else here is
        # one number per parameter.
        if isinstance(value,(list,tuple,dict)):continue
        if not math.isfinite(value) or (key=='eraser_mass' and value==0):raise ValueError(f'Invalid {key}')
        # ``eraser_start_x`` is a signed position; every other knob is a
        # magnitude and has to stay nonnegative.
        if key!='eraser_start_x' and value<0:raise ValueError(f'Invalid {key}')
    if not isinstance(r['fps'],int) or r['fps']<=0 or not math.isfinite(r['duration_sec']) or r['duration_sec']<=0:raise ValueError('Invalid timing')
    if r.get('slow_motion',1)!=1:raise ValueError('Slow motion is not supported; use real-time playback (slow_motion=1)')
    if r['fps']>2400:raise ValueError('Sample rate exceeds physics rate')
    if round(r['fps']*r['duration_sec'])<1:raise ValueError('Empty trajectory')
    if not isinstance(r['samples'],int) or r['samples']<1 or len(r['resolution'])!=2 or any(not isinstance(v,int) or v<2 or v%2 for v in r['resolution']):raise ValueError('Invalid render settings; use even resolution')
    camera=s['camera']
    for key in ('location','target'):
        if len(camera[key])!=3 or not all(math.isfinite(v) for v in camera[key]):raise ValueError('Invalid camera vector')
    # The source video is shot through a perspective lens; an orthographic
    # camera (with ortho_scale) also validates. A cache carries its camera with
    # it, so resimulate to change the framing.
    positive=lambda value:isinstance(value,(int,float)) and math.isfinite(value) and value>0
    projection=camera.get('projection','orthographic')
    if camera['location']==camera['target'] or projection not in ('orthographic','perspective'):
        raise ValueError('Camera needs distinct location and target and an orthographic or perspective projection')
    if projection=='orthographic' and not positive(camera.get('ortho_scale')):
        raise ValueError('Orthographic camera needs a positive ortho_scale')
    if projection=='perspective' and (not positive(camera.get('lens_mm')) or ('fstop' in camera and not positive(camera['fstop']))):
        raise ValueError('Perspective camera needs a positive lens_mm (and fstop, when depth of field is set)')

def load_scenario(args):
    scenario_path=args.scenario_json
    if scenario_path and not scenario_path.is_file():
        # A preset given by file name resolves against the scene's asset directory.
        candidate=SCENARIO_DIR/scenario_path.name
        if candidate.is_file():scenario_path=candidate
    s=merge(defaults(),json.loads(scenario_path.read_text(encoding='utf-8'))) if scenario_path else defaults()
    if args.scenario_overrides_json:s=merge(s,json.loads(args.scenario_overrides_json.read_text(encoding='utf-8')))
    for key in BASELINE_PHYSICS:
        if getattr(args,key,None) is not None:s['physics'][key]=getattr(args,key)
    for key in ('fps','duration_sec','resolution','samples'):
        if getattr(args,key,None) is not None:s['render'][key]=getattr(args,key)
    validate(s)
    return s
