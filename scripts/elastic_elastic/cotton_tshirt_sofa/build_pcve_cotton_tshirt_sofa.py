"""Edit catalog of the scene and verification of the accepted native delivery (--stage verify)."""

# PCVE_EDIT_CATALOG_BEGIN
# Source descriptions and five independent edits for the current published suite.
# Values in physics_override use the recorded shared-DSL/native-plan schema;
# scene-native adapters retain all required solver-field and presence conversions.
PCVE_SCENE = "cotton_tshirt_sofa"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "客厅内，一件棉质T恤落到沙发上，与沙发接触后发生折叠和形变。",
            "en": "In a living room, a cotton T-shirt falls onto a sofa, contacting the sofa and folding and deforming."
        },
        "quantitative": {
            "zh": "客厅内，一件质量约 103 g、面密度 180 g/m² 的棉质T恤，最低处离地 82 cm，松开后落到沙发右侧的坐垫上，与坐垫接触后发生折叠和形变。T恤与沙发之间的摩擦系数为 0.6，坐垫是杨氏模量 12 kPa 的软泡沫。",
            "en": "In a living room, a cotton T-shirt of about 103 g (180 g/m²), its lowest point 82 cm above the floor, is let go and falls onto the right seat cushion of a sofa, folding and deforming as it settles on the cushion. The friction coefficient between the shirt and the sofa is 0.6, and the seat cushion is soft foam with a Young's modulus of 12 kPa."
        }
    },
    "description_basis": "Current scene code and retained source-video inspection; quantitative values from tools/native/scene_spec.json baseline and the native source simulation_config (shirt mass 0.103 kg, 180 g/m^2, lowest point 0.82 m, friction 0.6, seat foam E 12 kPa). Physical outcomes beyond the visible interaction are not asserted."
}

PCVE_EDITS = {
    "heavy_shirt": {
        "case_id": "heavy_shirt",
        "catalog_case_id": "edit_heavy_shirt",
        "native_cli_case_id": "heavy_shirt",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET shirt.density TIMES 3",
        "applies_from_frame": 1,
        "physics_override": {
            "shirt_density_kg_m3": 1200.0
        },
        "physics_diff": {
            "shirt_density_kg_m3": {
                "from": 400.0,
                "to": 1200.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把棉质 T 恤的密度调大一些。",
                "en": "From the start of the clip, increase the cotton T-shirt's density."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把棉质 T 恤的密度增加到原来的 3 倍。",
                "en": "From frame 1 onwards, increase the cotton T-shirt's density to 3 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 heavy_shirt 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case heavy_shirt; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/elastic_elastic/cotton_tshirt_sofa/tools/native/edit_vocab.py"
    },
    "remove_seat": {
        "case_id": "remove_seat",
        "catalog_case_id": "edit_remove_seat",
        "native_cli_case_id": "remove_seat",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE seat",
        "applies_from_frame": 1,
        "physics_override": {
            "seat_present": [
                0
            ]
        },
        "physics_diff": {
            "seat_present": {
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
                "zh": "从视频一开始,把右侧落点坐垫从场景中删除。",
                "en": "From the start of the clip, remove the right landing seat cushion from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把右侧落点坐垫从场景中删除。",
                "en": "From frame 1 onwards, remove the right landing seat cushion from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 remove_seat 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case remove_seat; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/elastic_elastic/cotton_tshirt_sofa/tools/native/edit_vocab.py"
    },
    "low_friction": {
        "case_id": "low_friction",
        "catalog_case_id": "edit_low_friction",
        "native_cli_case_id": "low_friction",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET shirt.friction TIMES 0.25",
        "applies_from_frame": 1,
        "physics_override": {
            "shirt_friction": 0.15
        },
        "physics_diff": {
            "shirt_friction": {
                "from": 0.6,
                "to": 0.15
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把棉质 T 恤的接触摩擦系数调小一些。",
                "en": "From the start of the clip, decrease the cotton T-shirt's contact friction coefficient."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把棉质 T 恤的接触摩擦系数减少到原来的 0.25 倍。",
                "en": "From frame 1 onwards, reduce the cotton T-shirt's contact friction coefficient to 0.25 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 low_friction 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case low_friction; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/elastic_elastic/cotton_tshirt_sofa/tools/native/edit_vocab.py"
    },
    "stiff_shirt": {
        "case_id": "stiff_shirt",
        "catalog_case_id": "edit_stiff_shirt",
        "native_cli_case_id": "stiff_shirt",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET shirt.young_modulus TIMES 10",
        "applies_from_frame": 1,
        "physics_override": {
            "shirt_young_modulus_pa": 3000000.0
        },
        "physics_diff": {
            "shirt_young_modulus_pa": {
                "from": 300000.0,
                "to": 3000000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把棉质 T 恤的有效杨氏模量调大一些。",
                "en": "From the start of the clip, increase the cotton T-shirt's effective Young’s modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把棉质 T 恤的有效杨氏模量增加到原来的 10 倍。",
                "en": "From frame 1 onwards, increase the cotton T-shirt's effective Young’s modulus to 10 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 stiff_shirt 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case stiff_shirt; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/elastic_elastic/cotton_tshirt_sofa/tools/native/edit_vocab.py"
    },
    "low_friction_at_frame_10": {
        "case_id": "low_friction_at_frame_10",
        "catalog_case_id": "edit_low_friction_at_frame_10",
        "native_cli_case_id": "low_friction_at_frame_10",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET shirt.friction TIMES 0.25 AT FRAME 10",
        "applies_from_frame": 10,
        "physics_override": {
            "shirt_friction": 0.15
        },
        "physics_diff": {
            "shirt_friction": {
                "from": 0.6,
                "to": 0.15
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "在视频前段,把棉质 T 恤的接触摩擦系数调小一些。",
                "en": "Early in the clip, decrease the cotton T-shirt's contact friction coefficient."
            },
            "quantitative": {
                "zh": "从第 10 帧开始,把棉质 T 恤的接触摩擦系数减少到原来的 0.25 倍。",
                "en": "From frame 10 onwards, reduce the cotton T-shirt's contact friction coefficient to 0.25 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 low_friction_at_frame_10 案例；第 1–9 帧就是源视频的原生状态，求解器从源缓存恢复第 10 帧（t=9/24 s）T 恤和坐垫的顶点位置与速度，从这一帧起把 T 恤的接触摩擦系数设为 0.15 并继续求解。",
            "en": "Select native case low_friction_at_frame_10; frames 1-9 are the source native states. The solver restores the shirt and seat vertex positions and velocities of frame 10 (t=9/24 s) from the source cache, sets the shirt contact friction to 0.15 from that frame on and keeps solving."
        },
        "definition_source": "scripts/elastic_elastic/cotton_tshirt_sofa/tools/native/edit_vocab.py"
    },
}

PCVE_EXECUTION = {
    "builder": "scripts/elastic_elastic/cotton_tshirt_sofa/build_pcve_cotton_tshirt_sofa.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "verify"
    ],
    "native_help_command": [
        "python3",
        "scripts/elastic_elastic/cotton_tshirt_sofa/build_pcve_cotton_tshirt_sofa.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/elastic_elastic/cotton_tshirt_sofa/build_pcve_cotton_tshirt_sofa.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/elastic_elastic/cotton_tshirt_sofa/build_pcve_cotton_tshirt_sofa.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/elastic_elastic/cotton_tshirt_sofa/build_pcve_cotton_tshirt_sofa.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/elastic_elastic/cotton_tshirt_sofa/simulate_cotton_tshirt_sofa.py",
    "render_entry": "scripts/elastic_elastic/cotton_tshirt_sofa/render_cotton_tshirt_sofa.py",
    "current_suite": "renders/pcve_suites/pcve_cotton_tshirt_sofa_suite",
    "notes": [
        "native_cli_case_id selects the original scenario; catalog_case_id names the published edit_* video directory.",
        "The original simulator, renderer, runtime and worker requirements remain those documented by this scene.",
        "The builder only verifies the accepted delivery and does not solve; use the simulate/render entries for reproduction.",
        "The timed edit low_friction_at_frame_10 continues the source solve from frame 10 (simulate --case low_friction_at_frame_10 --source-cache ...); its merged native cache is published in inputs/native_timed/low_friction_at_frame_10/ of the suite."
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
from scene_driver import CASES,TIMED_CASES,output
from tools.retained_delivery import verify
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage",choices=("verify",),default="verify")
    p.add_argument("--cases",nargs="+",choices=CASES+TIMED_CASES,default=CASES+TIMED_CASES,
                   help="full-clip cases are checked in the accepted delivery, a timed edit in the published suite's inputs/native_timed/")
    p.add_argument("--out",type=Path,help="also write the report to <out>/verify_report.json (a fresh folder beneath renders/cotton_tshirt_sofa/)")
    a=p.parse_args()
    result={"verified_cases":verify(a.cases)}
    if a.out is not None:
        out=output(a.out);out.mkdir(parents=True)
        (out/"verify_report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result))
