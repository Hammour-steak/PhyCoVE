"""Bake the PCVE sink liquid into an isolated, disposable work cache."""

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
import sys
import time
from dataclasses import dataclass
from pathlib import Path


HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class PhysicsConfig:
    """Baseline values exposed to the shared PCVE edit vocabulary."""

    fps: int = 24
    duration_sec: float = 4.0
    faucet_inflow_velocity_m_s: float = 0.6
    water_kinematic_viscosity_m2_s: float = 1.0e-6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case-id",
        choices=("source", "edit_low_flow", "edit_high_flow", "edit_high_viscosity", "edit_stop_flow_at_2s"),
        default="source",
    )
    parser.add_argument("--scene", type=Path)
    parser.add_argument("--work-dir", type=Path)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def main() -> None:
    import bpy

    args = parse_args()
    default_work = HERE / "cases" / args.case_id / "work"
    work = (args.work_dir or default_work).expanduser().resolve()
    source = (args.scene or (work / "scene.blend")).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    work.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=str(source))
    scene = bpy.context.scene
    if scene.get("pcve_case_id") != args.case_id:
        raise RuntimeError("Prepared scene and requested case differ")
    domain = bpy.data.objects.get("LiquidDomain")
    if domain is None:
        raise RuntimeError("Missing LiquidDomain")
    modifier = next(
        (mod for mod in domain.modifiers if mod.type == "FLUID" and mod.fluid_type == "DOMAIN"),
        None,
    )
    if modifier is None or modifier.domain_settings is None:
        raise RuntimeError("Missing liquid domain settings")
    settings = modifier.domain_settings
    cache = (work / "fluid_cache").resolve()
    settings.cache_directory = str(cache)
    if cache.exists() and any(cache.iterdir()):
        raise RuntimeError(f"Refusing to overwrite non-empty runtime cache: {cache}")
    cache.mkdir(parents=True, exist_ok=True)

    if args.case_id == "edit_stop_flow_at_2s":
        emitter = bpy.data.objects["FaucetWaterInflow"]
        flow = next(m.flow_settings for m in emitter.modifiers if m.type == "FLUID" and m.fluid_type == "FLOW")
        for frame, subframe in ((1, 0.0), (48, 0.999), (49, 0.0), (96, 0.0)):
            scene.frame_set(frame, subframe=subframe)
            enabled = frame < 49
            if flow.use_inflow != enabled or abs(flow.velocity_coord.z - (-0.6 if enabled else 0.0)) > 1e-6:
                raise RuntimeError(f"Invalid timed inlet at {frame}+{subframe}")

    scene.frame_set(1)
    bpy.ops.object.select_all(action="DESELECT")
    domain.select_set(True)
    bpy.context.view_layer.objects.active = domain
    started = time.monotonic()
    result = bpy.ops.fluid.bake_all()
    if "FINISHED" not in result:
        raise RuntimeError(f"Mantaflow bake failed: {result}")
    bpy.ops.wm.save_as_mainfile(filepath=str(work / "scene_baked.blend"))
    print(f"PCVE_BAKE_SECONDS={time.monotonic() - started:.3f}", flush=True)
    print(f"PCVE_BAKED_SCENE={work / 'scene_baked.blend'}", flush=True)


if __name__ == "__main__":
    main()
