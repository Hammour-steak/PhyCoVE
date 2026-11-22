"""Assemble a gym_landing_mat suite in the current PCVE formats from finalized renders.

    python3 scripts/rigid_elastic/gym_landing_mat/tools/publish_suite.py         --renders renders/gym_landing_mat/<render> --suite <new suite folder>/pcve_gym_landing_mat_suite

The suite folder must not exist. Needs numpy (ground truth). For every case it copies the finalized video and
the render's native metadata, writes ground_truth_transforms.json from the native cache
(tools/export_ground_truth.py, pcve_ground_truth/1), video_validation.json (pcve_video_validation/1, full
ffprobe/ffmpeg decode),
prompts.json (pcve_prompts/1 from the builder catalog) and provenance.json (pcve_provenance/1), then
suite_manifest.json (pcve_suite/1), inputs/native_input_locations.json and README.txt. Prompts of a
published suite are updated with `build_pcve_gym_landing_mat.py --export-prompts`.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(CASE_DIR), str(CASE_DIR.parents[1])]

from pcve_edit_catalog import FORMAT_VERSION, _applies_from_frame, _fps, load_catalog  # noqa: E402
from scene_inputs import ASSETS, CASES, accepted_case, reference_main  # noqa: E402
from tools.export_ground_truth import ground_truth, save  # noqa: E402
from pcve_ground_truth import write as write_ground_truth  # noqa: E402

REPO = CASE_DIR.parents[2]
SCENE = "gym_landing_mat"
BUILDER = CASE_DIR / f"build_pcve_{SCENE}.py"
CATALOG = {case: "source" if case == "source" else "edit_" + case for case in CASES}
METADATA = ("environment_manifest.json", "ground_truth_transforms.json", "prompts.json", "realism_provenance.json",
            "render_report.json", "simulation_config.json", "simulation_report.json", "source_scene_specs.json",
            "video_probe.json", "scenario_metadata.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def validate(video: Path) -> dict:
    probe = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-count_frames", "-show_entries",
         "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames:format=duration",
         "-of", "json", str(video)]))
    decode = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], capture_output=True, text=True)
    stream = probe["streams"][0]
    frames = int(stream["nb_read_frames"])
    duration = float(probe["format"]["duration"])
    ok = ([stream["width"], stream["height"]] == [1280, 720] and stream["avg_frame_rate"] == "24/1"
          and frames == 96 and abs(duration - 4.0) < 1e-6 and decode.returncode == 0 and not decode.stderr.strip())
    if not ok:
        raise RuntimeError(f"Video contract failed: {video}: {probe} {decode.stderr[-300:]}")
    return {"technical_decode_verified": True, "pcve_spec_compliant": True, "resolution": [1280, 720],
            "fps": "24/1", "duration_sec": 4.0, "frames": 96, "full_decode": True, "sha256": sha256(video),
            "probe": probe}


def relative(path: Path) -> str:
    path = Path(path).resolve()
    return path.relative_to(REPO.resolve()).as_posix() if path.is_relative_to(REPO.resolve()) else path.as_posix()


def prompt_record(record: dict, fps: float) -> dict:
    """The pcve_prompts/1 file that `--export-prompts` keeps unchanged for this catalog record."""
    item = {"schema_version": 1, "format_version": FORMAT_VERSION, "scene": SCENE, "case_id": record["catalog_case_id"],
            "kind": record["kind"], "source_case_id": "source", "availability": "available",
            "prompts": record["prompts"], "edit_dsl": None, "object_id": None, "applies_from_frame": None,
            "application_time_sec": None, "physics_override": {}, "physics_diff": {},
            "prompt_provenance": {"origin": "generated:" + relative(BUILDER), "text_modified": False}}
    if record["kind"] == "edit":
        frame = _applies_from_frame(record)
        item.update(edit_dsl=record["edit_dsl"], applies_from_frame=frame, application_time_sec=(frame - 1) / fps,
                    physics_override=record["physics_override"], physics_diff=record["physics_diff"])
    return item


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--renders", type=Path, required=True, help="folder with <case>/render from tools/finalize.py")
    parser.add_argument("--suite", type=Path, required=True)
    args = parser.parse_args()
    renders, suite = args.renders.resolve(), args.suite.resolve()
    if suite.exists():
        raise FileExistsError(f"{suite} exists; choose a new suite folder")
    catalog = load_catalog(BUILDER)
    declared = {r["case_id"]: r for r in [catalog["source"], *catalog["edits"].values()]}
    fps = _fps()
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    rows = []
    for case in CASES:
        render = renders / case / "render"
        cid = CATALOG[case]
        target = suite / "cases" / cid
        (target / "native_metadata").mkdir(parents=True)
        shutil.copy2(render / "video.mp4", target / "video.mp4")
        for name in METADATA:
            src = render / name
            if src.is_file():
                shutil.copy2(src, target / "native_metadata" / name)
        simulation = accepted_case(case) / "simulation"
        write_ground_truth(target / "ground_truth_transforms.json", ground_truth(simulation, reference_main(case), case))
        check = validate(target / "video.mp4")
        save(target / "video_validation.json", {
            "schema_version": 1, "format_version": "pcve_video_validation/1", "scene": SCENE, "case_id": cid,
            "video": "video.mp4", **{k: check[k] for k in ("resolution", "fps", "duration_sec", "frames", "sha256")},
            "technical_probe_verified": True, "full_decode_verified": check["full_decode"], "content_unchanged": False,
            "visual_or_physics_acceptance": "new render; visual review pending", "native_validation": check})
        prompts = prompt_record(declared[case], fps)
        save(target / "prompts.json", prompts)
        report = json.loads((render / "render_report.json").read_text(encoding="utf-8"))
        save(target / "provenance.json", {
            "schema_version": 1, "format_version": "pcve_provenance/1", "scene": SCENE, "case_id": cid,
            "kind": prompts["kind"], "native_case_id": case, "video_sha256": check["sha256"], "created_at": now,
            "render_dir": relative(render), "native_metadata": f"cases/{cid}/native_metadata",
            "native_cache": {"file": relative(simulation / "cache.npz"), "sha256": report["physics_cache_sha256"]},
            "render": {"look": f"scripts/rigid_elastic/{SCENE}/appearance/realism.py", "samples": report["samples"],
                       "max_surface_replay_error_m": report["max_surface_replay_error_m"],
                       "fixed_environment_and_camera_identical": report["fixed_environment_and_camera_identical"]},
            "ground_truth": {"file": f"cases/{cid}/ground_truth_transforms.json",
                             "generator": f"scripts/rigid_elastic/{SCENE}/tools/export_ground_truth.py"}})
        rows.append({
            "case_id": cid, "native_case_id": case, "kind": prompts["kind"], "source_case_id": "source",
            "case_dir": f"cases/{cid}", "status": "rendered_pending_review", "availability": "video_present",
            "video": f"cases/{cid}/video.mp4", "video_sha256": check["sha256"],
            "media": {k: check[k] for k in ("resolution", "fps", "duration_sec", "frames", "sha256")},
            **{k: prompts[k] for k in ("prompts", "edit_dsl", "object_id", "applies_from_frame", "application_time_sec",
                                       "physics_override", "physics_diff")}})
        print("case", cid, check["sha256"][:12], flush=True)
    (suite / "inputs").mkdir()
    save(suite / "inputs" / "native_input_locations.json", {
        "scene": SCENE, "kind": "native_input_locations",
        "render_directories": [relative(renders / c / "render") for c in CASES],
        "native_simulations": {c: relative(accepted_case(c) / "simulation") for c in CASES},
        "packed_scenes": {c: relative(ASSETS / "packed" / f"{c}.blend") for c in CASES},
        "scene_code": relative(CASE_DIR)})
    (suite / "README.txt").write_text(
        f"PCVE suite: {SCENE}\nSource: cases/source/video.mp4; edits: cases/edit_*/video.mp4 ({len(rows) - 1}).\n"
        "Per case: video.mp4, prompts.json, provenance.json, video_validation.json, native_metadata/, "
        "ground_truth_transforms.json.\nIndex: suite_manifest.json. Scene code: scripts/rigid_elastic/gym_landing_mat.\n",
        encoding="utf-8")
    save(suite / "suite_manifest.json", {
        "schema_version": 5, "format_version": "pcve_suite/1",
        "layout": "cases/<case_id>/{video.mp4,prompts.json,provenance.json,video_validation.json}",
        "scene": SCENE, "title": SCENE, "suite_name": f"pcve_{SCENE}_suite", "interaction_category": "rigid_elastic",
        "suite_path": relative(suite), "source_count": 1, "edit_count": len(rows) - 1, "status": "rendered_pending_review",
        "source": rows[0], "edits": rows[1:],
        "metadata": {"scene_id": SCENE, "created_at": now, "look": "appearance/realism.py", "storage_type": "physical_files",
                     "render_outputs": relative(renders),
                     "physics": "accepted native solves (scene_manifest.json accepted_native_delivery); only the appearance is rendered",
                     "inputs": [{"role": "native_input_locations", "path": "inputs/native_input_locations.json"}]}})
    print("suite", suite)


if __name__ == "__main__":
    main()
