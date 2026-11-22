"""A science-museum hands-on gallery around the energy-track exhibit; appearance only.

Physics lives in physics/track_geometry.py. Every surface the ball or the carton can
touch (track bed, the inner faces and tops of the cheeks, tabletop, legs, floor) is
drawn from the same numbers; everything else built here is visual only and is checked
against the trajectories by render_u_track_ball.py (clearance and line of sight).

The look: a plywood exhibit in a modern science museum. The track is a CNC-cut birch
plywood channel (18 mm cheeks, a 24 mm formed bed with a linoleum running surface)
standing on plywood ribs on a heavy exhibit table (stacked-ply edge, furniture
linoleum top). The gallery has board-marked concrete walls, a terrazzo floor and a
tall steel-framed window; light comes from the sun and sky through that window and
from the gallery's ceiling track spots and recessed linear lights.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

import sys
sys.path.insert(0, str(_PCVE_ROOT / 'scripts'))
import math
from pcve_blender_compat import set_shader_input, shader_socket
from pcve_assets import asset as _pcve_asset
ASSETS=_pcve_asset('')/'polyhaven'/'u_track_ball'

ENVIRONMENT_THEME='science_museum_gallery'

# Poly Haven's authored real-world sizes of the scans (api.polyhaven.com/info).
TILE_M={'terrazzo_tiles':2.0,'wood_textured_concrete':1.8,'linoleum_brown':2.0,'plywood':.5}
# Baltic birch: 13 plies in an 18 mm sheet.
PLY_M=.018/13

# Objects tagged with this custom property are visual-only props: the renderer
# checks them against every ball and carton pose of the clip.
PROP_TAG='pcve_visual_prop'

def tag_prop(obj):
    obj[PROP_TAG]=True
    return obj

def material(bpy,name,color,metal=0,roughness=.5):
    mat=bpy.data.materials.new(name);mat.diffuse_color=(*color,1);mat.use_nodes=True
    shader=mat.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=(*color,1);shader.inputs['Metallic'].default_value=metal;shader.inputs['Roughness'].default_value=roughness
    return mat

def textured_material(bpy,name,color,roughness=.5,metal=0,scale=160,bump_distance=.00012):
    mat=material(bpy,name,color,metal,roughness);nodes=mat.node_tree.nodes;links=mat.node_tree.links;shader=nodes.get('Principled BSDF')
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=scale;noise.inputs['Detail'].default_value=2
    rough=nodes.new('ShaderNodeMapRange');rough.inputs['From Min'].default_value=0;rough.inputs['From Max'].default_value=1
    rough.inputs['To Min'].default_value=roughness*.85;rough.inputs['To Max'].default_value=min(.95,roughness*1.15)
    links.new(noise.outputs['Fac'],rough.inputs[0]);links.new(rough.outputs[0],shader.inputs['Roughness'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12;bump.inputs['Distance'].default_value=bump_distance
    links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],shader.inputs['Normal']);return mat

def box(bpy,name,location,size,mat,pitch=0,bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location);obj=bpy.context.object;obj.name=name;obj.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);obj.rotation_euler[1]=pitch;obj.data.materials.append(mat)
    if bevel:
        mod=obj.modifiers.new('Manufactured edge','BEVEL');mod.width=bevel;mod.segments=3;obj.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
    return obj

def mesh_object(bpy,name,vertices,faces,mats,smooth=False):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj)
    for mat in mats:obj.data.materials.append(mat)
    for poly in mesh.polygons:poly.use_smooth=smooth
    return obj

def aim(obj,point):
    from mathutils import Vector
    obj.rotation_euler=(Vector(point)-obj.location).to_track_quat('-Z','Y').to_euler()

# ---------------------------------------------------------------- scanned surfaces

def _coords(nodes,links,space,tile):
    """Metric texture coordinates divided by the scan's real size."""
    mapping=nodes.new('ShaderNodeMapping');mapping.inputs['Scale'].default_value=(1/tile,)*3
    if space=='world':
        src=nodes.new('ShaderNodeNewGeometry');links.new(src.outputs['Position'],mapping.inputs['Vector'])
    elif space=='uv':
        src=nodes.new('ShaderNodeUVMap');links.new(src.outputs['UV'],mapping.inputs['Vector'])
    else:
        src=nodes.new('ShaderNodeTexCoord');links.new(src.outputs['Object'],mapping.inputs['Vector'])
    return mapping

def _scan(bpy,nodes,links,stem,kind,vector,colour,box_projection):
    node=nodes.new('ShaderNodeTexImage');path=ASSETS/f'{stem}_{kind}_2k.jpg'
    if not path.is_file():raise FileNotFoundError(f'Missing scanned texture {path}; run scripts/download_assets.py --scene u_track_ball')
    node.image=bpy.data.images.load(str(path),check_existing=True)
    if not colour:node.image.colorspace_settings.name='Non-Color'
    if box_projection:node.projection='BOX';node.projection_blend=.25
    links.new(vector,node.inputs['Vector']);return node

def scan_material(bpy,name,stem,space='world',tint=None,saturation=1.,value=1.,rough_range=None,normal_strength=1.,coat=0.,coat_roughness=.2,specular=None,box_projection=True,grain_turn=False,flatten=0.,drift=0.):
    """A Poly Haven scan at its authored size, with its own roughness and normal maps.

    tint/saturation/value recolour the albedo while keeping every speck and seam
    of the scan (a furniture linoleum comes in many colours from one mill).
    grain_turn turns the scan a quarter turn (the plywood scan's grain runs along
    the image's v, our parts are unwrapped with their length along u); flatten
    pulls the albedo towards its mean (a quieter veneer than the scanned sheet);
    drift adds a slow +-drift tonal wander over half a metre or so, the handling
    and light-fade of a real surface, so a large panel is never one flat value.
    """
    mat=material(bpy,name,(.5,.5,.5));nodes=mat.node_tree.nodes;links=mat.node_tree.links;shader=nodes.get('Principled BSDF')
    mapping=_coords(nodes,links,space,TILE_M[stem])
    if grain_turn:mapping.inputs['Rotation'].default_value[2]=math.pi/2
    vector=mapping.outputs['Vector']
    colour=_scan(bpy,nodes,links,stem,'diff',vector,True,box_projection).outputs['Color']
    if flatten:
        mean=nodes.new('ShaderNodeMix');mean.data_type='RGBA';mean.inputs['Factor'].default_value=flatten
        links.new(colour,mean.inputs['A']);mean.inputs['B'].default_value=(.42,.30,.19,1);colour=mean.outputs['Result']
    if saturation!=1. or value!=1.:
        hsv=nodes.new('ShaderNodeHueSaturation');hsv.inputs['Saturation'].default_value=saturation;hsv.inputs['Value'].default_value=value
        links.new(colour,hsv.inputs['Color']);colour=hsv.outputs['Color']
    if tint is not None:
        mix=nodes.new('ShaderNodeMix');mix.data_type='RGBA';mix.blend_type='MULTIPLY';mix.inputs['Factor'].default_value=1
        links.new(colour,mix.inputs['A']);mix.inputs['B'].default_value=(*tint,1);colour=mix.outputs['Result']
    wander=None
    if drift:
        wander=nodes.new('ShaderNodeTexNoise');wander.inputs['Scale'].default_value=1.6;wander.inputs['Detail'].default_value=3
        links.new(_coords(nodes,links,space,1.).outputs['Vector'],wander.inputs['Vector'])
        gain=nodes.new('ShaderNodeMapRange');gain.inputs['To Min'].default_value=1-drift;gain.inputs['To Max'].default_value=1+drift
        links.new(wander.outputs['Fac'],gain.inputs['Value'])
        scale=nodes.new('ShaderNodeVectorMath');scale.operation='SCALE'
        links.new(colour,scale.inputs[0]);links.new(gain.outputs['Result'],scale.inputs['Scale']);colour=scale.outputs['Vector']
    links.new(colour,shader.inputs['Base Color'])
    rough=_scan(bpy,nodes,links,stem,'rough',vector,False,box_projection).outputs['Color']
    if rough_range:
        remap=nodes.new('ShaderNodeMapRange');remap.inputs['To Min'].default_value,remap.inputs['To Max'].default_value=rough_range
        links.new(rough,remap.inputs['Value']);rough=remap.outputs['Result']
    if wander is not None:
        # Handled areas polish up a little: roughness follows the same wander.
        smear=nodes.new('ShaderNodeMath');smear.operation='MULTIPLY_ADD';smear.inputs[1].default_value=.12
        links.new(wander.outputs['Fac'],smear.inputs[0]);links.new(rough,smear.inputs[2]);rough=smear.outputs[0]
    links.new(rough,shader.inputs['Roughness'])
    normal=nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=normal_strength
    links.new(_scan(bpy,nodes,links,stem,'nor_gl',vector,False,box_projection).outputs['Color'],normal.inputs['Color'])
    links.new(normal.outputs['Normal'],shader.inputs['Normal'])
    if coat:
        set_shader_input(shader,'Coat Weight',coat);set_shader_input(shader,'Coat Roughness',coat_roughness)
        links.new(normal.outputs['Normal'],shader_socket(shader,'Coat Normal'))
    if specular is not None:set_shader_input(shader,'Specular IOR Level',specular)
    return mat

def birch_face(bpy,name='Lacquered birch plywood face',space='uv'):
    # The scan is a warm, strongly figured softwood face; rotary-cut birch is paler,
    # greyer and much quieter, with the grain along the part.
    return scan_material(bpy,name,'plywood',space,tint=(1.0,.94,.86),saturation=.62,value=1.32,rough_range=(.36,.52),normal_strength=.45,coat=.18,coat_roughness=.3,grain_turn=True,flatten=.45,drift=.05)

def ply_edge(bpy,name='Birch plywood edge, clear lacquer'):
    """Sawn plywood edge: alternating long- and cross-grain plies with glue lines.

    Reads the per-vertex attribute ply_t (metres across the sheet thickness) that
    the mesh builders write, so the plies run parallel to the sheet faces however
    the part is oriented or bent.
    """
    mat=material(bpy,name,(.55,.42,.28),roughness=.5);nodes=mat.node_tree.nodes;links=mat.node_tree.links;shader=nodes.get('Principled BSDF')
    attr=nodes.new('ShaderNodeAttribute');attr.attribute_name='ply_t'
    def math_node(op,a,b=None):
        node=nodes.new('ShaderNodeMath');node.operation=op
        if isinstance(a,(int,float)):node.inputs[0].default_value=a
        else:links.new(a,node.inputs[0])
        if b is not None:
            if isinstance(b,(int,float)):node.inputs[1].default_value=b
            else:links.new(b,node.inputs[1])
        return node.outputs[0]
    p=math_node('DIVIDE',attr.outputs['Fac'],PLY_M)
    odd=math_node('FLOORED_MODULO',math_node('FLOOR',p),2.)
    frac=math_node('FRACT',p)
    glue=nodes.new('ShaderNodeMapRange');glue.inputs['From Min'].default_value=0.;glue.inputs['From Max'].default_value=.11
    glue.inputs['To Min'].default_value=1.;glue.inputs['To Max'].default_value=0.;links.new(frac,glue.inputs['Value'])
    tone=nodes.new('ShaderNodeMix');tone.data_type='RGBA';links.new(odd,tone.inputs['Factor'])
    tone.inputs['A'].default_value=(.62,.50,.35,1);tone.inputs['B'].default_value=(.50,.38,.25,1)
    lines=nodes.new('ShaderNodeMix');lines.data_type='RGBA';links.new(glue.outputs['Result'],lines.inputs['Factor'])
    links.new(tone.outputs['Result'],lines.inputs['A']);lines.inputs['B'].default_value=(.20,.13,.07,1)
    # Saw marks and the odd darker veneer: slow noise along the part.
    coord=nodes.new('ShaderNodeTexCoord');noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=40;noise.inputs['Detail'].default_value=4
    links.new(coord.outputs['Object'],noise.inputs['Vector'])
    vary=nodes.new('ShaderNodeMix');vary.data_type='RGBA';vary.blend_type='MULTIPLY';vary.inputs['Factor'].default_value=.35
    links.new(lines.outputs['Result'],vary.inputs['A']);links.new(noise.outputs['Color'],vary.inputs['B'])
    links.new(vary.outputs['Result'],shader.inputs['Base Color'])
    rough=nodes.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.45;rough.inputs['To Max'].default_value=.7
    links.new(odd,rough.inputs['Value']);links.new(rough.outputs['Result'],shader.inputs['Roughness'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.25;bump.inputs['Distance'].default_value=.00015
    links.new(glue.outputs['Result'],bump.inputs['Height']);links.new(bump.outputs['Normal'],shader.inputs['Normal'])
    set_shader_input(shader,'Coat Weight',.12);set_shader_input(shader,'Coat Roughness',.35)
    return mat

def set_ply_t(obj,values):
    """Store the across-thickness coordinate (metres) of every vertex for ply_edge."""
    attr=obj.data.attributes.new('ply_t','FLOAT','POINT')
    for i,value in enumerate(values):attr.data[i].value=value

def plate(bpy,name,location,size,face_mat,edge_mat,axis,bevel=.0012):
    """A plywood part: veneer on the two faces normal to axis, plies on its edges."""
    obj=box(bpy,name,location,size,face_mat);obj.data.materials.append(edge_mat)
    k='xyz'.index(axis)
    for poly in obj.data.polygons:poly.material_index=0 if abs(poly.normal[k])>.5 else 1
    set_ply_t(obj,[v.co[k]+size[k]/2 for v in obj.data.vertices])
    _uv_box(obj,TILE_M['plywood'])
    if bevel:
        mod=obj.modifiers.new('Sanded arris','BEVEL');mod.width=bevel;mod.segments=2;obj.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
    return obj

def _uv_box(obj,tile):
    """Planar UVs per face from its dominant axis, grain along the longest edge."""
    mesh=obj.data;uv=mesh.uv_layers.new(name='UVMap')
    dims=[max(v.co[i] for v in mesh.vertices)-min(v.co[i] for v in mesh.vertices) for i in range(3)]
    for poly in mesh.polygons:
        n=[abs(c) for c in poly.normal];k=n.index(max(n));axes=[i for i in range(3) if i!=k]
        if dims[axes[1]]>dims[axes[0]]:axes.reverse()
        for li in poly.loop_indices:
            co=mesh.vertices[mesh.loops[li].vertex_index].co
            uv.data[li].uv=(co[axes[0]],co[axes[1]])

# ---------------------------------------------------------------- the moving bodies

def turned_walnut(bpy,name='Turned walnut ball, oiled'):
    """A lathe-turned black walnut ball: end-grain rings at two poles, long grain between.

    Rings around the object's X axis give exactly that on a sphere; the ball's own
    rotation then shows in the grain as it rolls. 90 mm and 0.25 kg is a density of
    655 kg/m3; walnut is about 640 kg/m3. Deep chocolate heartwood with darker
    latewood lines and a hand-rubbed oil finish that carries a clear highlight, so the
    ball stands out against the pale birch ply and the olive linoleum.
    """
    mat=material(bpy,name,(.06,.032,.018),roughness=.30);nodes=mat.node_tree.nodes;links=mat.node_tree.links;shader=nodes.get('Principled BSDF')
    coord=nodes.new('ShaderNodeTexCoord')
    wave=nodes.new('ShaderNodeTexWave');wave.wave_type='RINGS';wave.rings_direction='X';wave.wave_profile='SAW'
    wave.inputs['Scale'].default_value=70;wave.inputs['Distortion'].default_value=4.0;wave.inputs['Detail'].default_value=3;wave.inputs['Detail Scale'].default_value=1.4
    links.new(coord.outputs['Object'],wave.inputs['Vector'])
    ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.interpolation='EASE'
    ramp.color_ramp.elements[0].position=.30;ramp.color_ramp.elements[0].color=(.085,.047,.026,1)
    ramp.color_ramp.elements[1].position=.92;ramp.color_ramp.elements[1].color=(.030,.016,.010,1)
    links.new(wave.outputs['Fac'],ramp.inputs['Fac'])
    # Walnut heartwood wanders between warm brown and a cooler purple-grey.
    hue=nodes.new('ShaderNodeTexNoise');hue.inputs['Scale'].default_value=30;hue.inputs['Detail'].default_value=2
    links.new(coord.outputs['Object'],hue.inputs['Vector'])
    cast=nodes.new('ShaderNodeMix');cast.data_type='RGBA';links.new(hue.outputs['Fac'],cast.inputs['Factor'])
    cast.inputs['A'].default_value=(1.15,1.0,.92,1);cast.inputs['B'].default_value=(.90,.88,.95,1)
    tone=nodes.new('ShaderNodeMix');tone.data_type='RGBA';tone.blend_type='MULTIPLY';tone.inputs['Factor'].default_value=1
    links.new(ramp.outputs['Color'],tone.inputs['A']);links.new(cast.outputs['Result'],tone.inputs['B'])
    flecks=nodes.new('ShaderNodeTexNoise');flecks.inputs['Scale'].default_value=900;flecks.inputs['Detail'].default_value=2
    links.new(coord.outputs['Object'],flecks.inputs['Vector'])
    mix=nodes.new('ShaderNodeMix');mix.data_type='RGBA';mix.blend_type='MULTIPLY';mix.inputs['Factor'].default_value=.3
    links.new(tone.outputs['Result'],mix.inputs['A']);links.new(flecks.outputs['Color'],mix.inputs['B'])
    links.new(mix.outputs['Result'],shader.inputs['Base Color'])
    # Open pores along the latewood: the oil sits glossier on the denser bands.
    rough=nodes.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.24;rough.inputs['To Max'].default_value=.38
    links.new(wave.outputs['Fac'],rough.inputs['Value']);links.new(rough.outputs['Result'],shader.inputs['Roughness'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.10;bump.inputs['Distance'].default_value=.0002
    links.new(wave.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs['Normal'],shader.inputs['Normal'])
    set_shader_input(shader,'Coat Weight',.45);set_shader_input(shader,'Coat Roughness',.12)
    return mat

def kraft_board(bpy,name='Kraft corrugated board'):
    """Unbleached kraft liner over B-flute: fibre mottling plus the faint flute ribs."""
    mat=textured_material(bpy,name,(.36,.22,.11),roughness=.86,scale=260,bump_distance=.00012)
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;shader=nodes.get('Principled BSDF')
    coord=nodes.new('ShaderNodeTexCoord')
    mottle=nodes.new('ShaderNodeTexNoise');mottle.inputs['Scale'].default_value=18;mottle.inputs['Detail'].default_value=5
    links.new(coord.outputs['Object'],mottle.inputs['Vector'])
    ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.29,.175,.085,1);ramp.color_ramp.elements[1].color=(.42,.27,.14,1)
    links.new(mottle.outputs['Fac'],ramp.inputs['Fac']);links.new(ramp.outputs['Color'],shader.inputs['Base Color'])
    flutes=nodes.new('ShaderNodeTexWave');flutes.wave_type='BANDS';flutes.bands_direction='Z';flutes.inputs['Scale'].default_value=37
    links.new(coord.outputs['Object'],flutes.inputs['Vector'])
    old=shader.inputs['Normal'].links[0].from_node
    rib=nodes.new('ShaderNodeBump');rib.inputs['Strength'].default_value=.10;rib.inputs['Distance'].default_value=.0003
    links.new(flutes.outputs['Fac'],rib.inputs['Height']);links.new(old.outputs['Normal'],rib.inputs['Normal']);links.new(rib.outputs['Normal'],shader.inputs['Normal'])
    return mat

# ---------------------------------------------------------------- the gallery

def window_glass(bpy):
    """6 mm float glass as a Fresnel mirror over a see-through layer (no refraction
    to go black at grazing angles); camera rays stay camera rays through it."""
    mat=bpy.data.materials.new('Clear float glass');mat.use_nodes=True
    nodes,links=mat.node_tree.nodes,mat.node_tree.links
    for node in [n for n in nodes if n.type!='OUTPUT_MATERIAL']:nodes.remove(node)
    clear=nodes.new('ShaderNodeBsdfTransparent');clear.inputs['Color'].default_value=(.93,.96,.95,1)
    mirror=nodes.new('ShaderNodeBsdfGlossy');mirror.inputs['Roughness'].default_value=0.
    fresnel=nodes.new('ShaderNodeFresnel');fresnel.inputs['IOR'].default_value=1.52
    pane=nodes.new('ShaderNodeMixShader');links.new(fresnel.outputs['Fac'],pane.inputs['Fac'])
    links.new(clear.outputs['BSDF'],pane.inputs[1]);links.new(mirror.outputs['BSDF'],pane.inputs[2])
    links.new(pane.outputs['Shader'],nodes['Material Output'].inputs['Surface'])
    return mat

def emitter(bpy,name,strength,color=(1,1,1)):
    mat=bpy.data.materials.new(name);mat.use_nodes=True;nodes,links=mat.node_tree.nodes,mat.node_tree.links
    for node in [n for n in nodes if n.type!='OUTPUT_MATERIAL']:nodes.remove(node)
    em=nodes.new('ShaderNodeEmission');em.inputs['Color'].default_value=(*color,1);em.inputs['Strength'].default_value=strength
    links.new(em.outputs['Emission'],nodes['Material Output'].inputs['Surface']);return mat

# Gallery shell (metres): the back wall's inner face, the left wall's, the ceiling.
BACK_Y=1.95;LEFT_X=-3.0;CEILING_Z=3.6;RIGHT_X=4.6;FRONT_Y=-6.2
WINDOW=(-2.72,-.82,.62,2.92)  # x0,x1,z0,z1 of the opening in the back wall

def build_gallery(bpy):
    concrete=scan_material(bpy,'Board-marked concrete','wood_textured_concrete','world',saturation=.8,value=1.05,rough_range=(.72,.95),normal_strength=1.2,drift=.06)
    terrazzo=scan_material(bpy,'Polished terrazzo tiles','terrazzo_tiles','world',saturation=.75,rough_range=(.12,.42),normal_strength=.5,specular=.5,drift=.05)
    ceiling=material(bpy,'Ceiling white paint',(.72,.72,.70),roughness=.9)
    steel=material(bpy,'Dark bronze anodised window frame',(.045,.040,.034),metal=.8,roughness=.38)
    ext=lambda n,c,s,m:tag_prop(box(bpy,n,c,s,m))
    # The floor is the simulator's ground plane (top at z=0): collision, not a prop.
    box(bpy,'Terrazzo floor',[.7,-2.1,-.05],[RIGHT_X-LEFT_X+.6,BACK_Y-FRONT_Y+.6,.1],terrazzo)
    x0,x1,z0,z1=WINDOW;t=.25;yc=BACK_Y+t/2;H=CEILING_Z
    # The window sits in a real hole: the reveal shows the wall's thickness.
    ext('Back wall left of window',[(LEFT_X-.25+x0)/2,yc,H/2],[x0-(LEFT_X-.25),t,H],concrete)
    ext('Back wall right of window',[(x1+RIGHT_X+.25)/2,yc,H/2],[RIGHT_X+.25-x1,t,H],concrete)
    ext('Back wall below window',[(x0+x1)/2,yc,z0/2],[x1-x0,t,z0],concrete)
    ext('Back wall above window',[(x0+x1)/2,yc,(z1+H)/2],[x1-x0,t,H-z1],concrete)
    ext('Left wall',[LEFT_X-.125,(FRONT_Y+BACK_Y)/2,H/2],[.25,BACK_Y-FRONT_Y+.5,H],concrete)
    ext('Right wall',[RIGHT_X+.125,(FRONT_Y+BACK_Y)/2,H/2],[.25,BACK_Y-FRONT_Y+.5,H],concrete)
    ext('Front wall',[(LEFT_X+RIGHT_X)/2,FRONT_Y-.125,H/2],[RIGHT_X-LEFT_X+.5,.25,H],concrete)
    ext('Ceiling slab',[(LEFT_X+RIGHT_X)/2,(FRONT_Y+BACK_Y)/2,H+.1],[RIGHT_X-LEFT_X+.5,BACK_Y-FRONT_Y+.5,.2],ceiling)
    # Steel-framed glazing set mid-depth in the opening, one mullion and one transom.
    gy=BACK_Y+.11;bar=.06;depth=.09
    ext('Window head',[(x0+x1)/2,gy,z1-bar/2],[x1-x0,depth,bar],steel)
    ext('Window sill rail',[(x0+x1)/2,gy,z0+bar/2],[x1-x0,depth,bar],steel)
    for x in (x0+bar/2,x1-bar/2,(x0+x1)/2):ext('Window jamb or mullion',[x,gy,(z0+z1)/2],[bar if x!=(x0+x1)/2 else .05,depth,z1-z0-2*bar],steel)
    ext('Window transom',[(x0+x1)/2,gy,z0+.62*(z1-z0)],[x1-x0-2*bar,depth*.8,.05],steel)
    pane=ext('Window glass',[(x0+x1)/2,gy,(z0+z1)/2],[x1-x0-.02,.008,z1-z0-.02],window_glass(bpy))
    pane.visible_shadow=False
    ext('Concrete sill',[(x0+x1)/2,BACK_Y+.03,z0-.012],[x1-x0+.04,.10,.024],concrete)
    # Outside: the ground blocks the sky from below for the light rays; the camera
    # looks through it to the photograph (see daylight()).
    ground=ext('Ground outside',[0,20,-.4],[60,30,.2],material(bpy,'Sunlit paving outside',(.30,.29,.26),roughness=.9))
    ground.visible_camera=False
    return dict(concrete=concrete,steel=steel)

def exhibit_graphics(bpy):
    """A dibond exhibit panel on the back wall and an angled label on the table."""
    from mathutils import Vector
    board=textured_material(bpy,'Printed dibond panel, matt laminate',(.80,.79,.76),roughness=.62,scale=400,bump_distance=.00002)
    header=material(bpy,'Panel header print, deep blue',(.020,.060,.140),roughness=.6)
    ink=material(bpy,'Panel print ink',(.025,.028,.034),roughness=.6)
    white=material(bpy,'Panel reversed-out white',(.80,.80,.78),roughness=.6)
    accent=material(bpy,'Panel accent orange',(.75,.25,.04),roughness=.6)
    alu=material(bpy,'Brushed aluminium stand-off',(.6,.6,.6),metal=1,roughness=.3)
    cx,cz,w,h=.80,1.47,1.10,.80;face=BACK_Y-.025
    tag_prop(box(bpy,'Exhibit panel',[cx,face+.003,cz],[w,.006,h],board,bevel=.001))
    tag_prop(box(bpy,'Exhibit panel header band',[cx,face-.0002,cz+h/2-.08],[w,.0004,.16],header))
    for sx in (-1,1):
        for sz in (-1,1):
            bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.012,depth=.025,location=[cx+sx*(w/2-.04),face+.012,cz+sz*(h/2-.04)],rotation=[math.pi/2,0,0])
            tag_prop(bpy.context.object).data.materials.append(alu)
    def text(body,loc,size,mat,align='LEFT'):
        bpy.ops.object.text_add(location=loc,rotation=[math.pi/2,0,0]);obj=bpy.context.object
        obj.data.body=body;obj.data.size=size;obj.data.align_x=align;obj.data.extrude=0;obj.data.materials.append(mat)
        return tag_prop(obj)
    left=cx-w/2+.07;fy=face-.0006
    text('ENERGY TRACK',[left,fy,cz+h/2-.105],.072,white)
    text('How high can the ball climb?',[left,fy,cz+h/2-.225],.036,ink)
    lines=['Let the ball go from the top of the long side.',
           'Falling, it trades height for speed; climbing,',
           'it trades the speed back for height.',
           'Friction takes a little on every run, so it',
           'never quite gets back to where it started.']
    for i,line in enumerate(lines):text(line,[left,fy,cz+h/2-.295-i*.036],.022,ink)
    # The diagram: the track's own profile, scaled, with the ball at the release point.
    curve=bpy.data.curves.new('Panel diagram profile','CURVE');curve.dimensions='3D';curve.bevel_depth=.0035
    spline=curve.splines.new('POLY');pts=[]
    for i in range(41):
        x=-.9+1.65*i/40;z=(.56 if x<0 else .2)*(x/(.9 if x<0 else .75))**2
        pts.append((x,z))
    spline.points.add(len(pts)-1)
    gx,gz,scale=cx+.24,cz-.33,.19
    for p,(x,z) in zip(spline.points,pts):p.co=(gx+x*scale,fy-.001,gz+z*scale,1)
    diag=bpy.data.objects.new('Panel diagram profile',curve);bpy.context.scene.collection.objects.link(diag);curve.materials.append(header);tag_prop(diag)
    bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=.016,depth=.001,location=[gx-.84*scale,fy-.0015,gz+.488*scale+.017],rotation=[math.pi/2,0,0])
    tag_prop(bpy.context.object).data.materials.append(accent)
    text('h',[gx-.92*scale-.03,fy,gz+.2*scale],.03,ink)
    return board

def table_label(bpy,c,ply_face,ply_edges):
    """An angled exhibit label at the front-left corner of the table, far from the run."""
    top=c['table_height'];x,y=-1.08,-.40
    run,rise=.20,.06
    verts=[(x-.13,y-run/2,top),(x+.13,y-run/2,top),(x+.13,y+run/2,top),(x-.13,y+run/2,top),(x-.13,y-run/2,top+.012),(x+.13,y-run/2,top+.012),(x+.13,y+run/2,top+.012+rise),(x-.13,y+run/2,top+.012+rise)]
    faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,4,7,3),(1,2,6,5)]
    obj=tag_prop(mesh_object(bpy,'Exhibit label block',verts,faces,[ply_face,ply_edges]))
    for poly in obj.data.polygons:poly.material_index=1 if abs(poly.normal.x)>.5 else 0
    set_ply_t(obj,[v[0]-(x-.13) for v in verts]);_uv_box(obj,.5)
    slope=math.atan2(rise,run)
    print_mat=material(bpy,'Label print',(.80,.79,.76),roughness=.55);ink=material(bpy,'Label ink',(.02,.025,.03),roughness=.6)
    centre=(x,y,top+.012+rise/2+.0008)
    plaque=tag_prop(box(bpy,'Label print face',centre,[.24,math.hypot(run,rise)-.02,.0012],print_mat));plaque.rotation_euler=(slope,0,0)
    for i,(body,size) in enumerate((('ENERGY TRACK',.016),('Place the ball at the top',.0085),('of the long side and let go.',.0085))):
        bpy.ops.object.text_add(location=(0,0,0));t=bpy.context.object;t.data.body=body;t.data.size=size;t.data.align_x='CENTER';t.data.materials.append(ink)
        t.parent=plaque;t.location=(0,.045-i*.028-(.006 if i else 0),.0007);tag_prop(t)
    return obj

def exhibit_table(bpy,c,ply_face,ply_edges):
    """The simulator's worktable: furniture linoleum on a 90 mm stack of five 18 mm
    birch-ply sheets, on black square-tube legs. Top face and legs are the physics."""
    from track_geometry import table_parts
    lino=scan_material(bpy,'Olive furniture linoleum','linoleum_brown','world',tint=(.50,.62,.50),saturation=.40,value=.98,rough_range=(.42,.62),normal_strength=.5,specular=.45,drift=.07)
    leg_mat=textured_material(bpy,'Black powder-coated steel',(.025,.026,.027),roughness=.5,metal=.3,scale=300,bump_distance=.00003)
    for part in table_parts(c):
        if part['kind']=='wood' and part['name']=='Oak worktable':
            top=box(bpy,'Exhibit table',part['location'],part['size'],lino);top.data.materials.append(ply_edges);top.data.materials.append(ply_face)
            for poly in top.data.polygons:poly.material_index=0 if poly.normal.z>.5 else (2 if poly.normal.z<-.5 else 1)
            set_ply_t(top,[v.co.z+part['size'][2]/2 for v in top.data.vertices]);_uv_box(top,.5)
            mod=top.modifiers.new('Sanded arris','BEVEL');mod.width=.002;mod.segments=2;top.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
        else:
            box(bpy,part['name'],part['location'],part['size'],leg_mat,bevel=.004)
    for y in (-.43,.43):tag_prop(box(bpy,'Steel lower stretcher',[.4,y,.16],[2.73,.04,.04],leg_mat,bevel=.003))
    for x in (-1.,1.8):tag_prop(box(bpy,'Steel end stretcher',[x,0,.16],[.04,.82,.04],leg_mat,bevel=.003))
    return lino

# ---------------------------------------------------------------- light

# Sun through the back window: it travels towards -y (into the room) and +x.
SUN_ELEVATION_DEG=32.
SUN_HEADING_DEG=-115.
# golden_gate_hills: open grassland with hills on the horizon, nothing near enough
# to look magnified in the pane. Its sun sits at azimuth WINDOW_VIEW_SUN_AZIMUTH_DEG
# in the photograph's own frame (measured from the brightest pixel of the 4k file);
# the photograph is turned so that its sun stands where the lamp is.
WINDOW_VIEW='golden_gate_hills_4k.hdr'
WINDOW_VIEW_SUN_AZIMUTH_DEG=0.
WINDOW_VIEW_STRENGTH=1.4

def daylight(bpy):
    from mathutils import Vector
    el,heading=math.radians(SUN_ELEVATION_DEG),math.radians(SUN_HEADING_DEG)
    travel=Vector((math.cos(el)*math.cos(heading),math.cos(el)*math.sin(heading),-math.sin(el)))
    data=bpy.data.lights.new('Afternoon sun','SUN');data.energy=4.0;data.angle=math.radians(.53);data.color=(1.,.955,.90)
    sun=bpy.data.objects.new('Afternoon sun',data);bpy.context.collection.objects.link(sun)
    sun.location=Vector((-1.8,BACK_Y,1.8))-6*travel;aim(sun,sun.location+travel)
    scene=bpy.context.scene;scene.world=bpy.data.worlds.new('Afternoon sky');scene.world.use_nodes=True
    nodes,links=scene.world.node_tree.nodes,scene.world.node_tree.links
    sky=nodes.new('ShaderNodeTexSky');sky.sky_type='NISHITA';sky.sun_disc=False;sky.sun_elevation=el
    sky.sun_rotation=math.atan2(-travel.x,-travel.y);sky.air_density,sky.dust_density=1.,2.
    lighting=nodes['Background'];links.new(sky.outputs['Color'],lighting.inputs['Color']);lighting.inputs['Strength'].default_value=.5
    coord=nodes.new('ShaderNodeTexCoord');turn=nodes.new('ShaderNodeMapping');turn.vector_type='VECTOR'
    towards=-travel
    turn.inputs['Rotation'].default_value=(0,0,math.radians(WINDOW_VIEW_SUN_AZIMUTH_DEG)-math.atan2(towards.y,towards.x))
    photo=nodes.new('ShaderNodeTexEnvironment');path=ASSETS/WINDOW_VIEW
    if not path.is_file():raise FileNotFoundError(f'Missing window view {path}')
    photo.image=bpy.data.images.load(str(path),check_existing=True)
    links.new(coord.outputs['Generated'],turn.inputs['Vector']);links.new(turn.outputs['Vector'],photo.inputs['Vector'])
    view=nodes.new('ShaderNodeBackground');view.inputs['Strength'].default_value=WINDOW_VIEW_STRENGTH;links.new(photo.outputs['Color'],view.inputs['Color'])
    camera_ray=nodes.new('ShaderNodeLightPath');mix=nodes.new('ShaderNodeMixShader')
    links.new(camera_ray.outputs['Is Camera Ray'],mix.inputs['Fac']);links.new(lighting.outputs['Background'],mix.inputs[1]);links.new(view.outputs['Background'],mix.inputs[2])
    links.new(mix.outputs['Shader'],nodes['World Output'].inputs['Surface'])
    # Portal across the opening so Cycles samples the sky through the hole.
    x0,x1,z0,z1=WINDOW;portal=bpy.data.lights.new('Window sky portal','AREA');portal.shape='RECTANGLE';portal.size,portal.size_y=x1-x0,z1-z0;portal.cycles.is_portal=True
    obj=bpy.data.objects.new('Window sky portal',portal);bpy.context.collection.objects.link(obj)
    obj.location=((x0+x1)/2,BACK_Y+.26,(z0+z1)/2);aim(obj,(obj.location.x,BACK_Y-1,obj.location.z))
    return sun

def gallery_lights(bpy,steel):
    """Ceiling track spots on the exhibit and recessed linear lights, all with fixtures."""
    from mathutils import Vector
    black=material(bpy,'Matt black luminaire',(.02,.02,.02),roughness=.55)
    track_y,track_z=-1.15,CEILING_Z-.03
    tag_prop(box(bpy,'Ceiling lighting track',[.4,track_y,track_z],[4.2,.035,.03],black))
    lens=emitter(bpy,'Spot lens glow',8.,(1.,.86,.70))
    for x,target in ((-1.1,(-.55,0,1.05)),(-.2,(.05,0,.9)),(.7,(.7,0,.95)),(1.6,(1.35,0,.8))):
        head=Vector((x,track_y,track_z-.16))
        stem=tag_prop(box(bpy,'Spot stem',[x,track_y,track_z-.07],[.02,.02,.11],black))
        bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=.045,depth=.16,location=head);can=tag_prop(bpy.context.object);can.name='Track spot head';can.data.materials.append(black);aim(can,target)
        data=bpy.data.lights.new('Track spot','SPOT');data.energy=320;data.spot_size=math.radians(30);data.spot_blend=.75;data.shadow_soft_size=.025;data.color=(1.,.86,.70)
        spot=bpy.data.objects.new('Track spot',data);bpy.context.collection.objects.link(spot)
        direction=(Vector(target)-head).normalized();spot.location=head+direction*.085;aim(spot,target)
        bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=.034,depth=.002,location=head+direction*.081);disc=tag_prop(bpy.context.object);disc.name='Spot lens';disc.data.materials.append(lens);aim(disc,target)
        disc.visible_shadow=False
    diffuser=emitter(bpy,'Linear light diffuser',6.,(1.,.95,.88))
    for x,y in ((-1.4,-.2),(.9,-.2),(-1.4,1.2),(.9,1.2)):
        tag_prop(box(bpy,'Recessed linear light housing',[x,y,CEILING_Z-.004],[1.24,.10,.008],black))
        d=tag_prop(box(bpy,'Recessed linear light diffuser',[x,y,CEILING_Z-.0085],[1.2,.075,.001],diffuser));d.visible_shadow=False
        data=bpy.data.lights.new('Linear light','AREA');data.shape='RECTANGLE';data.size,data.size_y=1.2,.075;data.energy=28;data.color=(1.,.95,.88)
        lamp=bpy.data.objects.new('Linear light',data);bpy.context.collection.objects.link(lamp);lamp.location=(x,y,CEILING_Z-.012)

def configure_lighting(bpy,scene,steel=None):
    daylight(bpy);gallery_lights(bpy,steel)

def build_room(bpy,c):
    """The gallery, the exhibit table and its graphics. Returns shared materials."""
    shell=build_gallery(bpy)
    ply_face=birch_face(bpy);ply_edges=ply_edge(bpy)
    exhibit_table(bpy,c,ply_face,ply_edges)
    exhibit_graphics(bpy);table_label(bpy,c,ply_face,ply_edges)
    return dict(shell,ply_face=ply_face,ply_edges=ply_edges)
