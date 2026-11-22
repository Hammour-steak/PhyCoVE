"""Search throw parameters whose impact chain is:
glass_screen_south -> wall_south -> floor -> toilet_bowl (east face),
with the ball still AIRBORNE when it reaches the toilet and the wall hit
high enough to read as a real rebound (not a floor skim).

Batch runner with early abort and sharding. Run with a Python that has pybullet.
"""
import sys
from pathlib import Path

SCENE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SCENE), str(SCENE / "physics"), str(SCENE.parents[1])]

import json
import math
from bathroom_colliders import load_colliders
from scene_geometry import BALL_RADIUS, FLOOR_Z

# Chain quality gates (metres above the world origin; floor top is FLOOR_Z).
GLASS_MIN_Z = 0.90
WALL_MIN_Z = 0.55
TOILET_MIN_Z = 0.25
FLIGHT_MIN_Z = 0.30     # peak height in the floor->toilet airborne window
FLIGHT_MIN_SEC = 0.15   # that window must last long enough to read as flight


def run(ox, oy, aim_y, speed, elev_deg, ball_res, fixture_res, hz=1440, room=None, name_of=None, max_t=3.8):
    import pybullet as p
    client = p.connect(p.DIRECT)
    try:
        p.setGravity(0, 0, -9.81)
        p.setTimeStep(1 / hz)
        p.setPhysicsEngineParameter(numSolverIterations=120, restitutionVelocityThreshold=.015,
                                    contactBreakingThreshold=.0002)
        floor = p.createMultiBody(0, p.createCollisionShape(p.GEOM_BOX, halfExtents=[9.78, 4.975, .05]),
                                  basePosition=[1.53, -.255, FLOOR_Z - .05])
        p.changeDynamics(floor, -1, lateralFriction=.55, restitution=fixture_res)
        name_of[floor] = 'floor'
        for box in room['boxes']:
            b = p.createMultiBody(0, p.createCollisionShape(p.GEOM_BOX, halfExtents=box['half_extents']),
                                  basePosition=box['center'])
            p.changeDynamics(b, -1, lateralFriction=.5, restitution=fixture_res)
            name_of[b] = box['name']
        sphere = p.createCollisionShape(p.GEOM_SPHERE, radius=BALL_RADIUS)
        ball = p.createMultiBody(.058, sphere, basePosition=[ox, oy, .95])
        p.changeDynamics(ball, -1, lateralFriction=.42, restitution=ball_res, rollingFriction=.0014,
                         spinningFriction=.001, linearDamping=0., angularDamping=.005,
                         collisionMargin=.00005, contactProcessingThreshold=.001,
                         ccdSweptSphereRadius=BALL_RADIUS * .75)
        for _ in range(120):
            p.stepSimulation()
        p.resetBaseVelocity(ball, [0, 0, 0], [0, 0, 0])
        p.resetBasePositionAndOrientation(ball, [ox, oy, .95], [0, 0, 0, 1])
        dx, dy = 4.55 - ox, aim_y - oy
        norm = math.hypot(dx, dy)
        el = math.radians(elev_deg)
        v = [speed * math.cos(el) * dx / norm, speed * math.cos(el) * dy / norm, speed * math.sin(el)]
        p.resetBaseVelocity(ball, v, [0, 0, 0])
        events = []
        samples = []
        last_name, last_t = None, -1
        for step in range(int(max_t * hz)):
            for c in p.getContactPoints(ball):
                nm = name_of.get(c[2], 'other')
                if nm == last_name and (step / hz - last_t) < 0.04:
                    last_t = step / hz
                    continue
                pos, _ = p.getBasePositionAndOrientation(ball)
                vel, _ = p.getBaseVelocity(ball)
                events.append((round(step / hz, 3), nm, [round(q, 3) for q in pos],
                               [round(q, 2) for q in vel], [round(q, 2) for q in c[7]]))
                last_name, last_t = nm, step / hz
            if step % 8 == 0:
                pos, _ = p.getBasePositionAndOrientation(ball)
                samples.append((round(step / hz, 3), [round(q, 3) for q in pos]))
            p.stepSimulation()
        pos, _ = p.getBasePositionAndOrientation(ball)
        return events, samples, [round(q, 2) for q in pos]
    finally:
        p.disconnect(client)


def flight_ok(events, samples):
    """Chain + height gates: glass high, wall rebound off the ground, then a
    real airborne arc from the last floor bounce into the toilet's east face."""
    if not events:
        return False, 'no contacts'
    order, firsts = [], {}
    for e in events:
        if not order or order[-1] != e[1]:
            order.append(e[1])
        firsts.setdefault(e[1], e)
    if order[0] != 'glass_screen_south':
        return False, 'first=%s' % order[0]
    if 'wall_south' not in firsts or 'toilet_bowl' not in firsts:
        return False, 'order=%s' % '->'.join(order)
    g, w, t = firsts['glass_screen_south'], firsts['wall_south'], firsts['toilet_bowl']
    if order.index('wall_south') > len(order) and False:
        return False, 'wall order'
    if g[2][2] < GLASS_MIN_Z:
        return False, 'glass low z=%.2f' % g[2][2]
    if w[2][2] < WALL_MIN_Z:
        return False, 'wall low z=%.2f' % w[2][2]
    if 'floor' in order[:order.index('wall_south')]:
        return False, 'floor before wall'
    # floor contact between wall and toilet
    idx_w = order.index('wall_south')
    after = [e for e in events if e[1] == 'floor' and e[0] >= w[0] and e[0] <= t[0]]
    if not after:
        return False, 'no floor between wall and toilet'
    if t[2][2] < TOILET_MIN_Z:
        return False, 'toilet low z=%.2f' % t[2][2]
    if abs(t[4][0]) < abs(t[4][1]):
        return False, 'toilet y-face %s' % (t[4],)
    # airborne window from the last floor touch into the toilet
    t_floor = after[-1][0]
    window = [s for s in samples if t_floor <= s[0] <= t[0]]
    if t[0] - t_floor < FLIGHT_MIN_SEC:
        return False, 'flight too short %.2fs' % (t[0] - t_floor)
    if not window or max(s[1][2] for s in window) < FLIGHT_MIN_Z:
        return False, 'flight too low %.2f' % (max(s[1][2] for s in window) if window else -1)
    return True, '->'.join(order)


def grid():
    for oy in (-1.2, -1.6):
        for aim_y in (-4.0, -4.3, -4.6):
            for speed in (15., 17., 19.):
                for elev in (8., 12., 16.):
                    for ball_res in (.60, .70, .78):
                        for fixture_res in (.45, .55, .63, .70):
                            yield (oy, aim_y, speed, elev, ball_res, fixture_res)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--shard', type=int, default=0)
    ap.add_argument('--nshards', type=int, default=1)
    ap.add_argument('--out', type=str, default='', help='output JSON (default: renders/bathroom_tennis_throw/search/flight_<shard>.json)')
    a = ap.parse_args()
    room = load_colliders()
    name_of = {}
    hits, nears = [], []
    for i, cfg in enumerate(grid()):
        if i % a.nshards != a.shard:
            continue
        oy, aim_y, speed, elev, ball_res, fixture_res = cfg
        try:
            events, samples, final = run(-1.6, oy, aim_y, speed, elev, ball_res, fixture_res,
                                         room=room, name_of=name_of)
        except Exception as exc:
            print('ERR', cfg, exc, flush=True)
            continue
        ok, why = flight_ok(events, samples)
        rec = dict(cfg=cfg, why=why, final=final,
                   events=[[e[0], e[1], e[2], e[3], e[4]] for e in events[:12]])
        if ok:
            hits.append(rec)
            print('HIT', cfg, why, 'final', final, flush=True)
        elif 'toilet' in why or 'flight' in why:
            nears.append(rec)
            print('NEAR', cfg, why, 'final', final, flush=True)
    out = Path(a.out) if a.out else SCENE.parents[2] / 'renders' / 'bathroom_tennis_throw' / 'search' / ('flight_%d.json' % a.shard)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(hits=hits, nears=nears), ensure_ascii=False), encoding='utf-8')
    print('shard %d: %d hits %d nears -> %s' % (a.shard, len(hits), len(nears), out), flush=True)


if __name__ == '__main__':
    main()
