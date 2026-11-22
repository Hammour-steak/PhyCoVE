"""Reconstruct recorded liquid per frame without deleting droplets or freezing trajectories.

Usage: python surface_cup_water_drop.py RUN [--contact-angle-deg 55]
Bulk water uses splashsurf; tiny detached airborne clusters become volume-preserving spheres;
landed droplets/puddles on the table, saucer, or linen become watertight sessile caps or films
with split base normals and preserved sliding velocity. No temporal holds are used.
"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
import argparse
import json
import time
from pathlib import Path

import numpy as np
import pysplashsurf
import trimesh
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from droplets_cup_water_drop import airborne_droplets, landed_droplets

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("run", type=Path)
parser.add_argument("--contact-angle-deg", type=float, default=42.0)
parser.add_argument("--frames", default="", help="optional comma-separated 1-based frames to mesh")
args = parser.parse_args()
if not 0 < args.contact_angle_deg <= 90:
    parser.error("contact angle must be in (0, 90] degrees")
only_frames = {int(x) for x in args.frames.split(",") if x.strip()} if args.frames else None

run = args.run
L = json.loads((run / "sim_log.json").read_text())
A = L["args"]
geom = Path(A["geom"])
cav = json.loads((geom / "cavity.json").read_text())
profile = np.asarray(cav["profile_z_rmin_rmedian"])
props = trimesh.util.concatenate([trimesh.load(geom / name) for name in ("plate_collider.obj", "napkin_collider.obj")])
d, fps = A["particle"], A["fps"]
volume = 0.8 * d ** 3
start, count = L["start_frame"], L["simulated_frames"]
n_frames = start - 1 + count
P = np.load(run / "water_pos.npy", mmap_mode="r")
V = np.load(run / "water_vel_f16.npy", mmap_mode="r")
initial = np.load(L["water_state"])["pos_local"]
poses = L["cup_pose"]
out = run / "surfaces"
out.mkdir(exist_ok=True)


def support_z(xy):
    z = np.zeros(len(xy))
    if len(xy):
        origins = np.column_stack([xy, np.full(len(xy), 0.5)])
        locations, indices, _ = props.ray.intersects_location(
            origins, np.tile([0.0, 0.0, -1.0], (len(xy), 1)), multiple_hits=False
        )
        if len(indices):
            z[indices] = np.maximum(0.0, np.asarray(locations).reshape(-1, 3)[:, 2])
    return z


def bulk_surface(pos, vel, pose_pos, rotation):
    empty = lambda dtype: np.empty((0, 3), dtype)
    if not len(pos):
        return empty(np.float32), empty(np.int32), empty(np.float32), empty(np.float32)
    result, _ = pysplashsurf.reconstruction_pipeline(
        pos,
        particle_radius=0.64 * d,
        smoothing_length=2.40,
        cube_size=0.50,
        iso_surface_threshold=0.52,
        mesh_smoothing_weights=True,
        mesh_smoothing_iters=14,
        normals_smoothing_iters=12,
        mesh_cleanup=True,
        compute_normals=True,
        multi_threading=True,
    )
    vertices = np.asarray(result.mesh.vertices, np.float32)
    triangles = np.asarray(result.mesh.triangles, np.int32)
    if not len(vertices) or not len(triangles):
        return empty(np.float32), empty(np.int32), empty(np.float32), empty(np.float32)
    normals = np.asarray(result.point_attributes["normals"], np.float32)

    # Seal inner-cup liquid boundary slightly into opaque porcelain wall/floor and form wetting meniscus
    v_loc = rotation.inv().apply(vertices.astype(np.float64) - np.asarray(pose_pos, np.float64))
    n_loc = rotation.inv().apply(normals.astype(np.float64))
    r_xy = np.hypot(v_loc[:, 0], v_loc[:, 1])
    r_wall = np.interp(v_loc[:, 2], profile[:, 0], profile[:, 1])
    in_cav = (
        (v_loc[:, 2] >= cav["inner_floor_z"] - 0.0025)
        & (v_loc[:, 2] <= cav["rim_z"] - 0.0015)
        & (r_xy <= r_wall + 0.0022)
    )
    if in_cav.any():
        ur_x = np.where(r_xy > 1e-6, v_loc[:, 0] / np.maximum(r_xy, 1e-6), 0.0)
        ur_y = np.where(r_xy > 1e-6, v_loc[:, 1] / np.maximum(r_xy, 1e-6), 0.0)
        n_rad = n_loc[:, 0] * ur_x + n_loc[:, 1] * ur_y

        side_seal = in_cav & (r_xy > r_wall - 0.0022) & (n_rad > 0.35)
        if side_seal.any():
            r_new = np.maximum(r_xy[side_seal], r_wall[side_seal] + 0.00045)
            v_loc[side_seal, 0] = ur_x[side_seal] * r_new
            v_loc[side_seal, 1] = ur_y[side_seal] * r_new
            r_xy[side_seal] = r_new

        floor_seal = in_cav & (v_loc[:, 2] < cav["inner_floor_z"] + 0.0022) & (n_loc[:, 2] < -0.35)
        if floor_seal.any():
            v_loc[floor_seal, 2] = np.minimum(v_loc[floor_seal, 2], cav["inner_floor_z"] - 0.00045)

        meniscus = (
            in_cav
            & (r_xy > r_wall - 0.0042)
            & (n_loc[:, 2] > 0.20)
            & (v_loc[:, 2] > cav["inner_floor_z"] + 0.004)
            & (v_loc[:, 2] < cav["rim_z"] - 0.0018)
        )
        w_men = None
        if meniscus.any():
            d_wall = np.maximum(r_wall[meniscus] - r_xy[meniscus], 0.0)
            t_men = np.clip(1.0 - d_wall / 0.0042, 0.0, 1.0)
            nz_w = np.clip((n_loc[meniscus, 2] - 0.20) / 0.35, 0.0, 1.0)
            w_men = (t_men * t_men * (3.0 - 2.0 * t_men)) * nz_w
            dz = 0.00135 * (t_men ** 2.2) * nz_w
            v_loc[meniscus, 2] = np.minimum(v_loc[meniscus, 2] + dz, cav["rim_z"] - 0.0008)
            lip = d_wall < 0.0012
            if lip.any():
                idx_lip = np.flatnonzero(meniscus)[lip]
                w_lip = (1.0 - d_wall[lip] / 0.0012) ** 2
                r_lip = r_xy[idx_lip] + w_lip * np.maximum(r_wall[idx_lip] + 0.00040 - r_xy[idx_lip], 0.0)
                v_loc[idx_lip, 0] = ur_x[idx_lip] * r_lip
                v_loc[idx_lip, 1] = ur_y[idx_lip] * r_lip

        touched = side_seal | floor_seal | meniscus
        if touched.any():
            vertices = (rotation.apply(v_loc) + np.asarray(pose_pos, np.float64)).astype(np.float32)
            if meniscus.any() and w_men is not None:
                recomputed = trimesh.Trimesh(vertices, triangles, process=False).vertex_normals.astype(np.float32)
                wm = w_men.astype(np.float32)[:, None]
                blended = (1.0 - wm) * normals[meniscus] + wm * recomputed[meniscus]
                blended /= np.maximum(np.linalg.norm(blended, axis=1, keepdims=True), 1e-6)
                normals[meniscus] = blended

    k = min(4, len(pos))
    distances, indices = cKDTree(pos).query(vertices, k=k)
    distances = np.asarray(distances).reshape(len(vertices), k)
    indices = np.asarray(indices).reshape(len(vertices), k)
    weights = 1.0 / np.maximum(distances, 1e-5)
    weights /= weights.sum(1, keepdims=True)
    velocity = (vel[indices] * weights[..., None]).sum(1).astype(np.float32)
    return vertices, triangles, normals, velocity


log = {
    "schema_version": 2,
    "particle_volume_m3": volume,
    "hidden_particles": 0,
    "drop_contact_angle_deg": args.contact_angle_deg,
    "temporal_filter": "none",
    "holds": {"segments": 0, "held_frames": 0},
    "frames": [],
}
t0 = time.monotonic()
ever_landed = np.zeros(len(initial), dtype=bool)
settled_xy = None

for frame in range(1, n_frames + 1):
    pose = poses[str(frame)]
    q = pose["quat_wxyz"]
    rotation = Rotation.from_quat([q[1], q[2], q[3], q[0]])
    if frame < start:
        pos = rotation.apply(initial) + pose["pos"]
        lin_v = np.asarray(pose.get("lin_vel", [0.0, 0.0, -9.81 * (frame - 1) / fps]), dtype=np.float64)
        ang_w = np.asarray(pose.get("ang_vel_world", [0.0, 0.0, 0.0]), dtype=np.float64)
        com_p = np.asarray(pose.get("com_pos", pose["pos"]), dtype=np.float64)
        vel = (lin_v + np.cross(ang_w, pos - com_p)).astype(np.float32)
    else:
        pos = np.asarray(P[frame - start], np.float64).copy()
        vel = np.asarray(V[frame - start], np.float32).copy()

    local = rotation.inv().apply(pos - pose["pos"])
    inside = (
        (np.hypot(local[:, 0], local[:, 1]) < np.interp(local[:, 2], profile[:, 0], profile[:, 1]) + 0.001)
        & (local[:, 2] > cav["inner_floor_z"] - 0.002)
        & (local[:, 2] < cav["rim_z"] + 0.003)
    )
    landed = ever_landed & (~inside) & (pos[:, 2] < 0.025)
    candidates = np.flatnonzero(~inside & ~landed & (pos[:, 2] < 0.05))
    if len(candidates):
        height = pos[candidates, 2] - support_z(pos[candidates, :2])
        touch = (height >= -0.0020) & (height < 0.0032) & (np.abs(vel[candidates, 2]) < 0.25)
        landed[candidates[touch]] = True
        # Absorb upper-layer particles of shallow puddles so they never render as bumpy spheres atop films
        remain = candidates[~touch & (height >= -0.0020) & (height < 0.0055)]
        if len(remain) and landed.any():
            d_land, _ = cKDTree(pos[landed]).query(pos[remain], k=1, distance_upper_bound=2.2 * d)
            landed[remain[np.isfinite(d_land)]] = True
    ever_landed |= landed

    if settled_xy is None:
        settled_xy = pos[:, :2].copy()
    else:
        fast = (~landed) | (np.hypot(vel[:, 0], vel[:, 1]) > 0.05)
        settled_xy[fast] = pos[fast, :2]
        slow_landed = landed & (~fast) & (np.hypot(vel[:, 0], vel[:, 1]) > 0.008)
        settled_xy[slow_landed] = 0.70 * settled_xy[slow_landed] + 0.30 * pos[slow_landed, :2]
        pos[landed, :2] = settled_xy[landed]

    if only_frames is not None and frame not in only_frames:
        continue

    moving = ~landed
    bulk, sv, st, sn, sm, subresolution_count = airborne_droplets(pos[moving], vel[moving], volume, d)
    vertices, triangles, normals, motion = bulk_surface(pos[moving][bulk], vel[moving][bulk], pose["pos"], rotation)
    if len(st):
        triangles = np.vstack([triangles, st + len(vertices)])
        vertices = np.vstack([vertices, sv])
        normals = np.vstack([normals, sn])
        motion = np.vstack([motion, sm])

    drops_v, drops_t, drops_ln, drops_vel, drop_count = landed_droplets(
        pos[landed], vel[landed], volume, d, args.contact_angle_deg, support_z
    )
    if len(drops_v) and len(drops_t):
        tm_drop = trimesh.Trimesh(drops_v, drops_t, process=False)
        cc_drop = tm_drop.split(only_watertight=False)
        if len(cc_drop) > 1:
            main_p = max(cc_drop, key=lambda m: abs(m.volume))
            flat_parts = [main_p]
            for m in cc_drop:
                if m is main_p:
                    continue
                mf = m.copy()
                min_z = mf.vertices[:, 2].min()
                h = np.maximum(mf.vertices[:, 2] - min_z, 0.0)
                mf.vertices[:, 2] = min_z + h * 0.20
                flat_parts.append(mf)
            comb = trimesh.util.concatenate(flat_parts)
            drops_v = comb.vertices.astype(np.float32)
            drops_t = comb.faces.astype(np.int32)
            drops_ln = comb.vertex_normals[comb.faces].reshape(-1, 3).astype(np.float32)
            drops_ln[:, :2] *= 0.35
            drops_ln /= np.maximum(np.linalg.norm(drops_ln, axis=1, keepdims=True), 1e-6)
            drops_vel = np.zeros_like(drops_v, dtype=np.float32)
    np.savez(
        out / f"water_{frame:04d}.npz",
        vertices=vertices,
        triangles=triangles,
        normals=normals,
        velocity=motion,
        drops_vertices=drops_v,
        drops_triangles=drops_t,
        drops_loop_normals=drops_ln,
        drops_velocity=drops_vel,
    )
    record = {
        "frame": frame,
        "total_particles": len(pos),
        "bulk_particles": int(bulk.sum()),
        "airborne_droplet_particles": subresolution_count,
        "landed_particles": int(landed.sum()),
        "represented_particles": int(bulk.sum()) + subresolution_count + int(landed.sum()),
        "isolated_not_meshed": 0,
        "drops": drop_count,
    }
    assert record["represented_particles"] == len(pos)
    log["frames"].append(record)
    if frame % 6 == 0 or frame == 1 or frame == n_frames:
        print(json.dumps(record), f"elapsed {time.monotonic() - t0:.1f}s", flush=True)

(out / "cup_poses.json").write_text(json.dumps({"poses": poses}))
(out / "hold_plan.json").write_text(
    json.dumps({"segments": [], "fade_frames": 0, "frames": [[[1.0, f"frame{f}"]] for f in range(1, n_frames + 1)]})
)
(run / "surface_log.json").write_text(json.dumps(log, indent=2))
print(f"surface done {time.monotonic() - t0:.1f}s; no discarded particles")
