"""Final photographic appearance layer: appearance only, SI metres.

Applied after sunlit_room_realism. It removes printed text from the shot (the
D0x identity marks on the tiles and the indexed playing cards), replaces the
smooth baize shader with a photographed napped wool, and lights the room only
from sources that exist in the scene: the analytic sun and the photographed
garden sky, both entering through the real casement. Physics, camera pose and
every solved sample are unchanged.
"""
import math
from pathlib import Path
import bpy
from look_domino_chain import set_socket
from natural_card_table import node_noise, mapped
ROOT=Path(__file__).resolve().parents[4]
REVISION='photographic_finish'
CARD_OBJECTS=['Loosely dealt 8 of spades','Loosely dealt King of hearts']+[f'Deck card {i:02}' for i in range(1,51)]
DECK_ANCHOR='Remaining deck - 50 separate 0.28 mm paper cards'


def remove_identity_labels():
    # The tiles carry only their moulded pips; the printed D01-D05 marks go.
    names=sorted(o.name for o in bpy.data.objects if o.name.endswith('_identity'))
    for name in names:bpy.data.objects.remove(bpy.data.objects[name],do_unlink=True)
    coll=bpy.data.collections.get('Sun receivers | identity labels excluded')
    if coll:
        for o in bpy.data.objects:
            if o.type=='LIGHT' and o.light_linking.receiver_collection==coll:o.light_linking.receiver_collection=None
        bpy.data.collections.remove(coll)
    return names


def remove_playing_cards():
    # Indexed card faces (K, 8) and the medallion back are printed graphics.
    names=[n for n in CARD_OBJECTS+[DECK_ANCHOR] if n in bpy.data.objects]
    for name in names:bpy.data.objects.remove(bpy.data.objects[name],do_unlink=True)
    return names


def caban_baize(cfg):
    """Dyed felted wool from the Poly Haven Caban scan at its provider scale."""
    field=bpy.data.objects['Mahjong | Square inset playing field']
    base=ROOT/cfg['asset']
    mat=bpy.data.materials.new('Dyed wool baize | Poly Haven Caban photographic nap');mat.use_nodes=True
    n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF')
    pos=n.new('ShaderNodeNewGeometry')
    scale=n.new('ShaderNodeVectorMath');scale.operation='DIVIDE'
    rx,ry=cfg['repeat_m'];scale.inputs[1].default_value=(rx,ry,1.0)
    offset=n.new('ShaderNodeVectorMath');offset.operation='ADD';offset.inputs[1].default_value=(.137,.311,0)
    l.new(pos.outputs['Position'],offset.inputs[0]);l.new(offset.outputs['Vector'],scale.inputs[0])
    def tex(name,colour):
        t=n.new('ShaderNodeTexImage');t.image=bpy.data.images.load(str(base/name),check_existing=True)
        t.image.colorspace_settings.name='sRGB' if colour else 'Non-Color';t.interpolation='Cubic'
        l.new(scale.outputs['Vector'],t.inputs['Vector']);return t
    diff=tex('caban_diff_4k.jpg',True);rough=tex('caban_rough_4k.jpg',False);nor=tex('caban_nor_gl_4k.jpg',False)
    # Keep the photographed fibre luminance; replace only the provider's orange dye.
    gray=n.new('ShaderNodeRGBToBW');l.new(diff.outputs['Color'],gray.inputs[0])
    lo,hi=cfg['luminance_window'];tone=mapped(n,l,gray.outputs[0],*cfg['tone_range'],lo,hi)
    # Decimetre dye-lot mottle hides the 0.27 m photographic repeat.
    broad=node_noise(n,l,pos.outputs['Position'],cfg['mottle_scale_per_m'],3)
    mottle=mapped(n,l,broad.outputs['Fac'],*cfg['mottle_range'],.3,.7)
    factor=n.new('ShaderNodeMath');factor.operation='MULTIPLY';l.new(tone,factor.inputs[0]);l.new(mottle,factor.inputs[1])
    dye=n.new('ShaderNodeMixRGB');dye.blend_type='MULTIPLY';dye.inputs[0].default_value=1;dye.inputs[1].default_value=tuple(cfg['dye_linear'])
    l.new(factor.outputs[0],dye.inputs[2]);l.new(dye.outputs[0],bs.inputs['Base Color'])
    r=mapped(n,l,rough.outputs['Color'],*cfg['roughness_range'],.45,1.0);l.new(r,bs.inputs['Roughness'])
    nm=n.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=cfg['normal_strength']
    l.new(nor.outputs['Color'],nm.inputs['Color']);l.new(nm.outputs['Normal'],bs.inputs['Normal'])
    set_socket(bs,'IOR',1.46);set_socket(bs,'Specular IOR Level',cfg['specular_level'])
    set_socket(bs,'Sheen Weight',cfg['sheen_weight']);set_socket(bs,'Sheen Roughness',cfg['sheen_roughness'])
    set_socket(bs,'Sheen Tint',tuple(cfg['sheen_tint_linear']))
    old=field.data.materials[0];field.data.materials[0]=mat
    mat['material_note']='Poly Haven Caban (CC0) luminance, roughness and normal maps at provider scale, re-dyed baize green; visual only.'
    return {'baize_material':mat.name,'replaced_material':old.name if old else None,'baize_repeat_m':list(cfg['repeat_m']),
            'baize_dye_linear':list(cfg['dye_linear'])}


def window_sky(cfg,rc):
    """Light the room from the sun and the photographed sky through the casement.

    The sunlit garden photograph moves from a 200 m emissive hemisphere to the
    world background with the same rotation and sun clip; a Cycles portal in the
    window opening guides sampling but adds no energy. The in-room area key and
    the area fill behind the glass (neither had a physical emitter) are removed.
    """
    removed=[]
    # Also the floating dark 'flag' panel beside the table: not a room object.
    for name in cfg['remove_lights']+cfg.get('remove_objects',[]):
        o=bpy.data.objects.get(name)
        if o:bpy.data.objects.remove(o,do_unlink=True);removed.append(name)
    ext=bpy.data.objects['Natural window | distant exterior hemisphere']
    em=ext.data.materials[0].node_tree.nodes
    angle=next(x for x in em if x.bl_idname=='ShaderNodeVectorRotate').inputs['Angle'].default_value
    image=next(x for x in em if x.bl_idname=='ShaderNodeTexEnvironment').image
    bpy.data.objects.remove(ext,do_unlink=True)
    world=bpy.context.scene.world;n=world.node_tree.nodes;l=world.node_tree.links;n.clear()
    coord=n.new('ShaderNodeTexCoord');rot=n.new('ShaderNodeVectorRotate');rot.rotation_type='AXIS_ANGLE'
    rot.inputs['Axis'].default_value=(0,0,1);rot.inputs['Angle'].default_value=angle
    l.new(coord.outputs['Generated'],rot.inputs['Vector'])
    env=n.new('ShaderNodeTexEnvironment');env.image=image;l.new(rot.outputs['Vector'],env.inputs['Vector'])
    clip=n.new('ShaderNodeVectorMath');clip.operation='MINIMUM';clip.inputs[1].default_value=(rc['exterior']['exterior_clip'],)*3
    l.new(env.outputs['Color'],clip.inputs[0])
    bg=n.new('ShaderNodeBackground');bg.inputs['Strength'].default_value=cfg['sky_strength']
    l.new(clip.outputs[0],bg.inputs['Color'])
    out=n.new('ShaderNodeOutputWorld');l.new(bg.outputs[0],out.inputs['Surface'])
    # Portal across the actual glazed opening, just outside the panes.
    panes=[o for o in bpy.data.objects if o.name.startswith('Natural window | ') and o.name.endswith(' pane')]
    pts=[o.matrix_world@v.co for o in panes for v in o.data.vertices]
    lo=[min(p[k] for p in pts) for k in range(3)];hi=[max(p[k] for p in pts) for k in range(3)]
    data=bpy.data.lights.new('Casement sky portal (no emission)','AREA');data.shape='RECTANGLE'
    data.size=hi[0]-lo[0]+.02;data.size_y=hi[2]-lo[2]+.02;data.cycles.is_portal=True
    portal=bpy.data.objects.new('Casement sky portal',data);bpy.context.collection.objects.link(portal)
    # Area lights emit along local -Z; point it into the room (-Y).
    portal.location=((lo[0]+hi[0])/2,hi[1]+.03,(lo[2]+hi[2])/2);portal.rotation_euler=(-math.pi/2,0,0)
    return {'removed_unmotivated_lights_and_flags':removed,'sky':'world background, same photograph, rotation and sun clip as the former exterior hemisphere',
            'sky_strength':cfg['sky_strength'],'sky_rotation_deg':math.degrees(angle),
            'portal_bounds_m':[lo,hi],'light_sources':['Late afternoon sun through casement (analytic sun)','garden sky through casement (world)']}


def apply_finish(cfg,ledger):
    rel=cfg['appearance'].get('finish') or {}
    if rel.get('revision')!=REVISION:return ledger
    rc=cfg['appearance']['realism']
    labels=remove_identity_labels() if rel['remove_identity_labels'] else []
    cards=remove_playing_cards() if rel['remove_playing_cards'] else []
    assert not [o.name for o in bpy.data.objects if o.type=='FONT'],'printed text left in the scene'
    baize=caban_baize(rel['baize'])
    light=window_sky(rel['lighting'],rc)
    bpy.context.scene.view_settings.exposure=rel['exposure_ev']
    result={k:v for k,v in ledger.items() if not k.startswith(('playing_card','deck_','card_','paper_','upper_loose','loose_card'))}
    return {**result,'finish_revision':REVISION,'removed_identity_label_objects':labels,'removed_playing_card_objects':len(cards),
            **baize,**light,'exposure_ev':rel['exposure_ev'],
            'finish_note':'Appearance only: no printed text, photographed wool baize, sun and sky through the real casement as the only light sources. Physics and camera unchanged.'}
