"""One-factor edits, using the repository's strict shared policy."""
from pathlib import Path
import json, sys
HERE = Path(__file__).resolve().parent
# scripts/ holds the shared DSL and policy modules (a packaged copy keeps them one level up).
SCRIPTS = next((p for p in HERE.parents if (p / 'pcve_edit_dsl.py').is_file()), HERE.parent)
sys.path.insert(0, str(SCRIPTS))
import pcve_edit_dsl as dsl
import pcve_edit_policy as policy
SPEC_PATH=HERE/'scene_spec.json'
SPEC = json.loads(SPEC_PATH.read_text(encoding='utf-8'))
BASELINE_PHYSICS = SPEC['baseline']
OBJECTS = {'coin': {'zh': '硬币', 'en': 'the coin'},
           'ruler': {'zh': '塑料尺', 'en': 'the plastic ruler'},
           'second_coin': {'zh': '同样的硬币', 'en': 'an identical coin'}}
PROPERTIES = {'mass': dsl.PropertySpec('scalar', 'kg', '质量', 'mass'),
              'young_modulus': dsl.PropertySpec('scalar', 'Pa', '杨氏模量', "Young's modulus")}
OWNED = tuple(dsl.SimBinding(p) for p in ('second_coin_initial_location_m', 'second_coin_initial_rotation_rad',
              'second_coin_mass_kg', 'second_coin_radius_m', 'second_coin_thickness_m'))
VOCAB = dsl.Vocabulary(
    objects=OBJECTS, properties=PROPERTIES,
    sim_bindings={('coin','mass'): dsl.SimBinding('coin_mass_kg'),
                  ('ruler','young_modulus'): dsl.SimBinding('ruler_young_modulus_pa')},
    delete_bindings={'coin': dsl.DeleteBinding('coin_present', index=0),
                     'ruler': dsl.DeleteBinding('ruler_present', index=0)},
    add_bindings={'second_coin': dsl.AddBinding('second_coin_present', 0, 'second_coin_initial_location_m', owned_parameters=OWNED)},
    add_presets={('second_coin', 'resting_on_ruler'): dsl.AddPreset(tuple((p, BASELINE_PHYSICS[p]) for p in (
        'second_coin_initial_location_m','second_coin_initial_rotation_rad','second_coin_mass_kg','second_coin_radius_m','second_coin_thickness_m')),
        '平放在尺面上、书的边缘和尺子末端连线中点处的同样硬币', 'an identical coin lying flat on the ruler, midway between the edge of the book and the end of the ruler')},
    object_parameters={'coin': (dsl.SimBinding('coin_initial_location_m'), dsl.SimBinding('coin_initial_rotation_rad')),
                       'second_coin': OWNED},
    # ruler_present is a DSL-only presence switch (default on): SPEC['baseline'] and resolve(case) of the existing
    # cases do not carry it; physics.py and appearance/realism.py read cfg.get('ruler_present', [1]).
    baseline_physics={**BASELINE_PHYSICS, 'ruler_present': [1]}, total_frames=round(SPEC['duration_s']*SPEC['fps']), scene_id='plastic_ruler_coin')

def resolve(case):
    result = json.loads(json.dumps(BASELINE_PHYSICS))
    expression = SPEC['cases'][case]['dsl']
    if expression:
        edit = dsl.parse(expression, VOCAB)
        override = dsl.to_scenario_override(edit, VOCAB)
        policy.audit_scenario_override(edit, VOCAB, override, {})
        result.update(override)
    return result


def recorded_physics_matches(recorded, case):
    """True if a solve's recorded physics block equals resolve(case).

    The accepted solves also carry the book's footprint length inside their physics block (under another
    key); it never entered the dynamics and is kept in scene_spec.json "diagnostics".
    """
    current = resolve(case)
    extra = {k: v for k, v in recorded.items() if k not in current}
    extra_ok = not extra or (len(extra) == 1 and list(extra.values())[0] == SPEC['diagnostics']['book_footprint_length_m'])
    return extra_ok and all(recorded.get(k) == v for k, v in current.items())
