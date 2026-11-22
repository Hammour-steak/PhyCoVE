"""Native timed edit (AT FRAME k) on the accepted solver: source physics to frame k, then the edit.

The whole-clip caches are registered assets (assets/scenes/football_goal_net/native/<case>/). A timed
edit (edit_vocab.TIMED_DSL, e.g. mass_double_at_frame_8 = SET ball.mass TIMES 2 AT FRAME 8) is solved in
two native stages with the executed solver snapshot of the accepted jobs (identical code, inputs and
runtime for source and the edit):

  prefix  the source variant from t = 0 to t = (k-1)/24 s. Its 120 Hz samples must reproduce the accepted
          source cache (assets/scenes/football_goal_net/native/source/simulation.npz) to < 1e-8 (the accepted
          prefix was integrated by an earlier snapshot of the same solver; the final snapshot reproduces it to
          ~1e-12, float64 round-off); the run ends with a lossless checkpoint (net positions/velocities, ball position/velocity/spin/
          orientation, turf foundation memory, contact ledgers) at tick (k-1) * hz / 24.
  edit    the edit variant restored from that checkpoint (the solver's own --resume), so the only change at
          the edit tick is the scheduled parameter (validated: nothing else in the physics identity differs);
          it keeps solving to t = 4 s.
  merge   the final cache takes the accepted source samples before the edit frame (exactly) and the edit run's
          samples from the edit frame on; the handoff error (prefix run vs accepted source) is recorded.

    python physics/solve_timed.py --case mass_double_at_frame_8 --out DIR [--stage prefix|compare|edit|merge|all]

Needs a Python 3.10 environment with numba like the one the accepted jobs ran in (not part of the
repository); the source and mass_double job folders (code, frozen inputs, receipt) are located through
tools/retained.py. The cache folder that
render_football_goal_net.py --cache-dir replays (and that the suite keeps in inputs/native_timed/<case>/)
is DIR's simulation.npz, timed_edit.json and prefix_vs_accepted_source.json plus physics_report.json,
run_identity.json and prefix_lineage.json of the edit run (DIR/edit/delivery/native/physics/<case>/).
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import runpy
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from tools.retained import SOLVER_ARCHIVE, full_input, read, solver_receipt  # noqa: E402
import edit_vocab  # noqa: E402

HZ = 192000
# Receipt paths are recorded relative to the checkout the job ran in; the pattern maps them into the archived solver:
# <checkout>/scripts/rigid_elastic/<case-data folder>/football_goal_net/<rel>
RECORDED = re.compile(r"^<checkout>/scripts/rigid_elastic/[^/]+/football_goal_net/")


def relocate(token):
    return str(SOLVER_ARCHIVE / RECORDED.sub("", token)) if RECORDED.match(token) else token


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def schedule(case):
    rows = edit_vocab.timed_schedule(case)
    assert len(rows) == 1, "one timed change per case"
    return int(rows[0]["frame"]), rows[0]["params"]


def snapshot_argv(base_case, tag, variant, seconds, resume):
    """The accepted job's recorded argv, relocated, with the tag, variant and duration replaced.

    The job's own --resume (a checkpoint of an earlier run that is not retained) is dropped: the prefix
    starts at t = 0 and the edit stage restores the prefix run's checkpoint."""
    receipt_path = solver_receipt(base_case)
    receipt = read(receipt_path)
    args = [relocate(t) for t in receipt["argv"][3:]]
    out = []
    i = 0
    while i < len(args):
        if args[i] in ("--tag", "--variant", "--seconds", "--resume"):
            i += 2
            continue
        out.append(args[i])
        i += 1
    out += ["--tag", tag, "--variant", variant, "--seconds", repr(seconds)]
    if resume:
        out += ["--resume", str(resume)]
    return receipt_path.parent / "code/run_scene.py", receipt, out


def run_stage(stage, case, out):
    """Run one stage in this process (called through a fresh interpreter per stage)."""
    k, params = schedule(case)
    base_case = edit_vocab.TIMED_BASE[case]
    seconds = (k - 1) / 24
    root = Path(out)
    if stage == "prefix":
        script, receipt, argv = snapshot_argv("source", f"source_prefix_to_frame_{k}", "source", seconds, None)
        data = root / "prefix"
    else:
        prefix = root / "prefix/delivery/native/physics" / f"source_prefix_to_frame_{k}"
        script, receipt, argv = snapshot_argv(base_case, case, base_case, 4.0, prefix)
        data = root / "edit"
    data.mkdir(parents=True, exist_ok=True)
    if not any(parent.name == "rigid_elastic" for parent in script.parents):
        # The snapshot modules locate a rigid_elastic/_case_data folder from their own path at import time
        # (run_scene's DATA is replaced below and nothing is read from it); run a byte-identical copy of the
        # code folder from such a location.
        staged = root / "rigid_elastic" / "snapshots" / stage / "code"
        (root / "rigid_elastic" / "_case_data").mkdir(parents=True, exist_ok=True)
        if not staged.exists():
            shutil.copytree(script.parent, staged)
        script = staged / script.name
    os.environ.update(CUDA_VISIBLE_DEVICES="", NUMBA_OPT=str(receipt.get("NUMBA_OPT", "1")), OMP_NUM_THREADS="1",
                      OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1",
                      NUMBA_CACHE_DIR=str(root / "numba_cache"), TMPDIR=str(data))
    sys.path.insert(0, str(script.parent))
    if stage == "edit":
        import certifier_extension as extension

        def timed_lineage(old, new, proof, parent):
            """Allow exactly the scheduled parameter change at the restored tick; everything else is identical."""
            assert old["variant"] == "source" and new["variant"] == base_case
            before, after = old["resolved_SI"], new["resolved_SI"]
            changed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
            assert changed == sorted(params) and all(after[key] == value for key, value in params.items()), changed
            assert all(old[key] == new[key] for key in set(old) | set(new) if key not in ("variant", "resolved_SI"))
            assert parent["tick"] == (k - 1) * HZ // 24
            return {"parent_checkpoint": parent,
                    "edit_frame": k, "edit_tick": parent["tick"], "edit_time_s": parent["tick"] / HZ,
                    "changed_parameters": {key: {"from": before[key], "to": after[key]} for key in changed},
                    "identical_code_inputs_runtime_and_timestep": True,
                    "definition": edit_vocab.TIMED_DSL[case]}
        extension.validate = timed_lineage
    sys.argv = [str(script), *argv]
    module = runpy.run_path(str(script))
    module["main"].__globals__["DATA"] = data
    module["main"]()


def compare_prefix(case, out):
    """The prefix run must reproduce the accepted source cache to < 1e-8 (120 Hz samples 0 .. 5(k-1))."""
    import numpy as np
    k, _ = schedule(case)
    run = Path(out) / "prefix/delivery/native/physics" / f"source_prefix_to_frame_{k}"
    n = 5 * (k - 1) + 1
    a = np.load(full_input("source") / "simulation.npz")
    b = np.load(run / "simulation.npz")
    keys = ("times", "ball_positions", "ball_velocities", "ball_angular_velocity", "ball_orientations", "net_positions")
    result = {key: float(np.abs(a[key][:n] - b[key][:n]).max()) for key in keys}
    result["bitwise_equal"] = all(np.array_equal(a[key][:n], b[key][:n]) for key in keys)
    result["samples_compared"] = n
    result["tolerance"] = 1e-8
    (Path(out) / "prefix_vs_accepted_source.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)
    if max(v for key, v in result.items() if key in keys) >= 1e-8:
        raise SystemExit("The prefix run does not reproduce the accepted source cache")
    return result


def merge(case, out):
    """Final cache: accepted source samples before the edit frame, the edit run's samples from the edit frame on."""
    import numpy as np
    k, params = schedule(case)
    run = Path(out) / "edit/delivery/native/physics" / case
    n = 5 * (k - 1)
    a = np.load(full_input("source") / "simulation.npz")
    with np.load(run / "simulation.npz") as z:
        b = {key: z[key] for key in z.files}
    assert np.array_equal(b["times"], np.arange(481) / 120) and np.array_equal(a["times"], b["times"])
    keys = ("ball_positions", "ball_velocities", "ball_angular_velocity", "ball_orientations", "net_positions",
            "contact_stats", "mechanical_energy_J")
    handoff = {key: float(np.abs(a[key][:n + 1] - b[key][:n + 1]).max()) for key in keys}
    assert max(handoff[key] for key in keys[:5]) < 1e-8, handoff
    merged = dict(b)
    for key in keys:
        merged[key] = np.concatenate([a[key][:n], b[key][n:]])
    merged["net_times"] = merged["times"]
    # turf_control_scale (grass render input) stays the edit run's: its columns are the edit run's own active
    # controls; the ball has not reached the turf before the edit frame, so the prefix rows are all 1.
    assert np.all(b["turf_control_scale"][:n + 1] == 1.0)
    merged["timed_edit_frame"] = np.array(k)
    merged["timed_edit_native_index"] = np.array(n)
    for key in keys:
        assert np.array_equal(merged[key][:n], a[key][:n])
    target = Path(out) / "simulation.npz"
    with target.open("xb") as f:
        np.savez_compressed(f, **merged)
    lineage = json.loads((run / "prefix_lineage.json").read_text())
    receipt = {"case": case, "definition": edit_vocab.TIMED_DSL[case], "edit_frame": k, "edit_time_s": (k - 1) / 24,
               "edit_native_index_120hz": n, "edit_tick_192khz": n * HZ // 120, "parameters_after_edit": params,
               "samples_from_accepted_source": [0, n - 1], "samples_from_edit_run": [n, 480],
               "state_handoff_max_abs_error_prefix_run_vs_accepted_source": handoff,
               "handoff": "the edit run restores the solver's lossless checkpoint written by the prefix run at the edit tick",
               "lineage": lineage, "edit_run_simulation_sha256": sha(run / "simulation.npz"),
               "simulation": str(target), "simulation_sha256": sha(target),
               "accepted_source_sha256": sha(full_input("source") / "simulation.npz")}
    (Path(out) / "timed_edit.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps({k2: v for k2, v in receipt.items() if k2 != "lineage"}), flush=True)
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--case", choices=tuple(edit_vocab.TIMED_DSL), required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--stage", choices=("prefix", "edit", "compare", "merge", "all"), default="all")
    a = p.parse_args()
    if a.stage in ("prefix", "edit"):
        run_stage(a.stage, a.case, a.out)
        return
    if a.stage == "compare":
        compare_prefix(a.case, a.out)
        return
    if a.stage == "merge":
        merge(a.case, a.out)
        return
    for stage in ("prefix", "compare", "edit", "merge"):
        subprocess.run([sys.executable, "-B", str(Path(__file__)), "--case", a.case, "--out", str(a.out), "--stage", stage], check=True)


if __name__ == "__main__":
    main()
