"""Cycles reconstruction. Baked motion comes from native dynamics."""
import argparse,json,math,os,socket,sys,time,struct,zlib,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
import numpy as np
from mathutils import Vector
from physics.scene import DATA,OUT,ASSET_DIR,BASELINE,sha,spring_constants
from appearance.render_helpers import material,wood_material,cube,cylinder,imported_prop,choose_gpu,area

def group(name):
 o=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(o);return o

def parent(o,g,identity=3):o.parent=g;o.pass_index=identity;return o

def mesh(name,vertices,faces,mat,identity=0):
 m=bpy.data.meshes.new(name);m.from_pydata(vertices,[],faces);m.update()
 o=bpy.data.objects.new(name,m);bpy.context.collection.objects.link(o);m.materials.append(mat);o.pass_index=identity
 for f in m.polygons:f.use_smooth=True
 return o

def tube(name,points,radius,mat,identity=0):
 c=bpy.data.curves.new(name,'CURVE');c.dimensions='3D';c.resolution_u=3;c.bevel_depth=radius;c.bevel_resolution=3
 sp=c.splines.new('POLY');sp.points.add(len(points)-1)
 for v,co in zip(sp.points,points):v.co=(*co,1)
 o=bpy.data.objects.new(name,c);bpy.context.collection.objects.link(o);c.materials.append(mat);o.pass_index=identity;return o

def rod(name,a,b,r,mat,identity=0):
 mid=(Vector(a)+Vector(b))/2;v=Vector(b)-Vector(a)
 o=cylinder(name,mid,r,v.length,mat);o.rotation_euler=v.to_track_quat('Z','Y').to_euler();o.pass_index=identity;return o

def text(name,body,location,size,mat,rotation=(math.pi/2,0,0),align='LEFT'):
 c=bpy.data.curves.new(name,'FONT');c.body=body;c.size=size;c.align_x=align;c.extrude=0.;c.space_line=1.3
 o=bpy.data.objects.new(name,c);bpy.context.collection.objects.link(o);o.location=location;o.rotation_euler=rotation;c.materials.append(mat);return o

def lathe(name,profile,mat,identity=0,segments=128):
 v=[(r*math.cos(i*2*math.pi/segments),r*math.sin(i*2*math.pi/segments),z) for r,z in profile for i in range(segments)]
 f=[]
 for j in range(len(profile)-1):
  for i in range(segments):f.append((j*segments+i,j*segments+(i+1)%segments,(j+1)*segments+(i+1)%segments,(j+1)*segments+i))
 return mesh(name,v,f,mat,identity)

def rough_metal(name,color,rough=.3,tool_marks=False):
 m=material(name,color,rough,.95);n=m.node_tree.nodes;l=m.node_tree.links;b=n['Principled BSDF']
 co=n.new('ShaderNodeTexCoord');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=350;noise.inputs['Detail'].default_value=3
 l.new(co.outputs['Object'],noise.inputs['Vector']);remap=n.new('ShaderNodeMapRange');remap.inputs['To Min'].default_value=rough*.85;remap.inputs['To Max'].default_value=rough*1.16
 l.new(noise.outputs['Fac'],remap.inputs['Value']);l.new(remap.outputs[0],b.inputs['Roughness'])
 if tool_marks:
  wave=n.new('ShaderNodeTexWave');wave.wave_type='RINGS';wave.rings_direction='Z';wave.inputs['Scale'].default_value=1800;wave.inputs['Distortion'].default_value=.2
  l.new(co.outputs['Object'],wave.inputs['Vector']);bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000006;bump.inputs['Strength'].default_value=.18
  l.new(wave.outputs['Color'],bump.inputs['Height']);l.new(bump.outputs['Normal'],b.inputs['Normal'])
 return m

def enamel(name,color):
 m=material(name,color,.39,.24);n=m.node_tree.nodes;l=m.node_tree.links;b=n['Principled BSDF'];b.inputs['Coat Weight'].default_value=.22;b.inputs['Coat Roughness'].default_value=.24
 co=n.new('ShaderNodeTexCoord');no=n.new('ShaderNodeTexNoise');no.inputs['Scale'].default_value=1800;no.inputs['Detail'].default_value=2;l.new(co.outputs['Object'],no.inputs['Vector'])
 bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.00003;bump.inputs['Strength'].default_value=.18;l.new(no.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],b.inputs['Normal']);return m

def bolt(name,at,steel,r=.003,axis='Y'):
 o=cylinder(name,at,r,.002,steel)
 if axis=='Y':o.rotation_euler[0]=math.pi/2
 slot=cube(name+' screwdriver slot',(at[0],at[1]-.0011,at[2]),(r*1.35,.00015,.00045),material(name+' slot darkness',(.035,.037,.038),.5),bevel=.00008)
 return [o,slot]

def coil_vertices(nodes,p):
 N=p['spring_active_turns'];segments=N*40;u=np.linspace(0,N,segments+1);j=np.minimum(np.floor(u).astype(int),N-1);f=u-j
 dz=np.diff(nodes);slope=np.r_[dz[0],2*dz[:-1]*dz[1:]/(dz[:-1]+dz[1:]),dz[-1]]
 z=(2*f**3-3*f**2+1)*nodes[j]+(f**3-2*f**2+f)*slope[j]+(-2*f**3+3*f**2)*nodes[j+1]+(f**3-f**2)*slope[j+1]
 theta=u*2*math.pi-math.pi/2;R=p['spring_mean_diameter_m']/2
 centers=np.c_[R*np.cos(theta),R*np.sin(theta),z]
 tangent=np.gradient(centers,axis=0);tangent/=np.linalg.norm(tangent,axis=1)[:,None]
 radial=np.c_[np.cos(theta),np.sin(theta),np.zeros(len(theta))];radial-=np.sum(radial*tangent,axis=1)[:,None]*tangent;radial/=np.linalg.norm(radial,axis=1)[:,None]
 binormal=np.cross(tangent,radial);a=np.arange(12)*2*math.pi/12
 verts=centers[:,None,:]+p['spring_wire_diameter_m']/2*(radial[:,None,:]*np.cos(a)[None,:,None]+binormal[:,None,:]*np.sin(a)[None,:,None])
 return verts.reshape(-1,3)

def tube_faces(rings,sides):
 return [(i*sides+j,i*sides+(j+1)%sides,(i+1)*sides+(j+1)%sides,(i+1)*sides+j) for i in range(rings-1) for j in range(sides)]

def shape_animation(obj,coords):
 obj.shape_key_add(name='Basis')
 for i,verts in enumerate(coords[1:],2):
  key=obj.shape_key_add(name=f'Native time {(i-1)/24:.6f} s');key.data.foreach_set('co',np.asarray(verts,dtype=np.float32).reshape(-1))
  for frame,value in [(i-1,0.),(i,1.),(i+1,0.)]:key.value=value;key.keyframe_insert('value',frame=frame)
 if obj.data.shape_keys.animation_data:
  for curve in obj.data.shape_keys.animation_data.action.fcurves:
   for k in curve.keyframe_points:k.interpolation='LINEAR'

def pan_pad(pad,compressions,radius,top):
 rings=20;sides=96;vs=[]
 for r in np.linspace(0,radius,rings):
  for a in np.arange(sides)*2*math.pi/sides:vs.append((r*math.cos(a),r*math.sin(a),top))
 # The contact surface is a flat-punch mode driven by the solved indentation.
 vs=np.asarray(vs);r=np.linalg.norm(vs[:,:2],axis=1);mode=np.where(r<=.016,1.,np.where(r>=.028,0.,.5+.5*np.cos(math.pi*(r-.016)/.012)))
 obj=mesh('Felt pad contact surface',vs,[f[::-1] for f in tube_faces(rings,sides)],pad,3)
 coords=[]
 for d in compressions:
  v=vs.copy();v[:,2]-=d*mode;coords.append(v)
 shape_animation(obj,coords);return obj

def weight_profile():
 profile=np.array([(0,0),(.0148,0),(.016,.001),(.016,.012),(.015,.013),(.005,.013),(.0045,.015),(.0075,.016),(.0075,.020),(.0065,.021),(0,.021)],dtype=float)
 volume=sum(math.pi*(b[1]-a[1])*(a[0]**2+a[0]*b[0]+b[0]**2)/3 for a,b in zip(profile[:-1],profile[1:]))
 profile[:,1]*=(.1/8500)/volume
 return profile,.1/8500

def environment(mats):
 wood=wood_material('Photographic worn laboratory bench',ASSET_DIR/'wood_table_001','wood_table_001',1.5)
 fine=wood_material('Fine grain calibration weight case',ASSET_DIR/'fine_grained_wood','fine_grained_wood',.6)
 cube('Laboratory bench',(.1,.0,-.027),(2.,1.4,.054),wood,.004)
 wall=material('Warm painted laboratory wall',(.40,.47,.43),.93);cube('Out of focus laboratory wall',(0,.80,1.2),(4.,.06,2.5),wall,.001)
 cube('Bench backboard',(0,.72,.10),(2.2,.035,.20),fine,.003)
 props=[imported_prop('pencil',(.38,.23),.18,.7,.0142),imported_prop('ruler_reference',(-.30,-.08),.30,1.4,0.)]
 paper=material('Experiment notebook paper',(.73,.71,.65),.86);ink=mats['ink']
 card=cube('Lab notebook',(.43,.08,.007),(.23,.28,.014),paper,.001)
 for x in [.325,.34]:cube('Notebook binding', (x,.08,.015),(.0015,.265,.001),mats['dark'],.0003)
 for y in np.linspace(-.035,.20,18):cube('Faint ruled notebook line',(.44,float(y),.0141),(.20,.00025,.00005),material('Notebook rule '+str(y),(.27,.38,.39),.9),.0)
 text('Experiment note','SPRING BALANCE\nIMPACT & DAMPING\n\nh = 85 mm\nF = kx + F0',(.355,.145,.0143),.009,ink,rotation=(0,0,0))
 # Open wooden weight box, kept well away from the moving pan.
 cube('Weight box bottom',(-.40,.18,.014),(.19,.12,.028),fine,.003)
 lining=material('Weight box felt',(.045,.06,.047),.93)
 cube('Weight box felt lining',(-.40,.18,.029),(.174,.104,.004),lining,.001)
 for x in [-.49,-.31]:cube('Box side',(x,.18,.038),(.008,.12,.025),fine,.001)
 for y in [.124,.236]:cube('Box end',(-.40,y,.038),(.19,.008,.025),fine,.001)
 lid=cube('Open box lid',(-.40,.253,.080),(.19,.009,.105),fine,.002);lid.rotation_euler[0]=-.12
 for i,r in enumerate([.010,.012,.014]):
  x=-.455+i*.054;profile=np.array([(0,0),(r,0),(r,.024),(.004,.024),(.004,.029),(.006,.029),(.006,.033),(0,.033)])
  o=lathe('Stored calibration weight',profile,mats['brass']);o.location=(x,.18,.031)
  text('Stored weight inscription',['20 g','50 g','100 g'][i],(x,.18-r-.0001,.042),.003,mats['engraving'],align='CENTER')
 return props

def integer_mask(exr,png):
 """Read the raw data pass in remote Blender; write exact uint8 PNG IDs."""
 im=bpy.data.images.load(str(exr),check_existing=False);im.colorspace_settings.name='Non-Color'
 assert tuple(im.size)==(1280,720)
 pixels=np.empty(1280*720*4,dtype=np.float32);im.pixels.foreach_get(pixels)
 raw=pixels.reshape(720,1280,4)[::-1,:,0];ids=np.rint(raw).astype(np.uint8)
 assert np.max(np.abs(raw-ids))<1e-5 and set(np.unique(ids))<={0,1,2,3,4}
 def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
 payload=b''.join(b'\0'+row.tobytes() for row in ids)
 png.parent.mkdir(parents=True,exist_ok=True)
 png.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1280,720,8,0,0,0,0))+chunk(b'IDAT',zlib.compress(payload,8))+chunk(b'IEND',b''))
 bpy.data.images.remove(im)
 return {str(k):int(np.count_nonzero(ids==k)) for k in np.unique(ids)}

def build(p,z):
 steel=rough_metal('Passivated spring steel',(.46,.49,.52),.22)
 aluminum=rough_metal('Spun aluminum pan',(.57,.60,.62),.30,True)
 brass=rough_metal('Brass calibration weight with fine lathe marks',(.52,.31,.10),.27,True)
 dark=enamel('Deep grey green enamel',(.035,.085,.076));ink=material('Printed graphite',(.015,.021,.019),.75)
 offwhite=enamel('Aged ivory enamel scale',(.72,.73,.65));red=enamel('Red pointer paint',(.49,.026,.015));rubber=material('Rubber feet',(.018,.024,.021),.79)
 mats={'steel':steel,'brass':brass,'dark':dark,'ink':ink,'engraving':material('Dark stamped brass lettering',(.055,.037,.014),.47,.4)}
 assets=environment(mats)
 # Cast base and an upright with actual brackets, screws and rubber feet.
 cube('Heavy cast laboratory stand base',(.015,.07,.035),(.46,.30,.05),dark,.016)
 for x in [-.17,.20]:
  for y in [-.05,.19]:cylinder('Rubber stand foot',(x,y,.008),.018,.016,rubber)
 rod('Stainless support upright',(-.18,.13,.06),(-.18,.13,.965),.009,steel)
 for zz in [.37,.92]:
  cube('Upright clamp',(-.18,.12,zz),(.043,.044,.037),dark,.004)
  rod('Instrument mounting bracket',(-.18,.125,zz),(.027,.115,zz),.007,steel)
  cylinder('Clamp adjustment knob',(-.21,.12,zz),.012,.015,dark).rotation_euler[1]=math.pi/2
  for o in bolt('Mounting screw',(-.18,.094,zz),steel,.004):pass
 back=enamel('Matte dark green instrument panel',(.035,.065,.057));back.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.57
 cube('Painted instrument backplate',(.04,.11,.65),(.37,.008,.592),back,.004)
 for x in [-.128,.208]:
  for zz in [.375,.925]:bolt('Backplate countersunk screw',(x,.104,zz),steel,.003)
 for x in [-.100,.100]:
  rod('Polished crosshead guide',(x,0,.283),(x,0,.911),.0025,steel)
  cube('Separate lower guide shoe',(x,0,.278),(.020,.035,.020),dark,.003)
  rod('Guide rear standoff',(x,0,.278),(x,.106,.278),.005,steel)
  rod('Lower guide mounting pillar',(x,.11,.06),(x,.11,.37),.005,steel)
  rod('Top support standoff',(x,0,.912),(x,.106,.912),.005,steel)
 cube('Upper spring support',(.0,.0,.912),(.235,.04,.026),dark,.004)
 for x in [-.100,.100]:bolt('Guide securing screw',(x,-.021,.912),steel,.003)
 rod('Zero adjustment shaft',(0,0,.871),(0,0,.941),.0025,steel)
 cylinder('Knurled zero adjustment nut',(0,0,.937),.009,.011,brass)
 for a in np.arange(24)*2*math.pi/24:
  rod('Fine zero knob knurl',(.0088*math.cos(a),.0088*math.sin(a),.932),(.0088*math.cos(a),.0088*math.sin(a),.942),.00027,steel)
 # Thread crest around the zero adjustment shaft.
 th=np.linspace(0,18*2*math.pi,720);tube('Zero screw thread',[(.0026*math.cos(a),.0026*math.sin(a),.888+a/(2*math.pi)*.0015) for a in th],.00025,steel)
 upper=[(0,-.0175,.845),(0,-.0175,.850),(0,-.010,.859),(0,-.005,.861)]
 upper+=[(.006*math.cos(t),0,.865+.006*math.sin(t)) for t in np.linspace(-math.pi/2,3*math.pi/2,90)]
 # DELETE spring (spring_present false): the helix and both formed wire eyes are absent; the clevises stay.
 spring=p.get('spring_present',True)
 if spring:tube('Upper formed spring eye and tail',upper,p['spring_wire_diameter_m']/2,steel,1)
 rod('Upper clevis pin',(0,-.007,.865),(0,.007,.865),.0018,steel)
 for y in [-.007,.007]:cube('Upper clevis ear',(0,y,.874),(.008,.002,.023),steel,.001)
 # Distributed coil geometry; all 97 keys come from the native cache.
 if spring:
  coords=[coil_vertices(nodes,p) for nodes in z['coil_node_z_m']]
  coil=mesh('Native steel helix - 28 massive turns',coords[0],tube_faces(len(coords[0])//12,12),steel,1);shape_animation(coil,coords)
 carriage=group('Native guided carriage and suspended pan');end=float(z['coil_node_z_m'][0,-1]);h=p['crosshead_height_m'];top=end-p['lower_hook_length_m'];cross=top-h/2
 lower=[(0,-.0175,end),(0,-.0175,end-.005),(0,-.010,end-.010)]
 lower+=[(.006*math.cos(t),0,end-.018+.006*math.sin(t)) for t in np.linspace(math.pi/2,5*math.pi/2,90)]
 if spring:parent(tube('Lower formed eye and tail',lower,p['spring_wire_diameter_m']/2,steel,1),carriage,1)
 parent(rod('Lower clevis pin',(0,-.007,end-.018),(0,.007,end-.018),.0018,steel),carriage)
 for y in [-.007,.007]:parent(cube('Lower clevis ear',(0,y,top+.0045),(.008,.002,.009),steel,.001),carriage)
 for zz in [cross-h/2+.00025,cross+h/2-.00025]:
  parent(cube('Hollow aluminum crosshead top or bottom',(0,0,zz),(.224,.014,.0005),aluminum,.00015),carriage)
 for yy in [-.00675,.00675]:
  parent(cube('Hollow aluminum crosshead side',(0,yy,cross),(.224,.0005,.013),aluminum,.00015),carriage)
 for xx in [-.11175,.11175]:parent(cube('Crosshead thin end cap',(xx,0,cross),(.0005,.014,.014),aluminum,.00015),carriage)
 polymer=material('POM low friction guide bushings',(.10,.115,.105),.42)
 for x in [-.100,.100]:
  bushing=lathe('Hollow polymer guide bushing',[(.0025,cross-.0085),(.004,cross-.0085),(.004,cross+.0085),(.0025,cross+.0085),(.0025,cross-.0085)],polymer,3);bushing.location.x=x;parent(bushing,carriage)
 for x in [-.032,.031]:
  for o in bolt('Crosshead small screw',(x,-.008,cross),steel,.002):parent(o,carriage)
 # Back-mounted air dashpot: long stroke, fixed body and a moving plunger.
 body=rod('Fixed slim air dashpot barrel',(.205,.027,.12),(.205,.027,.63),.008,aluminum)
 for zz in [.13,.62]:
  cube('Air dashpot mounting strap',(.205,.065,zz),(.023,.080,.015),dark,.001)
  bolt('Dashpot mounting bolt',(.205,.025,zz),steel,.0025)
 rod('Dashpot lower mounting pillar',(.205,.11,.06),(.205,.11,.40),.005,steel)
 piston=lathe('Hollow moving dashpot piston rod',[(.00085,.55),(.001,.55),(.001,cross),(.00085,cross),(.00085,.55)],steel,3);piston.location.x=.205;piston.location.y=.027;parent(piston,carriage)
 parent(rod('Crosshead dashpot coupling',(.108,0,cross),(.205,.027,cross),.001,steel),carriage)
 # Actual pointer follows the crosshead; the printed scale keeps baseline calibration.
 scale_x=.14;face_y=-.012
 cube('Ivory Newton scale',(scale_x+.016,face_y+.002,.546),(.052,.004,.552),offwhite,.0015)
 for zz in [.795,.390]:
  rod('Scale rear mounting spacer',(.177,face_y,zz),(.177,.106,zz),.0025,steel)
  bolt('Scale fastening screw',(.177,face_y-.001,zz),steel,.002)
 ei0=np.asarray(z['initial_segment_extension_m']);dc=spring_constants(BASELINE);N=28;Ms=dc['active_spring_mass_kg']
 calibration=[]
 for index in range(51):
  force=index*.1;T=(BASELINE['carriage_mass_kg']+Ms*(N-np.arange(1,N+1)+.5)/N)*9.81+force
  F0=BASELINE['spring_initial_tension_n'];e=np.where(T>=F0,(T-F0)/(N*dc['axial_rate_n_m']),(T-F0)/BASELINE['closed_turn_contact_stiffness_n_m']);travel=float(np.sum(e-ei0));zz=cross-travel
  if index%5==0:
   length=.014;text('Newton graduation '+str(force),f'{force:g}',(scale_x+.019,face_y-.0003,zz-.0033),.009,ink)
  else:length=.008
  cube('Printed Newton tick',(scale_x+length/2,face_y-.0002,zz),(length,.0001,.0007),ink,0)
  calibration.append({'load_n':force,'baseline_travel_m':travel,'z_m':zz})
 text('Scale unit','N',(scale_x+.023,face_y-.0003,cross+.018),.012,ink)
 pointer=mesh('Red pointer triangle',[(.111,-.018,cross+.004),(.147,-.018,cross),(.111,-.018,cross-.004)],[(0,1,2)],red,3);parent(pointer,carriage)
 # Suspended spun pan. Load path passes around the clear vertical fall corridor.
 pan=p['pan_pad_top_z_m'];floor=pan-.004;R=p['pan_radius_m']
 profile=[(0,floor-.0006),(R-.004,floor-.0006),(R,floor+.002),(R+.001,pan+.014),(R,pan+.015),(R-.0004,pan+.014),(R-.0006,floor+.002),(R-.004,floor),(0,floor)]
 parent(lathe('Thin spun aluminum receiving pan',profile,aluminum,3),carriage)
 theta=np.linspace(0,2*math.pi,260);parent(tube('Rolled aluminum pan rim',[(R*math.cos(a),R*math.sin(a),pan+.0145) for a in theta],.0011,aluminum),carriage)
 felt=material('Dense grey felt landing pad',(.085,.10,.095),.91)
 n=felt.node_tree.nodes;l=felt.node_tree.links;no=n.new('ShaderNodeTexNoise');no.inputs['Scale'].default_value=4500;no.inputs['Detail'].default_value=3
 bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.00012;bump.inputs['Strength'].default_value=.45;l.new(no.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],n['Principled BSDF'].inputs['Normal'])
 parent(lathe('Felt pad bottom and sides',[(0,pan-.004),(.066,pan-.004),(.066,pan)],felt,3),carriage)
 compressions=np.maximum(0,z['pan_pad_top_z_m']-z['weight_bottom_z_m']) if p['weight_present'] else np.zeros(97)
 parent(pan_pad(felt,compressions,.066,pan),carriage)
 apex=top-h-.010
 parent(rod('Pan central hanger pin',(0,0,top-h),(0,0,apex),.002,steel),carriage)
 for a in [math.pi/2,7*math.pi/6,11*math.pi/6]:
  at=(R*.96*math.cos(a),R*.96*math.sin(a),pan+.014)
  parent(rod('Three rod pan suspension',(0,0,apex),at,.00065,steel),carriage)
  parent(cylinder('Pan rim hanger eye',at,.002,.002,steel),carriage)
 weight=None;profile,volume=weight_profile()
 if p['weight_present']:
  weight=group('Native freely falling calibration weight');parent(lathe('Machined calibration mass',profile,brass,2),weight,2)
  parent(text('Stamped weight value',f"{round(p['weight_mass_kg']*1000)} g",(0,-.0161,.007),.0045,mats['engraving'],align='CENTER'),weight,2)
  for zz in [.0015,.012]:
   parent(tube('Fine circumferential machining groove',[(.01603*math.cos(a),.01603*math.sin(a),zz) for a in theta],.00007,mats['engraving'],2),weight,2)
  weight.location.z=float(z['weight_bottom_z_m'][0])
 # New collar has a compliant upper bumper with exactly the solver travel threshold.
 stop_objects=[]
 if p['stop_present']:
  orange=enamel('Added stop safety orange',(.57,.15,.018));center=p['stop_center_m'];size=p['stop_dimensions_m']
  assert abs(center[2]+size[2]/2-(top-h-p['stop_travel_m']))<1e-10
  stop_objects.append(cube('Added bolted travel stop',(center[0],center[1],center[2]-.00075),(size[0],size[1],size[2]-.0015),orange,.002,identity=4))
  pad=cube('Stop compliant rubber bumper',(center[0],0,center[2]+size[2]/2-.00075),(.023,.028,.0015),rubber,.0002,identity=4);stop_objects.append(pad)
  for i in range(97):
   compression=max(float(z['states'][i,27])-p['stop_travel_m'],0.);height=.0015-compression;assert height>0
   pad.scale.z=height/.0015;pad.location.z=center[2]+size[2]/2-.0015+height/2;pad.keyframe_insert('scale',frame=i+1);pad.keyframe_insert('location',frame=i+1)
  for o in bolt('Added stop clamping screw',(center[0],-.017,center[2]),steel,.003):o.pass_index=4;stop_objects.append(o)
  text('Stop collar travel marking','80 mm',(center[0]-.01,-.0172,center[2]+.002),.0045,ink).pass_index=4
 # Bake true sampled rigid states. No imposed spring motion or pose edits.
 for i in range(97):
  carriage.location.z=-float(z['states'][i,27]);carriage.keyframe_insert('location',frame=i+1)
  if weight:weight.location.z=float(z['weight_bottom_z_m'][i]);weight.keyframe_insert('location',frame=i+1)
 for obj in [carriage,weight]:
  if obj and obj.animation_data:
   for f in obj.animation_data.action.fcurves:
    for k in f.keyframe_points:k.interpolation='LINEAR'
 text('Instrument nameplate','SPRING BALANCE\n0 - 5 N  |  LAB 18',(-.052,-.021,.906),.007,offwhite)
 return {'assets':assets,'scale_calibration':calibration,'weight_external_volume_m3':volume,
 'weight_effective_density_kg_m3':p['weight_mass_kg']/volume,
 'weight_material_note':'Brass exterior. The 2x-mass edit uses a same-envelope high-density filled calibration weight.',
 'crosshead_initial_center_z_m':cross,'pan_hanger_apex_z_m':apex,
 'spring_rendering':'Monotone cubic interpolation through each native massive-turn node; wire section 1.1 mm; fixed topology, 97 native shape keys.',
 'pad_rendering':'Solved flat-punch indentation mode beneath the rigid mass; not a separately solved continuum.'}

OVERLAY=None  # appearance/realism.py hooks its look here, after the lights and compositor
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--case',default='source');ap.add_argument('--frames',type=int,nargs='*');ap.add_argument('--samples',type=int,default=192)
 ap.add_argument('--cpu-preview',action='store_true');ap.add_argument('--save-blend',action='store_true');ap.add_argument('--out',type=Path)
 ap.add_argument('--motion-preview',action='store_true',help='Half-size CPU review clip on a remote worker; never formal media')
 a=ap.parse_args(sys.argv[sys.argv.index('--')+1:]);started=time.time();folder=OUT/'cases'/a.case;p=json.loads((folder/'physics.json').read_text())['physics'];z=np.load(folder/'native_dynamics.npz')
 selected=a.frames if a.frames is not None else list(range(1,97));assert all(1<=x<=96 for x in selected)
 target=a.out or folder
 if a.motion_preview:
  assert a.cpu_preview and a.frames is None and a.samples<=32
 if a.cpu_preview:
  assert (a.motion_preview or len(selected)<=6) and a.out and a.out.is_relative_to(OUT/'appearance_audit')
  assert not os.environ.get('CUDA_VISIBLE_DEVICES');uuid=pci=policy=None;devices=[]
 bpy.ops.wm.read_factory_settings(use_empty=True);sc=bpy.context.scene;sc.render.engine='CYCLES';sc.cycles.samples=a.samples;sc.cycles.use_denoising=True;sc.cycles.use_persistent_data=True
 if a.cpu_preview:sc.cycles.device='CPU';sc.render.threads_mode='FIXED';sc.render.threads=6
 else:uuid,pci,policy,devices=choose_gpu(sc)
 sc.render.resolution_x=1280;sc.render.resolution_y=720;sc.render.resolution_percentage=50 if a.motion_preview else 100;sc.render.fps=24;sc.frame_start=1;sc.frame_end=96
 sc.render.image_settings.file_format='PNG';sc.render.image_settings.color_mode='RGB';sc.render.image_settings.color_depth='8';sc.render.use_motion_blur=False
 sc.view_settings.view_transform='AgX';sc.view_settings.look='AgX - Medium High Contrast';sc.view_settings.exposure=-.65
 sc.world=bpy.data.worlds.new('Photographic university workshop illumination');sc.world.use_nodes=True;n=sc.world.node_tree.nodes;l=sc.world.node_tree.links
 env=n.new('ShaderNodeTexEnvironment');env.image=bpy.data.images.load(str(ASSET_DIR/'university_workshop/university_workshop_4k.hdr'));l.new(env.outputs[0],n['Background'].inputs[0]);n['Background'].inputs['Strength'].default_value=.45
 construction=build(p,z)
 camera=bpy.data.cameras.new('Fixed spring balance review camera');cam=bpy.data.objects.new(camera.name,camera);bpy.context.collection.objects.link(cam)
 cam.location=(.74,-1.82,.94);aim=Vector((.025,0,.50));cam.rotation_euler=(aim-cam.location).to_track_quat('-Z','Y').to_euler();camera.lens=40;camera.sensor_width=36;camera.clip_start=.01;camera.clip_end=20
 camera.dof.use_dof=True;camera.dof.focus_distance=(cam.location-Vector((0,0,.55))).length;camera.dof.aperture_fstop=9.;sc.camera=cam
 area('Large soft laboratory window',(-.7,-.6,1.4),(0,0,.55),85,.70,(1.,.93,.82))
 area('Long reflection card on polished steel',(.65,.15,1.1),(0,0,.6),45,.60,(.80,.90,1.))
 area('Gentle front fill',(.2,-1.0,.85),(0,0,.6),20,.65,(1.,.97,.91))
 target.mkdir(parents=True,exist_ok=True);(target/'rgb').mkdir(exist_ok=True)
 sc.view_layers[0].use_pass_object_index=True;sc.use_nodes=True;n=sc.node_tree.nodes;l=sc.node_tree.links;n.clear();rl=n.new('CompositorNodeRLayers');com=n.new('CompositorNodeComposite');l.new(rl.outputs['Image'],com.inputs[0])
 if not a.motion_preview:
  ids=n.new('CompositorNodeOutputFile');ids.base_path=str(target/'instance_id');ids.file_slots[0].path='index_';ids.format.file_format='OPEN_EXR';ids.format.color_depth='32';ids.format.color_mode='BW';l.new(rl.outputs['IndexOB'],ids.inputs[0])
 if OVERLAY:OVERLAY(sc,cam,p,z,target)
 # Initial matrices are checked across edits after actual remote construction.
 sc.frame_set(1);bpy.context.view_layer.update()
 initial={o.name:[list(row) for row in o.matrix_world] for o in bpy.data.objects if o.type in ['MESH','CURVE','FONT']}
 texture_audit=[{'name':im.name,'packed':bool(im.packed_file),'size':list(im.size),'filepath':im.filepath} for im in bpy.data.images if im.source=='FILE']
 mask_rows=[]
 for frame in selected:
  sc.frame_set(frame);sc.render.filepath=str(target/'rgb'/f'{frame:04d}.png');bpy.ops.render.render(write_still=True)
  if not a.motion_preview:
   mask_path=target/'masks'/f'{frame:04d}.png';counts=integer_mask(target/'instance_id'/f'index_{frame:04d}.exr',mask_path)
   assert (counts.get('1',0)>15 if p.get('spring_present',True) else counts.get('1',0)==0) and counts.get('3',0)>500
   assert counts.get('2',0)>30 if p['weight_present'] else counts.get('2',0)==0
   assert counts.get('4',0)>10 if p['stop_present'] else counts.get('4',0)==0
   mask_rows.append({'frame_index':frame,'time_s':(frame-1)/24,'path':'masks/'+mask_path.name,'sha256':sha(mask_path),'pixel_counts':counts})
  print('RENDERED',a.case,frame,'wall_s',round(time.time()-started,2),flush=True)
 if a.save_blend:
  sc.frame_set(1)
  for im in bpy.data.images:
   if im.source=='FILE' and not im.packed_file:im.pack()
  bpy.ops.wm.save_as_mainfile(filepath=str(target/'animated_scene.blend'),compress=True)
 report={'case':a.case,'revision':'guided_spring_balance','execution_host':socket.gethostname(),'blender_version':bpy.app.version_string,
 'gpu_uuid':uuid,'gpu_pci_bus_id':pci,'gpu_policy':policy,'cycles_devices':devices,'local_blender_used':False,'cpu_preview_only':a.cpu_preview,
 'width':640 if a.motion_preview else 1280,'height':360 if a.motion_preview else 720,'fps':24,'frames':selected,'samples':a.samples,'native_cache_sha256':sha(folder/'native_dynamics.npz'),
 'motion_source':'Native distributed spring and rigid contact dynamics; no authored trajectories.',
 'construction':construction,'texture_audit':texture_audit,'initial_object_matrices':initial,
 'instance_ids':{'background_static':0,'elastic_spring':1,'falling_weight':2,'carriage_and_pan':3,'added_stop':4},
 'camera':{'matrix_world':[list(row) for row in cam.matrix_world],
 'world_to_blender_camera':[list(row) for row in cam.matrix_world.inverted()],
 'intrinsic_K':[[camera.lens/camera.sensor_width*1280,0,640],[0,camera.lens/camera.sensor_width*1280,360],[0,0,1]],'lens_mm':camera.lens,'sensor_width_mm':36},
 'saved_scene_is_animated':bool(a.save_blend),'native_time_endpoint_in_scene_s':4.,'wall_s':time.time()-started,
 'masks':mask_rows,'mask_source':'Raw Cycles IndexOB EXR read as Non-Color; integer gray8 PNG, no view transform.'}
 (target/'render_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 if (not a.cpu_preview or a.motion_preview) and selected==list(range(1,97)):
  ffmpeg='/usr/bin/ffmpeg' if Path('/usr/bin/ffmpeg').exists() else str(DATA/'runtime/ffmpeg/ffmpeg')
  command=[ffmpeg,'-y','-loglevel','error','-framerate','24','-start_number','1','-i',str(target/'rgb/%04d.png'),'-frames:v','96',
   '-c:v','libx264','-preset','medium','-crf','16','-pix_fmt','yuv420p','-movflags','+faststart','-threads','4',str(target/'video.mp4')]
  assert not (target/'video.mp4').exists(),'New production video must not overwrite an existing delivery'
  subprocess.run(command,check=True)
  (target/'encoding_receipt.json').write_text(json.dumps({'command':command,'ffmpeg_version':subprocess.check_output([ffmpeg,'-version'],text=True).splitlines()[0],
   'video_sha256':sha(target/'video.mp4'),'native_cache_sha256':report['native_cache_sha256'],'no_retiming':True,'cpu_motion_preview_only':a.motion_preview,'native_frame_times_s':z['frame_times_s'][:96].tolist()},indent=2),encoding='utf-8')

if __name__=='__main__':main()
