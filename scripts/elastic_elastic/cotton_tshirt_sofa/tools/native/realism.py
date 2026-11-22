"""Appearance overlay of the published videos: the T-shirt-on-sofa living room with soft afternoon sun.

`render.main` runs with one hook (`overlay`) right after the room and
photographic finish are built, so the native shirt/seat states,
the shutter sidecar, the camera and every edit stay those of render.py. Only
lights and room materials change.

    CUDA_VISIBLE_DEVICES=<uuid> blender -b --python-exit-code 1 --python realism.py -- \
        --case source --cache <suite>/cases/source/deformation.npz --out OUT [--frames 50] [--samples 64]
"""
from pathlib import Path
import os
import sys

HERE = Path(__file__).resolve().parent            # .../cotton_tshirt_sofa/tools/native
sys.path[:0] = [str(HERE), str(HERE.parents[1]), str(HERE.parents[3])]
import pcve_realism_kit as kit


def probe(scene):
    for o in scene.objects:
        if o.type == "LIGHT":
            print("LIGHT", o.name, o.data.type, round(o.data.energy, 2), tuple(round(v, 2) for v in o.location))
    print("WORLD", scene.world and [(n.bl_idname, n.inputs[1].default_value if n.bl_idname == "ShaderNodeBackground" else "") for n in scene.world.node_tree.nodes])
    for o in scene.objects:
        if o.type == "MESH" and not o.hide_render:
            lo, hi = kit.world_bbox([o])
            print("OBJ", o.name[:45], [round(v, 2) for v in lo], [round(v, 2) for v in hi],
                  [s.material.name[:35] for s in o.material_slots if s.material][:2])
    raise SystemExit(0)


def __overlay__(scene):
    import bpy
    if os.environ.get("REALISM_PROBE"):
        probe(scene)
    objs, mats = bpy.data.objects, bpy.data.materials
    # Low afternoon sun from the left window, raking across the sofa; curtain and panes pass it (shadow linking).
    sun = kit.sun("Afternoon sun through linen curtain", (.70, -.45, -.55), float(os.environ.get("REALISM_SUN", "9.0")),
                  angle_deg=float(os.environ.get("REALISM_SUN_ANGLE", "3.5")), color=(1.0, .90, .76))
    skip = bpy.data.collections.new("Sun passes through")
    for o in scene.objects:
        if o.name.startswith(("Gathered linen curtain", "Hem sewn along curtain folds", "Transparent window panes")):
            skip.objects.link(o)
    sun.light_linking.blocker_collection = skip
    for item in skip.collection_objects:
        item.light_linking.link_state = "EXCLUDE"
    for o in scene.objects:
        if o.type == "LIGHT" and o.data.type == "AREA":
            o.data.energy *= float(os.environ.get("REALISM_FILL", ".45"))
    kit.add_surface_wear(mats["Scanned oak floor, satin finish"], smudge=.14, grime=.10, scratch=.08, scale=1.0)
    kit.add_wall_mottling(mats["Warm chalk plaster"], .05)
    kit.add_surface_wear(mats["Warm greige looped wool rug"], smudge=.08, grime=.12, scratch=0.0, scale=.6)
    kit.add_surface_wear(mats["Window painted timber"], smudge=.08, grime=.10, scratch=.04, scale=.3)
    scene.view_settings.exposure += float(os.environ.get("REALISM_EXPOSURE_DELTA", "0"))
    if os.environ.get("REALISM_DEBUG") == "sun":
        scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0
        for o in scene.objects:
            if o.type == "LIGHT" and o.data.type != "SUN":
                o.data.energy = 0


import render
render.main(overlay=__overlay__)
