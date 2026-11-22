"""Glazed stoneware dishes at their simulated size in a city kitchen at night."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from scene_geometry import PROFILE,COM_HEIGHT
from city_kitchen import TEXTURES,SHELF_TOPS,ROOM_Y



def used_assets():
    """Every asset file the render reads, by registry name."""
    return {'polyhaven/kitchen_tableware_collision':str(TEXTURES.resolve())}


def _nodes(mat):
    return mat.node_tree.nodes,mat.node_tree.links


def glaze(bpy,name,color,pool,rough=.06,speckle=None):
    """A glossy stoneware glaze over clay.

    The glass of the glaze is the clear coat; under it the colour drifts a
    little over the dish and darkens where the glaze runs thick -- in the well
    and down at the foot -- the way a dipped glaze pools. ``speckle`` adds the
    iron spots of a reduction-fired stoneware body showing through.
    """
    mat=bpy.data.materials.new(name);mat.use_nodes=True;mat.diffuse_color=(*color,1)
    nodes,links=_nodes(mat);bsdf=nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value=.32
    bsdf.inputs['Coat Weight'].default_value=1.
    bsdf.inputs['Coat Roughness'].default_value=rough
    bsdf.inputs['Coat IOR'].default_value=1.52
    coord=nodes.new('ShaderNodeTexCoord')
    xyz=nodes.new('ShaderNodeSeparateXYZ');links.new(coord.outputs['Object'],xyz.inputs['Vector'])
    radius=nodes.new('ShaderNodeVectorMath');radius.operation='LENGTH'
    flat=nodes.new('ShaderNodeCombineXYZ');links.new(xyz.outputs['X'],flat.inputs['X']);links.new(xyz.outputs['Y'],flat.inputs['Y'])
    links.new(flat.outputs['Vector'],radius.inputs[0])
    # Thick glaze: inside the well (r < 0.06 m) and on the lower outside wall.
    thick=nodes.new('ShaderNodeMapRange')
    links.new(radius.outputs['Value'],thick.inputs['Value'])
    thick.inputs['From Min'].default_value,thick.inputs['From Max'].default_value=.075,.04
    tone=nodes.new('ShaderNodeMix');tone.data_type='RGBA'
    links.new(thick.outputs['Result'],tone.inputs['Factor'])
    tone.inputs['A'].default_value=(*color,1);tone.inputs['B'].default_value=(*pool,1)
    drift=nodes.new('ShaderNodeTexNoise');drift.inputs['Scale'].default_value=18.;drift.inputs['Detail'].default_value=4.
    links.new(coord.outputs['Object'],drift.inputs['Vector'])
    vary=nodes.new('ShaderNodeMapRange');links.new(drift.outputs['Fac'],vary.inputs['Value'])
    vary.inputs['To Min'].default_value,vary.inputs['To Max'].default_value=.92,1.06
    shade=nodes.new('ShaderNodeVectorMath');shade.operation='SCALE'
    links.new(tone.outputs['Result'],shade.inputs[0]);links.new(vary.outputs['Result'],shade.inputs['Scale'])
    colour=shade.outputs['Vector']
    if speckle:
        spots=nodes.new('ShaderNodeTexVoronoi');spots.inputs['Scale'].default_value=240.
        links.new(coord.outputs['Object'],spots.inputs['Vector'])
        mask=nodes.new('ShaderNodeMapRange');links.new(spots.outputs['Distance'],mask.inputs['Value'])
        mask.inputs['From Min'].default_value,mask.inputs['From Max'].default_value=.10,.16
        mix=nodes.new('ShaderNodeMix');mix.data_type='RGBA'
        links.new(mask.outputs['Result'],mix.inputs['Factor'])
        mix.inputs['A'].default_value=(*speckle,1);links.new(colour,mix.inputs['B'])
        colour=mix.outputs['Result']
    links.new(colour,bsdf.inputs['Base Color'])
    # The glaze surface is not machined: a faint orange-peel ripple in the coat.
    ripple=nodes.new('ShaderNodeTexNoise');ripple.inputs['Scale'].default_value=420.;ripple.inputs['Detail'].default_value=2.
    links.new(coord.outputs['Object'],ripple.inputs['Vector'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.06;bump.inputs['Distance'].default_value=.0001
    links.new(ripple.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs['Normal'],bsdf.inputs['Coat Normal'])
    return mat


def bisque(bpy,name,color):
    """Unglazed fired clay of the foot ring: matt, slightly gritty."""
    mat=bpy.data.materials.new(name);mat.use_nodes=True;mat.diffuse_color=(*color,1)
    nodes,links=_nodes(mat);bsdf=nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value=(*color,1);bsdf.inputs['Roughness'].default_value=.82
    grit=nodes.new('ShaderNodeTexNoise');grit.inputs['Scale'].default_value=900.
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.25;bump.inputs['Distance'].default_value=.0002
    links.new(grit.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
    return mat


def lathe(bpy,name,profile,mats,segments=160):
    verts=[(r*math.cos(i*2*math.pi/segments),r*math.sin(i*2*math.pi/segments),z) for r,z in profile for i in range(segments)]
    faces=[]
    for j in range(len(profile)-1):
        for i in range(segments):
            a=j*segments+i;b=j*segments+(i+1)%segments
            faces.append((a,b,b+segments,a+segments))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o)
    for m in mats:o.data.materials.append(m)
    for p in mesh.polygons:p.use_smooth=True
    return o


def dish_materials(bpy):
    """Longquan-style celadon and an ivory stoneware glaze, each with its bare foot."""
    celadon=glaze(bpy,'A - celadon glazed stoneware',(.205,.330,.270),(.120,.215,.175))
    ivory=glaze(bpy,'B - ivory glazed stoneware',(.640,.585,.470),(.560,.500,.385),speckle=(.20,.15,.10))
    return dict(celadon=(celadon,bisque(bpy,'A - iron-red unglazed foot',(.30,.15,.08))),
                ivory=(ivory,bisque(bpy,'B - buff unglazed foot',(.47,.38,.27))))


def dish(bpy,name,glaze_mat,foot_mat):
    """One dish on the shared lathe profile, origin at its centre of mass;
    only the foot ring's ground face is unglazed."""
    o=lathe(bpy,name,[(r,z-COM_HEIGHT) for r,z in PROFILE],(glaze_mat,foot_mat))
    for p in o.data.polygons:
        if p.center.z < .003-COM_HEIGHT:p.material_index=1
    return o


def make_dishes(bpy):
    mats=dish_materials(bpy)
    return {'bowl_a':dish(bpy,'Celadon shallow bowl A',*mats['celadon']),
            'bowl_b':dish(bpy,'Ivory shallow bowl B',*mats['ivory'])}


# Plates and the rest of the set on the lower walnut shelf: (glaze, x, count).
SHELF_STACKS=[('ivory',-2.15,4),('celadon',-1.80,3)]
PLATE_PROFILE=((0.,.003),(.045,.003),(.050,0.),(.056,0.),(.058,.004),(.085,.010),(.118,.018),(.128,.021),
               (.129,.024),(.126,.024),(.116,.020),(.083,.012),(.056,.009),(0.,.009))


def shelf_stacks(bpy):
    """The rest of the set at home on the lower shelf: dinner plates and two
    more of the shallow bowls, stacked as they nest."""
    mats=dish_materials(bpy)
    records=[]
    z0=SHELF_TOPS[0]
    y=ROOM_Y[1]-.135
    for glaze_name,x,count in SHELF_STACKS:
        g,f=mats[glaze_name]
        plates=glaze_name=='ivory'
        for k in range(count):
            if plates:
                o=lathe(bpy,f'Shelf plate {k+1}',PLATE_PROFILE,(g,f),96);pitch=.0091
                o.location=(x,y,z0+k*pitch)
            else:
                o=lathe(bpy,f'Shelf bowl {k+1}',[(r,z) for r,z in PROFILE],(g,f),96);pitch=.0146
                o.location=(x,y,z0+k*pitch)
            for p in o.data.polygons:
                if p.center.z < .003:p.material_index=1
            o.rotation_euler.z=k*1.3
        records.append(dict(glaze=glaze_name,x=x,y=y,count=count))
    return records


def build_environment(bpy,scene):
    """The kitchen and everything standing in it; returns a description of both."""
    from city_kitchen import build_kitchen
    from kitchen_props import add_props
    room=build_kitchen(scene)
    room['props']=[p['object_name'] for p in add_props(room['hob'])]
    room['shelf_stacks']=shelf_stacks(bpy)
    return room
