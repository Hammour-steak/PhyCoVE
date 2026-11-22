"""Replayed bodies (steel bottle, mesh pen cup, ballpoint) and the workstation they stand on.

The room around the desk -- window wall, daylight, the notebook stack that
stands in for the telephone collider -- is built by appearance/open_office.py.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math
from scene_geometry import (KETTLE_PROFILE, KETTLE_COM_Z, KETTLE_SCALE, kettle_clamp_xy,
                            HOLDER_COM_Z, BOTTLE_MODEL_BOTTOM, CUP_MODEL_BOTTOM, CUP_SCALE, CUP_VSCALE)
import open_office

MODELS = _pcve_asset('models')
TEXTURES = _pcve_asset('polyhaven/office_desk_kettle_tip')

# The bottle model is an insulated steel bottle with a flip-spout lid; its body
# texture carries a printed brand name. The body is shaded instead as plain
# satin powder coat over steel (0.90 kg is a full 0.5 l insulated steel bottle
# of this size). Lid plastic and the chrome collar stay as authored.
BOTTLE_BODY_MATERIAL = '02_-_Default'
BOTTLE_COAT = (.50, .46, .38)           # linear sRGB: warm off-white

# Parts of the furnished-desk GLB that stay: the desk itself and the computer
# kit on its right half. Everything else is dropped -- see import_desk.
DESK_KEEP = ('deskoffice', 'keyboard', 'monitor', 'mouse')


def _bsdf(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def plain_material(bpy, name, color, roughness, metallic=0., coat=0., bump_scale=0., bump_strength=0.):
    """A uniform paint/plastic, optionally with a fine orange-peel bump."""
    m = bpy.data.materials.new(name); m.use_nodes = True
    nodes, links = m.node_tree.nodes, m.node_tree.links
    bs = _bsdf(m)
    bs.inputs['Base Color'].default_value = (*color, 1)
    bs.inputs['Roughness'].default_value = roughness
    bs.inputs['Metallic'].default_value = metallic
    if coat:
        bs.inputs['Coat Weight'].default_value = coat
        bs.inputs['Coat Roughness'].default_value = .12
    if bump_scale:
        coord = nodes.new('ShaderNodeTexCoord'); noise = nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = bump_scale; noise.inputs['Detail'].default_value = 2.
        links.new(coord.outputs['Object'], noise.inputs['Vector'])
        bump = nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = bump_strength
        bump.inputs['Distance'].default_value = .0002
        links.new(noise.outputs['Fac'], bump.inputs['Height']); links.new(bump.outputs['Normal'], bs.inputs['Normal'])
    return m


def oak_desk_top(bpy):
    """Matt-lacquered oak veneer (Poly Haven oak_veneer_04, a 1 m scan) at true size.

    The texture is read through the 'WorldBox' UV map that restyle_desk bakes
    from world metres (open_office.world_uv): one UV unit is one metre of
    veneer, the grain runs along the desk's long (y) side, the way a veneered
    top is laid up, and the tile edges sit just outside the visible top
    (x = -0.46 and y = 1.12, past its front and back edges). Reading the
    textures through a real UV map -- rather than through object coordinates
    -- keeps the normal map's tangent frame consistent with the texture: the
    GLB's own UVs fan out from the cable grommet, and their tangents drew the
    fan's triangle edges as bright lines in the sheen.
    """
    m = bpy.data.materials.new('Matt-lacquered oak veneer desk top'); m.use_nodes = True
    nodes, links = m.node_tree.nodes, m.node_tree.links
    bs = _bsdf(m)
    uv = nodes.new('ShaderNodeUVMap'); uv.uv_map = open_office.WORLD_UV

    def tex(kind, colour):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(TEXTURES / f'oak_veneer_04_{kind}_2k.jpg'), check_existing=True)
        node.image.colorspace_settings.name = 'sRGB' if colour else 'Non-Color'
        links.new(uv.outputs['UV'], node.inputs['Vector'])
        return node
    diff = tex('diff', True)
    # A clear matt lacquer deepens raw veneer a little.
    tone = nodes.new('ShaderNodeHueSaturation')
    tone.inputs['Saturation'].default_value = 1.08; tone.inputs['Value'].default_value = .86
    links.new(diff.outputs['Color'], tone.inputs['Color']); links.new(tone.outputs['Color'], bs.inputs['Base Color'])
    rough = tex('rough', False)
    remap = nodes.new('ShaderNodeMapRange')
    remap.inputs['To Min'].default_value, remap.inputs['To Max'].default_value = .48, .62
    links.new(rough.outputs['Color'], remap.inputs['Value']); links.new(remap.outputs['Result'], bs.inputs['Roughness'])
    nor = tex('nor_gl', False)
    nmap = nodes.new('ShaderNodeNormalMap'); nmap.inputs['Strength'].default_value = .35
    nmap.uv_map = open_office.WORLD_UV
    links.new(nor.outputs['Color'], nmap.inputs['Color']); links.new(nmap.outputs['Normal'], bs.inputs['Normal'])
    return m


def _oak_uv(co, axis):
    """World position -> veneer UV: grain along y, tile edges off the visible top."""
    if axis == 2:
        return 1.12 - co.y, co.x + .46
    return (1.12 - co.y, co.z) if axis == 0 else (co.x + .46, co.z)


def import_desk(bpy):
    """The desk, keyboard, monitor and mouse of the furnished-desk GLB.

    Feet on z=0 exactly as before (the solver's DESK_Z is measured off this
    placement). Dropped: the telephone (its collider is carried by the
    notebook stack, open_office.notebook_stack), the three drawer units, the
    document rack and the file boxes on top of the drawers, the cubicle
    partitions with their pinned notes, the side cabinet, the PC tower, the
    office chair and the loose clutter. None of the dropped pieces is ever
    touched by a moving body in any of the six cases (their solver boxes stay;
    see the README for the measured gaps), and this is an open-plan bench desk
    by a window, not a cubicle.
    """
    from mathutils import Vector, Matrix
    path = MODELS / 'office_desk.glb'
    if not path.is_file(): raise FileNotFoundError(f'Missing local asset: {path}')
    previous = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    imported = set(bpy.data.objects) - previous
    meshes = [o for o in imported if o.type == 'MESH']
    transforms = {o: o.matrix_world.copy() for o in meshes}
    # The fit is computed over the WHOLE model, as before, so the desktop stays
    # at the measured DESK_Z whatever is dropped below.
    points = [transforms[o] @ Vector(c) for o in meshes for c in o.bound_box]
    low = Vector([min(p[i] for p in points) for i in range(3)])
    fit = Matrix.Translation(Vector([0, 0, -low.z]))
    kept = []
    for o in meshes:
        if not any(k in o.name.lower() for k in DESK_KEEP):
            continue
        o.parent = None
        o.matrix_world = Matrix.Identity(4)
        o.data = o.data.copy()
        o.data.transform(fit @ transforms[o])
        if 'keyboard' in o.name.lower():
            # 3 cm towards the monitor, as KEYBOARD_BOX in the solver.
            o.data.transform(Matrix.Translation(Vector([0, -0.03, 0])))
        kept.append(o)
    for o in list(imported):
        if o not in kept:
            bpy.data.objects.remove(o, do_unlink=True)
    restyle_desk(bpy, kept)
    bpy.context.view_layer.update()
    return kept


def restyle_desk(bpy, meshes):
    """Real materials for the kept GLB parts (the GLB ships flat colours only)."""
    oak = oak_desk_top(bpy)
    frame = plain_material(bpy, 'White powder-coated steel frame', (.80, .80, .78), .38,
                           bump_scale=700., bump_strength=.05)
    keys = plain_material(bpy, 'Graphite keyboard plastic', (.030, .031, .034), .52,
                          bump_scale=2500., bump_strength=.04)
    screen = plain_material(bpy, 'Monitor screen glass', (.004, .004, .005), .06)
    bezel = plain_material(bpy, 'Black monitor plastic', (.012, .012, .013), .45)
    stand = plain_material(bpy, 'Anodised aluminium stand', (.60, .60, .62), .32, metallic=1.)
    mouse = plain_material(bpy, 'White mouse plastic', (.72, .72, .70), .35)
    for o in meshes:
        n = o.name.lower(); mats = [s.material.name if s.material else '' for s in o.material_slots]
        if 'deskoffice' in n:
            # MI_Object_62_1 is the top slab, MI_Object_51 its edge band; the
            # legs and feet are the steel frame.
            new = oak if any(k in mats[0] for k in ('Object_62', 'Object_51')) else frame
            if new is oak:
                open_office.world_uv(o, _oak_uv)
        elif 'keyboard' in n:
            new = keys
        elif 'monitor' in n:
            new = screen if 'Object_67' in mats[0] else bezel if 'Object_74' in mats[0] else stand
        else:
            new = mouse
        for slot in o.material_slots:
            slot.material = new
        for poly in o.data.polygons:
            poly.use_smooth = 'deskoffice' not in n


def import_pen_cup(bpy):
    """The pen cup GLB, scaled to the solver's cup: body kept, factory pens dropped.

    The downloaded model ships with its own pens, scissors and clips; the scene
    simulates exactly one pen (the_pen.glb), so only the cup itself -- the wide
    cylinder segments and the two rims -- survives the import.
    """
    from mathutils import Vector, Matrix
    path = MODELS / 'pen_holder.glb'
    if not path.is_file(): raise FileNotFoundError(f'Missing local asset: {path}')
    previous = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    imported = set(bpy.data.objects) - previous
    meshes = [o for o in imported if o.type == 'MESH']
    keep = []
    for o in meshes:
        pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
        lo = Vector([min(p[i] for p in pts) for i in range(3)])
        hi = Vector([max(p[i] for p in pts) for i in range(3)])
        if hi.x - lo.x > 1.0 and hi.y - lo.y > 1.0:      # the cup body and rims
            keep.append((o, lo, hi))
    if not keep: raise ValueError('pen_holder.glb: cup body not found')
    lo = Vector([min(l[i] for _, l, _ in keep) for i in range(3)])
    hi = Vector([max(h[i] for _, _, h in keep) for i in range(3)])
    centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, 0))
    # Scale to the solver's outer radius (height stretched to HOLDER_HEIGHT);
    # the cup's outer bottom lands on the desktop, and the local frame is
    # shifted so the object origin sits at the COM the solver uses: the bottom
    # maps to -HOLDER_COM_Z, the rim to HOLDER_HEIGHT - HOLDER_COM_Z.
    shift_z = CUP_MODEL_BOTTOM * CUP_VSCALE - HOLDER_COM_Z
    fit = (Matrix.Translation(Vector([0, 0, shift_z])) @
           Matrix.Diagonal(Vector([CUP_SCALE, CUP_SCALE, CUP_VSCALE, 1.0])) @
           Matrix.Translation(-centre))
    steel = plain_material(bpy, 'Black powder-coated steel mesh', (.016, .016, .017), .40,
                           bump_scale=900., bump_strength=.04)
    for o, _, _ in keep:
        mat = o.matrix_world.copy(); o.parent = None
        o.matrix_world = Matrix.Identity(4)
        o.data = o.data.copy()
        o.data.transform(fit @ mat)
        for poly in o.data.polygons: poly.use_smooth = True
        for slot in o.material_slots: slot.material = steel
    for o in imported:
        if o.type != 'MESH' or o not in [k[0] for k in keep]:
            bpy.data.objects.remove(o, do_unlink=True)
    for o, _, _ in keep:
        o.location = (0, 0, 0)
    bpy.context.view_layer.update()
    return keep


def import_pen(bpy):
    """the_pen.glb at true size, rotated upright, origin at its middle."""
    from mathutils import Vector, Matrix
    path = MODELS / 'the_pen.glb'
    if not path.is_file(): raise FileNotFoundError(f'Missing local asset: {path}')
    previous = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    imported = set(bpy.data.objects) - previous
    meshes = [o for o in imported if o.type == 'MESH']
    transforms = {o: o.matrix_world.copy() for o in meshes}
    points = [transforms[o] @ Vector(c) for o in meshes for c in o.bound_box]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, (lo.z + hi.z) / 2))
    # The pen models along +X; stand it up (+X -> +Z) about its midpoint.
    fit = Matrix.Rotation(math.pi / 2, 4, 'Y') @ Matrix.Translation(-centre)
    for o in meshes:
        mat = o.matrix_world.copy(); o.parent = None
        o.matrix_world = Matrix.Identity(4)
        o.data = o.data.copy()
        o.data.transform(fit @ mat)
    for o in imported:
        if o.type != 'MESH': bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.update()
    return meshes


def powder_coat(bpy):
    """Satin powder coat over steel: a paint, so dielectric, with orange peel."""
    return plain_material(bpy, 'Powder-coated steel bottle', BOTTLE_COAT, .44,
                          bump_scale=900., bump_strength=.10)


def make_kettle(bpy):
    """water_bottle__plastic_bottle.glb, uniform scale, over the matching hull.

    KETTLE_PROFILE is the bottle's own measured silhouette times one uniform
    scale (see scene_geometry), so the skin fit is a pure uniform scaling --
    the bottle keeps its true proportions, no radial stretch. The frame is
    shifted so the model's bottom plane lands on the hull's bottom ring
    (0.002 - KETTLE_COM_Z, the surface that rests on the desk). What is left
    is a containment clamp: every skin vertex is pulled inside the hull's
    cross-section at its own height, so the replay can never show the skin
    poking through the collision body it is standing in for. The clamp is
    essentially a no-op on the body (the profile IS the skin's envelope);
    it bites only on the flip spout's square cross-section, by < 1 mm.
    Origin at the solver COM; the widest body mesh is the replayed object,
    cap and shoulder ring parented to it. The printed body material is
    replaced by plain powder coat (no lettering).
    """
    from mathutils import Vector, Matrix
    path = MODELS / 'water_bottle__plastic_bottle.glb'
    if not path.is_file(): raise FileNotFoundError(f'Missing local asset: {path}')
    previous = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    imported = set(bpy.data.objects) - previous
    meshes = [o for o in imported if o.type == 'MESH']
    transforms = {o: o.matrix_world.copy() for o in meshes}
    points = [transforms[o] @ Vector(c) for o in meshes for c in o.bound_box]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, 0))
    hull_bottom_z = KETTLE_PROFILE[0][1] - KETTLE_COM_Z
    shift_z = hull_bottom_z - BOTTLE_MODEL_BOTTOM * KETTLE_SCALE
    fit = (Matrix.Translation(Vector([0, 0, shift_z])) @
           Matrix.Diagonal(Vector([KETTLE_SCALE, KETTLE_SCALE, KETTLE_SCALE, 1.0])) @
           Matrix.Translation(-centre))
    coat = powder_coat(bpy)
    for o in meshes:
        mat = o.matrix_world.copy(); o.parent = None
        o.matrix_world = Matrix.Identity(4)
        o.data = o.data.copy()
        o.data.transform(fit @ mat)
        for v in o.data.vertices:
            x, y = kettle_clamp_xy(v.co.x, v.co.y, v.co.z)
            if x != v.co.x or y != v.co.y:
                v.co.x, v.co.y = x, y
        for poly in o.data.polygons: poly.use_smooth = True
        for slot in o.material_slots:
            if slot.material and slot.material.name.split('.')[0] == BOTTLE_BODY_MATERIAL:
                slot.material = coat
            elif slot.material and slot.material.use_nodes:
                bs = _bsdf(slot.material)
                if not bs.inputs['Roughness'].is_linked:
                    # Matte lid plastic and the chrome collar as authored, with
                    # the roughness floored so the collar never goes mirror-harsh.
                    bs.inputs['Roughness'].default_value = max(.22, min(.6, bs.inputs['Roughness'].default_value))
    if not any(s.material is coat for o in meshes for s in o.material_slots):
        raise ValueError(f'water_bottle__plastic_bottle.glb: no {BOTTLE_BODY_MATERIAL} body material to replace')
    for o in imported:
        try:
            if o.type != 'MESH':
                bpy.data.objects.remove(o, do_unlink=True)
        except ReferenceError:
            continue
    for o in meshes:
        o.location = (0, 0, 0)
    bpy.context.view_layer.update()
    body = next(o for o in meshes if any(s.material is coat for s in o.material_slots))
    for extra in meshes:
        if extra is not body:
            extra.parent = body
    return body


def make_dynamic_objects(bpy):
    """The replayed bodies, each modelled around its solver COM."""
    objects = {}
    objects['kettle'] = make_kettle(bpy)
    cup = import_pen_cup(bpy)
    objects['pen_holder'] = cup[0][0]
    for extra in cup[1:]:
        extra[0].parent = objects['pen_holder']
    pen = import_pen(bpy)
    objects['pen'] = pen[0]
    for extra in pen[1:]:
        extra.parent = objects['pen']
    return objects


def build_environment(bpy, scene):
    """Desk + room. Returns the room description used by the render checks."""
    desk = import_desk(bpy)
    room = open_office.build_office(bpy, scene, TEXTURES)
    room['desk_objects'] = [o.name for o in desk]
    room['computer'] = [dict(name=o.name, objects=[o.name], **_bbox(o))
                        for o in desk if any(k in o.name.lower() for k in ('monitor', 'mouse'))]
    room['keyboard'] = [dict(name=o.name, objects=[o.name], **_bbox(o))
                        for o in desk if 'keyboard' in o.name.lower()]
    return room


def _bbox(o):
    from mathutils import Vector
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return dict(bbox_min=[min(p[i] for p in pts) for i in range(3)],
                bbox_max=[max(p[i] for p in pts) for i in range(3)])
