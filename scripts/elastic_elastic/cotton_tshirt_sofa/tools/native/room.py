"""Window, curtain, textile rug and mechanically supported domestic props."""
import bpy,math,random
import numpy as np
from common import DATA,save
from textiles import woven

def weave_uv(obj,tile,plane='XY'):
    vertices=np.array([v.co for v in obj.data.vertices]);ids=np.array([loop.vertex_index for loop in obj.data.loops])
    values=np.stack([vertices[:,0]/tile[0],vertices[:,1 if plane=='XY'else 2]/tile[1]],1)
    uv=obj.data.uv_layers.get('Woven UV')or obj.data.uv_layers.new(name='Woven UV');uv.data.foreach_set('uv',values[ids].astype(np.float32).reshape(-1))

def build(api):
    api['room']()
    cube=api['cube'];cylinder=api['cylinder'];mesh=api['mesh_object'];material=api['material'];area=api['area']
    remove=['Plaster wall','Window deep reveal','Distant overcast sky','Window mullion','Window crossbar','Deep window sill',
        'Lived-in woven rug','Solid oak side table top','Tapered side-table leg','Hardback book','Linen cover',
        'Hand-thrown open mug','Coffee surface','Large window daylight','Soft room bounce','Window grazing detail',
        'Plant pot','Plant stem','Curved leaf']
    for obj in list(bpy.context.scene.objects):
        if any(obj.name.startswith(n)for n in remove)or(obj.type=='MESH'and obj.name.startswith('Torus')and abs(obj.location.x+1.316)<.01):
            bpy.data.objects.remove(obj,do_unlink=True)
        elif obj.name.startswith('Oak floor plank'):obj.location.z+=.003
        elif obj.name=='Plant pot':obj.location.z-=.01
    wood=bpy.data.materials['Photographed oak, Poly Haven wood_table_001'];wall=bpy.data.materials['Warm chalk plaster']
    frame=bpy.data.materials['Window painted timber'];floor=0.
    # A real opening; no luminous sky card or hidden solid wall behind glazing.
    for name,loc,dims in [
        ('Wall left of window',(-3.05,.88,1.65),(.9,.1,3.3)),
        ('Wall right of window',(1.2,.88,1.65),(4.6,.1,3.3)),
        ('Window breast',(-1.85,.88,.37),(1.5,.1,.74)),
        ('Window lintel',(-1.85,.88,2.975),(1.5,.1,.65))]:cube(name,loc,dims,wall,.003)
    for x in [-2.61,-1.85,-1.09]:cube('Real window vertical timber',(x,.73,1.70),(.035,.13,1.95),frame,.003)
    for z in [.73,2.67]:cube('Real window horizontal timber',(-1.85,.73,z),(1.56,.13,.035),frame,.003)
    glass=material('Clear 4 mm window glass',(.98,.99,1),.025);n=glass.node_tree.nodes;l=glass.node_tree.links;bs=n.get('Principled BSDF')
    bs.inputs['Transmission Weight'].default_value=1.;bs.inputs['IOR'].default_value=1.46
    path=n.new('ShaderNodeLightPath');transparent=n.new('ShaderNodeBsdfTransparent');transparent.inputs[0].default_value=(.96,.96,.96,1)
    mix=n.new('ShaderNodeMixShader');l.new(path.outputs['Is Shadow Ray'],mix.inputs[0]);l.new(bs.outputs[0],mix.inputs[1]);l.new(transparent.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],n.get('Material Output').inputs['Surface'])
    cube('Transparent window panes',(-1.85,.75,1.7),(1.48,.004,1.90),glass,.0008)
    cube('Oak window sill',(-1.85,.66,.72),(1.63,.32,.033),wood,.006)
    # Full-width linen obscures the outside; it is lit rather than emissive.
    curtain=material('Backlit warm linen curtain',(.67,.65,.60),.91)
    ramp=woven(curtain,'rough_linen',(.270708,.2713),.27,plane='XZ')
    ramp.color_ramp.elements[0].color=(.51,.49,.44,1);ramp.color_ramp.elements[1].color=(.80,.77,.70,1)
    n=curtain.node_tree.nodes;l=curtain.node_tree.links;bs=n.get('Principled BSDF');trans=n.new('ShaderNodeBsdfTranslucent');trans.inputs[0].default_value=(.72,.70,.65,1)
    mix=n.new('ShaderNodeMixShader');mix.inputs[0].default_value=.35;l.new(bs.outputs[0],mix.inputs[1]);l.new(trans.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],n.get('Material Output').inputs['Surface'])
    v=[];f=[];nx=192;nz=54
    for k in range(nz+1):
        t=k/nz
        for i in range(nx+1):
            u=i/nx;x=-2.68+1.68*u;wave=math.sin(2*math.pi*8*u)+.18*math.sin(2*math.pi*16*u+.4)
            v.append([x,.48+.034*wave*(.82+.18*t),.75+1.96*t+.006*math.sin(2*math.pi*8*u)*(1-t)**2])
    for k in range(nz):
        for i in range(nx):
            a=k*(nx+1)+i;f.append([a,a+1,a+nx+2,a+nx+1])
    o=mesh('Gathered linen curtain',np.asarray(v),np.asarray(f),mat=curtain);weave_uv(o,(.270708,.2713),'XZ');solid=o.modifiers.new('Linen thickness','SOLIDIFY');solid.thickness=.00045
    for t0,t1 in [(0,.007),(.991,1)]:
        vertices=[];faces=[]
        for t in [t0,t1]:
            for i in range(nx+1):
                u=i/nx;wave=math.sin(2*math.pi*8*u)+.18*math.sin(2*math.pi*16*u+.4)
                vertices.append([-2.68+1.68*u,.48+.034*wave*(.82+.18*t)-.0004,.75+1.96*t+.006*math.sin(2*math.pi*8*u)*(1-t)**2])
        for i in range(nx):faces.append([i,i+1,nx+2+i,nx+1+i])
        hem=mesh('Hem sewn along curtain folds',np.asarray(vertices),np.asarray(faces),mat=curtain);weave_uv(hem,(.270708,.2713),'XZ')
    rod=material('Brushed dark curtain rod',(.075,.065,.05),.4);o=cylinder('Curtain rod',(-1.84,.49,2.73),.009,1.84,rod);o.rotation_euler[1]=math.pi/2
    for i in range(9):
        bpy.ops.mesh.primitive_torus_add(major_radius=.013,minor_radius=.002,major_segments=20,minor_segments=6,location=(-2.66+i*.205,.49,2.73),rotation=(0,math.pi/2,0));bpy.context.object.data.materials.append(rod)
    # Closed backing and nonuniform pile height give the rug a real thickness.
    rug=material('Warm greige looped wool rug',(.36,.32,.27),.94);ramp=woven(rug,'wool_boucle',(.3147824,.3901000),.73)
    ramp.color_ramp.elements[0].color=(.20,.175,.135,1);ramp.color_ramp.elements[1].color=(.46,.405,.32,1)
    nx=96;ny=56;v=[];f=[]
    for j in range(ny+1):
        for i in range(nx+1):
            x=-1.315+2.73*i/nx;y=-1.52+1.6*j/ny
            z=.0125+.00055*math.sin(7*x+3*y)*math.sin(6*y-2*x)
            v.append([x,y,z])
    for j in range(ny):
        for i in range(nx):
            a=j*(nx+1)+i;f.append([a,a+1,a+nx+2,a+nx+1])
    boundary=list(range(nx+1))+[j*(nx+1)+nx for j in range(1,ny+1)]+list(range(ny*(nx+1)+nx-1,ny*(nx+1)-1,-1))+[j*(nx+1)for j in range(ny-1,0,-1)]
    bottom=[]
    for a in boundary:bottom.append(len(v));v.append([v[a][0],v[a][1],floor])
    for i,a in enumerate(boundary):b=boundary[(i+1)%len(boundary)];f.append([a,b,bottom[(i+1)%len(bottom)],bottom[i]])
    o=mesh('Wool rug with grounded backing',np.asarray(v),np.asarray(f),mat=rug)
    weave_uv(o,(.3147824,.3901000))
    bevel=o.modifiers.new('Rounded bound edge','BEVEL');bevel.width=.002;bevel.segments=3
    # Sparse actual flyaway fibres supplement the scanned loop normal map.
    rng=random.Random(14823);curve=bpy.data.curves.new('Loose wool fibre geometry','CURVE');curve.dimensions='3D';curve.resolution_u=1;curve.bevel_depth=.000065;curve.bevel_resolution=0
    for _ in range(9000):
        x=rng.uniform(-1.314,1.414);y=rng.uniform(-1.519,.079);angle=rng.uniform(0,math.tau);length=rng.uniform(.001,.003)
        z=.0125+.00055*math.sin(7*x+3*y)*math.sin(6*y-2*x)
        spline=curve.splines.new('POLY');spline.points.add(2)
        for k,p in enumerate(spline.points):t=k/2;p.co=(x+math.cos(angle)*length*t,y+math.sin(angle)*length*t,z+length*.45*math.sin(math.pi*t),1)
    o=bpy.data.objects.new('Wool flyaway fibres',curve);bpy.context.collection.objects.link(o);curve.materials.append(material('Matte wool fibre',(.37,.33,.27),.96))
    # Every leg has a horizontal floor-contact cap and a joined tabletop cap.
    cx=-1.54;cy=-.13;top=.548;cylinder('Grounded oak side table top',(cx,cy,.53),.265,.036,wood)
    for index,angle in enumerate([.1,2.1944,4.2888]):
        b=np.array([cx+.19*math.cos(angle),cy+.19*math.sin(angle),floor]);t=np.array([cx+.13*math.cos(angle),cy+.13*math.sin(angle),.513])
        vertices=[];faces=[]
        for center,radius in [(b,.012),(t,.022)]:
            vertices.extend([list(center+np.array([radius*math.cos(k*math.tau/32),radius*math.sin(k*math.tau/32),0]))for k in range(32)])
        vertices.extend([list(b),list(t)])
        for k in range(32):
            q=(k+1)%32;faces.extend([[k,q,k+32],[q,q+32,k+32],[64,q,k],[65,k+32,q+32]])
        mesh('Floor-contact oak leg '+str(index),np.asarray(vertices),np.asarray(faces),mat=wood)
    cover=bpy.data.materials['Terracotta linen book cloth'];paper=bpy.data.materials['Uncoated book paper']
    cube('Resting book paper block',(-1.59,-.155,.565),(.26,.17,.028),paper,.001)
    for z in [.549,.581]:cube('Resting book linen cover',(-1.59,-.155,z),(.268,.178,.003),cover,.001)
    ceramic=bpy.data.materials['Glazed oatmeal stoneware'];mx=-1.42;my=-.025
    profile=[(.033,0),(.037,.008),(.041,.078),(.041,.084),(.037,.086),(.035,.079),(.032,.012)];v=[];f=[]
    for r,z in profile:
        for k in range(64):v.append([mx+r*math.cos(k*math.tau/64),my+r*math.sin(k*math.tau/64),top+z])
    for j in range(len(profile)-1):
        for k in range(64):a=j*64+k;b=j*64+(k+1)%64;f.append([a,b,b+64,a+64])
    mesh('Grounded open coffee mug',np.asarray(v),np.asarray(f),mat=ceramic)
    bpy.ops.mesh.primitive_torus_add(major_radius=.025,minor_radius=.006,major_segments=48,minor_segments=12,location=(mx+.054,my,top+.04),rotation=(math.pi/2,0,0));bpy.context.object.data.materials.append(ceramic)
    cylinder('Grounded mug coffee',(mx,my,top+.069),.033,.001,bpy.data.materials['Coffee'])
    for mat in bpy.data.materials:
        if mat.name.startswith('Leaf '):
            bs=mat.node_tree.nodes.get('Principled BSDF')
            if bs:bs.inputs['Roughness'].default_value=.83;bs.inputs['Specular IOR Level'].default_value=.13
    area('Curtained daylight',(-1.84,.84,1.8),(.25,-.2,.58),1400,1.45,(1.,.96,.91),1.75)
    area('Weak room bounce',(1.1,-2.6,2.7),(.2,-.05,.62),50,3.,(1.,.94,.85))
    world=bpy.context.scene.world;world.node_tree.nodes['Background'].inputs['Color'].default_value=(.65,.69,.72,1);world.node_tree.nodes['Background'].inputs['Strength'].default_value=.13
    save(DATA/'research/room_support_audit.json',dict(floor_top_z_m=floor,rug_backing_bottom_z_m=floor,table_legs_bottom_z_m=[floor]*3,
        tabletop_top_z_m=top,mug_bottom_z_m=top,book_bottom_z_m=.5475,window='4 mm clear glazing, actual wall opening, gathered nonemissive linen curtain; no exterior scene or emissive sky card',
        changes='Common scene corrections applied identically to source and all five edits'))
