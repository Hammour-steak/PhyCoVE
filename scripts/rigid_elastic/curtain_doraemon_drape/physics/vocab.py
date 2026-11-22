"""Strict shared PCVE vocabulary of the scene: three curtain scalars and DELETE figurine (the porcelain vase)."""
from pathlib import Path
import copy, sys
HERE=Path(__file__).resolve().parent
SCRIPTS=next(p for p in HERE.parents if p.name=='scripts')
sys.path.insert(0,str(SCRIPTS))
import pcve_edit_dsl as dsl
from pcve_edit_policy import validate_edit
from baseline import PHYSICS,CASE

# Display names are what the video shows; they only enter prompts, never the solver.
OBJECTS={'curtain':{'zh':'米白色短窗帘','en':'the short off-white curtain'},   # object id figurine = the porcelain vase
         'figurine':{'zh':'青花瓷花瓶','en':'the blue-and-white porcelain vase'}}

VOCAB=dsl.Vocabulary(scene_id=CASE,
    objects=OBJECTS,
    properties={
        'young_modulus':dsl.PropertySpec('scalar','Pa','杨氏模量',"Young's modulus"),
        'density':dsl.PropertySpec('scalar','kg/m^3','密度','density'),
        'friction':dsl.PropertySpec('scalar','','摩擦系数','friction coefficient')},
    sim_bindings={('curtain','young_modulus'):dsl.SimBinding('cloth_young_modulus'),
        ('curtain','density'):dsl.SimBinding('cloth_density'),
        ('curtain','friction'):dsl.SimBinding('cloth_friction')},
    delete_bindings={'figurine':dsl.DeleteBinding('figure_active',index=0)},
    geometry={'figurine':dsl.GeometryAnchor('figure_location','figure_radius')},
    baseline_physics=copy.deepcopy(PHYSICS),total_frames=96)

CASES={'source':None,'young_modulus_x10':'SET curtain.young_modulus TIMES 10',
    'density_x0_5':'SET curtain.density TIMES 0.5','friction_x0_1':'SET curtain.friction TIMES 0.1',
    'delete_figurine':'DELETE figurine'}

# Timed edits (AT FRAME k): physics/simulate.py --source-cache continues the accepted source solve from the
# exact source state of frame k with the edited parameters.
TIMED={'friction_x0_1_at_frame_8':'SET curtain.friction TIMES 0.1 AT FRAME 8'}

def resolve(case):
    physics=copy.deepcopy(PHYSICS);text=TIMED[case] if case in TIMED else CASES[case]
    info=dict(case_id=case,edit_dsl=text,prompts={})
    if text:
        edit=dsl.parse(text,VOCAB);info['policy']=validate_edit(edit,VOCAB)
        info['override']=dsl.to_physics_override(edit,VOCAB);info['prompts']=dsl.make_prompts(edit,VOCAB)
        physics.update(info['override'])
        if case in TIMED:info['timed']=dsl.to_scenario_override(edit,VOCAB)[dsl.TIMED_EDITS_KEY][0]
    return physics,info

if __name__=='__main__':
    import json
    print(json.dumps({c:resolve(c)[1]for c in CASES},ensure_ascii=False,indent=2))
