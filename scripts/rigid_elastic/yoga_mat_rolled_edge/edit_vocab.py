"""Edit vocabulary of the rolled yoga-mat scene: baseline values, DSL bindings and the native cases."""
from __future__ import annotations
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]))
import pcve_edit_dsl as dsl

BASELINE={
    'ball_present':True,'mat_present':True,
    'ball_radius_m':0.12065,'ball_mass_kg':5.0,
    'ball_initial_location_m':[-1.05,0.0,0.1213],'ball_initial_speed_m_s':0.9,
    'mat_length_m':1.8,'mat_width_m':0.66,'mat_thickness_m':0.006,
    'mat_density_kg_m3':476.9921436588103,'mat_young_modulus_pa':6000000.0,
    'mat_viscosity_scale':1.0,
    'mat_poisson_ratio':0.46,'mat_curl_height_m':0.0335,'mat_curl_length_m':0.063,
    'contact_friction':0.72,
    'gravity_m_s2':9.81,
}
OBJECTS={
    'ball':{'zh':'药球','en':'the medicine ball'},
    'mat':{'zh':'卷边瑜伽垫','en':'the curled yoga mat'},
}
PROPERTIES={
    'mass':dsl.PropertySpec('scalar','kg','质量','mass'),
    'rolling_speed':dsl.PropertySpec('scalar','m/s','初始纯滚动速度','initial no-slip rolling speed',physical_quantity='velocity'),
    'young_modulus':dsl.PropertySpec('scalar','Pa','杨氏模量',"Young's modulus"),
    'viscosity_scale':dsl.PropertySpec('scalar','1','黏性倍率','viscosity scale'),
}
SIM_BINDINGS={
    ('ball','mass'):dsl.SimBinding('ball_mass_kg'),
    ('ball','rolling_speed'):dsl.SimBinding('ball_initial_speed_m_s'),
    ('mat','young_modulus'):dsl.SimBinding('mat_young_modulus_pa'),
    ('mat','viscosity_scale'):dsl.SimBinding('mat_viscosity_scale'),
}
DSL_BASELINE=dict(BASELINE)
DSL_BASELINE.update(ball_present=[1],mat_present=[1])
DELETE_BINDINGS={
    'ball':dsl.DeleteBinding('ball_present',index=0),
    'mat':dsl.DeleteBinding('mat_present',index=0),
}
VOCAB=dsl.Vocabulary(objects=OBJECTS,properties=PROPERTIES,sim_bindings=SIM_BINDINGS,
    delete_bindings=DELETE_BINDINGS,baseline_physics=DSL_BASELINE,
    total_frames=96)

CASE_DSL={
    'source':None,
    'delete_mat':'DELETE mat',
    'ball_mass_light':'SET ball.mass TIMES 0.25',
    'ball_speed_slow':'SET ball.rolling_speed TIMES 0.5',
    'mat_stiff':'SET mat.young_modulus TIMES 4',
}

# Timed edits (AT FRAME k): physics/simulate_source.py restores the source state of frame k
# (--source-cache/--edit-frame) and continues with the edited value; frames 1..k-1 are the source's own.
TIMED_DSL={'mass_x0p25_at_frame_16':'SET ball.mass TIMES 0.25 AT FRAME 16'}

def timed_override(case_id):
    """Edited physics values and the 1-based frame they apply from."""
    edit=dsl.parse(TIMED_DSL[case_id],VOCAB)
    return dsl.to_physics_override(edit,VOCAB),edit.at_frame

# Cases outside the published catalog (PCVE_EDITS); the driver kept in the staged suite's inputs/edit_<case>/ solves
# and renders them.
STAGED_DSL={'delete_ball':'DELETE ball'}

def override_for(case_id):
    text={**CASE_DSL,**STAGED_DSL}[case_id]
    if text is None:return {}
    edit=dsl.parse(text,VOCAB)
    if getattr(edit,'at_frame',None) is not None:raise ValueError('Whole-clip edits only')
    out=dsl.to_scenario_override(edit,VOCAB)
    for key in ('ball_present','mat_present'):
        if key in out:out[key]=bool(out[key][0])
    return out
