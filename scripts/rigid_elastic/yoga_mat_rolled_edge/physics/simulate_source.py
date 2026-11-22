"""Remote source-only ball/yoga-mat collision after physical settling."""
from pathlib import Path
import argparse
import math
import hashlib
import json
import sys
import time

import numpy as np
from scipy.spatial import cKDTree
import trimesh

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / "tools/manifold3d_deps"), str(ROOT / "tools/ipc_probe_deps")]
import uipc
from uipc import builtin, view
from uipc.core import AffineBodyStateAccessorFeature, Engine, FiniteElementStateAccessorFeature, Scene, World
from uipc.geometry import ground, label_surface, trimesh as ipc_trimesh
from uipc.constitution import AffineBodyConstitution, DiscreteShellBending, ElasticModuli2D, NeoHookeanShell

from prepare_mat import build_mat
from viscosity import apply_viscosity, manifest as viscosity_manifest


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def skew(vector):
    x, y, z = vector
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def transformed_minimum_z(vertices, transform):
    """Minimum z of the exact ABD collision surface, including affine strain."""
    world = np.asarray(vertices) @ transform[:3, :3].T + transform[:3, 3]
    return float(np.min(world[:, 2]))


def simulate_deleted_mat_floor(args, out, p, s, mesh_info, ball, ball_start, fps, frames):
    """Closed-form constrained rigid rolling after the elastic object is deleted."""
    started = time.monotonic()
    radius = float(args.ball_radius)
    clearance = 0.0003
    settled = np.eye(4)
    settled[:3, 3] = [ball_start[0], ball_start[1], -float(np.min(ball.vertices[:, 2])) + clearance]
    if args.rigid_initial_cache is not None:
        seed = np.load(args.rigid_initial_cache, allow_pickle=False)
        settled = np.asarray(seed["settled_ball_transform"]).copy()
        if not np.allclose(settled[:2,3], ball_start[:2], atol=1e-12, rtol=0):
            raise ValueError("floor-only initial state does not match the shared source")
    transforms = []
    velocities = []
    rows = []
    omega = float(args.ball_speed) / radius
    for frame in range(frames):
        t = frame / fps
        angle = omega * t
        c, q = np.cos(angle), np.sin(angle)
        rotation = np.array([[c, 0.0, q], [0.0, 1.0, 0.0], [-q, 0.0, c]])
        transform = np.eye(4)
        transform[:3, :3] = rotation @ settled[:3, :3]
        transform[:3, 3] = settled[:3, 3] + [args.ball_speed * t, 0.0, 0.0]
        velocity = np.zeros((4, 4))
        velocity[:3, :3] = skew([0.0, omega, 0.0]) @ rotation
        velocity[:3, 3] = [args.ball_speed, 0.0, 0.0]
        gap = transformed_minimum_z(ball.vertices, transform)
        transforms.append(transform)
        velocities.append(velocity)
        rows.append({
            "frame": frame + 1, "time_s": t,
            "ball_center_m": transform[:3, 3].tolist(),
            "ball_bottom_gap_m": gap,
            "ball_linear_velocity_m_s": velocity[:3, 3].tolist(),
            "curl_peak_m": None, "curl_peak_change_m": None,
            "wood_block_center_m": None,
        })
    provenance = {
        "execution_origin": "remote_server",
        "local_blender_used": False,
        "case": "delete_mat",
        "solver": "closed-form rigid-body no-slip rolling on a horizontal plane",
        "mat_present": False,
        "mat": p,
        "ball": {"radius_m": radius, "mass_kg": args.ball_mass, "rolling_speed_m_s": args.ball_speed, "initial_location_before_settle_m": ball_start.tolist()},
        "added_wood_block": None,
        "settled_initial_state": None if args.rigid_initial_cache is None else {"path": str(args.rigid_initial_cache.resolve()), "sha256": hashlib.sha256(args.rigid_initial_cache.read_bytes()).hexdigest(), "method": "shared source ball state; mat absent"},
        "simulation": {**s, "settle_s": 0.0, "record_duration_s": args.duration, "fps": fps},
        "mesh": mesh_info,
        "rigid_floor_model": {
            "gravity_m_s2": 9.81,
            "normal_force_balances_gravity": True,
            "no_slip_constraint": "omega_y = linear_speed_x / radius",
            "rolling_resistance": 0.0,
            "surface_clearance_m": clearance,
        },
    }
    write_json(out / "simulation_config.json", provenance)
    transforms = np.asarray(transforms)
    velocities = np.asarray(velocities)
    np.savez_compressed(
        out / "simulation.npz",
        mat_positions=np.empty((frames, 0, 3)), mat_velocities=np.empty((frames, 0, 3)),
        mat_rest_positions=np.empty((0, 3)), mat_faces=np.empty((0, 3), dtype=np.int32),
        mat_present=np.asarray([False], dtype=np.uint8),
        ball_transforms=transforms, ball_affine_velocities=velocities,
        ball_vertices=np.asarray(ball.vertices), ball_faces=np.asarray(ball.faces),
        times=np.arange(frames, dtype=np.float64) / fps,
        settled_mat_positions=np.empty((0, 3)), settled_ball_transform=settled,
        has_wood_block=np.asarray([False], dtype=np.uint8),
        wood_block_transforms=np.empty((0, 4, 4)), wood_block_affine_velocities=np.empty((0, 4, 4)),
        wood_block_vertices=np.empty((0, 3)), wood_block_faces=np.empty((0, 3), dtype=np.int32),
    )
    bx = transforms[:, 0, 3]
    report = {
        "status": "review_required",
        "reason": "deleted-mat rigid-floor diagnostic; requires numerical audit and remote render review",
        "settled_ball_floor_gap_m": float(rows[0]["ball_bottom_gap_m"]),
        "settled_mat_rms_speed_m_s": 0.0,
        "ball_final_x_m": float(bx[-1]), "ball_max_x_m": float(np.max(bx)),
        "wood_block_final_center_m": None, "wood_block_displacement_m": None,
        "curl_initial_peak_m": None, "curl_min_peak_m": None, "curl_final_peak_m": None,
        "manual_motion": False, "manual_deformation": False,
        "wall_seconds": time.monotonic() - started, "rows": rows,
    }
    write_json(out / "simulation_report.json", report)
    print("COMPLETE", json.dumps({"ball_max_x_m": report["ball_max_x_m"], "minimum_gap_m": min(row["ball_bottom_gap_m"] for row in rows), "wall_seconds": report["wall_seconds"]}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dt", type=float, default=1 / 480)
    parser.add_argument("--duration", type=float, default=1.6)
    parser.add_argument("--settle", type=float, default=0.5)
    parser.add_argument("--grid-x", type=int, default=65)
    parser.add_argument("--grid-y", type=int, default=17)
    parser.add_argument("--ball-speed", type=float, default=1.15)
    parser.add_argument("--ball-mass", type=float, default=4.536)
    parser.add_argument("--ball-radius", type=float, default=0.12065)
    parser.add_argument("--young", type=float)
    parser.add_argument("--curl-height", type=float, help="initial curl-tip midplane height above the floor in metres")
    parser.add_argument("--hinge-viscosity", type=float)
    parser.add_argument("--viscosity-scale", type=float)
    parser.add_argument("--velocity-tol", type=float, default=0.0001)
    parser.add_argument("--newton-max", type=int)
    parser.add_argument("--add-wood-block", action="store_true")
    parser.add_argument("--delete-mat", action="store_true")
    parser.add_argument("--delete-ball", action="store_true",
                        help="DELETE ball: the mat alone from the settled state (needs --settled-cache); the ball's record keeps "
                             "its settled pose at rest and simulation.npz carries ball_present = 0")
    parser.add_argument("--wood-block-mass", type=float, default=0.8)
    parser.add_argument("--settled-cache", type=Path)
    parser.add_argument("--rigid-initial-cache", type=Path, help="shared source ball state for the mat-deleted rigid-floor world")
    parser.add_argument("--fps", type=int, default=30, help="sampling rate of the recorded states (the benchmark uses 24)")
    parser.add_argument("--frames", type=int, help="recorded samples t = i/fps, i = 0..frames-1 (default: duration*fps + 1)")
    parser.add_argument("--source-cache", type=Path, help="timed edit: accepted source simulation.npz of the same revision; its state at --edit-frame is restored")
    parser.add_argument("--edit-frame", type=int, help="timed edit: 1-based frame from which the edited parameters apply")
    args = parser.parse_args()
    spec = json.loads((HERE / "scene_spec.json").read_text(encoding="utf-8"))
    p = dict(spec["mat"])
    if args.curl_height is not None:
        base = float(p["thickness_m"]) / 2 + float(p["midplane_floor_clearance_m"])
        rise = args.curl_height - base
        radius = float(p["residual_curl_radius_m"])
        if not (0.0 < rise < 2.0 * radius):
            raise ValueError("curl height is incompatible with the fixed residual curl radius")
        p["residual_curl_angle_rad"] = math.acos(1.0 - rise / radius)
        p["residual_curl_arc_m"] = radius * p["residual_curl_angle_rad"]
    if args.young is not None:
        p["effective_young_modulus_pa"] = args.young
    s = dict(spec["simulation"])
    if args.viscosity_scale is not None:
        if args.viscosity_scale <= 0:
            raise ValueError("viscosity scale must be positive")
        for name in ("surface_shear_viscosity_pa_s_m", "surface_bulk_viscosity_pa_s_m", "hinge_bending_viscosity"):
            s[name] *= args.viscosity_scale
    if args.hinge_viscosity is not None:
        if args.viscosity_scale is not None:
            raise ValueError("use either viscosity scale or a hinge-only override, not both")
        s["hinge_bending_viscosity"] = args.hinge_viscosity
    s.update({"dt_s": args.dt, "grid_x": args.grid_x, "grid_y": args.grid_y})
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    fps = args.fps
    stride = round(1.0 / (fps * args.dt))
    if abs(stride * args.dt - 1.0 / fps) > 1e-12:
        raise ValueError(f"dt must divide 1/{fps} s exactly")
    settle_steps = round(args.settle / args.dt)
    frames = args.frames or round(args.duration * fps) + 1
    timed = None
    if args.source_cache is not None or args.edit_frame is not None:
        # Timed edit: frames 1..k-1 are the accepted source cache; the complete source state of frame k (every shell
        # vertex position and velocity, the ball's affine transform and velocity) is restored into a world built with
        # the edited parameters, which then advances to the end of the clip.
        if args.source_cache is None or args.edit_frame is None or args.delete_mat or args.add_wood_block or args.settled_cache is not None:
            raise ValueError("a timed edit needs --source-cache and --edit-frame and continues the source world only")
        j = args.edit_frame - 1
        with np.load(args.source_cache, allow_pickle=False) as archive:
            source = {name: archive[name] for name in archive.files}
        source_config = json.loads((args.source_cache.parent / "simulation_config.json").read_text(encoding="utf-8"))
        source_report = json.loads((args.source_cache.parent / "simulation_report.json").read_text(encoding="utf-8"))
        if (len(source["times"]) != frames or not 1 <= j < frames or abs(float(source["times"][j]) - j / fps) > 1e-12
                or source_config["simulation"]["fps"] != fps or source_config["simulation"]["dt_s"] != args.dt):
            raise ValueError("source cache clock, length or step differs from this run")
        timed = {"index": j, "source": source, "config": source_config, "report": source_report, "frames": frames}
        frames = frames - j

    rest, mat_faces, mesh_info = build_mat(args.grid_x, args.grid_y, p)
    ball_radius = args.ball_radius
    ball_start = np.array([-1.05, 0.0, ball_radius + 0.00065])
    ball = trimesh.creation.icosphere(subdivisions=3, radius=ball_radius)
    block = trimesh.creation.box(extents=[0.14, 0.22, 0.075]) if args.add_wood_block else None
    block_start = np.array([0.25, 0.0, 0.0447]) if args.add_wood_block else None
    if args.delete_mat:
        if args.add_wood_block or args.settled_cache is not None:
            raise ValueError("delete-mat is an independent rigid-floor world")
        simulate_deleted_mat_floor(args, out, p, s, mesh_info, ball, ball_start, fps, frames)
        return

    cfg = Scene.default_config()
    cfg["dt"] = args.dt
    cfg["gravity"] = [[0.0], [0.0], [-9.81]]
    cfg["contact"]["d_hat"] = float(s["contact_d_hat_m"])
    cfg["contact"]["eps_velocity"] = 0.0001
    cfg["newton"]["semi_implicit"]["enable"] = 0
    cfg["newton"]["velocity_tol"] = args.velocity_tol
    cfg["newton"]["max_iter"] = int(args.newton_max or s["newton_max_iterations"])
    cfg["linear_system"]["fem_preconditioner"] = "mas"
    cfg["linear_system"]["tol_rate"] = 1e-8
    cfg["line_search"]["max_iter"] = 64
    cfg["contact"]["adaptive"]["kappa_eval_scale"] = 1.0
    cfg["contact"]["adaptive"]["min_kappa"] = 1e8
    cfg["contact"]["adaptive"]["max_kappa"] = 1e13

    scene = Scene(cfg)
    scene.contact_tabular().default_model(float(p["friction_floor"]), 1e11)
    scene.objects().create("hardwood_floor").geometries().create(ground(0.0, np.array([0.0, 0.0, 1.0])))
    young = float(p["effective_young_modulus_pa"])
    poisson = float(p["poisson_ratio"])
    mat_mesh = ipc_trimesh(rest, mat_faces)
    label_surface(mat_mesh)
    NeoHookeanShell().apply_to(
        mat_mesh,
        ElasticModuli2D.youngs_poisson(young, poisson),
        mass_density=float(p["density_kg_m3"]),
        thickness=float(p["thickness_m"]) / 2,
    )
    DiscreteShellBending().apply_to(mat_mesh, young, poisson)
    apply_viscosity(mat_mesh, s["surface_shear_viscosity_pa_s_m"], s["surface_bulk_viscosity_pa_s_m"], s["hinge_bending_viscosity"])
    scene.objects().create("continuous_yoga_mat").geometries().create(mat_mesh)

    ball_mesh = ipc_trimesh(np.asarray(ball.vertices), np.asarray(ball.faces, dtype=np.int32))
    label_surface(ball_mesh)
    AffineBodyConstitution().apply_to(ball_mesh, 1.0e9, args.ball_mass / ball.volume)
    ball_transform = np.eye(4)
    ball_transform[:3, 3] = ball_start
    view(ball_mesh.transforms())[:] = ball_transform
    if args.delete_ball:
        if args.delete_mat or block is not None or args.settled_cache is None or timed is not None:
            raise ValueError("delete-ball continues the settled mat alone")
    else:
        scene.objects().create("weighted_medicine_ball").geometries().create(ball_mesh)
    if block is not None:
        block_mesh = ipc_trimesh(np.asarray(block.vertices), np.asarray(block.faces, dtype=np.int32))
        label_surface(block_mesh)
        AffineBodyConstitution().apply_to(block_mesh, 1.0e9, args.wood_block_mass / block.volume)
        block_transform = np.eye(4)
        block_transform[:3, 3] = block_start
        view(block_mesh.transforms())[:] = block_transform
        scene.objects().create("added_sliding_wood_block").geometries().create(block_mesh)

    provenance = {
        "execution_origin": "remote_server",
        "local_blender_used": False,
        "case": "source",
        "solver": "libuipc CUDA nonlinear shell + discrete bending + ABD rigid proxy + IPC + viscosity",
        "mat_present": not args.delete_mat,
        "mat": p,
        "ball": {"radius_m": ball_radius, "mass_kg": args.ball_mass, "rolling_speed_m_s": args.ball_speed, "initial_location_before_settle_m": ball_start.tolist()},
        "added_wood_block": None if block is None else {"mass_kg": args.wood_block_mass, "size_m": [0.14, 0.22, 0.075], "initial_location_before_settle_m": block_start.tolist()},
        **({"ball_present": False} if args.delete_ball else {}),
        "settled_initial_state": None if args.settled_cache is None else {
            "path": str(args.settled_cache.resolve()),
            "sha256": hashlib.sha256(args.settled_cache.read_bytes()).hexdigest(),
            "policy": "reuse the accepted baseline post-settle FEM/ABD state; zero all velocities before applying the edited launch",
        },
        "simulation": {**s, "settle_s": args.settle, "record_duration_s": args.duration, "fps": fps},
        "mesh": mesh_info,
        "solver_config": cfg,
        "viscosity_plugin": viscosity_manifest(),
    }
    write_json(out / "simulation_config.json", provenance)

    uipc.Logger.set_level(uipc.Logger.Warn)
    started = time.monotonic()
    # Keep the Engine alive for the entire World lifetime.  libuipc stores a
    # weak reference and rejects World.init if a temporary Engine is released.
    engine = Engine("cuda", str(out / "solver"))
    world = World(engine)
    world.init(scene)
    if not world.is_valid():
        raise RuntimeError("invalid initial IPC world")

    fem = fg = None
    mapping = np.empty(0, dtype=np.int64)
    if not args.delete_mat:
        fem = world.features().find(FiniteElementStateAccessorFeature)
        fg = fem.create_geometry()
        for name, value in ((builtin.position, np.zeros(3)), (builtin.velocity, np.zeros(3))):
            if fg.vertices().find(name) is None:
                fg.vertices().create(name, value)
        fem.copy_to(fg)
        initial_fem = np.asarray(fg.positions().view()).reshape(-1, 3)
        distance, mapping = cKDTree(initial_fem).query(rest)
        if float(distance.max()) > 1e-8:
            raise RuntimeError("FEM mapping failed")

    if args.delete_ball:
        abd = ag = None
        ball_index = block_index = None
    else:
        abd = world.features().find(AffineBodyStateAccessorFeature)
        ag = abd.create_geometry()
        for name, value in ((builtin.transform, np.eye(4)), (builtin.velocity, np.zeros((4, 4)))):
            if ag.instances().find(name) is None:
                ag.instances().create(name, value)
        abd.copy_to(ag)
        transforms = np.asarray(ag.instances().find(builtin.transform).view())
        ball_index = int(np.argmin(np.linalg.norm(transforms[:, :3, 3] - ball_start, axis=1)))
        block_index = None if block is None else int(np.argmin(np.linalg.norm(transforms[:, :3, 3] - block_start, axis=1)))
    if block_index is not None and block_index == ball_index:
        raise RuntimeError("ABD instance mapping assigned ball and block to the same index")

    if args.delete_mat and args.settled_cache is not None:
        raise ValueError("delete-mat must settle its floor-only world independently")
    if timed is not None:
        j, source = timed["index"], timed["source"]
        if source["mat_positions"].shape[1:] != rest.shape:
            raise ValueError("source cache mesh differs from this world")
        fem.copy_to(fg)
        view(fg.vertices().find(builtin.position)).reshape(-1, 3)[mapping] = source["mat_positions"][j]
        view(fg.vertices().find(builtin.velocity)).reshape(-1, 3)[mapping] = source["mat_velocities"][j]
        fem.copy_from(fg)
        abd.copy_to(ag)
        view(ag.instances().find(builtin.transform))[ball_index] = source["ball_transforms"][j]
        view(ag.instances().find(builtin.velocity))[ball_index] = source["ball_affine_velocities"][j]
        abd.copy_from(ag)
        world.retrieve()
        print("SOURCE_STATE_RESTORED frame", j + 1, flush=True)
    elif args.settled_cache is None:
        print("SETTLE_BEGIN", settle_steps, flush=True)
        for step in range(settle_steps):
            world.advance()
            world.retrieve()
            if step % max(1, settle_steps // 5) == 0:
                print("SETTLE", step, "/", settle_steps, flush=True)
    else:
        seed = np.load(args.settled_cache, allow_pickle=False)
        seed_mat = np.asarray(seed["settled_mat_positions"])
        seed_ball = np.asarray(seed["settled_ball_transform"])
        if seed_mat.shape != rest.shape:
            raise ValueError(f"settled cache mesh mismatch: {seed_mat.shape} != {rest.shape}")
        fem.copy_to(fg)
        view(fg.vertices().find(builtin.position)).reshape(-1, 3)[mapping] = seed_mat
        view(fg.vertices().find(builtin.velocity))[:] = 0.0
        fem.copy_from(fg)
        if not args.delete_ball:
            abd.copy_to(ag)
            view(ag.instances().find(builtin.transform))[ball_index] = seed_ball
            view(ag.instances().find(builtin.velocity))[ball_index] = 0.0
            abd.copy_from(ag)
        world.retrieve()
        print("SETTLED_STATE_REUSED", args.settled_cache, flush=True)

    if args.delete_ball:
        settled_transform = np.asarray(seed["settled_ball_transform"]).copy()
    else:
        abd.copy_to(ag)
        settled_transform = np.asarray(ag.instances().find(builtin.transform).view())[ball_index].copy()
    if timed is not None:
        settled_transform = np.asarray(timed["source"]["settled_ball_transform"]).copy()
    settled_gap = transformed_minimum_z(ball.vertices, settled_transform)
    if timed is not None:
        settled_mat = np.asarray(timed["source"]["settled_mat_positions"]).copy()
        settled_speed = np.zeros_like(settled_mat)
    elif args.delete_mat:
        settled_mat = np.empty((0, 3), dtype=np.float64)
        settled_speed = np.empty((0, 3), dtype=np.float64)
    else:
        fem.copy_to(fg)
        settled_mat = np.asarray(fg.positions().view()).reshape(-1, 3)[mapping].copy()
        settled_speed = np.asarray(fg.vertices().find(builtin.velocity).view()).reshape(-1, 3)[mapping]
    if not (0.0 <= settled_gap <= 0.001):
        raise RuntimeError(f"settled ball-floor gap outside visible/contact gate: {settled_gap}")
    settled_rms = 0.0 if args.delete_mat else float(np.sqrt(np.mean(np.sum(settled_speed ** 2, axis=1))))
    if settled_rms > 0.002:
        raise RuntimeError("mat not settled before ball launch")

    if timed is None and not args.delete_ball:
        velocity = np.zeros((4, 4))
        velocity[:3, 3] = [args.ball_speed, 0.0, 0.0]
        velocity[:3, :3] = skew([0.0, args.ball_speed / ball_radius, 0.0]) @ settled_transform[:3, :3]
        view(ag.instances().find(builtin.velocity))[ball_index] = velocity
        abd.copy_from(ag)
        world.retrieve()
    offset = 0 if timed is None else timed["index"]

    mat_positions = []
    mat_velocities = []
    ball_transforms = []
    ball_velocities = []
    block_transforms = []
    block_velocities = []
    rows = []
    curl_count = mesh_info["curl_samples"] * args.grid_y
    initial_curl_peak = None if args.delete_mat else float(np.max(settled_mat[:curl_count, 2]))
    for frame in range(frames):
        if args.delete_mat:
            x = np.empty((0, 3), dtype=np.float64)
            v = np.empty((0, 3), dtype=np.float64)
        else:
            fem.copy_to(fg)
            x = np.asarray(fg.positions().view()).reshape(-1, 3)[mapping].copy()
            v = np.asarray(fg.vertices().find(builtin.velocity).view()).reshape(-1, 3)[mapping].copy()
        if args.delete_ball:
            transform, affine_velocity = settled_transform.copy(), np.zeros((4, 4))
        else:
            abd.copy_to(ag)
            transform = np.asarray(ag.instances().find(builtin.transform).view())[ball_index].copy()
            affine_velocity = np.asarray(ag.instances().find(builtin.velocity).view())[ball_index].copy()
        mat_positions.append(x)
        mat_velocities.append(v)
        ball_transforms.append(transform)
        ball_velocities.append(affine_velocity)
        if block_index is not None:
            block_transform = np.asarray(ag.instances().find(builtin.transform).view())[block_index].copy()
            block_velocity = np.asarray(ag.instances().find(builtin.velocity).view())[block_index].copy()
            block_transforms.append(block_transform)
            block_velocities.append(block_velocity)
        if frame == 0 and timed is not None:
            j, source = timed["index"], timed["source"]
            handoff = {"mat_positions": float(np.abs(x - source["mat_positions"][j]).max()),
                       "mat_velocities": float(np.abs(v - source["mat_velocities"][j]).max()),
                       "ball_transforms": float(np.abs(transform - source["ball_transforms"][j]).max()),
                       "ball_affine_velocities": float(np.abs(affine_velocity - source["ball_affine_velocities"][j]).max())}
            if max(handoff.values()) >= 1e-8:
                raise RuntimeError(f"source state was not restored exactly: {handoff}")
            timed["handoff"] = handoff
            write_json(out / "state_handoff.json", {"edit_frame": j + 1, "time_s": j / fps, "source_cache": str(args.source_cache),
                                                    "max_abs_error": handoff, "verified": True})
        rows.append({
            "frame": offset + frame + 1,
            "time_s": (offset + frame) / fps,
            "ball_center_m": transform[:3, 3].tolist(),
            "ball_bottom_gap_m": transformed_minimum_z(ball.vertices, transform),
            "ball_linear_velocity_m_s": affine_velocity[:3, 3].tolist(),
            "curl_peak_m": None if args.delete_mat else float(np.max(x[:curl_count, 2])),
            "curl_peak_change_m": None if args.delete_mat else float(np.max(x[:curl_count, 2]) - initial_curl_peak),
            "wood_block_center_m": None if block_index is None else block_transform[:3, 3].tolist(),
        })
        if frame % 5 == 0:
            print("FRAME", frame + 1, "/", frames, "ball_x", round(transform[0, 3], 4), "gap", round(rows[-1]["ball_bottom_gap_m"], 6), "curl", None if args.delete_mat else round(rows[-1]["curl_peak_m"], 5), flush=True)
        if frame < frames - 1:
            for _ in range(stride):
                world.advance()
                world.retrieve()

    np.savez_compressed(
        out / "simulation.npz",
        mat_positions=np.asarray(mat_positions),
        mat_velocities=np.asarray(mat_velocities),
        mat_rest_positions=np.empty((0, 3)) if args.delete_mat else rest,
        mat_faces=np.empty((0, 3), dtype=np.int32) if args.delete_mat else mat_faces,
        mat_present=np.asarray([not args.delete_mat], dtype=np.uint8),
        ball_transforms=np.asarray(ball_transforms),
        ball_affine_velocities=np.asarray(ball_velocities),
        ball_vertices=np.asarray(ball.vertices),
        ball_faces=np.asarray(ball.faces),
        **({"ball_present": np.asarray([False], dtype=np.uint8)} if args.delete_ball else {}),
        times=(offset + np.arange(frames, dtype=np.float64)) / fps,
        settled_mat_positions=settled_mat,
        settled_ball_transform=settled_transform,
        has_wood_block=np.asarray([block is not None], dtype=np.uint8),
        wood_block_transforms=np.asarray(block_transforms),
        wood_block_affine_velocities=np.asarray(block_velocities),
        wood_block_vertices=np.empty((0, 3)) if block is None else np.asarray(block.vertices),
        wood_block_faces=np.empty((0, 3), dtype=np.int32) if block is None else np.asarray(block.faces),
    )
    bx = np.asarray(ball_transforms)[:, 0, 3]
    curl = None if args.delete_mat else np.array([row["curl_peak_m"] for row in rows])
    report = {
        "status": "review_required",
        "reason": "source collision diagnostic; requires dt/2, mesh refinement, contact-frame render and pixel contact audit",
        "settled_ball_floor_gap_m": settled_gap,
        "settled_mat_rms_speed_m_s": settled_rms,
        "ball_final_x_m": float(bx[-1]),
        "ball_max_x_m": float(np.max(bx)),
        "wood_block_final_center_m": None if block is None else np.asarray(block_transforms)[-1, :3, 3].tolist(),
        "wood_block_displacement_m": None if block is None else (np.asarray(block_transforms)[-1, :3, 3] - np.asarray(block_transforms)[0, :3, 3]).tolist(),
        "curl_initial_peak_m": initial_curl_peak,
        "curl_min_peak_m": None if args.delete_mat else float(np.min(curl)),
        "curl_final_peak_m": None if args.delete_mat else float(curl[-1]),
        "manual_motion": False,
        "manual_deformation": False,
        "wall_seconds": time.monotonic() - started,
        "rows": rows,
    }
    if timed is not None:
        # Merge: frames 1..k-1 of the source cache, frames k.. of this continuation; simulation.npz is the full clip.
        j, source = timed["index"], timed["source"]
        (out / "simulation.npz").rename(out / "continuation.npz")
        with np.load(out / "continuation.npz", allow_pickle=False) as archive:
            continuation = {name: archive[name] for name in archive.files}
        per_frame = ("mat_positions", "mat_velocities", "ball_transforms", "ball_affine_velocities", "times")
        merged = {name: (np.concatenate([source[name][:j], value]) if name in per_frame else value) for name, value in continuation.items()}
        for name in per_frame:
            if len(merged[name]) != timed["frames"] or not np.array_equal(merged[name][:j], source[name][:j]):
                raise RuntimeError("merged cache prefix differs from the source: " + name)
        np.savez_compressed(out / "simulation.npz", **merged)
        rows = timed["report"]["rows"][:j] + rows
        bx = np.asarray([row["ball_center_m"][0] for row in rows])
        curl = np.asarray([row["curl_peak_m"] for row in rows])
        report.update({"rows": rows, "ball_final_x_m": float(bx[-1]), "ball_max_x_m": float(np.max(bx)),
                       "curl_min_peak_m": float(np.min(curl)), "curl_final_peak_m": float(curl[-1]),
                       "settled_mat_rms_speed_m_s": timed["report"]["settled_mat_rms_speed_m_s"]})
        provenance["simulation"]["record_duration_s"] = timed["config"]["simulation"]["record_duration_s"]
        provenance["timed_edit"] = {
            "frame": j + 1, "time_s": j / fps, "source_frames_kept": [1, j], "continued_frames": [j + 1, timed["frames"]],
            "source_cache": str(args.source_cache), "source_cache_sha256": hashlib.sha256(args.source_cache.read_bytes()).hexdigest(),
            "params_before": {"ball_mass_kg": timed["config"]["ball"]["mass_kg"]}, "params_after": {"ball_mass_kg": args.ball_mass},
            "state_handoff_max_abs": timed["handoff"], "continuation_cache": "continuation.npz", "merged_cache": "simulation.npz"}
        write_json(out / "simulation_config.json", provenance)
    write_json(out / "simulation_report.json", report)
    print("COMPLETE", json.dumps({key: report[key] for key in ("settled_ball_floor_gap_m", "ball_max_x_m", "curl_min_peak_m", "wall_seconds")}), flush=True)


if __name__ == "__main__":
    main()
