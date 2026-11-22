"""PCVE catalog of the phone_sofa_drop suite, and its package / verify stages.

--stage verify (default): check the published suite scene_manifest.json points at (videos, MP4
    sample tables, ground truth on the video clock, prompts against this catalog, registered caches);
    --require-standard also demands 1280x720 / 24 FPS / 96 frames / 4.000 s.
--stage package: encode the frames rendered by render_phone_sofa_drop.py (--render-root, default
    renders/phone_sofa_drop/render) into a new suite at --out-root (default
    renders/pcve_suites/pcve_phone_sofa_drop_suite, which must not exist yet) and point
    scene_manifest.json at it.
Prompts of the published suite are written with --export-prompts.
"""
from __future__ import annotations

# PCVE_EDIT_CATALOG_BEGIN
# Source description and the five edits of the published suite. Prompts follow the PCVE prompt
# rules (scripts/pcve_edit_dsl.py make_prompts(): timing clause first, SET by direction /
# multiple, DELETE "remove ... from the scene", ADD on the line between two visible objects).
# physics_override uses the shared-DSL schema; edit_vocab.scenario_override() converts presence
# lists to the scene's booleans and is checked against scene_spec.json. The ADD edit_dsl is
# written in the shared BETWEEN form; the scene's own preset DSL is kept in native_edit_dsl.
PCVE_SCENE = "phone_sofa_drop"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "客厅里,一部手机从中间的沙发坐垫上方由静止落下,砸在柔软的坐垫上,把坐垫压出一个凹陷后弹起,最后停在坐垫上。",
            "en": "In a living room, a phone is released from rest above the middle sofa cushion, lands on the soft cushion, presses a dent into it and bounces, and finally comes to rest on top of it."
        },
        "quantitative": {
            "zh": "客厅里,一部 14.7 cm × 7.1 cm × 0.8 cm、质量 187 g 的手机从中间的沙发坐垫上方约 26 cm 处由静止释放,重力加速度为 5 m/s²;这块坐垫约 77 cm 宽、96 cm 深、23 cm 厚,杨氏模量为 1000 Pa,手机落在坐垫上压出凹陷、弹起后停在上面。",
            "en": "In a living room, a 14.7 cm × 7.1 cm × 0.8 cm phone with a mass of 187 g is released from rest about 26 cm above the middle sofa cushion, with a gravitational acceleration of 5 m/s²; the cushion is about 77 cm wide, 96 cm deep and 23 cm thick with a Young's modulus of 1000 Pa, and the phone lands on it, presses a dent, bounces and comes to rest on top."
        }
    },
    "editable_objects": [
        {"object_id": "phone", "zh": "手机", "en": "the phone", "in_video": True,
         "properties": ["mass"], "can_delete": False, "can_add": False},
        {"object_id": "cushion", "zh": "中间的沙发坐垫", "en": "the middle sofa cushion", "in_video": True,
         "properties": ["young_modulus"], "can_delete": True, "can_add": False},
        {"object_id": "landing_pillow", "zh": "浅蓝灰色小枕头", "en": "a small blue-grey pillow", "in_video": False,
         "properties": [], "can_delete": False, "can_add": True}
    ],
    "description_basis": "Numbers from the solver configuration and the t = 0 state of the 4 s source cache: phone 0.0706 x 0.1466 x 0.00825 m, 0.187 kg, released at rest with its lowest corner 0.258 m above the cushion top under it; cushion 0.773 x 0.959 x 0.234 m, E = 1000 Pa; gravity 5 m/s^2 (the solver's setting)."
}

PCVE_EDITS = {
    "stiff_x100": {
        "case_id": "stiff_x100",
        "catalog_case_id": "edit_stiff_x100",
        "native_cli_case_id": "stiff_x100",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET cushion.young_modulus TIMES 100",
        "applies_from_frame": 1,
        "physics_override": {
            "cushion_young_modulus_pa": 100000.0
        },
        "physics_diff": {
            "cushion_young_modulus_pa": {
                "from": 1000.0,
                "to": 100000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把中间的沙发坐垫的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the middle sofa cushion's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把中间的沙发坐垫的杨氏模量增加到原来的 100 倍。",
                "en": "From frame 1 onwards, increase the middle sofa cushion's Young's modulus to 100 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 stiff_x100 案例；按 edit_dsl 和 physics_override 修改指定物理属性，由场景适配器做原生字段转换，再求解并渲染。",
            "en": "Select native case stiff_x100; apply edit_dsl and physics_override to the declared physical property through the scene adapter, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/phone_sofa_drop/scene_spec.json"
    },
    "remove_cushion": {
        "case_id": "remove_cushion",
        "catalog_case_id": "edit_remove_cushion",
        "native_cli_case_id": "remove_cushion",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE cushion",
        "applies_from_frame": 1,
        "physics_override": {
            "cushion_present": [
                0
            ]
        },
        "physics_diff": {
            "cushion_present": {
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
                "zh": "从视频一开始,把中间的沙发坐垫从场景中删除。",
                "en": "From the start of the clip, remove the middle sofa cushion from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把中间的沙发坐垫从场景中删除。",
                "en": "From frame 1 onwards, remove the middle sofa cushion from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 remove_cushion 案例；去掉中间的坐垫，保留其下方的软包木台面，再求解并渲染。",
            "en": "Select native case remove_cushion; leave out the middle cushion and keep the upholstered wooden seat deck under it, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/phone_sofa_drop/scene_spec.json"
    },
    "heavy_phone": {
        "case_id": "heavy_phone",
        "catalog_case_id": "edit_heavy_phone",
        "native_cli_case_id": "heavy_phone",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET phone.mass TIMES 10",
        "applies_from_frame": 1,
        "physics_override": {
            "phone_mass_kg": 1.87
        },
        "physics_diff": {
            "phone_mass_kg": {
                "from": 0.187,
                "to": 1.87
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把手机的质量调大一些。",
                "en": "From the start of the clip, increase the phone's mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把手机的质量增加到原来的 10 倍。",
                "en": "From frame 1 onwards, increase the phone's mass to 10 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 heavy_phone 案例；按 edit_dsl 和 physics_override 修改指定物理属性，由场景适配器做原生字段转换，再求解并渲染。",
            "en": "Select native case heavy_phone; apply edit_dsl and physics_override to the declared physical property through the scene adapter, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/phone_sofa_drop/scene_spec.json"
    },
    "soft_e_div2": {
        "case_id": "soft_e_div2",
        "catalog_case_id": "edit_soft_e_div2",
        "native_cli_case_id": "soft_e_div2",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET cushion.young_modulus TIMES 0.5",
        "applies_from_frame": 1,
        "physics_override": {
            "cushion_young_modulus_pa": 500.0
        },
        "physics_diff": {
            "cushion_young_modulus_pa": {
                "from": 1000.0,
                "to": 500.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把中间的沙发坐垫的杨氏模量调小一些。",
                "en": "From the start of the clip, decrease the middle sofa cushion's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把中间的沙发坐垫的杨氏模量减少到原来的 0.5 倍。",
                "en": "From frame 1 onwards, reduce the middle sofa cushion's Young's modulus to 0.5 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 soft_e_div2 案例；按 edit_dsl 和 physics_override 修改指定物理属性，由场景适配器做原生字段转换，再求解并渲染。",
            "en": "Select native case soft_e_div2; apply edit_dsl and physics_override to the declared physical property through the scene adapter, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/phone_sofa_drop/scene_spec.json"
    },
    "added_pillow": {
        "case_id": "added_pillow",
        "catalog_case_id": "edit_added_pillow",
        "native_cli_case_id": "added_pillow",
        "kind": "edit",
        "operation": "ADD",
        "edit_dsl": "ADD landing_pillow BETWEEN phone AND cushion_below_phone AT 1/4 FROM cushion_below_phone",
        "native_edit_dsl": "ADD landing_pillow AT PRESET middle_seat",
        "applies_from_frame": 1,
        "physics_override": {
            "pillow_present": [
                1
            ]
        },
        "physics_diff": {
            "pillow_present": {
                "from": [
                    0
                ],
                "to": [
                    1
                ]
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "placement": {
            "line": "from the phone's centre at release (0, -0.18, 0.7586) m straight down to the anchor cushion_below_phone, the point of the middle cushion's top surface on the phone's drop line ((0, -0.18, 0.4727) m: highest source cache surface vertex within 1 cm of the drop line at t = 0)",
            "pillow_centre_m": [0.0016, -0.1810, 0.5390],
            "pillow_centre_basis": "frame-1 ground truth of edit_added_pillow (centroid of the pillow's solver surface vertices)",
            "fraction_from_anchor": 0.232,
            "spoken_as": "1/4 FROM cushion_below_phone: one quarter of the way from the cushion surface directly below the phone to the phone (vague: closer to that cushion surface); the 1/4 point (0, -0.18, 0.5442) m is 5.5 mm from the pillow centre",
            "pillow_size_m": [0.379, 0.339, 0.159],
            "pillow_mass_kg": 0.3225
        },
        "prompts": {
            "vague": {
                "zh": "从视频一开始,在手机和手机正下方的坐垫面的连线上、靠近手机正下方的坐垫面的地方,放一个浅蓝灰色小枕头。",
                "en": "From the start of the clip, place a small blue-grey pillow on the line between the phone and the cushion surface directly below the phone, closer to the cushion surface directly below the phone."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,在手机和手机正下方的坐垫面连线的四等分点上放一个浅蓝灰色小枕头,取靠近手机正下方的坐垫面的那个。",
                "en": "From frame 1 onwards, place a small blue-grey pillow on the line between the phone and the cushion surface directly below the phone, one quarter of the way from the cushion surface directly below the phone to the phone."
            }
        },
        "prompt_note": "Prompts are pcve_edit_dsl.make_prompts(parse(edit_dsl, VOCAB), VOCAB) with this scene's edit_vocab.VOCAB. The endpoints of edit_dsl carry display-only GeometryAnchors in edit_vocab.py at their frame-1 positions; the division point is 0.55 cm from the added body's frame-1 centre. The solver still runs native_edit_dsl; physics and video are unchanged.",
        "how_to_edit": {
            "zh": "选择 added_pillow 案例；在手机正下方的坐垫上加入一个可变形小枕头（预设位置），手机和其他物体不动，再求解并渲染。",
            "en": "Select native case added_pillow; add the deformable pillow at its preset place on the cushion directly below the phone, leave the phone and everything else unchanged, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/phone_sofa_drop/scene_spec.json"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/phone_sofa_drop/build_pcve_phone_sofa_drop.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "verify",
        "package"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/phone_sofa_drop/build_pcve_phone_sofa_drop.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/phone_sofa_drop/build_pcve_phone_sofa_drop.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/phone_sofa_drop/build_pcve_phone_sofa_drop.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/phone_sofa_drop/build_pcve_phone_sofa_drop.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/phone_sofa_drop/simulate_phone_sofa_drop.py",
    "render_entry": "scripts/rigid_elastic/phone_sofa_drop/render_phone_sofa_drop.py",
    "current_suite": "renders/pcve_suites/pcve_phone_sofa_drop_suite",
    "notes": [
        "native_cli_case_id selects the scene case; catalog_case_id names the published edit_* directory.",
        "simulate_phone_sofa_drop.py --stage verify checks a registered 0-4 s cache; render_phone_sofa_drop.py --stage all builds and renders a case; this builder's --stage package encodes and publishes a new suite.",
        "--export-prompts writes the declared prompts into the published suite's prompts.json files."
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
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "build_pcve")
# PCVE_UNIFIED_ENTRY_END
from pathlib import Path
import argparse
import json

if __name__ == "__main__":
    from tools.scene_common import CASE_IDS, RENDER_ROOT, SUITE_DIR
    import edit_vocab

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", choices=("verify", "package"), default="verify")
    parser.add_argument("--cases", nargs="+", choices=CASE_IDS, default=list(CASE_IDS))
    parser.add_argument("--out", type=Path, help="Suite directory of the package stage (default renders/phone_sofa_drop/suite_build/pcve_phone_sofa_drop_suite)")
    parser.add_argument("--render-root", type=Path, default=RENDER_ROOT)
    parser.add_argument("--require-standard", action="store_true")
    args = parser.parse_args()
    for case in CASE_IDS:      # DSL -> override must agree with scene_spec.json and with the catalog
        resolved = edit_vocab.resolved_edit(case)
        if case != "source":
            declared = PCVE_EDITS[case]
            # ADD keeps the scene's native DSL (AT PRESET) in native_edit_dsl; edit_dsl is the
            # published BETWEEN form the prompts are worded from.
            if declared.get("native_edit_dsl", declared["edit_dsl"]) != resolved["edit_dsl"]:
                raise SystemExit(f"{case}: catalog DSL differs from scene_spec.json")
            for key, value in declared["physics_override"].items():
                native = resolved["physics_override"][key]
                if (bool(value[0]) if isinstance(value, list) else value) != native:
                    raise SystemExit(f"{case}: catalog override {key} differs from scene_spec.json")
    from tools import suite
    if args.stage == "verify":
        result = suite.verify(args.require_standard)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        raise SystemExit(0 if result["passed"] else 1)
    print(json.dumps(suite.package(args.render_root, args.out or SUITE_DIR.parents[1] / "phone_sofa_drop" / "suite_build" / SUITE_DIR.name, tuple(args.cases)), indent=2))
