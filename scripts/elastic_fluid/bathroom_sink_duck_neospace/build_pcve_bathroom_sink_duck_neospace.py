"""Public entry point: the source and edited videos of the faucet stream on the elastic duck (Genesis two-way coupling).

Builds the room (scene_*) when missing, prepares the duck geometry (duck_*), then per case simulates (simulate_*),
reconstructs the water and skins the duck (appearance/surface_*) and renders with the look (render_*, look_*). Source: a 2 kPa
duck under a 4.5 L/min tap; edits: `SET duck.stiffness TIMES 30`, `SET duck.core_stiffness TIMES 0.1`, `DELETE duck`,
`DELETE water`, `SET faucet.inflow_velocity TIMES 2`, and `SET faucet.inflow_velocity TO 0 AT FRAME 49`.
Every case shares the duck geometry and all other settings;
only the MPM substep count follows the duck's elastic wave speed. Each step is skipped when its output exists, so an
interrupted build resumes. Each case keeps video.mp4 and its bilingual prompts.json in <suite-root>/cases/<case_id>/,
intermediates go to <suite-root>/runs/ and <suite-root>/work/, and the configuration and run summaries to
<suite-root>/suite_manifest.json (`source` and `edits`, as in the other PCVE suites).
    CUDA_VISIBLE_DEVICES=<gpu> <genesis python> build_pcve_bathroom_sink_duck_neospace.py --suite-root SUITE --blender BLENDER
"""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'build_pcve')
# PCVE_UNIFIED_ENTRY_END

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("PCVE_REPO_ROOT", str(HERE.parents[2])))
sys.path.append(str(HERE.parents[1]))
from pcve_assets import blender as default_blender  # noqa: E402
NAME = "bathroom_sink_duck_neospace"
SUITE_NAME = f"pcve_{NAME}_suite"
SOURCE_CASE_ID = "bathroom_sink_duck_baseline"
BASE_INFLOW_VELOCITY = 4.5 / 60000.0 / (math.pi * 0.0065 ** 2)     # 4.5 L/min through the 13 mm aerator, m/s
PHYSICS_FLAGS = {"duck_young_modulus_pa": "--young", "duck_core_young_modulus_pa": "--core-young",
                 "faucet_inflow_velocity_m_s": "--inflow-velocity"}
PRESENCE_FLAGS = {"duck_presence": "--no-duck", "water_presence": "--no-water"}   # given when the entry is [0]
SOURCE = {
    "case_id": SOURCE_CASE_ID, "kind": "source", "interaction_category": "elastic_fluid",
    "description": {
        "vague": {"en": "Water from a bathroom faucet pours onto a soft rubber duck sitting in the sink; the stream presses into the duck and rocks it back.",
                  "zh": "浴室水龙头的水流冲在洗手池里的一只软橡皮鸭上，水流把鸭子压得凹陷，并把它冲得向后仰。"},
        "quantitative": {"en": "A tap stream of about 4.8 L/min falls about 8 cm onto a 12 cm, 91 g rubber duck with a Young's modulus of 2 kPa resting in a porcelain basin; "
                               "its weight squashes the duck by about 7 mm, the stream dents its head by about 3 mm and tilts it back by up to 18 degrees over 4 s.",
                         "zh": "约 4.8 L/min 的水流下落约 8 cm，冲在瓷盆里一只长 12 cm、重 91 g、杨氏模量 2 kPa 的橡皮鸭上；鸭子在自重下被压矮约 7 mm，"
                               "水流把它的头顶压下约 3 mm，并在 4 秒内把它冲得最多向后倾斜 18 度。"}},
    # The duck is one material; its core (deeper than the 10 mm skin) is a separate knob that equals the skin here.
    "physics": {"duck_presence": [1], "water_presence": [1],
                "duck_young_modulus_pa": 2000.0, "duck_core_young_modulus_pa": 2000.0,
                "faucet_inflow_velocity_m_s": BASE_INFLOW_VELOCITY},
}
EDITS = (
    {"case_id": "edit_stiff_duck", "kind": "edit", "edit_dsl": "SET duck.stiffness TIMES 30",
     "edit_summary": "The duck's Young's modulus rises from 2 kPa to 60 kPa at the same shape, density and Poisson ratio: it no longer sags "
                     "under its own weight (101.8 mm tall instead of 95.4 mm) or dents under the stream, and the stream rocks it back by up "
                     "to 32 degrees instead of 18."},
    {"case_id": "edit_soft_core_duck", "kind": "edit", "edit_dsl": "SET duck.core_stiffness TIMES 0.1",
     "edit_summary": "The duck's core (deeper than 10 mm below its surface) softens from 2 kPa to 200 Pa while its skin keeps "
                     "2 kPa: the duck sags under its own weight (88 mm tall at the first frame instead of 95 mm, and wider), keeps "
                     "sinking under the stream to 78 mm by 4 s while the source stays at 94 mm, and rocks back only up to 11 "
                     "degrees instead of 18."},
    {"case_id": "edit_delete_duck", "kind": "edit", "edit_dsl": "DELETE duck",
     "edit_summary": "The duck is removed from the first frame, together with its MPM material and ghost boundary: the unchanged "
                     "4.8 L/min stream falls straight onto the empty basin floor and spreads over it as a thin film."},
    {"case_id": "edit_delete_water", "kind": "edit", "edit_dsl": "DELETE water",
     "edit_summary": "The faucet releases no water from the first frame: the tap stays dry and the duck sits on the dry basin floor "
                     "in its settled shape for the whole clip, tilting at most 2 degrees as it finishes settling instead of being "
                     "rocked back to 18 degrees."},
    {"case_id": "edit_high_flow", "kind": "edit", "edit_dsl": "SET faucet.inflow_velocity TIMES 2",
     "edit_summary": "The faucet's outlet speed doubles from 0.57 to 1.13 m/s through the same 13 mm aerator (the emitted flow "
                     "rises from about 4.8 to 8.4 L/min): the stream knocks the duck back faster (15 degrees after 0.3 s instead "
                     "of 7) and further (up to 21 degrees instead of 18), and about 1.75 times as much water spreads over the "
                     "basin floor."},
    {"case_id": "edit_stop_flow_at_2s", "kind": "edit", "edit_dsl": "SET faucet.inflow_velocity TO 0 AT FRAME 49",
     "edit_summary": "At 2.00 s the faucet outlet speed changes from 0.565 m/s to zero, so no new water is emitted. "
                     "Previously emitted water continues under gravity and the two-way MPM/DFSPH coupling; "
                     "the duck's motion and deformation remain simulated."},
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite-root", type=Path, required=True)
    parser.add_argument("--scene", type=Path, help="built room (default: <suite-root>/work/scene.blend, built when missing)")
    parser.add_argument("--bathroom-asset", type=Path, help="Bathroom rev1 glb, if not at scene_*'s default path")
    parser.add_argument("--duck-asset", type=Path, help="rubber duck .blend, if not at scene_*'s default path")
    parser.add_argument("--blender", default=str(default_blender()), help="default: $BLENDER, blender on PATH, else ~/.local/opt/blender-*")
    parser.add_argument("--python", default=sys.executable, help="interpreter of the Genesis environment")
    parser.add_argument("--pool-simulate", type=Path, help="override the module providing create_boundary_solver()")
    parser.add_argument("--map-width", type=int, help="explicit material-map stencil width for a selected case; timed edits otherwise inherit the existing source")
    parser.add_argument("--publish-root", type=Path, help="suite path recorded in the manifest's outputs (default: --suite-root)")
    parser.add_argument("--cases", nargs="*", default=[SOURCE_CASE_ID] + [e["case_id"] for e in EDITS])
    return parser.parse_args()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    temporary.replace(path)


def run(command, log):
    print("RUN " + " ".join(map(str, command)), flush=True)
    with log.open("w") as stream:
        subprocess.run([str(part) for part in command], stdout=stream, stderr=subprocess.STDOUT, check=True)


def vocabulary():
    sys.path.insert(0, str(ROOT / "scripts"))
    import pcve_edit_dsl as dsl
    vocab = dsl.Vocabulary(
        objects={"duck": {"zh": "黄色橡皮鸭", "en": "the yellow rubber duck"},
                 "faucet": {"zh": "洗手台水龙头", "en": "the sink faucet"},
                 "water": {"zh": "水龙头流出的水", "en": "the water flowing from the faucet"}},
        properties={"stiffness": dsl.PropertySpec("scalar", "Pa", "刚度", "stiffness"),
                    "core_stiffness": dsl.PropertySpec("scalar", "Pa", "内芯刚度", "core stiffness"),
                    "inflow_velocity": dsl.PropertySpec("scalar", "m/s", "入流速度", "inflow velocity")},
        sim_bindings={("duck", "stiffness"): dsl.CompoundBinding((dsl.SimBinding("duck_young_modulus_pa"),
                                                                   dsl.SimBinding("duck_core_young_modulus_pa"))),
                      ("duck", "core_stiffness"): dsl.SimBinding("duck_core_young_modulus_pa"),
                      ("faucet", "inflow_velocity"): dsl.SimBinding("faucet_inflow_velocity_m_s")},
        delete_bindings={"duck": dsl.DeleteBinding("duck_presence", 0), "water": dsl.DeleteBinding("water_presence", 0)},
        baseline_physics=SOURCE["physics"], total_frames=96)
    return dsl, vocab


def plans():
    dsl, vocab = vocabulary()
    source = {**SOURCE, "prompts_document": {"schema_version": 1, "case_id": SOURCE_CASE_ID, "kind": "source",
                                             "prompts": SOURCE["description"]}}
    edits = []
    for case in EDITS:
        edit = dsl.parse(case["edit_dsl"], vocab)
        document = {"schema_version": 2, "case_id": case["case_id"], "source_case_id": SOURCE_CASE_ID,
                    "edit_dsl": case["edit_dsl"], "edit_summary": case["edit_summary"],
                    "applies_from_frame": dsl.starts_at_frame(edit),
                    "physics_diff": {**({f"presence ({edit.object_id})": {"from": True, "to": False}} if isinstance(edit, dsl.DeleteEdit) else
                                        {f"{edit.property_name} ({edit.object_id})": {"from": dsl.baseline_value_for(edit, vocab), "to": edit.to_value}}),
                                     "timing": dsl.timing_diff(edit, vocab)},
                    "prompts": dsl.make_prompts(edit, vocab)}
        if dsl.is_timed(edit):
            document["physics_diff"]["timing"]["time_s"] = (dsl.starts_at_frame(edit) - 1) / 24.0
        edits.append({**case, "physics": {**SOURCE["physics"], **dsl.to_scenario_override(edit, vocab)}, "prompts_document": document})
    return [source] + edits


def build_case(args, plan, duck, runs, cases, published):
    dsl, _ = vocabulary()
    work = runs / plan["case_id"]
    work.mkdir(parents=True, exist_ok=True)
    sim = work / "genesis_sim.npz"
    if not sim.exists():
        command = [args.python, "-u", HERE / f"simulate_{NAME}.py", "--duck-solid", duck / "duck_solid_world.obj",
                   "--ghost-mesh", duck / "duck_shell_world.obj", "--out", sim]
        for key, value in plan["physics"].items():
            if key == dsl.TIMED_EDITS_KEY:
                if len(value) != 1 or set(value[0]["params"]) != {"faucet_inflow_velocity_m_s"}:
                    raise ValueError("Only one timed faucet-inlet velocity change is implemented")
                command += ["--inflow-change-frame", str(value[0]["frame"]),
                            "--inflow-velocity-after", repr(value[0]["params"]["faucet_inflow_velocity_m_s"])]
            elif key in PRESENCE_FLAGS:
                command += [] if value[0] else [PRESENCE_FLAGS[key]]
            elif key == "duck_core_young_modulus_pa" and value == plan["physics"]["duck_young_modulus_pa"]:
                continue                               # one material
            else:
                command += [PHYSICS_FLAGS[key], repr(value)]
        if args.pool_simulate:
            command += ["--pool-simulate", args.pool_simulate]
        source_sim = runs / SOURCE_CASE_ID / "genesis_sim.npz"
        if dsl.TIMED_EDITS_KEY in plan["physics"] and not source_sim.exists():
            # One run for both: the timed edit's simulation also writes the unedited continuation as the source,
            # branched from the same solver state, so the frames before the change are identical in both cases.
            source_sim.parent.mkdir(parents=True, exist_ok=True)
            command += ["--source-branch-out", source_sim]
        if args.map_width is not None:
            command += ["--map-width", str(args.map_width)]
        elif dsl.TIMED_EDITS_KEY in plan["physics"]:
            source_report = runs / SOURCE_CASE_ID / "genesis_sim.json"
            if source_report.exists():
                # The published source predates the wider stencil used for the soft-core case. Use its
                # actual stencil for the timed edit instead of silently changing the pre-edit numerics.
                width = json.loads(source_report.read_text())["numerics"]["map_local_width"]
                command += ["--map-width", str(width)]
        run(command, work / "genesis_sim.log")
    surfaces = work / "surfaces"
    if not (surfaces / "surface_report.json").exists():
        run([args.python, HERE / f"appearance/surface_{NAME}.py", "--sim", sim, "--duck-rest", duck / "duck_rest.npz",
             "--out-dir", surfaces], work / "surface.log")
    render = work / "render"
    if not (render / "video.mp4").exists():
        run([args.blender, "-b", "--python-exit-code", "1", "--python", HERE / f"render_{NAME}.py", "--",
             "--scene", args.scene, "--surfaces", surfaces, "--output-dir", render], work / "render.log")
    case = cases / plan["case_id"]
    case.mkdir(parents=True, exist_ok=True)
    shutil.copy2(render / "video.mp4", case / "video.mp4")
    write_json(case / "prompts.json", plan["prompts_document"])

    report = json.loads(sim.with_suffix(".json").read_text())
    assert all(report["physics"][key] == value if isinstance(value, list) else math.isclose(report["physics"][key], value, rel_tol=1e-9)
               for key, value in plan["physics"].items()), "run does not match the case"
    rows = report["rows"]
    rendering = json.loads((render / "render_report.json").read_text())
    settle = re.search(r"^SETTLE took ([\d.]+)s", (work / "genesis_sim.log").read_text(), re.M)
    surface_seconds = sum(f["seconds"] for f in json.loads((surfaces / "surface_report.json").read_text())["frames"].values())
    elapsed = (report["build_seconds"] + (float(settle.group(1)) if settle else 0.0) + sum(r["seconds"] for r in rows)
               + surface_seconds + rendering["render_seconds"])
    record = {key: plan[key] for key in ("case_id", "kind", "interaction_category", "description", "source_case_id", "edit_dsl",
                                          "edit_summary") if key in plan}
    if plan["kind"] == "edit":
        document = plan["prompts_document"]
        record = {"case_id": plan["case_id"], "kind": "edit",
                  **{key: document[key] for key in ("source_case_id", "edit_dsl", "edit_summary", "applies_from_frame", "physics_diff", "prompts")}}
    record.update({
        "status": "completed", "elapsed_sec": round(elapsed, 1),
        "outputs": {"video": str(published / "cases" / plan["case_id"] / "video.mp4"),
                    "prompts": str(published / "cases" / plan["case_id"] / "prompts.json")},
        "video_sha256": digest(case / "video.mp4"),
        "physics": report["physics"], "numerics": report["numerics"],
        **({"provenance": report["provenance"]} if "provenance" in report else {}),
        "simulation": {"frames": report["frames"], "seconds_per_frame": report["seconds_per_frame"],
                       **({"inflow_intervention": report["inflow_intervention"]} if "inflow_intervention" in report else {}),
                       # what the emitter actually released: it drops the sub-layer remainder each time it emits a layer
                       "emitted_flow_l_min": rows[-1]["water"] * report["numerics"]["sph_particle_m"] ** 3
                                             / (report["frames"] / report["numerics"]["fps"]) * 60000.0,
                       "duck_peak_tilt_deg": max((r["tilt_deg"] for r in rows if "tilt_deg" in r), default=None),
                       "duck_final_tilt_deg": rows[-1].get("tilt_deg"),
                       "max_local_stretch": max((r["stretch_max"] for r in rows if "stretch_max" in r), default=None),
                       # water deeper inside the duck than its ghost boundary (see simulate_*: INSIDE_*)
                       "water_inside_duck_max": max(r.get("water_inside_duck", 0) for r in rows),
                       "pressure_iteration_cap_hits": sum(sum(r["cap_hits"]) for r in rows),
                       "material_map_error_peaks": rows[-1].get("map_error_peaks")},
        "render": {k: v for k, v in rendering.items() if k != "video"}})
    if "inflow_intervention" in report:
        event = report["inflow_intervention"]
        before_seconds = event["time_s"]
        before_count = rows[event["frame"] - 2]["water"] if event["frame"] > 1 else 0
        volume_per_particle = report["numerics"]["sph_particle_m"] ** 3
        record["simulation"]["emitted_flow_before_change_l_min"] = (
            before_count * volume_per_particle * 60000.0 / before_seconds if before_seconds else None)
        remaining_seconds = report["frames"] / report["numerics"]["fps"] - before_seconds
        record["simulation"]["emitted_flow_after_change_l_min"] = (
            (rows[-1]["water"] - before_count) * volume_per_particle * 60000.0 / remaining_seconds)
        record["simulation"]["emitted_flow_l_min_note"] = "Mean over the entire clip, including the interval with the tap off."
    return record


def main():
    args = parse_args()
    suite = args.suite_root.expanduser().resolve()
    published = args.publish_root or suite
    runs, cases = suite / "runs", suite / "cases"
    args.scene = (args.scene or suite / "work" / "scene.blend").expanduser().resolve()
    if not args.scene.exists():
        args.scene.parent.mkdir(parents=True, exist_ok=True)
        assets = [*(["--bathroom-asset", args.bathroom_asset] if args.bathroom_asset else []),
                  *(["--duck-asset", args.duck_asset] if args.duck_asset else [])]
        run([args.blender, "-b", "--python-exit-code", "1", "--python", HERE / f"appearance/scene_{NAME}.py", "--",
             "--work-dir", args.scene.parent, *assets], args.scene.parent / "scene.log")
    duck = runs / "duck"
    if not (duck / "duck_rest.npz").exists():
        duck.mkdir(parents=True, exist_ok=True)
        run([args.blender, "-b", args.scene, "--python-exit-code", "1", "--python", HERE / f"appearance/duck_{NAME}.py",
             "--", "--out-dir", duck], duck / "prepare.log")
    selected = [plan for plan in plans() if plan["case_id"] in args.cases]
    if not (runs / SOURCE_CASE_ID / "genesis_sim.npz").exists():
        # A timed edit simulates the source as its unedited branch (see build_case), so build it first.
        dsl, _ = vocabulary()
        selected.sort(key=lambda plan: 0 if dsl.TIMED_EDITS_KEY in plan["physics"] else 1)
    records = {plan["case_id"]: build_case(args, plan, duck, runs, cases, published) for plan in selected}

    manifest_path = suite / "suite_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    previous = {entry["case_id"]: entry for entry in [manifest.get("source")] + manifest.get("edits", []) if entry}
    previous.update(records)
    source = previous.get(SOURCE_CASE_ID)
    manifest = {
        "schema_version": 3, "suite_name": SUITE_NAME, "interaction_category": "elastic_fluid",
        "description": "A faucet stream of about 4.8 L/min lands on a 12 cm rubber duck resting in a porcelain basin (Neospace Bathroom rev1); "
                       "the edits make the duck 30 times stiffer, soften its core tenfold under an unchanged 10 mm skin, "
                       "double the faucet's outlet speed, delete the duck or the water, or turn off the faucet at 2 seconds.",
        "coupling": "Genesis 1.4.3 MPM duck and DFSPH water, two-way coupled by the pool scene's pressure-boundary operator "
                    "(equal and opposite impulses) plus a momentum-conserving water-duck viscous term",
        "baseline_physics": source["physics"] if source else None,
        "total_frames": 96, "resolution": [1280, 720], "fps": 24, "duration_sec": 4,
        "samples": source["render"]["samples"] if source else None, "look": source["render"]["look"] if source else None,
        "source_case_id": SOURCE_CASE_ID, "selected_base_video_sha256": source["video_sha256"] if source else None,
        "duck_geometry": json.loads((duck / "duck_prepare_report.json").read_text()),
        "source": source,
        "edits": [previous[e["case_id"]] for e in EDITS if e["case_id"] in previous]}
    write_json(manifest_path, manifest)
    print(f"PCVE_GENESIS_SUITE {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
