"""Solve the source and five physical edits, sharing the frozen stationary pose.

Writes <out-root>/cases/<case>/ (trajectory.npz, scene_params.json, audits).
This entry uses MuJoCo 3.3.7, NumPy and SciPy only; it never starts Blender.
When the current interpreter does not provide MuJoCo 3.3.7 it re-runs itself
with .runtime/spring_car_collision/deps on PYTHONPATH (under .venv-rigid-elastic
when that environment exists, else under the current interpreter).
"""
from __future__ import annotations

# PCVE_UNIFIED_ENTRY_BEGIN
from pathlib import Path as _EntryPath
import sys as _entry_sys
_entry_sys.path.insert(0,str(_EntryPath(__file__).resolve().parents[2]))
if __name__=="__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__,'simulate')
# PCVE_UNIFIED_ENTRY_END

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "physics")]
import edit_vocab
import scene_config

SPEC = edit_vocab.SPEC
# Toy car body (appearance/car_model.py) and the shared at-rest pose made from it by tools/make_car_geometry.py.
GEOMETRY = "toy_car"
CASE_IDS = tuple(SPEC["cases"])


def checked_override(case_id):
    """Use the default shared parser and physical policy, including genuine ADD."""
    if case_id == "source":
        return {}
    edit = edit_vocab.dsl.parse(SPEC["edit_dsl"][case_id], edit_vocab.VOCAB)
    actual = edit_vocab.scenario_override(edit)
    expected = SPEC["cases"][case_id]
    if actual.keys() != expected.keys() or any(
        abs(float(actual[key]) - float(expected[key])) > 1e-12 for key in expected
    ):
        raise ValueError(f"DSL does not match the physical case: {case_id}")
    return dict(expected)


def pinned_runtime():
    try:
        import mujoco
    except ImportError:
        return False
    return mujoco.__version__ == "3.3.7"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root", type=Path, default=scene_config.DEFAULT_SIMULATE_OUT)
    parser.add_argument("--asset-dir", type=Path, default=scene_config.asset_dir())
    parser.add_argument("--cases", nargs="+", choices=CASE_IDS, default=list(CASE_IDS))
    parser.add_argument("--dry-run", action="store_true", help="Validate physical definitions and inputs without integrating or writing.")
    args = parser.parse_args()
    if not args.dry_run and not pinned_runtime():
        if os.environ.get("SPRING_CAR_RUNTIME_REEXEC"):
            raise SystemExit("MuJoCo 3.3.7 is not importable from the scene runtime " + str(scene_config.MUJOCO_DEPS))
        env = scene_config.mujoco_env()
        env["SPRING_CAR_RUNTIME_REEXEC"] = "1"
        command = [str(scene_config.PYTHON), "-B", str(Path(__file__).resolve()), *sys.argv[1:]]
        raise SystemExit(subprocess.run(command, env=env).returncode)
    asset_dir = args.asset_dir.resolve()
    initial_path = asset_dir / GEOMETRY / "source_initial_state.json"
    initial_bytes = initial_path.read_bytes()
    initial_hash = hashlib.sha256(initial_bytes).hexdigest()
    initial_state = json.loads(initial_bytes)
    # The asset downloader verifies the complete manifest; the consumed common pose is recorded as a
    # native input (with its sha256) in every new solver provenance.
    jobs = []
    for case_id in args.cases:
        override = checked_override(case_id)
        case_dir = args.out_root.resolve() / "cases" / case_id
        if not args.dry_run and any(case_dir.glob("*")):
            raise FileExistsError(f"Refusing to overwrite an existing case: {case_dir}. Choose a new --out-root.")
        jobs.append((case_id, override, case_dir))
    if args.dry_run:
        print(json.dumps({"scene_id": SPEC["scene_id"], "dry_run": True,
            "cases": [{"case_id": name, "simulation_dt_s": SPEC["production_dt_s_by_case"][name],
                       "physical_override": override, "out": str(case_dir)}
                      for name, override, case_dir in jobs],
            "source_initial_state_sha256": initial_hash}, indent=2))
        return
    from physics_model import params_for_case, run_case, json_save
    for case_id, override, case_dir in jobs:
        c = params_for_case(case_id, overrides={"simulation_dt_s": SPEC["production_dt_s_by_case"][case_id]},
                            geometry_contract=asset_dir / GEOMETRY / "car_geometry.json")
        c["source_initial_state_input_file"] = str(initial_path)
        c["source_initial_state_input_sha256"] = initial_hash
        run_case(c, case_dir, initial_state=initial_state)
        json_save(case_dir / "scenario_overrides.json", override)
        print(json.dumps({"case_complete": case_id, "out": str(case_dir),
                          "numerically_revalidated": False}), flush=True)


if __name__ == "__main__":
    main()
