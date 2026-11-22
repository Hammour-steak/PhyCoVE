"""Two supported, lightly curled loose playing cards; appearance-only."""
import math
import bpy
from mathutils import Vector
from card_table_environment import rounded_outline

REVISION='loose_supported_stock'
TARGETS=['Loosely dealt 8 of spades','Loosely dealt King of hearts']
THICKNESS=.00028

def smoothstep(a,b,x):
    t=max(0.,min(1.,(x-a)/(b-a)))
    return t*t*(3-2*t)

def height_function(obj,other,lift):
    # Only free corners lift. The full overlap and a 3 mm guard band stay flat,
    # so the pre-existing support contact is retained exactly.
    into_other=other.matrix_world.inverted()@obj.matrix_world
    def h(x,y):
        q=into_other@Vector((x,y,0))
        outside=max(abs(q.x)-.0315,abs(q.y)-.044)
        free=smoothstep(.003,.011,outside)
        corner=smoothstep(.45,.98,abs(x)/.0315)*smoothstep(.42,.98,abs(y)/.044)
        # Unequal corner response avoids a perfectly symmetric bowl.
        bias=.68+.19*(x/.0315)+.13*(y/.044)
        return lift*free*corner*max(.3,bias)
    return h

def rebuild_card(obj,other,lift):
    coarse=rounded_outline(.063,.088,.0025,segments=12)
    outline=[]
    for a,b in zip(coarse,coarse[1:]+coarse[:1]):
        steps=max(1,math.ceil(math.hypot(b[0]-a[0],b[1]-a[1])/.00175))
        outline.extend([(a[0]+(b[0]-a[0])*i/steps,a[1]+(b[1]-a[1])*i/steps) for i in range(steps)])
    count=len(outline);rings=26
    height=height_function(obj,other,lift)
    xy=[(0.,0.)]+[(x*k/rings,y*k/rings) for k in range(1,rings+1) for x,y in outline]
    per=len(xy)
    vertices=[(x,y,height(x,y)+layer*THICKNESS) for layer in [0,1] for x,y in xy]
    top=[]
    for i in range(count):
        top.append((per,per+1+i,per+1+(i+1)%count))
    for k in range(1,rings):
        inner=1+(k-1)*count;outer=1+k*count
        for i in range(count):
            j=(i+1)%count
            top.append((per+inner+i,per+outer+i,per+outer+j,per+inner+j))
    bottom=[tuple(v-per for v in reversed(f)) for f in top]
    outer=1+(rings-1)*count
    side=[(outer+i,outer+(i+1)%count,per+outer+(i+1)%count,per+outer+i) for i in range(count)]
    mesh=bpy.data.meshes.new('Supported curled 0.28 mm stock | '+obj.name)
    mesh.from_pydata(vertices,[],top+bottom+side);mesh.update()
    previous=list(obj.data.materials);mesh.materials.append(previous[0].copy());mesh.materials.append(previous[1].copy())
    mesh.materials[0].name='Loose card print | '+obj.name
    mesh.materials[1].name='Loose card cut edge | '+obj.name
    uv=mesh.uv_layers.new(name='Entire printed card face')
    normals=[]
    eps=.000002
    for face in mesh.polygons:
        face.material_index=0 if face.index<len(top) else 1
        face.use_smooth=face.index<2*len(top)
        for li in face.loop_indices:
            v=mesh.vertices[mesh.loops[li].vertex_index].co
            uv.data[li].uv=(v.x/.063+.5,v.y/.088+.5)
            if face.index<2*len(top):
                dx=(height(v.x+eps,v.y)-height(v.x-eps,v.y))/(2*eps)
                dy=(height(v.x,v.y+eps)-height(v.x,v.y-eps))/(2*eps)
                n=Vector((-dx,-dy,1)).normalized()
                if face.index>=len(top):n=-n
                normals.append(n)
            else:normals.append(face.normal)
    mesh.normals_split_custom_set(normals)
    obj.data=mesh;obj.modifiers.clear()
    obj['loose_card_revision']=REVISION
    obj['card_face_vertex_count_per_layer']=per
    obj['actual_dimensions_m']=[.063,.088,THICKNESS]
    obj['maximum_free_corner_lift_m']=max(height(x,y) for x,y in xy)
    obj['selected_lift_limit_m']=lift
    obj['paper_shape_note']='Static lightly bent stiff stock; overlap remains flat. No live paper dynamics.'
    return {'object':obj.name,'vertices':len(vertices),'polygons':len(mesh.polygons),'thickness_m':THICKNESS,
            'maximum_free_corner_lift_m':obj['maximum_free_corner_lift_m'],'xy_and_yaw_unchanged':True,
            'overlap_flat_guard_band_m':.003,'normals':'Analytic smooth face normals, separate cut-wall normals'}

def finish(obj,settings):
    face=obj.data.materials[0]
    nodes=face.node_tree.nodes
    bs=next(n for n in nodes if n.bl_idname=='ShaderNodeBsdfPrincipled')
    bs.inputs['Coat Weight'].default_value=settings['coat_weight']
    bs.inputs['Coat Roughness'].default_value=.39
    bs.inputs['Specular IOR Level'].default_value=.33
    nodes['Slightly warm unbleached stock'].inputs[2].default_value=tuple(settings['stock_tint_linear'])
    rough=bs.inputs['Roughness'].links[0].from_node
    rough.inputs['To Min'].default_value=settings['roughness_range'][0]
    rough.inputs['To Max'].default_value=settings['roughness_range'][1]
    # Retain original artwork and restrained metre-scale sealed-stock emboss.
    face['loose_card_revision']=REVISION
    edge=obj.data.materials[1]
    en=edge.node_tree.nodes
    en['Separate warm cut paper sheets'].inputs[1].default_value=(.62,.598,.543,1)
    edge['loose_card_revision']=REVISION

    clean=settings.get('cut_edge_finish')
    if clean:
        if clean['revision']!='unprinted_stock':raise ValueError(clean['revision'])
        # A loose sheet exposes pale unprinted stock, not a drawn black outline.
        # Keep the existing 0.28 mm mesh and its real contact shadows.
        en.clear();eb=en.new('ShaderNodeBsdfPrincipled');out=en.new('ShaderNodeOutputMaterial')
        eb.inputs['Base Color'].default_value=tuple(clean['color_linear'])
        eb.inputs['Roughness'].default_value=clean['roughness']
        eb.inputs['IOR'].default_value=1.47
        eb.inputs['Specular IOR Level'].default_value=.22
        edge.node_tree.links.new(eb.outputs['BSDF'],out.inputs['Surface'])
        edge['cut_edge_finish_revision']=clean['revision']
        edge['surface_note']='Pale unprinted paper cut edge; no artificial dark adhesive/core band.'
        wear=[n for n in nodes if n.bl_idname=='ShaderNodeMapRange' and abs(n.inputs['From Max'].default_value-.0006)<1e-8 and abs(n.inputs['To Min'].default_value-.15)<1e-7]
        assert len(wear)==1
        wear[0].inputs['To Min'].default_value=clean['border_wear_strength']
        face['cut_edge_finish_revision']=clean['revision']

def enhance_environment(cfg,ledger):
    settings=cfg['appearance']['card_table'].get('loose_cards')
    if not settings:return ledger
    if settings['revision']!=REVISION:raise ValueError(settings['revision'])
    bpy.context.view_layer.update()
    cards=[bpy.data.objects[name] for name in TARGETS]
    rows=[]
    for i,obj in enumerate(cards):
        rows.append(rebuild_card(obj,cards[1-i],settings['corner_lift_limits_m'][i]))
        finish(obj,settings)
    bpy.context.view_layer.update()
    return {**ledger,'loose_card_revision':REVISION,'loose_card_geometry':rows,
            'loose_card_finish':'Satin printed stock with original artwork, restrained white albedo, separate cut edges.',
            'loose_card_scope':'Only two loose cards; 50-card deck, support gaps, XY, yaw and all domino data retained.',
            'loose_cards_are_static':True,'paper_finish_geometry_preserved':False}
