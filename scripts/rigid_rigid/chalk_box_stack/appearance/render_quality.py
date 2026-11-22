"""The same engine/device interface used by the other scene renderers."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

import sys
sys.path.insert(0, str(_PCVE_ROOT / 'scripts'))
from pcve_blender_compat import (eevee_engine, set_color_property)
def configure_renderer(bpy,scene,args):
    scene.render.engine='CYCLES' if args.engine=='cycles' else eevee_engine()
    scene.render.threads_mode='FIXED';scene.render.threads=4
    # A 180-degree shutter, the video default: a 2.8 m/s eraser smears by about
    # six centimetres per frame, as it does on any real camera.
    scene.render.use_motion_blur=True;scene.render.motion_blur_shutter=.5
    if args.engine=='cycles':
        scene.cycles.samples=args.samples;scene.cycles.use_denoising=True
        scene.cycles.use_adaptive_sampling=True;scene.cycles.adaptive_threshold=.015
        scene.cycles.adaptive_min_samples=min(16,args.samples)
        scene.cycles.max_bounces=8;scene.cycles.diffuse_bounces=4;scene.cycles.glossy_bounces=4
        # Most of the room is lit by bounce from the ceiling panels and the
        # windows; caustics off the bottle and varnish only add fireflies.
        scene.cycles.caustics_reflective=False;scene.cycles.caustics_refractive=False
        scene.cycles.sample_clamp_indirect=8.
        scene.render.use_persistent_data=True;scene.cycles.device='CPU'
        if args.device=='auto':
            try:
                prefs=bpy.context.preferences.addons['cycles'].preferences
                prefs.compute_device_type='CUDA';prefs.get_devices()
                available=[d for d in prefs.devices if d.type=='CUDA']
                for d in prefs.devices:d.use=d.type=='CUDA'
                if available:scene.cycles.device='GPU'
            except Exception:scene.cycles.device='CPU'
        return scene.cycles.device
    return 'GPU'

def configure_color(scene):
    set_color_property(scene.view_settings, 'view_transform', 'AgX')
    set_color_property(scene.view_settings, 'look', 'AgX - Base Contrast')
    scene.view_settings.exposure=EXPOSURE


# Exposed for the bench under the classroom's own lights (see configure_lighting).
EXPOSURE=0.
