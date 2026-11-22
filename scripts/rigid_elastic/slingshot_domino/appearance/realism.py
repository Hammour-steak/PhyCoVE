"""Measured-scale surface detail; does not modify physical shapes or transforms.

Called by the remote renderer only. All distances below are metres. Plywood
photographs cover 0.5 m; the laminate edge is a shader, not extra collision mesh.
"""
import math
import bpy


def material(name, color, roughness=.5, metallic=0):
    m=bpy.data.materials.new(name);m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Roughness'].default_value=roughness
    bs.inputs['Metallic'].default_value=metallic
    return m


def noise(nt, scale, detail=2, vector=None):
    n=nt.nodes.new('ShaderNodeTexNoise');n.inputs['Scale'].default_value=scale
    n.inputs['Detail'].default_value=detail
    if vector:nt.links.new(vector,n.inputs['Vector'])
    return n.outputs['Fac']


def ramp(nt, source, lo, hi, amin=0, amax=1):
    n=nt.nodes.new('ShaderNodeMapRange');n.clamp=True
    n.inputs['From Min'].default_value=amin;n.inputs['From Max'].default_value=amax
    n.inputs['To Min'].default_value=lo;n.inputs['To Max'].default_value=hi
    nt.links.new(source,n.inputs['Value']);return n.outputs['Result']


def bump(nt, height, bs, distance, strength=.2, normal=None):
    n=nt.nodes.new('ShaderNodeBump');n.inputs['Distance'].default_value=distance
    n.inputs['Strength'].default_value=strength;nt.links.new(height,n.inputs['Height'])
    if normal:nt.links.new(normal,n.inputs['Normal'])
    nt.links.new(n.outputs['Normal'],bs.inputs['Normal'])


def wood_material(assets, name, tint=(1,1,1), ply=False, end=False):
    m=material(name,(.45,.28,.13),.53);nt=m.node_tree;bs=nt.nodes.get('Principled BSDF')
    bs.inputs['IOR'].default_value=1.47;bs.inputs['Specular IOR Level'].default_value=.32
    uv=nt.nodes.new('ShaderNodeTexCoord').outputs['UV'];normal=None
    for kind,socket in [('diff','Base Color'),('rough','Roughness'),('nor_gl','Normal')]:
        tex=nt.nodes.new('ShaderNodeTexImage')
        tex.image=bpy.data.images.load(str(assets/'plywood'/('plywood_'+kind+'_4k.jpg')),check_existing=True)
        nt.links.new(uv,tex.inputs['Vector'])
        if kind!='diff':tex.image.colorspace_settings.name='Non-Color'
        if kind=='diff':
            tintnode=nt.nodes.new('ShaderNodeMixRGB');tintnode.blend_type='MULTIPLY'
            tintnode.inputs[0].default_value=1;tintnode.inputs[2].default_value=(*tint,1)
            nt.links.new(tex.outputs['Color'],tintnode.inputs[1]);color=tintnode.outputs[0]
            if ply:
                coord=nt.nodes.new('ShaderNodeTexCoord');xyz=nt.nodes.new('ShaderNodeSeparateXYZ')
                nt.links.new(coord.outputs['Object'],xyz.inputs[0])
                # Thirteen alternating veneer layers across the unchanged 19 mm fork.
                phase=nt.nodes.new('ShaderNodeMath');phase.operation='MULTIPLY_ADD'
                phase.inputs[1].default_value=13*math.pi/.019;phase.inputs[2].default_value=math.pi/2
                nt.links.new(xyz.outputs['X'],phase.inputs[0]);sine=nt.nodes.new('ShaderNodeMath');sine.operation='SINE'
                nt.links.new(phase.outputs[0],sine.inputs[0]);levels=ramp(nt,sine.outputs[0],.78,1.06,-1,1)
                mult=nt.nodes.new('ShaderNodeMixRGB');mult.blend_type='MULTIPLY';mult.inputs[0].default_value=.82
                nt.links.new(color,mult.inputs[1]);nt.links.new(levels,mult.inputs[2]);color=mult.outputs[0]
            nt.links.new(color,bs.inputs['Base Color'])
        elif kind=='rough':
            nt.links.new(ramp(nt,tex.outputs['Color'],.40 if not ply else .51,.65 if not ply else .75),bs.inputs['Roughness'])
        else:
            norm=nt.nodes.new('ShaderNodeNormalMap');norm.inputs['Strength'].default_value=.13 if not ply else .16
            nt.links.new(tex.outputs['Color'],norm.inputs['Color']);normal=norm.outputs['Normal']
            nt.links.new(normal,bs.inputs['Normal'])
    if end:
        # Fine cut pores in the end grain, no displacement of the support plane.
        coord=nt.nodes.new('ShaderNodeTexCoord')
        bump(nt,noise(nt,7500,1,coord.outputs['Object']),bs,.000018,.2,normal)
    m['texture_width_m']=.5;m['geometric_displacement_m']=0.
    return m


def wood_uv(o, grain='Z', offset=(.31,.37), edge=None, end=None):
    """Planar metric UVs before bevel; long fibres follow the actual timber axis."""
    uv=o.data.uv_layers.active or o.data.uv_layers.new(name='Half-metre measured wood UV')
    for p in o.data.polygons:
        n=p.normal
        if edge is not None and abs(n.x)<.9:p.material_index=1
        if end is not None and abs(n.z)>.9:p.material_index=2
        for li in p.loop_indices:
            v=o.data.vertices[o.data.loops[li].vertex_index].co
            if grain=='Z' and abs(n.z)>.9:a,b=v.y,v.x
            elif grain=='Z':a,b=v.z,(v.y if abs(n.x)>.5 else v.x)
            else:a,b=v.x,(v.y if abs(n.z)>.5 else v.z)
            uv.data[li].uv=(a/.5+offset[0],b/.5+offset[1])


def surface_variation(m, scale, distance, rough_min, rough_max, stretch=(1,1,1)):
    nt=m.node_tree;bs=nt.nodes.get('Principled BSDF')
    coord=nt.nodes.new('ShaderNodeTexCoord');vec=nt.nodes.new('ShaderNodeVectorMath');vec.operation='MULTIPLY'
    nt.links.new(coord.outputs['Object'],vec.inputs[0]);vec.inputs[1].default_value=stretch
    f=noise(nt,scale,2,vec.outputs[0]);nt.links.new(ramp(nt,f,rough_min,rough_max),bs.inputs['Roughness'])
    original=bs.inputs['Normal'].links[0].from_socket if bs.inputs['Normal'].is_linked else None
    bump(nt,f,bs,distance,.23,original)


def polish_scene(assets):
    # Different timber cuts and UVs replace a shared oversized varnished-table map.
    face=wood_material(assets,'4K measured pale plywood face',(.99,.91,.76))
    cut=wood_material(assets,'13-ply sawn and sanded fork edge',(.96,.85,.68),ply=True)
    end=wood_material(assets,'Fine sanded timber end grain',(.89,.79,.66),end=True)
    block=wood_material(assets,'Pale hardwood domino vertical fibres',(1.08,1.01,.88))
    base=wood_material(assets,'Oiled workshop mounting foot',(.83,.69,.50))
    y=bpy.data.objects['Hand shaped laminated wooden Y frame'];y.data.materials.clear()
    for m in (face,cut,end):y.data.materials.append(m)
    wood_uv(y,edge=cut)
    y['veneer_layer_count']=13;y['physical_envelope_unchanged']=True
    for o in list(bpy.data.objects):
        if o.name.startswith('Laminated ply edge'):bpy.data.objects.remove(o,do_unlink=True)
        elif o.name in ('domino','second_domino'):
            o.data.materials.clear()
            for m in (block,block,end):o.data.materials.append(m)
            wood_uv(o,offset=(.54,.63 if o.name=='domino'else .73),end=end)
        elif o.name=='Maple mounting foot':
            o.data.materials.clear()
            for m in (base,base,end):o.data.materials.append(m)
            wood_uv(o,grain='X',end=end)
        elif o.name=='Wooden 20cm ruler':
            o.data.materials.clear();o.data.materials.append(block);wood_uv(o,grain='X',offset=(.2,.7))
        elif o.name=='Pencil sharpened cedar':
            o.data.materials.clear();o.data.materials.append(base);wood_uv(o,grain='X')
    # Satin steel retains narrow directional machining marks instead of perfect paint.
    for name in ('Satin machined steel','Dark gunmetal clamp'):
        m=bpy.data.materials[name];bs=m.node_tree.nodes.get('Principled BSDF')
        if 'Dark'in name:
            bs.inputs['Base Color'].default_value=(.031,.038,.037,1)
            bs.inputs['Metallic'].default_value=.64
        surface_variation(m,550,.000012,.30,.48,(1,12,1.4))
        bevel=m.node_tree.nodes.new('ShaderNodeBevel');bevel.inputs['Radius'].default_value=.00007;bevel.samples=3
        # Bevel contributes only subpixel normal rounding, never moves a contact.
        n=bs.inputs['Normal'].links[0].from_socket
        m.node_tree.links.new(n,bevel.inputs['Normal']);m.node_tree.links.new(bevel.outputs['Normal'],bs.inputs['Normal'])
    # Leather grain stays in its metric UVs, with unpolished cut edges and waxed thread.
    leather=bpy.data.materials['2K worn oxblood leather'];lbs=leather.node_tree.nodes.get('Principled BSDF')
    lbs.inputs['Specular IOR Level'].default_value=.27
    for n in leather.node_tree.nodes:
        if n.type=='NORMAL_MAP':n.inputs['Strength'].default_value=.24
    lbs.inputs['Sheen Weight'].default_value=.08
    # Latex has broad, subdued highlights; speckle never changes band thickness.
    rubber=bpy.data.materials['Matte natural amber latex'];bs=rubber.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value=(.64,.39,.16,1)
    bs.inputs['Roughness'].default_value=.49;bs.inputs['Specular IOR Level'].default_value=.32
    # Polypropylene-like fine mould texture at micrometre scale.
    for name in ('Moulded petrol-blue solid polymer','Bone plastic'):
        m=bpy.data.materials[name];surface_variation(m,11000,.000006,.30,.42)
        bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['IOR'].default_value=1.48
        bs.inputs['Coat Weight'].default_value=.025
    # Real paper is a thin sheet, not a pristine luminous plane. Fibre relief is 6 um.
    paper=bpy.data.materials['Warm uncoated drawing paper'];bs=paper.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value=(.72,.705,.64,1)
    surface_variation(paper,16000,.000006,.83,.95)
    bs.inputs['Sheen Weight'].default_value=.12
    # Make the vertical grid visible and the pencil diagram legible.
    grid=material('Faded blue-grey printed graph grid',(.37,.47,.49),.95)
    for o in bpy.data.objects:
        if o.name.startswith('Faint graph paper'):
            o.data.materials.clear();o.data.materials.append(grid)
    graphite=bpy.data.materials['Graphite pencil'];gbs=graphite.node_tree.nodes.get('Principled BSDF')
    gbs.inputs['Base Color'].default_value=(.055,.06,.058,1);gbs.inputs['Roughness'].default_value=.77
    # Small pencil rubbings and uneven strokes sit on the original sheet outside the lane.
    from mathutils import Vector
    for k in range(7):
        d=bpy.data.curves.new('Graphite construction stroke','CURVE');d.dimensions='3D';d.bevel_depth=.000045;d.bevel_resolution=2
        s=d.splines.new('POLY');s.points.add(2)
        x=.171+.002*k;y=.138+.0012*math.sin(k)
        for p,v in zip(s.points,[(x,y,.00078),(x+.010,y+.001,.00078),(x+.013,y+.0006,.00078)]):p.co=(*v,1)
        o=bpy.data.objects.new('Pencil construction hatching',d);bpy.context.collection.objects.link(o);d.materials.append(graphite)
    sand=bpy.data.materials['Used fine sandpaper'];surface_variation(sand,14000,.00006,.89,1.)
    # Old varnished red timber is retained only in the background, with a quieter
    # finish so the actual tabletop experiment remains the visual focus.
    backdrop=bpy.data.materials['4K open-grain oiled maple'];nt=backdrop.node_tree
    bs=nt.nodes.get('Principled BSDF');old=bs.inputs['Base Color'].links[0].from_socket
    hs=nt.nodes.new('ShaderNodeHueSaturation');hs.inputs['Saturation'].default_value=.50
    hs.inputs['Value'].default_value=.78;nt.links.new(old,hs.inputs['Color']);nt.links.new(hs.outputs['Color'],bs.inputs['Base Color'])
    # Less frontal fill restores shape and contact shadows; a rectangular window reads
    # naturally in the ball and fastener highlights. Shared across every variant.
    key=bpy.data.lights['Large side window'];key.shape='RECTANGLE';key.size=.62;key.size_y=.90;key.energy=31
    key.color=(1.,.94,.85)
    bpy.data.lights['Cool soft room bounce'].energy=4.5
    bpy.data.lights['Warm shelf rim'].energy=6
    bpy.context.scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.16
    bpy.context.scene.view_settings.look='AgX - Medium High Contrast'
    bpy.context.scene.view_settings.exposure=.15
    bpy.context.scene['realism_revision']='measured wood UV, sawn laminate, material microstructure, restrained daylight'
    bpy.context.scene['visual_changes_affect_physics']=False
    bpy.context.scene['surface_detail_displacement_m']=0.
