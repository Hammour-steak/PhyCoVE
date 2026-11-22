"""Edit DSL vocabulary, edit statements and source prompts of the toy car track jump.

The solver overrides are DEFINITIONS in counterfactual_cases.py; EDIT_DSL states the same changes
in the PCVE edit DSL, and pcve_edit_dsl.make_prompts turns each statement into its four prompts.
Both friction edits also raise the track's rolling resistance; the DSL names the sliding friction
coefficient, which is the dimensionless one.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl
from scene_config import BASELINE

_ph=BASELINE['physics'];_render=BASELINE['render']
VOCAB=dsl.Vocabulary(
    objects={'car':{'zh':'红色玩具小车','en':'the red toy car'},'track':{'zh':'橙色轨道','en':'the orange track'}},
    properties={'initial_speed':dsl.PropertySpec('scalar','m/s','初速度','initial speed',True),
                'friction':dsl.PropertySpec('scalar','','摩擦系数','friction coefficient')},
    sim_bindings={('car','initial_speed'):dsl.SimBinding('car_initial_speed_m_s'),
                  ('track','friction'):dsl.SimBinding('track_lateral_friction')},
    delete_bindings={'car':dsl.DeleteBinding('present',0)},
    baseline_physics={'car_initial_speed_m_s':_ph['car']['initial_speed_m_s'],'track_lateral_friction':_ph['track']['lateral_friction'],'present':[1]},
    total_frames=round(_render['fps']*_render['duration_sec']))
EDIT_DSL={'edit_initial_speed_half':'SET car.initial_speed TIMES 0.5',
          'edit_initial_speed_double':'SET car.initial_speed TIMES 2',
          'edit_high_friction_uphill':'SET track.friction TO 2',
          'edit_remove_car':'DELETE car',
          'edit_high_friction_near_lip':'SET track.friction TO 3 AT FRAME 8'}
SOURCE_PROMPTS={
    'vague':{'zh':'红色玩具小车沿橙色轨道爬坡、腾空，落到地板后继续滚动并停下。',
             'en':'A red toy car climbs an orange toy track, launches from the ramp, lands on the floor and rolls to a stop.'},
    'quantitative':{'zh':'长 15 cm、质量 106 g 的红色玩具小车以 2.76 m/s 的初速度沿橙色轨道驶向坡道，冲上 27 cm 高的坡顶后腾空，落到地板上继续滚动并停下。',
                    'en':'A 15 cm, 106 g red toy car sets off along an orange toy track at 2.76 m/s, climbs the ramp to its 27 cm high lip, launches into the air, lands on the floor and rolls to a stop.'}}


def case_prompts(case_id):
    """edit_dsl, first edited frame and the four prompts of one case."""
    if case_id=='source':
        return {'edit_dsl':None,'applies_from_frame':None,'prompts':SOURCE_PROMPTS}
    edit=dsl.parse(EDIT_DSL[case_id],VOCAB)
    return {'edit_dsl':EDIT_DSL[case_id],'applies_from_frame':dsl.starts_at_frame(edit),'prompts':dsl.make_prompts(edit,VOCAB)}
