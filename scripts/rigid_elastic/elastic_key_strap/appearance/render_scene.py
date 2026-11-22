"""Base Cycles scene of the replay: moving parts, fixed camera and the base painted entryway.

Native physics is replayed without modifying trajectories. appearance/realism.py (the current
look) calls build_scene() and dresses the result; main() here renders the base look alone
(`--case-dir` with simulation.npz and resolved_config.json, `--device OPTIX|CUDA|CPU`)."""
import os, sys, socket, json, hashlib, argparse, subprocess, math
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

CATEGORY=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(CATEGORY.parent))
from pcve_assets import asset
ASSETS=asset('scenes/elastic_key_strap')

def dump(p,v):
    Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

def material(name,color,rough=.5,metal=0.):
    m=bpy.data.materials.new(name);m.use_nodes=True
    b=m.node_tree.nodes.get('Principled BSDF');b.inputs['Base Color'].default_value=(*color,1)
    b.inputs['Roughness'].default_value=rough;b.inputs['Metallic'].default_value=metal
    return m,b

def metal_material(name,color):
    m,b=material(name,color,.26,1.)
    n=m.node_tree.nodes;l=m.node_tree.links
    tex=n.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=1.;tex.inputs['Detail'].default_value=2
    coord=n.new('ShaderNodeTexCoord');stretch=n.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY'
    stretch.inputs[1].default_value=(24000,24000,350)
    l.new(coord.outputs['Object'],stretch.inputs[0]);l.new(stretch.outputs[0],tex.inputs['Vector'])
    ramp=n.new('ShaderNodeMapRange');ramp.inputs['From Min'].default_value=0;ramp.inputs['From Max'].default_value=1
    ramp.inputs['To Min'].default_value=.20;ramp.inputs['To Max'].default_value=.32
    l.new(tex.outputs['Fac'],ramp.inputs['Value']);l.new(ramp.outputs[0],b.inputs['Roughness'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.22;bump.inputs['Distance'].default_value=.000002
    l.new(tex.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],b.inputs['Normal'])
    if 'Anisotropic IOR Level' in b.inputs:b.inputs['Anisotropic IOR Level'].default_value=.24
    return m


def image_node(nodes,slug,channel,noncolor=False):
    files=list((ASSETS/slug).glob(channel+'.*'));assert len(files)==1,(slug,channel,files)
    tex=nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(files[0]),check_existing=True)
    uv=nodes.new('ShaderNodeUVMap');uv.uv_map='Metric surface UV'
    nodes.id_data.links.new(uv.outputs['UV'],tex.inputs['Vector'])
    if noncolor:tex.image.colorspace_settings.name='Non-Color'
    tex.interpolation='Linear';tex.extension='REPEAT'
    return tex


def surface_uv(obj,tile_m=1.,grain_x=False,offset=(0.,0.)):
    """Metric per-face UVs. Tangent-space normals use these same UVs."""
    uv=obj.data.uv_layers.new(name='Metric surface UV')
    obj.data.uv_layers.active=uv;uv.active_render=True
    for poly in obj.data.polygons:
        axis=max(range(3),key=lambda k:abs(poly.normal[k]));positive=poly.normal[axis]>0
        for li in poly.loop_indices:
            v=obj.data.vertices[obj.data.loops[li].vertex_index].co
            if axis==1:
                u,w=(v.x,v.z) if not positive else (-v.x,v.z)
            elif axis==2:
                u,w=(v.x,v.y) if positive else (-v.x,v.y)
            else:
                u,w=(-v.y,v.z) if positive else (v.y,v.z)
            if grain_x:u,w=-w,u
            uv.data[li].uv=(u/tile_m+offset[0],w/tile_m+offset[1])
    return obj


def oak_material():
    m,b=material('Fine oak veneer, satin oil finish',(.32,.21,.11),.39)
    n=m.node_tree.nodes;l=m.node_tree.links
    diffuse=image_node(n,'oak_veneer_01','diff');sat=n.new('ShaderNodeHueSaturation')
    sat.inputs['Saturation'].default_value=.94;sat.inputs['Value'].default_value=.70
    l.new(diffuse.outputs['Color'],sat.inputs['Color']);l.new(sat.outputs[0],b.inputs['Base Color'])
    rough=image_node(n,'oak_veneer_01','rough',True);remap=n.new('ShaderNodeMapRange')
    remap.inputs['To Min'].default_value=.27;remap.inputs['To Max'].default_value=.49
    l.new(rough.outputs['Color'],remap.inputs['Value']);l.new(remap.outputs[0],b.inputs['Roughness'])
    normal=image_node(n,'oak_veneer_01','nor_gl',True);nm=n.new('ShaderNodeNormalMap');nm.uv_map='Metric surface UV'
    nm.inputs['Strength'].default_value=.38;l.new(normal.outputs['Color'],nm.inputs['Color']);l.new(nm.outputs[0],b.inputs['Normal'])
    b.inputs['Coat Weight'].default_value=.16;b.inputs['Coat Roughness'].default_value=.36
    return m


def painted_wall_material():
    m,b=material('Warm mineral white, rolled matte emulsion',(.63,.61,.56),.78)
    n=m.node_tree.nodes;l=m.node_tree.links
    diffuse=image_node(n,'white_plaster_02','diff');mix=n.new('ShaderNodeMixRGB');mix.inputs[0].default_value=.97
    mix.inputs[2].default_value=(.63,.61,.56,1);l.new(diffuse.outputs['Color'],mix.inputs[1]);l.new(mix.outputs[0],b.inputs['Base Color'])
    rough=image_node(n,'white_plaster_02','rough',True);remap=n.new('ShaderNodeMapRange')
    remap.inputs['To Min'].default_value=.69;remap.inputs['To Max'].default_value=.87
    l.new(rough.outputs['Color'],remap.inputs['Value']);l.new(remap.outputs[0],b.inputs['Roughness'])
    scan=image_node(n,'white_plaster_02','nor_gl',True);nm=n.new('ShaderNodeNormalMap');nm.uv_map='Metric surface UV'
    nm.inputs['Strength'].default_value=.05;l.new(scan.outputs['Color'],nm.inputs['Color'])
    coord=n.new('ShaderNodeTexCoord');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=1150
    noise.inputs['Detail'].default_value=2.;noise.inputs['Roughness'].default_value=.65
    l.new(coord.outputs['Object'],noise.inputs['Vector'])
    micro=n.new('ShaderNodeBump');micro.inputs['Distance'].default_value=.000045;micro.inputs['Strength'].default_value=.45
    l.new(noise.outputs['Fac'],micro.inputs['Height']);l.new(nm.outputs[0],micro.inputs['Normal'])
    undulate=n.new('ShaderNodeTexNoise');undulate.inputs['Scale'].default_value=7.;undulate.inputs['Detail'].default_value=2.
    l.new(coord.outputs['Object'],undulate.inputs['Vector'])
    macro=n.new('ShaderNodeBump');macro.inputs['Distance'].default_value=.00015;macro.inputs['Strength'].default_value=.15
    l.new(undulate.outputs['Fac'],macro.inputs['Height']);l.new(micro.outputs[0],macro.inputs['Normal']);l.new(macro.outputs[0],b.inputs['Normal'])
    return m


def ceramic_material():
    m,b=material('Hand glazed warm grey stoneware',(.28,.31,.29),.29)
    b.inputs['Coat Weight'].default_value=.24;b.inputs['Coat Roughness'].default_value=.23
    n=m.node_tree.nodes;l=m.node_tree.links;coord=n.new('ShaderNodeTexCoord')
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=310.;noise.inputs['Detail'].default_value=3
    l.new(coord.outputs['Object'],noise.inputs['Vector'])
    mix=n.new('ShaderNodeMixRGB');mix.inputs[1].default_value=(.24,.265,.245,1);mix.inputs[2].default_value=(.34,.36,.32,1)
    l.new(noise.outputs['Fac'],mix.inputs[0]);l.new(mix.outputs[0],b.inputs['Base Color'])
    bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.00004;bump.inputs['Strength'].default_value=.18
    l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],b.inputs['Normal'])
    return m


def receipt_material():
    m,b=material('Thermal paper with printed shopping receipt',(.77,.74,.65),.82)
    n=m.node_tree.nodes;l=m.node_tree.links
    tex=n.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(ASSETS/'details/receipt.png'),check_existing=True)
    uv=n.new('ShaderNodeUVMap');uv.uv_map='Metric surface UV';l.new(uv.outputs['UV'],tex.inputs['Vector'])
    l.new(tex.outputs['Color'],b.inputs['Base Color'])
    return m


def mesh_object(name,v,f,mat,smooth=False):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(v,[],f);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj)
    if mat:mesh.materials.append(mat)
    if smooth:
        for p in mesh.polygons:p.use_smooth=True
    return obj

def bevel(obj,width=.001,segments=3):
    mod=obj.modifiers.new('Manufactured edge radius','BEVEL');mod.width=width;mod.segments=segments
    return obj

def box(name,location,dimensions,mat,radius=.001):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location);o=bpy.context.object;o.name=name
    o.dimensions=dimensions;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if mat:o.data.materials.append(mat)
    if radius:bevel(o,radius)
    return o

def torus(name,location,major,minor,mat):
    bpy.ops.mesh.primitive_torus_add(major_radius=major,minor_radius=minor,major_segments=96,minor_segments=12,
                                   location=location,rotation=(math.pi/2,0,0))
    o=bpy.context.object;o.name=name;o.data.materials.append(mat)
    for p in o.data.polygons:p.use_smooth=True
    return o

def curve(name,points,radius,mat):
    c=bpy.data.curves.new(name,'CURVE');c.dimensions='3D';c.resolution_u=24;c.bevel_depth=radius;c.bevel_resolution=4
    s=c.splines.new('BEZIER');s.bezier_points.add(len(points)-1)
    for b,p in zip(s.bezier_points,points):b.co=p;b.handle_left_type=b.handle_right_type='AUTO'
    o=bpy.data.objects.new(name,c);bpy.context.scene.collection.objects.link(o);o.data.materials.append(mat)
    return o

def import_asset(label,target_dims,target_center,base_z):
    with bpy.data.libraries.load(str(ASSETS/(label+'.blend')),link=False) as (src,dst):dst.objects=src.objects
    meshes=[]
    for o in dst.objects:
        if o is None:continue
        bpy.context.scene.collection.objects.link(o)
        o.animation_data_clear()
        if o.type not in ('MESH','EMPTY'):
            o.hide_render=True;continue
        if o.type=='MESH' and not o.hide_render:meshes.append(o)
    bpy.context.view_layer.update()
    corners=np.array([tuple(o.matrix_world@Vector(v)) for o in meshes for v in o.bound_box])
    low=corners.min(0);high=corners.max(0);dims=high-low
    root=bpy.data.objects.new(label+'_asset_root',None);bpy.context.scene.collection.objects.link(root)
    for o in dst.objects:
        if o is None:continue
        mw=o.matrix_world.copy();o.parent=None;o.parent=root;o.matrix_world=mw
    s=np.array(target_dims)/dims if target_dims is not None else np.ones(3)
    root.scale=s
    center=(low+high)/2
    root.location=(target_center[0]-center[0]*s[0],target_center[1]-center[1]*s[1],base_z-low[2]*s[2])
    return root,meshes

def point_at(obj,target):obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()

def area(name,pos,power,color,size,target,size_y=None):
    data=bpy.data.lights.new(name,'AREA');data.energy=power;data.color=color
    data.shape='RECTANGLE';data.size=size;data.size_y=size_y or size
    obj=bpy.data.objects.new(name,data);bpy.context.scene.collection.objects.link(obj)
    obj.location=pos;point_at(obj,target)


def window_architecture(room):
    """A real off-camera wall aperture shapes direct and indirect daylight."""
    box('Left wall below window',(-.90,-.89,.675),(.06,2.22,1.35),room,0)
    box('Left wall above window',(-.90,-.89,2.475),(.06,2.22,.05),room,0)
    box('Left wall before window',(-.90,-1.425,1.90),(.06,1.15,1.10),room,0)
    box('Left wall behind window',(-.90,-.05,1.90),(.06,.54,1.10),room,0)
    frame,_=material('Painted timber window reveal',(.64,.63,.59),.38)
    for y in (-.85,-.32):box('Off-camera vertical window frame',(-.862,y,1.90),(.065,.024,1.12),frame,.0015)
    for z in (1.35,2.45):box('Off-camera horizontal window frame',(-.862,-.585,z),(.065,.55,.024),frame,.0015)
    box('Off-camera window transom',(-.862,-.585,2.05),(.042,.53,.018),frame,.001)
    light=bpy.data.lights.new('Afternoon sun through side window','SUN');light.energy=.90
    light.color=(1.,.84,.66);light.angle=.022
    sun=bpy.data.objects.new(light.name,light);bpy.context.scene.collection.objects.link(sun)
    sun.location=(-1.15,-.80,2.15);point_at(sun,(0,.15,1.08))

def shell_geometry(x,tri,reference,h):
    normals=np.zeros_like(x);weights=np.zeros(len(x));thickness=np.zeros(len(x))
    dc=np.cross(x[tri[:,1]]-x[tri[:,0]],x[tri[:,2]]-x[tri[:,0]])
    dr=np.cross(reference[tri[:,1]]-reference[tri[:,0]],reference[tri[:,2]]-reference[tri[:,0]])
    a=np.linalg.norm(dc,axis=1);ar=np.linalg.norm(dr,axis=1);hh=h*ar/np.maximum(a,1e-12)
    for i in range(3):
        np.add.at(normals,tri[:,i],dc);np.add.at(thickness,tri[:,i],hh*ar);np.add.at(weights,tri[:,i],ar)
    normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-12)
    thickness/=weights
    verts=np.vstack((x+normals*thickness[:,None]/2,x-normals*thickness[:,None]/2))
    n=len(x);faces=[tuple(t) for t in tri]+[tuple((t+n)[::-1]) for t in tri]
    edges={}
    for t in tri:
        for a,b in zip(t,np.roll(t,-1)):
            key=tuple(sorted((a,b)));edges[key]=edges.get(key,0)+1
    for (a,b),count in edges.items():
        if count==1:faces.append((int(a),int(a+n),int(b+n),int(b)))
    return verts,faces

def configure_device(s,kind='OPTIX'):
    """Cycles device: 'CPU', or every visible GPU of one backend ('OPTIX' or 'CUDA')."""
    kind=kind.upper()
    if kind=='CPU':
        s.cycles.device='CPU'
        return [{'name':'CPU','id':'CPU','type':'CPU','threads':bpy.context.scene.render.threads}]
    s.cycles.device='GPU'
    pref=bpy.context.preferences.addons['cycles'].preferences
    pref.compute_device_type=kind;pref.get_devices()
    enabled=[]
    for device in pref.devices:
        device.use=device.type==kind
        if device.use:enabled.append({'name':device.name,'id':device.id,'type':device.type})
    if not enabled:raise RuntimeError(f'No {kind} device visible to Cycles')
    return enabled

def build_scene(cache,c,device='OPTIX'):
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    s=bpy.context.scene;s.render.engine='CYCLES'
    enabled=configure_device(s,device)
    s.cycles.use_denoising=True;s.cycles.use_adaptive_sampling=True;s.cycles.adaptive_threshold=.005
    s.cycles.max_bounces=8;s.cycles.diffuse_bounces=4;s.cycles.glossy_bounces=5
    s.cycles.seed=2207;s.render.use_persistent_data=True
    s.render.resolution_x=1280;s.render.resolution_y=720;s.render.resolution_percentage=100
    s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB';s.render.image_settings.color_depth='8'
    s.render.fps=24;s.frame_start=1;s.frame_end=96
    s.view_settings.view_transform='AgX';s.view_settings.look='AgX - Medium High Contrast';s.view_settings.exposure=0.
    s.world.use_nodes=True;s.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.72,.80,1.,1)
    s.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.045
    nickel=metal_material('Nickel plated key with fine wear',(.57,.60,.63))
    brass=metal_material('Satin brass with fine machining marks',(.48,.30,.10))
    hookmat=metal_material('Brushed stainless steel',(.30,.32,.34))
    wood=oak_material();plaster=painted_wall_material();rackwood=wood
    strapmat,b=material('Moulded sage silicone',(.040,.145,.105),.54)
    b.inputs['Specular IOR Level'].default_value=.32;b.inputs['Subsurface Weight'].default_value=.025
    n=strapmat.node_tree.nodes;l=strapmat.node_tree.links
    tex=n.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=14000;tex.inputs['Detail'].default_value=2
    coord=n.new('ShaderNodeTexCoord');l.new(coord.outputs['UV'],tex.inputs['Vector'])
    bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.0000015;bump.inputs['Strength'].default_value=.22
    l.new(tex.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],b.inputs['Normal'])
    surface_uv(box('Painted plaster wall',(0,.217,1.20),(3,.024,2.4),plaster,.0004),tile_m=1.)
    switchmat,_=material('Warm white satin switch plastic',(.62,.60,.55),.31)
    recess,_=material('Switch rocker reveal',(.12,.12,.11),.6)
    box('Entryway wall switch plate',(.29,.2005,1.19),(.086,.009,.086),switchmat,.003)
    box('Switch rocker shadow reveal',(.29,.1949,1.19),(.061,.002,.065),recess,.0015)
    box('Switch rocker',(.29,.1934,1.19),(.057,.004,.061),switchmat,.0018)
    import_asset('cabinet',(1.04,.47,.83),(0.02,-.03),0.)
    surface_uv(box('Solid oak cabinet top',(0,.02,.845),(1.04,.50,.030),wood,.0018),tile_m=1.83,grain_x=True,offset=(.29,.48))
    _,tray_meshes=import_asset('tray',(.115,.19,.030),(.205,.075),.860)
    ceramic=ceramic_material()
    for obj in tray_meshes:
        obj.data.materials.clear();obj.data.materials.append(ceramic)
    receipt=surface_uv(box('Small receipt in tray',(.20,.06,.866),(.043,.069,.0002),receipt_material(),.0001))
    for poly in receipt.data.polygons:
        for li in poly.loop_indices:
            v=receipt.data.vertices[receipt.data.loops[li].vertex_index].co
            receipt.data.uv_layers.active.data[li].uv=(v.x/.043+.5,v.y/.069+.5)
    receipt.rotation_euler[2]=.2
    surface_uv(box('Oak wall key rack',(0,.185,1.315),(.45,.025,.070),rackwood,.003),tile_m=1.83,grain_x=True,offset=(.73,.21))
    for x in (-.14,0,.14):
        hookpoints=[(x,.171,1.323),(x,.139,1.321),(x,.099,1.310),(x,.081,1.294),(x,.090,1.283),(x,.105,1.295)]
        curve('Fixed metal hook',hookpoints,.0018,hookmat)
        # Recessed screw and its cut are real geometry at the common baseline.
        bpy.ops.mesh.primitive_uv_sphere_add(segments=20,ring_count=12,radius=.0032,location=(x,.170,1.336))
        screw=bpy.context.object;screw.name='Rack screw';screw.scale=(1,.27,1);screw.data.materials.append(hookmat)
        for angle in (.27,math.pi/2+.27):
            cutter=box('Temporary screw drive cutter',(x,.1689,1.336),(.0044,.0014,.00065),None,0)
            cutter.rotation_euler[1]=angle
            mod=screw.modifiers.new('Recessed Phillips drive','BOOLEAN');mod.operation='DIFFERENCE';mod.object=cutter
            bpy.context.view_layer.objects.active=screw;bpy.ops.object.modifier_apply(modifier=mod.name)
            bpy.data.objects.remove(cutter,do_unlink=True)
    if c['strap_present'][0]:
        torus('Reinforced strap eyelet',(0,.090,1.2847),.0038,.001,strapmat)
    roots={}
    for i,name in enumerate(cache['body_names']):
        name=str(name);root=bpy.data.objects.new(name,None);bpy.context.scene.collection.objects.link(root);roots[name]=root
        root.rotation_mode='QUATERNION'
        if name=='keyring':
            o=torus('Split steel keyring',(0,0,0),c['ring_radius_m'],.00085,nickel);o.parent=root
            if c['strap_present'][0]:
                o=box('Strap end ferrule',(0,0,c['ring_radius_m']-.0005),(.0108,.0024,.0034),nickel,.0004);o.parent=root
        elif name.startswith('key'):
            raw=np.load(ASSETS/f'prepared/{name}.npz')
            o=mesh_object(name+'_original_asset',raw['vertices'],raw['triangles'],nickel if name=='key1' else brass,True)
            o.data.set_sharp_from_angle(angle=.55);bevel(o,.00010,3);o.parent=root
        elif name=='brass_fob':
            o=box('Added brass fob plate',(0,0,-.018),(.016,.003,.028),brass,.0015);o.parent=root
            o=torus('Added fob attachment eye',(0,0,-.001),.003,.0009,brass);o.parent=root
            o=torus('Added fob connector ring',(0,-.0055,.001),.0055,.0007,nickel)
            o.rotation_euler=(0,math.pi/2,0);o.parent=root
    shell=None
    if c['strap_present'][0]:
        vv,ff=shell_geometry(cache['strap_vertices'][0],cache['triangles'],cache['reference'],c['strap_thickness_m'])
        shell=mesh_object('Native finite-strain silicone strap',vv,ff,strapmat,True)
        uv_layer=shell.data.uv_layers.new(name='Material reference coordinates')
        count=len(cache['reference'])
        for loop in shell.data.loops:uv_layer.data[loop.index].uv=cache['uv'][loop.vertex_index%count]
    camd=bpy.data.cameras.new('Fixed side-front close-up');cam=bpy.data.objects.new('Fixed side-front close-up',camd)
    s.collection.objects.link(cam);s.camera=cam;cam.location=(.38,-.90,1.26);point_at(cam,(0,.075,1.105))
    camd.lens=40.;camd.sensor_width=36.;camd.clip_start=.01;camd.clip_end=30
    camd.dof.use_dof=True;camd.dof.focus_distance=(cam.location-Vector((0,.075,1.08))).length;camd.dof.aperture_fstop=8
    room,_=material('Off-camera warm white room surfaces',(.63,.61,.56),.82)
    floor,_=material('Off-camera natural oak floor bounce',(.22,.145,.085),.52)
    box('Room ceiling bounce',(.35,-.8,2.5),(2.5,2.4,.06),room,.002)
    box('Room right wall bounce',(1.6,-.8,1.25),(.06,2.4,2.5),room,.002)
    box('Room floor bounce',(.35,-.8,-.04),(2.5,2.4,.06),floor,.002)
    window_architecture(room)
    area('Cool daylight through tall side window',(-.95,-.62,1.90),78,(.86,.92,1.),.62,(0,.10,1.12),1.05)
    area('Warm reflected hallway light',(.75,-.95,1.55),3,(1.,.83,.65),1.0,(0,.10,1.08),1.2)
    return s,roots,shell,enabled

def apply_state(cache,index,roots,shell,c):
    bpy.context.scene.frame_set(index+1)
    for i,name in enumerate(cache['body_names']):
        root=roots[str(name)];root.location=cache['body_positions'][index,i]
        root.rotation_quaternion=cache['body_quaternions'][index,i]
    if shell:
        vv,_=shell_geometry(cache['strap_vertices'][index],cache['triangles'],cache['reference'],c['strap_thickness_m'])
        shell.data.vertices.foreach_set('co',vv.ravel());shell.data.update()
    bpy.context.view_layer.update()

def main():
    p=argparse.ArgumentParser();p.add_argument('--case-dir',type=Path,required=True)
    p.add_argument('--samples',type=int,default=128);p.add_argument('--preview-frames',type=int,nargs='*')
    p.add_argument('--width',type=int,default=1280);p.add_argument('--device',default='OPTIX',choices=('OPTIX','CUDA','CPU'))
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);out=a.case_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    cache=np.load(out/'simulation.npz');c=json.loads((out/'resolved_config.json').read_text())
    s,roots,shell,enabled=build_scene(cache,c,a.device);s.cycles.samples=a.samples
    s.render.resolution_x=a.width;s.render.resolution_y=round(a.width*9/16)
    bpy.context.view_layer.update()
    camera_signature={'matrix_world':list(np.array(s.camera.matrix_world).ravel()),'lens':s.camera.data.lens,'sensor_width':36.,
                      'width':s.render.resolution_x,'height':s.render.resolution_y}
    bounds=[];rigid_error=0.;shell_error=0.
    for frame in range(96):
        apply_state(cache,frame,roots,shell,c)
        points=[]
        for name,root in roots.items():
            for obj in root.children:
                if obj.type=='MESH':points.extend([obj.matrix_world@Vector(v) for v in obj.bound_box])
            i=list(cache['body_names']).index(name)
            rigid_error=max(rigid_error,float(np.linalg.norm(np.array(root.location)-cache['body_positions'][frame,i])))
        if shell:
            points.extend(Vector(v) for v in cache['strap_vertices'][frame])
            n=len(cache['reference']);verts=np.array([tuple(v.co) for v in shell.data.vertices])
            shell_error=max(shell_error,float(np.max(np.abs((verts[:n]+verts[n:])/2-cache['strap_vertices'][frame]))))
        ndc=np.array([tuple(world_to_camera_view(s,s.camera,v)) for v in points])
        bounds.append([float(ndc[:,0].min()),float(ndc[:,1].min()),float(ndc[:,0].max()),float(ndc[:,1].max())])
    apply_state(cache,0,roots,shell,c)
    replay={'camera':camera_signature,'rigid_position_max_error_m':rigid_error,'shell_mid_surface_max_error_m':shell_error,
            'screen_bounds_96_frames':bounds,'native_time_range_s':[float(cache['times'][0]),float(cache['times'][95])],
            'retiming':False,'motion_smoothing':False,'pose_edit':False,
            'attachment_contact_exclusion':'Strap-ring welded interface excluded by collision mask; free strap-key and cabinet contact remain active.'}
    replay['lights']=[{'name':o.name,'matrix':np.array(o.matrix_world).ravel().tolist(),'energy':o.data.energy,'color':list(o.data.color)}
                      for o in s.objects if o.type=='LIGHT' and not o.hide_render]
    replay['light_shapes']=[{'name':o.name,'type':o.data.type,'shape':getattr(o.data,'shape',None),'size':getattr(o.data,'size',None),'size_y':getattr(o.data,'size_y',None),'angle':getattr(o.data,'angle',None)}
                            for o in s.objects if o.type=='LIGHT' and not o.hide_render]
    dump(out/'native_replay_audit.json',replay)
    static_names=['Painted plaster wall','Solid oak cabinet top','Oak wall key rack',
                  'Entryway wall switch plate','Switch rocker','Small receipt in tray']
    appearance={'common_baseline_revision':True,'physics_collision_surfaces_unchanged':True,
        'wall_contact_plane_y_m':.205,'cabinet_contact_top_z_m':.860,
        'material_texture_width_m':{'oak_veneer_01':1.83,'white_plaster_02':1.0},
        'normal_mapping':'Non-Color tangent-space normal images use the same metric UV layer as color and roughness',
        'texture_uv_binding':'All image texture vectors explicitly use Metric surface UV; metric layer is also active_render',
        'paint_micro_bump_distance_m':.000045,'paint_micro_bump_strength':.45,
        'paint_macro_bump_distance_m':.00015,'paint_macro_bump_strength':.15,
        'depth_of_field':{'enabled':s.camera.data.dof.use_dof,'focus_distance_m':s.camera.data.dof.focus_distance,'f_stop':s.camera.data.dof.aperture_fstop},
        'world_color':list(s.world.node_tree.nodes['Background'].inputs['Color'].default_value),
        'world_strength':s.world.node_tree.nodes['Background'].inputs['Strength'].default_value,
        'view_transform':s.view_settings.view_transform,'view_look':s.view_settings.look,'exposure':s.view_settings.exposure,
        'static_objects':{name:{'matrix_world':np.array(bpy.data.objects[name].matrix_world).ravel().tolist(),
                                'dimensions':list(bpy.data.objects[name].dimensions)} for name in static_names},
        'off_camera_architecture':'Side window aperture and transom; room ceiling, side walls and floor provide path-traced light transport',
        'material_measurement_calibration':False}
    uv_records=[]
    for name in ['Fine oak veneer, satin oil finish','Warm mineral white, rolled matte emulsion','Thermal paper with printed shopping receipt']:
        mat=bpy.data.materials[name]
        for node in mat.node_tree.nodes:
            if node.type!='TEX_IMAGE':continue
            links=list(node.inputs['Vector'].links);assert len(links)==1
            uv_node=links[0].from_node
            assert uv_node.type=='UVMAP' and uv_node.uv_map=='Metric surface UV',(name,node.name)
            uv_records.append({'material':name,'texture':node.image.filepath,'uv_map':uv_node.uv_map})
        for node in mat.node_tree.nodes:
            if node.type=='NORMAL_MAP':assert node.uv_map=='Metric surface UV'
    active_uv={}
    for name in ['Painted plaster wall','Solid oak cabinet top','Oak wall key rack','Small receipt in tray']:
        layers=bpy.data.objects[name].data.uv_layers
        active_uv[name]=next(layer.name for layer in layers if layer.active_render)
        assert active_uv[name]=='Metric surface UV'
    appearance['verified_texture_uv_bindings']=uv_records;appearance['verified_active_render_uv']=active_uv
    dump(out/'appearance_scene_audit.json',appearance)
    visible=os.environ.get('CUDA_VISIBLE_DEVICES','')
    gpu=subprocess.check_output(['nvidia-smi','-i',visible,'--query-gpu=name,uuid,driver_version','--format=csv,noheader'],
                                text=True).strip() if visible and a.device!='CPU' else None
    provenance={'render_host':socket.gethostname(),
        'gpu_binding':visible or None,'gpu_uuids':visible.split(',') if visible else [],'gpu':gpu,'cycles_devices':enabled,
        'blender_version':bpy.app.version_string,'render_engine':'Cycles '+a.device,'samples':a.samples,
        'simulation_cache_sha256':hashlib.sha256((out/'simulation.npz').read_bytes()).hexdigest(),
        'local_blender_used':False}
    dump(out/'render_environment.json',provenance)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'))
    frames=a.preview_frames if a.preview_frames is not None else list(range(96))
    folder=out/('preview' if a.preview_frames is not None else 'frames');folder.mkdir(exist_ok=True)
    for frame in frames:
        apply_state(cache,frame,roots,shell,c);s.render.filepath=str(folder/f'{frame:04d}.png')
        bpy.ops.render.render(write_still=True)

if __name__=='__main__':main()
