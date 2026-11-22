"""Bake a native cache that is not part of the accepted delivery into the workshop template and audit it.

The bake and the saved-scene audit are those of `appearance/scene.py` (the delivered look), imported as a module;
only its render is not used.
`appearance/realism.py --native-dir DIR` then renders the result with the current look.

    <blender> -b --python-exit-code 1 --python bake_native.py -- --case CASE --native-dir DIR [--template workshop_template/packed/source.blend]

DIR/simulation.npz and DIR/config.json (physics/physics.py output) in; DIR/packed.blend and DIR/bake_report.json out.
"""
from pathlib import Path
import argparse
import json
import sys

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(HERE), str(HERE.parent), str(HERE.parent / "physics"), str(ROOT / "scripts")]
import pcve_realism_kit as kit
from pcve_assets import asset

import scene as delivered  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", required=True)
    p.add_argument("--native-dir", type=Path, required=True)
    p.add_argument("--template", type=Path, default=None)
    a = p.parse_args(argv)
    d = a.native_dir.resolve()
    cache_path, cfg = d / "simulation.npz", json.loads((d / "config.json").read_text(encoding="utf-8"))
    if cfg["case"] != a.case or cfg["cache_sha256"] != kit.sha256(cache_path):
        raise RuntimeError("native directory does not hold this case's cache")
    template = a.template or asset("scenes/silicone_block_chain/workshop_template/packed/source.blend")
    with np.load(cache_path) as native:
        cache = dict(native)
    indices = np.arange(96) * 4
    delivered.require_times(cache["times"][indices])
    bpy.ops.wm.open_mainfile(filepath=str(template))
    delivered.bake(cache, cfg, indices)
    model = d / "packed.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(model))
    bpy.ops.wm.open_mainfile(filepath=str(model))
    audit = delivered.audit_saved(cache, cfg, indices)
    report = {"case": a.case, "native_cache_sha256": cfg["cache_sha256"], "template_sha256": kit.sha256(template),
              "packed_scene": model.name, "packed_scene_sha256": kit.sha256(model), "baker": "appearance/scene.py bake + audit_saved",
              "blender": bpy.app.version_string,
              "physical_times_s": cache["times"][indices].tolist(), "saved_scene_audit": audit}
    (d / "bake_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("BAKE_NATIVE_OK", a.case, report["packed_scene_sha256"], flush=True)


main()
