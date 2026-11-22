"""Strict physical edits of the closed rubber band slider (shared DSL vocabulary)."""
from pathlib import Path
import json,sys
CATEGORY=next(p for p in Path(__file__).resolve().parents if p.name=='rigid_elastic')
sys.path[:0]=[str(CATEGORY.parent)]
import pcve_edit_dsl as dsl
import pcve_edit_policy as policy
SPEC=json.loads((Path(__file__).with_name('scene_spec.json')).read_text(encoding='utf-8'))
BASE=SPEC['baseline'];CASES=SPEC['cases'];DSL_BASE=dict(BASE);DSL_BASE['young_modulus_pa']=DSL_BASE.pop('young_pa')
EDITS={'young_x0p5':'SET band.young_modulus TIMES 0.5','mass_x3':'SET slider.mass TIMES 3',
       'friction_x2':'SET guide.friction TIMES 2','delete_band':'DELETE band','add_stop':'ADD stopper AT PRESET return_path'}
owned=tuple(dsl.SimBinding(k) for k in ['stopper_position_m','stopper_size_m'])
# Display names follow what the video shows: the guide's friction is the slider-guide sliding contact.
VOCAB=dsl.Vocabulary(objects={'band':{'zh':'橡皮筋','en':'the rubber band'},
    'slider':{'zh':'木滑块','en':'the wooden slider'},'guide':{'zh':'木导槽','en':'the wooden guide'},
    'stopper':{'zh':'中间开口的木挡块','en':'a wooden stop with a gap in the middle'}},
    properties={'young_modulus':dsl.PropertySpec('scalar','Pa','杨氏模量',"Young's modulus"),
                'mass':dsl.PropertySpec('scalar','kg','质量','mass'),'friction':dsl.PropertySpec('scalar','','摩擦系数','friction coefficient')},
    sim_bindings={('band','young_modulus'):dsl.SimBinding('young_modulus_pa'),('slider','mass'):dsl.SimBinding('mass_kg'),('guide','friction'):dsl.SimBinding('friction')},
    delete_bindings={'band':dsl.DeleteBinding('band_present',0)},baseline_physics=DSL_BASE,
    add_bindings={'stopper':dsl.AddBinding('stopper_present',0,'stopper_position_m',owned_parameters=owned)},
    add_presets={('stopper','return_path'):dsl.AddPreset(parameters=tuple((b.key,BASE[b.key]) for b in owned),
        zh='木滑块上的木桩和左端夹具连线上靠近木桩的四等分点',
        en='at the quarter point of the line from the peg on the wooden slider to the clamp at the left end')},
    object_parameters={'slider':tuple(dsl.SimBinding(k) for k in ['initial_x_m','mass_kg','slider_size_m','attachment_offset_m']),
        'band':tuple(dsl.SimBinding(k) for k in ['anchor_x_m','pin_radius_m','band_z_m','loop_rest_m','band_width_m','band_thickness_m']),
        'stopper':owned},scene_id='rubber_band_wood_slider',total_frames=96)
# Names for the prompts of the published ADD DSL
# ("ADD stopper BETWEEN slider_peg AND left_clamp AT 1/4 FROM slider_peg").
# The two endpoints are display-only names; VOCAB also carries them as
# display-only GeometryAnchors (see the end of this file) so that parse(edit_dsl, VOCAB) works.
PROMPT_OBJECTS={**VOCAB.objects,'slider_peg':{'zh':'木滑块上的木桩','en':'the peg on the wooden slider'},
    'left_clamp':{'zh':'左端夹具','en':'the clamp at the left end'}}

def override(case):
    if case=='source':return {}
    edit=dsl.parse(EDITS[case],VOCAB);actual=dsl.to_scenario_override(edit,VOCAB)
    policy.audit_scenario_override(edit,VOCAB,actual,{})
    native=dict(actual)
    if 'young_modulus_pa' in native:native['young_pa']=native.pop('young_modulus_pa')
    if {**BASE,**native}!={**BASE,**CASES[case]}:raise ValueError('Native/DSL mismatch')
    return actual


# --- Display-only ADD geometry -------------------------------------------------------------------------
# The published edit_dsl of the ADD case is the shared DSL's BETWEEN form:
#   ADD stopper BETWEEN slider_peg AND left_clamp AT 1/4 FROM slider_peg
# pcve_edit_dsl.parse(edit_dsl, VOCAB) needs a GeometryAnchor for both endpoints and for the new body.
# The anchors below are named points used only to place that line and word its prompts, the same way
# other scenes declare display anchors (e.g. rigid_rigid/kitchen_tin_collision stack_anchor).
# Centres are where each endpoint is at frame 1 of the ADD case, in the native frame (metres); radii only
# feed parse()'s overlap check. They live under display_anchor_* keys that no solver, renderer or SET/DELETE
# binding reads. The native "ADD ... AT PRESET" kept in native_edit_dsl still places the body; no existing
# id, binding or physical value changes.
# slider_peg: the band's attachment on the slider, x = initial_x_m + attachment_offset_m = 0.0475 m, at band height
# band_z_m = 0.0095 m. left_clamp: the band anchor pin at anchor_x_m = -0.07 m, same height. The 1/4 point from the
# peg, (0.0181, 0, 0.0095) m, is 0.72 cm from the stop's centre (0.015, 0, 0.016) m.
import dataclasses as _dataclasses
import sys as _sys
_dsl = _sys.modules[type(VOCAB).__module__]
DISPLAY_ADD_ANCHORS = {
    "slider_peg": {
        "zh": "木滑块上的木桩",
        "en": "the peg on the wooden slider",
        "centre_m": [
            0.0475,
            0.0,
            0.0095
        ],
        "radius_m": 0.003
    },
    "left_clamp": {
        "zh": "左端夹具",
        "en": "the clamp at the left end",
        "centre_m": [
            -0.07,
            0.0,
            0.0095
        ],
        "radius_m": 0.003
    }
}
DISPLAY_ADD_NEW_BODY_RADIUS_M = {
    "stopper": 0.003
}
DISPLAY_NAME_UPDATES = {}


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
