"""Assemble a video suite in the current PCVE suite format from finished renders of all six cases.

    .venv-rigid-elastic/bin/python scripts/rigid_elastic/picnic_ground_blanket/tools/publish_suite.py --delivery DIR --suite NEW_DIR
    .venv-rigid-elastic/bin/python scripts/rigid_elastic/picnic_ground_blanket/tools/publish_suite.py --delivery DIR --publish [--target SUITE]

DIR is the output root of build_pcve_picnic_ground_blanket.py (--out): DIR/<case>/render/ is a render packaged by
tools/finalize.py (video.mp4, render_report.json, simulation_config.json, simulation_report.json and the render
audits), and DIR/<case>/simulation/ the solve of a case that was solved anew. A render must replay its solve (the
physics_cache_sha256 of its render_report.json): DIR/<case>/simulation/cache.npz when present, else the accepted
state of the asset store (assets/scenes/picnic_ground_blanket/native/<case>/). The timed edit has no accepted state,
so it needs DIR/mass_double_at_frame_12/simulation/ (simulate --source-cache), and its frames before the edit must
equal the source solve of the same suite bit for bit.

Per case the suite gets cases/<case_id>/video.mp4, video_validation.json (pcve_video_validation/1), prompts.json
(pcve_prompts/1, from PCVE_SOURCE / PCVE_EDITS of build_pcve_picnic_ground_blanket.py), ground_truth_transforms.json
(tools/export_ground_truth.py, pcve_ground_truth/1), provenance.json (pcve_provenance/1) and native_metadata/ (the
render records and the solver's simulation_config.json / simulation_report.json, plus state_handoff.json of the timed
edit); the suite gets suite_manifest.json (pcve_suite/1), README.txt and inputs/native_input_locations.json. Every
ground truth file must be pcve_ground_truth/1 on the 24 fps clock, otherwise nothing is published. The
standardization records of the case provenance.json files of the suite being replaced
(--target) are carried into the new ones. Renders and solves are only read.

Without --publish the suite is written to NEW_DIR, which must not exist. With --publish it is built in
DIR/suite_staging/<name> and checked (media, ground truth format and clock, JSON, `--export-prompts --dry-run`
unchanged); only then is it copied next to the target, the target renamed to
renders/pcve_suites_archive/<name>_before_<UTC stamp> and the copy renamed into its place; for the published suite
the case_video_sha256 of scene_manifest.json is updated. Prompts of a published suite are updated with
`build_pcve_picnic_ground_blanket.py --export-prompts`. Needs numpy and ffmpeg/ffprobe.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parents[1]
REPO = CASE_DIR.parents[2]
for _path in (CASE_DIR, REPO / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from pcve_edit_catalog import FORMAT_VERSION, _applies_from_frame, _fps, load_catalog  # noqa: E402
from pcve_media_contract import require_video  # noqa: E402
from pcve_case_metadata import carried_provenance  # noqa: E402
from scene_inputs import ASSETS, CATALOG, SCENE, TIMED_CASES, native  # noqa: E402
from scene_paths import SUITE  # noqa: E402
from tools.export_ground_truth import write as write_ground_truth  # noqa: E402

BUILDER = CASE_DIR / f"build_pcve_{SCENE}.py"
MANIFEST_PATH = CASE_DIR / "scene_manifest.json"
FINAL = REPO / "renders/pcve_suites" / SUITE
LAYOUT = "cases/<case_id>/{video.mp4,prompts.json,provenance.json,video_validation.json,ground_truth_transforms.json}"
RENDER_RECORDS = ("render_report.json", "evaluated_surface_audit.json", "execution_provenance.json", "encoding_provenance.json")
SOLVE_RECORDS = ("simulation_config.json", "simulation_report.json", "state_handoff.json")
STATE_ARRAYS = ("solid_positions", "solid_velocities", "cloth_positions", "cloth_velocities", "body_transforms", "body_velocities")
GROUND_TRUTH_FORMAT = "pcve_ground_truth/1"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".writing")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def copy(src, dst):
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if sha(dst) != sha(src):
        raise RuntimeError(f"copy differs: {dst}")
    return dst


def relative(path):
    path = Path(path).resolve()
    return str(path.relative_to(REPO.resolve())) if REPO.resolve() in path.parents else str(path)


def solve_of(delivery, case):
    """The solve a case's render replays: DIR/<case>/simulation when solved anew, else the accepted state."""
    own = delivery / case / "simulation"
    if (own / "cache.npz").is_file():
        return own
    if case in TIMED_CASES:
        raise FileNotFoundError(f"{own}: the timed edit needs its solve (simulate --source-cache)")
    return native(case)


def check_render(render, case, solve):
    report = read(render / "render_report.json")
    if report.get("case") != case or report.get("rendered_frames") != list(range(1, 97)):
        raise RuntimeError(f"{render}: render_report.json is not a full 96-frame render of {case}")
    if report["physics_cache_sha256"] != sha(solve / "cache.npz"):
        raise RuntimeError(f"{render}: the render replays another solve than {solve}")
    if not report["evaluated_surface_verified"] or report["max_surface_replay_error_m"] > 2e-6 or report["surface_amplification"] != 1.0:
        raise RuntimeError(f"{render}: cloth replay audit failed")
    if read(render / "simulation_config.json") != read(solve / "simulation_config.json"):
        raise RuntimeError(f"{render}: the render's native configuration differs from {solve}")
    return report


def check_branch(solves):
    """The timed edit continues from the source solve of the same suite: frames before the edit are bit-identical."""
    import numpy as np
    result = {}
    for case in TIMED_CASES:
        config = read(solves[case] / "simulation_config.json")
        frame = config["timed_edit"]["frame"]
        source_cache = solves["source"] / "cache.npz"
        if config["timed_edit"]["source_cache_sha256"] != sha(source_cache):
            raise RuntimeError(f"{case} did not continue from this suite's source solve {source_cache}")
        with np.load(solves[case] / "cache.npz") as timed, np.load(source_cache) as source:
            difference = {k: float(np.abs(timed[k][:frame - 1] - source[k][:frame - 1]).max()) for k in STATE_ARRAYS}
        if any(difference.values()):
            raise RuntimeError(f"{case}: frames before the edit differ from the source solve: {difference}")
        handoff = read(solves[case] / "state_handoff.json")
        if not handoff["verified"] or max(handoff["max_abs_error"].values()) >= 1e-8:
            raise RuntimeError(f"{case}: state hand-off not verified")
        result[case] = {"frames_compared": frame - 1, "max_abs_difference": difference, "state_handoff_max_abs": handoff["max_abs_error"]}
    return result


def video_validation(video, case_id, acceptance):
    contract = require_video(video)
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,codec_tag_string,pix_fmt,width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames:format=duration",
         "-of", "json", str(video)], capture_output=True, text=True, check=True).stdout)
    stream = probe["streams"][0]
    decode = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(video), "-f", "null", "-"], capture_output=True, text=True)
    frames = int(stream["nb_read_frames"])
    return {"schema_version": 1, "format_version": "pcve_video_validation/1", "scene": SCENE, "case_id": case_id,
            "video": "video.mp4", "resolution": [int(stream["width"]), int(stream["height"])],
            "fps": stream["r_frame_rate"], "duration_sec": float(probe["format"]["duration"]), "frames": frames,
            "sha256": sha(video), "technical_probe_verified": frames == 96 and stream["r_frame_rate"] == "24/1",
            "full_decode_verified": decode.returncode == 0 and not decode.stderr.strip(),
            "content_unchanged": False, "visual_or_physics_acceptance": acceptance,
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


def carried(previous, case_id):
    """standardization record of a case of the suite being replaced."""
    path = previous / "cases" / case_id / "provenance.json" if previous else None
    if path is None or not path.is_file():
        return {}
    records = carried_provenance(path)
    if records:
        records["carried_from"] = {"file": relative(path), "sha256": sha(path)}
    return records


def build(delivery, suite, previous=None):
    if suite.exists():
        raise FileExistsError(f"{suite} exists; choose a new suite folder")
    catalog = load_catalog(BUILDER)
    records = [catalog["source"], *catalog["edits"].values()]
    missing = [r["case_id"] for r in records if not (delivery / r["case_id"] / "render" / "video.mp4").is_file()]
    if missing:
        raise FileNotFoundError(f"{delivery} lacks <case>/render/video.mp4 for {missing} (run tools/finalize.py)")
    fps = _fps()
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    solves = {r["case_id"]: solve_of(delivery, r["case_id"]) for r in records}
    branch = check_branch(solves)
    entries = []
    for record in records:
        case, case_id = record["case_id"], record["catalog_case_id"]
        render, solve = delivery / case / "render", solves[case]
        report = check_render(render, case, solve)
        folder = suite / "cases" / case_id
        video = copy(render / "video.mp4", folder / "video.mp4")
        digest = sha(video)
        metadata = folder / "native_metadata"
        for name in RENDER_RECORDS:
            if (render / name).is_file():
                copy(render / name, metadata / name)
        for name in SOLVE_RECORDS:
            if (solve / name).is_file():
                copy(solve / name, metadata / name)
        timed = case in TIMED_CASES
        acceptance = ("native timed continuation from the source state and a full 96-frame render; visual review pending" if timed
                      else "new render of the native state; visual review pending")
        check = video_validation(video, case_id, acceptance)
        if not (check["technical_probe_verified"] and check["full_decode_verified"]):
            raise RuntimeError(f"{case_id}: video fails the media contract")
        write(folder / "video_validation.json", check)
        prompts = prompt_record(record, fps)
        write(folder / "prompts.json", prompts)
        write_ground_truth(case, folder / "ground_truth_transforms.json", solve)
        config = read(solve / "simulation_config.json")
        case_record = {
            "schema_version": 1, "format_version": "pcve_provenance/1", "scene": SCENE, "case_id": case_id,
            "kind": record["kind"], "native_case_id": case, "video_sha256": digest, "created_at": now,
            "native_render_dir": relative(render), "native_metadata": f"cases/{case_id}/native_metadata",
            "native_solve": relative(solve), "native_solve_sha256": report["physics_cache_sha256"], "solver": config.get("solver"),
            "renderer": "appearance/render_replay.py (look.py, far_meadow.py)", "samples": report.get("samples"),
            "tuft_layout_sha256": report.get("appearance", {}).get("edge_grass", {}).get("tuft_layout_sha256"),
            "scene_code": relative(CASE_DIR)}
        if timed:
            case_record.update(status="native_timed_physics_rendered", timed_edit=config["timed_edit"], branch_check=branch[case])
        case_record.update(carried(previous, case_id))
        write(folder / "provenance.json", case_record)
        entries.append({
            "case_id": case_id, "native_case_id": case, "kind": record["kind"], "source_case_id": "source",
            "case_dir": f"cases/{case_id}", "status": "rendered_pending_review", "availability": "video_present",
            "video": f"cases/{case_id}/video.mp4", "video_sha256": digest,
            "ground_truth": f"cases/{case_id}/ground_truth_transforms.json",
            "media": {k: check[k] for k in ("resolution", "fps", "duration_sec", "frames", "sha256")},
            **{k: prompts[k] for k in ("prompts", "edit_dsl", "object_id", "applies_from_frame", "application_time_sec",
                                       "physics_override", "physics_diff")}})
    write(suite / "inputs" / "native_input_locations.json", {
        "scene": SCENE, "kind": "native_input_locations", "delivery": relative(delivery),
        "native_states": {r["case_id"]: relative(solves[r["case_id"]]) for r in records},
        "packed_scene": relative(ASSETS / "packed_scene.blend"), "scene_code": relative(CASE_DIR),
        "look": relative(CASE_DIR / "appearance/look.py")})
    (suite / "README.txt").write_text(
        f"PCVE suite: {SCENE}\nSource: cases/source/video.mp4; edits: cases/edit_*/video.mp4 ({len(entries) - 1}).\n"
        "Per case: video.mp4, prompts.json, provenance.json, video_validation.json, ground_truth_transforms.json, "
        "native_metadata/ (render and solver records).\n"
        f"Index: suite_manifest.json. Native states: inputs/native_input_locations.json. Scene code: {relative(CASE_DIR)}.\n",
        encoding="utf-8")
    write(suite / "suite_manifest.json", {
        "schema_version": 5, "format_version": "pcve_suite/1", "layout": LAYOUT, "scene": SCENE, "title": SCENE,
        "suite_name": suite.name, "interaction_category": "rigid_elastic", "suite_path": relative(suite),
        "source_count": 1, "edit_count": len(entries) - 1, "status": "rendered_pending_review",
        "source": entries[0], "edits": entries[1:],
        "metadata": {"scene_id": SCENE, "created_at": now, "storage_type": "physical_files", "delivery": relative(delivery),
                     "inputs": [{"role": "native_input_locations", "path": "inputs/native_input_locations.json"}]}})
    check_suite(suite, records)
    return {"suite": str(suite), "cases": {e["case_id"]: e["video_sha256"] for e in entries}, "branch_check": branch}


def check_suite(suite, records):
    """Every JSON file parses; every case has a compliant video and pcve_ground_truth/1 ground truth on the 24 fps clock."""
    for path in suite.rglob("*.json"):
        read(path)
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
    manifest = read(MANIFEST_PATH)
    entry = manifest["canonical_suites"][SUITE]
    index = read(suite / "suite_manifest.json")
    entry["case_video_sha256"] = {r["native_case_id"]: r["video_sha256"] for r in [index["source"], *index["edits"]]}
    temporary = MANIFEST_PATH.with_name("." + MANIFEST_PATH.name + ".writing")
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(MANIFEST_PATH)
    return entry["case_video_sha256"]


def publish(delivery, target):
    """Build and check in staging, then swap it in place of the target; the target is never moved first."""
    from pcve_edit_catalog import export_prompts
    catalog = load_catalog(BUILDER)
    records = [catalog["source"], *catalog["edits"].values()]
    real = target.resolve() if target.exists() else target.parent.resolve() / target.name
    stage = delivery / "suite_staging" / real.name
    result = build(delivery, stage, previous=real if real.exists() else None)
    dry = export_prompts(BUILDER, stage, dry_run=True)
    if any(row["status"] != "unchanged" for row in dry["exported"]):
        raise RuntimeError("staging prompts differ from the builder")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = real.parent.parent / "pcve_suites_archive" / f"{real.name}_before_{stamp}"
    incoming = real.with_name("." + real.name + ".incoming")
    if archive.exists() or incoming.exists():
        raise FileExistsError(archive if archive.exists() else incoming)
    shutil.copytree(stage, incoming, symlinks=True)
    for path in stage.rglob("*"):
        if path.is_file() and sha(path) != sha(incoming / path.relative_to(stage)):
            raise RuntimeError(f"copy differs: {incoming / path.relative_to(stage)}")
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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--delivery", type=Path, required=True, help="build_pcve output root: <case>/render (and <case>/simulation)")
    parser.add_argument("--suite", type=Path, help="new suite folder (must not exist)")
    parser.add_argument("--publish", action="store_true", help="build in DIR/suite_staging, check, then replace --target")
    parser.add_argument("--target", type=Path, default=FINAL, help="suite replaced by --publish (default: the published suite)")
    args = parser.parse_args()
    if args.publish:
        if args.suite:
            parser.error("--suite and --publish exclude each other; --publish builds in DIR/suite_staging")
        result = publish(args.delivery.resolve(), args.target.expanduser().absolute())
    else:
        if args.suite is None:
            parser.error("pass --suite NEW_DIR, or --publish to replace --target")
        suite = args.suite.resolve()
        target = args.target.expanduser().absolute()
        previous = target.resolve() if target.exists() and target.resolve() != suite else None
        result = build(args.delivery.resolve(), suite, previous)
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
