"""Baseline physics (scene_spec.json), the strict edit vocabulary, the case DSL and the solver parameters of a case."""
from pathlib import Path
import copy,json,sys
from common import ROOT,DATA
HERE=Path(__file__).resolve().parent

sys.path.insert(0,str(ROOT/'scripts'))

import pcve_edit_dsl as dsl
SPEC_PATH=DATA/'scene_spec.json' if (DATA/'scene_spec.json').is_file() else HERE/'scene_spec.json'
SPEC=json.loads(SPEC_PATH.read_text(encoding='utf8'))
BASELINE=SPEC['baseline']
VOCAB=dsl.Vocabulary(
    objects={'shirt':{'zh':'棉质 T 恤','en':'the cotton T-shirt'},'seat':{'zh':'右侧落点坐垫','en':'the right landing seat cushion'}},
    properties={'density':dsl.PropertySpec('scalar','kg/m^3','密度','density'),
        'young_modulus':dsl.PropertySpec('scalar','Pa','有效杨氏模量','effective Young’s modulus'),
        'friction':dsl.PropertySpec('scalar','','接触摩擦系数','contact friction coefficient')},
    sim_bindings={('shirt','density'):dsl.SimBinding('shirt_density_kg_m3'),('shirt','young_modulus'):dsl.SimBinding('shirt_young_modulus_pa'),('shirt','friction'):dsl.SimBinding('shirt_friction')},
    delete_bindings={'seat':dsl.DeleteBinding('seat_present',0)},
    baseline_physics=BASELINE,total_frames=SPEC['frames'],scene_id=SPEC['scene_id'])
CASE_DSL={'source':None,'stiff_shirt':'SET shirt.young_modulus TIMES 10','heavy_shirt':'SET shirt.density TIMES 3','low_friction':'SET shirt.friction TIMES 0.25','remove_seat':'DELETE seat'}
# Timed edits (AT FRAME k): simulate.py --source-cache continues the accepted source solve from frame k.
TIMED={'low_friction_at_frame_10':'SET shirt.friction TIMES 0.25 AT FRAME 10'}
def timed_schedule(case):
    return dsl.to_scenario_override(dsl.parse(TIMED[case],VOCAB),VOCAB)[dsl.TIMED_EDITS_KEY]
def parameters(case):
    p=copy.deepcopy(BASELINE)
    text=TIMED[case]if case in TIMED else CASE_DSL[case]
    if text:p.update(dsl.to_physics_override(dsl.parse(text,VOCAB),VOCAB))
    E=p['shirt_young_modulus_pa'];h=p['shirt_thickness_m'];nu=p['shirt_poisson_ratio']
    p['shirt_stretch_young_pa']=E
    p['shirt_shear_n_m']=p['shirt_shear_ratio']*E*h/(2*(1+nu))
    p['shirt_bending_rigidity_nm']=p['shirt_bending_ratio']*E*h**3/(12*(1-nu**2))
    return p
