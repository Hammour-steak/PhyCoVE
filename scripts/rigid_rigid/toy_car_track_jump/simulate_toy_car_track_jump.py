"""Free 6-DOF rigid toy car with four wheels on two unpowered rigid axles, solved in MuJoCo."""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == '__main__':
    import sys as _sys
    from pathlib import Path as _Path
    if (_Path(__file__).resolve().parents[2]/'pcve_scene_entry.py').is_file():
        _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__, 'simulate')
# PCVE_UNIFIED_ENTRY_END
import argparse
import csv
import importlib.metadata
import hashlib
import json
import math
from pathlib import Path
import time
import mujoco
import numpy as np
from scene_config import track_profile, chassis_boxes, launcher_colliders, save_json, signature

def build_model(cfg):
    ph,sq=cfg['physics'],cfg['simulation_quality'];c,tr,fl=ph['car'],ph['track'],ph['floor']
    # Direct (negative) solref: the contact behaves as a damped spring, so landing energy returns as a real rebound.
    k=fl['contact_stiffness_1_s2'];floor_solref='-%.6g -%.6g'%(k,2*fl['contact_damping_ratio']*math.sqrt(k))
    deck_solref='%.6g 1'%sq['deck_contact_time_constant_s']
    solimp='0.99 0.999 1e-5 0.5 2'
    def friction(mat):return '%.6g %.6g %.6g'%(mat['lateral_friction'],mat['spinning_friction'],mat['rolling_friction'])
    def segment(name,x0,z0,x1,z1,y,half_y,bottom,top):
        # A box between two profile samples, spanning bottom..top along the local normal.
        angle=math.atan2(z1-z0,x1-x0);nx,nz=-math.sin(angle),math.cos(angle);mid=(bottom+top)/2
        length=math.hypot(x1-x0,z1-z0)/2+sq['deck_segment_overlap_m']
        return ('<geom name="%s" type="box" pos="%.9f %.9f %.9f" euler="0 %.9f 0" size="%.9f %.9f %.9f"/>'
            %(name,(x0+x1)/2+nx*mid,y,(z0+z1)/2+nz*mid,-math.degrees(angle),length,half_y,(top-bottom)/2))
    profile=track_profile(cfg);deck=[];rails=[]
    for i,((x0,z0),(x1,z1)) in enumerate(zip(profile,profile[1:])):
        deck.append(segment('deck_%d'%i,x0,z0,x1,z1,0.,tr['width_m']/2,-tr['thickness_m'],0.))
        for side,sign in [('l',1),('r',-1)]:
            rails.append(segment('rail_%s_%d'%(side,i),x0,z0,x1,z1,sign*(tr['width_m']+tr['edge_width_m'])/2,tr['edge_width_m']/2,-tr['thickness_m'],tr['edge_height_m']))
    # Lying along the axle, a capsule keeps the tire's flat stance without a cylinder's sharp rims.
    half=c['tire_contact_half_width_m'];wheels=[]
    def axle(name,x):
        geoms=''.join('<geom name="%s_%d" type="capsule" size="%.9f" fromto="0 %.9f 0 0 %.9f 0"/>'%(name,j,c['wheel_radius_m'],y-half,y+half)
            for j,y in enumerate([-c['wheel_center_track_m']/2,c['wheel_center_track_m']/2]))
        wr,wm,ww=c['wheel_radius_m'],c['wheel_mass_kg'],c['wheel_width_m']
        # Parallel-axis theorem for the pair of wheels around the axle midpoint.
        across=wm*(3*wr*wr+ww*ww)/12+wm*(c['wheel_center_track_m']/2)**2
        return ('<body name="%s" pos="%.9f 0 %.9f"><joint name="%s_spin" type="hinge" axis="0 1 0" damping="%.6g" frictionloss="%.6g"/>'
            '<inertial pos="0 0 0" mass="%.9f" diaginertia="%.12g %.12g %.12g"/>%s</body>'
            %(name,x,-c['com_above_axle_m'],name,c['axle_damping_Nms'],c['axle_friction_Nm'],2*wm,2*across,wm*wr*wr,2*across,geoms))
    mass,length,width,height=c['chassis_mass_kg'],c['length_m'],c['body_width_m'],.07*c['length_m']/.38
    x2=length*length*c['longitudinal_second_moment_factor']/12;y2=width*width*c['transverse_second_moment_factor']/12
    inertia=[mass*(y2+height*height/12),mass*(x2+height*height/12),mass*(x2+y2)]
    shell=''.join('<geom name="chassis_%d" type="box" size="%.9f %.9f %.9f" pos="%.9f %.9f %.9f"/>'%(i,*half_size,*pos) for i,(half_size,pos) in enumerate(chassis_boxes(cfg)))
    start=tr['deck_z_m']+c['wheel_radius_m']+c['com_above_axle_m']
    launcher=''
    if ph['launcher']['collisions_enabled']:
        launcher=''.join('<geom name="%s" type="box" pos="%.9f %.9f %.9f" size="%.9f %.9f %.9f"/>'%(name,*pos,*[v/2 for v in size]) for name,pos,size in launcher_colliders(cfg))
    xml = f'''<mujoco model="toy_car_track_jump">
  <option timestep="{sq['timestep_s']}" gravity="{ph['gravity'][0]} {ph['gravity'][1]} {ph['gravity'][2]}" integrator="implicitfast" cone="elliptic" impratio="{sq['impratio']}" iterations="{sq['solver_iterations']}" tolerance="1e-10"/>
  <default><geom solimp="{solimp}" condim="3"/><default class="deck"><geom priority="1" condim="6" friction="{friction(tr)}" solref="{deck_solref}"/></default><default class="launcher"><geom priority="1" condim="6" friction="{friction(ph['launcher'])}" solref="{deck_solref}"/></default></default>
  <worldbody>
    <geom name="floor" type="plane" size="0 0 1" priority="2" condim="6" friction="{friction(fl)}" solref="{floor_solref}"/>
    <frame childclass="deck">{''.join(deck)}{''.join(rails)}</frame>
    <frame childclass="launcher">{launcher}</frame>
    <body name="car" pos="{c['initial_x_m']} {c['initial_y_m']} {start}">
      <freejoint name="car_free"/>
      <inertial pos="{c['com_longitudinal_offset_m']} {c['com_lateral_offset_m']} 0" mass="{mass}" diaginertia="{inertia[0]} {inertia[1]} {inertia[2]}"/>
      {shell}
      {axle('axle_0',c['wheelbase_m']/2)}
      {axle('axle_1',-c['wheelbase_m']/2)}
    </body>
  </worldbody>
</mujoco>'''
    if not c.get('present',True):
        begin=xml.index('    <body name="car"')
        end=xml.index('\n  </worldbody>',begin)
        xml=xml[:begin]+xml[end:]
    return xml

def simulate(cfg,case_id='source'):
    begin=time.perf_counter()
    ph,sq,rd=cfg['physics'],cfg['simulation_quality'],cfg['render'];c=ph['car']
    model=mujoco.MjModel.from_xml_string(build_model(cfg));data=mujoco.MjData(model)
    dt=sq['timestep_s'];per_frame=round(1/(rd['fps']*dt));per_sample=round(1/(sq['trajectory_hz']*dt))
    assert abs(per_frame*rd['fps']*dt-1)<1e-9 and per_frame%per_sample==0
    count=round(rd['duration_sec']/dt)
    if not c.get('present',True):
        assert model.nv==0 and model.nq==0
        samples=[{'time_sec':i/sq['trajectory_hz'],'objects':{}} for i in range(round(rd['duration_sec']*sq['trajectory_hz'])+1)]
        frames=[{'frame_index':i+1,'time_sec':i/rd['fps'],'objects':{}} for i in range(round(rd['duration_sec']*rd['fps']))]
        return {'schema_version':3,'scene':'toy_car_track_jump','category':'rigid_rigid','case_id':case_id,'configuration':cfg,
                'configuration_sha256':signature(cfg),'fps':rd['fps'],'frame_start':1,'frame_end':len(frames),'playback_rate':1.,
                'solver':{'name':'MuJoCo','version':importlib.metadata.version('mujoco'),'model':'Static track and floor; car and all wheels absent.','dynamic_dofs':int(model.nv)},
                'track_profile_m':track_profile(cfg),'native_launch_state':None,'initial_state':samples[0],
                'frames':frames,'trajectory_samples':samples,'contact_samples':[],'contact_events':[],'applied_interventions':[],
                'quality':{'maximum_track_penetration_m':0.,'maximum_tire_compression_on_floor_m':0.,'maximum_lateral_drift_m':0.,'maximum_motor_torque_Nm':0.,'maximum_paired_axle_spin_difference_rad_s':0.},
                'simulation_wall_sec':time.perf_counter()-begin}
    def gid(name):return mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_GEOM,name)
    def bid(name):return mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_BODY,name)
    def jid(name):return mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_JOINT,name)
    car=bid('car');axles=[bid('axle_0'),bid('axle_1')]
    hinge=[(model.jnt_qposadr[jid(n+'_spin')],model.jnt_dofadr[jid(n+'_spin')]) for n in ['axle_0','axle_1']]
    role={}
    for g in range(model.ngeom):
        name=mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_GEOM,g)
        role[g]=name
    # One launch impulse before frame 1: forward speed, the launcher's small misalignment, matching wheel spin.
    data.qvel[:3]=[c['initial_speed_m_s'],c['initial_lateral_speed_m_s'],0.];data.qvel[5]=c['initial_yaw_rate_rad_s']
    for _,dof in hinge:data.qvel[dof]=c['initial_speed_m_s']/c['wheel_radius_m']
    mujoco.mj_forward(model,data)
    def velocity(body):
        out=np.zeros(6);mujoco.mj_objectVelocity(model,data,mujoco.mjtObj.mjOBJ_BODY,body,out,0)
        return out[3:].tolist(),out[:3].tolist()
    def xyzw(body):
        w,x,y,z=data.xquat[body];return [float(x),float(y),float(z),float(w)]
    def state(t):
        v,w=velocity(car)
        out={'time_sec':t,'objects':{'car_body':{'location':data.xpos[car].tolist(),'quaternion_xyzw':xyzw(car),'linear_velocity':v,'angular_velocity':w}}}
        for a,body in enumerate(axles):
            va,wa=velocity(body);rot=data.xmat[body].reshape(3,3)
            for side,y in enumerate([-c['wheel_center_track_m']/2,c['wheel_center_track_m']/2]):
                r=rot@np.array([0.,y,0.])
                out['objects']['wheel_'+str(2*a+side)]={'location':(data.xpos[body]+r).tolist(),'quaternion_xyzw':xyzw(body),
                    'linear_velocity':(np.array(va)+np.cross(wa,r)).tolist(),'angular_velocity':wa,'native_axle_link':a,
                    'joint_angle_rad':float(data.qpos[hinge[a][0]]),'joint_velocity_rad_s':float(data.qvel[hinge[a][1]]),'motor_torque_Nm':0.}
        return out
    def contacts_now():
        track,floor,other,launchers=set(),set(),set(),set();body=False;force=0.;deepest_track=deepest_floor=deepest_body=0.;wrench=np.zeros(6)
        for i in range(data.ncon):
            con=data.contact[i];a,b=role[con.geom1],role[con.geom2]
            tire=a if a.startswith(('axle','chassis')) else b;world=b if tire==a else a
            if not tire.startswith(('axle','chassis')):continue
            mujoco.mj_contactForce(model,data,i,wrench);force+=abs(wrench[0])
            if wrench[0]<=1e-7:continue
            depth=max(0.,-con.dist)
            if world.startswith('launcher_'):launchers.add(tire+'/'+world)
            if tire.startswith('chassis'):body=True;deepest_body=max(deepest_body,depth);continue
            wheel=2*int(tire[5])+int(tire[7])
            if world=='floor':floor.add(wheel);deepest_floor=max(deepest_floor,depth)
            elif world.startswith('deck'):track.add(wheel);deepest_track=max(deepest_track,depth)
            else:other.add(wheel)
        return track,floor,other,body,force,deepest_track,deepest_floor,deepest_body,launchers
    samples,frames,records,events=[],[],[],[]
    applied=[]
    deck_ids=[g for g,name in role.items() if name.startswith(('deck_','rail_'))]
    lip=track_profile(cfg)[-1][0];launch=None;refined=None
    interval=[set(),set(),set(),False,0.,set()];max_track=max_floor=max_side=max_body=0.
    previous={'front_on_track':True,'rear_on_track':True,'on_floor':False,'body_contact':False,'on_launcher':False}
    for step in range(count+1):
        t=step*dt
        if step:mujoco.mj_step(model,data)
        for intervention in ph.get('interventions',[]):
            if any(e['id']==intervention['id'] for e in applied):continue
            if intervention['type']!='set_track_friction':raise ValueError('Unsupported intervention')
            if t+1e-12<intervention['trigger']['time_sec']:continue
            params=intervention['parameters']
            old=model.geom_friction[deck_ids[0]].copy().tolist()
            value=[params['lateral_friction'],params['spinning_friction'],params['rolling_friction']]
            position_before=data.qpos.copy();velocity_before=data.qvel.copy()
            for g in deck_ids:model.geom_friction[g]=value
            # mj_step rebuilds contacts with these parameters on the next integration
            # step. Do not refresh cached poses only in this case: that would shift
            # its exported state by one solver step relative to the source.
            assert np.array_equal(position_before,data.qpos) and np.array_equal(velocity_before,data.qvel)
            applied.append({'id':intervention['id'],'type':intervention['type'],'time_sec':t,'frame_float':1+t*rd['fps'],
                'geom_count':len(deck_ids),'before_friction':old,'after_friction':model.geom_friction[deck_ids[0]].tolist(),
                'friction_order':['sliding_dimensionless','torsional_m','rolling_m'],'state_at_activation':state(t),
                'positions_and_velocities_preserved_at_activation':True})
        tk,fl_,ot,bd,force,dt_,df_,db_,la_=contacts_now()
        interval[0]|=tk;interval[1]|=fl_;interval[2]|=ot;interval[3]=interval[3] or bd;interval[4]=max(interval[4],force)
        interval[5]|=la_
        max_track=max(max_track,dt_);max_floor=max(max_floor,df_);max_body=max(max_body,db_)
        center=data.xpos[car];max_side=max(max_side,abs(float(center[1])))
        status={'front_on_track':bool(tk&{0,1}),'rear_on_track':bool(tk&{2,3}),'on_floor':bool(fl_),'body_contact':bd,'on_launcher':bool(la_)}
        if not tk and previous['rear_on_track'] and not fl_:launch=state(t)
        for flag,value in status.items():
            if value!=previous[flag]:
                events.append({'time_sec':t,'frame_float':1+t*rd['fps'],'event':flag,'active':value,'car_position_m':center.tolist(),'wheels_on_track':sorted(tk),'wheels_on_floor':sorted(fl_)})
        previous=status
        if step%per_sample==0:
            samples.append(state(t))
            records.append({'time_sec':t,'wheels_on_track':sorted(interval[0]),'wheels_on_floor':sorted(interval[1]),'other_contacts':sorted(interval[2]),
                'body_contact':interval[3],'peak_normal_force_N':interval[4],'launcher_contacts':sorted(interval[5]),'aggregation':'union over preceding 1/240 s interval'})
            interval=[set(),set(),set(),False,0.,set()]
        if step%per_frame==0 and step<count:frames.append({'frame_index':step//per_frame+1,**samples[-1]})
    return {'schema_version':3,'scene':'toy_car_track_jump','category':'rigid_rigid','case_id':case_id,
        'configuration':cfg,'configuration_sha256':signature(cfg),'fps':rd['fps'],'frame_start':1,'frame_end':len(frames),'playback_rate':1.,
        'solver':{'name':'MuJoCo','version':importlib.metadata.version('mujoco'),
            'model':'free 6-DOF chassis, two passive hinge axles with four rigid wheel components; static deck, rails and floor',
            'tire_contact_proxy':'capsule of the tire radius along each axle stub',
            'runtime_forces':'gravity, contact, rolling friction and passive axle friction only',
            'initial_conditions':'single initial velocity with a small launcher misalignment and matching wheel spins; no subsequent velocity resets',
            'timestep_s':dt,'native_revolute_axles':2,'rigid_wheel_components':4},
        'track_profile_m':track_profile(cfg),'native_launch_state':launch,'initial_state':samples[0],
        'frames':frames,'trajectory_samples':samples,'contact_samples':records,'contact_events':events,'applied_interventions':applied,
        'quality':{'maximum_track_penetration_m':max_track,'maximum_chassis_penetration_m':max_body,'maximum_tire_compression_on_floor_m':max_floor,'maximum_lateral_drift_m':max_side,'maximum_motor_torque_Nm':0.,'maximum_paired_axle_spin_difference_rad_s':0.},
        'simulation_wall_sec':time.perf_counter()-begin}

def export_csv(path,result):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with Path(path).open('w',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['time_s','x_m','y_m','z_m','qx','qy','qz','qw','vx_m_s','vy_m_s','vz_m_s','wx_rad_s','wy_rad_s','wz_rad_s'])
        for s in result['trajectory_samples']:
            if 'car_body' not in s['objects']:continue
            b=s['objects']['car_body']
            writer.writerow([s['time_sec'],*b['location'],*b['quaternion_xyzw'],*b['linear_velocity'],*b['angular_velocity']])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--scenario-overrides-json',type=Path)
    from counterfactual_cases import CASE_IDS,case_configuration
    parser.add_argument('--case',choices=CASE_IDS,default='source')
    a=parser.parse_args()
    result=simulate(case_configuration(a.case,json.loads(a.scenario_overrides_json.read_text()) if a.scenario_overrides_json else None),a.case)
    save_json(a.out,result)
    export_csv(a.out.with_name('trajectory.csv'),result)
    save_json(a.out.with_name('contacts.json'),result['contact_events'])
    print(json.dumps({'quality':result['quality'],'simulation_wall_sec':result['simulation_wall_sec']},indent=2))

if __name__=='__main__':
    main()
