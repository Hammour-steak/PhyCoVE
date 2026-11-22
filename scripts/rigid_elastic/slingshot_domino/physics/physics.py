"""SI units. Inertial hyperelastic bands + dynamically contacted rigid bodies.

The bands are slender tension-dominated discretizations, not volumetric MPM.
Neo-Hookean nominal axial stress, Kelvin viscosity and small strip bending.
Pouch is a low-mass compound concave cup; no ball/pouch constraint or launch kick.
All rigid contacts and 6-DOF rotations are solved by Bullet. Local CPU only.
"""
import argparse, hashlib, json, math, sys, time, os
from pathlib import Path
import numpy as np
from numba import njit
from config import DATA, EDITS, write_json
from vocabulary import resolve
from fork_geometry import mesh as fork_mesh,contact as finite_band_contact
from ribbon_physics import frame as material_frame,table_contact as band_table_contact,boxes_contact as band_boxes_contact
from fork_profile import MOUNT_BOXES,MOUNT_CYLINDERS,MOUNT_SPHERES
sys.path.insert(0,str(DATA/'runtime/python_deps'))
conda=DATA/'runtime/pybullet_conda'
if conda.exists():
    sys.path.insert(0,str(conda/'Lib/site-packages'))
    if os.name=='nt' and (conda/'Library/bin').exists():
        _dll=os.add_dll_directory(str((conda/'Library/bin').resolve()))
import pybullet as p

@njit(cache=False)
def band_fork_contact(x,v,centers,half,rotation,anchor,l0):
    penetration=0.
    for i in range(1,len(x)-1):
        # This 12 mm region is the embedded attachment under the fork saddle.
        if i*l0<.014:continue
        for j in range(len(centers)):
            local=rotation[j].T@(x[i]-centers[j]);gap=half[j]+.00012-np.abs(local)
            if gap.min()>0:
                k=np.argmin(gap);sign=1. if local[k]>=0 else -1.
                normal=rotation[j][:,k]*sign;depth=gap[k]
                x[i]+=normal*depth;vn=np.dot(v[i],normal)
                if vn<0:v[i]-=1.05*vn*normal
                v[i]-=.025*(v[i]-np.dot(v[i],normal)*normal)
                penetration=max(penetration,depth)
    return penetration

@njit(cache=False)
def band_forces(x,v,l0,muA,etaA,B,node_mass,air):
    n=len(x); f=np.zeros_like(x)
    for i in range(n):
        f[i,2]-=node_mass[i]*9.81
        f[i]-=air*node_mass[i]*v[i]
    energy=0.
    maxlam=0.
    diss=0.
    for i in range(n-1):
        d=x[i+1]-x[i];L=max(np.sqrt(np.dot(d,d)),1e-9); t=d/L
        lam=L/l0;maxlam=max(maxlam,lam)
        rate=np.dot(v[i+1]-v[i],t)/l0
        axial=0.
        if lam>1.:
            axial=muA*(lam-1./(lam*lam))
            energy+=muA*l0*.5*(lam*lam+2./lam-3.)
        # Viscous force vanishes in compression to avoid artificial tensile glue.
        visc=etaA*rate if lam>1. else 0.
        axial=max(0.,axial+visc)
        f[i]+=axial*t; f[i+1]-=axial*t
        diss+=max(0.,visc*rate*l0)
    # Quadratic centerline bending; very weak at this t^3 / 12 strip thickness.
    for i in range(1,n-1):
        d=x[i-1]-2*x[i]+x[i+1]; g=B/(l0**3)*d
        f[i-1]-=g; f[i]+=2*g;f[i+1]-=g
        energy+=.5*B/(l0**3)*np.dot(d,d)
    return f,energy,maxlam,diss

def qrot(q,v):
    return np.asarray(p.getMatrixFromQuaternion(q)).reshape(3,3)@v

def simulate(case,out,segments=20,steps_per_frame=1200,quiet=False,stop_time=None):
    started=time.time();c,override=resolve(case);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    write_json(out/'scenario_overrides.json',override);write_json(out/'scene_params.json',c)
    cid=p.connect(p.DIRECT);dt=1/(c['fps']*steps_per_frame)
    p.setPhysicsEngineParameter(fixedTimeStep=dt,numSolverIterations=60,
      contactBreakingThreshold=.00015,allowedCcdPenetration=0.,deterministicOverlappingPairs=1,
      contactERP=.04,frictionERP=.05,enableConeFriction=1)
    p.setGravity(*c['gravity_m_s2']);p.setRealTimeSimulation(0)
    table=p.createMultiBody(baseMass=0,baseCollisionShapeIndex=p.createCollisionShape(p.GEOM_BOX,
      halfExtents=[.55,.342302501955486,.015]),basePosition=[.10,.262302501955486,-.015])
    p.changeDynamics(table,-1,lateralFriction=c['table_friction'],restitution=.35)
    floor=p.createMultiBody(0,p.createCollisionShape(p.GEOM_BOX,halfExtents=[5.,5.,.02]),basePosition=[0.,0.,-.79528585609])
    p.changeDynamics(floor,-1,lateralFriction=.5,restitution=.15)
    ball=None  # DELETE ball (ball_present [0]): no ball body
    if c.get('ball_present',[1])[0]:
     ball=p.createMultiBody(c['ball_mass_kg'],p.createCollisionShape(p.GEOM_SPHERE,radius=c['ball_radius_m']),
       basePosition=c['ball_position_m'],baseOrientation=c['ball_quaternion_xyzw'])
     p.changeDynamics(ball,-1,lateralFriction=c['ball_friction'],restitution=.55,rollingFriction=.0006,
       spinningFriction=.0001,linearDamping=.015,angularDamping=.015,ccdSweptSphereRadius=.006,
       contactProcessingThreshold=0.)
    # Concave cup via 9 convex plates, plus bottom lip. Attachment y +/-13 mm.
    shapes=[];half=[];pos=[];ori=[]
    shapes.append(p.GEOM_BOX);half.append([.00055,.006,.0065]);pos.append([0.,0.,0.]);ori.append([0,0,0,1])
    for sign in (-1,1):
        shapes.append(p.GEOM_BOX);half.append([.00055,math.hypot(.006,.007)/2,.0065]);pos.append([.003,sign*.0095,0.])
        ori.append(p.getQuaternionFromEuler([0.,0.,-sign*math.atan(.006/.007)]))
    shapes.append(p.GEOM_BOX);half.append([.004,.012,.00055]);pos.append([.004,0.,-.0082]);ori.append([0.,0.,0.,1.])
    col=p.createCollisionShapeArray(shapeTypes=shapes,halfExtents=half,collisionFramePositions=pos,collisionFrameOrientations=ori)
    pouch=p.createMultiBody(c['pouch_mass_kg'],col,basePosition=c['pouch_position_m'],baseOrientation=c['pouch_quaternion_xyzw'])
    p.changeDynamics(pouch,-1,lateralFriction=.15,restitution=.02,linearDamping=.4,angularDamping=.5,
      localInertiaDiagonal=[1.7e-8,1.1e-8,2.4e-8],contactStiffness=800.,contactDamping=.8)
    # Static wooden fork colliders: stem and two sloping branches. Their bounds
    # follow the rendered wood, and prevent a returned pouch passing through it.
    fork_shapes=[p.GEOM_BOX];fork_half=[[.0095,.012,.028]];fork_pos=[[0.,0.,.046]];fork_ori=[[0.,0.,0.,1.]]
    for sign in (-1,1):
        a=np.array([0.,sign*.014,.077]);b=np.array([0.,sign*.043,.131]);direction=(b-a)/np.linalg.norm(b-a)
        axis=np.cross([0.,0.,1.],direction);w=math.sqrt((1+direction[2])/2)
        q=[*(axis/(2*w)),w]
        fork_shapes.append(p.GEOM_BOX);fork_half.append([.0095,.010,.5*np.linalg.norm(b-a)]);fork_pos.append(((a+b)/2).tolist());fork_ori.append(q)
    fork_vertices,fork_faces=fork_mesh()
    forkcol=p.createCollisionShape(p.GEOM_MESH,vertices=fork_vertices.tolist(),indices=fork_faces.flatten().tolist(),flags=p.GEOM_FORCE_CONCAVE_TRIMESH)
    fork=p.createMultiBody(0,forkcol);p.changeDynamics(fork,-1,lateralFriction=.5,restitution=.05)
    mount_names={}
    for spec in MOUNT_BOXES:
        shape=p.createCollisionShape(p.GEOM_BOX,halfExtents=np.asarray(spec['size'])/2)
        body=p.createMultiBody(0,shape,basePosition=spec['center']);mount_names[body]=spec['id']
        p.changeDynamics(body,-1,lateralFriction=.5 if spec['material']=='wood'else .4,restitution=.05,collisionMargin=0.)
    for spec in MOUNT_CYLINDERS:
        shape=p.createCollisionShape(p.GEOM_CYLINDER,radius=spec['radius'],height=spec['depth'])
        orientation=[0,0,0,1]if spec['axis']==[0,0,1]else p.getQuaternionFromEuler([0,math.pi/2,0])
        body=p.createMultiBody(0,shape,basePosition=spec['center'],baseOrientation=orientation);mount_names[body]=spec['id']
        p.changeDynamics(body,-1,lateralFriction=.4,restitution=.05,collisionMargin=0.)
    for spec in MOUNT_SPHERES:
        shape=p.createCollisionShape(p.GEOM_SPHERE,radius=spec['radius'])
        body=p.createMultiBody(0,shape,basePosition=spec['center']);mount_names[body]=spec['id']
        p.changeDynamics(body,-1,lateralFriction=.4,restitution=.05)
    mount_centers=np.asarray([s['center']for s in MOUNT_BOXES]);mount_half=np.asarray([s['size']for s in MOUNT_BOXES])/2
    fork_centers=np.asarray(fork_pos);fork_half_arr=np.asarray(fork_half)
    fork_rot=np.asarray([np.asarray(p.getMatrixFromQuaternion(q)).reshape(3,3) for q in fork_ori])
    bodies={'ball':ball,'pouch':pouch} if ball is not None else {'pouch':pouch}
    for key in ('domino','second_domino'):
        if c[key+'_present'][0]:
            b=p.createMultiBody(c[key+'_mass_kg'],p.createCollisionShape(p.GEOM_BOX,halfExtents=np.array(c[key+'_size_m'])/2),
               basePosition=c[key+'_position_m'],baseOrientation=c[key+'_quaternion_xyzw'])
            p.changeDynamics(b,-1,lateralFriction=c['domino_friction'],restitution=.18,
              linearDamping=.01,angularDamping=.015,collisionMargin=0.,contactProcessingThreshold=0.)
            bodies[key]=b
    anchors=np.asarray(c['band_anchor_positions_m']);attach=np.array([[.006,-.013,0.],[.006,.013,0.]])
    x=np.zeros((2,segments+1,3));v=x.copy()
    for j in range(2):x[j]=np.linspace(anchors[j],np.array(c['pouch_position_m'])+attach[j],segments+1)
    l0=c['band_rest_length_m']/segments;area=c['band_width_m']*c['band_thickness_m']
    masses=np.full(segments+1,c['rubber_density_kg_m3']*area*l0);masses[[0,-1]]*=.5
    muA=c['young_modulus_pa']/3*area;etaA=c['rubber_viscosity_pa_s']*area
    B=c['young_modulus_pa']*c['band_width_m']*c['band_thickness_m']**3/12
    keys=list(bodies);frames=[];bands=[];vels=[];energy=[];dense=[];events=[]
    detail_states=[];detail_bands=[];detail_velocities=[];detail_times=[]
    slow_states=[];slow_bands=[];slow_velocities=[];slow_times=[]
    main_directors=[];detail_directors=[];slow_directors=[]
    main_roll=[];detail_roll=[];slow_roll=[]
    old_t=np.zeros((2,3));old_w=np.zeros((2,3));old_roll=np.zeros(2);frame_valid=np.zeros(2,dtype=np.bool_)
    contact_impulses={};peak_tilt={};first_hit=None
    release_step=round(c['release_s']/dt);total_steps=round(stop_time/dt)if stop_time else c['frames']*steps_per_frame
    first_contacts={};min_gap=0.;max_band_lambda=0.;contact_pouch_seen=False;separation=None;total_diss=0.;was_touching=False;sep_pending=False
    max_ball_speed=0.;initial_state={};mechanical=[];max_band_projection=0.;max_mount_projection=0.
    dynamics={name:p.getDynamicsInfo(b,-1) for name,b in bodies.items()}
    mass_schedule={}
    for edit in c.get('timed_edits',[]):
        if set(edit['params'])!={'domino_mass_kg'} or 'domino' not in bodies:
            raise ValueError('Only timed domino mass changes are supported')
        frame=int(edit['frame']);mass=float(edit['params']['domino_mass_kg'])
        if not 1<=frame<=c['frames'] or mass<=0:
            raise ValueError('Invalid timed domino mass edit')
        mass_schedule[(frame-1)*steps_per_frame]=(frame,mass)
    for name,b in bodies.items():
        pp,qq=p.getBasePositionAndOrientation(b);initial_state[name]={'position_m':pp,'quaternion_xyzw':qq}
    initial_band=x.copy();initial_elastic=None;release_energy=None;ball_sep_velocity=None
    detail_start=round(.45/dt);detail_stride=round((1/120)/dt)
    slow_start=round(.4/dt);slow_stride=round((1/72)/dt)
    for step in range(total_steps+1):
        t=step*dt
        if step in mass_schedule:
            frame,mass=mass_schedule[step]
            before=p.getDynamicsInfo(bodies['domino'],-1)
            inertia=np.asarray(before[2])*mass/before[0]
            p.changeDynamics(bodies['domino'],-1,mass=mass,localInertiaDiagonal=inertia.tolist())
            dynamics['domino']=p.getDynamicsInfo(bodies['domino'],-1)
            events.append({'event':'timed_mass_change','body':'domino','frame':frame,'time_s':t,
                'from_mass_kg':before[0],'to_mass_kg':dynamics['domino'][0],
                'local_inertia_before_kg_m2':list(before[2]),'local_inertia_after_kg_m2':list(dynamics['domino'][2])})
        detail_sample=step>=detail_start and(step-detail_start)%detail_stride==0 and step<detail_start+96*detail_stride
        slow_sample=step>=slow_start and(step-slow_start)%slow_stride==0 and step<slow_start+96*slow_stride
        if step<release_step and step%(steps_per_frame//6)!=0 and not detail_sample and not slow_sample:continue
        pp,qq=p.getBasePositionAndOrientation(pouch);pv,pw=p.getBaseVelocity(pouch)
        pp=np.array(pp);pv=np.array(pv);pw=np.array(pw)
        active=step>=release_step
        desired=qrot(qq,np.array([0.,0.,1.]))
        elastic=0.;diss=0.
        for j in range(2):
            r=qrot(qq,attach[j]);x[j,-1]=pp+r;v[j,-1]=pv+np.cross(pw,r)
            director,tangent,roll,root_axis=material_frame(x[j],desired,old_t[j],old_w[j],old_roll[j],frame_valid[j])
            old_t[j]=tangent[0];old_w[j]=root_axis;old_roll[j]=roll;frame_valid[j]=True
            f,U,lam,D=band_forces(x[j],v[j],l0,muA,etaA,B,masses,4.)
            elastic+=U;max_band_lambda=max(max_band_lambda,lam);diss+=D
            if active:
                p.applyExternalForce(pouch,-1,f[-1].tolist(),x[j,-1].tolist(),p.WORLD_FRAME)
                v[j,1:-1]+=dt*f[1:-1]/masses[1:-1,None]
                x[j,1:-1]+=dt*v[j,1:-1]
                max_band_projection=max(max_band_projection,finite_band_contact(x[j],v[j],director,l0,c['band_width_m'],c['band_thickness_m']))
                max_mount_projection=max(max_mount_projection,band_boxes_contact(x[j],v[j],director,l0,c['band_width_m'],c['band_thickness_m'],mount_centers,mount_half))
                # Surface contact of free band nodes with table, no visual-only offsets.
                band_table_contact(x[j],v[j],director,tangent,c['band_width_m'],c['band_thickness_m'],l0)
        if initial_elastic is None:initial_elastic=elastic
        if step==release_step:release_energy=elastic;events.append({'event':'latch_removed','time_s':t})
        if not active:
            # Real initial latch plus pre-release support: exact shared rest state.
            for name in [n for n in ('ball','pouch') if n in bodies]:
                p.resetBasePositionAndOrientation(bodies[name],c[name+'_position_m'],c[name+'_quaternion_xyzw'])
                p.resetBaseVelocity(bodies[name],[0,0,0],[0,0,0])
        sample=None
        if (step%steps_per_frame==0 and step<total_steps)or detail_sample or slow_sample:
            sample=[material_frame(x[j],desired,old_t[j],old_w[j],old_roll[j],frame_valid[j])for j in range(2)]
        if step%steps_per_frame==0 and step<total_steps:
            frames.append([(*p.getBasePositionAndOrientation(b)[0],*p.getBasePositionAndOrientation(b)[1])for b in bodies.values()])
            vels.append([(*p.getBaseVelocity(b)[0],*p.getBaseVelocity(b)[1])for b in bodies.values()]);bands.append(x.copy());energy.append(elastic)
            main_directors.append(np.array([f[0]for f in sample]));main_roll.append(np.array([f[2]for f in sample]))
        # Additional review samples come directly from physical integration steps.
        # 0.45--1.25 s at 120 Hz, displayed separately as a labelled 5x slow replay.
        if step>=detail_start and (step-detail_start)%detail_stride==0 and len(detail_times)<96:
            detail_times.append(t);detail_bands.append(x.copy())
            detail_states.append([(*p.getBasePositionAndOrientation(b)[0],*p.getBasePositionAndOrientation(b)[1])for b in bodies.values()])
            detail_velocities.append([(*p.getBaseVelocity(b)[0],*p.getBaseVelocity(b)[1])for b in bodies.values()])
            detail_directors.append(np.array([f[0]for f in sample]));detail_roll.append(np.array([f[2]for f in sample]))
        if slow_sample:
            slow_times.append(t);slow_bands.append(x.copy())
            slow_states.append([(*p.getBasePositionAndOrientation(b)[0],*p.getBasePositionAndOrientation(b)[1])for b in bodies.values()])
            slow_velocities.append([(*p.getBaseVelocity(b)[0],*p.getBaseVelocity(b)[1])for b in bodies.values()])
            slow_directors.append(np.array([f[0]for f in sample]));slow_roll.append(np.array([f[2]for f in sample]))
        if step%(steps_per_frame//6)==0:
            if ball is not None:
                bp=p.getBasePositionAndOrientation(ball)[0];bv=p.getBaseVelocity(ball)[0]
                dense.append([t,*bp,*bv,elastic]);max_ball_speed=max(max_ball_speed,np.linalg.norm(bv))
            total_energy=elastic
            for name,b in bodies.items():
                mass=dynamics[name][0];inertia=np.array(dynamics[name][2]);pos,quat=p.getBasePositionAndOrientation(b);lin,ang=p.getBaseVelocity(b)
                R=np.asarray(p.getMatrixFromQuaternion(quat)).reshape(3,3);omega=R.T@np.asarray(ang)
                total_energy+=.5*mass*np.dot(lin,lin)+.5*np.dot(inertia*omega,omega)+mass*9.81*pos[2]
            total_energy+=sum(.5*np.sum(masses[:,None]*v[j]**2)+np.sum(masses*9.81*x[j,:,2]) for j in range(2))
            mechanical.append([t,total_energy])
            for name in ('domino','second_domino'):
                if name in bodies:
                    q=p.getBasePositionAndOrientation(bodies[name])[1]
                    angle=math.degrees(math.acos(np.clip(1-2*(q[0]*q[0]+q[1]*q[1]),-1,1)))
                    if angle>peak_tilt.get(name,{}).get('angle_deg',-1):peak_tilt[name]={'angle_deg':angle,'time_s':t}
        if not active:continue
        p.stepSimulation();total_diss+=diss*dt
        contacts=p.getContactPoints()
        touching=False
        for ct in contacts:
            pair=tuple(sorted((ct[1],ct[2])));gap=ct[8];min_gap=min(min_gap,gap)
            if ct[9]>1e-7 and ball in pair:
                names={table:'table',floor:'floor',fork:'wooden_fork',**mount_names,**{i:n for n,i in bodies.items()}}
                other=names.get(pair[0]if pair[1]==ball else pair[1],'unknown')
                contact_impulses[other]=contact_impulses.get(other,0.)+ct[9]*dt
                if other=='domino' and first_hit is None:
                    first_hit={'time_s':t+dt,'ball_position_m':list(p.getBasePositionAndOrientation(ball)[0]),
                       'ball_velocity_after_first_step_m_s':list(p.getBaseVelocity(ball)[0]),'contact_height_m':ct[5][2]}
            if pair not in first_contacts and ct[9]>1e-7:
                first_contacts[pair]=t+dt
                names={table:'table',floor:'floor',fork:'wooden_fork',**mount_names,**{i:n for n,i in bodies.items()}}
                events.append({'event':'contact','bodies':[names.get(pair[0],str(pair[0])),names.get(pair[1],str(pair[1]))],
                  'time_s':t+dt,'point_m':list(ct[5]),'normal_force_n':ct[9]})
            if set(pair)=={ball,pouch} and ct[9]>1e-7:touching=True;contact_pouch_seen=True
        if touching:sep_pending=True
        if contact_pouch_seen and not touching and sep_pending:
            # Require a positive geometric separation, rather than one zero-force step.
            close=p.getClosestPoints(ball,pouch,.001)
            if not close or min(q[8] for q in close)>.00005:
                separation=t+dt;ball_sep_velocity=list(p.getBaseVelocity(ball)[0])
                events.append({'event':'ball_pouch_separation','time_s':separation,'ball_velocity_m_s':ball_sep_velocity})
                sep_pending=False
        was_touching=touching
    final_state={}
    for name,b in bodies.items():
        pp,qq=p.getBasePositionAndOrientation(b);vv,ww=p.getBaseVelocity(b)
        up=qrot(qq,[0,0,1]);tilt=math.degrees(math.acos(np.clip(up[2],-1,1)))
        final_state[name]={'position_m':pp,'quaternion_xyzw':qq,'speed_m_s':float(np.linalg.norm(vv)),
                          'angular_speed_rad_s':float(np.linalg.norm(ww)),'tilt_deg':tilt}
    np.savez_compressed(out/'trajectory.npz',states=np.asarray(frames),velocities=np.asarray(vels),
       bands=np.asarray(bands),body_names=np.asarray(keys),time_s=np.arange(len(frames))/c['fps'],
       elastic_energy_j=np.asarray(energy),dense_ball=np.asarray(dense),initial_band=initial_band,mechanical_energy=np.asarray(mechanical),
       detail_states=np.asarray(detail_states),detail_bands=np.asarray(detail_bands),detail_velocities=np.asarray(detail_velocities),detail_time_s=np.asarray(detail_times),
       slow_states=np.asarray(slow_states),slow_bands=np.asarray(slow_bands),slow_velocities=np.asarray(slow_velocities),slow_time_s=np.asarray(slow_times),
       directors=np.asarray(main_directors),detail_directors=np.asarray(detail_directors),slow_directors=np.asarray(slow_directors),
       roll_angle_rad=np.asarray(main_roll),detail_roll_angle_rad=np.asarray(detail_roll),slow_roll_angle_rad=np.asarray(slow_roll))
    report=dict(case_id=case,solver='PyBullet rigid 6-DOF + extensible neo-Hookean bands with finite-width contact against the exact Y profile',
       fork_collision_geometry='Same extruded concave Y profile as visible wood; static Bullet triangle mesh',
       band_collision_geometry='Five transverse samples with physical strip width and half-thickness clearance; continuous material directors updated at integration steps',
       leather_contact_stiffness_n_m=800.,leather_contact_damping_n_s_m=.8,
       maximum_band_fork_contact_projection_m=max_band_projection,
       maximum_band_mount_contact_projection_m=max_mount_projection,
       mount_collision_geometry=dict(boxes=MOUNT_BOXES,cylinders=MOUNT_CYLINDERS,spheres=MOUNT_SPHERES,scope='Shared nominal render geometry; decorative threads and manufacturing bevels are excluded'),
       solver_version=p.getAPIVersion(),execution='local CPU, no Blender',dt_s=dt,segments_per_band=segments,
       timed_edits=c.get('timed_edits',[]),timed_edits_applied_in_running_solver=bool(mass_schedule),
       duration_simulated_s=total_steps*dt,render_times_s=[0.,95/24],
       initial_state=initial_state,final_state=final_state,initial_elastic_energy_j=initial_elastic,
       release_elastic_energy_j=release_energy,integrated_band_viscous_dissipation_j=total_diss,
       initial_total_mechanical_energy_j=mechanical[0][1],max_total_mechanical_energy_j=max(e[1]for e in mechanical),
       max_stretch_ratio=max_band_lambda,minimum_contact_gap_m=min_gap,max_ball_speed_m_s=float(max_ball_speed),
       integrated_ball_normal_impulses_n_s=contact_impulses,peak_domino_tilt=peak_tilt,first_domino_hit=first_hit,
       ball_pouch_contact_occurred=contact_pouch_seen,ball_pouch_separation_s=separation,
       ball_separation_velocity_m_s=ball_sep_velocity,events=events,
       geometry_and_materials_calibrated_to_measurements=False,
       limitations=['Tension-dominated band model, weak centerline bending; cross-section torsion not resolved.',
       'Leather pouch treated as a light rigid compound cup; no leather shell strain.',
       'Parameters plausible SI values, not calibrated to a specific real specimen.'],
       elapsed_s=time.time()-started)
    report['trajectory_sha256']=hashlib.sha256((out/'trajectory.npz').read_bytes()).hexdigest()
    write_json(out/'physics_report.json',report);p.disconnect(cid)
    if not quiet:print(json.dumps({k:report[k]for k in ('case_id','elapsed_s','max_ball_speed_m_s','ball_pouch_separation_s','minimum_contact_gap_m','final_state')},ensure_ascii=True))
    return report

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--case',default='source',choices=['source',*EDITS]);a.add_argument('--all',action='store_true')
    a.add_argument('--segments',type=int,default=20);a.add_argument('--steps-per-frame',type=int,default=1200)
    a.add_argument('--out',type=Path);a.add_argument('--stop-time',type=float);args=a.parse_args()
    for case in ['source',*EDITS] if args.all else [args.case]:
        target=(args.out/case if args.all else args.out) if args.out else DATA/'simulation'/case
        simulate(case,target,args.segments,args.steps_per_frame,stop_time=args.stop_time)
