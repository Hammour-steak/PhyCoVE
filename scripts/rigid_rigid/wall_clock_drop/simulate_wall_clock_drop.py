"""Full 3D PyBullet rigid bodies: a wall clock falls off the wall onto a pine crate."""
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
from scene_config import SCENE_NAME, add_scenario_arguments, load_scenario, validate
from scene_geometry import (KEYS, SIM_HZ, SOLVER_ITERATIONS, CLOCK_RADIUS,
                            CLOCK_THICKNESS, CRATE_HALF_EXTENTS, CLOCK_LINEAR_DAMPING,
                            CLOCK_ANGULAR_DAMPING, CLOCK_ROLLING_FRICTION, CRATE_ROLLING_FRICTION,
                            CRATE_SPINNING_FRICTION, CRATE_ANGULAR_DAMPING, layout, present,
                            fixed_constants)
from room_colliders import load_colliders
from validate_wall_clock_drop import simulation_signature

# The disc hangs face-forward: its axis (the mesh's local +z) points along +y,
# which is a -90 degree rotation about x.
HANG_QUATERNION_XYZW = (-.7071067811865476, 0., 0., .7071067811865476)
# Nothing is allowed above the room's ceiling.
CEILING_MARGIN = 2.50


def _tilt_deg(m22):
    """Tilt of a body's local +z away from world +z, in degrees, from R[2][2]."""
    return math.degrees(math.acos(max(-1., min(1., m22))))


def simulate(s):
    import pybullet as p
    validate(s)
    r = s['render']
    ph = s['physics']
    sample_fps = r['fps'] * r['slow_motion']
    count = round(sample_fps * r['duration_sec'])
    stride = SIM_HZ // sample_fps
    gravity_z = float(ph['gravity_z'])
    timed_by_frame = {}
    for entry in ph.get('timed_edits') or []:
        frame, params = entry['frame'], entry['params']
        if not isinstance(frame, int) or not 2 <= frame <= count or set(params) != {'gravity_z'}:
            raise ValueError(f'Unsupported or invalid timed event: {entry!r}')
        value = float(params['gravity_z'])
        if not math.isfinite(value) or not -60. <= value <= 0.:
            raise ValueError('Timed gravity must be finite and point down or vanish')
        timed_by_frame.setdefault(frame, []).append(value)

    client = p.connect(p.DIRECT)
    try:
        p.setGravity(0, 0, gravity_z)
        p.setTimeStep(1 / SIM_HZ)
        p.setPhysicsEngineParameter(numSolverIterations=SOLVER_ITERATIONS, restitutionVelocityThreshold=.001,
                                    deterministicOverlappingPairs=1, contactBreakingThreshold=.0005)
        # The room: two floor levels, four walls and the south plinth, plus the
        # furniture boxes of the level the scene first stood in, all from the
        # scene's collider file (the rendered boot room is built on them).
        room = load_colliders()
        statics = {}
        for box in room['boxes']:
            shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=box['half_extents'])
            body = p.createMultiBody(0, shape, basePosition=box['center'])
            floor_like = box['name'].startswith('floor_')
            p.changeDynamics(body, -1, lateralFriction=.52, restitution=ph['floor_restitution'] if floor_like
                             else ph['fixture_restitution'])
            statics[box['name']] = body
        # The clock: the case alone, a disc of its true diameter and depth.
        # DELETE clock (clock_active [0]) never builds it.
        clock = None
        if present(ph, 'clock'):
            clock_shape = p.createCollisionShape(p.GEOM_CYLINDER, radius=CLOCK_RADIUS, height=CLOCK_THICKNESS)
            spawn = layout(ph)['clock']
            clock = p.createMultiBody(ph['clock_mass'], clock_shape, basePosition=spawn,
                                      baseOrientation=HANG_QUATERNION_XYZW)
            p.changeDynamics(clock, -1, lateralFriction=ph['clock_friction'], restitution=ph['clock_restitution'],
                             spinningFriction=.002, rollingFriction=CLOCK_ROLLING_FRICTION,
                             linearDamping=CLOCK_LINEAR_DAMPING, angularDamping=CLOCK_ANGULAR_DAMPING,
                             collisionMargin=.0004, contactProcessingThreshold=.002, ccdSweptSphereRadius=.06)
        # The crate: a nailed pine box on the floor beneath the fall line. The
        # half extents are the same three numbers the renderer scales its boards
        # to, so the crate that tips over is exactly this box -- the boards and
        # the air between them are a rigid body, not a soft shell.
        crate_body = None
        if present(ph, 'crate'):
            crate_shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=list(CRATE_HALF_EXTENTS))
            crate_body = p.createMultiBody(ph['crate_mass'], crate_shape, basePosition=layout(ph)['crate'])
            p.changeDynamics(crate_body, -1, lateralFriction=ph['crate_friction'],
                             restitution=ph['crate_restitution'],
                             spinningFriction=CRATE_SPINNING_FRICTION, rollingFriction=CRATE_ROLLING_FRICTION,
                             linearDamping=0., angularDamping=CRATE_ANGULAR_DAMPING,
                             collisionMargin=.0004, contactProcessingThreshold=.002)
        # The hanger lets go: the case drifts off the wall while it tips over.
        if clock is not None:
            p.resetBaseVelocity(clock, [0., float(ph['clock_push']), 0.], [float(ph['clock_tip_spin']), 0., 0.])

        dynamic = ([clock] if clock is not None else []) + ([crate_body] if crate_body is not None else [])
        pairs = [(body, name) for name, body in statics.items()]
        if crate_body is not None:
            pairs.append((crate_body, 'crate'))
        frames, events = [], []
        contact_state = {pair: False for pair in pairs}
        crate_contact_state = {pair: False for pair in pairs if pair[1] != 'crate'}
        max_penetration = 0.
        escaped = False
        first_impact = first_crate_impact = first_floor_impact = first_wall_impact = None
        crate_tilt_max = 0.
        timed_events = []
        crate_peak_speed = 0.
        pre_v = [list(p.getBaseVelocity(b)[0]) for b in dynamic]

        for step in range((count - 1) * stride + 1):
            t = step / SIM_HZ
            if step % stride == 0:
                # A timed edit fires at its frame boundary, before the motion
                # that follows it, and the run carries on from the state it had
                # reached -- every frame before it is the source video's own.
                frame_number = step // stride + 1
                for value in timed_by_frame.get(frame_number, []):
                    previous = gravity_z
                    gravity_z = float(value)
                    p.setGravity(0, 0, gravity_z)
                    timed_events.append(dict(frame=frame_number, time_sec=t, parameter='gravity_z',
                                             from_value=previous, to_value=gravity_z,
                                             applied_in_simulation=True))
            # Clock against everything else.
            for other_body, other in (pairs if clock is not None else ()):
                contacts = p.getContactPoints(clock, other_body)
                contact = bool(contacts)
                if contact and not contact_state[(other_body, other)]:
                    events.append(dict(time_sec=t, object=other, actor='clock',
                                       pre_velocity=pre_v[0] if other != 'crate' else pre_v[-1]))
                    if first_impact is None:
                        first_impact = t
                    if other == 'crate' and first_crate_impact is None:
                        first_crate_impact = t
                    elif other.startswith('floor') and first_floor_impact is None:
                        first_floor_impact = t
                    elif other.startswith('wall') and first_wall_impact is None:
                        first_wall_impact = t
                contact_state[(other_body, other)] = contact
                for c in contacts:
                    max_penetration = max(max_penetration, -c[8])
            # Crate against the room (and against the clock, already counted above).
            if crate_body is not None:
                for other_body, other in pairs:
                    if other == 'crate':
                        continue
                    contacts = p.getContactPoints(crate_body, other_body)
                    contact = bool(contacts)
                    if contact and not crate_contact_state[(other_body, other)]:
                        events.append(dict(time_sec=t, object=other, actor='crate'))
                    crate_contact_state[(other_body, other)] = contact
                    for c in contacts:
                        max_penetration = max(max_penetration, -c[8])
            if clock is not None:
                pos, q = p.getBasePositionAndOrientation(clock)
                if not (-4.95 < pos[0] < 3.95 and -2.56 < pos[1] < 3.25 and -0.5 < pos[2] < CEILING_MARGIN):
                    escaped = True
            if crate_body is not None:
                bpos, bq = p.getBasePositionAndOrientation(crate_body)
                if not (-4.95 < bpos[0] < 3.95 and -2.56 < bpos[1] < 3.25):
                    escaped = True
                crate_tilt_max = max(crate_tilt_max, _tilt_deg(p.getMatrixFromQuaternion(bq)[8]))
            crate_peak_speed = (max(crate_peak_speed, math.hypot(*p.getBaseVelocity(crate_body)[0]))
                                if crate_body is not None else crate_peak_speed)
            if step % stride == 0:
                frame = dict(frame_index=len(frames) + 1, time_sec=t)
                for key, body in zip(KEYS, (clock, crate_body)):
                    if body is None:
                        frame[key] = dict(present=False)
                        continue
                    pos_b, q_b = p.getBasePositionAndOrientation(body)
                    linear, angular = p.getBaseVelocity(body)
                    mat = p.getMatrixFromQuaternion(q_b)
                    matrix = [list(mat[j * 3:j * 3 + 3]) + [pos_b[j]] for j in range(3)] + [[0, 0, 0, 1]]
                    frame[key] = dict(present=True, location=list(pos_b), quaternion_xyzw=list(q_b),
                                      linear_velocity=list(linear), angular_velocity=list(angular),
                                      matrix_world=matrix)
                frames.append(frame)
            pre_v = [list(p.getBaseVelocity(b)[0]) for b in dynamic]
            if step < (count - 1) * stride:
                p.stepSimulation()

        final_speed = max(math.hypot(*p.getBaseVelocity(b)[0][:3]) for b in dynamic)
        last = frames[-1]
        clock_disp = (math.dist(frames[0]['clock']['location'], last['clock']['location'])
                      if clock is not None else 0.)
        crate_disp = (math.dist(frames[0]['crate']['location'], last['crate']['location'])
                   if crate_body is not None else 0.)
        crate_tilt_end = _tilt_deg(last['crate']['matrix_world'][2][2]) if crate_body is not None else 0.
        quality = dict(
            valid=(max_penetration < .012 and not escaped),
            first_impact_sec=first_impact, first_crate_impact_sec=first_crate_impact,
            first_floor_impact_sec=first_floor_impact, first_wall_impact_sec=first_wall_impact,
            transmission_observed=(crate_disp > .10 or crate_tilt_max > 20.) if crate_body is not None else False,
            crate_tilt_max_deg=crate_tilt_max, crate_tilt_end_deg=crate_tilt_end,
            crate_displacement_m=crate_disp, crate_peak_speed_m_s=crate_peak_speed,
            clock_displacement_m=clock_disp,
            escaped_room=escaped, settled_by_end=final_speed < .06, final_speed_m_s=final_speed,
            max_penetration_m=max_penetration, effective_gravity_z=gravity_z, timed_events=timed_events,
            events=events)
        return dict(schema_version=2, scene=SCENE_NAME, scenario=deepcopy(s),
                    simulation_signature=simulation_signature(s),
                    solver=dict(name='PyBullet', api_version=p.getAPIVersion(), constants=fixed_constants()),
                    playback_fps=r['fps'], sample_fps=sample_fps, slow_motion=r['slow_motion'],
                    frame_start=1, frame_end=count, physical_duration_sec=r['duration_sec'],
                    playback_duration_sec=r['duration_sec'] * r['slow_motion'],
                    sampled_end_time_sec=(count - 1) / sample_fps,
                    objects={'clock': dict(present=clock is not None, mass_kg=ph['clock_mass'],
                                           collision_shape='cylinder (case disc)',
                                           origin='centre of the clock case'),
                             'crate': dict(present=crate_body is not None, mass_kg=ph['crate_mass'],
                                           collision_shape='box',
                                           origin='centre of the crate')},
                    quality=quality, timed_events=timed_events, frames=frames)
    finally:
        p.disconnect(client)


CEILING_MARGIN = 2.50


def main():
    parser = add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    d = simulate(load_scenario(args))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(d, indent=2, allow_nan=False), encoding='utf-8')
    (args.out.parent / 'simulation_metrics.json').write_text(json.dumps(d['quality'], indent=2, allow_nan=False),
                                                             encoding='utf-8')
    print(json.dumps({k: v for k, v in d['quality'].items() if k != 'events'}, indent=2))
    if not d['quality']['valid']:
        raise RuntimeError('Physical validation failed')


if __name__ == '__main__':
    main()
