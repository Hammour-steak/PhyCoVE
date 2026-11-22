"""Mechanism look: grounded-end coil, guide parts, walnut block, oak tabletop, keyed from native states.

appearance/realism.py builds on build() below; main() renders the bare mechanism look of one case."""
from pathlib import Path
import sys,os,json,hashlib,math,platform,argparse
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scene_common import *
# Reuse the checked metric furniture/asset loader of base_scene.py.
import base_scene as old
bpy,np,Vector,Matrix=old.bpy,old.np,old.Vector,old.Matrix
ASSET_MANIFEST=ASSETS/'walnut_look/manifest.json'

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def material(name,color,rough=.5,metal=0):return old.material(name,color,rough,metal)

def pbr(name,normal_strength=.35):
    manifest=json.loads(ASSET_MANIFEST.read_text(encoding='utf8'))
    mat=material('Mechanism scanned '+name,(.45,.3,.18));nodes,links=mat.node_tree.nodes,mat.node_tree.links
    bs=nodes.get('Principled BSDF');uv=nodes.new('ShaderNodeTexCoord')
    for row in manifest['files']:
        if row['asset']!=name:continue
        tex=nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(ASSETS/row['path']),check_existing=True)
        links.new(uv.outputs['UV'],tex.inputs['Vector'])
        if 'nor_gl' in row['path']:
            tex.image.colorspace_settings.name='Non-Color';normal=nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=normal_strength
            links.new(tex.outputs['Color'],normal.inputs['Color']);links.new(normal.outputs['Normal'],bs.inputs['Normal'])
        elif 'rough' in row['path']:
            tex.image.colorspace_settings.name='Non-Color';links.new(tex.outputs['Color'],bs.inputs['Roughness'])
        else:links.new(tex.outputs['Color'],bs.inputs['Base Color'])
    return mat

def wire_material():
    mat=material('Blued spring steel with drawn-wire finish',(.085,.105,.13),.31,.92)
    nodes,links=mat.node_tree.nodes,mat.node_tree.links;bs=nodes.get('Principled BSDF')
    uv=nodes.new('ShaderNodeTexCoord');stretch=nodes.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY';stretch.inputs[1].default_value=(500,35000,1)
    links.new(uv.outputs['UV'],stretch.inputs[0]);noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=1;noise.inputs['Detail'].default_value=2
    links.new(stretch.outputs['Vector'],noise.inputs['Vector'])
    ramp=nodes.new('ShaderNodeMapRange');ramp.inputs['From Min'].default_value=0;ramp.inputs['From Max'].default_value=1
    ramp.inputs['To Min'].default_value=.25;ramp.inputs['To Max'].default_value=.37
    links.new(noise.outputs['Fac'],ramp.inputs['Value']);links.new(ramp.outputs['Result'],bs.inputs['Roughness'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000001;bump.inputs['Strength'].default_value=.16
    links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs['Normal'],bs.inputs['Normal'])
    if 'Anisotropic IOR Level' in bs.inputs:bs.inputs['Anisotropic IOR Level'].default_value=.28
    return mat

def spring_vertices(contact_length,c):
    turns=c['spring_active_turns']+2;segments=turns*96;sides=32
    r=c['spring_wire_diameter_m']/2;radius=c['spring_mean_diameter_m']/2
    seat_length=contact_length-c['pusher_size_m'][0]
    pitch=(seat_length-2*c['spring_wire_diameter_m'])/c['spring_active_turns']
    def integral(z):return 0 if z<=0 else z-.5 if z>=1 else z**3-.5*z**4
    def smooth(z):return 0 if z<=0 else 1 if z>=1 else z*z*(3-2*z)
    vertices=[]
    for i in range(segments+1):
        t=i/segments*turns;theta=2*math.pi*t+.38
        blend_integral=.5*(integral((t-.75)/.5)-integral((t-(turns-1.25))/.5))
        x=c['spring_wire_diameter_m']*t+(pitch-c['spring_wire_diameter_m'])*blend_integral
        blend=smooth((t-.75)/.5)-smooth((t-(turns-1.25))/.5)
        dx=(c['spring_wire_diameter_m']+(pitch-c['spring_wire_diameter_m'])*blend)/(2*math.pi)
        center=Vector((c['spring_anchor_x_m']+x,radius*math.cos(theta),c['spring_axis_z_m']+radius*math.sin(theta)))
        tangent=Vector((dx,-radius*math.sin(theta),radius*math.cos(theta))).normalized()
        normal=Vector((0,math.cos(theta),math.sin(theta)));binormal=tangent.cross(normal).normalized()
        for j in range(sides):
            phase=2*math.pi*j/sides
            v=center+r*(math.cos(phase)*normal+math.sin(phase)*binormal)
            # Actual planar end lands; wire never protrudes through either seat.
            v.x=max(c['spring_anchor_x_m'],min(c['spring_anchor_x_m']+seat_length,v.x))
            vertices.append(tuple(v))
    return vertices

def make_coil(c,q):
    sides=32;turns=c['spring_active_turns']+2;segments=turns*96
    comp=c['spring_rest_length_m']-c['spring_initial_compression_m']
    vertices=spring_vertices(comp,c);faces=[]
    for i in range(segments):
        for j in range(sides):
            a=i*sides+j;b=i*sides+(j+1)%sides;faces.append((a,b,b+sides,a+sides))
    faces += [tuple(reversed(range(sides))),tuple(range(len(vertices)-sides,len(vertices)))]
    mesh=bpy.data.meshes.new('Smooth closed-and-ground spring wire');mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new('spring | ground-end steel coil',mesh);bpy.context.collection.objects.link(obj)
    mesh.materials.append(wire_material());mesh.materials.append(material('Ground end steel',(.34,.36,.39),.42,.94))
    uv=mesh.uv_layers.new();wire_length=spring_properties(c)['coil_mass_kg']/(math.pi*(c['spring_wire_diameter_m']/2)**2*c['spring_density_kg_m3'])
    for poly in mesh.polygons:
        poly.use_smooth=poly.index<len(faces)-2
        if poly.index<len(faces)-2:
            ring,j=divmod(poly.index,sides)
            coords=[(ring/segments*wire_length,j/sides*math.pi*c['spring_wire_diameter_m']),
                    (ring/segments*wire_length,(j+1)/sides*math.pi*c['spring_wire_diameter_m']),
                    ((ring+1)/segments*wire_length,(j+1)/sides*math.pi*c['spring_wire_diameter_m']),
                    ((ring+1)/segments*wire_length,j/sides*math.pi*c['spring_wire_diameter_m'])]
            for li,value in zip(poly.loop_indices,coords):uv.data[li].uv=value
            if abs(poly.normal.x)>.92 and (ring<90 or ring>segments-90):poly.material_index=1;poly.use_smooth=False
    obj.shape_key_add(name='Compressed steel coil');key=obj.shape_key_add(name='Natural steel coil')
    key.slider_min=-.05;key.slider_max=2.0
    for point,co in zip(key.data,spring_vertices(c['spring_rest_length_m'],c)):point.co=co
    for frame,value in enumerate(q,1):key.value=float(value/c['spring_initial_compression_m']);key.keyframe_insert('value',frame=frame)
    obj['wire_diameter_m']=c['spring_wire_diameter_m'];obj['mean_diameter_m']=c['spring_mean_diameter_m']
    obj['active_turns']=c['spring_active_turns'];obj['total_turns']=turns
    obj['end_finish']='Closed and ground, clipped seat lands; continuous end-pitch transitions'
    obj['kinematics']='Dominant axial mode driven solely by native slider displacement'
    return obj

def grain_uv(obj,period,offset=(.13,.27)):
    uv=obj.data.uv_layers.active or obj.data.uv_layers.new()
    for poly in obj.data.polygons:
        axis=max(range(3),key=lambda k:abs(poly.normal[k]))
        a,b=((1,2) if axis==0 else (2,0) if axis==1 else (1,0))
        for li in poly.loop_indices:
            co=obj.data.vertices[obj.data.loops[li].vertex_index].co
            uv.data[li].uv=(co[a]/period+offset[0],co[b]/period+offset[1])

def plywood_edge():
    mat=material('Birch plywood 17 plies, continuous machined edge',(.43,.30,.17),.64)
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get('Principled BSDF')
    tex=n.new('ShaderNodeTexCoord');xyz=n.new('ShaderNodeSeparateXYZ');l.new(tex.outputs['Object'],xyz.inputs[0])
    phase=n.new('ShaderNodeMath');phase.operation='MULTIPLY';phase.inputs[1].default_value=17/.025*math.pi
    l.new(xyz.outputs['Z'],phase.inputs[0]);noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=70;noise.inputs['Detail'].default_value=3
    l.new(tex.outputs['Object'],noise.inputs['Vector']);jitter=n.new('ShaderNodeMath');jitter.operation='MULTIPLY';jitter.inputs[1].default_value=.15;l.new(noise.outputs['Fac'],jitter.inputs[0])
    add=n.new('ShaderNodeMath');add.operation='ADD';l.new(phase.outputs[0],add.inputs[0]);l.new(jitter.outputs[0],add.inputs[1])
    sine=n.new('ShaderNodeMath');sine.operation='SINE';l.new(add.outputs[0],sine.inputs[0])
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=.05;ramp.color_ramp.elements[0].color=(.32,.205,.112,1)
    ramp.color_ramp.elements[1].position=.75;ramp.color_ramp.elements[1].color=(.51,.36,.218,1)
    l.new(sine.outputs[0],ramp.inputs[0]);l.new(ramp.outputs['Color'],bs.inputs['Base Color'])
    bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000018;bump.inputs['Strength'].default_value=.22
    l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],bs.inputs['Normal'])
    return mat

def set_material(obj,mat):obj.data.materials.clear();obj.data.materials.append(mat)

def walnut_material():
    mat=pbr('walnut_veneer_02',.50);mat.name='Oil-finished walnut, independent scanned wood'
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get('Principled BSDF')
    color=bs.inputs['Base Color'].links[0].from_socket
    oil=n.new('ShaderNodeMixRGB');oil.blend_type='MULTIPLY';oil.inputs[0].default_value=1
    oil.inputs[2].default_value=(.26,.24,.22,1);l.new(color,oil.inputs[1]);l.new(oil.outputs[0],bs.inputs['Base Color'])
    if 'Coat Weight' in bs.inputs:bs.inputs['Coat Weight'].default_value=.13
    if 'Coat Roughness' in bs.inputs:bs.inputs['Coat Roughness'].default_value=.34
    coord=n.new('ShaderNodeTexCoord');stretch=n.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY';stretch.inputs[1].default_value=(1,12,12)
    l.new(coord.outputs['Object'],stretch.inputs[0]);pores=n.new('ShaderNodeTexNoise');pores.inputs['Scale'].default_value=200;pores.inputs['Detail'].default_value=2
    l.new(stretch.outputs[0],pores.inputs['Vector']);bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000010;bump.inputs['Strength'].default_value=.15
    if bs.inputs['Normal'].is_linked:l.new(bs.inputs['Normal'].links[0].from_socket,bump.inputs['Normal'])
    l.new(pores.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal'])
    return mat


def walnut_uv(obj,period=1.0,offset=(.31,.17)):
    # Actual walnut grain follows image U. Long X grain is continuous around
    # the four longitudinal faces; the transverse faces use another material.
    uv=obj.data.uv_layers.active or obj.data.uv_layers.new()
    hy=max(abs(v.co.y) for v in obj.data.vertices);hz=max(abs(v.co.z) for v in obj.data.vertices)
    for poly in obj.data.polygons:
        for li in poly.loop_indices:
            co=obj.data.vertices[obj.data.loops[li].vertex_index].co
            if poly.normal.z>.9:v=co.y
            elif poly.normal.y>.9:v=hy+hz-co.z
            elif poly.normal.z<-.9:v=-2*hy-2*hz-co.y
            else:v=co.z-hy-hz
            uv.data[li].uv=(co.x/period+offset[0],v/period+offset[1])


def walnut_end_grain():
    mat=material('Walnut transverse growth rings and open vessels',(.13,.061,.026),.58)
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get('Principled BSDF')
    coord=n.new('ShaderNodeTexCoord');sep=n.new('ShaderNodeSeparateXYZ');l.new(coord.outputs['Object'],sep.inputs[0])
    squares=[]
    for axis,shift in [('Y',.083),('Z',.071)]:
        add=n.new('ShaderNodeMath');add.operation='ADD';add.inputs[1].default_value=shift;l.new(sep.outputs[axis],add.inputs[0])
        mul=n.new('ShaderNodeMath');mul.operation='MULTIPLY';l.new(add.outputs[0],mul.inputs[0]);l.new(add.outputs[0],mul.inputs[1]);squares.append(mul)
    add=n.new('ShaderNodeMath');add.operation='ADD';l.new(squares[0].outputs[0],add.inputs[0]);l.new(squares[1].outputs[0],add.inputs[1])
    radius=n.new('ShaderNodeMath');radius.operation='SQRT';l.new(add.outputs[0],radius.inputs[0])
    wave=n.new('ShaderNodeMath');wave.operation='MULTIPLY';wave.inputs[1].default_value=2*math.pi/.0031;l.new(radius.outputs[0],wave.inputs[0])
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=290;noise.inputs['Detail'].default_value=3;l.new(coord.outputs['Object'],noise.inputs['Vector'])
    distort=n.new('ShaderNodeMath');distort.operation='MULTIPLY';distort.inputs[1].default_value=1.3;l.new(noise.outputs['Fac'],distort.inputs[0])
    total=n.new('ShaderNodeMath');total.operation='ADD';l.new(wave.outputs[0],total.inputs[0]);l.new(distort.outputs[0],total.inputs[1])
    sine=n.new('ShaderNodeMath');sine.operation='SINE';l.new(total.outputs[0],sine.inputs[0])
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.115,.060,.030,1);ramp.color_ramp.elements[1].color=(.132,.069,.036,1)
    l.new(sine.outputs[0],ramp.inputs[0]);l.new(ramp.outputs[0],bs.inputs['Base Color'])
    transverse=n.new('ShaderNodeCombineXYZ');l.new(sep.outputs['Y'],transverse.inputs['X']);l.new(sep.outputs['Z'],transverse.inputs['Y'])
    pores=n.new('ShaderNodeTexVoronoi');pores.voronoi_dimensions='2D';pores.inputs['Scale'].default_value=3000;pores.feature='F1';l.new(transverse.outputs[0],pores.inputs['Vector'])
    cavity=n.new('ShaderNodeValToRGB');cavity.color_ramp.elements[0].position=.13;cavity.color_ramp.elements[0].color=(.35,.35,.35,1);cavity.color_ramp.elements[1].position=.23
    l.new(pores.outputs['Distance'],cavity.inputs[0]);shade=n.new('ShaderNodeMixRGB');shade.blend_type='MULTIPLY';shade.inputs[0].default_value=1
    l.new(ramp.outputs[0],shade.inputs[1]);l.new(cavity.outputs[0],shade.inputs[2]);l.new(shade.outputs[0],bs.inputs['Base Color'])
    bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000018;bump.inputs['Strength'].default_value=.27
    l.new(cavity.outputs[0],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal'])
    return mat


def dense_replay(c,states,motion):
    assert len(motion['time'])==961 and np.max(np.abs(motion['time'][::10][:FRAMES]-states['time']))<1e-10
    assert np.array_equal(motion['positions'][::10][:FRAMES],states['positions'])
    names=list(motion['body_names'])
    for name in names:
        obj=bpy.data.objects[name];obj.animation_data_clear();obj.rotation_mode='QUATERNION';index=names.index(name)
        for t,pos,quat in zip(motion['time'],motion['positions'][:,index],motion['quaternions'][:,index]):
            obj.location=pos+np.array([-.001,0,0]) if name=='pusher' else pos
            obj.rotation_quaternion=quat;frame=1+float(t)*FPS
            obj.keyframe_insert('location',frame=frame);obj.keyframe_insert('rotation_quaternion',frame=frame)
    if 'pusher' in names:
        q=motion['positions'][:,names.index('pusher'),0]-(c['spring_anchor_x_m']+c['spring_rest_length_m']-c['spring_initial_compression_m'])
        keys=bpy.data.objects['spring | ground-end steel coil'].data.shape_keys;keys.animation_data_clear();key=keys.key_blocks[1]
        sleeve=bpy.data.objects['Moving telescopic guide sleeve'];rod=bpy.data.objects['Moving inner guide rod']
        sleeve.animation_data_clear();rod.animation_data_clear()
        rod.location.z=c['spring_axis_z_m']
        for t,value in zip(motion['time'],q):
            frame=1+float(t)*FPS;key.value=float(value/c['spring_initial_compression_m']);key.keyframe_insert('value',frame=frame)
            sleeve.location.x=float(value*.5);sleeve.keyframe_insert('location',frame=frame)
            rod.location.x=-.2295+float(value);rod.keyframe_insert('location',frame=frame)


def build(c,states,motion,finish='blued'):
    old.make_coil=make_coil
    # Reuse the base-scene furniture importer as scaffolding only. Its temporary
    # lower board is removed before evaluation, audit, saving or rendering.
    scaffold=dict(c,lower_position_m=[.325,0,.0525],lower_size_m=[1.3,.31,.025])
    contract=old.build(scaffold,states)
    scene=bpy.context.scene
    delta=c['spring_axis_z_m']-.14
    for name in ['Backstop','Fixed hollow guide sleeve','Moving telescopic guide sleeve','Moving inner guide rod']:
        obj=bpy.data.objects.get(name)
        if obj is None:continue  # DELETE spring omits both moving guide parts.
        if 'sleeve' in name:
            for vertex in obj.data.vertices:vertex.co.z+=delta
            obj.data.update()
        else:obj.location.z+=delta
    for obj in bpy.data.objects:
        if obj.name.startswith(('Backstop fixing screw','Phillips slot')):obj.location.z+=delta
    oak=pbr('white_oak_veneer',.28);ply=old.pbr('plywood');edge=plywood_edge();cut=walnut_end_grain();walnut=walnut_material()
    # A satin clear finish suppresses a broad mirror-like tabletop flare.
    bs=oak.node_tree.nodes.get('Principled BSDF');n,l=oak.node_tree.nodes,oak.node_tree.links
    rough=bs.inputs['Roughness'];previous=rough.links[0].from_socket if rough.is_linked else None
    if previous:
        maximum=n.new('ShaderNodeMath');maximum.operation='MAXIMUM';maximum.inputs[1].default_value=.49;l.new(previous,maximum.inputs[0]);l.new(maximum.outputs[0],rough)
    for obj in list(bpy.data.objects):
        if ' laminated ' in obj.name or obj.name=='lower | fixed plywood board' or obj.name.startswith('Lower spacer'):
            bpy.data.objects.remove(obj,do_unlink=True)
    for i,pos in enumerate(c['platform_riser_centres_m']):
        obj=bpy.data.objects['Upper spacer '+str(i)]
        for point in obj.data.vertices:point.co.z*=c['platform_riser_size_m'][2]/.025
        obj.location=pos;obj.data.update()
    for name in ['upper | fixed plywood board']:
        obj=bpy.data.objects[name];obj.data.materials.clear();obj.data.materials.append(ply);obj.data.materials.append(edge)
        for poly in obj.data.polygons:poly.material_index=1 if abs(poly.normal.z)<.9 else 0
        for modifier in obj.modifiers:
            if modifier.type=='BEVEL':modifier.width=c['wood_edge_radius_m'];modifier.segments=4
    # Three actual joined oak planks, with sub-millimetre seams outside the
    # centre flight corridor. The native rigid desk has the same top at z=0.
    bpy.data.objects.remove(bpy.data.objects['Craft table'],do_unlink=True)
    tabletop=oak.copy();tabletop.name='Satin oak tabletop with microscopic finish wear'
    n,l=tabletop.node_tree.nodes,tabletop.node_tree.links;bs=n.get('Principled BSDF')
    if 'Coat Weight' in bs.inputs:bs.inputs['Coat Weight'].default_value=.06
    if 'Coat Roughness' in bs.inputs:bs.inputs['Coat Roughness'].default_value=.32
    tc=n.new('ShaderNodeTexCoord');wear=n.new('ShaderNodeTexNoise');wear.inputs['Scale'].default_value=1250;wear.inputs['Detail'].default_value=2
    l.new(tc.outputs['Object'],wear.inputs['Vector']);micro=n.new('ShaderNodeBump');micro.inputs['Distance'].default_value=.000004;micro.inputs['Strength'].default_value=.12
    if bs.inputs['Normal'].is_linked:l.new(bs.inputs['Normal'].links[0].from_socket,micro.inputs['Normal'])
    l.new(wear.outputs['Fac'],micro.inputs['Height']);l.new(micro.outputs['Normal'],bs.inputs['Normal'])
    table=bpy.data.objects.new('Craft table',None);bpy.context.collection.objects.link(table);table.location=c['table_position_m']
    bpy.context.view_layer.update()
    for i,(yy,offset) in enumerate(zip([-.3,0,.3],[(.17,.10),(.43,.38),(.71,.66)])):
        plank=old.cube('Tabletop plank '+str(i),(.28,yy,-.025),(1.8,.29965,.05),tabletop,.0006)
        grain_uv(plank,.5,offset);plank.parent=table;plank.matrix_parent_inverse=table.matrix_world.inverted()
    for name in ['block','obstacle']:
        obj=bpy.data.objects.get(name)
        if obj:
            obj.data.materials.clear();obj.data.materials.append(walnut);obj.data.materials.append(cut)
            walnut_uv(obj,1.0,(.31,.17) if name=='block' else (.57,.26))
            for poly in obj.data.polygons:poly.material_index=1 if abs(poly.normal.x)>.9 else 0
            for modifier in obj.modifiers:
                if modifier.type=='BEVEL':modifier.width=c['wood_edge_radius_m'];modifier.segments=4
    for obj in bpy.data.objects:
        if obj.name.startswith(('Upper spacer','Table leg')):set_material(obj,oak);grain_uv(obj,.5,(.48,.13))
    pusher=bpy.data.objects.get('pusher')
    satin=material('Satin machined aluminium',(.30,.32,.34),.43,.88)
    if pusher:
        for vertex in pusher.data.vertices:vertex.co.y*=.046/.042;vertex.co.z*=.042/.030
        pusher.data.update();set_material(pusher,satin)
        scene.frame_set(1);bpy.context.view_layer.update()
        collar=old.tube('Spring end retaining collar',-.200,-.197,.0205,.0189,satin)
        for vertex in collar.data.vertices:vertex.co.z+=delta
        collar.parent=pusher;collar.matrix_parent_inverse=pusher.matrix_world.inverted()
    if 'Moving inner guide rod' in bpy.data.objects:set_material(bpy.data.objects['Moving inner guide rod'],satin)
    if 'Moving telescopic guide sleeve' in bpy.data.objects:
        set_material(bpy.data.objects['Moving telescopic guide sleeve'],material('Machined steel sliding sleeve',(.29,.31,.34),.37,.94))
    sleeve=bpy.data.objects['Fixed hollow guide sleeve'];set_material(sleeve,material('Aged bronze sleeve',(.23,.145,.065),.43,.82))
    # Visible small fixing brackets, well outside the 64 mm wide block corridor.
    bracket=material('Matte mounting brackets',(.17,.18,.19),.49,.75)
    dark=material('Screw recesses',(.018,.019,.02),.53,.65)
    for yy in [-.045,.045]:
        old.cube('Fixing angle foot',(-.285,yy,.116+delta),(.040,.018,.002),bracket,.0004)
        old.cube('Fixing angle back',(-.302,yy,.128+delta),(.002,.018,.026),bracket,.0004)
        old.cylinder('Countersunk fixing screw',(-.271,yy,.1171+delta),.0032,.0006,satin,axis='Z')
        old.cube('Screw drive',(-.271,yy,.11745+delta),(.004,.00065,.00005),dark,.00005)
    # A metric ruler gives an honest scale cue on the household work surface.
    ruler=old.cube('20 cm steel ruler',(-.075,-.274,.0004),(.215,.020,.0008),satin,.00018)
    for i in range(201):
        length=.008 if i%10==0 else .0055 if i%5==0 else .0033
        old.cube('Ruler millimetre '+str(i),(-.175+i*.001,-.284+length/2,.000805),(.00020,length,.000006),dark,0)
    for i in [0,5,10,15,20]:
        curve=bpy.data.curves.new('Ruler centimetre numeral','FONT');curve.body=str(i);curve.size=.0032;curve.align_x='CENTER';curve.extrude=0
        obj=bpy.data.objects.new('Ruler label '+str(i),curve);bpy.context.collection.objects.link(obj)
        obj.location=(-.175+i*.01,-.274,.000806);curve.materials.append(dark)
    # Replace presentation lines with a small engineering sketch on real paper.
    for obj in list(bpy.data.objects):
        if obj.name.startswith('Sketch pencil line'):bpy.data.objects.remove(obj,do_unlink=True)
    ink=material('Graphite on paper',(.19,.185,.17),.92)
    paper=bpy.data.objects['Sketch sheet']
    for point in paper.data.vertices:point.co.z*=.00014/.0007
    paper.location.z=.00007;paper.data.update()
    for modifier in paper.modifiers:
        if modifier.type=='BEVEL':modifier.width=.00005
    def line(name,points,radius=.00015):
        curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D';curve.resolution_u=1;curve.bevel_depth=radius;curve.bevel_resolution=1
        spline=curve.splines.new('POLY');spline.points.add(len(points)-1)
        for p,co in zip(spline.points,points):p.co=(*co,1)
        o=bpy.data.objects.new(name,curve);bpy.context.collection.objects.link(o);curve.materials.append(ink)
        o.scale.z=.025;o.location.z=points[0][2]*(1-.025)
    z=.000145
    line('Sketched single platform',[(.475,.307,z),(.475,.315,z),(.555,.315,z),(.555,.307,z),(.475,.307,z)])
    line('Sketched desk',[(.465,.277,z),(.695,.277,z)])
    for xx in [.485,.540]:line('Sketched platform foot',[(xx,.307,z),(xx,.277,z)])
    line('Sketched block',[(.565,.287,z),(.565,.31,z),(.596,.31,z),(.596,.287,z)])
    pts=[(.477+i/95*.073,.337+.004*math.sin(i/95*math.pi*16),z) for i in range(96)]
    line('Sketched coil',pts)
    # Native world-direction lookup for the photographic environment, with a
    # broad matching window and lower fill to retain contact and edge shading.
    manifest=json.loads(ASSET_MANIFEST.read_text(encoding='utf8'))
    row=next(x for x in manifest['files'] if x['asset']=='artist_workshop')
    world=bpy.data.worlds.new('Photographed daylight workshop');world.use_nodes=True
    n,l=world.node_tree.nodes,world.node_tree.links;n.clear()
    env=n.new('ShaderNodeTexEnvironment');env.image=bpy.data.images.load(str(ASSETS/row['path']))
    bg=n.new('ShaderNodeBackground');bg.inputs['Strength'].default_value=.15;l.new(env.outputs['Color'],bg.inputs['Color'])
    output=n.new('ShaderNodeOutputWorld');l.new(bg.outputs[0],output.inputs[0]);scene.world=world
    key=bpy.data.objects['Large left window'];key.location=(-.55,-.85,1.10);old.aim(key,(.03,0,.055));key.data.shape='RECTANGLE';key.data.size=.72;key.data.size_y=.95;key.data.energy=75;key.data.color=(1,.965,.92)
    fill=bpy.data.objects['Soft far wall bounce'];fill.data.energy=3;fill.data.color=(.88,.93,1)
    wall=bpy.data.materials.get('Warm lime plaster')
    if wall:
        n,l=wall.node_tree.nodes,wall.node_tree.links;noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=700;noise.inputs['Detail'].default_value=2
        bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000035;bump.inputs['Strength'].default_value=.2
        l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],n.get('Principled BSDF').inputs['Normal'])
    camera=scene.camera;camera.location=(.56,-1.60,.56);old.aim(camera,(.16,0,.075));camera.data.lens=58
    camera.data.dof.focus_distance=(camera.location-Vector((.13,0,.11))).length;camera.data.dof.aperture_fstop=11
    scene.view_settings.exposure=-.10;scene.render.motion_blur_shutter=.12
    dense_replay(c,states,motion)
    for action in bpy.data.actions:
        for curve in action.fcurves:
            for point in curve.keyframe_points:point.interpolation='LINEAR'
    if finish=='satin':
        coil=bpy.data.objects.get('spring | ground-end steel coil')
        if coil:coil.data.materials[0].node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.22,.24,.27)
    scene.frame_set(1);bpy.context.view_layer.update()
    rod=bpy.data.objects.get('Moving inner guide rod')
    if rod:assert abs(rod.matrix_world.translation.z-c['spring_axis_z_m'])<1e-7
    if c.get('block_present',[1])[0]:assert abs(bpy.data.objects['block'].matrix_world.translation.z-c['block_position_m'][2])<1e-7
    assert 'lower | fixed plywood board' not in bpy.data.objects
    assert not any(o.name.startswith('Lower spacer') for o in bpy.data.objects)
    hit,point,normal,face,obj,matrix=scene.ray_cast(bpy.context.evaluated_depsgraph_get(),Vector((.42,.07,.06)),Vector((0,0,-1)))
    assert hit and abs(point.z)<1e-6 and obj.name.startswith('Tabletop plank'),(hit,tuple(point),obj.name if obj else None)
    geometry_audit={'single_raised_platform':True,'lower_board_removed':True,'lower_risers_removed':True,
        'receiving_surface':'table','receiving_surface_z_m':float(point.z),'ray_probe_object':obj.name,
        'platform_top_z_m':c['upper_position_m'][2]+c['upper_size_m'][2]/2,'direct_riser_height_m':c['platform_riser_size_m'][2],'table_plank_seam_m':.00035,
        'common_baseline_revision':True,'motion_fps':MOTION_FPS,
        'block_material':'independent oil-finished walnut scan','table_material':'white oak scan',
        'guide_recoil_with_captured_spring_end':True,'mechanism_axis_z_m':c['spring_axis_z_m'],
        'moving_rod_axis_verified':bool(rod is not None),'block_bottom_initial_z_m':c['block_position_m'][2]-c['block_size_m'][2]/2}
    contract.update(camera={'location':list(camera.location),'rotation_euler':list(camera.rotation_euler),'lens_mm':camera.data.lens},
        geometry_audit=geometry_audit,
        revision='mechanism_look',replacement_spring={'wire_diameter_m':c['spring_wire_diameter_m'],'mean_diameter_m':c['spring_mean_diameter_m'],
        'active_turns':c['spring_active_turns'],'tube_sides':32,'samples_per_turn':96,'steel_seat_length_free_m':c['steel_free_seat_length_m'],
        'finish':finish,'closed_ground_end_lands':True},lighting='Photographic Artist Workshop HDRI, native world direction, broad window and reduced fill')
    return contract

def main():
    """Mechanism look of one case: inputs from --native/<case>, frames and records to --out."""
    p=argparse.ArgumentParser();p.add_argument('--case',default='source',choices=list(CASES));p.add_argument('--native',type=Path,default=NATIVE)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--frames',nargs='+',type=int);p.add_argument('--samples',type=int,default=256)
    p.add_argument('--finish',choices=['blued','satin'],default='blued')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    native=a.native/a.case;c=load_physics(native/'resolved_physics.json');states=np.load(native/'states.npz');motion=np.load(native/'motion_states.npz')
    contract=build(c,states,motion,a.finish);scene=bpy.context.scene;scene.cycles.samples=a.samples
    scene.cycles.use_adaptive_sampling=True;scene.cycles.adaptive_threshold=.006
    scene.cycles.denoising_prefilter='ACCURATE'
    scene.render.resolution_x=WIDTH;scene.render.resolution_y=HEIGHT
    out=a.out;(out/'frames').mkdir(parents=True,exist_ok=True)
    save(out/'render_provenance.json',{'worker':platform.node(),'cuda_visible_devices':os.environ.get('CUDA_VISIBLE_DEVICES',''),'revision':'mechanism_look',
        'blender':bpy.app.version_string,'samples':a.samples,'resolution':[WIDTH,HEIGHT],'media_contract_id':MEDIA_CONTRACT['contract_id'],
        'assets_manifest_sha256':digest(ASSET_MANIFEST),
        **{key:digest(native/name) for name,key in [('states.npz','states_sha256'),('motion_states.npz','motion_states_sha256'),('model.xml','model_sha256'),('resolved_physics.json','resolved_physics_sha256')]},**contract})
    for f in a.frames or range(1,FRAMES+1):
        scene.frame_set(f);scene.render.filepath=str(out/'frames'/f'{f:04d}.png');bpy.ops.render.render(write_still=True)
        print('RENDER_FRAME',a.case,f,flush=True)

if __name__=='__main__':main()
