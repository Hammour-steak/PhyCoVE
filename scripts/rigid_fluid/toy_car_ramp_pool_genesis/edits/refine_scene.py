"""Metre-scale material wear, motivated daylight and 3D foliage shadows."""
import argparse,hashlib,json,math,random,sys,time
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from lighting_profiles import apply_lighting,lighting_state,PROFILES,base

PROFILES['daylight']={'environment_strength':.36,'sun_energy':2.35,'sun_angle_degrees':.75,'exposure':.15}
RNG=random.Random(2026102714)

def node(mat,kind,name):
    n=mat.node_tree.nodes.new(kind);n.name=name;n.label=name;return n

def put(mat,value,socket):
    if hasattr(value,'is_output'): mat.node_tree.links.new(value,socket)
    else: socket.default_value=value

def mathnode(mat,op,a,b=0,name='math'):
    n=node(mat,'ShaderNodeMath',name);n.operation=op
    put(mat,a,n.inputs[0]);put(mat,b,n.inputs[1]);return n.outputs[0]

def world(mat):
    n=node(mat,'ShaderNodeTexCoord','Metre Coordinates')
    anchor=bpy.data.objects.get('WorldOrigin');n.object=anchor
    return n.outputs['Object']

def noise(mat,vec,scale,name):
    n=node(mat,'ShaderNodeTexNoise',name);n.inputs['Scale'].default_value=scale
    n.inputs['Detail'].default_value=3;mat.node_tree.links.new(vec,n.inputs['Vector']);return n.outputs['Fac']

def mix(mat,factor,a,b,mode='MIX',name='mix'):
    n=node(mat,'ShaderNodeMixRGB',name);n.blend_type=mode
    for v,s in [(factor,n.inputs[0]),(a,n.inputs[1]),(b,n.inputs[2])]:put(mat,v,s)
    return n.outputs[0]

def copy_material(old_name,new_name,object_filter=None):
    old=bpy.data.materials[old_name];mat=old.copy();mat.name=new_name
    for obj in bpy.context.scene.objects:
        if not hasattr(obj.data,'materials') or object_filter and not object_filter(obj):continue
        for i,m in enumerate(obj.data.materials):
            if m==old: obj.data.materials[i]=mat
    return mat

def linked_value(bsdf,name):
    socket=bsdf.inputs[name]
    return socket.links[0].from_socket if socket.is_linked else socket.default_value

def ellipse(mat,vec,center,radius,name):
    sub=node(mat,'ShaderNodeVectorMath',name+' position');sub.operation='SUBTRACT'
    put(mat,vec,sub.inputs[0]);sub.inputs[1].default_value=(*center,0)
    mul=node(mat,'ShaderNodeVectorMath',name+' dimensions');mul.operation='MULTIPLY'
    put(mat,sub.outputs[0],mul.inputs[0]);mul.inputs[1].default_value=(1/radius[0],1/radius[1],0)
    length=node(mat,'ShaderNodeVectorMath',name+' radius');length.operation='LENGTH';put(mat,mul.outputs[0],length.inputs[0])
    r=node(mat,'ShaderNodeMapRange',name+' feather');r.clamp=True;r.interpolation_type='SMOOTHERSTEP'
    put(mat,length.outputs['Value'],r.inputs['Value'])
    r.inputs['From Min'].default_value=.18;r.inputs['From Max'].default_value=1
    r.inputs['To Min'].default_value=1;r.inputs['To Max'].default_value=0
    return r.outputs[0]

def refine_paving():
    mat=copy_material('Scanned_Concrete_Pavement_4K','Paving_Dry_and_Damp')
    bs=mat.node_tree.nodes.get('Principled BSDF');vec=world(mat)
    color=linked_value(bs,'Base Color');rough=linked_value(bs,'Roughness')
    ao=next(n for n in mat.node_tree.nodes if n.bl_idname=='ShaderNodeTexImage' and n.image and '_ao_' in n.image.name)
    color=mix(mat,.28,color,ao.outputs[0],'MULTIPLY','Registered micro-occlusion')
    front=ellipse(mat,vec,(.90,-.55),(.57,.22),'Pool-edge dampness')
    hose=ellipse(mat,vec,(1.40,.79),(.37,.29),'Hose-area dampness')
    damp=mathnode(mat,'MAXIMUM',front,hose)
    broken=mathnode(mat,'MULTIPLY_ADD',noise(mat,vec,12,'Moisture breakup'),.9)
    # MULTIPLY_ADD's final socket sets the floor of the irregular wet mask.
    broken.node.inputs[2].default_value=.10
    damp=mathnode(mat,'MULTIPLY',damp,broken)
    damp=mathnode(mat,'MULTIPLY',damp,.58)
    dark=mix(mat,1,color,(.53,.55,.54,1),'MULTIPLY','Damp aggregate')
    put(mat,mix(mat,damp,color,dark,name='Dry to damp colour'),bs.inputs['Base Color'])
    put(mat,mix(mat,damp,rough,(.27,.27,.27,1),name='Dry to damp roughness'),bs.inputs['Roughness'])
    return {'registered_ao_mix':.28,'damp_mask_max':.58,'damp_roughness_target':.27,
       'note':'Static surface moisture from pool setup; no solver-generated wetness is claimed.'}

def refine_gravel():
    obj=bpy.data.objects['Continuous_Gravel_Bed']
    uv=obj.data.uv_layers.new(name='2p5m_Ground_UV')
    coords=np.array([v.co[:] for v in obj.data.vertices],dtype=np.float32)
    ids=np.empty(len(obj.data.loops),dtype=np.int32);obj.data.loops.foreach_get('vertex_index',ids)
    uv.data.foreach_set('uv',(coords[ids,:2]/2.5).flatten())
    mat=copy_material('Gravelly_Sand_Photographic','Gravel_Registered_PBR')
    ns,ls=mat.node_tree.nodes,mat.node_tree.links
    uvnode=node(mat,'ShaderNodeUVMap','Ground Tangents');uvnode.uv_map=uv.name
    for n in ns:
        if n.bl_idname=='ShaderNodeTexImage':n.projection='FLAT';ls.new(uvnode.outputs[0],n.inputs['Vector'])
    bs=ns.get('Principled BSDF');vec=world(mat);color=linked_value(bs,'Base Color')
    mottling=noise(mat,vec,2.1,'Root-zone soil variation')
    ramp=node(mat,'ShaderNodeValToRGB','Soil mineral and humus')
    ramp.color_ramp.elements[0].color=(.48,.44,.36,1);ramp.color_ramp.elements[0].position=.25
    ramp.color_ramp.elements[1].color=(1,1,1,1);ramp.color_ramp.elements[1].position=.75
    put(mat,mottling,ramp.inputs[0])
    put(mat,mix(mat,.45,color,ramp.outputs[0],'MULTIPLY','Soil moisture variation'),bs.inputs['Base Color'])
    return {'uv_repeat_m':2.5,'normal_map':'Registered planar UV, tangent space','humus_mix':.45}

def refine_curbs():
    mat=copy_material('Curb_WarmGrey_Concrete','Weathered_Stone_Edging',lambda o:o.name.startswith(('Back_Curb','Left_Curb')))
    bs=mat.node_tree.nodes.get('Principled BSDF');vec=world(mat)
    original=linked_value(bs,'Base Color')
    tex=node(mat,'ShaderNodeTexImage','Cast-stone photographic grain')
    tex.image=bpy.data.images['white_stucco_diff_4k.jpg'];tex.projection='BOX';tex.projection_blend=.2
    mapping=node(mat,'ShaderNodeVectorMath','Cast-stone texture scale');mapping.operation='SCALE';mapping.inputs[3].default_value=1/.70
    put(mat,vec,mapping.inputs[0]);put(mat,mapping.outputs[0],tex.inputs['Vector'])
    color=mix(mat,.45,original,tex.outputs[0],'MULTIPLY','Mineral texture')
    xyz=node(mat,'ShaderNodeSeparateXYZ','Curb height');put(mat,vec,xyz.inputs[0])
    foot=node(mat,'ShaderNodeMapRange','Soil splash at curb base');foot.clamp=True
    put(mat,xyz.outputs['Z'],foot.inputs['Value'])
    foot.inputs['From Min'].default_value=-.012;foot.inputs['From Max'].default_value=.035
    foot.inputs['To Min'].default_value=.5;foot.inputs['To Max'].default_value=0
    mask=mathnode(mat,'MULTIPLY',foot.outputs[0],noise(mat,vec,19,'Irregular soil contact'))
    put(mat,mix(mat,mask,color,(.10,.085,.055,1),name='Fine soil staining'),bs.inputs['Base Color'])
    count=0
    for o in bpy.context.scene.objects:
        if not o.name.startswith(('Back_Curb','Left_Curb')):continue
        bevel=next((m for m in o.modifiers if m.type=='BEVEL'),None)
        if bevel:bevel.width=RNG.uniform(.0017,.0030)
        texture=bpy.data.textures.new('Submillimetre mineral edge','CLOUDS');texture.noise_scale=.027
        dis=o.modifiers.new('Small weathered edge variation','DISPLACE');dis.texture=texture
        dis.strength=.00065;dis.mid_level=.5;dis.texture_coords='GLOBAL';count+=1
    return {'blocks':count,'displacement_m':.00065,'bevel_range_m':[.0017,.0030],'soil_contact_stain':True}

def refine_toy_finish():
    result={}
    for old in ['PCVE_TrackOrangePolypropylene','PCVE_TrackGraphiteSupports']:
        mat=copy_material(old,old+'_refined')
        if bpy.data.materials[old].users==0:bpy.data.materials.remove(bpy.data.materials[old]);mat.name=old
        bs=mat.node_tree.nodes.get('Principled BSDF');vec=world(mat)
        no=noise(mat,vec,420,'Fine moulded surface')
        r=node(mat,'ShaderNodeMapRange','Handling roughness');put(mat,no,r.inputs['Value'])
        r.inputs['To Min'].default_value=.30 if 'Orange' in old else .40
        r.inputs['To Max'].default_value=.39 if 'Orange' in old else .53
        put(mat,r.outputs[0],bs.inputs['Roughness']);result[old]=[r.inputs['To Min'].default_value,r.inputs['To Max'].default_value]
    mat=copy_material('Childrens Inflatable Pool','Printed_PVC')
    bs=mat.node_tree.nodes.get('Principled BSDF')
    for l in list(bs.inputs['Metallic'].links):mat.node_tree.links.remove(l)
    bs.inputs['Metallic'].default_value=0
    result['PVC_metallic']=0
    return result

def collection(name):
    col=bpy.data.collections.new(name);bpy.context.scene.collection.children.link(col);return col

def instance(name,mesh,col,location,scale=1,rotation=(0,0,0)):
    obj=bpy.data.objects.new(name,mesh);col.objects.link(obj)
    obj.location=location;obj.scale=(scale,)*3;obj.rotation_euler=rotation;return obj

def leaf_mesh(name,mat,dry=False):
    # One metre long reference leaf, including a raised midrib and curled margin.
    vertices=[];faces=[];rows=13
    for i in range(rows):
        u=i/(rows-1);half=.205*math.sin(math.pi*u)**.85
        for side in [-1,0,1]:
            z=.018*math.sin(math.pi*u)*(1-abs(side))
            if dry:z+=.032*(abs(side)**2)+.018*math.sin(u*math.tau)
            vertices.append((u-.5,side*half,z))
    for i in range(rows-1):
        for j in range(2):faces.append((3*i+j,3*(i+1)+j,3*(i+1)+j+1,3*i+j+1))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.materials.append(mat)
    for p in mesh.polygons:p.use_smooth=True
    return mesh

def curve_branch(name,points,radius,mat,col):
    data=bpy.data.curves.new(name,'CURVE');data.dimensions='3D';data.bevel_depth=radius;data.bevel_resolution=2
    spline=data.splines.new('POLY');spline.points.add(len(points)-1)
    for p,xyz in zip(spline.points,points):p.co=(*xyz,1)
    obj=bpy.data.objects.new(name,data);col.objects.link(obj);data.materials.append(mat);return obj

def add_canopy():
    col=collection('Off_Frame_Tree_Canopy')
    mat=base.shader('Tree_Leaf',(.045,.085,.012),.63)
    ns,ls=mat.node_tree.nodes,mat.node_tree.links;bs=ns.get('Principled BSDF')
    output=next(n for n in ns if n.type=='OUTPUT_MATERIAL')
    trans=node(mat,'ShaderNodeBsdfTranslucent','Thin leaf light');trans.inputs[0].default_value=(.12,.22,.035,1)
    blend=node(mat,'ShaderNodeMixShader','Thin leaf');blend.inputs[0].default_value=.14
    ls.new(bs.outputs[0],blend.inputs[1]);ls.new(trans.outputs[0],blend.inputs[2]);ls.new(blend.outputs[0],output.inputs['Surface'])
    mesh=leaf_mesh('Canopy_Leaf_Mesh',mat)
    bark=base.shader('Small_Branch',(.075,.057,.031),.88)
    count=0;tips=[]
    # Positions are built in 3D along the actual incoming sun direction.
    # Projected patches sit mainly on the foreground paving and left garden edge.
    for cluster,(cx,cy,rx,ry,number) in enumerate([(-.62,-1.18,.95,.51,190),(-1.56,.42,.68,.53,110)]):
        for i in range(number):
            angle=RNG.random()*math.tau;r=math.sqrt(RNG.random())
            gx=cx+rx*math.cos(angle)*r;gy=cy+ry*math.sin(angle)*r
            z=RNG.uniform(2.42,2.78);x=gx-z/math.sqrt(2);y=gy-z/math.sqrt(2)
            length=RNG.uniform(.055,.095)
            instance(f'Canopy_Leaf_{count:03d}',mesh,col,(x,y,z),length,
                     (RNG.uniform(-.38,.38),RNG.uniform(-.45,.45),RNG.random()*math.tau))
            if i%35==0:tips.append(Vector((x,y,z)))
            count+=1
    origin=Vector((-4.6,-3.65,3.15))
    for i,tip in enumerate(tips):
        middle=origin.lerp(tip,.63);middle.z-=.08
        curve_branch(f'Canopy_Twig_{i:02d}',[origin,middle,tip],.0038,bark,col)
    return {'leaf_count':count,'twig_count':len(tips),'height_m':[2.42,2.78],
            'method':'Real off-frame 3D leaves and branches, visible to all ray types; no image-based shadow mask'}

def add_fallen_leaves():
    col=collection('Sparse_Garden_Debris')
    mat=base.shader('Dry_Leaf',(.13,.075,.026),.86)
    ns,ls=mat.node_tree.nodes,mat.node_tree.links;bs=ns.get('Principled BSDF')
    info=node(mat,'ShaderNodeObjectInfo','Leaf colour variation')
    ramp=node(mat,'ShaderNodeValToRGB','Brown and olive leaves')
    ramp.color_ramp.elements[0].color=(.08,.066,.023,1)
    ramp.color_ramp.elements[1].color=(.22,.12,.035,1)
    ls.new(info.outputs['Random'],ramp.inputs[0]);ls.new(ramp.outputs[0],bs.inputs['Base Color'])
    bump=node(mat,'ShaderNodeBump','Dry leaf veins');bump.inputs['Strength'].default_value=.15;bump.inputs['Distance'].default_value=.00018
    vec=world(mat);ls.new(noise(mat,vec,600,'Leaf fibre'),bump.inputs['Height']);ls.new(bump.outputs[0],bs.inputs['Normal'])
    mesh=leaf_mesh('Fallen_Leaf_Mesh',mat,dry=True)
    paving=bpy.data.objects['ScannedPatio_TrueRelief'];inv=paving.matrix_world.inverted()
    points=[(-1.88,1.39),(-1.41,1.49),(-.61,1.49),(.23,1.45),(1.30,1.48),(2.13,1.41),
            (-2.00,.91),(-1.96,.18),(-1.91,-.57),(-1.97,-1.33),(-1.84,-1.80),
            (-.93,-1.68),(.12,-1.41),(.62,-1.22)]
    records=[]
    for i,(x,y) in enumerate(points):
        start=inv@Vector((x,y,1));direction=inv.to_3x3()@Vector((0,0,-1))
        hit,loc,normal,index=paving.ray_cast(start,direction)
        assert hit,(x,y)
        z=(paving.matrix_world@loc).z+.00035
        size=RNG.uniform(.035,.058)
        instance(f'Fallen_Leaf_{i:02d}',mesh,col,(x,y,z),size,(0,0,RNG.random()*math.tau))
        records.append({'position_m':[x,y,z],'length_m':size})
    return {'count':len(records),'placements':records,'contact':'Ray-cast onto unchanged paving relief'}

def refine_fence():
    mat=copy_material('Weathered_Wood_4K','Aged_Timber_Fence',lambda o:o.name.startswith(('Fence_Rear_','Fence_Left_','Fence_Post_')))
    bs=mat.node_tree.nodes.get('Principled BSDF');vec=world(mat);color=linked_value(bs,'Base Color')
    xyz=node(mat,'ShaderNodeSeparateXYZ','Timber height');put(mat,vec,xyz.inputs[0])
    foot=node(mat,'ShaderNodeMapRange','Timber ground weathering');foot.clamp=True
    put(mat,xyz.outputs['Z'],foot.inputs['Value'])
    foot.inputs['From Min'].default_value=0;foot.inputs['From Max'].default_value=.16
    foot.inputs['To Min'].default_value=.42;foot.inputs['To Max'].default_value=0
    mask=mathnode(mat,'MULTIPLY',foot.outputs[0],noise(mat,vec,12,'Timber foot irregularity'))
    dark=mix(mat,1,color,(.50,.54,.41,1),'MULTIPLY','Timber soil contact')
    put(mat,mix(mat,mask,color,dark,name='Light foot staining'),bs.inputs['Base Color'])
    col=collection('Fence_Construction_Details')
    metal=base.shader('Oxidised_Fasteners',(.11,.105,.09),.68)
    metal.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value=.62
    bpy.ops.mesh.primitive_uv_sphere_add(segments=8,ring_count=4,radius=1)
    temp=bpy.context.object;mesh=temp.data;mesh.name='Fence_Nailhead_Mesh';mesh.materials.append(metal)
    bpy.data.objects.remove(temp,do_unlink=True)
    count=0
    for obj in list(bpy.context.scene.objects):
        if not obj.name.startswith(('Fence_Rear_','Fence_Left_')):continue
        rear=obj.name.startswith('Fence_Rear_')
        for z in [.26,1.16]:
            for offset in [-.043,.043]:
                xyz=(obj.location.x+offset,3.5359,z) if rear else (-3.4659,obj.location.y+offset,z)
                nail=instance(f'Nail_{count:03d}',mesh,col,xyz)
                nail.scale=(.0016,.0006,.0016) if rear else (.0006,.0016,.0016);count+=1
    # Horizontal rails sit behind the boards and tie the existing posts together.
    for side,coords in [('Rear',[(.55,3.60,.26),(.55,3.60,1.16)]),('Left',[(-3.53,.25,.26),(-3.53,.25,1.16)])]:
        for i,pos in enumerate(coords):
            size=(8.1,.045,.075) if side=='Rear' else (.045,6.6,.075)
            bpy.ops.mesh.primitive_cube_add(size=1,location=pos);obj=bpy.context.object;obj.name=f'Fence_Rail_{side}_{i}'
            obj.dimensions=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
            for c in list(obj.users_collection):c.objects.unlink(obj)
            col.objects.link(obj);obj.data.materials.append(mat)
            bevel=obj.modifiers.new('Rail corner radius','BEVEL');bevel.width=.0015;bevel.segments=2
    return {'fasteners':count,'rails':4,'ground_stain_height_m':.16}

def protected_snapshot():
    result=base.environment_signature()
    result['fixed_geometry']={}
    for obj in bpy.context.scene.objects:
        if not (obj.name.startswith('PCVE_Toy') or obj.name=='ScannedPatio_TrueRelief'):continue
        record={'matrix':[list(row) for row in obj.matrix_world],'type':obj.type}
        if obj.type=='MESH':
            vertices=np.empty(len(obj.data.vertices)*3,dtype=np.float32);obj.data.vertices.foreach_get('co',vertices)
            loops=np.empty(len(obj.data.loops),dtype=np.int32);obj.data.loops.foreach_get('vertex_index',loops)
            record['mesh_sha256']=hashlib.sha256(vertices.tobytes()+loops.tobytes()).hexdigest()
        record['modifiers']=[{'type':m.type,'name':m.name} for m in obj.modifiers]
        if obj.rigid_body:record['rigid_body']={k:getattr(obj.rigid_body,k) for k in ['type','mass','friction','restitution','collision_shape','use_margin','collision_margin']}
        result['fixed_geometry'][obj.name]=record
    camera=bpy.context.scene.camera
    result['camera'].update({'sensor_width':camera.data.sensor_width,'sensor_fit':camera.data.sensor_fit,
        'dof':{'enabled':camera.data.dof.use_dof,'fstop':camera.data.dof.aperture_fstop,
               'focus_object':camera.data.dof.focus_object.name if camera.data.dof.focus_object else None,
               'focus_distance':camera.data.dof.focus_distance}})
    result['frame']=bpy.context.scene.frame_current
    scene=bpy.context.scene;rb=scene.rigidbody_world
    result['simulation']={'frame_start':scene.frame_start,'frame_end':scene.frame_end,'fps':scene.render.fps,
        'gravity':list(scene.gravity),'rigidbody_world':None if rb is None else {
            'time_scale':rb.time_scale,'substeps_per_frame':rb.substeps_per_frame,'solver_iterations':rb.solver_iterations,
            'cache_start':rb.point_cache.frame_start,'cache_end':rb.point_cache.frame_end}}
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--save',action='store_true');p.add_argument('--beauty',action='store_true')
    p.add_argument('--render-before',action='store_true')
    p.add_argument('--skip-preview',action='store_true');p.add_argument('--no-canopy',action='store_true')
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:]);args.out.mkdir(parents=True,exist_ok=True)
    scene=bpy.context.scene;before=protected_snapshot();lights_before=lighting_state(scene)
    base.configure_gpu(scene,32);scene.render.resolution_x=1280;scene.render.resolution_y=720
    scene.cycles.use_adaptive_sampling=True;scene.cycles.adaptive_threshold=.02
    baseline_render=None
    if args.render_before:
        scene.render.filepath=str(args.out/'before.png');started=time.monotonic()
        bpy.ops.render.render(write_still=True)
        baseline_render={'seconds':time.monotonic()-started,'resolution':[1280,720],'samples':32}
    started=time.monotonic()
    record={'revision':'realism_refinement','source':bpy.data.filepath,'seed':2026102714,'appearance_only':True,
            'protected_before':before,'lighting_before':lights_before}
    record['paving']=refine_paving();record['gravel']=refine_gravel();record['edging']=refine_curbs()
    record['toy_materials']=refine_toy_finish();record['fence']=refine_fence()
    record['fallen_leaves']=add_fallen_leaves()
    if not args.no_canopy:record['canopy']=add_canopy()
    apply_lighting(scene,'daylight');record['lighting_after']=lighting_state(scene)
    scene.view_settings.gamma=1
    scene.cycles.use_adaptive_sampling=True;scene.cycles.adaptive_threshold=.02
    base.configure_gpu(scene,32);scene.render.resolution_x=1280;scene.render.resolution_y=720
    record['protected_after']=protected_snapshot()
    assert before==record['protected_after'],'Action geometry, paving, camera or physics changed'
    record['build_seconds']=time.monotonic()-started;record['renders']={}
    if baseline_render:record['renders']['baseline_comparison']=baseline_render
    record['devices']=[{'name':d.name,'type':d.type,'enabled':d.use} for d in bpy.context.preferences.addons['cycles'].preferences.devices]
    if args.save:
        bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(args.out/'scene_realism.blend'),compress=True)
    if not args.skip_preview:
        scene.render.filepath=str(args.out/'after.png');started=time.monotonic()
        bpy.ops.render.render(write_still=True)
        record['renders']['comparison']={'seconds':time.monotonic()-started,'resolution':[1280,720],'samples':32}
    if args.beauty:
        scene.render.resolution_x=1920;scene.render.resolution_y=1080;scene.cycles.samples=128
        scene.cycles.adaptive_threshold=.008;scene.render.filepath=str(args.out/'beauty_1080p.png');started=time.monotonic()
        bpy.ops.render.render(write_still=True)
        record['renders']['beauty']={'seconds':time.monotonic()-started,'resolution':[1920,1080],'samples':128}
        if args.save:bpy.ops.wm.save_as_mainfile(filepath=str(args.out/'scene_realism.blend'),compress=True)
    record['scope']='Appearance and lighting refinement, frame-32 snapshot; no physics cache rebake or full animation regeneration.'
    (args.out/'realism_manifest.json').write_text(json.dumps(record,indent=2));print('REALISM_DONE',args.out,flush=True)

if __name__=='__main__':main()
