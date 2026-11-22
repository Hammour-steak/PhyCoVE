"""Cooking oil poured from a tilted bottle into a frying pan: Genesis 1.4.3 DFSPH at 0.5 mm.

Local frame: origin at the pan's centre on its flat interior floor (world (1.1, 3.405, 1.18233)), z up. The pan
interior (a solid of revolution, profile geometry/pan_profile.npz) is a static ghost-particle boundary that carries its
own pressure (split density solve, coupling_cooking_oil_pan.py), no-slip, wetted, with contact-line friction. Oil: 915 kg/m^3,
kinematic viscosity --mu (implicit solve), Akinci surface tension scaled to 0.032 N/m. The oil enters through the
bottle's pour opening: a disc of particles on the rest lattice (radius --jet-radius, normal to the exit axis) is
activated at the exit with the exit speed, so the volume flow is exactly the scheduled flow. All particles are
preallocated and parked inactive until emitted. --schedule T:Q[:R] ... changes the flow (m^3/s) from time T on, over a
linear ramp of R seconds;
--resume-from/--resume-frame continue a source run from its frame-F state (timed edits).
Writes oil_pos.npy (float32), oil_vel_f16.npy, active.npy (active count per frame), sim_log.json.
usage: <genesis python> simulate_cooking_oil_pan.py --out RUN [--flow M3_S] [--schedule T:Q ...] [--mu NU] [--resume-from SRC --resume-frame F]"""
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
import argparse, json, math, time
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent

ap = argparse.ArgumentParser()
ap.add_argument("--out", type=Path, required=True)
ap.add_argument("--pan", type=Path, default=HERE / "geometry/pan_profile.npz")
ap.add_argument("--particle", type=float, default=0.0005)
ap.add_argument("--rest-spacing", type=float, default=0.93)
ap.add_argument("--frames", type=int, default=96)
ap.add_argument("--fps", type=int, default=24)
ap.add_argument("--steps-per-frame", type=int, default=10)
ap.add_argument("--substeps", type=int, default=48, help="CFL: the stream lands at 2.2 m/s, 0.39 d per substep")
ap.add_argument("--rho", type=float, default=915.0)
ap.add_argument("--mu", type=float, default=1.4e-4,
                help="oil kinematic viscosity (m^2/s): olive oil at ~12 C (128 mPa s); at 0.5 mm the 20 C value 9e-5 lets the\n                     landing stream throw off numerical spray, which a viscous oil at Re ~ 40 does not do")
ap.add_argument("--surface-tension", type=float, default=3.9, help="Akinci gamma (3.9 = 0.032 N/m at 0.5 mm, rho 915)")
ap.add_argument("--flow", type=float, default=10e-6, help="volume flow (m^3/s): 10 mL/s, a tablespoon in 1.5 s")
ap.add_argument("--schedule", nargs="*", default=[], help="T:Q[:R] flow changes (s : m^3/s : linear ramp over R s)")
ap.add_argument("--start", type=float, default=7 / 24, help="pour start (s)")
ap.add_argument("--exit", type=float, nargs=3, default=(-0.04060, -0.00347, 0.24460),
                help="pour exit centre (m): over the lowest point of the bottle rim (inner radius 13.5 mm + 0.5 mm, 1 mm past the rim face)")
ap.add_argument("--axis", type=float, nargs=3, default=(0.035, 0.005, -0.15), help="exit direction")
ap.add_argument("--jet-radius", type=float, default=0.0023033, help="4.6 mm opening")
ap.add_argument("--inlet-buffer", type=float, default=0.0015, help="liquid held at the inlet velocity this far behind the opening (m)")
ap.add_argument("--ghost-radius", type=float, default=0.12, help="pan ghosts out to this radius (m)")
ap.add_argument("--wet", type=float, default=1.0, help="ghost wetting factor of the nonstick coating")
ap.add_argument("--wall-drag", type=float, default=-1.0,
                help="Navier-slip wall friction (1/s); -1: the laminar wall shear of the first particle layer, 2 nu / sp^2 / wall kernel share")
ap.add_argument("--cl-friction", type=float, default=1000.0, help="contact-line friction on the pan (1/s)")
ap.add_argument("--div-iters", type=int, default=10)
ap.add_argument("--resume-from", type=Path)
ap.add_argument("--resume-frame", type=int, default=0)
args = ap.parse_args()
args.out.mkdir(parents=True, exist_ok=True)
d = args.particle; sp = args.rest_spacing * d
V = 0.8 * d ** 3                                   # Genesis SPH particle volume

# ---- pan ghosts: lattice nodes up to three spacings below the interior surface z_s(r)
prof = np.load(args.pan); pr, pz = prof["r"], prof["z"]
R = args.ghost_radius
zs_max = float(np.interp(R, pr, pz))
ax = [np.arange(math.floor(-R / sp) - 1, math.ceil(R / sp) + 1)] * 2 + [np.arange(-4, math.ceil(zs_max / sp) + 1)]
I = np.stack(np.meshgrid(*ax, indexing="ij"), -1).reshape(-1, 3)
P = (I + 0.5) * sp
rn = np.hypot(P[:, 0], P[:, 1]); zs = np.interp(rn, pr, pz)
keep = (rn < R) & (P[:, 2] < zs) & (P[:, 2] > zs - 3 * sp)
ghost = P[keep]
wet = np.full(len(ghost), args.wet); cl = np.full(len(ghost), args.cl_friction)
# wall shear: the implicit viscosity is the projected SPH Laplacian, which resists only the relative velocity along
# each pair's line: a sheet one or two particles thick sliding over the pan barely feels the ghosts under it and an
# impact lamella skates to the pan wall. The Navier-slip term (coupling ghost_drag) adds the laminar wall shear of the
# first layer, tau = mu u / (sp / 2) on a layer sp thick, divided by the wall's kernel share at that height.
def _w(r, h):
    q = r / h; k = 8 / np.pi / h ** 3
    return np.where(q <= 0.5, k * (6 * q ** 3 - 6 * q ** 2 + 1), np.where(q <= 1, 2 * k * (1 - q) ** 3, 0.0))
_near = ghost[np.hypot(ghost[:, 0], ghost[:, 1]) < 0.01]
wall_share = float((V * _w(np.linalg.norm(_near - np.array([0.0, 0.0, 0.5 * sp]), axis=1), 2 * d)).sum())
wall_drag = 2 * args.mu / sp ** 2 / wall_share if args.wall_drag < 0 else args.wall_drag
# the drag is integrated explicitly: keep its rate below 1.8 / dt for a particle pressed against the pan (share ~0.5);
# only a 4x-viscosity oil reaches the cap, and there the implicit viscosity already resists sliding
dt_sub = 1.0 / args.fps / args.steps_per_frame / args.substeps
wall_drag = min(wall_drag, 1.8 / dt_sub)

# ---- emitter: disc on the rest lattice normal to the exit direction
E, A = np.array(args.exit), np.array(args.axis) / np.linalg.norm(args.axis)
U = np.cross(A, [1.0, 0.0, 0.0]); U /= np.linalg.norm(U); Wv = np.cross(A, U)
k = int(math.ceil(args.jet_radius / sp))
disc = np.array([(i * sp, j * sp) for i in range(-k, k + 1) for j in range(-k, k + 1)
                 if (i * sp) ** 2 + (j * sp) ** 2 <= args.jet_radius ** 2])
disc = disc[:, :1] * U + disc[:, 1:] * Wv
area_eff = len(disc) * sp * sp
t_end = args.frames / args.fps
sched = sorted([(args.start, args.flow, 0.0)] + [tuple((list(map(float, s.split(":"))) + [0.0])[:3]) for s in args.schedule])


def flow_at(t):
    """scheduled volume flow; a change T:Q:R goes linearly from the previous flow to Q over R seconds (a bottle
    cannot change its pour instantly: a step makes the faster oil overtake the slower stream below it and hit the
    pan as one slug)"""
    q = 0.0
    for t0, q0, r0 in sched:
        if t >= t0 - 1e-9:
            q = q + (q0 - q) * (t - t0) / r0 if (r0 > 0 and t < t0 + r0) else q0
    return q


def speed_at(t):
    return flow_at(t) / area_eff if t >= args.start - 1e-9 else 0.0


_tg = np.arange(args.start, t_end + 0.02, 1e-5)
_sg = np.concatenate([[0.0], np.cumsum(0.5 * (np.vectorize(speed_at)(_tg[1:] - 1e-12) + np.vectorize(speed_at)(_tg[:-1])) * 1e-5)])


def pushed(t):
    """oil length pushed through the opening by time t (m)"""
    return float(np.interp(t, _tg, _sg, left=0.0))


def exit_time(s):
    """time at which the oil pushed length reaches s (inf if never)"""
    if pushed(t_end) < s:
        return float("inf")
    lo_, hi_ = args.start, t_end
    for _ in range(60):
        mid = 0.5 * (lo_ + hi_)
        lo_, hi_ = (mid, hi_) if pushed(mid) < s else (lo_, mid)
    return hi_


n_layers = int((pushed(t_end + 1e-9) + args.inlet_buffer) / sp) + 2
N = n_layers * len(disc)
print(f"wall kernel share {wall_share:.3f}, wall drag {wall_drag:.0f} 1/s")
print(f"pan ghosts {len(ghost)} (r < {R} m); emitter disc {len(disc)} particles, exit speed {speed_at(args.start):.4f} m/s, "
      f"{N} oil particles max ({N * V * 1e6:.1f} mL)", flush=True)

import genesis as gs
gs.init(backend=gs.cuda, precision="32", seed=20261101, logging_level="warning")
import pcve_dfsph_patches as dfsph
import coupling_cooking_oil_pan as coupling
import genesis.engine.simulator as simulator
dfsph.install_dfsph_gravity_fix(); dfsph.install_quiet(0.0, "position", 20)
dfsph.install_surface_tension(args.surface_tension)
simulator.SPHSolver = coupling.make_solver()
implicit = args.mu > 2e-5
mu_explicit, nu_implicit = (0.0, args.mu) if implicit else (args.mu, 0.0)
dt = 1.0 / args.fps / args.steps_per_frame
B_ = max(R + 0.004, abs(args.exit[0]) + 0.03, abs(args.exit[1]) + 0.03)
lo, hi = (-B_, -B_, -0.0025), (B_, B_, args.exit[2] + 0.02)
scene = gs.Scene(
    sim_options=gs.options.SimOptions(dt=dt, substeps=args.substeps, gravity=(0, 0, -9.81)),
    sph_options=gs.options.SPHOptions(particle_size=d, pressure_solver="DFSPH", max_density_error_percent=0.005,
                                      max_divergence_error=0.02, max_divergence_solver_iterations=args.div_iters,
                                      max_density_solver_iterations=1000, lower_bound=lo, upper_bound=hi),
    rigid_options=gs.options.RigidOptions(enable_collision=False),
    coupler_options=gs.options.LegacyCouplerOptions(rigid_sph=True, rigid_mpm=False, rigid_pbd=False, rigid_fem=False,
                                                    mpm_sph=False, mpm_pbd=False, fem_mpm=False, fem_sph=False),
    show_viewer=False)
carrier = scene.add_entity(gs.morphs.Box(pos=(0.0, 0.0, 0.1), size=(0.01, 0.01, 0.01), fixed=True),
                           material=gs.materials.Rigid(needs_coup=False))
oil = scene.add_entity(gs.morphs.Nowhere(n_particles=N),
                       material=gs.materials.SPH.Liquid(rho=args.rho, mu=mu_explicit, gamma=0.0, sampler="regular"))
gho = scene.add_entity(gs.morphs.Nowhere(n_particles=len(ghost)),
                       material=gs.materials.SPH.Liquid(rho=args.rho, mu=mu_explicit, gamma=0.0, sampler="regular"))
coupling.CONFIG.update(n_fluid=N, ghost_local=ghost, ghost_psi=np.full(len(ghost), V), link_idx=carrier.links[0].idx,
                       implicit_nu=nu_implicit, body_mass=1.0, body_inertia=1.0, ghost_fixed=True, max_density_error_max=0.01,
                       max_divergence_error_max=1e9, ghost_wetting=wet, ghost_noslip=True,
                       ghost_viscosity_factor=np.ones(len(ghost)), contact_line_friction=cl,
                       ghost_drag=np.full(len(ghost), wall_drag))
t0 = time.perf_counter(); scene.build(); t_build = time.perf_counter() - t0
sph = scene.sim.sph_solver
from scipy.spatial.transform import Rotation
ls = scene.sim.rigid_solver.dyn_state.links; li = carrier.links[0].idx
lp = ls.pos.to_numpy()[li].reshape(-1)[:3]; lq = ls.quat.to_numpy()[li].reshape(-1)[:4]
sph.g_local.from_numpy(Rotation.from_quat([lq[1], lq[2], lq[3], lq[0]]).inv().apply(ghost - lp).astype(np.float32))
park = np.tile(np.array([R, R, 0.26], np.float32), (N, 1)) + (np.arange(N) % 7)[:, None].astype(np.float32) * 1e-4
oil.set_particles_pos(park); oil.set_particles_vel(np.zeros((N, 3), np.float32))
oil.set_particles_active(np.zeros(N, bool))
gho.set_particles_pos(ghost.astype(np.float32)); gho.set_particles_vel(np.zeros((len(ghost), 3), np.float32))
gho.set_particles_active(np.ones(len(ghost), bool))

import torch
emitted = 0                                        # layers
inlet_t = np.full(N, -1.0, np.float32); inlet_v = np.zeros((N, 3), np.float32)
t_clock0 = 0.0                                     # physical time at which this Genesis scene's clock (sim.cur_t) is 0
rec_p, rec_v, rec_n, rows = [], [], [], []
t_sim = time.perf_counter()
time_now = 0.0
first = 1
if args.resume_from:
    F = args.resume_frame
    srcP = np.load(args.resume_from / "oil_pos.npy", mmap_mode="r"); srcV = np.load(args.resume_from / "oil_vel_f16.npy", mmap_mode="r")
    srcN = np.load(args.resume_from / "active.npy"); src_log = json.load(open(args.resume_from / "sim_log.json"))
    for k_ in ("exit", "axis", "jet_radius", "flow", "start", "particle", "rest_spacing", "steps_per_frame", "substeps", "fps", "mu", "inlet_buffer"):
        a_, b_ = src_log["args"][k_], getattr(args, k_)
        assert (list(a_) == list(b_)) if isinstance(a_, list) else a_ == b_, k_
    for i_ in range(F):
        n_ = int(srcN[i_]); rec_p.append(np.asarray(srcP[i_, :n_], np.float32)); rec_v.append(np.asarray(srcV[i_, :n_], np.float16))
        rec_n.append(n_); rows.append(dict(src_log["frames"][i_], copied_from_source=True))
    n0 = rec_n[-1]
    assert n0 % len(disc) == 0
    emitted = n0 // len(disc)
    ids = torch.arange(0, n0, device=gs.device, dtype=gs.tc_int)
    oil.set_particles_pos(torch.as_tensor(rec_p[-1], device=gs.device), ids)
    oil.set_particles_vel(torch.as_tensor(rec_v[-1].astype(np.float32), device=gs.device), ids)
    oil.set_particles_active(torch.ones(n0, dtype=torch.bool, device=gs.device), ids)
    time_now = (F - 1) / args.fps
    t_clock0 = time_now                            # a resumed scene's own clock starts at 0
    for kk in range(emitted):                      # the source's layers still in the buffer at its frame-F time
        te = exit_time(kk * sp)
        if te > time_now:
            inlet_t[kk * len(disc):(kk + 1) * len(disc)] = min(te - t_clock0, 1e6)
            inlet_v[kk * len(disc):(kk + 1) * len(disc)] = A * speed_at(min(te, t_end) - 1e-6)
    sph.inlet_t.from_numpy(inlet_t); sph.inlet_v.from_numpy(inlet_v)
    first = F + 1
    print(f"resumed from {args.resume_from} frame {F}: {n0} particles, {emitted} layers, t = {time_now:.4f} s", flush=True)
for f in range(first, args.frames + 1):
    if f > 1:
        for _ in range(args.steps_per_frame):
            # layer k leaves the opening when the pushed length reaches k sp; it enters the inflow buffer inlet_buffer
            # earlier and moves there at the inlet velocity (coupling_cooking_oil_pan.kernel_inlet): the oil still in the spout holds
            # the falling stream back. Without it the column's top is free, the falling oil pulls it away from the next
            # layer through the viscosity and the stream tears at the opening into slabs.
            t1 = time_now + dt
            s0, s1, v = pushed(time_now), pushed(t1), speed_at(time_now)
            new = []
            while emitted < n_layers and emitted * sp - args.inlet_buffer < s1 - 1e-12 and v > 0:
                new.append(emitted); emitted += 1
            if new:
                lo_i = new[0] * len(disc); hi_i = (new[-1] + 1) * len(disc)
                pos = np.concatenate([E + disc + A * (s0 - kk * sp) for kk in new]).astype(np.float32)
                ids = torch.arange(lo_i, hi_i, device=gs.device, dtype=gs.tc_int)
                oil.set_particles_pos(torch.as_tensor(pos, device=gs.device), ids)
                oil.set_particles_vel(torch.as_tensor(np.tile(A * v, (len(pos), 1)).astype(np.float32), device=gs.device), ids)
                oil.set_particles_active(torch.ones(len(pos), dtype=torch.bool, device=gs.device), ids)
                for kk in new:
                    inlet_t[kk * len(disc):(kk + 1) * len(disc)] = min(exit_time(kk * sp) - t_clock0, 1e6)
                    inlet_v[kk * len(disc):(kk + 1) * len(disc)] = A * v
                sph.inlet_t.from_numpy(inlet_t); sph.inlet_v.from_numpy(inlet_v)
            scene.step()
            time_now = t1
    n = emitted * len(disc)
    p = oil.get_particles_pos().cpu().numpy().reshape(-1, 3)[:n]
    v_ = oil.get_particles_vel().cpu().numpy().reshape(-1, 3)[:n]
    if not (np.isfinite(p).all() and np.isfinite(v_).all()):
        raise RuntimeError(f"non-finite state at frame {f}")
    rec_p.append(p.astype(np.float32)); rec_v.append(v_.astype(np.float16)); rec_n.append(n)
    s = np.linalg.norm(v_, axis=1) if n else np.zeros(1)
    on_floor = p[:, 2] < 0.004 if n else np.zeros(1, bool)
    c = np.median(p[on_floor, :2], axis=0) if on_floor.sum() > 10 else np.zeros(2)
    rr = np.hypot(p[on_floor, 0] - c[0], p[on_floor, 1] - c[1]) if on_floor.sum() else np.zeros(1)
    it = sph.iter_counts; sub = max(1, it[2]); sph.iter_counts = [0, 0, 0, 0]
    vs = getattr(sph, "visc_stats", [0, 1, 0])
    row = {"frame": f, "t": round((f - 1) / args.fps, 4), "oil_ml": round(n * V * 1e6, 2),
           "puddle_ml": round(float(on_floor.sum()) * V * 1e6, 2),
           "puddle_r95_mm": round(float(np.percentile(rr, 95)) * 1e3, 1) if on_floor.sum() else 0.0,
           "max_r_mm": round(float(np.hypot(p[:, 0], p[:, 1]).max()) * 1e3, 1) if n else 0.0,
           "puddle_h_mm": round(float(np.percentile(p[on_floor, 2], 99)) * 1e3, 2) if on_floor.sum() else 0.0,
           "max_speed": round(float(s.max()), 3), "p99_speed": round(float(np.percentile(s, 99)), 3),
           "iters_div_mom_pos": [round(it[0] / sub, 1), round(it[1] / sub, 1), round(it[3] / sub, 1)],
           "visc_iters": round(vs[0] / max(1, vs[1]), 1)}
    if hasattr(sph, "visc_stats"):
        sph.visc_stats = [0, 0, 0]
    rows.append(row)
    print(json.dumps(row), f"| {time.perf_counter() - t_sim:.0f}s", flush=True)
    if f % 6 == 0 or f == args.frames:
        nmax = rec_n[-1]
        P_ = np.full((len(rec_p), nmax, 3), np.nan, np.float32); Vv = np.zeros((len(rec_p), nmax, 3), np.float16)
        for i, (pp, vv) in enumerate(zip(rec_p, rec_v)):
            P_[i, :len(pp)] = pp; Vv[i, :len(vv)] = vv
        np.save(args.out / "oil_pos.npy", P_); np.save(args.out / "oil_vel_f16.npy", Vv)
        np.save(args.out / "active.npy", np.array(rec_n))
        json.dump({"args": {k_: (str(x) if isinstance(x, Path) else x) for k_, x in vars(args).items()},
                   "n_particles_max": N, "n_ghosts": len(ghost), "disc_particles": len(disc), "area_eff_m2": area_eff,
                   "exit_speed_m_s": speed_at(args.start), "schedule": sched, "particle_volume_m3": V, "build_sec": t_build,
                   "viscosity_solve": "implicit" if implicit else "explicit", "wall_drag_per_s": wall_drag,
                   "sim_sec": time.perf_counter() - t_sim, "frames": rows}, open(args.out / "sim_log.json", "w"), indent=1)
print(f"done {time.perf_counter() - t_sim:.0f}s")
