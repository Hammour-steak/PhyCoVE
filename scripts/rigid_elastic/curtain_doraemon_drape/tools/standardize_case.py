"""Ground truth in the pcve_ground_truth/1 layout and public sidecars from the native data."""

from pathlib import Path
import json,shutil,sys
import numpy as np,trimesh
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'physics'))
from baseline import CASE,save,sha
from vocab import resolve

def credits(render_manifest):
    """Source and licence of every asset file the render loaded, from the registry (assets.json)."""
    repo=Path(__file__).resolve().parents[4]
    registry=json.loads((repo/'assets.json').read_text(encoding='utf8'))['assets']
    rows=[]
    for rel in render_manifest.get('assets',[]):
        name=rel.split('assets/',1)[1] if rel.startswith('assets/') else rel
        group=max((g for g in registry if name.startswith(g+'/')),key=len,default=None)
        if group is None:rows.append(dict(path=rel,registered=False));continue
        entry=registry[group];item=entry.get('files',{}).get(name[len(group)+1:],{})
        rows.append(dict(path=rel,group=group,source=item.get('source',entry.get('source')),
                         license=item.get('license',entry.get('license')),author=item.get('author',entry.get('author'))))
    return rows

def export(case,out,simulation,prompts=None):
    """Write GT and public sidecars of one finalized case folder from its native solver output folder."""
    p,edit=resolve(case);simulation=Path(simulation)
    if prompts is not None:edit['prompts']=prompts
    render=json.loads((out/'render_manifest.json').read_text(encoding='utf8'))
    save(out/'asset_credits.json',dict(assets=credits(render),
        figure=dict(object='blue-and-white porcelain vase',source='https://polyhaven.com/a/antique_ceramic_vase_01',license='CC0',
                    preparation='assets/scenes/curtain_doraemon_drape/porcelain_vase/preparation.json'),
        public_scope='Rendered media and evaluation data. BlenderKit dressing (notebook, pen holder) is royalty-free and not redistributed as files.'))
    for name in ['physics_audit.json']:
        source=simulation/name;target=out/name
        if not target.exists()or not source.samefile(target):shutil.copy2(source,target)
    z=np.load(out/'cache.npz');names=list(z['rigid_names']);cam=json.loads((out/'camera_calibration.json').read_text(encoding='utf8'))
    (out/'geometry').mkdir(exist_ok=True);objects={};canonical={};coordinate_errors={}
    for name,active,mass in [('figurine',p['figure_active'][0],p['figure_mass']),('ceramic_cup',p['cup_active'][0],p['cup_mass'])]:
        objects[name]=dict(object_name=name,present=bool(active),mass=mass,material_class='rigid')
        if not active:continue
        native=simulation/(name+'_geometry.npz');g=np.load(native)
        m=trimesh.Trimesh(g['vertices'],g['faces'],process=False);centre=m.center_mass
        shutil.copy2(native,out/'geometry'/(name+'_native.npz'))
        v=g['vertices']-centre
        np.savez_compressed(out/'geometry'/(name+'_com.npz'),vertices=v,faces=g['faces'],native_local_com=centre)
        T=z['rigid_transforms'][:,names.index(name)];C=np.tile(np.eye(4),(len(T),1,1));C[:,:3,3]=centre
        transforms=T@C;canonical[name]=transforms
        objects[name].update(dimensions=np.ptp(g['vertices'],axis=0).tolist(),collision_mesh=f'geometry/{name}_com.npz',
            native_collision_mesh=f'geometry/{name}_native.npz',native_local_com=centre.tolist())
        errors=[]
        for index in [0,len(T)-1]:
            original=g['vertices']@T[index,:3,:3].T+T[index,:3,3]
            recentered=v@transforms[index,:3,:3].T+transforms[index,:3,3]
            errors.append(float(abs(original-recentered).max()))
        coordinate_errors[name]=max(errors)
    objects['curtain']=dict(object_name='curtain',present=True,material_class='elastic_thin_woven_shell',
        deformation_manifest='deformation_manifest.json',rigid_transform_proxy=False)
    masks=np.load(out/'instance_masks.npz')['masks'];frames=[];mass=z['vertex_masses']
    com=np.einsum('tvi,v->ti',z['positions'],mass)/mass.sum()
    for i,t in enumerate(z['times']):
        fr=dict(frame_index=i+1,time_sec=float(t),camera_matrix_world=cam['matrix_world'])
        for name,ident in [('figurine',1),('ceramic_cup',3)]:
            present=objects[name]['present']
            fr[name]=dict(present=present,matrix_world=canonical[name][i].tolist()if present else np.eye(4).tolist(),
                visible_pixels=int((masks[i]==ident).sum()),in_camera_view=bool((masks[i]==ident).any()))
            if present:fr[name]['native_matrix_world']=z['rigid_transforms'][i,names.index(name)].tolist()
        fr['curtain']=dict(present=True,deformation_frame_index=i,centre_of_mass_world=com[i].tolist(),
            visible_pixels=int((masks[i]==2).sum()),in_camera_view=bool((masks[i]==2).any()))
        frames.append(fr)
    save(out/'ground_truth_transforms.json',dict(schema_version=1,scene=CASE,fps=24,frame_start=1,frame_end=96,
        physics=dict(resolved_parameters=p,objects=objects),objects=objects,camera=cam,frames=frames,
        rigid_coordinates='COM-centred mesh and reparameterized pose represent exactly the original world geometry; native poses retained.',
        elastic_ground_truth='No fitted rigid-body matrix is used for cloth. Use the full surface cache and instance masks.',
        accepted_benchmark_gt=False,material_calibrated=False))
    save(out/'canonical_coordinate_audit.json',dict(passed=max(coordinate_errors.values(),default=0.)<1e-10,
        max_world_geometry_reparameterization_error_m=coordinate_errors,
        existing_object_position_or_pose_edited=False,scope='Coordinate representation of GT only; simulated and rendered physical states unchanged.'))
    save(out/'deformation_manifest.json',dict(schema_version=1,scene_id=CASE,case_id=case,object_id='curtain',
        cache='cache.npz',cache_sha256=sha(out/'cache.npz'),positions_key='positions',velocities_key='velocities',faces_key='faces',
        rest_positions_key='rest_positions',material_uv_key='uv',times_key='times',vertex_masses_key='vertex_masses',
        shape=list(z['positions'].shape),units='m, s, kg',coordinate_system='world, right handed, Z up',
        instance_masks='instance_masks.npz',instance_id=2,hand_authored_deformation=False,
        material_calibrated=False,numerical_convergence_established=False))
    save(out/'prompts.json',dict(schema_version=1,case_id=case,kind='source'if case=='source'else'edit',
        source_case_id='source',edit_dsl=edit['edit_dsl'],prompts=edit['prompts']))
    if (out/'artifact_manifest.json').exists()and not(out/'private_render_artifact_manifest.json').exists():
        shutil.copy2(out/'artifact_manifest.json',out/'private_render_artifact_manifest.json')
    public=['video.mp4','prompts.json','ground_truth_transforms.json','deformation_manifest.json','cache.npz','cloth.mdd',
        'instance_masks.npz','gt.json','physics_audit.json','simulation_config.json','render_manifest.json',
        'portable_scene_audit.json','camera_calibration.json','encoding_verification.json','canonical_coordinate_audit.json','asset_credits.json','completion.json','execution_provenance.json','solver_log_audit.json','pipeline_completion.json','motion_quality.json']
    public += [p.relative_to(out).as_posix()for p in(out/'geometry').glob('*.npz')]
    if (out/'source_scene_readability.json').is_file():public.append('source_scene_readability.json')
    public=[name for name in public if (out/name).is_file()]   # optional sidecars may be absent
    save(out/'artifact_manifest.json',dict(schema_version=1,video=dict(fps=24,resolution=[1280,720],frames=96,playback_duration_sec=4.),
        distribution_scope='Rendered videos and evaluation sidecars only; private packed Blender scene and marketplace textures excluded.',
        files=[dict(path=name,bytes=(out/name).stat().st_size,sha256=sha(out/name))for name in public]))
