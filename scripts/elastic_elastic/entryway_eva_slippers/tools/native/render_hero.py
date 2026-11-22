"""Common-geometry rendering through the existing native replay renderer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mathutils import Vector

from common import INPUTS, read, save, sha
from vocab_hero import SPEC, SPEC_PATH, parameters
from hero_materials import apply_hero_finish
import render_replay as replay


def main(overlay=None):
    detail = "--detail-view" in sys.argv
    if detail:
        sys.argv.remove("--detail-view")
        if "--preview" not in sys.argv:
            raise ValueError("The product close-up is a diagnostic still view only")
    if "--cache" in sys.argv:
        cache = Path(sys.argv[sys.argv.index("--cache") + 1])
        config = read(cache.parent / "simulation_config.json")
        if config["geometry_file"] != SPEC["simulation"]["geometry"]:
            raise ValueError("A native cache of the production geometry is required")
    room_apply = replay.apply

    def apply(scene, spec):
        result = room_apply(scene, spec)
        if overlay is not None:
            overlay(scene)
        if detail:
            camera = scene.camera
            camera.location = (0.26, -0.43, 0.34)
            target = Vector((0.0, 0.005, 0.035))
            camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
            camera.data.lens = 58.0
            camera.data.dof.use_dof = False
            result.update(camera_location=list(camera.location), camera_rotation=list(camera.rotation_euler),
                          lens_mm=camera.data.lens, render_view="close_up_diagnostic")
        return result

    def record(path, value):
        if Path(path).name == "render_config.json":
            value.update(visual_revision="hero", hero_geometry_revision="production",
                         hero_material="Moulded EVA with a contoured heel cup, soft grip, smooth cuff borders and fine pores",
                         material_detail_max_bump_distance_m=0.00018,
                         size_mark_texture_sha256=sha(INPUTS / "assets/size_mark/size_42.png"),
                         diagnostic_close_up=detail)
        save(path, value)

    replay.SPEC = SPEC
    replay.SPEC_PATH = SPEC_PATH
    replay.parameters = parameters
    replay.apply_actor_finish = apply_hero_finish
    replay.apply = apply
    replay.save = record
    replay.main()


if __name__ == "__main__":
    main()
