"""Render one case: the current look (appearance/realism.py) or the accepted renderer, both over the packed kitchen."""
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
from scene_paths import CASES, NATIVE, OUTPUT, TEMPLATE, blender_runtime, direct, launch, output_path

LOOKS = {"realism": "appearance/realism.py",          # current look
         "accepted": "appearance/render_counter.py"}  # renderer of the accepted delivery

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=CASES, default="source")
    p.add_argument("--look", choices=tuple(LOOKS), default="realism")
    p.add_argument("--source", type=Path, help="native case directory with simulation.npz "
                                               "(default: the accepted native state of --case)")
    p.add_argument("--out", type=Path, help="output directory (default renders/silicone_bag_can/rebuild/<look>/<case>)")
    p.add_argument("--template", type=Path, help="packed kitchen (default: assets scenes/silicone_bag_can/source_scene.blend)")
    p.add_argument("--frames", default="1-96", help="realism look: 'a-b' or a comma list")
    p.add_argument("--samples", type=int, help="realism default 256; accepted look 64")
    p.add_argument("--device", choices=("OPTIX", "CUDA", "CPU"), default="OPTIX", help="realism look")
    p.add_argument("--gpu-uuid", default="auto", help="claimed GPU index/UUID, or 'cpu' (realism); pool GPU (accepted)")
    p.add_argument("--cpu-threads", type=int, default=6)
    p.add_argument("--blender-bin", type=Path)
    a = p.parse_args()
    origin = a.source or NATIVE / a.case
    out = output_path(a.out or OUTPUT / a.look / a.case)
    template = a.template or TEMPLATE
    for path in (template, origin / "simulation.npz", origin / "simulation_config.json"):
        if not path.is_file():
            raise FileNotFoundError(path)
    blender = blender_runtime(a.blender_bin)
    if a.look == "realism":
        command = [blender, "-b", template, "--disable-autoexec", "-t", a.cpu_threads, "--python-exit-code", "1",
                   "--python", CASE / LOOKS[a.look], "--", "--case", a.case, "--source", origin, "--out", out,
                   "--frames", a.frames, "--device", a.device, *(["--samples", a.samples] if a.samples else [])]
        direct(command, "cpu" if a.device == "CPU" else a.gpu_uuid, a.cpu_threads)
    else:
        if (out / "render_report.json").exists():
            raise FileExistsError(out / "render_report.json")
        command = [blender, "-b", template, "--disable-autoexec", "-t", a.cpu_threads, "--python-exit-code", "1",
                   "--python", CASE / LOOKS[a.look], "--", "--source", origin, "--out", out, "--mode", "render",
                   "--width", "1280", "--samples", a.samples or 64]
        launch(command, a.gpu_uuid, a.cpu_threads)
