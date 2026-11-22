"""Replay native states in Blender 4.3.2 and render one case (frames, video, receipts).

Native options: --case CASE (a CASE_DSL or timed TIMED_DSL case) --tag NAME --cache-root DIR --out-root DIR --frames all|i,j,k
--samples N --width PX --device GPU|CPU --backend OPTIX|CUDA --save-blend --grounding-audit
--assemble-only --blender-bin PATH --gpu-uuid UUID --render-threads N.
The default cache is the accepted native states in assets/scenes/metro_security_bag_curtain/native;
the default output is renders/metro_security_bag_curtain/rebuild_<UTC stamp>/render.
"""

from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[2]
# PCVE_UNIFIED_ENTRY_BEGIN
sys.path.insert(0, str(SCRIPTS))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, 'render')
# PCVE_UNIFIED_ENTRY_END

import argparse
import os
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edit_vocab import CASE_DSL, TIMED_DSL
from pcve_assets import blender
from scene_paths import CASE, NATIVE, REPO, default_rebuild_root, output_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", choices=(*CASE_DSL, *TIMED_DSL), default="source")
    parser.add_argument("--tag", default=NATIVE.name, help="native state set under assets native/")
    parser.add_argument("--cache-root", type=Path, help="directory holding <case>/states.npz")
    parser.add_argument("--out-root", type=Path)
    parser.add_argument("--frames", default="all")
    parser.add_argument("--samples", type=int, default=384)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--device", choices=("GPU", "CPU"), default="GPU")
    parser.add_argument("--backend", choices=("OPTIX", "CUDA"), default="OPTIX")
    parser.add_argument("--save-blend", action="store_true")
    parser.add_argument("--grounding-audit", action="store_true")
    parser.add_argument("--assemble-only", action="store_true")
    parser.add_argument("--blender-bin", type=Path)
    parser.add_argument("--gpu-uuid", help="sets CUDA_VISIBLE_DEVICES for the Blender process")
    parser.add_argument("--render-threads", type=int, default=8)
    args = parser.parse_args()
    out = output_path(args.out_root or default_rebuild_root() / "render")
    if (out / args.case).exists():
        parser.error("Choose a fresh render output directory")
    cache = (args.cache_root or NATIVE.parent / args.tag).resolve()
    if not all((cache / args.case / name).is_file() for name in ("states.npz", "simulation_config.json")):
        parser.error("The matching native states.npz and simulation_config.json are required")
    runtime = args.blender_bin
    if runtime is None:
        pinned = REPO / "tools/blender-4.3.2-linux-x64/blender"
        runtime = pinned if pinned.is_file() else blender()
    native = ["--case", args.case, "--cache-root", str(cache), "--out-root", str(out), "--tag", args.tag,
              "--out-tag", "final", "--frames", args.frames, "--width", str(args.width),
              "--samples", str(args.samples), "--backend", args.backend, "--device", args.device]
    if args.save_blend:
        native.append("--save-blend")
    if args.grounding_audit:
        native.append("--grounding-audit")
    if args.assemble_only:
        native.append("--assemble-only")
    env = dict(os.environ, OMP_NUM_THREADS=str(args.render_threads))
    if args.gpu_uuid:
        env["CUDA_VISIBLE_DEVICES"] = args.gpu_uuid
    if args.assemble_only or args.device == "CPU":
        env["CUDA_VISIBLE_DEVICES"] = "-1"
    command = [str(runtime), "-b", "-t", str(args.render_threads), "--factory-startup",
               "--python-exit-code", "1", "--python", str(CASE / "appearance" / "render_scene.py"), "--", *native]
    subprocess.run(command, check=True, env=env)


if __name__ == "__main__":
    main()
