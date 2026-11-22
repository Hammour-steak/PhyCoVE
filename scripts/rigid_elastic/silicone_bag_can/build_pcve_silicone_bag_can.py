"""Verify the accepted delivery and published suite, or rerun the accepted pipeline (native solve, accepted-look render, audit)."""

# PCVE_EDIT_CATALOG_BEGIN
# Source description and five independent edits of the published suite.
# physics_override uses the shared-DSL scenario fields of physics/vocab.py;
# the native solver keeps its own field conversions and object setup.
PCVE_SCENE = "silicone_bag_can"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "厨房里,一只硅胶袋的两根提手挂在台面边缘的两个钢挂钩上。一个金属罐头从袋口上方落下,掉进硅胶袋里,硅胶袋被罐头坠得向下变形,随后来回晃动。",
            "en": "In a kitchen, a silicone bag hangs by its two handles from two steel hooks at the edge of the counter. A metal can drops from above the bag's mouth into the silicone bag; the bag is pulled down out of shape by the can and then sways."
        },
        "quantitative": {
            "zh": "厨房里,一只宽 24 cm、深 15 cm、高 22 cm、约 273 g 的硅胶袋,两根提手挂在台面边缘的两个钢挂钩上;袋壁厚 1.4 mm,提手厚 2.4 mm,杨氏模量为 1.05 MPa。一个 340 g 的金属罐头(直径 6.8 cm、高 8 cm)从静止开始下落,起始时罐底比袋口高 18 cm,掉进硅胶袋里,硅胶袋被罐头坠得向下变形,随后来回晃动。",
            "en": "In a kitchen, a silicone bag 24 cm wide, 15 cm deep, 22 cm tall and about 273 g hangs by its two handles from two steel hooks at the edge of the counter; its wall is 1.4 mm thick, its handles 2.4 mm, and its Young's modulus is 1.05 MPa. A 340 g metal can (6.8 cm across, 8 cm tall) is released from rest with its bottom 18 cm above the bag's mouth and drops into the silicone bag; the bag is pulled down out of shape by the can and then sways."
        }
    },
    "editable_objects": [
        {
            "object_id": "can",
            "zh": "金属罐头",
            "en": "the metal can",
            "in_video": True,
            "properties": ["mass"],
            "can_delete": False,
            "can_add": False
        },
        {
            "object_id": "bag",
            "zh": "硅胶袋",
            "en": "the silicone bag",
            "in_video": True,
            "properties": ["young_modulus"],
            "can_delete": True,
            "can_add": False
        },
        {
            "object_id": "second_can",
            "zh": "同款金属罐头",
            "en": "a second metal can",
            "in_video": False,
            "properties": [],
            "can_delete": False,
            "can_add": True
        }
    ],
    "description_basis": "Physical values from the accepted native configuration (assets scenes/silicone_bag_can/native/source/simulation_config.json: physics can_mass_kg, can_radius_m, can_height_m, can_initial_location_m, bag_width_m, bag_depth_m, bag_bottom_z_m, bag_mouth_z_m, bag_thickness_m, bag_handle_thickness_m, bag_young_modulus_pa; bag_mass_kg) and the initial native state (can at rest); motion as seen in the source video."
}

PCVE_EDITS = {
    "add_second_can": {
        "case_id": "add_second_can",
        "catalog_case_id": "edit_add_second_can",
        "native_cli_case_id": "add_second_can",
        "kind": "edit",
        "operation": "ADD",
        "edit_dsl": "ADD second_can BETWEEN can AND bag_bottom AT 9/10 FROM can",
        "native_edit_dsl": "ADD second_can AT PRESET preloaded_inside_bag",
        "applies_from_frame": 1,
        "physics_override": {
            "second_can_present": [
                1
            ]
        },
        "physics_diff": {
            "second_can_present": {
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
                "zh": "从视频一开始,在金属罐头和硅胶袋袋底的连线上、靠近硅胶袋袋底的地方,放一个同款金属罐头。",
                "en": "From the start of the clip, place a second metal can on the line between the metal can and the bottom of the silicone bag, closer to the bottom of the silicone bag."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,在金属罐头和硅胶袋袋底连线的十等分点上放一个同款金属罐头,取靠近硅胶袋袋底的那个。",
                "en": "From frame 1 onwards, place a second metal can on the line between the metal can and the bottom of the silicone bag, one tenth of the way from the bottom of the silicone bag to the metal can."
            }
        },
        "prompt_note": "Prompts are pcve_edit_dsl.make_prompts(parse(edit_dsl, VOCAB), VOCAB) with this scene's edit_vocab.VOCAB. The endpoints of edit_dsl carry display-only GeometryAnchors in edit_vocab.py at their frame-1 positions; the division point is 0.92 cm from the added body's frame-1 centre. The solver still runs native_edit_dsl; physics and video are unchanged.",
        "how_to_edit": {
            "zh": "选择 add_second_can 案例;按 native_edit_dsl 和 physics_override 在袋内加入第二个罐头,先求解袋与该罐头在重力下的静止状态(准备状态 prepared_preloaded.npz),再从这个状态求解并渲染;下落罐头的初始位置不变。edit_dsl 是仓库定位 DSL 形式的语句(端点 bag_bottom 是 edit_vocab.py 里只用于定位的锚点),prompt 按它写成。",
            "en": "Select native case add_second_can; apply native_edit_dsl and physics_override to add the second can inside the bag, solve the bag and that can to rest under gravity first (prepared state prepared_preloaded.npz), then solve from that state and render; the falling can starts where it does in the source. edit_dsl is the placement statement in the repository's placement DSL form that the prompts are written from (its endpoint bag_bottom is a locating-only anchor in edit_vocab.py)."
        },
        "definition_source": "scripts/rigid_elastic/silicone_bag_can/physics/vocab.py"
    },
    "bag_young_x0_25": {
        "case_id": "bag_young_x0_25",
        "catalog_case_id": "edit_bag_young_x0_25",
        "native_cli_case_id": "bag_young_x0_25",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET bag.young_modulus TIMES 0.25",
        "applies_from_frame": 1,
        "physics_override": {
            "bag_young_modulus_pa": 262500.0
        },
        "physics_diff": {
            "bag_young_modulus_pa": {
                "from": 1050000,
                "to": 262500.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把硅胶袋的杨氏模量调小一些。",
                "en": "From the start of the clip, decrease the silicone bag's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把硅胶袋的杨氏模量减少到原来的 0.25 倍。",
                "en": "From frame 1 onwards, reduce the silicone bag's Young's modulus to 0.25 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 bag_young_x0_25 案例;按 edit_dsl 和 physics_override 改动袋体的杨氏模量(膜能与弯曲能同时按它计算),从共同的准备状态重新求解并渲染。",
            "en": "Select native case bag_young_x0_25; apply edit_dsl and physics_override to the bag's Young's modulus (membrane and bending energy both follow it), solve from the shared prepared state and render."
        },
        "definition_source": "scripts/rigid_elastic/silicone_bag_can/physics/vocab.py"
    },
    "bag_young_x5": {
        "case_id": "bag_young_x5",
        "catalog_case_id": "edit_bag_young_x5",
        "native_cli_case_id": "bag_young_x5",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET bag.young_modulus TIMES 5",
        "applies_from_frame": 1,
        "physics_override": {
            "bag_young_modulus_pa": 5250000.0
        },
        "physics_diff": {
            "bag_young_modulus_pa": {
                "from": 1050000,
                "to": 5250000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把硅胶袋的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the silicone bag's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把硅胶袋的杨氏模量增加到原来的 5 倍。",
                "en": "From frame 1 onwards, increase the silicone bag's Young's modulus to 5 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 bag_young_x5 案例;按 edit_dsl 和 physics_override 改动袋体的杨氏模量(膜能与弯曲能同时按它计算),从共同的准备状态重新求解并渲染。",
            "en": "Select native case bag_young_x5; apply edit_dsl and physics_override to the bag's Young's modulus (membrane and bending energy both follow it), solve from the shared prepared state and render."
        },
        "definition_source": "scripts/rigid_elastic/silicone_bag_can/physics/vocab.py"
    },
    "can_mass_x2": {
        "case_id": "can_mass_x2",
        "catalog_case_id": "edit_can_mass_x2",
        "native_cli_case_id": "can_mass_x2",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET can.mass TIMES 2",
        "applies_from_frame": 1,
        "physics_override": {
            "can_mass_kg": 0.68
        },
        "physics_diff": {
            "can_mass_kg": {
                "from": 0.34,
                "to": 0.68
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把金属罐头的质量调大一些。",
                "en": "From the start of the clip, increase the metal can's mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把金属罐头的质量增加到原来的 2 倍。",
                "en": "From frame 1 onwards, increase the metal can's mass to 2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 can_mass_x2 案例;按 edit_dsl 和 physics_override 改动下落罐头的质量,从共同的准备状态重新求解并渲染。",
            "en": "Select native case can_mass_x2; apply edit_dsl and physics_override to the falling can's mass, solve from the shared prepared state and render."
        },
        "definition_source": "scripts/rigid_elastic/silicone_bag_can/physics/vocab.py"
    },
    "delete_bag": {
        "case_id": "delete_bag",
        "catalog_case_id": "edit_delete_bag",
        "native_cli_case_id": "delete_bag",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE bag",
        "applies_from_frame": 1,
        "physics_override": {
            "bag_present": [
                0
            ]
        },
        "physics_diff": {
            "bag_present": {
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
                "zh": "从视频一开始,把硅胶袋从场景中删除。",
                "en": "From the start of the clip, remove the silicone bag from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把硅胶袋从场景中删除。",
                "en": "From frame 1 onwards, remove the silicone bag from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 delete_bag 案例;按 edit_dsl 和 physics_override 去掉袋体,罐头从同一位置落下,与地板按恢复系数 0.30 接触,求解并渲染;两个挂钩留在原处。",
            "en": "Select native case delete_bag; apply edit_dsl and physics_override to remove the bag body; the can drops from the same place onto the floor (restitution 0.30), then solve and render; the two hooks stay in place."
        },
        "definition_source": "scripts/rigid_elastic/silicone_bag_can/physics/vocab.py"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/silicone_bag_can/build_pcve_silicone_bag_can.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "verify",
        "simulate",
        "render",
        "audit",
        "all"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/silicone_bag_can/build_pcve_silicone_bag_can.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/silicone_bag_can/build_pcve_silicone_bag_can.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/silicone_bag_can/build_pcve_silicone_bag_can.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/silicone_bag_can/build_pcve_silicone_bag_can.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/silicone_bag_can/simulate_silicone_bag_can.py",
    "render_entry": "scripts/rigid_elastic/silicone_bag_can/render_silicone_bag_can.py",
    "current_suite": "renders/pcve_suites/pcve_silicone_bag_can_suite",
    "notes": [
        "native_cli_case_id selects the native case; catalog_case_id names the published edit_* video directory.",
        "Native solves run through tools/worker_run.py with the staged libuipc runtime; the current look renders on a directly claimed GPU or the CPU.",
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
import subprocess
from scene_paths import CASES, OUTPUT, output_path, worker_only

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", choices=("verify", "simulate", "render", "audit", "all"), default="verify")
    p.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    p.add_argument("--out", type=Path, help="rebuild root (default renders/silicone_bag_can/rebuild)")
    p.add_argument("--gpu-uuid", default="auto")
    p.add_argument("--cpu-threads", type=int, default=4)
    p.add_argument("--blender-bin", type=Path)
    a = p.parse_args()
    if a.stage == "verify":
        from tools.retained_delivery import verify, verify_suite
        print(json.dumps({"accepted_delivery": verify(a.cases),
                          "published_suite": verify_suite(a.cases)}, indent=1))
        raise SystemExit()
    # Accepted pipeline: native solve, accepted-look render and audit.
    out = output_path(a.out or OUTPUT)
    if a.stage in {"all", "simulate", "render"}:
        worker_only()
    if a.stage in {"all", "audit"} and set(a.cases) != set(CASES):
        p.error("This stage requires the complete six-case suite")

    def run(*args):
        subprocess.run([sys.executable, "-B", *map(str, args)], check=True)

    common = ["--gpu-uuid", a.gpu_uuid, "--cpu-threads", a.cpu_threads]
    if a.stage in {"all", "simulate", "render"}:
        for case in a.cases:
            dest = out / "native" / case
            if a.stage in {"all", "simulate"}:
                run(CASE / "simulate_silicone_bag_can.py", "--case", case, "--out", dest, *common)
            if a.stage in {"all", "render"}:
                extra = ["--blender-bin", a.blender_bin] if a.blender_bin else []
                run(CASE / "render_silicone_bag_can.py", "--case", case, "--look", "accepted", "--source", dest,
                    "--out", dest, *common, *extra)
    if a.stage in {"all", "audit"}:
        run(CASE / "tools/audit_native.py", "--root", out / "native")
