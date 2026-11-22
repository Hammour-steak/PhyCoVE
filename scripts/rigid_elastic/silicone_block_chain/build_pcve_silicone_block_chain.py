"""Verify the published suite: its six videos, prompts and ground truth, the native solves they replay and the
accepted delivery behind them."""

# PCVE_EDIT_CATALOG_BEGIN
# Source description and five independent edits of the published suite.
# Values in physics_override use the shared-DSL schema; physics/config.py owns the solver fields.
PCVE_SCENE = "silicone_block_chain"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "工作台上有一个小型木制压力机关。钢球沿倾斜的木轨道滚下，落进压盘中央的浅杯里。压盘沿四根导杆下压，压缩下面的海绵块，压盘边缘同时把右侧带铰链的小木旗顶起。",
            "en": "A small wooden press rig stands on a workbench. A steel ball rolls down a sloping wooden track and drops into the shallow cup in the middle of the platen. The platen slides down four guide rods and compresses the foam block beneath it, and its edge tips up the small hinged wooden flag on the right."
        },
        "quantitative": {
            "zh": "工作台上有一个小型木制压力机关。直径 32 mm、质量 134.7 g 的钢球从一条长 18.4 cm、落差 3.6 cm 的倾斜木轨道顶端由静止滚下，落进压盘中央的浅杯里。压盘连同浅杯共 18 g，套在四根导杆上，压在一块 32 × 32 × 40 mm 的海绵块上，海绵的杨氏模量为 3 kPa，剪切黏度为 35 Pa·s，体积黏度为 70 Pa·s。压盘边缘顶起右侧一面长 7 cm、质量 3 g 的铰链小木旗。",
            "en": "A small wooden press rig stands on a workbench. A 32 mm, 134.7 g steel ball starts at rest at the top of an 18.4 cm wooden track with a 3.6 cm drop, rolls down and drops into the shallow cup in the middle of the platen. The 18 g platen with its cup slides on four guide rods and rests on a 32 × 32 × 40 mm foam block with a Young's modulus of 3 kPa, a shear viscosity of 35 Pa·s and a bulk viscosity of 70 Pa·s. The platen's edge tips up a 7 cm, 3 g hinged wooden flag on the right."
        }
    },
    "editable_objects": [
        {"object_id": "steel_ball", "zh": "钢球", "en": "the steel ball", "in_video": True,
         "properties": ["mass"], "can_delete": False, "can_add": False},
        {"object_id": "foam_block", "zh": "海绵块", "en": "the foam block", "in_video": True,
         "properties": ["viscosity", "young_modulus"], "can_delete": True, "can_add": False}
    ],
    "description_basis": "Rig geometry and baseline parameters of physics/rig.py and physics/config.py (track 0.180 m run, 0.036 m rise; ball radius 16 mm; foam 32 x 32 x 40 mm; platen 18 g; flag 70 mm, 3 g); outcomes beyond the visible interaction are not asserted."
}

PCVE_EDITS = {
    "stiff_foam": {
        "case_id": "stiff_foam",
        "catalog_case_id": "edit_stiff_foam",
        "native_cli_case_id": "stiff_foam",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET foam_block.young_modulus TIMES 4",
        "applies_from_frame": 1,
        "physics_override": {
            "foam_young_modulus_pa": 12000.0
        },
        "physics_diff": {
            "foam_young_modulus_pa": {
                "from": 3000.0,
                "to": 12000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把海绵块的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the foam block's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把海绵块的杨氏模量增加到原来的 4 倍。",
                "en": "From frame 1 onwards, increase the foam block's Young's modulus to 4 times its original value."
            }
        },
        "label_zh": "海绵杨氏模量 ×4",
        "how_to_edit": {
            "zh": "选择 stiff_foam 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case stiff_foam; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/silicone_block_chain/edit_vocab.py"
    },
    "light_ball": {
        "case_id": "light_ball",
        "catalog_case_id": "edit_light_ball",
        "native_cli_case_id": "light_ball",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET steel_ball.mass TIMES 0.5",
        "applies_from_frame": 1,
        "physics_override": {
            "ball_mass_kg": 0.06735
        },
        "physics_diff": {
            "ball_mass_kg": {
                "from": 0.1347,
                "to": 0.06735
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把钢球的质量调小一些。",
                "en": "From the start of the clip, decrease the steel ball's mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把钢球的质量减少到原来的 0.5 倍。",
                "en": "From frame 1 onwards, reduce the steel ball's mass to 0.5 times its original value."
            }
        },
        "label_zh": "钢球质量 ×0.5",
        "how_to_edit": {
            "zh": "选择 light_ball 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case light_ball; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/silicone_block_chain/edit_vocab.py"
    },
    "viscous_foam": {
        "case_id": "viscous_foam",
        "catalog_case_id": "edit_viscous_foam",
        "native_cli_case_id": "viscous_foam",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET foam_block.viscosity TIMES 4",
        "applies_from_frame": 1,
        "physics_override": {
            "foam_shear_viscosity_pa_s": 140.0,
            "foam_bulk_viscosity_pa_s": 280.0
        },
        "physics_diff": {
            "foam_shear_viscosity_pa_s": {
                "from": 35.0,
                "to": 140.0
            },
            "foam_bulk_viscosity_pa_s": {
                "from": 70.0,
                "to": 280.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把海绵块的黏度调大一些。",
                "en": "From the start of the clip, increase the foam block's viscosity."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把海绵块的黏度增加到原来的 4 倍。",
                "en": "From frame 1 onwards, increase the foam block's viscosity to 4 times its original value."
            }
        },
        "label_zh": "海绵黏度 ×4",
        "how_to_edit": {
            "zh": "选择 viscous_foam 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case viscous_foam; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/silicone_block_chain/edit_vocab.py"
    },
    "remove_foam": {
        "case_id": "remove_foam",
        "catalog_case_id": "edit_remove_foam",
        "native_cli_case_id": "remove_foam",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE foam_block",
        "applies_from_frame": 1,
        "physics_override": {
            "foam_present": [
                0
            ]
        },
        "physics_diff": {
            "foam_present": {
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
                "zh": "从视频一开始,把海绵块从场景中删除。",
                "en": "From the start of the clip, remove the foam block from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把海绵块从场景中删除。",
                "en": "From frame 1 onwards, remove the foam block from the scene."
            }
        },
        "label_zh": "移除海绵",
        "how_to_edit": {
            "zh": "选择 remove_foam 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case remove_foam; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/silicone_block_chain/edit_vocab.py"
    },
    "light_ball_at_frame_8": {
        "case_id": "light_ball_at_frame_8",
        "catalog_case_id": "edit_light_ball_at_frame_8",
        "native_cli_case_id": "light_ball_at_frame_8",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET steel_ball.mass TIMES 0.5 AT FRAME 8",
        "applies_from_frame": 8,
        "physics_override": {
            "ball_mass_kg": 0.06735
        },
        "physics_diff": {
            "ball_mass_kg": {
                "from": 0.1347,
                "to": 0.06735
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "在视频前段,把钢球的质量调小一些。",
                "en": "Early in the clip, decrease the steel ball's mass."
            },
            "quantitative": {
                "zh": "从第 8 帧开始,把钢球的质量减少到原来的 0.5 倍。",
                "en": "From frame 8 onwards, reduce the steel ball's mass to 0.5 times its original value."
            }
        },
        "label_zh": "第 8 帧起钢球质量 ×0.5",
        "how_to_edit": {
            "zh": "选择 light_ball_at_frame_8 案例；同一次求解里第 1–7 帧用 source 参数，到第 8 帧（t = 7/24 s，钢球仍在轨道上）把钢球质量改为 67.35 g（同外径、同心空心），钢球保持位置和速度，此后的滚动加速度和转动惯量随之改变，继续求解到 4 s；第 1–7 帧与同一主机上的 source 求解逐位相同。",
            "en": "Select native case light_ball_at_frame_8; one solve runs the source parameters for frames 1-7 and at frame 8 (t = 7/24 s, the ball still on the track) sets the ball's mass to 67.35 g (same outer diameter, concentric hollow core); the ball keeps its position and velocity, its rolling acceleration and inertia change from there on, and the solve continues to 4 s. Frames 1-7 are bit-identical to the source solve on the same host."
        },
        "definition_source": "scripts/rigid_elastic/silicone_block_chain/edit_vocab.py"
    },
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/silicone_block_chain/build_pcve_silicone_block_chain.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "verify"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/silicone_block_chain/build_pcve_silicone_block_chain.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/silicone_block_chain/build_pcve_silicone_block_chain.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/silicone_block_chain/build_pcve_silicone_block_chain.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/silicone_block_chain/build_pcve_silicone_block_chain.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/silicone_block_chain/simulate_silicone_block_chain.py",
    "render_entry": "scripts/rigid_elastic/silicone_block_chain/render_silicone_block_chain.py",
    "ground_truth_tool": "scripts/rigid_elastic/silicone_block_chain/tools/export_ground_truth.py",
    "current_suite": "renders/pcve_suites/pcve_silicone_block_chain_suite",
    "notes": [
        "native_cli_case_id selects the scenario; catalog_case_id names the published edit_* video directory.",
        "verify checks the pinned native delivery, the accepted caches, the re-solves kept with the suite (source and the timed edit) and the published suite.",
        "Run verify with a Python that has numpy (for example .venv-rigid-elastic/bin/python): it reads the caches."
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
import hashlib
import json

from pcve_edit_policy import audit_suite_manifest
from pcve_media_contract import require_times, require_video
from edit_vocab import CASE_DSL, TIMED_DSL, VOCAB
from scene_paths import (DELIVERY, INPUTS, SCENE, SUITE_NAME, SUITE_SOLVES, cache, catalog_id, media, output_path,
                         packed, published_native)

STRIDE, FRAMES = 4, 96                 # video frame f = native sample 4 (f - 1) of the 96 Hz cache
TOL_M = 2e-6                           # rigid poses of the packed scenes are float32 keyframes
SOLVE_KEYS = ("states", "ball_spin_rad", "rigid_velocity", "elastic_positions")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


ACCEPTED_PREFIX = f"renders/{SCENE}/accepted/"
INPUTS_PREFIX = f"assets/scenes/{SCENE}/"


def pinned_location(row):
    """Where a file pinned by the accepted delivery manifest lives: the accepted delivery (renders/<scene>/accepted/...)
    or the reproduction inputs (assets/scenes/<scene>/<inputs folder>/{physics,packed}/...)."""
    path = row["path"]
    if path.startswith(INPUTS_PREFIX):
        return INPUTS / path[len(INPUTS_PREFIX):].split("/", 1)[1]   # native caches and packed scenes
    if path.startswith(ACCEPTED_PREFIX):
        return DELIVERY / path[len(ACCEPTED_PREFIX):]
    raise ValueError("Pinned path outside the delivery and the reproduction inputs: " + path)


def verify_delivery():
    """Every file pinned by the accepted delivery manifest still has its bytes; the delivery passes the edit policy."""
    pinned = json.loads((DELIVERY / "delivery_manifest.json").read_text())
    kinds = {}
    for row in pinned["files"]:
        location = pinned_location(row)
        if "sha256" not in row:
            kind = "unhashed_records_and_code"
        else:
            if sha256(location) != row["sha256"]:
                raise ValueError("Delivered file changed: " + row["path"] + " -> " + str(location))
            kind = ("packed_scenes" if location.suffix == ".blend" else "native_caches" if location.is_relative_to(INPUTS / "physics")
                    else "delivery_movies" if location.suffix == ".mp4" else "delivery_files")
        kinds[kind] = kinds.get(kind, 0) + 1
    native = json.loads((DELIVERY / "pcve_silicone_block_chain_suite/suite_manifest.json").read_text())
    if not audit_suite_manifest(native, VOCAB, DELIVERY / "pcve_silicone_block_chain_suite")["all_edits_compliant"]:
        raise ValueError("Edit policy audit failed")
    return {"pinned_files": len(pinned["files"]), "pinned_files_by_kind": kinds}


def load(path):
    import numpy as np
    with np.load(path) as data:
        return {k: data[k] for k in data.files}


def verify_solve(case, folder):
    """A solve folder holds this case's cache and solver report, with the parameters of physics/config.py."""
    sys.path.insert(0, str(CASE / "physics"))
    from config import parameters, timed_schedule
    config = json.loads((folder / "config.json").read_text())
    if config["case"] != case or config["cache_sha256"] != sha256(folder / "simulation.npz") or config["physics"] != parameters(case):
        raise ValueError(f"{case}: native cache or its parameters changed ({folder})")
    if case in TIMED_DSL:
        frame, change = timed_schedule(case)
        timed = config.get("timed_edit") or {}
        if (timed.get("frame"), timed.get("change")) != (frame, change):
            raise ValueError(f"{case}: the solve does not apply the timed edit of physics/config.py")
    data = load(folder / "simulation.npz")
    require_times(data["times"][::STRIDE][:FRAMES])
    return config, data


def verify_caches(cases):
    """Accepted caches (the four whole-clip edits and the accepted source) and the re-solves kept with the suite."""
    result = {}
    for case in cases:
        if case in CASE_DSL:
            verify_solve(case, cache(case).parent)
            result[case] = ["accepted cache"]
    solves = {case: verify_solve(case, published_native(case)) for case in SUITE_SOLVES if case in cases}
    for case, (config, data) in solves.items():
        if case in TIMED_DSL:
            # Samples up to the edit step are those of the source re-solve of the same run, bit for bit.
            source = solves["source"] if "source" in solves else verify_solve("source", published_native("source"))
            edge = STRIDE * (config["timed_edit"]["frame"] - 1) + 1
            prefix = {k: float(abs(data[k][:edge] - source[1][k][:edge]).max()) for k in SOLVE_KEYS}
            if any(prefix.values()):
                raise ValueError(f"{case}: samples before the edit differ from the source re-solve: {prefix}")
        result.setdefault(case, []).append(f"re-solve in cases/{catalog_id(case)}/native_metadata")
    return result


def verify_suite(cases):
    """Published videos, prompts and ground truth against the builder catalog and the solves the videos replay."""
    import numpy as np
    from pcve_edit_catalog import FORMAT_VERSION, load_catalog
    root = media()
    catalog = load_catalog(Path(__file__))
    declared = {"source": catalog["source"], **catalog["edits"]}
    published = json.loads((root / "suite_manifest.json").read_text())
    records = {r["native_case_id"]: r for r in [published["source"], *published["edits"]]}
    pinned = json.loads((CASE / "scene_manifest.json").read_text())["canonical_suites"][SUITE_NAME]["case_video_sha256"]
    result = []
    for case in cases:
        folder = root / "cases" / catalog_id(case)
        video = folder / "video.mp4"
        digest = sha256(video)
        if digest != records[case]["video_sha256"] or digest != pinned[case]:
            raise ValueError("Published video differs from suite_manifest.json or scene_manifest.json: " + str(video))
        prompts = json.loads((folder / "prompts.json").read_text())
        if (prompts.get("format_version") != FORMAT_VERSION or prompts["prompts"] != declared[case]["prompts"]
                or prompts.get("edit_dsl") != declared[case].get("edit_dsl")):
            raise ValueError("prompts.json differs from the declared catalog: " + case)
        solve = published_native(case)
        cache_sha = sha256(solve / "simulation.npz")
        render = json.loads((folder / "native_metadata/realism_provenance.json").read_text())
        rendered = (render.get("native_cache_sha256") == cache_sha if case in SUITE_SOLVES
                    else render["saved_scene_sha256"] == sha256(packed(case)))
        if not rendered or render["video"]["sha256"] != digest or render["frames"] != [1, FRAMES, FRAMES]:
            raise ValueError(f"{case}: the render record does not replay {solve} into this video")
        gt = json.loads((folder / "ground_truth_transforms.json").read_text())
        frames = gt["frames"]
        if (gt.get("format_version") != "pcve_ground_truth/1" or gt["fps"] != 24 or len(frames) != FRAMES
                or [f["frame_index"] for f in frames] != list(range(1, FRAMES + 1))
                or cache_sha not in gt["source"]["sha256"].values()):
            raise ValueError("Ground truth is not pcve_ground_truth/1 of the replayed solve: " + case)
        require_times([f["time_sec"] for f in frames])
        data = load(solve / "simulation.npz")
        states = data["states"][::STRIDE][:FRAMES]
        ball = np.array([f["steel_ball"]["location"] for f in frames])
        platen = np.array([f["guided_platen"]["location"][2] for f in frames])
        error = max(float(abs(ball[:, 0] - states[:, 1]).max()), float(abs(ball[:, 2] - states[:, 2]).max()),
                    float(abs(platen - states[:, 0]).max()))
        foam = data["elastic_positions"].size > 0
        if foam:
            surface = np.unique(data["elastic_faces"].ravel())
            centroid = data["elastic_positions"][::STRIDE][:FRAMES][:, surface].mean(axis=1)
            error = max(error, float(abs(np.array([f["foam_block"]["location"] for f in frames]) - centroid).max()))
        if error > TOL_M or any(f["foam_block"]["present"] != foam for f in frames):
            raise ValueError(f"{case}: ground truth differs from the native cache ({error:.3g} m)")
        result.append({"case_id": case, "video": str(video), "ground_truth_vs_cache_m": error, "media": require_video(video)})
    return {"suite": str(root), "verified_cases": result}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", choices=("verify",), default="verify")
    p.add_argument("--cases", nargs="+", choices=[*CASE_DSL, *TIMED_DSL], default=[*CASE_DSL, *TIMED_DSL])
    p.add_argument("--out", type=Path, help="also write the report to OUT/verify_report.json")
    a = p.parse_args()
    out = output_path(a.out) if a.out else None
    result = {"scene": SCENE, "delivery": verify_delivery(), "native_caches": verify_caches(a.cases), **verify_suite(a.cases)}
    print(json.dumps(result, ensure_ascii=False))
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "verify_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
