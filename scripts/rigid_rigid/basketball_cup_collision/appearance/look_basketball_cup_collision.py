"""Studio flat (appearance/studio_room.py), powder-coated steel bottle, leather ball."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from scene_geometry import COM_HEIGHT,BALL_RADIUS,BOTTLE_ASSET,BOTTLE_DATA
MODELS=_pcve_asset('models')
# Poly Haven CC0 furniture, textures and window view of this scene's room.
ROOM_ASSETS=_pcve_asset('polyhaven')/'basketball_cup_collision'
BALL_ASSET='basketball.glb'
# Interior daylight exposure under AgX (the sun patch on the floor sits about
# two stops over the shaded wall, as a phone camera would expose the room).
EXPOSURE=1.5
LOOK='AgX - Base Contrast'

# The bottle's body texture carries a printed brand name; the body is shaded
# instead as a plain powder-coated steel vacuum bottle (the 0.45 kg the
# simulator gives it is the weight of an empty insulated steel bottle this
# size). The lid's matte black plastic and the chrome collar stay as authored.
BOTTLE_BODY_MATERIAL='02_-_Default'
BOTTLE_COAT=(.045,.15,.135)

# basketball.glb's leather map carries a league logo and a maker's wordmark.
# Each patch is a box in the map's UV space (u0, u1, v0, v1; Blender's UV origin
# is the bottom-left of the image) and the UV offset of a clean stretch of the
# same leather to show there instead: the league logo takes the leather 70 px
# further along its own panel, the wordmark the same place on the neighbouring
# panel of the same shape (154 px over).
BALL_LOGO_PATCHES=(((.7764,.8721,.7363,.7891),(0.,-.0684)),
                   ((.6328,.7324,.1250,.3477),(.1504,0.)))
BALL_LOGO_FEATHER=.006


def bake_asset(bpy,name):
    """Import a GLB, strip animation, return world-baked mesh copies."""
    old=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(MODELS/name))
    imported=[o for o in bpy.data.objects if o not in old]
    for o in imported:o.animation_data_clear()
    bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get();result=[]
    for o in imported:
        if o.type!='MESH':continue
        mesh=bpy.data.meshes.new_from_object(o.evaluated_get(deps),preserve_all_data_layers=True,depsgraph=deps)
        mesh.transform(o.matrix_world);ob=bpy.data.objects.new(o.name+'_baked',mesh)
        bpy.context.collection.objects.link(ob);result.append(ob)
    for o in imported:bpy.data.objects.remove(o,do_unlink=True)
    return result


def bounds(parts):
    from mathutils import Vector
    pts=[v.co for o in parts for v in o.data.vertices]
    return Vector([min(v[i] for v in pts) for i in range(3)]),Vector([max(v[i] for v in pts) for i in range(3)])


def join(bpy,parts,name):
    bpy.ops.object.select_all(action='DESELECT')
    for o in parts:o.select_set(True)
    bpy.context.view_layer.objects.active=parts[0]
    if len(parts)>1:bpy.ops.object.join()
    o=bpy.context.object;o.name=name;return o


def powder_coat(bpy):
    """Satin powder coat over steel: a paint, so dielectric, with orange peel."""
    m=bpy.data.materials.new('Powder-coated steel bottle');m.use_nodes=True
    n=m.node_tree.nodes;l=m.node_tree.links;bs=n.get('Principled BSDF')
    bs.inputs['Base Color'].default_value=(*BOTTLE_COAT,1);bs.inputs['Roughness'].default_value=.46
    bs.inputs['Metallic'].default_value=0.
    coord=n.new('ShaderNodeTexCoord');peel=n.new('ShaderNodeTexNoise');peel.inputs['Scale'].default_value=900.
    peel.inputs['Detail'].default_value=2.;l.new(coord.outputs['Object'],peel.inputs['Vector'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12;bump.inputs['Distance'].default_value=.00015
    l.new(peel.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],bs.inputs['Normal'])
    return m


def make_bottle(bpy):
    """Bottle asset scaled to the collider's exact size, origin at its COM.

    Same transform chain as the bottle_collision.json export: uniform scale,
    base centred on the xy axes, then shifted so the mesh origin sits on the
    centre of mass the physics body animates around.
    """
    from mathutils import Vector,Matrix
    parts=bake_asset(bpy,BOTTLE_ASSET)
    o=join(bpy,parts,'bottle')
    lo,hi=bounds([o])
    center=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,lo.z))
    o.data.transform(Matrix.Scale(BOTTLE_DATA['scale'],4)@Matrix.Translation(-center))
    for v in o.data.vertices:v.co.z-=COM_HEIGHT
    for poly in o.data.polygons:poly.use_smooth=True
    coat=powder_coat(bpy)
    for slot in o.material_slots:
        if slot.material and slot.material.name.split('.')[0]==BOTTLE_BODY_MATERIAL:
            slot.material=coat
    for mat in o.data.materials:
        if not mat or not mat.use_nodes or mat is coat:continue
        bs=mat.node_tree.nodes.get('Principled BSDF')
        if bs and not bs.inputs['Roughness'].is_linked:
            # Lid plastic and chrome collar as authored, roughness floored so
            # the chrome stays crisp but never mirror-harsh.
            bs.inputs['Roughness'].default_value=max(.2,min(.75,bs.inputs['Roughness'].default_value))
    if not any(slot.material is coat for slot in o.material_slots):
        raise ValueError(f'{BOTTLE_ASSET}: no {BOTTLE_BODY_MATERIAL} body material to replace')
    o['contents']='empty bottle';o['has_liquid']=False
    return o


def _remove_ball_logos(bpy,mat):
    """Show clean leather over the logo patches of every map of the ball.

    Each image node is sampled a second time at its UV shifted by the patch
    offset, and the two samples are blended by a feathered mask, so colour,
    roughness and normal all lose the print together.
    """
    n=mat.node_tree.nodes;l=mat.node_tree.links
    images=[x for x in n if x.type=='TEX_IMAGE']
    uv=n.new('ShaderNodeUVMap');sep=n.new('ShaderNodeSeparateXYZ');l.new(uv.outputs['UV'],sep.inputs['Vector'])
    def math(op,a,b):
        m=n.new('ShaderNodeMath');m.operation=op;m.use_clamp=op in ('MULTIPLY_ADD',)
        for i,v in enumerate((a,b)):
            if isinstance(v,(int,float)):m.inputs[i].default_value=v
            else:l.new(v,m.inputs[i])
        return m.outputs[0]
    def ramp(value,edge,sign):
        # 1 inside the box edge, falling to 0 one feather outside it.
        m=n.new('ShaderNodeMapRange');m.clamp=True
        l.new(value,m.inputs['Value'])
        m.inputs['From Min'].default_value=edge-sign*BALL_LOGO_FEATHER;m.inputs['From Max'].default_value=edge
        return m.outputs['Result']
    mask_total=None;offset=None
    for (u0,u1,v0,v1),(du,dv) in BALL_LOGO_PATCHES:
        mask=math('MULTIPLY',math('MULTIPLY',ramp(sep.outputs['X'],u0,1),ramp(sep.outputs['X'],u1,-1)),
                  math('MULTIPLY',ramp(sep.outputs['Y'],v0,1),ramp(sep.outputs['Y'],v1,-1)))
        inside=math('CEIL',mask,0.)
        shift=n.new('ShaderNodeCombineXYZ');l.new(math('MULTIPLY',inside,du),shift.inputs['X']);l.new(math('MULTIPLY',inside,dv),shift.inputs['Y'])
        mask_total=mask if mask_total is None else math('ADD',mask_total,mask)
        if offset is None:offset=shift.outputs['Vector']
        else:
            add=n.new('ShaderNodeVectorMath');add.operation='ADD';l.new(offset,add.inputs[0]);l.new(shift.outputs['Vector'],add.inputs[1]);offset=add.outputs['Vector']
    moved=n.new('ShaderNodeVectorMath');moved.operation='ADD';l.new(uv.outputs['UV'],moved.inputs[0]);l.new(offset,moved.inputs[1])
    for image in images:
        twin=n.new('ShaderNodeTexImage');twin.image=image.image;twin.interpolation=image.interpolation;twin.extension=image.extension
        l.new(uv.outputs['UV'],image.inputs['Vector']);l.new(moved.outputs['Vector'],twin.inputs['Vector'])
        for out_name in ('Color','Alpha'):
            targets=[link.to_socket for link in image.outputs[out_name].links]
            if not targets:continue
            mix=n.new('ShaderNodeMix');mix.data_type='RGBA' if out_name=='Color' else 'FLOAT'
            l.new(mask_total,mix.inputs['Factor'])
            # ShaderNodeMix sockets: float A/B are inputs 2/3 (result 0),
            # colour A/B are inputs 6/7 (result 2).
            a,b=(mix.inputs[6],mix.inputs[7]) if out_name=='Color' else (mix.inputs[2],mix.inputs[3])
            l.new(image.outputs[out_name],a);l.new(twin.outputs[out_name],b)
            result=mix.outputs[2] if out_name=='Color' else mix.outputs[0]
            for socket in targets:l.new(result,socket)


def make_ball(bpy):
    """basketball.glb on the physical sphere, its leather without print.

    The library ball is a 400-vertex sphere whose outline turns polygonal at
    this size: it is subdivided and every vertex put back on the collision
    radius, so the silhouette is the PyBullet sphere itself.
    """
    parts=bake_asset(bpy,BALL_ASSET);lo,hi=bounds(parts);center=(lo+hi)/2
    radius=max((v.co-center).length for o in parts for v in o.data.vertices)
    for o in parts:
        for v in o.data.vertices:v.co=(v.co-center)*(BALL_RADIUS/radius)
    ball=join(bpy,parts,'basketball')
    smooth=ball.modifiers.new('Round outline','SUBSURF');smooth.levels=smooth.render_levels=2
    bpy.context.view_layer.objects.active=ball;bpy.ops.object.modifier_apply(modifier=smooth.name)
    for v in ball.data.vertices:v.co=v.co.normalized()*BALL_RADIUS
    for poly in ball.data.polygons:poly.use_smooth=True
    for mat in ball.data.materials:
        if not mat or not mat.use_nodes:continue
        _remove_ball_logos(bpy,mat)
        n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF')
        # Pebbled rubber-leather: never metallic; the scanned roughness map is
        # kept but held in the satin range a used ball has.
        for link in list(bs.inputs['Metallic'].links):l.remove(link)
        bs.inputs['Metallic'].default_value=0.
        if bs.inputs['Roughness'].is_linked:
            src=bs.inputs['Roughness'].links[0].from_socket
            rng=n.new('ShaderNodeMapRange');rng.clamp=True;rng.inputs['To Min'].default_value=.55;rng.inputs['To Max'].default_value=.85
            l.new(src,rng.inputs['Value']);l.new(rng.outputs['Result'],bs.inputs['Roughness'])
        else:
            bs.inputs['Roughness'].default_value=.68
        bs.inputs['Emission Strength'].default_value=0.
    return ball


def make_objects(bpy):
    bottle=make_bottle(bpy);result={'bottle':bottle}
    result['basketball']=make_ball(bpy)
    return result


def build_environment(bpy,scene):
    """The studio around the desk; see appearance/studio_room.py."""
    import studio_room
    return studio_room.build_room(ROOM_ASSETS)


def check_scene(bpy,scene,camera,room,data,objects):
    """Clearance and line of sight between the decoration and the moving bodies."""
    import studio_room
    keys=[k for k in ('basketball','bottle') if data['objects'][k]['present']]
    clearance=studio_room.check_clearance(room['decor'],data['frames'],keys,BOTTLE_DATA['vertices'],BALL_RADIUS)
    occlusion=studio_room.check_occlusion(scene,camera,room['decor'],data['frames'],
                                          {k:objects[k] for k in keys},BALL_RADIUS)
    return {'clearance_m':clearance,'occlusion':occlusion}
