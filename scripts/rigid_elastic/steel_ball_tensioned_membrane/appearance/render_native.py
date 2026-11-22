"""Remote-only Cycles renderer for the steel-ball / membrane case."""
from pathlib import Path
import argparse,hashlib,json,math,shutil,socket,subprocess,sys,time
import bpy
import numpy as np
from mathutils import Vector

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
HELPERS=HERE
sys.path[:0]=[str(HERE),str(HERE.parent),str(ROOT/"scripts")]
from pcve_assets import asset
from edit_vocab import SPEC,SPEC_PATH
from geometry import mat,procedural_surface,cube,cylinder,point_camera,build_membrane
from primitives import torus,beam,animate_ball
from realism import apply as apply_realism

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def text_obj(name,body,loc,size,material,rotation=(math.pi/2,0,0),align='CENTER'):
    data=bpy.data.curves.new(name,'FONT');data.body=body;data.size=size;data.align_x=align;data.extrude=.00025
    obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj);obj.location=loc;obj.rotation_euler=rotation;data.materials.append(material);return obj

def cable(name,points,radius,material):
    curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D';curve.bevel_depth=radius;curve.bevel_resolution=3
    spline=curve.splines.new('BEZIER');spline.bezier_points.add(len(points)-1)
    for bp,co in zip(spline.bezier_points,points):bp.co=co;bp.handle_left_type='AUTO';bp.handle_right_type='AUTO'
    obj=bpy.data.objects.new(name,curve);bpy.context.collection.objects.link(obj);curve.materials.append(material);return obj

def emissive(name,color,strength):
    m=mat(name,color,0,.35);b=m.node_tree.nodes.get('Principled BSDF');b.inputs['Emission Color'].default_value=(*color,1);b.inputs['Emission Strength'].default_value=strength;return m

def lab_membrane_material():
    """Matte latex with sparse, irregular DIC paint rather than a dense synthetic noise field."""
    m=mat('Charcoal latex with sparse DIC speckles',(.0025,.003,.0035),0,.76);n=m.node_tree.nodes;l=m.node_tree.links;b=n.get('Principled BSDF')
    b.inputs['IOR'].default_value=1.49;b.inputs['Specular IOR Level'].default_value=.22;b.inputs['Coat Weight'].default_value=.012;b.inputs['Coat Roughness'].default_value=.68
    coord=n.new('ShaderNodeTexCoord');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=132;noise.inputs['Detail'].default_value=1.7;noise.inputs['Roughness'].default_value=.61;noise.inputs['Distortion'].default_value=.08
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.interpolation='CONSTANT';ramp.color_ramp.elements[0].position=.735;ramp.color_ramp.elements[0].color=(.0025,.003,.0035,1);ramp.color_ramp.elements[1].position=.79;ramp.color_ramp.elements[1].color=(.34,.36,.37,1)
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.055;bump.inputs['Distance'].default_value=.00012
    l.new(coord.outputs['UV'],noise.inputs['Vector']);l.new(noise.outputs['Fac'],ramp.inputs['Fac']);l.new(ramp.outputs['Color'],b.inputs['Base Color']);l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],b.inputs['Normal'])
    return m

def lab_world(scene):
    world=bpy.data.worlds.new('Poly Haven University Workshop 4K');world.use_nodes=True;scene.world=world;n=world.node_tree.nodes;l=world.node_tree.links
    for node in list(n):n.remove(node)
    out=n.new('ShaderNodeOutputWorld');bg=n.new('ShaderNodeBackground');bg.inputs['Strength'].default_value=.42;env=n.new('ShaderNodeTexEnvironment')
    hdr=asset('scenes/steel_ball_tensioned_membrane/university_workshop_4k.hdr')
    if not hdr.exists():raise FileNotFoundError(hdr)
    env.image=bpy.data.images.load(str(hdr));coord=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeMapping');mapping.inputs['Rotation'].default_value[2]=math.radians(218)
    l.new(coord.outputs['Generated'],mapping.inputs['Vector']);l.new(mapping.outputs['Vector'],env.inputs['Vector']);l.new(env.outputs['Color'],bg.inputs['Color']);l.new(bg.outputs[0],out.inputs[0])

def optical_table(frame,steel,holes):
    # Physics ground z=0 is the actual breadboard top, so remove-membrane remains visually valid.
    cube('Damped optical breadboard',(0,0,-.065),(1.48,1.05,.065),frame,.012)
    cube('Stainless breadboard skin',(0,0,-.006),(1.46,1.03,.006),steel,.002)
    # Dark, almost flush bores read as tapped holes instead of raised black studs.
    for x in np.arange(-1.32,1.33,.10):
        for y in np.arange(-.91,.92,.10):cylinder('M6 tapped breadboard bore',(x,y,-.0005),.0031,.0006,holes,24)
    for x in (-1.22,1.22):
        for y in (-.79,.79):
            cylinder('Pneumatic isolation leg',(x,y,-.43),.105,.62,frame,64)
            cylinder('Isolation bellows',(x,y,-.18),.135,.15,holes,64)
            cylinder('Floor levelling foot',(x,y,-.77),.16,.055,frame,64)

def instrument_rack(x,y,frame,aluminum,screen,white,red,green,holes):
    cube('DAQ rack chassis',(x,y,.29),(.31,.22,.29),frame,.018)
    cube('DAQ brushed front',(x,y-.224,.31),(.292,.007,.25),aluminum,.004)
    cube('DAQ waveform display',(x-.08,y-.233,.37),(.13,.003,.075),screen,.002)
    grid=mat('DAQ display grid',(.03,.24,.20),0,.45)
    trace=emissive('DAQ impact trace',(.10,1.0,.48),5.0)
    for gx in np.linspace(x-.19,x+.03,7):cube('DAQ display vertical grid',(gx,y-.237,.37),(.00045,.0004,.068),grid,0)
    for gz in np.linspace(.315,.425,5):cube('DAQ display horizontal grid',(x-.08,y-.237,gz),(.12,.0004,.00045),grid,0)
    cable('DAQ live waveform',[(x-.19,y-.239,.37),(x-.14,y-.239,.366),(x-.10,y-.239,.372),(x-.075,y-.239,.418),(x-.05,y-.239,.335),(x-.01,y-.239,.372),(x+.03,y-.239,.37)],.0011,trace)
    text_obj('DAQ model label','DYNAMIC SIGNAL ANALYZER',(x-.08,y-.238,.455),.018,white,(math.pi/2,0,0))
    for row,z in enumerate((.21,.27,.33)):
        for col,dx in enumerate((.11,.17,.23)):
            cylinder('BNC input',(x+dx,y-.239,z),.011,.014,aluminum,32,rotation=(math.pi/2,0,0))
            cylinder('BNC dielectric',(x+dx,y-.248,z),.006,.004,holes,24,rotation=(math.pi/2,0,0))
    cylinder('DAQ power lamp',(x-.22,y-.24,.18),.008,.008,green,32,rotation=(math.pi/2,0,0))
    cylinder('DAQ stop button',(x+.22,y-.24,.47),.018,.013,red,32,rotation=(math.pi/2,0,0))

def high_speed_camera(loc,target,frame,aluminum,glass,white,holes):
    loc=Vector(loc);target=Vector(target);direction=(target-loc).normalized();side=direction.cross(Vector((0,0,1))).normalized()
    # FASTCAM-class compact camera on a rigid optical post.  The feet and base
    # terminate exactly on the z=0 breadboard plane; nothing is floating.
    body=cube('Scientific high-speed camera body',loc,(.075,.060,.060),frame,.009)
    body.rotation_euler[2]=math.atan2(direction.y,direction.x)
    for s in (-1,1):
        for dz in (-.034,0,.034):
            p=loc+side*(s*.062)+Vector((0,0,dz));fin=cube('Camera longitudinal heat-sink rib',p,(.056,.003,.004),aluminum,.001);fin.rotation_euler[2]=body.rotation_euler[2]
    front=loc+direction*.085
    beam('F-mount adapter',front,front+direction*.035,.043,aluminum)
    beam('High-speed macro lens',front+direction*.035,front+direction*.115,.047,frame)
    beam('Coated camera glass',front+direction*.116,front+direction*.121,.040,glass)
    # Interface panel and real connector detail give the body an instrument scale.
    rear=loc-direction*.076
    panel=cube('Camera rear interface panel',rear,(.003,.050,.046),aluminum,.002);panel.rotation_euler[2]=body.rotation_euler[2]
    for dz in (-.022,.006,.030):beam('Camera locking connector',rear-direction*.003+Vector((0,0,dz)),rear-direction*.014+Vector((0,0,dz)),.007,holes)
    text_obj('Camera brand','HIGH-SPEED',loc+Vector((0,0,.063)),.014,white,(0,0,body.rotation_euler[2]))
    cube('Camera mounting shoe',loc-Vector((0,0,.078)),(.055,.045,.018),aluminum,.004)
    cylinder('Optical post clamp',loc-Vector((0,0,.116)),.045,.050,frame,64)
    cylinder('Rigid optical post',(loc.x,loc.y,.3915),.016,.735,aluminum,64)
    cylinder('Camera post base',(loc.x,loc.y,.012),.067,.024,frame,64)
    for a in (0,2*math.pi/3,4*math.pi/3):
        cylinder('Camera base cap screw',(loc.x+.044*math.cos(a),loc.y+.044*math.sin(a),.025),.0042,.006,aluminum,24)

def build(cache,out,case,samples,width,camera_id='A',preview_frame=None):
    cache=Path(cache).resolve();sim_cfg_path=cache.parent/'simulation_config.json'
    if not sim_cfg_path.is_file():raise FileNotFoundError(sim_cfg_path)
    bpy.ops.wm.read_factory_settings(use_empty=True);z=np.load(cache,allow_pickle=False);spec=SPEC;sim_cfg=json.loads(sim_cfg_path.read_text())
    if sim_cfg.get('case')!=case:raise ValueError(f'cache case {sim_cfg.get("case")} != CLI case {case}')
    if sim_cfg.get('scene_id')!=spec['scene_id']:raise ValueError(f'cache scene {sim_cfg.get("scene_id")} != renderer scene {spec["scene_id"]}')
    p=dict(sim_cfg['physics'])
    scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='GPU';scene.cycles.samples=samples;scene.cycles.use_denoising=True;scene.cycles.use_adaptive_sampling=True;scene.cycles.adaptive_threshold=.012;scene.cycles.max_bounces=9;scene.cycles.glossy_bounces=6;scene.cycles.transmission_bounces=8;scene.cycles.sample_clamp_indirect=6
    try:
        pref=bpy.context.preferences.addons['cycles'].preferences;pref.compute_device_type='OPTIX';pref.get_devices()
        for d in pref.devices:d.use=d.type in {'OPTIX','CUDA'}
    except Exception as exc:print('OPTIX_SETUP_WARNING',repr(exc),flush=True)
    times=np.asarray(z['times'],float);fps=int(sim_cfg.get('output_fps',spec['fps']))
    if len(times)<2 or not np.allclose(np.diff(times),1/fps,rtol=0,atol=1e-10):raise ValueError('Renderer requires uniform native simulation samples')
    video_frames=len(times)-1
    scene.render.resolution_x=width;scene.render.resolution_y=round(width*9/16);scene.render.resolution_percentage=100;scene.render.fps=fps;scene.frame_start=1;scene.frame_end=video_frames;scene.render.use_persistent_data=True
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB';scene.render.image_settings.color_depth='8';scene.render.image_settings.compression=15;scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=-.78;lab_world(scene)
    frame=procedural_surface('Black anodized laboratory frame',(.012,.016,.020),.72,.30,90,.045);steel=procedural_surface('Precision brushed stainless steel',(.31,.34,.36),.88,.29,155,.035);aluminum=procedural_surface('Bead-blasted aluminum',(.25,.28,.30),.82,.34,115,.032)
    holes=mat('Black threaded holes',(.002,.003,.004),.25,.55);rubber=lab_membrane_material();white=mat('Instrument lettering',(.75,.80,.82),0,.48);red=mat('Emergency red',(.62,.012,.008),.15,.28);green=emissive('Status green',(.02,.65,.12),6);glass=mat('Optical glass',(.025,.055,.07),.15,.06);screen=emissive('Oscilloscope screen',(.006,.055,.045),3.2)
    floor=procedural_surface('Sealed university lab concrete',(.16,.17,.175),0,.66,42,.08);optical_table(frame,steel,holes);cube('Laboratory floor',(0,0,-.84),(5.5,5.5,.06),floor,.002)
    # Precision circular membrane fixture on four machined posts.
    ring_r=p['membrane_clear_diameter_m']/2
    for q in (math.pi/4,3*math.pi/4,5*math.pi/4,7*math.pi/4):
        x=.45*math.cos(q);y=.45*math.sin(q);cylinder('Ground precision support post',(x,y,.35),.026,.66,steel,64);cube('Post kinematic base',(x,y,.025),(.06,.06,.025),frame,.006)
        cylinder('Post lower flange',(x,y,.056),.050,.012,aluminum,64);cylinder('Post upper flange',(x,y,.669),.048,.020,aluminum,64)
        for a in (math.pi/4,3*math.pi/4,5*math.pi/4,7*math.pi/4):
            cylinder('Flange socket screw',(x+.034*math.cos(a),y+.034*math.sin(a),.066),.0032,.004,holes,24)
    torus('Lower precision clamp ring',(0,0,p['membrane_height_m']-.015),ring_r+.027,.029,frame)
    torus('Upper precision clamp ring',(0,0,p['membrane_height_m']+.016),ring_r+.024,.023,steel)
    torus('Replaceable clamp insert',(0,0,p['membrane_height_m']+.004),ring_r+.006,.009,aluminum)
    for i in range(24):
        q=2*math.pi*i/24;x=(ring_r+.052)*math.cos(q);y=(ring_r+.052)*math.sin(q)
        cylinder('M8 clamp screw shank',(x,y,p['membrane_height_m']+.030),.0042,.012,steel,24);cylinder('M8 socket head',(x,y,p['membrane_height_m']+.039),.0073,.007,steel,48);cylinder('Socket recess',(x,y,p['membrane_height_m']+.043),.0032,.001,holes,6);cylinder('Precision washer',(x,y,p['membrane_height_m']+.024),.010,.0022,steel,40)
    membrane=build_membrane(z,rubber)
    if membrane is not None:
        uv=membrane.data.uv_layers.new(name='DIC coordinates');rest=z['membrane_rest_positions'];radius=max(np.linalg.norm(rest[:,:2],axis=1).max(),1e-9)
        for loop in membrane.data.loops:uv.data[loop.index].uv=rest[loop.vertex_index,:2]/(2*radius)+.5
    # DELETE ball (rigid_body_present[0] == 0): no drop sphere.
    ball=animate_ball(z,p,steel,frame) if bool(z['rigid_body_present'][0]) else None
    if bool(z['second_ball_present'][0]):
        animate_ball(z,p,steel,frame,'second_ball_transforms','second_ball_radius_m','304 stainless pre-positioned sphere')
    # Symmetric T-slot release gantry and electromagnetic release head.
    for x in (-.58,.58):
        cube('80x40 T-slot gantry column',(x,.42,.73),(.032,.048,.73),frame,.004);cube('Gantry anchor plate',(x,.42,.018),(.095,.11,.018),aluminum,.006)
        cube('Continuous T-slot reveal',(x,.370,.73),(.006,.003,.64),holes,.001)
    cube('Release gantry crossbeam',(0,.42,1.43),(.62,.048,.042),frame,.004)
    cube('Linear adjustment carriage',(0,.40,1.36),(.11,.075,.065),aluminum,.008)
    # Forward cantilever places the pole face on the ball centreline, so the release head
    # sits directly above the ball.
    cube('Release head cantilever',(0,.205,1.345),(.044,.195,.028),frame,.004)
    beam('Cantilever left gusset',(-.055,.39,1.34),(-.055,.055,1.285),.012,aluminum)
    beam('Cantilever right gusset',(.055,.39,1.34),(.055,.055,1.285),.012,aluminum)
    cylinder('Electromagnetic release coil',(0,0,1.225),.055,.15,frame,96);cylinder('Hardened pole face',(0,0,1.145),.026,.010,steel,96)
    cylinder('Mechanical safety collar',(0,0,1.305),.066,.024,aluminum,96)
    text_obj('Release label','ELECTROMAGNETIC RELEASE',(0,.318,1.39),.018,white,(math.pi/2,0,0))
    # Camera, LED backlight, signal analyzer, cables and calibration scale.
    high_speed_camera((-.96,-.12,.90),(0,0,.69),frame,aluminum,glass,white,holes)
    instrument_rack(1.05,.36,frame,aluminum,screen,white,red,green,holes)
    cube('Diffuse LED backlight panel',(0,.83,.82),(.42,.018,.31),emissive('LED diffuser',(.70,.82,1.0),1.15),.008)
    for x in (-.45,.45):cube('LED panel side rail',(x,.855,.82),(.018,.027,.35),frame,.005)
    for zrail in (.48,1.16):cube('LED panel cross rail',(0,.855,zrail),(.45,.027,.018),frame,.005)
    for x in (-.43,.43):beam('LED panel stand',(x,.88,.02),(x,.88,.47),.018,frame)
    cube('Vertical calibration scale',(-.52,-.02,.69),(.008,.023,.29),aluminum,.002)
    cube('Scale upper clamp',(-.49,-.01,.90),(.035,.035,.014),frame,.004);cube('Scale lower clamp',(-.49,-.01,.48),(.035,.035,.014),frame,.004)
    beam('Scale upper clamp arm',(-.49,-.01,.90),(-.58,.365,.90),.009,aluminum);beam('Scale lower clamp arm',(-.49,-.01,.48),(-.58,.365,.48),.009,aluminum)
    for zt in np.linspace(.43,.95,27):cube('Millimetre scale tick',(-.51,-.047,zt),(.001,.014 if int(round(zt*100))%5==0 else .008,.0011),holes,0)
    # Two compact optical gates independently timestamp the ball before impact.
    for gate_z in (1.035,.955):
        cube('Photogate transmitter',(-.122,.025,gate_z),(.028,.034,.029),frame,.004);cube('Photogate receiver',(.122,.025,gate_z),(.028,.034,.029),frame,.004)
        cylinder('Photogate IR aperture',(-.092,-.010,gate_z),.006,.003,glass,32,rotation=(0,math.pi/2,0));cylinder('Photogate IR aperture',(.092,-.010,gate_z),.006,.003,glass,32,rotation=(0,math.pi/2,0))
        cube('Photogate left cantilever',(-.145,.225,gate_z-.030),(.010,.195,.008),aluminum,.002);cube('Photogate right cantilever',(.145,.225,gate_z-.030),(.010,.195,.008),aluminum,.002)
    for xrail in (-.155,.155):cube('Photogate support rail',(xrail,.420,.58),(.009,.009,.58),aluminum,.002)
    cube('Photogate support bridge',(0,.420,1.155),(.164,.009,.009),aluminum,.002)
    cable('Camera data cable',[(-1.046,-.131,.894),(-1.12,.05,.45),(-1.12,.70,.035),(.84,.585,.12)],.006,holes)
    cylinder('Release cable gland',(0,.058,1.24),.010,.010,holes,32,rotation=(math.pi/2,0,0))
    cable('Release trigger cable',[(0,.058,1.24),(0,.08,1.315),(0,.36,1.315),(.56,.44,1.30),(.67,.70,.40),(.89,.585,.30)],.004,holes)
    cable('Lower photogate cable',[(.151,.055,.955),(.155,.420,.955),(.24,.76,.035),(.84,.585,.22)],.003,holes)
    cable('Upper photogate cable',[(.151,.055,1.035),(.155,.420,1.035),(.30,.76,.035),(.86,.585,.26)],.003,holes)
    # Clear rear/side guard panels leave the camera-facing side open.
    acrylic=mat('Clear polycarbonate guard',(.22,.32,.36),0,.08);bs=acrylic.node_tree.nodes.get('Principled BSDF');bs.inputs['Transmission Weight'].default_value=.78;bs.inputs['Alpha'].default_value=.28;acrylic.surface_render_method='DITHERED'
    cube('Rear safety shield',(0,.99,.72),(.82,.006,.70),acrylic,.004);cube('Safety shield top rail',(0,.99,1.43),(.84,.018,.018),aluminum,.003)
    # Studio-quality lab lighting: broad reflections reveal the membrane slope.
    for name,loc,energy,size,size_y,color,target in [('Large overhead softbox',(.2,-.35,2.45),430,1.35,.75,(.86,.92,1.0),(0,0,.67)),('Left shape strip',(-1.55,-.55,1.20),310,.85,.20,(.62,.78,1.0),(0,0,.70)),('Warm instrument rim',(1.45,.72,1.58),270,.70,.24,(1.0,.72,.48),(0,0,.70))]:
        data=bpy.data.lights.new(name,'AREA');data.energy=energy;data.shape='RECTANGLE';data.size=size;data.size_y=size_y;data.color=color;o=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
    cameras={'A':((1.68,-2.85,2.98),(0,0,.86),62),'B':((1.55,-2.05,1.90),(0,0,.69),60),'C':((1.78,-2.35,1.42),(0,0,.67),66)}
    loc,target,lens=cameras[camera_id];cdata=bpy.data.cameras.new('Main camera');cam=bpy.data.objects.new('Main camera',cdata);bpy.context.collection.objects.link(cam);scene.camera=cam;cam.location=loc;cdata.lens=lens;cdata.sensor_width=36;cdata.dof.use_dof=True;cdata.dof.focus_object=membrane or bpy.data.objects['Upper precision clamp ring'];cdata.dof.aperture_fstop=8;point_camera(cam,target)
    appearance=apply_realism(scene,samples)
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Render on a Linux GPU host')
    out.mkdir(parents=True,exist_ok=True);frames=out/'frames'
    if preview_frame is None and frames.exists():shutil.rmtree(frames)
    frames.mkdir(exist_ok=True);scene.render.filepath=str(frames/'frame_');bpy.context.view_layer.update();bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'),compress=True);started=time.monotonic()
    if preview_frame is not None:
        scene.frame_set(preview_frame);scene.render.filepath=str(out/f'preview_{camera_id}_{preview_frame:04d}.png');bpy.ops.render.render(write_still=True)
    else:
        bpy.ops.render.render(animation=True);subprocess.run(['ffmpeg','-y','-framerate',str(fps),'-i',str(frames/'frame_%04d.png'),'-frames:v',str(video_frames),'-c:v','libx264','-crf','14','-pix_fmt','yuv420p','-movflags','+faststart',str(out/'video.mp4')],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    prompts={'scene_id':spec['scene_id'],'case_id':case,'edit_dsl':sim_cfg.get('edit_dsl'),'setting':'university mechanics laboratory controlled impact test','camera_id':camera_id,'source_prompt_zh':'大学物理与力学实验室内，电磁释放器将抛光钢球自由释放到圆形双压环中张紧的黑色乳胶膜上；高速相机、LED背光和动态信号分析仪记录撞击与形变。','source_prompt_en':'In a university physics and mechanics laboratory, an electromagnetic release drops a polished steel ball onto a black latex membrane tensioned in a bolted circular clamp while a high-speed camera, LED backlight and dynamic signal analyzer record the impact and deformation.','case_note_zh':'膜中心已预置一个同尺寸、同质量的动态钢球，原球随后沿同一轴线撞击它。' if p['second_ball_present'] else None,'case_note_en':'An identical dynamic steel ball is pre-positioned at the membrane centre; the original ball subsequently strikes it on-axis.' if p['second_ball_present'] else None}
    (out/'prompts.json').write_text(json.dumps(prompts,ensure_ascii=False,indent=2),encoding='utf-8');report={'status':'preview' if preview_frame is not None else 'complete','scene_id':sim_cfg['scene_id'],'case':case,'camera_id':camera_id,'frames':1 if preview_frame is not None else video_frames,'source_frame_count':len(times),'simulation_duration_s':float(times[-1]-times[0]),'playback_rate':1.0,'final_endpoint_in_cache_only':True,'fps':fps,'resolution':[scene.render.resolution_x,scene.render.resolution_y],'samples':samples,'cache_schema_version':int(z['cache_schema_version'][0]),'visible_rigid_objects':['ball']+(['second_ball'] if p['second_ball_present'] else []),'cache_sha256':sha256(cache),'spec_sha256':sha256(SPEC_PATH),'camera_matrix_world':[list(row) for row in cam.matrix_world],'engine':'Blender 4.3.2 Cycles/OptiX','environment':'Poly Haven University Workshop 4K HDRI + modeled university mechanics lab workcell','execution_host':socket.gethostname().split('.')[0],'appearance':appearance,'local_blender_used':False,'wall_seconds':time.monotonic()-started};(out/'render_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('LAB_RENDER_COMPLETE',case,camera_id,report['wall_seconds'])

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cache',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--case',required=True);ap.add_argument('--samples',type=int,default=256);ap.add_argument('--width',type=int,default=1280);ap.add_argument('--camera',choices=['A','B','C'],default='B');ap.add_argument('--preview-frame',type=int)
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:];a=ap.parse_args(argv);build(a.cache.resolve(),a.out.resolve(),a.case,a.samples,a.width,a.camera,a.preview_frame)
if __name__=='__main__':main()
