"""Finishing layer, applied on top of look_toy_car_track_jump.py and
refine_toy_car_track_jump.py. It changes no geometry, camera or pose.

- Daylight only: the hidden ceiling fill is removed; the low sun through the side window is
  strong enough to lay a real sunlit patch, cut by the window bars, across the floor and track.
- Molded toy plastics get a semi-gloss injection-molded finish, so the deck, rails and risers
  carry the window reflections a real polypropylene track shows at this low camera.
- The wool rug gets fibre sheen and a deeper pile, and the launcher housing a molded finish.
"""
import math
import bpy
from mathutils import Vector

PLASTIC_ROUGHNESS={
    'Orange polypropylene track':'track_roughness',
    'Blue molded risers and connectors':'riser_roughness',
    'Grey launcher housing':'launcher_roughness',
    'Yellow launcher button':'launcher_roughness',
}

def _principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')

def molded_finish(v):
    """Semi-gloss molded plastic: lower the remapped gloss range of the shared plastic shader."""
    changed={}
    for name,key in PLASTIC_ROUGHNESS.items():
        mat=bpy.data.materials.get(name)
        if mat is None:continue
        gloss=mat.node_tree.nodes.get('Map Range.004')
        lo,hi=v[key];gloss.inputs['To Min'].default_value=lo;gloss.inputs['To Max'].default_value=hi
        bs=_principled(mat);bs.inputs['Specular IOR Level'].default_value=v['plastic_specular_level']
        changed[name]=[lo,hi]
    return changed

def wool_rug(v):
    mat=bpy.data.materials.get('Woven wool rug')
    if mat is None:return None
    n=mat.node_tree.nodes;bs=_principled(mat)
    bs.inputs['Sheen Weight'].default_value=v['rug_sheen'];bs.inputs['Sheen Roughness'].default_value=.45
    bs.inputs['Sheen Tint'].default_value=(1.,.97,.9,1.)
    nor=next(x for x in n if x.type=='NORMAL_MAP');nor.inputs['Strength'].default_value=v['rug_normal']
    hue=next(x for x in n if x.type=='HUE_SAT');hue.inputs['Value'].default_value=v['rug_value']
    return {'sheen':v['rug_sheen'],'normal':v['rug_normal'],'value':v['rug_value']}

def daylight(scene,cfg):
    a=cfg['appearance']['lighting'];v=cfg['appearance']['daylight_finish']
    removed=[]
    for name in ['Weak ceiling bounce']:
        obj=bpy.data.objects.get(name)
        if obj is not None:
            data=obj.data;bpy.data.objects.remove(obj,do_unlink=True);bpy.data.lights.remove(data);removed.append(name)
    sun=bpy.data.objects['Direct sun through the side window']
    el=math.radians(a['sun_elevation_deg']);az=math.radians(v['sun_azimuth_deg'])
    # Azimuth is measured from the left-wall normal (+X travel) toward the back wall (+Y).
    direction=Vector((-math.cos(az),math.sin(az),math.tan(el))).normalized()
    sun.location=direction*6;q=(-direction).to_track_quat('-Z','Y');sun.rotation_mode='XYZ';sun.rotation_euler=q.to_euler()
    sun.data.color=tuple(v['sun_color'])
    return {'removed_hidden_lights':removed,'sun_direction_to_light':list(direction),'sun_energy':sun.data.energy,'sun_angle_deg':a['sun_angle_deg']}

def translucent_track(v):
    """Thin orange polypropylene passes some light: rails and lip edges glow slightly against the sun."""
    mat=bpy.data.materials.get('Orange polypropylene track')
    if mat is None:return None
    bs=_principled(mat);bs.inputs['Subsurface Weight'].default_value=v['track_subsurface']
    bs.inputs['Subsurface Radius'].default_value=(1.,.32,.08);bs.inputs['Subsurface Scale'].default_value=.003
    return {'subsurface_weight':v['track_subsurface'],'radius_m':[.003,.00096,.00024]}

def blank_roof_roundel(roots,v):
    """The source model's roof roundel carries a race number; paint the disc plain so the car shows no text."""
    body=roots.get('car_body') if roots else None
    if body is None:return None
    mats={slot.material for part in body.children_recursive for slot in getattr(part,'material_slots',[]) if slot.material and slot.material.use_nodes}
    mats={m for m in mats if m.name.startswith('Red painted die-cast toy')}
    cx,cy,r=v['roof_roundel_uv'];done=[]
    for mat in mats:
        n,l=mat.node_tree.nodes,mat.node_tree.links;bs=_principled(mat)
        if not bs.inputs['Base Color'].is_linked:continue
        src=bs.inputs['Base Color'].links[0].from_socket
        uv=n.new('ShaderNodeUVMap');uv.uv_map='Original asset UV'
        sub=n.new('ShaderNodeVectorMath');sub.operation='SUBTRACT';sub.inputs[1].default_value=(cx,cy,0.)
        length=n.new('ShaderNodeVectorMath');length.operation='LENGTH'
        mask=n.new('ShaderNodeMapRange');mask.clamp=True
        mask.inputs['From Min'].default_value=r;mask.inputs['From Max'].default_value=r-.003
        mix=n.new('ShaderNodeMixRGB');mix.blend_type='MIX';mix.inputs[2].default_value=(*v['roof_roundel_color'],1.)
        l.new(uv.outputs['UV'],sub.inputs[0]);l.new(sub.outputs[0],length.inputs[0]);l.new(length.outputs['Value'],mask.inputs['Value'])
        l.new(mask.outputs[0],mix.inputs[0]);l.new(src,mix.inputs[1]);l.new(mix.outputs[0],bs.inputs['Base Color'])
        done.append(mat.name)
    return {'materials':sorted(done),'uv_center_radius':[cx,cy,r]}

def plain_book_covers(v):
    """The scanned set has gilt titles on every spine: keep the recoloured cloth, drop the printed and embossed lettering."""
    done=0
    for mat in bpy.data.materials:
        if not mat.name.startswith('book_encyclopedia_set_01_cover') or not mat.use_nodes:continue
        n,l=mat.node_tree.nodes,mat.node_tree.links;bs=_principled(mat)
        if not bs.inputs['Base Color'].is_linked or bs.inputs['Base Color'].links[0].from_node.type!='MIX_RGB':continue
        mix=bs.inputs['Base Color'].links[0].from_node
        for link in list(mix.inputs[1].links):l.remove(link)
        g=v['book_cloth_value'];mix.inputs[1].default_value=(g,g,g,1.)
        for name,value in [('Metallic',0.),('Roughness',v['book_cloth_roughness'])]:
            for link in list(bs.inputs[name].links):l.remove(link)
            bs.inputs[name].default_value=value
        for link in list(bs.inputs['Normal'].links):l.remove(link)
        # Woven book cloth in place of the embossed title map.
        tc=n.new('ShaderNodeTexCoord');weave=n.new('ShaderNodeTexNoise');weave.inputs['Scale'].default_value=900.;weave.inputs['Detail'].default_value=2.
        bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.15;bump.inputs['Distance'].default_value=.0002
        l.new(tc.outputs['Object'],weave.inputs['Vector']);l.new(weave.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],bs.inputs['Normal'])
        done+=1
    return {'cover_materials':done}

def shelf_plant(v):
    """The wine bottle's printed label is replaced by a small scanned potted plant in the same shelf cell."""
    from look_toy_car_track_jump import append,place,bounds
    from pcve_assets import asset
    bottle=bpy.data.objects.get('wine_bottles_01_bordeaux')
    if bottle is None:return None
    low,high=bounds([bottle]);xy=((low.x+high.x)/2,(low.y+high.y)/2);z=low.z
    bpy.data.objects.remove(bottle,do_unlink=True)
    plant=append(asset('polyhaven/potted_plant_04/potted_plant_04_2k.blend'))
    info=place(plant,xy,z,v['plant_yaw_rad'])
    return {'removed':'wine_bottles_01_bordeaux','asset':'polyhaven/potted_plant_04',**info}

def finish_scene(scene,cfg,roots=None):
    v=cfg['appearance']['daylight_finish']
    ledger={'version':2}
    ledger['lighting']=daylight(scene,cfg)
    ledger['plastics']=molded_finish(v)
    ledger['track_translucency']=translucent_track(v)
    ledger['rug']=wool_rug(v)
    ledger['roof_roundel']=blank_roof_roundel(roots,v)
    ledger['books']=plain_book_covers(v)
    ledger['shelf_plant']=shelf_plant(v)
    return ledger
