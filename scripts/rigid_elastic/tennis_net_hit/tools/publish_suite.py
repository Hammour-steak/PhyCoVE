"""Assemble a suite from per-case render outputs in the current PCVE suite format.

    python3 scripts/rigid_elastic/tennis_net_hit/tools/publish_suite.py --renders DIR [--suite DIR]

<renders>/<case>/ holds video.mp4 with realism_provenance.json and render_setup_*.json beside it
(render_tennis_net_hit.py or tools/render_split.py). Per case the suite gets video.mp4,
native_metadata/ (those JSON files), prompts.json (pcve_prompts/1, from PCVE_SOURCE / PCVE_EDITS of
build_pcve_tennis_net_hit.py), provenance.json (pcve_provenance/1) and video_validation.json
(pcve_video_validation/1); the suite gets suite_manifest.json (pcve_suite/1), README.txt and
inputs/native_input_locations.json. Ground truth is written afterwards by
tools/export_ground_truth.py (inside Blender). An existing suite is never overwritten; prompts of a
published suite are updated with `build_pcve_tennis_net_hit.py --export-prompts`.
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
sys.path.insert(0, str(SCRIPTS))
from pcve_edit_catalog import FORMAT_VERSION, _applies_from_frame, _fps, load_catalog  # noqa: E402
from pcve_media_contract import require_video  # noqa: E402

SCENE = "tennis_net_hit"
BUILDER = SCENE_DIR / f"build_pcve_{SCENE}.py"
SUITE = REPO / f"renders/pcve_suites/pcve_{SCENE}_suite"
LAYOUT = "cases/<case_id>/{video.mp4,prompts.json,provenance.json,video_validation.json}"


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


def build(renders, suite, look):
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
        write(folder / "provenance.json", {
            "schema_version": 1, "format_version": "pcve_provenance/1", "scene": SCENE, "case_id": case,
            "kind": record["kind"], "native_case_id": native, "video_sha256": digest, "created_at": now,
            "native_render_dir": relative(source_dir), "native_metadata": f"cases/{case}/native_metadata",
            "render_cache_sha256": read(source_dir / "realism_provenance.json")["render_cache_sha256"],
            "scene_code": relative(SCENE_DIR), "look": look})
        entries.append({
            "case_id": case, "native_case_id": native, "kind": record["kind"], "source_case_id": "source",
            "case_dir": f"cases/{case}", "status": "rendered_pending_review", "availability": "video_present",
            "video": f"cases/{case}/video.mp4", "video_sha256": digest,
            "media": {k: check[k] for k in ("resolution", "fps", "duration_sec", "frames", "sha256")},
            **{k: prompts[k] for k in ("prompts", "edit_dsl", "object_id", "applies_from_frame", "application_time_sec",
                                       "physics_override", "physics_diff")}})
    write(suite / "inputs" / "native_input_locations.json", {
        "scene": SCENE, "kind": "native_input_locations",
        "native_delivery": "renders/tennis_net_hit/accepted",
        "render_caches": "renders/tennis_net_hit/accepted/physics/<case>/ (render_cache.npz and "
                         "qualification.json, members of worker_tars/<worker>/<case>_artifacts.tar; index <case>_files.json)",
        "packed_scene": "assets/scenes/tennis_net_hit/inputs/scene.blend",
        "render_outputs": relative(renders), "scene_code": relative(SCENE_DIR)})
    (suite / "README.txt").write_text(
        f"PCVE suite: {SCENE}\nSource: cases/source/video.mp4; edits: cases/edit_*/video.mp4 ({len(entries) - 1}).\n"
        "Per case: video.mp4, prompts.json, provenance.json, video_validation.json, native_metadata/, "
        "ground_truth_transforms.json.\nIndex: suite_manifest.json. Scene code: scripts/rigid_elastic/tennis_net_hit.\n",
        encoding="utf-8")
    write(suite / "suite_manifest.json", {
        "schema_version": 5, "format_version": "pcve_suite/1", "layout": LAYOUT, "scene": SCENE, "title": SCENE,
        "suite_name": suite.name, "interaction_category": "rigid_elastic", "suite_path": relative(suite),
        "source_count": 1, "edit_count": len(entries) - 1, "status": "rendered_pending_review",
        "source": entries[0], "edits": entries[1:],
        "metadata": {"scene_id": SCENE, "created_at": now, "look": look, "storage_type": "physical_files",
                     "render_outputs": relative(renders),
                     "inputs": [{"role": "native_input_locations", "path": "inputs/native_input_locations.json"}]}})
    return {"suite": str(suite), "cases": {e["case_id"]: e["video_sha256"] for e in entries}}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--renders", type=Path, required=True, help="Folder with one render output folder per native case")
    p.add_argument("--suite", type=Path, default=REPO / "renders" / SCENE / "suite_build" / SUITE.name,
                   help="New suite folder (must not exist; default: renders/tennis_net_hit/suite_build/<suite>)")
    p.add_argument("--look", default="clear_afternoon_park_court")
    args = p.parse_args()
    print(json.dumps(build(args.renders.resolve(), args.suite.resolve(), args.look), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
