"""Renderer of the accepted delivery: replay of the native states in the packed counter kitchen (run on a GPU worker).

The helpers (apply_physical_skin, replay_audit, skin_topology) are also imported by appearance/realism.py."""
from pathlib import Path
import argparse,hashlib,json,os,socket,sys,time
import numpy as np
CPU='--cpu-audit' in sys.argv or '--cpu-render' in sys.argv
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import optics_native as utils


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,o):Path(p).write_text(json.dumps(o,ensure_ascii=False,indent=2),encoding='utf-8')


def apply_physical_skin(native):
    bag=bpy.data.objects.get('silicone bag native FEM')
    if not bag:return dict(present=False)
    thickness=np.asarray(native['bag_vertex_thickness_m']);assert len(thickness)==len(bag.data.vertices)
    attr=bag.data.attributes.get('physical_silicone_thickness_m') or bag.data.attributes.new('physical_silicone_thickness_m','FLOAT','POINT')
    attr.data.foreach_set('value',thickness.astype(np.float32))
    group=bag.vertex_groups.get('physical wall thickness') or bag.vertex_groups.new(name='physical wall thickness')
    lo=float(thickness.min());hi=float(thickness.max());assert hi>lo>0
    for i,value in enumerate(thickness):group.add([i],float((value-lo)/(hi-lo)),'REPLACE')
    solid=bag.modifiers['declared 1.4 mm shell thickness'];solid.thickness=hi;solid.vertex_group=group.name;solid.thickness_vertex_group=lo/hi
    modified=[]
    for m in bag.data.materials:
        n=m.node_tree.nodes;l=m.node_tree.links
        field=n.get('physical thickness') or n.new('ShaderNodeAttribute');field.name='physical thickness';field.attribute_name=attr.name
        scale=n.get('physical optical depth') or n.new('ShaderNodeMath');scale.name='physical optical depth';scale.operation='MULTIPLY';scale.inputs[1].default_value=-300.
        l.new(field.outputs['Fac'],scale.inputs[0]);count=0
        for node in list(n):
            if node.type=='MATH' and node.operation=='DIVIDE' and not node.inputs[0].is_linked and abs(node.inputs[0].default_value+.42)<1e-5:
                l.new(scale.outputs[0],node.inputs[0]);count+=1
        if count==0:
            count=sum(node.type=='MATH' and node.operation=='DIVIDE' and node.inputs[0].is_linked and node.inputs[0].links[0].from_node==scale for node in n)
        assert count==1,(m.name,count)
        modified.append(m.name)
    return dict(present=True,physical_body_thickness_m=lo,physical_max_handle_thickness_m=hi,
        per_vertex_native_thickness_replayed=True,optical_depth='sigma=600 /m times actual local h; half per boundary',materials=modified)


def replay_audit(native):
    bag=bpy.data.objects.get('silicone bag native FEM');restore=[];worst=0.;rigid=0.
    if bag:
        for m in bag.modifiers:restore.append((m,m.show_viewport));m.show_viewport=False
    try:
        roots=[bpy.data.objects[str(x)+' rigid native transform'] for x in native['rigid_body_ids']]
        for i in range(96):
            bpy.context.scene.frame_set(i+1);bpy.context.view_layer.update()
            if bag:
                obj=bag.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=obj.to_mesh()
                xyz=np.array([tuple(v.co) for v in mesh.vertices]);worst=max(worst,float(np.abs(xyz-native['bag_positions'][i]).max()));obj.to_mesh_clear()
            for j,o in enumerate(roots):rigid=max(rigid,float(np.abs(np.asarray(o.matrix_world)-native['can_transforms'][i,j]).max()))
        assert worst<1e-6 and rigid<1e-5,(worst,rigid)
        return dict(passed=True,checked_states=96,shell_max_coordinate_error_m=worst,rigid_max_matrix_error=rigid,host=socket.gethostname(),native_solver_cache=True)
    finally:
        for m,visible in restore:m.show_viewport=visible


def static_rest_audit():
    import build_details as details
    prepared = json.loads(bpy.context.scene['counter_contact_report'])
    plate = bpy.data.objects['carved fruit plate / carved_wooden_plate']
    support = details.mesh_surface(plate)
    pears = []
    for row in prepared['pear_contacts']:
        obj = bpy.data.objects[row['object']]
        gap = min(details.contact_gaps(obj, support))
        assert 0 <= gap < .0002, (obj.name, gap)
        pears.append(dict(object=obj.name, evaluated_contact_gap_m=gap))
    cloth = bpy.data.objects[prepared['linen']['object']]
    cloth_bottom, cloth_top = utils.evaluated_z_bounds([cloth])
    assert .91 <= cloth_bottom < .9102 and cloth_top < .95
    assert all(mod.type != 'CLOTH' for mod in cloth.modifiers)
    rows = [row for row in json.loads(bpy.context.scene['counter_placements'])
            if row['asset'] != 'food_pears_asian_01']
    for row in rows:
        root = bpy.data.objects[row['object']]
        low, high = utils.evaluated_z_bounds(utils.descendants(root))
        row['evaluated_bottom_m'] = low
        row['evaluated_top_m'] = high
        assert abs(low - row['support_z_m']) < .002, row
        bounds = row['bounds_m']
        assert bounds[0][1] > .065 and bounds[1][1] < .57, row
    return dict(passed=True, contacts=rows, pear_contacts=pears,
                linen_evaluated_bounds_m=[cloth_bottom, cloth_top],
                scope='Shared passive counter dressing')
 
 
def skin_topology():
    bag=bpy.data.objects.get('silicone bag native FEM')
    if not bag:return dict(present=False)
    rows=[]
    for frame in (1,73,96):
        bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
        obj=bag.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=obj.to_mesh();mesh.calc_loop_triangles()
        v=np.asarray([tuple(x.co) for x in mesh.vertices]);f=np.asarray([tuple(x.vertices) for x in mesh.loop_triangles]);tri=v[f]
        volume=float(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()/6)
        edges={}
        for poly in mesh.polygons:
            ids=list(poly.vertices)
            for a,b in zip(ids,ids[1:]+ids[:1]):
                key=tuple(sorted((a,b)));edges[key]=edges.get(key,0)+1
        nonmanifold=sum(c!=2 for c in edges.values());obj.to_mesh_clear()
        assert nonmanifold==0 and volume>0,(frame,nonmanifold,volume)
        rows.append(dict(frame=frame,nonmanifold_edges=nonmanifold,signed_skin_volume_m3=volume))
    return dict(present=True,passed=True,states=rows,cavity='air; no volume shader')


def main():
    assert sys.platform.startswith('linux'), 'Blender runs on a Linux GPU worker'
    assert os.environ.get('CUDA_VISIBLE_DEVICES')=='' if CPU else os.environ.get('CUDA_VISIBLE_DEVICES','').startswith('GPU-')
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--mode',choices=('render','probe','assemble'),default='probe');ap.add_argument('--frames',nargs='+',type=int,default=[7,13,25,73])
    ap.add_argument('--width',type=int,default=1280);ap.add_argument('--samples',type=int,default=256);ap.add_argument('--cpu-audit',action='store_true')
    ap.add_argument('--cpu-render',action='store_true')
    a=ap.parse_args(sys.argv[sys.argv.index('--')+1:]);assert not a.cpu_audit or a.mode!='render'
    start=time.monotonic();a.out.mkdir(parents=True,exist_ok=True);native=np.load(a.source/'simulation.npz')
    template_hash=sha(bpy.data.filepath)
    assert np.array_equal(native['times'],np.arange(97)/24)
    utils.bind_native_cache(native);signature=utils.dynamic_signature();details=apply_physical_skin(native);assert utils.dynamic_signature()==signature
    scene=bpy.context.scene;scene.render.resolution_x=a.width;scene.render.resolution_y=a.width*9//16;scene.render.resolution_percentage=100
    scene.render.fps=24;scene.frame_start=1;scene.frame_end=96;scene.render.use_persistent_data=True;scene.render.use_motion_blur=False
    scene.cycles.device='CPU' if CPU else 'GPU';scene.cycles.samples=a.samples;scene.cycles.seed=731;scene.cycles.use_denoising=True
    scene.cycles.use_adaptive_sampling=True;scene.cycles.adaptive_min_samples=32;scene.cycles.adaptive_threshold=.02
    if CPU:
        scene.cycles.denoiser='OPENIMAGEDENOISE'
        if hasattr(scene.cycles,'denoising_use_gpu'):scene.cycles.denoising_use_gpu=False
    else:
        cp=bpy.context.preferences.addons['cycles'].preferences;cp.compute_device_type='OPTIX';cp.get_devices()
        for d in cp.devices:d.use=d.type=='OPTIX'
        assert any(d.use for d in cp.devices)
    cov=utils.coverage(native);save(a.out/'camera_coverage.json',cov);assert cov['passed'],cov
    save(a.out/'static_contact_audit.json',static_rest_audit());save(a.out/'optics_and_details.json',details)
    audit=replay_audit(native);audit['saved_scene_readback']=False
    if a.mode in ('render','assemble'):
        scene.frame_set(1);bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'scene.blend'),compress=True)
        bpy.ops.wm.open_mainfile(filepath=str(a.out/'scene.blend'),load_ui=False,use_scripts=False);scene=bpy.context.scene
        assert utils.dynamic_signature()==signature
        audit=replay_audit(native);audit.update(saved_scene_readback=True,saved_scene_sha256=sha(a.out/'scene.blend'))
    audit['native_cache_sha256']=sha(a.source/'simulation.npz');save(a.out/'native_replay_audit.json',audit)
    save(a.out/'skin_topology_audit.json',skin_topology())
    context=utils.static_signature();save(a.out/'appearance_invariants.json',dict(native_dynamics_unchanged=True,native_cache_sha256=sha(a.source/'simulation.npz'),
        no_liquid_objects=True,static_context_sha256=context,appearance_revision='counter_look',physical_skin=details,no_hand_animated_details=True))
    frames=list(range(1,97)) if a.mode=='render' else a.frames
    if a.mode!='assemble':
        dest=a.out/'frames';dest.mkdir(exist_ok=True)
        for frame in frames:
            scene.frame_set(frame);scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB';scene.render.image_settings.color_depth='8'
            scene.render.filepath=str(dest/('frame_%04d.png'%frame));bpy.ops.render.render(write_still=True)
    report=dict(status='complete' if a.mode=='render' else a.mode,frames=frames,physical_time_s=native['times'][np.asarray(frames)-1].tolist(),
        width=a.width,height=a.width*9//16,samples=a.samples,host=socket.gethostname(),gpu_uuid=None if CPU else os.environ['CUDA_VISIBLE_DEVICES'],
        cycles_device='CPU' if CPU else 'OPTIX',blender_version=bpy.app.version_string,
        template_sha256=template_hash,cpu_threads=scene.render.threads if CPU else None,
        adaptive_sampling=dict(enabled=True,minimum_samples=32,maximum_samples=a.samples,noise_threshold=.02),
        worker_ip=None,
        camera_matrix=[list(row) for row in scene.camera.matrix_world],camera_lens_mm=scene.camera.data.lens,static_context_sha256=context,
        photography=dict(fstop=scene.camera.data.dof.aperture_fstop,dof=scene.camera.data.dof.use_dof,sensor_width_mm=scene.camera.data.sensor_width,
                         view_transform=scene.view_settings.view_transform,look=scene.view_settings.look,exposure=scene.view_settings.exposure),
        no_liquid_objects=True,local_blender_used=False,appearance_revision='counter_look',native_source=str(a.source),
        optical_model='Reciprocal thin-sheet approximation with actual local physical h; no cavity volume',wall_seconds=time.monotonic()-start)
    save(a.out/('render_report.json' if a.mode=='render' else 'preview_report.json'),report)
    print('COUNTER_REPLAY_COMPLETE',a.mode,flush=True)


if __name__=='__main__':main()
