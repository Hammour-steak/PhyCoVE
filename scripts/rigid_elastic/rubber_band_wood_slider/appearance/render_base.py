"""Blender helpers of the rubber-band toy: materials, primitives, scanned assets and the hand sketch."""
import hashlib,json,math,random,sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from pcve_assets import asset
A=asset('scenes/rubber_band_wood_slider')
CASES=['source','young_x0p5','mass_x3','friction_x2','delete_band','add_stop']


def mat(name,color,rough=.45,metal=0.):
    m=bpy.data.materials.new(name);m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Roughness'].default_value=rough;bs.inputs['Metallic'].default_value=metal
    return m

def box(name,loc,size,material,bevel=.0008):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if material:o.data.materials.append(material)
    # Physical-sized box mapping: long grain runs along its X axis. Separate
    # faces use local coordinates, with no generated-coordinate swimming.
    uv=o.data.uv_layers.active
    seed=int.from_bytes(hashlib.sha256(name.encode()).digest()[:4],'little');rng=random.Random(seed)
    offset_uv=(rng.uniform(.10,.90),rng.uniform(.10,.90))
    for face in o.data.polygons:
        normal=face.normal
        axes=(0,1) if abs(normal.z)>.5 else ((0,2) if abs(normal.y)>.5 else (1,2))
        for li in face.loop_indices:
            co=o.data.vertices[o.data.loops[li].vertex_index].co
            uv.data[li].uv=(co[axes[0]]+offset_uv[0],co[axes[1]]+offset_uv[1])
    if bevel:
        mod=o.modifiers.new('hand_sanded_edges','BEVEL');mod.width=bevel;mod.segments=3
        mod=o.modifiers.new('weighted_normals','WEIGHTED_NORMAL')
    return o

def cylinder(name,loc,radius,depth,material,vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=loc)
    o=bpy.context.object;o.name=name;o.data.materials.append(material)
    uv=o.data.uv_layers.active
    for face in o.data.polygons:
        for li in face.loop_indices:
            co=o.data.vertices[o.data.loops[li].vertex_index].co
            if abs(face.normal.z)<.5:
                uv.data[li].uv=(co.z+.27,math.atan2(co.y,co.x)*radius+.23)
            else:uv.data[li].uv=(co.x+.27,co.y+.23)
    bevel=o.modifiers.new('rounded_cut','BEVEL');bevel.width=.00035;bevel.segments=3
    o.modifiers.new('weighted_normals','WEIGHTED_NORMAL')
    return o

def stroke(name,points,radius,material):
    c=bpy.data.curves.new(name,'CURVE');c.dimensions='3D';c.bevel_depth=radius;c.bevel_resolution=2
    s=c.splines.new('POLY');s.points.add(len(points)-1)
    for p,co in zip(s.points,points):p.co=(*co,1)
    o=bpy.data.objects.new(name,c);bpy.context.scene.collection.objects.link(o);o.data.materials.append(material);return o

def imported(key):
    with bpy.data.libraries.load(str(A/key/'asset.blend'),link=False) as (src,dst):dst.objects=src.objects
    objects=[]
    for o in dst.objects:
        if o and o.type not in ['LIGHT','CAMERA']:
            bpy.context.scene.collection.objects.link(o);objects.append(o)
    bpy.context.view_layer.update()
    return objects

def bounds(objects):
    ps=[o.matrix_world@Vector(c) for o in objects if o.type=='MESH' for c in o.bound_box]
    return Vector([min(p[i] for p in ps) for i in range(3)]),Vector([max(p[i] for p in ps) for i in range(3)])

def transformed_group(objects,matrix):
    # Bake the existing hierarchy's world matrices before removing parents.
    worlds=[o.matrix_world.copy() for o in objects]
    for o,m in zip(objects,worlds):o.parent=None;o.matrix_world=matrix@m
    bpy.context.view_layer.update()

def scanned_wood(name,key,lighten=1.,rough_floor=.42):
    m=mat(name,(.6,.4,.2));nt=m.node_tree;n=nt.nodes;l=nt.links;bs=n.get('Principled BSDF')
    rec=json.loads((A/key/'manifest.json').read_text())
    metres=(rec.get('dimensions_mm') or [1000.,1000.])[0]/1000
    tc=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeVectorMath');mapping.operation='SCALE'
    mapping.inputs[3].default_value=1/metres;l.new(tc.outputs['UV'],mapping.inputs[0])
    for ch,entry in rec['files'].items():
        im=n.new('ShaderNodeTexImage');im.image=bpy.data.images.load(str(A/entry['path'].removeprefix('assets/')),check_existing=True)
        l.new(mapping.outputs[0],im.inputs['Vector'])
        if ch=='Diffuse':
            if lighten!=1.:
                hue=n.new('ShaderNodeHueSaturation');hue.inputs['Saturation'].default_value=.65;hue.inputs['Value'].default_value=lighten
                l.new(im.outputs[0],hue.inputs['Color']);l.new(hue.outputs[0],bs.inputs['Base Color'])
            else:l.new(im.outputs[0],bs.inputs['Base Color'])
        elif ch=='Rough':
            im.image.colorspace_settings.name='Non-Color'
            remap=n.new('ShaderNodeMapRange');remap.inputs['To Min'].default_value=rough_floor;remap.inputs['To Max'].default_value=.78
            l.new(im.outputs[0],remap.inputs[0]);l.new(remap.outputs[0],bs.inputs['Roughness'])
        elif ch=='nor_gl':
            im.image.colorspace_settings.name='Non-Color';normal=n.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.35
            l.new(im.outputs[0],normal.inputs['Color']);l.new(normal.outputs[0],bs.inputs['Normal'])
    # Fine longitudinal fibres modulate the normal at a physical micrometre
    # amplitude. The scan supplies colour and larger features; no painted dirt.
    coord=n.new('ShaderNodeTexCoord');stretch=n.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY'
    stretch.inputs[1].default_value=(140.,6500.,6500.);l.new(coord.outputs['Object'],stretch.inputs[0])
    fibre=n.new('ShaderNodeTexNoise');fibre.inputs['Scale'].default_value=1.;fibre.inputs['Detail'].default_value=2.
    l.new(stretch.outputs[0],fibre.inputs[0]);micro=n.new('ShaderNodeBump');micro.inputs['Strength'].default_value=.24;micro.inputs['Distance'].default_value=.000012
    old_normal=list(bs.inputs['Normal'].links)
    if old_normal:l.new(old_normal[0].from_socket,micro.inputs['Normal'])
    l.new(fibre.outputs['Fac'],micro.inputs['Height']);l.new(micro.outputs[0],bs.inputs['Normal'])
    return m

def handwritten_paper():
    # Lightly warped physical paper with irregular pencil strokes, no CAD text.
    paper=mat('slightly_fibrous_uncoated_paper',(.73,.72,.68),.88)
    n=paper.node_tree.nodes;l=paper.node_tree.links;bs=n.get('Principled BSDF');tc=n.new('ShaderNodeTexCoord')
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=9000;l.new(tc.outputs['Object'],noise.inputs[0])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12;bump.inputs['Distance'].default_value=.000016
    l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal'])
    vertices=[];faces=[];nx=22;ny=16
    for j in range(ny):
        for i in range(nx):
            x=(i/(nx-1)-.5)*.122;y=(j/(ny-1)-.5)*.084
            z=.00028+.00025*(x/.061)**4+.00010*math.sin(y*65)
            vertices.append((x,y,z))
    for j in range(ny-1):
        for i in range(nx-1):
            a=j*nx+i;faces.append((a,a+1,a+1+nx,a+nx))
    mesh=bpy.data.meshes.new('real_paper_grid');mesh.from_pydata(vertices,[],faces);mesh.materials.append(paper)
    o=bpy.data.objects.new('small_hand_sketch',mesh);bpy.context.scene.collection.objects.link(o)
    root=bpy.data.objects.new('paper_and_ink',None);bpy.context.scene.collection.objects.link(root);o.parent=root
    root.location=(-.035,.083,0);root.rotation_euler.z=-.14
    ink=mat('faint_graphite',(.09,.085,.078),.9);rng=random.Random(760)
    lines=[[(-.042,-.018),(.042,-.018),(.042,.012),(-.042,.012),(-.042,-.018)],
        [(.017,-.014),(.037,-.014),(.037,.009),(.017,.009),(.017,-.014)],
        [(-.025,-.004),(.022,-.005)],[(-.025,.002),(.022,.001)],
        [(-.042,.023),(.040,.023)],[(.039,.023),(.034,.026)],[(.039,.023),(.034,.020)]]
    for k,line in enumerate(lines):
        pts=[]
        for a,b in zip(line[:-1],line[1:]):
            for u in np.linspace(0,1,25):
                x=a[0]*(1-u)+b[0]*u+rng.uniform(-.00012,.00012)
                y=a[1]*(1-u)+b[1]*u+rng.uniform(-.00012,.00012)
                z=.00031+.00025*(x/.061)**4+.00010*math.sin(y*65)
                pts.append((x,y,z))
        draw=stroke('handdrawn_pencil_line_'+str(k),pts,rng.uniform(.000055,.00009),ink);draw.parent=root

