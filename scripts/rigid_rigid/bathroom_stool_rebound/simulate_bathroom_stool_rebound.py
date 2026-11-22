"""Full 3D PyBullet rigid bodies: one thrown stool, then contacts and friction."""
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
from scene_geometry import (KEYS, GRAVITY, SIM_HZ, LAUNCH_DIR, SPIN_DIR,
                            FRICTION, RESTITUTION,
                            STATIC_RESTITUTION, static_boxes, bathtub_mesh_path, stool_boxes,
                            alcove_mesh_path, fixed_constants, SINK_BODIES)
from validate_bathroom_stool_rebound import simulation_signature


def _unit(vec):
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec]


def simulate(s):
    import pybullet as p
    validate(s)
    r = s['render']; ph = s['physics']; sample_fps = r['fps'] * r['slow_motion']
    count = round(sample_fps * r['duration_sec']); stride = SIM_HZ // sample_fps
    stool_friction = float(ph.get('stool_friction', FRICTION))
    if not math.isfinite(stool_friction) or stool_friction < 0:
        raise ValueError('stool_friction must be finite and nonnegative')
    timed_by_frame = {}
    for entry in ph.get('timed_edits') or []:
        frame = entry.get('frame'); params = entry.get('params')
        if not isinstance(frame, int) or not 2 <= frame <= count or not isinstance(params, dict) or set(params) != {'stool_friction'}:
            raise ValueError(f'Unsupported or invalid timed event: {entry!r}')
        value = float(params['stool_friction'])
        if not math.isfinite(value) or value < 0:
            raise ValueError('Timed friction must be finite and nonnegative')
        timed_by_frame.setdefault(frame, []).append(value)
    client = p.connect(p.DIRECT)
    try:
        p.setGravity(0, 0, GRAVITY)
        p.setTimeStep(1 / SIM_HZ)
        p.setPhysicsEngineParameter(numSolverIterations=120, restitutionVelocityThreshold=.001,
                                    deterministicOverlappingPairs=1, contactBreakingThreshold=.0005)
        # Static bathroom: floor, walls, washbasin cabinet + basin + mirror.
        statics = {}
        for name, center, half in static_boxes():
            shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=half)
            body = p.createMultiBody(0, shape, basePosition=center)
            p.changeDynamics(body, -1, lateralFriction=.75, restitution=STATIC_RESTITUTION)
            statics[name] = body
        # The tub alcove is the same story: the room's north-east corner is
        # chamfered at 45 degrees in the GLB and carries a marble shelf, while
        # the wall boxes are flat planes. Unmodelled, a stool that entered the
        # corner sank up to 1.2 m into the visible wall. It is a room fixture,
        # so it exists whether or not the bathtub does.
        alcove_mesh = alcove_mesh_path()
        if not alcove_mesh.is_file():
            raise FileNotFoundError(f'Missing alcove collider mesh: {alcove_mesh}')
        alcove_shape = p.createCollisionShape(p.GEOM_MESH, fileName=str(alcove_mesh),
                                              flags=p.GEOM_FORCE_CONCAVE_TRIMESH)
        alcove = p.createMultiBody(0, alcove_shape, basePosition=[0., 0., 0.])
        p.changeDynamics(alcove, -1, lateralFriction=.75, restitution=STATIC_RESTITUTION)
        statics['alcove'] = alcove
        # The bathtub is the marble's own triangles. Its visible outline is a
        # tilted, outward-flaring shell, so every box or hull surrogate left an
        # invisible wall the stool could hit metres from the marble. The
        # concave flag matters: without it Bullet fills the basin in.
        if ph['bathtub_active'][0]:
            tub_mesh = bathtub_mesh_path()
            if not tub_mesh.is_file():
                raise FileNotFoundError(f'Missing bathtub collider mesh: {tub_mesh}')
            hull_shape = p.createCollisionShape(p.GEOM_MESH, fileName=str(tub_mesh),
                                                flags=p.GEOM_FORCE_CONCAVE_TRIMESH)
            tub = p.createMultiBody(0, hull_shape, basePosition=[0., 0., 0.])
            p.changeDynamics(tub, -1, lateralFriction=.75, restitution=STATIC_RESTITUTION)
            statics['bathtub'] = tub
        # The stool: a compound of seat + three splayed legs, with the body
        # origin at the GLB seat centre and feet STOOL_COM_Z below it.
        parts = stool_boxes()
        halves = [b[0] for b in parts]
        offsets = [b[1] for b in parts]
        orientations = [b[2] for b in parts]
        stool_shape = p.createCollisionShapeArray([p.GEOM_BOX] * len(halves),
                                                  halfExtents=halves,
                                                  collisionFramePositions=offsets,
                                                  collisionFrameOrientations=orientations)
        spawn = list(ph['stool_spawn'])
        stool = p.createMultiBody(ph['stool_mass'], stool_shape, basePosition=spawn)
        p.changeDynamics(stool, -1, lateralFriction=stool_friction, restitution=RESTITUTION,
                         spinningFriction=.002, rollingFriction=.0005, linearDamping=0., angularDamping=0.,
                         collisionMargin=.0005, contactProcessingThreshold=.002)
        speed = float(ph['launch_speed']); spin = float(ph['launch_spin'])
        direction = _unit(LAUNCH_DIR)
        p.resetBaseVelocity(stool, [speed * c for c in direction],
                            [spin * c for c in _unit(SPIN_DIR)])
        def classify(name):
            return 'sink' if name in SINK_BODIES else name

        dynamic = [stool]
        # (other body id, label) pairs the stool is tracked against.
        pairs = [(body, classify(name)) for name, body in statics.items()]
        frames = []; events = []; contact_state = {pair: False for pair in pairs}
        max_penetration = 0.; escaped = False
        first_impact = None; first_sink_impact = None; first_tub_impact = None
        timed_events = []; rebound_toward_tub = None
        tub_center = [6.9915, 1.032, .72]
        pending = {}

        def velocities():
            return [list(p.getBaseVelocity(b)[0]) for b in dynamic]

        pre_v = velocities()
        # Seed the contact map with the post-settle state so resting on the
        # slab at frame 1 is not reported as an impact.
        for other_body, other in pairs:
            contact_state[(other_body, other)] = bool(p.getContactPoints(stool, other_body))
        for step in range((count - 1) * stride + 1):
            t = step / SIM_HZ
            if step % stride == 0:
                # A timed edit fires at its frame boundary, before the motion
                # that follows it: the new friction is written into every live
                # stool and the run carries on from the state it had reached.
                frame_number = step // stride + 1
                for value in timed_by_frame.get(frame_number, []):
                    previous = stool_friction; stool_friction = float(value)
                    for b in dynamic:
                        p.changeDynamics(b, -1, lateralFriction=stool_friction)
                    timed_events.append(dict(frame=frame_number, time_sec=t, parameter='stool_friction',
                                             from_value=previous, to_value=stool_friction,
                                             applied_in_simulation=True))
            v = velocities()
            for other_body, other in pairs:
                contacts = p.getContactPoints(stool, other_body)
                contact = bool(contacts)
                if contact and not contact_state[(other_body, other)]:
                    events.append(dict(time_sec=t, object=other, pre_velocity=pre_v))
                    pending[(other_body, other)] = len(events) - 1
                    if first_impact is None: first_impact = t
                    if other == 'sink' and first_sink_impact is None: first_sink_impact = t
                    if other == 'bathtub' and first_tub_impact is None: first_tub_impact = t
                elif not contact and contact_state[(other_body, other)] and (other_body, other) in pending:
                    ev = events[pending.pop((other_body, other))]
                    ev['contact_end_sec'] = t
                    pos, _ = p.getBasePositionAndOrientation(stool)
                    if other == 'sink' and rebound_toward_tub is None:
                        toward = [tub_center[i] - pos[i] for i in range(2)]
                        norm = math.hypot(*toward) or 1.
                        along = sum(v[0][i] * toward[i] / norm for i in range(2))
                        rebound_toward_tub = bool(along > 0.)
                        events[-1].update(rebound_toward_tub=rebound_toward_tub)
                contact_state[(other_body, other)] = contact
                for c in contacts:
                    max_penetration = max(max_penetration, -c[8])
            pos, _ = p.getBasePositionAndOrientation(stool)
            if not (-8.6 < pos[0] < 11.4 and -5.5 < pos[1] < 4.8 and pos[2] < 7.0):
                escaped = True
            if step % stride == 0:
                frame = dict(frame_index=len(frames) + 1, time_sec=t)
                for key, body in zip(KEYS, (stool,)):
                    pos_b, q = p.getBasePositionAndOrientation(body)
                    linear, angular = p.getBaseVelocity(body)
                    mat = p.getMatrixFromQuaternion(q)
                    matrix = [list(mat[j * 3:j * 3 + 3]) + [pos_b[j]] for j in range(3)] + [[0, 0, 0, 1]]
                    frame[key] = dict(present=True, location=list(pos_b), quaternion_xyzw=list(q),
                                      linear_velocity=list(linear), angular_velocity=list(angular), matrix_world=matrix)
                frames.append(frame)
            pre_v = v
            if step < (count - 1) * stride:
                p.stepSimulation()
        final_speed = max(math.hypot(*p.getBaseVelocity(b)[0][:3]) for b in dynamic)
        quality = dict(valid=(max_penetration < .015 and first_sink_impact is not None and not escaped),
                       events=events, first_impact_sec=first_impact,
                       first_sink_impact_sec=first_sink_impact, first_tub_impact_sec=first_tub_impact,
                       rebound_toward_tub=rebound_toward_tub,
                       escaped_room=escaped, settled_by_end=final_speed < .05,
                       final_speed_m_s=final_speed, max_penetration_m=max_penetration,
                       effective_stool_friction=stool_friction,
                       requested_launch_speed=speed, requested_launch_spin=spin,
                       timed_events=timed_events)
        return dict(schema_version=2, scene=SCENE_NAME, scenario=deepcopy(s), simulation_signature=simulation_signature(s),
                    solver=dict(name='PyBullet', api_version=p.getAPIVersion(), constants=fixed_constants()),
                    playback_fps=r['fps'], sample_fps=sample_fps, slow_motion=r['slow_motion'], frame_end=count,
                    physical_duration_sec=r['duration_sec'], playback_duration_sec=r['duration_sec'] * r['slow_motion'],
                    sampled_end_time_sec=(count - 1) / sample_fps,
                    objects={'stool': dict(present=True, mass_kg=ph['stool_mass'],
                                           collision_shape='seat slab + three tilted leg boxes + foot pads (GLB-matched)',
                                           origin='centre of the GLB seat slab')},
                    quality=quality, timed_events=timed_events, frames=frames)
    finally:
        p.disconnect(client)


def main():
    parser = add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); d = simulate(load_scenario(args))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(d, indent=2, allow_nan=False), encoding='utf-8')
    (args.out.parent / 'simulation_metrics.json').write_text(json.dumps(d['quality'], indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(d['quality'], indent=2))
    if not d['quality']['valid']: raise RuntimeError('Physical validation failed')


if __name__ == '__main__':
    main()
