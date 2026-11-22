"""Remote Cycles scene reconstruction; replays only solved physical states."""
import hashlib,json,math,os,sys
from pathlib import Path
if os.name=='nt' or not sys.platform.startswith('linux'):
    raise RuntimeError('Blender rendering runs on a Linux GPU host')
import bpy
import numpy as np
from mathutils import Vector,Matrix
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3]
DATA=REPO/'renders/thomas_dual_spring_train'
ASSETS=DATA/'assets'
TABLE=.560;RUN=TABLE+.009

def mat(name,color,rough=.5,metal=0):
    m=bpy.data.materials.new(name);m.use_nodes=True
    p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Roughness'].default_value=rough;p.inputs['Metallic'].default_value=metal
    return m

def finish(m,scale=5000,amplitude=.00002,strength=.15):
    n=m.node_tree.nodes;l=m.node_tree.links;p=n.get('Principled BSDF')
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=scale;noise.inputs['Detail'].default_value=3
    co=n.new('ShaderNodeTexCoord');l.new(co.outputs['Object'],noise.inputs['Vector'])
    bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=amplitude;bump.inputs['Strength'].default_value=strength
    l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],p.inputs['Normal'])
    return m

def box(name,loc,size,material,bevel=.001):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if material:o.data.materials.append(material)
    if bevel:
        b=o.modifiers.new('Small real edge radius','BEVEL');b.width=bevel;b.segments=3
        o.modifiers.new('Face normals','WEIGHTED_NORMAL')
    return o

def cyl(name,loc,r,depth,material,axis='Z',segments=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=segments,radius=r,depth=depth,location=loc)
    o=bpy.context.object;o.name=name
    if axis=='X':o.rotation_euler[1]=math.pi/2
    if axis=='Y':o.rotation_euler[0]=math.pi/2
    o.data.materials.append(material)
    for p in o.data.polygons:p.use_smooth=len(p.vertices)==4
    b=o.modifiers.new('Deburred rim','BEVEL');b.width=min(.0003,depth/5);b.segments=3
    o.modifiers.new('Capped normals','WEIGHTED_NORMAL')
    return o

def append_blend(p):
    with bpy.data.libraries.load(str(p),link=False) as (src,dst):
        original_names=tuple(src.objects);dst.objects=list(original_names)
    for original,o in zip(original_names,dst.objects):
        if o is not None and o.name not in bpy.context.scene.objects:bpy.context.scene.collection.objects.link(o)
        if o is not None:o['_source_name']=original
    bpy.context.view_layer.update()
    return [o for o in dst.objects if o]

def pbr_wood():
    d=json.loads((ASSETS/'wood_table/manifest.json').read_text())
    m=mat('Scanned real wood - CC0 Poly Haven',(.48,.32,.16),.44)
    n=m.node_tree.nodes;l=m.node_tree.links;p=n.get('Principled BSDF')
    co=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY';mapping.inputs[1].default_value=(1.2,4.0,1.0)
    l.new(co.outputs['Object'],mapping.inputs[0])
    for ch,sock in [('Diffuse','Base Color'),('Rough','Roughness'),('nor_gl','Normal')]:
        tex=n.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(ASSETS/d['files'][ch]['path'].removeprefix('assets/')),check_existing=True)
        if ch!='Diffuse':tex.image.colorspace_settings.name='Non-Color'
        l.new(mapping.outputs[0],tex.inputs['Vector'])
        if ch=='nor_gl':
            norm=n.new('ShaderNodeNormalMap');norm.inputs['Strength'].default_value=.4
            l.new(tex.outputs['Color'],norm.inputs['Color']);l.new(norm.outputs['Normal'],p.inputs[sock])
        elif ch=='Diffuse':
            hue=n.new('ShaderNodeHueSaturation');hue.inputs['Saturation'].default_value=.72;hue.inputs['Value'].default_value=1.2
            l.new(tex.outputs['Color'],hue.inputs['Color']);l.new(hue.outputs['Color'],p.inputs[sock])
        else:l.new(tex.outputs['Color'],p.inputs[sock])
    p.inputs['Coat Weight'].default_value=.08;p.inputs['Coat Roughness'].default_value=.33
    return m

def make_table():
    objs=append_blend(ASSETS/'noos_table/asset.blend')
    keep={'Cube','Cube.002','Cube.003'}
    transforms={o.name:o.matrix_world.copy() for o in objs}
    sc=Matrix.Diagonal((1.80,1.15,TABLE/.3578780293,1.))
    used=[]
    for o in objs:
        if o.get('_source_name') in keep and o.type=='MESH':
            old=transforms[o.name];o.parent=None;o.matrix_world=sc@old
            o.hide_render=False;o.hide_viewport=False;o.hide_set(False);o.visible_camera=True;o.show_instancer_for_render=True
            o['asset_source']='BlenderKit Noos DUO';used.append(o.name)
        else:bpy.data.objects.remove(o,do_unlink=True)
    return used

def make_track(wood):
    # Four machined segments, real 3 mm wheel grooves, modest end seams.
    for j in range(4):
        x=-.405+j*.270
        box('Track substrate '+str(j),(x,0,TABLE+.0045),(.2696,.073,.009),wood,.0007)
        for name,y,w in [('near',-.0304,.0122),('center',0,.0306),('far',.0304,.0122)]:
            box('Track raised '+name+str(j),(x,y,TABLE+.0105),(.2696,w,.003),wood,.00065)
    # Exposed puzzle tongues join the segments below the running grooves.
    for j in range(3):
        x=-.270+j*.270
        cyl('Circular wood track tongue '+str(j),(x,.0,TABLE+.004),.008,.0078,wood)

def make_room(wood):
    wall=finish(mat('Warm ivory painted plaster',(.72,.73,.66),.88),180,.00035,.16)
    sage=finish(mat('Muted sage lower wall',(.22,.33,.29),.8),220,.0002,.12)
    floor=mat('Warm oak floor',(.20,.12,.065),.52)
    for i in range(26):
        box('Floor board '+str(i),(-2+i*.16,0,-.012),(.159,5,.024),wood,.001)
    box('Back plaster wall',(0,1.9,1.6),(6,.12,3.2),wall,.0)
    box('Back sage wainscot',(0,1.82,.43),(6,.025,.86),sage,.002)
    trim=mat('Ivory satin trim',(.78,.76,.68),.43)
    box('Dado trim',(0,1.797,.864),(6,.032,.026),trim,.003)
    box('Room skirting',(0,1.795,.055),(6,.04,.11),trim,.003)
    box('Left side plaster',(-2,0,1.6),(.10,4,3.2),wall,0)
    # A simple window frame makes the origin of the broad daylight readable.
    glass=mat('Daylight visible through window',(.62,.73,.76),.4)
    bs=glass.node_tree.nodes.get('Principled BSDF');bs.inputs['Emission Color'].default_value=(.62,.73,.76,1);bs.inputs['Emission Strength'].default_value=.3
    box('Window sky',(-1.937,.15,1.55),(.006,1.25,1.3),glass,.0)
    for y in [-.49,.15,.79]:box('Window vertical stile',(-1.91,y,1.55),(.055,.035,1.37),trim,.002)
    for z in [.88,1.55,2.22]:box('Window horizontal stile',(-1.91,.15,z),(.055,1.32,.035),trim,.002)

def make_props(wood):
    # Few spare rails and wooden blocks; no unrelated tabletop clutter.
    for j in range(2):
        o=box('Spare wooden rail '+str(j),(-.27+j*.07,.285+j*.035,TABLE+.008+j*.016),(.235,.073,.016),wood,.0015)
        o.rotation_euler[2]=.08+j*.17
        for y in [-.020,.020]:
            groove=box('Spare track groove '+str(j)+str(y),(0,0,0),(.235,.007,.001),mat('Darker cut wood '+str(j)+str(y),(.23,.15,.078),.68),.0003)
            groove.parent=o;groove.location=(0,y,.0081)
    colors=[(.48,.10,.065),(.12,.30,.38),(.68,.43,.12)]
    for j in range(3):
        m=finish(mat('Worn painted block '+str(j),colors[j],.48),4500,.000018,.12)
        o=box('Toy block background '+str(j),(.28+j*.055,.275+(j%2)*.05,TABLE+.026),(.048,.048,.052),m,.0016)
        o.rotation_euler[2]=[.16,-.10,.23][j]
    # The researched cartoon learning-toy pack is deliberately unused: its
    # low-poly finish and extra furniture clutter do not suit this close view.

def helix_vertices(length,c,sgn):
    d=c['wire_diameter_m'];D=c['mean_coil_diameter_m'];n=c['active_turns'];turns=n+2
    samples=turns*64+1;theta=np.linspace(0,2*math.pi*turns,samples);u=theta/(2*math.pi)
    pitch=np.where(u<1,d*.5,np.where(u>n+1,d*.5,(length-2*d)/n))
    xx=np.where(u<1,d*.5+u*d*.5,np.where(u>n+1,length-d+(u-(n+1))*d*.5,d+(u-1)*(length-2*d)/n))
    active_wire=math.hypot(math.pi*D*n,c['spring_rest_length_m']-2*d)
    radius=math.sqrt(max((active_wire/(2*math.pi*n))**2-((length-2*d)/(2*math.pi*n))**2,0))
    ph=np.linspace(0,2*math.pi,12,endpoint=False)
    out=[]
    for t,x,ax in zip(theta,xx,pitch):
        radial=np.array([0,math.cos(t),math.sin(t)])
        tangent=np.array([sgn*ax/(2*math.pi),-radius*math.sin(t),radius*math.cos(t)]);tangent/=np.linalg.norm(tangent)
        other=np.cross(tangent,radial);other/=np.linalg.norm(other)
        center=np.array([sgn*x,radius*math.cos(t),radius*math.sin(t)])
        out.extend(center+(d/2)*(math.cos(p)*radial+math.sin(p)*other) for p in ph)
    return np.asarray(out,dtype=np.float32)

def coil(name,anchor,length,c,sgn,metal):
    xyz=helix_vertices(length,c,sgn);rings=len(xyz)//12;faces=[]
    for i in range(rings-1):
        for j in range(12):faces.append((i*12+j,i*12+(j+1)%12,(i+1)*12+(j+1)%12,(i+1)*12+j))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(xyz.tolist(),[],faces);mesh.update()
    mesh.materials.append(metal);o=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(o)
    o.location=(anchor,0,RUN+.024)
    for p in mesh.polygons:p.use_smooth=True
    return o

def make_springs(c,wood):
    steel=finish(mat('Cold drawn polished steel coils',(.44,.48,.51),.24,1),17000,.000004,.12)
    alu=finish(mat('Brushed aluminium push plates',(.50,.54,.56),.34,1),26000,.000006,.17)
    rods=mat('Chromed guide rods',(.6,.63,.66),.19,1)
    dark=mat('Slotted screw steel',(.15,.16,.17),.3,1)
    result={}
    for side,sgn in [('left',1),('right',-1)]:
        anchor=-sgn*.440
        box(side+' fixed mounting plinth',(anchor-sgn*.008,0,TABLE+.003),(.047,.110,.006),wood,.001)
        box(side+' fixed back plate',(anchor-sgn*.008,0,RUN+.024),(.016,.088,.048),alu,.0007)
        for y in [-.034,.034]:
            cyl(side+' guide rod '+str(y),(anchor+sgn*.066,y,RUN+.024),.0019,.145,rods,'X')
            cyl(side+' rod base screw '+str(y),(anchor-sgn*.0161,y,RUN+.024),.0038,.0016,dark,'X')
            box(side+' screw slot '+str(y),(anchor-sgn*.017,y,RUN+.024),(.00025,.0045,.0007),mat(side+str(y)+' slot',(.015,.016,.018),.6),.0001)
        if side=='right' and not c['right_spring_present'][0]:continue
        pusher=box(side+' moving contact plate',(anchor+sgn*.120,0,RUN+.024),(.0015,.080,.030),alu,.0005)
        # Two real guide bores; rod solids do not overlap a solid plate.
        for y in [-.034,.034]:
            cutter=cyl('Temporary bore',(pusher.location.x,y,RUN+.024),.00215,.012,alu,'X')
            md=pusher.modifiers.new('Actual guide bore','BOOLEAN');md.operation='DIFFERENCE';md.object=cutter
            bpy.context.view_layer.objects.active=pusher
            bpy.ops.object.modifier_move_up(modifier=md.name);bpy.ops.object.modifier_move_up(modifier=md.name)
            bpy.ops.object.modifier_apply(modifier=md.name);bpy.data.objects.remove(cutter,do_unlink=True)
        spring=coil(side+' physical steel helix',anchor,.11925,c,sgn,steel)
        result[side]=(pusher,spring,anchor,sgn)
    return result

def light(name,pos,energy,size,target,color=(1,1,1)):
    d=bpy.data.lights.new(name,'AREA');o=bpy.data.objects.new(name,d);bpy.context.scene.collection.objects.link(o)
    o.location=pos;d.energy=energy;d.shape='DISK';d.size=size;d.color=color
    o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler();return o

def scene_setup(c):
    bpy.ops.wm.read_factory_settings(use_empty=True);s=bpy.context.scene
    used=make_table();wood=pbr_wood();make_track(wood);make_room(wood);make_props(wood)
    append_blend(ASSETS/'canonical/train.blend')
    train=bpy.data.objects['TRAIN_ROOT'];train.location=(c['train_initial_x_m'],0,RUN)
    wheels=[bpy.data.objects['WHEEL_'+str(i)] for i in range(6)]
    if not c.get('train_present',[1])[0]:
        # DELETE train: the appended train model (TRAIN_ROOT and all its parts) is not rendered at all.
        for o in bpy.data.objects:
            root=o
            while root.parent:root=root.parent
            if root.name=='TRAIN_ROOT':o.hide_render=True;o.hide_viewport=True
    springs=make_springs(c,wood)
    block=None
    if c['obstacle_present'][0]:
        x,y,z=c['obstacle_initial_position_m'];block=box('NEW wood_block - free slider',(x,y,RUN+z),c['obstacle_size_m'],wood,.001)
    world=bpy.data.worlds.new('Cool diffuse daylight');world.use_nodes=True
    world.node_tree.nodes.get('Background').inputs['Color'].default_value=(.55,.65,.76,1)
    world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.22;s.world=world
    light('Window daylight',(-1.2,-.7,1.65),115,1.2,(0,0,RUN),(.91,.95,1))
    light('Soft room bounce',(1.3,.35,1.5),45,1.4,(0,0,RUN),(1,.91,.80))
    light('Front wall bounce',(.1,-1.5,1.1),20,1.1,(0,0,RUN),(1,.96,.88))
    bpy.ops.object.camera_add(location=(.78,-1.72,1.12));cam=bpy.context.object;cam.name='Shared fixed side-front camera'
    cam.rotation_euler=(Vector((0,.015,RUN+.026))-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.lens=58;cam.data.sensor_width=36;cam.data.clip_start=.02;cam.data.clip_end=50
    cam.data.dof.use_dof=True;cam.data.dof.focus_distance=(Vector((0,0,RUN+.028))-cam.location).length;cam.data.dof.aperture_fstop=8
    s.camera=cam;s.render.engine='CYCLES';s.cycles.device='GPU'
    prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
    devices=[]
    for d in prefs.devices:
        d.use=d.type=='OPTIX'
        if d.use:devices.append({'name':d.name,'id':d.id,'type':d.type})
    if len(devices)!=1:raise RuntimeError('Expected one UUID-visible OptiX device: '+repr(devices))
    s.cycles.samples=96;s.cycles.use_denoising=True;s.cycles.seed=1163;s.cycles.use_animated_seed=False
    s.cycles.max_bounces=6;s.cycles.diffuse_bounces=3;s.cycles.glossy_bounces=3;s.cycles.transmission_bounces=3
    s.cycles.use_adaptive_sampling=True;s.cycles.adaptive_threshold=.025
    s.render.resolution_x=1280;s.render.resolution_y=720;s.render.resolution_percentage=100
    s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB';s.render.image_settings.color_depth='8';s.render.image_settings.compression=15
    s.render.fps=24;s.frame_start=1;s.frame_end=192;s.render.use_motion_blur=False
    s.view_settings.view_transform='AgX';s.view_settings.look='AgX - Medium High Contrast';s.view_settings.exposure=.2
    s.render.film_transparent=False;s.render.use_file_extension=True
    bpy.context.view_layer.update()
    static=[]
    for o in s.objects:
        ancestor=o
        while ancestor.parent:ancestor=ancestor.parent
        if ancestor.name=='TRAIN_ROOT' or any(o.name.startswith(k) for k in ['left moving','right moving','left physical','right physical','NEW wood_block']):continue
        static.append({'name':o.name,'matrix_world':[list(r) for r in o.matrix_world],
                       'type':o.type,'materials':[m.name for m in o.data.materials if m] if o.type=='MESH' else [],
                       'light_energy':o.data.energy if o.type=='LIGHT' else None})
    static.sort(key=lambda r:r['name'])
    signature=hashlib.sha256(json.dumps(static,sort_keys=True).encode()).hexdigest()
    return s,train,wheels,springs,block,{'table_objects':used,'optix_devices':devices,'camera_matrix':[list(r) for r in cam.matrix_world],'camera_lens_mm':cam.data.lens,'fstop':8,'cycles_samples':96,'seed':1163,'exposure':.2,
        'static_scene_signature_sha256':signature,'evaluated_camera_and_static_objects':True,'static_objects':static}

def update(index,state,c,train,wheels,springs,block):
    q=state['qpos'][index];lookup={k:q[v] for k,v in c['joint_qposadr'].items()}
    if 'train_x' in lookup:
        train.location.x=c['train_initial_x_m']+lookup['train_x']
        train.location.z=RUN+lookup.get('train_z',0)
        for i,w in enumerate(wheels):w.rotation_euler[1]=lookup['wheel_angle_'+str(i)]
    for side,(plate,wire,anchor,sgn) in springs.items():
        length=c['spring_rest_length_m']-lookup[side+'_compression']
        plate.location.x=anchor+sgn*length
        xyz=helix_vertices(length-c['plate_half_thickness_m'],c,sgn)
        wire.data.vertices.foreach_set('co',xyz.ravel());wire.data.update()
    if block:
        adr=c['joint_qposadr']['block_free'];block.location=Vector(q[adr:adr+3])+Vector((0,0,RUN))
        block.rotation_mode='QUATERNION';block.rotation_quaternion=q[adr+3:adr+7]
    bpy.context.view_layer.update()

