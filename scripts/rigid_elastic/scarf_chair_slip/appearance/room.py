"""A closed, textured domestic room with a real curtain asset over the window."""
import math
import bpy,numpy as np
from mathutils import Vector,Matrix
from common import ASSETS

def metric_uv(ob):
    if ob.type!='MESH':return
    layer=ob.data.uv_layers.active or ob.data.uv_layers.new(name='Room metric UV')
    for face in ob.data.polygons:
        normal=ob.matrix_world.to_3x3()@face.normal;axis=int(np.argmax(np.abs(normal)))
        for li in face.loop_indices:
            v=ob.matrix_world@ob.data.vertices[ob.data.loops[li].vertex_index].co
            layer.data[li].uv=(v[1],v[2])if axis==0 else((v[0],v[2])if axis==1 else(v[0],v[1]))

def painted_wall():
    with bpy.data.libraries.load(str(ASSETS/'painted_plaster/asset.blend'),link=False)as(src,dst):dst.materials=src.materials
    m=next(m for m in dst.materials if m and m.use_nodes).copy();m.name='Scanned painted plaster / subtle lived-in finish'
    n=m.node_tree.nodes;l=m.node_tree.links
    for output in [x for x in n if x.type=='OUTPUT_MATERIAL']:
        for link in list(output.inputs['Displacement'].links):l.remove(link)
    for bs in [x for x in n if x.type=='BSDF_PRINCIPLED']:
        bs.inputs['Metallic'].default_value=0.;bs.inputs['Coat Weight'].default_value=0.
        if bs.inputs['Base Color'].is_linked:
            link=bs.inputs['Base Color'].links[0];source=link.from_socket;l.remove(link)
            paint=n.new('ShaderNodeMixRGB');paint.blend_type='MIX';paint.inputs[0].default_value=.85;paint.inputs[2].default_value=(.64,.62,.56,1.)
            l.new(source,paint.inputs[1]);l.new(paint.outputs[0],bs.inputs['Base Color'])
        for link in list(bs.inputs['Roughness'].links):
            source=link.from_socket;l.remove(link);rough=n.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.78;rough.inputs['To Max'].default_value=.95
            l.new(source,rough.inputs['Value']);l.new(rough.outputs['Result'],bs.inputs['Roughness'])
        if not bs.inputs['Roughness'].is_linked:bs.inputs['Roughness'].default_value=.88
    def tune(tree,visited):
        if tree.as_pointer()in visited:return
        visited.add(tree.as_pointer())
        for node in tree.nodes:
            if node.type=='NORMAL_MAP':node.inputs['Strength'].default_value=.06
            if node.type=='BUMP':node.inputs['Distance'].default_value=min(node.inputs['Distance'].default_value,.00012)
            if node.type=='GROUP':
                if 'UV Scale'in node.inputs:node.inputs['UV Scale'].default_value=(1.,1.,1.)
                if 'Height Scale'in node.inputs:node.inputs['Height Scale'].default_value=.0001
                tune(node.node_tree,visited)
    tune(m.node_tree,set());return m

def curtains():
    with bpy.data.libraries.load(str(ASSETS/'curtain_linen/asset.blend'),link=False)as(src,dst):dst.objects=src.objects
    objects=[o for o in dst.objects if o]
    for o in objects:
        if o.type in ['MESH','EMPTY']:bpy.context.collection.objects.link(o)
    bpy.context.view_layer.update()
    # The inspected asset has a white sheer and a separate grey curtain.
    # Use one complete linen panel, fitted to the whole opening, with one dye.
    chosen=[o for o in objects if o.type=='MESH'and o.name=='curtain'and not o.hide_render]
    if len(chosen)!=1:raise RuntimeError('Expected the inspected single curtain panel')
    points=np.concatenate([np.asarray([(o.matrix_world@Vector(p))[:]for p in o.bound_box])for o in chosen]);lo=points.min(0);hi=points.max(0);span=hi-lo
    width=int(np.argmax(span[:2]));depth=1-width;middle=(lo+hi)/2
    record=[]
    for ob in chosen:
        world=ob.matrix_world.copy();v=np.asarray([(world@p.co)[:]for p in ob.data.vertices]);new=np.empty_like(v)
        new[:,0]=-1.435+(v[:,depth]-middle[depth])*min(.65,.10/max(span[depth],1e-6))
        new[:,1]=.20+(v[:,width]-middle[width])*1.44/span[width]
        new[:,2]=.795+(v[:,2]-lo[2])*1.61/span[2]
        ob.parent=None;ob.matrix_world=Matrix.Identity(4);ob.animation_data_clear()
        ob.data.vertices.foreach_set('co',new.ravel());ob.data.update();record.append(dict(object=ob.name,vertices=len(v)))
    for ob in objects:
        if ob not in chosen:bpy.data.objects.remove(ob,do_unlink=True)
    original=next(m for m in chosen[0].data.materials if m and m.use_nodes)
    unified=original.copy();unified.name='One full-width curtain / warm ivory linen'
    for ob in chosen:ob.data.materials.clear();ob.data.materials.append(unified)
    materials={unified}
    for m in materials:
        nodes=m.node_tree.nodes;links=m.node_tree.links
        for output in [n for n in nodes if n.type=='OUTPUT_MATERIAL']:
            for link in list(output.inputs['Displacement'].links):links.remove(link)
        for bs in [n for n in nodes if n.type=='BSDF_PRINCIPLED']:
            bs.inputs['Specular IOR Level'].default_value=.22;bs.inputs['Sheen Weight'].default_value=.12
            for link in list(bs.inputs['Metallic'].links):links.remove(link)
            bs.inputs['Metallic'].default_value=0.
            for link in list(bs.inputs['Base Color'].links):
                source=link.from_socket;links.remove(link)
                grain=nodes.new('ShaderNodeRGBToBW');links.new(source,grain.inputs[0])
                dye=nodes.new('ShaderNodeMixRGB');dye.inputs[0].default_value=.94;dye.inputs[2].default_value=(.55,.51,.43,1.)
                links.new(grain.outputs[0],dye.inputs[1]);links.new(dye.outputs[0],bs.inputs['Base Color'])
            for link in list(bs.inputs['Roughness'].links):
                source=link.from_socket;links.remove(link);rough=nodes.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.82;rough.inputs['To Max'].default_value=.96
                links.new(source,rough.inputs['Value']);links.new(rough.outputs['Result'],bs.inputs['Roughness'])
            if not bs.inputs['Roughness'].is_linked:bs.inputs['Roughness'].default_value=.88
        for normal in [n for n in nodes if n.type=='NORMAL_MAP']:normal.inputs['Strength'].default_value=.28
        output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL'and n.is_active_output)
        surface=output.inputs['Surface'].links[0].from_socket
        transmission=nodes.new('ShaderNodeBsdfTranslucent');transmission.inputs['Color'].default_value=(.55,.51,.43,1.)
        mix=nodes.new('ShaderNodeMixShader');mix.inputs[0].default_value=.22
        links.new(surface,mix.inputs[1]);links.new(transmission.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],output.inputs['Surface'])
    return dict(asset='BlenderKit Gray linen curtain / d76ef886-dc84-40ff-a737-e15aa0f1841d',objects=record,
        revision='single_ivory_panel',panel_count=1,material_count=1,sheer_layer_removed=True,
        full_window_covered=True,dye_linear_rgb=[.55,.51,.43],common_static_background=True,window_exterior_hidden=True)

def build_room(scene,material,cube,curve,asset,floor_material):
    floor=floor_material();cube('Oak floor',(0,0,-.035),(7,7,.07),floor)
    plaster=painted_wall();ceiling=material('Ceiling flat warm white',(.72,.71,.67),.93)
    def wall(name,loc,dims):
        o=cube(name,loc,dims,plaster,.0007);metric_uv(o);return o
    wall('Bedroom back wall',(0,1.87,1.45),(6,.14,2.9))
    wall('Bedroom right wall',(3.,0,1.45),(.14,4.,2.9))
    wall('Bedroom camera-side wall',(.70,-2.05,1.45),(4.6,.14,2.9))
    cube('Room ceiling',(.70,0,2.94),(4.6,4.,.08),ceiling)
    # Four actual masonry returns leave a window opening; no solid wall behind it.
    wall('Left wall below sill',(-1.65,0,.39),(.14,4.,.78))
    wall('Left wall above window',(-1.65,0,2.575),(.14,4.,.65))
    wall('Left wall front return',(-1.65,-1.195,1.515),(.14,1.61,1.47))
    wall('Left wall rear return',(-1.65,1.395,1.515),(.14,1.21,1.47))
    trim=material('Eggshell painted timber trim',(.58,.57,.53),.63)
    cube('Back skirting',(0,1.785,.053),(6,.028,.104),trim,.0009)
    cube('Left skirting',(-1.565,0,.053),(.028,4.,.104),trim,.0009)
    caulk=material('Fine caulk and shadow line',(.32,.31,.28),.9)
    cube('Back skirting caulk',(0,1.771,.108),(6,.002,.0018),caulk)
    ivory=material('Window frame painted ivory',(.70,.70,.65),.42)
    gasket=material('Weathered rubber window seals',(.022,.024,.023),.77)
    for y in [-.39,.79]:
        cube('Window outer jamb',(-1.565,y,1.515),(.075,.052,1.51),ivory,.0007)
        cube('Narrow glass gasket',(-1.542,y+(.030 if y<0 else-.030),1.515),(.003,.003,1.39),gasket,.0004)
    for z in [.79,2.25]:cube('Window outer rail',(-1.565,.20,z),(.075,1.23,.052),ivory,.0007)
    cube('Window sill with real overhang',(-1.565,.20,.783),(.22,1.34,.028),ivory,.0015)
    cube('Window central mullion',(-1.55,.20,1.52),(.055,.032,1.43),ivory,.0006)
    glass=material('Window glass',(.90,.94,.96),.035);bs=glass.node_tree.nodes.get('Principled BSDF');bs.inputs['Transmission Weight'].default_value=1.;bs.inputs['IOR'].default_value=1.45
    cube('Window glazing',(-1.64,.20,1.52),(.006,1.12,1.39),glass)
    outside=material('Unresolved diffuse daylight beyond curtain',(.84,.87,.91),1.)
    cube('Plain exterior light field',(-1.90,.20,1.52),(.012,1.6,1.8),outside)
    curtain_record=curtains()
    metal=material('Curtain rod aged blackened brass',(.055,.043,.028),.38,.72)
    curve('Curtain rod',[(-1.43,-.59,2.42),(-1.43,.99,2.42)],.009,metal)
    for y in [-.55,.95]:
        curve('Curtain wall bracket',[(-1.578,y,2.39),(-1.43,y,2.39),(-1.43,y,2.42)],.004,metal)
    desk=asset('desk',loc=(-.91,-.035,0.),width=1.16)
    for ob in desk.children:
        if ob.type!='MESH':continue
        for mat in ob.data.materials:
            if not mat or not mat.use_nodes:continue
            for bs in [n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED']:
                bs.inputs['Specular IOR Level'].default_value=.30
                if not bs.inputs['Roughness'].is_linked:bs.inputs['Roughness'].default_value=.5
    paper=material('Slightly warm page edges',(.58,.56,.51),.89);cover=material('Used navy linen notebook cover',(.022,.040,.051),.92)
    cube('Notebook page block',(-.77,-.14,.746),(.235,.168,.018),paper,.001)
    for z in [.736,.756]:cube('Notebook cloth cover',(-.77,-.14,z),(.245,.176,.0026),cover,.001)
    cube('Notebook bound spine',(-.891,-.14,.746),(.006,.176,.023),cover,.0015)
    pencil=material('Graphite pencil lacquer',(.10,.07,.035),.46)
    curve('Pencil on desk',[(-.91,.055,.742),(-.77,.11,.742)],.003,pencil)
    curve('Fine graphite tip',[(-.77,.11,.742),(-.758,.115,.742)],.002,material('Graphite',(.018,.018,.018),.7))
    # A small handmade cup has wall thickness, a rolled lip, handle and liquid.
    ceramic=material('Glazed warm ceramic',(.48,.43,.34),.27)
    vertices=[];faces=[];rings=[(.031,0.),(.035,.006),(.036,.076),(.035,.081),(.0315,.081),(.031,.010),(.0,.010)]
    for radius,z in rings:
        for j in range(64):
            a=2*math.pi*j/64;vertices.append((-.999+radius*math.cos(a),.125+radius*math.sin(a),.737+z))
    for k in range(len(rings)-1):
        for j in range(64):faces.append((k*64+j,k*64+(j+1)%64,(k+1)*64+(j+1)%64,(k+1)*64+j))
    mesh=bpy.data.meshes.new('Ceramic cup profile');mesh.from_pydata(vertices,[],faces);mesh.update();cup=bpy.data.objects.new('Everyday ceramic cup',mesh);bpy.context.collection.objects.link(cup);mesh.materials.append(ceramic)
    for p in mesh.polygons:p.use_smooth=True
    handle=[(-.955+.022*math.cos(a),.125,.782+.027*math.sin(a))for a in np.linspace(0,2*math.pi,49)]
    curve('Cup handle',handle,.004,ceramic)
    bpy.ops.mesh.primitive_cylinder_add(vertices=64,radius=.0305,depth=.001,location=(-.999,.125,.799));bpy.context.object.name='Tea surface';bpy.context.object.data.materials.append(material('Tea',(.025,.012,.005),.16))
    outlet=material('Slightly aged outlet plastic',(.60,.59,.55),.54)
    cube('Domestic socket plate',(-.40,1.790,.29),(.086,.008,.086),outlet,.003)
    for x in [-.416,-.384]:cube('Socket recess',(x,1.784,.30),(.005,.003,.014),gasket,.001)
    bedwood=material('Bed frame walnut',(.13,.081,.046),.5);bedx=1.80
    cube('Bed base',(bedx,.82,.26),(1.43,1.90,.28),bedwood,.025)
    cube('Linen mattress',(bedx,.82,.49),(1.39,1.88,.21),material('Cream cotton bedding',(.53,.51,.46),.98),.07)
    cube('Bed headboard',(bedx,1.74,.76),(1.48,.09,.93),bedwood,.025)
    cube('Pillow',(bedx,1.38,.65),(.63,.43,.17),material('Pillow linen',(.65,.64,.59),.98),.07)
    world=bpy.data.worlds.new('Outdoor diffuse ambience through window');world.use_nodes=True;scene.world=world
    world.node_tree.nodes.get('Background').inputs['Color'].default_value=(.72,.79,.88,1);world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.08
    d=bpy.data.lights.new('Afternoon daylight outside real opening','AREA');d.energy=600.;d.shape='RECTANGLE';d.size=1.12;d.size_y=1.38;d.color=(1.,.94,.86)
    light=bpy.data.objects.new(d.name,d);bpy.context.collection.objects.link(light);light.location=(-1.78,.20,1.61);light.rotation_euler=(Vector((0,.05,.65))-light.location).to_track_quat('-Z','Y').to_euler()
    return dict(revision='lived_in_room',wall_asset='BlenderKit Painted Plaster Wall / 34b64880-c077-4c11-833a-45649e99490e',curtain=curtain_record,
        actual_window_opening=True,closed_room_shell=True,exterior_rendered=False,window_key_power_w=600.,static_background_shared_by_all_cases=True)
