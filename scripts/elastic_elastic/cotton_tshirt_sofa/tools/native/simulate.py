"""Native coupled cloth/FEM/IPC. Recorded motion is never authored or filtered.

A timed case (edit_vocab.TIMED, e.g. low_friction_at_frame_10) continues the accepted source solve: --source-cache
names the source deformation.npz (shutter_positions.npz beside it). The scene is built with the edited
parameters, the source state of the edit frame k (shirt and seat FEM vertex positions and velocities, as stored
in float32 by the cache) is written into the solver and solving resumes at t=(k-1)/24. simulation.npz and
shutter_positions.npz hold the source samples before frame k followed by the continuation.
"""

from pathlib import Path
import argparse,os,socket,sys,time,shutil
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import CASE,HERE,ROOT,save,sha,GEOMETRY

from edit_vocab import SPEC,SPEC_PATH,CASE_DSL,TIMED,parameters,timed_schedule
import uipc
if uipc.__version__!='0.0.28':raise RuntimeError('This cohort requires the original libuipc 0.0.28 material implementation')
from uipc import view,builtin
from uipc.core import Engine,Scene,World,FiniteElementStateAccessorFeature
from uipc.geometry import trimesh as ipc_trimesh,tetmesh,label_surface,ground
from uipc.constitution import (StableNeoHookean,ElasticModuli,StrainLimitingBaraffWitkinShell,
    ElasticModuli2D,DiscreteShellBending,AffineBodyConstitution,FiniteElementExternalForce)

def placed_shirt(rest):
    layout=SPEC['layout'];x=rest.copy();x-= (x.min(0)+x.max(0))/2
    a=np.deg2rad(layout['shirt_rotation_x_degrees']);b=np.deg2rad(layout['shirt_rotation_z_degrees'])
    rx=np.array([[1,0,0],[0,np.cos(a),-np.sin(a)],[0,np.sin(a),np.cos(a)]])
    rz=np.array([[np.cos(b),-np.sin(b),0],[np.sin(b),np.cos(b),0],[0,0,1]])
    x=x@(rz@rx).T;x[:,:2]+=layout['shirt_xy_center_m'];x[:,2]+=layout['shirt_lowest_z_m']-x[:,2].min()
    return x

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',choices=[*CASE_DSL,*TIMED],default='source')
    ap.add_argument('--source-cache',type=Path,help='timed cases: deformation.npz of the accepted source (shutter_positions.npz beside it)')
    ap.add_argument('--name',required=True);ap.add_argument('--out',type=Path);ap.add_argument('--duration',type=float,default=4.)
    ap.add_argument('--prepare-release',action='store_true');ap.add_argument('--dt',type=float,default=None);ap.add_argument('--settle-only',action='store_true')
    ap.add_argument('--velocity-tol',type=float,default=.0005);ap.add_argument('--linear-tol',type=float,default=1e-4);ap.add_argument('--max-iter',type=int,default=1800)
    ap.add_argument('--profile-after',type=float)
    a=ap.parse_args();assert os.name!='nt' and sys.platform=='linux'
    if a.dt is None:a.dt=1/240
    out=a.out if a.out else ROOT/'renders'/CASE/'outputs'/a.name
    if out.exists()and any(out.iterdir()):raise FileExistsError(out)
    out.mkdir(parents=True,exist_ok=True);p=parameters(a.case)
    timed=timed_schedule(a.case)if a.case in TIMED else None;src=None;src_shutter=None
    if timed:
        if a.source_cache is None or a.prepare_release or a.settle_only:raise SystemExit('A timed case needs --source-cache and a normal solve')
        with np.load(a.source_cache,allow_pickle=False)as z:src={k:z[k]for k in z.files}
        with np.load(a.source_cache.parent/'shutter_positions.npz',allow_pickle=False)as z:src_shutter={k:z[k]for k in z.files}
        if str(src_shutter['native_cache_sha256'])!=sha(a.source_cache):raise RuntimeError('Source exposure sidecar belongs to another cache')
        k_edit=int(timed[0]['frame'])
        if abs(src['times'][k_edit-1]-(k_edit-1)/SPEC['fps'])>1e-9:raise RuntimeError('Source cache clock differs')
    cfg=Scene.default_config();cfg['dt']=a.dt;cfg['gravity']=[[0.],[0.],[-9.81]]
    cfg['contact']['d_hat']=.0004;cfg['contact']['eps_velocity']=.00025
    cfg['contact']['adaptive'].update(kappa_eval_scale=1.,min_kappa=1e7,max_kappa=1e12)
    cfg['newton']['semi_implicit']['enable']=0;cfg['newton']['velocity_tol']=a.velocity_tol
    cfg['newton']['max_iter']=a.max_iter;cfg['line_search']['max_iter']=32
    cfg['linear_system']['fem_preconditioner']='mas';cfg['linear_system']['tol_rate']=a.linear_tol
    scene=Scene(cfg);resistance=1e9;table=scene.contact_tabular();table.default_model(.5,resistance)
    default=table.default_element();cloth_contact=table.create('cotton');seat_contact=table.create('attached_foam');pillow_contact=table.create('loose_pillow')
    table.insert(cloth_contact,default,p['shirt_friction'],resistance)
    table.insert(cloth_contact,seat_contact,p['shirt_friction'],resistance)
    table.insert(cloth_contact,pillow_contact,p['shirt_friction'],resistance)
    table.insert(cloth_contact,cloth_contact,p['shirt_friction'],resistance)
    # The original seat overlaps its glued upholstered deck by a few mm.
    # Its bottom FE boundary is attached; do not add contradictory contact
    # between that attached volume and the static deck/back assembly.
    table.insert(seat_contact,default,.5,resistance,False)
    static=np.load(GEOMETRY/'static_surface.npz')
    staticmesh=ipc_trimesh(static['vertices'],static['faces']);label_surface(staticmesh)
    AffineBodyConstitution().apply_to(staticmesh,1e9,600.)
    view(staticmesh.instances().find(builtin.is_fixed))[:]=1;default.apply_to(staticmesh)
    scene.objects().create('sofa_frame_and_left_seat').geometries().create(staticmesh)
    parts={};geos={};tets={};seed={};surfaces={}
    def volume(name,E,nu,rho,contact,fixed=False):
        d=np.load(GEOMETRY/(name+'_volume.npz'));v=d['vertices'];T=d['tets']
        m=tetmesh(v,T);label_surface(m);StableNeoHookean().apply_to(m,ElasticModuli.youngs_poisson(E,nu),rho);contact.apply_to(m)
        if fixed:view(m.vertices().find(builtin.is_fixed)).reshape(-1)[:]=(v[:,2]<v[:,2].min()+.018).astype(np.int32)
        scene.objects().create(name).geometries().create(m);parts[name]=v;geos[name]=m;tets[name]=T
        surfaces[name]=(d['surface_vertices'],d['surface_faces']);seed[name]=v.copy()
    if p['seat_present'][0]and not a.prepare_release:volume('seat',p['seat_young_pa'],p['seat_poisson_ratio'],p['seat_density_kg_m3'],seat_contact,True)
    if p['pillow_present'][0]and not a.settle_only and not a.prepare_release:volume('pillow',p['pillow_young_pa'],.25,p['pillow_density_kg_m3'],pillow_contact)
    if not a.settle_only:
        d=np.load(GEOMETRY/'shirt_shell.npz');faces=d['faces'];placed=placed_shirt(d['vertices'])
        
        if a.prepare_release:placed[:,2]+=1.5
        m=ipc_trimesh(placed,faces);label_surface(m)
        E=p['shirt_stretch_young_pa'];nu=p['shirt_poisson_ratio'];h=p['shirt_thickness_m']
        # Pinned 0.0.28 kernel: shear input has no full-thickness multiplier.
        shear_input=2*(1+nu)*p['shirt_shear_n_m']
        StrainLimitingBaraffWitkinShell().apply_to(m,ElasticModuli2D.youngs_poisson(E,nu),ElasticModuli2D.youngs_poisson(shear_input,nu),mass_density=p['shirt_density_kg_m3'],thickness=h/2,strain_rate=100.)
        DiscreteShellBending().apply_to(m,p['shirt_bending_rigidity_nm']/2)
        FiniteElementExternalForce().apply_to(m,np.zeros(3));cloth_contact.apply_to(m)
        if a.prepare_release:
            r=d['vertices'];pins=((r[:,0]-.15)**2+(r[:,2]-.62)**2<.010**2)|((r[:,0]+.15)**2+(r[:,2]-.62)**2<.010**2)
            if m.vertices().find(builtin.is_fixed)is None:m.vertices().create(builtin.is_fixed,0)
            view(m.vertices().find(builtin.is_fixed)).reshape(-1)[:]=pins.astype(np.int32)
            save(out/'preparation_grips.json',dict(nodes=np.flatnonzero(pins).tolist(),rule='Two 10 mm shoulder pinches, stationary throughout preparation; no pins after release'))
        obj=scene.objects().create('shirt');obj.geometries().create(m)
        parts['shirt']=placed;geos['shirt']=m;seed['shirt']=placed.copy()
        forces={'value':np.zeros_like(placed)}
        def animate(info):
            view(info.geo_slots()[0].geometry().vertices().find('external_force')).reshape(-1,3)[:]=forces['value']
        scene.animator().insert(obj,animate)
    masses={name:np.asarray(m.vertices().find(builtin.volume).view()).reshape(-1)* (p['shirt_density_kg_m3']if name=='shirt'else p[name+'_density_kg_m3'])for name,m in geos.items()}
    rug=ground(.0125,np.array([0.,0.,1.]));default.apply_to(rug)
    scene.objects().create('receiving_rug_support').geometries().create(rug)
    save(out/'simulation_config.json',dict(scene_id=CASE,case_id=a.case,physics=p,layout=SPEC['layout'],dt=a.dt,
        timed_continuation=dict(edit_frame=k_edit,start_time_s=(k_edit-1)/SPEC['fps'],source_cache=str(a.source_cache),source_cache_sha256=sha(a.source_cache),
            frames_from_source=[1,k_edit-1],frames_solved=[k_edit,96],physics_before_edit=parameters('source'),timed_edits=timed,
            restored_state='shirt and seat FEM vertex positions and velocities of the source sample (stored as float32 by the cache)')if timed else None,fps=SPEC['fps'],duration_s=a.duration,settle_only=a.settle_only,solver_config=cfg,
        solver='libuipc 0.0.28 CUDA: Baraff-Witkin membrane + discrete shell bending + Stable Neo-Hookean volume + IPC/ACCD',
        self_collision=True,contact_two_way=True,material_modulus_mapping='E_membrane=E; G_2D=c_shear*E*h/(2*(1+nu)); B=c_bend*E*h^3/(12*(1-nu^2)); c_shear and c_bend fixed across every edit',cloth_areal_density_kg_m2=p['shirt_density_kg_m3']*p['shirt_thickness_m'],
        masses_kg={n:float(m.sum())for n,m in masses.items()},material_calibration=SPEC['material_status'],
        cloth_pins_after_release=0,preparation_only=a.prepare_release,hand_authored_motion=False,air_force='Explicit passive normal quadratic drag plus 2% tangential skin drag; no motion filtering or state damping.',
        seat_support='Bottom 18 mm attached to the original deck; seat/static attachment pair excluded from contact. Other participant pairs remain active.',
        receiving_support={'height_m':.0125,'model':'rigid rug support plane','visible_rug_xy_bounds_m':[[-1.315,-1.52],[1.415,.08]],'scope':'Check that all actual floor contacts lie within the visible rug footprint.'}))
    uipc.Logger.set_level(uipc.Logger.Warn)
    start=time.monotonic();engine=Engine('cuda',str(out/'solver'));world=World(engine);world.init(scene)
    if not world.is_valid():raise RuntimeError('Invalid scene at initialization')
    accessor=world.features().find(FiniteElementStateAccessorFeature);state=accessor.create_geometry()
    for key,value in [(builtin.position,np.zeros(3)),(builtin.velocity,np.zeros(3))]:
        if state.vertices().find(key)is None:state.vertices().create(key,value)
    accessor.copy_to(state);positions0=np.asarray(state.positions().view()).reshape(-1,3)
    mapping={}
    for name,rest in parts.items():
        distances,idx=cKDTree(positions0).query(rest)
        if distances.max()>1e-7 or len(np.unique(idx))!=len(rest):raise RuntimeError('FEM mapping failed '+name)
        mapping[name]=idx
    equilibrium=GEOMETRY/'seat_equilibrium.npz'
    if not a.settle_only and 'seat'in parts:
        prepared=np.load(equilibrium)
        view(state.positions()).reshape(-1,3)[mapping['seat']]=prepared['positions']
        seed['seat']=prepared['positions'].copy()
        view(state.vertices().find(builtin.velocity)).reshape(-1,3)[mapping['seat']]=prepared['velocities']
        accessor.copy_from(state);world.retrieve()
    prepared_release=GEOMETRY/'prepared_release.npz'
    if not a.prepare_release and not a.settle_only:
        pr=np.load(prepared_release)
        view(state.positions()).reshape(-1,3)[mapping['shirt']]=pr['positions']
        view(state.vertices().find(builtin.velocity)).reshape(-1,3)[mapping['shirt']]=pr['velocities']
        accessor.copy_from(state);world.retrieve()
        save(out/'initial_state.json',dict(prepared_release_sha256=sha(prepared_release),gravity_preparation_used=True,cloth_pins_after_release=0))
    for name,v in parts.items():
        np.savez_compressed(out/(name+'_rest.npz'),vertices=v,tets=tets.get(name,np.zeros((0,4),np.int32)),faces=faces if name=='shirt'else surfaces[name][1])
    xhistory={n:[]for n in parts};vh={n:[]for n in parts};telemetry=[];air_dissipation=0.
    def read(t,record):
        nonlocal air_dissipation
        accessor.copy_to(state);xall=np.asarray(state.positions().view()).reshape(-1,3);vall=np.asarray(state.vertices().find(builtin.velocity).view()).reshape(-1,3)
        row={'time_s':t}
        for name,idx in mapping.items():
            x=xall[idx].copy();v=vall[idx].copy()
            if not np.isfinite(x).all()or not np.isfinite(v).all():raise RuntimeError('Nonfinite state')
            if record:xhistory[name].append(x);vh[name].append(v)
            row[name+'_max_speed_m_s']=float(np.linalg.norm(v,axis=1).max())
            row[name+'_com_m']=np.average(x,weights=masses[name],axis=0).tolist()
            if name in tets:
                T=tets[name];r=parts[name];det=np.linalg.det(np.stack([x[T[:,k]]-x[T[:,0]]for k in [1,2,3]],2))/np.linalg.det(np.stack([r[T[:,k]]-r[T[:,0]]for k in [1,2,3]],2))
                row[name+'_min_det_F']=float(det.min());row[name+'_inverted_tets']=int(np.sum(det<=0))
                row[name+'_max_down_m']=float(np.max(seed[name][:,2]-x[:,2]))
            if name=='shirt':
                tri=x[faces];normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);area=np.linalg.norm(normal,axis=1)/2
                n=np.zeros_like(x);va=np.zeros(len(x))
                for k in range(3):np.add.at(n,faces[:,k],normal);np.add.at(va,faces[:,k],area/3)
                n/=np.maximum(np.linalg.norm(n,axis=1,keepdims=True),1e-20);vn=np.sum(n*v,axis=1);vt=v-vn[:,None]*n
                forces['value']=-.5*p['air_density_kg_m3']*p['air_drag_coefficient']*va[:,None]*(vn[:,None]*np.abs(vn[:,None])*n+.02*np.linalg.norm(vt,axis=1)[:,None]*vt)
                power=float(np.sum(forces['value']*v))
                if power>1e-10:raise RuntimeError('Air injected energy')
                air_dissipation+=max(0,-power)*a.dt
                row['shirt_min_z_m']=float(x[:,2].min());row['shirt_air_dissipation_j']=air_dissipation
        telemetry.append(row)
        return xall,vall
    fps=SPEC['fps'];stride=round(1/fps/a.dt)
    if abs(stride*a.dt-1/fps)>1e-10:raise ValueError('dt must divide video period')
    count=round(a.duration*fps) if not a.prepare_release else round(a.duration*fps)+1
    # A real 1/60 s exposure starts at each canonical frame time. Retain three
    # actual solver states, including the midpoint, for deforming motion blur.
    # These sidecar states do not add video/GT frames or change physical speed.
    exposure=not a.prepare_release and not a.settle_only
    half=round((1/120)/a.dt)
    if exposure and(abs(half*a.dt-1/120)>1e-10 or 2*half>=stride):raise ValueError('dt must divide the camera exposure midpoint')
    shutter={n:[]for n in parts};shutter_times=[]
    def capture(step,xall):
        if exposure and step%stride in [0,half,2*half]and step//stride<count:
            shutter_times.append(step*a.dt)
            for n,idx in mapping.items():shutter[n].append(xall[idx].astype(np.float32,copy=True))
    first_step=0;handoff=None
    if timed:
        # Exact source state of frame k (as stored by the cache) for every FEM body; the sofa frame is fixed.
        i=k_edit-1;first_step=i*stride
        accessor.copy_to(state)
        for name,idx in mapping.items():
            view(state.positions()).reshape(-1,3)[idx]=src[name+'_positions'][i].astype(np.float64)
            view(state.vertices().find(builtin.velocity)).reshape(-1,3)[idx]=src[name+'_velocities'][i].astype(np.float64)
        accessor.copy_from(state);world.retrieve()
    xall,_=read(first_step*a.dt,True);capture(first_step,xall)
    if timed:
        handoff={f'{n}_{q}':float(np.abs(np.asarray(h[0],dtype=np.float64)-src[f'{n}_{q}'][k_edit-1]).max())for n in mapping for q,h in(('positions',xhistory[n]),('velocities',vh[n]))}
        if max(handoff.values())>=1e-8:raise RuntimeError(f'Source state was not restored exactly: {handoff}')
        save(out/'state_handoff.json',dict(edit_frame=k_edit,time_s=first_step*a.dt,parameters_after_edit=timed[0]['params'],max_abs_error=handoff,verified=True,
            precision='the source cache stores float32; the restored solver state equals those stored values exactly'))
    last_step=(count-1)*stride+(2*half if exposure else 0)
    # [PROFILE] Optional wall-time samples and a short native contact-log window.
    # The diagnostic branch never changes constitutive or state values.
    profile=[]
    for step in range(first_step+1,last_step+1):
        if a.profile_after is not None:
            verbose=a.profile_after<=step*a.dt<=a.profile_after+.1
            uipc.Logger.set_level(uipc.Logger.Info if verbose else uipc.Logger.Warn)
            if verbose:print('PROFILE_BEGIN_NATIVE_STEP',step,step*a.dt,flush=True)
            tick=time.monotonic()
        world.advance()
        if not world.is_valid():raise RuntimeError('Invalid native world at step '+str(step))
        if a.profile_after is not None:advanced=time.monotonic()
        world.retrieve();xall,_=read(step*a.dt,step%stride==0);capture(step,xall)
        if a.profile_after is not None and(step%10==0 or verbose):
            profile.append(dict(step=step,time_s=step*a.dt,native_advance_s=advanced-tick,retrieve_and_record_s=time.monotonic()-advanced))
            save(out/'solver_timing.json',dict(samples=profile,source_changes='Optional timing/logging only; physical model and states are unchanged'))
        if step%stride==0 and(step//stride)%6==0:
            print('FRAME',step//stride+1,'T',round(step*a.dt,3),'WALL',round(time.monotonic()-start,2),flush=True)
            save(out/'telemetry_partial.json',telemetry)
            np.savez_compressed(out/'checkpoint.npz',**{n+'_positions':np.array(v,dtype=np.float32)for n,v in xhistory.items()},
                **{n+'_velocities':np.array(v,dtype=np.float32)for n,v in vh.items()},times=np.arange(len(next(iter(xhistory.values()))))/fps)
    arrays={n+'_positions':np.array(v,dtype=np.float32)for n,v in xhistory.items()}
    arrays.update({n+'_velocities':np.array(v,dtype=np.float32)for n,v in vh.items()});arrays['times']=np.arange(count)/fps
    if timed:
        i=k_edit-1
        for key in list(arrays):
            if key!='times':
                if len(arrays[key])!=count-i:raise RuntimeError('Unexpected continuation length')
                arrays[key]=np.concatenate([src[key][:i],arrays[key]])
                if not np.array_equal(arrays[key][:i],src[key][:i]):raise RuntimeError('Merged cache differs from the source')
    if not a.settle_only:arrays['shirt_faces']=faces
    np.savez_compressed(out/'simulation.npz',**arrays)
    if exposure:
        expected=np.arange(count)[:,None]/fps+np.array([0,1/120,1/60])
        if timed:
            i=k_edit-1
            shutter_times=list(src_shutter['times'][:3*i])+list(shutter_times)
            shutter={n:list(src_shutter[n+'_positions'][:3*i])+list(v)for n,v in shutter.items()}
        if not np.allclose(shutter_times,expected.ravel(),atol=1e-12,rtol=0):raise RuntimeError('Native exposure sampling differs')
        np.savez_compressed(out/'shutter_positions.npz',times=np.asarray(shutter_times),native_cache_sha256=sha(out/'simulation.npz'),
            **{n+'_positions':np.array(v,dtype=np.float32)for n,v in shutter.items()})
    save(out/'telemetry.json',telemetry)
    if a.prepare_release:
        released=xhistory['shirt'][-1].copy();released[:,:2]+=np.asarray(SPEC['layout']['shirt_xy_center_m'])-(released[:,:2].min(0)+released[:,:2].max(0))/2
        released[:,2]+=SPEC['layout']['shirt_lowest_z_m']-released[:,2].min()
        np.savez_compressed(prepared_release,positions=released,velocities=vh['shirt'][-1],source_cache_sha256=sha(out/'simulation.npz'))
    if a.settle_only:
        np.savez_compressed(equilibrium,positions=xhistory['seat'][-1],velocities=vh['seat'][-1])
    save(out/'completion.json',dict(complete=True,worker_host=socket.gethostname(),gpu_uuid=os.environ.get('CUDA_VISIBLE_DEVICES'),
        cache_sha256=sha(out/'simulation.npz'),frames=count,runtime_s=time.monotonic()-start,native_scene_valid=world.is_valid(),uipc_version=uipc.__version__,
        exposure_cache_sha256=sha(out/'shutter_positions.npz')if exposure else None,exposure_duration_s=1/60 if exposure else None,
        exposure_native_states=3*count if exposure else 0,native_last_time_s=last_step*a.dt,state_handoff=handoff))
    print('COMPLETE',a.case,round(time.monotonic()-start,2),flush=True)

if __name__=='__main__':main()
