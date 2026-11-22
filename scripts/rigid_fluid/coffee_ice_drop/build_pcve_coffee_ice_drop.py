"""Public entry point: the source and edited videos of an ice cube dropped into coffee (Genesis two-way coupling).

Builds the cup-set geometry (geometry_*, cavity_*) when missing, then per case simulates (simulate_*), reconstructs the
coffee surface and the drops landed on the saucer (surface_*) and renders in the restaurant stage (render_*). Source: a
16 mm ice cube released 4 cm above the coffee; edits: `SET coffee.density TIMES 0.625`, `SET coffee.viscosity TIMES
1000000`, `DELETE ice` and `DELETE coffee` (edit_vocab.py maps each onto simulation flags). Every case shares the
geometry, the release pose and all numerics. Each step is skipped when its output exists and only missing frames are
rendered, so an interrupted build resumes. Each case keeps video.mp4 and its bilingual prompts.json in
<suite-root>/cases/<case_id>/, intermediates go to <suite-root>/runs/<case_id>/, and the configuration and run
summaries to <suite-root>/suite_manifest.json (`source` and `edits`, as in the other PCVE suites).
    CUDA_VISIBLE_DEVICES=<gpu> <genesis python> build_pcve_coffee_ice_drop.py --suite-root SUITE --blender BLENDER
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
import pcve_edit_dsl as dsl  # noqa: E402

NAME = "coffee_ice_drop"
SUITE_NAME = f"pcve_{NAME}_suite"
SOURCE_CASE_ID = "coffee_ice_drop_baseline"
FRAMES = edit_vocab.VOCAB.total_frames
SAMPLES = 128
PARTICLE_ML = 0.8 * 0.001 ** 3 * 1e6     # liquid volume of one 1 mm DFSPH particle (Genesis: 0.8 d^3)
ICE_ASSET_ID = "26692bef-66d6-4d54-bb63-cf9b68601af4"
SOURCE = {
    "case_id": SOURCE_CASE_ID, "kind": "source", "interaction_category": "rigid_fluid",
    "description": {
        "vague": {"en": "A small clear ice cube drops into a cup of coffee, splashes a few drops onto the saucer, sinks to the bottom "
                        "and bobs back up to float at the surface.",
                  "zh": "一块透明的小冰块掉进一杯咖啡里，溅出几滴咖啡落在托盘上，冰块先沉到杯底，再浮上来漂在液面。"},
        "quantitative": {"en": "A 16 mm ice cube (920 kg/m³) is released with its lowest corner 4 cm above coffee (1030 kg/m³, 1.45e-6 m²/s) "
                               "in a ceramic mug under 9.81 m/s² gravity; it hits the cup floor 0.17 s after release, splashes about "
                               "0.35 mL onto the saucer, and from 0.6 s on floats with its centre 6 mm below the coffee surface.",
                         "zh": "一块边长 16 mm、密度 920 kg/m³ 的冰块在 9.81 m/s² 重力下从最低角高出液面 4 cm 处释放，落入陶瓷杯中的咖啡"
                               "（密度 1030 kg/m³，运动黏度 1.45e-6 m²/s）；释放后 0.17 s 触到杯底，溅出约 0.35 mL 咖啡到托盘上，"
                               "0.6 s 起浮在液面，中心位于液面下 6 mm。"}},
    "physics": edit_vocab.BASELINE_PHYSICS,
}
EDITS = (
    {"case_id": "edit_low_density_coffee", "kind": "edit", "edit_dsl": "SET coffee.density TIMES 0.625",
     "edit_summary": "Coffee density drops from 1030 to 643.75 kg/m³, below the 920 kg/m³ ice: the splash is the same, but the ice "
                     "stays on the cup floor instead of floating back up (its centre ends 17.5 mm lower than in the source, "
                     "0.819 m instead of 0.836 m)."},
    {"case_id": "edit_high_viscosity_coffee", "kind": "edit", "edit_dsl": "SET coffee.viscosity TIMES 1000000",
     "edit_summary": "Coffee kinematic viscosity rises a million-fold to 1.45 m²/s: the ice is caught at the surface on impact "
                     "instead of plunging to the cup floor, nothing splashes or spills, and it stays there, sinking only about "
                     "1 mm in 4 s (centre 0.851 to 0.850 m) instead of floating at 0.836 m as in the source."},
    {"case_id": "edit_delete_ice", "kind": "edit", "edit_dsl": "DELETE ice",
     "edit_summary": "The ice is removed from the first frame: the coffee stays at rest in the cup for the whole clip, with no "
                     "splash, no spill and its surface at the source's fill height."},
    {"case_id": "edit_delete_coffee", "kind": "edit", "edit_dsl": "DELETE coffee",
     "edit_summary": "The coffee is removed from the first frame: the ice falls through the empty mug, lands on its floor 0.13 s "
                     "after release and rests there (centre at 0.817 m, 20 mm below its floating height in the source)."},
)
RENDER = {"engine": "Cycles", "samples": SAMPLES, "adaptive_sampling": False, "motion_blur_shutter_deg": 180,
          "resolution": [1280, 720], "fps": edit_vocab.FPS,
          "camera": {"lens_mm": 58.0, "elevation_deg": 30.0, "distance_m": 0.50, "target_z_m": 0.862,
                     "azimuth": "the stage's accepted view (-1.41, -6.77) -> cup"},
          "holds": {"tolerance_m": 1e-4, "tolerance_deg": 0.25, "min_frames": 3, "fade_frames": 6},
          "look": {"coffee": "absorption 1500/m (0.65, 0.38, 0.18) + scatter 900/m (0.75, 0.45, 0.25)",
                   "ice": "BlenderKit realistic ice cube, volume-matched to the 16 mm cube, clear (IOR 1.31) with a cloudy core"}}
GEOMETRY_FILES = ("cup_world.obj", "saucer_world.obj", "spoon_world.obj", "beans_world.obj", "geom_info.json",
                  "cavity.json", "saucer_solid.obj")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite-root", type=Path, required=True)
    parser.add_argument("--input-blend", type=Path, default=ROOT / "assets/scenes/coffee_ice_drop/loft_restaurant_stage.blend",
                        help="the loft restaurant stage .blend: the cup set is exported from it and every frame is rendered in it")
    parser.add_argument("--ice-asset", type=Path, default=ROOT / "assets/blenderkit/realistic_ice_cube/realistic_ice_cube.blend")
    parser.add_argument("--geometry", type=Path, default=HERE / "geometry", help="cup-set geometry (exported when missing)")
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
                    "physics_diff": {**({f"presence ({edit.object_id})": {"from": True, "to": False}} if isinstance(edit, dsl.DeleteEdit) else
                                        {f"{edit.property_name} ({edit.object_id})": {"from": dsl.baseline_value_for(edit, vocab), "to": edit.to_value}}),
                                     "timing": dsl.timing_diff(edit, vocab)},
                    "prompts": dsl.make_prompts(edit, vocab)}
        edits.append({**case, "physics": {**SOURCE["physics"], **dsl.to_physics_override(edit, vocab)}, "prompts_document": document})
    return [source] + edits


def build_geometry(args):
    if all((args.geometry / name).exists() for name in GEOMETRY_FILES):
        return
    args.geometry.mkdir(parents=True, exist_ok=True)
    run([args.blender, "-b", args.input_blend, "--python-exit-code", "1", "--python", HERE / f"appearance/geometry_{NAME}.py", "--", args.geometry],
        args.geometry / "geometry.log")
    run([args.python, HERE / f"physics/cavity_{NAME}.py", args.geometry], args.geometry / "cavity.log")


def check_run(sim_args, physics):
    """The finished simulation used this case's physics."""
    nu = sim_args["implicit_nu"] or sim_args["mu"]
    assert math.isclose(sim_args["coffee_density"], physics["coffee_density_kg_m3"], rel_tol=1e-9), "coffee density"
    assert math.isclose(sim_args["ice_density"], physics["ice_density_kg_m3"], rel_tol=1e-9), "ice density"
    assert math.isclose(nu, physics["coffee_kinematic_viscosity_m2_s"], rel_tol=1e-9), "coffee viscosity"
    assert math.isclose(sim_args["ice_side"], physics["ice_side_m"]) and math.isclose(sim_args["gravity"], physics["gravity_m_s2"])
    assert sim_args["no_ice"] == (not physics["ice_presence"][0]) and sim_args["no_coffee"] == (not physics["coffee_presence"][0])


def build_case(args, plan, runs, cases, published):
    work = runs / plan["case_id"]
    work.mkdir(parents=True, exist_ok=True)
    timings_path = work / "timings.json"
    timings = json.loads(timings_path.read_text()) if timings_path.exists() else {}
    if not (work / "sim_log.json").exists():
        run([args.python, "-u", HERE / f"simulate_{NAME}.py", "--geom", args.geometry, "--out", work,
             *edit_vocab.sim_args(plan["physics"])], work / "sim.log")
    if not (work / "surface_log.json").exists():
        timings["surface_sec"] = run([args.python, HERE / f"surface_{NAME}.py", work], work / "surface.log")
        write_json(timings_path, timings)
    frames = work / "frames"
    missing = [f for f in range(1, FRAMES + 1) if not (frames / f"frame_{f:04d}.png").exists()]
    if missing:
        seconds = run([args.blender, "-b", args.input_blend, "--python-exit-code", "1", "--python", HERE / f"render_{NAME}.py", "--",
                       work, args.ice_asset, frames, SAMPLES, "" if len(missing) == FRAMES else ",".join(map(str, missing))],
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
    check_run(log["args"], plan["physics"])
    rows = log["frames"]
    surface_log = json.loads((work / "surface_log.json").read_text())
    drops = surface_log["frames"]
    ice = [r["ice_z"] for r in rows if "ice_z" in r]
    lowest = min(range(len(ice)), key=ice.__getitem__) if ice else None
    spilled = log["n_particles"] - rows[-1]["coffee_in_cup"]
    record = {key: plan[key] for key in ("case_id", "kind", "interaction_category", "description") if key in plan}
    if plan["kind"] == "edit":
        document = plan["prompts_document"]
        record = {"case_id": plan["case_id"], "kind": "edit",
                  **{key: document[key] for key in ("source_case_id", "edit_dsl", "edit_summary", "applies_from_frame", "physics_diff", "prompts")}}
    record.update({
        "status": "completed",
        "elapsed_sec": round(log["build_sec"] + log["sim_sec"] + timings.get("surface_sec", 0.0) + timings.get("render_sec", 0.0), 1),
        "outputs": {"video": str(published / "cases" / plan["case_id"] / "video.mp4"),
                    "prompts": str(published / "cases" / plan["case_id"] / "prompts.json")},
        "video_sha256": digest(case / "video.mp4"),
        "physics": plan["physics"],
        "numerics": {key: value for key, value in log["args"].items() if key not in ("geom", "out")},
        "simulation": {"frames": len(rows), "coffee_particles": log["n_particles"],
                       "seconds_per_frame": round(log["sim_sec_per_frame"], 2),
                       "ice_lowest_center_z_m": round(ice[lowest], 4) if ice else None,
                       "ice_lowest_frame": rows[lowest]["frame"] if ice else None,
                       "ice_final_center_z_m": round(ice[-1], 4) if ice else None,
                       "ice_final_fluid_force_over_weight": round(rows[-1]["fluid_force_z_over_weight"], 3)
                                                            if "fluid_force_z_over_weight" in rows[-1] else None,
                       "coffee_final_surface_z_m": round(rows[-1]["top_z_995"], 4) if rows[-1]["top_z_995"] is not None else None,
                       "spilled_particles": spilled, "spilled_ml": round(spilled * PARTICLE_ML, 3),
                       "drops_on_saucer_or_table": drops[-1]["drops"],
                       # frame 1 still carries the settled cup's resting noise
                       "peak_particle_speed_m_s": round(max(r["max_speed"] for r in rows[1:]), 3)},
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
        "description": "A 16 mm ice cube drops into coffee in a ceramic mug in the loft restaurant, splashes onto the saucer, "
                       "sinks to the cup floor and floats back up; the edits lower the coffee's density below the ice's, raise its "
                       "viscosity a million-fold, or delete the ice or the coffee.",
        "coupling": "Genesis 1.4.3 rigid ice and DFSPH coffee, two-way coupled through shell ghost particles on the ice "
                    "(equal and opposite pressure impulses); the high-viscosity edit adds a monolithic implicit viscosity "
                    "solve over the liquid and the ice",
        "baseline_physics": edit_vocab.BASELINE_PHYSICS,
        "total_frames": FRAMES, "resolution": RENDER["resolution"], "fps": edit_vocab.FPS, "duration_sec": edit_vocab.DURATION_SEC,
        "samples": SAMPLES, "render": RENDER,
        "source_case_id": SOURCE_CASE_ID, "selected_base_video_sha256": source["video_sha256"] if source else None,
        "geometry": {"cup_center_xy_m": json.loads((args.geometry / "geom_info.json").read_text())["cup_center_xy"],
                     "cup_inner_floor_z_m": round(cavity["inner_floor_z"], 5), "cup_rim_z_m": round(cavity["rim_z"], 5)},
        "assets": {"stage": "assets/scenes/coffee_ice_drop/loft_restaurant_stage.blend",
                   "ice_blend": "assets/blenderkit/realistic_ice_cube/realistic_ice_cube.blend", "ice_asset_id": ICE_ASSET_ID,
                   "ice_asset_page": f"https://www.blenderkit.com/asset-gallery-detail/{ICE_ASSET_ID}/"},
        "source": source,
        "edits": [previous[e["case_id"]] for e in EDITS if e["case_id"] in previous]}
    write_json(manifest_path, manifest)
    print(f"PCVE_GENESIS_SUITE {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
