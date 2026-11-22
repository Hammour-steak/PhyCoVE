"""Common camera: one fixed pitchside telephoto view shared by the source and every edit.

A fixed view instead of a pull-back/zoom (a moving camera read as camera shake). Eye, target,
lens and focus never change over the clip. The framing was chosen from the canonical caches of
the cases so every ball sample and the net envelope of every variant stay inside the 1280x720
frame; no source/edit trajectory drives the camera.
"""
import hashlib
from pathlib import Path

import numpy as np

RECIPE = {
    'eye_m': [18.0, -34.0, 2.5],
    'target_m': [-1.0, -2.0, 1.0],
    'lens_mm': 90.0,
    'sensor_width_mm': 36.0,
    'aperture_fstop': 5.6,
    'focus_point_m': [0.3, 0.8, 1.0],
    'static': True,
    'source_or_edit_trajectory_used': False,
    'shared_across_all_six': True,
}


def state(t, view='wide'):
    return np.array(RECIPE['eye_m']), np.array(RECIPE['target_m']), RECIPE['lens_mm']


def apply(bpy, scene, view, seconds):
    from mathutils import Vector
    data = bpy.data.cameras.new('common fixed pitchside telephoto camera')
    cam = bpy.data.objects.new(data.name, data)
    scene.collection.objects.link(cam)
    eye, target, lens = state(0.)
    cam.location = eye
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    data.lens = lens
    data.sensor_width = RECIPE['sensor_width_mm']
    data.clip_start = .02
    data.clip_end = 2000.
    data.dof.use_dof = True
    data.dof.aperture_fstop = RECIPE['aperture_fstop']
    data.dof.focus_distance = float(np.linalg.norm(np.array(RECIPE['focus_point_m']) - eye))
    scene.camera = cam
    scene.frame_set(1)
    bpy.context.view_layer.update()
    receipt = {'recipe': RECIPE, 'focus_distance_m': data.dof.focus_distance, 'animated': False,
               'actor_pose_or_physics_modified': False, 'requested_view_ignored': view}
    return cam, receipt
