"""Build the published video suite from a finished set of renders of the current look.

    python3 tools/publish_suite.py --native renders/plastic_ruler_coin/rebuild [--publish] [--update-scene-manifest]

`--native` holds `realism/<case>/frame_0001..0096.png` with realism_provenance.json, camera.json,
render_replay.jsonl and ruler_render_binding.npz for all six cases (render_plastic_ruler_coin.py --out-root
<native>). Every case is first replay-checked against its native solve (tools/verify_replay.py); frames are encoded
when video.mp4 is missing (libx264 crf 16 yuv420p, 24 fps). The suite is assembled in `<native>/suite_staging` in
the current PCVE suite format: cases/<id>/video.mp4, prompts.json (pcve_prompts/1, from the builder catalog),
provenance.json (pcve_provenance/1), video_validation.json (pcve_video_validation/1), native_metadata/,
ground_truth_transforms.json (tools/export_ground_truth.py, pcve_ground_truth/1); suite_manifest.json (pcve_suite/1),
inputs/, native_manifests/, README.txt. A case that replaces a published case keeps the standardization
record of the published provenance.json. With --publish, once every case's ground truth is checked
to be pcve_ground_truth/1, the current suite moves to archive/pcve_suites/<suite>_before_<native folder name>/ and the
staging folder takes its place; then run this tool with --update-scene-manifest. Prompts of a published suite are
updated with `build_pcve_plastic_ruler_coin.py --export-prompts`.
Run with the repository venv (.venv-rigid-elastic/bin/python); ffmpeg and ffprobe must be on PATH.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
CASE = HERE.parent
sys.path[:0] = [str(HERE), str(CASE), str(CASE.parents[1])]
from scene_paths import (CASES, CATALOG, DELIVERED_SUITE, DELIVERY, REPO, SCENE, SUITE_NAME,  # noqa: E402
                         cache_dir)
from verify_replay import audit  # noqa: E402
from pcve_ground_truth import check_suite  # noqa: E402
from pcve_case_metadata import carried_provenance  # noqa: E402

FINAL = REPO / "renders/pcve_suites" / SUITE_NAME
BUILDER = CASE / f"build_pcve_{SCENE}.py"
LAYOUT = "cases/<case_id>/{video.mp4,prompts.json,provenance.json,video_validation.json}"
def carried(case_dir):
    """The standardization record of a published case, which a rebuilt case keeps."""
    return carried_provenance(Path(case_dir) / "provenance.json")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rel(path):
    path = Path(path).resolve()
    return str(path.relative_to(REPO.resolve())) if REPO.resolve() in path.parents else str(path)


def snapshot(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if sha(dst) != sha(src):
        raise RuntimeError(f"copy differs: {dst}")
    return sha(dst)


def encode(folder):
    video = folder / "video.mp4"
    if not video.is_file():
        frames = sorted(folder.glob("frame_*.png"))
        if [p.name for p in frames] != [f"frame_{i:04d}.png" for i in range(1, 97)]:
            raise RuntimeError(f"{folder}: expected frame_0001..0096.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "24", "-i", str(folder / "frame_%04d.png"),
                        "-frames:v", "96", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", str(video)], check=True)
    provenance = json.loads((folder / "realism_provenance.json").read_text())
    if provenance.get("frames") != [1, 96, 96]:
        raise RuntimeError(f"{folder}: provenance does not cover frames 1-96")
    provenance["video"] = {"file": video.name, "sha256": sha(video), "encoder": "ffmpeg libx264 crf 16 yuv420p 24 fps"}
    save(folder / "realism_provenance.json", provenance)
    return video


def inspect(video, case_id):
    """pcve_video_validation/1 record of one encoded video."""
    probe = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
         "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames:format=duration",
         "-of", "json", str(video)]))
    decode = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(video), "-f", "null", "-"], capture_output=True, text=True)
    stream = probe["streams"][0]
    duration = float(probe["format"]["duration"])
    frames = int(stream["nb_read_frames"])
    compliant = (stream["width"], stream["height"], stream["avg_frame_rate"], frames) == (1280, 720, "24/1", 96) and abs(duration - 4) < 1e-3
    return {"schema_version": 1, "format_version": "pcve_video_validation/1", "scene": SCENE, "case_id": case_id,
            "video": "video.mp4", "resolution": [stream["width"], stream["height"]], "fps": stream["avg_frame_rate"],
            "duration_sec": duration, "frames": frames, "sha256": sha(video), "technical_probe_verified": compliant,
            "full_decode_verified": decode.returncode == 0 and not decode.stderr.strip(), "content_unchanged": False,
            "visual_or_physics_acceptance": "replay-checked against the native solve; visual review pending",
            "native_validation": {"probe": probe}}


def prompt_record(record, fps):
    """The pcve_prompts/1 file that `--export-prompts` keeps unchanged for this catalog record."""
    from pcve_edit_catalog import FORMAT_VERSION, _applies_from_frame
    item = {"schema_version": 1, "format_version": FORMAT_VERSION, "scene": SCENE, "case_id": record["catalog_case_id"],
            "kind": record["kind"], "source_case_id": "source", "availability": "available", "prompts": record["prompts"],
            "edit_dsl": None, "object_id": None, "applies_from_frame": None, "application_time_sec": None,
            "physics_override": {}, "physics_diff": {},
            "prompt_provenance": {"origin": "generated:" + rel(BUILDER), "text_modified": False}}
    if record["kind"] == "edit":
        frame = _applies_from_frame(record)
        item.update(edit_dsl=record["edit_dsl"], applies_from_frame=frame, application_time_sec=(frame - 1) / fps,
                    physics_override=record["physics_override"], physics_diff=record["physics_diff"])
    return item


def build(native, stage):
    from pcve_edit_catalog import _fps, load_catalog
    if stage.exists():
        raise FileExistsError(stage)
    catalog = load_catalog(BUILDER)
    declared = {"source": catalog["source"], **catalog["edits"]}
    fps = _fps()
    stage.mkdir(parents=True)
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    entries = []
    for case in CASES:
        case_id = CATALOG[case]
        folder = native / "realism" / case
        replay = audit(folder, cache_dir(case), write=True)
        if not replay["passed"]:
            raise RuntimeError(f"{case}: rendered states differ from the native solve: {replay['failures'][:3]}")
        video = encode(folder)
        target = stage / "cases" / case_id
        snapshot(video, target / "video.mp4")
        files = [folder / n for n in ("realism_provenance.json", "camera.json", "render_replay.jsonl", "render_replay_audit.json")]
        files += [cache_dir(case) / n for n in ("simulation_config.json", "simulation_report.json")]
        files.append(DELIVERED_SUITE / "cases" / case / "scenario_overrides.json")
        metadata = []
        for p in files:
            dst = target / "native_metadata" / p.name
            digest = snapshot(p, dst)
            metadata.append({"source": rel(p), "relative": "native_metadata/" + p.name, "sha256": digest, "bytes": dst.stat().st_size})
        snapshot(target / "native_metadata/scenario_overrides.json", target / "scenario_overrides.json")
        check = inspect(target / "video.mp4", case_id)
        if not (check["technical_probe_verified"] and check["full_decode_verified"]):
            raise RuntimeError(f"{case}: video is not 1280x720 / 24 fps / 96 frames / 4 s or does not decode")
        save(target / "video_validation.json", check)
        prompts = prompt_record(declared[case], fps)
        save(target / "prompts.json", prompts)
        save(target / "provenance.json", {
            "schema_version": 1, "format_version": "pcve_provenance/1", "scene": SCENE, "case_id": case_id,
            "kind": prompts["kind"], "native_case_id": case, "video_sha256": check["sha256"], "created_at": now,
            "native_render_dir": rel(folder), "native_cache": rel(cache_dir(case)), "native_case_metadata": metadata,
            "native_acceptance": "Native solves are the accepted solves (unchanged); the video renders the same states, "
                                 "replay-checked frame by frame. Technical video checks do not establish visual acceptance.",
            **carried(FINAL / "cases" / case_id)})
        entries.append({
            "case_id": case_id, "native_case_id": case, "kind": prompts["kind"], "source_case_id": "source",
            "case_dir": f"cases/{case_id}", "status": "video_verified_pending_visual_review", "availability": "video_present",
            "video": f"cases/{case_id}/video.mp4", "video_sha256": check["sha256"],
            "media": {k: check[k] for k in ("resolution", "fps", "duration_sec", "frames", "sha256")},
            **{k: prompts[k] for k in ("prompts", "edit_dsl", "object_id", "applies_from_frame", "application_time_sec",
                                       "physics_override", "physics_diff")}})
    manifests = [CASE / "entrypoints.json", CASE / "scene_manifest.json", DELIVERY / "accepted_case.json",
                 DELIVERED_SUITE / "suite_manifest.json"]
    native_manifests = []
    for i, p in enumerate(manifests):
        dst = stage / "native_manifests" / f"{i:02d}_{p.name}"
        native_manifests.append({"source": rel(p), "path": str(dst.relative_to(stage)), "sha256": snapshot(p, dst)})
    look = json.loads((native / "realism" / "source" / "realism_provenance.json").read_text())
    save(stage / "inputs/native_input_locations.json", {
        "scene": SCENE, "kind": "native_input_locations",
        "original_case_directories": [rel(native / "realism" / c) for c in CASES],
        "scene_code": rel(CASE), "native_caches": rel(cache_dir("<case>")), "look": rel(CASE / "appearance/realism.py"),
        "look_assets": sorted(set(look["assets"].values()))})
    save(stage / "suite_manifest.json", {
        "schema_version": 5, "format_version": "pcve_suite/1", "layout": LAYOUT, "scene": SCENE, "title": SCENE,
        "suite_name": SUITE_NAME, "interaction_category": "rigid_elastic", "suite_path": rel(FINAL), "source_count": 1,
        "edit_count": len(entries) - 1, "status": "video_verified_pending_visual_review",
        "source": entries[0], "edits": entries[1:],
        "metadata": {"scene_id": SCENE, "created_at": now, "storage_type": "physical_files", "render_outputs": rel(native),
                     "inputs": [{"role": "native_input_locations", "path": "inputs/native_input_locations.json"}],
                     "native_manifests": native_manifests}})
    (stage / "README.txt").write_text(
        f"PCVE suite: {SCENE}\nSource: cases/source/video.mp4; edits: cases/edit_*/video.mp4 ({len(entries) - 1}).\n"
        "Per case: video.mp4, prompts.json, provenance.json, video_validation.json, native_metadata/, "
        "ground_truth_transforms.json.\nIndex: suite_manifest.json. Scene code: scripts/rigid_elastic/plastic_ruler_coin.\n",
        encoding="utf-8")
    subprocess.run([sys.executable, str(HERE / "export_ground_truth.py"), "--suite", str(stage)], check=True)
    for p in stage.rglob("*.json"):
        json.loads(p.read_text())
    check_suite(stage)
    return {e["native_case_id"]: e["video_sha256"] for e in entries}


def publish(native, stage):
    check_suite(stage)
    archive = REPO / "archive/pcve_suites" / f"{SUITE_NAME}_before_{native.name}"
    if archive.exists():
        raise FileExistsError(archive)
    archive.parent.mkdir(parents=True, exist_ok=True)
    if FINAL.exists():
        shutil.move(str(FINAL), str(archive))
    shutil.move(str(stage), str(FINAL))
    return {"published": str(FINAL), "previous_suite": str(archive)}


def update_scene_manifest(native):
    path = CASE / "scene_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    suite = json.loads((FINAL / "suite_manifest.json").read_text())
    records = [suite["source"], *suite["edits"]]
    entry = manifest["canonical_suites"][SUITE_NAME]
    entry.update(target=rel(FINAL),
                 case_video_sha256={r["native_case_id"]: r["video_sha256"] for r in records},
                 case_video_path={r["native_case_id"]: r["video"] for r in records})
    manifest["data"]["native_renders"] = rel(native)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return entry


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--native", type=Path, required=True)
    p.add_argument("--publish", action="store_true")
    p.add_argument("--update-scene-manifest", action="store_true")
    a = p.parse_args()
    native = a.native.resolve()
    stage = native / "suite_staging"
    result = {}
    if not a.update_scene_manifest or a.publish:
        result["video_sha256"] = build(native, stage)
    if a.publish:
        result.update(publish(native, stage))
    if a.update_scene_manifest:
        result["scene_manifest"] = update_scene_manifest(native)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
