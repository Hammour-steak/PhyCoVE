"""Native coupled shell/ABD IPC, with torque-driven compliant revolute hinge.

Recorded states are untouched native solutions. No pinned cloth vertices,
prescribed door trajectory, post-solve filtering or motion time remapping.
"""

from pathlib import Path
import argparse, os, socket, time,shutil
import numpy as np
from scipy.spatial import cKDTree
import trimesh
import uipc
from uipc import builtin,view
from uipc.core import Engine,World,Scene,FiniteElementStateAccessorFeature,AffineBodyStateAccessorFeature
from uipc.geometry import trimesh as ipc_mesh,label_surface,ground
from uipc.constitution import (StrainLimitingBaraffWitkinShell,ElasticModuli2D,DiscreteShellBending,
    AffineBodyConstitution,AffineBodyRevoluteJoint,AffineBodyRevoluteJointExternalForce,FiniteElementExternalForce)
from common import HERE,CASE,save,sha,DURATION
from geometry import towel,door_transform,doorstop_mesh,cabinet_collider,LAYOUT
from edit_vocab import resolve,CASES,CANDIDATES

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',choices=list(CASES|CANDIDATES),default='source');ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--dt',type=float,default=1/240);ap.add_argument('--pitch',type=float,default=.008);ap.add_argument('--duration',type=float,default=DURATION)
    ap.add_argument('--initial-state',type=Path);ap.add_argument('--settle-only',action='store_true')
    ap.add_argument('--source-cache',type=Path,help='Timed friction edit: restore the exact source state at the edit frame and continue solving')
    ap.add_argument('--geometry-preflight-only',action='store_true',help='CPU-only unsimulated placement/contact inspection; exits before constructing a CUDA engine')
    a=ap.parse_args();assert os.name=='posix'
    out=a.out;out.mkdir(parents=True,exist_ok=False);p,edit=resolve(a.case)
    start_time=0.;source_cache=None;edit_frame=None
    schedule=p.pop('timed_edits',[])
    if schedule:
        import json
        assert len(schedule)==1 and set(schedule[0]['params'])=={'towel_friction'},'Only one timed towel-friction change is supported'
        assert a.source_cache and not a.initial_state and not a.settle_only,'A timed edit requires the accepted source cache'
        edit_frame=int(schedule[0]['frame']);start_time=(edit_frame-1)/24
        source_cache=dict(np.load(a.source_cache))
        source_cfg=json.loads((a.source_cache.parent/'simulation_config.json').read_text())
        assert source_cfg['case_id']=='source' and source_cfg['dt']==a.dt and source_cfg['pitch']==a.pitch
        assert len(source_cache['positions'])==96 and abs(source_cache['times'][edit_frame-1]-start_time)<1e-12
        seed_dir=out/'resume_seed';seed_dir.mkdir()
        frame_fields={'positions','velocities','rigid_transforms','rigid_velocities','times'}
        seed_data={k:v[edit_frame-1:edit_frame] if k in frame_fields else v for k,v in source_cache.items()}
        np.savez_compressed(seed_dir/'cache.npz',**seed_data)
        save(seed_dir/'simulation_config.json',source_cfg)
        a.initial_state=seed_dir/'cache.npz';a.duration=(96-edit_frame+1)/24
        p.update(schedule[0]['params'])
    # DELETE towel (towel_present = [0]): no cloth body in the solve; the towel arrays of the cache keep the
    # seed's resting shape, unused (every published case has the towel).
    towel_present=bool(p.get('towel_present',[1])[0])
    placed,rest,faces,uv=towel(a.pitch);rest[:,1]-=.8;rest[:,2]+=.9
    initial_v=np.zeros_like(placed);seed=None;seed_rigids={};seed_rigid_velocities={}
    if a.initial_state:
        import json
        seed_cfg=json.loads((a.initial_state.parent/'simulation_config.json').read_text())
        assert seed_cfg['layout']==LAYOUT,'The native seed and current common geometry differ'
        seed=np.load(a.initial_state);assert np.array_equal(seed['faces'],faces) and np.array_equal(seed['uv'],uv)
        placed=seed['positions'][-1].copy();initial_v=seed['velocities'][-1].copy()
        seed_rigids={name:seed['rigid_transforms'][-1,i].copy()for i,name in enumerate(seed['rigid_names'].tolist())}
        if 'rigid_velocities'in seed.files:
            seed_rigid_velocities={name:seed['rigid_velocities'][-1,i].copy()for i,name in enumerate(seed['rigid_names'].tolist())}
        assert 'rigid_velocities'in seed.files,'The moving-door seed must carry native rigid velocities'
    cfg=Scene.default_config();cfg['dt']=a.dt;cfg['gravity']=[[0.],[0.],[-9.81]]
    cfg['contact']['enable']=1;cfg['contact']['friction']['enable']=1
    cfg['contact']['d_hat_relative']=0.;cfg['contact']['eps_velocity_relative']=0.
    cfg['contact']['d_hat']=.0004;cfg['contact']['eps_velocity']=.0001
    cfg['contact']['adaptive']['min_kappa']=1e7;cfg['contact']['adaptive']['max_kappa']=1e12
    cfg['newton']['semi_implicit']['enable']=0;cfg['newton']['velocity_tol']=1e-4;cfg['newton']['max_iter']=1500
    cfg['newton']['velocity_tol_relative']=0.
    cfg['line_search']['max_iter']=48;cfg['linear_system']['fem_preconditioner']='mas';cfg['linear_system']['tol_rate']=1e-8
    scene=Scene(cfg);scene.contact_tabular().default_model(.65,1e9)
    default=scene.contact_tabular().default_element();cc=scene.contact_tabular().create('cotton')
    scene.contact_tabular().insert(cc,default,p['towel_friction'],1e9);scene.contact_tabular().insert(cc,cc,p['towel_friction'],1e9)
    names=[];slots={};geometries={}
    def rigid(name,dimensions,center,mass=None,T=None,mesh_override=None):
        mesh=mesh_override if mesh_override is not None else doorstop_mesh(p)if name=='doorstop'else trimesh.creation.box(dimensions)
        if name not in ['doorstop','cabinet']:mesh.apply_translation(center)
        if name=='door':
            dy=LAYOUT['door_center_y']+.010
            parts=[mesh]
            for z in [.645,.735]:
                rod=trimesh.creation.cylinder(radius=.005,height=.026,sections=12)
                rod.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,[1.,0.,0.]));rod.apply_translation([.415,-.030+dy,z]);parts.append(rod)
                washer=trimesh.creation.cylinder(radius=.008,height=.0015,sections=24)
                washer.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,[1.,0.,0.]));washer.apply_translation([.415,-.0198+dy,z]);parts.append(washer)
            rod=trimesh.creation.cylinder(radius=.005,height=.112,sections=12);rod.apply_translation([.415,-.046+dy,.69]);parts.append(rod)
            # Intersecting components are one rigid body; union removes interior
            # triangle contacts and matches the visible handle/support surfaces.
            mesh=trimesh.boolean.union(parts,engine='manifold')
        geo=ipc_mesh(np.asarray(mesh.vertices),np.asarray(mesh.faces,np.int32));label_surface(geo)
        AffineBodyConstitution().apply_to(geo,1e9,(mass/mesh.volume)if mass else 700.)
        default.apply_to(geo);view(geo.instances().find(builtin.is_fixed))[:]=0 if mass else 1
        T=np.eye(4)if T is None else T
        if name in seed_rigids:T=seed_rigids[name].copy()
        view(geo.transforms())[:]=T
        slot,_=scene.objects().create(name).geometries().create(geo);slots[name]=slot;names.append(name)
        geometries[name]=(np.asarray(mesh.vertices),np.asarray(mesh.faces,np.int32),T)
    rigid('cabinet',[1,1,1],[0,0,0],mesh_override=cabinet_collider())
    if p['door_present'][0]:rigid('door',[.47,.018,.65],[.235,LAYOUT['door_center_y'],.445],p['door_mass'],door_transform())
    if p['stop_present'][0]:rigid('doorstop',p['stop_dimensions'],p['stop_location'],p['stop_mass'])
    scene.objects().create('floor').geometries().create(ground(0.,np.array([0.,0.,1.])))
    control={'tau':0.,'forces':np.zeros_like(placed)}
    if p['door_present'][0]:
        j=AffineBodyRevoluteJoint().create_geometry(np.array([[0.,LAYOUT['hinge_axis_y'],.16]]),np.array([[0.,LAYOUT['hinge_axis_y'],.73]]),
            [slots['cabinet']],np.array([0],np.int32),[slots['door']],np.array([0],np.int32),np.array([1e5]))
        AffineBodyRevoluteJointExternalForce().apply_to(j,p['hinge_torque'])
        obj=scene.objects().create('soft_close_hinge');obj.geometries().create(j)
        def hinge(info):
            g=info.geo_slots()[0].geometry();view(g.edges().find('external_torque'))[:]=control['tau']
            view(g.edges().find('external_torque/is_constrained'))[:]=1
        scene.animator().insert(obj,hinge)
    mesh=ipc_mesh(rest,faces);label_surface(mesh);h=p['towel_thickness'];E=p['towel_young_modulus'];nu=p['towel_poisson']
    shear_ratio=p.get('towel_shear_ratio',.04)
    StrainLimitingBaraffWitkinShell().apply_to(mesh,ElasticModuli2D.youngs_poisson(E,nu),
        ElasticModuli2D.youngs_poisson(E*h*shear_ratio,nu),mass_density=p['towel_density'],thickness=h/2,strain_rate=p.get('towel_strain_hardening',100.))
    bending_E=E*p.get('towel_bending_ratio',1.)
    D=bending_E*h**3/(12*(1-nu**2));DiscreteShellBending().apply_to(mesh,D/2)
    FiniteElementExternalForce().apply_to(mesh,np.zeros(3));cc.apply_to(mesh)
    if towel_present:
        cloth=scene.objects().create('towel');cloth.geometries().create(mesh)
        def air(info):
            g=info.geo_slots()[0].geometry();view(g.vertices().find('external_force')).reshape(-1,3)[:]=control['forces']
            mask=g.vertices().find('external_force/is_constrained')
            if mask is not None:view(mask)[:]=1
        scene.animator().insert(cloth,air)
    mass=np.asarray(mesh.vertices().find(builtin.volume).view()).reshape(-1)*p['towel_density']*(1. if towel_present else 0.)
    save(out/'simulation_config.json',dict(scene_id=CASE,case_id=a.case,physics=p,edit=edit,layout=LAYOUT,dt=a.dt,pitch=a.pitch,duration_s=a.duration,
        fps=24,solver='libuipc native CUDA IPC/ACCD, BW membrane, discrete shell bending, ABD, torque-driven revolute joint',
        config=cfg,towel_mass_kg=float(mass.sum()),bending_rigidity_nm=D,native_bending_coefficient_nm=D/2,
        inplane_young_modulus_pa=E,shear_to_membrane_ratio=shear_ratio,
        shear_input_effective_n_m=E*h*shear_ratio,shear_coefficient_n_m=E*h*shear_ratio/(2*(1+nu)),
        bending_young_modulus_pa=bending_E,bending_to_membrane_E_ratio=p.get('towel_bending_ratio',1.),
        strain_hardening_dimensionless=p.get('towel_strain_hardening',100.),
        pinned_cloth_vertices=0,door_motion_prescribed=False,material_product_calibrated=False,
        common_baseline_reconstruction_diagnostic=False,
        initial_rigid_velocities_restored=bool(seed_rigid_velocities),rigid_velocities_recorded=True,
        initial_state_sha256=sha(a.initial_state)if a.initial_state else None,
        shared_door_hold_s=LAYOUT['door_release_time'],settling_run=a.settle_only,
        timed_edits=schedule,absolute_start_time_s=start_time,source_cache=str(a.source_cache)if a.source_cache else None,
        source_cache_sha256=sha(a.source_cache)if a.source_cache else None,
        state_continuation='native FEM positions/velocities and ABD transforms/velocities restored; source clock retained'if schedule else None,
        temporary_door_stay='100 N*m/rad spring + 2 N*m*s/rad dashpot about initial hinge angle until release; no prescribed motion'))
    for name,(v,f,T)in geometries.items():np.savez_compressed(out/(name+'_geometry.npz'),vertices=v,faces=f,initial_transform=T)
    if seed is None:
        # Fail a source construction before CUDA if it intersects a real rigid
        # surface. This also catches secondary handles beneath a new drape.
        tri=placed[faces]
        samples=np.concatenate([placed,tri.mean(1),.5*(tri[:,0]+tri[:,1]),.5*(tri[:,1]+tri[:,2]),.5*(tri[:,0]+tri[:,2])])
        checks=[]
        for name,(v,f,T)in geometries.items():
            rigid_mesh=trimesh.Trimesh(v@T[:3,:3].T+T[:3,3],f,process=False)
            distance=trimesh.proximity.signed_distance(rigid_mesh,samples)
            checks.append(dict(object=name,max_interior_depth_m=float(max(0.,distance.max())),min_abs_distance_m=float(abs(distance).min())))
        save(out/'initial_geometry_preflight.json',dict(checks=checks,no_initial_state_overlap=all(r['max_interior_depth_m']<1e-8 for r in checks)))
        assert all(r['max_interior_depth_m']<1e-8 for r in checks),'Initial cloth intersects actual rigid geometry; reconstruct the common baseline before simulating'
    if a.geometry_preflight_only:
        assert seed is None and os.environ.get('CUDA_VISIBLE_DEVICES')=='','Geometry-only inspection must hide all CUDA devices'
        np.savez_compressed(out/'initial_placement_reference.npz',positions=placed,rest_positions=rest,faces=faces,uv=uv)
        save(out/'geometry_only_reference.json',{'simulated':False,'cuda_engine_constructed':False,'scope':'Actual CPU construction and initial rigid surface preflight only','worker':socket.gethostname()})
        print('CPU_INITIAL_GEOMETRY_CHECKED_NO_SIMULATION',flush=True);return
    start=time.monotonic();uipc.Logger.set_level(uipc.Logger.Info if a.duration<.25 else uipc.Logger.Warn);engine=Engine('cuda',str(out/'solver'));world=World(engine);world.init(scene)
    if not world.is_valid():raise RuntimeError('Invalid initial world')
    if towel_present:
        fem=world.features().find(FiniteElementStateAccessorFeature);fg=fem.create_geometry()
        for key,value in [(builtin.position,np.zeros(3)),(builtin.velocity,np.zeros(3))]:
            if fg.vertices().find(key)is None:fg.vertices().create(key,value)
        fem.copy_to(fg);dist,mapping=cKDTree(np.asarray(fg.positions().view()).reshape(-1,3)).query(rest)
        assert dist.max()<1e-8 and len(np.unique(mapping))==len(rest)
        view(fg.positions()).reshape(-1,3)[mapping]=placed
        view(fg.vertices().find(builtin.velocity)).reshape(-1,3)[mapping]=initial_v
        fem.copy_from(fg);world.retrieve()
    abd=world.features().find(AffineBodyStateAccessorFeature);ag=abd.create_geometry()
    for key,value in [(builtin.transform,np.eye(4)),(builtin.velocity,np.zeros((4,4)))]:
        if ag.instances().find(key)is None:ag.instances().create(key,value)
    if seed_rigid_velocities:
        abd.copy_to(ag);av=view(ag.instances().find(builtin.velocity)).reshape(-1,4,4)
        for i,name in enumerate(names):
            if name in seed_rigid_velocities:av[i]=seed_rigid_velocities[name]
        abd.copy_from(ag);world.retrieve()
    previous_angle=LAYOUT['door_initial_angle']
    if 'door'in seed_rigids:
        Ti=seed_rigids['door'];previous_angle=float(np.arctan2(Ti[1,0],Ti[0,0]))
        if 'door'in seed_rigid_velocities:
            W=seed_rigid_velocities['door'][:3,:3]@Ti[:3,:3].T
            previous_angle-=.5*(W[1,0]-W[0,1])*a.dt
    xs=[];vs=[];Ts=[];rigid_vs=[];telemetry=[];air_energy=0.
    def read(t,record):
        nonlocal previous_angle,air_energy
        if towel_present:
            fem.copy_to(fg);x=np.asarray(fg.positions().view()).reshape(-1,3)[mapping].copy();v=np.asarray(fg.vertices().find(builtin.velocity).view()).reshape(-1,3)[mapping].copy()
        else:
            x=placed.copy();v=np.zeros_like(placed)
        abd.copy_to(ag);T=np.asarray(ag.instances().find(builtin.transform).view()).reshape(-1,4,4).copy()
        rigid_v=np.asarray(ag.instances().find(builtin.velocity).view()).reshape(-1,4,4).copy()
        angle=0.;omega=0.;gap=0.
        if 'door'in names:
            transform=T[names.index('door')];angle=float(np.arctan2(transform[1,0],transform[0,0]));omega=(angle-previous_angle)/a.dt;previous_angle=angle
            # Closing spring preload + soft-close rotary dashpot. Both are forces;
            # the door can stall/reopen in response to cloth and added doorstop.
            if a.settle_only or t<LAYOUT['door_release_time']:
                control['tau']=100.*(LAYOUT['door_initial_angle']-angle)-2.*omega
            else:
                control['tau']=p['hinge_torque']-p['hinge_damping']*omega
            point=transform@np.array([.452,LAYOUT['door_back_y'],.74,1.]);gap=LAYOUT.get('frame_front_y',0.)-float(point[1])
        tri=x[faces];norm=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);area=np.linalg.norm(norm,axis=1)/2
        vn=np.zeros_like(x);va=np.zeros(len(x))
        for k in range(3):np.add.at(vn,faces[:,k],norm);np.add.at(va,faces[:,k],area/3)
        vn/=np.maximum(np.linalg.norm(vn,axis=1,keepdims=True),1e-20);speed=(v*vn).sum(1);tan=v-speed[:,None]*vn
        control['forces']=-.5*1.225*1.2*va[:,None]*(speed[:,None]*abs(speed[:,None])*vn+.03*np.linalg.norm(tan,axis=1)[:,None]*tan)
        power=float(np.sum(control['forces']*v));assert power<=1e-12;air_energy-=power*a.dt
        assert np.all(np.isfinite(x))and np.max(abs(x))<10
        telemetry.append([t,angle,omega,control['tau'],gap,x[:,2].min(),x[:,2].max(),np.max(np.linalg.norm(v,axis=1)),air_energy])
        if record:xs.append(x);vs.append(v);Ts.append(T);rigid_vs.append(rigid_v)
    count=round(a.duration*24);stride=round(1/(24*a.dt));assert abs(stride*a.dt-1/24)<1e-10
    read(start_time,True)
    handoff=None
    if source_cache is not None:
        i=edit_frame-1
        handoff={key:float(np.max(np.abs(actual-source_cache[key][i])))for key,actual in
            [('positions',xs[0]),('velocities',vs[0]),('rigid_transforms',Ts[0]),('rigid_velocities',rigid_vs[0])]}
        assert max(handoff.values())<1e-8,('Source state was not restored exactly',handoff)
        save(out/'state_handoff.json',dict(edit_frame=edit_frame,time_s=start_time,friction_before=source_cfg['physics']['towel_friction'],friction_after=p['towel_friction'],max_abs_error=handoff,verified=True))
    def checkpoint(filename):
        np.savez_compressed(out/filename,positions=np.array(xs),velocities=np.array(vs),faces=faces,uv=uv,rest_positions=rest,
            initial_positions=placed,vertex_masses=mass,rigid_transforms=np.array(Ts),rigid_velocities=np.array(rigid_vs),rigid_names=np.array(names),times=start_time+np.arange(len(xs))/24)
    for k in range(1,(count-1)*stride+1):
        if k<3:print('ADVANCE_BEGIN',k,flush=True)
        world.advance()
        if not world.is_valid():raise RuntimeError('Native IPC solve invalid')
        world.retrieve();read(start_time+k*a.dt,k%stride==0)
        if k<3:print('ADVANCE_END',k,'angle',previous_angle,flush=True)
        if k% (stride*6)==0:
            checkpoint('checkpoint.npz');print('FRAME',len(xs),'zmax',round(xs[-1][:,2].max(),4),'angle',round(previous_angle,6),'wall',round(time.monotonic()-start,1),flush=True)
    checkpoint('cache.npz')
    if source_cache is not None:
        (out/'cache.npz').rename(out/'continuation.npz')
        continuation=dict(np.load(out/'continuation.npz'))
        merged={k:np.concatenate([source_cache[k][:edit_frame-1],v])if k in frame_fields else v for k,v in continuation.items()}
        merged['initial_positions']=source_cache['initial_positions'].copy()
        assert len(merged['positions'])==96 and np.array_equal(merged['positions'][:edit_frame-1],source_cache['positions'][:edit_frame-1])
        np.savez_compressed(out/'cache.npz',**merged)
    np.savez_compressed(out/'telemetry.npz',values=np.array(telemetry),columns=np.array(['time_s','door_angle_rad','door_angular_velocity_rad_s','hinge_torque_nm','handle_gap_m','min_towel_z_m','max_towel_z_m','max_towel_speed_m_s','air_dissipation_j']))
    save(out/'completion.json',dict(complete=True,worker_host=socket.gethostname(),gpu_uuid=os.environ['CUDA_VISIBLE_DEVICES'],execution_job_name=os.environ.get('PCVE_JOB_NAME'),frames=96 if schedule else len(xs),continuation_frames=len(xs),timed_edits=schedule,state_handoff=handoff,runtime_s=time.monotonic()-start,cache_sha256=sha(out/'cache.npz')))
    print('COMPLETE',a.case,round(time.monotonic()-start,1),flush=True)

if __name__=='__main__':main()
