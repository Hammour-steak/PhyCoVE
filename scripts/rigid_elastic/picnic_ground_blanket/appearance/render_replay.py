"""Replay the accepted native picnic physics into the packed scene with the current look.

Every frame writes the native cloth vertices and rigid transforms of one case into the packed
scene, checks Blender's evaluated cloth mid-surface against the cache (2 um) and renders it.
Grass blades near the cloth are render proxies that follow the solved support surface; the
far lawn is continued with the same scanned plants (far_meadow.py). Light and materials come
from look.py. The camera is fixed and checked against scene_manifest.json on every frame.
"""
from pathlib import Path
import argparse, hashlib, json, math, os, socket, subprocess, sys
sys.dont_write_bytecode=True
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from far_meadow import continue_meadow
import look
REPOSITORY=HERE.parents[3]
sys.path.insert(0,str(REPOSITORY/'scripts'))
from pcve_media_contract import CONTRACT,require_times
from pcve_assets import asset
MANIFEST=json.loads((HERE.parent/'scene_manifest.json').read_text(encoding='utf-8'))
SKY=asset(f'polyhaven/{look.SKY_ID}/{look.SKY_ID}_2k.hdr')


def save(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):h.update(block)
    return h.hexdigest()


def clear_packed_surface_animation(ob):
    """Mesh writes do not override an animated shape-key datablock."""
    keys=ob.data.shape_keys
    record=dict(shape_keys_removed=len(keys.key_blocks) if keys else 0,
                shape_key_action_removed=bool(keys and keys.animation_data and keys.animation_data.action))
    ob.animation_data_clear()
    ob.data.animation_data_clear()
    if keys:ob.shape_key_clear()
    assert ob.data.shape_keys is None
    return record


def evaluated_mid_surface_error(ob,expected):
    """Audit Blender's evaluated surface, excluding only cosmetic thickness."""
    states=[]
    try:
        for modifier in ob.modifiers:
            if modifier.type!='SOLIDIFY':raise RuntimeError('Unexpected cloth modifier: '+modifier.type)
            states.append((modifier,modifier.show_viewport))
            modifier.show_viewport=False
        bpy.context.view_layer.update()
        evaluated=ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh=evaluated.to_mesh()
        try:
            if len(mesh.vertices)!=len(expected):raise RuntimeError('Evaluated cloth topology differs from the physics cache')
            points=np.empty_like(expected)
            mesh.vertices.foreach_get('co',points.reshape(-1))
            transform=np.asarray(evaluated.matrix_world)
            points=points@transform[:3,:3].T+transform[:3,3]
            return float(np.max(abs(points-expected)))
        finally:evaluated.to_mesh_clear()
    finally:
        for modifier,enabled in states:modifier.show_viewport=enabled
        bpy.context.view_layer.update()


def interpolate(top,lo,hi,nx,ny,xy):
    uv=(xy-lo)/(hi-lo)*np.array([nx-1,ny-1]);uv=np.clip(uv,0,[nx-1-1e-7,ny-1-1e-7]);ij=np.floor(uv).astype(np.int32);fx,fy=(uv-ij).T
    a=ij[:,0]*ny+ij[:,1];b=a+ny;c=b+1;d=a+1;lower=fx>=fy
    picks=np.stack([a,np.where(lower,b,c),np.where(lower,c,d)],axis=1)
    weights=np.stack([np.where(lower,1-fx,1-fy),np.where(lower,fx-fy,fx),np.where(lower,fy,fy-fx)],axis=1)
    return np.sum(top[picks]*weights[:,:,None],axis=1)


def add_fine_understory(scene):
    """Fill the existing meadow with metric, rooted fine shoots near the cloth."""
    rng=np.random.default_rng(842061)
    x,y=np.meshgrid(np.arange(-.86,.94,.012),np.arange(-.80,.82,.012),indexing='ij')
    xy=np.column_stack([x.reshape(-1),y.reshape(-1)])+rng.uniform(-.004,.004,(x.size,2))
    radius=np.sqrt((xy[:,0]/.91)**2+(xy[:,1]/.80)**2)
    probability=.92*np.clip((1.20-radius)/.45,0,1)
    xy=xy[rng.random(len(xy))<probability]
    ground=bpy.data.objects['Photographed meadow ground']
    tree=BVHTree.FromObject(ground,bpy.context.evaluated_depsgraph_get())
    xyz=np.column_stack([xy,np.zeros(len(xy))]).astype(np.float32)
    for i,(px,py) in enumerate(xy):
        hit,normal,index,distance=tree.ray_cast(Vector((float(px),float(py),.1)),Vector((0,0,-1)),.4)
        xyz[i,2]=float(hit.z)-.0004 if hit else 0.
    plants=[ob for ob in bpy.data.collections['Plant sources | Poly Haven CC0'].objects if ob.type=='MESH']
    heights=np.array([max(v.co.z for v in ob.data.vertices)for ob in plants])
    candidates=[i for i,ob in enumerate(plants)if ob.name.startswith('grass_bermuda_01') and .045<=heights[i]<=.090]
    ids=rng.choice(candidates,len(xy)).astype(np.int32)
    size=rng.uniform(.045,.066,len(xy))/heights[ids]
    scale=np.repeat(size[:,None],3,axis=1).astype(np.float32);scale[:,:2]*=rng.uniform(.88,1.12,(len(xy),2))
    rotation=np.zeros((len(xy),3),np.float32);rotation[:,:2]=rng.uniform(-.10,.10,(len(xy),2));rotation[:,2]=rng.uniform(-math.pi,math.pi,len(xy))
    modifier=bpy.data.objects['Lawn | instanced photographed plant species'].modifiers[0]
    region=(abs(xy[:,0])<.515)&(abs(xy[:,1])<.395)
    for name,keep in [('Fine turf | static meadow understory',~region),('Grass patch | fine rooted understory',region)]:
        mesh=bpy.data.meshes.new(name);mesh.from_pydata(xyz[keep].tolist(),[],[])
        for key,typ,values in [('plant_id','INT',ids[keep]),('plant_scale','FLOAT_VECTOR',scale[keep]),('plant_rotation','FLOAT_VECTOR',rotation[keep])]:
            attr=mesh.attributes.new(key,typ,'POINT');attr.data.foreach_set('value'if typ=='INT'else'vector',values.reshape(-1))
        ob=bpy.data.objects.new(name,mesh);scene.collection.objects.link(ob);mod=ob.modifiers.new('Photographed fine-grass instances','NODES');mod.node_group=modifier.node_group
    return len(xy)


def extend_ground(scene):
    """Continue the photographed terrain beyond its formerly visible square edge."""
    ground=bpy.data.objects['Photographed meadow ground'];mesh=ground.data
    points=np.asarray([v.co[:]for v in mesh.vertices]);border=(np.max(abs(points[:,:2]),axis=1)>11.999)
    selected=np.flatnonzero(border);selected=selected[np.argsort(np.arctan2(points[selected,1],points[selected,0]))]
    inner=points[selected];outer=inner.copy();outer[:,:2]*=32.;outer[:,2]=-.04
    vertices=np.vstack([inner,outer]);n=len(inner);faces=[(i,(i+1)%n,(i+1)%n+n,i+n)for i in range(n)]
    me=bpy.data.meshes.new('Continuous distant photographed terrain');me.from_pydata(vertices.tolist(),[],faces);me.update()
    # Recover the original UV affine mapping, preserving its real metric scale.
    uv=mesh.uv_layers.active;uv_by_vertex={}
    for loop in mesh.loops:uv_by_vertex[loop.vertex_index]=tuple(uv.data[loop.index].uv)
    anchors=np.array(list(uv_by_vertex));design=np.column_stack([points[anchors,:2],np.ones(len(anchors))]);values=np.array([uv_by_vertex[i]for i in anchors]);mapping=np.linalg.lstsq(design,values,rcond=None)[0]
    layer=me.uv_layers.new(name=uv.name)
    for loop in me.loops:layer.data[loop.index].uv=tuple(np.r_[vertices[loop.vertex_index,:2],1.]@mapping)
    me.materials.append(mesh.materials[0]);ob=bpy.data.objects.new(me.name,me);scene.collection.objects.link(ob)


def prepare_grass(scene,cache,physics):
    plants=bpy.data.collections['Plant sources | Poly Haven CC0'];bounds=[np.asarray([v.co[:]for v in ob.data.vertices])for ob in plants.objects if ob.type=='MESH']
    heights=np.array([v[:,2].max()for v in bounds]);widths=np.array([np.ptp(v[:,:2],axis=0).max()for v in bounds])
    native_lo=np.array([v.min(0)for v in bounds]);native_hi=np.array([v.max(0)for v in bounds]);native_center=(native_lo+native_hi)*.5;native_half=(native_hi-native_lo)*.5
    top_ids=cache['cover_volume_vertex_ids'];rest=cache['solid_rest_positions'][top_ids];lo,hi=rest[:,:2].min(0),rest[:,:2].max(0)
    nx=round((physics['cloth_dimensions'][0]+.18)/physics['foundation_pitch'])+1;ny=round((physics['cloth_dimensions'][1]+.18)/physics['foundation_pitch'])+1
    source_top=cache['solid_positions'][0,top_ids];rng=np.random.default_rng(20261026);objects=[];layout_hash=hashlib.sha256()
    # Include every clump whose full footprint can overlap the cloth, including
    # roots just outside the FEM domain. Leave the distant 100k-instance lawn static.
    for ob in list(scene.objects):
        if ob.type!='MESH' or 'plant_scale' not in ob.data.attributes or 'Grass patch' in ob.name:continue
        mesh=ob.data;xyz=np.asarray([v.co[:]for v in mesh.vertices]);outside=np.linalg.norm(np.maximum(np.maximum(lo-xyz[:,:2],xyz[:,:2]-hi),0.),axis=1);near=outside<.14
        if not near.any():continue
        values={}
        for key in ['plant_id','plant_scale','plant_rotation']:
            width=1 if key=='plant_id'else 3;array=np.empty((len(xyz),)if width==1 else(len(xyz),3),np.int32 if width==1 else np.float32)
            mesh.attributes[key].data.foreach_get('value'if width==1 else'vector',array.reshape(-1));values[key]=array
        def subset(label,mask):
            me=bpy.data.meshes.new(label);me.from_pydata(xyz[mask].tolist(),[],[])
            for key,array in values.items():
                integer=key=='plant_id';attr=me.attributes.new(key,'INT'if integer else'FLOAT_VECTOR','POINT');attr.data.foreach_set('value'if integer else'vector',array[mask].reshape(-1))
            return me
        if near.all():ob.name='Grass patch | full footprint | '+ob.name
        else:
            dynamic=ob.copy();dynamic.data=subset('Near-field contact grass points',near);dynamic.name='Grass patch | full footprint | '+ob.name
            scene.collection.objects.link(dynamic);ob.data=subset('Distant static grass points',~near)
    for ob in list(scene.objects):
        if ob.type!='MESH' or 'plant_scale' not in ob.data.attributes:continue
        mesh=ob.data;n=len(mesh.vertices);xyz=np.empty((n,3),np.float32);mesh.vertices.foreach_get('co',xyz.reshape(-1))
        scale=np.empty((n,3),np.float32);mesh.attributes['plant_scale'].data.foreach_get('vector',scale.reshape(-1))
        rotation=np.empty((n,3),np.float32);mesh.attributes['plant_rotation'].data.foreach_get('vector',rotation.reshape(-1))
        ids=np.empty(n,np.int32);mesh.attributes['plant_id'].data.foreach_get('value',ids)
        actual_width=widths[ids]*np.maximum(scale[:,0],scale[:,1]);ratio=np.minimum(1.,.16/(actual_width+1e-12));scale[:,:2]*=ratio[:,None]
        xy=xyz[:,:2].astype(np.float64);dx=np.maximum(np.maximum(lo-xy,xy-hi),0.);outside=np.linalg.norm(dx,axis=1)
        border_weight=np.clip(1-outside/.12,0,1);border_weight=border_weight**2*(3-2*border_weight)
        initial_crown=interpolate(source_top,lo,hi,nx,ny,xy);old_height=heights[ids]*scale[:,2]
        cap=.080+.018*np.sin(8.4*xy[:,0]+1.7*np.cos(6.2*xy[:,1]))+.010*np.sin(20*xy[:,1]+3*xy[:,0])
        crown_height=initial_crown[:,2]-xyz[:,2];target_cap=cap*(1-border_weight)+crown_height*border_weight
        scales_z=np.minimum(old_height,target_cap)/np.maximum(heights[ids],1e-8);inside=((xy>=lo)&(xy<=hi)).all(1)
        variation=rng.uniform(.96,1.04,n);scales_z[inside]=crown_height[inside]*variation[inside]/heights[ids[inside]];scale[:,2]=np.maximum(scales_z,.012)
        protected=np.zeros(n,bool)
        for x,y,r in [(.59,.055,.155),(.34,.41,.088),(.509,.298,.065)]:protected|=(xy[:,0]-x)**2+(xy[:,1]-y)**2<r*r
        scale[protected,2]=np.minimum(scale[protected,2],.0025/heights[ids[protected]])
        rotation[protected,:2]=0.
        mesh.attributes['plant_scale'].data.foreach_set('vector',scale.reshape(-1));mesh.attributes['plant_rotation'].data.foreach_set('vector',rotation.reshape(-1));mesh.update();active=np.arange(n) if 'Grass patch' in ob.name else np.empty(0,np.int32)
        layout_hash.update(xyz.tobytes()+ids.tobytes()+scale[:,:2].tobytes()+rotation.tobytes())
        objects.append(dict(object=ob,xyz=xyz,xy=xy,scale=scale,rotation=rotation,ids=ids,active=active,inside=inside,variation=variation,protected=protected,initial_crown=initial_crown,heights=heights,widths=widths))
    def update(frame,cloth_positions):
        top=cache['solid_positions'][frame,top_ids]
        # A conservative cloth height field stores each overlapping triangle's
        # minimum Z. Unlike sparse rays, this cannot miss a narrow fold.
        # Without the blanket (DELETE cotton_blanket) the field has no triangles: every cap stays infinite.
        support=cloth_positions if len(cloth_positions) else top
        step=.008;grid_lo=support[:,:2].min(0)-.22;grid_hi=support[:,:2].max(0)+.22;shape=np.ceil((grid_hi-grid_lo)/step).astype(int)+1;field=np.full(tuple(shape),np.inf)
        triangles=cloth_positions[cache['cloth_faces']];a=np.floor((triangles[:,:,:2].min(1)-grid_lo)/step).astype(int);b=np.floor((triangles[:,:,:2].max(1)-grid_lo)/step).astype(int);bottom=triangles[:,:,2].min(1)
        for low,high,z in zip(a,b,bottom):
            view=field[low[0]:high[0]+1,low[1]:high[1]+1];np.minimum(view,z,out=view)
        for item in objects:
            ob=item['object'];active=item['active'];xy=item['xy'];ids=item['ids'];scale=item['scale'].copy();rotation=item['rotation'].copy()
            if not len(active):continue
            crown=interpolate(top,lo,hi,nx,ny,xy[active]);height=np.maximum(crown[:,2]-item['xyz'][active,2],.001);inside=item['inside'][active];selected=active[inside]
            scale[selected,2]=height[inside]*item['variation'][selected]/item['heights'][ids[selected]]
            shear=crown-item['initial_crown'][active]
            rotation[selected,0]-=np.clip(shear[inside,1]/np.maximum(height[inside],.008),-.20,.20);rotation[selected,1]+=np.clip(shear[inside,0]/np.maximum(height[inside],.008),-.20,.20)
            # Bound the fully rotated native mesh, not just its local Z axis.
            # Tilting an otherwise height-capped clump can lift a lateral leaf
            # through cloth. Its complete footprint and horizontal Z extent
            # participate in this cap; the rigid/cloth cache remains untouched.
            angles=rotation[active];cx,cy,cz=np.cos(angles).T;sx,sy,sz=np.sin(angles).T
            matrix=np.empty((len(active),3,3));matrix[:,0,0]=cz*cy;matrix[:,0,1]=cz*sy*sx-sz*cx;matrix[:,0,2]=cz*sy*cx+sz*sx
            matrix[:,1,0]=sz*cy;matrix[:,1,1]=sz*sy*sx+cz*cx;matrix[:,1,2]=sz*sy*cx-cz*sx;matrix[:,2,0]=-sy;matrix[:,2,1]=cy*sx;matrix[:,2,2]=cy*cx
            center=native_center[ids[active]]*scale[active];half=native_half[ids[active]]*scale[active]
            world_center=np.einsum('nij,nj->ni',matrix,center)+item['xyz'][active];extent=np.einsum('nij,nj->ni',abs(matrix),half)
            lower=np.floor((world_center[:,:2]-extent[:,:2]-.001-grid_lo)/step).astype(int);upper=np.floor((world_center[:,:2]+extent[:,:2]+.001-grid_lo)/step).astype(int)
            lower=np.clip(lower,0,shape-1);upper=np.clip(upper,0,shape-1)
            for j,i in enumerate(active):
                low,high=lower[j],upper[j];cap=float(field[low[0]:high[0]+1,low[1]:high[1]+1].min())
                if not math.isfinite(cap):continue
                budget=cap-.001-float(item['xyz'][i,2]);horizontal=float(matrix[j,2,:2]@center[j,:2]+abs(matrix[j,2,:2])@half[j,:2])
                if budget<=0:scale[i]=0.;continue
                if horizontal>=budget:
                    rotation[i,:2]=0.;scale[i,2]=min(scale[i,2],budget/item['heights'][ids[i]])
                else:scale[i,2]=min(scale[i,2],(budget-horizontal)/(matrix[j,2,2]*item['heights'][ids[i]]))
            scale[item['protected'],2]=item['scale'][item['protected'],2]
            ob.data.attributes['plant_scale'].data.foreach_set('vector',scale.astype(np.float32).reshape(-1));ob.data.attributes['plant_rotation'].data.foreach_set('vector',rotation.astype(np.float32).reshape(-1));ob.data.update()
    return update,dict(layout_sha256=layout_hash.hexdigest(),instances=sum(len(i['ids'])for i in objects),max_clump_width_m=.16,transition_band_m=.12,cloth_clearance_m=.001,cloth_height_grid_pitch_m=.008,contact='Botanical proxy envelope replays the unmodified FEM grass surface. Conservative triangle minima cap the full rotated mesh footprint, including roots outside the cloth. Individual blades are not independently simulated rods.')



def tuft_root_distances(cloth,tracks,own):
    """Smallest lateral distance from a border-tuft root to the cloth border, over the accepted tracks and over this case."""
    roots=np.array([v.co[:2] for v in bpy.data.objects['Grass tufts | blanket border (static, outside the cloth)'].data.vertices])
    distance=np.array([v.value for v in cloth.data.attributes['hem_distance_m'].data]);border=np.flatnonzero(distance<1e-6)
    def closest(track):
        pts=track[:,border,:2].reshape(-1,2)
        return float(min(np.linalg.norm(pts-r,axis=1).min() for r in roots))
    return dict(accepted_tracks_min_root_distance_m=min(closest(t) for t in tracks),timed_track_min_root_distance_m=closest(own))


def configure_device(scene,device,backend):
    scene.cycles.device=device
    if device=='CPU':return 'CPU'
    pref=bpy.context.preferences.addons['cycles'].preferences
    pref.compute_device_type=backend;pref.get_devices()
    for d in pref.devices:d.use=d.type==backend
    if not any(d.use for d in pref.devices):raise RuntimeError('No '+backend+' device visible to Blender')
    return backend


def camera_record(scene):
    cam=scene.camera
    return dict(matrix_world=np.asarray(cam.matrix_world).tolist(),lens_mm=cam.data.lens,sensor_width_mm=cam.data.sensor_width,
                shift=[cam.data.shift_x,cam.data.shift_y],resolution=[scene.render.resolution_x,scene.render.resolution_y],
                dof=dict(focus_distance_m=cam.data.dof.focus_distance,fstop=cam.data.dof.aperture_fstop))


def main():
    import faulthandler
    faulthandler.enable(all_threads=True)
    parser=argparse.ArgumentParser();parser.add_argument('--scene',type=Path,required=True);parser.add_argument('--simulation',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=512);parser.add_argument('--still-frame',type=int,nargs='+');parser.add_argument('--frame-start',type=int,default=1);parser.add_argument('--frame-end',type=int,default=96)
    parser.add_argument('--device',choices=['GPU','CPU'],default='GPU');parser.add_argument('--cycles-backend',choices=['CUDA','OPTIX'],default='OPTIX')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);out=args.out;out.mkdir(parents=True,exist_ok=True);(out/'frames').mkdir(exist_ok=True)
    cfg=json.loads((args.simulation/'simulation_config.json').read_text());p=cfg['physics'];q=cfg['simulation']
    with np.load(args.simulation/'cache.npz') as archive:cache={name:archive[name]for name in archive.files}
    assert cfg['scene_id']=='picnic_ground_blanket' and len(cache['times'])==96 and q['fps']==24 and q['duration']==4.
    require_times(cache['times'])
    print('REPLAY_STAGE load_scene',flush=True)
    bpy.ops.wm.open_mainfile(filepath=str(args.scene),load_ui=False);s=bpy.context.scene;bpy.app.handlers.frame_change_pre.clear();bpy.app.handlers.frame_change_post.clear()
    s.render.resolution_x=1280;s.render.resolution_y=720;s.render.resolution_percentage=100
    camera=camera_record(s);expected=MANIFEST['camera']
    if not np.array_equal(np.asarray(camera['matrix_world']),np.asarray(expected['matrix_world'])) or (camera['lens_mm'],camera['sensor_width_mm'],camera['shift'],camera['resolution'])!=(expected['lens_mm'],expected['sensor_width_mm'],expected['shift'],expected['resolution']):
        raise RuntimeError('Packed camera differs from scene_manifest.json camera')
    camera_matrix=np.asarray(s.camera.matrix_world).copy();rest_transforms={o.name:np.asarray(o.matrix_world).tolist()for o in s.objects if o.type=='MESH' and o.pass_index==0 and 'plant_scale' not in o.data.attributes}
    s.render.engine='CYCLES';s.cycles.samples=args.samples;s.cycles.use_adaptive_sampling=True;s.cycles.adaptive_threshold=.006;s.cycles.adaptive_min_samples=64
    s.cycles.use_denoising=True;s.cycles.denoiser='OPENIMAGEDENOISE';s.cycles.denoising_input_passes='RGB_ALBEDO_NORMAL';s.cycles.denoising_prefilter='ACCURATE'
    s.cycles.use_animated_seed=False;s.cycles.seed=20261109;s.cycles.max_bounces=12;s.cycles.transparent_max_bounces=48;s.cycles.blur_glossy=.5;s.cycles.sample_clamp_indirect=12.
    backend=configure_device(s,args.device,args.cycles_backend)
    print('REPLAY_STAGE device_configured',backend,flush=True)
    s.render.fps=24;s.render.use_motion_blur=False;s.render.use_persistent_data=True;s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB';s.render.image_settings.color_depth='8';s.frame_start=1;s.frame_end=96
    for node in s.node_tree.nodes:
        if node.type=='OUTPUT_FILE':node.base_path=str(out/'masks_raw')
    body=bpy.data.objects['mandarin_orange'];body.animation_data_clear();body.hide_render=not bool(p['active'][0])
    cloth=bpy.data.objects['picnic_ground_blanket | actual physical surface'];animation_cleanup=clear_packed_surface_animation(cloth)
    # Presence of the blanket (physics active[1]; DELETE cotton_blanket): absent, the cloth is not rendered (no shadow
    # or reflection), the border tufts and edge shade are not added and no grass is capped under a cloth.
    blanket=bool(p['active'][1])
    if blanket:assert len(cloth.data.vertices)==cache['cloth_positions'].shape[1]
    else:
        assert cache['cloth_positions'].shape[1]==0;cloth.hide_render=True;cloth.hide_viewport=True
        for ob in s.objects:
            if ob.type=='MESH' and 'edge_shade' in ob.data.attributes:ob.data.attributes.remove(ob.data.attributes['edge_shade'])
    obstacle=None;present=bool(cache['path_obstacle_present'][0]);cup=None
    if present:
        contact=cache['path_obstacle_vertices'];radius=float(np.max(np.linalg.norm(contact[:,:2],axis=1)));height=float(np.ptp(contact[:,2]))
        if abs(radius-p['picnic_cup_radius'])>1e-6 or abs(height-p['picnic_cup_height'])>1e-6 or abs(contact[:,2].max()+contact[:,2].min())>1e-6:raise RuntimeError('Unexpected native cup contact mesh')
        obstacle,cup=look.enamel_cup(p['picnic_cup_radius'],p['picnic_cup_height']);s.collection.objects.link(obstacle);obstacle.pass_index=3
    appearance=look.apply(s,SKY,cloth);extend_ground(s);extra=add_fine_understory(s);grass_update,grass=prepare_grass(s,cache,p);grass['fine_understory_instances']=extra;errors=[]
    # Static border tufts: one layout for every case (accepted native states of all six cases + this one).
    tracks=[]
    if blanket:
        # The published videos were rendered with the layout of these six accepted states; the ADD case is
        # no longer published, but its state is still part of the layout, so a new render keeps the published tufts.
        for name in ('source','mass_double','faster','stiffer','add_path_obstacle','delete_actor'):
            with np.load(asset(f'scenes/picnic_ground_blanket/native/{name}/cache.npz')) as accepted:tracks.append(accepted['cloth_positions'])
        # A timed edit keeps the layout of the accepted cases, so its frames before the edit look exactly like the
        # source; its own cloth track is still checked for clearance (timed_track_min_clearance_m in the report).
        if not cfg.get('timed_edit'):tracks.append(cache['cloth_positions'])
        appearance['edge_grass']=look.edge_grass(s,cloth,tracks)
        if cfg.get('timed_edit'):appearance['edge_grass'].update(layout_tracks='the six accepted states of the published layout (timed edit)',**tuft_root_distances(cloth,tracks,cache['cloth_positions']))
    else:appearance['edge_grass']=dict(skipped='blanket deleted: no border tufts, no edge shade')
    meadow=continue_meadow(s)
    if cup:appearance['picnic_cup']=cup
    print('REPLAY_STAGE appearance_ready',meadow['instances'],flush=True)
    def update(frame):
        s.frame_set(frame);i=frame-1;x=cache['cloth_positions'][i]
        if blanket:cloth.data.vertices.foreach_set('co',x.astype(np.float32).reshape(-1));cloth.data.update()
        body.matrix_world=Matrix(cache['body_transforms'][i].tolist())
        if obstacle:obstacle.matrix_world=Matrix(cache['obstacle_transforms'][i].tolist())
        grass_update(i,x);bpy.context.view_layer.update()
        error=evaluated_mid_surface_error(cloth,x) if blanket else 0.;errors.append(error)
        if error>2e-6:raise RuntimeError(f'Evaluated surface differs from {cfg["case"]} cache at frame {frame}: {error} m')
        assert np.array_equal(np.asarray(s.camera.matrix_world),camera_matrix)
    frames=args.still_frame if args.still_frame else list(range(args.frame_start,args.frame_end+1))
    # A full 1-96 render writes render_report.json; a frame range or stills write a part report
    # (render_report_<first>-<last>.json) that tools/finalize.py merges.
    part='' if frames==list(range(1,97)) else f'_{min(frames):04d}-{max(frames):04d}'
    for frame in frames:
        update(frame);s.render.filepath=str(out/'frames'/f'{frame:04d}.png');bpy.ops.render.render(write_still=True);print('FRAME_COMPLETE',frame,flush=True)
    assert not errors or max(errors)<2e-6
    for name,transform in rest_transforms.items():assert np.array_equal(np.asarray(bpy.data.objects[name].matrix_world),np.asarray(transform)),name
    for name in ['simulation_config.json','simulation_report.json']:(out/name).write_bytes((args.simulation/name).read_bytes())
    save(out/f'evaluated_surface_audit{part}.json',dict(status='passed',case=cfg['case'],animation_cleanup=animation_cleanup,
        audit_target='Blender evaluated world-space cloth midsurface; cosmetic Solidify thickness excluded',
        evaluated_samples=len(errors),max_error_m=max(errors,default=0),tolerance_m=2e-6,
        cloth_displacement_max_m=float(np.linalg.norm(cache['cloth_positions']-cache['cloth_positions'][0],axis=-1).max()) if blanket else None,
        remaining_shape_keys=0,physical_cache_unchanged=True))
    gpu=None
    if backend!='CPU':
        try:gpu=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,name','--format=csv,noheader'],text=True,timeout=20).strip()
        except (OSError,subprocess.SubprocessError):gpu=None
    save(out/f'render_report{part}.json',dict(scene_id='picnic_ground_blanket',case=cfg['case'],fps=24,resolution=[1280,720],samples=args.samples,
        adaptive_threshold=s.cycles.adaptive_threshold,denoiser='OpenImageDenoise (albedo+normal, accurate prefilter)',seed=s.cycles.seed,motion_blur=False,
        rendered_frames=list(frames),native_sample_times_s=cache['times'].tolist(),media_contract_id=CONTRACT['contract_id'],max_surface_replay_error_m=max(errors,default=0),
        evaluated_surface_verified=True,packed_shape_keys_removed=animation_cleanup['shape_keys_removed'],surface_amplification=1.,
        physics_cache_sha256=sha(args.simulation/'cache.npz'),packed_source_scene_sha256=sha(args.scene),
        camera=camera,camera_matrix_world=camera_matrix.tolist(),static_prop_transforms_preserved=True,appearance=appearance,grass=grass,background_meadow=meadow))
    save(out/f'execution_provenance{part}.json',dict(host=socket.gethostname().split('.')[0],device=args.device,cycles_backend=backend,
        cuda_visible_devices=os.environ.get('CUDA_VISIBLE_DEVICES'),gpus=gpu,blender_version=bpy.app.version_string,threads=s.render.threads))
    print('RENDER_COMPLETE',cfg['case'],flush=True)


if __name__=='__main__':main()
