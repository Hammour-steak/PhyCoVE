"""Edit vocabulary of the metro security-bag scene: baseline physics, the cases and their DSL bindings."""
from pathlib import Path
import copy,sys
HERE=Path(__file__).resolve().parent;CATEGORY=HERE.parent
shared=next(p for p in HERE.parents if (p/'pcve_edit_dsl.py').is_file())
sys.path.insert(0,str(shared))
import pcve_edit_dsl as dsl
BASELINE={'curtain_width_m':.51,'curtain_length_m':.295,'curtain_top_height_m':1.055,'curtain_thickness_m':.0024,
 'curtain_density_kg_m3':3600.,'curtain_young_modulus_pa':3000000.,'curtain_poisson_ratio':.45,
 'membrane_viscosity_pa_s':12000.,'bending_viscosity_pa_s':240000.,'curtain_mass_damping_s_inv':4.0,'self_contact_friction':.15,'self_contact_skin_m':.008,'strip_count':6,'strip_gap_m':.003,
 'belt_height_m':.75,'belt_end_x_m':.70,'belt_nose_radius_m':.028,'ramp_end_x_m':1.25,'pickup_end_x_m':1.90,'pickup_height_m':.57,'nose_plate_friction':.18,'ramp_friction':.18,'pickup_friction':.30,'endstop_friction':.35,'bag_bag_friction':.30,'belt_speed_m_s':.4,'belt_bag_friction':.5,'curtain_contact_friction':.24,
 'bag_mass_kg':4.,'bag_dimensions_m':[.44,.33131616946334996,.21416777254621677],
 'bag_initial_center_m':[-.30,0.,.75],'bag_initial_speed_m_s':.2,'curtain_present':[1],
 'second_bag_present':[0],'second_bag_initial_center_m':[-.83,0.,.75],'second_bag_mass_kg':4.}
CASE_DSL={'source':None,'young_modulus_x100':'SET exit_curtain.young_modulus TO 300000000',
 'belt_speed_x2':'SET conveyor.velocity TO 0.8','friction_x0p02':'SET bag.friction TO 0.01',
 'delete_curtain':'DELETE exit_curtain'}
# Public multiplier syntax is equivalent to the native absolute-SI declaration.
PUBLIC_DSL=dict(CASE_DSL,young_modulus_x100='SET exit_curtain.young_modulus TIMES 100',belt_speed_x2='SET conveyor.velocity TIMES 2',friction_x0p02='SET bag.friction TIMES 0.02')
LABELS={'source':'原始场景','young_modulus_x100':'出口铅帘杨氏模量 ×100','belt_speed_x2':'输送带速度 ×2',
 'friction_x0p02':'背包与输送带摩擦系数 ×0.02','delete_curtain':'删除出口铅帘'}
VOCAB=dsl.Vocabulary(objects={'bag':{'zh':'背包','en':'the backpack'},'conveyor':{'zh':'输送带','en':'the conveyor belt'},
 'exit_curtain':{'zh':'出口铅帘','en':'the exit lead curtain'}},
 properties={'young_modulus':dsl.PropertySpec('scalar','Pa','杨氏模量',"Young's modulus",physical_quantity='young_modulus'),
 'velocity':dsl.PropertySpec('scalar','m/s','速度','speed',physical_quantity='velocity'),
 'friction':dsl.PropertySpec('scalar','','摩擦系数','friction coefficient',physical_quantity='friction')},
 sim_bindings={('exit_curtain','young_modulus'):dsl.SimBinding('curtain_young_modulus_pa'),('conveyor','velocity'):dsl.SimBinding('belt_speed_m_s'),('bag','friction'):dsl.SimBinding('belt_bag_friction')},
 delete_bindings={'exit_curtain':dsl.DeleteBinding('curtain_present',index=0,value_when_removed=0),
                  'bag':dsl.DeleteBinding('bag_present',index=0,value_when_removed=0)},
 # bag_present is a DSL-only presence switch (default on): BASELINE and parameters(case) of the existing cases do
 # not carry it, the solver and renderer read p.get('bag_present',[1]).
 baseline_physics={**BASELINE,'bag_present':[1]},total_frames=96)
def parameters(case):
    p=copy.deepcopy(BASELINE)
    if CASE_DSL[case]:p.update(dsl.to_physics_override(dsl.parse(CASE_DSL[case],VOCAB),VOCAB))
    return p

# Timed edits (AT FRAME k): frames 1..k-1 are the accepted source states; the solver restores the exact
# source state of frame k (t=(k-1)/24) from the source cache, applies the change there and keeps solving.
TIMED_DSL={'delete_curtain_at_frame_12':'DELETE exit_curtain AT FRAME 12'}
LABELS['delete_curtain_at_frame_12']='第 12 帧起删除出口铅帘'
def timed_schedule(case):
    """[{'frame': k, 'params': override}] of a timed case (the shared to_scenario_override form)."""
    return dsl.to_scenario_override(dsl.parse(TIMED_DSL[case],VOCAB),VOCAB)[dsl.TIMED_EDITS_KEY]
