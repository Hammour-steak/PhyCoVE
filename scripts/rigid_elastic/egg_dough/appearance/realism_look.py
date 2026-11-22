"""Photographic look of the egg-and-dough kitchen: shaders, room and daylight.

Applied after baking_look.make_baking_bench():
 - meter-scale baking-bench shaders: pinned CC0 Poly Haven wood PBR and authored procedural wear and cloth;
 - the kitchen is a closed room (walls, ceiling, wall cabinets) lit only by daylight from an overcast CC0
   sky HDRI through a modelled side window (Cycles portal); no studio HDRI and no hidden area lights;
 - worktop, backsplash, walls, pastry board, bowl flour and towel use scanned CC0 maps (Poly Haven
   macro_flour, beige_wall_001, rough_linen, white_maple_veneer; ambientCG SurfaceImperfections018);
 - dough and eggshell shaders: every dough field is evaluated in the FEM rest coordinates
   (rest_position_m), every eggshell field in the rigid egg's object coordinates, so detail moves with
   the deformation and the rigid pose and never swims.
Interaction meshes are never displaced: the FEM boundary and the rigid mesh render exactly as cached.
The module reads the look dictionary and applies the shared kitchen appearance.
"""

import math
import sys as _pcve_assets_sys
import sys as _scene_sys
from pathlib import Path as _ScenePath, Path, Path as _PcveAssetsPath

import bpy
from material_helpers import material, node, link, math_node as M, vector_math as V, map_range as R, noise, image, combine, box
from realism_look_assets import files
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))


def mix(m,a,b,factor,mode='MIX'):
    n=node(m,'ShaderNodeMixRGB');n.blend_type=mode
    for socket,value in zip(n.inputs,(factor,a,b)):
        if isinstance(value,(tuple,list,int,float)):socket.default_value=value
        else:link(m,value,socket)
    return n.outputs[0]


def coordinates(m):
    return node(m,'ShaderNodeTexCoord').outputs['Object']


def split(m,co):
    n=node(m,'ShaderNodeSeparateXYZ');link(m,co,n.inputs[0]);return n.outputs


def bump(m,h,distance,strength,normal=None):
    n=node(m,'ShaderNodeBump');n.inputs['Distance'].default_value=distance;n.inputs['Strength'].default_value=strength
    link(m,h,n.inputs['Height'])
    if normal is not None:link(m,normal,n.inputs['Normal'])
    return n.outputs['Normal']


def wood(multiplier=(.39,.31,.24)):
    m,bs=material('Sanded solid cherry · 1 m photographed PBR grain · satin pores',(.30,.18,.09),.48)
    bs.inputs['Specular IOR Level'].default_value=.32;bs.inputs['Coat Weight'].default_value=0
    co=coordinates(m);rot=node(m,'ShaderNodeVectorRotate');rot.rotation_type='EULER_XYZ';rot.inputs['Rotation'].default_value=(.25,.48,-.32);link(m,co,rot.inputs['Vector']);co=rot.outputs[0];s=split(m,co)
    long=V(m,'MULTIPLY',co,(1,1,.10));warp=noise(m,long,175,3)
    across=M(m,'ADD',s['X'],M(m,'MULTIPLY',s['Y'],.23))
    across=M(m,'ADD',across,M(m,'MULTIPLY',warp.outputs['Fac'],.0013))
    uv=combine(m,M(m,'ADD',s['Z'],.414),M(m,'ADD',across,.582))
    diff=image(m,Path('cherry_veneer/cherry_veneer_diff_4k.jpg'),uv)
    rad=V(m,'LENGTH',combine(m,M(m,'ADD',s['X'],.048),M(m,'ADD',s['Y'],.020),0))
    annual=M(m,'SINE',M(m,'ADD',M(m,'MULTIPLY',rad,2*math.pi/.0026),M(m,'MULTIPLY',warp.outputs['Fac'],7.0)))
    fibers=R(m,annual,.965,1.02,(-.5,.9))
    base=mix(m,diff,(*multiplier,1),1,'MULTIPLY')
    link(m,mix(m,base,fibers,1,'MULTIPLY'),bs.inputs['Base Color'])
    rough=image(m,Path('cherry_veneer/cherry_veneer_rough_4k.jpg'),uv,linear=True)
    link(m,R(m,rough,.37,.59),bs.inputs['Roughness'])
    n=bump(m,rough,.000035,.30)
    pores=noise(m,V(m,'MULTIPLY',co,(1,1,.055)),4100,2)
    link(m,bump(m,pores.outputs['Fac'],.000013,.29,n),bs.inputs['Normal'])
    m['grain_map_size_m']=1.;return m


def brushed_metal(name='Brushed satin nickel fittings',color=(.50,.55,.54)):
    m,bs=material(name,color,.30);bs.inputs['Metallic'].default_value=1
    co=coordinates(m);streak=noise(m,V(m,'MULTIPLY',co,(.025,1,1)),6800,2)
    link(m,R(m,streak.outputs['Fac'],.23,.38),bs.inputs['Roughness'])
    link(m,bump(m,streak.outputs['Fac'],.000004,.18),bs.inputs['Normal'])
    bs.inputs['Anisotropic'].default_value=.38
    return m


def linen():
    m,bs=material('Folded unbleached linen · yarn weave and narrow kitchen stripes',(.26,.30,.25),.86)
    bs.inputs['Sheen Weight'].default_value=.32;bs.inputs['Sheen Roughness'].default_value=.72
    co=coordinates(m);s=split(m,co)
    warp=M(m,'SINE',M(m,'MULTIPLY',s['X'],2*math.pi/.00062));weft=M(m,'SINE',M(m,'MULTIPLY',s['Y'],2*math.pi/.0007))
    yarn=M(m,'MULTIPLY',warp,weft);n=noise(m,co,1100,2)
    band=M(m,'SINE',M(m,'MULTIPLY',s['X'],2*math.pi/.032))
    stripe=R(m,band,0,.8,(.82,.98))
    color=mix(m,(.32,.35,.29,1),(.055,.095,.085,1),stripe)
    link(m,mix(m,color,R(m,n.outputs['Fac'],.82,1.05),1,'MULTIPLY'),bs.inputs['Base Color'])
    link(m,bump(m,yarn,.00013,.5),bs.inputs['Normal']);return m


SCENE_DIR=Path(__file__).resolve().parents[1]


FILES=files(SCENE_DIR)


FLOUR=FILES['polyhaven/macro_flour/macro_flour_diff_2k.jpg'].parent


PLASTER=FILES['polyhaven/beige_wall_001/beige_wall_001_diff_4k.jpg'].parent


LINEN=FILES['polyhaven/rough_linen/rough_linen_diff_2k.jpg'].parent


SKY=FILES['polyhaven/residential_garden/residential_garden_4k.hdr']


IMPERFECTIONS=FILES['ambientcg/SurfaceImperfections018/SurfaceImperfections018_SQ_Roughness.jpg']


MAPLE=FILES[f'scenes/{SCENE_DIR.name}/look_assets/white_maple_veneer/white_maple_veneer_diff_4k.jpg'].parent


RECEIPT={}


def img(m,path,co,linear=False,box_blend=None):
    assert Path(path) in FILES.values(),path  # only maps listed in realism_look_assets
    n=node(m,'ShaderNodeTexImage');n.image=bpy.data.images.load(str(path),check_existing=True)
    if linear:n.image.colorspace_settings.name='Non-Color'
    n.interpolation='Linear';n.extension='REPEAT'
    if box_blend is not None:n.projection='BOX';n.projection_blend=box_blend
    link(m,co,n.inputs['Vector']);return n.outputs['Color']


def gray(m,color):
    n=node(m,'ShaderNodeRGBToBW');link(m,color,n.inputs[0]);return n.outputs[0]


def scaled(m,co,span,offset=(0,0,0)):
    return V(m,'ADD',V(m,'MULTIPLY',co,(1/span,1/span,1/span)),tuple(offset))


def flour_color(m,diff):
    # The scan is photographed slightly warm; plain white wheat flour on site reads whiter.
    n=node(m,'ShaderNodeHueSaturation');n.inputs['Saturation'].default_value=.75;n.inputs['Value'].default_value=1.12
    link(m,diff,n.inputs['Color']);return n.outputs['Color']


def flour_layer(m,co,density,amount=1.):
    """Scanned flour (Poly Haven macro_flour, 0.30 m span): colour, grain height and coverage.
    `density` 0..1 decides where flour lies; the scanned height map breaks the edge into grains."""
    fco=scaled(m,co,.30,(.13,.61,.29))
    diff=flour_color(m,img(m,FLOUR/'macro_flour_diff_2k.jpg',fco,box_blend=.3))
    height=gray(m,img(m,FLOUR/'macro_flour_disp_2k.jpg',fco,linear=True,box_blend=.3))
    cover=R(m,M(m,'ADD',density,M(m,'MULTIPLY',M(m,'SUBTRACT',height,.38),1.5)),0,1,(.42,.70))
    cover=M(m,'MULTIPLY',cover,amount)
    return diff,height,cover


# --------------------------------------------------------------------------------------------
# Surfaces
# --------------------------------------------------------------------------------------------
def worktop(look):
    t=look.get('worktop',{})
    m,bs=material('Honed light grey engineered quartz · satin finish, aggregate flecks, scanned wear',tuple(t.get('color',(.56,.56,.535))),.32)
    bs.inputs['Specular IOR Level'].default_value=.5
    co=coordinates(m)
    # Aggregate: sparse 1-2 mm grey grains and lighter quartz chips, plus faint cloudiness.
    broad=noise(m,co,3.5,3,.55);fleck=noise(m,co,620,2,.45);fleck2=noise(m,co,260,3,.55);fine=noise(m,co,2300,2,.45)
    base=mix(m,(*t.get('color',(.56,.56,.535)),1),R(m,broad.outputs['Fac'],.95,1.04,(.3,.7)),1,'MULTIPLY')
    base=mix(m,base,(.33,.33,.32,1),R(m,fleck.outputs['Fac'],0,t.get('fleck_strength',.45),(.68,.75)))
    base=mix(m,base,(.70,.70,.68,1),R(m,fleck2.outputs['Fac'],0,.35,(.30,.24)))
    base=mix(m,base,R(m,fine.outputs['Fac'],.96,1.03,(.35,.65)),1,'MULTIPLY')
    link(m,base,bs.inputs['Base Color'])
    wear=img(m,IMPERFECTIONS,scaled(m,co,.40,(.17,.43,0)),linear=True,box_blend=.2)
    link(m,R(m,gray(m,wear),t.get('roughness_min',.24),t.get('roughness_max',.46),(.34,.47)),bs.inputs['Roughness'])
    n=bump(m,fleck.outputs['Fac'],.000008,.18)
    link(m,bump(m,gray(m,wear),.00001,.12,n),bs.inputs['Normal'])
    return m


def glazed_tile():
    m,bs=material('Glazed white subway tile · per-tile tint, slight set-in tilt and glaze ripple',(.78,.77,.72),.08)
    bs.inputs['Coat Weight'].default_value=.35;bs.inputs['Coat Roughness'].default_value=.05;bs.inputs['Specular IOR Level'].default_value=.5
    ob=node(m,'ShaderNodeObjectInfo');r1=ob.outputs['Random']
    r2=M(m,'FRACT',M(m,'MULTIPLY',r1,7.31));r3=M(m,'FRACT',M(m,'MULTIPLY',r1,13.7))
    link(m,mix(m,(.75,.745,.70,1),(.82,.81,.77,1),r1),bs.inputs['Base Color'])
    co=coordinates(m);s=split(m,co);ripple=noise(m,co,55,3,.5)
    link(m,R(m,ripple.outputs['Fac'],.05,.12),bs.inputs['Roughness'])
    # Each 150 x 75 mm tile is set slightly out of plane (up to ~0.6 degrees), as real tiling is.
    tilt=M(m,'ADD',M(m,'MULTIPLY',s['X'],M(m,'MULTIPLY',M(m,'SUBTRACT',r2,.5),.02)),M(m,'MULTIPLY',s['Z'],M(m,'MULTIPLY',M(m,'SUBTRACT',r3,.5),.02)))
    n=bump(m,tilt,1.,1.)
    link(m,bump(m,ripple.outputs['Fac'],.00025,.25,n),bs.inputs['Normal'])
    return m


def grout():
    m,bs=material('Light grey cement tile grout',(.50,.49,.45),.92)
    co=coordinates(m);n=noise(m,co,2500,2)
    link(m,bump(m,n.outputs['Fac'],.00004,.4),bs.inputs['Normal']);return m


def plaster(name,color,rough=(.82,.92)):
    m,bs=material(name,color,.88)
    co=coordinates(m);uv=scaled(m,co,3.,(.31,.17,.53))
    d=img(m,PLASTER/'beige_wall_001_diff_4k.jpg',uv,linear=True,box_blend=.2)
    r=img(m,PLASTER/'beige_wall_001_rough_4k.jpg',uv,linear=True,box_blend=.2)
    link(m,mix(m,(*color,1),R(m,gray(m,d),.94,1.05,(.535,.556)),1,'MULTIPLY'),bs.inputs['Base Color'])
    link(m,R(m,gray(m,r),rough[0],rough[1],(.59,.66)),bs.inputs['Roughness'])
    link(m,bump(m,gray(m,r),.00012,.35),bs.inputs['Normal']);return m


def pastry_board(look):
    t=look.get('board',{})
    m,bs=material('Maple pastry board · scanned CC0 maple, scanned flour dusting',(.66,.53,.35),.58)
    bs.inputs['Specular IOR Level'].default_value=.35
    co=coordinates(m);s=split(m,co)
    # Edge-glued board: staves 38-58 mm wide run along the long x axis; each stave shows its own
    # part of the 1 m maple scan and a slightly different tone, with a fine glue line between staves.
    yw=M(m,'ADD',s['Y'],M(m,'MULTIPLY',M(m,'SINE',M(m,'MULTIPLY',s['Y'],17.)),.011))
    q=M(m,'DIVIDE',M(m,'ADD',yw,.30),t.get('stave_width_m',.048))
    stave=M(m,'FLOOR',q)
    rnd=M(m,'FRACT',M(m,'MULTIPLY',M(m,'SINE',M(m,'MULTIPLY',stave,12.9898)),43758.5453))
    uv=V(m,'ADD',co,(.21,.37,.11))
    shift=node(m,'ShaderNodeCombineXYZ');link(m,M(m,'MULTIPLY',rnd,.53),shift.inputs[0]);link(m,M(m,'MULTIPLY',rnd,.29),shift.inputs[1])
    uv=V(m,'ADD',uv,shift.outputs[0])
    diff=img(m,MAPLE/'white_maple_veneer_diff_4k.jpg',uv,box_blend=.25)
    rough=img(m,MAPLE/'white_maple_veneer_rough_4k.jpg',uv,linear=True,box_blend=.25)
    contrast=node(m,'ShaderNodeBrightContrast');contrast.inputs['Contrast'].default_value=t.get('grain_contrast',.35);link(m,diff,contrast.inputs['Color'])
    wood=mix(m,contrast.outputs['Color'],(*t.get('tint',(.86,.79,.66)),1),1,'MULTIPLY')
    wood=mix(m,wood,R(m,rnd,.90,1.06),1,'MULTIPLY')
    glue=R(m,M(m,'ABSOLUTE',M(m,'SUBTRACT',M(m,'FRACT',q),.5)),0,1,(.485,.497))
    wood=mix(m,wood,(.36,.27,.16,1),M(m,'MULTIPLY',glue,t.get('glue_line_strength',.2)))
    # Board object coordinates: centre of the 24 mm board, top face at z=+0.012.
    top=R(m,s['Z'],0,1,(.0105,.0118))
    ellipse=V(m,'LENGTH',V(m,'MULTIPLY',co,(1,1.25,0)))
    work=R(m,ellipse,1,0,(.07,t.get('flour_radius_m',.20)))
    ring=R(m,ellipse,.9,0,(.075,.115))
    near_bowl=R(m,V(m,'LENGTH',V(m,'MULTIPLY',V(m,'SUBTRACT',co,(-.177,.075,0)),(1,1,0))),.75,0,(.045,.11))
    patch=noise(m,co,6.5,3,.6);streak=noise(m,V(m,'MULTIPLY',co,(.30,1.7,1)),20,3,.6)
    density=M(m,'MULTIPLY',M(m,'MAXIMUM',work,near_bowl),R(m,patch.outputs['Fac'],.30,1.1,(.36,.60)))
    density=M(m,'MAXIMUM',density,M(m,'MULTIPLY',ring,R(m,patch.outputs['Fac'],.55,1,(.3,.6))))
    density=M(m,'MULTIPLY',M(m,'MULTIPLY',density,R(m,streak.outputs['Fac'],.70,1.05,(.35,.62))),top)
    fdiff,fheight,cover=flour_layer(m,co,density,t.get('flour_amount',.95))
    link(m,mix(m,wood,fdiff,cover),bs.inputs['Base Color'])
    link(m,M(m,'ADD',R(m,gray(m,rough),.50,.68,(.66,.85)),M(m,'MULTIPLY',cover,.30)),bs.inputs['Roughness'])
    n=bump(m,gray(m,rough),.00002,.22)
    n=bump(m,M(m,'MULTIPLY',glue,-1),.00008,.4,n)
    marks=0
    for k in range(9):
        angle=-.6+((k*7)%11)/11*1.2;cx=-.17+((k*5)%13)/13*.34;cy=-.13+((k*3)%11)/11*.26
        x=M(m,'SUBTRACT',s['X'],cx);y=M(m,'SUBTRACT',s['Y'],cy)
        along=M(m,'ADD',M(m,'MULTIPLY',x,math.cos(angle)),M(m,'MULTIPLY',y,math.sin(angle)))
        cross=M(m,'SUBTRACT',M(m,'MULTIPLY',y,math.cos(angle)),M(m,'MULTIPLY',x,math.sin(angle)))
        line=R(m,M(m,'ABSOLUTE',cross),1,0,(.00003,.00016))
        marks=M(m,'ADD',marks,M(m,'MULTIPLY',line,R(m,M(m,'ABSOLUTE',along),1,0,(.010,.024+(k%3)*.006))))
    n=bump(m,M(m,'MULTIPLY',M(m,'MULTIPLY',marks,-1),top),.00004,.35,n)
    link(m,bump(m,M(m,'MULTIPLY',fheight,cover),.00018,.55,n),bs.inputs['Normal'])
    return m


def loose_flour():
    m,bs=material('Loose wheat flour heap · scanned CC0 flour',(.80,.76,.66),.9)
    co=coordinates(m);fco=scaled(m,co,.30,(.41,.07,.66))
    link(m,img(m,FLOUR/'macro_flour_diff_2k.jpg',fco,box_blend=.3),bs.inputs['Base Color'])
    link(m,R(m,gray(m,img(m,FLOUR/'macro_flour_rough_2k.jpg',fco,linear=True,box_blend=.3)),.82,.97,(.78,.88)),bs.inputs['Roughness'])
    h=gray(m,img(m,FLOUR/'macro_flour_disp_2k.jpg',fco,linear=True,box_blend=.3))
    link(m,bump(m,h,.0003,.7),bs.inputs['Normal']);return m


def linen_scanned(look):
    t=look.get('towel',{})
    m,bs=material('Natural linen tea towel · scanned CC0 weave, two woven stripes',tuple(t.get('color',(.43,.39,.32))),.85)
    bs.inputs['Sheen Weight'].default_value=.35;bs.inputs['Sheen Roughness'].default_value=.6
    co=coordinates(m);s=split(m,co);uv=scaled(m,co,.27,(.23,.71,.0))
    weave=gray(m,img(m,LINEN/'rough_linen_diff_2k.jpg',uv,linear=True,box_blend=.2))
    height=gray(m,img(m,LINEN/'rough_linen_disp_2k.exr',uv,linear=True,box_blend=.2))
    base=mix(m,(*t.get('color',(.43,.39,.32)),1),R(m,weave,.86,1.10,(.64,.72)),1,'MULTIPLY')
    stripe=0
    for y0,w in ((.050,.004),(.058,.0016)):
        stripe=M(m,'MAXIMUM',stripe,R(m,M(m,'ABSOLUTE',M(m,'SUBTRACT',M(m,'ABSOLUTE',s['Y']),y0)),1,0,(w*.45,w*.55)))
    link(m,mix(m,base,(*t.get('stripe_color',(.10,.15,.12)),1),stripe),bs.inputs['Base Color'])
    link(m,R(m,gray(m,img(m,LINEN/'rough_linen_rough_2k.jpg',uv,linear=True,box_blend=.2)),.78,.95,(.62,.82)),bs.inputs['Roughness'])
    link(m,bump(m,height,.0004,.6),bs.inputs['Normal']);return m


def towel_geometry(look,mat):
    """Folded linen towel: a rounded three-layer slab with soft creases, on the bench towel's footprint."""
    old=bpy.data.objects.get('Folded linen towel on stone counter')
    loc=(-.16,.27,-.024);rot=-.2
    if old is not None:
        loc=tuple(old.location);rot=old.rotation_euler[2];bpy.data.objects.remove(old,do_unlink=True)
    from mathutils import Vector,noise as mnoise
    # Height field over the 130 x 160 mm footprint: two layers (5-6 mm) with soft creases, the edge
    # of the top fold as a 1.5 mm step, and rounded edges that come down onto the worktop.
    hx,hy,nx,ny,round_r=.065,.08,66,80,.0035
    verts=[];faces=[]
    for j in range(ny+1):
        y=-hy+2*hy*j/ny
        for i in range(nx+1):
            x=-hx+2*hx*i/nx
            d=min(hx-abs(x),hy-abs(y))
            prof=math.sqrt(max(0.,1-(1-min(d,round_r)/round_r)**2))
            h=.0048+.0007*mnoise.noise(Vector((x*38,y*38,.3)))+.00035*mnoise.noise(Vector((x*110,y*95,2.2)))
            h-=.0007*math.exp(-((x+.018+.12*y)/.004)**2)          # one soft crease across the fold
            h-=.0014/(1+math.exp(-(y-.047)/.0012))                 # top layer ends: 1.4 mm step
            verts.append((x,y,max(0.,h)*prof))
    for j in range(ny):
        for i in range(nx):
            a=j*(nx+1)+i;faces.append((a,a+1,a+nx+2,a+nx+1))
    mesh=bpy.data.meshes.new('Folded linen towel height field');mesh.from_pydata(verts,[],faces);mesh.update()
    o=bpy.data.objects.new('Folded linen tea towel on stone counter',mesh);bpy.context.collection.objects.link(o)
    o.location=(loc[0],loc[1],loc[2]+.0002);o.rotation_euler[2]=rot;mesh.materials.append(mat)
    for p in mesh.polygons:p.use_smooth=True
    return o


def flour_heap_geometry(mat):
    """Replace the bench's smooth flour dome by a loose, scooped flour surface just below the bowl rim.
    The surface is a height field whose rim sits inside the ceramic wall (no gap, never outside it)."""
    from mathutils import Vector,noise as mnoise
    old=bpy.data.objects.get('Dry flour mound filling the bowl')
    if old is None:return None
    cx,cy=-.177,.075;rim=.0410;z_edge=.046;rings=36;segs=144
    verts=[(cx,cy,z_edge+.0046)];faces=[]
    for i in range(1,rings+1):
        r=rim*i/rings
        for j in range(segs):
            a=2*math.pi*j/segs;x=cx+r*math.cos(a);y=cy+r*math.sin(a)
            dome=.0046*(1-(r/rim)**2)**1.3
            lumps=.0011*mnoise.noise(Vector((x*150,y*150,1.7)))+.0005*mnoise.noise(Vector((x*420,y*420,4.1)))
            sx,sy=x-(cx+.011),y-(cy-.008);scoop=max(0.,1-(sx*sx/.013**2+sy*sy/.010**2))
            lip=max(0.,1-abs(math.sqrt(sx*sx/.013**2+sy*sy/.010**2)-1.15)/.25)
            edge=min(1.,(rim-r)/.004)
            verts.append((x,y,z_edge+dome+edge*(lumps-.0042*scoop**1.5+.0008*lip)))
    for j in range(segs):faces.append((0,1+j,1+(j+1)%segs))
    for i in range(rings-1):
        a0=1+i*segs;b0=1+(i+1)*segs
        for j in range(segs):faces.append((a0+j,b0+j,b0+(j+1)%segs,a0+(j+1)%segs))
    mesh=bpy.data.meshes.new('Loose scooped flour surface');mesh.from_pydata(verts,[],faces);mesh.update()
    o=bpy.data.objects.new('Loose flour in the bowl (scooped surface below the rim)',mesh);bpy.context.collection.objects.link(o)
    mesh.materials.append(mat)
    for p in mesh.polygons:p.use_smooth=True
    bpy.data.objects.remove(old,do_unlink=True)
    return o


# --------------------------------------------------------------------------------------------
# Interaction bodies
# --------------------------------------------------------------------------------------------
def dough(look):
    t=look.get('dough',{})
    color=tuple(look['dough_color_linear'])
    m,bs=material('Fresh kneaded wheat dough · translucent skin, base tucks, scanned flour dusting',color,.5)
    bs.inputs['Specular IOR Level'].default_value=t.get('specular_ior_level',.36)
    bs.inputs['Subsurface Weight'].default_value=t.get('subsurface_weight',.3)
    bs.inputs['Subsurface Radius'].default_value=tuple(t.get('subsurface_radius',(1.,.62,.34)))
    bs.inputs['Subsurface Scale'].default_value=t.get('subsurface_scale_m',.003)
    attr=node(m,'ShaderNodeAttribute');attr.attribute_name='rest_position_m';co=attr.outputs['Vector'];s=split(m,co)
    broad=noise(m,co,45,3,.55);skin=noise(m,co,650,4,.6);micro=noise(m,co,3800,2,.5)
    vor=node(m,'ShaderNodeTexVoronoi');vor.inputs['Scale'].default_value=380;link(m,co,vor.inputs['Vector'])
    sparse=noise(m,co,120,2)
    pits=M(m,'MULTIPLY',R(m,vor.outputs['Distance'],1,0,(0,.17)),R(m,sparse.outputs['Fac'],0,1,(.52,.62)))
    # Gathered tucks around the base, as left by rounding the dough by hand (rest coordinates).
    tucks=0
    for k in range(7):
        th=k*2*math.pi/7+.37*math.sin(3.1*k)
        across=M(m,'ABSOLUTE',M(m,'ADD',M(m,'MULTIPLY',s['X'],-math.sin(th)),M(m,'MULTIPLY',s['Y'],math.cos(th))))
        along=M(m,'ADD',M(m,'MULTIPLY',s['X'],math.cos(th)),M(m,'MULTIPLY',s['Y'],math.sin(th)))
        line=R(m,across,1,0,(.0002,.0013+.0005*(k%3)))
        mask=M(m,'MULTIPLY',R(m,along,0,1,(.030,.050)),R(m,s['Z'],1,0,(.003,.012+.003*(k%2))))
        tucks=M(m,'ADD',tucks,M(m,'MULTIPLY',M(m,'POWER',line,2),mask))
    top=R(m,s['Z'],.2,1,(.012,.034))
    patch=noise(m,co,22,3,.6)
    density=M(m,'MULTIPLY',top,R(m,patch.outputs['Fac'],0,1.1,(.42,.62)))
    fdiff,fheight,cover=flour_layer(m,co,density,t.get('flour_amount',.75))
    base=mix(m,(*color,1),R(m,broad.outputs['Fac'],.93,1.05,(.3,.7)),1,'MULTIPLY')
    link(m,mix(m,base,fdiff,cover),bs.inputs['Base Color'])
    link(m,M(m,'ADD',R(m,skin.outputs['Fac'],t.get('roughness_min',.42),t.get('roughness_max',.56)),M(m,'MULTIPLY',cover,.35)),bs.inputs['Roughness'])
    # Soft hand-shaped unevenness (~1 cm) so the skin is not a perfect CG dome.
    lumps=noise(m,co,85,3,.55)
    n=bump(m,lumps.outputs['Fac'],t.get('lump_bump_m',.0005),.5)
    n=bump(m,M(m,'MULTIPLY',tucks,-1),.00035,.6,n)
    n=bump(m,M(m,'MULTIPLY',pits,-1),.00012,.35,n)
    n=bump(m,skin.outputs['Fac'],.00011,.40,n)
    n=bump(m,micro.outputs['Fac'],.00003,.28,n)
    link(m,bump(m,M(m,'MULTIPLY',fheight,cover),.00012,.5,n),bs.inputs['Normal'])
    m['geometry_policy']='No displacement; native FEM boundary and silhouette retained'
    m['material_coordinates']='rest_position_m, meters; follows deformation'
    return m


def egg_shell(obj,t):
    """Brown hen eggshell on the pinned egg mesh: the source UV maps keep their speckles, roughness
    and normal; colour is re-graded to a measured-looking tan-brown with mottling, fine pigment
    specks and pores in the egg's object coordinates (rigid, so nothing swims)."""
    for m in obj.data.materials:
        if not m or not m.use_nodes:continue
        for bs in [n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED']:
            color=bs.inputs['Base Color'];rough=bs.inputs['Roughness'];normal=bs.inputs['Normal']
            c0=color.links[0].from_socket if color.is_linked else None
            r0=rough.links[0].from_socket if rough.is_linked else None
            n0=normal.links[0].from_socket if normal.is_linked else None
            co=coordinates(m)
            mott=noise(m,co,t['mottle_scale_per_m'],4,.55);mott2=noise(m,co,4*t['mottle_scale_per_m'],3,.55)
            base=mix(m,(*t['light_linear'],1),(*t['dark_linear'],1),R(m,mott.outputs['Fac'],0,1,(.36,.68)))
            base=mix(m,base,R(m,mott2.outputs['Fac'],.95,1.04,(.3,.7)),1,'MULTIPLY')
            if c0 is not None:
                # Source map: flat linear luminance 0.185 with darker baked specks down to ~0.11.
                base=mix(m,base,R(m,gray(m,c0),t['source_speckle_min'],1.,(.11,.185)),1,'MULTIPLY')
            specks=noise(m,co,t['speckle_scale_per_m'],2,.5)
            base=mix(m,base,(*t['speckle_linear'],1),R(m,specks.outputs['Fac'],0,t['speckle_strength'],(.70,.78)))
            link(m,base,color)
            # Source roughness map spans 0.35-0.53 (non-colour).
            if r0 is not None:link(m,R(m,gray(m,r0),*t['roughness_range'],(.35,.53)),rough)
            else:rough.default_value=sum(t['roughness_range'])/2
            bs.inputs['Specular IOR Level'].default_value=t['specular_ior_level'];bs.inputs['Coat Weight'].default_value=0.
            bs.inputs['Sheen Weight'].default_value=t.get('sheen_weight',.12);bs.inputs['Sheen Roughness'].default_value=.5
            pores=noise(m,co,t['pore_scale_per_m'],2,.5)
            n=bump(m,pores.outputs['Fac'],t['pore_bump_distance_m'],t['pore_bump_strength'],n0)
            link(m,bump(m,mott.outputs['Fac'],.00003,.15,n),normal)
            m['shell_treatment']='regrade: UV speckles kept, object-space mottling, specks and pores'


# --------------------------------------------------------------------------------------------
# Room, daylight and render settings
# --------------------------------------------------------------------------------------------
def slab(name,x0,x1,y0,y1,z0,z1,mat,bevel=0):
    o=box(name,((x0+x1)/2,(y0+y1)/2,(z0+z1)/2),(x1-x0,y1-y0,z1-z0),mat,bevel);o['baking_role']='room';return o


def room(look):
    r=look.get('room',{})
    x_in=r.get('left_wall_x_m',-1.20);x_out=x_in-.15;x_right=r.get('right_wall_x_m',1.75)
    y_back=.50;y_front=r.get('front_wall_y_m',-2.60);z_floor=-.949;z_ceil=r.get('ceiling_z_m',1.65)
    y0,y1=r.get('window_y_m',(-.80,.25));z0,z1=r.get('window_z_m',(.12,1.30))
    wall=plaster('Painted plaster walls · scanned CC0 plaster',tuple(r.get('wall_color',(.70,.68,.63))))
    ceiling=plaster('White painted ceiling · scanned CC0 plaster',(.78,.78,.76))
    parts=[slab('Left wall below window',x_out,x_in,y_front,y_back,z_floor,z0,wall),
        slab('Left wall above window',x_out,x_in,y_front,y_back,z1,z_ceil,wall),
        slab('Left wall in front of window',x_out,x_in,y_front,y0,z0,z1,wall),
        slab('Left wall behind window',x_out,x_in,y1,y_back,z0,z1,wall),
        slab('Right kitchen wall',x_right,x_right+.15,y_front,y_back,z_floor,z_ceil,wall),
        slab('Kitchen wall behind the camera',x_out,x_right+.15,y_front-.15,y_front,z_floor,z_ceil,wall),
        slab('Kitchen ceiling',x_out,x_right+.15,y_front-.15,y_back,z_ceil,z_ceil+.12,ceiling)]
    paint,bs=material('White satin painted timber window',(.80,.80,.77),.42)
    fx0,fx1=x_out+.03,x_out+.10;w=.06
    parts+=[slab('Window frame bottom rail',fx0,fx1,y0,y1,z0,z0+w,paint,.002),slab('Window frame head',fx0,fx1,y0,y1,z1-w,z1,paint,.002),
        slab('Window frame jamb (front)',fx0,fx1,y0,y0+w,z0,z1,paint,.002),slab('Window frame jamb (back)',fx0,fx1,y1-w,y1,z0,z1,paint,.002),
        slab('Window mullion',fx0+.01,fx1-.01,(y0+y1)/2-.025,(y0+y1)/2+.025,z0,z1,paint,.002),
        slab('Window transom',fx0+.01,fx1-.01,y0,y1,z0+.68*(z1-z0)-.025,z0+.68*(z1-z0)+.025,paint,.002),
        slab('Interior window board',x_out+.02,x_in+.03,y0-.04,y1+.04,z0-.004,z0+.022,paint,.003)]
    sage=bpy.data.materials.get('Muted sage enamel cabinetry') or paint
    for k,(xa,xb) in enumerate(((-.30,.20),(.20,.70),(.70,1.20))):
        parts.append(slab(f'Wall cabinet {k+1} (above the backsplash)',xa+.002,xb-.002,.10,.43,.50,1.22,sage,.002))
    return {'left_wall_inner_x_m':x_in,'right_wall_inner_x_m':x_right,'front_wall_inner_y_m':y_front,'ceiling_z_m':z_ceil,
        'window_opening_m':{'y':[y0,y1],'z':[z0,z1],'wall_x':[x_out,x_in]},'glazing':'none modelled (open casement); sky seen through the opening',
        'objects':[o.name for o in parts]}


def daylight(scene,look,window):
    r=look.get('daylight',{})
    world=scene.world;nt=world.node_tree
    for n in list(nt.nodes):
        if n.type!='OUTPUT_WORLD':nt.nodes.remove(n)
    out=[n for n in nt.nodes if n.type=='OUTPUT_WORLD'][0]
    tc=nt.nodes.new('ShaderNodeTexCoord');mp=nt.nodes.new('ShaderNodeMapping');env=nt.nodes.new('ShaderNodeTexEnvironment');bg=nt.nodes.new('ShaderNodeBackground')
    mp.inputs['Rotation'].default_value=(0,0,math.radians(r.get('sky_rotation_deg',0.)))
    env.image=bpy.data.images.load(str(SKY),check_existing=True)
    bg.inputs['Strength'].default_value=r.get('sky_strength',1.)
    nt.links.new(tc.outputs['Generated'],mp.inputs['Vector']);nt.links.new(mp.outputs['Vector'],env.inputs['Vector'])
    nt.links.new(env.outputs['Color'],bg.inputs['Color']);nt.links.new(bg.outputs['Background'],out.inputs['Surface'])
    (y0,y1),(z0,z1)=window['window_opening_m']['y'],window['window_opening_m']['z'];x_out=window['window_opening_m']['wall_x'][0]
    ld=bpy.data.lights.new('Window opening sky portal (samples the sky; adds no light)','AREA')
    ld.shape='RECTANGLE';ld.size=z1-z0;ld.size_y=y1-y0;ld.cycles.is_portal=True
    o=bpy.data.objects.new(ld.name,ld);scene.collection.objects.link(o)
    o.location=(x_out+.005,(y0+y1)/2,(z0+z1)/2);o.rotation_euler=(0,-math.pi/2,0)
    return {'sky':'Poly Haven residential_garden (CC0), overcast; visible only through the window','sky_strength':bg.inputs['Strength'].default_value,
        'sky_rotation_deg':r.get('sky_rotation_deg',0.),'portal':o.name,'other_lights':'none'}


def render_settings(scene,look):
    r=look.get('render',{})
    c=scene.cycles
    c.samples=r.get('samples',256);c.use_adaptive_sampling=True;c.adaptive_threshold=r.get('adaptive_threshold',.01)
    c.use_denoising=True;c.denoiser='OPENIMAGEDENOISE';c.denoising_prefilter='ACCURATE'
    c.sample_clamp_indirect=r.get('clamp_indirect',10.);c.max_bounces=12;c.diffuse_bounces=r.get('diffuse_bounces',4);c.glossy_bounces=4
    c.seed=0;c.use_animated_seed=False
    scene.view_settings.view_transform='AgX';scene.view_settings.look=r.get('agx_look','AgX - Medium High Contrast')
    scene.view_settings.exposure=r.get('exposure',0.)
    scene.render.use_motion_blur=bool(r.get('motion_blur',False))
    if scene.render.use_motion_blur:
        scene.render.motion_blur_shutter=r.get('shutter_frames',.25);scene.render.motion_blur_position='CENTER'
        # Blender 4.3: persistent data with motion blur drops objects that come to rest.
        scene.render.use_persistent_data=False
    return {'samples':c.samples,'adaptive_threshold':c.adaptive_threshold,'denoiser':'OpenImageDenoise','clamp_indirect':c.sample_clamp_indirect,
        'view':'AgX','look':scene.view_settings.look,'exposure':scene.view_settings.exposure,
        'motion_blur':scene.render.use_motion_blur,'shutter_frames':scene.render.motion_blur_shutter if scene.render.use_motion_blur else 0.,
        'persistent_data':scene.render.use_persistent_data}


def finish_environment(scene,look):
    """Restyle the bench built by baking_look.make_baking_bench() and light it with daylight."""
    import baking_look
    objects=list(bpy.data.objects)
    counter=bpy.data.objects.get('36 mm seamless quartz kitchen worktop with true sink opening')
    if counter is not None:counter.data.materials.clear();counter.data.materials.append(worktop(look))
    tile,joint=glazed_tile(),grout()
    removed=0
    for o in objects:
        role=o.get('baking_role')
        if role=='backsplash_tile':
            # Tiles past the side walls would sit outside the room.
            if o.location.x-.075<look.get('room',{}).get('left_wall_x_m',-1.20) or o.location.x+.075>look.get('room',{}).get('right_wall_x_m',1.75):
                bpy.data.objects.remove(o,do_unlink=True);removed+=1;continue
            o.data.materials.clear();o.data.materials.append(tile)
        elif o.name in ('Backsplash mortar bed','Silicone counter to tile joint'):
            o.data.materials.clear();o.data.materials.append(joint)
            if o.name=='Backsplash mortar bed':
                # Grout fills the 2 mm joints to 1.5 mm behind the tile face (the bed as built sits 8 mm back,
                # which reads as dark open slots). The bed's hidden part lies inside the tile bodies.
                o.location.y=.4125+o.dimensions.y/2
        elif o.name=='Continuous wall behind kitchen':
            o.data.materials.clear();o.data.materials.append(plaster('Painted plaster back wall · scanned CC0 plaster',tuple(look.get('room',{}).get('wall_color',(.70,.68,.63)))))
        elif role=='physical_support_surface':
            o.data.materials.clear();o.data.materials.append(pastry_board(look))
    flour_heap_geometry(loose_flour())
    towel_geometry(look,linen_scanned(look))
    window=room(look)
    light=daylight(scene,look,window)
    render=render_settings(scene,look)
    RECEIPT.update({'room':window,'daylight':light,'render':render,'removed_out_of_room_tiles':removed,
        'scanned_maps':sorted(FILES)})
    baking_look.LAYOUT['room_and_daylight']=RECEIPT
    kitchen=baking_look.LAYOUT.get('kitchen',{})
    if 'countertop' in kitchen:kitchen['countertop']['material']='Honed engineered quartz: procedural aggregate flecks, scanned ambientCG SurfaceImperfections018 wear in roughness'
    return RECEIPT
