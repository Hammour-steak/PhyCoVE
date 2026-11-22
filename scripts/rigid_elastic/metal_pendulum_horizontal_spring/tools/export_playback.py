"""Export a Blender playback file from the solved cache, with no dynamic re-solve."""

import argparse
import json
import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import bpy
import numpy as np

from appearance.renderer import setup


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    c = json.loads((a.run / "actual_config.json").read_text())
    d = np.load(a.run / "trajectory.npz")
    sc, pivot, post, devices = setup(c, d)
    for k, angle in enumerate(d["theta"]):
        pivot.rotation_euler = (0, -float(angle), 0)
        pivot.keyframe_insert(data_path="rotation_euler", frame=k + 1)
    head = bpy.data.objects.get("Native guided compression pose")
    if head:
        for k, x in enumerate(d["compression"]):
            head.location.x = float(x)
            head.keyframe_insert(data_path="location", frame=k + 1)
        for fc in head.animation_data.action.fcurves:
            for key in fc.keyframe_points:
                key.interpolation = "LINEAR"
    for fc in pivot.animation_data.action.fcurves:
        for key in fc.keyframe_points:
            key.interpolation = "LINEAR"
    if post:
        post.shape_key_add(name="Solved reference at t=0")
        post.data.shape_keys.use_relative = False
        for k, coords in enumerate(d["spring_vertices"]):
            key = post.shape_key_add(name=f"Solved t={k/24:.6f}s")
            key.data.foreach_set("co", coords.ravel())
            post.data.shape_keys.eval_time = key.frame
            post.data.shape_keys.keyframe_insert(data_path="eval_time", frame=k + 1)
        for fc in post.data.shape_keys.animation_data.action.fcurves:
            for key in fc.keyframe_points:
                key.interpolation = "LINEAR"
    sc.frame_set(1)
    sc["cache_source"] = str((a.run / "trajectory.npz").resolve())
    sc["physics"] = (
        "Playback of native integrated hinge and guided horizontal axial spring mode."
    )
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(a.run / "scene.blend"))


if __name__ == "__main__":
    main()
