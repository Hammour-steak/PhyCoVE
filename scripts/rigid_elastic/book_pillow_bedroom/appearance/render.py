"""Native 24 Hz Cycles replay of a qualified native cache in the current bedroom look,
with evaluated visible-contact audits.

Runs inside Blender 4.3.2 (see tools/launch.py) with the restored worker kit:
BOOK_PILLOW_ROOT=<kit>/book_kit, BOOK_PILLOW_KIT_SUPPORT=<kit helper directory>.

    blender -b --python-exit-code 1 --python appearance/render.py -- \
        --case source --input <native case dir> --output <fresh dir> [--frames 1 8 96 | --range 1 48]

The frozen bed-scene and bedding kit modules build the bed, pillow and books as accepted and the
book, quilt and pillow follow the native cache; appearance/realism_look.py then sets the
room, props, materials and daylight. Neither changes a pose, a shape key or a cache value:
every frame the book pose is compared with the cache, and at sampled frames the quilt
binding and the visible book/bedding gaps are measured on the evaluated meshes.
"""
from pathlib import Path
import argparse, hashlib, json, os, socket, sys
sys.dont_write_bytecode = True   # no __pycache__ inside the code tree

HERE=Path(__file__).resolve().parent
CASE_DIR=HERE.parent
sys.path[:0]=[str(HERE),str(CASE_DIR),str(CASE_DIR.parents[1])]  # appearance/, the scene, scripts/
HOST=socket.gethostname().split('.')[0]
if sys.platform!='linux':
    raise RuntimeError('Render on Linux')
import bpy, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

KIT_SUPPORT=Path(os.environ['BOOK_PILLOW_KIT_SUPPORT'])  # helper directory inside the restored kit
sys.path[:0]=[str(KIT_SUPPORT/'bedding'),str(KIT_SUPPORT/'cloth_finish')]
import render_bedding as old
import realism_look
ROOT, DATA = old.ROOT, old.DATA
old.ASSETS = DATA/'assets/quilt'


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def build(book, duvet, rest, pillow, accent):
    """The accepted scene: artist bed with the quilt bound to the cache, pillow, falling book, optional added book."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    old.old.linen = lambda n,c:old.old.base.material(n,c,.82)
    old.old.artist_bed = lambda:old.bedding(duvet,rest)
    old.old.build_room()
    if pillow is not None: old.old.pillow_object(pillow)
    root = old.old.make_book('Falling_Blue_Hardcover',[.24,.17,.036],(.065,.14,.20),'FIELD NOTES')
    old.old.base.animate_rigid(root,book)
    atlas = None
    if accent is not None:
        atlas = old.old.make_book('Resting_Atlas',[.26,.19,.030],(.24,.105,.04),'THE ATLAS')
        old.old.base.animate_rigid(atlas,accent)
    return root, atlas


def gpu_setup(scene):
    prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='CUDA';prefs.get_devices()
    devices=[d for d in prefs.devices if d.type=='CUDA']
    if not devices: raise RuntimeError('CUDA is required for production')
    for d in prefs.devices: d.use=d in devices
    import _cycles
    _cycles.set_device_override('CUDA');scene.cycles.device='GPU'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--case', required=True)
    p.add_argument('--tag', default='quilt')
    p.add_argument('--preview', action='store_true', help='Render the preview frame set only')
    p.add_argument('--frames', type=int, nargs='+')
    p.add_argument('--range', type=int, nargs=2)
    p.add_argument('--input', type=Path, required=True, help='Directory with verified native cache and motion audit')
    p.add_argument('--output', type=Path, required=True, help='Separate render directory')
    p.add_argument('--samples', type=int, default=realism_look.SAMPLES)
    p.add_argument('--cpu-stills', action='store_true', help='Look development on the CPU: at most four --frames')
    p.add_argument('--without-book', action='store_true',
                   help='DELETE book: the falling book is hidden from every ray (the poses and audits stay those of --input)')
    a = p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.cpu_stills and (not a.frames or len(a.frames) > 4):
        p.error('--cpu-stills renders at most four explicit --frames')
    backend = 'CPU' if a.cpu_stills else 'CUDA'
    out = a.input
    if not json.loads((out/'motion_audit.json').read_text())['passed']:
        raise RuntimeError('Motion audit must pass before preview/production rendering')
    cache = out/'simulation.npz'; before = sha(cache)
    with np.load(cache) as z:
        book, duvet, rest, times = z['phone_transforms'], z['duvet_positions'], z['duvet_rest_positions'], z['times']
        pillow = z['pillow_art_positions'] if z['pillow_present'].item() else None
        accent = z['accent_book_transforms'] if z['accent_book_present'].item() else None
    sys.path.insert(0,str(ROOT/'scripts'))
    from pcve_media_contract import require_times
    require_times(times)
    root, atlas = build(book, duvet, rest, pillow, accent)
    old.old.setup(96,a.samples,[1280,720],gpu=False); scene=bpy.context.scene
    scene.render.fps=24;scene.render.fps_base=1.
    # kit light rig, which the frozen cloth finish expects; the look replaces it with daylight.
    window = bpy.data.objects['Soft_Window']; window.location=(-1.55,-.45,2.05)
    old.old.base.look_at(window,(0,.30,.58))
    bpy.ops.object.light_add(type='AREA',location=(1.25,-.80,1.30))
    fill=bpy.context.object;fill.name='Soft_Reflected_Daylight';fill.data.shape='DISK';fill.data.size=1.4;fill.data.color=(1.,.93,.82)
    old.old.base.look_at(fill,(0,.3,.6))
    scene.frame_set(1)
    original = {obj.name: obj.matrix_world.copy() for obj in scene.objects if obj.type in {'MESH','EMPTY','CAMERA'}}
    camera = scene.camera.matrix_world.copy(), scene.camera.data.lens
    finish = realism_look.apply(scene, DATA/'assets', case=a.case)
    scene.frame_set(1)
    for name, transform in original.items():
        obj = scene.objects.get(name)
        if obj is not None and obj.matrix_world != transform:
            raise RuntimeError('The look moved an existing object: '+name)
    if scene.camera.matrix_world != camera[0] or scene.camera.data.lens != camera[1]:
        raise RuntimeError('The look changed the camera')
    if os.environ.get('BOOK_PILLOW_PROBE'):
        realism_look.probe(scene); return
    if a.cpu_stills:
        scene.cycles.device = 'CPU'
    else:
        gpu_setup(scene)
    realism_look.render_settings(scene, a.samples)

    target=a.output;(target/'frames').mkdir(exist_ok=True,parents=True)
    # Exact sampled cache-to-render positions, not a visually fitted displacement.
    audit=[]
    for f in range(1,97):
        scene.frame_set(f)
        err=float(abs(np.array(root.matrix_world)-book[f-1]).max())
        if err>2e-6: raise RuntimeError('Book render transform differs from native state')
        row={'frame':f,'time_s':float(times[f-1]),'book_pose_error':err}
        if f <= 19 or f in [25,37,49,73,96]:
            trees=[];errors=[]
            names=['Cube.003','Plane.004']+(['Sleeping_Pillow'] if pillow is not None else [])
            if atlas is not None: names += [o.name for o in atlas.children if o.type=='MESH']
            for name in names:
                obj=bpy.data.objects[name];ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
                actual=np.array([v.co[:] for v in mesh.vertices])
                if name in ['Cube.003','Plane.004']:
                    with np.load(old.ASSETS/(name+'_binding.npz')) as b:
                        expected=b['vertices']+np.einsum('vi,vij->vj',b['weights'],(duvet[f-1]-rest)[b['indices']])
                    error=float(abs(actual-expected).max());errors.append(error)
                    if error>2e-6: raise RuntimeError('Quilt animation differs from native cache')
                mesh.calc_loop_triangles()
                trees.append(BVHTree.FromPolygons([obj.matrix_world @ v.co for v in mesh.vertices],[tuple(t.vertices) for t in mesh.loop_triangles],all_triangles=True))
                ev.to_mesh_clear()
            bottom=np.array([[x,y,-.018] for x in np.linspace(-.12,.12,41) for y in np.linspace(-.085,.085,31)])
            bottom=bottom@book[f-1,:3,:3].T+book[f-1,:3,3]
            gaps=[]
            for point in bottom:
                hits=[tree.ray_cast(Vector((point[0],point[1],2.)),Vector((0,0,-1)))[0] for tree in trees]
                heights=[h.z for h in hits if h is not None]
                if heights: gaps.append(float(point[2]-max(heights)))
            row.update(binding_max_error_m=max(errors),visible_vertical_gap_m=min(gaps))
            if min(gaps)<-.003: raise RuntimeError('Visible bedding penetrates book beyond 3 mm sampled tolerance')
            if f==96 and abs(min(gaps))>.004: raise RuntimeError('Final visible book/support gap exceeds 4 mm')
        audit.append(row)
    (target/'binding_audit.json').write_text(json.dumps({'passed':True,'deformation_multiplier':1.,'samples':audit,'limitation':'Discrete sampled book-bottom raycasts, not an exact continuous certificate'},indent=2))
    chosen=a.frames or (list(range(a.range[0],a.range[1]+1)) if a.range else [1,7,8,9,10,11,13,19,96] if a.preview else list(range(1,97)))
    if a.without_book:
        for obj in [root,*root.children_recursive]:obj.hide_render=True;obj.hide_viewport=True
    receipts=target/'frame_provenance';receipts.mkdir(exist_ok=True)
    look=realism_look.fingerprint()
    made=[];reused=[];frame_records=[]
    for f in chosen:
        scene.frame_set(f);path=target/'frames'/f'frame_{f:04d}.png'
        receipt=receipts/f'frame_{f:04d}.json'
        if path.exists():
            if not receipt.exists():raise RuntimeError('Existing PNG lacks frame provenance; preserve and audit before retry')
            record=json.loads(receipt.read_text())
            if (record['png_sha256']!=sha(path) or record['native_cache_sha256']!=before
                    or record.get('look')!=look or record.get('samples')!=a.samples or record.get('backend')!=backend):
                raise RuntimeError('Existing frame provenance/cache/look mismatch')
            reused.append(f);frame_records.append(record);continue
        scene.render.filepath=str(path);bpy.ops.render.render(write_still=True)
        record={'frame':f,'physical_time_s':float(times[f-1]),'worker':HOST,'gpu_uuid':os.environ.get('CUDA_VISIBLE_DEVICES') or None,
            'backend':backend,'look':look,'samples':a.samples,
            'blender':bpy.app.version_string,'native_cache_sha256':before,'png_sha256':sha(path)}
        receipt.write_text(json.dumps(record,indent=2));made.append(f);frame_records.append(record)
        print('BOOK_PILLOW_FRAME_COMPLETE',a.case,f,flush=True)
    assert sha(cache)==before
    report=dict(case=a.case,worker=HOST,gpu_uuid=os.environ.get('CUDA_VISIBLE_DEVICES') or None,blender=bpy.app.version_string,engine='CYCLES',backend=backend,
        resolution=[1280,720],fps=24,rendered_frames=chosen,rendered_this_process=made,reused_verified_frames=reused,frame_provenance=frame_records,
        samples=a.samples,input_cache_sha256=before,physical_times_s=[float(times[f-1]) for f in chosen],
        camera_matrix=np.array(scene.camera.matrix_world).tolist(),camera_lens_mm=scene.camera.data.lens,
        camera_sensor_width_mm=scene.camera.data.sensor_width,camera_sensor_fit=scene.camera.data.sensor_fit,
        camera_shift=[scene.camera.data.shift_x,scene.camera.data.shift_y],look=look,finish=finish,
        manual_motion=False,deformation_multiplier=1.,**({'without_book':True} if a.without_book else {}))
    suffix='' if not a.range else '_%03d_%03d'%tuple(a.range)
    (target/('render_report'+suffix+'.json')).write_text(json.dumps(report,indent=2))

if __name__=='__main__':main()
