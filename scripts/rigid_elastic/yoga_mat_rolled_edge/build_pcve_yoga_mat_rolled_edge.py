"""Verify the published suite against the native caches, prompts and ground truth of this scene."""

# PCVE_EDIT_CATALOG_BEGIN
# Source descriptions and five independent edits for the current published suite.
# Values in physics_override use the recorded shared-DSL/native-plan schema;
# scene-native adapters retain all required solver-field and presence conversions.
PCVE_SCENE = "yoga_mat_rolled_edge"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "室内地板上，药球滚向卷边瑜伽垫，并与可变形的垫边发生接触。",
            "en": "On an indoor floor, a medicine ball rolls towards the curled edge of a yoga mat and contacts the deformable mat."
        },
        "quantitative": {
            "zh": "室内地板上，药球滚向卷边瑜伽垫，并与可变形的垫边发生接触。药球直径 24.1 cm、质量 5 kg，以 0.9 m/s 的速度纯滚动；瑜伽垫长 1.8 m、宽 0.66 m、厚 6 mm，杨氏模量为 6 MPa，卷起的垫边高约 3.4 cm。",
            "en": "On an indoor floor, a medicine ball rolls towards the curled edge of a yoga mat and contacts the deformable mat. The ball is 24.1 cm across, weighs 5 kg and rolls without slipping at 0.9 m/s; the mat is 1.8 m long, 0.66 m wide and 6 mm thick with a Young's modulus of 6 MPa, and its curled edge rises about 3.4 cm."
        }
    },
    "description_basis": "Current scene code (edit_vocab.BASELINE, physics/scene_spec.json: ball radius 0.12065 m, 5.0 kg, 0.9 m/s; mat 1.8 x 0.66 x 0.006 m, E 6 MPa, curl tip about 0.0335 m above the floor); physical outcomes beyond the visible interaction are not asserted."
}

PCVE_EDITS = {
    "young_x4": {
        "case_id": "young_x4",
        "catalog_case_id": "edit_young_x4",
        "native_cli_case_id": "mat_stiff",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET mat.young_modulus TIMES 4",
        "applies_from_frame": 1,
        "physics_override": {
            "mat_young_modulus_pa": 24000000.0
        },
        "physics_diff": {
            "mat_young_modulus_pa": {
                "from": 6000000.0,
                "to": 24000000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把卷边瑜伽垫的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the curled yoga mat's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把卷边瑜伽垫的杨氏模量增加到原来的 4 倍。",
                "en": "From frame 1 onwards, increase the curled yoga mat's Young's modulus to 4 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 mat_stiff 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case mat_stiff; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/yoga_mat_rolled_edge/edit_vocab.py"
    },
    "delete_mat": {
        "case_id": "delete_mat",
        "catalog_case_id": "edit_delete_mat",
        "native_cli_case_id": "delete_mat",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE mat",
        "applies_from_frame": 1,
        "physics_override": {
            "mat_present": [
                0
            ]
        },
        "physics_diff": {
            "mat_present": {
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
                "zh": "从视频一开始,把卷边瑜伽垫从场景中删除。",
                "en": "From the start of the clip, remove the curled yoga mat from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把卷边瑜伽垫从场景中删除。",
                "en": "From frame 1 onwards, remove the curled yoga mat from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 delete_mat 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case delete_mat; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/yoga_mat_rolled_edge/edit_vocab.py"
    },
    "mass_x0p25": {
        "case_id": "mass_x0p25",
        "catalog_case_id": "edit_mass_x0p25",
        "native_cli_case_id": "ball_mass_light",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET ball.mass TIMES 0.25",
        "applies_from_frame": 1,
        "physics_override": {
            "ball_mass_kg": 1.25
        },
        "physics_diff": {
            "ball_mass_kg": {
                "from": 5.0,
                "to": 1.25
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把药球的质量调小一些。",
                "en": "From the start of the clip, decrease the medicine ball's mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把药球的质量减少到原来的 0.25 倍。",
                "en": "From frame 1 onwards, reduce the medicine ball's mass to 0.25 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 ball_mass_light 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case ball_mass_light; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/yoga_mat_rolled_edge/edit_vocab.py"
    },
    "speed_x0p5": {
        "case_id": "speed_x0p5",
        "catalog_case_id": "edit_speed_x0p5",
        "native_cli_case_id": "ball_speed_slow",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET ball.rolling_speed TIMES 0.5",
        "applies_from_frame": 1,
        "physics_override": {
            "ball_initial_speed_m_s": 0.45
        },
        "physics_diff": {
            "ball_initial_speed_m_s": {
                "from": 0.9,
                "to": 0.45
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把药球的初始纯滚动速度调小一些。",
                "en": "From the start of the clip, decrease the medicine ball's initial no-slip rolling speed."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把药球的初始纯滚动速度减少到原来的 0.5 倍。",
                "en": "From frame 1 onwards, reduce the medicine ball's initial no-slip rolling speed to 0.5 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 ball_speed_slow 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case ball_speed_slow; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/yoga_mat_rolled_edge/edit_vocab.py"
    },
    "mass_x0p25_at_frame_16": {
        "case_id": "mass_x0p25_at_frame_16",
        "catalog_case_id": "edit_mass_x0p25_at_frame_16",
        "native_cli_case_id": "mass_x0p25_at_frame_16",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET ball.mass TIMES 0.25 AT FRAME 16",
        "applies_from_frame": 16,
        "physics_override": {
            "ball_mass_kg": 1.25
        },
        "physics_diff": {
            "ball_mass_kg": {
                "from": 5.0,
                "to": 1.25
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "在视频前段,把药球的质量调小一些。",
                "en": "Early in the clip, decrease the medicine ball's mass."
            },
            "quantitative": {
                "zh": "从第 16 帧开始,把药球的质量减少到原来的 0.25 倍。",
                "en": "From frame 16 onwards, reduce the medicine ball's mass to 0.25 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 mass_x0p25_at_frame_16 案例；第 1–15 帧就是 source 的原生状态，第 16 帧（t = 15/24 s）从 24 fps source 缓存恢复垫子和药球的完整状态，把药球质量改为 1.25 kg 后继续求解到 t = 95/24 s（simulate --case mass_x0p25_at_frame_16 --source-cache <source simulation.npz>），再逐帧渲染全部 96 帧。",
            "en": "Select native case mass_x0p25_at_frame_16; frames 1-15 are the source's native state. At frame 16 (t = 15/24 s) the complete state of the mat and the ball is restored from the 24 fps source cache, the ball's mass becomes 1.25 kg and the solve continues to t = 95/24 s (simulate --case mass_x0p25_at_frame_16 --source-cache <source simulation.npz>); all 96 frames are then rendered."
        },
        "definition_source": "scripts/rigid_elastic/yoga_mat_rolled_edge/edit_vocab.py"
    },
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/yoga_mat_rolled_edge/build_pcve_yoga_mat_rolled_edge.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "verify",
        "prepare"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/yoga_mat_rolled_edge/build_pcve_yoga_mat_rolled_edge.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/yoga_mat_rolled_edge/build_pcve_yoga_mat_rolled_edge.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/yoga_mat_rolled_edge/build_pcve_yoga_mat_rolled_edge.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/yoga_mat_rolled_edge/build_pcve_yoga_mat_rolled_edge.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/yoga_mat_rolled_edge/simulate_yoga_mat_rolled_edge.py",
    "render_entry": "scripts/rigid_elastic/yoga_mat_rolled_edge/render_yoga_mat_rolled_edge.py",
    "current_suite": "renders/pcve_suites/pcve_yoga_mat_rolled_edge_suite",
    "notes": [
        "native_cli_case_id selects the original scenario; catalog_case_id names the published edit_* video directory.",
        "--stage verify checks the published suite (videos, prompts, the native caches in cases/*/native_metadata, ground truth); --stage prepare checks the registered assets.",
        "The builder does not solve or render; use the simulate and render entries for reproduction."
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
import subprocess

from edit_vocab import BASELINE,CASE_DSL,TIMED_DSL,override_for,timed_override
from scene_paths import SCENE,SUITE_NAME,output_path,suite_dir

TIMED_PREFIX=('mat_positions','mat_velocities','ball_transforms','ball_affine_velocities','times')


def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(4<<20),b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def check(condition,message):
    if not condition:
        raise RuntimeError(message)


def expected_physics(case):
    """Solver values of one native case from edit_vocab (whole-clip override, or timed change and its frame)."""
    physics=dict(BASELINE)
    if case in TIMED_DSL:
        change,frame=timed_override(case)
        physics.update(change)
        return physics,frame
    physics.update(override_for(case))
    return physics,None


def verify_case(suite,case,record,expected_video):
    import numpy as np
    from pcve_media_contract import require_times,require_video
    from tools.export_ground_truth import differences
    folder=suite/'cases'/record['catalog_case_id']
    meta=folder/'native_metadata'
    video=folder/'video.mp4'
    digest=sha256(video)
    check(digest==expected_video,f'{case}: suite video differs from scene_manifest.json')
    media=require_video(video)
    prompts=read(folder/'prompts.json')
    check(prompts.get('format_version')=='pcve_prompts/1' and prompts['prompts']==record['prompts']
          and prompts.get('edit_dsl')==record.get('edit_dsl'),f'{case}: prompts.json differs from the builder catalog')
    receipt=read(meta/'encoding_receipt.json')
    cache=meta/'simulation.npz'
    check(receipt['video_sha256']==digest and receipt['native_cache_sha256']==sha256(cache)
          and receipt['fps']==24 and receipt['frames']==96,f'{case}: video was not encoded from this native cache at 24 fps')
    check(read(meta/'source_audit.json')['status']=='passed',f'{case}: native collision audit did not pass')
    config=read(meta/'simulation_config.json')
    physics,frame=expected_physics(case)
    observed=(config['ball']['radius_m'],config['ball']['mass_kg'],config['ball']['rolling_speed_m_s'],
              config['mat']['effective_young_modulus_pa'],bool(config.get('mat_present',True)))
    wanted=(physics['ball_radius_m'],physics['ball_mass_kg'],physics['ball_initial_speed_m_s'],
            physics['mat_young_modulus_pa'],bool(physics['mat_present']))
    check(observed==wanted,f'{case}: native parameters {observed} differ from edit_vocab {wanted}')
    check(config['simulation']['fps']==24 and config['simulation']['dt_s']==1/960,f'{case}: native clock or step differs')
    with np.load(cache,allow_pickle=False) as data:
        require_times(data['times'])
        states={k:data[k] for k in TIMED_PREFIX} if frame else None
    row={'case_id':case,'suite_case':record['catalog_case_id'],'video_sha256':digest,
         'native_cache_sha256':receipt['native_cache_sha256'],'media':media}
    if frame:
        timed=config.get('timed_edit') or {}
        handoff=timed.get('state_handoff_max_abs',{})
        check(timed.get('frame')==frame and handoff and max(handoff.values())<1e-8,f'{case}: timed hand-off record missing or inexact')
        source=suite/'cases/source/native_metadata/simulation.npz'
        check(timed.get('source_cache_sha256')==sha256(source),f'{case}: continued from another source cache than the published one')
        with np.load(source,allow_pickle=False) as data:
            check(all(np.array_equal(states[k][:frame-1],data[k][:frame-1]) for k in TIMED_PREFIX),
                  f'{case}: frames 1..{frame-1} differ from the source cache')
        row['timed']={'frame':frame,'state_handoff_max_abs':handoff,'prefix_frames_identical':frame-1}
    gt=read(folder/'ground_truth_transforms.json')
    check(gt.get('format_version')=='pcve_ground_truth/1',f'{case}: ground truth is not pcve_ground_truth/1')
    require_times([f['time_sec'] for f in gt['frames']])
    changed=differences(folder)
    check(not changed,f'{case}: ground truth differs from a fresh export in {changed}')
    row['ground_truth_frames']=len(gt['frames'])
    return row


def verify(suite,cases):
    from pcve_edit_catalog import load_catalog
    catalog=load_catalog(Path(__file__))
    records={r['native_cli_case_id']:r for r in [catalog['source'],*catalog['edits'].values()]}
    manifest=read(CASE/'scene_manifest.json')['canonical_suites'][SUITE_NAME]
    rows=[verify_case(suite,case,records[case],manifest['case_video_sha256'][case]) for case in cases]
    return {'scene':SCENE,'suite':str(suite),'verified_cases':rows}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('verify','prepare'),default='verify')
    parser.add_argument('--cases',nargs='+',choices=tuple(CASE_DSL)+tuple(TIMED_DSL),default=list(CASE_DSL)+list(TIMED_DSL))
    parser.add_argument('--suite',type=Path,help='suite to verify (default: the published suite of scene_manifest.json)')
    parser.add_argument('--out-root',type=Path,help='also write the verify report to DIR/verify_report.json')
    args=parser.parse_args()
    if args.stage=='prepare':
        subprocess.run([sys.executable,'-B',str(SCRIPTS/'download_assets.py'),'--scene',SCENE,'--check'],check=True)
    else:
        result=verify((args.suite or suite_dir()).resolve(),list(dict.fromkeys(args.cases)))
        text=json.dumps(result,indent=2)
        if args.out_root:
            out=output_path(args.out_root)
            out.mkdir(parents=True,exist_ok=True)
            (out/'verify_report.json').write_text(text+'\n',encoding='utf-8')
        print(text)
