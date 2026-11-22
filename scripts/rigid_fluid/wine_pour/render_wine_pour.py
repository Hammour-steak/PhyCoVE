"""Configure, bake, render and verify the approved PCVE wine-pour scene.

Run this script through Blender with ``assets/scenes/wine_pour/scene_template.blend`` open.  The
template contains the accepted bar appearance; every newly baked case receives
its own cache directory before any physical setting is changed.
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
        _pcve_prepare_entry(__file__, 'render')
# PCVE_UNIFIED_ENTRY_END

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from simulate_wine_pour import PhysicsConfig, simulate  # noqa: E402

TEMPLATE_SCENE_ID = "wine_pour"
BASELINE_FLOW_RATE_ML_S = PhysicsConfig().flow_rate_ml_s


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    defaults = PhysicsConfig()
    parser = argparse.ArgumentParser(description="Bake and render the approved PCVE wine-pour scene.")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--scenario-overrides-json", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--resolution", nargs=2, type=int, default=(1280, 720))
    parser.add_argument("--fps", type=int, default=defaults.fps)
    parser.add_argument("--duration-sec", type=float, default=defaults.duration_sec)
    parser.add_argument("--samples", type=int, default=96)
    parser.add_argument("--domain-resolution", type=int, default=144)
    parser.add_argument("--effector-subframes", type=int, default=4)
    parser.add_argument("--wine-density-kg-m3", type=float, default=defaults.wine_density_kg_m3)
    parser.add_argument("--wine-kinematic-viscosity-m2-s", type=float, default=defaults.wine_kinematic_viscosity_m2_s)
    parser.add_argument("--flow-rate-ml-s", type=float, default=defaults.flow_rate_ml_s)
    parser.add_argument("--nozzle-speed-m-s", type=float, default=defaults.nozzle_speed_m_s)
    parser.add_argument("--nozzle-speed-change-frame", type=int, default=defaults.nozzle_speed_change_frame)
    parser.add_argument("--nozzle-speed-after-m-s", type=float, default=defaults.nozzle_speed_after_m_s)
    parser.add_argument("--pour-start-sec", type=float, default=defaults.pour_start_sec)
    parser.add_argument("--pour-end-sec", type=float, default=defaults.pour_end_sec)
    parser.add_argument("--wine-presence", nargs=1, type=int, choices=(0, 1), default=defaults.wine_presence)
    parser.add_argument("--glass-presence", nargs=1, type=int, choices=(0, 1), default=defaults.glass_presence)
    parser.add_argument("--skip-fluid-bake", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--render-stills-only", action="store_true")
    parser.add_argument("--preview-frames", nargs="+", type=int)
    parser.add_argument("--reuse-existing-frames", action="store_true")
    parser.add_argument("--video-name", default="video.mp4")
    args = parser.parse_args(argv)
    if args.fps <= 0 or args.duration_sec <= 0 or args.samples <= 0:
        parser.error("fps, duration and samples must be positive")
    if args.domain_resolution < 32:
        parser.error("domain resolution must be at least 32")
    if not 0 <= args.effector_subframes <= 200:
        parser.error("effector subframes must be between 0 and 200")
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


def find_modifier(obj: bpy.types.Object, role: str):
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


def set_constant_boolean_animation(obj: bpy.types.Object, data_path: str, points: list[tuple[int, bool]]) -> None:
    obj.animation_data_clear()
    for frame, value in points:
        target = obj
        if data_path == "hide_render":
            target.hide_render = value
            target.keyframe_insert(data_path, frame=frame)
        else:
            flow_settings = find_modifier(obj, "flow").flow_settings
            flow_settings.use_inflow = value
            flow_settings.keyframe_insert("use_inflow", frame=frame)
    if obj.animation_data and obj.animation_data.action:
        for curve in obj.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "CONSTANT"


ARGS = parse_args()

if bpy.context.scene.get("pcve_scene_id") != TEMPLATE_SCENE_ID:
    raise RuntimeError("Open assets/scenes/wine_pour/scene_template.blend before running render_wine_pour.py")

if ARGS.scenario_overrides_json:
    payload = json.loads(ARGS.scenario_overrides_json.read_text(encoding="utf-8"))
    payload = payload.get("physics", payload)
    allowed = {
        "wine_density_kg_m3", "wine_kinematic_viscosity_m2_s", "flow_rate_ml_s",
        "nozzle_speed_m_s", "wine_presence", "glass_presence", "gravity_m_s2",
        "pour_start_sec", "pour_end_sec", "nozzle_speed_change_frame",
        "nozzle_speed_after_m_s",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"Unknown physics override(s): {unknown}")
    for field, value in payload.items():
        setattr(ARGS, field, value)

if tuple(ARGS.wine_presence) not in {(0,), (1,)}:
    raise ValueError("wine_presence must be [0] or [1]")
if tuple(ARGS.glass_presence) not in {(0,), (1,)}:
    raise ValueError("glass_presence must be [0] or [1]")

OUT = ARGS.out_dir.expanduser().resolve()
CACHE = (ARGS.cache_dir or (OUT / "fluid_cache")).expanduser().resolve()
FRAME_END = int(round(ARGS.duration_sec * ARGS.fps))
WINE_PRESENT = bool(ARGS.wine_presence[0])
GLASS_PRESENT = bool(ARGS.glass_presence[0])
RUN_FLUID = WINE_PRESENT
OUT.mkdir(parents=True, exist_ok=True)

config_fields = set(PhysicsConfig.__dataclass_fields__)
config = PhysicsConfig(**{
    **asdict(PhysicsConfig()),
    **{key: value for key, value in vars(ARGS).items() if key in config_fields},
    "wine_presence": tuple(ARGS.wine_presence),
    "glass_presence": tuple(ARGS.glass_presence),
})
ground_truth = simulate(config)
(OUT / "ground_truth.json").write_text(
    json.dumps(ground_truth, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)

scene = bpy.context.scene
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

domain = bpy.data.objects["WineFluidDomain"]
domain_modifier = find_modifier(domain, "domain")
ds = domain_modifier.domain_settings
flow = bpy.data.objects["WineInflow"]
flow_settings = find_modifier(flow, "flow").flow_settings

# Cache isolation is established before any solver or geometry mutation.
ds.cache_directory = str(CACHE)
ds.cache_frame_start = 1
ds.cache_frame_end = FRAME_END
ds.cache_type = "ALL"
ds.resolution_max = ARGS.domain_resolution
if Path(bpy.path.abspath(ds.cache_directory)).resolve() != CACHE:
    raise RuntimeError("Mantaflow cache path did not resolve to the requested directory")
if RUN_FLUID and not ARGS.skip_fluid_bake:
    try:
        CACHE.relative_to(OUT)
    except ValueError as exc:
        raise RuntimeError("A new bake cache must stay inside --out-dir") from exc
    if CACHE.exists() and any(CACHE.iterdir()):
        raise RuntimeError(f"Refusing to overwrite non-empty isolated cache: {CACHE}")
if RUN_FLUID and ARGS.skip_fluid_bake and not ARGS.skip_render and (
    not CACHE.exists() or not any(CACHE.iterdir())
):
    raise RuntimeError("--skip-fluid-bake requires a non-empty --cache-dir")

base, exponent = viscosity_parts(config.wine_kinematic_viscosity_m2_s)
ds.viscosity_base = base
ds.viscosity_exponent = exponent
if config.wine_kinematic_viscosity_m2_s >= 1.0e-3:
    ds.use_diffusion = False
    ds.use_viscosity = True
    ds.viscosity_value = config.wine_kinematic_viscosity_m2_s
    # Highly viscous liquid needs smaller adaptive time steps at the formal
    # domain resolution.  The default 1..4 range becomes unstable near the
    # end of the pour (the surface mesh bursts into disconnected droplets).
    ds.timesteps_min = max(ds.timesteps_min, 2)
    ds.timesteps_max = max(ds.timesteps_max, 12)
    ds.cfl_condition = min(ds.cfl_condition, 1.5)
    if config.wine_kinematic_viscosity_m2_s >= 1.5e-2:
        # Toothpaste-like viscosity needs an even tighter integration range
        # to keep the extruded rope cohesive at the 144-cell formal bake.
        ds.timesteps_min = max(ds.timesteps_min, 4)
        ds.timesteps_max = max(ds.timesteps_max, 20)
        ds.cfl_condition = min(ds.cfl_condition, 1.0)
else:
    ds.use_diffusion = True
    ds.use_viscosity = False
ds.surface_tension = 0.0

for obj in bpy.data.objects:
    if obj.name.startswith("GlassCollider"):
        modifier = find_modifier(obj, "effector")
        modifier.effector_settings.subframes = ARGS.effector_subframes

# Preserve the nozzle axis and outlet speed; flow-rate edits change only the
# emitter cross-section, matching Q = area * speed.
flow_ratio = math.sqrt(config.flow_rate_ml_s / BASELINE_FLOW_RATE_ML_S)
flow.scale.x *= flow_ratio
flow.scale.y *= flow_ratio
baseline_speed = PhysicsConfig().nozzle_speed_m_s
base_velocity = tuple(
    component * config.nozzle_speed_m_s / baseline_speed
    for component in flow_settings.velocity_coord
)
flow_settings.velocity_coord = base_velocity
start_frame = max(1, math.ceil(config.pour_start_sec * config.fps) + 1)
stop_frame = min(FRAME_END, math.ceil(config.pour_end_sec * config.fps) + 1)
if config.nozzle_speed_change_frame is not None and config.nozzle_speed_after_m_s == 0.0:
    stop_frame = min(stop_frame, config.nozzle_speed_change_frame)
set_constant_boolean_animation(
    flow,
    "use_inflow",
    [
        (1, False),
        (max(1, start_frame - 1), False),
        (start_frame, True),
        (stop_frame, False),
    ],
)
set_constant_boolean_animation(
    domain,
    "hide_render",
    [
        (1, True),
        (max(1, start_frame - 1), True),
        (start_frame, False),
    ],
)
if config.nozzle_speed_change_frame is not None:
    flow_settings.velocity_coord = base_velocity
    flow_settings.keyframe_insert("velocity_coord", frame=1)
    flow_settings.keyframe_insert(
        "velocity_coord", frame=max(1, config.nozzle_speed_change_frame - 1)
    )
    flow_settings.velocity_coord = tuple(
        component * config.nozzle_speed_after_m_s / config.nozzle_speed_m_s
        for component in base_velocity
    )
    flow_settings.keyframe_insert("velocity_coord", frame=config.nozzle_speed_change_frame)
    if flow.animation_data and flow.animation_data.action:
        for curve in flow.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "CONSTANT"

if not GLASS_PRESENT:
    glass = bpy.data.objects.get("RigidWineGlass")
    if glass:
        glass.hide_render = True
        glass.hide_viewport = True
    effector_group = ds.effector_group
    for obj in list(bpy.data.objects):
        if not obj.name.startswith("GlassCollider"):
            continue
        if effector_group and effector_group.objects.get(obj.name):
            effector_group.objects.unlink(obj)
    # Disable output-only bowl clipping before measuring the actual domain
    # mesh; otherwise evaluated dimensions describe the clipped wine surface.
    for modifier in domain.modifiers:
        if modifier.type == "BOOLEAN" or modifier.name.startswith("Subtle liquid surface"):
            modifier.show_viewport = False
            modifier.show_render = False
    bpy.context.view_layer.update()
    target_xy = 0.164
    domain.scale.x *= target_xy / domain.dimensions.x
    domain.scale.y *= target_xy / domain.dimensions.y
    bpy.context.view_layer.objects.active = domain
    domain.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    domain.select_set(False)
    for side in ("front", "back", "left", "right"):
        attr = "use_collision_border_" + side
        if hasattr(ds, attr):
            setattr(ds, attr, False)
if not WINE_PRESENT:
    domain.animation_data_clear()
    domain.hide_render = True
    domain.hide_viewport = True
    flow.animation_data_clear()
    flow.hide_viewport = True

template_path = Path(bpy.data.filepath).resolve()
metadata = {
    "schema_version": 2,
    "scene_id": "wine_pour",
    "interaction_category": "rigid_fluid",
    "template": {"path": str(template_path), "sha256": sha256(template_path)},
    "simulation_mode": "mantaflow_inflow_static_rigid" if RUN_FLUID else "no_liquid",
    "coupling": ground_truth["coupling"],
    "physics": asdict(config),
    "simulation_quality": {
        "domain_resolution": ARGS.domain_resolution,
        "method": "FLIP",
        "effector_subframes": ARGS.effector_subframes,
        "timesteps_min": ds.timesteps_min,
        "timesteps_max": ds.timesteps_max,
        "cfl_condition": ds.cfl_condition,
        "surface_tension": 0.0,
        "flow_rate_changes_emitter_cross_section": True,
        "timed_speed_change_uses_fixed_emitter_cross_section": True,
    },
    "render": {
        "resolution": list(ARGS.resolution), "fps": ARGS.fps,
        "frames": FRAME_END, "samples": ARGS.samples,
    },
    "cache_directory": str(CACHE) if RUN_FLUID else None,
    "assets": [
        {"name": "Wine Bottle and Glass", "author": "JoeDev", "license": "CC BY 4.0"},
        {"name": "Wine Bottles 01", "authors": ["Rico Cilliers", "Jurita Burger"], "license": "CC0 1.0"},
    ],
    "glass_visual_and_collision_separated": True,
}
(OUT / "scenario_metadata.json").write_text(
    json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)

scene.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "scene.blend"))
timings: dict[str, float | list[str]] = {}

if RUN_FLUID and not ARGS.skip_fluid_bake:
    CACHE.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    domain.select_set(True)
    bpy.context.view_layer.objects.active = domain
    started = time.time()
    result = bpy.ops.fluid.bake_all()
    timings["bake_seconds"] = time.time() - started
    timings["bake_result"] = sorted(result)
    if "FINISHED" not in result:
        raise RuntimeError(f"Mantaflow bake failed: {result}")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "scene_baked_final.blend"))
elif not RUN_FLUID:
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "scene_baked_final.blend"))


def configure_devices() -> None:
    try:
        preferences = bpy.context.preferences.addons["cycles"].preferences
        for backend in ("OPTIX", "CUDA"):
            try:
                preferences.compute_device_type = backend
                preferences.get_devices()
                break
            except Exception:
                continue
        for device in preferences.devices:
            device.use = device.type in {"OPTIX", "CUDA"}
        scene.cycles.device = "GPU"
    except Exception as exc:
        print(f"[render] GPU selection unavailable; using Cycles fallback: {exc}")


def render_outputs() -> None:
    reusable_frames = OUT / "frames"
    has_complete_reusable_sequence = ARGS.reuse_existing_frames and all(
        (reusable_frames / f"frame_{frame:04d}.png").is_file()
        and (reusable_frames / f"frame_{frame:04d}.png").stat().st_size > 100_000
        for frame in range(1, FRAME_END + 1)
    )
    if RUN_FLUID and not has_complete_reusable_sequence:
        # An incompatible or missing Mantaflow cache makes Blender render the
        # domain's source cube. Refuse that failure mode before producing any
        # preview or video.
        probe_frame = min(FRAME_END, max(start_frame + 6, 16))
        scene.frame_set(probe_frame)
        bpy.context.view_layer.update()
        evaluated = domain.evaluated_get(bpy.context.evaluated_depsgraph_get())
        if len(evaluated.data.polygons) <= 12:
            raise RuntimeError(
                f"No solved liquid mesh at frame {probe_frame}; bake this case instead of reusing an incompatible cache"
            )
    configure_devices()
    scene.render.use_persistent_data = True
    if ARGS.render_stills_only:
        preview_dir = OUT / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        for frame in sorted(set(ARGS.preview_frames or (1, 16, 56, FRAME_END))):
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
        "ffmpeg", "-y", "-v", "warning", "-framerate", str(ARGS.fps), "-start_number", "1",
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
        "sha256": sha256(video), "full_decode": "passed",
        "rendered_frames_this_run": rendered,
        "render_seconds": render_seconds, "encode_seconds": encode_seconds,
    })
    (OUT / "video_verification.json").write_text(json.dumps(probe, indent=2) + "\n", encoding="utf-8")
    timings.update({"render_seconds": render_seconds, "encode_seconds": encode_seconds})


if not ARGS.skip_render:
    render_outputs()

(OUT / "timings.json").write_text(json.dumps(timings, indent=2) + "\n", encoding="utf-8")
print(json.dumps({
    "status": "ok",
    "scene": str(OUT / "scene.blend"),
    "baked": RUN_FLUID and not ARGS.skip_fluid_bake,
    "rendered": not ARGS.skip_render,
    "cache": str(CACHE) if RUN_FLUID else None,
}, ensure_ascii=False))
