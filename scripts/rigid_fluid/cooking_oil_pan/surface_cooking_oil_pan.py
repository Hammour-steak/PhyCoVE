"""Oil surface per frame: <run>/<mesh-dir>/oil_####.npz (pan-local coordinates).

The oil is a few particles thick everywhere: the stream is 1.2-4.6 mm wide (2.5-10 particles) and the puddle ~2 mm deep
(4 particles), so a particle-blob surface would show the particles. Both are rebuilt from the particles' volume instead:
- puddle (particles near the pan surface that are not falling): a volume-conserving height field - column volume /
  cell area, Gaussian-smoothed over SMOOTH - standing on the pan surface (pushed SEAL into it);
- stream (the other particles near its centreline): a thread whose cross-section at height z is the particle volume
  per unit height there, centred on the centroid, both averaged over STREAM_TAU of fall (see stream_tube); it reaches
  down into the puddle and joins it with a smooth union (a meniscus of width JOIN);
- smaller clusters: drops of equal volume.
Puddle and stream are one implicit field meshed by marching cubes on one lattice (two blocks that share the plane
between them), so the surface is closed, with no internal faces where the stream enters the puddle.
usage: python surface_cooking_oil_pan.py <run_dir> [--mesh-dir NAME] [--rope] [frame ...]"""
import json, sys, time
from pathlib import Path
import numpy as np
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
from skimage import measure

CELL = 0.2e-3                 # lattice spacing (m)
PUD_BAND = 0.006              # puddle particles: within this height of the pan surface ...
PUD_FAST = -0.4               # ... and not falling faster than this (m/s)
SMOOTH = 1.2e-3               # puddle height-field smoothing (Gaussian sigma)
H_MIN = 0.06e-3               # thinner smoothed columns are dry
SEAL = 0.15e-3                # the oil's underside is pushed this far into the pan
STREAM_MIN = 30               # clusters with fewer particles are drops
STREAM_MIN_LEN = 0.004        # ... or spanning less height
STREAM_TAU = 0.006            # stream area/centroid smoothing: sigma = 6 ms of fall (speed x 6 ms along z)
STREAM_SMOOTH_MIN = 0.6e-3    # ... but at least this
STREAM_CORRIDOR = 0.003       # particles this close to the stream's centreline belong to it
G_AXIAL = 9.81
R_MIN = 0.12e-3               # thinner stream sections are not drawn (thread broken)
JOIN = 0.8e-3                 # smooth-union width where the stream meets the puddle
MIN_DROP = 2                  # smaller clusters are not drawn
ROPE_MIN = 30                 # rope mode: smaller clusters are not drawn
ROPE_SEAL_BAND = 0.5e-3       # rope mode: downward-facing surface this close to the pan is pressed into it

HERE = Path(__file__).resolve().parent
run = Path(sys.argv[1]); opts = sys.argv[2:]
mesh_dir = "meshes"
if "--mesh-dir" in opts:
    k = opts.index("--mesh-dir"); mesh_dir = opts[k + 1]; del opts[k:k + 2]
ROPE = "--rope" in opts          # a very viscous oil: direct particle surface (see rope_mesh)
if ROPE:
    opts.remove("--rope")
out = run / mesh_dir; out.mkdir(exist_ok=True)
L = json.load(open(run / "sim_log.json")); d = L["args"]["particle"]; Vp = L["particle_volume_m3"]
P = np.load(run / "oil_pos.npy", mmap_mode="r"); V = np.load(run / "oil_vel_f16.npy", mmap_mode="r")
counts = np.load(run / "active.npy")
PAN = HERE / "geometry/pan_profile.npz"
if "--pan" in opts:                      # the support surface the run was simulated on (DELETE pan: the flat hob top)
    k = opts.index("--pan"); PAN = Path(opts[k + 1]); del opts[k:k + 2]
only = {int(a) for a in opts} or set(range(1, len(P) + 1))
prof = np.load(PAN); pr, pz = prof["r"], prof["z"]
Z_EXIT = float(L["args"]["exit"][2]); V_EXIT = float(L["exit_speed_m_s"])


def pan_z(x, y):
    return np.interp(np.hypot(x, y), pr, pz)


def smin(a, b, k):
    """smooth maximum of two inside-positive fields (polynomial smooth union)"""
    h = np.clip(0.5 + 0.5 * (a - b) / k, 0.0, 1.0)
    return b + (a - b) * h + k * h * (1.0 - h)


def lattice(lo, hi):
    i0 = np.floor(np.asarray(lo) / CELL).astype(int); i1 = np.ceil(np.asarray(hi) / CELL).astype(int)
    return [np.arange(i0[a], i1[a] + 1) * CELL for a in range(3)]


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


SPHERE_V, SPHERE_F = _icosphere()


def puddle_field(pos):
    """height field top(x, y) over a lattice block, or None"""
    if len(pos) < 20:
        return None
    pad = 4 * SMOOTH + 2 * CELL
    gx, gy, _ = lattice(np.r_[pos[:, :2].min(0) - pad, 0], np.r_[pos[:, :2].max(0) + pad, 0])
    ix = np.clip(np.round((pos[:, 0] - gx[0]) / CELL).astype(int), 0, len(gx) - 1)
    iy = np.clip(np.round((pos[:, 1] - gy[0]) / CELL).astype(int), 0, len(gy) - 1)
    h = np.zeros((len(gx), len(gy))); np.add.at(h, (ix, iy), Vp / CELL ** 2)
    h = ndimage.gaussian_filter(h, SMOOTH / CELL, mode="constant")
    wet = h > H_MIN
    h *= len(pos) * Vp / max((h * wet).sum() * CELL ** 2, 1e-18)     # the dry fringe's volume goes back into the puddle
    X, Y = np.meshgrid(gx, gy, indexing="ij")
    base = pan_z(X, Y)
    return dict(gx=gx, gy=gy, base=base, top=np.where(wet, base + h, -1.0), wet=wet)


def stream_tube(pos, z_exit, v_exit):
    """per-slice centre and radius of the stream on the z lattice. The cross-section is the particle volume per unit
    height, averaged over STREAM_TAU of fall: a stream 3 particles wide pinches into short segments that a continuous
    oil thread does not have, and the average over the segments is the thread's (it carries the same flux at the
    same speed). Near the opening the window is ~1 mm, at the pan ~12 mm; it is truncated at the stream's ends."""
    zl = np.arange(np.floor(pos[:, 2].min() / CELL) - 2, np.ceil(pos[:, 2].max() / CELL) + 3) * CELL
    k = np.clip(np.round((pos[:, 2] - zl[0]) / CELL).astype(int), 0, len(zl) - 1)
    n = np.bincount(k, minlength=len(zl)).astype(float)
    cx = np.bincount(k, pos[:, 0], len(zl)); cy = np.bincount(k, pos[:, 1], len(zl))
    speed = np.sqrt(v_exit ** 2 + 2 * G_AXIAL * np.clip(z_exit - zl, 0, None))
    sig = np.maximum(STREAM_TAU * speed, STREAM_SMOOTH_MIN)
    occ = np.where(n > 0)[0]; inside = (np.arange(len(zl)) >= occ.min()) & (np.arange(len(zl)) <= occ.max())
    W = np.exp(-0.5 * ((zl[None, :] - zl[:, None]) / sig[:, None]) ** 2) * inside[None, :]
    W /= np.maximum(W.sum(1, keepdims=True), 1e-12)
    a = (W @ n) * Vp / CELL * inside                                   # cross-section area (m^2)
    w = W @ n
    cx = (W @ cx) / np.maximum(w, 1e-9); cy = (W @ cy) / np.maximum(w, 1e-9)
    r = np.sqrt(np.maximum(a, 0) / np.pi)
    return zl, cx, cy, r


def tube_phi(t, X, Y, z):
    zl, cx, cy, r = t
    i = np.round((z - zl[0]) / CELL).astype(int)
    if i < 0 or i >= len(zl) or r[i] < R_MIN:
        return None
    return r[i] - np.hypot(X - cx[i], Y - cy[i])


def mc_block(phi, gx, gy, gz, open_top=False, open_bottom=False):
    phi = phi.astype(np.float32).copy()
    phi[0], phi[-1], phi[:, 0], phi[:, -1] = -1, -1, -1, -1
    if not open_bottom:
        phi[:, :, 0] = -1
    if not open_top:
        phi[:, :, -1] = -1
    if phi.max() <= 0:
        return np.zeros((0, 3)), np.zeros((0, 3), int)
    v, f, _, _ = measure.marching_cubes(phi, 0.0, spacing=(CELL, CELL, CELL))
    return v + np.array([gx[0], gy[0], gz[0]]), f[:, ::-1]


def weld(v, f):
    key = np.round(v / (CELL * 1e-3)).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    f = inv.reshape(-1)[f]
    f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
    return v[first], f


def vertex_normals(v, f):
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    n = np.zeros_like(v)
    for c in range(3):
        np.add.at(n, f[:, c], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)


def rope_mesh(pos, vel):
    """Direct particle surface for a very viscous oil. It lands in a coiling rope and a tall mound: neither a height
    field nor a stream averaged along z can represent the coils, but the rope is 5-8 particles wide and the particles
    keep an orderly arrangement at this viscosity, so a pysplashsurf surface is smooth. Its underside is pressed SEAL
    into the pan (no air film); clusters of fewer than ROPE_MIN particles are dropped."""
    import pysplashsurf
    pairs = cKDTree(pos).query_pairs(1.6 * d, output_type="ndarray")
    adj = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(pos), len(pos)))
    _, lab = connected_components(adj, directed=False)
    keep = np.bincount(lab)[lab] >= ROPE_MIN
    mesh, _ = pysplashsurf.reconstruction_pipeline(pos[keep], particle_radius=0.5 * d, smoothing_length=2.0, cube_size=1.0,
                                                   iso_surface_threshold=0.6, mesh_smoothing_weights=True,
                                                   mesh_smoothing_iters=25, normals_smoothing_iters=10, mesh_cleanup=True,
                                                   compute_normals=True, multi_threading=True)
    v = np.asarray(mesh.mesh.vertices, np.float64); f = np.asarray(mesh.mesh.triangles, np.int64)
    n = np.array(mesh.point_attributes["normals"], np.float64)
    zp = pan_z(v[:, 0], v[:, 1])
    low = (v[:, 2] - zp < ROPE_SEAL_BAND) & (n[:, 2] < 0.3)
    v[low, 2] = zp[low] - SEAL
    dist, idx = cKDTree(pos[keep]).query(v, k=6)
    w = 1.0 / np.maximum(dist, 1e-5); w /= w.sum(1, keepdims=True)
    u = (vel[keep][idx] * w[..., None]).sum(1)
    return v, f, n, u, {"kept_particles": int(keep.sum())}


def frame_mesh(pos, vel):
    zpan = pan_z(pos[:, 0], pos[:, 1])
    pud = (pos[:, 2] - zpan < PUD_BAND) & (vel[:, 2] > PUD_FAST)
    rest = np.where(~pud)[0]
    tubes, drops = [], []
    if len(rest):
        q = pos[rest]
        # the stream: particles near its centreline (per-5 mm median position, from the opening down)
        zb = np.floor(q[:, 2] / 0.005).astype(int)
        cl = {}
        for b in np.unique(zb):
            m = zb == b
            if m.sum() >= 3:
                cl[b] = np.median(q[m, :2], axis=0)
        in_stream = np.zeros(len(q), bool)
        if cl:
            bs = np.array(sorted(cl)); cxy = np.array([cl[b] for b in bs])
            zc = (bs + 0.5) * 0.005
            ctr = np.stack([np.interp(q[:, 2], zc, cxy[:, 0]), np.interp(q[:, 2], zc, cxy[:, 1])], 1)
            in_stream = np.hypot(*(q[:, :2] - ctr).T) < STREAM_CORRIDOR
            # only the part connected to the opening (the top of the particle set) by the median line counts
        if in_stream.sum() >= STREAM_MIN and np.ptp(q[in_stream, 2]) > STREAM_MIN_LEN:
            tubes.append(stream_tube(q[in_stream], Z_EXIT, V_EXIT))
        other = np.where(~in_stream)[0]
        if len(other):
            qo = q[other]
            pairs = cKDTree(qo).query_pairs(1.6 * d, output_type="ndarray")
            adj = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(qo), len(qo)))
            _, lab = connected_components(adj, directed=False)
            for c in np.unique(lab):
                m = lab == c
                if m.sum() >= MIN_DROP:
                    drops.append((qo[m].mean(0), m.sum() * Vp, vel[rest][other][m].mean(0)))
    pf = puddle_field(pos[pud])
    # tubes that reach the puddle continue down into it
    if pf is not None:
        for it_, t in enumerate(tubes):
            zl, cx, cy, r = t
            j = np.where(r >= R_MIN)[0]
            if len(j) and zl[j[0]] < PUD_BAND + 0.004:
                lo = j[0]
                r[:lo] = r[lo]; cx[:lo] = cx[lo]; cy[:lo] = cy[lo]
                zmin = float(pan_z(np.array([cx[lo]]), np.array([cy[lo]]))[0]) - SEAL
                if zl[0] > zmin:
                    ext = np.arange(np.floor(zmin / CELL), np.round(zl[0] / CELL)) * CELL
                    t_new = (np.r_[ext, zl], np.r_[np.full(len(ext), cx[lo]), cx], np.r_[np.full(len(ext), cy[lo]), cy],
                             np.r_[np.full(len(ext), r[lo]), r])
                    tubes[it_] = t_new
    parts = []
    z_split = None
    if pf is not None:
        gx, gy, base, top = pf["gx"], pf["gy"], pf["base"], pf["top"]
        z_split = np.ceil((top.max() + 0.0012) / CELL) * CELL
        gz = np.arange(np.floor((base.min() - SEAL - 2 * CELL) / CELL), np.round(z_split / CELL) + 1) * CELL
        X, Y = np.meshgrid(gx, gy, indexing="ij")
        phi = np.empty((len(gx), len(gy), len(gz)), np.float32)
        for kz, z in enumerate(gz):
            ph = np.minimum(top - z, z - (base - SEAL))
            for t in tubes:
                tp = tube_phi(t, X, Y, z)
                if tp is not None:
                    ph = smin(ph, tp, JOIN)
            phi[:, :, kz] = ph
        parts.append(mc_block(phi, gx, gy, gz, open_top=True))
    for t in tubes:
        zl, cx, cy, r = t
        ok = r >= R_MIN
        if not ok.any():
            continue
        zlo = zl[ok].min() if z_split is None else max(z_split, zl[ok].min() - 2 * CELL)
        zhi = zl[ok].max() + 2 * CELL
        if zhi <= zlo:
            continue
        sel = ok & (zl >= zlo - CELL) & (zl <= zhi)
        rm = r[sel].max() + 3 * CELL
        lo = (min(cx[sel].min(), cx[sel].max()) - rm, min(cy[sel].min(), cy[sel].max()) - rm, zlo)
        hi = (cx[sel].max() + rm, cy[sel].max() + rm, zhi)
        gx, gy, gz = lattice(lo, hi)
        if z_split is not None:
            gz = gz[gz >= z_split - 1e-9]
        X, Y = np.meshgrid(gx, gy, indexing="ij")
        phi = np.full((len(gx), len(gy), len(gz)), -1.0, np.float32)
        for kz, z in enumerate(gz):
            tp = tube_phi(t, X, Y, z)
            if tp is not None:
                phi[:, :, kz] = tp
        parts.append(mc_block(phi, gx, gy, gz, open_bottom=z_split is not None))
    pv = [p[0] for p in parts if len(p[1])]; pf_ = [p[1] for p in parts if len(p[1])]
    if pv:
        offs = np.cumsum([0] + [len(x) for x in pv[:-1]])
        v, f = weld(np.concatenate(pv), np.concatenate([x + o for x, o in zip(pf_, offs)]))
    else:
        v, f = np.zeros((0, 3)), np.zeros((0, 3), int)
    nrm = vertex_normals(v, f) if len(f) else np.zeros((0, 3))
    for c, vol, u in drops:
        rad = (3 * vol / (4 * np.pi)) ** (1 / 3)
        f = np.concatenate([f, SPHERE_F + len(v)]); v = np.concatenate([v, c + rad * SPHERE_V])
        nrm = np.concatenate([nrm, SPHERE_V])
    if len(v):
        dist, idx = cKDTree(pos).query(v, k=6)
        w = 1.0 / np.maximum(dist, 1e-5); w /= w.sum(1, keepdims=True)
        vel_v = (vel[idx] * w[..., None]).sum(1)
    else:
        vel_v = np.zeros((0, 3))
    info = {"puddle_particles": int(pud.sum()), "threads": len(tubes), "drops": len(drops),
            "puddle_area_cm2": round(float(pf["wet"].sum()) * CELL ** 2 * 1e4, 2) if pf is not None else 0.0,
            "puddle_max_mm": round(float((pf["top"] - pf["base"])[pf["wet"]].max()) * 1e3, 2) if pf is not None else 0.0}
    return v, f, nrm, vel_v, info


if __name__ == "__main__":
    t0 = time.time(); rows = []
    for i in range(len(P)):
        if i + 1 not in only:
            continue
        n_act = int(counts[i])
        if n_act < 2:
            np.savez(out / f"oil_{i+1:04d}.npz", vertices=np.zeros((0, 3), np.float32), triangles=np.zeros((0, 3), np.int32),
                     normals=np.zeros((0, 3), np.float32), velocity=np.zeros((0, 3), np.float32))
            continue
        pos = np.asarray(P[i, :n_act], np.float64); vel = np.asarray(V[i, :n_act], np.float32)
        v, f, nrm, vel_v, info = (rope_mesh if ROPE else frame_mesh)(pos, vel)
        np.savez(out / f"oil_{i+1:04d}.npz", vertices=v.astype(np.float32), triangles=f.astype(np.int32),
                 normals=nrm.astype(np.float32), velocity=vel_v.astype(np.float32))
        rows.append(dict(frame=i + 1, particles=n_act, vertices=len(v), **info))
        if (i + 1) % 6 == 0 or len(only) < 12:
            print(rows[-1], f"{time.time() - t0:.0f}s", flush=True)
    json.dump({"frames": sorted(only), "rows": rows, "seconds": round(time.time() - t0, 1),
               "settings": {"cell": CELL, "puddle_band": PUD_BAND, "puddle_fast": PUD_FAST, "smooth": SMOOTH, "h_min": H_MIN,
                            "seal": SEAL, "stream_min": STREAM_MIN, "stream_min_len": STREAM_MIN_LEN,
                            "rope": ROPE, "stream_tau": STREAM_TAU, "stream_corridor": STREAM_CORRIDOR, "r_min": R_MIN, "join": JOIN, "min_drop": MIN_DROP}},
              open(run / "surface_log.json", "w"))
    print(f"surfaces done {time.time() - t0:.0f}s")
