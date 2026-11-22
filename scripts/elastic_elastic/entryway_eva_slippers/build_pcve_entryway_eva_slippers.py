"""Verify the accepted native delivery of the six cases, or check the registered assets."""

# PCVE_EDIT_CATALOG_BEGIN
# Source descriptions and five independent edits for the current published suite.
# Values in physics_override use the recorded shared-DSL/native-plan schema;
# scene-native adapters retain all required solver-field and presence conversions.
PCVE_SCENE = "entryway_eva_slippers"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "玄关地面上，一只EVA拖鞋下落，并与地面及另一只拖鞋发生接触。",
            "en": "In an entryway, an EVA slipper falls and contacts the floor and another slipper."
        },
        "quantitative": {
            "zh": "玄关石材地面上,一只 EVA 拖鞋(密度 200 kg/m³、杨氏模量 0.35 MPa)在离地约 45 cm 处以约 0.25 m/s 的水平速度下落,并与地面及另一只拖鞋发生接触。",
            "en": "In an entryway, an EVA slipper (density 200 kg/m³, Young's modulus 0.35 MPa) is released about 45 cm above the stone floor with a horizontal speed of about 0.25 m/s; it falls and contacts the floor and another slipper."
        }
    },
    "description_basis": "Current scene code and retained source-video inspection; physical outcomes beyond the visible interaction are not asserted."
}

PCVE_EDITS = {
    "slippery_floor": {
        "case_id": "slippery_floor",
        "catalog_case_id": "edit_slippery_floor",
        "native_cli_case_id": "slippery_floor",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET stone_floor.friction TIMES 0.25",
        "applies_from_frame": 1,
        "physics_override": {
            "floor_friction": 0.1375
        },
        "physics_diff": {
            "floor_friction": {
                "from": 0.55,
                "to": 0.1375
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把石材地面的接触摩擦系数调小一些。",
                "en": "From the start of the clip, decrease the stone floor's contact friction coefficient."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把石材地面的接触摩擦系数减少到原来的 0.25 倍。",
                "en": "From frame 1 onwards, reduce the stone floor's contact friction coefficient to 0.25 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 slippery_floor 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case slippery_floor; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/elastic_elastic/entryway_eva_slippers/edit_vocab.py"
    },
    "light_falling": {
        "case_id": "light_falling",
        "catalog_case_id": "edit_light_falling",
        "native_cli_case_id": "light_falling",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET falling_slipper.density TIMES 0.5",
        "applies_from_frame": 1,
        "physics_override": {
            "falling_density_kg_m3": 100.0
        },
        "physics_diff": {
            "falling_density_kg_m3": {
                "from": 200.0,
                "to": 100.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把上方落下的拖鞋的密度调小一些。",
                "en": "From the start of the clip, decrease the falling slide's density."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把上方落下的拖鞋的密度减少到原来的 0.5 倍。",
                "en": "From frame 1 onwards, reduce the falling slide's density to 0.5 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 light_falling 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case light_falling; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/elastic_elastic/entryway_eva_slippers/edit_vocab.py"
    },
    "add_shoe_tray": {
        "case_id": "add_shoe_tray",
        "catalog_case_id": "edit_add_shoe_tray",
        "native_cli_case_id": "add_shoe_tray",
        "kind": "edit",
        "operation": "ADD",
        "edit_dsl": "ADD shoe_tray BETWEEN resting_slipper AND left_floor_spot AT MIDPOINT",
        "native_edit_dsl": "ADD shoe_tray AT PRESET beside_resting_slide",
        "applies_from_frame": 1,
        "physics_override": {
            "tray_present": [
                1
            ]
        },
        "physics_diff": {
            "tray_present": {
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
                "zh": "从视频一开始,在地面上的拖鞋和地面拖鞋左侧的空地的连线上、大致中间的位置,放一个平放在地面上的带边木质鞋托盘。",
                "en": "From the start of the clip, place a wooden shoe tray with a raised rim lying flat on the floor on the line between the slide resting on the floor and the empty floor to the left of the resting slide, about midway between them."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,在地面上的拖鞋和地面拖鞋左侧的空地连线的中点放一个平放在地面上的带边木质鞋托盘。",
                "en": "From frame 1 onwards, place a wooden shoe tray with a raised rim lying flat on the floor at the midpoint of the line between the slide resting on the floor and the empty floor to the left of the resting slide."
            }
        },
        "prompt_note": "Prompts are pcve_edit_dsl.make_prompts(parse(edit_dsl, VOCAB), VOCAB) with this scene's edit_vocab.VOCAB. The endpoints of edit_dsl carry display-only GeometryAnchors in edit_vocab.py at their frame-1 positions; the division point is 1.53 cm from the added body's frame-1 centre. The solver still runs native_edit_dsl; physics and video are unchanged.",
        "how_to_edit": {
            "zh": "选择 add_shoe_tray 案例；按 native_edit_dsl 的预设位置在地面加入带边木质鞋托盘，其余物体从原场景第 1 帧的状态重新求解并渲染。",
            "en": "Select native case add_shoe_tray; add the wooden shoe tray at the preset position of native_edit_dsl on the floor, solve everything else from frame 1 of the source and render."
        },
        "definition_source": "scripts/elastic_elastic/entryway_eva_slippers/edit_vocab.py"
    },
    "remove_resting": {
        "case_id": "remove_resting",
        "catalog_case_id": "edit_remove_resting",
        "native_cli_case_id": "remove_resting",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE resting_slipper",
        "applies_from_frame": 1,
        "physics_override": {
            "resting_present": [
                0
            ]
        },
        "physics_diff": {
            "resting_present": {
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
                "zh": "从视频一开始,把地面上的拖鞋从场景中删除。",
                "en": "From the start of the clip, remove the slide resting on the floor from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把地面上的拖鞋从场景中删除。",
                "en": "From frame 1 onwards, remove the slide resting on the floor from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 remove_resting 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case remove_resting; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/elastic_elastic/entryway_eva_slippers/edit_vocab.py"
    },
    "stiff_falling": {
        "case_id": "stiff_falling",
        "catalog_case_id": "edit_stiff_falling",
        "native_cli_case_id": "stiff_falling",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET falling_slipper.young_modulus TIMES 4",
        "applies_from_frame": 1,
        "physics_override": {
            "falling_young_modulus_pa": 1400000.0
        },
        "physics_diff": {
            "falling_young_modulus_pa": {
                "from": 350000.0,
                "to": 1400000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把上方落下的拖鞋的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the falling slide's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把上方落下的拖鞋的杨氏模量增加到原来的 4 倍。",
                "en": "From frame 1 onwards, increase the falling slide's Young's modulus to 4 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 stiff_falling 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case stiff_falling; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/elastic_elastic/entryway_eva_slippers/edit_vocab.py"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/elastic_elastic/entryway_eva_slippers/build_pcve_entryway_eva_slippers.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "prepare",
        "verify"
    ],
    "native_help_command": [
        "python3",
        "scripts/elastic_elastic/entryway_eva_slippers/build_pcve_entryway_eva_slippers.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/elastic_elastic/entryway_eva_slippers/build_pcve_entryway_eva_slippers.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/elastic_elastic/entryway_eva_slippers/build_pcve_entryway_eva_slippers.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/elastic_elastic/entryway_eva_slippers/build_pcve_entryway_eva_slippers.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/elastic_elastic/entryway_eva_slippers/simulate_entryway_eva_slippers.py",
    "render_entry": "scripts/elastic_elastic/entryway_eva_slippers/render_entryway_eva_slippers.py",
    "current_suite": "renders/pcve_suites/pcve_entryway_eva_slippers_suite",
    "notes": [
        "native_cli_case_id selects the original scenario; catalog_case_id names the published edit_* video directory.",
        "The original simulator, renderer, runtime and worker requirements remain those documented by this scene.",
        "--stage verify checks the accepted native delivery and performs no new physical solve; use the simulate/render entries for reproduction."
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

import argparse,json,subprocess
from tools.retained import CASES,out_path,verify

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage",choices=("prepare","verify"),default="verify")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=CASES)
    parser.add_argument("--out",type=Path,help="Also write the verify report to <out>/verify_report.json (a fresh folder under renders/entryway_eva_slippers/)")
    args=parser.parse_args()
    if args.stage=="prepare":
        subprocess.run([sys.executable,"-B",str(CASE.parents[1]/"download_assets.py"),"--scene","entryway_eva_slippers","--check"],check=True)
        result={"prepared":True}
    else:
        result=verify(args.cases)
        if args.out is not None:
            out=out_path(args.out);out.mkdir(parents=True)
            (out/"verify_report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
