"""Cradle suspension geometry shared by the solver and the renderer, SI units."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
def pivots(c):
    spacing=2*c['ball_radius']+c['ball_gap']
    return [[(i-2)*spacing,0,c['pivot_height']] for i in range(5)]
