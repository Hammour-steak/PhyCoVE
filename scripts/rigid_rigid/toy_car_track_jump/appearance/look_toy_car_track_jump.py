"""Bright activity room: molded orange toy track on plastic risers, light grey plank floor, window daylight."""
import json
import math
from pathlib import Path
import random
import sys
import bpy
from mathutils import Matrix, Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from pcve_assets import asset
from scene_config import track_profile,curve_point

SCENE='scenes/toy_car_track_jump/'
ROOM_X=(-2.4,6.0);ROOM_Y=(-3.9,1.7);ROOM_H=2.7
# Back-wall window in shot; side window in the left wall, out of shot, carries the daylight and the sun.
WINDOW=(-.05,1.2,.95,2.35)
SIDE_WINDOW=(-.9,.7,.95,2.35)
FRONT_WINDOW=(.6,3.4,.8,2.4)
CURTAIN_BACK_OFFSET_M=.165

def material(name,color,rough=.4,metal=0.,coat=0.):
    m=bpy.data.materials.new(name);m.use_nodes=True
    p=m.node_tree.nodes.get('Principled BSDF')
    for key,value in [('Base Color',(*color,1)),('Roughness',rough),('Metallic',metal),('Coat Weight',coat),('Coat Roughness',.2)]:
        p.inputs[key].default_value=value
    return m

def plastic(name,color,rough=.34):
    """Handled toy plastic: mold-worn gloss, faint grime in patches, fine scuffs, dust on upward faces."""
    m=material(name,color,rough);n,l=m.node_tree.nodes,m.node_tree.links;p=n.get('Principled BSDF')
    p.inputs['IOR'].default_value=1.49;p.inputs['Subsurface Weight'].default_value=.06;p.inputs['Subsurface Scale'].default_value=.002
    tc=n.new('ShaderNodeTexCoord')
    def noise(scale,detail=5.,stretch=None):
        node=n.new('ShaderNodeTexNoise');node.inputs['Scale'].default_value=scale;node.inputs['Detail'].default_value=detail
        if stretch:
            mapping=n.new('ShaderNodeMapping');mapping.inputs['Scale'].default_value=stretch;l.new(tc.outputs['Object'],mapping.inputs['Vector']);l.new(mapping.outputs[0],node.inputs['Vector'])
        else:l.new(tc.outputs['Object'],node.inputs['Vector'])
        return node.outputs['Fac']
    def remap(source,lo,hi,to_lo,to_hi):
        node=n.new('ShaderNodeMapRange');node.inputs['From Min'].default_value=lo;node.inputs['From Max'].default_value=hi;node.inputs['To Min'].default_value=to_lo;node.inputs['To Max'].default_value=to_hi;node.clamp=True
        l.new(source,node.inputs['Value']);return node.outputs[0]
    # Grime darkens the color in soft patches; scuffs are streaks stretched along the part.
    grime=remap(noise(16.,6.),.42,.72,0.,.35)
    scuff=remap(noise(70.,4.,(.12,1.,1.)),.62,.74,0.,1.)
    base=n.new('ShaderNodeMixRGB');base.blend_type='MULTIPLY';base.inputs[1].default_value=(*color,1);base.inputs[2].default_value=(.42,.40,.37,1);l.new(grime,base.inputs[0])
    worn=n.new('ShaderNodeMixRGB');worn.blend_type='MIX';l.new(base.outputs[0],worn.inputs[1]);worn.inputs[2].default_value=(min(color[0]*1.25+.05,1),min(color[1]*1.25+.05,1),min(color[2]*1.25+.05,1),1)
    fac=n.new('ShaderNodeMath');fac.operation='MULTIPLY';fac.inputs[1].default_value=.35;l.new(scuff,fac.inputs[0]);l.new(fac.outputs[0],worn.inputs[0])
    # Dust settles only on faces turned up.
    geo=n.new('ShaderNodeNewGeometry');sep=n.new('ShaderNodeSeparateXYZ');l.new(geo.outputs['Normal'],sep.inputs[0])
    up=remap(sep.outputs['Z'],.55,.95,0.,1.);speck=remap(noise(600.,3.),.38,.62,0.,.28)
    dust_fac=n.new('ShaderNodeMath');dust_fac.operation='MULTIPLY';l.new(up,dust_fac.inputs[0]);l.new(speck,dust_fac.inputs[1])
    dusty=n.new('ShaderNodeMixRGB');dusty.blend_type='MIX';l.new(worn.outputs[0],dusty.inputs[1]);dusty.inputs[2].default_value=(.46,.44,.41,1);l.new(dust_fac.outputs[0],dusty.inputs[0])
    l.new(dusty.outputs[0],p.inputs['Base Color'])
    gloss=remap(noise(55.,5.),.3,.7,rough-.06,rough+.1)
    add=n.new('ShaderNodeMath');add.operation='ADD';l.new(gloss,add.inputs[0]);mul=n.new('ShaderNodeMath');mul.operation='MULTIPLY';mul.inputs[1].default_value=.22;l.new(scuff,mul.inputs[0]);l.new(mul.outputs[0],add.inputs[1]);l.new(add.outputs[0],p.inputs['Roughness'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.18;bump.inputs['Distance'].default_value=.00003;l.new(noise(1500.,2.),bump.inputs['Height']);l.new(bump.outputs['Normal'],p.inputs['Normal'])
    return m

def scuffed_floor(m):
    """Sheen on a real floor is uneven: traffic-polished lanes and dull patches show at a low viewing angle."""
    n,l=m.node_tree.nodes,m.node_tree.links;p=n.get('Principled BSDF');tc=n.new('ShaderNodeTexCoord')
    base=p.inputs['Roughness'].links[0].from_socket
    total=base
    for scale,detail,gain in [(1.6,4.,.18),(9.,5.,.10),(70.,3.,.05)]:
        nz=n.new('ShaderNodeTexNoise');nz.inputs['Scale'].default_value=scale;nz.inputs['Detail'].default_value=detail;l.new(tc.outputs['Object'],nz.inputs['Vector'])
        centre=n.new('ShaderNodeMath');centre.operation='SUBTRACT';centre.inputs[1].default_value=.5;l.new(nz.outputs['Fac'],centre.inputs[0])
        amp=n.new('ShaderNodeMath');amp.operation='MULTIPLY';amp.inputs[1].default_value=gain*2;l.new(centre.outputs[0],amp.inputs[0])
        add=n.new('ShaderNodeMath');add.operation='ADD';l.new(total,add.inputs[0]);l.new(amp.outputs[0],add.inputs[1]);total=add.outputs[0]
    l.new(total,p.inputs['Roughness'])
    return m

def pbr(name,directory,repeat_m,plane='XY',normal=.6,roughness=(.4,.7),saturation=1.,value=1.,tint=None,paint=0.):
    directory=Path(directory)
    m=material(name,(.5,.5,.5),.6);n,l=m.node_tree.nodes,m.node_tree.links;bs=n.get('Principled BSDF')
    tc=n.new('ShaderNodeTexCoord');anchor=bpy.data.objects.get('World-space texture anchor') or empty('World-space texture anchor')
    tc.object=anchor;vector=tc.outputs['Object']
    if plane!='XY':
        # First letter feeds texture U, second feeds V.
        sep=n.new('ShaderNodeSeparateXYZ');join=n.new('ShaderNodeCombineXYZ');l.new(vector,sep.inputs[0])
        l.new(sep.outputs[plane[0]],join.inputs['X']);l.new(sep.outputs[plane[1]],join.inputs['Y']);vector=join.outputs[0]
    scale=n.new('ShaderNodeVectorMath');scale.operation='SCALE';scale.inputs[3].default_value=1/repeat_m;l.new(vector,scale.inputs[0])
    images={}
    for channel,tag in [('color','_diff_'),('normal','_nor_gl_'),('rough','_rough_')]:
        im=n.new('ShaderNodeTexImage');im.image=bpy.data.images.load(str(next(directory.glob('*'+tag+'*'))),check_existing=True)
        if channel!='color':im.image.colorspace_settings.name='Non-Color'
        l.new(scale.outputs[0],im.inputs['Vector']);images[channel]=im
    hue=n.new('ShaderNodeHueSaturation');hue.inputs['Saturation'].default_value=saturation;hue.inputs['Value'].default_value=value
    l.new(images['color'].outputs[0],hue.inputs['Color']);color=hue.outputs[0]
    if tint:
        # paint>0 covers the photographed surface with a flat coat, leaving only its tonal variation.
        mix=n.new('ShaderNodeMixRGB');mix.blend_type='MIX' if paint else 'MULTIPLY';mix.inputs[0].default_value=paint or 1.;mix.inputs[2].default_value=(*tint,1)
        l.new(color,mix.inputs[1]);color=mix.outputs[0]
    l.new(color,bs.inputs['Base Color'])
    remap=n.new('ShaderNodeMapRange');remap.inputs['To Min'].default_value=roughness[0];remap.inputs['To Max'].default_value=roughness[1]
    l.new(images['rough'].outputs[0],remap.inputs['Value']);l.new(remap.outputs[0],bs.inputs['Roughness'])
    nor=n.new('ShaderNodeNormalMap');nor.inputs['Strength'].default_value=normal
    l.new(images['normal'].outputs[0],nor.inputs['Color']);l.new(nor.outputs[0],bs.inputs['Normal'])
    return m

def empty(name):
    obj=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(obj)
    return obj

def mesh(name,vertices,faces,mat,bevel=0.,smooth=False):
    data=bpy.data.meshes.new(name);data.from_pydata(vertices,[],faces);data.update()
    obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj)
    if mat:data.materials.append(mat)
    if smooth:
        for poly in data.polygons:poly.use_smooth=True
    if bevel:rounded(obj,bevel)
    return obj

def rounded(obj,width):
    mod=obj.modifiers.new('Molded edge radius','BEVEL');mod.width=width;mod.segments=3;mod.limit_method='ANGLE';mod.angle_limit=math.radians(35)
    obj.modifiers.new('Weighted normals','WEIGHTED_NORMAL')

def box(name,loc,size,mat,bevel=.001,parent=None):
    hx,hy,hz=size[0]/2,size[1]/2,size[2]/2
    v=[(sx*hx,sy*hy,sz*hz) for sx,sy,sz in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
    obj=mesh(name,v,[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],mat,bevel);obj.location=loc
    if parent:obj.parent=parent
    return obj

def cross_cylinder(name,loc,radius,length,mat,parent=None):
    """A short cylinder with its axis across the track (Y)."""
    n=48;v=[(radius*math.cos(i*math.tau/n),s*length/2,radius*math.sin(i*math.tau/n)) for s in (-1,1) for i in range(n)]
    f=[tuple(range(n))[::1],tuple(range(n,2*n))[::-1]]+[(i,(i+1)%n,n+(i+1)%n,n+i) for i in range(n)]
    obj=mesh(name,v,f,mat,bevel=min(radius*.1,.001));obj.location=loc
    for poly in obj.data.polygons:
        if poly.loop_total==4:poly.use_smooth=True
    if parent:obj.parent=parent
    return obj

def look_at(obj,target):
    obj.rotation_euler=(Vector(target)-Vector(obj.location)).to_track_quat('-Z','Y').to_euler()

def profile_height(points,x):
    for (x0,z0),(x1,z1) in zip(points,points[1:]):
        if x0<=x<=x1:return z0+(z1-z0)*(x-x0)/(x1-x0)
    return points[-1][1]

def sweep(name,points,section,mat,bevel=.0002):
    """Extrude a (y,dz) section along the (x,z) lane profile."""
    vertices=[(x,y,z+dz) for x,z in points for y,dz in section]
    n=len(section);faces=[tuple(reversed(range(n)))]
    for j in range(len(points)-1):
        for k in range(n):faces.append((j*n+k,j*n+(k+1)%n,(j+1)*n+(k+1)%n,(j+1)*n+k))
    faces.append(tuple((len(points)-1)*n+k for k in range(n)))
    obj=mesh(name,vertices,faces,mat,bevel=bevel)
    for p in obj.data.polygons:
        if len(p.vertices)==4:p.use_smooth=True
    return obj

def channel_section(tr):
    w=tr['width_m']/2;t=tr['thickness_m'];h=tr['edge_height_m'];e=tr['edge_width_m']
    # Thin U profile: running floor with radiused inner corners, upright rails, rounded rail tops.
    return [(-w-e,-t),(-w-e,h-.0008),(-w-e+.0006,h),(-w-.0006,h),(-w,h-.0008),(-w,.0012),(-w+.0012,0.),
        (w-.0012,0.),(w,.0012),(w,h-.0008),(w+.0006,h),(w+e-.0006,h),(w+e,h-.0008),(w+e,-t)]

def riser(x,tr,points,blue,dark,rubber):
    """A molded tower: wide footed base, tapered ribbed column with through windows, hinged saddle clipping the rails."""
    t=tr['thickness_m'];h=tr['edge_height_m'];W=tr['width_m'];e=tr['edge_width_m'];k=W/.084
    z=lambda u:profile_height(points,u);top=z(x)-t;angle=math.atan2(z(x+.002)-z(x-.002),.004)
    for sx in (-1,1):
        for sy in (-1,1):box('Rubber foot pad',(x+sx*.056*k,sy*.072*k,.0015),(.022*k,.022*k,.003),rubber,.0008)
    box('Riser base plate',(x,0,.003+.0055*k),(.145*k,.178*k,.011*k),blue,.0052)
    box('Base stiffening rib',(x,0,.003+.0135*k),(.11*k,.012*k,.006*k),blue,.0026)
    box('Base stiffening rib',(x,0,.003+.0135*k),(.012*k,.15*k,.006*k),blue,.0026)
    hinge=top-.019*k;base=.003+.011*k;w0,d0,w1,d1=.082*k,.074*k,.048*k,.062*k
    def width(zz):return w0+(w1-w0)*(zz-base)/(hinge-base)
    def depth(zz):return d0+(d1-d0)*(zz-base)/(hinge-base)
    v=[(x+sx*w/2,sy*d/2,zz) for zz,w,d in [(base,w0,d0),(hinge,w1,d1)] for sx,sy in [(-1,-1),(1,-1),(1,1),(-1,1)]]
    column=mesh('Riser tapered column',v,[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],blue)
    # Stacked molded sections: collar every 44 mm, a real window through each panel between collars.
    pitch=.044*k;collars=[base+pitch*(i+1) for i in range(max(0,int((hinge-base-.012)//pitch)))]
    edges=[base]+collars+[hinge]
    for lo,hi in zip(edges,edges[1:]):
        if hi-lo<.028:continue
        mid=(lo+hi)/2;cutter=box('cut',(x,0,mid),(width(mid)*.56,.3,hi-lo-.015),blue,0)
        mod=column.modifiers.new('Window','BOOLEAN');mod.operation='DIFFERENCE';mod.object=cutter;mod.solver='EXACT'
        bpy.context.view_layer.objects.active=column;bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cutter,do_unlink=True)
    rounded(column,.0032)
    for zz in collars:box('Riser section collar',(x,0,zz),(width(zz)+.006,depth(zz)+.006,.0072),blue,.0028)
    cross_cylinder('Riser hinge boss',(x,0,hinge),.0125*k,.072*k,blue)
    for s in (-1,1):cross_cylinder('Hinge pin cap',(x,s*.0365*k,hinge),.0065*k,.0024,dark)
    head=empty('Riser saddle');head.location=(x,0,top);head.rotation_euler.y=-angle
    box('Saddle under the lane',(0,0,-.0035*k),(.078*k,W+2*e+.012,.006*k),blue,.0015,head)
    for s in (-1,1):
        box('Saddle hinge lug',(0,s*.024*k,-.012*k),(.024*k,.012*k,.016*k),blue,.0015,head)
        y=W/2+e+.0035
        box('Snap clip outer wall',(0,s*y,(h+t-.006)/2),(.034*k,.004,h+t+.008),blue,.0009,head)
        box('Snap clip hook',(0,s*(W/2+e/2+.0012),h+t+.0007),(.034*k,.0085,.0018),blue,.0006,head)
    return {'station_x_m':x,'lane_underside_z_m':top,'hinge_z_m':hinge,'collars':len(collars)}

def track(cfg):
    tr=cfg['physics']['track'];pts=track_profile(cfg);W=tr['width_m'];t=tr['thickness_m'];h=tr['edge_height_m'];e=tr['edge_width_m']
    orange=plastic('Orange polypropylene track',(.7,.125,.014),.34)
    blue=plastic('Blue molded risers and connectors',(.03,.145,.44),.3)
    dark=plastic('Dark grey hinge pins',(.05,.055,.06),.42)
    rubber=material('Black rubber feet',(.012,.012,.013),.8)
    grey=plastic('Grey launcher housing',(.26,.28,.30),.4)
    yellow=plastic('Yellow launcher button',(.82,.52,.012),.33)
    section=channel_section(tr)
    arc=[0.]
    for a,b in zip(pts,pts[1:]):arc.append(arc[-1]+math.hypot(b[0]-a[0],b[1]-a[1]))
    def at_arc(s):
        for i in range(len(pts)-1):
            if arc[i]<=s<=arc[i+1]:
                q=(s-arc[i])/(arc[i+1]-arc[i]);return tuple(pts[i][k]+q*(pts[i+1][k]-pts[i][k]) for k in range(2))
        return pts[-1]
    # Stock 305 mm modules, butted with a hairline gap; the solved contact deck is continuous.
    module=.305;gap=.00025;lo=0.;index=0;joins=[]
    while lo<arc[-1]-1e-8:
        hi=min(lo+module,arc[-1]);start=lo+(gap/2 if lo>0 else 0);end=hi-(gap/2 if hi<arc[-1] else 0)
        part=[at_arc(start)]+[p for s,p in zip(arc,pts) if start<s<end]+[at_arc(end)]
        sweep('Orange track module %d'%index,part,section,orange,.00025)
        if hi<arc[-1]:joins.append(at_arc(hi))
        lo=hi;index+=1
    z=lambda x:profile_height(pts,x)
    for i,(x,zz) in enumerate(joins):
        # Blue tongue under the joint with a snap tab showing on each rail, as on real modular track.
        head=empty('Track connector %d'%i);head.location=(x,0,zz);head.rotation_euler.y=-math.atan2(z(x+.002)-z(x-.002),.004)
        box('Connector tongue under the joint',(0,0,-t-.0014),(.075,W-.012,.0028),blue,.0007,head)
        for s in (-1,1):
            box('Connector snap tab on the rail',(0,s*(W/2+e+.0011),(h-t)/2-.0005),(.03,.0022,h+t+.002),blue,.0006,head)
    ledger=[riser(curve_point(cfg,u)[0],tr,pts,blue,dark,rubber) for u in (.56,.93)]
    # A launcher at the track's start explains the first-frame speed; its push ends before frame 1.
    x0=tr['start_x_m'];before=set(bpy.data.objects)
    k=W/.084
    box('Launcher base plate',(x0-.1*k,0,.0045*k),(.215*k,.135*k,.009*k),grey,.004)
    box('Launcher housing',(x0-.122*k,0,.026*k),(.15*k,.112*k,.036*k),grey,.008)
    box('Launcher button',(x0-.15*k,0,.0485*k),(.062*k,.07*k,.012*k),yellow,.004)
    for dx in (-.018,-.006,.006,.018):box('Button grip rib',(x0+(dx-.15)*k,0,.0553*k),(.0026*k,.058*k,.0016*k),yellow,.0005)
    box('Launcher entry throat',(x0-.03*k,0,.0065*k),(.06*k,W+2*e+.01,.007*k),grey,.002)
    box('Launcher striker rod',(x0+.022*k,0,.0115*k),(.09*k,.012*k,.005*k),dark,.001)
    box('Launcher striker head',(x0+.066*k,0,.0135*k),(.007*k,.05*k,.015*k),yellow,.0015)
    return {'construction':'Orange polypropylene U-channel modules with blue snap connectors on three hinged molded risers','commercial_product_replica':False,
      'running_width_m':W,'lip_xyz_m':[pts[-1][0],0,pts[-1][1]],'module_joins_m':joins,'risers':ledger,'launcher_parts':len(set(bpy.data.objects)-before),
      'collision_surface':'same metric profile used by the solver; risers and launcher are static and below the car path'}

def wall(name,fixed,axis,span,height,holes,mat):
    """One wall mesh with true openings; holes are (a,b,bottom,top) along `span`."""
    def v(a,zz):return (a,fixed,zz) if axis=='Y' else (fixed,a,zz)
    vertices=[];faces=[]
    def quad(a0,a1,z0,z1):
        if a1<=a0 or z1<=z0:return
        i=len(vertices);vertices.extend([v(a0,z0),v(a1,z0),v(a1,z1),v(a0,z1)])
        faces.append((i+3,i+2,i+1,i) if span[0]>span[1] else (i,i+1,i+2,i+3))
    lo,hi=sorted(span);cursor=lo
    for a,b,bottom,top in sorted(holes):
        quad(cursor,a,0,height);quad(a,b,0,bottom);quad(a,b,top,height);cursor=b
    quad(cursor,hi,0,height)
    obj=mesh(name,vertices,faces,mat)
    mod=obj.modifiers.new('Plaster thickness','SOLIDIFY');mod.thickness=.14;mod.offset=-1.
    if span[0]>span[1] and holes:obj['opening_repaired']=True
    return obj

def draped_curtains(wa,wb,back_y,mat,tie):
    """Relaxed cloth-simulation panels, held back by a tie, fitted to this window; deepest fold stops at back_y."""
    panels=json.loads((asset('pcve/domino_chain_curtain_drape')/'settled_cloth.json').read_text())['panels']
    width=.46;placed={}
    for panel,name,x0 in [(next(q for q in panels if q['side']==1),'Curtain left',wa-.38),(next(q for q in panels if q['side']==0),'Curtain right',wb-.06)]:
        V=panel['vertices'];lo=min(v[0] for v in V);hi=max(v[0] for v in V);ymax=max(v[1] for v in V);sx=width/(hi-lo)
        verts=[(x0+(v[0]-lo)*sx,back_y+(v[1]-ymax),v[2]) for v in V]
        obj=mesh(name,verts,[tuple(f) for f in panel['faces']],mat,smooth=True)
        obj.modifiers.new('Cloth thickness','SOLIDIFY').thickness=.0012
        waist=[v for v in verts if abs(v[2]-panel['parameters']['tieback_height_m'])<.02]
        cx=(min(v[0] for v in waist)+max(v[0] for v in waist))/2;cy=(min(v[1] for v in waist)+max(v[1] for v in waist))/2
        rx=(max(v[0] for v in waist)-min(v[0] for v in waist))/2+.004;ry=(max(v[1] for v in waist)-min(v[1] for v in waist))/2+.004
        seg=48;zt=panel['parameters']['tieback_height_m'];ring=[(cx+rx*math.cos(k*math.tau/seg),cy+ry*math.sin(k*math.tau/seg),zt+d) for d in (-.024,.024) for k in range(seg)]
        band=mesh(name+' tie',ring,[(k,(k+1)%seg,seg+(k+1)%seg,seg+k) for k in range(seg)],tie,smooth=True);band.modifiers.new('Tie thickness','SOLIDIFY').thickness=.002
        placed[name]=[x0,x0+width]
    return placed

def append(path,names=None):
    with bpy.data.libraries.load(str(path),link=False) as (source,target):
        target.objects=[n for n in source.objects if names is None or n in names]
    loaded=[o for o in target.objects if o is not None]
    for obj in loaded:
        if not obj.users_collection:bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return [o for o in loaded if o.type=='MESH']

def gltf(path):
    before=set(bpy.context.scene.objects);bpy.ops.import_scene.gltf(filepath=str(path));new=set(bpy.context.scene.objects)-before
    # Asset demo animations (door swings) would drive the objects back to their authored poses.
    for obj in new:obj.animation_data_clear()
    bpy.context.view_layer.update()
    return [o for o in new if o.type=='MESH']

def model(name):
    return gltf(sorted(asset(SCENE+f'room/{name}').glob(f'{name}_*k.gltf'))[-1])

def bounds(objects):
    pts=[o.matrix_world@Vector(v) for o in objects for v in o.bound_box]
    return Vector([min(p[i] for p in pts) for i in range(3)]),Vector([max(p[i] for p in pts) for i in range(3)])

def place(objects,xy,z=0.,yaw=0.,scale=1.):
    """Rest a group on height z, centred at xy."""
    low,high=bounds(objects)
    move=Matrix.Translation((xy[0],xy[1],z))@Matrix.Rotation(yaw,4,'Z')@Matrix.Scale(scale,4)@Matrix.Translation((-(low.x+high.x)/2,-(low.y+high.y)/2,-low.z))
    # Move each hierarchy once, from its top object (glTF parts may hang off empties).
    tops=set()
    for obj in objects:
        while obj.parent:obj=obj.parent
        tops.add(obj)
    for obj in tops:obj.matrix_world=move@obj.matrix_world
    bpy.context.view_layer.update()
    low,high=bounds(objects)
    return {'world_bounds_m':[list(low),list(high)]}

def desaturate(mat_name,saturation,value=1.):
    mat=bpy.data.materials[mat_name];shader=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');hue=mat.node_tree.nodes.new('ShaderNodeHueSaturation')
    hue.inputs['Saturation'].default_value=saturation;hue.inputs['Value'].default_value=value
    mat.node_tree.links.new(shader.inputs['Base Color'].links[0].from_socket,hue.inputs['Color']);mat.node_tree.links.new(hue.outputs['Color'],shader.inputs['Base Color'])

BOOKS='polyhaven/book_encyclopedia_set_01/book_encyclopedia_set_01_2k.blend'
COVER_TINTS=[(.05,.09,.16),(.06,.13,.08),(.30,.27,.20),(.12,.12,.13),(.13,.08,.05),(.42,.40,.34)]

def book(number,rng):
    """One book from the bound set, recovered in a muted cloth colour so a shelf is not one matched series."""
    objects=append(asset(BOOKS),['book_encyclopedia_set_01_book%02d'%number]);tint=rng.choice(COVER_TINTS)
    for obj in objects:
        obj.data=obj.data.copy()
        for k,slot in enumerate(obj.data.materials):
            if slot and slot.name.startswith('book_encyclopedia_set_01_cover'):
                mat=slot.copy();n,l=mat.node_tree.nodes,mat.node_tree.links
                bs=next(x for x in n if x.type=='BSDF_PRINCIPLED');source=bs.inputs['Base Color'].links[0].from_socket
                bw=n.new('ShaderNodeRGBToBW');mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1.;mix.inputs[2].default_value=(*tint,1)
                gain=n.new('ShaderNodeMath');gain.operation='MULTIPLY';gain.inputs[1].default_value=3.;l.new(source,bw.inputs[0]);l.new(bw.outputs[0],gain.inputs[0]);l.new(gain.outputs[0],mix.inputs[1])
                l.new(mix.outputs[0],bs.inputs['Base Color']);obj.data.materials[k]=mat
    return objects

def book_row(x0,y,z,numbers,rng,lean=0.):
    """Upright books side by side from x0, spines to the room."""
    x=x0
    for number in numbers:
        objects=book(number,rng);low,high=bounds(objects);w=high.x-low.x
        place(objects,(x+w/2,y),z,rng.uniform(-.02,.02));x+=w+.0008

def wainscot(y,x0,x1,trim,skip):
    """Painted paneling below a rail on the back wall: real moldings catch the side light."""
    rail=.86
    box('Dado rail',((x0+x1)/2,y-.012,rail),(x1-x0,.024,.04),trim,.004)
    x=x0+.06;w=.72
    while x+w<x1:
        if not any(a<x+w and x<b for a,b in skip):
            for name,loc,size in [('top',(x+w/2,y-.006,rail-.1),(w,.012,.024)),('bottom',(x+w/2,y-.006,.2),(w,.012,.024)),
                ('left',(x+.012,y-.006,(rail-.1+.2)/2),(.024,.012,rail-.3)),('right',(x+w-.012,y-.006,(rail-.1+.2)/2),(.024,.012,rail-.3))]:
                box('Panel molding '+name,loc,size,trim,.003)
        x+=w+.06

def window_joinery(y,a,b,bottom,top,trim):
    for xx in [a,(a+b)/2,b]:box('Window upright',(xx,y-.03,(bottom+top)/2),(.05,.09,top-bottom+.05),trim,.002)
    for zz in [bottom,top,(bottom+top)/2+.25]:box('Window rail',((a+b)/2,y-.03,zz),(b-a+.05,.09,.04),trim,.002)
    box('Window sill',((a+b)/2,y-.075,bottom-.035),(b-a+.1,.14,.03),trim,.003)

def rug(extent):
    (x0,x1),(y0,y1)=extent;height=.007
    wool=pbr('Woven wool rug',asset(SCENE+'room/poly_wool_herringbone'),.75,normal=1.,roughness=(.8,1.),saturation=.6,value=1.5,tint=(.82,.78,.68))
    body=box('Rug',((x0+x1)/2,(y0+y1)/2,height/2),(x1-x0,y1-y0,height),wool,.0028)
    # Knotted fringe along both short ends, each strand lying at its own slight angle.
    rng=random.Random(7);strand=material('Rug fringe cotton',(.58,.55,.47),.9);vertices=[];faces=[]
    for x,sign in [(x0,-1),(x1,1)]:
        y=y0+.008
        while y<y1-.004:
            angle=rng.uniform(-.28,.28);length=rng.uniform(.038,.056);w=.0016
            ex,ey=x+sign*length*math.cos(angle),y+length*math.sin(angle);i=len(vertices)
            vertices.extend([(x,y-w,.0035),(x,y+w,.0035),(ex,ey+w,.0012),(ex,ey-w,.0012)]);faces.append((i,i+1,i+2,i+3));y+=rng.uniform(.0085,.012)
    mesh('Rug fringe',vertices,faces,strand)
    return {'world_bounds_m':[[x0-.06,y0,0.],[x1+.06,y1,height]]}

def power_cord(points):
    data=bpy.data.curves.new('Lamp power cord','CURVE');data.dimensions='3D';data.bevel_depth=.0024;data.bevel_resolution=2
    spline=data.splines.new('NURBS');spline.points.add(len(points)-1)
    for dst,src in zip(spline.points,points):dst.co=(*src,1)
    spline.use_endpoint_u=True;spline.order_u=4
    obj=bpy.data.objects.new('Lamp power cord',data);bpy.context.collection.objects.link(obj);obj.data.materials.append(material('Black cord',(.012,.012,.012),.45))
    return obj

def room(cfg):
    a=cfg['appearance']['room'];rng=random.Random(cfg['appearance']['seed'])
    old=asset(SCENE+'room_dressing')
    floor=pbr('Light grey vinyl plank floor',asset('polyhaven/wood_floor'),a['floor_repeat_m'],plane='YX',normal=.5,roughness=tuple(a['floor_roughness']),saturation=.08,value=a['floor_value'],tint=tuple(a['floor_color_linear']),paint=a['floor_coat']);scuffed_floor(floor)
    plaster=asset(SCENE+'room/plastered_wall')
    paint=lambda plane,color,coat:pbr('Painted plaster wall '+plane,plaster,2.3,plane=plane,normal=.26,roughness=(.55,.85),saturation=.3,value=1.,tint=tuple(color),paint=coat)
    wall_mat=lambda plane:paint(plane,a['wall_color_linear'],a['wall_coat'])
    trim=pbr('Eggshell painted woodwork',plaster,1.1,plane='XZ',normal=.18,roughness=(.3,.5),saturation=.2,value=1.,tint=tuple(a['trim_color_linear']),paint=.9)
    x0,x1=ROOM_X;y0,y1=ROOM_Y;h=ROOM_H
    box('Vinyl floor',((x0+x1)/2,(y0+y1)/2,-.05),(x1-x0+.6,y1-y0+.6,.1),floor,0)
    box('Ceiling',((x0+x1)/2,(y0+y1)/2,h+.05),(x1-x0+.6,y1-y0+.6,.1),material('Matte ceiling',(.72,.72,.69),.9),0)
    wall('Back wall',y1,'Y',(x0-.3,x1+.3),h,[WINDOW],wall_mat('XZ'))
    wall('Front wall',y0,'Y',(x1+.3,x0-.3),h,[(x1+x0-FRONT_WINDOW[1],x1+x0-FRONT_WINDOW[0],FRONT_WINDOW[2],FRONT_WINDOW[3])],wall_mat('XZ'))
    wall('Left wall',x0,'X',(y0-.3,y1+.3),h,[SIDE_WINDOW],wall_mat('YZ'))
    wall('Right wall',x1,'X',(y1+.3,y0-.3),h,[],wall_mat('YZ'))
    box('Back skirting',((x0+x1)/2,y1-.012,.065),(x1-x0,.024,.13),trim,.003)
    box('Left skirting',(x0+.012,(y0+y1)/2,.065),(.024,y1-y0,.13),trim,.003)
    wainscot(y1,x0,x1,trim,[])
    wa,wb,wz0,wz1=WINDOW;window_joinery(y1,wa,wb,wz0,wz1,trim)
    sa,sb,sz0,sz1=SIDE_WINDOW
    for yy in [sa,(sa+sb)/2,sb]:box('Side window upright',(x0+.03,yy,(sz0+sz1)/2),(.09,.05,sz1-sz0),trim,.002)
    box('Side window rail',(x0+.03,(sa+sb)/2,(sz0+sz1)/2+.25),(.09,sb-sa,.04),trim,.002)
    linen=pbr('Woven ivory linen curtain',asset('polyhaven/rough_linen'),.32,plane='XZ',normal=.7,roughness=(.78,.98),saturation=.5,value=1.,tint=(.82,.74,.58),paint=.72)
    n,l=linen.node_tree.nodes,linen.node_tree.links;bs=n.get('Principled BSDF');bs.inputs['Sheen Weight'].default_value=.35
    # Cloth lets daylight through: a thin translucent share lights the folds from behind.
    tr_=n.new('ShaderNodeBsdfTranslucent');tr_.inputs['Color'].default_value=(.86,.72,.5,1);mix=n.new('ShaderNodeMixShader');mix.inputs[0].default_value=.14
    l.new(bs.outputs[0],mix.inputs[1]);l.new(tr_.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],n.get('Material Output').inputs[0])
    # Hung clear of the sill: the deepest fold still stops in front of it.
    tie=pbr('Linen curtain tie',asset('polyhaven/rough_linen'),.2,plane='XZ',normal=.7,roughness=(.8,.98),saturation=.5,value=1.,tint=(.58,.52,.41),paint=.72)
    draped_curtains(wa,wb,y1-CURTAIN_BACK_OFFSET_M,linen,tie)
    rail_y=y1-CURTAIN_BACK_OFFSET_M-.05
    box('Curtain rail',((wa+wb)/2,rail_y,2.54),(wb-wa+.95,.024,.024),material('Dark steel rail',(.05,.05,.05),.4,metal=.8),.002)
    socket=material('White socket plate',(.74,.74,.72),.3)
    box('Wall socket',(2.63,y1-.016,.32),(.086,.008,.086),socket,.0015)
    box('Light switch',(-.34,y1-.006,1.12),(.086,.008,.086),socket,.0015)
    props={}
    # Left: cube storage with books and bins behind the track's level run.
    shelf_x=-1.0
    shelf=model('wooden_display_shelves_01');props['storage']=place(shelf,(shelf_x,y1-.22),0.,a['shelf_yaw_rad'])
    for z,dx,numbers in [(.42,-.44,(1,2,3,4,5)),(.8,-.08,(8,9,10,11,12,6)),(1.17,.28,(13,14,15))]:
        book_row(shelf_x+dx,y1-.22,z,numbers,rng)
    # Objects people keep on shelves, so the unit reads as used rather than staged with one series of books.
    for name,dx,z,yaw,scale in [('antique_ceramic_vase_01',-.3,1.175,.3,.75),('standing_picture_frame_01',.0,.425,-.2,1.2),('jug_01',-.33,.805,.5,.7)]:
        item=model(name);place(item,(shelf_x+dx,y1-.22),z,yaw,scale=scale)
    # One bottle of red wine stands in the cell in shot.
    for obj in model('wine_bottles_01'):
        if obj.name=='wine_bottles_01_bordeaux':place([obj],(shelf_x+.4,y1-.2),.805,.6)
        else:bpy.data.objects.remove(obj,do_unlink=True)
    # A woven wool rug behind the track, its near edge well clear of the riser feet.
    props['rug']=rug(a['rug_extent_m'])
    # Right of the window: side table with a lit lamp, sofa with cushions, pictures, plant.
    side_x=2.75;sofa_x=3.81
    side=model('side_table_01');props['side_table']=place(side,(side_x,y1-.25),0.,0.,scale=.9)
    sofa=model('Sofa_01');props['sofa']=place(sofa,(sofa_x,y1-.38),0.,0.,scale=1.)
    pillows=gltf(asset(SCENE+'room_dressing/throw_pillows_01/throw_pillows_01_1k.gltf'));
    # Rest the cushions on the sofa's real surfaces: probe the seat, the back and the arm with rays.
    depsgraph=bpy.context.evaluated_depsgraph_get();probe_x=sofa_x-.42;probe_y=y1-.42
    hit=lambda origin,direction:bpy.context.scene.ray_cast(depsgraph,Vector(origin),Vector(direction))
    seat=hit((probe_x,probe_y,1.5),(0,0,-1))[1].z
    back=hit((probe_x,y1-1.2,seat+.16),(0,1,0))[1].y
    arm=hit((sofa_x,probe_y,seat+.1),(-1,0,0))[1].x
    low,high=bounds(pillows);scale=.6;half=(high.x-low.x)*scale/2;depth=(high.y-low.y)*scale/2
    props['cushions']=place(pillows,(arm+half+.012,back-depth+.012),seat-.012,0.,scale=scale)
    props['sofa_surfaces']={'seat_z_m':seat,'back_y_m':back,'arm_x_m':arm}
    for obj,color in zip(sorted(pillows,key=lambda o:o.name),[(.56,.6,.5),(.74,.68,.56)]):
        cover=pbr('Woven cushion cover',asset('polyhaven/rough_linen'),.2,plane='XZ',normal=1.,roughness=(.78,.98),saturation=.4,value=1.,tint=color,paint=.75)
        for k in range(len(obj.data.materials)):obj.data.materials[k]=cover
    table_top=bounds(side)[1].z
    base=model('ceramic_vase_02');props['lamp_base']=place(base,(side_x,y1-.25),table_top,0.,scale=.72)
    top=bounds(base)[1].z
    shade_mat=pbr('Linen lamp shade',asset('polyhaven/rough_linen'),.14,plane='XZ',normal=.5,roughness=(.8,.98),saturation=.5,value=1.,tint=(.8,.73,.58),paint=.7)
    n,l=shade_mat.node_tree.nodes,shade_mat.node_tree.links
    # The bulb's light passes through the weave, so the color follows the fabric rather than a flat emission.
    em=n.new('ShaderNodeEmission');em.inputs['Color'].default_value=(1.,.74,.46,1);em.inputs['Strength'].default_value=a['lamp_glow']
    color_source=n.get('Principled BSDF').inputs['Base Color'].links[0].from_socket;tint_=n.new('ShaderNodeMixRGB');tint_.blend_type='MULTIPLY';tint_.inputs[0].default_value=1.;tint_.inputs[2].default_value=(1.,.78,.52,1);l.new(color_source,tint_.inputs[1]);l.new(tint_.outputs[0],em.inputs['Color'])
    mix=n.new('ShaderNodeAddShader');l.new(n.get('Principled BSDF').outputs[0],mix.inputs[0]);l.new(em.outputs[0],mix.inputs[1]);l.new(mix.outputs[0],n.get('Material Output').inputs[0])
    seg=64;rb,rt,hh=.17,.115,.2;zb=top-.03
    v=[(side_x+r*math.cos(i*math.tau/seg),y1-.25+r*math.sin(i*math.tau/seg),z_) for r,z_ in [(rb,zb),(rt,zb+hh)] for i in range(seg)]
    shade=mesh('Lamp shade',v,[(i,(i+1)%seg,seg+(i+1)%seg,seg+i) for i in range(seg)],shade_mat,smooth=True);shade.modifiers.new('Shade thickness','SOLIDIFY').thickness=.002;props['lamp_shade']={'world_bounds_m':[list(c) for c in bounds([shade])]}
    power_cord([(side_x+.02,y1-.21,table_top+.02),(side_x-.04,y1-.04,table_top-.02),(side_x-.09,y1-.03,.34),(side_x-.14,y1-.05,.05),(side_x-.15,y1-.09,.006),(2.59,y1-.09,.006),(2.62,y1-.05,.08),(2.63,y1-.024,.27),(2.63,y1-.018,.31)])
    fr=append(asset('polyhaven/hanging_picture_frame_02/hanging_picture_frame_02_2k.blend'));props['picture_a']=place(fr,(3.35,y1-.03),1.12,0.,scale=.95)
    fr=model('fancy_picture_frame_01');props['picture_b']=place(fr,(4.1,y1-.03),1.16,0.,scale=.9)
    return {'room_extent_m':[list(ROOM_X),list(ROOM_Y),ROOM_H],'floor':'light grey vinyl planks','props':props}

def car(cfg):
    library=asset(SCENE+'car_150mm/red_toy_car_library.blend');before=set(bpy.data.objects)
    with bpy.data.libraries.load(str(library),link=False) as (source,target):
        target.objects=list(source.objects)
    for obj in [o for o in bpy.data.objects if o not in before]:
        if not obj.users_collection:bpy.context.collection.objects.link(obj)
    roots={name:bpy.data.objects[name] for name in ['car_body','wheel_0','wheel_1','wheel_2','wheel_3']}
    roots['car_body']['asset_provenance']='Khronos ToyCar — Guido Odendahl and Eric Chadwick, CC0'
    # Smoked glazing: the pale source glass reads as white patches in a bright room.
    glass=bpy.data.materials.get('Glass')
    if glass:
        bs=next(x for x in glass.node_tree.nodes if x.type=='BSDF_PRINCIPLED');bs.inputs['Base Color'].default_value=(.1,.12,.14,1);bs.inputs['Transmission Weight'].default_value=.55;bs.inputs['Roughness'].default_value=.08
    # A wheel can turn a large angle while the shutter is open; sample that sweep instead of its chord.
    def steps(obj,count):
        obj.cycles.motion_steps=count
        for child in obj.children:steps(child,count)
    for name,obj in roots.items():steps(obj,6 if name.startswith('wheel') else 2)
    # The body's red paint remap also catches a patch of the wheel atlas, which flashes as the wheel turns: wheels carry no color.
    # Toy wheel plating is also duller than the car's trim; a mirror rim sparkles from frame to frame as it turns.
    wheel_mats={}
    for i in range(4):
        for part in roots['wheel_%d'%i].children:
            for slot in part.material_slots:
                mat=wheel_mats.get(slot.material.name)
                if mat is None:
                    mat=slot.material.copy();n,l=mat.node_tree.nodes,mat.node_tree.links;bs=next(x for x in n if x.type=='BSDF_PRINCIPLED')
                    floor_=n.new('ShaderNodeMath');floor_.operation='MAXIMUM';floor_.inputs[1].default_value=cfg['appearance']['wheel_min_roughness']
                    l.new(bs.inputs['Roughness'].links[0].from_socket,floor_.inputs[0]);l.new(floor_.outputs[0],bs.inputs['Roughness'])
                    gray=n.new('ShaderNodeRGBToBW');l.new(bs.inputs['Base Color'].links[0].from_socket,gray.inputs[0]);l.new(gray.outputs[0],bs.inputs['Base Color'])
                    wheel_mats[slot.material.name]=mat
                slot.material=mat
    return roots

def lighting(cfg):
    a=cfg['appearance']['lighting']
    world=bpy.data.worlds.new('Garden daylight outside the windows');world.use_nodes=True;bpy.context.scene.world=world
    n,l=world.node_tree.nodes,world.node_tree.links;bg=n.get('Background');bg.inputs['Strength'].default_value=a['environment_strength']
    env=n.new('ShaderNodeTexEnvironment');env.image=bpy.data.images.load(str(asset('polyhaven/sunny_rose_garden/sunny_rose_garden_8k.hdr')),check_existing=True)
    tc=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeMapping');mapping.inputs['Rotation'].default_value[2]=a['environment_rotation_rad']
    l.new(tc.outputs['Generated'],mapping.inputs['Vector']);l.new(mapping.outputs[0],env.inputs['Vector']);l.new(env.outputs[0],bg.inputs['Color'])
    def area(name,loc,target,size,size_y,energy,color,**flags):
        data=bpy.data.lights.new(name,'AREA');data.shape='RECTANGLE';data.size=size;data.size_y=size_y;data.energy=energy;data.color=color
        for key,value in flags.items():setattr(data.cycles,key,value)
        obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj);obj.location=loc;look_at(obj,target);obj.visible_camera=False
        return obj
    wa,wb,wz0,wz1=WINDOW;sa,sb,sz0,sz1=SIDE_WINDOW
    # Daylight enters only through the real openings; portals tell Cycles where to look for it.
    area('Back window sky portal',((wa+wb)/2,ROOM_Y[1]+.16,(wz0+wz1)/2),((wa+wb)/2,0,(wz0+wz1)/2),wb-wa,wz1-wz0,0.,(1,1,1),is_portal=True)
    fa,fb,fz0,fz1=FRONT_WINDOW
    # The room's other window, behind the camera, lights the faces turned toward the lens.
    area('Front window sky portal',(ROOM_X[0]+ROOM_X[1]-(fa+fb)/2,ROOM_Y[0]-.16,(fz0+fz1)/2),(ROOM_X[0]+ROOM_X[1]-(fa+fb)/2,0,(fz0+fz1)/2),fb-fa,fz1-fz0,0.,(1,1,1),is_portal=True)
    area('Side window sky portal',(ROOM_X[0]-.16,(sa+sb)/2,(sz0+sz1)/2),(0,(sa+sb)/2,(sz0+sz1)/2),sb-sa,sz1-sz0,0.,(1,1,1),is_portal=True)
    # Low sun through the side window rakes across the floor under the climb and the flight.
    sun=bpy.data.lights.new('Direct sun through the side window','SUN');sun.energy=a['sun_energy'];sun.angle=math.radians(a['sun_angle_deg']);sun.color=(1,.9,.76)
    obj=bpy.data.objects.new(sun.name,sun);bpy.context.collection.objects.link(obj)
    direction=Vector((-.98,.12,math.tan(math.radians(a['sun_elevation_deg'])))).normalized();obj.location=Vector((0,0,0))+direction*6;look_at(obj,(0,0,0))
    # Faint bounce: what the unseen ceiling and opposite wall return, kept well below the window light.
    area('Weak ceiling bounce',(1.,-.8,ROOM_H-.02),(1.,-.8,0),3.,3.,a['ceiling_bounce_w'],(1.,.96,.9))
    lamp=bpy.data.lights.new('Table lamp bulb','POINT');lamp.energy=a['lamp_w'];lamp.color=(1.,.72,.45);lamp.shadow_soft_size=.03
    shade=bpy.data.objects['Lamp shade'];obj=bpy.data.objects.new(lamp.name,lamp);bpy.context.collection.objects.link(obj)
    low,high=bounds([shade]);obj.location=(low+high)/2
    lens_response(bpy.context.scene,cfg['render'])

def lens_response(scene,render):
    """Faint halation around bright sources and slight color fringing, as a real lens adds to the sensor image."""
    scene.use_nodes=True;scene.render.use_compositing=True;tree=scene.node_tree;tree.nodes.clear()
    layers=tree.nodes.new('CompositorNodeRLayers');glare=tree.nodes.new('CompositorNodeGlare');glare.glare_type='FOG_GLOW';glare.quality='HIGH'
    glare.threshold=render['glare_threshold'];glare.size=render['glare_size'];glare.mix=render['glare_mix']
    fringe=tree.nodes.new('CompositorNodeLensdist');fringe.use_fit=False;fringe.inputs['Distortion'].default_value=0.;fringe.inputs['Dispersion'].default_value=render['lens_dispersion']
    out=tree.nodes.new('CompositorNodeComposite');tree.links.new(layers.outputs['Image'],glare.inputs['Image']);tree.links.new(glare.outputs['Image'],fringe.inputs['Image']);tree.links.new(fringe.outputs['Image'],out.inputs['Image'])
