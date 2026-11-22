"""Verify or package the published suite: six videos, the accepted native solves and the edit catalog."""

# PCVE_EDIT_CATALOG_BEGIN
# Source description and five independent edits of the published suite.
# Values in physics_override use the shared-DSL schema; physics/vocabulary.py owns the solver fields.
PCVE_SCENE = "plastic_ruler_coin"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "书桌边上,一本厚的精装书把一把透明塑料尺压在桌面上,尺子的一端伸出桌沿悬空。一枚硬币从尺子悬空一端的上方由静止落下,砸在尺子上。",
            "en": "At the edge of a desk, a thick hardcover book holds a clear plastic ruler down on the desk top, with one end of the ruler sticking out past the edge. A coin is released from rest above the overhanging end and drops onto the ruler."
        },
        "quantitative": {
            "zh": "书桌边上,一本 1.6 kg 的精装书把一把长 31.75 cm、宽 3.1 cm、厚 1.6 mm 的透明塑料尺压在桌面上,尺子伸出桌沿 14 cm,杨氏模量为 2.4 GPa,密度为 1200 kg/m³。一枚直径 23.25 mm、厚 2.33 mm、质量 7.5 g 的硬币,中心在桌沿外 11.3 cm 处,从尺面上方 5 cm 的高度由静止落下,砸在尺子上。",
            "en": "At the edge of a desk, a 1.6 kg hardcover book holds down a clear plastic ruler 31.75 cm long, 3.1 cm wide and 1.6 mm thick, with 14 cm of it sticking out past the edge; the ruler has a Young's modulus of 2.4 GPa and a density of 1200 kg/m³. A coin 23.25 mm across, 2.33 mm thick and weighing 7.5 g, centred 11.3 cm out from the desk edge, is released from rest 5 cm above the ruler and drops onto it."
        }
    },
    "editable_objects": [
        {"object_id": "coin", "zh": "硬币", "en": "the coin", "in_video": True,
         "properties": ["mass"], "can_delete": True, "can_add": False},
        {"object_id": "ruler", "zh": "塑料尺", "en": "the plastic ruler", "in_video": True,
         "properties": ["young_modulus"], "can_delete": False, "can_add": False},
        {"object_id": "second_coin", "zh": "同样的硬币", "en": "an identical coin", "in_video": False,
         "properties": [], "can_delete": False, "can_add": True}
    ],
    "description_basis": "Baseline of physics/scene_spec.json: ruler 317.5 x 31 x 1.6 mm, 140 mm overhang, E = 2.4 GPa, 1200 kg/m^3; coin 7.5 g, radius 11.625 mm, thickness 2.33 mm, centre x = 113 mm, bottom face 50 mm above the flat ruler; book 1.6 kg. Outcomes beyond the visible interaction are not asserted."
}

PCVE_EDITS = {
    "add_second_coin": {
        "case_id": "add_second_coin",
        "catalog_case_id": "edit_add_second_coin",
        "native_cli_case_id": "add_second_coin",
        "kind": "edit",
        "operation": "ADD",
        "edit_dsl": "ADD second_coin BETWEEN book_edge AND ruler_end AT MIDPOINT",
        "native_edit_dsl": "ADD second_coin AT PRESET resting_on_ruler",
        "applies_from_frame": 1,
        "physics_override": {
            "second_coin_present": [
                1
            ]
        },
        "physics_diff": {
            "second_coin_present": {
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
                "zh": "从视频一开始,在书的边缘和尺子末端的连线上、大致中间的位置,放一个同样的硬币。",
                "en": "From the start of the clip, place an identical coin on the line between the edge of the book and the end of the ruler, about midway between them."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,在书的边缘和尺子末端连线的中点放一个同样的硬币。",
                "en": "From frame 1 onwards, place an identical coin at the midpoint of the line between the edge of the book and the end of the ruler."
            }
        },
        "label_zh": "尺面中部加一枚同样的硬币",
        "how_to_edit": {
            "zh": "选择 add_second_coin 案例；按 native_edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。edit_dsl 是仓库定位 DSL 形式的语句(端点 book_edge、ruler_end 是 edit_vocab.py 里只用于定位的锚点),prompt 按它写成。",
            "en": "Select native case add_second_coin; apply native_edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render. edit_dsl is the placement statement in the repository's placement DSL form the prompts are written from (its endpoints book_edge and ruler_end are locating-only anchors in edit_vocab.py)."
        },
        "definition_source": "scripts/rigid_elastic/plastic_ruler_coin/physics/scene_spec.json"
    },
    "coin_mass_x02": {
        "case_id": "coin_mass_x02",
        "catalog_case_id": "edit_coin_mass_x02",
        "native_cli_case_id": "coin_mass_x02",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET coin.mass TIMES 0.2",
        "applies_from_frame": 1,
        "physics_override": {
            "coin_mass_kg": 0.0015
        },
        "physics_diff": {
            "coin_mass_kg": {
                "from": 0.0075,
                "to": 0.0015
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把硬币的质量调小一些。",
                "en": "From the start of the clip, decrease the coin's mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把硬币的质量减少到原来的 0.2 倍。",
                "en": "From frame 1 onwards, reduce the coin's mass to 0.2 times its original value."
            }
        },
        "label_zh": "硬币质量 ×0.2",
        "how_to_edit": {
            "zh": "选择 coin_mass_x02 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case coin_mass_x02; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/plastic_ruler_coin/physics/scene_spec.json"
    },
    "delete_coin": {
        "case_id": "delete_coin",
        "catalog_case_id": "edit_delete_coin",
        "native_cli_case_id": "delete_coin",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE coin",
        "applies_from_frame": 1,
        "physics_override": {
            "coin_present": [
                0
            ]
        },
        "physics_diff": {
            "coin_present": {
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
                "zh": "从视频一开始,把硬币从场景中删除。",
                "en": "From the start of the clip, remove the coin from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把硬币从场景中删除。",
                "en": "From frame 1 onwards, remove the coin from the scene."
            }
        },
        "label_zh": "删除硬币",
        "how_to_edit": {
            "zh": "选择 delete_coin 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case delete_coin; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/plastic_ruler_coin/physics/scene_spec.json"
    },
    "ruler_modulus_x025": {
        "case_id": "ruler_modulus_x025",
        "catalog_case_id": "edit_ruler_modulus_x025",
        "native_cli_case_id": "ruler_modulus_x025",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET ruler.young_modulus TIMES 0.25",
        "applies_from_frame": 1,
        "physics_override": {
            "ruler_young_modulus_pa": 600000000.0
        },
        "physics_diff": {
            "ruler_young_modulus_pa": {
                "from": 2400000000.0,
                "to": 600000000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把塑料尺的杨氏模量调小一些。",
                "en": "From the start of the clip, decrease the plastic ruler's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把塑料尺的杨氏模量减少到原来的 0.25 倍。",
                "en": "From frame 1 onwards, reduce the plastic ruler's Young's modulus to 0.25 times its original value."
            }
        },
        "label_zh": "尺子杨氏模量 ×0.25",
        "how_to_edit": {
            "zh": "选择 ruler_modulus_x025 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case ruler_modulus_x025; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/plastic_ruler_coin/physics/scene_spec.json"
    },
    "ruler_modulus_x8": {
        "case_id": "ruler_modulus_x8",
        "catalog_case_id": "edit_ruler_modulus_x8",
        "native_cli_case_id": "ruler_modulus_x8",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET ruler.young_modulus TIMES 8",
        "applies_from_frame": 1,
        "physics_override": {
            "ruler_young_modulus_pa": 19200000000.0
        },
        "physics_diff": {
            "ruler_young_modulus_pa": {
                "from": 2400000000.0,
                "to": 19200000000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把塑料尺的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the plastic ruler's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把塑料尺的杨氏模量增加到原来的 8 倍。",
                "en": "From frame 1 onwards, increase the plastic ruler's Young's modulus to 8 times its original value."
            }
        },
        "label_zh": "尺子杨氏模量 ×8",
        "how_to_edit": {
            "zh": "选择 ruler_modulus_x8 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case ruler_modulus_x8; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/plastic_ruler_coin/physics/scene_spec.json"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/plastic_ruler_coin/build_pcve_plastic_ruler_coin.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "verify",
        "package"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/plastic_ruler_coin/build_pcve_plastic_ruler_coin.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/plastic_ruler_coin/build_pcve_plastic_ruler_coin.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/plastic_ruler_coin/build_pcve_plastic_ruler_coin.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/plastic_ruler_coin/build_pcve_plastic_ruler_coin.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/plastic_ruler_coin/simulate_plastic_ruler_coin.py",
    "render_entry": "scripts/rigid_elastic/plastic_ruler_coin/render_plastic_ruler_coin.py",
    "ground_truth_tool": "scripts/rigid_elastic/plastic_ruler_coin/tools/export_ground_truth.py",
    "current_suite": "renders/pcve_suites/pcve_plastic_ruler_coin_suite",
    "notes": [
        "native_cli_case_id selects the scenario; catalog_case_id names the published edit_* video directory.",
        "verify checks the accepted delivery, the six accepted native solves and the published suite; package copies the published suite.",
        "Run verify with the repository venv (.venv-rigid-elastic/bin/python): it reads the native caches with numpy."
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
SCRIPTS = CASE.parents[1]
sys.path.insert(0, str(SCRIPTS))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, 'build_pcve')
# PCVE_UNIFIED_ENTRY_END

import argparse
import hashlib
import json
import shutil

sys.path.insert(0, str(CASE))
from scene_paths import (CASES, CATALOG, DELIVERED_SUITE, OUTPUT, SCENE, SUITE_NAME, cache_dir, media,
                         output_path)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def pinned_location(case, name, digest):
    """Where a file pinned by an artifact_manifest.json of the accepted delivery lives now."""
    if name in ("simulation.npz", "simulation_config.json", "simulation_report.json"):
        return cache_dir(case) / name                     # accepted solves: reproduction inputs in assets/
    return DELIVERED_SUITE / "cases" / case / name


def verify_delivery():
    from pcve_edit_policy import audit_suite_manifest
    from edit_vocab import VOCAB
    pinned = 0
    for case in CASES:
        manifest = json.loads((DELIVERED_SUITE / "cases" / case / "artifact_manifest.json").read_text())
        for row in manifest["files"]:
            if "sha256" not in row:
                continue  # code and record files are listed by path only
            location = pinned_location(case, row["path"], row["sha256"])
            if sha256(location) != row["sha256"]:
                raise ValueError(f"Accepted delivery file changed: {case}/{row['path']} -> {location}")
            pinned += 1
    native = json.loads((DELIVERED_SUITE / "suite_manifest.json").read_text())
    policy = audit_suite_manifest(native, VOCAB, DELIVERED_SUITE)
    if not policy["all_edits_compliant"]:
        raise ValueError("Edit policy audit of the accepted delivery suite failed")
    return {"pinned_files": pinned, "edit_policy_compliant": True}


def verify_caches(cases):
    import numpy as np
    from pcve_media_contract import require_times
    sys.path.insert(0, str(CASE / "physics"))
    import vocabulary
    for case in cases:
        config = json.loads((cache_dir(case) / "simulation_config.json").read_text())
        if not vocabulary.recorded_physics_matches(config["physics"], case):
            raise ValueError("Native solve parameters differ from physics/scene_spec.json: " + case)
        with np.load(cache_dir(case) / "simulation.npz") as data:
            if len(data["times"]) != 97 or float(data["times"][-1]) != 4.0:
                raise ValueError("Native solve does not hold the 97 states i/24, i = 0..96: " + case)
            require_times(data["times"][:96])
            if [bool(v) for v in data["present"]] != [bool(config["physics"]["coin_present"][0]),
                                                       bool(config["physics"]["second_coin_present"][0])]:
                raise ValueError("Native solve and its parameters disagree on the coins present: " + case)
    return list(cases)


def verify_suite(cases):
    from pcve_edit_catalog import load_catalog
    from pcve_media_contract import require_times, require_video
    root = media()
    pinned_videos = json.loads((CASE / "scene_manifest.json").read_text())["canonical_suites"][SUITE_NAME]["case_video_sha256"]
    catalog = load_catalog(Path(__file__))
    published = json.loads((root / "suite_manifest.json").read_text())
    records = {r["native_case_id"]: r for r in [published["source"], *published["edits"]]}
    declared = {"source": catalog["source"], **catalog["edits"]}
    result = []
    for case in cases:
        record = records[case]
        video = root / record["video"]
        folder = video.parent
        digest = sha256(video)
        provenance = json.loads((folder / "provenance.json").read_text())
        if not digest == record["video_sha256"] == provenance["video_sha256"] == pinned_videos[case]:
            raise ValueError("Published video differs from suite_manifest/provenance/scene_manifest: " + str(video))
        prompts = json.loads((folder / "prompts.json").read_text())
        if prompts["prompts"] != declared[case]["prompts"] or prompts["edit_dsl"] != declared[case].get("edit_dsl"):
            raise ValueError("prompts.json differs from the declared catalog: " + case)
        gt = json.loads((folder / "ground_truth_transforms.json").read_text())
        if gt.get("format_version") != "pcve_ground_truth/1" or len(gt["frames"]) != 96 or gt["frame_end"] != 96 or "camera" not in gt:
            raise ValueError("Ground truth does not follow the suite format: " + case)
        require_times([frame["time_sec"] for frame in gt["frames"]])
        result.append({"case_id": case, "catalog_case_id": CATALOG[case], "video": str(video), "media": require_video(video)})
    return {"suite": str(root), "verified_cases": result}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", choices=("verify", "package"), default="verify")
    p.add_argument("--cases", nargs="+", choices=list(CASES), default=list(CASES))
    p.add_argument("--out", type=Path, default=OUTPUT / "export", help="package: copy of the published suite")
    a = p.parse_args()
    result = {"scene": SCENE, "delivery": verify_delivery(), "native_caches": verify_caches(a.cases), **verify_suite(a.cases)}
    if a.stage == "package":
        if set(a.cases) != set(CASES):
            p.error("Package the complete six-case suite")
        target = output_path(a.out)
        shutil.copytree(media(), target)
        result["package"] = str(target)
    print(json.dumps(result, ensure_ascii=False, default=str))
