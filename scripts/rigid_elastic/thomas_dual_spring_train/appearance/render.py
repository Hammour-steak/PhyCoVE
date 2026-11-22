"""Remote-only appearance revision; identical solved poses and fixed camera."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,math,os,socket,subprocess,sys,time
if os.name=='nt' or not sys.platform.startswith('linux'):
    raise RuntimeError('Blender rendering runs on a Linux GPU host')
import bpy
import numpy as np
from mathutils import Vector
HERE=Path(__file__).resolve().parent;SUPPORT=HERE.parent;REPO=HERE.parents[3]
DATA=REPO/'renders/thomas_dual_spring_train'
sys.path.insert(0,str(REPO/'scripts'))
from pcve_assets import asset
ASSETS=asset('scenes/thomas_dual_spring_train')
LOOK='base_look'
spec=importlib.util.spec_from_file_location('native_scene',HERE/'base_scene.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.HERE=SUPPORT;base.REPO=REPO;base.DATA=DATA;base.ASSETS=ASSETS
detail_spec=importlib.util.spec_from_file_location('appearance_details',HERE/'details.py')
details=importlib.util.module_from_spec(detail_spec);detail_spec.loader.exec_module(details)
details.configure(base)

OVERLAY=None  # appearance/realism.py sets the published look, applied right after setup

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2),encoding='utf-8')

def image_material(slug,name,normal_strength=.6,rough_limits=(.35,.65),saturation=1.,value=1.):
    manifest=json.loads((ASSETS/slug/'manifest.json').read_text())
    material=base.mat(name,(.5,.5,.5),.65);nodes=material.node_tree.nodes;links=material.node_tree.links
    bs=nodes.get('Principled BSDF');coord=nodes.new('ShaderNodeTexCoord')
    for channel,socket_name in [('Diffuse','Base Color'),('Rough','Roughness'),('nor_gl','Normal')]:
        tex=nodes.new('ShaderNodeTexImage');tex.name=slug+' '+channel
        tex.image=bpy.data.images.load(str(ASSETS/manifest['files'][channel]['path'].removeprefix('assets/')),check_existing=True)
        tex.interpolation='Linear';tex.extension='REPEAT'
        if channel!='Diffuse':tex.image.colorspace_settings.name='Non-Color'
        links.new(coord.outputs['UV'],tex.inputs['Vector'])
        if channel=='Diffuse':
            hue=nodes.new('ShaderNodeHueSaturation');hue.inputs['Saturation'].default_value=saturation;hue.inputs['Value'].default_value=value
            links.new(tex.outputs['Color'],hue.inputs['Color']);links.new(hue.outputs['Color'],bs.inputs[socket_name])
        elif channel=='Rough':
            remap=nodes.new('ShaderNodeMapRange');remap.inputs['From Min'].default_value=0;remap.inputs['From Max'].default_value=1
            remap.inputs['To Min'].default_value=rough_limits[0];remap.inputs['To Max'].default_value=rough_limits[1]
            links.new(tex.outputs['Color'],remap.inputs['Value']);links.new(remap.outputs['Result'],bs.inputs[socket_name])
        else:
            normal=nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=normal_strength
            links.new(tex.outputs['Color'],normal.inputs['Color']);links.new(normal.outputs['Normal'],bs.inputs['Normal'])
    material['source_url']=manifest['source_url'];material['license']='CC0';material['scan_dimensions_mm']=manifest['dimensions_mm']
    return material

def surface(name,points,uv,material,thickness=0):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(points,[],[(0,1,2,3)]);mesh.update()
    layer=mesh.uv_layers.new(name='Metric scan UV')
    for i,co in enumerate(uv):layer.data[i].uv=co
    mesh.materials.append(material);o=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(o)
    if thickness:
        modifier=o.modifiers.new('Actual wall thickness','SOLIDIFY');modifier.thickness=thickness;modifier.offset=-1
    return o

def curtain(x=-1.40,start=.12,width=.34,bottom=.12,top=2.18):
    material=base.finish(base.mat('Unbleached linen curtain',(.72,.69,.61),.87),3600,.00012,.18)
    nodes=material.node_tree.nodes;links=material.node_tree.links;bs=nodes.get('Principled BSDF')
    transparent=nodes.new('ShaderNodeBsdfTranslucent');transparent.inputs['Color'].default_value=(.73,.70,.63,1)
    mix=nodes.new('ShaderNodeMixShader');mix.inputs[0].default_value=.17
    output=nodes.get('Material Output');links.new(bs.outputs[0],mix.inputs[1]);links.new(transparent.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],output.inputs['Surface'])
    vertices=[];uv=[];faces=[];nu,nv=72,24
    for j in range(nv+1):
        t=j/nv
        for i in range(nu+1):
            u=i/nu;y=start+u*width
            xx=x+.020*math.cos(u*math.pi*8)+.004*math.sin(t*6+u*9)
            zz=bottom+(top-bottom)*t+.002*math.cos(u*math.pi*8)*(1-t)**8
            vertices.append((xx,y,zz));uv.append((u*width,t*(top-bottom)))
    for j in range(nv):
        for i in range(nu):
            a=j*(nu+1)+i;faces.append((a,a+1,a+nu+2,a+nu+1))
    mesh=bpy.data.meshes.new('Linen folds');mesh.from_pydata(vertices,[],faces);mesh.materials.append(material)
    o=bpy.data.objects.new('Window linen with actual folds and hem',mesh);bpy.context.scene.collection.objects.link(o)
    layer=mesh.uv_layers.new(name='Metre weave')
    for polygon in mesh.polygons:
        polygon.use_smooth=True
        for loop_index in polygon.loop_indices:layer.data[loop_index].uv=uv[mesh.loops[loop_index].vertex_index]
    modifier=o.modifiers.new('Thin woven fabric','SOLIDIFY');modifier.thickness=.00035

def room(wood):
    wall=image_material('beige_wall_001','Scanned painted plaster, 3 metre repeat',.50,(.72,.92),.50,1.24)
    trim=base.finish(base.mat('Warm white eggshell joinery',(.73,.72,.67),.39),2400,.000018,.10)
    back=1.10;left=-1.45;height=2.65
    points=[(left,back,0),(3,back,0),(3,back,height),(left,back,height)]
    surface('Back wall - actual painted plaster',points,[(x/3+.15,z/3+.1) for x,y,z in points],wall,.10)
    # A real aperture in the left wall, rather than a luminous panel over a wall.
    for name,ya,yb,za,zb in [('front pier',-3,-1.05,0,height),('rear pier',.10,back,0,height),
                             ('sill wall',-1.05,.10,0,.72),('lintel wall',-1.05,.10,2.18,height)]:
        points=[(left,ya,za),(left,yb,za),(left,yb,zb),(left,ya,zb)]
        surface('Window wall '+name,points,[(y/3+.2,z/3+.1) for x,y,z in points],wall,.10)
    floor=image_material('wood_floor','Scanned oak floor, 1.7 metre repeat',.65,(.32,.60),.82,1.06)
    points=[(-2.5,-3,0),(3,-3,0),(3,back,0),(-2.5,back,0)]
    surface('Interior oak floor',points,[(x/1.7,y/1.7) for x,y,z in points],floor,.024)
    ceiling=base.mat('Matte ceiling',(.75,.75,.71),.92)
    surface('Ceiling for actual room bounce',[(-2,-3,height),(-2,back,height),(3,back,height),(3,-3,height)],[(0,0)]*4,ceiling)
    # Profiled skirting, paint caulk, and a modest chair rail provide real edges.
    for z,depth,thickness in [(.045,.022,.090),(.094,.027,.012),(.104,.017,.009),
                              (.688,.014,.030),(.708,.025,.012),(.719,.020,.010)]:
        base.box('Back wall joinery '+str(z),((left+3)/2,back-depth/2,z),(3-left,depth,thickness),trim,.0015)
        base.box('Side wall joinery '+str(z),(left+depth/2,(back-3)/2,z),(depth,back+3,thickness),trim,.0015)
    for y in [-1.05,.10]:base.box('Window jamb '+str(y),(left+.012,y,1.45),(.095,.055,1.55),trim,.002)
    for z in [.72,2.18]:base.box('Window head and sill '+str(z),(left+.012,-.475,z),(.11,1.26,.06),trim,.003)
    base.box('Window intermediate stile',(left-.025,-.48,1.45),(.048,.034,1.43),trim,.002)
    base.box('Window transom',(left-.025,-.475,1.46),(.048,1.15,.038),trim,.002)
    base.box('Window sill projection',(left+.04,-.475,.704),(.19,1.30,.022),trim,.003)
    curtain()

def maple():
    material=image_material('white_maple_veneer','Fine sanded maple track',.28,(.43,.63),.92,1.0)
    bs=material.node_tree.nodes.get('Principled BSDF');bs.inputs['Coat Weight'].default_value=.045;bs.inputs['Coat Roughness'].default_value=.38
    nodes=material.node_tree.nodes;links=material.node_tree.links
    original=bs.inputs['Base Color'].links[0].from_socket
    oil=nodes.new('ShaderNodeMixRGB');oil.name='Subtle amber clear finish';oil.blend_type='MULTIPLY'
    oil.inputs[0].default_value=.60;oil.inputs[2].default_value=(.60,.33,.15,1)
    links.new(original,oil.inputs[1]);links.new(oil.outputs[0],bs.inputs['Base Color'])
    return material

def end_grain():
    material=base.mat('Maple cut end grain',(.51,.36,.20),.62)
    nodes=material.node_tree.nodes;links=material.node_tree.links;bs=nodes.get('Principled BSDF')
    coord=nodes.new('ShaderNodeTexCoord');offset=nodes.new('ShaderNodeVectorMath');offset.operation='ADD';offset.inputs[1].default_value=(0,.06,.085)
    wave=nodes.new('ShaderNodeTexWave');wave.wave_type='RINGS';wave.rings_direction='X';wave.inputs['Scale'].default_value=85
    wave.inputs['Distortion'].default_value=3.2;wave.inputs['Detail'].default_value=2;wave.inputs['Detail Scale'].default_value=9
    links.new(coord.outputs['Object'],offset.inputs[0]);links.new(offset.outputs[0],wave.inputs['Vector'])
    ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.46,.31,.17,1);ramp.color_ramp.elements[1].color=(.61,.45,.27,1)
    links.new(wave.outputs['Color'],ramp.inputs[0]);links.new(ramp.outputs[0],bs.inputs['Base Color'])
    return base.finish(material,7000,.000022,.13)

def wood_uvs():
    end=end_grain()
    for o in bpy.context.scene.objects:
        if o.type!='MESH' or not o.data.materials:continue
        if not any(m and m.name=='Fine sanded maple track' for m in o.data.materials):continue
        root=o
        while root.parent:root=root.parent
        seed=int(hashlib.sha256(root.name.encode()).hexdigest()[:8],16)/2**32
        to_piece=root.matrix_world.inverted()@o.matrix_world
        layer=o.data.uv_layers.active or o.data.uv_layers.new(name='Metre wood grain')
        end_index=len(o.data.materials);o.data.materials.append(end)
        for polygon in o.data.polygons:
            axis=max(range(3),key=lambda i:abs(polygon.normal[i]))
            if axis==0:polygon.material_index=end_index
            for loop_index in polygon.loop_indices:
                p=to_piece@o.data.vertices[o.data.loops[loop_index].vertex_index].co
                u,v=(p.x,p.y) if axis==2 else (p.x,p.z) if axis==1 else (p.y,p.z)
                layer.data[loop_index].uv=(u+seed,v+.13+seed*.41)

def relight(scene):
    for o in list(scene.objects):
        if o.type=='LIGHT':bpy.data.objects.remove(o,do_unlink=True)
    world=scene.world;world.node_tree.nodes.get('Background').inputs['Color'].default_value=(.60,.72,1.,1)
    world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.065
    key=base.light('Daylight through actual left aperture',(-1.62,-.48,1.48),160,1.04,(0,.06,.57),(.94,.97,1.))
    key.data.shape='RECTANGLE';key.data.size=1.04;key.data.size_y=1.28
    sun=bpy.data.lights.new('Soft afternoon sunlight','SUN');sun.energy=1.2;sun.angle=.095;sun.color=(1.,.93,.82)
    o=bpy.data.objects.new('Soft afternoon sunlight',sun);scene.collection.objects.link(o)
    o.rotation_euler=Vector((1,1.2,-.65)).to_track_quat('-Z','Y').to_euler()

def setup(config,samples):
    base.make_room=room;base.pbr_wood=maple
    base.make_track=details.make_track;base.make_props=details.make_props
    scene,train,wheels,springs,block,record=base.scene_setup(config)
    wood_uvs();relight(scene)
    scene.cycles.samples=samples;scene.cycles.adaptive_threshold=.008
    scene.cycles.max_bounces=10;scene.cycles.diffuse_bounces=5;scene.cycles.glossy_bounces=5;scene.cycles.transmission_bounces=5
    scene.view_settings.exposure=0.;scene.frame_end=96
    for material in bpy.data.materials:
        if not material.use_nodes:continue
        bs=material.node_tree.nodes.get('Principled BSDF')
        if not bs:continue
        if 'Brushed aluminium' in material.name:
            bs.inputs['Roughness'].default_value=.30
            if 'Anisotropic IOR Level' in bs.inputs:bs.inputs['Anisotropic IOR Level'].default_value=.35
        if material.name.startswith('Worn painted block'):
            bs.inputs['Roughness'].default_value=.46;bs.inputs['Coat Weight'].default_value=.08
            nodes=material.node_tree.nodes;links=material.node_tree.links
            geometry=nodes.new('ShaderNodeNewGeometry');edge=nodes.new('ShaderNodeMapRange')
            edge.inputs['From Min'].default_value=.50;edge.inputs['From Max'].default_value=.59
            edge.inputs['To Min'].default_value=0;edge.inputs['To Max'].default_value=.20
            links.new(geometry.outputs['Pointiness'],edge.inputs['Value'])
            mix=nodes.new('ShaderNodeMixRGB');mix.inputs[1].default_value=bs.inputs['Base Color'].default_value
            mix.inputs[2].default_value=(.58,.43,.24,1)
            links.new(edge.outputs['Result'],mix.inputs[0]);links.new(mix.outputs[0],bs.inputs['Base Color'])
    details.apply(scene,config,record)
    bpy.context.view_layer.update()
    print('APPEARANCE_EVALUATION_FINISHED',flush=True)
    static=[]
    for o in scene.objects:
        ancestor=o
        while ancestor.parent:ancestor=ancestor.parent
        if ancestor.name=='TRAIN_ROOT' or any(o.name.startswith(k) for k in ['left moving','right moving','left physical','right physical','NEW wood_block']):continue
        static.append({'name':o.name,'matrix_world':[list(row) for row in o.matrix_world],'type':o.type,
            'materials':[m.name for m in o.data.materials if m] if o.type=='MESH' else [],'light_energy':o.data.energy if o.type=='LIGHT' else None})
    static.sort(key=lambda row:row['name'])
    record.update(static_objects=static,static_scene_signature_sha256=hashlib.sha256(json.dumps(static,sort_keys=True).encode()).hexdigest(),
        cycles_samples=samples,adaptive_threshold=.008,exposure=0.,appearance_revision=LOOK,
        texture_mappings={'painted_wall_repeat_m':3.,'maple_repeat_m':1.,'oak_floor_repeat_m':1.7,'normal_maps':'OpenGL, tangent-space, explicit metric UVs'},
        appearance_material_manifests={slug:sha(ASSETS/slug/'manifest.json') for slug in ['beige_wall_001','white_maple_veneer','wood_floor']},
        appearance_changes=['Milled rail cross section, true spare grooves and interlocking joinery',
            'Countersunk screws and bored guide bushings on fixed mounting hardware',
            'Spatially varying satin table finish; original wood and plywood scan preserved',
            'Fine painted plaster and closed room reflection geometry',
            'Paint microfinish and shader bevel on original train geometry'],
        physical_model_or_initial_conditions_changed=False)
    return scene,train,wheels,springs,block,record

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['preview','render'],default='preview');p.add_argument('--case',default='source')
    p.add_argument('--frame',type=int,default=16);p.add_argument('--samples',type=int,default=192);p.add_argument('--tag',default='p1')
    p.add_argument('--state-root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    folder=a.state_root/a.case;config=json.loads((folder/'config.json').read_text());states=np.load(folder/'states.npz',allow_pickle=False)
    assert len(states['time'])==96 and np.max(np.abs(states['time']-np.arange(96)/24))<1e-8
    scene,train,wheels,springs,block,record=setup(config,a.samples)
    if OVERLAY:OVERLAY(scene)
    print('SCENE_SETUP_FINISHED',flush=True)
    host=socket.gethostname().split('.')[0]
    record.update(worker=host,worker_ip=None,
        gpu_uuid=os.environ['CUDA_VISIBLE_DEVICES'],blender_version=bpy.app.version_string,local_blender_used=False,
        render_engine='Cycles / OptiX',case_id=a.case,mode=a.mode,resolution=[1280,720],fps=24,video_frames=96,duration_s=4.,
        state_cache_sha256=sha(folder/'states.npz'),
        motion_replay='Exact unchanged native physical samples at i/24; no retiming or motion interpolation',
        material_calibrated=False,accepted_benchmark_gt=False,new_blender_execution=True,
        started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    output=a.out/a.case;output.mkdir(parents=True,exist_ok=True)
    if a.mode=='preview':
        record.update(artifact_kind='single_frame_preview',actual_rendered_frame_count=1,preview_physical_time_s=float(states['time'][a.frame]))
        base.update(a.frame,states,config,train,wheels,springs,block)
        print('SOLVED_STATE_REPLAY_FINISHED',flush=True)
        target=output/('preview_'+a.tag+'_'+str(a.frame)+'.png');scene.render.filepath=str(target)
        print('CYCLES_RENDER_START',flush=True)
        bpy.ops.render.render(write_still=True);record['preview_path']=str(target)
        save(output/('preview_'+a.tag+'_metadata.json'),record)
    else:
        frames=output/'frames';frames.mkdir(parents=True,exist_ok=True)
        existing=output/'render_provenance.json'
        save(existing,record)
        base.update(0,states,config,train,wheels,springs,block)
        if a.case=='source':
            bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(output/'source_scene.blend'))
        manifest=[]
        for i in range(96):
            target=frames/f'{i:04d}.png'
            if not target.exists():
                scene.frame_set(i+1);base.update(i,states,config,train,wheels,springs,block)
                scene.render.filepath=str(target);bpy.ops.render.render(write_still=True)
            manifest.append({'path':target.name,'time_s':float(states['time'][i]),'sha256':sha(target)})
            save(output/'progress.json',{'case':a.case,'completed_frame':i+1,'total_frames':96,'worker':host})
        ffmpeg=Path(os.environ['PCVE_FFMPEG'])
        subprocess.run([str(ffmpeg),'-y','-v','error','-framerate','24','-i',str(frames/'%04d.png'),'-frames:v','96',
            '-an','-c:v','libx264','-threads','2','-preset','slow','-crf','16','-pix_fmt','yuv420p','-movflags','+faststart',str(output/'video.mp4')],check=True)
        save(output/'source_frame_manifest.json',{'pixel_source':'new remote Cycles renders from unchanged solved states','frames':manifest})
        record.update(video_sha256=sha(output/'video.mp4'),finished_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
        save(existing,record);save(output/'scene_render_metadata.json',record)
    print('REALISM_RENDER_COMPLETE',a.mode,a.case,flush=True)

if __name__=='__main__':main()
