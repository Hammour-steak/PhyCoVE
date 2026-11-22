"""Solve the native cases or verify the accepted delivery (videos and 96 native states)."""

# PCVE_EDIT_CATALOG_BEGIN
# Source descriptions and five independent edits for the current published suite.
# Values in physics_override use the recorded shared-DSL/native-plan schema;
# scene-native adapters retain all required solver-field and presence conversions.
PCVE_SCENE = "thomas_dual_spring_train"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "儿童木桌上，无动力蓝色玩具火车在两端导向压簧和推板之间运动。",
            "en": "On a wooden play table, an unpowered blue toy train moves between guided compression springs and pushers at both ends."
        },
        "quantitative": {
            "zh": "儿童木桌上,一辆 150 g 的无动力蓝色玩具火车停在约 90 cm 长的木轨道左端,左侧压簧初始被压缩 4.5 cm(两根压簧自然长度均为 12 cm、钢丝直径 1.1 mm、弹簧中径 2.4 cm),火车在两端导向压簧和推板之间运动。",
            "en": "On a wooden play table, a 150 g unpowered blue toy train sits at the left end of a wooden track about 90 cm long, with the left compression spring pre-compressed by 4.5 cm (both springs: 12 cm free length, 1.1 mm wire, 2.4 cm mean coil diameter); the train moves between the guided compression springs and pushers at both ends."
        }
    },
    "description_basis": "Current scene code and retained source-video inspection; physical outcomes beyond the visible interaction are not asserted."
}

PCVE_EDITS = {
    "add_wood_block": {
        "case_id": "add_wood_block",
        "catalog_case_id": "edit_add_wood_block",
        "native_cli_case_id": "add_wood_block",
        "kind": "edit",
        "operation": "ADD",
        "edit_dsl": "ADD wood_block BETWEEN train AND right_track_reference AT MIDPOINT",
        "native_edit_dsl": "ADD wood_block AT PRESET track_interceptor",
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
                "zh": "从视频一开始,在无动力蓝色玩具火车和右侧压簧下方的轨道的连线上、大致中间的位置,放一个木块。",
                "en": "From the start of the clip, place a wooden block on the line between the unpowered blue toy train and the track under the right spring, about midway between them."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,在无动力蓝色玩具火车和右侧压簧下方的轨道连线的中点放一个木块。",
                "en": "From frame 1 onwards, place a wooden block at the midpoint of the line between the unpowered blue toy train and the track under the right spring."
            }
        },
        "prompt_note": "Prompts are pcve_edit_dsl.make_prompts(parse(edit_dsl, VOCAB), VOCAB) with this scene's edit_vocab.VOCAB. The endpoints of edit_dsl carry display-only GeometryAnchors in edit_vocab.py at their frame-1 positions; the division point is 0.35 cm from the added body's frame-1 centre. The solver still runs native_edit_dsl; physics and video are unchanged.",
        "how_to_edit": {
            "zh": "选择 add_wood_block 案例；按 native_edit_dsl 的预设位置在轨道上加入木块，其余物体从原场景第 1 帧的状态重新求解并渲染。",
            "en": "Select native case add_wood_block; add the wooden block at the preset position of native_edit_dsl on the track, solve everything else from frame 1 of the source and render."
        },
        "definition_source": "scripts/rigid_elastic/thomas_dual_spring_train/physics/native.py"
    },
    "delete_right_spring": {
        "case_id": "delete_right_spring",
        "catalog_case_id": "edit_delete_right_spring",
        "native_cli_case_id": "delete_right_spring",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE right_spring",
        "applies_from_frame": 1,
        "physics_override": {
            "right_spring_present": [
                0
            ]
        },
        "physics_diff": {
            "right_spring_present": {
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
                "zh": "从视频一开始,把右侧压簧和推板从场景中删除。",
                "en": "From the start of the clip, remove the right compression spring and its moving pusher from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把右侧压簧和推板从场景中删除。",
                "en": "From frame 1 onwards, remove the right compression spring and its moving pusher from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 delete_right_spring 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case delete_right_spring; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/thomas_dual_spring_train/physics/native.py"
    },
    "mass_x3": {
        "case_id": "mass_x3",
        "catalog_case_id": "edit_mass_x3",
        "native_cli_case_id": "mass_x3",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET train.mass TIMES 3",
        "applies_from_frame": 1,
        "physics_override": {
            "train_mass_kg": 0.45
        },
        "physics_diff": {
            "train_mass_kg": {
                "from": 0.15,
                "to": 0.45
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把无动力蓝色玩具火车的质量调大一些。",
                "en": "From the start of the clip, increase the unpowered blue toy train's mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把无动力蓝色玩具火车的质量增加到原来的 3 倍。",
                "en": "From frame 1 onwards, increase the unpowered blue toy train's mass to 3 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 mass_x3 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case mass_x3; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/thomas_dual_spring_train/physics/native.py"
    },
    "right_young_x025": {
        "case_id": "right_young_x025",
        "catalog_case_id": "edit_right_young_x025",
        "native_cli_case_id": "right_young_x025",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET right_spring.young_modulus TIMES 0.25",
        "applies_from_frame": 1,
        "physics_override": {
            "right_young_modulus_pa": 50000000000.0
        },
        "physics_diff": {
            "right_young_modulus_pa": {
                "from": 200000000000.0,
                "to": 50000000000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把右侧压簧和推板的杨氏模量调小一些。",
                "en": "From the start of the clip, decrease the right compression spring and its moving pusher's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把右侧压簧和推板的杨氏模量减少到原来的 0.25 倍。",
                "en": "From frame 1 onwards, reduce the right compression spring and its moving pusher's Young's modulus to 0.25 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 right_young_x025 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case right_young_x025; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/thomas_dual_spring_train/physics/native.py"
    },
    "rolling_x4": {
        "case_id": "rolling_x4",
        "catalog_case_id": "edit_rolling_x4",
        "native_cli_case_id": "rolling_x4",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET train.rolling_resistance TIMES 4",
        "applies_from_frame": 1,
        "physics_override": {
            "train_rolling_friction_coefficient": 0.048
        },
        "physics_diff": {
            "train_rolling_friction_coefficient": {
                "from": 0.012,
                "to": 0.048
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把无动力蓝色玩具火车的滚动阻力系数调大一些。",
                "en": "From the start of the clip, increase the unpowered blue toy train's rolling resistance coefficient."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把无动力蓝色玩具火车的滚动阻力系数增加到原来的 4 倍。",
                "en": "From frame 1 onwards, increase the unpowered blue toy train's rolling resistance coefficient to 4 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 rolling_x4 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case rolling_x4; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/thomas_dual_spring_train/physics/native.py"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/thomas_dual_spring_train/build_pcve_thomas_dual_spring_train.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "simulate",
        "verify"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/thomas_dual_spring_train/build_pcve_thomas_dual_spring_train.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/thomas_dual_spring_train/build_pcve_thomas_dual_spring_train.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/thomas_dual_spring_train/build_pcve_thomas_dual_spring_train.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/thomas_dual_spring_train/build_pcve_thomas_dual_spring_train.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/thomas_dual_spring_train/simulate_thomas_dual_spring_train.py",
    "render_entry": "scripts/rigid_elastic/thomas_dual_spring_train/render_thomas_dual_spring_train.py",
    "current_suite": "renders/pcve_suites/pcve_thomas_dual_spring_train_suite",
    "notes": [
        "native_cli_case_id selects the original scenario; catalog_case_id names the published edit_* video directory.",
        "The original simulator, renderer, runtime and worker requirements remain those documented by this scene.",
        "--stage verify performs no new physical solve; --stage simulate runs the simulate entry per case."
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
sys.path.insert(0, str(CASE.parents[1]))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "build_pcve")
# PCVE_UNIFIED_ENTRY_END

import argparse
import json
import subprocess
from tools.retained_delivery import DATA, WORK, verify

CASES = ("source", "mass_x3", "rolling_x4", "right_young_x025", "delete_right_spring", "add_wood_block")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("simulate", "verify"), default="verify")
    parser.add_argument("--cases", nargs="+", choices=CASES, default=CASES)
    parser.add_argument("--out", type=Path, default=WORK / "rebuild",
                        help="--stage simulate writes <out>/simulation/<case> (under renders/thomas_dual_spring_train/)")
    parser.add_argument("--accepted-root", type=Path, default=DATA, help="Accepted native delivery checked by --stage verify")
    args = parser.parse_args()
    if args.stage == "simulate":
        output = (args.out / "simulation").resolve()
        if WORK.resolve() not in output.parents:
            parser.error(f"Use an output under {WORK}")
        for case in args.cases:
            subprocess.run([sys.executable, "-B", str(CASE / "simulate_thomas_dual_spring_train.py"),
                            "--case", case, "--out-root", str(output)], check=True)
        raise SystemExit()
    print(json.dumps({"verified_cases": verify(args.cases, args.accepted_root)}))
