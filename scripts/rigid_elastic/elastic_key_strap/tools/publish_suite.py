"""Assemble a video suite in the current PCVE suite format from finished renders of the current look.

    python3 scripts/rigid_elastic/elastic_key_strap/tools/publish_suite.py --native DIR [--suite NEW_DIR]
    python3 scripts/rigid_elastic/elastic_key_strap/tools/publish_suite.py --native DIR --publish [--target SUITE]

DIR is the output root of render_elastic_key_strap.py --out-root DIR for all six cases: realism/<case>/ with
frame_0001..0096.png or video.mp4, realism_provenance.json (or one realism_provenance_f*.json per frame range when a
case was rendered in parts), native_replay_audit.json and appearance_scene_audit.json. Each render must replay the
solve that is published with it (checked by the native_cache_sha256 of its record): the accepted solve for a
whole-clip case (scene_paths.cache_dir), and for a timed case DIR/physics/<case>/ (simulate_elastic_key_strap.py
--out-root DIR) or, without one, the published merged solve. Per case the frames are encoded when there is no video.mp4 (libx264
preset slow, crf 16, yuv420p, bt709, 24 fps), the provenance parts are merged and checked for one device type, one
setting and one code version, and the suite gets cases/<case_id>/video.mp4, native_metadata/ (the render records
and the solve's resolved_config, scenario_overrides and physics_audit), prompts.json (pcve_prompts/1, from
PCVE_SOURCE / PCVE_EDITS of build_pcve_elastic_key_strap.py), provenance.json (pcve_provenance/1),
video_validation.json (pcve_video_validation/1) and ground_truth_transforms.json (tools/export_ground_truth.py); a
timed case's merged solve is copied to inputs/native_timed/<case>/. The suite also gets suite_manifest.json
(pcve_suite/1), README.txt and inputs/native_input_locations.json. Every ground truth file must be
pcve_ground_truth/1. The standardization records of the case provenance.json files of the
published suite (--target) are carried into the new provenance.json files. Render outputs are only read.

Without --publish the suite is written to NEW_DIR, which must not exist (default:
renders/elastic_key_strap/suite_build/<suite>). With --publish the suite is built in DIR/suite_staging/<name> and checked (media,
ground truth format and clock, JSON, `--export-prompts --dry-run` unchanged); only then is it copied next to the
target, the target is renamed to <renders>/pcve_suites_archive/<name>_before_<UTC stamp>, the copy renamed into its
place, the timed cases' ground truth rewritten there (so it names the final inputs/native_timed/ path), and, for the
published suite, case_video_sha256 of scene_manifest.json updated. Prompts of a published suite are updated with
`build_pcve_elastic_key_strap.py --export-prompts`.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
CASE = HERE.parent
SCRIPTS = CASE.parents[1]
sys.path[:0] = [str(HERE), str(CASE), str(SCRIPTS)]
from scene_paths import DELIVERY, REPO, SCENE, SUITE_NAME, TIMED_CASES, cache_dir  # noqa: E402
from pcve_edit_catalog import FORMAT_VERSION, _applies_from_frame, _fps, load_catalog  # noqa: E402
from pcve_media_contract import require_video  # noqa: E402
from pcve_case_metadata import carried_provenance  # noqa: E402

BUILDER = CASE / f"build_pcve_{SCENE}.py"
FINAL = REPO / "renders/pcve_suites" / SUITE_NAME
BUILD = REPO / "renders" / CASE.name / "suite_build" / SUITE_NAME
LAYOUT = "cases/<case_id>/{video.mp4,prompts.json,provenance.json,video_validation.json,ground_truth_transforms.json}"
SAME = ("look", "native_cache", "native_cache_sha256", "render")
RENDER_RECORDS = ("native_replay_audit.json", "appearance_scene_audit.json")
SOLVE_RECORDS = ("resolved_config.json", "scenario_overrides.json", "physics_audit.json")
TIMED_SOLVE = ("simulation.npz", "trace_240hz.npz", "model.xml", *SOLVE_RECORDS)
GROUND_TRUTH_FORMAT = "pcve_ground_truth/1"


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".writing")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    digest = sha(dst)
    if digest != sha(src):
        raise RuntimeError(f"copy differs: {dst}")
    return digest


def relative(path):
    path = Path(path).resolve()
    return str(path.relative_to(REPO.resolve())) if REPO.resolve() in path.parents else str(path)


def merged_provenance(folder):
    """The render record of all 96 frames; parts rendered separately must agree on device type, settings and code."""
    whole = folder / "realism_provenance.json"
    parts = sorted(folder.glob("realism_provenance_f*.json"))
    if whole.is_file() and not parts:
        record = read(whole)
        if record["frames"] != [1, 96, 96]:
            raise RuntimeError(f"{folder}: provenance does not cover frames 1-96")
        return record
    records = [read(p) for p in parts]
    if not records:
        raise RuntimeError(f"{folder}: no realism_provenance")
    frames = sorted(f for r in records for f in r["frame_list"])
    if frames != list(range(1, 97)):
        raise RuntimeError(f"{folder}: frame parts do not cover 1-96 exactly once")
    per_card = ("host", "gpu", "cycles_devices")  # which card of the same model rendered a part

    def model(r):
        return (r["render"]["device"], (r["render"]["gpu"] or "CPU").split(",")[0].strip(),
                sorted({d["name"] for d in r["render"]["cycles_devices"]}))
    for r in records[1:]:
        for key in SAME:
            other = {k: v for k, v in r[key].items() if k not in per_card} if key == "render" else r[key]
            first = {k: v for k, v in records[0][key].items() if k not in per_card} if key == "render" else records[0][key]
            if other != first:
                raise RuntimeError(f"{folder}: frame parts differ in {key}")
        if model(r) != model(records[0]):
            raise RuntimeError(f"{folder}: frame parts were rendered on different device types")
    merged = dict(records[0])
    merged.update(frames=[1, 96, 96], frame_list=frames, parts=[p.name for p in parts],
                  render_hosts=sorted({r["render"]["host"] for r in records}),
                  render_gpus=sorted({r["render"]["gpu"] or "CPU" for r in records}))
    merged["replay_max_error"] = {k: max(r["replay_max_error"][k] for r in records) for k in records[0]["replay_max_error"]}
    return merged


def encode(folder, video):
    """Copy the case's video.mp4, or encode its 96 frames into the suite."""
    if (folder / "video.mp4").is_file():
        copy(folder / "video.mp4", video)
        return video
    frames = sorted(folder.glob("frame_*.png"))
    if [p.name for p in frames] != [f"frame_{i:04d}.png" for i in range(1, 97)]:
        raise RuntimeError(f"{folder}: expected frame_0001..0096.png")
    video.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-framerate", "24", "-i", str(folder / "frame_%04d.png"),
                    "-frames:v", "96", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
                    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                    "-movflags", "+faststart", str(video)], check=True)
    return video


def video_validation(video, case_id):
    contract = require_video(video)
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames:format=duration",
         "-of", "json", str(video)], capture_output=True, text=True, check=True).stdout)
    stream = probe["streams"][0]
    decode = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(video), "-f", "null", "-"],
                            capture_output=True, text=True)
    frames = int(stream["nb_read_frames"])
    return {"schema_version": 1, "format_version": "pcve_video_validation/1", "scene": SCENE, "case_id": case_id,
            "video": "video.mp4", "resolution": [int(stream["width"]), int(stream["height"])],
            "fps": stream["r_frame_rate"], "duration_sec": float(probe["format"]["duration"]), "frames": frames,
            "sha256": sha(video), "technical_probe_verified": frames == 96 and stream["r_frame_rate"] == "24/1",
            "full_decode_verified": decode.returncode == 0 and not decode.stderr.strip(),
            "content_unchanged": False, "visual_or_physics_acceptance": "new render; visual review pending",
            "native_validation": {"contract_probe": contract, "probe": probe}}


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


def carried(previous, case_id):
    """standardization record of a case of the suite being replaced."""
    path = previous / "cases" / case_id / "provenance.json" if previous else None
    if path is None or not path.is_file():
        return {}
    records = carried_provenance(path)
    if records:
        records["carried_from"] = {"file": relative(path), "sha256": sha(path)}
    return records


def build(native, suite, previous=None):
    if suite.exists():
        raise FileExistsError(f"{suite} exists; choose a new suite folder")
    catalog = load_catalog(BUILDER)
    records = [catalog["source"], *catalog["edits"].values()]
    missing = [r["case_id"] for r in records if not (native / "realism" / r["case_id"]).is_dir()]
    if missing:
        raise FileNotFoundError(f"{native} lacks {missing}")
    fps = _fps()
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    entries, look = [], None
    for record in records:
        native_id, case_id = record["case_id"], record["catalog_case_id"]
        render = native / "realism" / native_id
        timed = native_id in TIMED_CASES
        solve = native / "physics" / native_id
        if not (timed and (solve / "simulation.npz").is_file()):
            solve = cache_dir(native_id)
        provenance = merged_provenance(render)
        if provenance["native_cache_sha256"] != sha(solve / "simulation.npz"):
            raise RuntimeError(f"{native_id}: the render replays another solve than {solve}")
        folder = suite / "cases" / case_id
        video = encode(render, folder / "video.mp4")
        digest = sha(video)
        provenance["video"] = {"file": video.name, "sha256": digest,
                               "encoder": "ffmpeg libx264 preset slow crf 16 yuv420p bt709 24 fps"}
        write(folder / "native_metadata" / "realism_provenance.json", provenance)
        for name in RENDER_RECORDS:
            copy(render / name, folder / "native_metadata" / name)
        for name in SOLVE_RECORDS:
            copy(solve / name, folder / "native_metadata" / name)
        if timed:
            for name in TIMED_SOLVE:
                copy(solve / name, suite / "inputs" / "native_timed" / native_id / name)
        look = look or provenance.get("look")
        check = video_validation(video, case_id)
        if not (check["technical_probe_verified"] and check["full_decode_verified"]):
            raise RuntimeError(f"{case_id}: video fails the media contract")
        write(folder / "video_validation.json", check)
        prompts = prompt_record(record, fps)
        write(folder / "prompts.json", prompts)
        audit = read(solve / "physics_audit.json")
        case_record = {
            "schema_version": 1, "format_version": "pcve_provenance/1", "scene": SCENE, "case_id": case_id,
            "kind": record["kind"], "native_case_id": native_id, "video_sha256": digest, "created_at": now,
            "native_render_dir": relative(render), "native_metadata": f"cases/{case_id}/native_metadata",
            "native_solve": f"inputs/native_timed/{native_id}" if timed else relative(solve),
            "native_solve_sha256": sha(solve / "simulation.npz"), "solver": audit.get("solver"),
            "scene_code": relative(CASE), "look": provenance.get("look")}
        if timed:
            case_record.update(status="native_timed_physics_rendered", continuation=audit.get("continuation"))
        case_record.update(carried(previous, case_id))
        write(folder / "provenance.json", case_record)
        entries.append({
            "case_id": case_id, "native_case_id": native_id, "kind": record["kind"], "source_case_id": "source",
            "case_dir": f"cases/{case_id}", "status": "rendered_pending_review", "availability": "video_present",
            "video": f"cases/{case_id}/video.mp4", "video_sha256": digest,
            "ground_truth": f"cases/{case_id}/ground_truth_transforms.json",
            "media": {k: check[k] for k in ("resolution", "fps", "duration_sec", "frames", "sha256")},
            **{k: prompts[k] for k in ("prompts", "edit_dsl", "object_id", "applies_from_frame", "application_time_sec",
                                       "physics_override", "physics_diff")}})
    scene_audit = read(native / "realism" / "source" / "appearance_scene_audit.json")
    write(suite / "inputs" / "native_input_locations.json", {
        "scene": SCENE, "kind": "native_input_locations", "render_outputs": relative(native / "realism"),
        "native_caches": relative(cache_dir("source").parent) + "/<case>",
        "native_timed": {c: f"inputs/native_timed/{c}" for c in TIMED_CASES},
        "accepted_delivery": relative(DELIVERY), "scene_code": relative(CASE),
        "look": relative(CASE / "appearance/realism.py"),
        "look_assets": sorted({d["asset"] for d in scene_audit["dressing"]} | {scene_audit["light"]["world"]})})
    (suite / "README.txt").write_text(
        f"PCVE suite: {SCENE}\nSource: cases/source/video.mp4; edits: cases/edit_*/video.mp4 ({len(entries) - 1}).\n"
        "Per case: video.mp4, prompts.json, provenance.json, video_validation.json, native_metadata/, "
        "ground_truth_transforms.json.\nTimed edits: merged native solve in inputs/native_timed/<case>/.\n"
        f"Index: suite_manifest.json. Scene code: {relative(CASE)}.\n", encoding="utf-8")
    write(suite / "suite_manifest.json", {
        "schema_version": 5, "format_version": "pcve_suite/1", "layout": LAYOUT, "scene": SCENE, "title": SCENE,
        "suite_name": suite.name, "interaction_category": "rigid_elastic", "suite_path": relative(suite),
        "source_count": 1, "edit_count": len(entries) - 1, "status": "rendered_pending_review",
        "source": entries[0], "edits": entries[1:],
        "metadata": {"scene_id": SCENE, "created_at": now, "look": look, "storage_type": "physical_files",
                     "render_outputs": relative(native / "realism"),
                     "inputs": [{"role": "native_input_locations", "path": "inputs/native_input_locations.json"}]}})
    from export_ground_truth import export
    ground_truth = [export(r["case_id"], suite) for r in records]
    check_suite(suite, records)
    return {"suite": str(suite), "cases": {e["case_id"]: e["video_sha256"] for e in entries},
            "ground_truth": ground_truth}


def check_ground_truth(suite, records):
    for record in records:
        gt = read(suite / "cases" / record["catalog_case_id"] / "ground_truth_transforms.json")
        frames = gt.get("frames", [])
        if gt.get("format_version") != GROUND_TRUTH_FORMAT or gt.get("fps") != 24 or len(frames) != 96 or any(
                f["frame_index"] != i + 1 or abs(f["time_sec"] - i / 24) > 1e-9 for i, f in enumerate(frames)):
            raise RuntimeError(f"{record['catalog_case_id']}: ground truth is not {GROUND_TRUTH_FORMAT} on the 24 fps clock")


def check_suite(suite, records):
    """Every JSON file parses, every case has a compliant video and pcve_ground_truth/1 ground truth."""
    for p in suite.rglob("*.json"):
        read(p)
    for record in records:
        check = read(suite / "cases" / record["catalog_case_id"] / "video_validation.json")
        if not (check["technical_probe_verified"] and check["full_decode_verified"]):
            raise RuntimeError(f"{record['catalog_case_id']}: video fails the media contract")
    check_ground_truth(suite, records)


def update_scene_manifest(suite):
    path = CASE / "scene_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    entry = manifest["canonical_suites"][SUITE_NAME]
    index = read(suite / "suite_manifest.json")
    entry["case_video_sha256"] = {r["native_case_id"]: r["video_sha256"] for r in [index["source"], *index["edits"]]}
    temporary = path.with_name("." + path.name + ".writing")
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    return entry["case_video_sha256"]


def publish(native, target):
    """Build and check in staging, then swap it in place of the target; the target is never moved first."""
    from pcve_edit_catalog import export_prompts
    from export_ground_truth import export
    catalog = load_catalog(BUILDER)
    records = [catalog["source"], *catalog["edits"].values()]
    real = target.resolve() if target.exists() else target.parent.resolve() / target.name
    stage = native / "suite_staging" / real.name
    result = build(native, stage, previous=real if real.exists() else None)
    dry = export_prompts(BUILDER, stage, dry_run=True)
    if any(row["status"] != "unchanged" for row in dry["exported"]):
        raise RuntimeError("staging prompts differ from the builder")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = real.parent.parent / "pcve_suites_archive" / f"{real.name}_before_{stamp}"
    incoming = real.with_name("." + real.name + ".incoming")
    if archive.exists() or incoming.exists():
        raise FileExistsError(archive if archive.exists() else incoming)
    shutil.copytree(stage, incoming, symlinks=True)
    for p in stage.rglob("*"):
        if p.is_file() and sha(p) != sha(incoming / p.relative_to(stage)):
            raise RuntimeError(f"copy differs: {incoming / p.relative_to(stage)}")
    if real.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        os.rename(real, archive)
    os.rename(incoming, real)
    result["ground_truth"] = [export(c, real) for c in TIMED_CASES]
    check_suite(real, records)
    result.update(published=str(real), previous_suite=str(archive) if archive.exists() else None, staging=str(stage))
    if real == FINAL.resolve():
        result["scene_manifest_case_video_sha256"] = update_scene_manifest(real)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--native", type=Path, required=True, help="render_elastic_key_strap.py output root of all six cases")
    p.add_argument("--suite", type=Path, help="new suite folder (must not exist; default: renders/elastic_key_strap/suite_build/<suite>)")
    p.add_argument("--publish", action="store_true", help="build in DIR/suite_staging, check, then replace --target")
    p.add_argument("--target", type=Path, default=FINAL, help="suite replaced by --publish (default: the published suite)")
    a = p.parse_args()
    if a.publish:
        if a.suite:
            p.error("--suite and --publish exclude each other; --publish builds in DIR/suite_staging")
        result = publish(a.native.resolve(), a.target.expanduser().absolute())
    else:
        suite = (a.suite or BUILD).resolve()
        target = a.target.expanduser().absolute()
        previous = target.resolve() if target.exists() and target.resolve() != suite else None
        result = build(a.native.resolve(), suite, previous)
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
