"""Build the renderable water surface (plus spray, mist and foam) from a Genesis run of the toy boat glide.

Render-side only: it reads the particle cache and never changes the simulation.  The anisotropic surface
and the secondary particles are the elastic_duck implementation, with thresholds scaled to a 5 mm spacing
and a gentle 0.5 m/s glide (the toy-car stage does the same for its splash).  Particles near the pool's
inner wall are mirrored across it before meshing, so the surface meets the rings level instead of
rounding off into a visible gap.
"""

import argparse
import importlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[4]
POOL = json.loads((ROOT / "assets/sketchfab/inflatable_swimming_pool/prepared/pool_profile.json").read_text())
WALL_PROFILE = np.array(POOL["inner_wall_profile_z_r_m"], dtype=np.float64)
FLOOR_Z = POOL["inner_floor_z_m"]
# The simulated wall is a cylinder at the rings' radius where the authored water plane meets them.
WALL_RADIUS = float(np.interp(POOL["authored_water_z_m"], WALL_PROFILE[:, 0], WALL_PROFILE[:, 1]))
REACH = WALL_RADIUS + 0.05
DOMAIN_LOWER = np.array((-REACH, -REACH, FLOOR_Z))
DOMAIN_UPPER = np.array((REACH, REACH, FLOOR_Z + 0.40))
FPS = 24


# The splash stage of elastic_fluid_duck is reused as it is; a change there changes this scene's surfaces too.
DUCK_PHYSICS = ROOT / "scripts/elastic_fluid/elastic_fluid_duck/physics"


def load_duck_detail():
    source = DUCK_PHYSICS / "splash_elastic_fluid_duck.py"
    sys.path.insert(0, str(source.parent))
    return importlib.import_module("splash_elastic_fluid_duck"), source


def configure_for_toy_boat(detail):
    """Scale the duck's secondary-particle thresholds to a toy boat gliding at under 0.5 m/s."""
    detail.WORKERS = 32
    detail.SPRAY_BAND = (0.008, 0.030)
    detail.SPRAY_PIECE = 0.040
    detail.TORN_CLUSTER = 3
    detail.DROPS_PER_TORN = 20
    detail.SPRAY_SPEED = (0.30, 1.00)
    detail.SPRAY_MIN_HEIGHT = 0.006
    detail.SHED_NEIGHBOURS = 14
    detail.SHED_PER_FRAME = 2.0
    detail.SHED_MIN_SPEED = 0.40
    detail.SHED_HEIGHT = 0.010
    detail.DROP_RADIUS = (0.0010, 0.0030)
    detail.DROP_ALONG = 0.8
    detail.DROP_ACROSS = 0.25
    detail.DROP_SPREAD = 0.12
    detail.DROP_STRETCH = 0.10
    detail.CULL_MARGIN = 0.005
    detail.MAX_AGE = 1.0
    detail.DECK_Z = FLOOR_Z
    detail.SEED = 20261023
    detail.MIST_PER_TORN = 6
    detail.MIST_PER_FRAME = 1.5
    detail.MIST_RADIUS = (0.0004, 0.0010)
    detail.MIST_SPREAD = 0.30
    detail.MIST_SLOWDOWN = (0.30, 0.85)
    detail.MIST_TERMINAL = 1.0
    detail.MIST_LIFE = (0.20, 0.50)
    # A clean pool behind a toy hull: a little white water at the bow and in the wake, gone in about a second.
    detail.FOAM_CHURN = (0.12, 0.35)
    detail.FOAM_RATE = 0.06
    detail.FOAM_PATCH = (3, 7)
    detail.FOAM_PATCH_SPREAD = 0.004
    detail.FOAM_FROM_LANDING = 0.12
    detail.FOAM_LANDING_PATCH = (2, 4)
    detail.FOAM_RADIUS = (0.0007, 0.0018)
    detail.FOAM_LIFE = (0.40, 1.10)
    detail.FOAM_DUCK_GAP = 0.005
    # The wake is millimetres high: the duck's 25 smoothing passes flatten it to half; keep it.
    detail.SMOOTHING_ITERATIONS = 10


def quaternion_matrix(wxyz):
    w, x, y, z = np.asarray(wxyz, dtype=np.float64)
    s = 2.0 / (w * w + x * x + y * y + z * z)
    return np.array([
        [1 - s * (y * y + z * z), s * (x * y - z * w), s * (x * z + y * w)],
        [s * (x * y + z * w), 1 - s * (x * x + z * z), s * (y * z - x * w)],
        [s * (x * z - y * w), s * (y * z + x * w), 1 - s * (x * x + y * y)],
    ])


def hull_points(collider, position, quaternion, dx):
    """Points over the collider's surface (its vertices plus face samples) in world space."""
    import trimesh

    samples, _ = trimesh.sample.sample_surface_even(collider, max(200, int(collider.area / (dx * dx))), seed=0)
    local = np.concatenate((collider.vertices, samples))
    return local @ quaternion_matrix(quaternion).T + np.asarray(position)


def mirror_across_wall(x, v, h):
    """Reflect the particles within h of the wall to the far side of it (radially, at their height)."""
    r = np.hypot(x[:, 0], x[:, 1])
    near = r > WALL_RADIUS - h
    scale = (2 * WALL_RADIUS - r[near]) / np.maximum(r[near], 1e-9)
    mirrored = x[near].copy()
    mirrored[:, :2] *= scale[:, None]
    return np.concatenate((x, mirrored)), np.concatenate((v, v[near])), int(near.sum())


def clip_to_wall(vertices, triangles):
    """Drop the triangles of the mirrored skin outside the wall (they are inside the vinyl anyway)."""
    r = np.hypot(vertices[:, 0], vertices[:, 1])
    outside = r > WALL_RADIUS + 0.004
    keep = ~outside[triangles].all(axis=1)
    return triangles[keep]


def write_surface(out, frame, x, v, detail, h, dx, still_level):
    xm, vm, mirrored = mirror_across_wall(x, v, h)
    mesh, stats = detail.surface(xm, vm, h, dx, still_level)
    mesh = dict(mesh)
    mesh["triangles"] = clip_to_wall(mesh["vertices"], mesh["triangles"])
    np.savez_compressed(out / f"water_{frame:04d}.npz", **mesh)
    return {"surface": stats, "mirrored": mirrored}


def mesh_only(run, out, frames, collider, detail, dx, still_level, part):
    """Mesh frames independently, without the spray history.  Hidden particles are this frame's torn-off
    airborne ones (the history only adds those torn while still touching the water, which a glide
    this gentle almost never tears), so frames can be split over processes."""
    h = 2 * dx
    log = {"mode": "mesh only, per-frame hidden set", "frames": {}}
    for frame in frames:
        tick = time.monotonic()
        with np.load(run / "particles" / f"frame_{frame:04d}.npz") as state:
            x = state["water_pos"].astype(np.float64)
            v = state["water_vel"].astype(np.float64)
            boat = (hull_points(collider, state["boat_pos"], state["boat_quat_wxyz"], dx)
                    if bool(state.get("boat_active", True)) else np.zeros((0, 3)))
        tree = cKDTree(x)
        counts = tree.query_ball_point(x, 0.999 * h, return_length=True, workers=detail.WORKERS) - 1
        heights = detail.Heights(np.concatenate((x[counts >= 9], boat)), DOMAIN_LOWER, DOMAIN_UPPER, still_level,
                                 size=0.02)
        hidden = detail.torn_particles(tree, x, counts, h) & (x[:, 2] - heights(x) > 0)
        record = {"hidden": int(hidden.sum())}
        record.update(write_surface(out, frame, x[~hidden], v[~hidden], detail, h, dx, still_level))
        record["seconds"] = time.monotonic() - tick
        log["frames"][str(frame)] = record
        atomic_json(out / f"report_mesh_{part}.json", log)
        print("SURFACE", part, frame, json.dumps(record), flush=True)


def atomic_json(path, value):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    tmp.replace(path)


def parse_frames(text, maximum):
    frames = sorted({f for part in text.split(",")
                     for f in range(int(part.split("-")[0]), int(part.split("-")[-1]) + 1)})
    if not frames or frames[0] < 1 or frames[-1] > maximum:
        raise ValueError(f"frames must be inside 1-{maximum}: {text}")
    return frames


def main():
    import trimesh

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--frames", default="1-96", help="frames whose spray, mist and foam are written")
    parser.add_argument("--surfaces", help="frames this process meshes (default: --frames); see run_splash_parallel.sh")
    parser.add_argument("--no-secondaries", action="store_true",
                        help="mesh only: skip the frame-by-frame spray/mist/foam history (another process writes it)")
    parser.add_argument("--skip-existing", action="store_true", help="do not re-mesh frames whose water file exists")
    parser.add_argument("--part", default="0")
    parser.add_argument("--out-name", default="surface")
    args = parser.parse_args()

    run = args.run.resolve()
    report = json.loads((run / "simulation_report.json").read_text())
    frame_count = int(report["numerics"]["frames"])
    dx = float(report["numerics"]["dx_m"])
    still_level = float(report["water_level_m"])
    collider = trimesh.load(ROOT / report["physics"]["boat_collider"], force="mesh").convex_hull
    wanted = parse_frames(args.frames, frame_count)
    surfaces = set(parse_frames(args.surfaces, frame_count)) if args.surfaces else set(wanted)
    detail, source = load_duck_detail()
    configure_for_toy_boat(detail)
    detail.numba.set_num_threads(min(32, detail.numba.config.NUMBA_NUM_THREADS))

    out = run / args.out_name
    out.mkdir(exist_ok=True)
    if args.skip_existing:
        surfaces = {f for f in surfaces if not (out / f"water_{f:04d}.npz").exists()}
    if args.no_secondaries:
        mesh_only(run, out, sorted(surfaces), collider, detail, dx, still_level, args.part)
        return
    log = {"settings": {"source": "unchanged Genesis DFSPH particle cache", "implementation": str(source),
                        "dx_m": dx, "still_level_m": still_level, "wall_mirroring": "radial, within one kernel h"},
           "frames": {}, "physics_changed": False}
    drops = detail.Flying(dx, detail.DROP_RADIUS)
    mist = detail.Flying(dx, detail.MIST_RADIUS, terminal=detail.MIST_TERMINAL, life=detail.MIST_LIFE)
    foam = detail.Foam()
    converted = None
    previous = None
    h = 2 * dx
    for frame in range(1, max(wanted + list(surfaces)) + 1):
        tick = time.monotonic()
        with np.load(run / "particles" / f"frame_{frame:04d}.npz") as state:
            x = state["water_pos"].astype(np.float64)
            v = state["water_vel"].astype(np.float64)
            boat = (hull_points(collider, state["boat_pos"], state["boat_quat_wxyz"], dx)
                    if bool(state.get("boat_active", True)) else np.zeros((0, 3)))
        if previous is not None and np.median(np.linalg.norm(x - previous, axis=1)) >= dx:
            raise RuntimeError(f"particle ordering changed at frame {frame}")
        previous = x
        converted = np.zeros(len(x), bool) if converted is None else converted
        tree = cKDTree(x)
        counts = tree.query_ball_point(x, 0.999 * h, return_length=True, workers=detail.WORKERS) - 1
        height_points = np.concatenate((x[counts >= 9], boat))
        heights = detail.Heights(height_points, DOMAIN_LOWER, DOMAIN_UPPER, still_level, size=0.02)
        torn = detail.torn_particles(tree, x, counts, h)
        surface_now = detail.Surface(x, v, counts, still_level, dx)
        rng = np.random.default_rng(detail.SEED + frame)
        if frame > 1:
            drops.advance(1 / FPS)
            mist.advance(1 / FPS)
            foam.advance(1 / FPS, surface_now, boat, DOMAIN_LOWER, DOMAIN_UPPER)
        landed = drops.cull(heights, DOMAIN_LOWER, DOMAIN_UPPER)
        mist.cull(heights, DOMAIN_LOWER, DOMAIN_UPPER)
        if len(landed):
            selected = landed[rng.uniform(size=len(landed)) < detail.FOAM_FROM_LANDING]
            foam.spawn(selected, surface_now, rng, detail.FOAM_LANDING_PATCH)
        clearance = x[:, 2] - heights(x)
        new = torn & ~converted & (clearance > 0)
        converted = (converted | new) & torn
        speed = np.linalg.norm(v, axis=1)
        energy = (np.clip((speed[new] - detail.SPRAY_SPEED[0]) / (detail.SPRAY_SPEED[1] - detail.SPRAY_SPEED[0]), 0, 1)
                  * (clearance[new] > detail.SPRAY_MIN_HEIGHT))
        drops.emit(x[new], v[new], np.round(detail.DROPS_PER_TORN * energy).astype(int), rng,
                   detail.DROP_ALONG, detail.DROP_ACROSS, detail.DROP_SPREAD, detail.DROP_STRETCH)
        mist.emit(x[new], v[new], np.round(detail.MIST_PER_TORN * energy).astype(int), rng,
                  0.5, 1.0, detail.MIST_SPREAD, 0.2, detail.MIST_SLOWDOWN)
        shedding = (~converted & (counts >= 1) & (counts <= detail.SHED_NEIGHBOURS)
                    & (speed > detail.SHED_MIN_SPEED) & (x[:, 2] > still_level + detail.SHED_HEIGHT))
        rate = np.clip(speed[shedding] / 1.5, 0, 1.5)
        drops.emit(x[shedding], v[shedding], rng.poisson(detail.SHED_PER_FRAME * rate), rng,
                   detail.DROP_ALONG, detail.DROP_ACROSS, detail.DROP_SPREAD, detail.DROP_STRETCH)
        mist.emit(x[shedding], v[shedding], rng.poisson(detail.MIST_PER_FRAME * rate), rng,
                  0.5, 1.0, detail.MIST_SPREAD, 0.2, detail.MIST_SLOWDOWN)

        top, _ = surface_now.sample(surface_now.points[:, :2])
        layer = surface_now.points[:, 2] > top - dx / 2 - 0.004
        points, flow = surface_now.points[layer], surface_now.velocity[layer]
        if len(points) >= 9:
            _, neighbour = cKDTree(points).query(points, k=9, workers=detail.WORKERS)
            churn = np.linalg.norm(flow[neighbour[:, 1:]] - flow[:, None, :], axis=2).mean(axis=1)
            churn = rng.poisson(detail.FOAM_RATE * np.clip(
                (churn - detail.FOAM_CHURN[0]) / (detail.FOAM_CHURN[1] - detail.FOAM_CHURN[0]), 0, 1))
            foam.spawn(np.repeat(points, churn, axis=0), surface_now, rng, detail.FOAM_PATCH)
        foam.advance(0.0, surface_now, boat, DOMAIN_LOWER, DOMAIN_UPPER)

        record = {"torn_new": int(new.sum()), "hidden": int(converted.sum()), "shedding": int(shedding.sum()),
                  "drops": len(drops.radius), "mist": len(mist.radius), "foam": len(foam.radius)}
        if frame in wanted:
            drops.save(out / f"spray_{frame:04d}.npz")
            mist.save(out / f"mist_{frame:04d}.npz")
            foam.save(out / f"foam_{frame:04d}.npz")
        if frame in surfaces:
            record.update(write_surface(out, frame, x[~converted], v[~converted], detail, h, dx, still_level))
        record["seconds"] = time.monotonic() - tick
        log["frames"][str(frame)] = record
        atomic_json(out / f"report_{args.part}.json", log)
        print("SURFACE", frame, json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
