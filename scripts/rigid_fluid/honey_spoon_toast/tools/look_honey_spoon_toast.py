"""Prepare a grounded breakfast-table appearance around the frozen honey cache.

Run inside Blender. This changes render geometry/materials/lights only. The
spoon bowl, rig, honey coordinates, simulation and reconstructed surfaces are
not changed. The bread's landing patch remains at the solver's z=0.797 m.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector


def arguments():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-blend', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--asset-root', type=Path, required=True)
    return p.parse_args(argv)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluated_bounds(objects):
    deps = bpy.context.evaluated_depsgraph_get()
    pts = [o.matrix_world @ Vector(p) for obj in objects if obj.type == 'MESH'
           for o in [obj.evaluated_get(deps)] for p in o.bound_box]
    return Vector(tuple(min(p[i] for p in pts) for i in range(3))), Vector(tuple(max(p[i] for p in pts) for i in range(3)))


def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def mat(name, color, roughness=.5, metallic=0.):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    return material, bsdf


def cube(name, center, size, material, bevel=0.):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = obj.modifiers.new('Manufactured edge radius', 'BEVEL')
        mod.width, mod.segments = bevel, 4
    assign(obj, material)
    return obj


def append_objects(path, predicate=lambda obj: True):
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.objects = list(src.objects)
    objects = []
    for obj in dst.objects:
        if not obj:
            continue
        if predicate(obj):
            bpy.context.scene.collection.objects.link(obj)
            objects.append(obj)
        else:
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.context.view_layer.update()
    return objects


def world_mesh(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(deps), preserve_all_data_layers=True, depsgraph=deps)
    mesh.transform(obj.matrix_world)
    obj.parent = None
    obj.matrix_world = Matrix.Identity(4)
    obj.modifiers.clear()
    obj.data = mesh


def mesh_signature(names):
    record = {}
    for name in names:
        obj = bpy.data.objects[name]
        record[name] = {'matrix': [list(row) for row in obj.matrix_world],
            'vertices': [list(v.co) for v in obj.data.vertices] if obj.type == 'MESH' else None,
            'faces': [list(p.vertices) for p in obj.data.polygons] if obj.type == 'MESH' else None}
    return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()


def toast(asset, landing_z):
    objects = append_objects(asset, lambda obj: obj.type == 'MESH')
    for obj in objects:
        # This asset's geometry-node modifier stacks slices. Keep its one-slice
        # base mesh and the authored subdivision/UVs/material attributes.
        for modifier in list(obj.modifiers):
            if modifier.type == 'NODES':
                obj.modifiers.remove(modifier)
        world_mesh(obj)
        obj.name = 'PCVE_ToastTextured'
    lo, hi = evaluated_bounds(objects)
    source_bounds = [list(lo), list(hi)]
    size = hi - lo
    center = (lo + hi) * .5
    target_size = Vector((.130, .105, .022))
    for obj in objects:
        for vertex in obj.data.vertices:
            q = vertex.co - center
            vertex.co = Vector((.095 + q.x * target_size.x / size.x,
                                q.y * target_size.y / size.y,
                                landing_z - target_size.z * .5 + q.z * target_size.z / size.z))
        obj.data.update()
    # The contact mesh is a flat toast surface. Keep a smooth 13-mm-radius
    # landing patch at exactly that surface so cached honey never floats above
    # a deeply displaced photographic crumb or sinks into it.
    for obj in objects:
        for vertex in obj.data.vertices:
            if vertex.co.z < landing_z - .010:
                continue
            radius = math.hypot(vertex.co.x - .09767, vertex.co.y)
            weight = max(0., min(1., (.018 - radius) / .005))
            weight = weight * weight * (3. - 2. * weight)
            vertex.co.z = (1. - weight) * vertex.co.z + weight * landing_z
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        obj.data.update()
    bpy.context.view_layer.update()
    lo, hi = evaluated_bounds(objects)
    return objects, {'asset': str(asset), 'source_bounds_m': source_bounds,
        'world_bounds_m': [list(lo), list(hi)], 'landing_surface_m': landing_z,
        'landing_patch_center_m': [.09767, 0], 'landing_patch_flat_radius_m': .013}


def plate_profile(center, top, material):
    # Breakfast plate with a real underside, foot ring, flat well and rolled lip.
    profile = [(0,top),(.070,top),(.082,top),(.089,top+.001),(.101,top+.005),
        (.112,top+.008),(.118,top+.0085),(.120,top+.007),(.118,top+.005),
        (.108,top+.002),(.092,top-.002),(.060,top-.0035),(.052,top-.004),
        (.049,top-.006),(.048,top-.0167),(.043,top-.0167),(.042,top-.005),
        (.037,top-.0045),(0,top-.0045)]
    vertices, faces, rings = [], [], []
    for radius, height in profile:
        ring = []
        if radius == 0:
            ring.append(len(vertices)); vertices.append((center[0],center[1],height))
        else:
            for j in range(192):
                a = 2*math.pi*j/192
                ring.append(len(vertices)); vertices.append((center[0]+radius*math.cos(a), center[1]+radius*math.sin(a),height))
        rings.append(ring)
    for a,b in zip(rings,rings[1:]):
        for j in range(192):
            k=(j+1)%192
            faces.append((a[0],b[j],b[k]) if len(a)==1 else
                         (a[j],b[0],a[k]) if len(b)==1 else (a[j],b[j],b[k],a[k]))
    mesh=bpy.data.meshes.new('BreakfastPlateMesh');mesh.from_pydata(vertices,[],faces);mesh.update()
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
    obj=bpy.data.objects.new('PCVE_Plate',mesh);bpy.context.collection.objects.link(obj);assign(obj,material)
    for p in mesh.polygons:p.use_smooth=True
    sub=obj.modifiers.new('Soft ceramic profile','SUBSURF');sub.levels=2;sub.render_levels=2
    return obj


def wood_material(asset):
    images={key:bpy.data.images.load(str(asset/f'wood_table_{suffix}_4k.jpg'),check_existing=True)
            for key,suffix in [('diffuse','diff'),('roughness','rough'),('normal','nor_gl')]}
    material,bsdf=mat('PCVE_VarnishedPine',(.28,.14,.06),.47)
    nodes,links=material.node_tree.nodes,material.node_tree.links
    coords=nodes.new('ShaderNodeTexCoord');scale=nodes.new('ShaderNodeVectorMath');scale.operation='MULTIPLY'
    scale.inputs[1].default_value=(2.0,1.4,.04);links.new(coords.outputs['Generated'],scale.inputs[0])
    for key,output in [('diffuse','Base Color'),('roughness','Roughness'),('normal',None)]:
        image=images[key]
        tex=nodes.new('ShaderNodeTexImage');tex.image=image;tex.projection='BOX';tex.projection_blend=.15
        links.new(scale.outputs['Vector'],tex.inputs['Vector'])
        if key=='diffuse':
            adjust=nodes.new('ShaderNodeHueSaturation');adjust.inputs['Saturation'].default_value=.78
            adjust.inputs['Value'].default_value=.75;links.new(tex.outputs['Color'],adjust.inputs['Color'])
            links.new(adjust.outputs['Color'],bsdf.inputs[output])
        elif key=='normal':
            image.colorspace_settings.name='Non-Color'
            normal=nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.28
            links.new(tex.outputs['Color'],normal.inputs['Color']);links.new(normal.outputs['Normal'],bsdf.inputs['Normal'])
        else:
            image.colorspace_settings.name='Non-Color';links.new(tex.outputs['Color'],bsdf.inputs[output])
    bsdf.inputs['Coat Weight'].default_value=.06
    return material


def linen_material():
    material,bsdf=mat('PCVE_WovenLinen',(.53,.57,.47),.88)
    bsdf.inputs['Sheen Weight'].default_value=.25
    nodes,links=material.node_tree.nodes,material.node_tree.links
    coords=nodes.new('ShaderNodeTexCoord')
    waves=[]
    for direction in ['X','Y']:
        wave=nodes.new('ShaderNodeTexWave');wave.bands_direction=direction
        wave.inputs['Scale'].default_value=210.;wave.inputs['Distortion'].default_value=.18
        links.new(coords.outputs['UV'],wave.inputs['Vector']);waves.append(wave)
    multiply=nodes.new('ShaderNodeMath');multiply.operation='MULTIPLY'
    for i,wave in enumerate(waves):links.new(wave.outputs['Fac'],multiply.inputs[i])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.22;bump.inputs['Distance'].default_value=.00012
    links.new(multiply.outputs[0],bump.inputs['Height']);links.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
    ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.12,.18,.11,1);ramp.color_ramp.elements[1].color=(.32,.39,.27,1)
    links.new(multiply.outputs[0],ramp.inputs[0]);links.new(ramp.outputs['Color'],bsdf.inputs['Base Color'])
    return material


def napkin(table_z):
    vertices,faces=[],[];nx,ny=100,70
    for j in range(ny+1):
        for i in range(nx+1):
            u,v=i/nx,j/ny;x=(u-.5)*.190;y=(v-.5)*.135
            z=.0013+.00065*math.sin(5.0*math.pi*u+.8*math.sin(3*v))*math.sin(math.pi*v)+.0004*math.cos(4*math.pi*v+u)
            z+=.0045*math.exp(-((u-.18)/.11)**2)*math.sin(math.pi*v)
            z+=.0025*math.exp(-((v-.8)/.10)**2)*math.sin(math.pi*u)
            ca,sa=math.cos(-.18),math.sin(-.18)
            vertices.append((-.17+ca*x-sa*y,-.055+sa*x+ca*y,table_z+z))
    for j in range(ny):
        for i in range(nx):
            a=j*(nx+1)+i;faces.append((a,a+1,a+nx+2,a+nx+1))
    mesh=bpy.data.meshes.new('LinenFoldMesh');mesh.from_pydata(vertices,[],faces);mesh.update()
    uv=mesh.uv_layers.new(name='UVMap')
    for p in mesh.polygons:
        p.use_smooth=True
        for li in p.loop_indices:
            vi=mesh.loops[li].vertex_index;uv.data[li].uv=(vi%(nx+1)/nx,vi//(nx+1)/ny)
    obj=bpy.data.objects.new('PCVE_Napkin',mesh);bpy.context.collection.objects.link(obj);assign(obj,linen_material())
    solid=obj.modifiers.new('Linen thickness','SOLIDIFY');solid.thickness=.0006
    return obj


def coffee(asset,table_z):
    objects=append_objects(asset,lambda obj:obj.name in {'MUG.004','plate.004','Circle.003'})
    for obj in objects:world_mesh(obj)
    lo,hi=evaluated_bounds(objects);scale=.078/(hi.z-lo.z)
    for obj in objects:
        for vertex in obj.data.vertices:
            vertex.co=Vector((-.145+vertex.co.x*scale,.222+vertex.co.y*scale,table_z+(vertex.co.z-lo.z)*scale))
        for p in obj.data.polygons:p.use_smooth=True
        obj.name='PCVE_BackgroundCoffee_'+obj.name;obj.data.update()
    return objects


def point_light(obj,target):
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()


def polish_handle():
    """Render-only handle; the shared collision bowl is never changed."""
    obj=bpy.data.objects['PCVE_SpoonHandle']
    material=obj.data.materials[0]
    sections=[(-.170,.0001,.0003,.0020),(-.168,.0050,.0011,.0020),
        (-.160,.0063,.0013,.0019),(-.143,.0061,.0013,.0017),
        (-.116,.0053,.0012,.0015),(-.085,.0045,.0011,.0012),
        (-.058,.0036,.0010,.0007),(-.044,.0038,.0010,.0005),(-.035,.0050,.0008,.0004)]
    vertices,faces=[],[];sides=24
    for x,width,thickness,z in sections:
        for j in range(sides):
            a=2*math.pi*j/sides;vertices.append((x,width*math.cos(a),z+thickness*math.sin(a)))
    for i in range(len(sections)-1):
        for j in range(sides):
            k=(j+1)%sides;a=i*sides+j;b=i*sides+k
            faces.append((a,b,b+sides,a+sides))
    faces.extend([tuple(reversed(range(sides))),tuple(range((len(sections)-1)*sides,len(sections)*sides))])
    mesh=bpy.data.meshes.new('PolishedSpoonHandleMesh');mesh.from_pydata(vertices,[],faces);mesh.update()
    obj.data=mesh;obj.modifiers.clear();obj.location=(0,0,0);obj.rotation_euler=(0,0,0);obj.scale=(1,1,1)
    assign(obj,material)
    for p in mesh.polygons:p.use_smooth=True
    sub=obj.modifiers.new('Continuous cutlery curvature','SUBSURF');sub.levels=2;sub.render_levels=2


def main():
    args=arguments();source=args.input_blend.resolve();out=args.out.resolve();assets=args.asset_root.resolve()
    if out==source:raise ValueError('Keep the accepted baseline intact; --out must be a new scene')
    bpy.ops.wm.open_mainfile(filepath=str(source));scene=bpy.context.scene
    protected=['PCVE_SpoonRig','PCVE_SpoonBowl','PCVE_Honey']
    before_signature=mesh_signature(protected)
    before={'physics':{'input_scene_sha256':sha256(source),'spoon_honey_geometry_sha256':before_signature},
            'appearance':{'toast_asset':'procedural prisms','toast_bottom_m':.775,'plate_top_m':.762,
                          'camera_matrix':[list(row) for row in scene.camera.matrix_world],'camera_lens_mm':scene.camera.data.lens},
            'render':{'width':1280,'height':720,'fps':24,'frames':96,'samples':32}}
    for name in ['PCVE_ToastCrust','PCVE_ToastCrumbTop','PCVE_Plate','PCVE_Table','PCVE_Napkin','PCVE_BackWall']:
        obj=bpy.data.objects.get(name)
        if obj:bpy.data.objects.remove(obj,do_unlink=True)
    bread,bread_record=toast(assets/'blenderkit/toasted_bread/toasted_bread.blend',.797)
    bread_lo,_=evaluated_bounds(bread)
    plate_top=bread_lo.z
    ceramic,bsdf=mat('PCVE_IvoryPorcelain',(.70,.67,.59),.23)
    bsdf.inputs['Coat Weight'].default_value=.18;bsdf.inputs['Coat Roughness'].default_value=.16
    plate=plate_profile((.095,0),plate_top,ceramic)
    bpy.context.view_layer.update();plate_lo,_=evaluated_bounds([plate]);table_z=plate_lo.z
    tabletop=cube('PCVE_Table',(0,0,table_z-.020),(2.0,1.4,.04),wood_material(assets/'polyhaven/wood_table'),.003)
    napkin(table_z);coffee(assets/'blenderkit/coffee_cup_set/coffee_cup_set.blend',table_z)
    wall,_=mat('PCVE_WarmPlaster',(.57,.53,.46),.9)
    cube('PCVE_BackWall',(0,.65,table_z+.7),(3.,.06,1.4),wall)
    polish_handle()
    key=bpy.data.objects['PCVE_WindowKey'];key.location=(-.43,-.32,1.38);key.data.shape='RECTANGLE'
    key.data.size=.52;key.data.size_y=.80;key.data.energy=50.;key.data.color=(1.,.92,.80);point_light(key,(.04,0,.83))
    fill=bpy.data.objects['PCVE_SoftFill'];fill.location=(.45,.18,1.28);fill.data.energy=5.5;fill.data.size=.8
    fill.data.color=(.79,.87,1.);point_light(fill,(.07,0,.84))
    background=scene.world.node_tree.nodes.get('Background');background.inputs['Color'].default_value=(.54,.60,.66,1)
    background.inputs['Strength'].default_value=.16
    scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=-.35
    # A tighter food-photography frame keeps the spoon's held end outside the
    # image while showing the complete strand, landing point and bread slice.
    scene.camera.data.lens=90.
    scene.camera.rotation_euler=(Vector((.120,0,.843))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.camera.data.dof.aperture_fstop=11.
    scene.render.resolution_x,scene.render.resolution_y=1280,720;scene.render.resolution_percentage=100
    scene.render.fps=24;scene.frame_start=1;scene.frame_end=96
    scene['pcve_appearance']='grounded_breakfast_table'
    assert mesh_signature(protected)==before_signature,'A protected spoon/honey transform or mesh changed'
    after={'physics':before['physics'],'appearance':{'toast':bread_record,'plate_support_m':plate_top,
        'table_support_m':table_z,'bread_plate_gap_m':0.,'plate_table_gap_m':0.,
        'camera_matrix':[list(row) for row in scene.camera.matrix_world],'camera_lens_mm':scene.camera.data.lens,
        'look':'grounded_breakfast_table','light':'large rectangular window, restrained room fill',
        'spoon_handle':'render-only smooth tapered handle; physical bowl unchanged',
        'plate_surface':'plain ceramic plate'},'render':before['render']}
    out.parent.mkdir(parents=True,exist_ok=True)
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    record={'scope':'appearance only; cached dynamics and surfaces are read-only',
        'input_scene':str(source),'output_scene':str(out),'before':before,'after':after,
        'assets':[json.loads((assets/'blenderkit'/name/'asset_manifest.json').read_text()) for name in ['toasted_bread','coffee_cup_set']]+[json.loads((assets/'polyhaven/wood_table/asset_manifest.json').read_text())],
        'physical_model_limitation':'The cached landing surface remains flat and non-porous; toast pores are visual detail, without absorption or new fluid coupling.'}
    (out.parent/'appearance_manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    print('GROUNDED_SCENE_READY',str(out),json.dumps({'toast_bottom':plate_top,'plate_table_contact':table_z,'protected_geometry_unchanged':True}),flush=True)


if __name__=='__main__':main()
