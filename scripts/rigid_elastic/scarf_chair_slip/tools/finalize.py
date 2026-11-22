"""Remote CPU export of H.264, portable native replay and explicit provenance."""
from pathlib import Path
import argparse,json,os,shutil,socket,struct,subprocess,sys
import bpy,numpy as np
from mathutils import Matrix,Vector
HERE=Path(__file__).resolve().parent;SCENE=HERE.parent;sys.path[:0]=[str(SCENE/"physics"),str(SCENE/"appearance")]
from common import CASE,RUNTIME,WORK,save,sha
sys.path.insert(0,str(next(p for p in HERE.parents if p.name=='scripts')))
from pcve_media_contract import CONTRACT,require_video,require_times

def main():
    assert os.name!='nt'
    ap=argparse.ArgumentParser();ap.add_argument('--simulation',type=Path,required=True);ap.add_argument('--render',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args(sys.argv[sys.argv.index('--')+1:]);out=a.out;out.mkdir(parents=True,exist_ok=True)
    c=np.load(a.simulation/'cache.npz');require_times(c['times']);x=c['positions'];uv=c['uv'];names=list(c['rigid_names']);N=len(x)
    cfg=json.loads((a.simulation/'simulation_config.json').read_text());rm=json.loads((a.render/'render_manifest.json').read_text());done=json.loads((a.render/'render_completion.json').read_text())
    if done['frames']!=list(range(1,N+1))or rm['simulation_cache_sha256']!=sha(a.simulation/'cache.npz'):raise RuntimeError('Incomplete or mismatched render')
    frames=sorted((a.render/'rgb').glob('*.png'))
    if [p.name for p in frames]!=[f'{i:04d}.png'for i in range(1,N+1)]:raise RuntimeError('Missing RGB frame')
    ffmpeg=RUNTIME/'tools/ffmpeg-linux'
    if not ffmpeg.is_file():ffmpeg=Path(shutil.which('ffmpeg'))
    subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-y','-framerate','24','-start_number','1','-i',str(a.render/'rgb/%04d.png'),
        '-frames:v',str(N),'-an','-c:v','libx264','-threads','4','-crf','17','-preset','slow','-pix_fmt','yuv420p','-movflags','+faststart',str(out/'video.mp4')],check=True)
    decoded=subprocess.check_output([str(ffmpeg),'-v','error','-i',str(out/'video.mp4'),'-threads','2','-f','framemd5','-'],text=True)
    rows=[line for line in decoded.splitlines()if line and not line.startswith('#')]
    if len(rows)!=N:raise RuntimeError('Video decode count mismatch')
    media_observed=require_video(out/'video.mp4')
    save(out/'media_contract_check.json',dict(passed=True,contract=CONTRACT,observed=media_observed,native_times_verified=True,full_video_decoded=True))
    (out/'decoded_frames.framemd5').write_text(decoded)
    for name in ['cache.npz','simulation_config.json','completion.json','physics_audit.json','telemetry.npz']:
        shutil.copy2(a.simulation/name,out/name)
    for name in ['render_manifest.json','render_completion.json']:shutil.copy2(a.render/name,out/name)
    provenance=out/'provenance';provenance.mkdir(exist_ok=True)
    snapshot=provenance/'source_snapshot';snapshot.mkdir(exist_ok=True)
    for name in ['simulate.py','common.py','edit_vocab.py','worker.py']:
        if(a.simulation/'source_snapshot'/name).is_file():shutil.copy2(a.simulation/'source_snapshot'/name,snapshot/name)
    for phase in ['native','cycles','audit','finalize']:
        revision=a.render.parent.name if phase in ['cycles','finalize']else a.simulation.parent.name
        receipt=WORK/'receipts'/f'{revision}_{cfg["case_id"]}_{phase}_launch.json'
        if receipt.is_file():shutil.copy2(receipt,provenance/receipt.name)
    for name in ['render_replay.py','optics.py','room.py','scarf_material.py']:shutil.copy2(SCENE/'appearance'/name,provenance/name)
    for name in ['install_manifest_py029.json','active_solver_path.txt']:
        path=RUNTIME/'solver'/name
        if path.is_file():shutil.copy2(path,provenance/name)
    with(out/'cloth.mdd').open('wb')as f:
        f.write(struct.pack('>2i',N,x.shape[1]));f.write(c['times'].astype('>f4').tobytes());f.write(x.astype('>f4').tobytes())
    bpy.ops.wm.open_mainfile(filepath=str(a.render/'scene.blend'),load_ui=False,use_scripts=False)
    cloth=bpy.data.objects['Cotton scarf / exact native shell'];bpy.context.view_layer.objects.active=cloth
    cache=cloth.modifiers.new('Exact native recorded cloth','MESH_CACHE');cache.cache_format='MDD';cache.filepath=str((out/'cloth.mdd').resolve())
    cache.frame_start=1.;cache.frame_scale=1.;cache.interpolation='LINEAR'
    for i in range(len(cloth.modifiers)-1):bpy.ops.object.modifier_move_up(modifier=cache.name)
    rigid_replay={}
    for name,label in [('chair','prepared transform'),('landing_book','Hardcover book transform')]:
        if name not in names:continue
        ob=bpy.data.objects[label];ob.rotation_mode='QUATERNION';errors=[]
        for i,T in enumerate(c['rigid_transforms'][:,names.index(name)]):
            loc,rot,scale=Matrix(T.tolist()).decompose();ob.location=loc;ob.rotation_quaternion=rot;ob.scale=scale
            for prop in ['location','rotation_quaternion','scale']:ob.keyframe_insert(prop,frame=i+1)
            errors.append(float(np.abs(np.asarray(Matrix.LocRotScale(loc,rot,scale))-T).max()))
        rigid_replay[name]=max(errors)
    # The edge threads are optical only but their motion follows native vertices.
    nx,ny=cfg['grid'];seams=[o for o in bpy.data.objects if o.name.startswith('Woven selvedge')]
    fringes=[o for o in bpy.data.objects if o.name.startswith('Short cotton fringe')]
    # Blender suffixes are sorted by creation order for these <=100 curves.
    def order(o):return int(o.name.rsplit('.',1)[1])if o.name.rsplit('.',1)[-1].isdigit()else 0
    seams.sort(key=order);fringes.sort(key=order)
    for i in range(N):
        for ob,idx in zip(seams,[np.arange(ny),np.arange((nx-1)*ny,nx*ny)]):
            for pt,v in zip(ob.data.splines[0].points,x[i][idx]):pt.co=(*v,1);pt.keyframe_insert(data_path='co',frame=i+1)
        for ob,(end,j) in zip(fringes,[(end,j)for end in [0,ny-1]for j in range(nx)]):
            idx=j*ny+end;other=idx+(1 if end==0 else -1);d=x[i,idx]-x[i,other];d/=max(np.linalg.norm(d),1e-12)
            for pt,v in zip(ob.data.splines[0].points,[x[i,idx],x[i,idx]+d*.007]):pt.co=(*v,1);pt.keyframe_insert(data_path='co',frame=i+1)
    scene=bpy.context.scene;scene.frame_start=1;scene.frame_end=N;scene.frame_set(1)
    cache.filepath='//cloth.mdd';bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'),relative_remap=False)
    # Reopen, evaluate the delivered scene with scripts disabled and compare to native mid-surface.
    bpy.ops.wm.open_mainfile(filepath=str(out/'scene.blend'),load_ui=False,use_scripts=False)
    ob=bpy.data.objects['Cotton scarf / exact native shell'];errors=[]
    for frame in [1,7,13,25,49,73,N]:
        bpy.context.scene.frame_set(frame);dg=bpy.context.evaluated_depsgraph_get();dg.update();eo=ob.evaluated_get(dg);mesh=eo.to_mesh()
        pts=np.asarray([v.co[:]for v in mesh.vertices]);n=x.shape[1]
        if len(pts)!=2*n:raise RuntimeError('Unexpected solidify topology')
        error=float(np.linalg.norm((pts[:n]+pts[n:])/2-x[frame-1],axis=1).max());errors.append(dict(frame=frame,error_m=error));eo.to_mesh_clear()
    if max(r['error_m']for r in errors)>3e-6:raise RuntimeError('Portable native replay mismatch')
    cam=bpy.context.scene.camera
    save(out/'camera_calibration.json',dict(lens_mm=cam.data.lens,sensor_width_mm=cam.data.sensor_width,
        resolution=rm['resolution'],matrix_world=np.asarray(cam.matrix_world).tolist(),
        world_to_camera_opencv=(np.diag([1.,-1.,-1.,1.])@np.asarray(cam.matrix_world.inverted())).tolist()))
    background=[]
    for name in ['Bed base','Linen mattress','Bed headboard','Pillow']:
        ob=bpy.data.objects[name];points=np.asarray([ob.matrix_world@Vector(p)for p in ob.bound_box])
        background.append(dict(name=name,min_world_m=points.min(0).tolist(),max_world_m=points.max(0).tolist()))
    save(out/'static_background_bounds.json',dict(source_scene_sha256=sha(out/'scene.blend'),objects=background,scope='Actual static bed object bounds for conservative visibility checks.'))
    save(out/'gt.json',dict(scene_id=CASE,case_id=cfg['case_id'],units='SI metres kilograms seconds; Z up',fps=24,times_s=c['times'].tolist(),
        cloth_surface=dict(cache='cache.npz',positions='positions',velocities='velocities',faces='faces',uv='uv',mdd='cloth.mdd'),
        rigid_names=names,rigid_transforms=c['rigid_transforms'].tolist(),experimental_ground_truth_validated=False))
    (out/'thumbnails').mkdir(exist_ok=True)
    for frame in [1,7,13,25,49,73,N]:
        source=a.render/'rgb'/f'{frame:04d}.png'
        shutil.copy2(source,out/'thumbnails'/f'{frame:04d}.png')
        subprocess.run([str(ffmpeg),'-v','error','-y','-i',str(source),'-frames:v','1','-q:v','2',str(out/'thumbnails'/f'{frame:04d}.jpg')],check=True)
    save(out/'encoding_verification.json',dict(decoded_frames=N,fps=24,resolution=rm['resolution'],duration_s=N/24,
        video_sha256=sha(out/'video.mp4'),ffmpeg_sha256=sha(ffmpeg),worker_host=socket.gethostname()))
    save(out/'portable_scene_audit.json',dict(passed=True,sampled_mid_surface_errors=errors,rigid_matrix_decomposition_max_error=rigid_replay,
        blender_version=bpy.app.version_string,worker_host=socket.gethostname(),scene_sha256=sha(out/'scene.blend'),cache_sha256=sha(out/'cache.npz')))
    save(out/'artifact_manifest.json',dict(files=[dict(path=p.relative_to(out).as_posix())if p.suffix=='.json'else dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=sha(p))for p in sorted(out.rglob('*'))if p.is_file()and p.name!='artifact_manifest.json']))
    print('FINALIZED',cfg['case_id'],flush=True)
if __name__=='__main__':main()
