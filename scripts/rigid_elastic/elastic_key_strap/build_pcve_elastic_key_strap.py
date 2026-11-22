"""Verify, rebuild or publish case 13 (elastic_key_strap): six cases, native caches, videos and edit catalog."""

# PCVE_EDIT_CATALOG_BEGIN
# Source description and five independent edits of the published suite.
# Values in physics_override use the shared-DSL schema; edit_vocab.py and physics/physics_model.py own the solver fields.
PCVE_SCENE = "elastic_key_strap"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "玄关木柜上方的墙上钉着一块木质钥匙挂板。一条细长的硅胶挂带挂在中间的挂钩上，下端通过一个钢制钥匙圈挂着两把钥匙。钥匙串从稍高的位置松开，挂带起初是松弛弯曲的，钥匙串下落后把硅胶挂带拉长，随后上下回弹并轻轻摆动。",
            "en": "A wooden key rack is fixed to the wall above an entryway cabinet. A thin silicone strap hangs from its middle hook, and a steel keyring at the strap's lower end holds two keys. The keys are let go from slightly higher up while the strap is still slack and bowed; they drop and stretch the silicone strap, then bounce up and down and sway gently."
        },
        "quantitative": {
            "zh": "玄关木柜上方的墙上钉着一块木质钥匙挂板。一条长 21.6 cm、宽 10 mm、厚 0.8 mm 的硅胶挂带挂在离地 1.28 m 的中间挂钩上，挂带的杨氏模量为 450 kPa。挂带下端通过一个直径 24 mm、质量 3.5 g 的钢制钥匙圈挂着两把钥匙，钥匙长 5.9 cm 和 5.4 cm，合计 27 g。钥匙圈起初被托高 3.5 cm、向一侧偏 9 mm，挂带松弛弯曲；钥匙串从静止松开后下落，把挂带拉长，随后上下回弹并轻轻摆动。木柜台面离地 0.86 m。",
            "en": "A wooden key rack is fixed to the wall above an entryway cabinet. A silicone strap 21.6 cm long, 10 mm wide and 0.8 mm thick, with a Young's modulus of 450 kPa, hangs from the middle hook 1.28 m above the floor. A steel keyring 24 mm across and weighing 3.5 g at the strap's lower end holds two keys, 5.9 cm and 5.4 cm long, 27 g together. The keyring starts at rest 3.5 cm higher than the straight strap would hold it and 9 mm to one side, so the strap is slack and bowed; once let go, the keys drop and stretch the strap, then bounce up and down and sway gently. The cabinet top is 0.86 m above the floor."
        }
    },
    "editable_objects": [
        {"object_id": "keys", "zh": "两把钥匙", "en": "the two keys", "in_video": True,
         "properties": ["mass"], "can_delete": False, "can_add": False},
        {"object_id": "strap", "zh": "硅胶挂带", "en": "the silicone strap", "in_video": True,
         "properties": ["young_modulus"], "can_delete": True, "can_add": False}
    ],
    "description_basis": "Baseline parameters of physics/scene_spec.json (strap 0.216 x 0.010 x 0.0008 m, E 450 kPa; keys 27 g; ring radius 12 mm, 3.5 g; start 35 mm above the straight-strap position and 9 mm to the side; hook anchor 1.28 m; cabinet top 0.86 m) and the key lengths of assets scenes/elastic_key_strap/prepared/key_geometry_manifest.json; outcomes beyond the visible interaction are not asserted."
}

PCVE_EDITS = {
    "keys_mass_5x": {
        "case_id": "keys_mass_5x",
        "catalog_case_id": "edit_keys_mass_5x",
        "native_cli_case_id": "keys_mass_5x",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET keys.mass TIMES 5",
        "applies_from_frame": 1,
        "physics_override": {
            "keys_mass_kg": 0.135
        },
        "physics_diff": {
            "keys_mass_kg": {
                "from": 0.027,
                "to": 0.135
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把两把钥匙的质量调大一些。",
                "en": "From the start of the clip, increase the two keys' mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把两把钥匙的质量增加到原来的 5 倍。",
                "en": "From frame 1 onwards, increase the two keys' mass to 5 times its original value."
            }
        },
        "label_zh": "钥匙质量 ×5",
        "how_to_edit": {
            "zh": "选择 keys_mass_5x 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case keys_mass_5x; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/elastic_key_strap/edit_vocab.py"
    },
    "strap_soft": {
        "case_id": "strap_soft",
        "catalog_case_id": "edit_strap_soft",
        "native_cli_case_id": "strap_soft",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET strap.young_modulus TIMES 0.1",
        "applies_from_frame": 1,
        "physics_override": {
            "strap_young_modulus_pa": 45000.0
        },
        "physics_diff": {
            "strap_young_modulus_pa": {
                "from": 450000.0,
                "to": 45000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把硅胶挂带的杨氏模量调小一些。",
                "en": "From the start of the clip, decrease the silicone strap's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把硅胶挂带的杨氏模量减少到原来的 0.1 倍。",
                "en": "From frame 1 onwards, reduce the silicone strap's Young's modulus to 0.1 times its original value."
            }
        },
        "label_zh": "挂带杨氏模量 ×0.1",
        "how_to_edit": {
            "zh": "选择 strap_soft 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case strap_soft; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/elastic_key_strap/edit_vocab.py"
    },
    "strap_stiff": {
        "case_id": "strap_stiff",
        "catalog_case_id": "edit_strap_stiff",
        "native_cli_case_id": "strap_stiff",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET strap.young_modulus TIMES 10",
        "applies_from_frame": 1,
        "physics_override": {
            "strap_young_modulus_pa": 4500000.0
        },
        "physics_diff": {
            "strap_young_modulus_pa": {
                "from": 450000.0,
                "to": 4500000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把硅胶挂带的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the silicone strap's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把硅胶挂带的杨氏模量增加到原来的 10 倍。",
                "en": "From frame 1 onwards, increase the silicone strap's Young's modulus to 10 times its original value."
            }
        },
        "label_zh": "挂带杨氏模量 ×10",
        "how_to_edit": {
            "zh": "选择 strap_stiff 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case strap_stiff; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/elastic_key_strap/edit_vocab.py"
    },
    "remove_strap": {
        "case_id": "remove_strap",
        "catalog_case_id": "edit_remove_strap",
        "native_cli_case_id": "remove_strap",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE strap",
        "applies_from_frame": 1,
        "physics_override": {
            "strap_present": [
                0
            ]
        },
        "physics_diff": {
            "strap_present": {
                "from": [
                    1
                ],
                "to": [
                    0
                ]
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把硅胶挂带从场景中删除。",
                "en": "From the start of the clip, remove the silicone strap from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把硅胶挂带从场景中删除。",
                "en": "From frame 1 onwards, remove the silicone strap from the scene."
            }
        },
        "label_zh": "删除硅胶挂带",
        "how_to_edit": {
            "zh": "选择 remove_strap 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case remove_strap; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/elastic_key_strap/edit_vocab.py"
    },
    "keys_mass_5x_at_frame_24": {
        "case_id": "keys_mass_5x_at_frame_24",
        "catalog_case_id": "edit_keys_mass_5x_at_frame_24",
        "native_cli_case_id": "keys_mass_5x_at_frame_24",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET keys.mass TIMES 5 AT FRAME 24",
        "applies_from_frame": 24,
        "physics_override": {
            "keys_mass_kg": 0.135
        },
        "physics_diff": {
            "keys_mass_kg": {
                "from": 0.027,
                "to": 0.135
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "在视频前段,把两把钥匙的质量调大一些。",
                "en": "Early in the clip, increase the two keys' mass."
            },
            "quantitative": {
                "zh": "从第 24 帧开始,把两把钥匙的质量增加到原来的 5 倍。",
                "en": "From frame 24 onwards, increase the two keys' mass to 5 times its original value."
            }
        },
        "label_zh": "钥匙质量 ×5",
        "how_to_edit": {
            "zh": "选择 keys_mass_5x_at_frame_24 案例；第 1–23 帧就是源视频的原生状态，求解器从源缓存恢复第 24 帧（t=23/24 s）的 MuJoCo 状态（qpos、qvel），从这一帧起把两把钥匙的质量设为 0.135 kg 并继续求解。",
            "en": "Select native case keys_mass_5x_at_frame_24; frames 1-23 are the source native states. The solver restores the MuJoCo state (qpos, qvel) of frame 24 (t=23/24 s) from the source cache, sets the two keys to 0.135 kg from that frame on and keeps solving."
        },
        "definition_source": "scripts/rigid_elastic/elastic_key_strap/edit_vocab.py"
    },
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/elastic_key_strap/build_pcve_elastic_key_strap.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "all",
        "prepare",
        "simulate",
        "render",
        "publish",
        "verify"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/elastic_key_strap/build_pcve_elastic_key_strap.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/elastic_key_strap/build_pcve_elastic_key_strap.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/elastic_key_strap/build_pcve_elastic_key_strap.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/elastic_key_strap/build_pcve_elastic_key_strap.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/elastic_key_strap/simulate_elastic_key_strap.py",
    "render_entry": "scripts/rigid_elastic/elastic_key_strap/render_elastic_key_strap.py",
    "current_suite": "renders/pcve_suites/pcve_elastic_key_strap_suite",
    "notes": [
        "native_cli_case_id selects the original scenario; catalog_case_id names the published edit_* video directory.",
        "The accepted native solves are assets/scenes/elastic_key_strap/native_solves/cases/<case>; render_elastic_key_strap.py replays them with appearance/realism.py.",
        "keys_mass_5x_at_frame_24 continues the source solve from frame 24 (simulate_elastic_key_strap.py --source-cache); its merged native solve is kept in the suite's inputs/native_timed/<case>/.",
        "--stage verify re-checks the accepted delivery and the published suite; simulate/render/publish write under --out (default renders/elastic_key_strap/rebuild/<UTC stamp>)."
    ]
}

def pcve_source_prompts():
    """Return the source prompts declared directly in this PCVE entry."""
    from copy import deepcopy
    return deepcopy(PCVE_SOURCE["prompts"])


def pcve_edit_info(case_id):
    """Return one edit's DSL, parameter changes, native case ID and prompts."""
    from pcve_edit_catalog import edit_info
    return edit_info(PCVE_EDITS, case_id)


def pcve_edit_override(case_id):
    """Return the declared override; native field conversion stays scene-owned."""
    return pcve_edit_info(case_id)["physics_override"]

# PCVE_EDIT_CATALOG_END


from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
CASE = Path(__file__).resolve().parent
SCRIPTS = CASE.parents[1]
sys.path.insert(0, str(SCRIPTS))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, 'build_pcve')
# PCVE_UNIFIED_ENTRY_END

import argparse
import hashlib
import json
import re
import subprocess

sys.path.insert(0, str(CASE))
from scene_paths import (CASES, CATALOG, DELIVERY, OUTPUT, PHYSICS, SUITE_NAME, TIMED_CASES, cache_dir,
                         manifest, media, output_path, stamp)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify_delivery(selected):
    """Accepted delivery: edit policy, resolved parameters, cache and video hashes, native clock.

    The accepted delivery predates the timed edit, so only the whole-clip cases (CASES) are checked here."""
    import edit_vocab as vocab
    import numpy as np
    from pcve_edit_policy import audit_suite_manifest
    from pcve_media_contract import require_times, require_video

    retained = read(DELIVERY / "accepted_case.json")
    # The accepted delivery also holds an ADD case that is not part of the published suite; only the
    # published edits are audited against the current vocabulary.
    delivery = read(DELIVERY / "suite_manifest.json")
    delivery["edits"] = [e for e in delivery.get("edits", []) if e.get("case_id") in CASES]
    policy = audit_suite_manifest(delivery, vocab.VOCAB, PHYSICS)
    if not policy["all_edits_compliant"]:
        raise RuntimeError("Strict edit audit of the accepted delivery failed")
    entries = {row["id"]: row for row in retained["variants"]}
    rows = []
    for case in [c for c in selected if c in CASES]:
        folder, row = cache_dir(case), entries[case]
        cfg = dict(vocab.BASELINE)
        cfg.update(vocab.override_for(case))
        if read(folder / "resolved_config.json") != cfg:
            raise RuntimeError(f"Resolved parameters differ from the accepted solve for {case}")
        cache_hash = sha(folder / "simulation.npz")
        report = read(DELIVERY / "cases" / case / "render_environment.json")
        if cache_hash != row["native_cache_sha256"] or cache_hash != report["simulation_cache_sha256"]:
            raise RuntimeError(f"Accepted cache hash differs for {case}")
        video = DELIVERY / "cases" / case / "video.mp4"
        if sha(video) != row["video_sha256"]:
            raise RuntimeError(f"Accepted video hash differs for {case}")
        require_video(video)
        with np.load(folder / "simulation.npz", allow_pickle=False) as states:
            require_times(states["times"][:96])
            if states["times"][-1] != 4:
                raise RuntimeError(f"Accepted native endpoint differs for {case}")
        replay = read(DELIVERY / "cases" / case / "native_replay_audit.json")
        if replay["retiming"] or replay["motion_smoothing"]:
            raise RuntimeError(f"Accepted rendering provenance differs for {case}")
        rows.append({"case": case, "state_sha256": cache_hash, "accepted_video_sha256": row["video_sha256"]})
    return rows


def verify_suite(selected):
    """Published suite: video hashes and media contract, prompts equal to this builder, ground truth, paths."""
    from pcve_edit_catalog import load_catalog
    from pcve_media_contract import require_video

    suite = media()
    pinned = manifest()["canonical_suites"][SUITE_NAME]["case_video_sha256"]
    catalog = load_catalog(Path(__file__))
    records = {"source": catalog["source"], **catalog["edits"]}
    text = (suite / "suite_manifest.json").read_text(encoding="utf-8")
    # The published suite names files by paths relative to the repository root (renders/ and assets/ resolve
    # through the checkout); absolute paths are taken as they are.
    named = sorted({p if p.startswith("/") else str(SCRIPTS.parent / p)
                    for p in re.findall(r'"(/[^"]+|(?:renders|assets|scripts|tools)/[^"]+)"', text)})
    missing = [p for p in named if not Path(p).exists()]
    # Data never lives in scripts/: the only scripts/ path a suite may name is this scene's code folder.
    retired = [p for p in named if SCRIPTS.resolve() in Path(p).resolve().parents
               and CASE.resolve() not in [Path(p).resolve(), *Path(p).resolve().parents]]
    if missing or retired:
        raise RuntimeError(f"suite_manifest.json names missing or retired paths: {(missing + retired)[:5]}")
    rows = []
    for case in selected:
        folder = suite / "cases" / CATALOG[case]
        video_hash = sha(folder / "video.mp4")
        if video_hash != pinned[case]:
            raise RuntimeError(f"{case}: video differs from scene_manifest.json")
        require_video(folder / "video.mp4")
        prompts = read(folder / "prompts.json")
        if prompts["prompts"] != records[case]["prompts"] or prompts.get("edit_dsl") != records[case].get("edit_dsl"):
            raise RuntimeError(f"{case}: prompts.json differs from the builder; run --export-prompts")
        gt = read(folder / "ground_truth_transforms.json")
        frames = gt["frames"]
        if (gt["format_version"], gt["fps"], gt["camera"]["resolution"], len(frames)) != ("pcve_ground_truth/1", 24, [1280, 720], 96) or any(
                fr["frame_index"] != i + 1 or abs(fr["time_sec"] - i / 24) > 1e-9 for i, fr in enumerate(frames)):
            raise RuntimeError(f"{case}: ground truth does not follow the 96-frame 24 fps clock")
        if sha(cache_dir(case) / "simulation.npz") not in gt["source"]["sha256"].values():
            raise RuntimeError(f"{case}: ground truth was not written from the accepted cache")
        rows.append({"case": case, "video_sha256": video_hash, "ground_truth": "ok", "prompts": "ok"})
    return str(suite), rows


def run(cmd):
    print(" ".join(map(str, cmd)), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("all", "prepare", "simulate", "render", "publish", "verify"), default="verify")
    parser.add_argument("--cases", nargs="+", choices=CASES + TIMED_CASES, default=list(CASES + TIMED_CASES))
    parser.add_argument("--out", type=Path, help="output root of simulate/render/publish (default renders/elastic_key_strap/rebuild/<UTC stamp>)")
    parser.add_argument("--accepted-physics", action="store_true", help="render the accepted solves (scene_paths.cache_dir) instead of OUT/physics")
    parser.add_argument("--device", choices=("cpu", "optix", "cuda"), default="cpu")
    parser.add_argument("--samples", type=int, default=384)
    parser.add_argument("--blender-bin", type=Path)
    parser.add_argument("--gpu-uuid")
    parser.add_argument("--cpu-threads", type=int, default=32)
    args = parser.parse_args()
    if args.stage == "verify":
        result = {"accepted_delivery": verify_delivery(args.cases)}
        result["published_suite"], result["suite_cases"] = verify_suite(args.cases)
        print(json.dumps(result, indent=2))
        print("VERIFY_OK", len(args.cases), "cases", flush=True)
        return
    stages = ["prepare", "simulate", "render"] if args.stage == "all" else [args.stage]
    root = output_path(args.out or OUTPUT / stamp())
    if "prepare" in stages:
        run([sys.executable, SCRIPTS / "download_assets.py", "--scene", "rigid_elastic/elastic_key_strap", "--check"])
    for case in args.cases:
        if "simulate" in stages:
            cmd = [sys.executable, CASE / "simulate_elastic_key_strap.py", "--case", case, "--out-root", root]
            # A timed case continues the source solve of this run when there is one (else the accepted source).
            if case in TIMED_CASES and (root / "physics" / "source" / "simulation.npz").is_file():
                cmd += ["--source-cache", root / "physics" / "source"]
            run(cmd)
        if "render" in stages:
            cmd = [sys.executable, CASE / "render_elastic_key_strap.py", "--case", case, "--out-root", root,
                   "--device", args.device, "--samples", args.samples, "--cpu-threads", args.cpu_threads]
            if not args.accepted_physics:
                cmd += ["--cache-dir", root / "physics" / case]
            if args.gpu_uuid:
                cmd += ["--gpu-uuid", args.gpu_uuid]
            if args.blender_bin:
                cmd += ["--blender-bin", args.blender_bin]
            run(cmd)
    if "publish" in stages:
        if set(args.cases) != set(CASES + TIMED_CASES):
            parser.error("publishing needs all six cases")
        run([sys.executable, CASE / "tools/publish_suite.py", "--native", root, "--suite", root / SUITE_NAME])


if __name__ == "__main__":
    main()
