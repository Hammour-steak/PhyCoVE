"""A flat tin sliding into a yawed tin: off-centre impact and spin on a cloth-covered table."""
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

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
from scene_config import add_scenario_arguments, load_scenario, validate, SCENE_NAME
from scene_geometry import *
from validate_kitchen_tin_collision import simulation_signature

# The settle pass runs on these, and the declared coefficients are written in
# afterwards: a rest pose does not depend on friction, so starting every run
# from the same pair keeps an edit visible in the motion instead of in where
# the tins happened to come to rest.
SOURCE_CAN_MU, SOURCE_TABLE_MU = 0.20, 1.0

TIMED_FIELDS = {'initial_velocity': (0.0, 5.0), 'receiver_initial_velocity': (-0.6, 0.6),
                'driver_mass': (.05, 1.5), 'receiver_mass': (.05, 1.6),
                'restitution': (0.0, 1.0), 'driver_friction': (0.0, 1.2),
                'receiver_friction': (0.0, 1.2), 'table_friction': (0.0, 2.)}

HALF_EXTENTS = {'driver_can': (DRIVER_RADIUS, DRIVER_RADIUS, DRIVER_HEIGHT / 2),
                'receiver_can': RECEIVER_HALF}

# The bistro the tins sit in is a real room, and an extreme edit could send one
# of them over the table edge.  Without a floor and four walls that tin would
# fall for ever and the trace would describe a place the video never shows, so
# the room is part of the physics: FLOOR_Z / ROOM_X / ROOM_Y / ROOM_TOP_Z come
# from scene_geometry.py, the same numbers appearance/bistro_room.py builds on.


def timed_schedule(ph, count):
    """Read ``physics.timed_edits`` into ``{frame: params}``, rejecting nonsense."""
    schedule = {}
    for entry in ph.get('timed_edits') or []:
        if not isinstance(entry, dict) or set(entry) != {'frame', 'params'}:
            raise ValueError(f'Unsupported timed event: {entry!r}')
        frame = entry['frame']
        if type(frame) is not int or not 2 <= frame <= count:
            raise ValueError(f'Timed event frame {frame!r} is outside the clip (2..{count})')
        if frame in schedule:
            raise ValueError(f'More than one timed event targets frame {frame}')
        if not isinstance(entry['params'], dict) or not entry['params']:
            raise ValueError('Timed event params must be a non-empty object')
        for name, value in entry['params'].items():
            if name not in TIMED_FIELDS:
                raise ValueError(f'Timed edit cannot write {name!r}; this scene accepts {sorted(TIMED_FIELDS)}')
            low, high = TIMED_FIELDS[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'Timed {name!r} must be a finite number')
            if not low <= float(value) <= high:
                raise ValueError(f'Timed {name!r} = {value!r} is outside {low}..{high}')
        schedule[frame] = dict(entry['params'])
    return schedule


def body_state(p, bodies):
    state = {}
    for key, body in zip(KEYS, bodies):
        if body is None:
            state[key] = None
            continue
        pos, _ = p.getBasePositionAndOrientation(body)
        state[key] = {'location': list(pos), 'linear_velocity': list(p.getBaseVelocity(body)[0])}
    return state


def apply_timed_params(p, params, bodies, table, *, frame, time_sec):
    """Write one frame's edited physics into the running simulation.

    Returns one event per parameter with the value on both sides of the write
    and the motion state, which is what makes a mid-run case auditable
    afterwards.  A speed write also pins the spin to zero: the driver rides on
    its flat base, so any inherited roll would be wrong for this motion.
    """
    events = []
    index_of = {key: i for i, key in enumerate(KEYS)}
    for key, value in params.items():
        state_before = body_state(p, bodies)
        if key in ('initial_velocity', 'receiver_initial_velocity'):
            index = 0 if key == 'initial_velocity' else 1
            body = bodies[index]
            if body is None:
                raise ValueError(f'Timed edit writes {key!r} but that tin is not in the scene')
            _, angular = p.getBaseVelocity(body)
            before = float(p.getBaseVelocity(body)[0][0])
            # The tin slides on its base, so a speed write carries no spin.
            spin = [0.0, 0.0, 0.0] if index == 0 else list(angular)
            p.resetBaseVelocity(body, [float(value), 0.0, 0.0], spin)
            after = float(p.getBaseVelocity(body)[0][0])
        elif key in ('driver_mass', 'receiver_mass'):
            index = {'driver_mass': 0, 'receiver_mass': 1}[key]
            body = bodies[index]
            if body is None:
                raise ValueError(f'Timed edit writes {key!r} but that tin is not in the scene')
            before = float(p.getDynamicsInfo(body, -1)[0])
            p.changeDynamics(body, -1, mass=float(value))
            after = float(p.getDynamicsInfo(body, -1)[0])
        elif key == 'table_friction':
            before = float(p.getDynamicsInfo(table, -1)[1])
            p.changeDynamics(table, -1, lateralFriction=float(value))
            after = float(p.getDynamicsInfo(table, -1)[1])
        elif key in ('driver_friction', 'receiver_friction'):
            index = 0 if key == 'driver_friction' else 1
            body = bodies[index]
            if body is None:
                raise ValueError(f'Timed edit writes {key!r} but that tin is not in the scene')
            before = float(p.getDynamicsInfo(body, -1)[1])
            p.changeDynamics(body, -1, lateralFriction=float(value))
            after = float(p.getDynamicsInfo(body, -1)[1])
        else:  # restitution: the pair value the bodies were created with
            before = float(p.getDynamicsInfo(bodies[0], -1)[5]) ** 2
            for body in bodies:
                if body is not None:
                    p.changeDynamics(body, -1, restitution=math.sqrt(float(value)))
            after = float(p.getDynamicsInfo(bodies[0], -1)[5]) ** 2
        events.append({'frame': frame, 'time_sec': time_sec, 'parameter': key,
                       'from': before, 'to': after,
                       'state_before': state_before, 'state_after': body_state(p, bodies)})
    return events


def yaw_degrees(q):
    """Heading of a tin about the table normal, from its quaternion."""
    x, y, z, w = q
    forward_x = 1 - 2 * (y * y + z * z)
    forward_y = 2 * (x * y + z * w)
    return math.degrees(math.atan2(forward_y, forward_x))


def tilt_degrees(q):
    """Angle between the tin's own up axis and the table normal."""
    x, y, z, w = q
    up_z = 1 - 2 * (x * x + y * y)
    return math.degrees(math.acos(max(-1., min(1., up_z))))


def simulate(s):

    import pybullet as p
    validate(s)
    r = s['render']; ph = s['physics']; fps = r['fps'] * r['slow_motion']
    count = round(fps * r['duration_sec']); stride = SIM_HZ // fps
    driver_mu = float(ph['driver_friction']); receiver_mu = float(ph['receiver_friction'])
    table_mu = float(ph['table_friction'])
    schedule = timed_schedule(ph, count)
    client = p.connect(p.DIRECT)
    try:
        p.setGravity(0, 0, -9.81); p.setTimeStep(1 / SIM_HZ)
        p.setPhysicsEngineParameter(numSolverIterations=140, restitutionVelocityThreshold=.001,
                                    deterministicOverlappingPairs=1, contactBreakingThreshold=.0003)
        shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=[TABLE_HALF_X, TABLE_HALF_Y, .02])
        table = p.createMultiBody(0, shape, basePosition=[0, 0, TABLE_TOP_Z - .02])
        p.changeDynamics(table, -1, lateralFriction=SOURCE_TABLE_MU, restitution=0.)
        # Floor and walls: the bistro room the render builds on the same planes.
        height = ROOM_TOP_Z - FLOOR_Z
        mid_x, half_x = (ROOM_X[0] + ROOM_X[1]) / 2, (ROOM_X[1] - ROOM_X[0]) / 2 + .06
        mid_y, half_y = (ROOM_Y[0] + ROOM_Y[1]) / 2, (ROOM_Y[1] - ROOM_Y[0]) / 2 + .06
        floor = p.createMultiBody(0, p.createCollisionShape(p.GEOM_BOX, halfExtents=[half_x, half_y, .02]),
                                  basePosition=[mid_x, mid_y, FLOOR_Z - .02])
        p.changeDynamics(floor, -1, lateralFriction=.62, restitution=.10)
        for cx, cy, hx, hy in ((ROOM_X[0] - .03, mid_y, .03, half_y), (ROOM_X[1] + .03, mid_y, .03, half_y),
                               (mid_x, ROOM_Y[0] - .03, half_x, .03), (mid_x, ROOM_Y[1] + .03, half_x, .03)):
            wall = p.createMultiBody(0, p.createCollisionShape(p.GEOM_BOX, halfExtents=[hx, hy, height / 2]),
                                     basePosition=[cx, cy, FLOOR_Z + height / 2])
            p.changeDynamics(wall, -1, lateralFriction=.55, restitution=.18)
        hull = p.createCollisionShape(p.GEOM_MESH, vertices=hull_vertices())
        box = p.createCollisionShape(p.GEOM_BOX, halfExtents=RECEIVER_HALF)
        masses = [ph['driver_mass'], ph['receiver_mass']]
        # The tuna tin travels base-down, so its local Z axis stays vertical.
        # The sardine tin is yawed a quarter turn so its 129 mm side -- not
        # the 75 mm end -- is the face the driver runs into.
        quarter = p.getQuaternionFromEuler([0, 0, math.radians(RECEIVER_YAW_DEG)])
        orientations = [[0, 0, 0, 1], quarter]
        starts = [DRIVER_START, RECEIVER_START]
        active = [bool(ph.get('driver_active', [1])[0]), bool(ph['receiver_active'][0])]
        bodies = []
        for i in range(2):
            if not active[i]:
                bodies.append(None); continue
            body = p.createMultiBody(masses[i], hull if i == 0 else box,
                                     basePosition=list(starts[i]), baseOrientation=orientations[i])
            p.changeDynamics(body, -1, lateralFriction=SOURCE_CAN_MU, restitution=math.sqrt(ph['restitution']),
                             rollingFriction=.0016 if i == 0 else .0004,
                             spinningFriction=.0001, linearDamping=0., angularDamping=0.,
                             collisionMargin=.0001, contactProcessingThreshold=.001)
            bodies.append(body)
        for _ in range(240): p.stepSimulation()
        # The settle pass is not part of the clip.  The declared coefficients
        # are written in here, before the flat tin is given its speed.
        p.changeDynamics(table, -1, lateralFriction=table_mu)
        for i, body in enumerate(bodies):
            if body is not None:
                p.changeDynamics(body, -1, lateralFriction=driver_mu if i == 0 else receiver_mu)
        if bodies[0] is not None:
            p.resetBaseVelocity(bodies[0], [ph['initial_velocity'], 0, 0], [0, 0, 0])
        if bodies[1] is not None:
            p.resetBaseVelocity(bodies[1], [ph['receiver_initial_velocity'], 0, 0], [0, 0, 0])
        frames = []; first_impact = None; max_penetration = 0.; max_receiver_tilt = 0.
        max_receiver_speed = 0.; edge = 10.; lowest = 10.; last_motion = 0.
        contact_impulse = 0.; max_slip_ratio = 0.; timed_events = []
        for step in range((count - 1) * stride + 1):
            t = step / SIM_HZ
            contacts = p.getContactPoints(bodies[0], bodies[1]) if None not in bodies else []
            if contacts and first_impact is None: first_impact = t
            contact_impulse += sum(c[9] / SIM_HZ for c in contacts)
            for i, b in enumerate(bodies):
                if b is None: continue
                pos, q = p.getBasePositionAndOrientation(b); v, w = p.getBaseVelocity(b)
                if math.hypot(*v[:2]) > .005: last_motion = t
                lowest = min(lowest, pos[2])
                mat = p.getMatrixFromQuaternion(q)
                half = HALF_EXTENTS[KEYS[i]]
                extent_x = sum(abs(mat[j]) * d for j, d in enumerate(half))
                extent_y = sum(abs(mat[3 + j]) * d for j, d in enumerate(half))
                edge = min(edge, TABLE_HALF_X - abs(pos[0]) - extent_x,
                           TABLE_HALF_Y - abs(pos[1]) - extent_y)
                if i == 1:
                    # Tilt is the sliding-vs-tumbling gate, so it only means
                    # something while the tin is still on the cloth.  Once an
                    # edit has swept it off the table it is falling through the
                    # air, and landing on its rim is the honest outcome rather
                    # than a modelling defect -- the fall is checked separately
                    # by min_body_z_m against the floor.
                    if pos[2] > TABLE_TOP_Z - .02:
                        max_receiver_tilt = max(max_receiver_tilt, tilt_degrees(q))
                    max_receiver_speed = max(max_receiver_speed, math.hypot(*v[:2]))
                elif first_impact is None and abs(v[0]) > .02:
                    # Rolling, not skidding: the contact point's speed is v - w*r,
                    # and the ratio says how much of the travel is slip.
                    max_slip_ratio = max(max_slip_ratio, abs(v[0] - w[1] * DRIVER_RADIUS) / abs(v[0]))
                for c in p.getContactPoints(bodyA=b): max_penetration = max(max_penetration, -c[8])
            if step % stride == 0:
                frame_index = len(frames) + 1
                if frame_index in schedule:
                    timed_events.extend(apply_timed_params(
                        p, schedule[frame_index], bodies, table, frame=frame_index, time_sec=t))
                f = dict(frame_index=frame_index, time_sec=t)
                for key, b in zip(KEYS, bodies):
                    if b is None:
                        f[key] = dict(present=False); continue
                    pos, q = p.getBasePositionAndOrientation(b); v, w = p.getBaseVelocity(b)
                    mat = p.getMatrixFromQuaternion(q)
                    matrix = [list(mat[j * 3:j * 3 + 3]) + [pos[j]] for j in range(3)] + [[0, 0, 0, 1]]
                    f[key] = dict(present=True, location=list(pos), quaternion_xyzw=list(q),
                                  linear_velocity=list(v), angular_velocity=list(w), matrix_world=matrix)
                frames.append(f)
            if step < (count - 1) * stride: p.stepSimulation()
        speeds = [math.hypot(*p.getBaseVelocity(b)[0][:2]) for b in bodies if b is not None]
        first, last = frames[0], frames[-1]
        travel = {k: (round(last[k]['location'][0] - first[k]['location'][0], 6) if first[k]['present'] else None)
                  for k in KEYS}
        lateral = {k: (round(last[k]['location'][1] - first[k]['location'][1], 6) if first[k]['present'] else None)
                   for k in KEYS}
        yaw = {k: (round(yaw_degrees(last[k]['quaternion_xyzw']) - yaw_degrees(first[k]['quaternion_xyzw']), 3)
                   if first[k]['present'] else None) for k in KEYS}
        # Staying on the table is reported, not required: an edit is allowed to
        # knock a tin off it, and the room below is part of the scene.  What the
        # trace must not do is tunnel through a surface or leave the room.
        quality = dict(valid=max_penetration < .002 and lowest > FLOOR_Z - .005 and max_receiver_tilt < 60,
                       stayed_on_table=edge > .002,
                       first_impact_sec=first_impact, transmission_observed=max_receiver_speed > .02,
                       receiver_max_speed_m_s=round(max_receiver_speed, 6),
                       displacement_x_m=travel, displacement_y_m=lateral, yaw_change_deg=yaw,
                       max_receiver_tilt_deg=round(max_receiver_tilt, 3),
                       max_penetration_m=round(max_penetration, 6),
                       min_table_edge_clearance_m=round(edge, 6),
                       min_body_z_m=round(lowest, 6), floor_z_m=FLOOR_Z,
                       max_preimpact_slip_ratio=round(max_slip_ratio, 5),
                       contact_normal_impulse_Ns=round(contact_impulse, 6),
                       last_motion_sec=round(last_motion, 4),
                       settled_by_end=max(speeds) < .005, final_speed_m_s=round(max(speeds), 6),
                       requested_pair_restitution=ph['restitution'],
                       requested_driver_friction=driver_mu, requested_receiver_friction=receiver_mu,
                       requested_table_friction=table_mu)
        return dict(schema_version=2, scene=SCENE_NAME, scenario=deepcopy(s),
                    simulation_signature=simulation_signature(s),
                    solver=dict(name='PyBullet', api_version=p.getAPIVersion(), constants=fixed_constants()),
                    playback_fps=r['fps'], sample_fps=fps, slow_motion=r['slow_motion'], frame_end=count,
                    physical_duration_sec=r['duration_sec'], playback_duration_sec=count / r['fps'],
                    sampled_end_time_sec=(count - 1) / fps,
                    objects={
                        'driver_can': dict(present=bodies[0] is not None, mass_kg=masses[0], radius_m=DRIVER_RADIUS,
                                           height_m=DRIVER_HEIGHT, shape='revolved rolled-rim convex hull',
                                           origin='tin geometric centre'),
                        'receiver_can': dict(present=bodies[1] is not None, mass_kg=masses[1],
                                             half_extents_m=list(RECEIVER_HALF), shape='box',
                                             origin='tin geometric centre')},
                    timed_edits=[dict(frame=frame, params=params) for frame, params in sorted(schedule.items())],
                    timed_events=timed_events, quality=quality, frames=frames)
    finally:
        p.disconnect(client)


def main():
    parser = add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); data = simulate(load_scenario(args))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for path, payload in [(args.out, data), (args.out.parent / 'simulation_metrics.json', data['quality'])]:
        path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(data['quality'], indent=2))
    if not data['quality']['valid']: raise RuntimeError('Physical validation failed')


if __name__ == '__main__': main()
