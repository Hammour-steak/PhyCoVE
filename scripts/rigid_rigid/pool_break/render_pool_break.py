"""Render the pool-break scene with Blender's Python API.

The setting is a basement pub's billiard room in the late afternoon: brick
walls, a plank floor, a caged fluorescent fixture hanging over the cloth, two
wall sconces, a barrel table with stools, and low sun through a side window
(``billiard_room``). The table is its own model (``table_model``), fitted so its
cloth is the simulation's felt plane and its cushion noses are the simulation's
cushion planes; its legs stand on the room's floor. Only the four balls of the
shot are in play -- ``pool_table_animation`` ships a full fifteen-ball rack plus
two cue sticks, and every ball the shot does not use, along with that file's own
low-poly table, is hidden on import rather than moved. The four balls keep that
file's objects (and so their transforms), but wear the table model's numbered
ball meshes (``table_model.numbered_ball_mesh``), so their roll is visible.

The camera is bolted to a fixed rig behind the cue ball, looking down the table.
It does not follow anything: the ball travels through the frame and the rack
opens away from it, which is the motion the scene exists to show. ``--camera-mode
survey`` swaps in a higher three-quarter rig that holds the whole table, for
inspecting where the balls ended up rather than how they got there.

Everything the balls do is keyed from the matching PyBullet run -- locations and
rolling orientations per frame -- so the video and the ground-truth trajectory
file are the same numbers.
"""
from __future__ import annotations

# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    if _Path(__file__).with_name("entrypoints.json").is_file() and (_Path(__file__).resolve().parents[2]/"pcve_scene_entry.py").is_file():
        _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
        # This scene also renders from a Python that has the bpy module
        # (--render-python). Load bpy first for real runs so prepare_entry keeps
        # the render in this process instead of relaunching Blender; planning
        # calls (--help/--dry-run/--describe) stay import-free.
        if not {"-h", "--help", "--dry-run", "--describe"} & set(_sys.argv[1:]):
            try:
                import bpy  # noqa: F401
            except ImportError:
                pass
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__, "render")
# PCVE_UNIFIED_ENTRY_END

# Resolve the shared scripts directory, then this scene's module folders.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_scripts_dir = _clean_scene_dir.parents[1]
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / 'scripts').is_dir())
if str(_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
# Shared modules live in scripts/; scene-local modules live in this directory and
# its physics/, appearance/ and tools/ subdirectories.
for _scene_sub in ("", "physics", "appearance", "tools"):
    _scene_sub_dir = _clean_scene_dir / _scene_sub if _scene_sub else _clean_scene_dir
    if _scene_sub_dir.is_dir() and str(_scene_sub_dir) not in _clean_sys.path:
        _clean_sys.path.insert(1, str(_scene_sub_dir))


from pcve_blender_compat import (eevee_engine, set_eevee_property, set_color_property)

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Vector

import billiard_room as room_lib  # noqa: E402
import scene_config as cfg  # noqa: E402
import table_model as table_lib  # noqa: E402
from validate_pool_break import validate_cache  # noqa: E402
from pcve_scene_runtime import python_for  # noqa: E402


WORKSPACE_DIR = _PCVE_PROJECT_ROOT
PHYSICS_PYTHON = python_for("physics")

OUTPUT_STEM = "pool_break"
GROUND_TRUTH_NAME = "ground_truth_transforms.json"
SCENARIO_METADATA_NAME = "scenario_metadata.json"

BALL_OBJECTS = {
    "cue_ball": cfg.CUE_BALL_MESH,
    "apex_ball": cfg.APEX_BALL_MESH,
    "left_ball": cfg.LEFT_BALL_MESH,
    "right_ball": cfg.RIGHT_BALL_MESH,
}

# Camera rigs. Kept here rather than in ``scene_config.py`` on purpose: that file
# is hashed by ``validate_pool_break.signature()``, so touching a camera constant
# would invalidate every cached trajectory.
#
# ``break``   low at the head end, looking down the table. The cue ball sits in
#             the near third of the frame and the rack is away in the middle,
#             so the shot has depth and the ball's run reads as a run rather
#             than as a dot sliding sideways. The rig holds the *whole*
#             table -- playing surface, all four pockets, the near apron's outer
#             edge -- because a break is not over where it starts: the two wings
#             run to the side cushions. A rig that holds every cushion but crops
#             the near apron makes the table read as a tray sliding off the
#             bottom of the frame.
# ``survey``  the same table from higher and further back with the floor in
#             shot, for first/middle/last reviews and batch thumbnails.
#
# Both are fitted to the imported table, which carries 200 mm of rail and a
# 60 mm frame all round: its footprint is 2.18 x 1.30 m around the 1.81 x 0.93 m
# playing surface. A 25 mm lens puts the two near corners off frame (u = 1.03,
# v = -0.13), so the lens is 21 mm and the body stands at x = 1.90 m, as far
# back as the hall's side walls reach. The aim point sits 60 mm low to buy
# bottom margin without raising the camera (a 1.7 degree tilt at this
# distance). A 57 mm ball is about 20 px across at the cue spot and 13-16 px in
# the rack.
CAMERA_PRESETS = {
    "break": dict(
        location=(1.90, -0.54, 0.88), target=(-0.10, 0.0, -0.04),
        lens_mm=21.0, fstop=5.6, focus_offset=0.0,
    ),
    "survey": dict(
        location=(1.90, -1.00, 1.52), target=(-0.10, 0.0, 0.0),
        lens_mm=18.0, fstop=8.0, focus_offset=0.0,
    ),
}


# AgX, graded for a room whose brightest surface is the lamp-lit cloth.
ROOM_LOOK = "AgX - Base Contrast"
ROOM_EXPOSURE = 0.3


from pcve_scene_runtime import parse_render_args, run_renderer, apply_physics_overrides

def parse_args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    parser = argparse.ArgumentParser(description="Render a three-ball pool break.")
    parser.add_argument("--mode", choices=("preview", "animation", "sampled"), default="animation")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--resolution", nargs=2, type=int, default=cfg.BASELINE_RENDER["resolution"])
    parser.add_argument("--fps", type=int, default=cfg.BASELINE_RENDER["fps"])
    parser.add_argument("--duration-sec", type=float, default=cfg.BASELINE_RENDER["duration_sec"])
    parser.add_argument("--samples", type=int, default=cfg.BASELINE_RENDER["samples"])
    parser.add_argument("--preview-frame", type=int, default=14,
                        help="Frame for preview mode; 14 is just after the contact at the default speed.")
    parser.add_argument("--frame-count", type=int, default=6,
                        help="Number of evenly-spaced stills in sampled mode.")
    parser.add_argument("--seed", type=int, default=3110)
    parser.add_argument("--device", choices=("auto", "cpu"), default="auto")
    parser.add_argument("--engine", choices=("eevee", "cycles"), default="eevee")
    parser.add_argument("--camera-mode", choices=tuple(CAMERA_PRESETS),
                        default=cfg.BASELINE_RENDER["camera_mode"])
    # The three exposed controls. Left at None they fall back to the shared
    # baseline, so a caller that renders an existing physics file need not
    # repeat them.
    parser.add_argument("--cue-speed", type=float)
    parser.add_argument("--cue-contact-offset", type=float)
    parser.add_argument("--cue-mass", type=float)
    parser.add_argument("--scenario-overrides-json", type=Path)
    parser.add_argument("--physics-json", type=Path, default=None,
                        help="Replay a simulation result instead of running PyBullet.")
    parser.add_argument("--timed-edits-json", type=Path, default=None)
    return parse_render_args(parser, argv)


# ------------------------------------------------------------------ physics


def run_physics(args: argparse.Namespace) -> dict:
    """Reuse a trajectory, or simulate one with the same interpreter the suite uses."""
    if args.physics_json is not None:
        if args.scenario_overrides_json is not None:raise ValueError("Resimulate to change cached physics")
        data = json.loads(Path(args.physics_json).resolve().read_text(encoding="utf-8"))
        validate_cache(data)
        params = data["physics_parameters"]
        for name in ("cue_speed", "cue_contact_offset", "cue_mass"):
            requested = getattr(args, name)
            if requested is not None and abs(float(requested) - float(params[name])) > 1e-12:
                raise ValueError(
                    f"--{name.replace('_', '-')} is {requested} but the cached "
                    f"trajectory was solved with {params[name]}; drop the flag or "
                    "resimulate"
                )
        return data

    schedule = apply_physics_overrides(args, cfg.BASELINE_PHYSICS)
    if schedule is not None:
        if args.timed_edits_json is not None:raise ValueError("Use one timed-edit schedule")
        args.timed_edits_json = schedule
    out_path = Path(args.out_dir) / "physics_transforms.json"
    command = [
        str(args.physics_python),
        str(Path(__file__).with_name("simulate_pool_break.py")),
        "--out", str(out_path),
        "--fps", str(int(args.fps)),
        "--duration-sec", str(float(args.duration_sec)),
        "--cue-speed", str(float(args.cue_speed if args.cue_speed is not None
                                  else cfg.BASELINE_PHYSICS["cue_speed"])),
        "--cue-contact-offset", str(float(
            args.cue_contact_offset if args.cue_contact_offset is not None
            else cfg.BASELINE_PHYSICS["cue_contact_offset"])),
        "--cue-mass", str(float(args.cue_mass if args.cue_mass is not None
                                else cfg.BASELINE_PHYSICS["cue_mass"])),
    ]
    if args.timed_edits_json is not None:
        command += ["--timed-edits-json", str(Path(args.timed_edits_json).resolve())]
    subprocess.run(command, check=True)
    return json.loads(out_path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------- scene


def clear_imported_animation() -> None:
    """Drop the GLB's own take.

    The file ships a 3.3 s animation of the cue ball, two object balls and a cue
    stick. Left attached, it keys the very objects this script keyframes, and
    the render would show the imported shot fighting the simulated one.
    """
    for obj in bpy.data.objects:
        if obj.animation_data is not None:
            obj.animation_data_clear()
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def flatten_ball(obj: bpy.types.Object) -> None:
    """Detach a ball from the model's hierarchy with its world transform baked in.

    The GLB nests every ball under an empty that carries its authored position,
    and the mesh inside that empty is centred on its own origin. After this the
    object *is* the ball: origin at the centre, radius in metres, no parent -- so
    a physics location can be assigned straight onto ``obj.location``.
    """
    world = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = world
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    obj.select_set(False)


def import_table() -> tuple[dict[str, bpy.types.Object], float]:
    """Bring in the balls and the table, then keep only the balls from this file.

    ``pool_table_animation.glb`` is the only file in the repo whose ball meshes
    match the radius the simulation uses, so the four ball *objects* still come
    from it and their transforms are baked from the simulation. Its table is a
    low-poly game asset and is hidden -- ``table_model`` supplies a real one,
    fitted to the same felt plane and the same cushion noses, so the cached
    trajectories stay valid and the balls still bounce exactly where the
    cushions are.

    The balls' *meshes* are then swapped for the table model's own numbered
    balls (2k maps with the numbers on them, rebuilt as true spheres of the
    simulation's radius). This file's balls are flat 512 px colours: on a ball
    that rolls, a solid colour shows no rotation at all, and a ball that slides
    across the cloth without turning is exactly what a real break never does.
    Only ``obj.data`` changes, so every keyed transform -- and the ground-truth
    ``matrix_world`` -- is the same as before.

    Returns the balls and the floor height: the bottom of the table model's
    legs, which is where the room's boards are laid.
    """
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(cfg.MODEL_PATH))
    clear_imported_animation()

    scale = cfg.SCENE_SCALE
    shift = cfg.model_z_shift()
    for obj in bpy.data.objects:
        if obj.parent is None:
            obj.scale = (scale, scale, scale)
            obj.location.z -= shift
    bpy.context.view_layer.update()

    balls: dict[str, bpy.types.Object] = {}
    for slot, mesh_name in BALL_OBJECTS.items():
        obj = bpy.data.objects.get(mesh_name)
        if obj is None:
            raise RuntimeError(f"Ball mesh not found in {cfg.MODEL_PATH.name}: {mesh_name}")
        balls[slot] = obj

    for obj in balls.values():
        flatten_ball(obj)

    # Everything else this file brought in: the rest of the rack, both sticks and
    # the table. Hiding (not deleting) keeps the file's own hierarchy intact for
    # anyone who opens the .blend.
    keep = set(balls.values())
    for obj in bpy.data.objects:
        if obj in keep:
            continue
        obj.hide_viewport = True
        obj.hide_render = True

    table = table_lib.import_table(cfg.PLAY_HALF_X, cfg.PLAY_HALF_Y)
    for slot, label in BALL_NUMBERS.items():
        balls[slot].data = table_lib.numbered_ball_mesh(label, cfg.BALL_RADIUS)
    floor_z = table_lib.leg_bottom(table)
    print(f"[render] table: felt at z=0, noses at +/-{cfg.PLAY_HALF_X:.4f} x "
          f"+/-{cfg.PLAY_HALF_Y:.4f} m, legs on the floor at z={floor_z:.4f}", flush=True)
    return balls, floor_z


# Which of the table model's balls each slot wears: the same colours the
# slots always had -- the white cue ball, the yellow 1 at the apex, the blue 2
# and the red 3 behind it.
BALL_NUMBERS = {"cue_ball": "white", "apex_ball": "Ball1", "left_ball": "Ball2", "right_ball": "Ball3"}


def render_engine(args: argparse.Namespace) -> None:
    scene = bpy.context.scene
    if args.engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = int(args.samples)
        scene.cycles.use_denoising = True
        scene.cycles.max_bounces = 8
        scene.cycles.diffuse_bounces = 4
        scene.cycles.glossy_bounces = 4
        scene.cycles.device = "CPU"
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
        if args.device == "auto" and os.environ.get("PCVE_CYCLES_GPU") == "1":
            prefs = bpy.context.preferences.addons["cycles"].preferences
            try:
                prefs.compute_device_type = "CUDA"
                prefs.get_devices()
                for dev in prefs.devices:
                    dev.use = dev.type == "CUDA"
                scene.cycles.device = "GPU"
                if any(dev.type == "OPTIX" for dev in prefs.devices):
                    scene.cycles.denoiser = "OPTIX"
            except Exception as exc:  # noqa: BLE001 - any CUDA probe failure falls back
                print(f"[render] CPU fallback: {exc}", flush=True)
        print(f"[render] cycles device={scene.cycles.device} denoiser={scene.cycles.denoiser}",
              flush=True)
    else:
        scene.render.engine = eevee_engine()
        set_eevee_property(scene.eevee, 'taa_render_samples', int(args.samples))
        set_eevee_property(scene.eevee, 'use_raytracing', True)
        set_eevee_property(scene.eevee, 'use_gtao', True)
        # 2 m smears every contact shadow into grey haze on a table this size;
        # the balls are 57 mm across, so the occlusion radius has to be small.
        set_eevee_property(scene.eevee, 'gtao_distance', 0.06)
        # Screen-space AO at 60 mm covers the balls and nothing else. It cannot
        # darken an inside corner four metres away, so every wall panel, the
        # wall-to-floor join and the wall-to-wall corner arrived at the same
        # value as the middle of the wall -- which is most of why the room read
        # as painted cardboard. Fast GI is a coarse diffuse bounce over a much
        # longer distance: it costs two rays per pixel and it is what puts a
        # gradient into the corners.
        set_eevee_property(scene.eevee, 'use_fast_gi', True)
        set_eevee_property(scene.eevee, 'fast_gi_method', 'GLOBAL_ILLUMINATION')
        set_eevee_property(scene.eevee, 'fast_gi_distance', 0.85)
        set_eevee_property(scene.eevee, 'fast_gi_ray_count', 2)
        set_eevee_property(scene.eevee, 'fast_gi_step_count', 8)
        set_eevee_property(scene.eevee, 'fast_gi_quality', 0.5)


def build_scene(args: argparse.Namespace, physics: dict):
    # ``import_table`` starts from an empty file, so every scene reference below
    # has to be taken *after* it -- holding one across the reset leaves a dead
    # StructRNA behind.
    balls, floor_z = import_table()

    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.fps = int(physics["fps"])
    # Motion blur at a half-frame shutter, the way a 24 fps camera at 180
    # degrees smears a ball crossing the cloth. Persistent data has to stay off
    # with it: Blender 4.3 with both on drops an object that has come to rest
    # from every later frame of the same render session, and every ball here
    # comes to rest before the clip ends.
    scene.render.use_persistent_data = False
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.film_transparent = False
    set_color_property(scene.view_settings, 'view_transform', 'AgX')
    set_color_property(scene.view_settings, 'look', ROOM_LOOK)
    scene.view_settings.exposure = ROOM_EXPOSURE
    render_engine(args)

    room = room_lib.build(floor_z)

    preset = CAMERA_PRESETS[args.camera_mode]
    bpy.ops.object.camera_add(location=preset["location"])
    camera = bpy.context.object
    camera.name = "camera"
    camera.data.lens = preset["lens_mm"]
    camera.data.sensor_width = 36.0
    camera.data.clip_start = 0.005
    camera.data.clip_end = 60.0
    camera.data.dof.use_dof = True
    camera.data.dof.focus_distance = (
        Vector(preset["target"]) - Vector(preset["location"])
    ).length + preset["focus_offset"]
    camera.data.dof.aperture_fstop = preset["fstop"]
    scene.camera = camera
    target = bpy.data.objects.new("camera_target", None)
    scene.collection.objects.link(target)
    target.location = preset["target"]
    constraint = camera.constraints.new("TRACK_TO")
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"

    keyframe_balls(
        {slot: obj for slot, obj in balls.items()},
        physics["frames"],
    )

    scene.frame_start = 1
    scene.frame_end = int(physics["frame_end"])
    scene.frame_set(1)
    # The room is not in the simulation: refuse a take in which a ball would
    # touch a piece of it, or a piece of it would hide a ball from the camera.
    radius = float(physics["objects"]["cue_ball"]["radius"])
    room_lib.check_clearance(room["pieces"], physics["frames"], tuple(balls), radius)
    room_lib.check_line_of_sight(room["pieces"], physics["frames"], tuple(balls), radius, camera)
    return balls, camera


def keyframe_balls(balls: dict[str, bpy.types.Object], records: list[dict]) -> None:
    for slot, obj in balls.items():
        obj.rotation_mode = "QUATERNION"
        # A ball removed by a DELETE edit is absent in every record: not rendered.
        if not any(record.get(f"{slot}_present", True) for record in records):
            for part in (obj, *obj.children_recursive):
                part.hide_render = part.hide_viewport = True
    for record in records:
        frame = int(record["frame_index"])
        for slot, obj in balls.items():
            obj.location = record[f"{slot}_location"]
            quat = record[f"{slot}_quaternion_xyzw"]
            # Blender wants w first, the simulator hands it over last.
            obj.rotation_quaternion = (quat[3], quat[0], quat[1], quat[2])
            obj.keyframe_insert(data_path="location", frame=frame)
            obj.keyframe_insert(data_path="rotation_quaternion", frame=frame)
    for obj in balls.values():
        for fcurve in obj.animation_data.action.fcurves:
            for key in fcurve.keyframe_points:
                key.interpolation = "LINEAR"


# ----------------------------------------------------------------- outputs


def export_ground_truth(out_dir: Path, balls, camera, physics: dict, scenario: dict) -> None:
    scene = bpy.context.scene
    records = {
        "schema_version": 3,
        "scene": "pool_break",
        "fps": int(physics["fps"]),
        "frame_start": 1,
        "frame_end": int(physics["frame_end"]),
        "physics": {key: value for key, value in physics.items() if key != "frames"},
        "objects": {
            slot: {
                "object_name": obj.name,
                "radius_m": float(physics["objects"]["cue_ball"]["radius"]),
            }
            for slot, obj in balls.items()
        },
        "camera": {
            "object_name": camera.name,
            "lens_mm": float(camera.data.lens),
            "sensor_width_mm": float(camera.data.sensor_width),
            "resolution": [int(scene.render.resolution_x), int(scene.render.resolution_y)],
        },
        "scenario": scenario,
        "frames": [],
    }
    by_frame = {int(f["frame_index"]): f for f in physics["frames"]}
    for frame_index in range(1, int(physics["frame_end"]) + 1):
        scene.frame_set(frame_index)
        physical = by_frame[frame_index]
        entry = {"frame_index": frame_index, "time_sec": physical["time_sec"]}
        for slot, obj in balls.items():
            if physical.get(f"{slot}_present", True) is False:
                entry[slot] = {"present": False}
                continue
            entry[slot] = {
                "matrix_world": [[float(v) for v in row] for row in obj.matrix_world],
                "location": [float(v) for v in physical[f"{slot}_location"]],
                "linear_velocity": physical[f"{slot}_linear_velocity"],
                "angular_velocity": physical[f"{slot}_angular_velocity"],
                "table_gap": physical[f"{slot}_table_gap"],
            }
        for pair in ("cue_apex", "apex_left", "apex_right"):
            entry[f"{pair}_gap"] = physical.get(f"{pair}_gap")
        entry["camera_matrix_world"] = [
            [float(v) for v in row] for row in camera.matrix_world
        ]
        entry["camera_world_to_camera_matrix"] = [
            [float(v) for v in row] for row in camera.matrix_world.inverted()
        ]
        records["frames"].append(entry)
    (out_dir / GROUND_TRUTH_NAME).write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )


def render_preview(args: argparse.Namespace) -> None:
    scene = bpy.context.scene
    scene.render.image_settings.file_format = "PNG"
    scene.frame_set(max(scene.frame_start, min(int(args.preview_frame), scene.frame_end)))
    scene.render.filepath = str(args.out_dir / "preview.png")
    bpy.ops.render.render(write_still=True)


def render_sampled(args: argparse.Namespace) -> None:
    scene = bpy.context.scene
    scene.render.image_settings.file_format = "PNG"
    frame_end = int(scene.frame_end)
    if not 2 <= int(args.frame_count) <= frame_end:
        raise ValueError(f"--frame-count must be between 2 and {frame_end}")
    indices = [
        1 + round(i * (frame_end - 1) / (int(args.frame_count) - 1))
        for i in range(int(args.frame_count))
    ]
    for index in indices:
        scene.frame_set(index)
        scene.render.filepath = str(args.out_dir / f"frame_{index:04d}.png")
        bpy.ops.render.render(write_still=True)
        print(f"[render] frame {index} -> frame_{index:04d}.png", flush=True)
    (args.out_dir / "sampled_frames.json").write_text(
        json.dumps({"frame_indices": indices, "frame_end": frame_end}), encoding="utf-8"
    )


def main() -> None:
    import time

    started = time.perf_counter()
    args = parse_args()
    # Blender resolves relative render paths against its own base directory.
    args.out_dir = args.out_dir.resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    physics = run_physics(args)
    params = physics["physics_parameters"]
    scenario = {
        "schema_version": 3,
        "scene": "pool_break",
        "seed": int(args.seed),
        "environment": "pub_billiard_room_late_afternoon",
        "description": "Three balls racked in a triangle on the foot spot are struck by "
                       "the white cue ball; the triangle opens and the balls run to the "
                       "cushions. All four balls are PyBullet rigid bodies.",
        "camera_mode": args.camera_mode,
        "render": {
            "mode": args.mode,
            "fps": int(physics["fps"]),
            "duration_sec": float(physics["duration_sec"]),
            "resolution": [int(args.resolution[0]), int(args.resolution[1])],
            "samples": int(args.samples),
            "engine": "cycles" if args.engine == "cycles" else "eevee_next",
            "device": str(args.device),
        },
        "physics_params": {
            "cue_speed": float(params["cue_speed"]),
            "cue_contact_offset": float(params["cue_contact_offset"]),
            "cue_mass": float(params["cue_mass"]),
            "object_mass": float(params["object_mass"]),
        },
        "quality": physics["quality"],
    }
    (args.out_dir / SCENARIO_METADATA_NAME).write_text(
        json.dumps(scenario, indent=2), encoding="utf-8"
    )

    balls, camera = build_scene(args, physics)
    print(f"[render] scene built in {time.perf_counter() - started:.1f}s "
          f"({len(bpy.data.objects)} objects)", flush=True)
    export_ground_truth(args.out_dir, balls, camera, physics, scenario)

    if args.mode == "preview":
        render_preview(args)
    elif args.mode == "sampled":
        render_sampled(args)
    else:
        bpy.context.scene.render.filepath = str(args.out_dir / f"{OUTPUT_STEM}.mp4")
        bpy.ops.render.render(animation=True)
    # The room's scanned textures and window view are loaded from assets/ by
    # absolute path; store them relative to the .blend so the file still opens
    # once the repository lives somewhere else. (Done by hand rather than with
    # make_paths_relative, which needs an already-saved file and so a second
    # save that leaves a .blend1 backup beside the case's outputs.)
    for image in bpy.data.images:
        if (image.source == "FILE" and image.packed_file is None and image.filepath
                and not image.filepath.startswith("//")):
            image.filepath = bpy.path.relpath(bpy.path.abspath(image.filepath), start=str(args.out_dir))
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out_dir / f"{OUTPUT_STEM}.blend"))
    print(f"[render] complete: {args.out_dir}", flush=True)


if __name__ == "__main__":
    run_renderer(main, 'pool_break')

