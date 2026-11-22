"""Blender 4.3.2 / Cycles replay of one case's accepted native states with the current look (appearance/realism.py).

The native states are taken from the accepted increment (extracted once into .runtime/rubber_band_wood_slider/native/).
Frames 0001.png ... 0096.png show t = (frame - 1) / 24 s; with all 96 frames and ffmpeg available the case video is
encoded into the same folder (otherwise encode later with build_pcve_rubber_band_wood_slider.py --stage encode).
Output must be a fresh folder outside scripts/ (default renders/rubber_band_wood_slider/rebuild_<UTC>/render/<case>).
"""
from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
CASE = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE.parents[1]))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "render")
# PCVE_UNIFIED_ENTRY_END

sys.path.insert(0, str(CASE))
import argparse
from scene_paths import CASES, RENDERS, blender_runtime, launch, native_case, output_path, stamp

LOOK = CASE / "appearance/realism.py"


def frames(value):
    result = []
    for part in value.split(","):
        a, _, b = part.partition("-")
        result += list(range(int(a), int(b or a) + 1))
    if not result or min(result) < 1 or max(result) > 96:
        raise argparse.ArgumentTypeError("frames are 1..96, e.g. 1,31,96 or 1-96")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--case", choices=CASES, default="source")
    p.add_argument("--out", type=Path, help="fresh output folder (default renders/rubber_band_wood_slider/rebuild_<UTC>/render/<case>)")
    p.add_argument("--frames", type=frames, help="1-based frames, e.g. 1,31,96 (default: all 96)")
    p.add_argument("--samples", type=int, default=256)
    p.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    p.add_argument("--gpu-uuid", default="auto", help="GPU index or UUID on this host (checked idle); 'auto' = first idle")
    p.add_argument("--render-threads", type=int, default=8)
    p.add_argument("--blender-bin", type=Path)
    p.add_argument("--revision", default="look_review", help="label recorded in the provenance (must end in _review)")
    p.add_argument("--save-blend", action="store_true")
    p.add_argument("--no-encode", action="store_true")
    a = p.parse_args()
    out = output_path(a.out or RENDERS / f"rebuild_{stamp()}" / "render" / a.case)
    if out.exists() and any(out.iterdir()):
        p.error("Choose a fresh output folder")
    native = native_case(a.case)
    command = [blender_runtime(a.blender_bin), "-b", "-t", str(a.render_threads), "--python-exit-code", "1",
               "--python", LOOK, "--", "--case", a.case, "--input", native, "--audit", native / "capture_start_audit.json",
               "--out", out, "--samples", str(a.samples), "--review-candidate", "--revision", a.revision]
    if a.frames:
        command += ["--frames", *map(str, a.frames)]
    if a.device == "cpu":
        command += ["--cpu"]
    if a.save_blend:
        command += ["--save-blend"]
    code = launch(command, a.gpu_uuid, a.render_threads, cpu=a.device == "cpu")
    if code == 0 and not a.no_encode and (a.frames is None or len(a.frames) == 96):
        import subprocess
        code = subprocess.run([sys.executable, str(CASE / "tools/publish_suite.py"), "encode", str(out)]).returncode
    raise SystemExit(code)
