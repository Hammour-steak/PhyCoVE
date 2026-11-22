"""Five independent physical/add/delete edits; all original transforms frozen."""
from pathlib import Path
import copy,json,sys
HERE=Path(__file__).resolve().parent
CATEGORY=next((p for p in HERE.parents if p.name=='elastic_elastic'),None)
if CATEGORY is not None:
 ROOT=CATEGORY.parents[1];sys.path.insert(0,str(ROOT/'scripts'))
else:
 # The shared packager places this module and its immutable specification
 # together under vocab/<scene>, with the shared DSL one directory above.
 sys.path.insert(0,str(HERE.parent))
import pcve_edit_dsl as dsl
import pcve_edit_policy as policy
from common import INPUTS
SPEC=json.loads((INPUTS/'scene_spec.json').read_text(encoding='utf-8'));BASELINE=SPEC['baseline']
OWNED=tuple(dsl.SimBinding(n,0 if n=='doorstop_present' else None) for n in ['doorstop_present','doorstop_center_m','doorstop_radius_m','doorstop_height_m','doorstop_density_kg_m3'])
VOCAB=dsl.Vocabulary(objects={'falling_slipper':{'zh':'上方落下的拖鞋','en':'the falling slide'},'resting_slipper':{'zh':'原先静置地面的拖鞋','en':'the initially resting slide'},'doorstop':{'zh':'固定橡胶门挡','en':'the fixed rubber doorstop'}},properties={'young_modulus':dsl.PropertySpec('scalar','Pa','杨氏模量',"Young's modulus"),'density':dsl.PropertySpec('scalar','kg/m^3','密度','density')},sim_bindings={('falling_slipper','young_modulus'):dsl.SimBinding('falling_young_modulus_pa'),('resting_slipper','young_modulus'):dsl.SimBinding('resting_young_modulus_pa'),('falling_slipper','density'):dsl.SimBinding('falling_density_kg_m3')},delete_bindings={'resting_slipper':dsl.DeleteBinding('resting_present',0)},add_bindings={'doorstop':dsl.AddBinding('doorstop_present',0,'doorstop_center_m',owned_parameters=OWNED)},add_presets={('doorstop','downstream_floor'):dsl.AddPreset(tuple((n,BASELINE[n]) for n in ['doorstop_center_m','doorstop_radius_m','doorstop_height_m','doorstop_density_kg_m3']),'拖鞋落地路径旁的冻结预设位置','the frozen preset on the floor along the slide\'s subsequent path')},object_parameters={'falling_slipper':tuple(dsl.SimBinding(n) for n in ['falling_center_m','falling_euler_deg']),'resting_slipper':tuple(dsl.SimBinding(n) for n in ['resting_center_m','resting_euler_deg']),'doorstop':OWNED},baseline_physics=BASELINE,total_frames=96,scene_id=SPEC['scene_id'])
CASE_DSL={'source':None,'stiff_falling':'SET falling_slipper.young_modulus TIMES 4','soft_resting':'SET resting_slipper.young_modulus TIMES 0.25','heavy_falling':'SET falling_slipper.density TIMES 3','remove_resting':'DELETE resting_slipper','add_doorstop':'ADD doorstop AT PRESET downstream_floor'}

def override_for(case):
 text=CASE_DSL[case]
 if text is None:return {}
 edit=dsl.parse(text,VOCAB);over=dsl.to_scenario_override(edit,VOCAB);policy.audit_scenario_override(edit,VOCAB,over,{});return over

def parameters(case):
 out=copy.deepcopy(BASELINE);out.update(override_for(case));return out
