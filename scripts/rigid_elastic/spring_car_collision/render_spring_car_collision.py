"""Render one spring_car_collision case from its native MuJoCo solve in Blender 4.3 Cycles.

    python3 render_spring_car_collision.py --case source --out-root renders/spring_car_collision/<folder> \
        [--device optix|cuda|cpu] [--gpu-index N] [--frame-start 1 --frame-end 96 | --frames 1 30 60]

Writes <out-root>/<case>/frame_0001..0096.png, render_metadata.json (camera, settings,
asset and code hashes) and replay_audit.json (every keyed pose read back from the
evaluated scene against the solver cache). The solve is read from
assets/scenes/spring_car_collision/native_cases/<case>/ unless --cache names a
trajectory.npz with its scene_params.json. The look is appearance/look.py.
"""
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
import json
import os
import subprocess

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE_DIR))
import scene_config as cfg  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                allow_abbrev=False)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--case", choices=cfg.CASES, help="render the accepted native solve of this case")
    src.add_argument("--cache", type=Path, help="trajectory.npz of another solve (scene_params.json beside it)")
    p.add_argument("--out-root", type=Path, default=cfg.DEFAULT_RENDER_OUT)
    p.add_argument("--blender-bin", type=Path, help="Blender 4.3.2 (default: tools/blender-4.3.2-linux-x64, else $BLENDER/PATH)")
    p.add_argument("--device", choices=["optix", "cuda", "cpu"], default="optix")
    p.add_argument("--gpu-index", help="CUDA device index or UUID (sets CUDA_VISIBLE_DEVICES)")
    p.add_argument("--render-threads", type=int, default=16)
    p.add_argument("--samples", type=int, default=384)
    p.add_argument("--seed", type=int, default=17)
    p.add_argument("--frame-start", type=int, default=1)
    p.add_argument("--frame-end", type=int, default=cfg.FRAMES)
    p.add_argument("--frames", type=int, nargs="+", help="render only these frames (stills)")
    p.add_argument("--resume", action="store_true", help="skip frames that already exist")
    p.add_argument("--save-blend", action="store_true", help="also save the replay scene (unpacked)")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    a.blender_bin = a.blender_bin or cfg.blender()
    cache = (a.cache or cfg.native_case(a.case) / "trajectory.npz").resolve()
    case = a.case or cache.parent.name
    out = a.out_root.resolve() / case
    command = [str(a.blender_bin), "-b", "--factory-startup", "-t", str(a.render_threads), "--python-exit-code", "1",
               "--python", str(CASE_DIR / "appearance/render_native.py"), "--",
               "--cache", str(cache), "--case", case, "--out", str(out), "--device", a.device,
               "--samples", str(a.samples), "--seed", str(a.seed),
               "--frame-start", str(a.frame_start), "--frame-end", str(a.frame_end),
               "--asset-dir", str(cfg.asset_dir())]
    if a.frames:
        command += ["--frames", *map(str, a.frames)]
    if a.resume:
        command.append("--resume")
    if a.save_blend:
        command.append("--save-blend")
    env = dict(os.environ)
    if a.gpu_index is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(a.gpu_index)
    if a.dry_run:
        print(json.dumps({"command": command, "CUDA_VISIBLE_DEVICES": env.get("CUDA_VISIBLE_DEVICES")}, indent=2))
        return
    if not cache.is_file() or not (cache.parent / "scene_params.json").is_file():
        p.error(f"missing native solve: {cache} (+ scene_params.json)")
    out.mkdir(parents=True, exist_ok=True)
    raise SystemExit(subprocess.run(command, env=env).returncode)


if __name__ == "__main__":
    main()
