"""Render one case from its native state: the current look (appearance/realism.py) or the accepted renderer."""
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
from scene_paths import CASES, NATIVE, OUTPUT, blender_runtime, direct, output_path, pool, worker_only

LOOKS = {"realism": "appearance/realism.py",          # current look, built from the native cache
         "accepted": "appearance/render_replay.py"}   # renderer of the accepted delivery

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=CASES, default="source")
    p.add_argument("--look", choices=tuple(LOOKS), default="realism")
    p.add_argument("--out", type=Path, help="output directory (default renders/scarf_chair_slip/rebuild/<case>/<look>)")
    p.add_argument("--frames", default="1-96", help="'a-b' or a comma list")
    p.add_argument("--samples", type=int)
    p.add_argument("--device", choices=("OPTIX", "CUDA", "CPU"), default="OPTIX")
    p.add_argument("--cache", type=Path, help="native case folder or cache.npz (default: the accepted native state)")
    p.add_argument("--gpu-uuid", default="auto", help="claimed GPU index/UUID, or 'cpu'")
    p.add_argument("--cpu-threads", type=int, default=6)
    p.add_argument("--blender-bin", type=Path)
    a = p.parse_args()
    worker_only()
    out = output_path(a.out or OUTPUT / a.case / a.look)
    blender = blender_runtime(a.blender_bin)
    native = a.cache or NATIVE / a.case
    native = native.parent if native.suffix == ".npz" else native
    if not (native / "cache.npz").is_file():
        raise FileNotFoundError(native / "cache.npz")
    if a.look == "realism":
        command = [blender, "-b", "--factory-startup", "--disable-autoexec", "-t", a.cpu_threads,
                   "--python-exit-code", "1", "--python", CASE / LOOKS[a.look], "--",
                   "--case", a.case, "--native", native, "--out", out, "--frames", a.frames, "--device", a.device,
                   *(["--samples", a.samples] if a.samples else [])]
        direct(command, "cpu" if a.device == "CPU" else a.gpu_uuid, a.cpu_threads)
    else:
        if a.frames != "1-96":
            raise SystemExit("--look accepted renders all 96 frames (its --stills mode is for checks only)")
        args = ["--simulation", native, "--out", out, "--width", "1280", "--backend", a.device,
                "--samples", a.samples or 192]
        if str(a.gpu_uuid) == "auto":   # no claimed GPU: the lease launcher picks one
            pool("blender", LOOKS[a.look], args, a.gpu_uuid, a.cpu_threads, a.blender_bin)
        else:
            direct([blender, "-b", "--factory-startup", "--disable-autoexec", "-t", a.cpu_threads,
                    "--python-exit-code", "1", "--python", CASE / LOOKS[a.look], "--", *args],
                   "cpu" if a.device == "CPU" else a.gpu_uuid, a.cpu_threads)
