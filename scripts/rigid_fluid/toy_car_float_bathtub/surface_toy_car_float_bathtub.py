"""Water surface of the bathtub from the particle cache (render geometry only; the particles are read-only).

The open water is a height field: the top particle layer, averaged in space (wider where the water is still, so its particle
noise does not show, narrower where it moves fast) and over three frames, with a meniscus at the ceramic and the float.
Columns whose top particle lies under a solid have no water surface there, so the height continues through the solid from its
surroundings and the solid pierces the sheet at the right level. Thin sheets and clusters above the sheet join it in one
implicit field (marching cubes in a band); clusters well above it are meshed on their own; single torn-off particles become a
handful of droplets that keep their offsets while they fly. No foam or mist: clean tap water holds neither. The sheet ends
inside the ceramic, so it needs no bottom (rays that enter it end on the ceramic).
Writes water_####.npz (vertices, triangles, normals, velocity), spray_####.npz (position, radius, velocity, fade) and
caustic_####.npy (the sun's light pattern on the floor: light refracted by the height field, 1 = flat water) and wet_####.npy
(where water has touched the ceramic so far; the render draws its flat beads). Beads stay on the float and the car at the
points particles have come close to; they join the droplets in spray_####.npz, where kind tells them apart (0 droplet,
1 float bead, 2 car bead), and car_wet_local lists every car point that has been wet so far, in the car's own frame (the
render draws those as wet paint instead of sub-pixel spheres; water resting on the car makes no droplets for the same
reason). Frames must be processed in order from frame 1 for the wet history.
usage: <python> surface_toy_car_float_bathtub.py --run RUN --out DIR --frames 1-36 [--cell 0.002]"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import scene_asset
import argparse, json, time
from pathlib import Path

import numba
import numpy as np
import trimesh
from scipy.ndimage import distance_transform_edt, gaussian_filter, map_coordinates, maximum_filter
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes

HERE = Path(__file__).resolve().parent


def ASSET(rel):
    return scene_asset(HERE, "assets/" + rel)


ap = argparse.ArgumentParser()
ap.add_argument("--run", type=Path, required=True)
ap.add_argument("--out", type=Path, required=True)
ap.add_argument("--frames", default="1-96")
ap.add_argument("--cell", type=float, default=0.002)
ap.add_argument("--sigma-still", type=float, default=2.4, help="height-field Gaussian sigma in still water, in particle spacings")
ap.add_argument("--sigma-fast", type=float, default=1.3, help="in water moving faster than --speed-fast")
ap.add_argument("--speed-still", type=float, default=0.04)
ap.add_argument("--speed-fast", type=float, default=0.35)
ap.add_argument("--sigma-caustic", type=float, default=0.006, help="further smoothing of the surface normals for the light pattern (m)")
ap.add_argument("--meniscus-tub", type=float, default=0.0022, help="meniscus height on the ceramic (m); capillary length 2.7 mm")
ap.add_argument("--meniscus-float", type=float, default=0.0008, help="on the hydrophobic PVC")
ap.add_argument("--drops-per-particle", type=int, default=6)
ap.add_argument("--sun", type=float, nargs=3, default=(1.10, 0.77, -1.53), help="direction of the render's sun beam")
a = ap.parse_args()
a.out.mkdir(parents=True, exist_ok=True)
log = json.loads((a.run / "sim_log.json").read_text())
d = float(log["args"]["particle"]); sp = float(log["args"]["rest_spacing"]) * d; h = 2 * d
V = 0.8 * d ** 3
frames = sorted({f for part in a.frames.split(",") for f in range(int(part.split("-")[0]), int(part.split("-")[-1]) + 1)})
last_frame = len(log["frames"])

# ---------------------------------------------------------------- the tub on the surface grid
_t = np.load(HERE / "geometry/tub_shell.npz")
rings, (cx, cy) = _t["rings"], _t["center"]
INNER = np.arange(2, 25)
nth = rings.shape[1]
prof_rho = np.hypot(rings[INNER, :, 0] - cx, rings[INNER, :, 1] - cy)
prof_z = rings[INNER, 0, 2]
cell = a.cell
xs = np.arange(-0.46, 0.49 + 1e-9, cell); ys = np.arange(-0.95, 0.97 + 1e-9, cell)
X, Y = np.meshgrid(xs, ys, indexing="ij")
_rho = np.hypot(X - cx, Y - cy); _th = np.arctan2(Y - cy, X - cx) % (2 * np.pi) / (2 * np.pi) * nth
_i0 = np.floor(_th).astype(int) % nth; _i1 = (_i0 + 1) % nth; _w = _th - np.floor(_th)
ZS = np.zeros(X.shape)
for k in range(nth):
    m0, m1 = _i0 == k, _i1 == k
    ZS[m0] += (1 - _w[m0]) * np.interp(_rho[m0], prof_rho[:, k], prof_z)
    ZS[m1] += _w[m1] * np.interp(_rho[m1], prof_rho[:, k], prof_z)
del _rho, _th, _i0, _i1, _w

# ---------------------------------------------------------------- the solids, for the columns under them
_fv = np.load(ASSET("procedural_float/float_mesh.npz"))["vertices"][::2].astype(np.float64)
_cv = np.asarray(trimesh.load(ASSET("amg_vision_gt/collision.obj"), process=True).vertices, np.float64)


def quat_matrix(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def raster_solid(pts, top, bottom):
    """highest and lowest solid point per column"""
    i = ((pts[:, 0] - xs[0]) / cell).astype(int); j = ((pts[:, 1] - ys[0]) / cell).astype(int)
    ok = (i >= 0) & (i < len(xs)) & (j >= 0) & (j < len(ys))
    np.maximum.at(top, (i[ok], j[ok]), pts[ok, 2]); np.minimum.at(bottom, (i[ok], j[ok]), pts[ok, 2])


@numba.njit(parallel=True, fastmath=True, cache=True)
def splat_blobs(phi, ox, oy, oz, c, pts, R):
    """sum of cubic kernels on a cube grid; x slabs of one colour never overlap"""
    nx, ny, nz = phi.shape
    r_c = int(np.ceil(R / c))
    for colour in range(2):
        slabs = np.arange(colour, max(nx // (2 * r_c + 2), 1) * 2 + 2, 2)
        for s in numba.prange(len(slabs)):
            lo, hi = slabs[s] * (r_c + 1), (slabs[s] + 1) * (r_c + 1)
            for p in range(len(pts)):
                ic = int((pts[p, 0] - ox) / c)
                if ic < lo or ic >= hi:
                    continue
                jc, lc = int((pts[p, 1] - oy) / c), int((pts[p, 2] - oz) / c)
                for i in range(max(ic - r_c, 0), min(ic + r_c + 2, nx)):
                    rx = ox + i * c - pts[p, 0]
                    for j in range(max(jc - r_c, 0), min(jc + r_c + 2, ny)):
                        ry = oy + j * c - pts[p, 1]
                        for l in range(max(lc - r_c, 0), min(lc + r_c + 2, nz)):
                            rz = oz + l * c - pts[p, 2]
                            q = np.sqrt(rx * rx + ry * ry + rz * rz) / R
                            if q < 1.0:
                                phi[i, j, l] += (6.0 * q * q * q - 6.0 * q * q + 1.0) if q <= 0.5 else 2.0 * (1.0 - q) ** 3


def vertex_velocity(vertices, tree, vel):
    dist, idx = tree.query(vertices, k=4, workers=-1)
    w = np.clip(1 - dist / (2 * h), 1e-4, None) ** 3
    w /= w.sum(1, keepdims=True)
    return np.einsum("vk,vkd->vd", w, vel[idx])


def load_frame(f):
    """particles, the columns under solids, and the height field of one frame"""
    data = np.load(a.run / "particles" / f"frame_{f:04d}.npz")
    active = data["active"]
    x = data["water_pos"][active].astype(np.float64); v = data["water_vel"][active].astype(np.float64)
    tree = cKDTree(x)
    counts = tree.query_ball_point(x, 0.999 * h, return_length=True, workers=-1) - 1
    bulk = counts >= 8
    top_s = np.full(X.shape, -1e9); bot_s = np.full(X.shape, 1e9)
    for pts, key in ((_fv, "tray"), (_cv, "robot")):
        p = data[f"{key}_pos"]
        if np.abs(p).sum() > 0:
            raster_solid(pts @ quat_matrix(data[f"{key}_quat_wxyz"]).T + p, top_s, bot_s)
    has_solid = gaussian_filter((top_s > -1e8).astype(np.float32), 0.8) > 0.25
    # the top of the connected water per column (one spacing wide), then its top layer
    ci = ((x[:, 0] - xs[0]) / cell).astype(int); cj = ((x[:, 1] - ys[0]) / cell).astype(int)
    inside = (ci >= 0) & (ci < len(xs)) & (cj >= 0) & (cj < len(ys))
    H0 = np.full(X.shape, -1e9)
    b_ = bulk & inside
    np.maximum.at(H0, (ci[b_], cj[b_]), x[b_, 2])
    H_top = maximum_filter(H0, size=int(round(1.5 * sp / cell)) | 1)
    near_top = b_ & (x[:, 2] > H_top[np.clip(ci, 0, len(xs) - 1), np.clip(cj, 0, len(ys) - 1)] - sp)
    idx_top = np.flatnonzero(near_top)
    # a column whose top particle is under a solid has no surface there
    top_at = maximum_filter(top_s, size=5)
    idx_top = idx_top[~(has_solid[ci[idx_top], cj[idx_top]] & (x[idx_top, 2] < top_at[ci[idx_top], cj[idx_top]] - 0.25 * sp))]
    w_ = np.zeros(X.shape, np.float32); z_ = np.zeros(X.shape, np.float32); s_ = np.zeros(X.shape, np.float32)
    np.add.at(w_, (ci[idx_top], cj[idx_top]), 1.0)
    np.add.at(z_, (ci[idx_top], cj[idx_top]), x[idx_top, 2] + 0.5 * sp)
    np.add.at(s_, (ci[idx_top], cj[idx_top]), np.linalg.norm(v[idx_top], axis=1))
    fields = []
    for sigma in (a.sigma_still, a.sigma_fast):
        sig = sigma * sp / cell
        W_ = gaussian_filter(w_, sig); Z_ = gaussian_filter(z_, sig)
        valid = W_ > 0.15 * (cell / sp) ** 2
        H = np.where(valid, Z_ / np.maximum(W_, 1e-9), 0.0)
        # beyond the data (inside the ceramic, under the solids) the sheet continues from the nearest water
        H = H[tuple(distance_transform_edt(~valid, return_distances=False, return_indices=True))]
        fields.append(np.where(valid, H, gaussian_filter(H, 2.0)))
    sig = a.sigma_fast * sp / cell
    speed = gaussian_filter(s_, sig) / np.maximum(gaussian_filter(w_, sig), 1e-9)
    b = np.clip((speed - a.speed_still) / (a.speed_fast - a.speed_still), 0, 1)
    b = gaussian_filter(b * b * (3 - 2 * b), sig)
    H = (1 - b) * fields[0] + b * fields[1]
    return dict(x=x, v=v, ids=np.flatnonzero(active), counts=counts, bulk=bulk, top_s=top_s, bot_s=bot_s, has_solid=has_solid, near_top=near_top, H=H)


# ---------------------------------------------------------------- where beads can sit
_rng = np.random.default_rng(20261103)
_fm = trimesh.Trimesh(*(np.load(ASSET("procedural_float/float_mesh.npz"))[k] for k in ("vertices", "triangles")), process=False)
_p, _i = trimesh.sample.sample_surface(_fm, 60000, seed=2)
_m = _fm.face_normals[_i][:, 2] > 0.25
float_beads = dict(key="tray", p=np.asarray(_p[_m]), r=_rng.uniform(0.0006, 0.0016, _m.sum()), wet=np.zeros(_m.sum(), bool))
_cm = trimesh.load(ASSET("amg_vision_gt/collision.obj"), process=True)
_p, _i = trimesh.sample.sample_surface(_cm, 16000, seed=3)
_m = _cm.face_normals[_i][:, 2] > 0.05
car_beads = dict(key="robot", p=np.asarray(_p[_m]), r=_rng.uniform(0.0004, 0.0011, _m.sum()), wet=np.zeros(_m.sum(), bool))
wet_map = np.zeros(X.shape, np.float32)

# one kernel at its centre is 1; a lone cluster should come out with about a particle's radius
R_blob = 1.6 * sp
ISO_BLOB = 0.42
cache = {}


def frame_data(f):
    if f not in cache:
        cache[f] = load_frame(f)
    return cache[f]


report = {}
for f in frames:
    t0 = time.time()
    fd = frame_data(f)
    x, v, ids, counts, bulk, top_s, bot_s, has_solid, near_top = (fd[k] for k in ("x", "v", "ids", "counts", "bulk", "top_s", "bot_s", "has_solid", "near_top"))
    # three frames in time: a wave passes in many frames, the particle noise changes in each
    Hp, Hn = frame_data(max(f - 1, 1))["H"], frame_data(min(f + 1, last_frame))["H"]
    H = 0.25 * Hp + 0.5 * fd["H"] + 0.25 * Hn
    for k_ in [k_ for k_ in cache if k_ < f - 1]:
        del cache[k_]

    # ---- meniscus on the ceramic and on the solids at the water line
    wall = ZS > H
    dist_wall = distance_transform_edt(~wall) * cell
    pierced = (top_s > H) & (bot_s < H)
    dist_body = distance_transform_edt(~pierced) * cell if pierced.any() else np.full(X.shape, 1.0)
    H_m = H + a.meniscus_tub * np.exp(-dist_wall / 0.0027) + a.meniscus_float * np.exp(-dist_body / 0.0027)

    # ---- where the water has been: under the sheet now, or where a free particle reached the ceramic above it
    ci_ = np.clip(((x[:, 0] - xs[0]) / cell).astype(int), 0, len(xs) - 1); cj_ = np.clip(((x[:, 1] - ys[0]) / cell).astype(int), 0, len(ys) - 1)
    touch = (np.abs(x[:, 2] - ZS[ci_, cj_]) < 1.2 * sp) & (ZS[ci_, cj_] > H_m[ci_, cj_] + 0.001)
    spots = np.zeros(X.shape, np.float32)
    np.add.at(spots, (ci_[touch], cj_[touch]), 1.0)
    wet_map = np.maximum(wet_map * 0.998, np.maximum((ZS < H_m + 0.0005).astype(np.float32), (gaussian_filter(spots, 2.5) > 0.015).astype(np.float32)))
    np.save(a.out / f"wet_{f:04d}.npy", gaussian_filter(wet_map, 2.0).astype(np.float16))

    # ---- the sun's light pattern on the ceramic: each surface cell's light refracts down to the floor. Light the solids block
    # lands flat, so the pattern does not also draw their shadow, which the render's beam casts itself
    gx, gy = np.gradient(gaussian_filter(H, a.sigma_caustic / cell), cell, cell)
    nz = 1.0 / np.sqrt(1 + gx * gx + gy * gy); nx_, ny_ = -gx * nz, -gy * nz
    l_ = np.array(a.sun) / np.linalg.norm(a.sun)
    eta = 1 / 1.333
    cosi = -(nx_ * l_[0] + ny_ * l_[1] + nz * l_[2])
    k_r = np.sqrt(np.maximum(1 - eta * eta * (1 - cosi * cosi), 0))
    tx = eta * l_[0] + (eta * cosi - k_r) * nx_; ty = eta * l_[1] + (eta * cosi - k_r) * ny_; tz = eta * l_[2] + (eta * cosi - k_r) * nz
    depth = np.clip(H - ZS, 0, None)
    t0_ = np.array([eta * l_[0], eta * l_[1], -np.sqrt(1 - eta * eta * (l_[0] ** 2 + l_[1] ** 2))])
    sx = np.where(has_solid, t0_[0] / t0_[2], tx / np.minimum(tz, -1e-3)); sy = np.where(has_solid, t0_[1] / t0_[2], ty / np.minimum(tz, -1e-3))
    u = (X - depth * sx - xs[0]) / cell; w = (Y - depth * sy - ys[0]) / cell
    wet = depth > 0
    i0_, j0_ = np.floor(u[wet]).astype(int), np.floor(w[wet]).astype(int)
    fu, fv_ = u[wet] - i0_, w[wet] - j0_
    cau = np.zeros(X.shape, np.float32)
    for di, dj, wt in ((0, 0, (1 - fu) * (1 - fv_)), (1, 0, fu * (1 - fv_)), (0, 1, (1 - fu) * fv_), (1, 1, fu * fv_)):
        ii, jj = i0_ + di, j0_ + dj
        ok = (ii >= 0) & (ii < len(xs)) & (jj >= 0) & (jj < len(ys))
        np.add.at(cau, (ii[ok], jj[ok]), wt[ok].astype(np.float32))
    # the sun's width and the ceramic's depth blur it; off the wet floor the pattern is neutral
    cau = gaussian_filter(cau, 1.2)
    wet_blur = gaussian_filter(wet.astype(np.float32), 1.2)
    I_c = np.where(wet_blur > 0.5, cau / np.maximum(wet_blur, 1e-3), 1.0)
    np.save(a.out / f"caustic_{f:04d}.npy", np.clip(I_c, 0.0, 4.0).astype(np.float16))

    # ---- what stands above the sheet: clusters join the implicit field, lone particles become droplets
    H_at = map_coordinates(H, [(x[:, 0] - xs[0]) / cell, (x[:, 1] - ys[0]) / cell], order=1, mode="nearest")
    above = x[:, 2] - H_at
    free = ((~bulk) | (above > 2.0 * sp)) & (above > 0.5 * sp)
    # water lying on the ceramic above the sheet is a film and beads (wet_####.npy): a mesh or spheres there read as dirt
    ci_ = np.clip(((x[:, 0] - xs[0]) / cell).astype(int), 0, len(xs) - 1); cj_ = np.clip(((x[:, 1] - ys[0]) / cell).astype(int), 0, len(ys) - 1)
    on_ceramic = (x[:, 2] - ZS[ci_, cj_] < 1.5 * sp) & (ZS[ci_, cj_] > H_at)
    free &= ~on_ceramic
    # water resting on the car is its wet paint in the render (car_wet_local below), not droplets: spheres there are under
    # a pixel across and shimmer from frame to frame
    d_car = np.load(a.run / "particles" / f"frame_{f:04d}.npz")
    p_car = d_car["robot_pos"]
    if np.abs(p_car).sum() > 0:
        dist_car, _ = cKDTree(car_beads["p"] @ quat_matrix(d_car["robot_quat_wxyz"]).T + p_car).query(
            x, distance_upper_bound=1.2 * sp, workers=-1)
        v_car = d_car["robot_vel"] + np.cross(d_car["robot_ang"], x - p_car)
        free &= ~(np.isfinite(dist_car) & (np.linalg.norm(v - v_car, axis=1) < 0.25))
    # thin fast water is spray: as blobs of the particle's size, motion blur draws it as thick bristles
    speed_ = np.linalg.norm(v, axis=1)
    lone = free & (above > 1.5 * sp) & ((counts <= 3) | ((counts <= 8) & (speed_ > 1.5)))
    cluster = free & ~lone

    # ---- the implicit field in a band around the sheet
    zlo = float(np.percentile(H_m[ZS < H_m], 0.1)) - 3 * cell
    band_top = H_m.max() + 3 * cell
    in_band = cluster & (x[:, 2] < zlo + 0.14)
    if in_band.any():
        band_top = max(band_top, float(x[in_band, 2].max()) + R_blob + 2 * cell)
    zc = 2 * cell
    zg = np.arange(zlo, band_top + zc, zc)
    phi = (H_m[:, :, None] - zg[None, None, :]).astype(np.float32)
    phi[ZS > H_m + 0.015] = -1.0                      # the sheet ends 15 mm inside the ceramic
    if in_band.any():
        # splat on a cube grid of the z cell, then sample on the sheet's grid
        g_x = np.arange(xs[0], xs[-1] + zc, zc); g_y = np.arange(ys[0], ys[-1] + zc, zc)
        lo_ = x[in_band].min(0) - R_blob - zc; hi_ = x[in_band].max(0) + R_blob + zc
        ix0, ix1 = np.searchsorted(g_x, lo_[0]), np.searchsorted(g_x, hi_[0]) + 1
        jy0, jy1 = np.searchsorted(g_y, lo_[1]), np.searchsorted(g_y, hi_[1]) + 1
        cube = np.zeros((max(ix1 - ix0, 1), max(jy1 - jy0, 1), len(zg)), np.float32)
        splat_blobs(cube, g_x[ix0], g_y[jy0], zlo, zc, x[in_band], R_blob)
        ii0, ii1 = np.searchsorted(xs, g_x[ix0]), min(np.searchsorted(xs, g_x[min(ix1, len(g_x)) - 1]) + 1, len(xs))
        jj0, jj1 = np.searchsorted(ys, g_y[jy0]), min(np.searchsorted(ys, g_y[min(jy1, len(g_y)) - 1]) + 1, len(ys))
        I_, J_, L_ = np.meshgrid((xs[ii0:ii1] - g_x[ix0]) / zc, (ys[jj0:jj1] - g_y[jy0]) / zc, np.arange(len(zg)), indexing="ij")
        blob = np.zeros(phi.shape, np.float32)
        blob[ii0:ii1, jj0:jj1] = map_coordinates(cube, [I_, J_, L_], order=1, mode="constant").astype(np.float32)
        phi_blob = (blob - ISO_BLOB) * R_blob * 0.6
        k_ = 0.003                                    # smooth union of the two fields
        hh = np.clip(0.5 + 0.5 * (phi_blob - phi) / k_, 0, 1)
        phi = phi * (1 - hh) + phi_blob * hh + k_ * hh * (1 - hh)
    verts, tris, _, _ = marching_cubes(phi, 0.0, spacing=(cell, cell, zc))
    verts = verts + [xs[0], ys[0], zlo]
    corners = verts[tris]
    fn = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    if fn[:, 2].sum() < 0:
        tris = tris[:, ::-1]; fn = -fn
    normals = np.zeros_like(verts)
    for k in range(3):
        np.add.at(normals, tris[:, k], fn)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)

    # ---- clusters high above the sheet: their own closed pieces
    high = cluster & ~in_band
    if high.any():
        lo_ = x[high].min(0) - R_blob - 2 * cell; hi_ = x[high].max(0) + R_blob + 2 * cell
        c2 = 2 * cell
        shape = np.ceil((hi_ - lo_) / c2).astype(int) + 1
        if np.prod(shape) < 3e8:
            g = np.zeros(shape, np.float32)
            splat_blobs(g, lo_[0], lo_[1], lo_[2], c2, x[high], R_blob)
            if g.max() > ISO_BLOB:
                v2, t2, _, _ = marching_cubes(g, ISO_BLOB, spacing=(c2, c2, c2))
                v2 = v2 + lo_
                m2 = trimesh.Trimesh(v2, t2, process=False)
                if m2.volume < 0:
                    t2 = t2[:, ::-1]
                    m2 = trimesh.Trimesh(v2, t2, process=False)
                tris = np.vstack([tris, t2 + len(verts)])
                normals = np.vstack([normals, m2.vertex_normals])
                verts = np.vstack([verts, v2])

    surf = np.flatnonzero(near_top | free)
    vel = vertex_velocity(verts, cKDTree(x[surf]), v[surf])
    # a mesh that moves fast at this resolution would smear into bristles; the droplets carry the streaks
    _sp = np.linalg.norm(vel, axis=1, keepdims=True)
    vel = vel * np.minimum(1.0, 2.0 / np.maximum(_sp, 1e-6))
    np.savez(a.out / f"water_{f:04d}.npz", vertices=verts.astype(np.float32), triangles=tris.astype(np.int32),
             normals=normals.astype(np.float32), velocity=vel.astype(np.float32))

    # ---- droplets of the lone particles: offsets and sizes fixed per particle, so they do not flicker
    li = np.flatnonzero(lone)
    n = a.drops_per_particle
    if len(li):
        r_eq = (3 * V / (4 * np.pi) / n) ** (1 / 3)
        pos, rad, vel_d = [], [], []
        for i in li:
            rg = np.random.default_rng(int(ids[i]) + 77)
            pos.append(x[i] + rg.normal(0, 0.45 * sp, (n, 3))); rad.append(r_eq * rg.uniform(0.6, 1.25, n)); vel_d.append(np.tile(v[i], (n, 1)))
        pos, rad, vel_d = np.vstack(pos), np.concatenate(rad), np.vstack(vel_d)
    else:
        pos, vel_d = np.zeros((0, 3)), np.zeros((0, 3)); rad = np.zeros(0)
    kind = [np.zeros(len(rad), np.int8)]
    # ---- beads where the water has been
    tree_all = cKDTree(x)
    for beads, kind_id in ((float_beads, 1), (car_beads, 2)):
        data = np.load(a.run / "particles" / f"frame_{f:04d}.npz")
        p_ = data[f"{beads['key']}_pos"]
        if np.abs(p_).sum() == 0:
            continue
        R_ = quat_matrix(data[f"{beads['key']}_quat_wxyz"])
        w_p = beads["p"] @ R_.T + p_
        dist_, _ = tree_all.query(w_p, distance_upper_bound=0.9 * sp, workers=-1)
        beads["wet"] |= np.isfinite(dist_)
        Hb = map_coordinates(H, [(w_p[:, 0] - xs[0]) / cell, (w_p[:, 1] - ys[0]) / cell], order=1, mode="nearest")
        show = beads["wet"] & (w_p[:, 2] > Hb + 0.001)
        w_ang = data[f"{beads['key']}_ang"]; v_b = data[f"{beads['key']}_vel"]
        pos = np.vstack([pos, w_p[show]]); rad = np.concatenate([rad, beads["r"][show]])
        vel_d = np.vstack([vel_d, v_b + np.cross(w_ang, w_p[show] - p_)])
        kind.append(np.full(int(show.sum()), kind_id, np.int8))
    np.savez(a.out / f"spray_{f:04d}.npz", position=pos.astype(np.float32), radius=rad.astype(np.float32),
             velocity=vel_d.astype(np.float32), fade=np.ones(len(rad), np.float32), kind=np.concatenate(kind),
             car_wet_local=car_beads["p"][car_beads["wet"]].astype(np.float32))
    report[f] = dict(vertices=len(verts), triangles=len(tris), lone=int(lone.sum()), cluster=int(cluster.sum()), drops=len(rad),
                     float_beads=int(float_beads["wet"].sum()), car_beads=int(car_beads["wet"].sum()), wet_above_cm2=round(float((wet_map[ZS > H_m + 0.001] > 0.5).sum() * cell * cell * 1e4), 1),
                     zlo=round(zlo, 4), band_top=round(float(band_top), 4), sec=round(time.time() - t0, 2))
    print(f, json.dumps(report[f]), flush=True)
    (a.out / "surface_report.json").write_text(json.dumps(report, indent=1))
