"""Strict physical edits (shared DSL), including the explicitly requested preload preparation."""
from pathlib import Path
import json,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]))
import pcve_edit_dsl as dsl
import pcve_edit_policy as policy
SPEC=json.loads((HERE/'scene_spec.json').read_text(encoding='utf-8'))
BASELINE=dict(SPEC['baseline']);BASELINE.update(bag_present=[1],second_can_present=[0])
OWNED=tuple(dsl.SimBinding(k) for k in ('second_can_preload_seed_location_m','second_can_mass_kg','second_can_radius_m','second_can_height_m'))+(dsl.SimBinding('second_can_present',0),)
VOCAB=dsl.Vocabulary(objects={'can':{'zh':'金属罐头','en':'the metal can'},'bag':{'zh':'硅胶袋','en':'the silicone bag'},'second_can':{'zh':'同款金属罐头','en':'a second metal can'}},
    properties={'mass':dsl.PropertySpec('scalar','kg','质量','mass'),'young_modulus':dsl.PropertySpec('scalar','Pa','杨氏模量',"Young's modulus")},
    sim_bindings={('can','mass'):dsl.SimBinding('can_mass_kg'),('bag','young_modulus'):dsl.SimBinding('bag_young_modulus_pa')},
    delete_bindings={'bag':dsl.DeleteBinding('bag_present',index=0),'can':dsl.DeleteBinding('can_present',index=0)},
    add_bindings={'second_can':dsl.AddBinding('second_can_present',0,'second_can_preload_seed_location_m',owned_parameters=OWNED)},
    add_presets={('second_can','preloaded_inside_bag'):dsl.AddPreset(tuple((k,SPEC['baseline'][k]) for k in ('second_can_preload_seed_location_m','second_can_mass_kg','second_can_radius_m','second_can_height_m')),
        '立在硅胶袋的袋底','standing on the bottom inside the silicone bag')},
    # can_present lives only in the vocabulary baseline (readers default it to [1]); BASELINE is unchanged.
    object_parameters={'second_can':OWNED},baseline_physics={**BASELINE,'can_present':[1]},total_frames=97,scene_id=SPEC['scene_id'])
CASE_DSL={'source':None,'can_mass_x2':'SET can.mass TIMES 2','bag_young_x0_25':'SET bag.young_modulus TIMES 0.25','bag_young_x5':'SET bag.young_modulus TIMES 5','delete_bag':'DELETE bag','add_second_can':'ADD second_can AT PRESET preloaded_inside_bag'}


def override_for(case):
    if CASE_DSL[case] is None:return {}
    edit=dsl.parse(CASE_DSL[case],VOCAB);out=dsl.to_scenario_override(edit,VOCAB)
    for key in ('bag_present','second_can_present','can_present'):
        if key in out:out[key]=bool(out[key][0])
    policy.audit_scenario_override(edit,VOCAB,out,{})
    return out
