"""Verify the accepted physics and the published suite; export ground truth; encode and publish rendered cases."""

# PCVE_EDIT_CATALOG_BEGIN
# Source description and five independent edits of the published suite.
# physics_override uses the shared-DSL scenario fields of edit_vocab.py;
# the native solver keeps its own field names (young_pa) and object setup.
# The ADD edit_dsl is the shared DSL's BETWEEN form; the native preset DSL of
# edit_vocab.EDITS (which the solve uses) is kept in native_edit_dsl.
PCVE_SCENE = "rubber_band_wood_slider"

PCVE_SOURCE = {
    "case_id": "source",
    "catalog_case_id": "source",
    "native_cli_case_id": "source",
    "kind": "source",
    "edit_dsl": None,
    "prompts": {
        "vague": {
            "zh": "木导槽里放着一块木滑块。一根橡皮筋套在导槽左端夹具里的木桩和木滑块上的木桩之间,被拉长。木滑块起初静止,松开后橡皮筋把它沿导槽往回拉。",
            "en": "A wooden slider sits in a wooden guide. A rubber band is looped between a peg held in the clamp at the left end of the guide and a peg on the slider, and is stretched. The slider is still at first; once it is released, the band pulls it back along the guide."
        },
        "quantitative": {
            "zh": "长 300 mm 的木导槽里放着一块 55 mm × 42 mm × 24 mm、36 g 的木滑块,木滑块与导槽之间的摩擦系数为 0.2。一根自然周长 200 mm、宽 1.6 mm、厚 0.6 mm、杨氏模量 1.2 MPa 的橡皮筋套在导槽左端夹具里的木桩和木滑块上的木桩之间,两木桩中心相距 117.5 mm,橡皮筋被拉长约 28%。木滑块在前 0.5 s 被固定不动,之后松开,橡皮筋把它沿导槽往回拉。",
            "en": "A 36 g wooden slider, 55 mm × 42 mm × 24 mm, sits in a 300 mm wooden guide; the friction coefficient between the slider and the guide is 0.2. A rubber band with a natural loop length of 200 mm, 1.6 mm wide, 0.6 mm thick and with a Young's modulus of 1.2 MPa is looped between a peg held in the clamp at the left end of the guide and a peg on the slider; the pegs are 117.5 mm apart, so the band is stretched by about 28%. The slider is held in place for the first 0.5 s and then released, and the band pulls it back along the guide."
        }
    },
    "editable_objects": [
        {
            "object_id": "band",
            "zh": "橡皮筋",
            "en": "the rubber band",
            "in_video": True,
            "properties": ["young_modulus"],
            "can_delete": True,
            "can_add": False
        },
        {
            "object_id": "slider",
            "zh": "木滑块",
            "en": "the wooden slider",
            "in_video": True,
            "properties": ["mass"],
            "can_delete": False,
            "can_add": False
        },
        {
            "object_id": "guide",
            "zh": "木导槽",
            "en": "the wooden guide",
            "in_video": True,
            "properties": ["friction"],
            "can_delete": False,
            "can_add": False
        },
        {
            "object_id": "stopper",
            "zh": "中间开口的木挡块",
            "en": "a wooden stop with a gap in the middle",
            "in_video": False,
            "properties": [],
            "can_delete": False,
            "can_add": True
        }
    ],
    "description_basis": "Values from scene_spec.json baseline (guide_size_m, slider_size_m, mass_kg, friction, loop_rest_m, band_width_m, band_thickness_m, young_pa, anchor_x_m, initial_x_m + attachment_offset_m, pin_radius_m, release_time_s), equal to the physics recorded in the accepted native cases; stretch = (2 x 117.5 mm + 2 pi x 3.3 mm) / 200 mm - 1; motion as seen in the source video."
}

PCVE_EDITS = {
    "add_stop": {
        "case_id": "add_stop",
        "catalog_case_id": "edit_add_stop",
        "native_cli_case_id": "add_stop",
        "kind": "edit",
        "operation": "ADD",
        "edit_dsl": "ADD stopper BETWEEN slider_peg AND left_clamp AT 1/4 FROM slider_peg",
        "native_edit_dsl": "ADD stopper AT PRESET return_path",
        "applies_from_frame": 1,
        "physics_override": {
            "stopper_present": [
                1
            ]
        },
        "physics_diff": {
            "stopper_present": {
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
                "zh": "从视频一开始,在木滑块上的木桩和左端夹具的连线上、靠近木滑块上的木桩的地方,放一个中间开口的木挡块。",
                "en": "From the start of the clip, place a wooden stop with a gap in the middle on the line between the peg on the wooden slider and the clamp at the left end, closer to the peg on the wooden slider."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,在木滑块上的木桩和左端夹具连线的四等分点上放一个中间开口的木挡块,取靠近木滑块上的木桩的那个。",
                "en": "From frame 1 onwards, place a wooden stop with a gap in the middle on the line between the peg on the wooden slider and the clamp at the left end, one quarter of the way from the peg on the wooden slider to the clamp at the left end."
            }
        },
        "how_to_edit": {
            "zh": "选择 add_stop 案例;在导槽里固定一对 6 mm × 10 mm × 20 mm 的木块(中心 x = 15 mm,两块之间留 22 mm 让橡皮筋通过),从共同的准备初态重新求解并渲染。",
            "en": "Select native case add_stop; two fixed 6 mm x 10 mm x 20 mm wooden blocks stand in the guide (centre x = 15 mm, 22 mm clear between them for the band); solve from the shared prepared state and render."
        },
        "definition_source": "scripts/rigid_elastic/rubber_band_wood_slider/edit_vocab.py"
    },
    "delete_band": {
        "case_id": "delete_band",
        "catalog_case_id": "edit_delete_band",
        "native_cli_case_id": "delete_band",
        "kind": "edit",
        "operation": "DELETE",
        "edit_dsl": "DELETE band",
        "applies_from_frame": 1,
        "physics_override": {
            "band_present": [
                0
            ]
        },
        "physics_diff": {
            "band_present": {
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
                "zh": "从视频一开始,把橡皮筋从场景中删除。",
                "en": "From the start of the clip, remove the rubber band from the scene."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把橡皮筋从场景中删除。",
                "en": "From frame 1 onwards, remove the rubber band from the scene."
            }
        },
        "how_to_edit": {
            "zh": "选择 delete_band 案例;不创建橡皮筋及其作用力,木桩和木滑块保留,从共同的准备初态重新求解并渲染。",
            "en": "Select native case delete_band; the band and its forces are not created, the pegs and the slider stay; solve from the shared prepared state and render."
        },
        "definition_source": "scripts/rigid_elastic/rubber_band_wood_slider/edit_vocab.py"
    },
    "friction_x2": {
        "case_id": "friction_x2",
        "catalog_case_id": "edit_friction_x2",
        "native_cli_case_id": "friction_x2",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET guide.friction TIMES 2",
        "applies_from_frame": 1,
        "physics_override": {
            "friction": 0.4
        },
        "physics_diff": {
            "friction": {
                "from": 0.2,
                "to": 0.4
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把木导槽的摩擦系数调大一些。",
                "en": "From the start of the clip, increase the wooden guide's friction coefficient."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把木导槽的摩擦系数增加到原来的 2 倍。",
                "en": "From frame 1 onwards, increase the wooden guide's friction coefficient to 2 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 friction_x2 案例;木滑块与导槽之间的滑动摩擦系数 0.2 改为 0.4,从共同的准备初态重新求解并渲染。",
            "en": "Select native case friction_x2; the slider-guide sliding friction changes from 0.2 to 0.4; solve from the shared prepared state and render."
        },
        "definition_source": "scripts/rigid_elastic/rubber_band_wood_slider/edit_vocab.py"
    },
    "mass_x3": {
        "case_id": "mass_x3",
        "catalog_case_id": "edit_mass_x3",
        "native_cli_case_id": "mass_x3",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET slider.mass TIMES 3",
        "applies_from_frame": 1,
        "physics_override": {
            "mass_kg": 0.108
        },
        "physics_diff": {
            "mass_kg": {
                "from": 0.036,
                "to": 0.108
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把木滑块的质量调大一些。",
                "en": "From the start of the clip, increase the wooden slider's mass."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把木滑块的质量增加到原来的 3 倍。",
                "en": "From frame 1 onwards, increase the wooden slider's mass to 3 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 mass_x3 案例;木滑块质量 0.036 kg 改为 0.108 kg,从共同的准备初态重新求解并渲染。",
            "en": "Select native case mass_x3; the slider mass changes from 0.036 kg to 0.108 kg; solve from the shared prepared state and render."
        },
        "definition_source": "scripts/rigid_elastic/rubber_band_wood_slider/edit_vocab.py"
    },
    "young_x0p5": {
        "case_id": "young_x0p5",
        "catalog_case_id": "edit_young_x0p5",
        "native_cli_case_id": "young_x0p5",
        "kind": "edit",
        "operation": "SET",
        "edit_dsl": "SET band.young_modulus TIMES 0.5",
        "applies_from_frame": 1,
        "physics_override": {
            "young_modulus_pa": 600000.0
        },
        "physics_diff": {
            "young_modulus_pa": {
                "from": 1200000.0,
                "to": 600000.0
            }
        },
        "physics_schema": "shared_dsl; scene-native adapters retain their existing field/type conversions",
        "prompts": {
            "vague": {
                "zh": "从视频一开始,把橡皮筋的杨氏模量调小一些。",
                "en": "From the start of the clip, decrease the rubber band's Young's modulus."
            },
            "quantitative": {
                "zh": "从第 1 帧开始,把橡皮筋的杨氏模量减少到原来的 0.5 倍。",
                "en": "From frame 1 onwards, reduce the rubber band's Young's modulus to 0.5 times its original value."
            }
        },
        "how_to_edit": {
            "zh": "选择 young_x0p5 案例;橡皮筋杨氏模量 1.2 MPa 改为 0.6 MPa(膜力和弯矩一起缩放),从共同的准备初态重新求解并渲染。",
            "en": "Select native case young_x0p5; the band's Young's modulus changes from 1.2 MPa to 0.6 MPa (membrane and bending response together); solve from the shared prepared state and render."
        },
        "definition_source": "scripts/rigid_elastic/rubber_band_wood_slider/edit_vocab.py"
    }
}

PCVE_EXECUTION = {
    "builder": "scripts/rigid_elastic/rubber_band_wood_slider/build_pcve_rubber_band_wood_slider.py",
    "edit_selector": "--cases <native_cli_case_id>",
    "supported_native_stages": [
        "verify",
        "encode",
        "publish",
        "package"
    ],
    "native_help_command": [
        "python3",
        "scripts/rigid_elastic/rubber_band_wood_slider/build_pcve_rubber_band_wood_slider.py",
        "--native-help"
    ],
    "list_edits_command": [
        "python3",
        "scripts/rigid_elastic/rubber_band_wood_slider/build_pcve_rubber_band_wood_slider.py",
        "--list-edits"
    ],
    "show_prompts_command": [
        "python3",
        "scripts/rigid_elastic/rubber_band_wood_slider/build_pcve_rubber_band_wood_slider.py",
        "--show-prompts",
        "<case_id>"
    ],
    "export_prompts_command": [
        "python3",
        "scripts/rigid_elastic/rubber_band_wood_slider/build_pcve_rubber_band_wood_slider.py",
        "--export-prompts"
    ],
    "simulate_entry": "scripts/rigid_elastic/rubber_band_wood_slider/simulate_rubber_band_wood_slider.py",
    "render_entry": "scripts/rigid_elastic/rubber_band_wood_slider/render_rubber_band_wood_slider.py",
    "current_suite": "renders/pcve_suites/pcve_rubber_band_wood_slider_suite",
    "notes": [
        "native_cli_case_id selects the native case; catalog_case_id names the published edit_* video directory.",
        "All six cases replay the accepted native states of the increment assets/scenes/rubber_band_wood_slider/native/accepted_increment.zip.",
        "--stage verify reads the accepted native results and solves nothing; simulate_rubber_band_wood_slider.py re-solves one case; --export-prompts writes the prompts into the published suite."
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

sys.path[:0] = [str(CASE), str(CASE / "tools")]
import argparse
import json
import shutil
import subprocess
from scene_paths import CASES, CATALOG, INCREMENT, INCREMENT_NAME, RENDERS, REPO, SCENE_MANIFEST, SUITE_KEY, output_path, python_runtime, sha256, stamp

STAGES = ("verify", "encode", "publish", "package")


def run_tool(*args):
    """Tools needing numpy run with the repository venv."""
    return subprocess.run([str(python_runtime()), "-B", *map(str, args)]).returncode


def verify_suite(cases, states):
    """Published suite named by scene_manifest.json: videos, media contract, prompts, ground truth, native binding."""
    from pcve_edit_catalog import load_catalog
    from pcve_media_contract import require_video
    pointer = json.loads(SCENE_MANIFEST.read_text(encoding="utf-8"))["canonical_suites"][SUITE_KEY]
    suite = REPO / pointer["target"]
    manifest = json.loads((suite / "suite_manifest.json").read_text(encoding="utf-8"))
    catalog = load_catalog(Path(__file__))
    records = {r["native_case_id"]: r for r in [manifest["source"], *manifest["edits"]]}
    declared = {"source": catalog["source"], **catalog["edits"]}
    rows = []
    for case in cases:
        folder = suite / "cases" / CATALOG[case]
        digest = sha256(folder / "video.mp4")
        provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
        if not digest == pointer["case_video_sha256"][case] == records[case]["video_sha256"] == provenance["video_sha256"]:
            raise SystemExit(f"{case}: video sha256 differs between file, scene_manifest.json, suite_manifest.json and provenance.json")
        media = require_video(folder / "video.mp4")
        prompts = json.loads((folder / "prompts.json").read_text(encoding="utf-8"))
        if prompts["prompts"] != declared[case]["prompts"] or prompts["edit_dsl"] != declared[case].get("edit_dsl"):
            raise SystemExit(f"{case}: prompts.json differs from the builder catalog")
        prov = json.loads((folder / "native_metadata/render_provenance.json").read_text())
        gt = json.loads((folder / "ground_truth_transforms.json").read_text())
        if prov["simulation_cache_sha256"] != states[case]:
            raise SystemExit(f"{case}: the video was rendered from other native states")
        if gt.get("format_version") != "pcve_ground_truth/1" or len(gt["frames"]) != 96 or \
                any(abs(f["time_sec"] - (f["frame_index"] - 1) / 24) > 1e-9 for f in gt["frames"]):
            raise SystemExit(f"{case}: ground truth is not the 96-frame pcve_ground_truth/1 record of the video clock")
        if gt["camera"]["matrix_world"] != [[float(v) for v in r] for r in prov["camera_matrix_world"]]:
            raise SystemExit(f"{case}: ground-truth camera differs from the render camera")
        rows.append({"case": CATALOG[case], "video_sha256": digest, "frames": media["frames"], "fps": media["fps"],
                     "size": [media["width"], media["height"]], "gt_frames": len(gt["frames"])})
    return {"suite": str(suite), "cases": rows}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", choices=STAGES, default="verify")
    p.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    p.add_argument("--out", type=Path, help="package: fresh folder for a verified copy of the increment")
    p.add_argument("--native", type=Path, help="publish: render root with one folder per case; encode: render root or case folder")
    p.add_argument("--revision", help="publish: look label recorded in the suite provenance (look_revision)")
    p.add_argument("--archive-as", help="publish: archive/pcve_suites/<name> for the previous suite")
    a = p.parse_args()
    tools = CASE / "tools"
    if a.stage == "verify":
        from retained_delivery import verify
        checked = verify(a.cases)
        print(json.dumps({"stage": "verify", "accepted_delivery": "the increment and its native states",
                          "increment": INCREMENT_NAME, "verified_cases": checked,
                          "published_suite": verify_suite(a.cases, {r["case_id"]: r["native_cache_sha256"] for r in checked}), "status": "VERIFIED"}, indent=1, ensure_ascii=False))
    elif a.stage == "encode":
        root = output_path(a.native or p.error("--native is required"))
        folders = [root] if (root / "render_provenance.json").is_file() else [root / c for c in a.cases]
        for folder in folders:
            if subprocess.run([sys.executable, str(tools / "publish_suite.py"), "encode", str(folder)]).returncode:
                raise SystemExit(f"encode failed: {folder}")
    elif a.stage == "publish":
        if not (a.native and a.revision):
            p.error("--native and --revision are required")
        args = ["build", "--native", output_path(a.native), "--revision", a.revision]
        if a.archive_as:
            args += ["--archive-as", a.archive_as]
        raise SystemExit(run_tool(tools / "publish_suite.py", *args))
    else:
        from retained_delivery import verify
        verify(list(CASES))
        out = output_path(a.out or RENDERS / f"package_{stamp()}")
        if out.exists():
            p.error("Choose a fresh output folder")
        out.mkdir(parents=True)
        shutil.copy2(INCREMENT, out / INCREMENT.name)
        print(json.dumps({"stage": "package", "copied": str(out / INCREMENT.name), "sha256": sha256(out / INCREMENT.name)}))
