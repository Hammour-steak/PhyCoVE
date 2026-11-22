"""Free rigid-body dynamics: throw, bank off the board, fall through the rim.

No trajectory correction, no post-launch forces. The ball is a sphere; the
court's floor, backboard and rim are static. The only thing this file decides
for itself is *how* a launch condition becomes an initial velocity: the
scenario names a release point, an aim point on the backboard and a release
speed, and ``physics/launch.py`` solves for the velocity that hits that point.
"""
from __future__ import annotations

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
import json
import math
from pathlib import Path
import pybullet as b
from scene_config import load_scenario, write_json
import launch
from scene_geometry import (BOARD_CENTER, BOARD_HALF, FLOOR_Z, RIM_Z, RIM_CENTER_X,
                            RIM_CENTER_Y, RIM_SEGMENTS, goal_base_mesh,
                            rim_ring_points, static_boxes)

# Physics a schedule entry may write into the running simulation. The launch
# speed is absent on purpose: it is spent on frame 1, so there is nothing left
# to change later. Gravity is here because "make gravity three times stronger
# after the first impact" is an edit about what the ball does *next*.
TIMED_FIELDS = {'gravity_z', 'ball_restitution', 'ball_friction'}
# The zone in which the ball counts as circling the ring. Its radius stops
# short of the bracket that ties ring to board: a ball wedged on that bracket
# also travels round the rim axis, but it is stuck, not swirling, and counting
# it would let a wedged take pass for the shot this scene is about.
RIM_ZONE_RADIUS = 0.185
RIM_ZONE_HEIGHT = 0.26
# DELETE backboard (board_presence [0]) takes the board, its bracket and the
# rim out of the world. The shot then carries on past the goal into parts that
# are scenery in every other case (boom arms, strut, end wall, doors). For that
# case only they are solid: their rendered triangles, exported from the built
# scene by tools/export_board_absent_colliders.py, become static meshes.
BOARD_ABSENT_COLLIDERS = Path(__file__).resolve().parent / 'physics' / 'board_absent_colliders.json'
# Effective coefficients of those surfaces (the ball brings its own 0.60):
# goal steel as the counterweight box, vinyl crash pads soft, the rest of the
# hall (painted block, steel doors and frames) a hard wall.
PAD_RESTITUTION, PAD_FRICTION = 0.30, 0.60
WALL_RESTITUTION, WALL_FRICTION = 0.55, 0.50


def load_schedule(physics, frame_count):
    """Read a scenario's timed-edit schedule into ``{frame: params}``."""
    entries = physics.get('timed_edits', [])
    if not isinstance(entries, list):
        raise ValueError('timed_edits must be a list of {frame, params} events')
    schedule = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'frame', 'params'}:
            raise ValueError('Each timed edit needs exactly a frame and a params object')
        frame = entry['frame']
        if isinstance(frame, bool) or not isinstance(frame, int) or not 2 <= frame <= frame_count:
            raise ValueError(f'Timed edit frame {frame!r} is outside 2..{frame_count}')
        if frame in schedule:
            raise ValueError(f'Two timed edits target frame {frame}')
        params = entry['params']
        if not isinstance(params, dict) or not params:
            raise ValueError(f'Timed edit at frame {frame} carries no parameters')
        unknown = set(params) - TIMED_FIELDS
        if unknown:
            raise ValueError(f'A timed edit cannot change: {sorted(unknown)}')
        for name, value in params.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'Timed {name} must be a finite number')
        schedule[frame] = dict(params)
    return schedule


def apply_timed_params(client, frame, params, ball, physics, fps):
    """Write a scheduled parameter set into the live world and report both ends.

    Only a field of the world or of the ball's dynamics moves; the ball's pose
    and velocity are read before and after so the record can show that the edit
    redefined a coefficient rather than kicking the body.
    """
    position, _ = b.getBasePositionAndOrientation(ball, physicsClientId=client)
    linear, _ = b.getBaseVelocity(ball, physicsClientId=client)
    before = {'params': {name: physics[name] for name in params},
              'location': list(position), 'linear_velocity': list(linear)}
    physics.update(params)
    if 'gravity_z' in params:
        b.setGravity(0, 0, params['gravity_z'], physicsClientId=client)
    dynamics = {}
    if 'ball_restitution' in params:
        dynamics['restitution'] = params['ball_restitution']
    if 'ball_friction' in params:
        dynamics['lateralFriction'] = params['ball_friction']
    if dynamics:
        b.changeDynamics(ball, -1, physicsClientId=client, **dynamics)
    position_after, _ = b.getBasePositionAndOrientation(ball, physicsClientId=client)
    linear_after, _ = b.getBaseVelocity(ball, physicsClientId=client)
    if list(position_after) != list(position) or list(linear_after) != list(linear):
        raise RuntimeError('A parameter change moved the ball; that is a kick, not an edit')
    return {'frame': frame, 'time_sec': (frame - 1) / fps, 'params': params,
            'before': before,
            'after': {'params': {name: physics[name] for name in params},
                      'location': list(position_after),
                      'linear_velocity': list(linear_after)},
            'status': 'applied', 'effective_from_frame': frame}


def build_world(client, p):
    """The static court plus the ball; the ball is the only free body."""
    labels = {}
    board = bool(p.get('board_presence', [1])[0])
    for name, centre, half in static_boxes():
        if not board and name in ('backboard', 'rim_bracket'):
            continue
        shape = b.createCollisionShape(b.GEOM_BOX, halfExtents=half, physicsClientId=client)
        body = b.createMultiBody(0, shape, basePosition=centre, physicsClientId=client)
        if name == 'floor':
            dynamics = dict(restitution=p['floor_restitution'],
                            lateralFriction=p['floor_friction'],
                            rollingFriction=p['floor_rolling_friction'])
        elif name == 'backboard':
            dynamics = dict(restitution=p['board_restitution'],
                            lateralFriction=p['board_friction'])
        else:
            dynamics = dict(restitution=p['rim_restitution'], lateralFriction=p['rim_friction'])
        b.changeDynamics(body, -1, physicsClientId=client, **dynamics)
        labels[body] = name
    # The counterweight box is a wedge, so it goes in as a mesh: a box primitive
    # would either float above the ramp or bury the ball in solid steel.
    vertices, faces = goal_base_mesh()
    shape = b.createCollisionShape(b.GEOM_MESH, vertices=vertices, indices=faces,
                                  physicsClientId=client)
    body = b.createMultiBody(0, shape, basePosition=[0, 0, 0], physicsClientId=client)
    b.changeDynamics(body, -1, restitution=p['goal_base_restitution'],
                     lateralFriction=p['goal_base_friction'], physicsClientId=client)
    labels[body] = 'goal_base'
    # The rim: RIM_SEGMENTS static spheres on the ring centreline, spaced at
    # half the tube radius so consecutive spheres overlap and no gap survives
    # between two of them for a 21 cm ball to fall through.
    if not board:
        for item in json.loads(BOARD_ABSENT_COLLIDERS.read_text(encoding='utf-8'))['colliders']:
            shape = b.createCollisionShape(b.GEOM_MESH, vertices=item['vertices'], indices=item['indices'],
                                          physicsClientId=client)
            body = b.createMultiBody(0, shape, basePosition=[0, 0, 0], physicsClientId=client)
            restitution, friction = {'steel': (p['goal_base_restitution'], p['goal_base_friction']),
                                     'pad': (PAD_RESTITUTION, PAD_FRICTION)}.get(
                                         item['material'], (WALL_RESTITUTION, WALL_FRICTION))
            b.changeDynamics(body, -1, restitution=restitution, lateralFriction=friction, physicsClientId=client)
            labels[body] = item['label']
    shape = b.createCollisionShape(b.GEOM_SPHERE, radius=p.get('rim_tube', 0.0123),
                                   physicsClientId=client)
    for point in (rim_ring_points(RIM_SEGMENTS) if board else []):
        body = b.createMultiBody(0, shape, basePosition=list(point), physicsClientId=client)
        b.changeDynamics(body, -1, restitution=p['rim_restitution'],
                         lateralFriction=p['rim_friction'], physicsClientId=client)
        labels[body] = 'rim'
    r = p['ball_radius']
    shape = b.createCollisionShape(b.GEOM_SPHERE, radius=r, physicsClientId=client)
    velocity, info = launch.solve(p['ball_release_location'],
                                  [p['ball_aim_x'], p['board_face_y'], p['ball_aim_z']],
                                  p['ball_initial_speed'], abs(p['gravity_z']), p['ball_arc'])
    ball = b.createMultiBody(p['ball_mass'], shape,
                             basePosition=list(p['ball_release_location']),
                             physicsClientId=client)
    b.changeDynamics(ball, -1, restitution=p['ball_restitution'],
                     lateralFriction=p['ball_friction'],
                     rollingFriction=p['ball_rolling_friction'],
                     spinningFriction=p['ball_spinning_friction'],
                     linearDamping=p['ball_linear_damping'],
                     angularDamping=p['ball_angular_damping'],
                     ccdSweptSphereRadius=r * .8,
                     contactProcessingThreshold=0,
                     physicsClientId=client)
    spin = launch.spin_vector(p['ball_spin'], velocity[:2], p['ball_spin_tilt_deg'])
    b.resetBaseVelocity(ball, linearVelocity=velocity, angularVelocity=spin,
                        physicsClientId=client)
    labels[ball] = 'ball'
    return ball, labels, velocity, spin, info


def rim_entry_geometry(point, velocity):
    """How the ball met the ring: where, and is it sliding round or dropping in?

    A ball that drops through the middle has no tangential velocity and no
    story; a ball that circles the rim arrives sliding *along* the ring. Both
    numbers are recorded so a run can be judged without watching it: the
    radial distance from the ring axis, and the fraction of the horizontal
    speed that is tangent to the ring at that point (1.0 = pure orbit,
    0.0 = straight at the axis).
    """
    dx, dy = point[0] - RIM_CENTER_X, point[1] - RIM_CENTER_Y
    radial = math.hypot(dx, dy)
    tangent = (-dy / radial, dx / radial) if radial > 1e-6 else (1.0, 0.0)
    horizontal = math.hypot(velocity[0], velocity[1])
    tangential_speed = velocity[0] * tangent[0] + velocity[1] * tangent[1]
    return {'azimuth_deg': math.degrees(math.atan2(dy, dx)),
            'radial_distance_m': radial,
            'tangential_speed_m_s': tangential_speed,
            'tangential_fraction': abs(tangential_speed) / horizontal if horizontal > 1e-6 else 0.0,
            'vertical_speed_m_s': velocity[2]}


def contact_note(contacts, labels, ball):
    """Split the ball's contacts into named surfaces, keeping the strongest."""
    seen = {}
    for contact in contacts:
        body = contact[2]
        label = labels.get(body)
        if label is None or label == 'ball':
            continue
        distance, impulse = contact[8], contact[9]
        if label not in seen or impulse > seen[label][1]:
            seen[label] = (contact, impulse)
    return seen


def simulate(scenario):
    p = scenario['physics']
    fps, sub = int(p['fps']), int(p['substeps_per_frame'])
    count = round(fps * p['duration_sec'])
    dt = 1 / (fps * sub)
    r = p['ball_radius']
    schedule = load_schedule(p, count)
    client = b.connect(b.DIRECT)
    try:
        b.setGravity(0, 0, p['gravity_z'], physicsClientId=client)
        b.setTimeStep(dt, physicsClientId=client)
        b.setPhysicsEngineParameter(numSolverIterations=int(p['solver_iterations']),
                                    deterministicOverlappingPairs=1,
                                    restitutionVelocityThreshold=0.02,
                                    contactBreakingThreshold=0.0005,
                                    contactSlop=0.0002,
                                    physicsClientId=client)
        ball, labels, velocity, spin, launch_info = build_world(client, p)
        frames, events, timed_events = [], [], []
        previous = set()
        first_touch = {}
        orbit = {'revolutions': 0.0, 'signed_revolutions': 0.0, 'entered_frame': None,
                 'exited_frame': None, 'last_azimuth': None, 'samples': 0}
        through = None
        landing = None
        minimum_floor_gap, minimum_board_gap = 1.0, 1.0
        for frame in range(1, count + 1):
            # The edit lands at the top of its frame: frames 1..n-1 have already
            # been stepped on the baseline physics, and this frame's steps run
            # on the edited value from the state the baseline had reached.
            if frame in schedule:
                timed_events.append(apply_timed_params(client, frame, schedule[frame],
                                                       ball, p, fps))
            if frame > 1:
                for step in range(sub):
                    before_v = list(b.getBaseVelocity(ball, physicsClientId=client)[0])
                    b.stepSimulation(physicsClientId=client)
                    now = {label: contact for label, (contact, _) in
                           contact_note(b.getContactPoints(bodyA=ball, physicsClientId=client),
                                        labels, ball).items()}
                    for label, contact in now.items():
                        if label in previous:
                            continue
                        t = ((frame - 1) * sub + step) * dt
                        after_v = list(b.getBaseVelocity(ball, physicsClientId=client)[0])
                        point = list(b.getBasePositionAndOrientation(ball, physicsClientId=client)[0])
                        event = {'surface': label, 'time_sec': t, 'frame_index': frame,
                                 'position': point,
                                 'incoming_velocity': before_v, 'outgoing_velocity': after_v,
                                 'normal_impulse_ns': contact[9] * dt}
                        if label == 'rim':
                            event['rim_entry'] = rim_entry_geometry(point, before_v)
                        events.append(event)
                        first_touch.setdefault(label, event)
                        # The counterweight box counts as ground: a ball that
                        # settles on top of it has landed, and calling that
                        # "still airborne" would be a lie about the last second
                        # of the clip.
                        if label in ('floor', 'goal_base') and landing is None:
                            landing = event
                    previous = set(now)
                    pos = b.getBasePositionAndOrientation(ball, physicsClientId=client)[0]
                    minimum_floor_gap = min(minimum_floor_gap, pos[2] - r - FLOOR_Z)
                    # The board gap only means "did the ball get inside the
                    # panel" while the ball is actually in front of the panel.
                    # Past its edge the number is just how far behind the board
                    # the ball has travelled, which is where it ends up.
                    if (abs(pos[0]) < BOARD_HALF[0] + r
                            and abs(pos[2] - BOARD_CENTER[2]) < BOARD_HALF[2] + r
                            and pos[1] < p['board_face_y']):
                        minimum_board_gap = min(minimum_board_gap,
                                                p['board_face_y'] - pos[1] - r)
                    # Rim orbit: the ball's azimuth about the ring axis, sampled
                    # every substep while it is close enough to the ring to be
                    # circling it. Cumulative |dtheta| is the revolutions a
                    # viewer sees; the signed sum says whether they were one
                    # way round or a rock back and forth.
                    dx, dy = pos[0] - RIM_CENTER_X, pos[1] - RIM_CENTER_Y
                    if (math.hypot(dx, dy) < RIM_ZONE_RADIUS
                            and abs(pos[2] - RIM_Z) < RIM_ZONE_HEIGHT):
                        azimuth = math.atan2(dy, dx)
                        if orbit['entered_frame'] is None:
                            orbit['entered_frame'] = frame
                        if orbit['last_azimuth'] is not None:
                            delta = math.atan2(math.sin(azimuth - orbit['last_azimuth']),
                                               math.cos(azimuth - orbit['last_azimuth']))
                            orbit['revolutions'] += abs(delta) / (2 * math.pi)
                            orbit['signed_revolutions'] += delta / (2 * math.pi)
                        orbit['last_azimuth'] = azimuth
                        orbit['samples'] += 1
                        orbit['exited_frame'] = frame
                    if through is None and pos[2] < RIM_Z - r * 0.5 and math.hypot(dx, dy) < 0.14:
                        through = {'frame_index': frame, 'time_sec': (frame - 1) / fps,
                                   'axis_distance_m': math.hypot(dx, dy),
                                   'location': list(pos)}
            pos, quat = b.getBasePositionAndOrientation(ball, physicsClientId=client)
            vel, omega = b.getBaseVelocity(ball, physicsClientId=client)
            frames.append({'frame_index': frame, 'time_sec': (frame - 1) / fps,
                           'ball_location': list(pos), 'ball_quaternion_xyzw': list(quat),
                           'ball_linear_velocity': list(vel),
                           'ball_angular_velocity': list(omega)})
        metrics = {
            'launch': {'velocity_m_s': velocity, 'spin_rad_s': spin,
                       'launch_angle_deg': launch_info['launch_angle_deg'],
                       'predicted_flight_time_sec': launch_info['flight_time_sec'],
                       'predicted_apex_m': launch_info['apex_m']},
            'surface_sequence': [e['surface'] for e in events],
            'events': events,
            'cell_sequence': [(e['surface'], e['frame_index']) for e in events],
            'board_impact': first_touch.get('backboard'),
            'first_rim_contact': first_touch.get('rim'),
            'landing': landing,
            'rim_contact_count': sum(1 for e in events if e['surface'] == 'rim'),
            'rim_orbit_revolutions': round(orbit['revolutions'], 3),
            'rim_orbit_signed_revolutions': round(orbit['signed_revolutions'], 3),
            'rim_orbit_entered_frame': orbit['entered_frame'],
            'rim_orbit_exited_frame': orbit['exited_frame'],
            'through_rim': through,
            'passed_through_rim': through is not None,
            'min_floor_gap_m': minimum_floor_gap,
            'min_board_gap_m': minimum_board_gap,
            'path_length_m': sum(math.dist(a['ball_location'], c['ball_location'])
                                 for a, c in zip(frames, frames[1:])),
            'final_position': frames[-1]['ball_location'],
            'ball_mass_kg': p['ball_mass'], 'ball_radius_m': r,
            'timed_events': timed_events,
            'note': ('One rigid sphere against a static floor, backboard, bracket, wedged '
                     'counterweight box and 96-sphere rim. The ball is the only body that '
                     'moves, so every frame is a function of the launch and the contact '
                     'coefficients alone.'),
        }
        return {'schema_version': 1, 'simulator': 'pybullet', 'fps': fps, 'frame_start': 1,
                'frame_end': count, 'duration_sec': p['duration_sec'], 'physics': p,
                'timed_edits': p.get('timed_edits', []), 'frames': frames, 'metrics': metrics}
    finally:
        b.disconnect(client)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--scenario-overrides-json', type=Path)
    args = parser.parse_args()
    data = simulate(load_scenario(args.scenario_overrides_json))
    write_json(args.out, data)
    write_json(args.out.with_name('simulation_metrics.json'), data['metrics'])
    m = data['metrics']
    print('events', m['cell_sequence'], 'orbit', m['rim_orbit_revolutions'],
          'through', m['passed_through_rim'])


if __name__ == '__main__':
    main()
