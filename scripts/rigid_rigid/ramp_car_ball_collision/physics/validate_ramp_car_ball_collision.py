"""Evidence gates for native contacts, passive wheels and isolated physical edits."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse
import json
import math
from pathlib import Path
from scene_config import differences,save_json,signature

def norm(v):return math.sqrt(sum(a*a for a in v))

def measured_restitution(contact):
    def point_velocity(state,name,point):
        o=state[name];d=[a-b for a,b in zip(point,o['location'])];w=o['angular_velocity'];v=o['linear_velocity']
        cross=[w[1]*d[2]-w[2]*d[1],w[2]*d[0]-w[0]*d[2],w[0]*d[1]-w[1]*d[0]]
        return [a+b for a,b in zip(v,cross)]
    def relative(state):
        a=point_velocity(state,'car_body',contact['car_point_m']);b=point_velocity(state,'ball',contact['ball_point_m'])
        return sum((x-y)*n for x,y,n in zip(a,b,contact['normal_on_ball']))
    before=relative(contact['preimpact']);after=relative(contact['at_contact'])
    return {'preimpact_normal_relative_speed_m_s':before,'postimpact_normal_relative_speed_m_s':after,'measured_effective_restitution':-after/before}

def validate(r,case='source',source=None):
    cfg=r['configuration'];ball=cfg['physics']['ball'];car=cfg['physics']['car'];o=r['outcome'];f=o['first_collision'];dg=r['diagnostics']
    if not car.get('present',True):return validate_absent_car(r,case,source)
    rolling_slip=dg['maximum_preimpact_rolling_slip_m_s']
    if not ball['present'] and source:
        # The no-ball case has no impact endpoint. Compare the same free-roll
        # window as source, while retaining its full-run native-slip diagnostic.
        end=source['outcome']['first_collision']['time_sec'];start=o['ramp_exit']['time_sec']
        rolling_slip=max(abs(w['linear_velocity'][0]-w['joint_velocity_rad_s']*car['wheel_radius_m'])
            for s in r['trajectory_samples'] if start<=s['time_sec']<end
            for name,w in s['objects'].items() if name.startswith('wheel'))
    checks={'all_initial_velocities_zero':all(norm(v['linear_velocity'])==norm(v['angular_velocity'])==0 for v in r['initial_state'].values()),
        'four_initial_wheel_contacts':r['initial_wheel_support_links']==[0,1,2,3],
        'no_initial_penetration_over_1um':r['initial_max_penetration_m']<1e-6,
        'zero_motor_torque':dg['maximum_motor_torque_Nm']==0.,
        'finite_trajectory':all(math.isfinite(x) for s in r['trajectory_samples'] for b in s['objects'].values() for k in ['location','quaternion_xyzw','linear_velocity','angular_velocity'] for x in b[k]),
        'native_rolling_no_slip_before_impact':rolling_slip<.015,
        'maximum_penetration_under_0_3mm':dg['maximum_penetration_m']<.0003,
        'no_energy_creation':dg['maximum_energy_J']<=r['initial_energy_J']+1e-5,
        'no_all_wheel_flight_over_10ms':dg['longest_all_wheel_flight_s']<.01,
        'lateral_car_drift_under_2cm':dg['maximum_lateral_drift_m']<.02,
        'four_wheels_exit_ramp':o['ramp_exit'] is not None,
        'initial_car_mass_250g':abs(r['actual_dynamics']['car_body']['mass_kg']+sum(r['actual_dynamics']['wheel_'+str(j)]['mass_kg'] for j in range(4))-.25)<1e-12,
        'chassis_inertia_readback_matches':r['actual_dynamics']['car_body']['inertia_diagonal_kg_m2']==car['chassis_inertia_kg_m2'],
        'tire_material_readback_matches':all(r['actual_dynamics']['wheel_'+str(j)]['restitution']==car['tire_restitution'] and r['actual_dynamics']['wheel_'+str(j)]['lateral_friction']==car['tire_lateral_friction'] for j in range(4)),
        'no_authored_driving':r['implementation']['velocity_resets_after_start']==0 and not r['implementation']['trajectory_driving']}
    contact_measurement=measured_restitution(f) if f else None
    if ball['present']:
        checks.update({'actual_collision':f is not None,'ball_mass_readback_matches':r['actual_dynamics']['ball']['mass_kg']==ball['mass_kg'],'ball_inertia_consistent':all(abs(v-ball['inertia_factor']*ball['mass_kg']*ball['radius_m']**2)<1e-12 for v in r['actual_dynamics']['ball']['inertia_diagonal_kg_m2'])})
        if f:
            checks.update({'first_hit_after_flat_exit_by_50ms':f['time_sec']-o['ramp_exit']['time_sec']>.05,
                'chassis_hits_before_wheels':f['car_link']==-1,
                'first_hit_on_bumper_front':f['car_point_m'][0]-f['at_contact']['car_body']['location'][0]>.058,
                'hit_near_ball_equator':abs(f['position_m'][2]-f['at_contact']['ball']['location'][2])<.006,
                'ball_was_at_rest':norm(f['preimpact']['ball']['linear_velocity'])<1e-6 and norm(f['preimpact']['ball']['angular_velocity'])<1e-6,
                'car_slows_from_actual_contact':f['at_contact']['car_body']['linear_velocity'][0]<f['preimpact']['car_body']['linear_velocity'][0]-.02,
                'measured_restitution_matches_actual_product':abs(contact_measurement['measured_effective_restitution']-ball['restitution']*car['bumper_restitution'])<.005,
                'ball_moves_forward':o['ball_forward_displacement_m']>.005,
                'ball_rotation_contact_generated':o['ball_max_abs_angular_velocity_rad_s']>.5})
    else:checks.update({'ball_absent_in_solver_and_output':'ball' not in r['initial_state'] and not r['contact_events'], 'car_passes_original_ball_location':o['car_final_position_m'][0]>ball['initial_position_m'][0]+.15})
    comparison=None
    if source:
        delta=differences(source['configuration'],cfg);allowed={'edit_heavy_ball':'physics.ball.mass_kg','edit_low_restitution':'physics.ball.restitution','edit_remove_ball':'physics.ball.present','edit_light_ball':'physics.ball.mass_kg','edit_remove_car_at_2s':'physics.car.remove_at_sec'}[case]
        checks['single_target_change']=set(delta)=={allowed}
        checks['appearance_render_quality_equal']=all(signature(source['configuration'][k])==signature(cfg[k]) for k in ['appearance','render','simulation_quality'])
        first_t=source['outcome']['first_collision']['time_sec'];before=[(a,b) for a,b in zip(source['trajectory_samples'],r['trajectory_samples']) if a['time_sec']<first_t-.001]
        pre=max(math.dist(a['objects']['car_body']['location'],b['objects']['car_body']['location']) for a,b in before)
        checks['preimpact_car_trajectory_unchanged']=pre<1e-5
        sf=source['outcome']['first_collision'];spos=source['outcome']['car_final_position_m'][0];pos=o['car_final_position_m'][0] if o['car_final_position_m'] is not None else None
        comparison={'differences':delta,'maximum_preimpact_car_position_error_m':pre,'car_final_position_difference_m':pos-spos if pos is not None else None,
            'ball_displacement_difference_m':o['ball_forward_displacement_m']-source['outcome']['ball_forward_displacement_m'] if ball['present'] else None}
        if case=='edit_heavy_ball':checks['mass_edit_clear_car_motion_difference']=abs(pos-spos)>.3
        if case=='edit_light_ball':
            checks['lighter_ball_changes_postimpact_motion']=abs(comparison['ball_displacement_difference_m'])>.05
        if case=='edit_remove_car_at_2s':
            removed={'car_body','wheel_0','wheel_1','wheel_2','wheel_3'}
            before=[(a,b) for a,b in zip(source['trajectory_samples'],r['trajectory_samples']) if a['time_sec']<2.]
            ev=r['intervention_events']
            checks.update({'exact_source_history_before_2s':all(a==b for a,b in before),
                'car_and_wheels_present_before_2s':all(removed<=set(s['objects']) for s in r['trajectory_samples'] if s['time_sec']<2.),
                'car_and_wheels_absent_from_2s':all(not removed.intersection(s['objects']) for s in r['trajectory_samples'] if s['time_sec']>=2.),
                'native_removal_at_2s_frame49':len(ev)==1 and ev[0]['time_sec']==2. and ev[0]['first_absent_frame']==49 and ev[0]['body_absent_from_solver'],
                'remaining_ball_not_reset':len(ev)==1 and ev[0]['remaining_state_unchanged'],
                'source_collision_history_preserved':r['contact_events']==source['contact_events'],
                'no_car_contacts_after_removal':all(e['time_sec']<2. for e in r['contact_events'])})
            comparison['exact_prefix_samples']=len(before)
        if case=='edit_low_restitution':
            sep=f['at_contact']['ball']['linear_velocity'][0]-f['at_contact']['car_body']['linear_velocity'][0]
            ssep=sf['at_contact']['ball']['linear_velocity'][0]-sf['at_contact']['car_body']['linear_velocity'][0]
            comparison.update({'first_step_separation_speed_m_s':sep,'source_first_step_separation_speed_m_s':ssep})
            checks['restitution_clear_and_stable']=abs(sep-ssep)>.2 and (abs(comparison['ball_displacement_difference_m'])>.08 or abs(pos-spos)>.08)
        if case=='edit_remove_ball':checks['absence_changes_car_progress']=pos>spos+.08
    return {'accepted':all(checks.values()),'case':case,'checks':checks,'comparison':comparison,'diagnostics':dg,'measured_first_contact':contact_measurement,'shared_preimpact_window_maximum_rolling_slip_m_s':rolling_slip,
        'first_collision_sec':f['time_sec'] if f else None,'ramp_exit_sec':o['ramp_exit']['time_sec'] if o['ramp_exit'] else None,
        'contact_combination':{'car_ball_restitution':ball['restitution']*car['bumper_restitution'],'ball_floor_restitution':ball['restitution']*cfg['physics']['floor']['restitution'],
            'edit_scope':'Changing only ball restitution affects every contact involving the ball, including bumper, floor, possible tires, ramp or later contacts; other body coefficients remain fixed.'}}

def validate_absent_car(r,case,source):
    cfg=r['configuration'];b=cfg['physics']['ball'];removed={'car_body','wheel_0','wheel_1','wheel_2','wheel_3'}
    samples=r['trajectory_samples'];dg=r['diagnostics'];actual=r['actual_dynamics']
    delta=differences(source['configuration'],cfg) if source else None
    checks={'car_not_created_in_solver':not removed.intersection(actual),
        'car_and_wheels_absent_in_all_outputs':not removed.intersection(r['initial_state']) and all(not removed.intersection(s['objects']) for s in samples+r['frames']),
        'only_ball_remains_dynamic':set(actual)=={'ball'},'no_car_ball_contacts':not r['contact_events'] and r['outcome']['first_collision'] is None,
        'ball_initially_stationary':all(norm(o['linear_velocity'])==norm(o['angular_velocity'])==0 for o in r['initial_state'].values()),
        'ball_stays_at_rest':max(norm(s['objects']['ball']['linear_velocity']) for s in samples)<1e-6 and max(norm(s['objects']['ball']['angular_velocity']) for s in samples)<1e-6,
        'ball_horizontal_displacement_under_1um':max(math.dist(s['objects']['ball']['location'][:2],b['initial_position_m'][:2]) for s in samples)<1e-6,
        'vertical_settling_within_declared_contact_slop':max(abs(s['objects']['ball']['location'][2]-b['initial_position_m'][2]) for s in samples)<=cfg['simulation_quality']['contact_slop_m']+1e-9,
        'ball_mass_readback_matches':actual['ball']['mass_kg']==b['mass_kg'],
        'ball_inertia_consistent':all(abs(v-b['inertia_factor']*b['mass_kg']*b['radius_m']**2)<1e-12 for v in actual['ball']['inertia_diagonal_kg_m2']),
        'finite_trajectory':all(math.isfinite(x) for s in samples for o in s['objects'].values() for k in ['location','quaternion_xyzw','linear_velocity','angular_velocity'] for x in o[k]),
        'no_energy_creation':dg['maximum_energy_J']<=r['initial_energy_J']+1e-5,
        'no_authored_driving':not r['implementation']['trajectory_driving'] and r['implementation']['velocity_resets_after_start']==0,
        'same_native_time_step':not source or r['dt_sec']==source['dt_sec'],
        'single_target_change':delta is None or set(delta)=={'physics.car.present'},
        'appearance_render_quality_equal':not source or all(signature(source['configuration'][k])==signature(cfg[k]) for k in ['appearance','render','simulation_quality'])}
    return {'accepted':all(checks.values()),'case':case,'checks':checks,'comparison':{'differences':delta},'diagnostics':dg,'first_collision_sec':None,'ramp_exit_sec':None}

def main():
    p=argparse.ArgumentParser();p.add_argument('physics',type=Path);p.add_argument('--case',default='source');p.add_argument('--source',type=Path);p.add_argument('--out',type=Path)
    a=p.parse_args();r=validate(json.loads(a.physics.read_text()),a.case,json.loads(a.source.read_text()) if a.source else None)
    if a.out:save_json(a.out,r)
    print(json.dumps(r,indent=2));raise SystemExit(0 if r['accepted'] else 2)
if __name__=='__main__':main()
