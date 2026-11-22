"""Free 3D PyBullet collision; one aimed throw, no target animation."""
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    if _Path(__file__).with_name("entrypoints.json").is_file() and (_Path(__file__).resolve().parents[2]/"pcve_scene_entry.py").is_file():
        _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__, "simulate")
# PCVE_UNIFIED_ENTRY_END

# Resolve the shared scripts directory, then this scene's module folders.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_scripts_dir = _clean_scene_dir.parents[1]
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / "assets").is_dir())
if str(_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
# Shared modules live in scripts/; scene-local modules live in this directory and
# its physics/, appearance/ and tools/ subdirectories.
for _scene_sub in ("", "physics", "appearance", "tools"):
    _scene_sub_dir = _clean_scene_dir / _scene_sub if _scene_sub else _clean_scene_dir
    if _scene_sub_dir.is_dir() and str(_scene_sub_dir) not in _clean_sys.path:
        _clean_sys.path.insert(1, str(_scene_sub_dir))

import argparse,json,math
from pathlib import Path
from scene_config import *
from scene_geometry import *
from validate_basketball_cup_collision import simulation_signature

PENETRATION_LIMIT=.012

# PyBullet combines restitution multiplicatively: the bounce two bodies share
# is e_a * e_b, so the numbers below are chosen for the *pair* they produce,
# not for the body in isolation. Targets are the coefficients of restitution
# measured for the real materials in this room:
#   basketball / hardwood floor  .82  -> .90 * .85 = .765   (regulation drop test .82-.88)
#   basketball / painted wall    .75  -> .90 * .85 = .765
#   basketball / desk top        .72  -> .90 * .80 = .72
#   basketball / plastic bottle  .45  -> .90 * .50 = .45
#   bottle     / desk top        .40  -> .50 * .80 = .40
#   bottle     / wall           .425  -> .50 * .85 = .425
#   bottle     / floor          .425  -> .50 * .85 = .425
#   basketball / soft furniture  .27  -> .90 * .30 = .27
# A shared .7 everywhere would give .49 for every pair, i.e. a ball that
# dead-stops on the floor and sticks to the bottle.
#
# The bottle is a thin-walled shell, not a solid: a shell rings on impact and
# dumps most of the normal velocity into vibration, so every pair it forms sits
# around .40, not .60; .70 (bottle/wall .595) is the value for a solid metal
# block. In the x3 edit the cup reaches the wall at 10 m/s; with .70 it would
# rebound at 6 m/s and the rebound torque would spin it back through upright in
# a single frame (63.9 deg -> 7.8 deg -> 26.7 deg), which reads as the cup
# standing up again. At .50 the same impact is 4.2 m/s of
# rebound and the cup simply keeps tumbling forward through 172 deg and settles
# on its side -- what a plastic bottle actually does when it is thrown into a
# wall.
RESTITUTION=dict(ball=.90,bottle=.50,desk=.80,floor=.85,wall=.85,prop=.30)

# Bullet's rollingFriction is a *hard torsional constraint* at the contact
# point, not a drag: it can hold a resting body at an angle. With the ball's
# .06, a bottle tipped over on its base rim simply stops wherever it happens to
# be -- 9.8 deg, 18 deg, 46 deg across the cases -- instead of falling (past the critical angle atan(r/com) =
# 20.6 deg) or falling back flat (below it). That is the "leans but neither
# falls nor rights itself" artefact. It cannot simply be switched off either:
# at 0 a bottle that lands on its side rolls across the desk for ever, reaches
# the front edge and keeps creeping off it. Measured with the real hull on the
# desk, 2 s runs, start tilt -> end tilt:
#   rollingFriction   5   10   20   30   46 (deg)      lying bottle
#   .06 (the ball)    5   10   20   30   90           stops dead
#   .0018             0    1   20   90   90           stops in <1.5 s
#   .0015             0    0    8   90   90           stops in <1.5 s
#   0                 2    2   11   90   90           still rolling at 2 s
# .0015 is the largest value that still topples from every angle past the
# critical one; angularDamping then does the rest of the rolling resistance.
BOTTLE_ANGULAR_DAMPING=.35
BOTTLE_ROLLING_FRICTION=.0015

def effective_restitution():
 """Pair-wise restitution PyBullet actually applies (product of the two bodies)."""
 pairs=(('ball','floor'),('ball','wall'),('ball','desk'),
        ('ball','bottle'),('bottle','desk'),('bottle','wall'),
        ('bottle','floor'),('ball','prop'))
 return {f'{a}/{b}':round(RESTITUTION[a]*RESTITUTION[b],3) for a,b in pairs}

def simulate_without_ball(p,ph,s,fps,count,stride,bodies,timed_by_frame,client):
 """The DELETE basketball run: the settled room is stepped on its own for the
 whole clip with the same clock, gravity schedule and sampling as a throw."""
 bodies=dict(bodies,basketball=None);max_pen=0.;timed_events=[]
 bottles=[k for k in KEYS if k!='basketball' and bodies[k] is not None]
 max_tilt={k:0. for k in bottles};off_table={k:None for k in bottles}
 frames=[]
 for step in range((count-1)*stride+1):
  t=step/SIM_HZ
  for k in bottles:
   b=bodies[k]
   for c in p.getContactPoints(bodyA=b):max_pen=max(max_pen,-c[8])
   pos,q=p.getBasePositionAndOrientation(b)
   if on_table(pos) and pos[2]<=TABLE_TOP_Z+COM_HEIGHT+.01:
    mat=p.getMatrixFromQuaternion(q)
    max_tilt[k]=max(max_tilt[k],math.degrees(math.acos(max(-1.,min(1.,mat[8])))))
   if off_table[k] is None and (not on_table(pos) or pos[2]<TABLE_TOP_Z-BOTTLE_HEIGHT):
    off_table[k]=t
  if step%stride==0:
   frame_index=len(frames)+1
   for params in timed_by_frame.get(frame_index,[]):
    p.setGravity(0,0,-float(params['gravity']))
    timed_events.append(dict(frame=frame_index,time_sec=t,params=dict(params),
     from_values={key:ph[key] for key in params},applied_in_simulation=True,effective_from_frame=frame_index))
   f=dict(frame_index=frame_index,time_sec=t)
   for k,b in bodies.items():
    if b is None:f[k]=dict(present=False);continue
    pos,q=p.getBasePositionAndOrientation(b);v,w=p.getBaseVelocity(b);mat=p.getMatrixFromQuaternion(q)
    f[k]=dict(present=True,location=list(pos),quaternion_xyzw=list(q),linear_velocity=list(v),angular_velocity=list(w),
     matrix_world=[list(mat[j*3:j*3+3])+[pos[j]] for j in range(3)]+[[0,0,0,1]])
   frames.append(f)
  if step<(count-1)*stride:p.stepSimulation()
 travel={k:math.dist(frames[0][k]['location'],frames[-1][k]['location']) for k in bottles}
 quality=dict(valid=max_pen<PENETRATION_LIMIT,first_impact_sec=None,ball_floor_contact_sec=None,
  max_penetration_m=max_pen,max_bottle_tilt_deg=max_tilt,bottle_off_table_sec=off_table,displacement_m=travel,
  transmission_observed=any(travel.get(k,0)>.008 for k in bottles),final_ball_speed_m_s=None,
  timed_events=timed_events)
 return dict(schema_version=2,scene=SCENE_NAME,scenario=s,simulation_signature=simulation_signature(s),
  playback_fps=fps,sample_fps=fps,slow_motion=1,frame_start=1,frame_end=count,physical_duration_sec=4.,playback_duration_sec=4.,
  solver=dict(engine='PyBullet DIRECT',hz=SIM_HZ,iterations=120,gravity=[0,0,-ph['gravity']],
   desk_friction=.8,ball_friction=.5,bottle_friction=.4,ball_rolling_friction=.06,
   bottle_rolling_friction=BOTTLE_ROLLING_FRICTION,bottle_angular_damping=BOTTLE_ANGULAR_DAMPING,
   restitution=dict(RESTITUTION),effective_restitution=effective_restitution(),
   note='DELETE basketball: no ball is created; bottle as convex hull of the water_bottle__plastic_bottle.glb baked mesh; floor/desk/walls/carton/coffee table are analytic colliders'),
  bottle_reference=dict(height_m=BOTTLE_HEIGHT,max_radius_m=BOTTLE_RADIUS,com_height_m=COM_HEIGHT,
                        mesh_volume_m3=BOTTLE_MESH_VOLUME,inertia_per_kg=BOTTLE_INERTIA_PER_KG),
  objects={k:dict(present=bodies[k] is not None,mass_kg=ph['ball_mass'] if k=='basketball' else ph['bottle_mass']) for k in KEYS},
  quality=quality,timed_events=timed_events,frames=frames)

def simulate(s):
 import pybullet as p
 validate(s);ph=s['physics'];fps=s['render']['fps'];count=4*fps;stride=SIM_HZ//fps
 timed_by_frame={}
 for event in ph.get('timed_edits',[]):
  if not isinstance(event,dict) or set(event)!={'frame','params'}:raise ValueError(f'Invalid timed edit entry: {event!r}')
  frame=event['frame'];params=event['params']
  if type(frame) is not int or not 2<=frame<=count:raise ValueError(f'Timed edit frame {frame!r} is outside 2..{count}')
  unknown=set(params)-{'gravity'}
  if unknown:raise ValueError(f'Timed edit sets {sorted(unknown)}, which this scene cannot change mid-run')
  for key,value in params.items():
   if not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError(f'Timed {key} must be finite')
  timed_by_frame.setdefault(frame,[]).append(dict(params))
 client=p.connect(p.DIRECT)
 try:
  p.setGravity(0,0,-ph['gravity']);p.setTimeStep(1/SIM_HZ)
  p.setPhysicsEngineParameter(numSolverIterations=120,deterministicOverlappingPairs=1,restitutionVelocityThreshold=.015,contactBreakingThreshold=.0002)
  floor=p.createMultiBody(0,p.createCollisionShape(p.GEOM_BOX,halfExtents=[8,8,.05]),basePosition=[0,0,FLOOR_Z-.05])
  p.changeDynamics(floor,-1,lateralFriction=.8,restitution=RESTITUTION['floor'])
  # The desk: a full-height box under the desk top (appearance/studio_room.py
  # builds the visible desk on exactly this footprint and height).
  table=p.createMultiBody(0,p.createCollisionShape(p.GEOM_BOX,halfExtents=[TABLE_HALF[0],TABLE_HALF[1],TABLE_BODY]),
   basePosition=[TABLE_CENTER[0],TABLE_CENTER[1],TABLE_TOP_Z-TABLE_BODY])
  p.changeDynamics(table,-1,lateralFriction=.8,restitution=RESTITUTION['desk'])
  # Far safety walls (scene_geometry.SAFETY_WALLS): their inner faces are the
  # studio's west, south and north wall planes, so a runaway ball or cup stops
  # at a wall the camera can see instead of leaving the room.
  walls=[]
  for half,pos in SAFETY_WALLS:
   w=p.createMultiBody(0,p.createCollisionShape(p.GEOM_BOX,halfExtents=list(half)),basePosition=list(pos))
   p.changeDynamics(w,-1,lateralFriction=.5,restitution=RESTITUTION['wall']);walls.append(w)
  # The room's other static boxes (scene_geometry.ROOM_PROPS): the solid wall
  # the desk stands against, the carton beside the desk and the coffee table,
  # which the studio look shows exactly where they are, plus five furniture
  # boxes that no case ever touches and that have no visible counterpart.
  props=[]
  for _name,half,pos in ROOM_PROPS:
   b=p.createMultiBody(0,p.createCollisionShape(p.GEOM_BOX,halfExtents=list(half)),basePosition=list(pos))
   p.changeDynamics(b,-1,lateralFriction=.6,restitution=RESTITUTION['prop']);props.append(b)
  sphere=p.createCollisionShape(p.GEOM_SPHERE,radius=ph['ball_radius'])
  hull=p.createCollisionShape(p.GEOM_MESH,vertices=BOTTLE_VERTICES)
  bodies={};positions=layout(ph)
  for k in KEYS:
   if not present(ph,k) or k=='basketball':bodies[k]=None;continue
   b=p.createMultiBody(ph['bottle_mass'],hull,basePosition=positions[k])
   inertia=[v*ph['bottle_mass'] for v in BOTTLE_INERTIA_PER_KG]
   # Bottle dynamics: see BOTTLE_ROLLING_FRICTION above for why the rolling
   # coefficient is 25x smaller than the ball's, and why it is not zero.
   p.changeDynamics(b,-1,lateralFriction=.4,restitution=RESTITUTION['bottle'],rollingFriction=BOTTLE_ROLLING_FRICTION,spinningFriction=.001,
    linearDamping=0.,angularDamping=BOTTLE_ANGULAR_DAMPING,localInertiaDiagonal=inertia,
    collisionMargin=.0001,contactProcessingThreshold=.001,ccdSweptSphereRadius=.02)
   bodies[k]=b
  # Settle the bottle(s) on the desk before the visible clip starts; the ball
  # is created afterwards so the settle pass cannot drop it off its launch pose.
  for _ in range(240):p.stepSimulation()
  for b in bodies.values():
   if b is not None:p.resetBaseVelocity(b,[0,0,0],[0,0,0])
  if not present(ph,'basketball'):
   # DELETE basketball: the throw never happens and nothing else is changed.
   return simulate_without_ball(p,ph,s,fps,count,stride,bodies,timed_by_frame,client)
  ball=p.createMultiBody(ph['ball_mass'],sphere,basePosition=BALL_START)
  # Realistic basketball: its own restitution is .90 so the pairs it forms
  # land on the measured values (see RESTITUTION above) -- .765 on the floor
  # and on the wall, .72 on the desk, .63 against the bottle. Anything lower
  # makes the ball dead-stop on the desk or stick to the bottle after impact.
  # rollingFriction is the *torsional* limit Bullet applies at the contact
  # (an angular impulse budget scaled by that step's normal impulse), so it is
  # not a drag coefficient: a value of .06 budgets ~22 rad/s of spin removal on
  # a 1.2 m/s landing, i.e. twice the ball's whole spin, and zeroes the spin at
  # the first desk bounce (9.82 -> 0.00 rad/s); the ball then slides instead of
  # rolling and stalls 0.17 m short of the desk edge. .0015 puts the rolling
  # deceleration at 0.15 m/s^2 (equivalently mu_r .015, the measured range for
  # a basketball on a hard floor, 0.01-0.02) and matches the bottle's value.
  p.changeDynamics(ball,-1,lateralFriction=.5,restitution=RESTITUTION['ball'],rollingFriction=.0015,spinningFriction=.002,
   linearDamping=0.,angularDamping=.01,collisionMargin=.0001,contactProcessingThreshold=.001,
   ccdSweptSphereRadius=.03)
  bodies['basketball']=ball
  speed=ph['initial_velocity']
  v0=throw_velocity(speed,BALL_START,AIM_TARGET,ph['gravity'])
  # Backspin about the horizontal axis perpendicular to the flight direction:
  # the top of the ball has to move *against* the travel direction, so the spin
  # vector is -0.4 * (z_hat x u). +0.4 * (z_hat x u) would be topspin -- the
  # spin a ball picks up when it rolls, not the spin a hand imparts to a throw.
  uxz=math.hypot(v0[0],v0[1])
  spin=[.4*speed/ph['ball_radius']*v0[1]/uxz,-.4*speed/ph['ball_radius']*v0[0]/uxz,0]
  p.resetBaseVelocity(ball,v0,spin)
  first=None;first_pair=None;ball_floor=None;max_pen=0.;timed_events=[]
  bottles=[k for k in KEYS if k!='basketball' and bodies[k] is not None]
  max_tilt={k:0. for k in bottles};off_table={k:None for k in bottles}
  frames=[]
  for step in range((count-1)*stride+1):
   t=step/SIM_HZ
   for c in p.getContactPoints(bodyA=bodies['basketball']):
    max_pen=max(max_pen,-c[8])
    other=c[2] if c[1]==bodies['basketball'] else c[1]
    if other in (bodies[k] for k in bottles):
     if first_pair is None:first_pair=t;first=t
    elif other==floor:ball_floor=ball_floor if ball_floor is not None else t
   for k in bottles:
    b=bodies[k]
    for c in p.getContactPoints(bodyA=b):max_pen=max(max_pen,-c[8])
    pos,q=p.getBasePositionAndOrientation(b)
    supported=(on_table(pos) and pos[2]<=TABLE_TOP_Z+COM_HEIGHT+.01)
    if supported:
     mat=p.getMatrixFromQuaternion(q)
     max_tilt[k]=max(max_tilt[k],math.degrees(math.acos(max(-1.,min(1.,mat[8])))))
    if off_table[k] is None and (not on_table(pos) or pos[2]<TABLE_TOP_Z-BOTTLE_HEIGHT):
     off_table[k]=t
   if step%stride==0:
    frame_index=len(frames)+1
    for params in timed_by_frame.get(frame_index,[]):
     # Applied to the live world: the new gravity governs every free body
     # from this frame on and the run carries on from the state it reached.
     previous=ph['gravity'];new=float(params['gravity'])
     p.setGravity(0,0,-new)
     timed_events.append(dict(frame=frame_index,time_sec=t,params=dict(params),
      from_values={key:ph[key] for key in params},applied_in_simulation=True,
      effective_from_frame=frame_index))
    f=dict(frame_index=len(frames)+1,time_sec=t)
    for k,b in bodies.items():
     if b is None:f[k]=dict(present=False);continue
     pos,q=p.getBasePositionAndOrientation(b);v,w=p.getBaseVelocity(b);mat=p.getMatrixFromQuaternion(q)
     f[k]=dict(present=True,location=list(pos),quaternion_xyzw=list(q),linear_velocity=list(v),angular_velocity=list(w),
      matrix_world=[list(mat[j*3:j*3+3])+[pos[j]] for j in range(3)]+[[0,0,0,1]])
    frames.append(f)
   if step<(count-1)*stride:p.stepSimulation()
  travel={k:math.dist(frames[0][k]['location'],frames[-1][k]['location']) for k in KEYS if bodies[k] is not None}
  quality=dict(valid=max_pen<PENETRATION_LIMIT,first_impact_sec=first,ball_floor_contact_sec=ball_floor,
   max_penetration_m=max_pen,max_bottle_tilt_deg=max_tilt,bottle_off_table_sec=off_table,displacement_m=travel,
   transmission_observed=any(travel.get(k,0)>.008 for k in bottles),
   final_ball_speed_m_s=math.sqrt(sum(v*v for v in frames[-1]['basketball']['linear_velocity'])),
   timed_events=timed_events)
  return dict(schema_version=2,scene=SCENE_NAME,scenario=s,simulation_signature=simulation_signature(s),
   playback_fps=fps,sample_fps=fps,slow_motion=1,frame_start=1,frame_end=count,physical_duration_sec=4.,playback_duration_sec=4.,
   solver=dict(engine='PyBullet DIRECT',hz=SIM_HZ,iterations=120,gravity=[0,0,-ph['gravity']],
    desk_friction=.8,ball_friction=.5,bottle_friction=.4,ball_rolling_friction=.06,
    bottle_rolling_friction=BOTTLE_ROLLING_FRICTION,bottle_angular_damping=BOTTLE_ANGULAR_DAMPING,
    restitution=dict(RESTITUTION),effective_restitution=effective_restitution(),
    note='Aimed ballistic throw; bottle as convex hull of the water_bottle__plastic_bottle.glb baked mesh; the room is visual only, floor/desk/walls/carton/coffee table are analytic colliders'),
   bottle_reference=dict(height_m=BOTTLE_HEIGHT,max_radius_m=BOTTLE_RADIUS,com_height_m=COM_HEIGHT,
                         mesh_volume_m3=BOTTLE_MESH_VOLUME,inertia_per_kg=BOTTLE_INERTIA_PER_KG),
   objects={k:dict(present=bodies[k] is not None,mass_kg=ph['ball_mass'] if k=='basketball' else ph['bottle_mass']) for k in KEYS},
   quality=quality,timed_events=timed_events,frames=frames)
 finally:p.disconnect(client)

def main():
 p=add_scenario_arguments(argparse.ArgumentParser(description=__doc__));p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();d=simulate(load_scenario(a));a.out.parent.mkdir(parents=True,exist_ok=True)
 a.out.write_text(json.dumps(d,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
 (a.out.parent/'simulation_metrics.json').write_text(json.dumps(d['quality'],indent=2),encoding='utf-8')
 print(json.dumps(d['quality'],indent=2),flush=True)
if __name__=='__main__':main()
