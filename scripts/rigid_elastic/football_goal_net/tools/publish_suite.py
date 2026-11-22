"""Assemble a suite from per-case render outputs in the current PCVE suite format.

    python3 scripts/rigid_elastic/football_goal_net/tools/publish_suite.py --renders DIR \
        [--timed-solves DIR] (--suite NEW_DIR | --publish [--archive-root DIR]) [--blender-bin BLENDER]

<renders>/<case>/ holds video.mp4 with render_setup.json and render_report_*.json beside it, as
written by render_football_goal_net.py --render, one folder per native case. A timed edit
(edit_vocab.TIMED_DSL) also needs its merged native solve in <timed-solves>/<case>/ (simulation.npz,
timed_edit.json and the edit run's reports, see physics/solve_timed.py); it is copied to the suite's
inputs/native_timed/<case>/.

Per case the suite gets video.mp4, native_metadata/ (the render JSON files), prompts.json
(pcve_prompts/1, from PCVE_SOURCE / PCVE_EDITS of build_pcve_football_goal_net.py), provenance.json
(pcve_provenance/1), video_validation.json (pcve_video_validation/1) and ground_truth_transforms.json,
written by tools/export_ground_truth.py inside Blender and required to be pcve_ground_truth/1; the
suite gets suite_manifest.json (pcve_suite/1), README.txt and inputs/native_input_locations.json.
The standardization records of the published suite's provenance.json files are
carried into the new provenance.json of the same case.

--suite builds into a new folder (it must not exist). --publish builds into a staging folder next to
the published suite, checks it completely, and only then moves the published suite to the archive
and the staging folder into its place (and updates case_video_sha256 in scene_manifest.json); nothing
is moved when a step fails. Prompts of a published suite are updated with
`build_pcve_football_goal_net.py --export-prompts`.
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
REPO = SCRIPTS.parent
sys.path[:0] = [str(SCRIPTS), str(SCENE_DIR)]
from pcve_edit_catalog import FORMAT_VERSION, _applies_from_frame, _fps, load_catalog  # noqa: E402
from pcve_media_contract import require_video  # noqa: E402
from pcve_case_metadata import carried_provenance as _carried  # noqa: E402
from edit_vocab import TIMED_DSL  # noqa: E402

SCENE = "football_goal_net"
BUILDER = SCENE_DIR / f"build_pcve_{SCENE}.py"
SUITE = REPO / f"renders/pcve_suites/pcve_{SCENE}_suite"
MANIFEST = SCENE_DIR / "scene_manifest.json"
LAYOUT = "cases/<case_id>/{video.mp4,prompts.json,provenance.json,video_validation.json}"
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


def copy_timed_solve(native, solves, suite, cache_sha256):
    """Copy a timed edit's merged native solve (files only) to inputs/native_timed/<case>/ and check its bindings."""
    if solves is None:
        raise RuntimeError(f"{native}: a timed edit needs --timed-solves with its merged native solve")
    source_dir = solves / native
    receipt = read(source_dir / "timed_edit.json")
    if not (receipt["case"] == native and receipt["simulation_sha256"] == sha(source_dir / "simulation.npz") == cache_sha256):
        raise RuntimeError(f"{native}: merged solve does not match its receipt or the rendered cache")
    target = suite / "inputs/native_timed" / native
    target.mkdir(parents=True)
    for path in sorted(p for p in source_dir.iterdir() if p.is_file()):
        shutil.copy2(path, target / path.name)
        if sha(target / path.name) != sha(path):
            raise RuntimeError(f"{native}: copy of {path.name} differs")
    return target


def carried_provenance(previous, case):
    """standardization record of this case in the published suite, if it has them."""
    path = previous / "cases" / case / "provenance.json" if previous is not None else None
    return _carried(path) if path is not None else {}


def export_ground_truth(suite, blender):
    """Write every case's ground truth in Blender and require pcve_ground_truth/1 with 96 frames."""
    if blender is None:
        from pcve_assets import blender as default_blender
        blender = default_blender()
    subprocess.run([str(blender), "-b", "--factory-startup", "--python-exit-code", "1",
                    "--python", str(HERE / "export_ground_truth.py"), "--", "--suite", str(suite)], check=True)
    for case_dir in sorted((suite / "cases").iterdir()):
        gt = read(case_dir / "ground_truth_transforms.json")
        if not (gt.get("format_version") == GROUND_TRUTH_FORMAT and gt.get("case_id") == case_dir.name
                and gt.get("fps") == 24 and len(gt.get("frames", [])) == 96):
            raise RuntimeError(f"{case_dir.name}: ground truth is not {GROUND_TRUTH_FORMAT} with 96 frames")


def build(renders, suite, look, timed_solves=None, previous=None, blender=None, final=None):
    """Build a complete suite in `suite`; `final` is where it will be published (default: `suite`)."""
    if suite.exists():
        raise RuntimeError(f"{suite} exists; choose a new suite folder")
    catalog = load_catalog(BUILDER)
    records = [catalog["source"], *catalog["edits"].values()]
    fps = _fps()
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    entries = []
    for record in records:
        native, case = record["case_id"], record["catalog_case_id"]
        source_dir = renders / native
        folder = suite / "cases" / case
        (folder / "native_metadata").mkdir(parents=True)
        shutil.copy2(source_dir / "video.mp4", folder / "video.mp4")
        for name in sorted(p.name for p in source_dir.glob("*.json")):
            shutil.copy2(source_dir / name, folder / "native_metadata" / name)
        digest = sha(folder / "video.mp4")
        if digest != sha(source_dir / "video.mp4"):
            raise RuntimeError(f"{case}: copy differs")
        check = video_validation(folder / "video.mp4", case)
        if not (check["technical_probe_verified"] and check["full_decode_verified"]):
            raise RuntimeError(f"{case}: video fails the media contract")
        write(folder / "video_validation.json", check)
        prompts = prompt_record(record, fps)
        write(folder / "prompts.json", prompts)
        cache_sha256 = read(source_dir / "render_setup.json")["shared"]["cache_sha256"]
        provenance = {
            "schema_version": 1, "format_version": "pcve_provenance/1", "scene": SCENE, "case_id": case,
            "kind": record["kind"], "native_case_id": native, "video_sha256": digest, "created_at": now,
            "native_render_dir": relative(source_dir), "native_metadata": f"cases/{case}/native_metadata",
            "render_cache_sha256": cache_sha256, "scene_code": relative(SCENE_DIR), "look": look}
        if native in TIMED_DSL:
            timed = copy_timed_solve(native, timed_solves, suite, cache_sha256)
            provenance["native_timed_inputs"] = f"inputs/native_timed/{native}"
            provenance["status"] = "native_timed_physics_verified_and_rendered"
            provenance["timed_edit"] = read(timed / "timed_edit.json")
        provenance.update(carried_provenance(previous, case))
        write(folder / "provenance.json", provenance)
        entries.append({
            "case_id": case, "native_case_id": native, "kind": record["kind"], "source_case_id": "source",
            "case_dir": f"cases/{case}", "status": "rendered_pending_review", "availability": "video_present",
            "video": f"cases/{case}/video.mp4", "video_sha256": digest,
            "media": {k: check[k] for k in ("resolution", "fps", "duration_sec", "frames", "sha256")},
            **{k: prompts[k] for k in ("prompts", "edit_dsl", "object_id", "applies_from_frame", "application_time_sec",
                                       "physics_override", "physics_diff")}})
    write(suite / "inputs" / "native_input_locations.json", {
        "scene": SCENE, "kind": "native_input_locations",
        "native_caches": "assets/scenes/football_goal_net/native/<case>/simulation.npz (120 Hz, 481 states; render gate, "
                         "physics report and geometry audit beside it)",
        "timed_native_solves": "inputs/native_timed/<case>/ of this suite (merged solve of physics/solve_timed.py)",
        "packed_scene": "assets/scenes/football_goal_net/prepared_scene.blend",
        "accepted_physics_delivery": "renders/football_goal_net/accepted_physics",
        "accepted_media_delivery": "renders/football_goal_net/accepted_media",
        "render_outputs": relative(renders), "scene_code": relative(SCENE_DIR)})
    (suite / "README.txt").write_text(
        f"PCVE suite: {SCENE}\nSource: cases/source/video.mp4; edits: cases/edit_*/video.mp4 ({len(entries) - 1}).\n"
        "Per case: video.mp4, prompts.json, provenance.json, video_validation.json, native_metadata/, "
        "ground_truth_transforms.json.\nTimed edits: merged native solve in inputs/native_timed/<case>/.\n"
        "Index: suite_manifest.json. Scene code: scripts/rigid_elastic/football_goal_net.\n",
        encoding="utf-8")
    write(suite / "suite_manifest.json", {
        "schema_version": 5, "format_version": "pcve_suite/1", "layout": LAYOUT, "scene": SCENE, "title": SCENE,
        "suite_name": SUITE.name, "interaction_category": "rigid_elastic", "suite_path": relative(final or suite),
        "source_count": 1, "edit_count": len(entries) - 1, "status": "rendered_pending_review",
        "source": entries[0], "edits": entries[1:],
        "metadata": {"scene_id": SCENE, "created_at": now, "look": look, "storage_type": "physical_files",
                     "render_outputs": relative(renders),
                     "inputs": [{"role": "native_input_locations", "path": "inputs/native_input_locations.json"}]}})
    export_ground_truth(suite, blender)
    return {"suite": str(suite), "cases": {e["native_case_id"]: e["video_sha256"] for e in entries}}


def update_scene_manifest(cases, renders):
    """Point case_video_sha256 of the published suite at the new videos (keyed by native case id)."""
    manifest = read(MANIFEST)
    entry = manifest["canonical_suites"][SUITE.name]
    entry["native_render_outputs"] = relative(renders)
    entry["case_video_sha256"] = dict(cases)
    entry["public_case_ids"] = {case: "source" if case == "source" else "edit_" + case for case in cases}
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def publish(renders, look, timed_solves, archive_root, blender, target=SUITE):
    """Build and check a staging suite next to the published one, then swap them (published -> archive)."""
    final = target.resolve() if target.exists() else target.parent.resolve() / target.name
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    staging = final.parent / f".{final.name}.staging_{stamp}"
    archive = (archive_root or final.parent.parent / "pcve_suites_archive") / f"{final.name}_before_{stamp}"
    if archive.exists():
        raise FileExistsError(archive)
    result = build(renders, staging, look, timed_solves, final if final.exists() else None, blender, final)
    if final.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(final), str(archive))
    try:
        staging.rename(final)
    except OSError:
        if archive.exists() and not final.exists():
            shutil.move(str(archive), str(final))
        raise
    if target == SUITE:
        update_scene_manifest(result["cases"], renders)
    return {**result, "published": str(final), "previous_suite": str(archive) if archive.exists() else None}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--renders", type=Path, required=True, help="Folder with one render output folder per native case")
    p.add_argument("--timed-solves", type=Path, help="Folder with the merged native solve of each timed edit (<case>/)")
    where = p.add_mutually_exclusive_group(required=True)
    where.add_argument("--suite", type=Path, help="New suite folder (must not exist)")
    where.add_argument("--publish", action="store_true", help="Replace the published suite after a complete staging build")
    p.add_argument("--archive-root", type=Path, help="Where --publish moves the previous suite (default: renders/pcve_suites_archive)")
    p.add_argument("--target", type=Path, default=SUITE,
                   help="Suite that --publish replaces (default: the published suite; scene_manifest.json is updated only for it)")
    p.add_argument("--previous", type=Path, help="Suite whose provenance records are carried over (default: the published suite)")
    p.add_argument("--blender-bin", type=Path, help="Blender 4.3.2 for the ground truth (default: pcve_assets.blender())")
    p.add_argument("--look", default="appearance/realism.py")
    args = p.parse_args()
    timed = args.timed_solves.resolve() if args.timed_solves else None
    if args.publish:
        result = publish(args.renders.resolve(), args.look, timed, args.archive_root, args.blender_bin, args.target)
    else:
        previous = args.previous or (SUITE if SUITE.exists() else None)
        result = build(args.renders.resolve(), args.suite.resolve(), args.look, timed, previous, args.blender_bin)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
