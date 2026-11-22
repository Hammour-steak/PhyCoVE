"""Late-afternoon sun through the real casement; appearance only, SI metres.

The sun is a distant source whose rays pass through the existing 3D window
opening, curtains and glazing bars. Thin parallel glass is transparent to shadow
rays (no refractive offset at 3 mm) while camera rays still refract. Physics,
camera pose and every solved sample are unchanged.
"""
import math
from pathlib import Path
import bpy
from mathutils import Vector
from look_domino_chain import set_socket
from natural_card_table import node_noise, mapped
ROOT=Path(__file__).resolve().parents[4]
REVISION='afternoon_sun'


def sun_direction(sun):
    # Azimuth is measured from +Y (towards the window) to -X; vector points to the sun.
    a,e=math.radians(sun['azimuth_deg']),math.radians(sun['elevation_deg'])
    return Vector((-math.sin(a)*math.cos(e),math.cos(a)*math.cos(e),math.sin(e)))


def add_sun(cfg):
    sun=cfg['sun'];d=sun_direction(sun)
    data=bpy.data.lights.new('Late afternoon sun',type='SUN')
    data.energy=sun['strength_w_m2'];data.angle=math.radians(sun['angle_deg']);data.color=sun['color_linear']
    obj=bpy.data.objects.new('Late afternoon sun through casement',data);bpy.context.collection.objects.link(obj)
    obj.rotation_mode='QUATERNION';obj.rotation_quaternion=d.to_track_quat('Z','Y')
    return obj,d


def unlit_identity_labels(sun):
    # The D0x print sits 6 um off the -Y face, which never faces the sun. At an
    # 18 deg grazing sun the occluding resin is so close that Cycles' shadow test
    # flips with 1e-16 m pose noise, so the label flashed lit. Exclude it from
    # direct sun; bounce light still reaches it.
    labels=[o for o in bpy.data.objects if o.name.endswith('_identity')]
    if not labels:return []
    coll=bpy.data.collections.new('Sun receivers | identity labels excluded')
    for o in labels:coll.objects.link(o)
    sun.light_linking.receiver_collection=coll
    for co in coll.collection_objects:co.light_linking.link_state='EXCLUDE'
    return [o.name for o in labels]


def shadow_transparent_glass():
    # A 3 mm parallel slab transmits ~92 % with negligible lateral offset.
    names=[]
    for mat in bpy.data.materials:
        if not mat.name.startswith('Window | 3 mm clear soda lime glass'):continue
        n=mat.node_tree.nodes;l=mat.node_tree.links
        out=next(x for x in n if x.bl_idname=='ShaderNodeOutputMaterial');surface=out.inputs['Surface'].links[0].from_socket
        path=n.new('ShaderNodeLightPath');clear=n.new('ShaderNodeBsdfTransparent');clear.inputs['Color'].default_value=(.92,.93,.92,1)
        mix=n.new('ShaderNodeMixShader');l.new(path.outputs['Is Shadow Ray'],mix.inputs['Fac'])
        l.new(surface,mix.inputs[1]);l.new(clear.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],out.inputs['Surface'])
        names.append(mat.name)
    return names


def sunny_exterior(cfg,d):
    ext=bpy.data.objects['Natural window | distant exterior hemisphere'];ext.visible_shadow=False
    mat=ext.data.materials[0];n=mat.node_tree.nodes;l=mat.node_tree.links
    env=next(x for x in n if x.bl_idname=='ShaderNodeTexEnvironment')
    env.image=bpy.data.images.load(str(ROOT/cfg['exterior_asset']),check_existing=True)
    # Rotate the photograph so its sun azimuth matches the analytic sun.
    u=cfg['exterior_sun_u'];hdr_az=math.pi-2*math.pi*u;want=math.atan2(d.y,-d.x)
    rot=next(x for x in n if x.bl_idname=='ShaderNodeVectorRotate');rot.inputs['Angle'].default_value=hdr_az-want
    # The analytic lamp already carries the direct sun; clip the photographed disc.
    clip=n.new('ShaderNodeVectorMath');clip.operation='MINIMUM';clip.inputs[1].default_value=(cfg['exterior_clip'],)*3
    emission=next(x for x in n if x.bl_idname=='ShaderNodeEmission')
    l.new(env.outputs['Color'],clip.inputs[0]);l.new(clip.outputs[0],emission.inputs['Color'])
    emission.inputs['Strength'].default_value=cfg['exterior_strength']
    return math.degrees(hdr_az-want)


def clean_resin(cfg):
    mat=bpy.data.materials.get('Handled ivory resin - daylight satin')
    if mat is None:return None
    n=mat.node_tree.nodes;bs=n.get('Principled BSDF')
    set_socket(bs,'Coat Weight',cfg['coat_weight']);set_socket(bs,'Coat Roughness',cfg['coat_roughness'])
    for node in n:
        # Broad 5 mm tonal blotching read as dirt; keep a faint cast only.
        if node.bl_idname=='ShaderNodeMapRange' and abs(node.inputs['To Min'].default_value-.93)<1e-6:
            node.inputs['To Min'].default_value,node.inputs['To Max'].default_value=cfg['tone_range']
        # Sub-pixel polish/scratch variance only feeds the denoiser at 720p.
        if node.bl_idname=='ShaderNodeMapRange' and abs(node.inputs['To Min'].default_value-.205)<1e-6:
            node.inputs['To Min'].default_value,node.inputs['To Max'].default_value=cfg['roughness_range']
        if node.bl_idname=='ShaderNodeMapRange' and abs(node.inputs['To Max'].default_value-.075)<1e-6:
            node.inputs['To Max'].default_value=cfg['scratch_roughness']
        if node.bl_idname=='ShaderNodeBump':node.inputs['Strength'].default_value=cfg['grain_bump_strength']
    return mat.name


def mottled_felt(cfg):
    mat=bpy.data.materials.get('Pressed green wool baize - subtle photo fibres')
    if mat is None:return None
    n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF')
    base=bs.inputs['Base Color'].links[0].from_socket
    pos=n.new('ShaderNodeNewGeometry')
    # Pressed wool is never one flat dye lot: decimetre mottle plus faint nap streaks.
    broad=node_noise(n,l,pos.outputs['Position'],cfg['mottle_scale_per_m'],3)
    stretch=n.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY';stretch.inputs[1].default_value=(6,90,1)
    l.new(pos.outputs['Position'],stretch.inputs[0]);nap=node_noise(n,l,stretch.outputs['Vector'],1,2)
    a=mapped(n,l,broad.outputs['Fac'],*cfg['mottle_range'],.3,.7);b=mapped(n,l,nap.outputs['Fac'],*cfg['nap_range'],.3,.7)
    m=n.new('ShaderNodeMath');m.operation='MULTIPLY';l.new(a,m.inputs[0]);l.new(b,m.inputs[1])
    mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1
    l.new(base,mix.inputs[1]);l.new(m.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],bs.inputs['Base Color'])
    # Wool fibres scatter diffusely: weak Fresnel gloss, a soft fuzz sheen.
    set_socket(bs,'Sheen Weight',cfg['sheen_weight']);set_socket(bs,'Sheen Roughness',cfg['sheen_roughness'])
    set_socket(bs,'Specular IOR Level',cfg['specular_level'])
    for node in n:
        if node.bl_idname=='ShaderNodeMapRange' and abs(node.inputs['To Min'].default_value-.87)<1e-6:
            node.inputs['To Min'].default_value,node.inputs['To Max'].default_value=cfg['roughness_range']
        if node.bl_idname=='ShaderNodeBump':node.inputs['Strength'].default_value=cfg['fibre_bump_strength']
    return mat.name


def enclose_room(cfg):
    # Without a ceiling and the off-camera walls, sunlight bounced by the table
    # and floor escapes; a real room returns it as warm indirect light.
    if not cfg:return []
    from look_domino_chain import box
    wall=bpy.data.materials['Soft warm home dining room plaster'];made=[]
    back=bpy.data.objects['Room window wall | above'];y=back.location.y;h=cfg['ceiling_height_m']
    xr,yf=cfg['right_wall_x_m'],cfg['front_wall_y_m']
    ceiling=bpy.data.materials.new('Matte white ceiling paint');ceiling.use_nodes=True
    ceiling.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=cfg['ceiling_color_linear']
    ceiling.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.92
    for name,loc,dims,mat in [('ceiling',((xr-3.1)/2,(y+yf)/2,h+.05),(xr+3.1,y-yf+.2,.1),ceiling),
                              ('right wall',(xr+.06,(y+yf)/2,h/2),(.12,y-yf,h),wall),
                              ('front wall behind camera',((xr-3.1)/2,yf-.06,h/2),(xr+3.1,.12,h),wall)]:
        o=box('Enclosed room | '+name,loc,dims,mat,.001);o['static_decorative_prop']=True;made.append(o.name)
    return made


def append_asset(path,names):
    with bpy.data.libraries.load(str(ROOT/path),link=False) as (source,target):target.objects=list(names)
    objs=[o for o in target.objects if o]
    for o in objs:bpy.context.collection.objects.link(o);o['static_decorative_prop']=True;o['source_asset']=path
    bpy.context.view_layer.update();return objs


def place(objs,anchor,align):
    # Rigid translation (real-scale CC0 assets): bottom/back of the bounds onto `anchor`.
    pts=[o.matrix_world@Vector(c) for o in objs for c in o.bound_box]
    lo=Vector([min(p[k] for p in pts) for k in range(3)]);hi=Vector([max(p[k] for p in pts) for k in range(3)])
    ref=Vector(((lo.x+hi.x)/2,hi.y if align=='back' else (lo.y+hi.y)/2,lo.z if align=='bottom' else (lo.z+hi.z)/2))
    roots=[o for o in objs if o.parent not in objs]
    for o in roots:o.location+=Vector(anchor)-ref
    bpy.context.view_layer.update();pts=[o.matrix_world@Vector(c) for o in objs for c in o.bound_box]
    return [[min(p[k] for p in pts) for k in range(3)],[max(p[k] for p in pts) for k in range(3)]]


def room_props(cfg):
    out={}
    for row in cfg or []:
        objs=append_asset(row['asset'],row['objects'])
        for o in objs:
            if o.parent not in objs:o.rotation_euler.z+=math.radians(row.get('yaw_deg',0))
        bpy.context.view_layer.update()
        out[row['asset']]={'objects':[o.name for o in objs],'world_bounds_m':place(objs,row['anchor_m'],row['align'])}
    return out


def apply_realism(cfg,ledger):
    rc=cfg['appearance'].get('realism') or {}
    if rc.get('revision')!=REVISION:return ledger
    sun,d=add_sun(rc);enclosure=enclose_room(rc.get('enclosure'));props=room_props(rc.get('props'))
    glass=shadow_transparent_glass()
    unlit=unlit_identity_labels(sun)
    rotation=sunny_exterior(rc['exterior'],d)
    key=bpy.data.objects['Single soft rectangular daylight window'];key.data.energy*=rc['key_area_scale']
    fill=bpy.data.objects['Soft fill through linen privacy window'];fill.data.energy*=rc['window_fill_scale']
    bpy.context.scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value*=rc['world_scale']
    bpy.context.scene.view_settings.exposure=rc['exposure_ev']
    return {**ledger,'realism_revision':rc['revision'],'sun_excluded_receivers':unlit,'sun_direction_to_sun':list(d),'sun':rc['sun'],
            'shadow_transparent_glass_materials':glass,'enclosure_objects':enclosure,'room_props':props,'exterior_asset':rc['exterior']['exterior_asset'],
            'exterior_rotation_deg':rotation,'resin_material':clean_resin(rc['resin']),'felt_material':mottled_felt(rc['felt']),
            'key_area_power_w':key.data.energy,'window_fill_power_w':fill.data.energy,'exposure_ev':rc['exposure_ev'],
            'realism_note':'Appearance only: analytic sun through the existing 3D opening, shadow-transparent thin glazing, sunlit exterior, cleaner resin and mottled baize. Physics and camera pose unchanged.'}
