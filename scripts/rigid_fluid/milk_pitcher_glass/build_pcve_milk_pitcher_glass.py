"""Public entry point: milk poured from a carton into a clear glass cup (Genesis 1.4.3 DFSPH, 1 mm) and its edits.

An opaque 1 L milk carton, tipped over the cup, pours whole milk from its open screw spout at 75 mL/s from 0.25 s on.
Per case: simulate (simulate_*), build the milk surface (surface_*) and render the daylight kitchen template
(render_*, assets/scenes/milk_pitcher_glass/milk_carton_kitchen.blend). Each step is skipped when its output exists and only missing frames are
rendered, so an interrupted build resumes. An edit that lands at frame F continues the source's frame-F state and keeps
the source's frames 1..F; DELETE milk renders the empty scene once. Each case keeps video.mp4 and its bilingual
prompts.json in <suite-root>/cases/<case_id>/, intermediates go to <suite-root>/runs/<case_id>/, and the configuration and
run summaries to <suite-root>/suite_manifest.json.
    CUDA_VISIBLE_DEVICES=<gpu> <genesis python> build_pcve_milk_pitcher_glass.py --suite-root SUITE --blender BLENDER
"""
from __future__ import annotations
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import asset
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

NAME = "milk_pitcher_glass"
SUITE_NAME = f"pcve_{NAME}_suite"
SOURCE_CASE_ID = "milk_pitcher_glass_baseline"
FRAMES = edit_vocab.VOCAB.total_frames
SAMPLES = 64
TEMPLATE = asset("scenes/milk_pitcher_glass/milk_carton_kitchen.blend")
SOURCE = {
    "case_id": SOURCE_CASE_ID, "kind": "source", "interaction_category": "rigid_fluid",
    "description": {
        "vague": {"en": "A white milk carton is tipped over a clear glass cup on a wooden kitchen counter and milk pours from its "
                        "open spout in a smooth arc, splashing briefly on the bottom and then filling the cup steadily.",
                  "zh": "一盒白色牛奶斜举在木质厨房台面上的透明玻璃杯上方，牛奶从打开的瓶口划出一道平滑的弧线流下，先在杯底"
                        "溅起一点，然后稳稳地把杯子装满。"},
        "quantitative": {"en": "Whole milk (1030 kg/m³, 2.2e-6 m²/s, surface tension 0.046 N/m) leaves the 16 mm spout of a 1 L "
                               "carton held at 135° at 0.37 m/s (75 mL/s) from 0.25 s on, 16 cm above the counter, under "
                               "9.81 m/s² gravity. The stream falls into the clear glass, reaching the bottom at 0.37 s; by 4 s "
                               "277 mL has poured, 271 mL of it in the cup (milk 2.5 cm deep) and less than 0.1 mL spilled.",
                         "zh": "全脂牛奶（密度 1030 kg/m³，运动黏度 2.2e-6 m²/s，表面张力 0.046 N/m）从倾斜 135° 的 1 L 牛奶盒"
                               "直径 16 mm 的瓶口以 0.37 m/s（75 mL/s）流出，从 0.25 s 开始，出口离台面 16 cm，重力 9.81 m/s²。"
                               "液流落入透明玻璃杯，0.37 s 到达杯底；到 4 s 共倒出 277 mL，其中 271 mL 在杯中（深 2.5 cm），"
                               "洒出不到 0.1 mL。"}},
    "physics": edit_vocab.BASELINE_PHYSICS,
}
EDITS = (
    {"case_id": "edit_high_flow_speed", "kind": "edit", "edit_dsl": "SET milk.flow_speed TIMES 2",
     "edit_summary": "The milk leaves the spout twice as fast, 0.74 m/s (150 mL/s): the stream arcs further and lands nearer the "
                     "far wall of the cup, and by 4 s 553 mL has poured (544 mL in the cup, 6 cm deep) instead of 277 mL."},
    {"case_id": "edit_low_flow_speed", "kind": "edit", "edit_dsl": "SET milk.flow_speed TIMES 0.5",
     "edit_summary": "The milk leaves the spout at half the speed, 0.19 m/s (37.5 mL/s): a thinner stream that falls almost "
                     "straight down, and by 4 s 138 mL has poured instead of 277 mL."},
    {"case_id": "edit_delete_milk", "kind": "edit", "edit_dsl": "DELETE milk",
     "edit_summary": "There is no milk: the tipped carton pours nothing and the glass stays empty for the whole clip."},
    {"case_id": "edit_stop_after_2s", "kind": "edit", "edit_dsl": "SET milk.flow_speed TO 0.0 AT FRAME 49",
     "edit_summary": "Identical to the source until 2.0 s (frame 49); then no more milk leaves the spout, the stream's tail "
                     "falls into the cup within 0.1 s and the milk settles at 131 mL instead of filling on to 277 mL."},
)
RENDER = {"engine": "Cycles", "samples": SAMPLES, "denoising": True, "motion_blur_shutter_frames": 0.5,
          "resolution": [1280, 720], "fps": edit_vocab.FPS, "template": "assets/scenes/milk_pitcher_glass/milk_carton_kitchen.blend",
          "look": {"milk": "whole milk, subsurface weight 1, radius (1, 0.82, 0.55) x 1.2 mm, roughness 0.12, IOR 1.35",
                   "milk_in_glass": "volume-conserving height field over the glass floor (smoothed 3 mm, sealed into the glass)",
                   "stream_and_splash": "pysplashsurf, cut where it enters the milk in the glass; spray of 6-60 particles as "
                                        "drops, drops of fewer than 40 particles stuck on the glass not drawn",
                   "carton": "procedural 1 L brick carton (95 x 64 x 166 mm), printed board, threaded spout, cap on the counter",
                   "scene": "daylight kitchen (window daylight, oak counter, sage wall)"}}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite-root", type=Path, required=True)
    parser.add_argument("--blender", default=os.environ.get("BLENDER", "blender"))
    parser.add_argument("--python", default=sys.executable, help="interpreter of the Genesis environment")
    parser.add_argument("--device", choices=("OPTIX", "CUDA"), default="OPTIX",
                        help="Cycles GPU backend passed to the renderer (CUDA where OptiX fails)")
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
    source = {**SOURCE, "at_frame": None,
              "prompts_document": {"schema_version": 1, "case_id": SOURCE_CASE_ID, "kind": "source", "prompts": SOURCE["description"]}}
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
        edits.append({**case, "at_frame": edit.at_frame if dsl.is_timed(edit) else None,
                      "physics": {**SOURCE["physics"], **dsl.to_physics_override(edit, vocab)}, "prompts_document": document})
    return [source] + edits


def frames_done(directory, frames):
    return [f for f in frames if not (directory / f"frame_{f:04d}.png").exists()]


def build_case(args, plan, runs, cases, published):
    work = runs / plan["case_id"]
    work.mkdir(parents=True, exist_ok=True)
    source_work = runs / SOURCE_CASE_ID
    timings_path = work / "timings.json"
    timings = json.loads(timings_path.read_text()) if timings_path.exists() else {}
    at = plan["at_frame"]
    flags = edit_vocab.sim_args(plan["physics"], at)
    frames_dir = work / "frames"
    milk = flags is not None
    if milk:
        log_path = work / "sim_log.json"
        if not log_path.exists() or len(json.loads(log_path.read_text())["frames"]) < FRAMES:
            extra = ["--resume-from", source_work, "--resume-frame", at - 1] if at else []
            run([args.python, "-u", HERE / f"simulate_{NAME}.py", "--out", work, "--frames", FRAMES, "--fps", edit_vocab.FPS,
                 *flags, *extra], work / "sim.log")
        wanted = list(range(at, FRAMES + 1)) if at else list(range(1, FRAMES + 1))
        surface_log = work / "surface_log.json"
        if not surface_log.exists() or not set(wanted) <= set(json.loads(surface_log.read_text())["frames"]):
            timings["surface_sec"] = run([args.python, HERE / f"surface_{NAME}.py", work, *wanted], work / "surface.log")
            write_json(timings_path, timings)
        if at:                                     # frames before the edit are the source's
            frames_dir.mkdir(exist_ok=True)
            for f in range(1, at):
                target = frames_dir / f"frame_{f:04d}.png"
                if not target.exists():
                    shutil.copy2(source_work / "frames" / target.name, target)
        missing = frames_done(frames_dir, wanted)
        if missing:
            seconds = run([args.blender, "-b", TEMPLATE, "--python-exit-code", "1", "--python", HERE / f"render_{NAME}.py", "--",
                           "--run", work, "--out-dir", frames_dir, "--samples", SAMPLES, "--device", args.device, "--frames", *missing],
                          work / "render.log")
            timings["render_sec"] = timings.get("render_sec", 0.0) + seconds
            write_json(timings_path, timings)
    else:                                          # no milk: a static scene, rendered once
        missing = frames_done(frames_dir, range(1, FRAMES + 1))
        if missing:
            probe = work / "probe"
            if not (probe / "frame_0001.png").exists():
                seconds = run([args.blender, "-b", TEMPLATE, "--python-exit-code", "1", "--python", HERE / f"render_{NAME}.py", "--",
                               "--run", source_work, "--out-dir", probe, "--samples", SAMPLES, "--device", args.device, "--frames", 1,
                               "--no-milk"],
                              work / "render.log")
                timings["render_sec"] = seconds
                write_json(timings_path, timings)
            frames_dir.mkdir(exist_ok=True)
            for f in missing:
                shutil.copy2(probe / "frame_0001.png", frames_dir / f"frame_{f:04d}.png")
    missing_all = frames_done(frames_dir, range(1, FRAMES + 1))
    assert not missing_all, f"{plan['case_id']}: frames missing {missing_all[:8]}"
    video = work / "video.mp4"
    if not video.exists() or video.stat().st_mtime < max((frames_dir / f"frame_{f:04d}.png").stat().st_mtime for f in (1, FRAMES)):
        run(["ffmpeg", "-v", "error", "-y", "-framerate", edit_vocab.FPS, "-i", frames_dir / "frame_%04d.png", "-frames:v", FRAMES,
             "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", video], work / "encode.log")
    probe_out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                                "stream=nb_read_frames", "-of", "csv=p=0", str(video)], capture_output=True, text=True).stdout.strip()
    assert int(probe_out) == FRAMES, f"{video}: {probe_out} frames"
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
                   "video_sha256": digest(case / "video.mp4"), "physics": plan["physics"], "render": RENDER,
                   "elapsed_sec": round(timings.get("surface_sec", 0.0) + timings.get("render_sec", 0.0), 1),
                   "numerics": {}, "simulation": {"frames": FRAMES, "simulated": False, "milk_particles": 0}})
    if milk:
        log = json.loads((work / "sim_log.json").read_text())
        a = log["args"]
        expected_flow = float(flags[1]) if flags[0] == "--flow" else 75e-6
        assert math.isclose(a["flow"], expected_flow, rel_tol=1e-6), "flow"
        assert (a.get("stop", 1e9) >= 1e8) == (at is None), "stop"
        rows = log["frames"]; last = rows[-1]
        record["numerics"] = {k: v for k, v in a.items() if k not in ("out", "cup", "resume_from")}
        record["elapsed_sec"] = round(log["build_sec"] + log["sim_sec"] + record["elapsed_sec"], 1)
        record["simulation"] = {"frames": FRAMES, "simulated": True, "milk_particles": int(round(last["milk_ml"] / (log["particle_volume_m3"] * 1e6))),
                                "ghost_particles": log["n_ghosts"], "spout_exit_speed_m_s": round(log["exit_speed_m_s"], 4),
                                "milk_poured_ml": last["milk_ml"], "milk_in_cup_ml": last["in_cup_ml"],
                                "milk_on_counter_ml": last["on_table_ml"],
                                "peak_particle_speed_m_s": max(r["max_speed"] for r in rows),
                                "seconds_per_frame": round(log["sim_sec"] / max(1, FRAMES - (at or 1)), 1),
                                "continued_from_source_frame": at - 1 if at else None}
    return record


def main():
    args = parse_args()
    suite = args.suite_root.expanduser().resolve()
    published = args.publish_root or suite
    runs, cases = suite / "runs", suite / "cases"
    records = {plan["case_id"]: build_case(args, plan, runs, cases, published) for plan in plans() if plan["case_id"] in args.cases}
    manifest_path = suite / "suite_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    previous = {entry["case_id"]: entry for entry in [manifest.get("source")] + manifest.get("edits", []) if entry}
    previous.update(records)
    source = previous.get(SOURCE_CASE_ID)
    manifest = {
        "schema_version": 3, "suite_name": SUITE_NAME, "interaction_category": "rigid_fluid",
        "description": "Whole milk is poured from a tipped 1 L carton into a clear handled glass cup on a sunlit oak kitchen counter.",
        "coupling": "Genesis 1.4.3 DFSPH at 1 mm; the glass and the counter are static ghost-particle boundaries that carry "
                    "their own pressure (split density solve); Akinci surface tension scaled to milk (0.046 N/m); the milk "
                    "enters through a spout emitter that activates rest-lattice discs at the carton's spout exit",
        "baseline_physics": edit_vocab.BASELINE_PHYSICS,
        "total_frames": FRAMES, "resolution": RENDER["resolution"], "fps": edit_vocab.FPS, "duration_sec": edit_vocab.DURATION_SEC,
        "samples": SAMPLES, "render": RENDER,
        "source_case_id": SOURCE_CASE_ID, "selected_base_video_sha256": source["video_sha256"] if source else None,
        "geometry": {"glass": "geometry/glass_cup.npz (handled glass, 126 mm wide, 103 mm tall, 4 mm walls, 0.1 mm base)",
                     "spout_exit_m": [-0.0345, 0.005, 0.16], "spout_axis": [0.70711, 0.0, -0.70711], "jet_radius_m": 0.008,
                     "counter_top_z_m": 0.0},
        "assets": {"template": "assets/scenes/milk_pitcher_glass/milk_carton_kitchen.blend (packed images)"},
        "source": source,
        "edits": [previous[e["case_id"]] for e in EDITS if e["case_id"] in previous]}
    write_json(manifest_path, manifest)
    print(f"PCVE_GENESIS_SUITE {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
