"""Verify the published suite against the edit catalog and the native caches, or dispatch a reconstruction stage."""

# PCVE_EDIT_CATALOG_BEGIN
# Source description, four whole-clip edits and one timed edit of the published suite.
# Values in physics_override use the recorded shared-DSL/native-plan schema;
# scene-native adapters retain all required solver-field and presence conversions.
PCVE_SCENE = "spring_scale_weight_drop"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "一个铜色砝码落进弹簧秤的秤盘，秤盘连同横杆沿导杆下移，拉长钢制弹簧。",
            "en": "A brass weight drops into the pan of a spring balance; the pan and its crossbar slide down the guide rods and stretch the steel spring."
        },
        "quantitative": {
            "zh": "一个铜色砝码落进弹簧秤的秤盘，秤盘连同横杆沿导杆下移，拉长钢制弹簧。100 g 的砝码从秤盘上方 85 mm 处由静止落下；弹簧是一根 28 圈的钢丝拉簧，线径 1.1 mm，中径 35 mm；横杆连同秤盘的质量为 65 g。",
            "en": "A brass weight drops into the pan of a spring balance; the pan and its crossbar slide down the guide rods and stretch the steel spring. The 100 g weight starts at rest 85 mm above the pan; the spring is a 28-turn steel extension spring with 1.1 mm wire and a 35 mm mean coil diameter, and the crossbar with its pan has a mass of 65 g."
        }
    },
    "description_basis": "Current scene code and retained source-video inspection; numbers from physics/scene.py BASELINE (weight 0.100 kg released 0.085 m above the pad, 28 active turns, wire 1.1 mm, mean diameter 35 mm, carriage 0.065 kg); physical outcomes beyond the visible interaction are not asserted."
}

PCVE_EDITS = {
    "damped": {
        "case_id": "damped",
        "catalog_case_id": "edit_damped",
        "native_cli_case_id": "damped",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET guide.damping TIMES 4",
        "applies_from_frame": 1,
        "physics_override": {
            "guide_damping_ns_m": 1.2
        },
        "physics_diff": {
            "guide_damping_ns_m": {
                "from": 0.3,
                "to": 1.2
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把秤盘的导杆的黏性阻尼系数调大一些。",
                "en": "From the start of the clip, increase the pan's guide rods' viscous damping coefficient."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把秤盘的导杆的黏性阻尼系数增加到原来的 4 倍。",
                "en": "From frame 1 onwards, increase the pan's guide rods' viscous damping coefficient to 4 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 damped 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case damped; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/spring_scale_weight_drop/edit_vocab.py"
    },
    "heavy": {
        "case_id": "heavy",
        "catalog_case_id": "edit_heavy",
        "native_cli_case_id": "heavy",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET weight.mass TIMES 2",
        "applies_from_frame": 1,
        "physics_override": {
            "weight_mass_kg": 0.2
        },
        "physics_diff": {
            "weight_mass_kg": {
                "from": 0.1,
                "to": 0.2
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把下落砝码的质量调大一些。",
                "en": "From the start of the clip, increase the falling calibration weight's mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把下落砝码的质量增加到原来的 2 倍。",
                "en": "From frame 1 onwards, increase the falling calibration weight's mass to 2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 heavy 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case heavy; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/spring_scale_weight_drop/edit_vocab.py"
    },
    "remove_weight": {
        "case_id": "remove_weight",
        "catalog_case_id": "edit_remove_weight",
        "native_cli_case_id": "remove_weight",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE weight",
        "applies_from_frame": 1,
        "physics_override": {
            "weight_present": [
                0
            ]
        },
        "physics_diff": {
            "weight_present": {
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
                "zh": "从视频一开始,把下落砝码从场景中删除。",
                "en": "From the start of the clip, remove the falling calibration weight from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把下落砝码从场景中删除。",
                "en": "From frame 1 onwards, remove the falling calibration weight from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 remove_weight 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case remove_weight; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/spring_scale_weight_drop/edit_vocab.py"
    },
    "soft": {
        "case_id": "soft",
        "catalog_case_id": "edit_soft",
        "native_cli_case_id": "soft",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET spring.young_modulus TIMES 0.5",
        "applies_from_frame": 1,
        "physics_override": {
            "spring_young_modulus_pa": 100000000000.0
        },
        "physics_diff": {
            "spring_young_modulus_pa": {
                "from": 200000000000.0,
                "to": 100000000000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把弹簧秤的钢制弹簧的杨氏模量调小一些。",
                "en": "From the start of the clip, decrease the steel spring in the spring balance's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把弹簧秤的钢制弹簧的杨氏模量减少到原来的 0.5 倍。",
                "en": "From frame 1 onwards, reduce the steel spring in the spring balance's Young's modulus to 0.5 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 soft 案例；按 edit_dsl 和 physics_override 修改指定物理属性或物体存在性，由原场景适配器执行原生字段转换及必要的增删物体准备，再求解并渲染。",
            "en": "Select native case soft; apply edit_dsl and physics_override to the declared physical properties or object presence. Retain scene-native field conversions and required object setup, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/spring_scale_weight_drop/edit_vocab.py"
    },
    "heavy_at_frame_48": {
        "case_id": "heavy_at_frame_48",
        "catalog_case_id": "edit_heavy_at_frame_48",
        "native_cli_case_id": "heavy_at_frame_48",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET weight.mass TIMES 2 AT FRAME 48",
        "applies_from_frame": 48,
        "physics_override": {
            "weight_mass_kg": 0.2
        },
        "physics_diff": {
            "weight_mass_kg": {
                "from": 0.1,
                "to": 0.2
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "在视频进行到一半左右时,把下落砝码的质量调大一些。",
                "en": "About halfway through the clip, increase the falling calibration weight's mass."
            },
            "quantitative": {
                "zh": "从第 48 帧开始,把下落砝码的质量增加到原来的 2 倍。",
                "en": "From frame 48 onwards, increase the falling calibration weight's mass to 2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 heavy_at_frame_48 案例；第 1–47 帧就是 source 的原生缓存，第 48 帧（t = 47/24 s）从 source 缓存恢复完整状态，把砝码质量改为 0.2 kg 后用同一积分器续算到 4 s（simulate --case heavy_at_frame_48 --source-cache <source native_dynamics.npz>），再逐帧渲染全部 96 帧。",
            "en": "Select native case heavy_at_frame_48; frames 1-47 are the source's native cache. At frame 48 (t = 47/24 s) the complete source state is restored from that cache, the weight's mass becomes 0.2 kg and the same integrator continues to 4 s (simulate --case heavy_at_frame_48 --source-cache <source native_dynamics.npz>); all 96 frames are then rendered."
        },
        "definition_source": "scripts/rigid_elastic/spring_scale_weight_drop/edit_vocab.py"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/spring_scale_weight_drop/build_pcve_spring_scale_weight_drop.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "all",
        "prepare",
        "simulate",
        "render",
        "verify"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/spring_scale_weight_drop/build_pcve_spring_scale_weight_drop.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/spring_scale_weight_drop/build_pcve_spring_scale_weight_drop.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/spring_scale_weight_drop/build_pcve_spring_scale_weight_drop.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/spring_scale_weight_drop/build_pcve_spring_scale_weight_drop.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/spring_scale_weight_drop/simulate_spring_scale_weight_drop.py",
    "render_entry": "scripts/rigid_elastic/spring_scale_weight_drop/render_spring_scale_weight_drop.py",
    "current_suite": "renders/pcve_suites/pcve_spring_scale_weight_drop_suite",
    "notes": [
        "native_cli_case_id selects the native case; catalog_case_id names the published edit_* video directory.",
        "--stage verify checks the published suite (videos, prompts, ground truth) against this catalog, scene_manifest.json and the native caches.",
        "--stage simulate and --stage render run the simulate/render entries per case into a new --out-root; the timed edit continues from the accepted source cache."
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
SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "build_pcve")
# PCVE_UNIFIED_ENTRY_END

import argparse
import hashlib
import json
import subprocess

from physics.scene import DELIVERY
from scene_paths import REPO, SCENE, SUITE_NAME, suite

CASE_DIR = Path(__file__).resolve().parent


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def native_folder(case, input_root):
    """Native cache of a case: <input root>/cases/<case>/, or the suite case's native_metadata/ for a timed edit."""
    from edit_vocab import TIMED_DSL
    if case in TIMED_DSL:
        return suite() / "cases" / f"edit_{case}" / "native_metadata"
    return input_root / "cases" / case


def verify(cases, input_root):
    """Published suite against this catalog, scene_manifest.json, edit_vocab and the native caches."""
    import numpy as np
    from edit_vocab import parameters
    from pcve_edit_catalog import _applies_from_frame, load_catalog
    from pcve_media_contract import require_times, require_video
    from tools.export_ground_truth import FORMAT, build

    root = suite()
    catalog = load_catalog(Path(__file__))
    records = {"source": catalog["source"], **catalog["edits"]}
    pinned = json.loads((CASE_DIR / "scene_manifest.json").read_text(encoding="utf-8"))["canonical_suites"][SUITE_NAME]
    rows = {}
    for name in cases:
        record = records[name]
        folder = root / "cases" / record["catalog_case_id"]
        video = folder / "video.mp4"
        digest = sha256(video)
        if digest != pinned["case_video_sha256"][name]:
            raise ValueError(f"{name}: suite video differs from scene_manifest.json")
        media = require_video(video)
        prompts = json.loads((folder / "prompts.json").read_text(encoding="utf-8"))
        expected = {"format_version": "pcve_prompts/1", "prompts": record["prompts"], "edit_dsl": record.get("edit_dsl")}
        if record["kind"] == "edit":
            expected.update(applies_from_frame=_applies_from_frame(record), physics_override=record["physics_override"],
                            physics_diff=record["physics_diff"])
        if any(prompts.get(key) != value for key, value in expected.items()):
            raise ValueError(f"{name}: prompts.json differs from the builder catalog")
        # Native cache: the one the published video was rendered from, solved with the edit_vocab parameters
        # (parameters() also runs the shared edit-policy audit of the edit).
        native = native_folder(name, input_root)
        receipt = json.loads((folder / "native_metadata/encoding_receipt.json").read_text(encoding="utf-8"))
        cache_digest = sha256(native / "native_dynamics.npz")
        if receipt["video_sha256"] != digest or receipt["native_cache_sha256"] != cache_digest:
            raise ValueError(f"{name}: the video was not rendered from {native}/native_dynamics.npz")
        with np.load(native / "native_dynamics.npz", allow_pickle=False) as data:
            require_times(data["frame_times_s"][:96].tolist())
        physics = json.loads((native / "physics.json").read_text(encoding="utf-8"))
        declared = json.loads(json.dumps(parameters(name)))
        schedule = declared.pop("timed_edits", None)
        if physics["physics"] != declared or physics.get("timed_edits") != schedule:
            raise ValueError(f"{name}: native physics differs from edit_vocab")
        gt = json.loads((folder / "ground_truth_transforms.json").read_text(encoding="utf-8"))
        if gt.get("format_version") != FORMAT or len(gt["frames"]) != 96:
            raise ValueError(f"{name}: ground truth is not {FORMAT} with 96 frames")
        require_times([frame["time_sec"] for frame in gt["frames"]])
        fresh = json.loads(json.dumps(build(name, input_root)))
        if {k: v for k, v in gt.items() if k != "source"} != {k: v for k, v in fresh.items() if k != "source"}:
            raise ValueError(f"{name}: ground truth differs from a fresh export of the native cache")
        rows[name] = {"suite_case": record["catalog_case_id"], "video_sha256": digest, "native_cache_sha256": cache_digest,
                      "media": media}
    return {"suite": str(root), "native_input_root": str(input_root), "verified_cases": rows, "strict_edits": True}


def main():
    from edit_vocab import CASE_DSL, TIMED_DSL

    every = [*CASE_DSL, *TIMED_DSL]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("all", "prepare", "simulate", "render", "verify"), default="verify")
    parser.add_argument("--cases", nargs="+", choices=every, default=every)
    parser.add_argument("--output-dir", type=Path,
                        help="simulate/render: new output root outside scripts/, the assets and the suite")
    parser.add_argument("--input-root", type=Path, default=DELIVERY,
                        help="native caches <root>/cases/<case>/ for verify and render (default: the accepted delivery)")
    parser.add_argument("--look", choices=("base", "realism"), help="render: look passed to the render entry (default realism, the published look)")
    parser.add_argument("--blender-bin", type=Path)
    parser.add_argument("--gpu-uuid")
    parser.add_argument("--render-threads", type=int)
    parser.add_argument("--wait-idle", action="store_true")
    args = parser.parse_args()
    cases = list(dict.fromkeys(args.cases))
    if args.stage in ("all", "prepare"):
        subprocess.run([sys.executable, "-B", str(SCRIPTS / "download_assets.py"),
                        "--scene", SCENE, "--check"], check=True)
    if args.stage in ("all", "verify"):
        print(json.dumps(verify(cases, args.input_root.resolve()), indent=2))
    if args.stage in ("simulate", "render"):
        if args.output_dir is None:
            parser.error("Specify a new --out-root, for example renders/spring_scale_weight_drop/rebuild/<name>")
        for name in cases:
            output = args.output_dir if args.stage == "simulate" else args.output_dir / "cases" / name
            command = [sys.executable, "-B", str(CASE_DIR / f"{args.stage}_spring_scale_weight_drop.py"),
                       "--case", name, "--out-root", str(output)]
            if args.stage == "render":
                command += ["--input-root", str(args.input_root)]
                if args.look:
                    command += ["--look", args.look]
                for flag, value in (("--blender", args.blender_bin), ("--gpu", args.gpu_uuid),
                                    ("--threads", args.render_threads)):
                    if value is not None:
                        command += [flag, str(value)]
                if args.wait_idle:
                    command.append("--wait-idle")
            subprocess.run(command, check=True, cwd=REPO)


if __name__ == "__main__":
    main()
