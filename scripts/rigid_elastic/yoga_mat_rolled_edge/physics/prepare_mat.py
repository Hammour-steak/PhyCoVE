"""Remote libuipc relaxation of a real-scale PVC yoga mat with storage curl.

This is intentionally a mat-only calibration stage.  It establishes whether a
short residual curl survives gravity and floor contact without using Blender or
placing a ball.  The later collision scene must repeat the accepted preparation
before it gives the ball velocity.
"""
from pathlib import Path
import argparse
import json
import sys
import time

import numpy as np
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / "tools/manifold3d_deps"), str(ROOT / "tools/ipc_probe_deps")]
import uipc
from uipc import builtin
from uipc.core import Engine, FiniteElementStateAccessorFeature, Scene, World
from uipc.geometry import ground, label_surface, trimesh as ipc_trimesh
from uipc.constitution import DiscreteShellBending, ElasticModuli2D, NeoHookeanShell

from viscosity import apply_viscosity, manifest as viscosity_manifest


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def build_mat(nx, ny, p):
    """Create a circular residual-curvature lip joined tangentially to flat mat."""
    length = float(p["length_m"])
    width = float(p["width_m"])
    radius = float(p["residual_curl_radius_m"])
    angle = float(p["residual_curl_angle_rad"])
    arc = radius * angle
    if abs(arc - float(p["residual_curl_arc_m"])) > 1e-9:
        raise ValueError("residual curl arc must equal radius times angle")
    if not (0 < arc < length):
        raise ValueError("invalid curl arc length")

    base = float(p["thickness_m"]) / 2 + float(p["midplane_floor_clearance_m"])
    # libuipc's finite-thickness shell sanity check requires non-neighbouring
    # primitives not to begin closer than the full 6 mm contact thickness.
    # Ten samples leave about 7 mm along this 63 mm arc: resolved enough for
    # the gentle storage curl without creating an invalid over-refined shell.
    curl_n = min(10, nx - 2)
    theta = np.linspace(angle, 0.0, curl_n)
    transition_x = -0.31
    curl_x = transition_x - radius * np.sin(theta)
    curl_z = base + radius * (1.0 - np.cos(theta))
    flat_n = nx - curl_n + 1
    flat_x = np.linspace(transition_x, transition_x + length - arc, flat_n)[1:]
    center = np.column_stack([
        np.r_[curl_x, flat_x],
        np.r_[curl_z, np.full(flat_x.shape, base)],
    ])
    if len(center) != nx:
        raise AssertionError((len(center), nx))
    ys = np.linspace(-width / 2, width / 2, ny)
    vertices = np.array([[xz[0], y, xz[1]] for xz in center for y in ys], dtype=np.float64)
    faces = []
    for i in range(nx - 1):
        for j in range(ny - 1):
            q = i * ny + j
            if (i + j) % 2 == 0:
                faces.extend(((q, q + ny, q + ny + 1), (q, q + ny + 1, q + 1)))
            else:
                faces.extend(((q, q + ny, q + 1), (q + 1, q + ny, q + ny + 1)))
    info = {
        "curl_samples": curl_n,
        "flat_midplane_z_m": base,
        "initial_tip_height_m": float(curl_z[0]),
        "initial_tip_rise_m": float(curl_z[0] - base),
        "initial_curl_arc_m": arc,
        "initial_curl_radius_m": radius,
        "initial_curl_angle_rad": angle,
        "maximum_longitudinal_edge_m": float(np.max(np.linalg.norm(np.diff(center, axis=0), axis=1))),
        "maximum_transverse_edge_m": float(width / (ny - 1)),
    }
    return vertices, np.asarray(faces, dtype=np.int32), info


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--young", type=float)
    parser.add_argument("--dt", type=float)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--grid-x", type=int)
    parser.add_argument("--grid-y", type=int)
    args = parser.parse_args()

    spec = json.loads((HERE / "scene_spec.json").read_text(encoding="utf-8"))
    p = dict(spec["mat"])
    s = dict(spec["simulation"])
    if args.young is not None:
        p["effective_young_modulus_pa"] = args.young
    if args.dt is not None:
        s["dt_s"] = args.dt
    if args.duration is not None:
        s["duration_s"] = args.duration
    if args.grid_x is not None:
        s["grid_x"] = args.grid_x
    if args.grid_y is not None:
        s["grid_y"] = args.grid_y

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    dt = float(s["dt_s"])
    sample_hz = int(s["sample_hz"])
    stride = round(1.0 / (sample_hz * dt))
    if abs(stride * dt - 1.0 / sample_hz) > 1e-12:
        raise ValueError("dt must divide the diagnostic sample period exactly")
    samples = round(float(s["duration_s"]) * sample_hz) + 1
    rest, faces, mesh_info = build_mat(int(s["grid_x"]), int(s["grid_y"]), p)

    cfg = Scene.default_config()
    cfg["dt"] = dt
    cfg["gravity"] = [[0.0], [0.0], [-9.81]]
    cfg["contact"]["d_hat"] = float(s["contact_d_hat_m"])
    cfg["contact"]["eps_velocity"] = 0.0001
    cfg["newton"]["semi_implicit"]["enable"] = 0
    cfg["newton"]["velocity_tol"] = 0.0001
    cfg["newton"]["max_iter"] = int(s["newton_max_iterations"])
    cfg["linear_system"]["fem_preconditioner"] = "mas"
    cfg["linear_system"]["tol_rate"] = 1e-8
    cfg["line_search"]["max_iter"] = 64
    cfg["contact"]["adaptive"]["kappa_eval_scale"] = 1.0
    cfg["contact"]["adaptive"]["min_kappa"] = 1e8
    cfg["contact"]["adaptive"]["max_kappa"] = 1e13

    scene = Scene(cfg)
    scene.contact_tabular().default_model(float(p["friction_floor"]), 1e11)
    scene.objects().create("hardwood_floor").geometries().create(ground(0.0, np.array([0.0, 0.0, 1.0])))
    mesh = ipc_trimesh(rest, faces)
    label_surface(mesh)
    young = float(p["effective_young_modulus_pa"])
    poisson = float(p["poisson_ratio"])
    NeoHookeanShell().apply_to(
        mesh,
        ElasticModuli2D.youngs_poisson(young, poisson),
        mass_density=float(p["density_kg_m3"]),
        thickness=float(p["thickness_m"]) / 2,
    )
    DiscreteShellBending().apply_to(mesh, young, poisson)
    apply_viscosity(
        mesh,
        s["surface_shear_viscosity_pa_s_m"],
        s["surface_bulk_viscosity_pa_s_m"],
        s["hinge_bending_viscosity"],
    )
    scene.objects().create("continuous_yoga_mat").geometries().create(mesh)

    provenance = {
        "execution_origin": "remote_server",
        "local_blender_used": False,
        "solver": "libuipc CUDA NeoHookeanShell + DiscreteShellBending + IPC + native shell viscosity",
        "model_scope": "mat-only physical relaxation before ball introduction",
        "mat": p,
        "simulation": s,
        "mesh": mesh_info,
        "solver_config": cfg,
        "viscosity_plugin": viscosity_manifest(),
    }
    write_json(out / "preparation_config.json", provenance)

    uipc.Logger.set_level(uipc.Logger.Warn)
    started = time.monotonic()
    engine = Engine("cuda", str(out / "solver"))
    world = World(engine)
    world.init(scene)
    if not world.is_valid():
        raise RuntimeError("invalid initial IPC world")
    fem = world.features().find(FiniteElementStateAccessorFeature)
    geometry = fem.create_geometry()
    for name, value in ((builtin.position, np.zeros(3)), (builtin.velocity, np.zeros(3))):
        if geometry.vertices().find(name) is None:
            geometry.vertices().create(name, value)
    fem.copy_to(geometry)
    initial_all = np.asarray(geometry.positions().view()).reshape(-1, 3)
    distance, mapping = cKDTree(initial_all).query(rest)
    if float(distance.max()) > 1e-8:
        raise RuntimeError("FEM vertex mapping failed")

    positions = []
    velocities = []
    rows = []
    curl_vertex_count = int(mesh_info["curl_samples"]) * int(s["grid_y"])
    for sample in range(samples):
        fem.copy_to(geometry)
        x = np.asarray(geometry.positions().view()).reshape(-1, 3)[mapping].copy()
        v = np.asarray(geometry.vertices().find(builtin.velocity).view()).reshape(-1, 3)[mapping].copy()
        positions.append(x)
        velocities.append(v)
        tip = x[: int(s["grid_y"]), 2]
        speed = np.linalg.norm(v, axis=1)
        rows.append({
            "sample": sample,
            "time_s": sample / sample_hz,
            "tip_height_mean_m": float(np.mean(tip)),
            "tip_height_range_m": [float(np.min(tip)), float(np.max(tip))],
            "curl_peak_height_m": float(np.max(x[:curl_vertex_count, 2])),
            "rms_vertex_speed_m_s": float(np.sqrt(np.mean(speed ** 2))),
            "peak_vertex_speed_m_s": float(np.max(speed)),
            "minimum_vertex_z_m": float(np.min(x[:, 2])),
        })
        if sample % 5 == 0:
            print("SAMPLE", sample, "/", samples - 1, "tip", round(rows[-1]["tip_height_mean_m"], 5), "rms_v", round(rows[-1]["rms_vertex_speed_m_s"], 6), flush=True)
        if sample < samples - 1:
            for _ in range(stride):
                world.advance()
                world.retrieve()

    positions = np.asarray(positions)
    velocities = np.asarray(velocities)
    np.savez_compressed(
        out / "mat_preparation.npz",
        positions=positions,
        velocities=velocities,
        rest_positions=rest,
        faces=faces,
        times=np.arange(samples, dtype=np.float64) / sample_hz,
    )
    acceptance = spec["acceptance"]
    window = max(2, round(float(acceptance["window_s"]) * sample_hz) + 1)
    recent = rows[-window:]
    tip_drift = max(r["tip_height_mean_m"] for r in recent) - min(r["tip_height_mean_m"] for r in recent)
    final_tip = rows[-1]["tip_height_mean_m"]
    plausible = acceptance["plausible_final_tip_height_m"]
    checks = {
        "rms_speed": max(r["rms_vertex_speed_m_s"] for r in recent) <= float(acceptance["max_rms_vertex_speed_m_s"]),
        "peak_speed": max(r["peak_vertex_speed_m_s"] for r in recent) <= float(acceptance["max_peak_vertex_speed_m_s"]),
        "tip_drift": tip_drift <= float(acceptance["max_tip_height_drift_m"]),
        "tip_height_plausible": float(plausible[0]) <= final_tip <= float(plausible[1]),
        "no_floor_penetration": min(r["minimum_vertex_z_m"] for r in rows) >= float(p["thickness_m"]) / 2 - 1e-5,
        "finite": bool(np.isfinite(positions).all() and np.isfinite(velocities).all()),
    }
    report = {
        "status": "accepted_mat_preparation" if all(checks.values()) else "review_required",
        "checks": checks,
        "effective_young_modulus_pa": young,
        "initial_tip_height_m": mesh_info["initial_tip_height_m"],
        "final_tip_height_m": final_tip,
        "tip_height_drift_last_window_m": tip_drift,
        "maximum_speed_last_window_m_s": max(r["peak_vertex_speed_m_s"] for r in recent),
        "rms_speed_last_window_m_s": max(r["rms_vertex_speed_m_s"] for r in recent),
        "wall_seconds": time.monotonic() - started,
        "rows": rows,
    }
    write_json(out / "preparation_report.json", report)
    print("COMPLETE", report["status"], json.dumps(checks, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
