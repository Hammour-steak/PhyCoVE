"""Build duck-style anisotropic water, spray, mist and foam from a Genesis cache.

This is a render-side operation.  It does not rerun Genesis or change the
rigid/SPH state.  The anisotropic reconstruction and secondary-particle
implementation are imported from the accepted elastic_duck scene, while the
thresholds below are rescaled for this scene's 1 cm SPH spacing and 16 cm car.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
import time
import os

import numpy as np
from scipy.spatial import cKDTree


FPS = 24
DOMAIN_LOWER = np.array((-0.25, -0.44, 0.0), dtype=np.float64)
DOMAIN_UPPER = np.array((1.31, 0.44, 0.52), dtype=np.float64)
CAR_SIZE = np.array((0.160, 0.071, 0.055), dtype=np.float64)


def load_duck_detail():
    """The splash stage of elastic_fluid_duck, imported from that scene."""
    source = Path(__file__).resolve().parents[3] / "elastic_fluid" / "elastic_fluid_duck" / "physics" / "splash_elastic_fluid_duck.py"
    sys.path.insert(0, str(source.parent))
    module = importlib.import_module("splash_elastic_fluid_duck")
    return module, source


def configure_for_toy_car(detail,workers=16):
    """Scale duck secondary-particle thresholds to the smaller car/pool event."""
    detail.WORKERS = workers
    detail.SPRAY_BAND = (0.012, 0.040)
    detail.SPRAY_PIECE = 0.055
    detail.TORN_CLUSTER = 3
    detail.DROPS_PER_TORN = 28
    detail.SPRAY_SPEED = (0.35, 1.40)
    detail.SPRAY_MIN_HEIGHT = 0.008
    detail.SHED_NEIGHBOURS = 14
    detail.SHED_PER_FRAME = 3.0
    detail.SHED_MIN_SPEED = 0.45
    detail.SHED_HEIGHT = 0.012
    detail.DROP_RADIUS = (0.0012, 0.0042)
    detail.DROP_ALONG = 0.8
    detail.DROP_ACROSS = 0.25
    detail.DROP_SPREAD = 0.12
    detail.DROP_STRETCH = 0.10
    detail.CULL_MARGIN = 0.006
    detail.MAX_AGE = 1.25
    detail.DECK_Z = 0.0
    detail.SEED = 20261022
    detail.MIST_PER_TORN = 12
    detail.MIST_PER_FRAME = 3.0
    detail.MIST_RADIUS = (0.0004, 0.0011)
    detail.MIST_SPREAD = 0.30
    detail.MIST_SLOWDOWN = (0.30, 0.85)
    detail.MIST_TERMINAL = 1.0
    detail.MIST_LIFE = (0.20, 0.55)
    detail.FOAM_CHURN = (0.15, 0.45)
    detail.FOAM_RATE = 0.08
    detail.FOAM_PATCH = (3, 8)
    detail.FOAM_PATCH_SPREAD = 0.004
    detail.FOAM_FROM_LANDING = 0.12
    detail.FOAM_LANDING_PATCH = (2, 4)
    detail.FOAM_RADIUS = (0.0008, 0.0022)
    detail.FOAM_LIFE = (0.45, 1.20)
    detail.FOAM_DUCK_GAP = 0.006


def quaternion_matrix(wxyz):
    w, x, y, z = np.asarray(wxyz, dtype=np.float64)
    n = w*w + x*x + y*y + z*z
    if n < 1e-16:
        return np.eye(3)
    s = 2.0 / n
    return np.array([
        [1-s*(y*y+z*z), s*(x*y-z*w), s*(x*z+y*w)],
        [s*(x*y+z*w), 1-s*(x*x+z*z), s*(y*z-x*w)],
        [s*(x*z-y*w), s*(y*z+x*w), 1-s*(x*x+y*y)],
    ])


def car_material_points(position, quaternion):
    axes = [np.linspace(-0.5*size, 0.5*size, 5) for size in CAR_SIZE]
    local = np.stack(np.meshgrid(*axes, indexing="ij"), -1).reshape(-1, 3)
    shell = np.any(np.isclose(np.abs(local), 0.5*CAR_SIZE, atol=1e-9), axis=1)
    return local[shell] @ quaternion_matrix(quaternion).T + np.asarray(position)


def atomic_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def parse_frames(text, maximum):
    frames = sorted({frame for part in text.split(",")
                     for frame in range(int(part.split("-")[0]), int(part.split("-")[-1]) + 1)})
    if not frames or frames[0] < 1 or frames[-1] > maximum:
        raise ValueError(f"frames must be inside 1-{maximum}: {text}")
    return frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--frames", default="1-96")
    parser.add_argument("--out-name", default="aniso_toy")
    parser.add_argument('--workers',type=int,default=16)
    parser.add_argument('--interaction-gate',action='store_true')
    parser.add_argument('--reuse-primary',type=Path)
    parser.add_argument('--reuse-primary-prefix-last',type=int,default=96)
    args = parser.parse_args()

    run = args.run.resolve()
    report = json.loads((run / "simulation_report.json").read_text())
    frame_count = int(report["numerics"]["frames"])
    dx = float(report["numerics"]["dx_m"])
    wanted = parse_frames(args.frames, frame_count)
    detail, detail_source = load_duck_detail()
    configure_for_toy_car(detail,args.workers)
    detail.numba.set_num_threads(min(args.workers, detail.numba.config.NUMBA_NUM_THREADS))

    with np.load(run / "particles" / "frame_0001.npz") as state:
        initial = state["water_pos"].astype(np.float64)
    still_level = float(np.percentile(initial[:, 2], 99.5) + dx / 2)
    out = run / args.out_name
    out.mkdir(exist_ok=True)
    settings = {
        "source": "unchanged Genesis DFSPH particle cache",
        "implementation": str(detail_source),
        "dx_m": dx,
        "still_level_m": still_level,
        "surface": {
            "method": "elastic_duck anisotropic kernel",
            "covariance_radius_h": detail.COVARIANCE_RADIUS,
            "surface_neighbours": detail.SURFACE_NEIGHBOURS,
            "max_stretch": detail.MAX_STRETCH,
            "smoothing_iterations": detail.SMOOTHING_ITERATIONS,
            "normal_iterations": detail.NORMAL_ITERATIONS,
            "cell_particle_radii": detail.CELL,
            "iso": detail.ISO,
        },
        "secondary": {name: getattr(detail, name) for name in (
            "DROPS_PER_TORN", "SPRAY_SPEED", "SPRAY_MIN_HEIGHT", "SHED_MIN_SPEED",
            "SHED_HEIGHT", "DROP_RADIUS", "MIST_RADIUS", "MIST_LIFE", "FOAM_CHURN",
            "FOAM_RATE", "FOAM_RADIUS", "FOAM_LIFE")},
    }
    settings['interaction_gate']={'enabled':args.interaction_gate,'contact_distance_dx':1.5,
        'spray_source_radius_m':.32,'foam_source_radius_m':.24,'emission_duration_s':1.1,
        'emission_decay_s':.7,'scope':'Visual secondary emission only; physical particles and primary meshes are unchanged'}
    settings['primary_reused_from']=str(args.reuse_primary) if args.reuse_primary else None
    log_path = out / "report.json"
    log = {"settings": settings, "frames": {}, "physics_changed": False}

    drops = detail.Flying(dx, detail.DROP_RADIUS)
    mist = detail.Flying(dx, detail.MIST_RADIUS, terminal=detail.MIST_TERMINAL, life=detail.MIST_LIFE)
    foam = detail.Foam()
    converted = None
    previous = None
    h = 2 * dx
    contact_frame=None
    for frame in range(1, wanted[-1] + 1):
        tick = time.monotonic()
        with np.load(run / "particles" / f"frame_{frame:04d}.npz") as state:
            x = state["water_pos"].astype(np.float64)
            v = state["water_vel"].astype(np.float64)
            car_center=state['car_pos'].astype(np.float64)
            car = car_material_points(state["car_pos"], state["car_quat_wxyz"]) if report['physics'].get('car_present',True) else np.empty((0,3))
        if previous is not None and np.median(np.linalg.norm(x - previous, axis=1)) >= dx:
            raise RuntimeError(f"particle ordering changed at frame {frame}")
        previous = x
        converted = np.zeros(len(x), bool) if converted is None else converted
        tree = cKDTree(x)
        nearest_car=float(np.min(tree.query(car,k=1,workers=detail.WORKERS)[0])) if len(car) else 100.
        if contact_frame is None and nearest_car<=1.5*dx:contact_frame=frame
        elapsed=(frame-contact_frame)/FPS if contact_frame is not None else -1
        emit_gain=(np.exp(-elapsed/.7) if 0<=elapsed<=1.1 else 0.) if args.interaction_gate else 1.
        near_car=np.linalg.norm(x[:,:2]-car_center[:2],axis=1)<.32
        counts = tree.query_ball_point(x, 0.999*h, return_length=True, workers=detail.WORKERS) - 1
        height_points = np.concatenate((x[counts >= 9], car, np.array([[0., 0., dx/2]])))
        heights = detail.Heights(height_points, DOMAIN_LOWER, DOMAIN_UPPER, still_level, size=0.025)
        torn = detail.torn_particles(tree, x, counts, h)
        surface_now = detail.Surface(x, v, counts, still_level, dx)
        rng = np.random.default_rng(detail.SEED + frame)
        if frame > 1:
            drops.advance(1/FPS)
            mist.advance(1/FPS)
            foam.advance(1/FPS, surface_now, car, DOMAIN_LOWER, DOMAIN_UPPER)
        landed = drops.cull(heights, DOMAIN_LOWER, DOMAIN_UPPER)
        mist.cull(heights, DOMAIN_LOWER, DOMAIN_UPPER)
        if len(landed):
            selected = landed[rng.uniform(size=len(landed)) < detail.FOAM_FROM_LANDING]
            foam.spawn(selected, surface_now, rng, detail.FOAM_LANDING_PATCH)
        clearance = x[:, 2] - heights(x)
        new = torn & ~converted & (clearance > 0)
        converted = (converted | new) & torn
        speed = np.linalg.norm(v, axis=1)
        energy = (np.clip((speed[new]-detail.SPRAY_SPEED[0]) /
                          (detail.SPRAY_SPEED[1]-detail.SPRAY_SPEED[0]), 0, 1)
                  * (clearance[new] > detail.SPRAY_MIN_HEIGHT))
        if args.interaction_gate:energy*=emit_gain*near_car[new]
        drops.emit(x[new], v[new], np.round(detail.DROPS_PER_TORN*energy).astype(int), rng,
                   detail.DROP_ALONG, detail.DROP_ACROSS, detail.DROP_SPREAD, detail.DROP_STRETCH)
        mist.emit(x[new], v[new], np.round(detail.MIST_PER_TORN*energy).astype(int), rng,
                  0.5, 1.0, detail.MIST_SPREAD, 0.2, detail.MIST_SLOWDOWN)
        shedding = (~converted & (counts >= 1) & (counts <= detail.SHED_NEIGHBOURS)
                    & (speed > detail.SHED_MIN_SPEED) & (x[:, 2] > still_level + detail.SHED_HEIGHT))
        if args.interaction_gate:shedding&=near_car & (emit_gain>0)
        rate = np.clip(speed[shedding] / 1.5, 0, 1.5)
        if args.interaction_gate:rate*=emit_gain
        drops.emit(x[shedding], v[shedding], rng.poisson(detail.SHED_PER_FRAME*rate), rng,
                   detail.DROP_ALONG, detail.DROP_ACROSS, detail.DROP_SPREAD, detail.DROP_STRETCH)
        mist.emit(x[shedding], v[shedding], rng.poisson(detail.MIST_PER_FRAME*rate), rng,
                  0.5, 1.0, detail.MIST_SPREAD, 0.2, detail.MIST_SLOWDOWN)

        top, _ = surface_now.sample(surface_now.points[:, :2])
        layer = surface_now.points[:, 2] > top - dx/2 - 0.006
        points, flow = surface_now.points[layer], surface_now.velocity[layer]
        if len(points) >= 9:
            _, neighbour = cKDTree(points).query(points, k=9, workers=detail.WORKERS)
            churn = np.linalg.norm(flow[neighbour[:, 1:]] - flow[:, None, :], axis=2).mean(axis=1)
            churn = rng.poisson(detail.FOAM_RATE*np.clip(
                (churn-detail.FOAM_CHURN[0])/(detail.FOAM_CHURN[1]-detail.FOAM_CHURN[0]), 0, 1))
            if args.interaction_gate:
                close=np.linalg.norm(points[:,:2]-car_center[:2],axis=1)<.24
                churn=rng.binomial(churn,np.clip(emit_gain*close,0,1))
            foam.spawn(np.repeat(points, churn, axis=0), surface_now, rng, detail.FOAM_PATCH)
        foam.advance(0., surface_now, car, DOMAIN_LOWER, DOMAIN_UPPER)

        record = {"torn_new": int(new.sum()), "hidden": int(converted.sum()),
                  "shedding": int(shedding.sum()), "drops": len(drops.radius),
                  "mist": len(mist.radius), "foam": len(foam.radius)}
        record.update({'contact_frame':contact_frame,'nearest_car_particle_m':nearest_car,'secondary_emission_gain':float(emit_gain)})
        if frame in wanted:
            drops.save(out / f"spray_{frame:04d}.npz")
            mist.save(out / f"mist_{frame:04d}.npz")
            foam.save(out / f"foam_{frame:04d}.npz")
            if args.reuse_primary and frame<=args.reuse_primary_prefix_last:
                source=args.reuse_primary/f'water_{frame:04d}.npz';target=out/source.name
                if not target.exists():os.link(source,target)
                stats={'reused_unchanged_primary':str(source)}
            else:
                mesh, stats = detail.surface(x[~converted], v[~converted], h, dx, still_level)
                np.savez_compressed(out / f"water_{frame:04d}.npz", **mesh)
            record["surface"] = stats
        record["seconds"] = time.monotonic() - tick
        log["frames"][str(frame)] = record
        atomic_json(log_path, log)
        print("DUCK_STYLE_DETAIL", frame, json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
