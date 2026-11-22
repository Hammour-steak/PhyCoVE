"""Verify the accepted native delivery, or prepare and package the five delivered native cases."""

# PCVE_EDIT_CATALOG_BEGIN
# Source descriptions and five independent edits for the current published suite.
# Values in physics_override use the recorded shared-DSL/native-plan schema;
# scene-native adapters retain all required solver-field and presence conversions.
PCVE_SCENE = "curtain_doraemon_drape"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "窗边书桌上立着一个青花瓷花瓶,一块米白色亚麻短窗帘从窗前落下,盖到花瓶上,一部分布陷进瓶口,其余顺着瓶身垂到桌面上。",
            "en": "A blue-and-white porcelain vase stands on a desk by the window. A short off-white linen curtain drops in front of the window onto the vase; part of the fabric sinks into the mouth of the vase and the rest drapes down its sides onto the desktop."
        },
        "quantitative": {
            "zh": "窗边书桌上立着一个高 32 cm、最宽处直径 19 cm、瓶口直径 14 cm、质量 0.75 kg 的青花瓷花瓶。一块高 50 cm、用 92 cm 宽的布收成 68 cm 宽褶裥的米白色亚麻短窗帘(厚 0.25 mm、密度 360 kg/m³,即面密度 90 g/m²、总质量 41 g;杨氏模量 2 MPa;摩擦系数 0.55)开始时下沿离桌面 55 cm,以 0.16 m/s 的速度向下落,盖到花瓶上,一部分布陷进瓶口,其余顺着瓶身垂到桌面上。",
            "en": "A blue-and-white porcelain vase 32 cm tall, 19 cm across at its widest, with a 14 cm mouth and a mass of 0.75 kg, stands on a desk by the window. A short off-white linen curtain 50 cm tall, 92 cm of fabric gathered into 68 cm of pleats (0.25 mm thick with density 360 kg/m³, i.e. 90 g/m² and 41 g in total; Young's modulus 2 MPa; friction coefficient 0.55), starts with its lower edge 55 cm above the desktop and falls at 0.16 m/s onto the vase; part of the fabric sinks into the mouth and the rest drapes down its sides onto the desktop."
        }
    },
    "editable_objects": [
        {
            "object_id": "curtain",
            "zh": "米白色短窗帘",
            "en": "the short off-white curtain",
            "in_video": True,
            "properties": ["density", "friction", "young_modulus"],
            "can_delete": False,
            "can_add": False
        },
        {
            "object_id": "figurine",
            "zh": "青花瓷花瓶",
            "en": "the blue-and-white porcelain vase",
            "in_video": True,
            "properties": [],
            "can_delete": True,
            "can_add": False
        }
    ],
    "description_basis": "Physical values from physics/baseline.py PHYSICS/LAYOUT and the recorded simulation_config.json (cloth_material_width_m 0.916, cloth_mass_kg 0.0412); vase height, widest and mouth diameters from assets/scenes/curtain_doraemon_drape/porcelain_vase/preparation.json; motion as seen in the source video."
}

PCVE_EDITS = {
    "young_modulus_x10": {
        "case_id": "young_modulus_x10",
        "catalog_case_id": "edit_young_modulus_x10",
        "native_cli_case_id": "young_modulus_x10",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET curtain.young_modulus TIMES 10",
        "applies_from_frame": 1,
        "physics_override": {
            "cloth_young_modulus": 20000000.0
        },
        "physics_diff": {
            "cloth_young_modulus": {
                "from": 2000000.0,
                "to": 20000000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把米白色短窗帘的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the short off-white curtain's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把米白色短窗帘的杨氏模量增加到原来的 10 倍。",
                "en": "From frame 1 onwards, increase the short off-white curtain's Young's modulus to 10 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 young_modulus_x10 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case young_modulus_x10; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/curtain_doraemon_drape/edit_vocab.py"
    },
    "density_x0_5": {
        "case_id": "density_x0_5",
        "catalog_case_id": "edit_density_x0_5",
        "native_cli_case_id": "density_x0_5",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET curtain.density TIMES 0.5",
        "applies_from_frame": 1,
        "physics_override": {
            "cloth_density": 180.0
        },
        "physics_diff": {
            "cloth_density": {
                "from": 360.0,
                "to": 180.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把米白色短窗帘的密度调小一些。",
                "en": "From the start of the clip, decrease the short off-white curtain's density."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把米白色短窗帘的密度减少到原来的 0.5 倍。",
                "en": "From frame 1 onwards, reduce the short off-white curtain's density to 0.5 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 density_x0_5 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case density_x0_5; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/curtain_doraemon_drape/edit_vocab.py"
    },
    "delete_figurine": {
        "case_id": "delete_figurine",
        "catalog_case_id": "edit_delete_figurine",
        "native_cli_case_id": "delete_figurine",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE figurine",
        "applies_from_frame": 1,
        "physics_override": {
            "figure_active": [
                0
            ]
        },
        "physics_diff": {
            "figure_active": {
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
                "zh": "从视频一开始,把青花瓷花瓶从场景中删除。",
                "en": "From the start of the clip, remove the blue-and-white porcelain vase from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把青花瓷花瓶从场景中删除。",
                "en": "From frame 1 onwards, remove the blue-and-white porcelain vase from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 delete_figurine 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case delete_figurine; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/curtain_doraemon_drape/edit_vocab.py"
    },
    "friction_x0_1": {
        "case_id": "friction_x0_1",
        "catalog_case_id": "edit_friction_x0_1",
        "native_cli_case_id": "friction_x0_1",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET curtain.friction TIMES 0.1",
        "applies_from_frame": 1,
        "physics_override": {
            "cloth_friction": 0.055
        },
        "physics_diff": {
            "cloth_friction": {
                "from": 0.55,
                "to": 0.055
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把米白色短窗帘的摩擦系数调小一些。",
                "en": "From the start of the clip, decrease the short off-white curtain's friction coefficient."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把米白色短窗帘的摩擦系数减少到原来的 0.1 倍。",
                "en": "From frame 1 onwards, reduce the short off-white curtain's friction coefficient to 0.1 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 friction_x0_1 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case friction_x0_1; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/curtain_doraemon_drape/edit_vocab.py"
    },
    "friction_x0_1_at_frame_8": {
        "case_id": "friction_x0_1_at_frame_8",
        "catalog_case_id": "edit_friction_x0_1_at_frame_8",
        "native_cli_case_id": "friction_x0_1_at_frame_8",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET curtain.friction TIMES 0.1 AT FRAME 8",
        "applies_from_frame": 8,
        "physics_override": {
            "cloth_friction": 0.055
        },
        "physics_diff": {
            "cloth_friction": {
                "from": 0.55,
                "to": 0.055
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "在视频前段,把米白色短窗帘的摩擦系数调小一些。",
                "en": "Early in the clip, decrease the short off-white curtain's friction coefficient."
            },
            "quantitative": {
                "zh": "从第 8 帧开始,把米白色短窗帘的摩擦系数减少到原来的 0.1 倍。",
                "en": "From frame 8 onwards, reduce the short off-white curtain's friction coefficient to 0.1 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 friction_x0_1_at_frame_8 案例；第 1–7 帧就是源视频的原生状态，求解器从源缓存恢复第 8 帧（t=7/24 s）窗帘顶点的位置和速度以及所有刚体位姿，从这一帧起把窗帘的摩擦系数设为 0.055 并继续求解。",
            "en": "Select native case friction_x0_1_at_frame_8; frames 1-7 are the source native states. The solver restores the curtain vertex positions and velocities and every rigid pose of frame 8 (t=7/24 s) from the source cache, sets the curtain friction to 0.055 from that frame on and keeps solving."
        },
        "definition_source": "scripts/rigid_elastic/curtain_doraemon_drape/edit_vocab.py"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/curtain_doraemon_drape/build_pcve_curtain_doraemon_drape.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "prepare",
        "verify",
        "metadata",
        "validate",
        "package"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/curtain_doraemon_drape/build_pcve_curtain_doraemon_drape.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/curtain_doraemon_drape/build_pcve_curtain_doraemon_drape.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/curtain_doraemon_drape/build_pcve_curtain_doraemon_drape.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/curtain_doraemon_drape/build_pcve_curtain_doraemon_drape.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/curtain_doraemon_drape/simulate_curtain_doraemon_drape.py",
    "render_entry": "scripts/rigid_elastic/curtain_doraemon_drape/render_curtain_doraemon_drape.py",
    "current_suite": "renders/pcve_suites/pcve_curtain_doraemon_drape_suite",
    "notes": [
        "native_cli_case_id selects the original scenario; catalog_case_id names the published edit_* video directory.",
        "Solves need the case-isolated pyuipc 0.0.29 runtime (.runtime/curtain_doraemon_drape/uipc_029) and a claimed GPU; renders use Blender 4.3.2.",
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
from scene_paths import DELIVERY,output_path

sys.path.insert(0,str(CASE/'physics'))
from baseline import LAYOUT,sha
from vocab import CASES,VOCAB,resolve
from pcve_edit_policy import audit_suite_manifest
from pcve_media_contract import require_times,require_video


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def verify(root,selection):
    """Check a native delivery folder: DSL binding, edit policy, solver config, cache/render/video binding.

    Only the cases this code declares (vocab.CASES) are checked; a delivery may also hold cases outside the published suite."""
    manifest=read(root/'suite_manifest.json')
    manifest=dict(manifest,edits=[x for x in manifest['edits'] if x['case_id'] in CASES])
    if {x['case_id']:x['edit_dsl'] for x in manifest['edits']}!={case:dsl for case,dsl in CASES.items() if dsl}:
        raise RuntimeError('Suite DSL mismatch')
    if not audit_suite_manifest(manifest,VOCAB,root)['all_edits_compliant']:
        raise RuntimeError('Strict edit preflight failed')
    rows=[]
    for case in selection:
        folder=root/'cases'/case
        params,_=resolve(case)
        cfg=read(folder/'simulation_config.json')
        if cfg['physics']!=params or cfg['layout']!=LAYOUT:
            raise RuntimeError(f'Resolved simulation differs for {case}')
        cache=sha(folder/'cache.npz')
        video=sha(folder/'video.mp4')
        render=read(folder/'render_manifest.json')
        encoding=read(folder/'encoding_verification.json')
        if encoding['video_sha256']!=video or encoding['native_cache_sha256']!=cache or render['simulation_cache_sha256']!=cache:
            raise RuntimeError(f'Render and native evidence differ for {case}')
        require_video(folder/'video.mp4')
        require_times(read(folder/'gt.json')['times_s'])
        rows.append({'case':case,'video_sha256':video,'state_sha256':cache})
    print(json.dumps({'root':str(root),'verified_cases':rows},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('prepare','verify','metadata','validate','package'),default='verify')
    parser.add_argument('--root',type=Path,help='native delivery to verify, or the fresh output of metadata/validate/package')
    parser.add_argument('--accepted-root',type=Path,default=DELIVERY,help='accepted native delivery (default: scene_manifest data.accepted_delivery)')
    parser.add_argument('--simulation-root',type=Path,help='native solver outputs <root>/<case>/ for --stage package')
    parser.add_argument('--simulation-run',default='',help='run folder inside each solver case folder (e.g. run1)')
    parser.add_argument('--cases',nargs='+',choices=tuple(CASES),default=list(CASES))
    args=parser.parse_args()
    if args.stage=='verify':
        verify(args.root or args.accepted_root,args.cases)
    elif args.stage=='prepare':
        subprocess.run([sys.executable,'-B',str(SCRIPTS/'download_assets.py'),
                        '--scene','rigid_elastic/curtain_doraemon_drape','--check'],check=True)
    else:
        if args.root is None or set(args.cases)!=set(CASES):
            parser.error('Use a fresh --root (or --out-root) and all five native cases')
        path=output_path(args.root)
        command=[sys.executable,'-B',str(CASE/'tools/build_suite.py'),'--stage',args.stage,'--root',str(path)]
        if args.simulation_root:
            command += ['--simulation-root',str(args.simulation_root),'--simulation-run',args.simulation_run]
        subprocess.run(command,check=True)
