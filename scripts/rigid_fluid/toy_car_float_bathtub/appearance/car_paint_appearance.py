"""Approved silver paint and tinted glazing of the toy car, frozen from the static trial."""
import re

def serial(value):
    return list(value) if hasattr(value,'__len__') else value

def bsdf(mat):
    return next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')

def apply_car(pose):
    preset='silver_paint'
    raw={m.name:m for o in pose.children_recursive if o.type=='MESH' for m in o.data.materials if m}
    mats={re.sub(r'\.\d+$','',name):mat for name,mat in raw.items()}
    rim=next(o for o in pose.children_recursive if '.013_RIM_0' in o.name)
    mats['material.001']=rim.data.materials[0]
    changes=[]
    def set_inputs(name,values):
        mat=mats[name]
        node=bsdf(mat)
        for key,value in values.items():
            socket=node.inputs[key]
            assert not socket.is_linked,(name,key,'Unexpected texture link')
            old=serial(socket.default_value)
            socket.default_value=value
            new=serial(socket.default_value)
            if old!=new:
                changes.append({'type':'material','name':name,'field':key,'before':old,'after':new})

    # A slightly cool silver conductor, with a thin clear finish. The imported
    # pure-white conductor reflected almost all incoming light at every angle.
    paint=preset=='silver_paint'
    body_color=(.34,.38,.44,1) if paint else (.56,.60,.66,1)
    body_roughness=[('CHROME',.32),('CAR_CHASSIS',.34)] if paint else [('CHROME',.23),('CAR_CHASSIS',.27)]
    for name,roughness in body_roughness:
        set_inputs(name,{'Base Color':body_color,'Metallic':.82 if paint else 1.0,
            'Roughness':roughness,'Specular IOR Level':.5,
            'Coat Weight':.28 if paint else .16,'Coat Roughness':.13 if paint else .15})
    # Actual glazing reflection/transmission replaces the diffuse alpha pane.
    set_inputs('windows',{'Base Color':(.83,.90,.95,1),'Metallic':0.0,
        'Roughness':.075,'IOR':1.46,'Transmission Weight':.98,'Alpha':1.0,
        'Coat Weight':0.0,'Specular IOR Level':.5})
    set_inputs('LCOVERS',{'Base Color':(.94,.97,1.0,1),'Metallic':0.0,
        'Roughness':.085,'IOR':1.46,'Transmission Weight':.98,'Alpha':1.0,
        'Coat Weight':0.0,'Specular IOR Level':.5})
    if True:
        # These imported panes are surface sheets. A Fresnel thin-sheet model
        # avoids treating them as a thick solid lens and keeps shadow paths
        # straight, appropriate to miniature unthickened glazing.
        for name,roughness,tint in [('windows',.10,(.30,.34,.39,1)),
                                    ('LCOVERS',.085,(.97,.98,1.0,1))]:
            mat=mats[name]
            nodes,links=mat.node_tree.nodes,mat.node_tree.links
            output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL')
            transparent=nodes.new('ShaderNodeBsdfTransparent')
            transparent.label='Straight transmission through a thin pane'
            transparent.inputs['Color'].default_value=tint
            reflection=nodes.new('ShaderNodeBsdfPrincipled')
            reflection.label='White reflection lobe, weighted by dielectric Fresnel'
            reflection.inputs['Base Color'].default_value=(1,1,1,1)
            reflection.inputs['Metallic'].default_value=1.0
            reflection.inputs['Roughness'].default_value=roughness
            fresnel=nodes.new('ShaderNodeFresnel')
            fresnel.inputs['IOR'].default_value=1.46
            mix=nodes.new('ShaderNodeMixShader')
            links.new(fresnel.outputs['Fac'],mix.inputs[0])
            links.new(transparent.outputs[0],mix.inputs[1])
            links.new(reflection.outputs['BSDF'],mix.inputs[2])
            for link in list(output.inputs['Surface'].links):
                links.remove(link)
            links.new(mix.outputs[0],output.inputs['Surface'])
            mat['pcve_surface_model']='Fresnel thin-sheet glazing'
            changes.append({'type':'material_graph','name':name,'field':'surface_model',
                'before':'Solid Principled transmission on an unthickened imported pane',
                'after':{'model':'Fresnel thin-sheet glazing','ior':1.46,
                         'roughness':roughness,'transmission_tint':list(tint)}})
    set_inputs('BLACKGLASS',{'Base Color':(.006,.008,.012,1),
        'Roughness':.24,'Coat Weight':.22,'Coat Roughness':.13})
    set_inputs('mirror',{'Base Color':(.72,.75,.80,1),'Metallic':1.0,'Roughness':.08})
    set_inputs('carbon',{'Metallic':0.0,'Roughness':.34,'Specular IOR Level':.45,
        'Coat Weight':.12,'Coat Roughness':.15})
    set_inputs('AC_TREAD',{'Base Color':(.012,.013,.015,1),'Roughness':.65,
        'Specular IOR Level':.30})
    set_inputs('AC_TIRESIDE',{'Roughness':.66,'Specular IOR Level':.30})
    set_inputs('visiongt_interior',{'Metallic':0.0,'Roughness':.52})
    set_inputs('sw_paddles',{'Metallic':.55,'Roughness':.46,'Specular IOR Level':.35})
    for name in ['RIM_CAP','material.001']:
        set_inputs(name,{'Roughness':.26})
    # A display model has no powered dashboard or head/tail lamps.
    for name in ['HGLOB','GLOW','dash_red','visiongt_dash']:
        set_inputs(name,{'Emission Strength':0.0})

    return {'preset':'silver_paint','thin_glazing':True,'changes':changes,
            'implementation':'frozen from the selected 23 cm static preview'}
