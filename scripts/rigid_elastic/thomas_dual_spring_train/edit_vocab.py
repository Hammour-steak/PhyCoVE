"""Strict physical edits; immutable original poses; one new obstacle slot."""
from pathlib import Path
import copy,sys
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2]
sys.path.insert(0,str(REPO/'scripts'))
import pcve_edit_dsl as dsl
import pcve_edit_policy as policy
from pcve_media_contract import CONTRACT
from physics.native import BASELINE
DELIVERY_BASELINE=copy.deepcopy(BASELINE)
DELIVERY_BASELINE.update(duration_s=CONTRACT['duration_s'],fps=CONTRACT['fps'])
# Presence slot of the train for DELETE train; physics/native.py reads it with the default "present" and the
# published configurations carry no such key.
DELIVERY_BASELINE['train_present']=[1]
OBJECTS={'train':{'zh':'无动力蓝色玩具火车','en':'the unpowered blue toy train'},
         'right_spring':{'zh':'右侧压簧和推板','en':'the right compression spring and its moving pusher'},
         'wood_block':{'zh':'轨道上的新增木块','en':'a newly added wooden block on the track'}}
PROPERTIES={'mass':dsl.PropertySpec('scalar','kg','质量','mass'),
    'rolling_resistance':dsl.PropertySpec('scalar','dimensionless','滚动阻力系数','rolling resistance coefficient',physical_quantity='friction'),
    'young_modulus':dsl.PropertySpec('scalar','Pa','杨氏模量',"Young's modulus")}
FIELDS=('obstacle_initial_position_m','obstacle_initial_quaternion_wxyz','obstacle_size_m','obstacle_mass_kg','obstacle_friction')
OWNED=tuple(dsl.SimBinding(k) for k in FIELDS)
VOCAB=dsl.Vocabulary(objects=OBJECTS,properties=PROPERTIES,
    sim_bindings={('train','mass'):dsl.SimBinding('train_mass_kg'),
                  ('train','rolling_resistance'):dsl.SimBinding('train_rolling_friction_coefficient'),
                  ('right_spring','young_modulus'):dsl.SimBinding('right_young_modulus_pa')},
    delete_bindings={'right_spring':dsl.DeleteBinding('right_spring_present',0),'train':dsl.DeleteBinding('train_present',0)},
    add_bindings={'wood_block':dsl.AddBinding('obstacle_present',0,'obstacle_initial_position_m',owned_parameters=OWNED)},
    add_presets={('wood_block','track_interceptor'):dsl.AddPreset(parameters=tuple((k,BASELINE[k]) for k in FIELDS),
      zh='轨道中部，45×56×44毫米，85克，初始静止',en='at the middle of the track, 45×56×44 mm, 85 g, initially stationary')},
    object_parameters={'train':tuple(dsl.SimBinding(k) for k in ['train_mass_kg','train_rolling_friction_coefficient','train_initial_x_m','train_initial_quaternion_wxyz']),
                       'right_spring':(dsl.SimBinding('right_young_modulus_pa'),), 'wood_block':OWNED},
    baseline_physics=DELIVERY_BASELINE,total_frames=CONTRACT['frames'],scene_id='thomas_dual_spring_train')

BASELINE_PHYSICS=DELIVERY_BASELINE
def resolve(text):
    if text is None:return {}
    e=dsl.parse(text,VOCAB);o=dsl.to_scenario_override(e,VOCAB)
    policy.audit_scenario_override(e,VOCAB,o,{})
    return o

def scenario_override(edit):
    o=dsl.to_scenario_override(edit,VOCAB);policy.audit_scenario_override(edit,VOCAB,o,{})
    return o


# --- Display-only ADD geometry -----------------------------------------------------------------------
# The published edit_dsl of the ADD case is the shared DSL's BETWEEN form:
#   ADD wood_block BETWEEN train AND right_track_reference AT MIDPOINT
# pcve_edit_dsl.parse(edit_dsl, VOCAB) needs a GeometryAnchor for both endpoints and for the new body.
# The anchors below are named points used only to place that line and word its prompts, the same way
# other scenes declare display anchors (e.g. rigid_rigid/kitchen_tin_collision stack_anchor).
# Centres are where each endpoint is at frame 1 of the ADD case, in the native frame (metres); radii only
# feed parse()'s overlap check. They live under display_anchor_* keys that no solver, renderer or SET/DELETE
# binding reads. The native "ADD ... AT PRESET" kept in native_edit_dsl still places the body; no existing
# id, binding or physical value changes.
# Solver frame (track top z = 0.003 m; the render lifts it by 0.569 m). train: centre of the train body box at the
# start, (-0.30025, 0, 0.040) m (train_initial_x_m - 0.001 m; box centre 0.040 m above the body origin).
# right_track_reference: the point of the track top under the near end of the right spring, (0.35025, 0, 0.003) m.
# Their midpoint (0.025, 0, 0.0215) m is 0.35 cm from the added block's centre (0.025, 0, 0.025) m.
import dataclasses as _dataclasses
import sys as _sys
_dsl = _sys.modules[type(VOCAB).__module__]
DISPLAY_ADD_ANCHORS = {
    "train": {
        "centre_m": [
            -0.30025,
            0.0,
            0.04
        ],
        "radius_m": 0.023
    },
    "right_track_reference": {
        "zh": "右侧压簧下方的轨道",
        "en": "the track under the right spring",
        "centre_m": [
            0.35025,
            0.0,
            0.003
        ],
        "radius_m": 0.001
    }
}
DISPLAY_ADD_NEW_BODY_RADIUS_M = {
    "wood_block": 0.022
}
DISPLAY_NAME_UPDATES = {
    "wood_block": {
        "zh": "木块",
        "en": "a wooden block"
    },
    "right_track_reference": {
        "zh": "右侧压簧下方的轨道",
        "en": "the track under the right spring"
    }
}


def _with_display_add_anchors(vocab):
    objects = {k: dict(v) for k, v in vocab.objects.items()}
    physics = dict(vocab.baseline_physics)
    geometry = dict(vocab.geometry)
    for name, names in DISPLAY_NAME_UPDATES.items():
        objects[name] = dict(names)
    for name, anchor in DISPLAY_ADD_ANCHORS.items():
        if name not in objects:
            objects[name] = {'zh': anchor['zh'], 'en': anchor['en']}
        if name in geometry:
            continue
        physics[f'display_anchor_{name}_centre_m'] = list(anchor['centre_m'])
        physics[f'display_anchor_{name}_radius_m'] = anchor['radius_m']
        geometry[name] = _dsl.GeometryAnchor(f'display_anchor_{name}_centre_m', f'display_anchor_{name}_radius_m')
    for name, radius in DISPLAY_ADD_NEW_BODY_RADIUS_M.items():
        if name in geometry:
            continue
        physics[f'display_anchor_{name}_radius_m'] = radius
        geometry[name] = _dsl.GeometryAnchor(vocab.add_bindings[name].location_key, f'display_anchor_{name}_radius_m')
    return _dataclasses.replace(vocab, objects=objects, baseline_physics=physics, geometry=geometry)


VOCAB = _with_display_add_anchors(VOCAB)
