"""Configure, bake, render and verify the approved juice-dispenser scene.

Run through Blender with ``assets/scenes/juice_dispenser_orange_cup/scene_template.blend`` open.  Every physical
case receives its own cache directory before any solver or inflow mutation.
"""

from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'tools'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'render')
# PCVE_UNIFIED_ENTRY_END

import argparse
import inspect
import hashlib
import json
import re
import math
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import bpy
import numpy as np


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from simulate_juice_dispenser_orange_cup import (  # noqa: E402
    BASELINE_EMITTER_RADIUS_M,
    TEMPLATE_NOZZLE_SPEED_M_S,
    SOURCE_PRESET,
    PhysicsConfig,
    geometric_flow_rate_ml_s,
    INLET_PROTOCOL,
    simulate, speed_at_time, speed_schedule,
)
from flux_boundary import FluxBoundary
from liquid_measurements import measure_surface


TEMPLATE_SCENE_ID = "rigid_fluid_juice_dispenser_orange_cup"


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    defaults = PhysicsConfig()
    parser = argparse.ArgumentParser(description="Bake and render the PCVE juice-dispenser scene.")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--scenario-overrides-json", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--resolution", nargs=2, type=int, default=(1280, 720))
    parser.add_argument("--fps", type=int, default=defaults.fps)
    parser.add_argument("--duration-sec", type=float, default=defaults.duration_sec)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--domain-resolution", type=int, default=160)
    parser.add_argument("--timesteps-min", type=int, default=8)
    parser.add_argument("--flip-ratio", type=float, default=0.92)
    parser.add_argument("--timesteps-max", type=int, default=16)
    parser.add_argument("--orange-juice-density-kg-m3", type=float, default=defaults.orange_juice_density_kg_m3)
    parser.add_argument(
        "--orange-juice-kinematic-viscosity-m2-s",
        type=float,
        default=defaults.orange_juice_kinematic_viscosity_m2_s,
    )
    parser.add_argument("--inlet-aperture-mode", choices=("binary","fractional_circle"), default="binary")
    parser.add_argument("--inlet-target-area-m2", type=float)
    parser.add_argument("--inlet-plane-z-m", type=float)
    parser.add_argument("--viscosity-cg-accuracy", type=float, default=1e-7)
    parser.add_argument("--solver-vendor", type=Path, default=HERE.parents[2]/".runtime/juice_dispenser_orange_cup/solver_vendor")
    parser.add_argument("--viscosity-solver", choices=("auto", "diffusion", "coupled_spd"), default="auto",
                        help="auto: symmetric implicit strain-rate viscosity for nu >= 1e-3 m^2/s; diffusion otherwise")
    parser.add_argument("--nozzle-speed-m-s", type=float, default=defaults.nozzle_speed_m_s)
    parser.add_argument("--nozzle-speed-change-sec", type=float)
    parser.add_argument("--nozzle-speed-after-m-s", type=float)
    parser.add_argument("--pour-start-sec", type=float, default=defaults.pour_start_sec)
    parser.add_argument("--pour-end-sec", type=float, default=defaults.pour_end_sec)
    parser.add_argument("--orange-juice-presence", nargs=1, type=int, choices=(0, 1), default=defaults.orange_juice_presence)
    parser.add_argument("--glass-presence", nargs=1, type=int, choices=(0, 1), default=defaults.glass_presence)
    parser.add_argument("--skip-fluid-bake", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--render-stills-only", action="store_true")
    parser.add_argument("--preview-frames", nargs="+", type=int)
    parser.add_argument("--reuse-existing-frames", action="store_true")
    parser.add_argument("--video-name", default="video.mp4")
    args = parser.parse_args(argv)
    if args.scenario_overrides_json:
        payload = json.loads(args.scenario_overrides_json.read_text(encoding="utf-8"))
        quality = payload.get("simulation_quality", {})
        allowed_quality = {"domain_resolution", "timesteps_min", "timesteps_max", "flip_ratio",
                           "inlet_aperture_mode", "inlet_target_area_m2", "inlet_plane_z_m",
                           "viscosity_solver", "viscosity_cg_accuracy"}
        unknown = sorted(set(quality) - allowed_quality)
        if unknown:
            parser.error(f"Unknown simulation quality override(s): {unknown}")
        for key, value in quality.items():
            setattr(args, key, value)
    if args.fps <= 0 or args.duration_sec <= 0 or args.samples <= 0:
        parser.error("fps, duration and samples must be positive")
    if not 0 < args.viscosity_cg_accuracy <= 1e-3:
        parser.error("viscosity CG accuracy must be in (0, 1e-3]")
    if args.domain_resolution < 32:
        parser.error("domain resolution must be at least 32")
    if not 1 <= args.timesteps_min <= args.timesteps_max:
        parser.error("time-step limits must satisfy 1 <= min <= max")
    if not 0 <= args.flip_ratio <= 1:
        parser.error("FLIP ratio must be in [0,1]")
    if args.inlet_aperture_mode not in {"binary", "fractional_circle"}:
        parser.error("Unknown inlet aperture mode")
    if args.viscosity_solver not in {"auto", "diffusion", "coupled_spd"}:
        parser.error("Unknown viscosity solver")
    if args.inlet_target_area_m2 is not None and not 0 < args.inlet_target_area_m2 < 0.01:
        parser.error("Inlet target area must be positive and smaller than the domain cross-section")
    if args.inlet_plane_z_m is not None and not math.isfinite(args.inlet_plane_z_m):
        parser.error("Inlet plane must be finite")
    return args


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def viscosity_parts(value: float) -> tuple[float, int]:
    if not 0.0 < value < 10.0:
        raise ValueError("Mantaflow viscosity must be between 0 and 10 m^2/s")
    exponent = max(0, int(math.ceil(-math.log10(value))))
    base = value * 10**exponent
    while base >= 10.0 and exponent > 0:
        exponent -= 1
        base /= 10.0
    while base < 1.0:
        exponent += 1
        base *= 10.0
    return base, exponent


def fluid_modifier(obj: bpy.types.Object, role: str):
    for modifier in obj.modifiers:
        if modifier.type != "FLUID":
            continue
        if role == "domain" and modifier.domain_settings:
            return modifier
        if role == "flow" and modifier.flow_settings:
            return modifier
        if role == "effector" and modifier.effector_settings:
            return modifier
    raise RuntimeError(f"Missing {role} fluid modifier on {obj.name}")


def viscosity_settings(settings, domain_object) -> dict:
    """Read the active native branch and its nominal Blender viscosity mapping."""
    points = np.asarray([list(domain_object.matrix_world @ vertex.co) for vertex in domain_object.data.vertices])
    longest = float(np.ptp(points, axis=0).max())
    diffusion_nu = settings.viscosity_base * 10.0 ** -settings.viscosity_exponent
    solver = "free_surface" if settings.use_viscosity else "diffusion"
    effective_nu = settings.viscosity_value * longest**2 if settings.use_viscosity else diffusion_nu
    return {
        "solver": solver,
        "use_diffusion": settings.use_diffusion,
        "viscosity_base": settings.viscosity_base,
        "viscosity_exponent": settings.viscosity_exponent,
        "diffusion_kinematic_viscosity_m2_s": diffusion_nu,
        "effective_kinematic_viscosity_m2_s": effective_nu,
        "use_viscosity": settings.use_viscosity,
        "viscosity_value": settings.viscosity_value,
        "domain_longest_side_m": longest,
        "mapping": "free_surface: strength = nominal_nu / domain_length^2; diffusion: base * 10^-exponent; both use native Mantaflow time convention",
    }


def configure_cycles(scene: bpy.types.Scene) -> list[str]:
    selected: list[str] = []
    try:
        preferences = bpy.context.preferences.addons["cycles"].preferences
        for backend in ("OPTIX", "CUDA"):
            try:
                preferences.compute_device_type = backend
                preferences.get_devices()
                for device in preferences.devices:
                    device.use = device.type in {"OPTIX", "CUDA"}
                    if device.use:
                        selected.append(f"{device.type}:{device.name}")
                if selected:
                    break
            except Exception:
                selected.clear()
        scene.cycles.device = "GPU" if selected else "CPU"
    except Exception as exc:
        print(f"[render] GPU selection unavailable; using fallback: {exc}")
    return selected


def main() -> None:
    global INLET_PROTOCOL
    ARGS = parse_args()
    if ARGS.inlet_aperture_mode == "fractional_circle":
        INLET_PROTOCOL = "fixed_fractional_aperture_conservative_surface_inlet_7"
    template_path = Path(bpy.data.filepath).resolve()

    scene = bpy.context.scene
    if scene.get("pcve_scene_id") != TEMPLATE_SCENE_ID:
        raise RuntimeError(
            "Open assets/scenes/juice_dispenser_orange_cup/scene_template.blend before running "
            "render_juice_dispenser_orange_cup.py"
        )

    if ARGS.scenario_overrides_json:
        payload = json.loads(ARGS.scenario_overrides_json.read_text(encoding="utf-8"))
        payload = payload.get("physics", payload)
        if "timed_edits" in payload:
            raise ValueError("Use the supported nozzle_speed_change_sec / nozzle_speed_after_m_s profile for timed outlet-speed edits")
        allowed = {
            "orange_juice_density_kg_m3",
            "orange_juice_kinematic_viscosity_m2_s",
            "nozzle_speed_m_s",
            "nozzle_speed_change_sec",
            "nozzle_speed_after_m_s",
            "orange_juice_presence",
            "glass_presence",
            "gravity_m_s2",
            "pour_start_sec",
            "pour_end_sec",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError(f"Unknown physics override(s): {unknown}")
        for field, value in payload.items():
            setattr(ARGS, field, value)

    if tuple(ARGS.orange_juice_presence) not in {(0,), (1,)}:
        raise ValueError("orange_juice_presence must be [0] or [1]")
    if tuple(ARGS.glass_presence) not in {(0,), (1,)}:
        raise ValueError("glass_presence must be [0] or [1]")

    OUT = ARGS.out_dir.expanduser().resolve()
    CACHE = (ARGS.cache_dir or (OUT / "fluid_cache")).expanduser().resolve()
    FRAME_END = int(round(ARGS.duration_sec * ARGS.fps))
    JUICE_PRESENT = bool(ARGS.orange_juice_presence[0])
    GLASS_PRESENT = bool(ARGS.glass_presence[0])
    REUSE_CACHE = JUICE_PRESENT and ARGS.skip_fluid_bake and not ARGS.skip_render
    if not REUSE_CACHE and CACHE.exists() and any(CACHE.iterdir()):
        raise RuntimeError(f"Refusing to change a non-empty cache before configuring any fluid property: {CACHE}")
    if not JUICE_PRESENT:
        try:
            CACHE.relative_to(OUT)
        except ValueError as exc:
            raise RuntimeError("A no-liquid case must isolate its inactive cache inside --out-dir") from exc
    OUT.mkdir(parents=True, exist_ok=True)
    previous_metadata = json.loads((OUT / "scenario_metadata.json").read_text()) if (OUT / "scenario_metadata.json").is_file() else None

    config_fields = set(PhysicsConfig.__dataclass_fields__)
    config = PhysicsConfig(**{
        **asdict(PhysicsConfig()),
        **{key: value for key, value in vars(ARGS).items() if key in config_fields},
        "orange_juice_presence": tuple(ARGS.orange_juice_presence),
        "glass_presence": tuple(ARGS.glass_presence),
    })
    VISCOSITY_SOLVER = ARGS.viscosity_solver
    if VISCOSITY_SOLVER == "auto":
        VISCOSITY_SOLVER = "coupled_spd" if config.orange_juice_kinematic_viscosity_m2_s >= 1e-3 else "diffusion"
    ground_truth = simulate(config)
    ground_truth["inlet_protocol"] = INLET_PROTOCOL
    if REUSE_CACHE:
        if not previous_metadata or previous_metadata.get("inlet_protocol") != INLET_PROTOCOL:
            raise RuntimeError("Cached renders require the conservative inlet protocol; rebake historical caches")
        cached_physics = json.loads(json.dumps(asdict(PhysicsConfig())))
        cached_physics.update(previous_metadata["physics"])
        if cached_physics != json.loads(json.dumps(asdict(config))):
            raise RuntimeError("Cached physics differ from the requested case")
        if previous_metadata["simulation_quality"]["domain_resolution"] != ARGS.domain_resolution:
            raise RuntimeError("Cached solver resolution differs from the requested case")
        for key in ("timesteps_min", "timesteps_max"):
            if previous_metadata["simulation_quality"].get(key) != getattr(ARGS, key):
                raise RuntimeError(f"Cached {key} differs from the requested case")
        for key in ("inlet_aperture_mode", "inlet_target_area_m2", "inlet_plane_z_m"):
            actual = previous_metadata["simulation_quality"].get(key, "binary" if key == "inlet_aperture_mode" else None)
            if actual != getattr(ARGS, key):
                raise RuntimeError(f"Cached {key} differs from the requested case")
        if not math.isclose(previous_metadata["simulation_quality"].get("flip_ratio",0.92), ARGS.flip_ratio, abs_tol=1e-7):
            raise RuntimeError("Cached particle/grid coupling differs from the requested case")
        if previous_metadata["simulation_quality"].get("viscosity_solver", "diffusion") != VISCOSITY_SOLVER:
            raise RuntimeError("Cached viscosity solver differs from the requested case")
        if VISCOSITY_SOLVER in {"coupled_spd"} and previous_metadata["simulation_quality"].get("viscosity_cg_accuracy") != ARGS.viscosity_cg_accuracy:
            raise RuntimeError("Cached viscosity convergence accuracy differs from the requested case")
        if not (OUT / "boundary_flux.json").is_file():
            raise RuntimeError("Missing inlet-volume audit for the cached render")
        if previous_metadata["template"]["sha256"] != sha256(template_path):
            raise RuntimeError("Cached template differs from the requested template")
        baked_path = OUT / "scene_baked_final.blend"
        if not baked_path.is_file():
            raise RuntimeError("Cached rendering must load the saved baked scene")
        bpy.ops.wm.open_mainfile(filepath=str(baked_path))
        scene = bpy.context.scene
    (OUT / "ground_truth.json").write_text(
        json.dumps(ground_truth, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    if not REUSE_CACHE:
        scene.frame_start = 1
        scene.frame_end = FRAME_END
        scene.render.fps = ARGS.fps
        scene.render.fps_base = 1.0
        scene.gravity = (0.0, 0.0, -config.gravity_m_s2)
    scene.render.engine = "CYCLES"
    scene.render.resolution_x, scene.render.resolution_y = ARGS.resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.cycles.samples = ARGS.samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 8
    scene.cycles.transmission_bounces = 6
    scene.cycles.transparent_max_bounces = 8

    domain = bpy.data.objects["OrangeJuiceDomain"]
    domain_modifier = fluid_modifier(domain, "domain")
    ds = domain_modifier.domain_settings
    flow = bpy.data.objects["OrangeJuiceInflow"]
    flow_settings = fluid_modifier(flow, "flow").flow_settings
    viscosity_before = viscosity_settings(ds, domain)
    if REUSE_CACHE:
        if ds.resolution_max != ARGS.domain_resolution or ds.cache_frame_end != FRAME_END:
            raise RuntimeError("Saved baked scene has incompatible solver settings")
        if not all(math.isclose(a, b, abs_tol=1e-7) for a, b in zip(
            flow_settings.velocity_coord, (0.0, 0.0, -speed_at_time((scene.frame_current-1)/config.fps,
                config.nozzle_speed_m_s, config.nozzle_speed_change_sec, config.nozzle_speed_after_m_s))
        )):
            raise RuntimeError("Saved baked scene has incompatible outlet velocity")
    inflow_geometry_before = {
        "location_m": list(flow.location),
        "scale": list(flow.scale),
        "dimensions_m": list(flow.dimensions),
        "world_matrix": [list(row) for row in flow.matrix_world],
    }
    inflow_velocity_before = list(flow_settings.velocity_coord)
    if not REUSE_CACHE and not all(math.isclose(actual, expected, abs_tol=1e-7) for actual, expected in zip(
        inflow_velocity_before, (0.0, 0.0, -TEMPLATE_NOZZLE_SPEED_M_S)
    )):
        raise RuntimeError("The approved template must have its baseline 0.25 m/s downward inflow")

    if not REUSE_CACHE:
        # Cache isolation is established before any solver, geometry or inflow edit.
        ds.cache_directory = str(CACHE)
        ds.cache_frame_start = 1
        ds.cache_frame_end = FRAME_END
        ds.cache_type = "ALL"
        ds.resolution_max = ARGS.domain_resolution
        ds.timesteps_min = ARGS.timesteps_min
        ds.timesteps_max = ARGS.timesteps_max
        ds.flip_ratio = ARGS.flip_ratio
    if Path(bpy.path.abspath(ds.cache_directory)).resolve() != CACHE:
        raise RuntimeError("Mantaflow cache path did not resolve to the requested directory")
    if JUICE_PRESENT and not ARGS.skip_fluid_bake:
        try:
            CACHE.relative_to(OUT)
        except ValueError as exc:
            raise RuntimeError("A new bake cache must stay inside --out-dir") from exc
        if CACHE.exists() and any(CACHE.iterdir()):
            raise RuntimeError(f"Refusing to overwrite non-empty isolated cache: {CACHE}")
    if JUICE_PRESENT and ARGS.skip_fluid_bake and not ARGS.skip_render and (
        not CACHE.exists() or not any(CACHE.iterdir())
    ):
        raise RuntimeError("--skip-fluid-bake requires a non-empty --cache-dir")

    if not REUSE_CACHE:
        base, exponent = viscosity_parts(config.orange_juice_kinematic_viscosity_m2_s)
        ds.use_diffusion = VISCOSITY_SOLVER in {"diffusion", "coupled_spd"}
        ds.use_viscosity = False
        ds.viscosity_base = base
        ds.viscosity_exponent = exponent
        ds.surface_tension = 0.0

        # Speed edits keep the emitter geometry fixed and change the velocity passed
        # to Mantaflow.  At fixed cross-section the nominal flow scales with speed.
        flow_settings.use_initial_velocity = True
        flow_settings.velocity_coord = (0.0, 0.0, -config.nozzle_speed_m_s)
        flow_settings.surface_distance = 0.54
    viscosity_after = viscosity_settings(ds, domain)
    if viscosity_after["solver"] != ("diffusion" if VISCOSITY_SOLVER == "coupled_spd" else VISCOSITY_SOLVER) or viscosity_after["use_diffusion"] == viscosity_after["use_viscosity"]:
        raise RuntimeError("The native viscosity branch differs from the requested solver")
    if not math.isclose(viscosity_after["effective_kinematic_viscosity_m2_s"], config.orange_juice_kinematic_viscosity_m2_s, rel_tol=1e-6):
        raise RuntimeError("Native Mantaflow viscosity differs from the requested physical value")
    inflow_geometry_after = {
        "location_m": list(flow.location),
        "scale": list(flow.scale),
        "dimensions_m": list(flow.dimensions),
        "world_matrix": [list(row) for row in flow.matrix_world],
    }
    if inflow_geometry_after != inflow_geometry_before:
        raise RuntimeError("Outlet-speed edits must not change the emitter geometry")
    if not REUSE_CACHE:
        (OUT / "parameter_audit.json").write_text(json.dumps({
            "before": asdict(PhysicsConfig()),
            "after": asdict(config),
            "solver_inputs_before": {
                "inflow_geometry": inflow_geometry_before,
                "inflow_velocity_m_s": inflow_velocity_before,
                "viscosity": viscosity_before,
            },
            "solver_inputs_after": {
                "inflow_geometry": inflow_geometry_after,
                "inflow_velocity_m_s": list(flow_settings.velocity_coord),
                "viscosity": viscosity_after,
            },
            "outlet_speed_schedule": speed_schedule(config),
            "emitter_geometry_unchanged": True,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    start_frame = max(1, math.floor(config.pour_start_sec * config.fps) + 1)
    stop_frame = min(FRAME_END + 1, math.ceil(config.pour_end_sec * config.fps) + 1)
    if not REUSE_CACHE:
        flow.animation_data_clear()
    if not REUSE_CACHE and start_frame == 1 and stop_frame > FRAME_END:
        flow_settings.use_inflow = JUICE_PRESENT
    elif not REUSE_CACHE:
        for frame, value in (
            (1, False),
            (max(1, start_frame - 1), False),
            (start_frame, JUICE_PRESENT),
            (stop_frame, False),
        ):
            flow_settings.use_inflow = value
            flow_settings.keyframe_insert("use_inflow", frame=frame)
        if flow.animation_data and flow.animation_data.action:
            for curve in flow.animation_data.action.fcurves:
                for point in curve.keyframe_points:
                    point.interpolation = "CONSTANT"

    if not REUSE_CACHE and config.nozzle_speed_change_sec is not None:
        change_frame = round(config.nozzle_speed_change_sec * config.fps) + 1
        for frame, speed in ((1, config.nozzle_speed_m_s), (change_frame, config.nozzle_speed_after_m_s)):
            flow_settings.velocity_coord = (0.0, 0.0, -speed)
            flow_settings.keyframe_insert("velocity_coord", frame=frame)
        if config.nozzle_speed_after_m_s == 0.0:
            for frame, enabled in ((1, JUICE_PRESENT), (change_frame, False)):
                flow_settings.use_inflow = enabled
                flow_settings.keyframe_insert("use_inflow", frame=frame)
        if flow.animation_data and flow.animation_data.action:
            for curve in flow.animation_data.action.fcurves:
                for point in curve.keyframe_points:
                    point.interpolation = "CONSTANT"
        scene.frame_set(1)

    if not REUSE_CACHE:
        domain.animation_data_clear()
        domain.hide_render = not JUICE_PRESENT
        domain.hide_viewport = not JUICE_PRESENT
        flow.hide_viewport = not JUICE_PRESENT
        for name in ("PreviewOrangeJuiceStream", "PreviewOrangeJuiceInGlass"):
            obj = bpy.data.objects.get(name)
            if obj:
                obj.hide_render = True

        if not GLASS_PRESENT:
            glass = bpy.data.objects.get("ReceivingGlass")
            if glass:
                glass.hide_render = True
                glass.hide_viewport = True
            collider = bpy.data.objects.get("ReceivingGlassCollision")
            if collider:
                effectors = ds.effector_group
                if effectors and effectors.objects.get(collider.name):
                    effectors.objects.unlink(collider)

    metadata = {
        "schema_version": 4,
        "inlet_protocol": INLET_PROTOCOL,
        "source_preset": SOURCE_PRESET,
        "scene_id": TEMPLATE_SCENE_ID,
        "interaction_category": "rigid_fluid",
        "template": {"path": str(template_path), "sha256": sha256(template_path)},
        "simulation_mode": "mantaflow_inflow_static_rigid" if JUICE_PRESENT else "no_liquid",
        "coupling": ground_truth["coupling"],
        "physics": asdict(config),
        "outlet_speed_schedule": speed_schedule(config),
        "native_viscosity": viscosity_after,
        "simulation_quality": {
            "domain_resolution": ARGS.domain_resolution,
            "timesteps_min": ds.timesteps_min,
            "timesteps_max": ds.timesteps_max,
            "cfl_condition": ds.cfl_condition,
            "method": "FLIP",
            "flip_ratio": ds.flip_ratio,
            "viscosity_solver": VISCOSITY_SOLVER,
            "viscosity_implementation": "implicit_symmetric_strain_rate_active_mac" if VISCOSITY_SOLVER=="coupled_spd" else "native_full_domain",
            "inlet_aperture_mode":ARGS.inlet_aperture_mode,
            "inlet_target_area_m2":ARGS.inlet_target_area_m2,
            "inlet_plane_z_m":ARGS.inlet_plane_z_m,
            "viscosity_cg_accuracy": ARGS.viscosity_cg_accuracy if VISCOSITY_SOLVER == "coupled_spd" else None,
            "viscosity_cg_max_iter_factor": None,
            "viscosity_cg_max_iterations": 1500 if VISCOSITY_SOLVER == "coupled_spd" else None,
            "volume_projection_stage": "before_viscosity_pressure_and_meshing" if VISCOSITY_SOLVER=="coupled_spd" else "before_pressure_and_meshing",
            "viscous_boundary_discretization": "binary_liquid_cells_natural_free_surface_stationary_walls" if VISCOSITY_SOLVER == "coupled_spd" else None,
            "mesh_scale": ds.mesh_scale,
            "particles_per_cell": ds.particle_number,
            "surface_distance_cells": flow_settings.surface_distance,
            "flow_speed_changes_emitter_cross_section": False,
            "baseline_emitter_radius_m": BASELINE_EMITTER_RADIUS_M,
            "inflow_geometry": inflow_geometry_after,
            "inflow_velocity_m_s": list(flow_settings.velocity_coord),
        },
        "derived_diagnostics": {
            "geometric_flow_rate_ml_s": geometric_flow_rate_ml_s(config),
            "volume_annotations": "expected geometric supply; actual volumes measured from complete baked meshes",
        },
        "render": {
            "resolution": list(ARGS.resolution),
            "fps": ARGS.fps,
            "frames": FRAME_END,
            "samples": ARGS.samples,
        },
        "cache_directory": str(CACHE) if JUICE_PRESENT else None,
        "asset": {
            "name": "Juice Dispenser",
            "author": "dg samples",
            "license": "CC BY 4.0",
            "uid": "42f33cfdfc694e46b96a9ff168e4cae9",
        },
        "glass_visual_and_collision_separated": True,
    }
    if not REUSE_CACHE:
        (OUT / "scenario_metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    if not JUICE_PRESENT:
        # Remove the physical source, solved surface, static reservoir and previews.
        # This is object deletion, rather than a zero-speed or material-only edit.
        required_names = {"OrangeJuiceDomain", "OrangeJuiceInflow", "Juice_Juice_0",
                          "PreviewOrangeJuiceStream", "PreviewOrangeJuiceInGlass"}
        missing = sorted(required_names - set(bpy.data.objects.keys()))
        if missing:
            raise RuntimeError(f"Approved liquid objects missing before deletion: {missing}")
        liquid_objects = [obj for obj in bpy.data.objects if obj.name in required_names or any(
            material and material.name == "Orange juice liquid"
            for material in getattr(obj.data, "materials", ())
        )]
        removed_names = sorted(obj.name for obj in liquid_objects)
        for obj in liquid_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        remaining = sorted(obj.name for obj in bpy.data.objects if obj.name in required_names or any(
            material and material.name == "Orange juice liquid"
            for material in getattr(obj.data, "materials", ())
        ))
        if remaining:
            raise RuntimeError(f"Liquid objects remain after deletion: {remaining}")
        zero_frames = []
        for item in ground_truth["frames"]:
            measured = {
                "frame": item["frame"], "all_liquid_mesh_volume_ml": 0.0,
                "retained_volume_ml": 0.0, "delivered_below_outlet_volume_ml": 0.0,
                "injected_volume_ml": 0.0, "triangles": 0,
                "open_or_nonmanifold_edges": 0, "cup_band_vertices_outside_glass": 0,
            }
            item.update(measured)
            zero_frames.append(measured)
        ground_truth["annotation_status"] = "exact_zero_absent_object"
        metadata["liquid_presence"] = {
            "present": False, "removed_objects": removed_names,
            "reservoir_included": True, "applies_from_frame": 1,
        }
        metadata["derived_diagnostics"]["effective_flow_rate_ml_s"] = 0.0
        metadata["derived_diagnostics"]["volume_annotations"] = "exact zero: no liquid geometry, inflow, particles or solver"
        for name, value in {
            "ground_truth.json": ground_truth,
            "scenario_metadata.json": metadata,
            "liquid_presence_audit.json": {
                "status": "passed", "orange_juice_presence": [0],
                "removed_objects": removed_names, "remaining_liquid_objects": remaining,
                "reservoir_included": True, "inflow_enabled": False, "fluid_bake_required": False,
            },
            "boundary_flux.json": {
                "protocol": INLET_PROTOCOL, "simulation_mode": "no_liquid",
                "effective_flow_rate_ml_s": 0.0, "solver_invoked": False,
                "volume_records": [{"phase": "mesh", "frame": row["frame"], "target_ml": 0.0}
                                   for row in zero_frames],
            },
            "volume_measurements.json": {
                "protocol": INLET_PROTOCOL, "method": "exact zero from complete liquid-object deletion; no baked surface",
                "frames": zero_frames, "final": zero_frames[-1],
            },
        }.items():
            (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    scene.frame_set(1)
    if not REUSE_CACHE:
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "scene.blend"))
    timings = json.loads((OUT / "timings.json").read_text()) if REUSE_CACHE and (OUT / "timings.json").is_file() else {}

    if JUICE_PRESENT and not ARGS.skip_fluid_bake:
        CACHE.mkdir(parents=True, exist_ok=True)
        bpy.ops.object.select_all(action="DESELECT")
        domain.select_set(True)
        bpy.context.view_layer.objects.active = domain
        started = time.time()
        domain_points = np.asarray([list(domain.matrix_world @ vertex.co) for vertex in domain.data.vertices])
        flow_points = np.asarray([list(flow.matrix_world @ vertex.co) for vertex in flow.data.vertices])
        dx = float(np.ptp(domain_points, axis=0).max()) / ds.resolution_max
        boundary = FluxBoundary(
            domain_min=domain_points.min(axis=0),
            emitter_min_z=float(flow_points[:, 2].min()) - flow_settings.surface_distance * dx,
            center_xy=list(flow.location)[:2], radius_m=BASELINE_EMITTER_RADIUS_M,
            speed_m_s=config.nozzle_speed_m_s, start_sec=config.pour_start_sec,
            end_sec=config.pour_end_sec, report_path=OUT / "boundary_flux.json",
            speed_change_sec=config.nozzle_speed_change_sec, speed_after_m_s=config.nozzle_speed_after_m_s,
            aperture_mode=ARGS.inlet_aperture_mode,target_area_m2=ARGS.inlet_target_area_m2,target_plane_z_m=ARGS.inlet_plane_z_m,
        )
        boundary.install()
        import manta
        if VISCOSITY_SOLVER == 'coupled_spd':
            sys.path.insert(0,str(ARGS.solver_vendor.expanduser().resolve()))
            from coupled_viscosity import CoupledViscosity
            coupled_operator = CoupledViscosity(OUT/'coupled_viscosity_trace.json',tolerance=ARGS.viscosity_cg_accuracy)
        else:
            coupled_operator = None
        diffusion_failure = None
        native_diffusion = manta.cgSolveDiffusion
        def trace_diffusion(*args, **kwargs):
            nonlocal diffusion_failure
            scope = inspect.currentframe().f_back.f_globals
            suffix = re.fullmatch(r"liquid_step_(\d+)", inspect.currentframe().f_back.f_code.co_name).group(1)
            # Match the stress geometry to the prescribed conservative volume
            # before the implicit viscosity solve. Pressure sees the same level set.
            boundary.correct_simulation_volume(scope,suffix)
            try:
                return coupled_operator(*args,frame=int(scope['s'+suffix].frame),**kwargs)
            except BaseException as exc:
                diffusion_failure = repr(exc)
                coupled_operator.failure = coupled_operator.failure or repr(exc)
                coupled_operator.save()
                raise
        if VISCOSITY_SOLVER == 'coupled_spd':
            manta.cgSolveDiffusion = trace_diffusion
        try:
            result = bpy.ops.fluid.bake_all()
        finally:
            manta.cgSolveDiffusion = native_diffusion
            if coupled_operator is not None:
                coupled_operator.save()
            boundary.close()
        if diffusion_failure is not None:
            raise RuntimeError("Native diffusion callback failed: " + str(diffusion_failure))
        timings["bake_seconds"] = time.time() - started
        timings["bake_result"] = sorted(result)
        if "FINISHED" not in result:
            raise RuntimeError(f"Mantaflow bake failed: {result}")
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "scene_baked_final.blend"))
    elif not JUICE_PRESENT:
        timings.update({"bake_seconds": 0.0, "bake_result": "not_required_no_liquid"})
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "scene_baked_final.blend"))


    def verify_cache_and_measure() -> None:
        missing = [frame for frame in range(1, FRAME_END + 1)
                   if not (CACHE / "config" / f"config_{frame:04d}.uni").is_file()
                   or not (CACHE / "mesh" / f"fluid_mesh_{frame:04d}.bobj.gz").is_file()]
        if missing:
            raise RuntimeError(f"Incomplete fluid cache, including possibly cancelled FINISHED bake: {missing}")
        boundary_report = json.loads((OUT / "boundary_flux.json").read_text())
        if boundary_report["protocol"] != INLET_PROTOCOL:
            raise RuntimeError("Incompatible inlet audit")
        budgets = {entry["frame"]: entry["target_ml"] for entry in boundary_report["volume_records"] if entry["phase"] == "mesh"}
        measurements = []
        for item in ground_truth["frames"]:
            frame = item["frame"]
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            obj = domain.evaluated_get(bpy.context.evaluated_depsgraph_get())
            if len(obj.data.polygons) <= 12 and budgets[frame] > 0:
                raise RuntimeError(f"Missing solved surface at frame {frame}")
            measured = measure_surface(obj, bottom_z=config.glass_inner_bottom_z_m,
                lip_z=config.glass_lip_z_m, outlet_z=0.19535,
                glass_center_xy=(0.0, -0.101), glass_radius=config.glass_inner_radius_m)
            measured.update({"frame": frame, "injected_volume_ml": budgets[frame]})
            item.update(measured)
            item["liquid_volume_measurement_status"] = "measured_baked_closed_surface"
            measurements.append(measured)
        ground_truth["annotation_status"] = "measured_baked_surfaces"
        (OUT / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2, ensure_ascii=False) + "\n")
        (OUT / "volume_measurements.json").write_text(json.dumps({"protocol": INLET_PROTOCOL,
            "method": "oriented closed-surface integration; cup region clipped to bottom and lip planes",
            "frames": measurements, "final": measurements[-1]}, indent=2) + "\n")


    if JUICE_PRESENT and (not ARGS.skip_fluid_bake or not ARGS.skip_render):
        verify_cache_and_measure()


    def render_outputs() -> None:
        if JUICE_PRESENT:
            probe_frame = min(FRAME_END, max(start_frame + 12, 16))
            scene.frame_set(probe_frame)
            bpy.context.view_layer.update()
            evaluated = domain.evaluated_get(bpy.context.evaluated_depsgraph_get())
            if len(evaluated.data.polygons) <= 12:
                raise RuntimeError(
                    f"No solved liquid mesh at frame {probe_frame}; bake this case instead of reusing an incompatible cache"
                )
        devices = configure_cycles(scene)
        timings["cycles_devices"] = devices
        scene.render.use_persistent_data = True
        if ARGS.render_stills_only:
            preview_dir = OUT / "previews"
            preview_dir.mkdir(parents=True, exist_ok=True)
            for frame in sorted(set(ARGS.preview_frames or (1, 24, 48, 72, FRAME_END))):
                if not 1 <= frame <= FRAME_END:
                    continue
                scene.frame_set(frame)
                scene.render.filepath = str(preview_dir / f"frame_{frame:04d}.png")
                bpy.ops.render.render(write_still=True)
            return

        frames_dir = OUT / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        if not ARGS.reuse_existing_frames:
            for stale in frames_dir.glob("frame_*.png"):
                stale.unlink()
        started = time.time()
        rendered = 0
        for frame in range(1, FRAME_END + 1):
            path = frames_dir / f"frame_{frame:04d}.png"
            if ARGS.reuse_existing_frames and path.is_file() and path.stat().st_size > 100_000:
                continue
            scene.frame_set(frame)
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            rendered += 1
        render_seconds = time.time() - started
        video = OUT / ARGS.video_name
        encode_started = time.time()
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-framerate", str(ARGS.fps), "-start_number", "1",
            "-i", str(frames_dir / "frame_%04d.png"), "-frames:v", str(FRAME_END),
            "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(video),
        ], check=True)
        encode_seconds = time.time() - encode_started
        probe = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
            "-show_entries", "stream=codec_name,width,height,pix_fmt,r_frame_rate,avg_frame_rate,nb_read_frames:format=duration,size",
            "-of", "json", str(video),
        ], text=True))
        stream = probe["streams"][0]
        if [stream["width"], stream["height"]] != list(ARGS.resolution):
            raise RuntimeError("Encoded resolution does not match the requested resolution")
        if stream["r_frame_rate"] != f"{ARGS.fps}/1" or int(stream["nb_read_frames"]) != FRAME_END:
            raise RuntimeError("Encoded frame rate or decoded frame count is incorrect")
        expected_duration = FRAME_END / ARGS.fps
        if abs(float(probe["format"]["duration"]) - expected_duration) > 1.0e-3:
            raise RuntimeError("Encoded duration is incorrect")
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], check=True)
        probe.update({
            "sha256": sha256(video),
            "full_decode": "passed",
            "rendered_frames_this_run": rendered,
            "render_seconds": render_seconds,
            "encode_seconds": encode_seconds,
        })
        (OUT / "video_verification.json").write_text(json.dumps(probe, indent=2) + "\n", encoding="utf-8")
        timings.update({"render_seconds": render_seconds, "encode_seconds": encode_seconds})


    if not ARGS.skip_render:
        render_outputs()

    (OUT / "timings.json").write_text(json.dumps(timings, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "scene": str(OUT / "scene.blend"),
        "baked": JUICE_PRESENT and not ARGS.skip_fluid_bake,
        "rendered": not ARGS.skip_render,
        "cache": str(CACHE) if JUICE_PRESENT else None,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
