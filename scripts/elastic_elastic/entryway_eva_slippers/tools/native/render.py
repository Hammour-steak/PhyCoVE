"""Remote Cycles replay of the exact native FEM boundary at24Hz."""
from pathlib import Path
import argparse,os,socket,subprocess,sys,time
import bpy,numpy as np
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import FORMAL,INPUTS,save,read,sha
sys.path.insert(0,str(FORMAL))
from edit_vocab import SPEC,parameters
from geometry import doorstop

def material(name,color,roughness=.6):
 m=bpy.data.materials.new(name);m.use_nodes=True;p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,1.);p.inputs['Roughness'].default_value=roughness;return m

def mesh_object(name,v,f,mat=None):
 m=bpy.data.meshes.new(name);m.from_pydata(np.asarray(v).tolist(),[],np.asarray(f).tolist());m.update();o=bpy.data.objects.new(name,m);bpy.context.collection.objects.link(o)
 if mat:o.data.materials.append(mat)
 return o

def box(name,center,dims,mat,bevel=0.):
 bpy.ops.mesh.primitive_cube_add(size=1,location=center);o=bpy.context.object;o.name=name;o.dimensions=dims;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(mat)
 if mat.get('pcve_metric_uv',False):
  layer=o.data.uv_layers.active
  for poly in o.data.polygons:
   axis=int(np.argmax(np.abs(poly.normal)));axes=[j for j in range(3) if j!=axis]
   for loop in poly.loop_indices:
    point=o.data.vertices[o.data.loops[loop].vertex_index].co;layer.data[loop].uv=(point[axes[0]],point[axes[1]])
 if bevel:
  b=o.modifiers.new('Manufactured edge rounding','BEVEL');b.width=bevel;b.segments=3;o.modifiers.new('Weighted shading','WEIGHTED_NORMAL')
 return o

def pbr(name,asset,scale):
 m=material(name,(.5,.5,.5));m['pcve_metric_uv']=True;n=m.node_tree.nodes;l=m.node_tree.links;p=n.get('Principled BSDF');tc=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeVectorMath');mapping.operation='SCALE';mapping.inputs[3].default_value=scale;l.new(tc.outputs['UV'],mapping.inputs[0]);manifest=read(INPUTS/'assets/asset_manifest.json')
 for kind,target in [('Diffuse','Base Color'),('Rough','Roughness'),('nor_gl',None)]:
  e=next(x for x in manifest if x.get('asset_id')==asset and x.get('channel')==kind);t=n.new('ShaderNodeTexImage');t.image=bpy.data.images.load(str(INPUTS/'assets'/e['file']),check_existing=True);l.new(mapping.outputs['Vector'],t.inputs['Vector'])
  if kind!='Diffuse':t.image.colorspace_settings.name='Non-Color'
  if target:l.new(t.outputs['Color'],p.inputs[target])
  else:
   normal=n.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.55;l.new(t.outputs['Color'],normal.inputs['Color']);l.new(normal.outputs['Normal'],p.inputs['Normal'])
 return m

def foam_materials():
 source=INPUTS/'geometry/slide_cc0_artist';report=read(source/'materials_original.json')
 with bpy.data.libraries.load(str(source/'materials_original.blend'),link=False) as (src,dst):
  if any(n not in src.materials for n in report['materials']):raise RuntimeError('Authored material names missing: '+str(src.materials))
  dst.materials=report['materials']
 result=[]
 for i,m in enumerate(dst.materials):
  m.name='EVA slide | authored material '+str(i);m.use_nodes=True;n=m.node_tree.nodes;l=m.node_tree.links;p=next(x for x in n if x.type=='BSDF_PRINCIPLED');p.inputs['Metallic'].default_value=0.;p.inputs['Coat Weight'].default_value=0.;p.inputs['Subsurface Weight'].default_value=.015
  if not p.inputs['Roughness'].is_linked:p.inputs['Roughness'].default_value=.58
  old=p.inputs['Normal'].links[0].from_socket if p.inputs['Normal'].is_linked else None
  attr=n.new('ShaderNodeAttribute');attr.attribute_name='eva_rest';noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=2400.;noise.inputs['Detail'].default_value=2.;l.new(attr.outputs['Vector'],noise.inputs['Vector']);bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000025;bump.inputs['Strength'].default_value=.14;l.new(noise.outputs['Fac'],bump.inputs['Height'])
  if old:l.new(old,bump.inputs['Normal'])
  l.new(bump.outputs['Normal'],p.inputs['Normal']);result.append(m)
 return result

def bench():
 path=INPUTS/'assets/shoe_bench_artist.blend'
 with bpy.data.libraries.load(str(path),link=False) as (src,dst):dst.objects=src.objects
 loaded=[o for o in dst.objects if o and o.type not in ('CAMERA','LIGHT')]
 for o in loaded:bpy.context.collection.objects.link(o)
 bpy.context.view_layer.update();points=np.array([tuple(o.matrix_world@Vector(c)) for o in loaded if o.type=='MESH' for c in o.bound_box]);lo=points.min(0);hi=points.max(0);parent=bpy.data.objects.new('BlenderKit entryway shoe bench',None);bpy.context.collection.objects.link(parent)
 for o in loaded:
  o.name='Entryway bench | '+o.name
  if o.parent not in loaded:o.parent=parent
 parent.matrix_world=Matrix.Translation(Vector((.27,1.04,-lo[2])))@Matrix.Translation(Vector((-(lo[0]+hi[0])/2,-(lo[1]+hi[1])/2,0)))

def area(name,location,power,size,target,color=(1.,1.,1.)):
 d=bpy.data.lights.new(name,'AREA');d.energy=power;d.shape='DISK';d.size=size;d.color=color;o=bpy.data.objects.new(name,d);bpy.context.collection.objects.link(o);o.location=location;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()

def gpu_setup(cpu_preview=False):
 if cpu_preview:
  if os.environ.get('CUDA_VISIBLE_DEVICES','')!='':raise RuntimeError('CPU preview must run with GPUs hidden')
  return dict(host=socket.gethostname().split('.')[0],device='remote_CPU_diagnostic_stills',gpu_uuid=None,blender=bpy.app.version_string,local_blender_used=False)
 uuid=os.environ.get('CUDA_VISIBLE_DEVICES','')
 if not uuid.startswith('GPU-') or ',' in uuid:raise RuntimeError('Bind one inspected pool GPU for rendering')
 prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices();devices=[d for d in prefs.devices if d.type=='OPTIX'];bus=subprocess.check_output(['nvidia-smi','-i',uuid,'--query-gpu=pci.bus_id','--format=csv,noheader'],text=True).strip().lower();short=':'.join(bus.split(':')[-2:]).split('.')[0]
 chosen=devices if len(devices)==1 else [d for d in devices if short in d.id.lower()]
 if len(chosen)!=1:raise RuntimeError('Cycles device cannot be unambiguously matched to selected GPU')
 for d in prefs.devices:d.use=d==chosen[0]
 return dict(host=socket.gethostname().split('.')[0],gpu_uuid=uuid,pci_bus=bus,cycles_device=chosen[0].id,blender=bpy.app.version_string,local_blender_used=False)

def build(cache,case,out,width,samples):
 bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False);scene=bpy.context.scene;scene.render.engine='CYCLES';prov=gpu_setup(build.cpu_preview);scene.cycles.device='CPU' if build.cpu_preview else 'GPU';scene.cycles.samples=samples;scene.cycles.use_denoising=True;scene.cycles.adaptive_threshold=.01;scene.cycles.max_bounces=8;scene.render.resolution_x=width;scene.render.resolution_y=width*9//16;scene.render.resolution_percentage=100;scene.render.fps=24;scene.frame_start=1;scene.frame_end=min(96,len(cache['positions'])-1);scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB';scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=.1;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.
 scene.world.use_nodes=True;n=scene.world.node_tree.nodes;l=scene.world.node_tree.links;env=n.new('ShaderNodeTexEnvironment');env.image=bpy.data.images.load(str(INPUTS/'assets/studio_small_09_1k.hdr'));l.new(env.outputs['Color'],n.get('Background').inputs['Color']);n.get('Background').inputs['Strength'].default_value=.2
 floor=pbr('4K scanned stone tile entryway floor','large_floor_tiles_02',.55);oak=pbr('4K scanned pale timber','plywood',1.5);wall=material('Warm mineral paint',(.72,.70,.65),.9);trim=material('Soft white painted skirting',(.65,.66,.62),.55);metal=material('Satin nickel hardware',(.4,.42,.43),.26);metal.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value=.9
 box('Continuous receiving floor',(0,.2,-.015),(8.,8.,.03),floor)
 box('Entryway wall',(0,1.74,1.2),(6.,.08,2.4),wall)
 box('Painted skirting',(0,1.68,.055),(6.,.025,.11),trim,.003)
 box('Front door',(-.76,1.676,1.035),(.86,.045,2.07),oak,.006)
 for x in (-1.217,-.303):box('Door jamb',(x,1.65,1.055),(.045,.075,2.11),trim,.002)
 box('Door frame header',(-.76,1.65,2.09),(.96,.075,.045),trim,.002)
 box('Door handle mounting plate',(-.42,1.64,.95),(.045,.012,.14),metal,.008);box('Lever handle',(-.46,1.61,.96),(.13,.025,.022),metal,.008)
 bench()
 mats=foam_materials()
 # NpzFile has no stable filename API across NumPy versions: caller supplies level.
 level=build.level;shape=np.load(INPUTS/'accepted_delivery/geometry_d'/Path(build.geometry_file).name);actors=[]
 for part,name in [(0,'Falling EVA slide'),(1,'Initially resting EVA slide')]:
  mask=cache['part_ids']==part
  if not mask.any():continue
  f=cache['faces'][np.all(mask[cache['faces']],axis=1)];used=np.unique(f);remap=np.full(len(mask),-1,np.int32);remap[used]=np.arange(len(used));o=mesh_object(name,cache['positions'][0,used],remap[f]);uv=shape['uv'][:,[0,2,1]] if part==1 else shape['uv'];layer=o.data.uv_layers.new(name='Authored CC0 UV')
  if len(o.data.polygons)!=len(uv):raise RuntimeError('Native boundary/UV face mapping changed')
  for m in mats:o.data.materials.append(m)
  for i,poly in enumerate(o.data.polygons):
   poly.use_smooth=True;poly.material_index=int(shape['material_ids'][i])
   for j,idx in enumerate(poly.loop_indices):layer.data[idx].uv=uv[i,j]
  attr=o.data.attributes.new('eva_rest','FLOAT_VECTOR','POINT');attr.data.foreach_set('vector',cache['rest'][used].astype(np.float32).ravel());o['geometry_source']='Exact native tetrahedral boundary; smooth normals only';o['part_id']=part;actors.append((o,used));o.shape_key_add(name='Basis')
  for frame in range(1,len(cache['positions'])):
   key=o.shape_key_add(name=f'Native_{frame:03d}');key.data.foreach_set('co',cache['positions'][frame,used].ravel());key.value=0.;key.keyframe_insert('value',frame=frame);key.value=1.;key.keyframe_insert('value',frame=frame+1);key.value=0.;key.keyframe_insert('value',frame=frame+2)
  if o.data.shape_keys.animation_data:
   for fc in o.data.shape_keys.animation_data.action.fcurves:
    for k in fc.keyframe_points:k.interpolation='LINEAR'
 p=parameters(case)
 if p.get('doorstop_present',[False])[0]:
  v,f=doorstop(p);o=mesh_object('Added fixed rubber doorstop',v,f,material('Matte rubber doorstop',(.065,.07,.065),.6))
  for poly in o.data.polygons:poly.use_smooth=True
 camera_data=bpy.data.cameras.new('Shared low entryway camera');camera=bpy.data.objects.new('Shared low entryway camera',camera_data);bpy.context.collection.objects.link(camera);camera.location=SPEC['render']['camera_m'];camera.rotation_euler=(Vector(SPEC['render']['target_m'])-camera.location).to_track_quat('-Z','Y').to_euler();camera_data.lens=SPEC['render']['lens_mm'];camera_data.clip_start=.01;camera_data.clip_end=30.;camera_data.dof.use_dof=True;focus=bpy.data.objects.new('Contact focus',None);bpy.context.collection.objects.link(focus);focus.location=(-.04,.03,.10);camera_data.dof.focus_object=focus;camera_data.dof.aperture_fstop=8.;scene.camera=camera
 area('Soft daylight from entry window',(-1.0,-.7,1.6),240.,1.4,(0,0,.06),(1.,.95,.88));area('Room bounce fill',(.9,.0,1.1),65.,1.2,(0,0,.06),(.90,.95,1.));area('Soft background lift',(-.3,1.1,1.5),80.,1.2,(0,.5,.2),(1.,.97,.91))
 scene.frame_set(1);bpy.context.view_layer.update();save(out/'render_config.json',dict(case=case,provenance=prov,width=width,height=width*9//16,fps=24,frames=scene.frame_end,samples=samples,physical_duration_s=scene.frame_end/24,native_endpoint_s=float(cache['times'][-1]),formal_contract=dict(width=1280,height=720,fps=24,frames=96,duration_s=4),retiming=False,camera_location=list(camera.location),camera_rotation=list(camera.rotation_euler),lens_mm=camera_data.lens,mesh_level=level,geometry_file=build.geometry_file,geometry_sha256=sha(INPUTS/'accepted_delivery/geometry_d'/Path(build.geometry_file).name),scene_spec_sha256=sha(INPUTS/'scene_spec.json'),render_boundary='Exact native FEM vertices, no coordinate smoothing or subdivision',decorative_collision_scope='Bench, door and wall are outside the measured native trajectory domain; the floor, both slides and optional doorstop participate in contact.'))
 return scene

def main():
 if sys.platform!='linux':raise RuntimeError('Blender rendering runs on Linux')
 p=argparse.ArgumentParser();p.add_argument('--case',choices=SPEC['cases'],required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--samples',type=int,default=160);p.add_argument('--width',type=int,default=1280);p.add_argument('--preview',nargs='*',type=int);p.add_argument('--cpu-preview',action='store_true');a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
 if a.cpu_preview and (not a.preview or len(a.preview)>4):raise RuntimeError('Remote CPU mode is limited to four diagnostic stills')
 a.out.mkdir(parents=True,exist_ok=True);cfg=read(a.cache.parent/'simulation_config.json');build.level=cfg['mesh_level'];build.cpu_preview=a.cpu_preview;build.geometry_file=cfg.get('geometry_file',f"slipper_{build.level}_uniform.npz");z=np.load(a.cache);scene=build(z,a.case,a.out,a.width,a.samples);bpy.ops.file.pack_all();bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'scene.blend'),compress=True)
 frames=a.preview or list(range(1,97));folder=a.out/('previews' if a.preview else 'frames');folder.mkdir(exist_ok=True);start=time.monotonic()
 if max(frames)>len(z['positions']):raise RuntimeError('Cannot synthesize missing physical frames')
 for frame in frames:scene.frame_set(frame);scene.render.filepath=str(folder/f'{frame:04d}.png');bpy.ops.render.render(write_still=True)
 save(a.out/'render_receipt.json',dict(case=a.case,frames=frames,preview=bool(a.preview),host=socket.gethostname(),gpu_uuid=os.environ['CUDA_VISIBLE_DEVICES'],cache_sha256=sha(a.cache),scene_sha256=sha(a.out/'scene.blend'),wall_s=time.monotonic()-start))
 print('RENDER_COMPLETE',a.case,len(frames),time.monotonic()-start,flush=True)

if __name__=='__main__':main()
