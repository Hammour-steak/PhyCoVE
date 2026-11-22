import json
import os

import bpy
import numpy as np


ROOT = os.environ.get("PCVE_SCENE_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORK_DIR = os.environ.get("PCVE_WORK_DIR", os.path.join(ROOT, "work"))
OUTPUT_DIR = os.environ.get("PCVE_OUTPUT_DIR", os.path.join(ROOT, "outputs"))
os.makedirs(OUTPUT_DIR, exist_ok=True)
CACHE = os.path.join(WORK_DIR, os.environ.get("MPM_CACHE_NAME", "mpm_flat_drop_final_cache.npz"))
METRICS = os.path.join(WORK_DIR, os.environ.get("MPM_METRICS_NAME", "mpm_flat_drop_final_metrics.json"))
OUTPUT = os.path.join(
    OUTPUT_DIR,
    os.environ.get("MPM_BLEND_OUTPUT_NAME", "beach_ball_hammock_mpm_flat_drop.blend"),
)
OUTPUT_METRICS = os.path.join(
    OUTPUT_DIR,
    os.environ.get("MPM_EXPERIMENT_OUTPUT_NAME", "mpm_flat_drop_experiment.json"),
)

cache = np.load(CACHE)
surface_frames = cache["surface_frames"]
ball_frames = cache["ball_frames"]
with open(METRICS, "r", encoding="utf-8") as handle:
    metrics = json.load(handle)

scene = bpy.context.scene
hammock = bpy.data.objects["Hammock_ElasticBody_ORIGINAL"]
ball = bpy.data.objects["BeachBall_RigidBody"]

# Remove every Blender dynamics component from the two simulated objects.
for modifier in list(hammock.modifiers):
    if modifier.type == "CLOTH":
        hammock.modifiers.remove(modifier)
for modifier in list(ball.modifiers):
    if modifier.type == "COLLISION":
        ball.modifiers.remove(modifier)

bpy.context.view_layer.objects.active = ball
ball.select_set(True)
try:
    bpy.ops.rigidbody.object_remove()
except RuntimeError:
    pass
ball.select_set(False)

proxy = bpy.data.objects.get("Hammock_RigidSupport_PROXY")
if proxy:
    proxy.hide_render = True
    proxy.hide_viewport = True

# The cache contains world-space surface vertices. Store them as shape keys in
# the original textured mesh so the authored UVs and material remain untouched.
if hammock.data.shape_keys:
    bpy.context.view_layer.objects.active = hammock
    hammock.select_set(True)
    bpy.ops.object.shape_key_remove(all=True)
    hammock.select_set(False)

inverse = np.asarray(hammock.matrix_world.inverted(), dtype=np.float64)
hammock.shape_key_add(name="MPM_Basis", from_mix=False)
for frame_index, world_vertices in enumerate(surface_frames, start=1):
    key = hammock.shape_key_add(name=f"MPM_{frame_index:04d}", from_mix=False)
    homogeneous = np.concatenate(
        [world_vertices.astype(np.float64), np.ones((len(world_vertices), 1), dtype=np.float64)],
        axis=1,
    )
    local_vertices = (inverse @ homogeneous.T).T[:, :3]
    for vertex_index, coordinate in enumerate(local_vertices):
        key.data[vertex_index].co = coordinate
    if frame_index > 1:
        key.value = 0.0
        key.keyframe_insert(data_path="value", frame=frame_index - 1)
    key.value = 1.0
    key.keyframe_insert(data_path="value", frame=frame_index)
    if frame_index < len(surface_frames):
        key.value = 0.0
        key.keyframe_insert(data_path="value", frame=frame_index + 1)
    key.value = 0.0

shape_animation = hammock.data.shape_keys.animation_data
if shape_animation and shape_animation.action:
    for fcurve in shape_animation.action.fcurves:
        for point in fcurve.keyframe_points:
            point.interpolation = "LINEAR"

if ball.animation_data:
    ball.animation_data_clear()
for frame_index, position in enumerate(ball_frames, start=1):
    ball.location = tuple(float(value) for value in position)
    ball.keyframe_insert(data_path="location", frame=frame_index)
if ball.animation_data and ball.animation_data.action:
    for fcurve in ball.animation_data.action.fcurves:
        for point in fcurve.keyframe_points:
            point.interpolation = "LINEAR"

scene.frame_start = 1
scene.frame_end = len(surface_frames)
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.fps = 24
scene["physics_solver"] = "Taichi MLS-MPM fixed-corotated elasticity"
scene["blender_cloth_used"] = False
scene["mpm_young_modulus_pa"] = metrics["young_modulus_pa"]
scene["mpm_young_modulus_after_pa"] = metrics.get(
    "young_modulus_after_pa", metrics["young_modulus_pa"]
)
scene["mpm_young_modulus_change_time_s"] = metrics.get("young_modulus_change_time_s") or -1.0
scene["mpm_poisson_ratio"] = metrics["poisson_ratio"]
scene["mpm_hammock_density_kg_m3"] = metrics["density_kg_m3"]
scene["mpm_hammock_mass_kg"] = metrics["hammock_mass_kg"]
scene["mpm_numerical_thickness_m"] = metrics["thickness_m"]
scene["mpm_ball_mass_kg"] = metrics["ball_mass_kg"]
scene["mpm_ball_initial_velocity_m_s"] = metrics["ball_initial_velocity_m_s"]
scene["mpm_grid_resolution"] = metrics["grid_resolution"]
scene["mpm_substeps_per_frame"] = metrics["substeps_per_frame"]
scene["mpm_particle_count"] = metrics["particle_count"]
scene["mpm_pre_roll_seconds"] = metrics["pre_roll_seconds"]
lateral_locked = bool(metrics.get("ball_lateral_translation_locked", True))
feedback_dimension = "vertical" if lateral_locked else "full 3D"
scene["mpm_contact_method"] = (
    f"Grid-node non-penetration with {feedback_dimension} rigid-sphere impulse feedback"
)
scene["mpm_ball_lateral_translation_locked"] = lateral_locked
scene["mpm_ball_start_xy_m"] = metrics.get("ball_start_xy_m", [])
scene["physics_note"] = (
    "Hammock deformation and sphere impulses were solved externally in one Taichi MLS-MPM loop; "
    "Blender stores and renders the resulting mesh and rigid-sphere trajectories."
)
scene.frame_set(1)

metrics["blend_file"] = os.path.basename(OUTPUT)
metrics["blender_cloth_used"] = False
metrics["coupling"] = (
    f"two-way MPM grid-node contact with rigid-sphere {feedback_dimension} impulse feedback"
)
with open(OUTPUT_METRICS, "w", encoding="utf-8") as handle:
    json.dump(metrics, handle, ensure_ascii=False, indent=2)

bpy.ops.wm.save_as_mainfile(filepath=OUTPUT)
print("MPM_BLEND_READY", OUTPUT)
print("MPM_METRICS_READY", OUTPUT_METRICS)
