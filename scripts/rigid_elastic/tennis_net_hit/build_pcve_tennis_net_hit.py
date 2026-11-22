"""Verify the accepted native delivery and the published six-case suite, or check the registered assets."""

# PCVE_EDIT_CATALOG_BEGIN
# Source descriptions and five independent edits for the current published suite.
# Values in physics_override use the recorded shared-DSL/native-plan schema;
# scene-native adapters retain all required solver-field and presence conversions.
PCVE_SCENE = "tennis_net_hit"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "户外网球场上,一个网球从球网对面飞来,撞上张紧的球网后被弹回,落在对面的场地上滚开,球网晃动后慢慢恢复平静。",
            "en": "On an outdoor tennis court, a tennis ball flies in from the far side of the net, hits the taut tennis net, is thrown back onto the far court and rolls away while the net sways and settles."
        },
        "quantitative": {
            "zh": "户外硬地网球场上,一个直径 6.7 cm、质量 57.6 g 的网球从球网对面 1.8 m、离地 0.81 m 处以 8 m/s 的初速度飞向球网;球网中央高 0.914 m,网线的杨氏模量为 25 MPa。网球撞上张紧的球网后被弹回,落在对面的场地上滚开,球网晃动后慢慢恢复平静。",
            "en": "On an outdoor hard court, a tennis ball 6.7 cm in diameter and 57.6 g in mass starts on the far side, 1.8 m from the net and 0.81 m above the ground, and flies toward the net at an initial speed of 8 m/s; the tennis net is 0.914 m high at the centre and its cords have a Young's modulus of 25 MPa. The ball hits the taut net, is thrown back onto the far court and rolls away while the net sways and settles."
        }
    },
    "editable_objects": [
        {"object_id": "tennis_ball", "zh": "网球", "en": "the tennis ball",
         "properties": ["initial_velocity"], "can_delete": False},
        {"object_id": "tennis_net", "zh": "球网", "en": "the tennis net",
         "properties": ["young_modulus"], "can_delete": True}
    ],
    "description_basis": "Values from the frozen solver configuration (ball radius 0.0335 m, mass 0.0576 kg, start (0.85, -1.8, 0.81) m, forward speed 8 m/s, net centre height 0.914 m, strand effective modulus 25 MPa); motion as seen in the source video. Edit prompts are the output of pcve_edit_dsl.make_prompts for edit_vocab.py."
}

PCVE_EDITS = {
    "net_young_x10": {
        "case_id": "net_young_x10",
        "catalog_case_id": "edit_net_young_x10",
        "native_cli_case_id": "net_young_x10",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET tennis_net.young_modulus TIMES 10",
        "applies_from_frame": 1,
        "physics_override": {
            "net_young_modulus_pa": 250000000.0
        },
        "physics_diff": {
            "net_young_modulus_pa": {
                "from": 25000000.0,
                "to": 250000000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把球网的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the tennis net's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把球网的杨氏模量增加到原来的 10 倍。",
                "en": "From frame 1 onwards, increase the tennis net's Young's modulus to 10 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 net_young_x10 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case net_young_x10; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/tennis_net_hit/physics/common.py"
    },
    "ball_speed_x2": {
        "case_id": "ball_speed_x2",
        "catalog_case_id": "edit_ball_speed_x2",
        "native_cli_case_id": "ball_speed_x2",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET tennis_ball.initial_velocity TIMES 2",
        "applies_from_frame": 1,
        "physics_override": {
            "ball_initial_velocity_y_m_s": 16.0
        },
        "physics_diff": {
            "ball_initial_velocity_y_m_s": {
                "from": 8.0,
                "to": 16.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把网球的初速度调大一些。",
                "en": "From the start of the clip, increase the tennis ball's initial speed."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把网球的初速度增加到原来的 2 倍。",
                "en": "From frame 1 onwards, increase the tennis ball's initial speed to 2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 ball_speed_x2 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case ball_speed_x2; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/tennis_net_hit/physics/common.py"
    },
    "ball_speed_div5": {
        "case_id": "ball_speed_div5",
        "catalog_case_id": "edit_ball_speed_div5",
        "native_cli_case_id": "ball_speed_div5",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET tennis_ball.initial_velocity TIMES 0.2",
        "applies_from_frame": 1,
        "physics_override": {
            "ball_initial_velocity_y_m_s": 1.6
        },
        "physics_diff": {
            "ball_initial_velocity_y_m_s": {
                "from": 8.0,
                "to": 1.6
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把网球的初速度调小一些。",
                "en": "From the start of the clip, decrease the tennis ball's initial speed."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把网球的初速度减少到原来的 0.2 倍。",
                "en": "From frame 1 onwards, reduce the tennis ball's initial speed to 0.2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 ball_speed_div5 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case ball_speed_div5; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/tennis_net_hit/physics/common.py"
    },
    "remove_entire_net": {
        "case_id": "remove_entire_net",
        "catalog_case_id": "edit_remove_entire_net",
        "native_cli_case_id": "remove_entire_net",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE tennis_net",
        "applies_from_frame": 1,
        "physics_override": {
            "net_active": [
                0
            ]
        },
        "physics_diff": {
            "net_active": {
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
                "zh": "从视频一开始,把球网从场景中删除。",
                "en": "From the start of the clip, remove the tennis net from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把球网从场景中删除。",
                "en": "From frame 1 onwards, remove the tennis net from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 remove_entire_net 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case remove_entire_net; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/tennis_net_hit/physics/common.py"
    },
    "net_young_div10": {
        "case_id": "net_young_div10",
        "catalog_case_id": "edit_net_young_div10",
        "native_cli_case_id": "net_young_div10",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET tennis_net.young_modulus TIMES 0.1",
        "applies_from_frame": 1,
        "physics_override": {
            "net_young_modulus_pa": 2500000.0
        },
        "physics_diff": {
            "net_young_modulus_pa": {
                "from": 25000000.0,
                "to": 2500000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把球网的杨氏模量调小一些。",
                "en": "From the start of the clip, decrease the tennis net's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把球网的杨氏模量减少到原来的 0.1 倍。",
                "en": "From frame 1 onwards, reduce the tennis net's Young's modulus to 0.1 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 net_young_div10 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case net_young_div10; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/tennis_net_hit/physics/common.py"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/tennis_net_hit/build_pcve_tennis_net_hit.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "verify",
        "prepare"
    ],
    "publish_tool": "scripts/rigid_elastic/tennis_net_hit/tools/publish_suite.py",
    "ground_truth_tool": "scripts/rigid_elastic/tennis_net_hit/tools/export_ground_truth.py",
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/tennis_net_hit/build_pcve_tennis_net_hit.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/tennis_net_hit/build_pcve_tennis_net_hit.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/tennis_net_hit/build_pcve_tennis_net_hit.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/tennis_net_hit/build_pcve_tennis_net_hit.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/tennis_net_hit/simulate_tennis_net_hit.py",
    "render_entry": "scripts/rigid_elastic/tennis_net_hit/render_tennis_net_hit.py",
    "current_suite": "renders/pcve_suites/pcve_tennis_net_hit_suite",
    "notes": [
        "native_cli_case_id selects the original scenario; catalog_case_id names the published edit_* video directory.",
        "Physics is the accepted native solve; the render entry replays its qualified caches with the current look (appearance/realism.py).",
        "--stage verify checks the accepted native delivery and the published suite; it performs no new physical solve."
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
from scene_paths import REPO,output_path
sys.path.insert(0,str(CASE/'physics'))
from common import CASES,DATA,sha,worker_tars
from edit_vocab import VOCAB
from pcve_edit_policy import audit_suite_manifest
from pcve_media_contract import require_times,require_video

SUITE=REPO/'renders/pcve_suites/pcve_tennis_net_hit_suite'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def verify_native(data,selected):
    """The accepted native delivery: receipt, strict edit policy, original videos and native clocks."""
    result=read(data/'final_delivery_receipt.json')
    if not result['complete']:
        raise RuntimeError('The accepted delivery is incomplete')
    bundle=data/'bundle/pcve_tennis_net_hit_suite'
    audit=audit_suite_manifest(read(bundle/'suite_manifest.json'),VOCAB,bundle)
    if not audit['all_edits_compliant']:
        raise RuntimeError('Strict edit preflight of the accepted delivery failed')
    movies={r['id']:r for r in read(data/'suite_manifest.json')['movies']}
    rows=[]
    for case in selected:
        r=movies[case]
        video=data/r['video']
        qual=read(data/'physics_reports'/case/'qualification.json')
        if sha(video)!=r['sha256'] or qual['edit_dsl']!=CASES[case][1] or qual['physical_cache_sha256']!=r['physical_cache_sha256']:
            raise RuntimeError(f'Native or video binding of the accepted delivery differs for {case}')
        index=read(worker_tars(data)/(case+'_files.json'))['files']
        members={x['path']:x.get('sha256') for x in index}
        if members.get(f'physics/{case}/render_cache.npz')!=qual['render_cache_sha256'] or \
           members.get(f'physics/{case}/ground_truth_24fps.npz')!=qual['ground_truth_sha256']:
            raise RuntimeError(f'Worker tar index does not list the qualified cache/GT of {case}')
        require_video(video)
        require_times(qual['native_frame_times_s'])
        rows.append({'case':case,'delivery_video_sha256':r['sha256'],'state_sha256':r['physical_cache_sha256'],
                     'render_cache_sha256':qual['render_cache_sha256'],'ground_truth_sha256':qual['ground_truth_sha256']})
    return rows


def verify_suite(suite,data,selected):
    """The published suite: pinned videos, media contract, prompts = catalog, GT = native states,
    and every video rendered from the qualified render cache of its case."""
    from pcve_edit_catalog import load_catalog
    catalog=load_catalog(Path(__file__))
    canonical=read(CASE/'scene_manifest.json')['canonical_suites']['pcve_tennis_net_hit_suite']
    if (REPO/canonical['target']).resolve()!=suite.resolve():
        raise RuntimeError('scene_manifest.json points at another suite')
    manifest=read(suite/'suite_manifest.json')
    listed={r['case_id']:r for r in [manifest['source'],*manifest['edits']]}
    text=(suite/'suite_manifest.json').read_text(encoding='utf-8')
    if '_case' + '_data' in text:
        raise RuntimeError('suite_manifest.json names a scripts/_case_data path')
    rows=[]
    for case in selected:
        record=catalog['source'] if case=='source' else catalog['edits'][case]
        cid=record['catalog_case_id'];folder=suite/'cases'/cid
        video=folder/'video.mp4';digest=sha(video)
        if digest!=canonical['case_video_sha256'][case] or listed[cid]['video_sha256']!=digest or \
           read(folder/'provenance.json')['video_sha256']!=digest:
            raise RuntimeError(f'{cid}: video differs from scene_manifest/suite_manifest/provenance')
        media=require_video(video)
        prompts=read(folder/'prompts.json')
        same=prompts['prompts']==record['prompts'] and prompts['edit_dsl']==record['edit_dsl']
        if case!='source':
            same=same and prompts['physics_override']==record['physics_override'] and prompts['physics_diff']==record['physics_diff']
        if not same:
            raise RuntimeError(f'{cid}: prompts.json differs from the builder catalog')
        qual=read(data/'physics_reports'/case/'qualification.json')
        gt=read(folder/'ground_truth_transforms.json')
        require_times([f['time_sec'] for f in gt['frames']])
        if [f['tennis_ball']['location'] for f in gt['frames']]!=qual['native_ball_positions_m']:
            raise RuntimeError(f'{cid}: GT is not the native state of this case')
        provenance=read(folder/'native_metadata/realism_provenance.json')
        if provenance['render_cache_sha256']!=qual['render_cache_sha256'] or provenance['case']!=case:
            raise RuntimeError(f'{cid}: video was not rendered from the qualified render cache')
        rows.append({'case':cid,'video_sha256':digest,'frames':media['frames'],'fps':media['fps'],
                     'render_cache_sha256':qual['render_cache_sha256'],'look':provenance.get('revision')})
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('verify','prepare'),default='verify')
    parser.add_argument('--cases',nargs='+',choices=tuple(CASES),default=list(CASES))
    parser.add_argument('--out',type=Path,help='Also write the verify report to <out>/verify_report.json (under renders/tennis_net_hit/)')
    parser.add_argument('--accepted-root',type=Path,default=DATA,help='Accepted native delivery')
    parser.add_argument('--suite',type=Path,default=SUITE,help='Published suite checked by --stage verify')
    args=parser.parse_args()
    if args.stage=='verify':
        report=json.dumps({'native_delivery':verify_native(args.accepted_root,args.cases),
                           'published_suite':verify_suite(args.suite,args.accepted_root,args.cases)},indent=2)
        print(report)
        if args.out is not None:
            out=output_path(args.out);out.mkdir(parents=True,exist_ok=True)
            (out/'verify_report.json').write_text(report+'\n',encoding='utf-8')
    else:
        subprocess.run([sys.executable,'-B',str(SCRIPTS/'download_assets.py'),'--scene','rigid_elastic/tennis_net_hit','--check'],check=True)
