"""Publish and verify renders/pcve_suites/pcve_phone_sofa_drop_suite (stdlib + ffmpeg/ffprobe).

package(render_root, suite):  encode the six rendered 96-frame cases into a new suite in the current
    PCVE suite format: per case video.mp4, prompts.json (pcve_prompts/1), provenance.json
    (pcve_provenance/1), video_validation.json (pcve_video_validation/1), ground_truth_transforms.json;
    suite_manifest.json (pcve_suite/1), README.txt, inputs/, native_manifests/; then point
    scene_manifest.json at it.
verify(suite):  every case's video against scene_manifest.json, suite_manifest.json and provenance.json,
    MP4 sample table, prompts against the builder catalog, GT frame count and clock, the registered
    native cache behind the GT.
Prompts of a published suite are updated with `build_pcve_phone_sofa_drop.py --export-prompts`.
GT is written by tools/export_ground_truth.py with a numpy Python (.venv-rigid-elastic when present).
"""
from __future__ import annotations

import datetime
import json
import shutil
import subprocess
from pathlib import Path

from tools.scene_common import (CASE_IDS, PYTHON, REPO, SCENE, SUITE_DIR, SUITE_KEY, catalog_id, native_cache,
                                sha256, write_json)

BUILDER = SCENE / "build_pcve_phone_sofa_drop.py"
STANDARD = {"width": 1280, "height": 720, "fps": "24/1", "frames": 96, "duration_sec": 4.0}
X264 = ["-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-r", "24",
        "-movflags", "+faststart", "-an"]
LAYOUT = "cases/<case_id>/{video.mp4,prompts.json,provenance.json,video_validation.json}"


def rel(path):
    return str(Path(path).resolve().relative_to(REPO))


# ---------------------------------------------------------------- catalog and prompts
def catalog():
    from pcve_edit_catalog import load_catalog
    return load_catalog(BUILDER)


def record(cat, case):
    return cat["source"] if case == "source" else cat["edits"][case]


def prompt_origin():
    return "generated:" + rel(BUILDER)


def prompts_json(cat, case):
    """The pcve_prompts/1 file that `--export-prompts` keeps unchanged for this catalog record."""
    from pcve_edit_catalog import FORMAT_VERSION, _applies_from_frame, _fps
    item = record(cat, case)
    out = {"schema_version": 1, "format_version": FORMAT_VERSION, "scene": cat["scene"], "case_id": catalog_id(case),
           "kind": item["kind"], "source_case_id": "source", "availability": "available", "prompts": item["prompts"],
           "edit_dsl": None, "object_id": None, "applies_from_frame": None, "application_time_sec": None,
           "physics_override": {}, "physics_diff": {},
           "prompt_provenance": {"origin": prompt_origin(), "text_modified": False}}
    if case != "source":
        frame = _applies_from_frame(item)
        out.update(edit_dsl=item["edit_dsl"], applies_from_frame=frame, application_time_sec=(frame - 1) / _fps(),
                   physics_override=item["physics_override"], physics_diff=item["physics_diff"])
    return out


# ---------------------------------------------------------------- media
def probe(video):
    command = ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
               "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames,pix_fmt",
               "-show_entries", "format=duration", "-of", "json", str(video)]
    info = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
    decode = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], capture_output=True, text=True)
    stream = info["streams"][0]
    media = {"resolution": [stream["width"], stream["height"]], "fps": stream["r_frame_rate"],
             "duration_sec": round(float(info["format"]["duration"]), 3), "frames": int(stream["nb_read_frames"]),
             "full_decode": decode.returncode == 0 and not decode.stderr.strip(), "sha256": sha256(video),
             "probe": {"streams": [stream], "format": info["format"]}}
    media["pcve_spec_compliant"] = (media["resolution"] == [STANDARD["width"], STANDARD["height"]]
                                    and media["fps"] == STANDARD["fps"] and media["frames"] == STANDARD["frames"]
                                    and abs(media["duration_sec"] - STANDARD["duration_sec"]) < 1e-6
                                    and int(stream["nb_frames"]) == STANDARD["frames"] and media["full_decode"])
    return media


def video_validation(media, case):
    return {"schema_version": 1, "format_version": "pcve_video_validation/1", "scene": "phone_sofa_drop",
            "case_id": catalog_id(case), "video": "video.mp4", "resolution": media["resolution"], "fps": media["fps"],
            "duration_sec": media["duration_sec"], "frames": media["frames"], "sha256": media["sha256"],
            "technical_probe_verified": media["pcve_spec_compliant"], "full_decode_verified": media["full_decode"],
            "content_unchanged": False, "visual_or_physics_acceptance": "new render; visual review pending",
            "native_validation": {"probe": media["probe"]}}


def rendered_frames(case_dir):
    """Frame PNGs 1-96 of one case, checked against the worker reports (one device type, one host)."""
    workers = [json.loads(p.read_text()) for p in sorted(case_dir.glob("render_worker_*.json"))]
    seen = {}
    for w in workers:
        for f, row in w["frames"].items():
            seen[int(f)] = (row["sha256"], w["device_type"], w["host"], w["settings"]["samples"])
    if sorted(seen) != list(range(1, 97)):
        raise ValueError(f"{case_dir.name}: render reports do not cover frames 1-96")
    kinds = {(v[1], v[2], v[3]) for v in seen.values()}
    if len(kinds) != 1:
        raise ValueError(f"{case_dir.name}: frames from more than one device/host/sample setting: {kinds}")
    frames = [case_dir / "frames" / f"{f:04d}.png" for f in range(1, 97)]
    for f, path in enumerate(frames, 1):
        if sha256(path) != seen[f][0]:
            raise ValueError(f"{case_dir.name}: frame {f} differs from its render report")
    return frames, {"device_type": kinds.pop()[0], "hosts": sorted({w["host"] for w in workers}),
                    "devices": sorted({d for w in workers for d in w["devices"]}), "settings": workers[0]["settings"]}


def encode(frames_dir, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(".writing_" + target.name)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", "24", "-start_number", "1",
               "-i", str(frames_dir / "%04d.png"), "-frames:v", "96", *X264, str(tmp)]
    subprocess.run(command, check=True)
    tmp.replace(target)
    return command


def ground_truth(case, out):
    command = [str(PYTHON), str(SCENE / "tools/export_ground_truth.py"), "--case", case, "--out", str(out)]
    return json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)


def write_scene_pointer(suite, videos):
    path = SCENE / "scene_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    target = Path(suite).resolve()
    manifest["canonical_suites"] = {SUITE_KEY: {
        "target": rel(target) if REPO in target.parents else str(target), "case_video_sha256": videos}}
    write_json(path, manifest)


# ---------------------------------------------------------------- package (new suite from rendered frames)
def package(render_root, suite=SUITE_DIR, cases=CASE_IDS):
    render_root, suite = Path(render_root).resolve(), Path(suite).resolve()
    if tuple(cases) != CASE_IDS:
        raise ValueError("A suite is published with all six cases")
    if (suite / "suite_manifest.json").exists():
        raise FileExistsError(f"{suite} exists; choose a new suite folder")
    cat = catalog()
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    entries, videos = [], {}
    for case in cases:
        cid = catalog_id(case)
        case_dir = suite / "cases" / cid
        _, render = rendered_frames(render_root / case)
        encode(render_root / case / "frames", case_dir / "video.mp4")
        media = probe(case_dir / "video.mp4")
        if not media["pcve_spec_compliant"]:
            raise ValueError(f"{case}: encoded video is not 1280x720 / 24 FPS / 96 frames / 4.000 s")
        write_json(case_dir / "video_validation.json", video_validation(media, case))
        ground_truth(case, case_dir / "ground_truth_transforms.json")
        cache, _, cache_sha = native_cache(case)
        scene_report = json.loads((render_root / case / "scene_report.json").read_text())
        prompts = prompts_json(cat, case)
        write_json(case_dir / "prompts.json", prompts)
        write_json(case_dir / "provenance.json", {
            "schema_version": 1, "format_version": "pcve_provenance/1", "scene": "phone_sofa_drop", "case_id": cid,
            "kind": prompts["kind"], "native_case_id": case, "video_sha256": media["sha256"], "created_at": stamp,
            "native_case_dir": rel(render_root / case), "native_cache": rel(cache), "native_cache_sha256": cache_sha,
            "render": {**render, "frames": rel(render_root / case / "frames") + "/0001-0096.png",
                       "encoder": "ffmpeg " + " ".join(X264), "scene_report": rel(render_root / case / "scene_report.json"),
                       "look_sha256": scene_report.get("look_sha256")}})
        entries.append({
            "case_id": cid, "native_case_id": case, "kind": prompts["kind"], "source_case_id": "source",
            "case_dir": f"cases/{cid}", "status": "rendered_pending_review", "availability": "video_present",
            "video": f"cases/{cid}/video.mp4", "video_sha256": media["sha256"],
            "media": {k: media[k] for k in ("resolution", "fps", "duration_sec", "frames", "sha256")},
            **{k: prompts[k] for k in ("prompts", "edit_dsl", "object_id", "applies_from_frame", "application_time_sec",
                                       "physics_override", "physics_diff")}})
        videos[case] = media["sha256"]
    (suite / "inputs").mkdir(parents=True, exist_ok=True)
    write_json(suite / "inputs/native_input_locations.json", {
        "scene": "phone_sofa_drop", "kind": "native_input_locations",
        "scene_code": rel(SCENE), "render_root": rel(render_root),
        "native_caches": {c: f"assets/scenes/phone_sofa_drop/solves_4s_240hz/{c}/simulation_dense.npz" for c in cases},
        "packed_scenes": {c: f"assets/scenes/phone_sofa_drop/packed/{c}/scene.blend" for c in cases}})
    (suite / "native_manifests").mkdir(exist_ok=True)
    for name in ("entrypoints.json", "scene_spec.json"):
        shutil.copy2(SCENE / name, suite / "native_manifests" / f"scene_{name}")
    shutil.copy2(SCENE / "appearance" / "appearance.json", suite / "native_manifests" / "appearance.json")
    write_json(suite / "suite_manifest.json", {
        "schema_version": 5, "format_version": "pcve_suite/1", "layout": LAYOUT, "scene": "phone_sofa_drop",
        "title": "phone_sofa_drop", "suite_name": SUITE_KEY, "interaction_category": "rigid_elastic",
        "suite_path": rel(suite) if REPO in suite.parents else str(suite), "source_count": 1,
        "edit_count": len(entries) - 1, "status": "rendered_pending_review", "source": entries[0], "edits": entries[1:],
        "metadata": {"scene_id": "phone_sofa_drop", "created_at": stamp, "storage_type": "physical_files",
                     "render_outputs": rel(render_root), "media_standard": STANDARD,
                     "inputs": [{"role": "native_input_locations", "path": "inputs/native_input_locations.json"}],
                     "native_manifests": [{"path": f"native_manifests/{p.name}", "sha256": sha256(p)}
                                          for p in sorted((suite / "native_manifests").iterdir())]}})
    (suite / "README.txt").write_text(
        "PCVE suite: phone_sofa_drop\nSource: cases/source/video.mp4; edits: cases/edit_*/video.mp4 (5).\n"
        "Per case: video.mp4, prompts.json, provenance.json, video_validation.json, ground_truth_transforms.json.\n"
        "Index: suite_manifest.json. Scene code: scripts/rigid_elastic/phone_sofa_drop.\n", encoding="utf-8")
    write_scene_pointer(suite, videos)
    return {"suite": str(suite), "videos": videos}


# ---------------------------------------------------------------- verify
def ground_truth_cache_sha(gt):
    """sha256 of the native cache a ground-truth file was written from."""
    source = gt.get("source") or {}
    record = source.get("native_record") or source.get("previous_record") or {}
    return (gt.get("native_cache") or record.get("native_cache") or {}).get("sha256")


def verify(require_standard=False):
    from tools.scene_common import canonical_suite
    suite, pointer = canonical_suite()
    cat = catalog()
    manifest = json.loads((suite / "suite_manifest.json").read_text(encoding="utf-8"))
    problems, rows = [], []
    if set(pointer) != set(CASE_IDS):
        problems.append("scene_manifest.json does not list the six cases")
    for case in CASE_IDS:
        cid = catalog_id(case)
        case_dir = suite / "cases" / cid
        video = case_dir / "video.mp4"
        media = probe(video)
        prompts = json.loads((case_dir / "prompts.json").read_text(encoding="utf-8"))
        provenance = json.loads((case_dir / "provenance.json").read_text(encoding="utf-8"))
        gt = json.loads((case_dir / "ground_truth_transforms.json").read_text(encoding="utf-8"))
        entry = manifest["source"] if case == "source" else next(e for e in manifest["edits"] if e["native_case_id"] == case)
        _, _, cache_sha = native_cache(case)
        item = record(cat, case)
        checks = {
            "video_sha256_matches_manifests": media["sha256"] == pointer.get(case) == entry["video_sha256"]
                                              == provenance["video_sha256"],
            "full_decode": media["full_decode"],
            "gt_frames_equal_video_frames": len(gt["frames"]) == media["frames"],
            "gt_fps_equals_video_fps": f"{gt['fps']}/1" == media["fps"],
            "gt_clock": all(abs(r["time_sec"] - (r["frame_index"] - 1) / gt["fps"]) < 1e-9 for r in gt["frames"]),
            "gt_native_cache_registered": ground_truth_cache_sha(gt) == cache_sha,
            "prompts_match_catalog": prompts["prompts"] == item["prompts"] and prompts["edit_dsl"] == item.get("edit_dsl"),
            "prompt_origin_is_builder": prompts["prompt_provenance"]["origin"] == prompt_origin(),
            "standard_media": media["pcve_spec_compliant"],
        }
        for name, ok in checks.items():
            if not ok and (name != "standard_media" or require_standard):
                problems.append(f"{cid}: {name}")
        rows.append({"case": cid, "media": {k: media[k] for k in ("resolution", "fps", "frames", "duration_sec")},
                     "sha256": media["sha256"], "checks": checks})
    scripts = str(REPO / "scripts")
    for value in json.dumps(manifest).split('"'):
        if value.startswith("/mnt/") and not Path(value).exists():
            problems.append("suite_manifest path does not exist: " + value)
        # Data never lives under scripts/ (only this scene's code may be named), nor in temporary trees.
        if value.startswith("/tmp/") or (value.startswith(scripts) and not value.startswith(str(SCENE))):
            problems.append("suite_manifest refers to a scripts/ or temporary location: " + value)
    return {"suite": str(suite), "passed": not problems, "problems": problems, "cases": rows}
