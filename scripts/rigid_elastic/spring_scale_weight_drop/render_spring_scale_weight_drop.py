"""Render one case from its native cache on one leased NVIDIA GPU (tools/worker_run.py): the look of the published
suite (appearance/realism.py, an overlay on the base look; default) or the base look (appearance/render_spring.py)."""

from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "render")
# PCVE_UNIFIED_ENTRY_END

import argparse
import datetime
import os
import subprocess

from pcve_assets import blender
from physics.scene import DELIVERY
from scene_paths import output_path

CASE_DIR = Path(__file__).resolve().parent
RENDERERS = {"base": "appearance/render_spring.py", "realism": "appearance/realism.py"}
SAMPLES = {"base": 192, "realism": 128}


def main():
    from edit_vocab import CASE_DSL, TIMED_DSL

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=[*CASE_DSL, *TIMED_DSL], default="source")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="new case directory, outside scripts/, the assets and the suite")
    parser.add_argument("--input-root", type=Path, default=DELIVERY,
                        help="native caches <root>/cases/<case>/{native_dynamics.npz,physics.json} (default: the accepted delivery; "
                             "a timed case: the simulate output root)")
    parser.add_argument("--look", choices=tuple(RENDERERS), default="realism",
                        help="realism: appearance/realism.py, the look of the published suite; base: appearance/render_spring.py")
    parser.add_argument("--blender-bin", type=Path)
    parser.add_argument("--gpu-uuid", default="auto")
    parser.add_argument("--render-threads", type=int, default=6)
    parser.add_argument("--samples", type=int, help="default 128 (realism, as published) or 192 (base)")
    parser.add_argument("--wait-idle", action="store_true")
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("Renders run on Linux with an NVIDIA GPU (tools/worker_run.py)")
    samples = SAMPLES[args.look] if args.samples is None else args.samples
    try:
        output = output_path(args.output_dir)
    except ValueError as error:
        parser.error(str(error))
    if output.exists():
        parser.error("Choose a new render directory")
    if args.render_threads < 1 or samples < 1:
        parser.error("Threads and samples must be positive")
    cache = args.input_root.resolve() / "cases" / args.case
    for name in ("native_dynamics.npz", "physics.json"):
        if not (cache / name).is_file():
            parser.error(f"Missing native input {cache / name}")
    env = dict(os.environ, PCVE_SPRING_SCALE_INPUT=str(args.input_root.resolve()))
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    worker = [
        sys.executable, "-B", str(CASE_DIR / "tools/worker_run.py"),
        "--gpu", args.gpu_uuid, "--name", f"render_{args.look}_{args.case}_{stamp}",
    ]
    if args.wait_idle:
        worker.append("--wait-idle")
    worker += [
        "--", str(args.blender_bin or blender()), "-b", "-t", str(args.render_threads),
        "--factory-startup", "--disable-autoexec", "--python-exit-code", "1",
        "--python", str(CASE_DIR / RENDERERS[args.look]), "--",
        "--case", args.case, "--out", str(output), "--samples", str(samples),
    ]
    subprocess.run(worker, env=env, check=True)


if __name__ == "__main__":
    main()
