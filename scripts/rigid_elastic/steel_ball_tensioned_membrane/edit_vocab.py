"""Strict shared physical edits for the steel-ball / membrane case."""
from __future__ import annotations
import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
DSL_DIR=HERE.parents[1]
sys.path.insert(0,str(DSL_DIR))
import pcve_edit_dsl as dsl
import pcve_edit_policy as policy
from pcve_assets import asset
# Specification of the accepted solves (24 fps, 4 s); the solver, the renderer and finalize read it too.
SPEC_PATH=asset('scenes/steel_ball_tensioned_membrane/scene_spec.json')
SPEC=json.loads(SPEC_PATH.read_text(encoding='utf-8'))
BASELINE=dict(SPEC['baseline'])
OBJECTS={
 'ball':{'zh':'钢球','en':'the steel ball'},
 'membrane':{'zh':'张紧橡胶膜','en':'the tensioned rubber membrane'},
 'second_ball':{'zh':'第二个同规格钢球','en':'the second identical steel ball'},
}
PROPERTIES={
 'mass':dsl.PropertySpec('scalar','kg','质量','mass'),
 'young_modulus':dsl.PropertySpec('scalar','Pa','杨氏模量',"Young's modulus"),
 'pretension':dsl.PropertySpec('scalar','N/m','单位长度预张力','pretension per unit length',physical_quantity='surface_tension'),
}
SIM_BINDINGS={
 ('ball','mass'):dsl.SimBinding('ball_mass_kg'),
 ('membrane','young_modulus'):dsl.SimBinding('membrane_young_modulus_pa'),
 ('membrane','pretension'):dsl.SimBinding('membrane_surface_tension_n_m'),
}
DSL_BASELINE=dict(BASELINE)
DSL_BASELINE.update(ball_present=[1],second_ball_present=[0],membrane_present=[1])
DELETE_BINDINGS={
 'ball':dsl.DeleteBinding('ball_present',index=0),
 'membrane':dsl.DeleteBinding('membrane_present',index=0),
}
SECOND_BALL_OWNED=(dsl.SimBinding('second_ball_present',0),dsl.SimBinding('second_ball_initial_location_m'),dsl.SimBinding('second_ball_radius_m'),dsl.SimBinding('second_ball_mass_kg'))
ADD_BINDINGS={'second_ball':dsl.AddBinding('second_ball_present',0,'second_ball_initial_location_m',owned_parameters=SECOND_BALL_OWNED)}
ADD_PRESETS={('second_ball','impact_path_on_membrane'):dsl.AddPreset((
 ('second_ball_initial_location_m',BASELINE['second_ball_initial_location_m']),('second_ball_radius_m',BASELINE['second_ball_radius_m']),
 ('second_ball_mass_kg',BASELINE['second_ball_mass_kg'])),
 '膜中心处、原球下落路径上的同规格钢球','identical steel ball at membrane centre in the primary impact path')}
VOCAB=dsl.Vocabulary(objects=OBJECTS,properties=PROPERTIES,sim_bindings=SIM_BINDINGS,
 delete_bindings=DELETE_BINDINGS,add_bindings=ADD_BINDINGS,add_presets=ADD_PRESETS,
 object_parameters={'second_ball':SECOND_BALL_OWNED},baseline_physics=DSL_BASELINE,
 total_frames=round(SPEC['fps']*SPEC['duration_s'])+1,scene_id=SPEC['scene_id'])

CASE_DSL={
 'source':None,
 'ball_mass_heavy':'SET ball.mass TIMES 2',
 'membrane_soft':'SET membrane.young_modulus TIMES 0.5',
 'membrane_stiff':'SET membrane.young_modulus TIMES 3',
 'remove_membrane':'DELETE membrane',
 'add_second_ball':'ADD second_ball AT PRESET impact_path_on_membrane',
}

# Cases outside the published catalog (scene_spec.json cases, PCVE_EDITS); the driver kept in the staged suite's
# inputs/edit_<case>/ solves and renders them.
STAGED_DSL={'remove_ball':'DELETE ball'}

def override_for(case_id):
    text={**CASE_DSL,**STAGED_DSL}[case_id]
    if text is None:return {}
    edit=dsl.parse(text,VOCAB)
    if getattr(edit,'at_frame',None) is not None:raise ValueError('Whole-clip edits only')
    out=dsl.to_scenario_override(edit,VOCAB)
    for key in ('ball_present','second_ball_present','membrane_present'):
        if key in out:out[key]=bool(out[key][0])
    policy.audit_scenario_override(edit,VOCAB,out,{})
    return out


# --- Display-only ADD geometry -------------------------------------------------------------------------
# The published edit_dsl of the ADD case is the shared BETWEEN form:
#   ADD second_ball BETWEEN ball AND membrane_impact_point AT 1/9 FROM membrane_impact_point
# pcve_edit_dsl.parse(edit_dsl, VOCAB) needs a GeometryAnchor for both endpoints and for the new body.
# The anchors below are named points used only to place that line and word its prompts, the same way
# other scenes declare display anchors (e.g. rigid_rigid/kitchen_tin_collision stack_anchor).
# Centres are where each endpoint is at frame 1 of the ADD case, in the native frame (metres); radii only
# feed parse()'s overlap check. They live under display_anchor_* keys that no solver, renderer or SET/DELETE
# binding reads. The native "ADD ... AT PRESET" kept in native_edit_dsl still places the body; no existing
# id, binding or physical value changes.
# ball: the steel ball's release centre (0, 0, 1.10) m (ball_initial_location_m). membrane_impact_point: the centre of
# the tensioned membrane, (0, 0, 0.72) m (membrane_height_m). The 1/9 point from it, (0, 0, 0.7622) m, is 0.12 cm from
# the second ball's centre (0, 0, 0.761) m.
import dataclasses as _dataclasses
import sys as _sys
_dsl = _sys.modules[type(VOCAB).__module__]
DISPLAY_ADD_ANCHORS = {
    "ball": {
        "centre_m": [
            0.0,
            0.0,
            1.1
        ],
        "radius_m": 0.04
    },
    "membrane_impact_point": {
        "zh": "张紧膜的中心",
        "en": "the centre of the tensioned membrane",
        "centre_m": [
            0.0,
            0.0,
            0.72
        ],
        "radius_m": 0.001
    }
}
DISPLAY_ADD_NEW_BODY_RADIUS_M = {
    "second_ball": 0.04
}
DISPLAY_NAME_UPDATES = {
    "second_ball": {
        "zh": "同规格钢球",
        "en": "an identical steel ball"
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
