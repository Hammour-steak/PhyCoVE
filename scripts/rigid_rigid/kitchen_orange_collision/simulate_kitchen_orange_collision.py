"""Free 3D rigid-body rolling, impact and sliding on a kitchen table; nothing is scripted."""
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
from validate_kitchen_orange_collision import simulation_signature


# The source coefficients, used for the settling pass: a rest
# pose does not depend on friction, so starting every run from these makes an
# edit show up in the motion only.
SOURCE_ORANGE_MU, SOURCE_TABLE_MU = .72, 1.0

# A mid-run write lands in a body that is already moving, so its band is about
# keeping the run physical rather than about reproducing the source clip: an
# orange shoved to 7.2 m/s halfway across the table is a legitimate edit even
# though the scenario's own launch band stops at 3.2 m/s.
TIMED_FIELDS = {'initial_velocity': (0.0, 9.0), 'driver_mass': (.05, 2.),
                'cut_mass': (.05, 2.), 'restitution': (0.0, 1.0),
                'orange_friction': (.05, 1.5), 'table_friction': (0.0, 2.)}


def timed_schedule(ph, count):
    """Read ``physics.timed_edits`` into ``{frame: params}``, rejecting nonsense.

    Frame 1 is refused: the scenario's ordinary parameters already set that
    state, and accepting it here would give one edit two spellings.
    """
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
    afterwards. The rolling orange is given the spin that matches its new
    speed, so a mid-run speed edit keeps it rolling instead of skidding.
    """
    events = []
    for key, value in params.items():
        state_before = body_state(p, bodies)
        if key == 'initial_velocity':
            body = bodies[0]
            linear, angular = p.getBaseVelocity(body)
            before = float(linear[0])
            p.resetBaseVelocity(body, [float(value), 0.0, 0.0], [0.0, float(value) / RADIUS, 0.0])
            after = float(p.getBaseVelocity(body)[0][0])
        elif key in ('driver_mass', 'cut_mass'):
            body = bodies[0] if key == 'driver_mass' else bodies[1]
            before = float(p.getDynamicsInfo(body, -1)[0])
            p.changeDynamics(body, -1, mass=float(value))
            after = float(p.getDynamicsInfo(body, -1)[0])
        elif key == 'table_friction':
            before = float(p.getDynamicsInfo(table, -1)[1])
            p.changeDynamics(table, -1, lateralFriction=float(value))
            after = float(p.getDynamicsInfo(table, -1)[1])
        elif key == 'orange_friction':
            before = float(p.getDynamicsInfo(bodies[0], -1)[1])
            for body in bodies:
                if body is not None:
                    p.changeDynamics(body, -1, lateralFriction=float(value))
            after = float(p.getDynamicsInfo(bodies[0], -1)[1])
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


def simulate(s):

    import pybullet as p
    validate(s)
    r = s['render']; ph = s['physics']; fps = r['fps'] * r['slow_motion']
    count = round(fps * r['duration_sec']); stride = SIM_HZ // fps
    orange_mu = float(ph['orange_friction']); table_mu = float(ph['table_friction'])
    rear_count = int(ph['rear_oranges'])
    # Validated before any body exists: a schedule that names a frame outside
    # the clip or a field this scene cannot write is not worth simulating.
    schedule = timed_schedule(ph, count)
    present = [key for key, switch in (('driver_orange', 'driver_active'), ('cut_orange', 'cut_active'))
               if ph.get(switch, [1])[0]] + ['rear_orange_1', 'rear_orange_2'][:rear_count]
    client = p.connect(p.DIRECT)
    try:
        p.setGravity(0, 0, -9.81); p.setTimeStep(1 / SIM_HZ)
        p.setPhysicsEngineParameter(numSolverIterations=120, restitutionVelocityThreshold=.001,
                                    deterministicOverlappingPairs=1, contactBreakingThreshold=.0003)
        shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=[TABLE_HALF[0], TABLE_HALF[1], .02])
        table = p.createMultiBody(0, shape, basePosition=[TABLE_CENTER[0], TABLE_CENTER[1], TABLE_TOP_Z - .02])
        p.changeDynamics(table, -1, lateralFriction=SOURCE_TABLE_MU, restitution=0.)
        # The kitchen floor, so an orange that runs off the end of the table lands
        # instead of falling for ever.  It sits at z = 0, which is where the
        # imported floor plane is.
        floor_shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=[60., 60., .02])
        floor = p.createMultiBody(0, floor_shape, basePosition=[0., 0., -.02])
        p.changeDynamics(floor, -1, lateralFriction=SOURCE_TABLE_MU, restitution=0.)
        # Whole oranges get the analytic sphere: a faceted hull makes a rolling
        # ball climb over its own edges and lose a third of its speed per
        # decimetre.  The sliced orange has to be a hull, because the slice is
        # the point of it, so its dome is sampled at 48 rings (0.08 mm bumps).
        sphere_shape = p.createCollisionShape(p.GEOM_SPHERE, radius=RADIUS)
        cut_shape = p.createCollisionShape(p.GEOM_MESH, vertices=cut_vertices())
        masses = {'driver_orange': ph['driver_mass'], 'cut_orange': ph['cut_mass'],
                  'rear_orange_1': ph['driver_mass'], 'rear_orange_2': ph['driver_mass']}
        bodies = []; cut_inertia = cut_body_parameters(masses['cut_orange'])
        for key in KEYS:
            if key not in present:
                bodies.append(None); continue
            if key == 'driver_orange':
                pos = [START_X[0], DRIVER_Y, TABLE_TOP_Z + RADIUS + .0002]
                body = p.createMultiBody(masses[key], sphere_shape, basePosition=pos)
                p.changeDynamics(body, -1, localInertiaDiagonal=sphere_inertia(masses[key]))
            elif key == 'cut_orange':
                # The body origin is the sphere centre and the dome is the
                # resting face, so the centre sits one radius above the table
                # exactly like the rolling orange: a level hit.
                pos = [START_X[1], CUT_Y, TABLE_TOP_Z + RADIUS + .0002]
                body = p.createMultiBody(masses[key], cut_shape, basePosition=pos,
                                         baseOrientation=p.getQuaternionFromEuler([0, 0, math.radians(CUT_YAW_DEG)]),
                                         baseInertialFramePosition=[0, 0, cut_inertia['inertial_frame_z']])
                p.changeDynamics(body, -1, localInertiaDiagonal=cut_inertia['inertia'])
            else:
                index = int(key[-1]) - 1
                pos = [rear_x(rear_count)[index], CUT_Y, TABLE_TOP_Z + RADIUS + .0002]
                body = p.createMultiBody(masses[key], sphere_shape, basePosition=pos)
                p.changeDynamics(body, -1, localInertiaDiagonal=sphere_inertia(masses[key]))
            p.changeDynamics(body, -1, lateralFriction=SOURCE_ORANGE_MU, restitution=math.sqrt(ph['restitution']),
                             rollingFriction=ROLLING_FRICTION, spinningFriction=.0002, linearDamping=0., angularDamping=0.,
                             collisionMargin=.0002, contactProcessingThreshold=.001)
            bodies.append(body)
        for _ in range(240):
            p.stepSimulation()
        # The settling pass is not part of the clip. It runs on the source
        # coefficients so that an edit changes the motion after frame 1 and not
        # the rest pose the clip starts from.
        p.changeDynamics(table, -1, lateralFriction=table_mu)
        for body in bodies:
            if body is not None:
                p.changeDynamics(body, -1, lateralFriction=orange_mu)
        if bodies[0] is not None:
            p.resetBaseVelocity(bodies[0], [ph['initial_velocity'], 0, 0], [0, ph['initial_velocity'] / RADIUS, 0])
        frames = []; first_impact = None; max_penetration = 0.; max_cut_tilt = 0.; max_cut_speed = 0.
        edge = 10.; last_motion = 0.; contact_impulse = 0.; max_slip_ratio = 0.; timed_events = []
        min_body_z = 10.
        cut = bodies[1]
        for step in range((count - 1) * stride + 1):
            t = step / SIM_HZ
            contacts = p.getContactPoints(bodies[0], cut) if bodies[0] is not None and cut is not None else []
            if contacts and first_impact is None:
                first_impact = t
            contact_impulse += sum(c[9] / SIM_HZ for c in contacts)
            for i, b in enumerate(bodies):
                if b is None:
                    continue
                pos, q = p.getBasePositionAndOrientation(b); v, w = p.getBaseVelocity(b)
                min_body_z = min(min_body_z, pos[2])
                if math.hypot(*v[:2]) > .005:
                    last_motion = t
                mat = p.getMatrixFromQuaternion(q)
                extent_x = RADIUS * math.sqrt(max(0., 1. - mat[6] ** 2)) + RADIUS
                extent_y = RADIUS * math.sqrt(max(0., 1. - mat[7] ** 2)) + RADIUS
                edge = min(edge, TABLE_HALF[0] - abs(pos[0] - TABLE_CENTER[0]) - extent_x / 2,
                           TABLE_HALF[1] - abs(pos[1] - TABLE_CENTER[1]) - extent_y / 2)
                if i == 1:
                    # The struck orange rolls, so its body frame turns with it:
                    # this is how far it has rolled, not how far it has tipped.
                    max_cut_tilt = max(max_cut_tilt, math.degrees(math.acos(max(-1., min(1., mat[8])))))
                    max_cut_speed = max(max_cut_speed, math.hypot(*v[:2]))
                elif i == 0 and first_impact is None and abs(v[0]) > .02:
                    # Rolling, not skidding: the contact point's speed is v - w*R.
                    max_slip_ratio = max(max_slip_ratio, abs(v[0] - w[1] * RADIUS) / abs(v[0]))
                for c in p.getContactPoints(bodyA=b):
                    max_penetration = max(max_penetration, -c[8])
            if step % stride == 0:
                frame_index = len(frames) + 1
                # The edit lands at the top of its frame: the state recorded
                # here is already the edited one, and every earlier frame is
                # the source clip's own physics.
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
            if step < (count - 1) * stride:
                p.stepSimulation()
        speeds = [math.hypot(*p.getBaseVelocity(b)[0][:2]) for b in bodies if b is not None]
        travel = {k: (frames[-1][k]['location'][0] - frames[0][k]['location'][0]
                      if frames[0][k]['present'] else None) for k in KEYS}
        rear_travel = [travel['rear_orange_1'], travel['rear_orange_2']][:rear_count]
        # Validity is about the solver, not about the shot: a five-times-heavier
        # orange legitimately runs off the end of a 1.8 m table, so leaving the
        # table is reported rather than rejected.  Nothing may pass through it,
        # though, and nothing may end up under the floor.
        # 5 mm of transient overlap is a fortieth of an orange radius: it is what
        # a body landing on the floor at 3.8 m/s looks like at a 1/1440 s step,
        # and well under anything visible.  Only a solver that lets bodies sink
        # into each other should fail.
        quality = dict(valid=max_penetration < .005 and min_body_z > 0.,
                       left_table=edge < 0,
                       first_impact_sec=first_impact,
                       transmission_observed=max_cut_speed > .02,
                       cut_max_speed_m_s=max_cut_speed,
                       rear_max_speed_m_s=max((math.hypot(*f[k]['linear_velocity'][:2])
                                               for f in frames for k in ('rear_orange_1', 'rear_orange_2')
                                               if f[k]['present']), default=0.),
                       displacement_x_m=travel, rear_queue_travel_m=rear_travel,
                       cut_roll_deg=max_cut_tilt, min_body_centre_z=min_body_z,
                       max_penetration_m=max_penetration,
                       min_table_edge_clearance_m=edge, max_preimpact_slip_ratio=max_slip_ratio,
                       contact_normal_impulse_Ns=contact_impulse, last_motion_sec=last_motion,
                       settled_by_end=max(speeds) < .005, final_speed_m_s=max(speeds),
                       requested_pair_restitution=ph['restitution'],
                       requested_orange_friction=ph['orange_friction'],
                       requested_table_friction=ph['table_friction'],
                       rear_oranges=rear_count)
        return dict(schema_version=2, scene=SCENE_NAME, scenario=deepcopy(s), simulation_signature=simulation_signature(s),
                    solver=dict(name='PyBullet', api_version=p.getAPIVersion(), constants=fixed_constants()),
                    playback_fps=r['fps'], sample_fps=fps, slow_motion=r['slow_motion'], frame_end=count,
                    physical_duration_sec=r['duration_sec'], playback_duration_sec=count / r['fps'],
                    sampled_end_time_sec=(count - 1) / fps,
                    objects={k: dict(present=k in present, mass_kg=masses[k], radius_m=RADIUS,
                                     height_m=2 * RADIUS if k != 'cut_orange' else RADIUS + CUT_TOP,
                                     collision_shape='convex hull of the sampled orange surface'
                                     if k != 'cut_orange' else 'convex hull of the sliced orange, dome down and cut face up',
                                     origin='orange geometric centre') for k in KEYS},
                    timed_edits=[dict(frame=frame, params=params) for frame, params in sorted(schedule.items())],
                    timed_events=timed_events,
                    quality=quality, frames=frames)
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
    if not data['quality']['valid']:
        raise RuntimeError('Physical validation failed')


if __name__ == '__main__':
    main()
