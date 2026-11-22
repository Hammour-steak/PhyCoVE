"""Physically sized beverage cans in a built farmhouse kitchen lit by a low sun."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
from pcve_assets import asset as _pcve_asset
from kitchen_room import TEXTURES

MODELS=_pcve_asset('')/'models'
CAN_MODEL=MODELS/'pepsi_tin_with_texture.glb'


def used_assets():
    """Every asset file the render reads, by registry name."""
    return {'models/pepsi_tin_with_texture.glb':str(CAN_MODEL.resolve()),
            'polyhaven/kitchen_can_collision':str(TEXTURES.resolve())}


def make_cans(bpy):
    from mathutils import Matrix,Vector
    from scene_geometry import HEIGHT,RADIUS
    previous=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(CAN_MODEL))
    imported=[o for o in bpy.data.objects if o not in previous]
    meshes=[o for o in imported if o.type=='MESH']
    bpy.context.view_layer.update()
    # Actual vertices, rather than rotated bounding boxes, define the cylinder.
    points=[o.matrix_world@v.co for o in meshes for v in o.data.vertices]
    lo=Vector([min(p[i] for p in points) for i in range(3)])
    hi=Vector([max(p[i] for p in points) for i in range(3)])
    center=(lo+hi)/2
    transform=Matrix.Diagonal((2*RADIUS/(hi.x-lo.x),2*RADIUS/(hi.y-lo.y),HEIGHT/(hi.z-lo.z),1))@Matrix.Translation(-center)
    for o in meshes:
        mat=o.matrix_world.copy();o.parent=None;o.data=o.data.copy()
        o.data.transform(transform@mat);o.matrix_world=Matrix.Identity(4)
        for poly in o.data.polygons:poly.use_smooth=True
        for m in o.data.materials:
            if not m or not m.use_nodes:continue
            bs=m.node_tree.nodes.get('Principled BSDF')
            if bs:
                has_label=any(n.type=='TEX_IMAGE' for n in m.node_tree.nodes)
                bs.inputs['Metallic'].default_value=.5 if has_label else .88
                bs.inputs['Roughness'].default_value=.29 if has_label else .22
    for o in imported:
        if o.type!='MESH':bpy.data.objects.remove(o,do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:o.select_set(True)
    bpy.context.view_layer.objects.active=meshes[0];bpy.ops.object.join()
    original=bpy.context.object;original.name='Rolling Pepsi can'
    duplicate=original.copy();duplicate.data=original.data.copy();duplicate.name='Upright Pepsi can'
    bpy.context.collection.objects.link(duplicate)
    return {'rolling_can':original,'upright_can':duplicate}


def build_environment(bpy,scene):
    """The kitchen and everything standing in it; returns a description of both."""
    from kitchen_room import build_kitchen
    from tabletop_props import add_tabletop_props
    room=build_kitchen(scene)
    room['props']=[p['object_name'] for p in add_tabletop_props()]
    return room
