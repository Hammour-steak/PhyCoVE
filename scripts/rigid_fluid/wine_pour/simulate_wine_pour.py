"""Deterministic annotations for the rigid-glass / wine-pour scene.

Mantaflow resolves the liquid surface.  This lightweight model records the
prescribed bottle stream and volume balance used by the benchmark metadata;
it does not claim native two-way coupling between liquid and glass.
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


@dataclass(frozen=True)
class PhysicsConfig:
    fps: int = 24
    duration_sec: float = 4.0
    pour_start_sec: float = 0.35
    pour_end_sec: float = 3.35
    wine_density_kg_m3: float = 990.0
    wine_kinematic_viscosity_m2_s: float = 1.7e-6
    flow_rate_ml_s: float = 60.0
    nozzle_speed_m_s: float = 0.45
    nozzle_speed_change_frame: int | None = None
    nozzle_speed_after_m_s: float | None = None
    wine_presence: tuple[int, ...] = (1,)
    glass_presence: tuple[int, ...] = (1,)
    gravity_m_s2: float = 9.81
    glass_inner_bottom_z_m: float = 0.006
    glass_lip_z_m: float = 0.125


# Interior radius profile of the procedural stemless wine glass.
INNER_PROFILE = (
    (0.006, 0.018),
    (0.018, 0.029),
    (0.060, 0.045),
    (0.100, 0.039),
    (0.125, 0.037),
)


def _segment_volume(z0: float, r0: float, z1: float, r1: float, height: float) -> float:
    """Volume of a linearly tapered circular section up to ``height``."""
    h = max(0.0, min(z1 - z0, height))
    if h == 0.0:
        return 0.0
    radius = r0 + (r1 - r0) * h / (z1 - z0)
    return math.pi * h * (r0 * r0 + r0 * radius + radius * radius) / 3.0


def capacity_below(height_z: float) -> float:
    volume = 0.0
    for (z0, r0), (z1, r1) in zip(INNER_PROFILE, INNER_PROFILE[1:]):
        if height_z <= z0:
            break
        volume += _segment_volume(z0, r0, z1, r1, height_z - z0)
        if height_z < z1:
            break
    return volume


def height_for_volume(volume_m3: float) -> float:
    if volume_m3 <= 0.0:
        return INNER_PROFILE[0][0]
    capacity = capacity_below(INNER_PROFILE[-1][0])
    if volume_m3 >= capacity:
        return INNER_PROFILE[-1][0]
    lo, hi = INNER_PROFILE[0][0], INNER_PROFILE[-1][0]
    for _ in range(60):
        mid = (lo + hi) * 0.5
        if capacity_below(mid) < volume_m3:
            lo = mid
        else:
            hi = mid
    return (lo + hi) * 0.5


def simulate(config: PhysicsConfig) -> dict:
    if config.fps <= 0 or config.duration_sec <= 0:
        raise ValueError("fps and duration must be positive")
    if not 0.0 <= config.pour_start_sec < config.pour_end_sec <= config.duration_sec:
        raise ValueError("pour interval must lie inside the clip")
    if min(
        config.wine_density_kg_m3,
        config.wine_kinematic_viscosity_m2_s,
        config.flow_rate_ml_s,
        config.nozzle_speed_m_s,
        config.gravity_m_s2,
    ) <= 0.0:
        raise ValueError("physical values must be positive")
    if tuple(config.wine_presence) not in {(0,), (1,)}:
        raise ValueError("wine_presence must be [0] or [1]")
    if tuple(config.glass_presence) not in {(0,), (1,)}:
        raise ValueError("glass_presence must be [0] or [1]")

    frame_end = int(round(config.duration_sec * config.fps))
    timed_speed_values = (config.nozzle_speed_change_frame, config.nozzle_speed_after_m_s)
    if (timed_speed_values[0] is None) != (timed_speed_values[1] is None):
        raise ValueError("timed nozzle speed requires both frame and after-speed")
    if config.nozzle_speed_change_frame is not None:
        if not 1 <= config.nozzle_speed_change_frame <= frame_end:
            raise ValueError("nozzle_speed_change_frame must lie inside the clip")
        if config.nozzle_speed_after_m_s < 0.0:
            raise ValueError("nozzle_speed_after_m_s must be non-negative")
    wine_present = bool(config.wine_presence[0])
    glass_present = bool(config.glass_presence[0])
    capacity_m3 = capacity_below(config.glass_lip_z_m)
    flow_m3_s = config.flow_rate_ml_s * 1.0e-6
    nozzle_radius = math.sqrt(flow_m3_s / (math.pi * config.nozzle_speed_m_s))
    change_time_sec = (
        (config.nozzle_speed_change_frame - 1) / config.fps
        if config.nozzle_speed_change_frame is not None else None
    )
    flow_after_m3_s = (
        flow_m3_s * config.nozzle_speed_after_m_s / config.nozzle_speed_m_s
        if config.nozzle_speed_after_m_s is not None else flow_m3_s
    )
    frames = []
    for frame in range(1, frame_end + 1):
        time_sec = (frame - 1) / config.fps
        poured_until = min(time_sec, config.pour_end_sec)
        if change_time_sec is None:
            before_sec = max(0.0, poured_until - config.pour_start_sec)
            after_sec = 0.0
        else:
            before_sec = max(0.0, min(poured_until, change_time_sec) - config.pour_start_sec)
            after_sec = max(0.0, poured_until - max(config.pour_start_sec, change_time_sec))
        emitted = (flow_m3_s * before_sec + flow_after_m3_s * after_sec) if wine_present else 0.0
        retained = min(emitted, capacity_m3) if glass_present else 0.0
        speed_changed = config.nozzle_speed_change_frame is not None and frame >= config.nozzle_speed_change_frame
        current_speed = config.nozzle_speed_after_m_s if speed_changed else config.nozzle_speed_m_s
        current_flow = flow_after_m3_s if speed_changed else flow_m3_s
        frames.append({
            "frame": frame,
            "time_sec": time_sec,
            "stream_active": wine_present and current_speed > 0.0 and config.pour_start_sec <= time_sec < config.pour_end_sec,
            "nozzle_speed_m_s": current_speed,
            "flow_rate_ml_s": current_flow * 1.0e6,
            "emitted_volume_ml": emitted * 1.0e6,
            "retained_volume_ml": retained * 1.0e6,
            "spilled_volume_ml": (emitted - retained) * 1.0e6,
            "analytic_fill_height_m": height_for_volume(retained) if glass_present else None,
        })

    return {
        "schema_version": 1,
        "simulator": "pcve_prescribed_wine_inflow",
        "interaction_category": "rigid_fluid",
        "coupling": "prescribed inflow drives Mantaflow against a static rigid glass; no two-way rigid feedback",
        "fps": config.fps,
        "frame_start": 1,
        "frame_end": frame_end,
        "duration_sec": frame_end / config.fps,
        "objects": {
            "wine": {
                "present": wine_present,
                "density_kg_m3": config.wine_density_kg_m3,
                "kinematic_viscosity_m2_s": config.wine_kinematic_viscosity_m2_s,
                "flow_rate_ml_s": config.flow_rate_ml_s,
                "nozzle_speed_m_s": config.nozzle_speed_m_s,
                "nozzle_speed_change_frame": config.nozzle_speed_change_frame,
                "nozzle_speed_after_m_s": config.nozzle_speed_after_m_s,
                "nozzle_radius_m": nozzle_radius,
            },
            "glass": {
                "present": glass_present,
                "type": "static rigid stemless wine glass",
                "analytic_capacity_ml": capacity_m3 * 1.0e6,
            },
        },
        "config": asdict(config),
        "frames": frames,
    }


def parse_args() -> argparse.Namespace:
    defaults = PhysicsConfig()
    parser = argparse.ArgumentParser(description="Write wine-pour benchmark annotations.")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--fps", type=int, default=defaults.fps)
    parser.add_argument("--duration-sec", type=float, default=defaults.duration_sec)
    parser.add_argument("--pour-start-sec", type=float, default=defaults.pour_start_sec)
    parser.add_argument("--pour-end-sec", type=float, default=defaults.pour_end_sec)
    parser.add_argument("--wine-density-kg-m3", type=float, default=defaults.wine_density_kg_m3)
    parser.add_argument("--wine-kinematic-viscosity-m2-s", type=float, default=defaults.wine_kinematic_viscosity_m2_s)
    parser.add_argument("--flow-rate-ml-s", type=float, default=defaults.flow_rate_ml_s)
    parser.add_argument("--nozzle-speed-m-s", type=float, default=defaults.nozzle_speed_m_s)
    parser.add_argument("--nozzle-speed-change-frame", type=int, default=defaults.nozzle_speed_change_frame)
    parser.add_argument("--nozzle-speed-after-m-s", type=float, default=defaults.nozzle_speed_after_m_s)
    parser.add_argument("--wine-presence", nargs=1, type=int, choices=(0, 1), default=defaults.wine_presence)
    parser.add_argument("--glass-presence", nargs=1, type=int, choices=(0, 1), default=defaults.glass_presence)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = PhysicsConfig(
        fps=args.fps,
        duration_sec=args.duration_sec,
        pour_start_sec=args.pour_start_sec,
        pour_end_sec=args.pour_end_sec,
        wine_density_kg_m3=args.wine_density_kg_m3,
        wine_kinematic_viscosity_m2_s=args.wine_kinematic_viscosity_m2_s,
        flow_rate_ml_s=args.flow_rate_ml_s,
        nozzle_speed_m_s=args.nozzle_speed_m_s,
        nozzle_speed_change_frame=args.nozzle_speed_change_frame,
        nozzle_speed_after_m_s=args.nozzle_speed_after_m_s,
        wine_presence=tuple(args.wine_presence),
        glass_presence=tuple(args.glass_presence),
    )
    result = simulate(config)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

