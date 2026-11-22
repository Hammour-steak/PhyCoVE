"""Native nonlinear shell / ABD / IPC with declared rigid-floor restitution."""
from pathlib import Path
import argparse,copy,hashlib,json,os,socket,sys,time
import numpy as np
from scipy.spatial import cKDTree

HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parents[2])]  # scene physics modules and the shared scripts/ modules
from vocab import SPEC,CASE_DSL,override_for
from geometry import bag_mesh,can_mesh
from floor_contact import skew,restitution_impulse


def save(p,o):p.write_text(json.dumps(o,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',choices=SPEC['cases'],default='source')
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--duration',type=float,default=4.)
    ap.add_argument('--prepare',choices=('empty','loaded'));ap.add_argument('--initial',type=Path)
    ap.add_argument('--dt',type=float);ap.add_argument('--velocity-tol',type=float)
    ap.add_argument('--rigid-relaxation-rate',type=float,default=0.)
    ap.add_argument('--prepare-validation',action='store_true')
    a=ap.parse_args();host=socket.gethostname().split('.')[0]
    assert a.rigid_relaxation_rate>=0 and (a.prepare or a.rigid_relaxation_rate==0)
    assert not a.prepare_validation or (a.prepare=='loaded' and a.rigid_relaxation_rate==0)
    assert os.name!='nt'
    uuid=os.environ.get('CUDA_VISIBLE_DEVICES','');assert uuid.startswith('GPU-')
    # scripts/ (pcve_gpu_policy) is already on sys.path
    from pcve_gpu_policy import require_gpu,rank_uuids
    assert rank_uuids([uuid],case_id='silicone_bag_can')==[uuid]
    gate=require_gpu(uuid,case_id='silicone_bag_can')
    # No uipc import or CUDA allocation precedes the shared GPU model gate.
    import uipc
    from uipc import builtin,view
    from uipc.core import Engine,World,Scene,AffineBodyStateAccessorFeature,FiniteElementStateAccessorFeature
    from uipc.geometry import trimesh as ipc_trimesh,ground,label_surface
    from uipc.constitution import AffineBodyConstitution,NeoHookeanShell,ElasticModuli2D,DiscreteShellBending

    p=copy.deepcopy(SPEC['baseline']);p.update(override_for(a.case));s=copy.deepcopy(SPEC['simulation'])
    if a.prepare:p['bag_present']=True;p['second_can_present']=a.prepare=='loaded'
    if a.dt:s['dt_s']=a.dt
    if a.velocity_tol:s['newton_velocity_tolerance_m_s']=a.velocity_tol
    dt=s['dt_s'];fps=SPEC['fps'];stride=round(1/fps/dt);frames=round(a.duration*fps)+1
    assert abs(stride*dt-1/fps)<1e-12
    a.out.mkdir(parents=True,exist_ok=True);assert not (a.out/'simulation.npz').exists(),'Preserve completed native run'
    if p['bag_present']:rv,rf,fixed,handles=bag_mesh(p,s['angular_resolution'],s['height_resolution'])
    else:rv=np.empty((0,3));rf=np.empty((0,3),np.int32);fixed=np.empty(0,bool);handles=np.empty(0,np.int32)
    thickness=np.full(len(rv),p['bag_thickness_m']);thickness[handles]=p['bag_handle_thickness_m']
    # A short molded transition spreads reinforcement at the four strap roots.
    if len(rv):
        high=np.zeros(len(rv));high[handles]=1
        edges=np.unique(np.sort(np.concatenate((rf[:,[0,1]],rf[:,[1,2]],rf[:,[2,0]])),axis=1),axis=0)
        for _ in range(2):
            spread=np.zeros(len(rv));np.maximum.at(spread,edges[:,0],high[edges[:,1]]*.45);np.maximum.at(spread,edges[:,1],high[edges[:,0]]*.45)
            high=np.maximum(high,spread)
        thickness=p['bag_thickness_m']+(p['bag_handle_thickness_m']-p['bag_thickness_m'])*high
    lumped=np.zeros(len(rv))
    if len(rv):
        q=rv[rf];area=.5*np.linalg.norm(np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]),axis=1)
        np.add.at(lumped,rf.ravel(),np.repeat(area*thickness[rf].mean(axis=1)*p['bag_density_kg_m3']/3,3))
    alpha=12. if a.prepare and not a.prepare_validation else p['bag_rayleigh_mass_damping_s_inv'];dissipated=0.
    cfg=Scene.default_config();cfg['dt']=dt;cfg['gravity']=[[0.],[0.],[-p['gravity_m_s2']]]
    cfg['contact']['d_hat']=s['contact_d_hat_m'];cfg['contact']['eps_velocity']=.0001
    cfg['newton']['semi_implicit']['enable']=0;cfg['newton']['velocity_tol']=s['newton_velocity_tolerance_m_s'];cfg['newton']['max_iter']=s['newton_max_iterations']
    cfg['linear_system']['fem_preconditioner']='mas';cfg['linear_system']['tol_rate']=1e-7;cfg['line_search']['max_iter']=64
    cfg['contact']['adaptive']['kappa_eval_scale']=1.;cfg['contact']['adaptive']['min_kappa']=1e8;cfg['contact']['adaptive']['max_kappa']=1e13
    scene=Scene(cfg);scene.contact_tabular().default_model(p['contact_friction'],1e10)
    scene.objects().create('floor').geometries().create(ground(p['floor_height_m'],np.array([0.,0.,1.])))
    # Match the visible counter, cabinet carcass and projecting door fronts.
    # These passive colliders are identical in source and every edit.
    from trimesh.creation import box as box_mesh
    for spec in SPEC['static_collision_boxes']:
        bm=box_mesh(extents=spec['dimensions_m'])
        static=ipc_trimesh(np.asarray(bm.vertices),np.asarray(bm.faces,np.int32));label_surface(static)
        AffineBodyConstitution().apply_to(static,2e11,650.)
        transform=np.eye(4);transform[:3,3]=spec['center_m'];view(static.transforms())[:]=transform
        fixed_slot=static.instances().find(builtin.is_fixed);assert fixed_slot is not None
        view(fixed_slot)[:]=1
        scene.objects().create(spec['id']).geometries().create(static)
    if len(rv):
        mesh=ipc_trimesh(rv,rf);label_surface(mesh)
        contact_h=p['bag_contact_envelope_thickness_m']
        # This backend requires a constant collision radius along every edge.
        # Use a conservative constant envelope, and compensate mechanical
        # triangle coefficients so native integrated energy uses physical h.
        NeoHookeanShell().apply_to(mesh,ElasticModuli2D.youngs_poisson(p['bag_young_modulus_pa'],p['bag_poisson_ratio']),mass_density=p['bag_density_kg_m3'],thickness=contact_h/2)
        for name in ('mu','lambda'):
            coefficients=view(mesh.triangles().find(name)).reshape(-1)
            coefficients[:]*=thickness[rf].mean(axis=1)/contact_h
        # The constructor used its scalar default for nodal volumes. Assign the
        # consistent lumped volume of each triangle's mean full thickness.
        volume_slot=mesh.vertices().find('volume');assert volume_slot is not None
        view(volume_slot).reshape(-1)[:]=lumped/p['bag_density_kg_m3']
        DiscreteShellBending().apply_to(mesh,1.)
        edge_indices=np.asarray(mesh.edges().topo().view()).reshape(-1,2)
        hinge_h=thickness[edge_indices].mean(axis=1)
        view(mesh.edges().find('bending_stiffness')).reshape(-1)[:]=p['bag_young_modulus_pa']*hinge_h**3/(24*(1-p['bag_poisson_ratio']**2))
        view(mesh.vertices().find(builtin.is_fixed))[:]=fixed.astype(np.int32)
        actual_volume=np.asarray(mesh.vertices().find('volume').view()).reshape(-1)
        assert abs(float(actual_volume.sum()*p['bag_density_kg_m3'])-float(lumped.sum()))<1e-7
        scene.objects().create('bag').geometries().create(mesh)
    bodies=[]
    if not a.prepare:bodies.append(('can',p['can_initial_location_m'],p['can_mass_kg'],p['can_radius_m'],p['can_height_m']))
    if p['second_can_present']:bodies.append(('second_can',p['second_can_preload_seed_location_m'],p['second_can_mass_kg'],p['second_can_radius_m'],p['second_can_height_m']))
    body_meshes=[];inertias=[]
    for name,loc,mass,radius,height in bodies:
        cm=can_mesh(radius,height);body_meshes.append(cm);inertias.append(cm.moment_inertia/cm.volume*mass)
        mesh=ipc_trimesh(np.array(cm.vertices),np.array(cm.faces,np.int32));label_surface(mesh)
        AffineBodyConstitution().apply_to(mesh,2e11,mass/cm.volume)
        T=np.eye(4);T[:3,3]=loc;view(mesh.transforms())[:]=T
        scene.objects().create(name).geometries().create(mesh)
    config=dict(case=a.case,scene_id=SPEC['scene_id'],physics=p,simulation=s,solver_config=cfg,edit_dsl=CASE_DSL[a.case],
        solver='libuipc 0.0.28 nonlinear shell + ABD + IPC; native substep Newton/Coulomb floor restitution',
        material_scope=SPEC['material_scope'],actual_host=host,gpu_uuid=uuid,gpu_policy=gate,uipc_version=uipc.__version__,python_executable=sys.executable,python_version=sys.version,
        output_fps=fps,output_states=frames,duration_s=a.duration,playback_rate=1.,preparation=a.prepare,
        initial_cache_sha256=sha(a.initial) if a.initial else None,
        scoped_preload_authorization=SPEC['preload_authorization'] if (a.prepare=='loaded' or a.case=='add_second_can') else None,
        bag_mass_kg=float(lumped.sum()),reinforcement_model='Local physical thickness determines nodal mass and edge bending; triangle Lame coefficients are scaled by physical_h/contact_h so native membrane energy integrates physical_h. Contact radius is uniformly conservative.',
        damping_rate_s_inv=alpha,initialization='Native preparation cache positions and velocities are carried into the output simulation; the original falling can starts at its shared transform and angular velocity.')
    config['static_collision_boxes']=SPEC['static_collision_boxes']
    config['contact_envelope_approximation']=dict(full_thickness_m=p['bag_contact_envelope_thickness_m'],
        max_excess_radius_m=(p['bag_contact_envelope_thickness_m']-p['bag_thickness_m'])/2,
        reason='Installed backend codim edge contact requires equal endpoint radii. No checks are disabled; the body-wall envelope is conservative by 0.5 mm per side.')
    config['preparation_rigid_relaxation_rate_s_inv']=a.rigid_relaxation_rate
    config['preparation_validation_under_main_damping']=a.prepare_validation
    config['time_axis_scope']='Numerical dynamic-relaxation pseudo-time for a static equilibrium; not part of the four-second video' if a.rigid_relaxation_rate else 'Physical time'
    save(a.out/'simulation_config.json',config)
    uipc.Logger.set_level(uipc.Logger.Warn);start=time.monotonic();engine=Engine('cuda',str(a.out/'solver'));world=World(engine);world.init(scene)
    assert world.is_valid()
    fem=world.features().find(FiniteElementStateAccessorFeature) if len(rv) else None;fg=fem.create_geometry() if fem else None;mapping=None
    if fem:
        for key,default in ((builtin.position,np.zeros(3)),(builtin.velocity,np.zeros(3))):
            if fg.vertices().find(key) is None:fg.vertices().create(key,default)
        fem.copy_to(fg);dist,mapping=cKDTree(np.asarray(fg.positions().view()).reshape(-1,3)).query(rv);assert dist.max()<1e-8
    initial=np.load(a.initial) if a.initial else None
    if initial is not None and fem:
        assert np.array_equal(initial['bag_rest_positions'],rv) and np.array_equal(initial['bag_faces'],rf)
        assert np.array_equal(initial['bag_vertex_thickness_m'],thickness)
        view(fg.vertices().find(builtin.position)).reshape(-1,3)[mapping]=initial['bag_positions'][-1]
        view(fg.vertices().find(builtin.velocity)).reshape(-1,3)[mapping]=initial['bag_velocities'][-1]
        fem.copy_from(fg);world.retrieve()
    abd=world.features().find(AffineBodyStateAccessorFeature) if bodies else None;ag=abd.create_geometry() if abd else None;indices=[]
    if abd:
        for key,default in ((builtin.transform,np.eye(4)),(builtin.velocity,np.zeros((4,4)))):
            if ag.instances().find(key) is None:ag.instances().create(key,default)
        abd.copy_to(ag);states=np.asarray(ag.instances().find(builtin.transform).view())
        for name,loc,_,_,_ in bodies:
            distances=np.linalg.norm(states[:,:3,3]-loc,axis=1);index=int(np.argmin(distances));assert distances[index]<1e-8 and index not in indices;indices.append(index)
        for j,(name,*_) in enumerate(bodies):
            index=indices[j]
            if name=='can':view(ag.instances().find(builtin.velocity))[index,:3,:3]=skew(p['can_initial_angular_velocity_rad_s'])
            elif initial is not None:
                ids=list(initial['rigid_body_ids']);k=ids.index('second_can')
                view(ag.instances().find(builtin.transform))[index]=initial['can_transforms'][-1,k]
                view(ag.instances().find(builtin.velocity))[index]=initial['can_velocities'][-1,k]
        abd.copy_from(ag);world.retrieve()
    config['resolved_initial_states_from_preparation']=bool(initial is not None);save(a.out/'simulation_config.json',config)
    XX=[];VV=[];TT=[];TV=[];rows=[];impacts=[];armed=[True]*len(bodies)
    for f in range(frames):
        if fem:
            fem.copy_to(fg);x=np.asarray(fg.positions().view()).reshape(-1,3)[mapping].copy();v=np.asarray(fg.vertices().find(builtin.velocity).view()).reshape(-1,3)[mapping].copy()
        else:x=np.empty((0,3));v=np.empty((0,3))
        if abd:
            abd.copy_to(ag);T=np.asarray(ag.instances().find(builtin.transform).view())[indices].copy();V=np.asarray(ag.instances().find(builtin.velocity).view())[indices].copy()
        else:T=np.empty((0,4,4));V=np.empty((0,4,4))
        XX.append(x);VV.append(v);TT.append(T);TV.append(V)
        row=dict(frame=f+1,time_s=f/fps,can_z_m=T[:,2,3].tolist(),bag_min_z_m=float(x[:,2].min()) if len(x) else None,
            bag_max_speed_m_s=float(np.linalg.norm(v,axis=1).max()) if len(v) else None,
            bag_p95_speed_m_s=float(np.quantile(np.linalg.norm(v,axis=1),.95)) if len(v) else None,
            anchor_error_m=float(np.linalg.norm(x[fixed]-rv[fixed],axis=1).max()) if len(x) else 0.,floor_impact_count=len(impacts))
        rows.append(row)
        if f%6==0 or f==frames-1:
            print('FRAME',f+1,'/',frames,json.dumps(row),'seconds',round(time.monotonic()-start,2),flush=True)
            save(a.out/'progress.json',dict(frame=f+1,total=frames,wall_seconds=time.monotonic()-start,row=row))
        if f==frames-1:break
        for k in range(stride):
            if abd:
                abd.copy_to(ag);Tminus=np.asarray(ag.instances().find(builtin.transform).view()).copy();Vminus=np.asarray(ag.instances().find(builtin.velocity).view()).copy()
                for index in indices:Vminus[index,2,3]-=p['gravity_m_s2']*dt
            previous=world.frame();world.advance();world.retrieve();assert world.is_valid() and world.frame()==previous+1
            if abd:
                abd.copy_to(ag);Tpost=np.asarray(ag.instances().find(builtin.transform).view());Vpost=view(ag.instances().find(builtin.velocity));changed=False
                for j,(name,loc,mass,radius,height) in enumerate(bodies):
                    index=indices[j];tm=Tpost[index];verts=np.asarray(body_meshes[j].vertices)
                    gap=float((verts@tm[:3,:3].T+tm[:3,3])[:,2].min()-p['floor_height_m'])
                    if gap>2*s['contact_d_hat_m']:armed[j]=True
                    if armed[j] and gap<1.5*s['contact_d_hat_m']:
                        corrected,event=restitution_impulse(tm,Vpost[index],Vminus[index],Tminus[index],verts,mass,inertias[j],p['floor_restitution'],p['contact_friction'])
                        if event:
                            Vpost[index]=corrected;changed=True;armed[j]=False
                            event.update(body_id=name,time_s=f/fps+(k+1)*dt,gap_m=gap)
                            impacts.append(event);print('FLOOR_IMPACT',json.dumps(event),flush=True)
                if changed:abd.copy_from(ag)
            if fem and alpha:
                fem.copy_to(fg);vel=view(fg.vertices().find(builtin.velocity)).reshape(-1,3)
                prior=vel[mapping].copy();factor=np.exp(-alpha*dt);vel[mapping]=prior*factor
                dissipated+=.5*(1-factor*factor)*float(np.sum(lumped[:,None]*prior*prior));fem.copy_from(fg)
            if abd and a.rigid_relaxation_rate:
                # Quasistatic preparation only: dissipative dynamic relaxation
                # locates equilibrium without prescribing positions or angles.
                # A separate free validation under main damping must pass.
                abd.copy_to(ag);vel=view(ag.instances().find(builtin.velocity))
                vel[indices]*=np.exp(-a.rigid_relaxation_rate*dt);abd.copy_from(ag)
    cm=can_mesh(p['can_radius_m'],p['can_height_m'])
    np.savez_compressed(a.out/'simulation.npz',times=np.arange(frames)/fps,bag_positions=np.asarray(XX),bag_velocities=np.asarray(VV),bag_faces=rf,bag_rest_positions=rv,
        bag_fixed_mask=fixed,bag_handle_indices=handles,bag_vertex_thickness_m=thickness,can_transforms=np.asarray(TT),can_velocities=np.asarray(TV),
        rigid_body_ids=np.array([b[0] for b in bodies]),can_vertices=np.asarray(cm.vertices),can_faces=np.asarray(cm.faces),bag_thickness_m=p['bag_thickness_m'])
    report=dict(status='complete',wall_seconds=time.monotonic()-start,integration_steps=(frames-1)*stride,states=frames,rows=rows,
        material_calibrated=False,manual_motion=False,manual_deformation=False,physical_time_s=rows[-1]['time_s'],
        declared_damping_rate_s_inv=alpha,cumulative_damping_dissipation_j=dissipated,floor_impacts=impacts,geometry_or_positions_overwritten_for_bounce=False)
    save(a.out/'simulation_report.json',report);print('COMPLETE',a.case,report['wall_seconds'],flush=True)


if __name__=='__main__':main()
