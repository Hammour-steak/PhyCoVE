"""Public entry point: the tilted-cup pour (Genesis 1.4.3 DFSPH, 1 mm) and its whole-clip edits.

A ceramic cup rests on a walnut block at a 58-degree tilt with 81 mL of water whose surface starts 16 mm above the low
rim; the water drains over the rim and spreads across an oak worktop. Per case: simulate (simulate_*), reconstruct the
water surface, the tabletop film and the wet-oak map (surface_*) and render the sunlit kitchen (render_*). Each step is
skipped when its output exists and only missing frames are rendered, so an interrupted build resumes. Each case keeps
video.mp4 and its bilingual prompts.json in <suite-root>/cases/<case_id>/, intermediates go to
<suite-root>/runs/<case_id>/, and the configuration and run summaries to <suite-root>/suite_manifest.json.
    CUDA_VISIBLE_DEVICES=0 <genesis python> build_pcve_tilted_cup_table_pour.py --suite-root SUITE --blender BLENDER
"""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'build_pcve')
# PCVE_UNIFIED_ENTRY_END

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / "scripts")]
import edit_vocab  # noqa: E402
import pcve_edit_dsl as dsl  # noqa: E402

NAME = "tilted_cup_table_pour"
SUITE_NAME = f"pcve_{NAME}_suite"
SOURCE_CASE_ID = "tilted_cup_table_pour_baseline"
FRAMES = edit_vocab.VOCAB.total_frames
SAMPLES = 128
SOURCE = {
    "case_id": SOURCE_CASE_ID, "kind": "source", "interaction_category": "rigid_fluid",
    "description": {
        "vague": {"en": "A white ceramic cup of water rests tipped steeply on a small wooden block; the water pours over its low rim "
                        "in a clear stream and spreads across the wooden worktop into a wide, thin puddle in the morning sun.",
                  "zh": "一只装着水的白色陶瓷杯斜靠在一块小木块上，倾斜得很厉害；水从低侧杯口流出，形成一道清澈的水流，"
                        "在晨光下的木质台面上铺开成一大片薄薄的水滩。"},
        "quantitative": {"en": "A ceramic cup (74 mm wide, 55 mm tall) is held fixed at a 58° tilt with 81 mL of water (998.2 kg/m³, "
                               "1.0e-6 m²/s, surface tension 0.072 N/m) whose surface starts 16 mm above the low inner rim, under "
                               "9.81 m/s² gravity. The water pours over the rim at up to about 110 mL/s, hits the oak worktop at "
                               "about 1 m/s and spreads as a thin sheet up to about 25 cm from the cup; after about 1.5 s the stream "
                               "thins to a trickle, and at 4 s 34.5 mL is left in the cup and 46.5 mL lies on the table.",
                         "zh": "一只陶瓷杯（宽 74 mm、高 55 mm）以 58° 倾角固定不动，杯中有 81 mL 水（密度 998.2 kg/m³，运动黏度 "
                               "1.0e-6 m²/s，表面张力 0.072 N/m），初始水面比低侧内沿高 16 mm，重力 9.81 m/s²。水从杯口流出，流量最高"
                               "约 110 mL/s，以约 1 m/s 落到橡木台面上，铺成薄薄一层，最远离杯子约 25 cm；约 1.5 s 后水流变成细流，"
                               "4 s 时杯中剩 34.5 mL，台面上有 46.5 mL。"}},
    "physics": edit_vocab.BASELINE_PHYSICS,
}
EDITS = (
    {"case_id": "edit_high_viscosity_water", "kind": "edit", "edit_dsl": "SET water.viscosity TIMES 100",
     "edit_summary": "Water kinematic viscosity rises a hundred-fold to 1.0e-4 m²/s, like a light oil: it pours over the rim "
                     "slightly slower (peak about 100 instead of 110 mL/s) and 37.2 mL instead of 34.5 mL stays in the cup; on "
                     "the table it stops in a compact, thicker puddle reaching about 14 cm from the cup and 10 cm wide, instead "
                     "of a thin sheet reaching 25 cm and 20 cm wide."},
    {"case_id": "edit_delete_water", "kind": "edit", "edit_dsl": "DELETE water",
     "edit_summary": "The water is removed from the first frame: the empty cup rests tilted on its block for the whole clip and "
                     "the worktop stays dry."},
    {"case_id": "edit_delete_cup", "kind": "edit", "edit_dsl": "DELETE cup",
     "edit_summary": "The cup is removed from the first frame: the 81 mL of water, no longer held, drops onto the walnut block "
                     "and the worktop at once and bursts outward; within 0.3 s the sheet runs up against the tiled wall 30 cm "
                     "behind and spreads 20-40 cm to the sides, and by 1 s it lies still as a wide, shallow puddle with scattered "
                     "drops; about 0.9 mL stays on top of the block."},
)
CAMERA = {"location_m": [0.34, -0.47, 0.25], "target_m": [0.055, 0.0, 0.035], "lens_mm": 50, "sensor_mm": 36, "fstop": 8.0}
RENDER = {"engine": "Cycles", "samples": SAMPLES, "denoising": True, "motion_blur_shutter_frames": 0.5,
          "resolution": [1280, 720], "fps": edit_vocab.FPS, "color_management": "AgX, Medium High Contrast look, exposure -1.15",
          "camera": CAMERA,
          "light": {"sun": "40 W/m², elevation 32°, azimuth -20° (through the window behind the cup), angle 1.2°",
                    "window": "area light 0.70 x 0.88 m, 29 W", "world": "studio_small_09 HDRI, strength 0.11"},
          "look": {"water": "clear (IOR 1.333, roughness 0.018) with absorption 0.10 (0.58, 0.88, 0.96)",
                   "tabletop_water": "continuous film from the table particles (volume conserving, gaps up to ~2 cm bridged, depth "
                                     "levelled over 12 mm, rounded 1.5 mm edge)",
                   "oak": "White Oak Veneer 4k, darkened x(0.68, 0.62, 0.56) and roughness 0.16 where wet",
                   "support": "procedural oak billet in an oiled-walnut tone", "cup": "lathed porcelain, glaze coat 0.6 / 0.045"}}
ASSETS = ROOT / "assets/rigid_fluid/tilted_cup_environment"
PARTICLE_ML = 0.8 * 0.001 ** 3 * 1e6     # liquid volume of one 1 mm DFSPH particle (Genesis: 0.8 d^3)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite-root", type=Path, required=True)
    parser.add_argument("--blender", default=os.environ.get("BLENDER", "blender"))
    parser.add_argument("--python", default=sys.executable, help="interpreter of the Genesis environment")
    parser.add_argument("--publish-root", type=Path, help="suite path recorded in the manifest's outputs (default: --suite-root)")
    parser.add_argument("--cases", nargs="*", default=[SOURCE_CASE_ID] + [e["case_id"] for e in EDITS])
    parser.add_argument("--no-manifest", action="store_true", help="build the cases only (parallel builders of one suite)")
    return parser.parse_args()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    temporary.replace(path)


def run(command, log):
    print("RUN " + " ".join(map(str, command)), flush=True)
    started = time.perf_counter()
    with log.open("w") as stream:
        subprocess.run([str(part) for part in command], stdout=stream, stderr=subprocess.STDOUT, check=True)
    return time.perf_counter() - started


def plans():
    vocab = edit_vocab.VOCAB
    source = {**SOURCE, "prompts_document": {"schema_version": 1, "case_id": SOURCE_CASE_ID, "kind": "source",
                                             "prompts": SOURCE["description"]}}
    edits = []
    for case in EDITS:
        edit = dsl.parse(case["edit_dsl"], vocab)
        document = {"schema_version": 2, "case_id": case["case_id"], "source_case_id": SOURCE_CASE_ID,
                    "edit_dsl": case["edit_dsl"], "edit_summary": case["edit_summary"],
                    "applies_from_frame": dsl.starts_at_frame(edit),
                    "physics_diff": {**({f"presence ({edit.object_id})": {"from": True, "to": False}} if isinstance(edit, dsl.DeleteEdit) else
                                        {f"{edit.property_name} ({edit.object_id})": {"from": dsl.baseline_value_for(edit, vocab), "to": edit.to_value}}),
                                     "timing": dsl.timing_diff(edit, vocab)},
                    "prompts": dsl.make_prompts(edit, vocab)}
        edits.append({**case, "physics": {**SOURCE["physics"], **dsl.to_physics_override(edit, vocab)}, "prompts_document": document})
    return [source] + edits


def dry_run_dir(work, cup):
    """DELETE water: no simulation; empty meshes and a report the renderer reads"""
    meshes = work / "meshes_1mm"
    meshes.mkdir(parents=True, exist_ok=True)
    for f in range(1, FRAMES + 1):
        np.savez(meshes / f"water_{f:04d}.npz", vertices=np.zeros((0, 3), np.float32), triangles=np.zeros((0, 3), np.int32),
                 normals=np.zeros((0, 3), np.float32), velocity=np.zeros((0, 3), np.float32))
    from contact_geometry import CUP_CENTER_Z, CUP_TILT_DEG, SUPPORT_CENTER_X, SUPPORT_SIZE
    write_json(work / "simulation_report.json", {
        "solver": "none (no liquid)", "coupling": "none (no liquid)", "physics": {"cup_present": cup, "water_present": False,
                                                  "cup_pose": {"center_m": [0.0, 0.0, CUP_CENTER_Z], "euler_deg": [0, CUP_TILT_DEG, 0]}},
        "geometry": {"square_support_center_m": [SUPPORT_CENTER_X, 0.0, SUPPORT_SIZE[2] / 2]},
        "frames_simulated": FRAMES, "numerics": {"simulation_fps": edit_vocab.FPS, "physical_duration_sec": FRAMES / edit_vocab.FPS},
        "trajectory": [{"frame": f, "physical_time_sec": (f - 1) / edit_vocab.FPS} for f in range(1, FRAMES + 1)]})


def check_run(sim_args, physics):
    """The finished simulation used this case's physics."""
    assert math.isclose(sim_args["mu"], physics["water_kinematic_viscosity_m2_s"], rel_tol=1e-9), "water viscosity"
    assert math.isclose(sim_args["table_wet"], physics["table_adhesion_ratio"], rel_tol=1e-9), "table adhesion"
    assert sim_args["no_cup"] == (not physics["cup_presence"][0]), "cup presence"
    assert sim_args["frames"] == FRAMES and sim_args["fps"] == edit_vocab.FPS


def build_case(args, plan, runs, cases, published):
    work = runs / plan["case_id"]
    work.mkdir(parents=True, exist_ok=True)
    timings_path = work / "timings.json"
    timings = json.loads(timings_path.read_text()) if timings_path.exists() else {}
    flags = edit_vocab.sim_args(plan["physics"])
    water = flags is not None
    if not water:
        if not (work / "simulation_report.json").exists():
            dry_run_dir(work, bool(plan["physics"]["cup_presence"][0]))
    else:
        log_path = work / "sim_log.json"
        if not log_path.exists() or len(json.loads(log_path.read_text())["frames"]) < FRAMES:
            run([args.python, "-u", HERE / f"simulate_{NAME}.py", "--out", work, "--frames", FRAMES, "--fps", edit_vocab.FPS,
                 *flags], work / "sim.log")
        surface_log = work / "surface_log.json"
        if not surface_log.exists() or len(json.loads(surface_log.read_text())["frames"]) < FRAMES:
            timings["surface_sec"] = run([args.python, HERE / f"surface_{NAME}.py", work], work / "surface.log")
            write_json(timings_path, timings)
    frames = work / "render" / "frames"
    missing = [f for f in range(1, FRAMES + 1) if not (frames / f"frame_{f:04d}.png").exists()]
    if missing:
        seconds = run([args.blender, "-b", "--python-exit-code", "1", "--python", HERE / f"render_{NAME}.py", "--",
                       "--run", work, "--hdri", ASSETS / "studio_small_09/studio_small_09_1k.hdr", "--out", work / "render",
                       "--frames", ",".join(map(str, missing)), "--mesh-dir-name", "meshes_1mm",
                       "--camera-lens", CAMERA["lens_mm"], "--camera-target", *CAMERA["target_m"],
                       "--resolution", *RENDER["resolution"], "--output-fps", edit_vocab.FPS, "--samples", SAMPLES,
                       "--engine", "cycles", "--device", "gpu", "--real-time", "--appearance-preset", "refined_kitchen",
                       "--appearance-assets", ASSETS, "--fstop", CAMERA["fstop"]]
                      + (["--resume"] if len(missing) < FRAMES else []), work / "render.log")
        timings["render_sec"] = timings.get("render_sec", 0.0) + seconds
        write_json(timings_path, timings)
    video = work / "video.mp4"
    if not video.exists() or missing:
        run(["ffmpeg", "-v", "error", "-y", "-framerate", edit_vocab.FPS, "-i", frames / "frame_%04d.png", "-c:v", "libx264",
             "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", video], work / "encode.log")
    case = cases / plan["case_id"]
    case.mkdir(parents=True, exist_ok=True)
    shutil.copy2(video, case / "video.mp4")
    write_json(case / "prompts.json", plan["prompts_document"])

    record = {key: plan[key] for key in ("case_id", "kind", "interaction_category", "description") if key in plan}
    if plan["kind"] == "edit":
        document = plan["prompts_document"]
        record = {"case_id": plan["case_id"], "kind": "edit",
                  **{key: document[key] for key in ("source_case_id", "edit_dsl", "edit_summary", "applies_from_frame", "physics_diff", "prompts")}}
    record.update({"status": "completed",
                   "outputs": {"video": str(published / "cases" / plan["case_id"] / "video.mp4"),
                               "prompts": str(published / "cases" / plan["case_id"] / "prompts.json")},
                   "video_sha256": digest(case / "video.mp4"), "physics": plan["physics"],
                   "elapsed_sec": round(timings.get("surface_sec", 0.0) + timings.get("render_sec", 0.0), 1),
                   "numerics": {}, "simulation": {"frames": FRAMES, "simulated": False, "water_particles": 0},
                   "render": RENDER})
    if water:
        log = json.loads((work / "sim_log.json").read_text())
        check_run(log["args"], plan["physics"])
        rows, n = log["frames"], log["n_particles"]
        record["numerics"] = {k: v for k, v in log["args"].items() if k != "out"} | {"viscosity_solve": log["viscosity_solve"]}
        record["elapsed_sec"] = round(log["build_sec"] + log["sim_sec"] + record["elapsed_sec"], 1)
        record["simulation"] = {
            "frames": FRAMES, "simulated": True, "water_particles": n, "ghost_particles": log["n_ghosts"], "water_volume_ml": round(n * PARTICLE_ML, 1),
            "seconds_per_frame": round(log["sim_sec"] / max(1, len(rows) - 1), 1),
            "water_in_cup_final_ml": round(rows[-1]["in_cup_fraction"] * n * PARTICLE_ML, 1),
            "water_on_table_final_ml": round(rows[-1]["table_particles"] * PARTICLE_ML, 1),
            "peak_particle_speed_m_s": round(max(r["max_speed_m_s"] for r in rows), 3),
            "final_p99_particle_speed_m_s": round(rows[-1]["p99_speed_m_s"], 4),
            "surface_sec": round(timings.get("surface_sec", 0.0), 1),
            "tabletop_film_close_radius_m": json.loads((work / "surface_log.json").read_text())["close_radius_m"]}
    return record


def main():
    args = parse_args()
    suite = args.suite_root.expanduser().resolve()
    published = args.publish_root or suite
    runs, cases = suite / "runs", suite / "cases"
    records = {plan["case_id"]: build_case(args, plan, runs, cases, published) for plan in plans() if plan["case_id"] in args.cases}
    if args.no_manifest:
        return
    manifest_path = suite / "suite_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    previous = {entry["case_id"]: entry for entry in [manifest.get("source")] + manifest.get("edits", []) if entry}
    previous.update(records)
    source = previous.get(SOURCE_CASE_ID)
    from contact_geometry import ledger
    manifest = {
        "schema_version": 3, "suite_name": SUITE_NAME, "interaction_category": "rigid_fluid",
        "description": "A ceramic cup of water rests at a 58° tilt on a walnut block; the water drains over its low rim and "
                       "spreads across a sunlit oak kitchen worktop.",
        "coupling": "Genesis 1.4.3 DFSPH at 1 mm; the fixed cup, the support block and the tabletop are static ghost-particle "
                    "boundaries that carry their own pressure (split density solve); Akinci surface tension calibrated to "
                    "0.072 N/m; glaze and oak fully wetted (ghost wetting 1.0) with contact-line friction 1000/s on the oak; "
                    "viscosity above 2e-5 m²/s by an implicit no-slip solve",
        "baseline_physics": edit_vocab.BASELINE_PHYSICS,
        "total_frames": FRAMES, "resolution": RENDER["resolution"], "fps": edit_vocab.FPS, "duration_sec": edit_vocab.DURATION_SEC,
        "samples": SAMPLES, "render": RENDER,
        "source_case_id": SOURCE_CASE_ID, "selected_base_video_sha256": source["video_sha256"] if source else None,
        "geometry": ledger(),
        "assets": {"environment": "assets/rigid_fluid/tilted_cup_environment (studio_small_09 HDRI, White Oak Veneer, "
                                  "coffee_cup_set plates, cutting board, linen)"},
        "source": source,
        "edits": [previous[e["case_id"]] for e in EDITS if e["case_id"] in previous]}
    write_json(manifest_path, manifest)
    print(f"PCVE_GENESIS_SUITE {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
