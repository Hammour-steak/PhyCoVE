"""Package the approved Blender scene as a relocatable PCVE template."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy


argv = sys.argv[sys.argv.index("--") + 1 :]
target = Path(argv[0]).expanduser().resolve()
target.parent.mkdir(parents=True, exist_ok=True)

domains = []
for obj in bpy.data.objects:
    for modifier in obj.modifiers:
        if modifier.type == "FLUID" and modifier.domain_settings:
            domains.append(obj.name)

if domains != ["WineFluidDomain"]:
    raise RuntimeError(f"Unexpected fluid domains: {domains}")

bpy.context.scene["pcve_scene_id"] = "wine_pour"
bpy.context.scene["pcve_cache_policy"] = "isolated relative cache per output case"
bpy.ops.file.pack_all()
# Save first so Blender establishes the template's new base directory. Setting
# the // cache path before Save As would keep the original absolute target by
# rewriting it as a long relative path.
bpy.ops.wm.save_as_mainfile(filepath=str(target), check_existing=False)
for obj in bpy.data.objects:
    for modifier in obj.modifiers:
        if modifier.type == "FLUID" and modifier.domain_settings:
            modifier.domain_settings.cache_directory = "//fluid_cache"
bpy.ops.wm.save_as_mainfile(filepath=str(target), check_existing=False)
print(f"PCVE_TEMPLATE={target}")
