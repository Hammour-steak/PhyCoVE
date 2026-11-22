"""Verify and package book_pillow_bedroom: the accepted physics delivery and the published video suite.

Stages: verify (default, read-only), prepare (asset check), package (strict PCVE packager over a
fresh suite), annotate (write catalog prompts, editable objects and ground truth into a suite).
"""

# PCVE_EDIT_CATALOG_BEGIN
# Source description and five independent edits of the published suite.
# Values in physics_override use the recorded shared-DSL/native-plan schema;
# scene-native adapters retain all required solver-field and presence conversions.
PCVE_SCENE = "book_pillow_bedroom"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "卧室的床上，一本蓝色书从枕头上方由静止落下，砸在枕头上，枕头和下面的被子被压得凹陷下去。",
            "en": "In a bedroom, a blue book is released from rest above the bed and drops onto the pillow, pressing the pillow and the duvet beneath it down."
        },
        "quantitative": {
            "zh": "卧室的床上，一本 24 × 17 × 3.6 cm、0.5 kg 的蓝色书从枕头上方约 30 cm 处由静止落下，砸在约 65 × 45 × 16 cm、杨氏模量 400 Pa 的枕头上，枕头和下面的被子被压得凹陷下去。",
            "en": "In a bedroom, a 24 × 17 × 3.6 cm, 0.5 kg blue book is released from rest about 30 cm above the pillow and drops onto it; the pillow, about 65 × 45 × 16 cm with a Young's modulus of 400 Pa, and the duvet beneath it are pressed down."
        }
    },
    "description_basis": "Numbers from the accepted physics configuration (book 0.24 x 0.17 x 0.036 m, 0.5 kg; pillow Young's modulus 400 Pa) and the source native cache at frame 1 (lowest book corner 0.30 m above the pillow top; pillow bounding box 0.65 x 0.45 x 0.16 m). No colour is given for the pillow or the bedding, so the text holds for every look of this scene.",
    "editable_objects": [
        {
            "object_id": "book",
            "zh": "蓝色书",
            "en": "the blue book",
            "properties": [
                "mass"
            ],
            "can_delete": False
        },
        {
            "object_id": "pillow",
            "zh": "枕头",
            "en": "the pillow",
            "properties": [
                "young_modulus"
            ],
            "can_delete": True
        }
    ]
}

PCVE_EDITS = {
    "heavy_book": {
        "case_id": "heavy_book",
        "catalog_case_id": "edit_heavy_book",
        "native_cli_case_id": "heavy_book",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET book.mass TIMES 2",
        "applies_from_frame": 1,
        "physics_override": {
            "phone_mass_kg": 1.0
        },
        "physics_diff": {
            "phone_mass_kg": {
                "from": 0.5,
                "to": 1.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把蓝色书的质量调大一些。",
                "en": "From the start of the clip, increase the blue book's mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把蓝色书的质量增加到原来的 2 倍。",
                "en": "From frame 1 onwards, increase the blue book's mass to 2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 heavy_book 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case heavy_book; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/book_pillow_bedroom/physics/physics.py",
        "prompt_source": "Rendered with pcve_edit_dsl.make_prompts from edit_dsl and edit_vocab.VOCAB"
    },
    "firm_pillow": {
        "case_id": "firm_pillow",
        "catalog_case_id": "edit_firm_pillow",
        "native_cli_case_id": "firm_pillow",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET pillow.young_modulus TIMES 5",
        "applies_from_frame": 1,
        "physics_override": {
            "pillow_young_modulus_pa": 2000.0
        },
        "physics_diff": {
            "pillow_young_modulus_pa": {
                "from": 400.0,
                "to": 2000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把枕头的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the pillow's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把枕头的杨氏模量增加到原来的 5 倍。",
                "en": "From frame 1 onwards, increase the pillow's Young's modulus to 5 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 firm_pillow 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case firm_pillow; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/book_pillow_bedroom/physics/physics.py",
        "prompt_source": "Rendered with pcve_edit_dsl.make_prompts from edit_dsl and edit_vocab.VOCAB"
    },
    "add_bedside_book": {
        "case_id": "add_bedside_book",
        "catalog_case_id": "edit_add_bedside_book",
        "native_cli_case_id": "add_bedside_book",
        "kind": "edit",
        "operation": "ADD",
        "edit_dsl": "ADD extra_book BETWEEN book AND bed_below_book AT 1/3 FROM bed_below_book",
        "native_edit_dsl": "ADD extra_book AT PRESET landing_point",
        "applies_from_frame": 1,
        "physics_override": {
            "accent_book_present": [
                1
            ]
        },
        "physics_diff": {
            "accent_book_present": {
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
                "zh": "从视频一开始,在蓝色书和蓝色书正下方的床垫面的连线上、靠近蓝色书正下方的床垫面的地方,放一个平放的棕色精装本。",
                "en": "From the start of the clip, place a brown book lying flat on the line between the blue book and the mattress top directly below the blue book, closer to the mattress top directly below the blue book."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,在蓝色书和蓝色书正下方的床垫面连线的三等分点上放一个平放的棕色精装本,取靠近蓝色书正下方的床垫面的那个。",
                "en": "From frame 1 onwards, place a brown book lying flat on the line between the blue book and the mattress top directly below the blue book, one third of the way from the mattress top directly below the blue book to the blue book."
            }
        },
        "how_to_edit": {
            "zh": "选择 add_bedside_book 案例；按 native_edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case add_bedside_book; apply native_edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/book_pillow_bedroom/physics/physics.py",
        "prompt_source": "Prompts are pcve_edit_dsl.make_prompts(parse(edit_dsl, VOCAB), VOCAB) with this scene's edit_vocab.VOCAB. The endpoints of edit_dsl carry display-only GeometryAnchors in edit_vocab.py at their frame-1 positions; the division point is 0.74 cm from the added body's frame-1 centre. The solver still runs native_edit_dsl; physics and video are unchanged."
    },
    "soft_pillow": {
        "case_id": "soft_pillow",
        "catalog_case_id": "edit_soft_pillow",
        "native_cli_case_id": "soft_pillow",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET pillow.young_modulus TIMES 0.5",
        "applies_from_frame": 1,
        "physics_override": {
            "pillow_young_modulus_pa": 200.0
        },
        "physics_diff": {
            "pillow_young_modulus_pa": {
                "from": 400.0,
                "to": 200.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把枕头的杨氏模量调小一些。",
                "en": "From the start of the clip, decrease the pillow's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把枕头的杨氏模量减少到原来的 0.5 倍。",
                "en": "From frame 1 onwards, reduce the pillow's Young's modulus to 0.5 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 soft_pillow 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case soft_pillow; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/book_pillow_bedroom/physics/physics.py",
        "prompt_source": "Rendered with pcve_edit_dsl.make_prompts from edit_dsl and edit_vocab.VOCAB"
    },
    "remove_pillow": {
        "case_id": "remove_pillow",
        "catalog_case_id": "edit_remove_pillow",
        "native_cli_case_id": "remove_pillow",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE pillow",
        "applies_from_frame": 1,
        "physics_override": {
            "pillow_present": [
                0
            ]
        },
        "physics_diff": {
            "pillow_present": {
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
                "zh": "从视频一开始,把枕头从场景中删除。",
                "en": "From the start of the clip, remove the pillow from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把枕头从场景中删除。",
                "en": "From frame 1 onwards, remove the pillow from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 remove_pillow 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case remove_pillow; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/book_pillow_bedroom/physics/physics.py",
        "prompt_source": "Rendered with pcve_edit_dsl.make_prompts from edit_dsl and edit_vocab.VOCAB"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/book_pillow_bedroom/build_pcve_book_pillow_bedroom.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "verify",
        "prepare",
        "package"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/book_pillow_bedroom/build_pcve_book_pillow_bedroom.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/book_pillow_bedroom/build_pcve_book_pillow_bedroom.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/book_pillow_bedroom/build_pcve_book_pillow_bedroom.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/book_pillow_bedroom/build_pcve_book_pillow_bedroom.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/book_pillow_bedroom/simulate_book_pillow_bedroom.py",
    "render_entry": "scripts/rigid_elastic/book_pillow_bedroom/render_book_pillow_bedroom.py",
    "current_suite": "renders/pcve_suites/pcve_book_pillow_bedroom_suite",
    "notes": [
        "native_cli_case_id selects the original scenario; catalog_case_id names the published edit_* video directory.",
        "edit_dsl is the statement in the shared PCVE edit DSL that the prompts are rendered from; for SET and DELETE it is also the native statement the solver adapter executes, for the ADD the native preset statement is in native_edit_dsl.",
        "Builders that only verify/package retained results do not perform a new physical solve; use the simulate/render entries for reproduction."
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
CASE=Path(__file__).resolve().parent
SCRIPTS=CASE.parents[1]
sys.path.insert(0,str(SCRIPTS))
if __name__=='__main__':
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__,'build_pcve')
# PCVE_UNIFIED_ENTRY_END

import argparse
import json
import subprocess
from scene_paths import SCENE,native_delivery,output_path,suite_dir


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    cases=json.loads((CASE/'entrypoints.json').read_bytes())['entrypoints']['build_pcve']['cases']
    parser.add_argument('--stage',choices=('verify','prepare','package'),default='verify')
    parser.add_argument('--cases',nargs='+',choices=cases,default=cases)
    parser.add_argument('--out-root',type=Path,help='package: fresh output')
    parser.add_argument('--delivery',type=Path,help='verify: accepted physics delivery (default: scene_manifest.json native_delivery)')
    parser.add_argument('--suite',type=Path,help='verify: video suite (default: scene_manifest.json canonical_suites)')
    parser.add_argument('--renders-root',type=Path,help='package: directory holding a fresh pcve_'+SCENE+'_suite')
    args=parser.parse_args()
    if args.stage=='verify':
        sys.path.insert(0,str(CASE/'tools'))
        from verify_delivery import verify
        print(json.dumps(verify(args.delivery or native_delivery(),args.suite or suite_dir(),args.cases),indent=2,ensure_ascii=False))
    elif args.stage=='prepare':
        subprocess.run([sys.executable,'-B',str(SCRIPTS/'download_assets.py'),
                        '--scene','rigid_elastic/'+SCENE,'--check'],check=True)
    else:
        if args.out_root is None or args.renders_root is None or set(args.cases)!=set(cases):
            parser.error('Package all six cases from an explicit --renders-root to a fresh --out-root')
        out=output_path(args.out_root)
        if out.exists():
            parser.error('Choose a fresh package output')
        subprocess.run([sys.executable,'-B',str(SCRIPTS/'build_benchmark.py'),'--renders-root',
                        str(args.renders_root.resolve()),'--out-root',str(out),
                        '--scenes',SCENE,'--hardlink-state-caches'],check=True)
