"""Deterministic annotations for the orange-juice dispenser scene.

Mantaflow resolves the liquid surface.  This module records the prescribed
inflow and cylindrical-cup volume balance used by the benchmark metadata; it
does not claim native two-way fluid/rigid coupling.
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
from dataclasses import asdict, dataclass
from pathlib import Path


BASELINE_EMITTER_RADIUS_M = 0.0035
BASELINE_NOZZLE_SPEED_M_S = 1.20
TEMPLATE_NOZZLE_SPEED_M_S = 0.25
SOURCE_PRESET = "small_half_cup"
INLET_PROTOCOL = "fixed_aperture_conservative_surface_inlet_6"


@dataclass(frozen=True)
class PhysicsConfig:
    fps: int = 24
    duration_sec: float = 4.0
    pour_start_sec: float = 0.0
    pour_end_sec: float = 4.0
    orange_juice_density_kg_m3: float = 1040.0
    orange_juice_kinematic_viscosity_m2_s: float = 4.0e-6
    nozzle_speed_m_s: float = BASELINE_NOZZLE_SPEED_M_S
    nozzle_speed_change_sec: float | None = None
    nozzle_speed_after_m_s: float | None = None
    orange_juice_presence: tuple[int, ...] = (1,)
    glass_presence: tuple[int, ...] = (1,)
    gravity_m_s2: float = 9.81
    glass_inner_radius_m: float = 0.036
    glass_inner_bottom_z_m: float = 0.022
    glass_lip_z_m: float = 0.133


def geometric_flow_rate_ml_s(config: PhysicsConfig) -> float:
    """Prescribed geometric flux; baked retained volume is measured separately."""
    return math.pi * BASELINE_EMITTER_RADIUS_M**2 * config.nozzle_speed_m_s * 1.0e6



def speed_at_time(time_sec, initial_speed, change_sec=None, after_speed=None):
    """Right-continuous outlet control: the new speed applies at t >= change."""
    return after_speed if change_sec is not None and time_sec >= change_sec else initial_speed


def integrated_speed(begin_sec, end_sec, initial_speed, change_sec=None, after_speed=None):
    """Exact time integral of one speed step, including a straddling substep."""
    if end_sec <= begin_sec:
        return 0.0
    if change_sec is None:
        return initial_speed * (end_sec - begin_sec)
    before = max(0.0, min(end_sec, change_sec) - begin_sec)
    after = max(0.0, end_sec - max(begin_sec, change_sec))
    return initial_speed * before + after_speed * after


def speed_schedule(config):
    if config.nozzle_speed_change_sec is None:
        return []
    return [{"property": "dispenser.flow_speed", "at_sec": config.nozzle_speed_change_sec,
             "applies_from_frame": round(config.nozzle_speed_change_sec * config.fps) + 1,
             "before_m_s": config.nozzle_speed_m_s, "after_m_s": config.nozzle_speed_after_m_s,
             "interpolation": "CONSTANT"}]


def glass_capacity_m3(config: PhysicsConfig) -> float:
    height = config.glass_lip_z_m - config.glass_inner_bottom_z_m
    return math.pi * config.glass_inner_radius_m**2 * height


def simulate(config: PhysicsConfig) -> dict:
    if config.fps <= 0 or config.duration_sec <= 0:
        raise ValueError("fps and duration must be positive")
    if not 0.0 <= config.pour_start_sec < config.pour_end_sec <= config.duration_sec:
        raise ValueError("pour interval must lie inside the clip")
    physical_values = (
        config.orange_juice_density_kg_m3,
        config.orange_juice_kinematic_viscosity_m2_s,
        config.nozzle_speed_m_s,
        config.gravity_m_s2,
        config.glass_inner_radius_m,
    )
    if any(not math.isfinite(value) or value <= 0.0 for value in physical_values):
        raise ValueError("physical values must be finite and positive")
    if tuple(config.orange_juice_presence) not in {(0,), (1,)}:
        raise ValueError("orange_juice_presence must be [0] or [1]")
    if tuple(config.glass_presence) not in {(0,), (1,)}:
        raise ValueError("glass_presence must be [0] or [1]")

    scheduled = config.nozzle_speed_change_sec is not None
    if scheduled != (config.nozzle_speed_after_m_s is not None):
        raise ValueError("speed change time and after-speed must be provided together")
    if scheduled:
        when, after = config.nozzle_speed_change_sec, config.nozzle_speed_after_m_s
        if not math.isfinite(when) or not config.pour_start_sec < when < config.pour_end_sec:
            raise ValueError("speed change must lie strictly inside the active pour")
        if not math.isfinite(after) or after < 0.0:
            raise ValueError("after-speed must be finite and nonnegative")
        if not math.isclose(when * config.fps, round(when * config.fps), abs_tol=1e-8):
            raise ValueError("speed change must align with a video-frame boundary")

    frame_end = int(round(config.duration_sec * config.fps))
    juice_present = bool(config.orange_juice_presence[0])
    glass_present = bool(config.glass_presence[0])
    capacity = glass_capacity_m3(config)
    nominal_flow_ml_s = geometric_flow_rate_ml_s(config)
    flow_m3_s = nominal_flow_ml_s * 1.0e-6
    frames = []
    for frame in range(1, frame_end + 1):
        time_sec = frame / config.fps
        poured_sec = max(0.0, min(time_sec, config.pour_end_sec) - config.pour_start_sec)
        emitted = flow_m3_s * poured_sec if juice_present else 0.0
        if scheduled and juice_present:
            travel = integrated_speed(config.pour_start_sec, max(config.pour_start_sec, min(time_sec, config.pour_end_sec)),
                                      config.nozzle_speed_m_s, config.nozzle_speed_change_sec, config.nozzle_speed_after_m_s)
            emitted = math.pi * BASELINE_EMITTER_RADIUS_M**2 * travel
        control_time_sec = (frame - 1) / config.fps
        current_speed = speed_at_time(control_time_sec, config.nozzle_speed_m_s,
                                     config.nozzle_speed_change_sec, config.nozzle_speed_after_m_s)
        frames.append({
            "frame": frame,
            "time_sec": time_sec,
            "control_time_sec": control_time_sec,
            "stream_active": juice_present and current_speed > 0.0 and config.pour_start_sec <= (control_time_sec if scheduled else time_sec) < config.pour_end_sec,
            "nozzle_speed_m_s": current_speed if juice_present else 0.0,
            "geometric_flow_rate_ml_s": math.pi * BASELINE_EMITTER_RADIUS_M**2 * current_speed * 1e6 if juice_present and config.pour_start_sec <= time_sec < config.pour_end_sec else 0.0,
            "expected_geometric_emitted_volume_ml": emitted * 1.0e6,
            "retained_volume_ml": None if juice_present else 0.0,
            "liquid_volume_measurement_status": "requires_baked_surface" if juice_present else "exact_zero_absent_object",
        })

    return {
        "schema_version": 3,
        "simulator": "pcve_prescribed_orange_juice_inflow",
        "interaction_category": "rigid_fluid",
        "coupling": "prescribed inflow against a static rigid glass; no native two-way feedback",
        "fps": config.fps,
        "frame_start": 1,
        "frame_end": frame_end,
        "duration_sec": frame_end / config.fps,
        "objects": {
            "orange_juice": {
                "present": juice_present,
                "density_kg_m3": config.orange_juice_density_kg_m3,
                "kinematic_viscosity_m2_s": config.orange_juice_kinematic_viscosity_m2_s,
                "nozzle_speed_m_s": config.nozzle_speed_m_s,
                "emitter_radius_m": BASELINE_EMITTER_RADIUS_M,
                "geometric_flow_rate_ml_s": nominal_flow_ml_s,
                "flow_rate_definition": "Q = pi * emitter_radius_m^2 * nozzle_speed_m_s; measured baked volumes are separate.",
            },
            "glass": {
                "present": glass_present,
                "type": "static rigid cylindrical drinking glass",
                "analytic_capacity_ml": capacity * 1.0e6,
            },
        },
        "outlet_speed_schedule": speed_schedule(config),
        "config": asdict(config),
        "inlet_protocol": INLET_PROTOCOL,
        "annotation_status": "expected_supply_only_until_bake" if juice_present else "exact_zero_absent_object",
        "frames": frames,
    }


def parse_args() -> argparse.Namespace:
    defaults = PhysicsConfig()
    parser = argparse.ArgumentParser(description="Write orange-juice dispenser annotations.")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--fps", type=int, default=defaults.fps)
    parser.add_argument("--duration-sec", type=float, default=defaults.duration_sec)
    parser.add_argument("--nozzle-speed-change-sec", type=float)
    parser.add_argument("--nozzle-speed-after-m-s", type=float)
    parser.add_argument("--pour-start-sec", type=float, default=defaults.pour_start_sec)
    parser.add_argument("--pour-end-sec", type=float, default=defaults.pour_end_sec)
    parser.add_argument("--orange-juice-density-kg-m3", type=float, default=defaults.orange_juice_density_kg_m3)
    parser.add_argument(
        "--orange-juice-kinematic-viscosity-m2-s",
        type=float,
        default=defaults.orange_juice_kinematic_viscosity_m2_s,
    )
    parser.add_argument("--nozzle-speed-m-s", type=float, default=defaults.nozzle_speed_m_s)
    parser.add_argument("--orange-juice-presence", nargs=1, type=int, choices=(0, 1), default=defaults.orange_juice_presence)
    parser.add_argument("--glass-presence", nargs=1, type=int, choices=(0, 1), default=defaults.glass_presence)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = PhysicsConfig(
        fps=args.fps,
        duration_sec=args.duration_sec,
        pour_start_sec=args.pour_start_sec,
        pour_end_sec=args.pour_end_sec,
        orange_juice_density_kg_m3=args.orange_juice_density_kg_m3,
        orange_juice_kinematic_viscosity_m2_s=args.orange_juice_kinematic_viscosity_m2_s,
        nozzle_speed_m_s=args.nozzle_speed_m_s,
        nozzle_speed_change_sec=args.nozzle_speed_change_sec,
        nozzle_speed_after_m_s=args.nozzle_speed_after_m_s,
        orange_juice_presence=tuple(args.orange_juice_presence),
        glass_presence=tuple(args.glass_presence),
    )
    result = simulate(config)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
