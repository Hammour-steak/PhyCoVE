"""Two-way native rigid / layered FEM / cloth contact; no hand-authored motion."""
from pathlib import Path
import argparse,copy,hashlib,json,sys,time,os
import numpy as np
from scipy.spatial import cKDTree
HERE=Path(__file__).resolve().parent
ROOT=next((parent for parent in HERE.parents if (parent/'tools/ipc_probe_deps').is_dir()),None)
if ROOT is None:raise RuntimeError('Cannot locate the PhyCoVE repository root')
sys.path[:0]=[str(ROOT/'tools/manifold3d_deps'),str(ROOT/'tools/ipc_probe_deps'),str(ROOT/'tools/viscosity_plugin')]
import uipc
from uipc import builtin,view
from uipc.core import Engine,World,Scene,AffineBodyStateAccessorFeature,FiniteElementStateAccessorFeature
from uipc.geometry import trimesh as ipc_trimesh,tetmesh,ground,label_surface,label_triangle_orient,flip_inward_triangles
from uipc.constitution import StableNeoHookean,ElasticModuli,AffineBodyConstitution,StrainLimitingBaraffWitkinShell,ElasticModuli2D,DiscreteShellBending,SoftTransformConstraint
from geometry import mat_volume,napkin,grass_volume,medicine_ball,mandarin,path_obstacle,vertex_masses,support_height
from edit_vocab import SPECS,edit_info,cases

def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def main():
    if not os.environ.get('CUDA_VISIBLE_DEVICES','').startswith('GPU-'):
        raise RuntimeError('Run GPU simulation only on a rechecked idle GPU bound by UUID')
    ap=argparse.ArgumentParser();ap.add_argument('--scene',choices=list(SPECS),required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--case',default='source');ap.add_argument('--duration',type=float);ap.add_argument('--dt',type=float);ap.add_argument('--preload',type=float)
    ap.add_argument('--resolution-times',type=float,default=1);ap.add_argument('--initial-state',type=Path);ap.add_argument('--velocity-tol',type=float,default=.000001)
    ap.add_argument('--no-viscosity',action='store_true')
    ap.add_argument('--edit-dsl',help='Solve this edit DSL instead of the catalog entry of --case (--case is then only the record label).')
    ap.add_argument('--newton-iterations',type=int,default=1000)
    ap.add_argument('--native-info-after',type=int)
    ap.add_argument('--volume-viscosity-scale',type=float,default=1.,help='Explicit research sweep; not a benchmark edit.')
    ap.add_argument('--surface-viscosity-scale',type=float,default=1.,help='Explicit research sweep; not a benchmark edit.')
    ap.add_argument('--membrane-viscosity-scale',type=float,default=1.,help='Preparation or research only: scales membrane viscosity, retaining bending dissipation.')
    ap.add_argument('--preparation-inertia-scale',type=float,default=1.,help='Unrecorded static optimization only; changes inertia while preserving gravity and contact mass bounds.')
    ap.add_argument('--relax-initial',type=float,default=0.,help='Optional physical relaxation after importing a gravity-equilibrated warm start, before recording.')
    ap.add_argument('--preparation-checkpoint-stride',type=int,default=0)
    ap.add_argument('--preparation-stop-velocity',type=float,default=0.)
    ap.add_argument('--preparation-info',action='store_true',help='Research logging for unrecorded preparation Newton and line-search iterations.')
    ap.add_argument('--arrange-free-corner',action='store_true',help='Unrecorded common-baseline assembly only: lay one free corner over itself, then gravity-relax.')
    ap.add_argument('--preparation-reset-velocities',action='store_true',help='Unrecorded quasi-static optimization only: discard optimizer momentum between preparation iterations.')
    a=ap.parse_args();spec=copy.deepcopy(SPECS[a.scene]);p=spec['physics'];q=spec['simulation'];gym=a.scene=='gym_landing_mat'
    info=edit_info(a.scene,a.edit_dsl if a.edit_dsl else cases(a.scene)[a.case]);p.update(info.get('override',{}))
    if a.volume_viscosity_scale!=1:
        for key in ['volume_shear_viscosity','volume_bulk_viscosity']:p[key]*=a.volume_viscosity_scale
    if a.surface_viscosity_scale!=1:
        for key in ['surface_shear_viscosity','surface_bulk_viscosity','bending_viscosity']:p[key]*=a.surface_viscosity_scale
    if a.membrane_viscosity_scale!=1:
        for key in ['surface_shear_viscosity','surface_bulk_viscosity']:p[key]*=a.membrane_viscosity_scale
    for k in ['duration','dt']:
        if getattr(a,k) is not None:q[k]=getattr(a,k)
    if a.preload is not None:q['preload_seconds']=a.preload
    if a.initial_state:q['preload_seconds']=0.
    if a.resolution_times!=1:
        if gym:q['solid_grid']=[max(3,round((n-1)*a.resolution_times)+1) for n in q['solid_grid']]
        else:p['cloth_pitch']/=a.resolution_times
    dt=q['dt'];fps=q['fps'];stride=round(1/(fps*dt));count=round(fps*q['duration'])
    if a.preparation_inertia_scale!=1 and(count!=1 or a.no_viscosity):raise ValueError('Reduced preparation inertia is allowed only for a single-state, unrecorded preparation task')
    if a.preparation_reset_velocities and(a.preparation_inertia_scale==1 or count!=1):raise ValueError('Optimizer momentum reset is restricted to unrecorded static preparation')
    if a.arrange_free_corner and(gym or count!=1 or not a.initial_state or a.case!='source' or a.relax_initial<=0):raise ValueError('Corner assembly is restricted to an unrecorded, single-state picnic preparation with subsequent gravity relaxation')
    if abs(stride*dt-1/fps)>1e-10:raise ValueError('Output interval is not divisible by dt')
    out=a.out.resolve()
    if out.exists() and any(out.iterdir()):raise FileExistsError(out)
    out.mkdir(parents=True)
    for path in [HERE/'simulate.py',HERE/'geometry.py',HERE.parents[2]/'pcve_fem_geometry.py',HERE/'edit_vocab.py',HERE/'scene_specs.json',HERE/'viscosity.py']:
        (out/('source_'+path.name)).write_bytes(path.read_bytes())
    if gym:sv,st,cv,cf,cover_ids=mat_volume(p,q)
    else:sv,st,cover_ids=grass_volume(p);cv,cf=napkin(p)
    # Presence of the elastic body (active[1]; DELETE of the landing mat / the blanket). Absent: no cover shell, and
    # for the gym no foam core either; the rigid bodies and the floor are unchanged.
    elastic_present=bool(p['active'][1])
    if not elastic_present:
        cv=np.empty((0,3));cf=np.empty((0,3),np.int32)
        if gym:sv=np.empty((0,3));st=np.empty((0,4),np.int32);cover_ids=np.empty(0,np.int64)
    # The native viscosity extension registers an FEM-bound solver system, so it is loaded only when an FEM body exists
    # (always, except for the deleted landing mat, where only the ball and the floor remain).
    if len(sv)+len(cv):from viscosity import apply_viscosity,viscosity_manifest,apply_static_preparation
    canonical_reference=None
    if gym and a.initial_state and elastic_present:
        # Preserve the exact source rest metric across CPU SIMD/libm variants.
        # The generated mesh must match to 1 pm and connectivity must be exact;
        # only then load the original rest arrays before constructing the FEM.
        with np.load(a.initial_state)as reference:
            for key,value in [('solid_tetrahedra',st),('cloth_faces',cf)]:
                if not np.array_equal(reference[key],value):raise RuntimeError('Canonical mesh connectivity changed: '+key)
            errors={key:float(np.max(abs(reference[key]-value)))for key,value in [('solid_rest_positions',sv),('cloth_rest_positions',cv)]}
            if max(errors.values())>1e-12:raise RuntimeError('Canonical reference geometry differs materially: '+str(errors))
            sv=reference['solid_rest_positions'].copy();cv=reference['cloth_rest_positions'].copy()
            canonical_reference=dict(source_sha256=hashlib.sha256(a.initial_state.read_bytes()).hexdigest(),generated_roundoff_m=errors,exact_source_rest_arrays_loaded=True)
    for name in ['native_viscosity.cu','native_viscosity_frontend.cpp']:  # shared sources scripts/pcve_<name>
        (out/('source_'+name)).write_bytes((HERE.parents[2]/('pcve_'+name)).read_bytes())
    hold_actor={'enabled':True}
    body_mesh=medicine_ball() if gym else mandarin();body_present=bool(p['active'][0]);initial=np.eye(4);initial[:3,3]=p['body_initial_location']
    spawn=initial.copy()
    if not gym:spawn[2,3]=max(spawn[2,3],p['cloth_height']+p['body_radius']+.010)
    cfg=Scene.default_config();cfg['dt']=dt;cfg['gravity']=[[0.],[0.],[-9.81]];cfg['contact']['d_hat']=q['d_hat'];cfg['contact']['eps_velocity']=.0001
    cfg['newton']['semi_implicit']['enable']=0;cfg['newton']['velocity_tol']=a.velocity_tol;cfg['newton']['max_iter']=a.newton_iterations
    cfg['linear_system']['fem_preconditioner']='mas';cfg['linear_system']['tol_rate']=1e-9;cfg['line_search']['max_iter']=48
    # Positive user-specified kappa stays fixed. A corridor evaluation point
    # outside the barrier support has H_b <= 0; the native code then uses the
    # explicit finite bounds. Scale must be positive (zero fails the schema).
    cfg['contact']['adaptive']['kappa_eval_scale']=1.
    cfg['contact']['adaptive']['min_kappa']=1e8
    cfg['contact']['adaptive']['max_kappa']=1e13
    # Keep contact coefficients explicitly recorded. The native engine may scale them.
    resistance=1e12 if gym else 1e11
    scene=Scene(cfg);scene.contact_tabular().default_model(.55,resistance)
    actor_contact=scene.contact_tabular().create('actor_contact')
    scene.contact_tabular().insert(actor_contact,scene.contact_tabular().default_element(),p['friction'],resistance)
    scene.objects().create('fixed_floor').geometries().create(ground(0,np.array([0.,0.,1.])))
    obstacle_present=bool(p['gym_water_bottle_active'][0]) if gym else bool(p['picnic_cup_active'][0])
    obstacle_mesh=path_obstacle(a.scene,p) if obstacle_present else None
    obstacle_id='gym_water_bottle' if gym else 'picnic_cup'
    obstacle_contact=scene.contact_tabular().default_element()
    if gym and obstacle_present:
        obstacle_contact=scene.contact_tabular().create('dynamic_water_bottle_contact')
        bottle_resistance=p['gym_water_bottle_contact_resistance']
        scene.contact_tabular().insert(obstacle_contact,scene.contact_tabular().default_element(),p['gym_water_bottle_surface_friction'],bottle_resistance)
        scene.contact_tabular().insert(obstacle_contact,actor_contact,p['gym_water_bottle_ball_friction'],bottle_resistance)
    obstacle_initial=np.eye(4)
    obstacle_initial[:3,3]=p['gym_water_bottle_location' if gym else 'picnic_cup_location']
    if gym:
        # Bottle collision mesh is modelled along local Z and lies across the
        # ball path along world Y, so an impact drives a visible +X roll.
        obstacle_initial[:3,:3]=np.array([[1.,0.,0.],[0.,0.,-1.],[0.,1.,0.]])
    if obstacle_mesh is not None:
        om=ipc_trimesh(np.asarray(obstacle_mesh.vertices),np.asarray(obstacle_mesh.faces,np.int32));label_surface(om)
        obstacle_mass=p['gym_water_bottle_mass' if gym else 'picnic_cup_mass']
        AffineBodyConstitution().apply_to(om,1e9,obstacle_mass/obstacle_mesh.volume)
        view(om.transforms())[:]=obstacle_initial
        view(om.instances().find(builtin.is_fixed))[:]=0
        obstacle_contact.apply_to(om)
        scene.objects().create(obstacle_id).geometries().create(om)
    solid_slot=None;core_contact=None;material={}
    fixed_s=np.zeros(len(sv),bool)
    if len(sv):
        m=tetmesh(sv,st);label_surface(m);label_triangle_orient(m);m=flip_inward_triangles(m)
        StableNeoHookean().apply_to(m,ElasticModuli.youngs_poisson(32000,.25),mass_density=p['solid_density'])
        # Correct the installed SNK1 API-to-kernel mapping. These are actual tangent E,nu.
        centre=sv[st].mean(axis=1);E=p['solid_young_modulus']*np.where(centre[:,2]<.055,p['lower_layer_stiffness_ratio'],1.) if gym else np.full(len(st),p['solid_young_modulus'])
        nu=p['solid_poisson_ratio'];mu=E/(2*(1+nu));lam=E*nu/((1+nu)*(1-2*nu))
        view(m.tetrahedra().find('mu')).reshape(-1)[:]=mu
        view(m.tetrahedra().find('lambda')).reshape(-1)[:]=lam+mu
        if gym:
            core_contact=scene.contact_tabular().create('enclosed_foam_interior');core_contact.apply_to(m)
            for other in [core_contact,actor_contact]:scene.contact_tabular().insert(core_contact,other,0.,1e9,False)
        else:
            fixed_s=np.isclose(sv[:,2],sv[:,2].min(),atol=1e-10)
            view(m.vertices().find(builtin.is_fixed))[:]=fixed_s.astype(np.int32)
        material=dict(layer_top_actual_linearized_E_pa=p['solid_young_modulus'],layer_base_actual_linearized_E_pa=p['solid_young_modulus']*p['lower_layer_stiffness_ratio'],actual_nu=nu,
            native_mu_pa_range=[float(mu.min()),float(mu.max())],native_lambda_pa_range=[float((lam+mu).min()),float((lam+mu).max())],mapping_corrected=True,
            limitation='Two-layer compressible SNK1 with jointly solved objective metric viscosity; not fitted to measured foam plateau, hysteresis or relaxation data.')
        apply_viscosity(m,p['volume_shear_viscosity'],p['volume_bulk_viscosity'],0.,disabled=a.no_viscosity)
        if a.preparation_inertia_scale!=1:apply_static_preparation(m,a.preparation_inertia_scale,[0.,0.,-9.81])
        solid_obj=scene.objects().create('foam_core'if gym else'rooted_effective_grass_thatch');solid_slot,_=solid_obj.geometries().create(m)
        if not gym:material=dict(model='Free Baraff-Witkin woven cloth with Discrete Shells bending on a compressible rooted FEM grass-thatch layer',calibrated=False,cloth_fixed_vertices=0,grass_root_fixed_vertices=int(fixed_s.sum()),grass_model='Effective elastic/viscous vegetation continuum; individual grass blades are not independently simulated')
    if elastic_present:
        m=ipc_trimesh(cv,cf);label_surface(m)
        h=p['cover_thickness' if gym else 'cloth_thickness'];rho=p['cover_density' if gym else 'cloth_density'];Estretch=p['cover_stretch_modulus' if gym else 'cloth_young_modulus'];Eshear=p['cover_shear_modulus' if gym else 'cloth_shear_modulus'];bend=p['cover_bending_stiffness' if gym else 'cloth_bending_stiffness']
        StrainLimitingBaraffWitkinShell().apply_to(m,ElasticModuli2D.youngs_poisson(Estretch,.3),ElasticModuli2D.youngs_poisson(Eshear,.3),mass_density=rho,thickness=h/2,strain_rate=100.)
        DiscreteShellBending().apply_to(m,bend)
        if not gym:material['support']='Entire cloth is free. Distributed IPC contact and friction against deformable rooted vegetation; no pins, cuffs, clips or basket.'
        mass_c=np.asarray(m.vertices().find(builtin.volume).view()).reshape(-1)*rho
        fixed_c=np.asarray(m.vertices().find(builtin.is_fixed).view()).reshape(-1).astype(bool)
        apply_viscosity(m,p['surface_shear_viscosity'],p['surface_bulk_viscosity'],p['bending_viscosity'],disabled=a.no_viscosity)
        if a.preparation_inertia_scale!=1:apply_static_preparation(m,a.preparation_inertia_scale,[0.,0.,-9.81])
        cloth_obj=scene.objects().create('cover' if gym else 'linen_napkin');cloth_slot,_=cloth_obj.geometries().create(m)
        if gym:
            material['cover_attachment']='Closed loose PVC envelope with 0.8% lateral manufacturing ease, two-way frictional contact with the foam core. No bonded skin and no shape animation.'
        material.update(shell_full_thickness_m=h,shell_density_kg_m3=rho,shell_stretch_input_pa=Estretch,shell_shear_input=Eshear,shell_bending_input_nm=bend)
        material.update(shell_stretch_coefficient_n_per_m=Estretch*h/(1-.3**2),shell_shear_coefficient_n_per_m=Eshear/(2*(1+.3)),shell_shear_convention='Native independent 2D parameter: E_shear/(2*(1+nu)), with no thickness multiplier. Not a 3D shear modulus in Pa.')
    else:
        mass_c=np.empty(0);fixed_c=np.empty(0,bool);cloth_slot=None
        material['deleted_elastic_body']=dict(object_id=spec['elastic_id'],removed=('foam core and cover shell' if gym else 'cloth shell'),note='DELETE: the body is not created in the native scene; every other body, contact coefficient and setting is unchanged.')
    if body_present:
        m=ipc_trimesh(np.asarray(body_mesh.vertices),np.asarray(body_mesh.faces,np.int32));label_surface(m)
        AffineBodyConstitution().apply_to(m,1e9,p['body_mass']/body_mesh.volume);view(m.transforms())[:]=spawn
        actor_contact.apply_to(m)
        SoftTransformConstraint().apply_to(m,np.array([100000.,100000.]))
        actor_object=scene.objects().create(spec['actor_id']);actor_object.geometries().create(m)
        def hold_callback(info):
            current=info.geo_slots()[0].geometry()
            view(current.instances().find(builtin.is_constrained))[:]=1 if hold_actor['enabled'] else 0
            view(current.instances().find(builtin.aim_transform))[:]=spawn
        scene.animator().insert(actor_object,hold_callback)
    uipc.Logger.set_level(uipc.Logger.Warn);engine=Engine('cuda',str(out/'solver'));world=World(engine)
    config=dict(scene_id=a.scene,case=a.case,physics=p,simulation=q,edit=info,solver='libuipc CUDA FEM / thin shells / ABD / IPC + jointly solved native objective metric and dihedral viscosity; NOT MPM',solver_config=cfg,material=material,added_object=(obstacle_id if obstacle_present else None),hand_authored_deformation=False,hand_authored_motion=False,constitutive_velocity_updates=False,constitutive_force_updates=False,viscous_coupling='Native SoftTransformConstraint animator: F=M*(v_viscous-v)/dt; equivalent BDF1 inertial predictor, no per-step state writes or friction-cache invalidation.',release_status='ITERATION_REQUIRES_MATERIAL_AND_NUMERICAL_VALIDATION')
    if canonical_reference:config['canonical_reference_geometry']=canonical_reference
    config['contact_tabular_added_proxy']=dict(proxy_label=('dynamic_water_bottle_contact' if gym and obstacle_present else 'default_element'),moving_rigid_label='actor_contact',surface_friction=(p['gym_water_bottle_surface_friction'] if gym and obstacle_present else p['friction']),actor_friction=(p['gym_water_bottle_ball_friction'] if gym and obstacle_present else p['friction']),resistance=(p['gym_water_bottle_contact_resistance'] if gym and obstacle_present else resistance),fixed_affine_body=False,mass_kg=(p['gym_water_bottle_mass' if gym else 'picnic_cup_mass'] if obstacle_present else 0.),reason='The closed ADD prop is a second dynamic affine rigid body. Gravity, rigid/rigid IPC and rigid/elastic IPC determine its settling, impact translation and rotation. The lower bottle-pair contact coefficient represents local compliance of the thin PCTG wall; the main medicine-ball/mat coefficient remains unchanged.')
    config['viscous_coupling']='Native incremental objective metric and dihedral viscous potentials, exact gradients and exact Hessians with PSD projection enter the same contact/elastic Newton solve; no operator split or per-step state writes.'
    config['initialization']=dict(unrecorded_actor_clearance_transform=spawn.tolist(),recorded_initial_transform=initial.tolist(),recorded_initial_angular_velocity_rad_s=p.get('body_initial_angular_velocity',[0.,0.,0.]),placement_frozen_for_all_edits=True)
    config['contact_potential_coefficient']=dict(requested=resistance,refinement_requirement='Keep the active coefficient inside both source and refined native bounds, so changing dt does not silently change contact compliance.')
    config['contact_potential_coefficient']['corridor_policy']='Fixed positive contact coefficients. Positive evaluation scale=1 places the corridor probe outside barrier support (H_b<=0), using the native explicit-bounds fallback [1e8,1e13]. Earlier retained runs already had the same unclamped active coefficients; their original corridor policy remains in per-run snapshots.'
    if a.preparation_inertia_scale!=1:
        config['release_status']='UNRECORDED_STATIC_PREPARATION_ONLY';config['preparation_inertia_scale']=a.preparation_inertia_scale;config['preparation_method']='Reduced-inertia static relaxation. Original gravity force, original contact masses/bounds and all elastic terms retained. Not a physical motion clip; canonical recording inertia scale is 1.'
    save(out/'simulation_config.json',config);start=time.monotonic();world.init(scene)
    if not world.is_valid():raise RuntimeError('Invalid initial geometry')
    fem=fg=None;mapping=np.empty(0,np.int64)
    if len(sv)+len(cv):
        fem=world.features().find(FiniteElementStateAccessorFeature);fg=fem.create_geometry()
        for n,v in [(builtin.position,np.zeros(3)),(builtin.velocity,np.zeros(3))]:
            if fg.vertices().find(n) is None:fg.vertices().create(n,v)
        fem.copy_to(fg);expected=np.concatenate([sv,cv]);dist,mapping=cKDTree(np.asarray(fg.positions().view()).reshape(-1,3)).query(expected)
        if dist.max()>1e-8 or len(np.unique(mapping))!=len(expected):raise RuntimeError('Canonical FEM mapping failed')
    if not gym and not a.initial_state and len(cv):
        positions=view(fg.vertices().find(builtin.position)).reshape(-1,3)
        positions[mapping[len(sv):],:2]*=p['cloth_initial_xy_scale']
        placed=positions[mapping[len(sv):]].copy()
        xp,yp=placed[:,:2].T
        support=support_height(p,xp,yp)
        placed[:,2]=support+.0020+.0015*(1+np.sin(31*xp+.2)*np.sin(27*yp-.3))
        positions[mapping[len(sv):]]=placed
        fem.copy_from(fg);world.retrieve()
        material['physical_preparation']=f"Flat reference cloth is placed with {100*(1-p['cloth_initial_xy_scale']):.1f}% in-plane assembly ease and small placement folds, then physically gravity-draped. Preparation ends before recording; no recorded positions are authored."
    masses=np.concatenate([vertex_masses(sv,st,p['solid_density'])[0] if len(sv) else np.empty(0),mass_c]);fixed_all=np.concatenate([fixed_s,fixed_c])
    visc_info=viscosity_manifest() if len(sv)+len(cv) else dict(loaded=False,reason='No FEM body (landing mat deleted): the native FEM viscosity extension is not loaded.')
    visc_info['enabled']=not a.no_viscosity if len(sv)+len(cv) else False
    material['viscous_stage']=visc_info;config['native_viscosity']=visc_info
    material['limitation']='Effective elastic and viscous parameters; no product-specific measured indentation, hysteresis, or relaxation fit.'
    save(out/'simulation_config.json',config)
    recording={'enabled':False,'step':0};diagnostics=[];eq=None
    corners=np.where((abs(cv[:,0])>p.get('cloth_dimensions',[9,9])[0]/2-.012)&(abs(cv[:,1])>p.get('cloth_dimensions',[9,9])[1]/2-.012))[0] if not gym else np.empty(0,np.int32)
    def sample_diagnostic():
        if fem is not None:fem.copy_to(fg);x=np.asarray(fg.positions().view()).reshape(-1,3)[mapping]
        else:x=np.empty((0,3))
        shell=x[len(sv):]
        if abd:abd.copy_to(ag)
        T=np.asarray(ag.instances().find(builtin.transform).view())[actor_index] if body_present else initial
        near=np.linalg.norm(shell[:,:2]-T[:2,3],axis=1)<(.12 if gym else .065)
        if gym:near&=cv[:,2]>.09
        dent=float(np.max(eq[len(sv):][near,2]-shell[near,2])) if near.any() else 0.
        world_body=np.asarray(body_mesh.vertices)@T[:3,:3].T+T[:3,3]
        corner=float(np.linalg.norm(shell[corners]-eq[len(sv):][corners],axis=1).max()) if len(corners) else 0.
        diagnostics.append([recording['step']*dt,*T[:3,3],float(world_body[:,2].min()),dent,corner])
    def advance():
        if recording['enabled'] and a.native_info_after is not None and recording['step']>=a.native_info_after:uipc.Logger.set_level(uipc.Logger.Info)
        world.advance()
        if not world.is_valid():raise RuntimeError('Native world became invalid during physical advance')
        world.retrieve()
        if recording['enabled']:
            recording['step']+=1;sample_diagnostic()
    abd=world.features().find(AffineBodyStateAccessorFeature);ag=abd.create_geometry() if abd else None
    if body_present and abd is None:raise RuntimeError('Missing native rigid-body accessor')
    if abd:
        for n,v in [(builtin.transform,np.eye(4)),(builtin.velocity,np.zeros((4,4)))]:
            if ag.instances().find(n) is None:ag.instances().create(n,v)
        abd.copy_to(ag)
    # A fixed ADD proxy is created before the moving affine body, so its ABD
    # slot is index 0. Track the actual actor slot instead of recording the
    # proxy transform as if it were the medicine ball.
    obstacle_index=0 if obstacle_present else None
    actor_index=1 if (obstacle_present and body_present) else 0
    def reset_body(velocity=(0,0,0)):
        if not body_present:return
        abd.copy_to(ag);view(ag.instances().find(builtin.transform))[actor_index]=initial
        V=np.zeros((4,4));V[:3,3]=velocity
        wx,wy,wz=p.get('body_initial_angular_velocity',[0.,0.,0.]);W=np.array([[0.,-wz,wy],[wz,0.,-wx],[-wy,wx,0.]])
        V[:3,:3]=W@initial[:3,:3];view(ag.instances().find(builtin.velocity))[actor_index]=V;abd.copy_from(ag)
    def preparation_checkpoint(step):
        fem.copy_to(fg);px=np.asarray(fg.positions().view()).reshape(-1,3)[mapping].copy();pv=np.asarray(fg.vertices().find(builtin.velocity).view()).reshape(-1,3)[mapping].copy()
        free_speed=float(np.sqrt(np.mean((pv[~fixed_all]**2).sum(1))));corner_speed=float(np.linalg.norm(pv[len(sv):][corners],axis=1).max())if len(corners)else 0.
        np.savez_compressed(out/f'preparation_step_{step:05d}.npz',solid_positions=px[None,:len(sv)],solid_velocities=pv[None,:len(sv)],solid_rest_positions=sv,solid_tetrahedra=st,cloth_positions=px[None,len(sv):],cloth_velocities=pv[None,len(sv):],cloth_rest_positions=cv,cloth_faces=cf,cloth_fixed_mask=fixed_c)
        print('PREPARATION_CHECKPOINT',step,'free_vrms',free_speed,'max_corner_speed',corner_speed,flush=True)
        return free_speed,corner_speed
    def reset_preparation_momentum():
        fem.copy_to(fg);view(fg.vertices().find(builtin.velocity))[:]=0.;fem.copy_from(fg);world.retrieve()
    if a.initial_state:
        z=np.load(a.initial_state)
        if elastic_present and 'cloth_fixed_mask'in z and not np.array_equal(z['cloth_fixed_mask'],fixed_c):raise ValueError('Prepared support mask differs from the current physical attachment')
        for key,value in [('solid_rest_positions',sv),('cloth_rest_positions',cv),('solid_tetrahedra',st),('cloth_faces',cf)]:
            if not elastic_present and key.startswith('cloth'):continue  # deleted cover / blanket: only the remaining FEM body is loaded
            if not np.array_equal(z[key],value):raise RuntimeError('Initial state geometry mismatch: '+key)
        x=np.concatenate([z['solid_positions'][0],z['cloth_positions'][0][:len(cv)]]);v=np.concatenate([z['solid_velocities'][0],z['cloth_velocities'][0][:len(cv)]])
        if a.arrange_free_corner:
            shell=x[len(sv):];normal=np.array([1.,-1.,0.])/np.sqrt(2.);s=(shell[:,0]-shell[:,1]-.558)/np.sqrt(2.);mask=s>0;theta=np.deg2rad(140.)
            shell[mask,:]-=s[mask,None]*(1-np.cos(theta))*normal
            shell[mask,2]+=s[mask]*np.sin(theta);v[:]=0.
            config['common_baseline_assembly']=dict(scope='Unrecorded layout construction only; no benchmark edit uses this flag',free_corner_fold_deg=140.,rest_metric_unchanged=True,subsequent_motion='Native gravity/contact/bending relaxation, no pinned cloth vertices or recorded state writes')
            config['release_status']='UNRECORDED_LAYOUT_PREPARATION_ONLY'
        view(fg.vertices().find(builtin.position)).reshape(-1,3)[mapping]=x;view(fg.vertices().find(builtin.velocity)).reshape(-1,3)[mapping]=v;fem.copy_from(fg);world.retrieve()
        if obstacle_present:
            abd.copy_to(ag);settled_start=obstacle_initial.copy();settled_start[:3,3]=p['gym_water_bottle_settle_location' if gym else 'picnic_cup_settle_location']
            view(ag.instances().find(builtin.transform))[obstacle_index]=settled_start;view(ag.instances().find(builtin.velocity))[obstacle_index]=0.;abd.copy_from(ag);world.retrieve()
        config['initial_state_source']=dict(path=str(a.initial_state),sha256=hashlib.sha256(a.initial_state.read_bytes()).hexdigest())
        save(out/'simulation_config.json',config)
        if a.relax_initial:
            if a.preparation_info:uipc.Logger.set_level(uipc.Logger.Info)
            config['initial_state_source']['additional_physical_relaxation_seconds']=a.relax_initial
            for k in range(round(a.relax_initial/dt)):
                if a.preparation_reset_velocities:reset_preparation_momentum()
                advance()
                if a.preparation_checkpoint_stride and(k+1)%a.preparation_checkpoint_stride==0:
                    free_speed,corner_speed=preparation_checkpoint(k+1)
                    if a.preparation_stop_velocity and(k+1)*dt>=1.5 and free_speed<a.preparation_stop_velocity and corner_speed<2*a.preparation_stop_velocity:
                        config['preparation_early_stop']=dict(seconds=(k+1)*dt,free_rms_velocity_mps=free_speed,max_corner_velocity_mps=corner_speed,threshold_mps=a.preparation_stop_velocity);break
            save(out/'simulation_config.json',config)
            if a.preparation_info:uipc.Logger.set_level(uipc.Logger.Warn)
            if a.preparation_reset_velocities:
                reset_preparation_momentum();config['preparation_optimizer_momentum_reset']=True
                save(out/'simulation_config.json',config)
    else:
        if a.preparation_info:uipc.Logger.set_level(uipc.Logger.Info)
        for k in range(round(q['preload_seconds']/dt)):
            if a.preparation_reset_velocities:reset_preparation_momentum()
            advance()
            if k%300==0:print('PRELOAD',k,round(time.monotonic()-start,1),flush=True)
            if a.preparation_checkpoint_stride and (k+1)%a.preparation_checkpoint_stride==0:
                fem.copy_to(fg);px=np.asarray(fg.positions().view()).reshape(-1,3)[mapping].copy();pv=np.asarray(fg.vertices().find(builtin.velocity).view()).reshape(-1,3)[mapping].copy()
                free_speed=float(np.sqrt(np.mean((pv[~fixed_all]**2).sum(1))))
                np.savez_compressed(out/f'preparation_step_{k+1:05d}.npz',solid_positions=px[None,:len(sv)],solid_velocities=pv[None,:len(sv)],solid_rest_positions=sv,solid_tetrahedra=st,cloth_positions=px[None,len(sv):],cloth_velocities=pv[None,len(sv):],cloth_rest_positions=cv,cloth_faces=cf,cloth_fixed_mask=fixed_c)
                print('PREPARATION_CHECKPOINT',k+1,'free_vrms',free_speed,flush=True)
                if a.preparation_stop_velocity and (k+1)*dt>=1.5 and free_speed<a.preparation_stop_velocity:
                    config['preparation_early_stop']=dict(seconds=(k+1)*dt,free_rms_velocity_mps=free_speed,threshold_mps=a.preparation_stop_velocity);save(out/'simulation_config.json',config);break
        if a.preparation_info:uipc.Logger.set_level(uipc.Logger.Warn)
    if a.preparation_reset_velocities:reset_preparation_momentum()
    # The added prop alone receives a short unrecorded physical settling pass.
    # The actor stays constrained at its clearance pose. This lets the cup
    # actually load the blanket/grass and lets the bottle rest on the mat.
    if obstacle_present:
        settle_steps=round(p.get('path_obstacle_settle_seconds',0.)/dt)
        for _ in range(settle_steps):advance()
        abd.copy_to(ag)
        view(ag.instances().find(builtin.velocity))[obstacle_index]=0.
        abd.copy_from(ag);world.retrieve()
        config['added_object_settling']=dict(seconds=settle_steps*dt,recorded=False,actor_held=True,velocity_zeroed_after_settling=True)
        save(out/'simulation_config.json',config)
    hold_actor['enabled']=False
    reset_body(np.asarray(p['body_direction'])*p['body_initial_speed'])
    # All clips deliberately start with empty lagged friction history.
    if fem is not None:fem.copy_to(fg);fem.copy_from(fg);world.retrieve()
    if fem is not None:fem.copy_to(fg);eq=np.asarray(fg.positions().view()).reshape(-1,3)[mapping].copy()
    else:eq=np.empty((0,3))
    recording['enabled']=True;sample_diagnostic()
    inv=np.linalg.inv(np.stack([sv[st[:,k]]-sv[st[:,0]] for k in [1,2,3]],axis=-1)) if len(st) else np.empty((0,3,3))
    sx=[];svs=[];cx=[];cvs=[];bt=[];bv=[];ot=[];ov=[];rows=[]
    for f in range(count):
        if fem is not None:fem.copy_to(fg);x=np.asarray(fg.positions().view()).reshape(-1,3)[mapping].copy();v=np.asarray(fg.vertices().find(builtin.velocity).view()).reshape(-1,3)[mapping].copy()
        else:x=np.empty((0,3));v=np.empty((0,3))
        if abd:abd.copy_to(ag)
        T=np.asarray(ag.instances().find(builtin.transform).view())[actor_index].copy() if body_present else initial.copy()
        V=np.asarray(ag.instances().find(builtin.velocity).view())[actor_index].copy() if body_present else np.zeros((4,4))
        OT=np.asarray(ag.instances().find(builtin.transform).view())[obstacle_index].copy() if obstacle_present else np.eye(4)
        OV=np.asarray(ag.instances().find(builtin.velocity).view())[obstacle_index].copy() if obstacle_present else np.zeros((4,4))
        if not np.isfinite(x).all():raise RuntimeError('Nonfinite FEM state')
        if f==0:
            np.savez_compressed(out/'initial_state.npz',solid_positions=x[None,:len(sv)],solid_velocities=v[None,:len(sv)],solid_rest_positions=sv,solid_tetrahedra=st,cloth_positions=x[None,len(sv):],cloth_velocities=v[None,len(sv):],cloth_rest_positions=cv,cloth_faces=cf,cloth_fixed_mask=fixed_c)
        J=np.linalg.det(np.stack([x[st[:,k]]-x[st[:,0]] for k in [1,2,3]],axis=-1)@inv) if len(st) else np.ones(1)
        if J.min()<=.02:
            save(out/'failure_report.json',dict(frame=f+1,min_J=float(J.min())));raise RuntimeError('Collapsed volume')
        shell=x[len(sv):];near=np.linalg.norm(shell[:,:2]-T[:2,3],axis=1)<(.12 if gym else .055)
        if gym:near&=cv[:,2]>.09
        dent=float(np.max(eq[len(sv):][near,2]-shell[near,2])) if near.any() else 0.
        rows.append(dict(frame_index=f+1,time_sec=f/fps,local_depression_m=dent,min_jacobian=float(J.min()),elastic_rms_speed_mps=float(np.sqrt(np.mean(v*v))*np.sqrt(3)) if len(v) else 0.,body_location=T[:3,3].tolist(),added_object_location=(OT[:3,3].tolist() if obstacle_present else None)))
        sx.append(x[:len(sv)]);svs.append(v[:len(sv)]);cx.append(shell);cvs.append(v[len(sv):]);bt.append(T);bv.append(V);ot.append(OT);ov.append(OV)
        if f%3==0:
            print('FRAME',f+1,'dent_mm',round(dent*1000,3),'corner_mm',round(diagnostics[-1][6]*1000,4),'elapsed',round(time.monotonic()-start,1),flush=True);save(out/'progress.json',dict(frame=f+1,total=count,elapsed_seconds=time.monotonic()-start,corner_displacement_m=diagnostics[-1][6],elastic_rms_speed_mps=rows[-1]['elastic_rms_speed_mps'],body_location=rows[-1]['body_location'],min_jacobian=rows[-1]['min_jacobian'],depression_m=dent))
        if f<count-1:
            for _ in range(stride):advance()
    kwargs=dict(solid_positions=np.asarray(sx),solid_velocities=np.asarray(svs),solid_rest_positions=sv,solid_tetrahedra=st,cloth_positions=np.asarray(cx),cloth_velocities=np.asarray(cvs),cloth_rest_positions=cv,cloth_faces=cf,cover_volume_vertex_ids=cover_ids,body_transforms=np.asarray(bt),body_velocities=np.asarray(bv),body_vertices=np.asarray(body_mesh.vertices),body_faces=np.asarray(body_mesh.faces),times=np.arange(count)/fps,path_obstacle_present=np.array([obstacle_present],dtype=np.int8),path_obstacle_vertices=(np.asarray(obstacle_mesh.vertices) if obstacle_mesh is not None else np.empty((0,3),np.float64)),path_obstacle_faces=(np.asarray(obstacle_mesh.faces,np.int32) if obstacle_mesh is not None else np.empty((0,3),np.int32)),obstacle_transforms=np.asarray(ot),obstacle_velocities=np.asarray(ov),path_obstacle_id=np.array([obstacle_id]))
    kwargs.update(solid_fixed_mask=fixed_s,cloth_fixed_mask=fixed_c)
    np.savez_compressed(out/'cache.npz',**kwargs)
    report=dict(status='complete',scene_id=a.scene,case=a.case,frames=rows,peak_frame=max(rows,key=lambda r:r['local_depression_m'])['frame_index'],peak_depression_m=max(r['local_depression_m'] for r in rows),wall_seconds=time.monotonic()-start,body_mass_kg=p['body_mass'] if body_present else 0.,solid_vertices=len(sv),shell_vertices=len(cv),solid_tetrahedra=len(st),manual_recorded_deformation=False,manual_recorded_motion=False,release_status=config['release_status'])
    report['viscous_stage']=visc_info
    data=np.asarray(diagnostics);np.savez_compressed(out/'substep_diagnostics.npz',data=data,columns=np.array(['time_s','body_x_m','body_y_m','body_z_m','body_min_z_m','local_depression_m','outer_corner_displacement_m']))
    report['substep_peak_depression_m']=float(data[:,5].max());report['max_outer_corner_displacement_m']=float(data[:,6].max());report['diagnostic_sample_dt_s']=dt
    save(out/'simulation_report.json',report);print('COMPLETE',a.scene,a.case,report['peak_depression_m'],flush=True)

if __name__=='__main__':main()
