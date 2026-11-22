"""Verify the accepted native delivery, the native inputs and the published suite."""

# PCVE_EDIT_CATALOG_BEGIN
# Source description and four independent edits of the published suite.
# physics_override uses the shared-DSL scenario fields of physics/edit_vocab.py;
# the native solver keeps its own field conversions and object setup.
PCVE_SCENE = "cabinet_towel_pinch"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "厨房里一扇下柜柜门半开着,一条棉质擦手巾搭在柜门上沿,大部分垂在门外。柜门铰链把门关上,手巾随柜门一起移动,搭在门顶的部分被夹在柜门和柜框之间。",
            "en": "In a kitchen, a lower cabinet door stands half open with a cotton hand towel draped over its top edge, most of the towel hanging on the outside. The cabinet door hinge swings the door shut; the towel moves with the door, and the part over the top of the door is caught between the door and the cabinet frame."
        },
        "quantitative": {
            "zh": "厨房里一扇宽 47 cm、高 65 cm、质量 2.4 kg 的下柜柜门开始时打开 45°,一条 28 cm × 60 cm、厚 0.8 mm、约 40 g 的棉质擦手巾搭在柜门上沿,大部分垂在门外;手巾的杨氏模量为 1 MPa,摩擦系数为 1.2。0.5 s 后柜门被松开,柜门铰链以 0.9 N·m 的闭门力矩把门关上,手巾随柜门一起移动,搭在门顶的部分被夹在柜门和柜框之间。",
            "en": "In a kitchen, a lower cabinet door 47 cm wide, 65 cm tall and 2.4 kg starts open at 45°, with a cotton hand towel, 28 cm × 60 cm, 0.8 mm thick and about 40 g, draped over its top edge and mostly hanging on the outside; the towel has a Young's modulus of 1 MPa and a friction coefficient of 1.2. After 0.5 s the door is released and the cabinet door hinge closes it with a closing torque of 0.9 N·m; the towel moves with the door, and the part over the top of the door is caught between the door and the cabinet frame."
        }
    },
    "editable_objects": [
        {
            "object_id": "towel",
            "zh": "棉质擦手巾",
            "en": "the cotton hand towel",
            "in_video": True,
            "properties": ["density", "friction", "young_modulus"],
            "can_delete": False,
            "can_add": False
        },
        {
            "object_id": "door",
            "zh": "柜门",
            "en": "the cabinet door",
            "in_video": True,
            "properties": [],
            "can_delete": True,
            "can_add": False
        },
        {
            "object_id": "hinge",
            "zh": "柜门铰链",
            "en": "the cabinet door hinge",
            "in_video": True,
            "properties": ["closing_torque"],
            "can_delete": False,
            "can_add": False
        }
    ],
    "description_basis": "Physical values from the accepted native configuration (assets scenes/cabinet_towel_pinch/native/source/simulation_config.json: layout door_width, door_height, door_initial_angle, door_release_time, towel_width, towel_length; physics door_mass, towel_thickness, towel_young_modulus, towel_friction, hinge_torque; towel_mass_kg); motion as seen in the source video."
}

PCVE_EDITS = {
    "friction_x0_01": {
        "case_id": "friction_x0_01",
        "catalog_case_id": "edit_friction_x0_01",
        "native_cli_case_id": "friction_x0_01",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET towel.friction TIMES 0.01",
        "applies_from_frame": 1,
        "physics_override": {
            "towel_friction": 0.012
        },
        "physics_diff": {
            "towel_friction": {
                "from": 1.2,
                "to": 0.012
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把棉质擦手巾的摩擦系数调小一些。",
                "en": "From the start of the clip, decrease the cotton hand towel's friction coefficient."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把棉质擦手巾的摩擦系数减少到原来的 0.01 倍。",
                "en": "From frame 1 onwards, reduce the cotton hand towel's friction coefficient to 0.01 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 friction_x0_01 案例;按 edit_dsl 和 physics_override 改动手巾的摩擦系数,从共同的预稳定状态重新求解并渲染。",
            "en": "Select native case friction_x0_01; apply edit_dsl and physics_override to the towel friction coefficient, solve from the shared pre-settled state and render."
        },
        "definition_source": "scripts/rigid_elastic/cabinet_towel_pinch/physics/edit_vocab.py"
    },
    "hinge_torque_x0_03": {
        "case_id": "hinge_torque_x0_03",
        "catalog_case_id": "edit_hinge_torque_x0_03",
        "native_cli_case_id": "hinge_torque_x0_03",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET hinge.closing_torque TIMES 0.03",
        "applies_from_frame": 1,
        "physics_override": {
            "hinge_torque": 0.027
        },
        "physics_diff": {
            "hinge_torque": {
                "from": 0.9,
                "to": 0.027
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把柜门铰链的闭门力矩调小一些。",
                "en": "From the start of the clip, decrease the cabinet door hinge's closing torque."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把柜门铰链的闭门力矩减少到原来的 0.03 倍。",
                "en": "From frame 1 onwards, reduce the cabinet door hinge's closing torque to 0.03 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 hinge_torque_x0_03 案例;按 edit_dsl 和 physics_override 改动铰链闭门力矩,从共同的预稳定状态重新求解并渲染。",
            "en": "Select native case hinge_torque_x0_03; apply edit_dsl and physics_override to the hinge closing torque, solve from the shared pre-settled state and render."
        },
        "definition_source": "scripts/rigid_elastic/cabinet_towel_pinch/physics/edit_vocab.py"
    },
    "young_modulus_x30": {
        "case_id": "young_modulus_x30",
        "catalog_case_id": "edit_young_modulus_x30",
        "native_cli_case_id": "young_modulus_x30",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET towel.young_modulus TIMES 30",
        "applies_from_frame": 1,
        "physics_override": {
            "towel_young_modulus": 30000000.0
        },
        "physics_diff": {
            "towel_young_modulus": {
                "from": 1000000.0,
                "to": 30000000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把棉质擦手巾的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the cotton hand towel's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把棉质擦手巾的杨氏模量增加到原来的 30 倍。",
                "en": "From frame 1 onwards, increase the cotton hand towel's Young's modulus to 30 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 young_modulus_x30 案例;按 edit_dsl 和 physics_override 改动手巾的杨氏模量,从共同的预稳定状态重新求解并渲染。",
            "en": "Select native case young_modulus_x30; apply edit_dsl and physics_override to the towel Young's modulus, solve from the shared pre-settled state and render."
        },
        "definition_source": "scripts/rigid_elastic/cabinet_towel_pinch/physics/edit_vocab.py"
    },
    "delete_door": {
        "case_id": "delete_door",
        "catalog_case_id": "edit_delete_door",
        "native_cli_case_id": "delete_door",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE door",
        "applies_from_frame": 1,
        "physics_override": {
            "door_present": [
                0
            ]
        },
        "physics_diff": {
            "door_present": {
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
                "zh": "从视频一开始,把柜门从场景中删除。",
                "en": "From the start of the clip, remove the cabinet door from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把柜门从场景中删除。",
                "en": "From frame 1 onwards, remove the cabinet door from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 delete_door 案例;不创建柜门刚体和铰链,其余物体从共同的预稳定状态重新求解并渲染。",
            "en": "Select native case delete_door; the door body and its hinge are not created, everything else is solved from the shared pre-settled state and rendered."
        },
        "definition_source": "scripts/rigid_elastic/cabinet_towel_pinch/physics/edit_vocab.py"
    },
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/cabinet_towel_pinch/build_pcve_cabinet_towel_pinch.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "verify"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/cabinet_towel_pinch/build_pcve_cabinet_towel_pinch.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/cabinet_towel_pinch/build_pcve_cabinet_towel_pinch.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/cabinet_towel_pinch/build_pcve_cabinet_towel_pinch.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/cabinet_towel_pinch/build_pcve_cabinet_towel_pinch.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/cabinet_towel_pinch/simulate_cabinet_towel_pinch.py",
    "render_entry": "scripts/rigid_elastic/cabinet_towel_pinch/render_cabinet_towel_pinch.py",
    "current_suite": "renders/pcve_suites/pcve_cabinet_towel_pinch_suite",
    "notes": [
        "native_cli_case_id selects the native case; catalog_case_id names the published edit_* video directory.",
        "Native solves run through tools/worker.py with the staged libuipc runtime; renders run there (--gpu-uuid auto) or directly on a claimed GPU.",
        "--stage verify reads the accepted native results and does not solve anything."
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

sys.path.insert(0, str(CASE))
import argparse
import json
from scene_paths import CASES, output_path

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", choices=("verify",), default="verify")
    p.add_argument("--cases", nargs="+", choices=CASES, default=CASES)
    p.add_argument("--out", type=Path, help="also write the verify report to <out>/verify_report.json")
    a = p.parse_args()
    from tools.retained_delivery import verify
    report = json.dumps(verify(a.cases), indent=1)
    print(report)
    if a.out is not None:
        out = output_path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "verify_report.json").write_text(report + "\n", encoding="utf-8")
