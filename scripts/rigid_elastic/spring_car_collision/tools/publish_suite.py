"""Assemble a suite from a finished render root in the current PCVE suite format.

    python tools/publish_suite.py --native renders/spring_car_collision/<folder> [--staging DIR] [--publish]

`--native` holds <case>/frame_0001..0096.png (or video.mp4), render_metadata.json, replay_audit.json and
one render_part_*.json per Blender run for all six cases (render_spring_car_collision.py --out-root
<native>). Per case the frames are encoded (libx264, crf 16, yuv420p, bt709, 24 fps) when video.mp4 is
missing, the parts are checked for one device type, one setting and one code version, and the suite is
assembled in --staging (default <native>/suite_staging): cases/<id>/video.mp4, native_metadata/,
scenario_overrides.json, prompts.json (pcve_prompts/1, from PCVE_SOURCE / PCVE_EDITS of the builder),
provenance.json (pcve_provenance/1), video_validation.json (pcve_video_validation/1) and
ground_truth_transforms.json (tools/export_ground_truth.py, pcve_ground_truth/1), plus suite_manifest.json
(pcve_suite/1), README.txt and inputs/native_input_locations.json. With --publish, once every case's
ground truth is checked to be pcve_ground_truth/1, the current suite moves to
archive/pcve_suites/<suite>_before_<native folder name>/, the staging folder takes its place and
scene_manifest.json is repointed.
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
import scene_config as cfg  # noqa: E402
from pcve_edit_catalog import FORMAT_VERSION, _applies_from_frame, _fps, load_catalog  # noqa: E402
from pcve_ground_truth import check_suite  # noqa: E402

FINAL = cfg.SUITE
BUILDER = CASE / f"build_pcve_{cfg.SCENE}.py"
LAYOUT = "cases/<case_id>/{video.mp4,prompts.json,provenance.json,video_validation.json}"
def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def relative(path):
    path = Path(path).resolve()
    return str(path.relative_to(cfg.REPO.resolve())) if cfg.REPO.resolve() in path.parents else str(path)


def snapshot(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if sha(dst) != sha(src):
        raise RuntimeError(f"copy differs: {dst}")
    return sha(dst)


def merged_parts(folder):
    """All frames 1..96 exactly once, rendered on one device type with one setting and native cache."""
    parts = [json.loads(p.read_text()) for p in sorted(folder.glob("render_part_*.json"))]
    frames = sorted(f for p in parts for f in p["frames"])
    if frames != list(range(1, 97)):
        raise RuntimeError(f"{folder}: render parts do not cover frames 1-96 exactly once ({len(frames)} frames)")
    def key(p):
        r = {k: v for k, v in p["render"].items() if k not in ("host", "cuda_visible_devices", "cycles_devices")}
        return json.dumps([r, sorted({d["name"] for d in p["render"]["cycles_devices"]}),
                           p["native_cache_sha256"]], sort_keys=True)
    if len({key(p) for p in parts}) != 1:
        raise RuntimeError(f"{folder}: render parts differ in device type, settings or cache")
    return {"parts": len(parts), "hosts": sorted({p["render"]["host"] for p in parts}),
            "devices": sorted({d["name"] for p in parts for d in p["render"]["cycles_devices"]}) or ["CPU"],
            "render": parts[0]["render"]}


def encode(folder):
    video = folder / "video.mp4"
    if not video.is_file():
        frames = sorted(folder.glob("frame_*.png"))
        if [p.name for p in frames] != [f"frame_{i:04d}.png" for i in range(1, 97)]:
            raise RuntimeError(f"{folder}: expected frame_0001..0096.png")
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-framerate", "24", "-i", str(folder / "frame_%04d.png"),
                        "-frames:v", "96", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
                        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                        "-movflags", "+faststart", str(video)], check=True)
    return video


def video_validation(video, case_id):
    """pcve_video_validation/1 record: probe, full decode and the 1280x720 / 24 fps / 96 frames / 4 s contract."""
    from pcve_media_contract import require_video
    contract = require_video(video)
    probe = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
         "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames:format=duration",
         "-of", "json", str(video)]))
    decode = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(video), "-f", "null", "-"],
                            capture_output=True, text=True)
    stream = probe["streams"][0]
    duration = float(probe["format"]["duration"])
    frames = int(stream["nb_read_frames"])
    technical = (stream["width"], stream["height"], stream["avg_frame_rate"], frames) == (1280, 720, "24/1", 96) \
        and abs(duration - 4) < 1e-3
    return {"schema_version": 1, "format_version": "pcve_video_validation/1", "scene": cfg.SCENE, "case_id": case_id,
            "video": "video.mp4", "resolution": [stream["width"], stream["height"]], "fps": stream["r_frame_rate"],
            "duration_sec": duration, "frames": frames, "sha256": sha(video),
            "technical_probe_verified": technical,
            "full_decode_verified": decode.returncode == 0 and not decode.stderr.strip(),
            "content_unchanged": False, "visual_or_physics_acceptance": "new render; visual review pending",
            "native_validation": {"contract_probe": contract, "probe": probe}}


def prompt_record(record, fps):
    """The pcve_prompts/1 file that `--export-prompts` keeps unchanged for this catalog record."""
    item = {"schema_version": 1, "format_version": FORMAT_VERSION, "scene": cfg.SCENE, "case_id": record["catalog_case_id"],
            "kind": record["kind"], "source_case_id": "source", "availability": "available",
            "prompts": record["prompts"], "edit_dsl": None, "object_id": None, "applies_from_frame": None,
            "application_time_sec": None, "physics_override": {}, "physics_diff": {},
            "prompt_provenance": {"origin": "generated:" + relative(BUILDER), "text_modified": False}}
    if record["kind"] == "edit":
        frame = _applies_from_frame(record)
        item.update(edit_dsl=record["edit_dsl"], applies_from_frame=frame, application_time_sec=(frame - 1) / fps,
                    physics_override=record["physics_override"], physics_diff=record["physics_diff"])
    return item


def build(native, stage):
    from export_ground_truth import camera_for, export
    if stage.exists():
        raise FileExistsError(stage)
    catalog = load_catalog(BUILDER)
    records_by_case = {catalog["source"]["case_id"]: catalog["source"],
                       **{r["case_id"]: r for r in catalog["edits"].values()}}
    fps = _fps()
    stage.mkdir(parents=True)
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    entries, digests = [], {}
    for case in cfg.CASES:
        case_id = cfg.CATALOG[case]
        folder = native / case
        video = encode(folder)
        parts = merged_parts(folder)
        target = stage / "cases" / case_id
        digest = snapshot(video, target / "video.mp4")
        files = [folder / "render_metadata.json", folder / "replay_audit.json"]
        files += [cfg.native_case(case) / n for n in ("scenario_overrides.json", "physics_provenance.json", "physics_telemetry.json")]
        for p in files:
            snapshot(p, target / "native_metadata" / p.name)
        save(target / "native_metadata/render_parts.json", parts)
        snapshot(target / "native_metadata/scenario_overrides.json", target / "scenario_overrides.json")
        check = video_validation(target / "video.mp4", case_id)
        if not (check["technical_probe_verified"] and check["full_decode_verified"]):
            raise RuntimeError(f"{case_id}: video is not 1280x720 / 24 fps / 96 frames / 4 s or does not decode")
        save(target / "video_validation.json", check)
        prompts = prompt_record(records_by_case[case], fps)
        save(target / "prompts.json", prompts)
        save(target / "provenance.json", {
            "schema_version": 1, "format_version": "pcve_provenance/1", "scene": cfg.SCENE, "case_id": case_id,
            "kind": prompts["kind"], "native_case_id": case, "video_sha256": digest, "created_at": now,
            "native_render_dir": relative(folder), "native_metadata": f"cases/{case_id}/native_metadata",
            "native_case": relative(cfg.native_case(case)), "render_devices": parts["devices"],
            "scene_code": relative(CASE), "look": "appearance/look.py"})
        entries.append({
            "case_id": case_id, "native_case_id": case, "kind": prompts["kind"], "source_case_id": "source",
            "case_dir": f"cases/{case_id}", "status": "rendered_pending_review", "availability": "video_present",
            "video": f"cases/{case_id}/video.mp4", "video_sha256": digest,
            "media": {k: check[k] for k in ("resolution", "fps", "duration_sec", "frames", "sha256")},
            **{k: prompts[k] for k in ("prompts", "edit_dsl", "object_id", "applies_from_frame", "application_time_sec",
                                       "physics_override", "physics_diff")}})
        digests[case] = digest
    look = json.loads((native / "source/render_metadata.json").read_text())["environment"]
    save(stage / "inputs/native_input_locations.json", {
        "scene": cfg.SCENE, "kind": "native_input_locations",
        "native_render_dirs": [relative(native / c) for c in cfg.CASES],
        "scene_code": relative(CASE), "native_caches": "assets/scenes/spring_car_collision/native_cases/<case>",
        "look": "scripts/rigid_elastic/spring_car_collision/appearance/look.py", "look_assets": look["polyhaven_assets"]})
    save(stage / "suite_manifest.json", {
        "schema_version": 5, "format_version": "pcve_suite/1", "layout": LAYOUT, "scene": cfg.SCENE, "title": cfg.SCENE,
        "suite_name": cfg.SUITE_NAME, "interaction_category": cfg.CATEGORY, "suite_path": relative(FINAL),
        "source_count": 1, "edit_count": len(entries) - 1, "status": "rendered_pending_review",
        "source": entries[0], "edits": entries[1:],
        "metadata": {"scene_id": cfg.SCENE, "created_at": now, "look": "appearance/look.py",
                     "storage_type": "physical_files", "render_outputs": relative(native),
                     "inputs": [{"role": "native_input_locations", "path": "inputs/native_input_locations.json"}]}})
    (stage / "README.txt").write_text(
        f"PCVE suite: {cfg.SCENE}\nSource: cases/source/video.mp4; edits: cases/edit_*/video.mp4 ({len(entries) - 1}).\n"
        "Per case: video.mp4, prompts.json, provenance.json, video_validation.json, native_metadata/, "
        "scenario_overrides.json, ground_truth_transforms.json.\n"
        "Index: suite_manifest.json. Scene code: scripts/rigid_elastic/spring_car_collision.\n", encoding="utf-8")
    for case in cfg.CASES:
        print(json.dumps(export(case, stage, camera_for(case, stage, None))), flush=True)
    check_suite(stage)
    return digests


def publish(native, stage):
    check_suite(stage)
    archive = cfg.REPO / "archive/pcve_suites" / f"{cfg.SUITE_NAME}_before_{native.name}"
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
    entry = manifest["canonical_suites"][cfg.SUITE_NAME]
    entry.pop("revision", None)
    entry.update(target=relative(FINAL),
                 case_video_sha256={r["native_case_id"]: r["video_sha256"] for r in records},
                 case_video_path={r["native_case_id"]: r["video"] for r in records})
    manifest["data"]["native_renders"] = relative(native)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return entry


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--native", type=Path, required=True)
    p.add_argument("--staging", type=Path, help="suite staging folder (default <native>/suite_staging)")
    p.add_argument("--publish", action="store_true")
    a = p.parse_args()
    native = a.native.resolve()
    stage = (a.staging or native / "suite_staging").resolve()
    result = {"video_sha256": build(native, stage)}
    if a.publish:
        result.update(publish(native, stage))
        result["scene_manifest"] = update_scene_manifest(native)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
