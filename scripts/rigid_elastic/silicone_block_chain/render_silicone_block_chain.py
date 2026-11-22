"""Render one case: the realism look (overlay on the accepted packed scene, default) or the delivered look (bake the native cache into the workshop model on a leased pool GPU).

With --native-dir DIR (a physics/physics.py output: simulation.npz and config.json) the realism look renders that
solve instead of an accepted case: the two files are copied to <out>/native/, appearance/bake_native.py bakes them
into the workshop template (<out>/native/packed.blend, bake_report.json) and appearance/realism.py renders the bake.
Timed edits and the re-solved source of the published suite (cases/<case_id>/native_metadata) are rendered this way."""
from pathlib import Path
import sys

# PCVE_UNIFIED_ENTRY_BEGIN
CASE = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE.parents[1]))
if __name__ == "__main__":
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "render")
# PCVE_UNIFIED_ENTRY_END

import argparse
import json
import os
import shutil
import subprocess

from edit_vocab import CASE_DSL, TIMED_DSL
from scene_paths import OUTPUT, blender_runtime, output_path, packed

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=[*CASE_DSL, *TIMED_DSL], default="source")
    p.add_argument("--look", choices=("realism", "delivered"), default="realism")
    p.add_argument("--out-root", type=Path, default=OUTPUT, help="writes <root>/<look>/<case>; default renders/silicone_block_chain/rebuild")
    p.add_argument("--out", type=Path, help="explicit case directory (overrides --out-root)")
    p.add_argument("--frames", default="1-96", help="realism look: 'a-b' or a comma list; the video needs 1-96")
    p.add_argument("--gpu-uuid", help="realism: bind this GPU (CUDA_VISIBLE_DEVICES); delivered: lease this pool GPU")
    p.add_argument("--cpu-threads", type=int, default=8)
    p.add_argument("--samples", type=int)
    p.add_argument("--device", choices=("OPTIX", "CUDA", "CPU"), default="OPTIX", help="realism look only")
    p.add_argument("--blender-bin", type=Path)
    p.add_argument("--native-dir", type=Path, help="realism look: render this solve (simulation.npz, config.json) through "
                   "appearance/bake_native.py instead of the accepted case; required for timed cases")
    a = p.parse_args()
    if a.case in TIMED_DSL and a.native_dir is None:
        p.error("a timed case is rendered from its solve: pass --native-dir (simulate output or the suite case's native_metadata)")
    if a.native_dir is not None and a.look != "realism":
        p.error("--native-dir renders the realism look")
    out = output_path(a.out or a.out_root / a.look / a.case)
    if out.exists():
        raise FileExistsError(out)
    if a.look == "delivered":
        command = [sys.executable, "-B", str(CASE / "tools/worker.py"), "--case", a.case, "--out", str(out),
                   "--threads", str(a.cpu_threads), *(["--samples", str(a.samples)] if a.samples else []),
                   *(["--gpu-uuid", a.gpu_uuid] if a.gpu_uuid else [])]
        subprocess.run(command, check=True)
    else:
        env = dict(os.environ)
        if a.device == "CPU":
            env["CUDA_VISIBLE_DEVICES"] = ""
        elif a.gpu_uuid:
            env["CUDA_VISIBLE_DEVICES"] = a.gpu_uuid
        scene, native = str(packed(a.case)), []
        if a.native_dir is not None:
            source = a.native_dir.resolve()
            config = json.loads((source / "config.json").read_text(encoding="utf-8"))
            if config["case"] != a.case:
                p.error(f"{source} holds the solve of {config['case']}, not {a.case}")
            work = out / "native"
            work.mkdir(parents=True)
            for name in ("simulation.npz", "config.json"):
                shutil.copy2(source / name, work / name)
            bake = [str(blender_runtime(a.blender_bin)), "-b", "-t", str(a.cpu_threads), "--python-exit-code", "1",
                    "--python", str(CASE / "appearance/bake_native.py"), "--", "--case", a.case, "--native-dir", str(work)]
            subprocess.run(bake, env=dict(os.environ, CUDA_VISIBLE_DEVICES=""), check=True)
            scene, native = str(work / "packed.blend"), ["--native-dir", str(work)]
        command = [str(blender_runtime(a.blender_bin)), "-b", scene, "-t", str(a.cpu_threads),
                   "--python-exit-code", "1", "--python", str(CASE / "appearance/realism.py"), "--",
                   "--case", a.case, *native, "--out", str(out), "--frames", a.frames, "--device", a.device,
                   *(["--video"] if a.frames == "1-96" else []), *(["--samples", str(a.samples)] if a.samples else [])]
        subprocess.run(command, env=env, check=True)
