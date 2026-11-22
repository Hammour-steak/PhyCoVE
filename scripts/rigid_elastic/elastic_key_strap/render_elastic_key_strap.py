"""Render one case with the current look (appearance/realism.py) from its native solve.

    render_elastic_key_strap.py --case CASE [--out-root DIR | --out DIR] [--frames F ...] [--samples N]
                                [--device cpu|optix|cuda] [--gpu-uuid UUID] [--cpu-threads N]
                                [--blender-bin BIN] [--cache-dir DIR]

Frames go to DIR/realism/CASE/frame_0001..0096.png together with realism_provenance.json, the per-frame replay
audit and the appearance audit (default root renders/elastic_key_strap/rebuild/<UTC stamp>). The cache defaults to
the accepted solve in assets/scenes/elastic_key_strap/native_solves/cases/CASE. Video frame f shows native state f-1
of the 24 Hz cache; the camera is fixed. Blender 4.3.2 (tools/blender-4.3.2-linux-x64 in the repository root).
"""

from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
CASE = Path(__file__).resolve().parent
SCRIPTS = CASE.parents[1]
sys.path.insert(0, str(SCRIPTS))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, 'render')
# PCVE_UNIFIED_ENTRY_END

import argparse
import os
import subprocess

sys.path.insert(0, str(CASE))
from scene_paths import CASES, OUTPUT, TIMED_CASES, blender_runtime, cache_dir, output_path, stamp


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--case", choices=CASES + TIMED_CASES, default="source")
    p.add_argument("--out-root", type=Path)
    p.add_argument("--out", type=Path, help="exact output folder (instead of OUT_ROOT/realism/CASE)")
    p.add_argument("--frames", type=int, nargs="+", help="video frames 1..96 (default: all)")
    p.add_argument("--samples", type=int, default=384)
    p.add_argument("--device", choices=("cpu", "optix", "cuda"), default="cpu")
    p.add_argument("--gpu-uuid", help="sets CUDA_VISIBLE_DEVICES for a GPU device")
    p.add_argument("--cpu-threads", type=int, default=32)
    p.add_argument("--blender-bin", type=Path)
    p.add_argument("--cache-dir", type=Path, help="native solve to replay (default: the accepted native_solves case)")
    a = p.parse_args()
    out = output_path(a.out or (a.out_root or OUTPUT / stamp()) / "realism" / a.case)
    cache = (a.cache_dir or cache_dir(a.case)).resolve()
    for name in ("simulation.npz", "resolved_config.json"):
        if not (cache / name).is_file():
            p.error(f"{cache / name} is missing")
    if a.frames and not all(1 <= f <= 96 for f in a.frames):
        p.error("--frames are video frames 1..96")
    out.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if a.gpu_uuid:
        env["CUDA_VISIBLE_DEVICES"] = a.gpu_uuid
    elif a.device == "cpu":
        env["CUDA_VISIBLE_DEVICES"] = ""
    cmd = [str(blender_runtime(a.blender_bin)), "-b", "--factory-startup", "-t", str(a.cpu_threads),
           "--python-exit-code", "1", "--python", str(CASE / "appearance/realism.py"), "--",
           "--case", a.case, "--cache-dir", str(cache), "--out", str(out),
           "--samples", str(a.samples), "--device", a.device.upper()]
    if a.frames:
        cmd += ["--frames", *map(str, a.frames)]
    print(" ".join(cmd), flush=True)
    raise SystemExit(subprocess.run(cmd, env=env).returncode)


if __name__ == "__main__":
    main()
