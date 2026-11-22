"""Common photographic entryway room; it does not change any native actor geometry."""
import math
import bpy,numpy as np
from mathutils import Vector,Matrix
from common import INPUTS,sha
from render import material,box,area


def noise_material(name,color,roughness=.6,scale=180.,distance=.000015):
    m=material(name,color,roughness);n=m.node_tree.nodes;l=m.node_tree.links;p=n.get('Principled BSDF')
    tc=n.new('ShaderNodeTexCoord');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=scale;noise.inputs['Detail'].default_value=3.;l.new(tc.outputs['Object'],noise.inputs['Vector'])
    bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=distance;bump.inputs['Strength'].default_value=.22;l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],p.inputs['Normal']);return m


def foam(name,color):
    m=material(name,color,.57);n=m.node_tree.nodes;l=m.node_tree.links;p=n.get('Principled BSDF');p.inputs['IOR'].default_value=1.46
    if 'Diffuse Roughness' in p.inputs:p.inputs['Diffuse Roughness'].default_value=.2
    attr=n.new('ShaderNodeAttribute');attr.attribute_name='eva_rest'
    broad=n.new('ShaderNodeTexNoise');broad.inputs['Scale'].default_value=180.;broad.inputs['Detail'].default_value=3.;l.new(attr.outputs['Vector'],broad.inputs['Vector'])
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=.18;ramp.color_ramp.elements[0].color=(*[v*.85 for v in color],1);ramp.color_ramp.elements[1].position=.85;ramp.color_ramp.elements[1].color=(*[v*1.06 for v in color],1);l.new(broad.outputs['Fac'],ramp.inputs[0]);l.new(ramp.outputs['Color'],p.inputs['Base Color'])
    pores=n.new('ShaderNodeTexVoronoi');pores.inputs['Scale'].default_value=2900.;pores.distance='EUCLIDEAN';l.new(attr.outputs['Vector'],pores.inputs['Vector'])
    pit=n.new('ShaderNodeMapRange');pit.inputs['From Min'].default_value=.10;pit.inputs['From Max'].default_value=.32;pit.inputs['To Min'].default_value=0.;pit.inputs['To Max'].default_value=1.;pit.clamp=True;l.new(pores.outputs['Distance'],pit.inputs['Value'])
    bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000035;bump.inputs['Strength'].default_value=.28;l.new(pit.outputs['Result'],bump.inputs['Height']);l.new(bump.outputs['Normal'],p.inputs['Normal'])
    rough=n.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.49;rough.inputs['To Max'].default_value=.64;l.new(broad.outputs['Fac'],rough.inputs['Value']);l.new(rough.outputs['Result'],p.inputs['Roughness'])
    m['physical_detail']='Rest-space submillimetre pores; shader bump only, zero geometry displacement';return m


def oak():
    folder=INPUTS/'assets/room_dressing/white_oak_veneer';m=material('Photographed white oak | 0.5m scan',(.3,.2,.1),.55);m['pcve_metric_uv']=True;n=m.node_tree.nodes;l=m.node_tree.links;p=n.get('Principled BSDF');tc=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeVectorMath');mapping.operation='SCALE';mapping.inputs[3].default_value=2.;l.new(tc.outputs['UV'],mapping.inputs[0])
    for kind,target in [('diff','Base Color'),('rough','Roughness'),('nor_gl',None)]:
        t=n.new('ShaderNodeTexImage');t.image=bpy.data.images.load(str(folder/f'white_oak_veneer_{kind}_4k.jpg'),check_existing=True);l.new(mapping.outputs[0],t.inputs['Vector'])
        if kind!='diff':t.image.colorspace_settings.name='Non-Color'
        if target:l.new(t.outputs['Color'],p.inputs[target])
        else:
            normal=n.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.3;l.new(t.outputs['Color'],normal.inputs['Color']);l.new(normal.outputs[0],p.inputs['Normal'])
    return m


def metric_uv(o):
    layer=o.data.uv_layers.active or o.data.uv_layers.new(name='Metric furniture UV')
    world=np.asarray(o.matrix_world)
    for poly in o.data.polygons:
        axis=int(np.argmax(np.abs(poly.normal)));axes=[j for j in range(3) if j!=axis]
        for loop in poly.loop_indices:
            p=o.data.vertices[o.data.loops[loop].vertex_index].co
            layer.data[loop].uv=(p[axes[0]],p[axes[1]])


def import_prop(asset,xy,target_height,angle=0.,bottom=0.,keep_meshes=None,floor_anchor=None):
    before=set(bpy.context.scene.objects);bpy.ops.import_scene.gltf(filepath=str(INPUTS/'assets/room_dressing'/asset/(asset+'_2k.gltf')));objects=sorted(set(bpy.context.scene.objects)-before,key=lambda o:o.name);bpy.context.view_layer.update()
    if keep_meshes:
        for o in list(objects):
            if o.type=='MESH' and o.name not in keep_meshes:objects.remove(o);bpy.data.objects.remove(o,do_unlink=True)
    meshes=[o for o in objects if o.type=='MESH'];points=np.array([tuple(o.matrix_world@Vector(c)) for o in meshes for c in o.bound_box]);lo=points.min(0);hi=points.max(0);factor=target_height/(hi[2]-lo[2]);parent=bpy.data.objects.new('CC0 scan | '+asset,None);bpy.context.collection.objects.link(parent)
    anchor_z=lo[2]
    if floor_anchor:
        anchor=next(o for o in meshes if o.name==floor_anchor);anchor_z=min((anchor.matrix_world@Vector(c)).z for c in anchor.bound_box)
    for o in objects:
        o.name='CC0 '+asset+' | '+o.name
        if o.parent not in objects:
            world=o.matrix_world.copy();o.parent=parent;o.matrix_world=world
        if o.type=='MESH':o['pcve_decorative']=True
    parent.matrix_world=Matrix.Translation(Vector((xy[0],xy[1],bottom)))@Matrix.Rotation(math.radians(angle),4,'Z')@Matrix.Scale(factor,4)@Matrix.Translation(Vector((-(lo[0]+hi[0])/2,-(lo[1]+hi[1])/2,-anchor_z)))
    bpy.context.view_layer.update();return parent


def mat_weave():
    m=material('Natural coir woven doormat',(.17,.105,.05),.96);n=m.node_tree.nodes;l=m.node_tree.links;p=n.get('Principled BSDF');tc=n.new('ShaderNodeTexCoord');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=180.;noise.inputs['Roughness'].default_value=.8;l.new(tc.outputs['Object'],noise.inputs['Vector']);r=n.new('ShaderNodeValToRGB');r.color_ramp.elements[0].color=(.065,.031,.009,1);r.color_ramp.elements[1].color=(.26,.16,.06,1);l.new(noise.outputs[0],r.inputs[0]);l.new(r.outputs[0],p.inputs['Base Color']);b=n.new('ShaderNodeBump');b.inputs['Distance'].default_value=.0012;b.inputs['Strength'].default_value=.8;l.new(noise.outputs[0],b.inputs['Height']);l.new(b.outputs[0],p.inputs['Normal']);return m


def apply(scene,spec):
    actors=[o for o in scene.objects if 'part_id' in o]
    colors=[(.075,.115,.135),(.055,.080,.091)];mats=[foam('Moulded EVA | '+str(i),c) for i,c in enumerate(colors)]
    for o in actors:
        o.data.materials.clear()
        for m in mats:o.data.materials.append(m)
    wood=oak();paint=noise_material('Warm off-white eggshell cabinet',(.55,.52,.46),.63,210.,.000012);doorpaint=noise_material('Sage grey enamel door',(.14,.17,.155),.43,320.,.000008);charcoal=material('Powder-coated black hardware',(.025,.03,.029),.4)
    scene.objects['Front door'].data.materials.clear();scene.objects['Front door'].data.materials.append(doorpaint);scene.objects['Front door'].location.z+=.012
    scene.objects['Door handle mounting plate'].location.y=1.648
    hardware=scene.objects['Lever handle'].data.materials[0]
    bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=.009,depth=.05,location=(-.41,1.624,.96),rotation=(math.pi/2,0,0));stem=bpy.context.object;stem.name='Lever spindle attached to mounting plate';stem.data.materials.append(hardware)
    for poly in stem.data.polygons:poly.use_smooth=True
    for o in scene.objects:
        if o.name.startswith('Entryway bench | ') and o.type=='MESH':
            # Keep original scan/artist UVs; neutralize the exaggerated dark stain.
            for mat in o.data.materials:
                if mat and mat.use_nodes:
                    for p in mat.node_tree.nodes:
                        if p.type=='BSDF_PRINCIPLED' and not p.inputs['Roughness'].is_linked:p.inputs['Roughness'].default_value=.46
    # Small real construction details at the door; all well outside actor motion.
    box('Door lower weather seal',(-.76,1.644,.018),(.80,.014,.012),charcoal,.003)
    brushed=material('Brushed threshold aluminium',(.31,.32,.30),.38);brushed.node_tree.nodes.get('Principled BSDF').inputs['Metallic'].default_value=.85
    box('Door threshold strip',(-.76,1.675,.004),(.91,.14,.008),brushed,.002)
    for x in [-1.19,-.33]:box('Jamb recessed shadow line',(x,1.637,1.05),(.005,.006,2.07),charcoal,.001)
    # A compact shoe cupboard at the door side, physically scaled joinery.
    box('Shoe cabinet oak carcass',(-1.56,1.43,.57),(.55,.38,1.04),wood,.004)
    box('Cabinet recessed plinth',(-1.56,1.47,.035),(.47,.25,.07),charcoal,.002)
    for z in [.33,.84]:
        box('Flush shoe cupboard front',(-1.56,1.231,z),(.537,.025,.495),paint,.002)
        box('Cabinet slim pull',(-1.56,1.211,z+.16),(.14,.013,.009),charcoal,.003)
        for x in [-1.61,-1.51]:box('Cabinet pull attachment',(x,1.218,z+.16),(.008,.012,.007),charcoal,.002)
    box('Cabinet oak top edge',(-1.56,1.43,1.106),(.57,.4,.025),wood,.003)
    coir=mat_weave();box('Woven front-door mat backing',(-.76,1.31,.004),(.72,.44,.008),charcoal,.014)
    box('Coir door mat',(-.76,1.31,.010),(.705,.425,.012),coir,.011)
    # Scanned everyday props give material detail at the room's real scale.
    import_prop('wicker_basket_01',(.18,1.01),.105,angle=8.,bottom=.058)
    import_prop('rubber_boots',(.88,1.06),.28,angle=-14.,bottom=.0005,keep_meshes={'rubber_boots_dirty_l','rubber_boots_dirt_r'})
    import_prop('potted_plant_01',(.63,1.49),.58,angle=22.,bottom=.0003,floor_anchor='potted_plant_01_pot')
    # Light comes from one large side window, with restrained room bounce.
    for o in list(scene.objects):
        if o.type=='LIGHT':bpy.data.objects.remove(o,do_unlink=True)
    scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.075
    area('Overcast daylight through side window',(-1.35,-.35,1.75),220.,1.05,(0,.15,.05),(1.,.94,.84))
    area('Cool diffuse room bounce',(1.3,-.1,1.75),18.,1.6,(0,.2,.08),(.87,.94,1.))
    wall=scene.objects['Entryway wall'].data.materials[0]
    box('Room side wall',(1.75,.3,1.2),(.08,3.1,2.4),wall)
    box('Ceiling bounce',(0,.5,2.44),(3.6,3.4,.08),wall)
    scene.view_settings.exposure=-.05;scene.view_settings.look='AgX - Medium High Contrast';scene.cycles.max_bounces=10
    # Slightly wider camera reveals the bench and door-side details.
    camera=scene.camera;camera.location=spec['camera_m'];camera.rotation_euler=(Vector(spec['target_m'])-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.lens=spec['lens_mm'];camera.data.dof.aperture_fstop=9.
    floor=scene.objects['Continuous receiving floor'].data.materials[0];p=floor.node_tree.nodes.get('Principled BSDF')
    for n in floor.node_tree.nodes:
        if n.type=='NORMAL_MAP':n.inputs['Strength'].default_value=.22
    # Keep contact plane unchanged; only optical finish changes.
    if p.inputs['Roughness'].is_linked:
        socket=p.inputs['Roughness'].links[0].from_socket;r=floor.node_tree.nodes.new('ShaderNodeMapRange');r.inputs['To Min'].default_value=.32;r.inputs['To Max'].default_value=.58;floor.node_tree.links.new(socket,r.inputs['Value']);floor.node_tree.links.new(r.outputs[0],p.inputs['Roughness'])
    bpy.context.view_layer.update()
    decorations=[]
    for o in scene.objects:
        if o.type!='MESH' or 'part_id' in o or o.name in ['Continuous receiving floor','Added fixed rubber doorstop']:continue
        corners=np.array([tuple(o.matrix_world@Vector(c)) for c in o.bound_box]);decorations.append(dict(name=o.name,bounds_m=[corners.min(0).tolist(),corners.max(0).tolist()]))
    return dict(camera_location=list(camera.location),camera_rotation=list(camera.rotation_euler),lens_mm=camera.data.lens,decorative_bounds=decorations,hero_material='Shared moulded-EVA optical finish; unchanged physical parameters and exact native boundary',asset_manifest_sha256=sha(INPUTS/'assets/room_dressing/asset_manifest.json'))
