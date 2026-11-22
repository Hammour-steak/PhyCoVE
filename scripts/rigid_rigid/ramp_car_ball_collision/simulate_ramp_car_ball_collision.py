"""Gravity-only free chassis, four passive revolute wheels and a rigid sphere."""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__=='__main__':
    import sys as _sys
    from pathlib import Path as _Path
    if (_Path(__file__).resolve().parents[2]/'pcve_scene_entry.py').is_file():
        _sys.path.insert(0,str(_Path(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__,'simulate')
# PCVE_UNIFIED_ENTRY_END
import argparse
import csv
import importlib.metadata
import math
from pathlib import Path
import time
import pybullet as p
from scene_config import configured_scenario,profile,ramp_end_x,initial_car_pose,wheel_positions,car_collision_boxes,signature,save_json,CONTACT_REFERENCE

def simulate(cfg):
    begin=time.monotonic();client=p.connect(p.DIRECT)
    try:
        ph=cfg['physics'];c=ph['car'];b=ph['ball'];q=cfg['simulation_quality'];r=cfg['render']
        sub=q['substeps_per_frame'];dt=1/(r['fps']*sub);total=round(r['duration_sec']/dt)
        p.resetSimulation();p.setGravity(*ph['gravity']);p.setTimeStep(dt)
        p.setPhysicsEngineParameter(numSolverIterations=q['solver_iterations'],numSubSteps=0,
            deterministicOverlappingPairs=1,contactBreakingThreshold=q['contact_breaking_threshold_m'],
            contactSlop=q['contact_slop_m'],contactERP=q['contact_erp'],useSplitImpulse=1,
            splitImpulsePenetrationThreshold=0.,enableConeFriction=1,
            restitutionVelocityThreshold=q['restitution_velocity_threshold_m_s'])
        floor=p.createMultiBody(0,p.createCollisionShape(p.GEOM_BOX,halfExtents=[6.,4.,.06]),basePosition=[1.,0.,-.06])
        def static_material(body,mat):
            p.changeDynamics(body,-1,**{k:mat[k] for k in ['restitution']},lateralFriction=mat['lateral_friction'],
                rollingFriction=mat['rolling_friction'],spinningFriction=mat['spinning_friction'],collisionMargin=0.)
        static_material(floor,ph['floor']);ramps=[];rp=ph['ramp']
        for (x0,z0),(x1,z1) in zip(profile(cfg),profile(cfg)[1:]):
            angle=math.atan2(z1-z0,x1-x0);thick=rp['thickness_m']
            shape=p.createCollisionShape(p.GEOM_BOX,halfExtents=[math.hypot(x1-x0,z1-z0)/2,rp['width_m']/2,thick/2])
            body=p.createMultiBody(0,shape,basePosition=[(x0+x1)/2+math.sin(angle)*thick/2,0.,(z0+z1)/2-math.cos(angle)*thick/2],
                baseOrientation=p.getQuaternionFromEuler([0.,-angle,0.]))
            static_material(body,rp);ramps.append(body)
        common={'linearDamping':0.,'angularDamping':0.,'activationState':p.ACTIVATION_STATE_DISABLE_SLEEPING,'collisionMargin':q['collision_margin_m']}
        wr=c['wheel_radius_m'];car=None
        if c.get('present',True):
            boxes=car_collision_boxes()
            chassis=p.createCollisionShapeArray(shapeTypes=[p.GEOM_BOX]*len(boxes),halfExtents=[v[0] for v in boxes],collisionFramePositions=[v[1] for v in boxes])
            wheel=p.createCollisionShape(p.GEOM_CYLINDER,radius=c['wheel_radius_m'],height=c['wheel_width_m'],
                collisionFrameOrientation=p.getQuaternionFromEuler([math.pi/2,0.,0.]))
            xyz,theta=initial_car_pose(cfg)
            car=p.createMultiBody(baseMass=c['chassis_mass_kg'],baseCollisionShapeIndex=chassis,
                basePosition=xyz,baseOrientation=p.getQuaternionFromEuler([0.,theta,0.]),
                linkMasses=[c['wheel_mass_kg']]*4,linkCollisionShapeIndices=[wheel]*4,linkVisualShapeIndices=[-1]*4,
                linkPositions=wheel_positions(cfg),linkOrientations=[[0.,0.,0.,1.]]*4,
                linkInertialFramePositions=[[0.,0.,0.]]*4,linkInertialFrameOrientations=[[0.,0.,0.,1.]]*4,
                linkParentIndices=[0]*4,linkJointTypes=[p.JOINT_REVOLUTE]*4,linkJointAxis=[[0.,1.,0.]]*4)
            p.changeDynamics(car,-1,mass=c['chassis_mass_kg'],localInertiaDiagonal=c['chassis_inertia_kg_m2'],
                lateralFriction=c['chassis_lateral_friction'],restitution=c['bumper_restitution'],rollingFriction=0.,spinningFriction=0.,**common)
            wr=c['wheel_radius_m'];wm=c['wheel_mass_kg'];ww=c['wheel_width_m']
            wi=[wm*(3*wr*wr+ww*ww)/12,.5*wm*wr*wr,wm*(3*wr*wr+ww*ww)/12]
            for j in range(4):
                p.setJointMotorControl2(car,j,p.VELOCITY_CONTROL,force=0.)
                p.resetJointState(car,j,0.,c['initial_wheel_angular_velocity'])
                p.changeDynamics(car,j,localInertiaDiagonal=wi,lateralFriction=c['tire_lateral_friction'],
                    restitution=c['tire_restitution'],rollingFriction=c['tire_rolling_friction'],spinningFriction=c['tire_spinning_friction'],
                    jointDamping=c['axle_damping_Nms'])
            p.resetBaseVelocity(car,c['initial_linear_velocity'],c['initial_angular_velocity'])
        ball=None
        if b['present']:
            ball=p.createMultiBody(b['mass_kg'],p.createCollisionShape(p.GEOM_SPHERE,radius=b['radius_m']),
                basePosition=b['initial_position_m'],baseOrientation=b['initial_quaternion_xyzw'])
            bi=b['inertia_factor']*b['mass_kg']*b['radius_m']**2
            p.changeDynamics(ball,-1,localInertiaDiagonal=[bi]*3,lateralFriction=b['lateral_friction'],restitution=b['restitution'],
                rollingFriction=b['rolling_friction'],spinningFriction=b['spinning_friction'],
                ccdSweptSphereRadius=b['radius_m']*.8,contactProcessingThreshold=0.,**common)
            p.resetBaseVelocity(ball,b['initial_linear_velocity'],b['initial_angular_velocity'])
        def body_state(body):
            pos,quat=p.getBasePositionAndOrientation(body);v,w=p.getBaseVelocity(body)
            return {'location':list(pos),'quaternion_xyzw':list(quat),'linear_velocity':list(v),'angular_velocity':list(w)}
        def state():
            out={}
            if car is not None:
                out['car_body']=body_state(car)
                for j in range(4):
                    st=p.getLinkState(car,j,computeLinkVelocity=1,computeForwardKinematics=1);js=p.getJointState(car,j)
                    out['wheel_'+str(j)]={'location':list(st[0]),'quaternion_xyzw':list(st[1]),'linear_velocity':list(st[6]),'angular_velocity':list(st[7]),'joint_angle_rad':js[0],'joint_velocity_rad_s':js[1],'motor_torque_Nm':js[3]}
            if ball is not None:out['ball']=body_state(ball)
            return out
        def dynamics(body,link):
            d=p.getDynamicsInfo(body,link)
            return {'mass_kg':d[0],'inertia_diagonal_kg_m2':list(d[2]),'lateral_friction':d[1],'restitution':d[5],'rolling_friction':d[6],'spinning_friction':d[7],'shape_margin_readback_m':d[11]}
        actual={'car_body':dynamics(car,-1),**{'wheel_'+str(j):dynamics(car,j) for j in range(4)}} if car is not None else {}
        if ball is not None:actual['ball']=dynamics(ball,-1)
        # PyBullet 3.2.7 global body flags (activation/damping) in a link update can
        # silently address the base. Keep those in the base-only call and audit readback.
        if car is not None:
            assert actual['car_body']['inertia_diagonal_kg_m2']==c['chassis_inertia_kg_m2']
            assert actual['car_body']['restitution']==c['bumper_restitution']
            for j in range(4):
                assert actual['wheel_'+str(j)]['restitution']==c['tire_restitution']
                assert actual['wheel_'+str(j)]['lateral_friction']==c['tire_lateral_friction']
        # All nearby environment items are outside swept bounds; static room proxies remain in the solver.
        environment=[]
        for half,center in [([1.0,.42,.39],[.5,1.65,.39]),([.28,.22,.18],[-.85,.65,.18]),([.04,4.,1.4],[-2.5,0.,1.4]),([5.,.04,1.4],[1.,3.,1.4])]:
            environment.append(p.createMultiBody(0,p.createCollisionShape(p.GEOM_BOX,halfExtents=half),basePosition=center))
        p.performCollisionDetection();initial=state()
        init_contacts=p.getContactPoints(bodyA=car) if car is not None else []
        initial_support=sorted({v[3] for v in init_contacts if v[2] in ramps and v[3]>=0 and v[8]<.00005})
        initial_penetration=max([max(0.,-v[8]) for v in p.getContactPoints()] or [0.])
        frames=[];samples=[];events=[];episodes=[];active=None;first=None;exit_ramp=None
        interventions=[];remove_time=c.get('remove_at_sec')
        remove_tick=round(remove_time/dt) if remove_time is not None else None
        if remove_time is not None:
            assert c.get('present',True) and 0.<remove_time<r['duration_sec']
            assert abs(remove_tick*dt-remove_time)<1e-12
        stats={'maximum_penetration_m':0.,'maximum_ball_car_penetration_m':0.,'maximum_lateral_drift_m':0.,
            'maximum_motor_torque_Nm':0.,'maximum_speed_m_s':0.,'maximum_flat_preimpact_wheel_gap_m':0.,
            'maximum_energy_J':0.,'maximum_step_energy_gain_J':0.,'longest_all_wheel_flight_s':0.,'maximum_preimpact_rolling_slip_m_s':0.}
        initial_energy=None;last_energy=None;flight=0.;previous=initial;first_post=None
        stride=round(1/(q['trajectory_hz']*dt));assert abs(stride*dt-1/q['trajectory_hz'])<1e-12
        # Every pose and velocity is read from the solver; no runtime velocity reset or applied force.
        for tick in range(total+1):
            t=tick*dt
            if tick:p.stepSimulation()
            if tick==remove_tick:
                before=state();removed_id=car
                p.removeBody(car);car=None
                after=state()
                interventions.append({'kind':'remove_body','target':'car','time_sec':t,'simulation_tick':tick,
                    'first_absent_frame':round(t*r['fps'])+1,'removed_multibody_id':removed_id,
                    'removed_object_ids':['car_body','wheel_0','wheel_1','wheel_2','wheel_3'],
                    'state_immediately_before':before,'state_immediately_after':after,
                    'remaining_state_unchanged':all(before[k]==v for k,v in after.items()),
                    'body_absent_from_solver':removed_id not in [p.getBodyUniqueId(j) for j in range(p.getNumBodies())]})
            current=state();contacts=p.getContactPoints(bodyA=car) if car is not None else []
            pair=[v for v in contacts if ball is not None and v[2]==ball and v[9]>1e-7]
            support=[v for v in contacts if v[2] in ramps+[floor] and v[3]>=0 and v[9]>1e-7]
            floor_wheels={v[3] for v in support if v[2]==floor}
            if exit_ramp is None and len(floor_wheels)==4 and all(current['wheel_'+str(j)]['location'][0]-wr>ramp_end_x(cfg) for j in range(4)):
                exit_ramp={'time_sec':t,'car_position_m':current['car_body']['location'],'car_velocity_m_s':current['car_body']['linear_velocity']}
            if pair and active is None:
                v=max(pair,key=lambda z:z[9]);active={'start_sec':t,'end_sec':t,'impulse_Ns':0.,'minimum_distance_m':v[8]}
                event={'kind':'car_ball_contact','time_sec':t,'position_m':list(v[6]),'car_link':v[3],
                    'car_point_m':list(v[5]),'ball_point_m':list(v[6]),'normal_on_ball':list(v[7]),
                    'preimpact_time_sec':max(0.,t-dt),'preimpact':previous,'at_contact':current}
                events.append(event)
                if first is None:first=event
                episodes.append(active)
            if pair:
                active['end_sec']=t;active['impulse_Ns']+=sum(v[9] for v in pair)*dt
                active['minimum_distance_m']=min(active['minimum_distance_m'],min(v[8] for v in pair))
            elif active is not None:active=None
            if first and first_post is None and t>=first['time_sec']+.03:
                first_post={'time_sec':t,'objects':current}
            cps=p.getContactPoints();pen=max([max(0.,-v[8]) for v in cps] or [0.])
            stats['maximum_penetration_m']=max(stats['maximum_penetration_m'],pen)
            stats['maximum_ball_car_penetration_m']=max(stats['maximum_ball_car_penetration_m'],max([max(0.,-v[8]) for v in pair] or [0.]))
            if car is not None:stats['maximum_lateral_drift_m']=max(stats['maximum_lateral_drift_m'],abs(current['car_body']['location'][1]))
            for obj in current.values():stats['maximum_speed_m_s']=max(stats['maximum_speed_m_s'],math.sqrt(sum(v*v for v in obj['linear_velocity'])))
            if car is not None:stats['maximum_motor_torque_Nm']=max(stats['maximum_motor_torque_Nm'],*[abs(current['wheel_'+str(j)]['motor_torque_Nm']) for j in range(4)])
            if car is not None and tick and not support:flight+=dt;stats['longest_all_wheel_flight_s']=max(stats['longest_all_wheel_flight_s'],flight)
            else:flight=0.
            if car is not None and exit_ramp and first is None:
                for j in range(4):
                    w=current['wheel_'+str(j)];stats['maximum_flat_preimpact_wheel_gap_m']=max(stats['maximum_flat_preimpact_wheel_gap_m'],w['location'][2]-wr)
                    if .08<t and abs(w['linear_velocity'][0])>.1:
                        slip=abs(w['linear_velocity'][0]-w['joint_velocity_rad_s']*wr)
                        stats['maximum_preimpact_rolling_slip_m_s']=max(stats['maximum_preimpact_rolling_slip_m_s'],slip)
            energy=0.
            for name,obj in current.items():
                d=actual[name];v=obj['linear_velocity'];w=obj['angular_velocity'];mat=p.getMatrixFromQuaternion(obj['quaternion_xyzw'])
                local=[sum(mat[k*3+j]*w[k] for k in range(3)) for j in range(3)]
                energy+=d['mass_kg']*(9.81*obj['location'][2]+.5*sum(z*z for z in v))+.5*sum(I*z*z for I,z in zip(d['inertia_diagonal_kg_m2'],local))
            if initial_energy is None:initial_energy=energy
            stats['maximum_energy_J']=max(stats['maximum_energy_J'],energy)
            if last_energy is not None:stats['maximum_step_energy_gain_J']=max(stats['maximum_step_energy_gain_J'],energy-last_energy)
            last_energy=energy
            if tick%stride==0:samples.append({'time_sec':t,'objects':current,'energy_J':energy,'wheel_support':sorted({v[3] for v in support})})
            if tick%sub==0 and tick//sub<round(r['fps']*r['duration_sec']):
                frames.append({'frame_index':tick//sub+1,'time_sec':t,'objects':current})
            previous=current
        if first:first['postimpact_30ms']=first_post
        x0=b['initial_position_m'][0];bs=[v['objects']['ball'] for v in samples] if ball is not None else []
        ball_path=sum(math.dist(a['location'][:2],z['location'][:2]) for a,z in zip(bs,bs[1:]))
        grouped=[]
        for ep in episodes:
            if grouped and ep['start_sec']-grouped[-1]['end_sec']<.005:
                grouped[-1]['end_sec']=ep['end_sec'];grouped[-1]['impulse_Ns']+=ep['impulse_Ns']
                grouped[-1]['minimum_distance_m']=min(grouped[-1]['minimum_distance_m'],ep['minimum_distance_m']);grouped[-1]['solver_interval_count']+=1
            else:grouped.append({**ep,'solver_interval_count':1})
        outcome={'ramp_exit':exit_ramp,'first_collision':first,'contact_episodes':grouped,'raw_solver_contact_intervals':episodes,
            'contact_episode_definition':'Native positive-normal-force intervals grouped when separation in time is less than 5 ms; raw solver intervals retained.',
            'secondary_contact_count':max(0,len(grouped)-1),'raw_contact_interval_count':len(episodes),'ball_forward_displacement_m':bs[-1]['location'][0]-x0 if bs else None,
            'ball_surface_path_m':ball_path if bs else None,'car_final_position_m':current['car_body']['location'] if car is not None else None,
            'car_final_velocity_m_s':current['car_body']['linear_velocity'] if car is not None else None,
            'car_post_collision_displacement_m':current['car_body']['location'][0]-first['at_contact']['car_body']['location'][0] if first and car is not None else None,
            'ball_final_velocity_m_s':bs[-1]['linear_velocity'] if bs else None,
            'ball_max_abs_angular_velocity_rad_s':max([math.sqrt(sum(z*z for z in v['angular_velocity'])) for v in bs] or [0.])}
        return {'schema_version':1,'scene':'ramp_car_ball_collision','solver':{'name':'PyBullet','version':importlib.metadata.version('pybullet'),'api':p.getAPIVersion(),
            'contact_reference':CONTACT_REFERENCE,'restitution_rule':'eA * eB','lateral_friction_rule':'clamp(muA * muB, -10, 10)',
            'rolling_friction_rule':'clamp(rollingA * muB + rollingB * muA, -10, 10)',
            'rolling_resistance_model':'Native Bullet load-limited rolling/spinning contact constraints; passive jointDamping on four revolute axles. Zero body linear/angular damping.'},
            'configuration':cfg,'configuration_sha256':signature(cfg),'dt_sec':dt,'simulation_wall_sec':time.monotonic()-begin,
            'initial_state':initial,'initial_wheel_support_links':initial_support,'initial_max_penetration_m':initial_penetration,
            'actual_dynamics':actual,'initial_energy_J':initial_energy,'final_energy_J':last_energy,'diagnostics':stats,
            'outcome':outcome,'contact_events':events,'intervention_events':interventions,'frames':frames,'trajectory_samples':samples,'frame_end':len(frames),
            'implementation':{'free_base_dofs':6,'independent_passive_wheel_hinges':4,'motor_force_limit_Nm':0.,'runtime_external_forces':False,
                'velocity_resets_after_start':0,'trajectory_driving':False,'render_replay_only':True}}
    finally:p.disconnect(client)

def export_csv(path,result):
    with Path(path).open('w') as f:
        w=csv.writer(f);w.writerow(['time_sec','object_id','x','y','z','qx','qy','qz','qw','vx','vy','vz','wx','wy','wz','joint_angle_rad','joint_velocity_rad_s'])
        for s in result['trajectory_samples']:
            for name,o in s['objects'].items():w.writerow([s['time_sec'],name,*o['location'],*o['quaternion_xyzw'],*o['linear_velocity'],*o['angular_velocity'],o.get('joint_angle_rad',''),o.get('joint_velocity_rad_s','')])

def main():
    pa=argparse.ArgumentParser();pa.add_argument('--out',type=Path,required=True);pa.add_argument('--case',choices=list(__import__('scene_config').CASES),default='source');pa.add_argument('--overrides-json',type=Path);pa.add_argument('--configuration-json',type=Path)
    a=pa.parse_args();import json
    cfg=configured_scenario(a.case,a.configuration_json,json.loads(a.overrides_json.read_text()) if a.overrides_json else None)
    result=simulate(cfg);save_json(a.out,result);export_csv(a.out.with_name('trajectory.csv'),result)
    print(json.dumps({'out':str(a.out),'wall_sec':result['simulation_wall_sec'],'diagnostics':result['diagnostics'],'outcome':{k:v for k,v in result['outcome'].items() if k!='first_collision'},'initial_support':result['initial_wheel_support_links']}))

if __name__=='__main__':main()
