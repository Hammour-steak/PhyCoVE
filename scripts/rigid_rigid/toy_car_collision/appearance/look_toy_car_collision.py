"""A sunlit child's playroom and independently tinted die-cast toy cars."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from scene_geometry import DIMENSIONS
from pcve_assets import asset as _pcve_asset
MODELS=_pcve_asset('')/'models'
POLYHAVEN=_pcve_asset('polyhaven/toy_car_collision')
CAR_ASSET='hotwheels_technetium__www.vecarz.com.glb'
RECEIVER_ASSET='cartoonish_toy_car.glb'
CAR_ASSETS=(CAR_ASSET,RECEIVER_ASSET)

# The room lines are the skirting faces. The cars roll along y = 0 from
# x = -0.49 to at most x = 1.56 (the receiver in edit_driver_speed_x3), so the
# walls stand 1.2 m and 0.7 m clear of the lane; the floor itself is the
# simulator's ground plane z = 0. The camera (scene_config) looks from the
# south-west corner towards the north-east one.
ROOM=dict(x=(-1.60,2.30),y=(-2.30,1.25),ceiling_m=2.60)

# Everything the simulator does not see. The west window is behind the left
# edge of the frame: the camera only sees the afternoon sun it lets in, a
# parallelogram of light across the boards, crossed by the shadows of the
# glazing bars. Its low sill (0.60 m) brings the near edge of that patch to
# x = -0.5, so both cars stay in the sunlight from the first frame. The north window's sill is above the top
# of the frame and lights the room with skylight only.
LOOK=dict(
    wall_color=(.40,.50,.52),
    # Poly Haven wood_floor: oak boards authored as a 1.7 m x 1.7 m patch.
    floor=dict(diffuse='wood_floor_diff_2k.jpg',tile_m=1.70,boards_along_x=True,roughness_min=.32),
    windows=[dict(wall='west',span=(-1.05,.35),z=(.60,2.20)),
             dict(wall='north',span=(.95,2.05),z=(1.05,2.25))],
    sockets=[dict(wall='north',at=(.86,.30)),dict(wall='east',at=(-.25,.30))],
    daylight=dict(sun_window='west',sun_elevation_deg=30.,sun_heading_deg=12.,sun_energy=3.5,sky_strength=.9),
    # Poly Haven models face -y; yaw turns them about z, and each bounding box
    # is set on its anchor (x/y centre, *_min/*_max faces), standing on the floor.
    furniture=[
        dict(model='painted_wooden_cabinet',name='Toy cupboard',x=0.,y_max=1.248),
        dict(model='wicker_basket_02',name='Wicker basket',yaw_deg=-15.,x=.80,y_max=1.21),
        dict(model='SchoolDesk_01',name='Homework desk',yaw_deg=-90.,x_max=2.296,y=.86),
        dict(model='painted_wooden_chair_01',name='Desk chair',yaw_deg=90.,x_max=1.72,y=.84),
        dict(model='wooden_stool_02',name='Footstool',yaw_deg=70.,x=-.30,y=.47),
        dict(model='baseball_01',name='Baseball',x=.22,y=.46),
        # Leaning on the east wall: tipped 15 deg back, then turned to face the room.
        dict(model='Ukulele_01',name='Ukulele',tilt_deg=(-15.,0.),yaw_deg=-90.,x_max=2.312,y=-.20),
    ])


def build_environment(bpy,scene):
    from kids_room import build_room
    return build_room(ROOM,LOOK,POLYHAVEN)

def make_cars(bpy,present):
    from asset_import import import_car
    objects={};wheels={}
    for i,key in enumerate(('car_a','car_b')):
        if not present[i]:continue
        root,spin=import_car(MODELS/CAR_ASSETS[i],key,1,DIMENSIONS[i][0])
        physics=bpy.data.objects.new(key+'_physics',None);bpy.context.collection.objects.link(physics)
        root.parent=physics;root.rotation_mode='XYZ';root.rotation_euler=(0,0,math.pi/2)
        for part in root.children_recursive:
            if part.type!='MESH':continue
            for slot in part.material_slots:
                m=slot.material
                if not m:continue
                if i==1:
                    if m.use_nodes:
                        shader=m.node_tree.nodes.get('Principled BSDF')
                        if shader and 'Material.002' in m.name:
                            shader.inputs['Base Color'].default_value=(.025,.22,.31,1)
                            shader.inputs['Roughness'].default_value=.3
                            if shader.inputs.get('Coat Weight'):shader.inputs['Coat Weight'].default_value=.35
                    continue
                if 'Livery' not in m.name:continue
                mat=m.copy();mat.name=key+'_paint';slot.material=mat
                n=mat.node_tree.nodes;l=mat.node_tree.links;bs=n.get('Principled BSDF');base=bs.inputs['Base Color'];links=list(base.links)
                if links:
                    source=links[0].from_socket;l.remove(links[0]);mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY'
                    mix.inputs[0].default_value=.78;mix.inputs[2].default_value=((.95,.15,.045,1) if i==0 else (.07,.36,.95,1))
                    l.new(source,mix.inputs[1]);l.new(mix.outputs[0],base)
                bs.inputs['Metallic'].default_value=.72;bs.inputs['Roughness'].default_value=.24
                if bs.inputs.get('Coat Weight'):bs.inputs['Coat Weight'].default_value=.35
        objects[key]=physics;wheels[key]=spin
    return objects,wheels
