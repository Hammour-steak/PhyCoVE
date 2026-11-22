"""Mid-century home study look: the facade the renderer calls.

The room and the desk are built in study_room.py, the cradle in
cradle_model.py and the scanned desk and sideboard pieces in desk_props.py.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

from pcve_assets import asset as _pcve_asset
ASSETS=_pcve_asset('')/'polyhaven'/'newtons_cradle'


ENVIRONMENT_THEME='mid_century_study'
# The look: the daylit study (study_room.py), the
# chrome-frame cradle (cradle_model.py) and the scanned desk dressing (desk_props.py).


def build_environment(bpy,scene,c):
    """The study, the desk and everything standing in it; returns a description."""
    from study_room import build_study
    from desk_props import add_props
    room=build_study(scene,c['table_height'])
    room['props']=[p['object_name'] for p in add_props(c['table_height'])]
    return room


def used_assets():
    """Every asset folder or file the render reads, by registry name."""
    from desk_props import PROPS
    names=sorted({'rosewood_veneer1','plastered_wall_04','rectangular_parquet',*(model for _,model,*_ in PROPS)})
    return {f'polyhaven/newtons_cradle/{name}':str((ASSETS/name).resolve()) for name in names}
