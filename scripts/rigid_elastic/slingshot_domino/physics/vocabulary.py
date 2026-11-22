import copy, sys
from config import BASE, EDITS, CAT
sys.path.insert(0,str(CAT.parent))
import pcve_edit_dsl as dsl
import pcve_edit_policy as policy

VOCAB=dsl.Vocabulary(
 objects={k:{'zh':v,'en':e}for k,v,e in [('bands','两条扁平橡胶带','the two flat rubber bands'),
 ('ball','塑料小球','the plastic ball'),('domino','原有木牌','the original domino')]},
 properties={'young_modulus':dsl.PropertySpec('scalar','Pa','杨氏模量',"Young's modulus"),
 'mass':dsl.PropertySpec('scalar','kg','质量','mass')},
 sim_bindings={('bands','young_modulus'):dsl.SimBinding('young_modulus_pa'),
 ('ball','mass'):dsl.SimBinding('ball_mass_kg'),('domino','mass'):dsl.SimBinding('domino_mass_kg')},
 delete_bindings={'domino':dsl.DeleteBinding('domino_present',0),'ball':dsl.DeleteBinding('ball_present',0)},
 # ball_present lives only in the vocabulary baseline (the solver reads it with default [1]).
 baseline_physics={**copy.deepcopy(BASE),'ball_present':[1]},
 total_frames=96)

def resolve(case):
    override={}
    if case!='source':
        edit=dsl.parse(EDITS[case],VOCAB)
        override=dsl.to_scenario_override(edit,VOCAB)
        policy.audit_scenario_override(edit,VOCAB,override,{})
    conf=copy.deepcopy(BASE);conf.update(override)
    return conf,override
