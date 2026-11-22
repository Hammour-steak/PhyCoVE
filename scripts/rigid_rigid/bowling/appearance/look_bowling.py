"""Operating bowling venue: scanned pins and ball, masking unit, lane, gutters and visible lamp fixtures.

architecture(), asset_pin_mesh(), pin_visual_mesh(), ball_asset_finish(), idle_lane_racks() and lighting()
build the look in layers: a graybox hall, a photographic bowling club, a documentary look, the venue,
and the final photographic layer below. Helpers suffixed with a layer name (architecture_venue,
asset_pin_mesh_photographic, ...) are the lower layers the final functions build on.

Final layer (appearance only; contact geometry, cached dynamics and camera do not depend on it):
- No text or marks anywhere: no lane numerals; the manufacturer logo and approval stamp printed on the
  source pin coating are painted out of its base-colour texture with unprinted coating wear.
- Masking unit: woven acoustic fabric panels (Poly Haven poly_wool_herringbone, CC0) at the real 27 cm
  weave repeat, with an aluminium nosing on the bottom edge.
- Gutters, capping, kickbacks and strike plates: scanned scuff and scratch breakup in roughness and normal
  (Poly Haven blue_metal_plate maps, roughness and normal only).
- Lane: a full, smooth top coat, so pins, kickbacks and lamps mirror in the lane.
- Lighting: every lamp is a visible fixture (housing plus lit lens); no free-floating fill lights and no
  world fill. Lane-end, masking-wash and pit lamps hang from the masking unit, ceiling and pinsetter frame.
"""
from __future__ import annotations

import collections
import math
import random
import sys as _scene_sys
from pathlib import Path as _ScenePath, Path

import bpy
from mathutils import Vector
from scene_config import pin_radius, pin_mass_properties, fixed_geometry
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))


def material(name,color,roughness=.35,metallic=0.):
    m=bpy.data.materials.new(name);m.use_nodes=True
    bs=m.node_tree.nodes.get("Principled BSDF");bs.inputs["Base Color"].default_value=color
    bs.inputs["Roughness"].default_value=roughness;bs.inputs["Metallic"].default_value=metallic
    return m


def linkmesh(name,verts,faces,mat):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o)
    if mat:o.data.materials.append(mat)
    return o


def look_at(o,xyz):o.rotation_euler=(Vector(xyz)-o.location).to_track_quat('-Z','Y').to_euler()


def noise(nodes,links,coord,scale,detail=2):
    n=nodes.new("ShaderNodeTexNoise");n.inputs["Scale"].default_value=scale;n.inputs["Detail"].default_value=detail
    links.new(coord,n.inputs["Vector"]);return n


def finish_material(name,base,roughness,stripe=None):
    """Microscopic finish and sparse handling marks attached to object coordinates."""
    m=material(name,base,roughness);n=m.node_tree.nodes;l=m.node_tree.links;bs=n.get("Principled BSDF")
    tc=n.new("ShaderNodeTexCoord");fine=noise(n,l,tc.outputs["Generated"],260,2)
    ramp=n.new("ShaderNodeMapRange");ramp.inputs["From Min"].default_value=.25;ramp.inputs["From Max"].default_value=.75
    ramp.inputs["To Min"].default_value=roughness-.045;ramp.inputs["To Max"].default_value=roughness+.08
    l.new(fine.outputs["Fac"],ramp.inputs["Value"]);l.new(ramp.outputs["Result"],bs.inputs["Roughness"])
    bs.inputs["Coat Weight"].default_value=.22;bs.inputs["Coat Roughness"].default_value=.22
    if "pin" in name.lower() or "neck" in name.lower():
        mapping=n.new("ShaderNodeVectorMath");mapping.operation="MULTIPLY";mapping.inputs[1].default_value=(28.,28.,2.4)
        l.new(tc.outputs["Generated"],mapping.inputs[0])
        wear=noise(n,l,mapping.outputs["Vector"],7.,2)
        mask=n.new("ShaderNodeValToRGB");mask.color_ramp.elements[0].position=.73;mask.color_ramp.elements[0].color=(0,0,0,1)
        mask.color_ramp.elements[1].position=.79;mask.color_ramp.elements[1].color=(.33,.33,.33,1)
        l.new(wear.outputs["Fac"],mask.inputs["Fac"])
        mix=n.new("ShaderNodeMixRGB");mix.inputs[1].default_value=base;mix.inputs[2].default_value=tuple(v*.60 if i<3 else v for i,v in enumerate(base))
        l.new(mask.outputs["Color"],mix.inputs[0]);l.new(mix.outputs["Color"],bs.inputs["Base Color"])
    return m


def ball_material(cfg):
    a=cfg["appearance"]["ball"];m=finish_material("Deep navy marbled reactive resin",a["color_a_linear"],a["roughness"])
    n=m.node_tree.nodes;l=m.node_tree.links;bs=n.get("Principled BSDF");tc=n.new("ShaderNodeTexCoord")
    tex=noise(n,l,tc.outputs["Generated"],4.6,5);tex.inputs["Roughness"].default_value=.67
    ramp=n.new("ShaderNodeValToRGB");ramp.color_ramp.elements[0].position=.23;ramp.color_ramp.elements[0].color=a["color_a_linear"]
    ramp.color_ramp.elements[1].position=.78;ramp.color_ramp.elements[1].color=a["color_b_linear"]
    l.new(tex.outputs["Fac"],ramp.inputs["Fac"]);l.new(ramp.outputs["Color"],bs.inputs["Base Color"])
    bs.inputs["Coat Weight"].default_value=a["coat_weight"];bs.inputs["Coat Roughness"].default_value=.16
    return m


def build_ball(cfg):
    r=cfg["physics"]["ball"]["radius_m"]
    bpy.ops.mesh.primitive_uv_sphere_add(segments=96,ring_count=64,radius=r)
    ball=bpy.context.object;ball.name="B01";ball.data.materials.append(ball_material(cfg));ball.rotation_mode="QUATERNION"
    # Three real bores: two 20 mm finger holes and one 25 mm thumb hole.
    for i,(direction,radius) in enumerate([((-.17,-.66,.73),.010),((.17,-.66,.73),.010),((-.06,-.96,.27),.0125)]):
        axis=Vector(direction).normalized()
        bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=radius,depth=.10,location=axis*.105)
        cutter=bpy.context.object;cutter.rotation_euler=axis.to_track_quat('Z','Y').to_euler()
        mod=ball.modifiers.new(f"Real finger bore {i+1}","BOOLEAN");mod.operation="DIFFERENCE";mod.solver="EXACT";mod.object=cutter
        bpy.context.view_layer.objects.active=ball;bpy.ops.object.modifier_apply(modifier=mod.name);bpy.data.objects.remove(cutter,do_unlink=True)
    mod=ball.modifiers.new("Softened bore rims","BEVEL");mod.width=.00055;mod.segments=3;mod.limit_method="ANGLE"
    bpy.context.view_layer.objects.active=ball;bpy.ops.object.modifier_apply(modifier=mod.name)
    for poly in ball.data.polygons:poly.use_smooth=True
    # Restrained shallow surface scuffs, without displacement of silhouette.
    ball["diameter_m"]=2*r;ball["finger_hole_diameters_m"]=[.020,.020,.025]
    ball["collision_proxy"]="B01 spherical envelope, finger cavities omitted";ball["visual_geometry"]="authored true boolean bores"
    return ball


def disk(name,x,y,z,r,mat):
    return linkmesh(name,[(x+r*math.cos(i*2*math.pi/32),y+r*math.sin(i*2*math.pi/32),z) for i in range(32)],[tuple(range(32))],mat)


def lane_markings(cfg,offset,mat):
    # Seven regulation-style aiming arrows farther toward the approach.
    for j in range(-3,4):
        x=-4.4+abs(j)*.13;y=offset+j*.122
        linkmesh("Flush inlaid aiming arrow",[(x+.085,y,.00015),(x-.025,y-.016,.00015),(x-.012,y,.00015),(x-.025,y+.016,.00015)],[(0,1,2,3)],mat)
        disk("Approach locator dot",-7.0,offset+j*.122,.00015,.006,mat)
    for x,y in [(0,0),(.2598076,.15),(.2598076,-.15)]:disk("Flush pin position spot",x,y+offset,.00015,.012,mat)


def text(name,body,location,size,mat,rotation=(math.pi/2,0,-math.pi/2)):
    curve=bpy.data.curves.new(name,"FONT");curve.body=body;curve.size=size;curve.align_x='CENTER';curve.extrude=.0005
    o=bpy.data.objects.new(name,curve);bpy.context.collection.objects.link(o);o.location=location;o.rotation_euler=rotation;o.data.materials.append(mat)
    return o


def asset_pin_mesh_scanned_pin(cfg,root):
    path=Path(root)/'retired_pin/retired_pin.blend'
    with bpy.data.libraries.load(str(path),link=False) as (source,target):target.objects=['Bowling Pin']
    source=target.objects[0];bpy.context.collection.objects.link(source);source.animation_data_clear();bpy.context.view_layer.update()
    deps=bpy.context.evaluated_depsgraph_get();mesh=bpy.data.meshes.new_from_object(source.evaluated_get(deps),preserve_all_data_layers=True,depsgraph=deps)
    points=[source.matrix_world@v.co for v in mesh.vertices];low=Vector(tuple(min(v[k] for v in points) for k in range(3)));high=Vector(tuple(max(v[k] for v in points) for k in range(3)))
    scale=.38/(high.z-low.z);cx=(low.x+high.x)/2;cy=(low.y+high.y)/2
    points=[Vector(((v.x-cx)*scale,(v.y-cy)*scale,(v.z-low.z)*scale)) for v in points]
    rings=collections.defaultdict(list)
    for p in points:rings[round(p.z,6)].append(math.hypot(p.x,p.y))
    ring_r={z:max(v) for z,v in rings.items()};com=pin_mass_properties()['com_height_m'];profile=cfg['physics']['pins']['profile_z_radius_m']
    for v,p in zip(mesh.vertices,points):
        rr=ring_r[round(p.z,6)];target_r=pin_radius(min(.38,max(0,p.z)),profile);factor=target_r/rr if rr>1e-9 else 1
        v.co=(p.x*factor,p.y*factor,p.z-com)
    m=material('David Geuens asset coating / restrained wear and two red bands',(.77,.76,.73,1),.245)
    n=m.node_tree.nodes;l=m.node_tree.links;bs=n.get('Principled BSDF');uv=n.new('ShaderNodeTexCoord')
    maps={}
    for node in source.data.materials[0].node_tree.nodes:
        if node.type=='TEX_IMAGE' and node.image:
            key='normal' if 'Normal' in node.image.name else ('rough' if 'Roughness' in node.image.name else 'color')
            tex=n.new('ShaderNodeTexImage');tex.image=node.image;l.new(uv.outputs['UV'],tex.inputs['Vector']);maps[key]=tex
    sep=n.new('ShaderNodeSeparateColor');l.new(maps['color'].outputs['Color'],sep.inputs['Color'])
    ma=n.new('ShaderNodeMath');ma.operation='MAXIMUM';l.new(sep.outputs['Red'],ma.inputs[0]);l.new(sep.outputs['Green'],ma.inputs[1])
    mb=n.new('ShaderNodeMath');mb.operation='MAXIMUM';l.new(ma.outputs[0],mb.inputs[0]);l.new(sep.outputs['Blue'],mb.inputs[1])
    wear=n.new('ShaderNodeMapRange');wear.clamp=True;wear.inputs['From Min'].default_value=.05;wear.inputs['From Max'].default_value=.8;wear.inputs['To Min'].default_value=.78;wear.inputs['To Max'].default_value=1.02;l.new(mb.outputs[0],wear.inputs['Value'])
    white=n.new('ShaderNodeMixRGB');white.blend_type='MULTIPLY';white.inputs[0].default_value=1;white.inputs[1].default_value=(.77,.76,.73,1);l.new(wear.outputs['Result'],white.inputs[2])
    xyz=n.new('ShaderNodeSeparateXYZ');l.new(uv.outputs['Generated'],xyz.inputs[0]);masks=[]
    for lo,hi in [(.258/.38,.269/.38),(.280/.38,.291/.38)]:
        a=n.new('ShaderNodeMath');a.operation='GREATER_THAN';l.new(xyz.outputs['Z'],a.inputs[0]);a.inputs[1].default_value=lo
        b=n.new('ShaderNodeMath');b.operation='LESS_THAN';l.new(xyz.outputs['Z'],b.inputs[0]);b.inputs[1].default_value=hi
        both=n.new('ShaderNodeMath');both.operation='MULTIPLY';l.new(a.outputs[0],both.inputs[0]);l.new(b.outputs[0],both.inputs[1]);masks.append(both)
    mask=n.new('ShaderNodeMath');mask.operation='MAXIMUM';l.new(masks[0].outputs[0],mask.inputs[0]);l.new(masks[1].outputs[0],mask.inputs[1])
    mix=n.new('ShaderNodeMixRGB');l.new(mask.outputs[0],mix.inputs[0]);l.new(white.outputs[0],mix.inputs[1]);mix.inputs[2].default_value=(.42,.008,.013,1);l.new(mix.outputs[0],bs.inputs['Base Color'])
    if 'rough' in maps:
        maps['rough'].image.colorspace_settings.name='Non-Color';rm=n.new('ShaderNodeMapRange');rm.inputs['To Min'].default_value=.205;rm.inputs['To Max'].default_value=.32;l.new(maps['rough'].outputs['Color'],rm.inputs['Value']);l.new(rm.outputs['Result'],bs.inputs['Roughness'])
    if 'normal' in maps:
        maps['normal'].image.colorspace_settings.name='Non-Color';nm=n.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.20;l.new(maps['normal'].outputs['Color'],nm.inputs['Color']);l.new(nm.outputs['Normal'],bs.inputs['Normal'])
    bs.inputs['Coat Weight'].default_value=.30;bs.inputs['Coat Roughness'].default_value=.17
    mesh.materials.clear();mesh.materials.append(m)
    for p in mesh.polygons:p.material_index=0;p.use_smooth=p.normal.z>-.95
    bpy.data.objects.remove(source,do_unlink=True);mesh.name='Asset pin warped to frozen 38 cm collision contour';return mesh


def asset_pin_mesh_photographic(cfg,root):
 mesh=asset_pin_mesh_scanned_pin(cfg,root);mat=mesh.materials[0];n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF');tex=next(x for x in n if x.type=='TEX_IMAGE' and 'Base' in x.image.name)
 sep=n.new('ShaderNodeSeparateColor');l.new(tex.outputs['Color'],sep.inputs['Color'])
 maximum=n.new('ShaderNodeMath');maximum.operation='MAXIMUM';l.new(sep.outputs['Green'],maximum.inputs[0]);l.new(sep.outputs['Blue'],maximum.inputs[1])
 mul=n.new('ShaderNodeMath');mul.operation='MULTIPLY';mul.inputs[1].default_value=1.25;l.new(maximum.outputs[0],mul.inputs[0])
 red=n.new('ShaderNodeMath');red.operation='GREATER_THAN';l.new(sep.outputs['Red'],red.inputs[0]);l.new(mul.outputs[0],red.inputs[1])
 coating=n.new('ShaderNodeMixRGB');coating.inputs[0].default_value=.12;coating.inputs[2].default_value=(.72,.70,.67,1);l.new(tex.outputs['Color'],coating.inputs[1])
 paint=n.new('ShaderNodeMixRGB');l.new(red.outputs[0],paint.inputs[0]);l.new(coating.outputs[0],paint.inputs[1]);paint.inputs[2].default_value=(.48,.012,.009,1);l.new(paint.outputs[0],bs.inputs['Base Color']);bs.inputs['Coat Weight'].default_value=.38;bs.inputs['Coat Roughness'].default_value=.12
 mesh.name='David Geuens source UV coating / frozen silhouette';return mesh


def pin_visual_mesh(base,index):
    """Rotate the coating with an axisymmetric visual mesh, preserving its UV atlas and physics poses."""
    from mathutils import Matrix
    me=base.copy();me.name='Pin coating orientation '+str(index+1)
    me.transform(Matrix.Rotation([0.,2.0,4.2][index],4,'Z'));me.update()
    return me


def box(name,center,size,mat,bevel=0):
    x,y,z=(v/2 for v in size)
    ob=linkmesh(name,[(-x,-y,-z),(-x,-y,z),(-x,y,-z),(-x,y,z),(x,-y,-z),(x,-y,z),(x,y,-z),(x,y,z)],
        [(0,4,6,2),(1,3,7,5),(0,1,5,4),(2,6,7,3),(0,2,3,1),(4,5,7,6)],mat)
    ob.location=center
    uv=ob.data.uv_layers.new(name='Manufactured surface')
    for face in ob.data.polygons:
        for li,co in zip(face.loop_indices,[(0,0),(0,1),(1,1),(1,0)]):uv.data[li].uv=co
    if bevel:
        mod=ob.modifiers.new('Manufactured edge radius','BEVEL');mod.width=bevel;mod.segments=3
        ob.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
    return ob


def cylinder_between(name,a,b,r,mat,vertices=20):
    delta=Vector(b)-Vector(a);h=delta.length/2
    vs=[(r*math.cos(2*math.pi*j/vertices),r*math.sin(2*math.pi*j/vertices),z) for z in [-h,h] for j in range(vertices)]
    fs=[tuple(reversed(range(vertices))),tuple(range(vertices,2*vertices))]
    fs.extend((j,(j+1)%vertices,(j+1)%vertices+vertices,j+vertices) for j in range(vertices))
    ob=linkmesh(name,vs,fs,mat);ob.location=(Vector(a)+Vector(b))/2;ob.rotation_euler=delta.to_track_quat('Z','Y').to_euler()
    for f in list(ob.data.polygons)[2:]:f.use_smooth=True
    return ob


def noise_finish(name, color, roughness, metallic=0, variation=.025):
    mat = material(name, color, roughness, metallic)
    n, l = mat.node_tree.nodes, mat.node_tree.links
    bs = n.get('Principled BSDF')
    tc = n.new('ShaderNodeTexCoord')
    tex = n.new('ShaderNodeTexNoise'); tex.inputs['Scale'].default_value = 155
    l.new(tc.outputs['Object'], tex.inputs['Vector'])
    mp = n.new('ShaderNodeMapRange')
    mp.inputs['To Min'].default_value = roughness - variation
    mp.inputs['To Max'].default_value = roughness + variation
    l.new(tex.outputs['Fac'], mp.inputs['Value']); l.new(mp.outputs['Result'], bs.inputs['Roughness'])
    return mat


def cable(name, points, radius, mat):
    curve = bpy.data.curves.new(name, 'CURVE'); curve.dimensions = '3D'
    curve.resolution_u = 12; curve.bevel_depth = radius; curve.bevel_resolution = 2
    spline = curve.splines.new('BEZIER'); spline.bezier_points.add(len(points)-1)
    for p, co in zip(spline.bezier_points, points):
        p.co = co; p.handle_left_type = 'AUTO'; p.handle_right_type = 'AUTO'
    ob = bpy.data.objects.new(name, curve); bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat); return ob


def ring(name, center, major, minor, mat, axis='Z'):
    vs=[];fs=[]
    for i in range(32):
        a=i*2*math.pi/32
        for j in range(8):
            b=j*2*math.pi/8;vs.append(((major+minor*math.cos(b))*math.cos(a),(major+minor*math.cos(b))*math.sin(a),minor*math.sin(b)))
    for i in range(32):
        for j in range(8):fs.append((i*8+j,((i+1)%32)*8+j,((i+1)%32)*8+(j+1)%8,i*8+(j+1)%8))
    o=linkmesh(name,vs,fs,mat);o.location=center
    if axis == 'Y': o.rotation_euler.x = math.pi/2
    elif axis == 'X': o.rotation_euler.y = math.pi/2
    o.data.materials.append(mat)
    for p in o.data.polygons: p.use_smooth = True
    return o


def screw(name, pos, mat, axis='X', radius=.0038):
    delta = Vector({'X':(.007,0,0),'Y':(0,.007,0),'Z':(0,0,.007)}[axis])
    return cylinder_between(name, Vector(pos)-delta/2, Vector(pos)+delta/2, radius, mat, 6)


def ball_finish(ball):
    mat = material('B01 / used deep blue resin', (.009,.020,.055,1), .23)
    n, l = mat.node_tree.nodes, mat.node_tree.links; bs = n.get('Principled BSDF')
    tc = n.new('ShaderNodeTexCoord')
    tex = n.new('ShaderNodeTexNoise'); tex.inputs['Scale'].default_value = 5.2
    tex.inputs['Detail'].default_value = 5; tex.inputs['Roughness'].default_value = .7
    l.new(tc.outputs['Generated'], tex.inputs['Vector'])
    ramp = n.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = .25
    ramp.color_ramp.elements[0].color = (.003,.007,.022,1)
    ramp.color_ramp.elements[1].position = .78
    ramp.color_ramp.elements[1].color = (.018,.044,.12,1)
    l.new(tex.outputs['Fac'], ramp.inputs['Fac']); l.new(ramp.outputs['Color'], bs.inputs['Base Color'])
    fine = n.new('ShaderNodeTexNoise'); fine.inputs['Scale'].default_value=210
    l.new(tc.outputs['Generated'],fine.inputs['Vector'])
    rough=n.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.19;rough.inputs['To Max'].default_value=.265
    l.new(fine.outputs['Fac'],rough.inputs['Value']);l.new(rough.outputs['Result'],bs.inputs['Roughness'])
    bs.inputs['Coat Weight'].default_value=.18;bs.inputs['Coat Roughness'].default_value=.19
    bs.inputs['IOR'].default_value=1.50
    ball.data.materials.clear();ball.data.materials.append(mat)


def ball_asset_finish(ball,root):
    """Use the downloaded artist's photographed resin pattern, preserving B01 geometry."""
    ball_finish(ball)
    root=Path(root);path=root/'ball_ramprasath/ball.blend'
    with bpy.data.libraries.load(str(path),link=False) as (src,dst):
        dst.images=[name for name in src.images if name.startswith('orange-abstract-painting')]
    im=dst.images[0];im.colorspace_settings.name='sRGB'
    mat=ball.data.materials[0];n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get('Principled BSDF')
    tc=next(node for node in n if node.type=='TEX_COORD')
    mapping=n.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY';mapping.inputs[1].default_value=(1.35,1.35,1.35);l.new(tc.outputs['Generated'],mapping.inputs[0])
    tex=n.new('ShaderNodeTexImage');tex.image=im;tex.projection='BOX';tex.projection_blend=.35;l.new(mapping.outputs['Vector'],tex.inputs['Vector'])
    bw=n.new('ShaderNodeRGBToBW');l.new(tex.outputs['Color'],bw.inputs['Color'])
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.0025,.006,.021,1);ramp.color_ramp.elements[1].color=(.022,.058,.15,1)
    l.new(bw.outputs[0],ramp.inputs[0]);l.new(ramp.outputs[0],bs.inputs['Base Color'])
    mat.name='B01 / BlenderKit photographed resin pattern, toned navy'


def maple_material(root):
    mat=material('Sealed hard maple / photographed one metre grain',(.48,.31,.15,1),.205)
    n,l=mat.node_tree.nodes,mat.node_tree.links;bs=n.get('Principled BSDF');tc=n.new('ShaderNodeTexCoord')
    for kind,filename in [('color','white_maple_veneer_diff_8k.jpg'),('rough','white_maple_veneer_rough_4k.jpg'),('normal','white_maple_veneer_nor_gl_4k.jpg')]:
        im=bpy.data.images.load(str(root/'white_maple_veneer'/filename),check_existing=True)
        if kind!='color':im.colorspace_settings.name='Non-Color'
        tex=n.new('ShaderNodeTexImage');tex.image=im;l.new(tc.outputs['UV'],tex.inputs['Vector'])
        if kind=='color':
            hs=n.new('ShaderNodeHueSaturation');hs.inputs['Saturation'].default_value=.85;hs.inputs['Value'].default_value=.45;l.new(tex.outputs['Color'],hs.inputs['Color'])
            tint=n.new('ShaderNodeMixRGB');tint.name='Amber polyurethane finish';tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1;tint.inputs[2].default_value=(1.,.72,.42,1)
            l.new(hs.outputs['Color'],tint.inputs[1]);l.new(tint.outputs[0],bs.inputs['Base Color'])
        elif kind=='rough':
            mp=n.new('ShaderNodeMapRange');mp.inputs['To Min'].default_value=.095;mp.inputs['To Max'].default_value=.145
            l.new(tex.outputs['Color'],mp.inputs['Value']);l.new(mp.outputs['Result'],bs.inputs['Roughness'])
        else:
            nm=n.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.025
            l.new(tex.outputs['Color'],nm.inputs['Color']);l.new(nm.outputs['Normal'],bs.inputs['Normal'])
    bs.inputs['Coat Weight'].default_value=.22;bs.inputs['Coat Roughness'].default_value=.08
    bs.inputs['Anisotropic'].default_value=.06
    bs.inputs['Anisotropic Rotation'].default_value=.25
    tangent=n.new('ShaderNodeTangent');tangent.direction_type='UV_MAP';tangent.uv_map='Maple grain in metres';l.new(tangent.outputs['Tangent'],bs.inputs['Tangent'])
    return mat


def boards(cfg,off,mat,seed):
    rng=random.Random(seed);p=cfg['physics']['lane'];w=p['width_m'];bw=w/39
    verts=[];faces=[];uvs=[];tone=[]
    for j in range(39):
        # Flush joints under continuous finish; a 0.16 mm hairline, not open parquet gaps.
        y0=off-w/2+j*bw+.00008;y1=off-w/2+(j+1)*bw-.00008
        cuts=[p['front_x_m']];x=p['front_x_m']+rng.uniform(.3,1.8)
        while x<p['deck_end_x_m']:cuts.append(x);x+=rng.uniform(1.2,2.4)
        cuts.append(p['deck_end_x_m'])
        for left,right in zip(cuts,cuts[1:]):
            start=len(verts);u=rng.random();v=rng.random()
            verts.extend([(left+.00007,y0,0),(right-.00007,y0,0),(right-.00007,y1,0),(left+.00007,y1,0)])
            faces.append((start,start+1,start+2,start+3));uvs.extend([(u,v),(u,v+right-left),(u+bw,v+right-left),(u+bw,v)])
            tone.append(rng.randrange(7))
    ob=linkmesh('Maple lane boards / '+str(off),verts,faces,None);layer=ob.data.uv_layers.new(name='Maple grain in metres')
    for loop in ob.data.loops:layer.data[loop.index].uv=uvs[loop.vertex_index]
    for k,factor in enumerate([.91,.94,.97,1.,1.02,1.04,1.06]):
        variant=mat.copy();variant.name='Maple board natural shade '+str(k)
        tint=variant.node_tree.nodes.get('Amber polyurethane finish');tint.inputs[2].default_value=(factor,.72*factor,.42*factor,1)
        ob.data.materials.append(variant)
    for poly,index in zip(ob.data.polygons,tone):poly.material_index=index
    return ob


def coating_scuffs(off,mat,seed):
    rng=random.Random(seed);vs=[];fs=[]
    for i in range(27):
        x=rng.uniform(-.50,.88);y=off+rng.uniform(-.48,.48);angle=rng.uniform(-math.pi,math.pi)
        length=rng.uniform(.012,.065);width=rng.uniform(.00025,.00085)
        tangent=Vector((math.cos(angle),math.sin(angle),0));side=Vector((-math.sin(angle),math.cos(angle),0))
        center=Vector((x,y,.00011));k=len(vs)
        vs.extend([center-tangent*length/2,center+side*width,center+tangent*length/2,center-side*width]);fs.append((k,k+1,k+2,k+3))
    return linkmesh('Restrained pin deck coating contact scuffs',vs,fs,mat)


def machine(off,root,m):
    dark,steel,rubber=m['dark'],m['steel'],m['rubber'];y0=off
    # Welded frame, mounted to the rear foundations. The pinsetting table is parked.
    for y in [-.73,.73]:
        box('Machine rear upright',(2.96,off+y,1.11),(.070,.070,2.30),dark,.003)
        box('Machine upper longitudinal box section',(1.90,off+y,1.62),(2.17,.060,.095),dark,.002)
        box('Machine lower longitudinal box section',(1.90,off+y,.96),(2.17,.045,.060),dark,.002)
        cylinder_between('Table lift guide',(.90,off+y,.86),(.90,off+y,1.63),.015,steel)
        cylinder_between('Rear frame cross brace',(1.28,off+y,.98),(2.94,off+y,1.65),.012,dark)
        for x,z in [(.90,1.64),(2.94,1.64),(2.94,.98)]:screw('Frame captive bolt',(x,off+y-.034,z),steel,'Y',.006)
    for x in [.90,1.50,2.90]:
        box('Upper machine cross member',(x,off,1.64),(.06,1.52,.075),dark,.002)
    box('Front pinsetter beam',(.91,off,.935),(.095,1.56,.11),dark,.004)
    box('Front pinsetter beam lower flange',(.865,off,.877),(.024,1.57,.014),steel,.001)
    for y in [-.67,-.45,-.23,0,.23,.45,.67]:screw('Front beam fastener',(.858,off+y,.94),steel,'X',.004)
    # Folded front guarding encloses the setting cells; its return flanges attach to the frame.
    box('Pinsetter front guard',(.23,off,1.12),(.070,1.52,.24),dark,.005)
    box('Guard lower folded flange',(.24,off,.997),(.115,1.55,.018),dark,.002)
    for y in [-.71,.71]:box('Guard side return',(.59,off+y,1.12),(.68,.034,.24),dark,.002)
    for y in [-.65,-.32,0,.32,.65]:screw('Guard removable cover fastener',(.191,off+y,1.16),steel,'X',.004)
    # Ten cell carriers, open pressed-steel rings and paired gripping pads, no decorative extra pins.
    for row in range(4):
        x=.35+row*.2598
        box('Parked table transverse rail',(x,off,1.16),(.033,.32+row*.30,.032),steel,.001)
        for j in range(row+1):
            y=off+(2*j-row)*.15
            ring('Empty spotting-cell steel carrier',(x,y,1.08),.058,.006,steel)
            for side in [-1,1]:
                box('Spotting cell rubber gripping shoe',(x,y+side*.047,1.065),(.056,.018,.033),rubber,.004)
                cylinder_between('Cell pivot link',(x-.035,y+side*.048,1.075),(x-.020,y+side*.065,1.15),.005,dark,12)
            screw('Cell mount screw',(x-.015,y,1.173),dark,'Z',.003)
    # Raised sweep with real side rockers, hung clear of every cached moving body.
    box('Raised sweep rake',(.51,off,.78),(.045,1.37,.062),dark,.004)
    for y in [-.65,.65]:
        cylinder_between('Sweep rocker arm',(.51,off+y,.80),(1.80,off+y,1.39),.013,steel)
        cylinder_between('Sweep linkage pivot',(1.80,off+y-.03,1.39),(1.80,off+y+.03,1.39),.032,dark)
    # Distributor banks, guide rollers, side-mounted drive belts and motors.
    for y in [-.48,0,.48]:
        box('Pin distributor channel',(2.03,off+y,1.39),(1.37,.19,.035),steel,.002)
        for side in [-1,1]:box('Distributor channel folded flange',(2.03,off+y+side*.104,1.44),(1.37,.017,.12),dark,.002)
        for x in [1.45,1.78,2.12,2.48]:cylinder_between('Distributor urethane roller',(x,off+y-.10,1.41),(x,off+y+.10,1.41),.018,rubber)
    for y in [-.79,.79]:
        for x in [1.78,2.67]:
            cylinder_between('Drive pulley hub',(x,off+y-.025,1.54),(x,off+y+.025,1.54),.072,dark,32)
            ring('Drive pulley rim',(x,off+y,1.54),.077,.006,steel,'Y')
            screw('Drive pulley centre bolt',(x,off+y,1.54),steel,'Y',.009)
        cable('Tensioned drive belt',[(1.78,off+y,1.62),(2.67,off+y,1.62),(2.75,off+y,1.54),(2.67,off+y,1.46),(1.78,off+y,1.46),(1.70,off+y,1.54),(1.78,off+y,1.62)],.008,rubber)
    cylinder_between('Motor finned housing',(2.67,off+.39,1.54),(2.67,off+.70,1.54),.093,dark,32)
    for j in range(9):ring('Motor cooling rib',(2.67,off+.41+j*.029,1.54),.095,.004,steel,'Y')
    box('Sealed electrical cabinet',(2.91,off-.36,1.82),(.19,.38,.41),m['panel'],.006)
    for j in range(5):box('Cabinet louvre',(2.807,off-.36,1.73+j*.031),(.006,.20,.006),dark)
    for y in [-.47,-.25]:screw('Cabinet cover fastener',(2.809,off+y,1.99),steel,'X')
    cable('Electrical loom',[(2.81,off-.36,1.64),(2.48,off-.65,1.53),(1.92,off-.65,1.60),(1.60,off-.55,1.17)],.010,rubber)
    for j,y in enumerate([-.45,-.15,.15,.45]):
        cable('Blue pneumatic service line',[(2.82,off-.36,1.67),(2.35,off+y,1.61),(1.48,off+y,1.47),(.83,off+y,1.17)],.004,m['hose'])
    # A restrained identification plaque; lane numbers belong to a continuous masking facade.
    plaque=box('Machine service plate',(.854,off-.47,.941),(.003,.15,.045),steel,.0005)
    return plaque


LANES = [-2, -1, 0, 1, 2, 3]


PITCH = 1.78


# Masking unit and kickback extents (m, lane frame: headpin at x=0, deck end 0.95, pit back 2.85).
MASK_FRONT_X = -.39


MASK_BOTTOM_Z = 1.10


KICKBACK_X = (-.25, 2.97)


KICKBACK_HALF_GAP = PITCH/2 - .0475


# Ten-pin triangle in the lane frame, same 0.30 m spacing as the three simulated pins (spots 1-3).
PIN_SPOTS = [(row*.2598076, (j-row/2)*.30) for row in range(4) for j in range(row+1)]


# Range finders sit on board 10 from each gutter, 40-43 ft past the foul line.
RANGE_FINDER_X = (-18.29+12.19, -18.29+13.11)


def laminate(name, color, roughness, scuff_color, seed):
    """Satin high-pressure laminate with sparse lighter pin-impact scuffs."""
    mat = noise_finish(name, color, roughness, 0, .04)
    n, l = mat.node_tree.nodes, mat.node_tree.links; bs = n.get('Principled BSDF')
    tc = n.new('ShaderNodeTexCoord')
    marks = n.new('ShaderNodeTexNoise'); marks.noise_dimensions = '4D'
    marks.inputs['Scale'].default_value = 9; marks.inputs['Detail'].default_value = 8
    next(s for s in marks.inputs if s.name == 'W').default_value = seed
    l.new(tc.outputs['Object'], marks.inputs['Vector'])
    ramp = n.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = .66; ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
    ramp.color_ramp.elements[1].position = .74; ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
    l.new(marks.outputs['Fac'], ramp.inputs['Fac'])
    mix = n.new('ShaderNodeMixRGB'); mix.inputs[1].default_value = color; mix.inputs[2].default_value = scuff_color
    l.new(ramp.outputs['Color'], mix.inputs[0]); l.new(mix.outputs['Color'], bs.inputs['Base Color'])
    return mat


def curtain_material():
    """Black pit curtain: heavy fabric, vertical folds as shading only (the contact face stays flat)."""
    mat = material('Black pit curtain fabric', (.006, .006, .007, 1), .95)
    n, l = mat.node_tree.nodes, mat.node_tree.links; bs = n.get('Principled BSDF')
    bs.inputs['Sheen Weight'].default_value = .35; bs.inputs['Sheen Roughness'].default_value = .45
    tc = n.new('ShaderNodeTexCoord')
    wave = n.new('ShaderNodeTexWave'); wave.bands_direction = 'Y'
    wave.inputs['Scale'].default_value = 7.5; wave.inputs['Distortion'].default_value = 2.2
    wave.inputs['Detail'].default_value = 1.5; l.new(tc.outputs['Object'], wave.inputs['Vector'])
    bump = n.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = .55; bump.inputs['Distance'].default_value = .02
    l.new(wave.outputs['Fac'], bump.inputs['Height']); l.new(bump.outputs['Normal'], bs.inputs['Normal'])
    return mat


def masking_material():
    """Printed masking panel: deep night-blue with a soft violet band, matte vinyl."""
    mat = material('Printed masking unit vinyl', (.010, .014, .040, 1), .62)
    n, l = mat.node_tree.nodes, mat.node_tree.links; bs = n.get('Principled BSDF')
    tc = n.new('ShaderNodeTexCoord'); sep = n.new('ShaderNodeSeparateXYZ'); l.new(tc.outputs['Object'], sep.inputs['Vector'])
    warp = n.new('ShaderNodeTexNoise'); warp.inputs['Scale'].default_value = .35; warp.inputs['Detail'].default_value = 3
    l.new(tc.outputs['Object'], warp.inputs['Vector'])
    add = n.new('ShaderNodeMath'); add.operation = 'MULTIPLY_ADD'; add.inputs[1].default_value = .9
    l.new(warp.outputs['Fac'], add.inputs[0]); l.new(sep.outputs['Z'], add.inputs[2])
    ramp = n.new('ShaderNodeValToRGB'); e = ramp.color_ramp.elements
    e[0].position = .45; e[0].color = (.010, .014, .040, 1)
    e[1].position = 1.25; e[1].color = (.004, .005, .013, 1)
    mid = e.new(.80); mid.color = (.050, .022, .085, 1)
    norm = n.new('ShaderNodeMapRange'); norm.inputs['From Min'].default_value = 0; norm.inputs['From Max'].default_value = 2.6
    l.new(add.outputs[0], norm.inputs['Value']); l.new(norm.outputs['Result'], ramp.inputs['Fac'])
    l.new(ramp.outputs['Color'], bs.inputs['Base Color'])
    return mat


def emissive(name, color, strength, base=(.8, .8, .8, 1)):
    mat = material(name, base, .3); bs = mat.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Emission Color'].default_value = color; bs.inputs['Emission Strength'].default_value = strength
    return mat


def retint_lane(ob, wood_tint):
    """Lighter, less amber synthetic-maple finish; board-to-board tone variation kept."""
    for mat, factor in zip(ob.data.materials, [.96, .975, .99, 1., 1.01, 1.025, 1.04]):
        tint = mat.node_tree.nodes.get('Amber polyurethane finish')
        tint.inputs[2].default_value = tuple(min(1., c*factor) for c in wood_tint) + (1,)


def lane_wear(mat, venue):
    """Dry back-end: faint lengthwise conditioner streaks and a hazed ball track in the coat sheen."""
    n, l = mat.node_tree.nodes, mat.node_tree.links; bs = n.get('Principled BSDF')
    tc = n.new('ShaderNodeTexCoord'); stretch = n.new('ShaderNodeMapping')
    stretch.inputs['Scale'].default_value = (.18, 11., 1.); l.new(tc.outputs['Object'], stretch.inputs['Vector'])
    streak = n.new('ShaderNodeTexNoise'); streak.inputs['Scale'].default_value = 3.; streak.inputs['Detail'].default_value = 6
    l.new(stretch.outputs['Vector'], streak.inputs['Vector'])
    sep = n.new('ShaderNodeSeparateXYZ'); l.new(tc.outputs['Object'], sep.inputs['Vector'])
    # Ball track: a soft band a little right of centre on every lane (lane frame repeats every pitch).
    wrap = n.new('ShaderNodeMath'); wrap.operation = 'WRAP'; wrap.inputs[1].default_value = -PITCH/2; wrap.inputs[2].default_value = PITCH/2
    l.new(sep.outputs['Y'], wrap.inputs[0])
    track = n.new('ShaderNodeMapRange'); track.interpolation_type = 'SMOOTHSTEP'
    track.inputs['From Min'].default_value = .22; track.inputs['From Max'].default_value = .06
    dist = n.new('ShaderNodeMath'); dist.operation = 'ABSOLUTE'
    sub = n.new('ShaderNodeMath'); sub.operation = 'SUBTRACT'; sub.inputs[1].default_value = -.05
    l.new(wrap.outputs[0], sub.inputs[0]); l.new(sub.outputs[0], dist.inputs[0]); l.new(dist.outputs[0], track.inputs['Value'])
    rough = next(nd for nd in n if nd.bl_idname == 'ShaderNodeMapRange' and nd.outputs['Result'].links and nd.outputs['Result'].links[0].to_node == bs)
    a = n.new('ShaderNodeMath'); a.operation = 'MULTIPLY_ADD'; a.inputs[1].default_value = venue['streak_roughness']
    l.new(streak.outputs['Fac'], a.inputs[0]); l.new(rough.outputs['Result'], a.inputs[2])
    b = n.new('ShaderNodeMath'); b.operation = 'MULTIPLY_ADD'; b.inputs[1].default_value = venue['track_roughness']
    l.new(track.outputs['Result'], b.inputs[0]); l.new(a.outputs[0], b.inputs[2])
    l.new(b.outputs[0], bs.inputs['Roughness'])
    c = n.new('ShaderNodeMath'); c.operation = 'MULTIPLY_ADD'; c.inputs[1].default_value = venue['streak_roughness']
    c.inputs[2].default_value = bs.inputs['Coat Roughness'].default_value
    l.new(streak.outputs['Fac'], c.inputs[0]); l.new(c.outputs[0], bs.inputs['Coat Roughness'])


def deck_finish(mat, venue):
    """Synthetic pin deck panel from just ahead of the headpin: cooler tone, duller coat, grey ball and pin impact wear."""
    n, l = mat.node_tree.nodes, mat.node_tree.links; bs = n.get('Principled BSDF')
    geo = n.new('ShaderNodeNewGeometry'); sep = n.new('ShaderNodeSeparateXYZ'); l.new(geo.outputs['Position'], sep.inputs['Vector'])
    deck = n.new('ShaderNodeMapRange'); deck.inputs['From Min'].default_value = venue['deck_start_x_m']-.002
    deck.inputs['From Max'].default_value = venue['deck_start_x_m']+.002; l.new(sep.outputs['X'], deck.inputs['Value'])
    wear = n.new('ShaderNodeTexNoise'); wear.inputs['Scale'].default_value = 14; wear.inputs['Detail'].default_value = 9
    wear.inputs['Roughness'].default_value = .62; l.new(geo.outputs['Position'], wear.inputs['Vector'])
    ramp = n.new('ShaderNodeValToRGB'); e = ramp.color_ramp.elements
    e[0].position = .50; e[0].color = (0, 0, 0, 1); e[1].position = .72; e[1].color = (1, 1, 1, 1)
    l.new(wear.outputs['Fac'], ramp.inputs['Fac'])
    amount = n.new('ShaderNodeMath'); amount.operation = 'MULTIPLY'; amount.inputs[1].default_value = venue['deck_wear']
    l.new(ramp.outputs['Color'], amount.inputs[0])
    tint_link = next(k for k in l if k.to_socket == bs.inputs['Base Color'])
    toned = n.new('ShaderNodeMixRGB'); toned.blend_type = 'MULTIPLY'; toned.inputs[2].default_value = tuple(venue['deck_tint'])+(1,)
    l.new(deck.outputs['Result'], toned.inputs[0]); l.new(tint_link.from_socket, toned.inputs[1])
    worn = n.new('ShaderNodeMixRGB'); worn.inputs[2].default_value = (.20, .19, .18, 1)
    gate = n.new('ShaderNodeMath'); gate.operation = 'MULTIPLY'
    l.new(amount.outputs[0], gate.inputs[0]); l.new(deck.outputs['Result'], gate.inputs[1])
    l.new(gate.outputs[0], worn.inputs[0]); l.new(toned.outputs['Color'], worn.inputs[1]); l.new(worn.outputs['Color'], bs.inputs['Base Color'])
    rough_link = next(k for k in l if k.to_socket == bs.inputs['Roughness'])
    dull = n.new('ShaderNodeMath'); dull.operation = 'MULTIPLY_ADD'; dull.inputs[1].default_value = venue['deck_roughness_add']
    l.new(deck.outputs['Result'], dull.inputs[0]); l.new(rough_link.from_socket, dull.inputs[2]); l.new(dull.outputs[0], bs.inputs['Roughness'])


def deck_and_lane_inlays(cfg, off, venue, mark, spot):
    """All ten pin spots on every deck, the deck panel joint, and the two range finders."""
    w = cfg['physics']['lane']['width_m']; x = venue['deck_start_x_m']
    for sx, sy in PIN_SPOTS: disk('Pin deck spot', sx, off+sy, .00018, venue['pin_spot_radius_m'], spot)
    linkmesh('Pin deck panel joint', [(x-.0007, off-w/2, .00016), (x+.0007, off-w/2, .00016), (x+.0007, off+w/2, .00016), (x-.0007, off+w/2, .00016)], [(0, 1, 2, 3)], spot)
    y = w/2-9.5*w/39; x0, x1 = RANGE_FINDER_X
    for side in [-1, 1]:
        c = off+side*y
        linkmesh('Range finder inlay', [(x0, c-.0045, .00015), (x1, c-.0045, .00015), (x1, c+.0045, .00015), (x0, c+.0045, .00015)], [(0, 1, 2, 3)], mark)


def lowered_sweep(off, m):
    """Idle lane: sweep down in guard position in front of an empty deck, rocker arms back to the machine pivots."""
    x = -.16; half = KICKBACK_HALF_GAP-.02
    box('Lowered sweep board (idle lane)', (x, off, .115), (.030, 2*half, .19), m['dark'], .004)
    box('Lowered sweep rubber cushion', (x, off, .018), (.036, 2*half, .030), m['rubber'], .006)
    box('Lowered sweep aluminium cap', (x, off, .212), (.034, 2*half, .012), m['alu'], .002)
    for y in [-.65, .65]: cylinder_between('Lowered sweep rocker arm', (x+.02, off+y, .19), (1.80, off+y, 1.39), .013, m['steel'])


def idle_lane_racks(cfg, base_pin):
    """Optional full ten-pin racks on the neighbouring lanes (static; not tracked, not in ground truth)."""
    if cfg['appearance']['venue']['idle_lanes'] != 'racked': return
    rng = random.Random(409071); z = pin_mass_properties()['com_height_m']
    for lane in LANES:
        if lane == 0: continue
        for k, (sx, sy) in enumerate(PIN_SPOTS):
            o = bpy.data.objects.new('Idle lane standing pin', pin_visual_mesh(base_pin, k % 3)); bpy.context.collection.objects.link(o)
            o.location = (sx, lane*PITCH+sy, z); o.rotation_euler = (0, 0, rng.uniform(0, 2*math.pi))


def masking_art(venue):
    """Printed masking vinyl, one panel per lane: night-blue field and two flowing light ribbons."""
    import numpy as np
    w, h = 1024, 1324
    img = bpy.data.images.new('Masking unit print', w, h, float_buffer=True)
    u = np.linspace(0, 1, w)[None, :]; v = np.linspace(0, 1, h)[:, None]
    col = np.array(venue['mask_low'])*(1-v[..., None])+np.array(venue['mask_high'])*v[..., None]
    col = np.broadcast_to(col, (h, w, 3)).copy()
    for amp, phase, off, width, c in venue['mask_ribbons']:
        centre = off+amp*np.sin(2*np.pi*u*.9+phase)+.05*u
        a = np.exp(-((v-centre)/width)**2)[..., None]
        rim = np.exp(-((v-centre-width*1.1)/(width*.12))**2)[..., None]
        col = col*(1-.85*a)+np.array(c)*.85*a+np.array(c)*1.6*rim
    rgba = np.concatenate([col, np.ones((h, w, 1))], axis=2).astype(np.float32)
    img.pixels.foreach_set(rgba.ravel()); img.pack()
    mat = material('Printed masking unit vinyl panel', (.02, .02, .05, 1), .58)
    n, l = mat.node_tree.nodes, mat.node_tree.links
    tex = n.new('ShaderNodeTexImage'); tex.image = img; l.new(tex.outputs['Color'], n.get('Principled BSDF').inputs['Base Color'])
    return mat


def kickback(y, m, sign):
    """Full-height side partition from just ahead of the headpin to the pit back."""
    x0, x1 = KICKBACK_X; t = .095
    box('Kickback laminate panel', ((x0+x1)/2, y, (MASK_BOTTOM_Z-.33)/2), (x1-x0, t, MASK_BOTTOM_Z+.33), m['kick'], .002)
    box('Kickback front rubber edge guard', (x0-.006, y, (MASK_BOTTOM_Z-.02)/2), (.014, t+.008, MASK_BOTTOM_Z+.02), m['edge'], .005)
    for face in [-1, 1]:
        fy = y+face*(t/2+.0012)
        # Lower stainless kick plate where pins strike, with countersunk screws.
        box('Kickback steel strike plate', (.55, fy, .17), (1.30, .002, .26), m['strike'], .0005)
        for x in [-.05, .30, .65, 1.0, 1.15]:
            for z in [.07, .27]: screw('Strike plate screw', (x, fy, z), m['alu'], 'Y', .0035)
        box('Kickback top seal', ((x0+x1)/2, fy, MASK_BOTTOM_Z-.012), (x1-x0, .003, .024), m['dark'])


def architecture_venue(cfg, root):
    root = Path(root); app = cfg['appearance']; venue = app['venue']
    m = {
      'dark': noise_finish('Black phosphate and powder-coated machine steel', (.017, .020, .024, 1), .43, .35),
      'steel': noise_finish('Dull zinc plated fasteners', (.23, .25, .26, 1), .42, .65),
      'rubber': noise_finish('Rubber pit conveyor and impact cushion', (.012, .013, .014, 1), .8),
      'gutter': noise_finish('Used charcoal gutter resin', (.022, .024, .027, 1), .46, 0, .08),
      'trim': noise_finish('Satin lane capping', (.030, .033, .038, 1), .32, .10),
      'under': noise_finish('Maple phenolic backing', (.21, .117, .053, 1), .44),
      'panel': noise_finish('Service cabinet grey', (.15, .17, .17, 1), .52, .1),
      'hose': material('Dark blue polyurethane service hose', (.009, .035, .062, 1), .38),
      'kick': laminate('Charcoal kickback laminate', tuple(venue['kickback_color']) + (1,), .38, (.09, .09, .09, 1), 3.1),
      'alu': noise_finish('Anodised aluminium nosing', (.42, .43, .44, 1), .32, .9),
      'edge': noise_finish('Black rubber kickback edge guard', (.010, .010, .011, 1), .62, 0, .05),
      'strike': noise_finish('Black satin steel kick plate', (.030, .031, .034, 1), .34, .3, .02),
      'curtain': curtain_material(),
      'mask': masking_material(),
    }
    wood = maple_material(root)
    hs = next(nd for nd in wood.node_tree.nodes if nd.bl_idname == 'ShaderNodeHueSaturation')
    hs.inputs['Saturation'].default_value = venue['wood_saturation']; hs.inputs['Value'].default_value = venue['wood_value']
    wood.node_tree.nodes.get('Principled BSDF').inputs['Coat Weight'].default_value = venue['lane_coat_weight']
    lane_wear(wood, venue); deck_finish(wood, venue)
    p = cfg['physics']['lane']
    marks = material('Black-brown flush lane inlay', (.030, .020, .012, 1), .32)
    spot = material('Black pin spot and deck joint print', (.018, .017, .016, 1), .40)
    scuff = material('Rubber transfer and hairline coating wear', (.21, .13, .071, 1), .38)
    for lane in LANES:
        off = lane*PITCH
        retint_lane(boards(cfg, off, wood, 409051+lane), venue['wood_tint'])
        lane_markings(cfg, off, marks); coating_scuffs(off, scuff, 109051+lane)
        deck_and_lane_inlays(cfg, off, venue, marks, spot)
        for c in fixed_geometry(cfg):
            if c['kind'] != 'box': continue
            loc = list(c['center']); loc[1] += off; size = list(c['size'])
            if c['id'] == 'pit_back': mat = m['curtain']
            elif c['id'].startswith('pit'): mat = m['rubber']
            elif 'divider' in c['id']: mat = m['trim']
            else: mat = m['under']
            if c['id'] == 'lane_deck': loc[2] -= .0005; size[2] -= .001
            box('Immutable contact surface / '+str(lane)+' / '+c['id'], loc, size, mat, .001 if 'divider' in c['id'] else 0)
        for sign in [-1, 1]:
            vs = []
            for x in [p['front_x_m'], p['deck_end_x_m']]:
                for j in range(81):
                    a = math.pi*j/80; vs.append((x, off+sign*(p['width_m']/2+p['gutter_width_m']*(1-math.cos(a))/2), -p['gutter_depth_m']*math.sin(a)))
            ob = linkmesh('Continuous concave gutter / '+str(lane)+' / '+str(sign), vs,
                [(j, j+1, j+82, j+81) if sign == 1 else (j+81, j+82, j+1, j) for j in range(80)], m['gutter'])
            for f in ob.data.polygons: f.use_smooth = True
        box('Recessed pin deck end protection', (.944, off, -.049), (.010, p['width_m'], .090), m['dark'], .0005)
        # Curtain hangs from the machine frame down into the pit; the contact face itself is the pit back.
        box('Pit curtain upper drop', (2.91, off, (MASK_BOTTOM_Z+1.9)/2), (.12, 1.60, 1.9-MASK_BOTTOM_Z), m['curtain'])
        for x in [2.91, 3.14]: cylinder_between('Conveyor rear roller', (x, off-.70, .01), (x, off+.70, .01), .072, m['dark'], 32)
        before = set(bpy.data.objects); machine(off, root, m)
        if lane and venue['idle_lanes'] == 'closed':
            for ob in set(bpy.data.objects)-before:
                if ob.name.startswith(('Raised sweep rake', 'Sweep rocker arm')): bpy.data.objects.remove(ob)
            lowered_sweep(off, m)
    ymin = LANES[0]*PITCH-PITCH/2; ymax = LANES[-1]*PITCH+PITCH/2; cy = (ymin+ymax)/2; total = ymax-ymin
    for k in range(len(LANES)+1):
        y = ymin+k*PITCH
        if 0 < k < len(LANES):
            box('Continuous shared division cap', (-7.04, y, .033), (15.94, .094, .020), m['trim'], .002)
            for x in [-10.5, -7.5, -4.5, -1.5]:
                box('Flush capping joint', (x, y, .0432), (.0018, .093, .0008), m['dark'])
        kickback(y, m, 1)
    # Masking unit: printed fascia, light shelf soffit, lane numbers and LED edge.
    mask_top = 3.40; depth = .70-MASK_FRONT_X
    box('Masking unit fascia', (MASK_FRONT_X+.03, cy, (MASK_BOTTOM_Z+mask_top)/2), (.06, total, mask_top-MASK_BOTTOM_Z), m['mask'], .004)
    box('Masking unit light shelf', (MASK_FRONT_X+depth/2, cy, MASK_BOTTOM_Z+.02), (depth, total, .04), m['dark'], .003)
    box('Masking unit enclosure top', (MASK_FRONT_X+depth/2+.5, cy, mask_top), (depth+1., total, .04), m['dark'])
    edge = emissive('Masking LED edge strip', tuple(venue['led_color'])+(1,), venue['led_strength'])
    box('Masking LED edge strip', (MASK_FRONT_X-.002, cy, MASK_BOTTOM_Z+.012), (.006, total, .010), edge)
    numeral = emissive('Illuminated lane numerals', (1, .97, .92, 1), 2.2)
    diffuser = emissive('Pin light diffuser', (1, .97, .92, 1), venue['pin_diffuser_strength'])
    font = root/'fonts/DejaVuSansCondensed.ttf'
    art = masking_art(venue)
    for lane in LANES:
        off = lane*PITCH; x = MASK_FRONT_X-.0015; zt = mask_top-.02
        panel_ob = linkmesh('Masking unit printed panel / '+str(lane),
            [(x, off+PITCH/2-.004, MASK_BOTTOM_Z+.03), (x, off-PITCH/2+.004, MASK_BOTTOM_Z+.03), (x, off-PITCH/2+.004, zt), (x, off+PITCH/2-.004, zt)], [(0, 1, 2, 3)], art)
        uv = panel_ob.data.uv_layers.new(name='Print')
        for li, co in zip(range(4), [(0, 0), (1, 0), (1, 1), (0, 1)]): uv.data[li].uv = co
        number = text('Lane number', str(9-lane), (MASK_FRONT_X-.003, off, MASK_BOTTOM_Z+.13), .17, numeral)
        number.location.x = MASK_FRONT_X-.004
        if font.exists(): number.data.font = bpy.data.fonts.load(str(font))
        box('Pin light housing', (MASK_FRONT_X+.13, off, MASK_BOTTOM_Z-.012), (.13, 1.36, .024), m['dark'], .002)
        box('Pin light diffuser', (MASK_FRONT_X+.13, off, MASK_BOTTOM_Z-.0245), (.09, 1.30, .002), diffuser)
    # Hall around the approach end; anything behind the masking unit is enclosed.
    plaster = noise_finish('Warm acoustic plaster', (.16, .16, .15, 1), .9)
    panel = noise_finish('Deep teal acoustic side panels', (.020, .036, .040, 1), .65)
    box('Service room rear wall', (3.78, cy, 1.56), (.13, total+.2, 4.1), plaster)
    for y in [ymin-.10, ymax+.10]:
        box('Continuous hall side wall', (-6.5, y, 1.60), (21, .16, 3.9), plaster)
        box('Hall skirting', (-6.5, y, 0.16), (21, .18, .32), m['dark'])
        for x in [-8, -5, -2]: box('Side acoustic panel', (x, y-(.09 if y > 0 else -.09), 1.43), (1.35, .035, 1.8), panel, .004)
    ceiling = noise_finish('Perforated charcoal suspended ceiling', (.040, .043, .042, 1), .92)
    box('Continuous suspended ceiling', (-8.7, cy, 3.52), (17.4, total+.3, .12), ceiling)
    for x in [-12, -10.8, -9.6, -8.4, -7.2, -6, -4.8, -3.6, -2.4, -1.2]:
        box('Suspended ceiling T rail', (x, cy, 3.455), (.014, total, .018), m['dark'])
    box('Continuous subfloor foundation', (-7, cy, -.48), (29, total+.4, .16), m['rubber'])
    return [{'revision': 'venue', 'lane_width_m': p['width_m'], 'lane_pitch_m': PITCH, 'board_count': 39,
        'masking_front_x_m': MASK_FRONT_X, 'masking_bottom_z_m': MASK_BOTTOM_Z, 'kickback_x_m': list(KICKBACK_X),
        'kickback_inner_abs_y_m': KICKBACK_HALF_GAP, 'idle_lanes': venue['idle_lanes'], 'pin_deck_start_x_m': venue['deck_start_x_m'], 'pit_back_material': 'black curtain fabric (shading-only folds; contact face unchanged)',
        'pin_asset': 'David Geuens, BlenderKit, royalty free; original UV atlas retained',
        'wood_asset': 'Jenelle van Heerden, Poly Haven white_maple_veneer, CC0, 1 m tile',
        'fixed_contacts': 'unchanged source collision geometry; kickbacks, masking and curtain are static visuals outside the swept volume'}]


def lens_finish(s, venue):
    """Subtle lens bloom on emitters and natural corner fall-off; no distortion, so projections stay exact."""
    s.use_nodes = True; t = s.node_tree; n, l = t.nodes, t.links
    rl = n.get('Render Layers'); comp = n.get('Composite')
    glare = n.new('CompositorNodeGlare'); glare.glare_type = 'FOG_GLOW'; glare.quality = 'HIGH'
    glare.threshold = venue['glare_threshold']; glare.mix = venue['glare_mix']; glare.size = 8
    mask = n.new('CompositorNodeEllipseMask'); mask.width = 1.05; mask.height = 1.15
    blur = n.new('CompositorNodeBlur'); blur.filter_type = 'GAUSS'; blur.use_relative = True; blur.factor_x = 30; blur.factor_y = 30
    l.new(mask.outputs['Mask'], blur.inputs['Image'])
    vig = n.new('CompositorNodeMixRGB'); vig.blend_type = 'MULTIPLY'; vig.inputs[0].default_value = venue['vignette']
    l.new(rl.outputs['Image'], glare.inputs['Image']); l.new(glare.outputs['Image'], vig.inputs[1]); l.new(blur.outputs['Image'], vig.inputs[2])
    l.new(vig.outputs['Image'], comp.inputs['Image'])


def _texture_dir(root, asset):
    """root is <assets>/bowling_documentary; the CC0 scans live in <assets>/polyhaven/<id>."""
    return Path(root).parent / 'polyhaven' / asset


def _image(path, non_color):
    im = bpy.data.images.load(str(path), check_existing=True)
    if non_color: im.colorspace_settings.name = 'Non-Color'
    return im


def asset_pin_mesh(cfg, root):
    """Scanned pin mesh and coating, with the printed maker marks painted out of the base colour."""
    import numpy as np
    mesh = asset_pin_mesh_photographic(cfg, root); p7 = cfg['appearance']['photographic_finish']['pin']
    nodes = [n for m in mesh.materials for n in m.node_tree.nodes
             if n.type == 'TEX_IMAGE' and n.image and 'BaseColor' in n.image.name]
    src = nodes[0].image; w, h = src.size
    px = np.empty(w*h*4, dtype=np.float32); src.pixels.foreach_get(px); px = px.reshape(h, w, 4)
    u0, u1, v0, v1 = p7['print_box_uv']; c0, c1, r0, r1 = int(u0*w), int(u1*w), int(v0*h), int(v1*h)
    shift = int(p7['patch_shift_u']*w); feather = max(4, int(p7['feather_u']*w))
    yy = np.arange(r1-r0)[:, None]; xx = np.arange(c1-c0)[None, :]
    edge = np.minimum(np.minimum(yy, r1-r0-1-yy), np.minimum(xx, c1-c0-1-xx))
    a = np.clip(edge/feather, 0, 1); a = (a*a*(3-2*a))[..., None]
    out = px.copy()
    out[r0:r1, c0:c1] = px[r0:r1, c0:c1]*(1-a) + px[r0:r1, c0+shift:c1+shift]*a
    img = bpy.data.images.new('Pin coating, printed marks painted out', w, h, alpha=True)
    img.colorspace_settings.name = src.colorspace_settings.name
    img.pixels.foreach_set(out.ravel()); img.pack()
    for n in nodes: n.image = img
    # Only the appended source material (left on an unused mesh) still points at the marked texture;
    # unlink it so the logo image is not packed into the saved scene.
    bpy.data.images.remove(src, do_unlink=True)
    mesh.name = 'Asset pin, unmarked coating, frozen 38 cm contour'
    return mesh


def _fabric(root, f):
    d = _texture_dir(root, f['asset'])
    mat = material('Woven acoustic fabric masking panel', (.03, .035, .05, 1), .9)
    n, l = mat.node_tree.nodes, mat.node_tree.links; bs = n.get('Principled BSDF')
    tc = n.new('ShaderNodeTexCoord'); sep = n.new('ShaderNodeSeparateXYZ'); l.new(tc.outputs['Object'], sep.inputs['Vector'])
    comb = n.new('ShaderNodeCombineXYZ')
    for axis, socket in [('Y', 'X'), ('Z', 'Y')]:
        div = n.new('ShaderNodeMath'); div.operation = 'DIVIDE'; div.inputs[1].default_value = f['tile_m']
        l.new(sep.outputs[axis], div.inputs[0]); l.new(div.outputs[0], comb.inputs[socket])
    tex = {}
    for key, name in [('diff', 'diff'), ('rough', 'rough'), ('nor', 'nor_gl')]:
        t = n.new('ShaderNodeTexImage'); t.image = _image(d/f"{f['asset']}_{name}_2k.jpg", key != 'diff')
        l.new(comb.outputs['Vector'], t.inputs['Vector']); tex[key] = t
    tint = n.new('ShaderNodeMixRGB'); tint.blend_type = 'MULTIPLY'; tint.inputs[0].default_value = 1
    tint.inputs[2].default_value = tuple(f['tint_linear']) + (1,)
    l.new(tex['diff'].outputs['Color'], tint.inputs[1])
    # Each stretched panel was dyed and has faded a little differently.
    info = n.new('ShaderNodeObjectInfo'); spread = n.new('ShaderNodeMapRange')
    spread.inputs['To Min'].default_value, spread.inputs['To Max'].default_value = f['panel_tone_range']
    l.new(info.outputs['Random'], spread.inputs['Value'])
    tone = n.new('ShaderNodeMixRGB'); tone.blend_type = 'MULTIPLY'; tone.inputs[0].default_value = 1
    l.new(tint.outputs[0], tone.inputs[1]); l.new(spread.outputs['Result'], tone.inputs[2]); l.new(tone.outputs[0], bs.inputs['Base Color'])
    rm = n.new('ShaderNodeMapRange'); rm.inputs['To Min'].default_value, rm.inputs['To Max'].default_value = f['roughness_range']
    l.new(tex['rough'].outputs['Color'], rm.inputs['Value']); l.new(rm.outputs['Result'], bs.inputs['Roughness'])
    nm = n.new('ShaderNodeNormalMap'); nm.inputs['Strength'].default_value = f['normal_strength']
    l.new(tex['nor'].outputs['Color'], nm.inputs['Color']); l.new(nm.outputs['Normal'], bs.inputs['Normal'])
    bs.inputs['Sheen Weight'].default_value = f['sheen']; bs.inputs['Sheen Roughness'].default_value = .5
    return mat


def _scuffed(mat, root, s, spec):
    """Replace the procedural roughness of a venue finish with a scanned scuff/scratch map at true scale."""
    d = _texture_dir(root, s['asset']); n, l = mat.node_tree.nodes, mat.node_tree.links; bs = n.get('Principled BSDF')
    for link in [k for k in l if k.to_socket in (bs.inputs['Roughness'], bs.inputs['Normal'])]: l.remove(link)
    tc = n.new('ShaderNodeTexCoord'); mp = n.new('ShaderNodeMapping')
    sx, sy, sz = spec.get('stretch_xyz', [1, 1, 1])
    mp.inputs['Scale'].default_value = (1/(s['tile_m']*sx), 1/(s['tile_m']*sy), 1/(s['tile_m']*sz))
    mp.inputs['Location'].default_value = tuple(spec.get('offset_xyz', [0, 0, 0]))
    l.new(tc.outputs['Object'], mp.inputs['Vector'])
    rough = n.new('ShaderNodeTexImage'); rough.image = _image(d/f"{s['asset']}_rough_2k.jpg", True)
    nor = n.new('ShaderNodeTexImage'); nor.image = _image(d/f"{s['asset']}_nor_gl_2k.jpg", True)
    for t in (rough, nor): t.projection = 'BOX'; t.projection_blend = .3; l.new(mp.outputs['Vector'], t.inputs['Vector'])
    rm = n.new('ShaderNodeMapRange'); rm.inputs['To Min'].default_value, rm.inputs['To Max'].default_value = spec['roughness_range']
    l.new(rough.outputs['Color'], rm.inputs['Value']); l.new(rm.outputs['Result'], bs.inputs['Roughness'])
    nm = n.new('ShaderNodeNormalMap'); nm.inputs['Strength'].default_value = spec['normal_strength']
    l.new(nor.outputs['Color'], nm.inputs['Color']); l.new(nm.outputs['Normal'], bs.inputs['Normal'])
    if 'coat_weight' in spec: bs.inputs['Coat Weight'].default_value = spec['coat_weight']; bs.inputs['Coat Roughness'].default_value = spec['coat_roughness']


def _board_tones(factors, tint):
    """Board-to-board tone spread of a real maple lane (the venue layer flattens it to about 4 %)."""
    for mat in bpy.data.materials:
        if not mat.name.startswith('Maple board natural shade'): continue
        k = int(mat.name.split('shade ')[1].split('.')[0])
        node = mat.node_tree.nodes.get('Amber polyurethane finish')
        node.inputs[2].default_value = tuple(min(1., c*factors[k]) for c in tint) + (1,)


def _lane_coat(c):
    """Fuller, smoother lane top coat; the conditioner streak amplitude in the coat is reduced."""
    for mat in bpy.data.materials:
        if not mat.name.startswith('Maple board natural shade'): continue
        bs = mat.node_tree.nodes.get('Principled BSDF'); bs.inputs['Coat Weight'].default_value = c['weight']
        link = next(k for k in mat.node_tree.links if k.to_socket == bs.inputs['Coat Roughness'])
        node = link.from_node; node.inputs[1].default_value = c['streak']; node.inputs[2].default_value = c['roughness']


def architecture(cfg, root):
    ledger = architecture_venue(cfg, root); finish_cfg = cfg['appearance']['photographic_finish']
    # 1. No text: delete the lane numerals and their font.
    for ob in [o for o in bpy.data.objects if o.name.startswith('Lane number')]:
        data = ob.data; bpy.data.objects.remove(ob, do_unlink=True); bpy.data.curves.remove(data)
    for font in list(bpy.data.fonts):
        if not font.users: bpy.data.fonts.remove(font)
    # 2. Masking unit: woven acoustic fabric, aluminium bottom nosing.
    fabric = _fabric(root, finish_cfg['masking_fabric']); alu = bpy.data.materials['Anodised aluminium nosing']
    for ob in bpy.data.objects:
        if ob.name.startswith(('Masking unit printed panel', 'Masking unit fascia')): ob.data.materials[0] = fabric
        elif ob.name.startswith('Masking LED edge strip'): ob.data.materials[0] = alu; ob.name = 'Masking unit aluminium nosing'
    for name in ['Printed masking unit vinyl panel', 'Printed masking unit vinyl', 'Illuminated lane numerals', 'Masking LED edge strip']:
        if name in bpy.data.materials and not bpy.data.materials[name].users: bpy.data.materials.remove(bpy.data.materials[name])
    if 'Masking unit print' in bpy.data.images and not bpy.data.images['Masking unit print'].users:
        bpy.data.images.remove(bpy.data.images['Masking unit print'])
    # 3. Scanned scuffs on the dark lane furniture.
    s = finish_cfg['scuff_maps']
    for mat_name, key in [('Used charcoal gutter resin', 'gutter'), ('Satin lane capping', 'capping'),
                          ('Charcoal kickback laminate', 'kickback'), ('Black satin steel kick plate', 'strike_plate')]:
        _scuffed(bpy.data.materials[mat_name], root, s, s[key])
    # 4. Lane top coat.
    _lane_coat(finish_cfg['lane_coat']); _board_tones(finish_cfg['board_tone_factors'], cfg['appearance']['venue']['wood_tint'])
    ledger[0].update({'revision': 'venue_photographic_finish', 'text_and_marks': 'none (lane numerals removed, pin maker marks painted out)',
        'masking_finish': 'Poly Haven poly_wool_herringbone, CC0, 27 cm weave repeat',
        'scuff_maps': 'Poly Haven blue_metal_plate roughness and normal, CC0, 2.5 m repeat'})
    return ledger


def _fixture(name, loc, target, size, depth, power, color, housing, lens_strength):
    """Area emitter at the lit lens of a real housing; the housing sits behind the emitting face."""
    d = bpy.data.lights.new(name, 'AREA'); d.shape = 'RECTANGLE'; d.size, d.size_y = size; d.energy = power; d.color = color
    light = bpy.data.objects.new(name, d); bpy.context.collection.objects.link(light); light.location = loc; look_at(light, target)
    rot = light.rotation_euler.to_matrix(); back = rot @ Vector((0, 0, 1))
    h = box(name+' housing', Vector(loc)+back*(depth/2+.003), (size[0]+.03, size[1]+.03, depth), housing, .004); h.rotation_euler = light.rotation_euler
    lens = box(name+' lit lens', Vector(loc)+back*.0015, (size[0], size[1], .002),
               emissive(name+' lens', tuple(color)+(1,), lens_strength), 0)
    lens.rotation_euler = light.rotation_euler; lens.visible_shadow = False
    return light


def _spot_fixture(name, loc, target, f, color, housing):
    """Ceiling can spot: the emitter sits at the lit lens in the mouth of a cylindrical can."""
    d = bpy.data.lights.new(name, 'SPOT'); d.energy = f['power_W']; d.color = color
    d.spot_size = math.radians(f['cone_deg']); d.spot_blend = f['blend']; d.shadow_soft_size = f['lens_radius_m']
    light = bpy.data.objects.new(name, d); bpy.context.collection.objects.link(light); light.location = loc; look_at(light, target)
    back = light.rotation_euler.to_matrix() @ Vector((0, 0, 1)); r = f['lens_radius_m']
    cylinder_between(name+' can', Vector(loc)+back*.004, Vector(loc)+back*.16, r+.02, housing, 32)
    lens = cylinder_between(name+' lit lens', Vector(loc)+back*.001, Vector(loc)+back*.003, r,
                            emissive(name+' lens', tuple(color)+(1,), f['lens_strength']), 32)
    lens.visible_shadow = False
    cylinder_between(name+' ceiling stem', Vector(loc)+back*.09, (loc[0], loc[1], 3.46), .012, housing, 12)
    return light


def lighting(cfg):
    app = cfg['appearance']; venue = app['venue']; L = app['lighting']; F = app['photographic_finish']['fixtures']
    s = bpy.context.scene; s.world = bpy.data.worlds.new('Enclosed hall, no fill'); s.world.use_nodes = True
    bg = s.world.node_tree.nodes.get('Background'); bg.inputs['Color'].default_value = (.63, .70, .85, 1)
    bg.inputs['Strength'].default_value = app['world_strength']

    def area(name, loc, power, sx, sy, color, target=None):
        d = bpy.data.lights.new(name, 'AREA'); d.shape = 'RECTANGLE'; d.energy = power; d.size = sx; d.size_y = sy; d.color = color
        o = bpy.data.objects.new(name, d); bpy.context.collection.objects.link(o); o.location = loc
        if target: look_at(o, target)
        return o
    housing = bpy.data.materials['Black phosphate and powder-coated machine steel']
    glow = emissive('Neutral white fluorescent diffuser', (1, .95, .86, 1), 1.6)
    trim = material('Ceiling light extruded housing', (.07, .075, .08, 1), .45, .4)
    lens_finish(s, venue)
    for x in L['overhead_rows_x_m']:
        for pair in [-1.5, .5, 2.5]:
            y = pair*PITCH
            box('Linear light housing', (x, y, 3.40), (.17, 2.65, .065), trim, .006)
            box('Linear opal light diffuser', (x, y, 3.36), (.125, 2.54, .010), glow, .002)
            area('4000K overhead lane fixture', (x, y, 3.35), L['overhead_power_W'], .125, 2.54, (1., .95, .86))
            for dy in [-1.1, 1.1]: box('Fixture suspension rod', (x, y+dy, 3.445), (.006, .006, .03), trim)
    for lane in LANES:
        off = lane*PITCH
        # Pin lights sit in the masking light shelf behind their diffuser and rake back across the deck;
        # the emitter's long side runs across the lane, matching its 1.30 m diffuser.
        area('Pin deck light', (MASK_FRONT_X+.13, off, MASK_BOTTOM_Z-.03), L['pin_light_W'], 1.30, .09, (1., .97, .93), (.45, off, 0.))
        f = F['lane_end']
        _fixture('Lane-end light bar', (MASK_FRONT_X+f['dx_m'], off, MASK_BOTTOM_Z+f['dz_m']), (-1.8, off, 0.), (1.25, f['lens_height_m']), .04,
                 L['lane_end_W'], (1., .96, .90), housing, f['lens_strength'])
        for dy in [-.5, .5]:
            box('Lane-end light bar bracket', (MASK_FRONT_X+f['dx_m']/2+.002, off+dy, MASK_BOTTOM_Z+.004), (abs(f['dx_m'])+.004, .02, .024), housing, .001)
        f = F['masking_wash']
        _spot_fixture('Ceiling masking wash spot', (MASK_FRONT_X-1.6, off, f['z_m']), (MASK_FRONT_X, off, f['aim_z_m']), f, (.92, .94, 1.), housing)
        f = F['pit_service']
        _fixture('Pinsetter pit service lamp', (1.6, off, f['z_m']), (2.6, off, -.1), (.5, .12), .05,
                 L['pit_service_W'], (.92, .95, 1.), housing, f['lens_strength'])
