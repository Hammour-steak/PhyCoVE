"""Render one case with the current look (appearance/realism.py) from its native cache.

Default input: the accepted solve of the case (assets scenes/plastic_ruler_coin/accepted/physics/<case>);
--cache-dir DIR uses a new solve (a folder written by simulate_plastic_ruler_coin.py).
Default output: renders/plastic_ruler_coin/rebuild/realism/<case>; --out-root DIR writes DIR/realism/<case>.
Blender 4.3.2 (tools/blender-4.3.2-linux-x64); --device gpu binds one GPU (CUDA_VISIBLE_DEVICES=--gpu-uuid),
--device cpu renders with --cpu-threads threads. All frames of one case must use the same device and settings.
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
from scene_paths import CASES, OUTPUT, blender_runtime, cache_dir, output_path

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--case", choices=CASES, default="source")
    p.add_argument("--cache-dir", type=Path, help="native solve folder (simulation.npz, simulation_config.json)")
    p.add_argument("--out-root", type=Path, default=OUTPUT)
    p.add_argument("--out", type=Path, help="exact output folder (overrides --out-root)")
    p.add_argument("--frames", type=int, nargs="+", help="1-based video frames (default: all 96)")
    p.add_argument("--samples", type=int, default=512)
    p.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    p.add_argument("--gpu-uuid", help="GPU to bind (CUDA_VISIBLE_DEVICES); inherited when omitted")
    p.add_argument("--cpu-threads", type=int, default=32)
    p.add_argument("--blender-bin", type=Path)
    p.add_argument("--save-scene", action="store_true", help="also save the built scene of the first frame")
    a = p.parse_args()
    source = (a.cache_dir or cache_dir(a.case)).resolve()
    if not (source / "simulation.npz").is_file() or not (source / "simulation_config.json").is_file():
        p.error(f"no native solve in {source}")
    out = output_path(a.out or a.out_root / "realism" / a.case)
    command = [str(blender_runtime(a.blender_bin)), "-b", "--factory-startup", "--python-exit-code", "1"]
    if a.device == "cpu":
        command += ["-t", str(a.cpu_threads)]
    command += ["--python", str(CASE / "appearance/realism.py"), "--", "--cache-dir", str(source), "--out", str(out),
                "--samples", str(a.samples), "--device", a.device, "--threads", str(a.cpu_threads)]
    if a.frames:
        command += ["--frames", *map(str, a.frames)]
    if a.save_scene:
        command.append("--save-scene")
    env = dict(os.environ)
    if a.device == "gpu" and a.gpu_uuid:
        env["CUDA_VISIBLE_DEVICES"] = a.gpu_uuid
    if a.device == "cpu":
        env["CUDA_VISIBLE_DEVICES"] = ""
    raise SystemExit(subprocess.run(command, env=env).returncode)
