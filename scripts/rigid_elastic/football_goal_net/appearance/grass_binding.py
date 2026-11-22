"""Remote Blender: sparse samples of the exact simulated turf state."""
import numpy as np
import hashlib,json
from pathlib import Path
def bind(bpy,turf,cache,eye,target):
    carriers=[o for o in bpy.context.scene.objects if o.type=='MESH' and not o.hide_render and o.data.attributes.get('tuft_variant')]
    assert carriers
    xy=cache['turf_control_xy'];scales=cache['turf_control_scale'];times=cache['times'];hg=.024
    # A sample outside the shot footprint keeps the field defined before
    # any ground contact; all actual deformed samples retain their SI values.
    if len(xy)==0:xy=np.array([[1000.,1000.]],np.float32);scales=np.ones((len(times),1),np.float32)
    points=np.column_stack((xy,np.full(len(xy),hg))).astype(np.float32)
    mesh=bpy.data.meshes.new('sparse physical grass state');mesh.from_pydata(points.tolist(),[],[])
    control=bpy.data.objects.new('nonrender physical grass samples',mesh);bpy.context.scene.collection.objects.link(control);control['pcve_role']='nonrender_physics_data_sampler'
    control.shape_key_add(name='Basis')
    for i,t in enumerate(times):
        frame=1+float(t)*120;coords=points.copy();coords[:,2]=hg*scales[i];key=control.shape_key_add(name=f'Turf_{i:04d}');key.data.foreach_set('co',coords.ravel())
        for f,value in ((frame-1,0.),(frame,1.),(frame+1,0.)):key.value=value;key.keyframe_insert('value',frame=f)
    for fcurve in control.data.shape_keys.animation_data.action.fcurves:
        for key in fcurve.keyframe_points:key.interpolation='LINEAR'
    original_group=next(m.node_group for m in carriers[0].modifiers if m.type=='NODES')
    static_group=original_group.copy();static_group.name='static grass outside shared contact corridor'
    static_mapping=next(n for n in static_group.nodes if n.bl_idname=='ShaderNodeMapRange')
    for link in tuple(static_mapping.outputs['Result'].links):
        destination=link.to_socket;static_group.links.remove(link);value=destination.default_value;destination.default_value=tuple(1. for _ in value) if hasattr(value,'__len__') else 1.
    for n in tuple(static_group.nodes):
        if n.bl_idname=='GeometryNodeObjectInfo':static_group.nodes.remove(n)
    group=original_group.copy();group.name='force-state height sampling inside shared corridor'
    nodes,links=group.nodes,group.links;mapping=next(n for n in nodes if n.bl_idname=='ShaderNodeMapRange');destinations=[l.to_socket for l in mapping.outputs['Result'].links]
    for link in list(mapping.outputs['Result'].links):links.remove(link)
    for n in list(nodes):
        if n.bl_idname=='GeometryNodeObjectInfo':nodes.remove(n)
    def node(kind,**attrs):
        n=nodes.new(kind)
        for key,value in attrs.items():setattr(n,key,value)
        return n
    def math(op,a,b):
        n=node('ShaderNodeMath',operation=op)
        for sock,value in zip(n.inputs,(a,b)):
            if isinstance(value,(int,float)):sock.default_value=value
            else:links.new(value,sock)
        return n.outputs[0]
    info=node('GeometryNodeObjectInfo',transform_space='RELATIVE');info.inputs['Object'].default_value=control
    pos=node('GeometryNodeInputPosition');xyz=node('ShaderNodeSeparateXYZ');links.new(pos.outputs[0],xyz.inputs[0])
    store=node('GeometryNodeStoreNamedAttribute',data_type='FLOAT',domain='POINT');store.inputs['Name'].default_value='physical_height_m';links.new(info.outputs['Geometry'],store.inputs['Geometry']);links.new(xyz.outputs['Z'],store.inputs['Value'])
    combine=node('ShaderNodeCombineXYZ');links.new(xyz.outputs['X'],combine.inputs['X']);links.new(xyz.outputs['Y'],combine.inputs['Y'])
    flat=node('GeometryNodeSetPosition');links.new(store.outputs['Geometry'],flat.inputs['Geometry']);links.new(combine.outputs[0],flat.inputs['Position'])
    nearest=node('GeometryNodeSampleNearest',domain='POINT');links.new(flat.outputs[0],nearest.inputs['Geometry']);links.new(combine.outputs[0],nearest.inputs['Sample Position'])
    index=node('GeometryNodeSampleIndex',data_type='FLOAT_VECTOR',domain='POINT');links.new(flat.outputs[0],index.inputs['Geometry']);links.new(pos.outputs[0],index.inputs['Value']);links.new(nearest.outputs[0],index.inputs['Index'])
    distance=node('ShaderNodeVectorMath',operation='DISTANCE');links.new(combine.outputs[0],distance.inputs[0]);links.new(index.outputs['Value'],distance.inputs[1])
    attr=node('GeometryNodeInputNamedAttribute',data_type='FLOAT');attr.inputs['Name'].default_value='physical_height_m'
    value=node('GeometryNodeSampleIndex',data_type='FLOAT',domain='POINT');links.new(flat.outputs[0],value.inputs['Geometry']);links.new(attr.outputs['Attribute'],value.inputs['Value']);links.new(nearest.outputs[0],value.inputs['Index'])
    scale=math('DIVIDE',value.outputs['Value'],hg);inside=math('LESS_THAN',distance.outputs['Value'],.009);result=math('ADD',1.,math('MULTIPLY',inside,math('SUBTRACT',scale,1.)))
    for socket in destinations:links.new(result,socket)
    forward=(target-eye)/np.linalg.norm(target-eye);right=np.cross(forward,np.array([0.,0.,1.]));right/=np.linalg.norm(right);records=[]
    x0,x1,y0,y1=json.loads(Path(__file__).with_name('visual_layout.json').read_text())['common_soil_bounds_xy_m']
    def make_mesh(name,arrays,mask):
        mesh=bpy.data.meshes.new(name);mesh.vertices.add(int(mask.sum()));mesh.vertices.foreach_set('co',arrays['position'][mask].ravel())
        for attr,kind,field in [('tuft_rotation','FLOAT_VECTOR','vector'),('tuft_scale','FLOAT_VECTOR','vector'),('tuft_variant','INT','value')]:mesh.attributes.new(name=attr,type=kind,domain='POINT').data.foreach_set(field,arrays[attr][mask].ravel())
        mesh.update();return mesh
    for obj in carriers:
        arrays=turf._source_arrays(obj.data);relative=arrays['position'].astype(np.float64)-eye;depth=relative@forward;side=relative@right;distance=np.linalg.norm(relative,axis=1)
        probability=np.ones(len(distance));xyroot=arrays['position'][:,:2].astype(np.float64);phase=np.sin(xyroot[:,0]*127.1+xyroot[:,1]*311.7)*43758.5453
        keep=(depth>-.5)&(np.abs(side)<np.maximum(depth,0.)*.75+1.)&(phase-np.floor(phase)<probability)
        pos_array=arrays['position'];inside=(pos_array[:,0]>=x0)&(pos_array[:,0]<=x1)&(pos_array[:,1]>=y0)&(pos_array[:,1]<=y1);live=keep&inside;static=keep&~inside;assert int(live.sum()+static.sum())==int(keep.sum())
        obj.data=make_mesh('interactive roots '+obj.name,arrays,live);next(m for m in obj.modifiers if m.type=='NODES').node_group=group
        static_obj=bpy.data.objects.new(obj.name+' | static outer field',make_mesh('unchanged outer roots '+obj.name,arrays,static));bpy.context.scene.collection.objects.link(static_obj);static_obj.matrix_world=obj.matrix_world.copy();static_obj['static_unaffected_turf']=True;static_obj.modifiers.new('Unaffected grass, same prototypes and unit height','NODES').node_group=static_group
        records.append({'object':obj.name,'roots':int(keep.sum()),'animated_corridor_roots':int(live.sum()),'static_outer_roots':int(static.sum()),'all_original_positions_and_attributes_retained_without_duplication':True})
    return {'source':'same viscoelastic foundation state as ball forces','layout_sha256':hashlib.sha256(Path(__file__).with_name('visual_layout.json').read_bytes()).hexdigest(),'samples':len(points),'old_distance_only_compression_removed':True,'grass_LOD':'fixed shared broad frustum; full tuft density; only the common contact corridor depends on animated samples','common_interactive_bounds_xy_m':[x0,x1,y0,y1],'static_background_has_no_animated_object_dependencies':True,'carriers':records,'resolved_botanical_material':False}
