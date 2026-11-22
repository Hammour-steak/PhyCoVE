"""Verify the accepted native delivery, the native inputs and the published suite."""

# PCVE_EDIT_CATALOG_BEGIN
# Source description and five independent edits of the published suite.
# physics_override uses the shared-DSL scenario fields of physics/edit_vocab.py;
# the native solver keeps its own field conversions and object setup.
PCVE_SCENE = "scarf_chair_slip"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "房间里书桌旁有一把木椅,一条带流苏的棉质围巾搭在椅背顶上,长的一端垂向椅面,短的一端垂在椅背后面,两端都没有碰到椅面。围巾从静止开始滑下椅背,落在椅面上堆成一团。",
            "en": "Beside a desk in a room, a fringed cotton scarf hangs over the top of a wooden chair's backrest, its long end hanging toward the seat and its short end behind the backrest, neither end touching the seat. Starting at rest, the scarf slides off the backrest and lands in a heap on the seat."
        },
        "quantitative": {
            "zh": "房间里书桌旁有一把高 1.08 m、椅面高 46 cm、质量 6.7 kg 的木椅。一条宽 27 cm、长 94.5 cm(含两端各 3.5 cm 的流苏)、厚 0.35 mm、质量约 36 g 的棉质围巾搭在椅背顶上,长的一端向椅面一侧垂下约 60 cm,短的一端在椅背后面垂下约 18 cm,两端离椅面都还有约 8 cm;围巾的杨氏模量为 4 MPa,与木椅之间的摩擦系数为 0.32。围巾从静止开始滑下椅背,约 1 s 后落在椅面上堆成一团。",
            "en": "Beside a desk in a room stands a wooden chair 1.08 m tall with a 46 cm seat height and a mass of 6.7 kg. A fringed cotton scarf 27 cm wide, 94.5 cm long including 3.5 cm of fringe at each end, 0.35 mm thick and about 36 g hangs over the top of the backrest: its long end hangs about 60 cm toward the seat and its short end about 18 cm behind the backrest, both ends still about 8 cm above the seat. The scarf has a Young's modulus of 4 MPa and a friction coefficient of 0.32 against the wooden chair. Starting at rest, the scarf slides off the backrest and after about 1 s lands in a heap on the seat."
        }
    },
    "editable_objects": [
        {
            "object_id": "scarf",
            "zh": "棉质围巾",
            "en": "the cotton scarf",
            "in_video": True,
            "properties": ["density", "friction", "young_modulus"],
            "can_delete": False,
            "can_add": False
        },
        {
            "object_id": "chair",
            "zh": "木椅",
            "en": "the wooden chair",
            "in_video": True,
            "properties": [],
            "can_delete": True,
            "can_add": False
        },
        {
            "object_id": "landing_book",
            "zh": "精装书",
            "en": "a hardcover book",
            "in_video": False,
            "properties": [],
            "can_delete": False,
            "can_add": True
        }
    ],
    "description_basis": "Physical values from the accepted native configuration (assets scenes/scarf_chair_slip/native/source/simulation_config.json: layout width, long_side, short_side, fringe_length, release_time; physics scarf_thickness, scarf_young_modulus, scarf_friction, chair_mass; material_length_m, scarf_mass_kg) and the chair collision mesh (1.081 m tall, seat top at 0.456 m); timing and heap measured on the native source cache (scarf below 0.53 m from frame 25)."
}

PCVE_EDITS = {
    "young_modulus_x10": {
        "case_id": "young_modulus_x10",
        "catalog_case_id": "edit_young_modulus_x10",
        "native_cli_case_id": "young_modulus_x10",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET scarf.young_modulus TIMES 10",
        "applies_from_frame": 1,
        "physics_override": {
            "scarf_young_modulus": 40000000.0
        },
        "physics_diff": {
            "scarf_young_modulus": {
                "from": 4000000.0,
                "to": 40000000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把棉质围巾的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the cotton scarf's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把棉质围巾的杨氏模量增加到原来的 10 倍。",
                "en": "From frame 1 onwards, increase the cotton scarf's Young's modulus to 10 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 young_modulus_x10 案例;按 edit_dsl 和 physics_override 改动围巾的杨氏模量(拉伸、剪切和弯曲按同一材料比例缩放),从原场景第 1 帧的状态重新求解并渲染。",
            "en": "Select native case young_modulus_x10; apply edit_dsl and physics_override to the scarf Young's modulus (stretch, shear and bending scale together), solve from frame 1 of the source and render."
        },
        "definition_source": "scripts/rigid_elastic/scarf_chair_slip/physics/edit_vocab.py"
    },
    "density_x2": {
        "case_id": "density_x2",
        "catalog_case_id": "edit_density_x2",
        "native_cli_case_id": "density_x2",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET scarf.density TIMES 2",
        "applies_from_frame": 1,
        "physics_override": {
            "scarf_density": 840.0
        },
        "physics_diff": {
            "scarf_density": {
                "from": 420.0,
                "to": 840.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把棉质围巾的密度调大一些。",
                "en": "From the start of the clip, increase the cotton scarf's density."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把棉质围巾的密度增加到原来的 2 倍。",
                "en": "From frame 1 onwards, increase the cotton scarf's density to 2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 density_x2 案例;按 edit_dsl 和 physics_override 改动围巾的密度,从原场景第 1 帧的状态重新求解并渲染。",
            "en": "Select native case density_x2; apply edit_dsl and physics_override to the scarf density, solve from frame 1 of the source and render."
        },
        "definition_source": "scripts/rigid_elastic/scarf_chair_slip/physics/edit_vocab.py"
    },
    "friction_x0_2": {
        "case_id": "friction_x0_2",
        "catalog_case_id": "edit_friction_x0_2",
        "native_cli_case_id": "friction_x0_2",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET scarf.friction TIMES 0.2",
        "applies_from_frame": 1,
        "physics_override": {
            "scarf_friction": 0.064
        },
        "physics_diff": {
            "scarf_friction": {
                "from": 0.32,
                "to": 0.064
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把棉质围巾的摩擦系数调小一些。",
                "en": "From the start of the clip, decrease the cotton scarf's friction coefficient."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把棉质围巾的摩擦系数减少到原来的 0.2 倍。",
                "en": "From frame 1 onwards, reduce the cotton scarf's friction coefficient to 0.2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 friction_x0_2 案例;按 edit_dsl 和 physics_override 改动围巾与木椅之间的摩擦系数(围巾与地面、书本及自身的摩擦不变),从原场景第 1 帧的状态重新求解并渲染。",
            "en": "Select native case friction_x0_2; apply edit_dsl and physics_override to the scarf-chair friction coefficient (scarf-floor, scarf-book and self friction unchanged), solve from frame 1 of the source and render."
        },
        "definition_source": "scripts/rigid_elastic/scarf_chair_slip/physics/edit_vocab.py"
    },
    "add_landing_book": {
        "case_id": "add_landing_book",
        "catalog_case_id": "edit_add_landing_book",
        "native_cli_case_id": "add_landing_book",
        "kind": "edit",
        "operation": "ADD",
        "edit_dsl": "ADD landing_book BETWEEN scarf AND seat_middle AT 1/10 FROM seat_middle",
        "native_edit_dsl": "ADD landing_book AT PRESET seat_center",
        "applies_from_frame": 1,
        "physics_override": {
            "book_active": [
                1
            ]
        },
        "physics_diff": {
            "book_active": {
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
                "zh": "从视频一开始,在棉质围巾和木椅椅面中间的连线上、靠近木椅椅面中间的地方,放一个平放的精装书。",
                "en": "From the start of the clip, place a hardcover book lying flat on the line between the cotton scarf and the middle of the wooden chair's seat, closer to the middle of the wooden chair's seat."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,在棉质围巾和木椅椅面中间连线的十等分点上放一个平放的精装书,取靠近木椅椅面中间的那个。",
                "en": "From frame 1 onwards, place a hardcover book lying flat on the line between the cotton scarf and the middle of the wooden chair's seat, one tenth of the way from the middle of the wooden chair's seat to the cotton scarf."
            }
        },
        "prompt_note": "Prompts are pcve_edit_dsl.make_prompts(parse(edit_dsl, VOCAB), VOCAB) with this scene's edit_vocab.VOCAB. The endpoints of edit_dsl carry display-only GeometryAnchors in edit_vocab.py at their frame-1 positions; the division point is 1.00 cm from the added body's frame-1 centre. The solver still runs native_edit_dsl; physics and video are unchanged.",
        "how_to_edit": {
            "zh": "选择 add_landing_book 案例;按 native_edit_dsl 的预设位置在椅面上方加入独立的精装书刚体,其余物体从原场景第 1 帧的状态重新求解并渲染。",
            "en": "Select native case add_landing_book; add the free hardcover-book body at the preset position of native_edit_dsl over the seat, solve everything else from frame 1 of the source and render."
        },
        "definition_source": "scripts/rigid_elastic/scarf_chair_slip/physics/edit_vocab.py"
    },
    "delete_chair": {
        "case_id": "delete_chair",
        "catalog_case_id": "edit_delete_chair",
        "native_cli_case_id": "delete_chair",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE chair",
        "applies_from_frame": 1,
        "physics_override": {
            "chair_active": [
                0
            ]
        },
        "physics_diff": {
            "chair_active": {
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
                "zh": "从视频一开始,把木椅从场景中删除。",
                "en": "From the start of the clip, remove the wooden chair from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把木椅从场景中删除。",
                "en": "From frame 1 onwards, remove the wooden chair from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 delete_chair 案例;不创建木椅刚体,围巾从原场景第 1 帧的状态重新求解并渲染。",
            "en": "Select native case delete_chair; the chair body is not created, the scarf is solved from frame 1 of the source and rendered."
        },
        "definition_source": "scripts/rigid_elastic/scarf_chair_slip/physics/edit_vocab.py"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/scarf_chair_slip/build_pcve_scarf_chair_slip.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "verify"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/scarf_chair_slip/build_pcve_scarf_chair_slip.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/scarf_chair_slip/build_pcve_scarf_chair_slip.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/scarf_chair_slip/build_pcve_scarf_chair_slip.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/scarf_chair_slip/build_pcve_scarf_chair_slip.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/scarf_chair_slip/simulate_scarf_chair_slip.py",
    "render_entry": "scripts/rigid_elastic/scarf_chair_slip/render_scarf_chair_slip.py",
    "current_suite": "renders/pcve_suites/pcve_scarf_chair_slip_suite",
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
