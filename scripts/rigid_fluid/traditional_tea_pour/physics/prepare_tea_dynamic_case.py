"""Make independent simulation inputs; source particle and surface caches stay intact."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("source", type=Path)
p.add_argument("target", type=Path)
p.add_argument("--coaster", type=Path)
a = p.parse_args()
source, target = a.source.resolve(), a.target.resolve()
target.mkdir(exist_ok=False, parents=True)
files = ("input_config.json", "acceptance_plan.json", "cup_collider.obj", "visible_solid_closed.obj",
         "audit_cavity_closed.obj", "actual_inner_open.obj", "actual_inner_open.npz",
         "visual_cup_world.npz", "collider_repair.json")
if (source/'render_reference.blend').exists():
    files=files+("render_reference.blend",)
for name in files:
    shutil.copy2(source / name, target / name)
if a.coaster:
    shutil.copy2(a.coaster, target / "coaster_world.obj")
manifest = {"source": str(source), "target": str(target),
            "copied_inputs_sha256": {name: hashlib.sha256((target/name).read_bytes()).hexdigest() for name in files},
            "fresh_particle_cache": True, "original_source_particles": str(source / "particles")}
(target / "input_provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest), flush=True)
