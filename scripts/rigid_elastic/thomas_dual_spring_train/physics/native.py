"""Passive guided-coil / rigid train dynamics in MuJoCo 3.3.7 (CPU).

The wooden grooves reduce the train's chassis to longitudinal translation.
Six revolute wheels exchange finite Coulomb traction with an ideal guided
running surface through a dissipative impulse solve. Normal support is the
declared equal wheel load, and dry bearing/rolling torque acts at the hinges.
Impact slip is allowed. Two finite-
mass spring end plates contact the train only unilaterally. No actuator,
prescribed train trajectory, attraction after separation, or video retiming.
"""
import os
os.environ['MUJOCO_GL']='disable'
import argparse,copy,hashlib,json,math,platform,socket,sys
from pathlib import Path
import mujoco
import numpy as np
HERE=Path(__file__).resolve().parent;DATA=HERE.parents[3]/'renders/thomas_dual_spring_train'
sys.path.insert(0,str(HERE.parents[2]))
from pcve_assets import asset

BASELINE={
    'train_mass_kg':.150,'train_rolling_friction_coefficient':.012,
    'left_young_modulus_pa':200e9,'right_young_modulus_pa':200e9,
    'spring_poisson_ratio':.30,'wire_diameter_m':.0011,'mean_coil_diameter_m':.024,
    'active_turns':12,'total_turns':14,'spring_rest_length_m':.120,
    'spring_density_kg_m3':7850,'spring_anchor_abs_x_m':.440,
    'spring_initial_compression_m':.045,'left_initial_q_m':.044964513156502954,'plate_half_thickness_m':.00075,
    'plate_mass_kg':.0094,'spring_damping_n_s_m':.025,
    'right_spring_present':[1],'obstacle_present':[0],
    'train_initial_x_m':-.440+.120-.045+.065+.00075,
    'train_initial_quaternion_wxyz':[1.,0.,0.,0.],
    'obstacle_initial_position_m':[.025,0.,.025],
    'obstacle_initial_quaternion_wxyz':[1.,0.,0.,0.],
    'obstacle_size_m':[.045,.056,.044],'obstacle_mass_kg':.085,
    'obstacle_friction':.32,'duration_s':8.,'fps':24,'simulation_dt_s':1/38400,
}
CASES={'source':None,'mass_x3':'SET train.mass TIMES 3',
       'rolling_x4':'SET train.rolling_resistance TIMES 4',
       'right_young_x025':'SET right_spring.young_modulus TIMES 0.25',
       'delete_right_spring':'DELETE right_spring',
       'add_wood_block':'ADD wood_block AT PRESET track_interceptor'}
# Cases outside the published catalog; the driver kept in the staged suite's inputs/edit_<case>/ solves them.
STAGED_CASES={'delete_train':'DELETE train'}

def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')

def params(case='source',dt=None):
    from edit_vocab import resolve
    c=copy.deepcopy(BASELINE);c.update(resolve({**CASES,**STAGED_CASES}[case]))
    if dt is not None:c['simulation_dt_s']=dt
    c['case_id']=case
    d,D,n=c['wire_diameter_m'],c['mean_coil_diameter_m'],c['active_turns']
    for side in ['left','right']:
        G=c[side+'_young_modulus_pa']/(2*(1+c['spring_poisson_ratio']))
        c[side+'_stiffness_n_m']=G*d**4/(8*D**3*n)
    axial=c['spring_rest_length_m']-2*d
    active_length=math.hypot(math.pi*D*n,axial)
    end_length=math.pi*D
    rhoA=c['spring_density_kg_m3']*math.pi*d*d/4
    c['coil_mass_kg']=rhoA*(active_length+2*end_length)
    c['coil_effective_mass_kg']=rhoA*(active_length/3+end_length)
    c['moving_plate_effective_mass_kg']=c['plate_mass_kg']+c['coil_effective_mass_kg']
    c['solid_height_m']=c['total_turns']*d
    c['spring_max_compression_m']=c['spring_rest_length_m']-c['solid_height_m']-.006
    c['rolling_force_n']=c['train_rolling_friction_coefficient']*c['train_mass_kg']*9.81
    return c

def make_xml(c):
    r=.0135671627;wm=.002;wheelI=wm*r*r/2
    geometry=asset('scenes/thomas_dual_spring_train/canonical/geometry.json')
    if geometry.exists():
        g=json.loads(geometry.read_text(encoding='utf-8'));centers=g['wheel_centers_m'];r=float(np.mean([p[2] for p in centers]));wheelI=wm*r*r/2
    else:centers=[[x,y,r] for x in [-.03867539,-.00391030,.03073210] for y in [-.01979524,.01979524]]
    c['wheel_radius_m']=r;c['wheel_centers_m']=centers;c['wheel_mass_kg']=wm
    c['rolling_effective_mass_kg']=c['train_mass_kg']+6*wheelI/r**2
    mj=f'''<mujoco model="thomas_dual_spring_train">
      <compiler angle="radian" inertiafromgeom="false"/>
      <option timestep="{c['simulation_dt_s']}" gravity="0 0 -9.81" integrator="implicitfast" solver="Newton" iterations="100" tolerance="1e-12" cone="elliptic">
        <flag energy="enable"/>
      </option>
      <default><geom solref="0.0012 1" solimp=".999 .999 .0001" condim="1" margin="0" friction="0 0 0" contype="4" conaffinity="4"/></default>
      <worldbody>
      <geom name="wooden_track_top" type="plane" pos="0 0 .003" size="1 1 .01" condim="3" friction=".32 .001 .0001" contype="2" conaffinity="2"/>
      <geom name="right_fixed_end" type="box" pos=".448 0 .025" size=".008 .042 .024"/>
      <geom name="left_fixed_end" type="box" pos="-.448 0 .025" size=".008 .042 .024"/>
      '''
    # DELETE train (train_present [0], absent from the published configurations): no train body or wheels.
    if c.get('train_present',[1])[0]:
        mj+=f'''<body name="train" pos="{c['train_initial_x_m']} 0 0">
       <joint name="train_x" type="slide" axis="1 0 0" damping=".001"/>
       <inertial pos="0 0 .036" mass="{c['train_mass_kg']-6*wm}" diaginertia=".000075 .00019 .00018"/>
       <geom name="body" type="box" pos="-.001 0 .040" size=".054 .023 .023"/>
       <geom name="front_coupler" type="box" pos=".061 0 .019" size=".004 .00424 .00424"/>
       <geom name="rear_coupler" type="box" pos="-.061 0 .019" size=".004 .00424 .00424"/>
    '''
        for i,(x,y,z) in enumerate(centers):
            mj+=f'''<body name="wheel_{i}" pos="{x} {y} {z}"><joint name="wheel_angle_{i}" type="hinge" axis="0 1 0" frictionloss="{c['train_rolling_friction_coefficient']*c['train_mass_kg']*9.81*r/6}"/>
        <inertial pos="0 0 0" mass="{wm}" diaginertia="{wheelI*.6} {wheelI} {wheelI*.6}"/>
        <geom name="wheel_tread_{i}" type="cylinder" size="{r} .0035" euler="1.57079632679 0 0" contype="0" conaffinity="0"/></body>'''
        mj+='</body>'
    for side,sgn in [('left',1),('right',-1)]:
        if side=='right' and not c['right_spring_present'][0]:continue
        rest=-sgn*(c['spring_anchor_abs_x_m']-c['spring_rest_length_m'])
        # Positive q shortens either spring; spring zero is the plate rest center.
        mj+=f'''<body name="{side}_plate" pos="{rest} 0 .024">
        <joint name="{side}_compression" type="slide" axis="{-sgn} 0 0" stiffness="{c[side+'_stiffness_n_m']}" damping="{c['spring_damping_n_s_m']}" limited="true" range="0 {c['spring_max_compression_m']}" solreflimit=".001 1" solimplimit=".999 .999 .0001"/>
        <inertial pos="0 0 0" mass="{c['moving_plate_effective_mass_kg']}" diaginertia=".00001 .000005 .000005"/>
        <geom name="{side}_pusher_contact" type="box" size="{c['plate_half_thickness_m']} .040 .015"/></body>'''
    if c['obstacle_present'][0]:
        x,y,z=c['obstacle_initial_position_m'];sx,sy,sz=np.asarray(c['obstacle_size_m'])/2
        mm=c['obstacle_mass_kg'];Ix=mm*((2*sy)**2+(2*sz)**2)/12;Iy=mm*((2*sx)**2+(2*sz)**2)/12;Iz=mm*((2*sx)**2+(2*sy)**2)/12
        mj+=f'''<body name="wood_block" pos="{x} {y} {z}"><freejoint name="block_free"/>
        <inertial pos="0 0 0" mass="{mm}" diaginertia="{Ix} {Iy} {Iz}"/>
        <geom name="block_contact" type="box" size="{sx} {sy} {sz}" condim="3" friction="{c['obstacle_friction']} .001 .0001" contype="6" conaffinity="6"/></body>'''
    mj+='</worldbody></mujoco>'
    return mj

def run(case='source',dt=None,tag='rebuild',write=True,output=None,duration_s=None):
    if mujoco.__version__!='3.3.7':raise RuntimeError('Pinned mujoco==3.3.7 is required')
    c=params(case,dt)
    if duration_s is not None:c['duration_s']=duration_s
    xml=make_xml(c);m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
    ix=lambda n:m.joint(n).qposadr[0]
    iv=lambda n:m.joint(n).dofadr[0]
    li=ix('left_compression');ri=ix('right_compression') if c['right_spring_present'][0] else None
    # DELETE train: the solve holds only the two springs, the left one released from its preload.
    train=bool(c.get('train_present',[1])[0])
    tx=ix('train_x') if train else None;tv=iv('train_x') if train else None
    # Freeze the common source contact preparation in the baseline. All five
    # interventions retain exactly the same existing-object initial qpos.
    # The 35.5 um contact compliance was resolved once in the source setup;
    # do not re-fit an existing object's pose for an edited mass or friction.
    d.qpos[li]=c['left_initial_q_m']
    d.qvel[:]=0;mujoco.mj_forward(m,d)
    energy_reference=d.energy[0]-.5*c['left_stiffness_n_m']*d.qpos[li]**2
    c['joint_qposadr']={m.joint(i).name:int(m.joint(i).qposadr[0]) for i in range(m.njnt)}
    c['joint_dofadr']={m.joint(i).name:int(m.joint(i).dofadr[0]) for i in range(m.njnt)}
    initial=d.qpos.copy();initial_qvel=d.qvel.copy()
    steps=round(c['duration_s']/c['simulation_dt_s']);sample_stride=round(1/c['fps']/c['simulation_dt_s'])
    dense_stride=max(1,round(1/1200/c['simulation_dt_s']))
    wheel_dofs=np.array([iv('wheel_angle_'+str(i)) for i in range(6)]) if train else None
    radius=c['wheel_radius_m'];wheel_inertia=c['wheel_mass_kg']*radius**2/2
    mass=c['train_mass_kg'];friction_impulse_bound=.45*mass*9.81*c['simulation_dt_s']/6
    traction_energy_change=0.;max_positive_traction_work=0.;max_wheel_asymmetry=0.
    frames=[];dense=[];contacts=[];penetration=0.
    for step in range(steps+1):
        if d.ncon:penetration=max(penetration,-float(np.min(d.contact.dist)))
        if step%sample_stride==0 or step%dense_stride==0:
            mujoco.mj_forward(m,d)
            row=np.r_[d.time,d.qpos,d.qvel,d.energy-np.array([energy_reference,0])]
            if step%sample_stride==0:frames.append(row.copy())
            if step%dense_stride==0:dense.append(row.copy())
            forces={'left':0.,'right':0.,'block':0.}
            for j in range(d.ncon):
                ct=d.contact[j];penetration=max(penetration,-float(ct.dist))
                names=[m.geom(int(g)).name for g in ct.geom]
                f=np.zeros(6);mujoco.mj_contactForce(m,d,j,f)
                for key,needle in [('left','left_pusher_contact'),('right','right_pusher_contact'),('block','block_contact')]:
                    if needle in names and 'wooden_track_top' not in names:forces[key]+=max(0.,f[0])
            if step%dense_stride==0:contacts.append([d.time,*forces.values()])
        if step<steps:
            mujoco.mj_step(m,d)
            if not train:continue
            # Solve the symmetric six-contact maximum-dissipation Coulomb QP.
            # v'=v+6J/M, omega_i'=omega_i-J*r/I, |J|<=mu*N*dt.
            # Its closed-form optimum minimizes post-step kinetic energy;
            # it permits slip at the traction bound, rather than prescribing
            # omega=v/r. Symmetry is a consequence of identical unloaded axles.
            vstar=float(d.qvel[tv]);w=d.qvel[wheel_dofs].copy();wmean=float(w.mean())
            slip=vstar-radius*wmean
            impulse=float(np.clip(-slip/(6/mass+radius**2/wheel_inertia),-friction_impulse_bound,friction_impulse_bound))
            before=.5*mass*vstar*vstar+.5*wheel_inertia*float(w@w)
            d.qvel[tv]=vstar+6*impulse/mass;d.qvel[wheel_dofs]=w-impulse*radius/wheel_inertia
            after=.5*mass*d.qvel[tv]**2+.5*wheel_inertia*float(d.qvel[wheel_dofs]@d.qvel[wheel_dofs])
            work=after-before;traction_energy_change+=work;max_positive_traction_work=max(max_positive_traction_work,work)
            max_wheel_asymmetry=max(max_wheel_asymmetry,float(np.max(np.abs(w-wmean))))
    frames=np.asarray(frames);dense=np.asarray(dense);contacts=np.asarray(contacts)
    q=dense[:,1:1+m.nq];v=dense[:,1+m.nq:1+m.nq+m.nv]
    if train:
        wheel_ids=[ix('wheel_angle_'+str(i)) for i in range(6)]
        roll_error=np.max(np.abs(q[:,wheel_ids]*c['wheel_radius_m']-q[:,tx,None]))
        wheel_vel=[iv('wheel_angle_'+str(i)) for i in range(6)]
        slip_vel=np.abs(v[:,wheel_vel]*c['wheel_radius_m']-v[:,tv,None])
    total=dense[:,-2:].sum(1);initial_energy=total[0]
    turns=np.flatnonzero((v[:-1,tv]*v[1:,tv]<0)&(np.abs(v[:-1,tv])+np.abs(v[1:,tv])>.001)) if train else []
    events={}
    for col,name in [(1,'left'),(2,'right'),(3,'block')]:
        active=contacts[:,col]>.02;starts=np.flatnonzero(active&~np.r_[False,active[:-1]])
        events[name]=[round(float(contacts[i,0]),5) for i in starts]
    report={'case_id':case,'solver':'MuJoCo','version':mujoco.__version__,'dt_s':c['simulation_dt_s'],
       'duration_s':c['duration_s'],'frame_contract':{'fps':24,'video_frames':len(frames)-1,'time_interval_s':f"[0,{c['duration_s']:g})", 'saved_endpoint':True},
       'max_speed_m_s':float(np.abs(v[:,tv]).max()) if train else None,'final_speed_m_s':float(v[-1,tv]) if train else None,
       'train_x_range_m':[float(c['train_initial_x_m']+q[:,tx].min()),float(c['train_initial_x_m']+q[:,tx].max())] if train else None,
       'initial_energy_j':float(initial_energy),'final_energy_j':float(total[-1]),
       'maximum_energy_increase_above_initial_j':float(max(0,total.max()-initial_energy)),
       'energy_gain_fraction':float(max(0,total.max()-initial_energy)/max(initial_energy,1e-12)),
       'largest_positive_energy_step_j':float(max(0,np.diff(total).max())),
       'max_contact_penetration_m':penetration,'penetration_sampling':'all native solver steps',
       'max_cumulative_wheel_slip_m':float(roll_error) if train else None,
       'max_tread_slip_speed_m_s':float(slip_vel.max()) if train else None,'wheel_contact_model':'six symmetric finite-inertia hinges; bounded maximum-dissipation Coulomb traction impulses; equal ideal rail normal support; dry rolling torque',
       'traction_energy_change_j':float(traction_energy_change),'max_positive_traction_step_work_j':float(max_positive_traction_work),
       'max_wheel_symmetry_error_rad_s':float(max_wheel_asymmetry),'wheel_friction_coefficient':.45,
       'max_compression_left_m':float(q[:,li].max()),'max_compression_right_m':float(q[:,ri].max()) if ri is not None else None,
       'min_coil_gap_m':float((c['spring_rest_length_m']-2*c['wire_diameter_m']-max(q[:,li].max(),q[:,ri].max() if ri is not None else 0))/c['active_turns']-c['wire_diameter_m']),
       'contact_onsets_s':events,'train_reversals_s':[float(dense[i+1,0]) for i in turns],
       'initial_qpos':initial.tolist(),'initial_qvel':initial_qvel.tolist(),'joint_names':[m.joint(i).name for i in range(m.njnt)],
       'initial_placement_unchanged':True,'active_actuators':m.nu,'prescribed_motion':False,
       'material_calibrated':False,'accepted_benchmark_gt':False,
       'coupler_contact_proxy':'inscribed rectangular patch of the actual flat circular magnet end; exact axial end plane; avoids unstable small cylinder-box GJK contacts in MuJoCo 3.3.7',
       'limitations':['Ideal longitudinal rail guidance; train cannot heave, yaw, pitch or derail','Added block is a free six-degree-of-freedom rigid body with gravity and native Coulomb ground contact','Equal wheel normal loads assumed; finite-inertia hinges, bounded Coulomb traction and rolling torque; transient slipping allowed','Guided axial spring mode only; no lateral buckling or wire self-collision','Hypothesized contact, bearing friction, mass and material parameters; no measured product calibration'],
       'execution_host':socket.gethostname(),'execution_os':platform.platform()}
    payload={'time':frames[:-1,0],'endpoint_time':frames[-1,0],'qpos':frames[:-1,1:1+m.nq],
       'qvel':frames[:-1,1+m.nq:1+m.nq+m.nv],'energy':frames[:-1,-2:],
       'dense_time':dense[:,0],'dense_qpos':q,'dense_qvel':v,'dense_energy':dense[:,-2:],'contacts':contacts,
       'joint_names':np.array(report['joint_names'])}
    if write:
        folder=(Path(output) if output else DATA/'simulation'/tag)/case;folder.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(folder/'states.npz',**payload);(folder/'model.xml').write_text(xml)
        save(folder/'config.json',c);save(folder/'physics_report.json',report)
    return report,payload,c

def main():
    p=argparse.ArgumentParser();p.add_argument('--case',default='all',choices=['all',*CASES]);p.add_argument('--tag',default='rebuild');a=p.parse_args()
    for case in CASES if a.case=='all' else [a.case]:
        r,_,_=run(case,tag=a.tag)
        print(json.dumps({k:r[k] for k in ['case_id','max_speed_m_s','final_speed_m_s','max_contact_penetration_m','energy_gain_fraction','contact_onsets_s','train_reversals_s']},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
