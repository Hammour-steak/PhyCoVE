"""Native CUDA IPC: woven thin shell, dynamic weighted figurine and optional cup.

All recorded motion is native integration. Assembly writes happen before the
preparation solve. No mesh filtering, deformation gain or tail freezing.

A timed case (vocab.TIMED, e.g. friction_x0_1_at_frame_8) continues the accepted source solve: --source-cache
names the source run (cache.npz, simulation_config.json); the scene is built with the edited parameters, the
exact source state of the edit frame k (curtain vertex positions and velocities, every rigid transform) is
written into the solver, and solving resumes at t=(k-1)/24. The cache does not record rigid-body velocities;
the vase rests on the desk (its recorded 24 Hz motion is below 3e-4 m/s), so its affine velocity restarts at
zero. cache.npz then holds source frames 1..k-1 followed by the continuation.
"""
from pathlib import Path
import argparse, json, os, shutil, socket, time
import numpy as np
from scipy.spatial import cKDTree
import trimesh
import uipc
from uipc import builtin,view
from uipc.core import Engine,World,Scene,FiniteElementStateAccessorFeature,AffineBodyStateAccessorFeature
from uipc.geometry import trimesh as ipc_trimesh,label_surface,ground
from uipc.constitution import (StrainLimitingBaraffWitkinShell,ElasticModuli2D,
    DiscreteShellBending,AffineBodyConstitution,SoftPositionConstraint,FiniteElementExternalForce)
from baseline import HERE,CASE,LAYOUT,FIGURE_ASSET,BASELINE_REVISION,curtain,figure_mesh,cup_mesh,save,sha
from vocab import resolve,CASES,TIMED
from cloth_dissipation import internal_force,air_force

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',choices=[*CASES,*TIMED],default='source')
    ap.add_argument('--source-cache',type=Path,help='timed cases: run folder of the accepted source solve (cache.npz, simulation_config.json)')
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--dt',type=float,default=1/240)
    ap.add_argument('--pitch',type=float,default=.009);ap.add_argument('--duration',type=float,default=4.)
    ap.add_argument('--prepare',type=float,default=.25);a=ap.parse_args()
    assert os.name!='nt'
    if a.out.exists()and any(a.out.iterdir()):raise FileExistsError(a.out)
    out=a.out;out.mkdir(parents=True,exist_ok=True);p,edit=resolve(a.case)
    timed=edit.get('timed');src=None
    if timed:
        if a.source_cache is None:raise SystemExit('A timed case needs --source-cache (the accepted source run)')
        source_cfg=json.loads((a.source_cache/'simulation_config.json').read_text())
        base,_=resolve('source')
        if source_cfg['case_id']!='source' or source_cfg['physics']!=base or source_cfg['dt']!=a.dt or source_cfg['pitch']!=a.pitch:
            raise RuntimeError('The source cache was not solved with the baseline parameters, dt and pitch')
        with np.load(a.source_cache/'cache.npz',allow_pickle=False) as z:src={key:z[key] for key in z.files}
        k_edit=int(timed['frame']);t_edit=(k_edit-1)/24
        if abs(src['times'][k_edit-1]-t_edit)>1e-12:raise RuntimeError('Source cache clock differs')
    placed,faces,uv=curtain(a.pitch)
    nx=len(np.unique(uv[:,0]));nz=len(np.unique(uv[:,1]))
    row=placed[::nz]
    arcs=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(row,axis=0),axis=1))]
    rest=placed.copy();rest[:,0]=np.repeat(arcs-arcs[-1]/2,nz);rest[:,1]=0.
    cfg=Scene.default_config();cfg['dt']=a.dt;cfg['gravity']=[[0.],[0.],[-9.81]]
    cfg['contact']['d_hat']=.0008;cfg['contact']['eps_velocity']=.0005
    cfg['contact']['adaptive']['kappa_eval_scale']=1.
    cfg['contact']['adaptive']['min_kappa']=1e7;cfg['contact']['adaptive']['max_kappa']=1e12
    cfg['newton']['semi_implicit']['enable']=0;cfg['newton']['velocity_tol']=1e-4
    cfg['newton']['max_iter']=1500;cfg['line_search']['max_iter']=48
    cfg['linear_system']['fem_preconditioner']='mas';cfg['linear_system']['tol_rate']=1e-8
    scene=Scene(cfg);resistance=1e9;scene.contact_tabular().default_model(.45,resistance)
    default=scene.contact_tabular().default_element();cloth_contact=scene.contact_tabular().create('linen_contact')
    scene.contact_tabular().insert(cloth_contact,default,p['cloth_friction'],resistance)
    scene.contact_tabular().insert(cloth_contact,cloth_contact,p['cloth_friction'],resistance)
    rigid_meshes={};rigid_order=[];rigid_slots={}
    def rigid(name,mesh,mass=None,T=None):
        m=ipc_trimesh(np.asarray(mesh.vertices),np.asarray(mesh.faces,np.int32));label_surface(m)
        AffineBodyConstitution().apply_to(m,1e9,(mass/mesh.volume)if mass else 1000.)
        default.apply_to(m);view(m.instances().find(builtin.is_fixed))[:]=0 if mass else 1
        transform=np.eye(4)if T is None else T;view(m.transforms())[:]=transform
        slot,_=scene.objects().create(name).geometries().create(m)
        rigid_meshes[name]=(np.asarray(mesh.vertices),np.asarray(mesh.faces,np.int32),transform)
        rigid_order.append(name);rigid_slots[name]=slot
    table=trimesh.creation.box(LAYOUT['table_dimensions']);table.apply_translation(LAYOUT['table_center']);rigid('desk',table)
    pane=trimesh.creation.box([1.21,.016,1.10]);pane.apply_translation([0.,.305,.65]);rigid('window',pane)
    sill=trimesh.creation.box([1.40,.23,.036]);sill.apply_translation([0.,.227,.081]);rigid('window_sill',sill)
    note=trimesh.creation.box([.24,.16,.024]);note.apply_translation([-.405,-.225,.014]);rigid('notebook',note)
    holder=trimesh.creation.cylinder(radius=.043,height=.18,sections=48);holder.apply_translation(np.asarray(LAYOUT['pen_holder_location'])+[0.,0.,.09]);rigid('pen_holder',holder)
    scene.objects().create('room_floor').geometries().create(ground(-.76,np.array([0.,0.,1.])))
    if p['figure_active'][0]:
        T=np.eye(4);T[:3,3]=p['figure_location'];rigid('figurine',figure_mesh(),p['figure_mass'],T)
    if p['cup_active'][0]:
        T=np.eye(4);T[:3,3]=p['cup_location'];rigid('ceramic_cup',cup_mesh(),p['cup_mass'],T)
    m=ipc_trimesh(rest,faces);label_surface(m)
    h=p['cloth_thickness'];E=p['cloth_young_modulus'];nu=p['cloth_poisson_ratio']
    # The pinned native BW kernel multiplies stretch by full h but NOT shear.
    # Supply E_shear = E*h*0.04 to obtain G_2D = E*h*0.04/[2(1+nu)].
    shear_input=E*h*.04
    StrainLimitingBaraffWitkinShell().apply_to(m,
        ElasticModuli2D.youngs_poisson(E,nu),ElasticModuli2D.youngs_poisson(shear_input,nu),
        mass_density=p['cloth_density'],thickness=h/2,strain_rate=100.)
    # Raw overload uses coefficient kappa = D/2 (energy has no extra 1/2).
    D=E*h**3/(12*(1-nu**2));DiscreteShellBending().apply_to(m,D/2)
    SoftPositionConstraint().apply_to(m,1e6)
    FiniteElementExternalForce().apply_to(m,np.zeros(3),enable=True)
    force_mask=m.vertices().find('external_force/is_constrained')
    assert force_mask is not None and np.asarray(force_mask.view()).all(), 'Independent force activation mask required'
    cloth_contact.apply_to(m)
    pinned=uv[:,1]>.999999;holding={'active':True};forces={'values':np.zeros_like(rest)}
    obj=scene.objects().create('curtain');slot,_=obj.geometries().create(m)
    def animate(info):
        geo=info.geo_slots()[0].geometry()
        view(geo.vertices().find(builtin.is_constrained)).reshape(-1)[:]=pinned.astype(np.int32)if holding['active']else 0
        view(geo.vertices().find(builtin.aim_position)).reshape(-1,3)[:]=placed
        view(geo.vertices().find('external_force')).reshape(-1,3)[:]=forces['values']
    scene.animator().insert(obj,animate)
    mass=np.asarray(m.vertices().find(builtin.volume).view()).reshape(-1)*p['cloth_density']
    for name,(v,f,T)in rigid_meshes.items():np.savez_compressed(out/(name+'_geometry.npz'),vertices=v,faces=f,initial_transform=T)
    config=dict(scene_id=CASE,case_id=a.case,edit=edit,physics=p,layout=LAYOUT,dt=a.dt,pitch=a.pitch,
        timed_continuation=dict(edit_frame=k_edit,start_time_s=t_edit,source_cache=str(a.source_cache/'cache.npz'),source_cache_sha256=sha(a.source_cache/'cache.npz'),
            frames_from_source=[1,k_edit-1],frames_solved=[k_edit,96],physics_before_edit=resolve('source')[0])if timed else None,
        frames=round(a.duration*24),fps=24,release_time=0.,preparation_seconds=a.prepare,
        solver='libuipc CUDA Baraff-Witkin membrane + discrete shell bending + IPC/ACCD + affine rigid bodies',
        solver_config=cfg,cloth_mass_kg=float(mass.sum()),cloth_material_width_m=float(arcs[-1]),
        cloth_initial_projected_width_m=LAYOUT['cloth_width'],cloth_node_count=len(rest),cloth_triangles=len(faces),
        stretch_E_pa=E,shear_input=shear_input,shear_coefficient_n_m=shear_input/(2*(1+nu)),
        flexural_rigidity_nm=D,native_bending_energy_coefficient_nm=D/2,
        figure_is_dynamic=bool(p['figure_active'][0]),figure_is_glued=False,
        air_drag='Passive linear-plus-quadratic normal and tangential force, with positive implicit predictor.',
        deformation_damping='Momentum-preserving mass-projected internal force; constant rate in s^-1; no state overwrite or output filtering.',
        independent_external_force_mask=True,solver_package_version='0.0.29',self_collision=True,cloth_fixed_vertices_after_release=0,hand_authored_recorded_motion=False,
        material_calibration='Effective woven shell, supported areal-weight range; no product-specific tensile, bending, friction or drop-test fit.')
    config.update(baseline_revision=BASELINE_REVISION,figure_collision_sha256=sha(FIGURE_ASSET/'collision.npz'),
        figure_preparation_sha256=sha(FIGURE_ASSET/'preparation.json'),figure_object='porcelain vase (hollow scanned surface of revolution)',
        figure_source='https://polyhaven.com/a/antique_ceramic_vase_01',figure_source_license='CC0')
    save(out/'simulation_config.json',config)
    uipc.Logger.set_level(uipc.Logger.Warn);start=time.monotonic();engine=Engine('cuda',str(out/'solver'));world=World(engine)
    world.init(scene)
    if not world.is_valid():raise RuntimeError('Invalid native initial scene')
    fem=world.features().find(FiniteElementStateAccessorFeature);fg=fem.create_geometry()
    for key,value in [(builtin.position,np.zeros(3)),(builtin.velocity,np.zeros(3))]:
        if fg.vertices().find(key)is None:fg.vertices().create(key,value)
    fem.copy_to(fg);dist,mapping=cKDTree(np.asarray(fg.positions().view()).reshape(-1,3)).query(rest)
    if dist.max()>1e-8 or len(np.unique(mapping))!=len(rest):raise RuntimeError('FEM topology mapping failed')
    # Common assembly only. Flat, unstrained reference -> gathered vertical sheet.
    view(fg.positions()).reshape(-1,3)[mapping]=placed;fem.copy_from(fg);world.retrieve()
    abd=world.features().find(AffineBodyStateAccessorFeature);ag=abd.create_geometry()
    for key,value in [(builtin.transform,np.eye(4)),(builtin.velocity,np.zeros((4,4)))]:
        if ag.instances().find(key)is None:ag.instances().create(key,value)
    # Native affine ordering is geometry creation order, including static bodies.
    abd.copy_to(ag)
    transforms=np.asarray(ag.instances().find(builtin.transform).view()).reshape(-1,4,4)
    if len(transforms)!=len(rigid_order):raise RuntimeError('Unexpected ABD ordering')
    positions=[];velocities=[];transforms_all=[];telemetry=[];energy_air=0.;energy_internal=0.;max_internal_force=0.;max_internal_torque=0.
    def read_state(t,record=False):
        nonlocal energy_air,energy_internal,max_internal_force,max_internal_torque
        fem.copy_to(fg);x=np.asarray(fg.positions().view()).reshape(-1,3)[mapping].copy()
        v=np.asarray(fg.vertices().find(builtin.velocity).view()).reshape(-1,3)[mapping].copy()
        abd.copy_to(ag);T=np.asarray(ag.instances().find(builtin.transform).view()).reshape(-1,4,4).copy()
        tri=x[faces];normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);areas=np.linalg.norm(normal,axis=1)/2
        vn=np.zeros_like(x);vertex_area=np.zeros(len(x))
        for k in range(3):np.add.at(vn,faces[:,k],normal);np.add.at(vertex_area,faces[:,k],areas/3)
        vn/=np.maximum(np.linalg.norm(vn,axis=1,keepdims=True),1e-20)
        speed=(v*vn).sum(1);tangent=v-speed[:,None]*vn
        aerodynamic=air_force(v,vn,vertex_area,mass,p,a.dt)
        dissipative,diagnostic=internal_force(x,v,mass,p['cloth_deformation_damping_s_inv'],a.dt)
        forces['values']=aerodynamic+dissipative
        power=float(np.sum(aerodynamic*v));energy_air+=max(0.,-power)*a.dt
        energy_internal+=max(0.,-diagnostic['power_w'])*a.dt
        max_internal_force=max(max_internal_force,diagnostic['resultant_force_n'])
        max_internal_torque=max(max_internal_torque,diagnostic['resultant_torque_nm'])
        if record:
            positions.append(x);velocities.append(v);transforms_all.append(T)
        kinetic=float(.5*np.sum(mass*np.sum(v*v,axis=1)))
        telemetry.append([t,float(x[:,2].min()),float(x[:,2].max()),float(np.max(np.linalg.norm(v,axis=1))),kinetic,energy_air,energy_internal])
        if not np.all(np.isfinite(x)):raise RuntimeError('Nonfinite state')
        return x,v,T
    def step(t,record=False):
        world.advance()
        if not world.is_valid():raise RuntimeError('IPC world invalid')
        world.retrieve();return read_state(t,record)
    count=round(a.duration*24);stride=round(1/(24*a.dt));handoff=None
    if abs(stride*a.dt-1/24)>1e-10:raise ValueError('dt must divide rendered time')
    if timed:
        # Exact source state of frame k: curtain vertex positions/velocities and every rigid transform.
        holding['active']=False;release=-1.;start_t=t_edit;first=k_edit-1
        fem.copy_to(fg)
        view(fg.positions()).reshape(-1,3)[mapping]=src['positions'][first]
        view(fg.vertices().find(builtin.velocity)).reshape(-1,3)[mapping]=src['velocities'][first]
        fem.copy_from(fg)
        if list(src['rigid_names'])!=rigid_order:raise RuntimeError('Rigid body order differs from the source cache')
        abd.copy_to(ag)
        view(ag.instances().find(builtin.transform)).reshape(-1,4,4)[:]=src['rigid_transforms'][first]
        view(ag.instances().find(builtin.velocity)).reshape(-1,4,4)[:]=0.
        abd.copy_from(ag);world.retrieve()
        x0,v0,T0=read_state(start_t,True)
        handoff={'positions':float(np.abs(x0-src['positions'][first]).max()),'velocities':float(np.abs(v0-src['velocities'][first]).max()),
                 'rigid_transforms':float(np.abs(T0-src['rigid_transforms'][first]).max())}
        if max(handoff.values())>=1e-8:raise RuntimeError(f'Source state was not restored exactly: {handoff}')
        save(out/'state_handoff.json',dict(edit_frame=k_edit,time_s=start_t,parameters_after_edit=timed['params'],max_abs_error=handoff,
            rigid_velocity='not recorded in the source cache; restarted at zero (the vase rests on the desk)',verified=True))
        steps=(count-k_edit)*stride
    else:
        read_state(-a.prepare)
        for k in range(round(a.prepare/a.dt)):step(-a.prepare+(k+1)*a.dt)
        holding['active']=False
        fem.copy_to(fg)
        view(fg.vertices().find(builtin.velocity)).reshape(-1,3)[mapping]=np.asarray(p['cloth_initial_velocity_m_s'])
        fem.copy_from(fg);world.retrieve()
        release=0.;start_t=0.;first=0
        read_state(0.,True)
        steps=(count-1)*stride
    for k in range(1,steps+1):
        t=start_t+k*a.dt;holding['active']=t<=release+1e-10
        step(t,k%stride==0)
        if k%stride==0 and(k//stride)%4==0:
            np.savez_compressed(out/'checkpoint.npz',positions=np.asarray(positions),faces=faces,uv=uv,
                rigid_transforms=np.asarray(transforms_all),rigid_names=np.array(rigid_order),times=(first+np.arange(len(positions)))/24)
            print('FRAME',len(positions),'t',round(t,4),'wall',round(time.monotonic()-start,1),flush=True)
    positions,velocities,transforms_all=np.asarray(positions),np.asarray(velocities),np.asarray(transforms_all)
    extra={}
    if timed:
        np.savez_compressed(out/'continuation.npz',positions=positions,velocities=velocities,rigid_transforms=transforms_all,times=(first+np.arange(len(positions)))/24)
        positions=np.concatenate([src['positions'][:first],positions]);velocities=np.concatenate([src['velocities'][:first],velocities])
        transforms_all=np.concatenate([src['rigid_transforms'][:first],transforms_all])
        for key,value in (('positions',positions),('velocities',velocities),('rigid_transforms',transforms_all)):
            if len(value)!=count or not np.array_equal(value[:first],src[key][:first]):raise RuntimeError('Merged cache differs from the source before the edit frame')
        extra=dict(timed_edit_frame=np.array(k_edit))
    np.savez_compressed(out/'cache.npz',positions=positions,velocities=velocities,
        faces=faces,uv=uv,rest_positions=rest,vertex_masses=mass,
        rigid_transforms=transforms_all,rigid_names=np.array(rigid_order),times=np.arange(count)/24,**extra)
    np.savez_compressed(out/'telemetry.npz',values=np.asarray(telemetry),columns=np.array([
        'time_s','min_cloth_z_m','max_cloth_z_m','max_speed_m_s','cloth_kinetic_energy_j','air_dissipation_j','internal_dissipation_j']))
    save(out/'completion.json',dict(complete=True,worker_host=socket.gethostname(),gpu_uuid=os.environ.get('CUDA_VISIBLE_DEVICES'),
        duration_s=a.duration,frames=len(positions),runtime_seconds=time.monotonic()-start,cache_sha256=sha(out/'cache.npz'),state_handoff=handoff,
        dissipation_model='momentum-preserving internal + viscous aerodynamic forces',max_internal_resultant_force_n=max_internal_force,max_internal_resultant_torque_nm=max_internal_torque,internal_dissipation_j=energy_internal,air_dissipation_j=energy_air,uipc_path=uipc.__file__,numpy_version=np.__version__,native_scene_valid=world.is_valid()))
    print('COMPLETE',a.case,round(time.monotonic()-start,2),flush=True)

if __name__=='__main__':main()
