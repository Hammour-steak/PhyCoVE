"""Validate measured contact, flight, rigid attachment, spin and rollout evidence."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scene_config import save_json, wheel_positions

def norm(values):
    return math.sqrt(sum(v*v for v in values))

def inverse_rotate(q,v):
    x,y,z,w=q
    # Rotation by the quaternion conjugate.
    x,y,z=-x,-y,-z
    t=[2*(y*v[2]-z*v[1]),2*(z*v[0]-x*v[2]),2*(x*v[1]-y*v[0])]
    return [v[0]+w*t[0]+y*t[2]-z*t[1],v[1]+w*t[1]+z*t[0]-x*t[2],v[2]+w*t[2]+x*t[1]-y*t[0]]

def validate(result):
    cfg=result['configuration'];c=cfg['physics']['car'];samples=result['trajectory_samples'];contacts=result['contact_samples']
    bodies=[s['objects']['car_body'] for s in samples]
    floor_indices=[i for i,s in enumerate(contacts) if s['wheels_on_floor']]
    first_floor=floor_indices[0] if floor_indices else None
    flights=[];active=[]
    for i,s in enumerate(contacts):
        if first_floor is not None and i>=first_floor:break
        free=not(s['wheels_on_track'] or s['wheels_on_floor'] or s.get('other_contacts') or s['body_contact'])
        if free:active.append(i)
        else:
            if active:flights.append(active)
            active=[]
    if active:flights.append(active)
    main=max(flights,key=len) if flights else []
    begin,end=(main[0],main[-1]) if main else (0,0)
    # Start two samples after contact release for a clean analytical free-flight check.
    fit=samples[begin+2:end-1]
    residuals=[];vel_res=[]
    def system_com(sample):
        masses={'car_body':c['chassis_mass_kg'],**{'wheel_'+str(j):c['wheel_mass_kg'] for j in range(4)}}
        mass=sum(masses.values())
        # The chassis body origin is not its center of mass; solver velocities already refer to the center of mass.
        x,y,z,w=sample['objects']['car_body']['quaternion_xyzw']
        arm=inverse_rotate([-x,-y,-z,w],[c['com_longitudinal_offset_m'],c['com_lateral_offset_m'],0.])
        location=[sum(masses[name]*sample['objects'][name]['location'][k] for name in masses)/mass+masses['car_body']*arm[k]/mass for k in range(3)]
        velocity=[sum(masses[name]*sample['objects'][name]['linear_velocity'][k] for name in masses)/mass for k in range(3)]
        return {'location':location,'linear_velocity':velocity}
    if fit:
        s0=fit[0];b0=system_com(s0);g=cfg['physics']['gravity']
        for s in fit:
            t=s['time_sec']-s0['time_sec'];b=system_com(s)
            expected=[b0['location'][k]+b0['linear_velocity'][k]*t+.5*g[k]*t*t for k in range(3)]
            residuals.append(norm([b['location'][k]-expected[k] for k in range(3)]))
            vel_res.append(norm([b['linear_velocity'][k]-b0['linear_velocity'][k]-g[k]*t for k in range(3)]))
    attach_error=0.
    offsets=wheel_positions(cfg)
    for s in samples:
        b=s['objects']['car_body']
        for j in range(4):
            delta=[s['objects']['wheel_'+str(j)]['location'][k]-b['location'][k] for k in range(3)]
            local=inverse_rotate(b['quaternion_xyzw'],delta)
            attach_error=max(attach_error,norm([local[k]-offsets[j][k] for k in range(3)]))
    track_end=cfg['physics']['track']['curve_start_x_m']+cfg['physics']['track']['curve_horizontal_length_m']
    # Geometric edge crossings are independent of force-threshold chatter at seams.
    front_cross=next((s['time_sec'] for s in samples if min(s['objects']['wheel_'+str(j)]['location'][0] for j in [0,1])>track_end),None)
    rear_cross=next((s['time_sec'] for s in samples if min(s['objects']['wheel_'+str(j)]['location'][0] for j in [2,3])>track_end),None)
    flight_height=[s['objects']['car_body']['location'][2] for s in samples[begin:end+1]]
    flight_vz=[s['objects']['car_body']['linear_velocity'][2] for s in samples[begin:end+1]]
    landing_time=contacts[first_floor]['time_sec'] if first_floor is not None else None
    rebound_height=0.
    rebound_com_rise=0.
    if first_floor is not None:
        for i in range(first_floor,min(len(samples),first_floor+round(.5*cfg['simulation_quality']['trajectory_hz']))):
            if not contacts[i]['wheels_on_floor']:
                lowest=min(samples[i]['objects']['wheel_'+str(j)]['location'][2]-c['wheel_radius_m'] for j in range(4))
                rebound_height=max(rebound_height,lowest)
        post=[bodies[i]['location'][2] for i in range(first_floor,min(len(samples),first_floor+round(.28*cfg['simulation_quality']['trajectory_hz'])))]
        trough=post[0]
        for height in post:
            rebound_com_rise=max(rebound_com_rise,height-trough)
            trough=min(trough,height)
    ground=bodies[first_floor+round(.55*cfg['simulation_quality']['trajectory_hz']):] if first_floor is not None else []
    departure=result.get('native_launch_state')
    ground_yaws=[abs(math.degrees(math.atan2(2*(b['quaternion_xyzw'][3]*b['quaternion_xyzw'][2]+b['quaternion_xyzw'][0]*b['quaternion_xyzw'][1]),1-2*(b['quaternion_xyzw'][1]**2+b['quaternion_xyzw'][2]**2)))) for b in bodies[first_floor or 0:]]
    exit_speed=norm(departure['objects']['car_body']['linear_velocity'] if departure else bodies[begin]['linear_velocity'])
    final_speed=norm(bodies[-1]['linear_velocity'])
    body_contacts=sum(s['body_contact'] for s in contacts)
    min_spin=min(max(abs(s['objects']['wheel_'+str(j)]['joint_velocity_rad_s']) for s in samples) for j in range(4))
    metrics={'front_axle_crosses_lip_sec':front_cross,'rear_axle_crosses_lip_sec':rear_cross,
        'free_flight_start_sec':samples[begin]['time_sec'],'free_flight_end_sec':samples[end]['time_sec'],
        'free_flight_duration_sec':len(main)/cfg['simulation_quality']['trajectory_hz'],
        'first_floor_contact_sec':landing_time,'apex_car_com_z_m':max(flight_height or [0.]),
        'ballistic_max_position_residual_m':max(residuals or [1.]),
        'ballistic_max_velocity_residual_m_s':max(vel_res or [1.]),
        'ballistic_reference':'mass-weighted center of mass of chassis and all four wheel bodies',
        'max_wheel_attachment_error_m':attach_error,'body_contact_samples':body_contacts,'maximum_heading_deviation_after_landing_deg':max(ground_yaws or [180.]),
        'measured_rebound_clearance_m':rebound_height,'measured_impact_rebound_com_rise_m':rebound_com_rise,'initial_speed_m_s':c['initial_speed_m_s'],
        'exit_speed_m_s':exit_speed,'exit_speed_measurement_time_sec':departure['time_sec'] if departure else samples[begin]['time_sec'],
        'exit_speed_measurement':'native last-rear-contact release' if departure else 'first free-flight output sample','final_speed_m_s':final_speed,
        'final_car_position_m':bodies[-1]['location'],'minimum_peak_wheel_spin_rad_s':min_spin,
        **result['quality']}
    checks={'exact_frame_count':len(result['frames'])==96 and result['fps']==24,
        'normal_gravity':cfg['physics']['gravity']==[0.,0.,-9.81],
        'front_then_rear_clear_edge':front_cross is not None and rear_cross is not None and front_cross<rear_cross,
        'sustained_free_flight':len(main)>=round(.18*cfg['simulation_quality']['trajectory_hz']),
        'flight_rises_and_falls':bool(flight_vz) and max(flight_vz)>.15 and min(flight_vz)<-.25,
        'parabolic_flight':metrics['ballistic_max_position_residual_m']<.001 and metrics['ballistic_max_velocity_residual_m_s']<.005,
        'wheel_contact_landing':landing_time is not None and landing_time<2.5,
        'no_chassis_ground_impact':body_contacts==0,
        'rigid_wheel_axle_attachments':attach_error<.00001,
        'zero_motor_torque':result['quality']['maximum_motor_torque_Nm']==0.,
        'wheels_rotate':min_spin>20.,
        'no_deep_penetration':result['quality']['maximum_track_penetration_m']<.0005 and result['quality']['maximum_tire_compression_on_floor_m']<.002,
        'forward_facing_rollout':bool(ground_yaws) and max(ground_yaws)<15.,
        'limited_lateral_drift':result['quality']['maximum_lateral_drift_m']<.12,
        'slight_impact_rebound':.004<max(rebound_height,rebound_com_rise)<.03,
        'rolls_forward_after_landing':bool(ground) and bodies[-1]['location'][0]-bodies[first_floor]['location'][0]>.35,
        'gradual_rollout_deceleration':bool(ground) and norm(ground[0]['linear_velocity'])>final_speed+.2 and final_speed<.20,
        'speed_decreases_on_ramp':.40*c['initial_speed_m_s']<exit_speed<c['initial_speed_m_s'],
        'unmodified_real_time':result['playback_rate']==1.,
        'passive_axle_pairs_remain_coupled':result['quality']['maximum_paired_axle_spin_difference_rad_s']<5.,
    }
    return {'schema_version':1,'accepted':all(checks.values()),'checks':checks,'metrics':metrics,
        'scope':'Numerical and engineering acceptance of this revised source; no counterfactual edit cases requested or claimed.'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('physics_json',type=Path);p.add_argument('--out',type=Path)
    a=p.parse_args();report=validate(json.loads(a.physics_json.read_text()))
    if a.out:save_json(a.out,report)
    print(json.dumps(report,indent=2));raise SystemExit(0 if report['accepted'] else 1)
