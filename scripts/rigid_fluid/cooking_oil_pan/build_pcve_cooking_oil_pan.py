"""Public entry point: cooking oil poured from a tilted bottle into a frying pan (Genesis 1.4.3 DFSPH, 0.5 mm) and its edits.

A tilted oil bottle pours over its lower rim into a dark nonstick pan on an induction hob, in a modern kitchen in daylight,
at 10 mL/s from frame 8 on. Per case: simulate (simulate_*), build the oil surface (surface_*) and render the kitchen
template (render_*, assets/scenes/cooking_oil_pan/scene_template.blend). Each step is skipped when its output exists and
only missing frames are rendered, so an interrupted build resumes. An edit that lands at frame F continues the source's
frame F-1 state and keeps the source's frames before F. Each case keeps video.mp4 and its bilingual prompts.json in <suite-root>/cases/<case_id>/,
intermediates go to <suite-root>/runs/<case_id>/, and the configuration and run summaries to <suite-root>/suite_manifest.json.
    CUDA_VISIBLE_DEVICES=<gpu> <genesis python> build_pcve_cooking_oil_pan.py --suite-root SUITE --blender BLENDER
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

NAME = "cooking_oil_pan"
SUITE_NAME = f"pcve_{NAME}_suite"
SOURCE_CASE_ID = "cooking_oil_pan_baseline"
FRAMES = edit_vocab.VOCAB.total_frames
SAMPLES = 64
TEMPLATE = asset("scenes/cooking_oil_pan/scene_template.blend")
SOURCE = {
    "case_id": SOURCE_CASE_ID, "kind": "source", "interaction_category": "rigid_fluid",
    "description": {
        "vague": {"en": "A tilted bottle of cooking oil pours a thin golden stream into a dark nonstick frying pan on an induction "
                        "hob in a sunlit kitchen; the oil lands without splashing and spreads into a smooth, glossy puddle.",
                  "zh": "阳光照进厨房，倾斜的油瓶把一股细细的金色食用油倒进电磁炉上的深色不粘平底锅；油落下时没有飞溅，"
                        "在锅底铺开成一片光滑发亮的油面。"},
        "quantitative": {"en": "Cooking oil (915 kg/m³, kinematic viscosity 1.4e-4 m²/s, surface tension 0.032 N/m) leaves the lower rim "
                               "of the bottle's mouth at 10 mL/s from 0.29 s on, 24.5 cm above the pan floor, under 9.81 m/s² gravity. "
                               "The stream thins from 4.6 mm to about 2.4 mm as it falls and lands at 2.3 m/s at 0.46 s; by 4 s 36.5 mL has "
                               "poured and the puddle is about 11 cm across and 4 mm deep, with no splash.",
                         "zh": "食用油（密度 915 kg/m³，运动黏度 1.4e-4 m²/s，表面张力 0.032 N/m）从 0.29 s 开始以 10 mL/s 从油瓶瓶口下沿"
                               "流出，出口离锅底 24.5 cm，重力 9.81 m/s²。油柱下落时从 4.6 mm 变细到约 2.4 mm，0.46 s 以 2.3 m/s 落到锅底；"
                               "到 4 s 共倒出 36.5 mL，油面直径约 11 cm、深约 4 mm，没有飞溅。"}},
    "physics": edit_vocab.BASELINE_PHYSICS,
}
EDITS = (
    {"case_id": "edit_increase_flow", "kind": "edit", "edit_dsl": "SET bottle.flow_rate TIMES 4",
     "edit_summary": "The bottle pours four times as much, 40 mL/s: a thicker sheet over the rim (a 7.3 mm stream leaving at 0.96 m/s "
                     "instead of 4.6 mm at 0.67 m/s). By 4 s 146 mL has poured instead of 36.5 mL and the puddle has spread to about "
                     "19 cm across, most of the pan floor, instead of 11 cm."},
    {"case_id": "edit_decrease_flow", "kind": "edit", "edit_dsl": "SET bottle.flow_rate TIMES 0.2",
     "edit_summary": "The bottle pours a fifth as much, 2 mL/s: a hair-thin stream that falls almost straight down. By 4 s 7.3 mL has "
                     "poured instead of 36.5 mL and the puddle is about 5.5 cm across instead of 11 cm."},
    {"case_id": "edit_increase_at_2s", "kind": "edit", "edit_dsl": "SET bottle.flow_rate TIMES 2.8 AT FRAME 49",
     "edit_summary": "Identical to the source until 2.0 s (frame 49); then the pour rises from 10 to 28 mL/s within 0.2 s: the stream "
                     "thickens and its landing point moves towards the far side of the puddle. By 4 s 70 mL has poured instead of "
                     "36.5 mL and the puddle is about 14 cm across instead of 11 cm."},
    {"case_id": "edit_decrease_at_1s", "kind": "edit", "edit_dsl": "SET bottle.flow_rate TIMES 0.2 AT FRAME 25",
     "edit_summary": "Identical to the source until 1.0 s (frame 25); then the pour falls from 10 to 2 mL/s within 0.2 s: the stream thins "
                     "to a thread without breaking and the puddle barely grows. By 4 s 13.8 mL has poured instead of 36.5 mL and the "
                     "puddle is about 8 cm across instead of 11 cm."},
    {"case_id": "edit_increase_viscosity", "kind": "edit", "edit_dsl": "SET oil.kinematic_viscosity TIMES 100",
     "edit_summary": "The oil is a hundred times as viscous (1.4e-2 m²/s, like honey): the stream buckles where it lands and coils into a "
                     "growing pile instead of spreading. By 4 s the same 36.5 mL stands as a glossy mound about 6.5 cm across and 3-4 cm "
                     "tall instead of a puddle 11 cm across and 4 mm deep."},
)
RENDER = {"engine": "Cycles", "samples": SAMPLES, "denoising": True, "motion_blur_shutter_frames": 0.5,
          "resolution": [1280, 720], "fps": edit_vocab.FPS, "template": "assets/scenes/cooking_oil_pan/scene_template.blend",
          "look": {"oil": "clear dielectric, IOR 1.47, roughness 0.03, volume absorption (8, 40, 220) /m",
                   "puddle": "volume-conserving height field over the pan (smoothed 1.2 mm), pressed 0.15 mm into the pan",
                   "stream": "thread rebuilt from the particle volume per height, averaged over 6 ms of fall; joins the puddle in one closed surface",
                   "viscous_rope": "from 1e-3 m²/s: direct pysplashsurf surface, which keeps the coils",
                   "lighting": "daylight from the open side of the room: sky, low sun (azimuth 250°, elevation 28°), weak under-cabinet strip",
                   "materials": "pan interior dark-grey semi-gloss PTFE, brushed steel utensils, honed quartz counter"}}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite-root", type=Path, required=True)
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
    source = {**SOURCE, "at_frame": None,
              "prompts_document": {"schema_version": 1, "case_id": SOURCE_CASE_ID, "kind": "source", "prompts": SOURCE["description"]}}
    edits = []
    for case in EDITS:
        edit = dsl.parse(case["edit_dsl"], vocab)
        document = {"schema_version": 2, "case_id": case["case_id"], "source_case_id": SOURCE_CASE_ID,
                    "edit_dsl": case["edit_dsl"], "edit_summary": case["edit_summary"],
                    "applies_from_frame": dsl.starts_at_frame(edit),
                    "physics_diff": {f"{edit.property_name} ({edit.object_id})": {"from": dsl.baseline_value_for(edit, vocab), "to": edit.to_value},
                                     "timing": dsl.timing_diff(edit, vocab)},
                    "prompts": dsl.make_prompts(edit, vocab)}
        edits.append({**case, "at_frame": edit.at_frame if dsl.is_timed(edit) else None,
                      "physics": {**SOURCE["physics"], **dsl.to_physics_override(edit, vocab)}, "prompts_document": document})
    return [source] + edits


def frames_done(directory, frames):
    return [f for f in frames if not (directory / f"frame_{f:04d}.png").exists()]


def check_run(args_log, flags):
    """the finished run was made with the settings this case asks for (runs may have been resumed from checkpoints)"""
    wanted, key = {}, None
    for flag in flags:
        if flag.startswith("--") and not flag[2:3].isdigit():
            key = flag[2:].replace("-", "_"); wanted[key] = []
        else:
            wanted[key].append(flag)
    for key, values in wanted.items():
        have = args_log[key]
        if key == "schedule":
            have = [tuple(map(float, item.split(":"))) for item in have]
            values = [tuple(map(float, item.split(":"))) for item in values]
            assert all(math.isclose(a, b, rel_tol=1e-9) for x, y in zip(have, values) for a, b in zip(x, y)) and len(have) == len(values), key
        else:
            have = have if isinstance(have, list) else [have]
            assert all(math.isclose(a, float(b), rel_tol=1e-6, abs_tol=1e-9) for a, b in zip(have, values)) and len(have) == len(values), (key, have, values)


def build_case(args, plan, runs, cases, published):
    work = runs / plan["case_id"]
    work.mkdir(parents=True, exist_ok=True)
    source_work = runs / SOURCE_CASE_ID
    timings_path = work / "timings.json"
    timings = json.loads(timings_path.read_text()) if timings_path.exists() else {}
    at = plan["at_frame"]
    flags = edit_vocab.sim_args(plan["physics"], at)
    frames_dir = work / "frames"
    log_path = work / "sim_log.json"
    if not log_path.exists() or len(json.loads(log_path.read_text())["frames"]) < FRAMES:
        extra = ["--resume-from", source_work, "--resume-frame", at - 1] if at else []
        run([args.python, "-u", HERE / f"simulate_{NAME}.py", "--out", work, "--frames", FRAMES, "--fps", edit_vocab.FPS,
             *flags, *extra], work / "sim.log")
    wanted = list(range(at, FRAMES + 1)) if at else list(range(1, FRAMES + 1))
    surface_log = work / "surface_log.json"
    if not surface_log.exists() or not set(wanted) <= set(json.loads(surface_log.read_text())["frames"]):
        rope = ["--rope"] if edit_vocab.rope(plan["physics"]) else []
        timings["surface_sec"] = run([args.python, HERE / f"surface_{NAME}.py", work, *rope, *wanted], work / "surface.log")
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
                       "--run", work, "--out-dir", frames_dir, "--samples", SAMPLES, "--frames", *missing], work / "render.log")
        timings["render_sec"] = timings.get("render_sec", 0.0) + seconds
        write_json(timings_path, timings)
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
    log = json.loads(log_path.read_text())
    a = log["args"]
    check_run(a, flags)
    rows = log["frames"]; last = rows[-1]
    record.update({"status": "completed",
                   "outputs": {"video": str(published / "cases" / plan["case_id"] / "video.mp4"),
                               "prompts": str(published / "cases" / plan["case_id"] / "prompts.json")},
                   "video_sha256": digest(case / "video.mp4"), "physics": plan["physics"], "render": RENDER,
                   "elapsed_sec": round(log["build_sec"] + log["sim_sec"] + timings.get("surface_sec", 0.0) + timings.get("render_sec", 0.0), 1),
                   "numerics": {k: v for k, v in a.items() if k not in ("out", "pan", "resume_from", "resume_frame")},
                   "simulation": {"frames": FRAMES, "simulated": True,
                                  "oil_particles": int(round(last["oil_ml"] / (log["particle_volume_m3"] * 1e6))),
                                  "ghost_particles": log["n_ghosts"], "exit_speed_m_s": round(log["exit_speed_m_s"], 4),
                                  "wall_drag_per_s": round(log.get("wall_drag_per_s", 0.0), 1),
                                  "oil_poured_ml": last["oil_ml"], "oil_near_pan_ml": last["puddle_ml"],
                                  "puddle_r95_mm": last["puddle_r95_mm"], "peak_particle_speed_m_s": max(r["max_speed"] for r in rows),
                                  "surface": "rope" if edit_vocab.rope(plan["physics"]) else "height field and thread",
                                  "continued_from_source_frame": at - 1 if at else None}})
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
        "description": "Cooking oil is poured from a tilted bottle into a dark nonstick frying pan on an induction hob in a sunlit modern kitchen.",
        "coupling": "Genesis 1.4.3 DFSPH at 0.5 mm; the pan interior is a static ghost-particle boundary that carries its own pressure "
                    "(split density solve), no-slip with laminar wall shear; implicit viscosity; Akinci surface tension scaled to oil "
                    "(0.032 N/m); the oil enters through an inflow buffer at the bottle's lower rim that holds the stream back as the "
                    "oil in the neck does",
        "baseline_physics": edit_vocab.BASELINE_PHYSICS,
        "total_frames": FRAMES, "resolution": RENDER["resolution"], "fps": edit_vocab.FPS, "duration_sec": edit_vocab.DURATION_SEC,
        "samples": SAMPLES, "render": RENDER,
        "source_case_id": SOURCE_CASE_ID, "selected_base_video_sha256": source["video_sha256"] if source else None,
        "geometry": {"pan": "geometry/pan_profile.npz (interior surface of revolution, flat floor to r = 9 cm, 30 cm rim)",
                     "pan_origin_world_m": [1.1, 3.405, 1.18233], "exit_m": edit_vocab.rim_exit(edit_vocab.JET_RADIUS_M),
                     "exit_direction": [0.035, 0.005, -0.15], "jet_radius_m": edit_vocab.JET_RADIUS_M, "flow_change_ramp_sec": edit_vocab.RAMP_SEC},
        "assets": {"template": "assets/scenes/cooking_oil_pan/scene_template.blend (packed textures; modern kitchen, hob, pan and bottle; no fluid cache)"},
        "source": source,
        "edits": [previous[e["case_id"]] for e in EDITS if e["case_id"] in previous]}
    write_json(manifest_path, manifest)
    print(f"PCVE_GENESIS_SUITE {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
