"""Imported CC0 mahjong furniture and appearance-only domestic context."""
from pathlib import Path
import math
import bpy
from mathutils import Matrix
ROOT=Path(__file__).resolve().parents[4]
TABLE_REVISION='innerscene_mahjong_game_table'
TABLE_FILE=ROOT/'assets/innerscene/mahjong_game_table/mahjong-game-table.glb'
OLD_TABLE_NAMES={'Card table solid timber foundation','Solid wooden perimeter rail - real inset opening',
'Inset baize - top coincides with solved support plane','Cloth binding seated inside timber rail','Table apron'}

def world_bounds(objects):
    points=[o.matrix_world@v.co for o in objects if o.type=='MESH' for v in o.data.vertices]
    return [[min(p[k] for p in points) for k in range(3)],[max(p[k] for p in points) for k in range(3)]]

def crop_existing_fibres(bounds):
    obj=bpy.data.objects['Fine short baize fibres - 8 to 18 micron width'];old=obj.data
    verts=[];faces=[];materials=[]
    for j in range(0,len(old.vertices),6):
        points=[old.vertices[j+k].co.copy() for k in range(6)]
        world=[obj.matrix_world@p for p in points]
        if not all(bounds[0][0]+.003<p.x<bounds[1][0]-.003 and bounds[0][1]+.003<p.y<bounds[1][1]-.003 for p in world):continue
        i=len(verts);verts.extend(points);faces.extend([(i,i+1,i+3,i+2),(i+2,i+3,i+5,i+4)])
        materials.extend([old.polygons[j//3].material_index,old.polygons[j//3+1].material_index])
    mesh=bpy.data.meshes.new('Existing fibres trimmed to actual imported playing field');mesh.from_pydata(verts,[],faces);mesh.update()
    for m in old.materials:mesh.materials.append(m)
    for p,idx in zip(mesh.polygons,materials):p.material_index=idx
    obj.data=mesh
    return len(faces)//2

def import_table(cfg,ledger):
    for obj in list(bpy.context.scene.objects):
        if obj.name in OLD_TABLE_NAMES or obj.name.startswith('Card table tapered timber support'):
            bpy.data.objects.remove(obj,do_unlink=True)
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(TABLE_FILE))
    imported=[o for o in bpy.data.objects if o not in before];meshes=[o for o in imported if o.type=='MESH']
    assert len(meshes)==22
    field=next(o for o in meshes if o.name=='Square inset playing field')
    bpy.context.view_layer.update();source_bounds=world_bounds(meshes);source_field=world_bounds([field])
    # Uniform SI height normalization seats the source feet on the room floor,
    # while matching the actual top plane to the frozen solved support plane.
    scale=cfg['appearance']['card_table'].get('horizontal_reference_height_m',cfg['physics']['floor_z'])/source_field[1][2]
    vertical_scale=cfg['physics']['floor_z']/source_field[1][2]
    root=bpy.data.objects.new('Innerscene mahjong table placement',None);bpy.context.collection.objects.link(root)
    for obj in imported:
        if obj.parent is None:obj.parent=root
        obj['static_decorative_prop']=True
        obj['source_asset']='Innerscene Mahjong table - Game Table / CC0-1.0'
        obj['source_object_name']=obj.name
        obj.name='Mahjong | '+obj.name
    root.scale=(scale,scale,vertical_scale);root.location=(0,cfg['appearance']['card_table']['center_y_m'],0)
    bpy.context.view_layer.update();actual=world_bounds(meshes);playing=world_bounds([field])
    assert abs(playing[1][2]-cfg['physics']['floor_z'])<1e-7 and abs(actual[0][2])<1e-7
    kept=crop_existing_fibres(playing)
    return {**ledger,'table_asset':TABLE_REVISION,'table_asset_file':str(TABLE_FILE.relative_to(ROOT)),
    'table_source_world_bounds_m':source_bounds,'table_source_playing_field_bounds_m':source_field,
    'table_horizontal_reference_scale':scale,'table_vertical_height_scale':vertical_scale,'table_uniform_height_scale':scale if abs(scale-vertical_scale)<1e-10 else None,'table_world_bounds_m':actual,'table_dimensions_m':[actual[1][k]-actual[0][k] for k in range(3)],
    'felt_world_bounds_m':playing,'felt_dimensions_m':[playing[1][k]-playing[0][k] for k in range(3)],
    'felt_surface_z_m':playing[1][2],'felt_fibre_ribbons':kept,
    'table_geometry_note':'All 22 supplied mesh/UV/normal arrays retained. Horizontal fit is fixed at the prior reference height; vertical fit follows the actual collision support height. Feet remain on the room floor.',
    'table_materials_note':'Supplied longitudinal/end-grain walnut, trays, feet, bronze brackets and textile PBR.',
    'contact_material_note':'Imported furniture and textile remain visual only; actual collision support height is configuration.physics.floor_z. Relative dimensions, friction, gravity and all target edits retain the accepted values.'}

def enhance_environment(cfg,ledger):
    rev=cfg['appearance']['card_table'].get('table_asset')
    if rev is None:return ledger
    if rev!=TABLE_REVISION:raise ValueError('Unknown mahjong table asset: '+str(rev))
    for key in ['felt_nap_revision','felt_wear_center_xy_m','felt_wear_ellipse_radii_m','felt_wear_is_shader_only','raised_rail_height_above_felt_m']:ledger.pop(key,None)
    result=refine_milled_trays(cfg,linen_window_context(cfg,finish_table_textile(cfg,import_table(cfg,ledger))))
    from window_realism import rebuild_window
    result=rebuild_window(cfg,result)
    from gathered_linen import enhance_environment as gathered_drapes
    result=gathered_drapes(cfg,result)
    from loose_card_realism import enhance_environment as loose_paper
    result=loose_paper(cfg,result)
    return correct_room_layout(cfg,result)

def finish_table_textile(cfg,ledger):
    from look_domino_chain import material,set_socket
    field=bpy.data.objects['Mahjong | Square inset playing field']
    mat=material('Pressed green wool baize - subtle photo fibres',(.021,.050,.032,1),.91)
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;bs=nodes.get('Principled BSDF')
    set_socket(bs,'IOR',1.46);set_socket(bs,'Sheen Weight',.14);set_socket(bs,'Sheen Roughness',.78)
    set_socket(bs,'Sheen Tint',(.24,.32,.19,1))
    position=nodes.new('ShaderNodeNewGeometry')
    mapping=nodes.new('ShaderNodeVectorMath');mapping.operation='SCALE';mapping.inputs['Scale'].default_value=5
    links.new(position.outputs['Position'],mapping.inputs[0])
    tex=nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(ROOT/'assets/ambientcg/Fabric034/Fabric034_SQ_Color.jpg'),check_existing=True)
    tex.image.colorspace_settings.name='sRGB';links.new(mapping.outputs['Vector'],tex.inputs['Vector'])
    gray=nodes.new('ShaderNodeRGBToBW');links.new(tex.outputs['Color'],gray.inputs[0])
    tone=nodes.new('ShaderNodeMapRange');tone.clamp=True;tone.inputs['From Min'].default_value=.15;tone.inputs['From Max'].default_value=.65
    tone.inputs['To Min'].default_value=.88;tone.inputs['To Max'].default_value=1.12;links.new(gray.outputs[0],tone.inputs['Value'])
    dye=nodes.new('ShaderNodeMixRGB');dye.blend_type='MULTIPLY';dye.inputs[0].default_value=1;dye.inputs[1].default_value=(.021,.050,.032,1)
    links.new(tone.outputs['Result'],dye.inputs[2]);links.new(dye.outputs[0],bs.inputs['Base Color'])
    height=nodes.new('ShaderNodeBump');height.inputs['Distance'].default_value=.000060;height.inputs['Strength'].default_value=.30
    links.new(gray.outputs[0],height.inputs['Height']);links.new(height.outputs[0],bs.inputs['Normal'])
    rough=nodes.new('ShaderNodeMapRange');rough.inputs['From Min'].default_value=.15;rough.inputs['From Max'].default_value=.65
    rough.inputs['To Min'].default_value=.87;rough.inputs['To Max'].default_value=.95;rough.clamp=True
    links.new(gray.outputs[0],rough.inputs['Value']);links.new(rough.outputs[0],bs.inputs['Roughness'])
    field.data.materials[0]=mat
    return {**ledger,'felt_asset':'ambientCG Fabric034 official photo texture plus existing real-scale fibres',
    'felt_finish_revision':'pressed_baize','felt_selected_repeat_m':.20,'felt_repeat_is_measured':False,
    'felt_fibre_bump_distance_m':.000060,'table_materials_note':'Source walnut/end grain, bronze and feet retained; photo oak lines four trays, and photo Fabric034 shades the playfield. Original UV/mesh unchanged.'}


def linen_window_context(cfg,ledger):
    if cfg['appearance']['room'].get('window_context_revision')!='painted_casement_garden':return ledger
    from look_domino_chain import box,material,look_at,set_socket
    from card_table_environment import metre_uv
    # Source scene components are already metre scale. Only four window/linen
    # pieces are appended; no source furniture, camera or lights are brought in.
    path=ROOT/'assets/blenderkit/modern_living_room_interior/modern_living_room_interior.blend'
    names=['Window','Plane.004','Plane.005','Cylinder']
    with bpy.data.libraries.load(str(path),link=False) as (source,target):target.objects=list(names)
    objects=list(target.objects);assert all(o for o in objects)
    for obj in objects:bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.update()
    transform=Matrix.Translation((-.75,-1.1562353134+cfg['appearance']['room']['back_wall_y_m']-1.9,-.06))@Matrix.Rotation(math.pi,4,'Z')
    originals={}
    for obj,source_name in zip(objects,names):
        old_world=obj.matrix_world.copy();obj.parent=None
        originals[source_name]={'matrix':[list(r) for r in old_world],'vertices':len(obj.data.vertices),'polygons':len(obj.data.polygons)}
        obj.matrix_world=transform@old_world;obj.name='Linen window | '+source_name
        obj['static_decorative_prop']=True;obj['source_asset']='Modern Living Room Interior / Ibrohim Toxirov / BlenderKit royalty_free';obj['source_object_name']=source_name
    bpy.context.view_layer.update();window=objects[0];bounds=world_bounds([window])
    source_reference_bounds=[list(v) for v in bounds]
    sill=cfg['appearance']['room'].get('window_sill_height_m')
    if sill is not None:bounds[0][2]=sill-.014
    glazing=material('Privacy glazing - physical rough transmission',(.93,.96,.99,1),.65)
    gb=glazing.node_tree.nodes.get('Principled BSDF')
    set_socket(gb,'Transmission Weight',1.0);set_socket(gb,'IOR',1.46)
    for idx,mat in enumerate(window.data.materials):
        if mat and mat.name.split('.')[0]=='Glass':window.data.materials[idx]=glazing
    for name in ['Home dining room back wall','Home dining room side wall','Continuous home floor']:
        obj=bpy.data.objects.get(name)
        if obj:bpy.data.objects.remove(obj,do_unlink=True)
    wall=bpy.data.materials['Soft warm home dining room plaster']
    bs=wall.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(.60,.575,.52,1);bs.inputs['Roughness'].default_value=.86
    x0,x1=bounds[0][0]+.014,bounds[1][0]-.014;z0,z1=bounds[0][2]+.014,bounds[1][2]-.014;y=cfg['appearance']['room']['back_wall_y_m']
    pieces=[('left',(-3+x0)/2,(-3-x0)*-1,(z0+z1)/2,z1-z0),
            ('right',(x1+3)/2,3-x1,(z0+z1)/2,z1-z0),
            ('below',0,6,z0/2,z0),('above',0,6,(z1+2.8)/2,2.8-z1)]
    for name,x,width,z,height in pieces:
        obj=box('Room window wall | '+name,(x,y,z),(width,.12,height),wall,.001);obj['static_decorative_prop']=True
    box('Room side wall',(-3.04,(y-2.1)/2,1.4),(.12,y+2.1,2.8),wall,.001)
    floor_back=max(3.1,y+.30)
    floor=box('Continuous home floor',(0,(floor_back-2.9)/2,-.025),(6.4,floor_back+2.9,.05),bpy.data.materials['Satin oak card table rail - physical grain and handled edge'])
    metre_uv(floor)
    trim=material('Warm painted skirting and sill',(.69,.655,.575,1),.42)
    box('Window sill with rounded front edge',((x0+x1)/2,y-.10,z0-.012),(x1-x0+.05,.27,.024),trim,.003)
    box('Back wall skirting | left',((-3+x0)/2,y-.071,.047),(x0+3,.026,.094),trim,.002)
    box('Back wall skirting | right',((3+x1)/2,y-.071,.047),(3-x1,.026,.094),trim,.002)
    sky=material('Diffuse daylight beyond privacy glazing',(.8,.86,.90,1),1)
    sky.node_tree.nodes.clear();sn=sky.node_tree.nodes.new('ShaderNodeEmission');sn.inputs['Color'].default_value=(.65,.72,.78,1);sn.inputs['Strength'].default_value=1.0
    so=sky.node_tree.nodes.new('ShaderNodeOutputMaterial');sky.node_tree.links.new(sn.outputs[0],so.inputs['Surface'])
    box('Daylight surface beyond window',((x0+x1)/2,y+.35,(z0+z1)/2),(x1-x0+.4,.01,z1-z0+.4),sky)
    bpy.ops.object.light_add(type='AREA',location=((x0+x1)/2,y+.32,(z0+z1)/2))
    light=bpy.context.object;light.name='Soft fill through linen privacy window';light.visible_camera=False;light.visible_glossy=False;light.data.shape='RECTANGLE'
    light.data.size=x1-x0-.12;light.data.size_y=z1-z0-.12;light.data.energy=cfg['appearance']['room']['window_context_fill_w'];light.data.color=(.92,.955,1)
    look_at(light,(0,.05,.75))
    return {**ledger,'window_context_revision':'linen_privacy_window','window_component_source':str(path),
    'window_source_objects':originals,'window_component_transform':[list(r) for r in transform],
    'window_source_reference_bounds_m':source_reference_bounds,'window_world_bounds_m':bounds,'window_linen_bounds_m':{o.name:world_bounds([o]) for o in objects[1:3]},
    'window_fill_power_w':light.data.energy,'window_glazing_note':'Source frame with physical privacy glazing replacing a ray-switch glass shader; a diffuse outside daylight surface and an appearance fill (uncalibrated), not a pasted background.',
    'window_asset_license':'BlenderKit royalty_free: use in this rendered project; raw source/standalone extracted components are not redistributed.'}

def refine_milled_trays(cfg,ledger):
    from look_domino_chain import box
    wood=bpy.data.materials['Satin oak card table rail - physical grain and handled edge'].copy()
    wood.name='Milled oak tile trays - real metre grain'
    nodes=wood.node_tree.nodes;links=wood.node_tree.links
    mapping=next(n for n in nodes if n.bl_idname=='ShaderNodeMapping')
    position=nodes.new('ShaderNodeNewGeometry');links.new(position.outputs['Position'],mapping.inputs['Vector'])
    trays=[]
    for obj in bpy.context.scene.objects:
        if obj.name.startswith('Mahjong | ') and 'tile tray' in obj.name:
            obj.data.materials[0]=wood;trays.append(obj.name)
    return {**ledger,'table_tray_finish':'Four source tray meshes with photo oak lining, no geometry or transform edits.',
    'table_tray_objects':trays,'appearance_revision':'mahjong_home_linen','window_added_joinery':'Original source frame and sash retained; no added grille across the different source glazing depths.'}


def correct_room_layout(cfg,ledger):
    # The frozen cloth asset was authored for y=1.9 m. Reposition the intact
    # panels, hems and tiebacks as a single translation; no new cloth solve.
    wall_y=cfg['appearance']['room']['back_wall_y_m'];dy=wall_y-1.9
    moved=[]
    for o in bpy.context.scene.objects:
        if o.name in ['Linen window | Plane.004','Linen window | Plane.005'] or o.name.startswith(('Linen drape hem | ','Linen tieback | ')):
            o.location.y+=dy;moved.append(o.name)
    bpy.context.view_layer.update()
    result=dict(ledger)
    result['window_linen_bounds_m']={n:world_bounds([bpy.data.objects[n]]) for n in ['Linen window | Plane.004','Linen window | Plane.005']}
    for row in result.get('curtain_reconstruction',[]):
        row['world_bounds_m']=result['window_linen_bounds_m'][row['object']]
    for row in result.get('curtain_tiebacks',[]):
        row['center_m'][1]+=dy;row['wall_anchor_m'][1]+=dy
    result['room_spatial_revision']='visible_floor_room_gap'
    result['actual_back_wall_y_m']=wall_y
    result['window_sill_top_m']=cfg['appearance']['room'].get('window_sill_height_m',.4591455)
    result['table_to_back_wall_clearance_m']=wall_y-.06-ledger['table_world_bounds_m'][1][1]
    result['table_to_sill_clearance_m']=wall_y-.235-ledger['table_world_bounds_m'][1][1]
    result['curtain_rigid_translation_m']=[0,dy,0]
    result['translated_frozen_linen_objects']=moved
    result['room_spatial_note']='Window-wall setback and sill follow the recorded room configuration. Actual tabletop height follows physics.floor_z; horizontal footprint and all materials are retained.'
    result['continuous_floor_back_extent_m']=max(3.1,wall_y+.30)
    return result
