"""Original SI geometry. Dynamic poses and helix length come only from solver cache."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import scene_asset
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
import math
import random
import hashlib
import bpy
from pathlib import Path
from mathutils import Vector, Euler, Matrix
from scene_config import road_points

ASSETS=scene_asset(Path(__file__).resolve().parents[1], 'assets/realism')
LOOK={}

def material(name, color, rough=.5, metal=0):
    m=bpy.data.materials.new(name);m.diffuse_color=color;m.use_nodes=True
    p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=color
    p.inputs['Roughness'].default_value=rough;p.inputs['Metallic'].default_value=metal
    return m

def empty(name):
    o=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(o);return o

def pbr(name,asset,resolution,width,roughness,normal_strength,tint=(1,1,1,1)):
    m=material(name,(.5,.4,.25,1));n=m.node_tree.nodes;l=m.node_tree.links;p=n.get('Principled BSDF')
    uv=n.new('ShaderNodeTexCoord');scale=n.new('ShaderNodeVectorMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=(1/width,1/width,1);l.new(uv.outputs['UV'],scale.inputs[0])
    if asset=='white_maple_veneer':
        # The maple scan grain runs horizontally; metric UV V follows the part's long axis.
        sep=n.new('ShaderNodeSeparateXYZ');combine=n.new('ShaderNodeCombineXYZ');l.new(uv.outputs['UV'],sep.inputs[0]);l.new(sep.outputs['Y'],combine.inputs['X']);l.new(sep.outputs['X'],combine.inputs['Y']);l.new(combine.outputs[0],scale.inputs[0])
    textures={}
    for channel in ['diff','rough','nor_gl']:
        t=n.new('ShaderNodeTexImage');t.image=bpy.data.images.load(str(ASSETS/asset/f'{asset}_{channel}_{resolution}.jpg'),check_existing=True)
        t.image.colorspace_settings.name='sRGB' if channel=='diff' else 'Non-Color';t.extension='REPEAT';l.new(scale.outputs[0],t.inputs['Vector']);textures[channel]=t
    if asset=='cotton_jersey':
        # This scan is non-square and the published dimension is its height.
        im=textures['diff'].image;scale.inputs[1].default_value=(im.size[1]/(width*im.size[0]),1/width,1)
    mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1.;mix.inputs[2].default_value=tint
    l.new(textures['diff'].outputs['Color'],mix.inputs[1]);l.new(mix.outputs[0],p.inputs['Base Color'])
    remap=n.new('ShaderNodeMapRange');remap.inputs['To Min'].default_value=roughness[0];remap.inputs['To Max'].default_value=roughness[1]
    l.new(textures['rough'].outputs['Color'],remap.inputs[0]);l.new(remap.outputs[0],p.inputs['Roughness'])
    normal=n.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=normal_strength;l.new(textures['nor_gl'].outputs['Color'],normal.inputs['Color']);l.new(normal.outputs[0],p.inputs['Normal'])
    return m

def wood(name,ref,light,dark,scale=(4,240,18)):
    m=pbr(name,'white_maple_veneer','2k',LOOK.get('wood_texture_width_m',1.0),LOOK.get('wood_roughness_range',[.23,.38]),LOOK.get('wood_normal_strength',.16),LOOK.get('road_wood_tint' if 'road' in name.lower() else 'support_wood_tint',(.82,.70,.49,1)))
    p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Coat Weight'].default_value=LOOK['surface_finish']['wood_coat_weight'];p.inputs['Coat Roughness'].default_value=LOOK['surface_finish']['wood_coat_roughness']
    finish_variation(m,65,.14)
    return m

def micro_surface(mat,scale,roughness,depth=.000008,variation=.08):
    n=mat.node_tree.nodes;l=mat.node_tree.links;p=n.get('Principled BSDF');tc=n.new('ShaderNodeTexCoord')
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=scale;noise.inputs['Detail'].default_value=2;l.new(tc.outputs['Object'],noise.inputs['Vector'])
    r=n.new('ShaderNodeMapRange');r.inputs['To Min'].default_value=roughness*(1-variation);r.inputs['To Max'].default_value=roughness*(1+variation)
    l.new(noise.outputs['Fac'],r.inputs[0]);l.new(r.outputs[0],p.inputs['Roughness'])
    bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=depth;bump.inputs['Strength'].default_value=.2;l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],p.inputs['Normal'])

def finish_variation(mat,scale,amount):
    # Metric object-space variation in a thin finish, with no displacement.
    n=mat.node_tree.nodes;l=mat.node_tree.links;p=n.get('Principled BSDF')
    original=p.inputs['Roughness'].links[0].from_socket if p.inputs['Roughness'].is_linked else None
    base=p.inputs['Roughness'].default_value
    tc=n.new('ShaderNodeTexCoord');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=scale;noise.inputs['Detail'].default_value=3;noise.inputs['Roughness'].default_value=.65
    l.new(tc.outputs['Object'],noise.inputs['Vector'])
    remap=n.new('ShaderNodeMapRange');remap.inputs['To Min'].default_value=1-amount;remap.inputs['To Max'].default_value=1+amount;l.new(noise.outputs['Fac'],remap.inputs[0])
    multiply=n.new('ShaderNodeMath');multiply.operation='MULTIPLY';multiply.inputs[0].default_value=base
    if original:l.new(original,multiply.inputs[0])
    l.new(remap.outputs[0],multiply.inputs[1]);l.new(multiply.outputs[0],p.inputs['Roughness'])

def handled_clear_finish(mat,strength):
    # CC0 surface-imperfection mask changes reflection only, never base colour.
    n=mat.node_tree.nodes;l=mat.node_tree.links;p=n.get('Principled BSDF')
    tc=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeVectorMath');mapping.operation='SCALE';mapping.inputs[3].default_value=1/.18;l.new(tc.outputs['Object'],mapping.inputs[0])
    tex=n.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(ASSETS/'fingerprints001/Fingerprints001_1K-JPG_Roughness.jpg'),check_existing=True);tex.image.colorspace_settings.name='Non-Color';tex.projection='BOX';tex.projection_blend=.12;l.new(mapping.outputs[0],tex.inputs['Vector'])
    weight=n.new('ShaderNodeMath');weight.operation='MULTIPLY';weight.inputs[1].default_value=strength;l.new(tex.outputs['Color'],weight.inputs[0])
    add=n.new('ShaderNodeMath');add.operation='ADD'
    if p.inputs['Roughness'].is_linked:l.new(p.inputs['Roughness'].links[0].from_socket,add.inputs[0])
    else:add.inputs[0].default_value=p.inputs['Roughness'].default_value
    l.new(weight.outputs[0],add.inputs[1]);l.new(add.outputs[0],p.inputs['Roughness'])

def faint_road_wear(mat):
    # Sparse, low-opacity rubber burnishing on the static wooden wheel paths.
    n=mat.node_tree.nodes;l=mat.node_tree.links;p=n.get('Principled BSDF');base=p.inputs['Base Color'].links[0].from_socket
    tc=n.new('ShaderNodeTexCoord');sep=n.new('ShaderNodeSeparateXYZ');l.new(tc.outputs['Object'],sep.inputs[0])
    bands=[]
    for yy in [-.038,.038]:
        sub=n.new('ShaderNodeMath');sub.operation='SUBTRACT';sub.inputs[1].default_value=yy;l.new(sep.outputs['Y'],sub.inputs[0])
        ab=n.new('ShaderNodeMath');ab.operation='ABSOLUTE';l.new(sub.outputs[0],ab.inputs[0])
        remap=n.new('ShaderNodeMapRange');remap.clamp=True;remap.inputs['From Min'].default_value=.0006;remap.inputs['From Max'].default_value=.004;remap.inputs['To Min'].default_value=1;remap.inputs['To Max'].default_value=0;l.new(ab.outputs[0],remap.inputs[0]);bands.append(remap.outputs[0])
    band=n.new('ShaderNodeMath');band.operation='MAXIMUM';l.new(bands[0],band.inputs[0]);l.new(bands[1],band.inputs[1])
    scale=n.new('ShaderNodeVectorMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=(25,440,50);l.new(tc.outputs['Object'],scale.inputs[0])
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=1;noise.inputs['Detail'].default_value=2;l.new(scale.outputs[0],noise.inputs['Vector'])
    mask=n.new('ShaderNodeMapRange');mask.clamp=True;mask.inputs['From Min'].default_value=.48;mask.inputs['From Max'].default_value=.74;mask.inputs['To Min'].default_value=0;mask.inputs['To Max'].default_value=LOOK['surface_finish']['road_wear_opacity'];l.new(noise.outputs['Fac'],mask.inputs[0])
    mul=n.new('ShaderNodeMath');mul.operation='MULTIPLY';l.new(band.outputs[0],mul.inputs[0]);l.new(mask.outputs[0],mul.inputs[1])
    mix=n.new('ShaderNodeMixRGB');mix.inputs[2].default_value=(.24,.22,.18,1);l.new(mul.outputs[0],mix.inputs[0]);l.new(base,mix.inputs[1]);l.new(mix.outputs[0],p.inputs['Base Color'])

def grounded_group(name,objects,pivot,rotation,base):
    group=empty(name);group.location=pivot
    bpy.context.view_layer.update()
    for ob in objects:
        world=ob.matrix_world.copy();ob.parent=group;ob.matrix_world=world
    group.rotation_euler=rotation;bpy.context.view_layer.update()
    low=min((ob.matrix_world@Vector(v)).z for ob in objects if ob.type in ['MESH','FONT','CURVE'] for v in ob.bound_box)
    group.location.z+=base-low;bpy.context.view_layer.update()
    return group

def wheel_flare(name,xc,side,car,mat):
    # A closed injection-moulded flare covers the exposed tire shoulder.
    # Kept inside the original 143 mm bumper-to-bumper envelope.
    profile=[(.02235,.0310),(.02235,.0404),(.0230,.0434),(.0249,.0427),(.02515,.0405),(.0248,.0310)]
    steps=80;verts=[]
    for radius,yy in profile:
        for i in range(steps+1):
            angle=math.pi*i/steps
            verts.append((xc+radius*math.cos(angle),side*yy,radius*math.sin(angle)))
    faces=[];stride=steps+1
    for j in range(len(profile)):
        for i in range(steps):faces.append((j*stride+i,j*stride+i+1,((j+1)%len(profile))*stride+i+1,((j+1)%len(profile))*stride+i))
    faces.extend([tuple(j*stride for j in reversed(range(len(profile)))),tuple(j*stride+steps for j in range(len(profile)))])
    ob=mesh(name,verts,faces,mat);ob.parent=car;closed_normals(ob)
    for face in ob.data.polygons:face.use_smooth=True
    bevel=ob.modifiers.new('0.20 mm moulded flare lip','BEVEL');bevel.width=.0002;bevel.segments=2
    ob.modifiers.new('Flare face normals','WEIGHTED_NORMAL')
    return ob

def metric_uv(obj):
    uv=obj.data.uv_layers.active or obj.data.uv_layers.new(name='Metres')
    dimensions=[max(v.co[i] for v in obj.data.vertices)-min(v.co[i] for v in obj.data.vertices) for i in range(3)];longaxis=max(range(3),key=lambda i:dimensions[i])
    phase=int(hashlib.sha256(obj.name.encode()).hexdigest()[:8],16)/0xffffffff
    offset=(phase*1.73,phase*.91)
    for poly in obj.data.polygons:
        normalaxis=max(range(3),key=lambda i:abs(poly.normal[i]));tangents=[i for i in range(3) if i!=normalaxis]
        grain=longaxis if longaxis in tangents else tangents[-1];cross=next(i for i in tangents if i!=grain)
        for li in poly.loop_indices:
            co=obj.data.vertices[obj.data.loops[li].vertex_index].co;uv.data[li].uv=(co[cross]+offset[0],co[grain]+offset[1])

def box(name,pos,size,mat,bevel=.0006,rotation=None):
    bpy.ops.mesh.primitive_cube_add(size=1,location=pos);o=bpy.context.object;o.name=name;o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    metric_uv(o)
    if rotation:o.rotation_euler=rotation
    o.data.materials.append(mat)
    if bevel:
        mod=o.modifiers.new('small manufactured edge','BEVEL');mod.width=bevel;mod.segments=3
        o.modifiers.new('face normals','WEIGHTED_NORMAL')
    return o

def cylinder(name,pos,r,depth,mat,axis='Y',bevel=.00015,vertices=48):
    rot={'Y':(math.pi/2,0,0),'X':(0,math.pi/2,0),'Z':(0,0,0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=r,depth=depth,location=pos,rotation=rot)
    o=bpy.context.object;o.name=name;o.data.materials.append(mat)
    if bevel:
        mod=o.modifiers.new('edge round','BEVEL');mod.width=bevel;mod.segments=2
    for poly in o.data.polygons:poly.use_smooth=True
    o.modifiers.new('face normals','WEIGHTED_NORMAL');return o

def parent(o,p,pos):o.parent=p;o.location=pos;return o

def mesh(name,verts,faces,mat):
    me=bpy.data.meshes.new(name);me.from_pydata(verts,[],faces);me.update();o=bpy.data.objects.new(name,me)
    bpy.context.collection.objects.link(o);me.materials.append(mat);metric_uv(o);return o

def tube(name,points,radius,mat,parent_obj=None):
    cu=bpy.data.curves.new(name,'CURVE');cu.dimensions='3D';cu.resolution_u=1;cu.bevel_depth=radius;cu.bevel_resolution=2
    sp=cu.splines.new('POLY');sp.points.add(len(points)-1)
    for p,co in zip(sp.points,points):p.co=(*co,1)
    o=bpy.data.objects.new(name,cu);bpy.context.collection.objects.link(o);cu.materials.append(mat)
    if parent_obj:o.parent=parent_obj
    return o

def lathe_y(name,profile,mat,parent_obj,segments=64):
    verts=[(r*math.sin(math.tau*i/segments),y,r*math.cos(math.tau*i/segments)) for r,y in profile for i in range(segments)]
    faces=[]
    for j in range(len(profile)):
        for i in range(segments):faces.append((j*segments+i,j*segments+(i+1)%segments,((j+1)%len(profile))*segments+(i+1)%segments,((j+1)%len(profile))*segments+i))
    o=mesh(name,verts,faces,mat);o.parent=parent_obj
    for poly in o.data.polygons:poly.use_smooth=True
    return o

def rounded_rect(cx,cy,width,depth,radius,z):
    pts=[]
    for x,y,angle in [(cx+width/2-radius,cy+depth/2-radius,0),(cx-width/2+radius,cy+depth/2-radius,math.pi/2),
                       (cx-width/2+radius,cy-depth/2+radius,math.pi),(cx+width/2-radius,cy-depth/2+radius,math.pi*1.5)]:
        for i in range(12):
            a=angle+i*math.pi/22;pts.append((x+radius*math.cos(a),y+radius*math.sin(a),z))
    return pts

def ellipse_print(name,x,y,z,rx,rz,mat,parent_obj=None):
    pts=[(x+rx*math.cos(math.tau*i/64),y,z+rz*math.sin(math.tau*i/64)) for i in range(64)]
    ob=mesh(name,pts,[tuple(range(64))],mat)
    if parent_obj:ob.parent=parent_obj
    return ob

def screw_face(name,pos,axis,steel,dark,r=.0020,parent_obj=None):
    ob=cylinder(name,pos,r,.0005,steel,axis,.00007,32)
    if parent_obj:ob.parent=parent_obj
    for angle in [0,math.pi/2]:
        d=r*.62;v=(math.cos(angle)*d,math.sin(angle)*d)
        if axis=='Y':points=[(pos[0]-v[0],pos[1]-.00031,pos[2]-v[1]),(pos[0]+v[0],pos[1]-.00031,pos[2]+v[1])]
        elif axis=='X':points=[(pos[0]-.00031,pos[1]-v[0],pos[2]-v[1]),(pos[0]-.00031,pos[1]+v[0],pos[2]+v[1])]
        else:points=[(pos[0]-v[0],pos[1]-v[1],pos[2]+.00031),(pos[0]+v[0],pos[1]+v[1],pos[2]+.00031)]
        tube('Recessed cross in '+name,points,.00011,dark,parent_obj)

def ellipsoid(name,centre,radii,mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48,ring_count=24,radius=1,location=centre)
    ob=bpy.context.object;ob.name=name;ob.scale=radii
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    for poly in ob.data.polygons:poly.use_smooth=True
    # UV circumference/meridian in metres, rather than one scan per sphere.
    for uv in ob.data.uv_layers.active.data:uv.uv=(uv.uv.x*math.tau*(radii[0]+radii[1])/2,uv.uv.y*math.pi*(radii[0]+radii[2])/2)
    ob.data.materials.append(mat);return ob

def plush_bear(x,y):
    cloth=pbr('Oatmeal knitted cotton bear','cotton_jersey','2k',LOOK['fabric_texture_height_m'],[.72,.94],.25,(.90,.79,.65,1))
    cloth.node_tree.nodes.get('Principled BSDF').inputs['Sheen Weight'].default_value=.38
    muzzle=pbr('Cream knitted muzzle','cotton_jersey','2k',LOOK['fabric_texture_height_m'],[.76,.96],.20,(1,1,.95,1))
    thread=material('Dark embroidered bear thread',(.028,.022,.017,1),.9)
    seams=material('Cotton sewing thread',(.36,.26,.17,1),.94)
    parts=[('Stuffed body',(x,y,.151),(.047,.037,.070)),('Stuffed head',(x,y-.012,.242),(.042,.034,.039)),
        ('Left cloth ear',(x-.032,y-.006,.272),(.016,.010,.019)),('Right cloth ear',(x+.032,y-.006,.272),(.016,.010,.019)),
        ('Left cloth paw',(x-.041,y-.015,.172),(.020,.022,.037)),('Right cloth paw',(x+.041,y-.015,.172),(.020,.022,.037)),
        ('Left cloth foot',(x-.026,y-.023,.092),(.024,.031,.027)),('Right cloth foot',(x+.026,y-.023,.092),(.024,.031,.027))]
    rng=random.Random(3107);fibres=bpy.data.curves.new('Short cotton surface fibres','CURVE');fibres.dimensions='3D';fibres.bevel_depth=.000023;fibres.bevel_resolution=0
    for label,centre,radii in parts:
        ellipsoid(label,centre,radii,cloth)
        for i in range(850 if 'head' in label else 350):
            zz=rng.uniform(-1,1);a=rng.uniform(0,math.tau);rr=math.sqrt(1-zz*zz);v=Vector((rr*math.cos(a),rr*math.sin(a),zz))
            start=Vector(centre)+Vector(tuple(v[k]*radii[k] for k in range(3)));normal=Vector(tuple(v[k]/radii[k] for k in range(3))).normalized()
            end=start+normal*rng.uniform(.00035,.00080);sp=fibres.splines.new('POLY');sp.points.add(1);sp.points[0].co=(*start,1);sp.points[1].co=(*end,1)
    ob=bpy.data.objects.new('Fine short cotton fibres on toy',fibres);bpy.context.collection.objects.link(ob);fibres.materials.append(cloth)
    ellipsoid('Soft stitched muzzle',(x,y-.041,.228),(.023,.009,.015),muzzle)
    for side in [-1,1]:
        ellipsoid('Embroidered soft eye',(x+side*.014,y-.043,.249),(.0024,.00065,.0031),thread)
        ellipsoid('Ear inner cloth',(x+side*.032,y-.015,.272),(.009,.001,.012),muzzle)
    ellipsoid('Embroidered nose',(x,y-.0501,.234),(.005,.0011,.0031),thread)
    for side in [-1,1]:tube('Embroidered bear smile',[(x,y-.050,.231),(x,y-.050,.226),(x+side*.006,y-.049,.224)],.00045,thread)
    for i in range(8):
        zz=.214+i*.007;tube('Short sewn head seam',[(x+.035,y-.015,zz),(x+.035,y-.012,zz+.0026)],.00020,seams)

def rainbow_stacker(x,y):
    colors=[(.68,.24,.12,1),(.95,.62,.13,1),(.76,.78,.47,1),(.24,.62,.51,1),(.15,.36,.48,1)]
    for i,tint in enumerate(colors):
        outer=.092-i*.016;inner=outer-.013
        contour=[(-outer,0)]+[(outer*math.cos(math.pi-j*math.pi/64),.009+outer*math.sin(math.pi-j*math.pi/64)) for j in range(65)]+[(outer,0),(inner,0)]
        contour +=[(inner*math.cos(j*math.pi/64),.009+inner*math.sin(j*math.pi/64)) for j in range(65)]+[(-inner,0)]
        n=len(contour);verts=[(xx,yy,zz) for yy in [-.017,.017] for xx,zz in contour]
        faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n)]
        mat=pbr('Translucent toy wood stain '+str(i),'white_oak_veneer','4k',.5,[.40,.57],.12,tint)
        ob=mesh('Separate wooden rainbow arch '+str(i),verts,faces,mat);ob.location=(x,y,0);ob.rotation_euler[2]=-.12
        be=ob.modifiers.new('0.55 mm sanded toy edges','BEVEL');be.width=.00055;be.segments=3;ob.modifiers.new('Arch face normals','WEIGHTED_NORMAL')

def book_paper(name,axis='X'):
    # The stripe spacing represents actual leaves, not oversized black grooves.
    mat=material(name,(.80,.77,.68,1),.86)
    n=mat.node_tree.nodes;l=mat.node_tree.links;p=n.get('Principled BSDF')
    tc=n.new('ShaderNodeTexCoord');sep=n.new('ShaderNodeSeparateXYZ');l.new(tc.outputs['Object'],sep.inputs[0])
    frequency=n.new('ShaderNodeMath');frequency.operation='MULTIPLY';frequency.inputs[1].default_value=math.tau/.00018;l.new(sep.outputs[axis],frequency.inputs[0])
    wave=n.new('ShaderNodeMath');wave.operation='SINE';l.new(frequency.outputs[0],wave.inputs[0])
    ramp=n.new('ShaderNodeMapRange');ramp.inputs['From Min'].default_value=-1;ramp.inputs['To Min'].default_value=.79;ramp.inputs['To Max'].default_value=1;l.new(wave.outputs[0],ramp.inputs[0])
    mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1;mix.inputs[1].default_value=(.83,.80,.72,1);l.new(ramp.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],p.inputs['Base Color'])
    bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000012;bump.inputs['Strength'].default_value=.15;l.new(wave.outputs[0],bump.inputs['Height']);l.new(bump.outputs[0],p.inputs['Normal'])
    return mat

def library_shelf_books():
    """Seven CC0 books, normalized from evaluated source vertices in metres."""
    import json
    recipe=json.loads((Path(__file__).resolve().parents[1]/'book_assets.json').read_text())
    source=ASSETS/'decorative_books/decorative_book_set_01_2k.blend'
    old_images=set(bpy.data.images)
    with bpy.data.libraries.load(str(source),link=False) as (available,loaded):
        assert set(recipe['object_names'])<=set(available.objects)
        loaded.objects=recipe['object_names']
    imported={o.name:o for o in loaded.objects}
    for ob in imported.values():bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.update()
    file_by_stem={r['image_stem']:ASSETS/'decorative_books'/r['path'] for r in recipe['downloads'] if 'image_stem' in r}
    for im in set(bpy.data.images)-old_images:
        if im.source!='FILE':continue
        key=Path(im.filepath).stem.split('_2k')[0]
        assert key in file_by_stem,(im.name,im.filepath)
        im.filepath=str(file_by_stem[key]);im.reload()
    # Source UVs, page blocks, case hinges and the actual deformed mesh are retained.
    # Only modest, documented use is selected from the source's ageing controls.
    for ob in imported.values():
        for mat in ob.data.materials:
            if not mat.use_nodes:continue
            for node in mat.node_tree.nodes:
                if node.type=='GROUP':
                    values={'damage_amount':.22,'stains':.12,'bump_strength':.28,'folds':.35,
                            'roughness':.47 if ob.name.startswith('book_hardcover') else .62}
                    for key,value in values.items():
                        if key in node.inputs:node.inputs[key].default_value=value
    def vertices(ob):return [ob.matrix_world@v.co for v in ob.data.vertices]
    def hull(points):
        pts=sorted(set((round(p.x,9),round(p.z,9)) for p in points))
        def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
        sides=[]
        for sequence in [pts,list(reversed(pts))]:
            side=[]
            for q in sequence:
                while len(side)>=2 and cross(side[-2],side[-1],q)<=0:side.pop()
                side.append(q)
            sides.append(side[:-1])
        return sides[0]+sides[1]
    def span(poly,z):
        xs=[]
        for a,b in zip(poly,poly[1:]+poly[:1]):
            if min(a[1],b[1])-1e-9<=z<=max(a[1],b[1])+1e-9:
                if abs(a[1]-b[1])<1e-9:xs.extend([a[0],b[0]])
                else:xs.append(a[0]+(b[0]-a[0])*(z-a[1])/(b[1]-a[1]))
        return min(xs),max(xs)
    def place(source_name,label,dimensions,front,base,rotation):
        ob=imported[source_name];deps=bpy.context.evaluated_depsgraph_get();ev=ob.evaluated_get(deps)
        me=bpy.data.meshes.new_from_object(ev,preserve_all_data_layers=True,depsgraph=deps);me.transform(ev.matrix_world)
        lo=[min(v.co[i] for v in me.vertices) for i in range(3)];hi=[max(v.co[i] for v in me.vertices) for i in range(3)]
        original=[hi[i]-lo[i] for i in range(3)];centre=[(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]]
        for v in me.vertices:
            for i in range(3):v.co[i]=(v.co[i]-centre[i])*dimensions[i]/original[i]
        me.update();ob.data=me;ob.modifiers.clear();ob.constraints.clear();ob.animation_data_clear();ob.parent=None;ob.matrix_world=Matrix.Identity(4)
        group=empty('CC0 shelf book '+label);ob.name='CC0 bound book mesh '+label;ob.parent=group;group.rotation_euler=rotation
        bpy.context.view_layer.update();points=vertices(ob);group.location.y=front-min(p.y for p in points);group.location.z=base-min(p.z for p in points)
        group['source_object']=source_name;group['source_dimensions_m']=original;group['normalized_dimensions_m']=dimensions
        group['support_height_m']=base;group['placement_label']=label;group['license']='CC0; Poly Haven Decorative Book Set 01'
        bpy.context.view_layer.update();return group,ob
    upright=[
        ('book_hardcover_01_cover87','0 Willow Wobbles',(.025,.167,.224),.735,-.008,.005),
        ('book_softcover_01_cover04','1 Cats and their humans',(.018,.154,.203),.746,.006,-.008),
        ('catalogue_softcover_01_cover26','2 Fluffy Doggo',(.012,.173,.214),.731,-.005,.011),
        ('book_hardcover_01_cover66','3 Space Walk',(.028,.177,.246),.749,.004,-.005),
        ('book_hardcover_01_cover06','4 Chrysanthemum',(.023,.160,.222),.738,-.11,.024)]
    previous=None
    for name,label,dimensions,front,lean,yaw in upright:
        group,ob=place(name,label,dimensions,front,.059,(0,lean,yaw));current=hull(vertices(ob))
        if previous is None:shift=.1885-min(p[0] for p in current)
        else:
            low=max(min(p[1] for p in current),min(p[1] for p in previous));high=min(max(p[1] for p in current),max(p[1] for p in previous))
            levels=sorted({low,high,*[p[1] for p in current+previous if low<p[1]<high]})
            shift=max(span(previous,z)[1]-span(current,z)[0] for z in levels)+.00020
        group.location.x+=shift;bpy.context.view_layer.update();previous=hull(vertices(ob))
        group['placement_method']='Evaluated XZ convex silhouettes with 0.2 mm side clearance; stable slight tilt, last paperback rests against taller neighbour'
    base=.059
    for name,label,dimensions,front,centre_x,yaw in [
        ('book_softcover_01_cover86','5 Weather laid flat',(.013,.143,.172),.831,.467,-.025),
        ('book_hardcover_01_cover29','6 Sun laid flat',(.011,.148,.158),.835,.465,.029)]:
        group,ob=place(name,label,dimensions,front,base,(0,math.pi/2,yaw));points=vertices(ob)
        group.location.x+=centre_x-(min(p.x for p in points)+max(p.x for p in points))/2
        bpy.context.view_layer.update();base=max(p.z for p in vertices(ob))
        group['placement_method']='Actual evaluated underside on shelf or lower book, no overlap with front display book'

def face_out_picture_book(x,y,z,cream,teal,orange):
    paper=book_paper('Board book ivory page edges','Y')
    green=material('Woodland printed hardback case',(.12,.20,.12,1),.43)
    micro_surface(green,2000,.43,.000004,.07)
    box('Thick board book page core',(x,y+.009,z+.0895),(.146,.016,.173),paper,.00065)
    for yy in [y,y+.018]:box('Rounded laminated board book cover',(x,yy,z+.0895),(.153,.0026,.179),green,.00105)
    art=material('Original watercolor Woodland cover print',(1,1,1,1),.41)
    p=art.node_tree.nodes.get('Principled BSDF');p.inputs['Coat Weight'].default_value=.21;p.inputs['Coat Roughness'].default_value=.30
    tex=art.node_tree.nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(ASSETS/'generated/woodland_cover.png'),check_existing=True);tex.interpolation='Linear'
    art.node_tree.links.new(tex.outputs['Color'],p.inputs['Base Color'])
    # Rounded flat print follows the 153 x 179 mm front board, without baked highlights.
    w,h,r=.153,.179,.00110;pts=[]
    for cx,cz,start in [(-w/2+r,r,math.pi),(w/2-r,r,math.pi*1.5),(w/2-r,h-r,0),(-w/2+r,h-r,math.pi/2)]:
        for j in range(9):
            angle=start+j*math.pi/16;pts.append((x+cx+r*math.cos(angle),y-.001317,z+cz+r*math.sin(angle)))
    ob=mesh('UV printed watercolor picture book front',pts,[tuple(range(len(pts)))],art)
    for face in ob.data.polygons:
        for li in face.loop_indices:
            co=ob.data.vertices[ob.data.loops[li].vertex_index].co;ob.data.uv_layers.active.data[li].uv=((co.x-x+w/2)/w,(co.z-z)/h)
    # A shallow actual spine hinge and unobtrusive laminate end caps.
    tube('Face out case binding crease',[(x-w/2+.006,y-.00134,z+.003),(x-w/2+.006,y-.00134,z+h-.003)],.00010,green)

def make_car(cfg,red,rubber,black,steel,rim,glass,lamp):
    car=empty('Free rigid chassis from solver');wheels=[]
    def part(ob):ob.parent=car;return ob
    def beam(name,a,b,width,depth,mat):
        d=Vector(b)-Vector(a);ob=box(name,(Vector(a)+Vector(b))/2,(width,depth,d.length),mat,.00022)
        ob.rotation_euler=d.to_track_quat('Z','Y').to_euler();return part(ob)
    # Rounded longitudinal shell, with actual openings rather than black discs.
    sections=[(-.066,.0265,.009,.027),(-.063,.029,.006,.030),(-.054,.0305,.004,.032),
        (-.030,.0308,.004,.033),(.010,.0308,.004,.033),(.032,.0302,.004,.032),
        (.056,.0296,.006,.030),(.064,.0288,.009,.029),(.066,.0268,.010,.027)]
    ring=32;verts=[]
    for xx,ww,low,high in sections:
        for j in range(ring):
            a=math.tau*j/ring;cc=math.cos(a);ss=math.sin(a)
            verts.append((xx,ww*math.copysign(abs(cc)**.40,cc),(low+high)/2+(high-low)/2*math.copysign(abs(ss)**.40,ss)))
    faces=[tuple(reversed(range(ring)))]+[(i*ring+j,i*ring+(j+1)%ring,(i+1)*ring+(j+1)%ring,(i+1)*ring+j) for i in range(len(sections)-1) for j in range(ring)]+[tuple((len(sections)-1)*ring+j for j in range(ring))]
    body=mesh('Rounded moulded ABS body shell',verts,faces,red)
    for xc in [-.046,.046]:
        cutter=cylinder('Temporary physical wheel opening cutter',(xc,0,0),.02225,.11,black,'Y',0,96)
        bo=body.modifiers.new('Open wheel well','BOOLEAN');bo.operation='DIFFERENCE';bo.solver='EXACT';bo.object=cutter
        bpy.context.view_layer.objects.active=body;bpy.ops.object.modifier_apply(modifier=bo.name);bpy.data.objects.remove(cutter,do_unlink=True)
    be=body.modifiers.new('0.45 mm tooling radius','BEVEL');be.width=.00045;be.segments=3;be.limit_method='ANGLE';be.angle_limit=.45
    for poly in body.data.polygons:poly.use_smooth=True
    body.modifiers.new('Weighted moulded panel normals','WEIGHTED_NORMAL');part(body)
    parent(box('Dark recessed underbody',(0,0,0),(.118,.048,.006),black,.0007),car,(0,0,.006))
    ivory=material('Warm ivory separate ABS roof',(.74,.71,.63,1),.29)
    ivory.node_tree.nodes.get('Principled BSDF').inputs['Coat Weight'].default_value=.22
    micro_surface(ivory,1900,.27,.000003,.07);finish_variation(ivory,70,.12)
    # Roof and pillars are separate, visibly tooled ABS parts around clear glazing.
    parent(box('Separate rounded roof cap',(0,0,0),(.063,.052,.0038),ivory,.00135),car,(-.017,0,.0576))
    interior=material('Dark warm grey moulded cabin interior',(.049,.045,.038,1),.61)
    seat=material('Satin moulded seat plastic',(.104,.096,.075,1),.54)
    parent(box('Cabin interior floor',(0,0,0),(.067,.048,.0014),interior,.0003),car,(-.012,0,.033))
    for yy in [-.012,.012]:
        parent(box('Visible front seat cushion',(0,0,0),(.017,.016,.0030),seat,.0016),car,(-.008,yy,.035))
        ob=parent(box('Visible front seat back',(0,0,0),(.0037,.017,.015),seat,.0015),car,(-.016,yy,.042));ob.rotation_euler[1]=-.12
        parent(box('Rear bench cushion',(0,0,0),(.012,.017,.003),seat,.0012),car,(-.036,yy,.0355))
    parent(box('Dashboard beneath windscreen',(0,0,0),(.011,.046,.005),interior,.001),car,(.016,0,.036))
    steering=[]
    for i in range(49):
        a=math.tau*i/48;steering.append((.008+.0025*math.cos(a),-.012+.0041*math.sin(a),.042+.0032*math.cos(a)))
    tube('Small unoccupied steering wheel',steering,.00052,black,car)
    beam('Steering column',(.012,-.012,.037),(.008,-.012,.042),.0012,.0012,black)
    for yy in [-.011,.011]:parent(box('Dashboard instrument recess',(0,0,0),(.0008,.010,.002),black,.00025),car,(.0098,yy,.039))
    def pane(name,corners,bow):
        # A shallow curved 0.28 mm transparent moulding, not an opaque decal.
        nu,nv=10,6;vs=[]
        c=[Vector(p) for p in corners];normal=(c[1]-c[0]).cross(c[3]-c[0]).normalized()
        for j in range(nv+1):
            v=j/nv
            for i in range(nu+1):
                u=i/nu;p=(1-v)*((1-u)*c[0]+u*c[1])+v*((1-u)*c[3]+u*c[2])+normal*bow*math.sin(math.pi*u)*math.sin(math.pi*v);vs.append(tuple(p))
        fs=[(j*(nu+1)+i,j*(nu+1)+i+1,(j+1)*(nu+1)+i+1,(j+1)*(nu+1)+i) for j in range(nv) for i in range(nu)]
        ob=part(mesh(name,vs,fs,glass));so=ob.modifiers.new('0.28 mm clear moulded glazing thickness','SOLIDIFY');so.thickness=.00028
        for poly in ob.data.polygons:poly.use_smooth=True
        tube('Recessed EPDM window seal '+name,corners+[corners[0]],.00032,black,car)
    for side in [-1,1]:
        yb=side*.0284;yt=side*.0242
        beam('Front inclined A pillar',(.025,yb,.032),(.011,yt,.0558),.0019,.0018,red)
        beam('Centre B pillar',(-.012,yb,.032),(-.012,yt,.0558),.0014,.0017,black)
        beam('Rear inclined C pillar',(-.050,yb,.032),(-.044,yt,.0558),.0026,.0020,red)
        beam('Lower window belt rail',(-.049,yb,.033),(.024,yb,.033),.0014,.0018,red)
        for label,co in [('Front side window',[(-.0108,yb,.0349),(.0218,yb,.0349),(.0100,yt,.0548),(-.0108,yt,.0548)]),
                        ('Rear side window',[(-.0468,yb,.0349),(-.0135,yb,.0349),(-.0135,yt,.0548),(-.0425,yt,.0548)])]:
            if side>0:co=list(reversed(co))
            pane(label+' '+str(side),co,.00028)
        for xc in [-.046,.046]:
            wheel_flare('Thick moulded wheel arch flare',xc,side,car,black)
        tube('Door shut line',[(-.012,side*.03098,.009),(-.012,side*.03098,.0305)],.000095,black,car)
        parent(box('Inset moulded door handle',(0,0,0),(.0058,.0010,.0011),black,.00025),car,(-.0045,side*.0310,.0294))
        parent(box('Side running step',(0,0,0),(.042,.0034,.0024),black,.00045),car,(0,side*.031,.005))
        parent(box('Mirror stalk',(0,0,0),(.0017,.004,.0015),black,.0003),car,(.017,side*.029,.037))
        parent(box('Rounded side mirror housing',(0,0,0),(.0055,.0030,.0045),black,.001),car,(.017,side*.032,.038))
        parent(box('Reflective mirror inset',(0,0,0),(.0042,.00018,.0030),steel,.0005),car,(.0168,side*.03352,.038))
    windshield=[(.024,-.0265,.0348),(.024,.0265,.0348),(.0113,.0231,.0546),(.0113,-.0231,.0546)]
    pane('Curved transparent windscreen',windshield,.00050)
    rear=[(-.0493,.026,.035),(-.0493,-.026,.035),(-.0440,-.0231,.0545),(-.0440,.0231,.0545)]
    pane('Transparent tailgate window',rear,.00025)
    for yy in [-.011,.011]:tube('Separate windscreen wiper blade',[(.0246,yy-.003,.0354),(.0227,yy+.005,.0378)],.00019,black,car)
    for xx in [-.06875,.06875]:parent(box('Injection moulded rounded bumper',(0,0,0),(.0055,.066,.0080),black,.0010),car,(xx,0,.007))
    parent(box('Recessed radiator grille',(0,0,0),(.0007,.028,.009),black,.0007),car,(.0662,0,.020))
    for yy in [-.010,-.005,0,.005,.010]:parent(box('Moulded grille slat',(0,0,0),(.0007,.00065,.007),rim,.00015),car,(.0668,yy,.020))
    reflector=material('Aluminised toy headlamp reflector',(.74,.76,.78,1),.17,.92)
    for yy in [-.022,.022]:
        parent(cylinder('Headlight dark surround',(0,0,0),.0048,.0013,black,'X',.0003,64),car,(.0659,yy,.0225))
        parent(cylinder('Recessed headlamp reflector',(0,0,0),.0039,.0004,reflector,'X',.00015,64),car,(.0666,yy,.0225))
        parent(cylinder('Clear headlight lens',(0,0,0),.0040,.00055,lamp,'X',.0002,64),car,(.0670,yy,.0225))
        for zz in [-.002,-.001,0,.001,.002]:parent(box('Moulded headlight lens fluting',(0,0,0),(.00010,.0057,.00012),lamp,.00004),car,(.0673,yy,.0225+zz))
    tail=material('Red translucent tail lamp plastic',(.48,.013,.005,1),.20)
    tail.node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value=.45
    for yy in [-.022,.022]:
        parent(box('Rear lamp backing',(0,0,0),(.00045,.006,.005),reflector,.0006),car,(-.0661,yy,.022))
        parent(box('Red rear lamp lens',(0,0,0),(.00075,.0065,.0055),tail,.0007),car,(-.0666,yy,.022))
    for yy in [-.018,.018]:tube('Moulded roof rail',[(-.043,yy,.0596),(-.040,yy,.0618),(.009,yy,.0618),(.011,yy,.0596)],.00065,black,car)
    for xx in [-.032,.004]:tube('Roof rack crossbar',[(xx,-.020,.0618),(xx,.020,.0618)],.00048,steel,car)
    # Narrow parting lines follow the actual bonnet rather than arbitrary dirt.
    for side in [-1,1]:tube('Bonnet panel seam',[(.029,side*.022,.0327),(.044,side*.022,.0315),(.060,side*.021,.0293)],.000075,black,car)
    for side in [-1,1]:
        ellipse_print('Thin pad printed door badge',.0005,side*.03099,.0207,.0066,.0066,ivory,car)
        ob=text('07',(.0005,side*.031045,.0207),.0070,black,(math.pi/2,0,0) if side<0 else (-math.pi/2,0,math.pi));ob.data.extrude=0;ob.parent=car
    c=cfg['physics']['car'];r=c['wheel_radius_m'];ww=c['wheel_width_m']
    recess=material('Recessed graphite wheel barrel',(.025,.029,.030,1),.43,.24)
    alloy=material('Vacuum metallised silver toy wheel',(.52,.55,.55,1),.24,.72)
    for i in range(4):
        w=empty('Solved wheel '+str(i));wheels.append(w)
        lathe_y('Rounded rubber tire carcass',[(.0115,-.0068),(.0158,-.007),(.0187,-.0063),(.01965,-.0046),(.01965,.0046),(.0187,.0063),(.0158,.007),(.0115,.0068)],rubber,w,96)
        for side in [-1,1]:
            parent(cylinder('Deep wheel barrel',(0,0,0),.0116,.0013,recess,'Y',.00015,64),w,(0,side*.0063,0))
            lathe_y('Polished moulded rim lip',[(.0109,side*.0069),(.0116,side*.0069),(.0117,side*.00725),(.01135,side*.00760),(.0109,side*.00740)],alloy,w,96)
            parent(cylinder('Recessed wheel centre hub',(0,0,0),.0032,.0012,alloy,'Y',.00035,64),w,(0,side*.00705,0))
            for k in range(5):
                theta=k*math.tau/5
                ob=box('Five sculpted wheel spokes',(0,0,0),(.00235,.0011,.0082),alloy,.00040)
                parent(ob,w,(math.sin(theta)*.00685,side*.00710,math.cos(theta)*.00685));ob.rotation_euler[1]=theta+.08
                parent(cylinder('Recessed hub screw',(0,0,0),.00055,.0004,steel,'Y',.00012,16),w,(math.sin(theta)*.0041,side*.00780,math.cos(theta)*.0041))
            for rr in [.0132,.0162]:tube('Fine tire sidewall moulding ring',[(rr*math.sin(math.tau*k/100),side*.00704,rr*math.cos(math.tau*k/100)) for k in range(101)],.00009,rubber,w)
            for k in range(20):
                a=math.tau*k/20;tube('Tiny sidewall tooling mark',[(rr*math.sin(a),side*.00705,rr*math.cos(a)) for rr in [.0170,.0177]],.00011,rubber,w)
        for k in range(36):
            for side in [-1,1]:
                a=math.tau*(k+(0.33 if side>0 else 0))/36
                ob=box('Staggered rounded all terrain tread lug',(0,0,0),(.00175,.0046,.00046),rubber,.00012)
                parent(ob,w,(math.sin(a)*(r-.00028),side*.00265,math.cos(a)*(r-.00028)))
                ob.rotation_mode='QUATERNION';ob.rotation_quaternion=Euler((0,a,0)).to_quaternion()@Euler((0,0,side*.32)).to_quaternion()
    return car,wheels

def oak_floor_boards(floor):
    # Physical joints follow the butt joints of the nine source scan boards.
    # The phase is shared by geometry and UV; there are no extra painted seams.
    rng=random.Random(7451);width=1.7/9;gap=.00035
    joints=[1-526/576,1-407/576,1-213/576,1-529/576,1-400/576,1-213/576,1-79/576,1-406/576,1-215/576]
    for row in range(32):
        yy=-2.7+(row+.5)*width;col=row%9;phase=rng.uniform(0,1.7)
        for k in range(-4,4):
            start=1.7*(k+joints[col])-phase;end=start+1.7
            if end<-3.5 or start>3.5:continue
            start=max(start,-3.5);end=min(end,3.5)
            ob=box('Individual satin oak floorboard',((start+end)/2,yy,-.008),(end-start-gap,width-gap,.016),floor,.00025)
            uv=ob.data.uv_layers.active
            for poly in ob.data.polygons:
                for li in poly.loop_indices:
                    co=ob.data.vertices[ob.data.loops[li].vertex_index].co
                    u=(col+(co.y/width+.5))/9*1.7
                    v=co.x+(start+end)/2+phase
                    uv.data[li].uv=(u,v)
    dark=material('Narrow oak board joint depth',(.085,.052,.028,1),.8)
    box('Floor sublayer below board joints',(0,.2,-.018),(7.5,6.2,.010),dark,0)

def text(body,pos,size,mat,rotation=(math.pi/2,0,0)):
    cu=bpy.data.curves.new('Painted '+body,'FONT');cu.body=body;cu.size=size;cu.align_x='CENTER';cu.align_y='CENTER';cu.extrude=.000015
    o=bpy.data.objects.new('Painted '+body,cu);bpy.context.collection.objects.link(o);o.location=pos;o.rotation_euler=rotation;cu.materials.append(mat);return o

def spring_points(cfg,compression):
    b=cfg['physics']['baffle'];s=cfg['physics']['spring'];wire=s['wire_diameter_m'];turns=s['active_turns']+s['closed_end_turns']
    start=b['rest_x_m']+b['thickness_m']/2+compression;end=b['rest_x_m']+b['thickness_m']/2+s['rest_length_m']
    length=end-start;points=[];rad=s['mean_coil_diameter_m']/2
    # First and last turns have closed pitch; the 14 active turns share all
    # remaining physical length. Endpoints and wire diameter never scale.
    for i in range(turns*48+1):
        u=i/48
        if u<1:x=wire*u
        elif u<turns-1:x=wire+(length-2*wire)*(u-1)/(turns-2)
        else:x=length-wire+wire*(u-(turns-1))
        theta=2*math.pi*u;points.append((start+x,rad*math.cos(theta),b['center_z_m']+rad*math.sin(theta),1))
    return points

def closed_normals(ob):
    import bmesh
    bm=bmesh.new();bm.from_mesh(ob.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(ob.data);bm.free();ob.data.update()
    return ob

def cut_mesh(ob,cutter):
    bpy.context.view_layer.objects.active=ob;bo=ob.modifiers.new('Manufactured through opening','BOOLEAN');bo.operation='DIFFERENCE';bo.solver='EXACT';bo.object=cutter
    while list(ob.modifiers).index(bo)>0:bpy.ops.object.modifier_move_up(modifier=bo.name)
    bpy.ops.object.modifier_apply(modifier=bo.name);bpy.data.objects.remove(cutter,do_unlink=True);return ob

def capsule_cutter(name,left,right,z,y,rad,depth,mat):
    contour=[]
    for cx,start in [(left,math.pi/2),(right,3*math.pi/2)]:
        for j in range(33):
            a=start+j*math.pi/32;contour.append((cx+rad*math.cos(a),z+rad*math.sin(a)))
    n=len(contour);vs=[(x,yy,zz) for yy in [y-depth/2,y+depth/2] for x,zz in contour]
    fs=[tuple(range(n)),tuple(reversed(range(n,2*n)))]+[(i,i+n,(i+1)%n+n,(i+1)%n) for i in range(n)]
    return closed_normals(mesh(name,vs,fs,mat))

def sleeve_x(name,pos,outer,inner,length,mat,parent_obj=None):
    x,y,z=pos;ns=64;profile=[(-length/2,outer),(length/2,outer),(length/2,inner),(-length/2,inner)]
    vs=[(x+xx,y+r*math.cos(math.tau*i/ns),z+r*math.sin(math.tau*i/ns)) for xx,r in profile for i in range(ns)]
    fs=[(j*ns+i,j*ns+(i+1)%ns,((j+1)%4)*ns+(i+1)%ns,((j+1)%4)*ns+i) for j in range(4) for i in range(ns)]
    ob=closed_normals(mesh(name,vs,fs,mat))
    for p in ob.data.polygons:p.use_smooth=True
    be=ob.modifiers.new('0.08 mm turned edge break','BEVEL');be.width=.00008;be.segments=2;ob.modifiers.new('Sleeve face normals','WEIGHTED_NORMAL')
    if parent_obj:ob.parent=parent_obj
    return ob

def cloth_surface(name,cx,cy,width,depth,z,mat,kind='mat'):
    nx,ny=64,48;vs=[]
    for j in range(ny+1):
        v=j/ny
        for i in range(nx+1):
            u=i/nx;xx=(u-.5)*width;yy=(v-.5)*depth
            if kind=='mat':
                edge=.0018*math.sin(7*math.pi*u+.3)*math.sin(math.pi*v)+.0010*math.sin(5*math.pi*v)*math.sin(math.pi*u)
                zz=.00045*math.sin(4*math.pi*u+.4)*math.sin(3*math.pi*v)+.011*math.exp(-((u-.97)/.11)**2-((v-.06)/.20)**2)
                xx+=.0007*math.sin(8*math.pi*v);yy+=edge
                if abs(xx+.09)<.023 and abs(yy+.07)<.023:zz=0.0
            else:
                mask=1-math.exp(-((xx/.042)**8+(yy/.043)**8));zz=.0030*math.sin(5*math.pi*u+.7)*math.sin(4*math.pi*v)*mask
            vs.append((cx+xx,cy+yy,z+zz))
    minimum=min(p[2] for p in vs)
    if kind=='mat':vs=[(x,y,zz-minimum+.0015) for x,y,zz in vs]
    fs=[(j*(nx+1)+i,j*(nx+1)+i+1,(j+1)*(nx+1)+i+1,(j+1)*(nx+1)+i) for j in range(ny) for i in range(nx)]
    ob=mesh(name,vs,fs,mat)
    if kind=='mat':ob['flat_rest_height_m']=z-minimum+.0015
    for p in ob.data.polygons:p.use_smooth=True
    so=ob.modifiers.new('1.5 mm woven cloth thickness','SOLIDIFY');so.thickness=.0015;so.offset=-1
    # One consistent metre mapping for a fabric surface, regardless of folds.
    uv=ob.data.uv_layers.active
    for p in ob.data.polygons:
        for li in p.loop_indices:
            co=ob.data.vertices[ob.data.loops[li].vertex_index].co;uv.data[li].uv=(co.x-cx,co.y-cy)
    if kind=='mat':
        rim=list(range(nx+1))+[j*(nx+1)+nx for j in range(1,ny+1)]+[ny*(nx+1)+i for i in range(nx-1,-1,-1)]+[j*(nx+1) for j in range(ny-1,0,-1)]
        pts=[tuple(Vector(vs[i])+Vector((0,0,.0002))) for i in rim];tube('Soft bound cotton mat edge',pts+[pts[0]],.00075,mat)
    return ob

def finish_rug(ob,mat):
    n=mat.node_tree.nodes;l=mat.node_tree.links;p=n.get('Principled BSDF');base=p.inputs['Base Color'].links[0].from_socket
    tc=n.new('ShaderNodeTexCoord');sep=n.new('ShaderNodeSeparateXYZ');l.new(tc.outputs['UV'],sep.inputs[0]);ab=n.new('ShaderNodeMath');ab.operation='ABSOLUTE';l.new(sep.outputs['X'],ab.inputs[0])
    masks=[]
    for low,high in [(.205,.224),(.237,.242)]:
        gt=n.new('ShaderNodeMath');gt.operation='GREATER_THAN';gt.inputs[1].default_value=low;l.new(ab.outputs[0],gt.inputs[0])
        lt=n.new('ShaderNodeMath');lt.operation='LESS_THAN';lt.inputs[1].default_value=high;l.new(ab.outputs[0],lt.inputs[0])
        both=n.new('ShaderNodeMath');both.operation='MULTIPLY';l.new(gt.outputs[0],both.inputs[0]);l.new(lt.outputs[0],both.inputs[1]);masks.append(both.outputs[0])
    mask=n.new('ShaderNodeMath');mask.operation='MAXIMUM';l.new(masks[0],mask.inputs[0]);l.new(masks[1],mask.inputs[1])
    image=next(node for node in n if node.type=='TEX_IMAGE' and '_diff_' in node.image.name)
    tint=n.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1;tint.inputs[2].default_value=(.66,.62,.53,1);l.new(image.outputs['Color'],tint.inputs[1])
    mix=n.new('ShaderNodeMixRGB');l.new(mask.outputs[0],mix.inputs[0]);l.new(base,mix.inputs[1]);l.new(tint.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],p.inputs['Base Color'])
    yarn=material('Cream cotton rug warp ends',(.56,.53,.45,1),.9);yarn.node_tree.nodes.get('Principled BSDF').inputs['Sheen Weight'].default_value=.25
    rng=random.Random(5419)
    for side,col in [(-1,0),(1,64)]:
        for j in range(1,48):
            point=ob.data.vertices[j*65+col].co
            for strand in [-1,0,1]:
                length=rng.uniform(.008,.013);yy=point.y+strand*.00025
                pts=[(point.x,yy,point.z),(point.x+side*length*.45,yy+rng.uniform(-.0007,.0007),max(.0004,point.z-.002)),(point.x+side*length,yy+rng.uniform(-.0012,.0012),max(.00025,point.z-.008))]
                tube('Loose short cotton warp yarn',pts,.00017,yarn)

def toy_bin_contents():
    """Original sewn plush and turned maple; metric, static appearance geometry."""
    import bisect
    before=set(bpy.data.objects)
    lining=pbr('Soft oatmeal toy-bin lining','cotton_jersey','2k',LOOK['fabric_texture_height_m'],[.78,.96],.18,(.92,.86,.73,1))
    lining.node_tree.nodes.get('Principled BSDF').inputs['Sheen Weight'].default_value=.34
    cloth=cloth_surface('Folded cotton lining inside toy bin',.77,.86,.235,.170,.0685,lining,'fold')
    for v in cloth.data.vertices:
        xx,yy,zz=v.co
        distances=[math.hypot(xx-.830,yy-.860)-.047,
                   math.hypot((xx-.693)*.85,yy-.844)-.032,
                   math.hypot((xx-.739)*.85,yy-.844)-.032]
        d=min(distances);w=max(0,min(1,1-d/.008));w=w*w*(3-2*w)
        v.co.z=zz*(1-w)+.0685*w
    cloth.data.update();cloth['resting_surface_z_m']=.064;cloth['toy_support_z_m']=.0685
    cotton=pbr('Rabbit oatmeal cotton plush','curly_teddy_natural','2k',.3,[.84,.98],.36,(.96,.93,.85,1))
    # The fleece scan is rectangular: preserve its published width and texel aspect.
    image=next(n.image for n in cotton.node_tree.nodes if n.type=='TEX_IMAGE')
    coordinate_scale=next(n for n in cotton.node_tree.nodes if n.type=='VECT_MATH' and n.operation=='MULTIPLY')
    coordinate_scale.inputs[1].default_value=(1/.3,image.size[0]/(.3*image.size[1]),1)
    cream=pbr('Rabbit cream muzzle cotton','cotton_jersey','2k',LOOK['fabric_texture_height_m'],[.85,.98],.10,(1,.96,.85,1))
    pink=pbr('Rabbit dusty rose inner-ear cotton','cotton_jersey','2k',LOOK['fabric_texture_height_m'],[.84,.98],.10,(.74,.48,.43,1))
    for mat,value in [(cotton,1.15),(cream,1.75),(pink,1.0)]:
        n=mat.node_tree.nodes;l=mat.node_tree.links;p=n.get('Principled BSDF')
        p.inputs['Sheen Weight'].default_value=.62;p.inputs['Sheen Roughness'].default_value=.78;p.inputs['IOR'].default_value=1.38
        original=p.inputs['Base Color'].links[0].from_socket
        dye=n.new('ShaderNodeHueSaturation');dye.inputs['Saturation'].default_value=.80;dye.inputs['Value'].default_value=value
        l.new(original,dye.inputs['Color'])
        tc=n.new('ShaderNodeTexCoord');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=125;noise.inputs['Detail'].default_value=2
        l.new(tc.outputs['Object'],noise.inputs['Vector'])
        remap=n.new('ShaderNodeMapRange');remap.inputs['To Min'].default_value=.94;remap.inputs['To Max'].default_value=1.025;l.new(noise.outputs['Fac'],remap.inputs[0])
        mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1
        l.new(dye.outputs['Color'],mix.inputs[1]);l.new(remap.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],p.inputs['Base Color'])
    thread=material('Rabbit dark brown embroidery',(.037,.025,.019,1),.94)
    seam=material('Rabbit matching cotton sewing thread',(.48,.40,.30,1),.97)
    rabbit_before=set(bpy.data.objects);fur_surfaces=[]
    def stuffed(label,centre,radii,phase,shape='body'):
        ob=ellipsoid('Rabbit '+label,centre,radii,cotton)
        for v in ob.data.vertices:
            q=v.co.copy();u=Vector(tuple(q[k]/radii[k] for k in range(3)))
            ripple=.008*math.sin(u.x*8+u.z*5+phase)*math.cos(u.y*6-phase)
            if shape=='head':
                # Broad cheeks, narrower jaw, a flatter forehead and uneven fill.
                v.co.x=q.x*(.95+.095*math.exp(-((u.z+.15)/.45)**2)-.13*max(-u.z,0)**2)+.0012*(u.z*u.z-.3)
                v.co.y=q.y*(1-.085*max(u.z,0)+.045*math.exp(-((u.z+.25)/.5)**2))
                v.co.z=q.z*(.985+.024*u.x)
            elif shape=='body':
                v.co.x=q.x*(1-.15*u.z+.025*math.sin(u.z*5+phase))
                v.co.y=q.y*(1-.10*u.z);v.co.z=q.z
            else:
                v.co=q*(1+.035*math.sin(u.x*3+u.z*2+phase))
            v.co*=1+ripple
        ob.data.update()
        if 'seated foot' in label:
            ob.location.z=-min(v.co.z for v in ob.data.vertices);ob['support_part']=True
        fur_surfaces.append((ob,7500 if shape=='head' else 1500));return ob
    body=stuffed('soft pear-shaped body',(-.002,.004,.079),(.039,.032,.062),.6)
    left=stuffed('floppy arm -1',(-.037,-.005,.088),(.014,.018,.039),-.7,'limb');left.rotation_euler[1]=-.14
    right=stuffed('floppy arm 1',(.035,-.001,.095),(.013,.018,.037),.7,'limb');right.rotation_euler[1]=.20
    for side in [-1,1]:stuffed('seated foot '+str(side),(side*.023,-.022,.025),(.023,.031,.025),side*.9,'limb')
    head_before=set(bpy.data.objects)
    head=stuffed('gently shaped head',(0,-.008,.155),(.0368,.028,.0355),1.2,'head')
    muzzle=ellipsoid('Rabbit soft cream muzzle',(-.0006,-.0353,.145),(.019,.0069,.0118),cream)
    # The muzzle is a soft sewn panel with a shallow central cleft.
    for v in muzzle.data.vertices:
        v.co.y+=.00055*math.exp(-(v.co.x/.0038)**2)*max(0,1-(v.co.z/.0118)**2)
    fur_surfaces.append((muzzle,1100))
    for side in [-1,1]:
        x=side*.0131;z=.1642+side*.0004
        ellipsoid('Rabbit embroidered eye '+str(side),(x,-.03345,z),(.00155,.00040,.0019),thread)
        for dx in [-.00050,0,.00050]:tube('Rabbit eye embroidery stitch',[(x+dx,-.03393,z-.0013),(x+dx,-.03393,z+.0013)],.00010,thread)
    # Small triangular satin stitching, rather than a moulded ball nose.
    for j in range(9):
        z=.1498-j*.00035;half=.0025*(1-j/10)
        tube('Rabbit satin stitched nose',[(-half,-.04245,z),(half,-.04245,z)],.00020,thread)
    tube('Rabbit embroidered nose stem',[(0,-.04245,.1465),(0,-.04230,.1435)],.00020,thread)
    for side in [-1,1]:tube('Rabbit small embroidered smile',[(0,-.04230,.1435),(side*.0018,-.04195,.1428),(side*.0033,-.04150,.1433)],.00018,thread)
    for side in [-1,1]:
        controls=([(-.020,-.003,.181),(-.028,.003,.230),(-.055,-.013,.255),(-.058,-.036,.219)] if side<0 else
                  [(.019,-.004,.182),(.031,.004,.222),(.047,-.013,.229),(.041,-.042,.187)])
        controls=list(map(Vector,controls))
        def ear_sample(t,u,controls=controls):
            a,b,c,d=controls;s=1-t
            centre=s**3*a+3*s*s*t*b+3*s*t*t*c+t**3*d
            tangent=(3*s*s*(b-a)+6*s*t*(c-b)+3*t*t*(d-c)).normalized()
            wide=Vector((tangent.z,0,-tangent.x)).normalized();depth=tangent.cross(wide).normalized()
            width=.00055+.0100*math.sin(math.pi*t)**.64
            thickness=.0010+.0022*math.sin(math.pi*t)**.65
            # Slight central channel and cloth gathering around the ear root.
            centre.y+=.0005*math.sin(t*math.pi*4)*(1-t)**2
            return centre+wide*(width*math.cos(u))+depth*(thickness*math.sin(u))
        rings=48;segments=32
        vs=[tuple(ear_sample(j/rings,math.tau*i/segments)) for j in range(rings+1) for i in range(segments)]
        fs=[(j*segments+i,j*segments+(i+1)%segments,(j+1)*segments+(i+1)%segments,(j+1)*segments+i) for j in range(rings) for i in range(segments)]
        fs.extend([tuple(reversed(range(segments))),tuple(rings*segments+i for i in range(segments))])
        ear=mesh('Rabbit curved floppy ear '+str(side),vs,fs,cotton);closed_normals(ear)
        for p in ear.data.polygons:p.use_smooth=True
        fur_surfaces.append((ear,2600))
        patch_vs=[]
        for j in range(41):
            t=.08+.84*j/40
            for i in range(13):
                u=math.pi*1.5+(i/12-.5)*1.24;pt=ear_sample(t,u);pt.y-=.00009;patch_vs.append(tuple(pt))
        patch=mesh('Rabbit inset rose ear panel '+str(side),patch_vs,[(j*13+i,j*13+i+1,(j+1)*13+i+1,(j+1)*13+i) for j in range(40) for i in range(12)],pink)
        for p in patch.data.polygons:p.use_smooth=True
        for u in [0,math.pi]:
            pts=[tuple(ear_sample(j/64,u)) for j in range(65)];tube('Rabbit fine ear edge seam',pts,.00013,seam)
    # A shallow seam follows the actual shaped head, including the crown.
    for side in [-1,1]:
        for j in range(18):
            a=-.78+j*.113
            pts=[(side*.0363*math.cos(q),-.0075,.155+.0351*math.sin(q)) for q in [a,a+.049]]
            tube('Rabbit fine head seam',pts,.00010,seam)
    bpy.context.view_layer.update()
    pivot=Vector((0,-.008,.155));rot=Euler((-.045,.135,.10),'XYZ').to_matrix().to_4x4()
    pose=Matrix.Translation(pivot)@rot@Matrix.Translation(-pivot)
    for ob in set(bpy.data.objects)-head_before:ob.matrix_world=pose@ob.matrix_world
    bpy.context.view_layer.update()
    rng=random.Random(101031)
    pile=bpy.data.curves.new('Rabbit fine cotton pile geometry','CURVE');pile.dimensions='3D';pile.bevel_depth=.000025;pile.bevel_resolution=0
    for ob,count in fur_surfaces:
        ob.data.calc_loop_triangles();triangles=list(ob.data.loop_triangles);areas=[];total=0
        for tr in triangles:total+=tr.area;areas.append(total)
        normal_matrix=ob.matrix_world.to_3x3().inverted().transposed()
        for i in range(count):
            tr=triangles[bisect.bisect_left(areas,rng.random()*total)];vv=[ob.data.vertices[k] for k in tr.vertices]
            a=math.sqrt(rng.random());b=rng.random();weights=[1-a,a*(1-b),a*b]
            q=sum((v.co*w for v,w in zip(vv,weights)),Vector());nn=sum((v.normal*w for v,w in zip(vv,weights)),Vector())
            start=ob.matrix_world@q;normal=(normal_matrix@nn).normalized()
            length=rng.uniform(.00040,.0010)*(1+.15*math.sin(start.x*240+start.z*95))
            bend=Vector((rng.uniform(-.00015,.00015),rng.uniform(-.00015,.00015),-.00010))
            pts=[start,start+normal*length*.57+bend*.35,start+normal*length+bend]
            # Flattened underside fibres rest on the soft lining.
            for pt in pts:pt.z=max(.00002,pt.z)
            sp=pile.splines.new('POLY');sp.points.add(2)
            for p,co in zip(sp.points,pts):p.co=(*co,1)
    pile_ob=bpy.data.objects.new('Rabbit short soft cotton pile',pile);bpy.context.collection.objects.link(pile_ob);pile.materials.append(cotton)
    rabbit=empty('Seated oatmeal plush rabbit')
    for ob in set(bpy.data.objects)-rabbit_before-{rabbit}:
        if ob.parent is None:ob.parent=rabbit
    rabbit.location=(.716,.866,.0685);rabbit.rotation_euler[2]=-.075
    rabbit['support_height_m']=.0685;rabbit['description']='Sewn cotton rabbit: shaped cheeks and jaw, tilted head, two gravity-folded cloth ears, embroidered face, 21300 surface-sampled short fibres, flattened supported feet'
    stack=empty('Wooden pastel stacking toy');stack.location=(.830,.860,.0685)
    def maple(name,tint,paint=False):
        m=pbr(name,'white_maple_veneer','2k',.32,[.47,.64] if paint else [.39,.56],.075,tint)
        p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Coat Weight'].default_value=.07;p.inputs['Coat Roughness'].default_value=.44
        finish_variation(m,185,.09)
        if paint:
            n=m.node_tree.nodes;l=m.node_tree.links;old=p.inputs['Base Color'].links[0].from_socket
            mix=n.new('ShaderNodeMixRGB');mix.inputs[0].default_value=.40;mix.inputs[2].default_value=tint;l.new(old,mix.inputs[1]);l.new(mix.outputs[0],p.inputs['Base Color'])
        return m
    raw=maple('Stacking toy clear maple',(1,.91,.72,1))
    base=cylinder('Stacking toy maple base',(0,0,.004),.046,.008,raw,'Z',.0007,96);base.parent=stack;base['support_part']=True
    # Apply the cylinder transform before metric UVs so the scan has real scale.
    for v in base.data.vertices:v.co=base.matrix_basis@v.co
    base.matrix_basis=Matrix.Identity(4);metric_uv(base)
    peg=cylinder('Stacking toy central wooden peg',(0,0,.0815),.0055,.147,raw,'Z',.0005,64);peg.parent=stack
    colors=[(.79,.77,.62,1),(.64,.33,.22,1),(.76,.63,.34,1),(.66,.44,.40,1),(.38,.52,.57,1),(.47,.59,.46,1)]
    offsets=[(0,0),(.00016,-.00012),(-.00022,.00017),(.00018,.00028),(-.00023,-.00018),(.00021,-.00013)]
    for j,(r,tint) in enumerate(zip([.042,.038,.033,.028,.023,.018],colors)):
        mat=maple('Stacking ring translucent stain '+str(j),tint,True)
        inner=.0063;profile=[(p[0],p[1]) for p in rounded_rect((r+inner)/2,0,r-inner,.022,.0024,0)]
        ring=lathe_y('Rounded annular wooden stacking ring '+str(j),profile,mat,stack,96)
        # Board grain is continuous over each flat face; each separate ring has its own board orientation.
        rotate=Euler((math.pi/2,0,j*.47+.13),'XYZ').to_matrix()
        for v in ring.data.vertices:v.co=rotate@v.co
        ring.data.update();metric_uv(ring)
        ring.location=(offsets[j][0],offsets[j][1],.019+j*.022)
        ring['ring_inner_radius_m']=inner;ring['ring_outer_radius_m']=r;ring['radial_offset_m']=math.hypot(*offsets[j])
        ring['manufactured_edge_radius_m']=.0024
    # A turned cap with a short shoulder reads as a manufactured wooden part.
    profile=[(.003,.153),(.006,.154),(.0085,.158),(.0090,.164),(.0081,.169),(.0054,.173),(.001,.175)]
    cap=lathe_y('Stacking toy natural maple top',profile,raw,stack,96)
    for v in cap.data.vertices:v.co=Vector((v.co.x,-v.co.z,v.co.y))
    cap.data.update();metric_uv(cap)
    stack.scale.z=1.24;stack['vertical_profile_scale']=1.24
    stack['support_height_m']=.0685;stack['description']='Six individually grained matte-stained maple rings, restrained 2.4mm roundovers, submillimetre offsets inside peg clearance, closed support surfaces and turned cap'
    bpy.context.view_layer.update()
    for root in [rabbit,stack]:
        pts=[ob.matrix_world@v.co for ob in root.children if ob.type=='MESH' for v in ob.data.vertices]
        root['measured_world_dimensions_m']=[max(v[k] for v in pts)-min(v[k] for v in pts) for k in range(3)]
    return {'rabbit':rabbit,'stacker':stack,'lining':cloth}



def build_scene(cfg,data,gray=False):
    global LOOK
    LOOK=cfg['appearance']
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    for m in list(bpy.data.materials):bpy.data.materials.remove(m)
    rng=random.Random(cfg['appearance']['seed']);ref=empty('World texture coordinates metres')
    floor=pbr('Scanned satin oak floor','wood_floor','2k',LOOK.get('floor_texture_width_m',1.7),LOOK.get('floor_roughness_range',[.19,.43]),LOOK.get('floor_normal_strength',.38),LOOK.get('floor_tint',[1,1,1,1]))
    floor.node_tree.nodes.get('Principled BSDF').inputs['Coat Weight'].default_value=.18
    floor.node_tree.nodes.get('Principled BSDF').inputs['Coat Roughness'].default_value=.35
    beech=wood('Fine beech road',ref,(.68,.49,.28),(.47,.30,.14),(4,230,15))
    faint_road_wear(beech)
    maple=wood('Maple support blocks',ref,(.70,.56,.35),(.52,.38,.20),(4,190,16))
    red=material('Terracotta toy enamel',cfg['appearance']['car_color'],.3)
    rubber=material('Tire rubber',(.012,.016,.020,1),.72);black=material('Black moulded chassis',(.019,.025,.030,1),.43)
    steel=material('Brushed steel guides',(.38,.42,.47,1),.21,.92);springmat=material('Tempered spring steel',(.22,.25,.29,1),.19,.95)
    rim=material('Moulded silver ABS wheel hubs',(.27,.30,.31,1),.41,.28);glass=material('Clear lightly smoked polycarbonate windows',(.75,.86,.89,1),.095)
    glass.node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value=1.0
    glass.node_tree.nodes.get('Principled BSDF').inputs['IOR'].default_value=1.47
    glass.node_tree.nodes.get('Principled BSDF').inputs['Coat Weight'].default_value=.35
    red.node_tree.nodes.get('Principled BSDF').inputs['Coat Weight'].default_value=.28
    red.node_tree.nodes.get('Principled BSDF').inputs['Coat Roughness'].default_value=.20
    micro_surface(red,1800,LOOK['car_plastic_roughness'],.000004,.08);micro_surface(rubber,2600,.72,.000012,.12);micro_surface(black,2000,.43,.000007,.10)
    finish_variation(red,85,LOOK['surface_finish']['plastic_roughness_variation']);finish_variation(black,110,.10);finish_variation(rubber,130,.08)
    handled_clear_finish(red,LOOK['surface_finish']['paint_touch_roughness_delta']);handled_clear_finish(glass,LOOK['surface_finish']['glazing_touch_roughness_delta'])
    white=material('Warm ivory paint',(.77,.76,.69,1),.42);lamp=material('Headlight lens',(.94,.96,.97,1),.10)
    lamp.node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value=.86
    lamp.node_tree.nodes.get('Principled BSDF').inputs['IOR'].default_value=1.47
    dark=material('Screw recess',(.018,.020,.023,1),.5)
    teal=pbr('Satin teal toy-kit wood stain','white_oak_veneer','4k',.5,[.39,.55],.12,(.18,.62,.55,1))
    ink=material('Screen printed warm white track ink',(.75,.72,.62,1),.54)
    roadink=material('Muted sage road screenprint',(.23,.36,.29,1),.61)
    if gray:
        for mat in list(bpy.data.materials):
            if mat.name not in ['Spring steel wire','Brushed steel guides']:
                p=mat.node_tree.nodes.get('Principled BSDF')
                for link in list(p.inputs['Base Color'].links):mat.node_tree.links.remove(link)
                p.inputs['Base Color'].default_value=(.38,.40,.42,1)
    # Scan's 1.7 m width includes its actual 19 cm floor boards. The physical
    # contact plane stays z=0; the texture is never used as displacement.
    oak_floor_boards(floor)
    wall=material('Subtle sage grey wall paint',LOOK.get('wall_color',(.66,.69,.66,1)),.87);micro_surface(wall,2100,.87,.000018,.025)
    trim=material('Painted timber trim',(.77,.76,.70,1),.47);micro_surface(trim,2200,.47,.000008,.045)
    box('Back plaster wall',(0,1.08,1.25),(5,.08,2.5),wall,.001)
    box('Skirting back',(0,1.028,.052),(5,.024,.104),trim,.0007)
    box('Skirting moulded lip',(0,1.013,.095),(5,.008,.008),trim,.0008)
    # Actual wall opening and window create the shared light and reflections.
    for yy,sz in [(-1.45,1.7),(.74,.68)]:box('Left wall beside window',(-1.75,yy,1.25),(.08,sz,2.5),wall,.001)
    box('Wall below window',(-1.75,-.05,.29),(.08,1.1,.58),wall,.001)
    box('Wall over window',(-1.75,-.05,2.22),(.08,1.1,.56),wall,.001)
    for yy in [-.56,.46]:box('Window outer vertical casing',(-1.699,yy,1.26),(.032,.06,1.44),trim,.001)
    for zz in [.56,1.96]:box('Window outer horizontal casing',(-1.699,-.05,zz),(.032,1.08,.06),trim,.001)
    box('Window centre mullion',(-1.695,-.05,1.26),(.036,.024,1.34),trim,.0006)
    box('Window sash bar',(-1.695,-.05,1.25),(.036,1.00,.024),trim,.0006)
    box('Painted window sill',(-1.66,-.05,.54),(.16,1.17,.028),trim,.0015)
    # Close the room outside the camera frustum, so sky illumination enters
    # through the window instead of uniformly lighting the floor from above.
    box('Ceiling outside framing',(.125,-.61,2.53),(3.83,3.46,.06),trim,.001)
    box('Front wall behind camera',(.125,-2.34,1.25),(3.83,.08,2.5),wall,.001)
    box('Right room wall outside framing',(2.04,-.61,1.25),(.08,3.46,2.5),wall,.001)
    r=cfg['physics']['road'];pts=road_points(cfg);half=r['width_m']/2;t=r['board_thickness_m']
    # Render the same faceted top envelope used for contact, as a single wood
    # mesh. Solid lower support sides touch the floor without fake shadows.
    road_parts=[]
    for name,segment in [('Fixed fine maple ramp board',[p for p in pts if p[0]<=0]),('Fixed maple horizontal deck',[p for p in pts if p[0]>=0])]:
        verts=[]
        for x,z in segment:verts +=[(x,-half,z),(x,half,z),(x,-half,z-t),(x,half,z-t)]
        faces=[]
        for i in range(len(segment)-1):
            a=i*4;bb=a+4;faces +=[(a,bb,bb+1,a+1),(a+2,a+3,bb+3,bb+2),(a,a+2,bb+2,bb),(a+1,bb+1,bb+3,a+3)]
        faces +=[(0,1,3,2),(len(verts)-4,len(verts)-2,len(verts)-1,len(verts)-3)]
        road=mesh(name,verts,faces,beech);road_parts.append(road)
        be=road.modifiers.new('0.20 mm sanded deck edge','BEVEL');be.width=.00020;be.segments=3;be.limit_method='ANGLE';be.angle_limit=.50
        road.modifiers.new('Board face normals','WEIGHTED_NORMAL')
    # Visible 6 mm battens support a 14 mm flat deck at its original z=20 mm.
    for yy in [-.064,.064]:box('Fixed flat deck support batten',(.35,yy,.003),(.70,.014,.006),maple,.0002)
    # Thin plywood laminations on exposed edges, following the ramp slope.
    edge=material('Seven ply birch board edge',(.51,.37,.21,1),.48);nt=edge.node_tree;n=nt.nodes;l=nt.links;p=n.get('Principled BSDF')
    uv=n.new('ShaderNodeTexCoord');sep=n.new('ShaderNodeSeparateXYZ');l.new(uv.outputs['UV'],sep.inputs[0])
    mul=n.new('ShaderNodeMath');mul.operation='MULTIPLY';mul.inputs[1].default_value=math.tau/.004
    l.new(sep.outputs['Y'],mul.inputs[0]);sine=n.new('ShaderNodeMath');sine.operation='SINE';l.new(mul.outputs[0],sine.inputs[0])
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=0;ramp.color_ramp.elements[0].color=(.40,.30,.20,1);ramp.color_ramp.elements[1].position=.45;ramp.color_ramp.elements[1].color=(.52,.41,.28,1)
    l.new(sine.outputs[0],ramp.inputs[0]);l.new(ramp.outputs[0],p.inputs['Base Color'])
    for road in road_parts:
        road.data.materials.append(edge)
        for poly in road.data.polygons:
            if abs(poly.normal.z)<.9:
                poly.material_index=1
                for li in poly.loop_indices:
                    co=road.data.vertices[road.data.loops[li].vertex_index].co;x=float(co.x);top=__import__('scene_config').profile(cfg,x)[0]
                    road.data.uv_layers.active.data[li].uv=(x,float(co.z)-top)
    # Seven-ply cheeks follow the actual underside, including the bottom arc.
    xr=r['ramp_start_x_m'];zr=pts[0][1];contour=[(xr,0),(0,0)]+[(x,z-t) for x,z in reversed(pts) if x<=0];n=len(contour)
    for yy in [-.064,.064]:
        vs=[(x,y,z) for y in [yy-.007,yy+.007] for x,z in contour]
        fs=[tuple(range(n)),tuple(reversed(range(n,2*n)))]+[(j,j+n,(j+1)%n+n,(j+1)%n) for j in range(n)]
        cheek=closed_normals(mesh('Contoured fixed plywood ramp cheek',vs,fs,maple))
        cut_mesh(cheek,capsule_cutter('Carry slot cutter',-.554,-.461,.058,yy,.012,.050,dark))
        metric_uv(cheek);cheek.data.materials.append(edge)
        for poly in cheek.data.polygons:
            if abs(poly.normal.y)<.5:
                poly.material_index=1
                for li in poly.loop_indices:
                    co=cheek.data.vertices[cheek.data.loops[li].vertex_index].co;cheek.data.uv_layers.active.data[li].uv=(co.x,co.y-yy)
        be=cheek.modifiers.new('0.45 mm sanded plywood edge','BEVEL');be.width=.00045;be.segments=3;cheek.modifiers.new('Plywood normals','WEIGHTED_NORMAL')
    brand=material('Flat muted teal kit printing',(.10,.25,.21,1),.62)
    label=text('GRAVITY PLAY',(xr+.145,-.071055,.025),.0080,brand);label.data.extrude=0
    for xx,zz in [(xr+.028,.024),(-.30,.020),(-.08,.008)]:screw_face('Captive cheek fastening',(xx,-.07125,zz),'Y',steel,dark,.0017)
    from scene_config import profile
    def road_pigment(name,lo,hi,y0,y1):
        xs=[lo]+[x for x,z in pts if lo<x<hi]+[hi]
        vs=[(x,y,profile(cfg,x)[0]+.000035) for x in xs for y in [y0,y1]]
        return mesh(name,vs,[(i*2,i*2+2,i*2+3,i*2+1) for i in range(len(xs)-1)],roadink)
    for side in [-1,1]:road_pigment('Thin printed toy road edge',xr+.009,.695,side*.060-.0011,side*.060+.0011)
    x=xr+.022
    while x<.30:
        road_pigment('Printed road centre dash',x,min(x+.026,.30),-.0016,.0016);x+=.061
    # Small flush metal screws and dowel joints indicate a real fixed track.
    for xx in [-.63,.68]:
        zz=next((z for x,z in pts if abs(x-xx)<1e-6),r['flat_top_z_m']) if xx>0 else pts[0][1]-.02*r['slope']
        for yy in [-.066,.066]:
            cylinder('Flush road screw',(xx,yy,zz+.0001),.0018,.00025,steel,'Z',.00005,24)
    b=cfg['physics']['baffle'];s=cfg['physics']['spring'];back=b['rest_x_m']+b['thickness_m']/2+s['rest_length_m']
    for side in [-1,1]:
        y=side*b['guide_y_m'];rodstart=b['rest_x_m']-.025;rodend=back+.015
        cylinder('Fixed horizontal guide rod',((rodstart+rodend)/2,y,b['guide_z_m']),.0017,rodend-rodstart,steel,'X')
        upright=box('Rear fixed upright',(back+.006,side*.054,.065),(.012,.026,.090),teal,.00065)
        cut_mesh(upright,cylinder('Rear rod bore',(back+.006,y,b['guide_z_m']),.00205,.040,dark,'X',0,48))
        sleeve_x('Rear pressed guide bushing',(back+.006,y,b['guide_z_m']),.0037,.0018,.014,steel)
        box('Front guide foot',(rodstart,side*.067,.052),(.012,.014,.064),teal,.0005)
        tab=box('Guide support tab',(rodstart,side*.058,.084),(.012,.023,.007),steel,.0003)
        cut_mesh(tab,cylinder('Front rod bore',(rodstart,y,b['guide_z_m']),.0019,.030,dark,'X',0,48))
        sleeve_x('Front pressed guide bushing',(rodstart,y,b['guide_z_m']),.0035,.0018,.013,steel)
        cylinder('Bracket fastening screw',(back+.006,side*.054,.1103),.002,.0006,steel,'Z',.0001,24)
        screw_face('Rear guide mounting cross screw',(back+.006,side*.054,.1107),'Z',steel,dark,.0020)
    for xx in [b['rest_x_m']-.025,back+.006]:
        for side in [-1,1]:
            yy=side*.061
            box('Fixed guide mounting foot',(xx,yy,.0206),(.024,.027,.0012),steel,.00025)
            for dx in [-.0080,.0080]:screw_face('Guide foot wood screw',(xx+dx,yy,.0213),'Z',steel,dark,.00165)
    box('Fixed spring anchor plate',(back+.006,0,b['center_z_m']),(.012,.130,.016),steel,.0007)
    # Mechanical stops survive delete_spring. Maximum stop is on the rods,
    # leaving more than the physical solid height of the helix.
    for side in [-1,1]:
        for xx in [b['rest_x_m']-.007,b['rest_x_m']+s['effective_stroke_m']+.006]:
            sleeve_x('Guide mechanical stop collar',(xx,side*b['guide_y_m'],b['guide_z_m']),.0042,.00175,.005,steel)
            screw_face('Stop collar grub screw',(xx,side*b['guide_y_m'],b['guide_z_m']+.0042),'Z',steel,dark,.0008)
    baffle=empty('Baffle pose from solver')
    movingwood=box('Sliding maple baffle',(0,0,0),(.006,.120,.080),maple,.0005)
    for side in [-1,1]:cut_mesh(movingwood,cylinder('Moving rod bore',(0,side*b['guide_y_m'],b['guide_z_m']-b['center_z_m']),.00205,.024,dark,'X',0,48))
    movingwood.parent=baffle
    for side in [-1,1]:
        zz=b['guide_z_m']-b['center_z_m'];yy=side*b['guide_y_m']
        yoke=box('Bolted baffle bearing plate',(-.0036,side*.055,zz),(.0012,.019,.017),steel,.0002)
        cut_mesh(yoke,cylinder('Yoke bearing bore',(-.0036,yy,zz),.00205,.020,dark,'X',0,48));yoke.parent=baffle
        sleeve_x('Annular moving baffle bearing',(0,yy,zz),.0043,.00185,.010,steel,baffle)
        for dz in [-.0058,.0058]:screw_face('Baffle bearing fastening',(-.00425,side*.051,zz+dz),'X',steel,dark,.0009,baffle)
    # Ink on the baffle, on a body-local plane: no extra contact thickness.
    stripe=mesh('Small teal printed baffle top band',[(-.00304,-.058,.027),(-.00304,.058,.027),(-.00304,.058,.036),(-.00304,-.058,.036)],[(0,1,2,3)],teal);stripe.parent=baffle
    parent(cylinder('Moving spring end seat',(0,0,0),.016,.0015,steel,'X'),baffle,(.0035,0,0))
    cylinder('Fixed spring end seat',(back-.0006,0,b['center_z_m']),.016,.0012,steel,'X')
    helix=None
    if s['present']:
        cu=bpy.data.curves.new('Physical length spring helix','CURVE');cu.dimensions='3D';cu.resolution_u=1;cu.bevel_depth=s['wire_diameter_m']/2;cu.bevel_resolution=3
        spline=cu.splines.new('POLY');points=spring_points(cfg,0);spline.points.add(len(points)-1)
        for p,co in zip(spline.points,points):p.co=co
        helix=bpy.data.objects.new('Metal compression spring solved length',cu);bpy.context.collection.objects.link(helix);cu.materials.append(springmat)
    before_car=set(bpy.data.objects)
    car,wheels=make_car(cfg,red,rubber,black,steel,rim,glass,lamp)
    if not cfg['physics']['car'].get('present',True):
        # DELETE car: the car is built as usual (the rest of the room is constructed identically) and every object
        # make_car created (body, glazing, trim, wheels, tyres) is removed again, so it casts no shadow or reflection.
        for ob in set(bpy.data.objects)-before_car:bpy.data.objects.remove(ob,do_unlink=True)
        car=None;wheels=[]
    matcloth=pbr('Woven blue-grey cotton play mat','cotton_jersey','2k',LOOK['fabric_texture_height_m'],[.73,.94],.35,(.25,.40,.43,1))
    matcloth.node_tree.nodes.get('Principled BSDF').inputs['Sheen Weight'].default_value=.24
    playmat=cloth_surface('Loose cotton mat outside motion corridor',-.51,.62,.51,.35,.0015,matcloth)
    finish_rug(playmat,matcloth)
    blue=material('Block blue',(.07,.24,.42,1),.6);yellow=material('Block ochre',(.66,.40,.08,1),.6)
    blockred=material('Block red',(.51,.10,.05,1),.6)
    blockblue=pbr('Blue stained wooden block','white_maple_veneer','2k',1,[.43,.63],.12,(.09,.31,.45,1))
    blockyellow=pbr('Ochre stained wooden block','white_maple_veneer','2k',1,[.43,.63],.12,(.90,.65,.21,1))
    blockterra=pbr('Terracotta stained wooden block','white_maple_veneer','2k',1,[.43,.63],.12,(.65,.24,.12,1))
    for i,(x,y,sz,rot,mat) in enumerate([(-.60,.55,.038,.12,blockblue),(-.49,.22,.032,-.19,maple),(.27,.50,.037,.20,blockyellow),(.51,.50,.032,-.25,blockterra)]):
        base=playmat['flat_rest_height_m'] if i==0 else 0.
        ob=box('Grounded wooden play block '+str(i),(x,y,sz/2+base),(sz,sz,sz),mat,.0006,(0,0,rot))
        if i in [0,2]:
            mark=text('A' if i==0 else 'B',(0,-sz/2-.000035,0),sz*.50,white);mark.parent=ob;mark.data.extrude=0
    rainbow_stacker(-.085,.365)
    # A real assembled cabinet: actual butt joints, recessed backing and a toe kick.
    cabinet_before=set(bpy.data.objects)
    cabinet=material('Satin white cabinet paint',(.72,.71,.65,1),.44);micro_surface(cabinet,1800,.44,.000006,.08)
    backing=material('Matte warm white recessed cabinet backing',(.69,.68,.62,1),.62);micro_surface(backing,2100,.62,.000005,.05)
    felt=material('Small dark felt cabinet floor protectors',(.08,.075,.063,1),.95)
    for xx in [.235,.985]:
        for yy in [.775,.955]:box('Cabinet felt floor pad',(xx,yy,.0005),(.030,.028,.001),felt,.0002)
    box('Cabinet inset plinth',(.61,.762,.021),(.79,.018,.040),cabinet,.00045)
    for xx in [.224,.996]:box('Cabinet plinth return',(xx,.865,.021),(.018,.188,.040),cabinet,.0004)
    box('Cabinet rear plinth rail',(.61,.968,.021),(.79,.018,.040),cabinet,.0004)
    oak=pbr('Clear finished oak cabinet top','white_oak_veneer','4k',.5,[.34,.49],.09,(.94,.88,.76,1))
    oak.node_tree.nodes.get('Principled BSDF').inputs['Coat Weight'].default_value=.10
    # Three real glued boards share the long X grain; joints are 0.12 mm wide.
    for j in range(3):box('Oak cabinet top board '+str(j),(.61,.76+j*.100,.346),(.88,.09988,.022),oak,.00055)
    box('Cabinet bottom',(.61,.851,.050),(.8434,.280,.018),cabinet,.00045)
    sides=[]
    for xx in [.179,1.041]:sides.append(box('Cabinet upright',(xx,.8555,.188),(.018,.289,.294),cabinet,.0005))
    sides.append(box('Cabinet upright divider',(.61,.851,.197),(.018,.280,.276),cabinet,.0004))
    box('Cabinet real back panel',(.61,.994,.197),(.8434,.006,.276),backing,.00025)
    # An inset rear panel and slim edge tape have physical joints, not black outlines.
    for xx in [.18825,.60075,.61925,1.03175]:
        box('Cabinet recessed backing joint',(xx,.9905,.197),(.00055,.003,.275),backing,.00012)
    for ob in sides:
        box('Cabinet front edge band seam',(ob.location.x,.71087,ob.location.z),(.0168,.00018,ob.dimensions.z-.001),cabinet,.0003)
    holemat=material('Recessed unused shelf pin holes',(.23,.22,.18,1),.9)
    # Standard 32 mm shelf pin spacing, actual blind bores in the panel faces.
    for wall,face,sign in [(sides[0],.188,1),(sides[2],.601,-1),(sides[2],.619,1),(sides[1],1.032,-1)]:
        for yy in [.749,.962]:
            for zz in [.126,.158,.190,.222,.254,.286]:
                cut_mesh(wall,cylinder('Blind shelf pin bore cutter',(face-sign*.00125,yy,zz),.00165,.0035,holemat,'X',0,24))
                cylinder('Recessed shelf pin hole bottom',(face-sign*.0028,yy,zz),.00160,.0001,holemat,'X',0,24)
    # Detailed printed bindings replace the repeated monochrome spine recipe.
    library_shelf_books()
    before_book=set(bpy.data.objects)
    face_out_picture_book(.495,.758,.059,white,teal,blockred)
    grounded_group('Inclined face-out board book',set(bpy.data.objects)-before_book,(.495,.758,.059),(0,0,-.09),.059)
    # Woven storage basket, with thickness, rim, individual vertical strips.
    fabric=pbr('Scanned cotton knit storage bin','cotton_jersey','2k',LOOK['fabric_texture_height_m'],[.70,.95],.34,(.85,.89,.79,1))
    fabric.node_tree.nodes.get('Principled BSDF').inputs['Sheen Weight'].default_value=.30
    def soft_bin_surface(point):
        x,y,z=point;u=max(-1,min(1,(x-.77)/.137));h=max(0,min(1,(z-.059)/.135))
        front=max(0,min(1,(.86-y)/.09));dip=.0040*(1-u*u)*front*h**4
        return (x,y+.0019*math.sin(3*math.pi*u+.25)*math.sin(math.pi*h)*front,z-dip)
    def fabric_ring(points):
        dense=[]
        for i,a in enumerate(points):
            b=points[(i+1)%len(points)]
            for j in range(4):dense.append(soft_bin_surface(tuple(a[k]+(b[k]-a[k])*j/4 for k in range(3))))
        return dense
    loops=[fabric_ring(rounded_rect(.77,.86,.251,.197,.012,.059)),fabric_ring(rounded_rect(.77,.86,.274,.220,.015,.194)),
           fabric_ring(rounded_rect(.77,.86,.266,.212,.011,.194)),fabric_ring(rounded_rect(.77,.86,.243,.189,.008,.064))]
    verts=[co for ring in loops for co in ring];count=len(loops[0]);faces=[]
    for ring in range(3):
        for j in range(count):faces.append((ring*count+j,ring*count+(j+1)%count,(ring+1)*count+(j+1)%count,(ring+1)*count+j))
    faces.append(tuple(range(3*count,4*count)))
    basket=mesh('Open woven cotton storage basket',verts,faces,fabric)
    for poly in basket.data.polygons:poly.use_smooth=True
    rimpoints=fabric_ring(rounded_rect(.77,.86,.271,.217,.014,.194));tube('Basket sewn upper rim',rimpoints+[rimpoints[0]],.0022,fabric)
    for xx,yy in [(.647,.771),(.893,.771),(.647,.949),(.893,.949)]:
        seam=[soft_bin_surface((xx+(.003 if xx<.77 else -.003)*(1-h),yy,.064+h*.125)) for h in [j/32 for j in range(33)]]
        tube('Basket vertical folded seam',seam,.00052,fabric)
    stitchmat=material('Unbleached cotton basket stitching',(.68,.64,.53,1),.86)
    for i in range(70):
        xx=.650+i*.00345
        points=[soft_bin_surface((xx+dx,.7497,.187)) for dx in [0,.00125]]
        tube('Basket rim lockstitch',points,.00011,stitchmat)
    handle=material('Basket leather handle',(.17,.095,.045,1),.56)
    box('Basket front handle',(.77,.750,.161),(.065,.002,.014),handle,.003)
    for xx in [.744,.796]:cylinder('Basket handle rivet',(xx,.7485,.161),.0017,.001,steel,'Y',.0001,20)
    # Plain woven basket front: no label patch, lettering or label stitches.
    toy_bin_contents()
    cabinet_group=empty('Grounded toy storage group')
    for ob in set(bpy.data.objects)-cabinet_before-{cabinet_group}:
        if ob.parent is None:ob.parent=cabinet_group
    cabinet_group.location.x=-.10
    # HDRI is lighting/reflection only; all near/mid background is 3D.
    world=bpy.data.worlds.new('Window sky and garden illumination');bpy.context.scene.world=world;world.use_nodes=True
    wn=world.node_tree.nodes;wl=world.node_tree.links;env=wn.new('ShaderNodeTexEnvironment');env.image=bpy.data.images.load(str(ASSETS/'residential_garden/residential_garden_1k.hdr'),check_existing=True)
    tc=wn.new('ShaderNodeTexCoord');mapping=wn.new('ShaderNodeMapping');mapping.inputs['Rotation'].default_value[2]=LOOK['lighting']['hdri_rotation_z_rad']
    wl.new(tc.outputs['Generated'],mapping.inputs['Vector']);wl.new(mapping.outputs[0],env.inputs['Vector']);wl.new(env.outputs['Color'],wn['Background'].inputs[0]);wn['Background'].inputs[1].default_value=LOOK['lighting']['hdri_strength']
    def area(name,pos,energy,color,size,target,shape='DISK',size_y=None):
        light=bpy.data.lights.new(name,'AREA');light.energy=energy;light.color=color;light.shape=shape;light.size=size
        if size_y is not None:light.size_y=size_y
        o=bpy.data.objects.new(name,light);bpy.context.collection.objects.link(o);o.location=pos;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
    area('Sky through real window',(-1.68,-.05,1.27),LOOK['lighting']['window_area_W'],LOOK['lighting']['window_color'],LOOK['lighting'].get('window_width_m',.94),LOOK['lighting'].get('window_target_m',[-.68,-.05,1.27]),'RECTANGLE',LOOK['lighting'].get('window_height_m',1.30))
    area('Camera side room fill',(.30,-.95,1.55),LOOK['lighting']['room_fill_W'],(.78,.87,1),1.5,(0,0,.05))
    sun=bpy.data.lights.new('Soft daylight through window','SUN');sun.energy=LOOK['lighting']['sun_strength'];sun.angle=LOOK['lighting']['sun_angle_rad'];sun.color=LOOK['lighting']['sun_color']
    so=bpy.data.objects.new('Soft daylight through window',sun);bpy.context.collection.objects.link(so);so.rotation_euler=Vector(LOOK['lighting'].get('sun_direction',[1.7,.35,-1.28])).to_track_quat('-Z','Y').to_euler()
    bpy.ops.object.camera_add(location=cfg['appearance']['camera']);camera=bpy.context.object;camera.name='Fixed side front camera'
    camera.rotation_euler=(Vector(cfg['appearance']['target'])-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.lens=cfg['appearance']['lens_mm'];camera.data.clip_start=.005;camera.data.clip_end=20;optics=LOOK.get('camera_optics',{});camera.data.dof.use_dof=optics.get('dof_enabled',False);camera.data.dof.aperture_fstop=optics.get('fstop',11.);camera.data.dof.focus_distance=optics.get('focus_distance_m',1.85);camera.data.dof.aperture_blades=optics.get('aperture_blades',7)
    sc=bpy.context.scene;sc.camera=camera;sc.unit_settings.system='METRIC';sc.unit_settings.scale_length=1.
    ren=cfg['render'];sc.render.engine=ren['engine'];sc.cycles.samples=ren['samples'];sc.cycles.use_denoising=ren['denoise']
    sc.cycles.max_bounces=8;sc.cycles.diffuse_bounces=4;sc.cycles.glossy_bounces=4;sc.render.use_persistent_data=True
    sc.render.resolution_x=ren['width'];sc.render.resolution_y=ren['height'];sc.render.resolution_percentage=100;sc.render.fps=ren['fps'];sc.frame_start=1;sc.frame_end=ren['frames'];sc.render.image_settings.file_format='PNG';sc.render.use_motion_blur=False
    sc.view_settings.view_transform='AgX';sc.view_settings.look='AgX - Medium High Contrast';sc.view_settings.exposure=LOOK.get('exposure',0.);sc.render.film_transparent=False
    objects={'car':car,'wheels':wheels,'baffle':baffle,'helix':helix}
    # An appearance overlay can name a look module in appearance/ that post-processes this build.
    if LOOK.get('look_module'):
        import importlib
        importlib.import_module(LOOK['look_module']).apply(cfg,data,objects,gray)
    return objects

def apply_frame(cfg,data,frame,objects):
    # body_pose rows: chassis, wheel_0..3, baffle; only the baffle row when the car is deleted.
    for i,o in enumerate([*([objects['car'],*objects['wheels']] if objects['car'] else []),objects['baffle']]):
        pose=data['body_pose'][frame,i];o.location=pose[:3];o.rotation_mode='QUATERNION';o.rotation_quaternion=pose[3:]
    if objects['helix']:
        for p,co in zip(objects['helix'].data.splines[0].points,spring_points(cfg,float(data['spring_compression'][frame]))):p.co=co
        objects['helix'].data.update_tag()
    bpy.context.view_layer.update()
