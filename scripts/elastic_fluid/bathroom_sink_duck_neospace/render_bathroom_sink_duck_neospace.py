"""Render the Genesis coupled run in the bathroom room with the scene look.

The built scene supplies room, camera, duck object and materials. Per frame the Genesis water mesh (with a
`velocity` attribute, so Cycles motion-blurs it) and the skinned duck are swapped in. Water faces lying within
FILM_ZONE_M of the basin floor use the look's shadow-transparent film material.
    blender -b --python render_bathroom_sink_duck_neospace.py -- --scene work/scene.blend \
        --surfaces surfaces --output-dir output
(surfaces from surface_bathroom_sink_duck_neospace.py)
"""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'render')
# PCVE_UNIFIED_ENTRY_END

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from look_bathroom_sink_duck_neospace import BASIN_FLOOR_Z, WATER_MATERIAL, apply_look, film_water  # noqa: E402

FILM_ZONE_M = 0.003


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--surfaces", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--frames", type=str, default="", help="e.g. 1-96 or 4,7 (default: all)")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])


def main():
    import bpy
    import numpy as np

    args = parse_args()
    surfaces = args.surfaces.expanduser().resolve()
    output = args.output_dir.expanduser().resolve()
    (output / "frames").mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.expanduser().resolve()))
    scene = bpy.context.scene
    apply_look(scene)
    duck = bpy.data.objects["ElasticRubberDuck"]
    has_duck = (surfaces / "duck_visual.npz").exists()      # absent when the duck is deleted
    if has_duck:
        duck_motion = np.load(surfaces / "duck_visual.npz")
        duck_index = {int(f): i for i, f in enumerate(duck_motion["frames"])}
        to_local = np.array(duck.matrix_world.inverted())
    else:
        duck.hide_render = True

    water = bpy.data.materials[WATER_MATERIAL]
    film = film_water()
    water_object = bpy.data.objects.new("GenesisWater", bpy.data.meshes.new("GenesisWater"))
    scene.collection.objects.link(water_object)

    if args.frames:
        if "-" in args.frames:
            first, last = (int(x) for x in args.frames.split("-"))
            frames = list(range(first, last + 1))
        else:
            frames = [int(x) for x in args.frames.split(",")]
    else:
        frames = sorted(int(path.stem.split("_")[1]) for path in surfaces.glob("water_*.npz"))
    scene.render.image_settings.file_format = "PNG"
    started = time.monotonic()
    for frame in frames:
        scene.frame_set(frame)
        if has_duck:
            world = duck_motion["vertices"][duck_index[frame]].astype(np.float64)
            local = (np.c_[world, np.ones(len(world))] @ to_local.T)[:, :3]
            duck.data.vertices.foreach_set("co", local.astype(np.float32).ravel())
            duck.data.update()

        data = np.load(surfaces / f"water_{frame:04d}.npz")
        mesh = bpy.data.meshes.new(f"GenesisWater{frame:04d}")
        mesh.from_pydata(data["vertices"].tolist(), [], data["triangles"].tolist())
        mesh.materials.append(water)
        mesh.materials.append(film)
        centres = np.zeros(len(mesh.polygons) * 3, dtype=np.float32)
        mesh.polygons.foreach_get("center", centres)
        mesh.polygons.foreach_set("material_index", (centres.reshape(-1, 3)[:, 2] < BASIN_FLOOR_Z + FILM_ZONE_M).astype(np.int32))
        mesh.polygons.foreach_set("use_smooth", np.ones(len(mesh.polygons), dtype=bool))
        velocity = mesh.attributes.new("velocity", "FLOAT_VECTOR", "POINT")
        velocity.data.foreach_set("vector", data["velocity"].ravel())
        previous = water_object.data
        water_object.data = mesh
        bpy.data.meshes.remove(previous)

        scene.render.filepath = str(output / "frames" / f"frame_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
        print(f"PCVE_GENESIS_FRAME={frame}", flush=True)
    seconds = time.monotonic() - started

    report = {"look": scene["pcve_look"], "frames": len(frames), "render_seconds": seconds, "samples": scene.cycles.samples}
    if not args.frames:
        video = output / "video.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-framerate", str(scene.render.fps), "-start_number", str(frames[0]),
                        "-i", str(output / "frames" / "frame_%04d.png"), "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                        str(video)], check=True)
        report["video"] = str(video)
    (output / "render_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"PCVE_GENESIS_RENDER_SECONDS={seconds:.1f}", flush=True)


if __name__ == "__main__":
    main()
