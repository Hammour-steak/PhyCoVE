"""Blender CPU-only finalization of one rendered case: H.264 video, masks, portable replay scene, GT sidecars.

Run after render_curtain_doraemon_drape.py on a Linux host:
    blender -b --factory-startup --python tools/finalize_remote.py -- --case CASE --simulation SIM --render RENDER --out OUT
No rendering, simulation or image edits.
"""

from pathlib import Path
import argparse,json,os,shutil,socket,struct,subprocess,sys
sys.dont_write_bytecode=True   # Blender ignores PYTHONDONTWRITEBYTECODE; keep scripts/ free of __pycache__
if sys.platform != 'linux':
    raise RuntimeError('Finalize on a Linux host')
import bpy
import numpy as np
from mathutils import Matrix
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
sys.path.insert(0,str(next(p for p in HERE.parents if p.name=='scripts')))
from pcve_media_contract import require_video,require_times
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'physics'))
from baseline import RUNTIME,CASE,save,sha

def main():
    assert os.name!='nt'
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--simulation',type=Path,required=True)
    ap.add_argument('--render',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args(sys.argv[sys.argv.index('--')+1:]);out=a.out;out.mkdir(parents=True,exist_ok=True)
    frames=sorted((a.render/'rgb').glob('*.png'))
    if len(frames)!=96 or[p.name for p in frames]!=[f'{i:04d}.png'for i in range(1,97)]:raise RuntimeError('Incomplete 96-frame replay')
    z=np.load(a.simulation/'cache.npz');positions=z['positions'];names=list(z['rigid_names'])
    require_times(z['times'].tolist())
    rm=json.loads((a.render/'scene_manifest.json').read_text());rc=json.loads((a.render/'render_completion.json').read_text())
    if 'camera' in rm:   # calibration of the fixed camera recorded by appearance/render.py
        cam=rm['camera'];M=np.array(cam['matrix_world'],float);w,h=rm['resolution'];f=cam['lens_mm']/cam['sensor_width_mm']*w
        save(out/'camera_calibration.json',dict(object_name='Fixed camera',lens_mm=cam['lens_mm'],sensor_width_mm=cam['sensor_width_mm'],
            sensor_fit=cam['sensor_fit'],resolution=[w,h],pixel_aspect=[1.,1.],K=[[f,0,w/2],[0,f,h/2],[0,0,1]],matrix_world=cam['matrix_world'],
            world_to_camera_opencv=(np.diag([1.,-1.,-1.,1.])@np.linalg.inv(M)).tolist(),shift=cam['shift'],
            convention='Blender camera looks along local -Z with local +Y up; OpenCV transform uses +Z forward and +Y down.',
            thin_lens_depth_of_field=True,aperture_fstop=cam['fstop'],focus_distance_m=cam['focus_distance_m']))
    cachehash=sha(a.simulation/'cache.npz')
    if cachehash!=rm['simulation_cache_sha256']or cachehash!=rc['cache_sha256']:raise RuntimeError('Render is bound to another cache')
    if rm['resolution']!=[1280,720]or rc['frames']!=list(range(1,97)):raise RuntimeError('Render format mismatch')
    ffmpeg=RUNTIME/'runtime/tools/ffmpeg-linux'
    if not ffmpeg.is_file():ffmpeg=Path(shutil.which('ffmpeg'))
    subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-y','-framerate','24','-start_number','1',
        '-i',str(a.render/'rgb/%04d.png'),'-frames:v','96','-an','-c:v','libx264','-threads','4','-crf','17',
        '-preset','slow','-pix_fmt','yuv420p','-movflags','+faststart',str(out/'video.mp4')],check=True)
    canonical_media=require_video(out/'video.mp4')
    verify=subprocess.check_output([str(ffmpeg),'-v','error','-i',str(out/'video.mp4'),'-threads','2','-f','framemd5','-'],text=True)
    rows=[line for line in verify.splitlines()if line and not line.startswith('#')]
    if len(rows)!=96 or'#dimensions 0: 1280x720'not in verify:raise RuntimeError('Decoded video verification failed')
    (out/'decoded_frames.framemd5').write_text(verify)
    masks=[]
    for frame in range(1,97):
        image=bpy.data.images.load(str(a.render/'ids'/f'instance_{frame:04d}.exr'),check_existing=False)
        image.colorspace_settings.name='Non-Color';w,h=image.size
        values=np.empty(w*h*4,np.float32);image.pixels.foreach_get(values)
        values=np.flipud(values.reshape(h,w,4)[:,:,0]).copy()
        if(w,h)!=(1280,720)or np.max(abs(values-np.round(values)))>1e-4:raise RuntimeError('Invalid object-index pass')
        masks.append(np.round(values).astype(np.uint8));bpy.data.images.remove(image)
    masks=np.asarray(masks)
    np.savez_compressed(out/'instance_masks.npz',masks=masks,times=z['times'],ids=np.array([0,1,2,3]),
        labels=np.array(['environment','figurine','curtain','ceramic_cup']))
    if a.case=='source':
        first_pixels=int((masks[0]==1).sum());last_pixels=int((masks[-1]==1).sum())
        coverage=1.-last_pixels/max(1,first_pixels)
        readable=dict(initial_figure_pixels=first_pixels,final_figure_pixels=last_pixels,
            figure_coverage_fraction=coverage,final_cloth_pixels=int((masks[-1]==2).sum()),
            final_native_cloth_max_height_m=float(positions[-1,:,2].max()),manual_visual_review_pending=True)
        readable['passed']=first_pixels>=1000 and coverage>=.5 and readable['final_cloth_pixels']>=1000 and readable['final_native_cloth_max_height_m']>.2
        save(out/'source_scene_readability.json',readable)
        if not readable['passed']:print('WARNING source drape readability check failed: '+str(readable),flush=True)
    objects={};rigid_replay_error={}
    for name in ['figurine','ceramic_cup']:
        if name not in names:continue
        transforms=z['rigid_transforms'][:,names.index(name)]
        quats=[list(Matrix(T.tolist()).to_quaternion())for T in transforms]
        objects[name]=dict(material_class='rigid',native_transform=transforms.tolist(),
            position_m=transforms[:,:3,3].tolist(),quaternion_wxyz=quats,
            pose_origin='Original native collision geometry coordinate origin; not a claim of measured centre of mass.')
    objects['curtain']=dict(material_class='elastic_thin_woven_shell',surface_cache='cache.npz',positions_key='positions',
        faces_key='faces',uv_key='uv',mdd='cloth.mdd',hand_authored_motion=False)
    save(out/'gt.json',dict(schema_version=3,scene_id=CASE,case_id=a.case,fps=24,times_s=z['times'].tolist(),
        coordinates='Right handed Z up, SI metres kilograms seconds',objects=objects))
    with(out/'cloth.mdd').open('wb')as stream:
        stream.write(struct.pack('>2i',len(positions),positions.shape[1]))
        stream.write(z['times'].astype('>f4').tobytes());stream.write(positions.astype('>f4').tobytes())
    # A directly playable .blend, with a relative MDD plus keys from native
    # rigid transforms. No fitted or manually authored physical motion.
    bpy.ops.wm.open_mainfile(filepath=str(a.render/'scene.blend'),load_ui=False,use_scripts=False)
    curtain=bpy.data.objects['CURTAIN exact native thin shell'];bpy.context.view_layer.objects.active=curtain
    cache=next((m for m in curtain.modifiers if m.type=='MESH_CACHE'),None)  # appearance/render.py already drives the cloth by MDD
    if cache is None:cache=curtain.modifiers.new('Native exact vertex cache','MESH_CACHE');cache.cache_format='MDD'
    cache.filepath=str((out/'cloth.mdd').resolve());cache.frame_start=1.;cache.frame_scale=1.;cache.interpolation='LINEAR'
    while curtain.modifiers.find(cache.name)>0:bpy.ops.object.modifier_move_up(modifier=cache.name)
    for name,label in [('figurine','FIGURINE native rigid transform'),('ceramic_cup','Added glazed ceramic tumbler')]:
        if name not in names:continue
        root=bpy.data.objects[label];root.rotation_mode='QUATERNION';errors=[]
        for frame,T in enumerate(z['rigid_transforms'][:,names.index(name)],1):
            loc,rot,scale=Matrix(T.tolist()).decompose();root.location=loc;root.rotation_quaternion=rot;root.scale=scale
            for prop in ['location','rotation_quaternion','scale']:root.keyframe_insert(prop,frame=frame)
            replay=np.asarray(Matrix.LocRotScale(loc,rot,scale));errors.append(float(abs(replay-T).max()))
        if root.animation_data and root.animation_data.action:
            for fc in root.animation_data.action.fcurves:
                for kp in fc.keyframe_points:kp.interpolation='LINEAR'
        rigid_replay_error[name]=max(errors)
    for node in (bpy.context.scene.node_tree.nodes if bpy.context.scene.node_tree else []):
        if node.type=='OUTPUT_FILE':node.base_path='//ids'   # no render-worker path inside the portable scene
    bpy.context.scene.frame_set(1);bpy.ops.file.pack_all();cache.filepath='//cloth.mdd'
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'),relative_remap=False)
    for name in ['cache.npz','simulation_config.json','completion.json','telemetry.npz']:
        shutil.copy2(a.simulation/name,out/name)
    for name in ['scene_manifest.json','render_completion.json']:
        shutil.copy2(a.render/name,out/('render_manifest.json'if name=='scene_manifest.json'else name))
    (out/'thumbnails').mkdir(exist_ok=True)
    for frame in [1,11,16,24,48,72,96]:shutil.copy2(a.render/'rgb'/f'{frame:04d}.png',out/'thumbnails'/f'{frame:04d}.png')
    save(out/'encoding_verification.json',dict(video_sha256=sha(out/'video.mp4'),decoded_frames=96,fps=24,
        resolution=[1280,720],duration_s=4.,canonical_media_contract_verified=True,masks_shape=list(masks.shape),native_cache_sha256=cachehash,
        worker_host=socket.gethostname(),ffmpeg_sha256=sha(ffmpeg),rigid_scene_replay_max_matrix_error=rigid_replay_error,
        mdd_max_float32_roundoff_m=float(abs(positions-positions.astype(np.float32).astype(float)).max())))
    save(out/'artifact_manifest.json',dict(files=[dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=sha(p))
        for p in sorted(out.rglob('*'))if p.is_file()and p.name!='artifact_manifest.json']))
    print('FINALIZED',a.case,'video bytes',(out/'video.mp4').stat().st_size,flush=True)

if __name__=='__main__':main()
