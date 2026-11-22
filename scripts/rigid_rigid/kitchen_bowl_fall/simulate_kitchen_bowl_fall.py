"""Full 3D PyBullet rigid bodies: a bowl falls off a cupboard onto the tableware below."""
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
from scene_geometry import (KEYS, SIM_HZ, SOLVER_ITERATIONS,
                            FALLING_BOWL_RADIUS, FALLING_BOWL_HEIGHT, TABLEWARE_PARTS,
                            TABLEWARE_BOWL_RADIUS, TABLEWARE_BOWL_HEIGHT,
                            CABINET_X_MIN, CABINET_X_MAX, CABINET_Z_BOTTOM, CABINET_Z_TOP,
                            CABINET_FRONT_Y, CABINET_BACK_Y, PANEL_T, BOARD_TOP_Z, SHELF_Z,
                            SHELF_T, DOOR_T, DOOR_OPEN_DEG, DOOR_HINGE_X,
                            FALLING_BOWL_LINEAR_DAMPING,
                            FALLING_BOWL_ANGULAR_DAMPING, FALLING_BOWL_ROLLING_FRICTION,
                            TABLEWARE_ROLLING_FRICTION, TABLEWARE_SPINNING_FRICTION,
                            TABLEWARE_ANGULAR_DAMPING, ROOM_X_MIN, ROOM_X_MAX, ROOM_Y_MIN,
                            ROOM_Y_MAX, layout, present, fixed_constants)
from room_colliders import load_colliders
from validate_kitchen_bowl_fall import simulation_signature

# The bowl is a cylinder (closed convex hull of the bowl profile) with its axis
# vertical; it tips forward off the cupboard ledge about +x. Nothing is allowed
# above the kitchen ceiling.
CEILING_MARGIN = 2.75


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
        # The kitchen: floor, island counter and the walls, from the verified
        # export of modern_kitchen.glb.
        room = load_colliders()
        statics = {}
        for box in room['boxes']:
            shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=box['half_extents'])
            body = p.createMultiBody(0, shape, basePosition=box['center'])
            counter_like = box['name'].startswith('counter')
            floor_like = box['name'].startswith('floor')
            p.changeDynamics(body, -1, lateralFriction=.55,
                             restitution=ph['counter_restitution'] if counter_like
                             else (ph['counter_restitution'] if floor_like else ph['cupboard_restitution']))
            statics[box['name']] = body
        # The open wall cupboard the bowl falls out of. The GLB ships only a door
        # panel in that volume (measured: x -0.494..0.197, z 1.828..2.678, 56 mm
        # thick, nothing behind it), so the carcass is built here exactly where
        # that panel was: the bottom board the bowl stands on, two sides, a top,
        # a back, one fixed shelf, and the door leaf swung open on its right
        # hinge. Every board the renderer draws is a board the solver collides.
        def add_static(name, x0, x1, y0, y1, z0, z1, restitution, friction, orientation=None):
            half = [(x1 - x0) / 2, (y1 - y0) / 2, (z1 - z0) / 2]
            centre = [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2]
            shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=half)
            body = p.createMultiBody(0, shape, basePosition=centre,
                                    baseOrientation=orientation or [0, 0, 0, 1])
            p.changeDynamics(body, -1, lateralFriction=friction, restitution=restitution)
            statics[name] = body
            return body

        cup_restit, cup_fric = ph['cupboard_restitution'], .50
        add_static('cupboard_bottom', CABINET_X_MIN, CABINET_X_MAX,
                   CABINET_FRONT_Y, CABINET_BACK_Y, CABINET_Z_BOTTOM, BOARD_TOP_Z, cup_restit, cup_fric)
        add_static('cupboard_top', CABINET_X_MIN, CABINET_X_MAX,
                   CABINET_FRONT_Y, CABINET_BACK_Y, CABINET_Z_TOP - PANEL_T, CABINET_Z_TOP,
                   cup_restit, cup_fric)
        add_static('cupboard_side_l', CABINET_X_MIN, CABINET_X_MIN + PANEL_T,
                   CABINET_FRONT_Y, CABINET_BACK_Y, BOARD_TOP_Z, CABINET_Z_TOP - PANEL_T,
                   cup_restit, cup_fric)
        add_static('cupboard_side_r', CABINET_X_MAX - PANEL_T, CABINET_X_MAX,
                   CABINET_FRONT_Y, CABINET_BACK_Y, BOARD_TOP_Z, CABINET_Z_TOP - PANEL_T,
                   cup_restit, cup_fric)
        add_static('cupboard_back', CABINET_X_MIN, CABINET_X_MAX,
                   CABINET_BACK_Y - PANEL_T, CABINET_BACK_Y, BOARD_TOP_Z, CABINET_Z_TOP - PANEL_T,
                   cup_restit, cup_fric)
        add_static('cupboard_shelf', CABINET_X_MIN + PANEL_T, CABINET_X_MAX - PANEL_T,
                   CABINET_FRONT_Y + .004, CABINET_BACK_Y - PANEL_T,
                   SHELF_Z - SHELF_T, SHELF_Z, cup_restit, cup_fric)
        # The door leaf, swung open about the vertical hinge on the right jamb.
        angle = math.radians(DOOR_OPEN_DEG)
        ca, sa = math.cos(angle), math.sin(angle)
        leaf_half_x = (CABINET_X_MAX - CABINET_X_MIN) / 2 - .002
        rel_x = (CABINET_X_MIN + CABINET_X_MAX) / 2 - DOOR_HINGE_X
        rel_y = (CABINET_FRONT_Y - DOOR_T / 2) - CABINET_FRONT_Y
        door_centre = [DOOR_HINGE_X + rel_x * ca - rel_y * sa,
                       CABINET_FRONT_Y + rel_x * sa + rel_y * ca,
                       (CABINET_Z_BOTTOM + CABINET_Z_TOP) / 2]
        door_shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=[
            leaf_half_x, DOOR_T / 2, (CABINET_Z_TOP - CABINET_Z_BOTTOM) / 2 - .002])
        door_body = p.createMultiBody(0, door_shape, basePosition=door_centre,
                                      baseOrientation=[0, 0, math.sin(angle / 2), math.cos(angle / 2)])
        p.changeDynamics(door_body, -1, lateralFriction=cup_fric, restitution=cup_restit)
        statics['cupboard_door'] = door_body
        # The falling bowl: a cylinder of its true diameter and depth, standing on
        # the bottom board at the angle it was left at.
        # A DELETE of the falling bowl (falling_bowl_active [0]) leaves it out of the solve.
        bowl = None
        if present(ph, 'falling_bowl'):
            bowl_shape = p.createCollisionShape(p.GEOM_CYLINDER, radius=FALLING_BOWL_RADIUS,
                                                height=FALLING_BOWL_HEIGHT)
            spawn = layout(ph)['falling_bowl']
            tilt = math.radians(float(ph.get('falling_bowl_tilt_deg', 0.)))
            bowl = p.createMultiBody(ph['falling_bowl_mass'], bowl_shape, basePosition=spawn,
                                     baseOrientation=[math.sin(tilt / 2), 0, 0, math.cos(tilt / 2)])
            p.changeDynamics(bowl, -1, lateralFriction=ph['falling_bowl_friction'],
                             restitution=ph['falling_bowl_restitution'],
                             spinningFriction=.002, rollingFriction=FALLING_BOWL_ROLLING_FRICTION,
                             linearDamping=FALLING_BOWL_LINEAR_DAMPING, angularDamping=FALLING_BOWL_ANGULAR_DAMPING,
                             collisionMargin=.0004, contactProcessingThreshold=.002, ccdSweptSphereRadius=.05)
        # The tableware: one bowl standing on the hob, a cylinder of its own
        # diameter and depth. It gets swept-sphere CCD as well: when the bowl ten
        # times heavier lands on it, it is thrown at a speed where a 1/1440 s step
        # is longer than the gap to the floor, and without CCD it tunnels straight
        # through the kitchen instead of landing on it.
        tableware_bodies = {}
        if present(ph, TABLEWARE_PARTS[0]):
            for key in TABLEWARE_PARTS:
                # A box, not a cylinder, and only for this body. Cylinder on
                # cylinder goes through GJK/EPA, and when the ten-times-heavier
                # bowl pinches this one against the quartz the solver resolves
                # the penetration with a correction so large that the bowl is
                # thrown clean out of the kitchen -- soft ERP and swept-sphere
                # CCD both fail to save it. A box of the bowl's own footprint
                # generates a stable manifold and the same collision reads the
                # same on screen; the bowl is a flat dish, so it was never going
                # to roll on its side anyway.
                shape = p.createCollisionShape(p.GEOM_BOX,
                                               halfExtents=[TABLEWARE_BOWL_RADIUS,
                                                            TABLEWARE_BOWL_RADIUS,
                                                            TABLEWARE_BOWL_HEIGHT / 2])
                body = p.createMultiBody(ph['tableware_mass'], shape,
                                         basePosition=layout(ph)[key])
                p.changeDynamics(body, -1, lateralFriction=ph['tableware_friction'],
                                 restitution=ph['tableware_restitution'],
                                 spinningFriction=TABLEWARE_SPINNING_FRICTION,
                                 rollingFriction=TABLEWARE_ROLLING_FRICTION,
                                 linearDamping=0., angularDamping=TABLEWARE_ANGULAR_DAMPING,
                                 collisionMargin=.0004, contactProcessingThreshold=.002,
                                 ccdSweptSphereRadius=TABLEWARE_BOWL_RADIUS * .8)
                tableware_bodies[key] = body
        # The bowl was left standing askew on the cupboard board with its rim
        # already past the front lip, so it tips out by itself: a slow forward
        # roll and no launch velocity. Gravity does the rest.
        if bowl is not None:
            p.resetBaseVelocity(bowl, [float(ph.get('falling_bowl_push_x', 0.)),
                                       -float(ph['falling_bowl_push']), 0.],
                                [float(ph['falling_bowl_spin']), 0., 0.])

        dynamic = ([bowl] if bowl is not None else []) + list(tableware_bodies.values())
        bowl_targets = [(body, name) for name, body in statics.items()]
        bowl_targets += [(body, 'tableware') for body in tableware_bodies.values()]
        if bowl is None:
            bowl_targets = []
        room_targets = [(body, name) for name, body in statics.items()]
        frames, events = [], []
        contact_state = {pair: False for pair in bowl_targets}
        tableware_contact_state = {(body, name): False
                                   for body in tableware_bodies.values() for name, _ in room_targets}
        max_penetration = 0.
        escaped = False
        first_impact = first_tableware_impact = first_counter_impact = first_floor_impact = None
        tableware_tilt_max = 0.
        timed_events = []
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
            # The falling bowl against everything else.
            for other_body, other in bowl_targets:
                contacts = p.getContactPoints(bowl, other_body)
                contact = bool(contacts)
                if contact and not contact_state[(other_body, other)]:
                    events.append(dict(time_sec=t, object=other, actor='falling_bowl',
                                       pre_velocity=pre_v[0]))
                    if first_impact is None:
                        first_impact = t
                    if other == 'tableware' and first_tableware_impact is None:
                        first_tableware_impact = t
                    elif other.startswith('counter') and first_counter_impact is None:
                        first_counter_impact = t
                    elif other.startswith('floor') and first_floor_impact is None:
                        first_floor_impact = t
                contact_state[(other_body, other)] = contact
                for c in contacts:
                    max_penetration = max(max_penetration, -c[8])
            # The bowls against the room. This is sampled once per output frame:
            # it feeds the penetration and "stayed in the kitchen" audits, not the
            # impact timing, and four extra bodies per solver step is wasted work.
            if step % stride == 0:
                for body in tableware_bodies.values():
                    for other_body, other in room_targets:
                        contacts = p.getContactPoints(body, other_body)
                        contact = bool(contacts)
                        if contact and not tableware_contact_state[(body, other)]:
                            events.append(dict(time_sec=t, object=other, actor='tableware'))
                        tableware_contact_state[(body, other)] = contact
                        for c in contacts:
                            max_penetration = max(max_penetration, -c[8])
            if bowl is not None:
                pos, q = p.getBasePositionAndOrientation(bowl)
                if not (ROOM_X_MIN < pos[0] < ROOM_X_MAX and ROOM_Y_MIN < pos[1] < ROOM_Y_MAX
                        and -0.6 < pos[2] < CEILING_MARGIN):
                    escaped = True
            for body in tableware_bodies.values():
                bpos, bq = p.getBasePositionAndOrientation(body)
                if not (ROOM_X_MIN < bpos[0] < ROOM_X_MAX and ROOM_Y_MIN < bpos[1] < ROOM_Y_MAX):
                    escaped = True
                tableware_tilt_max = max(tableware_tilt_max, _tilt_deg(p.getMatrixFromQuaternion(bq)[8]))
            if step % stride == 0:
                frame = dict(frame_index=len(frames) + 1, time_sec=t)
                for key in KEYS:
                    body = bowl if key == 'falling_bowl' else tableware_bodies.get(key)
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
        bowl_disp = (math.dist(frames[0]['falling_bowl']['location'], last['falling_bowl']['location'])
                     if bowl is not None else 0.)
        # Report the most displaced and most tilted tableware body (the scene
        # has one bowl on the hob).
        live_parts = [key for key in TABLEWARE_PARTS if last[key]['present']]
        tableware_disp = max((math.dist(frames[0][key]['location'], last[key]['location'])
                              for key in live_parts), default=0.)
        tableware_tilt_end = max((_tilt_deg(last[key]['matrix_world'][2][2])
                                  for key in live_parts), default=0.)
        parts_end = {key: dict(location=last[key]['location'],
                               tilt_deg=_tilt_deg(last[key]['matrix_world'][2][2]),
                               displacement_m=math.dist(frames[0][key]['location'], last[key]['location']))
                     for key in live_parts}
        quality = dict(
            valid=(max_penetration < .012 and not escaped),
            first_impact_sec=first_impact, first_tableware_impact_sec=first_tableware_impact,
            first_counter_impact_sec=first_counter_impact, first_floor_impact_sec=first_floor_impact,
            transmission_observed=(tableware_disp > .05 or tableware_tilt_max > 15.) if live_parts else False,
            tableware_tilt_max_deg=tableware_tilt_max, tableware_tilt_end_deg=tableware_tilt_end,
            tableware_displacement_m=tableware_disp, bowl_displacement_m=bowl_disp,
            tableware_parts_end=parts_end,
            escaped_room=escaped, settled_by_end=final_speed < .06, final_speed_m_s=final_speed,
            max_penetration_m=max_penetration, effective_gravity_z=gravity_z, timed_events=timed_events,
            events=events)
        objects = {'falling_bowl': dict(present=bowl is not None, mass_kg=ph['falling_bowl_mass'],
                                        collision_shape='cylinder (bowl hull)',
                                        origin='centre of the falling bowl')}
        for key in TABLEWARE_PARTS:
            objects[key] = dict(present=key in tableware_bodies, mass_kg=ph['tableware_mass'],
                                collision_shape='cylinder (single bowl)',
                                origin='centre of that bowl')
        return dict(schema_version=2, scene=SCENE_NAME, scenario=deepcopy(s),
                    simulation_signature=simulation_signature(s),
                    solver=dict(name='PyBullet', api_version=p.getAPIVersion(), constants=fixed_constants()),
                    playback_fps=r['fps'], sample_fps=sample_fps, slow_motion=r['slow_motion'],
                    frame_start=1, frame_end=count, physical_duration_sec=r['duration_sec'],
                    playback_duration_sec=r['duration_sec'] * r['slow_motion'],
                    sampled_end_time_sec=(count - 1) / sample_fps,
                    objects=objects,
                    quality=quality, timed_events=timed_events, frames=frames)
    finally:
        p.disconnect(client)


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
