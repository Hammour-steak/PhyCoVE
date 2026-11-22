"""Check inputs, rebuild the cases, or verify the accepted delivery and the published suite.

Stages: prepare (registered inputs), simulate, render, all, verify (default).
--stage verify checks the accepted physics delivery (renders/metro_security_bag_curtain/accepted and the
native states in assets/scenes/metro_security_bag_curtain/native) for the whole-clip cases and the
published suite named by scene_manifest.json (videos, prompts, ground truth, native states; the timed
edit's merged states are in the suite's inputs/native_timed/). With --out-root it checks a fresh rebuild.
"""

# PCVE_EDIT_CATALOG_BEGIN
# Source description and the five edits of the published suite (four whole-clip edits and one timed
# DELETE). physics_override uses the shared-DSL field names of edit_vocab.py; the scene adapter applies
# them before the native solve.
PCVE_SCENE = "metro_security_bag_curtain"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "地铁站安检口，X 光安检机的输送带把一只灰色双肩背包从机器出口送出，背包顶开出口铅帘，越过输送带末端，滑下不锈钢滑板，停在取物台上。",
            "en": "At a metro station security checkpoint, the X-ray scanner's conveyor belt carries a grey backpack out of the machine; the backpack pushes through the exit lead curtain, runs off the end of the belt, slides down a stainless-steel chute and stops on the pickup tray."
        },
        "quantitative": {
            "zh": "地铁站安检口，X 光安检机的输送带以 0.4 m/s 运行，带面离地 75 cm，出口外还有 70 cm 带面。一只 44×33×21 cm、4 kg 的灰色双肩背包开始时中心在出口铅帘后方 30 cm，速度为 0.2 m/s，背包与输送带之间的摩擦系数为 0.5。出口铅帘由 6 条长 29.5 cm、厚 2.4 mm 的橡胶帘条组成，总宽 51 cm，杨氏模量 3 MPa。背包顶开铅帘，越过带端，滑下水平长 55 cm、落差 18 cm 的不锈钢滑板，停在 65 cm 长的取物台上。",
            "en": "At a metro station security checkpoint, the X-ray scanner's conveyor belt runs at 0.4 m/s with its surface 75 cm above the floor and 70 cm of belt beyond the exit. A 44×33×21 cm, 4 kg grey backpack starts with its centre 30 cm behind the exit lead curtain, moving at 0.2 m/s; the friction coefficient between the backpack and the belt is 0.5. The curtain is six rubber strips 29.5 cm long and 2.4 mm thick, 51 cm wide in total, with a Young's modulus of 3 MPa. The backpack pushes through the curtain, runs off the end of the belt, slides down a stainless-steel chute 55 cm long with an 18 cm drop and stops on a 65 cm pickup tray."
        }
    },
    "editable_objects": [
        {"object_id": "bag", "zh": "背包", "en": "the backpack", "in_video": True,
         "properties": ["friction"], "can_delete": False, "can_add": False},
        {"object_id": "conveyor", "zh": "输送带", "en": "the conveyor belt", "in_video": True,
         "properties": ["velocity"], "can_delete": False, "can_add": False},
        {"object_id": "exit_curtain", "zh": "出口铅帘", "en": "the exit lead curtain", "in_video": True,
         "properties": ["young_modulus"], "can_delete": True, "can_add": False}
    ],
    "description_basis": "Values from edit_vocab.BASELINE and the accepted native source states (bag centre x=-0.30 m, curtain plane x=0, belt end x=0.70 m)."
}

PCVE_EDITS = {
    "belt_speed_x2": {
        "case_id": "belt_speed_x2",
        "catalog_case_id": "edit_belt_speed_x2",
        "native_cli_case_id": "belt_speed_x2",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET conveyor.velocity TIMES 2",
        "applies_from_frame": 1,
        "physics_override": {
            "belt_speed_m_s": 0.8
        },
        "physics_diff": {
            "belt_speed_m_s": {
                "from": 0.4,
                "to": 0.8
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把输送带的速度调大一些。",
                "en": "From the start of the clip, increase the conveyor belt's speed."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把输送带的速度增加到原来的 2 倍。",
                "en": "From frame 1 onwards, increase the conveyor belt's speed to 2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 belt_speed_x2 案例；按 physics_override 把带速设为 0.8 m/s，再求解并渲染。",
            "en": "Select native case belt_speed_x2; set the belt speed to 0.8 m/s from physics_override, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/metro_security_bag_curtain/edit_vocab.py"
    },
    "delete_curtain": {
        "case_id": "delete_curtain",
        "catalog_case_id": "edit_delete_curtain",
        "native_cli_case_id": "delete_curtain",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE exit_curtain",
        "applies_from_frame": 1,
        "physics_override": {
            "curtain_present": [
                0
            ]
        },
        "physics_diff": {
            "curtain_present": {
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
                "zh": "从视频一开始,把出口铅帘从场景中删除。",
                "en": "From the start of the clip, remove the exit lead curtain from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把出口铅帘从场景中删除。",
                "en": "From frame 1 onwards, remove the exit lead curtain from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 delete_curtain 案例；出口铅帘不参与求解也不渲染，其余不变。",
            "en": "Select native case delete_curtain; the exit curtain is neither solved nor rendered, everything else is unchanged."
        },
        "definition_source": "scripts/rigid_elastic/metro_security_bag_curtain/edit_vocab.py"
    },
    "friction_x0p02": {
        "case_id": "friction_x0p02",
        "catalog_case_id": "edit_friction_x0p02",
        "native_cli_case_id": "friction_x0p02",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET bag.friction TIMES 0.02",
        "applies_from_frame": 1,
        "physics_override": {
            "belt_bag_friction": 0.01
        },
        "physics_diff": {
            "belt_bag_friction": {
                "from": 0.5,
                "to": 0.01
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把背包的摩擦系数调小一些。",
                "en": "From the start of the clip, decrease the backpack's friction coefficient."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把背包的摩擦系数减少到原来的 0.02 倍。",
                "en": "From frame 1 onwards, reduce the backpack's friction coefficient to 0.02 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 friction_x0p02 案例；按 physics_override 把背包与输送带之间的摩擦系数设为 0.01，再求解并渲染。",
            "en": "Select native case friction_x0p02; set the belt-backpack friction coefficient to 0.01 from physics_override, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/metro_security_bag_curtain/edit_vocab.py"
    },
    "young_modulus_x100": {
        "case_id": "young_modulus_x100",
        "catalog_case_id": "edit_young_modulus_x100",
        "native_cli_case_id": "young_modulus_x100",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET exit_curtain.young_modulus TIMES 100",
        "applies_from_frame": 1,
        "physics_override": {
            "curtain_young_modulus_pa": 300000000.0
        },
        "physics_diff": {
            "curtain_young_modulus_pa": {
                "from": 3000000.0,
                "to": 300000000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把出口铅帘的杨氏模量调大一些。",
                "en": "From the start of the clip, increase the exit lead curtain's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把出口铅帘的杨氏模量增加到原来的 100 倍。",
                "en": "From frame 1 onwards, increase the exit lead curtain's Young's modulus to 100 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 young_modulus_x100 案例；按 physics_override 把帘条杨氏模量设为 300 MPa，再求解并渲染。",
            "en": "Select native case young_modulus_x100; set the strip Young's modulus to 300 MPa from physics_override, then solve and render."
        },
        "definition_source": "scripts/rigid_elastic/metro_security_bag_curtain/edit_vocab.py"
    },
    "delete_curtain_at_frame_12": {
        "case_id": "delete_curtain_at_frame_12",
        "catalog_case_id": "edit_delete_curtain_at_frame_12",
        "native_cli_case_id": "delete_curtain_at_frame_12",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE exit_curtain AT FRAME 12",
        "applies_from_frame": 12,
        "physics_override": {
            "curtain_present": [0]
        },
        "physics_diff": {
            "curtain_present": {
                "from": [1],
                "to": [0]
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "在视频前段,把出口铅帘从场景中删除。",
                "en": "Early in the clip, remove the exit lead curtain from the scene."
            },
            "quantitative": {
                "zh": "从第 12 帧开始,把出口铅帘从场景中删除。",
                "en": "From frame 12 onwards, remove the exit lead curtain from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 delete_curtain_at_frame_12 案例；第 1–11 帧就是源视频的原生状态，求解器从源缓存恢复第 12 帧（t=11/24 s）的完整状态，从这一帧起出口铅帘不再参与求解也不再渲染，背包从该状态继续求解。",
            "en": "Select native case delete_curtain_at_frame_12; frames 1-11 are the source's native states. The solver restores the exact source state of frame 12 (t=11/24 s) from the source cache; from that frame on the exit curtain is neither solved nor rendered and the backpack keeps being solved from that state."
        },
        "definition_source": "scripts/rigid_elastic/metro_security_bag_curtain/edit_vocab.py"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/metro_security_bag_curtain/build_pcve_metro_security_bag_curtain.py",
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
        "scripts/rigid_elastic/metro_security_bag_curtain/build_pcve_metro_security_bag_curtain.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/metro_security_bag_curtain/build_pcve_metro_security_bag_curtain.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/metro_security_bag_curtain/build_pcve_metro_security_bag_curtain.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/metro_security_bag_curtain/build_pcve_metro_security_bag_curtain.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/metro_security_bag_curtain/simulate_metro_security_bag_curtain.py",
    "render_entry": "scripts/rigid_elastic/metro_security_bag_curtain/render_metro_security_bag_curtain.py",
    "current_suite": "renders/pcve_suites/pcve_metro_security_bag_curtain_suite",
    "notes": [
        "native_cli_case_id selects the scene case; catalog_case_id names the published edit_* directory.",
        "--export-prompts writes these prompts to the suite (pcve_prompts/1); tools/export_ground_truth.py writes the ground truth; tools/publish_suite.py assembles a new suite from render outputs.",
        "delete_curtain_at_frame_12 is a native timed edit: the simulate entry restores the source state of frame 12 and keeps solving (edit_vocab.TIMED_DSL).",
        "--stage verify does not solve; use the simulate/render entries or --stage all for a reproduction."
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

SCRIPTS = Path(__file__).resolve().parents[2]
# PCVE_UNIFIED_ENTRY_BEGIN
sys.path.insert(0, str(SCRIPTS))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, 'build_pcve')
# PCVE_UNIFIED_ENTRY_END

import argparse
import hashlib
import json
import os
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scene_paths import (ASSETS, CASE, DELIVERY, NATIVE, REPO, SCENE_MANIFEST,
                         default_rebuild_root, ensure_numpy_runtime, output_path)

CASES = ("source", "young_modulus_x100", "belt_speed_x2", "friction_x0p02", "delete_curtain")
# Timed edits continue the solver from the accepted source states (edit_vocab.TIMED_DSL); their merged
# native states are published with the suite in inputs/native_timed/<case>/.
TIMED_CASES = ("delete_curtain_at_frame_12",)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            result.update(block)
    return result.hexdigest()


def prepare():
    registry = read(REPO / "assets.json")["assets"]
    prefix = "scenes/metro_security_bag_curtain/"
    count = 0
    for key, group in registry.items():
        if not key.startswith(prefix):
            continue
        for name, record in group["files"].items():
            path = ASSETS / key.removeprefix(prefix) / name
            if not path.is_file() or path.stat().st_size != record["bytes"] or sha(path) != record["sha256"]:
                raise RuntimeError(f"Missing or changed registered input {path}")
            count += 1
    if not count:
        raise RuntimeError("The scene's assets.json groups are required")
    print(json.dumps({"assets_checked": count}))
    return count


def without_code_hash(config):
    """A simulation config without the solver source hash some stored copies still carry."""
    solver = config.get("solver")
    if not isinstance(solver, dict):
        return config
    return {**config, "solver": {k: v for k, v in solver.items() if k != "solver_combined_sha256"}}


def check_native(case, native_root):
    """The native states belong to this case: parameters, DSL (timed schedule) and the 24 Hz clock."""
    import numpy as np
    from edit_vocab import CASE_DSL, TIMED_DSL, parameters, timed_schedule
    from pcve_media_contract import require_times
    config = read(native_root / case / "simulation_config.json")
    if case in TIMED_DSL:
        want = (parameters("source"), TIMED_DSL[case], timed_schedule(case))
    else:
        want = (parameters(case), CASE_DSL[case], None)
    if (config["physics"], config["edit_dsl"], config.get("timed_edits")) != want:
        raise RuntimeError(f"Native parameters differ from edit_vocab for {case}")
    with np.load(native_root / case / "states.npz", allow_pickle=False) as states:
        if len(states["times"]) != 97 or states["times"][-1] != 4:
            raise RuntimeError(f"Native endpoints differ for {case}")
        require_times(states["times"][:96])
    return config, sha(native_root / case / "states.npz")


def verify_delivery(cases):
    """Accepted physics delivery: receipts tie every whole-clip video to the native states in assets.

    The delivery also holds an ADD case outside the published suite (add_second_bag); only the cases of edit_vocab.CASE_DSL are checked."""
    from edit_vocab import PUBLIC_DSL, VOCAB
    from pcve_edit_policy import audit_suite_manifest
    from pcve_media_contract import require_times, require_video
    manifest = read(DELIVERY / "suite_manifest.json")
    current = {case: edit for case, edit in PUBLIC_DSL.items() if edit}
    actual = {edit["case_id"]: edit["edit_dsl"] for edit in manifest["edits"] if edit["case_id"] in current}
    if actual != current:
        raise RuntimeError("The delivered edit definitions differ from edit_vocab")
    manifest = {**manifest, "edits": [edit for edit in manifest["edits"] if edit["case_id"] in current]}
    if not audit_suite_manifest(manifest, VOCAB, suite_root=DELIVERY)["all_edits_compliant"]:
        raise RuntimeError("Strict edit preflight failed")
    videos = {item["case_id"]: item for item in manifest["videos"]}
    rows = []
    for case in [c for c in cases if c not in TIMED_CASES]:
        delivery = DELIVERY / "cases" / case
        config, cache_hash = check_native(case, NATIVE)
        if without_code_hash(config) != without_code_hash(read(delivery / "simulation_config.json")):
            raise RuntimeError(f"Delivery parameters differ for {case}")
        video = delivery / "video.mp4"
        encoding = read(delivery / "encoding_receipt.json")
        render = read(delivery / "render_report.json")
        video_hash = sha(video)
        if (encoding["input_state_sha256"] != cache_hash or render["simulation_cache_sha256"] != cache_hash
                or encoding["video_sha256"] != video_hash or videos[case]["sha256"] != video_hash):
            raise RuntimeError(f"Cache and render receipts differ for {case}")
        require_times(read(delivery / "ground_truth.json")["times_s"])
        replay = read(delivery / "replay_audit.json")
        if not replay["passed"] or replay["frames_checked"] != 96:
            raise RuntimeError(f"Native scene replay differs for {case}")
        if render["frames"] != list(range(96)) or encoding["frames"] != 96 or encoding["fps"] != 24:
            raise RuntimeError(f"Rendered sample times differ for {case}")
        require_video(video)
        rows.append({"case": case, "video": str(video.relative_to(REPO)), "video_sha256": video_hash,
                     "state_sha256": cache_hash})
    return rows


def verify_suite(cases):
    """Published suite named by scene_manifest.json: videos, prompts, ground truth, native link."""
    import numpy as np
    from pcve_edit_catalog import load_catalog
    from pcve_media_contract import require_video
    scene = read(SCENE_MANIFEST)
    name = f"pcve_{scene['scene_id']}_suite"
    pointer = scene["canonical_suites"][name]
    suite = REPO / pointer["target"]
    manifest = read(suite / "suite_manifest.json")
    catalog = load_catalog(Path(__file__))
    declared = {"source": catalog["source"], **catalog["edits"]}
    records = {r["native_case_id"]: r for r in [manifest["source"], *manifest["edits"]]}
    rows = []
    for case in cases:
        record = records[case]
        folder = suite / "cases" / record["case_id"]
        video = suite / record["video"]
        digest = sha(video)
        if not (digest == record["video_sha256"] == pointer["case_video_sha256"][case]):
            raise RuntimeError(f"Suite video hash differs for {case}")
        require_video(video)
        prompts = read(folder / "prompts.json")
        want = declared[case]
        if prompts["prompts"] != want["prompts"] or prompts.get("edit_dsl") != want["edit_dsl"]:
            raise RuntimeError(f"prompts.json differs from the builder catalog for {case}")
        if read(folder / "provenance.json")["video_sha256"] != digest or read(folder / "video_validation.json")["sha256"] != digest:
            raise RuntimeError(f"provenance.json or video_validation.json video hash differs for {case}")
        native = suite / "inputs" / "native_timed" if case in TIMED_CASES else NATIVE
        _, cache_hash = check_native(case, native)
        report = read(folder / "native_metadata" / "render_report.json")
        if report["simulation_cache_sha256"] != cache_hash:
            raise RuntimeError(f"Suite video was not rendered from the accepted native states for {case}")
        truth = read(folder / "ground_truth_transforms.json")
        if (truth["fps"], truth["frame_start"], truth["frame_end"], len(truth["frames"])) != (24, 1, 96, 96):
            raise RuntimeError(f"Ground truth frame range differs for {case}")
        if cache_hash not in truth["source"]["sha256"].values() or truth["camera"]["matrix_world"] != report["camera"]["matrix_world"]:
            raise RuntimeError(f"Ground truth is not tied to this video's states and camera for {case}")
        with np.load(native / case / "states.npz", allow_pickle=False) as states:
            roots = states["bag_positions"]
            for f in (0, 47, 95):
                if not np.allclose(truth["frames"][f]["bag"]["location"], roots[f, 0], atol=1e-12):
                    raise RuntimeError(f"Ground truth bag pose differs from the native states for {case}")
        rows.append({"case": record["case_id"], "video_sha256": digest, "state_sha256": cache_hash,
                     "prompts": "catalog", "ground_truth_frames": len(truth["frames"])})
    return {"suite": str(suite), "cases": rows}


def verify_fresh(root, cases):
    """A rebuild under --out-root: native states and rendered videos tie together."""
    from pcve_media_contract import require_video
    rows = []
    for case in cases:
        _, cache_hash = check_native(case, root / "simulation")
        folder = root / "render" / case
        encoding = read(folder / "encoding_receipt.json")
        render = read(folder / "render_report.json")
        if encoding["input_state_sha256"] != cache_hash or render["simulation_cache_sha256"] != cache_hash:
            raise RuntimeError(f"Fresh render was not made from the fresh states for {case}")
        if sha(folder / "video.mp4") != encoding["video_sha256"]:
            raise RuntimeError(f"Fresh video receipt differs for {case}")
        replay = read(folder / "replay_audit.json")
        if not replay["passed"] or replay["frames_checked"] != 96:
            raise RuntimeError(f"Native scene replay differs for {case}")
        require_video(folder / "video.mp4")
        rows.append({"case": case, "state_sha256": cache_hash, "video_sha256": encoding["video_sha256"]})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", choices=("all", "prepare", "simulate", "render", "verify"), default="verify")
    parser.add_argument("--cases", nargs="+", choices=CASES + TIMED_CASES, default=list(CASES + TIMED_CASES))
    parser.add_argument("--out-root", type=Path)
    parser.add_argument("--blender-bin", type=Path)
    parser.add_argument("--gpu-uuid")
    parser.add_argument("--render-threads", type=int, default=8)
    parser.add_argument("--device", choices=("GPU", "CPU"), default="GPU")
    parser.add_argument("--samples", type=int, default=384)
    args = parser.parse_args()
    ensure_numpy_runtime()
    if args.stage == "verify":
        if args.out_root:
            result = {"fresh_reproduction": verify_fresh(output_path(args.out_root), args.cases)}
        else:
            result = {"accepted_delivery": verify_delivery(args.cases), "published_suite": verify_suite(args.cases)}
        print(json.dumps(result, indent=2))
        return
    if args.stage in {"all", "prepare"}:
        prepare()
    if args.stage == "prepare":
        return
    root = output_path(args.out_root or default_rebuild_root())
    if args.stage in {"all", "simulate"}:
        for case in args.cases:
            # A timed case continues from the source states of this rebuild when they are part of it.
            resume = (["--source-cache", str(root / "simulation" / "source")]
                      if case in TIMED_CASES and "source" in args.cases else [])
            subprocess.run([sys.executable, "-B", str(CASE / "simulate_metro_security_bag_curtain.py"),
                            "--case", case, "--out-root", str(root / "simulation"), *resume], check=True)
    if args.stage in {"all", "render"}:
        for case in args.cases:
            command = [sys.executable, "-B", str(CASE / "render_metro_security_bag_curtain.py"),
                       "--case", case, "--out-root", str(root / "render"), "--cache-root", str(root / "simulation"),
                       "--render-threads", str(args.render_threads), "--device", args.device,
                       "--samples", str(args.samples), "--save-blend", "--grounding-audit"]
            if args.gpu_uuid:
                command += ["--gpu-uuid", args.gpu_uuid]
            if args.blender_bin:
                command += ["--blender-bin", str(args.blender_bin)]
            subprocess.run(command, check=True, env=dict(os.environ))
        print(json.dumps({"fresh_reproduction": verify_fresh(root, args.cases)}, indent=2))


if __name__ == "__main__":
    main()
