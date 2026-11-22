"""Strict shared physical-edit vocabulary for case 13 (elastic_key_strap)."""
import json, sys
from pathlib import Path
CASE = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE.parents[1]))
import pcve_edit_dsl as dsl
import pcve_edit_policy as policy
SPEC = json.loads((CASE / 'physics' / 'scene_spec.json').read_text(encoding='utf8'))
BASELINE = SPEC['baseline']
VOCAB = dsl.Vocabulary(
    objects={'keys': {'zh': '两把钥匙', 'en': 'the two keys'},
             'strap': {'zh': '硅胶挂带', 'en': 'the silicone strap'},
             'keyring': {'zh': '钥匙串', 'en': 'the keyring with its two keys'}},
    properties={'mass': dsl.PropertySpec('scalar', 'kg', '质量', 'mass'),
                'young_modulus': dsl.PropertySpec('scalar', 'Pa', '杨氏模量', "Young's modulus")},
    sim_bindings={('keys', 'mass'): dsl.SimBinding('keys_mass_kg'),
                  ('strap', 'young_modulus'): dsl.SimBinding('strap_young_modulus_pa')},
    delete_bindings={'strap': dsl.DeleteBinding('strap_present', 0), 'keyring': dsl.DeleteBinding('keyring_present', 0)},
    # keyring_present lives only in the vocabulary baseline (absent means present), so the resolved
    # configurations of the published solves (BASELINE + override) are unchanged.
    baseline_physics={**BASELINE, 'keyring_present': [1]}, total_frames=97, scene_id=SPEC['scene_id'])
CASE_DSL = {'source': None, 'keys_mass_5x': 'SET keys.mass TIMES 5',
            'strap_soft': 'SET strap.young_modulus TIMES 0.1',
            'strap_stiff': 'SET strap.young_modulus TIMES 10',
            'remove_strap': 'DELETE strap'}
LABELS = {'source': '基础场景', 'keys_mass_5x': '钥匙质量 ×5', 'strap_soft': '挂带杨氏模量 ×0.1',
          'strap_stiff': '挂带杨氏模量 ×10', 'remove_strap': '删除硅胶挂带'}


# Timed edits (AT FRAME k): the solver restores the exact source state of frame k (t=(k-1)/24) from the
# accepted source solve, applies the change there and keeps solving (physics/physics_model.py --source-cache).
TIMED_DSL = {'keys_mass_5x_at_frame_24': 'SET keys.mass TIMES 5 AT FRAME 24'}
LABELS['keys_mass_5x_at_frame_24'] = '第 24 帧起钥匙质量 ×5'


def override_for(case_id):
    text = TIMED_DSL[case_id] if case_id in TIMED_DSL else CASE_DSL[case_id]
    if text is None:
        return {}
    edit = dsl.parse(text, VOCAB)
    out = dsl.to_scenario_override(edit, VOCAB)
    policy.audit_scenario_override(edit, VOCAB, out, {})
    return out
