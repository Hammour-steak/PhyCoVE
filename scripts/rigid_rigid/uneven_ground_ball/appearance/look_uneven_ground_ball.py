"""Pine-forest hiking trail: scanned ground, real trees and an HDRI sky.

The ground is the simulation mesh itself: nothing here moves a vertex of it.
A worn trail of packed earth (Poly Haven ``forest_ground_04``) runs along the
terrain's broad trough, where every ball rolls; pine-needle litter
(``forest_leaves_04``) covers the rest. Both are shading only (albedo,
roughness, normal map and a millimetre-scale bump), so the ball sits exactly
on the collision surface. Hollows and crests keep the cavity tint baked from
the same height field.

The setting around it is built from CC0 Poly Haven scans: pine trunks with
the ``pine_bark`` scan, stumps, a fallen trunk, ferns, saplings, moss-covered
rocks, dry branches and stones. None of it takes part in the simulation; every
piece is checked at render time against the ball trajectories of all six
cases (``ball_corridor.json``) for clearance and for blocking the camera's
view of the ball. The bench, planters and fence boxes that the simulator still
contains are 2.2 m or more from any trajectory and are not drawn.

Light is the unclipped ``forest_slope`` HDRI (a sunny pine forest) plus a sun
lamp on the bearing and elevation of the HDRI's own sun; the map's small
sun disc is replaced by the sky around it so the sun is not counted twice.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from pathlib import Path
import json,math,random

from pcve_assets import asset as _pcve_asset
ASSETS=_pcve_asset('')/'polyhaven'/'uneven_ground_ball'
CORRIDOR=Path(__file__).with_name('ball_corridor.json')
TRAIL_TEXTURE='forest_ground_04'   # packed trail earth, 3.15 m scan
FLOOR_TEXTURE='forest_leaves_04'   # pine needles and twigs, 1.5 m scan
BARK_TEXTURE='pine_bark'           # 2 m scan
HDRI=ASSETS/'forest_slope_4k.hdr'
RESOLUTION='2k'
CHANNELS=('diff','disp','nor_gl','rough')
# The trail follows the terrain's broad trough (centre y=-0.30, see scene_config bumps).
TRAIL_CENTRE_Y=-.30
TRAIL_HALF_WIDTH=.95
# Scene bearing (atan2(y, x)) the sky is turned to put its sun at: ahead and to
# the right of the camera (the camera looks along +y, bearing 90). That turns the
# open, downhill part of the panorama (tall stems, green understory) to the
# back of the shot, and the sun rakes the trail from the right as before, so
# every crest throws its shadow towards the camera-left.
SUN_AZIMUTH_DEG=45.
SUN_STRENGTH=16.          # W/m^2 at normal incidence; about 4:1 against the sky
SUN_ANGLE_DEG=.53
SUN_COLOUR=(1.,.95,.88)
EXPOSURE=-.15             # AgX - Medium High Contrast
CLEARANCE=.02             # m between any prop and the ball surface, all six cases


def material(bpy,name,color,metal=0,roughness=.5):
    mat=bpy.data.materials.new(name);mat.diffuse_color=(*color,1);mat.use_nodes=True
    shader=mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=(*color,1);shader.inputs['Metallic'].default_value=metal;shader.inputs['Roughness'].default_value=roughness
    return mat

def load_texture_set(bpy,asset,resolution=RESOLUTION):
    """Return {channel: bpy.types.Image} for a fetched Poly Haven set."""
    images={}
    for channel in CHANNELS:
        path=ASSETS/f'{asset}_{channel}_{resolution}.jpg'
        if not path.exists():raise FileNotFoundError(f'Missing texture {path}; run scripts/download_assets.py --scene uneven_ground_ball')
        image=bpy.data.images.load(str(path),check_existing=True)
        image.colorspace_settings.name='sRGB' if channel=='diff' else 'Non-Color'
        images[channel]=image
    return images

def _mix(nodes,links,factor,first,second,blend='MIX'):
    """MixRGB that accepts either a socket, an RGB tuple, or a numeric factor."""
    node=nodes.new('ShaderNodeMixRGB');node.blend_type=blend
    if isinstance(factor,(int,float)):node.inputs[0].default_value=factor
    else:links.new(factor,node.inputs[0])
    for source,index in ((first,1),(second,2)):
        if isinstance(source,tuple):
            node.inputs[index].default_value=tuple(source)+(1.,)*(4-len(source)) if len(source)<4 else source
        else:links.new(source,node.inputs[index])
    return node.outputs['Color']

def _samplers(nodes,links,uv,images,metres_per_tile,label,rotation=0.,offset=(0.,0.)):
    """One mapping per texture set; every channel shares it so tiling is exact."""
    mapping=nodes.new('ShaderNodeMapping');mapping.vector_type='POINT'
    mapping.inputs['Scale'].default_value=(1/metres_per_tile,)*3
    mapping.inputs['Rotation'].default_value[2]=math.radians(rotation)
    mapping.inputs['Location'].default_value=(*offset,0.)
    links.new(uv,mapping.inputs['Vector'])
    out={}
    for channel,image in images.items():
        sampler=nodes.new('ShaderNodeTexImage');sampler.image=image
        sampler.label=f'{label} {channel} ({metres_per_tile:g} m per tile)'
        links.new(mapping.outputs['Vector'],sampler.inputs['Vector'])
        out[channel]=sampler.outputs['Color']
    return out

def _noise(nodes,links,vector,scale,detail=4.,roughness=.5):
    node=nodes.new('ShaderNodeTexNoise');node.inputs['Scale'].default_value=scale;node.inputs['Detail'].default_value=detail
    node.inputs['Roughness'].default_value=roughness;links.new(vector,node.inputs['Vector']);return node.outputs['Fac']

def _ramp(nodes,links,fac,low,high,lo_color=(0,0,0,1),hi_color=(1,1,1,1)):
    ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=low;ramp.color_ramp.elements[1].position=high
    ramp.color_ramp.elements[0].color=lo_color;ramp.color_ramp.elements[1].color=hi_color
    links.new(fac,ramp.inputs[0]);return ramp.outputs['Color']

def ground_material(bpy,c,guide='none',trail_asset=TRAIL_TEXTURE,floor_asset=FLOOR_TEXTURE,
                    trail_half_width=TRAIL_HALF_WIDTH,edge_width=.45,vertex_tint='terrain_shading'):
    trail=load_texture_set(bpy,trail_asset);floor=load_texture_set(bpy,floor_asset)
    mat=material(bpy,'Pine trail and needle litter',(.20,.15,.10),roughness=.85)
    nodes,links=mat.node_tree.nodes,mat.node_tree.links;shader=nodes.get('Principled BSDF')
    uv=nodes.new('ShaderNodeTexCoord').outputs['UV']
    separate=nodes.new('ShaderNodeSeparateXYZ');links.new(uv,separate.inputs[0])
    trail_set=_samplers(nodes,links,uv,trail,3.15,'trail')
    # Needle litter: the same scan twice, turned and shifted, blended by a
    # 3 m noise so the 1.5 m repeat never lines up.
    floor_a=_samplers(nodes,links,uv,floor,1.5,'litter A')
    floor_b=_samplers(nodes,links,uv,floor,1.5,'litter B',rotation=63.,offset=(.37,.81))
    patch=_ramp(nodes,links,_noise(nodes,links,uv,.33,3.),.42,.58)
    floor_set={key:_mix(nodes,links,patch,floor_a[key],floor_b[key]) for key in CHANNELS}

    # --- trail / litter boundary, broken up so the edge is never a straight line
    wobble=nodes.new('ShaderNodeMath');wobble.operation='MULTIPLY';wobble.inputs[1].default_value=.55
    links.new(_noise(nodes,links,uv,1.4,5.),wobble.inputs[0])
    offset_y=nodes.new('ShaderNodeMath');offset_y.operation='SUBTRACT';offset_y.inputs[1].default_value=TRAIL_CENTRE_Y
    links.new(separate.outputs['Y'],offset_y.inputs[0])
    absolute_y=nodes.new('ShaderNodeMath');absolute_y.operation='ABSOLUTE';links.new(offset_y.outputs[0],absolute_y.inputs[0])
    shifted=nodes.new('ShaderNodeMath');shifted.operation='ADD'
    links.new(absolute_y.outputs[0],shifted.inputs[0]);links.new(wobble.outputs[0],shifted.inputs[1])
    is_litter=nodes.new('ShaderNodeMapRange');is_litter.interpolation_type='SMOOTHSTEP'
    is_litter.inputs['From Min'].default_value=trail_half_width;is_litter.inputs['From Max'].default_value=trail_half_width+edge_width
    links.new(shifted.outputs[0],is_litter.inputs['Value'])
    # Needles drift onto the trail in thin patches as well.
    drift=_ramp(nodes,links,_noise(nodes,links,uv,4.5,6.,.6),.55,.75)
    drift_amount=nodes.new('ShaderNodeMath');drift_amount.operation='MULTIPLY';drift_amount.inputs[1].default_value=.55
    links.new(drift,drift_amount.inputs[0])
    litter=nodes.new('ShaderNodeMath');litter.operation='MAXIMUM';litter.use_clamp=True
    links.new(is_litter.outputs['Result'],litter.inputs[0]);links.new(drift_amount.outputs[0],litter.inputs[1])
    litter=litter.outputs[0]

    # Damp/dry variation over a few metres on the bare earth.
    macro=_ramp(nodes,links,_noise(nodes,links,uv,.45,4.),.30,.72,(.80,.76,.70,1),(1.06,1.03,.98,1))
    trail_colour=_mix(nodes,links,1.,trail_set['diff'],macro,'MULTIPLY')
    floor_colour=_mix(nodes,links,1.,floor_set['diff'],(.92,.88,.84),'MULTIPLY')
    # Moss cushions in the litter, only well away from the trail (y > 1.3 m).
    away=nodes.new('ShaderNodeMapRange');away.inputs['From Min'].default_value=1.3;away.inputs['From Max'].default_value=2.6
    links.new(separate.outputs['Y'],away.inputs['Value'])
    moss=nodes.new('ShaderNodeMath');moss.operation='MULTIPLY'
    links.new(_ramp(nodes,links,_noise(nodes,links,uv,.42,6.,.62),.54,.63),moss.inputs[0]);links.new(away.outputs['Result'],moss.inputs[1])
    floor_colour=_mix(nodes,links,moss.outputs[0],floor_colour,_mix(nodes,links,.55,floor_set['diff'],(.07,.12,.03),'MULTIPLY'))
    albedo=_mix(nodes,links,litter,trail_colour,floor_colour)
    if vertex_tint:
        tint=nodes.new('ShaderNodeVertexColor');tint.layer_name=vertex_tint
        albedo=_mix(nodes,links,1.,albedo,tint.outputs['Color'],'MULTIPLY')
    links.new(albedo,shader.inputs['Base Color'])

    span=nodes.new('ShaderNodeMapRange');span.inputs['To Min'].default_value=.62;span.inputs['To Max'].default_value=.98
    links.new(_mix(nodes,links,litter,trail_set['rough'],floor_set['rough']),span.inputs['Value'])
    links.new(span.outputs['Result'],shader.inputs['Roughness'])

    # --- micro relief: mixed tangent-space normals, then the height map as a
    # bump of a few millimetres (shading only; the surface does not move).
    normal_map=nodes.new('ShaderNodeNormalMap');normal_map.inputs['Strength'].default_value=1.;normal_map.space='TANGENT'
    normal_map.uv_map='World metres'
    links.new(_mix(nodes,links,litter,trail_set['nor_gl'],floor_set['nor_gl']),normal_map.inputs['Color'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.6;bump.inputs['Distance'].default_value=.004
    links.new(_mix(nodes,links,litter,trail_set['disp'],floor_set['disp']),bump.inputs['Height'])
    links.new(normal_map.outputs['Normal'],bump.inputs['Normal'])
    links.new(bump.outputs['Normal'],shader.inputs['Normal'])

    if guide=='contours':
        position=nodes.new('ShaderNodeNewGeometry');xyz=nodes.new('ShaderNodeSeparateXYZ');links.new(position.outputs['Position'],xyz.inputs[0])
        grade=nodes.new('ShaderNodeMath');grade.operation='MULTIPLY';grade.inputs[1].default_value=c['terrain_slope'];links.new(xyz.outputs['X'],grade.inputs[0])
        subtract=nodes.new('ShaderNodeMath');subtract.operation='SUBTRACT';links.new(xyz.outputs['Z'],subtract.inputs[0]);links.new(grade.outputs[0],subtract.inputs[1])
        baseline=nodes.new('ShaderNodeMath');baseline.operation='SUBTRACT';baseline.inputs[1].default_value=c['terrain_base_height'];links.new(subtract.outputs[0],baseline.inputs[0])
        scale=nodes.new('ShaderNodeMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=50.;links.new(baseline.outputs[0],scale.inputs[0])
        repeat=nodes.new('ShaderNodeMath');repeat.operation='PINGPONG';repeat.inputs[1].default_value=.5;links.new(scale.outputs[0],repeat.inputs[0])
        threshold=nodes.new('ShaderNodeMath');threshold.operation='LESS_THAN';threshold.inputs[1].default_value=.016;links.new(repeat.outputs[0],threshold.inputs[0])
        overlay=nodes.new('ShaderNodeMixRGB');overlay.blend_type='MIX'
        links.new(albedo,overlay.inputs[1]);overlay.inputs[2].default_value=(.03,.09,.10,1)
        links.new(threshold.outputs[0],overlay.inputs[0])
        links.new(overlay.outputs['Color'],shader.inputs['Base Color'])
    return mat

def bake_terrain_shading(mesh,vertices,c):
    """Bake cavity and slope into a colour attribute: shading data, not geometry.

    Hollows collect damp fine material and read darker; exposed crests are
    scuffed lighter. The tint is derived from the same height field the ball
    collides with, so it cannot contradict the motion.
    """
    import numpy as np
    from terrain_geometry import curvature
    x=vertices[:,0];y=vertices[:,1]
    lap=curvature(x,y,c)
    # Positive Laplacian = hollow (surface curves up around the point).
    cavity=np.clip(lap/6.,-1.,1.)
    brightness=1.-.34*cavity
    warm=np.clip(-cavity,0.,1.)
    tint=np.stack((brightness+.05*warm,brightness,brightness-.06*warm),axis=1)
    tint=np.clip(tint,0.,2.2)
    attribute=mesh.color_attributes.new(name='terrain_shading',type='FLOAT_COLOR',domain='POINT')
    rgba=np.concatenate((tint,np.ones((len(tint),1))),axis=1)
    attribute.data.foreach_set('color',rgba.astype(np.float32).ravel())
    return tint

def ball_material(bpy):
    """Moulded rubber play ball: four printed panels, pebble grain, trail dust."""
    mat=material(bpy,'Blue and yellow rubber play ball',(.02,.10,.42),roughness=.48)
    nodes,links=mat.node_tree.nodes,mat.node_tree.links;shader=nodes.get('Principled BSDF')
    coord=nodes.new('ShaderNodeTexCoord');sep=nodes.new('ShaderNodeSeparateXYZ');links.new(coord.outputs['Generated'],sep.inputs[0])
    centred=[]
    for axis in ('X','Y'):
        node=nodes.new('ShaderNodeMath');node.operation='SUBTRACT';node.inputs[1].default_value=.5;links.new(sep.outputs[axis],node.inputs[0]);centred.append(node)
    angle=nodes.new('ShaderNodeMath');angle.operation='ARCTAN2';links.new(centred[1].outputs[0],angle.inputs[0]);links.new(centred[0].outputs[0],angle.inputs[1])
    freq=nodes.new('ShaderNodeMath');freq.operation='MULTIPLY';freq.inputs[1].default_value=2;links.new(angle.outputs[0],freq.inputs[0])
    wave=nodes.new('ShaderNodeMath');wave.operation='SINE';links.new(freq.outputs[0],wave.inputs[0])
    split=nodes.new('ShaderNodeMath');split.operation='GREATER_THAN';links.new(wave.outputs[0],split.inputs[0])
    panels=_mix(nodes,links,split.outputs[0],(.018,.085,.36,1),(.80,.56,.035,1))
    # Moulding seams between panels: thin, slightly darker lines.
    seam=nodes.new('ShaderNodeMath');seam.operation='ABSOLUTE';links.new(wave.outputs[0],seam.inputs[0])
    seam_line=nodes.new('ShaderNodeMath');seam_line.operation='LESS_THAN';seam_line.inputs[1].default_value=.035;links.new(seam.outputs[0],seam_line.inputs[0])
    seam_mix=nodes.new('ShaderNodeMath');seam_mix.operation='MULTIPLY';seam_mix.inputs[1].default_value=.55;links.new(seam_line.outputs[0],seam_mix.inputs[0])
    albedo=_mix(nodes,links,seam_mix.outputs[0],panels,(.03,.03,.03,1))
    # Fine trail dust settles in the grain and dulls the print a little.
    dust=_ramp(nodes,links,_noise(nodes,links,coord.outputs['Object'],38.,6.,.6),.48,.80)
    dust_amount=nodes.new('ShaderNodeMath');dust_amount.operation='MULTIPLY';dust_amount.inputs[1].default_value=.32;links.new(dust,dust_amount.inputs[0])
    albedo=_mix(nodes,links,dust_amount.outputs[0],albedo,(.30,.24,.17,1))
    links.new(albedo,shader.inputs['Base Color'])
    rough=nodes.new('ShaderNodeMath');rough.operation='MULTIPLY_ADD';rough.inputs[1].default_value=.35;rough.inputs[2].default_value=.42
    links.new(dust_amount.outputs[0],rough.inputs[0]);links.new(rough.outputs[0],shader.inputs['Roughness'])
    for name,value in (('Coat Weight',.12),('Coat Roughness',.35),('Specular IOR Level',.45)):
        if name in shader.inputs:shader.inputs[name].default_value=value
    # Pebble grain about 1.5 mm across (ball diameter 0.2 m = 1 generated unit).
    grain=nodes.new('ShaderNodeTexVoronoi');grain.feature='SMOOTH_F1'
    grain.inputs['Scale'].default_value=130.;links.new(coord.outputs['Generated'],grain.inputs['Vector'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.35;bump.inputs['Distance'].default_value=.0004
    links.new(grain.outputs['Distance'],bump.inputs['Height']);links.new(bump.outputs[0],shader.inputs['Normal'])
    return mat

# ---------------------------------------------------------------- sky and sun

def _hdri_sun(np,image):
    """Sun of an equirectangular map: direction in the map's own frame, its
    irradiance at normal incidence (with the surrounding sky subtracted), the
    sky radiance just around it, and the cone that contains the disc."""
    w,h=image.size
    px=np.empty(w*h*4,np.float32);image.pixels.foreach_get(px)
    rgb=px.reshape(h,w,4)[...,:3].astype(np.float64)
    lum=rgb@np.array([.2126,.7152,.0722])
    row,col=np.unravel_index(np.argmax(lum),lum.shape)
    # Blender equirect: u = 0.5 - atan2(y, x) / 2pi; image rows run bottom-up.
    lon=(.5-(np.arange(w)+.5)/w)*2*math.pi
    lat=((np.arange(h)+.5)/h-.5)*math.pi
    azimuth,elevation=lon[col],lat[row]
    sun=np.array([math.cos(elevation)*math.cos(azimuth),math.cos(elevation)*math.sin(azimuth),math.sin(elevation)])
    cos_lat=np.cos(lat)[:,None]
    cos_angle=(cos_lat*np.cos(lon)[None,:]*sun[0]+cos_lat*np.sin(lon)[None,:]*sun[1]+np.sin(lat)[:,None]*sun[2])
    ring=(cos_angle<math.cos(math.radians(3)))&(cos_angle>math.cos(math.radians(6)))
    fill=rgb[ring].mean(0)
    disc=(cos_angle>math.cos(math.radians(3)))&(lum>3*float(fill@np.array([.2126,.7152,.0722])))
    radius=math.degrees(math.acos(min(1.,float(cos_angle[disc].min()))))+360/w
    return dict(azimuth_deg=math.degrees(azimuth),elevation_deg=math.degrees(elevation),fill=fill,radius_deg=radius)

def build_world(bpy,scene):
    """forest_slope HDRI turned so its sun sits at SUN_AZIMUTH_DEG, plus a sun lamp there.

    The map was shot in a pine forest whose canopy hides most of the sun disc
    (its measured disc irradiance is under 0.02), so the map alone gives only
    soft skylight. The lamp restores the direct sun on the open trail at the
    HDRI's own elevation; the few disc pixels are replaced by the sky around
    them so they neither double the sun nor sparkle.
    """
    import numpy as np
    from mathutils import Vector
    image=bpy.data.images.load(str(HDRI),check_existing=True);image.colorspace_settings.name='Linear Rec.709'
    sun=_hdri_sun(np,image)
    turn=sun['azimuth_deg']-SUN_AZIMUTH_DEG
    azimuth,elevation=math.radians(SUN_AZIMUTH_DEG),math.radians(sun['elevation_deg'])
    toward_sun=Vector((math.cos(elevation)*math.cos(azimuth),math.cos(elevation)*math.sin(azimuth),math.sin(elevation)))
    world=bpy.data.worlds.new('Pine forest morning sky');world.use_nodes=True;scene.world=world
    n,l=world.node_tree.nodes,world.node_tree.links
    coord=n.new('ShaderNodeTexCoord')
    mapping=n.new('ShaderNodeMapping');mapping.inputs['Rotation'].default_value[2]=math.radians(turn)
    env=n.new('ShaderNodeTexEnvironment');env.image=image
    l.new(coord.outputs['Generated'],mapping.inputs['Vector']);l.new(mapping.outputs['Vector'],env.inputs['Vector'])
    unit=n.new('ShaderNodeVectorMath');unit.operation='NORMALIZE';l.new(coord.outputs['Generated'],unit.inputs[0])
    dot=n.new('ShaderNodeVectorMath');dot.operation='DOT_PRODUCT';dot.inputs[1].default_value=toward_sun;l.new(unit.outputs['Vector'],dot.inputs[0])
    inside=n.new('ShaderNodeMath');inside.operation='GREATER_THAN';inside.inputs[1].default_value=math.cos(math.radians(sun['radius_deg']))
    l.new(dot.outputs['Value'],inside.inputs[0])
    cut=_mix(n,l,inside.outputs['Value'],env.outputs['Color'],tuple(float(v) for v in sun['fill'])+(1.,))
    background=n.get('Background');l.new(cut,background.inputs['Color']);background.inputs['Strength'].default_value=1.
    bpy.ops.object.light_add(type='SUN',location=(0,0,8));lamp=bpy.context.object;lamp.name='Morning sun (bearing of the HDRI sun)'
    lamp.rotation_euler=(-toward_sun).to_track_quat('-Z','Y').to_euler()
    lamp.data.energy=SUN_STRENGTH;lamp.data.color=SUN_COLOUR;lamp.data.angle=math.radians(SUN_ANGLE_DEG)
    print(f"[sky] HDRI sun azimuth {sun['azimuth_deg']:.2f} elevation {sun['elevation_deg']:.2f} deg, disc {sun['radius_deg']:.2f} deg; "
          f"sky turned {turn:.2f} deg, lamp {SUN_STRENGTH} W/m2 from azimuth {SUN_AZIMUTH_DEG}",flush=True)
    return lamp

# ---------------------------------------------------------------- the forest

def _terrain_uv_mesh(bpy,name,vertices,faces):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata([tuple(v) for v in vertices],[],[tuple(f) for f in faces]);mesh.update()
    uv=mesh.uv_layers.new(name='World metres')
    import numpy as np
    loops=np.empty(len(mesh.loops),dtype=np.int32);mesh.loops.foreach_get('vertex_index',loops)
    uv.data.foreach_set('uv',np.asarray(vertices,dtype=np.float32)[loops][:,:2].ravel())
    for face in mesh.polygons:face.use_smooth=True
    return mesh

def build_far_ground(bpy,c,mat):
    """Forest floor beyond the far edge of the collision terrain (y > 8 m).

    Same height function and material, so the litter carries on to the trees
    behind; it starts 5 cm under the terrain edge to leave no seam. The ball
    never comes within 9 m of it.
    """
    import numpy as np
    from terrain_geometry import height
    (x0,_),(x1,y1)=c['terrain_bounds']
    xs=np.linspace(-40.,40.,321);ys=np.concatenate(([y1-.05],np.linspace(y1+.25,60.,240)))
    x,y=np.meshgrid(xs,ys,indexing='ij');z=height(x,y,c)-.004
    vertices=np.column_stack((x.ravel(),y.ravel(),z.ravel()))
    nx,ny=len(xs),len(ys);faces=[]
    for i in range(nx-1):
        for j in range(ny-1):
            a=i*ny+j;b=a+ny;faces.extend([(a,b,b+1),(a,b+1,a+1)])
    mesh=_terrain_uv_mesh(bpy,'Forest floor beyond the trail',vertices,faces)
    bake_terrain_shading(mesh,vertices,c)
    obj=bpy.data.objects.new('Forest floor beyond the trail',mesh);bpy.context.scene.collection.objects.link(obj);obj.data.materials.append(mat)
    return obj

def bark_material(bpy):
    bark=load_texture_set(bpy,BARK_TEXTURE)
    mat=material(bpy,'Scots pine bark',(.25,.17,.12),roughness=.9)
    nodes,links=mat.node_tree.nodes,mat.node_tree.links;shader=nodes.get('Principled BSDF')
    uv=nodes.new('ShaderNodeUVMap');uv.uv_map='Bark metres'
    s=_samplers(nodes,links,uv.outputs['UV'],bark,2.,'bark')
    # Pine bark is grey-brown low down and turns orange higher up the stem.
    sep=nodes.new('ShaderNodeSeparateXYZ');links.new(uv.outputs['UV'],sep.inputs[0])
    upper=nodes.new('ShaderNodeMapRange');upper.inputs['From Min'].default_value=2.5;upper.inputs['From Max'].default_value=7.;links.new(sep.outputs['Y'],upper.inputs['Value'])
    warm=_mix(nodes,links,upper.outputs['Result'],(.88,.87,.86),(1.12,.95,.80))
    # Each stem a little lighter or darker, greyer or redder.
    info=nodes.new('ShaderNodeObjectInfo')
    shade=_ramp(nodes,links,info.outputs['Random'],0.,1.,(.70,.68,.68,1),(1.08,1.0,.94,1))
    links.new(_mix(nodes,links,1.,_mix(nodes,links,1.,s['diff'],warm,'MULTIPLY'),shade,'MULTIPLY'),shader.inputs['Base Color'])
    links.new(s['rough'],shader.inputs['Roughness'])
    nm=nodes.new('ShaderNodeNormalMap');nm.uv_map='Bark metres';nm.inputs['Strength'].default_value=1.2;links.new(s['nor_gl'],nm.inputs['Color'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.8;bump.inputs['Distance'].default_value=.02
    links.new(s['disp'],bump.inputs['Height']);links.new(nm.outputs['Normal'],bump.inputs['Normal']);links.new(bump.outputs[0],shader.inputs['Normal'])
    return mat

def pine_trunk(bpy,name,base,radius,height_m,lean,mat,seed):
    """A straight pine stem: tapering, root flare, bark UVs in metres."""
    import numpy as np
    rng=np.random.default_rng(seed);segments=28;rings=40
    zs=np.concatenate((np.linspace(0,1.2,16),np.linspace(1.35,height_m,rings-16)))
    verts=[];uvs=[];faces=[]
    lobes=rng.uniform(0,2*math.pi,3)
    for k,z in enumerate(zs):
        r=radius*(1-.35*z/height_m)*(1+.55*math.exp(-z/.28))
        for s in range(segments+1):
            t=2*math.pi*s/segments
            wobble=1+.05*sum(math.sin(3*t+a)*math.exp(-z/.6) for a in lobes)
            rr=r*wobble
            verts.append((base[0]+rr*math.cos(t)+lean[0]*z,base[1]+rr*math.sin(t)+lean[1]*z,base[2]+z-.25))
            uvs.append((t*radius,z))
    for k in range(len(zs)-1):
        for s in range(segments):
            a=k*(segments+1)+s;b=a+segments+1;faces.append((a,a+1,b+1,b))
    # Dead lower branches broken off short, as on any pine grown in a stand.
    for _ in range(int(rng.integers(6,12))):
        z0=float(rng.uniform(.8,min(7.,height_m*.45)));t=float(rng.uniform(0,2*math.pi));r_here=radius*(1-.35*z0/height_m)
        length=float(rng.uniform(.10,.34));thick=float(rng.uniform(.010,.024));droop=math.radians(float(rng.uniform(5,30)))
        d=(math.cos(t)*math.cos(droop),math.sin(t)*math.cos(droop),-math.sin(droop))
        u=(-math.sin(t),math.cos(t),0.);w=(d[1]*u[2]-d[2]*u[1],d[2]*u[0]-d[0]*u[2],d[0]*u[1]-d[1]*u[0])
        start=(base[0]+lean[0]*z0+(r_here-.02)*math.cos(t),base[1]+lean[1]*z0+(r_here-.02)*math.sin(t),base[2]+z0-.25)
        first=len(verts)
        for end,rad in ((0.,thick),(length+.02,thick*.35)):
            for s in range(6):
                a=2*math.pi*s/6
                verts.append(tuple(start[i]+d[i]*end+rad*(math.cos(a)*u[i]+math.sin(a)*w[i]) for i in range(3)));uvs.append((a*thick,z0+end))
        for s in range(6):faces.append((first+s,first+(s+1)%6,first+6+(s+1)%6,first+6+s))
        faces.append(tuple(first+6+s for s in range(6)))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    uv=mesh.uv_layers.new(name='Bark metres')
    for poly in mesh.polygons:
        poly.use_smooth=True
        for li in poly.loop_indices:uv.data[li].uv=uvs[mesh.loops[li].vertex_index]
    obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj);obj.data.materials.append(mat)
    return obj

_GLTF={}

def _import_gltf(bpy,asset_id):
    """Import a Poly Haven glTF once; return {mesh object name: object}, unlinked
    from the scene, each mesh centred on its own footprint (the sets are laid
    out side by side in the file) with its modelled ground line kept at z=0."""
    if asset_id in _GLTF:return _GLTF[asset_id]
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(ASSETS/asset_id/f'{asset_id}_1k.gltf'))
    new=[o for o in bpy.data.objects if o not in before]
    meshes={}
    for o in new:
        for collection in list(o.users_collection):collection.objects.unlink(o)
        if o.type=='MESH':
            from mathutils import Matrix
            o.data.transform(o.matrix_world);o.matrix_world.identity()
            xs=[v.co.x for v in o.data.vertices];ys=[v.co.y for v in o.data.vertices]
            o.data.transform(Matrix.Translation((-(min(xs)+max(xs))/2,-(min(ys)+max(ys))/2,0)))
            meshes[o.name]=o
    _GLTF[asset_id]=meshes
    return meshes

def _place(bpy,source,name,location,yaw_deg,scale=1.,sink=0.,tilt=(0.,0.)):
    from mathutils import Matrix,Euler
    obj=bpy.data.objects.new(name,source.data);bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world=Matrix.Translation((location[0],location[1],location[2]-sink))@Euler((math.radians(tilt[0]),math.radians(tilt[1]),math.radians(yaw_deg)),'XYZ').to_matrix().to_4x4()@Matrix.Scale(scale,4)
    return obj

# Hand-placed props (scene metres; the camera looks along +y from y=-2.2).
# (asset, mesh, x, y, yaw deg, scale, sink m)
PROPS=[('tree_stump_01','tree_stump_01',-2.55,2.75,35.,1.,.04),
       ('tree_stump_02','tree_stump_02',2.35,3.55,-25.,.9,.04),
       ('dead_tree_trunk','dead_tree_trunk',.25,2.35,7.,1.,.05),
       ('dry_branches_medium_01','dry_branches_medium_01_a',-1.05,1.45,96.,.9,.01),
       ('dry_branches_medium_01','dry_branches_medium_01_c',1.55,1.35,-74.,1.,.005),
       ('rock_moss_set_02','rock_moss_set_02_rock12',-3.9,4.9,20.,.85,.12),
       ('rock_moss_set_02','rock_moss_set_02_rock08',3.6,5.6,-40.,.9,.08),
       ('pine_sapling_small','pine_sapling_small_a',-1.35,4.35,10.,1.,.02),
       ('pine_sapling_small','pine_sapling_small_c',4.1,4.2,70.,1.,.02),
       ('pine_sapling_small','pine_sapling_small_b',.95,5.9,140.,1.05,.02)]
FERNS=[(-3.3,1.9,20.,'b'),(-1.95,1.55,140.,'a'),(-0.65,2.0,75.,'c'),(1.05,1.75,-30.,'d'),(2.45,1.7,200.,'b'),
       (3.5,2.4,110.,'c'),(-4.4,2.9,250.,'b'),(-.2,3.3,10.,'a'),(1.6,2.75,300.,'c'),(5.0,3.3,40.,'b'),(-5.6,3.9,160.,'c')]
# Pine stems: (x, y, radius) on the collision terrain behind the trail, then
# seeded stems on the far floor.
TRUNKS=[(-3.2,3.9,.19),(-1.85,6.2,.29),(-.75,5.4,.13),(1.4,4.0,.23),(2.9,6.6,.27),(4.6,3.6,.18),(-5.2,6.4,.26),(.6,7.3,.2),(6.2,6.0,.22)]

def build_forest(bpy,c,ground):
    """Everything around the trail. Returns the prop objects (for the checks)."""
    from terrain_geometry import height
    props=[build_far_ground(bpy,c,ground)]
    bark=bark_material(bpy);rng=random.Random(4107)
    stems=list(TRUNKS);tries=0
    while len(stems)<40 and tries<4000:
        tries+=1;y=rng.uniform(8.3,34.);half=.72*(y+2.2)+1.5;x=rng.uniform(-half,half)
        if all(math.hypot(x-sx,y-sy)>1.6 for sx,sy,_ in stems):stems.append((x,y,rng.uniform(.10,.34)))
    for i,(x,y,r) in enumerate(stems):
        z=float(height(x,y,c));lean=(rng.uniform(-.012,.012),rng.uniform(-.012,.012))
        props.append(pine_trunk(bpy,f'Pine stem {i:02d}',(x,y,z),r,rng.uniform(18.,26.),lean,bark,seed=100+i))
    def source(asset,mesh):return _import_gltf(bpy,asset)[mesh]
    for asset,mesh,x,y,yaw,scale,sink in PROPS:
        props.append(_place(bpy,source(asset,mesh),f'{asset} at ({x:g}, {y:g})',(x,y,float(height(x,y,c))),yaw,scale,sink))
    ferns=list(FERNS);tries=0
    while len(ferns)<90 and tries<6000:
        tries+=1;y=rng.uniform(2.7,24.);half=.72*(y+2.2)+1.;x=rng.uniform(-half,half)
        if all(math.hypot(x-fx,y-fy)>.75 for fx,fy,*_ in ferns) and all(math.hypot(x-sx,y-sy)>r+.45 for sx,sy,r in stems):
            ferns.append((x,y,rng.uniform(0,360),rng.choice('abcd'),rng.uniform(.8,1.45)))
    for x,y,yaw,which,*scale in ferns:
        props.append(_place(bpy,source('fern_02',f'fern_02_{which}'),f'Fern at ({x:.2f}, {y:.2f})',(x,y,float(height(x,y,c))),yaw,scale[0] if scale else 1.,.015))
    for i in range(9):
        y=rng.uniform(6.,20.);half=.72*(y+2.2);x=rng.uniform(-half,half)
        props.append(_place(bpy,source('pine_sapling_small','pine_sapling_small_'+'abc'[i%3]),f'Sapling at ({x:.2f}, {y:.2f})',(x,y,float(height(x,y,c))),rng.uniform(0,360),rng.uniform(.9,1.5),.02))
    props.append(build_canopy(bpy))
    return props

def build_canopy(bpy,z=17.):
    """Pine crowns overhead, out of frame: an 80 m sheet of leaf clumps that
    only casts shadow (dappled sun on the floor) and shades part of the sky.
    Hidden from the camera and from reflections."""
    mesh=bpy.data.meshes.new('Pine crowns (shadow only)')
    mesh.from_pydata([(-40,-25,z),(40,-25,z),(40,55,z),(-40,55,z)],[],[(0,1,2,3)]);mesh.update()
    mat=bpy.data.materials.new('Pine crown clumps');mat.use_nodes=True;nodes,links=mat.node_tree.nodes,mat.node_tree.links
    out=nodes.get('Material Output');nodes.remove(nodes.get('Principled BSDF'))
    coord=nodes.new('ShaderNodeTexCoord')
    clumps=_ramp(nodes,links,_noise(nodes,links,coord.outputs['Object'],.30,7.,.66),.50,.54)
    leaves=nodes.new('ShaderNodeBsdfDiffuse');leaves.inputs['Color'].default_value=(.04,.06,.025,1)
    gap=nodes.new('ShaderNodeBsdfTransparent');mix=nodes.new('ShaderNodeMixShader')
    links.new(clumps,mix.inputs[0]);links.new(gap.outputs[0],mix.inputs[1]);links.new(leaves.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],out.inputs['Surface'])
    obj=bpy.data.objects.new('Pine crowns (shadow only)',mesh);bpy.context.scene.collection.objects.link(obj);obj.data.materials.append(mat)
    obj.visible_camera=False;obj.visible_glossy=False;obj.visible_transmission=False
    return obj

def scatter_stones(bpy,c,corridor,count=26,seed=517):
    """Small stones (scanned rocks scaled to 6-16 cm) along the far trail edge.

    Placement rejects any spot whose stone could come within the clearance of
    a ball centre of any case; the render-time check below verifies it exactly.
    """
    from terrain_geometry import height
    rocks=_import_gltf(bpy,'rock_moss_set_02');names=sorted(rocks)
    rng=random.Random(seed);placed=[];stones=[]
    ball=[(p[0],p[1]) for p in corridor]
    for _ in range(count*40):
        if len(placed)>=count:break
        x=rng.uniform(-4.2,4.0);y=rng.uniform(.75,2.2)
        size=rng.uniform(.06,.16)
        if min(math.hypot(x-bx,y-by) for bx,by in ball)<c['ball_radius']+CLEARANCE+size*.9+.03:continue
        if any(math.hypot(x-px,y-py)<.25 for px,py in placed):continue
        mesh=rocks[names[rng.randrange(len(names))]]
        dims=max(mesh.dimensions);scale=size/dims
        obj=_place(bpy,mesh,f'Stone at ({x:.2f}, {y:.2f})',(x,y,float(height(x,y,c))),rng.uniform(0,360),scale,sink=size*.25,tilt=(rng.uniform(-12,12),rng.uniform(-12,12)))
        # The rock scans are modelled around their own centre; drop each onto the ground.
        bottom=min((obj.matrix_world@v.co).z for v in obj.data.vertices)
        obj.location.z+=float(height(x,y,c))-size*.25-bottom
        placed.append((x,y));stones.append(obj)
    return stones

def load_corridor(frames):
    """Ball centres of all six published cases plus this case's frames."""
    points=[tuple(f['ball']['location']) for f in frames]
    if CORRIDOR.is_file():
        for case in json.loads(CORRIDOR.read_text(encoding='utf-8'))['cases'].values():points.extend(tuple(p) for p in case)
    return points

def check_props(bpy,scene,camera,props,corridor,radius):
    """Raise if a prop comes within CLEARANCE of the ball surface at any ball
    centre of any case, or hides a ball that is inside the frame."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from bpy_extras.object_utils import world_to_camera_view
    depsgraph=bpy.context.evaluated_depsgraph_get();trees=[]
    for obj in props:
        mesh=obj.evaluated_get(depsgraph).to_mesh();mw=obj.matrix_world
        trees.append((obj.name,BVHTree.FromPolygons([mw@v.co for v in mesh.vertices],[tuple(p.vertices) for p in mesh.polygons])))
        obj.evaluated_get(depsgraph).to_mesh_clear()
    worst=(1e9,None,None);origin=camera.matrix_world.translation;hidden=[]
    for p in corridor:
        centre=Vector(p)
        for name,tree in trees:
            hit=tree.find_nearest(centre)
            if hit[0] is not None and hit[3]-radius<worst[0]:worst=(hit[3]-radius,name,p)
        view=world_to_camera_view(scene,camera,centre)
        if 0<view.x<1 and 0<view.y<1 and view.z>0:
            ray=centre-origin;side=ray.cross(Vector((0,0,1))).normalized()*radius*.7;up=ray.cross(side).normalized()*radius*.7
            for target in (centre,centre+side,centre-side,centre+up,centre-up):
                d=target-origin;length=d.length;d.normalize()
                for name,tree in trees:
                    hit=tree.ray_cast(origin,d,length)
                    if hit[0] is not None:hidden.append((name,p));break
    print(f'[props] {len(props)} props, {len(corridor)} ball centres: closest prop {worst[1]} is {worst[0]*1000:.0f} mm from the ball surface',flush=True)
    if worst[0]<CLEARANCE:raise RuntimeError(f'Prop {worst[1]} comes within {worst[0]*1000:.1f} mm of the ball at {worst[2]}')
    if hidden:raise RuntimeError(f'Props hide the ball from the camera: {hidden[:5]}')
    return worst[0]
