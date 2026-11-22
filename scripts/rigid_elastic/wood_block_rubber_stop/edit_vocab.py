"""Edit DSL vocabulary of the scene: object names as seen on screen, editable
properties, and their bindings to the native parameters in scene_spec.json."""
from pathlib import Path
import copy,json,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import pcve_edit_dsl as dsl
SPEC=json.loads((HERE/'scene_spec.json').read_text(encoding='utf-8'))
# SET edits are written as multiples of the baseline (the shared DSL convention);
# they resolve to the same native values as the cases in scene_spec.json
# (4.2 m/s, 20 kg, 32 kPa), which the shared policy audit checks.
CASE_DSL={
 'source':None,
 'fast_block':'SET wood_block.initial_velocity TIMES 1.5',
 'heavy_block':'SET wood_block.mass TIMES 10',
 'soft_010':'SET open_cell_sponge.young_modulus TIMES 0.1',
 'remove_bumper':'DELETE open_cell_sponge',
 'add_mid_block':'ADD secondary_wood_block AT PRESET path_midpoint',
}
SELECTED_CASES=tuple(CASE_DSL)
BASELINE={**SPEC['baseline'],'block_initial_speed_m_s':SPEC['baseline']['block_initial_velocity_m_s'][0],
          'bumper_present':[1],'added_block_present':[0]}
ADDED_OWNED=(dsl.SimBinding('added_block_present',0),dsl.SimBinding('added_block_initial_center_m'),dsl.SimBinding('added_block_dimensions_m'),dsl.SimBinding('added_block_mass_kg'))
# Display names are what a viewer sees: one wooden block, one yellow sponge with
# a green scouring layer, and (ADD only) a second, smaller wooden block.
OBJECT_NAMES={
 'wood_block':{'zh':'木块','en':'the wooden block'},
 'open_cell_sponge':{'zh':'黄绿色海绵','en':'the yellow-and-green sponge'},
 'secondary_wood_block':{'zh':'小木块','en':'a small wooden block'},
}
VOCAB=dsl.Vocabulary(
 objects=OBJECT_NAMES,
 properties={
  'mass':dsl.PropertySpec('scalar','kg','质量','mass',physical_quantity='mass'),
  'initial_velocity':dsl.PropertySpec('scalar','m/s','初始速度','initial speed',physical_quantity='velocity'),
  'young_modulus':dsl.PropertySpec('scalar','Pa','杨氏模量',"Young's modulus",physical_quantity='young_modulus'),
  'contact_friction':dsl.PropertySpec('scalar','','接触摩擦系数','contact friction coefficient',physical_quantity='friction')},
 sim_bindings={('wood_block','mass'):dsl.SimBinding('block_mass_kg'),('wood_block','initial_velocity'):dsl.SimBinding('block_initial_speed_m_s'),('open_cell_sponge','young_modulus'):dsl.SimBinding('bumper_young_modulus_pa'),('open_cell_sponge','contact_friction'):dsl.SimBinding('contact_friction')},
 delete_bindings={'open_cell_sponge':dsl.DeleteBinding('bumper_present',index=0,value_when_removed=0)},
 add_bindings={'secondary_wood_block':dsl.AddBinding('added_block_present',0,'added_block_initial_center_m',owned_parameters=ADDED_OWNED)},
 # The preset centre lies on the floor at the midpoint of the block-to-sponge
 # centre line (x=-0.635 m between -1.30 m and 0.03 m); the ADD prompts say
 # "midpoint" in words.
 add_presets={('secondary_wood_block','path_midpoint'):dsl.AddPreset((('added_block_initial_center_m',SPEC['baseline']['added_block_initial_center_m']),('added_block_dimensions_m',SPEC['baseline']['added_block_dimensions_m']),('added_block_mass_kg',SPEC['baseline']['added_block_mass_kg'])),'木块和黄绿色海绵连线的中点','at the midpoint of the line between the wooden block and the yellow-and-green sponge')},
 object_parameters={'secondary_wood_block':ADDED_OWNED},baseline_physics=BASELINE,total_frames=round(SPEC['duration_s']/SPEC['playback_time_scale']*SPEC['display_fps']))

# Cases outside the published catalog (scene_spec.json cases, PCVE_EDITS); the driver kept in the staged suite's
# inputs/edit_<case>/ solves and renders them. Their presence edits resolve through STAGED_VOCAB (end of this file).
STAGED_DSL={'remove_wood_block':'DELETE wood_block'}

def parameters(case):
 p=copy.deepcopy(SPEC['baseline'])
 if case in STAGED_DSL:
  p.update({k:bool(v[0]) for k,v in dsl.to_physics_override(dsl.parse(STAGED_DSL[case],STAGED_VOCAB),STAGED_VOCAB).items()});return p
 p.update(SPEC['cases'][case]);return p

def case_dsl(case):
 return {**CASE_DSL,**STAGED_DSL}[case]


# Published form of the ADD edit (the catalog's edit_dsl); CASE_DSL keeps the native
# "ADD ... AT PRESET" that the solve uses. The preset centre is the midpoint of the
# block-to-sponge line.
ADD_LINE_DSL='ADD secondary_wood_block BETWEEN wood_block AND open_cell_sponge AT MIDPOINT'


def add_prompts():
 """ADD prompts rendered from ADD_LINE_DSL by the shared renderer (the shared BETWEEN wording).
 The native preset still places the body."""
 # The endpoints carry display-only GeometryAnchors (end of this file).
 return dsl.make_prompts(dsl.parse(ADD_LINE_DSL,VOCAB),VOCAB)


def case_prompts(case):
 """Bilingual vague/quantitative prompts of one edit case, generated from the DSL."""
 edit=dsl.parse(CASE_DSL[case],VOCAB)
 if isinstance(edit,dsl.AddEdit):
  return add_prompts()
 return dsl.make_prompts(edit,VOCAB)


# --- Display-only ADD geometry -------------------------------------------------------------------------
# The published edit_dsl of the ADD case is the shared DSL's BETWEEN form:
#   ADD secondary_wood_block BETWEEN wood_block AND open_cell_sponge AT MIDPOINT
# pcve_edit_dsl.parse(edit_dsl, VOCAB) needs a GeometryAnchor for both endpoints and for the new body.
# The anchors below are named points used only to place that line and word its prompts, the same way
# other scenes declare display anchors (e.g. rigid_rigid/kitchen_tin_collision stack_anchor).
# Centres are where each endpoint is at frame 1 of the ADD case, in the native frame (metres); radii only
# feed parse()'s overlap check. They live under display_anchor_* keys that no solver, renderer or SET/DELETE
# binding reads. The native "ADD ... AT PRESET" kept in native_edit_dsl still places the body; no existing
# id, binding or physical value changes.
# wood_block (-1.30, 0, 0.049) m and open_cell_sponge (0.03, 0, 0.062) m: frame-1 centres. Their midpoint
# (-0.635, 0, 0.0555) m is exactly above the small block's centre (-0.635, 0, 0.044) m, 1.15 cm higher (it rests on
# the floor and is lower than both endpoints).
import dataclasses as _dataclasses
import sys as _sys
_dsl = _sys.modules[type(VOCAB).__module__]
DISPLAY_ADD_ANCHORS = {
    "wood_block": {
        "centre_m": [
            -1.3,
            0.0,
            0.049
        ],
        "radius_m": 0.0475
    },
    "open_cell_sponge": {
        "centre_m": [
            0.03,
            0.0,
            0.062
        ],
        "radius_m": 0.06
    }
}
DISPLAY_ADD_NEW_BODY_RADIUS_M = {
    "secondary_wood_block": 0.0425
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

# Vocabulary of the staged DELETE wood_block case: the scene vocabulary plus the block's presence slot (block_present of
# scene_spec.json, which the solver, renderer and ground-truth export read with the default "present"). It is kept apart
# from VOCAB because the published catalog pins VOCAB's editable objects (build_pcve check_catalog).
STAGED_VOCAB = _dataclasses.replace(
    VOCAB, baseline_physics={**VOCAB.baseline_physics, 'block_present': [1]},
    delete_bindings={**VOCAB.delete_bindings, 'wood_block': dsl.DeleteBinding('block_present', index=0, value_when_removed=0)})
