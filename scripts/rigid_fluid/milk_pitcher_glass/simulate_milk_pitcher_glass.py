"""Milk poured from a carton spout into a glass cup: Genesis 1.4.3 DFSPH at 1 mm.

The glass cup (4 mm walls, closed solid) and the worktop are static ghost-particle boundaries that carry their own
pressure (split density solve, coupling_milk_pitcher_glass.py); Akinci surface tension scaled to milk (0.046 N/m); the glass and the
oak are wetted. Milk enters from the carton's spout: from --start on, every 1/rate seconds a disc of particles on the
rest lattice (radius --jet-radius, normal to the spout axis) is activated at the spout exit with the exit speed along
the axis, so the volume flow is exactly --flow. All particles are preallocated and parked inactive until emitted.
--stop ends the pour; --resume-from/--resume-frame continue a source run from its frame-F state (timed edits).
Writes milk_pos.npy (float32), milk_vel_f16.npy, active.npy (active count per frame), sim_log.json.
usage: <genesis python> simulate_milk_pitcher_glass.py --out RUN [--flow M3_S] [--stop S] [--resume-from SRC --resume-frame F]"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'simulate')
# PCVE_UNIFIED_ENTRY_END
import argparse, json, math, sys, time
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ap = argparse.ArgumentParser()
ap.add_argument("--out", type=Path, required=True)
ap.add_argument("--cup", type=Path, default=HERE / "geometry/glass_cup.npz")
ap.add_argument("--particle", type=float, default=0.001)
ap.add_argument("--rest-spacing", type=float, default=0.93)
ap.add_argument("--frames", type=int, default=96)
ap.add_argument("--fps", type=int, default=24)
ap.add_argument("--steps-per-frame", type=int, default=10)
ap.add_argument("--substeps", type=int, default=32, help="16 is unstable at the 2-4 m/s impact spray")
ap.add_argument("--mu", type=float, default=2.2e-6, help="milk kinematic viscosity (m^2/s)")
ap.add_argument("--surface-tension", type=float, default=0.96, help="Akinci gamma (1.5 = 0.072 N/m at 1 mm)")
ap.add_argument("--flow", type=float, default=75e-6, help="volume flow (m^3/s)")
ap.add_argument("--start", type=float, default=0.25, help="pour start (s)")
ap.add_argument("--stop", type=float, default=1e9, help="pour stop (s)")
ap.add_argument("--exit", type=float, nargs=3, default=(-0.0345, 0.005, 0.160), help="spout exit centre (m)")
ap.add_argument("--axis", type=float, nargs=3, default=(0.70711, 0.0, -0.70711), help="spout axis")
ap.add_argument("--jet-radius", type=float, default=0.008)
ap.add_argument("--cl-friction", type=float, default=1000.0, help="contact-line friction on the oak (1/s)")
ap.add_argument("--div-iters", type=int, default=10)
ap.add_argument("--resume-from", type=Path, help="run whose frame --resume-frame state this run continues from")
ap.add_argument("--resume-frame", type=int, default=0, help="frames up to this one are copied from --resume-from")
args = ap.parse_args()
args.out.mkdir(parents=True, exist_ok=True)
d = args.particle; sp = args.rest_spacing * d
FOOT = (0.0304, 0.043, 0.0036)                     # glass foot ring sealed to the worktop: r from, r to, z below
V = 0.8 * d ** 3                                   # Genesis SPH particle volume


def lattice(lo, hi):
    ax = [np.arange(math.floor(lo[i] / sp), math.ceil(hi[i] / sp) + 1) for i in range(3)]
    I = np.stack(np.meshgrid(*ax, indexing="ij"), -1).reshape(-1, 3)
    return I, (I + 0.5) * sp


# ---- glass ghosts: lattice nodes inside the closed glass solid (signed distance from dense surface samples)
cup = np.load(args.cup); cv, cf = cup["vertices"], cup["triangles"]
a, b, c = cv[cf[:, 0]], cv[cf[:, 1]], cv[cf[:, 2]]
fn = np.cross(b - a, c - a); area = 0.5 * np.linalg.norm(fn, axis=1); fn /= np.maximum(2 * area, 1e-20)[:, None]
vol = np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0
if vol < 0:
    fn = -fn                                       # outward normals
rng = np.random.default_rng(1)
n_s = np.maximum(1, (area / (0.00025 ** 2)).astype(int))
tri = np.repeat(np.arange(len(cf)), n_s)
u, w = rng.random(len(tri)), rng.random(len(tri)); flip = u + w > 1; u[flip], w[flip] = 1 - u[flip], 1 - w[flip]
samples = a[tri] + u[:, None] * (b - a)[tri] + w[:, None] * (c - a)[tri]
tree = cKDTree(samples)
Ig, Pg = lattice(cv.min(0) - 0.002, cv.max(0) + 0.002)
dist, idx = tree.query(Pg)
signed = np.einsum("ij,ij->i", Pg - samples[idx], fn[tri[idx]])
inside = signed < 0
# The visual glass has a 0.1 mm base (outer bottom z = 0.2 mm, inner floor z = 0.3 mm): the milk rests on the worktop
# ghosts, but the solid wall only starts ~2 mm up, which would leave a gap under the foot. Seal the foot ring to the
# worktop: nodes below the wall's solid start, between the inner floor's edge and the foot's outer edge.
r_node, z_node = np.hypot(Pg[:, 0], Pg[:, 1]), Pg[:, 2]
foot = (z_node > 0) & (z_node < FOOT[2]) & (r_node > FOOT[0]) & (r_node < FOOT[1])
g_cup = Ig[inside | foot]
# ---- worktop ghosts: three rows under z = 0
It, Pt = lattice((-0.12, -0.12, -3 * sp), (0.12, 0.12, -0.5 * sp))
g_tab = It[Pt[:, 2] < 0]
keys = {}
for idx_, kind in ((g_cup, "glass"), (g_tab, "oak")):
    for row in map(tuple, idx_):
        keys.setdefault(row, kind)
GI = np.array(list(keys)); ghost = (GI + 0.5) * sp
kinds = np.array(list(keys.values()))
wet = np.ones(len(ghost))
cl = np.where(kinds == "oak", args.cl_friction, 0.0)

# ---- emitter: disc on the rest lattice normal to the spout axis
E, A = np.array(args.exit), np.array(args.axis) / np.linalg.norm(args.axis)
U = np.array([0.0, 1.0, 0.0]); W = np.cross(A, U); W /= np.linalg.norm(W)
k = int(math.ceil(args.jet_radius / sp))
disc = np.array([(i * sp, j * sp) for i in range(-k, k + 1) for j in range(-k, k + 1)
                 if (i * sp) ** 2 + (j * sp) ** 2 <= args.jet_radius ** 2])
disc = disc[:, :1] * U + disc[:, 1:] * W
area_eff = len(disc) * sp * sp
speed = args.flow / area_eff                       # layers of the disc every sp/speed seconds give exactly --flow
rate = speed / sp
t_end = args.frames / args.fps
n_layers = int(max(0.0, min(args.stop, t_end) - args.start) * rate) + 2
N = n_layers * len(disc)
print(f"glass ghosts {len(g_cup)} ({int((foot & ~inside).sum())} foot seal), oak ghosts {len(g_tab)}; emitter disc {len(disc)} particles, exit speed {speed:.3f} m/s, "
      f"{rate:.0f} layers/s, {N} milk particles ({N * V * 1e6:.0f} mL)", flush=True)

import genesis as gs
gs.init(backend=gs.cuda, precision="32", seed=20261031, logging_level="warning")
import pcve_dfsph_patches as dfsph
import coupling_milk_pitcher_glass as coupling
import genesis.engine.simulator as simulator
dfsph.install_dfsph_gravity_fix(); dfsph.install_quiet(0.0, "position", 20)
dfsph.install_surface_tension(args.surface_tension)
simulator.SPHSolver = coupling.make_solver()
dt = 1.0 / args.fps / args.steps_per_frame
lo, hi = (-0.118, -0.118, -0.004), (0.118, 0.118, 0.20)
scene = gs.Scene(
    sim_options=gs.options.SimOptions(dt=dt, substeps=args.substeps, gravity=(0, 0, -9.81)),
    sph_options=gs.options.SPHOptions(particle_size=d, pressure_solver="DFSPH", max_density_error_percent=0.005,
                                      max_divergence_error=0.02, max_divergence_solver_iterations=args.div_iters,
                                      max_density_solver_iterations=1000, lower_bound=lo, upper_bound=hi),
    rigid_options=gs.options.RigidOptions(enable_collision=False),
    coupler_options=gs.options.LegacyCouplerOptions(rigid_sph=True, rigid_mpm=False, rigid_pbd=False, rigid_fem=False,
                                                    mpm_sph=False, mpm_pbd=False, fem_mpm=False, fem_sph=False),
    show_viewer=False)
carrier = scene.add_entity(gs.morphs.Box(pos=(0.0, 0.0, 0.05), size=(0.01, 0.01, 0.01), fixed=True),
                           material=gs.materials.Rigid(needs_coup=False))
milk = scene.add_entity(gs.morphs.Nowhere(n_particles=N),
                        material=gs.materials.SPH.Liquid(rho=1030.0, mu=args.mu, gamma=0.0, sampler="regular"))
gho = scene.add_entity(gs.morphs.Nowhere(n_particles=len(ghost)),
                       material=gs.materials.SPH.Liquid(rho=1030.0, mu=args.mu, gamma=0.0, sampler="regular"))
coupling.CONFIG.update(n_fluid=N, ghost_local=ghost, ghost_psi=np.full(len(ghost), V), link_idx=carrier.links[0].idx,
                       implicit_nu=0.0, ice_mass=1.0, ice_inertia=1.0, ghost_fixed=True, max_density_error_max=0.01,
                       max_divergence_error_max=1e9, ghost_wetting=wet, ghost_noslip=True,
                       ghost_viscosity_factor=np.ones(len(ghost)), contact_line_friction=cl)
t0 = time.perf_counter(); scene.build(); t_build = time.perf_counter() - t0
sph = scene.sim.sph_solver
from scipy.spatial.transform import Rotation
ls = scene.sim.rigid_solver.dyn_state.links; li = carrier.links[0].idx
lp = ls.pos.to_numpy()[li].reshape(-1)[:3]; lq = ls.quat.to_numpy()[li].reshape(-1)[:4]
sph.g_local.from_numpy(Rotation.from_quat([lq[1], lq[2], lq[3], lq[0]]).inv().apply(ghost - lp).astype(np.float32))
park = np.tile(np.array([0.11, 0.11, 0.19], np.float32), (N, 1)) + (np.arange(N) % 7)[:, None].astype(np.float32) * 1e-4
milk.set_particles_pos(park); milk.set_particles_vel(np.zeros((N, 3), np.float32))
milk.set_particles_active(np.zeros(N, bool))
gho.set_particles_pos(ghost.astype(np.float32)); gho.set_particles_vel(np.zeros((len(ghost), 3), np.float32))
gho.set_particles_active(np.ones(len(ghost), bool))

import torch
emitted = 0                                        # layers
rec_p, rec_v, rec_n, rows = [], [], [], []
t_sim = time.perf_counter()
step_dt = dt
time_now = 0.0
first = 1
if args.resume_from:
    # an edit that starts at --resume-frame: frames 1..F are the source's, the solve continues from its frame-F state
    F = args.resume_frame
    srcP = np.load(args.resume_from / "milk_pos.npy", mmap_mode="r"); srcV = np.load(args.resume_from / "milk_vel_f16.npy", mmap_mode="r")
    srcN = np.load(args.resume_from / "active.npy"); src_log = json.load(open(args.resume_from / "sim_log.json"))
    for k_ in ("exit", "axis", "jet_radius", "flow", "start", "particle", "rest_spacing", "steps_per_frame", "substeps", "fps"):
        assert src_log["args"][k_] == getattr(args, k_.replace("-", "_")) or list(src_log["args"][k_]) == list(getattr(args, k_)), k_
    for i_ in range(F):
        n_ = int(srcN[i_]); rec_p.append(np.asarray(srcP[i_, :n_], np.float32)); rec_v.append(np.asarray(srcV[i_, :n_], np.float16))
        rec_n.append(n_); rows.append(dict(src_log["frames"][i_], copied_from_source=True))
    n0 = rec_n[-1]
    assert n0 % len(disc) == 0
    emitted = n0 // len(disc)
    ids = torch.arange(0, n0, device=gs.device, dtype=gs.tc_int)
    milk.set_particles_pos(torch.as_tensor(rec_p[-1], device=gs.device), ids)
    milk.set_particles_vel(torch.as_tensor(rec_v[-1].astype(np.float32), device=gs.device), ids)
    milk.set_particles_active(torch.ones(n0, dtype=torch.bool, device=gs.device), ids)
    time_now = (F - 1) / args.fps
    first = F + 1
    print(f"resumed from {args.resume_from} frame {F}: {n0} particles, {emitted} layers, t = {time_now:.4f} s", flush=True)
for f in range(first, args.frames + 1):
    if f > 1:
        for _ in range(args.steps_per_frame):
            # layers whose emission time falls in this step start behind the exit and reach it during the step
            new = []
            while emitted < n_layers:
                t_e = args.start + emitted / rate
                if t_e >= time_now + step_dt or t_e >= args.stop:
                    break
                new.append((emitted, t_e)); emitted += 1
            if new:
                lo_i = new[0][0] * len(disc); hi_i = (new[-1][0] + 1) * len(disc)
                pos = np.concatenate([E + disc - A * speed * (t_e - time_now) for _, t_e in new]).astype(np.float32)
                ids = torch.arange(lo_i, hi_i, device=gs.device, dtype=gs.tc_int)
                milk.set_particles_pos(torch.as_tensor(pos, device=gs.device), ids)
                milk.set_particles_vel(torch.as_tensor(np.tile(A * speed, (len(pos), 1)).astype(np.float32), device=gs.device), ids)
                milk.set_particles_active(torch.ones(len(pos), dtype=torch.bool, device=gs.device), ids)
            scene.step()
            time_now += step_dt
    n = emitted * len(disc)
    p = milk.get_particles_pos().cpu().numpy().reshape(-1, 3)[:n]
    v = milk.get_particles_vel().cpu().numpy().reshape(-1, 3)[:n]
    if not (np.isfinite(p).all() and np.isfinite(v).all()):
        raise RuntimeError(f"non-finite state at frame {f}")
    rec_p.append(p.astype(np.float32)); rec_v.append(v.astype(np.float16)); rec_n.append(n)
    s = np.linalg.norm(v, axis=1) if n else np.zeros(1)
    r = np.hypot(p[:, 0], p[:, 1]) if n else np.zeros(1)
    in_cup = (r < 0.06) & (p[:, 2] < 0.103) if n else np.zeros(1, bool)
    it = sph.iter_counts; sub = max(1, it[2]); sph.iter_counts = [0, 0, 0, 0]
    row = {"frame": f, "t": round((f - 1) / args.fps, 4), "milk_ml": round(n * V * 1e6, 1),
           "in_cup_ml": round(float(in_cup.sum()) * V * 1e6, 1),
           "on_table_ml": round(float(((p[:, 2] < 0.004) & (r > 0.064)).sum()) * V * 1e6, 2) if n else 0.0,
           "max_speed": round(float(s.max()), 3), "p99_speed": round(float(np.percentile(s, 99)), 3),
           "iters_div_mom_pos": [round(it[0] / sub, 1), round(it[1] / sub, 1), round(it[3] / sub, 1)]}
    rows.append(row)
    print(json.dumps(row), f"| {time.perf_counter() - t_sim:.0f}s", flush=True)
    if f % 6 == 0 or f == args.frames:
        nmax = rec_n[-1]
        P = np.full((len(rec_p), nmax, 3), np.nan, np.float32); Vv = np.zeros((len(rec_p), nmax, 3), np.float16)
        for i, (pp, vv) in enumerate(zip(rec_p, rec_v)):
            P[i, :len(pp)] = pp; Vv[i, :len(vv)] = vv
        np.save(args.out / "milk_pos.npy", P); np.save(args.out / "milk_vel_f16.npy", Vv)
        np.save(args.out / "active.npy", np.array(rec_n))
        json.dump({"args": {k_: (str(x) if isinstance(x, Path) else x) for k_, x in vars(args).items()},
                   "n_particles_max": N, "n_ghosts": len(ghost), "glass_ghosts": len(g_cup), "disc_particles": len(disc),
                   "exit_speed_m_s": speed, "layers_per_s": rate, "particle_volume_m3": V, "build_sec": t_build,
                   "sim_sec": time.perf_counter() - t_sim, "frames": rows}, open(args.out / "sim_log.json", "w"), indent=1)
print(f"done {time.perf_counter() - t_sim:.0f}s")
