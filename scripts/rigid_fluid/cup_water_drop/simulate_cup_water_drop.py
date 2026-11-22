"""Genesis 1.4.3 two-way simulation: a water-filled ceramic mug dropped onto a wooden dining table.

The mug is a free rigid body (convex body hull for table contact) coupled to DFSPH water via three layers
of ceramic ghost particles carrying independent pressure constraints and split density projection
(coupling_cup_water_drop.py), returning equal-and-opposite force and torque impulses to the mug.
Water uses Akinci et al. (2013) cohesion/curvature surface tension calibrated to 0.072 N/m with partial
porcelain wall wetting (dfsph_cup_water_drop.py).

Two modes:
- relax: holds the mug fixed while damping the liquid lattice to hydrostatic rest and meniscus equilibrium.
- drop: evolves exact free-fall translation + slight natural release angular rate until --start-frame,
  then runs the fully coupled rigid-fluid impact, asymmetric rim splash, droplet spill, and settling.
"""
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
import argparse
import json
import math
import time
from pathlib import Path
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=("relax", "drop"))
ap.add_argument("--geom", type=Path, default=Path(__file__).resolve().parent / "geometry")
ap.add_argument("--out", type=Path, required=True)
ap.add_argument("--water-state", type=Path, help="drop: relaxed cup-local water state (.npz from relax)")
ap.add_argument("--particle", type=float, default=0.001)
ap.add_argument("--rest-spacing", type=float, default=0.9300,
                help="lattice spacing / particle size giving rest density in Genesis cubic spline")
ap.add_argument("--fill-z", type=float, default=0.0305, help="water surface height in cup frame (m)")
ap.add_argument("--mu", type=float, default=1.0e-6, help="water kinematic viscosity (m^2/s)")
ap.add_argument("--surface-tension", type=float, default=1.5,
                help="Akinci 2013 surface tension gamma; 1.5 corresponds to 0.072 N/m at 1 mm resolution")
ap.add_argument("--wall-wetting", type=float, default=0.55,
                help="ceramic wall adhesion weight relative to liquid cohesion (0.55 ~ partial porcelain wetting)")
ap.add_argument("--density", type=float, default=998.2)
ap.add_argument("--cup-mass", type=float, default=0.32)
ap.add_argument("--release", type=float, nargs=3, default=(0.0, 0.0, 0.320), help="mug centre at release (m)")
ap.add_argument("--yaw-deg", type=float, default=12.0)
ap.add_argument("--omega-deg", type=float, nargs=3, default=(0.0, 0.0, 0.0),
                help="release angular velocity in world frame (deg/s); zero keeps mug strictly upright")
ap.add_argument("--fps", type=int, default=24)
ap.add_argument("--frames", type=int, default=96, help="last clip frame")
ap.add_argument("--start-frame", type=int, default=6, help="first dynamically simulated frame after analytic free fall")
ap.add_argument("--steps-per-frame", type=int, default=10)
ap.add_argument("--substeps", type=int, default=16, help="DFSPH substeps per scene step")
ap.add_argument("--max-density-error", type=float, default=0.01, help="DFSPH average density error (percent)")
ap.add_argument("--max-divergence-error", type=float, default=0.05, help="DFSPH average divergence error (percent/dt)")
ap.add_argument("--max-error-max", type=float, default=0.015, help="worst-particle position/divergence error (fraction)")
ap.add_argument("--momentum-error-avg", type=float, default=2e-4, help="momentum solve average compression per substep")
ap.add_argument("--momentum-error-max", type=float, default=1.5e-3, help="momentum solve worst compression per substep")
ap.add_argument("--jacobi-omega", type=float, default=0.38, help="damped Jacobi relaxation (< 0.48 spectral bound)")
ap.add_argument("--max-iters", type=int, default=120)
ap.add_argument("--checkpoint-every", type=int, default=6)
ap.add_argument("--ghost-layers", type=int, default=3)
ap.add_argument("--friction", type=float, default=0.42, help="glazed ceramic on wood friction")
ap.add_argument("--surface-friction", type=float, default=0.85, help="water coupling friction on table and props")
ap.add_argument("--sdf-cell", type=float, default=0.0005)
ap.add_argument("--coup-softness", type=float, default=0.0003)
ap.add_argument("--contact-timeconst", type=float, default=0.002)
ap.add_argument("--table-half", type=float, nargs=2, default=(0.65, 0.48))
ap.add_argument("--domain-top", type=float, default=0.9)
ap.add_argument("--relax-gravity", type=float, default=9.81)
ap.add_argument("--relax-sec", type=float, default=0.36)
ap.add_argument("--relax-damping", type=float, default=0.88)
ap.add_argument("--meniscus-omega", type=float, default=0.0,
                help="optional radial paraboloid meniscus shaping rate in relax (rad/s; 0 keeps flat hydrostatic rest)")
args = ap.parse_args()
args.geom = args.geom.expanduser().resolve()
args.out = args.out.expanduser().resolve()
if args.water_state:
    args.water_state = args.water_state.expanduser().resolve()
if args.frames < args.start_frame or args.particle <= 0 or args.substeps < 1:
    ap.error("frames must include start-frame; particle size and substeps must be positive")
args.out.mkdir(parents=True, exist_ok=True)

import trimesh
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

G = 9.81
cup = trimesh.load(args.geom / "cup_local.obj", process=True)
cav = json.loads((args.geom / "cavity.json").read_text())
prof = np.array(cav["profile_z_rmin_rmedian"])
floor_z, rim_z = cav["inner_floor_z"], cav["rim_z"]
hi_z = cup.bounds[1, 2]
bottom_z = cup.bounds[0, 2]
sp = args.rest_spacing * args.particle
body = cup.vertices[np.hypot(cup.vertices[:, 0], cup.vertices[:, 1]) <= 0.0525]
hull = trimesh.convex.convex_hull(body)
hull.export(args.out / "cup_body_hull.obj")
c_cm_local = np.asarray(hull.center_mass, dtype=np.float64)

# Water lattice inside measured cavity
zs = np.arange(floor_z + 0.5 * sp, args.fill_z - 0.5 * sp + 1e-9, sp)
rmax = np.interp(args.fill_z, prof[:, 0], prof[:, 1])
g1 = (np.arange(-int(rmax / sp) - 1, int(rmax / sp) + 2) + 0.5) * sp
X, Y = np.meshgrid(g1, g1, indexing="ij")
water_l = np.concatenate([
    np.stack([X[m], Y[m], np.full(m.sum(), z)], 1)
    for z in zs for m in [np.hypot(X, Y) <= np.interp(z, prof[:, 0], prof[:, 1]) - 0.5 * sp]
])
if args.mode == "drop":
    water_l = np.load(args.water_state)["pos_local"]

# Ceramic boundary ghosts within `ghost_layers` spacings inside the mug wall/floor
surf, fi = trimesh.sample.sample_surface_even(cup, 120000, seed=1)
surf_n = cup.face_normals[fi]
surf_tree = cKDTree(surf)


def inside_ceramic(P):
    dist, idx = surf_tree.query(P, workers=8)
    return ((P - surf[idx]) * surf_n[idx]).sum(1) < 0, dist


lo, hi = cup.bounds
gx = [(np.arange(math.floor(lo[i] / sp) - 1, math.ceil(hi[i] / sp) + 2) + 0.5) * sp for i in range(2)]
gz = np.arange(math.floor(lo[2] / sp) - 1, math.ceil(hi[2] / sp) + 2) * sp + (zs[0] % sp)
GX, GY, GZ = np.meshgrid(gx[0], gx[1], gz, indexing="ij")
cand = np.stack([GX.ravel(), GY.ravel(), GZ.ravel()], 1)
ins, depth = inside_ceramic(cand)
ghost_l = cand[ins & (depth < args.ghost_layers * sp)]
print(
    f"{args.mode}: water {len(water_l)} particles ({len(water_l) * 0.8 * args.particle ** 3 * 1e6:.1f} mL), "
    f"ghosts {len(ghost_l)}",
    flush=True,
)

import genesis as gs
gs.init(backend=gs.cuda, precision="32", seed=20261025, logging_level="warning")
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dfsph_cup_water_drop as dfsph
import coupling_cup_water_drop as coupling
import genesis.engine.simulator as simulator

dfsph.install_dfsph_gravity_fix()
dfsph.install_quiet(0.0, "position", 20)
dfsph.install_surface_tension(args.surface_tension, wall_weight=args.wall_wetting)
simulator.SPHSolver = coupling.make_solver()

relax = args.mode == "relax"
use_implicit_visc = (not relax) and (args.mu >= 5.0e-4)
explicit_mu = 0.0 if use_implicit_visc else args.mu
implicit_nu = args.mu if use_implicit_visc else 0.0
grav = args.relax_gravity if relax else G
dt = 1.0 / args.fps / args.steps_per_frame
tx, ty = args.table_half

scene = gs.Scene(
    sim_options=gs.options.SimOptions(
        dt=dt, substeps=16 if relax else args.substeps, gravity=(0, 0, -grav), floor_height=0.0
    ),
    sph_options=gs.options.SPHOptions(
        particle_size=args.particle,
        pressure_solver="DFSPH",
        max_density_error_percent=args.max_density_error,
        max_divergence_error=args.max_divergence_error,
        max_divergence_solver_iterations=args.max_iters,
        max_density_solver_iterations=args.max_iters,
        lower_bound=(-tx, -ty, -0.004),
        upper_bound=(tx, ty, args.domain_top),
    ),
    rigid_options=gs.options.RigidOptions(
        enable_collision=True, enable_self_collision=False, constraint_timeconst=args.contact_timeconst
    ),
    coupler_options=gs.options.LegacyCouplerOptions(
        rigid_sph=True, rigid_mpm=False, rigid_pbd=False, rigid_fem=False,
        mpm_sph=False, mpm_pbd=False, fem_mpm=False, fem_sph=False,
    ),
    show_viewer=False,
)
sticky = dict(
    sdf_cell_size=args.sdf_cell, sdf_min_res=32, sdf_max_res=256,
    coup_softness=args.coup_softness, coup_friction=args.surface_friction,
    coup_restitution=0.0, friction=args.friction,
)
scene.add_entity(gs.morphs.Plane(pos=(0.0, 0.0, 0.0)), material=gs.materials.Rigid(**sticky))
for name in ("plate_collider.obj", "napkin_collider.obj"):
    scene.add_entity(
        gs.morphs.Mesh(file=str(args.geom / name), fixed=True, convexify=False, decimate=False),
        material=gs.materials.Rigid(**sticky),
    )
water = scene.add_entity(
    gs.morphs.Nowhere(n_particles=len(water_l)),
    material=gs.materials.SPH.Liquid(rho=args.density, mu=explicit_mu, gamma=0.0, sampler="regular"),
)
ghosts = scene.add_entity(
    gs.morphs.Nowhere(n_particles=len(ghost_l)),
    material=gs.materials.SPH.Liquid(rho=args.density, mu=explicit_mu, gamma=0.0, sampler="regular"),
)

R_rel = Rotation.from_euler("z", args.yaw_deg, degrees=True)
P_rel = np.asarray(args.release, dtype=np.float64)
C0 = P_rel + R_rel.apply(c_cm_local)
omega_w = np.zeros(3, dtype=np.float64) if relax else np.radians(np.asarray(args.omega_deg, dtype=np.float64))


def freefall_state(t_sec: float):
    R_t = Rotation.from_rotvec(omega_w * t_sec) * R_rel
    C_t = C0 - np.array([0.0, 0.0, 0.5 * G * t_sec ** 2])
    P_t = C_t - R_t.apply(c_cm_local)
    V_cm = np.array([0.0, 0.0, 0.0 if relax else -G * t_sec])
    q_xyzw = R_t.as_quat()
    Q_t = np.array([q_xyzw[3], q_xyzw[0], q_xyzw[1], q_xyzw[2]])
    return P_t, Q_t, R_t, C_t, V_cm


T0 = 0.0 if relax else (args.start_frame - 1) / args.fps
P0, Q0, R0, C_t0, V_cm0 = freefall_state(T0)
cup_e = scene.add_entity(
    gs.morphs.Mesh(
        file=str(args.out / "cup_body_hull.obj"), pos=tuple(P0), quat=tuple(Q0),
        convexify=True, decimate=False, visualization=False, fixed=relax,
    ),
    material=gs.materials.Rigid(
        rho=1000.0, friction=args.friction, needs_coup=False,
        sdf_cell_size=0.002, sdf_min_res=16, sdf_max_res=64,
    ),
)

# Isotropic rotational inertia scale for optional implicit-viscosity CG preconditioner
cup_inertia_iso = float(args.cup_mass * (hull.moment_inertia.trace() / (3.0 * max(hull.mass, 1e-12))))
coupling.CONFIG.update(
    n_fluid=len(water_l),
    ghost_local=ghost_l,
    ghost_psi=np.full(len(ghost_l), 0.8 * args.particle ** 3),
    link_idx=cup_e.links[0].idx,
    implicit_nu=implicit_nu,
    cup_mass=args.cup_mass,
    cup_inertia=max(cup_inertia_iso, 1e-5),
    max_density_error_max=args.max_error_max,
    max_divergence_error_max=args.max_error_max,
    momentum_error_avg=args.momentum_error_avg,
    momentum_error_max=args.momentum_error_max,
    momentum_max_iters=args.max_iters,
    jacobi_omega=args.jacobi_omega,
)

t0 = time.perf_counter()
scene.build()
t_build = time.perf_counter() - t0
sph = scene.sim.sph_solver
if not relax:
    cup_e.set_mass(args.cup_mass)

ls = scene.sim.rigid_solver.dyn_state.links
li = cup_e.links[0].idx
lp = ls.pos.to_numpy()[li].reshape(-1)[:3]
lq = ls.quat.to_numpy()[li].reshape(-1)[:4]
mp = cup_e.get_pos().cpu().numpy().ravel()
mq = cup_e.get_quat().cpu().numpy().ravel()
xyzw = lambda w: [w[1], w[2], w[3], w[0]]
R_link0 = Rotation.from_quat(xyzw(lq))
sph.g_local.from_numpy(
    R_link0.inv().apply(Rotation.from_quat(xyzw(mq)).apply(ghost_l) + mp - lp).astype(np.float32)
)

n = len(water_l)
wp0 = R0.apply(water_l) + P0
wv0 = V_cm0 + np.cross(omega_w, wp0 - lp)
water.set_particles_pos(wp0.astype(np.float32))
water.set_particles_active(np.ones(n, bool))
ghosts.set_particles_pos((R0.apply(ghost_l) + P0).astype(np.float32))
ghosts.set_particles_vel(np.zeros((len(ghost_l), 3), np.float32))
ghosts.set_particles_active(np.ones(len(ghost_l), bool))
water.set_particles_vel(wv0.astype(np.float32))
if not relax:   # Must come after particle writes, which reset rigid DOF velocities in Genesis
    omega_link0 = R_link0.inv().apply(omega_w)
    cup_e.set_dofs_velocity(np.array([*V_cm0, *omega_link0], dtype=np.float32))
sph.kernel_place_ghosts(ls)

tilt0 = math.degrees(math.acos(np.clip(R0.apply([0, 0, 1])[2], -1.0, 1.0)))
print(
    f"built in {t_build:.0f}s; cup z={P0[2]:.4f} m, vz={V_cm0[2]:+.3f} m/s, tilt={tilt0:.2f} deg",
    flush=True,
)

if relax:
    t0 = time.perf_counter()
    n_relax = int(round(args.relax_sec / dt))
    shaping_start = int(round(0.14 / dt))
    for i in range(n_relax):
        scene.step()
        v = water.get_particles_vel().cpu().numpy().reshape(-1, 3)
        damp = 0.78 if i >= n_relax - 8 else args.relax_damping
        v_next = v * damp
        if args.meniscus_omega > 0.0 and i >= shaping_start:
            wp_cur = water.get_particles_pos().cpu().numpy().reshape(-1, 3)
            pl_cur = R0.inv().apply(wp_cur - P0)
            px = pl_cur[:, 0] - 0.0022
            py = pl_cur[:, 1] + 0.0015
            theta = np.arctan2(py, px)
            # Subtle off-axis + multi-lobe shaping prevents artificial laser-straight central needle singularity
            mod = 1.0 + 0.18 * np.cos(2.0 * theta + 0.35) + 0.14 * np.cos(3.0 * theta - 1.10) + 0.09 * np.cos(5.0 * theta + 1.90)
            ramp = min(1.0, (i - shaping_start + 1) / 14.0)
            rim_guard = np.clip((rim_z - 0.0014 - pl_cur[:, 2]) / 0.0028, 0.0, 1.0)
            scale = (args.meniscus_omega ** 2) * ramp * mod * rim_guard
            a_loc = np.column_stack([scale * px, scale * py, np.zeros(len(pl_cur))])
            v_next = v_next + dt * R0.apply(a_loc)
        water.set_particles_vel(v_next.astype(np.float32))
        if i % 24 == 23:
            print(f"relax {i + 1}: max|v| {np.abs(v).max():.4f} mean|v| {np.linalg.norm(v, axis=1).mean():.5f}", flush=True)
    wp = water.get_particles_pos().cpu().numpy().reshape(-1, 3)
    pl = R0.inv().apply(wp - P0)
    np.savez(
        args.out / "water_relaxed.npz",
        pos_local=pl.astype(np.float64),
        rest_spacing=args.rest_spacing,
        particle=args.particle,
    )
    surface = float(np.percentile(pl[:, 2], 99.5))
    gap = float(pl[:, 2].min() - floor_z)
    json.dump(
        {
            "args": {kk: (str(x) if isinstance(x, Path) else x) for kk, x in vars(args).items()},
            "n_particles": n,
            "n_ghosts": len(ghost_l),
            "build_sec": t_build,
            "relax_wall_sec": time.perf_counter() - t0,
            "surface_z_995_m": surface,
            "floor_gap_m": gap,
        },
        open(args.out / "relax_log.json", "w"),
        indent=2,
    )
    print(
        f"relaxed {args.relax_sec}s in {time.perf_counter() - t0:.0f}s; "
        f"surface {surface * 1e3:.2f} mm, floor gap {gap * 1e3:.3f} mm",
        flush=True,
    )
    raise SystemExit

frames = list(range(args.start_frame, args.frames + 1))
rec_pos = np.zeros((len(frames), n, 3), np.float32)
rec_vel = np.zeros((len(frames), n, 3), np.float16)
poses = {}
for f_pre in range(1, args.start_frame):
    t_pre = (f_pre - 1) / args.fps
    Pf, Qf, _, Cf, Vf = freefall_state(t_pre)
    poses[f_pre] = {
        "pos": Pf.tolist(),
        "quat_wxyz": Qf.tolist(),
        "com_pos": Cf.tolist(),
        "lin_vel": Vf.tolist(),
        "ang_vel_world": omega_w.tolist(),
    }

log = []
t_sim = time.perf_counter()
rim_r = float(np.interp(rim_z, prof[:, 0], prof[:, 1]))

for k, f in enumerate(frames):
    if k > 0:
        for _ in range(args.steps_per_frame):
            scene.step()
    p = water.get_particles_pos().cpu().numpy().reshape(-1, 3)
    v = water.get_particles_vel().cpu().numpy().reshape(-1, 3)
    if not np.isfinite(p).all() or not np.isfinite(v).all():
        raise RuntimeError(f"non-finite liquid state at frame {f}")
    cp = cup_e.get_pos().cpu().numpy().ravel()
    cq = cup_e.get_quat().cpu().numpy().ravel()
    cv = cup_e.get_dofs_velocity().cpu().numpy().ravel()
    lp_now = ls.pos.to_numpy()[li].reshape(-1)[:3]
    ang_now = ls.cd_ang.to_numpy()[li].reshape(-1)[:3]
    vel_now = ls.cd_vel.to_numpy()[li].reshape(-1)[:3]

    rec_pos[k] = p
    rec_vel[k] = v.astype(np.float16)
    poses[f] = {
        "pos": cp.tolist(),
        "quat_wxyz": cq.tolist(),
        "com_pos": lp_now.tolist(),
        "lin_vel": vel_now.tolist(),
        "ang_vel_world": ang_now.tolist(),
    }

    Rc = Rotation.from_quat(xyzw(cq))
    pl = Rc.inv().apply(p - cp)
    r = np.hypot(pl[:, 0], pl[:, 1])
    in_cup = (
        (r < np.interp(pl[:, 2], prof[:, 0], prof[:, 1]) + 0.001)
        & (pl[:, 2] > floor_z - 0.002)
        & (pl[:, 2] < rim_z + 0.003)
    )
    outside_rim = (r > rim_r + args.particle) & (~in_cup)
    prof_r = np.interp(pl[:, 2], prof[:, 0], prof[:, 1])
    near = (
        (np.abs(pl[:, :2]) < 0.09).all(1)
        & (pl[:, 2] > bottom_z - 0.003)
        & (pl[:, 2] < hi_z + 0.003)
        & ((r > prof_r - 0.0018) | (pl[:, 2] < floor_z + 0.0018) | (pl[:, 2] > rim_z - 0.0018))
    )
    leak = np.zeros(n, bool)
    if near.any():
        leak[near] = inside_ceramic(pl[near])[0]

    row = {
        "frame": f,
        "t": (f - 1) / args.fps,
        "water_in_cup": float(in_cup.mean()),
        "water_E_per_kg": float(0.5 * (v ** 2).sum(1).mean() + G * p[:, 2].mean()),
        "cup_linear_energy_J": float(args.cup_mass * (0.5 * (vel_now ** 2).sum() + G * lp_now[2])),
        "max_water_z": float(p[:, 2].max()),
        "max_speed": float(np.linalg.norm(v, axis=1).max()),
        "mean_water_speed": float(np.linalg.norm(v, axis=1).mean()),
        "water_above_rim_particles": int((pl[:, 2] > rim_z).sum()),
        "water_outside_rim_particles": int(outside_rim.sum()),
        "water_outside_rim_ml": float(outside_rim.sum() * 0.8 * args.particle ** 3 * 1e6),
        "max_height_above_rim_m": float(pl[:, 2].max() - rim_z),
        "water_on_table": int(((~in_cup) & (p[:, 2] < 0.004)).sum()),
        "particles_in_ceramic": int(leak.sum()),
        "cup_z": float(cp[2]),
        "cup_vz": float(vel_now[2]),
        "cup_tilt_deg": math.degrees(math.acos(np.clip(Rc.apply([0, 0, 1])[2], -1.0, 1.0))),
        "iters_div_mom_pos": [round(sph.iter_counts[idx] / max(1, sph.iter_counts[2]), 2) for idx in (0, 1, 3)],
    }
    sph.iter_counts = [0, 0, 0, 0]
    log.append(row)
    print(
        json.dumps({kk: (round(x, 4) if isinstance(x, float) else x) for kk, x in row.items()}),
        f"| {time.perf_counter() - t_sim:.0f}s",
        flush=True,
    )
    if k % args.checkpoint_every == 0 or f == frames[-1]:
        np.save(args.out / "water_pos.npy", rec_pos[: k + 1])
        np.save(args.out / "water_vel_f16.npy", rec_vel[: k + 1])
        json.dump(
            {
                "args": {kk: (str(x) if isinstance(x, Path) else x) for kk, x in vars(args).items()},
                "n_particles": n,
                "n_ghosts": len(ghost_l),
                "start_frame": args.start_frame,
                "simulated_frames": k + 1,
                "build_sec": t_build,
                "sim_sec": time.perf_counter() - t_sim,
                "frames": log,
                "cup_pose": {str(kk): vv for kk, vv in poses.items()},
                "water_state": str(args.water_state),
                "release": list(P_rel),
                "yaw_deg": args.yaw_deg,
                "omega_deg": list(args.omega_deg),
            },
            open(args.out / "sim_log.json", "w"),
            indent=2,
        )
print(f"done: sim {time.perf_counter() - t_sim:.0f}s ({(time.perf_counter() - t_sim) / max(1, len(frames) - 1):.2f}s/frame)")
