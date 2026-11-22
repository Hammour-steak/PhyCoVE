"""Metric, manufactured scanner and station environment; runs inside Blender."""
import bpy,math
from mathutils import Vector
from scene_paths import ASSETS

def material(name,col,rough=.45,metal=0):
    m=bpy.data.materials.new(name);m.use_nodes=True;p=m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value=(*col,1);p.inputs['Roughness'].default_value=rough;p.inputs['Metallic'].default_value=metal
    return m
def micro(m,scale=400,distance=.00003,strength=.2,stretch=(1,1,1),coordinates='Object'):
    n=m.node_tree.nodes;l=m.node_tree.links;p=n.get('Principled BSDF');co=n.new('ShaderNodeTexCoord');mult=n.new('ShaderNodeVectorMath');mult.operation='MULTIPLY';mult.inputs[1].default_value=stretch;l.new(co.outputs[coordinates],mult.inputs[0])
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=scale;noise.inputs['Detail'].default_value=3;l.new(mult.outputs[0],noise.inputs['Vector'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=strength;bump.inputs['Distance'].default_value=distance;l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],p.inputs['Normal'])
    return co,mult,noise
def cube(name,loc,size,mat,bevel=.003):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if mat:o.data.materials.append(mat)
    if bevel:
        b=o.modifiers.new('Manufactured edge radius','BEVEL');b.width=bevel;b.segments=3
        o.modifiers.new('Weighted surface normals','WEIGHTED_NORMAL')
    return o
def cylinder(name,loc,r,depth,mat,axis='Z'):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=r,depth=depth,location=loc);o=bpy.context.object;o.name=name
    if axis=='Y':o.rotation_euler[0]=math.pi/2
    if axis=='X':o.rotation_euler[1]=math.pi/2
    o.data.materials.append(mat);b=o.modifiers.new('Turned metal edge','BEVEL');b.width=.001;b.segments=2
    for p in o.data.polygons:p.use_smooth=True
    o.modifiers.new('Normals','WEIGHTED_NORMAL');return o
def image_material(name,path,emission=0):
    m=material(name,(1,1,1),.47);n=m.node_tree.nodes;l=m.node_tree.links;tex=n.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(path),check_existing=True);p=n.get('Principled BSDF');l.new(tex.outputs['Color'],p.inputs['Base Color'])
    if emission:l.new(tex.outputs['Color'],p.inputs['Emission Color']);p.inputs['Emission Strength'].default_value=emission
    return m
def placard(name,loc,size,image,emission=0,front='-Y'):
    m=image_material(name,ASSETS/'signage_labels'/image,emission)
    bpy.ops.mesh.primitive_plane_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=(size[0],size[1],0)
    o.rotation_euler=(math.pi/2,0,0) if front=='-Y' else (math.pi/2,0,math.pi/2)
    o.data.materials.append(m);return o
def area(name,loc,target,power,size,color=(1,1,1)):
    dat=bpy.data.lights.new(name,'AREA');dat.energy=power;dat.shape='RECTANGLE';dat.size=size;dat.size_y=size*.5;dat.color=color
    o=bpy.data.objects.new(name,dat);bpy.context.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()

def build(p):
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    cream=material('Warm grey fine powder-coat',(.44,.47,.47),.35,.15);micro(cream,1150,.000035,.18)
    dark=material('Dark graphite coated steel',(.048,.06,.065),.4,.25);micro(dark,900,.000025,.15)
    steel=material('Brushed satin stainless steel',(.55,.59,.60),.27,.88);micro(steel,800,.000025,.15,(1,12,1))
    anisotropic=steel.node_tree.nodes.get('Principled BSDF').inputs.get('Anisotropic IOR Level')
    if anisotropic is not None:anisotropic.default_value=.45
    rubber=material('Conveyor continuous rubber top cover',(.008,.010,.011),.90)
    rubber.node_tree.nodes.get('Principled BSDF').inputs['Specular IOR Level'].default_value=.12
    co,_,_=micro(rubber,560,.000075,.2,(.7,3,1));n=rubber.node_tree.nodes;l=rubber.node_tree.links
    mapping=n.new('ShaderNodeMapping');l.new(co.outputs['Object'],mapping.inputs['Vector'])
    for node in n:
        if node.type=='VECT_MATH':l.new(mapping.outputs['Vector'],node.inputs[0])
    seam=n.new('ShaderNodeTexWave');seam.wave_type='BANDS';seam.bands_direction='X';seam.inputs['Scale'].default_value=.38;seam.inputs['Distortion'].default_value=0;l.new(mapping.outputs['Vector'],seam.inputs['Vector'])
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=.988;ramp.color_ramp.elements[0].color=(.008,.010,.011,1);ramp.color_ramp.elements[1].position=.997;ramp.color_ramp.elements[1].color=(.014,.016,.017,1);l.new(seam.outputs['Color'],ramp.inputs[0]);l.new(ramp.outputs[0],n.get('Principled BSDF').inputs['Base Color'])
    # Only the belt material moves; its speed comes from the actual physical parameter.
    for f in (1,145):mapping.inputs['Location'].default_value[0]=-p['belt_speed_m_s']*(f-1)/24;mapping.inputs['Location'].keyframe_insert('default_value',frame=f)
    for c in rubber.node_tree.animation_data.action.fcurves:
        for k in c.keyframe_points:k.interpolation='LINEAR'
    orange=material('Muted safety orange powder coat',(.78,.19,.028),.38,.1)
    black=material('Deep tunnel liner',(.012,.016,.018),.75)
    # The belt surface is exactly z=0.75 m, matching the solver support plane.
    cube('Continuous moving belt',(.48,0,.745),(4.18,.55,.01),rubber,.006)
    for y in (-.303,.303):
        cube('Outfeed steel edge extrusion',(.55,y,.705),(4.32,.035,.075),steel,.004)
        cube('Dark edge seal',(.55,y*.95,.747),(4.24,.009,.009),dark,.002)
    for x in (-1.55,-.6,.45,1.2,2.55):
        cylinder('Conveyor steel roller',(x,0,.697),.045,.59,steel,'Y')
        cylinder('Roller axle',(x,0,.697),.012,.65,steel,'Y')
        for y in (-.32,.32):cube('Roller bearing block',(x,y,.694),(.10,.035,.10),dark,.006)
    for x in (-1.27,-.25,1.15,2.15):
        for y in (-.27,.27):
            cube('Conveyor support leg',(x,y,.35),(.045,.045,.65),steel,.004);cylinder('Levelling foot',(x,y,.004),.045,.018,dark)
            cylinder('Levelling threaded stem',(x,y,.023),.012,.035,steel)
        cube('Support crossbar',(x,0,.22),(.04,.57,.035),steel,.003)
    # Closed chassis underneath; open tunnel with independently manufactured covers.
    cube('Scanner lower cabinet',(-.78,0,.40),(1.59,.78,.59),cream,.008)
    for y in (-.35,.35):cube('Scanner side support plinth',(-.79,y,.727),(1.60,.075,.066),dark,.003)
    for y in (-.325,.325):cube('Tunnel side shielding cabinet',(-.79,y,.9085),(1.60,.13,.299),cream,.006)
    cube('Scanner upper shell',(-.79,0,1.138),(1.61,.78,.158),cream,.006)
    for y in (-.263,.263):cube('Tunnel interior liner',(-.79,y,.91),(1.57,.007,.30),black,.001)
    cube('Tunnel ceiling liner',(-.79,0,1.06),(1.57,.52,.008),black,.001)
    for y in (-.284,.284):cube('Front portal machined trim',(.018,y,.89175),(.055,.048,.3085),dark,.006)
    cube('Front top trim',(.018,0,1.075),(.055,.612,.055),dark,.006)
    cube('Curtain clamping rail',(.027,0,1.048),(.017,.52,.022),steel,.002)
    for y in (-.24,-.16,-.08,0,.08,.16,.24):cylinder('Clamp screw',(.038,y,1.049),.0035,.002,steel,'X')
    for y in (-.391,.391):
        cube('Side accent stripe',(-.78,y,1.015),(1.48,.003,.014),orange,.001)
        cube('Lower service panel seam',(-.78,math.copysign(.3905,y),.38),(1.36,.001,.0015),dark,0)
        for x in (-1.42,-.15):
            for z in (.22,.57,.89,1.15):cylinder('M4 service fastener',(x,math.copysign(.391,y),z),.0028,.0025,steel,'Y')
    for j in range(13):cube('Cabinet ventilation slot',(-1.20+j*.031,-.391,.55),(.015,.003,.065),dark,.003)
    for x in (-1.32,-.44):cube('Folded cover service joint',(x,-.391,.96),(.0012,.0015,.29),dark,0)
    placard('X-ray warning label',(-.40,-.392,.53),(.31,.096),'caution.png')
    # Mushroom stop button in a metal escutcheon, in view on the operator side.
    cylinder('Emergency-stop yellow collar',(-.12,-.397,.91),.023,.014,material('Stop collar yellow',(.94,.65,.05),.34),'Y')
    cylinder('Red emergency mushroom',(-.12,-.412,.91),.017,.027,material('Emergency red',(.65,.025,.015),.3),'Y')
    for x,col in ((-.24,(.04,.55,.18)),(-.32,(.55,.20,.025))):
        lamp=material('Status indicator',col,.26);pp=lamp.node_tree.nodes.get('Principled BSDF');pp.inputs['Emission Color'].default_value=(*col,1);pp.inputs['Emission Strength'].default_value=.3;cylinder('Status lamp',(x,-.392,.91),.006,.005,lamp,'Y')
    # A rear entrance curtain is already behind both initial bags; it is never crossed in this clip.
    for k in range(6):cube('Rear inlet shielding strip',(-1.59,-.255+(k+.5)*.085,.905),(.002,.084,.295),black,.001)
    cube('Rear curtain mounting rail',(-1.589,0,1.059),(.025,.56,.025),dark,.002)
    # Photo-derived granite floor, with real-world metre coordinates.
    floor=material('Poly Haven granite tile CC0',(.35,.36,.35),.38)
    n=floor.node_tree.nodes;l=floor.node_tree.links;co=n.new('ShaderNodeTexCoord');texs={}
    for role,key in (('diff','Base Color'),('rough','Roughness'),('nor_gl',None)):
        t=n.new('ShaderNodeTexImage');t.image=bpy.data.images.load(str(ASSETS/'granite_tile'/('granite_tile_'+role+'_4k.jpg')),check_existing=True);l.new(co.outputs['Object'],t.inputs['Vector']);texs[role]=t
        if role!='diff':t.image.colorspace_settings.name='Non-Color'
        if key:l.new(t.outputs['Color'],n.get('Principled BSDF').inputs[key])
    normal=n.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.3;l.new(texs['nor_gl'].outputs['Color'],normal.inputs['Color']);l.new(normal.outputs['Normal'],n.get('Principled BSDF').inputs['Normal'])
    cube('Granite station floor',(0,0,-.055),(18,18,.10),floor,0)
    wall=material('Large ceramic wall panels',(.63,.65,.64),.32);micro(wall,500,.00002,.12)
    cube('Station back wall',(0,3.1,1.58),(14,.15,3.17),wall,.01)
    for x in range(-6,7):cube('Wall panel joint',(x,3.024,1.58),(.002,.002,3.17),dark,0)
    for z in (.7,1.4,2.1,2.8):cube('Wall horizontal joint',(0,3.024,z),(14,.002,.0015),dark,0)
    for x in (-2.4,2.3):
        cube('Square station column',(x,1.85,1.58),(.42,.42,3.17),wall,.006)
        cube('Column steel skirting',(x,1.85,.115),(.432,.432,.24),steel,.003)
    # Queue barriers, restrained background props, floor contact shadows.
    strap=material('Queue barrier webbing',(.055,.105,.12),.8)
    for x in (-1.7,-.4,.9,2.2):
        cylinder('Queue post base',(x,1.15,.0075),.13,.025,steel);cylinder('Queue post',(x,1.15,.4575),.022,.90,steel);cylinder('Belt cassette',(x,1.15,.9175),.038,.09,dark)
    for x in (-1.05,.25,1.55):cube('Retractable barrier belt',(x,1.15,.9275),(1.25,.008,.055),strap,.001)
    cube('Station sign backing',(-.55,3.015,2.16),(2.31,.020,.369),dark,.003)
    placard('Station bilingual sign',(-.55,3.0045,2.16),(2.30,.359),'station_sign.png',.22)
    for x in (1.5,2.2,2.9):
        cube('Distant fare gate',(x,2.2,.51),(.31,1.0,1.03),steel,.025)
        cube('Fare gate top',(x,2.2,1.034),(.32,.98,.025),dark,.008)
    cube('Operator monitor base',(-1.13,.61,.0075),(.34,.25,.025),steel,.005)
    cube('Operator screen post',(-1.13,.61,.575),(.04,.04,1.16),steel,.004)
    cube('Monitor bezel',(-1.13,.60,1.29),(.47,.033,.31),dark,.013)
    placard('Inspection monitor',(-1.13,.583,1.29),(.437,.274),'monitor.png',.65)
    ceiling=material('Ceiling white',(.73,.75,.74),.55);cube('Ceiling',(0,0,3.23),(14,12,.13),ceiling,0)
    luminous=material('Ceiling diffusers',(.82,.87,.88),.4);pp=luminous.node_tree.nodes.get('Principled BSDF');pp.inputs['Emission Color'].default_value=(.82,.87,.88,1);pp.inputs['Emission Strength'].default_value=2.8
    for x in (-2,0,2):
        cube('Linear ceiling light housing',(x,.2,3.14),(.12,4.3,.055),dark,.004);cube('Linear ceiling diffuser',(x,.2,3.106),(.09,4.23,.008),luminous,.002)
    world=bpy.data.worlds.new('Enclosed station ambient');world.use_nodes=True;world.node_tree.nodes.get('Background').inputs['Color'].default_value=(.68,.74,.78,1);world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.16;bpy.context.scene.world=world
    area('Ceiling over scanner',(-.8,-.1,2.85),(-.5,0,.75),280,2.8,(.91,.96,1))
    area('Broad station fill',(1.5,-2.5,2.5),(0,0,.9),180,2.5,(1,.96,.91))
    area('Exit material edge',(.4,1.6,2.5),(0,0,.85),180,2.0,(.91,.96,1))
    area('Back concourse light',(-2,1.3,2.8),(-1,2,0),230,3,(1,.97,.92))
    dat=bpy.data.cameras.new('Fixed exit three-quarter camera');cam=bpy.data.objects.new('Camera',dat);bpy.context.collection.objects.link(cam)
    cam.location=(2.25,-2.80,1.60);target=Vector((-.25,0,1.17));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();dat.lens=44;dat.sensor_width=36
    dat.dof.use_dof=True;dat.dof.focus_distance=(Vector((.1,0,.88))-cam.location).length;dat.dof.aperture_fstop=10;bpy.context.scene.camera=cam
    from checkpoint_details import enrich
    detail=enrich(p)
    from detail_refinement import refine
    refinement=refine(p)
    return {'detail':detail,'refinement':refinement,'belt_mapping':mapping,'materials':{'steel':steel,'dark':dark},'camera_target':list(target)}
