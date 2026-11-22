"""Domestic material/lighting corrections, common to all six rendered cases."""
import bpy,math,numpy as np
from common import asset,save
from textiles import clean_principled,photo


def metric_uv(obj,name,scale=1.,axes=None):
    vertices=np.array([obj.matrix_world@v.co for v in obj.data.vertices]);values=np.zeros((len(obj.data.loops),2),np.float32)
    for face in obj.data.polygons:
        pair=axes
        if pair is None:
            normal=np.abs(np.array(obj.matrix_world.to_3x3()@face.normal));axis=int(np.argmax(normal));pair=[(1,2),(0,2),(0,1)][axis]
        for loop in face.loop_indices:values[loop]=vertices[obj.data.loops[loop].vertex_index,list(pair)]/scale
    uv=obj.data.uv_layers.get(name)or obj.data.uv_layers.new(name=name);uv.data.foreach_set('uv',values.reshape(-1))


def curtain_point(u,t):
    theta=math.tau*(7.8*u+.11*math.sin(math.tau*u)+.035*math.sin(3*math.tau*u))
    amplitude=.032+.007*math.sin(3.7*u+.6)
    wave=math.sin(theta+.035*t)+.16*math.sin(2*theta+.7)
    return [-2.68+1.68*u,.48+amplitude*wave*(.80+.20*t)+.0025*math.sin(8*u+math.pi*t),.735+1.975*t+.0035*math.sin(theta+.5)*(1-t)**2]


def finish(api,out):
    report_dir=out
    cube=api['cube'];mesh=api['mesh_object'];material=api['material'];area=api['area']
    for obj in list(bpy.context.scene.objects):
        if obj.name.startswith('Oak floor plank')or obj.name.startswith('Botanical paper motif'):bpy.data.objects.remove(obj,do_unlink=True)
    floor=material('Scanned oak floor, satin finish',(.3,.22,.14),.65);n,l,bs,out=clean_principled(floor);bs.inputs['Sheen Weight'].default_value=0
    uv=n.new('ShaderNodeUVMap');uv.uv_map='Floor UV'
    diffuse=photo(n,l,'oak_wood_planks_diff_2k.jpg',uv.outputs[0]);sat=n.new('ShaderNodeHueSaturation');sat.inputs['Saturation'].default_value=.68;sat.inputs['Value'].default_value=.92;l.new(diffuse.outputs[0],sat.inputs['Color']);l.new(sat.outputs[0],bs.inputs['Base Color'])
    rough=photo(n,l,'oak_wood_planks_rough_2k.jpg',uv.outputs[0],True);rm=n.new('ShaderNodeMapRange');rm.inputs['To Min'].default_value=.48;rm.inputs['To Max'].default_value=.76;l.new(rough.outputs[0],rm.inputs[0]);l.new(rm.outputs[0],bs.inputs['Roughness'])
    normal=photo(n,l,'oak_wood_planks_nor_gl_2k.png',uv.outputs[0],True);nm=n.new('ShaderNodeNormalMap');nm.uv_map='Floor UV';nm.inputs['Strength'].default_value=.5;l.new(normal.outputs[0],nm.inputs['Color']);l.new(nm.outputs[0],bs.inputs['Normal'])
    obj=cube('Photographed continuous oak floor',(0,-2.05,-.01),(8.,6.1,.02),floor,.0003);metric_uv(obj,'Floor UV',1.20000005,(0,1))
    wall=bpy.data.materials['Warm chalk plaster'];n,l,bs,out=clean_principled(wall);bs.inputs['Sheen Weight'].default_value=0;bs.inputs['Specular IOR Level'].default_value=.28
    uv=n.new('ShaderNodeUVMap');uv.uv_map='Wall UV';diff=photo(n,l,'white_plaster_02_diff_2k.jpg',uv.outputs[0]);gray=n.new('ShaderNodeRGBToBW');l.new(diff.outputs[0],gray.inputs[0])
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.51,.50,.465,1);ramp.color_ramp.elements[1].color=(.65,.635,.595,1);l.new(gray.outputs[0],ramp.inputs[0]);l.new(ramp.outputs[0],bs.inputs['Base Color'])
    bs.inputs['Roughness'].default_value=.91
    normal=photo(n,l,'white_plaster_02_nor_gl_2k.png',uv.outputs[0],True);nm=n.new('ShaderNodeNormalMap');nm.uv_map='Wall UV';nm.inputs['Strength'].default_value=.18;l.new(normal.outputs[0],nm.inputs['Color']);l.new(nm.outputs[0],bs.inputs['Normal'])
    for name,location,dims in [('Actual room left wall',(-3.55,-1.96,1.5),(.12,5.75,3.)),('Actual room right wall',(3.55,-1.96,1.5),(.12,5.75,3.)),('Actual room ceiling',(0,-1.96,3.05),(7.2,5.75,.12)),('Actual wall behind camera',(0,-4.85,1.5),(7.2,.12,3.))]:cube(name,location,dims,wall,.002)
    for obj in bpy.context.scene.objects:
        if obj.type=='MESH'and any(m==wall for m in obj.data.materials):metric_uv(obj,'Wall UV')
    frame=bpy.data.materials['Window painted timber'];bs=frame.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(.66,.65,.615,1);bs.inputs['Roughness'].default_value=.58
    wood=bpy.data.materials['Photographed oak, Poly Haven wood_table_001'];n=wood.node_tree.nodes;l=wood.node_tree.links;bs=n.get('Principled BSDF')
    if bs.inputs['Base Color'].is_linked:
        previous=bs.inputs['Base Color'].links[0].from_socket;sat=n.new('ShaderNodeHueSaturation');sat.inputs['Saturation'].default_value=.58;sat.inputs['Value'].default_value=.88;l.new(previous,sat.inputs['Color']);l.new(sat.outputs[0],bs.inputs['Base Color'])
    if bs.inputs['Roughness'].is_linked:
        previous=bs.inputs['Roughness'].links[0].from_socket;rm=n.new('ShaderNodeMapRange');rm.inputs['To Min'].default_value=.42;rm.inputs['To Max'].default_value=.70;l.new(previous,rm.inputs[0]);l.new(rm.outputs[0],bs.inputs['Roughness'])
    obj=bpy.data.objects['Gathered linen curtain'];nx=192;nz=54
    for k in range(nz+1):
        for i in range(nx+1):obj.data.vertices[k*(nx+1)+i].co=curtain_point(i/nx,k/nz)
    from room import weave_uv
    weave_uv(obj,(.270708,.2713),'XZ')
    hems=[o for o in bpy.context.scene.objects if o.name.startswith('Hem sewn along curtain folds')]
    for obj,(t0,t1)in zip(sorted(hems,key=lambda o:o.name),[(0,.007),(.991,1)]):
        for k,t in enumerate([t0,t1]):
            for i in range(nx+1):v=curtain_point(i/nx,t);v[1]-=.0004;obj.data.vertices[k*(nx+1)+i].co=v
        weave_uv(obj,(.270708,.2713),'XZ')
    curtain=bpy.data.materials['Backlit warm linen curtain'];n=curtain.node_tree.nodes
    for node in n:
        if node.type=='MIX_SHADER':node.inputs[0].default_value=.48
        elif node.type=='VALTORGB':node.color_ramp.elements[0].color=(.39,.38,.345,1);node.color_ramp.elements[1].color=(.70,.68,.63,1)
    # A genuine flat botanical print replaces the extruded block motif.
    art=material('Public-domain botanical print on rag paper',(.7,.7,.7),.9);n,l,bs,out=clean_principled(art);bs.inputs['Sheen Weight'].default_value=0;bs.inputs['Specular IOR Level'].default_value=.25
    tex=n.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(asset('met_360446_botanical_study.jpg')),check_existing=True);l.new(tex.outputs[0],bs.inputs['Base Color']);bs.inputs['Roughness'].default_value=.88
    width=.415;height=width*tex.image.size[1]/tex.image.size[0];cx=.66;cz=1.61
    vertices=np.array([[cx-width/2,.768,cz-height/2],[cx+width/2,.768,cz-height/2],[cx+width/2,.768,cz+height/2],[cx-width/2,.768,cz+height/2]])
    mesh('Botanical study, genuine flat print',vertices,np.array([[0,1,2,3]]),np.array([[[0,0],[1,0],[1,1],[0,1]]]),art)
    # Flat printed type and visible page edges, shared domestic set dressing.
    ink=material('Book cover printed ink',(.065,.035,.023),.9)
    for text,location,size in [('BOTANICAL',(-1.685,-.145,.5831),.014),('NOTES',(-1.652,-.170,.5831),.011),('A FIELD JOURNAL',(-1.665,-.207,.5831),.0045)]:
        curve=bpy.data.curves.new('Printed book typography','FONT');curve.body=text;curve.size=size;curve.extrude=0;curve.align_x='LEFT';curve.materials.append(ink);obj=bpy.data.objects.new('Ink printed flush on book cover',curve);bpy.context.collection.objects.link(obj);obj.location=location
    paper=bpy.data.materials['Uncoated book paper'];bs=paper.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(.64,.61,.54,1)
    ceramic=bpy.data.materials['Glazed oatmeal stoneware'];n=ceramic.node_tree.nodes;l=ceramic.node_tree.links;bs=n.get('Principled BSDF');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=180;noise.inputs['Detail'].default_value=2
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.36,.315,.25,1);ramp.color_ramp.elements[1].color=(.57,.52,.435,1);l.new(noise.outputs['Fac'],ramp.inputs[0]);l.new(ramp.outputs[0],bs.inputs['Base Color']);bs.inputs['Roughness'].default_value=.24
    for obj in list(bpy.context.scene.objects):
        if obj.type=='LIGHT':bpy.data.objects.remove(obj,do_unlink=True)
    area('Broad overcast light outside glazing',(-2.24,1.40,2.04),(.28,-.3,.60),1950,2.25,(.91,.95,1.),2.0)
    area('Very weak interior reflected fill',(1.7,-3.9,2.15),(.15,-.05,.62),22,2.7,(1.,.91,.80),2.1)
    world=bpy.context.scene.world;world.node_tree.nodes['Background'].inputs['Color'].default_value=(.69,.76,.85,1);world.node_tree.nodes['Background'].inputs['Strength'].default_value=.18
    save(report_dir/'photographic_room_definition.json',dict(floor_plane_z_m=0.,floor_texture_tile_m=1.20000005,room_enclosed=True,window_exterior_rendered=False,cloth_geometry_or_trajectory_changed=False,
        light='Broad nonemissive-window daylight, room enclosure and low reflected interior fill',art='Met Open Access: Mary Delany, Botanical Study, object 360446',style='Common photographic baseline for source and all edits.'))
