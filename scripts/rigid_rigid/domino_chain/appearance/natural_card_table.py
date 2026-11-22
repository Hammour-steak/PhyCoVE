"""Natural surface treatment and real tea-set asset. Appearance only."""
from __future__ import annotations
from pathlib import Path
import math,random
import bpy
from mathutils import Vector
from look_domino_chain import material,set_socket
from card_table_environment import mesh_object,lathe
ROOT=Path(__file__).resolve().parents[4]

def node_noise(nodes,links,vector,scale,detail=2):
    n=nodes.new('ShaderNodeTexNoise');n.inputs['Scale'].default_value=scale;n.inputs['Detail'].default_value=detail
    links.new(vector,n.inputs['Vector']);return n

def mapped(nodes,links,output,lo,hi,from_lo=0,from_hi=1):
    n=nodes.new('ShaderNodeMapRange');n.clamp=True
    for k,v in [('From Min',from_lo),('From Max',from_hi),('To Min',lo),('To Max',hi)]:n.inputs[k].default_value=v
    links.new(output,n.inputs['Value']);return n.outputs['Result']

def natural_paper():
    names={'Printed King of Hearts - Byron Knoll / Public Domain':'KH',
           'Printed Eight of Spades - Byron Knoll / Public Domain':'8S'}
    for mat in bpy.data.materials:
        if mat.name not in names and mat.name!='Original navy geometric card back':continue
        n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF')
        bs.inputs['Roughness'].default_value=.49;set_socket(bs,'Coat Weight',.008)
        for node in n:
            if node.bl_idname=='ShaderNodeMixRGB' and node.blend_type=='MULTIPLY':
                node.inputs[2].default_value=(.755,.746,.704,1)
            if node.bl_idname=='ShaderNodeTexImage' and mat.name in names:
                old=node.image
                node.image=bpy.data.images.load(str(ROOT/'assets/pcve/domino_chain_natural/card_faces'/(names[mat.name]+'_unruled.png')),check_existing=True)
                if old.users==0:bpy.data.images.remove(old)
        coord=n.new('ShaderNodeTexCoord')
        grain=node_noise(n,l,coord.outputs['Object'],8000,2)
        r=mapped(n,l,grain.outputs['Fac'],.44,.57);l.new(r,bs.inputs['Roughness'])
    edge=bpy.data.materials['Exposed used paper card edges'];bs=edge.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value=(.58,.565,.51,1);bs.inputs['Roughness'].default_value=.74
    # An imperfect but still squared-up deck; top/bottom footprints remain clear of the dominoes.
    rng=random.Random(41873)
    for i in range(50):
        obj=bpy.data.objects[f'Deck card {i+1:02}'];t=i/49
        obj.location.x=.00065*math.sin(i*.12)+rng.uniform(-.00035,.00035)
        obj.location.y=-.0010*t+rng.uniform(-.00022,.00022)
        obj.rotation_euler[2]=.0045*math.sin(i*.17)+rng.uniform(-.003,.003)
    top=bpy.data.objects['Deck card 50']
    top.location.x+=.0009;top.location.y-=.00055;top.rotation_euler[2]-=.008
    return {'card_outer_print_rule_removed':True,'deck_individual_offset_max_m':.0018,
            'printed_paper_albedo_tint_linear':[.755,.746,.704]}

def natural_felt(cfg):
    mat=bpy.data.materials['Brushed wool baize - fine fibres and restrained wear'];n=mat.node_tree.nodes;l=mat.node_tree.links
    bs=n.get('Principled BSDF');set_socket(bs,'Sheen Weight',.045);set_socket(bs,'Sheen Tint',(.16,.30,.20,1))
    # Keep the real felt image; tint gently dulled and compressed nap patches.
    color=next(node for node in n if node.bl_idname=='ShaderNodeMixRGB' and node.blend_type=='MULTIPLY')
    color.inputs[1].default_value=cfg['appearance']['card_table']['felt_color_linear']
    coord=n.new('ShaderNodeTexCoord')
    brushing=node_noise(n,l,coord.outputs['Object'],18,2)
    existing=color.inputs[2].links[0].from_socket
    factor=mapped(n,l,brushing.outputs['Fac'],.94,1.035)
    mult=n.new('ShaderNodeMath');mult.operation='MULTIPLY';l.new(existing,mult.inputs[0]);l.new(factor,mult.inputs[1]);l.new(mult.outputs[0],color.inputs[2])
    # Fibre directions get real geometry at the visible fabric surface. A 30 mm
    # swept contact strip stays clear, so no strand visually cuts through a tile.
    rng=random.Random(610031)
    mats=[material('Short baize fibre '+str(i),c,.93) for i,c in enumerate(
        [(.020,.052,.031,1),(.028,.064,.040,1),(.014,.039,.023,1),(.034,.073,.046,1)])]
    from paper_support import fibre_exclusion
    exclude_paper=fibre_exclusion(cfg);omitted_paper=0
    verts=[];faces=[];ids=[];count=cfg['appearance']['card_table']['visible_fibre_count'];surface=cfg['physics']['floor_z'];z=cfg['appearance']['card_table'].get('horizontal_reference_height_m',surface)
    for i in range(count):
        x,y=rng.uniform(-.235,.235),rng.uniform(-.105,.315)
        if -.085<x<.135 and -.017<y<.017:continue
        angle=rng.uniform(0,2*math.pi);length=rng.uniform(.00016,.00043);width=rng.uniform(.000008,.000018)
        dx,dy=math.cos(angle)*length,math.sin(angle)*length;wx,wy=-math.sin(angle)*width/2,math.cos(angle)*width/2
        start=len(verts)
        h=rng.uniform(.000018,.000065)
        for t,hz in [(0,.000004),(.5,h),(1,.000006)]:
            cx,cy=x+t*dx,y+t*dy
            verts.extend([(cx-wx,cy-wy,z+hz),(cx+wx,cy+wy,z+hz)])
        index=rng.choices(range(4),[.36,.22,.34,.08])[0]
        if exclude_paper(x,y):
            del verts[start:];omitted_paper+=1;continue
        faces.extend([(start,start+1,start+3,start+2),(start+2,start+3,start+5,start+4)])
        ids.extend([index,index])
    obj=mesh_object('Fine short baize fibres - 8 to 18 micron width',verts,faces)
    # Keep micron-scale source coordinates/normals intact under height changes.
    obj.location.z=surface-z
    for m in mats:obj.data.materials.append(m)
    for poly,index in zip(obj.data.polygons,ids):poly.material_index=index
    obj['static_decorative_prop']=True;obj['fibre_length_m']=[.00016,.00043];obj['fibre_height_m']=[.000018,.000065]
    return {'felt_fibre_ribbons':len(faces)//2,'fibre_ribbons_omitted_under_paper':omitted_paper,'felt_fibre_width_m':[.000008,.000018],
            'felt_fibre_length_m':[.00016,.00043],'felt_fibre_max_height_m':.000065,
            'fibres_omitted_in_swept_contact_strip_m':[-.085,.135,-.017,.017]}

def imported_tea(cfg):
    for name in ['Stoneware tea saucer - 90 mm diameter','Hollow tea cup - fine rolled ceramic rim','Tea surface and shallow meniscus']:
        obj=bpy.data.objects.get(name)
        if obj:bpy.data.objects.remove(obj,do_unlink=True)
    asset=ROOT/'assets/polyhaven/tea_set_01/tea_set_01_4k.blend'
    names=['tea_set_01_cup_small_01','tea_set_01_saucer_circular_04']
    with bpy.data.libraries.load(str(asset),link=False) as (source,target):
        target.objects=list(names)
    cup,plate=target.objects
    for obj in [cup,plate]:
        bpy.context.collection.objects.link(obj)
        for mat in obj.data.materials:
            if not mat or not mat.use_nodes:continue
            for node in mat.node_tree.nodes:
                if node.bl_idname=='ShaderNodeTexImage' and node.image:
                    node.image.filepath=str(asset.parent/'textures'/Path(node.image.filepath).name);node.image.reload()
    x,y=cfg['appearance']['card_table']['tea_center_xy_m'];z=cfg['physics']['floor_z']
    # Asset originals are metres. Move its true lowest plate point to the felt.
    plate_min=min(v.co.z for v in plate.data.vertices);plate.location=(x,y,z-plate_min+.000003)
    plate.rotation_euler[2]=-.20
    cup.location=(x,y,z-plate_min);cup.rotation_euler[2]=math.radians(-72)
    cup.name='PolyHaven floral tea cup - original 107 mm bowl';plate.name='PolyHaven floral saucer - original 149 mm diameter'
    bpy.context.view_layer.update()
    # Measure upper saucer seat and cup foot from evaluated original geometry.
    deps=bpy.context.evaluated_depsgraph_get();plate_eval=plate.evaluated_get(deps);cup_eval=cup.evaluated_get(deps)
    cup_mesh=cup_eval.to_mesh();plate_mesh=plate_eval.to_mesh()
    local_floor=min(v.co.z for v in cup_mesh.vertices)
    foot_r=max(math.hypot(v.co.x,v.co.y) for v in cup_mesh.vertices if v.co.z<local_floor+.00003)
    seat=[v.co.z for v in plate_mesh.vertices if math.hypot(v.co.x,v.co.y)<foot_r+.0003 and v.normal.z>.6]
    seat_top=max(seat)
    plate.location.z=z-min(v.co.z for v in plate_mesh.vertices)+.000005
    cup.location.z=plate.location.z+seat_top-local_floor+.000004
    cup_eval.to_mesh_clear();plate_eval.to_mesh_clear();bpy.context.view_layer.update()
    # One level liquid surface, about 8 mm below the actual cup lip.
    tea=material('Amber tea with room reflections',(.035,.011,.0027,1),.12)
    bs=tea.node_tree.nodes.get('Principled BSDF');set_socket(bs,'IOR',1.333);set_socket(bs,'Transmission Weight',.46)
    tea_z=cup.location.z+.060
    lathe('Level tea surface inside imported cup',[(.0487,.00042),(.0484,.00018),(.0480,0),(0,0)],(x,y,tea_z),tea,128)
    def actual_bounds(obj):
        evaluated=obj.evaluated_get(deps);points=[evaluated.matrix_world@Vector(v) for v in evaluated.bound_box]
        lo=[min(v[k] for v in points) for k in range(3)];hi=[max(v[k] for v in points) for k in range(3)]
        return {'min':lo,'max':hi,'dimensions_m':[hi[k]-lo[k] for k in range(3)]}
    return {'tea_asset':'Poly Haven Tea Set 01 / CC0','tea_asset_original_scale_preserved':True,
            'tea_cup_world_bounds':actual_bounds(cup),'tea_saucer_world_bounds':actual_bounds(plate),
            'tea_center_xy_m':[x,y],'tea_surface_z_m':tea_z,
            'tea_cup_seat_support_gap_m':.000004,'tea_cup_foot_radius_m':foot_r,'tea_saucer_seat_local_z_m':seat_top}

def enhance_environment(cfg,ledger):
    from paper_support import seat_paper
    result={**ledger,**natural_paper(),**seat_paper(cfg),**natural_felt(cfg),**imported_tea(cfg)}
    for key in ['tea_cup_height_m','tea_saucer_diameter_m','tea_cup_center_m']:result.pop(key,None)
    result['appearance_revision']='natural_card_table'
    result['contact_material_note']='Visual changes only; original quarter-gravity solver poses and contact parameters remain frozen.'
    return result

