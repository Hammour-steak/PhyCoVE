"""Replay native gym states in the unchanged, fully packed accepted environment."""
from pathlib import Path
import argparse,hashlib,json,os,sys
import bpy
import numpy as np
from mathutils import Matrix


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb')as stream:
        for block in iter(lambda:stream.read(1<<20),b''):digest.update(block)
    return digest.hexdigest()


def save(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def seam_states(cache,grid):
    nx,ny,nz=grid;lookup={int(v):i for i,v in enumerate(cache['cover_volume_vertex_ids'])}
    perimeter=([(i,0)for i in range(nx)]+[(nx-1,j)for j in range(1,ny)]+
               [(i,ny-1)for i in range(nx-2,-1,-1)]+[(0,j)for j in range(ny-2,0,-1)])
    ids=[lookup[(i*ny+j)*nz+nz-1]for i,j in perimeter]
    positions=cache['cloth_positions'][:,ids].copy();positions[:,:,2]+=.00055
    return np.concatenate([positions+np.array([0,0,side*.00055])for side in [-1,1]],axis=1)


def handle_states(cache):
    # Identical sewn-webbing definition to the accepted renderer. The attachment
    # frame follows three actual simulated shell vertices, without amplification.
    rest=cache['cloth_rest_positions'];positions=cache['cloth_positions'];result=[]
    for side in [-1,1]:
        for centre in [-.30,.30]:
            picks=[np.argmin(np.linalg.norm(rest-np.array([centre+dx,side*.394,z]),axis=1))
                   for dx,z in [(-.060,.070),(.060,.070),(-.060,.100)]]
            a,b,up=positions[:,picks[0]],positions[:,picks[1]],positions[:,picks[2]]
            tangent=b-a;tangent/=np.linalg.norm(tangent,axis=1)[:,None]
            vertical=up-a;vertical-=tangent*(vertical*tangent).sum(1)[:,None]
            vertical/=np.linalg.norm(vertical,axis=1)[:,None];normal=np.cross(tangent,vertical)*(-side)
            vertices=[]
            for t in np.linspace(0,1,21):
                mid=(1-t)*a+t*b+normal*(.004+.025*np.sin(np.pi*t))-vertical*(.016*np.sin(np.pi*t))
                for sign in [-1,1]:vertices.append(mid+vertical*(sign*.007))
            result.append(np.stack(vertices,axis=1))
    return result


def main(overlay=None):
    """overlay(scene,args,cache), if given, restyles the scene after the camera and static matrices are recorded."""
    if not os.environ.get('CUDA_VISIBLE_DEVICES','').startswith('GPU-'):
        raise RuntimeError('Bind the selected idle GPU by UUID before starting Blender')
    parser=argparse.ArgumentParser()
    parser.add_argument('--scene',type=Path,required=True)
    parser.add_argument('--reference-main',type=Path,required=True)
    parser.add_argument('--simulation',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=192)
    parser.add_argument('--still-frame',type=int)
    parser.add_argument('--frame-start',type=int,default=1)
    parser.add_argument('--frame-end',type=int,default=96)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    out=args.out;out.mkdir(parents=True,exist_ok=True)
    for name in ['frames','deformation']:(out/name).mkdir(exist_ok=True)
    config=json.loads((args.simulation/'simulation_config.json').read_text())
    report=json.loads((args.simulation/'simulation_report.json').read_text())
    with np.load(args.simulation/'cache.npz')as archive:cache={k:archive[k]for k in archive.files}
    assert config['scene_id']=='gym_landing_mat' and len(cache['times'])==96
    assert config['simulation']['fps']==24 and config['simulation']['duration']==4.
    bpy.ops.wm.open_mainfile(filepath=str(args.scene),load_ui=False)
    scene=bpy.context.scene
    bpy.app.handlers.frame_change_pre.clear();bpy.app.handlers.frame_change_post.clear()
    original_camera=np.asarray(scene.camera.matrix_world).copy()
    static={o.name:np.asarray(o.matrix_world).copy()for o in scene.objects if o.pass_index==0}
    if overlay is not None:overlay(scene,args,cache)
    body=bpy.data.objects['medicine_ball'];body.animation_data_clear()
    body.hide_render=not bool(config['physics']['active'][0])
    body_vertices=np.asarray([vertex.co[:]for vertex in body.data.vertices])
    body_faces=np.asarray([face.vertices[:]for face in body.data.polygons])
    assert np.array_equal(body_faces,cache['body_faces'])
    rigid_geometry_error=float(np.max(abs(body_vertices-cache['body_vertices'])))
    assert rigid_geometry_error<1e-7,'Packed rigid surface differs from the physical contact mesh'
    obstacle=None
    if bool(cache['path_obstacle_present'][0]):
        obstacle=bpy.data.objects['gym_water_bottle'];obstacle.animation_data_clear()
    cloth=bpy.data.objects['gym_landing_mat | actual physical surface']
    # Presence of the landing mat (physics active[1]; DELETE landing_mat): absent, the cover, its piping and the
    # four handles are not rendered (no shadow or reflection either) and nothing is replayed onto them.
    mat_present=bool(config['physics']['active'][1])
    handles=sorted([o for o in scene.objects if o.name.startswith('Stitched carry handle')],key=lambda o:o.name)
    assert len(handles)==4
    if mat_present:
        assert len(cloth.data.vertices)==cache['cloth_positions'].shape[1]
        faces=np.asarray([p.vertices[:]for p in cloth.data.polygons])
        assert np.array_equal(faces,cache['cloth_faces'])
        animated=[(cloth,cache['cloth_positions']),
                  (bpy.data.objects['Sewn white cover piping'],seam_states(cache,config['simulation']['solid_grid']))]
        animated.extend(zip(handles,handle_states(cache)))
    else:
        assert cache['cloth_positions'].shape[1]==0 and cache['solid_positions'].shape[1]==0
        animated=[]
        for ob in [cloth,bpy.data.objects['Sewn white cover piping'],*handles]:
            ob.animation_data_clear();ob.hide_render=True;ob.hide_viewport=True
    for ob,positions in animated:
        ob.animation_data_clear()
        if ob.data.shape_keys:ob.shape_key_clear()
        assert len(ob.data.vertices)==positions.shape[1]
    scene.render.engine='CYCLES';scene.cycles.device='GPU';scene.cycles.samples=args.samples
    scene.cycles.use_denoising=True;scene.cycles.seed=20261014;scene.cycles.use_animated_seed=False
    scene.cycles.adaptive_threshold=.004;scene.cycles.max_bounces=10;scene.cycles.transparent_max_bounces=32
    pref=bpy.context.preferences.addons['cycles'].preferences;pref.compute_device_type='OPTIX';pref.get_devices()
    for device in pref.devices:device.use=device.type=='OPTIX'
    if not any(device.use for device in pref.devices):raise RuntimeError('No OptiX GPU available')
    scene.render.resolution_x=1280;scene.render.resolution_y=720;scene.render.resolution_percentage=100
    scene.render.fps=24;scene.frame_start=1;scene.frame_end=96;scene.render.use_motion_blur=False
    scene.render.use_persistent_data=True;scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
    for node in scene.node_tree.nodes:
        if node.type=='OUTPUT_FILE':node.base_path=str(out/'masks_raw')
    errors=[]
    def update(frame):
        scene.frame_set(frame);i=frame-1
        for ob,positions in animated:
            ob.data.vertices.foreach_set('co',positions[i].astype(np.float32).reshape(-1));ob.data.update()
        body.matrix_world=Matrix(cache['body_transforms'][i].tolist())
        if obstacle:obstacle.matrix_world=Matrix(cache['obstacle_transforms'][i].tolist())
        bpy.context.view_layer.update()
        if mat_present:
            result=np.empty_like(cache['cloth_positions'][i]);cloth.data.vertices.foreach_get('co',result.reshape(-1))
            errors.append(float(np.max(abs(result-cache['cloth_positions'][i]))))
        else:errors.append(0.)
        assert np.array_equal(np.asarray(scene.camera.matrix_world),original_camera)
        assert all(np.array_equal(np.asarray(bpy.data.objects[name].matrix_world),matrix)for name,matrix in static.items())
    for frame in sorted({1,int(report['peak_frame']),96}):update(frame)
    if max(errors)>2e-6:raise RuntimeError('Surface replay differs from native states')
    gt=json.loads((args.reference_main/'ground_truth_transforms.json').read_text())
    assert np.max(abs(np.asarray(gt['camera']['matrix_world'])-original_camera))<1e-6
    gt['frames']=[];gt['objects']['medicine_ball']['mass']=config['physics']['body_mass']
    gt['objects']['medicine_ball']['present']=bool(config['physics']['active'][0])
    gt['objects']['landing_mat']['present']=mat_present
    for i,t in enumerate(cache['times']):
        gt['frames'].append(dict(frame_index=i+1,time_sec=float(t),camera_matrix_world=original_camera.tolist(),objects={
            'medicine_ball':dict(present=bool(config['physics']['active'][0]),matrix_world=cache['body_transforms'][i].tolist(),
                                 location=cache['body_transforms'][i,:3,3].tolist(),linear_velocity=cache['body_velocities'][i,:3,3].tolist()),
            'landing_mat':dict(present=mat_present,deformable=True,deformation_frame_index=i,matrix_world=np.eye(4).tolist())}))
        if obstacle:gt['frames'][-1]['objects']['gym_water_bottle']=dict(present=True,deformable=False,
            matrix_world=cache['obstacle_transforms'][i].tolist(),location=cache['obstacle_transforms'][i,:3,3].tolist(),
            linear_velocity=cache['obstacle_velocities'][i,:3,3].tolist())
    save(out/'ground_truth_transforms.json',gt)
    np.savez_compressed(out/'deformation/surface.npz',positions=cache['cloth_positions'],rest_positions=cache['cloth_rest_positions'],faces=cache['cloth_faces'],times=cache['times'])
    rr=dict(scene_id='gym_landing_mat',case=config['case'],status='rendered',fps=24,resolution=[1280,720],samples=args.samples,
            peak_frame=report['peak_frame'],peak_depression_m=report['peak_depression_m'],max_surface_replay_error_m=max(errors),
            physics_cache_sha256=sha(args.simulation/'cache.npz'),release_status=config['release_status'],
            surface_amplification=1.,camera=gt['camera'],packed_reference_scene_sha256=sha(args.scene),
            fixed_environment_and_camera_identical=True,cosmetic_seam_and_handles='Original definitions attached to native shell vertices',
            max_rigid_geometry_replay_error_m=rigid_geometry_error,
            render_settings=dict(adaptive_threshold=.004,denoising=True,aperture_fstop=scene.camera.data.dof.aperture_fstop,
                                 focus_distance_m=scene.camera.data.dof.focus_distance,motion_blur=False),
            worker_host=os.uname().nodename,gpu_uuid=os.environ['CUDA_VISIBLE_DEVICES'],remote_blender_only=True,
            source_shape_key_animation_removed=True)
    save(out/'render_report.json',rr);save(out/'simulation_config.json',config);save(out/'simulation_report.json',report)
    save(out/'prompts.json',dict(kind='edit'if config['edit']else'source',**config['edit']))
    (out/'environment_manifest.json').write_bytes((args.reference_main/'environment_manifest.json').read_bytes())
    for path in args.simulation.glob('source_*'):(out/path.name).write_bytes(path.read_bytes())
    # The production render calls update explicitly. Saving a geometry snapshot
    # must not claim that a Python closure survives a reload of the .blend.
    update(1);bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'),compress=True)
    selected=[args.still_frame]if args.still_frame else range(args.frame_start,args.frame_end+1)
    for frame in selected:
        if not 1<=frame<=96:raise ValueError('Frame outside the four-second output')
        update(frame);scene.render.filepath=str(out/'frames'/f'{frame:04d}.png')
        bpy.ops.render.render(write_still=True);print('FRAME_COMPLETE',frame,flush=True)
    rr['rendered_frames']=list(selected);rr['max_surface_replay_error_m']=max(errors)
    save(out/'render_report.json',rr)


if __name__=='__main__':main()
