"""The tilted-cup pour at 1 mm: Genesis 1.4.3 DFSPH. The fixed cup, the support block and the tabletop are static
ghost-particle boundaries that carry their own pressure (split density solve), Akinci surface tension calibrated to
0.072 N/m, the glaze and the oak fully wetted (ghost wetting 1.0) with contact-line friction on the oak. Initial state:
water at rest in the 58-degree cup, its horizontal surface --head above the low inner rim (81 mL).
Viscosity up to 2e-5 m^2/s is Genesis's explicit SPH viscosity; above, an implicit no-slip solve (unconditionally
stable; the explicit step diverges at 1e-3 m^2/s). --no-cup removes the cup's ghosts (the DELETE cup edit): the same
water starts unsupported. Writes water_pos.npy, water_vel_f16.npy, sim_log.json and simulation_report.json (read by
surface_*.py and render_*.py).
usage: <genesis python> simulate_tilted_cup_table_pour.py --out RUN [--mu NU] [--no-cup] [--frames N]"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from contact_geometry import (CUP_CENTER_Z, SUPPORT_CENTER_X, LOW_INNER_RIM_Z, CUP_TILT_DEG, CUP_INNER_RADIUS,  # noqa
                              CUP_OUTER_RADIUS, CUP_HEIGHT, CUP_BOTTOM_THICKNESS, SUPPORT_SIZE)

ap = argparse.ArgumentParser()
ap.add_argument("--out", type=Path, required=True)
ap.add_argument("--particle", type=float, default=0.001)
ap.add_argument("--rest-spacing", type=float, default=0.93)
ap.add_argument("--head", type=float, default=0.016)
ap.add_argument("--frames", type=int, default=96, help="recorded frames, frame 1 = t 0")
ap.add_argument("--fps", type=int, default=24)
ap.add_argument("--steps-per-frame", type=int, default=10)
ap.add_argument("--substeps", type=int, default=16)
ap.add_argument("--mu", type=float, default=1.004e-6, help="water kinematic viscosity (m^2/s)")
ap.add_argument("--no-cup", action="store_true", help="DELETE cup: no cup boundary")
ap.add_argument("--surface-tension", type=float, default=1.5)
ap.add_argument("--table-wet", type=float, default=1.0, help="ghost wetting factor of the oak (sessile drop: 0.67 -> 87 deg, 0.5 -> 98 deg, 1.0 -> ~67 deg)")
ap.add_argument("--cl-friction", type=float, default=1000.0, help="contact-line friction of the oak (1/s)")
ap.add_argument("--div-iters", type=int, default=10, help="cap of the auxiliary divergence solve")
ap.add_argument("--table-x", type=float, nargs=2, default=(-0.06, 0.42), help="the sheet reaches x = 0.32 m")
ap.add_argument("--table-y", type=float, nargs=2, default=(-0.17, 0.17))
args = ap.parse_args()
args.out.mkdir(parents=True, exist_ok=True)

d = args.particle; sp = args.rest_spacing * d
a = math.radians(CUP_TILT_DEG)
ROT = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
C = np.array([0.0, 0.0, CUP_CENTER_Z])
H2, RI, RO, FLOOR = CUP_HEIGHT / 2, CUP_INNER_RADIUS, CUP_OUTER_RADIUS, -CUP_HEIGHT / 2 + CUP_BOTTOM_THICKNESS


def local(p):
    return (p - C) @ ROT


def lattice(lo, hi):
    ax = [np.arange(math.floor(lo[i] / sp), math.ceil(hi[i] / sp) + 1) for i in range(3)]
    I = np.stack(np.meshgrid(*ax, indexing="ij"), -1).reshape(-1, 3)
    return I, (I + 0.5) * sp          # node (i, j, k) at ((i, j, k) + 0.5) sp: rows at z = +-0.5 sp, +-1.5 sp, ...


# water: horizontal surface `head` above the low inner rim, half a spacing clear of the ceramic
I, P = lattice((-0.08, -0.05, 0.0), (0.08, 0.05, 0.11))
L = local(P); r = np.hypot(L[:, 0], L[:, 1])
water = P[(r <= RI - 0.5 * sp) & (L[:, 2] >= FLOOR + 0.5 * sp) & (L[:, 2] <= H2 - 0.5 * sp) & (P[:, 2] <= LOW_INNER_RIM_Z + args.head)]
# ghosts: every lattice node inside the ceramic, the support block and the top 3 rows of the tabletop patch
cer = ((r >= RI) & (r <= RO) & (np.abs(L[:, 2]) <= H2)) | ((r <= RO) & (L[:, 2] >= -H2) & (L[:, 2] <= FLOOR))
gc = I[cer]
Is, Ps = lattice((SUPPORT_CENTER_X - SUPPORT_SIZE[0] / 2, -SUPPORT_SIZE[1] / 2, 0.0),
                 (SUPPORT_CENTER_X + SUPPORT_SIZE[0] / 2, SUPPORT_SIZE[1] / 2, SUPPORT_SIZE[2]))
inside_s = (np.abs(Ps[:, 0] - SUPPORT_CENTER_X) <= SUPPORT_SIZE[0] / 2) & (np.abs(Ps[:, 1]) <= SUPPORT_SIZE[1] / 2) \
    & (Ps[:, 2] >= 0) & (Ps[:, 2] <= SUPPORT_SIZE[2])
gs_ = Is[inside_s]
It, Pt = lattice((args.table_x[0], args.table_y[0], -3 * sp), (args.table_x[1], args.table_y[1], -0.5 * sp))
gt = It[Pt[:, 2] < 0]
keys = {}
for idx, w in ((gc[:0] if args.no_cup else gc, 1.0), (gs_, None), (gt, None)):
    for row in map(tuple, idx):
        keys.setdefault(row, w)
k = args.table_wet
GI = np.array(list(keys.keys())); ghost = (GI + 0.5) * sp
wet = np.array([1.0 if v == 1.0 else k for v in keys.values()])
visc = np.array([1.0 for v in keys.values()])
cl = np.array([0.0 if v == 1.0 else args.cl_friction for v in keys.values()])
print(f"water {len(water)} particles ({len(water)*0.8*d**3*1e6:.1f} mL), ghosts {len(ghost)} "
      f"(cup {0 if args.no_cup else len(gc)}, support {len(gs_)}, table {len(gt)}), table wetting {k:.3f}", flush=True)

import genesis as gs
gs.init(backend=gs.cuda, precision="32", seed=20261030, logging_level="warning")
import pcve_dfsph_patches as dfsph
import coupling_tilted_cup_table_pour as coupling
import genesis.engine.simulator as simulator
dfsph.install_dfsph_gravity_fix(); dfsph.install_quiet(0.0, "position", 20)
dfsph.install_surface_tension(args.surface_tension)
simulator.SPHSolver = coupling.make_solver()
dt = 1.0 / args.fps / args.steps_per_frame
implicit = args.mu > 2e-5
mu_explicit, nu_implicit = (0.0, args.mu) if implicit else (args.mu, 0.0)
lo = (args.table_x[0] + 0.002, args.table_y[0] + 0.002, -0.004); hi = (args.table_x[1] - 0.002, args.table_y[1] - 0.002, 0.2)
scene = gs.Scene(
    sim_options=gs.options.SimOptions(dt=dt, substeps=args.substeps, gravity=(0, 0, -9.81)),
    sph_options=gs.options.SPHOptions(particle_size=d, pressure_solver="DFSPH", max_density_error_percent=0.005,
                                      max_divergence_error=0.02, max_divergence_solver_iterations=args.div_iters,
                                      max_density_solver_iterations=1000, lower_bound=lo, upper_bound=hi),
    rigid_options=gs.options.RigidOptions(enable_collision=False),
    coupler_options=gs.options.LegacyCouplerOptions(rigid_sph=True, rigid_mpm=False, rigid_pbd=False, rigid_fem=False,
                                                    mpm_sph=False, mpm_pbd=False, fem_mpm=False, fem_sph=False),
    show_viewer=False)
carrier = scene.add_entity(gs.morphs.Box(pos=tuple(C), size=(0.01, 0.01, 0.01), fixed=True),
                           material=gs.materials.Rigid(needs_coup=False))
wat = scene.add_entity(gs.morphs.Nowhere(n_particles=len(water)),
                       material=gs.materials.SPH.Liquid(rho=998.2, mu=mu_explicit, gamma=0.0, sampler="regular"))
gho = scene.add_entity(gs.morphs.Nowhere(n_particles=len(ghost)),
                       material=gs.materials.SPH.Liquid(rho=998.2, mu=mu_explicit, gamma=0.0, sampler="regular"))
coupling.CONFIG.update(n_fluid=len(water), ghost_local=ghost, ghost_psi=np.full(len(ghost), 0.8 * d ** 3),
                       link_idx=carrier.links[0].idx, implicit_nu=nu_implicit, body_mass=1.0, body_inertia=1.0, ghost_fixed=True,
                       max_density_error_max=0.01, max_divergence_error_max=1e9, ghost_wetting=wet, ghost_noslip=True, ghost_viscosity_factor=visc, contact_line_friction=cl)
t0 = time.perf_counter(); scene.build(); t_build = time.perf_counter() - t0
sph = scene.sim.sph_solver
from scipy.spatial.transform import Rotation
ls = scene.sim.rigid_solver.dyn_state.links; li = carrier.links[0].idx
lp = ls.pos.to_numpy()[li].reshape(-1)[:3]; lq = ls.quat.to_numpy()[li].reshape(-1)[:4]
sph.g_local.from_numpy(Rotation.from_quat([lq[1], lq[2], lq[3], lq[0]]).inv().apply(ghost - lp).astype(np.float32))
n = len(water)
wat.set_particles_pos(water.astype(np.float32)); wat.set_particles_vel(np.zeros((n, 3), np.float32))
wat.set_particles_active(np.ones(n, bool))
gho.set_particles_pos(ghost.astype(np.float32)); gho.set_particles_vel(np.zeros((len(ghost), 3), np.float32))
gho.set_particles_active(np.ones(len(ghost), bool))

rec_p = np.zeros((args.frames, n, 3), np.float32); rec_v = np.zeros((args.frames, n, 3), np.float16)
rows = []; t_sim = time.perf_counter()
for f in range(1, args.frames + 1):
    if f > 1:
        for _ in range(args.steps_per_frame):
            scene.step()
    p = wat.get_particles_pos().cpu().numpy().reshape(-1, 3); v = wat.get_particles_vel().cpu().numpy().reshape(-1, 3)
    if not (np.isfinite(p).all() and np.isfinite(v).all()):
        raise RuntimeError(f"non-finite state at frame {f}")
    rec_p[f - 1] = p; rec_v[f - 1] = v.astype(np.float16)
    Lp = local(p); rp = np.hypot(Lp[:, 0], Lp[:, 1])
    in_cup = (rp < RI + 0.001) & (Lp[:, 2] > FLOOR - 0.002) & (Lp[:, 2] < H2 + 0.002)
    on_table = ~in_cup & (p[:, 2] < 0.004)
    s = np.linalg.norm(v, axis=1)
    it = sph.iter_counts; sub = max(1, it[2])
    row = {"frame": f, "physical_time_sec": (f - 1) / args.fps, "in_cup_fraction": float(in_cup.mean()),
           "table_particles": int(on_table.sum()), "max_speed_m_s": float(s.max()),
           "p99_speed_m_s": float(np.percentile(s, 99)),
           "table_mean_speed_m_s": float(s[on_table].mean()) if on_table.any() else 0.0,
           "table_height_p50_p95_mm": [float(np.percentile(p[on_table, 2], q) * 1e3) for q in (50, 95)] if on_table.any() else None,
           "min_z_mm": float(p[:, 2].min() * 1e3),
           "iters_div_mom_pos": [round(it[0] / sub, 1), round(it[1] / sub, 1), round(it[3] / sub, 1)]}
    sph.iter_counts = [0, 0, 0, 0]
    rows.append(row)
    print(json.dumps({kk: (round(x, 4) if isinstance(x, float) else x) for kk, x in row.items()}),
          f"| {time.perf_counter()-t_sim:.0f}s", flush=True)
    if f % 6 == 0 or f == args.frames:
        np.save(args.out / "water_pos.npy", rec_p[:f]); np.save(args.out / "water_vel_f16.npy", rec_v[:f])
        log = {"args": {kk: (str(x) if isinstance(x, Path) else x) for kk, x in vars(args).items()}, "n_particles": n,
               "n_ghosts": len(ghost), "viscosity_solve": "implicit" if implicit else "explicit", "build_sec": t_build, "sim_sec": time.perf_counter() - t_sim, "frames": rows}
        json.dump(log, open(args.out / "sim_log.json", "w"), indent=1)
        report = {"solver": "Genesis 1.4.3 DFSPH, 1 mm, ghost-particle boundaries with own pressure, split density solve, "
                            "Akinci surface tension", "coupling": ("static support and tabletop" if args.no_cup else "static cup, support and tabletop") + " ghost boundaries",
                  "physics": {"cup_present": not args.no_cup, "water_present": True, "water_kinematic_viscosity_m2_s": args.mu, "cup_pose": {"center_m": C.tolist(), "euler_deg": [0, CUP_TILT_DEG, 0]}},
                  "geometry": {"square_support_center_m": [SUPPORT_CENTER_X, 0.0, SUPPORT_SIZE[2] / 2]},
                  "frames_simulated": f, "numerics": {"simulation_fps": args.fps, "physical_duration_sec": f / args.fps},
                  "trajectory": [{"frame": rr["frame"], "physical_time_sec": rr["physical_time_sec"]} for rr in rows]}
        json.dump(report, open(args.out / "simulation_report.json", "w"), indent=1)
print(f"done {time.perf_counter()-t_sim:.0f}s")
