"""Meter-scale home baking workbench; decorations never drive interaction.

The worktop, backsplash tiles, tile joints, back wall and pastry board are built without a material:
realism_look.finish_environment() gives them their only material."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import math
import bpy
import numpy as np
from material_helpers import material,node,link,noise,box,cylinder,wood_material

LAYOUT={}

def bounds(objects):
    arr=np.array([list(o.matrix_world@v.co) for o in objects for v in o.data.vertices])
    return arr.min(0),arr.max(0)

def lathe(name,profile,center,mat):
    verts=[];faces=[];rings=[];N=96
    for r,z in profile:
        count=N if r else 1;rings.append(list(range(len(verts),len(verts)+count)))
        verts.extend((center[0]+r*math.cos(2*math.pi*j/count),center[1]+r*math.sin(2*math.pi*j/count),z) for j in range(count))
    for a,b in zip(rings[:-1],rings[1:]):
        if len(a)==1:faces.extend((a[0],b[j],b[(j+1)%N]) for j in range(N))
        elif len(b)==1:faces.extend((a[j],b[0],a[(j+1)%N]) for j in range(N))
        else:faces.extend((a[j],b[j],b[(j+1)%N],a[(j+1)%N]) for j in range(N))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],[f[::-1] for f in faces]);mesh.update()
    o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);mesh.materials.append(mat)
    for p in mesh.polygons:p.use_smooth=True
    return o

def tube(name,points,radius,mat):
    curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D';curve.resolution_u=12
    curve.bevel_depth=radius;curve.bevel_resolution=5;curve.use_fill_caps=True
    spline=curve.splines.new('POLY');spline.points.add(len(points)-1)
    for point,xyz in zip(spline.points,points):point.co=(*xyz,1)
    o=bpy.data.objects.new(name,curve);bpy.context.collection.objects.link(o);curve.materials.append(mat)
    return o

def rounded_rectangle(width,depth,radius,z,center,n=12):
    points=[]
    for cx,cy,start in [(width/2-radius,depth/2-radius,0),(-width/2+radius,depth/2-radius,90),(-width/2+radius,-depth/2+radius,180),(width/2-radius,-depth/2+radius,270)]:
        for j in range(n):
            a=math.radians(start+j*90/n)
            points.append((center[0]+cx+radius*math.cos(a),center[1]+cy+radius*math.sin(a),z))
    return points

def kitchen_architecture(appearance=None):
    structure=[]
    def part(name,loc,dim,mat,bevel=0,role='kitchen_structure'):
        o=box(name,loc,dim,mat,bevel);o['baking_role']=role;structure.append(o);return o
    # Exact counter/board interface is -24 mm. Cabinet height is independent
    # of the simulation plane, which remains z=0 at the pastry-board top.
    counter=part('36 mm seamless quartz kitchen worktop with true sink opening',(0,.09,-.042),(2.4,.68,.036),None,.0015,'countertop')
    cutter=box('Temporary rounded sink cutout',(-.56,.10,-.06),(.48,.38,.4),None,.030)
    bpy.context.view_layer.objects.active=cutter
    for modifier in list(cutter.modifiers):bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.context.view_layer.objects.active=counter
    mod=counter.modifiers.new('Actual through opening for dry sink','BOOLEAN');mod.operation='DIFFERENCE';mod.object=cutter
    bpy.ops.object.modifier_apply(modifier=mod.name);bpy.data.objects.remove(cutter,do_unlink=True)
    paint,bs=material('Muted sage enamel cabinetry',(.14,.23,.21),.48)
    bs.inputs['Specular IOR Level'].default_value=.31
    dark,_=material('Dark cabinet reveals and toe recess',(.035,.045,.039),.74)
    from realism_look import brushed_metal
    metal=brushed_metal()
    part('Cabinet back panel',(0,.386,-.44),(2.36,.018,.76),dark,.001)
    part('Cabinet bottom shelf',(0,.11,-.80),(2.36,.57,.036),dark,.001)
    for x in (-1.18,0,.6,1.18):
        part('Vertical cabinet partition',(x,.11,-.44),(.018,.57,.74),dark,.001)
    # The under-sink cabinet is hollow; no solid block fills the sink bowl.
    part('Recessed cabinet toe kick',(0,.14,-.86),(2.34,.51,.128),dark,.001)
    # Real panel gaps, four modules, 18 mm fronts and 160 mm metal pulls.
    for k,x in enumerate((-.9,-.3,.3,.9)):
        for j,(z,h) in enumerate(((-.153,.17),(-.423,.36),(-.703,.184))):
            part(f'Cabinet {k+1} drawer {j+1} front',(x,-.190,z),(.595,.018,h),paint,.0012,'cabinet_front')
            for px in (x-.08,x+.08):
                mount=cylinder('Nickel pull standoff',(px,-.210,z+.032),.004,.025,metal,.0006);mount.rotation_euler[0]=math.pi/2
            pull=cylinder('160 mm nickel drawer pull',(x,-.224,z+.032),.004,.176,metal,.001);pull.rotation_euler[1]=math.pi/2
    part('Cabinet finished right end panel',(1.186,.11,-.44),(.018,.59,.76),paint,.001)
    part('Continuous wall behind kitchen',(0,.466,.67),(4,.07,3.2),None)
    part('Backsplash mortar bed',(0,.426,.247),(3.6,.014,.54),None)
    # 150 x 75 mm ceramic tiles in running bond, 2 mm joints.
    for row in range(7):
        for col in range(-13,14):
            x=col*.15+(row%2)*.075
            part('Glazed subway backsplash tile',(x,.415,-.024+.0375+row*.075),(.148,.008,.073),None,.0007,'backsplash_tile')
    part('Silicone counter to tile joint',(0,.411,-.022),(2.4,.004,.004),None,.001)
    floor,_=material('Matte room floor below cabinetry',(.27,.25,.21),.8)
    part('Continuous kitchen floor',(0,0,-.949),(7,7,.05),floor)
    # Dry stainless bowl: connected rounded rim, 3 mm metal wall and drain.
    rings=[(.50,.40,.04,-.023),(.474,.374,.033,-.026),(.444,.344,.035,-.040),(.388,.288,.04,-.173),(.355,.255,.055,-.185)]
    verts=[p for w,d,r,z in rings for p in rounded_rectangle(w,d,r,z,(-.56,.10))];n=48
    faces=[]
    for k in range(len(rings)-1):
        for j in range(n):faces.append((k*n+j,k*n+(j+1)%n,(k+1)*n+(j+1)%n,(k+1)*n+j))
    faces.append(tuple(range((len(rings)-1)*n,len(rings)*n)))
    mesh=bpy.data.meshes.new('Watertight shaped stainless sink');mesh.from_pydata(verts,[],faces);mesh.update()
    sink=bpy.data.objects.new('Empty undermounted stainless kitchen sink',mesh);bpy.context.collection.objects.link(sink);mesh.materials.append(metal)
    for f in mesh.polygons:f.use_smooth=True
    solid=sink.modifiers.new('3 mm stainless shell','SOLIDIFY');solid.thickness=.003
    sink['baking_role']='sink';structure.append(sink)
    drain=cylinder('Sink drain flange',(-.56,.10,-.183),.026,.003,metal,.0006)
    inset,_=material('Unlit drain holes',(.018,.022,.020),.7)
    for j in range(8):
        a=j*math.pi/4;cylinder('Sink drain hole',(-.56+.015*math.cos(a),.10+.015*math.sin(a),-.1812),.0025,.0006,inset,.0001)
    # Faucet meets the counter at a real escutcheon, curves toward the bowl.
    x=-.47;y=.345
    cylinder('Faucet deck escutcheon',(x,y,-.020),.027,.008,metal,.0015)
    cylinder('Mixer body',(x,y,.028),.018,.09,metal,.002)
    points=[(x,y,z) for z in np.linspace(.05,.17,10)]
    points.extend((x,y-.065+.065*math.cos(a),.17+.065*math.sin(a)) for a in np.linspace(0,math.pi,50)[1:])
    points.extend((x,y-.13,z) for z in np.linspace(.17,.145,6)[1:])
    tube('Curved satin nickel kitchen faucet',points,.0105,metal)
    cylinder('Faucet aerator rim',(x,y-.13,.143),.0117,.010,metal,.001)
    cylinder('Recessed faucet aerator',(x,y-.13,.1374),.0087,.0007,inset,.0001)
    lever=cylinder('Single lever mixer handle',(x+.037,y,.072),.004,.065,metal,.001);lever.rotation_euler[1]=math.pi/2
    # A switched socket makes the backsplash a kitchen wall, at actual scale.
    socket,_=material('Off-white electrical faceplate',(.65,.68,.63),.38)
    part('Kitchen wall socket faceplate',(.46,.402,.18),(.086,.009,.086),socket,.002)
    for dx in (-.012,.012):part('Wall socket recessed aperture',(.46+dx,.396,.182),(.004,.001,.014),dark,.0006)
    bpy.context.view_layer.update()
    lo,hi=bounds([counter]);zfloor=-.924
    return {'authorship':'Original meter-scale kitchen geometry; no imported furniture model',
        'countertop':{'name':counter.name,'world_min_m':lo.tolist(),'world_max_m':hi.tolist(),'material':'Original procedural honed quartz with submillimeter aggregate, no tiled pattern','top_z_m':-.024,'thickness_m':.036,'working_height_m':.9,'front_y_m':-.25,'sink_opening_m':[.48,.38]},
        'cabinet':{'front_y_m':-.199,'drawer_pull_length_m':.176,'floor_z_m':zfloor,'real_gaps_m':.005},
        'backsplash':{'tile_m':[.148,.008,.073],'pitch_m':[.15,.075],'grout_m':.002,'front_y_m':.411},
        'sink':{'size_m':[.50,.40,.162],'empty':True,'faucet_connected_to_deck':True},
        'structure_objects':[o.name for o in structure]}

def make_baking_bench(appearance):
    global LAYOUT
    kitchen=kitchen_architecture(appearance)
    board=box('Solid maple pastry board · physical flat support',(0,0,-.012),(.46,.34,.024),None,.003)
    board.name='Worn hardwood pastry board · physical flat support'
    board['baking_role']='physical_support_surface'
    props=[];wood=wood_material((.65,.58,.48),appearance=appearance)
    # A 28 cm rolling pin on the counter behind the board, supported by its barrel.
    pin=cylinder('Wooden rolling pin barrel',(.13,.25,-.006),.018,.20,wood,.003);pin.rotation_euler[1]=math.pi/2;props.append(pin)
    for x in (.01,.25):
        handle=cylinder('Rolling pin handle',(x,.25,-.006),.008,.04,wood,.004);handle.rotation_euler[1]=math.pi/2;props.append(handle)
    ceramic,bs=material('Ivory ceramic flour bowl',(.68,.71,.66),.31)
    profile=[(0,0),(.024,0),(.028,.003),(.039,.014),(.048,.050),(.048,.054),(.045,.056),(.042,.052),(.034,.020),(.023,.008),(0,.008)]
    bowl=lathe('Small flour bowl · solid base and true wall thickness',profile,(-.177,.075),ceramic);props.append(bowl)
    flour,bs=material('Dry wheat flour in bowl',(.80,.76,.64),.94)
    tc=node(flour,'ShaderNodeTexCoord');n=noise(flour,tc.outputs['Object'],2200,2)
    bump=node(flour,'ShaderNodeBump');bump.inputs['Distance'].default_value=.00004;bump.inputs['Strength'].default_value=.2
    link(flour,n.outputs['Fac'],bump.inputs['Height']);link(flour,bump.outputs['Normal'],bs.inputs['Normal'])
    mound=lathe('Dry flour mound filling the bowl',[(0,.008),(.023,.008),(.0335,.02),(.0385,.039),(.034,.046),(.020,.056),(0,.061)],(-.177,.075),flour);props.append(mound)
    from realism_look import brushed_metal
    metal=brushed_metal('Brushed stainless bench scraper')
    blade=box('Bench scraper blade',(.174,.075,.0006),(.073,.088,.0012),metal,.0005);blade.rotation_euler[2]=-.12;props.append(blade)
    handle=cylinder('Bench scraper wooden grip',(.174,.112,.011),.010,.077,wood,.002);handle.rotation_euler[1]=math.pi/2;handle.rotation_euler[2]=-.12;props.append(handle)
    from realism_look import linen as woven_linen
    linen=woven_linen()
    vertices=[];faces=[];nx=25;ny=31
    for j in range(ny):
        y=(j/(ny-1)-.5)*.16
        for i in range(nx):
            x=(i/(nx-1)-.5)*.13
            z=.0015*math.cos(x*95+y*17)+.0008*math.sin(y*120+x*21)+.002*(1-(2*y/.16)**2)
            vertices.append((x,y,z))
    z0=min(v[2] for v in vertices)
    vertices=[(x,y,z-z0+.0011) for x,y,z in vertices]
    for j in range(ny-1):
        for i in range(nx-1):
            a=j*nx+i;faces.append((a,a+1,a+nx+1,a+nx))
    mesh=bpy.data.meshes.new('Folded woven linen with small physical wrinkles');mesh.from_pydata(vertices,[],faces);mesh.update()
    cloth=bpy.data.objects.new('Folded linen towel on stone counter',mesh);bpy.context.collection.objects.link(cloth);cloth.location=(-.16,.27,-.024);cloth.rotation_euler[2]=-.2;mesh.materials.append(linen)
    solidify=cloth.modifiers.new('Linen folded layer thickness','SOLIDIFY');solidify.thickness=.001
    for f in mesh.polygons:f.use_smooth=True
    props.append(cloth)
    bpy.context.view_layer.update()
    descriptions=[]
    for o in props:
        low,high=bounds([o]);descriptions.append({'name':o.name,'world_min_m':low.tolist(),'world_max_m':high.tolist()})
    LAYOUT={'context':'freshly kneaded dough on a pastry board above a fitted kitchen cabinet with stone worktop, dry sink and tiled backsplash',
      'support':{'size_m':[.46,.34,.024],'center_xy_m':[0,0],'top_z_m':0},
      'kitchen':kitchen,'decorative_props':descriptions,
      'flour_policy':'Optical dust on board/dough and static flour in background bowl; no flour particle dynamics or fluid.'}

def receipt():return LAYOUT
