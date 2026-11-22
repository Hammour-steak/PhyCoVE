"""Independent CPU audit of a solved ball/yoga-mat cache (simulation.npz with its config and report)."""
from pathlib import Path
import argparse
import json
import numpy as np


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def transformed_minimum_z(vertices, transform):
    world = vertices @ transform[:3, :3].T + transform[:3, 3]
    return float(np.min(world[:, 2]))


def axial_vector(skew_matrix):
    return np.array([skew_matrix[2, 1], skew_matrix[0, 2], skew_matrix[1, 0]])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path)
    args = parser.parse_args()
    case = args.case.resolve()
    cache = np.load(case / "simulation.npz", allow_pickle=False)
    config = json.loads((case / "simulation_config.json").read_text(encoding="utf-8"))
    simulation = json.loads((case / "simulation_report.json").read_text(encoding="utf-8"))

    vertices = cache["ball_vertices"]
    transforms = cache["ball_transforms"]
    velocities = cache["ball_affine_velocities"]
    positions = cache["mat_positions"]
    mat_present = bool(config.get("mat_present", True))
    times = cache["times"]
    radius = float(config["ball"]["radius_m"])
    thickness = float(config["mat"]["thickness_m"])
    grid_y = int(config["simulation"]["grid_y"])
    ball_x = transforms[:, 0, 3]
    front_x = ball_x + radius
    if mat_present:
        tip_x = positions[:, :grid_y, 0].mean(axis=1)
        # Audit only the contiguous approach phase.  A rejected ball can move
        # left of the tip again after impact; those rebound frames are not
        # "pre-contact" and must not be mixed into the no-slip launch check.
        approach_mask = front_x < tip_x - 0.002
        first_contact = np.flatnonzero(~approach_mask)
        precontact = np.arange(first_contact[0] if len(first_contact) else len(transforms))
    else:
        precontact = np.arange(len(transforms))
    if len(precontact) < 3:
        raise RuntimeError("too few pre-contact frames for rolling audit")

    exact_gap = np.array([transformed_minimum_z(vertices, transform) for transform in transforms])
    report_gap = np.array([row["ball_bottom_gap_m"] for row in simulation["rows"]])
    singular_values = np.array([np.linalg.svd(transform[:3, :3], compute_uv=False) for transform in transforms])
    rigid_strain = float(np.max(np.abs(singular_values - 1.0)))
    center_steps = np.linalg.norm(np.diff(transforms[:, :3, 3], axis=0), axis=1)
    velocity_steps = np.linalg.norm(np.diff(velocities[:, :3, 3], axis=0), axis=1)

    roll_error = []
    for index in precontact:
        linear = velocities[index, :3, 3]
        # ABD stores dA/dt.  Convert it to the spatial velocity gradient
        # L=dA/dt*A^-1 before extracting angular velocity.
        gradient = velocities[index, :3, :3] @ np.linalg.inv(transforms[index, :3, :3])
        angular = axial_vector(0.5 * (gradient - gradient.T))
        roll_error.append(abs(float(linear[0] - angular[1] * radius)))
    roll_error = np.asarray(roll_error)
    mat_bottom = positions[:, :, 2].min(axis=1) - thickness / 2 if mat_present else None
    dt_frame = float(np.median(np.diff(times)))
    checks = {
        "finite": bool(all(np.isfinite(array).all() for array in (positions, transforms, velocities))),
        "first_frame_exact_ball_gap_le_1mm": bool(0.0 <= exact_gap[0] <= 0.001),
        "exact_gap_matches_simulation_report": bool(np.max(np.abs(exact_gap - report_gap)) <= 1e-9),
        "no_ball_floor_penetration": bool(np.min(exact_gap) >= -1e-5),
        "no_mat_floor_penetration": True if not mat_present else bool(np.min(mat_bottom) >= -1e-5),
        "abd_ball_is_rigid_within_0p2_percent": bool(rigid_strain <= 0.002),
        "precontact_roll_error_le_10mm_s": bool(np.max(roll_error) <= 0.010),
        "no_center_teleport_over_6cm_per_video_frame": bool(np.max(center_steps) <= 0.06),
        "no_velocity_jump_over_3m_s_per_video_frame": bool(np.max(velocity_steps) <= 3.0),
    }
    block_metrics = None
    if "has_wood_block" in cache and bool(cache["has_wood_block"][0]):
        block_vertices = cache["wood_block_vertices"]
        block_transforms = cache["wood_block_transforms"]
        block_velocities = cache["wood_block_affine_velocities"]
        block_gap = np.array([transformed_minimum_z(block_vertices, transform) for transform in block_transforms])
        block_singular_values = np.array([np.linalg.svd(transform[:3, :3], compute_uv=False) for transform in block_transforms])
        block_rigid_strain = float(np.max(np.abs(block_singular_values - 1.0)))
        block_steps = np.linalg.norm(np.diff(block_transforms[:, :3, 3], axis=0), axis=1)
        checks.update({
            "wood_block_finite": bool(all(np.isfinite(array).all() for array in (block_transforms, block_velocities))),
            "no_wood_block_floor_penetration": bool(np.min(block_gap) >= -1e-5),
            "abd_wood_block_is_rigid_within_0p2_percent": bool(block_rigid_strain <= 0.002),
            "no_wood_block_teleport_over_6cm_per_video_frame": bool(np.max(block_steps) <= 0.06),
        })
        block_metrics = {
            "minimum_exact_wood_block_floor_gap_m": float(np.min(block_gap)),
            "maximum_wood_block_abd_principal_stretch_error": block_rigid_strain,
            "maximum_wood_block_center_step_m": float(np.max(block_steps)),
            "wood_block_displacement_m": (block_transforms[-1, :3, 3] - block_transforms[0, :3, 3]).tolist(),
        }
    result = {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "metrics": {
            "first_frame_exact_ball_floor_gap_m": float(exact_gap[0]),
            "minimum_exact_ball_floor_gap_m": float(np.min(exact_gap)),
            "maximum_gap_report_difference_m": float(np.max(np.abs(exact_gap - report_gap))),
            "minimum_mat_bottom_gap_m": None if not mat_present else float(np.min(mat_bottom)),
            "maximum_abd_principal_stretch_error": rigid_strain,
            "maximum_precontact_no_slip_error_m_s": float(np.max(roll_error)),
            "maximum_center_step_m": float(np.max(center_steps)),
            "maximum_center_speed_implied_m_s": float(np.max(center_steps) / dt_frame),
            "maximum_linear_velocity_step_m_s": float(np.max(velocity_steps)),
            "precontact_frames": precontact.tolist(),
            "wood_block": block_metrics,
        },
        "scope": "Numerical/geometry gate only. Manual review of remote-rendered profile and contact frames remains mandatory.",
    }
    write_json(case / "source_audit.json", result)
    print(json.dumps(result, indent=2))
    if result["status"] != "passed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
