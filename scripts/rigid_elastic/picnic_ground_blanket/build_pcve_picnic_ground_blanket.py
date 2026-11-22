"""Verify the published suite, or re-solve / re-render / package selected cases."""

# PCVE_EDIT_CATALOG_BEGIN
# Source description and the five edits of the current published suite: four whole-clip edits and
# one timed edit (AT FRAME 12). The edit prompts are scripts/pcve_edit_dsl.py make_prompts output for
# the vocabulary in physics/edit_vocab.py; physics_override uses the parameter names of
# physics/scene_specs.json, which the native solve reads.
PCVE_SCENE = "picnic_ground_blanket"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "草地上平铺着一块绿白格子野餐布,布上一个橘子向右滚过布面,把野餐布和下面的草地压出浅浅的凹陷,滚了一小段后停下;旁边的草地上放着保温壶、马克杯和一盘可颂与橘子。",
            "en": "A green-and-white gingham picnic blanket lies flat on a lawn. An orange on the blanket rolls to the right across it, pressing a shallow dip into the blanket and the lawn beneath, and comes to rest after a short distance; a thermos, a mug and a plate of croissants and an orange sit on the grass beside it."
        },
        "quantitative": {
            "zh": "草地上平铺着一块 84 cm × 60 cm 的绿白格子野餐布,布下的草层约 5 cm 厚。布上一个直径 6.4 cm、质量 0.11 kg 的橘子以 0.9 m/s 的初速度向右滚过布面,把野餐布和下面的草地压出浅浅的凹陷,滚了约 26 cm 后停下;旁边的草地上放着保温壶、马克杯和一盘可颂与橘子。",
            "en": "An 84 cm × 60 cm green-and-white gingham picnic blanket lies flat on a lawn whose grass layer is about 5 cm deep. An orange 6.4 cm across and weighing 0.11 kg starts rolling to the right across the blanket at 0.9 m/s, pressing a shallow dip into the blanket and the lawn beneath, and comes to rest after about 26 cm; a thermos, a mug and a plate of croissants and an orange sit on the grass beside it."
        }
    },
    "editable_objects": [
        {
            "object_id": "mandarin_orange",
            "zh": "滚动的橘子",
            "en": "the rolling orange",
            "in_video": True,
            "properties": ["friction", "initial_velocity", "mass"],
            "can_delete": True,
            "can_add": False
        },
        {
            "object_id": "cotton_blanket",
            "zh": "野餐布",
            "en": "the picnic blanket",
            "in_video": True,
            "properties": ["bending_stiffness", "young_modulus"],
            "can_delete": False,
            "can_add": False
        },
        {
            "object_id": "grass_thatch",
            "zh": "草地",
            "en": "the lawn",
            "in_video": True,
            "properties": ["young_modulus"],
            "can_delete": False,
            "can_add": False
        }
    ],
    "description_basis": "Physical parameters from physics/scene_specs.json; rolling distance and stopping point from the native source state (0.256 m, at rest from frame 31)."
}

PCVE_EDITS = {
    "delete_actor": {
        "case_id": "delete_actor",
        "catalog_case_id": "edit_delete_actor",
        "native_cli_case_id": "delete_actor",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE mandarin_orange",
        "applies_from_frame": 1,
        "physics_override": {
            "active": [0, 1]
        },
        "physics_diff": {
            "active": {"from": [1, 1], "to": [0, 1]}
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把滚动的橘子从场景中删除。",
                "en": "From the start of the clip, remove the rolling orange from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把滚动的橘子从场景中删除。",
                "en": "From frame 1 onwards, remove the rolling orange from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 delete_actor 案例;按 edit_dsl 和 physics_override 修改物体存在性,再求解并渲染。",
            "en": "Select native case delete_actor; apply edit_dsl and physics_override to the object presence, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/picnic_ground_blanket/physics/edit_vocab.py"
    },
    "stiffer": {
        "case_id": "stiffer",
        "catalog_case_id": "edit_stiffer",
        "native_cli_case_id": "stiffer",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET grass_thatch.young_modulus TIMES 10",
        "applies_from_frame": 1,
        "physics_override": {
            "solid_young_modulus": 9000.0
        },
        "physics_diff": {
            "solid_young_modulus": {"from": 900.0, "to": 9000.0}
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把草地的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the lawn's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把草地的杨氏模量增加到原来的 10 倍。",
                "en": "From frame 1 onwards, increase the lawn's Young's modulus to 10 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 stiffer 案例;按 edit_dsl 和 physics_override 修改草层的杨氏模量,再求解并渲染。",
            "en": "Select native case stiffer; apply edit_dsl and physics_override to the grass layer's Young's modulus, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/picnic_ground_blanket/physics/edit_vocab.py"
    },
    "faster": {
        "case_id": "faster",
        "catalog_case_id": "edit_faster",
        "native_cli_case_id": "faster",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET mandarin_orange.initial_velocity TIMES 2",
        "applies_from_frame": 1,
        "physics_override": {
            "body_initial_speed": 1.8
        },
        "physics_diff": {
            "body_initial_speed": {"from": 0.9, "to": 1.8}
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把滚动的橘子的初速度大小调大一些。",
                "en": "From the start of the clip, increase the rolling orange's initial speed."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把滚动的橘子的初速度大小增加到原来的 2 倍。",
                "en": "From frame 1 onwards, increase the rolling orange's initial speed to 2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 faster 案例;按 edit_dsl 和 physics_override 修改橘子的初速度大小,再求解并渲染。",
            "en": "Select native case faster; apply edit_dsl and physics_override to the orange's initial speed, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/picnic_ground_blanket/physics/edit_vocab.py"
    },
    "mass_double": {
        "case_id": "mass_double",
        "catalog_case_id": "edit_mass_double",
        "native_cli_case_id": "mass_double",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET mandarin_orange.mass TIMES 2",
        "applies_from_frame": 1,
        "physics_override": {
            "body_mass": 0.22
        },
        "physics_diff": {
            "body_mass": {"from": 0.11, "to": 0.22}
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把滚动的橘子的质量调大一些。",
                "en": "From the start of the clip, increase the rolling orange's mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把滚动的橘子的质量增加到原来的 2 倍。",
                "en": "From frame 1 onwards, increase the rolling orange's mass to 2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 mass_double 案例;按 edit_dsl 和 physics_override 修改橘子的质量,再求解并渲染。",
            "en": "Select native case mass_double; apply edit_dsl and physics_override to the orange's mass, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/picnic_ground_blanket/physics/edit_vocab.py"
    },
    "mass_double_at_frame_12": {
        "case_id": "mass_double_at_frame_12",
        "catalog_case_id": "edit_mass_double_at_frame_12",
        "native_cli_case_id": "mass_double_at_frame_12",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET mandarin_orange.mass TIMES 2 AT FRAME 12",
        "applies_from_frame": 12,
        "physics_override": {
            "body_mass": 0.22
        },
        "physics_diff": {
            "body_mass": {"from": 0.11, "to": 0.22}
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "在视频前段,把滚动的橘子的质量调大一些。",
                "en": "Early in the clip, increase the rolling orange's mass."
            },
            "quantitative": {
                "zh": "从第 12 帧开始,把滚动的橘子的质量增加到原来的 2 倍。",
                "en": "From frame 12 onwards, increase the rolling orange's mass to 2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 mass_double_at_frame_12 案例;第 1–11 帧就是 source 的原生状态,第 12 帧(t = 11/24 s)从 source 原生缓存恢复草层、野餐布和橘子的完整状态,把橘子质量改为 0.22 kg 后继续求解到 4 s(simulate --case mass_double_at_frame_12 --source-cache <source cache.npz>),再逐帧渲染全部 96 帧。",
            "en": "Select native case mass_double_at_frame_12; frames 1-11 are the source's native state. At frame 12 (t = 11/24 s) the complete source state of the lawn, the blanket and the orange is restored from the source cache, the orange's mass becomes 0.22 kg and the solve continues to 4 s (simulate --case mass_double_at_frame_12 --source-cache <source cache.npz>); all 96 frames are then rendered."
        },
        "definition_source": "scripts/rigid_elastic/picnic_ground_blanket/physics/edit_vocab.py"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/picnic_ground_blanket/build_pcve_picnic_ground_blanket.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": ["verify", "simulate", "render", "finalize", "replay", "all"],
    "native_help_command": ["python3", "scripts/rigid_elastic/picnic_ground_blanket/build_pcve_picnic_ground_blanket.py", "--native-help"],
    "list_edits_command": ["python3", "scripts/rigid_elastic/picnic_ground_blanket/build_pcve_picnic_ground_blanket.py", "--list-edits"],
    "show_prompts_command": ["python3", "scripts/rigid_elastic/picnic_ground_blanket/build_pcve_picnic_ground_blanket.py", "--show-prompts", "<case_id>"],
    "export_prompts_command": ["python3", "scripts/rigid_elastic/picnic_ground_blanket/build_pcve_picnic_ground_blanket.py", "--export-prompts"],
    "simulate_entry": "scripts/rigid_elastic/picnic_ground_blanket/simulate_picnic_ground_blanket.py",
    "render_entry": "scripts/rigid_elastic/picnic_ground_blanket/render_picnic_ground_blanket.py",
    "current_suite": "renders/pcve_suites/pcve_picnic_ground_blanket_suite",
    "notes": [
        "native_cli_case_id selects the native case; catalog_case_id names the published edit_* folder.",
        "--stage verify checks the published suite, its prompts and GT against the native inputs in assets/scenes/picnic_ground_blanket/native/ and the solver records of the timed edit.",
        "--stage replay re-renders the accepted native states of the whole-clip cases; --stage all solves anew (Linux, CUDA GPU through tools/worker_run.py), then renders and packages.",
        "The timed edit has no accepted state in the asset store: --stage all/simulate solves it from the source state of frame 12, and render/finalize replay that solve."
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
import subprocess
from scene_inputs import CASES, SCENE, TIMED_CASES
from scene_paths import OUTPUT, analysis_python, output_path, require_linux

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage",choices=("all","verify","validate","simulate","render","finalize","replay"),default="verify",
                        help="verify (default) checks the published suite; replay re-renders and packages the accepted native states")
    parser.add_argument("--cases",nargs="+",choices=CASES+TIMED_CASES,
                        help="native case IDs (default: all six; the five whole-clip cases for replay or --reuse-native)")
    parser.add_argument("--out",type=Path,default=OUTPUT)
    parser.add_argument("--gpu-uuid",default="auto",help="GPU index or UUID for render (CUDA_VISIBLE_DEVICES); 'auto' inherits it")
    parser.add_argument("--blender-bin",type=Path)
    parser.add_argument("--cpu-threads",type=int,default=6)
    parser.add_argument("--reuse-native",action="store_true",
                        help="Render or finalize the accepted native state of each case instead of a new solve")
    args=parser.parse_args()
    if args.stage in {"verify","validate"}:
        raise SystemExit(subprocess.run([str(analysis_python()),"-B",str(CASE/"tools/verify.py"),*(args.cases or [])]).returncode)
    if args.reuse_native and args.stage not in {"render","finalize","replay"}:
        parser.error("--reuse-native applies to render, finalize or replay")
    reuse=args.reuse_native or args.stage=="replay"
    cases=args.cases or (list(CASES) if reuse else list(CASES+TIMED_CASES))
    if reuse and set(cases)&set(TIMED_CASES):
        parser.error("The timed edit has no accepted native state to replay; solve it with --stage all or simulate")
    if args.stage in {"all","simulate"}:require_linux()
    out=output_path(args.out)
    for case in cases:
        simulation=out/case/"simulation"
        render=out/case/"render"
        sim=[sys.executable,"-B",CASE/f"simulate_{SCENE}.py","--case-id",case,"--out",simulation,
             "--gpu-uuid",args.gpu_uuid,"--cpu-threads",args.cpu_threads]
        movie=[sys.executable,"-B",CASE/f"render_{SCENE}.py","--case-id",case,"--out",render,
               "--gpu-uuid",args.gpu_uuid,"--cpu-threads",args.cpu_threads]
        if args.blender_bin is not None:movie+=["--blender-bin",args.blender_bin]
        final=[analysis_python(),"-B",CASE/"tools/finalize.py","--render",render,"--case",case]
        if not reuse:
            movie+=["--simulation",simulation]
            final+=["--simulation",simulation]
        stages={"all":[sim,movie,final],"simulate":[sim],"render":[movie],
                "finalize":[final],"replay":[movie,final]}[args.stage]
        for cmd in stages:subprocess.run(list(map(str,cmd)),check=True)
