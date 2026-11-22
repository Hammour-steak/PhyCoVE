"""Four seconds, fixed camera; one water cup on the room's desk and a thrown basketball."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from copy import deepcopy
import json,math
from scene_geometry import BALL_RADIUS,BOTTLE_POSITION

SCENE_NAME='basketball_cup_collision'
# bottle_presence is [bottle].
BASELINE_PHYSICS=dict(ball_mass=.62,bottle_mass=.45,initial_velocity=5.2,gravity=9.81,
 bottle_presence=[1],bottle_position=list(BOTTLE_POSITION),
 ball_radius=BALL_RADIUS,timed_edits=[])
PHYSICS_LIMITS=dict(ball_mass=(.30,3.20),bottle_mass=(.10,10.0),initial_velocity=(4.0,17.),
                    gravity=(1.,60.))
# Presence switch for the basketball, carried only by a DELETE basketball
# override. It is not in BASELINE_PHYSICS, so the published cases' scenarios
# stay unchanged; an absent key means the ball is thrown.
OPTIONAL_PHYSICS=dict(ball_presence=[1])
TOTAL_FRAMES=96

# Camera: 16 mm aimed at (1.9,-0.3,0.45). The heavy-bottle case's ball rolls
# back across the floor to the coffee table; with this framing every moving
# body stays inside the render's 2 % safe margin in all cases (smallest:
# 0.040, heavy bottle).
def defaults():
 return dict(schema_version=1,scene=SCENE_NAME,seed=0,physics=deepcopy(BASELINE_PHYSICS),
  render=dict(fps=24,duration_sec=4.,slow_motion=1,resolution=[960,540],samples=48),
  camera=dict(location=[-.6,-3.0,2.2],target=[1.9,-.3,.45],lens_mm=16))

def merge(base,overrides):
 result=deepcopy(base)
 if not isinstance(overrides,dict):raise ValueError('Scenario overrides must be an object')
 for k,v in overrides.items():
  if k in OPTIONAL_PHYSICS and k not in result:result[k]=deepcopy(v);continue
  if k not in result:raise ValueError('Unknown field: '+k)
  result[k]=merge(result[k],v) if isinstance(v,dict) else deepcopy(v)
 return result

def _finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def validate(s):
 if s['scene']!=SCENE_NAME or s['schema_version']!=1:raise ValueError('Wrong scene/schema')
 if set(s)-{'schema_version','scene','physics','render','camera','seed'}:raise ValueError('Unknown scenario field')
 if set(s['physics'])-set(OPTIONAL_PHYSICS)!=set(BASELINE_PHYSICS):raise ValueError('Unknown editable physics parameter')
 ph=s['physics'];r=s['render']
 if 'ball_presence' in ph and (not isinstance(ph['ball_presence'],list) or len(ph['ball_presence'])!=1
                               or any(type(v) is not int or v not in (0,1) for v in ph['ball_presence'])):
  raise ValueError('ball_presence must be one 0/1 entry for [basketball]')
 for key,(low,high) in PHYSICS_LIMITS.items():
  if not _finite(ph[key]) or not low<=ph[key]<=high:raise ValueError(f'{key} must be finite and within {low}..{high}')
 presence=ph['bottle_presence']
 if not isinstance(presence,list) or len(presence)!=1 or any(type(v) is not int or v not in (0,1) for v in presence):
  raise ValueError('bottle_presence must be one 0/1 entry for [bottle]')
 v=ph['bottle_position']
 if not isinstance(v,list) or len(v)!=3 or not all(_finite(c) for c in v):raise ValueError('bottle_position')
 if not _finite(ph['ball_radius']) or ph['ball_radius']<=0:raise ValueError('ball_radius')
 schedule=ph['timed_edits']
 if not isinstance(schedule,list):raise ValueError('timed_edits must be a list')
 seen=set()
 for event in schedule:
  if not isinstance(event,dict) or set(event)!={'frame','params'}:raise ValueError('timed_edits entry')
  frame=event['frame'];params=event['params']
  if type(frame) is not int or not 2<=frame<=TOTAL_FRAMES or frame in seen:raise ValueError('timed_edits frame')
  seen.add(frame)
  if not isinstance(params,dict) or not params or not set(params)<={'gravity'}:
   raise ValueError('timed_edits params may set only gravity')
  for key,value in params.items():
   if not _finite(value):raise ValueError('timed '+key+' must be finite')
   if not PHYSICS_LIMITS[key][0]<=value<=PHYSICS_LIMITS[key][1]:raise ValueError('timed '+key+' outside its limits')
 if type(r['fps']) is not int or r['fps']<=0 or 1440%r['fps']:raise ValueError('fps must divide 1440')
 if r['slow_motion']!=1 or r['duration_sec']!=4.:raise ValueError('Scene is fixed at 4 seconds in real time')
 if len(r['resolution'])!=2 or any(type(v) is not int or v<1 for v in r['resolution']):raise ValueError('resolution')
 if type(r['samples']) is not int or r['samples']<1:raise ValueError('samples')
 if set(r)!={'fps','duration_sec','slow_motion','resolution','samples'}:raise ValueError('Unknown render field')
 if set(s['camera'])!={'location','target','lens_mm'}:raise ValueError('Unknown camera field')
 for k in ('location','target'):
  if len(s['camera'][k])!=3 or not all(_finite(v) for v in s['camera'][k]):raise ValueError('camera')
 if not _finite(s['camera']['lens_mm']) or s['camera']['lens_mm']<=0:raise ValueError('lens')

def add_scenario_arguments(p):
 from pathlib import Path
 p.add_argument('--scenario-json',type=Path);p.add_argument('--scenario-overrides-json',type=Path)
 for key in PHYSICS_LIMITS:p.add_argument('--'+key.replace('_','-'),type=float)
 return p

def load_scenario(args):
 s=defaults()
 for k in ('scenario_json','scenario_overrides_json'):
  if getattr(args,k,None):s=merge(s,json.loads(getattr(args,k).read_text(encoding='utf-8')))
 for k in PHYSICS_LIMITS:
  if getattr(args,k,None) is not None:s['physics'][k]=getattr(args,k)
 validate(s);return s
