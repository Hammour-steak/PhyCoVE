"""Verify, re-solve, render or publish spring_car_collision: source + five edits.

Stages (--stage, default verify):
  verify    published suite (scene_manifest.json canonical_suites) and the accepted native solves
  simulate  solve the selected cases into --out-root/cases/<case>/ (simulate entry)
  render    render the selected cases from the accepted solves into --out-root/<case>/ (render entry)
  publish   encode a finished render root and assemble it as a suite (tools/publish_suite.py)
"""

# PCVE_EDIT_CATALOG_BEGIN
# Source description and five independent edits of the published suite.
# Values in physics_override use the shared-DSL schema; edit_vocab.py and physics/physics_model.py own the solver fields.
PCVE_SCENE = "spring_car_collision"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "木地板上，左边装着一个压缩着的弹簧发射器，一辆玩具车静止地停在它的推板前，右边放着一个木块。弹簧松开后把玩具车向右弹出，玩具车沿地板滚过去撞上木块。",
            "en": "On a wooden floor, a compressed spring launcher stands on the left, a toy car rests against its pusher plate, and a wooden block stands further to the right. The spring is released and launches the toy car to the right; the car rolls along the floor and runs into the wooden block."
        },
        "quantitative": {
            "zh": "木地板上左边装着一个弹簧发射器：钢制压缩弹簧自由长度 22 cm、圈径 3 cm、线径 1.2 mm，杨氏模量 205.4 GPa（刚度 47.4 N/m），起初被压缩 6 cm。一辆长 23 cm、质量 0.3 kg 的玩具车静止地停在推板前；车头右方 51 cm 处放着一个 8 × 8.5 × 5.5 cm、0.14 kg 的木块。弹簧松开后把玩具车向右弹出，玩具车沿地板滚过去撞上木块。",
            "en": "On a wooden floor, a spring launcher stands on the left: a steel compression spring 22 cm long when relaxed and 3 cm across, wound from 1.2 mm wire with a Young's modulus of 205.4 GPa (a stiffness of 47.4 N/m), starts compressed by 6 cm. A toy car 23 cm long and weighing 0.3 kg rests against the pusher plate, and a wooden block of 8 × 8.5 × 5.5 cm and 0.14 kg stands 51 cm ahead of the car's nose. The spring is released and launches the car to the right; the car rolls along the floor and runs into the block."
        }
    },
    "editable_objects": [
        {"object_id": "spring", "zh": "弹簧", "en": "the spring", "in_video": True,
         "properties": ["young_modulus"], "can_delete": True, "can_add": False},
        {"object_id": "car", "zh": "玩具车", "en": "the toy car", "in_video": True,
         "properties": [], "can_delete": False, "can_add": False},
        {"object_id": "block", "zh": "木块", "en": "the wooden block", "in_video": True,
         "properties": ["mass"], "can_delete": True, "can_add": False},
        {"object_id": "obstacle_block", "zh": "第二个木块", "en": "another wooden block", "in_video": False,
         "properties": [], "can_delete": False, "can_add": True}
    ],
    "description_basis": "Baseline of scene_spec.json: spring free length 0.22 m, mean coil diameter 30 mm, wire 1.2 mm, E 205.4 GPa (axial rate 47.4 N/m), initial compression 60 mm; toy car 0.230 x 0.110 x 0.0785 m, 0.3 kg, at rest against the pusher (nose x = -0.267 m); block 0.080 x 0.085 x 0.055 m, 0.14 kg, near face x = 0.240 m. Outcomes beyond the visible interaction are not asserted."
}

PCVE_EDITS = {
    "add_block": {
        "case_id": "add_block",
        "catalog_case_id": "edit_add_block",
        "native_cli_case_id": "add_block",
        "kind": "edit",
        "operation": "ADD",
        "edit_dsl": "ADD obstacle_block BETWEEN car AND block AT 5/6 FROM car",
        "native_edit_dsl": "ADD obstacle_block AT PRESET approach",
        "applies_from_frame": 1,
        "physics_override": {
            "obstacle_present": [
                1
            ]
        },
        "physics_diff": {
            "obstacle_present": {
                "from": [
                    0
                ],
                "to": [
                    1
                ]
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,在玩具车和木块的连线上、靠近木块的地方,放一个大小相近的木块。",
                "en": "From the start of the clip, place another wooden block on the line between the toy car and the wooden block, closer to the wooden block."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,在玩具车和木块连线的六等分点上放一个大小相近的木块,取靠近木块的那个。",
                "en": "From frame 1 onwards, place another wooden block on the line between the toy car and the wooden block, one sixth of the way from the wooden block to the toy car."
            }
        },
        "label_zh": "增加木块",
        "how_to_edit": {
            "zh": "选择 add_block 案例；按 native_edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。edit_dsl 是共享的 BETWEEN 形式定位语句,prompt 按它写成。",
            "en": "Select native case add_block; apply native_edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render. edit_dsl is the shared BETWEEN-form placement statement the prompts are written from."
        },
        "definition_source": "scripts/rigid_elastic/spring_car_collision/scene_spec.json (derived_interventions.add_block: 5/6 along the car-root to block-centre line, 80 x 85 x 59.2 mm, 0.14 kg)"
    },
    "remove_spring": {
        "case_id": "remove_spring",
        "catalog_case_id": "edit_remove_spring",
        "native_cli_case_id": "remove_spring",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE spring",
        "applies_from_frame": 1,
        "physics_override": {
            "spring_present": [
                0
            ]
        },
        "physics_diff": {
            "spring_present": {
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
                "zh": "从视频一开始,把弹簧从场景中删除。",
                "en": "From the start of the clip, remove the spring from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把弹簧从场景中删除。",
                "en": "From frame 1 onwards, remove the spring from the scene."
            }
        },
        "label_zh": "删除弹簧",
        "how_to_edit": {
            "zh": "选择 remove_spring 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case remove_spring; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/spring_car_collision/edit_vocab.py"
    },
    "stiffer_spring": {
        "case_id": "stiffer_spring",
        "catalog_case_id": "edit_stiffer_spring",
        "native_cli_case_id": "stiffer_spring",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET spring.young_modulus TIMES 3",
        "applies_from_frame": 1,
        "physics_override": {
            "spring_young_modulus_pa": 616200000000.0
        },
        "physics_diff": {
            "spring_young_modulus_pa": {
                "from": 205400000000.0,
                "to": 616200000000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把弹簧的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the spring's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把弹簧的杨氏模量增加到原来的 3 倍。",
                "en": "From frame 1 onwards, increase the spring's Young's modulus to 3 times its original value."
            }
        },
        "label_zh": "弹簧杨氏模量 ×3",
        "how_to_edit": {
            "zh": "选择 stiffer_spring 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case stiffer_spring; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/spring_car_collision/edit_vocab.py"
    },
    "remove_block": {
        "case_id": "remove_block",
        "catalog_case_id": "edit_remove_block",
        "native_cli_case_id": "remove_block",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE block",
        "applies_from_frame": 1,
        "physics_override": {
            "block_present": [
                0
            ]
        },
        "physics_diff": {
            "block_present": {
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
                "zh": "从视频一开始,把木块从场景中删除。",
                "en": "From the start of the clip, remove the wooden block from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把木块从场景中删除。",
                "en": "From frame 1 onwards, remove the wooden block from the scene."
            }
        },
        "label_zh": "删除木块",
        "how_to_edit": {
            "zh": "选择 remove_block 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case remove_block; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/spring_car_collision/edit_vocab.py"
    },
    "heavier_block": {
        "case_id": "heavier_block",
        "catalog_case_id": "edit_heavier_block",
        "native_cli_case_id": "heavier_block",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET block.mass TIMES 3",
        "applies_from_frame": 1,
        "physics_override": {
            "block_mass_kg": 0.42
        },
        "physics_diff": {
            "block_mass_kg": {
                "from": 0.14,
                "to": 0.42
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把木块的质量调大一些。",
                "en": "From the start of the clip, increase the wooden block's mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把木块的质量增加到原来的 3 倍。",
                "en": "From frame 1 onwards, increase the wooden block's mass to 3 times its original value."
            }
        },
        "label_zh": "木块质量 ×3",
        "how_to_edit": {
            "zh": "选择 heavier_block 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case heavier_block; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/spring_car_collision/edit_vocab.py"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/spring_car_collision/build_pcve_spring_car_collision.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "verify",
        "simulate",
        "render",
        "publish"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/spring_car_collision/build_pcve_spring_car_collision.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/spring_car_collision/build_pcve_spring_car_collision.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/spring_car_collision/build_pcve_spring_car_collision.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/spring_car_collision/build_pcve_spring_car_collision.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/spring_car_collision/simulate_spring_car_collision.py",
    "render_entry": "scripts/rigid_elastic/spring_car_collision/render_spring_car_collision.py",
    "current_suite": "renders/pcve_suites/pcve_spring_car_collision_suite",
    "notes": [
        "native_cli_case_id selects the original scenario; catalog_case_id names the published edit_* video directory.",
        "Accepted native solves: assets/scenes/spring_car_collision/native_cases/<case> (MuJoCo 3.3.7, .runtime/spring_car_collision/deps).",
        "The verify stage does not solve or render; use the simulate/render stages for reproduction."
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


# PCVE_UNIFIED_ENTRY_BEGIN
from pathlib import Path as _EntryPath
import sys as _entry_sys
_entry_sys.path.insert(0, str(_EntryPath(__file__).resolve().parents[2]))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "build_pcve")
# PCVE_UNIFIED_ENTRY_END

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1])]
import scene_config as cfg  # noqa: E402

STAGES = ("verify", "simulate", "render", "publish")


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def recorded_cache_sha256(source):
    """The native trajectory sha256 named in a ground-truth "source" record (nested records included)."""
    if isinstance(source, dict):
        if isinstance(source.get("cache_sha256"), str):
            return source["cache_sha256"]
        for value in source.values():
            found = recorded_cache_sha256(value)
            if found:
                return found
    return None


def verify(cases, suite=None):
    """Published videos, prompts and ground truth, plus the accepted native solves they come from."""
    from pcve_media_contract import require_video
    manifest = read_json(HERE / "scene_manifest.json")
    entry = manifest["canonical_suites"][cfg.SUITE_NAME]
    root = Path(suite or (cfg.REPO / entry["target"])).resolve()
    report = {"suite": str(root), "cases": {}}
    for case in cases:
        folder = root / "cases" / cfg.CATALOG[case]
        video = folder / "video.mp4"
        digest = sha256(video)
        if suite is None and digest != entry["case_video_sha256"][case]:
            raise ValueError(f"{case}: video differs from scene_manifest.json")
        if read_json(folder / "provenance.json")["video_sha256"] != digest:
            raise ValueError(f"{case}: video differs from provenance.json")
        contract = require_video(video)
        prompts = read_json(folder / "prompts.json")
        if (prompts["scene"], prompts["case_id"]) != (cfg.SCENE, cfg.CATALOG[case]) or \
                set(prompts["prompts"]) != {"vague", "quantitative"}:
            raise ValueError(f"{case}: prompts.json does not belong to this case")
        gt = read_json(folder / "ground_truth_transforms.json")
        if len(gt["frames"]) != cfg.FRAMES or gt["fps"] != cfg.FPS or gt["frame_end"] != cfg.FRAMES:
            raise ValueError(f"{case}: ground truth is not 96 frames at 24 fps")
        native = cfg.native_case(case)
        recorded = manifest["native_cases"][case]["trajectory_sha256"]
        if sha256(native / "trajectory.npz") != recorded or recorded_cache_sha256(gt["source"]) != recorded:
            raise ValueError(f"{case}: accepted native solve or its ground truth differs from scene_manifest.json")
        report["cases"][case] = {"video_sha256": digest, "contract": contract, "native": str(native),
                                 "ground_truth_frames": len(gt["frames"])}
    report["passed"] = True
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--stage", choices=STAGES, default="verify")
    p.add_argument("--cases", nargs="+", choices=cfg.CASES, default=list(cfg.CASES))
    p.add_argument("--out-root", type=Path, help="simulate/render output root, or the render root to publish")
    p.add_argument("--suite", type=Path, help="verify another suite folder instead of the published one")
    p.add_argument("--blender-bin", type=Path, help="render: Blender executable (default tools/blender-4.3.2)")
    p.add_argument("--gpu-index", help="render: CUDA device index or UUID")
    p.add_argument("--render-threads", type=int, help="render: CPU threads")
    p.add_argument("--device", choices=["cpu", "optix", "cuda"], default="optix", help="render: Cycles device")
    p.add_argument("--publish", action="store_true", help="publish: replace the published suite (otherwise <out-root>/suite_staging only)")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    cases = list(dict.fromkeys(a.cases))
    if a.stage == "simulate":
        command = [sys.executable, "-B", str(HERE / f"simulate_{cfg.SCENE}.py"), "--cases", *cases]
        command += ["--out-root", str(a.out_root or cfg.DEFAULT_SIMULATE_OUT)]
        commands = [command]
    elif a.stage == "render":
        commands = []
        for case in cases:
            command = [sys.executable, "-B", str(HERE / f"render_{cfg.SCENE}.py"), "--case", case,
                       "--out-root", str(a.out_root or cfg.DEFAULT_RENDER_OUT), "--device", a.device]
            if a.blender_bin:
                command += ["--blender-bin", str(a.blender_bin)]
            if a.gpu_index:
                command += ["--gpu-index", a.gpu_index]
            if a.render_threads:
                command += ["--render-threads", str(a.render_threads)]
            commands.append(command)
    elif a.stage == "publish":
        if not a.out_root:
            p.error("--stage publish needs --out-root <render root>")
        command = [sys.executable, "-B", str(HERE / "tools/publish_suite.py"), "--native", str(a.out_root)]
        commands = [command + (["--publish"] if a.publish else [])]
    else:
        commands = []
    if a.dry_run:
        print(json.dumps({"scene": cfg.SCENE, "stage": a.stage, "cases": cases, "commands": commands}, indent=2))
        return
    if a.stage == "verify":
        print(json.dumps(verify(cases, a.suite), indent=2))
        return
    if a.stage == "publish" and set(cases) != set(cfg.CASES):
        p.error(f"--stage {a.stage} works on the whole suite (all six cases)")
    for command in commands:
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
