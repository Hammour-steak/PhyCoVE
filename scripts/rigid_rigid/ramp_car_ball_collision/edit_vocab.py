"""Edit DSL vocabulary, edit cases and prompts of the ramp car and ball scene.

The solver overrides are CASES in scene_config.py; EDIT_DSL states the same changes in the PCVE
edit DSL, and pcve_edit_dsl.make_prompts turns each statement into its four prompts.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl
from scene_config import BASELINE,CASES

_ph=BASELINE['physics'];_render=BASELINE['render']
VOCAB=dsl.Vocabulary(
    objects={'car':{'zh':'橙色玩具小车','en':'the orange toy car'},'ball':{'zh':'彩色小球','en':'the colorful ball'}},
    properties={'mass':dsl.PropertySpec('scalar','kg','质量','mass'),
                'restitution':dsl.PropertySpec('scalar','','恢复系数','coefficient of restitution')},
    sim_bindings={('ball','mass'):dsl.SimBinding('ball_mass_kg'),('ball','restitution'):dsl.SimBinding('ball_restitution')},
    delete_bindings={'car':dsl.DeleteBinding('present',0),'ball':dsl.DeleteBinding('present',1)},
    baseline_physics={'ball_mass_kg':_ph['ball']['mass_kg'],'ball_restitution':_ph['ball']['restitution'],'present':[1,1]},
    total_frames=round(_render['fps']*_render['duration_sec']))
EDIT_DSL={'edit_heavy_ball':'SET ball.mass TO 0.8',
          'edit_low_restitution':'SET ball.restitution TIMES 0.125',
          'edit_remove_ball':'DELETE ball',
          'edit_light_ball':'SET ball.mass TO 0.01',
          'edit_remove_car':'DELETE car',
          'edit_remove_car_at_2s':'DELETE car AT FRAME 49'}
SOURCE_PROMPTS={
    'vague':{'zh':'无动力的橙色玩具小车从静止开始沿蓝色玩具坡道滑下，在地板上用车头撞上静止的彩色小球。',
             'en':'An unpowered orange toy car rolls from rest down a blue toy ramp and hits a stationary colorful ball on the floor with its front bumper.'},
    'quantitative':{'zh':'质量 0.25 kg、长约 12 cm 的无动力橙色玩具小车从静止开始沿长 55 cm、高 12 cm 的蓝色坡道滑下，在地板上用车头撞上直径 6 cm、质量 30 g 的静止彩色小球。',
                    'en':'An unpowered 0.25 kg, 12 cm orange toy car rolls from rest down a 55 cm long, 12 cm high blue ramp and hits a stationary 6 cm, 30 g colorful ball on the floor with its front bumper.'}}

def edit_info(case):
    entries={
        'source': {'operation':'SOURCE','target':None},
        'edit_heavy_ball': {'operation':'SET','target':'ball.mass','before':.03,'after':.8,'unit':'kg','note':'Ball inertia is updated with its mass; shape, position, contact coefficients and all other inputs are unchanged.'},
        'edit_low_restitution': {'operation':'SET','target':'ball.restitution','before':.8,'after':.1,
            'contact_scope':'Bullet multiplies the two object restitution values. Bumper-ball effective restitution 0.64 -> 0.08; floor-ball 0.096 -> 0.012. All contacts involving the ball are affected.'},
        'edit_remove_ball': {'operation':'DELETE','target':'ball','effective_time_sec':0.},
        'edit_light_ball': {'operation':'SET','target':'ball.mass','before':.03,'after':.01,'unit':'kg','note':'Ball inertia is updated with its mass; all other inputs are unchanged.'},
        'edit_remove_car': {'operation':'DELETE','target':'car','effective_time_sec':0.,'note':'The complete car, body and all four wheels, is removed before simulation starts.'},
        'edit_remove_car_at_2s': {'operation':'DELETE','target':'car','effective_time_sec':2.,'first_absent_frame':49,
            'note':'The complete car and its four wheels are removed at 2.0 s; the preceding collision history is kept and the ball continues from its solver state.'}}
    info=dict(entries[case])
    if case=='source':
        info.update(edit_dsl=None,applies_from_frame=None,prompts=SOURCE_PROMPTS)
        return info
    edit=dsl.parse(EDIT_DSL[case],VOCAB)
    if isinstance(edit,dsl.SetEdit):
        field={'mass':'mass_kg','restitution':'restitution'}[edit.property_name]
        assert abs(dsl.resolved_to_value(edit,VOCAB)-CASES[case]['physics']['ball'][field])<1e-12,case
    info.update(edit_dsl=EDIT_DSL[case],applies_from_frame=dsl.starts_at_frame(edit),prompts=dsl.make_prompts(edit,VOCAB))
    return info
