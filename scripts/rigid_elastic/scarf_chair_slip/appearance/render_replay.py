"""Renderer of the accepted delivery (remote Cycles scene); every moving primary surface replays native state."""
from pathlib import Path
import argparse,json,os,socket,sys,time
import bpy,numpy as np
from mathutils import Vector,Matrix
HERE=Path(__file__).resolve().parent;sys.path[:0]=[str(HERE),str(HERE.parent/'physics')]
from common import LAYOUT,save,sha,ASSETS
from edit_vocab import resolve
from optics import OPTICS,CAMERA_LAYOUT
sys.path.insert(0,str(next(p for p in HERE.parents if p.name=='scripts')))
from pcve_media_contract import CONTRACT,require_times

def material(name,color,rough=.5,metal=0.):
    m=bpy.data.materials.new(name);m.use_nodes=True;m.diffuse_color=(*color,1)
    bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Roughness'].default_value=rough;bs.inputs['Metallic'].default_value=metal
    return m
def cube(name,loc,dims,mat,bevel=0.):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=dims
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if mat:o.data.materials.append(mat)
    if bevel:
        m=o.modifiers.new('Manufactured soft edge','BEVEL');m.width=bevel;m.segments=4
        o.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
    return o
def curve(name,points,radius,mat):
    d=bpy.data.curves.new(name,'CURVE');d.dimensions='3D';d.bevel_depth=radius;d.bevel_resolution=2
    p=d.splines.new('POLY');p.points.add(len(points)-1)
    for a,b in zip(p.points,points):a.co=(*b,1)
    o=bpy.data.objects.new(name,d);bpy.context.collection.objects.link(o);o.data.materials.append(mat)
    return o
def asset(key,loc=(0,0,0),width=None):
    path=ASSETS/key/'asset.blend'
    if key=='prepared':path=ASSETS/LAYOUT['chair_geometry_dir']/'chair.blend'
    with bpy.data.libraries.load(str(path),link=False)as(src,dst):dst.objects=src.objects
    obs=[o for o in dst.objects if o and o.type in ['MESH','CURVE','EMPTY']]
    for o in obs:bpy.context.collection.objects.link(o);o.animation_data_clear()
    bpy.context.view_layer.update();trans={o:o.matrix_world.copy()for o in obs}
    for o in obs:o.parent=None;o.matrix_world=trans[o]
    geo=[o for o in obs if o.type in ['MESH','CURVE']and not o.hide_render]
    pts=np.asarray([o.matrix_world@Vector(x)for o in geo for x in o.bound_box]);lo=pts.min(0);hi=pts.max(0)
    if key!='prepared':
        center=(lo+hi)/2;center[2]=lo[2];scale=width/(hi-lo)[0] if width else 1.
        for o in obs:
            T=o.matrix_world.copy();T.translation-=Vector(center);T=Matrix.Diagonal((scale,scale,scale,1.))@T
            T.translation+=Vector(loc);o.matrix_world=T
    root=bpy.data.objects.new(key+' transform',None);bpy.context.collection.objects.link(root)
    for o in obs:o.parent=root
    return root
def floor_material():
    m=material('Scanned oak floor / Poly Haven',(.3,.21,.13),.46);n=m.node_tree.nodes;l=m.node_tree.links;bs=n.get('Principled BSDF')
    tc=n.new('ShaderNodeTexCoord');mp=n.new('ShaderNodeVectorMath');mp.operation='SCALE';mp.inputs[3].default_value=1/2.
    l.new(tc.outputs['Object'],mp.inputs[0])
    for role,slot in [('diff','Base Color'),('rough','Roughness'),('nor_gl',None)]:
        p=next((ASSETS/'wood_floor').glob('*_'+role+'_2k.jpg'))
        tx=n.new('ShaderNodeTexImage');tx.image=bpy.data.images.load(str(p));l.new(mp.outputs['Vector'],tx.inputs['Vector'])
        if role!='diff':tx.image.colorspace_settings.name='Non-Color'
        if slot:l.new(tx.outputs['Color'],bs.inputs[slot])
        else:
            nm=n.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.38;l.new(tx.outputs['Color'],nm.inputs['Color']);l.new(nm.outputs['Normal'],bs.inputs['Normal'])
    return m
def cotton(length):
    from scarf_material import cotton as asset_cotton
    return asset_cotton(length)

def room(scene):
    from room import build_room
    return build_room(scene,material,cube,curve,asset,floor_material)

def main():
    assert sys.platform.startswith('linux'), 'Blender runs on a Linux GPU worker'
    ap=argparse.ArgumentParser();ap.add_argument('--simulation',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--stills');ap.add_argument('--width',type=int,default=CONTRACT['width']);ap.add_argument('--samples',type=int,default=192)
    ap.add_argument('--backend',choices=['CUDA','OPTIX','CPU'],default='CUDA')
    a=ap.parse_args(sys.argv[sys.argv.index('--')+1:]);out=a.out;(out/'rgb').mkdir(parents=True,exist_ok=True)
    cfg=json.loads((a.simulation/'simulation_config.json').read_text());cache=a.simulation/'cache.npz'
    if not cache.exists():cache=a.simulation/'checkpoint.npz'
    # common.py carries the repository data paths, so compare the recorded inputs instead of its hash.
    if cfg['layout']!=LAYOUT or cfg['physics']!=resolve(cfg['case_id'])[0]:raise RuntimeError('Baseline source mismatch')
    c=np.load(cache)
    if not a.stills:require_times(c['times'])
    positions=c['positions'];faces=c['faces'];uv=c['uv'];names=list(c['rigid_names'])
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.render.engine='CYCLES'
    if a.backend=='CPU':
        scene.cycles.device='CPU'
    else:
        pref=bpy.context.preferences.addons['cycles'].preferences;pref.compute_device_type=a.backend;pref.get_devices()
        for d in pref.devices:d.use=d.type==a.backend
        if not any(d.use for d in pref.devices):raise RuntimeError('Missing UUID-bound '+a.backend+' GPU')
        scene.cycles.device='GPU'
    scene.cycles.samples=a.samples;scene.cycles.use_denoising=True;scene.render.use_persistent_data=True
    scene.cycles.adaptive_threshold=.009;scene.cycles.max_bounces=12;scene.cycles.diffuse_bounces=6
    scene.render.resolution_x=a.width;scene.render.resolution_y=round(a.width*9/16);scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB';scene.render.fps=24
    scene.view_settings.view_transform='AgX';scene.view_settings.look=OPTICS['view_look'];scene.view_settings.exposure=OPTICS['exposure']
    room_record=room(scene);roots={}
    if cfg['physics']['chair_active'][0]:
        chair=asset('prepared');chair.location.z=LAYOUT['chair_ground_clearance'];roots['chair']=chair
        for o in chair.children:
            o.location.z+=LAYOUT['chair_ground_clearance']
            if o.type=='MESH':
                for mat in o.data.materials:
                    if not mat or not mat.node_tree:continue
                    n=mat.node_tree.nodes;l=mat.node_tree.links;bs=next((a for a in n if a.type=='BSDF_PRINCIPLED'),None)
                    if bs is None:continue
                    bs.inputs['Roughness'].default_value=.39;bs.inputs['Coat Weight'].default_value=.12;bs.inputs['Coat Roughness'].default_value=.3
                    tex=n.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=1400.;tex.inputs['Detail'].default_value=2.
                    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.14;bump.inputs['Distance'].default_value=.000018
                    l.new(tex.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],bs.inputs['Normal'])
        chair.location.z=0
    if cfg['physics']['book_active'][0]:
        p=cfg['physics'];r=bpy.data.objects.new('Hardcover book transform',None);bpy.context.collection.objects.link(r);roots['landing_book']=r
        loc=np.array(p['book_location']);dims=p['book_dimensions']
        cover=material('Added book / rust linen cover',(.32,.095,.043),.8)
        pages=material('Added book / fine page edges',(.77,.73,.62),.85)
        body=cube('Added book page block',loc,(dims[0]-.007,dims[1]-.006,dims[2]-.005),pages,.0015);body.parent=r
        for sign in [-1,1]:
            ob=cube('Added clothbound cover',loc+np.array([0,0,sign*(dims[2]/2-.001)]),(dims[0],dims[1],.002),cover,.001);ob.parent=r
        spine=cube('Added rounded book spine',loc+np.array([-dims[0]/2+.002,0,0]),(.004,dims[1],dims[2]),cover,.002);spine.parent=r
    mesh=bpy.data.meshes.new('Native cotton triangles');mesh.from_pydata(positions[0].tolist(),[],faces.tolist());mesh.update()
    cloth=bpy.data.objects.new('Cotton scarf / exact native shell',mesh);bpy.context.collection.objects.link(cloth)
    layer=mesh.uv_layers.new(name='Material UV')
    for poly in mesh.polygons:
        poly.use_smooth=True
        for li in poly.loop_indices:layer.data[li].uv=uv[mesh.loops[li].vertex_index]
    cm=cotton(cfg['material_length_m']);mesh.materials.append(cm)
    solid=cloth.modifiers.new('True textile thickness','SOLIDIFY');solid.thickness=cfg['physics']['scarf_thickness'];solid.offset=0.
    nx,ny=cfg['grid'];thread=material('Cotton selvedge thread',(.22,.16,.095),.87)
    seam_indices=[np.arange(ny),np.arange((nx-1)*ny,nx*ny)]
    seams=[curve('Woven selvedge',positions[0][idx],.00010,thread)for idx in seam_indices]
    # Fringes are connected native shell ribbons and move with the recorded mesh.
    fringes=[]
    bpy.ops.object.camera_add(location=CAMERA_LAYOUT['camera_location']);cam=bpy.context.object
    cam.rotation_euler=(Vector(CAMERA_LAYOUT['camera_target'])-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=OPTICS['camera_lens_mm'];scene.camera=cam
    cam.data.dof.use_dof=True;cam.data.dof.focus_distance=(Vector((0,.15,.68))-cam.location).length;cam.data.dof.aperture_fstop=9.
    frames=[int(s)for s in a.stills.split(',')]if a.stills else list(range(1,len(positions)+1));start=time.monotonic()
    manifest=dict(worker_host=socket.gethostname(),gpu_uuid=os.environ.get('CUDA_VISIBLE_DEVICES'),blender_version=bpy.app.version_string,cycles_backend=a.backend,
        optics=OPTICS,simulation_cache_sha256=sha(cache),camera=CAMERA_LAYOUT,resolution=[a.width,round(a.width*9/16)],fps=24,samples=a.samples,
        optical_cloth='Native body and connected fringe vertices, 0.35 mm symmetric solidify; tiny optical selvedge thread; no invented fringe motion, smoothing or deformation gain.',
        textile_revision='native_fringed_cotton',textile_optical_parameters=dict(asset='BlenderKit Hanging scarf',atlas_body_region_uv=list(cm['atlas_body_region_uv']),roughness_range=[.76,.94],specular_ior_level=.20,micro_bump_distance_m=.000025,native_fringe=True,native_motion_changed=False),
        chair_optical_from='BlenderKit Simple Wooden Chair, detailed mesh with shared upright back design; native ABD transform',
        asset_manifest=json.loads((ASSETS/'selected_asset_manifest.json').read_text()),room=room_record,primary_geometry_not_animated_by_keyframes=True)
    save(out/'render_manifest.json',manifest)
    for frame in frames:
        i=frame-1
        if i>=len(positions):continue
        scene.frame_set(frame);mesh.vertices.foreach_set('co',positions[i].astype(np.float32).ravel());mesh.update()
        for name,root in roots.items():root.matrix_world=Matrix(c['rigid_transforms'][i,names.index(name)].tolist())
        for ob,idx in zip(seams,seam_indices):
            for pt,v in zip(ob.data.splines[0].points,positions[i][idx]):pt.co=(*v,1)
        for ob,idx,neighbor in fringes:
            d=positions[i][idx]-positions[i][neighbor];d/=max(np.linalg.norm(d),1e-12)
            for pt,v in zip(ob.data.splines[0].points,[positions[i][idx],positions[i][idx]+d*.007]):pt.co=(*v,1)
        scene.render.filepath=str(out/'rgb'/f'{frame:04d}.png')
        if frame==frames[0]:
            bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'))
        bpy.ops.render.render(write_still=True);print('RENDERED',frame,'wall',round(time.monotonic()-start,2),flush=True)
    save(out/'render_completion.json',dict(complete=True,frames=frames,runtime_seconds=time.monotonic()-start,
        worker_host=socket.gethostname(),gpu_uuid=os.environ.get('CUDA_VISIBLE_DEVICES'),cache_sha256=sha(cache)))
if __name__=='__main__':main()
