"""Assemble a suite from per-case render outputs in the current PCVE suite format.

    python3 scripts/rigid_elastic/metro_security_bag_curtain/tools/publish_suite.py --renders DIR \
        [--native DIR] [--timed-native DIR] [--suite DIR] [--look NAME]

<renders>/<case>/ is the output folder of render_metro_security_bag_curtain.py for every native case of
the builder catalog (video.mp4, render_report.json, encoding_receipt.json, replay_audit.json and the
audits). Each render must be tied to its native states: the whole-clip cases to <native>/<case>/states.npz
(default: the accepted native states in assets/), a timed edit to <timed-native>/<case>/states.npz (the
merged output of simulate_metro_security_bag_curtain.py --case <timed case>; default: the published
suite's inputs/native_timed/), which is copied into the
suite's inputs/native_timed/<case>/. Per case the suite gets video.mp4, native_metadata/ (the render JSON
files; for a timed edit also its simulation_config.json and simulation_report.json), prompts.json
(pcve_prompts/1, from PCVE_SOURCE / PCVE_EDITS of build_pcve_metro_security_bag_curtain.py),
provenance.json (pcve_provenance/1), video_validation.json (pcve_video_validation/1) and
ground_truth_transforms.json (pcve_ground_truth/1, tools/export_ground_truth.py); the suite gets
suite_manifest.json (pcve_suite/1), README.txt and inputs/native_input_locations.json.

The tool never moves or overwrites a suite: it builds into a new folder (--suite, must not exist) and
checks every case there (render tied to its states, media contract, ground truth in pcve_ground_truth/1).
Replacing the published suite is a separate step after review: move the published folder to
renders/pcve_suites_archive/, then move the new folder in its place, and update the canonical_suites entry
of scene_manifest.json from the printed hashes. The provenance records of the published suite
(--previous, default renders/pcve_suites/pcve_metro_security_bag_curtain_suite when it is not the
target) are carried over per case: standardization. Prompts of a published suite are
updated with `build_pcve_metro_security_bag_curtain.py --export-prompts`.
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

HERE = Path(__file__).resolve().parent
SCENE_DIR = HERE.parent
SCRIPTS = SCENE_DIR.parents[1]
sys.path[:0] = [str(HERE), str(SCENE_DIR), str(SCRIPTS)]
from pcve_edit_catalog import FORMAT_VERSION, _applies_from_frame, _fps, load_catalog  # noqa: E402
from pcve_media_contract import require_video  # noqa: E402
from pcve_case_metadata import carried_provenance  # noqa: E402
from scene_paths import NATIVE, REPO, SCENE, SUITE, ensure_numpy_runtime  # noqa: E402

BUILDER = SCENE_DIR / f"build_pcve_{SCENE}.py"
LAYOUT = "cases/<case_id>/{video.mp4,prompts.json,provenance.json,video_validation.json}"
METADATA = ("render_report.json", "encoding_receipt.json", "replay_audit.json", "support_audit.json",
            "scene_reuse_audit.json")
TIMED_STATE_FILES = ("states.npz", "simulation_config.json", "simulation_report.json")
GROUND_TRUTH_FORMAT = "pcve_ground_truth/1"


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".writing")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def relative(path):
    path = Path(path).resolve()
    return str(path.relative_to(REPO.resolve())) if REPO.resolve() in path.parents else str(path)


def prompt_record(record, fps):
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


def video_validation(video, case):
    contract = require_video(video)
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames:format=duration",
                            "-of", "json", str(video)], capture_output=True, text=True, check=True)
    probe = json.loads(probe.stdout)
    stream = probe["streams"][0]
    decode = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], capture_output=True, text=True)
    frames = int(stream["nb_read_frames"])
    return {"schema_version": 1, "format_version": "pcve_video_validation/1", "scene": SCENE, "case_id": case,
            "video": "video.mp4", "resolution": [int(stream["width"]), int(stream["height"])], "fps": stream["r_frame_rate"],
            "duration_sec": float(probe["format"]["duration"]), "frames": frames, "sha256": sha(video),
            "technical_probe_verified": frames == 96 and stream["r_frame_rate"] == "24/1",
            "full_decode_verified": decode.returncode == 0 and not decode.stderr.strip(),
            "content_unchanged": False, "visual_or_physics_acceptance": "new render; visual review pending",
            "native_validation": {"contract_probe": contract, "probe": probe}}


def check_render(case, render_dir, states_dir):
    """The render replays these native states: receipts, 96-frame replay audit, frame list."""
    report = read(render_dir / "render_report.json")
    receipt = read(render_dir / "encoding_receipt.json")
    replay = read(render_dir / "replay_audit.json")
    states = sha(states_dir / case / "states.npz")
    if report["simulation_cache_sha256"] != states or receipt["input_state_sha256"] != states:
        raise RuntimeError(f"{case}: render is not tied to {states_dir / case / 'states.npz'}")
    if receipt["video_sha256"] != sha(render_dir / "video.mp4"):
        raise RuntimeError(f"{case}: video.mp4 differs from its encoding receipt")
    if not replay["passed"] or replay["frames_checked"] != 96 or report["frames"] != list(range(96)):
        raise RuntimeError(f"{case}: replay audit or frame list incomplete")
    return report, states


def build(renders, suite, native, timed_native, look, previous=None):
    import export_ground_truth as gt
    from edit_vocab import TIMED_DSL
    if suite.exists():
        raise RuntimeError(f"{suite} exists; choose a new suite folder")
    if previous is not None and (previous == suite or not (previous / "cases").is_dir()):
        previous = None
    catalog = load_catalog(BUILDER)
    records = [catalog["source"], *catalog["edits"].values()]
    fps = _fps()
    checked = {}
    for record in records:
        case = record["case_id"]
        checked[case] = check_render(case, renders / case, timed_native if case in TIMED_DSL else native)
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    entries = []
    for record in records:
        native_case, case = record["case_id"], record["catalog_case_id"]
        render_dir = renders / native_case
        report, states_sha = checked[native_case]
        folder = suite / "cases" / case
        (folder / "native_metadata").mkdir(parents=True)
        shutil.copy2(render_dir / "video.mp4", folder / "video.mp4")
        for name in METADATA:
            if (render_dir / name).is_file():
                shutil.copy2(render_dir / name, folder / "native_metadata" / name)
        timed = native_case in TIMED_DSL
        if timed:
            target = suite / "inputs" / "native_timed" / native_case
            target.mkdir(parents=True)
            for name in TIMED_STATE_FILES:
                shutil.copy2(timed_native / native_case / name, target / name)
            for name in TIMED_STATE_FILES[1:]:
                shutil.copy2(timed_native / native_case / name, folder / "native_metadata" / name)
            states_root = suite / "inputs" / "native_timed"
        else:
            states_root = native
        digest = sha(folder / "video.mp4")
        if digest != sha(render_dir / "video.mp4"):
            raise RuntimeError(f"{case}: copy differs")
        check = video_validation(folder / "video.mp4", case)
        if not (check["technical_probe_verified"] and check["full_decode_verified"]):
            raise RuntimeError(f"{case}: video fails the media contract")
        write(folder / "video_validation.json", check)
        prompts = prompt_record(record, fps)
        write(folder / "prompts.json", prompts)
        truth = gt.build(native_case, states_root, report)
        if truth.get("format_version") != GROUND_TRUTH_FORMAT or len(truth.get("frames", ())) != 96:
            raise RuntimeError(f"{case}: ground truth is not {GROUND_TRUTH_FORMAT} with 96 frames; nothing published")
        truth = json.dumps(truth, indent=1) + "\n"
        (folder / "ground_truth_transforms.json").write_text(truth)
        provenance = {
            "schema_version": 1, "format_version": "pcve_provenance/1", "scene": SCENE, "case_id": case,
            "kind": record["kind"], "native_case_id": native_case, "video_sha256": digest, "created_at": now,
            "native_render_dir": relative(render_dir), "native_metadata": f"cases/{case}/native_metadata",
            "native_states": relative(states_root / native_case / "states.npz"), "native_states_sha256": states_sha,
            "ground_truth_sha256": hashlib.sha256(truth.encode()).hexdigest(),
            "scene_code": relative(SCENE_DIR), "look": look}
        old = previous / "cases" / case / "provenance.json" if previous is not None else None
        if old is not None and old.is_file():
            provenance["previous_suite"] = relative(previous)
            provenance.update(carried_provenance(old))
        if timed:
            config = read(timed_native / native_case / "simulation_config.json")
            provenance["status"] = "native_timed_physics_verified_and_rendered"
            provenance["native_timed_edit"] = {
                "edit_frame": config["continuation"]["edit_frame"],
                "native_states": f"inputs/native_timed/{native_case}/states.npz",
                "state_handoff_max_abs_error": max(config["continuation"]["handoff_max_abs_error"].values())}
        write(folder / "provenance.json", provenance)
        entries.append({
            "case_id": case, "native_case_id": native_case, "kind": record["kind"], "source_case_id": "source",
            "case_dir": f"cases/{case}", "status": provenance.get("status", "rendered_pending_review"),
            "availability": "video_present", "video": f"cases/{case}/video.mp4", "video_sha256": digest,
            "media": {k: check[k] for k in ("resolution", "fps", "duration_sec", "frames", "sha256")},
            **{k: prompts[k] for k in ("prompts", "edit_dsl", "object_id", "applies_from_frame", "application_time_sec",
                                       "physics_override", "physics_diff")},
            "ground_truth": f"cases/{case}/ground_truth_transforms.json",
            "ground_truth_sha256": provenance["ground_truth_sha256"]})
    write(suite / "inputs" / "native_input_locations.json", {
        "scene": SCENE, "kind": "native_input_locations",
        "native_states": relative(native), "timed_native_states": "inputs/native_timed/<case>/",
        "render_outputs": relative(renders), "scene_code": relative(SCENE_DIR),
        "metadata_policy": "Case-local evidence is in cases/<case>/native_metadata; frames, depth and object-index EXRs and "
                           "the saved scene of every case stay in the render output folder."})
    (suite / "README.txt").write_text(
        f"PCVE suite: {SCENE}\nSource: cases/source/video.mp4; edits: cases/edit_*/video.mp4 ({len(entries) - 1}).\n"
        "Per case: video.mp4, prompts.json, provenance.json, video_validation.json, native_metadata/, "
        "ground_truth_transforms.json.\nTimed edits: merged native states in inputs/native_timed/<case>/.\n"
        f"Index: suite_manifest.json. Scene code: {relative(SCENE_DIR)}.\n", encoding="utf-8")
    write(suite / "suite_manifest.json", {
        "schema_version": 5, "format_version": "pcve_suite/1", "layout": LAYOUT, "scene": SCENE, "title": SCENE,
        "suite_name": suite.name, "interaction_category": "rigid_elastic", "suite_path": relative(suite),
        "source_count": 1, "edit_count": len(entries) - 1, "status": "rendered_pending_review",
        "source": entries[0], "edits": entries[1:],
        "metadata": {"scene_id": SCENE, "created_at": now, "look": look, "storage_type": "physical_files",
                     "render_outputs": relative(renders), "ground_truth_exporter": relative(HERE / "export_ground_truth.py"),
                     "inputs": [{"role": "native_input_locations", "path": "inputs/native_input_locations.json"}]}})
    return {"suite": str(suite), "case_video_sha256": {e["native_case_id"]: e["video_sha256"] for e in entries},
            "case_ground_truth_sha256": {e["native_case_id"]: e["ground_truth_sha256"] for e in entries}}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--renders", type=Path, required=True, help="Folder with one render output folder per native case")
    p.add_argument("--native", type=Path, default=NATIVE, help="Native states of the whole-clip cases (<dir>/<case>/states.npz)")
    p.add_argument("--timed-native", type=Path, default=SUITE / "inputs" / "native_timed",
                   help="Merged native states of the timed edits (<dir>/<case>/states.npz; default: the published suite's)")
    p.add_argument("--suite", type=Path, default=SUITE.parents[1] / SCENE / "suite_build" / SUITE.name,
                   help="New suite folder (must not exist; default: renders/metro_security_bag_curtain/suite_build/<suite>)")
    p.add_argument("--previous", type=Path, default=SUITE,
                   help="Published suite whose per-case provenance history is carried over (default: the published suite)")
    p.add_argument("--look", default="metro concourse (appearance/realism.py)")
    args = p.parse_args()
    ensure_numpy_runtime()
    print(json.dumps(build(args.renders.resolve(), args.suite.resolve(), args.native.resolve(), args.timed_native.resolve(),
                           args.look, args.previous.resolve()),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
