"""Full 3D PyBullet rigid bodies: an unstable kettle topples into a pen cup and throws the pen."""
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
from scene_config import (SCENE_NAME, add_scenario_arguments, load_scenario, validate,
                          MASS_KEYS, TIMED_PRESENCE_KEYS)
from scene_geometry import (DESK_Z, DESK_CENTRE_XY, DESK_HALF_XY, SIM_HZ, GRAVITY,
                            KETTLE_COM_Z, KETTLE_TILT_DEG, KETTLE_KICK_OMEGA_X, KETTLE_KICK_VY,
                            KETTLE_START_XY,
                            PEN_HOLDER_XY, HOLDER_RADIUS, HOLDER_WALL, HOLDER_HEIGHT, HOLDER_COM_Z, HOLDER_FLOOR,
                            PEN_RADIUS, PEN_HALF_LENGTH, PEN_LEAN_DEG, PEN_BOTTOM_INSET,
                            PEN_DRAPE_DIR,
                            KETTLE_FRICTION, HOLDER_FRICTION, PEN_FRICTION, DESK_FRICTION,
                            KEYBOARD_BOX, PHONE_BOX, RACK_BOXES,
                            RESTITUTION, kettle_hull_vertices, holder_compound_specs, fixed_constants)
from validate_office_desk_kettle_tip import simulation_signature


def _tilt_deg(q):
    """Tilt of a body's local +Z away from world +Z, in degrees."""
    from pybullet import getMatrixFromQuaternion
    m = getMatrixFromQuaternion(q)
    return math.degrees(math.acos(max(-1.0, min(1.0, m[8]))))


def simulate(s):
    import pybullet as p
    validate(s)
    r = s['render']; ph = s['physics']; sample_fps = r['fps'] * r['slow_motion']
    count = round(sample_fps * r['duration_sec']); stride = SIM_HZ // sample_fps
    pen_present = bool(ph['pen_present'][0])
    kettle_present = bool(ph.get('kettle_present', [1])[0])
    timed_by_frame = {}
    for entry in ph.get('timed_edits') or []:
        frame = entry.get('frame'); params = entry.get('params')
        if not isinstance(frame, int) or not 2 <= frame <= count or not isinstance(params, dict) or not params:
            raise ValueError(f'Unsupported or invalid timed event: {entry!r}')
        for key, value in params.items():
            if key in TIMED_PRESENCE_KEYS:
                if value != [0]:
                    raise ValueError(f'Timed {key} must be [0]')
                continue
            if key not in MASS_KEYS:
                raise ValueError(f'Unsupported timed parameter: {key!r}')
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'Timed {key} must be finite and positive')
        timed_by_frame.setdefault(frame, {}).update(params)
    client = p.connect(p.DIRECT)
    try:
        p.setGravity(0, 0, GRAVITY)
        p.setTimeStep(1 / SIM_HZ)
        p.setPhysicsEngineParameter(numSolverIterations=120, restitutionVelocityThreshold=.001,
                                    deterministicOverlappingPairs=1, contactBreakingThreshold=.0005)
        # Static desktop: one box under the GLB desktop slab's footprint, plus
        # stand-ins for the keyboard and telephone props baked into the desk
        # GLB, and for the right-half drawer/rack furniture (so rebound paths
        # from mass and contact edits meet solid stand-ins instead of clipping
        # through), so every near-miss in the sweep is a real contact.
        static_bodies = []
        floor = p.createCollisionShape(p.GEOM_BOX, halfExtents=[DESK_HALF_XY[0], DESK_HALF_XY[1], .015])
        desk = p.createMultiBody(0, floor, basePosition=[DESK_CENTRE_XY[0], DESK_CENTRE_XY[1], DESK_Z - .015])
        p.changeDynamics(desk, -1, lateralFriction=DESK_FRICTION, restitution=0.)
        static_bodies.append(desk)
        for prop in (KEYBOARD_BOX, PHONE_BOX, *RACK_BOXES):
            shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=list(prop['half']))
            body = p.createMultiBody(0, shape, basePosition=list(prop['centre']))
            p.changeDynamics(body, -1, lateralFriction=DESK_FRICTION, restitution=0.)
            static_bodies.append(body)
        # Kettle: convex hull of the shared lathe profile, origin at its COM.
        hull = p.createCollisionShape(p.GEOM_MESH, vertices=kettle_hull_vertices())
        # DELETE kettle never builds the bottle; the cup and the pen then
        # settle and stand exactly as they do before the topple.
        kettle = (p.createMultiBody(ph['kettle_mass'], hull,
                                    basePosition=[KETTLE_START_XY[0], KETTLE_START_XY[1], DESK_Z + KETTLE_COM_Z])
                  if kettle_present else None)
        # Pen cup: compound of a floor disc plus a ring of wall boxes, built in
        # the body's COM frame (children positioned relative to the COM).
        specs = holder_compound_specs()
        seg_half, _, _ = specs[0][0]
        compound = p.createCollisionShapeArray(
            shapeTypes=[p.GEOM_CYLINDER] + [p.GEOM_BOX] * len(specs),
            halfExtents=[[.0, .0, .0]] + [list(specs[0][0])] * len(specs),
            radii=[HOLDER_RADIUS - .004] + [0.] * len(specs),
            lengths=[HOLDER_FLOOR] + [0.] * len(specs),
            collisionFramePositions=[[0., 0., -HOLDER_COM_Z + HOLDER_FLOOR / 2.]] +
                                    [[pos[0], pos[1], pos[2] - HOLDER_COM_Z] for _, pos, _ in specs],
            collisionFrameOrientations=[[0., 0., 0., 1.]] + [
                [0., 0., math.sin((yaw + math.pi / 2.) / 2.), math.cos((yaw + math.pi / 2.) / 2.)]
                for _, _, yaw in specs])
        holder = p.createMultiBody(ph['pen_holder_mass'], compound,
                                   basePosition=[PEN_HOLDER_XY[0], PEN_HOLDER_XY[1], DESK_Z + HOLDER_COM_Z])
        # Pen: draped across the short cup like pens really sit in one --
        # bottom end on the inner floor, shaft resting ON the rim, top hanging
        # outside.  The drape AZIMUTH is not cosmetic any more: with a pure
        # gravity topple the bottle never sweeps through the pen (its body
        # tops out at z ~ 0.95 while the pen's protruding end sits at 0.99 and
        # 9 cm off the bottle's axis), so the pen has to be levered out by the
        # CUP's own fall instead.  That only happens if the protruding end
        # hangs on the side the cup rotates towards: there the rim comes down
        # and the pen's far end strikes the desktop first and gets flicked
        # clear.  Draped the other way (towards the bottle) the rim lifts and
        # the pen simply rides the cup down and finishes lying inside the
        # toppled bore, invisible.  PEN_DRAPE_DIR is the horizontal unit
        # vector the pen's TOP leans towards.
        pen_shape = p.createCollisionShape(p.GEOM_CYLINDER, radius=PEN_RADIUS, height=2 * PEN_HALF_LENGTH)
        pen = None
        if pen_present:
            px, py = PEN_HOLDER_XY[0], PEN_HOLDER_XY[1]
            lean = math.radians(PEN_LEAN_DEG)
            ux, uy = PEN_DRAPE_DIR
            bottom = [px - ux * PEN_BOTTOM_INSET, py - uy * PEN_BOTTOM_INSET,
                      DESK_Z + HOLDER_FLOOR + PEN_RADIUS]
            axis = (ux * math.sin(lean), uy * math.sin(lean), math.cos(lean))
            pen_com = [bottom[0] + PEN_HALF_LENGTH * axis[0],
                       bottom[1] + PEN_HALF_LENGTH * axis[1],
                       bottom[2] + PEN_HALF_LENGTH * axis[2] + .001]
            # Rotating the pen's +Z about (-uy, ux, 0) by `lean` sends its top
            # towards (ux, uy); for a (0, -1) drape this equals an Euler-X lean.
            pen = p.createMultiBody(
                ph['pen_mass'], pen_shape, basePosition=pen_com,
                baseOrientation=p.getQuaternionFromAxisAngle([-uy, ux, 0.], lean))
        for b, fr in ((kettle, KETTLE_FRICTION), (holder, HOLDER_FRICTION), (pen, PEN_FRICTION)):
            if b is None: continue
            p.changeDynamics(b, -1, lateralFriction=fr, restitution=math.sqrt(RESTITUTION),
                             spinningFriction=.001, rollingFriction=.0001, linearDamping=0., angularDamping=0.,
                             collisionMargin=.0001, contactProcessingThreshold=.001)
        if pen is not None:
            p.changeDynamics(pen, -1, ccdSweptSphereRadius=PEN_RADIUS)
        # Settle the pen inside the cup before the clip. This pre-roll is not
        # part of the video; the kettle stands still through it and receives
        # its launch pose right afterwards, at frame 1. 480 steps (0.33 s):
        # at 240 the draped pen was still creeping ~1 cm over the first three
        # frames (0.10 m/s at frame 1), which read as the pen twitching before
        # anything touched it.
        for _ in range(480): p.stepSimulation()
        # Launch pose: lean past the tipping angle so gravity finishes the
        # topple, and drop the lowest hull vertex exactly onto the desktop.
        # The topple heading is the horizontal direction from the kettle to
        # the cup (any way across the desk): the lean rotates about the
        # horizontal axis a = d x z_normal... a = (-dy, dx, 0), for which
        # a x z = d, so a positive rotation about a moves the kettle's top
        # towards the cup. The kick's angular velocity uses the same axis,
        # keeping pose and nudge consistent by construction.
        tilt = math.radians(KETTLE_TILT_DEG)
        dx = PEN_HOLDER_XY[0] - KETTLE_START_XY[0]
        dy = PEN_HOLDER_XY[1] - KETTLE_START_XY[1]
        dl = math.hypot(dx, dy)
        d = (dx / dl, dy / dl)
        axis = (-d[1], d[0], 0.)
        tilt_q = p.getQuaternionFromAxisAngle(axis, tilt)
        verts = kettle_hull_vertices()

        def rotated_by(q):
            # getMatrixFromQuaternion is row-major (m[i*3+k] == R[i][k]);
            # indexing m[k*3+i] here would silently apply the transposed
            # rotation, which once made every spawn lean away from the cup.
            m = p.getMatrixFromQuaternion(q)
            return [[sum(m[i * 3 + k] * v[k] for k in range(3)) for i in range(3)] for v in verts]

        rotated = rotated_by(tilt_q)
        # Direction check must use the kettle's TOP, not the hull's max-y
        # vertex: with the top leaning away from the cup the bottom rim's
        # far vertex still has positive y, which would wrongly keep the
        # pose. The axial apex (max body z) always sits on the lean side.
        top_i = max(range(len(verts)), key=lambda i: verts[i][2])
        if sum(rotated[top_i][k] * d[k] for k in range(2)) < 0:
            tilt_q = p.getQuaternionFromAxisAngle(axis, -tilt)
            rotated = rotated_by(tilt_q)
        low = min(v[2] for v in rotated)
        # Spawn with the lowest hull vertex exactly ON the desktop (zero
        # clearance): the resting contact forms on the very first step, so
        # the settle below closes it before the kick arrives.
        if kettle is not None:
            p.resetBasePositionAndOrientation(
                kettle, [KETTLE_START_XY[0], KETTLE_START_XY[1], DESK_Z - low], tilt_q)
        # Let the tilted base edge settle into a resting contact BEFORE the
        # kick. Kicking in the same step as the pose reset makes the edge slam
        # into the desk as a fresh collision, and that pivot impact keeps only
        # I_com/I_edge ~ 23% of the angular velocity (measured: omega 12 ->
        # 2.4 within 40 ms, the kettle then just rocks back upright). With
        # the resting contact already closed, the solver carries the same
        # rotation as a constrained pivot with no impact loss.
        for _ in range(6): p.stepSimulation()
        # The nudge must push the top towards the cup too, and it must be
        # PIVOT-CONSISTENT: a pure omega about the centre of mass gives the
        # resting base edge ~0.9 m/s straight into the desk, and the very
        # first contact solve then acts as a pivot impact that keeps only
        # I_com/I_edge ~ 23% of the spin (measured: omega 12 -> 2.4). The
        # motion that actually hinged on the base edge is omega about that
        # edge, i.e. the same omega plus a com velocity of omega x (com-edge),
        # which the resting contact carries without any impact loss.
        # KETTLE_KICK_OMEGA_X only carries the bottle over its 23 deg balance
        # angle; from there the topple is pure gravity, so the replay shows
        # the bottle going over in place -- no lunge, no launch. Everything
        # after that (the strike energy, the cup going flat, the pen being
        # thrown) is gravity plus the mass ratio, not a scripted push.
        low_i = min(range(len(verts)), key=lambda i: rotated[i][2])
        ex, ey, ez = rotated[low_i]              # edge position rel the com
        omega = KETTLE_KICK_OMEGA_X
        vx = omega * (axis[1] * (-ez))           # a x (com - edge), a = (ax, ay, 0)
        vy_ = omega * (-axis[0] * (-ez))
        vz = omega * (axis[0] * (-ey) - axis[1] * (-ex))
        vy = KETTLE_KICK_VY
        if kettle is not None:
            p.resetBaseVelocity(kettle, [vx + vy * d[0], vy_ + vy * d[1], vz],
                                [omega * axis[0], omega * axis[1], 0.])

        masses = dict(kettle=ph['kettle_mass'], pen_holder=ph['pen_holder_mass'],
                      pen=ph['pen_mass'] if pen_present else 0.)
        bodies = dict(kettle=kettle, pen_holder=holder, pen=pen)
        # Presence at frame 1, which is what the cache's object table reports.
        # A timed DELETE sets a slot to None partway through, so the live dict
        # cannot be asked this question once the clip has started.
        built = {key: body is not None for key, body in bodies.items()}
        frames = []; timed_events = []
        first_impact = None; pen_release = None
        holder_max_speed = 0.; pen_max_speed = 0.; max_penetration = 0.; last_motion = 0.
        max_penetration_pair = None
        holder_tilt3_frame = None; previous_kc = False
        holder_max_tilt = 0.
        left_desk = set()
        kettle_settled = False
        props_settled = False

        def velocities():
            return {k: (list(p.getBaseVelocity(b)[0]) if b is not None else [0., 0., 0.])
                    for k, b in bodies.items()}

        for step in range((count - 1) * stride + 1):
            t = step / SIM_HZ
            if step % stride == 0:
                # A timed edit fires at its frame boundary, before the motion
                # that follows it: the new masses are written into the live
                # bodies and the run carries on from the state it had reached.
                # A timed DELETE is the same idea taken literally -- the body
                # is removed from the world here, so it stops colliding from
                # this frame on and the frame loop sees the same None a
                # whole-clip delete leaves behind.
                frame_number = step // stride + 1
                for key, value in timed_by_frame.get(frame_number, {}).items():
                    if key in TIMED_PRESENCE_KEYS:
                        if holder is not None:
                            p.removeBody(holder)
                            holder = None
                            bodies['pen_holder'] = None
                            # The cup was the only thing holding the pen up;
                            # once it is gone the pen is out of it by
                            # definition, whatever its own motion does next.
                            if pen_release is None and first_impact is not None:
                                pen_release = t
                            timed_events.append(dict(frame=frame_number, time_sec=t, parameter=key,
                                                     from_value=[1], to_value=[0],
                                                     applied_in_simulation=True,
                                                     effective_from_frame=frame_number))
                        continue
                    body = bodies['pen'] if key == 'pen_mass' else bodies[key.replace('_mass', '')]
                    if body is None: continue
                    previous = masses[key.replace('_mass', '')]
                    p.changeDynamics(body, -1, mass=float(value))
                    masses[key.replace('_mass', '')] = float(value)
                    timed_events.append(dict(frame=frame_number, time_sec=t, parameter=key,
                                             from_value=previous, to_value=float(value),
                                             applied_in_simulation=True))
            if holder is None:
                # Kept from the last frame the cup existed, so the metrics still
                # describe the topple that actually happened before it vanished.
                contacts = []
            else:
                holder_pos, holder_q = p.getBasePositionAndOrientation(holder)
                holder_tilt = _tilt_deg(holder_q)
                holder_max_tilt = max(holder_max_tilt, holder_tilt)
                contacts = p.getContactPoints(kettle, holder) if kettle is not None else []
            kc = bool(contacts)
            if kc and not previous_kc and first_impact is None:
                first_impact = t
            previous_kc = kc
            # Settling friction for the kettle, armed 0.6 s after its first
            # touch of the holder. By then the whole story is done -- the lid
            # strike, the holder topple and (in the baseline the pen flies at
            # ~0.38 s) -- and the kettle's leftover motion is just a convex
            # hull rolling like a barrel: with rollingFriction ~ 0 that never
            # decays, and a heavy kettle crawls at a constant ~0.2 m/s until
            # it drops off the desk edge. A real jug has a handle and spout
            # that arrest the roll; the extra damping stands in for them. It
            # only damps future velocities, so whatever resting equilibrium
            # the kettle has already found is left untouched.
            if first_impact is not None and not kettle_settled and t >= first_impact + .6:
                p.changeDynamics(kettle, -1, rollingFriction=.01, angularDamping=.8)
                kettle_settled = True
            # The struck cup and the flung pen get their own arrest, armed as
            # soon as the cup has finished toppling (tilt >= 80 deg, and at
            # least 0.2 s past the strike) or 0.6 s after it -- whichever
            # comes first. Their leftover motion is a perfect cylinder
            # rolling on its rim (the cup) or on its shell (the pen): with
            # rollingFriction ~ 0 neither ever decays, and the pair was
            # measured creeping ~0.3 m across the desk until the end of the
            # replay. Arresting at topple completion rather than on a fixed
            # clock also caps how far the struck cup slides -- enough to
            # keep its lying body clear of the phone prop north of it. Real
            # props have irregular rims, contents and pen clips; the damping
            # stands in for them and only touches future velocities, so the
            # topple itself and the pen's flight are already over when this
            # fires.
            if (first_impact is not None and not props_settled
                    and ((holder_tilt >= 80. and t >= first_impact + .2) or t >= first_impact + .6)):
                if holder is not None:
                    p.changeDynamics(holder, -1, rollingFriction=.01,
                                     angularDamping=.8, linearDamping=.8)
                if pen is not None:
                    p.changeDynamics(pen, -1, rollingFriction=.01,
                                     angularDamping=.8, linearDamping=.8)
                props_settled = True
            if holder_tilt3_frame is None and first_impact is not None and holder_tilt >= 3.0:
                holder_tilt3_frame = step // stride + 1
            if pen is not None:
                pen_pos, pen_q = p.getBasePositionAndOrientation(pen)
                pen_speed = math.dist(p.getBaseVelocity(pen)[0], [0., 0., 0.])
                pen_max_speed = max(pen_max_speed, pen_speed)
                if holder is None:
                    # The cup is gone, so "is the pen still inside it" has no
                    # answer; pen_release was stamped at the removal instead.
                    dist = radial = None
                else:
                    dist = math.hypot(pen_pos[0] - holder_pos[0], pen_pos[1] - holder_pos[1])
                    # Release is measured in the CUP's OWN frame, not in world
                    # x/y: once the cup lies on its side its mouth points
                    # sideways, and a world-horizontal "distance from the cup
                    # axis" test then reads a pen that has clearly rolled out
                    # onto the desk as still captive. The cup-local test says
                    # "out" when the pen's centre is past the inner wall radius
                    # or above the rim plane, which is rotation invariant.
                    inv_pos, inv_orn = p.invertTransform(holder_pos, holder_q)
                    pen_local, _ = p.multiplyTransforms(inv_pos, inv_orn, pen_pos,
                                                        p.getQuaternionFromEuler([0., 0., 0.]))
                    radial = math.hypot(pen_local[0], pen_local[1])
                    if pen_release is None and first_impact is not None and (
                            radial > HOLDER_RADIUS - HOLDER_WALL
                            or pen_local[2] > -HOLDER_COM_Z + HOLDER_HEIGHT
                            or dist > HOLDER_RADIUS + PEN_RADIUS + .01):
                        pen_release = t
            holder_speed = (math.dist(p.getBaseVelocity(holder)[0], [0., 0., 0.])
                            if holder is not None else 0.)
            holder_max_speed = max(holder_max_speed, holder_speed)
            for key, b in bodies.items():
                if b is None: continue
                pos, q = p.getBasePositionAndOrientation(b)
                inside = (abs(pos[0] - DESK_CENTRE_XY[0]) < DESK_HALF_XY[0] - .01 and
                          abs(pos[1] - DESK_CENTRE_XY[1]) < DESK_HALF_XY[1] - .01)
                if not inside and pos[2] < DESK_Z + .12:
                    left_desk.add(key)
                if key != 'kettle' or pos[2] < DESK_Z + KETTLE_COM_Z + .05:
                    for c in p.getContactPoints(bodyA=b):
                        if -c[8] > max_penetration:
                            max_penetration = -c[8]
                            other = next((n for n, bb in bodies.items() if bb == c[2]), 'static prop')
                            max_penetration_pair = f'{key}~{other}@t={t:.3f}'
            vel = velocities()
            if max(math.dist(v, [0., 0., 0.]) for v in vel.values()) > .005: last_motion = t
            if step % stride == 0:
                frame = dict(frame_index=len(frames) + 1, time_sec=t)
                for key, b in bodies.items():
                    if b is None:
                        frame[key] = dict(present=False)
                        continue
                    pos, q = p.getBasePositionAndOrientation(b)
                    linear, angular = p.getBaseVelocity(b)
                    mat = p.getMatrixFromQuaternion(q)
                    matrix = [list(mat[j * 3:j * 3 + 3]) + [pos[j]] for j in range(3)] + [[0, 0, 0, 1]]
                    frame[key] = dict(present=True, location=list(pos), quaternion_xyzw=list(q),
                                      linear_velocity=list(linear), angular_velocity=list(angular),
                                      matrix_world=matrix)
                frames.append(frame)
            if step < (count - 1) * stride:
                p.stepSimulation()
        final_speed = max(math.dist(p.getBaseVelocity(b)[0], [0., 0., 0.])
                          for b in bodies.values() if b is not None)
        # A cup that was deleted mid-run has no final pose; report the tilt it
        # had reached when it vanished rather than inventing one.
        final_holder_tilt = (_tilt_deg(p.getBasePositionAndOrientation(holder)[1])
                             if holder is not None else holder_tilt)
        final_kettle_tilt = (_tilt_deg(p.getBasePositionAndOrientation(kettle)[1])
                             if kettle is not None else None)
        quality = dict(valid=max_penetration < .0025 and not left_desk,
                       transmission_observed=holder_max_speed > .05,
                       pen_thrown_observed=(pen is None and False) or (pen_max_speed > .25 and pen_release is not None),
                       first_impact_sec=first_impact, pen_release_sec=pen_release,
                       holder_first_tilt_3deg_frame=holder_tilt3_frame,
                       holder_max_tilt_deg=holder_max_tilt,
                       final_kettle_tilt_deg=final_kettle_tilt,
                       final_holder_tilt_deg=final_holder_tilt,
                       last_motion_sec=last_motion, settled_by_end=final_speed < .02, final_speed_m_s=final_speed,
                       max_penetration_m=max_penetration, max_penetration_pair=max_penetration_pair, holder_max_speed_m_s=holder_max_speed,
                       pen_max_speed_m_s=pen_max_speed, bodies_left_desk=sorted(left_desk),
                       masses_kg=masses, timed_events=timed_events)
        return dict(schema_version=2, scene=SCENE_NAME, scenario=deepcopy(s), simulation_signature=simulation_signature(s),
                    solver=dict(name='PyBullet', api_version=p.getAPIVersion(), constants=fixed_constants()),
                    playback_fps=r['fps'], sample_fps=sample_fps, slow_motion=r['slow_motion'], frame_end=count,
                    physical_duration_sec=r['duration_sec'], playback_duration_sec=r['duration_sec'] * r['slow_motion'],
                    sampled_end_time_sec=(count - 1) / sample_fps,
                    objects={k: dict(present=built[k], mass_kg=masses[k],
                                     collision_shape={'kettle': 'convex hull of shared kettle profile',
                                                      'pen_holder': 'compound: floor disc + wall ring',
                                                      'pen': 'cylinder'}[k],
                                     origin='centre of mass') for k in bodies},
                    quality=quality, timed_events=timed_events, frames=frames)
    finally: p.disconnect(client)


def main():
    parser = add_scenario_arguments(argparse.ArgumentParser(description=__doc__))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); d = simulate(load_scenario(args))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(d, indent=2, allow_nan=False), encoding='utf-8')
    (args.out.parent / 'simulation_metrics.json').write_text(json.dumps(d['quality'], indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(d['quality'], indent=2))
    if not d['quality']['valid']: raise RuntimeError('Physical validation failed')


if __name__ == '__main__': main()
