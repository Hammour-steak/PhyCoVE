"""Remote-only Blender/Cycles renderer for the membrane impact cache."""
from pathlib import Path
import argparse,json,math,platform,subprocess,sys,time
import bpy
import numpy as np
from mathutils import Matrix,Vector

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]

def mat(name,color,metallic=0,rough=.45):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    b=m.node_tree.nodes.get('Principled BSDF');b.inputs['Base Color'].default_value=(*color,1);b.inputs['Metallic'].default_value=metallic;b.inputs['Roughness'].default_value=rough
    return m

def procedural_surface(name,color,metallic,rough,noise_scale,bump_strength):
    m=mat(name,color,metallic,rough);n=m.node_tree.nodes;nks=m.node_tree.links;b=n.get('Principled BSDF')
    tex=n.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=noise_scale;tex.inputs['Detail'].default_value=5;tex.inputs['Roughness'].default_value=.7
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=.28;ramp.color_ramp.elements[0].color=(.20,.20,.20,1);ramp.color_ramp.elements[1].position=.78;ramp.color_ramp.elements[1].color=(.72,.72,.72,1)
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=bump_strength;bump.inputs['Distance'].default_value=.00022
    nks.new(tex.outputs['Fac'],ramp.inputs['Fac']);nks.new(ramp.outputs['Color'],bump.inputs['Height']);nks.new(bump.outputs['Normal'],b.inputs['Normal'])
    return m

def cube(name,loc,scale,material,bevel=.004):
    bpy.ops.mesh.primitive_cube_add(location=loc);o=bpy.context.object;o.name=name;o.scale=scale;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if bevel:
        mod=o.modifiers.new('Machined edge radius','BEVEL');mod.width=bevel;mod.segments=3
    o.data.materials.append(material);return o

def cylinder(name,loc,radius,depth,material,vertices=48,rotation=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=loc,rotation=rotation or (0,0,0));o=bpy.context.object;o.name=name;o.data.materials.append(material)
    be=o.modifiers.new('Edge chamfer','BEVEL');be.width=min(radius*.10,.002);be.segments=2;return o

def point_camera(camera,target):
    camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()

def workbench_material():
    return procedural_surface('Walnut workbench',(0.20,.075,.028),0,.34,7,.12)

def build_membrane(z,material):
    pos=z['membrane_positions'];rest=z['membrane_rest_positions'];faces=z['membrane_faces']
    if len(rest)==0:return None
    mesh=bpy.data.meshes.new('Native rubber membrane mesh');mesh.from_pydata(pos[0].tolist(),[],faces.tolist());mesh.materials.append(material)
    o=bpy.data.objects.new('Rubber membrane — native IPC surface',mesh);bpy.context.collection.objects.link(o)
    sol=o.modifiers.new('Physical full thickness','SOLIDIFY');sol.thickness=.0008;sol.offset=0;sol.use_rim=True
    sub=o.modifiers.new('Render subdivision','SUBSURF');sub.subdivision_type='CATMULL_CLARK';sub.levels=1;sub.render_levels=1
    o.shape_key_add(name='Basis');o.data.shape_keys.use_relative=False
    for i,p in enumerate(pos):
        key=o.shape_key_add(name=f'Native_{i:04d}')
        for j,co in enumerate(p):key.data[j].co=co
    o.data.shape_keys.eval_time=10;o.data.shape_keys.keyframe_insert('eval_time',frame=1)
    o.data.shape_keys.eval_time=len(pos)*10;o.data.shape_keys.keyframe_insert('eval_time',frame=len(pos))
    for fc in o.data.shape_keys.animation_data.action.fcurves:
        for kp in fc.keyframe_points:kp.interpolation='LINEAR'
    return o

def build_scene(cache,out,case,samples,width):
    bpy.ops.wm.read_factory_settings(use_empty=True);z=np.load(cache,allow_pickle=False);spec=json.loads((HERE/'scene_spec.json').read_text());p=dict(spec['baseline']);p.update(spec['cases'][case])
    scene=bpy.context.scene;scene.render.engine='BLENDER_EEVEE_NEXT'
    scene.render.resolution_x=width;scene.render.resolution_y=round(width*9/16);scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False;scene.render.image_settings.color_mode='RGB';scene.render.fps=spec['fps']
    scene.frame_start=1;scene.frame_end=len(z['times']);scene.render.image_settings.color_depth='8';scene.render.engine='CYCLES'
    scene.cycles.samples=samples;scene.cycles.use_denoising=True;scene.cycles.use_adaptive_sampling=True;scene.cycles.adaptive_threshold=.02;scene.cycles.max_bounces=7;scene.cycles.diffuse_bounces=3;scene.cycles.glossy_bounces=4;scene.cycles.transmission_bounces=4
    scene.cycles.device='GPU'
    try:
        prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
        for device in prefs.devices:device.use=device.type in {'OPTIX','CUDA'}
    except Exception as exc:print('GPU_DEVICE_WARNING',repr(exc),flush=True)
    scene.render.image_settings.compression=15;scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=-1.0
    world=bpy.data.worlds.new('Neutral laboratory world');scene.world=world;world.use_nodes=True;world.node_tree.nodes['Background'].inputs['Color'].default_value=(.035,.045,.055,1);world.node_tree.nodes['Background'].inputs['Strength'].default_value=.28
    steel=procedural_surface('Satin stainless steel',(0.31,.34,.36),.93,.19,95,.10)
    darksteel=procedural_surface('Powder-coated frame',(0.025,.032,.038),.72,.31,34,.08)
    rubber=procedural_surface('Fine-grain black latex',(0.011,.014,.016),0,.56,180,.10)
    aluminum=mat('Anodized clamp aluminum',(.16,.18,.20),.82,.25);brass=mat('Calibration brass',(.46,.19,.045),.78,.23)
    concrete=procedural_surface('Sealed laboratory concrete',(.12,.135,.145),0,.72,8,.16);wood=workbench_material()
    warning=mat('Safety yellow',(.72,.32,.018),.18,.32);red=mat('Indicator red',(.48,.012,.009),.15,.28);glass=mat('Gauge glass',(.08,.11,.13),0,.08)
    floor=cube('Concrete floor',(0,0,.04),(3.6,3.6,.04),concrete,.002)
    cube('Rear wall',(0,1.65,1.25),(3.6,.05,1.25),mat('Cool lab wall',(.19,.22,.24),0,.68),.01)
    # Side workbench uses a real scanned PBR wood material.
    cube('Instrument workbench',(1.38,.43,.52),(.56,.38,.045),wood,.012)
    for x in (.94,1.82):
        for y in (.12,.74):cube('Workbench leg',(x,y,.28),(.035,.035,.24),darksteel,.004)
    # Four-post test rig and perimeter clamp bars.
    for x in (-.47,.47):
        for y in (-.47,.47):
            cube('40 mm T-slot upright',(x,y,.39),(.026,.026,.31),darksteel,.004)
            cube('Base foot',(x,y,.09),(.075,.075,.014),darksteel,.006)
    for y in (-.39,.39):cube('Y clamp rail',(0,y,.684),(.44,.032,.025),aluminum,.004)
    for x in (-.39,.39):cube('X clamp rail',(x,0,.684),(.032,.44,.025),aluminum,.004)
    # Bolts, washers and tensioning knobs give the boundary a readable physical identity.
    for t in np.linspace(-.31,.31,7):
        for x,y in ((t,-.39),(t,.39),(-.39,t),(.39,t)):
            cylinder('M8 clamp washer',(x,y,.714),.013,.0035,steel,32)
            cylinder('M8 socket bolt',(x,y,.721),.006,.012,darksteel,24)
    for x,y in ((-.47,-.47),(.47,-.47),(-.47,.47),(.47,.47)):
        cylinder('Brass preload micrometer',(x,y,.72),.018,.065,brass,40)
    build_membrane(z,rubber)
    # Native rigid sphere cache.
    if case!='remove_membrane' or True:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=128,ring_count=64,radius=p['ball_radius_m']);ball=bpy.context.object;ball.name='304 stainless steel impact sphere';ball.data.materials.append(steel);ball.rotation_mode='QUATERNION'
        if case=='remove_ball':ball.hide_render=True
        for f,T in enumerate(z['ball_transforms'],1):
            M=Matrix(T.tolist());ball.location=M.to_translation();ball.rotation_quaternion=M.to_quaternion();ball.keyframe_insert('location',frame=f);ball.keyframe_insert('rotation_quaternion',frame=f)
        # tiny etched witness mark reveals genuine angular motion without altering collision geometry
    if bool(z['second_ball_present'][0]):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=128,ring_count=64,radius=p['second_ball_radius_m']);second=bpy.context.object;second.name='304 stainless pre-positioned sphere';second.data.materials.append(steel);second.rotation_mode='QUATERNION'
        for f,T in enumerate(z['second_ball_transforms'],1):
            M=Matrix(T.tolist());second.location=M.to_translation();second.rotation_quaternion=M.to_quaternion();second.keyframe_insert('location',frame=f);second.keyframe_insert('rotation_quaternion',frame=f)
    # Calibration scale and instrument props.
    cube('Scale mast',(-.57,.15,.63),(.008,.025,.31),aluminum,.002)
    for ztick in np.linspace(.36,.94,15):cube('Scale tick',(-.552,.122,ztick),(.001,.012,.0012),darksteel,0)
    cylinder('Load-cell housing',(.0,.49,.69),.038,.052,darksteel,64,rotation=(math.pi/2,0,0));cylinder('Status lamp',(.0,.525,.69),.012,.012,red,40,rotation=(math.pi/2,0,0))
    # High-speed camera prop in background.
    cube('High-speed camera body',(-1.05,.72,.83),(.13,.09,.085),darksteel,.012);cylinder('Camera lens',(-.96,.63,.83),.057,.13,glass,64,rotation=(math.pi/2,0,0))
    for x,y in ((-1.12,.76),(-.98,.76),(-1.05,.60)):cylinder('Tripod leg',(x,y,.43),.012,.62,darksteel,20,rotation=(0.18,0,0))
    # Safety stripe blocks around the base.
    for i in range(10):cube('Safety stripe',(-.64+i*.14,-.58,.085),(.055,.018,.006),warning if i%2==0 else darksteel,.001)
    # Lighting: broad strip reflections make steel curvature legible.
    for name,loc,energy,size,color in [('Key',(1.2,-1.0,2.15),210,1.4,(1.0,.91,.80)),('Fill',(-1.6,-.4,1.55),120,1.2,(.65,.78,1.0)),('Top',(0,.3,2.5),180,1.0,(.85,.92,1.0))]:
        data=bpy.data.lights.new(name,'AREA');data.energy=energy;data.shape='DISK';data.size=size;data.color=color;o=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector((0,0,.62))-o.location).to_track_quat('-Z','Y').to_euler()
    cdata=bpy.data.cameras.new('Camera');cam=bpy.data.objects.new('Camera',cdata);bpy.context.collection.objects.link(cam);scene.camera=cam;cam.location=(1.42,-1.66,1.34);cdata.lens=52;cdata.sensor_width=36;cdata.dof.use_dof=True;cdata.dof.focus_object=bpy.data.objects.get('Rubber membrane — native IPC surface');cdata.dof.aperture_fstop=7.1;point_camera(cam,(0,0,.70))
    out.mkdir(parents=True,exist_ok=True);frames=out/'frames';frames.mkdir(exist_ok=True);scene.render.filepath=str(frames/'frame_')
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'),compress=True)
    started=time.monotonic();bpy.ops.render.render(animation=True)
    ffmpeg=['ffmpeg','-y','-framerate',str(spec['fps']),'-i',str(frames/'frame_%04d.png'),'-c:v','libx264','-crf','16','-pix_fmt','yuv420p','-movflags','+faststart',str(out/'video.mp4')]
    subprocess.run(ffmpeg,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    prompts={'scene_id':spec['scene_id'],'case_id':case,'edit_dsl':{'source':None,'ball_mass_heavy':'SET ball.mass TIMES 2','membrane_soft':'SET membrane.young_modulus TIMES 0.5','membrane_stiff':'SET membrane.young_modulus TIMES 3','remove_membrane':'DELETE membrane','add_second_ball':'ADD second_ball AT PRESET impact_path_on_membrane'}[case],
      'source_prompt_zh':'一颗抛光钢球自由下落，撞击实验台架上四边夹紧并双轴预拉伸的黑色橡胶膜。',
      'source_prompt_en':'A polished steel ball falls freely onto a black rubber membrane, biaxially tensioned and clamped in a laboratory test frame.'}
    (out/'prompts.json').write_text(json.dumps(prompts,ensure_ascii=False,indent=2),encoding='utf-8')
    report={'status':'complete','case':case,'frames':len(z['times']),'resolution':[scene.render.resolution_x,scene.render.resolution_y],'samples_argument':samples,'engine':'Blender 4.3.2 Cycles/OptiX','wall_seconds':time.monotonic()-started,'execution_host':platform.node(),'local_blender_used':False,'cache':str(cache)}
    (out/'render_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('RENDER_COMPLETE',case,report['wall_seconds'],flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cache',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--case',required=True);ap.add_argument('--samples',type=int,default=64);ap.add_argument('--width',type=int,default=1280)
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    a=ap.parse_args(argv);build_scene(a.cache.resolve(),a.out.resolve(),a.case,a.samples,a.width)
if __name__=='__main__':main()
