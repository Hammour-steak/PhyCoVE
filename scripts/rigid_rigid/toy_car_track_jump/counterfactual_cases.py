"""Five requested physical counterfactuals, with SI values and edit prompts."""
from scene_config import scenario
from edit_vocab import case_prompts

CASE_IDS=['source','edit_initial_speed_half','edit_initial_speed_double','edit_high_friction_uphill','edit_remove_car','edit_high_friction_near_lip']
DEFINITIONS={
 'source':{'kind':'source','overrides':{},'title_zh':'原始场景','edit_zh':None},
 'edit_initial_speed_half':{'kind':'edit','overrides':{'physics':{'car':{'initial_speed_m_s':1.38}}},
    'title_zh':'初速度减半','edit_zh':'将小车的初始前进速度降低为原来的一半（2.76 → 1.38 m/s），初始轮速与车速同步匹配。'},
 'edit_initial_speed_double':{'kind':'edit','overrides':{'physics':{'car':{'initial_speed_m_s':5.52}}},
    'title_zh':'初速度加倍','edit_zh':'将小车的初始前进速度提高为原来的两倍（2.76 → 5.52 m/s），初始轮速与车速同步匹配。'},
 'edit_high_friction_uphill':{'kind':'edit','overrides':{'physics':{'track':{'lateral_friction':2.,'rolling_friction':.006}}},
    'title_zh':'高摩擦，停在坡中','edit_zh':'从第 1 帧起增大轨道与车轮之间的滑动摩擦和滚动阻力，使小车爬上斜坡一段距离后停住。'},
 'edit_remove_car':{'kind':'edit','overrides':{'physics':{'car':{'present':False}}},
    'title_zh':'删除小车','edit_zh':'从第 1 帧起删除小车及其全部车轮，保留轨道、支架和房间。'},
 'edit_high_friction_near_lip':{'kind':'edit','overrides':{'physics':{'interventions':[
    {'id':'near_lip_friction','type':'set_track_friction','trigger':{'time_sec':7/24},
     'parameters':{'lateral_friction':3.,'spinning_friction':1e-5,'rolling_friction':.04}}]}},
    'title_zh':'临近起跳口增摩，停在坡顶','edit_zh':'在第 8 帧（0.291667 秒）、小车即将到达轨道末端时，增大轨道滑动摩擦和滚动阻力，使小车停在坡顶。'},
}

def case_configuration(case_id,overrides=None):
    from scene_config import merge
    cfg=scenario(overrides)
    return merge(cfg,DEFINITIONS[case_id]['overrides'])

def prompts(case_id):
    d=DEFINITIONS[case_id]
    en={
      'source':'A red toy car climbs an orange toy track, launches from the ramp, lands on the floor and rolls to a stop.',
      'edit_initial_speed_half':'Reduce the initial forward speed of the toy car by half, with matching initial wheel spin.',
      'edit_initial_speed_double':'Double the initial forward speed of the toy car, with matching initial wheel spin.',
      'edit_high_friction_uphill':'Increase track sliding friction and rolling resistance from the start so that the car climbs partway up the ramp and stops.',
      'edit_remove_car':'Remove the toy car and all its wheel components from the start, leaving the track and room.',
      'edit_high_friction_near_lip':'At frame 8, increase track sliding friction and rolling resistance so that the car stops near the launch lip.'}
    return {'schema_version':3,'case_id':case_id,'source_case_id':'source','interaction_category':'rigid_rigid',
            'object_ids':{'car_body':'C01','wheel_0':'WFL','wheel_1':'WFR','wheel_2':'WRL','wheel_3':'WRR'},
            'edit_instruction':{'zh':d['edit_zh'],'en':en[case_id] if case_id!='source' else None},'title_zh':d['title_zh'],
            **case_prompts(case_id),
            'video_spec':{'duration_sec':4.,'resolution':[1280,720],'fps':24,'frames':96,'playback_rate':1.},
            'parameter_overrides':d['overrides'],
            'friction_units':{'lateral_friction':'dimensionless','rolling_friction':'m','spinning_friction':'m'},
            'notes':['Initial-speed edits also update the matching passive wheel spin.','Friction edits change contact parameters in MuJoCo, without pose or velocity resets.']}
