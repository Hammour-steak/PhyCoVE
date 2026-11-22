"""Assemble a video suite in the current PCVE suite format from finished renders of the current look.

    python3 scripts/rigid_elastic/silicone_block_chain/tools/publish_suite.py --native DIR --suite NEW_DIR
    python3 scripts/rigid_elastic/silicone_block_chain/tools/publish_suite.py --native DIR --publish [--target SUITE]

DIR is the output root of render_silicone_block_chain.py --out-root DIR for all six cases: realism/<case>/ with
frame_0001..0096.png or video.mp4 and realism_provenance.json. A case rendered from a solve of its own (--native-dir:
the re-solved source and the timed edit) also has realism/<case>/native/ (simulation.npz, config.json, bake_report.json);
every other case must replay its accepted cache (assets accepted_solves/physics/<case>). The timed edit must branch from the
source solve of the same suite: its samples up to the edit step are compared with it bit for bit.

Per case the suite gets cases/<case_id>/video.mp4 (the render's video.mp4, else its 96 frames encoded as
appearance/realism.py does: libx264 crf 16 yuv420p 24 fps), native_metadata/ (realism_provenance.json, the solver report
config.json and, for a solve of its own, simulation.npz and bake_report.json), prompts.json (pcve_prompts/1 from
PCVE_SOURCE / PCVE_EDITS of build_pcve_silicone_block_chain.py), provenance.json (pcve_provenance/1),
video_validation.json (pcve_video_validation/1) and ground_truth_transforms.json (tools/export_ground_truth.py, which
writes pcve_ground_truth/1); the suite gets suite_manifest.json (pcve_suite/1), README.txt and
inputs/native_input_locations.json. Render outputs are only read.

Without --publish the suite is written to NEW_DIR, which must not exist. With --publish it is built in
DIR/suite_staging/<name> and checked (media, ground truth
format and clock, JSON, `--export-prompts --dry-run` unchanged); only then is it copied next to the target, the target
renamed to renders/pcve_suites_archive/<name>_before_<UTC stamp> and the copy renamed into its place; for the published
suite, case_video_sha256 of scene_manifest.json is updated. Prompts of a published suite are updated with
`build_pcve_silicone_block_chain.py --export-prompts`.
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
sys.path[:0] = [str(CASE), str(CASE.parents[1])]
from scene_paths import CASES, DELIVERY, REPO, SCENE, SUITE_NAME, TIMED_CASES, cache, catalog_id, packed  # noqa: E402
from pcve_edit_catalog import FORMAT_VERSION, _applies_from_frame, _fps, load_catalog  # noqa: E402
from pcve_media_contract import require_video  # noqa: E402

BUILDER = CASE / f"build_pcve_{SCENE}.py"
FINAL = REPO / "renders/pcve_suites" / SUITE_NAME
LAYOUT = "cases/<case_id>/{video.mp4,prompts.json,provenance.json,video_validation.json,ground_truth_transforms.json}"
OWN_SOLVE = ("simulation.npz", "config.json", "bake_report.json")
GROUND_TRUTH_FORMAT = "pcve_ground_truth/1"
SOLVE_KEYS = ("states", "ball_spin_rad", "rigid_velocity", "elastic_positions")


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


def solve_of(render, case):
    """The solve folder a render replays: its own native/ folder, else the accepted cache of the case."""
    own = render / "native"
    if (own / "simulation.npz").is_file():
        return own, True
    if case not in CASES:
        raise FileNotFoundError(f"{render}: a timed case needs its solve in native/ (render_silicone_block_chain.py --native-dir)")
    return cache(case).parent, False


def check_render(render, case, solve, own):
    provenance = read(render / "realism_provenance.json")
    if provenance.get("case") != case or provenance.get("frames") != [1, 96, 96] or provenance.get("look") != "realism":
        raise RuntimeError(f"{render}: realism_provenance.json is not a realism render of {case}, frames 1-96")
    digest = sha(solve / "simulation.npz")
    if "native_cache_sha256" in provenance:
        replays = provenance["native_cache_sha256"] == digest
    else:                                        # render records without the cache hash name the accepted packed scene
        replays = not own and provenance["saved_scene_sha256"] == sha(packed(case))
    if not replays or (own and read(solve / "bake_report.json")["native_cache_sha256"] != digest):
        raise RuntimeError(f"{render}: the render does not replay {solve}")
    return provenance


def encode(render, video):
    """Copy the case's video.mp4, or encode its 96 frames into the suite."""
    if (render / "video.mp4").is_file():
        copy(render / "video.mp4", video)
        return video
    frames = sorted(render.glob("frame_*.png"))
    if [p.name for p in frames] != [f"frame_{i:04d}.png" for i in range(1, 97)]:
        raise RuntimeError(f"{render}: expected frame_0001..0096.png")
    video.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-framerate", "24", "-i", str(render / "frame_%04d.png"),
                    "-frames:v", "96", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(video)], check=True)
    return video


def video_validation(video, case_id):
    contract = require_video(video)
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,codec_tag_string,pix_fmt,width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames:format=duration",
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
            "codec": {k: stream.get(k) for k in ("codec_name", "codec_tag_string", "pix_fmt")},
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


def check_branch(solves):
    """The timed edit's samples up to its edit step equal the source solve of the same suite, bit for bit."""
    import numpy as np
    if not any(c in solves for c in TIMED_CASES):
        return {}
    with np.load(solves["source"] / "simulation.npz") as source:
        reference = {k: source[k] for k in SOLVE_KEYS}
    result = {}
    for case in TIMED_CASES:
        frame = read(solves[case] / "config.json")["timed_edit"]["frame"]
        edge = 4 * (frame - 1) + 1
        with np.load(solves[case] / "simulation.npz") as timed:
            difference = {k: float(np.abs(timed[k][:edge] - reference[k][:edge]).max()) for k in SOLVE_KEYS}
        if any(difference.values()):
            raise RuntimeError(f"{case} does not branch from this suite's source solve: {difference}")
        result[case] = {"samples_compared": edge, "max_abs_difference": difference}
    return result


def build(native, suite):
    if suite.exists():
        raise FileExistsError(f"{suite} exists; choose a new suite folder")
    catalog = load_catalog(BUILDER)
    records = [catalog["source"], *catalog["edits"].values()]
    missing = [r["case_id"] for r in records if not (native / "realism" / r["case_id"]).is_dir()]
    if missing:
        raise FileNotFoundError(f"{native} lacks realism/{missing}")
    fps = _fps()
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    solves = {}
    for record in records:
        render = native / "realism" / record["case_id"]
        solves[record["case_id"]] = solve_of(render, record["case_id"])
    branch = check_branch({case: folder for case, (folder, _) in solves.items()})
    entries, own_solves = [], {}
    for record in records:
        native_id, case_id = record["case_id"], record["catalog_case_id"]
        render = native / "realism" / native_id
        solve, own = solves[native_id]
        provenance = check_render(render, native_id, solve, own)
        folder = suite / "cases" / case_id
        video = encode(render, folder / "video.mp4")
        digest = sha(video)
        if provenance.get("video", {}).get("sha256") not in (None, digest):
            raise RuntimeError(f"{render}: video.mp4 is not the video of its render record")
        provenance["video"] = {"file": video.name, "sha256": digest, "encoder": "ffmpeg libx264 crf 16 yuv420p 24 fps"}
        metadata = folder / "native_metadata"
        write(metadata / "realism_provenance.json", provenance)
        for name in OWN_SOLVE if own else ("config.json",):
            copy(solve / name, metadata / name)
        if own:
            own_solves[native_id] = metadata
        check = video_validation(video, case_id)
        if not (check["technical_probe_verified"] and check["full_decode_verified"]):
            raise RuntimeError(f"{case_id}: video fails the media contract")
        write(folder / "video_validation.json", check)
        prompts = prompt_record(record, fps)
        write(folder / "prompts.json", prompts)
        config = read(solve / "config.json")
        case_record = {
            "schema_version": 1, "format_version": "pcve_provenance/1", "scene": SCENE, "case_id": case_id,
            "kind": record["kind"], "native_case_id": native_id, "video_sha256": digest, "created_at": now,
            "native_render_dir": relative(render), "native_metadata": f"cases/{case_id}/native_metadata",
            "native_solve": f"cases/{case_id}/native_metadata" if own else relative(solve),
            "native_solve_sha256": config["cache_sha256"], "solver": config.get("solver"), "solver_host": config.get("solver_host"),
            "scene_code": relative(CASE), "look": "appearance/realism.py"}
        if config.get("timed_edit"):
            case_record.update(status="native_timed_physics_rendered", timed_edit=config["timed_edit"],
                               branch_check=branch.get(native_id))
        write(folder / "provenance.json", case_record)
        entries.append({
            "case_id": case_id, "native_case_id": native_id, "kind": record["kind"], "source_case_id": "source",
            "case_dir": f"cases/{case_id}", "status": "rendered_pending_review", "availability": "video_present",
            "video": f"cases/{case_id}/video.mp4", "video_sha256": digest,
            "ground_truth": f"cases/{case_id}/ground_truth_transforms.json",
            "media": {k: check[k] for k in ("resolution", "fps", "duration_sec", "frames", "sha256")},
            **{k: prompts[k] for k in ("prompts", "edit_dsl", "object_id", "applies_from_frame", "application_time_sec",
                                       "physics_override", "physics_diff")}})
    write(suite / "inputs" / "native_input_locations.json", {
        "scene": SCENE, "kind": "native_input_locations", "render_outputs": relative(native / "realism"),
        "accepted_caches": relative(cache("source").parent.parent) + "/<case>",
        "packed_scenes": relative(packed("source").parent) + "/<case>.blend",
        "own_solves": {c: f"cases/{catalog_id(c)}/native_metadata" for c in own_solves},
        "accepted_delivery": relative(DELIVERY), "scene_code": relative(CASE),
        "look": relative(CASE / "appearance/realism.py"),
        "look_assets": [f"assets/polyhaven/{i}" for i in ("small_workshop", "white_maple_veneer", "ash_veneer")]})
    (suite / "README.txt").write_text(
        f"PCVE suite: {SCENE}\nSource: cases/source/video.mp4; edits: cases/edit_*/video.mp4 ({len(entries) - 1}).\n"
        "Per case: video.mp4, prompts.json, provenance.json, video_validation.json, native_metadata/, "
        "ground_truth_transforms.json.\nSolves rendered outside the accepted delivery (simulation.npz, config.json, "
        "bake_report.json): cases/<case>/native_metadata/.\n"
        f"Index: suite_manifest.json. Scene code: {relative(CASE)}.\n", encoding="utf-8")
    write(suite / "suite_manifest.json", {
        "schema_version": 5, "format_version": "pcve_suite/1", "layout": LAYOUT, "scene": SCENE, "title": SCENE,
        "suite_name": suite.name, "interaction_category": "rigid_elastic", "suite_path": relative(suite),
        "source_count": 1, "edit_count": len(entries) - 1, "status": "rendered_pending_review",
        "source": entries[0], "edits": entries[1:],
        "metadata": {"scene_id": SCENE, "created_at": now, "look": "appearance/realism.py", "storage_type": "physical_files",
                     "render_outputs": relative(native / "realism"),
                     "inputs": [{"role": "native_input_locations", "path": "inputs/native_input_locations.json"}]}})
    command = [sys.executable, str(HERE / "export_ground_truth.py"), "--suite", str(suite),
               "--native", *[f"{c}={own_solves[c]}" if c in own_solves else f"{c}=accepted" for c in (r["case_id"] for r in records)]]
    subprocess.run(command, check=True)
    check_suite(suite, records)
    return {"suite": str(suite), "cases": {e["case_id"]: e["video_sha256"] for e in entries}, "branch_check": branch}


def check_suite(suite, records):
    """Every JSON file parses; every case has a compliant video and pcve_ground_truth/1 ground truth on the 24 fps clock."""
    for p in suite.rglob("*.json"):
        read(p)
    for record in records:
        folder = suite / "cases" / record["catalog_case_id"]
        check = read(folder / "video_validation.json")
        if not (check["technical_probe_verified"] and check["full_decode_verified"]) or check["sha256"] != sha(folder / "video.mp4"):
            raise RuntimeError(f"{record['catalog_case_id']}: video fails the media contract")
        gt = read(folder / "ground_truth_transforms.json")
        frames = gt.get("frames", [])
        if gt.get("format_version") != GROUND_TRUTH_FORMAT or gt.get("fps") != 24 or len(frames) != 96 or any(
                f["frame_index"] != i + 1 or abs(f["time_sec"] - i / 24) > 1e-9 for i, f in enumerate(frames)):
            raise RuntimeError(f"{record['catalog_case_id']}: ground truth is not {GROUND_TRUTH_FORMAT} on the 24 fps clock")


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
    catalog = load_catalog(BUILDER)
    records = [catalog["source"], *catalog["edits"].values()]
    real = target.resolve() if target.exists() else target.parent.resolve() / target.name
    stage = native / "suite_staging" / real.name
    result = build(native, stage)
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
    check_suite(real, records)
    result.update(published=str(real), previous_suite=str(archive) if archive.exists() else None, staging=str(stage))
    if real == FINAL.resolve():
        result["scene_manifest_case_video_sha256"] = update_scene_manifest(real)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--native", type=Path, required=True, help="render_silicone_block_chain.py output root of all six cases")
    p.add_argument("--suite", type=Path, help="new suite folder (must not exist)")
    p.add_argument("--publish", action="store_true", help="build in DIR/suite_staging, check, then replace --target")
    p.add_argument("--target", type=Path, default=FINAL, help="suite replaced by --publish (default: the published suite)")
    a = p.parse_args()
    if a.publish:
        if a.suite:
            p.error("--suite and --publish exclude each other; --publish builds in DIR/suite_staging")
        result = publish(a.native.resolve(), a.target.expanduser().absolute())
    else:
        if a.suite is None:
            p.error("pass --suite NEW_DIR, or --publish to replace --target")
        suite = a.suite.resolve()
        result = build(a.native.resolve(), suite)
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
