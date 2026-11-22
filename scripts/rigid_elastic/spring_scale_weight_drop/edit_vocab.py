"""Edit vocabulary of the spring balance: whole-clip and timed edits; no existing-object transform is editable."""
import sys
from physics.scene import BASELINE,REPO
sys.path.insert(0,str(REPO/'scripts'))
import pcve_edit_dsl as dsl
import pcve_edit_policy as policy

OBJECTS={'weight':{'zh':'下落砝码','en':'the falling calibration weight'},
 'spring':{'zh':'弹簧秤的钢制弹簧','en':'the steel spring in the spring balance'},
 'guide':{'zh':'秤盘的导杆','en':"the pan's guide rods"}}
PROPERTIES={'mass':dsl.PropertySpec('scalar','kg','质量','mass'),
 'young_modulus':dsl.PropertySpec('scalar','Pa','杨氏模量',"Young's modulus"),
 'damping':dsl.PropertySpec('scalar','N*s/m','黏性阻尼系数','viscous damping coefficient')}
BINDINGS={('weight','mass'):dsl.SimBinding('weight_mass_kg'),
 ('spring','young_modulus'):dsl.SimBinding('spring_young_modulus_pa'),
 ('guide','damping'):dsl.SimBinding('guide_damping_ns_m')}
DSL_BASELINE=dict(BASELINE)
DSL_BASELINE.update({k:[int(BASELINE[k])] for k in ['weight_present','stop_present']})
# The spring's presence switch is not a solver input of the published cases (BASELINE has no key for it);
# physics/simulate_spring.py reads it with the default "present".
DSL_BASELINE.update(spring_present=[1])
VOCAB=dsl.Vocabulary(objects=OBJECTS,properties=PROPERTIES,sim_bindings=BINDINGS,
 delete_bindings={'weight':dsl.DeleteBinding('weight_present',0),'spring':dsl.DeleteBinding('spring_present',0)},
 baseline_physics=DSL_BASELINE,total_frames=96,scene_id='steel_ball_silicone_cup')

CASE_DSL={'source':None,'heavy':'SET weight.mass TIMES 2','soft':'SET spring.young_modulus TIMES 0.5',
 'damped':'SET guide.damping TIMES 4','remove_weight':'DELETE weight'}
# Timed edits (AT FRAME k): physics/simulate_spring.py restores the accepted source state at t=(k-1)/24 from the
# source cache (--source-cache) and continues with the edited value; frames 1..k-1 are the source's own.
TIMED_DSL={'heavy_at_frame_48':'SET weight.mass TIMES 2 AT FRAME 48'}
# Whole-clip cases outside the published catalog (PCVE_EDITS); the driver kept in the staged suite's
# inputs/edit_<case>/ solves and renders them.
STAGED_DSL={'remove_spring':'DELETE spring'}
LABELS={'source':'砝码下落拉伸弹簧秤','heavy':'砝码质量 ×2','soft':'弹簧杨氏模量 ×0.5',
 'damped':'导向黏性阻尼 ×4','remove_weight':'删除下落砝码','heavy_at_frame_48':'第 48 帧起砝码质量 ×2',
 'remove_spring':'删除弹簧'}

def case_dsl(case):
 return {**CASE_DSL,**TIMED_DSL,**STAGED_DSL}[case]

def override_for(case):
 text=case_dsl(case)
 if text is None:return {}
 edit=dsl.parse(text,VOCAB);out=dsl.to_scenario_override(edit,VOCAB)
 policy.audit_scenario_override(edit,VOCAB,out,{})
 for key in ['weight_present','stop_present','spring_present']:
  if key in out:out[key]=bool(out[key][0])
 return out

def parameters(case):return dict(BASELINE,**override_for(case))
