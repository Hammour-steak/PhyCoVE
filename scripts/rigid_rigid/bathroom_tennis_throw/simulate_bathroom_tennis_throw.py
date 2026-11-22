"""Tennis ball hurled into a bathroom; static GLB fixture boxes, stool bodies, timed gravity."""
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
from scene_config import *
from scene_geometry import (BALL_RADIUS, STOOL_HALF_A, STOOL_HALF_B, STOOL_TAG, 
                            SIM_HZ, FLOOR_Z, KEYS,
                            BOUNDS_MIN, BOUNDS_MAX, layout, launch_velocity, present)
from bathroom_colliders import load_colliders
from validate_bathroom_tennis_throw import simulation_signature

# Rolling resistance of a felt tennis ball on polished marble. At .0014 the ball
# is still rolling at ~1.1-1.4 m/s when the 4 s clip ends -- 3-4 m after its last
# bounce -- so where it comes to rest (and whether it leaves the shot) is a coin
# flip: 2 cm of aim change flipped one case between "in frame" and 8 frames out.
# .003 settles the aim and gravity cases inside the shot. Do NOT go to .005: the
# extra grip during the spinning toilet impact reverses edit_bouncier_bathroom
# and edit_heavy_gravity_after_impact, throwing the ball back past the camera.
# It does nothing for a speeded-up run -- that ball is flying, not rolling.
BALL_ROLL_FRICTION = .003

# Marble slab under the whole room. It has to reach wall_west's collider face
# (x = -8.60), not the visible floor mesh edge (x = -8.35): the room has no
# visible west wall -- wall_west is synthetic -- so anything between the two
# numbers is a hole with nothing under it. A 1.5x speed run rolls that far
# (3.3 m/s at x = -8.0) and would fall to z = -3 without it.
FLOOR_CENTER = (1.53, -.255, FLOOR_Z - .05)
FLOOR_HALF = (10.13, 4.975, .05)


def spawn_overlap(positions, ph, room):
    """Deepest amount by which any body is born inside a static collider.

    A body that spawns inside a box does not merely clip for one frame: the
    solver pushes it out over the 400-step pre-roll, which is fast enough to
    launch it across the room: a stool born 54 mm inside the shower-door track
    is ejected 1.7 m and enters the visible clip mid-topple. Nothing downstream
    can see it, because every audit starts at frame 1. Measuring it here turns
    the whole class of placement bugs into a hard `valid` failure instead of a
    silent visual glitch.
    """
    boxes = [(b['center'], b['half_extents'], b['name']) for b in room['boxes']]
    boxes.append((list(FLOOR_CENTER), list(FLOOR_HALF), 'floor'))
    worst, offenders = 0., []
    for key in KEYS:
        if not present(ph, key):
            continue
        half = [BALL_RADIUS] * 3 if key == 'tennis_ball' else (
            STOOL_HALF_A if STOOL_TAG[key] == 'a' else STOOL_HALF_B)
        c = positions[key]
        for bc, bh, name in boxes:
            depth = min(min(c[i] + half[i], bc[i] + bh[i]) - max(c[i] - half[i], bc[i] - bh[i])
                        for i in range(3))
            if depth > 1e-3:      # 1 mm: resting contacts sit at -0.1 mm by construction
                offenders.append(dict(body=key, box=name, depth_m=round(depth, 5)))
                worst = max(worst, depth)
    return worst, offenders


def simulate(s):
    import pybullet as p
    validate(s)
    ph = s['physics']
    fps = s['render']['fps']
    count = 4 * fps
    stride = SIM_HZ // fps
    client = p.connect(p.DIRECT)
    try:
        p.setGravity(0, 0, ph['gravity_z'])
        p.setTimeStep(1 / SIM_HZ)
        p.setPhysicsEngineParameter(numSolverIterations=120, deterministicOverlappingPairs=1,
                                    restitutionVelocityThreshold=.015, contactBreakingThreshold=.0002)
        # Marble floor: one slab under the whole room, running from the east
        # wall to the *west* wall's collider face (x -8.60..11.66). The visible
        # floor mesh stops at x = -8.35 (raycast: hit at -8.30, miss at -8.40)
        # and there is no visible west wall at all -- wall_west is synthetic --
        # so a slab sized to the mesh left a 25 cm hole between the floor edge
        # and the wall. Nothing had ever rolled that far until a 1.5x speed
        # edit put the ball there at 3.3 m/s: it dropped through to z = -3.
        floor = p.createMultiBody(0, p.createCollisionShape(p.GEOM_BOX, halfExtents=list(FLOOR_HALF)),
                                  basePosition=list(FLOOR_CENTER))
        p.changeDynamics(floor, -1, lateralFriction=.55, restitution=ph['fixture_restitution'])
        # Bathroom fixtures exported from big_project.glb, plus synthetic walls.
        room = load_colliders()
        fixture_bodies = []
        for box in room['boxes']:
            body = p.createMultiBody(0, p.createCollisionShape(p.GEOM_BOX, halfExtents=box['half_extents']),
                                     basePosition=box['center'])
            p.changeDynamics(body, -1, lateralFriction=.5, restitution=ph['fixture_restitution'])
            fixture_bodies.append(body)
        # Ball and stools.
        sphere = p.createCollisionShape(p.GEOM_SPHERE, radius=BALL_RADIUS)
        stool_shapes = {'a': p.createCollisionShape(p.GEOM_BOX, halfExtents=list(STOOL_HALF_A)),
                        'b': p.createCollisionShape(p.GEOM_BOX, halfExtents=list(STOOL_HALF_B))}
        bodies = {}
        positions = layout(ph)
        spawn_overlap_m, spawn_offenders = spawn_overlap(positions, ph, room)
        for k in KEYS:
            if not present(ph, k):
                bodies[k] = None
                continue
            ball = k == 'tennis_ball'
            b = p.createMultiBody(ph['ball_mass'] if ball else ph['stool_mass'],
                                  sphere if ball else stool_shapes[STOOL_TAG[k]], basePosition=positions[k])
            p.changeDynamics(b, -1, lateralFriction=.42 if ball else .6,
                             restitution=ph['ball_restitution'] if ball else ph['stool_restitution'],
                             rollingFriction=BALL_ROLL_FRICTION if ball else .002, spinningFriction=.001,
                             linearDamping=0., angularDamping=.005 if ball else .05,
                             collisionMargin=.00005, contactProcessingThreshold=.001)
            if ball:
                p.changeDynamics(b, -1, ccdSweptSphereRadius=BALL_RADIUS * .75)
            bodies[k] = b
        # Settle the stools before the visible clip starts. The ball spawns
        # airborne (it is mid-throw), so it is restored to its launch point
        # once the stools have come to rest.
        for _ in range(400):
            p.stepSimulation()
        for k, b in bodies.items():
            if b is not None:
                p.resetBaseVelocity(b, [0, 0, 0], [0, 0, 0])
                if k == 'tennis_ball':
                    p.resetBasePositionAndOrientation(b, positions[k], [0, 0, 0, 1])
        origin, aim = None, None
        from scene_geometry import throw_line
        origin, aim = throw_line(ph)
        v = launch_velocity(ph)
        d = [aim[0] - origin[0], aim[1] - origin[1]]
        norm = math.hypot(*d)
        spin = [30. * -d[1] / norm, 30. * d[0] / norm, 0.]  # topspin along the flight direction
        p.resetBaseVelocity(bodies['tennis_ball'], list(v), list(spin))
        first = None
        first_pair = {}
        room_first = None
        max_pen = 0.
        max_tilt = {k: 0. for k in KEYS[1:] if bodies[k] is not None}
        frames = []
        # Mid-run schedule: gravity edits land inside the frame loop below and
        # are applied to the live world, then the run continues from that state.
        timed_events = []
        timed_by_frame = {}
        for event in ph.get('timed_edits', []):
            if not isinstance(event, dict) or set(event) != {'frame', 'params'}:
                raise ValueError(f'Invalid timed edit entry: {event!r}')
            frame = event['frame']
            params = event['params']
            if type(frame) is not int or not 2 <= frame <= count:
                raise ValueError(f'Timed edit frame {frame!r} is outside 2..{count}')
            if set(params) != {'gravity_z'}:
                raise ValueError(f'Timed edit sets {sorted(params)}, which this scene cannot change mid-run')
            value = params['gravity_z']
            if not math.isfinite(value) or not -60. <= value <= -1.:
                raise ValueError('Timed gravity_z must be finite and point down')
            timed_by_frame.setdefault(frame, []).append(dict(params))
        static_ids = {floor, *fixture_bodies}
        for step in range((count - 1) * stride + 1):
            t = step / SIM_HZ
            ball_contacts = p.getContactPoints(bodyA=bodies['tennis_ball'])
            if ball_contacts:
                if room_first is None and any(c[2] in static_ids for c in ball_contacts):
                    room_first = t
                if first is None:
                    first = t
            for k, b in bodies.items():
                if b is None:
                    continue
                for c in p.getContactPoints(bodyA=b):
                    max_pen = max(max_pen, -c[8])
                if k != 'tennis_ball':
                    contacts = p.getContactPoints(bodies['tennis_ball'], b)
                    if contacts and k not in first_pair:
                        first_pair[k] = t
                        first = t if first is None else first
                    q = p.getBasePositionAndOrientation(b)[1]
                    mat = p.getMatrixFromQuaternion(q)
                    max_tilt[k] = max(max_tilt[k], math.degrees(math.acos(max(-1., min(1., mat[8])))))
            if step % stride == 0:
                frame_index = len(frames) + 1
                for params in timed_by_frame.get(frame_index, []):
                    # Applied to the live world: gravity changes for every body
                    # still in flight and the run carries on from the state it
                    # had reached.
                    p.setGravity(0, 0, float(params['gravity_z']))
                    timed_events.append(dict(frame=frame_index, time_sec=t, params=dict(params),
                                             from_values={'gravity_z': ph['gravity_z']},
                                             applied_in_simulation=True, effective_from_frame=frame_index))
                f = dict(frame_index=len(frames) + 1, time_sec=t)
                for k, b in bodies.items():
                    if b is None:
                        f[k] = dict(present=False)
                        continue
                    pos, q = p.getBasePositionAndOrientation(b)
                    vel, w = p.getBaseVelocity(b)
                    mat = p.getMatrixFromQuaternion(q)
                    f[k] = dict(present=True, location=list(pos), quaternion_xyzw=list(q),
                                linear_velocity=list(vel), angular_velocity=list(w),
                                matrix_world=[list(mat[j * 3:j * 3 + 3]) + [pos[j]] for j in range(3)] + [[0, 0, 0, 1]])
                frames.append(f)
            if step < (count - 1) * stride:
                p.stepSimulation()
        travel = {k: math.dist(frames[0][k]['location'], frames[-1][k]['location']) for k in KEYS if bodies[k] is not None}
        inside = all(BOUNDS_MIN[0] - .05 <= f['tennis_ball']['location'][0] <= BOUNDS_MAX[0] + .05 and
                     BOUNDS_MIN[1] - .05 <= f['tennis_ball']['location'][1] <= BOUNDS_MAX[1] + .05 and
                     f['tennis_ball']['location'][2] > -.05 for f in frames)
        quality = dict(valid=max_pen < .004 and inside and spawn_overlap_m <= 1e-3,
                       first_ball_fixture_contact_sec=room_first, first_impact_sec=first,
                       ball_stool_contact_sec=first_pair, max_penetration_m=max_pen,
                       max_stool_tilt_deg=max_tilt, displacement_m=travel,
                       ball_stayed_in_room=inside,
                       spawn_overlap_m=spawn_overlap_m, spawn_offenders=spawn_offenders,
                       transmission_observed=any(travel.get(k, 0) > .02 for k in KEYS[1:] if bodies[k] is not None),
                       final_ball_speed_m_s=math.sqrt(sum(vv * vv for vv in frames[-1]['tennis_ball']['linear_velocity'])),
                       timed_events=timed_events)
        return dict(schema_version=2, scene=SCENE_NAME, scenario=s, simulation_signature=simulation_signature(s),
                    playback_fps=fps, sample_fps=fps, slow_motion=1, frame_start=1, frame_end=count,
                    physical_duration_sec=4., playback_duration_sec=4.,
                    solver=dict(engine='PyBullet DIRECT', hz=SIM_HZ, iterations=120, gravity=[0, 0, ph['gravity_z']],
                                floor_friction=.55, ball_friction=.42, stool_friction=.6,
                                fixture_boxes=len(room['boxes']),
                                note='Tennis ball vs static bathroom fixtures and wooden stools; no deformation'),
                    colliders=dict(asset=room['asset'], floor_z=room['floor_z'],
                                   boxes=[b['name'] for b in room['boxes']]),
                    objects={k: dict(present=bodies[k] is not None,
                                     mass_kg=ph['ball_mass'] if k == 'tennis_ball' else ph['stool_mass']) for k in KEYS},
                    quality=quality, timed_events=timed_events, frames=frames)
    finally:
        p.disconnect(client)


def main():
    p = add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    d = simulate(load_scenario(a))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(d, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    (a.out.parent / 'simulation_metrics.json').write_text(json.dumps(d['quality'], indent=2), encoding='utf-8')
    print(json.dumps(d['quality'], indent=2), flush=True)


if __name__ == '__main__':
    main()
