"""SI manufactured toy scene for the silicone bridge. All motion and shell vertices come from the solved caches.

- the silicone is translucent pigmented platinum silicone (random-walk subsurface), smoothed by
  subdivision before the 6 mm solidify, and its fixed 20 mm end bands are rendered lying in
  6.2 mm rebates of the road deck, held by aluminium clamp plates and pan-head screws outside
  the car's path;
- the room is dressed with CC0 Poly Haven scans (pine cube shelf, potted plant, wicker basket,
  carved wooden elephant, baseball) at their native metric size;
- light comes only through the real window opening (sun + HDRI sky, guided by a portal); there are
  no hidden key or fill lights;
- the car and wheels are keyframed from the cache so Cycles renders real motion blur.
The diecast car, road and shared material helpers come from the original metric toy-room builder.
"""

import json
import math
import random
import sys
import sys as _pcve_assets_sys
from pathlib import Path, Path as _PcveAssetsPath

import bmesh
import bpy
from mathutils import Vector
from pcve_assets import scene_asset, asset as shared_asset
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
sys.path.append(str(Path(__file__).resolve().parents[3]))


ASSETS = scene_asset(Path(__file__).resolve().parents[1], 'assets/pbr')


def material(name, color, roughness=.5, metallic=0, coat=0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = color
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    for key, value in [('Base Color', color), ('Roughness', roughness), ('Metallic', metallic),
                       ('Coat Weight', coat), ('Coat Roughness', .24)]:
        p.inputs[key].default_value = value
    return m


def pbr_wood(name, asset, tint=(1, 1, 1), rough_range=(.32, .54), normal_strength=.3, diffuse_tag='diff'):
    """Metric UVs divide coordinates by the provider's measured tile size."""
    m = material(name, (.45, .3, .15, 1), coat=.10)
    n, l = m.node_tree.nodes, m.node_tree.links
    p, images = n.get('Principled BSDF'), {}
    for channel, tag in [('Diffuse', diffuse_tag), ('Rough', 'rough'), ('Normal', 'nor_gl')]:
        path = ASSETS / asset / f'{asset}_{tag}_2k.jpg'
        if not path.is_file():
            raise FileNotFoundError(f'{path}: run fetch_assets.py first')
        node = n.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(path), check_existing=True)
        if channel != 'Diffuse':
            node.image.colorspace_settings.name = 'Non-Color'
        node.label = f'CC0 Poly Haven {asset} {channel}'
        images[channel] = node
    mul = n.new('ShaderNodeMixRGB')
    mul.blend_type, mul.inputs[0].default_value = 'MULTIPLY', 1
    mul.inputs[2].default_value = (*tint, 1)
    l.new(images['Diffuse'].outputs[0], mul.inputs[1])
    # Slight board-to-board variation belongs to the material, not displacement.
    info, variation = n.new('ShaderNodeObjectInfo'), n.new('ShaderNodeMapRange')
    variation.inputs['To Min'].default_value, variation.inputs['To Max'].default_value = .95, 1.035
    l.new(info.outputs['Random'], variation.inputs['Value'])
    board_tone = n.new('ShaderNodeMixRGB'); board_tone.blend_type = 'MULTIPLY'
    board_tone.inputs[0].default_value = 1
    l.new(mul.outputs[0], board_tone.inputs[1]); l.new(variation.outputs[0], board_tone.inputs[2])
    l.new(board_tone.outputs[0], p.inputs['Base Color'])
    remap = n.new('ShaderNodeMapRange')
    remap.inputs['To Min'].default_value, remap.inputs['To Max'].default_value = rough_range
    l.new(images['Rough'].outputs[0], remap.inputs['Value'])
    l.new(remap.outputs[0], p.inputs['Roughness'])
    normal = n.new('ShaderNodeNormalMap')
    normal.inputs['Strength'].default_value = normal_strength
    l.new(images['Normal'].outputs[0], normal.inputs['Color'])
    l.new(normal.outputs[0], p.inputs['Normal'])
    return m


def end_grain():
    m = material('Maple cut end grain', (.49, .36, .21, 1), .52)
    n, l = m.node_tree.nodes, m.node_tree.links
    tc, mapping = n.new('ShaderNodeTexCoord'), n.new('ShaderNodeVectorMath')
    mapping.operation, mapping.inputs[1].default_value = 'ADD', (0, .027, -.04)
    l.new(tc.outputs['Object'], mapping.inputs[0])
    wave = n.new('ShaderNodeTexWave')
    wave.wave_type, wave.rings_direction = 'RINGS', 'X'
    wave.inputs['Scale'].default_value, wave.inputs['Distortion'].default_value = 38, 8
    wave.inputs['Detail'].default_value = 4
    wave.inputs['Detail Scale'].default_value = 2.6
    l.new(mapping.outputs[0], wave.inputs['Vector'])
    ramp = n.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (.32, .23, .14, 1)
    ramp.color_ramp.elements[1].color = (.39, .29, .18, 1)
    l.new(wave.outputs['Color'], ramp.inputs[0])
    l.new(ramp.outputs[0], n.get('Principled BSDF').inputs['Base Color'])
    return m


def uv_metres(obj, tile_m=1, offset=(0, 0), grain_axis='X'):
    uv = obj.data.uv_layers.active or obj.data.uv_layers.new(name='Metric grain UV')
    for face in obj.data.polygons:
        axis = max(range(3), key=lambda i: abs(face.normal[i]))
        for index in face.loop_indices:
            co = obj.data.vertices[obj.data.loops[index].vertex_index].co
            if axis == 2:
                a, b = (co.x, co.y) if grain_axis == 'X' else (co.y, co.x)
            elif axis == 1:
                a, b = (co.x, co.z) if grain_axis == 'X' else (co.z, co.x)
            else:
                a, b = (co.z, co.y) if grain_axis == 'Z' else (co.y, co.z)
            uv.data[index].uv = (a / tile_m + offset[0], b / tile_m + offset[1])


def box(name, pos, size, mat, bevel=.001, rotation=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=pos)
    o = bpy.context.object
    o.name, o.dimensions = name, size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if rotation:
        o.rotation_euler = rotation
    if mat:
        o.data.materials.append(mat)
    uv_metres(o)
    if bevel:
        mod = o.modifiers.new('Manufactured edge radius in metres', 'BEVEL')
        mod.width, mod.segments = bevel, 3
        o.modifiers.new('Weighted corner normals', 'WEIGHTED_NORMAL')
    return o


def wood_box(name, pos, size, mat, rng, end=None, bevel=.001, grain_axis='X'):
    o = box(name, pos, size, mat, bevel)
    uv_metres(o, 1., (rng.random(), rng.random()), grain_axis)
    if end:
        o.data.materials.append(end)
        for p in o.data.polygons:
            if abs(p.normal.x if grain_axis == 'X' else p.normal.z) > .9:
                p.material_index = 1
    return o


def cylinder(name, pos, radius, depth, mat, rotation=(math.pi / 2, 0, 0), bevel=.0005, vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                      location=pos, rotation=rotation)
    o = bpy.context.object
    o.name = name
    if mat:
        o.data.materials.append(mat)
    if bevel:
        mod = o.modifiers.new('Moulded edge', 'BEVEL')
        mod.width, mod.segments = bevel, 3
    for poly in o.data.polygons:
        poly.use_smooth = True
    o.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return o


def mesh_object(name, verts, faces, mat, bevel=0):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    o = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(o)
    mesh.materials.append(mat)
    if bevel:
        b = o.modifiers.new('Pressed rounded edges', 'BEVEL')
        b.width, b.segments = bevel, 3
        o.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return o


def recalc_normals(obj):
    bm = bmesh.new(); bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data); bm.free(); obj.data.update()


def path_tube(name, points, radius, mat, parent=None, closed=False):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions, curve.bevel_depth, curve.bevel_resolution = '3D', radius, 3
    spline = curve.splines.new('POLY'); spline.points.add(len(points) - 1)
    for p, xyz in zip(spline.points, points): p.co = (*xyz, 1)
    spline.use_cyclic_u = closed
    obj = bpy.data.objects.new(name, curve); bpy.context.collection.objects.link(obj)
    curve.materials.append(mat)
    if parent: obj.parent = parent
    return obj


def surface_finish(mat, scale, rough_min, rough_max, bump_m=0):
    """Fine manufacturing variation in metres, kept below silhouette scale."""
    n, l = mat.node_tree.nodes, mat.node_tree.links
    tc, noise = n.new('ShaderNodeTexCoord'), n.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = scale
    l.new(tc.outputs['Object'], noise.inputs['Vector'])
    remap = n.new('ShaderNodeMapRange')
    remap.inputs['To Min'].default_value, remap.inputs['To Max'].default_value = rough_min, rough_max
    l.new(noise.outputs['Fac'], remap.inputs['Value'])
    p = n.get('Principled BSDF'); l.new(remap.outputs[0], p.inputs['Roughness'])
    if bump_m:
        previous_normal = p.inputs['Normal'].links[0].from_socket if p.inputs['Normal'].is_linked else None
        bump = n.new('ShaderNodeBump'); bump.inputs['Distance'].default_value = bump_m
        bump.inputs['Strength'].default_value = .16
        if previous_normal: l.new(previous_normal, bump.inputs['Normal'])
        l.new(noise.outputs['Fac'], bump.inputs['Height']); l.new(bump.outputs[0], p.inputs['Normal'])


def empty(name):
    o = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(o)
    return o


def parent_local(obj, parent, pos=(0, 0, 0)):
    obj.parent, obj.location = parent, pos
    return obj


def lathe_tire(radius, width, mat):
    """Rounded sidewalls, exact solved outer radius and axial width."""
    profile = [(-width / 2, .0082), (-width / 2, radius * .91),
               (-width / 2 + .0006, radius * .985), (-width / 2 + .0012, radius),
               (width / 2 - .0012, radius), (width / 2 - .0006, radius * .985),
               (width / 2, radius * .91), (width / 2, .0082), (-width / 2, .0082)]
    verts = [(r * math.sin(k * math.tau / 64), y, r * math.cos(k * math.tau / 64))
             for y, r in profile for k in range(64)]
    faces = [(j * 64 + k, j * 64 + (k + 1) % 64, (j + 1) * 64 + (k + 1) % 64, (j + 1) * 64 + k)
             for j in range(len(profile) - 1) for k in range(64)]
    o = mesh_object('Rounded rubber tire', verts, faces, mat)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def printed_road_material(wood):
    """Thin matte road paint with irregular submillimetre edges on actual maple."""
    mat=wood.copy();mat.name='Graphite road print over visible maple margins'
    n,l=mat.node_tree.nodes,mat.node_tree.links;p=n.get('Principled BSDF')
    base=p.inputs['Base Color'].links[0].from_socket
    tc,sep=n.new('ShaderNodeTexCoord'),n.new('ShaderNodeSeparateXYZ')
    l.new(tc.outputs['Object'],sep.inputs[0])
    absolute=n.new('ShaderNodeMath');absolute.operation='ABSOLUTE';l.new(sep.outputs['Y'],absolute.inputs[0])
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=1800
    l.new(tc.outputs['Object'],noise.inputs['Vector'])
    edge=n.new('ShaderNodeMapRange');edge.inputs['To Min'].default_value=.0574;edge.inputs['To Max'].default_value=.0585
    l.new(noise.outputs['Fac'],edge.inputs['Value'])
    mask=n.new('ShaderNodeMath');mask.operation='LESS_THAN'
    l.new(absolute.outputs[0],mask.inputs[0]);l.new(edge.outputs[0],mask.inputs[1])
    paint=n.new('ShaderNodeMixRGB');paint.blend_type='MIX'
    l.new(mask.outputs[0],paint.inputs[0]);l.new(base,paint.inputs[1]);paint.inputs[2].default_value=(.070,.082,.079,1)
    l.new(paint.outputs[0],p.inputs['Base Color'])
    surface_finish(mat,2100,.50,.68,.000006)
    p.inputs['Coat Weight'].default_value=.025
    return mat


def import_metric_prop(asset,position,longest_horizontal_m,angle=0):
    """Normalize the imported world bounds, then rotate and ground the asset."""
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(ASSETS/asset/(asset+'_2k.gltf')))
    imported=set(bpy.data.objects)-before
    bpy.context.view_layer.update()
    points=[obj.matrix_world@Vector(v) for obj in imported if obj.type=='MESH' for v in obj.bound_box]
    low=Vector([min(v[i] for v in points) for i in range(3)])
    high=Vector([max(v[i] for v in points) for i in range(3)])
    factor=longest_horizontal_m/max(high.x-low.x,high.y-low.y)
    root=empty('CC0 '+asset)
    for obj in imported:
        if obj.parent not in imported:
            matrix=obj.matrix_world.copy();obj.parent=root;obj.matrix_world=matrix
    root.scale=(factor,)*3;root.rotation_euler.z=angle
    offset=Vector(((low.x+high.x)/2,(low.y+high.y)/2,low.z))*factor
    offset.rotate(root.rotation_euler)
    root.location=Vector(position)-offset
    root['asset_id']=asset;root['license']='CC0-1.0'
    root['original_bbox_m']=list(high-low);root['uniform_scale']=factor
    root['longest_horizontal_m']=longest_horizontal_m
    bpy.context.view_layer.update()
    return root


def build_car(cfg, red, rubber, alloy, black, glass, paint, steel):
    """Original modern diecast hatchback, fitted to the five unchanged rigid bodies."""
    car, wheels = empty('Rigid chassis from solved cache'), []
    spec=cfg['appearance']['car_visual_design']
    blue = material('Muted mineral blue factory diecast enamel',spec['paint_color_linear'],.29,spec['paint_metallic'],spec['paint_coat_weight'])
    surface_finish(blue,4200,*spec['paint_roughness_range'],.0000007)
    blue.node_tree.nodes.get('Principled BSDF').inputs['Coat Roughness'].default_value=.19
    ivory=blue
    rubber=material('Fine moulded carbon rubber tire',(.011,.012,.013,1),.64)
    surface_finish(rubber,6200,.59,.68,.0000015)
    trim = material('Satin graphite arch and sill moulding', (.013, .017, .021, 1), .46)
    rim = material('Satin graphite aluminium wheel casting',spec['rim_color_linear'],spec['rim_roughness'],spec['rim_metallic'])
    seat = material('Warm grey moulded cabin upholstery', (.115, .105, .086, 1), .73)
    lens = material('Clear prismatic headlamp polycarbonate', (.73, .80, .83, 1), .075, .10, .60)
    lens.node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value = .32
    tail = material('Ruby translucent tail lamp', (.23, .0025, .0018, 1), .15, .07, .50)
    glass.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = spec['glass_color_linear']
    glass.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value = spec['glass_roughness']
    glass.node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value = spec['glass_transmission']
    glass.node_tree.nodes.get('Principled BSDF').inputs['IOR'].default_value=spec['glass_ior']

    # Closed, crowned coachwork. Dense cubic interpolation avoids a stack of boxes.
    ribs = [(-.054,.0205,.007,.020),(-.051,.026,.004,.024),(-.043,.0313,.003,.0253),
            (-.030,.0325,.003,.0258),(-.010,.0327,.003,.0257),(.010,.0325,.003,.0254),
            (.027,.0321,.003,.0255),(.041,.0312,.004,.0247),(.050,.0268,.005,.0236),
            (.054,.0228,.007,.0207)]
    def section(x):
        i = min(len(ribs)-2, next((j for j in range(len(ribs)-1) if x <= ribs[j+1][0]), len(ribs)-2))
        t = (x-ribs[i][0])/(ribs[i+1][0]-ribs[i][0])
        out=[]
        for k in [1,2,3]:
            a,b,c,d=[ribs[max(0,min(len(ribs)-1,j))][k] for j in [i-1,i,i+1,i+2]]
            out.append(.5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t))
        return out
    verts=[]; nx=81; ring=96
    for j in range(nx):
        x=-.054+.108*j/(nx-1); w,low,high=section(x)
        for k in range(ring):
            a=math.tau*k/ring; sy,sz=math.cos(a),math.sin(a)
            y=w*math.copysign(abs(sy)**spec['body_section_exponents'][0],sy)
            z=(low+high)/2+(high-low)/2*math.copysign(abs(sz)**spec['body_section_exponents'][1],sz)
            verts.append((x,y,z))
    faces=[tuple(reversed(range(ring))),tuple(range((nx-1)*ring,nx*ring))]
    faces += [(j*ring+k,j*ring+(k+1)%ring,(j+1)*ring+(k+1)%ring,(j+1)*ring+k)
              for j in range(nx-1) for k in range(ring)]
    body=parent_local(mesh_object('Continuous curved modern diecast coachwork',verts,faces,blue),car)
    recalc_normals(body)
    for x in [-.0375,.0375]:
        cutter=cylinder('Temporary manifold wheel arch tool',(x,0,0),.0153,.09,None,bevel=0,vertices=128)
        mod=body.modifiers.new('True open wheel aperture','BOOLEAN');mod.operation,mod.object,mod.solver='DIFFERENCE',cutter,'EXACT'
        bpy.context.view_layer.objects.active=body;bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cutter,do_unlink=True)
    for face in body.data.polygons:face.use_smooth=True
    mod=body.modifiers.new('Soft painted casting edges','BEVEL');mod.width,mod.segments,mod.limit_method=.00025,3,'ANGLE'
    # Stamped fender shoulders cover the upper tire width rather than exposing
    # the complete cylinder outside a narrow floating-looking body.
    for axle in [-.0375,.0375]:
        for side in [-1,1]:
            verts=[];na,nr=80,8
            for j in range(nr+1):
                u=j/nr;r=.0153+(.0170-.0153)*u
                for k in range(na+1):
                    angle=.12+(math.pi-.24)*k/na;x=axle+r*math.cos(angle);z=r*math.sin(angle)
                    w,lo,hi=section(x);t=max(-.999,min(.999,(z-(lo+hi)/2)/((hi-lo)/2)))
                    sine=abs(t)**(1/spec['body_section_exponents'][1]);body_y=w*max(0,1-sine*sine)**(spec['body_section_exponents'][0]/2)
                    y=body_y+(spec['formed_fender_outer_y_m']-body_y)*(1-u)**.7
                    verts.append((x,side*(y+.00002),z))
            faces=[(j*(na+1)+k,j*(na+1)+k+1,(j+1)*(na+1)+k+1,(j+1)*(na+1)+k) for j in range(nr) for k in range(na)]
            fender=parent_local(mesh_object('Integrated formed wheel arch shoulder',verts,faces,blue),car)
            recalc_normals(fender)
            for f in fender.data.polygons:f.use_smooth=True
            solid=fender.modifiers.new('Thin diecast fender flange','SOLIDIFY');solid.thickness=.0003;solid.offset=-1
    parent_local(box('Recessed detailed undertray',(0,0,0),(.094,.047,.003),black,.0007),car,(0,0,.0045))
    # A low contrast roof and swept pillars enclose actual transparent windows.
    roof_rows=[(-.033,.0188,.0386),(-.031,.0205,.0400),(-.026,.0218,.0408),
               (-.014,.0220,.041),(.005,.0217,.0409),(.013,.0205,.0401),(.015,.0190,.0393)]
    verts=[]; roof_n=61
    for j in range(roof_n):
        x=roof_rows[0][0]+(roof_rows[-1][0]-roof_rows[0][0])*j/(roof_n-1)
        i=min(len(roof_rows)-2,next((q for q in range(len(roof_rows)-1) if x<=roof_rows[q+1][0]),len(roof_rows)-2))
        t=(x-roof_rows[i][0])/(roof_rows[i+1][0]-roof_rows[i][0]); out=[]
        for k in [1,2]:
            a,b,c,d=[roof_rows[max(0,min(len(roof_rows)-1,q))][k] for q in [i-1,i,i+1,i+2]]
            out.append(.5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t))
        w,h=out;h=min(.041,h)
        for k in range(25):
            u=-1+2*k/24;verts.append((x,w*u,h-.0017*u*u))
    faces=[(j*25+k,(j+1)*25+k,(j+1)*25+k+1,j*25+k+1) for j in range(roof_n-1) for k in range(24)]
    roof=parent_local(mesh_object('Crowned continuous ivory roof',verts,faces,ivory),car);recalc_normals(roof)
    for face in roof.data.polygons:face.use_smooth=True
    sol=roof.modifiers.new('Roof cast thickness inside contact envelope','SOLIDIFY');sol.thickness,sol.offset=.0007,-1
    bevel=roof.modifiers.new('Rounded painted roof edge','BEVEL');bevel.width,bevel.segments=.00025,3

    def flank_point(x,z,side,offset=.000025):
        w,lo,hi=section(x)
        t=max(-.999,min(.999,(z-(lo+hi)/2)/((hi-lo)/2)))
        sine=abs(t)**(1/spec['body_section_exponents'][1])
        y=w*max(0,1-sine*sine)**(spec['body_section_exponents'][0]/2)
        return (x,side*(y+offset),z)

    def pane(name,corners,bulge):
        points=[];nu,nv=18,12
        for j in range(nv+1):
            v=j/nv
            for i in range(nu+1):
                u=i/nu;p=Vector(corners[0])*(1-u)*(1-v)+Vector(corners[1])*u*(1-v)+Vector(corners[2])*u*v+Vector(corners[3])*(1-u)*v
                p+=Vector(bulge)*math.sin(math.pi*u)*math.sin(math.pi*v);points.append(p)
        faces=[(j*(nu+1)+i,j*(nu+1)+i+1,(j+1)*(nu+1)+i+1,(j+1)*(nu+1)+i) for j in range(nv) for i in range(nu)]
        obj=parent_local(mesh_object(name,points,faces,glass),car)
        for f in obj.data.polygons:f.use_smooth=True
        sol=obj.modifiers.new('Real thin clear moulded glazing','SOLIDIFY');sol.thickness,sol.offset=.00035,0
        path_tube(name+' thin rubber seal',corners,.00016,black,car,True)
    for side in [-1,1]:
        corners=[(-.041,side*.0270,.0250),(.0275,side*.0268,.0251),
                 (.0121,side*.0200,.0388),(-.0285,side*.0205,.0390)]
        pane('Swept transparent side window',corners,(0,side*.0007,0))
        def cast_pillar(name,points,mat):
            obj=parent_local(mesh_object(name,points,[tuple(range(len(points)))],mat),car)
            recalc_normals(obj)
            solid=obj.modifiers.new('Thin pressed diecast window frame','SOLIDIFY');solid.thickness=.00045
            edge=obj.modifiers.new('Small cast window-frame edge','BEVEL');edge.width=.00012;edge.segments=4
            return obj
        cast_pillar('Continuous cast front window pillar',[corners[1],(.0293,side*.0263,.0257),(.0136,side*.0198,.0385),corners[2]],blue)
        cast_pillar('Continuous cast rear window pillar',[corners[0],corners[3],(-.0306,side*.0196,.0383),(-.0442,side*.0263,.0256)],blue)
        bp=[]
        for j in range(17):
            v=j/16
            for x in [-.00855,-.00745]:bp.append((x,side*(.0271*(1-v)+.0212*v+.00072*math.sin(math.pi*v)),.0252*(1-v)+.0392*v))
        pillar=parent_local(mesh_object('Recessed solid B pillar',bp,[(2*j,2*j+1,2*j+3,2*j+2) for j in range(16)],black),car)
        recalc_normals(pillar)
        solid=pillar.modifiers.new('Moulded B-pillar thickness','SOLIDIFY');solid.thickness=.00022
        path_tube('Painted shoulder below glass',[corners[0],(-.008,side*.0285,.0250),corners[1]],.00030,blue,car)
        path_tube('Continuous dark upper window seal',[corners[3],corners[2]],.00020,black,car)
        gap=material('Restrained recessed body seam '+str(side),(.012,.024,.029,1),.62)
        for label,points in [('Front door', [(-.0078,.024),(-.0082,.009),(.0175,.009),(.0205,.021)]),
                             ('Rear door',[(-.0095,.024),(-.010,.009),(-.0195,.009)])]:
            path_tube(label+' body-following shut line',[flank_point(x0+(x1-x0)*k/14,z0+(z1-z0)*k/14,side) for (x0,z0),(x1,z1) in zip(points,points[1:]) for k in range(15)],spec['panel_gap_radius_m'],gap,car)
        for x,length in [(-.002,.0043),(-.023,.0035)]:
            handle=parent_local(box('Small inset body-colour door handle',(0,0,0),(length,.00045,.00065),blue,.00018),car,flank_point(x,.022,side,.00008))
        path_tube('Mirror mounting stalk',[(.022,side*.027,.027),(.020,side*.031,.027)],.0005,black,car)
        parent_local(box('Compact painted door mirror',(0,0,0),(.0050,.0036,.0027),blue,.0011),car,(.020,side*.0315,.0277))
        parent_local(box('Recessed mirror glass',(0,0,0),(.0002,.0028,.0018),steel,.0006),car,(.01745,side*.0315,.0278))
    pane('Swept curved front windscreen',[(.0292,-.026,.0258),(.0292,.026,.0258),
            (.0130,.0194,.0384),(.0130,-.0194,.0384)],(.0007,0,.0001))
    pane('Curved rear hatch glazing',[(-.0438,.026,.0258),(-.0438,-.026,.0258),
            (-.0300,-.0187,.0381),(-.0300,.0187,.0381)],(-.00055,0,0))
    parent_local(box('Cabin floor and parcel shelf',(0,0,0),(.063,.045,.0016),black,.0006),car,(-.007,0,.0251))
    for x in [-.023,.007]:
        for y in [-.011,.011]:
            parent_local(box('Rounded individual seat cushion',(0,0,0),(.014,.015,.0026),seat,.0012),car,(x,y,.0262))
            back=parent_local(box('Contoured seat back',(0,0,0),(.0034,.0143,.0077),seat,.0012),car,(x-.006,y,.0303));back.rotation_euler.y=-.14
            parent_local(box('Small moulded seat headrest',(0,0,0),(.0033,.0075,.0026),seat,.0011),car,(x-.0065,y,.0352))
    parent_local(box('Curved matte dashboard',(0,0,0),(.008,.044,.0037),black,.0012),car,(.019,0,.0271))
    bpy.ops.mesh.primitive_torus_add(major_radius=.0032,minor_radius=.00042,major_segments=48,minor_segments=10)
    steering=bpy.context.object;steering.name='Visible steering wheel';steering.data.materials.append(black)
    parent_local(steering,car,(.012,-.011,.031));steering.rotation_euler.y=1.05
    for y in [-.012,.009]:
        path_tube('Tiny black windscreen wiper',[(.0284,y,.0265),(.0250,y+.007,.0292)],.00016,black,car)
    path_tube('Bonnet perimeter fine shut line',[(.030,-.0258,.0251),(.031,0,.02555),(.030,.0258,.0251)],.000085,black,car)
    # Clean, modern front: inset grille, slim optics and painted soft bumpers.
    for x in [-.05365,.05365]:
        parent_local(box('Integrated painted bumper',(0,0,0),(.0025,.049,.0068),blue,.0020),car,(x,0,.0097))
        parent_local(box('Graphite lower bumper insert',(0,0,0),(.0022,.035,.0029),trim,.0011),car,(x,0,.0077))
    parent_local(box('Recessed fine front air intake',(0,0,0),(.00065,.022,.0040),black,.0009),car,(.0542,0,.0165))
    for yy in [-.008,-.004,0,.004,.008]:
        parent_local(box('Discrete grille vertical vane',(0,0,0),(.00020,.00025,.0025),steel,.00007),car,(.05457,yy,.0165))
    for side in [-1,1]:
        y=side*.0165
        parent_local(box('Inset modern headlamp housing',(0,0,0),(.0005,.0074,.0025),black,.0008),car,(.0542,y,.0170))
        parent_local(box('Inset clear prismatic headlamp',(0,0,0),(.0006,.0067,.0019),lens,.00065),car,(.05435,y,.0171))
        for yy in [-.0023,0,.0023]:
            parent_local(box('Separate miniature headlamp reflector',(0,0,0),(.00016,.0011,.0012),rim,.00035),car,(.05467,y+yy,.0171))
        parent_local(box('Recessed ruby rear corner lamp',(0,0,0),(.00065,.0072,.0020),tail,.0006),car,(-.05415,y,.0170))
    parent_local(box('Thin inset rear lamp strip',(0,0,0),(.00065,.025,.0009),tail,.0003),car,(-.0543,0,.0170))
    for x in [-.0375,.0375]:
        parent_local(cylinder('Unpowered independent wheel axle',(0,0,0),.0011,.061,steel,bevel=.00012),car,(x,0,0))
    for x in [-.022,.022]:
        parent_local(cylinder('Realistic underside retaining screw',(0,0,0),.0013,.0003,steel,rotation=(0,0,0),bevel=.0001),car,(x,0,.0030))

    c=cfg['physics']['car']
    for i in range(4):
        wheel=empty('Rigid wheel cache pose '+str(i));wheels.append(wheel)
        parent_local(lathe_tire(c['wheel_radius_m'],c['wheel_width_m'],rubber),wheel)
        for side in [-1,1]:
            y=side*(c['wheel_width_m']/2+.00001)
            bpy.ops.mesh.primitive_torus_add(major_radius=.00855,minor_radius=.00023,major_segments=96,minor_segments=16)
            lip=bpy.context.object;lip.name='True open rounded alloy rim lip';lip.data.materials.append(rim)
            for face in lip.data.polygons:face.use_smooth=True
            parent_local(lip,wheel,(0,side*.00452,0));lip.rotation_euler.x=math.pi/2
            parent_local(cylinder('Deep recessed graphite wheel dish',(0,0,0),.0078,.00018,black,bevel=.00008,vertices=96),wheel,(0,side*.0039,0))
            for k in range(5):
                angle=k*math.tau/5
                outline=[]
                for radius,da in [(.0018,-.34),(.0040,-.20),(.0079,-.105),(.0079,.105),(.0040,.20),(.0018,.34)]:
                    outline.append((radius*math.sin(angle+da),side*.00430,radius*math.cos(angle+da)))
                spoke=parent_local(mesh_object('Solid formed recessed alloy spoke',outline,[tuple(range(6))],rim),wheel)
                recalc_normals(spoke)
                solid=spoke.modifiers.new('Thin cast wheel spoke','SOLIDIFY');solid.thickness=.00025
                edge=spoke.modifiers.new('Eased spoke casting edge','BEVEL');edge.width=.00010;edge.segments=4
            parent_local(cylinder('Small flush wheel hub',(0,0,0),.0019,.00025,rim,bevel=.00012,vertices=64),wheel,(0,y-side*.00005,0))
            for radius in [.0100,.0125]:
                bpy.ops.mesh.primitive_torus_add(major_radius=radius,minor_radius=.000035,major_segments=96,minor_segments=6)
                o=bpy.context.object;o.name='Fine rubber sidewall moulding';o.data.materials.append(rubber)
                parent_local(o,wheel,(0,side*(c['wheel_width_m']/2-.00008),0));o.rotation_euler.x=math.pi/2
        for k in range(56):
            angle=k*math.tau/56
            tread=parent_local(box('Fine moulded tire tread',(0,0,0),(.00015,.0058,.000045),black,.000015),wheel,
                  (math.sin(angle)*(c['wheel_radius_m']-.00003),0,math.cos(angle)*(c['wheel_radius_m']-.00003)))
            tread.rotation_euler.y=angle
    for obj in bpy.data.objects:
        parent=obj.parent
        while parent and parent!=car and parent not in wheels:parent=parent.parent
        if parent==car or parent in wheels:
            for modifier in obj.modifiers:
                if modifier.type=='BEVEL':modifier.segments=max(modifier.segments,5)
    car['visual_asset']='Original refined mineral blue single-colour diecast hatchback'
    car['adaptation_record']=json.dumps({'design':'Original refined diecast hatchback, no external car mesh','body_shoulder_and_glazing_join_refined':True,'single_colour_factory_enamel':True,'solid_recessed_satin_alloy_spokes':True,
        'visual_length_m':.1098,'wheel_radius_m':.014,'wheelbase_m':.075,'wheel_track_m':.068,
        'roof_contact_height_m':.041,'roof_luggage':False,
        'rigid_contact_proxies_and_inertias_unchanged':True,'four_free_native_wheel_hinges':True})
    return car,wheels


def evaluated_prop_bounds(root):
    bpy.context.view_layer.update();graph=bpy.context.evaluated_depsgraph_get()
    points=[o.evaluated_get(graph).matrix_world@Vector(c) for o in root.children_recursive
            if o.type=='MESH' for c in o.evaluated_get(graph).bound_box]
    return (Vector(tuple(min(p[j] for p in points) for j in range(3))),
            Vector(tuple(max(p[j] for p in points) for j in range(3))))


def build_window_sheer(spec):
    """Actual folded thin fabric at the side window, participating in shadows."""
    mat=material('Ivory daylight voile curtain',(.74,.73,.68,1),.92)
    n,l=mat.node_tree.nodes,mat.node_tree.links;p=n.get('Principled BSDF')
    p.inputs['Sheen Weight'].default_value=.35
    translucent=n.new('ShaderNodeBsdfTranslucent');translucent.inputs['Color'].default_value=(.85,.84,.79,1)
    diffuse_mix=n.new('ShaderNodeMixShader');diffuse_mix.inputs[0].default_value=spec['translucent_weight']
    l.new(p.outputs[0],diffuse_mix.inputs[1]);l.new(translucent.outputs[0],diffuse_mix.inputs[2])
    transparent=n.new('ShaderNodeBsdfTransparent');transparent.inputs['Color'].default_value=(1,1,1,1)
    sheer=n.new('ShaderNodeMixShader');sheer.inputs[0].default_value=spec['transparent_weight']
    l.new(diffuse_mix.outputs[0],sheer.inputs[1]);l.new(transparent.outputs[0],sheer.inputs[2])
    l.new(sheer.outputs[0],n.get('Material Output').inputs['Surface'])
    surface_finish(mat,4000,.86,.97,.000025)
    for panel,(y0,y1) in enumerate(spec['panels_y_m']):
        steps=max(40,int((y1-y0)/.003));rows=24;verts=[];faces=[]
        for j in range(rows+1):
            z=spec['bottom_z_m']+(spec['top_z_m']-spec['bottom_z_m'])*j/rows
            for i in range(steps+1):
                y=y0+(y1-y0)*i/steps
                phase=(y-y0)*math.tau/spec['fold_pitch_m']
                x=-1.385+spec['fold_depth_m']*math.sin(phase)*(1.0-.12*j/rows)
                zz=z+.003*(1-j/rows)*math.sin(phase*.5)
                verts.append((x,y,zz))
        for j in range(rows):
            for i in range(steps):
                k=j*(steps+1)+i;faces.append((k,k+1,k+steps+2,k+steps+1))
        curtain=mesh_object('Soft folded side-window voile '+str(panel),verts,faces,mat)
        for poly in curtain.data.polygons:poly.use_smooth=True
        solid=curtain.modifiers.new('Thin sewn curtain cloth','SOLIDIFY');solid.thickness=spec['fabric_thickness_m']
        curtain['fold_pitch_m']=spec['fold_pitch_m'];curtain['outside_vehicle_motion']=True
        path_tube('Curtain stitched lower hem',verts[:steps+1],.001,mat)


def build_basket_drape(spec):
    """Static folded linen resting over the measured basket rim; no event driver."""
    mat=pbr_wood('Natural ivory woven throw over basket rim','fabric_pattern_07',(.97,.94,.86),(.75,.91),.32,'col_2')
    n,l=mat.node_tree.nodes,mat.node_tree.links;p=n.get('Principled BSDF')
    base=p.inputs['Base Color'].links[0].from_socket
    tint=n.new('ShaderNodeMixRGB');tint.inputs[0].default_value=.035
    tint.inputs[1].default_value=(.66,.60,.49,1)
    l.new(base,tint.inputs[2]);l.new(tint.outputs[0],p.inputs['Base Color'])
    p.inputs['Sheen Weight'].default_value=.32;p.inputs['Coat Weight'].default_value=0
    import numpy as np
    asset=scene_asset(Path(__file__).resolve().parents[1], 'assets/generated')/spec['mesh']
    data=np.load(asset);verts=data['vertices'];faces=data['faces']
    cloth=mesh_object('Static linen drape on basket - clear of motion',verts.tolist(),faces.tolist(),mat)
    recalc_normals(cloth);uv=cloth.data.uv_layers.new(name='Linen metres')
    for loop in cloth.data.loops:uv.data[loop.index].uv=data['uv'][loop.vertex_index]
    for poly in cloth.data.polygons:poly.use_smooth=True
    smooth=cloth.modifiers.new('Smooth settled cloth curvature','SUBSURF');smooth.levels=1;smooth.render_levels=1
    solid=cloth.modifiers.new('Fine woven cloth thickness','SOLIDIFY');solid.thickness=.00065
    cloth['construction']='Original Blender cloth settlement on actual basket collision mesh, with rear edge tucked at rim; final mesh frozen'
    cloth['clear_of_vehicle_corridor']=True
    nx,ny=36,60
    for indices in [[j*(nx+1) for j in range(ny+1)],[j*(nx+1)+nx for j in range(ny+1)],list(range(ny*(nx+1),(ny+1)*(nx+1)))]:
        path_tube('Fine sewn linen hem',[verts[k] for k in indices],.0004,mat)
    return cloth


def node_noise(n, scale, detail=2.0, roughness=.5, vector=None, links=None):
    noise = n.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = scale
    noise.inputs['Detail'].default_value = detail
    noise.inputs['Roughness'].default_value = roughness
    if vector is not None:
        links.new(vector, noise.inputs['Vector'])
    return noise


def map_range(n, lo, hi, from_lo=0., from_hi=1.):
    m = n.new('ShaderNodeMapRange')
    m.inputs['From Min'].default_value, m.inputs['From Max'].default_value = from_lo, from_hi
    m.inputs['To Min'].default_value, m.inputs['To Max'].default_value = lo, hi
    return m


def silicone_material(spec):
    """Translucent pigmented platinum silicone; all detail is attached to the rest-pose UVs.

    Light passes through the closed 6 mm solid by a diffuse translucent lobe on its faces. Volumetric
    subsurface scattering was tried and left a fixed speckle after OIDN denoising, so it is off.
    """
    mat = material('Translucent pigmented platinum silicone', spec['base_color_linear'], .37)
    n, l = mat.node_tree.nodes, mat.node_tree.links
    p = n.get('Principled BSDF')
    p.inputs['IOR'].default_value = spec['ior']
    p.inputs['Subsurface Weight'].default_value = 0.0
    p.inputs['Specular IOR Level'].default_value = .5
    p.inputs['Coat Weight'].default_value = 0
    translucent = n.new('ShaderNodeBsdfTranslucent')
    translucent.inputs['Color'].default_value = spec['translucent_color_linear']
    mix = n.new('ShaderNodeMixShader'); mix.inputs[0].default_value = spec['translucency']
    l.new(p.outputs[0], mix.inputs[1]); l.new(translucent.outputs[0], mix.inputs[2])
    l.new(mix.outputs[0], n.get('Material Output').inputs['Surface'])
    uv = n.new('ShaderNodeUVMap'); uv.uv_map = 'Silicone rest metres'
    # Gentle pigment density variation (centimetre scale) and handling smudges (millimetre scale).
    pigment = node_noise(n, 22, 3, .55, uv.outputs['UV'], l)
    tint = map_range(n, .94, 1.05, .3, .7)
    l.new(pigment.outputs['Fac'], tint.inputs['Value'])
    mul = n.new('ShaderNodeMixRGB'); mul.blend_type = 'MULTIPLY'; mul.inputs[0].default_value = 1
    mul.inputs[1].default_value = spec['base_color_linear']
    l.new(tint.outputs[0], mul.inputs[2]); l.new(mul.outputs[0], p.inputs['Base Color'])
    satin = node_noise(n, 140, 4, .6, uv.outputs['UV'], l)
    rough = map_range(n, *spec['roughness_range'], .3, .7)
    l.new(satin.outputs['Fac'], rough.inputs['Value'])
    smudge = node_noise(n, 55, 5, .65, uv.outputs['UV'], l)
    smudge_mask = map_range(n, 0., spec['smudge_roughness_add'], .58, .72)
    smudge_mask.clamp = True
    l.new(smudge.outputs['Fac'], smudge_mask.inputs['Value'])
    add = n.new('ShaderNodeMath'); add.operation = 'ADD'; add.use_clamp = True
    l.new(rough.outputs[0], add.inputs[0]); l.new(smudge_mask.outputs[0], add.inputs[1])
    l.new(add.outputs[0], p.inputs['Roughness'])
    # Soft millimetre-scale moulding waviness; finer relief would be sub-pixel and only add noise.
    grain = node_noise(n, 1 / spec['orange_peel_scale_m'], 2, .5, uv.outputs['UV'], l)
    bump = n.new('ShaderNodeBump'); bump.inputs['Distance'].default_value = spec['orange_peel_bump_m']
    bump.inputs['Strength'].default_value = .35
    l.new(grain.outputs['Fac'], bump.inputs['Height']); l.new(bump.outputs[0], p.inputs['Normal'])
    l.new(bump.outputs[0], translucent.inputs['Normal'])
    edge = mat.copy(); edge.name = 'Cut edge of six millimetre silicone'
    edge.node_tree.nodes.get('Principled BSDF').inputs['Specular IOR Level'].default_value = .42
    mat['finish'] = 'analytic CC0-free procedural finish, rest-pose UV, no bitmap'
    return mat, edge


def brushed_aluminium():
    m = material('Brushed aluminium clamp plate', (.80, .80, .78, 1), .30, 1.0)
    n, l = m.node_tree.nodes, m.node_tree.links
    p = n.get('Principled BSDF')
    p.inputs['Anisotropic'].default_value = .55
    tc = n.new('ShaderNodeTexCoord')
    stretch = n.new('ShaderNodeMapping'); stretch.inputs['Scale'].default_value = (40, 3000, 3000)
    l.new(tc.outputs['Object'], stretch.inputs['Vector'])
    lines = node_noise(n, 1, 4, .7, stretch.outputs[0], l)
    rr = map_range(n, .24, .36, .3, .7)
    l.new(lines.outputs['Fac'], rr.inputs['Value']); l.new(rr.outputs[0], p.inputs['Roughness'])
    return m


def zinc_screw_steel():
    m = material('Zinc plated steel screw', (.66, .67, .66, 1), .28, 1.0)
    surface_finish(m, 9000, .24, .36, 0)
    return m


def pan_head_screw(name, x, y, top, steel, recess):
    s = cylinder(name + ' pan head', (x, y, top + .00065), .0026, .0013, steel, rotation=(0, 0, 0),
                 bevel=.0007, vertices=48)
    for angle in [0, math.pi / 2]:
        b = box(name + ' cross recess', (x, y, top + .00122), (.0022, .00055, .0002), recess, .00006)
        b.rotation_euler.z = angle + .4
    return s


def rebated_deck(name, a, b, width, top, rebate_floor, rebate_half_width, rebate_end, wood, endmat, road_print, rng):
    """12 mm printed deck; a routed rebate takes the fixed silicone band at the bridge end."""
    deck = wood_box(name, ((a + b) / 2, 0, (top + .053) / 2), (b - a - .00018, width, top - .053), wood, rng, endmat, 0)
    if rebate_end is not None:
        # The rebate is the 20 mm band next to the free span; the cutter overshoots past the end face.
        lo, hi = (rebate_end - .020, rebate_end + .010) if rebate_end >= b - 1e-9 else (rebate_end - .010, rebate_end + .020)
        bpy.ops.mesh.primitive_cube_add(size=1, location=((lo + hi) / 2, 0, (rebate_floor + top + .01) / 2))
        cutter = bpy.context.object
        cutter.dimensions = (hi - lo, 2 * rebate_half_width, top + .01 - rebate_floor)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        mod = deck.modifiers.new('Routed 6.2 mm silicone rebate', 'BOOLEAN')
        mod.operation, mod.object, mod.solver = 'DIFFERENCE', cutter, 'EXACT'
        bpy.context.view_layer.objects.active = deck
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cutter, do_unlink=True)
        uv_metres(deck, 1., (rng.random(), rng.random()), 'X')
    deck.data.materials.append(road_print)
    deck_top_local = max(v.co.z for v in deck.data.vertices)  # mesh coordinates are object-local
    for poly in deck.data.polygons:
        if abs(poly.normal.x) > .9:
            poly.material_index = 1
        elif poly.normal.z > .9:
            poly.material_index = 2 if poly.center.z > deck_top_local - 1e-6 else 0
        else:
            poly.material_index = 0
    bev = deck.modifiers.new('Manufactured edge radius in metres', 'BEVEL')
    bev.width, bev.segments, bev.limit_method = .00065, 3, 'ANGLE'
    deck.modifiers.new('Weighted corner normals', 'WEIGHTED_NORMAL')
    return deck


def build_roads(cfg, wood, endmat, rng, paint, alu, steel, recess):
    b, r = cfg['physics']['bridge'], cfg['physics']['road']
    mount = cfg['appearance']['bridge_mount']
    half, top, width = b['free_span_m'] / 2, r['height_m'], r['width_m']
    present = b['present']
    road_print = printed_road_material(wood)
    floor_z = top - mount['rebate_depth_m']
    for side, x1, x2 in [('left', r['left_extent_m'], -half), ('right', half, r['right_extent_m'])]:
        cuts = [x1] + [q for q in [-.36, .46, .78] if x1 + .06 < q < x2 - .06] + [x2]
        for j, (aa, bb) in enumerate(zip(cuts, cuts[1:])):
            wood_box(f'{side} laminated road support {j}', ((aa + bb) / 2, 0, .02645),
                     (bb - aa - .00018, width, .0529), wood, rng, endmat, .00055)
            bridge_end = None
            if present and side == 'left' and bb == x2:
                bridge_end = x2
            if present and side == 'right' and aa == x1:
                bridge_end = x1
            rebated_deck(f'{side} twelve millimetre road deck {j}', aa, bb, width, top, floor_z,
                         mount['rebate_half_width_m'], bridge_end, wood, endmat, road_print, rng)
            for yy in [-width / 2 - .000015, width / 2 + .000015]:
                for xx in [aa + .030, bb - .030]:
                    cylinder('Flush wooden assembly dowel', (xx, yy, .031), .0022, .00006,
                             endmat, bevel=.00006, vertices=40)
        if present:
            sign_x = -1 if side == 'left' else 1
            x0, x1p = mount['plate_x_m']
            y0, y1 = mount['plate_y_m']
            t = mount['plate_thickness_m']
            for sy in [-1, 1]:
                plate = box(f'{side} aluminium clamp plate {sy}',
                            (sign_x * (x0 + x1p) / 2, sy * (y0 + y1) / 2, top + t / 2 + .00005),
                            (x1p - x0, y1 - y0, t), alu, .0009)
                plate['outside_vehicle_corridor_abs_y_m'] = y0
                for yy in mount['screw_y_m']:
                    pan_head_screw(f'{side} clamp screw', sign_x * (x0 + x1p) / 2, sy * yy,
                                   top + t + .00005, steel, recess)
        x = x1 + .035
        while x < x2 - .025:
            box('Worn ivory printed centre dash', (x, 0, top + .000025), (.021, .002, .00004), paint, .000025)
            x += .046


def import_shared_gltf(name, filename, rotation_z=0.):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(shared_asset(name) / filename))
    imported = set(bpy.data.objects) - before
    root = empty('CC0 ' + name)
    for obj in imported:
        if obj.parent not in imported:
            m = obj.matrix_world.copy(); obj.parent = root; obj.matrix_world = m
    root.rotation_euler.z = rotation_z
    root['asset'] = name; root['license'] = 'CC0-1.0'; root['scale'] = 'native metric size (uniform scale 1)'
    bpy.context.view_layer.update()
    return root


def tint_drawers(root, tint, roughness):
    """The scan's white bins become linen-grey: their own copy of the material, base colour multiplied."""
    shared = {}
    for obj in root.children_recursive:
        if obj.type != 'MESH' or '_drawer_' not in obj.name:
            continue
        for slot in obj.material_slots:
            src = slot.material
            if src.name not in shared:
                m = src.copy(); m.name = src.name + ' - linen grey painted bins'
                n, l = m.node_tree.nodes, m.node_tree.links
                p = next(node for node in n if node.type == 'BSDF_PRINCIPLED')
                base = p.inputs['Base Color'].links[0].from_socket
                mul = n.new('ShaderNodeMixRGB'); mul.blend_type = 'MULTIPLY'; mul.inputs[0].default_value = 1
                mul.inputs[2].default_value = (*tint[:3], 1)
                l.new(base, mul.inputs[1]); l.new(mul.outputs[0], p.inputs['Base Color'])
                if p.inputs['Roughness'].is_linked:
                    l.remove(p.inputs['Roughness'].links[0])
                p.inputs['Roughness'].default_value = roughness
                shared[src.name] = m
            slot.material = shared[src.name]
    root['bin_tint_linear'] = list(tint)


def ground_at(root, x=None, y=None, z=0., back_y=None):
    lo, hi = evaluated_prop_bounds(root)
    shift = Vector((0, 0, z - lo.z))
    if x is not None:
        shift.x = x - (lo.x + hi.x) / 2
    if y is not None:
        shift.y = y - (lo.y + hi.y) / 2
    if back_y is not None:
        shift.y = back_y - hi.y
    root.location += shift
    bpy.context.view_layer.update()
    lo, hi = evaluated_prop_bounds(root)
    root['world_bounds_m'] = [list(lo), list(hi)]
    return lo, hi


def build_room(cfg, wood, endmat, rng):
    app = cfg['appearance']; room = app['room']
    wall = pbr_wood('Fine painted mineral plaster - one metre tile', room['wall_texture'], (.86, .88, .83), (.82, .95), .10)
    wall_p = wall.node_tree.nodes.get('Principled BSDF'); wall_p.inputs['Coat Weight'].default_value = 0
    wall_base = wall_p.inputs['Base Color'].links[0].from_socket
    paint_mix = wall.node_tree.nodes.new('ShaderNodeMixRGB')
    paint_mix.inputs[0].default_value = room['plaster_color_texture_mix']
    paint_mix.inputs[1].default_value = (.55, .555, .52, 1)
    wall.node_tree.links.new(wall_base, paint_mix.inputs[2]); wall.node_tree.links.new(paint_mix.outputs[0], wall_p.inputs['Base Color'])
    trim = material('Warm white satin skirting enamel', (.66, .665, .63, 1), .40, coat=.10)
    surface_finish(trim, 2400, .36, .48, .000018)
    back = box('Continuous back wall', (0, 1.15, 1.25), (6, .08, 2.5), wall, .001)
    uv_metres(back, room['wall_tile_m'], (.21, .13), 'X')
    box('Skirting eight centimetre base', (0, 1.094, .040), (6, .022, .080), trim, .00065)
    box('Skirting eased top cap', (0, 1.091, .081), (6, .018, .005), trim, .0014)
    box('Painted quarter-round floor beading', (0, 1.075, .006), (6, .014, .012), trim, .0045)
    box('Room ceiling', (0, -.5, 2.52), (6, 4, .08), trim, 0)
    box('Front wall behind camera', (0, -2.35, 1.25), (6, .08, 2.5), wall, 0)
    box('Right room wall', (2.8, -.60, 1.25), (.08, 3.5, 2.5), wall, 0)
    # Left wall (x = -1.50, y from -2.35 to 1.15) with one open window; the sun reaches the floor only
    # through this opening.
    (y0, y1), (z0, z1) = room['window']['y_m'], room['window']['z_m']
    yc, zc = (y0 + y1) / 2, (z0 + z1) / 2
    for pos, size in [((-1.50, -.60, z0 / 2), (.08, 3.5, z0)), ((-1.50, -.60, (z1 + 2.5) / 2), (.08, 3.5, 2.5 - z1)),
                      ((-1.50, (-2.35 + y0) / 2, zc), (.08, y0 + 2.35, z1 - z0)),
                      ((-1.50, (y1 + 1.15) / 2, zc), (.08, 1.15 - y1, z1 - z0))]:
        box('Window wall with open aperture', pos, size, wall, 0)
    for yy in [y0, y1]:
        box('White window jamb', (-1.47, yy, zc), (.11, .045, z1 - z0 + .05), trim, .003)
    for zz in [z0, z1]:
        box('White window rail', (-1.47, yc, zz), (.11, y1 - y0 + .04, .045), trim, .003)
    for yy in room['window'].get('mullion_y_m', []):
        box('Window mullion', (-1.47, yy, zc), (.10, .028, z1 - z0 - .04), trim, .002)
    box('Deep painted window sill', (-1.40, yc, z0 - .02), (.26, y1 - y0 + .12, .038), trim, .003)
    floor = pbr_wood('Satin oak floor 1.7 metre tile', room['floor_texture'], (.94, .96, 1),
                     room['floor_roughness_range'], room['floor_normal_strength'])
    fp = floor.node_tree.nodes.get('Principled BSDF')
    fp.inputs['Coat Weight'].default_value = room['floor_coat_weight']
    fp.inputs['Coat Roughness'].default_value = room['floor_coat_roughness']
    build_window_sheer(app['window_sheer'])
    plane = box('Continuous solid oak floor', (0, 0, -.008), (7, 6, .016), floor, 0)
    uv_metres(plane, room['floor_tile_m'], (.12, .18), 'Y')
    # Sewn floor cushion, clear of the plant and basket.
    cotton = pbr_wood('Photographic woven cotton check', 'fabric_pattern_07', (.92, .97, 1), (.67, .88), .38, 'col_2')
    cotton.node_tree.nodes.get('Principled BSDF').inputs['Sheen Weight'].default_value = .18
    cushion = empty('Soft floor cushion clear of the vehicle corridor')
    cushion.location = room['cushion_position_m']; cushion.rotation_euler.z = room['cushion_rotation_z_rad']
    verts = []; rings = 12; steps = 120
    for j in range(rings + 1):
        phi = math.pi * j / rings; radial = math.sin(phi) ** .48
        for k in range(steps):
            theta = math.tau * k / steps; ct, st = math.cos(theta), math.sin(theta)
            xx = .205 * math.copysign(abs(ct) ** .45, ct) * radial
            yy = .145 * math.copysign(abs(st) ** .45, st) * radial
            z = .022 + .021 * math.cos(phi) + .0018 * math.sin(theta + 0.6) * math.sin(phi) ** 2
            if j > rings / 2: z = .001 + .024 * (1 + math.cos(phi)) ** 1.7
            fold = (.0011 * math.sin(theta * 17 + 1.2) + .0007 * math.sin(theta * 29 - .7)) * math.sin(phi) ** 4
            verts.append((xx * (1 + fold * 8), yy * (1 + fold * 8), max(.0003, z + fold)))
    faces = [(j * steps + k, j * steps + (k + 1) % steps, (j + 1) * steps + (k + 1) % steps, (j + 1) * steps + k)
             for j in range(rings) for k in range(steps)]
    puff =parent_local(mesh_object('Cotton cushion with tension folds', verts, faces, cotton), cushion)
    recalc_normals(puff); uv_metres(puff, .4, (.12, .21), 'X')
    for f in puff.data.polygons: f.use_smooth = True
    piping = material('Cotton bound piping', (.16, .23, .25, 1), .82)
    surface_finish(piping, 2500, .73, .88, .00004)
    seam = []
    for k in range(steps):
        a = math.tau * k / steps; ct, st = math.cos(a), math.sin(a)
        seam.append((.205 * math.copysign(abs(ct) ** .45, ct), .145 * math.copysign(abs(st) ** .45, st), .022))
    path_tube('Sewn cushion perimeter piping', seam, .00115, piping, cushion, True)
    # Wicker basket with its settled linen throw, moved together by the same offset.
    for asset_id, spec in app['external_models'].items():
        import_metric_prop(asset_id, spec['position_m'], spec['longest_horizontal_m'], spec['rotation_z_rad'])
    drape = build_basket_drape(app['basket_drape'])
    drape.location = room['basket_drape_offset_m']
    for obj in bpy.data.objects:
        if obj.name.startswith('Fine sewn linen hem'):
            obj.location = room['basket_drape_offset_m']
    # Scanned CC0 furniture and props at native size.
    placed = {}
    for name, spec in app['shared_models'].items():
        root = import_shared_gltf(name, spec['file'], spec['rotation_z_rad'])
        if 'bin_tint_linear' in spec:
            tint_drawers(root, spec['bin_tint_linear'], spec.get('bin_roughness', .7))
        if 'back_y_m' in spec:
            placed[name] = ground_at(root, x=spec['center_x_m'], back_y=spec['back_y_m'])
        else:
            x, y, z = spec['position_m']
            placed[name] = ground_at(root, x=x, y=y, z=z)
    return placed


def build_lighting(cfg):
    lighting = cfg['appearance']['lighting']; sc = bpy.context.scene
    world = bpy.data.worlds.new('Daylight sky seen through the window'); sc.world, world.use_nodes = world, True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    env = nodes.new('ShaderNodeTexEnvironment')
    h = lighting['hdri']
    env.image = bpy.data.images.load(str(ASSETS / h['asset'] / (h['asset'] + '_2k.hdr')), check_existing=True)
    mapping, coord = nodes.new('ShaderNodeMapping'), nodes.new('ShaderNodeTexCoord')
    mapping.inputs['Rotation'].default_value.z = math.radians(h['rotation_z_degrees'])
    links.new(coord.outputs['Generated'], mapping.inputs['Vector']); links.new(mapping.outputs[0], env.inputs['Vector'])
    # The HDRI's own sun is clamped away; the sun lamp below is the single direct sun.
    clamp = nodes.new('ShaderNodeVectorMath'); clamp.operation = 'MINIMUM'
    clamp.inputs[1].default_value = (h['clamp'],) * 3
    links.new(env.outputs[0], clamp.inputs[0]); links.new(clamp.outputs[0], nodes['Background'].inputs[0])
    nodes['Background'].inputs[1].default_value = h['strength']
    s = lighting['sun']
    sun = bpy.data.lights.new('Afternoon sun entering real side window', 'SUN')
    sun.energy, sun.angle, sun.color = s['strength'], math.radians(s['angle_degrees']), s['color']
    obj = bpy.data.objects.new(sun.name, sun); bpy.context.collection.objects.link(obj)
    obj.rotation_euler = Vector(s['direction']).to_track_quat('-Z', 'Y').to_euler()
    # The portal covers the window opening exactly (local X = world Z, local Y = world Y).
    (y0, y1), (z0, z1) = cfg['appearance']['room']['window']['y_m'], cfg['appearance']['room']['window']['z_m']
    portal = bpy.data.lights.new('Window opening sampling portal (emits nothing)', 'AREA')
    portal.shape = 'RECTANGLE'; portal.size, portal.size_y = z1 - z0, y1 - y0
    portal.cycles.is_portal = True
    po = bpy.data.objects.new(portal.name, portal); bpy.context.collection.objects.link(po)
    po.location = (-1.455, (y0 + y1) / 2, (z0 + z1) / 2); po.rotation_euler = (0, -math.pi / 2, 0)


def keyframe_rigid_cache(data, car, wheels):
    """Cache poses become linear keyframes (frame f = cache index f-1) so motion blur sees real motion."""
    for i, obj in enumerate([car, *wheels]):
        obj.rotation_mode = 'QUATERNION'
        prev = None
        for index in range(data['body_pose'].shape[0]):
            pose = data['body_pose'][index, i]
            q = [float(v) for v in pose[3:]]
            if prev is not None and sum(a * b for a, b in zip(prev, q)) < 0:
                q = [-v for v in q]
            prev = q
            obj.location = [float(v) for v in pose[:3]]; obj.rotation_quaternion = q
            obj.keyframe_insert('location', frame=index + 1)
            obj.keyframe_insert('rotation_quaternion', frame=index + 1)
        for fc in obj.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'


def build_scene(cfg, data):
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for m in list(bpy.data.materials):
        bpy.data.materials.remove(m)
    rng = random.Random(cfg['appearance']['seed'])
    wood = pbr_wood('Natural oil finished maple', 'white_maple_veneer', (.81, .72, .56), (.35, .58), .40)
    endmat = end_grain()
    red = material('Deep red baked diecast enamel', (.25, .013, .007, 1), .25, .02, .48)
    rubber = material('Matte black tire rubber', (.008, .010, .011, 1), .72)
    alloy = material('Cream enamel wheel rim', (.57, .55, .46, 1), .33, .25, .10)
    black = material('Graphite moulded plastic', (.022, .028, .030, 1), .55)
    glass = material('Lightly smoked clear polycarbonate glazing', (.28, .37, .35, 1), .12, coat=.18)
    p = glass.node_tree.nodes.get('Principled BSDF')
    p.inputs['Transmission Weight'].default_value = .83; p.inputs['IOR'].default_value = 1.49
    steel = material('Satin zinc hardware', (.36, .38, .37, 1), .31, .82)
    paint = material('Soft ivory printed markings', (.72, .70, .60, 1), .49)
    alu, screw_steel = brushed_aluminium(), zinc_screw_steel()
    recess = material('Shadowed screw recess', (.02, .02, .02, 1), .6)
    build_room(cfg, wood, endmat, rng)
    build_roads(cfg, wood, endmat, rng, paint, alu, screw_steel, recess)
    bridge = None
    b = cfg['physics']['bridge']; spec = cfg['appearance']['silicone']
    if b['present']:
        sil, cut_edge = silicone_material(spec)
        verts, faces, rest = data['vertices'][0], data['faces'], data['rest_vertices']
        # All faces, including the fixed 20 mm end bands that lie in the road rebates.
        bridge = mesh_object('Solved six millimetre silicone bridge', verts.tolist(), faces.tolist(), sil)
        uv = bridge.data.uv_layers.new(name='Silicone rest metres')
        for loop in bridge.data.loops:
            co = rest[loop.vertex_index]
            uv.data[loop.index].uv = (co[0] + b['length_m'] / 2, co[1] + b['width_m'] / 2)
        bridge.data.materials.append(cut_edge)
        bridge['surface_coordinates'] = 'Lagrangian rest-pose UV, one unit per metre'
        bridge['surface_relief_is_shading_only'] = True
        subd = bridge.modifiers.new('Smooth limit surface of the solved shell', 'SUBSURF')
        subd.levels, subd.render_levels = 1, spec['subdivision_render_levels']
        subd.boundary_smooth = 'PRESERVE_CORNERS'
        sol = bridge.modifiers.new('Actual solved shell thickness', 'SOLIDIFY')
        sol.thickness, sol.offset, sol.use_even_offset = b['thickness_m'], 0, True
        sol.material_offset_rim = 1
        edge = bridge.modifiers.new('Small moulded section edge radius', 'BEVEL')
        edge.width, edge.segments, edge.limit_method = .0004, 2, 'ANGLE'
        for poly in bridge.data.polygons:
            poly.use_smooth = True
        if hasattr(bridge, 'cycles'):
            bridge.cycles.use_motion_blur = False  # deformation per frame is < 2 mm; no deform blur
    car, wheels = None, []
    # DELETE car (car present false; the published configurations have no such key): no car body or wheels.
    if cfg['physics']['car'].get('present', True):
        car, wheels = build_car(cfg, red, rubber, alloy, black, glass, paint, steel)
        keyframe_rigid_cache(data, car, wheels)
    build_lighting(cfg)
    app, sc = cfg['appearance'], bpy.context.scene
    bpy.ops.object.camera_add(location=app['camera'])
    camera = bpy.context.object
    camera.name = 'Fixed lower side front camera'
    camera.rotation_euler = (Vector(app['target']) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.lens, camera.data.clip_start, camera.data.clip_end = app['lens_mm'], .005, 30
    camera.data.dof.use_dof, sc.camera = True, camera
    camera.data.dof.focus_distance = app['camera_optics']['focus_distance_m']
    camera.data.dof.aperture_fstop = app['camera_optics']['fstop']
    camera.data.dof.aperture_blades = 7
    sc.unit_settings.system, sc.unit_settings.scale_length = 'METRIC', 1
    r = cfg['render']
    sc.render.engine, sc.cycles.samples = 'CYCLES', r['samples']
    sc.cycles.use_adaptive_sampling, sc.cycles.use_denoising = False, True
    sc.cycles.denoiser = 'OPENIMAGEDENOISE'
    sc.cycles.denoising_input_passes, sc.cycles.denoising_prefilter = 'RGB_ALBEDO_NORMAL', 'ACCURATE'
    # A fixed seed keeps the denoised noise of static surfaces identical from frame to frame.
    sc.cycles.seed = 0; sc.cycles.use_animated_seed = False
    sc.cycles.max_bounces, sc.cycles.diffuse_bounces, sc.cycles.glossy_bounces = 10, 5, 5
    sc.cycles.transmission_bounces = 8
    sc.cycles.transparent_max_bounces = 8
    sc.cycles.sample_clamp_indirect = 10.0
    sc.render.resolution_x, sc.render.resolution_y = r['width'], r['height']
    sc.render.resolution_percentage = 100
    sc.render.fps, sc.frame_start, sc.frame_end = r['fps'], 1, r['frames']
    sc.render.image_settings.file_format, sc.render.image_settings.color_mode, sc.render.image_settings.color_depth = 'PNG', 'RGB', '8'
    grade = app['color_grade']
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look, sc.view_settings.exposure = grade['look'], grade['exposure_ev']
    sc.render.film_transparent = False
    sc.render.use_motion_blur = bool(r.get('motion_blur'))
    sc.render.motion_blur_shutter = r.get('motion_blur_shutter_frames', .5)
    sc.render.motion_blur_position = 'CENTER'
    # Persistent data must stay off with motion blur (Blender 4.3 drops objects that come to rest).
    sc.render.use_persistent_data = bool(r.get('persistent_data', False)) and not sc.render.use_motion_blur
    return bridge, car, wheels


def apply_frame(data, frame, bridge, car, wheels):
    if bridge:
        bridge.data.vertices.foreach_set('co', data['vertices'][frame].astype('float32').ravel())
        bridge.data.update()
    for i, o in enumerate([car, *wheels] if car else []):
        pose = data['body_pose'][frame, i]
        o.location, o.rotation_mode, o.rotation_quaternion = pose[:3], 'QUATERNION', pose[3:]
    bpy.context.scene.frame_set(frame + 1)
    bpy.context.view_layer.update()
