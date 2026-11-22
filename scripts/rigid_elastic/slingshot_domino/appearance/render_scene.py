"""Remote-only Blender scene construction and physical-cache replay."""
import argparse, hashlib, json, math, os, platform, socket, sys, time
from pathlib import Path
if os.name=='nt' or not sys.platform.startswith('linux'):
    raise RuntimeError('Blender rendering runs on a Linux GPU host')
import bpy
import numpy as np
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ribbon_frames import from_cache
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'physics'))
from fork_profile import OUTLINE,MOUNT_BOXES,MOUNT_CYLINDERS,MOUNT_SPHERES,TABLE_EDGE_Y
from realism import polish_scene
OVERLAY=None  # optional hook(out_dir) run after polish_scene; appearance/realism_overlay.py sets it

def mat(name,color,rough=.45,metal=0.):
    m=bpy.data.materials.new(name);m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*color,1.)
    bs.inputs['Roughness'].default_value=rough;bs.inputs['Metallic'].default_value=metal
    return m

def pbr(name,folder,prefix,scale=(1,1,1),leather=False):
    m=mat(name,(.3,.18,.07));nt=m.node_tree;nodes=nt.nodes;bs=nodes.get('Principled BSDF')
    coord=nodes.new('ShaderNodeTexCoord');mapping=nodes.new('ShaderNodeMapping')
    nt.links.new(coord.outputs['UV'if leather else'Generated'],mapping.inputs['Vector']);mapping.inputs['Scale'].default_value=(1,1,1)if leather else scale
    files=list(folder.glob(prefix+'*'))
    for filestr,socketname,normal in [('diff','Base Color',False),('coll1','Base Color',False),('rough','Roughness',False),('nor_gl','Normal',True)]:
        path=next((p for p in files if filestr in p.name),None)
        if not path:continue
        tex=nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(path),check_existing=True)
        tex.projection='FLAT'if leather else'BOX';tex.projection_blend=.16
        if socketname!='Base Color':tex.image.colorspace_settings.name='Non-Color'
        nt.links.new(mapping.outputs['Vector'],tex.inputs['Vector'])
        if normal:
            norm=nodes.new('ShaderNodeNormalMap');norm.inputs['Strength'].default_value=.38 if leather else .27
            nt.links.new(tex.outputs['Color'],norm.inputs['Color']);nt.links.new(norm.outputs['Normal'],bs.inputs['Normal'])
        elif leather and socketname=='Base Color':
            mix=nodes.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=.65;mix.inputs[2].default_value=(.48,.29,.34,1)
            nt.links.new(tex.outputs['Color'],mix.inputs[1]);nt.links.new(mix.outputs[0],bs.inputs[socketname])
        elif socketname=='Roughness':
            rough=nodes.new('ShaderNodeMath');rough.operation='MULTIPLY_ADD';rough.inputs[1].default_value=.6;rough.inputs[2].default_value=.25
            nt.links.new(tex.outputs['Color'],rough.inputs[0]);nt.links.new(rough.outputs[0],bs.inputs[socketname])
        else:nt.links.new(tex.outputs['Color'],bs.inputs[socketname])
    if leather:bs.inputs['Roughness'].default_value=.63
    return m

def finish(o,name,m,bevel=0.):
    o.name=name
    if m:o.data.materials.append(m)
    if bevel:
        b=o.modifiers.new('Submillimetre manufactured edge','BEVEL');b.width=bevel;b.segments=3
        b=o.modifiers.new('Weighted shading','WEIGHTED_NORMAL')
    return o

def box(name,loc,size,m,bevel=0.):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return finish(o,name,m,bevel)

def cylinder(name,loc,radius,depth,m,axis=(0,0,1),vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=loc)
    o=bpy.context.object;o.rotation_mode='QUATERNION';o.rotation_quaternion=Vector((0,0,1)).rotation_difference(Vector(axis))
    finish(o,name,m,.0002)
    for p in o.data.polygons:p.use_smooth=True
    return o

def sphere(name,loc,r,m):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48,ring_count=24,radius=r,location=loc)
    o=finish(bpy.context.object,name,m)
    for p in o.data.polygons:p.use_smooth=True
    return o

def curve(name,points,r,m):
    d=bpy.data.curves.new(name,'CURVE');d.dimensions='3D';d.resolution_u=12;d.bevel_depth=r;d.bevel_resolution=3
    s=d.splines.new('POLY');s.points.add(len(points)-1)
    for p,co in zip(s.points,points):p.co=(*co,1)
    o=bpy.data.objects.new(name,d);bpy.context.collection.objects.link(o)
    if m:d.materials.append(m)
    return o

def text(name,string,loc,size,m,rotation=(0,0,0),align='LEFT'):
    d=bpy.data.curves.new(name,'FONT');d.body=string;d.size=size;d.align_x=align;d.extrude=0
    o=bpy.data.objects.new(name,d);bpy.context.collection.objects.link(o);o.location=loc;o.rotation_euler=rotation
    d.materials.append(m);return o

def yz_extrusion(name,outline,xcenter,depth,m):
    n=len(outline);vs=[(x,y,z)for x in (xcenter-depth/2,xcenter+depth/2)for y,z in outline]
    faces=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n)for i in range(n)]
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vs,[],faces);mesh.update()
    o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);finish(o,name,m,.002)
    return o

def parent(child,par):child.parent=par

def make_domino(name,c,wood,ivory,ink):
    o=box(name,(0,0,0),c['domino_size_m'],wood,.00065)
    # Inlaid pips on both broad x faces; grooves and end grain stay attached.
    for face in (-1,1):
        line=box(name+'_center_score',(face*.00603,0,0),(.00016,.029,.00045),ink,.0001);parent(line,o)
        for yy,zz in [(-.0085,.021),(.0085,.021),(0,.013),(0,-.019)]:
            dot=cylinder(name+'_ebony_inlay',(face*.00610,yy,zz),.0015,.00017,ink,axis=(1,0,0),vertices=24);parent(dot,o)
    return o

def make_pouch(leather,thread):
    # The visible cup and the Bullet plates share a 6 mm parabolic bowl profile.
    verts=[];faces=[];ny=24;nz=8
    for iz in range(nz+1):
        z=-.0065+.013*iz/nz
        for iy in range(ny+1):
            y=-.013+.026*iy/ny;x=.006*max(0.,abs(y)-.006)/.007
            verts.append((x,y,z))
    for iz in range(nz):
        for iy in range(ny):
            k=iz*(ny+1)+iy;faces.append((k,k+1,k+ny+2,k+ny+1))
    mesh=bpy.data.meshes.new('cupped leather');mesh.from_pydata(verts,[],faces);mesh.update()
    uv=mesh.uv_layers.new(name='Metric leather cut')
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            v=mesh.vertices[mesh.loops[li].vertex_index].co
            uv.data[li].uv=((v.y+.013)/.10,(v.z+.0065)/.10)
    o=bpy.data.objects.new('pouch',mesh);bpy.context.collection.objects.link(o);mesh.materials.append(leather)
    solid=o.modifiers.new('1.1mm leather matches collision thickness','SOLIDIFY');solid.thickness=.0011;solid.offset=0
    bevel=o.modifiers.new('Leather cut edge','BEVEL');bevel.width=.0002;bevel.segments=2
    for poly in mesh.polygons:poly.use_smooth=True
    bottom=box('Folded leather lower supporting lip',(.004,0,-.0082),(.008,.024,.0011),leather,.0005);parent(bottom,o)
    for z in (-.0054,.0054):
        for y in np.linspace(-.0115,.0115,14):
            x=.006*max(0.,abs(y)-.006)/.007-.00062
            st=curve('Hand stitched leather edge',[(x,y-.0003,z-.00022),(x-.00003,y,z),(x,y+.0003,z+.00022)],.00010,thread);parent(st,o)
    eyelet=mat('Dull aged brass pouch eyelets',(.26,.17,.07),.42,.78)
    for side in (-1,1):
        bpy.ops.mesh.primitive_torus_add(major_segments=24,minor_segments=8,major_radius=.0007,minor_radius=.00015,location=(.0050,side*.0118,0),rotation=(0,math.pi/2,0))
        parent(finish(bpy.context.object,'Pouch stitched band attachment eyelet',eyelet),o)
    return o

def bandmesh(name,n,m):
    # Four vertices per station form a thin, physically narrowing flat strip.
    vs=[(0,0,0)]*(n*4);fs=[]
    for i in range(n-1):
        for j in range(4):fs.append((i*4+j,i*4+(j+1)%4,(i+1)*4+(j+1)%4,(i+1)*4+j))
    fs += [(3,2,1,0),tuple((n-1)*4+i for i in range(4))]
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vs,[],fs);mesh.update()
    o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);mesh.materials.append(m)
    for poly in mesh.polygons:poly.use_smooth=False
    return o

def update_band(o,center,c):
    l0=c['band_rest_length_m']/(len(center)-1)
    vs=[]
    for i,pnt in enumerate(center):
        tangent=center[min(i+1,len(center)-1)]-center[max(i-1,0)];tangent/=max(np.linalg.norm(tangent),1e-10)
        wide=np.array([0.,0.,1.]);wide-=np.dot(wide,tangent)*tangent
        if np.linalg.norm(wide)<.1:wide=np.array([0,1.,0]);wide-=np.dot(wide,tangent)*tangent
        wide/=np.linalg.norm(wide);normal=np.cross(tangent,wide)
        L=np.linalg.norm(center[min(i+1,len(center)-1)]-center[max(i-1,0)])/(1 if i in (0,len(center)-1)else 2)
        lam=max(L/l0,1.);w=c['band_width_m']/math.sqrt(lam);th=c['band_thickness_m']/math.sqrt(lam)
        for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]:vs.append(pnt+a*w/2*wide+b*th/2*normal)
    o.data.vertices.foreach_set('co',np.array(vs).flatten());o.data.update()

def build(args,c,cache):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    assets=args.assets;wood=pbr('4K open-grain oiled maple',assets/'wood','wood_table_001',(.25,.7,.7))
    leather=pbr('2K worn oxblood leather',assets/'leather','leather_red_02',(.12,.3,.2),True)
    metal=mat('Satin machined steel',(.3,.32,.32),.27,.9)
    black=mat('Dark gunmetal clamp',(.025,.032,.033),.36,.78)
    ink=mat('Black ebony inlay',(.018,.012,.008),.42)
    rubber=mat('Matte natural amber latex',(.64,.36,.12),.57)
    bs=rubber.node_tree.nodes.get('Principled BSDF');bs.inputs['Subsurface Weight'].default_value=.045
    bs.inputs['Subsurface Scale'].default_value=.00035;bs.inputs['Transmission Weight'].default_value=.055;bs.inputs['IOR'].default_value=1.52
    noise=rubber.node_tree.nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=230
    bump=rubber.node_tree.nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.08;bump.inputs['Distance'].default_value=.00004
    rubber.node_tree.links.new(noise.outputs['Fac'],bump.inputs['Height']);rubber.node_tree.links.new(bump.outputs['Normal'],bs.inputs['Normal'])
    blue=mat('Moulded petrol-blue solid polymer',(.032,.19,.235),.36)
    blue.node_tree.nodes.get('Principled BSDF').inputs['Coat Weight'].default_value=.035
    bn=blue.node_tree.nodes.new('ShaderNodeTexNoise');bn.inputs['Scale'].default_value=350
    bump=blue.node_tree.nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.055;bump.inputs['Distance'].default_value=.000012
    blue.node_tree.links.new(bn.outputs['Fac'],bump.inputs['Height']);blue.node_tree.links.new(bump.outputs['Normal'],blue.node_tree.nodes.get('Principled BSDF').inputs['Normal'])
    cream=mat('Bone plastic',(.72,.65,.45),.38)
    paper=mat('Warm uncoated drawing paper',(.78,.76,.67),.91)
    graphite=mat('Graphite pencil',(.12,.14,.15),.85)
    # Actual public-domain table asset, normalized once, common to every edit.
    asset=assets/'wooden_table_02/wooden_table_02_4k.blend'
    with bpy.data.libraries.load(str(asset),link=False) as (src,dst):dst.objects=list(src.objects)
    imported=[]
    for o in dst.objects:
        if o and o.type=='MESH':bpy.context.collection.objects.link(o);imported.append(o)
    for im in bpy.data.images:
        if im.source=='FILE' and not Path(bpy.path.abspath(im.filepath)).exists():
            match=list((assets/'wooden_table_02').rglob(Path(im.filepath).name))
            if match:im.filepath=str(match[0]);im.reload()
    bounds=np.array([tuple(o.matrix_world@Vector(v))for o in imported for v in o.bound_box])
    low=bounds.min(0);high=bounds.max(0);scale=1.1/(high[0]-low[0]);top=high[2]
    for o in imported:
        o.scale*=scale;o.location=Vector(((o.location.x-(low[0]+high[0])/2)*scale+.10,
             (o.location.y-(low[1]+high[1])/2)*scale+.262302501955486,(o.location.z-top)*scale))
        o.name='PolyHaven_table_'+o.name
    # Preserve scanned 4K detail, with a subdued satin finish in neutral daylight.
    table_materials={m for o in imported for m in o.data.materials if m}
    for material in table_materials:
        if not material.use_nodes:continue
        nt=material.node_tree
        for bs in [n for n in nt.nodes if n.type=='BSDF_PRINCIPLED']:
            color=bs.inputs['Base Color']
            if color.is_linked:
                old=color.links[0].from_socket;hs=nt.nodes.new('ShaderNodeHueSaturation');hs.inputs['Saturation'].default_value=.70;hs.inputs['Value'].default_value=.92
                nt.links.new(old,hs.inputs['Color']);nt.links.new(hs.outputs['Color'],color)
            rough=bs.inputs['Roughness']
            if rough.is_linked:
                old=rough.links[0].from_socket;remap=nt.nodes.new('ShaderNodeMapRange');remap.inputs['To Min'].default_value=.42;remap.inputs['To Max'].default_value=.77
                nt.links.new(old,remap.inputs['Value']);nt.links.new(remap.outputs['Result'],rough)
            else:rough.default_value=.56
        for n in nt.nodes:
            if n.type=='NORMAL_MAP':n.inputs['Strength'].default_value=.32
            if n.type=='BUMP':n.inputs['Strength'].default_value=.16
    # A small wooden base near the table edge makes the clamp's load path visible.
    for spec in MOUNT_BOXES:
        box(spec['name'],spec['center'],spec['size'],wood if spec['material']=='wood'else black,spec['bevel'])
    yz=OUTLINE.tolist()
    yz_extrusion('Hand shaped laminated wooden Y frame',yz,0.,.019,wood)
    # Visible lamination lines follow the handle and fork face.
    ply=mat('Thin warm timber lamination',(.24,.15,.075),.64)
    for xx in (-.007,-.003,.003,.007):
        curve('Laminated ply edge',[(xx,-.011,.021),(xx,-.013,.057),(xx,-.024,.081),(xx,-.047,.124)],.00010,ply)
    # Fork tips with screw-on clamps. The anchors are (0,+/-43mm,132mm).
    for side in (-1,1):
        y=side*.043
        pad=box('Fork leather band saddle',(0.,y,.132),(.021,.013,.006),leather,.0008)
        plate=box('Brass fork band clamp',(-.0108,y,.132),(.002,.014,.008),metal,.0004)
        for zz in (.1295,.1345):
            cylinder('Fork clamp slotted screw',(-.0122,y,zz),.0013,.001,metal,axis=(1,0,0),vertices=24)
            slit=box('Screwdriver slot',(-.01275,y,zz),(.00015,.0015,.00025),ink,.00004)
    # Desk clamp grips the mounting foot and the tabletop at its near edge.
    # Rear rail crosses to the table edge, with screw and pressure foot below.
    edge_y=(low[1]-high[1])*scale/2+.262302501955486;spine_y=edge_y-.012;screw_y=edge_y+.027
    assert abs(edge_y-TABLE_EDGE_Y)<1e-6,'Shared mount geometry must agree with actual table edge'
    for spec in MOUNT_CYLINDERS:cylinder(spec['name'],spec['center'],spec['radius'],spec['depth'],metal,axis=spec['axis'])
    for spec in MOUNT_SPHERES:sphere(spec['name'],spec['center'],spec['radius'],metal)
    for zz in np.linspace(-.080,-.035,24):
        bpy.ops.mesh.primitive_torus_add(major_segments=24,minor_segments=6,location=(-.004,screw_y,zz),major_radius=.003,minor_radius=.00032)
        finish(bpy.context.object,'Machined clamp screw thread',metal)
    bpy.context.scene['mount_collision_boxes']=json.dumps(MOUNT_BOXES)
    # Quiet household workshop context, set outside the projectile lane.
    for k,(px,py) in enumerate([(-.160,.160),(-.137,.172),(-.113,.158)]):
        sphere('Spare solid plastic ball '+str(k),(px,py,.0075),.0075,blue if k!=1 else cream)
    note=box('Off-white sketch sheet',(.186,.115,.00045),(.165,.128,.0005),paper,.0001)
    # Drawings are geometry placed on paper, not fake lighting baked into wood.
    for j in range(13):curve('Faint graph paper horizontal',[(.105,.055+j*.01,.00073),(.265,.055+j*.01,.00073)],.000035,mat('Graph blue '+str(j),(.55,.66,.66),1))
    for j in range(17):curve('Faint graph paper vertical',[(.105+j*.01,.055,.00073),(.105+j*.01,.175,.00073)],.000035,paper)
    text('Sketch title','ELASTIC / 01',(.112,.154,.00079),.006,graphite)
    curve('Pencilled sling',[(.125,.083,.0008),(.131,.106,.0008),(.12,.126,.0008),(.124,.108,.0008),(.141,.126,.0008),(.131,.106,.0008)],.00019,graphite)
    curve('Pencilled band',[(.120,.126,.0008),(.109,.112,.0008),(.141,.126,.0008)],.00010,graphite)
    for d in range(15):
        xx=.145+.0045*d;yy=.119-.00020*d*d
        curve('Ballistic pencil dashes',[(xx,yy,.0008),(xx+.002,yy-.001,.0008)],.00010,graphite)
    curve('Domino drawing',[(.218,.076,.0008),(.218,.112,.0008),(.226,.112,.0008),(.226,.076,.0008),(.218,.076,.0008)],.00017,graphite)
    text('Sketch note','m = 1.85 g',(.174,.061,.00079),.0044,graphite)
    # Sharpened hexagonal pencil alongside the sketch, fully seated on tabletop.
    pencil=mat('Ochre pencil lacquer',(.62,.28,.035),.34)
    cylinder('Hexagonal graphite pencil',(.18,.205,.0032),.0032,.16,pencil,axis=(1,0,0),vertices=6)
    bpy.ops.mesh.primitive_cone_add(vertices=6,radius1=.0032,radius2=.0004,depth=.014,location=(.093,.205,.0032))
    o=finish(bpy.context.object,'Pencil sharpened cedar',wood);o.rotation_euler[1]=-math.pi/2
    cylinder('Pencil graphite tip',(.085,.205,.0032),.00045,.003,graphite,axis=(1,0,0))
    # Folded sandpaper and a real-sized small ruler establish a craft tabletop.
    sand=mat('Used fine sandpaper',(.35,.23,.12),.95)
    box('Sandpaper scrap',(-.25,.15,.0006),(.075,.065,.001),sand,.0003)
    ruler=box('Wooden 20cm ruler',(.23,.262,.0015),(.20,.022,.003),mat('Ruler pale beech',(.62,.43,.21),.6),.0005)
    for j in range(41):
        xx=.13+.005*j;length=.008 if j%2==0 else .004
        box('Ruler engraved tick',(xx,.253+length/2,.00305),(.00025,length,.00005),ink)
    for j in range(0,21,2):text('Ruler cm number',str(j),(.129+j*.01,.261,.00310),.0042,ink)
    # Background is a domestic making corner, lit by broad afternoon window light.
    wall=mat('Sage limewash wall',(.29,.37,.32),.94)
    box('Room back wall',(.1,.72,.65),(3.,.08,2.5),wall,.008)
    floor=mat('Warm pale floor',(.30,.25,.19),.82)
    box('Room floor',(.1,0,-.79528585609),(5,5,.04),floor)
    box('Back skirting',(.1,.667,-.68),(3.,.018,.10),wood,.003)
    shelf=box('Back workshop shelf',(.12,.57,.30),(.95,.21,.024),wood,.003)
    for x0 in (-.28,.51):
        box('Shelf upright',(x0,.62,.10),(.025,.035,.43),wood,.002)
    # Soft out-of-focus jars, thread spools and books, with small natural variation.
    jar=mat('Glazed ivory ceramic',(.65,.62,.49),.24)
    cylinder('Brush pot',(-.13,.57,.365),.034,.11,jar)
    for i in range(7):
        xx=-.15+.006*i;obj=cylinder('Wood brush handle',(xx,.57+.012*math.sin(i),.455),.0017,.17,wood)
        obj.rotation_euler[1]=.10*(i-3)
        cylinder('Brush brass ferrule',(xx,.57+.012*math.sin(i),.535),.0025,.025,metal)
    for i,clr in enumerate([(.22,.30,.30),(.43,.21,.10),(.63,.58,.39)]):
        bk=box('Linen sketchbook '+str(i),(.14,.58,.328+.025*i),(.17,.13,.021),mat('Book fabric '+str(i),clr,.8),.002)
    box('Cork inspiration board',(.43,.663,.64),(.44,.025,.35),mat('Natural cork',(.37,.23,.12),.9),.006)
    for i in range(3):
        page=box('Pinned plan '+str(i),(.30+.12*i,.646,.64),(.09,.001,.13),paper,.0005)
        sphere('Brass board pin '+str(i),(.30+.12*i,.644,.696),.0026,metal)
    for o in list(bpy.context.scene.objects):
        if o.name.startswith(('Back workshop shelf','Shelf upright','Brush pot','Wood brush handle',
           'Brush brass ferrule','Linen sketchbook','Cork inspiration board','Pinned plan','Brass board pin')):
            o.location.z-=.22
    # A large window frame lies out of view and produces believable broad highlights.
    def area(name,loc,target,power,size,color):
        d=bpy.data.lights.new(name,'AREA');d.energy=power;d.shape='DISK';d.size=size;d.color=color
        o=bpy.data.objects.new(name,d);bpy.context.collection.objects.link(o);o.location=loc
        o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
    area('Large side window',(-.45,-.22,.85),(.04,.04,0),35,.78,(1.,.96,.90))
    area('Cool soft room bounce',(.5,-.7,.85),(0,0,.06),12,1.1,(.86,.92,1.))
    area('Warm shelf rim',(.45,.48,.9),(0,0,.06),14,.65,(1.,.92,.83))
    world=bpy.data.worlds.new('Interior daylight');world.use_nodes=True;bpy.context.scene.world=world
    nt=world.node_tree;env=nt.nodes.new('ShaderNodeTexEnvironment');env.image=bpy.data.images.load(str(assets/'studio_small_09_1k.hdr'))
    nt.links.new(env.outputs['Color'],nt.nodes.get('Background').inputs['Color']);nt.nodes.get('Background').inputs['Strength'].default_value=.22
    # Dynamic rigid bodies are replayed without per-case offsets or visual motion.
    dynamic={'ball':sphere('ball',(0,0,0),c['ball_radius_m'],blue),'pouch':make_pouch(leather,cream)}
    if not c.get('ball_present',[1])[0]:bpy.data.objects.remove(dynamic.pop('ball'),do_unlink=True)  # DELETE ball
    for key in ('domino','second_domino'):
        if c[key+'_present'][0]:dynamic[key]=make_domino(key,c,wood,cream,ink)
    bands=[bandmesh('Left latex ribbon',cache['bands'].shape[2],rubber),bandmesh('Right latex ribbon',cache['bands'].shape[2],rubber)]
    position=(-.34,-.52,.295)if args.view=='diagonal'else(-.40,-.49,.32)
    bpy.ops.object.camera_add(location=position);cam=bpy.context.object;cam.name='Shared diagonal Y-groove view'
    target=Vector((.005,0.,.063));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.type='PERSP';cam.data.lens=53 if args.view=='diagonal'else 55;cam.data.sensor_width=36;cam.data.dof.use_dof=True
    cam.data.dof.focus_distance=(target-cam.location).length;cam.data.dof.aperture_fstop=13
    scene=bpy.context.scene;scene.camera=cam;scene.render.engine='CYCLES';scene.cycles.samples=args.samples
    scene['fork_profile_m']=json.dumps(yz)
    scene.cycles.use_denoising=True;scene.cycles.adaptive_threshold=.018;scene.cycles.device='GPU'
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    # The published look records a fixed GPU decision instead of calling the allocation policy.
    gpu_decision={'allowed':True,'policy':'realism pass: GPU given by CUDA_VISIBLE_DEVICES'}
    scene['gpu_allocation_policy']=json.dumps(gpu_decision)
    prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='CUDA';prefs.get_devices()
    for d in prefs.devices:d.use=d.type=='CUDA'
    if not any(d.use for d in prefs.devices):raise RuntimeError('Selected remote GPU unavailable to Cycles')
    scene.render.resolution_x=args.width;scene.render.resolution_y=args.height;scene.render.resolution_percentage=100
    scene.render.fps=24;scene.frame_start=1;scene.frame_end=96;scene.render.image_settings.file_format='PNG'
    scene.render.image_settings.color_mode='RGB';scene.render.film_transparent=False
    scene.render.threads_mode='FIXED';scene.render.threads=8
    scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=-.2
    scene.unit_settings.system='METRIC';scene.unit_settings.length_unit='METERS'
    scene.render.use_file_extension=True
    scene['table_bounds_m']=json.dumps({'min':[(low[0]-high[0])*scale/2+.1,(low[1]-high[1])*scale/2+.262302501955486,(low[2]-high[2])*scale],
       'max':[(high[0]-low[0])*scale/2+.1,(high[1]-low[1])*scale/2+.262302501955486,0.]})
    polish_scene(assets)
    if OVERLAY:OVERLAY(args.out)
    return dynamic,bands

def main():
    a=argparse.ArgumentParser();a.add_argument('--assets',type=Path,required=True);a.add_argument('--simulation',type=Path,required=True)
    a.add_argument('--out',type=Path,required=True);a.add_argument('--frames',default='1:96');a.add_argument('--samples',type=int,default=128)
    a.add_argument('--width',type=int,default=1280);a.add_argument('--height',type=int,default=720);a.add_argument('--save-blend',action='store_true')
    a.add_argument('--view',choices=['diagonal','wider'],default='diagonal')
    a.add_argument('--detail',action='store_true',help='120 Hz physical samples; separate 5x slow review clip')
    a.add_argument('--slow',action='store_true',help='Explicit auxiliary 3x slow replay; canonical default is real time')
    args=a.parse_args(sys.argv[sys.argv.index('--')+1:]);args.out.mkdir(parents=True,exist_ok=True)
    c=json.loads((args.simulation/'scene_params.json').read_text());cache_path=args.simulation/'trajectory.npz'
    if not cache_path.is_file():cache_path=args.simulation/'physics_cache.npz'
    cache=np.load(cache_path)
    dynamic,bands=build(args,c,cache);names=list(cache['body_names'])
    prefix='detail_'if args.detail else('slow_'if args.slow else'')
    states=cache[prefix+'states'];bcache=cache[prefix+'bands'];physical_times=cache[prefix+'time_s']
    ribbon=from_cache(cache,c,args.detail,not(args.detail or args.slow))
    if args.detail:
        scene=bpy.context.scene
        tag=mat('Replay annotation',(.9,.95,.92),.8)
        label=text('Explicit detail replay label','DETAIL REPLAY  |  5x SLOW  |  120 Hz physical samples',(0,0,0),.014,tag)
        label.parent=scene.camera;label.location=(-.322,.170,-1.);label.rotation_euler=(0,0,0)
        bs=tag.node_tree.nodes.get('Principled BSDF');bs.inputs['Emission Color'].default_value=(.9,.95,.92,1);bs.inputs['Emission Strength'].default_value=1
        backing=mat('Replay dark caption panel',(.007,.012,.009),.9)
        panel=box('Explicit supplemental replay panel',(0,0,0),(.668,.035,.001),backing)
        panel.parent=scene.camera;panel.location=(0,.176,-1.004);panel.rotation_euler=(0,0,0)
        clock=text('Physical replay time','t = 0.450 s',(0,0,0),.014,tag)
        clock.parent=scene.camera;clock.location=(.220,.170,-1.);clock.rotation_euler=(0,0,0)
        # Keep review annotations sharp at the focal plane and invisible to
        # non-camera rays, so they do not shade or illuminate the experiment.
        depth=scene.camera.data.dof.focus_distance
        for overlay in (label,panel,clock):
            overlay.location*=depth;overlay.scale*=depth
            overlay.visible_shadow=False;overlay.visible_diffuse=False;overlay.visible_glossy=False
            overlay.visible_transmission=False;overlay.visible_volume_scatter=False
    def replay(frame):
        i=frame-1
        for j,name in enumerate(names):
            o=dynamic[str(name)];o.location=states[i,j,:3];o.rotation_mode='QUATERNION';xyzw=states[i,j,3:]
            o.rotation_quaternion=(xyzw[3],xyzw[0],xyzw[1],xyzw[2])
        for j,o in enumerate(bands):
            o.data.vertices.foreach_set('co',ribbon['vertices'][i,j].flatten());o.data.update()
        if args.detail:clock.data.body=f't = {physical_times[i]:.3f} s'
        bpy.context.view_layer.update()
    if ':' in args.frames:
        start,end=map(int,args.frames.split(':'));frames=list(range(start,end+1))
    else:frames=[int(f)for f in args.frames.split(',')]
    bpy.context.scene['physical_time_mapping']='0.45+(frame-1)/120 s'if args.detail else('0.4+(frame-1)/72 s'if args.slow else'(frame-1)/24 s')
    bpy.context.scene['playback_slowdown']=5 if args.detail else(3 if args.slow else 1)
    frame_dir=args.out/'frames';frame_dir.mkdir(exist_ok=True)
    rendered=[];started=time.time()
    for f in frames:
        target=frame_dir/f'frame_{f:04d}.png'
        if target.is_file():continue
        bpy.context.scene.frame_set(f);replay(f);bpy.context.scene.render.filepath=str(target)
        bpy.ops.render.render(write_still=True);rendered.append(f)
        print('FRAME_DONE',f,'elapsed',round(time.time()-started,2),flush=True)
    replay(1)
    if args.save_blend:
        for f in range(1,97):
            replay(f)
            for o in dynamic.values():
                o.keyframe_insert('location',frame=f);o.keyframe_insert('rotation_quaternion',frame=f)
            for o in bands:
                if not o.data.shape_keys:o.shape_key_add(name='Basis')
                key=o.shape_key_add(name=f'Physical frame {f}')
                key.data.foreach_set('co',np.array([v.co[:]for v in o.data.vertices]).flatten())
                key.value=0;key.keyframe_insert('value',frame=f-1)
                key.value=1;key.keyframe_insert('value',frame=f)
                key.value=0;key.keyframe_insert('value',frame=f+1)
        for o in dynamic.values():
            if o.animation_data:
                for fc in o.animation_data.action.fcurves:
                    for key in fc.keyframe_points:key.interpolation='LINEAR'
        bpy.context.scene.frame_set(1);replay(1)
        bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(args.out/'scene.blend'))
    record=dict(worker_host=socket.gethostname(),worker_ip=None,
       gpu_uuid=os.environ.get('CUDA_VISIBLE_DEVICES'),blender_version=bpy.app.version_string,python=platform.python_version(),
       visual_revision='measured-scale plywood, separate timber cuts, paper fibres, metal microstructure and rectangular window',
       unchanged_authoritative_physics_version='accepted',
       ribbon_centerline_error_m=ribbon['maximum_centerline_reconstruction_error_m'],
       ribbon_pouch_axis_error=ribbon['maximum_pouch_axis_alignment_error'],ribbon_orientation_model=ribbon['model'],
       gpu_allocation_policy=json.loads(bpy.context.scene['gpu_allocation_policy']),camera_view=args.view,
       physics_cache_sha256=hashlib.sha256(cache_path.read_bytes()).hexdigest(),
       scene_params_sha256=hashlib.sha256((args.simulation/'scene_params.json').read_bytes()).hexdigest(),
       camera_matrix=[list(row)for row in bpy.context.scene.camera.matrix_world],
       camera_lens_mm=bpy.context.scene.camera.data.lens,resolution=[args.width,args.height],fps=24,frames=frames,
       samples=args.samples,elapsed_s=time.time()-started,rendered_this_run=rendered,
       table_bounds_m=json.loads(bpy.context.scene['table_bounds_m']),
       physical_time_mapping=bpy.context.scene['physical_time_mapping'],
       playback_role='supplemental_detail_5x_slow'if args.detail else('supplemental_3x_slow'if args.slow else'benchmark_real_time'),physical_sample_times_s=physical_times.tolist(),
       playback_slowdown=5 if args.detail else(3 if args.slow else 1),physical_sampling_hz=120 if args.detail else(72 if args.slow else 24),
       native_scene='Source scene.blend contains rigid keyframes and cached band shape keys; trajectory.npz is authoritative')
    (args.out/('render_receipt_'+str(frames[0])+'_'+str(frames[-1])+'.json')).write_text(json.dumps(record,indent=2))
    print('RENDER_COMPLETE',flush=True)

if __name__=='__main__':main()
