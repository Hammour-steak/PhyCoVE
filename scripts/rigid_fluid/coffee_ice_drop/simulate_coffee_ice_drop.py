"""Genesis 1.4.3 two-way simulation: a rigid 16 mm ice cube dropped into DFSPH coffee in the restaurant's mug.

Writes coffee particle positions/velocities per frame (fp16), the ice pose per frame and sim_log.json. Defaults are
the published base case; the edits change one input (--coffee-density, --implicit-nu, --no-ice, --no-coffee).
See README.md for the numerical choices."""
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
import argparse, json, time
from pathlib import Path
import numpy as np

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geom", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--particle", type=float, default=0.001)
    ap.add_argument("--mu", type=float, default=1.45e-6, help="SPH kinematic viscosity (m^2/s)")
    ap.add_argument("--gamma", type=float, default=2e-4)
    ap.add_argument("--coffee-density", type=float, default=1030.0)
    ap.add_argument("--ice-density", type=float, default=920.0)
    ap.add_argument("--ice-side", type=float, default=0.016)
    ap.add_argument("--ice-xyz", type=float, nargs=3, default=(0.0, -0.003, 0.8907))
    ap.add_argument("--ice-euler", type=float, nargs=3, default=(0.35, -0.24, 0.5), help="Blender XYZ euler, rad")
    ap.add_argument("--gravity", type=float, default=9.81)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--frames", type=int, default=96)
    ap.add_argument("--steps-per-frame", type=int, default=10)
    ap.add_argument("--substeps", type=int, default=16)
    ap.add_argument("--settle-sec", type=float, default=0.4)
    ap.add_argument("--coup-softness", type=float, default=0.0003)
    ap.add_argument("--sdf-cell", type=float, default=0.0005)
    ap.add_argument("--no-ice", action="store_true")
    ap.add_argument("--no-coffee", action="store_true", help="DELETE coffee: rigid ice, mug, saucer and table only")
    ap.add_argument("--implicit-nu", type=float, default=0.0,
                    help="kinematic viscosity solved implicitly (m^2/s); the explicit SPH mu is then set to 0")
    ap.add_argument("--domain-top", type=float, default=1.10)
    ap.add_argument("--max-density-error", type=float, default=0.005, help="DFSPH average density error tolerance (percent)")
    ap.add_argument("--max-divergence-error", type=float, default=0.01, help="DFSPH divergence error tolerance (percent per dt)")
    ap.add_argument("--xsph", type=float, default=0.0, help="XSPH epsilon (0 = off)")
    ap.add_argument("--xsph-mode", choices=("position", "velocity"), default="position")
    ap.add_argument("--div-nmin", type=int, default=20, help="neighbour count below which DFSPH skips the divergence fix")
    ap.add_argument("--domain-half", type=float, default=0.20)
    ap.add_argument("--surface-friction", type=float, default=1.0,
                    help="coupling friction of saucer and table for the liquid (drops landing there stop instead of skating)")
    ap.add_argument("--dump-pressure", action="store_true")
    ap.add_argument("--no-props", action="store_true", help="leave the spoon and coffee beans out of the SPH boundary")
    ap.add_argument("--ghost-mode", choices=("shell", "surface"), default="shell")
    ap.add_argument("--ghost-layers", type=int, default=3)
    ap.add_argument("--psi-scale", type=float, default=None, help="default: plane calibration (ice_coupling_coffee_ice_drop.plane_psi_scale)")
    ap.add_argument("--ghost-spacing", type=float, default=0.6, help="ice boundary particle spacing / particle size")
    ap.add_argument("--friction", type=float, default=0.05, help="rigid contact friction of wet ice and ceramic")
    ap.add_argument("--floor-gap", type=float, default=0.002,
                    help="ice collides with a hidden cavity shell whose floor is raised by this much, so a particle layer "
                         "fits under a cube resting on the bottom (0 = collide with the real mug mesh)")
    ap.add_argument("--keep-double-gravity", action="store_true", help="reproduce Genesis 1.4.3's DFSPH 2 g bug")
    ap.add_argument("--rigid-response", choices=("both", "pressure", "collision", "akinci"), default="akinci")
    ap.add_argument("--fill-z", type=float, default=0.8450, help="liquid fill height before settling (settles to ~0.8412, 13 mm below the rim)")
    ap.add_argument("--rest-spacing", type=float, default=0.9283,
                    help="lattice spacing / particle size at which Genesis's 0.8*d^3 particle volume gives rest density")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    import genesis as gs
    from scipy.spatial.transform import Rotation

    gs.init(backend=gs.cuda, precision="32", seed=20261022, logging_level="warning")
    import sys; sys.path.insert(0, str(Path(__file__).resolve().parent))
    import dfsph_coffee_ice_drop as coupling_patch
    if not args.keep_double_gravity:
        coupling_patch.install_dfsph_gravity_fix()
    coupling_patch.install_quiet(args.xsph, args.xsph_mode, args.div_nmin)
    if args.xsph > 0 or args.div_nmin != 20:
        if args.rigid_response != "akinci" or args.no_ice or args.no_coffee:
            import genesis.engine.simulator as simulator
            from genesis.engine.solvers.sph_solver import SPHSolver as _Base
            simulator.SPHSolver = coupling_patch.make_xsph_solver(_Base)
    if args.rigid_response == "collision":
        coupling_patch.install_collision_only()
    elif args.rigid_response == "akinci" and not (args.no_ice or args.no_coffee):
        import ice_coupling_coffee_ice_drop as ice_boundary
        import genesis.engine.simulator as simulator
        simulator.SPHSolver = ice_boundary.make_solver()
    else:
        coupling_patch.install(args.rigid_response)
    cav = json.loads((args.geom / "cavity.json").read_text())
    dt = 1.0 / args.fps / args.steps_per_frame
    table_z = 0.79916
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=dt, substeps=args.substeps, gravity=(0, 0, -args.gravity), floor_height=table_z),
        sph_options=gs.options.SPHOptions(particle_size=args.particle, pressure_solver="DFSPH",
                                          max_density_error_percent=args.max_density_error,
                                          max_divergence_error=args.max_divergence_error,
                                          lower_bound=(-args.domain_half, -args.domain_half, table_z - 0.004), upper_bound=(args.domain_half, args.domain_half, args.domain_top)),
        rigid_options=gs.options.RigidOptions(enable_collision=True, enable_self_collision=False),
        coupler_options=gs.options.LegacyCouplerOptions(rigid_sph=True, rigid_mpm=False, rigid_pbd=False, rigid_fem=False,
                                                        mpm_sph=False, mpm_pbd=False, fem_mpm=False, fem_sph=False),
        show_viewer=False,
    )
    wall = dict(sdf_cell_size=args.sdf_cell, sdf_min_res=32, sdf_max_res=256, coup_softness=args.coup_softness,
                coup_friction=0.05, coup_restitution=0.0, friction=args.friction)
    # contact bits: 1 = real mug (SPH boundary), 2 = ice and its hidden cavity collider, saucer collides with both
    mug_bits = dict(contype=1, conaffinity=1) if args.floor_gap > 0 else {}
    ice_bits = dict(contype=2, conaffinity=2) if args.floor_gap > 0 else {}
    cup = scene.add_entity(gs.morphs.Mesh(file=str(args.geom / "cup_world.obj"), fixed=True, convexify=False, decimate=False, **mug_bits),
                           material=gs.materials.Rigid(**wall))
    sticky = {**wall, "coup_friction": args.surface_friction}
    saucer = scene.add_entity(gs.morphs.Mesh(file=str(args.geom / "saucer_solid.obj"), fixed=True, convexify=False, decimate=False),
                              material=gs.materials.Rigid(**sticky))
    # the tabletop as a coupled rigid plane: the SPH domain floor below it keeps tangential velocity (frictionless)
    table = scene.add_entity(gs.morphs.Plane(pos=(0.0, 0.0, table_z), contype=4, conaffinity=4), material=gs.materials.Rigid(**sticky))
    # the spoon and the coffee beans on the saucer: drops land on them instead of passing through (fluid coupling only)
    if not args.no_props:
        for prop in ("spoon_world.obj", "beans_world.obj"):
            scene.add_entity(gs.morphs.Mesh(file=str(args.geom / prop), fixed=True, convexify=False, decimate=False, contype=4, conaffinity=4),
                             material=gs.materials.Rigid(**{**sticky, "sdf_cell_size": 0.0003}))
    if args.floor_gap > 0:
        import trimesh
        prof_c = np.array(cav["profile_z_rmin_rmedian"])
        floor_c = cav["inner_floor_z"] + args.floor_gap
        zs_c = prof_c[prof_c[:, 0] > floor_c, 0]
        inner = [(0.0, floor_c), (float(np.interp(floor_c, prof_c[:, 0], prof_c[:, 1])), floor_c)]
        inner += [(float(np.interp(z, prof_c[:, 0], prof_c[:, 1])), float(z)) for z in zs_c[::4]] + [(float(prof_c[-1, 1]), cav["rim_z"])]
        outer = [(inner[-1][0] + 0.003, cav["rim_z"]), (inner[1][0] + 0.003, cav["inner_floor_z"] - 0.003), (0.0, cav["inner_floor_z"] - 0.003)]
        ring = np.array(inner + outer)
        shell = trimesh.creation.revolve(ring[::-1], sections=96)
        trimesh.repair.fix_normals(shell)
        shell_path = args.out / "ice_cavity_collider.obj"; shell.export(shell_path)
        scene.add_entity(gs.morphs.Mesh(file=str(shell_path), fixed=True, convexify=False, decimate=False, visualization=False,
                                        contype=2, conaffinity=2),
                         material=gs.materials.Rigid(needs_coup=False, friction=args.friction, sdf_cell_size=args.sdf_cell,
                                                     sdf_min_res=32, sdf_max_res=256))
    # Genesis samples meshes at spacing d, but with V = 0.8 d^3 and support 2d the rest lattice spacing is 0.928 d, so a
    # mesh-sampled liquid settles ~20 % lower. Place a rest-density lattice in the measured cavity instead.
    prof = np.array(cav["profile_z_rmin_rmedian"])
    fill_z = args.fill_z
    sp = args.rest_spacing * args.particle
    zs = np.arange(cav["inner_floor_z"] + 0.5 * sp, fill_z - 0.5 * sp + 1e-9, sp)
    rmax = np.interp(fill_z, prof[:, 0], prof[:, 1])
    xs = np.arange(-rmax, rmax + 1e-9, sp)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    lat = []
    for z in zs:
        rin = np.interp(z, prof[:, 0], prof[:, 1]) - 0.5 * sp
        m = np.hypot(X, Y) <= rin
        lat.append(np.stack([X[m], Y[m], np.full(m.sum(), z)], 1))
    lattice = np.concatenate(lat).astype(np.float32)
    if args.no_coffee:
        lattice = np.zeros((0, 3), np.float32)
    if not args.no_ice:  # no liquid inside the (possibly partly submerged) starting ice
        from scipy.spatial.transform import Rotation as _R
        loc = _R.from_euler("xyz", args.ice_euler).inv().apply(lattice - np.array(args.ice_xyz))
        lattice = lattice[np.abs(loc).max(axis=1) > args.ice_side / 2 + 0.5 * sp]
    coffee = None if args.no_coffee else scene.add_entity(
        gs.morphs.Nowhere(n_particles=len(lattice)),
        material=gs.materials.SPH.Liquid(rho=args.coffee_density, mu=args.mu, gamma=args.gamma, sampler="regular"))
    akinci = args.rigid_response == "akinci" and not (args.no_ice or args.no_coffee)
    if akinci:
        if args.ghost_mode == "shell":
            ghost_local, ghost_psi = ice_boundary.sample_box_shell(args.ice_side, args.particle, layers=args.ghost_layers)
        else:
            ghost_local = ice_boundary.sample_box_surface(args.ice_side, args.ghost_spacing * args.particle)
            psi_scale = ice_boundary.plane_psi_scale(args.particle, args.ghost_spacing * args.particle) if args.psi_scale is None else args.psi_scale
            ghost_psi = psi_scale * ice_boundary.boundary_volumes(ghost_local, 2 * args.particle)
        ghosts = scene.add_entity(gs.morphs.Nowhere(n_particles=len(ghost_local)),
                                  material=gs.materials.SPH.Liquid(rho=args.coffee_density, mu=args.mu, gamma=args.gamma, sampler="regular"))
    q_xyzw = Rotation.from_euler("xyz", args.ice_euler).as_quat()
    ice_quat = (q_xyzw[3], q_xyzw[0], q_xyzw[1], q_xyzw[2])
    ice = None
    if not args.no_ice:
        ice = scene.add_entity(gs.morphs.Box(size=(args.ice_side,) * 3, pos=tuple(args.ice_xyz), quat=ice_quat, **ice_bits),
                               material=gs.materials.Rigid(rho=args.ice_density, sdf_cell_size=args.ice_side / 40,
                                                           sdf_min_res=32, sdf_max_res=64, coup_softness=args.coup_softness,
                                                           coup_friction=0.05, coup_restitution=0.0, friction=args.friction,
                                                           needs_coup=not akinci))
        if akinci:
            ice_boundary.CONFIG.update(n_fluid=len(lattice), ghost_local=ghost_local, ghost_psi=ghost_psi, link_idx=ice.links[0].idx,
                                       implicit_nu=args.implicit_nu, ice_mass=args.ice_density * args.ice_side ** 3,
                                       ice_inertia=args.ice_density * args.ice_side ** 5 / 6.0)
    t0 = time.perf_counter()
    scene.build()
    t_build = time.perf_counter() - t0
    n = coffee.n_particles if coffee is not None else 0
    if coffee is not None:
        coffee.set_particles_pos(lattice)
        coffee.set_particles_vel(np.zeros_like(lattice))
        coffee.set_particles_active(np.ones(n, dtype=bool))
    if akinci:
        R0 = Rotation.from_quat(q_xyzw)
        ghosts.set_particles_pos((R0.apply(ghost_local) + np.array(args.ice_xyz)).astype(np.float32))
        ghosts.set_particles_vel(np.zeros((len(ghost_local), 3), np.float32))
        ghosts.set_particles_active(np.ones(len(ghost_local), dtype=bool))
        sph = scene.sim.sph_solver
        print(f"ice boundary: {len(ghost_local)} ghosts, psi/V_fluid median {np.median(ghost_psi)/(0.8*args.particle**3):.2f}", flush=True)
    print(f"built in {t_build:.1f}s, particles={n}, substep_dt={dt/args.substeps:.2e}", flush=True)

    def hold_ice():
        ice.set_pos(np.array(args.ice_xyz, dtype=np.float32))
        ice.set_quat(np.array(ice_quat, dtype=np.float32))
        ice.set_dofs_velocity(np.zeros(6, dtype=np.float32))

    def particles():
        return coffee.get_particles_pos().cpu().numpy().reshape(-1, 3) if coffee is not None else np.zeros((0, 3))

    def particle_vel():
        return coffee.get_particles_vel().cpu().numpy().reshape(-1, 3) if coffee is not None else np.zeros((0, 3))

    # settle the coffee with the ice held in the air (not recorded)
    if akinci and args.implicit_nu > 0:
        sph.visc_on = False
    t0 = time.perf_counter()
    settle_steps = int(round(args.settle_sec / dt))
    for i in range(settle_steps):
        if ice is not None:
            hold_ice()
        scene.step()
    p = particles()
    if n:
        print(f"settled {args.settle_sec}s in {time.perf_counter()-t0:.1f}s; coffee top z(99.5%)={np.percentile(p[:,2],99.5):.4f} "
              f"max|v|={np.abs(particle_vel()).max():.3f}", flush=True)
    if ice is not None:
        hold_ice()
    if akinci and args.implicit_nu > 0:
        sph.visc_on = True

    rec_pos = np.zeros((args.frames, n, 3), np.float16)
    rec_vel = np.zeros((args.frames, n, 3), np.float16)
    ice_pose = []
    log = []
    inside = lambda pp: (np.hypot(pp[:, 0], pp[:, 1]) < 0.0365) & (pp[:, 2] > cav["inner_floor_z"] - 0.002)
    t_sim = time.perf_counter()
    for f in range(args.frames):
        if f > 0:
            for _ in range(args.steps_per_frame):
                scene.step()
        p = particles()
        v = particle_vel()
        rec_pos[f] = (p - np.array([0, 0, 0.8])).astype(np.float16)  # store relative to z=0.8 for fp16 precision
        rec_vel[f] = v.astype(np.float16)
        row = {"frame": f + 1, "t": f / args.fps, "coffee_in_cup": int(inside(p).sum()), "max_speed": float(np.linalg.norm(v, axis=1).max()) if n else 0.0,
               "top_z_995": float(np.percentile(p[inside(p), 2], 99.5)) if inside(p).any() else None}
        if ice is not None:
            pos = ice.get_pos().cpu().numpy().ravel(); quat = ice.get_quat().cpu().numpy().ravel()
            vel = ice.get_dofs_velocity().cpu().numpy().ravel()
            ice_pose.append({"pos": pos.tolist(), "quat_wxyz": quat.tolist()})
            row.update(ice_z=float(pos[2]), ice_xy=[float(pos[0]), float(pos[1])], ice_vz=float(vel[2]))
            if akinci:
                fs = sph.force_sum.to_numpy()[0] / max(1, args.steps_per_frame * args.substeps if f > 0 else 1)
                sph.force_sum.fill(0)
                row.update(fluid_force_z_over_weight=float(fs[2] / (args.ice_density * args.ice_side ** 3 * args.gravity)),
                           iters_div_den=[sph.iter_counts[0] / max(1, sph.iter_counts[2]), sph.iter_counts[1] / max(1, sph.iter_counts[2])])
                if args.implicit_nu > 0:
                    row.update(visc_cg_iters=sph.visc_stats[0] / max(1, sph.visc_stats[1]), visc_worst_rel_residual=sph.visc_stats[2])
        log.append(row)
        if f % 4 == 0 or f == args.frames - 1:
            el = time.perf_counter() - t_sim
            print(json.dumps({k: (round(v, 5) if isinstance(v, float) else v) for k, v in row.items()}), f"| {el:.0f}s", flush=True)
    t_sim = time.perf_counter() - t_sim
    if args.dump_pressure:
        sph = scene.sim.sph_solver
        np.savez(args.out / "pressure.npz", p=sph.particles.p.to_numpy()[:, 0], pos=sph.particles.pos.to_numpy()[:, 0],
                 rho=sph.particles.rho.to_numpy()[:, 0])
    np.save(args.out / "coffee_pos_f16.npy", rec_pos)
    np.save(args.out / "coffee_vel_f16.npy", rec_vel)
    json.dump({"args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}, "n_particles": n,
               "build_sec": t_build, "sim_sec": t_sim, "sim_sec_per_frame": t_sim / max(1, args.frames - 1),
               "ice_quat_wxyz0": ice_quat, "frames": log, "ice_pose": ice_pose, "z_offset": 0.8},
              open(args.out / "sim_log.json", "w"), indent=1)
    print(f"done: sim {t_sim:.0f}s ({t_sim/max(1,args.frames-1):.2f}s/frame)")


if __name__ == "__main__":
    main()
