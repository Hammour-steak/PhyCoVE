"""Verify the accepted native delivery, or regenerate, render and finalize gym_landing_mat cases."""

# PCVE_EDIT_CATALOG_BEGIN
# Source descriptions and five independent edits for the current published suite.
# Values in physics_override use the recorded shared-DSL/native-plan schema;
# scene-native adapters retain all required solver-field and presence conversions.
PCVE_SCENE = "gym_landing_mat"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "体育馆的木地板上放着一块蓝色落地垫,一个实心球斜着向右下方落到垫面上,垫面被压陷后回弹,实心球最后停在垫子上。",
            "en": "On the wooden floor of a gym, a medicine ball drops at a slant, down and to the right, onto a blue landing mat; the mat surface is pressed in and springs back, and the ball comes to rest on the mat."
        },
        "quantitative": {
            "zh": "体育馆木地板上放着一块 1.2 m × 0.8 m、厚 14 cm 的蓝色落地垫,泡棉芯上层的杨氏模量为 10 kPa。直径 22.5 cm、质量 4.54 kg 的实心球开始时球心离地 51.5 cm,以 0.8 m/s 的速度向右下方运动(偏离竖直方向约 33°),落到垫面上,垫面被压陷后回弹,实心球最后停在垫子上。",
            "en": "A blue landing mat, 1.2 m × 0.8 m and 14 cm thick, lies on the wooden floor of a gym; the upper layer of its foam core has a Young's modulus of 10 kPa. A medicine ball 22.5 cm in diameter and 4.54 kg starts with its center 51.5 cm above the floor, moving down and to the right at 0.8 m/s (about 33° from vertical), lands on the mat and presses the surface in; the surface springs back and the ball comes to rest on the mat."
        }
    },
    "editable_objects": [
        {
            "object_id": "medicine_ball",
            "zh": "实心球",
            "en": "the medicine ball",
            "in_video": True,
            "properties": ["friction", "initial_velocity", "mass"],
            "can_delete": True,
            "can_add": False
        },
        {
            "object_id": "landing_mat",
            "zh": "落地垫",
            "en": "the landing mat",
            "in_video": True,
            "properties": ["bending_stiffness", "young_modulus"],
            "can_delete": False,
            "can_add": False
        },
        {
            "object_id": "gym_water_bottle",
            "zh": "运动水壶",
            "en": "a sports water bottle",
            "in_video": False,
            "properties": [],
            "can_delete": False,
            "can_add": True
        }
    ],
    "description_basis": "Physical values from physics/scene_specs.json (body_radius, body_mass, body_initial_location, body_initial_speed, body_direction, solid_dimensions, solid_young_modulus); motion as seen in the source video."
}

PCVE_EDITS = {
    "add_path_obstacle": {
        "case_id": "add_path_obstacle",
        "catalog_case_id": "edit_add_path_obstacle",
        "native_cli_case_id": "add_path_obstacle",
        "kind": "edit",
        "operation": "ADD",
        "edit_dsl": "ADD gym_water_bottle BETWEEN medicine_ball AND ball_heading_point AT 1/10 FROM ball_heading_point",
        "native_edit_dsl": "ADD gym_water_bottle AT PRESET roll_path",
        "applies_from_frame": 1,
        "physics_override": {
            "gym_water_bottle_active": [
                1
            ]
        },
        "physics_diff": {
            "gym_water_bottle_active": {
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
                "zh": "从视频一开始,在实心球和实心球运动方向与垫面的交点的连线上、靠近实心球运动方向与垫面的交点的地方,放一个横放的运动水壶。",
                "en": "From the start of the clip, place a sports water bottle lying on its side on the line between the medicine ball and the point where the medicine ball's line of motion meets the mat, closer to the point where the medicine ball's line of motion meets the mat."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,在实心球和实心球运动方向与垫面的交点连线的十等分点上放一个横放的运动水壶,取靠近实心球运动方向与垫面的交点的那个。",
                "en": "From frame 1 onwards, place a sports water bottle lying on its side on the line between the medicine ball and the point where the medicine ball's line of motion meets the mat, one tenth of the way from the point where the medicine ball's line of motion meets the mat to the medicine ball."
            }
        },
        "prompt_note": "Prompts are pcve_edit_dsl.make_prompts(parse(edit_dsl, VOCAB), VOCAB) with this scene's edit_vocab.VOCAB. The endpoints of edit_dsl carry display-only GeometryAnchors in edit_vocab.py at their frame-1 positions; the division point is 0.23 cm from the added body's frame-1 centre. The solver still runs native_edit_dsl; physics and video are unchanged.",
        "how_to_edit": {
            "zh": "选择 add_path_obstacle 案例；按 native_edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case add_path_obstacle; apply native_edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/gym_landing_mat/edit_vocab.py"
    },
    "delete_actor": {
        "case_id": "delete_actor",
        "catalog_case_id": "edit_delete_actor",
        "native_cli_case_id": "delete_actor",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE medicine_ball",
        "applies_from_frame": 1,
        "physics_override": {
            "active": [
                0,
                1
            ]
        },
        "physics_diff": {
            "active": {
                "from": [
                    1,
                    1
                ],
                "to": [
                    0,
                    1
                ]
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把实心球从场景中删除。",
                "en": "From the start of the clip, remove the medicine ball from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把实心球从场景中删除。",
                "en": "From frame 1 onwards, remove the medicine ball from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 delete_actor 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case delete_actor; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/gym_landing_mat/edit_vocab.py"
    },
    "faster": {
        "case_id": "faster",
        "catalog_case_id": "edit_faster",
        "native_cli_case_id": "faster",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET medicine_ball.initial_velocity TIMES 3",
        "applies_from_frame": 1,
        "physics_override": {
            "body_initial_speed": 2.4
        },
        "physics_diff": {
            "body_initial_speed": {
                "from": 0.8,
                "to": 2.4
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把实心球的初速度大小调大一些。",
                "en": "From the start of the clip, increase the medicine ball's initial speed."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把实心球的初速度大小增加到原来的 3 倍。",
                "en": "From frame 1 onwards, increase the medicine ball's initial speed to 3 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 faster 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case faster; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/gym_landing_mat/edit_vocab.py"
    },
    "mass_double": {
        "case_id": "mass_double",
        "catalog_case_id": "edit_mass_double",
        "native_cli_case_id": "mass_double",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET medicine_ball.mass TIMES 2",
        "applies_from_frame": 1,
        "physics_override": {
            "body_mass": 9.0718474
        },
        "physics_diff": {
            "body_mass": {
                "from": 4.5359237,
                "to": 9.0718474
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把实心球的质量调大一些。",
                "en": "From the start of the clip, increase the medicine ball's mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把实心球的质量增加到原来的 2 倍。",
                "en": "From frame 1 onwards, increase the medicine ball's mass to 2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 mass_double 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case mass_double; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/gym_landing_mat/edit_vocab.py"
    },
    "young_modulus_rebound": {
        "case_id": "young_modulus_rebound",
        "catalog_case_id": "edit_young_modulus_rebound",
        "native_cli_case_id": "young_modulus_rebound",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET landing_mat.young_modulus TIMES 10",
        "applies_from_frame": 1,
        "physics_override": {
            "solid_young_modulus": 100000.0
        },
        "physics_diff": {
            "solid_young_modulus": {
                "from": 10000.0,
                "to": 100000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把落地垫的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the landing mat's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把落地垫的杨氏模量增加到原来的 10 倍。",
                "en": "From frame 1 onwards, increase the landing mat's Young's modulus to 10 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 young_modulus_rebound 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case young_modulus_rebound; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/gym_landing_mat/edit_vocab.py"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/gym_landing_mat/build_pcve_gym_landing_mat.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "all",
        "verify",
        "validate",
        "simulate",
        "render",
        "finalize",
        "replay"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/gym_landing_mat/build_pcve_gym_landing_mat.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/gym_landing_mat/build_pcve_gym_landing_mat.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/gym_landing_mat/build_pcve_gym_landing_mat.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/gym_landing_mat/build_pcve_gym_landing_mat.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/gym_landing_mat/simulate_gym_landing_mat.py",
    "render_entry": "scripts/rigid_elastic/gym_landing_mat/render_gym_landing_mat.py",
    "current_suite": "renders/pcve_suites/pcve_gym_landing_mat_suite",
    "notes": [
        "native_cli_case_id selects the original scenario; catalog_case_id names the published edit_* video directory.",
        "The simulator and runtime are the accepted ones; the render entry applies the current look (appearance/realism.py) unless --look accepted is given.",
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

# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "build_pcve")
# PCVE_UNIFIED_ENTRY_END
from pathlib import Path
import sys

CASE = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE.parents[1]))

import argparse
import contextlib
import json
import subprocess
from scene_inputs import CASES, SCENE
from scene_paths import OUTPUT, output_path, worker_only
from tools.retained_delivery import verify

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage",choices=("all","verify","validate","simulate","render","finalize","replay"),default="verify")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=CASES)
    parser.add_argument("--out",type=Path,default=OUTPUT)
    parser.add_argument("--gpu-uuid",default="auto")
    parser.add_argument("--blender-bin",type=Path)
    parser.add_argument("--cpu-threads",type=int,default=6)
    parser.add_argument("--reuse-native",action="store_true",
                        help="Render or finalize an explicitly retained native cache")
    parser.add_argument("--look",choices=("realism","accepted"),default="realism",
                        help="realism: current appearance (appearance/realism.py); accepted: frozen renderer of the accepted delivery")
    parser.add_argument("--samples",type=int)
    args=parser.parse_args()
    if args.stage in {"verify","validate"}:
        with contextlib.redirect_stdout(sys.stderr):
            verified=verify(args.cases)
        print(json.dumps({"scene":SCENE,"verified_cases":verified}))
        raise SystemExit()
    if args.reuse_native and args.stage not in {"render","replay"}:
        parser.error("--reuse-native applies to render or replay")
    if args.stage in {"all","simulate","render","replay"}:worker_only()
    out=output_path(args.out)
    reuse=args.reuse_native or args.stage=="replay"
    for case in args.cases:
        simulation=out/case/"simulation"
        render=out/case/"render"
        sim=[CASE/f"simulate_{SCENE}.py","--case-id",case,"--out",simulation,
             "--gpu-uuid",args.gpu_uuid,"--cpu-threads",args.cpu_threads]
        movie=[CASE/f"render_{SCENE}.py","--case-id",case,"--out",render,
               "--gpu-uuid",args.gpu_uuid,"--cpu-threads",args.cpu_threads,"--look",args.look]
        if args.blender_bin is not None:movie+=["--blender-bin",args.blender_bin]
        if args.samples is not None:movie+=["--samples",args.samples]
        final=[CASE/"tools/finalize.py","--render",render]
        if not reuse:movie+=["--simulation",simulation]
        stages={"all":[sim,movie,final],"simulate":[sim],"render":[movie],
                "finalize":[final],"replay":[movie,final]}[args.stage]
        for cmd in stages:subprocess.run([sys.executable,"-B",*map(str,cmd)],check=True)
