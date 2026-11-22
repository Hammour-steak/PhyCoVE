"""Cycles lookdev, direct native-state playback and optional MDD scene."""

from pathlib import Path
import argparse,json,math,os,random,socket,struct,sys
import bpy,numpy as np
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import HERE,DATA,save,sha,ASSETS,GEOMETRY

from edit_vocab import SPEC,parameters

def material(name,color,rough=.7):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*color,1);bs.inputs['Roughness'].default_value=rough
    return m

def cube(name,loc,scale,mat,bevel=.01):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if mat:o.data.materials.append(mat)
    if bevel:
        mod=o.modifiers.new('Soft manufactured edges','BEVEL');mod.width=bevel;mod.segments=3
    return o

def cylinder(name,loc,radius,depth,mat,vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=loc)
    o=bpy.context.object;o.name=name;o.data.materials.append(mat)
    for p in o.data.polygons:p.use_smooth=True
    mod=o.modifiers.new('Edge radius','BEVEL');mod.width=min(.004,depth*.2);mod.segments=3
    return o

def mesh_object(name,vertices,faces,uv=None,mat=None):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices.tolist(),[],faces.tolist());mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    if uv is not None:
        layer=mesh.uv_layers.new(name='Artist UV')
        layer.data.foreach_set('uv',np.asarray(uv,dtype=np.float32).reshape(-1))
    if mat:mesh.materials.append(mat)
    for p in mesh.polygons:p.use_smooth=True
    return obj

def look_at(obj,point):obj.rotation_euler=(Vector(point)-obj.location).to_track_quat('-Z','Y').to_euler()

def area(name,loc,target,power,size,color=(1,1,1),size_y=None):
    d=bpy.data.lights.new(name,'AREA');d.energy=power;d.shape='RECTANGLE';d.size=size;d.size_y=size_y or size;d.color=color
    o=bpy.data.objects.new(name,d);bpy.context.collection.objects.link(o);o.location=loc;look_at(o,target);return o

def textile_detail(mat,scale=1500,distance=.00007):
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;bs=next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
    bs.inputs['Roughness'].default_value=.8
    if 'Sheen Weight'in bs.inputs:bs.inputs['Sheen Weight'].default_value=.22
    # Generated object coordinates are baked below into a rest-coordinate layer
    # for the dynamic garment, so yarn-scale texture does not swim as it falls.
    tex=nodes.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=scale;tex.inputs['Detail'].default_value=2
    coords=nodes.new('ShaderNodeTexCoord');links.new(coords.outputs['Generated'],tex.inputs['Vector'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.22;bump.inputs['Distance'].default_value=distance
    links.new(tex.outputs['Fac'],bump.inputs['Height'])
    if bs.inputs['Normal'].is_linked:links.new(bs.inputs['Normal'].links[0].from_socket,bump.inputs['Normal'])
    links.new(bump.outputs['Normal'],bs.inputs['Normal'])
    return tex

def tint_material(mat,color):
    for bs in mat.node_tree.nodes:
        if bs.type=='BSDF_PRINCIPLED':
            for link in list(bs.inputs['Base Color'].links):mat.node_tree.links.remove(link)
            bs.inputs['Base Color'].default_value=(*color,1)
    mat.diffuse_color=(*color,1)

def wood_material():
    mat=material('Photographed oak, Poly Haven wood_table_001',(.34,.24,.14),.5);n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF')
    tc=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeMapping');l.new(tc.outputs['Generated'],mapping.inputs['Vector']);mapping.inputs['Scale'].default_value=(1,3,1)
    for channel,socket in [('diff','Base Color'),('rough','Roughness'),('nor_gl','Normal')]:
        matches=list((ASSETS/'raw').glob('*'+channel+'*4k*'))
        if not matches:matches=list((ASSETS/'raw').glob('*'+channel+'*'))
        if not matches:continue
        tex=n.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(matches[0]),check_existing=True);l.new(mapping.outputs['Vector'],tex.inputs['Vector'])
        if channel!='diff':tex.image.colorspace_settings.name='Non-Color'
        if channel=='nor_gl':
            normal=n.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.35;l.new(tex.outputs['Color'],normal.inputs['Color']);l.new(normal.outputs['Normal'],bs.inputs['Normal'])
        else:l.new(tex.outputs['Color'],bs.inputs[socket])
    return mat

def room():
    random.seed(5081);wood=wood_material();wall=material('Warm chalk plaster',(.67,.65,.59),.92)
    n=wall.node_tree.nodes;l=wall.node_tree.links;bs=n.get('Principled BSDF');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=180
    bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.0004;bump.inputs['Strength'].default_value=.16;l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],bs.inputs['Normal'])
    for row in range(28):
        for col in range(7):
            x=-3.6+col*1.19+(row%3)*.397;y=-3+row*.18
            cube('Oak floor plank', (x,y,-.014),(1.187,.178,.022),wood,.0007)
    cube('Plaster wall',(0,.88,1.65),(7,.1,3.3),wall,.003)
    # Window return wall, expressed as separate jamb and sill geometry.
    frame=material('Window painted timber',(.78,.77,.72),.5)
    cube('Window deep reveal',(-1.85,.735,1.7),(1.45,.21,1.83),frame,.015)
    sky=material('Daylight through glazing',(.7,.81,.9),.2)
    sky.node_tree.nodes.get('Principled BSDF').inputs['Emission Color'].default_value=(.72,.84,1.,1)
    sky.node_tree.nodes.get('Principled BSDF').inputs['Emission Strength'].default_value=.8
    cube('Distant overcast sky',(-1.85,.61,1.7),(1.32,.01,1.68),sky,.001)
    for x in [-2.52,-1.85,-1.18]:cube('Window mullion',(x,.58,1.7),(.036,.05,1.72),frame,.004)
    for z in [.84,1.7,2.56]:cube('Window crossbar',(-1.85,.575,z),(1.38,.05,.035),frame,.004)
    cube('Deep window sill',(-1.85,.49,.82),(1.56,.37,.045),wood,.006)
    cube('Painted baseboard',(0,.80,.055),(7,.026,.11),frame,.003)
    rug=material('Wool flatweave rug',(.42,.37,.29),.98);textile_detail(rug,2100,.0005)
    cube('Lived-in woven rug',(.05,-.72,.006),(2.73,1.60,.013),rug,.032)
    # Side table, a reading book and a coffee mug give domestic context.
    cylinder('Solid oak side table top',(-1.47,-.13,.535),.265,.032,wood)
    for ang in [0,2.0944,4.1888]:
        o=cylinder('Tapered side-table leg',(-1.47+.16*math.cos(ang),-.13+.16*math.sin(ang),.265),.018,.51,wood,32)
    cover=material('Terracotta linen book cloth',(.27,.07,.035));paper=material('Uncoated book paper',(.77,.72,.61),.92)
    book=cube('Hardback book',(-1.48,-.145,.571),(.285,.192,.028),paper,.002)
    for z in [.556,.588]:cube('Linen cover',(-1.48,-.145,z),(.292,.198,.004),cover,.001)
    ceramic=material('Glazed oatmeal stoneware',(.55,.49,.38),.25)
    # Lathed open vessel, with a thick lip and visible dark coffee surface.
    vertices=[];faces=[];profile=[(.033,0),(.037,.008),(.041,.078),(.041,.084),(.037,.086),(.035,.079),(.032,.012)]
    for r,z in profile:
        for k in range(64):vertices.append([-1.37+r*math.cos(k*math.tau/64),-.06+r*math.sin(k*math.tau/64),.593+z])
    for j in range(len(profile)-1):
        for k in range(64):a=j*64+k;b=j*64+(k+1)%64;faces.append([a,b,b+64,a+64])
    mesh_object('Hand-thrown open mug',np.array(vertices),np.array(faces),mat=ceramic)
    bpy.ops.mesh.primitive_torus_add(major_radius=.025,minor_radius=.006,major_segments=48,minor_segments=12,location=(-1.316,-.06,.633),rotation=(math.pi/2,0,0));bpy.context.object.data.materials.append(ceramic)
    coffee=material('Coffee',(.018,.009,.004),.22);cylinder('Coffee surface',(-1.37,-.06,.662),.033,.001,coffee)
    # A restrained botanical print with linen mat and a fine oak frame.
    matting=material('Cotton rag art paper',(.75,.72,.64),.9)
    cube('Oak picture frame',(.66,.795,1.61),(.61,.036,.74),wood,.006)
    cube('Picture mat',(.66,.773,1.61),(.572,.005,.702),matting,.001)
    ink=material('Muted botanical ink',(.12,.18,.10),.96)
    for i in range(7):
        angle=.55+i*.25;x=.64+.085*math.sin(angle);z=1.35+i*.066
        leaf=cube('Botanical paper motif',(x,.767,z),(.055,.002,.106),ink,.02);leaf.rotation_euler[1]=(-1 if i%2 else 1)*.6
    # Fine leaves on curved midribs, not billboard cards.
    pot=material('Unglazed clay planter',(.29,.16,.10),.88);cylinder('Plant pot',(-1.55,.42,.16),.145,.30,pot)
    stemmat=material('Plant stems',(.045,.08,.025),.7)
    leaves=[material('Leaf '+str(i),(.035+i*.007,.085+i*.009,.024+i*.003),.48)for i in range(5)]
    for i in range(35):
        ang=random.uniform(0,math.tau);h=random.uniform(.52,1.08);r=random.uniform(.11,.34)
        start=Vector((-1.55,.42,.30));end=Vector((-1.55+r*math.cos(ang),.42+r*math.sin(ang),h))
        d=end-start;o=cylinder('Plant stem',(start+end)/2,.002,d.length,stemmat,10);o.rotation_euler=d.to_track_quat('Z','Y').to_euler()
        width=random.uniform(.026,.055);length=random.uniform(.12,.23);v=[]
        for k in range(9):
            t=k/8;center=end+Vector((math.cos(ang)*length*t,math.sin(ang)*length*t,math.sin(t*math.pi)*.035-.065*t))
            side=Vector((-math.sin(ang),math.cos(ang),0))*width*math.sin(math.pi*t)
            v.extend([list(center-side),list(center+Vector((0,0,.006*math.sin(math.pi*t)))),list(center+side)])
        f=[]
        for k in range(8):
            j=k*3;f.extend([[j,j+3,j+4,j+1],[j+1,j+4,j+5,j+2]])
        mesh_object('Curved leaf',np.array(v),np.array(f),mat=random.choice(leaves))
    area('Large window daylight',(-2.0,-.15,2.35),(.35,.0,.45),450,1.7,(.91,.96,1.),2.0)
    area('Soft room bounce',(1,-2.7,2.9),(.3,0,.5),170,3.2,(1,.91,.79))
    area('Window grazing detail',(-1.4,.55,1.9),(.4,-.2,.5),170,1.1,(1,.98,.93),1.6)
    world=bpy.data.worlds.new('Quiet afternoon sky');world.use_nodes=True;world.node_tree.nodes['Background'].inputs['Color'].default_value=(.52,.63,.78,1);world.node_tree.nodes['Background'].inputs['Strength'].default_value=.22;bpy.context.scene.world=world

def main(overlay=None):
    ap=argparse.ArgumentParser();ap.add_argument('--cpu',action='store_true');ap.add_argument('--cache',type=Path,required=True);ap.add_argument('--out',required=True);ap.add_argument('--case',default='source');ap.add_argument('--frames',nargs='*',type=int)
    ap.add_argument('--geometry-root',type=Path);ap.add_argument('--width',type=int,default=1280);ap.add_argument('--samples',type=int,default=128);ap.add_argument('--save-scene',action='store_true');a=ap.parse_args(sys.argv[sys.argv.index('--')+1:]);presentation=json.loads((ASSETS/'presentation.json').read_text());camera_spec=presentation['camera']
    cache=a.cache if a.cache.is_absolute() else DATA/a.cache
    with np.load(cache)as data:z={k:data[k]for k in data.files if k=='times'or k.endswith('_positions')}
    times=z['times'];out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    cachehash=sha(cache);p=parameters(a.case);geo=a.geometry_root or GEOMETRY
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    with bpy.data.libraries.load(str(ASSETS/'raw/sofa.blend'),link=False) as(src,dst):dst.objects=src.objects
    for obj in dst.objects:
        if obj:bpy.context.collection.objects.link(obj)
    fabric=bpy.data.materials.get('Fabric');tint_material(fabric,(.16,.205,.17))
    # Original normal/height/roughness images and UVs remain in this material.
    sofa_source=next(o for o in dst.objects if o and o.name.startswith('Seat part'))
    bpy.data.objects.remove(sofa_source,do_unlink=True)
    raw=np.load(ASSETS/'research/sofa_Seat part.npz');labels=np.load(ASSETS/'research/sofa_components.npz')['labels']
    mask=~np.isin(labels[raw['faces'][:,0]],[10,4,5,12,14,15])
    mesh_object('Original sofa shell, back, left cushion and accent pillow',raw['vertices'],raw['faces'][mask],raw['uv'][mask],fabric)
    dynamic={};bind={}
    for name in ['seat','pillow']:
        if name+'_positions'not in z:continue
        d=np.load(geo/(name+'_render_binding.npz'));mat=fabric
        if name=='pillow':mat=fabric.copy();mat.name='Pale blue linen pillow';tint_material(mat,(.24,.37,.43))
        dynamic[name]=mesh_object('Original '+name+' with piping',d['original_vertices'],d['faces'],d['uv'],mat)
        bind[name]=d
    with bpy.data.libraries.load(str(ASSETS/'raw/shirt.blend'),link=False) as(src,dst):dst.materials=src.materials
    cotton=next(m for m in dst.materials if m and 'Jersey'in m.name);cotton=cotton.copy();cotton.name='Ivory cotton jersey, original artist normal map';tint_material(cotton,(.59,.555,.49))
    for bs in cotton.node_tree.nodes:
        if bs.type=='BSDF_PRINCIPLED':bs.inputs['Emission Strength'].default_value=0
    from textiles import cotton_jersey,sofa_textile
    tex=cotton_jersey(cotton)
    sofa_textile(fabric)
    if 'pillow'in dynamic:sofa_textile(dynamic['pillow'].data.materials[0],((.20,.30,.35),(.27,.39,.44)))
    shirt=np.load(geo/'shirt_detail_binding.npz');shell=np.load(geo/'shirt_shell.npz');sf=shell['faces']
    body_uv=np.load(geo/'shirt_material_uv.npz')['uv']
    dynamic['shirt']=mesh_object('Cotton T-shirt physical surface',shell['vertices'],sf,body_uv,cotton)
    solidify=dynamic['shirt'].modifiers.new('Physical cotton thickness 0.45 mm','SOLIDIFY');solidify.thickness=.00045;solidify.offset=0
    dynamic['shirt_detail']=mesh_object('Artist cotton seams, cuffs, hem and stitches',shirt['artist_vertices'],shirt['faces'],shirt['uv'],cotton)
    # Stable garment rest coordinates drive the microstructure during deformation.
    for obj,rest_coords in [(dynamic['shirt'],shell['vertices']),(dynamic['shirt_detail'],shirt['artist_vertices'])]:
        attr=obj.data.attributes.new('cotton_rest','FLOAT_VECTOR','POINT');attr.data.foreach_set('vector',np.asarray(rest_coords,np.float32).reshape(-1))
        uv=obj.data.uv_layers.new(name='Knit UV');ids=np.array([loop.vertex_index for loop in obj.data.loops]);knit=np.stack([rest_coords[ids,0]/.2636027474,rest_coords[ids,2]/.2637999952],1);uv.data.foreach_set('uv',knit.astype(np.float32).reshape(-1))
    coords=cotton.node_tree.nodes.new('ShaderNodeAttribute');coords.attribute_name='cotton_rest';cotton.node_tree.links.new(coords.outputs['Vector'],tex.inputs['Vector'])
    # A narrow rib-knit collar is attached to the physical neck boundary. Its
    # positions are derived from the same FE states, never separately animated.
    shell_rest=np.load(geo/'shirt_shell.npz')['vertices']
    edges=np.concatenate([sf[:,[0,1]],sf[:,[1,2]],sf[:,[2,0]]]);unique,counts=np.unique(np.sort(edges,1),axis=0,return_counts=True)
    boundary=unique[counts==1];adj={}
    for u,v in boundary:adj.setdefault(int(u),[]).append(int(v));adj.setdefault(int(v),[]).append(int(u))
    remaining=set(adj);loops=[]
    while remaining:
        first=next(iter(remaining));loop=[first];previous=None;node=first
        while True:
            next_node=next(n for n in adj[node]if n!=previous)
            if next_node==first:break
            loop.append(next_node);previous,node=node,next_node
        remaining.difference_update(loop);loops.append(np.asarray(loop,np.int32))
    neck=max(loops,key=lambda ids:float(shell_rest[ids,2].mean()));N=len(neck);neighbor_lists=[]
    all_boundary=set(adj)
    for vertex in neck:
        ids=np.unique(sf[np.any(sf==vertex,axis=1)])
        interior=np.array([i for i in ids if i not in all_boundary],np.int32)
        neighbor_lists.append(interior if len(interior)else ids[ids!=vertex])
    initial_inner=np.array([shell_rest[ids].mean(0)for ids in neighbor_lists])
    alpha=np.minimum(.009/np.maximum(np.linalg.norm(initial_inner-shell_rest[neck],axis=1),1e-8),1.2)
    collar_faces=np.array([[i,(i+1)%N,(i+1)%N+N,i+N]for i in range(N)],np.int32)
    collar_uv=np.array([[[i/N,0],[(i+1)/N,0],[(i+1)/N,1],[i/N,1]]for i in range(N)])
    rib=material('Ivory cotton rib-knit neckline',(.54,.505,.44),.84)
    rn=rib.node_tree.nodes;rl=rib.node_tree.links;wave=rn.new('ShaderNodeTexWave');wave.bands_direction='X';wave.inputs['Scale'].default_value=200
    tc=rn.new('ShaderNodeTexCoord');rl.new(tc.outputs['UV'],wave.inputs['Vector']);bump=rn.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.00012;bump.inputs['Strength'].default_value=.3
    rl.new(wave.outputs['Color'],bump.inputs['Height']);rl.new(bump.outputs['Normal'],rn.get('Principled BSDF').inputs['Normal'])
    dynamic['collar']=mesh_object('Sewn cotton rib-knit collar',np.concatenate([shell_rest[neck],initial_inner]),collar_faces,collar_uv,rib)
    from room import build
    build(globals())
    from photographic import finish
    finish(globals(),out)
    if overlay is not None:overlay(bpy.context.scene)
    from textiles import ensure_upholstery_uv
    for item in bpy.context.scene.objects:
        if item.type=='MESH'and any(m and(m==fabric or m.name.startswith('Pale blue linen pillow'))for m in item.data.materials):ensure_upholstery_uv(item)
    scene=bpy.context.scene;camera_data=bpy.data.cameras.new('Fixed elevated three-quarter camera');camera=bpy.data.objects.new(camera_data.name,camera_data);scene.collection.objects.link(camera)
    camera.location=camera_spec['location_m'];look_at(camera,camera_spec['target_m']);camera_data.lens=camera_spec['lens_mm'];scene.camera=camera
    camera_data.dof.use_dof=True;camera_data.dof.focus_distance=(camera.location-Vector(camera_spec['focus_point_m'])).length;camera_data.dof.aperture_fstop=camera_spec['fstop']
    scene.render.engine='CYCLES';devices=[]
    if a.cpu:
        scene.cycles.device='CPU';devices=[dict(name='Host CPU',type='CPU',enabled=True)]
        scene.cycles.denoiser='OPENIMAGEDENOISE'
        if hasattr(scene.cycles,'denoising_use_gpu'):scene.cycles.denoising_use_gpu=False
    else:
        prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='CUDA';prefs.get_devices()
        for device in prefs.devices:
            device.use=device.type=='CUDA';devices.append(dict(name=device.name,type=device.type,enabled=device.use))
        if not any(d['enabled']for d in devices):raise RuntimeError('No visible CUDA render device')
        scene.cycles.device='GPU'
    scene.cycles.samples=a.samples;scene.cycles.use_denoising=True;scene.cycles.adaptive_threshold=presentation['adaptive_threshold']
    scene.cycles.max_bounces=8;scene.cycles.diffuse_bounces=4;scene.cycles.glossy_bounces=4;scene.cycles.transparent_max_bounces=8
    scene.render.resolution_x=a.width;scene.render.resolution_y=round(a.width*9/16);scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB';scene.render.film_transparent=False
    scene.render.fps=SPEC['fps'];scene.frame_start=1;scene.frame_end=len(times);scene.view_settings.view_transform='AgX';scene.view_settings.look=presentation['look'];scene.view_settings.exposure=presentation['exposure']
    scene.render.use_persistent_data=True
    # Integer object-index diagnostics accompany the beauty; these labels are
    # not fractional exposure-integrated coverage at motion-blurred boundaries.
    for name,obj in dynamic.items():obj.pass_index={'shirt':1,'shirt_detail':1,'collar':1,'seat':2,'pillow':3}[name]
    scene.view_layers[0].use_pass_object_index=True;scene.use_nodes=True
    nodes=scene.node_tree.nodes;nodes.clear();links=scene.node_tree.links
    layers=nodes.new('CompositorNodeRLayers');composite=nodes.new('CompositorNodeComposite');links.new(layers.outputs['Image'],composite.inputs['Image'])
    index_scale=nodes.new('CompositorNodeMath');index_scale.operation='DIVIDE';index_scale.inputs[1].default_value=255.
    links.new(layers.outputs['IndexOB'],index_scale.inputs[0])
    masks=nodes.new('CompositorNodeOutputFile');masks.base_path=str(out/'masks');masks.file_slots[0].path='instance_'
    masks.format.file_format='PNG';masks.format.color_mode='BW';masks.format.color_depth='8'
    masks.format.color_management='OVERRIDE';masks.format.view_settings.view_transform='Raw'
    links.new(index_scale.outputs[0],masks.inputs[0])
    def positions(frame,data=z):
        result={}
        x=data['shirt_positions'][frame].astype(float);tri=x[sf[shirt['triangles']]];u=tri[:,1]-tri[:,0];v=tri[:,2]-tri[:,0];n=np.cross(u,v);n/=np.maximum(np.linalg.norm(n,axis=1,keepdims=True),1e-20);c=shirt['coordinates']
        result['shirt_detail']=tri[:,0]+c[:,0,None]*u+c[:,1,None]*v+c[:,2,None]*n
        result['shirt']=x
        normals=np.zeros_like(x);t=x[sf];fn=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0])
        for corner in range(3):np.add.at(normals,sf[:,corner],fn)
        normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-20)
        rim=x[neck]+normals[neck]*.0012
        inner=np.array([x[ids].mean(0)for ids in neighbor_lists])
        inside=x[neck]+alpha[:,None]*(inner-x[neck])+normals[neck]*.0012
        result['collar']=np.concatenate([rim,inside])
        for name,d in bind.items():
            T=np.load(geo/(name+'_volume.npz'))['tets'];t=data[name+'_positions'][frame][T[d['tet_indices']]]
            result[name]=np.einsum('nk,nki->ni',d['weights'],t)
        return result
    exposure_path=cache.parent/'shutter_positions.npz';exposure_hash=None;playback=False
    motion_data=z;motion_times=times
    if exposure_path.is_file():
        exposure_hash=sha(exposure_path)
        with np.load(exposure_path)as data:
            if str(data['native_cache_sha256'])!=cachehash:raise RuntimeError('Exposure sidecar belongs to different physics')
            motion_data={k:data[k]for k in data.files if k=='times'or k.endswith('_positions')}
        motion_times=motion_data['times']
        expected=(times[:,None]+np.array([0,1/120,1/60])).ravel()
        if not np.allclose(motion_times,expected,rtol=0,atol=1e-10):raise RuntimeError('Camera exposure native times differ')
        for name in ['shirt','seat','pillow']:
            key=name+'_positions'
            if key in z and not np.array_equal(z[key],motion_data[key][::3]):raise RuntimeError('Exposure/video native states differ')
        scene.render.use_motion_blur=True;scene.render.motion_blur_position='START';scene.render.motion_blur_shutter=SPEC['fps']/60
    if exposure_hash or a.save_scene:
        scene_dir=out/('scene'if a.save_scene else'motion_cache');scene_dir.mkdir(exist_ok=True);streams={}
        for name,obj in dynamic.items():
            stream=(scene_dir/(name+'.mdd')).open('wb');stream.write(struct.pack('>2i',len(motion_times),len(obj.data.vertices)))
            stream.write(np.asarray(motion_times,dtype='>f4').tobytes());streams[name]=stream
        for frame in range(len(motion_times)):
            for name,v in positions(frame,motion_data).items():streams[name].write(np.asarray(v,dtype='>f4').tobytes())
        for name,stream in streams.items():
            stream.close();obj=dynamic[name];mod=obj.modifiers.new('Native physics MDD','MESH_CACHE');mod.cache_format='MDD';mod.filepath=str(scene_dir/(name+'.mdd'))
            # Blender 4.3 applies frame_start AFTER conversion to seconds in
            # TIME mode. 1/fps, not 1, aligns scene frame 1 to native time 0.
            mod.time_mode='TIME';mod.play_mode='SCENE';mod.frame_start=1/SPEC['fps'];mod.frame_scale=1
            mod.deform_mode='OVERWRITE';mod.factor=1.;mod.forward_axis='POS_Y';mod.up_axis='POS_Z'
            obj.cycles.use_motion_blur=True;obj.cycles.use_deform_motion=True;obj.cycles.motion_steps=1
            bpy.context.view_layer.objects.active=obj
            while obj.modifiers.find(mod.name)>0:bpy.ops.object.modifier_move_up(modifier=mod.name)
        playback=True
    frames=a.frames if a.frames is not None else list(range(len(times)))
    for frame in frames:
        if not playback:
            for name,v in positions(frame).items():dynamic[name].data.vertices.foreach_set('co',np.asarray(v,dtype=np.float32).reshape(-1));dynamic[name].data.update()
        scene.frame_set(frame+1);scene.render.filepath=str(out/('frame_%04d.png'%frame));bpy.ops.render.render(write_still=True)
        print('RENDERED',frame,flush=True)
    if a.save_scene:
        for name,v in positions(0).items():dynamic[name].data.vertices.foreach_set('co',np.asarray(v,dtype=np.float32).reshape(-1));dynamic[name].data.update()
        scene.frame_set(1);masks.base_path='//preview_masks';scene.render.filepath='//preview.png'
        bpy.ops.file.pack_all()
        for name,obj in dynamic.items():obj.modifiers.get('Native physics MDD').filepath='//'+name+'.mdd'
        bpy.ops.wm.save_as_mainfile(filepath=str(scene_dir/'living_room.blend'))
    if sha(cache)!=cachehash:raise RuntimeError('Rendering changed physics cache')
    if exposure_hash and sha(exposure_path)!=exposure_hash:raise RuntimeError('Rendering changed exposure cache')
    fx=scene.render.resolution_x*camera_data.lens/camera_data.sensor_width
    camera_calibration=dict(matrix_world=[list(r)for r in camera.matrix_world],world_to_blender_camera=[list(r)for r in camera.matrix_world.inverted()],
        K=[[fx,0,scene.render.resolution_x/2],[0,fx,scene.render.resolution_y/2],[0,0,1]],
        projection_convention='Blender camera coordinates converted to computer vision by (x,-y,-z); image origin at top left; pixel aspect 1.',
        sensor_width_mm=camera_data.sensor_width,lens_mm=camera_data.lens,resolution=[scene.render.resolution_x,scene.render.resolution_y])
    save(out/'render_report.json',dict(case_id=a.case,worker_host=socket.gethostname(),gpu_uuid=os.environ.get('CUDA_VISIBLE_DEVICES'),devices=devices,
        blender_version=bpy.app.version_string,engine='Cycles CPU'if a.cpu else'Cycles CUDA',resolution=[scene.render.resolution_x,scene.render.resolution_y],samples=a.samples,frames=frames,native_times_s=[float(times[i])for i in frames],diagnostic_geometry_root=str(a.geometry_root)if a.geometry_root else None,
        cache_sha256=cachehash,exposure_cache_sha256=exposure_hash,camera_exposure=dict(enabled=bool(exposure_hash),shutter_seconds=1/60 if exposure_hash else 0,position='starts at canonical native frame time',deformation_samples=3 if exposure_hash else 1,temporal_scope='Native substep positions at t, t+1/120 and t+1/60; Cycles integrates the piecewise-linear deforming surface within that exposure, without changing the 24 fps physical timeline.'),source_shader='Poly Haven photographed cotton jersey with immutable rest-space knit UVs; metre-calibrated artist upholstery UVs with photographed yarn occlusion/normal/roughness and microfiber sheen; Poly Haven wool rug and linen curtain. See pinned asset manifest.',
        deformation='Exact physical cloth body with symmetric 0.45 mm thickness, artist UV/normal transfer, embedded artist stitches/cuffs/hem and FE-attached rib collar; native cushion/pillow embeddings. No motion filtering, gains or retiming.',camera=camera_spec,presentation_definition=presentation,presentation_sha256=sha(ASSETS/'presentation.json'),physics_revision='repeat solve with the unchanged material model and released initial state',camera_calibration=camera_calibration,local_blender_invoked=False))

if __name__=='__main__':main()
