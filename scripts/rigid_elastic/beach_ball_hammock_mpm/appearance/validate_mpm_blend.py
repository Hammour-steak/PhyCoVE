import json
import os
from pathlib import Path

import bpy


scene = bpy.context.scene
hammock = bpy.data.objects["Hammock_ElasticBody_ORIGINAL"]
ball = bpy.data.objects["BeachBall_RigidBody"]
work = Path(os.environ["PCVE_WORK_DIR"])
metrics = json.loads((work / os.environ["MPM_METRICS_NAME"]).read_text(encoding="utf-8"))
cloth_modifiers = [modifier.name for modifier in hammock.modifiers if modifier.type == "CLOTH"]
shape_keys = hammock.data.shape_keys

assert not cloth_modifiers, cloth_modifiers
assert ball.rigid_body is None
assert bool(scene["blender_cloth_used"]) is False
assert scene["physics_solver"] == "Taichi MLS-MPM fixed-corotated elasticity"
assert abs(scene["mpm_young_modulus_pa"] - metrics["young_modulus_pa"]) < 1.0e-6
assert abs(
    scene["mpm_young_modulus_after_pa"]
    - metrics.get("young_modulus_after_pa", metrics["young_modulus_pa"])
) < 1.0e-6
assert abs(scene["mpm_ball_mass_kg"] - metrics["ball_mass_kg"]) < 1.0e-6
assert abs(scene["mpm_pre_roll_seconds"] - metrics["pre_roll_seconds"]) < 1.0e-6
assert scene["mpm_contact_method"].startswith("Grid-node non-penetration")
assert len(shape_keys.key_blocks) == 97
assert scene.frame_start == 1 and scene.frame_end == 96

for frame in (1, 16, 24, 48, 72, 96):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    position = ball.matrix_world.translation
    assert all(abs(value) < 100.0 for value in position)
    print("VALID_FRAME", frame, tuple(round(value, 6) for value in position))

print("MPM_BLEND_VALID", len(shape_keys.key_blocks), scene["mpm_particle_count"])
