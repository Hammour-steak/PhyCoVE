"""Frozen replay utilities (native cache binding, signatures, camera coverage); the caller gates the host."""
from pathlib import Path
import hashlib,json
import numpy as np
import bpy
from mathutils import Vector,Matrix

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(p,o):Path(p).write_text(json.dumps(o,ensure_ascii=False,indent=2),encoding='utf-8')

def dynamic_signature():
    bpy.context.scene.frame_set(1);h=hashlib.sha256()
    for o in sorted(bpy.data.objects,key=lambda x:x.name):
        if o.name!='silicone bag native FEM' and not (o.type=='EMPTY' and 'rigid native transform' in o.name):continue
        h.update(o.name.encode());h.update(np.asarray(o.matrix_world,dtype=np.float32).tobytes())
        if o.type=='MESH':
            v=np.empty(len(o.data.vertices)*3,np.float32);o.data.vertices.foreach_get('co',v);h.update(v.tobytes())
            for key in o.data.shape_keys.key_blocks:
                key.data.foreach_get('co',v);h.update(v.tobytes())
            action=o.data.shape_keys.animation_data.action
        else:action=o.animation_data.action
        for fc in action.fcurves:
            h.update(fc.data_path.encode());h.update(str(fc.array_index).encode())
            for k in fc.keyframe_points:h.update(np.asarray(k.co,dtype=np.float32).tobytes())
    return h.hexdigest()

def static_signature():
    h=hashlib.sha256();scene=bpy.context.scene;scene.frame_set(1)
    for o in sorted(bpy.data.objects,key=lambda x:x.name):
        parent=o
        is_native=False
        while parent:
            if parent.name=='silicone bag native FEM' or 'rigid native transform' in parent.name:is_native=True;break
            parent=parent.parent
        if is_native:continue
        h.update((o.name+'|'+o.type+'|'+str(o.hide_render)).encode());h.update(np.asarray(o.matrix_world,dtype=np.float32).tobytes())
        if o.type=='MESH':
            v=np.empty(len(o.data.vertices)*3,np.float32);o.data.vertices.foreach_get('co',v);h.update(v.tobytes())
        elif o.type=='LIGHT':h.update(str((o.data.energy,o.data.size,tuple(o.data.color))).encode())
        if o.type in ('MESH','CURVE'):
            for m in o.data.materials:
                if not m or not m.use_nodes:continue
                h.update(m.name.encode())
                for node in m.node_tree.nodes:
                    h.update(node.bl_idname.encode())
                    for inp in node.inputs:
                        if not hasattr(inp,'default_value'):continue
                        value=inp.default_value
                        if isinstance(value,(float,int,str,bool)):value=str(value)
                        elif hasattr(value,'__len__'):
                            try:value=str(tuple(value))
                            except TypeError:value=str(type(value))
                        else:continue
                        h.update((inp.name+value).encode())
    return h.hexdigest()

def reset_material(m):
    m.use_nodes=True;n=m.node_tree.nodes;n.clear();p=n.new('ShaderNodeBsdfPrincipled');out=n.new('ShaderNodeOutputMaterial')
    m.node_tree.links.new(p.outputs['BSDF'],out.inputs['Surface']);return n,m.node_tree.links,p,out

def bind_native_cache(native):
    """Reuse one packed kitchen, replacing only native cached state coordinates.

    This is replay/export, with no integration, fitting, retiming or smoothing.
    The saved file is independently reloaded and checked against every state.
    """
    bag=bpy.data.objects.get('silicone bag native FEM')
    if native['bag_positions'].shape[1]:
        assert bag and len(bag.data.vertices)==native['bag_positions'].shape[1]
        faces=np.asarray([p.vertices[:] for p in bag.data.polygons])
        assert np.array_equal(faces,native['bag_faces'])
        keys=bag.data.shape_keys.key_blocks
        keys['Basis'].data.foreach_set('co',native['bag_positions'][0].astype(np.float32).ravel())
        for i in range(96):keys['Native state %03d'%i].data.foreach_set('co',native['bag_positions'][i].astype(np.float32).ravel())
        bag.data.update()
    elif bag:bpy.data.objects.remove(bag,do_unlink=True)
    template=bpy.data.objects['can rigid native transform']
    children=list(template.children)
    for j,identity in enumerate(native['rigid_body_ids']):
        name=str(identity)+' rigid native transform';root=bpy.data.objects.get(name)
        if root is None:
            root=bpy.data.objects.new(name,None);bpy.context.scene.collection.objects.link(root)
            for child in children:
                copy=child.copy();copy.data=child.data;copy.parent=root
                copy.matrix_parent_inverse=child.matrix_parent_inverse.copy();copy.matrix_basis=child.matrix_basis.copy()
                bpy.context.scene.collection.objects.link(copy)
        root.animation_data_clear();root.rotation_mode='QUATERNION'
        for i in range(96):
            loc,rotation,scale=Matrix(native['can_transforms'][i,j].tolist()).decompose()
            root.location=loc;root.rotation_quaternion=rotation;root.scale=scale
            for channel in ('location','rotation_quaternion','scale'):root.keyframe_insert(channel,frame=i+1)
        for fc in root.animation_data.action.fcurves:
            for key in fc.keyframe_points:key.interpolation='LINEAR'
    if 'can' not in [str(x) for x in native['rigid_body_ids']]:  # DELETE can: no can in the native state
        for o in [template,*template.children_recursive]:bpy.data.objects.remove(o,do_unlink=True)
    bpy.context.scene.frame_set(1);bpy.context.view_layer.update()

def evaluated_z_bounds(objects):
    bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get();values=[]
    for o in objects:
        if o.type!='MESH':continue
        ev=o.evaluated_get(deps);mesh=ev.to_mesh()
        values.extend((ev.matrix_world@v.co).z for v in mesh.vertices);ev.to_mesh_clear()
    assert values
    return min(values),max(values)

def descendants(root):
    result=[]
    for o in bpy.data.objects:
        parent=o.parent
        while parent:
            if parent==root:result.append(o);break
            parent=parent.parent
    return result

def contact_audit():
    rows=[]
    for name,target,objects in (
        ('cutting board',.910,[bpy.data.objects['rounded cutting board']]),
        ('ceramic plate',.910,[bpy.data.objects['photo6 small stoneware plate']]),
        ('lemon on plate',.913,descendants(bpy.data.objects['photo6 lemon asset root'])),
        ('apple on counter',.910,descendants(bpy.data.objects['photo6 food_apple_01 asset root'])),
        ('cotton towel lower layer',.910,[bpy.data.objects['woven cotton folded layer 0']]),
        ('knife handle on board',.930,[bpy.data.objects['photo6 knife walnut handle']])):
        low,high=evaluated_z_bounds(objects);rows.append(dict(object=name,min_evaluated_z_m=low,max_evaluated_z_m=high,declared_rest_z_m=target,gap_m=low-target))
    assert max(abs(row['gap_m']) for row in rows)<5e-6,rows
    return dict(scope='Static background contacts only; no native trajectories were changed',tolerance_m=5e-6,contacts=rows,passed=True)

def detail_camera():
    cam=bpy.context.scene.camera;cam.location=(.55,-1.65,1.48);target=Vector((.025,-.145,.80))
    cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=49
    cam.data.dof.focus_distance=(target-cam.location).length;cam.data.dof.aperture_fstop=5.6

def coverage(native,state_indices=None):
    """Project every shell vertex and conservative rigid envelope at all video states."""
    scene=bpy.context.scene;bpy.context.view_layer.update()
    proj=np.asarray(scene.camera.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(),x=scene.render.resolution_x,y=scene.render.resolution_y),dtype=float)
    view=np.asarray(scene.camera.matrix_world.inverted(),dtype=float);vp=proj@view
    bounds=np.array([[np.inf,np.inf],[-np.inf,-np.inf]])
    cube=np.array([[x,y,z] for x in (-.034,.034) for y in (-.034,.034) for z in (-.04,.04)])
    selected=np.arange(96) if state_indices is None else np.asarray(state_indices,dtype=int)
    t=native['can_transforms'][selected]
    p=(np.einsum('...ij,kj->...ki',t[:,:,:3,:3],cube)+t[:,:,:3,3][...,None,:]).reshape(-1,3)
    if native['bag_positions'].shape[1]:p=np.concatenate([p,native['bag_positions'][selected].reshape(-1,3)])
    clip=np.c_[p,np.ones(len(p))]@vp.T;ndc=clip[:,:2]/clip[:,3,None]*.5+.5
    bounds[0]=ndc.min(0);bounds[1]=ndc.max(0)
    passed=bool((bounds[0]>.015).all() and (bounds[1]<.985).all() and (clip[:,3]>0).all())
    return dict(all_video_states=len(selected),state_indices=selected.tolist(),all_shell_vertices=True,rigid_envelope='conservative 68x68x80 mm box',normalized_image_bounds=bounds.tolist(),minimum_margin=.015,passed=passed)
