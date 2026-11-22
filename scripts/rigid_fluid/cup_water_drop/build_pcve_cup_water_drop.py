"""Public entry point: the source video of a water-filled mug dropped onto a dining table (Genesis two-way coupling).

Builds the mug geometry and the plate and napkin colliders (geometry_*, cavity_*) when missing, then per case settles the
water in the held mug and simulates the drop (simulate_*), reconstructs the water surface and the drops landed on the
table (surface_*) and renders the dining-table scene (render_*). Source: a 72 mm ceramic mug holding 240 mL of water,
released with its base 0.284 m above the table. Each step is skipped when its output exists and only missing frames are
rendered, so an interrupted build resumes. Each case keeps video.mp4 and its bilingual prompts.json in
<suite-root>/cases/<case_id>/, intermediates go to <suite-root>/runs/<case_id>/, and the configuration and run
summaries to <suite-root>/suite_manifest.json (`source` and `edits`, as in the other PCVE suites; no edits yet).
    CUDA_VISIBLE_DEVICES=<gpu> <genesis python> build_pcve_cup_water_drop.py --suite-root SUITE --blender BLENDER
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / "scripts")]
import edit_vocab  # noqa: E402
import layout_cup_water_drop as layout  # noqa: E402
import pcve_edit_dsl as dsl  # noqa: E402

NAME = "cup_water_drop"
SUITE_NAME = f"pcve_{NAME}_suite"
SOURCE_CASE_ID = "cup_water_drop_baseline"
FRAMES = edit_vocab.VOCAB.total_frames
SAMPLES = 64
PARTICLE_ML = 0.8 * 0.001 ** 3 * 1e6     # liquid volume of one 1 mm DFSPH particle (Genesis: 0.8 d^3)
SOURCE = {
    "case_id": SOURCE_CASE_ID, "kind": "source", "interaction_category": "rigid_fluid",
    "description": {
        "vague": {"en": "A white ceramic mug of water falls onto a wooden dining table and lands upright with a small hop; the water "
                        "inside splashes up in a little crown and settles, and a few tiny drops land on the table.",
                  "zh": "一只装着水的白色陶瓷杯掉到木质餐桌上，直立着落地并轻轻弹了一下；杯里的水溅起一圈小水花后平静下来，"
                        "几滴小水珠落在桌面上。"},
        "quantitative": {"en": "A 72 mm, 0.32 kg ceramic mug holding 240 mL of water (998.2 kg/m³, 1.0e-6 m²/s, surface tension "
                               "0.072 N/m) is released from rest with its base 0.284 m above the table under 9.81 m/s² gravity. It "
                               "lands upright 0.24 s later at 2.4 m/s, rebounds at about 0.2 m/s and comes to rest; inside, the water "
                               "surface erupts into a crown and a short central jet that fall back within 0.2 s, and about 0.05 mL of "
                               "water ends up on the table as a few small drops.",
                         "zh": "一只高 72 mm、质量 0.32 kg 的陶瓷杯装有 240 mL 水（密度 998.2 kg/m³，运动黏度 1.0e-6 m²/s，表面张力 "
                               "0.072 N/m），在 9.81 m/s² 重力下从杯底高出桌面 0.284 m 处由静止释放；0.24 s 后以 2.4 m/s 直立落到桌上，"
                               "以约 0.2 m/s 弹起后静止；杯中水面溅起一圈水花和一道短的中心射流，0.2 s 内落回，约 0.05 mL 水以几滴"
                               "小水珠落在桌面上。"}},
    "physics": edit_vocab.BASELINE_PHYSICS,
}
EDITS = (
    {"case_id": "edit_heavy_cup", "kind": "edit", "edit_dsl": "SET cup.mass TIMES 2.5",
     "edit_summary": "The ceramic mug mass increases 2.5-fold from 0.32 kg to 0.80 kg: with 2.5 times higher inertia, the mug impacts the table harder, rebounds with higher momentum, and the water inside splashes up more violently against the heavier walls."},
    {"case_id": "edit_high_viscosity_water", "kind": "edit", "edit_dsl": "SET water.viscosity TIMES 100",
     "edit_summary": "Water kinematic viscosity increases 100-fold from 1.0e-6 m²/s to 1.0e-4 m²/s, like a light syrup: viscous shear strongly dampens droplet breakup and splashing, keeping the water inside the mug with no fine droplets ejected onto the table."},
    {"case_id": "edit_low_density_water", "kind": "edit", "edit_dsl": "SET water.density TIMES 0.6",
     "edit_summary": "Water density decreases to 0.6 times its original value, from 998.2 kg/m³ to 598.92 kg/m³: the fluid has less inertia relative to the mug, allowing the splash wave to erupt more sharply upon deceleration."},
    {"case_id": "edit_delete_water", "kind": "edit", "edit_dsl": "DELETE water",
     "edit_summary": "Water is removed from the first frame: the empty dry mug falls, hits the dining table, rebounds with a slight bounce and comes to rest upright; the table and saucer remain completely dry."},
)
RENDER = {"engine": "Cycles", "samples": SAMPLES, "denoising": True, "seed": 0, "motion_blur_shutter_frames": 0.38,
          "resolution": [1280, 720], "fps": edit_vocab.FPS, "color_management": "AgX, Medium High Contrast look, exposure -1",
          "camera": {"location_m": list(layout.CAMERA_LOCATION), "target_m": list(layout.CAMERA_TARGET),
                     "lens_mm": layout.CAMERA_LENS_MM, "sensor_mm": layout.CAMERA_SENSOR_MM},
          "holds": {"tolerance_m": 1e-4, "tolerance_deg": 0.25, "min_frames": 3, "fade_frames": 6},
          "look": {"water": "clear (IOR 1.333, roughness 0.025) with absorption 1.2/m (0.48, 0.82, 0.92)",
                   "mug": "BlenderKit MUG.004 porcelain with its subdivision modifier evaluated, roughness 0.24"}}
GEOMETRY_FILES = ("cup_local.obj", "cup_export.json", "cavity.json", "plate_collider.obj", "napkin_collider.obj")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite-root", type=Path, required=True)
    parser.add_argument("--cup-asset", type=Path, default=ROOT / "assets/blenderkit/coffee_cup_set/coffee_cup_set.blend")
    parser.add_argument("--geometry", type=Path, default=HERE / "geometry", help="mug and collider geometry (built when missing)")
    parser.add_argument("--blender", default=os.environ.get("BLENDER", "blender"))
    parser.add_argument("--python", default=sys.executable, help="interpreter of the Genesis environment")
    parser.add_argument("--publish-root", type=Path, help="suite path recorded in the manifest's outputs (default: --suite-root)")
    parser.add_argument("--cases", nargs="*", default=[SOURCE_CASE_ID] + [e["case_id"] for e in EDITS])
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
                    "physics_diff": {f"{edit.property_name} ({edit.object_id})": {"from": dsl.baseline_value_for(edit, vocab),
                                                                                  "to": edit.to_value},
                                     "timing": dsl.timing_diff(edit, vocab)},
                    "prompts": dsl.make_prompts(edit, vocab)}
        edits.append({**case, "physics": {**SOURCE["physics"], **dsl.to_physics_override(edit, vocab)}, "prompts_document": document})
    return [source] + edits


def build_geometry(args):
    if all((args.geometry / name).exists() for name in GEOMETRY_FILES):
        return
    args.geometry.mkdir(parents=True, exist_ok=True)
    run([args.blender, "-b", args.cup_asset, "--python-exit-code", "1", "--python", HERE / f"appearance/geometry_{NAME}.py", "--",
         args.geometry], args.geometry / "geometry.log")
    run([args.python, HERE / f"physics/cavity_{NAME}.py", args.geometry], args.geometry / "cavity.log")


def check_run(sim_args, physics):
    """The finished simulation used this case's physics."""
    half = layout.CUP_HEIGHT / 2
    assert math.isclose(sim_args["density"], physics["water_density_kg_m3"], rel_tol=1e-9), "water density"
    assert math.isclose(sim_args["mu"], physics["water_kinematic_viscosity_m2_s"], rel_tol=1e-9), "water viscosity"
    assert math.isclose(sim_args["cup_mass"], physics["cup_mass_kg"], rel_tol=1e-9), "cup mass"
    assert math.isclose(sim_args["surface_tension"], physics["water_surface_tension_n_m"] * edit_vocab.ST_GAMMA_PER_N_M,
                        rel_tol=1e-6), "surface tension"
    assert math.isclose(sim_args["release"][2] - half, physics["cup_release_bottom_height_m"], abs_tol=1e-9), "release height"
    assert math.isclose(sim_args["yaw_deg"], physics["cup_yaw_deg"]) and math.isclose(sim_args["fill_z"], physics["water_fill_top_in_cup_frame_m"])


def build_case(args, plan, runs, cases, published):
    work = runs / plan["case_id"]
    relax = work / "relax"
    work.mkdir(parents=True, exist_ok=True)
    timings_path = work / "timings.json"
    timings = json.loads(timings_path.read_text()) if timings_path.exists() else {}
    flags = edit_vocab.sim_args(plan["physics"])
    if not (relax / "water_relaxed.npz").exists():
        relax.mkdir(exist_ok=True)
        timings["relax_sec"] = run([args.python, "-u", HERE / f"simulate_{NAME}.py", "relax", "--geom", args.geometry,
                                    "--out", relax, *flags], relax / "relax.log")
        write_json(timings_path, timings)
    if not (work / "sim_log.json").exists() or json.loads((work / "sim_log.json").read_text())["simulated_frames"] < FRAMES - 5:
        run([args.python, "-u", HERE / f"simulate_{NAME}.py", "drop", "--geom", args.geometry, "--out", work,
             "--water-state", relax / "water_relaxed.npz", "--frames", FRAMES, *flags], work / "sim.log")
    if not (work / "surface_log.json").exists():
        timings["surface_sec"] = run([args.python, HERE / f"surface_{NAME}.py", work], work / "surface.log")
        write_json(timings_path, timings)
    frames = work / "frames"
    missing = [f for f in range(1, FRAMES + 1) if not (frames / f"frame_{f:04d}.png").exists()]
    if missing:
        seconds = run([args.blender, "-b", "--python-exit-code", "1", "--python", HERE / f"render_{NAME}.py", "--",
                       work, args.cup_asset, frames, SAMPLES, "" if len(missing) == FRAMES else ",".join(map(str, missing))],
                      work / "render.log")
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

    log = json.loads((work / "sim_log.json").read_text())
    relax_log = json.loads((relax / "relax_log.json").read_text())
    check_run(log["args"], plan["physics"])
    rows = log["frames"]
    surface_log = json.loads((work / "surface_log.json").read_text())
    n = log["n_particles"]
    impact = next(r for r in rows if r["cup_vz"] > -0.5 and r["frame"] > log["start_frame"])
    after = [r for r in rows if r["frame"] >= impact["frame"]]
    spilled = round(n * (1 - rows[-1]["water_in_cup"]))
    record = {key: plan[key] for key in ("case_id", "kind", "interaction_category", "description") if key in plan}
    if plan["kind"] == "edit":
        document = plan["prompts_document"]
        record = {"case_id": plan["case_id"], "kind": "edit",
                  **{key: document[key] for key in ("source_case_id", "edit_dsl", "edit_summary", "applies_from_frame", "physics_diff", "prompts")}}
    skip = ("geom", "out", "water_state")
    record.update({
        "status": "completed",
        "elapsed_sec": round(relax_log["build_sec"] + relax_log["relax_wall_sec"] + log["build_sec"] + log["sim_sec"]
                             + timings.get("surface_sec", 0.0) + timings.get("render_sec", 0.0), 1),
        "outputs": {"video": str(published / "cases" / plan["case_id"] / "video.mp4"),
                    "prompts": str(published / "cases" / plan["case_id"] / "prompts.json")},
        "video_sha256": digest(case / "video.mp4"),
        "physics": plan["physics"],
        "numerics": {"relax": {k: v for k, v in relax_log["args"].items() if k not in skip},
                     "drop": {k: v for k, v in log["args"].items() if k not in skip and not k.startswith("relax_")}},
        "simulation": {"frames": FRAMES, "analytic_free_fall_frames": log["start_frame"] - 1,
                       "simulated_frames": len(rows), "water_particles": n, "ghost_particles": log["n_ghosts"],
                       "water_volume_ml": round(n * PARTICLE_ML, 1),
                       "relaxed_surface_in_cup_frame_m": round(relax_log["surface_z_995_m"], 5),
                       "seconds_per_frame": round(log["sim_sec"] / max(1, len(rows) - 1), 1),
                       "impact_frame": impact["frame"],
                       "water_energy_per_kg_before_after_impact": [round(rows[0]["water_E_per_kg"], 3),
                                                                   round(impact["water_E_per_kg"], 3)],
                       "cup_rebound_speed_m_s": round(max(r["cup_vz"] for r in after), 3),
                       "cup_final_center_z_m": round(rows[-1]["cup_z"], 4),
                       "cup_final_tilt_deg": round(rows[-1]["cup_tilt_deg"], 3),
                       "water_in_cup_final_fraction": round(rows[-1]["water_in_cup"], 5),
                       "spilled_particles": spilled, "spilled_ml": round(spilled * PARTICLE_ML, 3),
                       "drops_on_table": surface_log["frames"][-1]["drops"],
                       "peak_particle_speed_after_impact_m_s": round(max(r["max_speed"] for r in after), 3),
                       "final_peak_particle_speed_m_s": round(rows[-1]["max_speed"], 3)},
        "render": {**RENDER, "held_frames": surface_log["holds"]["held_frames"], "hold_segments": surface_log["holds"]["segments"]}})
    return record


def main():
    args = parse_args()
    suite = args.suite_root.expanduser().resolve()
    published = args.publish_root or suite
    runs, cases = suite / "runs", suite / "cases"
    args.geometry = args.geometry.expanduser().resolve()
    build_geometry(args)
    records = {plan["case_id"]: build_case(args, plan, runs, cases, published) for plan in plans() if plan["case_id"] in args.cases}

    manifest_path = suite / "suite_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    previous = {entry["case_id"]: entry for entry in [manifest.get("source")] + manifest.get("edits", []) if entry}
    previous.update(records)
    source = previous.get(SOURCE_CASE_ID)
    cavity = json.loads((args.geometry / "cavity.json").read_text())
    manifest = {
        "schema_version": 3, "suite_name": SUITE_NAME, "interaction_category": "rigid_fluid",
        "description": "A 72 mm ceramic mug holding 240 mL of water is dropped from 0.284 m onto a wooden dining table next to a "
                       "side plate and a folded napkin; it lands upright, the water splashes inside the mug and a few drops "
                       "land on the table.",
        "coupling": "Genesis 1.4.3 free rigid mug and DFSPH water, two-way coupled through ghost particles in the ceramic that "
                    "carry their own pressure (equal and opposite impulses on the mug); split density solve (motion-caused "
                    "compression through the velocity, existing compression through the positions only, inelastically); "
                    "Akinci surface tension calibrated to 0.072 N/m on a fully wetted mug; the table, plate and napkin are "
                    "fixed colliders",
        "baseline_physics": edit_vocab.BASELINE_PHYSICS,
        "total_frames": FRAMES, "resolution": RENDER["resolution"], "fps": edit_vocab.FPS, "duration_sec": edit_vocab.DURATION_SEC,
        "samples": SAMPLES, "render": RENDER,
        "source_case_id": SOURCE_CASE_ID, "selected_base_video_sha256": source["video_sha256"] if source else None,
        "geometry": {"cup_inner_floor_z_cup_frame_m": round(cavity["inner_floor_z"], 5), "cup_rim_z_cup_frame_m": round(cavity["rim_z"], 5),
                     "cup_vertices": json.loads((args.geometry / "cup_export.json").read_text())["n_vertices"],
                     "plate_xy_m": list(layout.PLATE_XY), "napkin_xy_m": list(layout.NAPKIN_XY), "table_top_z_m": 0.0},
        "assets": {"cup_blend": "assets/blenderkit/coffee_cup_set/coffee_cup_set.blend", "cup_object": layout.CUP_ASSET_OBJECT,
                   "cup_asset_id": layout.CUP_ASSET_ID,
                   "cup_asset_page": f"https://www.blenderkit.com/asset-gallery-detail/{layout.CUP_ASSET_ID}/",
                   "environment": "procedural (render_cup_water_drop.py)"},
        "source": source,
        "edits": [previous[e["case_id"]] for e in EDITS if e["case_id"] in previous]}
    write_json(manifest_path, manifest)
    print(f"PCVE_GENESIS_SUITE {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
