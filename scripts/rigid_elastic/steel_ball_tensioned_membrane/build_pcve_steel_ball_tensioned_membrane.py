"""Rebuild or verify the native four-second membrane suite."""

# PCVE_EDIT_CATALOG_BEGIN
# Source descriptions and five independent edits for the current published suite.
# Values in physics_override use the recorded shared-DSL/native-plan schema;
# scene-native adapters retain all required solver-field and presence conversions.
PCVE_SCENE = "steel_ball_tensioned_membrane"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "实验室内，钢球自由下落到圆形夹具中张紧的橡胶膜上，膜面随撞击发生形变。",
            "en": "In a laboratory, a steel ball falls onto a rubber membrane tensioned in a circular fixture, deforming the membrane through impact."
        },
        "quantitative": {
            "zh": "实验室内,一个直径 8 cm、质量 2.09 kg 的钢球从球心高出膜面 38 cm 处自由下落,落到圆形夹具中张紧的橡胶膜上(膜的有效直径 76 cm、厚 0.8 mm、杨氏模量 1.2 MPa、预张力 65 N/m),膜面随撞击发生形变。",
            "en": "In a laboratory, a steel ball 8 cm in diameter and 2.09 kg in mass falls freely from 38 cm above a rubber membrane (centre to membrane) tensioned in a circular fixture (76 cm clear diameter, 0.8 mm thick, Young's modulus 1.2 MPa, pretension 65 N/m), deforming the membrane through impact."
        }
    },
    "description_basis": "Current scene code and retained source-video inspection; physical outcomes beyond the visible interaction are not asserted."
}

PCVE_EDITS = {
    "remove_membrane": {
        "case_id": "remove_membrane",
        "catalog_case_id": "edit_remove_membrane",
        "native_cli_case_id": "remove_membrane",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE membrane",
        "applies_from_frame": 1,
        "physics_override": {
            "membrane_present": [
                0
            ]
        },
        "physics_diff": {
            "membrane_present": {
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
                "zh": "从视频一开始,把张紧橡胶膜从场景中删除。",
                "en": "From the start of the clip, remove the tensioned rubber membrane from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把张紧橡胶膜从场景中删除。",
                "en": "From frame 1 onwards, remove the tensioned rubber membrane from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 remove_membrane 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case remove_membrane; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/steel_ball_tensioned_membrane/edit_vocab.py"
    },
    "membrane_stiff": {
        "case_id": "membrane_stiff",
        "catalog_case_id": "edit_membrane_stiff",
        "native_cli_case_id": "membrane_stiff",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET membrane.young_modulus TIMES 3",
        "applies_from_frame": 1,
        "physics_override": {
            "membrane_young_modulus_pa": 3600000.0
        },
        "physics_diff": {
            "membrane_young_modulus_pa": {
                "from": 1200000.0,
                "to": 3600000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把张紧橡胶膜的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the tensioned rubber membrane's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把张紧橡胶膜的杨氏模量增加到原来的 3 倍。",
                "en": "From frame 1 onwards, increase the tensioned rubber membrane's Young's modulus to 3 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 membrane_stiff 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case membrane_stiff; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/steel_ball_tensioned_membrane/edit_vocab.py"
    },
    "ball_mass_heavy": {
        "case_id": "ball_mass_heavy",
        "catalog_case_id": "edit_ball_mass_heavy",
        "native_cli_case_id": "ball_mass_heavy",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET ball.mass TIMES 2",
        "applies_from_frame": 1,
        "physics_override": {
            "ball_mass_kg": 4.182088
        },
        "physics_diff": {
            "ball_mass_kg": {
                "from": 2.091044,
                "to": 4.182088
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把钢球的质量调大一些。",
                "en": "From the start of the clip, increase the steel ball's mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把钢球的质量增加到原来的 2 倍。",
                "en": "From frame 1 onwards, increase the steel ball's mass to 2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 ball_mass_heavy 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case ball_mass_heavy; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/steel_ball_tensioned_membrane/edit_vocab.py"
    },
    "membrane_soft": {
        "case_id": "membrane_soft",
        "catalog_case_id": "edit_membrane_soft",
        "native_cli_case_id": "membrane_soft",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET membrane.young_modulus TIMES 0.5",
        "applies_from_frame": 1,
        "physics_override": {
            "membrane_young_modulus_pa": 600000.0
        },
        "physics_diff": {
            "membrane_young_modulus_pa": {
                "from": 1200000.0,
                "to": 600000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把张紧橡胶膜的杨氏模量调小一些。",
                "en": "From the start of the clip, decrease the tensioned rubber membrane's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把张紧橡胶膜的杨氏模量减少到原来的 0.5 倍。",
                "en": "From frame 1 onwards, reduce the tensioned rubber membrane's Young's modulus to 0.5 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 membrane_soft 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case membrane_soft; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/steel_ball_tensioned_membrane/edit_vocab.py"
    },
    "add_second_ball": {
        "case_id": "add_second_ball",
        "catalog_case_id": "edit_add_second_ball",
        "native_cli_case_id": "add_second_ball",
        "kind": "edit",
        "operation": "ADD",
        "edit_dsl": "ADD second_ball BETWEEN ball AND membrane_impact_point AT 1/9 FROM membrane_impact_point",
        "native_edit_dsl": "ADD second_ball AT PRESET impact_path_on_membrane",
        "applies_from_frame": 1,
        "physics_override": {
            "second_ball_present": [
                1
            ]
        },
        "physics_diff": {
            "second_ball_present": {
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
                "zh": "从视频一开始,在钢球和张紧膜的中心的连线上、靠近张紧膜的中心的地方,放一个同规格钢球。",
                "en": "From the start of the clip, place an identical steel ball on the line between the steel ball and the centre of the tensioned membrane, closer to the centre of the tensioned membrane."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,在钢球和张紧膜的中心连线的九等分点上放一个同规格钢球,取靠近张紧膜的中心的那个。",
                "en": "From frame 1 onwards, place an identical steel ball on the line between the steel ball and the centre of the tensioned membrane, one ninth of the way from the centre of the tensioned membrane to the steel ball."
            }
        },
        "prompt_note": "Prompts are pcve_edit_dsl.make_prompts(parse(edit_dsl, VOCAB), VOCAB) with this scene's edit_vocab.VOCAB. The endpoints of edit_dsl carry display-only GeometryAnchors in edit_vocab.py at their frame-1 positions; the division point is 0.12 cm from the added body's frame-1 centre. The solver still runs native_edit_dsl; physics and video are unchanged.",
        "how_to_edit": {
            "zh": "选择 add_second_ball 案例；按 native_edit_dsl 的预设位置加入第二个同规格钢球，其余物体从原场景第 1 帧的状态重新求解并渲染。",
            "en": "Select native case add_second_ball; add the second identical steel ball at the preset position of native_edit_dsl, solve everything else from frame 1 of the source and render."
        },
        "definition_source": "scripts/rigid_elastic/steel_ball_tensioned_membrane/edit_vocab.py"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/steel_ball_tensioned_membrane/build_pcve_steel_ball_tensioned_membrane.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "verify",
        "prepare",
        "all",
        "simulate",
        "render",
        "finalize",
        "audit"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/steel_ball_tensioned_membrane/build_pcve_steel_ball_tensioned_membrane.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/steel_ball_tensioned_membrane/build_pcve_steel_ball_tensioned_membrane.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/steel_ball_tensioned_membrane/build_pcve_steel_ball_tensioned_membrane.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/steel_ball_tensioned_membrane/build_pcve_steel_ball_tensioned_membrane.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/steel_ball_tensioned_membrane/simulate_steel_ball_tensioned_membrane.py",
    "render_entry": "scripts/rigid_elastic/steel_ball_tensioned_membrane/render_steel_ball_tensioned_membrane.py",
    "current_suite": "renders/pcve_suites/pcve_steel_ball_tensioned_membrane_suite",
    "notes": [
        "native_cli_case_id selects the original scenario; catalog_case_id names the published edit_* video directory.",
        "The original simulator, renderer, runtime and worker requirements remain those documented by this scene.",
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
import hashlib
import json
import os
import subprocess

from edit_vocab import CASE_DSL,SPEC,override_for
from pcve_media_contract import require_video,require_times
from scene_paths import DATA,blender_runtime,output_path,worker_only

CASES=tuple(SPEC['cases'])
STAGES=('simulate','render','finalize','audit')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def verify(root,cases):
    accepted=read(root/'accepted_case.json')
    records={row['id']:row for row in accepted['variants']}
    rows=[]
    for case in cases:
        row=records[case]
        video=root/row['video_path']
        native=root/row['raw_artifact_root']
        cache=native/'simulation.npz'
        cfg=read(native/'simulation_config.json')
        expected=dict(SPEC['baseline'])
        expected.update(override_for(case))
        if cfg['physics']!=expected or row['edit_dsl']!=CASE_DSL[case]:
            raise RuntimeError(f'Accepted resolved physical inputs differ for {case}')
        video_hash,cache_hash=sha(video),sha(cache)
        if video_hash!=row['video_sha256'] or cache_hash!=row['retained_raw_artifacts']['simulation.npz']['sha256']:
            raise RuntimeError(f'Accepted video or native cache changed for {case}')
        require_video(video)
        transforms=read(native/'ground_truth_transforms.json')
        require_times([frame['time_s'] for frame in transforms['frames']])
        render=read(native/'render_report.json')
        if render['cache_sha256']!=cache_hash or render['playback_rate']!=1.0:
            raise RuntimeError(f'Accepted render replay differs for {case}')
        rows.append({'case':case,'video_sha256':video_hash,'state_sha256':cache_hash})
    print(json.dumps({'verified_cases':rows},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('verify','prepare','all',*STAGES))
    parser.add_argument('--stages',nargs='+',choices=STAGES)
    parser.add_argument('--cases',nargs='+',choices=CASES,default=list(CASES))
    parser.add_argument('--out',type=Path)
    parser.add_argument('--accepted-root',type=Path,default=DATA)
    parser.add_argument('--blender-bin',type=Path)
    parser.add_argument('--gpu-uuid',default='auto')
    parser.add_argument('--render-threads',type=int,default=6)
    args=parser.parse_args()
    if args.stage and args.stages:
        parser.error('Use either --stage or --stages')
    stages=args.stages or (list(STAGES) if args.stage=='all' else [args.stage or 'verify'])
    if stages==['verify']:
        verify(args.accepted_root,args.cases)
        raise SystemExit()
    if stages==['prepare']:
        subprocess.run([sys.executable,'-B',str(SCRIPTS/'download_assets.py'),
                        '--scene','steel_ball_tensioned_membrane','--check'],check=True)
        raise SystemExit()
    if 'simulate' in stages or 'render' in stages:
        worker_only()
    if args.out is None:
        parser.error('Supply --out-root under renders/steel_ball_tensioned_membrane/ for reconstruction')
    out=output_path(args.out)
    runtime=blender_runtime(args.blender_bin)
    for case in args.cases:
        override_for(case)
        folder=out/'cases'/case
        if 'simulate' in stages:
            subprocess.run([sys.executable,'-B',str(CASE/'simulate_steel_ball_tensioned_membrane.py'),
                            '--case',case,'--out',str(folder),'--gpu',args.gpu_uuid,'--threads',str(args.render_threads)],check=True)
        if 'render' in stages:
            subprocess.run([sys.executable,'-B',str(CASE/'render_steel_ball_tensioned_membrane.py'),
                            '--case',case,'--cache',str(folder/'simulation.npz'),'--out',str(folder),
                            '--blender',str(runtime),'--gpu',args.gpu_uuid,'--threads',str(args.render_threads)],check=True)
            subprocess.run([str(runtime),'-b','--factory-startup','--disable-autoexec','--python-exit-code','1',
                            '--python',str(CASE/'tools/audit_native_replay.py'),'--','--case-dir',str(folder)],
                           env=dict(os.environ,CUDA_VISIBLE_DEVICES='-1'),check=True)
        if 'finalize' in stages:
            subprocess.run([sys.executable,'-B',str(CASE/'tools/finalize.py'),'--case-dir',str(folder),
                            '--case',case],check=True)
    if 'audit' in stages:
        subprocess.run([sys.executable,'-B',str(CASE/'tools/audit_real4s.py'),'--root',str(out),
                        '--out',str(out/'audit.json')],check=True)
