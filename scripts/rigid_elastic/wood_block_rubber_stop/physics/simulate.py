"""Remote-only libuipc solid-FEM/rigid-body impact simulation."""
from pathlib import Path
import argparse,copy,hashlib,json,os,socket,sys,time
import numpy as np
import trimesh
from scipy.spatial import cKDTree
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path[:0]=[str(HERE.parent),str(ROOT/'tools/manifold3d_deps'),str(ROOT/'tools/ipc_probe_deps')]
import uipc
from uipc import builtin,view
from uipc.core import Engine,World,Scene,AffineBodyStateAccessorFeature,FiniteElementStateAccessorFeature
from uipc.geometry import trimesh as ipc_trimesh,tetmesh,ground,label_surface,label_triangle_orient,flip_inward_triangles
from uipc.constitution import StableNeoHookean,ElasticModuli,AffineBodyConstitution
from edit_vocab import SPEC,CASE_DSL,STAGED_DSL,parameters,case_dsl

def save(path,obj):path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def structured_box(dim,center_xy,bottom,cells,fixed_boundary='bottom_z'):
 nx,ny,nz=map(int,cells);dx,dy,dz=map(float,dim);cx,cy=center_xy
 xs=np.linspace(cx-dx/2,cx+dx/2,nx+1);ys=np.linspace(cy-dy/2,cy+dy/2,ny+1);zs=np.linspace(bottom,bottom+dz,nz+1)
 v=np.array([[x,y,z] for z in zs for y in ys for x in xs],float)
 def q(i,j,k):return k*(ny+1)*(nx+1)+j*(nx+1)+i
 t=[]
 for k in range(nz):
  for j in range(ny):
   for i in range(nx):
    a=q(i,j,k);b=q(i+1,j,k);c=q(i+1,j+1,k);d=q(i,j+1,k);e=q(i,j,k+1);f=q(i+1,j,k+1);g=q(i+1,j+1,k+1);h=q(i,j+1,k+1)
    t.extend([(a,b,c,g),(a,c,d,g),(a,d,h,g),(a,h,e,g),(a,e,f,g),(a,f,b,g)])
 t=np.asarray(t,np.int32)
 for i,T in enumerate(t):
  P=v[T];det=np.linalg.det(np.stack([P[1]-P[0],P[2]-P[0],P[3]-P[0]],axis=1))
  if det<0:t[i,[2,3]]=t[i,[3,2]]
 if np.min([np.linalg.det(np.stack([v[T[1]]-v[T[0]],v[T[2]]-v[T[0]],v[T[3]]-v[T[0]]],axis=1)) for T in t])<=0:raise RuntimeError('invalid tet orientation')
 if fixed_boundary=='bottom_z':fixed=np.isclose(v[:,2],bottom)
 elif fixed_boundary=='rear_x':fixed=np.isclose(v[:,0],cx+dx/2)
 elif fixed_boundary=='none':fixed=np.zeros(len(v),dtype=bool)
 else:raise ValueError(f'unknown fixed boundary: {fixed_boundary}')
 return v,t,fixed

def boundary_faces(tets):
 faces={}
 for T in tets:
  for f in ((T[0],T[2],T[1]),(T[0],T[1],T[3]),(T[1],T[2],T[3]),(T[2],T[0],T[3])):
   key=tuple(sorted(map(int,f)))
   if key in faces:del faces[key]
   else:faces[key]=tuple(map(int,f))
 return np.asarray(list(faces.values()),np.int32)

def main():
 if sys.platform!='linux' or not os.environ.get('CUDA_VISIBLE_DEVICES'):raise RuntimeError('Linux CUDA host with one GPU bound through CUDA_VISIBLE_DEVICES only')
 ap=argparse.ArgumentParser();ap.add_argument('--case',choices=[*SPEC['cases'],*STAGED_DSL],required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--duration',type=float);ap.add_argument('--dt',type=float);ap.add_argument('--newton-max-iterations',type=int);a=ap.parse_args()
 p=parameters(a.case);sim=copy.deepcopy(SPEC['simulation']);duration=a.duration or SPEC['duration_s']
 if case_dsl(a.case):
  import pcve_edit_dsl as dsl
  from edit_vocab import VOCAB,STAGED_VOCAB
  from pcve_edit_policy import audit_scenario_override
  vocab=STAGED_VOCAB if a.case in STAGED_DSL else VOCAB
  edit=dsl.parse(case_dsl(a.case),vocab)
  audit_scenario_override(edit,vocab,{'physics':dsl.to_scenario_override(edit,vocab)})
 if a.dt is not None:sim['dt_s']=a.dt
 if a.newton_max_iterations is not None:sim['newton_max_iterations']=a.newton_max_iterations
 dt=sim['dt_s'];fps=SPEC['fps'];stride=round(1/(fps*dt));frames=round(duration*fps)+1
 out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 if any(out.iterdir()):raise FileExistsError(out)
 parts=[]
 if p['bumper_present']:
  v,t,fixed=structured_box(p['bumper_dimensions_m'],p['bumper_center_xy_m'],p['bumper_bottom_z_m'],sim['grid_cells'],p['bumper_fixed_boundary']);parts.append(('open_cell_sponge',v,t,fixed,p['bumper_young_modulus_pa'],p['bumper_density_kg_m3']))
 cfg=Scene.default_config();cfg['dt']=dt;cfg['gravity']=[[0.],[0.],[-p['gravity_m_s2']]];cfg['contact']['d_hat']=sim['contact_d_hat_m'];cfg['contact']['eps_velocity']=.0001
 cfg['newton']['semi_implicit']['enable']=0;cfg['newton']['velocity_tol']=2e-4;cfg['newton']['max_iter']=sim['newton_max_iterations'];cfg['linear_system']['fem_preconditioner']='mas';cfg['linear_system']['tol_rate']=1e-8;cfg['line_search']['max_iter']=48
 cfg['contact']['adaptive']['kappa_eval_scale']=1.;cfg['contact']['adaptive']['min_kappa']=1e8;cfg['contact']['adaptive']['max_kappa']=1e13
 scene=Scene(cfg);tab=scene.contact_tabular();tab.default_model(p['contact_friction'],sim['contact_resistance']);block_contact=tab.create('wood_block_contact');sponge_contact=tab.create('free_sponge_contact');floor_contact=tab.create('floor_contact');tab.insert(block_contact,tab.default_element(),p['contact_friction'],sim['contact_resistance']);tab.insert(block_contact,floor_contact,p['floor_friction'],sim['contact_resistance']);tab.insert(sponge_contact,floor_contact,p['sponge_floor_friction'],sim['contact_resistance'])
 floor=ground(0.,np.array([0.,0.,1.]));floor_contact.apply_to(floor);scene.objects().create('fixed_floor').geometries().create(floor)
 # The hero table leg is a real fixed rigid body in the IPC scene, not render-only decoration.
 backstop_dims=np.asarray(p['backstop_dimensions_m']);backstop_body=trimesh.creation.box(backstop_dims);backstop_T=np.eye(4);backstop_T[:3,3]=p['backstop_center_m']
 backstop_mesh=ipc_trimesh(np.asarray(backstop_body.vertices),np.asarray(backstop_body.faces,np.int32));label_surface(backstop_mesh);AffineBodyConstitution().apply_to(backstop_mesh,1.0e10,p['backstop_density_kg_m3']);view(backstop_mesh.transforms())[:]=backstop_T;view(backstop_mesh.instances().find(builtin.is_fixed))[:]=1;scene.objects().create('fixed_wood_table_leg').geometries().create(backstop_mesh)
 rest=[];tets=[];faces=[];fixed_masks=[];part_ids=[];offset=0
 for part_id,(name,v,t,fixed,E,rho) in enumerate(parts,1):
  mesh=tetmesh(v,t);label_surface(mesh);label_triangle_orient(mesh);mesh=flip_inward_triangles(mesh);StableNeoHookean().apply_to(mesh,ElasticModuli.youngs_poisson(E,p['bumper_poisson_ratio']),mass_density=rho);view(mesh.vertices().find(builtin.is_fixed))[:]=fixed.astype(np.int32);sponge_contact.apply_to(mesh);scene.objects().create(name).geometries().create(mesh)
  bf=boundary_faces(t)+offset;rest.append(v);tets.append(t+offset);faces.append(bf);fixed_masks.append(fixed);part_ids.append(np.full(len(v),part_id,np.int8));offset+=len(v)
 dims=np.asarray(p['block_dimensions_m']);block=trimesh.creation.box(dims);T0=np.eye(4);T0[:3,3]=p['block_initial_center_m'];mesh=ipc_trimesh(np.asarray(block.vertices),np.asarray(block.faces,np.int32));label_surface(mesh);AffineBodyConstitution().apply_to(mesh,1e10,p['block_mass_kg']/block.volume);view(mesh.transforms())[:]=T0;block_contact.apply_to(mesh)
 # DELETE wood_block (block_present false): the block is not in the IPC scene; its record keeps the initial pose at rest.
 block_present=bool(p.get('block_present',True))
 if block_present:scene.objects().create('wood_block').geometries().create(mesh)
 added_block=None;added_T0=None
 if p['added_block_present']:
  added_dims=np.asarray(p['added_block_dimensions_m']);added_block=trimesh.creation.box(added_dims);added_T0=np.eye(4);added_T0[:3,3]=p['added_block_initial_center_m'];added_mesh=ipc_trimesh(np.asarray(added_block.vertices),np.asarray(added_block.faces,np.int32));label_surface(added_mesh);AffineBodyConstitution().apply_to(added_mesh,1e10,p['added_block_mass_kg']/added_block.volume);view(added_mesh.transforms())[:]=added_T0;block_contact.apply_to(added_mesh);scene.objects().create('secondary_wood_block').geometries().create(added_mesh)
 config={'scene_id':SPEC['scene_id'],'case_id':a.case,'edit_dsl':case_dsl(a.case),'physics':p,'simulation':sim,'solver':'libuipc 0.0.28 CUDA StableNeoHookean FEM + ABD + frictional IPC','solver_config':cfg,'execution_host':None,'local_blender_used':False,'manual_motion':False,'manual_deformation':False,'model_scope':SPEC['model_scope']};save(out/'simulation_config.json',config)
 config.update(execution_host=socket.gethostname().split('.')[0],execution_hostname=socket.gethostname(),gpu_uuid=os.environ.get('CUDA_VISIBLE_DEVICES'),new_revision=SPEC.get('revision_note','speed x1.5; all baseline poses, friction and materials unchanged'))
 save(out/'simulation_config.json',config)
 uipc.Logger.set_level(uipc.Logger.Warn);start=time.monotonic();engine=Engine('cuda',str(out/'solver'));world=World(engine);world.init(scene)
 if not world.is_valid():raise RuntimeError('invalid initial IPC scene')
 abd=world.features().find(AffineBodyStateAccessorFeature);ag=abd.create_geometry()
 for n,val in ((builtin.transform,np.eye(4)),(builtin.velocity,np.zeros((4,4)))):
  if ag.instances().find(n) is None:ag.instances().create(n,val)
 abd.copy_to(ag);TT=np.asarray(ag.instances().find(builtin.transform).view());bi=None
 if block_present:bi=int(np.argmin(np.linalg.norm(TT[:,:3,3]-T0[:3,3],axis=1)));V=np.zeros((4,4));V[:3,3]=p['block_initial_velocity_m_s'];view(ag.instances().find(builtin.velocity))[bi]=V
 abi=None
 if added_T0 is not None:
  abi=int(np.argmin(np.linalg.norm(TT[:,:3,3]-added_T0[:3,3],axis=1)));AV=np.zeros((4,4));AV[:3,3]=p['added_block_initial_velocity_m_s'];view(ag.instances().find(builtin.velocity))[abi]=AV
 abd.copy_from(ag);world.retrieve()
 allrest=np.concatenate(rest) if rest else np.empty((0,3));allt=np.concatenate(tets) if tets else np.empty((0,4),np.int32);allf=np.concatenate(faces) if faces else np.empty((0,3),np.int32);allfixed=np.concatenate(fixed_masks) if fixed_masks else np.empty(0,bool);allparts=np.concatenate(part_ids) if part_ids else np.empty(0,np.int8)
 fem=world.features().find(FiniteElementStateAccessorFeature) if parts else None;fg=fem.create_geometry() if fem else None;mapping=None
 if fem:
  for n,val in ((builtin.position,np.zeros(3)),(builtin.velocity,np.zeros(3))):
   if fg.vertices().find(n) is None:fg.vertices().create(n,val)
  fem.copy_to(fg);xa=np.asarray(fg.positions().view()).reshape(-1,3);dist,mapping=cKDTree(xa).query(allrest)
  if dist.max()>1e-8 or len(np.unique(mapping))!=len(allrest):raise RuntimeError('FEM mapping failed')
 BP=[];BV=[];ABP=[];ABV=[];XP=[];XV=[];rows=[];initial_front=float(p['bumper_center_xy_m'][0]-p['bumper_dimensions_m'][0]/2);initial_rear=float(p['bumper_center_xy_m'][0]+p['bumper_dimensions_m'][0]/2);initial_thickness=float(p['bumper_dimensions_m'][0]);leg_front=float(p['backstop_center_m'][0]-p['backstop_dimensions_m'][0]/2);primary_mask=allparts==1;front_mask=primary_mask & np.isclose(allrest[:,0],initial_front,atol=1e-10);rear_mask=primary_mask & np.isclose(allrest[:,0],initial_rear,atol=1e-10);substep_peak_displacement=0.;substep_peak_compression=0.;substep_peak_max_compression=0.;substep_index=0;substep_peak_index=None
 for f in range(frames):
  abd.copy_to(ag);current_T=np.asarray(ag.instances().find(builtin.transform).view());current_V=np.asarray(ag.instances().find(builtin.velocity).view());T=current_T[bi].copy() if bi is not None else T0.copy();VV=current_V[bi].copy() if bi is not None else np.zeros((4,4));BP.append(T);BV.append(VV)
  if abi is not None:ABP.append(current_T[abi].copy());ABV.append(current_V[abi].copy())
  if fem:fem.copy_to(fg);x=np.asarray(fg.positions().view()).reshape(-1,3)[mapping].copy();vv=np.asarray(fg.vertices().find(builtin.velocity).view()).reshape(-1,3)[mapping].copy()
  else:x=np.empty((0,3));vv=np.empty((0,3))
  XP.append(x);XV.append(vv)
  primary=x[primary_mask] if len(x) and np.any(primary_mask) else np.empty((0,3));front_x=x[front_mask,0] if len(x) and np.any(front_mask) else np.empty(0);rear_x=x[rear_mask,0] if len(x) and np.any(rear_mask) else np.empty(0);compression=max(0.,initial_thickness-float(rear_x.mean()-front_x.mean())) if len(front_x) and len(rear_x) else 0.;max_compression=max(0.,initial_thickness-float(rear_x.min()-front_x.max())) if len(front_x) and len(rear_x) else 0.;disp=float(np.linalg.norm(primary-allrest[primary_mask],axis=1).max()) if len(primary) else 0.;com_translation=float(primary[:,0].mean()-allrest[primary_mask,0].mean()) if len(primary) else 0.;sponge_rear=float(rear_x.max()) if len(rear_x) else None;leg_gap=float(leg_front-sponge_rear) if sponge_rear is not None else None
  block_world=np.asarray(block.vertices)@T[:3,:3].T+T[:3,3];block_front=float(block_world[:,0].max());nominal_gap=float(initial_front-block_front)
  added_center=current_T[abi][:3,3].tolist() if abi is not None else None;added_velocity=current_V[abi][:3,3].tolist() if abi is not None else None
  rows.append({'frame':f+1,'time_s':f/fps,'block_center_m':T[:3,3].tolist(),'block_velocity_m_s':VV[:3,3].tolist(),'block_front_x_m':block_front,'nominal_reference_gap_m':nominal_gap,'bumper_max_displacement_m':disp,'sponge_center_translation_x_m':com_translation,'sponge_rear_x_m':sponge_rear,'sponge_to_table_leg_gap_m':leg_gap,'front_face_mean_compression_m':compression,'front_face_max_compression_m':max_compression,'added_block_center_m':added_center,'added_block_velocity_m_s':added_velocity})
  if f%10==0:print('FRAME',f+1,'/',frames,'x',round(float(T[0,3]),4),'vx',round(float(VV[0,3]),3),'disp_mm',round(disp*1000,2),'elapsed',round(time.monotonic()-start,1),flush=True)
  if f<frames-1:
   for _ in range(stride):
    world.advance();world.retrieve();substep_index+=1
    if fem and np.any(allparts==1):
     fem.copy_to(fg);sx=np.asarray(fg.positions().view()).reshape(-1,3)[mapping];sp=sx[allparts==1];sr=allrest[allparts==1]
     sd=float(np.linalg.norm(sp-sr,axis=1).max());sfx=sx[front_mask,0] if np.any(front_mask) else np.empty(0);srx=sx[rear_mask,0] if np.any(rear_mask) else np.empty(0);sc=max(0.,initial_thickness-float(srx.mean()-sfx.mean())) if len(sfx) and len(srx) else 0.;smc=max(0.,initial_thickness-float(srx.min()-sfx.max())) if len(sfx) and len(srx) else 0.
     if sd>substep_peak_displacement:substep_peak_displacement=sd;substep_peak_index=substep_index
     substep_peak_compression=max(substep_peak_compression,sc);substep_peak_max_compression=max(substep_peak_max_compression,smc)
 np.savez_compressed(out/'simulation.npz',block_transforms=np.asarray(BP),block_velocities=np.asarray(BV),block_vertices=np.asarray(block.vertices),block_faces=np.asarray(block.faces),added_block_transforms=np.asarray(ABP),added_block_velocities=np.asarray(ABV),added_block_vertices=np.asarray(added_block.vertices) if added_block is not None else np.empty((0,3)),added_block_faces=np.asarray(added_block.faces) if added_block is not None else np.empty((0,3),np.int32),elastic_positions=np.asarray(XP),elastic_velocities=np.asarray(XV),elastic_rest_positions=allrest,elastic_tetrahedra=allt,elastic_surface_faces=allf,elastic_fixed_mask=allfixed,elastic_part_ids=allparts,times=np.arange(frames)/fps)
 speed=np.array([r['block_velocity_m_s'][0] for r in rows]);contact=np.array([r['bumper_max_displacement_m'] for r in rows]);gaps=np.array([r['nominal_reference_gap_m'] for r in rows]);first=int(np.argmax(gaps<=sim['contact_d_hat_m']*1.5))+1 if np.any(gaps<=sim['contact_d_hat_m']*1.5) and p['bumper_present'] else None
 target_front=initial_front if p['bumper_present'] else float(p['backstop_center_m'][0]-p['backstop_dimensions_m'][0]/2)
 if p['added_block_present']:target_front=min(target_front,float(p['added_block_initial_center_m'][0]-p['added_block_dimensions_m'][0]/2))
 any_gaps=np.array([target_front-r['block_front_x_m'] for r in rows]);first_any=int(np.argmax(any_gaps<=sim['contact_d_hat_m']*1.5))+1 if np.any(any_gaps<=sim['contact_d_hat_m']*1.5) else None
 leg_gaps=np.array([r['sponge_to_table_leg_gap_m'] for r in rows if r['sponge_to_table_leg_gap_m'] is not None]);first_leg=int(np.argmax(leg_gaps<=sim['contact_d_hat_m']*1.5))+1 if len(leg_gaps) and np.any(leg_gaps<=sim['contact_d_hat_m']*1.5) else None
 max_sponge_translation=max((r['sponge_center_translation_x_m'] for r in rows),default=0.)
 added_initial=np.asarray(p['added_block_initial_center_m']);added_travel=max((float(np.linalg.norm(np.asarray(r['added_block_center_m'])-added_initial)) for r in rows if r['added_block_center_m'] is not None),default=0.)
 backstop_mass=float(np.prod(p['backstop_dimensions_m']))*p['backstop_density_kg_m3']
 pre_i=max(0,(first_any or frames)-2);pre_v=float(speed[pre_i]);v0=float(p['block_initial_velocity_m_s'][0]);pre_distance=max(0.,float(rows[pre_i]['block_center_m'][0]-p['block_initial_center_m'][0]));observed_mu=(v0*v0-pre_v*pre_v)/(2*p['gravity_m_s2']*pre_distance) if pre_distance>1e-6 else 0.
 report={'status':'complete','case_id':a.case,'frames':frames,'wall_seconds':time.monotonic()-start,'first_primary_contact_frame':first,'first_any_contact_frame':first_any,'peak_bumper_displacement_m':max(float(contact.max(initial=0)),substep_peak_displacement),'peak_bumper_displacement_saved_frame_m':float(contact.max(initial=0)),'peak_bumper_displacement_substep_index':substep_peak_index,'peak_front_face_compression_m':max(float(max(r['front_face_mean_compression_m'] for r in rows)),substep_peak_compression),'peak_front_face_max_compression_m':max(float(max(r['front_face_max_compression_m'] for r in rows)),substep_peak_max_compression),'minimum_block_x_velocity_m_s':float(speed.min()),'final_block_x_velocity_m_s':float(speed[-1]),'pre_contact_block_x_velocity_m_s':pre_v,'pre_contact_speed_loss_m_s':v0-pre_v,'pre_contact_slide_distance_m':pre_distance,'floor_friction_input':p['floor_friction'],'floor_friction_inferred_from_pre_contact_motion':observed_mu,'initial_block_kinetic_energy_j':0.5*p['block_mass_kg']*float(np.dot(p['block_initial_velocity_m_s'],p['block_initial_velocity_m_s'])),'block_apparent_density_kg_m3':p['block_mass_kg']/float(np.prod(p['block_dimensions_m'])),'fixed_backstop_mass_kg':backstop_mass,'fixed_backstop_has_collision_volume':True,'fixed_table_leg_mass_kg':backstop_mass,'fixed_table_leg_has_collision_volume':True,'added_block_peak_travel_m':added_travel,'rows':rows,'development_status':'OBSERVABLE_OPEN_CELL_SPONGE_COMPRESSION_CANDIDATE_PENDING_PRODUCT_SPECIFIC_CRUSHABLE_FOAM_AND_VISCOELASTIC_CALIBRATION'};save(out/'simulation_report.json',report);print('COMPLETE',a.case,json.dumps({k:report[k] for k in ('first_any_contact_frame','pre_contact_block_x_velocity_m_s','pre_contact_speed_loss_m_s','floor_friction_inferred_from_pre_contact_motion','peak_bumper_displacement_m','peak_front_face_compression_m','peak_front_face_max_compression_m','final_block_x_velocity_m_s','added_block_peak_travel_m')}),flush=True)
 report.update({'first_sponge_table_leg_contact_frame':first_leg,'max_sponge_center_translation_x_m':max_sponge_translation,'sponge_fixed_vertex_count':int(allfixed.sum()),'sponge_floor_friction_input':p['sponge_floor_friction']})
 save(out/'simulation_report.json',report)
if __name__=='__main__':main()
