"""Verify the published suite of picnic_ground_blanket against its native inputs.

For every case this checks, without rendering or solving:
  * native inputs of a whole-clip case (assets/scenes/picnic_ground_blanket/native/<case>/): SHA-256 equal to
    the assets.json registration, the 96-sample i/24 s clock, scene/case/fps/duration, and that the recorded
    edit override equals the DSL edit of physics/edit_vocab.py and the builder catalog (DELETE also removes the
    orange from the solve);
  * the timed edit's solver records in the suite case's native_metadata/ (edit, frame, exact state hand-off
    from the source cache of the asset store); when its merged solve (recorded in provenance.json) is readable,
    also that frames 1-11 are the source cache bit for bit;
  * the canonical suite named in scene_manifest.json: video SHA-256, media contract (1280x720, 24 fps,
    96 frames, 4.000 s, full decode), prompts.json (pcve_prompts/1) equal to the builder catalog, and
    ground_truth_transforms.json (pcve_ground_truth/1) equal to a fresh export from the native state
    (tools/export_ground_truth.py; the "source" record is not compared); the timed edit's frames 1-11 equal the
    source ground truth;
  * the render behind each video: for a whole-clip case the native render of the accepted delivery
    (scene_manifest.json data.accepted_delivery; same video bytes, the replayed cache is the case's native
    state), for the timed edit the render record in its native_metadata/ (replayed its merged solve).

Needs numpy (for example .venv-rigid-elastic/bin/python). Usage: verify.py [CASE ...] (default: all six).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parents[1]
REPO = CASE_DIR.parents[2]
for _path in (CASE_DIR, REPO / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import numpy as np  # noqa: E402
import pcve_edit_dsl as dsl  # noqa: E402
from pcve_edit_catalog import FORMAT_VERSION, load_catalog  # noqa: E402
from pcve_media_contract import require_times, require_video  # noqa: E402
from edit_vocab import EDIT_CASES, TIMED_EDIT_CASES, VOCAB  # noqa: E402
from scene_inputs import CASES, CATALOG, SCENE, TIMED_CASES, native  # noqa: E402
from scene_paths import DELIVERY, MANIFEST, SUITE, SUITE_DIR, repo_path  # noqa: E402
from tools.export_ground_truth import compare as compare_ground_truth  # noqa: E402

NATIVE_FILES = ("cache.npz", "initial_state.npz", "simulation_config.json", "simulation_report.json")
GROUND_TRUTH_FORMAT = "pcve_ground_truth/1"
STATE_ARRAYS = ("solid_positions", "solid_velocities", "cloth_positions", "cloth_velocities", "body_transforms", "body_velocities")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def registered(group=f"scenes/{SCENE}"):
    return read(REPO / "assets.json")["assets"][group]["files"]


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def override_of(text):
    return dsl.to_physics_override(dsl.parse(text, VOCAB), VOCAB) if text else {}


def verify_native(case, files, catalog):
    folder = native(case)
    for name in NATIVE_FILES:
        entry = files.get(f"native/{case}/{name}")
        check(entry is not None, f"{case}: native/{case}/{name} is not registered in assets.json")
        check(sha256(folder / name) == entry["sha256"], f"{case}: native {name} differs from assets.json")
    config = read(folder / "simulation_config.json")
    check((config["scene_id"], config["case"], config["simulation"]["fps"], config["simulation"]["duration"]) == (SCENE, case, 24, 4.0),
          f"{case}: unexpected native scene, case or clock")
    text = EDIT_CASES[case]
    override = override_of(text)
    check(config["edit"].get("override", {}) == override, f"{case}: native edit override differs from the DSL")
    check(all(config["physics"].get(k) == v for k, v in override.items()), f"{case}: native physics lacks the edit")
    record = catalog["source"] if case == "source" else catalog["edits"][case]
    if case != "source":
        check(record["edit_dsl"] == text and record["physics_override"] == override, f"{case}: builder catalog differs from the DSL")
    if case == "delete_actor":
        report = read(folder / "simulation_report.json")
        check(config["physics"]["active"][0] == 0 and report["body_mass_kg"] == 0, "delete_actor: the orange is still solved")
    with np.load(folder / "cache.npz", allow_pickle=False) as cache:
        times = cache["times"]
        cup = bool(cache["path_obstacle_present"][0])
    require_times(times)
    check(not cup, f"{case}: the picnic-cup ADD object (in no published case) is present in the native state")
    return record


def verify_timed(case, folder, catalog):
    """Solver records of a timed edit published with its suite case."""
    record = catalog["edits"][case]
    text = TIMED_EDIT_CASES[case]
    override = override_of(text)
    frame = dsl.starts_at_frame(dsl.parse(text, VOCAB))
    check(record["edit_dsl"] == text and record["physics_override"] == override, f"{case}: builder catalog differs from the DSL")
    metadata = folder / "native_metadata"
    config = read(metadata / "simulation_config.json")
    check((config["scene_id"], config["case"], config["simulation"]["fps"], config["simulation"]["duration"]) == (SCENE, case, 24, 4.0),
          f"{case}: unexpected native scene, case or clock")
    check(config["edit"].get("override", {}) == override and all(config["physics"].get(k) == v for k, v in override.items()),
          f"{case}: native edit differs from the DSL")
    timed = config["timed_edit"]
    source_cache = native("source") / "cache.npz"
    check(timed["frame"] == frame and abs(timed["time_s"] - (frame - 1) / 24) < 1e-12, f"{case}: edit frame differs from the DSL")
    check(timed["source_frames_kept"] == [1, frame - 1] and timed["continued_frames"] == [frame, 96], f"{case}: unexpected frame split")
    check(timed["source_cache_sha256"] == sha256(source_cache), f"{case}: the continuation did not start from the accepted source cache")
    handoff = read(metadata / "state_handoff.json")
    check(handoff["verified"] and handoff["edit_frame"] == frame and max(handoff["max_abs_error"].values()) < 1e-8,
          f"{case}: state hand-off not verified")
    provenance = read(folder / "provenance.json")
    physics = provenance.get("standardization", {}).get("physics", {})
    merged_sha = physics.get("merged_cache_sha256")
    render = read(metadata / "render_report.json")
    check(merged_sha is not None and render["physics_cache_sha256"] == merged_sha, f"{case}: the video replays another solve than the published one")
    check(render["max_surface_replay_error_m"] <= 2e-6 and render["surface_amplification"] == 1.0, f"{case}: cloth replay audit failed")
    merged = repo_path(physics["merged_cache"]) if physics.get("merged_cache") else None
    solve = None
    if merged is not None and merged.is_file() and sha256(merged) == merged_sha:
        solve = merged.parent
        with np.load(merged, allow_pickle=False) as timed_cache, np.load(source_cache, allow_pickle=False) as source:
            for name in STATE_ARRAYS:
                check(np.array_equal(timed_cache[name][:frame - 1], source[name][:frame - 1]), f"{case}: frames before the edit differ from the source in {name}")
    return record, solve, merged_sha


def verify_case(case, files, catalog, suite):
    folder = SUITE_DIR / "cases" / CATALOG[case]
    if case in TIMED_CASES:
        record, solve, cache_sha = verify_timed(case, folder, catalog)
    else:
        record, solve, cache_sha = verify_native(case, files, catalog), None, files[f"native/{case}/cache.npz"]["sha256"]
    video = folder / "video.mp4"
    digest = sha256(video)
    check(digest == suite["case_video_sha256"][case], f"{case}: suite video differs from scene_manifest.json")
    media = require_video(video)
    prompts = read(folder / "prompts.json")
    check(prompts.get("format_version") == FORMAT_VERSION and prompts["prompts"] == record["prompts"]
          and prompts.get("edit_dsl") == record.get("edit_dsl"), f"{case}: prompts.json differs from the builder catalog")
    if case != "source":
        check(prompts["physics_override"] == record["physics_override"] and prompts["applies_from_frame"] == record["applies_from_frame"],
              f"{case}: prompts.json edit fields differ from the builder catalog")
    gt = read(folder / "ground_truth_transforms.json")
    check(gt.get("format_version") == GROUND_TRUTH_FORMAT and gt.get("case_id") == CATALOG[case] and len(gt["frames"]) == 96,
          f"{case}: ground truth is not {GROUND_TRUTH_FORMAT}")
    require_times([frame["time_sec"] for frame in gt["frames"]])
    exported = case not in TIMED_CASES or solve is not None
    if exported:
        differing = compare_ground_truth(case, SUITE_DIR, solve)
        check(not differing, f"{case}: GT differs from a fresh export of the native state in {differing}")
    if case in TIMED_CASES:
        frame = record["applies_from_frame"]
        source_gt = read(SUITE_DIR / "cases" / "source" / "ground_truth_transforms.json")
        check(gt["frames"][:frame - 1] == source_gt["frames"][:frame - 1], f"{case}: GT frames before the edit differ from the source")
        report = folder / "native_metadata" / "render_report.json"
    else:
        native_render = DELIVERY / suite["native_renders"][case]
        check(sha256(native_render / "video.mp4") == digest, f"{case}: native delivery video differs from the suite")
        report = native_render / "render_report.json"
        render = read(report)
        check(render["physics_cache_sha256"] == cache_sha, f"{case}: the video replays a different native cache")
        check(render["max_surface_replay_error_m"] <= 2e-6 and render["surface_amplification"] == 1.0, f"{case}: cloth replay audit failed")
    return {"case_id": case, "suite_case": CATALOG[case], "video_sha256": digest, "native_cache_sha256": cache_sha,
            "render_record": str(report), "gt_frames": len(gt["frames"]), "gt_reexported": exported, "media": media}


def verify(cases=CASES + TIMED_CASES):
    catalog = load_catalog(CASE_DIR / f"build_pcve_{SCENE}.py")
    files = registered()
    suite = MANIFEST["canonical_suites"][SUITE]
    return [verify_case(case, files, catalog, suite) for case in cases]


if __name__ == "__main__":
    selected = sys.argv[1:] or list(CASES + TIMED_CASES)
    unknown = sorted(set(selected) - set(CASES + TIMED_CASES))
    if unknown:
        raise SystemExit(f"Unknown cases {unknown}; choices: {', '.join(CASES + TIMED_CASES)}")
    print(json.dumps({"scene": SCENE, "suite": str(SUITE_DIR), "verified_cases": verify(selected)}, indent=2))
