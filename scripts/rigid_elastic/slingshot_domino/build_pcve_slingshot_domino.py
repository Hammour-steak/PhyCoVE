"""Verify the accepted native delivery (five cases) and the published timed-edit case."""

# PCVE_EDIT_CATALOG_BEGIN
# Source descriptions and the five edits of the current published suite.
# Values in physics_override use the recorded shared-DSL/native-plan schema;
# scene-native adapters retain all required solver-field and presence conversions.
PCVE_SCENE = "slingshot_domino"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "桌面弹弓的橡皮筋释放小球，小球向木制多米诺骨牌运动并发生碰撞。",
            "en": "A tabletop slingshot releases a ball using elastic bands; the ball travels towards a wooden domino and collides with it."
        },
        "quantitative": {
            "zh": "桌面弹弓的两条扁平橡胶带(自然长度 9 cm、宽 4 mm、杨氏模量 1 MPa)把一个直径 1.5 cm、质量 1.85 g 的塑料小球弹出,小球向约 29 cm 外一块 1.2×3.5×7.5 cm、16 g 的木制多米诺骨牌运动并与它碰撞。",
            "en": "A tabletop slingshot's two flat rubber bands (9 cm rest length, 4 mm wide, Young's modulus 1 MPa) launch a plastic ball 1.5 cm in diameter and 1.85 g in mass towards a 1.2 × 3.5 × 7.5 cm, 16 g wooden domino about 29 cm away, and the ball collides with it."
        }
    },
    "description_basis": "Current scene code and retained source-video inspection; physical outcomes beyond the visible interaction are not asserted."
}

PCVE_EDITS = {
    "delete_domino": {
        "case_id": "delete_domino",
        "catalog_case_id": "edit_delete_domino",
        "native_cli_case_id": "delete_domino",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE domino",
        "applies_from_frame": 1,
        "physics_override": {
            "domino_present": [
                0
            ]
        },
        "physics_diff": {
            "domino_present": {
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
                "zh": "从视频一开始,把原有木牌从场景中删除。",
                "en": "From the start of the clip, remove the original domino from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把原有木牌从场景中删除。",
                "en": "From frame 1 onwards, remove the original domino from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 delete_domino 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case delete_domino; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/slingshot_domino/edit_vocab.py"
    },
    "heavy_ball": {
        "case_id": "heavy_ball",
        "catalog_case_id": "edit_heavy_ball",
        "native_cli_case_id": "heavy_ball",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET ball.mass TIMES 3",
        "applies_from_frame": 1,
        "physics_override": {
            "ball_mass_kg": 0.00555
        },
        "physics_diff": {
            "ball_mass_kg": {
                "from": 0.00185,
                "to": 0.00555
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把塑料小球的质量调大一些。",
                "en": "From the start of the clip, increase the plastic ball's mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把塑料小球的质量增加到原来的 3 倍。",
                "en": "From frame 1 onwards, increase the plastic ball's mass to 3 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 heavy_ball 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case heavy_ball; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/slingshot_domino/edit_vocab.py"
    },
    "heavy_domino": {
        "case_id": "heavy_domino",
        "catalog_case_id": "edit_heavy_domino",
        "native_cli_case_id": "heavy_domino",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET domino.mass TIMES 2",
        "applies_from_frame": 1,
        "physics_override": {
            "domino_mass_kg": 0.032
        },
        "physics_diff": {
            "domino_mass_kg": {
                "from": 0.016,
                "to": 0.032
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把原有木牌的质量调大一些。",
                "en": "From the start of the clip, increase the original domino's mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把原有木牌的质量增加到原来的 2 倍。",
                "en": "From frame 1 onwards, increase the original domino's mass to 2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 heavy_domino 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case heavy_domino; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/slingshot_domino/edit_vocab.py"
    },
    "soft_bands": {
        "case_id": "soft_bands",
        "catalog_case_id": "edit_soft_bands",
        "native_cli_case_id": "soft_bands",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET bands.young_modulus TIMES 0.5",
        "applies_from_frame": 1,
        "physics_override": {
            "young_modulus_pa": 500000.0
        },
        "physics_diff": {
            "young_modulus_pa": {
                "from": 1000000.0,
                "to": 500000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把两条扁平橡胶带的杨氏模量调小一些。",
                "en": "From the start of the clip, decrease the two flat rubber bands' Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把两条扁平橡胶带的杨氏模量减少到原来的 0.5 倍。",
                "en": "From frame 1 onwards, reduce the two flat rubber bands' Young's modulus to 0.5 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 soft_bands 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case soft_bands; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/slingshot_domino/edit_vocab.py"
    },
    "heavy_domino_at_frame_12": {
        "case_id": "heavy_domino_at_frame_12",
        "catalog_case_id": "edit_heavy_domino_at_frame_12",
        "native_cli_case_id": "heavy_domino_at_frame_12",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET domino.mass TIMES 10 AT FRAME 12",
        "applies_from_frame": 12,
        "physics_override": {
            "domino_mass_kg": 0.16
        },
        "physics_diff": {
            "domino_mass_kg": {
                "from": 0.016,
                "to": 0.16
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "在视频前段,把原有木牌的质量调大一些。",
                "en": "Early in the clip, increase the original domino's mass."
            },
            "quantitative": {
                "zh": "从第 12 帧开始,把原有木牌的质量增加到原来的 10 倍。",
                "en": "From frame 12 onwards, increase the original domino's mass to 10 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "运行 heavy_domino_at_frame_12 原生案例,在第12帧通过 PyBullet changeDynamics 将骨牌质量及转动惯量增至10倍,从当前状态继续求解并渲染。",
            "en": "Run native case heavy_domino_at_frame_12; use PyBullet changeDynamics at frame 12 to scale the domino mass and inertia by 10, then continue solving and render the native trajectory."
        },
        "definition_source": "scripts/rigid_elastic/slingshot_domino/edit_vocab.py",
        "timing": {
            "applies_from_frame": 12,
            "application_time_sec": 0.4583333333333333,
            "total_frames": 96,
            "unedited_frames": [
                1,
                11
            ]
        },
        "timed_video": {
            "switch_frame": 12,
            "method": "native_timed_physics_rerender",
            "solver_state_handoff": True
        },
        "verified_outcome": {
            "domino_remains_upright": True,
            "max_tilt_deg": 0.3538913538721176
        }
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/slingshot_domino/build_pcve_slingshot_domino.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "verify"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/slingshot_domino/build_pcve_slingshot_domino.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/slingshot_domino/build_pcve_slingshot_domino.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/slingshot_domino/build_pcve_slingshot_domino.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/slingshot_domino/build_pcve_slingshot_domino.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/slingshot_domino/simulate_slingshot_domino.py",
    "render_entry": "scripts/rigid_elastic/slingshot_domino/render_slingshot_domino.py",
    "current_suite": "renders/pcve_suites/pcve_slingshot_domino_suite",
    "notes": [
        "native_cli_case_id selects the original scenario; catalog_case_id names the published edit_* video directory.",
        "The original simulator, renderer, runtime and worker requirements remain those documented by this scene.",
        "--stage verify performs no new physical solve; use the simulate/render entries for reproduction."
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
from tools.retained_delivery import DATA, TIMED, WORK, verify

CASES=("source","soft_bands","heavy_ball","heavy_domino","delete_domino",*TIMED)

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage",choices=("verify",),default="verify")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=CASES)
    parser.add_argument("--out",type=Path,help="Also write the verify report to <out>/verify_report.json (under renders/slingshot_domino/)")
    parser.add_argument("--accepted-root",type=Path,default=DATA,help="Accepted native delivery (holds delivery/accepted)")
    args=parser.parse_args()
    report=json.dumps({"verified_cases":verify(args.cases,args.accepted_root)})
    print(report)
    if args.out is not None:
        out=args.out.resolve()
        if WORK.resolve() not in out.parents:
            parser.error(f"Write the report under {WORK}")
        out.mkdir(parents=True,exist_ok=True)
        (out/"verify_report.json").write_text(report+"\n",encoding="utf-8")
