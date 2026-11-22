from pathlib import Path
import math,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from validate_toy_car_track_jump import validate

def norm(v):return math.sqrt(sum(x*x for x in v))

def validate_case(result,source=None):
    case=result['case_id'];cfg=result['configuration']
    common={'frame_count':len(result['frames'])==96,'fps':result['fps']==24,
            'real_time':result['playback_rate']==1.,'normal_gravity':cfg['physics']['gravity']==[0.,0.,-9.81]}
    if case=='edit_remove_car':
        common.update(no_car=all(not s['objects'] for s in result['trajectory_samples']),zero_dynamic_dofs=result['solver']['dynamic_dofs']==0,
                      no_contacts=not result['contact_samples'] and not result['contact_events'])
        return {'accepted':all(common.values()),'checks':common,'metrics':{'dynamic_objects':0}}
    standard=validate(result)
    for key in ['rigid_wheel_axle_attachments','zero_motor_torque','no_deep_penetration','unmodified_real_time','passive_axle_pairs_remain_coupled']:
        common[key]=standard['checks'][key]
    samples=result['trajectory_samples'];b=[s['objects']['car_body'] for s in samples]
    tail=b[-120:];speeds=[norm(x['linear_velocity']) for x in b]
    metrics={'maximum_x_m':max(x['location'][0] for x in b),'maximum_height_m':max(x['location'][2] for x in b),
             'final_position_m':b[-1]['location'],'final_speed_m_s':speeds[-1],
             'tail_max_speed_m_s':max(speeds[-120:]),'tail_x_range_m':max(x['location'][0] for x in tail)-min(x['location'][0] for x in tail),
             'body_contact_samples':sum(s['body_contact'] for s in result['contact_samples']),
             'body_contact_tail_samples':sum(s['body_contact'] for s in result['contact_samples'][-120:]),
             'maximum_chassis_penetration_m':result['quality'].get('maximum_chassis_penetration_m',0.),
             'final_wheels_on_track':result['contact_samples'][-1]['wheels_on_track'],
             'maximum_track_penetration_m':result['quality']['maximum_track_penetration_m']}
    lip=result['track_profile_m'][-1][0]
    if case=='source':
        common.update(standard['checks']);metrics.update(standard['metrics'])
    elif case=='edit_initial_speed_half':
        peak_index=max(range(len(b)),key=lambda i:b[i]['location'][0])
        common.update(initial_speed_halved=cfg['physics']['car']['initial_speed_m_s']==1.38,
                      climbs_but_does_not_reach_lip=cfg['physics']['track']['curve_start_x_m']+.1<metrics['maximum_x_m']<lip-.1,
                      rolls_back=any(x['linear_velocity'][0]<-.2 for x in b),
                      reverses_after_peak=min(x['location'][0] for x in b[peak_index:])<metrics['maximum_x_m']-.1,
                      launcher_collision_recorded=any(s.get('launcher_contacts') for s in result['contact_samples']))
    elif case=='edit_initial_speed_double':
        common.update(initial_speed_doubled=cfg['physics']['car']['initial_speed_m_s']==5.52,
                      higher_flight=metrics['maximum_height_m']>.6,
                      further_travel=metrics['maximum_x_m']>2.5,
                      sustained_flight=standard['metrics']['free_flight_duration_sec']>.35,
                      actual_launch=result['native_launch_state'] is not None)
    elif case=='edit_high_friction_uphill':
        common.update(stops_on_ramp=cfg['physics']['track']['curve_start_x_m']+.1<b[-1]['location'][0]<lip-.1,
                      remains_at_rest=metrics['tail_max_speed_m_s']<.001 and metrics['tail_x_range_m']<.0001,
                      supported_by_track=len(metrics['final_wheels_on_track'])>=2,
                      no_floor_contact=not any(s['wheels_on_floor'] for s in result['contact_samples']),
                      no_chassis_support_at_rest=metrics['body_contact_tail_samples']==0,
                      no_deep_chassis_contact=metrics['maximum_chassis_penetration_m']<.0005)
    elif case=='edit_high_friction_near_lip':
        events=result['applied_interventions'];event=events[0] if events else {}
        front=[samples[-1]['objects']['wheel_'+str(i)]['location'][0] for i in [0,1]]
        prefix_error=0.
        assert source is not None
        for s,ref in zip(samples,source['trajectory_samples']):
            if s['time_sec']>7/24+1e-12:break
            for name,obj in s['objects'].items():
                for field in ['location','quaternion_xyzw','linear_velocity','angular_velocity']:
                    prefix_error=max(prefix_error,max(abs(a-b) for a,b in zip(obj[field],ref['objects'][name][field])))
        common.update(one_intervention=len(events)==1,
                      exact_activation_time=abs(event.get('time_sec',-1)-7/24)<1e-12,
                      continuous_state=event.get('positions_and_velocities_preserved_at_activation',False),
                      identical_source_prefix=prefix_error<1e-10,
                      near_lip=lip-.1<b[-1]['location'][0]<lip,
                      front_axle_stays_on_track=max(front)<lip,
                      all_four_wheels_supported=metrics['final_wheels_on_track']==[0,1,2,3],
                      remains_at_rest=metrics['tail_max_speed_m_s']<.001 and metrics['tail_x_range_m']<.0001,
                      no_floor_contact=not any(s['wheels_on_floor'] for s in result['contact_samples']))
        metrics.update(activation_sec=event.get('time_sec'),activation_frame_float=event.get('frame_float'),prefix_max_state_error=prefix_error,front_axle_final_x_m=front)
    else:raise ValueError(case)
    return {'accepted':all(common.values()),'checks':common,'metrics':metrics,'scope':'Per-case numerical acceptance; video and visual acceptance are separate.'}
