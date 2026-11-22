"""Milk surface per frame for render_milk_pitcher_glass.py: <run>/<mesh-dir>/milk_####.npz.

The milk standing in the glass is drawn from a volume-conserving height field: at 1 mm the particle pool's free surface
is a rough layer of single particles (a crushed-snow look), whereas gravity and surface tension keep a real milk
surface smooth on the scale of a few millimetres. Pool particles (inside the glass, below the volume level + POOL_BAND,
not falling fast) are binned into columns over the glass floor; the column surface (column bottom on the glass + column
volume / cell area) is smoothed over SMOOTH, shifted to conserve the pool volume and meshed (marching cubes) as a closed
body bounded by that surface and the glass cavity (pushed POOL_SEAL into the glass, no air film). The rest - the stream,
the plunge and the splash - is a pysplashsurf surface of the remaining particles, cut where it enters the pool. Spray
clusters of fewer than MIN_CLUSTER particles are not drawn.
usage: python surface_milk_pitcher_glass.py <run_dir> [--mesh-dir NAME] [frame ...]"""
import json, sys, time
from pathlib import Path
import numpy as np
import pysplashsurf
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
from skimage import measure

CELL = 0.4e-3
POOL_BAND = 0.006
POOL_FAST = -0.45                                   # m/s: particles falling faster than this belong to the stream
SMOOTH = 3.0e-3
POOL_SEAL = 0.15e-3
MIN_CLUSTER = 6                                     # smaller spray is not drawn
WALL_BAND = 0.003                                   # drops this close to the inner glass wall sit on it
WALL_MIN = 40                                       # smaller drops stuck on the glass are not drawn: the 1 mm impact on
                                                    # the dry floor over-splashes (~30 % of the first 20 mL), real pours leave a few spots
WALL_FLAT = 0.35                                    # thickness / width of a drop spread on the glass
DROP_MAX = 60                                       # clusters below this are drawn as spherical drops of equal volume

run = Path(sys.argv[1]); opts = sys.argv[2:]
mesh_dir = "meshes"
if "--mesh-dir" in opts:
    k = opts.index("--mesh-dir"); mesh_dir = opts[k + 1]; del opts[k:k + 2]
out = run / mesh_dir; out.mkdir(exist_ok=True)
L = json.load(open(run / "sim_log.json")); d = L["args"]["particle"]; Vp = L["particle_volume_m3"]
P = np.load(run / "milk_pos.npy", mmap_mode="r"); V = np.load(run / "milk_vel_f16.npy", mmap_mode="r")
counts = np.load(run / "active.npy")
only = {int(a) for a in opts} or set(range(1, len(P) + 1))

# ---- glass cavity profile r_cav(z) from the inner surface of the glass mesh
cup = np.load(Path(__file__).resolve().parent / "geometry/glass_cup.npz"); cv, cf = cup["vertices"], cup["triangles"]
a, b, c = cv[cf[:, 0]], cv[cf[:, 1]], cv[cf[:, 2]]
fn = np.cross(b - a, c - a); area = 0.5 * np.linalg.norm(fn, axis=1); fn /= np.maximum(2 * area, 1e-20)[:, None]
if np.einsum("ij,ij->i", a, np.cross(b, c)).sum() < 0:
    fn = -fn
rng = np.random.default_rng(3)
ns = np.maximum(1, (area / (0.0003 ** 2)).astype(int)); tri = np.repeat(np.arange(len(cf)), ns)
u, w = rng.random(len(tri)), rng.random(len(tri)); fl = u + w > 1; u[fl], w[fl] = 1 - u[fl], 1 - w[fl]
S = a[tri] + u[:, None] * (b - a)[tri] + w[:, None] * (c - a)[tri]; N = fn[tri]
rS = np.hypot(S[:, 0], S[:, 1]); radial = np.einsum("ij,ij->i", N[:, :2], S[:, :2] / np.maximum(rS, 1e-9)[:, None])
inner_wall = radial < -0.3
floor = (N[:, 2] > 0.7) & (rS < 0.035) & (S[:, 2] < 0.002)
Z_FLOOR = float(np.median(S[floor, 2])); R_FLOOR = float(rS[floor].max())
zb = np.arange(0.0, 0.104, 0.00025)
r_cav = np.full(len(zb), np.nan)
for i, z in enumerate(zb):
    m = inner_wall & (np.abs(S[:, 2] - z) < 0.0004)
    if m.any():
        r_cav[i] = np.median(rS[m])
ok = np.isfinite(r_cav); r_cav = np.interp(zb, zb[ok], r_cav[ok]); r_cav[zb < Z_FLOOR] = 0.0
r_cav[(zb >= Z_FLOOR) & (zb < zb[ok].min())] = max(R_FLOOR, r_cav[ok][0])
def rcav(z):
    return np.interp(z, zb, r_cav, left=0.0, right=r_cav[-1])
cav_vol = np.concatenate([[0.0], np.cumsum(np.pi * r_cav[:-1] ** 2 * np.diff(zb))])   # volume below zb
print(f"glass floor z {Z_FLOOR*1e3:.2f} mm (r {R_FLOOR*1e3:.1f} mm), cavity r at 20/48/90 mm: "
      f"{rcav(0.02)*1e3:.1f} / {rcav(0.048)*1e3:.1f} / {rcav(0.09)*1e3:.1f} mm, volume to 0.1 m {cav_vol[-1]*1e6:.0f} mL", flush=True)

gx = np.arange(-0.064, 0.064 + CELL, CELL)
X, Y = np.meshgrid(gx, gx, indexing="ij"); R = np.hypot(X, Y)
# bottom of each column: the floor inside R_FLOOR, else the height at which the cavity reaches that radius (lower bulge)
z_bottom = np.full(R.shape, np.inf)
z_bottom[R <= R_FLOOR] = Z_FLOOR
lower = zb[(zb >= Z_FLOOR) & (zb <= 0.048)]
z_bottom = np.where(R > R_FLOOR, np.interp(R, np.maximum.accumulate(rcav(lower)), lower, right=np.inf), z_bottom)


def pool_mesh(pos, vel):
    r = np.hypot(pos[:, 0], pos[:, 1])
    inside = r < rcav(pos[:, 2]) + 0.001
    slow = vel[:, 2] > POOL_FAST
    vol_in = (inside & slow).sum() * Vp
    level = float(np.interp(vol_in, cav_vol, zb))
    pool = inside & (pos[:, 2] < level + POOL_BAND) & (slow | (pos[:, 2] < level - 0.003))
    if pool.sum() < 50:
        return None, pool, level
    ix = np.clip(np.round((pos[pool, 0] - gx[0]) / CELL).astype(int), 0, len(gx) - 1)
    iy = np.clip(np.round((pos[pool, 1] - gx[0]) / CELL).astype(int), 0, len(gx) - 1)
    h = np.zeros(R.shape); np.add.at(h, (ix, iy), Vp / CELL ** 2)
    zs = z_bottom + h
    wet = np.isfinite(z_bottom) & (h > 0)
    s = SMOOTH / CELL
    region = np.isfinite(z_bottom) & (z_bottom < level + 0.002)
    num = ndimage.gaussian_filter(np.where(wet, zs, 0.0), s); den = ndimage.gaussian_filter(wet.astype(float), s)
    surf = np.where(region, num / np.maximum(den, 1e-6), -1.0)
    surf = np.where(region & (den < 0.05), level, surf)
    # volume conservation: shift so that the volume between the cavity bottom and the surface equals the pool's
    def volume(sf):
        return (np.clip(sf - np.where(np.isfinite(z_bottom), z_bottom, sf), 0, None) * region).sum() * CELL ** 2
    target = pool.sum() * Vp
    for _ in range(3):
        cur = volume(surf)
        area_ = ((surf > z_bottom) & region).sum() * CELL ** 2
        surf = np.where(region, surf + (target - cur) / max(area_, 1e-9), surf)
    top = float(surf[region].max()) + 0.0015
    zg = np.arange(Z_FLOOR - 0.0006, top, CELL)
    phi = np.minimum(surf[..., None] - zg[None, None, :], rcav(zg)[None, None, :] + POOL_SEAL - R[..., None])
    phi = np.minimum(phi, zg[None, None, :] - (Z_FLOOR - POOL_SEAL))
    phi = np.where(region[..., None], phi, -1.0).astype(np.float32)
    phi[0], phi[-1], phi[:, 0], phi[:, -1], phi[:, :, 0], phi[:, :, -1] = -1, -1, -1, -1, -1, -1
    vtx, faces, nrm, _ = measure.marching_cubes(phi, 0.0, spacing=(CELL, CELL, CELL))
    vtx += np.array([gx[0], gx[0], zg[0]])
    faces = faces[:, ::-1].copy()
    return (vtx, faces, nrm, surf), pool, level           # marching-cubes normals point out of the milk here


def _icosphere(subdiv=2):
    t = (1 + 5 ** 0.5) / 2
    v = np.array([[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
                  [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]], float)
    f = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6],
         [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7],
         [9, 8, 1]]
    v = list(v / np.linalg.norm(v, axis=1)[:, None])
    for _ in range(subdiv):
        cache, nf = {}, []
        def mid(i, j):
            key = (min(i, j), max(i, j))
            if key not in cache:
                m = (v[i] + v[j]) / 2; v.append(m / np.linalg.norm(m)); cache[key] = len(v) - 1
            return cache[key]
        for a_, b_, c_ in f:
            ab, bc, ca = mid(a_, b_), mid(b_, c_), mid(c_, a_)
            nf += [[a_, ab, ca], [b_, bc, ab], [c_, ca, bc], [ab, bc, ca]]
        f = nf
    return np.array(v), np.array(f)


def surface_at(surf, xy):
    i = np.clip(np.round((xy[:, 0] - gx[0]) / CELL).astype(int), 0, len(gx) - 1)
    j = np.clip(np.round((xy[:, 1] - gx[0]) / CELL).astype(int), 0, len(gx) - 1)
    return surf[i, j]


t0 = time.time(); rows = []
for i in range(len(P)):
    if i + 1 not in only:
        continue
    n_act = int(counts[i])
    empty = dict(vertices=np.zeros((0, 3), np.float32), triangles=np.zeros((0, 3), np.int32),
                 normals=np.zeros((0, 3), np.float32), velocity=np.zeros((0, 3), np.float32))
    if n_act < 2:
        np.savez(out / f"milk_{i+1:04d}.npz", **empty); continue
    pos = np.asarray(P[i, :n_act], np.float64); vel = np.asarray(V[i, :n_act], np.float32)
    pm, pool, level = pool_mesh(pos, vel)
    rest = ~pool
    parts_v, parts_f, parts_n, parts_u = [], [], [], []
    if pm is not None:
        vtx, faces, nrm, surf = pm
        parts_v.append(vtx); parts_f.append(faces); parts_n.append(nrm); parts_u.append(np.zeros_like(vtx))
    if rest.sum() > MIN_CLUSTER:
        q = pos[rest]; qv = vel[rest]
        tree = cKDTree(q)
        pairs = tree.query_pairs(1.5 * d, output_type="ndarray")
        adj = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(q), len(q)))
        _, lab = connected_components(adj, directed=False)
        size = np.bincount(lab)
        keep = size[lab] >= DROP_MAX
        drops = np.where((size >= MIN_CLUSTER) & (size < DROP_MAX))[0]
        if len(drops):
            dv, df, dn, du = [], [], [], []
            base_v, base_f = _icosphere()
            for k_, cl in enumerate(drops):
                m = lab == cl
                ctr = q[m].mean(0); vol_ = size[cl] * Vp
                rr_ = np.hypot(ctr[0], ctr[1]); gap = rcav(ctr[2]) - rr_
                if 0.0 < rr_ and gap < WALL_BAND and size[cl] < WALL_MIN:
                    continue                   # numerical splash residue stuck on the glass (see WALL_MIN)
                if 0.0 < rr_ and gap < WALL_BAND:
                    # a splash on the glass spreads into a flat spot: oblate drop, short axis along the wall normal,
                    # its back pushed into the glass
                    nrm_ = np.array([ctr[0] / rr_, ctr[1] / rr_, 0.0])
                    e1 = np.array([-nrm_[1], nrm_[0], 0.0]); e2 = np.array([0.0, 0.0, 1.0])
                    a_ = (3 * vol_ / (4 * np.pi * WALL_FLAT)) ** (1 / 3); c_ = WALL_FLAT * a_
                    ctr = ctr + nrm_ * (gap - 0.4 * c_)
                    M = np.stack([e1 * a_, e2 * a_, nrm_ * c_], 1)
                    dv.append(ctr + base_v @ M.T)
                    nn_ = base_v @ np.linalg.inv(M); nn_ /= np.linalg.norm(nn_, axis=1, keepdims=True)
                    dn.append(nn_)
                else:
                    rad = (3 * vol_ / (4 * np.pi)) ** (1 / 3)
                    dv.append(ctr + rad * base_v); dn.append(base_v.copy())
                df.append(base_f + len(df) * len(base_v))
                du.append(np.repeat(qv[m].mean(0)[None], len(base_v), 0))
            if dv:
                parts_v.append(np.concatenate(dv)); parts_f.append(np.concatenate(df)); parts_n.append(np.concatenate(dn))
                parts_u.append(np.concatenate(du))
        if keep.sum() > MIN_CLUSTER:
            mesh, _ = pysplashsurf.reconstruction_pipeline(q[keep], particle_radius=0.5 * d, smoothing_length=2.0,
                                                           cube_size=0.5, iso_surface_threshold=0.6,
                                                           mesh_smoothing_weights=True, mesh_smoothing_iters=25,
                                                           normals_smoothing_iters=10, mesh_cleanup=True,
                                                           compute_normals=True, multi_threading=True)
            sv = np.asarray(mesh.mesh.vertices, np.float64); sf = np.asarray(mesh.mesh.triangles, np.int64)
            sn = np.array(mesh.point_attributes["normals"], np.float64)
            if pm is not None and len(sv):
                rr = np.hypot(sv[:, 0], sv[:, 1])
                below = (rr < rcav(sv[:, 2]) + 0.001) & (sv[:, 2] < surface_at(pm[3], sv[:, :2]) - 0.0008)
                sf = sf[~below[sf].any(1)]
            if len(sf):
                used = np.unique(sf); remap = np.full(len(sv), -1); remap[used] = np.arange(len(used))
                dist, idx = cKDTree(q[keep]).query(sv[used], k=4)
                ww = 1.0 / np.maximum(dist, 1e-5); ww /= ww.sum(1, keepdims=True)
                parts_v.append(sv[used]); parts_f.append(remap[sf]); parts_n.append(sn[used])
                parts_u.append((qv[keep][idx] * ww[..., None]).sum(1))
    if not parts_v:
        np.savez(out / f"milk_{i+1:04d}.npz", **empty); continue
    offs = np.cumsum([0] + [len(v_) for v_ in parts_v[:-1]])
    np.savez(out / f"milk_{i+1:04d}.npz", vertices=np.concatenate(parts_v).astype(np.float32),
             triangles=np.concatenate([f_ + o for f_, o in zip(parts_f, offs)]).astype(np.int32),
             normals=np.concatenate(parts_n).astype(np.float32), velocity=np.concatenate(parts_u).astype(np.float32))
    rows.append({"frame": i + 1, "particles": n_act, "pool_particles": int(pool.sum()), "pool_level_mm": round(level * 1e3, 2),
                 "rest_particles": int(rest.sum())})
    if (i + 1) % 6 == 0 or len(only) < 8:
        print(rows[-1], f"{time.time() - t0:.0f}s", flush=True)
json.dump({"frames": sorted(only), "rows": rows, "seconds": round(time.time() - t0, 1),
           "settings": {"cell": CELL, "pool_band": POOL_BAND, "pool_fast": POOL_FAST, "smooth": SMOOTH, "seal": POOL_SEAL,
                        "min_cluster": MIN_CLUSTER, "drop_max": DROP_MAX, "wall_band": WALL_BAND, "wall_min": WALL_MIN, "wall_flat": WALL_FLAT}}, open(run / "surface_log.json", "w"))
print(f"surfaces done {time.time() - t0:.0f}s")
