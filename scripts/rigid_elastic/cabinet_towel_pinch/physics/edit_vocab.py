"""Five single-factor edits; existing placement is immutable."""
import sys, copy
from common import REPO
sys.path.insert(0,str(REPO/'scripts'))
import pcve_edit_dsl as dsl

BASELINE={'door_present': [1],
 'stop_present': [0],
 'towel_density': 300.0,
 'towel_young_modulus': 1000000.0,
 'towel_friction': 1.2,
 'towel_thickness': 0.0008,
 'towel_poisson': 0.3,
 'hinge_torque': 0.9,
 'hinge_damping': 1.2,
 'door_mass': 2.4,
 'stop_location': [0.3, -0.09, 0.0005],
 'stop_dimensions': [0.13, 0.12, 0.24],
 'stop_mass': 2.0,
 'towel_bending_ratio': 0.01,
 'towel_strain_hardening': 500.0,
 'towel_shear_ratio': 0.004}
OBJECTS={k:{'zh':zh,'en':en}for k,zh,en in [('towel','棉质擦手巾','the cotton hand towel'),('door','柜门','the cabinet door'),('hinge','柜门铰链','the cabinet door hinge')]}
PROPERTIES={'density':dsl.PropertySpec('scalar','kg/m^3','密度','density'),
    'young_modulus':dsl.PropertySpec('scalar','Pa','杨氏模量',"Young's modulus"),
    'friction':dsl.PropertySpec('scalar','1','摩擦系数','friction coefficient'),
    'closing_torque':dsl.PropertySpec('scalar','N*m','闭门力矩','closing torque')}
VOCAB=dsl.Vocabulary(objects=OBJECTS,properties=PROPERTIES,
    sim_bindings={**{('towel',k):dsl.SimBinding('towel_'+k)for k in ['density','young_modulus','friction']},('hinge','closing_torque'):dsl.SimBinding('hinge_torque')},
    delete_bindings={'door':dsl.DeleteBinding('door_present',0),'towel':dsl.DeleteBinding('towel_present',0)},
    # towel_present lives only in the vocabulary baseline (absent means present): BASELINE and the resolved
    # physics of the published cases are unchanged.
    baseline_physics={**BASELINE,'towel_present':[1]},total_frames=96)
CASES={'source':None,'friction_x0_01':'SET towel.friction TIMES 0.01',
    'hinge_torque_x0_03':'SET hinge.closing_torque TIMES 0.03','young_modulus_x30':'SET towel.young_modulus TIMES 30',
    'delete_door':'DELETE door'}
CANDIDATES={'density_x20':'SET towel.density TIMES 20','delete_towel':'DELETE towel'}

def resolve(case):
    text=(CASES|CANDIDATES)[case];p=copy.deepcopy(BASELINE);override={}
    if text:
        edit=dsl.parse(text,VOCAB);override=dsl.to_scenario_override(edit,VOCAB)
        p.update(override)
    return p,dict(dsl=text,scenario_overrides=override)
