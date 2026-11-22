"""Build the source and eight requested rigid-body edits with canonical PCVE CLIs."""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "build_pcve")
# PCVE_UNIFIED_ENTRY_END

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from pcve_assets import blender
from scene_config import SCENE, SUPPORTED_CASES, scenario, signature
from edit_vocab import edit_info
from simulate_ball_box_rebound import simulate, write_json, export_csv
from physics.validate_ball_box_rebound import validate


def source_prompts():
    return {"vague": {
        "zh": "明亮室内玩具区，星星玩具球斜撞白色玩具箱后反弹，正面撞动黑白足球，随后两球逐渐减速。",
        "en": "In a bright playroom, a star-patterned toy ball rebounds obliquely from a white toy chest and makes a near-central head-on impact with a football; both balls then slow down."},
        "quantitative": {
        "zh": "直径 18 厘米、质量 0.32 千克的星星玩具球以约 1.56 m/s 的速度、约 45 度的方向撞上 72×44×40 厘米、8 千克的白色玩具箱，反弹后几乎正面撞上直径 22 厘米、质量 0.43 千克的黑白足球，随后两球逐渐减速。",
        "en": "An 18 cm, 0.32 kg star-patterned toy ball rolls at about 1.56 m/s into a 72x44x40 cm, 8 kg white toy chest at about 45 degrees, rebounds, and hits a 22 cm, 0.43 kg black-and-white football almost head-on. Both balls then slow down."}}


def replay_source(path, cfg):
    result = json.loads(path.read_text())
    previous = copy.deepcopy(result["configuration"])
    if previous["physics"] != cfg["physics"] or previous["simulation_quality"] != cfg["simulation_quality"]:
        raise ValueError("Cache replay must keep physical inputs and numerical quality frozen")
    if any(previous["render"][key] != cfg["render"][key] for key in ("fps", "duration_sec", "total_frames")):
        raise ValueError("Cache replay must keep timing frozen")
    result["configuration"], result["configuration_sha256"] = cfg, signature(cfg)
    result["case_id"] = "source"
    result["appearance_replay_provenance"] = {
        "source_cache": str(path.resolve()), "source_cache_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "solved_frames_sha256": signature(result["frames"]),
        "solved_trajectory_sha256": signature(result["trajectory_samples"]), "new_simulation_performed": False}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--stage", choices=["all", "simulate", "prepare", "preview", "render", "verify"], default="all")
    parser.add_argument("--cases", nargs="+", choices=SUPPORTED_CASES, default=list(SUPPORTED_CASES))
    parser.add_argument("--blender", type=Path, default=blender())
    parser.add_argument("--threads-native", type=int, default=64)
    parser.add_argument("--device", choices=["cpu", "gpu", "metal"], default="cpu")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--config-json", type=Path)
    parser.add_argument("--keyframes", type=int, nargs="+")
    parser.add_argument("--reuse-physics-json", type=Path, help="Reuse the source only; edits are solved independently")
    args = parser.parse_args()
    override = json.loads(args.config_json.read_text()) if args.config_json else None
    cfg = scenario(override)
    out = args.out_root.expanduser().resolve()
    manifest_path = out / "suite_manifest.json"
    selected = list(dict.fromkeys(("source", *args.cases)))
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest["configuration"] != cfg:
            raise ValueError("Choose a fresh output root for changed source inputs")
    else:
        if out.exists() and any(out.iterdir()):
            raise FileExistsError("Refusing an existing unowned output root")
        manifest = {"schema_version": 4, "suite_name": "pcve_" + SCENE + "_suite", "scene": SCENE,
            "interaction_category": "rigid_rigid", "configuration": cfg, "configuration_sha256": signature(cfg),
            "source_case_id": "source", "source": None, "edits": [], "requested_scope": "source and eight counterfactual edits",
            "supported_cases": list(SUPPORTED_CASES), "resolution": cfg["render"]["resolution"],
            "fps": cfg["render"]["fps"], "duration_sec": cfg["render"]["duration_sec"],
            "total_frames": cfg["render"]["total_frames"], "samples": cfg["render"]["samples"],
            "playback_rate": 1.0, "status": "running",
            "framing_policy": "User retained the source camera and permits edited bodies to leave the frame. No camera recentering or trajectory intervention.",
            "video_status": "not_rendered"}
        write_json(manifest_path, manifest)
    source = None
    for case in selected:
        expected = scenario(override, case=case)
        info = edit_info(case, cfg) if case != "source" else None
        folder = out / "cases" / case
        path = folder / "physics_transforms.json"
        folder.mkdir(parents=True, exist_ok=True)
        if args.stage in ("all", "simulate"):
            if path.exists() and not args.skip_existing:
                raise FileExistsError(path)
            if not path.exists():
                result = replay_source(args.reuse_physics_json, expected) if case == "source" and args.reuse_physics_json else simulate(expected, case)
                write_json(path, result)
                export_csv(folder / "trajectory.csv", result)
                write_json(folder / "contacts.json", result["contact_events"])
                write_json(folder / "interventions.json", result.get("intervention_events", []))
        result = json.loads(path.read_text())
        if result["configuration"] != expected or result.get("case_id", "source") != case:
            raise ValueError("Cache configuration/case differs: " + case)
        validation = validate(result, case, source)
        write_json(folder / "physics_validation.json", validation)
        if not validation["accepted"]:
            raise RuntimeError(f"Physics rejected {case}: {[key for key, value in validation['checks'].items() if not value]}")
        if case == "source":
            source = result
        write_json(folder / "settings.json", expected)
        prompt = {"schema_version": 2, "case_id": case, "source_case_id": "source"}
        if info:
            prompt.update(info)
            write_json(folder / "scenario_overrides.json", info["physics_override"])
            write_json(folder / "configuration_diff.json", {"before": cfg, "after": expected, "declared_fields": info["target_fields"]})
        else:
            prompt["prompts"] = source_prompts()
        write_json(folder / "prompts.json", prompt)
        old = manifest.get("source") if case == "source" else next((e for e in manifest["edits"] if e["case_id"] == case), None)
        record = old or {"case_id": case, "kind": "source" if case == "source" else "edit",
                         "source_case_id": "source", "case_dir": str(folder)}
        record.update(status="physics_accepted", simulation_wall_sec=result["simulation_wall_sec"],
                      physics_validation=validation, observed_outcome=validation["metrics"])
        if info:
            record.update(info)
        record["outputs"] = {key: str(folder / name) for key, name in (
            ("video", "video.mp4"), ("scene", SCENE + ".blend"), ("physics", "physics_transforms.json"),
            ("trajectory", "trajectory.csv"), ("contacts", "contacts.json"), ("interventions", "interventions.json"),
            ("ground_truth", "ground_truth_transforms.json"), ("scenario_metadata", "scenario_metadata.json"))}
        if args.stage in ("all", "prepare", "preview", "render"):
            mode = {"prepare": "prepare", "preview": "frames"}.get(args.stage, "animation")
            already_prepared = args.skip_existing and mode == "prepare" and (folder / (SCENE + ".blend")).exists()
            if not already_prepared:
                command = [str(args.blender), "--factory-startup", "-b", "-t", str(args.threads_native), "--python-exit-code", "1",
                    "--python", str(HERE / ("render_" + SCENE + ".py")), "--", "--physics-json", str(path),
                    "--out-dir", str(folder), "--mode", mode, "--device", args.device, "--threads-native", str(args.threads_native)]
                if args.skip_existing:
                    command.append("--skip-existing")
                if mode == "frames":
                    frames = args.keyframes or ([48, 49, 96] if case == "edit_remove_football_at_2s" else [1, 34, 96])
                    command += ["--keyframes", *map(str, frames)]
                begin = time.perf_counter()
                with (folder / ("render_" + mode + ".log")).open("w") as log:
                    subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
                record[mode + "_pipeline_sec"] = time.perf_counter() - begin
            record["status"] = "scene_prepared_video_pending" if mode == "prepare" else "keyframes_rendered_pending_review"
        if args.stage in ("all", "render", "verify"):
            subprocess.run([sys.executable, str(ROOT / "scripts/pcve_verify_video.py"), str(folder / "video.mp4"),
                "--out", str(folder / "video_validation.json"), "--resolution", "1280", "720", "--fps", "24", "--frames", "96"], check=True)
            record["status"] = "video_technically_verified_pending_visual_review"
        if case == "source":
            manifest["source"] = record
        else:
            manifest["edits"] = [e for e in manifest["edits"] if e["case_id"] != case] + [record]
        manifest["status"] = "physics_accepted_video_pending" if args.stage == "simulate" else record["status"]
        manifest["video_status"] = "partially_or_fully_rendered_pending_review" if args.stage in ("all", "render", "verify") else "not_rendered"
        write_json(manifest_path, manifest)
        print(case, record["status"], flush=True)
    write_json(out / "implementation_manifest.json", {"configuration": cfg, "runtime_python": sys.executable, "python_version": sys.version,
        "asset_policy": "Daylit playroom geometry, white chest texture, environment, camera and lighting; star ball with cream pad-print stars on pigmented vinyl, registered CC0 Poly Haven wood_floor as the floor appearance (floor contact parameters independent of it), text-free book covers and car plate/badge, football use marks from its own scuff map. All edits independently solve only declared physical changes. Full video rendering remains separate from physics and preparation."})
    print(manifest_path)


if __name__ == "__main__":
    main()
