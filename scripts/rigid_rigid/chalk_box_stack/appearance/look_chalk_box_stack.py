"""Procedural classroom decor and visible rigid bodies; no physics changes."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

import sys
sys.path.insert(0, str(_PCVE_ROOT / 'scripts'))
from pcve_blender_compat import (set_shader_input)
import math,random
ENVIRONMENT_THEME='sage_classroom_chalkboard_geometry_tools'
# The look, in brief (appearance and camera only; the physics cache replays):
# - Camera: a 40 mm perspective lens at f/8 from the front-left end of the
#   bench (scenario camera), so the cartons' struck face is visible.
# - Bench: an oiled slab on an open black steel frame, 2.6 x 1.0 m at 0.76 m
#   support height, topped with scanned oak veneer at real size.
# - Blackboard: the scanned realistic_blackboard.glb, hung so the bench does
#   not cut the board off along a hard line (see _import_blackboard).
# - Cartons: one dyed paperboard sheet each. The blank is a body, a 1.3 mm
#   groove and a lid with 0.35 mm crease edges; the ink wraps the whole sheet,
#   the mask is cut back at every cut edge to expose the paper core, and the
#   surface carries ink mottle, crushed fibre along the folds, grime at the
#   bottom edge and the shadow the lid casts on the tray; matte knockout
#   lettering sits almost flush on the board.
# - Eraser: a beech handle with grain in colour, roughness and relief, and a
#   felt sole with fibres, nap sheen and chalk dust.
# - Dressing: the supplied the_pen.glb and chalk.glb assets with their own
#   baked materials; one chalk stick is tinted yellow by multiplying the
#   asset's base colour; a 7 mm crumb lies beside the stick it broke off.
#   There are no chalk-powder films or dust patches on the bench.
# - Light: the classroom's own: six ceiling LED troffers whose diffusers are
#   the emitters, and an overcast sky through two windows in the left wall, in
#   a closed room (side walls, ceiling, the wall behind the camera).
# - Floor: scanned grey floor tiles; drawing tools: varnished hardwood; renders
#   carry a 180-degree motion blur.
from pcve_assets import asset as _pcve_asset
_MODEL_DIR=_pcve_asset('')/'models'


def _material(bpy,name,color,rough=.62,metallic=0.,coat=0.,bump=0.,bump_scale=14.,
              grain=None,speckle=None,speckle_color=None,bump_distance=.00025):
    """Principled surface with optional procedural relief, wood grain or aggregate."""
    material=bpy.data.materials.new(name);material.diffuse_color=(*color,1.);material.use_nodes=True
    nodes=material.node_tree.nodes;links=material.node_tree.links
    bsdf=nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value=(*color,1.)
    bsdf.inputs['Roughness'].default_value=rough
    if metallic:
        bsdf.inputs['Metallic'].default_value=metallic
    if coat:
        set_shader_input(bsdf, 'Coat Weight', coat)
        set_shader_input(bsdf, 'Coat Roughness', 0.24)
    if not (bump>0. or speckle):
        return material
    vector=nodes.new('ShaderNodeTexCoord').outputs['Object']
    if grain:
        mapping=nodes.new('ShaderNodeMapping');mapping.inputs['Scale'].default_value=grain
        links.new(mapping.inputs['Vector'],vector);vector=mapping.outputs['Vector']
    if bump>0.:
        noise=nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value=bump_scale
        noise.inputs['Detail'].default_value=3.
        noise.inputs['Roughness'].default_value=.52
        links.new(noise.inputs['Vector'],vector)
        relief=nodes.new('ShaderNodeBump')
        relief.inputs['Strength'].default_value=bump
        relief.inputs['Distance'].default_value=bump_distance
        links.new(relief.inputs['Height'],noise.outputs['Fac'])
        links.new(bsdf.inputs['Normal'],relief.outputs['Normal'])
    if speckle:
        aggregate=nodes.new('ShaderNodeTexVoronoi');aggregate.inputs['Scale'].default_value=speckle
        links.new(aggregate.inputs['Vector'],vector)
        ramp=nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].position=.36;ramp.color_ramp.elements[0].color=(*color,1.)
        ramp.color_ramp.elements[1].position=.68
        ramp.color_ramp.elements[1].color=(*(speckle_color or tuple(c*.55 for c in color)),1.)
        links.new(ramp.inputs['Fac'],aggregate.outputs['Distance'])
        links.new(bsdf.inputs['Base Color'],ramp.outputs['Color'])
    return material


def _slate_surface(bpy):
    """Matte painted slate with fine tooth and broad, faint wiping wear."""
    material=_material(bpy,'Slate chalkboard',(.038,.054,.045),rough=.94,
                       bump=.32,bump_scale=650.,bump_distance=.00035)
    nodes=material.node_tree.nodes;links=material.node_tree.links
    bsdf=nodes['Principled BSDF']
    set_shader_input(bsdf, 'Specular IOR Level', 0.18)
    coord=nodes.new('ShaderNodeTexCoord')
    mapping=nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value=(1.4,1.,7.)
    links.new(mapping.inputs['Vector'],coord.outputs['Object'])
    wear=nodes.new('ShaderNodeTexNoise');wear.inputs['Scale'].default_value=5.
    wear.inputs['Detail'].default_value=4.;wear.inputs['Roughness'].default_value=.7
    links.new(wear.inputs['Vector'],mapping.outputs['Vector'])
    tone=nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].position=.2
    tone.color_ramp.elements[0].color=(.028,.042,.034,1.)
    tone.color_ramp.elements[1].position=.8
    tone.color_ramp.elements[1].color=(.052,.068,.057,1.)
    links.new(tone.inputs['Fac'],wear.outputs['Fac'])
    links.new(bsdf.inputs['Base Color'],tone.outputs['Color'])
    rough=nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value=.86;rough.inputs['To Max'].default_value=.98
    links.new(rough.inputs['Value'],wear.outputs['Fac'])
    links.new(bsdf.inputs['Roughness'],rough.outputs['Result'])
    # A second, coarser relief survives normal camera distances without pits.
    tooth=nodes.new('ShaderNodeTexNoise');tooth.inputs['Scale'].default_value=160.
    tooth.inputs['Detail'].default_value=2.
    links.new(tooth.inputs['Vector'],coord.outputs['Object'])
    fine_normal=bsdf.inputs['Normal'].links[0].from_socket
    relief=nodes.new('ShaderNodeBump')
    relief.inputs['Strength'].default_value=.22
    relief.inputs['Distance'].default_value=.00045
    links.new(relief.inputs['Height'],tooth.outputs['Fac'])
    links.new(relief.inputs['Normal'],fine_normal)
    links.new(bsdf.inputs['Normal'],relief.outputs['Normal'])
    return material


def _eraser_wood(bpy):
    """Beech handle whose colour, gloss and relief all follow the grain.

    A flat tan block with one noise bump puts the whole pattern in the normal
    channel and leaves the surface reading as moulded plastic. Real beech also
    varies in colour and sheen between early and late
    wood, and the figure has to run the length of the block on the front face as
    well as on the top, so both cross axes are stretched, not just Y.
    """
    material=bpy.data.materials.new('Beech eraser handle');material.use_nodes=True
    nodes=material.node_tree.nodes;links=material.node_tree.links
    bsdf=nodes['Principled BSDF']
    set_shader_input(bsdf, 'Coat Weight', 0.06)
    set_shader_input(bsdf, 'Coat Roughness', 0.36)
    coord=nodes.new('ShaderNodeTexCoord')
    grain=nodes.new('ShaderNodeMapping')
    grain.inputs['Scale'].default_value=(.55,24.,24.)
    links.new(grain.inputs['Vector'],coord.outputs['Object'])
    fibre=nodes.new('ShaderNodeTexNoise')
    fibre.inputs['Scale'].default_value=7.5
    fibre.inputs['Detail'].default_value=7.
    fibre.inputs['Roughness'].default_value=.58
    links.new(fibre.inputs['Vector'],grain.outputs['Vector'])
    # A broad second octave stops neighbouring fibres from sharing one tone.
    blotch=nodes.new('ShaderNodeTexNoise')
    blotch.inputs['Scale'].default_value=2.4
    blotch.inputs['Detail'].default_value=3.
    links.new(blotch.inputs['Vector'],coord.outputs['Object'])
    blend=nodes.new('ShaderNodeMixRGB');blend.blend_type='MIX';blend.inputs['Fac'].default_value=.26
    links.new(blend.inputs['Color1'],fibre.outputs['Fac'])
    links.new(blend.inputs['Color2'],blotch.outputs['Fac'])
    tone=nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.interpolation='LINEAR'
    tone.color_ramp.elements[0].position=.24
    tone.color_ramp.elements[0].color=(.152,.073,.028,1.)
    tone.color_ramp.elements[1].position=.80
    tone.color_ramp.elements[1].color=(.575,.396,.230,1.)
    middle=tone.color_ramp.elements.new(.46)
    middle.color=(.352,.196,.088,1.)
    links.new(tone.inputs['Fac'],blend.outputs['Color'])
    # Beech figure is not just tonal blotches: the dark late-wood lines are what
    # the eye reads as "wood" at a glance, so they get their own stretched,
    # high-frequency layer multiplied over the tone.
    lines=nodes.new('ShaderNodeMapping')
    lines.inputs['Scale'].default_value=(.30,34.,34.)
    links.new(lines.inputs['Vector'],coord.outputs['Object'])
    streak=nodes.new('ShaderNodeTexNoise')
    streak.inputs['Scale'].default_value=12.
    streak.inputs['Detail'].default_value=6.
    streak.inputs['Roughness'].default_value=.62
    links.new(streak.inputs['Vector'],lines.outputs['Vector'])
    line_ramp=nodes.new('ShaderNodeValToRGB')
    line_ramp.color_ramp.elements[0].position=.38
    line_ramp.color_ramp.elements[0].color=(.70,.66,.62,1.)
    line_ramp.color_ramp.elements[1].position=.52
    line_ramp.color_ramp.elements[1].color=(1.,1.,1.,1.)
    links.new(line_ramp.inputs['Fac'],streak.outputs['Fac'])
    figure=nodes.new('ShaderNodeMixRGB');figure.blend_type='MULTIPLY';figure.inputs['Fac'].default_value=.62
    links.new(figure.inputs['Color1'],tone.outputs['Color'])
    links.new(figure.inputs['Color2'],line_ramp.outputs['Color'])
    links.new(bsdf.inputs['Base Color'],figure.outputs['Color'])
    gloss=nodes.new('ShaderNodeMapRange')
    gloss.inputs['To Min'].default_value=.42;gloss.inputs['To Max'].default_value=.62
    links.new(gloss.inputs['Value'],blend.outputs['Color'])
    links.new(bsdf.inputs['Roughness'],gloss.outputs['Result'])
    relief=nodes.new('ShaderNodeTexNoise')
    relief.inputs['Scale'].default_value=150.
    relief.inputs['Detail'].default_value=3.
    links.new(relief.inputs['Vector'],grain.outputs['Vector'])
    bump=nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value=.05;bump.inputs['Distance'].default_value=.00012
    links.new(bump.inputs['Height'],relief.outputs['Fac'])
    # Pores sit finer than the grain bands and are what stop beech reading as a
    # smooth moulded shell at this distance.
    pores=nodes.new('ShaderNodeTexNoise')
    pores.inputs['Scale'].default_value=420.
    pores.inputs['Detail'].default_value=2.
    links.new(pores.inputs['Vector'],grain.outputs['Vector'])
    pit=nodes.new('ShaderNodeBump')
    pit.inputs['Strength'].default_value=.16;pit.inputs['Distance'].default_value=.00008
    links.new(pit.inputs['Height'],pores.outputs['Fac'])
    links.new(pit.inputs['Normal'],bump.outputs['Normal'])
    links.new(bsdf.inputs['Normal'],pit.outputs['Normal'])
    return material


def _eraser_felt(bpy):
    """Chalk-loaded wool felt: packed fibres, a nap sheen and the dust it holds.

    A dark slab with one noise bump has no fibre structure at all once the shot
    gets close. Felt reads as felt because the surface scatters light in every
    direction (sheen) and because it is never clean: the pad in use is streaked
    with the chalk it has been wiping.
    """
    material=bpy.data.materials.new('Chalk-loaded eraser felt');material.use_nodes=True
    nodes=material.node_tree.nodes;links=material.node_tree.links
    bsdf=nodes['Principled BSDF']
    # Deep felt is nearly lambertian; leaving the default specular in place is
    # what made the pad read as a painted metal plinth.
    bsdf.inputs['Roughness'].default_value=.96
    set_shader_input(bsdf, 'Specular IOR Level', 0.14)
    set_shader_input(bsdf, 'Sheen Weight', 0.26)
    set_shader_input(bsdf, 'Sheen Roughness', 0.62)
    set_shader_input(bsdf, 'Sheen Tint', (0.58, 0.6, 0.56, 1.0))
    coord=nodes.new('ShaderNodeTexCoord')
    base=nodes.new('ShaderNodeValToRGB')
    base.color_ramp.elements[0].position=.24
    base.color_ramp.elements[0].color=(.021,.027,.026,1.)
    base.color_ramp.elements[1].position=.80
    base.color_ramp.elements[1].color=(.062,.069,.066,1.)
    weave=nodes.new('ShaderNodeTexNoise')
    weave.inputs['Scale'].default_value=140.
    weave.inputs['Detail'].default_value=4.
    links.new(weave.inputs['Vector'],coord.outputs['Object'])
    links.new(base.inputs['Fac'],weave.outputs['Fac'])
    # Chalk dust is what makes a used pad lighter than a new one, and it sits in
    # broad smears rather than in an even film.
    smear=nodes.new('ShaderNodeTexNoise')
    smear.inputs['Scale'].default_value=26.
    smear.inputs['Detail'].default_value=5.
    smear.inputs['Roughness'].default_value=.62
    links.new(smear.inputs['Vector'],coord.outputs['Object'])
    mask=nodes.new('ShaderNodeValToRGB')
    mask.color_ramp.elements[0].position=.54
    mask.color_ramp.elements[0].color=(0.,0.,0.,1.)
    mask.color_ramp.elements[1].position=.82
    mask.color_ramp.elements[1].color=(.20,.20,.20,1.)
    links.new(mask.inputs['Fac'],smear.outputs['Fac'])
    dust=nodes.new('ShaderNodeMixRGB');dust.blend_type='MIX'
    dust.inputs['Color2'].default_value=(.600,.602,.575,1.)
    links.new(dust.inputs['Fac'],mask.outputs['Color'])
    links.new(dust.inputs['Color1'],base.outputs['Color'])
    links.new(bsdf.inputs['Base Color'],dust.outputs['Color'])
    fibre=nodes.new('ShaderNodeTexNoise')
    fibre.inputs['Scale'].default_value=900.
    fibre.inputs['Detail'].default_value=2.
    links.new(fibre.inputs['Vector'],coord.outputs['Object'])
    fine=nodes.new('ShaderNodeBump')
    fine.inputs['Strength'].default_value=.42;fine.inputs['Distance'].default_value=.00030
    links.new(fine.inputs['Height'],fibre.outputs['Fac'])
    nap=nodes.new('ShaderNodeTexNoise')
    nap.inputs['Scale'].default_value=110.
    nap.inputs['Detail'].default_value=3.
    links.new(nap.inputs['Vector'],coord.outputs['Object'])
    coarse=nodes.new('ShaderNodeBump')
    coarse.inputs['Strength'].default_value=.26;coarse.inputs['Distance'].default_value=.00055
    links.new(coarse.inputs['Height'],nap.outputs['Fac'])
    links.new(coarse.inputs['Normal'],fine.outputs['Normal'])
    links.new(bsdf.inputs['Normal'],coarse.outputs['Normal'])
    return material


def _bench_surface(bpy,name,color,rough=.40):
    """Enamel bench top with tonal drift and scuffs, so it stops reading as vinyl."""
    material=bpy.data.materials.new(name);material.use_nodes=True
    nodes=material.node_tree.nodes;links=material.node_tree.links
    bsdf=nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value=rough
    set_shader_input(bsdf, 'Coat Weight', 0.1)
    set_shader_input(bsdf, 'Coat Roughness', 0.3)
    coord=nodes.new('ShaderNodeTexCoord')
    drift=nodes.new('ShaderNodeTexNoise')
    drift.inputs['Scale'].default_value=1.7
    drift.inputs['Detail'].default_value=4.
    drift.inputs['Roughness'].default_value=.62
    links.new(drift.inputs['Vector'],coord.outputs['Object'])
    tone=nodes.new('ShaderNodeValToRGB')
    tone.color_ramp.elements[0].position=.26
    tone.color_ramp.elements[0].color=(*(c*.80 for c in color),1.)
    tone.color_ramp.elements[1].position=.78
    tone.color_ramp.elements[1].color=(*(min(1.,c*1.22) for c in color),1.)
    links.new(tone.inputs['Fac'],drift.outputs['Fac'])
    links.new(bsdf.inputs['Base Color'],tone.outputs['Color'])
    # Long shallow scuffs running across the bench, as on any used lab table.
    scuff_coord=nodes.new('ShaderNodeMapping')
    scuff_coord.inputs['Scale'].default_value=(3.0,7.5,3.0)
    links.new(scuff_coord.inputs['Vector'],coord.outputs['Object'])
    scuff=nodes.new('ShaderNodeTexNoise')
    scuff.inputs['Scale'].default_value=4.2
    scuff.inputs['Detail'].default_value=2.
    links.new(scuff.inputs['Vector'],scuff_coord.outputs['Vector'])
    mask=nodes.new('ShaderNodeValToRGB')
    mask.color_ramp.elements[0].position=.66;mask.color_ramp.elements[0].color=(0.,0.,0.,1.)
    mask.color_ramp.elements[1].position=.76;mask.color_ramp.elements[1].color=(1.,1.,1.,1.)
    links.new(mask.inputs['Fac'],scuff.outputs['Fac'])
    wear=nodes.new('ShaderNodeMixRGB');wear.inputs['Fac'].default_value=1.
    links.new(wear.inputs['Fac'],mask.outputs['Color'])
    links.new(wear.inputs['Color1'],tone.outputs['Color'])
    wear.inputs['Color2'].default_value=(*(c*.72 for c in color),1.)
    links.new(bsdf.inputs['Base Color'],wear.outputs['Color'])
    gloss=nodes.new('ShaderNodeMixRGB');gloss.blend_type='MIX'
    links.new(gloss.inputs['Fac'],mask.outputs['Color'])
    gloss.inputs['Color1'].default_value=(rough,rough,rough,1.)
    gloss.inputs['Color2'].default_value=(.62,.62,.62,1.)
    links.new(bsdf.inputs['Roughness'],gloss.outputs['Color'])
    relief=nodes.new('ShaderNodeBump')
    relief.inputs['Strength'].default_value=.07
    relief.inputs['Distance'].default_value=.00015
    links.new(relief.inputs['Height'],mask.outputs['Color'])
    links.new(bsdf.inputs['Normal'],relief.outputs['Normal'])
    return material


def _cube_mesh(bpy,name,size):
    """A real-world-sized cube mesh, so Object texture coordinates stay isotropic."""
    x,y,z=(value*.5 for value in size)
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata([(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),
                      (-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)],[],
                     [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
    mesh.update()
    return mesh


def _import_prop(bpy,scene,filename,name,length,location,yaw=0.,roll=0.,stand=False,solo=False):
    """Drop a downloaded GLB onto the bench at real size.

    Sketchfab exports arrive with arbitrary orientation, units and a parent
    transform, so the mesh is baked into world space first and then re-oriented
    from its own bounding box instead of assuming a Z-up, metre-scaled asset.
    Laid flat by default; ``stand`` sets the long axis upright, which is the
    way a bottle is actually put down on a bench. ``roll`` spins the prop
    about its own long axis, which is how the side that faces the camera is
    chosen; standing up, the same job is done by ``yaw``. ``solo`` keeps only
    one mesh piece out of a multi-part asset: chalk.glb ships two complete
    sticks under one bounding box (one along X, one along Y, the Y one leaning
    ~22 deg), and a single chalk prop wants exactly one straight stick.
    """
    from mathutils import Matrix, Vector
    path=_MODEL_DIR/filename
    if not path.exists():raise FileNotFoundError(path)
    existing={obj.name for obj in bpy.data.objects}
    bpy.ops.import_scene.gltf(filepath=str(path))
    parts=[obj for obj in bpy.data.objects if obj.name not in existing and obj.type=='MESH']
    if not parts:raise RuntimeError(f'{filename} contained no mesh geometry')
    if solo and len(parts)>1:
        def rodness(o):
            corners=[o.matrix_world @ Vector(c) for c in o.bound_box]
            dims=sorted(max(getattr(c,a) for c in corners)-min(getattr(c,a) for c in corners)
                        for a in 'xyz')
            return dims[0]/max(dims[1],1e-9)
        keep=max(parts,key=lambda o:(rodness(o),len(o.data.vertices)))
        for extra in parts:
            if extra is not keep:bpy.data.objects.remove(extra,do_unlink=True)
        parts=[keep]
    for obj in scene.objects:obj.select_set(False)
    for part in parts:part.select_set(True)
    bpy.context.view_layer.objects.active=parts[0]
    if len(parts)>1:bpy.ops.object.join()
    prop=bpy.context.view_layer.objects.active
    prop.name=name
    # The glTF importer leaves objects in quaternion mode, where writing
    # rotation_euler silently does nothing.
    prop.rotation_mode='XYZ'
    world=prop.matrix_world.copy();prop.parent=None;prop.matrix_world=world
    for stray in [o for o in bpy.data.objects if o.name not in existing and o.type!='MESH']:
        bpy.data.objects.remove(stray,do_unlink=True)
    for obj in scene.objects:obj.select_set(False)
    prop.select_set(True);bpy.context.view_layer.objects.active=prop
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    axes=[max(v.co[i] for v in prop.data.vertices)-min(v.co[i] for v in prop.data.vertices)
          for i in range(3)]
    tall=axes.index(max(axes))
    prop.scale=(length/max(axes),)*3
    # Index by which local axis is the long one: 0 = X, 1 = Y, 2 = Z.
    if stand:
        # Send the long axis to world up. glTF is Y-up, Blender is Z-up, and the
        # exported model may be authored either way, so the move is derived from
        # the measured axis rather than assumed.
        up=[Matrix.Rotation(-math.pi*.5,4,'Y'),Matrix.Rotation(math.pi*.5,4,'X'),
            Matrix.Rotation(0.,4,'Z')][tall]
        prop.rotation_euler=(Matrix.Rotation(yaw,4,'Z') @ up).to_euler()
    else:
        lay=[Matrix.Rotation(0.,4,'Z'),Matrix.Rotation(-math.pi*.5,4,'Z'),
             Matrix.Rotation(math.pi*.5,4,'Y')][tall]
        spin=[Matrix.Rotation(roll,4,'X'),Matrix.Rotation(roll,4,'Y'),
              Matrix.Rotation(roll,4,'Z')][tall]
        prop.rotation_euler=(Matrix.Rotation(yaw,4,'Z') @ lay @ spin).to_euler()
    bpy.context.view_layer.update()
    corners=[prop.matrix_world @ Vector(corner) for corner in prop.bound_box]
    low=Vector((min(c.x for c in corners),min(c.y for c in corners),min(c.z for c in corners)))
    high=Vector((max(c.x for c in corners),max(c.y for c in corners),max(c.z for c in corners)))
    prop.location+=Vector((location[0]-(low.x+high.x)*.5,location[1]-(low.y+high.y)*.5,
                           location[2]-low.z))
    bpy.context.view_layer.update()
    return prop


def _tint_prop(prop,tint,name):
    """Multiply an imported asset's baked base colour by a tint.

    The supplied chalk carries a base-colour texture, so a yellow stick cannot
    be made by writing Base Color: the texture link would win. Instead the
    texture is rerouted through a MULTIPLY mix, which keeps the mottling of the
    baked map and shifts the overall hue. Every slot shares one shaded copy.
    """
    shaded=None
    for slot in prop.material_slots:
        if slot.material is None:continue
        if shaded is None:
            shaded=slot.material.copy();shaded.name=name
            nodes=shaded.node_tree.nodes;links=shaded.node_tree.links
            bsdf=nodes['Principled BSDF']
            source=bsdf.inputs['Base Color'].links[0].from_socket if bsdf.inputs['Base Color'].links else None
            mix=nodes.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs['Fac'].default_value=1.
            mix.inputs['Color2'].default_value=(*tint,1.)
            if source is not None:
                links.new(mix.inputs['Color1'],source)
            else:
                mix.inputs['Color1'].default_value=bsdf.inputs['Base Color'].default_value
            links.new(bsdf.inputs['Base Color'],mix.outputs['Color'])
        slot.material=shaded
    return prop


def _pbr_coords(nodes,links,scale=(1,1,1)):
    tex=nodes.new('ShaderNodeTexCoord');mapping=nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value=scale;links.new(tex.outputs['Object'],mapping.inputs['Vector'])
    return mapping


def _pbr_noise(nodes,links,vector,scale,detail=3,roughness=.5,distortion=0.):
    node=nodes.new('ShaderNodeTexNoise');node.inputs['Scale'].default_value=scale
    node.inputs['Detail'].default_value=detail;node.inputs['Roughness'].default_value=roughness
    node.inputs['Distortion'].default_value=distortion;links.new(vector,node.inputs['Vector'])
    return node


def _pbr_range(nodes,links,source,low,high):
    node=nodes.new('ShaderNodeMapRange');node.inputs['To Min'].default_value=low
    node.inputs['To Max'].default_value=high;links.new(source,node.inputs['Value'])
    return node


def _pbr_bump(nodes,links,height,strength,distance,normal=None):
    node=nodes.new('ShaderNodeBump');node.inputs['Strength'].default_value=strength
    node.inputs['Distance'].default_value=distance;links.new(height,node.inputs['Height'])
    if normal is not None:links.new(normal,node.inputs['Normal'])
    return node


def _powder_coated_steel(bpy,name,color):
    """Black powder coat with an orange-peel skin, matching u_track_ball's frame."""
    material=bpy.data.materials.new(name);material.use_nodes=True
    nodes=material.node_tree.nodes;links=material.node_tree.links
    bsdf=nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value=(*color,1.)
    bsdf.inputs['Metallic'].default_value=.42
    skin=_pbr_noise(nodes,links,_pbr_coords(nodes,links).outputs['Vector'],240.,2)
    links.new(_pbr_range(nodes,links,skin.outputs['Fac'],.48,.62).outputs[0],bsdf.inputs['Roughness'])
    bump=_pbr_bump(nodes,links,skin.outputs['Fac'],.14,.00004)
    links.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
    return material


def _carton_mesh(bpy,name,size,phase=0.):
    """The blank of a folding carton: a body, a groove and a lid.

    One rounded cube reads as moulded plastic: a 1.5 mm bevel catches a rim
    highlight of its own and no fold is visible anywhere on it. A real chalk
    box is a tray with a lid snapped over it, so the silhouette carries a
    groove all the way round just under the top face, and the lid sits in it as
    a separate island of the same mesh.

    The lid is flush with the body (no overhang) so the outer profile still
    matches the collision box exactly, and the groove is 0.9 mm -- thin in
    reality, but it is a real shadow line rather than a drawn one. Corners are
    jittered by a fraction of a millimetre: a folded carton is not a machined
    cube, and the eye reads the difference long before it can name it.
    """
    w,d,h=size
    lid=.0035;gap=.0013
    body_top=h/2-lid-gap;body_bottom=-h/2
    rng=random.Random(int(phase*1000)+17)
    verts=[];faces=[]
    def island(z0,z1,inset=0.):
        x,y=w/2-inset,d/2-inset
        corners=[(-x,-y,z0),(x,-y,z0),(x,y,z0),(-x,y,z0),
                 (-x,-y,z1),(x,-y,z1),(x,y,z1),(-x,y,z1)]
        base=len(verts)
        for cx,cy,cz in corners:
            verts.append((cx+rng.uniform(-.00025,.00025),
                          cy+rng.uniform(-.00025,.00025),
                          cz+rng.uniform(-.00018,.00018)))
        faces.extend([(base+0,base+3,base+2,base+1),(base+4,base+5,base+6,base+7),
                      (base+0,base+1,base+5,base+4),(base+1,base+2,base+6,base+5),
                      (base+2,base+3,base+7,base+6),(base+3,base+0,base+4,base+7)])
    island(body_bottom,body_top)
    island(h/2-lid,h/2)
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata(verts,[],faces);mesh.update()
    return mesh,dict(body_bottom=body_bottom,body_top=body_top,lid_bottom=h/2-lid,lid_top=h/2)


def _carton_board(bpy,name,ink,size,phase=0.,parts=None):
    """A dyed folding carton: ink over the whole blank, paper core at the edges.

    A printed plate on a cube, even with a lid and bare board around the
    panel, reads as a label on a block, because a label is a rectangle on a
    surface and nothing else.

    A classroom chalk box is a dyed blank: the colour wraps the whole sheet
    and what shows is the paper core along every cut edge and at the worn
    corners. So the ink covers the entire carton, the mask is cut back a
    couple of millimetres at each edge to expose that core, the lid is a
    separate island behind a groove, and the surface carries what a used box
    carries -- ink mottle, crushed fibre along the folds, grime at the bottom
    edge and the shadow the lid casts on the tray.

    Object coordinates are metres on a real-world-sized mesh, so the print
    rides the rigid body through the impact instead of floating above it.
    ``phase`` shifts the noise field so a stack of boxes is not three
    impressions of one die.
    """
    w,d,h=size
    parts=parts or dict(body_bottom=-h/2,body_top=h/2-.0048,lid_bottom=h/2-.0035,lid_top=h/2)
    body_bottom,body_top,lid_top=parts['body_bottom'],parts['body_top'],parts['lid_top']
    body_h=body_top-body_bottom
    material=bpy.data.materials.new(name);material.use_nodes=True
    nodes=material.node_tree.nodes;links=material.node_tree.links
    bsdf=nodes['Principled BSDF']
    # Uncoated board: no coat, and a low specular so the ink stays matte.
    set_shader_input(bsdf, 'Specular IOR Level', 0.22)
    coord=nodes.new('ShaderNodeTexCoord');obj=coord.outputs['Object']
    sep=nodes.new('ShaderNodeSeparateXYZ');links.new(obj,sep.inputs['Vector'])
    # Pulp mottle, fibre and tooth are the three scales paperboard actually
    # has; stretched along x so the fibre reads as machine direction.
    field=_pbr_coords(nodes,links,(.6,1.8,1.8))
    field.inputs['Location'].default_value=(phase*1.7,phase*2.3,phase*.9)
    pulp=_pbr_noise(nodes,links,field.outputs['Vector'],6.5,3,.55)
    fibre=_pbr_noise(nodes,links,field.outputs['Vector'],210.,2,.5)
    tooth=_pbr_noise(nodes,links,field.outputs['Vector'],900.,2,.5)
    cover=_pbr_noise(nodes,links,field.outputs['Vector'],26.,3,.6)
    # The ink gets its own, less anisotropic field: the pulp noise is
    # stretched hard along the machine direction, and reusing it inside the
    # colour printed visible vertical banding across the panel.
    ink_field=_pbr_coords(nodes,links,(.85,1.15,1.15))
    ink_field.inputs['Location'].default_value=(phase*2.1,phase*.7,phase*1.3)
    mottle=_pbr_noise(nodes,links,ink_field.outputs['Vector'],150.,4,.6)

    def face(source,plane,sign,soft=.0016):
        """1 on the face lying at `plane`; `sign` is its outward direction.

        The print must not wrap onto the neighbouring faces, so the mask falls
        off as soon as the surface turns the corner into the bevel.
        """
        edge=nodes.new('ShaderNodeMapRange');edge.clamp=True
        edge.inputs['From Min'].default_value=plane-sign*soft
        edge.inputs['From Max'].default_value=plane-sign*soft*2.
        edge.inputs['To Min'].default_value=1.;edge.inputs['To Max'].default_value=0.
        links.new(source,edge.inputs['Value'])
        return edge.outputs['Result']

    def both(a,b):
        node=nodes.new('ShaderNodeMath');node.operation='MULTIPLY'
        links.new(a,node.inputs[0]);links.new(b,node.inputs[1])
        return node.outputs[0]

    def max2(a,b):
        node=nodes.new('ShaderNodeMath');node.operation='MAXIMUM'
        links.new(a,node.inputs[0]);links.new(b,node.inputs[1])
        return node.outputs[0]

    def window_at(source,center,limit,soft=.0009):
        """A window around a centre that is not the object origin."""
        shift=nodes.new('ShaderNodeMath');shift.operation='SUBTRACT'
        links.new(source,shift.inputs[0]);shift.inputs[1].default_value=center
        absolute=nodes.new('ShaderNodeMath');absolute.operation='ABSOLUTE'
        links.new(shift.outputs[0],absolute.inputs[0])
        edge=nodes.new('ShaderNodeMapRange');edge.clamp=True
        edge.inputs['From Min'].default_value=limit
        edge.inputs['From Max'].default_value=limit-soft
        edge.inputs['To Min'].default_value=0.;edge.inputs['To Max'].default_value=1.
        links.new(absolute.outputs[0],edge.inputs['Value'])
        return edge.outputs['Result']

    # --- edge distance ----------------------------------------------------
    # On any face the gap to the nearest face plane is ~0, so the median of
    # the three gaps is the distance to the nearest cut or folded edge.
    def gap(axis,half):
        absolute=nodes.new('ShaderNodeMath');absolute.operation='ABSOLUTE'
        links.new(sep.outputs[axis],absolute.inputs[0])
        left=nodes.new('ShaderNodeMath');left.operation='SUBTRACT'
        left.inputs[0].default_value=half
        links.new(absolute.outputs[0],left.inputs[1])
        return left.outputs[0]
    gx,gy,gz=gap('X',w/2),gap('Y',d/2),gap('Z',h/2)
    low=nodes.new('ShaderNodeMath');low.operation='MINIMUM'
    links.new(gx,low.inputs[0]);links.new(gy,low.inputs[1])
    high=nodes.new('ShaderNodeMath');high.operation='MAXIMUM'
    links.new(gx,high.inputs[0]);links.new(gy,high.inputs[1])
    inner=nodes.new('ShaderNodeMath');inner.operation='MINIMUM'
    links.new(high.outputs[0],inner.inputs[0]);links.new(gz,inner.inputs[1])
    middle=nodes.new('ShaderNodeMath');middle.operation='MAXIMUM'
    links.new(low.outputs[0],middle.inputs[0]);links.new(inner.outputs[0],middle.inputs[1])
    # The paper core: the ink is cut back from every cut edge, and how far it
    # is cut back varies along the edge -- a clean even frame of bare board
    # reads as a plastic box with white trim, not as a folded blank.
    core_noise=_pbr_noise(nodes,links,field.outputs['Vector'],55.,3,.6)
    core_width=nodes.new('ShaderNodeMapRange');core_width.clamp=True
    core_width.inputs['From Min'].default_value=.25;core_width.inputs['From Max'].default_value=.75
    core_width.inputs['To Min'].default_value=.00015;core_width.inputs['To Max'].default_value=.0011
    links.new(core_noise.outputs['Fac'],core_width.inputs['Value'])
    core=nodes.new('ShaderNodeMapRange');core.clamp=True
    links.new(core_width.outputs['Result'],core.inputs['From Min'])
    core.inputs['From Max'].default_value=.0002
    core.inputs['To Min'].default_value=0.;core.inputs['To Max'].default_value=1.
    links.new(middle.outputs[0],core.inputs['Value'])
    # Fibre damage spreads further than the exposed core.
    fold=nodes.new('ShaderNodeMapRange');fold.clamp=True
    fold.inputs['From Min'].default_value=.0062;fold.inputs['From Max'].default_value=.0008
    fold.inputs['To Min'].default_value=0.;fold.inputs['To Max'].default_value=1.
    links.new(middle.outputs[0],fold.inputs['Value'])

    # --- printed fields ---------------------------------------------------
    # The colour wraps the whole blank: the four sides of the tray, the four
    # sides of the lid and the lid top. What is left uncovered is the paper
    # core at the cut edges.
    side_faces=max2(max2(face(sep.outputs['Y'],-d/2.,-1),face(sep.outputs['Y'],d/2.,1)),
                    max2(face(sep.outputs['X'],-w/2.,-1),face(sep.outputs['X'],w/2.,1)))
    lid_face=face(sep.outputs['Z'],lid_top,1)
    core_cut=nodes.new('ShaderNodeMath');core_cut.operation='MULTIPLY'
    links.new(core.outputs['Result'],core_cut.inputs[0]);core_cut.inputs[1].default_value=.92
    keep=nodes.new('ShaderNodeMath');keep.operation='SUBTRACT'
    keep.inputs[0].default_value=1.;links.new(core_cut.outputs[0],keep.inputs[1])
    printed=both(max2(side_faces,lid_face),keep.outputs[0])
    # A darker stripe near the bottom, the way a cheap carton is over-printed
    # to cover the scuffs it collects there.
    stripe=both(both(window_at(sep.outputs['Z'],body_bottom+.0135,.0034,soft=.0018),side_faces),
                 keep.outputs[0])

    # --- ink and board colour --------------------------------------------
    # Ink density varies across the sheet: uncoated board drinks ink unevenly,
    # so the field is a wash between a starved and a fully loaded pass.
    # A touch of neutral is mixed in first: full saturation reads as enamel
    # paint, and school stationery is dyed board, not sprayed metal.
    soft=tuple(c*.87+n*.13 for c,n in zip(ink,(.40,.38,.34)))
    starved=tuple(c*.70+t*.30 for c,t in zip(soft,(.86,.78,.58)))
    shade=nodes.new('ShaderNodeMixRGB');shade.blend_type='MIX'
    shade.inputs['Color1'].default_value=(*starved,1.)
    shade.inputs['Color2'].default_value=(*soft,1.)
    links.new(cover.outputs['Fac'],shade.inputs['Fac'])
    # Finer mottling inside the ink: a lay-down is never one flat value.
    ink_wash=nodes.new('ShaderNodeValToRGB')
    ink_wash.color_ramp.elements[0].position=.22;ink_wash.color_ramp.elements[0].color=(.84,.84,.84,1)
    ink_wash.color_ramp.elements[1].position=.78;ink_wash.color_ramp.elements[1].color=(1.,1.,1.,1)
    links.new(mottle.outputs['Fac'],ink_wash.inputs[0])
    ink_mix=nodes.new('ShaderNodeMixRGB');ink_mix.blend_type='MULTIPLY'
    links.new(shade.outputs['Color'],ink_mix.inputs['Color1'])
    links.new(ink_wash.outputs['Color'],ink_mix.inputs['Color2'])
    ink_final=nodes.new('ShaderNodeMixRGB');ink_final.blend_type='MIX'
    links.new(ink_mix.outputs['Color'],ink_final.inputs['Color1'])
    ink_final.inputs['Color2'].default_value=(*(c*.62 for c in soft),1.)
    links.new(stripe,ink_final.inputs['Fac'])

    pulp_mix=nodes.new('ShaderNodeMath');pulp_mix.operation='MULTIPLY_ADD'
    links.new(pulp.outputs['Fac'],pulp_mix.inputs[0]);pulp_mix.inputs[1].default_value=.45
    links.new(fibre.outputs['Fac'],pulp_mix.inputs[2])
    board=nodes.new('ShaderNodeValToRGB');board.color_ramp.interpolation='EASE'
    board.color_ramp.elements[0].position=0.;board.color_ramp.elements[0].color=(.560,.495,.385,1)
    board.color_ramp.elements[1].position=1.;board.color_ramp.elements[1].color=(.680,.610,.480,1)
    links.new(pulp_mix.outputs[0],board.inputs[0])

    base=nodes.new('ShaderNodeMixRGB');base.blend_type='MIX'
    links.new(printed,base.inputs['Fac'])
    links.new(board.outputs['Color'],base.inputs['Color1'])
    links.new(ink_final.outputs['Color'],base.inputs['Color2'])

    # --- handling damage --------------------------------------------------
    # Fold scores: the blank darkens along the lines it was creased.
    worn=nodes.new('ShaderNodeMixRGB');worn.blend_type='MULTIPLY'
    worn.inputs['Color2'].default_value=(.74,.72,.66,1.)
    fold_shade=nodes.new('ShaderNodeMath');fold_shade.operation='MULTIPLY'
    links.new(fold.outputs['Result'],fold_shade.inputs[0]);fold_shade.inputs[1].default_value=.42
    links.new(fold_shade.outputs[0],worn.inputs['Fac'])
    links.new(base.outputs['Color'],worn.inputs['Color1'])
    # Crushed fibre along the edges: the board goes pale and fibrous where it
    # has been knocked about, which is most of what separates a used carton
    # from a rendered one.
    wear_fac=nodes.new('ShaderNodeMath');wear_fac.operation='MULTIPLY'
    links.new(fold.outputs['Result'],wear_fac.inputs[0]);wear_fac.inputs[1].default_value=.14
    edge_wear=nodes.new('ShaderNodeMixRGB');edge_wear.blend_type='MIX'
    edge_wear.inputs['Color2'].default_value=(.86,.82,.72,1.)
    links.new(wear_fac.outputs[0],edge_wear.inputs['Fac'])
    links.new(worn.outputs['Color'],edge_wear.inputs['Color1'])
    # Grime collects along the bottom edge, where the box has been stood on
    # and dragged across a desk.
    grime=nodes.new('ShaderNodeMapRange');grime.clamp=True
    grime.inputs['From Min'].default_value=body_bottom+.015;grime.inputs['From Max'].default_value=body_bottom
    grime.inputs['To Min'].default_value=0.;grime.inputs['To Max'].default_value=1.
    links.new(sep.outputs['Z'],grime.inputs['Value'])
    grime_fac=nodes.new('ShaderNodeMath');grime_fac.operation='MULTIPLY'
    links.new(grime.outputs['Result'],grime_fac.inputs[0]);grime_fac.inputs[1].default_value=.30
    dirty=nodes.new('ShaderNodeMixRGB');dirty.blend_type='MIX'
    dirty.inputs['Color2'].default_value=(.46,.41,.34,1.)
    links.new(grime_fac.outputs[0],dirty.inputs['Fac'])
    links.new(edge_wear.outputs['Color'],dirty.inputs['Color1'])
    # The groove under the lid is in shadow: a tuck lid casts a hard line on
    # the wall of the tray.
    seam=nodes.new('ShaderNodeMapRange');seam.clamp=True
    seam.inputs['From Min'].default_value=body_top-.0028;seam.inputs['From Max'].default_value=body_top-.0002
    seam.inputs['To Min'].default_value=0.;seam.inputs['To Max'].default_value=1.
    links.new(sep.outputs['Z'],seam.inputs['Value'])
    groove_fac=nodes.new('ShaderNodeMath');groove_fac.operation='MULTIPLY'
    links.new(seam.outputs['Result'],groove_fac.inputs[0]);groove_fac.inputs[1].default_value=.55
    groove=nodes.new('ShaderNodeMixRGB');groove.blend_type='MULTIPLY'
    groove.inputs['Color2'].default_value=(.52,.50,.47,1.)
    links.new(groove_fac.outputs[0],groove.inputs['Fac'])
    links.new(dirty.outputs['Color'],groove.inputs['Color1'])
    links.new(groove.outputs['Color'],bsdf.inputs['Base Color'])

    # Paper takes a soft sheen along the fibre; ink on uncoated board is matte
    # and uneven. Left uniform this is what reads as a laminated label.
    rough_board=_pbr_range(nodes,links,fibre.outputs['Fac'],.64,.80)
    rough_ink=_pbr_range(nodes,links,cover.outputs['Fac'],.70,.86)
    roughness=nodes.new('ShaderNodeMixRGB');roughness.blend_type='MIX'
    links.new(printed,roughness.inputs['Fac'])
    links.new(rough_board.outputs[0],roughness.inputs['Color1'])
    links.new(rough_ink.outputs[0],roughness.inputs['Color2'])
    # Grime and crushed fibre are both rougher than the sheet around them.
    rough_dirty=nodes.new('ShaderNodeMath');rough_dirty.operation='ADD'
    links.new(grime_fac.outputs[0],rough_dirty.inputs[0])
    links.new(wear_fac.outputs[0],rough_dirty.inputs[1])
    rough_final=nodes.new('ShaderNodeMath');rough_final.operation='ADD'
    links.new(roughness.outputs['Color'],rough_final.inputs[0])
    links.new(rough_dirty.outputs[0],rough_final.inputs[1])
    links.new(rough_final.outputs[0],bsdf.inputs['Roughness'])

    grain_bump=_pbr_bump(nodes,links,pulp_mix.outputs[0],.32,.00050)
    tooth_bump=_pbr_bump(nodes,links,tooth.outputs['Fac'],.18,.00013,grain_bump.outputs['Normal'])
    links.new(tooth_bump.outputs['Normal'],bsdf.inputs['Normal'])
    return material

_TEXTURE_DIR=_pcve_asset('')/'polyhaven'/'chalk_box_stack'


def _scanned_material(bpy,name,stem,tile_m,rotate_deg=0.,tint=None,rough_range=None,normal_strength=.7):
    """A Poly Haven scan (colour, roughness and OpenGL normal maps) at its real size.

    Box projection, so a 9 cm slab edge or a 12 mm set-square member gets wood
    on every face instead of one row of texels smeared across it. ``tile_m`` is
    the scan's published width; ``rotate_deg`` turns the grain about Z.
    """
    material=bpy.data.materials.new(name);material.use_nodes=True
    nodes=material.node_tree.nodes;links=material.node_tree.links
    bsdf=nodes['Principled BSDF']
    coord=nodes.new('ShaderNodeTexCoord');mapping=nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value=(1/tile_m,1/tile_m,1/tile_m)
    mapping.inputs['Rotation'].default_value=(0.,0.,math.radians(rotate_deg))
    links.new(coord.outputs['Object'],mapping.inputs['Vector'])

    def scan(kind,colour):
        node=nodes.new('ShaderNodeTexImage');node.projection='BOX';node.projection_blend=.18
        node.image=bpy.data.images.load(str(_TEXTURE_DIR/f'{stem}_{kind}_2k.jpg'),check_existing=True)
        if not colour:node.image.colorspace_settings.name='Non-Color'
        links.new(mapping.outputs['Vector'],node.inputs['Vector']);return node.outputs['Color']

    colour=scan('diff',True)
    if tint is not None:
        tinted=nodes.new('ShaderNodeVectorMath');tinted.operation='MULTIPLY'
        tinted.inputs[1].default_value=tint;links.new(colour,tinted.inputs[0]);colour=tinted.outputs['Vector']
    links.new(colour,bsdf.inputs['Base Color'])
    rough=scan('rough',False)
    if rough_range is not None:rough=_pbr_range(nodes,links,rough,*rough_range).outputs[0]
    links.new(rough,bsdf.inputs['Roughness'])
    normal=nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=normal_strength
    links.new(scan('nor_gl',False),normal.inputs['Color']);links.new(normal.outputs['Normal'],bsdf.inputs['Normal'])
    return material


# Poly Haven publishes oak_veneer_01 as a 1.83 m square and floor_tiles_06 as 3 m.
OAK_VENEER_M=1.83
FLOOR_TILES_M=3.
# Daylight comes through two windows in the left wall (x = -4), sills at desk
# height plus 14 cm; each pair is the window's extent along y.
CLASSROOM_WINDOWS=((-2.2,-.9),(-.4,.9))
WINDOW_SILL,WINDOW_HEAD=.90,2.40


def _build_workbench(bpy,scene):
    """The u_track_ball workbench, fitted to this scene's desk footprint.

    A 2.6 x 1.0 m slab at 0.76 m support height, matching the desk the physics
    cache, the camera and every ground-truth transform assume. The slab sits on
    an open steel frame with no apron, so no front skirt reads as a black bar
    across the bottom of frame.
    """
    from scene_geometry import TABLE_Z
    # Scanned oak veneer, the surface a school desk actually has, with the grain
    # along the slab. A procedural birch has wave bands that read as regular
    # dark stripes once the bench fills the foreground.
    top=_scanned_material(bpy,'Oak veneer worktop','oak_veneer_01',OAK_VENEER_M,rotate_deg=90.,rough_range=(.38,.62))
    steel=_powder_coated_steel(bpy,'Black powder coated steel',(.024,.031,.035))
    parts=[]

    def slab(name,location,size,material,bevel=.0):
        bpy.ops.mesh.primitive_cube_add(size=1,location=location)
        obj=bpy.context.object;obj.name=name;obj.dimensions=size
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        obj.data.materials.append(material)
        if bevel:
            mod=obj.modifiers.new('Manufactured edge','BEVEL');mod.width=bevel;mod.segments=3
            obj.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
        parts.append(obj);return obj

    slab('Birch worktop',(0,0,TABLE_Z-.045),(2.6,1.,.09),top,bevel=.004)
    for x in (-1.06,1.06):
        for y in (-.40,.40):
            slab('Steel leg',(x,y,(TABLE_Z-.09)/2),(.07,.07,TABLE_Z-.09),steel,bevel=.002)
    for y in (-.40,.40):
        slab('Steel lower brace',(0,y,.18),(2.26,.032,.032),steel,bevel=.002)
    bpy.context.view_layer.update()
    return parts


def _import_blackboard(bpy,scene):
    """Scanned blackboard against the wall.

    The GLB arrives already 3.63 x 0.065 x 1.63 m with the writing face towards
    -Y, so it only needs baking into world space and one translation: the back
    goes to the wall face (y=1.29) and the height is chosen so the bottom rail
    clears the bench. No rescaling, so the frame mouldings keep their proportions.

    The rail hangs at ``TABLE_Z - 0.10``. These numbers are measured under an
    orthographic view of the bench, where the hard floor is 0.527 m: below that
    the bench's far top edge -- 0.725 m in front of the
    board -- projects over the rail and cuts the board off along a hard line,
    with no moulding and no plaster under it. Note the gap on screen is much
    larger than the height difference suggests: the camera looks 13.7 deg down
    and across, so the same screen column meets the bench edge and the rail at
    world x values 0.626 m apart, and that sideways offset alone is worth
    0.227 m of screen height. Ten centimetres under the bench top leaves about
    130 px of plaster, which reads as a gap between two objects rather than as
    an empty band across the frame.
    """
    from mathutils import Matrix,Vector
    from scene_geometry import TABLE_Z
    path=_MODEL_DIR/'realistic_blackboard.glb'
    if not path.exists():raise FileNotFoundError(path)
    existing=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported=[obj for obj in bpy.data.objects if obj not in existing]
    parts=[obj for obj in imported if obj.type=='MESH']
    if not parts:raise RuntimeError('realistic_blackboard.glb contained no mesh geometry')
    bpy.context.view_layer.update()
    # Bake the whole hierarchy first; the glTF parents carry the asset transform.
    worlds={part:part.matrix_world.copy() for part in parts}
    for part in parts:
        part.data=part.data.copy();part.data.transform(worlds[part])
        part.parent=None;part.matrix_world=Matrix.Identity(4)
    for obj in imported:
        if obj.type!='MESH':bpy.data.objects.remove(obj,do_unlink=True)
    points=[vertex.co for part in parts for vertex in part.data.vertices]
    low=Vector(tuple(min(p[i] for p in points) for i in range(3)))
    high=Vector(tuple(max(p[i] for p in points) for i in range(3)))
    if min(high-low)<=0:raise RuntimeError('realistic_blackboard.glb has degenerate bounds')
    # The writing face points towards -Y, so the asset's +Y side is its back and
    # must meet the wall face (y=1.29) from the camera side; aligning the other
    # way buries the whole board 6.5 cm inside the wall and the wall occludes it.
    # ``rail`` is the one knob for how high the board hangs. The absolute floor
    # is 0.527 m under an orthographic view (see the docstring); below that the rail disappears behind the
    # bench. Raising it towards TABLE_Z opens the plaster band fast --
    # level with the bench top it is already a third of the frame.
    rail=TABLE_Z-.10
    shift=Vector((.10,1.29-high.y,rail-low.z))
    for index,part in enumerate(parts):
        part.data.transform(Matrix.Translation(shift));part.data.update()
        part.name=f'Blackboard {index:02d}'
    bpy.context.view_layer.update()
    return parts


def build_room(bpy,data):
    from mathutils import Vector
    scene=bpy.context.scene
    mat=lambda name,color,**kw:_material(bpy,name,color,**kw)
    bench=_bench_surface(bpy,'Worn blue-grey enamel',(.196,.272,.302),rough=.42)
    # Knockout lettering: bare board showing through the ink field, so it is
    # matte paper (a semi-gloss cream at rough .56 reads as moulded plastic
    # type standing on the panel).
    cream=mat('Carton knockout',(.862,.788,.585),rough=.76,bump=.06,bump_scale=520.,bump_distance=.00012)
    felt=mat('Charcoal eraser felt',(.045,.060,.060),rough=.92,bump=.18,bump_scale=360.,bump_distance=.0008)
    timber=_eraser_wood(bpy)
    eraser_felt=_eraser_felt(bpy)
    wall=mat('Muted mineral plaster',(.470,.450,.408),rough=.78,bump=.035,bump_scale=220.,bump_distance=.0003)
    # Scanned grey checker tiles, a common classroom floor.
    floor=_scanned_material(bpy,'Classroom floor tiles','floor_tiles_06',FLOOR_TILES_M,rough_range=(.45,.75))
    slate=_slate_surface(bpy)
    walnut=mat('Walnut board trim',(.098,.058,.040),rough=.42,grain=(1.,6.,1.),bump=.08,bump_scale=180.)
    # Board rules and set-squares are varnished hardwood; a polished
    # metallic ochre would read as a gold ornament.
    drawing_wood=_scanned_material(bpy,'Varnished beech drawing tools','oak_veneer_01',OAK_VENEER_M*.5,
                            tint=(1.08,.98,.80),rough_range=(.30,.45),normal_strength=.4)
    paper=mat('Scribbled worksheet',(.795,.755,.640),rough=.72,bump=.02,bump_scale=520.,bump_distance=.00008)

    def cube(name,loc,size,material,parent=None,bevel=.003,rotation=None):
        o=bpy.data.objects.new(name,_cube_mesh(bpy,name,size))
        scene.collection.objects.link(o);o.location=loc;o.data.materials.append(material)
        if bevel:
            mod=o.modifiers.new('Soft manufactured edges','BEVEL');mod.width=bevel;mod.segments=3
            o.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
        if rotation is not None:o.rotation_euler=rotation
        if parent:o.parent=parent
        return o
    def text(name,string,loc,size,material,parent=None,rotation=(math.pi/2,0,0)):
        # 0.02 mm extrude: enough for Cycles to shade a solid, far too little
        # for the type to catch a rim highlight of its own at this framing.
        curve=bpy.data.curves.new(name,'FONT');curve.body=string;curve.size=size;curve.align_x='CENTER';curve.extrude=.00002
        o=bpy.data.objects.new(name,curve);scene.collection.objects.link(o);o.location=loc;o.rotation_euler=rotation;curve.materials.append(material)
        if parent:o.parent=parent
        return o

    cube('Classroom floor',(0,0,-.06),(8,5,.12),floor)
    cube('Sage plaster wall',(0,1.35,1.5),(8,.12,3),wall)
    # Close the classroom: side walls, the wall behind the camera and a ceiling.
    # The camera sees none of them, but the light does -- in an open box the
    # ceiling panels and the windows have nothing to bounce off, and the shadows
    # under the cartons go grey and directionless. Windows are on the left wall,
    # as in most classrooms (pupils facing the board get daylight from the left).
    # Every wall runs 12 cm below the floor top so it overlaps the floor slab:
    # with daylight outside, a seam where two boxes only touch along an edge
    # shows as a pinhole of light.
    y0,y1=-2.5,1.41
    for name,loc,size in (('Right wall',(4.06,(y0+y1)/2,1.44),(.12,y1-y0+.24,3.12)),
                          ('Back wall behind camera',(0,y0-.06,1.44),(8.24,.12,3.12)),
                          ('Ceiling',(0,(y0+y1)/2,3.06),(8.24,y1-y0+.24,.12))):
        cube(name,loc,size,wall,bevel=0)
    sill,head=WINDOW_SILL,WINDOW_HEAD
    cube('Window wall below sills',(-4.06,(y0+y1)/2,(sill-.12)/2),(.12,y1-y0+.24,sill+.12),wall,bevel=0)
    cube('Window wall above heads',(-4.06,(y0+y1)/2,(head+3.)/2),(.12,y1-y0+.24,3.-head),wall,bevel=0)
    edges=[y0-.12,*[e for opening in CLASSROOM_WINDOWS for e in opening],y1+.12]
    for a,b in zip(edges[::2],edges[1::2]):
        cube('Window wall pier',(-4.06,(a+b)/2,(sill+head)/2),(.12,b-a,head-sill),wall,bevel=0)
    for a,b in CLASSROOM_WINDOWS:
        cube('Window sill board',(-3.97,(a+b)/2,sill-.012),(.10,b-a+.06,.024),paper,bevel=.002)
    ground=cube('Ground outside',(0,0,-.30),(60,60,.2),mat('Paving outside',(.24,.23,.21),rough=.9),bevel=0)
    ground.visible_camera=False
    _build_workbench(bpy,scene)
    # The desk stands 0.79 m clear of the wall face (y=1.29) and is left open;
    # from the camera on the left the wall base under the desk edge falls
    # outside the frame.
    # The scanned blackboard GLB is wide enough to fill this framing.
    _import_blackboard(bpy,scene)

    # Ruler and triangular set-square are behind the action, outside the contact lane.
    cube('Meter rule',(.68,.33,.775),(.48,.055,.012),drawing_wood)
    for i in range(25):cube('Ruler tick',(.45+i*.018,.31,.782),(.001,.018 if i%5==0 else .009,.001),bench,bevel=0)
    verts=[(.62,.33,.79),(.92,.33,.79),(.92,.33,1.04)]
    for i in range(3):
        a,b=Vector(verts[i]),Vector(verts[(i+1)%3]);o=cube('Standing geometry triangle',(a+b)/2,(.012,.015,(b-a).length),drawing_wood)
        o.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler()

    # --- bench dressing --------------------------------------------------
    # A bare slab with two props reads as a clean product shot. A stack of
    # worksheets, a pen, loose chalk and crumbs give the surface a working
    # history and, more importantly, real contact cues. The pen and the chalk
    # are the supplied GLB assets with their own baked materials; there is no
    # chalk-powder film, because at this distance a translucent film reads as
    # white haze on the bench rather than powder.
    def sheet(name,loc,size,angle,material,parent=None):
        return cube(name,loc,size,material,parent,bevel=.0008,rotation=(0,0,angle))
    sheet('Worksheet stack 0',(.455,.335,.7608),(.212,.288,.0010),.19,paper)
    sheet('Worksheet stack 1',(.462,.331,.7619),(.212,.288,.0010),.165,paper)
    top=sheet('Worksheet stack 2',(.451,.339,.7630),(.212,.288,.0010),.205,paper)
    for i in range(6):
        cube('Ruled line',(0,(i-2.0)*.033,.0007),(.176,.0006,.0002),felt,top,bevel=0)
    # the_pen.glb lying across the worksheet stack, bottom flush with the top
    # sheet rather than sunk into it.
    _import_prop(bpy,scene,'the_pen.glb','Pencil',.143,(.372,.268,.7635),yaw=-.42)

    def chalk_stick(name,x,y,length,yaw):
        return _import_prop(bpy,scene,'chalk.glb',name,length,(x,y,.76),yaw=yaw,solo=True)
    chalk_stick('Loose chalk 4',.332,.152,.058,.34)
    # One yellow stick keeps the two-colour cue; the asset ships with a base
    # texture, so the yellow is a multiply tint over it (see _tint_prop).
    yellow=chalk_stick('Loose chalk 5',.298,.216,.046,-1.15)
    _tint_prop(yellow,(.98,.82,.32),'Yellow chalk')
    # No short stub: the asset scales its diameter with its length, so a 26 mm
    # stick comes out thin and reads as a different, slighter object than the
    # two beside it.
    # Crumbs: the little wedges that break off a stick and are never swept up.
    chalk_stick('Chalk crumb 3',.268,.246,.007,.9)
    chalk_stick('Chalk crumb 4',.352,.204,.005,-1.3)
    # A single stick is enough on the left, and it belongs back against the
    # board rather than out towards the viewer; the rest of that end of the
    # bench is given to a bottle someone put down.
    # Clear of the bottle: against its base the stick read as a spout on it.
    chalk_stick('Loose chalk 0',-.74,.33,.058,-.55)
    # Standing on its base, as a bottle left on a bench would be, with the
    # label turned a little towards the camera instead of square to it.
    bottle=_import_prop(bpy,scene,'water_bottle__plastic_bottle.glb','Water bottle',
                        .208,(-.455,.190,.7600),yaw=.30,stand=True)

    objects={}
    # Deep, slightly muted colours: a washed-out tint reads as a toy, and these
    # are the colours a school actually buys.
    prints=[(.055,.215,.285),(.430,.085,.060),(.060,.125,.360),(.400,.215,.030),(.095,.255,.085)]
    for i in range(data['geometry']['count']):
        root=bpy.data.objects.new(f'box_{i}',None);scene.collection.objects.link(root);objects[f'box_{i}']=root
        w,d,h=data['geometry']['box_size']
        # One sheet of printed board per carton. The ink is masked into the
        # material (see _carton_board) rather than glued on as thin plates:
        # a plate owns its bevel highlight and its own gloss, and at this viewing
        # distance that is exactly what turns print into a stuck-on plastic label.
        # The blank is a body, a groove and a lid, so the carton reads as a
        # folded box instead of a moulded block.
        mesh,parts=_carton_mesh(bpy,f'Paperboard carton {i}',(w,d,h),phase=i*.37)
        board=_carton_board(bpy,f'Carton board {i}',prints[i%5],(w,d,h),phase=i*.37,parts=parts)
        carton=bpy.data.objects.new('Paperboard carton',mesh)
        scene.collection.objects.link(carton);carton.data.materials.append(board);carton.parent=root
        # 0.35 mm edge, not 1.5 mm: a folded carton has a crease, not a fillet.
        bevel=carton.modifiers.new('Soft manufactured edges','BEVEL');bevel.width=.00035;bevel.segments=2
        carton.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
        body_mid=(parts['body_bottom']+parts['body_top'])/2
        # Lettering stays geometry (a font) but nearly flush: 0.02 mm extrude
        # and 0.25 mm off the board, so it reads as ink knocked out of the
        # printed sheet rather than moulded plastic type standing on it.
        text('Carton lettering','CHALK  /  12',(0,-d/2-.00025,body_mid+.007),.012,cream,root)
        text('Lid lettering','DUSTLESS',(0,-.012,parts['lid_top']+.00025),.013,cream,root,rotation=(0,0,0))
    root=bpy.data.objects.new('eraser',None);scene.collection.objects.link(root);objects['eraser']=root
    cube('Felt sole',(0,0,-.009),(.13,.075,.014),eraser_felt,root,.0018)
    # 4 mm chamfer: a softer 6 mm round reads as a moulded plastic soap bar,
    # real beech handles keep a machined edge.
    cube('Wooden grip',(0,0,.006),(.13,.075,.018),timber,root,.004)
    for y in [-.023,0,.023]:cube('Felt channels',(0,y,-.0162),(.122,.003,.0006),bench,root,.0001)
    return objects


def configure_lighting(bpy,scene):
    """A classroom's own light: ceiling LED troffers and daylight from the windows.

    Invisible area cards under a grey world would light the bench evenly from
    nowhere and leave the cartons on faint, directionless shadows. Every
    source is something the room has: six 1.2 x 0.3 m LED troffers in the
    ceiling, whose diffusers are the emitters themselves, and an overcast sky
    seen through the two left-hand windows, with a portal in each opening.
    """
    import math
    from mathutils import Vector
    world=bpy.data.worlds.new('Overcast sky');world.use_nodes=True
    nodes,links=world.node_tree.nodes,world.node_tree.links
    sky=nodes.new('ShaderNodeTexSky');sky.sky_type='NISHITA';sky.sun_disc=False
    sky.sun_elevation=math.radians(32.);sky.sun_rotation=math.radians(-110.)
    sky.air_density,sky.dust_density=1.,4.
    links.new(sky.outputs['Color'],nodes['Background'].inputs['Color'])
    nodes['Background'].inputs['Strength'].default_value=DAYLIGHT_STRENGTH
    scene.world=world
    for a,b in CLASSROOM_WINDOWS:
        data=bpy.data.lights.new('Window sky portal','AREA');data.shape='RECTANGLE'
        data.size,data.size_y=b-a,WINDOW_HEAD-WINDOW_SILL;data.cycles.is_portal=True
        portal=bpy.data.objects.new('Window sky portal',data);scene.collection.objects.link(portal)
        portal.location=(-4.13,(a+b)/2,(WINDOW_SILL+WINDOW_HEAD)/2)
        portal.rotation_euler=(Vector((1.,0.,0.))).to_track_quat('-Z','Y').to_euler()

    housing=bpy.data.materials.new('Troffer housing');housing.use_nodes=True
    housing.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.80,.80,.78,1.)
    housing.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.45
    diffuser=bpy.data.materials.new('Troffer opal diffuser');diffuser.use_nodes=True
    bsdf=diffuser.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value=(.9,.9,.9,1.);bsdf.inputs['Roughness'].default_value=.6
    set_shader_input(bsdf,'Emission Color',(1.,.955,.90,1.))   # about 4000 K
    set_shader_input(bsdf,'Emission Strength',TROFFER_STRENGTH)
    for x in (-2.4,0.,2.4):
        for y in (-1.45,.15):
            for name,loc,size,material in (('Troffer housing',(x,y,2.985),(1.22,.32,.03),housing),
                                           ('Troffer diffuser',(x,y,2.968),(1.18,.28,.004),diffuser)):
                bpy.ops.mesh.primitive_cube_add(size=1,location=loc)
                obj=bpy.context.object;obj.name=name;obj.dimensions=size
                bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
                obj.data.materials.append(material)


# Overcast-sky strength behind the windows and troffer diffuser radiance; with
# the exposure in render_quality these put the bench at a classroom's level.
DAYLIGHT_STRENGTH=.6
TROFFER_STRENGTH=14.
