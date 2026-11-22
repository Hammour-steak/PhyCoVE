"""Edit DSL vocabulary: three scalar edits, one deletion, one new body.

Object names are what a viewer sees on screen. SET/DELETE prompts are generated
by the shared DSL renderer. The ADD case is published in the shared DSL's
``ADD ... BETWEEN ... AT MIDPOINT`` (ADD_LINE_DSL) and its prompts are rendered
from that line (see add_prompts()); the native ``ADD obstacle AT PRESET landing``
still resolves the physics.
"""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
CATEGORY = next((p for p in HERE.parents if p.name == 'rigid_elastic'),None)
sys.path.insert(0,str(CATEGORY.parent if CATEGORY else HERE.parent))
sys.path.insert(0,str(HERE))
import pcve_edit_dsl as dsl
import pcve_edit_policy as policy  # noqa: F401  (scene_common uses vocabulary_module().policy)
if (HERE/'scene_common.py').is_file():
    # The distributed vocabulary includes an exact, dependency-free snapshot.
    import importlib.util
    _s=importlib.util.spec_from_file_location('spring_block_step_packaged_constants',HERE/'scene_common.py')
    _m=importlib.util.module_from_spec(_s);_s.loader.exec_module(_m)
    BASE,FRAMES=_m.BASE,_m.FRAMES
else:
    from scene_common import BASE, FRAMES

NEW = ('obstacle_position_m','obstacle_size_m','obstacle_mass_kg','obstacle_quaternion_wxyz','obstacle_friction')
owned = tuple(dsl.SimBinding(k) for k in NEW)
LANDING={k:BASE[k] for k in NEW}
LANDING['obstacle_position_m']=[.31,0,.025]
# Two fixed props on the workbench, behind and in front of the landing path, whose
# centres have the ADD preset centre (0.31, 0) m as their midpoint in plan view.
# Appearance only (appearance/realism.py places them); not part of the solver scene.
ADD_ENDPOINTS={'bowl':{'xy_m':(0.37,0.31),'zh':'木碗','en':'the wooden bowl'},
               'tape':{'xy_m':(0.25,-0.31),'zh':'胶带卷','en':'the roll of tape'}}
assert all(abs((ADD_ENDPOINTS['bowl']['xy_m'][i]+ADD_ENDPOINTS['tape']['xy_m'][i])/2-LANDING['obstacle_position_m'][i])<1e-12 for i in (0,1))
OBJECT_NAMES={
    'block':{'zh':'木块','en':'the wooden block'},
    'spring':{'zh':'弹簧','en':'the spring'},
    'table':{'zh':'桌面','en':'the tabletop'},
    'obstacle':{'zh':'大小相近的木块','en':'a similar-sized wooden block'},
}
VOCAB = dsl.Vocabulary(
    objects=OBJECT_NAMES,
    properties={'mass':dsl.PropertySpec('scalar','kg','质量','mass'),
                'young_modulus':dsl.PropertySpec('scalar','Pa','杨氏模量',"Young's modulus"),
                'friction':dsl.PropertySpec('scalar','','摩擦系数','friction coefficient')},
    sim_bindings={('block','mass'):dsl.SimBinding('block_mass_kg'),
                  ('spring','young_modulus'):dsl.SimBinding('spring_young_modulus_pa'),
                  ('table','friction'):dsl.SimBinding('table_friction')},
    delete_bindings={'spring':dsl.DeleteBinding('spring_present',0),'block':dsl.DeleteBinding('block_present',0)},
    # block_present lives only in the vocabulary baseline (the solver reads it with default [1]),
    # so the resolved physics of the published cases is unchanged.
    baseline_physics={**BASE,'block_present':[1]}, total_frames=FRAMES,
    add_bindings={'obstacle':dsl.AddBinding('obstacle_present',0,'obstacle_position_m',owned_parameters=owned)},
    add_presets={('obstacle','landing'):dsl.AddPreset(tuple((k,LANDING[k]) for k in NEW),
        '木碗和胶带卷连线的中点',
        'at the midpoint of the line between the wooden bowl and the roll of tape')},
    object_parameters={'block':tuple(dsl.SimBinding(k) for k in ('block_position_m','block_size_m','block_quaternion_wxyz')),
                       'spring':tuple(dsl.SimBinding(k) for k in ('spring_anchor_x_m','spring_rest_length_m','spring_initial_compression_m')),
                       'table':tuple(dsl.SimBinding(k) for k in ('table_position_m','table_size_m')),
                       'obstacle':owned},scene_id='spring_block_step')


# Published form of the ADD edit (the catalog's edit_dsl): the preset centre is the midpoint of
# the bowl-to-tape line. bowl and tape are display names only (ADD_ENDPOINTS, appearance
# props): they are named in PROMPT_OBJECTS, not in VOCAB, so they carry no physics binding and
# stay out of editable_objects.
ADD_LINE_DSL='ADD obstacle BETWEEN bowl AND tape AT MIDPOINT'
PROMPT_OBJECTS={**OBJECT_NAMES,**{k:{'zh':v['zh'],'en':v['en']} for k,v in ADD_ENDPOINTS.items()}}


def add_prompts():
    """ADD prompts rendered from ADD_LINE_DSL by the shared renderer (shared BETWEEN wording).
    The native preset still places the body."""
    # The endpoints are display-only GeometryAnchors of VOCAB (end of this file),
    # so the published line parses against VOCAB like any other edit.
    return dsl.make_prompts(dsl.parse(ADD_LINE_DSL,VOCAB),VOCAB)


def case_prompts(command):
    """Bilingual vague/quantitative prompts of one edit, generated from its DSL string."""
    edit=dsl.parse(command,VOCAB)
    if isinstance(edit,dsl.AddEdit):
        return add_prompts()
    return dsl.make_prompts(edit,VOCAB)


# --- Display-only ADD geometry -------------------------------------------------------------------------
# The published edit_dsl of the ADD case is the shared DSL's BETWEEN form:
#   ADD obstacle BETWEEN bowl AND tape AT MIDPOINT
# pcve_edit_dsl.parse(edit_dsl, VOCAB) needs a GeometryAnchor for both endpoints and for the new body.
# The anchors below are named points used only to place that line and word its prompts, the same way
# other scenes declare display anchors (e.g. rigid_rigid/kitchen_tin_collision stack_anchor).
# Centres are where each endpoint is at frame 1 of the ADD case, in the native frame (metres); radii only
# feed parse()'s overlap check. They live under display_anchor_* keys that no solver, renderer or SET/DELETE
# binding reads. The native "ADD ... AT PRESET" kept in native_edit_dsl still places the body; no existing
# id, binding or physical value changes.
# bowl and tape: the bounding-box centres of the two workbench props (render_report dressing: bowl
# (0.37, 0.31, 0.0365) m, tape roll (0.25, -0.31, 0.0242) m). Their midpoint (0.31, 0, 0.0304) m is 0.54 cm from the
# added block's centre (0.31, 0, 0.025) m.
import dataclasses as _dataclasses
import sys as _sys
_dsl = _sys.modules[type(VOCAB).__module__]
DISPLAY_ADD_ANCHORS = {
    "bowl": {
        "zh": "木碗",
        "en": "the wooden bowl",
        "centre_m": [
            0.37,
            0.31,
            0.03655
        ],
        "radius_m": 0.0365
    },
    "tape": {
        "zh": "胶带卷",
        "en": "the roll of tape",
        "centre_m": [
            0.25,
            -0.31,
            0.0242
        ],
        "radius_m": 0.05
    }
}
DISPLAY_ADD_NEW_BODY_RADIUS_M = {
    "obstacle": 0.025
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
