"""Manufactured metric details shared by all cases; runs inside Blender."""
import bpy,math,random
from scene_paths import ASSETS
from mathutils import Vector
from scene_environment import cube,cylinder,material,micro

def remove(prefixes):
    for ob in list(bpy.context.scene.objects):
        if ob.name.startswith(tuple(prefixes)):bpy.data.objects.remove(ob,do_unlink=True)

def mesh_object(name,verts,faces,mat):
    me=bpy.data.meshes.new(name);me.from_pydata(verts,[],faces);me.update()
    ob=bpy.data.objects.new(name,me);bpy.context.collection.objects.link(ob)
    if mat:me.materials.append(mat)
    return ob

def wire(name,points,radius,mat):
    data=bpy.data.curves.new(name,'CURVE');data.dimensions='3D';data.resolution_u=12
    data.bevel_depth=radius;data.bevel_resolution=3
    sp=data.splines.new('BEZIER');sp.bezier_points.add(len(points)-1)
    for point,co in zip(sp.bezier_points,points):
        point.co=co;point.handle_left_type='AUTO';point.handle_right_type='AUTO'
    ob=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(ob);ob.data.materials.append(mat)
    return ob

def bolt(name,loc,axis,steel,dark,r=.004):
    direction=Vector({'X':(1,0,0),'Y':(0,-1,0),'Z':(0,0,1)}[axis]);q=Vector((0,0,1)).rotation_difference(direction)
    center=Vector(loc);verts=[];faces=[]
    for rad,z in ((r*1.4,-.0005),(r*1.4,.0002),(r,.0002),(r,.002),(r*.43,.002),(r*.43,.0008)):
        for k in range(12):
            angle=k*math.tau/12;v=center+q@Vector((rad*math.cos(angle),rad*math.sin(angle),z));verts.append(tuple(v))
    for a in range(5):
        for k in range(12):j=(k+1)%12;faces.append((a*12+k,a*12+j,(a+1)*12+j,(a+1)*12+k))
    faces.append(tuple(range(60,72)));o=mesh_object(name,verts,faces,steel);o.data.materials.append(dark);o.data.polygons[-1].material_index=1
    bevel=o.modifiers.new('Socket head machined lip','BEVEL');bevel.width=.00015;bevel.segments=2
    o.modifiers.new('Fastener normals','WEIGHTED_NORMAL');return o

def perforated_door(cream,dark,steel):
    remove(('Scanner lower cabinet','Cabinet ventilation slot','Lower service panel seam'))
    # Internal frame is recessed 24 mm behind removable, 1.2 mm sheet doors.
    cube('Scanner recessed inner chassis',(-.78,.012,.40),(1.57,.732,.57),dark,.003)
    cube('Lower cabinet folded top return',(-.78,0,.688),(1.59,.78,.014),cream,.002)
    cube('Lower cabinet folded bottom return',(-.78,0,.112),(1.59,.78,.014),cream,.002)
    for x in (-1.567,.007):cube('Cabinet corner folded return',(x,0,.40),(.016,.78,.578),cream,.002)
    for y in (.387,):cube('Cabinet far service skin',(-.78,y,.40),(1.57,.009,.566),cream,.002)
    for z in (.133,.667):cube('Internal door folded mounting flange',(-.78,-.373,z),(1.545,.050,.008),cream,.001)
    for x in (-1.55,-.752,-.02):cube('Door perimeter folded side flange',(x,-.373,.40),(.003,.050,.53),cream,.0006)
    # The aperture is actual missing geometry, with separately bent louvre blades.
    x0,x1=-1.55,-.755;z0,z1=.13,.671;hx0,hx1=-1.415,-.855;hz0,hz1=.463,.593;y=-.392
    rects=[(x0,x1,z0,hz0),(x0,x1,hz1,z1),(x0,hx0,hz0,hz1),(hx1,x1,hz0,hz1)]
    v=[];f=[]
    for a,b,c,d in rects:
        n=len(v);v.extend([(a,y,c),(b,y,c),(b,y,d),(a,y,d)]);f.append((n,n+1,n+2,n+3))
    panel=mesh_object('Removable steel door with real ventilation aperture',v,f,cream)
    solid=panel.modifiers.new('Pressed sheet gauge 1.2 mm','SOLIDIFY');solid.thickness=.0012
    b=panel.modifiers.new('Hemmed panel edges','BEVEL');b.width=.0007;b.segments=3;panel.modifiers.new('Panel normals','WEIGHTED_NORMAL')
    for k in range(8):
        blade=cube('Pressed ventilation louvre blade',((hx0+hx1)/2,y+.003,hz0+.009+k*.016),(.56,.015,.008),cream,.0008)
        blade.rotation_euler.x=math.radians(-25)
    cube('Separate right hand service door',(-.377,-.392,.4005),(.735,.004,.541),cream,.002)
    for x in (-1.53,-.777,-.727,-.034):
        for z in (.151,.65):bolt('Captive service panel socket screw',(x,-.395,z),'Y',steel,dark,.0035)
    for x in (-1.546,-.031):
        for z in (.235,.565):
            cylinder('Service door hinge knuckle',(x,-.397,z),.0055,.046,steel)
            cylinder('Hinge pin cap',(x,-.397,z+.023),.006,.002,dark)
    for x in (-.80,-.08):
        cylinder('Quarter-turn latch bezel',(x,-.398,.355),.012,.003,steel,'Y')
        cylinder('Recessed latch spindle',(x,-.400,.355),.008,.001,dark,'Y')
        cube('Latch screwdriver recess',(x,-.401,.355),(.012,.001,.002),steel,.0003)
    # One cover is paint, one actual EPDM gasket, instead of a drawn seam.
    for x in (-1.32,-.44):
        cube('Upper enclosure compressed panel gasket',(x,-.3915,.96),(.0028,.003,.278),dark,.0006)
        for z in (.848,1.078):bolt('Upper shell countersunk service screw',(x+.012,-.3905,z),'Y',steel,dark,.0027)
    label=bpy.data.objects.get('X-ray warning label')
    if label:
        label.location.y=-.3995
        cube('Safety label laminated adhesive edge',(-.40,-.3985,.53),(.312,.0015,.098),bpy.data.materials.get('Stop collar yellow'),.001)
    # Visible front shell is separately folded around the tunnel, without intruding.
    cube('Front lower cabinet removable access skin',(.017,0,.40),(.012,.748,.54),cream,.003)
    for yy in (-.352,.352):
        for zz in (.15,.65):bolt('Front access panel fixing',(.024,yy,zz),'X',steel,dark,.003)

def belt_loop(p,rubber,steel,dark):
    remove(('Continuous moving belt',))
    r=p['belt_nose_radius_m'];x0,x1,z=-1.55,p['belt_end_x_m']-r,p['belt_height_m']-r
    path=[(x0,z+r),(x1,z+r)]
    path.extend((x1+r*math.cos(math.pi/2-i*math.pi/32),z+r*math.sin(math.pi/2-i*math.pi/32)) for i in range(1,33))
    path.append((x0,z-r))
    path.extend((x0+r*math.cos(-math.pi/2-i*math.pi/32),z+r*math.sin(-math.pi/2-i*math.pi/32)) for i in range(1,32))
    length=[0.]
    for a,b in zip(path,path[1:]):length.append(length[-1]+math.dist(a,b))
    total=length[-1]+math.dist(path[-1],path[0]);verts=[(x,y,zz) for x,zz in path for y in (-.275,.275)];faces=[]
    for i in range(len(path)):j=(i+1)%len(path);faces.append((2*i,2*j,2*j+1,2*i+1))
    ob=mesh_object('Continuous moving belt',verts,faces,rubber);uv=ob.data.uv_layers.new(name='Metric endless belt coordinates')
    for i,poly in enumerate(ob.data.polygons):
        j=(i+1)%len(path);a=length[i]/total;b=length[j]/total if j else 1.
        for loop,co in zip(poly.loop_indices,((a,0),(b,0),(b,1),(a,1))):uv.data[loop].uv=co
        poly.use_smooth=i not in (0,33)
    solid=ob.modifiers.new('Real 6 mm belt carcass','SOLIDIFY');solid.thickness=.006;solid.offset=-1
    rubber.node_tree.animation_data_clear()
    n=rubber.node_tree.nodes;l=rubber.node_tree.links;n.clear();out=n.new('ShaderNodeOutputMaterial');bs=n.new('ShaderNodeBsdfPrincipled');l.new(bs.outputs[0],out.inputs[0])
    bs.inputs['Base Color'].default_value=(.009,.011,.012,1);bs.inputs['Roughness'].default_value=.78;bs.inputs['Specular IOR Level'].default_value=.25
    tc=n.new('ShaderNodeTexCoord');mp=n.new('ShaderNodeMapping');l.new(tc.outputs['UV'],mp.inputs['Vector'])
    metric=n.new('ShaderNodeVectorMath');metric.operation='MULTIPLY';metric.inputs[1].default_value=(total,.55,1);l.new(mp.outputs['Vector'],metric.inputs[0])
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=1100;noise.inputs['Detail'].default_value=2;l.new(metric.outputs[0],noise.inputs['Vector'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.22;bump.inputs['Distance'].default_value=.000055;l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],bs.inputs['Normal'])
    rough=n.new('ShaderNodeMapRange');rough.inputs['From Min'].default_value=0;rough.inputs['From Max'].default_value=1;rough.inputs['To Min'].default_value=.68;rough.inputs['To Max'].default_value=.85;l.new(noise.outputs['Fac'],rough.inputs['Value']);l.new(rough.outputs[0],bs.inputs['Roughness'])
    for frame in (1,97):
        mp.inputs['Location'].default_value[0]=-p['belt_speed_m_s']*(frame-1)/(24*total);mp.inputs['Location'].keyframe_insert('default_value',frame=frame)
    for fc in rubber.node_tree.animation_data.action.fcurves:
        for key in fc.keyframe_points:key.interpolation='LINEAR'
    for x in (x0,x1):
        cylinder('Terminal belt drum',(x,0,z),r-.006,.542,steel,'Y')
        for yy in (-.316,.316):
            cylinder('Terminal drum bearing cover',(x,yy,z),.025,.024,dark,'Y')
            for dx in (-.025,.025):bolt('Bearing mounting socket screw',(x+dx,yy-.014,z),'Y',steel,dark,.003)
    # Broad, shallow handling abrasion: real roughness variation, never a decal.
    for side in (-1,1):
        cube('Belt side tracking wear strip',((x0+x1)/2,side*.280,p['belt_height_m']-.019),(x1-x0,.006,.017),dark,.001)
    return {'outer_top_z_m':z+r,'solver_belt_plane_z_m':p['belt_height_m'],'loop_length_m':total,'thickness_m':.006}

def tiled_floor():
    old=bpy.data.objects['Granite station floor'];bpy.data.objects.remove(old,do_unlink=True)
    mat=material('Honed granite tile with physical joints',(.2,.21,.20),.36);n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF');tc=n.new('ShaderNodeTexCoord')
    for role,port in (('diff','Base Color'),('rough',None),('nor_gl',None)):
        tex=n.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(ASSETS/'granite_tile'/('granite_tile_'+role+'_4k.jpg')),check_existing=True);l.new(tc.outputs['UV'],tex.inputs['Vector'])
        if role!='diff':tex.image.colorspace_settings.name='Non-Color'
        if port:l.new(tex.outputs['Color'],bs.inputs[port])
        elif role=='rough':
            remap=n.new('ShaderNodeMapRange');remap.inputs['To Min'].default_value=.23;remap.inputs['To Max'].default_value=.49;l.new(tex.outputs['Color'],remap.inputs['Value']);l.new(remap.outputs[0],bs.inputs['Roughness'])
        else:
            normal=n.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.20;l.new(tex.outputs['Color'],normal.inputs['Color']);l.new(normal.outputs['Normal'],bs.inputs['Normal'])
    grout=material('Recessed real epoxy tile grout',(.115,.126,.124),.82)
    vertices=[];faces=[];top_uv=[];mids=[];rng=random.Random(1206)
    def box(cx,cy,cz,sx,sy,sz,material_index,uvs=None):
        a=len(vertices);vertices.extend([(cx+dx*sx/2,cy+dy*sy/2,cz+dz*sz/2) for dx,dy,dz in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))])
        for inds in ((0,3,2,1),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(4,5,6,7)):
            faces.append(tuple(a+i for i in inds));mids.append(material_index if inds==(4,5,6,7) else 1);top_uv.append(uvs if inds==(4,5,6,7) and uvs else [(0,0)]*4)
    box(0,0,-.057,18,18,.10,1)
    for i in range(30):
        for j in range(30):
            u,v=rng.randrange(5),rng.randrange(5);uv=[((u+a)/5,(v+b)/5) for a,b in ((.025,.025),(.975,.025),(.975,.975),(.025,.975))];turn=rng.randrange(4);uv=uv[turn:]+uv[:turn]
            box(-8.7+i*.6,-8.7+j*.6,-.011,.5978,.5978,.012,0,uv)
    ob=mesh_object('Granite station floor',vertices,faces,mat);ob.data.materials.append(grout);uv=ob.data.uv_layers.new(name='Single-granite-tile photo crop')
    for face,mid,coords in zip(ob.data.polygons,mids,top_uv):
        face.material_index=mid
        for k,co in zip(face.loop_indices,coords):uv.data[k].uv=co
    b=ob.modifiers.new('Sub-millimetre stone edge arris','BEVEL');b.width=.00065;b.segments=2;ob.modifiers.new('Stone normals','WEIGHTED_NORMAL')
    return {'tile_pitch_m':.6,'joint_width_m':.0022,'floor_top_z_m':-.005,'separate_solid_tile_count':900,'photo_texture_used_for_stone_grain_only':True}

def fixture_details(steel,dark,cream):
    rubber=material('EPDM hardware gasket',(.009,.012,.013),.82);micro(rubber,1000,.000035,.12)
    for y in (-.303,.303):
        for x in (.20,.66,1.18,1.72,2.23):bolt('Rail end and splice fixing',(x,y-math.copysign(.019,-y),.707),'Y',steel,dark,.0036)
    # Pressed gussets and real weld beads support the polished square tubes.
    for x in (-1.27,-.25,1.15,2.15):
        for y in (-.27,.27):
            yy=y-.025 if y<0 else y+.025
            o=mesh_object('Welded conveyor support gusset',[(x-.075,yy,.667),(x+.075,yy,.667),(x,yy,.573)],[(0,1,2)],steel);s=o.modifiers.new('2.5 mm bracket plate','SOLIDIFY');s.thickness=.0025
            bolt('Support clamp bolt',(x,yy-.002,.62),'Y',steel,dark,.0045)
            points=[(x+.012*math.cos(k*math.tau/16),y+.012*math.sin(k*math.tau/16),.012+k*.0014/16) for k in range(16*20)]
            wire('Levelling stem real helical thread',points,.00055,steel)
    # Gearmotor hangs from a plate tied to both conveyor frame rails.
    cube('Gearmotor mounting bridge',(1.20,0,.688),(.29,.66,.012),steel,.002)
    for y in (-.305,.305):bolt('Motor bridge rail fixing',(1.20,y,.6945),'Z',steel,dark,.004)
    for x in (1.09,1.31):
        cube('Gearmotor outside-return-belt hanger',(x,-.34,.644),(.025,.045,.10),steel,.002)
        cube('Gearmotor lower cradle',(x,-.22,.615),(.025,.29,.008),steel,.001)
    cast=material('Cast aluminium drive housing',(.21,.235,.24),.48,.80);micro(cast,500,.00008,.20)
    cylinder('Conveyor gearmotor body',(1.20,-.10,.546),.065,.24,cast,'X')
    for k in range(12):cylinder('Motor cooling fin',(1.105+k*.017,-.10,.546),.070,.0035,cast,'X')
    cube('Drive reduction gearbox',(1.337,-.10,.564),(.08,.15,.14),cast,.008)
    for yy in (-.155,-.045):
        for zz in (.515,.615):bolt('Gearbox cover bolt',(1.3775,yy,zz),'X',steel,dark,.003)
    # Clamping hardware is fixed at the existing physical upper boundary.
    cube('Curtain retaining backing plate',(-.004,0,1.060),(.012,.534,.031),steel,.002)
    for yy in (-.24,-.16,-.08,0,.08,.16,.24):
        cylinder('Clamp screw elastomer sealing washer',(.039,yy,1.049),.005,.0018,rubber,'X')
        bolt('Curtain clamp socket fixing',(.041,yy,1.049),'X',steel,dark,.0033)
    # Flexible conduits are static, with both endpoints attached to real hardware.
    wire('Monitor power and signal cable',[(-1.13,-.697,1.35),(-1.18,-.66,1.23),(-1.15,-.69,1.09),(-1.151,-.69,.77),(-1.17,-.66,.36),(-1.25,-.41,.29)],.004,rubber)
    for zz in (.38,.65,.96):cube('Cable stand retaining saddle',(-1.15,-.699,zz),(.025,.014,.018),dark,.001)
    cylinder('Cabinet flexible cable gland',(-1.25,-.397,.29),.011,.025,dark,'Y')
    wire('Keyboard coiled lead',[(-1.25,-.72,1.11),(-1.27,-.705,1.085),(-1.17,-.70,1.07),(-1.15,-.69,1.03)],.0025,rubber)
    # The LCD is set behind a bezel lip and a thin anti-reflection cover.
    screen=bpy.data.objects.get('Inspection monitor')
    if screen:
        body=bpy.data.objects['Monitor bezel'];body.location.y=-.693;body.dimensions.y=.018
        screen.location.y=-.714
        glass=material('Monitor anti-reflection cover glass',(.95,.98,.99),.13)
        bs=glass.node_tree.nodes.get('Principled BSDF');bs.inputs['Transmission Weight'].default_value=.98;bs.inputs['IOR'].default_value=1.46
        cube('Monitor cover glass',(-1.13,-.715,1.29),(.437,.0012,.274),glass,.0004)
        cube('LCD panel structural backing',(-1.13,-.710,1.29),(.437,.007,.274),dark,.001)
        for xx in (-1.353,-.907):cube('Monitor raised bezel side',(xx,-.705,1.29),(.014,.032,.295),dark,.002)
        for zz in (1.1485,1.4315):cube('Monitor raised bezel rail',(-1.13,-.705,zz),(.46,.032,.012),dark,.002)
        for k in range(4):cylinder('Monitor tactile lower controls',(-1.04+k*.028,-.723,1.141),.0032,.002,dark,'Y')
    # Small operator-side labels have a real aluminium plate and seated fasteners.
    plate=cube('Scanner equipment identification plate',(-1.03,-.395,.272),(.29,.0015,.073),steel,.001)
    for xx in (-1.161,-.899):bolt('Nameplate rivet',(xx,-.3965,.272),'Y',steel,dark,.0018)
    for k in range(4):cube('Etched equipment data rule',(-1.02,-.397,.255+k*.010),(.205 if k else .18,.0003,.001),dark,0)

def concourse_details(steel,dark):
    # Subtle coating variation, instead of the strong checkerboard wall blocks.
    for name in ('Large ceramic wall panels','Subway porcelain panel warm variation'):
        m=bpy.data.materials.get(name)
        if m:m.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.51,.54,.535,1) if name.startswith('Large') else (.485,.51,.50,1)
    for ob in bpy.context.scene.objects:
        if ob.name.startswith('Individual concourse wall panel'):
            ob.dimensions.y=.023;ob.location.y=5.119
            ob.modifiers['Manufactured edge radius'].width=.0015
    # Glass wings are laminated glass with coloured edges, not opaque cyan blocks.
    glass=bpy.data.materials['Frosted fare gate glass'];bs=glass.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value=(.82,.94,.90,1);bs.inputs['Transmission Weight'].default_value=.96;bs.inputs['Roughness'].default_value=.09;bs.inputs['IOR'].default_value=1.52
    led=material('Gate permission arrow LED',(.025,.42,.12),.28);b=led.node_tree.nodes.get('Principled BSDF');b.inputs['Emission Color'].default_value=(.025,.55,.13,1);b.inputs['Emission Strength'].default_value=.6
    for x in (-.2,.7,1.6):
        for y in (3.08,3.92):
            cube('Fare gate top service seam',(x,y,1.049),(.30,.0015,.0016),dark,.0003)
            for xx in (x-.125,x+.125):bolt('Fare gate cover socket screw',(xx,y,1.049),'Z',steel,dark,.0028)
        cube('Fare gate infrared sensor bezel',(x,2.997,.68),(.13,.006,.042),dark,.004)
        for dx in (-.04,.04):cylinder('Infrared receiver lens',(x+dx,2.992,.68),.010,.003,glass,'Y')
        cube('Fare gate reader glass',(x,3.34,1.075),(.091,.092,.003),dark,.003)
        mesh_object('Reader illuminated directional arrow',[(x-.022,3.335,1.077),(x+.022,3.335,1.077),(x,3.365,1.077)],[(0,1,2)],led)
    for ob in list(bpy.context.scene.objects):
        if ob.name.startswith('Glass wing metal hinge'):
            x,y,z=ob.location
            for zz in (z-.20,z+.20):
                cube('Laminated wing bolted clamp',(x,y-.016,zz),(.045,.022,.045),steel,.003)
                bolt('Wing hinge compression bolt',(x,y-.028,zz),'Y',steel,dark,.003)
    # Hollow aluminium sign rims and their mounting studs cast actual shadows.
    for name,face in (('Station sign backing','Station bilingual sign'),('Train direction sign backing','Metro train direction sign')):
        backing=bpy.data.objects.get(name);graphic=bpy.data.objects.get(face)
        if not backing or not graphic:continue
        cx,cy,cz=backing.location;w,h=backing.dimensions.x,backing.dimensions.z
        for sign in (-1,1):
            cube('Wayfinding aluminium side extrusion',(cx+sign*(w/2-.004),cy-.008,cz),(.009,.024,h),steel,.0015)
            cube('Wayfinding aluminium horizontal extrusion',(cx,cy-.008,cz+sign*(h/2-.004)),(w,.024,.009),steel,.0015)
        for dx in (-w*.40,w*.40):cylinder('Wall sign captive standoff',(cx+dx,cy+.010,cz),.012,.034,steel,'Y')
        # Actual printed sign face has dielectric ink, no added emission.
        for m in graphic.data.materials:
            if m and m.use_nodes:m.node_tree.nodes.get('Principled BSDF').inputs['Emission Strength'].default_value=0
    # Tile edges and raised ribs on tactile paving remain actual geometry.
    for ob in bpy.context.scene.objects:
        if ob.name.startswith('Tactile paving tile'):
            for y in (ob.location.y-.135,ob.location.y+.135):
                cube('Tactile tile border groove',(ob.location.x,y,-.004),(.276,.0012,.001),dark,.0002)

def refine(p):
    mats=bpy.data.materials;steel=mats['Brushed satin stainless steel'];dark=mats['Dark graphite coated steel'];cream=mats['Warm grey fine powder-coat'];rubber=mats['Conveyor continuous rubber top cover']
    cream.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value=0
    cream.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.40
    for mat,low,high in ((cream,.35,.45),(steel,.24,.33),(dark,.35,.46)):
        n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF');tc=n.new('ShaderNodeTexCoord');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=7.0;noise.inputs['Detail'].default_value=3
        l.new(tc.outputs['Object'],noise.inputs['Vector']);r=n.new('ShaderNodeMapRange');r.inputs['To Min'].default_value=low;r.inputs['To Max'].default_value=high;l.new(noise.outputs['Fac'],r.inputs['Value']);l.new(r.outputs[0],bs.inputs['Roughness'])
    perforated_door(cream,dark,steel);belt=belt_loop(p,rubber,steel,dark);floor=tiled_floor();fixture_details(steel,dark,cream);concourse_details(steel,dark)
    from monitor_upgrade import upgrade
    upgrade()
    from concourse_return import build as build_return
    architecture=build_return()
    from outfeed import build as build_outfeed
    outfeed=build_outfeed(p)
    from station_details import build as build_station
    architecture.update(build_station(p))
    # Direct sources belong to real ceiling fixtures; restrained fill reveals depth.
    for name,power in (('Broad station fill',70),('Exit material edge',100),('Concourse side illumination',125),('Ceiling over scanner',245),('Back concourse light',180),('Gate concourse overhead',200)):
        ob=bpy.data.objects.get(name)
        if ob:ob.data.energy=power
    bpy.context.scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.055
    bpy.context.view_layer.update()
    assert abs(belt['outer_top_z_m']-p['belt_height_m'])<1e-10
    return {'revision':'metro_extended_outfeed','belt':belt,'outfeed':outfeed,'floor':floor,'architecture':architecture,'physics_parameters_changed':True,'actor_initial_transforms_changed':False,'camera_shared_with_earlier_layout':False,
        'earlier_detail_additions':['hollow louvred removable sheet door','socket recesses and washers','wrapped belt and end drums','motor cooling fins and gearbox (superseded by compact outlet)','900 individually bevelled 600 mm stone tiles','LCD bezel and cover glass','clamped laminated gate wings','sign extrusions and mounting studs','supported cable runs'],
        'new_outfeed_geometry':['extended wrapped belt and terminal drums','fixed feathered transfer lip','deeper sloping stainless sheet and folded cheeks','lower level pickup deck','pickup rubber end stop','structural rails and ten levelling feet'],
        'static_object_count':len([o for o in bpy.context.scene.objects if o.type in ('MESH','CURVE','FONT')])}

def refine_bag_materials(bags):
    """Keep the original scan/UVs; distinguish woven fabric from warm leather."""
    seen=set()
    for root in bags:
        for ob in root.children:
            if ob.type!='MESH':continue
            for mat in ob.data.materials:
                if not mat or mat.name in seen or not mat.use_nodes:continue
                seen.add(mat.name);n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF')
                if not bs or not bs.inputs['Base Color'].is_linked:continue
                color=bs.inputs['Base Color'].links[0].from_socket
                sep=n.new('ShaderNodeSeparateColor');l.new(color,sep.inputs[0]);warm=n.new('ShaderNodeMath');warm.operation='SUBTRACT';l.new(sep.outputs['Red'],warm.inputs[0]);l.new(sep.outputs['Blue'],warm.inputs[1])
                mask=n.new('ShaderNodeMapRange');mask.inputs['From Min'].default_value=.025;mask.inputs['From Max'].default_value=.15;mask.clamp=True;l.new(warm.outputs[0],mask.inputs['Value'])
                rough=n.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.78;rough.inputs['To Max'].default_value=.38;l.new(mask.outputs[0],rough.inputs['Value']);l.new(rough.outputs[0],bs.inputs['Roughness'])
                bs.inputs['Sheen Weight'].default_value=.18;bs.inputs['Sheen Roughness'].default_value=.65
