"""Deterministic rigid toy-car trajectory for the fish-tank Mantaflow scene.

A die-cast toy car is dropped into an aquarium that holds only water.  Blender Mantaflow
treats the animated car collision hull kinematically, so this module supplies
the rigid motion: gravity, displaced-volume buoyancy, added mass, quadratic
form drag, Stokes drag for viscosity counterfactuals, a hydrostatic righting
moment that levels the car, and the contact with the tank's glass bottom.  The
same trajectory is the benchmark ground truth and the renderer's obstacle path;
it is prescribed one-way coupling, not a native two-way rigid/fluid solve.

All positions are world coordinates in metres with +Z up.  The car's long axis
is world Y; Euler X is pitch (nose up/down) and Euler Y is roll.
"""

from __future__ import annotations
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
from dataclasses import asdict, dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class PhysicsConfig:
    fps: int = 24
    duration_sec: float = 4.0
    substeps: int = 96
    trajectory_subframes: int = 24
    # Toy car: BlenderKit "Rally Toy Car Race" scaled to a 90 mm 1:43-style
    # die-cast.  Volume is the closed-mesh volume of the scaled asset.
    toy_length_m: float = 0.0901
    toy_width_m: float = 0.0399
    toy_height_m: float = 0.0308
    toy_volume_m3: float = 6.156e-5
    toy_mass_kg: float = 0.085
    water_density_kg_m3: float = 998.0
    water_kinematic_viscosity_m2_s: float = 1.0e-6
    # Photoscanned moss rock, normalized to 85 x 67 x 40 mm.  The volume is
    # an ellipsoid proxy; 275 g gives a plausible stone density (~2310 kg/m3).
    rock_width_m: float = 0.085
    rock_depth_m: float = 0.067
    rock_height_m: float = 0.040
    rock_volume_m3: float = 1.193e-4
    rock_mass_kg: float = 0.275
    rock_center_x_m: float = 1.705
    rock_center_y_m: float = -1.320
    toy_presence: tuple[int, ...] = (1,)
    water_presence: tuple[int, ...] = (1,)
    gravity_m_s2: float = 9.81
    # Aquarium geometry (world).  The renderer measures these from the placed
    # assets and refuses to run if they drift from the values below.
    water_surface_z_m: float = 0.758
    substrate_z_m: float = 0.485  # top of the 10 mm glass base
    tank_inner_x_m: tuple[float, float] = (1.4598, 1.7902)
    tank_inner_y_m: tuple[float, float] = (-1.42, -0.94)
    # Release state.
    release_time_sec: float = 0.25
    drop_x_m: float = 1.515
    drop_y_m: float = -1.18
    drop_bottom_height_above_surface_m: float = 0.22
    # Released vertically: no authored lateral impulse.  This keeps the car
    # over the same tank position while buoyancy produces vertical bobbing.
    initial_velocity_m_s: tuple[float, float, float] = (0.0, 0.0, 0.0)
    initial_pitch_rad: float = -0.30
    initial_roll_rad: float = 0.10
    initial_yaw_rad: float = 0.0
    initial_pitch_rate_rad_s: float = 1.10
    initial_roll_rate_rad_s: float = -0.35
    initial_yaw_rate_rad_s: float = 0.25
    # Reduced hydrodynamics.
    vertical_drag_coefficient: float = 1.05
    horizontal_drag_coefficient: float = 0.85
    added_mass_coefficient: float = 0.5
    # Linear free-surface radiation damping for positively buoyant bodies.
    # Quadratic form drag becomes vanishingly small near rest, which otherwise
    # leaves small toys bobbing like an almost lossless spring.  This ratio is
    # applied only while a body that can float is partially submerged, so the
    # source car's sinking trajectory is unchanged.
    floating_heave_damping_ratio: float = 0.40
    righting_frequency_hz: float = 1.3
    righting_damping_ratio: float = 0.45
    substrate_restitution: float = 0.12
    substrate_friction_decay_s: float = 0.08


# Placement the PhysicsConfig geometry defaults are expressed in: the tank on
# the kids'-bedroom toy chest, long axis along world Y, front facing -X.
REFERENCE_TANK_ORIGIN = (1.625, -1.18, 0.428)
REFERENCE_TANK_YAW = -math.pi / 2.0


def place_config(config: "PhysicsConfig", origin: tuple[float, float, float], yaw: float) -> "PhysicsConfig":
    """Move the tank-relative geometry of ``config`` to another tank placement.

    Every world-space field (water level, glass bottom, inner glass bounds,
    drop point, initial drift and yaw) is carried by the same rigid motion as
    the tank, so the drop is identical relative to the tank in any room.  Only
    quarter-turn yaw changes are allowed, which keeps the inner bounds
    axis-aligned for the clamp in ``simulate``.
    """
    turn = yaw - REFERENCE_TANK_YAW
    quarter = round(turn / (math.pi / 2.0))
    if abs(turn - quarter * math.pi / 2.0) > 1e-6:
        raise ValueError("tank yaw must differ from the reference by a multiple of 90 degrees")
    c, s = round(math.cos(turn)), round(math.sin(turn))
    ox, oy, oz = REFERENCE_TANK_ORIGIN

    def point(x: float, y: float) -> tuple[float, float]:
        dx, dy = x - ox, y - oy
        return origin[0] + c * dx - s * dy, origin[1] + s * dx + c * dy

    corners = [point(x, y) for x in config.tank_inner_x_m for y in config.tank_inner_y_m]
    drop_x, drop_y = point(config.drop_x_m, config.drop_y_m)
    rock_x, rock_y = point(config.rock_center_x_m, config.rock_center_y_m)
    vx, vy, vz = config.initial_velocity_m_s
    dz = origin[2] - oz
    return replace(
        config,
        water_surface_z_m=config.water_surface_z_m + dz,
        substrate_z_m=config.substrate_z_m + dz,
        tank_inner_x_m=(min(p[0] for p in corners), max(p[0] for p in corners)),
        tank_inner_y_m=(min(p[1] for p in corners), max(p[1] for p in corners)),
        drop_x_m=drop_x,
        drop_y_m=drop_y,
        rock_center_x_m=rock_x,
        rock_center_y_m=rock_y,
        initial_velocity_m_s=(c * vx - s * vy, s * vx + c * vy, vz),
        initial_yaw_rad=config.initial_yaw_rad + turn,
    )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _floating_heave_damping_force(
    *, rho: float, gravity: float, volume: float, half_height: float,
    effective_mass: float, submerged: float, velocity_z: float,
    mass: float, damping_ratio: float,
) -> float:
    """Return a free-surface heave damping force for a floating body.

    The critical-damping scale comes from the local hydrostatic stiffness of
    the same linear submerged-volume model used by the buoyancy calculation.
    A smooth window removes the term in air and when fully submerged.  It is
    intentionally disabled for negatively buoyant bodies, preserving the
    baseline sinking trajectory and applying only to the edited float cases.
    """
    if rho * volume <= mass or not 0.0 < submerged < 1.0 or damping_ratio <= 0.0:
        return 0.0
    stiffness = rho * gravity * volume / (2.0 * half_height)
    critical = 2.0 * math.sqrt(stiffness * effective_mass)
    surface_window = 4.0 * submerged * (1.0 - submerged)
    return -damping_ratio * critical * surface_window * velocity_z


def _half_extent_z(config: PhysicsConfig, pitch: float, roll: float) -> float:
    """Vertical half-extent of the car's bounding box at the given tilt."""
    return 0.5 * (
        config.toy_height_m * abs(math.cos(pitch)) * abs(math.cos(roll))
        + config.toy_length_m * abs(math.sin(pitch))
        + config.toy_width_m * abs(math.sin(roll))
    )


def submerged_fraction(config: PhysicsConfig, z: float, pitch: float, roll: float) -> float:
    half = _half_extent_z(config, pitch, roll)
    return _clamp((config.water_surface_z_m - (z - half)) / (2.0 * half), 0.0, 1.0)


def validate(config: PhysicsConfig) -> None:
    if config.fps <= 0 or config.duration_sec <= 0 or config.substeps <= 0:
        raise ValueError("fps, duration and substeps must be positive")
    if config.trajectory_subframes <= 0 or config.substeps % config.trajectory_subframes:
        raise ValueError("trajectory_subframes must be a positive divisor of substeps")
    if min(
        config.toy_mass_kg,
        config.toy_volume_m3,
        config.water_density_kg_m3,
        config.water_kinematic_viscosity_m2_s,
        config.gravity_m_s2,
    ) <= 0:
        raise ValueError("mass, volume, density, viscosity and gravity must be positive")
    for name in ("toy_presence", "water_presence"):
        if tuple(getattr(config, name)) not in {(0,), (1,)}:
            raise ValueError(f"{name} must be [0] or [1]")
    if not config.substrate_z_m < config.water_surface_z_m:
        raise ValueError("the substrate must lie below the water surface")


def _simulate_rock(config: PhysicsConfig, schedule: list[dict], include_fractional_keys: bool) -> dict:
    """Vertical reduced-order buoyancy trajectory for the aquarium rock.

    The visual scan is driven by this centre-of-mass path and a smooth
    ellipsoid proxy drives Mantaflow.  This is prescribed one-way coupling,
    matching the car model's stated limitation.
    """
    dt = 1.0 / (config.fps * config.substeps)
    key_stride = config.substeps // config.trajectory_subframes
    frame_end = max(2, int(round(config.duration_sec * config.fps)))
    rho = config.water_density_kg_m3
    mass = config.rock_mass_kg
    volume = config.rock_volume_m3
    area = config.rock_width_m * config.rock_depth_m
    half_h = 0.5 * config.rock_height_m
    z = config.substrate_z_m + half_h
    vz = 0.0
    resting = True
    first_lift = None
    frames = []
    fractional = []
    schedule_by_frame = {int(item["frame"]): item["params"] for item in schedule}

    for frame in range(1, frame_end + 1):
        params = schedule_by_frame.get(frame, {})
        rho = float(params.get("water_density_kg_m3", rho))
        if resting and rho * volume > mass * 1.001:
            resting = False
            first_lift = frame
        if frame > 1 and not resting:
            for substep in range(1, config.substeps + 1):
                submerged = _clamp((config.water_surface_z_m - (z - half_h)) / config.rock_height_m, 0.0, 1.0)
                m_eff = mass + config.added_mass_coefficient * rho * volume * submerged
                force = -mass * config.gravity_m_s2 + rho * config.gravity_m_s2 * volume * submerged
                force -= 0.5 * rho * 1.05 * area * submerged * abs(vz) * vz
                force += _floating_heave_damping_force(
                    rho=rho,
                    gravity=config.gravity_m_s2,
                    volume=volume,
                    half_height=half_h,
                    effective_mass=m_eff,
                    submerged=submerged,
                    velocity_z=vz,
                    mass=mass,
                    damping_ratio=config.floating_heave_damping_ratio,
                )
                vz += force / m_eff * dt
                z += vz * dt
                floor = config.substrate_z_m + half_h
                if z <= floor:
                    z, vz, resting = floor, 0.0, True
                if include_fractional_keys and substep < config.substeps and substep % key_stride == 0:
                    fractional.append({
                        "frame": frame - 1 + substep / config.substeps,
                        "location": [config.rock_center_x_m, config.rock_center_y_m, z],
                    })
        submerged = _clamp((config.water_surface_z_m - (z - half_h)) / config.rock_height_m, 0.0, 1.0)
        frames.append({
            "frame": frame,
            "time_sec": (frame - 1) / config.fps,
            "location": [config.rock_center_x_m, config.rock_center_y_m, z],
            "velocity_m_s": [0.0, 0.0, vz],
            "submerged_fraction": submerged,
        })
    return {
        "frames": frames,
        "fractional_keyframes": fractional,
        "first_lift_frame": first_lift,
        "final_center_z_m": z,
        "floats": z > config.water_surface_z_m - config.rock_height_m,
    }


def simulate(config: PhysicsConfig, *, include_fractional_keys: bool = False,
             schedule: list[dict] | None = None) -> dict:
    """Integrate the reduced rigid-body model.

    Fractional keys preserve the impact path between frames for Mantaflow's
    effector subframes; the CLI omits them so the public ground truth stays
    compact.
    """
    validate(config)
    toy_present = bool(config.toy_presence[0])
    water_present = bool(config.water_presence[0])
    frame_end = max(2, int(round(config.duration_sec * config.fps)))
    dt = 1.0 / (config.fps * config.substeps)
    key_stride = config.substeps // config.trajectory_subframes

    m = config.toy_mass_kg
    volume = config.toy_volume_m3
    rho = config.water_density_kg_m3
    nu = config.water_kinematic_viscosity_m2_s
    mu = rho * nu
    base_mu = rho * PhysicsConfig.water_kinematic_viscosity_m2_s
    area_top = config.toy_length_m * config.toy_width_m
    area_side = config.toy_length_m * config.toy_height_m
    area_front = config.toy_width_m * config.toy_height_m
    equivalent_radius = (3.0 * volume / (4.0 * math.pi)) ** (1.0 / 3.0)
    omega_0 = 2.0 * math.pi * config.righting_frequency_hz

    x, y = config.drop_x_m, config.drop_y_m
    pitch, roll, yaw = config.initial_pitch_rad, config.initial_roll_rad, config.initial_yaw_rad
    z = config.water_surface_z_m + config.drop_bottom_height_above_surface_m + _half_extent_z(config, pitch, roll)
    vx, vy, vz = config.initial_velocity_m_s
    w_pitch, w_roll, w_yaw = (
        config.initial_pitch_rate_rad_s,
        config.initial_roll_rate_rad_s,
        config.initial_yaw_rate_rad_s,
    )
    resting = False
    first_contact = None
    substrate_contact = None
    deepest_z = z
    peak_speed = 0.0
    peak_fraction = 0.0
    frames: list[dict] = []
    fractional: list[dict] = []
    lo_x = config.tank_inner_x_m[0] + 0.5 * config.toy_width_m
    hi_x = config.tank_inner_x_m[1] - 0.5 * config.toy_width_m
    lo_y = config.tank_inner_y_m[0] + 0.5 * config.toy_length_m
    hi_y = config.tank_inner_y_m[1] - 0.5 * config.toy_length_m
    schedule = list(schedule or [])
    schedule_by_frame = {int(item["frame"]): item["params"] for item in schedule}

    def pose() -> tuple[list[float], list[float]]:
        return [x, y, z], [pitch, roll, yaw]

    for frame in range(1, frame_end + 1):
        params = schedule_by_frame.get(frame, {})
        rho = float(params.get("water_density_kg_m3", rho))
        nu = float(params.get("water_kinematic_viscosity_m2_s", nu))
        mu = rho * nu
        base_mu = rho * PhysicsConfig.water_kinematic_viscosity_m2_s
        # A body resting on the glass must wake when a timed density edit makes
        # its maximum buoyancy exceed its weight.
        if resting and water_present and rho * volume > m * 1.001:
            resting = False
        if not toy_present:
            frames.append({"frame": frame, "time_sec": (frame - 1) / config.fps, "present": False})
            continue
        interval_start = (frame - 2) / config.fps
        if frame > 1 and interval_start >= config.release_time_sec - 1e-9 and not resting:
            for substep in range(1, config.substeps + 1):
                f = submerged_fraction(config, z, pitch, roll) if water_present else 0.0
                # Buoyancy and added mass act on the displaced volume.
                buoyancy = rho * config.gravity_m_s2 * volume * f
                m_eff = m + config.added_mass_coefficient * rho * volume * f
                speed = math.sqrt(vx * vx + vy * vy + vz * vz)
                fz = -m * config.gravity_m_s2 + buoyancy
                fx = fy = 0.0
                if f > 0.0:
                    fz -= 0.5 * rho * config.vertical_drag_coefficient * area_top * f * abs(vz) * vz
                    fx -= 0.5 * rho * config.horizontal_drag_coefficient * area_side * f * abs(vx) * vx
                    fy -= 0.5 * rho * config.horizontal_drag_coefficient * area_front * f * abs(vy) * vy
                    fz += _floating_heave_damping_force(
                        rho=rho,
                        gravity=config.gravity_m_s2,
                        volume=volume,
                        half_height=_half_extent_z(config, pitch, roll),
                        effective_mass=m_eff,
                        submerged=f,
                        velocity_z=vz,
                        mass=m,
                        damping_ratio=config.floating_heave_damping_ratio,
                    )
                vx += fx / m_eff * dt
                vy += fy / m_eff * dt
                vz += fz / m_eff * dt
                # Excess viscous resistance (zero for the water baseline) is
                # applied as an exact exponential decay so the high-viscosity
                # counterfactual stays stable at this time step.
                excess_mu = max(0.0, mu - base_mu)
                if f > 0.0 and excess_mu > 0.0:
                    rate = 6.0 * math.pi * excess_mu * equivalent_radius * f / m_eff
                    decay = math.exp(-rate * dt)
                    vx, vy, vz = vx * decay, vy * decay, vz * decay
                x += vx * dt
                y += vy * dt
                z += vz * dt

                # Hydrostatic righting: the cast chassis sits below the centre
                # of buoyancy, so tilt relaxes as a damped oscillator that only
                # acts on the immersed part.  In air the car spins freely.
                if f > 0.0:
                    k = omega_0 * omega_0 * f
                    c = 2.0 * config.righting_damping_ratio * omega_0 * f
                    if excess_mu > 0.0:
                        c += 20.0 * math.pi * excess_mu * equivalent_radius * f / m_eff
                    w_pitch += (-k * pitch - c * w_pitch) * dt
                    w_roll += (-k * roll - c * w_roll) * dt
                    w_yaw *= math.exp(-c * dt)
                pitch += w_pitch * dt
                roll += w_roll * dt
                yaw += w_yaw * dt

                x = _clamp(x, lo_x, hi_x)
                y = _clamp(y, lo_y, hi_y)
                floor_center = config.substrate_z_m + _half_extent_z(config, pitch, roll)
                if z <= floor_center:
                    if substrate_contact is None:
                        substrate_contact = frame - 1 + substep / config.substeps
                    z = floor_center
                    vz = max(0.0, -vz * config.substrate_restitution)
                    # Sand contact: sliding and tilt die out quickly.
                    decay = math.exp(-dt / config.substrate_friction_decay_s)
                    vx, vy = vx * decay, vy * decay
                    pitch, roll = pitch * decay, roll * decay
                    w_pitch, w_roll, w_yaw = w_pitch * decay, w_roll * decay, w_yaw * decay
                    if abs(vz) < 1e-3 and math.hypot(vx, vy) < 1e-3 and abs(pitch) + abs(roll) < 1e-3:
                        vx = vy = vz = 0.0
                        w_pitch = w_roll = w_yaw = 0.0
                        resting = True

                if include_fractional_keys and substep < config.substeps and substep % key_stride == 0:
                    location, rotation = pose()
                    fractional.append({
                        "frame": frame - 1 + substep / config.substeps,
                        "location": location,
                        "rotation_euler": rotation,
                    })
                if resting:
                    break

        f = submerged_fraction(config, z, pitch, roll) if water_present else 0.0
        if first_contact is None and f > 0.0:
            first_contact = frame
        deepest_z = min(deepest_z, z)
        peak_speed = max(peak_speed, math.sqrt(vx * vx + vy * vy + vz * vz))
        peak_fraction = max(peak_fraction, f)
        location, rotation = pose()
        frames.append({
            "frame": frame,
            "time_sec": (frame - 1) / config.fps,
            "present": True,
            "location": location,
            "rotation_euler": rotation,
            "velocity_m_s": [vx, vy, vz],
            "submerged_fraction": f,
        })

    if toy_present and water_present:
        coupling = "analytic rigid trajectory drives a Mantaflow moving obstacle; no native two-way FSI"
    elif water_present:
        coupling = "no toy is present; the aquarium water is a static source-matched volume"
    elif toy_present:
        coupling = "no water is present; analytic rigid motion resolves gravity and substrate contact"
    else:
        coupling = "no interacting objects are present"
    floor_center = config.substrate_z_m + 0.5 * config.toy_height_m
    rock = _simulate_rock(config, schedule, include_fractional_keys)
    result = {
        "schema_version": 1,
        "simulator": "pcve_prescribed_rigid_fish_tank_toy",
        "coupling": coupling,
        "fps": config.fps,
        "frame_start": 1,
        "frame_end": frame_end,
        "duration_sec": frame_end / config.fps,
        "objects": {
            "toy_car": {
                "present": toy_present,
                "dimensions_m": [config.toy_width_m, config.toy_length_m, config.toy_height_m],
                "volume_m3": volume,
                "mass_kg": m,
                "mean_density_kg_m3": m / volume,
            },
            "water": {
                "present": water_present,
                "density_kg_m3": rho,
                "kinematic_viscosity_m2_s": config.water_kinematic_viscosity_m2_s,
                "surface_z_m": config.water_surface_z_m,
            },
            "moss_rock": {
                "dimensions_m": [config.rock_width_m, config.rock_depth_m, config.rock_height_m],
                "volume_m3": config.rock_volume_m3,
                "mass_kg": config.rock_mass_kg,
                "mean_density_kg_m3": config.rock_mass_kg / config.rock_volume_m3,
            },
        },
        "physics": {"gravity_m_s2": [0.0, 0.0, -config.gravity_m_s2]},
        "quality": {
            "first_water_contact_frame": first_contact,
            "substrate_contact_frame": substrate_contact,
            "deepest_toy_center_z_m": deepest_z if toy_present else None,
            "peak_toy_speed_m_s": peak_speed if toy_present else None,
            "peak_submerged_fraction": peak_fraction if toy_present else None,
            "final_toy_center_z_m": z if toy_present else None,
            "toy_rests_on_substrate": toy_present and abs(z - floor_center) < 2e-3,
            "toy_floats": toy_present and water_present and z > config.water_surface_z_m - config.toy_height_m,
            "rock_first_lift_frame": rock["first_lift_frame"],
            "rock_final_center_z_m": rock["final_center_z_m"],
            "rock_floats": rock["floats"],
        },
        "config": asdict(config),
        "timed_edits": schedule,
        "frames": frames,
        "rock_frames": rock["frames"],
    }
    if include_fractional_keys:
        result["fractional_keyframes"] = fractional
        result["rock_fractional_keyframes"] = rock["fractional_keyframes"]
    return result


def parse_args() -> argparse.Namespace:
    defaults = PhysicsConfig()
    parser = argparse.ArgumentParser(description="Simulate the fish-tank toy-car trajectory.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--toy-mass-kg", type=float, default=defaults.toy_mass_kg)
    parser.add_argument("--water-density-kg-m3", type=float, default=defaults.water_density_kg_m3)
    parser.add_argument(
        "--water-kinematic-viscosity-m2-s", type=float, default=defaults.water_kinematic_viscosity_m2_s
    )
    parser.add_argument("--toy-presence", nargs=1, type=int, choices=(0, 1), default=defaults.toy_presence)
    parser.add_argument("--water-presence", nargs=1, type=int, choices=(0, 1), default=defaults.water_presence)
    parser.add_argument("--gravity-m-s2", type=float, default=defaults.gravity_m_s2)
    return parser.parse_args()


def config_from_args(args: argparse.Namespace) -> PhysicsConfig:
    return PhysicsConfig(**{
        **asdict(PhysicsConfig()),
        "toy_mass_kg": args.toy_mass_kg,
        "water_density_kg_m3": args.water_density_kg_m3,
        "water_kinematic_viscosity_m2_s": args.water_kinematic_viscosity_m2_s,
        "toy_presence": tuple(args.toy_presence),
        "water_presence": tuple(args.water_presence),
        "gravity_m_s2": args.gravity_m_s2,
    })


def main() -> None:
    args = parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(simulate(config_from_args(args)), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
