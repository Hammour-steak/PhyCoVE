"""Public entry point: a toy car dropped onto an inflatable float in a bathtub (Genesis 1.4.3 DFSPH, 6 mm) and its edits.

A 2 kg silver toy sports car falls 0.55 m onto a 0.15 kg float on 31 cm of water in a freestanding bathtub, in a bathroom in
daylight. Per case: simulate (simulate_*), build the water surface (surface_*) and render the bathroom (render_*). The water
and the float start from an accepted settled state (assets/settled/, made by `simulate_* relax`); without it the builder
settles them itself. Each step is skipped when its output exists and only missing frames are rendered, so an interrupted
build resumes. An edit that lands at frame F continues the source's frame-F state and keeps the source's frames before F.
Each case keeps video.mp4 and its bilingual prompts.json in <suite-root>/cases/<case_id>/, intermediates go to
<suite-root>/runs/<case_id>/, and the configuration and run summaries to <suite-root>/suite_manifest.json.
    CUDA_VISIBLE_DEVICES=<gpu> <genesis python> build_pcve_toy_car_float_bathtub.py --suite-root SUITE --blender BLENDER
"""
from __future__ import annotations
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import scene_asset
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

NAME = "toy_car_float_bathtub"
SUITE_NAME = f"pcve_{NAME}_suite"
SOURCE_CASE_ID = "toy_car_float_bathtub_baseline"
FRAMES = edit_vocab.VOCAB.total_frames
FPS = edit_vocab.FPS
SAMPLES = 256
# the accepted run: 6 mm particles, 10 steps of 8 substeps per frame (0.4 particle sizes per substep at 4.6 m/s)
SIM = ["--particle", "0.006", "--substeps", "8", "--steps-per-frame", "10", "--surface-tension", "0.02", "--frames", str(FRAMES)]
SETTLE = ["--particle", "0.006", "--substeps", "8", "--steps-per-frame", "5", "--surface-tension", "0.02", "--relax-frames", "30"]
SETTLED = {True: scene_asset(HERE, "assets/settled/settled.npz"), False: scene_asset(HERE, "assets/settled/settled_no_float.npz")}
SOURCE = {
    "case_id": SOURCE_CASE_ID, "kind": "source", "interaction_category": "rigid_fluid",
    "description": {
        "vague": {"en": "A toy car drops onto an inflatable float in a bathtub; the float is pushed down into the water, bobs back up "
                        "and rocks, and keeps the car afloat.",
                  "zh": "一辆玩具小车落到浴缸里的充气浮垫上，浮垫被压进水里、又弹回来来回摇晃，一直托着小车漂在水面上。"},
        "quantitative": {"en": "A 23 cm, 2.0 kg silver toy sports car is dropped from 0.55 m above a 0.15 kg purple inflatable float "
                               "(46 × 28 cm) floating on 31 cm of water (998 kg/m³) in a bathtub. It lands at 3.3 m/s about 0.35 s in "
                               "and pushes the float about 6 cm into the water; the float bobs back up with a period of about 0.65 s "
                               "and rocks by up to 18°, and it still carries the car at 4.0 s.",
                         "zh": "一辆长 23 cm、重 2.0 kg 的银色玩具跑车从浮垫上方 0.55 m 处落下，砸在浴缸里漂浮的 0.15 kg 紫色充气浮垫"
                               "（46 × 28 cm）上，水深 31 cm、密度 998 kg/m³。小车约在 0.35 s 以 3.3 m/s 落到浮垫上，把浮垫压进水里约 6 cm；"
                               "浮垫随后以约 0.65 s 的周期上下起伏、最多倾斜 18°，到 4.0 s 仍托着小车。"}},
    "physics": edit_vocab.BASELINE_PHYSICS,
}
EDITS = (
    {"case_id": "edit_no_float", "kind": "edit", "edit_dsl": "DELETE float",
     "edit_summary": "Without the float the 2 kg car falls straight into the water at 3.3 m/s, throws a splash more than a metre high "
                     "and reaches the tub floor about 0.25 s after entering the water, where it stays upright, instead of riding "
                     "on the float."},
    {"case_id": "edit_heavy_car", "kind": "edit", "edit_dsl": "SET toy_car.mass TIMES 4",
     "edit_summary": "At 8 kg the car pushes the float about 20 cm under the water, slides off it and sinks to the tub floor by about "
                     "0.9 s, where it stays upright; the released float shoots up out of the water, tumbles and settles floating "
                     "again, empty."},
    {"case_id": "edit_low_density", "kind": "edit", "edit_dsl": "SET water.density TIMES 0.1",
     "edit_summary": "With water a tenth as dense (99.8 kg/m³) the float has already sunk about 2 cm deeper when the car lands; the "
                     "car drives it about 25 cm down with a much bigger splash, slides off and stays on the tub floor, and the float, "
                     "still lighter than this water, rises back to the surface without the car."},
    {"case_id": "edit_density_at_2s", "kind": "edit", "edit_dsl": "SET water.density TIMES 0.1 AT FRAME 49",
     "edit_summary": "Identical to the source until 2.0 s (frame 49); then the water becomes a tenth as dense: float and car sink "
                     "together about 22 cm within 0.6 s, the car tips off and comes to rest upside down on the tub floor, and the "
                     "float rises back to the surface without it."},
    {"case_id": "edit_no_car", "kind": "edit", "edit_dsl": "DELETE toy_car",
     "edit_summary": "Without the car nothing lands: the float rides quietly at the surface and the water stays calm."},
)
RENDER = {"engine": "Cycles", "samples": SAMPLES, "denoising": True, "motion_blur_shutter_frames": 0.5,
          "resolution": [1280, 720], "fps": FPS, "camera": {"position_m": [-1.05, 0.80, 1.62], "target_m": [0.02, -0.04, 0.56], "lens_mm": 32},
          "look": {"water": "clear dielectric, IOR 1.333, absorption colour (0.82, 0.97, 0.99) at density 1/m; light bouncing off the "
                            "ceramic passes the water surface (refractive caustic paths on)",
                   "surface": "height field of the top particle layer (sigma 2.4 spacings in still water, 1.3 in fast water, 3-frame "
                              "average), meniscus on ceramic and float, clusters joined in one implicit field, lone fast particles as "
                              "droplets (clear glass spheres without the water's absorption); light lines on the floor from the "
                              "height field's refraction of the sun",
                   "wet": "where the water has been: glossier, slightly darker ceramic with an uneven edge and flat bead highlights; "
                          "beads on the float where particles touched it; wet paint on the car there (slightly darker, full "
                          "clear coat, sparse beads in the coat normal)",
                   "lighting": "virtual window at y = -1 m: soft area light and a sun beam (area light, 16 deg spread); AgX Medium "
                               "High Contrast, exposure -2.3",
                   "room": "Sketchfab bathroom, natural_finish ceramic, stone and wood (appearance/bathroom_*.py), satin pop-up drain"}}


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
              "prompts_document": {"schema_version": 2, "case_id": SOURCE_CASE_ID, "kind": "source",
                                   "interaction_category": "rigid_fluid", "prompts": SOURCE["description"]}}
    edits = []
    for case in EDITS:
        edit = dsl.parse(case["edit_dsl"], vocab)
        if isinstance(edit, dsl.DeleteEdit):
            physical_diff = {f"presence ({edit.object_id})": {"from": True, "to": False}}
        else:
            physical_diff = {f"{edit.property_name} ({edit.object_id})": {"from": dsl.baseline_value_for(edit, vocab), "to": edit.to_value}}
        document = {"schema_version": 2, "case_id": case["case_id"], "source_case_id": SOURCE_CASE_ID,
                    "edit_dsl": case["edit_dsl"], "edit_summary": case["edit_summary"],
                    "applies_from_frame": dsl.starts_at_frame(edit),
                    "physics_diff": {**physical_diff, "timing": dsl.timing_diff(edit, vocab)},
                    "prompts": dsl.make_prompts(edit, vocab)}
        edits.append({**case, "at_frame": edit.at_frame if dsl.is_timed(edit) else None,
                      "physics": {**SOURCE["physics"], **dsl.to_physics_override(edit, vocab)}, "prompts_document": document})
    return [source] + edits


def missing_frames(directory, frames):
    return [f for f in frames if not (directory / f"frame_{f:04d}.png").exists()]


def check_run(args_log, physics, at):
    """the finished run was made with the physics this case asks for"""
    want = {"car_mass": physics["car_mass_kg"], "float_mass": physics["float_mass_kg"],
            "no_car": not physics["car_presence"][0], "no_float": not edit_vocab.has_float(physics)}
    rho = physics["water_density_kg_m3"]
    want["density_after"] = None if rho == edit_vocab.BASELINE_PHYSICS["water_density_kg_m3"] else rho
    for key, value in want.items():
        have = args_log[key]
        ok = (have is None and value is None) or (isinstance(value, bool) and have == value) or \
             (value is not None and have is not None and not isinstance(value, bool) and math.isclose(float(have), float(value), rel_tol=1e-6))
        assert ok, (key, have, value)
    if want["density_after"] is not None:
        assert math.isclose(args_log["density_time"], (at - 1) / FPS if at else 0.0, abs_tol=1e-9), args_log["density_time"]


def settled_state(args, runs, with_float):
    """the accepted settled water (and float) of assets/settled/, or one made here"""
    if SETTLED[with_float].exists():
        return SETTLED[with_float]
    work = runs / ("settle" if with_float else "settle_no_float")
    if not (work / "settled.npz").exists():
        shutil.rmtree(work, ignore_errors=True)
        run([args.python, "-u", HERE / f"simulate_{NAME}.py", "relax", "--out", work, *SETTLE, *([] if with_float else ["--no-float"])],
            runs / f"{work.name}.log")
    return work / "settled.npz"


def build_case(args, plan, runs, cases, published, checkpoints):
    work = runs / plan["case_id"]
    work.mkdir(parents=True, exist_ok=True)
    source_work = runs / SOURCE_CASE_ID
    timings_path = work / "timings.json"
    timings = json.loads(timings_path.read_text()) if timings_path.exists() else {}
    at = plan["at_frame"]
    physics = plan["physics"]
    flags = edit_vocab.sim_args(physics, at)
    log_path = work / "sim_log.json"
    if not log_path.exists() or len(json.loads(log_path.read_text())["frames"]) < FRAMES:
        if at:
            extra = ["--resume-from", source_work, "--resume-frame", at]
        else:
            extra = ["--settled", settled_state(args, runs, edit_vocab.has_float(physics))]
            if plan["kind"] == "source" and checkpoints:
                extra += ["--checkpoint-frames", *checkpoints]
        run([args.python, "-u", HERE / f"simulate_{NAME}.py", "run", "--out", work, *SIM, *flags, *extra], work / "sim.log")
    surfaces = work / "surfaces"
    report = surfaces / "surface_report.json"
    if not report.exists() or len(json.loads(report.read_text())) < FRAMES:
        # all frames even for a timed edit: the wet marks follow the water's history from frame 1
        timings["surface_sec"] = run([args.python, HERE / f"surface_{NAME}.py", "--run", work, "--out", surfaces,
                                      "--frames", f"1-{FRAMES}", "--sigma-caustic", "0.006"], work / "surface.log")
        write_json(timings_path, timings)
    frames_dir = work / "frames"
    frames_dir.mkdir(exist_ok=True)
    wanted = list(range(at, FRAMES + 1)) if at else list(range(1, FRAMES + 1))
    if at:                                     # frames before the edit are the source's
        for f in range(1, at):
            target = frames_dir / f"frame_{f:04d}.png"
            if not target.exists():
                shutil.copy2(source_work / "frames" / target.name, target)
    missing = missing_frames(frames_dir, wanted)
    if missing:
        seconds = run([args.blender, "-b", "--python-exit-code", "1", "--python", HERE / f"render_{NAME}.py", "--",
                       "--run", work, "--mesh-dir", surfaces, "--out", frames_dir, "--samples", SAMPLES, "--frames", *missing],
                      work / "render.log")
        timings["render_sec"] = timings.get("render_sec", 0.0) + seconds
        write_json(timings_path, timings)
    missing_all = missing_frames(frames_dir, range(1, FRAMES + 1))
    assert not missing_all, f"{plan['case_id']}: frames missing {missing_all[:8]}"
    video = work / "video.mp4"
    if not video.exists() or video.stat().st_mtime < max((frames_dir / f"frame_{f:04d}.png").stat().st_mtime for f in range(1, FRAMES + 1)):
        run(["ffmpeg", "-v", "error", "-y", "-framerate", FPS, "-i", frames_dir / "frame_%04d.png", "-frames:v", FRAMES,
             "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", video], work / "encode.log")
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", str(video)], capture_output=True, text=True).stdout.strip()
    assert int(probe) == FRAMES, f"{video}: {probe} frames"
    case = cases / plan["case_id"]
    case.mkdir(parents=True, exist_ok=True)
    destination = case / "video.mp4"
    # A cleaned suite may share one inode between its run and published video.
    if not destination.exists() or not video.samefile(destination):
        shutil.copy2(video, destination)
    write_json(case / "prompts.json", plan["prompts_document"])

    record = {key: plan[key] for key in ("case_id", "kind", "interaction_category", "description") if key in plan}
    if plan["kind"] == "edit":
        document = plan["prompts_document"]
        record = {"case_id": plan["case_id"], "kind": "edit",
                  **{key: document[key] for key in ("source_case_id", "edit_dsl", "edit_summary", "applies_from_frame", "physics_diff", "prompts")}}
    log = json.loads(log_path.read_text())
    a = log["args"]
    check_run(a, physics, at)
    rows = log["frames"]
    last = rows[-1]
    end = {"level_m": last["level"], "water_lost_particles": last["lost"]}
    if "float_z" in last:
        end.update(float_centre_z_m=last["float_z"], float_tilt_deg=last["tilt"])
    if "car_z" in last:
        end.update(car_centre_z_m=last["car_z"])
    record.update({"status": "completed",
                   "outputs": {"video": str(published / "cases" / plan["case_id"] / "video.mp4"),
                               "prompts": str(published / "cases" / plan["case_id"] / "prompts.json")},
                   "video_sha256": digest(case / "video.mp4"), "physics": physics, "render": RENDER,
                   # a timed edit's log starts with the source's rows, whose time the source already counts
                   "elapsed_sec": round(sum(r.get("sec", 0.0) for r in rows[at - 1 if at else 0:]) + log.get("build_sec", 0.0)
                                        + timings.get("surface_sec", 0.0) + timings.get("render_sec", 0.0), 1),
                   "numerics": {k: v for k, v in a.items() if k not in ("out", "settled", "resume_from", "debug_from")},
                   "simulation": {"frames": FRAMES, "simulated": True, "water_particles": log["n_fluid"], "ghost_particles": log["n_ghost"],
                                  "peak_particle_speed_m_s": max(r["vmax"] for r in rows),
                                  "max_float_tilt_deg": max(r.get("tilt", 0.0) for r in rows), "at_end": end,
                                  "continued_from_source_frame": at}})
    return record


def main():
    args = parse_args()
    suite = args.suite_root.expanduser().resolve()
    published = args.publish_root or suite
    runs, cases = suite / "runs", suite / "cases"
    runs.mkdir(parents=True, exist_ok=True)
    all_plans = plans()
    checkpoints = sorted({p["at_frame"] for p in all_plans if p["at_frame"]})
    records = {plan["case_id"]: build_case(args, plan, runs, cases, published, checkpoints)
               for plan in all_plans if plan["case_id"] in args.cases}
    manifest_path = suite / "suite_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    previous = {entry["case_id"]: entry for entry in [manifest.get("source")] + manifest.get("edits", []) if entry}
    previous.update(records)
    source = previous.get(SOURCE_CASE_ID)
    manifest = {
        "schema_version": 3, "suite_name": SUITE_NAME, "interaction_category": "rigid_fluid",
        "description": "A 2 kg silver toy sports car drops onto a 0.15 kg inflatable float in a bathtub of water and rides it; Genesis "
                       "DFSPH with two-way coupled rigid bodies.",
        "coupling": "Genesis 1.4.3 DFSPH at 6 mm (1.38 M particles), stale second gravity removed; the bathtub, float and car are "
                    "ghost-particle shells that carry their own pressure (split density solve, warm-started momentum part); the "
                    "pressure iterations also move the bodies (strong coupling), since the 0.15 kg float holds ~11 kg of added mass; "
                    "the rigid solver holds the float at 1 kg in contacts, its weight stays 0.15 kg",
        "baseline_physics": edit_vocab.BASELINE_PHYSICS,
        "total_frames": FRAMES, "resolution": RENDER["resolution"], "fps": FPS, "duration_sec": edit_vocab.DURATION_SEC,
        "samples": SAMPLES, "render": RENDER,
        "source_case_id": SOURCE_CASE_ID, "selected_base_video_sha256": source["video_sha256"] if source else None,
        "geometry": {"bathtub": "geometry/tub_shell.npz (rings of the fitted ceramic shell, appearance/bathroom_finish.py): the "
                                "simulated interior is the rendered one",
                     "float": "assets/procedural_float/ (tools/make_float.py): 46 x 28 cm, 5.06 L, six welded tubes, wavy seam",
                     "car": "assets/amg_vision_gt/collision.obj, CoACD convex decomposition",
                     "float_centre_from_tub_centre_m": [0.06, -0.22], "car_release_from_float_centre_m": [-0.02, 0.035],
                     "car_release_height_m": 1.0522, "rigid_floor_clearance_m": 0.012},
        "assets": {"settled": "assets/settled/settled.npz and settled_no_float.npz: the accepted settled water (and float)",
                   "bathroom": "assets/sketchfab_bathroom/bathroom.glb", "car": "assets/amg_vision_gt/"},
        "source": source,
        "edits": [previous[e["case_id"]] for e in EDITS if e["case_id"] in previous]}
    write_json(manifest_path, manifest)
    print(f"PCVE_GENESIS_SUITE {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
