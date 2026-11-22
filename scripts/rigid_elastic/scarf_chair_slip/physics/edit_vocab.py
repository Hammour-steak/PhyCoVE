"""Five physical counterfactuals using the shared strict edit DSL."""
from pathlib import Path
import copy,sys
from common import PHYSICS,CASE,LAYOUT
HERE=Path(__file__).resolve().parent;SCRIPTS=next(p for p in HERE.parents if p.name=='scripts')
sys.path.insert(0,str(SCRIPTS))
import pcve_edit_dsl as dsl
from pcve_edit_policy import validate_edit
VOCAB=dsl.Vocabulary(scene_id=CASE,
    objects={'scarf':{'zh':'棉质围巾','en':'the cotton scarf'},'chair':{'zh':'木椅','en':'the wooden chair'},
             'landing_book':{'zh':'精装书','en':'a hardcover book'}},
    properties={'young_modulus':dsl.PropertySpec('scalar','Pa','杨氏模量',"Young's modulus"),
                'density':dsl.PropertySpec('scalar','kg/m^3','密度','density'),
                'friction':dsl.PropertySpec('scalar','','摩擦系数','friction coefficient')},  # binds scarf_friction: the scarf-chair contact only
    sim_bindings={('scarf','young_modulus'):dsl.SimBinding('scarf_young_modulus'),
                  ('scarf','density'):dsl.SimBinding('scarf_density'),
                  ('scarf','friction'):dsl.SimBinding('scarf_friction')},
    delete_bindings={'chair':dsl.DeleteBinding('chair_active',index=0)},
    add_bindings={'landing_book':dsl.AddBinding('book_active',0,'book_location',owned_parameters=(
        dsl.SimBinding('book_active',0),dsl.SimBinding('book_location'),dsl.SimBinding('book_dimensions'),dsl.SimBinding('book_mass')))},
    add_presets={('landing_book','seat_center'):dsl.AddPreset((('book_location',PHYSICS['book_location']),
        ('book_dimensions',PHYSICS['book_dimensions']),('book_mass',PHYSICS['book_mass'])),
        '椅面上的预设位置，改变围巾落座时的接触','at its preset position above the seat, changing the scarf landing contact')},
    object_parameters={'landing_book':(dsl.SimBinding('book_active',0),dsl.SimBinding('book_location'),
        dsl.SimBinding('book_dimensions'),dsl.SimBinding('book_mass'))},
    baseline_physics=PHYSICS,total_frames=round(24*LAYOUT['duration']))
CASES={'source':None,'young_modulus_x10':'SET scarf.young_modulus TIMES 10',
       'density_x2':'SET scarf.density TIMES 2','friction_x0_2':'SET scarf.friction TIMES 0.2',
       'add_landing_book':'ADD landing_book AT PRESET seat_center','delete_chair':'DELETE chair'}
def resolve(case):
    p=copy.deepcopy(PHYSICS);text=CASES[case];info=dict(case_id=case,edit_dsl=text,prompts={})
    if text:
        e=dsl.parse(text,VOCAB);info.update(policy=validate_edit(e,VOCAB),override=dsl.to_physics_override(e,VOCAB),prompts=dsl.make_prompts(e,VOCAB))
        p.update(info['override'])
    return p,info
if __name__=='__main__':
    import json
    print(json.dumps({c:resolve(c)[1]for c in CASES},ensure_ascii=False,indent=2))
