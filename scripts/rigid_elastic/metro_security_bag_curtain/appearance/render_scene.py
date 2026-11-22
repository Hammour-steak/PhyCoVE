"""Blender replay of the accepted native states into the security-checkpoint scene.

blender -b --factory-startup --python-exit-code 1 --python appearance/render_scene.py --     --case source --out-root DIR [--frames all|0,30,95] [--samples N] [--device GPU|CPU] [--save-blend] [--grounding-audit]

The station, scanner and outfeed geometry is built by scene_environment.build(); the current
look (appearance/realism.py) is applied after the actors exist. Bag poses and curtain vertices
come only from <cache-root>/<case>/states.npz; nothing is animated by hand.
"""
import platform,socket
import bpy,numpy as np,json,hashlib,sys,os,argparse,subprocess,time,math
from pathlib import Path
from mathutils import Vector
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
sys.path[:0]=[str(HERE.parent), str(HERE.parents[2])]
from scene_environment import build,material,micro
from scene_paths import ASSETS, NATIVE, ffmpeg_binary, output_path
ENVIRONMENT_FILES=('scene_environment.py','checkpoint_details.py','detail_refinement.py','monitor_upgrade.py','concourse_return.py','outfeed.py','station_details.py','realism.py')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2),encoding='utf-8')
def actors(p,c):
    curtain=None
    if p['curtain_present'][0]:
        mesh=bpy.data.meshes.new('Physical independent strip shell surfaces');mesh.from_pydata(c['positions'][0].tolist(),[],c['triangles'].tolist());mesh.update()
        curtain=bpy.data.objects.new('exit_curtain',mesh);bpy.context.collection.objects.link(curtain);curtain.pass_index=2
        uv=mesh.uv_layers.new(name='Rest material coordinates')
        for loop in mesh.loops:uv.data[loop.index].uv=c['uv'][loop.vertex_index]
        for k in range(6):
            col=.018+(k%3)*.0015;m=material('Opaque rubber-encapsulated shielding strip %d'%k,(col,col*1.05,col*1.07),.82+(k%2)*.02)
            m.node_tree.nodes.get('Principled BSDF').inputs['Specular IOR Level'].default_value=.22
            micro(m,800,.000045,.14,coordinates='UV');mesh.materials.append(m)
        for poly,tri in zip(mesh.polygons,c['triangles']):poly.material_index=int(c['strip_ids'][tri[0]]);poly.use_smooth=True
        solid=curtain.modifiers.new('Declared physical encapsulated strip thickness','SOLIDIFY');solid.thickness=p['curtain_thickness_m'];solid.offset=0
    bags=[]
    if not c['bag_q'].shape[1]:return curtain,bags   # DELETE bag (bag_present 0): no backpack scan is loaded
    with bpy.data.libraries.load(str(ASSETS/'backpack/prepared.blend'),link=False) as (src,dst):dst.objects=['bag_asset']
    source=dst.objects[0];bpy.context.collection.objects.link(source)
    for m in source.data.materials:
        if m and m.use_nodes:
            micro(m,2600,.000035,.12)
            for n in m.node_tree.nodes:
                if n.type=='BSDF_PRINCIPLED':n.inputs['Sheen Weight'].default_value=.10
    for i in range(c['bag_q'].shape[1]):
        root=bpy.data.objects.new('bag' if i==0 else 'second_bag',None);bpy.context.collection.objects.link(root)
        ob=source if i==0 else source.copy()
        if i:bpy.context.collection.objects.link(ob)
        ob.name='bag_scan' if i==0 else 'second_bag_scan';ob.parent=root;ob.location=(0,0,0);ob.pass_index=1 if i==0 else 3;bags.append(root)
    return curtain,bags
def curtain_shown(c,f):
    """A timed DELETE (states.npz curtain_present_per_frame) removes the curtain from its edit frame on."""
    return 'curtain_present_per_frame' not in c or bool(c['curtain_present_per_frame'][f])
def replay(f,p,c,curtain,bags):
    bpy.context.scene.frame_set(f+1)
    if curtain:
        curtain.hide_render=not curtain_shown(c,f)
    if curtain and not curtain.data.shape_keys:
        curtain.data.vertices.foreach_set('co',c['positions'][f].astype(np.float32).ravel());curtain.data.update()
    for i,o in enumerate(bags):o.location=c['bag_positions'][f,i];o.rotation_euler=c['bag_euler'][f,i]
    bpy.context.view_layer.update()
def native_audit(p,c,curtain,bags,nframes):
    maxq=0.;maxx=0.;maxangle=0.;visibility=0
    if curtain:
        for m in curtain.modifiers:m.show_viewport=False
    for f in range(nframes):
        bpy.context.scene.frame_set(f+1);bpy.context.view_layer.update()
        if curtain and curtain.hide_render==curtain_shown(c,f):visibility+=1
        for i,o in enumerate(bags):
            maxq=max(maxq,(o.matrix_world.translation-Vector(c['bag_positions'][f,i])).length)
            maxangle=max(maxangle,float(np.max(np.abs(np.array(o.rotation_euler)-c['bag_euler'][f,i]))))
        if curtain:
            e=curtain.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=e.to_mesh();v=np.empty(len(mesh.vertices)*3,dtype=np.float32);mesh.vertices.foreach_get('co',v)
            assert len(mesh.vertices)==c['positions'].shape[1]
            maxx=max(maxx,float(np.abs(v.reshape(-1,3)-c['positions'][f]).max()));e.to_mesh_clear()
    if curtain:
        for m in curtain.modifiers:m.show_viewport=True
    result={'frames_checked':nframes,'from_reopened_blend':True,'without_manual_reassignment':True,'max_rigid_position_error_m':maxq,'max_rigid_pitch_error_rad':maxangle,'max_surface_coordinate_error_m':maxx,'curtain_visibility_mismatches':visibility,'passed':maxq<1e-6 and maxangle<1e-6 and maxx<1e-6 and visibility==0}
    assert result['passed'],result
    return result
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',default='source');ap.add_argument('--tag',default='accepted_states');ap.add_argument('--cache-root',type=Path,help='native states root (default assets native/<tag>)');ap.add_argument('--out-root',type=Path,required=True);ap.add_argument('--out-tag',default='preview');ap.add_argument('--frames',default='0,18,30,48,80,143');ap.add_argument('--samples',type=int,default=48);ap.add_argument('--width',type=int,default=1280);ap.add_argument('--save-blend',action='store_true');ap.add_argument('--grounding-audit',dest='grounding_audit',action='store_true');ap.add_argument('--assemble-only',action='store_true')
    ap.add_argument('--backend',choices=('CUDA','OPTIX'),default='OPTIX');ap.add_argument('--device',choices=('GPU','CPU'),default='GPU')
    a=ap.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    out=output_path(a.out_root)/a.case
    if out.exists():raise FileExistsError('Choose a fresh render output: '+str(out))
    gpu=not a.assemble_only and a.device=='GPU'
    if a.assemble_only:
        assert a.save_blend and a.grounding_audit
    if gpu:
        # Make the selected GPU visible to other NVML-based dispatchers before CPU scene preparation.
        warm=bpy.context.scene;warm.render.engine='CYCLES';warm.cycles.device='GPU';warm.cycles.samples=1;warm.render.use_persistent_data=True
        early=bpy.context.preferences.addons['cycles'].preferences;early.compute_device_type=a.backend;early.get_devices()
        for device in early.devices:device.use=device.type==a.backend
        assert any(device.use for device in early.devices),'No bound '+a.backend+' device'
        warm.render.resolution_x=16;warm.render.resolution_y=16;warm.render.resolution_percentage=100
        bpy.ops.render.render(write_still=False)
    source=(a.cache_root or NATIVE.parent/a.tag)/a.case;config=json.loads((source/'simulation_config.json').read_text());p=config['physics'];c=np.load(source/'states.npz');nframes=config['frames_for_video']
    environment=build(p);curtain,bags=actors(p,c);from detail_refinement import refine_bag_materials;refine_bag_materials(bags);from realism import apply as apply_look;look=apply_look(p,c,curtain,bags);s=bpy.context.scene;s.render.engine='CYCLES';s.cycles.device='GPU' if gpu else 'CPU';s.cycles.samples=a.samples;s.cycles.use_denoising=True;s.cycles.denoiser='OPENIMAGEDENOISE';s.cycles.denoising_input_passes='RGB_ALBEDO_NORMAL';s.cycles.adaptive_threshold=look.get('adaptive_threshold',.025);s.cycles.max_bounces=8
    prefs=None
    if gpu:
        prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type=a.backend;prefs.get_devices()
        for d in prefs.devices:d.use=d.type==a.backend
        assert any(d.use for d in prefs.devices),'No '+a.backend+' GPU'
    s.render.resolution_x=a.width;s.render.resolution_y=round(a.width*9/16);s.render.resolution_percentage=100;s.render.fps=24;s.frame_start=1;s.frame_end=nframes
    s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB';s.render.image_settings.color_depth='8';s.render.use_persistent_data=True
    s.view_settings.view_transform='AgX';s.view_settings.look=look.get('view_look','AgX - Medium High Contrast');s.view_settings.exposure=look.get('exposure',-.05)
    out.mkdir(parents=True,exist_ok=False)
    final=a.out_tag.startswith('final')
    if final:s.view_layers[0].use_pass_object_index=True;s.view_layers[0].use_pass_z=True
    s.use_nodes=True;tree=s.node_tree;tree.nodes.clear();rl=tree.nodes.new('CompositorNodeRLayers');co=tree.nodes.new('CompositorNodeComposite')
    from realism import finish;tree.links.new(finish(tree,rl.outputs['Image']),co.inputs['Image'])
    if final:
        for output,folder in (('IndexOB','object_index'),('Depth','depth')):
            n=tree.nodes.new('CompositorNodeOutputFile');n.base_path=str(out/folder);n.format.file_format='OPEN_EXR';n.format.color_mode='BW';n.format.color_depth='32';n.file_slots[0].path='frame_';tree.links.new(rl.outputs[output],n.inputs[0])
    if a.save_blend:
        if curtain:
            curtain.shape_key_add(name='Basis')
            for f in range(nframes):
                key=curtain.shape_key_add(name='Solver frame %03d'%f);key.data.foreach_set('co',c['positions'][f].astype(np.float32).ravel())
                key.value=0.;key.keyframe_insert('value',frame=f);key.value=1.;key.keyframe_insert('value',frame=f+1);key.value=0.;key.keyframe_insert('value',frame=f+2)
            for curve in curtain.data.shape_keys.animation_data.action.fcurves:
                for k in curve.keyframe_points:k.interpolation='LINEAR'
            if 'curtain_present_per_frame' in c:
                for f in range(nframes):curtain.hide_render=not curtain_shown(c,f);curtain.keyframe_insert('hide_render',frame=f+1)
        for f in range(nframes):
            replay(f,p,c,curtain,bags)
            for ob in bags:ob.keyframe_insert('location',frame=f+1);ob.keyframe_insert('rotation_euler',frame=f+1)
        for ob in bags:
            for curve in ob.animation_data.action.fcurves:
                for k in curve.keyframe_points:k.interpolation='LINEAR'
        replay(0,p,c,curtain,bags);bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/'private_scene.blend'),compress=True)
        bpy.ops.wm.open_mainfile(filepath=str(out/'private_scene.blend'),load_ui=False,use_scripts=False);s=bpy.context.scene;curtain=bpy.data.objects.get('exit_curtain');bags=([bpy.data.objects['bag']] if p.get('bag_present',[1])[0] else [])+([bpy.data.objects['second_bag']] if p['second_bag_present'][0] else [])
        save(out/'replay_audit.json',native_audit(p,c,curtain,bags,nframes))
    if a.grounding_audit:
        from audit_grounding import audit
        support=audit();save(out/'support_audit.json',support);assert support['status']=='passed',support
        from audit_scene_reuse import audit as audit_reuse
        reuse=audit_reuse(p,c);save(out/'scene_reuse_audit.json',reuse);assert reuse['status']=='passed',reuse
    frames=list(range(nframes)) if a.frames=='all' else [int(x) for x in a.frames.split(',')]
    cam=s.camera;focal=cam.data.lens/cam.data.sensor_width*s.render.resolution_x
    camera={'matrix_world':[list(row) for row in cam.matrix_world],'lens_mm':cam.data.lens,'sensor_width_mm':cam.data.sensor_width,'width':s.render.resolution_x,'height':s.render.resolution_y,'K':[[focal,0,s.render.resolution_x/2],[0,focal,s.render.resolution_y/2],[0,0,1]]}
    save(out/'render_report.json',{'scene_id':'metro_security_bag_curtain','case_id':a.case,'execution_host':socket.gethostname(),'execution_platform':platform.platform(),'gpu_uuid':os.environ.get('CUDA_VISIBLE_DEVICES'),'early_gpu_context_initialized':gpu,'device':'GPU' if gpu else 'CPU','assembly_only':a.assemble_only,'cycles_devices':[{'name':d.name,'type':d.type,'id':d.id,'use':d.use} for d in prefs.devices] if prefs else [],'blender_version':bpy.app.version_string,'samples':a.samples,'camera':camera,'frames':frames,'simulation_cache_sha256':sha(source/'states.npz'),'environment_refinement':environment['refinement'],'visual_revision':look.get('look','current'),'look':look,'physics_generation':'v9 recomputed planar-rigid/strip-shell dynamics','timed_edits':config.get('timed_edits'),'bag_asset':'4K textured backpack scan, original UVs, common prepared baseline geometry','prepared_geometry_sha256':sha(ASSETS/'backpack/prepared_geometry.npz'),'missing_images':[im.filepath for im in bpy.data.images if im.source=='FILE' and im.size[0]>0 and not im.packed_file and not Path(bpy.path.abspath(im.filepath)).exists()]})
    if a.assemble_only:
        return
    for f in frames:
        target=out/('frame_%04d.png'%f)
        if target.exists():continue
        replay(f,p,c,curtain,bags);s.render.filepath=str(target);start=time.monotonic();bpy.ops.render.render(write_still=True);print(json.dumps({'frame':f,'wall_s':time.monotonic()-start,'case':a.case}),flush=True)
    if a.frames=='all':
        ffmpeg=ffmpeg_binary()
        subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-y','-framerate','24','-i',str(out/'frame_%04d.png'),'-frames:v',str(nframes),'-c:v','libx264','-threads','4','-preset','slow','-crf','16','-pix_fmt','yuv420p','-movflags','+faststart',str(out/'video.mp4')],check=True)
        save(out/'encoding_receipt.json',{'video_sha256':sha(out/'video.mp4'),'encoder':'CPU ffmpeg/libx264 CRF16','ffmpeg_binary_sha256':sha(ffmpeg),'input_state_sha256':sha(source/'states.npz'),'frames':nframes,'fps':24})
    print(json.dumps({'completed':a.case,'output':str(out)}),flush=True)
if __name__=='__main__':main()
