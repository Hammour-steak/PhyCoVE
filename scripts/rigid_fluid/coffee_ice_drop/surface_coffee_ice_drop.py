"""Coffee surface per frame for rendering.

usage: python surface_coffee_ice_drop.py <run_dir> [cube_size 0.6] [film contact angle deg 10] [temporal half-window 6]
Writes <run_dir>/surfaces/coffee_####.npz (surface + per-vertex velocity + drop films) and hold_plan.json.

- Isolated single particles (no other particle within one support radius, 2 particle sizes) get no surface.
- Particles resting outside the mug on the saucer or the table (slower than 5 cm/s, within 1.5 mm of the support) are
  grouped into connected clusters; each cluster of two or more particles is drawn as one wetting drop: a spherical cap
  with a small contact angle (default 10 degrees: a thin wetting film, conforming to the saucer slope) holding the cluster's liquid volume (n x 0.8 d^3), centred on the cluster. A 1 mm SPH
  particle pile would otherwise render as pepper-like beads.
- Everything else is meshed with splashsurf; vertices carry the inverse-distance-weighted particle velocity (m/s).
- Resting SPH particles jitter (median ~1 cm/s, ~0.1 mm per frame in a still cup), so a mirror-like coffee surface
  shimmers. Particles whose whole motion within +-TEMPORAL_K frames stays below JITTER_LO are meshed at their centred
  window mean (with the window's drift as blur velocity), blended out by JITTER_HI so waves and splash keep their own
  trajectories. Render-side only; the simulation data is untouched.
- Holds: stretches of at least 3 frames where the ice stays within +-0.1 mm and +-0.25 degrees and the meshed
  particles' window-mean trajectories keep 99.9 % within +-0.1 mm and every one within 1 mm are meshed once from their
  mean positions, at rest;
  hold_plan.json tells the renderer to draw each hold once and to cross-fade consecutive holds over 6 frames.
"""
import json, shutil, sys, time
from pathlib import Path
import numpy as np
import pysplashsurf
import trimesh
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

run = Path(sys.argv[1]); cube = float(sys.argv[2]) if len(sys.argv) > 2 else 0.6
L = json.load(open(run / "sim_log.json"))
geom_dir = Path(L["args"]["geom"]); geom_dir = geom_dir if geom_dir.is_absolute() else run.parent.parent / geom_dir
cx, cy = json.load(open(geom_dir / "geom_info.json"))["cup_center_xy"]
cav = json.load(open(geom_dir / "cavity.json"))
saucer = trimesh.load(geom_dir / "saucer_solid.obj")
CAV_PROF = np.array(cav["profile_z_rmin_rmedian"])
TABLE_Z = 0.79916
P = np.load(run / "coffee_pos_f16.npy"); V = np.load(run / "coffee_vel_f16.npy")
TEMPORAL_K = int(sys.argv[4]) if len(sys.argv) > 4 else 6
JITTER_LO, JITTER_HI = 0.4e-3, 1.0e-3  # m: window motion amplitude treated as pure jitter / as real motion


def _window(f):
    lo, hi = max(0, f - TEMPORAL_K), min(len(P), f + TEMPORAL_K + 1)
    k = min(f - lo, hi - 1 - f)                    # symmetric window: no lag
    return P[f - k:f + k + 1].astype(np.float64), k


def _jitter_weight(Wn):
    """1 where a particle's whole motion inside the window is below JITTER_LO (resting jitter), 0 above JITTER_HI
    (sloshing waves, splash and the sinking ice's surroundings keep their own trajectory)."""
    amp = (Wn.max(axis=0) - Wn.min(axis=0)).max(axis=1)
    return np.clip((JITTER_HI - amp) / (JITTER_HI - JITTER_LO), 0.0, 1.0)[:, None]


def denoised_positions(f):
    raw = P[f].astype(np.float64)
    if TEMPORAL_K <= 0:
        return raw
    Wn, k = _window(f)
    if k == 0:
        return raw
    w = _jitter_weight(Wn)
    return w * Wn.mean(axis=0) + (1 - w) * raw


def denoised_velocity(f):
    """Motion-blur velocity: jittering particles get the window's mean drift instead of their random jitter velocity
    (which smears the mirror reflections in a new direction every frame)."""
    raw = V[f].astype(np.float32)
    if TEMPORAL_K <= 0:
        return raw
    Wn, k = _window(f)
    if k == 0:
        return raw
    drift = ((Wn[-1] - Wn[0]) / (2 * k / L["args"]["fps"])).astype(np.float32)
    w = _jitter_weight(Wn).astype(np.float32)
    return w * drift + (1 - w) * raw
d = L["args"]["particle"]; r = d / 2; vol_p = 0.8 * d ** 3
CUP_R = 0.0365
THETA = np.radians(float(sys.argv[3]) if len(sys.argv) > 3 else 10.0)  # contact angle of a coffee film on glaze / finished wood
cap_k = np.pi * (1 - np.cos(THETA)) / np.sin(THETA) * (3 + ((1 - np.cos(THETA)) / np.sin(THETA)) ** 2) / 6  # V = cap_k a^3


def support_z(xy):
    z = np.full(len(xy), TABLE_Z)
    if len(xy):
        origins = np.column_stack([xy, np.full(len(xy), 0.9)])
        loc, idx, _ = saucer.ray.intersects_location(origins, np.tile([0, 0, -1.0], (len(xy), 1)), multiple_hits=False)
        if len(idx):
            z[idx] = np.maximum(z[idx], np.asarray(loc).reshape(-1, 3)[:, 2])
    return z


def cap_mesh(center, volume, rings=6, segs=24):
    """Spherical-cap film of `volume` laid on the support: each top vertex sits at support(x, y) + cap height(rho)."""
    a = (volume / cap_k) ** (1 / 3)
    R = a / np.sin(THETA)
    rho = a * np.arange(rings + 1) / rings
    top = [np.array([center[0], center[1]])]
    rr = [0.0]
    for i in range(1, rings + 1):
        for j in range(segs):
            t = 2 * np.pi * j / segs
            top.append(center + rho[i] * np.array([np.cos(t), np.sin(t)])); rr.append(rho[i])
    top = np.array(top); rr = np.array(rr)
    hz = np.sqrt(np.maximum(R ** 2 - rr ** 2, 0)) - R * np.cos(THETA)
    sz = support_z(top)
    verts = np.column_stack([top, sz + hz + 0.00003])
    faces = [[0, 1 + j, 1 + (j + 1) % segs] for j in range(segs)]
    for i in range(rings - 1):
        a0, b0 = 1 + i * segs, 1 + (i + 1) * segs
        for j in range(segs):
            k = (j + 1) % segs
            faces += [[a0 + j, b0 + j, b0 + k], [a0 + j, b0 + k, a0 + k]]
    base = len(verts); last = 1 + (rings - 1) * segs
    verts = np.vstack([verts, [center[0], center[1], sz[0] - 0.0001]])
    faces += [[base, last + (j + 1) % segs, last + j] for j in range(segs)]
    return verts, np.array(faces)


def smooth_near_ice(v, t, n, pose, band=0.007, iters=60):
    """Taubin-smooth the liquid surface within `band` of the ice (weight fading to 0 at the band edge): the particle
    layers touching the ice boundary are disordered and their 0.2-0.4 mm bumps glint; a real meniscus is smooth."""
    if pose is None:
        return v, n
    from scipy.spatial.transform import Rotation
    import scipy.sparse as sp_
    q = pose["quat_wxyz"]
    loc = Rotation.from_quat([q[1], q[2], q[3], q[0]]).inv().apply(v - np.array(pose["pos"]) - [cx, cy, 0])
    dq = np.abs(loc) - L["args"]["ice_side"] / 2
    sd = np.linalg.norm(np.maximum(dq, 0), axis=1) + np.minimum(dq.max(1), 0)
    w = np.clip(1.0 - sd / band, 0.0, 1.0)
    if not (w > 0).any():
        return v, n
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    A = sp_.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(v), len(v))).tocsr()
    A = ((A + A.T) > 0).astype(np.float64)
    deg = np.asarray(A.sum(1)).ravel(); deg[deg == 0] = 1
    v = v.copy()
    for k in range(iters):
        lam = 0.5 if k % 2 == 0 else -0.53
        v += (lam * w)[:, None] * (A @ v / deg[:, None] - v)
    # shading uses stored normals: recompute them from the smoothed geometry inside the band
    gn = trimesh.Trimesh(v, t, process=False).vertex_normals
    n = n.copy(); sel = w > 0
    n[sel] = (w[sel, None] * gn[sel] + (1 - w[sel, None]) * n[sel])
    n[sel] /= np.linalg.norm(n[sel], axis=1, keepdims=True) + 1e-12
    return v, n.astype(np.float32)


HOLD_EPS_T, HOLD_EPS_A, HOLD_MIN, HOLD_FADE = 0.1e-3, 0.25, 3, 6   # m, deg (~0.4 px), shortest hold, cross-fade frames
HOLD_MAX_C = 1.0e-3   # m: a single meshed particle may jitter this much inside a hold (it is drawn at its mean)
HOLD_FLIPS = 5        # particles that may change between isolated / landed / meshed inside a hold (drawn as at its start)

out = run / "surfaces"; out.mkdir(exist_ok=True)
log = {"isolation_radius_m": 2 * d, "drop_contact_angle_deg": float(np.degrees(THETA)), "frames": []}
t0 = time.time()
n_f, n_p = len(P), P.shape[1]
PIN_DROPS = True

# pass 1: per-frame render positions (denoised, landed drops pinned) and the landed / isolated sets
pos_all = np.zeros((n_f, n_p, 3), np.float32); vel_all = np.zeros((n_f, n_p, 3), np.float32)
landed_all = np.zeros((n_f, n_p), bool); lone_all = np.zeros((n_f, n_p), bool)
was_landed = np.zeros(n_p, bool)
landing_pos = np.zeros((n_p, 3))
for f in range(n_f if n_p else 0):
    pos = denoised_positions(f); pos[:, 2] += L["z_offset"]; vel = denoised_velocity(f)
    nn, _ = cKDTree(pos).query(pos, k=2)
    lone = nn[:, 1] > 2 * d
    rad = np.hypot(pos[:, 0], pos[:, 1]); speed = np.linalg.norm(vel, axis=1)
    # landed = resting on the saucer/table. Sticky (hysteresis): a drop that has landed stays a film while it hugs the
    # surface and moves slower than 0.3 m/s (sliding included); otherwise one noisy frame turns its film back into a
    # 2 mm bead and the drop visibly shrinks for that frame.
    # outside the cup = not inside the measured cavity (the cup's outer wall narrows to ~22 mm at its foot, so a fixed
    # radius test turned drops running down the outside into "in the cup" beads half-way down)
    in_cavity = (rad < np.interp(pos[:, 2], CAV_PROF[:, 0], CAV_PROF[:, 1])) & (pos[:, 2] > cav["inner_floor_z"] - 0.001)
    cand = np.where(~in_cavity & (pos[:, 2] < 0.822))[0]
    landed = np.zeros(len(pos), bool)
    if len(cand):
        h = pos[cand, 2] - support_z(pos[cand, :2])
        now = (speed[cand] < 0.05) & (h < 0.0015)
        keep = was_landed[cand] & (speed[cand] < 0.3) & (h < 0.004)
        landed[cand[now | keep]] = True
    # pin: a landed particle is drawn where it landed (a few-microlitre coffee drop stays pinned on glaze or wood by
    # contact-angle hysteresis; the 1 mm SPH drops creep down the saucer slope instead)
    fresh = landed & ~was_landed
    landing_pos[fresh] = pos[fresh]
    if PIN_DROPS:
        pos[landed] = landing_pos[landed]
    was_landed = landed.copy()
    pos_all[f], vel_all[f], landed_all[f], lone_all[f] = pos, vel, landed, lone

# pass 2: holds. A path-traced frame redraws its Monte Carlo noise wherever geometry moves, however little, while the
# static scene keeps one seed and one noise pattern; the clear ice and the scattering coffee are noisy enough at 128
# samples that sub-pixel motion (a settled or creeping ice and the liquid around it) reads as boiling. Where the ice
# stays within +-HOLD_EPS_T and +-HOLD_EPS_A, and the meshed particles' +-TEMPORAL_K-frame mean trajectories (their
# resting jitter averaged out) keep 99.9 % within +-HOLD_EPS_T (no sloshing) and every one within HOLD_MAX_C (no
# sliding drop), with at most HOLD_FLIPS particles changing between isolated, landed and meshed, for HOLD_MIN frames
# or more, the stretch is drawn once from its mean state; the renderer cross-fades consecutive holds over HOLD_FADE
# frames.
ice = L["ice_pose"]
if ice:
    IP = np.array([q["pos"] for q in ice]); IQ = np.array([q["quat_wxyz"] for q in ice])
    for i in range(1, n_f):
        if IQ[i] @ IQ[i - 1] < 0: IQ[i] = -IQ[i]
    # the ice holds if its raw or its window-mean pose stays put (the floating ice wobbles ~0.08 deg per frame; right
    # after an impact the window mean still holds the fall)
    win = [slice(max(0, i - TEMPORAL_K), min(n_f, i + TEMPORAL_K + 1)) for i in range(n_f)]
    SP_ = np.array([IP[w].mean(0) for w in win]); SQ = np.array([IQ[w].mean(0) for w in win])
    SQ /= np.linalg.norm(SQ, axis=1, keepdims=True)
ang = lambda a, b: np.degrees(2 * np.arccos(np.clip(abs(a @ b), 0, 1)))
if n_p:  # window-mean trajectories for the hold test (landed particles stay pinned)
    csum = np.concatenate([np.zeros((1, n_p, 3)), np.cumsum(pos_all, axis=0, dtype=np.float64)])
    smooth = np.empty_like(pos_all)
    for i in range(n_f):
        lo_, hi_ = max(0, i - TEMPORAL_K), min(n_f, i + TEMPORAL_K + 1)
        smooth[i] = (csum[hi_] - csum[lo_]) / (hi_ - lo_)
        smooth[i][landed_all[i]] = pos_all[i][landed_all[i]]
    del csum
segs, f = [], 0
while f < n_f:
    g = f
    if n_p:
        lo = smooth[f].copy(); hi = lo.copy(); body = ~landed_all[f] & ~lone_all[f]
    while g + 1 < n_f:
        h = g + 1
        if ice and not any((X[f:h + 1].max(0) - X[f:h + 1].min(0)).max() <= 2 * HOLD_EPS_T
                           and max(ang(Y[i], Y[j]) for i in (f, h) for j in range(f, h + 1)) <= 2 * HOLD_EPS_A
                           for X, Y in ((IP, IQ), (SP_, SQ))):
            break
        if n_p:
            if ((landed_all[h] != landed_all[f]) | (lone_all[h] != lone_all[f])).sum() > HOLD_FLIPS:
                break
            nlo = np.minimum(lo, smooth[h]); nhi = np.maximum(hi, smooth[h])
            if body.any():
                rng = (nhi - nlo)[body].max(1)
                if rng.max() > HOLD_MAX_C or np.partition(rng, int(0.999 * (len(rng) - 1)))[int(0.999 * (len(rng) - 1))] > 2 * HOLD_EPS_T:
                    break
            lo, hi = nlo, nhi
        g = h
    if g - f + 1 >= (HOLD_MIN if g + 1 < n_f else 2):   # the clip's last two frames may hold too
        segs.append((f, g))
    f = g + 1
seg_of = {i: k for k, (a, b) in enumerate(segs) for i in range(a, b + 1)}
held_pose = []
for a, b in segs:
    if ice:
        qm = IQ[a:b + 1].mean(0); qm /= np.linalg.norm(qm)
        held_pose.append({"pos": IP[a:b + 1].mean(0).tolist(), "quat_wxyz": qm.tolist()})
    else:
        held_pose.append(None)
plan = {"hold_tolerance_m": HOLD_EPS_T, "hold_tolerance_deg": HOLD_EPS_A, "fade_frames": HOLD_FADE,
        "segments": [{"first": a + 1, "last": b + 1, "ice_pose": held_pose[k]} for k, (a, b) in enumerate(segs)],
        "frames": [[[1.0, f"seg{seg_of[i]}" if i in seg_of else f"frame{i + 1}"]] for i in range(n_f)]}
for k in range(len(segs) - 1):
    (a0, a1), (b0, b1) = segs[k], segs[k + 1]
    if b0 != a1 + 1:
        continue  # a moving stretch in between: no fade
    m = min(HOLD_FADE // 2, a1 - a0 + 1, b1 - b0 + 1)
    for j, i in enumerate(range(b0 - m, b0 + m)):
        w = (j + 1) / (2 * m + 1)
        plan["frames"][i] = [[1 - w, f"seg{k}"], [w, f"seg{k + 1}"]]
json.dump(plan, open(out / "hold_plan.json", "w"), indent=1)
print(f"holds: {len(segs)} segments over {len(seg_of)} of {n_f} frames", flush=True)

# pass 3: surfaces (a hold is meshed once, from its mean positions, at rest)
for f in range(n_f):
    k = seg_of.get(f)
    if n_p == 0:  # DELETE coffee: nothing to mesh
        e3 = np.zeros((0, 3), np.float32)
        np.savez(out / f"coffee_{f+1:04d}.npz", vertices=e3, triangles=np.zeros((0, 3), np.int32), normals=e3, velocity=e3,
                 drops_vertices=e3, drops_triangles=np.zeros((0, 3), np.int32))
        log["frames"].append({"frame": f + 1, "isolated_not_meshed": 0, "landed_particles": 0, "drops": 0})
        continue
    if k is not None and f != segs[k][0]:
        shutil.copyfile(out / f"coffee_{segs[k][0]+1:04d}.npz", out / f"coffee_{f+1:04d}.npz")
        log["frames"].append({**log["frames"][segs[k][0]], "frame": f + 1})
        continue
    if k is not None:
        a, b = segs[k]
        pos = pos_all[a:b + 1].astype(np.float64).mean(0); vel = np.zeros((n_p, 3), np.float32)
        landed, lone, pose = landed_all[a], lone_all[a], held_pose[k]
    else:
        pos = pos_all[f].astype(np.float64); vel = vel_all[f]
        landed, lone, pose = landed_all[f], lone_all[f], (ice[f] if ice else None)
    dv, dt_ = [], []
    li = np.where(landed)[0]
    if len(li):
        pairs = cKDTree(pos[li]).query_pairs(1.6 * d, output_type="ndarray")
        import scipy.sparse as sp
        g = sp.coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(li), len(li)))
        ncomp, lab = connected_components(g, directed=False)
        for c in range(ncomp):
            m = li[lab == c]
            if len(m) < 2:
                continue
            ctr = pos[m, :2].mean(0)
            vv, tt = cap_mesh(ctr, len(m) * vol_p)
            dt_.append(tt + sum(len(x) for x in dv)); dv.append(vv)
    body = ~landed & ~lone
    mesh, _ = pysplashsurf.reconstruction_pipeline(pos[body], particle_radius=r, smoothing_length=2.0, cube_size=cube,
                                                   iso_surface_threshold=0.6, mesh_smoothing_weights=True,
                                                   mesh_smoothing_iters=25, normals_smoothing_iters=10, mesh_cleanup=True,
                                                   compute_normals=True, multi_threading=True)
    v = np.asarray(mesh.mesh.vertices, np.float64); t = np.asarray(mesh.mesh.triangles, np.int32)
    n = np.array(mesh.point_attributes["normals"], np.float32)
    dist, idx = cKDTree(pos[body]).query(v, k=4)
    w = 1.0 / np.maximum(dist, 1e-5); w /= w.sum(1, keepdims=True)
    vvel = (vel[body][idx] * w[..., None]).sum(1).astype(np.float32)
    v[:, 0] += cx; v[:, 1] += cy
    v, n = smooth_near_ice(v, t, n, pose)
    drops_v = (np.concatenate(dv) + [cx, cy, 0]).astype(np.float32) if dv else np.zeros((0, 3), np.float32)
    drops_t = np.concatenate(dt_).astype(np.int32) if dt_ else np.zeros((0, 3), np.int32)
    np.savez(out / f"coffee_{f+1:04d}.npz", vertices=v.astype(np.float32), triangles=t, normals=n, velocity=vvel,
             drops_vertices=drops_v, drops_triangles=drops_t)
    log["frames"].append({"frame": f + 1, "isolated_not_meshed": int((lone & ~landed).sum()), "landed_particles": int(landed.sum()),
                          "drops": len(dv)})
    if f % 12 == 0:
        print(f"frame {f+1}: {(lone & ~landed).sum()} isolated hidden, {landed.sum()} landed -> {len(dv)} drops  {time.time()-t0:.0f}s", flush=True)
log["holds"] = {"segments": len(segs), "held_frames": len(seg_of)}
json.dump(log, open(run / "surface_log.json", "w"), indent=1)
print(f"surface done {time.time()-t0:.0f}s; drops at end {log['frames'][-1]['drops']}")
