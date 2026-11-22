"""CPU rigid-contact alternative: native Bullet boxes with a passive guided spring.

No scripted trajectories, launch velocities, pose corrections or terminal snaps.
"""
from pathlib import Path
import sys,time,json,hashlib,platform,math,argparse
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scene_common import *
# The accepted states were solved with this Windows pybullet 3.2.5 build; on Linux the
# repository's .venv-rigid-elastic pybullet (same API 202010061) is imported instead.
sys.path.insert(0,str(RUNTIME/'pybullet'))
import pybullet as pb


def run(case,out,dt):
    c,overrides=parameters(case);derived=spring_properties(c);cid=pb.connect(pb.DIRECT)
    pb.setGravity(0,0,-9.81);pb.setTimeStep(dt)
    pb.setPhysicsEngineParameter(numSolverIterations=160,solverResidualThreshold=1e-12,
        deterministicOverlappingPairs=1,enableConeFriction=1,contactBreakingThreshold=.0002,
        restitutionVelocityThreshold=.05,contactERP=.2,frictionERP=.2)
    ids={};masses={};inertias={};root=__import__('xml.etree.ElementTree',fromlist=['Element']).Element('bullet_scene',version='3.2.5',format='PCVE Bullet authoring model; native snapshots supplied separately')
    import xml.etree.ElementTree as ET
    ET.SubElement(root,'physics',timestep=str(dt),gravity='0 0 -9.81',solver_iterations='160',spring_law='Hooke plus viscous and dry guide friction')
    world=ET.SubElement(root,'worldbody');actor_mu=math.sqrt(.35)
    def box(name,pos,size,mass,mu,offset=(0,0,0),quat=(0,0,0,1),margin=.0008):
        shape=pb.createCollisionShape(pb.GEOM_BOX,halfExtents=(np.asarray(size)/2).tolist(),collisionFramePosition=offset)
        body=pb.createMultiBody(baseMass=mass,baseCollisionShapeIndex=shape,basePosition=pos,baseOrientation=quat)
        ids[name]=body;masses[name]=mass
        pb.changeDynamics(body,-1,lateralFriction=mu,restitution=math.sqrt(.22),linearDamping=0,angularDamping=0,
            spinningFriction=0,rollingFriction=0,collisionMargin=margin,activationState=pb.ACTIVATION_STATE_DISABLE_SLEEPING)
        inertias[name]=np.asarray(pb.getDynamicsInfo(body,-1)[2])
        if mass:
            node=ET.SubElement(world,'body',name=name,pos=' '.join(map(str,pos)),mass=str(mass))
            ET.SubElement(node,'geom',name=name+'_geom',pos=' '.join(map(str,offset)),size=' '.join(map(str,size)),type='box',margin=str(margin))
        else:ET.SubElement(world,'geom',name=name,pos=' '.join(map(str,pos)),size=' '.join(map(str,size)),type='box',margin=str(margin))
        return body
    box('table',c['table_position_m'],c['table_size_m'],0,c['table_friction']/actor_mu)
    box('upper',c['upper_position_m'],c['upper_size_m'],0,c['upper_friction']/actor_mu)
    for i,pos in enumerate(c['platform_riser_centres_m']):box('riser'+str(i),pos,c['platform_riser_size_m'],0,.5)
    if c.get('block_present',[1])[0]:box('block',c['block_position_m'],c['block_size_m'],c['block_mass_kg'],actor_mu)
    if c['obstacle_present'][0]:box('obstacle',c['obstacle_position_m'],c['obstacle_size_m'],c['obstacle_mass_kg'],actor_mu)
    initial_tip=c['spring_anchor_x_m']+c['spring_rest_length_m']-c['spring_initial_compression_m'];rest_tip=c['spring_anchor_x_m']+c['spring_rest_length_m']
    latch=None
    if c['spring_present'][0]:
        pusher=box('pusher',[initial_tip,0,c['spring_axis_z_m']],c['pusher_size_m'],c['pusher_mass_kg']+derived['effective_coil_mass_kg'],.12/actor_mu,offset=[-.001,0,0])
        guide=pb.createConstraint(pusher,-1,-1,-1,pb.JOINT_PRISMATIC,[1,0,0],[0,0,0],[initial_tip,0,c['spring_axis_z_m']]);pb.changeConstraint(guide,maxForce=100,erp=.8)
        latch=pb.createConstraint(pusher,-1,-1,-1,pb.JOINT_FIXED,[1,0,0],[0,0,0],[initial_tip,0,c['spring_axis_z_m']]);pb.changeConstraint(latch,maxForce=100,erp=.8)
    names=[n for n in ['block','pusher','obstacle'] if n in ids]
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'model.xml').write_text(ET.tostring(root,encoding='unicode'),encoding='utf8')
    pb.saveBullet(str(out/'native_initial.bullet'))
    positions=[];quaternions=[];velocities=[];energies=[];events={};contacts=set();min_distance=0;max_total=-1e30;max_kinetic=0;had_upper=False;had_pusher=False;max_slider=-1e30;start=time.monotonic()
    stride=round(1/MOTION_FPS/dt);assert abs(stride*dt-1/MOTION_FPS)<1e-12
    def state():
        pos=[];quat=[];vel=[];potential=0.;kinetic=0.
        for name in names:
            p,q=pb.getBasePositionAndOrientation(ids[name]);linear,angular=pb.getBaseVelocity(ids[name]);rotation=np.asarray(pb.getMatrixFromQuaternion(q)).reshape(3,3);omega=rotation.T@angular
            pos.append(p);quat.append([q[3],*q[:3]]);vel.append([*angular,*linear]);potential+=masses[name]*9.81*p[2]
            kinetic+=.5*masses[name]*np.dot(linear,linear)+.5*np.dot(inertias[name]*omega,omega)
        if 'pusher' in names:potential+=.5*derived['stiffness_n_m']*(pos[names.index('pusher')][0]-rest_tip)**2
        return pos,quat,vel,[potential,kinetic]
    for step in range(round(4/dt)+1):
        t=step*dt
        if latch is not None and t>=RELEASE-dt/2:pb.removeConstraint(latch);latch=None
        current=state()
        p,q,v,e=current;max_total=max(max_total,sum(e));max_kinetic=max(max_kinetic,e[1])
        if step%stride==0:
            positions.append(p);quaternions.append(q);velocities.append(v);energies.append(e)
        on_upper=False;on_table=False
        for con in pb.getContactPoints():
            if con[1] not in ids.values() or con[2] not in ids.values():continue
            a=next(n for n,b in ids.items() if b==con[1]);b=next(n for n,b in ids.items() if b==con[2]);pair=tuple(sorted([a+'_geom' if a in names else a,b+'_geom' if b in names else b]))
            min_distance=min(min_distance,con[8]);contacts.add(pair)
            if 'block_geom' in pair and con[8]<=0 and con[9]>1e-7:
                if 'upper' in pair:on_upper=True;had_upper=True
                if 'table' in pair:
                    on_table=True;events.setdefault('first_table_contact_s',t);events.setdefault('first_table_contact_position_m',list(pb.getBasePositionAndOrientation(ids['block'])[0]))
                if 'pusher_geom' in pair:had_pusher=True
                if 'obstacle_geom' in pair:events.setdefault('first_obstacle_geom_contact_s',t)
        block=pb.getBasePositionAndOrientation(ids['block'])[0] if 'block' in ids else (math.nan,0,math.nan)
        if block[0]>.167 and block[2]<.139:events.setdefault('leave_upper_s',t)
        if t>=RELEASE and had_upper and block[0]>.13 and not on_upper and not on_table:events.setdefault('first_airborne_s',t)
        if 'pusher' in ids:
            tip=pb.getBasePositionAndOrientation(ids['pusher'])[0][0];vx=pb.getBaseVelocity(ids['pusher'])[0][0];travel=tip-initial_tip;max_slider=max(max_slider,travel)
            if t>=RELEASE and travel>=c['spring_initial_compression_m']:events.setdefault('first_natural_length_s',t)
            if t>=RELEASE and had_pusher and travel>.06 and block[0]-c['block_size_m'][0]/2-tip>1e-5:events.setdefault('natural_length_separation_s',t)
            force=-derived['stiffness_n_m']*(tip-rest_tip)-c['spring_damping_ns_m']*vx-c['guide_dry_friction_n']*math.tanh(vx/.001)
            if travel>c['guide_travel_limit_m']:force-=100000*(travel-c['guide_travel_limit_m'])+50*max(vx,0)
            if travel<-.001:force-=100000*(travel+.001)+50*min(vx,0)
            pb.applyExternalForce(ids['pusher'],-1,[force,0,0],[tip,0,c['spring_axis_z_m']],pb.WORLD_FRAME)
        if step<round(4/dt):pb.stepSimulation()
    dense_p,dense_q,dense_v=np.asarray(positions),np.asarray(quaternions),np.asarray(velocities);dense_e=np.asarray(energies);selection=np.arange(FRAMES)*(MOTION_FPS//FPS)
    pos,quat=dense_p[selection],dense_q[selection]
    qpos=np.concatenate([dense_p,dense_q],axis=2).reshape(len(dense_p),-1);qvel=dense_v.reshape(len(dense_p),-1)
    np.savez_compressed(out/'states.npz',time=np.arange(FRAMES)/FPS,positions=pos,quaternions=quat,body_names=np.array(names),cvel=dense_v[selection],energy=dense_e[selection],qpos=qpos[selection],qvel=qvel[selection],initial_qpos=qpos[0],initial_qvel=qvel[0])
    np.savez_compressed(out/'motion_states.npz',time=np.arange(len(dense_p))/MOTION_FPS,positions=dense_p,quaternions=dense_q,body_names=np.array(names),cvel=dense_v,energy=dense_e,qpos=qpos,qvel=qvel)
    save(out/'resolved_physics.json',dict(c,spring_derived=derived));save(out/'scenario_overrides.json',overrides)
    save(out/'ground_truth_transforms.json',{'scene_id':CASE_ID,'fps':FPS,'frame_count':FRAMES,'times_sec':(np.arange(FRAMES)/FPS).tolist(),'objects':{n:{'positions_m':pos[:,i].tolist(),'quaternions_wxyz':quat[:,i].tolist()} for i,n in enumerate(names)},'accepted_benchmark_gt':False,'scope':'Native Bullet rigid body states'})
    result={'case_id':case,'dt_s':dt,'solver':'pybullet==3.2.5','api_version':pb.getAPIVersion(),'events':events,'initial_all_velocities_zero':bool(np.all(qvel[0]==0)),
        'min_contact_distance_m':min_distance,'max_kinetic_energy_j':max_kinetic,'initial_total_energy_j':float(sum(dense_e[0])),'max_total_energy_j':max_total,
        'end_position_m':pos[-1,0].tolist(),'max_rotation_deg':float(np.degrees(2*np.arccos(np.clip(np.abs(dense_q[:,0,0]),0,1))).max()),'end_speed_m_s':float(np.linalg.norm(dense_v[-1,0,3:])),
        'motion_samples':len(dense_p),'motion_fps':MOTION_FPS,'maximum_guide_displacement_m':max_slider if c['spring_present'][0] else None,'guide_upper_stop_not_hit':bool(not c['spring_present'][0] or max_slider<c['guide_travel_limit_m']-.0001),
        'native_contact_pairs':[list(p) for p in sorted(contacts)],'elapsed_s':time.monotonic()-start,'execution_host':platform.node(),'material_calibrated':False,'accepted_benchmark_gt':False}
    pb.saveBullet(str(out/'native_final.bullet'));pb.disconnect(cid);save(out/'physics_audit.json',result);return pos,quat,result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cases',nargs='+',default=list(CASES));ap.add_argument('--dt',type=float,default=1/192000);ap.add_argument('--convergence',action='store_true');ap.add_argument('--out',type=Path,default=RENDERS/'resim');a=ap.parse_args();audits=[]
    for case in a.cases:
        path=a.out/'cases'/case;p,q,r=run(case,path,a.dt)
        if a.convergence:
            half=a.out/'numerics_half'/case;p2,q2,r2=run(case,half,a.dt/2)
            dense=np.load(path/'motion_states.npz');dense2=np.load(half/'motion_states.npz')
            r['convergence']={'half_dt_s':a.dt/2,'max_position_error_m':float(np.linalg.norm(p-p2,axis=2).max()),
              'max_rotation_error_deg':float(np.degrees(2*np.arccos(np.clip(np.abs((q*q2).sum(axis=2)),0,1))).max()),
              'end_position_error_m':float(np.linalg.norm(p[-1,0]-p2[-1,0])), 'half_dt_events':r2['events'],
              'dense_motion_position_error_m':float(np.linalg.norm(dense['positions']-dense2['positions'],axis=2).max()),
              'dense_motion_rotation_error_deg':float(np.degrees(2*np.arccos(np.clip(np.abs((dense['quaternions']*dense2['quaternions']).sum(axis=2)),0,1))).max())}
            save(path/'physics_audit.json',r)
        audits.append(r);print(json.dumps(r),flush=True)
    save(a.out/'physics_audits.json',audits)

if __name__=='__main__':main()
