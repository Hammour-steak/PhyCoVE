"""libuipc simulation for the steel-ball / tensioned-membrane case."""
from pathlib import Path
import argparse,copy,hashlib,json,platform,sys,time
import numpy as np
from scipy.spatial import Delaunay,cKDTree
import trimesh

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[3]
sys.path[:0]=[str(HERE.parent),str(ROOT/'tools/manifold3d_deps'),str(ROOT/'tools/ipc_probe_deps')]
import uipc
from uipc import builtin,view
from uipc.core import Engine,World,Scene,AffineBodyStateAccessorFeature,FiniteElementStateAccessorFeature
from uipc.geometry import trimesh as ipc_trimesh,ground,label_surface
from uipc.constitution import AffineBodyConstitution,NeoHookeanShell,ElasticModuli2D,DiscreteShellBending
from edit_vocab import SPEC,SPEC_PATH,override_for,CASE_DSL,STAGED_DSL

def save(path,obj):path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')

def membrane_mesh(nr,nt,rest_radius,z):
    """Quality triangular disk with exact circular boundary vertices.

    Ring populations grow with radius before a 2-D Delaunay triangulation.  This
    avoids the pathological 128-way centre fan whose first circumferential edge
    was smaller than the physical shell/contact thickness.
    """
    verts=[[0.,0.,z]]
    for ir in range(1,nr):
        r=rest_radius*ir/nr
        count=max(8,round(nt*ir/nr))
        phase=(ir%2)*np.pi/count
        for it in range(count):
            q=2*np.pi*it/count+phase
            verts.append([r*np.cos(q),r*np.sin(q),z])
    for it in range(nt):
        q=2*np.pi*it/nt
        verts.append([rest_radius*np.cos(q),rest_radius*np.sin(q),z])
    verts=np.asarray(verts,float)
    faces=Delaunay(verts[:,:2]).simplices.astype(np.int32)
    # Delaunay winding is not promised.  Keep every shell face consistently +Z.
    tri=verts[faces]
    flip=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])[:,2]<0
    faces[flip,1],faces[flip,2]=faces[flip,2].copy(),faces[flip,1].copy()
    fixed=np.linalg.norm(verts[:,:2],axis=1)>rest_radius*(1-1e-9)
    return verts,faces,fixed

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',choices=[*SPEC['cases'],*STAGED_DSL],required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--duration',type=float);ap.add_argument('--dt',type=float);a=ap.parse_args()
    p=copy.deepcopy(SPEC['baseline']);p.update(SPEC['cases'].get(a.case,{}));p.update(override_for(a.case))
    sim=copy.deepcopy(SPEC['simulation']);
    if a.duration is not None:SPEC_DURATION=a.duration
    else:SPEC_DURATION=SPEC['duration_s']
    if a.dt is not None:sim['dt_s']=a.dt
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise FileExistsError(out)
    nr=int(sim['radial_resolution']);nt=int(sim['angular_resolution']);dt=float(sim['dt_s']);fps=int(SPEC['fps']);stride=round(1/(fps*dt));frames=round(SPEC_DURATION*fps)+1
    if abs(stride*dt-1/fps)>1e-10:raise ValueError('dt must divide frame interval')
    installed_stretch=1.0+p['membrane_surface_tension_n_m']*(1-p['membrane_poisson_ratio']**2)/(p['membrane_young_modulus_pa']*p['membrane_thickness_m'])
    rest_radius=(p['membrane_clear_diameter_m']/2)/installed_stretch
    rv,rf,fixed=membrane_mesh(nr,nt,rest_radius,p['membrane_height_m']) if p['membrane_present'] else (np.empty((0,3)),np.empty((0,3),np.int32),np.empty(0,bool))
    ball=trimesh.creation.icosphere(subdivisions=3,radius=p['ball_radius_m'])
    second_ball=trimesh.creation.icosphere(subdivisions=3,radius=p['second_ball_radius_m'])
    if p['second_ball_present'] and (not np.isclose(p['second_ball_radius_m'],p['ball_radius_m']) or not np.isclose(p['second_ball_mass_kg'],p['ball_mass_kg'])):
        raise ValueError('The added ball must be identical to the source ball in radius and mass')
    cfg=Scene.default_config();cfg['dt']=dt;cfg['gravity']=[[0.],[0.],[-p['gravity_m_s2']]]
    cfg['contact']['d_hat']=sim['contact_d_hat_m'];cfg['contact']['eps_velocity']=0.0001
    cfg['newton']['semi_implicit']['enable']=0;cfg['newton']['velocity_tol']=sim['newton_velocity_tolerance_m_s'];cfg['newton']['max_iter']=sim['newton_max_iterations']
    cfg['linear_system']['fem_preconditioner']='mas';cfg['linear_system']['tol_rate']=1e-8;cfg['line_search']['max_iter']=48
    cfg['contact']['adaptive']['kappa_eval_scale']=1.;cfg['contact']['adaptive']['min_kappa']=1e8;cfg['contact']['adaptive']['max_kappa']=1e13
    scene=Scene(cfg);scene.contact_tabular().default_model(p['membrane_friction'],1e11)
    scene.objects().create('floor').geometries().create(ground(0.0,np.array([0.,0.,1.])))
    membrane_slot=None
    if p['membrane_present']:
        mesh=ipc_trimesh(rv,rf);label_surface(mesh)
        NeoHookeanShell().apply_to(mesh,ElasticModuli2D.youngs_poisson(p['membrane_young_modulus_pa'],p['membrane_poisson_ratio']),mass_density=p['membrane_density_kg_m3'],thickness=p['membrane_thickness_m']/2)
        DiscreteShellBending().apply_to(mesh,p['membrane_young_modulus_pa'],p['membrane_poisson_ratio'])
        view(mesh.vertices().find(builtin.is_fixed))[:]=fixed.astype(np.int32)
        membrane_slot,_=scene.objects().create('rubber_membrane').geometries().create(mesh)
    ball_initial=np.eye(4);ball_initial[:3,3]=p['ball_initial_location_m']
    if p['ball_present']:
        mesh=ipc_trimesh(np.asarray(ball.vertices),np.asarray(ball.faces,np.int32));label_surface(mesh)
        AffineBodyConstitution().apply_to(mesh,2.0e11,p['ball_mass_kg']/ball.volume);view(mesh.transforms())[:]=ball_initial
        scene.objects().create('steel_ball').geometries().create(mesh)
    second_ball_initial=np.eye(4);second_ball_initial[:3,3]=p['second_ball_initial_location_m']
    if p['second_ball_present']:
        mesh=ipc_trimesh(np.asarray(second_ball.vertices),np.asarray(second_ball.faces,np.int32));label_surface(mesh)
        AffineBodyConstitution().apply_to(mesh,2.0e11,p['second_ball_mass_kg']/second_ball.volume);view(mesh.transforms())[:]=second_ball_initial
        scene.objects().create('second_steel_ball').geometries().create(mesh)
    config=dict(scene_id=SPEC['scene_id'],case=a.case,edit_dsl={**CASE_DSL,**STAGED_DSL}[a.case],physics=p,simulation=sim,solver='libuipc CUDA NeoHookeanShell + DiscreteShellBending + IPC',solver_config=cfg,
      material_scope='Effective uncalibrated nearly incompressible rubber sheet; no MPM thickening and no hand-authored deformation.',execution_host=platform.node(),local_blender_used=False,
      duration_s=SPEC_DURATION,output_fps=fps,output_states=frames,integration_steps=round(SPEC_DURATION/dt),playback_rate=1.0)
    save(out/'simulation_config.json',config)
    uipc.Logger.set_level(uipc.Logger.Warn);started=time.monotonic();engine=Engine('cuda',str(out/'solver'));world=World(engine);world.init(scene)
    if not world.is_valid():raise RuntimeError('Invalid initial IPC world')
    fem=world.features().find(FiniteElementStateAccessorFeature) if p['membrane_present'] else None
    fg=fem.create_geometry() if fem else None;mapping=None
    if fem:
        for name,value in [(builtin.position,np.zeros(3)),(builtin.velocity,np.zeros(3))]:
            if fg.vertices().find(name) is None:fg.vertices().create(name,value)
        fem.copy_to(fg);xall=np.asarray(fg.positions().view()).reshape(-1,3);dist,mapping=cKDTree(xall).query(rv)
        if dist.max()>1e-8:raise RuntimeError('FEM mapping failed')
        pos=view(fg.vertices().find(builtin.position)).reshape(-1,3)
        # Convert the requested membrane force per unit length to an installed
        # equibiaxial stretch. This small-strain membrane relation is only the
        # initialization; the recorded dynamics use the nonlinear NH shell.
        pos[mapping,:2]*=installed_stretch
        config['derived_installed_stretch_ratio']=installed_stretch
        view(fg.vertices().find(builtin.velocity)).reshape(-1,3)[mapping]=0
        fem.copy_from(fg);world.retrieve()
        save(out/'simulation_config.json',config)
    abd=world.features().find(AffineBodyStateAccessorFeature) if (p['ball_present'] or p['second_ball_present']) else None
    ag=abd.create_geometry() if abd else None
    if abd:
        for name,value in [(builtin.transform,np.eye(4)),(builtin.velocity,np.zeros((4,4)))]:
            if ag.instances().find(name) is None:ag.instances().create(name,value)
    ball_index=second_ball_index=None
    if abd:
        abd.copy_to(ag);TT=np.asarray(ag.instances().find(builtin.transform).view())
        if p['ball_present']:
            distances=np.linalg.norm(TT[:,:3,3]-ball_initial[:3,3],axis=1);ball_index=int(np.argmin(distances))
            if distances[ball_index]>1e-8:raise RuntimeError('Primary ball affine-body mapping failed')
        if p['second_ball_present']:
            distances=np.linalg.norm(TT[:,:3,3]-second_ball_initial[:3,3],axis=1);second_ball_index=int(np.argmin(distances))
            if distances[second_ball_index]>1e-8 or second_ball_index==ball_index:raise RuntimeError('Second ball affine-body mapping failed')
    MP=[];MV=[];BT=[];BV=[];SBT=[];SBV=[];rows=[]
    for f in range(frames):
        if fem:
            fem.copy_to(fg);px=np.asarray(fg.positions().view()).reshape(-1,3)[mapping].copy();pv=np.asarray(fg.vertices().find(builtin.velocity).view()).reshape(-1,3)[mapping].copy()
        else:px=np.empty((0,3));pv=np.empty((0,3))
        if p['ball_present']:
            abd.copy_to(ag);T=np.asarray(ag.instances().find(builtin.transform).view())[ball_index].copy();V=np.asarray(ag.instances().find(builtin.velocity).view())[ball_index].copy()
        else:T=ball_initial.copy();V=np.zeros((4,4))
        if p['second_ball_present']:
            abd.copy_to(ag);ST=np.asarray(ag.instances().find(builtin.transform).view())[second_ball_index].copy();SV=np.asarray(ag.instances().find(builtin.velocity).view())[second_ball_index].copy()
        else:ST=second_ball_initial.copy();SV=np.zeros((4,4))
        MP.append(px);MV.append(pv);BT.append(T);BV.append(V);SBT.append(ST);SBV.append(SV)
        depression=float(max(0,p['membrane_height_m']-px[:,2].min())) if len(px) else 0.
        row=dict(frame=f+1,time_s=f/fps,ball_location_m=T[:3,3].tolist(),ball_velocity_m_s=V[:3,3].tolist(),max_membrane_depression_m=depression)
        if p['second_ball_present']:
            row.update(second_ball_location_m=ST[:3,3].tolist(),second_ball_velocity_m_s=SV[:3,3].tolist(),ball_center_distance_m=float(np.linalg.norm(T[:3,3]-ST[:3,3])))
        rows.append(row)
        if f%6==0 or f==frames-1:
            print('FRAME',f+1,'/',frames,'ball_z',round(float(T[2,3]),4),'depression_mm',round(depression*1000,2),'elapsed',round(time.monotonic()-started,1),flush=True)
            save(out/'progress.json',dict(case=a.case,frame=f+1,total_states=frames,time_s=f/fps,wall_seconds=time.monotonic()-started))
        if f<frames-1:
            for _ in range(stride):world.advance();world.retrieve()
    np.savez_compressed(out/'simulation.npz',cache_schema_version=np.array([2],np.int32),rigid_body_ids=np.array(['ball','second_ball']),rigid_body_present=np.array([p['ball_present'],p['second_ball_present']],np.int8),membrane_positions=np.asarray(MP),membrane_velocities=np.asarray(MV),membrane_rest_positions=rv,membrane_faces=rf,membrane_fixed_mask=fixed,ball_transforms=np.asarray(BT),ball_velocities=np.asarray(BV),second_ball_transforms=np.asarray(SBT),second_ball_velocities=np.asarray(SBV),ball_vertices=np.asarray(ball.vertices),ball_faces=np.asarray(ball.faces),second_ball_vertices=np.asarray(second_ball.vertices),second_ball_faces=np.asarray(second_ball.faces),times=np.arange(frames)/fps,second_ball_present=np.array([p['second_ball_present']],np.int8))
    report=dict(status='complete',case=a.case,frames=frames,duration_s=SPEC_DURATION,output_fps=fps,integration_steps=round(SPEC_DURATION/dt),playback_rate=1.0,wall_seconds=time.monotonic()-started,peak_depression_m=max(r['max_membrane_depression_m'] for r in rows),rows=rows,manual_motion=False,manual_deformation=False,development_status='PENDING_NUMERICAL_AND_MATERIAL_CALIBRATION')
    save(out/'simulation_report.json',report);print('COMPLETE',a.case,report['peak_depression_m'],flush=True)
if __name__=='__main__':main()
