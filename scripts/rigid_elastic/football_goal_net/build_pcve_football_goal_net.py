"""Edit catalog of football_goal_net; verify the accepted deliveries and the published suite, check assets,
or solve the timed edit natively (physics/solve_timed.py)."""

# PCVE_EDIT_CATALOG_BEGIN
# Source descriptions and five independent edits for the current published suite.
# Values in physics_override use the recorded shared-DSL/native-plan schema;
# scene-native adapters retain all required solver-field and presence conversions.
PCVE_SCENE = "football_goal_net"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "体育场的足球场上,一个足球从球门线前飞进球门,撞进球门网的后网;球网被撞得向后鼓起又弹回,把足球弹出球门,足球落在草地上弹跳着滚回场内。",
            "en": "In a football stadium, a football flies into the goal from just in front of the goal line and hits the back of the goal net; the net bulges backwards and springs back, throwing the ball out of the goal, and the ball bounces and rolls back onto the pitch."
        },
        "quantitative": {
            "zh": "体育场的足球场上,一个直径 22 cm、质量 0.43 kg 的足球从球门线前 0.6 m、离地 1.14 m 处,以 16 m/s 的水平初速度和 1 m/s 的向上初速度飞进宽 7.32 m、高 2.44 m、深约 2.5 m 的球门,撞进球门网的后网;网线粗 4 mm,杨氏模量为 84.4 MPa。球网被撞得向后鼓起又弹回,把足球弹出球门,足球落在草地上弹跳着滚回场内。",
            "en": "In a football stadium, a football 22 cm in diameter and 0.43 kg in mass starts 0.6 m in front of the goal line and 1.14 m above the ground, with a horizontal speed of 16 m/s and an upward speed of 1 m/s, and flies into a goal 7.32 m wide, 2.44 m high and about 2.5 m deep, hitting the back of the goal net; the net cords are 4 mm thick with a Young's modulus of 84.4 MPa. The net bulges backwards and springs back, throwing the ball out of the goal, and the ball bounces and rolls back onto the pitch."
        }
    },
    "editable_objects": [
        {"object_id": "ball", "zh": "足球", "en": "the football",
         "properties": ["mass", "horizontal_velocity"], "can_delete": False},
        {"object_id": "net", "zh": "球门网", "en": "the goal net",
         "properties": ["young_modulus"], "can_delete": True}
    ],
    "description_basis": "Values from physics/strict_edit_plan.json baseline_physics (ball radius 0.11 m, mass 0.43 kg, start (0.58, -0.6, 1.14) m with the goal line at y = 0, horizontal speed 16 m/s, vertical speed 1 m/s, net strand E = 84415781.8 Pa) and the net model (posts at x = +-3.66 m, crossbar 2.44 m, rear ground rail at y = 2.55 m, 4 mm hexagonal-mesh strands); motion as seen in the source video. Edit prompts for SET/DELETE are rendered with the shared pcve_edit_dsl.render from edit_vocab.py."
}

PCVE_EDITS = {
    "remove_net": {
        "case_id": "remove_net",
        "catalog_case_id": "edit_remove_net",
        "native_cli_case_id": "remove_net",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE net",
        "applies_from_frame": 1,
        "physics_override": {"net_present": [0]},
        "physics_diff": {"net_present": {"from": [1], "to": [0]}},
        "physics_schema": "native_strict_edit_plan_SI",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把球门网从场景中删除。",
                "en": "From the start of the clip, remove the goal net from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把球门网从场景中删除。",
                "en": "From frame 1 onwards, remove the goal net from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 remove_net 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case remove_net; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/football_goal_net/edit_vocab.py"
    },
    "mass_double": {
        "case_id": "mass_double",
        "catalog_case_id": "edit_mass_double",
        "native_cli_case_id": "mass_double",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET ball.mass TIMES 2",
        "applies_from_frame": 1,
        "physics_override": {"ball_mass_kg": 0.86},
        "physics_diff": {"ball_mass_kg": {"from": 0.43, "to": 0.86}},
        "physics_schema": "native_strict_edit_plan_SI",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把足球的质量调大一些。",
                "en": "From the start of the clip, increase the football's mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把足球的质量增加到原来的 2 倍。",
                "en": "From frame 1 onwards, increase the football's mass to 2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 mass_double 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case mass_double; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/football_goal_net/edit_vocab.py"
    },
    "speed_half": {
        "case_id": "speed_half",
        "catalog_case_id": "edit_speed_half",
        "native_cli_case_id": "speed_half",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET ball.horizontal_velocity TIMES 0.5",
        "applies_from_frame": 1,
        "physics_override": {"ball_horizontal_velocity_mps": 8.0},
        "physics_diff": {"ball_horizontal_velocity_mps": {"from": 16.0, "to": 8.0}},
        "physics_schema": "native_strict_edit_plan_SI",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把足球的水平初速度调小一些。",
                "en": "From the start of the clip, decrease the football's initial horizontal speed."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把足球的水平初速度减少到原来的 0.5 倍。",
                "en": "From frame 1 onwards, reduce the football's initial horizontal speed to 0.5 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 speed_half 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case speed_half; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/football_goal_net/edit_vocab.py"
    },
    "young_tenth": {
        "case_id": "young_tenth",
        "catalog_case_id": "edit_young_tenth",
        "native_cli_case_id": "young_tenth",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET net.young_modulus TIMES 0.1",
        "applies_from_frame": 1,
        "physics_override": {"net_axial_young_modulus_Pa": 8441578.182},
        "physics_diff": {"net_axial_young_modulus_Pa": {"from": 84415781.81594129, "to": 8441578.182}},
        "physics_schema": "native_strict_edit_plan_SI",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把球门网的杨氏模量调小一些。",
                "en": "From the start of the clip, decrease the goal net's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把球门网的杨氏模量减少到原来的 0.1 倍。",
                "en": "From frame 1 onwards, reduce the goal net's Young's modulus to 0.1 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 young_tenth 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case young_tenth; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/football_goal_net/edit_vocab.py"
    },
    "mass_double_at_frame_8": {
        "case_id": "mass_double_at_frame_8",
        "catalog_case_id": "edit_mass_double_at_frame_8",
        "native_cli_case_id": "mass_double_at_frame_8",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET ball.mass TIMES 2 AT FRAME 8",
        "applies_from_frame": 8,
        "physics_override": {
            "ball_mass_kg": 0.86
        },
        "physics_diff": {
            "ball_mass_kg": {
                "from": 0.43,
                "to": 0.86
            }
        },
        "physics_schema": "native_strict_edit_plan_SI",
        "prompts": {
            "vague": {
                "zh": "在视频前段,把足球的质量调大一些。",
                "en": "Early in the clip, increase the football's mass."
            },
            "quantitative": {
                "zh": "从第 8 帧开始,把足球的质量增加到原来的 2 倍。",
                "en": "From frame 8 onwards, increase the football's mass to 2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 mass_double_at_frame_8 案例；用已验收的求解器快照先按源参数求解到第 8 帧（t=7/24 s，与源缓存之差 < 1e-8），再从这一时刻的无损检查点恢复、把足球质量设为 0.86 kg 继续求解到 4 s；合并缓存第 1–7 帧取源缓存（physics/solve_timed.py）。",
            "en": "Select native case mass_double_at_frame_8; the accepted solver snapshot solves the source parameters to frame 8 (t=7/24 s, within 1e-8 of the source cache), then restores its lossless checkpoint at that instant, sets the ball mass to 0.86 kg and keeps solving to 4 s; the merged cache keeps the source samples of frames 1-7 (physics/solve_timed.py)."
        },
        "definition_source": "scripts/rigid_elastic/football_goal_net/edit_vocab.py"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/football_goal_net/build_pcve_football_goal_net.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": ["all", "prepare", "simulate", "verify"],
    "list_edits_command": ["python3", "scripts/rigid_elastic/football_goal_net/build_pcve_football_goal_net.py", "--list-edits"],
    "show_prompts_command": ["python3", "scripts/rigid_elastic/football_goal_net/build_pcve_football_goal_net.py", "--show-prompts", "<case_id>"],
    "export_prompts_command": ["python3", "scripts/rigid_elastic/football_goal_net/build_pcve_football_goal_net.py", "--export-prompts"],
    "simulate_entry": "scripts/rigid_elastic/football_goal_net/simulate_football_goal_net.py",
    "render_entry": "scripts/rigid_elastic/football_goal_net/render_football_goal_net.py",
    "current_suite": "renders/pcve_suites/pcve_football_goal_net_suite",
    "notes": [
        "native_cli_case_id selects the native case; catalog_case_id names the published cases/<id>/ folder.",
        "--stage verify checks the accepted media delivery and the published suite; it performs no solve.",
        "--stage simulate solves the timed edit natively (physics/solve_timed.py); the whole-clip caches are registered assets."
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
sys.path.insert(0, str(CASE))

if __name__ == "__main__":
    from tools.retained import CASES, fresh, verify, verify_published
    from edit_vocab import TIMED_DSL
    ALL_CASES = list(CASES) + list(TIMED_DSL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("all", "prepare", "simulate", "verify"), default="verify")
    parser.add_argument("--cases", nargs="+", choices=ALL_CASES, default=ALL_CASES)
    parser.add_argument("--out", type=Path, help="fresh output folder of --stage simulate (one subfolder per case)")
    args = parser.parse_args()
    if args.stage == "simulate":
        if args.out is None:
            parser.error("Provide a fresh --out")
        timed = [case for case in args.cases if case in TIMED_DSL]
        if not timed:
            parser.error("--stage simulate solves timed cases only (" + ", ".join(TIMED_DSL) + ")")
        root = fresh(args.out)
        for case in timed:
            subprocess.run([sys.executable, "-B", str(CASE / "simulate_football_goal_net.py"),
                            "--mode", "solve", "--case", case, "--out", str(root / case)], check=True)
        raise SystemExit()
    result = {}
    if args.stage in {"all", "prepare"}:
        subprocess.run([sys.executable, "-B", str(CASE.parents[1] / "download_assets.py"), "--scene",
                        "rigid_elastic/football_goal_net", "--check"], check=True)
        result["prepared"] = True
    if args.stage in {"all", "verify"}:
        result.update(verify(args.cases))
        result.update(verify_published(args.cases))
    print(json.dumps(result, ensure_ascii=False, indent=1))
