"""Native BW woven shell + bending + IPC/ACCD + dynamic chair/book."""
from pathlib import Path
import argparse,importlib.metadata,os,shutil,socket,time
import numpy as np,trimesh
from scipy.spatial import cKDTree
import uipc
from uipc import builtin,view
from uipc.core import Engine,World,Scene,FiniteElementStateAccessorFeature,AffineBodyStateAccessorFeature
from uipc.geometry import trimesh as ipc_mesh,label_surface,ground
from uipc.constitution import (StrainLimitingBaraffWitkinShell,ElasticModuli2D,DiscreteShellBending,
    AffineBodyConstitution,SoftPositionConstraint,FiniteElementExternalForce)
from common import CASE,HERE,LAYOUT,save,sha,scarf,ASSETS
from edit_vocab import CASES,resolve

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',choices=list(CASES),default='source')
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--dt',type=float,default=1/480)
    ap.add_argument('--pitch',type=float,default=.006);ap.add_argument('--duration',type=float,default=LAYOUT['duration'])
    ap.add_argument('--initial-state',type=Path);ap.add_argument('--prepare',type=float,default=0.)
    ap.add_argument('--hand-pin',choices=['all','short_edge'],default='all')
    a=ap.parse_args();assert os.name!='nt'
    assert os.environ.get('CUDA_VISIBLE_DEVICES','').startswith('GPU-'),'Use the policy-gated launcher'
    if a.out.exists() and any(a.out.iterdir()):raise FileExistsError(a.out)
    out=a.out;out.mkdir(parents=True,exist_ok=True);p,edit=resolve(a.case)
    (out/'source_snapshot').mkdir()
    for source in HERE.glob('*.py'):shutil.copy2(source,out/'source_snapshot'/source.name)
    placed,faces,uv,rest,grid,length=scarf(a.pitch)
    initial=None
    if a.initial_state:
        initial=np.load(a.initial_state)
        if not np.array_equal(initial['faces'],faces)or not np.array_equal(initial['uv'],uv):raise RuntimeError('Prepared topology differs')
        placed=initial['positions'][0].copy()
    cfg=Scene.default_config();cfg['dt']=a.dt;cfg['gravity']=[[0.],[0.],[-9.81]]
    cfg['contact']['d_hat']=.0006;cfg['contact']['eps_velocity']=.0002
    cfg['contact']['adaptive']['min_kappa']=1e7;cfg['contact']['adaptive']['max_kappa']=1e12
    cfg['newton']['semi_implicit']['enable']=0;cfg['newton']['velocity_tol']=1e-4
    cfg['newton']['max_iter']=1000;cfg['line_search']['max_iter']=48
    cfg['linear_system']['fem_preconditioner']='mas';cfg['linear_system']['tol_rate']=1e-8
    scene=Scene(cfg);resistance=1e9;scene.contact_tabular().default_model(.45,resistance)
    default=scene.contact_tabular().default_element();cloth_contact=scene.contact_tabular().create('cotton')
    wood_contact=scene.contact_tabular().create('varnished_wood');floor_contact=scene.contact_tabular().create('floor');book_contact=scene.contact_tabular().create('clothbound_book')
    scene.contact_tabular().insert(cloth_contact,wood_contact,p['scarf_friction'],resistance)
    scene.contact_tabular().insert(cloth_contact,floor_contact,p['scarf_floor_friction'],resistance)
    scene.contact_tabular().insert(cloth_contact,book_contact,p['scarf_book_friction'],resistance)
    scene.contact_tabular().insert(cloth_contact,cloth_contact,p['scarf_self_friction'],resistance)
    rigid_order=[];rigid_geo={}
    def rigid(name,v,f,mass):
        mesh=trimesh.Trimesh(v,f,process=True);mesh.fix_normals()
        if not np.isfinite(mesh.volume)or mesh.volume<=0:raise ValueError('Invalid rigid volume '+name)
        v=np.asarray(mesh.vertices);f=np.asarray(mesh.faces,np.int32)
        m=ipc_mesh(v,f);label_surface(m);AffineBodyConstitution().apply_to(m,1e10,mass/mesh.volume)
        (wood_contact if name=='chair'else book_contact).apply_to(m);view(m.instances().find(builtin.is_fixed))[:]=0
        scene.objects().create(name).geometries().create(m);rigid_order.append(name)
        rigid_geo[name]=(v,f);np.savez_compressed(out/(name+'_geometry.npz'),vertices=v,faces=f)
    if p['chair_active'][0]:
        data=np.load(ASSETS/LAYOUT['chair_geometry_dir']/LAYOUT['chair_collision_file']);v=data['vertices'].copy();v[:,2]+=LAYOUT['chair_ground_clearance']
        rigid('chair',v,data['faces'],p['chair_mass'])
    if p['book_active'][0]:
        mesh=trimesh.creation.box(p['book_dimensions']);mesh.apply_translation(p['book_location'])
        rigid('landing_book',mesh.vertices,mesh.faces,p['book_mass'])
    floor_geometry=ground(0.,np.array([0.,0.,1.]));floor_contact.apply_to(floor_geometry)
    scene.objects().create('floor').geometries().create(floor_geometry)
    m=ipc_mesh(rest,faces);label_surface(m)
    E=p['scarf_young_modulus'];nu=p['scarf_poisson_ratio'];h=p['scarf_thickness']
    shear_input=E*h*.04
    StrainLimitingBaraffWitkinShell().apply_to(m,ElasticModuli2D.youngs_poisson(E,nu),
        ElasticModuli2D.youngs_poisson(shear_input,nu),mass_density=p['scarf_density'],thickness=h/2,strain_rate=100.)
    D=p['scarf_bending_reference_nm']*(E/p['scarf_modulus_reference_pa']);DiscreteShellBending().apply_to(m,D/2)
    SoftPositionConstraint().apply_to(m,1e6);FiniteElementExternalForce().apply_to(m,np.zeros(3));cloth_contact.apply_to(m)
    if m.vertices().find('external_force/is_constrained')is None:raise RuntimeError('Solver needs independent force and holding masks')
    if LAYOUT['release_time']==0 and a.prepare==0:view(m.vertices().find(builtin.is_constrained)).reshape(-1)[:]=0
    obj=scene.objects().create('scarf');obj.geometries().create(m)
    holding={'active':LAYOUT['release_time']>0};forces={'values':np.zeros_like(rest)}
    pin_mask=np.ones(len(uv),np.int32)if a.hand_pin=='all'else((uv[:,1]>.98)&(abs(uv[:,0]-.5)<.22)).astype(np.int32)
    def animate(info):
        g=info.geo_slots()[0].geometry()
        view(g.vertices().find(builtin.is_constrained)).reshape(-1)[:]=pin_mask if holding['active']else 0
        view(g.vertices().find('external_force/is_constrained')).reshape(-1)[:]=1
        view(g.vertices().find(builtin.aim_position)).reshape(-1,3)[:]=placed
        view(g.vertices().find('external_force')).reshape(-1,3)[:]=forces['values']
    scene.animator().insert(obj,animate)
    masses=np.asarray(m.vertices().find(builtin.volume).view()).reshape(-1)*p['scarf_density']
    config=dict(scene_id=CASE,case_id=a.case,physics=p,edit=edit,layout=LAYOUT,solver_config=cfg,
        solver='libuipc CUDA strain-limiting Baraff-Witkin shell + discrete bending + IPC/ACCD + dynamic ABD',
        dt=a.dt,pitch=a.pitch,duration=a.duration,fps=24,frames=round(a.duration*24),grid=grid,
        material_length_m=length,material_width_m=LAYOUT['width'],scarf_mass_kg=float(masses.sum()),
        thickness_full_m=h,bending_rigidity_nm=D,bending_native_coefficient_nm=D/2,
        membrane_stretch_E_pa=E,shear_input=shear_input,shear_coefficient_n_m=shear_input/(2*(1+nu)),
        material_calibrated=False,material_note='Effective woven shell: independently chosen 4 micro-Nm source bending, scaled with the declared elastic material edit; no measured product fit.',
        contact_friction_pairs={'cotton/wood':p['scarf_friction'],'cotton/floor':p['scarf_floor_friction'],'cotton/book':p['scarf_book_friction'],'cotton/cotton':p['scarf_self_friction']},
        initial_state_sha256=sha(a.initial_state)if a.initial_state else None,preparation_seconds=a.prepare,
        hold_model=a.hand_pin,pinned_vertices_before_release=int(pin_mask.sum())if LAYOUT['release_time']>0 or a.prepare>0 else 0,
        pins_after_release=0,hand_authored_recorded_motion=False,post_solve_deformation=False,self_collision=True,
        chair_dynamic=bool(p['chair_active'][0]),chair_fixed=False,
        air_force='Passive quadratic normal drag + 3 percent tangential drag; independent enabled force mask; no direct state damping.',
        solver_distribution_version=importlib.metadata.version('pyuipc'),external_force_activation_attribute='external_force/is_constrained',
        baseline_design_revision=LAYOUT['chair_revision'],collision_sha256=sha(ASSETS/LAYOUT['chair_geometry_dir']/LAYOUT['chair_collision_file']))
    save(out/'simulation_config.json',config)
    uipc.Logger.set_level(getattr(uipc.Logger,'Warn',None)or uipc.Logger.Level.Warn);start=time.monotonic();engine=Engine('cuda',str(out/'solver'));world=World(engine);world.init(scene)
    if not world.is_valid():raise RuntimeError('Invalid initial world')
    fem=world.features().find(FiniteElementStateAccessorFeature);fg=fem.create_geometry()
    for key,val in [(builtin.position,np.zeros(3)),(builtin.velocity,np.zeros(3))]:
        if fg.vertices().find(key)is None:fg.vertices().create(key,val)
    fem.copy_to(fg);dist,mapping=cKDTree(np.asarray(fg.positions().view()).reshape(-1,3)).query(rest)
    if dist.max()>1e-8 or len(np.unique(mapping))!=len(rest):raise RuntimeError('FEM mapping error')
    view(fg.positions()).reshape(-1,3)[mapping]=placed
    if initial is not None:view(fg.vertices().find(builtin.velocity)).reshape(-1,3)[mapping]=initial['velocities'][0]
    fem.copy_from(fg);world.retrieve()
    abd=world.features().find(AffineBodyStateAccessorFeature)if rigid_order else None
    ag=abd.create_geometry()if abd is not None else None
    if ag is not None:
        for key,val in [(builtin.transform,np.eye(4)),(builtin.velocity,np.zeros((4,4)))]:
            if ag.instances().find(key)is None:ag.instances().create(key,val)
    if initial is not None and abd is not None:
        abd.copy_to(ag);old_names=list(initial['rigid_names'])
        for i,name in enumerate(rigid_order):
            if name in old_names:
                j=old_names.index(name)
                view(ag.instances().find(builtin.transform)).reshape(-1,4,4)[i]=initial['rigid_transforms'][0,j]
                view(ag.instances().find(builtin.velocity)).reshape(-1,4,4)[i]=initial['rigid_velocities'][0,j]
        abd.copy_from(ag);world.retrieve()
    positions=[];velocities=[];allT=[];allRV=[];telemetry=[];air_energy=0.
    def read(t,record=False):
        nonlocal air_energy
        fem.copy_to(fg);x=np.asarray(fg.positions().view()).reshape(-1,3)[mapping].copy()
        v=np.asarray(fg.vertices().find(builtin.velocity).view()).reshape(-1,3)[mapping].copy()
        if abd is not None:
            abd.copy_to(ag);T=np.asarray(ag.instances().find(builtin.transform).view()).reshape(-1,4,4).copy()
            RV=np.asarray(ag.instances().find(builtin.velocity).view()).reshape(-1,4,4).copy()
        else:T=np.empty((0,4,4));RV=np.empty((0,4,4))
        if not np.isfinite(x).all()or not np.isfinite(T).all():raise RuntimeError('Nonfinite state')
        tri=x[faces];n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);area=np.linalg.norm(n,axis=1)/2
        vn=np.zeros_like(x);va=np.zeros(len(x))
        for k in range(3):np.add.at(vn,faces[:,k],n);np.add.at(va,faces[:,k],area/3)
        vn/=np.maximum(np.linalg.norm(vn,axis=1,keepdims=True),1e-20)
        s=(v*vn).sum(1);vt=v-s[:,None]*vn
        forces['values']=-.5*p['air_density']*p['air_drag_coefficient']*va[:,None]*(s[:,None]*abs(s[:,None])*vn+.03*np.linalg.norm(vt,axis=1)[:,None]*vt)
        power=float(np.sum(forces['values']*v));air_energy+=max(0.,-power)*a.dt
        if power>1e-12:raise RuntimeError('Air force adds energy')
        telemetry.append([t,x[:,2].min(),x[:,2].max(),np.linalg.norm(v,axis=1).max(),.5*np.sum(masses*np.sum(v*v,axis=1)),air_energy,int(pin_mask.sum())if holding['active']else 0])
        if record:positions.append(x);velocities.append(v);allT.append(T);allRV.append(RV)
        return x,v,T
    stride=round(1/(24*a.dt));assert abs(stride*a.dt-1/24)<1e-10
    read(-a.prepare)
    for k in range(round(a.prepare/a.dt)):
        world.advance()
        if not world.is_valid():raise RuntimeError('Invalid preparation step')
        world.retrieve();read(-a.prepare+(k+1)*a.dt)
    count=round(a.duration*24);read(0,True)
    for k in range(1,(count-1)*stride+1):
        t=k*a.dt;holding['active']=t<=LAYOUT['release_time']+1e-10
        world.advance()
        if not world.is_valid():raise RuntimeError('Native world failed')
        world.retrieve();read(t,k%stride==0)
        if k%stride==0 and k//stride%6==0:
            np.savez_compressed(out/'checkpoint.npz',positions=np.asarray(positions),faces=faces,uv=uv,
                rigid_transforms=np.asarray(allT),rigid_names=np.array(rigid_order),times=np.arange(len(positions))/24)
            print('FRAME',len(positions),'wall',round(time.monotonic()-start,2),flush=True)
    np.savez_compressed(out/'cache.npz',positions=np.asarray(positions),velocities=np.asarray(velocities),faces=faces,uv=uv,
        rest_positions=rest,vertex_masses=masses,rigid_transforms=np.asarray(allT),rigid_velocities=np.asarray(allRV),rigid_names=np.array(rigid_order),times=np.arange(count)/24)
    np.savez_compressed(out/'telemetry.npz',values=np.asarray(telemetry),columns=np.array(['time_s','min_z_m','max_z_m','max_speed_m_s','kinetic_j','air_dissipation_j','held_vertices']))
    save(out/'completion.json',dict(complete=True,worker_host=socket.gethostname(),gpu_uuid=os.environ['CUDA_VISIBLE_DEVICES'],
        frames=len(positions),runtime_seconds=time.monotonic()-start,cache_sha256=sha(out/'cache.npz'),uipc_path=uipc.__file__,native_scene_valid=world.is_valid()))
    print('COMPLETE',a.case,round(time.monotonic()-start,2),flush=True)
if __name__=='__main__':main()
