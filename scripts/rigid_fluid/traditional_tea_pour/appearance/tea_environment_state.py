"""Read-only invariants and actual scene ledger for the environment revision."""
import hashlib
import json

import bpy
import numpy as np

HEROES=('TraditionalTeaCup_Visual','TraditionalTeapot_Visual','TraditionalTeapotLid_Visual')
SUPPORTS=('MapleTable','TeaDecor_WovenCoaster')


def file_hash(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while data:=f.read(8*1024*1024): h.update(data)
    return h.hexdigest()


def value(v):
    if isinstance(v,(int,float,str,bool)) or v is None: return v
    try: return list(v)
    except TypeError: return str(v)


def mesh_hash(mesh,uv=True):
    h=hashlib.sha256()
    for collection,prop,dtype,count in [(mesh.vertices,'co',np.float32,3),
                                       (mesh.loops,'vertex_index',np.int32,1),
                                       (mesh.polygons,'loop_total',np.int32,1),
                                       (mesh.polygons,'material_index',np.int32,1),
                                       (mesh.polygons,'use_smooth',np.bool_,1)]:
        data=np.empty(len(collection)*count,dtype=dtype)
        collection.foreach_get(prop,data)
        h.update(data.tobytes())
    if uv:
        for layer in mesh.uv_layers:
            a=np.empty(len(layer.data)*2,dtype=np.float32)
            layer.data.foreach_get('uv',a)
            h.update(layer.name.encode()); h.update(a.tobytes())
    return h.hexdigest()


def material_state(mat):
    data={'name':mat.name,'use_nodes':mat.use_nodes,'nodes':[],'links':[]}
    if mat.use_nodes:
        for n in mat.node_tree.nodes:
            row={'name':n.name,'type':n.bl_idname,
                 'inputs':[(s.identifier,value(s.default_value)) for s in n.inputs if hasattr(s,'default_value')]}
            for attr in ('operation','blend_type','distribution','interpolation','extension','projection','uv_map'):
                if hasattr(n,attr): row[attr]=getattr(n,attr)
            if hasattr(n,'image') and n.image:
                im=n.image
                row['image']={'name':im.name,'colorspace':im.colorspace_settings.name,
                              'packed_sha256':hashlib.sha256(im.packed_file.data).hexdigest() if im.packed_file else None,
                              'size':list(im.size)}
            if hasattr(n,'color_ramp'):
                row['ramp']=[(e.position,list(e.color)) for e in n.color_ramp.elements]
            data['nodes'].append(row)
        data['links']=sorted([(x.from_node.name,x.from_socket.identifier,x.to_node.name,x.to_socket.identifier) for x in mat.node_tree.links])
    return data


def camera_state():
    c=bpy.context.scene.camera
    return {'name':c.name,'matrix_world':[list(r) for r in c.matrix_world],
            'lens':c.data.lens,'sensor_width':c.data.sensor_width,'sensor_height':c.data.sensor_height,
            'sensor_fit':c.data.sensor_fit,'shift_xy':[c.data.shift_x,c.data.shift_y],
            'clip':[c.data.clip_start,c.data.clip_end],
            'dof':[c.data.dof.use_dof,c.data.dof.focus_distance,c.data.dof.aperture_fstop,
                   c.data.dof.aperture_blades,c.data.dof.aperture_ratio,c.data.dof.aperture_rotation]}


def transforms():
    return {name:[list(r) for r in bpy.data.objects[name].matrix_world]
            for name in HEROES+SUPPORTS+('GenesisTeaSurface',)}


def protected_state():
    scene=bpy.context.scene
    return {'camera':camera_state(),'transforms':transforms(),
            'hero_meshes':{n:mesh_hash(bpy.data.objects[n].data) for n in HEROES},
            'support_geometry':{n:mesh_hash(bpy.data.objects[n].data,False) for n in SUPPORTS},
            'hero_and_tea_materials':{n:[material_state(m) for m in bpy.data.objects[n].data.materials if m]
                                      for n in HEROES+('GenesisTeaSurface',)},
            'visibility':{n:[bpy.data.objects[n].hide_render,bpy.data.objects[n].hide_viewport] for n in HEROES+SUPPORTS+('GenesisTeaSurface',)},
            'render':[scene.render.engine,scene.render.resolution_x,scene.render.resolution_y,
                      scene.render.resolution_percentage,scene.render.fps,scene.render.fps_base,
                      scene.cycles.samples,scene.cycles.use_denoising,scene.render.use_motion_blur],
            'color':[scene.view_settings.view_transform,scene.view_settings.look,scene.view_settings.exposure,scene.view_settings.gamma]}


def environment_state():
    result={'objects':{},'materials':{},'lights':{},'world':[]}
    for o in bpy.context.scene.objects:
        if o.type=='LIGHT':
            result['lights'][o.name]={'matrix':[list(r) for r in o.matrix_world],
                'energy':o.data.energy,'color':list(o.data.color),'size':o.data.size,
                'size_y':o.data.size_y,'shape':o.data.shape}
        if (o.name.startswith(('Env15_','TeaDecor_','TeaRoom_')) or o.name in ('MapleTable','WarmBackdrop')) and o.type in ('MESH','CURVE'):
            result['objects'][o.name]={'matrix':[list(r) for r in o.matrix_world],
                'dimensions_m':list(o.dimensions),'hide_render':o.hide_render,
                'mesh_sha256':mesh_hash(o.data) if o.type=='MESH' else None,
                'materials':[m.name for m in o.data.materials if m]}
            for m in o.data.materials:
                if m and m.name not in result['materials']:
                    result['materials'][m.name]=material_state(m)
    for n in bpy.context.scene.world.node_tree.nodes:
        result['world'].append({'type':n.type,'inputs':{s.name:value(s.default_value) for s in n.inputs if hasattr(s,'default_value')}})
    return result


def digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
