"""Saved-scene support checks; runs inside Blender after the scene is assembled."""
import socket
import bpy
from mathutils import Vector

def audit():
    bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get()
    objects=[o for o in bpy.context.scene.objects if o.type in ('MESH','CURVE','FONT') and not o.name.startswith(('bag_scan','second_bag_scan','exit_curtain'))]
    boxes={}
    for ob in objects:
        evaluated=ob.evaluated_get(deps);points=[evaluated.matrix_world@Vector(v) for v in evaluated.bound_box]
        boxes[ob.name]=([min(p[k] for p in points) for k in range(3)],[max(p[k] for p in points) for k in range(3)])
    floor='Granite station floor';floor_z=boxes[floor][1][2];eps=.0026
    names=sorted(boxes);connected={floor};changed=True
    while changed:
        changed=False
        for a in names:
            if a in connected:continue
            amin,amax=boxes[a]
            for b in list(connected):
                bmin,bmax=boxes[b]
                if all(amin[k]<=bmax[k]+eps and bmin[k]<=amax[k]+eps for k in range(3)):
                    connected.add(a);changed=True;break
    groups={};counts={'Levelling foot':10,'Queue post base':4,'Operator monitor base':1,'Distant fare gate':3,'Square station column':2,'Column steel skirting':2,'Station back wall':1,'Walk-through detector floor foot':2,'Tray cart caster wheel':4}
    for prefix,count in counts.items():
        selected=[n for n in names if n==prefix or n.startswith(prefix+'.')]
        groups[prefix]={'expected_count':count,'actual_count':len(selected),'floor_gaps_m':{n:boxes[n][0][2]-floor_z for n in selected}}
    unconnected=[n for n in names if n not in connected]
    checks={'all_expected_ground_contacts_present':all(g['actual_count']==g['expected_count'] for g in groups.values()),
            'ground_contact_gaps_below_0p1mm':all(abs(gap)<.0001 for g in groups.values() for gap in g['floor_gaps_m'].values()),
            'static_AABB_components_connected_to_ground':not unconnected}
    return {'status':'passed' if all(checks.values()) else 'failed','checks':checks,'floor_top_z_m':floor_z,
            'static_mesh_count':len(names),'mounting_contact_tolerance_m':eps,'ground_groups':groups,'unconnected_static_objects':unconnected,
            'scope':'Evaluated Blender bounds and support connectivity; includes 2.6mm tolerance for decals/gaskets. Not structural strength or exact triangle-contact certification.',
            'execution_host':socket.gethostname(),'local_blender_used':False}
