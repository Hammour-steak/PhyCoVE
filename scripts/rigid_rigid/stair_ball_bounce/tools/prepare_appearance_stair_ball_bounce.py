"""Reuse accepted solver output for an appearance-only rebuild, with frozen-data proof."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scene_config import differences, merge, scenario, signature
from simulate_stair_ball_bounce import write_json


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen(result):
    return {k: v for k, v in result.items() if k not in ["configuration", "configuration_sha256"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument("--out-root", type=Path, required=True)
    p.add_argument("--appearance-json", type=Path, help="appearance-only override; default: the appearance in scene_config.py")
    p.add_argument("--cases", nargs="+", default=["source", "edit_high_friction"])
    p.add_argument("--case-source", nargs="*", default=[], metavar="CASE=ROOT",
                   help="Accepted suite holding a case that is absent from --source-root")
    a = p.parse_args()
    old, out = a.source_root.resolve(), a.out_root.resolve()
    override = json.loads(a.appearance_json.read_text()) if a.appearance_json else {"appearance": scenario()["appearance"]}
    assert set(override) == {"appearance"}
    assert old != out and not out.exists(), "Use a new output root"
    roots = {case: old for case in a.cases}
    roots.update({k: Path(v).resolve() for k, v in (item.split("=", 1) for item in a.case_source)})
    for root in set(roots.values()):
        assert json.loads((root/"acceptance_report.json").read_text())["accepted"], root
    source = json.loads((old/"cases/source/physics_transforms.json").read_text())
    cfg = merge(source["configuration"], override)
    # These presets explicitly include the existing shared camera, so scenario()
    # and the public build command reconstruct exactly the same full configuration.
    assert cfg == scenario(override)
    manifest = copy.deepcopy(json.loads((old/"suite_manifest.json").read_text()))
    manifest.update(configuration=cfg, source=None, edits=[], status="appearance_render_pending")
    out.mkdir(parents=True)
    write_json(out/"suite_manifest.json", manifest)
    records = []
    for case in a.cases:
        before_path = roots[case]/"cases"/case/"physics_transforms.json"
        before = json.loads(before_path.read_text())
        # Every edit must branch from the same solved source rollout.
        case_source = json.loads((roots[case]/"cases/source/physics_transforms.json").read_text())
        assert {k: v for k, v in frozen(case_source).items() if k != "simulation_wall_sec"} == \
            {k: v for k, v in frozen(source).items() if k != "simulation_wall_sec"}
        after = copy.deepcopy(before)
        # The source suite may carry a different look (camera included); the
        # output look is the complete scenario appearance, and only appearance may differ.
        after["configuration"] = scenario(override, case)
        after["configuration_sha256"] = signature(after["configuration"])
        delta = differences(before["configuration"], after["configuration"])
        assert delta and all(k.startswith("appearance.") for k in delta)
        assert frozen(before) == frozen(after)
        for key in ["physics", "simulation_quality", "render"]:
            assert before["configuration"][key] == after["configuration"][key]
        folder = out/"cases"/case
        write_json(folder/"physics_transforms.json", after)
        write_json(folder/"settings.json", after["configuration"])
        for name in ["trajectory.csv", "contacts.json"]:
            shutil.copy2(before_path.with_name(name), folder/name)
            assert digest(before_path.with_name(name)) == digest(folder/name)
        records.append({"case": case, "solver_reference": str(before_path),
            "reference_acceptance": str(roots[case]/"acceptance_report.json"),
            "reference_acceptance_sha256": digest(roots[case]/"acceptance_report.json"),
            "before_physics_file_sha256": digest(before_path), "after_physics_file_sha256": digest(folder/"physics_transforms.json"),
            "frozen_solver_payload_sha256": signature(frozen(after)),
            "physics_configuration_sha256": signature(after["configuration"]["physics"]),
            "simulation_quality_sha256": signature(after["configuration"]["simulation_quality"]),
            "before": before["configuration"], "after": after["configuration"],
            "changed_fields": delta, "all_nonappearance_configuration_identical": True,
            "all_poses_contacts_raw_contacts_metrics_and_timing_identical": True,
            "trajectory_csv_and_contacts_files_byte_identical": True})
    write_json(out/"appearance_change_audit.json", {"accepted": True,
        "scope": "Appearance-only configuration replacement. All other solver fields are structurally identical, including raw contacts and timing; CSV and contact exports are byte-identical. No simulation was rerun.",
        "reference_acceptance": str(old/"acceptance_report.json"),
        "reference_acceptance_sha256": digest(old/"acceptance_report.json"), "cases": records})
    print(json.dumps({"prepared": str(out), "cases": a.cases,
                      "changed_fields": list(records[0]["changed_fields"]), "solver_rerun": False}, indent=2))


if __name__ == "__main__":
    main()
