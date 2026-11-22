"""Shared static appearance refinement for source and every counterfactual.
Metric tangent UVs, restrained wear, moderate molded edges and four glass panes.
Lighting remains controlled by the appearance configuration.
"""
import bpy
PLASTICS=['Orange polypropylene track','Blue molded risers and connectors','Dark grey hinge pins','Grey launcher housing','Yellow launcher button']

def refine_scene(scene):
    s=scene
    UV_NAME='PCVE metric surface UV'
    mapping={}
    for mat in bpy.data.materials:
        if not mat.use_nodes:continue
        tc=next((n for n in mat.node_tree.nodes if n.type=='TEX_COORD' and n.object and n.object.name=='World-space texture anchor'),None)
        if tc is None:continue
        scale=next(n for n in mat.node_tree.nodes if n.type=='VECT_MATH' and n.operation=='SCALE')
        axes=(0,1)
        upstream=scale.inputs[0].links[0].from_node
        if upstream.type=='COMBXYZ':
            axes=tuple('XYZ'.index(upstream.inputs[i].links[0].from_socket.name) for i in (0,1))
        mapping[mat.name]={'axes':axes,'scale':float(scale.inputs['Scale'].default_value),'anchor':tc.object,
                           'images':[n for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.inputs['Vector'].is_linked and n.inputs['Vector'].links[0].from_node==scale]}
    targets=[o for o in s.objects if o.type=='MESH' and any(m and m.name in mapping for m in o.data.materials)]

    for obj in targets:
        layer=obj.data.uv_layers.new(name=UV_NAME)
        for poly in obj.data.polygons:
            mat=obj.data.materials[poly.material_index]
            if not mat or mat.name not in mapping:continue
            spec=mapping[mat.name];axes=spec['axes'];anchor_inv=spec['anchor'].matrix_world.inverted()
            normal=(obj.matrix_world.to_3x3().inverted().transposed()@poly.normal).normalized()
            omitted=next(i for i in range(3) if i not in axes)
            # Preserve the current projection on main faces; keep secondary faces nondegenerate.
            if abs(normal[omitted])<0.05:
                omitted=max(range(3),key=lambda i:abs(normal[i]))
                axes=tuple(i for i in range(3) if i!=omitted)
            for li in poly.loop_indices:
                p=anchor_inv@(obj.matrix_world@obj.data.vertices[obj.data.loops[li].vertex_index].co)
                layer.data[li].uv=(p[axes[0]]*spec['scale'],p[axes[1]]*spec['scale'])
        obj.data.uv_layers.active=layer
    for name,spec in mapping.items():
        mat=bpy.data.materials[name];nodes,links=mat.node_tree.nodes,mat.node_tree.links
        uv=nodes.new('ShaderNodeUVMap');uv.name='PCVE metric surface UV';uv.uv_map=UV_NAME
        for im in spec['images']:links.new(uv.outputs['UV'],im.inputs['Vector'])
        for node in nodes:
            if node.type=='NORMAL_MAP' and node.space=='TANGENT':node.uv_map=UV_NAME

    # Opaque molded toy plastic; retain only faint grime and local scuffs.
    for name in PLASTICS:
        nodes=bpy.data.materials[name].node_tree.nodes
        nodes.get('Principled BSDF').inputs['Subsurface Weight'].default_value=.02
        nodes.get('Map Range').inputs['To Max'].default_value=.18
        nodes.get('Map Range.003').inputs['To Max'].default_value=.12
        nodes.get('Math').inputs[1].default_value=.18
        nodes.get('Math.003').inputs[1].default_value=.12
    # Change cosmetic edge radii only; the track deck and collision geometry stay intact.
    for obj in s.objects:
        limit=None
        if obj.type=='MESH' and any(m and m.name=='Blue molded risers and connectors' for m in obj.data.materials):limit=.0016
        if obj.name.startswith('Riser base plate'):limit=.0025
        if obj.name.startswith(('Panel molding','Back skirting','Left skirting')):limit=.0015
        if obj.name=='Dado rail':limit=.002
        if obj.name.startswith(('Window upright','Window rail','Side window')):limit=.0012
        if obj.name=='Window sill':limit=.0018
        if limit is not None:
            for mod in obj.modifiers:
                if mod.type=='BEVEL':mod.width=min(mod.width,limit)

    # Four clear 4 mm panes, seated inside the existing wooden frames.
    glass=bpy.data.materials.new('Clear 4 mm window glass');glass.use_nodes=True
    nodes,links=glass.node_tree.nodes,glass.node_tree.links
    for node in list(nodes):nodes.remove(node)
    shader=nodes.new('ShaderNodeBsdfGlass');shader.inputs['Color'].default_value=(1.,1.,1.,1.);shader.inputs['IOR'].default_value=1.46;shader.inputs['Roughness'].default_value=.015
    output=nodes.new('ShaderNodeOutputMaterial');links.new(shader.outputs['BSDF'],output.inputs['Surface'])
    for ix,(xa,xb) in enumerate([(-.028,.553),(.597,1.178)]):
        for iz,(za,zb) in enumerate([(.967,1.883),(1.917,2.333)]):
            verts=[(x,y,z) for x,y,z in [(xa,1.701,za),(xb,1.701,za),(xb,1.705,za),(xa,1.705,za),(xa,1.701,zb),(xb,1.701,zb),(xb,1.705,zb),(xa,1.705,zb)]]
            mesh=bpy.data.meshes.new('Window glass pane');mesh.from_pydata(verts,[],[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]);mesh.update()
            obj=bpy.data.objects.new(f'Physical window glass {ix}-{iz}',mesh);s.collection.objects.link(obj);obj.data.materials.append(glass)

    return {'metric_uv_objects':len(targets),'window_glass_panes':4,'surface_preset':'balanced_molded_plastic'}
